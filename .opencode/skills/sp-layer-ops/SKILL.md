---
name: sp-layer-ops
description: 调用 MCP tools 操作 Substance Painter 图层栈，包括新建图层、
             修改材质属性、应用 Smart Material/普通材质、添加 Smart Mask、
             批量 Undo。调色/材质参数调整、图层增删改类任务触发此 skill。
---

# SP Layer Operations

操作 Substance Painter 图层栈的 MCP tools 参考（38 tools）。

## API 速查表

### SP 10.x 关键事实

| 原假设 | 实际 API |
|---|---|
| `substance_painter.layers` | `substance_painter.layerstack` |
| `is_enabled()` / `set_enabled()` | `is_visible()` / `set_visible()` |
| `get_child_layers()` | `node.sub_layers()` (GroupLayerNode) |
| 节点类型 `node.get_type().name` | `type(node).__name__` → `"FillLayerNode"` / `"GroupLayerNode"` / `"PaintLayerNode"` |
| Scalar 通道用 `ls.Color` | 必须用 `colormanagement.Color(v,v,v)` |
| `node.get_source()` 返回 Color | 返回 `SourceUniformColor`，需 `.get_color().value_raw` 取值 |
| `move_node()` / `duplicate_node()` | SP 10.x 不存在，用 UI 操作 |
| `substance_painter.undo` | 不存在，用 `ScopedModification` 批量合并 + 用户 Ctrl+Z |
| `substance_painter.camera` | 不存在，相机 API 在 `substance_painter.display.Camera` |
| `ScopedModification` 只能 `with` | 支持手动 `__enter__()` / `__exit__()` 跨 HTTP 调用 |

---

## Tool 参考

### 连接

**`sp_ping`** — 检查 bridge 连通性。任何操作前必须先调用。

### 图层读取

**`sp_get_layer_stack`** — 返回完整图层树 JSON。GROUP 类型含 `children`（递归）。

**`sp_get_texture_sets(filter="")`** — 返回所有纹理集及其图层结构，支持名称过滤。

**`sp_get_layer_properties(layer_id)`** — 返回指定图层的详细属性。

**`sp_get_layer_channels(layer_id)`** — 返回所有通道的 opacity、blend_mode、source 值。

### 图层写入

**`sp_add_fill_layer(name, channel, color_hex, opacity, blend_mode)`** — 在图层栈顶部新建 Fill Layer。

| 参数 | 默认值 | 说明 |
|------|--------|------|
| name | 必填 | 语义化命名 |
| channel | "BaseColor" | BaseColor / Roughness / Metallic / Height / Normal |
| color_hex | "#FFFFFF" | 十六进制颜色 |
| opacity | 1.0 | 0.0–1.0，建议从 0.3–0.5 开始 |
| blend_mode | "Normal" | Normal / Multiply / Overlay / Screen |

**`sp_add_group_layer(name)`** — 新建空分组图层。

**`sp_add_paint_layer(name)`** — 新建绘画图层（PaintLayerNode）。

**`sp_set_layer_property(layer_id, prop, value)`** — 修改图层属性。prop: opacity / enabled / name / blend_mode。

**`sp_set_layer_channel(layer_id, channel, value)`** — 为指定通道设定数值。
- channel: `"Roughness"` / `"Metallic"` / `"Height"` / `"BaseColor"` / `"Normal"`
- 非 BaseColor 通道 value 为 float (0.0–1.0)
- BaseColor 为 hex color (`"#FF0000"`)

**`sp_delete_layer(layer_id)`** — 删除指定图层。

**`sp_duplicate_layer(layer_id)`** — 复制图层，新图层在原图层上方。

**`sp_move_layer(layer_id, target_id, position)`** — ⚠️ SP 10.x 无 API，NotImplementedError。用 UI 拖拽。

**`sp_group_layers(layer_ids)`** — ⚠️ SP 10.x 无 API，NotImplementedError。用 Ctrl+G。

**`sp_ungroup_layer(layer_id)`** — ⚠️ SP 10.x 无 API，NotImplementedError。用 Ctrl+Shift+G。

### Smart Material（需要 SP 10.0+）

**`sp_list_shelf_materials(filter="")`** — 列出可用 Smart Material，支持关键词过滤。

**`sp_apply_smart_material(layer_id, material_name)`** — 对指定图层应用 Shelf 中的 Smart Material。

**`sp_add_smart_mask(layer_id, mask_name)`** — 为图层添加程序化遮罩。
常用 mask_name：`"Dirt"` / `"Rust"` / `"Edge Damage"` / `"Dust"` / `"Edges Scratched"`

### 普通材质（需要 SP 10.0+）

**`sp_list_materials(filter="")`** — 列出可用普通材质（SUBSTANCE 类型），支持关键词过滤。SP 中有 917+ 个。

**`sp_apply_material(layer_id, material_name)`** — 将普通材质应用到指定图层的所有通道。
调用前先用 `sp_list_materials` 确认名称。

### 批量 Undo

**`sp_begin_batch(name)`** — 开始批量操作，后续 layer 操作合并为单条 undo。

**`sp_end_batch()`** — 结束批量操作，合并为单条 undo。

```
sp_begin_batch("Apply Rust Effect")
  sp_add_fill_layer("Rust_Base")
  sp_set_layer_channel("xxx", "Roughness", 0.8)
  sp_add_smart_mask("xxx", "Rust")
sp_end_batch()
→ 用户按 Ctrl+Z 一次撤销全部操作
```

### Texture Set

**`sp_set_active_texture_set(name)`** — 切换当前操作的纹理集。

**`sp_set_texture_set_resolution(width, height)`** — 修改当前纹理集分辨率。

### 项目

**`sp_get_project_info()`** — 读取项目名、路径、is_open、is_busy。

**`sp_save_project()`** — 保存当前项目。

### 视觉反馈

**`sp_capture_viewport(mode="quick")`** — 截取 viewport。mode: `"quick"` (迭代) / `"render"` (Iray)。

**`sp_set_camera(x,y,z, target_x,target_y,target_z, fov)`** — 设置相机位置和视角。

**`sp_set_environment(preset)`** — 切换 HDRI 环境光预设。

### Iray 渲染

**`sp_set_iray_params(max_samples, max_time, width, height)`** — 设置 Iray 参数。

**`sp_start_iray_render()`** — 异步启动 Iray 渲染。

**`sp_check_iray_render()`** — 检查渲染状态。

### 导出

**`sp_export_textures(preset, output_dir)`** — 触发贴图导出。

### Escape hatch

**`sp_run_python(code)`** — 在主线程执行任意 Python。仅作备用。

---

## 常见错误

| 错误 | 原因 | 解决 |
|------|------|------|
| `"Layer not found"` | layer_id 无效或已删除 | 重新调 `sp_get_layer_stack` |
| `"Smart Material not found"` | 名称拼写错误 | 先调 `sp_list_shelf_materials` 确认 |
| `"Material not found"` | 名称拼写错误 | 先调 `sp_list_materials` 确认 |
| `"Unknown channel"` | 通道名错误 | 可选: Roughness/Metallic/Height/BaseColor/Normal |
| `"This node already has a mask"` | 图层已有遮罩 | 先删除现有遮罩或换图层 |
| `"NotImplementedError"` | 该操作 SP 10.x 无 Python API | 用 UI 操作 |
