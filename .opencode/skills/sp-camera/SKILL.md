---
name: sp-camera
description: 控制 Substance Painter 相机位置/旋转/FOV、HDRI 环境光切换、
             Iray 渲染流程。用户要求调整视角、打光、渲染截图时触发此 skill。
---

# SP Camera & Rendering

相机控制、环境光、Iray 渲染的完整工作流。

## ⚠️ 核心原则：先读后改

**任何相机操作前，必须先读取当前状态。**

| 操作前必读 | 说明 |
|---|---|
| `sp_capture_viewport("quick")` | 先看当前视角 |
| `sp_run_python` 读 `cam.position` / `cam.rotation` | 修改前确认当前值 |

---

## 相机控制

### set_camera 参数规则

所有参数默认 `0.0`，表示"保持当前值不变"。只有非零值会修改对应属性。

| 参数 | 说明 |
|---|---|
| `x, y, z` | 相机世界坐标位置 |
| `target_x, target_y, target_z` | 相机朝向目标点（会自动计算欧拉角旋转） |
| `fov` | 视场角（度），默认 45 |

### 旋转相机（原地转头）

`set_camera` 的 `target_x/y/z` 会覆盖 rotation。要原地旋转相机，**直接赋值 `cam.rotation`**：

```python
import substance_painter.display as display
cam = display.Camera.get_default_camera()
cur = list(cam.rotation)
cam.rotation = [cur[0] + 30, cur[1], cur[2]]  # X轴转30度
```

**欧拉角注意：** SP 内部会重新映射欧拉角，`X+30` 可能变成 `Z` 变化。实际 3D 旋转效果正确，但数值显示可能不符合直觉。

### Frame Mesh（自动适配视图）

```python
import sp_bridge.handlers as h
h.frame_mesh()
```

相机沿当前视线方向移动到适配模型的距离，**保留旋转角度**。

### 典型相机操作

| 需求 | 方法 |
|------|------|
| 只改 FOV | `sp_set_camera(fov=60)` |
| 只改位置 | `sp_set_camera(x=100, y=50, z=0)` |
| 旋转朝向目标 | `sp_set_camera(target_x=0, target_y=60, target_z=0)` |
| 原地旋转 | `cam.rotation = [x, y, z]` |
| 适配模型 | `h.frame_mesh()` |

---

## 环境光

**`sp_set_environment(preset)`** — 切换 HDRI 环境光预设。

常用预设：
- `"Studio"` — 均匀打光，适合材质预览
- `"Sunrise"` / `"Sunset"` — 暖色调自然光
- `"Night"` — 冷色调低光
- `"Neutral"` — 中性灰，无色偏

**工作流：** 先 `sp_capture_viewport("quick")` 看当前光照 → `sp_set_environment` 切换 → 再截图对比。

---

## Iray 渲染

### 标准流程

```
1. sp_set_iray_params(max_samples=100, max_time=60)   设置参数
2. sp_start_iray_render()                               启动渲染（异步）
3. sp_check_iray_render()                               轮询状态（iterations/time）
4. 等 iterations 稳定                                   渲染完成
5. sp_capture_viewport(mode="render")                   截取渲染结果
```

### 参数建议

| 用途 | max_samples | max_time |
|------|-------------|----------|
| 快速预览 | 50 | 30 |
| 质量预览 | 100 | 60 |
| 最终渲染 | 500 | 300 |

### 注意事项

- `start_iray_render` 是异步的，不阻塞 HTTP
- `check_iray_render` 返回 `iterations`（如 `"120/100"`）和 `time`
- 当 iterations 不再变化时，渲染已完成
- `capture_viewport("render")` 截取的是 Iray 渲染结果，不是实时 viewport

---

## 截图对比工作流

调整视角/光照后，用截图对比确认效果：

```
1. sp_capture_viewport("quick")       记录当前状态
2. sp_set_environment("Studio")       切换光照
3. sp_capture_viewport("quick")       对比
4. sp_set_iray_params(100, 60)
5. sp_start_iray_render()
6. [轮询 sp_check_iray_render]
7. sp_capture_viewport("render")      最终确认
```

> 📘 Iray 渲染的详细参数调优、进度监控、常见问题见 [sp-iray](../sp-iray/SKILL.md)。

---

## Related Skills

- [sp-index](../sp-index/SKILL.md) — 所有 skill 的索引
- [sp-iray](../sp-iray/SKILL.md) — Iray 渲染引擎详解（参数、进度、问题排查）
- [sp-creative-workflow](../sp-creative-workflow/SKILL.md) — 截图驱动的材质迭代
- [sp-computer-use](../sp-computer-use/SKILL.md) — CU 方式旋转视角（Alt+拖拽）
- [sp-export-pipeline](../sp-export-pipeline/SKILL.md) — 渲染后导出贴图
