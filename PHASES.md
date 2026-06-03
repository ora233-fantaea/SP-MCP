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

遇到 API 不确定时，先用 `sp_run_python` 探索，再写实现。

---

## Phase 状态总览

| Phase | 内容 | 状态 |
|---|---|---|
| Phase 1 | Bridge 连通 | ✅ 完成 |
| Phase 2 | 核心图层工具 | ✅ 完成 |
| Phase 3 | 视觉反馈（截图） | ✅ 完成 |
| Phase 4 | Smart Material 创作工具 | ✅ 完成（Iray 留后续） |
| Phase 5 | Skills + Commands 补全 | ⬜ 待开始 |

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
- `capture_viewport(mode="render")` — 同 quick 的 Qt grab，返回 `"mode": "render"` 标记

**Iray 限制（已知）：**
- SP 10.x 无 Python API 触发 Iray 渲染
- `action.trigger()` 会阻塞 UI 线程导致 timeout
- 用户需手动触发 Iray（F10 或 Mode > Rendering），等待完成后调用 `capture_viewport(mode="render")` 截取结果

---

## Phase 5 — Skills + Commands 补全

**目标：** 把 Phase 2–4 探索出的真实 API 写进 Skills，
后续 session 不用重新探索。

**前提：** Phase 2–4 全部完成。

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
