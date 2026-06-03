"""
test_handlers_mock.py — 测试 plugin/handlers.py 的业务逻辑。
substance_painter.* 已由 conftest.py 完整 mock。
"""

import pytest
from plugin import handlers  # noqa: E402


# ── get_layer_stack ──────────────────────────────────────────────────────────

class TestGetLayerStack:
    def test_returns_list(self, fresh_layer_stack):
        result = handlers.get_layer_stack()
        assert isinstance(result, list)

    def test_layer_count(self, fresh_layer_stack):
        result = handlers.get_layer_stack()
        # root = [Group(2 children), Fill] → 2 entries
        assert len(result) == 2

    def test_layer_fields(self, fresh_layer_stack):
        layer = handlers.get_layer_stack()[0]
        for key in ("id", "name", "type", "enabled", "opacity"):
            assert key in layer

    def test_layer_type_names(self, fresh_layer_stack):
        types = [l["type"] for l in handlers.get_layer_stack()]
        assert "GroupLayerNode" in types
        assert "FillLayerNode" in types

    def test_group_has_children(self, fresh_layer_stack):
        stack = handlers.get_layer_stack()
        group = [n for n in stack if n["type"] == "GroupLayerNode"][0]
        assert "children" in group
        assert len(group["children"]) == 2

    def test_empty_stack(self, fresh_layer_stack):
        import substance_painter.layerstack as ls
        ls._root_nodes.clear()
        result = handlers.get_layer_stack()
        assert result == []
        ls._build_default_stack()


# ── add_fill_layer ───────────────────────────────────────────────────────────

class TestAddFillLayer:
    def test_returns_id_and_name(self, fresh_layer_stack):
        result = handlers.add_fill_layer(name="Test_Layer")
        assert "id" in result and "name" in result
        assert result["name"] == "Test_Layer"

    def test_layer_appears_in_stack(self, fresh_layer_stack):
        handlers.add_fill_layer(name="New_Fill")
        names = [l["name"] for l in handlers.get_layer_stack()]
        assert "New_Fill" in names

    def test_stack_grows_by_one(self, fresh_layer_stack):
        before = len(handlers.get_layer_stack())
        handlers.add_fill_layer(name="Extra")
        after = len(handlers.get_layer_stack())
        assert after == before + 1

    def test_opacity_param(self, fresh_layer_stack):
        handlers.add_fill_layer(name="Semi", opacity=0.5)

    def test_blend_mode_param(self, fresh_layer_stack):
        result = handlers.add_fill_layer(name="Overlay_Layer", blend_mode="Overlay")
        assert result["name"] == "Overlay_Layer"

    def test_invalid_opacity(self, fresh_layer_stack):
        with pytest.raises(ValueError, match="opacity"):
            handlers.add_fill_layer(name="Bad", opacity=1.5)


# ── set_layer_property ───────────────────────────────────────────────────────

class TestSetLayerProperty:
    def test_set_opacity(self, fresh_layer_stack):
        layer_id = handlers.get_layer_stack()[0]["id"]
        result = handlers.set_layer_property(layer_id, "opacity", 0.42)
        assert result["ok"] is True

    def test_set_enabled_false(self, fresh_layer_stack):
        layer_id = handlers.get_layer_stack()[0]["id"]
        result = handlers.set_layer_property(layer_id, "enabled", False)
        assert result["ok"] is True

    def test_set_name(self, fresh_layer_stack):
        layer_id = handlers.get_layer_stack()[0]["id"]
        handlers.set_layer_property(layer_id, "name", "Renamed")
        names = [l["name"] for l in handlers.get_layer_stack()]
        assert "Renamed" in names

    def test_set_blend_mode(self, fresh_layer_stack):
        layer_id = handlers.get_layer_stack()[0]["id"]
        result = handlers.set_layer_property(layer_id, "blend_mode", "Multiply")
        assert result["ok"] is True

    def test_invalid_blend_mode(self, fresh_layer_stack):
        layer_id = handlers.get_layer_stack()[0]["id"]
        with pytest.raises(ValueError, match="Unknown blend mode"):
            handlers.set_layer_property(layer_id, "blend_mode", "Nope")

    def test_invalid_layer_id(self, fresh_layer_stack):
        with pytest.raises(ValueError, match="not found"):
            handlers.set_layer_property("999999", "opacity", 0.5)

    def test_unsupported_prop(self, fresh_layer_stack):
        layer_id = handlers.get_layer_stack()[0]["id"]
        with pytest.raises(ValueError, match="Unsupported prop"):
            handlers.set_layer_property(layer_id, "nonexistent", 0.5)


# ── get_layer_properties ─────────────────────────────────────────────────────

class TestGetLayerProperties:
    def test_returns_dict(self, fresh_layer_stack):
        layer_id = handlers.get_layer_stack()[0]["id"]
        props = handlers.get_layer_properties(layer_id)
        assert isinstance(props, dict)
        assert "blending_mode" in props

    def test_invalid_layer_id(self, fresh_layer_stack):
        with pytest.raises(ValueError, match="not found"):
            handlers.get_layer_properties("999999")


# ── export_textures ──────────────────────────────────────────────────────────

class TestExportTextures:
    def test_returns_files_list(self, fresh_layer_stack):
        result = handlers.export_textures(preset="PBR Metallic Roughness",
                                          output_dir="/tmp/export")
        assert "files" in result and len(result["files"]) > 0


# ── dispatch ─────────────────────────────────────────────────────────────────

class TestDispatch:
    def test_ping(self):
        result = handlers.dispatch({"method": "ping", "params": {}})
        assert result["status"] == "ok"

    def test_ping_has_smart_api(self):
        result = handlers.dispatch({"method": "ping", "params": {}})
        assert result["smart_api"] is True

    def test_unknown_method(self):
        with pytest.raises(ValueError, match="Unknown method"):
            handlers.dispatch({"method": "nope", "params": {}})

    def test_get_layer_stack_via_dispatch(self, fresh_layer_stack):
        result = handlers.dispatch({"method": "get_layer_stack", "params": {}})
        assert isinstance(result, list)


# ── run_python ───────────────────────────────────────────────────────────────

class TestRunPython:
    def test_stdout_capture(self):
        result = handlers.run_python(code="print('hello sp')")
        assert "hello sp" in result["stdout"]

    def test_syntax_error_raises(self):
        with pytest.raises(SyntaxError):
            handlers.run_python(code="def bad(:")


# ── Iray 渲染参数 ────────────────────────────────────────────────────────────

class TestSetIrayParams:
    def test_sets_max_samples(self):
        result = handlers.set_iray_params(max_samples=50, max_time=30)
        assert result["ok"] is True
        assert result["max_samples"] == 50
        assert result["max_time"] == 30

    def test_sets_width_height(self):
        result = handlers.set_iray_params(max_samples=100, max_time=60,
                                          width=1280, height=720)
        assert result["ok"] is True

    def test_verify_widget_values(self):
        import substance_painter.ui
        from PySide2.QtWidgets import QWidget, QLineEdit, QSpinBox

        win = substance_painter.ui.get_main_window()
        dock = win.findChild(QWidget, "irayParametersView")
        panel = dock.widget()

        # 设置前
        ms_container = panel.findChild(QWidget, "maxSamples")
        ms_le = ms_container.findChild(QLineEdit, "value")
        old_val = ms_le.text()

        # 设置
        handlers.set_iray_params(max_samples=200, max_time=45)

        # 验证
        assert ms_le.text() == "200"

        # 恢复
        ms_le.setText(old_val)


class TestStartIrayRender:
    def test_returns_ok(self):
        result = handlers.start_iray_render()
        assert result["ok"] is True
        assert "queued" in result["message"].lower() or "started" in result["message"].lower()


class TestCheckIrayRender:
    def test_returns_status(self):
        result = handlers.check_iray_render()
        assert "active" in result

    def test_returns_iterations_when_panel_exists(self):
        import substance_painter.ui
        from PySide2.QtWidgets import QWidget

        win = substance_painter.ui.get_main_window()
        dock = win.findChild(QWidget, "irayParametersView")
        panel = dock.widget()
        il = panel.findChild(QWidget, "iterationsLabel")
        il._text = "150/100"  # mock 设置 label 文本

        result = handlers.check_iray_render()
        assert result["iterations"] == "150/100"

        il._text = ""  # 恢复


class TestCaptureViewportRender:
    def test_returns_mode_render(self):
        result = handlers.capture_viewport(mode="render")
        assert result["mode"] == "render"
        assert "image" in result
        assert "width" in result
        assert "height" in result

    def test_invalid_mode(self):
        with pytest.raises(ValueError, match="Unknown capture mode"):
            handlers.capture_viewport(mode="invalid")
