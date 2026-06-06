"""
plugin/sp_bridge/handlers.py

所有 substance_painter.* API 调用都在这里。
这个模块的函数只能在 Painter 主线程执行（由 bridge.py 的调度机制保证）。

SP 10.x 实际 API：
  - substance_painter.layerstack（不是 layers）
  - get_root_layer_nodes(stack) 返回 List[Node]（节点对象，非 int ID）
  - 节点类型：type(node).__name__ → "FillLayerNode" / "GroupLayerNode" / ...
  - get_opacity(channel) / set_opacity(val, channel) 需要 ChannelType 参数
  - is_visible() / set_visible(bool) — 不是 is_enabled / set_enabled
"""

import contextlib
import io
import base64





def _sp():
    import substance_painter
    return substance_painter


def _sp_version() -> tuple:
    import substance_painter.application
    ver_str = substance_painter.application.version()
    return tuple(int(x) for x in ver_str.split(".")[:2])


def _has_smart_api() -> bool:
    return _sp_version() >= (10, 0)


# ── 自动 batch — 每个图层修改自动包裹 ScopedModification，生成单条 undo ──

_batch_scope = None


@contextlib.contextmanager
def _auto_batch(name: str):
    """如果外部 batch 已激活则跳过，否则用 ScopedModification 自动包裹。"""
    if _batch_scope is not None:
        yield
        return
    import substance_painter.layerstack as ls
    scope = ls.ScopedModification(name)
    scope.__enter__()
    try:
        yield
    finally:
        scope.__exit__(None, None, None)


# ── 节点克隆辅助 — 供 move/group/ungroup 进行 delete+re-insert ──


def _copy_channels(src_node, dst_node):
    import substance_painter.layerstack as ls
    import substance_painter.colormanagement as cm
    for ch in (ls.ChannelType.BaseColor, ls.ChannelType.Roughness,
               ls.ChannelType.Metallic, ls.ChannelType.Height, ls.ChannelType.Normal):
        dst_node.set_opacity(src_node.get_opacity(ch), ch)
        dst_node.set_blending_mode(src_node.get_blending_mode(ch), ch)
        try:
            src = src_node.get_source(ch)
            if src is not None:
                if hasattr(src, "get_color"):
                    c = src.get_color()
                    raw = c.value_raw
                    dst_node.set_source(ch, cm.Color(raw[0], raw[1], raw[2]))
                else:
                    dst_node.set_source(ch, src)
        except (AttributeError, TypeError):
            pass


def _clone_node(src_node, insert_pos):
    """在 insert_pos 处创建 src_node 的完整克隆，返回新节点。"""
    import substance_painter.layerstack as ls

    node_type = type(src_node).__name__

    if node_type == "GroupLayerNode":
        new_node = ls.insert_group(insert_pos)
        new_node.set_name(src_node.get_name())
        new_node.set_visible(src_node.is_visible())
        new_node.set_opacity(
            src_node.get_opacity(ls.ChannelType.BaseColor),
            ls.ChannelType.BaseColor,
        )
        for child in src_node.sub_layers():
            child_pos = ls.InsertPosition.inside_node(
                new_node, ls.NodeStack.Substack
            )
            _clone_node(child, child_pos)
    elif node_type == "PaintLayerNode":
        new_node = ls.insert_paint(insert_pos)
        new_node.set_name(src_node.get_name())
        new_node.set_visible(src_node.is_visible())
        _copy_channels(src_node, new_node)
    else:  # FillLayerNode (also handles other fill-like types)
        new_node = ls.insert_fill(insert_pos)
        new_node.set_name(src_node.get_name())
        new_node.set_visible(src_node.is_visible())
        _copy_channels(src_node, new_node)

    return new_node


# ── 公共入口 ──────────────────────────────────────────────────────────────────

def dispatch(req: dict):
    method = req.get("method")
    if not method:
        raise KeyError("Request missing 'method' field")
    fn = _REGISTRY.get(method)
    if fn is None:
        raise ValueError(f"Unknown method: {method!r}")
    params = req.get("params") or {}
    return fn(**params)


# ── handlers ─────────────────────────────────────────────────────────────────

def ping() -> dict:
    import substance_painter
    import substance_painter.application
    return {
        "status": "ok",
        "sp_version": substance_painter.application.version(),
        "sdk_version": substance_painter.__version__,
        "smart_api": _has_smart_api(),
    }


def get_layer_stack() -> list:
    """返回完整图层树，GROUP 类型含 children（递归）。"""
    import substance_painter.layerstack as ls
    import substance_painter.textureset as ts

    stack = ts.get_active_stack()
    nodes = ls.get_root_layer_nodes(stack)
    return _serialize_nodes(nodes)


def get_texture_sets(filter: str = "") -> list:
    """返回所有纹理集及其图层结构。"""
    import substance_painter.textureset as ts
    import substance_painter.layerstack as ls

    all_ts = ts.all_texture_sets()
    result = []
    for textureset in all_ts:
        name = textureset.name()
        if filter and filter.lower() not in name.lower():
            continue
        res = textureset.get_resolution()
        stack = textureset.get_stack()
        root_nodes = ls.get_root_layer_nodes(stack)
        layers = _serialize_nodes(root_nodes)
        result.append({
            "id": str(textureset.material_id),
            "name": name,
            "resolution": f"{res.width}x{res.height}",
            "layers": layers,
        })
    return result


def get_layer_properties(layer_id: str) -> dict:
    node = _find_layer(layer_id)
    import substance_painter.layerstack as ls
    ch = ls.ChannelType.BaseColor
    return {
        "id":            str(node.uid()),
        "name":          node.get_name(),
        "type":          type(node).__name__,
        "enabled":       node.is_visible(),
        "opacity":       node.get_opacity(ch),
        "blending_mode": node.get_blending_mode(ch).name,
    }


def add_fill_layer(
    name: str,
    channel: str = "BaseColor",
    color_hex: str = "#FFFFFF",
    opacity: float = 1.0,
    blend_mode: str = "Normal",
) -> dict:
    if not name:
        raise ValueError("name must not be empty")
    if not (0.0 <= opacity <= 1.0):
        raise ValueError(f"opacity must be in [0.0, 1.0], got {opacity}")

    with _auto_batch(f"Add Fill Layer '{name}'"):
        import substance_painter.layerstack as ls
        import substance_painter.textureset as ts

        stack = ts.get_active_stack()
        pos = ls.InsertPosition.from_textureset_stack(stack)
        layer = ls.insert_fill(pos)
        layer.set_name(name)

        ch = getattr(ls.ChannelType, channel, ls.ChannelType.BaseColor)
        layer.set_opacity(opacity, ch)

        blend = getattr(ls.BlendingMode, blend_mode, None)
        if blend is not None:
            layer.set_blending_mode(blend, ch)

        if color_hex and channel.lower() == "basecolor":
            r, g, b = _hex_to_rgb(color_hex)
            color = ls.Color(r, g, b)
            layer.set_source(ch, color)

        new_id = str(layer.uid())

        return {"id": new_id, "name": layer.get_name()}


def set_layer_property(layer_id: str, prop: str, value) -> dict:
    _VALID_PROPS = {"opacity", "enabled", "name", "blend_mode"}
    if prop not in _VALID_PROPS:
        raise ValueError(
            f"Unsupported prop: {prop!r}. Valid: {sorted(_VALID_PROPS)}"
        )

    with _auto_batch(f"Set layer {prop}"):
        node = _find_layer(layer_id)
        import substance_painter.layerstack as ls

        if prop == "opacity":
            node.set_opacity(float(value), ls.ChannelType.BaseColor)
        elif prop == "enabled":
            node.set_visible(bool(value))
        elif prop == "name":
            node.set_name(str(value))
        elif prop == "blend_mode":
            blend = getattr(ls.BlendingMode, str(value), None)
            if blend is None:
                raise ValueError(f"Unknown blend mode: {value!r}")
            node.set_blending_mode(blend)

        return {"ok": True}


def apply_smart_material(layer_id: str, material_name: str) -> dict:
    with _auto_batch(f"Apply Smart Material '{material_name}'"):
        _require_smart_api("apply_smart_material")
        import substance_painter.resource as r
        import substance_painter.layerstack as ls

        node = _find_layer(layer_id)
        resource = _find_resource(material_name, r.Type.SMART_MATERIAL)
        if resource is None:
            raise ValueError(f"Smart Material not found: {material_name!r}")

        pos = ls.InsertPosition.above_node(node)
        group = ls.insert_smart_material(pos, resource.identifier())
        return {"id": str(group.uid()), "name": group.get_name()}


def add_smart_mask(layer_id: str, mask_name: str) -> dict:
    with _auto_batch(f"Add Smart Mask '{mask_name}'"):
        _require_smart_api("add_smart_mask")
        import substance_painter.resource as r
        import substance_painter.layerstack as ls

        node = _find_layer(layer_id)
        resource = _find_resource(mask_name, r.Type.SMART_MASK)
        if resource is None:
            raise ValueError(f"Smart Mask not found: {mask_name!r}")

        node.add_mask(ls.MaskBackground.White)
        pos = ls.InsertPosition.inside_node(node, ls.NodeStack.Mask)
        effects = ls.insert_smart_mask(pos, resource.identifier())
        return {"ok": True, "effects_count": len(effects)}


def list_shelf_materials(filter: str = "") -> list:
    import substance_painter.resource as r

    results = r.search(filter) if filter else r.search("")
    materials = []
    for res in results:
        try:
            if res.type() == r.Type.SMART_MATERIAL:
                materials.append(res.gui_name())
        except (ValueError, AttributeError):
            continue
    return sorted(set(materials))


def list_materials(filter: str = "") -> list:
    """列出所有普通材质（SUBSTANCE 类型），支持关键词过滤。"""
    import substance_painter.resource as r

    results = r.search(filter) if filter else r.search("")
    materials = []
    for res in results:
        try:
            if res.type() == r.Type.SUBSTANCE:
                materials.append(res.gui_name())
        except (ValueError, AttributeError):
            continue
    return sorted(set(materials))


def apply_material(layer_id: str, material_name: str) -> dict:
    """将普通材质（SUBSTANCE 类型）应用到指定图层的所有通道。"""
    with _auto_batch(f"Apply Material '{material_name}'"):
        import substance_painter.resource as r
        import substance_painter.layerstack as ls

        node = _find_layer(layer_id)
        resource = _find_resource(material_name, r.Type.SUBSTANCE)
        if resource is None:
            raise ValueError(f"Material not found: {material_name!r}")

        rid = resource.identifier()
        for ch in (ls.ChannelType.BaseColor, ls.ChannelType.Roughness,
                   ls.ChannelType.Metallic, ls.ChannelType.Height, ls.ChannelType.Normal):
            try:
                node.set_source(ch, rid)
            except Exception:
                pass
        return {"ok": True, "material": material_name, "layer_id": str(node.uid())}


def capture_viewport(mode: str = "quick") -> dict:
    if mode == "quick":
        return _capture_qt()
    elif mode == "render":
        return _capture_iray()
    else:
        raise ValueError(f"Unknown capture mode: {mode!r}. Use 'quick' or 'render'.")


def export_textures(preset: str, output_dir: str) -> dict:
    if not output_dir:
        raise ValueError("output_dir must not be empty")
    import substance_painter.export
    config = substance_painter.export.ExportConfig()
    config.export_path = output_dir
    config.preset = preset
    result = substance_painter.export.export_project_textures(config)
    return {"files": [str(f) for f in result.textures]}


def run_python(code: str) -> dict:
    sp = _sp()
    buf = io.StringIO()
    local: dict = {}
    with contextlib.redirect_stdout(buf):
        exec(code, {"sp": sp, "__builtins__": __builtins__}, local)  # noqa: S102
    return {
        "stdout": buf.getvalue(),
        "locals": {k: repr(v) for k, v in local.items()},
    }


# ── Phase 6: 图层基础 + 通道 + Undo ─────────────────────────────────────────

def delete_layer(layer_id: str) -> dict:
    with _auto_batch("Delete layer"):
        node = _find_layer(layer_id)
        import substance_painter.layerstack as ls
        ls.delete_node(node)

        return {"ok": True}


def add_group_layer(name: str) -> dict:
    if not name:
        raise ValueError("name must not be empty")
    with _auto_batch(f"Add Group Layer '{name}'"):
        import substance_painter.layerstack as ls
        import substance_painter.textureset as ts

        stack = ts.get_active_stack()
        pos = ls.InsertPosition.from_textureset_stack(stack)
        node = ls.insert_group(pos)
        node.set_name(name)
        return {"id": str(node.uid()), "name": node.get_name()}


def add_paint_layer(name: str) -> dict:
    if not name:
        raise ValueError("name must not be empty")
    with _auto_batch(f"Add Paint Layer '{name}'"):
        import substance_painter.layerstack as ls
        import substance_painter.textureset as ts

        stack = ts.get_active_stack()
        pos = ls.InsertPosition.from_textureset_stack(stack)
        node = ls.insert_paint(pos)
        node.set_name(name)
        return {"id": str(node.uid()), "name": node.get_name()}


def undo() -> dict:
    """撤销上一步操作（SP 原生 undo 栈）。"""
    import contextlib as _ctx
    import io as _io

    code = (
        "from substance_painter.ui import get_main_window\n"
        "from PySide2.QtWidgets import QUndoView\n"
        "mv = get_main_window()\n"
        "views = mv.findChildren(QUndoView)\n"
        "for v in views:\n"
        "    if v.objectName() == 'history':\n"
        "        s = v.stack()\n"
        "        if s.canUndo():\n"
        "            s.undo()\n"
        "            print('ok')\n"
        "        else:\n"
        "            print('empty')\n"
        "        break\n"
        "else:\n"
        "    print('not_found')\n"
    )
    result = run_python(code)
    output = result.get("stdout", "").strip()
    if output == "ok":
        return {"ok": True}
    elif output == "empty":
        return {"ok": False, "error": "Nothing to undo"}
    else:
        return {"ok": False, "error": "Undo history not found"}


def redo() -> dict:
    """重做上一步操作（SP 原生 redo 栈）。"""
    code = (
        "from substance_painter.ui import get_main_window\n"
        "from PySide2.QtWidgets import QUndoView\n"
        "mv = get_main_window()\n"
        "views = mv.findChildren(QUndoView)\n"
        "for v in views:\n"
        "    if v.objectName() == 'history':\n"
        "        s = v.stack()\n"
        "        if s.canRedo():\n"
        "            s.redo()\n"
        "            print('ok')\n"
        "        else:\n"
        "            print('empty')\n"
        "        break\n"
        "else:\n"
        "    print('not_found')\n"
    )
    result = run_python(code)
    output = result.get("stdout", "").strip()
    if output == "ok":
        return {"ok": True}
    elif output == "empty":
        return {"ok": False, "error": "Nothing to redo"}
    else:
        return {"ok": False, "error": "Undo history not found"}


_CHANNEL_MAP = {
    "roughness":  "Roughness",
    "metallic":   "Metallic",
    "height":     "Height",
    "basecolor":  "BaseColor",
    "normal":     "Normal",
}


def set_layer_channel(layer_id: str, channel: str, value) -> dict:
    ch_key = channel.lower()
    if ch_key not in _CHANNEL_MAP:
        raise ValueError(
            f"Unknown channel: {channel!r}. Valid: {sorted(_CHANNEL_MAP.keys())}"
        )
    with _auto_batch(f"Set {channel} channel"):
        node = _find_layer(layer_id)
        import substance_painter.layerstack as ls
        import substance_painter.colormanagement as cm

        ch = getattr(ls.ChannelType, _CHANNEL_MAP[ch_key])

        if ch_key == "basecolor":
            r, g, b = _hex_to_rgb(str(value))
            node.set_source(ch, cm.Color(r, g, b))
        else:
            v = float(value)
            node.set_source(ch, cm.Color(v, v, v))

        return {"ok": True}


def get_layer_channels(layer_id: str) -> dict:
    node = _find_layer(layer_id)
    import substance_painter.layerstack as ls

    result = {}
    for ch_name in ("BaseColor", "Roughness", "Metallic", "Height", "Normal"):
        ch = getattr(ls.ChannelType, ch_name)
        source = node.get_source(ch)
        entry = {
            "opacity":    node.get_opacity(ch),
            "blend_mode": node.get_blending_mode(ch).name,
        }
        if source is not None:
            # SourceUniformColor → get_color().value_raw
            if hasattr(source, "get_color"):
                c = source.get_color()
                raw = c.value_raw
                if ch_name == "BaseColor":
                    entry["source"] = f"#{int(raw[0]*255):02x}{int(raw[1]*255):02x}{int(raw[2]*255):02x}"
                else:
                    entry["source"] = raw[0]
            elif hasattr(source, "r"):
                entry["source"] = f"#{int(source.r*255):02x}{int(source.g*255):02x}{int(source.b*255):02x}"
            else:
                entry["source"] = str(source)
        result[ch_name] = entry
    return result


# ── Phase 7: 图层高级 + TextureSet + 项目 + 相机 ─────────────────────────────

def duplicate_layer(layer_id: str) -> dict:
    with _auto_batch("Duplicate layer"):
        node = _find_layer(layer_id)
        import substance_painter.layerstack as ls
        import substance_painter.textureset as ts

        stack = ts.get_active_stack()
        pos = ls.InsertPosition.above_node(node)
        new_node = ls.insert_fill(pos)
        new_node.set_name(node.get_name())

        # GroupLayerNode 没有 get_source，只复制 fill layer 的通道属性
        if type(node).__name__ != "GroupLayerNode":
            import substance_painter.colormanagement as cm
            for ch in (ls.ChannelType.BaseColor, ls.ChannelType.Roughness,
                       ls.ChannelType.Metallic, ls.ChannelType.Height, ls.ChannelType.Normal):
                new_node.set_opacity(node.get_opacity(ch), ch)
                new_node.set_blending_mode(node.get_blending_mode(ch), ch)
                try:
                    src = node.get_source(ch)
                    if src is not None and hasattr(src, "get_color"):
                        c = src.get_color()
                        raw = c.value_raw
                        new_node.set_source(ch, cm.Color(raw[0], raw[1], raw[2]))
                except (AttributeError, TypeError):
                    pass

        new_id = str(new_node.uid())

        return {"id": new_id, "name": new_node.get_name()}


def move_layer(layer_id: str, target_id: str, position: str = "above") -> dict:
    src = _find_layer(layer_id)
    target = _find_layer(target_id)

    if src is target:
        return {"ok": True}

    import substance_painter.layerstack as ls

    with _auto_batch("Move layer"):
        if position == "above":
            insert_pos = ls.InsertPosition.above_node(target)
        else:
            insert_pos = ls.InsertPosition.below_node(target)

        new_node = _clone_node(src, insert_pos)
        ls.delete_node(src)

    return {"id": str(new_node.uid()), "name": new_node.get_name(), "ok": True}


def group_layers(layer_ids: list) -> dict:
    import substance_painter.layerstack as ls
    import substance_painter.textureset as ts

    with _auto_batch("Group layers"):
        nodes = [_find_layer(uid) for uid in layer_ids]
        stack = ts.get_active_stack()
        root_nodes = ls.get_root_layer_nodes(stack)

        # Sort by stack order
        all_flat = []
        def _flatten(ns):
            for n in ns:
                all_flat.append(n)
                if type(n).__name__ == "GroupLayerNode":
                    _flatten(n.sub_layers())
        _flatten(root_nodes)
        sorted_nodes = sorted(nodes, key=lambda n: all_flat.index(n) if n in all_flat else 9999)

        first = sorted_nodes[0]
        group = ls.insert_group(ls.InsertPosition.above_node(first))
        group.set_name("Group")

        for node in sorted_nodes:
            child_pos = ls.InsertPosition.inside_node(group, ls.NodeStack.Substack)
            _clone_node(node, child_pos)
            ls.delete_node(node)

    return {"id": str(group.uid()), "name": group.get_name(), "ok": True}


def ungroup_layer(layer_id: str) -> dict:
    import substance_painter.layerstack as ls

    with _auto_batch("Ungroup layer"):
        group = _find_layer(layer_id)
        if type(group).__name__ != "GroupLayerNode":
            raise ValueError(f"Layer is not a group: {layer_id!r}")

        children = list(group.sub_layers())
        for child in children:
            insert_pos = ls.InsertPosition.above_node(group)
            _clone_node(child, insert_pos)
            ls.delete_node(child)

        ls.delete_node(group)

    return {"ok": True}


def set_active_texture_set(name: str) -> dict:
    import substance_painter.textureset as ts
    for textureset in ts.all_texture_sets():
        if textureset.name() == name:
            ts.set_active_stack(textureset.get_stack())
            return {"ok": True}
    raise ValueError(f"Texture set not found: {name!r}")


def set_texture_set_resolution(width: int, height: int) -> dict:
    if width <= 0 or height <= 0:
        raise ValueError(f"width and height must be positive, got {width}x{height}")
    import substance_painter.textureset as ts
    stack = ts.get_active_stack()
    for textureset in ts.all_texture_sets():
        if textureset.get_stack() is stack:
            textureset.set_resolution(width, height)
            return {"ok": True}
    return {"ok": True}


def get_project_info() -> dict:
    import substance_painter.project
    return {
        "name":        substance_painter.project.name(),
        "file_path":   substance_painter.project.file_path(),
        "is_open":     substance_painter.project.is_open(),
        "is_busy":     substance_painter.project.is_busy(),
    }


def save_project() -> dict:
    import substance_painter.project
    substance_painter.project.save()
    return {"ok": True}


def set_camera(
    x: float, y: float, z: float,
    target_x: float, target_y: float, target_z: float,
    fov: float,
) -> dict:
    import substance_painter.display as display
    cam = display.Camera.get_default_camera()
    cam.position = [x, y, z]
    cam.field_of_view = fov
    return {"ok": True}


def frame_mesh() -> dict:
    import math
    import substance_painter.project as project
    import substance_painter.display as display

    with _auto_batch("Frame mesh"):
        bb = project.get_scene_bounding_box()
        cx, cy, cz = bb.center
        radius = bb.radius

        cam = display.Camera.get_default_camera()
        px, py, pz = cam.position

        # Direction from current camera position to bounding box center
        dx = cx - px
        dy = cy - py
        dz = cz - pz
        length = math.sqrt(dx * dx + dy * dy + dz * dz)

        if length < 0.001:
            dx, dy, dz = 0.0, 0.0, 1.0
        else:
            dx, dy, dz = dx / length, dy / length, dz / length

        # Distance needed to frame the bounding box within the current FOV
        fov_rad = math.radians(cam.field_of_view / 2.0)
        distance = radius / math.tan(fov_rad) * 1.2

        # Move camera along current line of sight to the proper distance
        cam.position = [
            cx - dx * distance,
            cy - dy * distance,
            cz - dz * distance,
        ]

    return {"ok": True}


def set_environment(preset: str) -> dict:
    import substance_painter.display as display
    import substance_painter.resource as r
    # 查找匹配的环境资源
    resources = r.search(preset)
    for res in resources:
        if preset.lower() in res.gui_name().lower():
            display.set_environment_resource(res.identifier())
            return {"ok": True, "environment": res.gui_name()}
    raise ValueError(f"Environment preset not found: {preset!r}")


# ── Phase 8: 批量 Undo ──────────────────────────────────────────────────────


def begin_batch(name: str) -> dict:
    """开始批量操作。后续 layer 操作将合并为单条 undo。"""
    global _batch_scope
    if not name:
        raise ValueError("name must not be empty")
    if _batch_scope is not None:
        raise RuntimeError("A batch is already active. Call end_batch() first.")
    import substance_painter.layerstack as ls
    _batch_scope = ls.ScopedModification(name)
    _batch_scope.__enter__()
    return {"ok": True, "batch_name": name}


def end_batch() -> dict:
    """结束批量操作，合并为单条 undo。"""
    global _batch_scope
    if _batch_scope is None:
        raise RuntimeError("No active batch. Call begin_batch() first.")
    _batch_scope.__exit__(None, None, None)
    _batch_scope = None
    return {"ok": True}


# ── Phase 9: JS API 集成 ────────────────────────────────────────────────────

def bake_mesh_maps(texture_set_name: str) -> dict:
    """通过 JS API 烘焙指定纹理集的 mesh maps。"""
    if not texture_set_name:
        raise ValueError("texture_set_name must not be empty")
    import substance_painter.js as js
    js.evaluate(f'alg.baking.bake("{texture_set_name}")')
    return {"ok": True, "texture_set": texture_set_name}


def add_texture_set_channel(texture_set_name: str, channel_id: str,
                             channel_format: str = "RGB16F",
                             channel_label: str = "") -> dict:
    """通过 JS API 给纹理集添加通道。"""
    if not texture_set_name:
        raise ValueError("texture_set_name must not be empty")
    if not channel_id:
        raise ValueError("channel_id must not be empty")
    label = channel_label or channel_id
    import substance_painter.js as js
    js.evaluate(
        f'alg.texturesets.addChannel(["{texture_set_name}"], '
        f'"{channel_id}", "{channel_format}", "{label}")'
    )
    return {"ok": True, "channel": channel_id}


def remove_texture_set_channel(texture_set_name: str, channel_id: str) -> dict:
    """通过 JS API 删除纹理集通道。"""
    if not texture_set_name:
        raise ValueError("texture_set_name must not be empty")
    if not channel_id:
        raise ValueError("channel_id must not be empty")
    import substance_painter.js as js
    js.evaluate(f'alg.texturesets.removeChannel(["{texture_set_name}"], "{channel_id}")')
    return {"ok": True, "channel": channel_id}


# ── 内部工具 ──────────────────────────────────────────────────────────────────

def _serialize_nodes(nodes: list) -> list:
    """将 node 对象列表序列化为 JSON 兼容的图层树。"""
    import substance_painter.layerstack as ls

    result = []
    for node in nodes:
        node_type_name = type(node).__name__
        entry = {
            "id":      str(node.uid()),
            "name":    node.get_name(),
            "type":    node_type_name,
            "enabled": node.is_visible(),
            "opacity": node.get_opacity(ls.ChannelType.BaseColor),
        }
        if node_type_name == "GroupLayerNode":
            children = node.sub_layers()
            entry["children"] = _serialize_nodes(children)
        result.append(entry)
    return result


def _find_layer(uid: str):
    """在图层栈中递归查找指定 uid 的节点，找不到抛 ValueError。"""
    import substance_painter.layerstack as ls
    import substance_painter.textureset as ts

    stack = ts.get_active_stack()
    root_nodes = ls.get_root_layer_nodes(stack)
    found = _search_nodes(root_nodes, uid)
    if found is None:
        raise ValueError(f"Layer not found: {uid!r}")
    return found


def _search_nodes(nodes: list, uid: str):
    """递归搜索节点列表，返回匹配的 node 对象或 None。"""
    for node in nodes:
        if str(node.uid()) == uid:
            return node
        if type(node).__name__ == "GroupLayerNode":
            children = node.sub_layers()
            found = _search_nodes(children, uid)
            if found is not None:
                return found
    return None


def _find_resource(name: str, res_type):
    """按 gui_name 搜索指定类型的资源，返回 Resource 或 None。"""
    import substance_painter.resource as r
    results = r.search(name)
    for res in results:
        if res.type() == res_type and res.gui_name() == name:
            return res
    return None


def _require_smart_api(fn_name: str) -> None:
    if not _has_smart_api():
        import substance_painter.application
        raise RuntimeError(
            f"{fn_name} requires SP 10.0+, current version: "
            f"{substance_painter.application.version()}"
        )


def _hex_to_rgb(hex_color: str) -> tuple:
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i+2], 16) / 255.0 for i in (0, 2, 4))


def set_iray_params(
    max_samples: int = 100,
    max_time: int = 60,
    width: int = 0,
    height: int = 0,
) -> dict:
    """设置 Iray 渲染参数。width/height 为 0 表示不修改。"""
    import substance_painter.ui
    from PySide2.QtWidgets import QDockWidget, QWidget, QLineEdit, QSpinBox

    win = substance_painter.ui.get_main_window()
    panel = None
    for dock in win.findChildren(QDockWidget):
        if dock.objectName() == "irayParametersView":
            panel = dock.widget()
            break
    if panel is None:
        raise RuntimeError("Iray parameters panel not found")

    def _set_line_edit(container_name, value):
        container = panel.findChild(QWidget, container_name)
        if container:
            le = container.findChild(QLineEdit, "value")
            if le:
                le.setText(str(value))
                le.editingFinished.emit()
                return True
        return False

    _set_line_edit("maxSamples", max_samples)
    _set_line_edit("maxTime", max_time)

    if width > 0:
        sb = panel.findChild(QSpinBox, "width")
        if sb:
            sb.setValue(width)
    if height > 0:
        sb = panel.findChild(QSpinBox, "height")
        if sb:
            sb.setValue(height)

    return {"ok": True, "max_samples": max_samples, "max_time": max_time}


# Iray 异步渲染状态
_iray_render_state = {"active": False, "start_time": 0}


def start_iray_render() -> dict:
    """异步启动 Iray 渲染（通过 QTimer 延迟触发，避免阻塞 HTTP）。"""
    import substance_painter.ui
    from PySide2.QtWidgets import QAction

    win = substance_painter.ui.get_main_window()
    iray_action = None
    for action in win.findChildren(QAction):
        if action.text() == "Rendering (Iray)" and action.isEnabled():
            iray_action = action
            break

    if iray_action is None:
        raise RuntimeError("Iray rendering action not found")

    # 延迟 500ms 触发，让 HTTP 响应先返回
    from PySide2.QtCore import QTimer
    QTimer.singleShot(500, iray_action.trigger)

    _iray_render_state["active"] = True
    _iray_render_state["start_time"] = __import__("time").time()

    return {"ok": True, "message": "Iray render queued (starts in 500ms)"}


def check_iray_render() -> dict:
    """检查 Iray 渲染状态。返回 iterations 和 time 信息。"""
    import substance_painter.ui
    from PySide2.QtWidgets import QDockWidget

    win = substance_painter.ui.get_main_window()
    panel = None
    for dock in win.findChildren(QDockWidget):
        if dock.objectName() == "irayParametersView":
            panel = dock.widget()
            break

    if panel is None:
        return {"active": False, "error": "Iray panel not found"}

    iterations_label = panel.findChild(type(panel), "iterationsLabel")
    time_label = panel.findChild(type(panel), "timeLabel")

    result = {"active": _iray_render_state.get("active", False)}
    if iterations_label:
        result["iterations"] = iterations_label.text()
    if time_label:
        result["time"] = time_label.text()

    return result


def _capture_qt() -> dict:
    import substance_painter.ui
    try:
        from PySide2.QtWidgets import QOpenGLWidget
        from PySide2.QtCore import QBuffer, QIODevice
    except ImportError:
        from PySide6.QtOpenGLWidgets import QOpenGLWidget          # type: ignore
        from PySide6.QtCore import QBuffer, QIODevice              # type: ignore

    main_win = substance_painter.ui.get_main_window()
    viewports = main_win.findChildren(QOpenGLWidget)

    if not viewports:
        raise RuntimeError("No QOpenGLWidget found — is a project open?")

    viewport = max(viewports, key=lambda w: w.width() * w.height())
    pixmap = viewport.grab()

    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    pixmap.save(buf, "PNG")
    data = bytes(buf.data())

    return {
        "image":  base64.b64encode(data).decode("ascii"),
        "width":  pixmap.width(),
        "height": pixmap.height(),
    }


def _capture_iray() -> dict:
    """Iray 模式截图。

    用户工作流：
    1. sp_set_iray_params(max_samples=50, max_time=30)  设置低质量
    2. 手动在 Painter 按 F10 或 Mode > Rendering 触发 Iray
    3. 等待渲染完成
    4. sp_capture_viewport(mode="render") 截取当前 viewport

    本函数使用 Qt grab 截取当前 viewport 状态。
    """
    result = _capture_qt()
    result["mode"] = "render"
    return result


# ── 方法注册表 ────────────────────────────────────────────────────────────────

_REGISTRY: dict = {
    "ping":                     ping,
    "get_layer_stack":          get_layer_stack,
    "get_texture_sets":         get_texture_sets,
    "get_layer_properties":     get_layer_properties,
    "add_fill_layer":           add_fill_layer,
    "set_layer_property":       set_layer_property,
    "apply_smart_material":     apply_smart_material,
    "add_smart_mask":           add_smart_mask,
    "list_shelf_materials":     list_shelf_materials,
    "list_materials":           list_materials,
    "apply_material":           apply_material,
    "set_iray_params":          set_iray_params,
    "start_iray_render":        start_iray_render,
    "check_iray_render":        check_iray_render,
    "capture_viewport":         capture_viewport,
    "export_textures":          export_textures,
    "run_python":               run_python,
    # Phase 6
    "delete_layer":             delete_layer,
    "add_group_layer":          add_group_layer,
    "add_paint_layer":          add_paint_layer,
    "undo":                     undo,
    "redo":                     redo,
    "set_layer_channel":        set_layer_channel,
    "get_layer_channels":       get_layer_channels,
    # Phase 7
    "duplicate_layer":          duplicate_layer,
    "move_layer":               move_layer,
    "group_layers":             group_layers,
    "ungroup_layer":            ungroup_layer,
    "set_active_texture_set":   set_active_texture_set,
    "set_texture_set_resolution": set_texture_set_resolution,
    "get_project_info":         get_project_info,
    "save_project":             save_project,
    "set_camera":               set_camera,
    "frame_mesh":               frame_mesh,
    "set_environment":          set_environment,
    # Phase 8
    "begin_batch":              begin_batch,
    "end_batch":                end_batch,
    # Phase 9
    "bake_mesh_maps":           bake_mesh_maps,
    "add_texture_set_channel":  add_texture_set_channel,
    "remove_texture_set_channel": remove_texture_set_channel,
}
