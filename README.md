# Substance 3D Painter MCP Server (SP-MCP)

本项目为 Substance 3D Painter 实现了一个 MCP（Model Context Protocol）Server，使得各大主流的 LLM（如 OpenCode, Claude Code, Cursor 等）能够通过标准化工具直接与 Painter 交互。该项目旨在利用大模型强大的推理与设计能力，自动化驱动 **视觉创作**（如材质设计、皮肤制作、磨损做旧等）工作流。

## 🎯 核心能力与工作流

通过本 MCP Server，AI 可以实现以下核心闭环操作：
1. **理解当前状态**：读取 Painter 的图层栈结构。
2. **制定修改决策**：分析并推断需要修改的材质参数。
3. **执行操作**：调用工具（如新建图层、添加智能材质/遮罩、调整属性）。
4. **获取视觉反馈**：控制 Painter 截取 3D 视口画面。
5. **迭代与确认**：根据截图进行多轮自我评估和修改，直到满意为止，最后可以进行高质量渲染并导出贴图。

## ⚙️ 架构概述

本项目包含两大部分，通过本地 HTTP 协议进行通信：

*   **`plugin/` (SP 内嵌插件)**：作为 Painter 的插件运行，启动在主线程轮询执行的 HTTP Server（默认端口 `27182`）。接收并实际执行针对 `substance_painter` 的 API 调用。
*   **`server/` (MCP Server)**：基于 `FastMCP` 搭建的外部独立服务。负责暴露 MCP 工具（Tools）给各种支持 MCP 协议的 AI 客户端，并将 AI 的指令翻译为对插件端发起的请求。

## 🚀 安装与启动

### 环境要求
*   Substance 3D Painter 10.0.1+
*   Python 3.10+
*   依赖库：`fastmcp` (0.9+), `requests` (2.31+)

### 1. 部署 Painter 插件
将本仓库下的 `plugin` 文件夹内容复制到您的 Substance 3D Painter 插件目录下：
*   **Windows 默认路径**:
    ```text
    %USERPROFILE%\Documents\Adobe\Adobe Substance 3D Painter\python\plugins\sp_bridge\
    ```
安装完成后，启动 Substance 3D Painter。如果安装成功，软件内置的 Python Console 会输出以下日志：
```text
[INFO] sp_bridge: SP Bridge started on port 27182
```
*(提示：插件的详细运行日志会保存在 `%USERPROFILE%\sp_bridge.log`)*

### 2. 安装 Python 依赖
克隆本仓库后，在项目根目录安装依赖：

```powershell
# 方式 A：使用 venv（推荐）
python -m venv .venv
.venv\Scripts\activate
pip install fastmcp requests

# 方式 B：直接安装到全局 Python
pip install fastmcp requests
```

### 3. 配置 LLM 客户端

#### OpenCode
在 `~/.config/opencode/opencode.jsonc` 中添加：

```json
{
  "mcp": {
    "substance-painter": {
      "type": "local",
      "command": ["<你的Python路径>", "<本仓库绝对路径>/server/sp_mcp.py"],
      "enabled": true,
      "timeout": 30000
    }
  }
}
```

**注意**：`command` 中的路径必须是绝对路径。Python 路径可通过 `where python` 或 `which python3` 获取。

#### Claude Code / Cursor / Hermes Agent 等
使用标准 MCP stdio 协议，配置格式类似：
```json
{
  "mcpServers": {
    "substance-painter": {
      "command": "<Python路径>",
      "args": ["<本仓库绝对路径>/server/sp_mcp.py"]
    }
  }
}
```

### 4. 启动使用

```
1. 启动 Painter，打开一个项目
2. 确认 Console 显示 [INFO] sp_bridge: SP Bridge started on port 27182
3. 启动 LLM 客户端（OpenCode / Claude Code / Cursor 等）
4. 在对话中直接使用，例如："帮我看看当前 Painter 的图层结构"
```

## 🛠️ MCP Tools (全部 14 个工具)

*   **连接与读取**:
    *   `sp_ping`: 检查 Bridge 连通性及版本状态。任何操作前必须先调用。
    *   `sp_get_layer_stack`: 返回完整的图层树 JSON（含 Group 子节点递归）。
    *   `sp_get_layer_properties`: 获取指定图层的详细属性（opacity、blend_mode 等）。
    *   `sp_list_shelf_materials`: 列出可用 Smart Material，支持关键词过滤。
    *   `sp_capture_viewport`: 截取当前 3D 视口为 Base64 PNG（`mode="quick"` 快速截屏 / `mode="render"` Iray 渲染后截图）。
*   **图层操作**:
    *   `sp_add_fill_layer`: 在图层栈顶部新建填充图层（含颜色、通道、混合模式）。
    *   `sp_set_layer_property`: 修改指定图层的属性（visible、opacity、name、blend_mode）。
    *   `sp_apply_smart_material`: 对指定图层应用 Shelf 中的 Smart Material。
    *   `sp_add_smart_mask`: 为图层添加程序化遮罩（Edge Wear / Dirt / Rust 等）。
*   **Iray 渲染**:
    *   `sp_set_iray_params`: 设置 Iray 渲染质量参数（采样数、时间、分辨率）。
    *   `sp_start_iray_render`: 异步启动 Iray 渲染（不阻塞 HTTP）。
    *   `sp_check_iray_render`: 轮询 Iray 渲染进度（iterations / time）。
*   **导出**:
    *   `sp_export_textures`: 触发贴图一键导出。
*   **调试**:
    *   `sp_run_python`: 在 Painter 主线程执行任意 Python 代码（escape hatch）。

## 🤝 后续集成扩展
结合 **SP2VTF** 工具（见项目规划），可以将导出的贴图一键转换为 Source 引擎（如 L4D2、CS 等游戏）兼容的 VTF 格式，实现一站式的自定义皮肤制作工作流。

## 🔧 调试与排错

*   Bridge 连接失败 → 检查 Painter 是否启动、插件是否加载
*   日志文件 → `%USERPROFILE%\sp_bridge.log`
*   热重载（不重启 Painter）：在 Python Console 执行 `import importlib, sp_bridge.handlers; importlib.reload(sp_bridge.handlers)`
*   详见 [AGENTS.md](./AGENTS.md) 中的调试章节

---
*本项目包含为 AI 开发设计的专用工作流设定与提示词机制，详情可参阅代码库内的 [AGENTS.md](./AGENTS.md) 与 [PHASES.md](./PHASES.md)。*
