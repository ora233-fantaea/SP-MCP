"""
test_bugfix_regression.py — 针对 9 个已修复 bug 的回归守卫。

每个测试类对应一个 bug，类 docstring 记录修复前的错误行为，
确保这些问题不会再次回归。涵盖：
  #1 图层搬运（move/group/ungroup/duplicate）静默丢失 mask/effect/笔触
  #2 list_resources_by_usage 因 Type/Usage 枚举混用恒返回空
  #3 capture_viewport(mode="render") 不触发 Iray，返回值需诚实告知
  #4 window_grab 区域截图忽略 x 偏移、宽度错位
  #5 长操作可申请更长 bridge 等待，避免误报超时后重复执行
  #6 add_texture_set_channel 两层默认格式一致且合法
  #7 set_color_lut docstring 引用了不存在的工具名
  #8 set_layer_property 的 "enabled" 属性在 MCP 层可达
  #9 set_camera 用 None 语义、支持对准世界原点
"""

import pytest
from plugin.sp_bridge import handlers


# ══════════════════════════════════════════════════════════════════════════════
# #1 — 图层搬运静默丢失 mask / effect / 笔触
#
# 修复前：_clone_node 只复制 5 个 PBR 通道，mask/effect/paint 笔触被静默丢弃，
#         move/group/ungroup/duplicate 返回 {"ok": True} 却丢了数据。
# 修复后：尽力复制 mask 背景，无法克隆的内容追加到返回值的 "warnings" 列表。
# ══════════════════════════════════════════════════════════════════════════════

import substance_painter.layerstack as ls


class TestCloneWarnsOnLossyCopy:
    def test_duplicate_plain_layer_no_warnings(self, fresh_layer_stack):
        """无 mask/effect 的普通填充层复制不应产生告警。"""
        r = handlers.add_fill_layer("Plain")
        result = handlers.duplicate_layer(r["id"])
        assert "warnings" not in result or result["warnings"] == []

    def test_duplicate_layer_with_mask_effects_warns(self, fresh_layer_stack):
        """带 mask effect 的层复制时必须在 warnings 中告知未拷贝。"""
        r = handlers.add_fill_layer("Masked")
        node = ls.get_node_by_uid(int(r["id"]))
        node.add_mask(ls.MaskBackground.White)
        node._mask_effects = ["smart_mask_edge_wear"]   # 模拟一个 mask 效果

        result = handlers.duplicate_layer(r["id"])
        assert "warnings" in result
        assert any("mask effect" in w for w in result["warnings"])

    def test_duplicate_copies_mask_background(self, fresh_layer_stack):
        """遮罩背景应被复制到新节点。"""
        r = handlers.add_fill_layer("MaskBg")
        node = ls.get_node_by_uid(int(r["id"]))
        node.add_mask(ls.MaskBackground.White)

        before = len(handlers.get_layer_stack())
        new = handlers.duplicate_layer(r["id"])
        after = len(handlers.get_layer_stack())
        assert after == before + 1
        new_node = ls.get_node_by_uid(int(new["id"]))
        assert new_node.has_mask() is True

    def test_duplicate_layer_with_content_effect_warns(self, fresh_layer_stack):
        """带 content effect 的层复制时必须告警。"""
        r = handlers.add_fill_layer("WithFilter")
        node = ls.get_node_by_uid(int(r["id"]))
        node._content_effects = ["blur_filter"]

        result = handlers.duplicate_layer(r["id"])
        assert "warnings" in result
        assert any("content effect" in w for w in result["warnings"])

    def test_paint_layer_duplicate_warns_strokes(self, fresh_layer_stack):
        """paint 层复制时必须告知笔触未拷贝。"""
        r = handlers.add_paint_layer("PaintLossy")
        result = handlers.duplicate_layer(r["id"])
        assert "warnings" in result
        assert any("paint strokes" in w for w in result["warnings"])

    def test_move_layer_propagates_warnings(self, fresh_layer_stack):
        """move_layer 也应回传 warnings。"""
        stack = handlers.get_layer_stack()
        src_id = stack[-1]["id"]
        node = ls.get_node_by_uid(int(src_id))
        node._content_effects = ["levels"]
        result = handlers.move_layer(src_id, stack[0]["id"], "above")
        assert "warnings" in result

    def test_group_layers_propagates_warnings(self, fresh_layer_stack):
        """group_layers 也应回传 warnings。"""
        stack = handlers.get_layer_stack()
        fills = [n["id"] for n in stack if n["type"] == "FillLayerNode"][:1]
        node = ls.get_node_by_uid(int(fills[0]))
        node._content_effects = ["generator"]
        result = handlers.group_layers(fills)
        assert "warnings" in result

    def test_ungroup_layer_propagates_warnings(self, fresh_layer_stack):
        """ungroup_layer 也应回传子层的 warnings。"""
        stack = handlers.get_layer_stack()
        group = [n for n in stack if n["type"] == "GroupLayerNode"][0]
        gnode = ls.get_node_by_uid(int(group["id"]))
        # 给第一个子层加一个 content effect
        gnode.sub_layers()[0]._content_effects = ["filter"]
        result = handlers.ungroup_layer(group["id"])
        assert "warnings" in result


# ══════════════════════════════════════════════════════════════════════════════
# #2 — list_resources_by_usage 恒空
#
# 修复前：用 res.type()(Type 枚举) 比较 r.Usage.*(Usage 枚举)，永不相等。
# 修复后：用 r.Type.* 比较，能正确按类型筛选。
# ══════════════════════════════════════════════════════════════════════════════

class TestListResourcesByUsage:
    def test_filter_returns_results(self, fresh_layer_stack):
        """filter 类型应返回结果（修复前恒为空）。"""
        result = handlers.list_resources_by_usage("smart_material")
        assert result["count"] > 0
        assert isinstance(result["resources"], list)

    def test_smart_mask_returns_results(self, fresh_layer_stack):
        result = handlers.list_resources_by_usage("smart_mask")
        assert result["count"] > 0

    def test_substance_returns_results(self, fresh_layer_stack):
        result = handlers.list_resources_by_usage("substance")
        assert result["count"] > 0

    def test_environment_returns_results(self, fresh_layer_stack):
        result = handlers.list_resources_by_usage("environment")
        assert result["count"] > 0

    def test_unknown_usage_raises(self, fresh_layer_stack):
        with pytest.raises(ValueError, match="Unknown usage"):
            handlers.list_resources_by_usage("nonexistent")

    def test_search_filters_results(self, fresh_layer_stack):
        """带 search 关键词应进一步缩小结果。"""
        result = handlers.list_resources_by_usage("smart_material", search="Steel")
        assert "Steel" in result["resources"]
        assert all("steel" in r.lower() for r in result["resources"])


# ══════════════════════════════════════════════════════════════════════════════
# #3 — capture_viewport(mode="render") 不触发 Iray
#
# 修复前：docstring 称 "Iray 离线渲染"，实际只做 Qt grab，误导模型。
# 修复后：返回值带 "note" 字段诚实说明不触发 Iray。
# ══════════════════════════════════════════════════════════════════════════════

class TestCaptureRenderHonesty:
    def test_render_mode_has_note(self, fresh_layer_stack):
        result = handlers.capture_viewport(mode="render")
        assert result["mode"] == "render"
        assert "note" in result
        assert "Iray" in result["note"]

    def test_quick_mode_has_no_note(self, fresh_layer_stack):
        """quick 模式不应携带 render 专属的 note。"""
        result = handlers.capture_viewport(mode="quick")
        assert "note" not in result


# ══════════════════════════════════════════════════════════════════════════════
# #4 — window_grab 区域截图
#
# 修复前：x 偏移算出却未用；GetDIBits 按 region 宽度解全宽位图导致错位。
# 修复后：先抓全窗口再用 QImage.copy 在像素空间裁剪，尺寸正确且夹取边界。
# ══════════════════════════════════════════════════════════════════════════════

class TestWindowGrabRegion:
    def test_full_grab(self, fresh_layer_stack):
        result = handlers.window_grab()
        assert result["width"] > 0 and result["height"] > 0
        assert len(result["image"]) > 0

    def test_region_grab_dimensions(self, fresh_layer_stack):
        result = handlers.window_grab({"x": 10, "y": 20, "width": 400, "height": 300})
        assert result["width"] == 400
        assert result["height"] == 300

    def test_region_clamped_to_window(self, fresh_layer_stack):
        """超出窗口的区域应被夹取，不会越界。"""
        result = handlers.window_grab({"x": 0, "y": 0,
                                       "width": 99999, "height": 99999})
        # 窗口 mock 为 1920x1080；裁剪后不得超过窗口尺寸
        assert result["width"] <= 1920
        assert result["height"] <= 1080

    def test_region_offset_beyond_window_clamped(self, fresh_layer_stack):
        """x/y 偏移超出窗口时夹到边界内，仍返回合法尺寸（≥1，不越界）。"""
        result = handlers.window_grab({"x": 99999, "y": 99999,
                                       "width": 100, "height": 100})
        assert 1 <= result["width"] <= 1920
        assert 1 <= result["height"] <= 1080


# ══════════════════════════════════════════════════════════════════════════════
# #5 — 长操作超时与重复执行风险
#
# 修复前：bridge 固定 60s，长操作超时即报错但任务仍在跑，可能被重复触发。
# 修复后：client 可传 timeout 给 bridge 放宽等待；export/open/create 用 300s。
# ══════════════════════════════════════════════════════════════════════════════

class TestLongOperationTimeout:
    def test_client_passes_timeout_to_bridge(self, monkeypatch):
        """client.call(timeout=...) 应把 timeout 写进请求体，并放宽 HTTP 读超时。"""
        from server import client as sp_client
        captured = {}

        class _Resp:
            status_code = 200
            def json(self):
                return {"ok": True, "result": {"files": []}}

        def fake_post(url, json=None, timeout=None):
            captured["body"] = json
            captured["http_timeout"] = timeout
            return _Resp()

        import requests
        monkeypatch.setattr(requests, "post", fake_post)
        sp_client.call("export_textures", {"preset": "p", "output_dir": "/x"},
                       timeout=300.0)
        assert captured["body"]["timeout"] == 300.0
        # HTTP 读超时应比 bridge 等待多留余量
        assert captured["http_timeout"] > 300.0

    def test_export_textures_uses_long_timeout(self, monkeypatch):
        """sp_export_textures 应用更长超时调用 bridge。"""
        from server import client as sp_client
        captured = {}

        def fake_call(method, params=None, timeout=None):
            captured["method"] = method
            captured["timeout"] = timeout
            return {"files": []}

        monkeypatch.setattr(sp_client, "call", fake_call)
        from server.sp_mcp import sp_export_textures
        sp_export_textures(preset="PBR", output_dir="/tmp/x")
        assert captured["timeout"] is not None
        assert captured["timeout"] >= 300.0

    def test_open_project_uses_long_timeout(self, monkeypatch):
        from server import client as sp_client
        captured = {}

        def fake_call(method, params=None, timeout=None):
            captured["timeout"] = timeout
            return {"ok": True}

        monkeypatch.setattr(sp_client, "call", fake_call)
        from server.sp_mcp import sp_open_project
        sp_open_project(file_path="/x.spp")
        assert captured["timeout"] is not None and captured["timeout"] >= 300.0

    def test_create_project_uses_long_timeout(self, monkeypatch):
        from server import client as sp_client
        captured = {}

        def fake_call(method, params=None, timeout=None):
            captured["timeout"] = timeout
            return {"ok": True}

        monkeypatch.setattr(sp_client, "call", fake_call)
        from server.sp_mcp import sp_create_project
        sp_create_project(mesh_file_path="/m.fbx")
        assert captured["timeout"] is not None and captured["timeout"] >= 300.0


class TestBridgeTimeoutResolution:
    """bridge _resolve_wait_timeout 的解析/夹取与对畸形输入的健壮性。"""

    def _handler_cls(self):
        from plugin.sp_bridge import bridge
        return bridge._RpcHandler

    def test_none_uses_default(self):
        h = self._handler_cls()
        assert h._resolve_wait_timeout(None) == h.TIMEOUT

    def test_clamped_to_floor(self):
        """低于默认值的请求被抬到 TIMEOUT（不会低于 bridge/client 契约下限）。"""
        h = self._handler_cls()
        assert h._resolve_wait_timeout(5) == h.TIMEOUT

    def test_clamped_to_ceiling(self):
        h = self._handler_cls()
        assert h._resolve_wait_timeout(99999) == h.MAX_TIMEOUT

    def test_valid_passthrough(self):
        h = self._handler_cls()
        assert h._resolve_wait_timeout(300.0) == 300.0

    def test_non_numeric_falls_back(self):
        """字符串/列表等非数值不应抛错，回退默认值。"""
        h = self._handler_cls()
        assert h._resolve_wait_timeout("not_a_number") == h.TIMEOUT
        assert h._resolve_wait_timeout([1, 2]) == h.TIMEOUT

    def test_nan_infinity_fall_back(self):
        """NaN/Infinity 会让 min/max 失效、done.wait 行为未定义，必须回退。"""
        h = self._handler_cls()
        assert h._resolve_wait_timeout(float("nan")) == h.TIMEOUT
        assert h._resolve_wait_timeout(float("inf")) == h.TIMEOUT



# ══════════════════════════════════════════════════════════════════════════════
# #6 — add_texture_set_channel 默认格式一致且合法
#
# 修复前：MCP 层默认 "Color4"，handler 层默认 "RGB16F"，且 "Color4" 非合法格式。
# 修复后：两层默认统一为合法值 "sRGB8"。
# ══════════════════════════════════════════════════════════════════════════════

class TestChannelFormatDefault:
    def test_mcp_and_handler_defaults_match(self):
        import inspect
        from server.sp_mcp import sp_add_texture_set_channel
        mcp_default = inspect.signature(
            sp_add_texture_set_channel).parameters["channel_format"].default
        handler_default = inspect.signature(
            handlers.add_texture_set_channel).parameters["channel_format"].default
        assert mcp_default == handler_default

    def test_default_is_valid_format(self):
        import inspect
        from server.sp_mcp import sp_add_texture_set_channel
        default = inspect.signature(
            sp_add_texture_set_channel).parameters["channel_format"].default
        # 合法的 alg 格式集合（不含已废弃的 "Color4"）
        assert default in {"sRGB8", "L8", "RGB8", "RGB16", "RGB16F", "RGB32F"}


# ══════════════════════════════════════════════════════════════════════════════
# #7 — set_color_lut docstring 引用了不存在的工具
#
# 修复前：docstring 写 "用 sp_list_all_resources"，该工具不存在。
# 修复后：改为存在的 sp_list_resources_by_usage。
# ══════════════════════════════════════════════════════════════════════════════

class TestSetColorLutDocstring:
    def test_docstring_references_valid_tool(self):
        from server.sp_mcp import sp_set_color_lut
        doc = sp_set_color_lut.__doc__ or ""
        assert "sp_list_all_resources" not in doc
        assert "sp_list_resources_by_usage" in doc


# ══════════════════════════════════════════════════════════════════════════════
# #8 — set_layer_property 的 "enabled" 属性
#
# 修复前：handler 支持 "enabled"，但 MCP 层 _VALID_PROPS 不含，调用被拒。
# 修复后：MCP 层接受 "enabled"（visible 别名）。
# ══════════════════════════════════════════════════════════════════════════════

class TestSetLayerPropertyEnabled:
    def test_mcp_accepts_enabled(self, monkeypatch):
        from server import client as sp_client
        monkeypatch.setattr(sp_client, "call",
                            lambda m, p=None, **k: {"ok": True})
        from server.sp_mcp import sp_set_layer_property
        result = sp_set_layer_property(layer_id="1", prop="enabled", value=False)
        assert result["ok"] is True

    def test_handler_enabled_toggles_visibility(self, fresh_layer_stack):
        layer_id = handlers.get_layer_stack()[0]["id"]
        handlers.set_layer_property(layer_id, "enabled", False)
        node = ls.get_node_by_uid(int(layer_id))
        assert node.is_visible() is False


# ══════════════════════════════════════════════════════════════════════════════
# #9 — set_camera None 语义与对准原点
#
# 修复前："非零才覆盖" 注释与 is_not_None 实现不符；对准 (0,0,0) 时朝向不更新。
# 修复后：仅显式提供的参数才覆盖；三个 target 分量齐全才更新朝向，支持原点。
# ══════════════════════════════════════════════════════════════════════════════

import substance_painter.display as display


class TestSetCamera:
    def test_partial_update_keeps_other_axes(self, fresh_layer_stack):
        """只传 x 时，y/z 应保持当前值不变。"""
        cam = display.Camera.get_default_camera()
        cam.position = [1.0, 2.0, 3.0]
        handlers.set_camera(x=10.0)
        assert cam.position == [10.0, 2.0, 3.0]

    def test_fov_not_modified_when_omitted(self, fresh_layer_stack):
        cam = display.Camera.get_default_camera()
        cam.field_of_view = 33.0
        handlers.set_camera(x=1.0)
        assert cam.field_of_view == 33.0

    def test_target_origin_updates_rotation(self, fresh_layer_stack):
        """对准世界原点 (0,0,0) 时朝向应更新（修复前被跳过）。"""
        cam = display.Camera.get_default_camera()
        cam.position = [0.0, 0.0, 0.0]
        cam.rotation = [11.0, 22.0, 33.0]
        handlers.set_camera(x=0.0, y=0.0, z=5.0,
                            target_x=0.0, target_y=0.0, target_z=0.0)
        # 从 (0,0,5) 看向原点，朝向应改变（不再是初始的 11,22）
        assert cam.rotation[:2] != [11.0, 22.0]

    def test_target_ignored_when_incomplete(self, fresh_layer_stack):
        """target 分量不齐全时不更新朝向。"""
        cam = display.Camera.get_default_camera()
        cam.rotation = [5.0, 6.0, 7.0]
        handlers.set_camera(x=1.0, target_x=1.0)  # 缺 target_y/z
        assert cam.rotation == [5.0, 6.0, 7.0]

    def test_returns_ok(self, fresh_layer_stack):
        result = handlers.set_camera(x=1.0, y=2.0, z=3.0)
        assert result["ok"] is True
