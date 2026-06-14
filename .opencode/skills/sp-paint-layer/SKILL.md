---
name: sp-paint-layer
description: 管理 Substance Painter 绘画图层（PaintLayerNode），包括创建绘画层、
             搭配遮罩、手动绘制区域。用户提到绘画/手绘/笔刷/paint 时触发此 skill。
---

# SP Paint Layer

绘画图层（PaintLayerNode）区别于 Fill Layer——它允许在 UV 空间上**逐像素手绘**，适合需要精确控制绘制区域的场景。

## Paint Layer vs Fill Layer

| | Paint Layer | Fill Layer |
|---|---|---|
| **创建 API** | `sp_add_paint_layer` | `sp_add_fill_layer` |
| **节点类型** | `PaintLayerNode` | `FillLayerNode` |
| **覆盖范围** | 初始透明，需要手动绘制 | 覆盖整个模型 |
| **使用场景** | 局部细节、手绘效果、精确控制 | 全局材质、整体调色 |
| **搭配遮罩** | 需要手动绘制或添加 Smart Mask | 必须配 Smart Mask |

---

## 创建绘画图层

```
sp_add_paint_layer(name)
```

创建后图层是**透明的**，不会覆盖任何内容。需要通过以下方式填充内容：

1. **Computer Use** — 用 `sp_mouse_click` / `sp_mouse_drag` 在 viewport 上手绘
2. **Smart Mask** — `sp_add_smart_mask` 添加程序化遮罩，定义绘制区域
3. **后续填入** — 创建后再调 `sp_set_layer_channel` 设置通道值（但 Paint Layer 的通道值需在绘制区域内才生效）

### 典型工作流

```
1. sp_add_paint_layer("Hand_Paint_Detail")
2. sp_add_smart_mask(layer_id, "Dirt")         用 mask 定义绘制区域
3. sp_set_layer_channel(layer_id, "BaseColor", "#FF6600")  设置颜色
4. sp_set_layer_channel(layer_id, "Roughness", 0.9)
5. sp_capture_viewport("quick")                 确认
```

---

## Computer Use 手绘

Painter 的画笔工具可以通过 Computer Use 操控：

```
sp_window_focus()
  sp_shortcut("paint_mode")                    切换到绘制模式 (1)
  sp_window_grab()                             截图定位 viewport
  sp_mouse_drag(x1, y1, x2, y2, "left", "window")  在 viewport 上绘制一笔
  sp_window_grab()                             确认绘制结果
sp_cu_unlock()
```

### 笔刷控制

Painter 的笔刷参数（大小、流量、硬度）在 UI 顶部工具栏，可以用 Computer Use 点击调整：

1. `sp_window_grab()` → 定位笔刷大小滑块
2. `sp_mouse_click(滑块x, 滑块y, "left", "window")` → 聚焦
3. `sp_key_send("20")` → 设置笔刷大小
4. 或 `sp_mouse_drag` 拖动滑块

---

## Paint Layer + Smart Mask 组合

这是最实用的模式——用 Smart Mask 程序化地定义绘制区域，然后用 Paint Layer 覆盖颜色/粗糙度：

### 局部锈迹
```
sp_add_paint_layer("Local_Rust")
sp_add_smart_mask(layer_id, "Rust")             程序化锈迹区域
sp_set_layer_channel(layer_id, "BaseColor", "#8B4513")
sp_set_layer_channel(layer_id, "Roughness", 0.9)
sp_set_layer_property(layer_id, "opacity", 0.6)
```

### 手动高亮
```
sp_add_paint_layer("Highlight")
sp_set_layer_channel(layer_id, "BaseColor", "#FFFFFF")
sp_set_layer_property(layer_id, "opacity", 0.2)
sp_set_layer_property(layer_id, "blend_mode", "Overlay")
# 然后用 CU 在需要高亮的区域绘制
```

### 局部污迹
```
sp_add_paint_layer("Grime_Detail")
sp_add_smart_mask(layer_id, "Grime")
sp_set_layer_channel(layer_id, "BaseColor", "#3a3a3a")
sp_set_layer_channel(layer_id, "Roughness", 0.8)
```

---

## Paint Layer 的限制

| 限制 | 说明 | 替代方案 |
|------|------|---------|
| 无法直接用 API 绘制 | SP 没有 Python API 控制笔刷 | 用 Computer Use 鼠标拖拽 |
| 通道值需 mask 配合 | 没有 mask 的 Paint Layer 不可见 | 总是配 Smart Mask 或 CU 手动绘制 |
| 绘制精度受限 | CU 鼠标拖拽不如人手精确 | 优先用 Smart Mask 定义区域 |
| 无法选择笔刷预设 | 需通过 CU 点击 UI | — |

**实际建议：** 90% 的需求用 Fill Layer + Smart Mask 就够了。Paint Layer 主要用于：
- Smart Mask 覆盖不到的区域
- 需要不规则/艺术化笔触
- 手动修复程序化 mask 的瑕疵

---

## 常见错误

| 错误 | 原因 | 解决 |
|------|------|------|
| 创建后看不到效果 | Paint Layer 初始是透明的 | 添加 Smart Mask 或用 CU 绘制 |
| `This node already has a mask` | 已有 mask | 删掉旧 mask 或新建图层 |
| CU 绘制位置不对 | 坐标映射错误 | 用 `sp_window_grab` → 视觉定位 → `relative="window"` |
| 画笔没反应 | 未选中 paint 模式 | `sp_shortcut("paint_mode")` |

---

## Related Skills

- [sp-index](../sp-index/SKILL.md) — 所有 skill 的索引
- [sp-layer-ops](../sp-layer-ops/SKILL.md) — 图层操作 API 参考
- [sp-computer-use](../sp-computer-use/SKILL.md) — 鼠标拖拽绘制、笔刷 UI 控制
- [sp-smart-material](../sp-smart-material/SKILL.md) — Smart Mask 定义绘制区域
- [sp-creative-workflow](../sp-creative-workflow/SKILL.md) — 材质创作整体流程