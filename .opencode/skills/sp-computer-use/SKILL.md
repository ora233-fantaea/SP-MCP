---
name: sp-computer-use
description: 通过 Computer Use 控制 Substance Painter 窗口，包括截图、鼠标点击、
             键盘输入。用户要求在 SP 中执行 UI 操作（点击菜单、拖拽视角、
             输入文字等）时触发此 skill。
---

# SP Computer Use

通过 Windows API 控制 SP 窗口的 MCP tools 参考。

## ⚠️ 强制规则：警示条生命周期

**每次使用 Computer Use 都必须遵守以下流程，没有例外。**

### 开始控制前（必做）

```
第一步：sp_ping()                    确认 bridge 连通
第二步：sp_window_focus()            聚焦 SP 窗口 + 显示红色警示条
```

**任何** Computer Use 操作（mouse/key/grab/info）都必须在 `sp_window_focus()` 之后执行。
如果 `sp_window_focus` 返回 `focused: false`，停止操作并告知用户手动切换到 SP 窗口。

### 结束控制后（必做）

**所有** Computer Use 操作完成后，最后一步必须调用：

```
sp_cu_unlock()                       ← 🟢 绿色 → 10 秒后消失
```

### 警示条状态机

```
[隐藏] → sp_window_focus() → 🔴 红色 (MCP Control Active)
🔴 红色 → sp_cu_warning()  → 🟡 黄色 (Timeout - Check terminal)
🟡 黄色 → sp_cu_banner_text("...") → 🔴 恢复红色 或 🟢 sp_cu_unlock()
🔴 红色 → sp_cu_unlock()  → 🟢 绿色 (MCP Control Released) → 10 秒后 → [隐藏]
```

### 完整序列模板

```
sp_ping()
sp_window_focus()                    ← 🔴 警示条出现
  sp_window_grab()                   截图确认状态
  sp_mouse_click(...)                操作
  sp_key_send(...)                   操作
  ...                                更多操作
sp_cu_unlock()                       ← 🔴 警示条消失
```

---

## 超时处理（>30 秒无响应）

如果某个 Computer Use 操作（特别是 `sp_key_send` 或 `sp_mouse_click`）返回 timeout 或
30 秒内没有收到响应，执行以下流程：

```
1. sp_cu_warning("Timeout - Check terminal / SP dialogs")  ← 🟡 黄色警示条
2. 等待用户确认后，恢复红色：
   sp_cu_banner_text("MCP Control Active - Do not touch mouse/keyboard")
3. sp_cu_unlock()  ← 🟢 绿色 → 10 秒后消失
```

**常见超时原因：**
- SP 弹出了确认对话框（保存、覆盖等），阻塞了 UI
- SP 正在执行耗时操作（烘焙、导出），UI 被锁定
- 操作触发了外部程序或文件选择器
- 用户在 SP 中打开了模态对话框

**处理步骤：**
1. 更新警示条文字提醒用户检查 SP 窗口
2. 如果是确认对话框 → 等用户手动点击确认
3. 如果是文件选择器 → 等用户选择或取消
4. 如果是权限/路径读取 → 提示用户在系统弹窗中允许
5. 确认 SP 恢复正常后，恢复警示条文字，继续操作

---

## Tool 速查

### 窗口控制

**`sp_window_focus()`** — 聚焦 SP 窗口 + 显示红色警示条。
必须在任何 Computer Use 操作前调用。

**`sp_cu_unlock()`** — 隐藏警示条。所有操作结束后调用。

**`sp_cu_warning(text?)`** — 将警示条切换为黄色等待状态。
不传 text 时使用默认提示文字 `"Timeout - Check terminal"`。
用户处理完毕后用 `sp_cu_banner_text` 恢复红色，或直接 `sp_cu_unlock`。

**`sp_cu_banner_text(text)`** — 更新警示条显示的文字。
用于超时时显示提示信息，恢复正常后传入原始文字。

**`sp_window_info()`** — 返回窗口位置/尺寸/状态。
用于坐标映射：截图中的像素坐标 = 屏幕坐标 - `screen_origin`。

**`sp_window_grab(region?)`** — 截取 SP 窗口。
- 不传 region：截取整个 SP 窗口
- 传 region：`{"x": 0, "y": 0, "width": 400, "height": 300}`（相对窗口左上角）

### 鼠标

**`sp_mouse_move(x, y, relative?)`** — 移动鼠标。
- `relative="screen"`（默认）：屏幕绝对坐标
- `relative="window"`：相对 SP 窗口左上角

**`sp_mouse_click(x?, y?, button?, clicks?, relative?)`** — 点击。
- button：`"left"` / `"right"` / `"middle"`
- clicks：1=单击（默认），2=双击
- 不传 x/y：在当前位置点击

**`sp_mouse_scroll(amount)`** — 滚轮。
- 正值=向上滚，负值=向下滚
- ±120 = 1 个 notch

**`sp_mouse_drag(x1, y1, x2, y2, button?, relative?)`** — 拖拽。
- 从 (x1,y1) 拖到 (x2,y2)

### 键盘

**`sp_key_send(keys, modifiers?)`** — 发送键盘输入。
- 普通字符：`sp_key_send("hello")` → 逐键打出
- 单键：`sp_key_send("enter")` / `sp_key_send("tab")` / `sp_key_send("escape")`
- 组合键：`sp_key_send("a", ["ctrl"])` → Ctrl+A
- 多修饰键：`sp_key_send("s", ["ctrl", "shift"])` → Ctrl+Shift+S

**支持的键名：** enter, tab, esc, space, backspace, delete, home, end, pageup, pagedown, left, right, up, down, f1-f12, ctrl, shift, alt

**`sp_shortcut(action)`** — 预定义快捷键封装，不需要记录键。

| 类别 | action | 快捷键 |
|------|--------|--------|
| **文件** | `save` | Ctrl+S |
| | `save_as` | Ctrl+Shift+S |
| | `new_project` | Ctrl+N |
| | `open_project` | Ctrl+O |
| | `close_project` | Ctrl+W |
| | `import_image` | Ctrl+I |
| | `export_textures` | Ctrl+Shift+E |
| **编辑** | `undo` | Ctrl+Z |
| | `redo` | Ctrl+Y |
| | `select_all` | Ctrl+A |
| | `deselect` | Ctrl+Shift+A |
| | `copy` | Ctrl+C |
| | `paste` | Ctrl+V |
| | `cut` | Ctrl+X |
| | `duplicate` | Ctrl+D |
| | `delete_layer` | Delete |
| **图层** | `new_fill_layer` | Ctrl+Shift+F |
| | `new_paint_layer` | Ctrl+Shift+P |
| | `new_group` | Ctrl+Shift+G |
| | `merge_down` | Ctrl+E |
| **视口** | `frame_all` | Alt+F |
| | `toggle_wireframe` | F4 |
| | `toggle_unity` | F5 |
| **模式** | `paint_mode` | 1 |
| | `erase_mode` | 2 |
| | `project_mode` | 3 |
| **显示** | `toggle_ui` | Space |
| | `toggle_mask_view` | Alt+M |
| **Iray** | `toggle_iray` | F10 |

---

## 坐标映射流程

截图中的 UI 元素坐标 ≠ 屏幕坐标，需要减去窗口偏移：

```
1. sp_window_info()                    获取 screen_origin: {x, y}
2. sp_window_grab()                    截图
3. 视觉模型分析截图，得到元素在截图中的像素坐标 (px, py)
4. 屏幕绝对坐标 = (px + screen_origin.x, py + screen_origin.y)
5. sp_mouse_click(屏幕x, 屏幕y)       点击目标位置
```

如果使用 `relative="window"`，则传入截图中的像素坐标即可（自动加偏移）。

---

## SP 常见 UI 操作

### 旋转 3D 视角

```
sp_window_focus()
sp_window_grab()                       确认 viewport 位置
sp_mouse_drag(x1, y1, x2, y2, "left", "window")   Alt+拖拽
sp_window_grab()                       截图验证旋转结果
sp_cu_unlock()
```

**注意：** SP 旋转视角 = Alt + 左键拖拽。但 `sp_mouse_drag` 不支持同时按住修饰键。
替代方案：用 `sp_run_python` 直接发送 Alt+drag：

```python
import time, ctypes as ct
user32 = ct.windll.user32
user32.keybd_event(0x12, 0, 0, 0)           # Alt down
user32.SetCursorPos(x1, y1)
user32.mouse_event(0x0002, 0, 0, 0, 0)      # Left down
for i in range(0, steps):
    user32.SetCursorPos(x1 + dx*i//steps, y1 + dy*i//steps)
    time.sleep(0.01)
user32.mouse_event(0x0004, 0, 0, 0, 0)      # Left up
user32.keybd_event(0x12, 0, 0x0002, 0)      # Alt up
```

### 点击菜单

```
sp_window_focus()
sp_window_grab()                       截图定位菜单位置
sp_mouse_click(菜单x, 菜单y, "left", "window")
sp_window_grab()                       确认菜单展开
sp_mouse_click(选项x, 选项y, "left", "window")
sp_cu_unlock()
```

### 点击图层面板

```
sp_window_focus()
sp_window_grab()                       截图定位图层
sp_mouse_click(图层x, 图层y, "left", "window")
sp_cu_unlock()
```

### 输入文字（搜索栏等）

```
sp_window_focus()
sp_mouse_click(搜索栏x, 搜索栏y, "left", "window")   先聚焦输入框
sp_key_send("搜索关键词")                               输入文字
sp_key_send("enter")                                    确认
sp_cu_unlock()
```

---

## 常见错误

| 错误 | 原因 | 解决 |
|------|------|------|
| 点击无反应 | SP 窗口不在前台 | 重新调 `sp_window_focus` |
| 视角没变化 | 拖拽坐标不在 viewport 内 | 用 `sp_window_grab` 重新定位 |
| 文字输入到错误位置 | 没先点击输入框 | 先 `sp_mouse_click` 聚焦目标 |
| 操作触发了意外 UI | 坐标偏移计算错误 | 检查 `screen_origin` 或用 `relative="window"` |
| Timeout / 30 秒无响应 | SP 弹出对话框阻塞 UI | 更新警示条文字提醒用户检查 SP 窗口 |

---

## Related Skills

- [sp-index](../sp-index/SKILL.md) — 所有 skill 的索引
- [sp-quickstart](../sp-quickstart/SKILL.md) — 首次连接验证（含 CU quickstart 变体）
- [sp-debug](../sp-debug/SKILL.md) — CU 操作超时/报错的排查
- [sp-camera](../sp-camera/SKILL.md) — 相机控制（可用 CU 拖拽旋转作为替代）
- [sp-paint-layer](../sp-paint-layer/SKILL.md) — CU 手绘笔刷操控
