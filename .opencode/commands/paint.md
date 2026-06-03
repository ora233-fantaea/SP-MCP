---
description: 触发完整材质创作工作流
---

执行标准创作迭代循环：

1. **sp_ping** — 确认连接
2. **sp_capture_viewport(mode="quick")** — 看当前状态
3. **sp_get_layer_stack** — 分析图层结构
4. **[决策]** 根据用户需求和截图制定材质方案
5. **执行材质操作**：
   - `sp_apply_smart_material` — 应用 Smart Material
   - `sp_add_fill_layer` — 新建 Fill Layer
   - `sp_add_smart_mask` — 添加程序化遮罩
   - `sp_set_layer_property` — 调整属性
6. **sp_capture_viewport(mode="quick")** — 评估结果
7. **[评估]** 满意 → 继续，不满意 → 回步骤 5
8. **sp_capture_viewport(mode="render")** — 最终确认（可选）

原则：
- opacity 从 0.3–0.5 开始
- 每步截图确认
- 图层命名语义化
