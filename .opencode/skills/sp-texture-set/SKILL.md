---
name: sp-texture-set
description: 管理 Substance Painter 纹理集：切换活动纹理集、调整分辨率、
             烘焙 mesh maps、增删通道。用户提到纹理集/烘焙/分辨率/通道时触发此 skill。
---

# SP Texture Set Management

纹理集管理、烘焙、通道操作的工作流。

## ⚠️ 核心原则：先读后改

**任何操作前，必须先确认当前纹理集状态。**

| 操作前必读 | 说明 |
|---|---|
| `sp_get_texture_sets()` | 确认有哪些纹理集，找到目标名称 |
| `sp_get_layer_stack()` | 确认当前图层结构 |
| `sp_run_python` 读 `ts.get_resolution()` | 修改分辨率前先看当前值 |

---

## 纹理集切换

**`sp_set_active_texture_set(name)`** — 切换当前操作的纹理集。

name 必须与 `sp_get_texture_sets` 返回的名称**完全一致**（大小写敏感）。

**工作流：**
```
1. sp_get_texture_sets()              列出所有纹理集
2. sp_set_active_texture_set("xxx")   切换到目标
3. sp_get_layer_stack()               确认图层结构已更新
4. 执行操作
```

---

## 分辨率管理

**`sp_set_texture_set_resolution(width, height)`** — 修改当前纹理集分辨率。

常用值：`1024` / `2048` / `4096`

**注意：** 修改分辨率会影响所有通道的纹理精度。高分辨率（4096）适合最终导出，低分辨率（1024）适合快速预览。

**工作流：**
```
1. sp_run_python("import substance_painter.texturesets; ts = substance_painter.texturesets.get_active(); print(ts.get_resolution())")
   确认当前分辨率
2. sp_set_texture_set_resolution(2048, 2048)   修改
3. sp_capture_viewport("quick")               确认效果
```

---

## 烘焙 Mesh Maps

**`sp_bake_mesh_maps(texture_set_name)`** — 烘焙指定纹理集的 mesh maps（AO/Curvature/Normal 等）。

通过 `js.evaluate("alg.baking.bake()")` 实现，需要 SP 10.0+。

**注意事项：**
- 烘焙会阻塞主线程，耗时较长
- 需要模型有正确的 UV 展开
- 烘焙结果会影响 Smart Material 和 Smart Mask 的效果

**工作流：**
```
1. sp_get_texture_sets()              确认纹理集名称
2. sp_bake_mesh_maps("textureSetName")  烘焙
3. sp_capture_viewport("quick")       确认烘焙效果
```

---

## 通道管理

### 查看通道

**`sp_get_layer_channels(layer_id)`** — 返回所有通道的 opacity、blend_mode、source 值。

### 设置通道值

**`sp_set_layer_channel(layer_id, channel, value)`**

| channel | value 类型 | 范围 |
|---------|-----------|------|
| `"BaseColor"` | hex color | `"#FF0000"` |
| `"Roughness"` | float | 0.0–1.0 |
| `"Metallic"` | float | 0.0–1.0 |
| `"Height"` | float | -1.0–1.0 |
| `"Normal"` | hex color | 通常不手动设置 |

### 增删通道（JS API）

**`sp_add_texture_set_channel(texture_set_name, channel_id, channel_format, channel_label)`**
- `channel_format`: `"Color4"` (RGBA) 或 `"Grayscale"` (灰度)
- 需要 SP 10.0+

**`sp_remove_texture_set_channel(texture_set_name, channel_id)`**

---

## 多纹理集工作流

当模型有多个纹理集时，操作前必须确认目标：

```
1. sp_get_texture_sets()                    列出所有
2. 选择目标纹理集
3. sp_set_active_texture_set("targetName")  切换
4. sp_get_layer_stack()                     确认图层
5. 执行操作
6. 重复 2–5 处理下一个纹理集
```

**批量操作：** 用 `sp_begin_batch` / `sp_end_batch` 包裹多个纹理集的操作，用户 Ctrl+Z 可一次撤销。
