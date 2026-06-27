"""
test_server_tools.py

测试 server/sp_mcp.py 的 FastMCP tool 定义层：
- tool 参数校验
- client.py 对 bridge 的 HTTP 封装
- server 对 bridge 错误响应的处理
- Phase 6/7 新增 tool 的参数校验

不需要 Painter 运行（bridge 调用全部 mock）。
"""

import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_bridge(monkeypatch):
    """mock server/client.py 的 call() 函数，避免真实 HTTP 请求。"""
    from server import client as sp_client

    def fake_call(method, params=None, **kwargs):
        params = params or {}
        responses = {
            "ping":                    {"status": "ok", "sp_version": "10.0.0", "smart_api": True},
            "get_layer_stack":         [
                {"id": "1", "name": "Metal_Base", "type": "FillLayer",  "enabled": True},
                {"id": "2", "name": "Scratches",  "type": "PaintLayer", "enabled": True},
            ],
            "get_texture_sets":        [
                {"id": "1", "name": "Default", "resolution": "4096x4096", "layers": []},
            ],
            "get_layer_properties":    {"id": "1", "name": "Metal_Base", "type": "FillLayer",
                                        "enabled": True, "opacity": 1.0, "blending_mode": "Normal"},
            "add_fill_layer":          {"id": "99", "name": params.get("name", "")},
            "set_layer_property":      {"ok": True},
            "apply_smart_material":    {"id": "100", "name": "Smart_Material"},
            "add_smart_mask":          {"ok": True, "effects_count": 1},
            "list_shelf_materials":    ["Steel", "Copper", "Gold Armor"],
            "list_materials":          ["Carbon Fiber", "Concrete Raw", "Fabric Felt"],
            "apply_material":          {"ok": True, "material": params.get("material_name", ""), "layer_id": params.get("layer_id", "")},
            "set_iray_params":         {"ok": True, "max_samples": params.get("max_samples", 100),
                                        "max_time": params.get("max_time", 60)},
            "start_iray_render":       {"ok": True, "message": "Iray render queued"},
            "check_iray_render":       {"active": True, "iterations": "50/100", "time": "00:00:10/00:01:00"},
            "capture_viewport":        {"image": "base64data", "width": 800, "height": 600},
            "export_textures":         {"files": ["BaseColor.png", "Roughness.png"]},
            "run_python":              {"stdout": "", "locals": {}},
            # Phase 6
            "delete_layer":            {"ok": True},
            "add_group_layer":         {"id": "200", "name": params.get("name", "New Group")},
            "add_paint_layer":         {"id": "201", "name": params.get("name", "New Paint")},
            "undo":                    {"ok": True},
            "redo":                    {"ok": True},
            "set_layer_channel":       {"ok": True},
            "get_layer_channels":      {"BaseColor": {"opacity": 1.0, "blend_mode": "Normal"},
                                        "Roughness": {"opacity": 1.0, "blend_mode": "Normal", "source": 0.5}},
            # Phase 7
            "duplicate_layer":         {"id": "300", "name": "Copy_Layer"},
            "move_layer":              {"ok": True, "id": "1", "name": "Moved"},
            "group_layers":            {"ok": True, "id": "400", "name": "Group"},
            "ungroup_layer":           {"ok": True},
            "set_active_texture_set":  {"ok": True},
            "set_texture_set_resolution": {"ok": True},
            "get_project_info":        {"name": "MockProject", "file_path": "/mock/project.spp",
                                        "is_open": True, "is_busy": False},
            "save_project":            {"ok": True},
            "set_camera":              {"ok": True},
            "frame_mesh":              {"ok": True},
            "set_environment":         {"ok": True},
            # Phase 8
            "begin_batch":             {"ok": True, "batch_name": params.get("name", "")},
            "end_batch":               {"ok": True},
            "undo":                    {"ok": True, "remaining": 0},
            "redo":                    {"ok": True, "remaining": 0},
            # Phase 9
            "bake_mesh_maps":          {"ok": True, "texture_set": params.get("texture_set_name", "")},
            "add_texture_set_channel": {"ok": True, "channel": params.get("channel_id", "")},
            "remove_texture_set_channel": {"ok": True, "channel": params.get("channel_id", "")},
            # Phase 13: Source Control + Camera/Display
            "get_source_info":           {"layer_id": "1", "node_type": "FillLayerNode",
                                          "source_mode": "Material",
                                          "material_source": {"type": "SourceSubstance",
                                            "resource": {"context": "user", "name": "test_material"}}},
            "get_substance_parameters":  {"layer_id": "1",
                                          "parameters": {"scale": {"value": 1.0},
                                                         "dirt_level": {"value": 0.5}}},
            "set_substance_parameters":  {"ok": True, "layer_id": "1",
                                          "updated": ["scale", "dirt_level"]},
            "get_substance_presets":     {"layer_id": "1",
                                          "presets": ["Default", "Worn", "Polished"]},
            "apply_substance_preset":    {"ok": True, "layer_id": "1", "preset": "Worn"},
            "get_source_outputs":        {"layer_id": "1",
                                          "image_outputs": ["output", "roughness"],
                                          "active_output": "output"},
            "set_source_output":         {"ok": True, "layer_id": "1",
                                          "active_output": "roughness"},
            "get_camera":                {"position": [0.0, 0.0, 5.0],
                                          "rotation": [0.0, 0.0, 0.0],
                                          "field_of_view": 45.0,
                                          "focal_length": 50.0,
                                          "focus_distance": 100.0,
                                          "aperture": 2.8,
                                          "orthographic_height": 10.0,
                                          "projection_type": "Perspective"},
            "get_tone_mapping":          {"tone_mapping": "Linear"},
            "set_tone_mapping":          {"ok": True, "tone_mapping": params.get("function", "ACES")},
            "get_color_lut":             {"color_lut": None},
            "set_color_lut":             {"ok": True, "color_lut": "Mock LUT"},
            "get_scene_bounding_box":    {"dimensions": [10.0, 10.0, 10.0],
                                          "center": [0.0, 0.0, 0.0],
                                          "radius": 8.66},
            # Phase 15: Effect Nodes
            "add_filter_effect":        {"ok": True, "layer_id": "1", "effect_id": "101",
                                         "effect_type": "filter"},
            "add_generator_effect":     {"ok": True, "layer_id": "1", "effect_id": "102",
                                         "effect_type": "generator"},
            "add_levels_effect":        {"ok": True, "layer_id": "1", "effect_id": "103",
                                         "effect_type": "levels"},
            "add_compare_mask_effect":  {"ok": True, "layer_id": "1", "effect_id": "104",
                                         "effect_type": "compare_mask"},
            "add_color_selection_effect": {"ok": True, "layer_id": "1", "effect_id": "105",
                                           "effect_type": "color_selection"},
            "add_anchor_point_effect":  {"ok": True, "layer_id": "1", "effect_id": "106",
                                         "effect_type": "anchor_point"},
            "get_effect_parameters":    {"layer_id": "103", "node_type": "LevelsEffectNode",
                                         "parameters": {"affected_channel": "BaseColor",
                                                        "levels": {"mode": "mono"}}},
            "get_selected_nodes":       {"nodes": [{"id": "1", "name": "Layer", "type": "FillLayerNode"}],
                                         "count": 1},
            "set_selected_nodes":       {"ok": True, "selected": ["1", "2"]},
            # Phase 16: Baking
            "get_baking_parameters":    {"texture_set": "Default", "common": {},
                                         "bakers": {}, "curvature_method": "FromMesh",
                                         "textureset_enabled": True},
            "set_baking_parameters":    {"ok": True, "texture_set": "Default",
                                         "updated_count": 1},
            "bake_texture_set":         {"ok": True, "texture_set": "Default",
                                         "message": "Baking started asynchronously."},
            "get_baking_state":         {"texture_set": "Default",
                                         "textureset_enabled": True,
                                         "curvature_method": "FromMesh",
                                         "enabled_bakers": ["AO", "Normal"]},
            "set_baking_state":         {"ok": True, "texture_set": "Default",
                                         "changed": ["curvature_method=FromNormalMap"]},
            # Phase 17: Project Lifecycle
            "create_project":           {"ok": True, "mesh_file_path": "/mock/mesh.fbx",
                                         "name": "NewProject"},
            "open_project":             {"ok": True, "file_path": "/mock/project.spp",
                                         "name": "OpenedProject"},
            "close_project":            {"ok": True, "message": "Project closed."},
            "reload_mesh":              {"ok": True, "mesh_file_path": "/mock/new_mesh.fbx",
                                         "message": "Mesh reload initiated."},
            "get_project_metadata":     {"context": "test", "key": "version", "value": 42},
            "set_project_metadata":     {"ok": True, "context": "test", "key": "version"},
            "list_project_metadata":    {"context": "test", "keys": ["version", "author"]},
            "list_resources_by_usage":  {"usage": "filter", "search": "",
                                         "resources": ["Blur", "Sharpen"], "count": 2},
        }
        if method not in responses:
            raise ValueError(f"Unknown method in mock: {method}")
        return responses[method]

    monkeypatch.setattr(sp_client, "call", fake_call)
    return fake_call


# ---------------------------------------------------------------------------
# client.py 封装层
# ---------------------------------------------------------------------------

class TestClientCall:
    def test_ping_returns_status_ok(self, mock_bridge):
        from server.client import call
        result = call("ping")
        assert result["status"] == "ok"

    def test_get_layer_stack_returns_list(self, mock_bridge):
        from server.client import call
        result = call("get_layer_stack")
        assert isinstance(result, list)

    def test_add_fill_layer_returns_id(self, mock_bridge):
        from server.client import call
        result = call("add_fill_layer", {"name": "Test"})
        assert "id" in result

    def test_unknown_method_raises(self, mock_bridge):
        from server.client import call
        with pytest.raises(ValueError):
            call("nonexistent_method")


# ---------------------------------------------------------------------------
# MCP tool 参数校验（通过直接调 tool 函数）
# ---------------------------------------------------------------------------

class TestToolParameters:
    def test_sp_add_fill_layer_requires_name(self, mock_bridge):
        from server.sp_mcp import sp_add_fill_layer
        with pytest.raises((ValueError, TypeError)):
            sp_add_fill_layer(name="")

    def test_sp_add_fill_layer_opacity_range(self, mock_bridge):
        from server.sp_mcp import sp_add_fill_layer
        with pytest.raises(ValueError):
            sp_add_fill_layer(name="Test", opacity=1.5)
        with pytest.raises(ValueError):
            sp_add_fill_layer(name="Test", opacity=-0.1)

    def test_sp_set_layer_property_valid(self, mock_bridge):
        from server.sp_mcp import sp_set_layer_property
        result = sp_set_layer_property(layer_id="uid-001", prop="opacity", value=0.5)
        assert result["ok"] is True

    def test_sp_set_layer_property_invalid_prop(self, mock_bridge):
        from server.sp_mcp import sp_set_layer_property
        with pytest.raises(ValueError):
            sp_set_layer_property(layer_id="uid-001", prop="invalid_prop", value=0.5)

    def test_sp_export_textures_requires_output_dir(self, mock_bridge):
        from server.sp_mcp import sp_export_textures
        with pytest.raises((ValueError, TypeError)):
            sp_export_textures(preset="PBR Metallic Roughness", output_dir="")

    def test_sp_export_textures_valid(self, mock_bridge):
        from server.sp_mcp import sp_export_textures
        result = sp_export_textures(preset="PBR Metallic Roughness", output_dir="/tmp/export")
        assert "files" in result

    def test_sp_set_iray_params_valid(self, mock_bridge):
        from server.sp_mcp import sp_set_iray_params
        result = sp_set_iray_params(max_samples=50, max_time=30)
        assert result["ok"] is True
        assert result["max_samples"] == 50

    def test_sp_start_iray_render(self, mock_bridge):
        from server.sp_mcp import sp_start_iray_render
        result = sp_start_iray_render()
        assert result["ok"] is True

    def test_sp_check_iray_render(self, mock_bridge):
        from server.sp_mcp import sp_check_iray_render
        result = sp_check_iray_render()
        assert "active" in result
        assert "iterations" in result

    def test_client_call_with_timeout(self, mock_bridge):
        from server.client import call
        result = call("ping", timeout=30)
        assert result["status"] == "ok"


# ---------------------------------------------------------------------------
# Phase 4: Smart Material tools
# ---------------------------------------------------------------------------

class TestSmartMaterialTools:
    def test_sp_list_shelf_materials(self, mock_bridge):
        from server.sp_mcp import sp_list_shelf_materials
        result = sp_list_shelf_materials(filter="Steel")
        assert isinstance(result, list)

    def test_sp_apply_smart_material(self, mock_bridge):
        from server.sp_mcp import sp_apply_smart_material
        result = sp_apply_smart_material(layer_id="1", material_name="Steel")
        assert "id" in result

    def test_sp_add_smart_mask(self, mock_bridge):
        from server.sp_mcp import sp_add_smart_mask
        result = sp_add_smart_mask(layer_id="1", mask_name="Edge Wear")
        assert result["ok"] is True

    def test_sp_list_materials(self, mock_bridge):
        from server.sp_mcp import sp_list_materials
        result = sp_list_materials(filter="Carbon")
        assert isinstance(result, list)

    def test_sp_apply_material(self, mock_bridge):
        from server.sp_mcp import sp_apply_material
        result = sp_apply_material(layer_id="1", material_name="Carbon Fiber")
        assert result["ok"] is True

    def test_sp_apply_material_requires_layer_id(self, mock_bridge):
        from server.sp_mcp import sp_apply_material
        with pytest.raises((ValueError, TypeError)):
            sp_apply_material(layer_id="", material_name="Carbon Fiber")

    def test_sp_apply_material_requires_name(self, mock_bridge):
        from server.sp_mcp import sp_apply_material
        with pytest.raises((ValueError, TypeError)):
            sp_apply_material(layer_id="1", material_name="")


# ---------------------------------------------------------------------------
# Phase 6: Layer basics + channels + undo
# ---------------------------------------------------------------------------

class TestPhase6Tools:
    def test_sp_delete_layer(self, mock_bridge):
        from server.sp_mcp import sp_delete_layer
        result = sp_delete_layer(layer_id="1")
        assert result["ok"] is True

    def test_sp_add_group_layer(self, mock_bridge):
        from server.sp_mcp import sp_add_group_layer
        result = sp_add_group_layer(name="MyGroup")
        assert "id" in result
        assert result["name"] == "MyGroup"

    def test_sp_add_group_layer_requires_name(self, mock_bridge):
        from server.sp_mcp import sp_add_group_layer
        with pytest.raises((ValueError, TypeError)):
            sp_add_group_layer(name="")

    def test_sp_add_paint_layer(self, mock_bridge):
        from server.sp_mcp import sp_add_paint_layer
        result = sp_add_paint_layer(name="MyPaint")
        assert "id" in result
        assert result["name"] == "MyPaint"

    def test_sp_add_paint_layer_requires_name(self, mock_bridge):
        from server.sp_mcp import sp_add_paint_layer
        with pytest.raises((ValueError, TypeError)):
            sp_add_paint_layer(name="")

    def test_sp_undo(self, mock_bridge):
        from server.sp_mcp import sp_undo
        result = sp_undo()
        # 外置栈为空时返回 ok=False
        assert "ok" in result

    def test_sp_redo(self, mock_bridge):
        from server.sp_mcp import sp_redo
        result = sp_redo()
        # 外置栈为空时返回 ok=False
        assert "ok" in result

    def test_sp_set_layer_channel(self, mock_bridge):
        from server.sp_mcp import sp_set_layer_channel
        result = sp_set_layer_channel(layer_id="1", channel="Roughness", value=0.5)
        assert result["ok"] is True

    def test_sp_set_layer_channel_requires_layer_id(self, mock_bridge):
        from server.sp_mcp import sp_set_layer_channel
        with pytest.raises((ValueError, TypeError)):
            sp_set_layer_channel(layer_id="", channel="Roughness", value=0.5)

    def test_sp_get_layer_channels(self, mock_bridge):
        from server.sp_mcp import sp_get_layer_channels
        result = sp_get_layer_channels(layer_id="1")
        assert isinstance(result, dict)
        assert "BaseColor" in result

    def test_sp_get_layer_channels_requires_layer_id(self, mock_bridge):
        from server.sp_mcp import sp_get_layer_channels
        with pytest.raises((ValueError, TypeError)):
            sp_get_layer_channels(layer_id="")


# ---------------------------------------------------------------------------
# Phase 7: Layer advanced + TextureSet + Project + Camera
# ---------------------------------------------------------------------------

class TestPhase7Tools:
    def test_sp_duplicate_layer(self, mock_bridge):
        from server.sp_mcp import sp_duplicate_layer
        result = sp_duplicate_layer(layer_id="1")
        assert "id" in result

    def test_sp_duplicate_layer_requires_id(self, mock_bridge):
        from server.sp_mcp import sp_duplicate_layer
        with pytest.raises((ValueError, TypeError)):
            sp_duplicate_layer(layer_id="")

    def test_sp_move_layer(self, mock_bridge):
        from server.sp_mcp import sp_move_layer
        result = sp_move_layer(layer_id="1", target_id="2", position="above")
        assert result["ok"] is True

    def test_sp_move_layer_invalid_position(self, mock_bridge):
        from server.sp_mcp import sp_move_layer
        with pytest.raises((ValueError, TypeError)):
            sp_move_layer(layer_id="1", target_id="2", position="invalid")

    def test_sp_group_layers(self, mock_bridge):
        from server.sp_mcp import sp_group_layers
        result = sp_group_layers(layer_ids=["1", "2"])
        assert result["ok"] is True

    def test_sp_group_layers_empty_raises(self, mock_bridge):
        from server.sp_mcp import sp_group_layers
        with pytest.raises((ValueError, TypeError)):
            sp_group_layers(layer_ids=[])

    def test_sp_ungroup_layer(self, mock_bridge):
        from server.sp_mcp import sp_ungroup_layer
        result = sp_ungroup_layer(layer_id="1")
        assert result["ok"] is True

    def test_sp_ungroup_layer_requires_id(self, mock_bridge):
        from server.sp_mcp import sp_ungroup_layer
        with pytest.raises((ValueError, TypeError)):
            sp_ungroup_layer(layer_id="")

    def test_sp_set_active_texture_set(self, mock_bridge):
        from server.sp_mcp import sp_set_active_texture_set
        result = sp_set_active_texture_set(name="Default")
        assert result["ok"] is True

    def test_sp_set_active_texture_set_requires_name(self, mock_bridge):
        from server.sp_mcp import sp_set_active_texture_set
        with pytest.raises((ValueError, TypeError)):
            sp_set_active_texture_set(name="")

    def test_sp_set_texture_set_resolution(self, mock_bridge):
        from server.sp_mcp import sp_set_texture_set_resolution
        result = sp_set_texture_set_resolution(width=2048, height=2048)
        assert result["ok"] is True

    def test_sp_set_texture_set_resolution_invalid(self, mock_bridge):
        from server.sp_mcp import sp_set_texture_set_resolution
        with pytest.raises(ValueError):
            sp_set_texture_set_resolution(width=0, height=1024)

    def test_sp_get_project_info(self, mock_bridge):
        from server.sp_mcp import sp_get_project_info
        result = sp_get_project_info()
        assert "name" in result
        assert result["name"] == "MockProject"

    def test_sp_save_project(self, mock_bridge):
        from server.sp_mcp import sp_save_project
        result = sp_save_project()
        assert result["ok"] is True

    def test_sp_set_camera(self, mock_bridge):
        from server.sp_mcp import sp_set_camera
        result = sp_set_camera(x=1, y=2, z=3, target_x=0, target_y=0, target_z=0, fov=45)
        assert result["ok"] is True

    def test_sp_frame_mesh(self, mock_bridge):
        from server.sp_mcp import sp_frame_mesh
        result = sp_frame_mesh()
        assert result["ok"] is True

    def test_sp_set_environment(self, mock_bridge):
        from server.sp_mcp import sp_set_environment
        result = sp_set_environment(preset="Sunrise")
        assert result["ok"] is True


# ---------------------------------------------------------------------------
# Phase 8: Batch Undo
# ---------------------------------------------------------------------------

class TestPhase8Tools:
    def test_sp_begin_batch(self, mock_bridge):
        from server.sp_mcp import sp_begin_batch
        result = sp_begin_batch(name="TestBatch")
        assert result["ok"] is True

    def test_sp_begin_batch_requires_name(self, mock_bridge):
        from server.sp_mcp import sp_begin_batch
        with pytest.raises((ValueError, TypeError)):
            sp_begin_batch(name="")

    def test_sp_end_batch(self, mock_bridge):
        from server.sp_mcp import sp_end_batch
        result = sp_end_batch()
        assert result["ok"] is True


# ---------------------------------------------------------------------------
# Phase 9: JS API Integration
# ---------------------------------------------------------------------------

class TestPhase9Tools:
    def test_sp_bake_mesh_maps(self, mock_bridge):
        from server.sp_mcp import sp_bake_mesh_maps
        result = sp_bake_mesh_maps(texture_set_name="Default")
        assert result["ok"] is True

    def test_sp_bake_mesh_maps_requires_name(self, mock_bridge):
        from server.sp_mcp import sp_bake_mesh_maps
        with pytest.raises((ValueError, TypeError)):
            sp_bake_mesh_maps(texture_set_name="")

    def test_sp_add_texture_set_channel(self, mock_bridge):
        from server.sp_mcp import sp_add_texture_set_channel
        result = sp_add_texture_set_channel(
            texture_set_name="Default", channel_id="custom_ch",
            channel_format="sRGB8", channel_label="Custom"
        )
        assert result["ok"] is True

    def test_sp_add_texture_set_channel_requires_ts(self, mock_bridge):
        from server.sp_mcp import sp_add_texture_set_channel
        with pytest.raises((ValueError, TypeError)):
            sp_add_texture_set_channel(texture_set_name="", channel_id="ch")

    def test_sp_add_texture_set_channel_requires_ch(self, mock_bridge):
        from server.sp_mcp import sp_add_texture_set_channel
        with pytest.raises((ValueError, TypeError)):
            sp_add_texture_set_channel(texture_set_name="Default", channel_id="")

    def test_sp_remove_texture_set_channel(self, mock_bridge):
        from server.sp_mcp import sp_remove_texture_set_channel
        result = sp_remove_texture_set_channel(
            texture_set_name="Default", channel_id="custom_ch"
        )
        assert result["ok"] is True

    def test_sp_remove_texture_set_channel_requires_ts(self, mock_bridge):
        from server.sp_mcp import sp_remove_texture_set_channel
        with pytest.raises((ValueError, TypeError)):
            sp_remove_texture_set_channel(texture_set_name="", channel_id="ch")

    def test_sp_remove_texture_set_channel_requires_ch(self, mock_bridge):
        from server.sp_mcp import sp_remove_texture_set_channel
        with pytest.raises((ValueError, TypeError)):
            sp_remove_texture_set_channel(texture_set_name="Default", channel_id="")


# ---------------------------------------------------------------------------
# Phase 13: Source Control Tools
# ---------------------------------------------------------------------------

class TestSourceControlTools:
    """sp_get_source_info / sp_get_substance_parameters / sp_set_substance_parameters /
       sp_get_substance_presets / sp_apply_substance_preset / sp_get_source_outputs /
       sp_set_source_output"""

    # ── sp_get_source_info ──

    def test_sp_get_source_info(self, mock_bridge):
        from server.sp_mcp import sp_get_source_info
        result = sp_get_source_info(layer_id="1")
        assert result["layer_id"] == "1"
        assert "source_mode" in result

    def test_sp_get_source_info_with_channel(self, mock_bridge):
        from server.sp_mcp import sp_get_source_info
        result = sp_get_source_info(layer_id="1", channel="BaseColor")
        assert result["layer_id"] == "1"

    def test_sp_get_source_info_empty_id_raises(self, mock_bridge):
        from server.sp_mcp import sp_get_source_info
        with pytest.raises(ValueError, match="layer_id must not be empty"):
            sp_get_source_info(layer_id="")

    # ── sp_get_substance_parameters ──

    def test_sp_get_substance_parameters(self, mock_bridge):
        from server.sp_mcp import sp_get_substance_parameters
        result = sp_get_substance_parameters(layer_id="1")
        assert result["layer_id"] == "1"
        assert "parameters" in result

    def test_sp_get_substance_parameters_requires_layer(self, mock_bridge):
        from server.sp_mcp import sp_get_substance_parameters
        with pytest.raises(ValueError, match="layer_id must not be empty"):
            sp_get_substance_parameters(layer_id="")

    # ── sp_set_substance_parameters ──

    def test_sp_set_substance_parameters(self, mock_bridge):
        from server.sp_mcp import sp_set_substance_parameters
        result = sp_set_substance_parameters(
            layer_id="1", params={"scale": 2.0, "dirt_level": 0.8}
        )
        assert result["ok"] is True

    def test_sp_set_substance_parameters_empty_layer_raises(self, mock_bridge):
        from server.sp_mcp import sp_set_substance_parameters
        with pytest.raises(ValueError, match="layer_id must not be empty"):
            sp_set_substance_parameters(layer_id="", params={"scale": 1.0})

    def test_sp_set_substance_parameters_empty_params_raises(self, mock_bridge):
        from server.sp_mcp import sp_set_substance_parameters
        with pytest.raises(ValueError, match="params must be a non-empty dict"):
            sp_set_substance_parameters(layer_id="1", params={})

    def test_sp_set_substance_parameters_non_dict_raises(self, mock_bridge):
        from server.sp_mcp import sp_set_substance_parameters
        with pytest.raises(ValueError, match="params must be a non-empty dict"):
            sp_set_substance_parameters(layer_id="1", params="not_a_dict")

    # ── sp_get_substance_presets ──

    def test_sp_get_substance_presets(self, mock_bridge):
        from server.sp_mcp import sp_get_substance_presets
        result = sp_get_substance_presets(layer_id="1")
        assert result["layer_id"] == "1"
        assert "presets" in result

    def test_sp_get_substance_presets_empty_layer_raises(self, mock_bridge):
        from server.sp_mcp import sp_get_substance_presets
        with pytest.raises(ValueError, match="layer_id must not be empty"):
            sp_get_substance_presets(layer_id="")

    # ── sp_apply_substance_preset ──

    def test_sp_apply_substance_preset(self, mock_bridge):
        from server.sp_mcp import sp_apply_substance_preset
        result = sp_apply_substance_preset(layer_id="1", preset_name="Worn")
        assert result["ok"] is True
        assert result["preset"] == "Worn"

    def test_sp_apply_substance_preset_empty_layer_raises(self, mock_bridge):
        from server.sp_mcp import sp_apply_substance_preset
        with pytest.raises(ValueError, match="layer_id must not be empty"):
            sp_apply_substance_preset(layer_id="", preset_name="Worn")

    def test_sp_apply_substance_preset_empty_preset_raises(self, mock_bridge):
        from server.sp_mcp import sp_apply_substance_preset
        with pytest.raises(ValueError, match="preset_name must not be empty"):
            sp_apply_substance_preset(layer_id="1", preset_name="")

    # ── sp_get_source_outputs ──

    def test_sp_get_source_outputs(self, mock_bridge):
        from server.sp_mcp import sp_get_source_outputs
        result = sp_get_source_outputs(layer_id="1")
        assert result["layer_id"] == "1"
        assert "image_outputs" in result

    def test_sp_get_source_outputs_empty_layer_raises(self, mock_bridge):
        from server.sp_mcp import sp_get_source_outputs
        with pytest.raises(ValueError, match="layer_id must not be empty"):
            sp_get_source_outputs(layer_id="")

    # ── sp_set_source_output ──

    def test_sp_set_source_output(self, mock_bridge):
        from server.sp_mcp import sp_set_source_output
        result = sp_set_source_output(layer_id="1", output_identifier="roughness")
        assert result["ok"] is True

    def test_sp_set_source_output_empty_layer_raises(self, mock_bridge):
        from server.sp_mcp import sp_set_source_output
        with pytest.raises(ValueError, match="layer_id must not be empty"):
            sp_set_source_output(layer_id="", output_identifier="roughness")

    def test_sp_set_source_output_empty_output_raises(self, mock_bridge):
        from server.sp_mcp import sp_set_source_output
        with pytest.raises(ValueError, match="output_identifier must not be empty"):
            sp_set_source_output(layer_id="1", output_identifier="")


# ---------------------------------------------------------------------------
# Phase 13: Camera / Display Tools
# ---------------------------------------------------------------------------

class TestCameraDisplayTools:
    """sp_get_camera / sp_get_tone_mapping / sp_set_tone_mapping /
       sp_get_color_lut / sp_set_color_lut / sp_get_scene_bounding_box"""

    # ── sp_get_camera ──

    def test_sp_get_camera(self, mock_bridge):
        from server.sp_mcp import sp_get_camera
        result = sp_get_camera()
        expected_keys = {"position", "rotation", "field_of_view", "focal_length",
                         "focus_distance", "aperture", "orthographic_height",
                         "projection_type"}
        assert set(result.keys()) == expected_keys

    def test_sp_get_camera_position_is_list(self, mock_bridge):
        from server.sp_mcp import sp_get_camera
        result = sp_get_camera()
        assert len(result["position"]) == 3
        assert len(result["rotation"]) == 3

    # ── sp_get_tone_mapping ──

    def test_sp_get_tone_mapping(self, mock_bridge):
        from server.sp_mcp import sp_get_tone_mapping
        result = sp_get_tone_mapping()
        assert "tone_mapping" in result

    # ── sp_set_tone_mapping ──

    def test_sp_set_tone_mapping(self, mock_bridge):
        from server.sp_mcp import sp_set_tone_mapping
        result = sp_set_tone_mapping(function="ACES")
        assert result["ok"] is True

    def test_sp_set_tone_mapping_invalid_raises(self, mock_bridge):
        from server.sp_mcp import sp_set_tone_mapping
        with pytest.raises(ValueError, match="must be 'Linear' or 'ACES'"):
            sp_set_tone_mapping(function="InvalidMode")

    # ── sp_get_color_lut ──

    def test_sp_get_color_lut(self, mock_bridge):
        from server.sp_mcp import sp_get_color_lut
        result = sp_get_color_lut()
        assert "color_lut" in result

    # ── sp_set_color_lut ──

    def test_sp_set_color_lut(self, mock_bridge):
        from server.sp_mcp import sp_set_color_lut
        result = sp_set_color_lut(resource_name="sepia")
        assert result["ok"] is True

    # ── sp_get_scene_bounding_box ──

    def test_sp_get_scene_bounding_box(self, mock_bridge):
        from server.sp_mcp import sp_get_scene_bounding_box
        result = sp_get_scene_bounding_box()
        assert set(result.keys()) == {"dimensions", "center", "radius"}
        assert len(result["dimensions"]) == 3
        assert len(result["center"]) == 3


# ---------------------------------------------------------------------------
# Phase 15: Effect Node Tools
# ---------------------------------------------------------------------------

class TestEffectNodeTools:
    """sp_add_filter_effect / sp_add_generator_effect / sp_add_levels_effect /
       sp_add_compare_mask_effect / sp_add_color_selection_effect /
       sp_add_anchor_point_effect / sp_get_effect_parameters /
       sp_get_selected_nodes / sp_set_selected_nodes"""

    def test_sp_add_filter_effect(self, mock_bridge):
        from server.sp_mcp import sp_add_filter_effect
        result = sp_add_filter_effect(layer_id="1")
        assert result["ok"] is True
        assert result["effect_type"] == "filter"

    def test_sp_add_filter_effect_empty_layer_raises(self, mock_bridge):
        from server.sp_mcp import sp_add_filter_effect
        with pytest.raises(ValueError, match="layer_id must not be empty"):
            sp_add_filter_effect(layer_id="")

    def test_sp_add_generator_effect(self, mock_bridge):
        from server.sp_mcp import sp_add_generator_effect
        result = sp_add_generator_effect(layer_id="1")
        assert result["ok"] is True

    def test_sp_add_levels_effect(self, mock_bridge):
        from server.sp_mcp import sp_add_levels_effect
        result = sp_add_levels_effect(layer_id="1")
        assert result["ok"] is True

    def test_sp_add_compare_mask_effect(self, mock_bridge):
        from server.sp_mcp import sp_add_compare_mask_effect
        result = sp_add_compare_mask_effect(layer_id="1")
        assert result["ok"] is True

    def test_sp_add_color_selection_effect(self, mock_bridge):
        from server.sp_mcp import sp_add_color_selection_effect
        result = sp_add_color_selection_effect(layer_id="1")
        assert result["ok"] is True

    def test_sp_add_anchor_point_effect(self, mock_bridge):
        from server.sp_mcp import sp_add_anchor_point_effect
        result = sp_add_anchor_point_effect(layer_id="1", anchor_name="Test")
        assert result["ok"] is True

    def test_sp_get_effect_parameters(self, mock_bridge):
        from server.sp_mcp import sp_get_effect_parameters
        result = sp_get_effect_parameters(layer_id="103")
        assert "node_type" in result

    def test_sp_get_selected_nodes(self, mock_bridge):
        from server.sp_mcp import sp_get_selected_nodes
        result = sp_get_selected_nodes()
        assert "nodes" in result

    def test_sp_set_selected_nodes(self, mock_bridge):
        from server.sp_mcp import sp_set_selected_nodes
        result = sp_set_selected_nodes(node_ids=["1", "2"])
        assert result["ok"] is True

    def test_sp_set_selected_nodes_empty_raises(self, mock_bridge):
        from server.sp_mcp import sp_set_selected_nodes
        with pytest.raises(ValueError, match="node_ids must be a non-empty list"):
            sp_set_selected_nodes(node_ids=[])


# ---------------------------------------------------------------------------
# Phase 16: Baking Tools
# ---------------------------------------------------------------------------

class TestBakingTools:
    """sp_get_baking_parameters / sp_set_baking_parameters / sp_bake_texture_set /
       sp_get_baking_state / sp_set_baking_state"""

    def test_sp_get_baking_parameters(self, mock_bridge):
        from server.sp_mcp import sp_get_baking_parameters
        result = sp_get_baking_parameters(texture_set_name="Default")
        assert result["texture_set"] == "Default"

    def test_sp_get_baking_parameters_empty_ts_raises(self, mock_bridge):
        from server.sp_mcp import sp_get_baking_parameters
        with pytest.raises(ValueError, match="texture_set_name must not be empty"):
            sp_get_baking_parameters(texture_set_name="")

    def test_sp_set_baking_parameters(self, mock_bridge):
        from server.sp_mcp import sp_set_baking_parameters
        result = sp_set_baking_parameters(
            texture_set_name="Default", common_params={"OutputSize": [2048, 2048]}
        )
        assert result["ok"] is True

    def test_sp_bake_texture_set(self, mock_bridge):
        from server.sp_mcp import sp_bake_texture_set
        result = sp_bake_texture_set(texture_set_name="Default")
        assert result["ok"] is True

    def test_sp_get_baking_state(self, mock_bridge):
        from server.sp_mcp import sp_get_baking_state
        result = sp_get_baking_state(texture_set_name="Default")
        assert "enabled_bakers" in result

    def test_sp_set_baking_state(self, mock_bridge):
        from server.sp_mcp import sp_set_baking_state
        result = sp_set_baking_state(
            texture_set_name="Default", curvature_method="FromNormalMap"
        )
        assert result["ok"] is True


# ---------------------------------------------------------------------------
# Phase 17: Project Lifecycle Tools
# ---------------------------------------------------------------------------

class TestProjectLifecycleTools:
    """sp_create_project / sp_open_project / sp_close_project / sp_reload_mesh /
       sp_get_project_metadata / sp_set_project_metadata / sp_list_project_metadata"""

    def test_sp_create_project(self, mock_bridge):
        from server.sp_mcp import sp_create_project
        result = sp_create_project(mesh_file_path="/mock/mesh.fbx")
        assert result["ok"] is True

    def test_sp_create_project_empty_mesh_raises(self, mock_bridge):
        from server.sp_mcp import sp_create_project
        with pytest.raises(ValueError, match="mesh_file_path must not be empty"):
            sp_create_project(mesh_file_path="")

    def test_sp_open_project(self, mock_bridge):
        from server.sp_mcp import sp_open_project
        result = sp_open_project(file_path="/mock/project.spp")
        assert result["ok"] is True

    def test_sp_open_project_empty_raises(self, mock_bridge):
        from server.sp_mcp import sp_open_project
        with pytest.raises(ValueError, match="file_path must not be empty"):
            sp_open_project(file_path="")

    def test_sp_close_project(self, mock_bridge):
        from server.sp_mcp import sp_close_project
        result = sp_close_project()
        assert result["ok"] is True

    def test_sp_reload_mesh(self, mock_bridge):
        from server.sp_mcp import sp_reload_mesh
        result = sp_reload_mesh(mesh_file_path="/mock/new_mesh.fbx")
        assert result["ok"] is True

    def test_sp_get_project_metadata(self, mock_bridge):
        from server.sp_mcp import sp_get_project_metadata
        result = sp_get_project_metadata(context="test", key="version")
        assert "value" in result

    def test_sp_set_project_metadata(self, mock_bridge):
        from server.sp_mcp import sp_set_project_metadata
        result = sp_set_project_metadata(context="test", key="k", value="v")
        assert result["ok"] is True

    def test_sp_list_project_metadata(self, mock_bridge):
        from server.sp_mcp import sp_list_project_metadata
        result = sp_list_project_metadata(context="test")
        assert "keys" in result


# ---------------------------------------------------------------------------
# Phase 17b: Resource Tools
# ---------------------------------------------------------------------------

class TestResourceUsageTools:
    """sp_list_resources_by_usage"""

    def test_sp_list_resources_by_usage(self, mock_bridge):
        from server.sp_mcp import sp_list_resources_by_usage
        result = sp_list_resources_by_usage(usage="filter")
        assert result["usage"] == "filter"
        assert isinstance(result["resources"], list)

    def test_sp_list_resources_by_usage_empty_raises(self, mock_bridge):
        from server.sp_mcp import sp_list_resources_by_usage
        with pytest.raises(ValueError, match="usage must not be empty"):
            sp_list_resources_by_usage(usage="")


# ---------------------------------------------------------------------------
# Bridge 错误响应处理
# ---------------------------------------------------------------------------

class TestBridgeErrorHandling:
    def test_bridge_timeout_raises(self, monkeypatch):
        from server import client as sp_client
        import requests

        def fake_post(*args, **kwargs):
            raise requests.exceptions.Timeout()

        monkeypatch.setattr(requests, "post", fake_post)
        with pytest.raises(ConnectionError, match="timeout"):
            sp_client.call("ping")

    def test_bridge_connection_refused_raises(self, monkeypatch):
        from server import client as sp_client
        import requests

        def fake_post(*args, **kwargs):
            raise requests.exceptions.ConnectionError()

        monkeypatch.setattr(requests, "post", fake_post)
        with pytest.raises(ConnectionError, match="not reachable"):
            sp_client.call("ping")

    def test_bridge_error_response_raises(self, monkeypatch):
        from server import client as sp_client
        import requests

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": False, "error": "Layer not found"}
        mock_resp.status_code = 500

        monkeypatch.setattr(requests, "post", lambda *a, **kw: mock_resp)
        with pytest.raises(RuntimeError, match="Layer not found"):
            sp_client.call("set_layer_property",
                           {"layer_id": "bad-id", "prop": "opacity", "value": 0.5})


# ---------------------------------------------------------------------------
# Integration — 需要 Painter 运行
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestIntegration:
    def test_real_ping(self, bridge_url):
        import requests
        r = requests.post(
            bridge_url,
            json={"method": "ping", "params": {}},
            timeout=5
        )
        assert r.status_code == 200
        assert r.json()["ok"] is True
        assert r.json()["result"]["status"] == "ok"

    def test_real_get_layer_stack(self, bridge_url):
        import requests
        r = requests.post(
            bridge_url,
            json={"method": "get_layer_stack", "params": {}},
            timeout=5
        )
        assert r.status_code == 200
        result = r.json()["result"]
        assert isinstance(result, list)

    def test_real_roundtrip_add_and_get(self, bridge_url):
        """新建图层后能在图层栈里找到它。"""
        import requests

        requests.post(bridge_url, json={
            "method": "add_fill_layer",
            "params": {"name": "Test_Roundtrip", "opacity": 0.5}
        }, timeout=5)

        r = requests.post(bridge_url, json={
            "method": "get_layer_stack", "params": {}
        }, timeout=5)
        names = [l["name"] for l in r.json()["result"]]
        assert "Test_Roundtrip" in names
