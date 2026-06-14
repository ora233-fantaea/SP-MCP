---
name: sp-export-pipeline
description: 触发 Substance Painter 贴图导出，包括预设选择、输出路径、
             导出后验证。用户提到导出/输出贴图/export 时触发此 skill。
---

# SP Export Pipeline

Substance Painter 贴图导出完整流程。

## 导出工作流

```
1. sp_save_project()                        保存当前项目
2. sp_capture_viewport(mode="render")       最终渲染确认（可选但推荐）
3. sp_export_textures(preset, output_dir)   执行导出
4. 检查返回的文件列表，确认数量/类型正确
```

## sp_export_textures

触发贴图导出，返回导出的文件路径列表。

| 参数 | 类型 | 说明 |
|------|------|------|
| preset | str | 导出预设名称，必须与 SP 中配置的完全一致 |
| output_dir | str | 输出目录绝对路径 |

### 常用 Preset

| Preset | 输出通道 | 适用场景 |
|--------|---------|---------|
| `"PBR Metallic Roughness"` | BaseColor, Roughness, Metallic, Normal, Height, AO | 标准 PBR 流程（最常用） |
| `"PBR Metallic Roughness (No Alpha)"` | 同上，不含 Alpha | 不需要透明度的场景 |
| `"PBR SpecGloss"` | Diffuse, Specular, Glossiness, Normal | SpecGloss 流程 |
| `"Unreal Engine 4 (Packed)"` | 含 ORM 打包贴图 | UE4/UE5 |
| `"Unity (Standard)"` | 含 MetallicSmoothness 打包贴图 | Unity |

> ⚠️ Preset 名称取决于你在 SP 中的导出模板配置。如果预设名不确定，先用 `sp_run_python` 探索：
> ```python
> import substance_painter.js as js
> js.evaluate('alg.mapexport.presets()')  # 或类似 API
> ```

### 调用示例

```
sp_export_textures(
    preset="PBR Metallic Roughness",
    output_dir="E:/export/gun_skin_v1"
)
```

返回：
```json
{
  "ok": true,
  "preset": "PBR Metallic Roughness",
  "output_dir": "E:/export/gun_skin_v1",
  "files": [
    "E:/export/gun_skin_v1/BaseColor.png",
    "E:/export/gun_skin_v1/Roughness.png",
    "E:/export/gun_skin_v1/Metallic.png",
    "E:/export/gun_skin_v1/Normal.png",
    "E:/export/gun_skin_v1/Height.png",
    "E:/export/gun_skin_v1/AmbientOcclusion.png"
  ]
}
```

## 导出前检查清单

- [ ] 项目已保存（`sp_save_project`）
- [ ] 所有纹理集分辨率正确（`sp_get_texture_sets`）
- [ ] 没有隐藏的关键图层（`sp_get_layer_stack` 确认 visible 状态）
- [ ] `output_dir` 父目录存在（SP 不会自动创建目录）
- [ ] `output_dir` 有足够的磁盘空间
- [ ] 目标文件夹不存在同名文件（会被覆盖）

## 常用输出目录约定

| 项目类型 | 推荐路径 |
|---------|---------|
| 临时测试 | `%TEMP%/sp_export/` |
| 版本迭代 | `E:/export/project_name/v1/`, `v2/`, ... |
| 引擎导入 | `E:/game_project/content/textures/` |

## 导出后验证

```
1. 检查返回的 files 列表是否包含所有预期通道
2. BaseColor.png — 必有
3. Roughness.png — PBR 必有
4. Metallic.png — PBR 必有
5. Normal.png — 必有（OpenGL 或 DirectX 格式取决于项目设置）
6. 文件大小 > 0（用 sp_run_python 的 os.path.getsize 或手动检查）
```

## 批量导出（多纹理集）

如果模型有多个纹理集，每个纹理集都会导出对应的贴图。
SP 的导出预设会自动处理，无需手动切换纹理集。

## 常见错误

| 错误 | 原因 | 解决 |
|------|------|------|
| `"output_dir must not be empty"` | 输出目录参数为空 | 提供绝对路径 |
| `"Preset not found"` | 预设名拼写错误或不存在 | 检查 SP 导出对话框中的预设名 |
| 导出文件为空/0 字节 | 项目未保存或图层为空 | 先 `sp_save_project()` |
| `FileNotFoundError` | 输出目录父路径不存在 | 手动创建目录或换路径 |
| 导出了意外的通道 | 预设配置不同 | 在 SP 中检查导出预设的通道配置 |
| 导出期间 timeout | Iray 渲染阻塞主线程 | 等待渲染完成后再导出 |

## Related Skills

- [sp-project](../sp-project/SKILL.md) — 导出前保存、批量操作
- [sp-camera](../sp-camera/SKILL.md) — Iray 渲染 + 截图确认效果
- [sp-iray](../sp-iray/SKILL.md) — Iray 渲染参数详解与调优
- [sp-texture-set](../sp-texture-set/SKILL.md) — 纹理集分辨率、通道管理