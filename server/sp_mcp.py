"""
server/sp_mcp.py

FastMCP server：对外暴露 MCP tools，内部通过 client.py 和 SP bridge 通信。

启动方式：
  stdio 模式（OpenCode / Claude Code）：
      python server/sp_mcp.py

  SSE 模式（浏览器 / 其他工具）：
      python server/sp_mcp.py --transport sse --port 8765
"""

import argparse
import sys
import os

# 确保 server 包可以被导入（兼容直接运行和 -m 两种方式）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastmcp import FastMCP
from server import client as sp

mcp = FastMCP("substance-painter")


# ── 连接 ─────────────────────────────────────────────────────────────────────

@mcp.tool()
def sp_ping() -> dict:
    """
    检查 SP bridge 连通性。
    任何操作序列开始前必须先调用，确认 Painter 正在运行且插件已加载。
    返回 SP 版本号和 Smart Material API 可用性。
    """
    return sp.call("ping")


# ── 图层读取 ──────────────────────────────────────────────────────────────────

@mcp.tool()
def sp_get_layer_stack() -> list:
    """
    返回当前活动纹理集的完整图层树 JSON。
    每个节点包含 id、name、type、enabled、opacity。
    GROUP 类型包含 children 列表（递归）。
    注意：layer id 在 Painter 重启后会变化，不要跨 session 缓存。
    """
    return sp.call("get_layer_stack")


@mcp.tool()
def sp_get_texture_sets(filter: str = "") -> list:
    """
    返回所有纹理集及其图层结构。
    每个纹理集包含：id、name、resolution、layers（图层树）。
    支持按名称关键词过滤（大小写不敏感）。

    filter: 关键词过滤，空字符串返回全部纹理集。
    返回: [{"id": "249", "name": "att_ammo_50b", "resolution": "4096x4096", "layers": [...]}]
    """
    return sp.call("get_texture_sets", {"filter": filter})


@mcp.tool()
def sp_find_layer_by_name(name: str) -> dict:
    """
    在所有纹理集中按名称搜索图层（大小写不敏感）。
    返回匹配的图层列表，每个包含 id、name、type、texture_set、depth。
    用于在不知道 layer_id 时定位目标图层。
    """
    if not name:
        raise ValueError("name must not be empty")
    return sp.call("find_layer_by_name", {"name": name})


@mcp.tool()
def sp_get_layer_properties(layer_id: str) -> dict:
    """
    返回指定图层的详细属性（opacity、enabled、blend_mode 等）。
    layer_id 从 sp_get_layer_stack 的返回值中获取。
    """
    return sp.call("get_layer_properties", {"layer_id": layer_id})


# ── 图层写入 ──────────────────────────────────────────────────────────────────

@mcp.tool()
def sp_add_fill_layer(
    name: str,
    channel: str = "BaseColor",
    color_hex: str = "#FFFFFF",
    opacity: float = 1.0,
    blend_mode: str = "Normal",
) -> dict:
    """
    在图层栈顶部新建 Fill Layer，返回新图层的 id 和 name。

    name      图层名称，使用语义化命名（如 "Rust_Overlay"，不要用 "Layer_1"）
    channel   通道名：BaseColor / Roughness / Metallic / Height / Normal
    color_hex 十六进制颜色，仅 BaseColor 通道有效（如 "#8B4513"）
    opacity   0.0–1.0，第一次建议从 0.3–0.5 开始，截图确认后再调整
    blend_mode 混合模式：Normal / Multiply / Overlay / Screen
    """
    if not name:
        raise ValueError("name must not be empty")
    if not (0.0 <= opacity <= 1.0):
        raise ValueError(f"opacity must be in [0.0, 1.0], got {opacity}")

    return sp.call("add_fill_layer", {
        "name":       name,
        "channel":    channel,
        "color_hex":  color_hex,
        "opacity":    opacity,
        "blend_mode": blend_mode,
    })


@mcp.tool()
def sp_set_layer_property(layer_id: str, prop: str, value: object) -> dict:
    """
    修改图层属性。
    layer_id 从 sp_get_layer_stack 获取。
    prop 可选值：opacity（float 0–1）/ enabled（bool）/ name（str）/ blend_mode（str）
    修改后建议调用 sp_capture_viewport 确认视觉效果。
    """
    _VALID_PROPS = {"opacity", "enabled", "name", "blend_mode"}
    if prop not in _VALID_PROPS:
        raise ValueError(
            f"Invalid prop: {prop!r}. Valid options: {sorted(_VALID_PROPS)}"
        )

    return sp.call("set_layer_property", {
        "layer_id": layer_id,
        "prop":     prop,
        "value":    value,
    })


# ── Smart Material（需要 SP 10.0+）────────────────────────────────────────────

@mcp.tool()
def sp_list_shelf_materials(filter: str = "") -> list:
    """
    列出 Shelf 中可用的 Smart Material，支持关键词过滤（大小写不敏感）。
    调用 sp_apply_smart_material 前建议先用此 tool 确认材质名称。
    示例：sp_list_shelf_materials(filter="metal") → ["Steel Dark Matte", ...]
    需要 SP 10.0+。
    """
    return sp.call("list_shelf_materials", {"filter": filter})


@mcp.tool()
def sp_apply_smart_material(layer_id: str, material_name: str) -> dict:
    """
    对指定图层应用 Shelf 中的 Smart Material（含所有 PBR 通道）。
    调用前先用 sp_list_shelf_materials 确认 material_name 的准确拼写。
    需要 SP 10.0+。
    """
    return sp.call("apply_smart_material", {
        "layer_id":      layer_id,
        "material_name": material_name,
    })


@mcp.tool()
def sp_add_smart_mask(layer_id: str, mask_name: str) -> dict:
    """
    为图层添加程序化遮罩。
    常用 mask_name：
      "Edge Wear"       边缘磨损
      "Dirt"            污垢
      "Grunge Scratches" 划痕
      "Rust"            锈迹
    需要 SP 10.0+。
    """
    return sp.call("add_smart_mask", {
        "layer_id":  layer_id,
        "mask_name": mask_name,
    })


@mcp.tool()
def sp_add_mask(layer_id: str) -> dict:
    """
    为图层添加一个空白白色遮罩（非程序化 Smart Mask）。
    添加后可用 sp_set_layer_channel 调整遮罩通道。
    如需程序化遮罩（自动边缘磨损等），用 sp_add_smart_mask。
    """
    if not layer_id:
        raise ValueError("layer_id must not be empty")
    return sp.call("add_mask", {"layer_id": layer_id})


@mcp.tool()
def sp_remove_mask(layer_id: str) -> dict:
    """
    移除图层的遮罩（不支持程序化 Smart Mask）。
    注意：Smart Mask 的遮罩需要用 sp_delete_layer 删除整个 mask effect。
    """
    if not layer_id:
        raise ValueError("layer_id must not be empty")
    return sp.call("remove_mask", {"layer_id": layer_id})


@mcp.tool()
def sp_list_materials(filter: str = "") -> list:
    """
    列出 Shelf 中可用的普通材质（SUBSTANCE 类型），支持关键词过滤。
    示例：sp_list_materials(filter="carbon") → ["Carbon Fiber", ...]
    需要 SP 10.0+。
    """
    return sp.call("list_materials", {"filter": filter})


@mcp.tool()
def sp_apply_material(layer_id: str, material_name: str) -> dict:
    """
    将普通材质（SUBSTANCE 类型）应用到指定图层的所有通道。
    调用前先用 sp_list_materials 确认 material_name 的准确拼写。
    需要 SP 10.0+。
    """
    if not layer_id:
        raise ValueError("layer_id must not be empty")
    if not material_name:
        raise ValueError("material_name must not be empty")
    return sp.call("apply_material", {
        "layer_id":      layer_id,
        "material_name": material_name,
    })


# ── 视觉反馈 ──────────────────────────────────────────────────────────────────

@mcp.tool()
def sp_set_iray_params(
    max_samples: int = 100,
    max_time: int = 60,
    width: int = 0,
    height: int = 0,
) -> dict:
    """
    设置 Iray 渲染参数，控制渲染质量和速度。

    max_samples  最大采样数（越小越快，100 适合快速预览）
    max_time     最大渲染时间（秒）
    width        渲染宽度（0=不修改，当前 viewport 尺寸）
    height       渲染高度（0=不修改）

    推荐快速预览：max_samples=50, max_time=30
    推荐最终渲染：max_samples=500, max_time=300
    """
    return sp.call("set_iray_params", {
        "max_samples": max_samples,
        "max_time":    max_time,
        "width":       width,
        "height":      height,
    })


@mcp.tool()
def sp_start_iray_render() -> dict:
    """
    异步启动 Iray 渲染（不阻塞 HTTP）。
    启动后用 sp_check_iray_render 轮询状态，
    渲染稳定后调用 sp_capture_viewport(mode="render") 截图。
    """
    return sp.call("start_iray_render")


@mcp.tool()
def sp_check_iray_render() -> dict:
    """
    检查 Iray 渲染状态。
    返回 iterations（如 "120/100"）和 time（如 "00:00:15/00:00:30"）。
    当 iterations 不再变化时，渲染已完成。
    """
    return sp.call("check_iray_render")


@mcp.tool()
def sp_get_iray_params() -> dict:
    """
    读取当前 Iray 渲染面板的参数设置。
    返回 params 字典，包含各 spinbox 的 objectName 和当前值。
    用于在修改前确认当前渲染配置。
    """
    return sp.call("get_iray_params")


@mcp.tool()
def sp_capture_viewport(mode: str = "quick") -> dict:
    """
    截取当前 3D viewport，返回 base64 编码的 PNG 图像。
    这是视觉创作迭代的核心工具，每次批量修改后必须调用。

    mode="quick"   Qt grab，毫秒级，用于迭代确认
    mode="render"  Iray 离线渲染，秒级，用于最终确认（导出前）

    返回：{"image": "<base64 PNG>", "width": int, "height": int}
    将 image 字段作为图像内容传给视觉模型分析。
    """
    if mode not in ("quick", "render"):
        raise ValueError(f"mode must be 'quick' or 'render', got {mode!r}")

    return sp.call("capture_viewport", {"mode": mode})


# ── 导出 ──────────────────────────────────────────────────────────────────────

@mcp.tool()
def sp_list_export_presets() -> list:
    """
    列出所有可用的导出预设名称。
    在调用 sp_export_textures 之前，先用此工具确认 preset 参数的正确值。
    """
    return sp.call("list_export_presets")


@mcp.tool()
def sp_export_textures(preset: str, output_dir: str) -> dict:
    """
    触发贴图导出，返回导出的文件路径列表。
    导出前建议先调用 sp_capture_viewport(mode="render") 做最终确认。
    output_dir 的文件可直接传给 SP2VTF 进行 Source 引擎格式转换。

    preset     导出预设名称，如 "PBR Metallic Roughness"
    output_dir 输出目录的绝对路径
    返回：{"files": ["path/to/BaseColor.png", ...]}
    """
    if not output_dir:
        raise ValueError("output_dir must not be empty")

    return sp.call("export_textures", {
        "preset":     preset,
        "output_dir": output_dir,
    })


# ── Escape hatch ──────────────────────────────────────────────────────────────

@mcp.tool()
def sp_run_python(code: str) -> dict:
    """
    在 Painter 主线程执行任意 Python 代码片段。
    仅在结构化 tool 无法满足需求时使用（Phase 2 功能探索、一次性调试）。
    优先使用上面的具体 tool，不要将此作为默认选项。

    返回：{"stdout": str, "locals": {str: str}}
    """
    return sp.call("run_python", {"code": code})


# ── Phase 6 — 图层基础 + 通道 + Undo ────────────────────────────────────────

@mcp.tool()
def sp_delete_layer(layer_id: str) -> dict:
    """
    删除指定图层。
    layer_id 从 sp_get_layer_stack 获取。
    """
    if not layer_id:
        raise ValueError("layer_id must not be empty")
    return sp.call("delete_layer", {"layer_id": layer_id})


@mcp.tool()
def sp_add_group_layer(name: str) -> dict:
    """
    新建空分组图层。
    name: 分组名称，使用语义化命名。
    """
    if not name:
        raise ValueError("name must not be empty")
    return sp.call("add_group_layer", {"name": name})


@mcp.tool()
def sp_add_paint_layer(name: str) -> dict:
    """
    新建绘画图层（PaintLayerNode）。
    name: 图层名称。
    """
    if not name:
        raise ValueError("name must not be empty")
    return sp.call("add_paint_layer", {"name": name})


@mcp.tool()
def sp_undo() -> dict:
    """
    撤销上一步操作。
    通过 SP 原生 undo 栈实现，用户在 SP 按 Ctrl+Z 也能撤销 MCP 操作。
    所有 layerstack API 操作（add/delete/modify）自动推入 SP undo 栈。
    """
    return sp.call("undo", {})


@mcp.tool()
def sp_redo() -> dict:
    """
    重做上一步被撤销的操作。
    通过 SP 原生 redo 栈实现，用户在 SP 按 Ctrl+Y 也能重做 MCP 操作。
    所有 layerstack API 操作（add/delete/modify）自动推入 SP undo 栈。
    """
    return sp.call("redo", {})


@mcp.tool()
def sp_set_layer_channel(layer_id: str, channel: str, value: object) -> dict:
    """
    为指定通道设定数值。

    layer_id  从 sp_get_layer_stack 获取
    channel   通道名：Roughness / Metallic / Height / BaseColor / Normal
    value     非 BaseColor 通道为 float (0.0–1.0)，BaseColor 为 hex color ("#FF0000")

    修改后建议调用 sp_capture_viewport 确认视觉效果。
    """
    if not layer_id:
        raise ValueError("layer_id must not be empty")
    return sp.call("set_layer_channel", {
        "layer_id": layer_id,
        "channel":  channel,
        "value":    value,
    })


@mcp.tool()
def sp_get_layer_channels(layer_id: str) -> dict:
    """
    返回所有通道的 opacity、blend_mode、source 值。
    用于查看图层的完整 PBR 通道状态。
    """
    if not layer_id:
        raise ValueError("layer_id must not be empty")
    return sp.call("get_layer_channels", {"layer_id": layer_id})


# ── Phase 7 — 图层高级 + TextureSet + 项目 + 相机 ───────────────────────────

@mcp.tool()
def sp_duplicate_layer(layer_id: str) -> dict:
    """
    复制图层，新图层在原图层上方。
    新图层继承原图层的所有通道属性。
    """
    if not layer_id:
        raise ValueError("layer_id must not be empty")
    return sp.call("duplicate_layer", {"layer_id": layer_id})


@mcp.tool()
def sp_move_layer(layer_id: str, target_id: str, position: str = "above") -> dict:
    """
    移动图层到目标图层上方或下方。

    layer_id  要移动的图层 ID
    target_id 目标图层 ID
    position  "above"（默认）或 "below"
    """
    if position not in ("above", "below"):
        raise ValueError(f"position must be 'above' or 'below', got {position!r}")
    return sp.call("move_layer", {
        "layer_id":  layer_id,
        "target_id": target_id,
        "position":  position,
    })


@mcp.tool()
def sp_group_layers(layer_ids: list) -> dict:
    """
    将多个图层打包进新分组。
    layer_ids: 图层 ID 列表，至少 1 个。
    """
    if not layer_ids:
        raise ValueError("layer_ids must not be empty")
    return sp.call("group_layers", {"layer_ids": layer_ids})


@mcp.tool()
def sp_ungroup_layer(layer_id: str) -> dict:
    """
    解散分组，子层提升到父级。
    group 内的图层会被移到 group 原位置的上方。
    """
    if not layer_id:
        raise ValueError("layer_id must not be empty")
    return sp.call("ungroup_layer", {"layer_id": layer_id})


@mcp.tool()
def sp_set_active_texture_set(name: str) -> dict:
    """
    切换当前操作的纹理集。
    name: 纹理集名称（从 sp_get_texture_sets 获取）。
    """
    if not name:
        raise ValueError("name must not be empty")
    return sp.call("set_active_texture_set", {"name": name})


@mcp.tool()
def sp_set_texture_set_resolution(width: int, height: int) -> dict:
    """
    修改当前纹理集分辨率。
    width/height: 分辨率数值（如 2048, 4096）。
    常用值：1024, 2048, 4096。
    """
    if width <= 0 or height <= 0:
        raise ValueError(f"width and height must be positive, got {width}x{height}")
    return sp.call("set_texture_set_resolution", {
        "width":  width,
        "height": height,
    })


@mcp.tool()
def sp_get_project_info() -> dict:
    """
    读取当前项目信息。
    返回：name、file_path、is_open、is_busy。
    """
    return sp.call("get_project_info")


@mcp.tool()
def sp_save_project() -> dict:
    """
    保存当前项目。
    建议在导出前调用。
    """
    return sp.call("save_project")


@mcp.tool()
def sp_set_camera(
    x: float, y: float, z: float,
    target_x: float, target_y: float, target_z: float,
    fov: float,
) -> dict:
    """
    设置相机位置和视角。

    x/y/z           相机位置
    target_x/y/z    目标点位置（相机朝向）
    fov             视场角（度），默认 45
    """
    return sp.call("set_camera", {
        "x": x, "y": y, "z": z,
        "target_x": target_x, "target_y": target_y, "target_z": target_z,
        "fov": fov,
    })


@mcp.tool()
def sp_frame_mesh() -> dict:
    """
    自动适配视图到模型（frame all）。
    相机会自动调整位置和缩放以适配整个模型。
    """
    return sp.call("frame_mesh")


@mcp.tool()
def sp_set_environment(preset: str) -> dict:
    """
    切换 HDRI 环境光预设。
    preset: 预设名称（如 "Sunrise", "Studio", "Night"）。
    """
    return sp.call("set_environment", {"preset": preset})


# ── Phase 8 — 批量 Undo ────────────────────────────────────────────────────

@mcp.tool()
def sp_begin_batch(name: str) -> dict:
    """
    开始批量操作。后续 layer 操作将合并为单条 undo。
    基于 `layerstack.ScopedModification`，用户在 SP 按 Ctrl+Z 一次撤销整批操作。

    使用示例：
    sp_begin_batch("Apply Rust Effect")
      sp_add_fill_layer("Rust_Base")
      sp_set_layer_channel("xxx", "Roughness", 0.8)
      sp_add_smart_mask("xxx", "Edge Wear")
    sp_end_batch()
    """
    if not name:
        raise ValueError("name must not be empty")
    return sp.call("begin_batch", {"name": name})


@mcp.tool()
def sp_end_batch() -> dict:
    """
    结束批量操作，合并为单条 undo。
    """
    return sp.call("end_batch")


# ── Phase 9 — JS API 集成（Baking + 通道管理）───────────────────────────────

@mcp.tool()
def sp_bake_mesh_maps(texture_set_name: str) -> dict:
    """
    烘焙指定纹理集的 mesh maps（AO/Curvature/Normal 等）。
    需要 SP 10.0+。通过 `js.evaluate("alg.baking.bake()")` 实现。

    texture_set_name: 纹理集名称（从 sp_get_texture_sets 获取）
    """
    if not texture_set_name:
        raise ValueError("texture_set_name must not be empty")
    return sp.call("bake_mesh_maps", {"texture_set_name": texture_set_name})


@mcp.tool()
def sp_add_texture_set_channel(texture_set_name: str, channel_id: str,
                                channel_format: str = "Color4",
                                channel_label: str = "") -> dict:
    """
    给纹理集添加通道。
    通过 `js.evaluate("alg.texturesets.addChannel()")` 实现。

    texture_set_name: 纹理集名称
    channel_id: 通道标识符（如 "custom_channel_0"）
    channel_format: 通道格式（"Color4" / "Grayscale"，默认 "Color4"）
    channel_label: 通道显示名称（默认同 channel_id）
    """
    if not texture_set_name:
        raise ValueError("texture_set_name must not be empty")
    if not channel_id:
        raise ValueError("channel_id must not be empty")
    return sp.call("add_texture_set_channel", {
        "texture_set_name": texture_set_name,
        "channel_id": channel_id,
        "channel_format": channel_format,
        "channel_label": channel_label,
    })


@mcp.tool()
def sp_remove_texture_set_channel(texture_set_name: str, channel_id: str) -> dict:
    """
    删除纹理集通道。
    通过 `js.evaluate("alg.texturesets.removeChannel()")` 实现。

    texture_set_name: 纹理集名称
    channel_id: 通道标识符
    """
    if not texture_set_name:
        raise ValueError("texture_set_name must not be empty")
    if not channel_id:
        raise ValueError("channel_id must not be empty")
    return sp.call("remove_texture_set_channel", {
        "texture_set_name": texture_set_name,
        "channel_id": channel_id,
    })


# ── Computer Use ────────────────────────────────────────────────────────────────

@mcp.tool()
def sp_window_info() -> dict:
    """
    返回 SP 主窗口的位置和尺寸信息，供 Computer Use 类工具做坐标映射。

    返回：screen_origin（窗口左上角屏幕坐标）、geometry（位置+宽高）、窗口状态标志。
    配合 sp_window_grab 使用，可精确定位截图中的 UI 元素坐标。
    """
    return sp.call("window_info")


@mcp.tool()
def sp_window_grab(region: dict = None) -> dict:
    """
    截取 SP 窗口完整截图或指定区域，返回 base64 编码的 PNG。

    region（可选）：{"x": 0, "y": 0, "width": 400, "height": 300}，x/y 相对于窗口左上角。
    不传 region 则截取整个 SP 窗口。
    返回 {"image": "<base64>", "width": int, "height": int}，
    可将 image 字段直接传给视觉模型分析窗口内容。
    """
    return sp.call("window_grab", {"region": region} if region else {})


@mcp.tool()
def sp_window_focus() -> dict:
    """
    将 SP 窗口置于前台并确保获得焦点。

    在发送鼠标点击或键盘操作前调用，确保输入到达正确的窗口。
    如果窗口已最小化，会先还原。

    返回 {"focused": bool, "is_minimized": bool, "hwnd": int}
    """
    return sp.call("window_focus", {})


@mcp.tool()
def sp_cu_unlock() -> dict:
    """
    解除 Computer Use 锁定，隐藏警示条。

    Computer Use 操作结束后调用，清除 "MCP Control Active" 警示覆盖层。
    返回 {"ok": True}
    """
    return sp.call("cu_unlock", {})


@mcp.tool()
def sp_cu_banner_text(text: str) -> dict:
    """
    更新 Computer Use 警示条显示的文字。

    用于超时时显示提示信息（如 "⚠ 请检查 SP 是否弹出确认对话框"），
    恢复正常后传入原始文字 "MCP Control Active - Do not touch mouse/keyboard"。

    返回 {"ok": bool, "text": str}
    """
    return sp.call("cu_banner_text", {"text": text})


@mcp.tool()
def sp_cu_warning(text: str = "") -> dict:
    """
    将警示条切换为黄色等待状态，提醒用户检查终端或 SP 弹窗。

    用于 Computer Use 操作超时时：
    1. sp_cu_warning("Timeout - Check terminal")  → 黄色警示条
    2. 用户处理完毕后，恢复：sp_cu_banner_text("MCP Control Active ...")  → 红色
    3. 操作结束：sp_cu_unlock()  → 绿色 → 消失

    不传 text 时使用默认提示文字。
    """
    return sp.call("cu_warning", {"text": text})


@mcp.tool()
def sp_mouse_move(x: int, y: int, relative: str = "screen") -> dict:
    """
    移动鼠标到指定坐标。

    x/y         目标坐标
    relative    "screen"（屏幕绝对坐标，默认）或 "window"（相对 SP 窗口左上角）
    """
    return sp.call("mouse_move", {"x": x, "y": y, "relative": relative})


@mcp.tool()
def sp_mouse_click(
    x: int = None, y: int = None,
    button: str = "left", clicks: int = 1,
    relative: str = "screen"
) -> dict:
    """
    在指定坐标执行鼠标点击。

    x/y         点击坐标（不传则在当前位置点击）
    button      "left" / "right" / "middle"
    clicks      1=单击, 2=双击
    relative    "screen" 或 "window"
    """
    params = {"button": button, "clicks": clicks, "relative": relative}
    if x is not None:
        params["x"] = x
    if y is not None:
        params["y"] = y
    return sp.call("mouse_click", params)


@mcp.tool()
def sp_mouse_scroll(amount: int) -> dict:
    """
    鼠标滚轮滚动。

    amount  正值=向上滚，负值=向下滚。建议 ±120 为单位（Windows 标准）。
    """
    return sp.call("mouse_scroll", {"amount": amount})


@mcp.tool()
def sp_mouse_drag(
    x1: int, y1: int, x2: int, y2: int,
    button: str = "left", relative: str = "screen"
) -> dict:
    """
    从 (x1,y1) 拖拽到 (x2,y2)。

    button    "left" / "right" / "middle"
    relative  "screen" 或 "window"
    """
    return sp.call("mouse_drag", {
        "x1": x1, "y1": y1, "x2": x2, "y2": y2,
        "button": button, "relative": relative,
    })


@mcp.tool()
def sp_key_send(keys: str, modifiers: list = None) -> dict:
    """
    发送键盘按键到当前焦点窗口。

    keys        要发送的文本（支持组合键名如 "enter", "tab", "f5" 等）
    modifiers   修饰键列表，如 ["ctrl", "shift"]
                修饰键会按住→发送 keys→释放修饰键

    常用键名：
    导航: enter, tab, esc, space, backspace, delete,
          home, end, pageup, pagedown, left, right, up, down
    修饰: ctrl, shift, alt
    功能: f1 - f12
    普通字符直接用文本，如 "Hello World"

    示例：
    sp_key_send(keys="a", modifiers=["ctrl"])   → Ctrl+A
    sp_key_send(keys="enter")                   → 回车
    sp_key_send(keys="Hello")                   → 打字 Hello
    """
    return sp.call("key_send", {
        "keys": keys,
        "modifiers": modifiers or [],
    })


@mcp.tool()
def sp_shortcut(action: str) -> dict:
    """
    执行预定义的 SP 快捷键操作。

    action: 操作名称，可选值：
      文件: save / save_as / new_project / open_project / close_project
            import_image / export_textures
      编辑: undo / redo / select_all / deselect / copy / paste / cut
            duplicate / delete_layer
      图层: new_fill_layer / new_paint_layer / new_group / merge_down
      视口: frame_all / toggle_wireframe / toggle_unity
      模式: paint_mode / erase_mode / project_mode
      显示: toggle_ui / toggle_mask_view
      Iray: toggle_iray

    示例：
    sp_shortcut(action="save")             → Ctrl+S
    sp_shortcut(action="undo")             → Ctrl+Z
    sp_shortcut(action="frame_all")        → Alt+F
    sp_shortcut(action="toggle_wireframe") → F4
    """
    return sp.call("sp_shortcut", {"action": action})


# ── 程序化源参数控制 ─────────────────────────────────────────────────────────


@mcp.tool()
def sp_get_source_info(layer_id: str, channel: str = None) -> dict:
    """
    获取填充图层/效果的程序化源信息。

    layer_id  从 sp_get_layer_stack 获取的图层 ID
    channel   通道名（BaseColor/Roughness/Metallic/Height/Normal 等），不指定则返回所有通道

    返回源类型、资源引用、参数、预设列表等。
    如果图层没有源或图层类型不支持源，返回明确错误。
    """
    if not layer_id:
        raise ValueError("layer_id must not be empty")
    kwargs = {"layer_id": layer_id}
    if channel:
        kwargs["channel"] = channel
    return sp.call("get_source_info", kwargs)


@mcp.tool()
def sp_get_substance_parameters(layer_id: str, channel: str = None) -> dict:
    """
    读取程序化 Substance 源的当前参数值。

    layer_id  图层 ID（该图层必须已应用程序化材质/Substance）
    channel   通道名，不指定则自动选择（先尝 BaseColor，再尝 Material 模式）

    返回每个参数的 name、value、type 和 description。
    用于 AI 理解当前材质状态并决定调参方向。
    """
    if not layer_id:
        raise ValueError("layer_id must not be empty")
    kwargs = {"layer_id": layer_id}
    if channel:
        kwargs["channel"] = channel
    return sp.call("get_substance_parameters", kwargs)


@mcp.tool()
def sp_set_substance_parameters(layer_id: str, params: dict,
                                channel: str = None) -> dict:
    """
    修改程序化 Substance 源的参数值。

    layer_id  图层 ID
    params    参数名→值的映射，如 {"scale": 2.0, "dirt_amount": 0.5, "color": {"r": 1.0, "g": 0.5, "b": 0.2}}
              bool 参数用 0/1 而非 true/false
    channel   通道名，不指定则自动选择

    修改后建议调用 sp_capture_viewport 评估效果。
    """
    if not layer_id:
        raise ValueError("layer_id must not be empty")
    if not params or not isinstance(params, dict):
        raise ValueError("params must be a non-empty dict, e.g. {\"scale\": 2.0}")
    kwargs = {"layer_id": layer_id, "params": params}
    if channel:
        kwargs["channel"] = channel
    return sp.call("set_substance_parameters", kwargs)


@mcp.tool()
def sp_get_substance_presets(layer_id: str, channel: str = None) -> dict:
    """
    列出程序化 Substance 源的所有可用预设名称。

    用此 tool 查看预设列表，然后用 sp_apply_substance_preset 应用。
    """
    if not layer_id:
        raise ValueError("layer_id must not be empty")
    kwargs = {"layer_id": layer_id}
    if channel:
        kwargs["channel"] = channel
    return sp.call("get_substance_presets", kwargs)


@mcp.tool()
def sp_apply_substance_preset(layer_id: str, preset_name: str,
                              channel: str = None) -> dict:
    """
    为程序化 Substance 源应用指定预设。

    preset_name 必须是 sp_get_substance_presets 返回列表中的值。
    """
    if not layer_id:
        raise ValueError("layer_id must not be empty")
    if not preset_name:
        raise ValueError("preset_name must not be empty")
    kwargs = {"layer_id": layer_id, "preset_name": preset_name}
    if channel:
        kwargs["channel"] = channel
    return sp.call("apply_substance_preset", kwargs)


@mcp.tool()
def sp_get_source_outputs(layer_id: str, channel: str = None) -> dict:
    """
    获取程序化 Substance 源的输出信息。

    返回 image_outputs（输出列表）、active_output（当前输出）、
    mask_output（遮罩输出）、output_mapping（通道→输出映射）。
    """
    if not layer_id:
        raise ValueError("layer_id must not be empty")
    kwargs = {"layer_id": layer_id}
    if channel:
        kwargs["channel"] = channel
    return sp.call("get_source_outputs", kwargs)


@mcp.tool()
def sp_set_source_output(layer_id: str, output_identifier: str,
                         channel: str = None) -> dict:
    """
    切换程序化 Substance 源的活动输出。

    output_identifier  输出标识符，从 sp_get_source_outputs 的 image_outputs 列表获取
                       常用如 "output"、"base_color"、"roughness" 等
    """
    if not layer_id:
        raise ValueError("layer_id must not be empty")
    if not output_identifier:
        raise ValueError("output_identifier must not be empty")
    kwargs = {"layer_id": layer_id, "output_identifier": output_identifier}
    if channel:
        kwargs["channel"] = channel
    return sp.call("set_source_output", kwargs)


# ── 相机与显示增强 ────────────────────────────────────────────────────────────


@mcp.tool()
def sp_get_camera() -> dict:
    """
    读取主相机完整状态。

    返回 position[x,y,z], rotation[x,y,z](欧拉角°), field_of_view(°),
    focal_length(mm), focus_distance, aperture, orthographic_height, projection_type。

    用于 AI 理解当前视角，在 sp_set_camera 前查询当前值避免非预期跳变。
    """
    return sp.call("get_camera")


@mcp.tool()
def sp_get_tone_mapping() -> dict:
    """
    获取当前色调映射函数（Linear 或 ACES）。

    仅在非色彩管理模式下有效；色彩管理模式下返回 error 提示。
    """
    return sp.call("get_tone_mapping")


@mcp.tool()
def sp_set_tone_mapping(function: str = "ACES") -> dict:
    """
    设置色调映射函数。

    function  "Linear"（线性转 sRGB，裁剪 >1 值）
              "ACES"（学院色彩编码系统标准重映射）

    仅在非色彩管理模式下有效。
    """
    if function not in ("Linear", "ACES"):
        raise ValueError(f"function must be 'Linear' or 'ACES', got {function!r}")
    return sp.call("set_tone_mapping", {"function": function})


@mcp.tool()
def sp_get_color_lut() -> dict:
    """
    获取当前项目使用的色彩 LUT 配置文件。

    返回 None 表示未使用色彩配置文件。
    """
    return sp.call("get_color_lut")


@mcp.tool()
def sp_set_color_lut(resource_name: str) -> dict:
    """
    按名称设置色彩 LUT 配置文件。

    resource_name  资源名称（模糊匹配），如 "sepia"、"Greyscale"、"Invert" 等。
                   用 sp_list_all_resources 可查看可用的 colorluts。

    设为空字符串 "" 则清除色彩 LUT。
    """
    return sp.call("set_color_lut", {"resource_name": resource_name})


@mcp.tool()
def sp_get_scene_bounding_box() -> dict:
    """
    获取场景包围盒。

    返回 dimensions[x,y,z]、center[x,y,z]、radius。
    用于 AI 计算相机取景距离、判断模型尺度。
    """
    return sp.call("get_scene_bounding_box")


# ── Phase 15: 效果节点 ──────────────────────────────────────────────────────────


@mcp.tool()
def sp_add_filter_effect(layer_id: str, filter_name: str = None) -> dict:
    """
    在图层上添加 Filter 效果。

    filter_name  模糊搜索的 filter 资源名。不指定则创建空 filter。
    返回 effect_id 用于后续参数获取/设置。
    """
    if not layer_id:
        raise ValueError("layer_id must not be empty")
    kwargs = {"layer_id": layer_id}
    if filter_name:
        kwargs["filter_name"] = filter_name
    return sp.call("add_filter_effect", kwargs)


@mcp.tool()
def sp_add_generator_effect(layer_id: str, generator_name: str = None) -> dict:
    """
    在图层上添加 Generator 效果。

    generator_name  模糊搜索的 generator 资源名。不指定则创建空 generator。
    """
    if not layer_id:
        raise ValueError("layer_id must not be empty")
    kwargs = {"layer_id": layer_id}
    if generator_name:
        kwargs["generator_name"] = generator_name
    return sp.call("add_generator_effect", kwargs)


@mcp.tool()
def sp_add_levels_effect(layer_id: str) -> dict:
    """
    在图层上添加 Levels 效果。

    用于调整通道的色阶（输入/输出范围、gamma、clamp）。
    """
    if not layer_id:
        raise ValueError("layer_id must not be empty")
    return sp.call("add_levels_effect", {"layer_id": layer_id})


@mcp.tool()
def sp_add_compare_mask_effect(layer_id: str) -> dict:
    """
    在图层 Mask 栈中添加 Compare Mask 效果。

    用于基于通道比较创建遮罩。
    """
    if not layer_id:
        raise ValueError("layer_id must not be empty")
    return sp.call("add_compare_mask_effect", {"layer_id": layer_id})


@mcp.tool()
def sp_add_color_selection_effect(layer_id: str) -> dict:
    """
    在图层 Mask 栈中添加 Color Selection 效果。

    用于基于 ID Mask 颜色选择创建遮罩。
    """
    if not layer_id:
        raise ValueError("layer_id must not be empty")
    return sp.call("add_color_selection_effect", {"layer_id": layer_id})


@mcp.tool()
def sp_add_anchor_point_effect(layer_id: str, anchor_name: str = "Anchor") -> dict:
    """
    在图层上添加 Anchor Point 效果，用于引用其他图层的内容。

    anchor_name  锚点名称。
    """
    if not layer_id:
        raise ValueError("layer_id must not be empty")
    return sp.call("add_anchor_point_effect",
                   {"layer_id": layer_id, "anchor_name": anchor_name or "Anchor"})


@mcp.tool()
def sp_get_effect_parameters(layer_id: str) -> dict:
    """
    读取效果节点参数。

    支持 LevelsEffect, CompareMaskEffect, ColorSelectionEffect,
    FilterEffect, GeneratorEffect。
    返回节点类型和当前参数/源信息。
    """
    if not layer_id:
        raise ValueError("layer_id must not be empty")
    return sp.call("get_effect_parameters", {"layer_id": layer_id})


@mcp.tool()
def sp_get_selected_nodes(texture_set_name: str = None) -> dict:
    """
    获取当前选中的节点列表。

    texture_set_name  纹理集名称，不指定则使用活动纹理集。
    """
    kwargs = {}
    if texture_set_name:
        kwargs["texture_set_name"] = texture_set_name
    return sp.call("get_selected_nodes", kwargs)


@mcp.tool()
def sp_set_selected_nodes(node_ids: list) -> dict:
    """
    设置选中节点。

    node_ids  节点 ID 列表。
    """
    if not node_ids:
        raise ValueError("node_ids must be a non-empty list")
    return sp.call("set_selected_nodes", {"node_ids": node_ids})


# ── Phase 16: 烘焙 API ──────────────────────────────────────────────────────────


@mcp.tool()
def sp_get_baking_parameters(texture_set_name: str) -> dict:
    """
    读取纹理集的完整烘焙参数。

    返回 common 参数、各 baker 参数、曲率方法、启用的 bakers 和 UV tiles。
    """
    if not texture_set_name:
        raise ValueError("texture_set_name must not be empty")
    return sp.call("get_baking_parameters", {"texture_set_name": texture_set_name})


@mcp.tool()
def sp_set_baking_parameters(texture_set_name: str,
                             common_params: dict = None,
                             baker_params: dict = None) -> dict:
    """
    设置纹理集的烘焙参数。

    common_params  如 {"OutputSize": [4096, 4096], "HipolyMesh": "file:///C:/..."}
    baker_params    如 {"AO": {"Distribution": "Cosine"}}
    """
    if not texture_set_name:
        raise ValueError("texture_set_name must not be empty")
    kwargs = {"texture_set_name": texture_set_name}
    if common_params:
        kwargs["common_params"] = common_params
    if baker_params:
        kwargs["baker_params"] = baker_params
    return sp.call("set_baking_parameters", kwargs)


@mcp.tool()
def sp_bake_texture_set(texture_set_name: str) -> dict:
    """
    异步启动纹理集烘焙。

    烘焙过程异步进行，完成后触发 BakingProcessEnded 事件。
    使用前需确保烘焙参数已配置（sp_set_baking_parameters）。
    """
    if not texture_set_name:
        raise ValueError("texture_set_name must not be empty")
    return sp.call("bake_texture_set", {"texture_set_name": texture_set_name})


@mcp.tool()
def sp_get_baking_state(texture_set_name: str) -> dict:
    """
    获取烘焙状态（启用/禁用、链接信息、UV tiles）。

    返回 textureset_enabled, curvature_method, enabled_bakers,
    linked_groups, enabled_uv_tiles。
    """
    if not texture_set_name:
        raise ValueError("texture_set_name must not be empty")
    return sp.call("get_baking_state", {"texture_set_name": texture_set_name})


@mcp.tool()
def sp_set_baking_state(texture_set_name: str,
                        enabled: bool = None,
                        curvature_method: str = None,
                        enabled_bakers: list = None,
                        enabled_uv_tiles: list = None) -> dict:
    """
    设置烘焙状态。

    enabled            是否启用该纹理集烘焙
    curvature_method    "FromMesh" 或 "FromNormalMap"
    enabled_bakers      启用的 baker 列表，如 ["AO", "Normal", "Curvature"]
    enabled_uv_tiles    启用的 UV tiles，如 [{"u": 0, "v": 0}, {"u": 1, "v": 0}]
    """
    if not texture_set_name:
        raise ValueError("texture_set_name must not be empty")
    kwargs = {"texture_set_name": texture_set_name}
    if enabled is not None:
        kwargs["enabled"] = enabled
    if curvature_method:
        kwargs["curvature_method"] = curvature_method
    if enabled_bakers is not None:
        kwargs["enabled_bakers"] = enabled_bakers
    if enabled_uv_tiles is not None:
        kwargs["enabled_uv_tiles"] = enabled_uv_tiles
    return sp.call("set_baking_state", kwargs)


# ── Phase 17: 项目生命周期 ──────────────────────────────────────────────────────


@mcp.tool()
def sp_create_project(
    mesh_file_path: str,
    mesh_map_file_paths: list = None,
    normal_map_format: str = "OpenGL",
    tangent_space_mode: str = "PerFragment",
    project_workflow: str = "Default",
    import_cameras: bool = False,
    default_texture_resolution: int = 2048,
    mesh_unit_scale: float = None,
) -> dict:
    """
    创建新 Substance 3D Painter 项目。

    mesh_file_path              网格文件路径 (.fbx/.obj/.dae/.ply/.usd)
    mesh_map_file_paths          额外的网格贴图路径列表
    normal_map_format            "OpenGL" 或 "DirectX"
    tangent_space_mode           "PerVertex" 或 "PerFragment"
    project_workflow             "Default" / "TextureSetPerUVTile" / "UVTile"
    import_cameras               是否从网格文件导入相机
    default_texture_resolution   默认贴图分辨率 (256/512/1024/2048/4096)
    mesh_unit_scale              自定义单位缩放 (cm)，None 则使用文件内部单位

    仅在未打开项目时可用。
    """
    if not mesh_file_path:
        raise ValueError("mesh_file_path must not be empty")
    kwargs = {
        "mesh_file_path": mesh_file_path,
        "normal_map_format": normal_map_format,
        "tangent_space_mode": tangent_space_mode,
        "project_workflow": project_workflow,
        "import_cameras": import_cameras,
        "default_texture_resolution": default_texture_resolution,
    }
    if mesh_map_file_paths:
        kwargs["mesh_map_file_paths"] = mesh_map_file_paths
    if mesh_unit_scale is not None:
        kwargs["mesh_unit_scale"] = mesh_unit_scale
    return sp.call("create_project", kwargs)


@mcp.tool()
def sp_open_project(file_path: str) -> dict:
    """
    打开已有 .spp 项目。

    file_path  项目文件的完整路径。
    仅在未打开项目时可用。
    """
    if not file_path:
        raise ValueError("file_path must not be empty")
    return sp.call("open_project", {"file_path": file_path})


@mcp.tool()
def sp_close_project() -> dict:
    """
    关闭当前项目（不保存修改）。

    关闭后可使用 sp_create_project 或 sp_open_project 开始新工作。
    """
    return sp.call("close_project")


@mcp.tool()
def sp_reload_mesh(mesh_file_path: str,
                   import_cameras: bool = True,
                   preserve_strokes: bool = True) -> dict:
    """
    重载当前项目的网格（异步操作）。

    mesh_file_path     新网格文件路径
    import_cameras     是否从文件导入相机
    preserve_strokes   是否保留笔触位置
    """
    if not mesh_file_path:
        raise ValueError("mesh_file_path must not be empty")
    return sp.call("reload_mesh", {
        "mesh_file_path": mesh_file_path,
        "import_cameras": import_cameras,
        "preserve_strokes": preserve_strokes,
    })


@mcp.tool()
def sp_get_project_metadata(context: str, key: str) -> dict:
    """
    读取项目元数据。

    context  命名空间（如插件名），用于隔离不同工具的元数据
    key      元数据键名
    """
    if not context:
        raise ValueError("context must not be empty")
    if not key:
        raise ValueError("key must not be empty")
    return sp.call("get_project_metadata", {"context": context, "key": key})


@mcp.tool()
def sp_set_project_metadata(context: str, key: str, value) -> dict:
    """
    写入项目元数据。

    支持类型: bool, int, float, str, list, dict (键为 str)。
    元数据随项目文件持久化保存。
    """
    if not context:
        raise ValueError("context must not be empty")
    if not key:
        raise ValueError("key must not be empty")
    return sp.call("set_project_metadata",
                   {"context": context, "key": key, "value": value})


@mcp.tool()
def sp_list_project_metadata(context: str) -> dict:
    """
    列出某 context 下所有元数据键名。
    """
    if not context:
        raise ValueError("context must not be empty")
    return sp.call("list_project_metadata", {"context": context})


@mcp.tool()
def sp_list_resources_by_usage(usage: str, search: str = "") -> dict:
    """
    按用途类型列出可用资源。

    usage   资源用途: "filter"/"generator"/"substance"/"smart_material"/"smart_mask"/"texture"/"environment"/"export_preset"
    search  可选的名称过滤
    """
    if not usage:
        raise ValueError("usage must not be empty")
    return sp.call("list_resources_by_usage",
                   {"usage": usage, "search": search or ""})


# ── 入口 ──────────────────────────────────────────────────────────────────────

def main() -> None:
    # 安全 PID 锁：启动前自动清理上一个 sp_mcp.py 僵尸进程
    # 双重校验（PID + 命令行含 sp_mcp.py），绝不误杀
    from server.pidlock import acquire_pid_lock
    acquire_pid_lock()

    parser = argparse.ArgumentParser(description="SP MCP Server")
    parser.add_argument(
        "--transport",
        default="stdio",
        choices=["stdio", "sse"],
        help="Transport mode (default: stdio)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="SSE server port (default: 8765, only used with --transport sse)",
    )
    args = parser.parse_args()

    try:
        if args.transport == "sse":
            mcp.run(transport="sse", port=args.port)
        else:
            mcp.run(transport="stdio")
    finally:
        # 确保退出时清理 PID 文件（mcp.run 可能触发 atexit，最终兜底）
        from server.pidlock import _cleanup_pid_file
        _cleanup_pid_file()


if __name__ == "__main__":
    main()
