---
name: sp-layer-ops
description: 调用 MCP tools 操作 Substance Painter 图层栈，包括新建图层、
             修改材质属性、应用 Smart Material、添加 Smart Mask。
             调色/材质参数调整、图层增删改类任务触发此 skill。
---

# SP Layer Operations

操作 Substance Painter 图层栈的 MCP tools 参考。

## API 速查表

### SP 10.x 关键事实

| 原假设 | 实际 API |
|---|---|
| `substance_painter.layers` | `substance_painter.layerstack` |
| `substance_painter.__version__` | `substance_painter.application.version()` → `"10.0.1"` |
| `is_enabled()` / `set_enabled()` | `is_visible()` / `set_visible()` |
| `get_child_layers()` | `node.sub_layers()` (GroupLayerNode) |
| `get_root_layer_nodes()` 返回 int ID | 返回 `List[Node]` 节点对象 |
| 节点类型 `node.get_type().name` | `type(node).__name__` → `"FillLayerNode"` / `"GroupLayerNode"` |
| `get_opacity()` 无参数 | `get_opacity(ChannelType.BaseColor)` 需要 ChannelType |
| Smart Material 用 `layers` 模块 | `resource.search()` + `ls.insert_smart_material()` |
| Smart Mask 直接插入 | 需先 `node.add_mask(White)` 再 `insert_smart_mask()` |

---

## Tool 参考

### sp_ping

检查 bridge 连通性。**任何操作前必须先调用。**

```
返回: {"status": "ok", "sp_version": "10.0.1", "sdk_version": "0.3.0", "smart_api": true}
```

### sp_get_layer_stack

返回完整图层树 JSON。GROUP 类型含 `children` 列表（递归）。

```
返回: [
  {"id": "528", "name": "Metal_Base", "type": "FillLayerNode", "enabled": true, "opacity": 1.0},
  {"id": "258", "name": "Scratches", "type": "PaintLayerNode", "enabled": true, "opacity": 1.0}
]
```

**注意：** layer id 在 Painter 重启后会变化，不要跨 session 缓存。

### sp_get_layer_properties(layer_id)

返回指定图层的详细属性。

```
参数: layer_id (str) — 从 sp_get_layer_stack 获取
返回: {"id", "name", "type", "enabled", "opacity", "blending_mode"}
```

### sp_add_fill_layer(name, channel, color_hex, opacity, blend_mode)

在图层栈顶部新建 Fill Layer。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| name | str | 必填 | 语义化命名（如 "Rust_Overlay"） |
| channel | str | "BaseColor" | BaseColor / Roughness / Metallic / Height / Normal |
| color_hex | str | "#FFFFFF" | 十六进制颜色（仅 BaseColor 有效） |
| opacity | float | 1.0 | 0.0–1.0，建议从 0.3–0.5 开始 |
| blend_mode | str | "Normal" | Normal / Multiply / Overlay / Screen |

### sp_set_layer_property(layer_id, prop, value)

修改图层属性。

| prop | 值类型 | 说明 |
|------|--------|------|
| opacity | float (0–1) | 透明度 |
| enabled | bool | 可见性（is_visible/set_visible） |
| name | str | 图层名称 |
| blend_mode | str | 混合模式 |

### sp_apply_smart_material(layer_id, material_name)

对指定图层应用 Shelf 中的 Smart Material。需要 SP 10.0+。

```
参数:
  layer_id      目标图层 id
  material_name Smart Material 名称（先用 sp_list_shelf_materials 确认）
返回: {"id": "...", "name": "..."}
```

### sp_add_smart_mask(layer_id, mask_name)

为图层添加程序化遮罩。需要 SP 10.0+。

常用 mask_name：
- `"Edge Wear"` — 边缘磨损
- `"Dirt"` — 污垢
- `"Grunge Scratches"` — 划痕
- `"Rust"` — 锈迹

### sp_list_shelf_materials(filter)

列出可用 Smart Material，支持关键词过滤。

```
参数: filter (str) — 关键词，如 "metal"，空字符串返回全部
返回: ["Steel", "Copper", "Gold Armor", ...]
```

## 常见错误

| 错误 | 原因 | 解决 |
|------|------|------|
| `"Layer not found"` | layer_id 无效或已删除 | 重新调用 `sp_get_layer_stack` |
| `"Smart Material not found"` | 名称拼写错误 | 先调 `sp_list_shelf_materials` 确认 |
| `"opacity must be in [0.0, 1.0]"` | opacity 超范围 | 检查参数值 |
| `"Unknown blend mode"` | 混合模式不存在 | 可选值: Normal/Multiply/Overlay/Screen |
