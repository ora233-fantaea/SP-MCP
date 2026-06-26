---
description: 触发完整材质创作工作流
---

执行标准创作迭代循环：

1. **sp_ping** — 确认连接
2. **sp_get_project_info** — 确认项目已打开
3. **sp_get_texture_sets** — 确认纹理集
4. **sp_capture_viewport(mode="quick")** — 看当前状态
5. **sp_get_layer_stack** — 分析图层结构
6. **[决策]** 根据用户需求和截图制定材质方案
7. **执行材质操作**：
   - `sp_apply_smart_material` / `sp_apply_material` — 应用材质
   - `sp_add_fill_layer` — 新建图层
   - `sp_add_smart_mask` — 添加程序化遮罩
   - `sp_set_layer_channel` — 调整通道值
   - `sp_set_substance_parameters` — 微调程序化源参数
   - `sp_add_levels_effect` / `sp_add_filter_effect` — 添加效果节点
   - `sp_set_tone_mapping` — 调整色调映射
8. **sp_capture_viewport(mode="quick")** — 评估结果
9. **[评估]** 满意 → 继续，不满意 → 回步骤 7
10. **sp_save_project()** — 保存

原则：
- 先读后改（每步操作前确认当前状态）
- opacity 从 0.3–0.5 开始
- 每步截图确认
- 图层命名语义化
- 批量操作用 `sp_begin_batch` / `sp_end_batch`
