# SP MCP — AGENTS.md

## 项目概述

本项目为 Substance 3D Painter 实现一个 MCP（Model Context Protocol）server，
使 LLM（OpenCode 或其他支持 MCP 的客户端）能够通过结构化工具调用控制
Painter 的图层栈，并最终驱动 **视觉创作**（材质设计、皮肤制作等）工作流。

核心设计目标：
- LLM 读取图层树 → 推理 → 修改材质参数 → 截图确认 → 迭代
- 兼容所有支持 MCP stdio / SSE 的客户端（OpenCode、Claude Code、Cursor 等）
- Plugin 侧只用 Python 标准库 + PySide2（SP 内置），不依赖外部 pip 包

**开发进度和阶段任务见 → [PHASES.md](./PHASES.md)**
每次开始新任务前先读 PHASES.md，找到当前未完成的 Phase 继续执行。

---

## 已知 API 事实（重要，勿忽略）

Phase 2 探索发现以下与文档/预期不符的实际 API，所有代码必须遵循：

| 原假设 | 实际 API |
|---|---|
| `substance_painter.layers` | `substance_painter.layerstack` |
| `substance_painter.__version__` | `substance_painter.application.version()` → `"10.0.1"` |
| `is_enabled()` / `set_enabled()` | `is_visible()` / `set_visible()` |
| `get_child_layers()` | `get_root_layer_nodes(node.get_stack())` |
| 类型枚举 `"FILL"` / `"GROUP"` | `"FillLayer"` / `"GroupLayer"` |

---

## 仓库结构

```
sp-mcp/
├── plugin/                     # 装入 Painter 的嵌入式插件
│   ├── __init__.py             # 插件入口：start_plugin / close_plugin
│   ├── bridge.py               # HTTP server（独立线程）+ QTimer 轮询队列调度
│   └── handlers.py             # substance_painter.* API 的实际调用
├── server/
│   ├── sp_mcp.py               # FastMCP server，暴露 MCP tools
│   └── client.py               # 对 plugin HTTP bridge 的封装（requests）
├── tests/
│   ├── conftest.py             # substance_painter mock 注入
│   ├── test_handlers_mock.py   # mock 测试，不需要 Painter
│   └── test_server_tools.py    # server tool 测试，含 integration
├── AGENTS.md                   # 本文件，每次 session 必读
├── PHASES.md                   # 开发阶段规划，任务来源
├── mcp.json                    # MCP server 描述
└── pyproject.toml
```

### Plugin 安装路径（Windows）

```
%USERPROFILE%\Documents\Adobe\Adobe Substance 3D Painter\python\plugins\sp_bridge\
```

Plugin 加载成功后，SP Python Console 输出：
```
[INFO] sp_bridge: SP Bridge started on port 27182
```
日志文件：`%USERPROFILE%\sp_bridge.log`

---

## 架构

```
LLM / MCP Client
      ↕  stdio 或 SSE
  server/sp_mcp.py          外部进程，FastMCP，tool 定义
      ↕  HTTP POST localhost:27182
  plugin/bridge.py          Painter 内嵌 Python，HTTP server 线程
      ↕  QTimer 轮询队列（每 50ms，主线程执行）
  plugin/handlers.py        主线程执行，substance_painter.* API
      ↕
  Painter 图层栈 / 导出系统
```

**关键约束：** `substance_painter.*` 的所有 API 必须在 Painter 主线程执行。
bridge.py 用 `queue.Queue` + `QTimer`（50ms 轮询）实现跨线程调度，
HTTP handler 用 `threading.Event` 阻塞等待结果（timeout 10s）。

注意：`substance_painter.ui.schedule_on_ui_thread()` 在 SP 10.x 不存在，
不要使用。跨线程调度统一走 `_task_queue` + `QTimer` 方案。

---

## MCP Tools 参考

### 读取类

**`sp_ping`**
检查 bridge 连通性。应在任何操作序列开始前调用。
```
返回: {"status": "ok", "sp_version": "10.0.1", "smart_api": true}
```

**`sp_get_layer_stack`**
返回完整图层树 JSON。
需要 Painter 里有打开的项目，否则报错。
```
返回: [{"id": "...", "name": "Metal_Base", "type": "FillLayer", "visible": true}, ...]
```

**`sp_get_layer_properties(layer_id)`**
返回指定图层的详细属性。

**`sp_capture_viewport(mode="quick")`**
截取当前 3D viewport 为 PNG，以 base64 返回。
**这是视觉创作迭代的核心工具**——每次批量修改后必须调用。
```
mode="quick"   Qt grab，毫秒级，迭代用
mode="render"  Iray，秒级，最终确认用
返回: {"image": "<base64 PNG>", "width": int, "height": int}
```

### 写入类

**`sp_add_fill_layer(name, channel, color_hex, opacity, blend_mode)`**
在图层栈顶部新建 Fill Layer。
opacity 第一次建议 0.3–0.5，截图确认后再调整。

**`sp_set_layer_property(layer_id, prop, value)`**
prop 可选值：`opacity` / `visible` / `name` / `blend_mode`

**`sp_apply_smart_material(layer_id, material_name)`**
应用 Shelf 中的 Smart Material。需要 SP 10.0+。

**`sp_add_smart_mask(layer_id, mask_name)`**
添加程序化遮罩。常用值：`"Edge Wear"` / `"Dirt"` / `"Grunge Scratches"` / `"Rust"`

**`sp_list_shelf_materials(filter)`**
列出可用 Smart Material，支持关键词过滤。

**`sp_export_textures(preset, output_dir)`**
触发贴图导出，返回导出文件路径列表。

**`sp_run_python(code)`**
在主线程执行任意 Python 代码。
**仅作 escape hatch，优先用具体 tool。**

---

## 创作工作流规范

### 标准迭代循环

```
1. sp_ping()                    确认连接
2. sp_capture_viewport("quick") 看当前状态
3. sp_get_layer_stack()         理解图层结构
4. [决策] 制定材质方案
5. 执行材质操作
6. sp_capture_viewport("quick") 看结果
7. [评估] 满意 → export，不满意 → 回步骤 5
8. sp_capture_viewport("render") 最终确认
9. sp_export_textures()
```

### 原则

- 图层命名语义化（`"Rust_Overlay"` 而非 `"Layer_1"`）
- 先建基础材质，再叠加效果
- 每个视觉层次完成后截图，不要攒到最后
- opacity 从保守值开始（0.3–0.5），截图确认后调整

---

## 开发指南

### 环境

```
Substance 3D Painter  10.0.1
Python（外部 venv）    3.10+
fastmcp               0.9+
requests              2.31+
```

### 启动顺序

```
1. 启动 Painter，打开一个项目
2. 确认 Python Console 显示 [INFO] sp_bridge: SP Bridge started on port 27182
3. 激活 venv：.venv\Scripts\activate
4. 启动 MCP server：python server/sp_mcp.py
```

### OpenCode 配置（%APPDATA%\opencode\config.json）

```json
{
  "mcp": {
    "substance-painter": {
      "type": "local",
      "command": ["C:\\<项目路径>\\sp-mcp\\.venv\\Scripts\\python.exe", "server/sp_mcp.py"]
    }
  }
}
```

### 调试

Bridge 连通性测试（PowerShell）：
```powershell
Invoke-RestMethod -Uri http://127.0.0.1:27182 -Method POST `
  -ContentType "application/json" `
  -Body '{"method":"ping","params":{}}'
```

日志：`%USERPROFILE%\sp_bridge.log`

### 测试命令

```powershell
# mock 测试（不需要 Painter）
pytest tests/ -m "not integration" -v

# integration 测试（需要 Painter + 打开项目）
pytest tests/ -m integration -v
```

### 版本检测

```python
# 正确方式（Phase 2 验证）
import substance_painter.application
version_str = substance_painter.application.version()  # → "10.0.1"

# 错误方式（不要用）
# substance_painter.__version__  → 返回 SDK 版本 "0.3.0"，不是 Painter 版本
```

---

## 与 SP2VTF 的集成

```bash
# 导出后调用 SP2VTF 转换为 Source 引擎 VTF 格式
python sp2vtf/convert.py --input ./export/gun_skin_v1 --output ./vtf/
```

---

## 已知限制

- `sp_capture_viewport` 需要项目打开且 3D viewport 可见
- Smart Material API 需要 SP 10.0+，9.x 上相关 tool 返回明确错误
- Layer id 在 Painter 重启后会变化，不要跨 session 缓存
- `schedule_on_ui_thread` 在 SP 10.x 不存在，已用 QTimer 轮询方案替代
