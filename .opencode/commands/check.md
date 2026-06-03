---
description: 验证 SP bridge 健康状态
---

执行以下检查：

1. **Mock 测试** — `pytest tests/ -m "not integration" -v`
   - 验证代码逻辑正确
   - 输出测试通过数

2. **sp_ping** — 验证 bridge 连通
   - 返回 SP 版本号和 smart_api 状态

3. **sp_get_layer_stack** — 验证项目已打开
   - 返回图层树 JSON
   - 失败说明 Painter 未运行或未打开项目

4. **sp_capture_viewport(mode="quick")** — 验证截图可用
   - 返回 base64 PNG
   - 失败说明 viewport 不可见

输出每步结果，有失败立即报告原因。
