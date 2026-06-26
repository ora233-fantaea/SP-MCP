---
name: sp-effect-nodes
description: 管理 Substance Painter 效果节点（Filter/Generator/Levels/Compare Mask/
             Color Selection/Anchor Point）。用户提到效果/滤镜/色阶/锚点/生成器
             /遮罩比较/颜色选择时触发此 skill。
---

# SP Effect Nodes

效果节点是 SP 图层栈中的程序化处理单元，可以插入到图层的效果栈或遮罩栈中，
实现色阶调整、通道比较、颜色过滤等非破坏性操作。

## ⚠️ 核心原则：先读后改

**任何操作前，必须先确认当前状态。**

| 操作前必读 | 说明 |
|---|---|
| `sp_get_layer_stack()` | 确认图层结构，找到目标 layer_id |
| `sp_get_effect_parameters(layer_id)` | 修改效果参数前，先读当前值 |
| `sp_get_selected_nodes()` | 确认当前选中了哪些节点 |

---

## 效果节点类型

| 类型 | 创建 Tool | 插入位置 | 用途 |
|------|----------|---------|------|
| **Filter** | `sp_add_filter_effect` | 图层效果栈 | 应用滤镜（模糊/锐化/色调等） |
| **Generator** | `sp_add_generator_effect` | 图层效果栈 | 程序化生成纹理/图案 |
| **Levels** | `sp_add_levels_effect` | 图层效果栈 | 调整通道色阶（黑白场/中间调） |
| **Compare Mask** | `sp_add_compare_mask_effect` | 图层 Mask 栈 | 比较两个通道生成遮罩 |
| **Color Selection** | `sp_add_color_selection_effect` | 图层 Mask 栈 | 按颜色/ID 选择区域生成遮罩 |
| **Anchor Point** | `sp_add_anchor_point_effect` | 图层效果栈 | 引用其他图层内容作为输入 |

---

## 添加效果节点

### Filter 效果

```
sp_add_filter_effect(layer_id, filter_name?)
```

- `filter_name`：可选，指定 filter 资源名称。不传则创建空的 Filter 效果
- 常用 filter：Blur、Sharpen、HSL、Invert 等
- **先查资源：** `sp_list_resources_by_usage(usage="filter", search="blur")`

### Generator 效果

```
sp_add_generator_effect(layer_id, generator_name?)
```

- `generator_name`：可选，指定 generator 资源名称
- 常用 generator：Noise、Gradient、Pattern、Text 等
- **先查资源：** `sp_list_resources_by_usage(usage="generator", search="noise")`

### Levels 效果

```
sp_add_levels_effect(layer_id)
```

- 添加色阶调整效果，可调节黑白场/中间调
- 添加后用 `sp_get_effect_parameters` 读取参数，再用 `sp_run_python` 修改

### Compare Mask 效果

```
sp_add_compare_mask_effect(layer_id)
```

- 在图层 **Mask 栈**中添加通道比较遮罩
- 比较两个输入通道（如 AO vs Curvature），按比较结果生成遮罩区域

### Color Selection 效果

```
sp_add_color_selection_effect(layer_id)
```

- 在图层 **Mask 栈**中添加颜色/ID 选择遮罩
- 按颜色值或 Mesh ID 选择特定区域

### Anchor Point 效果

```
sp_add_anchor_point_effect(layer_id, anchor_name?)
```

- 创建锚点引用，可被其他图层/效果通过资源链接引用
- `anchor_name` 默认 `"Anchor"`

---

## 读取效果参数

```
sp_get_effect_parameters(layer_id)
```

支持解析以下效果节点类型的参数：

| 节点类型 | 返回的关键参数 |
|---------|--------------|
| `LevelsEffectNode` | `affected_channel`, `levels` (含各通道的黑白场/中间调) |
| `CompareMaskEffectNode` | `operand`, `operation`, `background_color`, `threshold` |
| `ColorSelectionEffectNode` | `color`, `range`, `invert`, `background_color` |
| `FilterEffectNode` | source 信息（filter 资源名、参数） |
| `GeneratorEffectNode` | source 信息（generator 资源名、参数） |

**工作流：**
```
1. sp_get_layer_stack()                    找到效果节点的 layer_id
2. sp_get_effect_parameters(layer_id)      读取当前参数
3. [决策] 确定需要修改的参数
4. sp_run_python(...)                      直接修改参数
5. sp_capture_viewport("quick")            确认效果
```

---

## 节点选择

### 获取选中节点

```
sp_get_selected_nodes(texture_set_name?)
```

- 不传 `texture_set_name`：获取当前活动纹理集的选中节点
- 返回：`{"nodes": [{"id": "...", "name": "...", "type": "..."}], "count": N}`

### 设置选中节点

```
sp_set_selected_nodes(node_ids)
```

- `node_ids`：要选中的节点 ID 列表
- 用于在 SP UI 中高亮特定节点，方便后续 CU 操作

---

## 典型工作流

### 色阶调整流程

```
1. sp_get_layer_stack()                        找到目标图层
2. sp_add_levels_effect(layer_id)              添加 Levels 效果
3. sp_get_effect_parameters(effect_id)         读取默认参数
4. sp_run_python("...")                         调整黑白场/中间调
5. sp_capture_viewport("quick")                确认
```

### Filter + Generator 组合

```
1. sp_list_resources_by_usage("generator", "noise")  找合适的生成器
2. sp_add_generator_effect(layer_id, "Noise")        添加生成器效果
3. sp_list_resources_by_usage("filter", "blur")      找合适的滤镜
4. sp_add_filter_effect(layer_id, "Blur")            添加滤镜效果
5. sp_capture_viewport("quick")                      确认
```

### Mask 栈效果链

```
1. sp_add_compare_mask_effect(layer_id)       添加通道比较遮罩
2. sp_get_effect_parameters(effect_id)        读取比较参数
3. sp_run_python("...")                        调整为需要的比较逻辑
4. sp_add_color_selection_effect(layer_id)    叠加颜色选择遮罩
5. sp_capture_viewport("quick")               确认遮罩区域
```

---

## 效果节点的 Layer ID

⚠️ 效果节点插入后，其 `layer_id` 会变化（与普通图层不同）：
- 效果节点通过 `get_node_by_uid()` 查找
- 每次操作后重新调用 `sp_get_layer_stack()` 获取最新 ID
- 效果节点不在图层树中，而是挂在父节点的效果栈/Mask 栈上

---

## 常见错误

| 错误 | 原因 | 解决 |
|------|------|------|
| `"Layer not found"` | 效果节点 ID 已过期 | 重新 `sp_get_layer_stack` 获取 |
| `"does not support sources"` | 对非 Fill/Effect 节点读 source | 检查节点类型 |
| 效果节点不在图层树中 | 效果节点挂在父节点的栈上 | 用 `sp_get_effect_parameters` 读取 |
| Filter/Generator 名称无效 | 拼写错误或不存在 | 先用 `sp_list_resources_by_usage` 确认 |

---

## Related Skills

- [sp-index](../sp-index/SKILL.md) — 所有 skill 的索引
- [sp-layer-ops](../sp-layer-ops/SKILL.md) — 图层操作 API（效果节点插入的基础）
- [sp-smart-material](../sp-smart-material/SKILL.md) — 用 `sp_list_resources_by_usage` 发现可用资源
- [sp-creative-workflow](../sp-creative-workflow/SKILL.md) — 效果调整后的截图迭代
- [sp-debug](../sp-debug/SKILL.md) — `sp_run_python` 直接操作效果节点参数
