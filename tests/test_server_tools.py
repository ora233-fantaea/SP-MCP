"""
test_server_tools.py

测试 server/sp_mcp.py 的 FastMCP tool 定义层：
- tool 参数校验
- client.py 对 bridge 的 HTTP 封装
- server 对 bridge 错误响应的处理

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
        # 默认返回合理的成功响应
        responses = {
            "ping":            {"status": "ok", "sp_version": "10.0.0", "smart_api": True},
            "get_layer_stack": [
                {"id": "1", "name": "Metal_Base", "type": "FillLayer",  "enabled": True},
                {"id": "2", "name": "Scratches",  "type": "PaintLayer", "enabled": True},
            ],
            "add_fill_layer":       {"id": "99", "name": params.get("name", "")},
            "set_layer_property":   {"ok": True},
            "export_textures":      {"files": ["BaseColor.png", "Roughness.png"]},
            "set_iray_params":      {"ok": True, "max_samples": params.get("max_samples", 100),
                                     "max_time": params.get("max_time", 60)},
            "start_iray_render":    {"ok": True, "message": "Iray render queued"},
            "check_iray_render":    {"active": True, "iterations": "50/100", "time": "00:00:10/00:01:00"},
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
        # name 为空字符串应该被拒绝
        with pytest.raises((ValueError, TypeError)):
            sp_add_fill_layer(name="")

    def test_sp_add_fill_layer_opacity_range(self, mock_bridge):
        from server.sp_mcp import sp_add_fill_layer
        # opacity 超出 0-1 范围
        with pytest.raises(ValueError):
            sp_add_fill_layer(name="Test", opacity=1.5)
        with pytest.raises(ValueError):
            sp_add_fill_layer(name="Test", opacity=-0.1)

    def test_sp_set_layer_property_valid(self, mock_bridge):
        from server.sp_mcp import sp_set_layer_property
        result = sp_set_layer_property(
            layer_id="uid-001", prop="opacity", value=0.5
        )
        assert result["ok"] is True

    def test_sp_set_layer_property_invalid_prop(self, mock_bridge):
        from server.sp_mcp import sp_set_layer_property
        with pytest.raises(ValueError):
            sp_set_layer_property(
                layer_id="uid-001", prop="invalid_prop", value=0.5
            )

    def test_sp_export_textures_requires_output_dir(self, mock_bridge):
        from server.sp_mcp import sp_export_textures
        with pytest.raises((ValueError, TypeError)):
            sp_export_textures(preset="PBR Metallic Roughness", output_dir="")

    def test_sp_export_textures_valid(self, mock_bridge):
        from server.sp_mcp import sp_export_textures
        result = sp_export_textures(
            preset="PBR Metallic Roughness",
            output_dir="/tmp/export"
        )
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
