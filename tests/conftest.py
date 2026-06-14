"""
conftest.py — shared fixtures for SP MCP tests.

mock substance_painter.* 按照 SP 10.x 真实 API 结构构建。
覆盖 Phase 1–7 所有 handler 需要的 mock。

关键 API 事实：
- get_root_layer_nodes(stack) 返回 List[Node] 对象，不是 int ID
- 节点类型：type(node).__name__ → "FillLayerNode" / "GroupLayerNode" / "PaintLayerNode"
- is_visible() / set_visible(bool) — 不是 is_enabled / set_enabled
- get_opacity(channel) / set_opacity(val, channel) 需要 ChannelType 参数
- textureset.name() 是方法，get_resolution() 返回 Resolution(width, height)
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
            self._sources = {}       # channel → value（有状态）
            self._parent = parent
            self._children = []
            self._stack = None
            self._has_mask = False

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

        def set_source(self, ch, value):
            """有状态 mock：存储 channel → value 映射。"""
            self._sources[ch] = value

        def get_source(self, ch):
            """返回指定通道的 source 值。包装 cm.Color 为带 get_color() 的对象。"""
            val = self._sources.get(ch)
            if val is None:
                return None
            if hasattr(val, "value_raw"):
                # cm.Color → 包装为 SourceUniformColor-like 对象
                class _MockSource:
                    def __init__(self, color):
                        self._color = color
                    def get_color(self):
                        return self._color
                return _MockSource(val)
            return val

        def add_child(self, child):
            child._parent = self
            child._stack = self._stack
            self._children.append(child)

        def sub_layers(self):
            return list(self._children)

        def add_mask(self, background):
            self._has_mask = True

        def get_parent(self):
            return self._parent

        def get_next_sibling(self):
            if self._parent is None:
                siblings = layerstack._root_nodes
            else:
                siblings = self._parent._children
            try:
                idx = siblings.index(self)
                return siblings[idx + 1] if idx + 1 < len(siblings) else None
            except ValueError:
                return None

        def get_previous_sibling(self):
            if self._parent is None:
                siblings = layerstack._root_nodes
            else:
                siblings = self._parent._children
            try:
                idx = siblings.index(self)
                return siblings[idx - 1] if idx - 1 >= 0 else None
            except ValueError:
                return None

        ns = {
            "__init__": __init__, "uid": uid, "get_name": get_name,
            "set_name": set_name, "is_visible": is_visible, "set_visible": set_visible,
            "get_opacity": get_opacity, "set_opacity": set_opacity,
            "get_blending_mode": get_blending_mode, "set_blending_mode": set_blending_mode,
            "get_stack": get_stack, "set_source": set_source, "get_source": get_source,
            "add_child": add_child, "sub_layers": sub_layers, "add_mask": add_mask,
            "get_parent": get_parent, "get_next_sibling": get_next_sibling,
            "get_previous_sibling": get_previous_sibling,
        }
        return type(class_name, (), ns)

    MockNode = _make_node_class("FillLayerNode")
    MockGroupNode = _make_node_class("GroupLayerNode")
    MockPaintNode = _make_node_class("PaintLayerNode")

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

    def insert_group(pos):
        node = MockGroupNode("New Group")
        _root_nodes.insert(0, node)
        return node

    def insert_paint(pos):
        node = MockPaintNode("New Paint")
        _root_nodes.insert(0, node)
        return node

    def delete_node(node):
        if node in _root_nodes:
            _root_nodes.remove(node)
        elif node._parent and node in node._parent._children:
            node._parent._children.remove(node)

    def move_node(node, pos):
        """将 node 移动到 pos 位置。简化 mock：删除原位，插入到根列表头部。"""
        delete_node(node)
        _root_nodes.insert(0, node)

    class InsertPosition:
        def __init__(self, node, node_stack=None):
            self._node = node
            self._node_stack = node_stack

        @staticmethod
        def from_textureset_stack(stack):
            return InsertPosition(None, stack)

        @staticmethod
        def above_node(node=None):
            return InsertPosition(node, None)

        @staticmethod
        def below_node(node=None):
            return InsertPosition(node, None)

        @staticmethod
        def inside_node(node, node_stack):
            return InsertPosition(node, node_stack)

    layerstack.ChannelType = ChannelType
    layerstack.BlendingMode = BlendingMode
    layerstack.InsertPosition = InsertPosition
    layerstack.MockNode = MockNode
    layerstack.MockGroupNode = MockGroupNode
    layerstack.MockPaintNode = MockPaintNode
    layerstack.get_root_layer_nodes = get_root_layer_nodes
    layerstack.insert_fill = insert_fill
    layerstack.insert_group = insert_group
    layerstack.insert_paint = insert_paint
    layerstack.insert_smart_material = lambda pos, rid: MockGroupNode("Smart_Material")
    layerstack.insert_smart_mask = lambda pos, rid: [MockNode("MaskEffect")]
    layerstack.delete_node = delete_node
    layerstack.move_node = move_node

    def _get_node_by_uid(uid):
        """递归搜索所有节点（根 + 子节点）。"""
        def _search(nodes):
            for n in nodes:
                if n.uid() == uid:
                    return n
                if type(n).__name__ == "GroupLayerNode":
                    found = _search(n.sub_layers())
                    if found is not None:
                        return found
            return None
        return _search(list(_root_nodes))
    layerstack.get_node_by_uid = _get_node_by_uid

    class MockScopedModification:
        """Mock ScopedModification — 记录 enter/exit 状态。"""
        def __init__(self, name=""):
            self.name = name
            self._active = False
        def __enter__(self):
            self._active = True
            return self
        def __exit__(self, exc_type, exc_val, exc_tb):
            self._active = False
            return False
    layerstack.ScopedModification = MockScopedModification

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

    # ── substance_painter.colormanagement ──
    colormanagement = types.ModuleType("substance_painter.colormanagement")

    class MockCMColor:
        def __init__(self, r, g, b):
            self._r, self._g, self._b = r, g, b
        @property
        def value_raw(self):
            return (self._r, self._g, self._b)
        @property
        def value(self):
            return [self._r, self._g, self._b]
    colormanagement.Color = MockCMColor

    # ── substance_painter.textureset ──
    textureset = types.ModuleType("substance_painter.textureset")

    class MockResolution:
        def __init__(self, width, height):
            self.width = width
            self.height = height

    class MockTextureSet:
        def __init__(self, ts_id, name, width=4096, height=4096):
            self._id = ts_id
            self._name = name
            self._resolution = MockResolution(width, height)
            self._stack = MockStack(stack_id=ts_id)
        def name(self):
            return self._name
        def get_resolution(self):
            return self._resolution
        def set_resolution(self, width, height):
            self._resolution = MockResolution(width, height)
        def get_stack(self):
            return self._stack
        @property
        def material_id(self):
            return self._id

    _mock_texture_sets = [
        MockTextureSet(1, "Default"),
        MockTextureSet(2, "MetalParts"),
    ]

    textureset.get_active_stack = lambda: _mock_stack
    textureset.set_active_stack = lambda stack: None
    textureset.all_texture_sets = lambda: list(_mock_texture_sets)
    textureset.Stack = MockStack
    textureset.Resolution = MockResolution
    textureset._mock_texture_sets = _mock_texture_sets

    # ── substance_painter.display ──
    display_mod = types.ModuleType("substance_painter.display")

    class MockCamera:
        _position = [0.0, 0.0, 5.0]
        _rotation = [0.0, 0.0, 0.0]
        _fov = 45.0
        @property
        def position(self): return list(self._position)
        @position.setter
        def position(self, v): self._position = list(v)
        @property
        def rotation(self): return list(self._rotation)
        @rotation.setter
        def rotation(self, v): self._rotation = list(v)
        @property
        def field_of_view(self): return self._fov
        @field_of_view.setter
        def field_of_view(self, v): self._fov = v

    _mock_camera = MockCamera()
    display_mod.Camera = type("Camera", (), {
        "get_default_camera": staticmethod(lambda: _mock_camera),
    })
    display_mod._mock_camera = _mock_camera

    _mock_env_resource = None
    def _set_environment_resource(res_id):
        nonlocal _mock_env_resource
        _mock_env_resource = res_id
    def _get_environment_resource():
        return _mock_env_resource
    display_mod.set_environment_resource = _set_environment_resource
    display_mod.get_environment_resource = _get_environment_resource

    # ── substance_painter.js ──
    js_mod = types.ModuleType("substance_painter.js")

    def _js_evaluate(code):
        """Mock JS evaluate — 模拟 alg API 调用。"""
        if "alg.baking.bake" in code:
            return '{"ok": true}'
        elif "alg.texturesets.addChannel" in code:
            return '{"ok": true}'
        elif "alg.texturesets.removeChannel" in code:
            return '{"ok": true}'
        elif "alg.texturesets.getActiveTextureSet" in code:
            return '["Default"]'
        elif "alg.project.isOpen" in code:
            return "true"
        elif "alg.project.name" in code:
            return '"MockProject"'
        elif "SPUndoRedo" in code:
            return '{"ok": true}'
        elif "alg.ui.clickButton" in code:
            return '{"ok": true}'
        return '"ok"'

    js_mod.evaluate = _js_evaluate

    # ── substance_painter.undo (legacy, not used by new handlers) ──
    undo_mod = types.ModuleType("substance_painter.undo")
    undo_mod.undo = lambda: None
    undo_mod.redo = lambda: None
    undo_mod.is_undo_available = lambda: True
    undo_mod.is_redo_available = lambda: True

    # ── substance_painter.project ──
    project_mod = types.ModuleType("substance_painter.project")
    project_mod.name = lambda: "MockProject"
    project_mod.file_path = lambda: "/mock/project.spp"
    project_mod.is_open = lambda: True
    project_mod.is_busy = lambda: False
    project_mod.save = lambda: None

    class MockBoundingBox:
        def __init__(self):
            self.center = [0.0, 0.0, 0.0]
            self.dimensions = [10.0, 10.0, 10.0]
            self.radius = 8.66
    project_mod.get_scene_bounding_box = lambda: MockBoundingBox()

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
        SUBSTANCE = "substance"
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
        all_resources = [
            # Smart Materials (representative subset of real SP 10.0.1)
            MockResource("Steel", "smartmaterial"),
            MockResource("Copper", "smartmaterial"),
            MockResource("Gold Armor", "smartmaterial"),
            MockResource("Aluminium Anodized Red", "smartmaterial"),
            MockResource("Bronze Corroded", "smartmaterial"),
            MockResource("Leather Rough", "smartmaterial"),
            MockResource("Plastic Matte", "smartmaterial"),
            MockResource("Wood Walnut", "smartmaterial"),
            # Smart Masks (representative subset of real SP 10.0.1)
            MockResource("Dirt", "smartmask"),
            MockResource("Dust", "smartmask"),
            MockResource("Rust", "smartmask"),
            MockResource("Edge Damage", "smartmask"),
            MockResource("Edges Scratched", "smartmask"),
            MockResource("Surface Worn", "smartmask"),
            MockResource("Paint Damaged", "smartmask"),
            MockResource("Moisture", "smartmask"),
            # Regular Materials (SUBSTANCE type, representative subset)
            MockResource("Carbon Fiber", "substance"),
            MockResource("Concrete Raw", "substance"),
            MockResource("Fabric Felt", "substance"),
            MockResource("Leather Grain", "substance"),
            MockResource("Metal Rust", "substance"),
            MockResource("Plastic Glossy", "substance"),
            MockResource("Wood Bark", "substance"),
            # Environments
            MockResource("Studio", "environment"),
            MockResource("Sunrise", "environment"),
            MockResource("Night", "environment"),
        ]
        if not query:
            return all_resources
        return [r for r in all_resources if query.lower() in r._name.lower()]

    resource.search = resource_search
    resource.ResourceID = MockResourceID

    # ── Mock ctypes.windll.user32 (for Computer Use) ──
    import ctypes as _real_ctypes
    _ctypes_state = {"pos": (500, 400), "fg_hwnd": None}

    class _MockUser32:
        @staticmethod
        def GetCursorPos(buf):
            import struct
            struct.pack_into("ll", buf, 0, _ctypes_state["pos"][0], _ctypes_state["pos"][1])
        @staticmethod
        def SetCursorPos(x, y):
            _ctypes_state["pos"] = (x, y)
        @staticmethod
        def mouse_event(flags, x, y, data, extra):
            pass
        @staticmethod
        def keybd_event(vk, scan, flags, extra):
            pass
        @staticmethod
        def GetSystemMetrics(idx):
            return {0: 1920, 1: 1080}.get(idx, 0)
        @staticmethod
        def VkKeyScanW(ch):
            return ch
        @staticmethod
        def SetForegroundWindow(hwnd):
            _ctypes_state["fg_hwnd"] = hwnd
        @staticmethod
        def FindWindowW(cls, title):
            return 12345
        @staticmethod
        def GetWindowRect(hwnd, buf):
            import struct
            struct.pack_into("iiii", buf, 0, 0, 0, 1920, 1080)
        @staticmethod
        def GetDC(hwnd):
            return 1
        @staticmethod
        def ReleaseDC(hwnd, dc):
            return 1
        @staticmethod
        def PrintWindow(hwnd, dc, flags):
            return 1

    _real_ctypes.windll.user32 = _MockUser32()

    class _MockGdi32:
        @staticmethod
        def CreateCompatibleDC(hdc):
            return 2
        @staticmethod
        def CreateCompatibleBitmap(hdc, w, h):
            return 3
        @staticmethod
        def SelectObject(hdc, obj):
            return obj
        @staticmethod
        def GetDIBits(hdc, bmp, start, count, buf, bmi, usage):
            # Fill with white pixels (BGRA: 0xFF, 0xFF, 0xFF, 0xFF)
            import struct
            for i in range(0, len(buf), 4):
                struct.pack_into("BBBB", buf, i, 255, 255, 255, 255)
            return count
        @staticmethod
        def DeleteObject(obj):
            return 1
        @staticmethod
        def DeleteDC(hdc):
            return 1

    _real_ctypes.windll.gdi32 = _MockGdi32()

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

    # QPoint mock
    class _MockQPoint:
        def __init__(self, x, y): self._x = x; self._y = y
        def x(self): return self._x
        def y(self): return self._y
    pyside2_core.QPoint = _MockQPoint

    # QRect mock
    class _MockQRect:
        def __init__(self, *args):
            if len(args) == 4:
                self._x, self._y, self._w, self._h = args
            else:
                self._x = self._y = self._w = self._h = 0
        def x(self): return self._x
        def y(self): return self._y
        def width(self): return self._w
        def height(self): return self._h
        def adjusted(self, a, b, c, d):
            return _MockQRect(self._x + a, self._y + b, self._w - a - c, self._h - b - d)
    pyside2_core.QRect = _MockQRect

    # QBuffer / QIODevice mock for viewport capture
    class _FakeBuffer:
        def __init__(self): self._data = b""
        def open(self, mode): pass
        def write(self, data): self._data = data
        def data(self): return self._data
    pyside2_core.QBuffer = _FakeBuffer
    pyside2_core.QIODevice = type('QIODevice', (), {'WriteOnly': 0})
    pyside2_core.Qt = type('Qt', (), {
        'AlignCenter': 0x0084,
        'ToolTip': 0x0000000D,
        'FramelessWindowHint': 0x00000800,
        'WindowStaysOnTopHint': 0x00040000,
    })

    pyside2_gui = types.ModuleType("PySide2.QtGui")

    class _MockQImage:
        Format_ARGB32 = 5
        def __init__(self, data, w, h, fmt):
            self._data = data; self._w = w; self._h = h
        def width(self): return self._w
        def height(self): return self._h

    class _MockQPixmap:
        def __init__(self):
            self._data = b""; self._w = 0; self._h = 0
        @staticmethod
        def fromImage(img):
            pm = _MockQPixmap()
            pm._data = img._data; pm._w = img._w; pm._h = img._h
            return pm
        def save(self, path, fmt):
            import struct
            with open(path, 'wb') as f:
                # Minimal valid PNG
                f.write(b"\x89PNG\r\n\x1a\n")
                f.write(b"\x00" * 64)

    pyside2_gui.QImage = _MockQImage
    pyside2_gui.QPixmap = _MockQPixmap
    pyside2.QtGui = pyside2_gui

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
        def setObjectName(self, n): self._name = n
        def width(self): return getattr(self, '_w', 0) or getattr(self, '_geo_w', 100)
        def height(self): return getattr(self, '_h', 0) or getattr(self, '_geo_h', 30)
        def show(self): pass
        def hide(self): pass
        def move(self, x, y): pass
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
        def __init__(self, name="", parent=None, enabled=True, shortcut=""):
            super().__init__(name, parent)
            self._text = name
            self._enabled = enabled
            self._shortcut = shortcut
        def text(self): return self._text
        def isEnabled(self): return self._enabled
        def trigger(self): pass
        def shortcut(self):
            class _MockShortcut:
                def __init__(self, s): self._s = s
                def toString(self): return self._s
            return _MockShortcut(self._shortcut)

    class _MockQDockWidget(_MockWidget):
        def __init__(self, name="", parent=None):
            super().__init__(name, parent)
            self._widget = None
        def widget(self): return self._widget
        def setWidget(self, w): self._widget = w

    class _MockQMainWindow(_MockWidget):
        def __init__(self):
            super().__init__("S4MainWindow")
            self._geo_x = 0
            self._geo_y = 23
            self._geo_w = 1920
            self._geo_h = 1017
            self._minimized = False
            self._maximized = True
            self._fullscreen = False
            self._visible = True
            self._active = True
            self._win_title = "Adobe Substance 3D Painter"
        def geometry(self):
            class _QRect:
                def __init__(self): pass
                def x(self): return self._x
                def y(self): return self._y
                def width(self): return self._w
                def height(self): return self._h
                def adjusted(self, a, b, c, d):
                    r2 = _QRect()
                    r2._x = self._x + a; r2._y = self._y + b
                    r2._w = self._w - a - c; r2._h = self._h - b - d
                    return r2
            r = _QRect()
            r._x = self._geo_x; r._y = self._geo_y
            r._w = self._geo_w; r._h = self._geo_h
            return r
        def width(self): return self._geo_w
        def height(self): return self._geo_h
        def x(self): return self._geo_x
        def y(self): return self._geo_y
        def isMinimized(self): return self._minimized
        def isMaximized(self): return self._maximized
        def isFullScreen(self): return self._fullscreen
        def isVisible(self): return self._visible
        def isActiveWindow(self): return self._active
        def windowTitle(self): return self._win_title
        def setWindowTitle(self, t): self._win_title = t
        def mapToGlobal(self, qpoint):
            qx = qpoint.x() if hasattr(qpoint, 'x') else 0
            qy = qpoint.y() if hasattr(qpoint, 'y') else 0
            class _Pt:
                def __init__(self, x, y): self._x, self._y = x, y
                def x(self): return self._x
                def y(self): return self._y
            return _Pt(qx + self._geo_x, qy + self._geo_y)
        def grab(self, rect=None):
            class _FakePixmap:
                def __init__(self, w, h):
                    self._w = w; self._h = h
                def width(self): return self._w
                def height(self): return self._h
                def save(self, path, fmt):
                    with open(path, 'wb') as f:
                        f.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
            if rect and hasattr(rect, '_w'):
                return _FakePixmap(rect._w, rect._h)
            return _FakePixmap(self._geo_w, self._geo_h)
        def showMinimized(self): self._minimized = True; self._maximized = False
        def showMaximized(self): self._minimized = False; self._maximized = True
        def showFullScreen(self): self._fullscreen = True
        def showNormal(self): self._minimized = False; self._maximized = False; self._fullscreen = False
        def hide(self): self._visible = False
        def show(self): self._visible = True
        def activateWindow(self): self._active = True
        def raise_(self): pass
        def winId(self): return 12345
        def lower(self): pass
        def resize(self, w, h): self._geo_w = w; self._geo_h = h
        def move(self, x, y): self._geo_x = x; self._geo_y = y
        def menuBar(self): return _MockWidget("menubar", self)

    pyside2_widgets.QWidget = _MockWidget
    pyside2_widgets.QLineEdit = _MockQLineEdit
    pyside2_widgets.QSpinBox = _MockQSpinBox
    pyside2_widgets.QComboBox = _MockQComboBox
    pyside2_widgets.QAction = _MockQAction
    pyside2_widgets.QDockWidget = _MockQDockWidget
    pyside2_widgets.QMainWindow = _MockQMainWindow

    class _MockQLabel(_MockWidget):
        def __init__(self, text="", parent=None):
            if parent is None and isinstance(text, _MockWidget):
                parent, text = text, ""
            # If parent is provided, first arg is the widget name; else it's label text
            if parent is not None and isinstance(text, str) and text:
                super().__init__(text, parent)
                self._text = ""
            else:
                super().__init__("QLabel", parent)
                self._text = text if isinstance(text, str) else ""
        def setText(self, t): self._text = t
        def text(self): return self._text
        def setAlignment(self, a): pass
        def adjustSize(self): pass
        def raise_(self): pass
        def deleteLater(self): pass
        def setStyleSheet(self, s): self._stylesheet = s
        def styleSheet(self): return getattr(self, '_stylesheet', '')
    pyside2_widgets.QLabel = _MockQLabel
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
                def save(self, buf, fmt):
                    # 写入假 PNG 数据，使 base64 编码测试通过
                    buf.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
            return FakePixmap(self._w, self._h)

    pyside2_widgets.QOpenGLWidget = _MockQOpenGLWidget

    # QOpenGLWidget mock for PySide2.QtOpenGLWidgets import path
    pyside2_gl = types.ModuleType("PySide2.QtOpenGLWidgets")
    pyside2_gl.QOpenGLWidget = _MockQOpenGLWidget
    sys.modules["PySide2.QtOpenGLWidgets"] = pyside2_gl

    sys.modules["PySide2"] = pyside2
    sys.modules["PySide2.QtCore"] = pyside2_core
    sys.modules["PySide2.QtGui"] = pyside2_gui
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
    _MockQLabel("iterationsLabel", _iray_panel)
    _MockQLabel("timeLabel", _iray_panel)

    # Iray QAction
    _iray_action = _MockQAction("Rendering (Iray)", enabled=True)
    _iray_action.setParent(_mock_main_window)

    # Undo/Redo QActions
    _undo_action = _MockQAction("UNDO", enabled=True, shortcut="Ctrl+Z")
    _undo_action.setParent(_mock_main_window)
    _redo_action = _MockQAction("REDO", enabled=True, shortcut="Ctrl+Y")
    _redo_action.setParent(_mock_main_window)

    # Mock QUndoView + QUndoStack for undo/redo
    class _MockQUndoStack:
        def __init__(self):
            self._can_undo = False
            self._can_redo = False
            self._count = 0
        def canUndo(self): return self._can_undo
        def canRedo(self): return self._can_redo
        def count(self): return self._count
        def undo(self):
            self._can_undo = False
            self._can_redo = True
        def redo(self):
            self._can_redo = False
            self._can_undo = True
        def push(self, cmd):
            self._count += 1
            self._can_undo = True
            self._can_redo = False

    class _MockQUndoView(_MockWidget):
        def __init__(self, name="", parent=None):
            super().__init__(name, parent)
            self._stack = _MockQUndoStack()
        def stack(self): return self._stack

    pyside2_widgets.QUndoStack = _MockQUndoStack
    pyside2_widgets.QUndoView = _MockQUndoView

    _mock_undo_view = _MockQUndoView("history", _mock_main_window)

    # Mock QOpenGLWidget (viewport)
    _mock_viewport = _MockQOpenGLWidget("Viewer3D", _mock_main_window)

    def _mock_get_main_window():
        return _mock_main_window

    ui.get_main_window = _mock_get_main_window

    # ── 注册到 sys.modules ──
    sp.application   = app
    sp.ui            = ui
    sp.layerstack    = layerstack
    sp.colormanagement = colormanagement
    sp.textureset    = textureset
    sp.undo          = undo_mod
    sp.project       = project_mod
    sp.display       = display_mod
    sp.js            = js_mod
    sp.export        = export
    sp.resource      = resource

    sys.modules["substance_painter"]            = sp
    sys.modules["substance_painter.application"] = app
    sys.modules["substance_painter.ui"]         = ui
    sys.modules["substance_painter.logging"]    = logging_mod
    sys.modules["substance_painter.layerstack"]  = layerstack
    sys.modules["substance_painter.colormanagement"] = colormanagement
    sys.modules["substance_painter.textureset"]  = textureset
    sys.modules["substance_painter.undo"]        = undo_mod
    sys.modules["substance_painter.project"]     = project_mod
    sys.modules["substance_painter.display"]     = display_mod
    sys.modules["substance_painter.js"]          = js_mod
    sys.modules["substance_painter.export"]      = export
    sys.modules["substance_painter.resource"]    = resource

    return sp, layerstack


SP_MOCK, LAYERS_MOCK = _make_sp_mock()


@pytest.fixture
def fresh_layer_stack():
    import substance_painter.layerstack as ls
    ls._build_default_stack()
    # Reset mock undo stack state
    from PySide2.QtWidgets import QUndoView
    from substance_painter.ui import get_main_window
    main_win = get_main_window()
    if main_win:
        undo_view = main_win.findChild(QUndoView, "history")
        if undo_view:
            stack = undo_view.stack()
            stack._can_undo = False
            stack._can_redo = False
            stack._count = 0
    # Reset CU banner state
    from plugin.sp_bridge import handlers as _h
    _h._cu_banner = None
    yield ls._root_nodes


@pytest.fixture
def bridge_url():
    return "http://localhost:27182"
