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

    return {"id": str(layer.uid()), "name": layer.get_name()}


def set_layer_property(layer_id: str, prop: str, value) -> dict:
    _VALID_PROPS = {"opacity", "enabled", "name", "blend_mode"}
    if prop not in _VALID_PROPS:
        raise ValueError(
            f"Unsupported prop: {prop!r}. Valid: {sorted(_VALID_PROPS)}"
        )

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
        if res.type() == r.Type.SMART_MATERIAL:
            materials.append(res.gui_name())
    return sorted(set(materials))


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
    node = _find_layer(layer_id)
    import substance_painter.layerstack as ls
    ls.delete_node(node)
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
    import substance_painter.undo
    substance_painter.undo.undo()
    return {"ok": True, "undoable": substance_painter.undo.is_undo_available()}


def redo() -> dict:
    import substance_painter.undo
    substance_painter.undo.redo()
    return {"ok": True, "redoable": substance_painter.undo.is_redo_available()}


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

    ch = getattr(ls.ChannelType, _CHANNEL_MAP[ch_key])
    if ch_key == "basecolor":
        r, g, b = _hex_to_rgb(str(value))
        node.set_source(ch, ls.Color(r, g, b))
    else:
        node.set_source(ch, float(value))
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
            if ch_name == "BaseColor" and hasattr(source, "r"):
                entry["source"] = f"#{int(source.r*255):02x}{int(source.g*255):02x}{int(source.b*255):02x}"
            else:
                entry["source"] = source
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

    for ch in (ls.ChannelType.BaseColor, ls.ChannelType.Roughness,
               ls.ChannelType.Metallic, ls.ChannelType.Height, ls.ChannelType.Normal):
        new_node.set_opacity(node.get_opacity(ch), ch)
        new_node.set_blending_mode(node.get_blending_mode(ch), ch)
        src = node.get_source(ch)
        if src is not None:
            new_node.set_source(ch, src)

    return {"id": str(new_node.uid()), "name": new_node.get_name()}


def move_layer(layer_id: str, target_id: str, position: str = "above") -> dict:
    if position not in ("above", "below"):
        raise ValueError(f"position must be 'above' or 'below', got {position!r}")
    node = _find_layer(layer_id)
    target = _find_layer(target_id)
    import substance_painter.layerstack as ls

    if position == "above":
        pos = ls.InsertPosition.above_node(target)
    else:
        pos = ls.InsertPosition.below_node(target)
    ls.move_node(node, pos)
    return {"ok": True}


def group_layers(layer_ids: list) -> dict:
    if not layer_ids:
        raise ValueError("layer_ids must not be empty")
    import substance_painter.layerstack as ls
    import substance_painter.textureset as ts

    nodes = [_find_layer(lid) for lid in layer_ids]
    stack = ts.get_active_stack()
    pos = ls.InsertPosition.from_textureset_stack(stack)
    group = ls.insert_group(pos)
    group.set_name("New Group")

    for node in nodes:
        ls.move_node(node, ls.InsertPosition.inside_node(group, group.get_stack()))

    return {"id": str(group.uid()), "name": group.get_name()}


def ungroup_layer(layer_id: str) -> dict:
    node = _find_layer(layer_id)
    import substance_painter.layerstack as ls

    children = node.sub_layers()
    for child in children:
        ls.move_node(child, ls.InsertPosition.above_node(node))
    ls.delete_node(node)
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
        "color_space": substance_painter.project.color_space(),
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
    import substance_painter.camera
    substance_painter.camera.set_position(x, y, z)
    substance_painter.camera.set_target(target_x, target_y, target_z)
    substance_painter.camera.set_fov(fov)
    return {"ok": True}


def frame_mesh() -> dict:
    import substance_painter.camera
    substance_painter.camera.frame_all()
    return {"ok": True}


def set_environment(preset: str) -> dict:
    import substance_painter.environment
    substance_painter.environment.set_preset(preset)
    return {"ok": True}


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
}
