# Changelog

本项目所有重要变更记录在此。格式参考 [Keep a Changelog](https://keepachangelog.com/)，
版本号遵循 [语义化版本](https://semver.org/)。

---

## [0.6.0] — 2026-06-30 — 实机全工具审计

本次版本的核心是**对 80 个非 Computer Use 工具逐个在真实 Substance Painter
10.0.1 上调用验证**，并对 12 个 Computer Use 工具单独完成实机验证。审计修复了
7 个此前被 mock 测试自我掩盖的真 bug，并把 bake 从同步阻塞改为异步架构。
这是项目首次达到"实机验证可用"。
完整过程见 [PHASES.md Phase 18](./PHASES.md)。

### Added

- **`sp_get_bake_status`** — 轮询 `sp_bake_mesh_maps` 的异步烘焙状态
  （phase/progress/status/elapsed），供客户端确认完成而非盲目重试。
- **`sp_cancel_bake`** — 取消进行中的异步烘焙（基于 `StopSource.request_stop()`）。
- 三个文档（README/AGENTS/PHASES）补全 Phase 18 实机审计记录与 API 事实表。
- 新增 [CHANGELOG.md](./CHANGELOG.md)；README 顶部加 version/tools/tests 徽章。
- `plugin/__init__.py` 明确声明插件包，pytest 配置加入仓库根目录到 import path，
  让本地测试入口更可复现。

### Changed

- **`sp_bake_mesh_maps` 改为异步** —— 原同步 `js.evaluate("alg.baking.bake()")`
  会阻塞 HTTP 直到烘焙完成，超时后 SP 内仍继续执行、客户端误判失败而重试，
  存在重复触发烘焙的高危风险。现用 `baking.bake_async()` 立即返回，配
  `BakingProcessProgress`/`BakingProcessEnded` 事件驱动状态机，从根上消除
  超时误报。docstring 写入"勿盲目重试、用 get_bake_status 轮询"提醒。
- `sp_set_baking_parameters` / `sp_set_baking_state` 加固：传了参数却全未匹配、
  或全部可改项为 None 时，明确报错而非静默谎报 ok。
- `sp_set_environment` 只在 `Usage.ENVIRONMENT` 资源里匹配，避免误选同名非环境资源。
- mcp.json 补全到 94 工具，version 0.5.0 → 0.6.0。
- pyproject 版本号同步到 0.6.0。
- README 加 computer-use 安全警告（mouse_*/key_send/sp_shortcut 会真实操控
  物理鼠标键盘，调用时勿同时用电脑、先 window_focus）。

### Fixed（实机暴露的 7 个真 bug）

| Bug | 根因 | 修复 |
|-----|------|------|
| `get_layer_channels` 在画图层崩 | 无条件调 `get_source()`，但 PaintLayerNode 无该方法 | hasattr 探测，不支持 source 的图层只回 opacity/blend_mode |
| `_copy_channels` 克隆 procedural 图层崩 | SourceSubstance 传给 set_source 抛 "Unknown parameter type" | 捕获所有异常 + 跳过并告警 |
| `set_texture_set_resolution` 永远匹配不到 | 用 `is` 比较 pybind11 stack 包装（每次返回不同对象） | 改 `==`（Stack 定义值相等） |
| `set_texture_set_resolution` set_resolution 崩 | 传 (w,h) 两参数，实际接受单个 Resolution 对象 | 改传 `ts.Resolution(w, h)` |
| `export_textures` 立即崩 | 用不存在的 `ExportConfig` 类；实际接受 JSON dict | 按真实 API 重写：preset 解析为 url + json_config + 展平 textures dict |
| `get_iray_params` 读不全 | 只扫 QSpinBox，漏读 maxSamples/maxTime（实为 QLineEdit） | 按控件真实类型读 |
| `list_resources_by_usage` / `list_export_presets` 等枚举崩溃 | 硬写枚举成员名、直接迭代 pybind11 枚举 | getattr 防御式构建 + `__members__` |

### Verified

- 只读 28 个工具 ✅ 实机逐个调用
- 写操作 38 个 ✅ 测试图层上实机执行（batch 包裹 + 测完清理）
- 生命周期 5 个 ✅ 在废弃项目上实测（save/close/create/reload/open）
- computer-use 12 个 ✅ 全部实机验证（含会动鼠标键盘的 6 个）
- bake 异步链路 ✅ 启动→查询→取消，取消后 `is_busy=False`
- 464 测试全绿

### Known limitations

- `bake` 实际完成烘焙 / `iray` 实际渲染出图：受测试机器性能/磁盘空间限制，
  仅验证异步链路与参数读写，未跑完一次完整烘焙/渲染。
- `key_send` 的逐字符打字路径未实测（任何字符都会真实输入到焦点窗口）。

---

## [0.5.0] — 2026-06-15 — 功能补全（92 工具）

### Added — Tier 1 三大功能块（`f633aeb`）

- **效果节点（Phase 15）**：Filter / Generator / Levels / CompareMask /
  ColorSelection / Anchor 六类效果插入，配 `get_effect_parameters` /
  `get_selected_nodes` / `set_selected_nodes`。
- **烘焙 API（Phase 16）**：Python 原生 `substance_painter.baking` 参数/状态/
  异步执行，替代 JS `alg.baking.bake()`。含 `get/set_baking_parameters`、
  `bake_texture_set`、`get/set_baking_state`。
- **项目生命周期（Phase 17）**：`create_project` / `open_project` /
  `close_project` / `reload_mesh` + 项目级持久化元数据读写 +
  `list_resources_by_usage`。
- `sp_shortcut`（`80f299a`）— 26 个预定义 SP 快捷键封装。
- 程序化源参数控制（Phase 13b，SourceSubstance）：get/set parameters、
  presets、outputs 共 7 个工具。
- 相机与显示增强：camera / tone_mapping / color_lut / scene_bounding_box。

### Changed

- 插件文件重构进 `plugin/sp_bridge/` 子目录（`8dd954b`，Phase 12）。
- 跨线程调度统一走 `_task_queue` + QTimer 方案（`schedule_on_ui_thread` 在
  SP 10.x 不存在）。
- 用 SP 原生 QUndoStack 实现 undo/redo（`37a44ac`，Phase 10/11，非外置栈）。
- 每个 layer API 自动包裹 `ScopedModification`，1 次调用 = 1 条 undo（Phase 12）。
- 移除已废弃的 QML 插件，全部功能走 Python bridge（`1d7d807`）。
- 扩展 .gitignore（venv / logs / IDE / .claude/ / .spp 等，`0b5f222`）。

### Fixed

- `set_camera` 读取当前状态、保留未指定参数、支持 target 旋转（`f134884`）。
- fastmcp banner 在 stdio 模式污染 stdout（`ed39d77`）。
- Phase 6/7 工具适配 SP 10.x API 限制（`d86c6bc`）。

---

## [0.4.0] — 2026-06-12 — Computer Use（Phase 14）

### Added（`ebcbb22`）

mini Computer Use 能力，供 LLM 视觉模型驱动 SP UI：

- 窗口截图与信息：`window_info` / `window_grab`（全窗口或区域）/ `window_focus`
  （聚焦 + 红色警示条）。
- 鼠标控制：`mouse_move` / `mouse_click`（左/右/中，单击/双击）/ `mouse_scroll`
  / `mouse_drag`。
- 键盘控制：`key_send`（单键/组合键/打字，支持 enter/tab/f1-f12/方向键等命名键）。
- CU 警示条：`cu_unlock` / `cu_banner_text` / `cu_warning`。

### Fixed

- `alg.ui.clickButton` 在 SP 10.0.1 有 `findChild` 内部 bug，Computer Use 的
  鼠标点击绕过此限制。

---

## [0.3.0] — 2026-06-08 — 稳定性与防僵尸

### Added

- PID 文件锁防止 MCP zombie 进程（`19d2b4b`）。

### Fixed

- timeout 60s 作为真实修复（`5b60350`，此前误改 banner）。

---

## [0.2.0] — 2026-06-06 — 图层高级操作 + Skills

### Added

- **四功能复现（Phase 13，`8b6941b`）**：用 delete+re-insert 工作流实现
  SP 10.x 缺 Python API 的 `move_layer` / `group_layers` / `ungroup_layer` /
  `frame_mesh`。发现 `get_node_by_uid` / `get_parent` / `get_scene_bounding_box`
  等真实 API。
- **Skills 扩展（`f7c2f4a`）**：从 8 个扩到 13 个，形成完整 SP-MCP skill 系统。
- 新增 sp-camera / sp-texture-set / sp-project skills，sp-layer-ops 加入
  "先读后改"原则（`de00499`）。

### Changed

- README 完善：安装路径、缺失工具、Antigravity CLI 配置（`2774729`）。
- README 移除 SP2VTF 集成章节（`a87bcae`）。

### Fixed

- README 安装路径修正、补齐缺失工具说明（`2774729`、`d2b8d0b`）。

---

## [0.1.0] — 2026-06-03 — 初始版本

### Added

- SP MCP bridge + server 初始实现（`5f19d07`）：HTTP bridge（端口 27182）+
  FastMCP server + QTimer 跨线程调度。
- 核心图层工具（Phase 2）：`get_layer_stack` / `get_texture_sets` /
  `add_fill_layer` / `set_layer_property` 等。
- 视觉反馈回路（Phase 3）：`capture_viewport`（quick/render 两种模式），
  建立"截图→评估→修改→截图"迭代闭环。
- Smart Material 创作工具（Phase 4）：`apply_smart_material` / `add_smart_mask` /
  `list_shelf_materials` + Iray 渲染（`set_iray_params` / `start_iray_render` /
  `check_iray_render`）。
- 图层基础 + 通道 + Undo（Phase 6/7/8）：delete/group/paint layer、undo/redo、
  set/get layer channel、duplicate/move/group/ungroup、TextureSet 管理、
  batch 操作。
- Skills + Commands 补全（Phase 5，`0993c62`）：sp-layer-ops /
  sp-creative-workflow / sp-export-pipeline / sp-debug 四个 skill +
  check / paint / export 命令。
- 初始 README、AGENTS.md、PHASES.md（`5442828` / `6915f5d`）。

### Known limitations（初始）

- `schedule_on_ui_thread` 在 SP 10.x 不存在 → 用 QTimer 轮询队列。
- `substance_painter.layers` 不存在 → 用 `substance_painter.layerstack`。
- `is_enabled` 不存在 → 用 `is_visible`。
- Layer id 在 Painter 重启后变化，不跨 session 缓存。

---

## 版本演进一览

| 版本 | 日期 | 工具数 | 里程碑 |
|------|------|--------|--------|
| 0.1.0 | 2026-06-03 | ~23 | 核心 bridge + 图层工具 + 视觉反馈回路 |
| 0.2.0 | 2026-06-06 | ~30 | 图层高级操作（move/group/ungroup/frame）+ skills |
| 0.3.0 | 2026-06-08 | ~30 | 稳定性 + PID 锁 |
| 0.4.0 | 2026-06-12 | ~42 | Computer Use（窗口截图 + 鼠标键盘控制） |
| 0.5.0 | 2026-06-15 | 92 | 效果节点 + 烘焙 + 项目生命周期 |
| 0.6.0 | 2026-06-30 | 94 | 实机全工具审计 + bake 异步化 + 7 bug 修复 |

> 完整提交历史见 `git log`。开发过程与阶段任务详见 [PHASES.md](./PHASES.md)。
