---
name: sp-project
description: 管理 Substance Painter 项目：读取项目信息、保存、批量操作、
             撤销/重做。用户提到保存/撤销/批量/项目信息时触发此 skill。
---

# SP Project Management

项目管理、批量操作、撤销/重做的工作流。

## ⚠️ 核心原则：先读后改

**任何操作前，必须先确认项目状态。**

| 操作前必读 | 说明 |
|---|---|
| `sp_get_project_info()` | 确认项目是否打开、是否忙碌 |
| `sp_get_layer_stack()` | 确认当前图层结构 |
| `sp_get_texture_sets()` | 确认纹理集状态 |

---

## 项目信息

**`sp_get_project_info()`** — 读取当前项目信息。

返回：
- `name` — 项目名称
- `file_path` — .spp 文件路径
- `is_open` — 是否已打开项目
- `is_busy` — 是否正在处理（渲染/导出中）

**注意：** `is_busy` 为 `true` 时，等待完成后再操作。

---

## 保存项目

**`sp_save_project()`** — 保存当前项目。

**建议保存时机：**
- 大量操作后
- 导出前
- 切换纹理集前
- 关闭 Painter 前

---

## 撤销/重做

**`sp_undo()`** — 撤销上一步操作。
**`sp_redo()`** — 重做上一步被撤销的操作。

基于 SP 原生 `QUndoStack`，用户在 Painter 按 Ctrl+Z / Ctrl+Y 也能同步撤销/重做 MCP 操作。

### Undo 栈机制

每个 layerstack API 操作（add/delete/modify）自动推入 SP undo 栈。

**单个 API = 1 条 undo：**
```
sp_add_fill_layer("Rust")        → undo 栈 +1
sp_set_layer_channel("xxx", ...) → undo 栈 +1
sp_add_smart_mask("xxx", ...)    → undo 栈 +1
→ 用户需按 3 次 Ctrl+Z 才能全部撤销
```

**批量操作 = 1 条 undo：**
```
sp_begin_batch("Apply Rust")
  sp_add_fill_layer("Rust")
  sp_set_layer_channel("xxx", ...)
  sp_add_smart_mask("xxx", ...)
sp_end_batch()
→ 用户按 1 次 Ctrl+Z 撤销整批
```

---

## 批量操作

**`sp_begin_batch(name)`** — 开始批量操作。
**`sp_end_batch()`** — 结束批量操作，合并为单条 undo。

### 规则

- 每个 `sp_begin_batch` 必须有对应的 `sp_end_batch`
- 批量内嵌套的 `sp_begin_batch` 会被自动跳过（不重复嵌套）
- 批量操作期间的**所有** layer 操作都会合并，包括读取操作（但读取不产生 undo）
- 超时限制：60 秒（bridge.py TIMEOUT）

### 推荐用法

```python
# 多个相关操作打包成一次 undo
sp_begin_batch("Apply Battle Worn Effect")
  sp_add_fill_layer("Base_Metal")
  sp_apply_material(layer_id, "Metal Polished")
  sp_set_layer_channel(layer_id, "Roughness", 0.7)
  sp_add_smart_mask(layer_id, "Edge Damage")
  sp_add_fill_layer("Rust_Overlay", opacity=0.3, blend_mode="Overlay")
  sp_add_smart_mask(rust_layer_id, "Rust")
sp_end_batch()
# 用户按 Ctrl+Z 一次撤销全部操作
```

### 何时用批量

| 场景 | 是否用批量 |
|------|-----------|
| 单个图层操作 | 不用 |
| 多个图层 + 通道 + 遮罩 | 用 |
| 试错探索 | 不用（方便单独撤销） |
| 确定的材质方案 | 用 |

---

## 典型工作流

### 完整材质制作流程

```
1. sp_ping()                           确认连接
2. sp_get_project_info()               确认项目状态
3. sp_get_texture_sets()               确认纹理集
4. sp_set_active_texture_set("target") 切换
5. sp_get_layer_stack()                确认图层
6. sp_begin_batch("Material Setup")
7.   sp_add_fill_layer("Base")
8.   sp_apply_material(...)
9.   sp_set_layer_channel(...)
10.  sp_add_smart_mask(...)
11. sp_end_batch()
12. sp_capture_viewport("quick")       确认效果
13. sp_save_project()                  保存
```

### 出错恢复

```
1. sp_undo()           撤销最后一步
2. sp_capture_viewport("quick")  确认回滚状态
3. 重新操作
```

### 多纹理集批量处理

```
1. sp_get_texture_sets()              列出所有
2. sp_begin_batch("Multi-set Update")
3. 对每个纹理集:
   sp_set_active_texture_set("name")
   sp_get_layer_stack()
   sp_add_fill_layer(...)
   sp_set_layer_channel(...)
4. sp_end_batch()
5. sp_save_project()
```

---

## Related Skills

- [sp-index](../sp-index/SKILL.md) — 所有 skill 的索引
- [sp-layer-ops](../sp-layer-ops/SKILL.md) — 图层操作 API（batch 包裹的对象）
- [sp-texture-set](../sp-texture-set/SKILL.md) — 纹理集管理
- [sp-quickstart](../sp-quickstart/SKILL.md) — 首次连接验证
- [sp-creative-workflow](../sp-creative-workflow/SKILL.md) — 批量操作在材质创作中的实际应用
