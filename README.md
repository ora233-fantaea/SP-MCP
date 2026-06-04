# Substance 3D Painter MCP Server (SP-MCP)

本项目为 Substance 3D Painter 实现了一个 MCP（Model Context Protocol）Server，使得各大主流的 LLM（如 OpenCode, Claude Code, Cursor 等）能够通过标准化工具直接与 Painter 交互。该项目旨在利用大模型强大的推理与设计能力，自动化驱动 **视觉创作**（如材质设计、皮肤制作、磨损做旧等）工作流。

## 🎯 核心能力与工作流

通过本 MCP Server，AI 可以实现以下核心闭环操作：
1. **理解当前状态**：读取 Painter 的图层栈结构、纹理集、项目信息。
2. **制定修改决策**：分析并推断需要修改的材质参数。
3. **执行操作**：调用工具（如新建图层、添加材质/遮罩、调整通道值、批量操作）。
4. **获取视觉反馈**：控制 Painter 截取 3D 视口画面。
5. **迭代与确认**：根据截图进行多轮自我评估和修改，直到满意为止。
6. **烘焙与导出**：烘焙 mesh maps、导出贴图。

## ⚙️ 架构概述

本项目包含三大部分：

*   **`plugin/` (SP 内嵌插件)**：作为 Painter 的 Python 插件运行，启动 HTTP Server（端口 `27182`），接收并执行 `substance_painter` API 调用。
*   **`server/` (MCP Server)**：基于 `FastMCP` 搭建的外部服务，暴露 MCP Tools 给 AI 客户端。
*   **`plugin/js/` (QML 插件)**：SP 的 QML 插件，提供 UI 菜单项（Tools 菜单）。

```
LLM / MCP Client
      ↕  stdio 或 SSE
  server/sp_mcp.py          MCP Tools 定义（40 个）
      ↕  HTTP POST localhost:27182
  plugin/bridge.py           HTTP Server + QTimer 调度
      ↕  QTimer 轮询队列（主线程执行）
  plugin/handlers.py         substance_painter.* API 调用
      ↕
  Painter 图层栈 / 导出 / 烘焙 / JS API
```

## 🚀 安装与启动

### 环境要求
*   Substance 3D Painter 10.0.1+
*   Python 3.10+
*   依赖库：`fastmcp` (0.9+), `requests` (2.31+)

### 1. 部署 Painter 插件

**Python 插件（必需）：**
将 `plugin/` 文件夹内容复制到：
```
%USERPROFILE%\Documents\Adobe\Adobe Substance 3D Painter\python\plugins\sp_bridge\
```

**QML 插件（可选）：**
将 `plugin/js/sp-bake-maps/` 和 `plugin/js/sp-textureset-channels/` 复制到：
```
%USERPROFILE%\Documents\Adobe\Adobe Substance 3D Painter\plugins\
```

安装完成后启动 Painter，Python Console 显示：
```
[INFO] sp_bridge: SP Bridge started on port 27182
[插件 - sp-bake-maps] [SP MCP] Bake Maps plugin loaded
[插件 - sp-textureset-channe...] [SP MCP] TextureSet Channels plugin loaded
```

### 2. 安装 Python 依赖

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install fastmcp requests
```

### 3. 配置 LLM 客户端

**OpenCode** (`~/.config/opencode/opencode.jsonc`):
```json
{
  "mcp": {
    "substance-painter": {
      "type": "local",
      "command": ["<Python路径>", "<仓库绝对路径>/server/sp_mcp.py"],
      "enabled": true,
      "timeout": 30000
    }
  }
}
```

**Claude Code / Cursor:**
```json
{
  "mcpServers": {
    "substance-painter": {
      "command": "<Python路径>",
      "args": ["<仓库绝对路径>/server/sp_mcp.py"]
    }
  }
}
```

### 4. 启动使用

```
1. 启动 Painter，打开一个项目
2. 确认 Console 显示 Bridge started
3. 启动 LLM 客户端
4. 对话中直接使用："帮我看看当前 Painter 的图层结构"
```

## 🛠️ MCP Tools（40 个）

### 连接

| Tool | 说明 |
|------|------|
| `sp_ping` | 检查 bridge 连通性，返回 SP 版本 |

### 图层读取

| Tool | 说明 |
|------|------|
| `sp_get_layer_stack` | 返回当前纹理集的图层树 JSON（含 Group 递归） |
| `sp_get_texture_sets(filter)` | 返回所有纹理集及图层结构，支持过滤 |
| `sp_get_layer_properties(layer_id)` | 返回图层详细属性 |
| `sp_get_layer_channels(layer_id)` | 返回所有通道的 opacity/blend/source |

### 图层写入

| Tool | 说明 |
|------|------|
| `sp_add_fill_layer(name, ...)` | 新建 Fill Layer（含颜色/通道/混合模式） |
| `sp_add_group_layer(name)` | 新建空分组图层 |
| `sp_add_paint_layer(name)` | 新建绘画图层 |
| `sp_set_layer_property(layer_id, prop, value)` | 修改图层属性（opacity/visible/name/blend_mode） |
| `sp_set_layer_channel(layer_id, channel, value)` | 设定通道值（Roughness/Metallic/Height/BaseColor） |
| `sp_delete_layer(layer_id)` | 删除图层 |
| `sp_duplicate_layer(layer_id)` | 复制图层 |

### Smart Material / 普通材质

| Tool | 说明 |
|------|------|
| `sp_list_shelf_materials(filter)` | 列出 Smart Material（122 个） |
| `sp_apply_smart_material(layer_id, name)` | 应用 Smart Material |
| `sp_add_smart_mask(layer_id, mask_name)` | 添加程序化遮罩（66 个可用） |
| `sp_list_materials(filter)` | 列出普通材质（917+ 个 SUBSTANCE 类型） |
| `sp_apply_material(layer_id, name)` | 应用普通材质到所有通道 |

### 批量 Undo

| Tool | 说明 |
|------|------|
| `sp_begin_batch(name)` | 开始批量操作（基于 ScopedModification） |
| `sp_end_batch()` | 结束批量，合并为单条 undo |

### Texture Set 管理

| Tool | 说明 |
|------|------|
| `sp_set_active_texture_set(name)` | 切换活动纹理集 |
| `sp_set_texture_set_resolution(w, h)` | 修改纹理集分辨率 |

### 项目

| Tool | 说明 |
|------|------|
| `sp_get_project_info()` | 读取项目名/路径/状态 |
| `sp_save_project()` | 保存项目 |

### 视觉反馈

| Tool | 说明 |
|------|------|
| `sp_capture_viewport(mode)` | 截取 viewport（`"quick"` 迭代 / `"render"` Iray） |
| `sp_set_camera(x,y,z, tx,ty,tz, fov)` | 设置相机位置和视角 |
| `sp_set_environment(preset)` | 切换 HDRI 环境光 |

### Iray 渲染

| Tool | 说明 |
|------|------|
| `sp_set_iray_params(samples, time, w, h)` | 设置 Iray 参数 |
| `sp_start_iray_render()` | 异步启动 Iray |
| `sp_check_iray_render()` | 检查渲染进度 |

### 导出

| Tool | 说明 |
|------|------|
| `sp_export_textures(preset, output_dir)` | 导出贴图 |

### JS API（通过 alg）

| Tool | 说明 |
|------|------|
| `sp_bake_mesh_maps(texture_set_name)` | 烘焙 mesh maps（AO/Curvature/Normal 等） |
| `sp_add_texture_set_channel(ts, id, fmt, label)` | 给纹理集添加通道 |
| `sp_remove_texture_set_channel(ts, id)` | 删除纹理集通道 |

### Escape Hatch

| Tool | 说明 |
|------|------|
| `sp_run_python(code)` | 在主线程执行任意 Python |

## ⚠️ 已知限制

以下操作在 SP 10.x 中无 Python API，需要在 Painter UI 中手动完成：

| 操作 | 替代方案 |
|------|---------|
| Undo / Redo | `Ctrl+Z` / `Ctrl+Y` |
| 移动图层 | UI 拖拽 |
| 分组图层 | `Ctrl+G` |
| 解散分组 | `Ctrl+Shift+G` |
| 自动适配视图 | viewport 快捷键 `F` |

## 🤝 SP2VTF 集成

导出后可调用 SP2VTF 转换为 Source 引擎格式：
```bash
python sp2vtf/convert.py --input ./export/gun_skin_v1 --output ./vtf/
```

## 🔧 调试与排错

| 问题 | 排查 |
|------|------|
| Bridge 连接失败 | 检查 Painter 是否启动、插件是否加载 |
| Timeout | Iray 渲染中会阻塞，等待完成后重试 |
| 插件未加载 | 检查 Python Console 输出 |
| 日志文件 | `%USERPROFILE%\sp_bridge.log` |
| 热重载 | `import importlib, sp_bridge.handlers; importlib.reload(sp_bridge.handlers)` |

详见 [AGENTS.md](./AGENTS.md) 和 [PHASES.md](./PHASES.md)。

---
*本项目包含为 AI 开发设计的专用工作流设定与提示词机制，详情可参阅代码库内的 [AGENTS.md](./AGENTS.md) 与 [PHASES.md](./PHASES.md)。*
