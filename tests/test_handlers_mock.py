"""
test_handlers_mock.py — 测试 plugin/handlers.py 的业务逻辑。

覆盖 Phase 1–7 所有 handler：
- Phase 2: get_layer_stack, add_fill_layer, set_layer_property, get_layer_properties
- Phase 3: capture_viewport (quick/render)
- Phase 4: get_texture_sets, apply_smart_material, add_smart_mask, list_shelf_materials,
           set_iray_params, start_iray_render, check_iray_render
- Phase 6: delete_layer, add_group_layer, add_paint_layer, undo, redo,
           set_layer_channel, get_layer_channels
- Phase 7: duplicate_layer, move_layer, group_layers, ungroup_layer,
           set_active_texture_set, set_texture_set_resolution,
           get_project_info, save_project,
           set_camera, frame_mesh, set_environment
"""

import pytest
from plugin.sp_bridge import handlers  # noqa: E402


# ── Phase 2: get_layer_stack ─────────────────────────────────────────────────

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


# ── Phase 2: add_fill_layer ──────────────────────────────────────────────────

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


# ── Phase 2: set_layer_property ──────────────────────────────────────────────

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


# ── Phase 2: get_layer_properties ────────────────────────────────────────────

class TestGetLayerProperties:
    def test_returns_dict(self, fresh_layer_stack):
        layer_id = handlers.get_layer_stack()[0]["id"]
        props = handlers.get_layer_properties(layer_id)
        assert isinstance(props, dict)
        assert "blending_mode" in props

    def test_invalid_layer_id(self, fresh_layer_stack):
        with pytest.raises(ValueError, match="not found"):
            handlers.get_layer_properties("999999")


# ── Phase 3: capture_viewport ────────────────────────────────────────────────

class TestCaptureViewportQuick:
    def test_returns_image(self, fresh_layer_stack):
        result = handlers.capture_viewport(mode="quick")
        assert "image" in result
        assert "width" in result
        assert "height" in result

    def test_returns_base64(self, fresh_layer_stack):
        import base64
        result = handlers.capture_viewport(mode="quick")
        decoded = base64.b64decode(result["image"])
        assert len(decoded) > 0


class TestCaptureViewportRender:
    def test_returns_mode_render(self):
        result = handlers.capture_viewport(mode="render")
        assert result["mode"] == "render"
        assert "image" in result

    def test_invalid_mode(self):
        with pytest.raises(ValueError, match="Unknown capture mode"):
            handlers.capture_viewport(mode="invalid")


# ── Phase 4: get_texture_sets ────────────────────────────────────────────────

class TestGetTextureSets:
    def test_returns_list(self, fresh_layer_stack):
        result = handlers.get_texture_sets()
        assert isinstance(result, list)

    def test_returns_two_default(self, fresh_layer_stack):
        result = handlers.get_texture_sets()
        assert len(result) == 2

    def test_has_required_fields(self, fresh_layer_stack):
        result = handlers.get_texture_sets()
        for ts in result:
            for key in ("id", "name", "resolution", "layers"):
                assert key in ts

    def test_resolution_format(self, fresh_layer_stack):
        result = handlers.get_texture_sets()
        for ts in result:
            assert "x" in ts["resolution"]

    def test_filter_match(self, fresh_layer_stack):
        result = handlers.get_texture_sets(filter="Metal")
        assert len(result) == 1
        assert result[0]["name"] == "MetalParts"

    def test_filter_no_match(self, fresh_layer_stack):
        result = handlers.get_texture_sets(filter="Nonexistent")
        assert len(result) == 0

    def test_layers_are_trees(self, fresh_layer_stack):
        result = handlers.get_texture_sets()
        for ts in result:
            assert isinstance(ts["layers"], list)


# ── Phase 4: apply_smart_material ────────────────────────────────────────────

class TestApplySmartMaterial:
    def test_returns_id_and_name(self, fresh_layer_stack):
        layer_id = handlers.get_layer_stack()[0]["id"]
        result = handlers.apply_smart_material(layer_id, "Steel")
        assert "id" in result
        assert result["name"] == "Smart_Material"

    def test_invalid_material_name(self, fresh_layer_stack):
        layer_id = handlers.get_layer_stack()[0]["id"]
        with pytest.raises(ValueError, match="not found"):
            handlers.apply_smart_material(layer_id, "NonexistentMaterial")

    def test_invalid_layer_id(self, fresh_layer_stack):
        with pytest.raises(ValueError, match="not found"):
            handlers.apply_smart_material("999999", "Steel")


# ── Phase 4: add_smart_mask ──────────────────────────────────────────────────

class TestAddSmartMask:
    def test_returns_ok(self, fresh_layer_stack):
        layer_id = handlers.get_layer_stack()[0]["id"]
        result = handlers.add_smart_mask(layer_id, "Dirt")
        assert result["ok"] is True
        assert result["effects_count"] == 1

    def test_invalid_mask_name(self, fresh_layer_stack):
        layer_id = handlers.get_layer_stack()[0]["id"]
        with pytest.raises(ValueError, match="not found"):
            handlers.add_smart_mask(layer_id, "NonexistentMask")

    def test_invalid_layer_id(self, fresh_layer_stack):
        with pytest.raises(ValueError, match="not found"):
            handlers.add_smart_mask("999999", "Dirt")


# ── Phase 4: list_shelf_materials ────────────────────────────────────────────

class TestListShelfMaterials:
    def test_returns_list(self, fresh_layer_stack):
        result = handlers.list_shelf_materials()
        assert isinstance(result, list)

    def test_returns_all_when_empty_filter(self, fresh_layer_stack):
        result = handlers.list_shelf_materials(filter="")
        assert len(result) >= 3

    def test_filter_steel(self, fresh_layer_stack):
        result = handlers.list_shelf_materials(filter="Steel")
        assert "Steel" in result

    def test_filter_case_insensitive(self, fresh_layer_stack):
        result = handlers.list_shelf_materials(filter="copper")
        assert "Copper" in result

    def test_filter_no_match(self, fresh_layer_stack):
        result = handlers.list_shelf_materials(filter="Nonexistent")
        assert len(result) == 0


# ── Phase 4: list_materials + apply_material ─────────────────────────────────

class TestListMaterials:
    def test_returns_list(self, fresh_layer_stack):
        result = handlers.list_materials()
        assert isinstance(result, list)

    def test_returns_substance_only(self, fresh_layer_stack):
        result = handlers.list_materials(filter="")
        for name in result:
            assert "Carbon" in name or "Concrete" in name or "Fabric" in name or "Leather" in name or "Metal" in name or "Plastic" in name or "Wood" in name

    def test_filter(self, fresh_layer_stack):
        result = handlers.list_materials(filter="Carbon")
        assert "Carbon Fiber" in result


class TestApplyMaterial:
    def test_returns_ok(self, fresh_layer_stack):
        layer_id = handlers.get_layer_stack()[-1]["id"]
        result = handlers.apply_material(layer_id, "Carbon Fiber")
        assert result["ok"] is True
        assert result["material"] == "Carbon Fiber"

    def test_invalid_material(self, fresh_layer_stack):
        layer_id = handlers.get_layer_stack()[-1]["id"]
        with pytest.raises(ValueError, match="not found"):
            handlers.apply_material(layer_id, "Nonexistent Material")

    def test_invalid_layer(self, fresh_layer_stack):
        with pytest.raises(ValueError, match="not found"):
            handlers.apply_material("999999", "Carbon Fiber")


# ── Phase 4: Iray 渲染参数 ──────────────────────────────────────────────────

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

        ms_container = panel.findChild(QWidget, "maxSamples")
        ms_le = ms_container.findChild(QLineEdit, "value")
        old_val = ms_le.text()

        handlers.set_iray_params(max_samples=200, max_time=45)
        assert ms_le.text() == "200"

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
        il._text = "150/100"

        result = handlers.check_iray_render()
        assert result["iterations"] == "150/100"

        il._text = ""


# ── Phase 4: export_textures ─────────────────────────────────────────────────

class TestExportTextures:
    def test_returns_files_list(self, fresh_layer_stack):
        result = handlers.export_textures(preset="PBR Metallic Roughness",
                                          output_dir="/tmp/export")
        assert "files" in result and len(result["files"]) > 0


# ── Phase 2: dispatch ────────────────────────────────────────────────────────

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


# ── Phase 2: run_python ──────────────────────────────────────────────────────

class TestRunPython:
    def test_stdout_capture(self):
        result = handlers.run_python(code="print('hello sp')")
        assert "hello sp" in result["stdout"]

    def test_syntax_error_raises(self):
        with pytest.raises(SyntaxError):
            handlers.run_python(code="def bad(:")


# ══════════════════════════════════════════════════════════════════════════════
# Phase 6 — 图层基础 + 通道 + Undo
# ══════════════════════════════════════════════════════════════════════════════


# ── Phase 6: delete_layer ────────────────────────────────────────────────────

class TestDeleteLayer:
    def test_delete_root_layer(self, fresh_layer_stack):
        layer_id = handlers.get_layer_stack()[-1]["id"]
        result = handlers.delete_layer(layer_id)
        assert result["ok"] is True
        names = [l["name"] for l in handlers.get_layer_stack()]
        assert "Edge_Wear" not in names

    def test_delete_group_removes_children(self, fresh_layer_stack):
        stack = handlers.get_layer_stack()
        group = [n for n in stack if n["type"] == "GroupLayerNode"][0]
        result = handlers.delete_layer(group["id"])
        assert result["ok"] is True
        remaining = handlers.get_layer_stack()
        assert all(n["type"] != "GroupLayerNode" for n in remaining)

    def test_delete_nonexistent_raises(self, fresh_layer_stack):
        with pytest.raises(ValueError, match="not found"):
            handlers.delete_layer("999999")


# ── Phase 6: add_group_layer ─────────────────────────────────────────────────

class TestAddGroupLayer:
    def test_returns_id_and_name(self, fresh_layer_stack):
        result = handlers.add_group_layer(name="MyGroup")
        assert "id" in result
        assert result["name"] == "MyGroup"

    def test_group_appears_in_stack(self, fresh_layer_stack):
        handlers.add_group_layer(name="NewGroup")
        types = [l["type"] for l in handlers.get_layer_stack()]
        assert "GroupLayerNode" in types

    def test_group_has_no_children(self, fresh_layer_stack):
        handlers.add_group_layer(name="EmptyGroup")
        stack = handlers.get_layer_stack()
        group = [n for n in stack if n["name"] == "EmptyGroup"][0]
        assert group["children"] == []


# ── Phase 6: add_paint_layer ─────────────────────────────────────────────────

class TestAddPaintLayer:
    def test_returns_id_and_name(self, fresh_layer_stack):
        result = handlers.add_paint_layer(name="MyPaint")
        assert "id" in result
        assert result["name"] == "MyPaint"

    def test_paint_layer_type(self, fresh_layer_stack):
        result = handlers.add_paint_layer(name="PaintLayer")
        layer_id = result["id"]
        props = handlers.get_layer_properties(layer_id)
        assert props["type"] == "PaintLayerNode"

    def test_paint_layer_appears_in_stack(self, fresh_layer_stack):
        handlers.add_paint_layer(name="VisiblePaint")
        names = [l["name"] for l in handlers.get_layer_stack()]
        assert "VisiblePaint" in names


# ── Phase 6: undo / redo ─────────────────────────────────────────────────────

class TestUndo:
    def test_nothing_to_undo(self, fresh_layer_stack):
        """Mock QUndoStack canUndo returns False by default."""
        import plugin.sp_bridge.handlers as h
        result = h.undo()
        assert result["ok"] is False
        assert "Nothing to undo" in result["error"]

    def test_undo_add_fill_layer(self, fresh_layer_stack):
        """Mock QUndoStack.undo() is called."""
        import plugin.sp_bridge.handlers as h
        h.add_fill_layer("UndoTest")
        # Manually enable mock undo (real SP tracks layerstack ops automatically)
        from substance_painter.ui import get_main_window
        from PySide2.QtWidgets import QUndoView
        main_win = get_main_window()
        undo_view = main_win.findChild(QUndoView, "history")
        undo_view.stack()._can_undo = True
        result = h.undo()
        assert result["ok"] is True

    def test_undo_set_property(self, fresh_layer_stack):
        import plugin.sp_bridge.handlers as h
        layer_id = h.get_layer_stack()[0]["id"]
        h.set_layer_property(layer_id, "opacity", 0.3)
        from substance_painter.ui import get_main_window
        from PySide2.QtWidgets import QUndoView
        main_win = get_main_window()
        undo_view = main_win.findChild(QUndoView, "history")
        undo_view.stack()._can_undo = True
        result = h.undo()
        assert result["ok"] is True


class TestRedo:
    def test_nothing_to_redo(self, fresh_layer_stack):
        """Mock QUndoStack canRedo returns False by default."""
        import plugin.sp_bridge.handlers as h
        result = h.redo()
        assert result["ok"] is False
        assert "Nothing to redo" in result["error"]

    def test_redo_after_undo(self, fresh_layer_stack):
        """Mock QUndoStack.redo() is called."""
        import plugin.sp_bridge.handlers as h
        h.add_fill_layer("RedoTest")
        from substance_painter.ui import get_main_window
        from PySide2.QtWidgets import QUndoView
        main_win = get_main_window()
        undo_view = main_win.findChild(QUndoView, "history")
        undo_view.stack()._can_redo = True
        result = h.redo()
        assert result["ok"] is True


# ── Phase 6: set_layer_channel ───────────────────────────────────────────────

class TestSetLayerChannel:
    def test_set_roughness(self, fresh_layer_stack):
        layer_id = handlers.get_layer_stack()[-1]["id"]
        result = handlers.set_layer_channel(layer_id, "Roughness", 0.5)
        assert result["ok"] is True

    def test_set_metallic(self, fresh_layer_stack):
        layer_id = handlers.get_layer_stack()[-1]["id"]
        result = handlers.set_layer_channel(layer_id, "Metallic", 0.8)
        assert result["ok"] is True

    def test_set_height(self, fresh_layer_stack):
        layer_id = handlers.get_layer_stack()[-1]["id"]
        result = handlers.set_layer_channel(layer_id, "Height", 0.3)
        assert result["ok"] is True

    def test_set_basecolor(self, fresh_layer_stack):
        layer_id = handlers.get_layer_stack()[-1]["id"]
        result = handlers.set_layer_channel(layer_id, "BaseColor", "#FF0000")
        assert result["ok"] is True

    def test_invalid_channel(self, fresh_layer_stack):
        layer_id = handlers.get_layer_stack()[-1]["id"]
        with pytest.raises(ValueError, match="Unknown channel"):
            handlers.set_layer_channel(layer_id, "InvalidChannel", 0.5)

    def test_nonexistent_layer(self, fresh_layer_stack):
        with pytest.raises(ValueError, match="not found"):
            handlers.set_layer_channel("999999", "Roughness", 0.5)


# ── Phase 6: get_layer_channels ──────────────────────────────────────────────

class TestGetLayerChannels:
    def test_returns_dict(self, fresh_layer_stack):
        layer_id = handlers.get_layer_stack()[-1]["id"]
        result = handlers.get_layer_channels(layer_id)
        assert isinstance(result, dict)

    def test_has_all_channels(self, fresh_layer_stack):
        layer_id = handlers.get_layer_stack()[-1]["id"]
        result = handlers.get_layer_channels(layer_id)
        for ch in ("BaseColor", "Roughness", "Metallic", "Height", "Normal"):
            assert ch in result

    def test_channel_has_fields(self, fresh_layer_stack):
        layer_id = handlers.get_layer_stack()[-1]["id"]
        result = handlers.get_layer_channels(layer_id)
        for ch_name, ch_data in result.items():
            assert "opacity" in ch_data
            assert "blend_mode" in ch_data

    def test_after_set_channel(self, fresh_layer_stack):
        layer_id = handlers.get_layer_stack()[-1]["id"]
        handlers.set_layer_channel(layer_id, "Roughness", 0.75)
        result = handlers.get_layer_channels(layer_id)
        assert result["Roughness"]["source"] == 0.75

    def test_nonexistent_layer(self, fresh_layer_stack):
        with pytest.raises(ValueError, match="not found"):
            handlers.get_layer_channels("999999")


# ══════════════════════════════════════════════════════════════════════════════
# Phase 7 — 图层高级 + TextureSet + 项目 + 相机
# ══════════════════════════════════════════════════════════════════════════════


# ── Phase 7: duplicate_layer ─────────────────────────────────────────────────

class TestDuplicateLayer:
    def test_creates_copy(self, fresh_layer_stack):
        layer_id = handlers.get_layer_stack()[-1]["id"]
        result = handlers.duplicate_layer(layer_id)
        assert "id" in result
        assert result["name"] == "Edge_Wear"

    def test_doubled_count(self, fresh_layer_stack):
        before = len(handlers.get_layer_stack())
        layer_id = handlers.get_layer_stack()[-1]["id"]
        handlers.duplicate_layer(layer_id)
        after = len(handlers.get_layer_stack())
        assert after == before + 1

    def test_nonexistent_layer(self, fresh_layer_stack):
        with pytest.raises(ValueError, match="not found"):
            handlers.duplicate_layer("999999")


# ── Phase 7: move_layer ──────────────────────────────────────────────────────

class TestMoveLayer:
    def test_move_above(self, fresh_layer_stack):
        stack = handlers.get_layer_stack()
        # Move last layer above the first one
        result = handlers.move_layer(stack[-1]["id"], stack[0]["id"], "above")
        assert result["ok"] is True
        new_stack = handlers.get_layer_stack()
        assert new_stack[0]["name"] == stack[-1]["name"]

    def test_move_below(self, fresh_layer_stack):
        stack = handlers.get_layer_stack()
        result = handlers.move_layer(stack[0]["id"], stack[-1]["id"], "below")
        assert result["ok"] is True

    def test_move_to_self(self, fresh_layer_stack):
        stack = handlers.get_layer_stack()
        result = handlers.move_layer(stack[0]["id"], stack[0]["id"], "above")
        assert result["ok"] is True

    def test_invalid_layer(self, fresh_layer_stack):
        with pytest.raises(ValueError):
            handlers.move_layer("999999", "1", "above")


class TestGroupLayers:
    def test_groups_layers(self, fresh_layer_stack):
        stack = handlers.get_layer_stack()
        fill_ids = [n["id"] for n in stack if n["type"] == "FillLayerNode"][:2]
        result = handlers.group_layers(fill_ids)
        assert result["ok"] is True
        assert "Group" in result["name"]

    def test_empty_raises(self, fresh_layer_stack):
        with pytest.raises(ValueError):
            handlers.group_layers(["999999"])


class TestUngroupLayer:
    def test_ungroup_layer(self, fresh_layer_stack):
        stack = handlers.get_layer_stack()
        group = [n for n in stack if n["type"] == "GroupLayerNode"][0]
        original_count = len(stack)
        result = handlers.ungroup_layer(group["id"])
        assert result["ok"] is True

    def test_ungroup_non_group_raises(self, fresh_layer_stack):
        stack = handlers.get_layer_stack()
        fill = [n for n in stack if n["type"] == "FillLayerNode"][0]
        with pytest.raises(ValueError, match="not a group"):
            handlers.ungroup_layer(fill["id"])


# ── Phase 7: set_active_texture_set ──────────────────────────────────────────

class TestSetActiveTextureSet:
    def test_returns_ok(self, fresh_layer_stack):
        result = handlers.set_active_texture_set("MetalParts")
        assert result["ok"] is True

    def test_invalid_name(self, fresh_layer_stack):
        with pytest.raises(ValueError, match="not found"):
            handlers.set_active_texture_set("NonexistentTextureSet")


# ── Phase 7: set_texture_set_resolution ──────────────────────────────────────

class TestSetTextureSetResolution:
    def test_returns_ok(self, fresh_layer_stack):
        result = handlers.set_texture_set_resolution(2048, 2048)
        assert result["ok"] is True

    def test_invalid_dimensions(self, fresh_layer_stack):
        with pytest.raises(ValueError):
            handlers.set_texture_set_resolution(0, 1024)


# ── Phase 7: get_project_info ────────────────────────────────────────────────

class TestGetProjectInfo:
    def test_returns_dict(self, fresh_layer_stack):
        result = handlers.get_project_info()
        assert isinstance(result, dict)
        assert "name" in result
        assert "file_path" in result
        assert "is_open" in result
        assert "is_busy" in result

    def test_project_name(self, fresh_layer_stack):
        result = handlers.get_project_info()
        assert result["name"] == "MockProject"


# ── Phase 7: save_project ────────────────────────────────────────────────────

class TestSaveProject:
    def test_returns_ok(self, fresh_layer_stack):
        result = handlers.save_project()
        assert result["ok"] is True


# ── Phase 7: set_camera ──────────────────────────────────────────────────────

class TestSetCamera:
    def test_returns_ok(self, fresh_layer_stack):
        result = handlers.set_camera(
            x=1.0, y=2.0, z=3.0,
            target_x=0.0, target_y=0.0, target_z=0.0,
            fov=45.0
        )
        assert result["ok"] is True

    def test_sets_position(self, fresh_layer_stack):
        handlers.set_camera(
            x=10.0, y=20.0, z=30.0,
            target_x=0.0, target_y=0.0, target_z=0.0,
            fov=60.0
        )
        import substance_painter.display as display
        cam = display.Camera.get_default_camera()
        assert cam.position == [10.0, 20.0, 30.0]
        assert cam.field_of_view == 60.0


class TestFrameMesh:
    def test_returns_ok(self, fresh_layer_stack):
        result = handlers.frame_mesh()
        assert result["ok"] is True


# ── Phase 7: set_environment ─────────────────────────────────────────────────

class TestSetEnvironment:
    def test_returns_ok(self, fresh_layer_stack):
        result = handlers.set_environment("Sunrise")
        assert result["ok"] is True


# ══════════════════════════════════════════════════════════════════════════════
# Phase 8 — 批量 Undo
# ══════════════════════════════════════════════════════════════════════════════


class TestBeginBatch:
    def test_returns_ok(self, fresh_layer_stack):
        result = handlers.begin_batch("Test Batch")
        assert result["ok"] is True
        assert result["batch_name"] == "Test Batch"
        handlers.end_batch()

    def test_duplicate_begin_raises(self, fresh_layer_stack):
        handlers.begin_batch("First")
        with pytest.raises(RuntimeError, match="already active"):
            handlers.begin_batch("Second")
        handlers.end_batch()

    def test_empty_name_raises(self, fresh_layer_stack):
        with pytest.raises(ValueError, match="name"):
            handlers.begin_batch("")


class TestEndBatch:
    def test_returns_ok(self, fresh_layer_stack):
        handlers.begin_batch("To End")
        result = handlers.end_batch()
        assert result["ok"] is True

    def test_no_batch_raises(self, fresh_layer_stack):
        # 确保没有活跃的 batch
        handlers._batch_scope = None
        with pytest.raises(RuntimeError, match="No active batch"):
            handlers.end_batch()


class TestBatchWorkflow:
    def test_begin_operate_end(self, fresh_layer_stack):
        handlers.begin_batch("Workflow Test")
        handlers.add_fill_layer("Batch_A")
        handlers.add_fill_layer("Batch_B")
        result = handlers.end_batch()
        assert result["ok"] is True
        names = [l["name"] for l in handlers.get_layer_stack()]
        assert "Batch_A" in names
        assert "Batch_B" in names

    def test_batch_scope_active_during_ops(self, fresh_layer_stack):
        handlers.begin_batch("Scope Test")
        assert handlers._batch_scope is not None
        assert handlers._batch_scope._active is True
        handlers.add_fill_layer("ScopeLayer")
        handlers.end_batch()
        assert handlers._batch_scope is None


# ══════════════════════════════════════════════════════════════════════════════
# Phase 9 — JS API 集成
# ══════════════════════════════════════════════════════════════════════════════


class TestBakeMeshMaps:
    def test_returns_ok(self, fresh_layer_stack):
        result = handlers.bake_mesh_maps("Default")
        assert result["ok"] is True

    def test_empty_name_raises(self, fresh_layer_stack):
        with pytest.raises(ValueError, match="must not be empty"):
            handlers.bake_mesh_maps("")


class TestAddTextureSetChannel:
    def test_returns_ok(self, fresh_layer_stack):
        result = handlers.add_texture_set_channel("Default", "custom_ch", "Color4", "Custom Channel")
        assert result["ok"] is True
        assert result["channel"] == "custom_ch"

    def test_empty_ts_name_raises(self, fresh_layer_stack):
        with pytest.raises(ValueError, match="must not be empty"):
            handlers.add_texture_set_channel("", "custom_ch")

    def test_empty_channel_id_raises(self, fresh_layer_stack):
        with pytest.raises(ValueError, match="must not be empty"):
            handlers.add_texture_set_channel("Default", "")


class TestRemoveTextureSetChannel:
    def test_returns_ok(self, fresh_layer_stack):
        result = handlers.remove_texture_set_channel("Default", "custom_ch")
        assert result["ok"] is True
        assert result["channel"] == "custom_ch"

    def test_empty_ts_name_raises(self, fresh_layer_stack):
        with pytest.raises(ValueError, match="must not be empty"):
            handlers.remove_texture_set_channel("", "custom_ch")

    def test_empty_channel_id_raises(self, fresh_layer_stack):
        with pytest.raises(ValueError, match="must not be empty"):
            handlers.remove_texture_set_channel("Default", "")
