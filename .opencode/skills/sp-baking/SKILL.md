---
name: sp-baking
description: 控制 Substance Painter 烘焙流程：读取/设置烘焙参数、启动异步烘焙、
             管理烘焙状态（启用 baker/UV tiles/曲率方法）。用户提到烘焙/bake/
             mesh maps/AO/Curvature/Normal 烘焙时触发此 skill。
---

# SP Baking API

完整的 Python 烘焙 API 控制——从参数配置、状态管理到异步执行。

> 📘 本 skill 覆盖 Phase 16 的 Python Baking API。旧的 `sp_bake_mesh_maps`（JS API）
> 仍然可用但功能受限，推荐使用本 API 以获得完整的参数控制。

## ⚠️ 核心原则：先读后改

| 操作前必读 | 说明 |
|---|---|
| `sp_get_baking_parameters(texture_set_name)` | 读取完整烘焙参数（common + 各 baker） |
| `sp_get_baking_state(texture_set_name)` | 读取烘焙启用状态、链接信息 |

---

## 烘焙 API 概览

| Tool | 功能 |
|------|------|
| `sp_get_baking_parameters` | 读取纹理集的完整烘焙参数（common + 各 baker） |
| `sp_set_baking_parameters` | 设置烘焙参数（分辨率/高模路径/AO 参数等） |
| `sp_bake_texture_set` | 异步启动纹理集烘焙 |
| `sp_get_baking_state` | 获取烘焙状态（启用/bakers/UV tiles/链接） |
| `sp_set_baking_state` | 设置烘焙状态（启用纹理集/bakers/曲率方法/UV tiles） |

### 与旧 JS API 对比

| | Python Baking API (Phase 16) | JS API (Phase 9) |
|---|---|---|
| **Tool** | `sp_get/set_baking_parameters` + `sp_bake_texture_set` | `sp_bake_mesh_maps` |
| **参数控制** | ✅ 完整（common + 每个 baker 的独立参数） | ❌ 无（用 SP 当前设置） |
| **状态查询** | ✅ `sp_get_baking_state` | ❌ 无 |
| **Baker 开关** | ✅ `sp_set_baking_state` | ❌ 无 |
| **曲率方法** | ✅ FromMesh / FromNormalMap | ❌ 无 |
| **UV Tiles** | ✅ 支持 | ❌ 无 |
| **执行方式** | 异步（`bake_async`） | 同步阻塞（`alg.baking.bake`） |

---

## 读取烘焙参数

```
sp_get_baking_parameters(texture_set_name)
```

返回结构：
```json
{
  "texture_set": "body",
  "common": {
    "OutputSize": [4096, 4096],
    "HipolyMesh": "file:///E:/models/highpoly.fbx",
    "CageMesh": null,
    "MaxFrontalDistance": 0.01,
    "MaxRearDistance": 0.01,
    "RelativeToBoundingBox": false,
    "AOCalculation": true,
    "UseLowPolyAsHighPoly": false,
    "MatchUVs": "Always",
    "SoftenNormalMap": false,
    "AverageNormal": false,
    "DilationWidth": 4
  },
  "bakers": {
    "AO": { "Distribution": "Cosine", "RayCount": 512, "OcclusionRange": 1.0 },
    "Curvature": { "Algorithm": "PerPixels", "Soften": false },
    "Normal": { "Format": "OpenGL", "RelativeToBoundingBox": false },
    "WorldSpaceNormal": {},
    "Position": {},
    "Thickness": { "RayCount": 256 },
    "ID": { "ColorSource": "MaterialColor" }
  },
  "curvature_method": "FromMesh",
  "textureset_enabled": true
}
```

**关键参数说明：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `OutputSize` | `[W, H]` | 烘焙贴图分辨率 |
| `HipolyMesh` | `str` | 高模文件路径（file:// URL） |
| `DilationWidth` | `float` | UV 边缘扩展像素数 |
| `MaxFrontalDistance` | `float` | 法线烘焙的前向搜索距离 |
| `MaxRearDistance` | `float` | 法线烘焙的后向搜索距离 |
| `MatchUVs` | `str` | UV 匹配策略：Always / OnlyIfSameName / Never |

---

## 设置烘焙参数

```
sp_set_baking_parameters(texture_set_name, common_params?, baker_params?)
```

### 修改 Common 参数

```
sp_set_baking_parameters(
    texture_set_name="body",
    common_params={"OutputSize": [4096, 4096], "DilationWidth": 8}
)
```

### 修改特定 Baker 参数

```
sp_set_baking_parameters(
    texture_set_name="body",
    baker_params={"AO": {"RayCount": 1024, "OcclusionRange": 2.0}}
)
```

### 同时修改 Common + Baker

```
sp_set_baking_parameters(
    texture_set_name="body",
    common_params={"OutputSize": [2048, 2048]},
    baker_params={"Curvature": {"Algorithm": "PerPixels"}}
)
```

---

## 管理烘焙状态

### 读取状态

```
sp_get_baking_state(texture_set_name)
```

返回：
```json
{
  "texture_set": "body",
  "textureset_enabled": true,
  "curvature_method": "FromMesh",
  "enabled_bakers": ["AO", "Curvature", "Normal", "WorldSpaceNormal", "Position", "Thickness", "ID"],
  "linked_groups": { "AO": ["body", "accessories"] }
}
```

### 设置状态

```
sp_set_baking_state(
    texture_set_name,
    enabled=True/False,               # 启用/禁用整个纹理集
    curvature_method="FromMesh",      # 或 "FromNormalMap"
    enabled_bakers=["AO", "Normal"],  # 只启用指定 baker
    enabled_uv_tiles=[0, 1]           # 启用指定 UV tiles
)
```

### 典型操作

**只烘焙 AO + Curvature（跳过高成本 baker）：**
```
sp_set_baking_state("body", enabled_bakers=["AO", "Curvature"])
```

**切换曲率计算方法：**
```
sp_set_baking_state("body", curvature_method="FromNormalMap")
```

**禁用某个纹理集的烘焙：**
```
sp_set_baking_state("body", enabled=False)
```

---

## 执行烘焙

```
sp_bake_texture_set(texture_set_name)
```

⚠️ **异步执行**——调用后立即返回，烘焙在后台运行。

### 烘焙前检查清单

- [ ] 项目已保存（`sp_save_project`）
- [ ] 烘焙参数已确认（`sp_get_baking_parameters`）
- [ ] 需要的 baker 已启用（`sp_get_baking_state`）
- [ ] 高模路径正确（如果烘焙法线）
- [ ] 分辨率合理（测试用 2048，最终用 4096）

### 监控烘焙进度

烘焙是异步的，通过 SP event 系统监控：

```python
# 用 sp_run_python 注册回调
import substance_painter.event as event
import substance_painter.baking as baking

def on_baking_end(status):
    print(f"Baking completed: {status}")

dispatcher = event.DISPATCHER
dispatcher.subscribe(event.BakingProcessEnded, on_baking_end)
```

或简单地用 `sp_capture_viewport("quick")` + `sp_get_texture_sets` 检查结果。

---

## 烘焙产出的 Mesh Maps

| Map | 通道名 | 用途 |
|-----|--------|------|
| Ambient Occlusion | AO | Smart Mask 基础输入（凹陷/遮挡检测） |
| Curvature | Curvature | 边缘磨损/凸起检测 |
| Normal | Normal | 法线贴图（高模细节→低模） |
| World Space Normal | Normal (WS) | 方向性 mask |
| Position | Position | 位置渐变/世界对齐效果 |
| Thickness | Thickness | 薄壁检测/半透明 |
| ID Map | ID | 按材质 ID 分区 |

---

## 常见错误

| 错误 | 原因 | 解决 |
|------|------|------|
| `"TextureSet not found"` | 纹理集名称拼写错误 | `sp_get_texture_sets` 确认名称 |
| 烘焙后 Smart Mask 无效果 | AO/Curvature map 未烘焙或 baker 未启用 | `sp_get_baking_state` 检查 enabled_bakers |
| 法线贴图显示异常 | OpenGL/DirectX 格式不匹配 | `sp_set_baking_parameters` 设置 Normal Format |
| 烘焙参数 `set` 无效 | 参数名大小写或拼写错误 | `sp_get_baking_parameters` 先读确认确切的参数名 |

---

## Related Skills

- [sp-index](../sp-index/SKILL.md) — 所有 skill 的索引
- [sp-texture-set](../sp-texture-set/SKILL.md) — 纹理集管理、烘焙前后的通道检查
- [sp-smart-material](../sp-smart-material/SKILL.md) — 烘焙是 Smart Material/Mask 的前置条件
- [sp-project](../sp-project/SKILL.md) — 烘焙前后保存、项目生命周期
- [sp-debug](../sp-debug/SKILL.md) — 烘焙超时/报错排查
