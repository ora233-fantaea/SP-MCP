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
5. 执行材质操作（add_fill_layer / apply_smart_material / apply_material / add_effect / set_substance_parameters）
6. sp_capture_viewport(mode="quick") 评估结果
7. [评估] 满意 → 进入步骤 8，不满意 → 回步骤 5
8. [可选] sp_start_iray_render() → 轮询 sp_check_iray_render() → sp_capture_viewport(mode="render") 做 Iray 最终确认
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

### 旧化木材
```
sp_begin_batch("Aged Wood")
  sp_apply_material(layer_id, "Wood")
  sp_add_fill_layer(name="Wood_Wear", color_hex="#8B7355", opacity=0.4, blend_mode="Overlay")
  sp_set_layer_channel(layer_id, "Roughness", 0.7)
  sp_add_smart_mask(layer_id, "Surface Worn")          表面磨损
  sp_add_fill_layer(name="Dirt_Accumulation", color_hex="#5C4033", opacity=0.25, blend_mode="Multiply")
  sp_add_smart_mask(layer_id, "Dirt")                   凹陷积灰
sp_end_batch()
→ sp_capture_viewport("quick")
```

### 旧化皮革
```
sp_begin_batch("Worn Leather")
  sp_apply_material(layer_id, "Leather")
  sp_set_layer_channel(layer_id, "Roughness", 0.5)
  sp_add_fill_layer(name="Leather_Crease", color_hex="#3a2a1a", opacity=0.35, blend_mode="Multiply")
  sp_add_smart_mask(layer_id, "Cavity")                 褶皱加深
  sp_add_fill_layer(name="Edge_Scuff", color_hex="#8B7D6B", opacity=0.4, blend_mode="Normal")
  sp_add_smart_mask(layer_id, "Edge Damage")            边缘磨损
sp_end_batch()
→ sp_capture_viewport("quick")
```

### 橡胶
```
sp_begin_batch("Rubber Grip")
  sp_apply_material(layer_id, "Rubber")
  sp_set_layer_channel(layer_id, "Roughness", 0.8)
  sp_add_fill_layer(name="Rubber_Dust", color_hex="#808080", opacity=0.2, blend_mode="Overlay")
  sp_add_smart_mask(layer_id, "Dust")
sp_end_batch()
→ sp_capture_viewport("quick")
```

### 玻璃
```
sp_begin_batch("Glass")
  sp_apply_material(layer_id, "Glass")
  sp_set_layer_channel(layer_id, "Roughness", 0.05)     近乎光滑
  sp_set_layer_channel(layer_id, "Metallic", 0.0)        非金属
  sp_add_fill_layer(name="Glass_Dirt", color_hex="#888888", opacity=0.15, blend_mode="Overlay")
  sp_add_smart_mask(layer_id, "Dirt")                    轻微积灰
sp_end_batch()
→ sp_capture_viewport("quick")
```

### 陶瓷
```
sp_begin_batch("Ceramic")
  sp_apply_material(layer_id, "Ceramic")
  sp_set_layer_channel(layer_id, "Roughness", 0.2)
  sp_add_fill_layer(name="Glaze_Wear", color_hex="#D0C8B8", opacity=0.3, blend_mode="Overlay")
  sp_add_smart_mask(layer_id, "Edge Damage")             釉面剥落
  sp_add_fill_layer(name="Crack_Line", color_hex="#5a5040", opacity=0.2, blend_mode="Multiply")
  sp_add_smart_mask(layer_id, "Cavity")                  裂纹
sp_end_batch()
→ sp_capture_viewport("quick")
```

### 碳纤维
```
sp_begin_batch("Carbon Fiber")
  sp_apply_material(layer_id, "Carbon Fiber")
  sp_set_layer_channel(layer_id, "Roughness", 0.3)
  sp_add_fill_layer(name="Clear_Coat_Damage", color_hex="#CCCCCC", opacity=0.25, blend_mode="Overlay")
  sp_add_smart_mask(layer_id, "Scratches")               表面划痕
sp_end_batch()
→ sp_capture_viewport("quick")
```

### 石材
```
sp_begin_batch("Stone Surface")
  sp_apply_material(layer_id, "Concrete")                或用 Stone/Granite
  sp_set_layer_channel(layer_id, "Roughness", 0.85)
  sp_add_fill_layer(name="Moss_Growth", color_hex="#4A7C3F", opacity=0.25, blend_mode="Overlay")
  sp_add_smart_mask(layer_id, "Dirt")                    苔藓堆积
  sp_add_fill_layer(name="Stone_Chip", color_hex="#9E9E9E", opacity=0.3, blend_mode="Normal")
  sp_add_smart_mask(layer_id, "Edge Damage")             边缘破损
sp_end_batch()
→ sp_capture_viewport("quick")
```

### 通用做旧流程（适用于任何材质）

```
1. sp_apply_material(layer_id, <基础材质>)
2. sp_capture_viewport("quick")                          确认基础效果
3. 叠加磨损层:
   sp_add_fill_layer("Wear_Overlay", color_hex="#888888", opacity=0.3, blend_mode="Overlay")
   sp_add_smart_mask(layer_id, "Surface Worn")
4. 叠加脏迹层:
   sp_add_fill_layer("Dirt_Layer", color_hex="#5a5040", opacity=0.25, blend_mode="Multiply")
   sp_add_smart_mask(layer_id, "Dirt")
5. 叠加边缘损坏:
   sp_add_fill_layer("Edge_Damage", color_hex="#CCCCCC", opacity=0.35, blend_mode="Normal")
   sp_add_smart_mask(layer_id, "Edge Damage")
6. 微调各层 opacity 和 Roughness
7. sp_capture_viewport("render")                         最终确认（可选）
```

**做旧强度参考：**

| 强度 | 磨损 opacity | 脏迹 opacity | 边缘 opacity | 适用场景 |
|------|-------------|-------------|-------------|---------|
| 轻度 | 0.15–0.25 | 0.1–0.2 | 0.15–0.25 | 新品、展示品 |
| 中度 | 0.3–0.5 | 0.25–0.4 | 0.3–0.5 | 日常使用 |
| 重度 | 0.5–0.7 | 0.4–0.6 | 0.5–0.8 | 战损、废墟 |
| 极端 | 0.7–1.0 | 0.6–0.9 | 0.8–1.0 | 末日、废弃 |

## 参数调整策略

1. **opacity 从 0.3 开始** — 太高会覆盖底层
2. **截图确认后再加强** — 每次 +0.1–0.2
3. **blend_mode 选对** — Overlay 适合叠加纹理，Multiply 适合加深
4. **命名保持一致** — 方便后续定位和修改
5. **通道值渐进** — Roughness 从 0.5 开始，Metallic 从 0.3 开始
6. **做旧分层** — 磨损、脏迹、边缘分开建层，方便单独调整强度

---

## Related Skills

- [sp-index](../sp-index/SKILL.md) — 所有 skill 的索引
- [sp-smart-material](../sp-smart-material/SKILL.md) — 材质库浏览、Smart Material/Mask 选择策略
- [sp-layer-ops](../sp-layer-ops/SKILL.md) — 图层操作 API 完整参考
- [sp-camera](../sp-camera/SKILL.md) — 调整视角、HDRI 环境光
- [sp-iray](../sp-iray/SKILL.md) — Iray 渲染参数调优
- [sp-effect-nodes](../sp-effect-nodes/SKILL.md) — 效果节点（Filter/Generator/Levels 等）
- [sp-substance-source](../sp-substance-source/SKILL.md) — 程序化源参数读写、预设切换
- [sp-baking](../sp-baking/SKILL.md) — Python 烘焙 API
- [sp-project](../sp-project/SKILL.md) — 批量操作、撤销/重做、项目生命周期
- [sp-quickstart](../sp-quickstart/SKILL.md) — 首次连接时的验证流程
