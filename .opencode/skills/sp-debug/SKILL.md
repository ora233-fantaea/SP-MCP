---
name: sp-debug
description: 排查 SP MCP bridge 连接问题、plugin 加载失败、tool 调用报错。
             遇到连接错误、timeout、API 报错时触发此 skill。
---

# SP Debug

排查 SP MCP 连接和 API 问题。

## 快速诊断流程

```
1. sp_ping                              → 连通性
2. sp_get_layer_stack                   → 项目是否打开
3. sp_capture_viewport(mode="quick")    → 截图是否可用
4. 检查日志                              → 错误详情
```

## 常见问题

### Bridge 连接失败

**症状：** `ConnectionError: SP bridge not reachable`

**排查：**
1. 确认 Painter 已启动
2. 确认 Python Console 显示 `[INFO] sp_bridge: SP Bridge started on port 27182`
3. 手动测试：`Invoke-RestMethod -Uri http://127.0.0.1:27182 -Method POST -ContentType "application/json" -Body '{"method":"ping","params":{}}'`

### Timeout

**症状：** `ConnectionError: SP bridge timeout after 12s`

**排查：**
1. 检查是否在 Iray 渲染中（渲染期间所有请求 timeout）
2. 等待 Iray 完成后重试
3. 简单操作（ping/get_layer_stack）不应 timeout

### "No project loaded"

**症状：** `RuntimeError: No project loaded`

**解决：** 在 Painter 中打开一个项目

### "No module named 'substance_painter.layers'"

**症状：** handlers.py 导入旧模块名

**解决：** 确认 handlers.py 已更新为 `substance_painter.layerstack`

### Smart API 不可用

**症状：** `"requires SP 10.0+"`

**排查：**
- 确认 Painter 版本 ≥ 10.0
- `_has_smart_api()` 使用 `application.version()` 而非 `__version__`

## 日志位置

```
%USERPROFILE%\sp_bridge.log
```

查看最近错误：
```powershell
Get-Content "$env:USERPROFILE\sp_bridge.log" -Tail 20
```

## 重启 Bridge

1. 关闭 Painter
2. 重新启动 Painter
3. 确认 Console 显示 `[INFO] sp_bridge: SP Bridge started on port 27182`
4. 测试 `sp_ping`

## 热重载（不重启 Painter）

```powershell
# 1. 复制更新的 handlers.py
Copy-Item "E:\SP-MCP\plugin\handlers.py" "$env:USERPROFILE\Documents\Adobe\Adobe Substance 3D Painter\python\plugins\sp_bridge\handlers.py" -Force

# 2. 在 Painter Python Console 执行：
import importlib, sp_bridge.handlers; importlib.reload(sp_bridge.handlers)
```
