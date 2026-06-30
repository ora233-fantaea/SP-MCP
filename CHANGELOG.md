# Changelog

本项目所有重要变更记录在此。格式参考 [Keep a Changelog](https://keepachangelog.com/)，
版本号遵循 [语义化版本](https://semver.org/)。

---

## [0.6.0] — 2026-06-30 — 实机全工具审计

本次版本的核心是**对 92 个工具中的 80 个（除 computer-use 外）逐个在真实
Substance Painter 10.0.1 上调用验证**，修复了 7 个此前被 mock 测试自我掩盖的
真 bug，并把 bake 从同步阻塞改为异步架构。这是项目首次达到"实机验证可用"。

### Added

- **`sp_get_bake_status`** — 轮询 `sp_bake_mesh_maps` 的异步烘焙状态
  （phase/progress/status/elapsed），供客户端确认完成而非盲目重试。
- **`sp_cancel_bake`** — 取消进行中的异步烘焙（基于 `StopSource.request_stop()`）。
- 三个文档（README/AGENTS/PHASES）补全 Phase 18 实机审计记录与 API 事实表。

### Changed

- **`sp_bake_mesh_maps` 改为异步** —— 原同步 `js.evaluate("alg.baking.bake()")`
  会阻塞 HTTP 直到烘焙完成，超时后 SP 内仍继续执行、客户端误判失败而重试，
  存在重复触发烘焙的高危风险。现用 `baking.bake_async()` 立即返回，配
  `BakingProcessProgress`/`BakingProcessEnded` 事件驱动状态机，从根上消除
  超时误报。docstring 写入"勿盲目重试、用 get_bake_status 轮询"提醒。
- `sp_set_baking_parameters` / `sp_set_baking_state` 加固：传了参数却全未匹配、
  或全部可改项为 None 时，明确报错而非静默谎报 ok。

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

## [0.5.0] — 2026-06 — 功能补全（92 工具）

### Added

- **Tier 1 三大功能块**：效果节点（Filter/Generator/Levels/CompareMask/
  ColorSelection/Anchor）、烘焙 API（Python 原生参数/状态/异步执行）、
  项目生命周期（create/open/close/reload_mesh + 元数据）。
- `sp_shortcut` — 26 个预定义 SP 快捷键封装。
- 程序化源参数控制（SourceSubstance）：get/set parameters、presets、outputs。
- 相机与显示增强：camera / tone_mapping / color_lut / scene_bounding_box。
- Computer Use（Phase 14）：window 截图 + 鼠标/键盘控制 + CU 警示条。
- 16 个项目专属 skill（LLM 操作参考）。
- 自动 batch：每个图层修改自动包裹 ScopedModification，1 次调用 = 1 条 undo。
- PID 文件锁防止 MCP zombie 进程。

### Changed

- 插件文件重构进 `plugin/sp_bridge/` 子目录。
- 跨线程调度统一走 `_task_queue` + QTimer 方案（`schedule_on_ui_thread` 在
  SP 10.x 不存在）。
- 用 SP 原生 QUndoStack 实现 undo/redo（非外置栈）。

---

## [0.4.0] 及更早

核心图层工具、视觉反馈回路（截图迭代）、Smart Material 创作工具、
Skills + Commands 补全。详见 git 历史。
