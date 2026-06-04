---
name: sp-creative-workflow
description: 通过截图回路驱动 Substance Painter 材质创作，包括视觉评估、
             迭代调整、多轮确认。用户要求设计/美化/调整材质外观时触发此 skill。
---

# SP Creative Workflow

通过截图回路驱动材质创作的标准工作流。

## 核心原则

- **先截图再动手** — 每次修改前先看当前状态
- **opacity 从保守值开始** — 0.3–0.5，截图确认后再加强
- **图层命名语义化** — `"Rust_Overlay"` 而非 `"Layer_1"`
- **每步截图** — 不要攒到最后，每个视觉层次完成后确认
- **批量操作用 begin_batch** — 多个相关操作打包成一次 undo

## 标准迭代循环

```
1. sp_ping()                         确认连接
2. sp_capture_viewport(mode="quick") 看当前状态
3. sp_get_layer_stack()              理解图层结构
4. [决策] 根据截图制定材质方案
5. 执行材质操作（add_fill_layer / apply_smart_material / apply_material）
6. sp_capture_viewport(mode="quick") 评估结果
7. [评估] 满意 → 进入步骤 8，不满意 → 回步骤 5
8. sp_capture_viewport(mode="render") Iray 最终确认（可选）
```

## 截图模式选择

| 模式 | 用途 | 耗时 |
|------|------|------|
| `quick` | 迭代确认 | 毫秒级 |
| `render` | 最终确认 | 需先渲染（set_iray_params → start → check → capture） |

## 批量工作流（推荐）

多个相关操作打包成一次 undo，用户 Ctrl+Z 可一次撤销整批：

```
sp_begin_batch("Apply Rust Effect")
  sp_add_fill_layer("Rust_Base")
  sp_set_layer_channel("xxx", "Roughness", 0.8)
  sp_set_layer_channel("xxx", "Metallic", 0.6)
  sp_add_smart_mask("xxx", "Rust")
sp_end_batch()
```

## 迭代策略

- **修改属性** — `sp_set_layer_property` / `sp_set_layer_channel`
- **复制调整** — `sp_duplicate_layer` 复制后改参数，对比效果
- **删除重来** — `sp_delete_layer` 删掉不满意的图层
- **通道微调** — `sp_set_layer_channel` 精确控制每个 PBR 通道

## 典型场景示例

### 战损金属
```
sp_begin_batch("Battle Worn Metal")
  sp_apply_smart_material(layer_id, "Steel")           基础金属
  sp_add_smart_mask(layer_id, "Edge Damage")            边缘磨损
  sp_add_fill_layer(name="Rust_Overlay", opacity=0.3, blend_mode="Overlay")
  sp_set_layer_channel(layer_id, "Roughness", 0.85)
  sp_add_smart_mask(layer_id, "Rust")                   锈迹
sp_end_batch()
→ sp_capture_viewport("quick") 确认效果
```

### 氧化铜
```
sp_begin_batch("Oxidized Copper")
  sp_apply_material(layer_id, "Copper")                 基础铜
  sp_add_fill_layer(name="Oxidation", color_hex="#2E8B57", opacity=0.4, blend_mode="Overlay")
  sp_add_smart_mask(layer_id, "Dirt")                   自然氧化分布
sp_end_batch()
→ sp_capture_viewport("quick")
```

### 烤漆
```
sp_begin_batch("Painted Surface")
  sp_apply_smart_material(layer_id, "Steel Painted")
  sp_add_smart_mask(layer_id, "Paint Damaged")          掉漆
sp_end_batch()
→ sp_capture_viewport("quick")
```

### 塑料外壳
```
sp_begin_batch("Plastic Housing")
  sp_apply_material(layer_id, "Plastic Matte")          基础塑料
  sp_set_layer_channel(layer_id, "Roughness", 0.6)
  sp_add_smart_mask(layer_id, "Surface Worn")           表面磨损
sp_end_batch()
→ sp_capture_viewport("quick")
```

## 参数调整策略

1. **opacity 从 0.3 开始** — 太高会覆盖底层
2. **截图确认后再加强** — 每次 +0.1–0.2
3. **blend_mode 选对** — Overlay 适合叠加纹理，Multiply 适合加深
4. **命名保持一致** — 方便后续定位和修改
5. **通道值渐进** — Roughness 从 0.5 开始，Metallic 从 0.3 开始
