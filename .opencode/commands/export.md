---
description: 导出 Substance Painter 贴图
---

导出 Substance Painter 贴图：

1. **sp_save_project()** — 保存当前项目
2. **sp_capture_viewport(mode="render")** — 最终渲染确认（可选）
3. **sp_export_textures(preset, output_dir)** — 导出贴图
   - preset: 如 `"PBR Metallic Roughness"`
   - output_dir: 输出目录绝对路径
4. 检查返回的文件列表，确认所有通道已导出

导出的文件可直接用于游戏引擎、渲染器或后续处理。