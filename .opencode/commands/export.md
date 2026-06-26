---
description: 导出 Substance Painter 贴图
---

导出 Substance Painter 贴图：

1. **sp_ping()** — 确认连接
2. **sp_get_project_info()** — 确认项目状态
3. **sp_save_project()** — 保存当前项目
4. **sp_get_texture_sets()** — 确认纹理集分辨率
5. **sp_capture_viewport(mode="render")** — 最终渲染确认（可选）
   - 需要先 Iray 渲染：`sp_set_iray_params` → `sp_start_iray_render` → 等待 → `sp_capture_viewport("render")`
6. **sp_list_resources_by_usage("export_preset")** — 浏览可用导出预设
7. **sp_export_textures(preset, output_dir)** — 导出贴图
   - preset: 如 `"PBR Metallic Roughness"`、`"Unreal Engine 4 (Packed)"`
   - output_dir: 输出目录绝对路径
8. 检查返回的文件列表，确认所有通道已导出

导出的文件可直接用于游戏引擎、渲染器或后续处理。
