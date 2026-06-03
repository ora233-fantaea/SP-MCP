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
            "undo":                    {"ok": True, "undoable": True},
            "redo":                    {"ok": True, "redoable": True},
            "set_layer_channel":       {"ok": True},
            "get_layer_channels":      {"BaseColor": {"opacity": 1.0, "blend_mode": "Normal"},
                                        "Roughness": {"opacity": 1.0, "blend_mode": "Normal", "source": 0.5}},
            # Phase 7
            "duplicate_layer":         {"id": "300", "name": "Copy_Layer"},
            "move_layer":              {"ok": True},
            "group_layers":            {"id": "400", "name": "New Group"},
            "ungroup_layer":           {"ok": True},
            "set_active_texture_set":  {"ok": True},
            "set_texture_set_resolution": {"ok": True},
            "get_project_info":        {"name": "MockProject", "file_path": "/mock/project.spp",
                                        "color_space": "sRGB"},
            "save_project":            {"ok": True},
            "set_camera":              {"ok": True},
            "frame_mesh":              {"ok": True},
            "set_environment":         {"ok": True},
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
        assert result["ok"] is True

    def test_sp_redo(self, mock_bridge):
        from server.sp_mcp import sp_redo
        result = sp_redo()
        assert result["ok"] is True

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
        with pytest.raises(ValueError):
            sp_move_layer(layer_id="1", target_id="2", position="invalid")

    def test_sp_group_layers(self, mock_bridge):
        from server.sp_mcp import sp_group_layers
        result = sp_group_layers(layer_ids=["1", "2"])
        assert "id" in result

    def test_sp_group_layers_empty_raises(self, mock_bridge):
        from server.sp_mcp import sp_group_layers
        with pytest.raises(ValueError):
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
