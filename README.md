<div align="center">

# 🎨 Substance 3D Painter MCP Server (SP-MCP)

[![Python](https://img.shields.io/badge/python-3.10%2B-blue?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![SP](https://img.shields.io/badge/Substance%20Painter-10.0%2B-ff6b35?style=for-the-badge&logo=adobe&logoColor=white)](https://www.adobe.com/products/substance3d-painter.html)
[![fastmcp](https://img.shields.io/badge/fastmcp-0.9%2B-6366f1?style=for-the-badge)](https://github.com/jlowin/fastmcp)
[![requests](https://img.shields.io/badge/requests-2.31%2B-2ea44f?style=for-the-badge)](https://pypi.org/project/requests/)

*让 AI 成为你的首席材质艺术家。*

本项目为 Substance 3D Painter 实现了一个 **MCP（Model Context Protocol）Server**，使得各大主流的 LLM（如 OpenCode, Claude Code, Cursor 等）能够通过标准化工具直接与 Painter 交互。该项目旨在利用大模型强大的推理与设计能力，自动化驱动 **视觉创作**（如材质设计、皮肤制作、磨损做旧等）工作流。

</div>

---

> [!IMPORTANT]  
> 该项目要求 LLM **同时具备视觉识别（Vision）与工具调用（Tool Calling）能力**，二者缺一不可。材质创作工作流的核心闭环是：AI 截图评估 → 调参 → 再截图验证，因此纯文本模型无法使用。
>
> ✅ **推荐模型**：Claude Sonnet 4/4.5、Claude Opus 4.5+  
> ⚠️ **也可尝试**：Gemini、Qwen、Kimi 等支持 Vision + Tool 的模型（兼容性因客户端而异，需自行测试）

## 🎯 核心能力与工作流

通过本 MCP Server，AI 可以实现以下核心闭环操作：

1. 🔍 **理解当前状态**：读取 Painter 的图层栈结构、纹理集、项目信息。
2. 🧠 **制定修改决策**：分析并推断需要修改的材质参数。
3. 🛠️ **执行操作**：调用工具（如新建图层、添加材质/遮罩、调整通道值、批量操作）。
4. 👁️ **获取视觉反馈**：控制 Painter 截取 3D 视口画面。
5. 🔄 **迭代与确认**：根据截图进行多轮自我评估和修改，直到满意为止。
6. 📦 **烘焙与导出**：烘焙 mesh maps、导出贴图。

## ⚙️ 架构概述

本项目包含两大部分：

*   🔌 **`plugin/sp_bridge/` (SP 内嵌插件)**：作为 Painter 的 Python 插件运行，启动 HTTP Server（端口 `27182`），接收并执行 `substance_painter` API 调用。
*   🌐 **`server/` (MCP Server)**：基于 `FastMCP` 搭建的外部服务，暴露 MCP Tools 给 AI 客户端。

```mermaid
graph LR
    LLM["LLM / MCP Client<br>(stdio 或 SSE)"] <--> Server["server/sp_mcp.py<br>(MCP Tools)"]
    Server <-->|HTTP POST 27182| Bridge["plugin/sp_bridge/bridge.py<br>(HTTP Server + QTimer)"]
    Bridge <-->|主线程轮询| Handlers["plugin/sp_bridge/handlers.py"]
    Handlers <--> SP["Painter 图层栈 / 导出 / 烘焙"]
```

## 🚀 安装与启动

### 环境要求
*   **Substance 3D Painter** 10.0.1+
*   **Python** 3.10+
*   **依赖库**: `fastmcp` (0.9+), `requests` (2.31+)

### 1. 部署 Painter 插件

将 `plugin/sp_bridge/` 文件夹复制到以下路径：
```bash
%USERPROFILE%\Documents\Adobe\Adobe Substance 3D Painter\python\plugins\
```

> **成功标志**：安装完成后启动 Painter，Python Console 会显示：
> `[INFO] sp_bridge: SP Bridge started on port 27182`

### 2. 安装 Python 依赖

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install fastmcp requests
```

### 3. 配置 LLM 客户端

<details>
<summary><b>OpenCode</b></summary>

在 `~/.config/opencode/opencode.jsonc` 中添加：
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
</details>

<details>
<summary><b>Claude Code / Cursor / OpenClaw</b></summary>

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
</details>

<details>
<summary><b>Hermes Agent</b></summary>

在 `~/.hermes/config.yaml` 中添加：
```yaml
mcp_servers:
  substance-painter:
    command: "<Python路径>"
    args: ["<仓库绝对路径>/server/sp_mcp.py"]
```
</details>

### 4. 启动使用

1. 启动 Painter，打开一个项目
2. 确认 Console 显示 Bridge started
3. 启动 LLM 客户端
4. 💬 对话中直接使用：*"帮我看看当前 Painter 的图层结构"*

---

## 🛠️ MCP Tools (94 个 🆕)

> [!TIP]
> 所有图层修改操作（`add_fill_layer`、`set_layer_channel`、`apply_smart_material` 等）自动包裹 `ScopedModification`，**每个 API 调用 = 1 条 undo**。
> 用 `sp_begin_batch` / `sp_end_batch` 可将多个操作再合并为 1 条，方便撤销。

<details>
<summary><b>🔌 连接与项目管理 (4)</b></summary>

| Tool | 说明 |
|------|------|
| `sp_ping` | 检查 bridge 连通性，返回 SP 版本 |
| `sp_get_project_info` | 读取项目名/路径/状态 |
| `sp_save_project` | 保存项目 |
| `sp_run_python` | 【Escape Hatch】在主线程执行任意 Python |
</details>

<details>
<summary><b>📚 图层与纹理集读取 (5)</b></summary>

| Tool | 说明 |
|------|------|
| `sp_get_layer_stack` | 返回当前纹理集的图层树 JSON（含 Group 递归） |
| `sp_get_texture_sets` | 返回所有纹理集及图层结构，支持过滤 |
| `sp_find_layer_by_name` | 跨纹理集按名称搜索图层，返回匹配列表 |
| `sp_get_layer_properties` | 返回图层详细属性 |
| `sp_get_layer_channels` | 返回所有通道的 opacity/blend/source |
</details>

<details>
<summary><b>✏️ 图层与通道写入 (12)</b></summary>

| Tool | 说明 |
|------|------|
| `sp_add_fill_layer` | 新建 Fill Layer（含颜色/通道/混合模式） |
| `sp_add_group_layer` | 新建空分组图层 |
| `sp_add_paint_layer` | 新建绘画图层 |
| `sp_set_layer_property` | 修改图层属性（opacity/visible/name/blend_mode） |
| `sp_set_layer_channel` | 设定通道值（Roughness/Metallic/Height/BaseColor/Normal） |
| `sp_delete_layer` | 删除图层 |
| `sp_duplicate_layer` | 复制图层 |
| `sp_move_layer` | 移动图层到目标上方/下方 |
| `sp_group_layers` | 打包图层进新分组 |
| `sp_ungroup_layer` | 解散分组，子层提升到父级 |
| `sp_add_mask` | 为图层添加遮罩（黑/白背景） |
| `sp_remove_mask` | 移除图层遮罩 |
</details>

<details>
<summary><b>⏪ Undo / Redo 与批量操作 (4)</b></summary>

| Tool | 说明 |
|------|------|
| `sp_undo` | 撤销上一步（通过 SP 原生 QUndoStack） |
| `sp_redo` | 重做（通过 SP 原生 QUndoStack） |
| `sp_begin_batch` | 开始批量操作（基于 ScopedModification） |
| `sp_end_batch` | 结束批量，合并为单条 undo |
</details>

<details>
<summary><b>✨ 材质与效果 (5)</b></summary>

| Tool | 说明 |
|------|------|
| `sp_list_shelf_materials` | 列出可用 Smart Material，支持过滤 |
| `sp_apply_smart_material` | 对指定图层应用 Smart Material |
| `sp_list_materials` | 列出可用普通材质 |
| `sp_apply_material` | 应用普通材质 |
| `sp_add_smart_mask` | 为图层添加程序化遮罩 |
</details>

<details>
<summary><b>📸 视觉反馈与渲染 (10)</b></summary>

| Tool | 说明 |
|------|------|
| `sp_capture_viewport` | 截取 viewport（`"quick"` 迭代 / `"render"` 截当前画面，不自动触发 Iray） |
| `sp_set_camera` | 设置相机位置和视角 |
| `sp_frame_mesh` | 自动适配视图到模型 |
| `sp_set_environment` | 切换 HDRI 环境光 |
| `sp_set_iray_params` | 设置 Iray 参数 |
| `sp_get_iray_params` | 读取当前 Iray 参数 |
| `sp_start_iray_render`| 异步启动 Iray |
| `sp_check_iray_render`| 检查渲染进度 |
| `sp_list_export_presets` | 列出所有可用导出预设 |
| `sp_export_textures` | 导出贴图 |
</details>

<details>
<summary><b>🛠️ 纹理集与 JS API (5)</b></summary>

| Tool | 说明 |
|------|------|
| `sp_set_active_texture_set`| 切换活动纹理集 |
| `sp_set_texture_set_resolution`| 修改纹理集分辨率 |
| `sp_bake_mesh_maps` | **异步**烘焙 mesh maps（AO/Curvature/Normal 等），立即返回；用 `sp_get_bake_status` 轮询，**勿超时重试** |
| `sp_add_texture_set_channel` | 给纹理集添加通道 |
| `sp_remove_texture_set_channel`| 删除纹理集通道 |
</details>

<details>
<summary><b>🖱️ Computer Use (12)</b></summary>

> 通过 Windows API 实现 mini Computer Use，供视觉模型通过截图→坐标映射→鼠标点击/键盘输入驱动 SP UI。
> `sp_window_focus()` 会在 SP 窗口顶部显示红色 "MCP Control Active" 警示条，操作结束后用 `sp_cu_unlock()` 清除。
>
> ⚠️ **安全警告**：`sp_mouse_*` / `sp_key_send` / `sp_shortcut` 会**真实操控你的物理鼠标和键盘**。
> 调用这些工具时，请勿同时使用电脑做其他工作（光标会被抢占），并确保 SP 窗口处于前台（先调 `sp_window_focus`）。
> 这些操作可能误触其他窗口或对话框——仅在你能随时抢回控制权时使用。

| Tool | 说明 |
|------|------|
| `sp_window_info` | 返回窗口位置/尺寸/状态，配合截图做坐标映射 |
| `sp_window_grab` | 截取 SP 窗口或指定区域 → base64 PNG |
| `sp_window_focus` | 聚焦 SP 窗口 + 显示红色警示条 |
| `sp_cu_unlock` | 解除锁定 + 隐藏警示条 |
| `sp_cu_banner_text` | 更新警示条文字 |
| `sp_cu_warning` | 将警示条切换为黄色等待状态（处理超时） |
| `sp_mouse_move` | 移动鼠标（屏幕/窗口相对坐标） |
| `sp_mouse_click` | 点击（左/右/中，单击/双击） |
| `sp_mouse_scroll` | 滚轮（±120） |
| `sp_mouse_drag` | 拖拽 A→B |
| `sp_key_send` | 键盘输入（单键/组合键/打字） |
| `sp_shortcut` | 预定义快捷键封装（save/undo/frame_all 等 26 种） |
</details>

<details>
<summary><b>✨ 效果节点 (9)</b></summary>

| Tool | 说明 |
|------|------|
| `sp_add_filter_effect` | 添加 Filter 效果（可选指定 filter 资源） |
| `sp_add_generator_effect` | 添加 Generator 效果（可选指定 generator 资源） |
| `sp_add_levels_effect` | 添加 Levels 色阶调整效果 |
| `sp_add_compare_mask_effect` | 添加 Compare Mask 通道比较遮罩效果 |
| `sp_add_color_selection_effect` | 添加 Color Selection ID 遮罩效果 |
| `sp_add_anchor_point_effect` | 添加 Anchor Point 锚点效果 |
| `sp_get_effect_parameters` | 读取效果节点参数 |
| `sp_get_selected_nodes` | 获取当前选中节点列表 |
| `sp_set_selected_nodes` | 设置选中节点 |
</details>

<details>
<summary><b>🔥 烘焙 API (7)</b></summary>

> 完整 Python 烘焙参数控制，替代 JS `alg.baking.bake()`。
> `bake_mesh_maps` / `bake_texture_set` 均为异步，立即返回——**不要因延迟/超时重试**，
> 否则会重复触发烘焙。用 `sp_get_bake_status` 轮询确认完成。

| Tool | 说明 |
|------|------|
| `sp_get_baking_parameters` | 读取纹理集完整烘焙参数（common + 各 baker） |
| `sp_set_baking_parameters` | 设置烘焙参数（分辨率/高模路径等） |
| `sp_bake_texture_set` | 异步启动纹理集烘焙 |
| `sp_get_baking_state` | 获取烘焙状态（启用/bakers/UV tiles/链接） |
| `sp_set_baking_state` | 设置烘焙状态（启用纹理集/bakers/曲率方法） |
| `sp_get_bake_status` | 轮询 `sp_bake_mesh_maps` 的异步状态（phase/progress/status） |
| `sp_cancel_bake` | 取消进行中的异步烘焙（基于 StopSource.request_stop） |
</details>

<details>
<summary><b>📁 项目生命周期 (7)</b></summary>

| Tool | 说明 |
|------|------|
| `sp_create_project` | 创建新项目（网格/设置/工作流/法线格式） |
| `sp_open_project` | 打开已有 .spp 项目 |
| `sp_close_project` | 关闭当前项目（不保存） |
| `sp_reload_mesh` | 异步重载项目网格 |
| `sp_get_project_metadata` | 读取项目持久化元数据 |
| `sp_set_project_metadata` | 写入项目持久化元数据 |
| `sp_list_project_metadata` | 列出 context 下所有元数据键 |
</details>

<details>
<summary><b>🔍 资源发现 (1)</b></summary>

| Tool | 说明 |
|------|------|
| `sp_list_resources_by_usage` | 按用途类型列出资源（filter/generator/substance 等） |
</details>

<details>
<summary><b>🎨 程序化源控制 (7)</b></summary>

| Tool | 说明 |
|------|------|
| `sp_get_source_info` | 获取填充图层/效果的源信息 |
| `sp_get_substance_parameters` | 读取程序化源参数值 |
| `sp_set_substance_parameters` | 修改程序化源参数值 |
| `sp_get_substance_presets` | 列出程序化源可用预设 |
| `sp_apply_substance_preset` | 应用指定预设 |
| `sp_get_source_outputs` | 获取源输出映射信息 |
| `sp_set_source_output` | 切换源活动输出 |
</details>

<details>
<summary><b>📷 相机与显示 (6)</b></summary>

| Tool | 说明 |
|------|------|
| `sp_get_camera` | 读取主相机完整状态 |
| `sp_get_tone_mapping` | 获取色调映射函数 |
| `sp_set_tone_mapping` | 设置色调映射函数 |
| `sp_get_color_lut` | 获取色彩 LUT 配置 |
| `sp_set_color_lut` | 设置色彩 LUT 配置 |
| `sp_get_scene_bounding_box` | 获取场景包围盒 |
</details>

## ⚠️ 已知限制

*   **视口状态**：`sp_capture_viewport` 需要项目打开且 3D viewport 可见。
*   **版本限制**：Smart Material API 需要 SP 10.0+，9.x 版本上相关 tool 会返回明确错误。
*   **ID 缓存**：Layer ID 在 Painter 重启后会变化，请勿跨 session 缓存。
*   **API 替代**：
    *   `schedule_on_ui_thread` 在 SP 10.x 不存在，已用 `QTimer` 轮询方案替代。
    *   `alg.ui.clickButton` 在 SP 10.0.1 有内部 bug（`findChild of undefined`），请使用 Computer Use 的鼠标点击绕过此限制。
*   **窗口前台**：Computer Use 鼠标/键盘输入受 Windows 前台窗口限制，操作前务必调用 `sp_window_focus()`。

## 🔧 调试与排错

| 问题 | 常见排查方案 |
|------|------|
| **Bridge 连接失败** | 检查 Painter 是否启动、Python Console 中插件是否加载成功 |
| **Timeout 异常** | Iray 渲染中会阻塞主线程，等待完成后重试 |
| **插件未加载** | 检查 Python Console 输出报错信息 |
| **查看运行日志** | `%USERPROFILE%\sp_bridge.log` |
| **代码热重载** | `import importlib, sp_bridge.handlers; importlib.reload(sp_bridge.handlers)` |
| **CU 警示条不消失** | 手动调用 `sp_cu_unlock()` 或是重启 Painter |

> 📚 详情及进阶开发指南可参阅代码库内的 [AGENTS.md](./AGENTS.md) 和 [PHASES.md](./PHASES.md)。
