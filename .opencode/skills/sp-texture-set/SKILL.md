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
1. sp_run_python("import substance_painter.textureset as ts_mod; ts = ts_mod.get_active_stack(); print(ts_mod.get_resolution(ts))")
   确认当前分辨率
2. sp_set_texture_set_resolution(2048, 2048)   修改
3. sp_capture_viewport("quick")               确认效果
```

---

## 烘焙 Mesh Maps

SP-MCP 提供两套烘焙 API：

### Python Baking API（推荐，Phase 16）

完整的参数控制、状态管理、异步执行。5 个 tools：

| Tool | 功能 |
|------|------|
| `sp_get_baking_parameters` | 读取 common + 各 baker 完整参数 |
| `sp_set_baking_parameters` | 设置分辨率/高模路径/AO 参数等 |
| `sp_bake_texture_set` | 异步启动烘焙 |
| `sp_get_baking_state` | 获取启用/bakers/UV tiles/链接 |
| `sp_set_baking_state` | 开关 baker/曲率方法/UV tiles |

> 📘 详见 [sp-baking](../sp-baking/SKILL.md)。

### JS API（Phase 9，兼容保留）

**`sp_bake_mesh_maps(texture_set_name)`** — 通过 `alg.baking.bake()` 烘焙。
使用当前 SP 烘焙设置，功能受限但调用简单。

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

---

## 烘焙 Mesh Maps 专题

`sp_bake_mesh_maps(texture_set_name)` 是高风险操作——它会**阻塞主线程**，期间所有 bridge 请求 timeout。

### 烘焙时机

烘焙应该在**任何 Smart Material / Smart Mask 操作之前**完成，因为这些功能依赖 AO、Curvature、Normal 等 mesh maps。

### 烘焙前提

- 模型有正确的 UV 展开（所有 UV shell 不重叠）
- 高模和低模已正确设置（如果需要法线烘焙）
- SP 项目中的烘焙参数已配置（Cage、Max Frontal Distance 等）

### 标准流程

```
1. sp_get_texture_sets()                        确认纹理集名称
2. sp_save_project()                            先保存（烘焙不可撤销）
3. sp_bake_mesh_maps("TextureSetName")          执行烘焙（阻塞！）
4. [等待 30s–5min]                              取决于模型复杂度和分辨率
5. sp_ping()                                    确认 bridge 恢复响应
6. sp_capture_viewport("quick")                 确认烘焙效果
```

### 烘焙产出的 Mesh Maps

| Map | 通道名 | 用途 |
|-----|--------|------|
| Ambient Occlusion | AO | Smart Mask 的基础输入（凹陷/遮挡） |
| Curvature | Curvature | 边缘磨损/凸起检测 |
| World Space Normal | Normal (WS) | 方向性 mask |
| Position | Position | 位置渐变 |
| Thickness | Thickness | 薄壁检测 |
| ID Map | ID | 按材质 ID 分区 |

### 烘焙后验证

```
sp_capture_viewport("quick")  → 检查模型表面是否有烘焙结果
```

如果 Smart Mask 效果不对（如 Dirt 全黑或无效果），很可能是烘焙未完成或参数不对。

### 常见烘焙问题

| 问题 | 原因 | 解决 |
|------|------|------|
| 烘焙期间全部 timeout | 主线程阻塞中 | 正常现象，等待完成 |
| 烘焙失败（返回 error） | 模型 UV 有问题 | 在 SP 中检查 UV 和烘焙设置 |
| 烘焙后 Smart Mask 无效果 | AO/Curvature map 缺失 | `sp_get_texture_sets` 确认通道列表含 AO |
| 法线贴图显示异常 | OpenGL/DirectX 格式不匹配 | 在 SP 烘焙设置中切换法线格式 |
| 烘焙耗时极长 | 分辨率过高或模型太复杂 | 先用低分辨率测试，确认没问题再提高 |

---

## Related Skills

- [sp-index](../sp-index/SKILL.md) — 所有 skill 的索引
- [sp-baking](../sp-baking/SKILL.md) — Python 烘焙 API 详解（参数、状态、异步执行）
- [sp-smart-material](../sp-smart-material/SKILL.md) — 烘焙是 Smart Material/Mask 的前置步骤
- [sp-layer-ops](../sp-layer-ops/SKILL.md) — 图层操作 API
- [sp-project](../sp-project/SKILL.md) — 烘焙前后保存、批量操作
- [sp-iray](../sp-iray/SKILL.md) — 烘焙后可能需要的 Iray 渲染确认
