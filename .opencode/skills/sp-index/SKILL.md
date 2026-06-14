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

### 我要控制画面 / 渲染
| 需求 | Skill |
|------|-------|
| 调整相机位置、视角、FOV | [sp-camera](../sp-camera/SKILL.md) |
| Iray 光线追踪渲染 | [sp-iray](../sp-iray/SKILL.md) |
| 切换 HDRI 环境光 | [sp-camera](../sp-camera/SKILL.md) |

### 我要管理项目 / 纹理集
| 需求 | Skill |
|------|-------|
| 保存、撤销、批量操作 | [sp-project](../sp-project/SKILL.md) |
| 切换纹理集、改分辨率、烘焙 | [sp-texture-set](../sp-texture-set/SKILL.md) |
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
| 3 | **sp-layer-ops** | 图层栈 API 完整参考 | 图层/通道/opacity/blend |
| 4 | **sp-smart-material** | 材质库浏览/选择/叠加 | 材质/贴材质/换材质/遮罩/磨损/脏迹 |
| 5 | **sp-paint-layer** | 绘画图层工作流 | 绘画/手绘/笔刷/paint |
| 6 | **sp-camera** | 相机/HDRI 环境光 | 视角/相机/光照/环境光/HDRI |
| 7 | **sp-iray** | Iray 渲染引擎 | Iray/渲染/光线追踪/高质量截图 |
| 8 | **sp-project** | 项目/保存/撤销/批量 | 保存/撤销/重做/批量/项目信息 |
| 9 | **sp-texture-set** | 纹理集/分辨率/烘焙 | 纹理集/烘焙/分辨率/通道 |
| 10 | **sp-export-pipeline** | 贴图导出 | 导出/输出贴图/export |
| 11 | **sp-computer-use** | UI 操控/键盘鼠标 | 点击/拖拽/输入/快捷键/操作 SP 界面 |
| 12 | **sp-debug** | 排错 + sp_run_python | 报错/连接失败/timeout/调试 |

## 典型多 Skill 协作流程

### 完整材质制作（从零开始）
```
sp-quickstart       → 验证连通
sp-texture-set      → 确认纹理集 + 烘焙
sp-smart-material   → 浏览材质库
sp-creative-workflow → 迭代制作（内含 layer-ops）
sp-camera           → 调整视角
sp-iray             → 最终渲染
sp-export-pipeline  → 导出
```

### 只需微调现有材质
```
sp-quickstart       → 验证连通（已有 session 可跳过）
sp-layer-ops        → 读取图层 → 修改参数
sp-camera           → 截图确认
```

### UI 操作类任务
```
sp-computer-use     → 全程主导
sp-debug            → 出错时参考
```

### 排错
```
sp-debug            → 诊断流程
sp-quickstart       → 逐步排查
```

---

## Skill 依赖关系图

```
sp-index (本文件)
 ├── sp-quickstart ─────→ sp-creative-workflow, sp-debug, sp-computer-use
 ├── sp-creative-workflow → sp-layer-ops, sp-smart-material, sp-camera, sp-iray, sp-project
 ├── sp-layer-ops ──────→ sp-smart-material, sp-creative-workflow, sp-paint-layer, sp-project
 ├── sp-smart-material ──→ sp-layer-ops, sp-creative-workflow, sp-texture-set
 ├── sp-paint-layer ────→ sp-layer-ops, sp-computer-use, sp-smart-material
 ├── sp-camera ─────────→ sp-iray, sp-creative-workflow, sp-computer-use
 ├── sp-iray ───────────→ sp-camera, sp-export-pipeline, sp-creative-workflow
 ├── sp-project ────────→ sp-layer-ops, sp-texture-set, sp-quickstart
 ├── sp-texture-set ────→ sp-layer-ops, sp-project, sp-smart-material, sp-iray
 ├── sp-export-pipeline ─→ sp-project, sp-camera, sp-iray
 ├── sp-computer-use ───→ sp-quickstart, sp-debug
 └── sp-debug ──────────→ sp-quickstart, sp-project
```