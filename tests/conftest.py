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

    class _FakeSignal:
        def __init__(self): self._slots = []
        def connect(self, slot): self._slots.append(slot)
        def emit(self, *args):
            for s in self._slots: s(*args)

    class _FakeQTimer:
        _active = []
        def __init__(self): pass
        def timeout(self): return _FakeSignal()
        def start(self, ms): pass
        def stop(self): pass
        @staticmethod
        def singleShot(ms, fn): fn()  # mock: 立即执行

    pyside2_core.QTimer = _FakeQTimer
    pyside2.QtCore = pyside2_core

    # QBuffer / QIODevice mock for viewport capture
    class _FakeBuffer:
        def __init__(self): self._data = b""
        def open(self, mode): pass
        def write(self, data): self._data = data
        def data(self): return self._data
    pyside2_core.QBuffer = _FakeBuffer
    pyside2_core.QIODevice = type('QIODevice', (), {'WriteOnly': 0})

    pyside2_widgets = types.ModuleType("PySide2.QtWidgets")

    class _MockWidget:
        """模拟 Qt widget，支持 findChildren/findChild。"""
        def __init__(self, name="", parent=None):
            self._name = name
            self._parent = parent
            self._children = []
            self._text = ""
            if parent and hasattr(parent, '_children'):
                parent._children.append(self)
        def objectName(self): return self._name
        def text(self): return self._text
        def setParent(self, p):
            if self._parent and self in self._parent._children:
                self._parent._children.remove(self)
            self._parent = p
            if p and hasattr(p, '_children') and self not in p._children:
                p._children.append(self)
        def findChild(self, dtype, name=""):
            for c in self._children:
                if name and c._name != name: continue
                if dtype and not isinstance(c, dtype): continue
                return c
            return None
        def findChildren(self, dtype):
            result = []
            for c in self._children:
                if isinstance(c, dtype):
                    result.append(c)
                if hasattr(c, 'findChildren'):
                    result.extend(c.findChildren(dtype))
            return result

    class _MockQLineEdit(_MockWidget):
        def __init__(self, name="", parent=None):
            super().__init__(name, parent)
            self._text = ""
            self.editingFinished = _FakeSignal()
        def text(self): return self._text
        def setText(self, v): self._text = str(v)

    class _MockQSpinBox(_MockWidget):
        def __init__(self, name="", parent=None):
            super().__init__(name, parent)
            self._value = 0
        def value(self): return self._value
        def setValue(self, v): self._value = v

    class _MockQComboBox(_MockWidget):
        def __init__(self, name="", parent=None):
            super().__init__(name, parent)
            self._items = []
            self._current = 0
        def count(self): return len(self._items)
        def itemText(self, i): return self._items[i] if i < len(self._items) else ""
        def currentText(self): return self._items[self._current] if self._items else ""

    class _MockQAction(_MockWidget):
        def __init__(self, name="", parent=None, enabled=True):
            super().__init__(name, parent)
            self._text = name
            self._enabled = enabled
        def text(self): return self._text
        def isEnabled(self): return self._enabled
        def trigger(self): pass

    class _MockQDockWidget(_MockWidget):
        def __init__(self, name="", parent=None):
            super().__init__(name, parent)
            self._widget = None
        def widget(self): return self._widget
        def setWidget(self, w): self._widget = w

    class _MockQMainWindow(_MockWidget):
        def __init__(self):
            super().__init__("S4MainWindow")
        def menuBar(self): return _MockWidget("menubar", self)

    pyside2_widgets.QWidget = _MockWidget
    pyside2_widgets.QLineEdit = _MockQLineEdit
    pyside2_widgets.QSpinBox = _MockQSpinBox
    pyside2_widgets.QComboBox = _MockQComboBox
    pyside2_widgets.QAction = _MockQAction
    pyside2_widgets.QDockWidget = _MockQDockWidget
    pyside2_widgets.QMainWindow = _MockQMainWindow
    pyside2.QtWidgets = pyside2_widgets

    # QOpenGLWidget mock — used by handlers via PySide2.QtWidgets
    class _MockQOpenGLWidget(_MockWidget):
        def __init__(self, name="", parent=None):
            super().__init__(name, parent)
            self._w = 800
            self._h = 600
        def width(self): return self._w
        def height(self): return self._h
        def grab(self):
            class FakePixmap:
                def __init__(self, w, h): self._w, self._h = w, h
                def width(self): return self._w
                def height(self): return self._h
                def save(self, buf, fmt): pass
            return FakePixmap(self._w, self._h)

    pyside2_widgets.QOpenGLWidget = _MockQOpenGLWidget

    # QOpenGLWidget mock for PySide2.QtOpenGLWidgets import path
    pyside2_gl = types.ModuleType("PySide2.QtOpenGLWidgets")
    pyside2_gl.QOpenGLWidget = _MockQOpenGLWidget
    sys.modules["PySide2.QtOpenGLWidgets"] = pyside2_gl

    sys.modules["PySide2"] = pyside2
    sys.modules["PySide2.QtCore"] = pyside2_core
    sys.modules["PySide2.QtWidgets"] = pyside2_widgets

    # ── 构建 mock Iray 面板 ──
    _mock_main_window = _MockQMainWindow()
    _iray_panel = _MockWidget("irayParametersView")
    _mock_dock = _MockQDockWidget("irayParametersView")
    _mock_dock.setWidget(_iray_panel)
    _mock_dock.setParent(_mock_main_window)

    # maxSamples / maxTime / width / height widgets
    _max_samples_container = _MockWidget("maxSamples", _iray_panel)
    _max_samples_le = _MockQLineEdit("value", _max_samples_container)
    _max_samples_le.setText("1000")

    _max_time_container = _MockWidget("maxTime", _iray_panel)
    _max_time_le = _MockQLineEdit("value", _max_time_container)
    _max_time_le.setText("300")

    _width_sb = _MockQSpinBox("width", _iray_panel)
    _width_sb.setValue(1920)
    _height_sb = _MockQSpinBox("height", _iray_panel)
    _height_sb.setValue(1080)

    # iterationsLabel / timeLabel
    _MockWidget("iterationsLabel", _iray_panel)
    _MockWidget("timeLabel", _iray_panel)

    # Iray QAction
    _iray_action = _MockQAction("Rendering (Iray)", enabled=True)
    _iray_action.setParent(_mock_main_window)

    # Mock QOpenGLWidget (viewport)
    _mock_viewport = _MockQOpenGLWidget("Viewer3D", _mock_main_window)

    _mock_viewport = _MockQOpenGLWidget("Viewer3D", _mock_main_window)

    def _mock_get_main_window():
        return _mock_main_window

    ui.get_main_window = _mock_get_main_window

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
