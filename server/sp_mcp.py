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


_UNDO_REDO_CODE = """\
from substance_painter.ui import get_main_window
from PySide2.QtWidgets import QUndoView
mv = get_main_window()
views = mv.findChildren(QUndoView)
for v in views:
    if v.objectName() == 'history':
        s = v.stack()
        if s.canUndo():
            s.undo()
            print('ok')
        else:
            print('empty')
        break
else:
    print('not_found')
"""

_REDO_CODE = """\
from substance_painter.ui import get_main_window
from PySide2.QtWidgets import QUndoView
mv = get_main_window()
views = mv.findChildren(QUndoView)
for v in views:
    if v.objectName() == 'history':
        s = v.stack()
        if s.canRedo():
            s.redo()
            print('ok')
        else:
            print('empty')
        break
else:
    print('not_found')
"""


@mcp.tool()
def sp_undo() -> dict:
    """
    撤销上一步操作。
    通过 SP 原生 undo 栈实现，用户在 SP 按 Ctrl+Z 也能撤销 MCP 操作。
    所有 layerstack API 操作（add/delete/modify）自动推入 SP undo 栈。
    """
    result = sp.call("run_python", {"code": _UNDO_REDO_CODE})
    output = result.get("stdout", "").strip() if isinstance(result, dict) else ""
    if output == "ok":
        return {"ok": True}
    elif output == "empty":
        return {"ok": False, "error": "Nothing to undo"}
    else:
        return {"ok": False, "error": "Undo history not found"}


@mcp.tool()
def sp_redo() -> dict:
    """
    重做上一步被撤销的操作。
    通过 SP 原生 redo 栈实现，用户在 SP 按 Ctrl+Y 也能重做 MCP 操作。
    所有 layerstack API 操作（add/delete/modify）自动推入 SP undo 栈。
    """
    result = sp.call("run_python", {"code": _REDO_CODE})
    output = result.get("stdout", "").strip() if isinstance(result, dict) else ""
    if output == "ok":
        return {"ok": True}
    elif output == "empty":
        return {"ok": False, "error": "Nothing to redo"}
    else:
        return {"ok": False, "error": "Undo history not found"}


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


# ── 入口 ──────────────────────────────────────────────────────────────────────

def main() -> None:
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

    if args.transport == "sse":
        mcp.run(transport="sse", port=args.port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
