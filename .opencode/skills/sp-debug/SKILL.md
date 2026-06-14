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

### "vectorial is not a valid Type"

**症状：** `list_shelf_materials("")` 遇到未知资源类型

**解决：** handler 已加 try/except 容错，遇到未知类型自动跳过

### "This node already has a mask"

**症状：** 对已有遮罩的图层再次调用 `add_smart_mask`

**解决：** 先用 `delete_layer` 删掉旧遮罩，或换一个图层

### "RuntimeError: move_layer / group_layers / ungroup_layer NotImplementedError"

**症状：** `NotImplementedError: move_layer / group_layers / ungroup_layer`

**解决：** Phase 13 后这三个操作已通过 delete+re-insert 工作流实现。
如果仍然报错，说明 handlers.py 版本过旧，热重载或重启 Painter。

### "alg.ui.clickButton 报错"

**症状：** `findChild of undefined`

**解决：** SP 10.0.1 的已知 bug，用 Computer Use 鼠标点击替代。

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
Copy-Item "E:\SP-MCP\plugin\sp_bridge\handlers.py" "$env:USERPROFILE\Documents\Adobe\Adobe Substance 3D Painter\python\plugins\sp_bridge\handlers.py" -Force

# 2. 在 Painter Python Console 执行：
import importlib, sp_bridge.handlers; importlib.reload(sp_bridge.handlers)
```

---

## sp_run_python Cookbook

`sp_run_python` 是 escape hatch，在主线程执行任意 Python。
**优先用具体 tool，只有 tool 覆盖不到时才用这个。**
以下是最常用的代码片段。

### 读取相机状态

```python
import substance_painter.display as display
cam = display.Camera.get_default_camera()
print(f"position: {cam.position}")
print(f"rotation: {cam.rotation}")
print(f"fov: {cam.fov}")
```

### 修改相机原地旋转

```python
import substance_painter.display as display
cam = display.Camera.get_default_camera()
cur = list(cam.rotation)
cam.rotation = [cur[0] + 30, cur[1], cur[2]]
```

### 读取纹理集分辨率

```python
import substance_painter.textureset as ts
for t in ts.all_texture_sets():
    res = t.get_resolution()
    print(f"{t.name()}: {res.width}x{res.height}")
```

### 遍历所有纹理集的所有图层

```python
import substance_painter.textureset as ts
import substance_painter.layerstack as ls

def _print_tree(node, depth):
    indent = "  " * depth
    print(f"{indent}[{type(node).__name__}] {node.get_name()} (uid={node.get_uid()})")
    if type(node).__name__ == "GroupLayerNode":
        for child in node.sub_layers():
            _print_tree(child, depth + 1)

for t in ts.all_texture_sets():
    print(f"=== {t.name()} ({t.get_resolution().width}x{t.get_resolution().height}) ===")
    for node in ls.get_root_layer_nodes(t.get_stack()):
        _print_tree(node, 0)
```

### 批量修改所有图层的 opacity

```python
import substance_painter.layerstack as ls
import substance_painter.textureset as ts
from substance_painter.layerstack import ChannelType

stack = ts.get_active_stack()
for node in ls.get_root_layer_nodes(stack):
    for ch in [ChannelType.BaseColor, ChannelType.Roughness,
               ChannelType.Metallic, ChannelType.Height, ChannelType.Normal]:
        try:
            current = node.get_opacity(ch)
            if current > 0:
                node.set_opacity(ch, current * 0.5)  # 减半
        except:
            pass
```

### 读取图层的 source 值

```python
import substance_painter.layerstack as ls
node = ls.get_node_by_uid(123)  # 替换为实际 uid
ch = ls.ChannelType.BaseColor
source = node.get_source(ch)
print(type(source).__name__)  # SourceUniformColor
if hasattr(source, 'get_color'):
    color = source.get_color()
    print(f"RGB: {color.value_raw}")
```

### 获取模型包围盒

```python
import substance_painter.project as proj
bb = proj.get_scene_bounding_box()
print(f"Center: {bb.center}")
print(f"Dimensions: {bb.dimensions}")
print(f"Radius: {bb.radius}")
```

### 调用 JS API

```python
import substance_painter.js as js
# 获取活动纹理集名称
result = js.evaluate("alg.texturesets.getActiveTextureSet()")
print(result)
# 导出贴图
js.evaluate('alg.mapexport.save("E:/export/my_textures")')
```

### 探索未知模块的 API

```python
import substance_painter.display as display
cam = display.Camera.get_default_camera()
print("=== Attributes ===")
print([a for a in dir(cam) if not a.startswith('_')])
print("=== Methods ===")
print([a for a in dir(cam) if callable(getattr(cam, a, None)) and not a.startswith('_')])
```

### 使用原则

1. **先看后改** — 先读属性，确认值，再改
2. **打印确认** — 每次都 `print()` 返回值
3. **不要假设 API 存在** — SP 10.x API 与实际常有差异（参考 AGENTS.md「已知 API 事实」表）
4. **优先用 tool** — 99% 的操作标准 tool 就够了，这个只做探索和补缺

---

## Related Skills

- [sp-index](../sp-index/SKILL.md) — 所有 skill 的索引
- [sp-quickstart](../sp-quickstart/SKILL.md) — 逐步验证连通性
- [sp-project](../sp-project/SKILL.md) — 撤销误操作、保存恢复点
- [sp-computer-use](../sp-computer-use/SKILL.md) — CU 操作超时排查
