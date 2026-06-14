---
name: sp-quickstart
description: 首次连接 Substance Painter 的端到端上手流程。LLM 第一次操作 SP 时
             必须先执行此 skill，逐项验证连通性、项目状态、截图可用性，
             然后做一个最小修改来确认整条链路畅通。
---

# SP Quickstart

首次连接 SP-MCP 的标准化上手流程。**任何新 session 开始操作 SP 前，必须先走完此流程。**

## 强制检查清单

按顺序执行，每步失败则停在当前步骤排查：

```
1. sp_ping()                            → 确认 bridge 在线
2. sp_get_project_info()                → 确认项目已打开
3. sp_get_texture_sets()                → 确认有哪些纹理集
4. sp_get_layer_stack()                 → 确认图层可读
5. sp_capture_viewport(mode="quick")    → 确认截图可用
6. [最小修改]                            → 确认写入链路畅通
7. sp_capture_viewport(mode="quick")    → 确认修改生效
8. sp_save_project()                    → 保存
```

---

## 每步详解

### Step 1: 确认 Bridge 在线

```
sp_ping()
```

**预期返回：**
```json
{"status": "ok", "sp_version": "10.0.1", "smart_api": true}
```

**失败排查：**
| 症状 | 解决 |
|------|------|
| `ConnectionError` | Painter 未启动，或插件未加载。检查 Painter Python Console 是否有 `[INFO] sp_bridge: SP Bridge started on port 27182` |
| timeout | Bridge 线程卡死。重启 Painter |

---

### Step 2: 确认项目已打开

```
sp_get_project_info()
```

**预期返回：**
```json
{"name": "MyProject", "file_path": "E:/projects/MyProject.spp", "is_open": true, "is_busy": false}
```

**关键判断：**
- `is_open: false` → 在 Painter 中打开一个项目
- `is_busy: true` → 等待渲染/导出完成后再继续
- `file_path` 为空 → 项目未保存过，先 `sp_save_project()`

---

### Step 3: 确认纹理集

```
sp_get_texture_sets()
```

**预期返回：**
```json
[
  {"id": "249", "name": "default", "resolution": "2048x2048", "layers": [...]},
  {"id": "250", "name": "body", "resolution": "4096x4096", "layers": [...]}
]
```

**判断：**
- 返回空列表 → 模型没有纹理集，检查 SP 中的 Texture Set List 面板
- 多个纹理集 → 确认当前要对哪个操作，必要时用 `sp_set_active_texture_set("name")` 切换

---

### Step 4: 确认图层可读

```
sp_get_layer_stack()
```

**预期返回：** 至少有一个图层节点（通常是最底层的初始材质层）。

**判断：**
- 返回 `[]` → 纹理集没有图层，可能是一个空白项目
- `type: "GroupLayerNode"` 有 `children` → 分组结构正常

---

### Step 5: 确认截图可用

```
sp_capture_viewport(mode="quick")
```

**预期返回：**
```json
{"image": "<base64 PNG>", "width": 1052, "height": 606}
```

**判断：**
- 返回全黑或空白 → 3D viewport 可能被遮挡，调整 SP 窗口布局
- `width` / `height` 为 0 → viewport 未正确初始化

---

### Step 6: 最小写入验证（"Hello World"）

这是最关键的一步——验证整条**写入链路**畅通：

```
sp_begin_batch("Quickstart Test")
  sp_add_fill_layer(name="QS_Test", color_hex="#FF4444", opacity=0.5)
sp_end_batch()
```

然后在 SP 中检查：
- 图层面板出现 `QS_Test` 图层
- 3D viewport 上模型变红

---

### Step 7: 截图确认修改

```
sp_capture_viewport(mode="quick")
```

对比 Step 5 的截图，确认模型外观有变化（红色叠加）。

---

### Step 8: 清理并保存

```
sp_delete_layer(layer_id="<QS_Test 的 id>")
sp_save_project()
```

> ⚠️ 操作前要从 `sp_get_layer_stack()` 重新获取 `QS_Test` 的实际 layer_id。

---

## 常见首次连接问题

| 问题 | 原因 | 解决 |
|------|------|------|
| `sp_ping` 成功但 `sp_get_layer_stack` 报错 | 项目未打开 | 在 Painter 中打开任意 .spp 项目 |
| 截图一片空白 | Viewport 最小化或不可见 | 确保 3D view 面板可见且模型在视口内 |
| `sp_add_fill_layer` 没反应 | 纹理集未正确选择 | 先调 `sp_get_texture_sets` + `sp_set_active_texture_set` |
| 所有写入 tool 报 timeout | SP 主线程被阻塞（渲染中） | 等待 Iray 完成或取消渲染 |

---

## Quickstart 变体

### 只读检查（不修改项目）

```
sp_ping() → sp_get_project_info() → sp_get_texture_sets() → sp_get_layer_stack() → sp_capture_viewport("quick")
```

适合"帮我看看当前 SP 的项目是什么状态"类型的请求。

### 完整材质制作（Quickstart + Creative Workflow）

Quickstart 1–5 走完后，进入 [sp-creative-workflow](../sp-creative-workflow/SKILL.md) 的标准迭代循环。

---

## 与 Computer Use Quickstart

如果用户要求通过 UI 操作 SP，在 Quickstart 后追加：

```
sp_window_focus()       ← 聚焦 SP + 显示红色警示条
sp_window_info()         ← 获取窗口位置
sp_window_grab()         ← 截图确认 UI 布局
  ... Computer Use 操作 ...
sp_cu_unlock()           ← 释放 + 隐藏警示条
```

详见 [sp-computer-use](../sp-computer-use/SKILL.md)。

---

## Related Skills

- [sp-index](../sp-index/SKILL.md) — 所有 skill 的索引，不确定用什么先看这个
- [sp-creative-workflow](../sp-creative-workflow/SKILL.md) — 连接验证后进入材质创作流程
- [sp-debug](../sp-debug/SKILL.md) — 任何步骤失败时的排查指南
- [sp-computer-use](../sp-computer-use/SKILL.md) — CU 模式的完整操作流程
- [sp-project](../sp-project/SKILL.md) — 项目保存、撤销