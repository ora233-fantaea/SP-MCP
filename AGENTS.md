# SP MCP — AGENTS.md

## 项目概述

本项目为 Substance 3D Painter 实现一个 MCP（Model Context Protocol）server，
使 LLM（OpenCode 或其他支持 MCP 的客户端）能够通过结构化工具调用控制
Painter 的图层栈，并最终驱动 **视觉创作**（材质设计、皮肤制作等）工作流。

核心设计目标：
- LLM 读取图层树 → 推理 → 修改材质参数 → 截图确认 → 迭代
- 兼容所有支持 MCP stdio / SSE 的客户端（OpenCode、Claude Code、Cursor 等）
- Plugin 侧只用 Python 标准库 + PySide2（SP 内置），不依赖外部 pip 包

**开发进度和阶段任务见 → [PHASES.md](./PHASES.md)**
每次开始新任务前先读 PHASES.md，找到当前未完成的 Phase 继续执行。

---

## 已知 API 事实（重要，勿忽略）

Phase 2 探索发现以下与文档/预期不符的实际 API，所有代码必须遵循：

| 原假设 | 实际 API |
|---|---|
| `substance_painter.layers` | `substance_painter.layerstack` |
| `substance_painter.__version__` | `substance_painter.application.version()` → `"10.0.1"` |
| `is_enabled()` / `set_enabled()` | `is_visible()` / `set_visible()` |
| `get_child_layers()` | `node.sub_layers()` (GroupLayerNode) |
| `textureset.name` 是属性 | `ts.name()` 是方法，返回 `str` |
| `textureset.get_resolution` | `ts.get_resolution()` 返回 `Resolution(width, height)` |
| `type(node).__name__` | `"FillLayerNode"` / `"GroupLayerNode"` / `"PaintLayerNode"` |
| `get_root_layer_nodes()` 返回 int ID | 返回 `List[Node]` 节点对象 |
| 节点类型 `node.get_type().name` | `type(node).__name__` → `"FillLayerNode"` / `"GroupLayerNode"` |
| `get_opacity()` 无参数 | `get_opacity(ChannelType.BaseColor)` 需要 ChannelType |
| 类型枚举 `"FILL"` / `"GROUP"` | `"FillLayerNode"` / `"GroupLayerNode"` |
| Smart Material 用 `layers` 模块 | `resource.search()` + `ls.insert_smart_material()` |
| Smart Mask 直接插入 | 需先 `node.add_mask(White)` 再 `insert_smart_mask()` |
| `schedule_on_ui_thread` 存在 | 不存在，用 QTimer 轮询队列 |
| `substance_painter.camera` | 不存在，相机 API 在 `substance_painter.display.Camera` |
| `substance_painter.environment` | 不存在，环境 API 在 `substance_painter.display.set_environment_resource()` |
| Scalar 通道用 `ls.Color` | 必须用 `colormanagement.Color(v,v,v)` |
| `node.get_source()` 返回 Color | 返回 `SourceUniformColor`，需 `.get_color().value_raw` 取值 |
| `move_node()` / `duplicate_node()` | SP 10.x 不存在 `move_node`。用 `_clone_node`(delete+re-insert 工作流) 实现 move/group/ungroup |
| `get_node_by_uid()` / `get_parent()` / `get_scene_bounding_box()` | 实际存在！`ls.get_node_by_uid(uid)` 按 int UID 查找，`node.get_parent()` 返回父节点，`project.get_scene_bounding_box()` 返回 BoundingBox(center, dimensions, radius) |
| `frame_mesh` 无 API | 用 `project.get_scene_bounding_box()` + `display.Camera` 计算实现 |
| `group_layers` 无 API | 用 `insert_group` + `InsertPosition.inside_node(group, NodeStack.Substack)` + `_clone_node` 实现 |
| `substance_painter.undo` | 不存在。用 SP 原生 QUndoStack（`QUndoView("history").stack()` 的 `undo()`/`redo()`），handler 自动包裹 `ScopedModification` |
| `ScopedModification` 只能 `with` | 支持手动 `__enter__()` / `__exit__()` 跨 HTTP 调用 |
| 每个 layer API 调用生成多条 undo | 每个 handler 自动包裹 `_auto_batch("操作名")`，1 个 API 调用 = 1 条 undo |
| `substance_painter.js` | JS API 入口，`js.evaluate("alg.xxx")` 调用 |
| Baking 用 Python API | 不存在，用 `js.evaluate("alg.baking.bake(name)")` |
| Texture Set 通道管理 | Python API 不完整，用 `js.evaluate("alg.texturesets.addChannel(...)")` |
| `alg.ui.clickButton` | 存在但有 `findChild` 错误（2026-06 现场复测确认 SP 10.0.1 bug），用 Computer Use 鼠标点击替代 |

---

## 仓库结构

```
sp-mcp/
├── plugin/
│   └── sp_bridge/              # 装入 Painter 的嵌入式插件
│       ├── __init__.py             # 插件入口：start_plugin / close_plugin
│       ├── bridge.py               # HTTP server（独立线程）+ QTimer 轮询队列调度
│       └── handlers.py             # substance_painter.* API 的实际调用（_REGISTRY: 92 方法）
├── server/                    # 外部 MCP 进程（venv 运行）
│   ├── sp_mcp.py                   # FastMCP server，暴露 92 个 MCP tools
│   ├── client.py                   # 对 plugin HTTP bridge 的封装（requests）
│   └── pidlock.py                  # 单实例 PID 锁（防止重复启动 server）
├── tests/
│   ├── conftest.py                 # substance_painter mock 注入
│   ├── test_handlers_mock.py       # handler mock 测试，不需要 Painter
│   ├── test_server_tools.py        # server tool 测试，含 integration
│   └── test_pidlock.py             # PID 锁测试（依赖 wmic，沙箱内可能 skip/fail）
├── .opencode/skills/          # 16 个项目专属 skill（LLM 操作参考）
├── AGENTS.md                  # 本文件，每次 session 必读
├── PHASES.md                  # 开发阶段规划，任务来源
├── mcp.json / .mcp.json       # MCP server 描述
└── pyproject.toml
```

### Plugin 安装路径（Windows）

```
%USERPROFILE%\Documents\Adobe\Adobe Substance 3D Painter\python\plugins\sp_bridge\
```

Plugin 加载成功后，SP Python Console 输出：
```
[INFO] sp_bridge: SP Bridge started on port 27182
```
日志文件：`%USERPROFILE%\sp_bridge.log`

---

## 架构

```
LLM / MCP Client
      ↕  stdio 或 SSE
  server/sp_mcp.py          外部进程，FastMCP，tool 定义
      ↕  HTTP POST localhost:27182
  plugin/sp_bridge/bridge.py          Painter 内嵌 Python，HTTP server 线程
      ↕  QTimer 轮询队列（每 50ms，主线程执行）
  plugin/sp_bridge/handlers.py        主线程执行，substance_painter.* API
      ↕
  Painter 图层栈 / 导出系统
```

**关键约束：** `substance_painter.*` 的所有 API 必须在 Painter 主线程执行。
bridge.py 用 `queue.Queue` + `QTimer`（50ms 轮询）实现跨线程调度，
HTTP handler 用 `threading.Event` 阻塞等待结果（timeout 10s）。

注意：`substance_painter.ui.schedule_on_ui_thread()` 在 SP 10.x 不存在，
不要使用。跨线程调度统一走 `_task_queue` + `QTimer` 方案。

---

## MCP Tools 参考

### 读取类

**`sp_ping`**
检查 bridge 连通性。应在任何操作序列开始前调用。
```
返回: {"status": "ok", "sp_version": "10.0.1", "smart_api": true}
```

**`sp_get_layer_stack`**
返回当前活动纹理集的完整图层树 JSON。
需要 Painter 里有打开的项目，否则报错。
```
返回: [{"id": "...", "name": "Metal_Base", "type": "FillLayer", "visible": true}, ...]
```

**`sp_get_texture_sets(filter="")`**
返回所有纹理集及其图层结构，支持名称过滤。
需要打开项目且有纹理集。
```
返回: [{"id": "249", "name": "att_ammo_50b", "resolution": "4096x4096", "layers": [...]}, ...]
```

**`sp_get_layer_properties(layer_id)`**
返回指定图层的详细属性。

**`sp_capture_viewport(mode="quick")`**
截取当前 3D viewport 为 PNG，以 base64 返回。
**这是视觉创作迭代的核心工具**——每次批量修改后必须调用。
```
mode="quick"   Qt grab，毫秒级，迭代用
mode="render"  截当前 viewport（不自动触发 Iray；需先 start_iray_render + 轮询 check_iray_render）
返回: {"image": "<base64 PNG>", "width": int, "height": int}
```

### 写入类

**`sp_add_fill_layer(name, channel, color_hex, opacity, blend_mode)`**
在图层栈顶部新建 Fill Layer。
opacity 第一次建议 0.3–0.5，截图确认后再调整。

**`sp_set_layer_property(layer_id, prop, value)`**
prop 可选值：`opacity` / `visible` / `name` / `blend_mode`

**`sp_apply_smart_material(layer_id, material_name)`**
应用 Shelf 中的 Smart Material。需要 SP 10.0+。

**`sp_add_smart_mask(layer_id, mask_name)`**
添加程序化遮罩。常用值：`"Edge Wear"` / `"Dirt"` / `"Grunge Scratches"` / `"Rust"`

**`sp_list_shelf_materials(filter)`**
列出可用 Smart Material，支持关键词过滤。

**`sp_list_materials(filter)`** — 列出普通材质（SUBSTANCE 类型），支持关键词过滤。

**`sp_apply_material(layer_id, material_name)`** — 将普通材质应用到图层的所有通道。

**`sp_export_textures(preset, output_dir)`**
触发贴图导出，返回导出文件路径列表。

**`sp_run_python(code)`**
在主线程执行任意 Python 代码。
**仅作 escape hatch，优先用具体 tool。**

### Iray 渲染

**`sp_set_iray_params(max_samples, max_time, width, height)`**
设置 Iray 渲染参数。通过 UI widget 控制。

**`sp_start_iray_render()`**
异步启动 Iray 渲染（QTimer.singleShot，不阻塞 HTTP）。

**`sp_check_iray_render()`**
检查 Iray 渲染状态，返回 iterations 和 time。

### Phase 6 — 图层基础 + 通道

**`sp_delete_layer(layer_id)`**
删除指定图层。

**`sp_add_group_layer(name)`**
新建空分组图层。

**`sp_add_paint_layer(name)`**
新建绘画图层（PaintLayerNode）。

**`sp_undo()` / `sp_redo()`**
撤销 / 重做上一步操作。
**通过 SP 原生 undo 栈实现**，用户在 SP 按 Ctrl+Z 也能撤销 MCP 操作。
所有 layerstack API 操作（add/delete/modify）自动推入 SP undo 栈。

**`sp_set_layer_channel(layer_id, channel, value)`**
为指定通道设定数值。channel: `"Roughness"` / `"Metallic"` / `"Height"` / `"BaseColor"`。
非 BaseColor 通道 value 为 float (0.0–1.0)，BaseColor 为 hex color。

**`sp_get_layer_channels(layer_id)`**
返回所有通道的 opacity、blend_mode、source 值。

### Phase 7 — 图层高级 + TextureSet + 项目 + 相机

**`sp_duplicate_layer(layer_id)`**
复制图层，新图层在原图层上方。

**`sp_move_layer(layer_id, target_id, position)`**
移动图层到目标图层上方或下方。position: `"above"` / `"below"`。
**通过 delete+re-insert 工作流实现。**

**`sp_group_layers(layer_ids)`**
将多个图层打包进新分组。
**通过 `insert_group` + `DeletePosition.inside_node(Substack)` 实现。**

**`sp_ungroup_layer(layer_id)`**
解散分组，子层提升到父级。
**通过递归子节点 → re-insert → delete group 实现。**

**`sp_frame_mesh()`**
自动适配视图到模型。
**通过 `project.get_scene_bounding_box()` 计算实现。**

**`sp_set_environment(preset)`**
切换 HDRI 环境光预设。

**`sp_set_active_texture_set(name)`** — 切换当前操作的活动纹理集。

**`sp_set_texture_set_resolution(width, height)`** — 调整活动纹理集分辨率。

**`sp_get_project_info()`** — 读取项目信息（路径/纹理集/分辨率等）。

**`sp_save_project()`** — 保存当前项目。

**`sp_set_camera(position?, rotation?, fov?, target?)`** — 设置相机位置/旋转/FOV，或朝向目标点。

### Phase 8 — 批量 Undo

**`sp_begin_batch(name)`**
开始批量操作。后续 layer 操作将合并为单条 undo。
基于 `layerstack.ScopedModification`，用户在 SP 按 Ctrl+Z 一次撤销整批操作。

**`sp_end_batch()`**
结束批量操作，合并为单条 undo。

**使用示例：**
```
sp_begin_batch("Apply Rust Effect")
  sp_add_fill_layer("Rust_Base")
  sp_set_layer_channel("xxx", "Roughness", 0.8)
  sp_add_smart_mask("xxx", "Edge Wear")
sp_end_batch()
→ 用户按 Ctrl+Z 一次撤销全部 3 个操作
```

### Phase 9 — JS API 集成

通过 `sp.js.evaluate()` 调用 SP 的 `alg` JS API，补上 Python API 缺失的功能。

**`sp_bake_mesh_maps(texture_set_name)`** — 烘焙 mesh maps（AO/Curvature/Normal 等）。
需要 SP 10.0+。通过 `alg.baking.bake()` 实现。需要完整参数控制时用 Phase 16 的原生烘焙 API。

**`sp_add_texture_set_channel(texture_set_name, channel_id, channel_format, channel_label)`** — 给纹理集添加通道。
`channel_format`: 传给 `alg.texturesets.addChannel()` 的格式字符串，默认 `"RGB16F"`，其它可选 `"sRGB8"` / `"L8"` / `"L16"` / `"RGBA16F"` 等。通过 `alg.texturesets.addChannel()` 实现。

**`sp_remove_texture_set_channel(texture_set_name, channel_id)`** — 删除纹理集通道。
通过 `alg.texturesets.removeChannel()` 实现。

**JS API 调用方式：**
```python
# 在 handler 中调用 JS API
import substance_painter.js as js
result = js.evaluate("alg.baking.bake('textureSetName')")
# 返回值是 JSON 字符串，需要 json.loads() 解析
```

### Phase 14 — Computer Use

通过 Windows API（`ctypes.windll.user32`）实现 mini Computer Use，供 LLM 视觉模型驱动 SP UI。

**`sp_window_info()`** — 返回窗口位置/尺寸/状态，配合截图做坐标映射。

**`sp_window_grab(region?)`** — 截取 SP 完整窗口或指定区域，返回 base64 PNG。
region 格式：`{"x": 0, "y": 0, "width": 400, "height": 300}`（相对窗口左上角）。

**`sp_window_focus()`** — 将 SP 窗口置于前台，获取焦点，并显示红色警示条。
返回 `{"focused": bool, "is_minimized": bool, "hwnd": int}`。
调用后 SP 窗口顶部会显示 "MCP Control Active" 半透明警示覆盖层。

**`sp_cu_unlock()`** — 解除 Computer Use 锁定，隐藏警示条。
操作结束后必须调用，确保警示条消失。

**`sp_cu_warning(text?)`** — 将警示条切换为黄色等待状态，提醒用户检查终端或 SP 弹窗。
不传 text 时使用默认提示 "Timeout - Check terminal"。
用户处理完毕后用 `sp_cu_banner_text` 恢复红色，或直接 `sp_cu_unlock` 结束。

**`sp_cu_banner_text(text)`** — 更新警示条显示的文字。
用于超时时显示提示信息（如 "⚠ 请检查 SP 是否弹出确认对话框"），
恢复正常后传入原始文字 "MCP Control Active - Do not touch mouse/keyboard"。

**`sp_mouse_move(x, y, relative?)`** — 移动鼠标。
relative：`"screen"`（屏幕绝对坐标，默认）或 `"window"`（相对 SP 窗口左上角）。

**`sp_mouse_click(x?, y?, button?, clicks?, relative?)`** — 鼠标点击。
button：`"left"` / `"right"` / `"middle"`。clicks：1=单击, 2=双击。
不传 x/y 则在当前位置点击。

**`sp_mouse_scroll(amount)`** — 滚轮。
正值=向上滚，负值=向下滚。Windows 标准单位 ±120。

**`sp_mouse_drag(x1, y1, x2, y2, button?, relative?)`** — 拖拽从 (x1,y1) 到 (x2,y2)。

**`sp_key_send(keys, modifiers?)`** — 发送键盘输入。
keys：文本字符串或键名。modifiers：`["ctrl"]`, `["ctrl","shift"]` 等。
支持键名：enter, tab, esc, space, backspace, delete, home, end, pageup, pagedown, left, right, up, down, f1-f12, ctrl, shift, alt。

**`sp_shortcut(action)`** — 预定义快捷键封装。
action 可选值：
  文件: save / save_as / new_project / open_project / close_project / import_image / export_textures
  编辑: undo / redo / select_all / deselect / copy / paste / cut / duplicate / delete_layer
  图层: new_fill_layer / new_paint_layer / new_group / merge_down
  视口: frame_all / toggle_wireframe / toggle_unity
  模式: paint_mode / erase_mode / project_mode
  显示: toggle_ui / toggle_mask_view
  Iray: toggle_iray

**使用示例：**
```
sp_window_focus()                          → 聚焦 SP + 显示警示条
sp_window_grab()                           → 截整窗口发给 LLM 分析
sp_mouse_click(400, 300, "left")           → 在窗口坐标 (400,300) 左键点击
sp_key_send("a", ["ctrl"])                 → Ctrl+A 全选
sp_key_send("hello")                       → 逐键打出 "hello"
sp_shortcut(action="save")                 → Ctrl+S 保存
sp_shortcut(action="undo")                 → Ctrl+Z 撤销
sp_shortcut(action="frame_all")            → Alt+F 适配视图
sp_cu_unlock()                             → 操作完毕，隐藏警示条
```

---

### 图层补充工具

**`sp_find_layer_by_name(name)`** — 跨所有纹理集按名称搜索图层（大小写不敏感），返回 `matches` 列表。不知道 layer_id 时用它定位。

**`sp_add_mask(layer_id)`** — 为图层加空白白色遮罩（非程序化）。`sp_remove_mask(layer_id)` 移除。Smart Mask 不走这里，用 `sp_delete_layer` 删整个 mask effect。

**`sp_list_export_presets()`** — 列出可用导出预设名。调 `sp_export_textures` 前先确认 preset 合法值。

**`sp_get_iray_params()`** — 读取当前 Iray 面板参数（改前确认现状）。

### 程序化源参数控制（SourceSubstance）

仅 `FillLayerNode` / `FillEffectNode` 且源为 `SourceSubstance` 时可用。

**`sp_get_source_info(layer_id, channel?)`** — 读取源信息（类型/颜色/资源/参数）。

**`sp_get_substance_parameters(layer_id, channel?)`** — 读取参数当前值 + 类型/描述。

**`sp_set_substance_parameters(layer_id, params, channel?)`** — 批量改参数（dict）。

**`sp_get_substance_presets(layer_id, channel?)`** / **`sp_apply_substance_preset(layer_id, preset_name, channel?)`** — 列出/应用预设。

**`sp_get_source_outputs(layer_id, channel?)`** / **`sp_set_source_output(layer_id, output_id, channel?)`** — 输出映射读写。

### 相机与显示增强

**`sp_get_camera()`** — 读取主相机完整状态（position/rotation/fov）。

**`sp_get_tone_mapping()`** / **`sp_set_tone_mapping(function)`** — 色调映射，function: `"Linear"` / `"ACES"`。

**`sp_get_color_lut()`** / **`sp_set_color_lut(resource_name)`** — 色彩 LUT 配置读写。

**`sp_get_scene_bounding_box()`** — 场景包围盒（center/dimensions/radius）。

### Phase 15 — 效果节点

通过 `layerstack.insert_*_effect` 在图层 Content / Mask 栈插入效果节点。

**`sp_add_filter_effect(layer_id, filter_name?)`** — Filter 效果（Content 栈）。

**`sp_add_generator_effect(layer_id, generator_name?)`** — Generator 效果（Content 栈）。

**`sp_add_levels_effect(layer_id)`** — Levels 色阶（Content 栈）。

**`sp_add_compare_mask_effect(layer_id)`** / **`sp_add_color_selection_effect(layer_id)`** — 遮罩效果（Mask 栈）。

**`sp_add_anchor_point_effect(layer_id, anchor_name?)`** — 锚点（Content 栈）。

**`sp_get_effect_parameters(layer_id)`** — 读取效果节点参数（Levels/CompareMask/ColorSelection/Filter/Generator）。

**`sp_get_selected_nodes(texture_set_name?)`** / **`sp_set_selected_nodes(node_ids)`** — 选区读写。

### Phase 16 — 烘焙 API（Python 原生）

用 `substance_painter.baking` 原生 API，比 Phase 9 的 `sp_bake_mesh_maps`（JS）更完整。

**`sp_get_baking_parameters(texture_set_name)`** — 读取 common + 各 baker + 曲率方法 + 启用项。

**`sp_set_baking_parameters(texture_set_name, common?, baker?)`** — 设置烘焙参数。

**`sp_bake_texture_set(texture_set_name)`** — 异步启动烘焙。

**`sp_get_baking_state(texture_set_name)`** / **`sp_set_baking_state(texture_set_name, ...)`** — 启用状态/曲率方法/bakers/UV tiles 读写。

### Phase 17 — 项目生命周期 + 元数据

**`sp_create_project(mesh_path, ...)`** — 创建新项目（网格/法线格式/工作流）。

**`sp_open_project(file_path)`** / **`sp_close_project()`** — 打开 .spp / 关闭项目。

**`sp_reload_mesh(mesh_path, ...)`** — 异步重载网格。

**`sp_get_project_metadata(context, key)`** / **`sp_set_project_metadata(context, key, value)`** / **`sp_list_project_metadata(context)`** — 项目级持久化元数据读写。

**`sp_list_resources_by_usage(usage, search?)`** — 按用途列资源。usage: `filter`/`generator`/`substance`/`smart_material`/`smart_mask`/`texture`/`environment`/`export_preset`。

> **工具规模：** MCP tools 总计 92 个，与 `sp_mcp.py` 的 `@mcp.tool()` 数和 `handlers.py` 的 `_REGISTRY` 条目一一对应。新增工具要三处同步：`sp_mcp.py` + `handlers.py` + `.opencode/skills`。

---

## 创作工作流规范

### 标准迭代循环

```
1. sp_ping()                    确认连接
2. sp_capture_viewport("quick") 看当前状态
3. sp_get_layer_stack()         理解图层结构
4. [决策] 制定材质方案
5. 执行材质操作
6. sp_capture_viewport("quick") 看结果
7. [评估] 满意 → export，不满意 → 回步骤 5
8. sp_capture_viewport("render") 最终确认
9. sp_export_textures()
```

### 原则

- 图层命名语义化（`"Rust_Overlay"` 而非 `"Layer_1"`）
- 先建基础材质，再叠加效果
- 每个视觉层次完成后截图，不要攒到最后
- opacity 从保守值开始（0.3–0.5），截图确认后调整

---

## 开发指南

### 环境

```
Substance 3D Painter  10.0.1
Python（外部 venv）    3.10+
fastmcp               0.9+
requests              2.31+
```

### 启动顺序

```
1. 启动 Painter，打开一个项目
2. 确认 Python Console 显示 [INFO] sp_bridge: SP Bridge started on port 27182
3. 激活 venv：.venv\Scripts\activate
4. 启动 MCP server：python server/sp_mcp.py
```

### OpenCode 配置（~/.config/opencode/opencode.jsonc）

```json
{
  "mcp": {
    "substance-painter": {
      "type": "local",
      "command": ["C:\\<项目路径>\\sp-mcp\\.venv\\Scripts\\python.exe", "server/sp_mcp.py"]
    }
  }
}
```

### 调试

Bridge 连通性测试（PowerShell）：
```powershell
Invoke-RestMethod -Uri http://127.0.0.1:27182 -Method POST `
  -ContentType "application/json" `
  -Body '{"method":"ping","params":{}}'
```

日志：`%USERPROFILE%\sp_bridge.log`

### 测试命令

```powershell
# mock 测试（不需要 Painter）
pytest tests/ -m "not integration" -v

# integration 测试（需要 Painter + 打开项目）
pytest tests/ -m integration -v
```

### 版本检测

```python
# 正确方式（Phase 2 验证）
import substance_painter.application
version_str = substance_painter.application.version()  # → "10.0.1"

# 错误方式（不要用）
# substance_painter.__version__  → 返回 SDK 版本 "0.3.0"，不是 Painter 版本
```

---

## 与 SP2VTF 的集成

```bash
# 导出后调用 SP2VTF 转换为 Source 引擎 VTF 格式
python sp2vtf/convert.py --input ./export/gun_skin_v1 --output ./vtf/
```

---

## 已知限制

- `sp_capture_viewport` 需要项目打开且 3D viewport 可见
- Smart Material API 需要 SP 10.0+，9.x 上相关 tool 返回明确错误
- Layer id 在 Painter 重启后会变化，不要跨 session 缓存
- `schedule_on_ui_thread` 在 SP 10.x 不存在，已用 QTimer 轮询方案替代
