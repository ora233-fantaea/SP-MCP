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
    返回完整图层树 JSON。
    每个节点包含 id、name、type（FILL/PAINT/GROUP）、enabled、opacity。
    GROUP 类型包含 children 列表（递归）。
    修改图层前必须调用，获取准确的 layer id。
    注意：layer id 在 Painter 重启后会变化，不要跨 session 缓存。
    """
    return sp.call("get_layer_stack")


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
