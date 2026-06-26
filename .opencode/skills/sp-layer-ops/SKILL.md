---
name: sp-layer-ops
description: 调用 MCP tools 操作 Substance Painter 图层栈，包括新建图层、
             修改材质属性、应用 Smart Material/普通材质、添加 Smart Mask、
             批量 Undo。调色/材质参数调整、图层增删改类任务触发此 skill。
---

# SP Layer Operations

操作 Substance Painter 图层栈的 MCP tools 参考（92 tools 全覆盖）。

## ⚠️ 核心原则：先读后改

**任何操作前，必须先调用读取 tools 确认当前状态，不要假设或直接重置。**

| 操作前必读 | 说明 |
|---|---|
| `sp_get_texture_sets()` | 确认当前有哪些纹理集，选对目标 |
| `sp_get_layer_stack()` | 确认当前图层结构，找到正确的 layer_id |
| `sp_get_layer_channels(layer_id)` | 修改通道前，先看当前值 |
| `sp_get_layer_properties(layer_id)` | 修改属性前，先看当前值 |

**错误示范：** 直接 `sp_add_fill_layer` + `sp_apply_material` → 可能加到错误的纹理集/位置
**正确示范：** `sp_get_texture_sets` → `sp_set_active_texture_set` → `sp_get_layer_stack` → 确认 layer_id → 再操作

---

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
| `move_node()` / `duplicate_node()` | SP 10.x 不存在，`move_layer`/`group_layers`/`ungroup_layer` 用 delete+re-insert 工作流实现 |
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

**`sp_find_layer_by_name(name)`** — 在所有纹理集中按名称搜索图层（大小写不敏感）。
不知道 layer_id 时用它定位，返回 `matches` 列表（每项含 id/name/type/texture_set/depth）。

**`sp_add_mask(layer_id)`** — 为图层添加一个空白白色遮罩（非程序化）。
添加后可用 `sp_set_layer_channel` 调遮罩；要程序化磨损/脏迹用 `sp_add_smart_mask`。

**`sp_remove_mask(layer_id)`** — 移除图层的普通遮罩。
注意：Smart Mask 不走这里，需用 `sp_delete_layer` 删掉整个 mask effect。

**`sp_set_layer_property(layer_id, prop, value)`** — 修改图层属性。prop: opacity / visible(bool) / name / blend_mode。

**`sp_set_layer_channel(layer_id, channel, value)`** — 为指定通道设定数值。
- channel: `"Roughness"` / `"Metallic"` / `"Height"` / `"BaseColor"` / `"Normal"`
- 非 BaseColor 通道 value 为 float (0.0–1.0)
- BaseColor 为 hex color (`"#FF0000"`)

**`sp_delete_layer(layer_id)`** — 删除指定图层。

**`sp_duplicate_layer(layer_id)`** — 复制图层，新图层在原图层上方。

**`sp_move_layer(layer_id, target_id, position)`** — 移动图层到目标图层的上方或下方。
- `position`: `"above"`（默认）/ `"below"`
- **实现方式：** delete+re-insert 工作流（SP 10.x 无原生 `move_node` API）

**`sp_group_layers(layer_ids)`** — 将多个图层打包进新分组。
- `layer_ids`: 图层 id 列表（顺序任意，自动按栈顺序排列）
- **实现方式：** `insert_group` + clone 每个节点 + delete 原节点

**`sp_ungroup_layer(layer_id)`** — 解散分组，子层提升到父级。
- **实现方式：** clone 所有子节点到组位置 + delete 组

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

### 效果节点（Phase 15）

> 详情见 [sp-effect-nodes](../sp-effect-nodes/SKILL.md)。

| Tool | 说明 |
|------|------|
| `sp_add_filter_effect(layer_id, filter_name?)` | 添加 Filter 效果 |
| `sp_add_generator_effect(layer_id, generator_name?)` | 添加 Generator 效果 |
| `sp_add_levels_effect(layer_id)` | 添加 Levels 色阶效果 |
| `sp_add_compare_mask_effect(layer_id)` | 添加 Compare Mask 遮罩效果 |
| `sp_add_color_selection_effect(layer_id)` | 添加 Color Selection 遮罩效果 |
| `sp_add_anchor_point_effect(layer_id, anchor_name?)` | 添加 Anchor Point 锚点 |
| `sp_get_effect_parameters(layer_id)` | 读取效果节点参数 |
| `sp_get_selected_nodes(texture_set_name?)` | 获取当前选中节点 |
| `sp_set_selected_nodes(node_ids)` | 设置选中节点 |

### 程序化源控制（Phase 13）

> 详情见 [sp-substance-source](../sp-substance-source/SKILL.md)。

| Tool | 说明 |
|------|------|
| `sp_get_source_info(layer_id, channel?)` | 读取填充图层/效果的源信息 |
| `sp_get_substance_parameters(layer_id, channel?)` | 读取程序化源参数值 |
| `sp_set_substance_parameters(layer_id, params, channel?)` | 修改程序化源参数值 |
| `sp_get_substance_presets(layer_id, channel?)` | 列出程序化源预设 |
| `sp_apply_substance_preset(layer_id, preset_name, channel?)` | 应用预设 |
| `sp_get_source_outputs(layer_id, channel?)` | 获取输出映射 |
| `sp_set_source_output(layer_id, output_id, channel?)` | 切换活动输出 |

### 相机与显示（Phase 13–14）

| Tool | 说明 |
|------|------|
| `sp_get_camera()` | 读取主相机完整状态 |
| `sp_get_tone_mapping()` | 获取色调映射函数（Linear/ACES） |
| `sp_set_tone_mapping(function)` | 设置色调映射函数 |
| `sp_get_color_lut()` | 获取色彩 LUT 配置 |
| `sp_set_color_lut(resource_name)` | 设置色彩 LUT |
| `sp_get_scene_bounding_box()` | 获取场景包围盒 |

### 烘焙 API（Phase 16）

> 详情见 [sp-baking](../sp-baking/SKILL.md)。

| Tool | 说明 |
|------|------|
| `sp_get_baking_parameters(ts_name)` | 读取完整烘焙参数 |
| `sp_set_baking_parameters(ts_name, common?, baker?)` | 设置烘焙参数 |
| `sp_bake_texture_set(ts_name)` | 异步启动烘焙 |
| `sp_get_baking_state(ts_name)` | 获取烘焙启用状态 |
| `sp_set_baking_state(ts_name, ...)` | 设置烘焙状态/曲率方法/bakers/UV tiles |

### 项目生命周期（Phase 17）

| Tool | 说明 |
|------|------|
| `sp_create_project(mesh_path, ...)` | 创建新项目（网格/法线格式/工作流） |
| `sp_open_project(file_path)` | 打开已有 .spp 项目 |
| `sp_close_project()` | 关闭当前项目 |
| `sp_reload_mesh(mesh_path, ...)` | 异步重载网格 |
| `sp_get_project_metadata(context, key)` | 读取持久化元数据 |
| `sp_set_project_metadata(context, key, value)` | 写入持久化元数据 |
| `sp_list_project_metadata(context)` | 列出某 context 下所有键 |

### 资源发现（Phase 17b）

**`sp_list_resources_by_usage(usage, search?)`** — 按用途类型列出资源。
- `usage`：`"filter"` / `"generator"` / `"substance"` / `"smart_material"` / `"smart_mask"` / `"texture"` / `"environment"` / `"export_preset"`
- `search`：可选关键词过滤

---

## 常见错误

| 错误 | 原因 | 解决 |
|------|------|------|
| `"Layer not found"` | layer_id 无效或已删除 | 重新调 `sp_get_layer_stack` |
| `"Smart Material not found"` | 名称拼写错误 | 先调 `sp_list_shelf_materials` 确认 |
| `"Material not found"` | 名称拼写错误 | 先调 `sp_list_materials` 确认 |
| `"Unknown channel"` | 通道名错误 | 可选: Roughness/Metallic/Height/BaseColor/Normal |
| `"This node already has a mask"` | 图层已有遮罩 | 先删除现有遮罩或换图层 |
| `"name must not be empty"` | 图层名参数为空 | 传入非空字符串 |
| `"A batch is already active"` | `begin_batch` 重复调用 | 先 `end_batch` 结束上一个批量 |

---

## 图层移动与分组示例（Phase 13 实现）

> ⚠️ 这三个操作通过 **delete+re-insert** 工作流实现，操作后 layer_id 会变化，需重新调用 `sp_get_layer_stack`。

### 移动图层

```
sp_get_layer_stack()                           确认图层 ID
sp_move_layer(layer_id="111", target_id="222", position="above")
sp_get_layer_stack()                           重新读取新 ID
```

### 分组多个图层

```
sp_get_layer_stack()                           确认图层 ID
sp_group_layers(layer_ids=["111", "222", "333"])
sp_get_layer_stack()                           重新读取，找到新建的 GroupLayerNode
```

### 解散分组

```
sp_get_layer_stack()                           找到 GroupLayerNode 的 ID
sp_ungroup_layer(layer_id="999")
sp_get_layer_stack()                           重新读取，子层已提升到父级
```

### 搭配 batch 的完整工作流

```
sp_begin_batch("Reorganize Layers")
  sp_group_layers(layer_ids=["111", "222"])    先分组
  sp_move_layer(group_id, target_id, "above")  再移动
sp_end_batch()
→ 用户按 Ctrl+Z 一次撤销所有重组操作
```

---

## Related Skills

- [sp-index](../sp-index/SKILL.md) — 所有 skill 的索引
- [sp-smart-material](../sp-smart-material/SKILL.md) — Smart Material/Mask 选择策略和组合技巧
- [sp-creative-workflow](../sp-creative-workflow/SKILL.md) — 材质创作迭代循环 + 配方示例
- [sp-paint-layer](../sp-paint-layer/SKILL.md) — 绘画图层工作流
- [sp-project](../sp-project/SKILL.md) — 批量操作、撤销/重做
- [sp-texture-set](../sp-texture-set/SKILL.md) — 纹理集切换、烘焙
