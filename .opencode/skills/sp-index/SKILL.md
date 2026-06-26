---
name: sp-index
description: SP-MCP skill 索引。当不确定用哪个 skill、或任务涉及多个 skill
             时优先查阅此索引。列出了每个 skill 的核心能力和触发条件。
---

# SP-MCP Skill Index

这是所有 SP-MCP skill 的索引。**不知道用什么 skill 时先看这里。**

## 按任务类型查找

### 我是第一次 / 新 session 开始
→ [sp-quickstart](../sp-quickstart/SKILL.md)

### 我要做材质 / 调整外观
| 需求 | Skill |
|------|-------|
| 创建/修改材质，需要截图迭代 | [sp-creative-workflow](../sp-creative-workflow/SKILL.md) |
| 浏览材质库，选 Smart Material / Mask | [sp-smart-material](../sp-smart-material/SKILL.md) |
| 操作图层（增删改、通道、遮罩） | [sp-layer-ops](../sp-layer-ops/SKILL.md) |
| 手绘细节 | [sp-paint-layer](../sp-paint-layer/SKILL.md) |
| 调整程序化源参数/预设 | [sp-substance-source](../sp-substance-source/SKILL.md) |
| 添加效果节点（Filter/Generator/Levels 等） | [sp-effect-nodes](../sp-effect-nodes/SKILL.md) |

### 我要控制画面 / 渲染
| 需求 | Skill |
|------|-------|
| 调整相机位置、视角、FOV | [sp-camera](../sp-camera/SKILL.md) |
| 色调映射 / 色彩 LUT / 包围盒 | [sp-camera](../sp-camera/SKILL.md) |
| Iray 光线追踪渲染 | [sp-iray](../sp-iray/SKILL.md) |
| 切换 HDRI 环境光 | [sp-camera](../sp-camera/SKILL.md) |

### 我要管理项目 / 纹理集
| 需求 | Skill |
|------|-------|
| 保存、撤销、批量操作 | [sp-project](../sp-project/SKILL.md) |
| 创建/打开/关闭项目、重载网格、元数据 | [sp-project](../sp-project/SKILL.md) |
| 切换纹理集、改分辨率 | [sp-texture-set](../sp-texture-set/SKILL.md) |
| 烘焙 mesh maps（参数控制 + 异步执行） | [sp-baking](../sp-baking/SKILL.md) |
| 导出贴图 | [sp-export-pipeline](../sp-export-pipeline/SKILL.md) |

### 我要操作 SP 的 UI
→ [sp-computer-use](../sp-computer-use/SKILL.md)

### 出问题了
→ [sp-debug](../sp-debug/SKILL.md)

---

## Skill 速查表

| # | Skill | 核心能力 | 触发关键词 |
|---|-------|---------|-----------|
| 1 | **sp-quickstart** | 首次连接端到端验证 | 第一次/开始/连接/上手 |
| 2 | **sp-creative-workflow** | 材质创作迭代循环 | 设计/美化/调整/做材质/做旧 |
| 3 | **sp-layer-ops** | 图层栈 API 完整参考（92 tools） | 图层/通道/opacity/blend |
| 4 | **sp-smart-material** | 材质库浏览/选择/叠加 + 资源发现 | 材质/贴材质/换材质/遮罩/磨损/脏迹 |
| 5 | **sp-paint-layer** | 绘画图层工作流 | 绘画/手绘/笔刷/paint |
| 6 | **sp-camera** | 相机/HDRI/色调映射/LUT/包围盒 | 视角/相机/光照/环境光/HDRI/色调 |
| 7 | **sp-iray** | Iray 渲染引擎 | Iray/渲染/光线追踪/高质量截图 |
| 8 | **sp-project** | 项目/保存/撤销/批量/生命周期/元数据 | 保存/撤销/重做/批量/项目信息/创建项目 |
| 9 | **sp-texture-set** | 纹理集/分辨率/通道管理 | 纹理集/分辨率/通道 |
| 10 | **sp-baking** | Python 烘焙 API（参数/状态/异步执行） | 烘焙/bake/mesh maps/AO/Curvature |
| 11 | **sp-export-pipeline** | 贴图导出 | 导出/输出贴图/export |
| 12 | **sp-computer-use** | UI 操控/键盘鼠标 | 点击/拖拽/输入/快捷键/操作 SP 界面 |
| 13 | **sp-debug** | 排错 + sp_run_python cookbook | 报错/连接失败/timeout/调试 |
| 14 | **sp-effect-nodes** | 效果节点（Filter/Generator/Levels/CompareMask/ColorSelection/Anchor） | 效果/滤镜/色阶/锚点/生成器/遮罩比较 |
| 15 | **sp-substance-source** | 程序化源参数/预设/输出映射 | 参数/预设/源输出/substance 参数 |

---

## 典型多 Skill 协作流程

### 完整材质制作（从零开始）
```
sp-quickstart         → 验证连通
sp-texture-set        → 确认纹理集
sp-baking             → 配置烘焙参数 + 执行烘焙
sp-smart-material     → 浏览材质库 + 发现资源
sp-substance-source   → 微调程序化源参数
sp-effect-nodes       → 添加色阶/滤镜等效果（可选）
sp-creative-workflow  → 迭代制作（内含 layer-ops）
sp-camera             → 调整视角 + 色调映射
sp-iray               → 最终渲染
sp-export-pipeline    → 导出
```

### 只需微调现有材质
```
sp-quickstart         → 验证连通（已有 session 可跳过）
sp-layer-ops          → 读取图层 → 修改参数
sp-substance-source   → 调整程序化源参数
sp-camera             → 截图确认
```

### 添加效果节点
```
sp-layer-ops          → 确认图层结构
sp-effect-nodes       → 添加/调整效果节点
sp-substance-source   → 微调效果的源参数
sp-creative-workflow  → 截图迭代确认
```

### 烘焙配置
```
sp-texture-set        → 确认纹理集
sp-baking             → 读取参数 → 设置参数 → 设置状态 → 执行烘焙
sp-project            → 保存项目
```

### UI 操作类任务
```
sp-computer-use       → 全程主导
sp-debug              → 出错时参考
```

### 项目级操作
```
sp-project            → 创建/打开/关闭项目、元数据管理
sp-baking             → 配置烘焙参数
sp-texture-set        → 切换纹理集
```

---

## Skill 依赖关系图

```
sp-index (本文件)
 ├── sp-quickstart ──────────→ sp-creative-workflow, sp-debug, sp-computer-use
 ├── sp-creative-workflow ───→ sp-layer-ops, sp-smart-material, sp-camera, sp-iray, sp-project, sp-effect-nodes, sp-substance-source, sp-baking
 ├── sp-layer-ops ───────────→ sp-smart-material, sp-creative-workflow, sp-paint-layer, sp-project, sp-effect-nodes, sp-substance-source, sp-baking
 ├── sp-smart-material ──────→ sp-layer-ops, sp-creative-workflow, sp-texture-set, sp-baking
 ├── sp-paint-layer ─────────→ sp-layer-ops, sp-computer-use, sp-smart-material
 ├── sp-camera ──────────────→ sp-iray, sp-creative-workflow, sp-computer-use
 ├── sp-iray ────────────────→ sp-camera, sp-export-pipeline, sp-creative-workflow
 ├── sp-project ─────────────→ sp-layer-ops, sp-texture-set, sp-quickstart, sp-baking
 ├── sp-texture-set ─────────→ sp-layer-ops, sp-project, sp-smart-material, sp-baking
 ├── sp-baking ──────────────→ sp-texture-set, sp-project, sp-smart-material
 ├── sp-export-pipeline ─────→ sp-project, sp-camera, sp-iray
 ├── sp-computer-use ────────→ sp-quickstart, sp-debug
 ├── sp-debug ───────────────→ sp-quickstart, sp-project
 ├── sp-effect-nodes ────────→ sp-layer-ops, sp-smart-material, sp-substance-source
 └── sp-substance-source ────→ sp-layer-ops, sp-effect-nodes, sp-creative-workflow
```
