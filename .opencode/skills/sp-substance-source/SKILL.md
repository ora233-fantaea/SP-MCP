---
name: sp-substance-source
description: 控制 Substance Painter 程序化源（Substance Source）：读写参数、
             列出/应用预设、管理输出映射。用户提到程序化材质参数/预设/源输出
             /调参数/substance 参数时触发此 skill。
---

# SP Substance Source Control

操作填充图层和效果节点的程序化源（Substance Source）——读写参数、切换预设、管理输出映射。

## ⚠️ 核心原则：先读后改

| 操作前必读 | 说明 |
|---|---|
| `sp_get_source_info(layer_id)` | 确认源类型、资源、当前模式 |
| `sp_get_substance_parameters(layer_id)` | 读取所有参数当前值 |
| `sp_get_substance_presets(layer_id)` | 列出可用预设 |

---

## 适用节点类型

源控制 API 适用于以下节点类型：
- `FillLayerNode` — 填充图层
- `FillEffectNode` — 填充效果
- `GeneratorEffectNode` — 生成器效果
- `FilterEffectNode` — 滤镜效果

---

## 读取源信息

```
sp_get_source_info(layer_id, channel?)
```

- `channel`：可选，指定通道（不传则返回所有通道的源信息）
- 返回源类型：Substance / UniformColor / Bitmap / Reference 等
- 返回源模式：`"Material"` / `"Decal"` / `"Image"` / `"Substance"` 等

---

## 读写参数

### 读取参数

```
sp_get_substance_parameters(layer_id, channel?)
```

返回所有参数的名称、当前值和类型。示例：
```json
{
  "layer_id": "123",
  "channel": "BaseColor",
  "parameters": {
    "roughness": {"value": 0.5, "type": "FLOAT1"},
    "metalness": {"value": 0.8, "type": "FLOAT1"},
    "color": {"value": [1.0, 0.2, 0.1], "type": "FLOAT3"}
  }
}
```

### 修改参数

```
sp_set_substance_parameters(layer_id, params, channel?)
```

- `params`：`{"参数名": 新值, ...}`，传入需要修改的参数即可，不用全量
- `channel`：可选，指定要修改的通道
- 自动包裹 `ScopedModification`，1 次调用 = 1 条 undo

**示例：**
```
// 修改粗糙度和金属度
sp_set_substance_parameters("abc123", {"roughness": 0.3, "metalness": 0.9})

// 修改指定通道的参数
sp_set_substance_parameters("abc123", {"color": [0.8, 0.2, 0.1]}, channel="BaseColor")
```

---

## 预设管理

### 列出预设

```
sp_get_substance_presets(layer_id, channel?)
```

返回程序化源的所有可用预设列表。一些 substance 自带数十个预设（不同的材质变体）。

### 应用预设

```
sp_apply_substance_preset(layer_id, preset_name, channel?)
```

- `preset_name`：必须与 `sp_get_substance_presets` 返回的名称完全一致
- 自动包裹 `ScopedModification`

**典型工作流：**
```
1. sp_get_substance_presets(layer_id)                 列出所有预设
2. sp_apply_substance_preset(layer_id, "Rusty Iron")  应用预设
3. sp_capture_viewport("quick")                       看效果
4. sp_get_substance_parameters(layer_id)              读取应用后的参数
5. sp_set_substance_parameters(layer_id, {...})       微调特定参数
6. sp_capture_viewport("quick")                       确认微调
```

---

## 输出映射

程序化源可以有多个输出（如一个 substance 同时输出 BaseColor、Normal、Roughness），
输出映射控制哪个输出连接到哪个通道。

### 读取输出映射

```
sp_get_source_outputs(layer_id, channel?)
```

返回：
```json
{
  "layer_id": "123",
  "image_outputs": ["Base_Color", "Normal", "Roughness", "Metallic", "Height"],
  "active_output": "Base_Color",
  "mask_output": null,
  "output_mapping": {
    "BaseColor": "Base_Color",
    "Normal": "Normal",
    "Roughness": "Roughness"
  }
}
```

### 切换活动输出

```
sp_set_source_output(layer_id, output_identifier, channel?)
```

- `output_identifier`：必须是 `image_outputs` 列表中的值
- 切换后图层的内容会变成新输出的结果

**使用场景：** 当程序的源有多个输出但当前只需要其中一个时，用此 API 选择。

---

## 参数类型参考

程序化源参数有不同数据类型，修改时传入对应格式的值：

| 类型 | Python 格式 | 示例 |
|------|-----------|------|
| `FLOAT1` | `float` | `0.5` |
| `FLOAT2` | `[float, float]` | `[0.5, 0.8]` |
| `FLOAT3` | `[float, float, float]` | `[1.0, 0.2, 0.1]` |
| `FLOAT4` | `[float, float, float, float]` | `[1.0, 0.5, 0.2, 1.0]` |
| `INT1` | `int` | `3` |
| `BOOLEAN` | `bool` | `true` / `false` |
| `STRING` | `str` | `"filename.png"` |

---

## 常用流程

### 完整源控制工作流

```
1. sp_get_layer_stack()                        确认目标图层
2. sp_get_source_info(layer_id)                确认源类型和资源
3. sp_get_substance_parameters(layer_id)       读取当前参数
4. sp_get_substance_presets(layer_id)          浏览预设（可选）
5. sp_apply_substance_preset(layer_id, "...")  切换预设（可选）
6. sp_set_substance_parameters(layer_id, {...}) 微调参数
7. sp_get_source_outputs(layer_id)             确认输出映射
8. sp_set_source_output(layer_id, "...")       切换输出（可选）
9. sp_capture_viewport("quick")                确认效果
```

### 快速参数迭代

```
sp_get_substance_parameters(layer_id)              读
sp_set_substance_parameters(layer_id, {"roughness": 0.7})  改
sp_capture_viewport("quick")                       看
```

---

## 常见错误

| 错误 | 原因 | 解决 |
|------|------|------|
| `"does not support sources"` | 节点类型不对 | 确认是 FillLayer/Effect 节点 |
| `"Preset not found"` | 预设名拼写错误 | `sp_get_substance_presets` 确认 |
| `"Output not found"` | 输出标识符不存在 | `sp_get_source_outputs` 确认 `image_outputs` |
| `"Failed to wrap parameter"` | 参数值类型不对 | 参考参数类型表，确认格式正确 |
| 修改参数后没变化 | 参数名大小写不匹配 | `sp_get_substance_parameters` 确认确切名称 |

---

## Related Skills

- [sp-index](../sp-index/SKILL.md) — 所有 skill 的索引
- [sp-layer-ops](../sp-layer-ops/SKILL.md) — 图层操作 API（源控制的对象）
- [sp-effect-nodes](../sp-effect-nodes/SKILL.md) — 效果节点的源也是程序化源
- [sp-smart-material](../sp-smart-material/SKILL.md) — Smart Material 内部包含程序化源
- [sp-creative-workflow](../sp-creative-workflow/SKILL.md) — 参数调整后的截图迭代
