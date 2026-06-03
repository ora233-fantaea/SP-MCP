---
description: 导出贴图并转换为 VTF 格式
---

导出 Substance Painter 贴图并转换为 Source 引擎格式：

1. **sp_capture_viewport(mode="render")** — 最终确认（可选）
2. **sp_export_textures(preset, output_dir)** — 导出贴图
   - preset: 如 `"PBR Metallic Roughness"`
   - output_dir: 输出目录绝对路径
3. **SP2VTF 转换**（可选）：
   ```bash
   python sp2vtf/convert.py --input <output_dir> --output <vtf_dir>
   ```

输出导出的文件路径列表。
