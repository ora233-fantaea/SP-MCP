# SP MCP — 开发阶段规划

本文件供 AI agent 读取，按阶段指导项目开发。
每个 Phase 包含：目标、已知信息、具体任务、验收标准。
**按顺序执行，当前 Phase 验收通过后再进入下一个。**

---

## 已知 API 事实（Phase 2–4 探索结果）

在开始任何任务前，先记住这些修正：

| 原假设 | 实际 API |
|---|---|
| `substance_painter.layers` | `substance_painter.layerstack` |
| `substance_painter.__version__` | `substance_painter.application.version()` → `"10.0.1"` |
| `is_enabled()` / `set_enabled()` | `is_visible()` / `set_visible()` |
| `get_child_layers()` | `node.sub_layers()` (GroupLayerNode) |
| `get_root_layer_nodes()` 返回 int ID | 返回 `List[Node]` 节点对象 |
| 节点类型 `node.get_type().name` | `type(node).__name__` → `"FillLayerNode"` / `"GroupLayerNode"` |
| `get_opacity()` 无参数 | `get_opacity(ChannelType.BaseColor)` 需要 ChannelType |
| 类型枚举 `"FILL"` / `"GROUP"` | `"FillLayerNode"` / `"GroupLayerNode"` |
| Smart Material 用 `layers` 模块 | `resource.search()` + `ls.insert_smart_material()` |
| Smart Mask 直接插入 | 需先 `node.add_mask(White)` 再 `insert_smart_mask()` |
| `schedule_on_ui_thread` 存在 | 不存在，用 QTimer 轮询队列 |
| `substance_painter.textureset` | 返回所有纹理集，`.name()` 是方法，`.get_resolution()` 返回 `Resolution` 对象 |

遇到 API 不确定时，先用 `sp_run_python` 探索，再写实现。

---

## Phase 状态总览

| Phase | 内容 | 状态 |
|---|---|---|
| Phase 1 | Bridge 连通 | ✅ 完成 |
| Phase 2 | 核心图层工具 | ✅ 完成 |
| Phase 3 | 视觉反馈（截图） | ✅ 完成 |
| Phase 4 | Smart Material 创作工具 | ✅ 完成（含 Iray） |
| Phase 5 | Skills + Commands 补全 | ✅ 完成 |
| Phase 6 | 图层基础 + 通道 + Undo | ✅ 完成 |
| Phase 7 | 图层高级 + TextureSet + 项目 + 相机 | ✅ 完成 |
| Phase 8 | 批量 Undo（ScopedModification） | ✅ 完成 |
| Phase 9 | JS API 集成（Baking + 通道管理） | ✅ 完成 |
| Phase 10 | Undo/Redo 探索 | ✅ 完成（发现 SP 原生 undo 栈跟踪 Python API 操作） |
| Phase 11 | 外置 Undo/Redo 栈 | ✅ 已删除（改用 SP 原生 undo/redo） |
| Phase 12 | 自动 batch + 文件重构 | ✅ 完成 |
| Phase 13 | 四功能复现（move/group/ungroup/frame） | ✅ 完成 |
| Phase 13b | 程序化源参数控制 + 相机/显示增强 | ✅ 完成 |
| Phase 14 | Computer Use（窗口截图 + 鼠标/键盘控制） | ✅ 完成 |
| Phase 15 | 效果节点（Filter/Generator/Levels/CompareMask/ColorSelection/Anchor） | ✅ 完成 |
| Phase 16 | 烘焙 API（Python 原生：参数/状态/异步执行） | ✅ 完成 |
| Phase 17 | 项目生命周期 + 元数据 + 资源发现 | ✅ 完成 |

---

## Phase 2 — 核心图层工具

**状态：** ✅ 完成

- Mock 28/28 ✅
- Server 13/13 ✅
- Integration 3/3 ✅（ping, get_layer_stack, add+get roundtrip）
- 所有 handler 使用真实 SP 10.x API

---

## Phase 3 — 视觉反馈（截图回路）

**状态：** ✅ 完成

- `_capture_qt()` 已验证：1052×606 PNG，有效
- 找到主 viewport：`QOpenGLWidget` name="Viewer3D"
- `mode="render"` 保持 `NotImplementedError`（Iray 留后续）

---

## Phase 4 — Smart Material 创作工具

**状态：** ✅ 完成

已实现并验证：
- `list_shelf_materials(filter)` — 返回 `List[str]`，37 个 metal 材质
- `apply_smart_material(layer_id, material_name)` — 创建 GroupLayerNode
- `add_smart_mask(layer_id, mask_name)` — 先 add_mask 再 insert_smart_mask
- `set_iray_params(max_samples, max_time, width, height)` — 通过 UI widget 控制 Iray 参数
- `start_iray_render()` — QTimer.singleShot 异步触发 Iray
- `check_iray_render()` — 读取 iterationsLabel/timeLabel 监控渲染进度
- `capture_viewport(mode="render")` — Iray 渲染完成后 Qt grab 截图
- `get_texture_sets(filter)` — 返回所有纹理集及图层结构，支持名称过滤

**Iray 工作流（方案 B — MCP 层独立 tool）：**
```
1. sp_set_iray_params(max_samples=100, max_time=60, width=1920, height=1080)
2. sp_start_iray_render()          ← QTimer 异步触发，不阻塞 HTTP
3. sp_check_iray_render()          ← 轮询 iterations/time 直到稳定
4. sp_capture_viewport("render")   ← 渲染完成后截图
```

**已知限制：**
- Iray 渲染阻塞 Qt 主线程，渲染期间所有 bridge 请求 timeout
- `start_iray_render` 的 QTimer.singleShot 延迟触发，HTTP 先返回
- `check_iray_render` 在渲染期间也会 timeout（主线程被占用）
- bridge 10s timeout 不变，不影响其他 tool

---

## Phase 5 — Skills + Commands 补全

**状态：** ✅ 完成

**已完成：**
- `.opencode/skills/sp-layer-ops/SKILL.md` — 图层操作 API 速查表
- `.opencode/skills/sp-creative-workflow/SKILL.md` — 创作迭代循环
- `.opencode/skills/sp-export-pipeline/SKILL.md` — 导出 + SP2VTF 流水线
- `.opencode/skills/sp-debug/SKILL.md` — 调试排错指南
- `.opencode/commands/check.md` — 健康检查一键命令
- `.opencode/commands/paint.md` — 创作工作流命令
- `.opencode/commands/export.md` — 导出命令
- MCP tools 总计 16 个（含 `sp_get_texture_sets`）

---

**目标：** 把 Phase 2–4 探索出的真实 API 写进 Skills，
后续 session 不用重新探索。

**任务 5.1 — 创建目录结构：**
```
.opencode/
├── skills/
│   ├── sp-layer-ops/SKILL.md
│   ├── sp-creative-workflow/SKILL.md
│   ├── sp-export-pipeline/SKILL.md
│   └── sp-debug/SKILL.md
└── commands/
    ├── check.md
    ├── paint.md
    └── export.md
```

**任务 5.2 — `sp-layer-ops/SKILL.md`：**

frontmatter:
```yaml
---
name: sp-layer-ops
description: 调用 MCP tools 操作 Substance Painter 图层栈，包括新建图层、
             修改材质属性、应用 Smart Material、添加 Smart Mask。
             调色/材质参数调整、图层增删改类任务触发此 skill。
---
```

内容包含：
- 真实 API 速查表（从 Phase 2 结果填入）
- 每个 tool 的参数和示例调用
- 常见错误和处理方式

**任务 5.3 — `sp-creative-workflow/SKILL.md`：**

frontmatter:
```yaml
---
name: sp-creative-workflow
description: 通过截图回路驱动 Substance Painter 材质创作，包括视觉评估、
             迭代调整、多轮确认。用户要求设计/美化/调整材质外观时触发此 skill。
---
```

内容包含：
- 标准迭代循环（截图→评估→修改→截图）
- quick vs render 模式的使用时机
- 典型场景示例（战损金属、氧化铜、烤漆等）
- 参数调整策略（从保守值开始，截图确认再加强）

**任务 5.4 — `sp-export-pipeline/SKILL.md`：**

frontmatter:
```yaml
---
name: sp-export-pipeline
description: 触发 Substance Painter 贴图导出并对接 SP2VTF 完成 Source 引擎
             格式转换。用户提到导出、转 VTF、L4D2 材质时触发此 skill。
---
```

内容包含：
- 实际可用的 preset 名称（从 Phase 2 探索结果填入）
- export_textures 调用示例
- SP2VTF 衔接命令

**任务 5.5 — `sp-debug/SKILL.md`：**

frontmatter:
```yaml
---
name: sp-debug
description: 排查 SP MCP bridge 连接问题、plugin 加载失败、tool 调用报错。
             遇到连接错误、timeout、API 报错时触发此 skill。
---
```

内容包含 Phase 1–4 踩过的所有坑：
- `schedule_on_ui_thread` 不存在 → 用 QTimer 轮询队列
- `substance_painter.layers` 不存在 → 用 `substance_painter.layerstack`
- `is_enabled` 不存在 → 用 `is_visible`
- Smart API 版本判断用 `application.version()` 而非 `__version__`
- 日志位置：`%USERPROFILE%\sp_bridge.log`

**任务 5.6 — `commands/check.md`：**

```markdown
---
description: 验证 SP bridge 健康状态
---

执行以下检查：
1. pytest tests/ -m "not integration" — mock 测试
2. sp_ping — 验证 bridge 连通
3. sp_get_layer_stack — 验证项目已打开
4. sp_capture_viewport(mode="quick") — 验证截图可用
输出每步结果，有失败立即报告原因。
```

**任务 5.7 — `commands/paint.md`：**

```markdown
---
description: 触发完整材质创作工作流
---

执行标准创作迭代循环：
1. sp_ping 确认连接
2. sp_capture_viewport(mode="quick") 看当前状态
3. sp_get_layer_stack 分析图层结构
4. 根据用户需求制定材质方案
5. 执行材质操作（apply/add/set）
6. sp_capture_viewport(mode="quick") 评估结果
7. 根据截图决定是否继续调整
8. 满意后 sp_capture_viewport(mode="render") 最终确认
```

**任务 5.8 — `commands/export.md`：**

```markdown
---
description: 导出贴图并转换为 VTF 格式
---

1. sp_capture_viewport(mode="render") 最终确认
2. sp_export_textures(preset, output_dir) 导出
3. 调用 SP2VTF 转换为 Source 引擎格式：
   python sp2vtf/convert.py --input <output_dir> --output <vtf_dir>
```

**验收标准：**
- 四个 SKILL.md 文件内容完整，description 准确
- `/check` 命令能一键输出 bridge 健康报告
- `/paint` 命令能触发一次完整的截图迭代循环
- `/export` 命令能触发导出并调用 SP2VTF

---

## Phase 6 — 图层基础 + 通道 + Undo

**状态：** ✅ 完成

**目标：** 补齐现有 handler 测试缺口 + 新增 7 个 tool，覆盖图层增删、分组、绘画图层、undo/redo、通道值控制。

### 任务 6.0 — 补测试缺口

**问题：** 以下 4 个 handler 已实现并 live 验证，但 mock 测试完全缺失：

| Handler | 缺什么 |
|---------|--------|
| `get_texture_sets` | `textureset` mock 不完整：缺 `all_texture_sets()`、textureset 对象的 `.name()` `.get_resolution()` `.get_stack()` |
| `apply_smart_material` | 无测试：`resource.search` + `InsertPosition.above_node` 未验证 |
| `add_smart_mask` | 无测试：`add_mask` + `insert_smart_mask` + `MaskBackground` + `NodeStack` 未验证 |
| `list_shelf_materials` | 无测试：`resource.search` 过滤逻辑未验证 |

**具体改动（`tests/conftest.py`）：**

1. 补全 `textureset` mock：
   - `all_texture_sets()` → 返回含 2 个 mock textureset 对象的列表
   - 每个对象有 `.name()` → `str`、`.get_resolution()` → `Resolution(width, height)`、`.get_stack()` → `Stack`
   - `Resolution` 类：`(width, height)` 数据类

2. 已有 mock 确认够用（无需改动）：
   - `resource.search` 已有智能过滤逻辑（3 个硬编码材质）
   - `InsertPosition.above_node` / `inside_node` 已 mock
   - `node.add_mask` 已 mock
   - `insert_smart_mask` 已 mock

**具体改动（`tests/test_handlers_mock.py`）：**

新增 4 个测试类/函数：
- `test_get_texture_sets` — 验证返回格式、filter 过滤
- `test_apply_smart_material` — 验证 resource.search 调用 + insert 结果
- `test_add_smart_mask` — 验证 add_mask + insert_smart_mask 调用
- `test_list_shelf_materials` — 验证返回值类型和 filter

**验收：** `pytest tests/ -m "not integration"` 全绿，覆盖所有 16 个现有 tool

---

### 任务 6.1 — 图层删除 + 分组 + 绘画图层（3 tools）

**`sp_delete_layer(layer_id)`**

- handler：`_find_layer(layer_id)` → `ls.delete_node(node)`
- mock：`ls.delete_node` 已存在（conftest.py:174），无需新增
- 测试：删除后验证节点不在图层树中

**`sp_add_group_layer(name)`**

- handler：`ls.InsertPosition.from_textureset_stack(stack)` → `ls.insert_group(pos)` → `node.set_name(name)`
- mock 需新增：`ls.insert_group(pos)` → 创建 `MockGroupNode("New Group")`，插入 `_root_nodes[0]`，返回节点
- 测试：创建后验证图层树中有 GroupLayerNode

**`sp_add_paint_layer(name)`**

- handler：同上，用 `ls.insert_paint(pos)`
- mock 需新增：
  - `_make_node_class("PaintLayerNode")` → 创建 `MockPaintNode` 类
  - `ls.insert_paint(pos)` → 创建 `MockPaintNode("New Paint")`，插入 `_root_nodes[0]`，返回节点
- 测试：创建后验证 type 为 PaintLayerNode

**改动文件：** `conftest.py`（+20 行）、`handlers.py`（+25 行）、`sp_mcp.py`（+25 行）、`test_handlers_mock.py`（+30 行）、`mcp.json`（+3 tools）

---

### 任务 6.2 — Undo / Redo（2 tools）

**`sp_undo()` / `sp_redo()`**

- handler：`import substance_painter.undo; undo.undo()` / `undo.redo()`
- mock 需新增：`substance_painter.undo` 整个模块
  - `undo()` → 无操作（mock 无法真正 undo，但接口要通）
  - `redo()` → 无操作
  - `is_undo_available()` → `True`（用于验证调用可行性）
  - `is_redo_available()` → `True`
- 测试：调用后验证无异常，返回 `{"ok": true}`

**改动文件：** `conftest.py`（+12 行）、`handlers.py`（+12 行）、`sp_mcp.py`（+16 行）、`test_handlers_mock.py`（+10 行）、`mcp.json`（+2 tools）

---

### 任务 6.3 — 通道值控制（2 tools）

**`sp_set_layer_channel(layer_id, channel, value)`**

- handler：
  ```python
  ch = _parse_channel(channel)  # "roughness" → ChannelType.Roughness
  if ch == ChannelType.BaseColor:
      r, g, b = _hex_to_rgb(value)
      layer.set_source(ch, ls.Color(r, g, b))
  else:
      layer.set_source(ch, float(value))
  ```
- mock 改动：`node.set_source` 从 no-op 改为**有状态**：
  ```python
  def set_source(self, ch, value):
      self._sources[ch] = value
  def get_source(self, ch):
      return self._sources.get(ch)
  ```
- 测试：set roughness=0.5 → get 返回 0.5

**`sp_get_layer_channels(layer_id)`**

- handler：遍历 `ChannelType` 枚举值，对每个调用 `get_opacity(ch)` + `get_blending_mode(ch)` + `get_source(ch)`
- 返回：`{"BaseColor": {"opacity": 1.0, "blend_mode": "Normal", "source": "#FF0000"}, "Roughness": {"opacity": 1.0, "blend_mode": "Normal", "source": 0.5}, ...}`
- mock：利用已有的 `get_opacity` / `get_blending_mode` + 新增的 `get_source`
- 测试：add_fill_layer 设 roughness → get_layer_channels 验证

**改动文件：** `conftest.py`（+10 行改 set_source）、`handlers.py`（+30 行）、`sp_mcp.py`（+25 行）、`test_handlers_mock.py`（+20 行）、`mcp.json`（+2 tools）

---

### Phase 6 验收标准

- `pytest tests/ -m "not integration"` 全绿（预计 56 + ~25 = 81+ tests）
- 7 个新 tool 均有 mock 测试 + server 测试
- 4 个补测 handler 均有测试覆盖
- `PHASES.md` 更新 Phase 6 状态为 ✅
- `AGENTS.md` 更新 tool 列表为 23 个

---

## Phase 7 — 图层高级 + TextureSet + 项目 + 相机

**状态：** ✅ 完成

**目标：** 新增 11 个 tool，覆盖图层复制/移动/分组/解散、纹理集管理、项目操作、相机控制。

### 任务 7.1 — 图层高级操作（4 tools）

**`sp_duplicate_layer(layer_id)`**

- handler：
  1. `_find_layer(layer_id)` 获取源节点
  2. 读取属性：`get_name()`, `get_opacity(ch)`, `get_blending_mode(ch)`, `get_source(ch)`（各通道）
  3. `ls.insert_fill(ls.InsertPosition.above_node(src))` 创建新节点
  4. 复制所有属性到新节点
- mock：组合现有 API，无新增 mock
- 测试：duplicate → 验证图层树中有两个同名节点

**`sp_move_layer(layer_id, target_id, position)`**

- handler：
  1. 找到两个节点
  2. `ls.move_node(node, ls.InsertPosition.above_node(target))` 或 `below_node(target)`
- mock 需新增：`ls.move_node(node, pos)` → 从当前父级删除 → 在 pos 位置插入
- 测试：move 后验证顺序变化

**`sp_group_layers(layer_ids)`**

- handler：
  1. 找到所有节点（按图层树顺序）
  2. `ls.insert_group(ls.InsertPosition.above_node(first))` 创建空组
  3. 依次 `ls.move_node(child, ls.InsertPosition.inside_node(group, group.get_stack()))` 移入组
- mock：组合 `insert_group` + `move_node`
- 测试：group 后验证子节点在组内

**`sp_ungroup_layer(layer_id)`**

- handler：
  1. 找到组节点
  2. 遍历 `group.sub_layers()` → `ls.move_node(child, ls.InsertPosition.above_node(group))`
  3. `ls.delete_node(group)`
- mock：组合 `move_node` + `delete_node`
- 测试：ungroup 后验证子节点提升到父级，组已删除

**改动文件：** `conftest.py`（+15 行 move_node）、`handlers.py`（+60 行）、`sp_mcp.py`（+50 行）、`test_handlers_mock.py`（+40 行）、`mcp.json`（+4 tools）

---

### 任务 7.2 — TextureSet 管理 + 项目（4 tools）

**`sp_set_active_texture_set(name)`**

- handler：
  1. `ts.all_texture_sets()` 遍历找 `t.name() == name`
  2. `ts.set_active_stack(t.get_stack())`
- mock 需新增：
  - `textureset.set_active_stack(stack)` → 更新全局 `_mock_stack`
  - conftest 6.0 中已补全的 `all_texture_sets()` 返回 mock 对象
- 测试：切换后 `get_active_stack()` 返回新 stack

**`sp_set_texture_set_resolution(width, height)`**

- handler：
  1. `ts.get_active_stack()` → 找到当前 textureset
  2. `ts.set_resolution(width, height)`
- mock 需新增：`textureset.set_resolution(w, h)` → 存储到 textureset 对象
- 测试：设置后 get_resolution 返回新值

**`sp_get_project_info()`**

- handler：
  ```python
  import substance_painter.project as proj
  return {
      "name": proj.name(),
      "file_path": proj.file_path(),
      "color_space": proj.color_space(),
  }
  ```
- mock 需新增：`substance_painter.project` 模块
  - `name()` → `"MockProject"`
  - `file_path()` → `"/mock/project.spp"`
  - `color_space()` → `"sRGB"`
  - `save()` → 无操作
- 测试：调用返回预期结构

**`sp_save_project()`**

- handler：`project.save()` → `{"ok": true}`
- mock：同上 `project.save()`
- 测试：调用无异常

**改动文件：** `conftest.py`（+25 行 project 模块 + textureset 完善）、`handlers.py`（+40 行）、`sp_mcp.py`（+40 行）、`test_handlers_mock.py`（+30 行）、`mcp.json`（+4 tools）

---

### 任务 7.3 — 相机 + 环境（3 tools）

**需要先探索的 API：**
```python
# 用 sp_run_python 在 Painter 中探索
import substance_painter.camera; print(dir(substance_painter.camera))
import substance_painter.environment; print(dir(substance_painter.environment))
```

**`sp_set_camera(x, y, z, target_x, target_y, target_z, fov)`**

- handler：根据探索结果实现（可能是 `camera.set_position()` / `camera.set_target()` 或 UI 操作）
- mock 需新增：`substance_painter.camera` 模块
- 测试：调用无异常

**`sp_frame_mesh()`**

- handler：`camera.frame_all()` 或等效 API
- mock：同上
- 测试：调用无异常

**`sp_set_environment(preset)`**

- handler：切换 HDRI 环境光预设
- mock 需新增：`substance_painter.environment` 模块
- 测试：调用无异常

**注意：** camera/environment API 未经探索，实际签名可能不同。
实现时先用 `sp_run_python` 探索真实 API，再调整 mock 和 handler。

**改动文件：** `conftest.py`（+20 行）、`handlers.py`（+30 行）、`sp_mcp.py`（+30 行）、`test_handlers_mock.py`（+15 行）、`mcp.json`（+3 tools）

---

### Phase 7 验收标准

- `pytest tests/ -m "not integration"` 全绿（预计 81 + ~35 = 116+ tests）
- 11 个新 tool 均有 mock 测试 + server 测试
- `PHASES.md` 更新 Phase 7 状态为 ✅
- `AGENTS.md` 更新 tool 列表为 34 个
- 所有新 tool 写入 `mcp.json`
- 相关 SKILL.md 更新

---

## Phase 8 — 批量 Undo（ScopedModification）

**状态：** ✅ 完成

**目标：** 将 LLM 发起的多个 layer 操作合并为单条 undo，用户在 SP 里按一次 Ctrl+Z 即可撤销整批操作。

**已验证：**
- `ls.ScopedModification("name")` 支持手动 `__enter__()` / `__exit__()`
- 批量内操作合并为 1 条 undo 条目（实测 Ctrl+Z 一次撤销 2 个 insert_fill）
- 跨 HTTP 调用保持 batch 打开状态可行（`_batch_scope` 全局变量）

**任务 8.1 — 实现 handler：**

```python
# handlers.py
_batch_scope = None

def begin_batch(name: str) -> dict:
    global _batch_scope
    if _batch_scope is not None:
        raise RuntimeError("A batch is already active. Call end_batch() first.")
    import substance_painter.layerstack as ls
    _batch_scope = ls.ScopedModification(name)
    _batch_scope.__enter__()
    return {"ok": True, "batch_name": name}

def end_batch() -> dict:
    global _batch_scope
    if _batch_scope is None:
        raise RuntimeError("No active batch. Call begin_batch() first.")
    _batch_scope.__exit__(None, None, None)
    _batch_scope = None
    return {"ok": True}
```

**任务 8.2 — MCP tool 定义：**

```python
# sp_mcp.py
@mcp.tool()
def sp_begin_batch(name: str) -> dict:
    """开始批量操作。后续 layer 操作将合并为单条 undo。"""

@mcp.tool()
def sp_end_batch() -> dict:
    """结束批量操作，合并为单条 undo。"""
```

**任务 8.3 — mock + 测试：**

- conftest.py：mock `ScopedModification`（`__enter__` / `__exit__` 有状态记录）
- test_handlers_mock.py：测试 begin → 操作 → end 流程、未 begin 就 end 报错、重复 begin 报错
- test_server_tools.py：server tool 参数校验

**任务 8.4 — Live 验证：**

1. `sp_begin_batch("Test Batch")`
2. `sp_add_fill_layer("A")` + `sp_add_fill_layer("B")`
3. `sp_end_batch()`
4. 在 SP 按 Ctrl+Z → 两个图层一起消失

**验收标准：**
- 146+ 测试全绿
- Live 验证 Ctrl+Z 撤销批量操作
- PHASES.md 更新 Phase 8 状态为 ✅

---

## Phase 9 — JS API 集成（Baking + 通道管理）

**状态：** ✅ 完成

**目标：** 通过 `sp.js.evaluate()` 调用 SP 的 `alg` JS API，补上 Python API 缺失的功能。

**已验证可用的 JS API：**

| JS API | 功能 | 测试结果 |
|--------|------|---------|
| `alg.baking.bake(textureSetName)` | 烘焙 mesh maps | ✅ 返回 `{}`（成功） |
| `alg.texturesets.getActiveTextureSet()` | 获取活动纹理集 | ✅ 返回 `["name"]` |
| `alg.texturesets.addChannel(...)` | 添加通道 | ✅ 函数存在 |
| `alg.texturesets.editChannel(...)` | 编辑通道 | ✅ 函数存在 |
| `alg.texturesets.removeChannel(...)` | 删除通道 | ✅ 函数存在 |
| `alg.texturesets.setResolution(...)` | 设置分辨率 | ✅ 函数存在 |
| `alg.mapexport.save(path)` | 导出贴图 | ✅ 需要路径参数 |
| `alg.project.isOpen()` / `name()` | 项目信息 | ✅ 正常 |
| `alg.ui.clickButton(name)` | 点击 UI 按钮 | ⚠️ 有 findChild 错误 |

**任务 9.1 — 烘焙 Mesh Maps：**

```python
# handlers.py
def bake_mesh_maps(texture_set_name: str) -> dict:
    """通过 JS API 烘焙指定纹理集的 mesh maps。"""
    import substance_painter.js as js
    js.evaluate(f'alg.baking.bake("{texture_set_name}")')
    return {"ok": True, "texture_set": texture_set_name}
```

**任务 9.2 — Texture Set 通道管理：**

```python
# handlers.py
def add_texture_set_channel(texture_set_name: str, channel_id: str, 
                             channel_format: str = "Color4",
                             channel_label: str = "") -> dict:
    """通过 JS API 给纹理集添加通道。"""
    import substance_painter.js as js
    label = channel_label or channel_id
    js.evaluate(f'alg.texturesets.addChannel("{texture_set_name}", '
                f'"{channel_id}", "{channel_format}", "{label}")')
    return {"ok": True}

def remove_texture_set_channel(texture_set_name: str, channel_id: str) -> dict:
    """通过 JS API 删除纹理集通道。"""
    import substance_painter.js as js
    js.evaluate(f'alg.texturesets.removeChannel("{texture_set_name}", "{channel_id}")')
    return {"ok": True}
```

**任务 9.3 — Undo/Redo 探索（可选）：**

`alg.ui.clickButton("Undo")` 存在但报 `findChild` 错误。需要进一步探索：
- 可能需要先初始化 JS 上下文
- 可能需要传入不同的按钮标识符
- 如果无法解决，保持 `NotImplementedError`

**任务 9.4 — mock + 测试：**

- conftest.py：mock `substance_painter.js` 模块（`evaluate` 函数）
- test_handlers_mock.py：测试 bake / add_channel / remove_channel
- test_server_tools.py：server tool 参数校验

**验收标准：**
- 166+ 测试全绿
- `sp_bake_mesh_maps` live 验证（烘焙一次确认）
- `sp_add_texture_set_channel` / `sp_remove_texture_set_channel` live 验证
- PHASES.md 更新 Phase 9 状态为 ✅
- AGENTS.md 更新 tool 列表

---

## Phase 10 — Undo/Redo 探索

**状态：** ✅ 完成

**发现：** SP 原生 undo 栈会跟踪 Python layerstack API 操作，无需外置栈或 QML 插件。

**验证：**
- `add_fill_layer()` → UNDO action enabled, text="新建 填充图层"
- `set_layer_property()` → UNDO action enabled, text="撤销 图层节点不透明度"
- `delete_layer()` → UNDO action enabled, text="撤销 删除节点"
- `ScopedModification` → 自定义 undo 名称

**实现：** 通过 `QAction(objectName="UNDO").trigger()` 直接触发 SP 原生 undo/redo。

---

## Phase 11 — Undo/Redo（已删除）

**状态：** ✅ 已删除（改用 SP 原生 undo/redo）

**原方案：** 外置 Python 栈记录逆操作
**现方案：** 直接调用 SP 原生 undo/redo，代码更简洁，与 SP UI 完全同步。

---

## Phase 12 — 自动 batch + 文件重构

**状态：** ✅ 完成

**目标：** 每个图层修改 API 调用自动包裹 `ScopedModification`，确保 1 次调用 = 1 条 undo；同时将 plugin .py 文件整合到 `sp_bridge/` 子目录。

### 任务 12.1 — `_auto_batch()` 上下文管理器

```python
@contextlib.contextmanager
def _auto_batch(name: str):
    """如果外部 batch 已激活则跳过，否则用 ScopedModification 自动包裹。"""
    if _batch_scope is not None:
        yield; return
    scope = ls.ScopedModification(name)
    scope.__enter__()
    try: yield
    finally: scope.__exit__(None, None, None)
```

### 任务 12.2 — 包裹所有图层修改 handler

| handler | batch 名称 | 原 undo 数 | 现 undo 数 |
|---------|-----------|-----------|-----------|
| `add_fill_layer` | `"Add Fill Layer 'xxx'"` | 4-5 | 1 |
| `add_group_layer` | `"Add Group Layer 'xxx'"` | 2 | 1 |
| `add_paint_layer` | `"Add Paint Layer 'xxx'"` | 2 | 1 |
| `delete_layer` | `"Delete layer"` | 1 | 1 |
| `set_layer_property` | `"Set layer {prop}"` | 1 | 1 |
| `set_layer_channel` | `"Set {channel} channel"` | 1 | 1 |
| `duplicate_layer` | `"Duplicate layer"` | 多 | 1 |
| `apply_smart_material` | `"Apply Smart Material 'xxx'"` | 多 | 1 |
| `add_smart_mask` | `"Add Smart Mask 'xxx'"` | 多 | 1 |
| `apply_material` | `"Apply Material 'xxx'"` | 多 | 1 |

**嵌套兼容：** `_auto_batch` 检测 `_batch_scope`，外层有 `begin_batch/end_batch` 时自动跳过。

### 任务 12.3 — 文件重构

```
plugin/                →  plugin/
├── __init__.py  (删)      ├── sp_bridge/
├── bridge.py    (删)      │   ├── __init__.py
├── handlers.py  (删)      │   ├── bridge.py
└── js/                    │   └── handlers.py
                           └── js/
```

相对导入自动适配（`from . import bridge` / `from . import handlers`），测试导入更新为 `from plugin.sp_bridge import handlers`。

### 验收标准

- 182 测试全绿
- PHASES.md / AGENTS.md / README.md 文档同步更新
- README 添加 for-the-badge 依赖徽章

---

## Phase 13 — 四功能复现（move/group/ungroup/frame）

**状态：** ✅ 完成

**目标：** 用 delete+re-insert 工作流复现 SP 10.x 缺 Python API 的四个操作。

### 新发现 API

| API | 路径 | 说明 |
|-----|------|------|
| `get_node_by_uid(uid: int)` | `substance_painter.layerstack` | 按 int UID 查找节点 |
| `node.get_parent()` | Node | 返回父节点或 None |
| `node.get_next_sibling()` | Node | 返回下一个兄弟节点或 None |
| `node.get_previous_sibling()` | Node | 返回上一个兄弟节点或 None |
| `get_scene_bounding_box()` | `substance_painter.project` | 返回 BoundingBox(center, dimensions, radius) |
| `InsertPosition.inside_node(node, NodeStack.Substack)` | layerstack | 在组的子层栈中插入 |

### 实现方式

| 功能 | 方案 |
|------|------|
| `move_layer` | `_clone_node(src, pos)` → delete src → 1 条 undo |
| `group_layers` | `insert_group` → `inside_node(group, Substack)` → clone 每个节点 → delete 原节点 |
| `ungroup_layer` | 遍历 `sub_layers()` → clone 到 group 位置 → delete child → delete group |
| `frame_mesh` | `get_scene_bounding_box()` → 计算距离 = radius / tan(fov/2) * 1.2 → 设置 camera.position |

**辅助函数：**
- `_clone_node(src_node, insert_pos)` — 在指定位置创建同类型节点的完整深拷贝
- `_copy_channels(src, dst)` — 复制所有 5 个通道的 opacity/blend/source

**验收：** 187 测试全绿，4 个功能 live 验证通过。

---

## Phase 14 — Computer Use

**状态：** ✅ 完成

**目标：** 实现 mini Computer Use 能力——截取 SP 完整窗口界面、控制鼠标和键盘，供 LLM 视觉模型驱动 SP UI。

### 发现的 API/能力

| 能力 | 实现方式 |
|------|---------|
| 全窗口截图 | `main_window.grab()` → QPixmap → PNG → base64 |
| 区域截图 | `main_window.grab(QRect)` |
| 窗口信息 | `main_window.geometry()` / `mapToGlobal()` / `isMinimized()` 等 |
| 鼠标移动 | `ctypes.windll.user32.SetCursorPos(x, y)` |
| 左/右/中/双击 | `ctypes.windll.user32.mouse_event(MOUSEEVENTF_*)` |
| 拖拽 | `SetCursorPos` + `mouse_event(LDOWN)` + `SetCursorPos` + `mouse_event(LUP)` |
| 滚轮 | `mouse_event(MOUSEEVENTF_WHEEL, delta)` |
| 键盘 | `ctypes.windll.user32.keybd_event(vk, 0, ...)` |
| 组合键 | keybd_event 按下修饰键 → 发送按键 → 释放修饰键 |
| 等待 | `time.sleep()` |

### 实现的新 MCP Tools（7 个）

| Tool | 参数 | 功能 |
|------|------|------|
| `sp_window_info` | 无 | 返回窗口位置/尺寸/状态 |
| `sp_window_grab` | `region?` | 全窗口/区域截图 → base64 PNG |
| `sp_window_focus` | 无 | 聚焦 SP 窗口 + 显示红色警示条 |
| `sp_cu_unlock` | 无 | 解除锁定 + 隐藏警示条 |
| `sp_mouse_move` | `x, y, relative?` | 移动鼠标（屏幕/窗口坐标） |
| `sp_mouse_click` | `x?, y?, button?, clicks?, relative?` | 点击（左/右/中，单击/双击） |
| `sp_mouse_scroll` | `amount` | 滚轮（正值=上，负值=下） |
| `sp_mouse_drag` | `x1, y1, x2, y2, button?, relative?` | 拖拽 A→B |
| `sp_key_send` | `keys, modifiers?` | 单键/组合键/打字 |
| `sp_shortcut` | `action` | 预定义快捷键封装 |

### 键名支持

导航：enter, tab, esc, space, backspace, delete, home, end, pageup, pagedown, left, right, up, down

修饰：ctrl, shift, alt

功能：f1-f12

普通字符直接传输（如 `"Hello"` → 逐键打出 H-e-l-l-o）

### 已知限制

- `alg.ui.clickButton()` — SP 10.0.1 内部 bug（`findChild of undefined`），不可用，Computer Use 通过鼠标点击绕过了此限制
- 窗口截图仅限 SP 窗口内，无法截桌面其他区域
- 激活窗口/置顶可能受 Windows 限制

### 验收

- 10 个 handler + 10 个 MCP tool + 12 个新测试（sp_shortcut）
- 248 测试全绿（含已有 207）
- handlers.py 增长 ~250 行，sp_mcp.py 增长 ~140 行

---

## Phase 13b — 程序化源参数控制 + 相机/显示增强

**状态：** ✅ 完成

**程序化源（SourceSubstance）参数控制（7 tools）：**

| Tool | 功能 |
|------|------|
| `get_source_info(layer_id, channel?)` | 读取填充图层/效果的源信息（类型/颜色/资源/参数） |
| `get_substance_parameters(layer_id, channel?)` | 读取程序化源当前参数值 + 类型/描述 |
| `set_substance_parameters(layer_id, params, channel?)` | 批量修改源参数（`PropertyValue` 包装） |
| `get_substance_presets(layer_id, channel?)` | 列出源的可用预设 |
| `apply_substance_preset(layer_id, preset_name, channel?)` | 应用预设 |
| `get_source_outputs(layer_id, channel?)` | 读取输出映射 |
| `set_source_output(layer_id, output_id, channel?)` | 切换活动输出 |

> 仅 `FillLayerNode` / `FillEffectNode` 且源为 `SourceSubstance` 时支持，否则抛 `ValueError`。

**相机与显示增强（6 tools）：**

| Tool | 功能 |
|------|------|
| `get_camera()` | 读取主相机完整状态（position/rotation/fov） |
| `get_tone_mapping()` / `set_tone_mapping(function)` | 色调映射（Linear/ACES） |
| `get_color_lut()` / `set_color_lut(resource_name)` | 色彩 LUT 配置 |
| `get_scene_bounding_box()` | 场景包围盒（center/dimensions/radius） |

---

## Phase 15 — 效果节点

**状态：** ✅ 完成

**目标：** 通过 `layerstack.insert_*_effect` 在图层 Content / Mask 栈插入效果节点。

### 实现的 MCP Tools（9 个）

| Tool | 插入位置 | 说明 |
|------|---------|------|
| `add_filter_effect(layer_id, filter_name?)` | Content | Filter 效果，可指定资源 |
| `add_generator_effect(layer_id, generator_name?)` | Content | Generator 效果 |
| `add_levels_effect(layer_id)` | Content | Levels 色阶 |
| `add_compare_mask_effect(layer_id)` | Mask | Compare Mask |
| `add_color_selection_effect(layer_id)` | Mask | Color Selection |
| `add_anchor_point_effect(layer_id, anchor_name?)` | Content | Anchor Point |
| `get_effect_parameters(layer_id)` | — | 读取 Levels/CompareMask/ColorSelection/Filter/Generator 参数 |
| `get_selected_nodes(texture_set_name?)` | — | 获取当前选中节点 |
| `set_selected_nodes(node_ids)` | — | 设置选中节点 |

### 新发现 API

| API | 说明 |
|-----|------|
| `ls.insert_filter_effect / insert_generator_effect / insert_levels_effect` | 在 `NodeStack.Content` 插入 |
| `ls.insert_compare_mask_effect / insert_color_selection_effect` | 在 `NodeStack.Mask` 插入 |
| `ls.insert_anchor_point_effect(pos, name)` | 锚点需要名称参数 |
| `ls.get_selected_nodes(stack)` / `ls.set_selected_nodes(nodes)` | 选区读写 |

---

## Phase 16 — 烘焙 API（Python 原生）

**状态：** ✅ 完成

**目标：** 用 `substance_painter.baking` 原生 API 替代 Phase 9 的 `sp_bake_mesh_maps`（JS 方案），
提供完整的参数读写 + 状态控制 + 异步执行。

### 实现的 MCP Tools（5 个）

| Tool | 功能 |
|------|------|
| `get_baking_parameters(ts_name)` | 读取 common + 各 baker + 曲率方法 + 启用项 |
| `set_baking_parameters(ts_name, common?, baker?)` | 设置烘焙参数 |
| `bake_texture_set(ts_name)` | 异步启动烘焙 |
| `get_baking_state(ts_name)` | 读取启用状态/曲率方法/bakers/UV tiles |
| `set_baking_state(ts_name, ...)` | 设置启用状态/曲率方法/bakers/UV tiles |

### 新发现 API

| API | 说明 |
|-----|------|
| `baking.BakingParameters.from_texture_set_name(name)` | 入口 |
| `bp.common()` / `bp.baker(MeshMapUsage)` | 参数字典（`{name: Property}`） |
| `bp.get_curvature_method()` / `bp.get_enabled_bakers()` / `bp.get_enabled_uv_tiles()` | 状态读取 |
| `textureset.MeshMapUsage` | baker 枚举（AO/Curvature/Normal/...） |

> Phase 9 的 `sp_bake_mesh_maps`（JS `alg.baking.bake`）保留，作为快速一键烘焙的备选。

---

## Phase 17 — 项目生命周期 + 元数据 + 资源发现

**状态：** ✅ 完成

### 实现的 MCP Tools（8 个）

| Tool | 功能 |
|------|------|
| `create_project(mesh_path, ...)` | 创建新项目（网格/法线格式/工作流/UV tile） |
| `open_project(file_path)` | 打开 .spp |
| `close_project()` | 关闭当前项目 |
| `reload_mesh(mesh_path, ...)` | 异步重载网格 |
| `get_project_metadata(context, key)` | 读取持久化元数据 |
| `set_project_metadata(context, key, value)` | 写入持久化元数据 |
| `list_project_metadata(context)` | 列出某 context 下所有键 |
| `list_resources_by_usage(usage, search?)` | 按用途类型列资源（filter/generator/substance/...） |

### 新发现 API

| API | 说明 |
|-----|------|
| `project.create(mesh_file_path=..., settings=ProjectCreationSettings(...))` | 创建项目 |
| `project.Metadata(context)` → `.set/get/list_keys` | 项目级持久化元数据 |
| `project.reload_mesh(path, settings)` | 异步重载，配 `ProjectCreationSettings` |
| `resource.Usage` 枚举 | 资源用途分类 |

### 当前工具规模

**MCP tools 总计 92 个**（与 `server/sp_mcp.py` 的 `@mcp.tool()` 数量、
`handlers.py` 的 `_REGISTRY` 条目数一一对应）。新增工具时三处需同步：
`sp_mcp.py`（tool 定义）+ `handlers.py`（handler + 注册表）+ 对应 `.opencode/skills`。

---

## 探索未知 API 的标准流程

遇到任何不确定的 API，按此顺序探索：

```python
# 1. 看模块有什么
sp_run_python: "import substance_painter.XXX; print(dir(substance_painter.XXX))"

# 2. 看具体对象有什么方法
sp_run_python: "
import substance_painter.layerstack as ls
stack = ls.get_stack()
nodes = ls.get_root_layer_nodes(stack)
if nodes:
    node = nodes[0]
    print(type(node).__name__)
    print(dir(node))
"

# 3. 看文档字符串
sp_run_python: "
import substance_painter.layerstack as ls
print(ls.get_stack.__doc__)
"
```

**原则：** 宁可多探索一步确认 API，不要假设后写错再改。
