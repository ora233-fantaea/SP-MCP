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
import traceback as _traceback


def _log_info(msg: str):
    """Log an informational audit message to SP's logging system."""
    try:
        import substance_painter.logging
        substance_painter.logging.log(
            substance_painter.logging.INFO,
            "sp_bridge",
            msg,
        )
    except Exception:
        pass


def _log_warning(msg: str):
    """Log a warning to SP's logging system. Silently ignored if unavailable (tests)."""
    try:
        import substance_painter.logging
        substance_painter.logging.log(
            substance_painter.logging.WARNING,
            "sp_bridge",
            msg,
        )
    except Exception:
        pass





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
            _log_warning(
                f"_copy_channels: failed to copy source for channel {ch} "
                f"on node {type(src_node).__name__} — {_traceback.format_exc()}"
            )
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

        _log_info(f"add_fill_layer: name={name!r} id={new_id}")
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
        _log_info(f"apply_smart_material: layer={layer_id!r} material={material_name!r} group={str(group.uid())}")
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
                _log_warning(
                    f"apply_material: failed to set source for channel {ch} "
                    f"on layer {layer_id!r} with material {material_name!r} — "
                    f"{_traceback.format_exc()}"
                )
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
    files = [str(f) for f in result.textures]
    _log_info(f"export_textures: preset={preset!r} output_dir={output_dir!r} files={len(files)}")
    return {"files": files}


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
        _log_info(f"delete_layer: id={layer_id!r} name={node.get_name()!r}")
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
                    _log_warning(
                        f"duplicate_layer: failed to copy channel {ch} "
                        f"on layer {layer_id!r} — {_traceback.format_exc()}"
                    )
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

        if not sorted_nodes:
            raise ValueError("group_layers: layer_ids must not be empty")

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
    _log_info("save_project: saved")
    return {"ok": True}


def set_camera(
    x: float = 0.0, y: float = 0.0, z: float = 0.0,
    target_x: float = 0.0, target_y: float = 0.0, target_z: float = 0.0,
    fov: float = 0.0,
) -> dict:
    import math
    import substance_painter.display as display

    cam = display.Camera.get_default_camera()

    # 读取当前状态
    px, py, pz = cam.position
    rx, ry, rz = cam.rotation
    current_fov = cam.field_of_view

    # 位置：非零值才覆盖
    new_x = x if x != 0.0 else px
    new_y = y if y != 0.0 else py
    new_z = z if z != 0.0 else pz
    cam.position = [new_x, new_y, new_z]

    # FOV：非零值才覆盖
    cam.field_of_view = fov if fov != 0.0 else current_fov

    # 目标点：有值时计算旋转朝向目标
    if target_x != 0.0 or target_y != 0.0 or target_z != 0.0:
        dx = target_x - new_x
        dy = target_y - new_y
        dz = target_z - new_z
        length = math.sqrt(dx * dx + dy * dy + dz * dz)
        if length > 0.001:
            # 计算欧拉角（简化版：只算 yaw/pitch）
            yaw = math.degrees(math.atan2(dx, dz))
            pitch = math.degrees(math.atan2(-dy, math.sqrt(dx * dx + dz * dz)))
            cam.rotation = [pitch, yaw, rz]

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
    _log_info(f"begin_batch: {name!r}")
    return {"ok": True, "batch_name": name}


def end_batch() -> dict:
    """结束批量操作，合并为单条 undo。"""
    global _batch_scope
    if _batch_scope is None:
        raise RuntimeError("No active batch. Call begin_batch() first.")
    _batch_scope.__exit__(None, None, None)
    _batch_scope = None
    _log_info("end_batch: committed")
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


# ── Computer Use ───────────────────────────────────────────────────────────────

def window_info() -> dict:
    import substance_painter.ui as ui
    win = ui.get_main_window()
    geo = win.geometry()
    from PySide2.QtCore import QPoint
    origin = win.mapToGlobal(QPoint(0, 0))
    return {
        "screen_origin": {"x": origin.x(), "y": origin.y()},
        "geometry": {"x": geo.x(), "y": geo.y(), "width": geo.width(), "height": geo.height()},
        "is_minimized": win.isMinimized(),
        "is_maximized": win.isMaximized(),
        "is_fullscreen": win.isFullScreen(),
        "is_visible": win.isVisible(),
        "is_active": win.isActiveWindow(),
    }


def window_grab(region: dict = None) -> dict:
    import substance_painter.ui as ui
    import base64
    import ctypes as ct
    import struct

    win = ui.get_main_window()
    hwnd = int(win.winId())
    user32 = ct.windll.user32
    gdi32 = ct.windll.gdi32

    # Get window rect
    buf = ct.create_string_buffer(16)
    user32.GetWindowRect(hwnd, buf)
    left, top, right, bottom = struct.unpack("iiii", buf.raw[:16])
    full_w, full_h = right - left, bottom - top

    hdc_window = user32.GetDC(hwnd)
    hdc_mem = gdi32.CreateCompatibleDC(hdc_window)
    hbmp = gdi32.CreateCompatibleBitmap(hdc_window, full_w, full_h)
    gdi32.SelectObject(hdc_mem, hbmp)

    # PW_RENDERFULLCONTENT = 2 — captures OpenGL rendered content correctly
    user32.PrintWindow(hwnd, hdc_mem, 2)

    if region and all(k in region for k in ("x", "y", "width", "height")):
        rx, ry, rw, rh = region["x"], region["y"], region["width"], region["height"]
    else:
        rx, ry, rw, rh = 0, 0, full_w, full_h

    # Extract region bits
    bmi = struct.pack("IiiHHIIiiII", 40, rw, -rh, 1, 32, 0, rw * rh * 4, 0, 0, 0, 0)
    pixel_buf = ct.create_string_buffer(rw * rh * 4)
    gdi32.GetDIBits(hdc_mem, hbmp, ry, rh, pixel_buf, bmi, 0)

    from PySide2.QtGui import QImage, QPixmap
    img = QImage(bytes(pixel_buf), rw, rh, QImage.Format_ARGB32)
    pixmap = QPixmap.fromImage(img)

    gdi32.DeleteObject(hbmp)
    gdi32.DeleteDC(hdc_mem)
    user32.ReleaseDC(hwnd, hdc_window)

    tmp = __import__("tempfile").mktemp(suffix=".png")
    pixmap.save(tmp, "PNG")
    with open(tmp, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    __import__("os").unlink(tmp)
    return {"image": b64, "width": rw, "height": rh}


def _get_mouse_pos():
    import ctypes as ct
    user32 = ct.windll.user32
    buf = ct.create_string_buffer(8)
    user32.GetCursorPos(buf)
    return (ct.c_long.from_buffer(buf, 0).value, ct.c_long.from_buffer(buf, 4).value)


def _set_mouse_pos(x: int, y: int):
    import ctypes as ct
    ct.windll.user32.SetCursorPos(x, y)


def _mouse_event(flags: int, data: int = 0):
    import ctypes as ct
    ct.windll.user32.mouse_event(flags, 0, 0, data, 0)


_MOUSEEVENTF_LEFTDOWN = 0x0002
_MOUSEEVENTF_LEFTUP = 0x0004
_MOUSEEVENTF_RIGHTDOWN = 0x0008
_MOUSEEVENTF_RIGHTUP = 0x0010
_MOUSEEVENTF_MIDDLEDOWN = 0x0020
_MOUSEEVENTF_MIDDLEUP = 0x0040
_MOUSEEVENTF_WHEEL = 0x0800

_cu_banner = None


def _show_cu_banner():
    global _cu_banner
    if _cu_banner is not None:
        return
    import substance_painter.ui as ui
    from PySide2.QtWidgets import QLabel
    from PySide2.QtCore import Qt
    win = ui.get_main_window()
    banner = QLabel(win)
    banner.setText("MCP Control Active - Do not touch mouse/keyboard")
    banner.setObjectName("_mcp_cu_banner")
    banner.setStyleSheet("""
        QLabel#_mcp_cu_banner {
            background-color: rgba(220, 50, 50, 230);
            color: white;
            font-size: 15px;
            font-weight: bold;
            padding: 8px 40px;
            border-radius: 4px;
        }
    """)
    banner.setAlignment(Qt.AlignCenter)
    banner.adjustSize()
    bw = banner.width()
    banner.move((win.width() - bw) // 2, 5)
    banner.raise_()
    banner.show()
    _cu_banner = banner


def _hide_cu_banner():
    global _cu_banner
    if _cu_banner is None:
        return
    _cu_banner.hide()
    _cu_banner.deleteLater()
    _cu_banner = None


def window_focus() -> dict:
    import time
    import ctypes as ct
    import substance_painter.ui as ui

    _show_cu_banner()

    win = ui.get_main_window()

    if win.isMinimized():
        win.showNormal()

    win.raise_()
    win.activateWindow()

    hwnd = int(win.winId())
    ct.windll.user32.SetForegroundWindow(hwnd)

    time.sleep(0.05)

    return {
        "focused": win.isActiveWindow(),
        "is_minimized": win.isMinimized(),
        "hwnd": hwnd,
    }


def cu_unlock() -> dict:
    global _cu_banner
    if _cu_banner is None:
        return {"ok": True}
    _cu_banner.setText("MCP Control Released")
    _cu_banner.setStyleSheet("""
        QLabel#_mcp_cu_banner {
            background-color: rgba(50, 180, 80, 230);
            color: white;
            font-size: 15px;
            font-weight: bold;
            padding: 8px 40px;
            border-radius: 4px;
        }
    """)
    _cu_banner.adjustSize()
    import substance_painter.ui as ui
    win = ui.get_main_window()
    bw = _cu_banner.width()
    _cu_banner.move((win.width() - bw) // 2, 5)

    from PySide2.QtCore import QTimer
    QTimer.singleShot(10000, _hide_cu_banner)
    return {"ok": True}


def cu_banner_text(text: str) -> dict:
    global _cu_banner
    if _cu_banner is None:
        return {"ok": False, "error": "No active banner. Call window_focus first."}
    _cu_banner.setText(text)
    _cu_banner.adjustSize()
    bw = _cu_banner.width()
    import substance_painter.ui as ui
    win = ui.get_main_window()
    _cu_banner.move((win.width() - bw) // 2, 5)
    return {"ok": True, "text": text}


def cu_warning(text: str = "") -> dict:
    global _cu_banner
    if _cu_banner is None:
        return {"ok": False, "error": "No active banner. Call window_focus first."}
    if not text:
        text = "Timeout - Please check SP for confirmation dialogs, or check terminal for permission requests"
    _cu_banner.setText(text)
    _cu_banner.setStyleSheet("""
        QLabel#_mcp_cu_banner {
            background-color: rgba(220, 160, 30, 230);
            color: white;
            font-size: 15px;
            font-weight: bold;
            padding: 8px 40px;
            border-radius: 4px;
        }
    """)
    _cu_banner.adjustSize()
    bw = _cu_banner.width()
    import substance_painter.ui as ui
    win = ui.get_main_window()
    _cu_banner.move((win.width() - bw) // 2, 5)
    return {"ok": True, "text": text}


def mouse_move(x: int, y: int, relative: str = "screen") -> dict:
    pos_before = _get_mouse_pos()
    if relative == "window":
        info = window_info()
        x += info["screen_origin"]["x"]
        y += info["screen_origin"]["y"]
    _set_mouse_pos(x, y)
    import time
    time.sleep(0.01)
    pos_after = _get_mouse_pos()
    return {"moved": (pos_before != pos_after), "x": pos_after[0], "y": pos_after[1]}


def mouse_click(
    x: int = None, y: int = None,
    button: str = "left", clicks: int = 1,
    relative: str = "screen"
) -> dict:
    import time
    if x is not None and y is not None:
        mouse_move(x, y, relative)
        time.sleep(0.02)
    flags_map = {
        "left": (_MOUSEEVENTF_LEFTDOWN, _MOUSEEVENTF_LEFTUP),
        "right": (_MOUSEEVENTF_RIGHTDOWN, _MOUSEEVENTF_RIGHTUP),
        "middle": (_MOUSEEVENTF_MIDDLEDOWN, _MOUSEEVENTF_MIDDLEUP),
    }
    if button not in flags_map:
        raise ValueError(f"Unknown button: {button}. Use left/right/middle.")
    down, up = flags_map[button]
    for _ in range(clicks):
        _mouse_event(down)
        time.sleep(0.01)
        _mouse_event(up)
        time.sleep(0.01)
    pos = _get_mouse_pos()
    return {"clicked": True, "button": button, "clicks": clicks, "x": pos[0], "y": pos[1]}


def mouse_scroll(amount: int) -> dict:
    _mouse_event(_MOUSEEVENTF_WHEEL, amount)
    return {"scrolled": True, "amount": amount}


def mouse_drag(
    x1: int, y1: int, x2: int, y2: int,
    button: str = "left", relative: str = "screen"
) -> dict:
    import time
    flags_map = {
        "left": (_MOUSEEVENTF_LEFTDOWN, _MOUSEEVENTF_LEFTUP),
        "right": (_MOUSEEVENTF_RIGHTDOWN, _MOUSEEVENTF_RIGHTUP),
        "middle": (_MOUSEEVENTF_MIDDLEDOWN, _MOUSEEVENTF_MIDDLEUP),
    }
    if button not in flags_map:
        raise ValueError(f"Unknown button: {button}")
    down, up = flags_map[button]

    mouse_move(x1, y1, relative)
    time.sleep(0.02)
    _mouse_event(down)
    time.sleep(0.02)
    mouse_move(x2, y2, relative)
    time.sleep(0.05)
    _mouse_event(up)
    time.sleep(0.02)
    pos = _get_mouse_pos()
    return {"dragged": (x1, y1, x2, y2), "button": button, "end_x": pos[0], "end_y": pos[1]}


def _key_event(vk: int, up: bool = False):
    import ctypes as ct
    KEYEVENTF_KEYUP = 0x0002
    ct.windll.user32.keybd_event(vk, 0, KEYEVENTF_KEYUP if up else 0, 0)


_VK_MAP = {
    "enter": 0x0D, "return": 0x0D,
    "tab": 0x09,
    "escape": 0x1B, "esc": 0x1B,
    "space": 0x20,
    "backspace": 0x08,
    "delete": 0x2E, "del": 0x2E,
    "insert": 0x2D, "ins": 0x2D,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21, "page_down": 0x22,
    "left": 0x25, "right": 0x27, "up": 0x26, "down": 0x28,
    "shift": 0x10, "ctrl": 0x11, "control": 0x11,
    "alt": 0x12, "menu": 0x12,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73,
    "f5": 0x74, "f6": 0x75, "f7": 0x76, "f8": 0x77,
    "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
}


def key_send(keys: str, modifiers: list = None) -> dict:
    import time
    if modifiers:
        for mod in modifiers:
            vk = _VK_MAP.get(mod.lower())
            if vk:
                _key_event(vk)
                time.sleep(0.02)

    sent = []
    for ch in keys:
        vk = _VK_MAP.get(ch.lower())
        if vk is None and len(ch) == 1:
            import ctypes as ct
            vk = ct.windll.user32.VkKeyScanW(ord(ch)) & 0xFF
        if vk:
            _key_event(vk)
            time.sleep(0.01)
            _key_event(vk, up=True)
            time.sleep(0.01)
            sent.append(ch)

    if modifiers:
        time.sleep(0.02)
        for mod in reversed(modifiers):
            vk = _VK_MAP.get(mod.lower())
            if vk:
                _key_event(vk, up=True)
                time.sleep(0.02)

    return {"sent": "".join(sent), "modifiers": modifiers or []}


# ── 快捷键封装 ────────────────────────────────────────────────────────────────

# SP 常用操作 → (修饰键列表, 主键)
_SHORTCUT_MAP = {
    # 文件操作
    "save":              (["ctrl"],          "s"),
    "save_as":           (["ctrl", "shift"], "s"),
    "new_project":       (["ctrl"],          "n"),
    "open_project":      (["ctrl"],          "o"),
    "close_project":     (["ctrl"],          "w"),
    "import_image":      (["ctrl"],          "i"),
    "export_textures":   (["ctrl", "shift"], "e"),
    # 编辑操作
    "undo":              (["ctrl"],          "z"),
    "redo":              (["ctrl"],          "y"),
    "select_all":        (["ctrl"],          "a"),
    "deselect":          (["ctrl", "shift"], "a"),
    "copy":              (["ctrl"],          "c"),
    "paste":             (["ctrl"],          "v"),
    "cut":               (["ctrl"],          "x"),
    "duplicate":         (["ctrl"],          "d"),
    "delete_layer":      ([],                "delete"),
    # 图层操作
    "new_fill_layer":    (["ctrl", "shift"], "f"),
    "new_paint_layer":   (["ctrl", "shift"], "p"),
    "new_group":         (["ctrl", "shift"], "g"),
    "merge_down":        (["ctrl"],          "e"),
    # 视口操作
    "frame_all":         (["alt"],           "f"),
    "toggle_wireframe":  ([],                "f4"),
    "toggle_unity":      ([],                "f5"),
    # 模式切换
    "paint_mode":        ([],                "1"),
    "erase_mode":        ([],                "2"),
    "project_mode":      ([],                "3"),
    # 显示
    "toggle_ui":         ([],                "space"),
    "toggle_mask_view":  (["alt"],           "m"),
    # Iray
    "toggle_iray":       ([],                "f10"),
}


def sp_shortcut(action: str) -> dict:
    """
    执行预定义的 SP 快捷键操作。
    """
    key = action.lower().strip()
    if key not in _SHORTCUT_MAP:
        valid = sorted(_SHORTCUT_MAP.keys())
        raise ValueError(
            f"Unknown shortcut action: '{action}'. "
            f"Valid actions: {valid}"
        )
    modifiers, keys = _SHORTCUT_MAP[key]
    return key_send(keys, modifiers)


# ── 内部工具 ──────────────────────────────────────────────────────────────────

def list_export_presets() -> list:
    """列出所有可用的导出预设名称。"""
    import substance_painter.resource as r
    presets = []
    for res in r.search(""):
        try:
            if res.type().name == "EXPORT_PRESET":
                presets.append(res.gui_name())
        except (ValueError, AttributeError):
            continue
    # Fallback: try JS API if resource search returns nothing
    if not presets:
        try:
            import substance_painter.js as js
            result = js.evaluate(
                "alg.mapexport.presets().map(function(p){return p.name;})"
            )
            if isinstance(result, list):
                presets = result
        except Exception:
            pass
    return sorted(set(presets))


def get_iray_params() -> dict:
    """读取当前 Iray 渲染参数设置。"""
    import substance_painter.ui
    from PySide2.QtWidgets import QDockWidget, QSpinBox

    win = substance_painter.ui.get_main_window()
    panel = None
    for dock in win.findChildren(QDockWidget):
        if dock.objectName() == "irayParametersView":
            panel = dock.widget()
            break

    if panel is None:
        return {"error": "Iray panel not found"}

    params = {}
    for sb in panel.findChildren(QSpinBox):
        name = sb.objectName()
        if name:
            params[name] = sb.value()

    return {"params": params}


def add_mask(layer_id: str) -> dict:
    """为图层添加一个空白遮罩（非 Smart Mask）。"""
    with _auto_batch("Add mask"):
        import substance_painter.layerstack as ls
        node = _find_layer(layer_id)
        mask = node.add_mask(ls.MaskBackground.White)
        return {"ok": True, "layer_id": layer_id}


def remove_mask(layer_id: str) -> dict:
    """移除图层的遮罩（如果有的话）。"""
    with _auto_batch("Remove mask"):
        import substance_painter.layerstack as ls
        node = _find_layer(layer_id)
        node.remove_mask()
        return {"ok": True, "layer_id": layer_id}


def find_layer_by_name(name: str) -> dict:
    """在所有纹理集中按名称搜索图层，返回匹配的图层信息列表。"""
    import substance_painter.textureset as ts
    import substance_painter.layerstack as ls

    results = []
    for t in ts.all_texture_sets():
        stack = t.get_stack()
        root_nodes = ls.get_root_layer_nodes(stack)

        def _search(nodes, depth=0):
            for n in nodes:
                if n.get_name().lower() == name.lower():
                    results.append({
                        "id": str(n.uid()),
                        "name": n.get_name(),
                        "type": type(n).__name__,
                        "texture_set": t.name(),
                        "depth": depth,
                    })
                if type(n).__name__ == "GroupLayerNode":
                    _search(n.sub_layers(), depth + 1)

        _search(root_nodes)
    return {"matches": results}


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
        # Fallback: try node-by-uid lookup (for effect nodes, etc.)
        try:
            found = ls.get_node_by_uid(int(uid))
        except Exception:
            pass
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
    from PySide2.QtWidgets import QDockWidget, QLabel

    win = substance_painter.ui.get_main_window()
    panel = None
    for dock in win.findChildren(QDockWidget):
        if dock.objectName() == "irayParametersView":
            panel = dock.widget()
            break

    if panel is None:
        return {"active": False, "error": "Iray panel not found"}

    iterations_label = panel.findChild(QLabel, "iterationsLabel")
    time_label = panel.findChild(QLabel, "timeLabel")

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


# ── Phase: 程序化源参数控制 ─────────────────────────────────────────────────


def _resolve_channel(channel: str):
    """将字符串 channel 名称转换为 ChannelType 枚举值。"""
    import substance_painter.layerstack as ls
    mapping = {
        "BaseColor":  ls.ChannelType.BaseColor,
        "Roughness":  ls.ChannelType.Roughness,
        "Metallic":   ls.ChannelType.Metallic,
        "Height":     ls.ChannelType.Height,
        "Normal":     ls.ChannelType.Normal,
        "Emissive":   ls.ChannelType.Emissive,
        "Specular":   ls.ChannelType.Specular,
        "Opacity":    ls.ChannelType.Opacity,
        "AmbientOcclusion": ls.ChannelType.AmbientOcclusion,
    }
    if hasattr(ls.ChannelType, "Scattering"):
        mapping["Scattering"] = ls.ChannelType.Scattering
    if hasattr(ls.ChannelType, "Translucency"):
        mapping["Translucency"] = ls.ChannelType.Translucency

    if channel in mapping:
        return mapping[channel]
    raise ValueError(f"Unknown channel: {channel!r}. Valid: {sorted(mapping.keys())}")


def _serialize_property_value(value) -> object:
    """将 PropertyValue 对象序列化为 JSON 兼容的基本类型。"""
    import substance_painter.colormanagement as cm
    try:
        raw = value.value()
    except Exception:
        return str(value)

    # Color 对象
    if isinstance(raw, cm.Color):
        return {"r": raw.value_raw[0], "g": raw.value_raw[1], "b": raw.value_raw[2]}
    # 枚举
    if hasattr(raw, "name"):
        return raw.name
    # 基本类型
    if isinstance(raw, (int, float, bool, str)):
        return raw
    # Tuple/list
    if isinstance(raw, (tuple, list)):
        return list(raw)
    return str(raw)


def _serialize_source(source) -> dict:
    """将 Source 对象序列化为 dict。"""
    import substance_painter.source as src_mod
    import substance_painter.colormanagement as cm
    import substance_painter.resource as r

    stype = type(source).__name__
    info = {"type": stype}

    # 公共属性
    if isinstance(source, src_mod.SourceUniformColor):
        try:
            c = source.get_color()
            info["color"] = {"r": c.value_raw[0], "g": c.value_raw[1], "b": c.value_raw[2]}
        except Exception:
            pass
    elif isinstance(source, src_mod.SourceSubstance):
        rid = source.resource_id
        if rid:
            info["resource"] = {"context": rid.context, "name": rid.name, "url": rid.url()}
        try:
            info["image_inputs"] = list(source.image_inputs)
        except Exception:
            pass
        try:
            info["image_outputs"] = list(source.image_outputs)
        except Exception:
            pass
        try:
            info["active_output"] = source.active_output
        except Exception:
            pass
        try:
            info["mask_output"] = source.mask_output
        except Exception:
            pass
        try:
            info["presets"] = source.get_preset_list()
        except Exception:
            info["presets"] = []
        try:
            params = source.get_parameters()
            info["parameters"] = {k: _serialize_property_value(v) for k, v in params.items()}
        except Exception:
            info["parameters"] = {}
        try:
            props = source.get_properties()
            info["parameter_types"] = {}
            for k, prop in props.items():
                try:
                    info["parameter_types"][k] = prop.type().name
                except Exception:
                    pass
        except Exception:
            pass
    elif isinstance(source, src_mod.SourceBitmap):
        rid = source.resource_id
        if rid:
            info["resource"] = {"context": rid.context, "name": rid.name, "url": rid.url()}
        try:
            info["color_space"] = source.get_color_space().name
        except Exception:
            pass
    elif isinstance(source, src_mod.SourceVectorial):
        rid = source.resource_id
        if rid:
            info["resource"] = {"context": rid.context, "name": rid.name, "url": rid.url()}
        try:
            params = source.get_parameters()
            info["artboard_id"] = params.artboard_id
            info["scope"] = params.scope
        except Exception:
            pass
    elif isinstance(source, src_mod.SourceReference):
        try:
            if source.anchor:
                info["anchor_id"] = str(source.anchor.uid())
        except Exception:
            pass
        try:
            info["alpha_matte"] = source.alpha_matte.name
        except Exception:
            pass
    elif isinstance(source, src_mod.SourceFont):
        rid = source.resource_id
        if rid:
            info["resource"] = {"context": rid.context, "name": rid.name, "url": rid.url()}
        try:
            params = source.get_parameters()
            info["text"] = params.text
            info["font_size"] = params.size
        except Exception:
            pass

    return info


def _get_substance_source(layer_id: str, channel: str = None):
    """Helper: 从图层获取 SourceSubstance 对象。

    如果 source 不是 Substance 类型则抛出 ValueError。
    """
    import substance_painter.source as src_mod
    import substance_painter.layerstack as ls

    node = _find_layer(layer_id)
    node_type = type(node).__name__

    if node_type not in ("FillLayerNode", "FillEffectNode"):
        raise ValueError(
            f"Layer {layer_id!r} (type={node_type}) does not support sources. "
            f"Only FillLayerNode / FillEffectNode are supported."
        )

    mode = node.source_mode

    if mode is not None and mode.name == "Material":
        s = node.get_material_source()
    elif channel:
        ch = _resolve_channel(channel)
        s = node.get_source(ch)
    else:
        # 自动查找 — 优先 BaseColor channel
        try:
            ch = _resolve_channel("BaseColor")
            s = node.get_source(ch)
        except Exception:
            s = None
        # 如果 BaseColor 没有，尝试 material source
        if s is None and mode is not None and mode.name == "Material":
            try:
                s = node.get_material_source()
            except Exception:
                pass

    if s is None:
        raise ValueError(
            f"Layer {layer_id!r} has no source assigned. "
            f"Apply a material or set a source first."
        )

    if not isinstance(s, src_mod.SourceSubstance):
        raise ValueError(
            f"Layer {layer_id!r} source is {type(s).__name__}, not a procedural "
            f"(Substance) source. Only procedural sources have parameters."
        )

    return s


# ── 公共 handler 函数 ──


def get_source_info(layer_id: str, channel: str = None) -> dict:
    """获取填充图层/效果的源信息。"""
    import substance_painter.source as src_mod
    import substance_painter.layerstack as ls

    node = _find_layer(layer_id)
    node_type = type(node).__name__

    if node_type not in ("FillLayerNode", "FillEffectNode",
                         "GeneratorEffectNode", "FilterEffectNode"):
        raise ValueError(
            f"Layer {layer_id!r} (type={node_type}) does not support sources."
        )

    mode = node.source_mode if hasattr(node, "source_mode") else None
    result = {
        "layer_id": layer_id,
        "node_type": node_type,
        "source_mode": mode.name if mode else "none",
    }

    if mode is not None and mode.name == "Material":
        try:
            ms = node.get_material_source()
            if ms is not None:
                result["material_source"] = _serialize_source(ms)
        except Exception:
            result["material_source"] = None
    else:
        if channel:
            ch = _resolve_channel(channel)
            try:
                s = node.get_source(ch)
                if s is not None:
                    result["source"] = _serialize_source(s)
            except Exception as e:
                result["source_error"] = str(e)
        else:
            sources = {}
            for ch_name in ("BaseColor", "Roughness", "Metallic", "Height", "Normal"):
                try:
                    ch = _resolve_channel(ch_name)
                    s = node.get_source(ch)
                    if s is not None:
                        sources[ch_name] = _serialize_source(s)
                except Exception:
                    pass
            if sources:
                result["sources"] = sources

    return result


def get_substance_parameters(layer_id: str, channel: str = None) -> dict:
    """读取程序化源（Substance）的当前参数值。"""
    source = _get_substance_source(layer_id, channel)

    params = source.get_parameters()
    props = source.get_properties()

    result = {}
    for name, value in params.items():
        entry = {"value": _serialize_property_value(value)}
        prop = props.get(name)
        if prop:
            try:
                entry["type"] = prop.type().name
            except Exception:
                pass
            try:
                entry["description"] = str(prop.description())
            except Exception:
                pass
        result[name] = entry

    return {"layer_id": layer_id, "parameters": result}


def set_substance_parameters(layer_id: str, params: dict,
                             channel: str = None) -> dict:
    """修改程序化源参数。params 为 {name: value, ...}。"""
    import substance_painter.properties as sprop

    source = _get_substance_source(layer_id, channel)

    # 将原始值包装为 PropertyValue
    wrapped = {}
    for k, v in params.items():
        try:
            wrapped[k] = sprop.PropertyValue(v)
        except Exception as e:
            raise ValueError(
                f"Failed to wrap parameter {k!r}={v!r}: {e}"
            ) from e

    with _auto_batch("Set substance parameters"):
        source.set_parameters(wrapped)

    _log_info(
        f"set_substance_parameters layer={layer_id!r} "
        f"keys={list(params.keys())}"
    )
    return {"ok": True, "layer_id": layer_id, "updated": list(params.keys())}


def get_substance_presets(layer_id: str, channel: str = None) -> dict:
    """列出程序化源的所有可用预设。"""
    source = _get_substance_source(layer_id, channel)
    return {"layer_id": layer_id, "presets": source.get_preset_list()}


def apply_substance_preset(layer_id: str, preset_name: str,
                           channel: str = None) -> dict:
    """为程序化源应用预设。"""
    source = _get_substance_source(layer_id, channel)

    presets = source.get_preset_list()
    if preset_name not in presets:
        raise ValueError(
            f"Preset {preset_name!r} not found. "
            f"Available: {presets[:20]}" + ("..." if len(presets) > 20 else "")
        )

    with _auto_batch(f"Apply preset {preset_name}"):
        source.apply_preset(preset_name)

    _log_info(
        f"apply_substance_preset layer={layer_id!r} preset={preset_name!r}"
    )
    return {"ok": True, "layer_id": layer_id, "preset": preset_name}


def get_source_outputs(layer_id: str, channel: str = None) -> dict:
    """获取程序化源的输出映射信息。"""
    import substance_painter.source as src_mod

    source = _get_substance_source(layer_id, channel)

    result = {
        "layer_id": layer_id,
        "image_outputs": [],
        "active_output": None,
        "mask_output": None,
        "output_mapping": {},
    }

    try:
        result["image_outputs"] = list(source.image_outputs)
    except Exception:
        pass
    try:
        result["active_output"] = source.active_output
    except Exception:
        pass
    try:
        result["mask_output"] = source.mask_output
    except Exception:
        pass
    try:
        om = source.output_mapping
        for ch in om:
            try:
                val = om[ch]
                ch_name = ch.name if hasattr(ch, "name") else str(ch)
                val_name = val.name if hasattr(val, "name") else str(val)
                result["output_mapping"][ch_name] = val_name
            except Exception:
                pass
    except Exception:
        pass

    return result


def set_source_output(layer_id: str, output_identifier: str,
                      channel: str = None) -> dict:
    """设置程序化源的活动输出（在单输出上下文中）。"""
    source = _get_substance_source(layer_id, channel)

    if output_identifier not in source.image_outputs:
        raise ValueError(
            f"Output {output_identifier!r} not found. "
            f"Available: {list(source.image_outputs)}"
        )

    with _auto_batch(f"Set output to {output_identifier}"):
        source.active_output = output_identifier

    _log_info(
        f"set_source_output layer={layer_id!r} output={output_identifier!r}"
    )
    return {"ok": True, "layer_id": layer_id, "active_output": output_identifier}


# ── Phase: 相机与显示增强 ────────────────────────────────────────────────────


def get_camera() -> dict:
    """读取主相机的完整状态。"""
    import substance_painter.display as display

    cam = display.Camera.get_default_camera()
    return {
        "position": list(cam.position),
        "rotation": list(cam.rotation),
        "field_of_view": cam.field_of_view,
        "focal_length": cam.focal_length,
        "focus_distance": cam.focus_distance,
        "aperture": cam.aperture,
        "orthographic_height": cam.orthographic_height,
        "projection_type": cam.projection_type.name,
    }


def get_tone_mapping() -> dict:
    """获取当前色调映射函数。"""
    import substance_painter.display as display

    try:
        tm = display.get_tone_mapping()
        return {"tone_mapping": tm.name}
    except Exception as e:
        return {"tone_mapping": None, "error": str(e)}


def set_tone_mapping(function: str) -> dict:
    """设置色调映射函数（"Linear" 或 "ACES"）。"""
    import substance_painter.display as display

    valid = {x.name: x for x in display.ToneMappingFunction}
    if function not in valid:
        raise ValueError(
            f"Unknown tone mapping: {function!r}. Valid: {sorted(valid.keys())}"
        )

    display.set_tone_mapping(valid[function])
    _log_info(f"set_tone_mapping: {function!r}")
    return {"ok": True, "tone_mapping": function}


def get_color_lut() -> dict:
    """获取当前色彩 LUT 配置文件。"""
    import substance_painter.display as display

    rid = display.get_color_lut_resource()
    if rid is None:
        return {"color_lut": None}
    return {"color_lut": {"context": rid.context, "name": rid.name, "url": rid.url()}}


def set_color_lut(resource_name: str) -> dict:
    """按名称设置色彩 LUT 配置文件。"""
    import substance_painter.display as display
    import substance_painter.resource as r

    resources = r.search(resource_name)
    for res in resources:
        if resource_name.lower() in res.gui_name().lower():
            display.set_color_lut_resource(res.identifier())
            _log_info(f"set_color_lut: {res.gui_name()!r}")
            return {"ok": True, "color_lut": res.gui_name()}

    raise ValueError(f"Color LUT not found: {resource_name!r}")


def get_scene_bounding_box() -> dict:
    """获取场景包围盒（中心、尺寸、半径）。"""
    import substance_painter.project as project

    bb = project.get_scene_bounding_box()
    return {
        "dimensions": list(bb.dimensions),
        "center": list(bb.center),
        "radius": bb.radius,
    }


# ── Phase 15: 效果节点 ──────────────────────────────────────────────────────────

def _get_layer_node(layer_id: str, node_stack=None):
    """Helper: 获取图层节点并返回插入位置所需信息。"""
    node = _find_layer(layer_id)
    node_type = type(node).__name__
    if node_type not in ("FillLayerNode", "GroupLayerNode", "PaintLayerNode",
                         "FillEffectNode", "GroupLayerNode"):
        raise ValueError(
            f"Layer {layer_id!r} (type={node_type}) does not support effects."
        )
    return node


def _insert_effect(layer_id: str, effect_type: str, **kwargs):
    """Helper: 在图层内部插入效果节点。"""
    import substance_painter.layerstack as ls

    node = _get_layer_node(layer_id)
    # 在图层内容栈内部插入
    pos = ls.InsertPosition.inside_node(node, ls.NodeStack.Content)

    with _auto_batch(f"Add {effect_type}"):
        if effect_type == "filter":
            rid = kwargs.get("resource_id")
            node = ls.insert_filter_effect(pos, rid)
        elif effect_type == "generator":
            rid = kwargs.get("resource_id")
            node = ls.insert_generator_effect(pos, rid)
        elif effect_type == "levels":
            node = ls.insert_levels_effect(pos)
        elif effect_type == "compare_mask":
            pos = ls.InsertPosition.inside_node(node, ls.NodeStack.Mask)
            node = ls.insert_compare_mask_effect(pos)
        elif effect_type == "color_selection":
            pos = ls.InsertPosition.inside_node(node, ls.NodeStack.Mask)
            node = ls.insert_color_selection_effect(pos)
        elif effect_type == "anchor_point":
            pos = ls.InsertPosition.inside_node(node, ls.NodeStack.Content)
            node = ls.insert_anchor_point_effect(pos, kwargs.get("name", "Anchor"))
        else:
            raise ValueError(f"Unknown effect type: {effect_type!r}")

    _log_info(f"add_{effect_type}_effect layer={layer_id!r}")
    return {"ok": True, "layer_id": layer_id, "effect_id": str(node.uid()),
            "effect_type": effect_type}


def add_filter_effect(layer_id: str, filter_name: str = None) -> dict:
    """在图层上添加 Filter 效果。"""
    import substance_painter.resource as r
    rid = None
    if filter_name:
        resources = r.search(filter_name)
        for res in resources:
            if filter_name.lower() in res.gui_name().lower():
                rid = res.identifier()
                break
        if rid is None:
            raise ValueError(f"Filter resource not found: {filter_name!r}")
    return _insert_effect(layer_id, "filter", resource_id=rid)


def add_generator_effect(layer_id: str, generator_name: str = None) -> dict:
    """在图层上添加 Generator 效果。"""
    import substance_painter.resource as r
    rid = None
    if generator_name:
        resources = r.search(generator_name)
        for res in resources:
            if generator_name.lower() in res.gui_name().lower():
                rid = res.identifier()
                break
        if rid is None:
            raise ValueError(f"Generator resource not found: {generator_name!r}")
    return _insert_effect(layer_id, "generator", resource_id=rid)


def add_levels_effect(layer_id: str) -> dict:
    """在图层上添加 Levels 效果。"""
    return _insert_effect(layer_id, "levels")


def add_compare_mask_effect(layer_id: str) -> dict:
    """在图层 Mask 栈中添加 Compare Mask 效果。"""
    return _insert_effect(layer_id, "compare_mask")


def add_color_selection_effect(layer_id: str) -> dict:
    """在图层 Mask 栈中添加 Color Selection 效果。"""
    return _insert_effect(layer_id, "color_selection")


def add_anchor_point_effect(layer_id: str, anchor_name: str = "Anchor") -> dict:
    """在图层上添加 Anchor Point 效果。"""
    return _insert_effect(layer_id, "anchor_point", name=anchor_name)


def get_effect_parameters(layer_id: str) -> dict:
    """读取效果节点的参数。

    支持: LevelsEffect, CompareMaskEffect, ColorSelectionEffect,
          FilterEffect, GeneratorEffect
    """
    import substance_painter.layerstack as ls
    import substance_painter.source as src_mod

    node = _find_layer(layer_id)
    node_type = type(node).__name__

    result = {"layer_id": layer_id, "node_type": node_type}

    if node_type == "LevelsEffectNode":
        params = node.get_parameters()
        ch = node.affected_channel
        result["parameters"] = {
            "affected_channel": ch.name if hasattr(ch, "name") else str(ch),
            "levels": _serialize_levels_params(params),
        }
    elif node_type == "CompareMaskEffectNode":
        params = node.get_parameters()
        result["parameters"] = {
            "channel": params.channel.name if hasattr(params.channel, "name") else str(params.channel),
            "left_operand": params.left_operand.name,
            "right_operand": params.right_operand.name,
            "operation": params.operation.name,
            "constant": params.constant,
            "tolerance": params.tolerance,
            "hardness": params.hardness,
        }
    elif node_type == "ColorSelectionEffectNode":
        params = node.get_parameters()
        result["parameters"] = {
            "output_value": params.output_value,
            "hardness": params.hardness,
            "tolerance": params.tolerance,
            "background_color": params.background_color.name,
            "colors": [[c.value_raw[0], c.value_raw[1], c.value_raw[2]]
                       for c in params.colors] if params.colors else [],
        }
        if params.id_mask:
            result["parameters"]["id_mask"] = params.id_mask.url()
    elif node_type in ("FilterEffectNode", "GeneratorEffectNode"):
        try:
            source = node.get_source()
            if source is not None:
                result["source"] = _serialize_source(source)
        except Exception as e:
            result["source_error"] = str(e)
    else:
        raise ValueError(
            f"Layer {layer_id!r} (type={node_type}) is not a recognized effect node."
        )

    return result


def _serialize_levels_params(params) -> dict:
    """将 LevelsParams 序列化为 dict。"""
    if hasattr(params, "mono"):
        # LevelsParamsMono
        m = params.mono
        return {"mode": "mono", "in_low": m.in_low, "in_mid": m.in_mid,
                "in_high": m.in_high, "out_low": m.out_low, "out_high": m.out_high,
                "gamma": m.gamma, "clamp": m.clamp}
    elif hasattr(params, "red"):
        return {"mode": "rgb",
                "red": {"in_low": params.red.in_low, "in_mid": params.red.in_mid,
                        "in_high": params.red.in_high, "out_low": params.red.out_low,
                        "out_high": params.red.out_high, "gamma": params.red.gamma,
                        "clamp": params.red.clamp},
                "green": {"in_low": params.green.in_low, "in_mid": params.green.in_mid,
                          "in_high": params.green.in_high, "out_low": params.green.out_low,
                          "out_high": params.green.out_high, "gamma": params.green.gamma,
                          "clamp": params.green.clamp},
                "blue": {"in_low": params.blue.in_low, "in_mid": params.blue.in_mid,
                         "in_high": params.blue.in_high, "out_low": params.blue.out_low,
                         "out_high": params.blue.out_high, "gamma": params.blue.gamma,
                         "clamp": params.blue.clamp}}
    return {"mode": "unknown"}


def get_selected_nodes(texture_set_name: str = None) -> dict:
    """获取当前选中的节点列表。"""
    import substance_painter.textureset as ts_mod
    import substance_painter.layerstack as ls

    if texture_set_name:
        texture_set = ts_mod.TextureSet.from_name(texture_set_name)
        stack = texture_set.get_stack()
    else:
        stack = ts_mod.get_active_stack()

    nodes = ls.get_selected_nodes(stack)
    result = []
    for node in nodes:
        info = {"id": str(node.uid()), "name": node.get_name(),
                "type": type(node).__name__}
        result.append(info)

    return {"nodes": result, "count": len(result)}


def set_selected_nodes(node_ids: list) -> dict:
    """设置选中节点。"""
    import substance_painter.layerstack as ls

    nodes = [_find_layer(lid) for lid in node_ids]
    ls.set_selected_nodes(nodes)

    return {"ok": True, "selected": [str(n.uid()) for n in nodes]}


# ── Phase 16: 烘焙 API ──────────────────────────────────────────────────────────


def get_baking_parameters(texture_set_name: str) -> dict:
    """读取纹理集的烘焙参数。"""
    import substance_painter.baking as baking

    bp = baking.BakingParameters.from_texture_set_name(texture_set_name)
    common = bp.common()
    result = {
        "texture_set": texture_set_name,
        "common": {},
        "bakers": {},
        "curvature_method": bp.get_curvature_method().name,
        "textureset_enabled": bp.is_textureset_enabled(),
    }

    # 序列化 common 参数
    for name, prop in common.items():
        try:
            pv = prop.value()
            result["common"][name] = _serialize_property_value(pv)
        except Exception:
            result["common"][name] = str(prop)

    # 序列化各 baker 参数
    import substance_painter.textureset as ts_mod
    for map_usage in ts_mod.MeshMapUsage:
        try:
            baker_params = bp.baker(map_usage)
            if baker_params:
                result["bakers"][map_usage.name] = {}
                for name, prop in baker_params.items():
                    try:
                        pv = prop.value()
                        result["bakers"][map_usage.name][name] = _serialize_property_value(pv)
                    except Exception:
                        result["bakers"][map_usage.name][name] = str(prop)
        except Exception:
            pass

    # 启用的 bakers
    try:
        enabled = bp.get_enabled_bakers()
        result["enabled_bakers"] = [e.name for e in enabled]
    except Exception:
        result["enabled_bakers"] = []

    # 启用的 UV tiles
    try:
        tiles = bp.get_enabled_uv_tiles()
        result["enabled_uv_tiles"] = [{"u": t.u, "v": t.v} for t in tiles]
    except Exception:
        pass

    return result


def set_baking_parameters(texture_set_name: str,
                          common_params: dict = None,
                          baker_params: dict = None) -> dict:
    """设置烘焙参数。

    common_params: {"OutputSize": [4096, 4096], "HipolyMesh": "file:///..."}
    baker_params: {"AO": {"Distribution": "Cosine"}, "Curvature": {...}}
    """
    import substance_painter.baking as baking
    import substance_painter.textureset as ts_mod
    import substance_painter.properties as sprop

    bp = baking.BakingParameters.from_texture_set_name(texture_set_name)
    updates = {}

    if common_params:
        common = bp.common()
        for name, value in common_params.items():
            for prop_name, prop in common.items():
                if prop_name.lower() == name.lower():
                    updates[prop] = sprop.PropertyValue(value)
                    break

    if baker_params:
        for usage_name, params_dict in baker_params.items():
            try:
                usage = getattr(ts_mod.MeshMapUsage, usage_name)
                baker = bp.baker(usage)
                for name, value in params_dict.items():
                    for prop_name, prop in baker.items():
                        if prop_name.lower() == name.lower():
                            updates[prop] = sprop.PropertyValue(value)
                            break
            except Exception as e:
                raise ValueError(
                    f"Invalid baker usage {usage_name!r}: {e}"
                ) from e

    if updates:
        with _auto_batch("Set baking parameters"):
            baking.BakingParameters.set(updates)

    _log_info(
        f"set_baking_parameters ts={texture_set_name!r} "
        f"keys={list(updates.keys())}"
    )
    return {"ok": True, "texture_set": texture_set_name,
            "updated_count": len(updates)}


def bake_texture_set(texture_set_name: str) -> dict:
    """异步启动纹理集烘焙。"""
    import substance_painter.baking as baking
    import substance_painter.textureset as ts_mod

    texture_set = ts_mod.TextureSet.from_name(texture_set_name)
    stop_source = baking.bake_async(texture_set)

    _log_info(f"bake_texture_set: {texture_set_name!r}")
    return {"ok": True, "texture_set": texture_set_name,
            "message": "Baking started asynchronously. "
                       "Monitor progress via BakingProcessEnded event."}


def get_baking_state(texture_set_name: str) -> dict:
    """获取烘焙状态（启用/禁用状态，链接信息）。"""
    import substance_painter.baking as baking
    import substance_painter.textureset as ts_mod

    bp = baking.BakingParameters.from_texture_set_name(texture_set_name)
    ts = ts_mod.TextureSet.from_name(texture_set_name)

    result = {
        "texture_set": texture_set_name,
        "textureset_enabled": bp.is_textureset_enabled(),
        "curvature_method": bp.get_curvature_method().name,
        "enabled_bakers": [e.name for e in bp.get_enabled_bakers()],
    }

    # 获取链接信息
    for map_usage in ts_mod.MeshMapUsage:
        try:
            linked = baking.get_linked_texture_sets(ts, map_usage)
            if len(linked) > 1:
                result.setdefault("linked_groups", {})
                result["linked_groups"][map_usage.name] = [t.name() for t in linked]
        except Exception:
            pass

    try:
        tiles = bp.get_enabled_uv_tiles()
        result["enabled_uv_tiles"] = [{"u": t.u, "v": t.v} for t in tiles]
    except Exception:
        pass

    return result


def set_baking_state(texture_set_name: str,
                     enabled: bool = None,
                     curvature_method: str = None,
                     enabled_bakers: list = None,
                     enabled_uv_tiles: list = None) -> dict:
    """设置烘焙状态（启用/禁用纹理集/bakers/UV tiles，曲率方法）。"""
    import substance_painter.baking as baking
    import substance_painter.textureset as ts_mod

    bp = baking.BakingParameters.from_texture_set_name(texture_set_name)
    ts = ts_mod.TextureSet.from_name(texture_set_name)
    changed = []

    if enabled is not None:
        bp.set_textureset_enabled(enabled)
        changed.append(f"textureset_enabled={enabled}")

    if curvature_method:
        valid_methods = {"FromMesh": baking.CurvatureMethod.FromMesh,
                         "FromNormalMap": baking.CurvatureMethod.FromNormalMap}
        if curvature_method not in valid_methods:
            raise ValueError(
                f"Unknown curvature method: {curvature_method!r}. "
                f"Valid: {list(valid_methods.keys())}"
            )
        bp.set_curvature_method(valid_methods[curvature_method])
        changed.append(f"curvature_method={curvature_method}")

    if enabled_bakers is not None:
        usages = [getattr(ts_mod.MeshMapUsage, u) for u in enabled_bakers]
        bp.set_enabled_bakers(usages)
        changed.append(f"enabled_bakers={enabled_bakers}")

    if enabled_uv_tiles is not None:
        tiles = [ts.uv_tile(t["u"], t["v"]) for t in enabled_uv_tiles]
        bp.set_enabled_uv_tiles(tiles)
        changed.append(f"enabled_uv_tiles={enabled_uv_tiles}")

    _log_info(f"set_baking_state ts={texture_set_name!r} {', '.join(changed)}")
    return {"ok": True, "texture_set": texture_set_name, "changed": changed}


# ── Phase 17: 项目生命周期 ──────────────────────────────────────────────────────


def create_project(mesh_file_path: str,
                   mesh_map_file_paths: list = None,
                   normal_map_format: str = "OpenGL",
                   tangent_space_mode: str = "PerFragment",
                   project_workflow: str = "Default",
                   import_cameras: bool = False,
                   default_texture_resolution: int = 2048,
                   mesh_unit_scale: float = None) -> dict:
    """创建新项目。

    仅在不处于 edition state 时可用（即需要先关闭当前项目）。
    """
    import substance_painter.project as project

    if project.is_open():
        raise RuntimeError(
            "A project is already open. Call close_project() first before creating a new one."
        )

    nmf_map = {"OpenGL": project.NormalMapFormat.OpenGL,
               "DirectX": project.NormalMapFormat.DirectX}
    ts_map = {"PerVertex": project.TangentSpace.PerVertex,
              "PerFragment": project.TangentSpace.PerFragment}
    pw_map = {"Default": project.ProjectWorkflow.Default,
              "TextureSetPerUVTile": project.ProjectWorkflow.TextureSetPerUVTile,
              "UVTile": project.ProjectWorkflow.UVTile}

    if normal_map_format not in nmf_map:
        raise ValueError(
            f"Unknown normal_map_format: {normal_map_format!r}. "
            f"Valid: {list(nmf_map.keys())}"
        )
    if tangent_space_mode not in ts_map:
        raise ValueError(
            f"Unknown tangent_space_mode: {tangent_space_mode!r}. "
            f"Valid: {list(ts_map.keys())}"
        )
    if project_workflow not in pw_map:
        raise ValueError(
            f"Unknown project_workflow: {project_workflow!r}. "
            f"Valid: {list(pw_map.keys())}"
        )

    settings = project.Settings(
        normal_map_format=nmf_map[normal_map_format],
        tangent_space_mode=ts_map[tangent_space_mode],
        project_workflow=pw_map[project_workflow],
        import_cameras=import_cameras,
        default_texture_resolution=default_texture_resolution,
        mesh_unit_scale=mesh_unit_scale,
    )

    project.create(
        mesh_file_path=mesh_file_path,
        mesh_map_file_paths=mesh_map_file_paths or [],
        settings=settings,
    )

    _log_info(f"create_project: {mesh_file_path!r}")
    return {"ok": True, "mesh_file_path": mesh_file_path,
            "name": project.name()}


def open_project(file_path: str) -> dict:
    """打开已有 .spp 项目。"""
    import substance_painter.project as project

    project.open(file_path)

    _log_info(f"open_project: {file_path!r}")
    return {"ok": True, "file_path": file_path, "name": project.name()}


def close_project() -> dict:
    """关闭当前项目（不保存）。"""
    import substance_painter.project as project

    if not project.is_open():
        return {"ok": True, "message": "No project was open."}

    project.close()
    _log_info("close_project")
    return {"ok": True, "message": "Project closed."}


def reload_mesh(mesh_file_path: str,
                import_cameras: bool = True,
                preserve_strokes: bool = True) -> dict:
    """异步重载网格。"""
    import substance_painter.project as project

    settings = project.MeshReloadingSettings(
        import_cameras=import_cameras,
        preserve_strokes=preserve_strokes,
    )

    # 使用同步 wrapper: 通过事件循环等待完成
    project.reload_mesh(
        mesh_file_path=mesh_file_path,
        settings=settings,
        loading_status_cb=lambda status: None,  # 简化: 不等待回调
    )

    _log_info(f"reload_mesh: {mesh_file_path!r}")
    return {"ok": True, "mesh_file_path": mesh_file_path,
            "message": "Mesh reload initiated. Check ProjectEditionEntered event for completion."}


def get_project_metadata(context: str, key: str) -> dict:
    """读取项目元数据。"""
    import substance_painter.project as project

    metadata = project.Metadata(context)
    value = metadata.get(key)

    return {"context": context, "key": key, "value": value}


def set_project_metadata(context: str, key: str, value) -> dict:
    """写入项目元数据。"""
    import substance_painter.project as project

    metadata = project.Metadata(context)
    metadata.set(key, value)

    _log_info(f"set_project_metadata: {context}/{key}")
    return {"ok": True, "context": context, "key": key}


def list_project_metadata(context: str) -> dict:
    """列出某 context 下所有元数据键。"""
    import substance_painter.project as project

    metadata = project.Metadata(context)
    keys = metadata.list()

    return {"context": context, "keys": keys}


def list_resources_by_usage(usage: str, search: str = "") -> dict:
    """按用途类型列出资源（FILTER, GENERATOR, SUBSTANCE, SMART_MATERIAL 等）。

    usage: 资源用途，如 "filter", "generator", "substance", "smart_material"
    """
    import substance_painter.resource as r

    usage_map = {
        "filter": r.Usage.FILTER,
        "generator": r.Usage.GENERATOR,
        "substance": r.Usage.SUBSTANCE,
        "smart_material": r.Usage.SMART_MATERIAL,
        "smart_mask": r.Usage.SMART_MASK,
        "texture": r.Usage.TEXTURE,
        "environment": r.Usage.ENVIRONMENT,
        "export_preset": r.Usage.EXPORT_PRESET,
    }

    usage_lower = usage.lower()
    if usage_lower not in usage_map:
        raise ValueError(
            f"Unknown usage: {usage!r}. Valid: {sorted(usage_map.keys())}"
        )

    target_usage = usage_map[usage_lower]
    all_resources = r.search(search) if search else r.search("")
    result = []
    for res in all_resources:
        try:
            if res.type() == target_usage:
                result.append(res.gui_name())
        except Exception:
            pass

    return {"usage": usage, "search": search, "resources": result,
            "count": len(result)}


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
    # Phase 14 — Computer Use
    "window_info":              window_info,
    "window_grab":              window_grab,
    "window_focus":             window_focus,
    "cu_unlock":                cu_unlock,
    "cu_banner_text":           cu_banner_text,
    "cu_warning":               cu_warning,
    "mouse_move":               mouse_move,
    "mouse_click":              mouse_click,
    "mouse_scroll":             mouse_scroll,
    "mouse_drag":               mouse_drag,
    "key_send":                 key_send,
    "sp_shortcut":              sp_shortcut,
    # new tools
    "list_export_presets":      list_export_presets,
    "get_iray_params":          get_iray_params,
    "add_mask":                 add_mask,
    "remove_mask":              remove_mask,
    "find_layer_by_name":       find_layer_by_name,
    # source control
    "get_source_info":          get_source_info,
    "get_substance_parameters": get_substance_parameters,
    "set_substance_parameters": set_substance_parameters,
    "get_substance_presets":    get_substance_presets,
    "apply_substance_preset":   apply_substance_preset,
    "get_source_outputs":       get_source_outputs,
    "set_source_output":        set_source_output,
    # camera & display
    "get_camera":               get_camera,
    "get_tone_mapping":         get_tone_mapping,
    "set_tone_mapping":         set_tone_mapping,
    "get_color_lut":            get_color_lut,
    "set_color_lut":            set_color_lut,
    "get_scene_bounding_box":   get_scene_bounding_box,
    # Phase 15 — effect nodes
    "add_filter_effect":        add_filter_effect,
    "add_generator_effect":     add_generator_effect,
    "add_levels_effect":        add_levels_effect,
    "add_compare_mask_effect":  add_compare_mask_effect,
    "add_color_selection_effect": add_color_selection_effect,
    "add_anchor_point_effect":  add_anchor_point_effect,
    "get_effect_parameters":    get_effect_parameters,
    "get_selected_nodes":       get_selected_nodes,
    "set_selected_nodes":       set_selected_nodes,
    # Phase 16 — baking
    "get_baking_parameters":    get_baking_parameters,
    "set_baking_parameters":    set_baking_parameters,
    "bake_texture_set":         bake_texture_set,
    "get_baking_state":         get_baking_state,
    "set_baking_state":         set_baking_state,
    # Phase 17 — project lifecycle
    "create_project":           create_project,
    "open_project":             open_project,
    "close_project":            close_project,
    "reload_mesh":              reload_mesh,
    "get_project_metadata":     get_project_metadata,
    "set_project_metadata":     set_project_metadata,
    "list_project_metadata":    list_project_metadata,
    "list_resources_by_usage":  list_resources_by_usage,
}
