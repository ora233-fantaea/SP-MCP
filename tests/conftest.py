"""
conftest.py — shared fixtures for SP MCP tests.

mock substance_painter.* 按照 SP 10.x 真实 API 结构构建。
关键：get_root_layer_nodes(stack) 返回 List[Node] 对象，不是 int ID。
"""

import sys
import types
import pytest


def _make_sp_mock():
    sp = types.ModuleType("substance_painter")
    sp.__version__ = "10.0.0"

    # ── substance_painter.application ──
    app = types.ModuleType("substance_painter.application")
    _app_version = "10.0.0"
    app.version = lambda: _app_version
    app._app_version = _app_version

    # ── substance_painter.ui ──
    ui = types.ModuleType("substance_painter.ui")
    ui.schedule_on_ui_thread = lambda fn: fn()
    ui.get_main_window = lambda: None

    # ── substance_painter.logging ──
    logging_mod = types.ModuleType("substance_painter.logging")
    logging_mod.INFO = "INFO"
    logging_mod.ERROR = "ERROR"
    logging_mod.log = lambda *a, **kw: None
    sp.logging = logging_mod

    # ── substance_painter.layerstack ──
    layerstack = types.ModuleType("substance_painter.layerstack")

    class _Enum:
        def __init__(self, name):
            self.name = name
        def __repr__(self):
            return f"{type(self).__name__}.{self.name}"

    class ChannelType(_Enum):
        BaseColor  = _Enum("BaseColor")
        Roughness  = _Enum("Roughness")
        Metallic   = _Enum("Metallic")
        Height     = _Enum("Height")
        Normal     = _Enum("Normal")

    class BlendingMode(_Enum):
        Normal   = _Enum("Normal")
        Multiply = _Enum("Multiply")
        Overlay  = _Enum("Overlay")
        Screen   = _Enum("Screen")

    # ── MockNode: 模拟真实节点对象 ──
    _next_uid = [1]

    def _make_node_class(class_name):
        """动态创建指定名称的节点类，使 type(node).__name__ 匹配真实 API。"""
        def __init__(self, name, parent=None):
            self._uid = _next_uid[0]
            _next_uid[0] += 1
            self._name = name
            self._visible = True
            self._opacity = {}
            self._blending = {}
            self._parent = parent
            self._children = []
            self._stack = None

        def uid(self):
            return self._uid

        def get_name(self):
            return self._name

        def set_name(self, v):
            self._name = v

        def is_visible(self):
            return self._visible

        def set_visible(self, v):
            self._visible = v

        def get_opacity(self, channel=None):
            ch = channel or ChannelType.BaseColor
            return self._opacity.get(ch, 1.0)

        def set_opacity(self, v, channel=None):
            ch = channel or ChannelType.BaseColor
            self._opacity[ch] = v

        def get_blending_mode(self, channel=None):
            ch = channel or ChannelType.BaseColor
            return self._blending.get(ch, BlendingMode.Normal)

        def set_blending_mode(self, v, channel=None):
            ch = channel or ChannelType.BaseColor
            self._blending[ch] = v

        def get_stack(self):
            return self._stack

        def set_source(self, ch, color):
            pass

        def add_child(self, child):
            child._parent = self
            child._stack = self._stack
            self._children.append(child)

        def sub_layers(self):
            return list(self._children)

        def add_mask(self, background):
            self._has_mask = True

        ns = {
            "__init__": __init__, "uid": uid, "get_name": get_name,
            "set_name": set_name, "is_visible": is_visible, "set_visible": set_visible,
            "get_opacity": get_opacity, "set_opacity": set_opacity,
            "get_blending_mode": get_blending_mode, "set_blending_mode": set_blending_mode,
            "get_stack": get_stack, "set_source": set_source, "add_child": add_child,
            "sub_layers": sub_layers, "add_mask": add_mask,
        }
        return type(class_name, (), ns)

    MockNode = _make_node_class("FillLayerNode")
    MockGroupNode = _make_node_class("GroupLayerNode")

    class MockStack:
        def __init__(self, stack_id=0):
            self.stack_id = stack_id

    # ── 全局状态 ──
    _root_nodes = []
    _mock_stack = MockStack()
    _group_stacks = {}  # group_stack -> group_node（用于 get_root_layer_nodes）

    def _build_default_stack():
        _next_uid[0] = 1
        _root_nodes.clear()
        _group_stacks.clear()
        g = MockGroupNode("Group_Base")
        g._group_stack = MockStack(stack_id=_next_uid[0])
        _next_uid[0] += 1
        g._stack = g._group_stack
        _group_stacks[g._group_stack] = g
        f1 = MockNode("Metal_Base")
        f2 = MockNode("Scratches")
        f3 = MockNode("Edge_Wear")
        g.add_child(f1)
        g.add_child(f2)
        f3._stack = _mock_stack
        _root_nodes.extend([g, f3])

    _build_default_stack()

    def get_root_layer_nodes(stack):
        """返回 List[Node]。如果 stack 是某 group 的专属 stack，返回其子节点。"""
        if stack in _group_stacks:
            group = _group_stacks[stack]
            return list(group._children)
        return list(_root_nodes)

    def insert_fill(pos):
        node = MockNode("New Layer")
        _root_nodes.insert(0, node)
        return node

    def delete_node(node):
        if node in _root_nodes:
            _root_nodes.remove(node)
        elif node._parent and node in node._parent._children:
            node._parent._children.remove(node)

    class InsertPosition:
        def __init__(self, node, node_stack=None):
            self._node = node
            self._node_stack = node_stack

        @staticmethod
        def from_textureset_stack(stack):
            return InsertPosition(None, stack)

        def above_node(self, node=None):
            return InsertPosition(node or self._node, self._node_stack)

        def below_node(self, node=None):
            return InsertPosition(node or self._node, self._node_stack)

        def inside_node(self, node, node_stack):
            return InsertPosition(node, node_stack)

    layerstack.ChannelType = ChannelType
    layerstack.BlendingMode = BlendingMode
    layerstack.InsertPosition = InsertPosition
    layerstack.MockNode = MockNode
    layerstack.MockGroupNode = MockGroupNode
    layerstack.get_root_layer_nodes = get_root_layer_nodes
    layerstack.insert_fill = insert_fill
    layerstack.insert_smart_material = lambda pos, rid: MockGroupNode("Smart_Material")
    layerstack.insert_smart_mask = lambda pos, rid: [MockNode("MaskEffect")]
    layerstack.delete_node = delete_node

    class MaskBackground:
        Black = "Black"
        White = "White"
    layerstack.MaskBackground = MaskBackground

    class NodeStack:
        Content = "Content"
        Mask = "Mask"
        Substack = "Substack"
    layerstack.NodeStack = NodeStack

    class MockColor:
        def __init__(self, r, g, b, cs=None):
            self.r, self.g, self.b = r, g, b
    layerstack.Color = MockColor

    layerstack._root_nodes = _root_nodes
    layerstack._mock_stack = _mock_stack
    layerstack._group_stacks = _group_stacks
    layerstack._build_default_stack = _build_default_stack

    # ── substance_painter.textureset ──
    textureset = types.ModuleType("substance_painter.textureset")
    textureset.get_active_stack = lambda: _mock_stack
    textureset.Stack = MockStack

    # ── substance_painter.export ──
    export = types.ModuleType("substance_painter.export")
    class ExportConfig:
        export_path = ""
        preset = ""
    class ExportResult:
        textures = ["/tmp/export/BaseColor.png", "/tmp/export/Roughness.png",
                    "/tmp/export/Metallic.png", "/tmp/export/Normal.png"]
    export.ExportConfig = ExportConfig
    export.export_project_textures = lambda config: ExportResult()

    # ── substance_painter.resource ──
    resource = types.ModuleType("substance_painter.resource")

    class ResourceType:
        SMART_MATERIAL = "smartmaterial"
        SMART_MASK = "smartmask"
    resource.Type = ResourceType

    class MockResourceID:
        def __init__(self, name, ctx="user"):
            self.name = name
            self.context = ctx
            self.version = "1.0"
        def url(self):
            return f"resource://{self.context}/{self.name}"

    class MockResource:
        def __init__(self, name, res_type="smartmaterial"):
            self._name = name
            self._type = res_type
            self._id = MockResourceID(name)
        def gui_name(self):
            return self._name
        def identifier(self):
            return self._id
        def type(self):
            return self._type

    def resource_search(query):
        all_mats = [
            MockResource("Steel", "smartmaterial"),
            MockResource("Copper", "smartmaterial"),
            MockResource("Gold Armor", "smartmaterial"),
        ]
        if not query:
            return all_mats
        return [r for r in all_mats if query.lower() in r._name.lower()]

    resource.search = resource_search
    resource.ResourceID = MockResourceID

    # ── PySide2 mock ──
    pyside2 = types.ModuleType("PySide2")
    pyside2_core = types.ModuleType("PySide2.QtCore")
    class _FakeQTimer:
        def __init__(self): pass
        def timeout(self): return type('S', (), {'connect': lambda s, f: None})()
        def start(self, ms): pass
        def stop(self): pass
    pyside2_core.QTimer = _FakeQTimer
    pyside2.QtCore = pyside2_core
    sys.modules["PySide2"] = pyside2
    sys.modules["PySide2.QtCore"] = pyside2_core

    # ── 注册到 sys.modules ──
    sp.application   = app
    sp.ui            = ui
    sp.layerstack    = layerstack
    sp.textureset    = textureset
    sp.export        = export
    sp.resource      = resource

    sys.modules["substance_painter"]            = sp
    sys.modules["substance_painter.application"] = app
    sys.modules["substance_painter.ui"]         = ui
    sys.modules["substance_painter.logging"]    = logging_mod
    sys.modules["substance_painter.layerstack"]  = layerstack
    sys.modules["substance_painter.textureset"]  = textureset
    sys.modules["substance_painter.export"]      = export
    sys.modules["substance_painter.resource"]    = resource

    return sp, layerstack


SP_MOCK, LAYERS_MOCK = _make_sp_mock()


@pytest.fixture
def fresh_layer_stack():
    import substance_painter.layerstack as ls
    ls._build_default_stack()
    yield ls._root_nodes


@pytest.fixture
def bridge_url():
    return "http://localhost:27182"
