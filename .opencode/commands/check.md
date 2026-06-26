---
description: 验证 SP bridge 健康状态
---

执行以下检查：

1. **Mock 测试** — `pytest tests/ -m "not integration" -v`
   - 验证代码逻辑正确
   - 输出测试通过数

2. **sp_ping** — 验证 bridge 连通
   - 返回 SP 版本号和 smart_api 状态

3. **sp_get_project_info** — 验证项目状态
   - 返回 name / file_path / is_open / is_busy
   - is_open: false → 在 Painter 中打开项目
   - is_busy: true → 等待完成

4. **sp_get_texture_sets** — 验证纹理集可读
   - 返回所有纹理集及分辨率

5. **sp_get_layer_stack** — 验证图层可读
   - 返回图层树 JSON

6. **sp_capture_viewport(mode="quick")** — 验证截图可用
   - 返回 base64 PNG

输出每步结果，有失败立即报告原因。
