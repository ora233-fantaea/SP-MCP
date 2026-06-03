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

## 标准迭代循环

```
1. sp_ping()                         确认连接
2. sp_capture_viewport(mode="quick") 看当前状态
3. sp_get_layer_stack()              理解图层结构
4. [决策] 根据截图制定材质方案
5. 执行材质操作（add_fill_layer / apply_smart_material / set_layer_property）
6. sp_capture_viewport(mode="quick") 评估结果
7. [评估] 满意 → 进入步骤 8，不满意 → 回步骤 5
8. sp_capture_viewport(mode="render") Iray 最终确认（可选）
```

## 截图模式选择

| 模式 | 用途 | 耗时 | 调用方式 |
|------|------|------|---------|
| `quick` | 迭代确认，看大致效果 | 毫秒级 | `sp_capture_viewport(mode="quick")` |
| `render` | 最终确认，导出前 | 需先渲染 | `sp_set_iray_params` → `sp_start_iray_render` → `sp_check_iray_render` → `sp_capture_viewport(mode="render")` |

## 典型场景示例

### 战损金属
```
1. sp_apply_smart_material(layer_id, "Steel")        基础金属
2. sp_capture_viewport("quick")                       确认基础效果
3. sp_add_smart_mask(layer_id, "Edge Wear")           边缘磨损
4. sp_capture_viewport("quick")                       确认磨损效果
5. sp_add_fill_layer(name="Rust_Overlay", opacity=0.3, blend_mode="Overlay")
6. sp_capture_viewport("quick")                       确认锈迹叠加
7. sp_add_smart_mask(layer_id, "Dirt")                添加污垢
8. sp_capture_viewport("quick")                       最终确认
```

### 氧化铜
```
1. sp_add_fill_layer(name="Copper_Base", color_hex="#B87333")
2. sp_add_fill_layer(name="Oxidation", color_hex="#2E8B57", opacity=0.4, blend_mode="Overlay")
3. sp_add_smart_mask(layer_id, "Dirt")                自然氧化分布
4. sp_capture_viewport("quick")
```

### 烤漆
```
1. sp_apply_smart_material(layer_id, "Steel Painted")
2. sp_capture_viewport("quick")
3. sp_add_smart_mask(layer_id, "Edge Wear")           边缘掉漆
4. sp_capture_viewport("quick")
```

## 参数调整策略

1. **opacity 从 0.3 开始** — 太高会覆盖底层
2. **截图确认后再加强** — 每次 +0.1–0.2
3. **blend_mode 选对** — Overlay 适合叠加纹理，Multiply 适合加深
4. **命名保持一致** — 方便后续定位和修改
