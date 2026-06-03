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

### 2. 部署 MCP Server
克隆本项目后，在项目根目录创建并激活虚拟环境，然后安装依赖并启动 MCP 服务：

```powershell
# 创建虚拟环境并激活
python -m venv .venv
.venv\Scripts\activate

# 安装依赖
pip install fastmcp requests

# 启动 Server
python server/sp_mcp.py
```

### 3. 配置客户端 (以 OpenCode 为例)
在客户端的配置文件（如 `%APPDATA%\opencode\config.json`）中添加 MCP Server 节点：
```json
{
  "mcp": {
    "substance-painter": {
      "type": "local",
      "command": ["C:\\<项目绝对路径>\\.venv\\Scripts\\python.exe", "server/sp_mcp.py"]
    }
  }
}
```

## 🛠️ MCP Tools (主要工具集)

*   **读取类**:
    *   `sp_ping`: 检查 Bridge 连通性及版本状态。
    *   `sp_get_layer_stack`: 返回完整的图层树 JSON。
    *   `sp_get_layer_properties`: 获取指定图层的详细属性。
    *   `sp_capture_viewport`: 截取当前 3D 视口为 Base64 PNG（支持快速截屏模式与 Iray 渲染模式）。
*   **操作类**:
    *   `sp_add_fill_layer`: 在图层栈顶部新建填充图层。
    *   `sp_set_layer_property`: 修改指定图层的属性（可见性、不透明度、名称、混合模式等）。
    *   `sp_apply_smart_material`: 在图层中应用智能材质（Smart Material）。
    *   `sp_add_smart_mask`: 为图层添加程序化遮罩（Smart Mask）。
*   **导出类**:
    *   `sp_export_textures`: 触发贴图一键导出。

## 🤝 后续集成扩展
结合 **SP2VTF** 工具（见项目规划），可以将导出的贴图一键转换为 Source 引擎（如 L4D2、CS 等游戏）兼容的 VTF 格式，实现一站式的自定义皮肤制作工作流。

---
*本项目包含为 AI 开发设计的专用工作流设定与提示词机制，详情可参阅代码库内的 [AGENTS.md](./AGENTS.md) 与 [PHASES.md](./PHASES.md)。*
