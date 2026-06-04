"""
plugin/handlers.py

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


# ── 外置 Undo/Redo 栈 ────────────────────────────────────────────────────────

_undo_stack = []  # [(undo_fn, redo_fn), ...]
_redo_stack = []  # [(undo_fn, redo_fn), ...]


def _push_undo(undo_fn, redo_fn):
    """记录一条 undo 操作，清空 redo 栈。"""
    _undo_stack.append((undo_fn, redo_fn))
    _redo_stack.clear()


def _save_layer_state(layer_id: str) -> dict:
    """保存图层的完整状态，用于 delete_layer 的 undo。"""
    import substance_painter.layerstack as ls

    node = _find_layer(layer_id)
    state = {
        "id": str(node.uid()),
        "name": node.get_name(),
        "type": type(node).__name__,
        "visible": node.is_visible(),
        "opacity": {},
        "blending": {},
        "sources": {},
    }

    for ch_name in ("BaseColor", "Roughness", "Metallic", "Height", "Normal"):
        ch = getattr(ls.ChannelType, ch_name)
        state["opacity"][ch_name] = node.get_opacity(ch)
        state["blending"][ch_name] = node.get_blending_mode(ch).name
        try:
            src = node.get_source(ch)
            if src is not None and hasattr(src, "get_color"):
                c = src.get_color()
                state["sources"][ch_name] = c.value_raw
        except Exception:
            pass

    return state


def _restore_layer(state: dict) -> str:
    """从保存的状态恢复图层，返回新图层 id。"""
    import substance_painter.layerstack as ls
    import substance_painter.colormanagement as cm
    import substance_painter.textureset as ts

    stack = ts.get_active_stack()
    pos = ls.InsertPosition.from_textureset_stack(stack)

    if state["type"] == "GroupLayerNode":
        node = ls.insert_group(pos)
    else:
        node = ls.insert_fill(pos)

    node.set_name(state["name"])
    node.set_visible(state["visible"])

    for ch_name in ("BaseColor", "Roughness", "Metallic", "Height", "Normal"):
        ch = getattr(ls.ChannelType, ch_name)
        if ch_name in state["opacity"]:
            node.set_opacity(state["opacity"][ch_name], ch)
        if ch_name in state["blending"]:
            blend = getattr(ls.BlendingMode, state["blending"][ch_name], None)
            if blend:
                node.set_blending_mode(blend, ch)
        if ch_name in state["sources"]:
            raw = state["sources"][ch_name]
            node.set_source(ch, cm.Color(raw[0], raw[1], raw[2]))

    return str(node.uid())


def _sp():
    import substance_painter
    return substance_painter


def _sp_version() -> tuple:
    import substance_painter.application
    ver_str = substance_painter.application.version()
    return tuple(int(x) for x in ver_str.split(".")[:2])


def _has_smart_api() -> bool:
    return _sp_version() >= (10, 0)


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

    # 记录 undo
    _push_undo(
        undo_fn=lambda: delete_layer(new_id),
        redo_fn=lambda: add_fill_layer(name, channel, color_hex, opacity, blend_mode),
    )

    return {"id": new_id, "name": layer.get_name()}


def set_layer_property(layer_id: str, prop: str, value) -> dict:
    _VALID_PROPS = {"opacity", "enabled", "name", "blend_mode"}
    if prop not in _VALID_PROPS:
        raise ValueError(
            f"Unsupported prop: {prop!r}. Valid: {sorted(_VALID_PROPS)}"
        )

    node = _find_layer(layer_id)
    import substance_painter.layerstack as ls

    # 读取旧值
    if prop == "opacity":
        old_value = node.get_opacity(ls.ChannelType.BaseColor)
        node.set_opacity(float(value), ls.ChannelType.BaseColor)
    elif prop == "enabled":
        old_value = node.is_visible()
        node.set_visible(bool(value))
    elif prop == "name":
        old_value = node.get_name()
        node.set_name(str(value))
    elif prop == "blend_mode":
        old_value = node.get_blending_mode(ls.ChannelType.BaseColor).name
        blend = getattr(ls.BlendingMode, str(value), None)
        if blend is None:
            raise ValueError(f"Unknown blend mode: {value!r}")
        node.set_blending_mode(blend)

    # 记录 undo
    _push_undo(
        undo_fn=lambda: set_layer_property(layer_id, prop, old_value),
        redo_fn=lambda: set_layer_property(layer_id, prop, value),
    )

    return {"ok": True}


def apply_smart_material(layer_id: str, material_name: str) -> dict:
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
    # 保存完整状态用于 undo
    saved_state = _save_layer_state(layer_id)

    node = _find_layer(layer_id)
    import substance_painter.layerstack as ls
    ls.delete_node(node)

    # 记录 undo
    _push_undo(
        undo_fn=lambda: _restore_layer(saved_state),
        redo_fn=lambda: delete_layer(layer_id),
    )

    return {"ok": True}


def add_group_layer(name: str) -> dict:
    if not name:
        raise ValueError("name must not be empty")
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
    import substance_painter.layerstack as ls
    import substance_painter.textureset as ts

    stack = ts.get_active_stack()
    pos = ls.InsertPosition.from_textureset_stack(stack)
    node = ls.insert_paint(pos)
    node.set_name(name)
    return {"id": str(node.uid()), "name": node.get_name()}


def undo() -> dict:
    """撤销上一步操作（外置 undo 栈）。"""
    if not _undo_stack:
        return {"ok": False, "error": "Nothing to undo"}
    undo_fn, redo_fn = _undo_stack.pop()
    undo_fn()
    _redo_stack.append((undo_fn, redo_fn))
    return {"ok": True, "remaining": len(_undo_stack)}


def redo() -> dict:
    """重做上一步操作（外置 redo 栈）。"""
    if not _redo_stack:
        return {"ok": False, "error": "Nothing to redo"}
    undo_fn, redo_fn = _redo_stack.pop()
    redo_fn()
    _undo_stack.append((undo_fn, redo_fn))
    return {"ok": True, "remaining": len(_redo_stack)}


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
    node = _find_layer(layer_id)
    import substance_painter.layerstack as ls
    import substance_painter.colormanagement as cm

    ch = getattr(ls.ChannelType, _CHANNEL_MAP[ch_key])

    # 读取旧值
    old_value = None
    try:
        src = node.get_source(ch)
        if src is not None and hasattr(src, "get_color"):
            c = src.get_color()
            old_raw = c.value_raw
            if ch_key == "basecolor":
                old_value = f"#{int(old_raw[0]*255):02x}{int(old_raw[1]*255):02x}{int(old_raw[2]*255):02x}"
            else:
                old_value = old_raw[0]
    except Exception:
        pass

    # 设置新值
    if ch_key == "basecolor":
        r, g, b = _hex_to_rgb(str(value))
        node.set_source(ch, cm.Color(r, g, b))
    else:
        v = float(value)
        node.set_source(ch, cm.Color(v, v, v))

    # 记录 undo
    if old_value is not None:
        _push_undo(
            undo_fn=lambda: set_layer_channel(layer_id, channel, old_value),
            redo_fn=lambda: set_layer_channel(layer_id, channel, value),
        )

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

    # 记录 undo
    _push_undo(
        undo_fn=lambda: delete_layer(new_id),
        redo_fn=lambda: duplicate_layer(layer_id),
    )

    return {"id": new_id, "name": new_node.get_name()}


def move_layer(layer_id: str, target_id: str, position: str = "above") -> dict:
    raise NotImplementedError(
        "move_layer is not available through the SP 10.x Python API. "
        "Use keyboard shortcuts or drag-and-drop in the UI."
    )


def group_layers(layer_ids: list) -> dict:
    raise NotImplementedError(
        "group_layers is not available through the SP 10.x Python API. "
        "Select layers in UI and press Ctrl+G."
    )


def ungroup_layer(layer_id: str) -> dict:
    raise NotImplementedError(
        "ungroup_layer is not available through the SP 10.x Python API. "
        "Select group in UI and press Ctrl+Shift+G."
    )


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
    raise NotImplementedError(
        "frame_mesh is not available through the Python API. "
        "Use viewport shortcut 'F' or sp_run_python as workaround."
    )


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

_batch_scope = None


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
