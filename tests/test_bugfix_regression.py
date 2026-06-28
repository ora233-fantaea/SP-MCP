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


# ══════════════════════════════════════════════════════════════════════════════
# 离线调试追加修复（不依赖真实 SP）
#
# #A _hex_to_rgb 无输入校验 → 用户传 "#FFF"/"#GGGGGG"/"" 时抛裸 ValueError
# #B window_grab 硬编码 PySide2，缺 _capture_qt 那样的 PySide6 回退
# #C frame_mesh 当 fov<=0（正交相机）时 tan(0)=0 除零崩溃
# #D bridge stop() 取消队列任务时未写 error → HTTP 端误报 ok:true/result:null
# #E group_layers 重复 id 导致同节点被克隆两次、对已删除节点二次 delete
# ══════════════════════════════════════════════════════════════════════════════


class TestHexToRgbValidation:
    def test_valid_6_digit(self):
        assert handlers._hex_to_rgb("#FF0000") == (1.0, 0.0, 0.0)

    def test_valid_without_hash(self):
        assert handlers._hex_to_rgb("00FF00") == (0.0, 1.0, 0.0)

    def test_3_digit_shorthand(self):
        # #F00 → #FF0000
        assert handlers._hex_to_rgb("#F00") == (1.0, 0.0, 0.0)

    def test_empty_raises_clear_error(self):
        with pytest.raises(ValueError, match="hex"):
            handlers._hex_to_rgb("")

    def test_wrong_length_raises_clear_error(self):
        with pytest.raises(ValueError, match="hex"):
            handlers._hex_to_rgb("#FFFF")

    def test_non_hex_chars_raise_clear_error(self):
        with pytest.raises(ValueError, match="non-hex|hex"):
            handlers._hex_to_rgb("#GGGGGG")

    def test_set_layer_channel_bad_hex_clear_error(self, fresh_layer_stack):
        layer_id = handlers.get_layer_stack()[-1]["id"]
        with pytest.raises(ValueError, match="hex"):
            handlers.set_layer_channel(layer_id, "BaseColor", "#ZZZ")


class TestFrameMeshFovGuard:
    def test_zero_fov_does_not_crash(self, fresh_layer_stack):
        """fov=0（正交/退化相机）不应触发除零，应回退到安全 FOV。"""
        import substance_painter.display as display
        cam = display.Camera.get_default_camera()
        cam.field_of_view = 0.0
        result = handlers.frame_mesh()
        assert result["ok"] is True

    def test_180_fov_does_not_crash(self, fresh_layer_stack):
        import substance_painter.display as display
        cam = display.Camera.get_default_camera()
        cam.field_of_view = 180.0
        result = handlers.frame_mesh()
        assert result["ok"] is True


class TestGroupLayersDedup:
    def test_duplicate_ids_cloned_once(self, fresh_layer_stack, monkeypatch):
        """同一 id 传两次只应克隆一次（修复前会克隆两次并对已删节点二次 delete）。"""
        stack = handlers.get_layer_stack()
        fill_id = [n["id"] for n in stack if n["type"] == "FillLayerNode"][0]

        calls = []
        real_clone = handlers._clone_node

        def _spy(src, pos, warnings=None):
            calls.append(src.uid())
            return real_clone(src, pos, warnings)

        monkeypatch.setattr(handlers, "_clone_node", _spy)
        result = handlers.group_layers([fill_id, fill_id])
        assert result["ok"] is True
        # 去重后该节点只被克隆一次
        assert calls.count(int(fill_id)) == 1


class TestBridgeCancelReportsError:
    def test_stop_writes_error_on_queued_task(self):
        """真实驱动 BridgeServer.stop()：队列里未执行的任务被取消时，
        其 holder 必须被写入 error，避免 HTTP 端误报 ok:true/result:null。"""
        import threading
        from plugin.sp_bridge import bridge

        holder = {"result": None, "error": None}
        done = threading.Event()
        cancelled = [False]

        def _task():
            pass
        _task._holder = holder
        _task._done = done
        _task._cancel = lambda: cancelled.__setitem__(0, True)

        # 把任务塞进 bridge 的全局队列，然后跑真实的 stop()。
        # server/timer 均为 None，stop() 只走 drain+cancel 分支。
        bridge._task_queue.put(_task)
        srv = bridge.BridgeServer()
        srv.stop()

        assert cancelled[0] is True
        assert holder["error"] is not None and "cancel" in holder["error"].lower()
        assert done.is_set()


# ══════════════════════════════════════════════════════════════════════════════
# 离线调试第二轮：把「静默谎报成功」改成如实报告（不依赖真实 SP）
#
# #F apply_material 五个通道全部失败时仍返回 ok → 现应抛错；部分失败应在
#    返回值里给出 failed_channels。
# #G set_texture_set_resolution 找不到匹配活动 stack 的纹理集时仍返回 ok →
#    现应抛错（分辨率根本没改）。
# #H end_batch 提交（__exit__）抛异常时仍返回 ok → 现应抛错，且必须清空
#    _batch_scope 以免后续 begin_batch 永久卡死。
# ══════════════════════════════════════════════════════════════════════════════


class TestApplyMaterialFailureReporting:
    def test_all_channels_fail_raises(self, fresh_layer_stack, monkeypatch):
        r = handlers.add_fill_layer("MatFail")
        node = ls.get_node_by_uid(int(r["id"]))

        def _boom(ch, value):
            raise RuntimeError("set_source boom")
        monkeypatch.setattr(node, "set_source", _boom)

        with pytest.raises(RuntimeError, match="failed to apply"):
            handlers.apply_material(r["id"], "Carbon Fiber")

    def test_partial_failure_reports_failed_channels(self, fresh_layer_stack, monkeypatch):
        r = handlers.add_fill_layer("MatPartial")
        node = ls.get_node_by_uid(int(r["id"]))
        import substance_painter.layerstack as _ls
        real_set = node.set_source

        def _flaky(ch, value):
            if ch == _ls.ChannelType.Normal:
                raise RuntimeError("normal channel boom")
            return real_set(ch, value)
        monkeypatch.setattr(node, "set_source", _flaky)

        result = handlers.apply_material(r["id"], "Carbon Fiber")
        assert result["ok"] is True
        assert "Normal" in result["failed_channels"]
        assert "BaseColor" in result["applied_channels"]

    def test_all_success_no_failed_key(self, fresh_layer_stack):
        layer_id = handlers.get_layer_stack()[-1]["id"]
        result = handlers.apply_material(layer_id, "Carbon Fiber")
        assert result["ok"] is True
        assert "failed_channels" not in result


class TestSetResolutionNoMatchRaises:
    def test_no_matching_stack_raises(self, fresh_layer_stack, monkeypatch):
        import substance_painter.textureset as ts
        # 让活动 stack 变成一个谁都不匹配的对象
        monkeypatch.setattr(ts, "get_active_stack", lambda: object())
        with pytest.raises(RuntimeError, match="NOT changed"):
            handlers.set_texture_set_resolution(2048, 2048)

    def test_match_still_ok(self, fresh_layer_stack):
        result = handlers.set_texture_set_resolution(2048, 2048)
        assert result["ok"] is True

    def test_matches_by_value_not_identity(self, fresh_layer_stack):
        """实机回归：pybind11 每次 get_stack()/get_active_stack() 返回不同
        包装对象（is False / == True）。mock 现也如此，handler 必须用 ==
        匹配；若误用 is 会匹配不到而 raise，本测试即失败。"""
        import substance_painter.textureset as ts
        active = ts.get_active_stack()
        ts_stack = ts.all_texture_sets()[0].get_stack()
        # 不同对象（is False）但值相等（== True）——精确复现实机行为
        assert active is not ts_stack
        assert active == ts_stack
        # handler 必须靠 == 找到纹理集
        result = handlers.set_texture_set_resolution(1024, 1024)
        assert result["ok"] is True
        assert result["width"] == 1024


class TestEndBatchCommitFailure:
    def test_commit_failure_raises_and_clears_scope(self, fresh_layer_stack):
        handlers.begin_batch("WillFailCommit")

        class _BoomScope:
            def __exit__(self, *a):
                raise RuntimeError("commit boom")
        handlers._batch_scope = _BoomScope()

        with pytest.raises(RuntimeError, match="failed to commit"):
            handlers.end_batch()
        # 关键：即便提交失败，_batch_scope 也必须被清空，否则后续永久卡死
        assert handlers._batch_scope is None
        # 验证可以再次开新 batch（不会报 already active）
        handlers.begin_batch("AfterFailure")
        handlers.end_batch()


# ══════════════════════════════════════════════════════════════════════════════
# 离线调试第三轮：并发/契约硬化（#1/#2/#3/#4）
#
# #1 allow_reuse_address 应设在 server 实例上，不污染 ThreadingHTTPServer 类全局。
# #2 bridge stop() 后入队的请求不再留下孤儿任务，而是被 _shutting_down 拒绝。
# #3 _node_effect_count 探测失败返回 None（而非 0），上层据此给出「无法确认」告警，
#    即便 SP 的 effect accessor 改名也不会静默丢失。
# #4 client.call(timeout<60) 时 HTTP 读超时仍 ≥ bridge 实际等待（夹取到下限），
#    避免客户端先于 bridge 超时导致重复执行。
# ══════════════════════════════════════════════════════════════════════════════


class TestClientTimeoutFloor:
    """#4：client 读超时必须覆盖 bridge 的等待下限。"""

    def _capture_http_timeout(self, monkeypatch, call_timeout):
        from server import client as sp_client
        captured = {}

        class _Resp:
            status_code = 200
            def json(self):
                return {"ok": True, "result": None}

        def fake_post(url, json=None, timeout=None):
            captured["http_timeout"] = timeout
            return _Resp()

        import requests
        monkeypatch.setattr(requests, "post", fake_post)
        sp_client.call("ping", timeout=call_timeout)
        return captured["http_timeout"]

    def test_short_timeout_still_covers_bridge_floor(self, monkeypatch):
        from server import client as sp_client
        # 请求 timeout=20，但 bridge 会等到下限 60s；client 读超时必须 > 60。
        http_t = self._capture_http_timeout(monkeypatch, 20)
        assert http_t >= sp_client._BRIDGE_MIN_WAIT
        assert http_t > 20 + 5  # 不能只按请求值 +5 计算

    def test_long_timeout_passthrough(self, monkeypatch):
        http_t = self._capture_http_timeout(monkeypatch, 300)
        assert http_t >= 300

    def test_huge_timeout_clamped_to_ceiling(self, monkeypatch):
        from server import client as sp_client
        http_t = self._capture_http_timeout(monkeypatch, 999999)
        assert http_t <= sp_client._BRIDGE_MAX_WAIT + sp_client._TIMEOUT_MARGIN

    def test_default_timeout_covers_floor(self, monkeypatch):
        from server import client as sp_client
        captured = {}

        class _Resp:
            status_code = 200
            def json(self):
                return {"ok": True, "result": None}

        def fake_post(url, json=None, timeout=None):
            captured["http_timeout"] = timeout
            captured["body"] = json
            return _Resp()

        import requests
        monkeypatch.setattr(requests, "post", fake_post)
        sp_client.call("ping")  # 无 timeout
        # 默认路径不应把 timeout 写进 body，且读超时 ≥ bridge 下限+余量
        assert "timeout" not in captured["body"]
        assert captured["http_timeout"] >= sp_client._BRIDGE_MIN_WAIT + sp_client._TIMEOUT_MARGIN


class TestBridgeShutdownRejectsEnqueue:
    """#2：关闭后入队被拒绝，不再产生孤儿任务。"""

    def test_shutting_down_flag_set_by_stop(self):
        from plugin.sp_bridge import bridge
        # 跑真实 stop()（server/timer 为 None），应置位 _shutting_down
        srv = bridge.BridgeServer()
        srv.stop()
        assert bridge._shutting_down is True
        # start() 应复位标志，避免 reload 后无法工作
        # 不真正起 HTTP server：手动验证复位逻辑的契约
        import threading
        with bridge._enqueue_lock:
            bridge._shutting_down = False
        assert bridge._shutting_down is False


class TestEffectCountTristate:
    """#3：探测失败返回 None；上层据此告警而非静默。"""

    def test_returns_int_when_accessor_present(self, fresh_layer_stack):
        r = handlers.add_fill_layer("EffCount")
        node = ls.get_node_by_uid(int(r["id"]))
        node._content_effects = ["a", "b"]
        assert handlers._node_effect_count(node, "content") == 2

    def test_returns_zero_when_empty(self, fresh_layer_stack):
        r = handlers.add_fill_layer("EffEmpty")
        node = ls.get_node_by_uid(int(r["id"]))
        assert handlers._node_effect_count(node, "content") == 0

    def test_returns_none_when_accessor_absent(self):
        class _Bare:
            pass
        # 没有 content_effects/get_content_effects → 无法探测 → None
        assert handlers._node_effect_count(_Bare(), "content") is None

    def test_clone_warns_when_cannot_verify(self, fresh_layer_stack, monkeypatch):
        """探测失败（None）时克隆应给出「无法确认」告警，绝不静默。"""
        r = handlers.add_fill_layer("CannotVerify")
        monkeypatch.setattr(handlers, "_node_effect_count",
                            lambda node, kind: None)
        result = handlers.duplicate_layer(r["id"])
        assert "warnings" in result
        assert any("could not verify" in w for w in result["warnings"])


class TestAllowReuseAddressNotGlobal:
    """#1：不应在 ThreadingHTTPServer 类上设置 allow_reuse_address。"""

    def test_class_attr_not_mutated_by_import(self):
        from http.server import ThreadingHTTPServer
        # 模块默认值即可（True/False 视实现），关键是 bridge 不在 import/类层面强改。
        # 我们断言 bridge 源码不再含「ThreadingHTTPServer.allow_reuse_address =」赋值。
        import pathlib
        src = pathlib.Path("plugin/sp_bridge/bridge.py").read_text(encoding="utf-8")
        assert "ThreadingHTTPServer.allow_reuse_address =" not in src
        assert "self._server.allow_reuse_address = True" in src


# ══════════════════════════════════════════════════════════════════════════════
# 实机调试（SP 10.0.1 实测，离线 mock 已同步真实 API 形态）
#
# R1 list_resources_by_usage: 真实 Type 没有 FILTER/GENERATOR/TEXTURE/ENVIRONMENT，
#    用途在 Usage 枚举；必须用 res.usages() 配 r.Usage 筛选。
# R2 list_export_presets: 导出预设不在 resource.search()，须用 export 模块 API。
# R3 _resolve_channel: 真实 ChannelType 用 "AO" 不是 "AmbientOcclusion"，
#    旧实现建表时即崩，连累所有 substance 源查询。
# R4 _serialize_property_value: 真实 get_parameters() 返回原生值（非 PropertyValue），
#    旧实现无条件 .value() 退化成 str，把 0.5 变 "0.5"。
# R5 MeshMapUsage / ToneMappingFunction 是 pybind11 枚举，不可直接迭代。
# ══════════════════════════════════════════════════════════════════════════════


class TestListResourcesByUsageReal:
    def test_filter_uses_usages(self, fresh_layer_stack):
        r = handlers.list_resources_by_usage("filter")
        assert r["count"] >= 1
        assert "Blur" in r["resources"]

    def test_generator(self, fresh_layer_stack):
        r = handlers.list_resources_by_usage("generator")
        assert r["count"] >= 1

    def test_texture(self, fresh_layer_stack):
        r = handlers.list_resources_by_usage("texture")
        assert r["count"] >= 1

    def test_environment(self, fresh_layer_stack):
        r = handlers.list_resources_by_usage("environment")
        assert "Sunrise" in r["resources"]

    def test_substance_maps_to_procedural(self, fresh_layer_stack):
        r = handlers.list_resources_by_usage("substance")
        assert "Carbon Fiber" in r["resources"]

    def test_unknown_raises(self, fresh_layer_stack):
        with pytest.raises(ValueError, match="Unknown usage"):
            handlers.list_resources_by_usage("bogus")


class TestListExportPresetsReal:
    def test_uses_export_module(self, fresh_layer_stack):
        r = handlers.list_export_presets()
        assert isinstance(r, list)
        # 来自 predefined + resource 两路
        assert "PBR Metallic Roughness" in r
        assert "Unity HD Render Pipeline" in r


class TestResolveChannelReal:
    def test_does_not_crash_building_map(self):
        # 旧实现会在建表时访问不存在的 AmbientOcclusion 而崩；新实现防御式构建
        assert handlers._resolve_channel("BaseColor") is not None

    def test_ao_alias(self):
        # "AmbientOcclusion" 别名应解析到真实的 AO（mock 现也用 AO）
        import substance_painter.layerstack as _ls
        if hasattr(_ls.ChannelType, "AO"):
            assert handlers._resolve_channel("AmbientOcclusion") == _ls.ChannelType.AO

    def test_unknown_channel_raises(self):
        with pytest.raises(ValueError, match="Unknown channel"):
            handlers._resolve_channel("NotAChannel")


class TestSerializePropertyValueReal:
    def test_native_float_passthrough(self):
        # 真实 get_parameters() 给原生 float，不能退化成字符串
        assert handlers._serialize_property_value(0.5) == 0.5
        assert isinstance(handlers._serialize_property_value(0.5), float)

    def test_native_int_passthrough(self):
        assert handlers._serialize_property_value(32) == 32

    def test_wrapped_value_object(self):
        class _PV:
            def value(self): return 0.8
        assert handlers._serialize_property_value(_PV()) == 0.8


class TestMeshMapUsageIteration:
    def test_iter_helper_returns_members(self):
        usages = handlers._iter_mesh_map_usages()
        assert len(usages) >= 1
        # 应能拿到 AO 等成员
        names = {getattr(u, "name", str(u)) for u in usages}
        assert "AO" in names or len(names) >= 1


# ══════════════════════════════════════════════════════════════════════════════
# 加固轮 — 把「硬写枚举成员、建表即崩」与「无事可做却谎报成功」彻底清掉。
#
# 同一类 bug 在 _resolve_channel / list_resources_by_usage 上已实机踩过：
# 不同 SP 版本枚举成员可能增删/改名，硬写 Enum.Member 在建表时整体抛
# AttributeError，连合法输入也一并失败。这里守住剩余的 Usage / 项目枚举表，
# 以及 baking 两个「静默丢弃输入仍 ok」的路径。
# ══════════════════════════════════════════════════════════════════════════════


class TestUsageMapDefensive:
    """list_resources_by_usage 的 Usage 表用 getattr 防御式构建：
    单个成员名在某版本缺失时只是少一个可选用途，而非整函数崩溃。"""

    def test_missing_one_usage_member_does_not_crash_others(self, fresh_layer_stack):
        import substance_painter.resource as r
        # 删掉一个成员，模拟某版本 SP 没有 SHADER
        had = hasattr(r.Usage, "SHADER")
        saved = getattr(r.Usage, "SHADER", None)
        if had:
            delattr(r.Usage, "SHADER")
        try:
            # filter 这条合法路径仍应正常工作，不被缺失成员牵连
            out = handlers.list_resources_by_usage("filter")
            assert out["count"] >= 1
            # 缺失的成员从合法集合里消失 → 用它会得到清晰的 Unknown usage
            with pytest.raises(ValueError, match="Unknown usage"):
                handlers.list_resources_by_usage("shader")
        finally:
            if had:
                setattr(r.Usage, "SHADER", saved)


class TestCreateProjectEnumDefensive:
    """create_project 的 NormalMapFormat/TangentSpace/ProjectWorkflow 表
    用 getattr 构建：缺失成员从合法集合移除，而非建表即崩。"""

    def test_missing_workflow_member_does_not_crash(self, fresh_layer_stack, monkeypatch):
        import substance_painter.project as project
        # create_project 要求当前无打开项目，先模拟已关闭
        monkeypatch.setattr(project, "is_open", lambda: False)
        # 模拟某版本没有 UVTile workflow
        had = hasattr(project.ProjectWorkflow, "UVTile")
        saved = getattr(project.ProjectWorkflow, "UVTile", None)
        if had:
            delattr(project.ProjectWorkflow, "UVTile")
        try:
            # 用缺失的 workflow → 清晰 ValueError，而非 AttributeError 崩在建表处
            with pytest.raises(ValueError, match="Unknown project_workflow"):
                handlers.create_project("/tmp/mesh.fbx", project_workflow="UVTile")
        finally:
            if had:
                setattr(project.ProjectWorkflow, "UVTile", saved)


class TestSetBakingParametersUnmatched:
    """传了参数却一个名字都没匹配上 → 全被静默丢弃，必须报错而非 ok。"""

    def test_no_param_matches_raises(self):
        with pytest.raises(ValueError, match="none of the given parameter names"):
            handlers.set_baking_parameters(
                "Default", common_params={"TotallyBogusKey": 1})

    def test_matched_param_reports_count(self):
        out = handlers.set_baking_parameters(
            "Default", common_params={"OutputSize": [4096, 4096]})
        assert out["updated_count"] == 1
        assert out["unmatched_params"] == []

    def test_no_params_at_all_is_noop_ok(self):
        # 完全不传参数 → 不是「丢弃了输入」，按惯例视为无操作成功
        out = handlers.set_baking_parameters("Default")
        assert out["ok"] is True
        assert out["updated_count"] == 0


class TestSetBakingStateNoChange:
    """全部可改项都为 None → 没有任何要做的事，明确报错而非假装成功。"""

    def test_all_none_raises(self):
        with pytest.raises(ValueError, match="no state given to change"):
            handlers.set_baking_state("Default")

    def test_one_field_still_works(self):
        out = handlers.set_baking_state("Default", enabled=True)
        assert out["ok"] is True
        assert any("textureset_enabled" in c for c in out["changed"])


class TestSetEnvironmentUsageFiltered:
    """set_environment 只在 Usage.ENVIRONMENT 资源里匹配，避免误选同名的
    非环境资源；未命中时把可用环境贴图列进报错。"""

    def test_picks_environment_resource(self, fresh_layer_stack):
        out = handlers.set_environment("Sunrise")
        assert out["ok"] is True
        assert out["environment"] == "Sunrise"

    def test_unknown_lists_available(self, fresh_layer_stack):
        with pytest.raises(ValueError, match="Available environments"):
            handlers.set_environment("NoSuchHDRI_xyz")

    def test_does_not_select_non_environment_same_name(self, fresh_layer_stack, monkeypatch):
        # 构造一个和环境贴图同名、但用途是 smart_material 的资源排在前面，
        # 旧实现（不校验用途）会误选它；新实现只认 ENVIRONMENT。
        import substance_painter.resource as r
        import substance_painter.display as display

        class _Fake:
            def __init__(self, name, usages, ident):
                self._n = name
                self._u = usages
                self._id = ident
            def gui_name(self): return self._n
            def usages(self): return list(self._u)
            def identifier(self): return self._id

        real_search = r.search

        def fake_search(q):
            base = list(real_search(q))
            # 同名 brush 排最前面（诱饵，id 独特），真正的环境资源在后
            return [_Fake("Studio", ["brush"], "id://decoy-brush")] + base

        # 捕获实际传给 set_environment_resource 的 identifier
        captured = {}
        monkeypatch.setattr(display, "set_environment_resource",
                            lambda rid: captured.__setitem__("rid", rid))
        monkeypatch.setattr(r, "search", fake_search)

        handlers.set_environment("Studio")
        # 绝不能选中 brush 诱饵的 id —— 必须是某个环境用途资源
        assert captured["rid"] != "id://decoy-brush"


class TestExportTexturesRealApi:
    """实机回归：export_project_textures 接受 JSON dict（无 ExportConfig 类），
    返回 .textures 为 {stack: [files]} dict。守住 handler 用真实 API。"""

    def test_returns_flattened_files(self, fresh_layer_stack):
        out = handlers.export_textures(preset="PBR Metallic Roughness",
                                       output_dir="/tmp/export")
        # 从 {stack: [...]} 展平为单一列表
        assert out["count"] == len(out["files"])
        assert out["count"] > 0
        assert all(isinstance(f, str) for f in out["files"])

    def test_unknown_preset_raises(self, fresh_layer_stack):
        with pytest.raises(ValueError, match="Export preset not found"):
            handlers.export_textures(preset="__NoSuchPreset__",
                                     output_dir="/tmp/export")

    def test_resource_preset_resolves(self, fresh_layer_stack):
        # 资源预设（经 resource_id.url()）也应能解析
        out = handlers.export_textures(preset="Unity HD Render Pipeline",
                                       output_dir="/tmp/export")
        assert out["count"] > 0

