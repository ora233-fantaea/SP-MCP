---
name: sp-smart-material
description: 浏览 Substance Painter 材质库、应用 Smart Material/普通材质、
             添加 Smart Mask、材质对比评估。用户提到材质/贴材质/
             换材质/遮罩/磨损/脏迹时触发此 skill。
---

# SP Smart Material & Mask

Smart Material 是 Substance Painter 最核心的功能——它是一个**多层材质预设**，包含基础材质、磨损效果、污迹遮罩等，一键应用即可获得逼真的 PBR 效果。

## ⚠️ 核心原则

1. **先列后选** — 不要猜材质名，先用 `sp_list_shelf_materials` / `sp_list_materials` 确认
2. **截图评估** — 应用材质后立即截图看效果
3. **先基后效** — 先铺基础材质层，再叠加 Smart Mask
4. **opacity 渐进** — 叠加层从 0.3 开始

---

## Smart Material vs 普通 Material

| | Smart Material | 普通 Material |
|---|---|---|
| **API** | `sp_list_shelf_materials` + `sp_apply_smart_material` | `sp_list_materials` + `sp_apply_material` |
| **结构** | 多层 GroupLayerNode（含遮罩、生成器） | 单层材质预设 |
| **效果** | 自带磨损/脏迹等程序化细节 | 仅基础材质属性 |
| **数量** | 数百个（取决于安装的 Shelf） | 917+（SP 内置） |
| **适用场景** | 最终效果、快速出图 | 作为基础层，叠加 mask 做定制效果 |
| **可调性** | 展开组可调各层参数 | 只能调当前图层的通道值 |

**选择策略：**
- 追求快速效果 → Smart Material
- 需要精确控制每个通道 → 普通 Material + 手动 Smart Mask
- 混合使用 → 底层普通 Material + 上层 Smart Material 叠加

---

## 浏览材质库

### 列出 Smart Material

```
sp_list_shelf_materials(filter="")
```

`filter` 支持关键词（大小写不敏感），常用过滤词：

| filter | 返回数量 | 典型结果 |
|--------|---------|---------|
| `"metal"` | ~37 | Steel、Iron、Aluminum、Copper 等 |
| `"wood"` | ~15 | Wood、Wood Painted 等 |
| `"fabric"` | ~20 | Fabric、Leather 等 |
| `"paint"` | ~10 | Steel Painted、Car Paint 等 |
| `"rust"` | ~5 | Rust、Rust Iron 等 |
| `"plastic"` | ~12 | Plastic Matte、Plastic Glossy 等 |
| `""` (空) | ~200+ | 全部 |

**工作流：**
```
1. sp_list_shelf_materials(filter="metal")   浏览金属类
2. 选择材质名
3. sp_apply_smart_material(layer_id, "Steel Rough")  应用
4. sp_capture_viewport("quick")              看效果
```

### 列出普通材质

```
sp_list_materials(filter="")
```

917+ 个内置材质，filter 必传。建议先用大类别过滤，再精确搜索。

---

## 应用 Smart Material

```
sp_apply_smart_material(layer_id, material_name)
```

- `layer_id`：目标图层（会在此图层上方创建新组）
- `material_name`：必须与 `sp_list_shelf_materials` 返回的名称**完全一致**

**注意：** Smart Material 会创建一个 **GroupLayerNode**，包含多个子层。可以用 `sp_get_layer_stack` 展开查看内部结构。

**示例：**
```
sp_get_layer_stack()                              确定 layer_id
sp_list_shelf_materials("steel")                  列出可选材质
sp_apply_smart_material("abc123", "Steel Rough")  应用
sp_get_layer_stack()                              查看生成的组结构
sp_capture_viewport("quick")                      截图确认
```

---

## 常用 Smart Material 速查

### 金属类
| 材质名 | 效果 |
|--------|------|
| `Steel Rough` | 粗糙钢铁 |
| `Steel Polished` | 抛光钢铁 |
| `Steel Painted` | 烤漆钢铁（自带掉漆效果） |
| `Iron` | 铸铁 |
| `Iron Rough` | 粗糙铸铁 |
| `Aluminum` | 铝 |
| `Copper` | 铜 |
| `Copper Polished` | 抛光铜 |
| `Gold` | 金 |
| `Silver` | 银 |
| `Brass` | 黄铜 |
| `Chrome` | 镀铬 |

### 木材类
| 材质名 | 效果 |
|--------|------|
| `Wood` | 通用木材 |
| `Wood Painted` | 刷漆木材 |
| `Wood Rough` | 粗糙木材 |
| `Wood Floor` | 地板木 |

### 织物/皮革
| 材质名 | 效果 |
|--------|------|
| `Fabric` | 通用织物 |
| `Leather` | 皮革 |
| `Leather Rough` | 粗糙皮革 |
| `Rubber` | 橡胶 |

### 塑料/其他
| 材质名 | 效果 |
|--------|------|
| `Plastic Matte` | 哑光塑料 |
| `Plastic Glossy` | 光面塑料 |
| `Glass` | 玻璃 |
| `Ceramic` | 陶瓷 |
| `Carbon Fiber` | 碳纤维 |

> ⚠️ 材质名因 SP 版本和安装的 Shelf 而异。**必须先 `sp_list_shelf_materials` 确认**，不要盲猜。

---

## Smart Mask

Smart Mask 是程序化遮罩，根据模型的曲率、AO、法线等信息自动计算磨损/脏迹位置。

### 列出可用 Mask

SP 不提供独立的"列出 mask"API，但可以通过以下方式探索：

```
sp_list_shelf_materials(filter="")  → 部分 Smart Material 名包含 mask 效果关键词
```

或直接用 `sp_run_python` 探索：
```python
import substance_painter.resource as res
# 搜索 mask 类型资源
results = res.search({"types": ["mask"]})  # 尝试
```

### 添加 Smart Mask

```
sp_add_smart_mask(layer_id, mask_name)
```

**⚠️ 前提：** 目标图层**不能已有 mask**，否则报错 `"This node already has a mask"`。

### 常用 Smart Mask 速查

| Mask 名 | 效果 | 适用场景 |
|---------|------|---------|
| `Dirt` | 脏迹（凹陷处堆积） | 任何需要做旧的材质 |
| `Rust` | 锈迹 | 金属材质 |
| `Edge Damage` | 边缘磨损 | 硬表面、武器、机械 |
| `Edge Wear` | 边缘磨损（更细腻） | 金属边缘 |
| `Dust` | 灰尘 | 任何表面 |
| `Edges Scratched` | 边缘划痕 | 金属、塑料 |
| `Surface Worn` | 表面磨损 | 任何高频接触面 |
| `Paint Damaged` | 掉漆 | 烤漆表面 |
| `Scratches` | 划痕 | 金属、塑料 |
| `Cavity` | 凹陷 | 复杂几何体 |
| `Grime` | 污垢 | 任何 |

**层叠策略：** 同一个图层可以多次 `add_smart_mask`……不，一个图层只能有一个 mask。但可以在多个图层各加不同 mask，通过 `opacity` 和 `blend_mode` 叠加。

---

## 材质叠加模式

```
Layer Stack（从上到下）:
├── Rust_Overlay (opacity=0.3, blend=Overlay)    ← 叠加锈迹
│   └── [Smart Mask: Rust]
├── Edge_Wear (opacity=0.5, blend=Normal)         ← 边缘磨损
│   └── [Smart Mask: Edge Damage]
├── Base_Metal (opacity=1.0, blend=Normal)        ← 基础材质
│   └── [Smart Material: Steel Rough]
└── (原始底层)
```

**叠加原则：**
- 基础材质放在最下面（opacity=1.0, blend=Normal）
- 效果叠加层在上面（opacity=0.3–0.5, blend=Overlay/Multiply）
- 磨损/划痕层在中层（opacity=0.5–0.7, blend=Normal）

---

## 常见错误

| 错误 | 原因 | 解决 |
|------|------|------|
| `"Smart Material not found"` | 材质名拼写错误或不存在 | `sp_list_shelf_materials` 确认名称 |
| `"Material not found"` | 同上 | `sp_list_materials` 确认名称 |
| `"This node already has a mask"` | 图层已有 mask | 先 `sp_delete_layer` 删掉现有 mask 子节点，或换图层 |
| `"requires SP 10.0+"` | SP 版本 < 10.0 | Smart Material API 需要 10.0+ |
| 应用后没变化 | 材质名存在但资源类型不匹配 | 用 `sp_get_layer_stack` 确认是否创建了新图层 |
| 部分效果缺失 | 模型没有烘焙 mesh maps | 先 `sp_bake_mesh_maps` 烘焙 AO/Curvature/Normal |

---

## 材质对比工作流

当不确定哪个材质更好时：

```
1. sp_get_layer_stack()                              记录当前状态
2. sp_begin_batch("Test Material A")
3.   sp_apply_smart_material(layer_id, "Steel Rough")
4. sp_end_batch()
5. sp_capture_viewport("quick")                       截图 A
6. sp_undo()                                          撤销
7. sp_begin_batch("Test Material B")
8.   sp_apply_smart_material(layer_id, "Steel Polished")
9. sp_end_batch()
10. sp_capture_viewport("quick")                      截图 B
11. 对比 A vs B → 选择
12. 如果不满意 → sp_undo() → 继续试下一个
```

---

## 与 sp-layer-ops 的关系

Smart Material/Mask 的 API 详情在 [sp-layer-ops](../sp-layer-ops/SKILL.md) 的「Smart Material」和「普通材质」章节。
本 skill 侧重于**材质选择策略和组合技巧**，sp-layer-ops 侧重于**API 参数和技术细节**。

---

## Related Skills

- [sp-index](../sp-index/SKILL.md) — 所有 skill 的索引
- [sp-layer-ops](../sp-layer-ops/SKILL.md) — Smart Material/Mask API 参数详解
- [sp-creative-workflow](../sp-creative-workflow/SKILL.md) — 材质创作迭代循环 + 配方
- [sp-texture-set](../sp-texture-set/SKILL.md) — 烘焙 mesh maps（Smart Mask 依赖 AO/Curvature）
- [sp-paint-layer](../sp-paint-layer/SKILL.md) — 用 Paint Layer 补充 Smart Mask 覆盖不到的区域