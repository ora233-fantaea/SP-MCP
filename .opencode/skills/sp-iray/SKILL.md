---
name: sp-iray
description: 控制 Substance Painter Iray 渲染引擎：参数设置、异步启动、
             进度轮询、渲染截图。用户提到 Iray/渲染/ray tracing/光线追踪/
             高质量截图时触发此 skill。
---

# SP Iray Rendering

Iray 是 Substance Painter 内置的 GPU 光线追踪渲染器，能产生照片级真实感的渲染结果。
与 viewport 实时预览不同，Iray 计算全局光照、反射、折射，适合**最终确认**和**展示用截图**。

## ⚠️ 核心约束

| 约束 | 说明 |
|------|------|
| **渲染期间主线程阻塞** | Iray 运行时，所有 bridge 请求（包括 `sp_ping`）都会 timeout |
| **启动是异步的** | `sp_start_iray_render` 通过 QTimer 触发，HTTP 不会阻塞 |
| **渲染中轮询也会 timeout** | `sp_check_iray_render` 在渲染期间同样会被阻塞 |
| **不要在渲染期间做其他操作** | 等 `sp_check_iray_render` 恢复响应，说明渲染完成 |

## 标准流程

```
1. sp_set_camera(x, y, z, ...)             调整到想要的视角（可选）
2. sp_set_environment("Studio")            设置 HDRI 环境光（可选）
3. sp_set_iray_params(max_samples=100, max_time=60)  设参数
4. sp_start_iray_render()                  异步启动
5. sp_check_iray_render()                  轮询（可能 timeout）
6. [等 10-30 秒]                           主线程阻塞，无响应
7. sp_check_iray_render()                  重试 → 返回 iterations/time
8. 等 iterations 稳定（不再增长）           渲染收敛
9. sp_capture_viewport(mode="render")       截取渲染结果
```

## 参数详解

**`sp_set_iray_params(max_samples, max_time, width, height)`**

| 参数 | 默认 | 说明 |
|------|------|------|
| `max_samples` | 100 | 每像素最大采样数。越高噪点越少，但耗时线性增长 |
| `max_time` | 60 | 最大渲染时间（秒）。到达后强制停止 |
| `width` | 1920 | 渲染分辨率宽 |
| `height` | 1080 | 渲染分辨率高 |

渲染实际的停止条件是 **max_samples 和 max_time 中先到达的那个**。

### 参数配方

| 用途 | max_samples | max_time | 分辨率 | 预估耗时 |
|------|-------------|----------|--------|---------|
| 快速预览 | 50 | 30 | 960×540 | 5-15s |
| 质量预览 | 100 | 60 | 1920×1080 | 15-30s |
| 高质量 | 300 | 120 | 1920×1080 | 30-90s |
| 最终渲染 | 500 | 300 | 3840×2160 | 2-5min |
| 展示级 | 1000 | 600 | 3840×2160 | 5-15min |

> ⚠️ 耗时取决于 GPU 性能和场景复杂度。复杂材质 + 高分辨率可能远超预估。

## 进度监控

**`sp_check_iray_render()`** 返回：

```json
{
  "status": "rendering",
  "iterations": "45/100",
  "time": "12s"
}
```

- `iterations`: `"<已完成>/<目标>"` — 如 `"100/100"` 表示已达目标采样数
- `time`: 已用时间
- 当 `iterations` 稳定不再增长时，渲染已收敛
- 如果返回 error/timeout，说明仍在渲染中（主线程阻塞）

### 渲染中 vs 渲染完成

```
渲染中: sp_check_iray_render() → ConnectionError / timeout（正常！等 10s 重试）
渲染完成: sp_check_iray_render() → {"iterations": "100/100", "time": "28s"}
```

## 渲染截图 vs 快速截图

| | `mode="quick"` | `mode="render"` |
|---|---|---|
| **技术** | `QPixmap.grab()` | Qt grab after Iray |
| **效果** | Viewport 实时预览 | Iray 光线追踪 |
| **光照** | 简化光照 | 完整全局光照 |
| **反射** | 无 | 完整反射/折射 |
| **耗时** | 毫秒级 | 渲染耗时后 + 毫秒 |
| **用途** | 迭代确认 | 最终确认、展示 |

**策略：** 迭代阶段用 `quick`，达到满意效果后用一次 Iray `render` 做最终确认。

## 渲染前检查清单

- [ ] 相机视角正确（`sp_set_camera` 或 `sp_frame_mesh`）
- [ ] HDRI 环境光已设置（`sp_set_environment`）
- [ ] 所有图层可见性正确
- [ ] 项目已保存（`sp_save_project`）
- [ ] 不做其他 bridge 请求，等渲染完成

## 取消渲染

Iray 没有 API 取消渲染。如果需要中断：

1. 在 Painter UI 中点击 Iray 工具栏的 Stop 按钮
2. 或等待 `max_time` 到达自动停止
3. 或用 Computer Use 点击 Stop 按钮：
   ```
   sp_window_focus()
   sp_window_grab()                         定位 Stop 按钮
   sp_mouse_click(x, y, "left", "window")   点击
   sp_cu_unlock()
   ```

## 常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
| `sp_start_iray_render` 没反应 | Iray 已经在运行 | 先在 SP 中停止当前渲染 |
| 渲染结果全黑 | 环境光设置为极暗或相机在模型内部 | `sp_set_environment("Studio")` + `sp_frame_mesh()` |
| 渲染结果噪点多 | max_samples 太低 | 提高 max_samples 到 300-500 |
| 渲染中途 timeout | 正常现象，主线程被阻塞 | 等 10-30s 后重试 `sp_check_iray_render` |
| 渲染后截图还是 viewport 画面 | 需要在渲染完成后截图 | 确认 `sp_check_iray_render` 返回收敛状态后再截图 |
| 渲染时间远超 max_time | max_time 参数未生效 | 在 Painter UI 中手动停止；检查 Iray 版本 |
| Iray 工具栏不可见 | 窗口布局问题 | `sp_shortcut("toggle_iray")` 或 F10 |

## Related Skills

- [sp-camera](../sp-camera/SKILL.md) — 相机控制、HDRI 环境光
- [sp-export-pipeline](../sp-export-pipeline/SKILL.md) — 渲染后导出贴图
- [sp-creative-workflow](../sp-creative-workflow/SKILL.md) — 迭代中何时用 quick vs render
- [sp-computer-use](../sp-computer-use/SKILL.md) — CU 点击 Iray UI 按钮