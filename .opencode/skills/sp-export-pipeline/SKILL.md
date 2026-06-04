---
name: sp-export-pipeline
description: 触发 Substance Painter 贴图导出并对接 SP2VTF 完成 Source 引擎
             格式转换。用户提到导出、转 VTF、L4D2 材质时触发此 skill。
---

# SP Export Pipeline

Substance Painter 贴图导出 + SP2VTF 格式转换。

## 导出工作流

```
1. sp_save_project()                    保存当前项目
2. sp_capture_viewport(mode="render")   最终确认（可选）
3. sp_export_textures(preset, output_dir) 导出贴图
4. 调用 SP2VTF 转换为 Source 引擎格式（可选）
```

## sp_export_textures

触发贴图导出，返回导出的文件路径列表。

| 参数 | 类型 | 说明 |
|------|------|------|
| preset | str | 导出预设名称 |
| output_dir | str | 输出目录绝对路径 |

### 常用 preset

| Preset | 说明 |
|--------|------|
| `"PBR Metallic Roughness"` | 标准 PBR 流程 |
| `"PBR Metallic Roughness (No Alpha)"` | 不含 Alpha 通道 |
| `"PBR SpecGloss"` | SpecGloss 流程 |

### 调用示例

```python
sp_export_textures(
    preset="PBR Metallic Roughness",
    output_dir="E:/export/gun_skin_v1"
)
```

返回：
```json
{"files": ["E:/export/gun_skin_v1/BaseColor.png", "..."]}
```

## SP2VTF 转换

导出完成后，调用 SP2VTF 将 PNG/EXR 转换为 Source 引擎 VTF 格式：

```bash
python sp2vtf/convert.py --input <output_dir> --output <vtf_dir>
```

### 参数

| 参数 | 说明 |
|------|------|
| `--input` | SP 导出目录（包含 BaseColor.png 等） |
| `--output` | VTF 输出目录 |

### 输出文件

转换后生成对应的 `.vtf` 和 `.vmt` 文件，可直接用于 Source 引擎材质。

## 常见错误

| 错误 | 原因 | 解决 |
|------|------|------|
| `"output_dir must not be empty"` | 输出目录为空 | 提供绝对路径 |
| 导出文件为空 | 项目未保存或图层为空 | 先保存项目 |
| SP2VTF 报错 | 输入路径错误 | 确认导出目录存在且包含贴图文件 |
