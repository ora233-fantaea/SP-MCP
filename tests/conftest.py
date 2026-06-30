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

    class _EnumMeta(type):
        def __iter__(cls):
            for k, v in cls.__dict__.items():
                if not k.startswith("_") and isinstance(v, _Enum):
                    yield v

    class _Enum(metaclass=_EnumMeta):
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
        Emissive   = _Enum("Emissive")
        Specular   = _Enum("Specular")
        Opacity    = _Enum("Opacity")
        AO         = _Enum("AO")   # 真实 SP 用 AO，不是 AmbientOcclusion
        Scattering = _Enum("Scattering")
        Translucency = _Enum("Translucency")

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
            self._mask_background = None
            self._content_effects = []   # content 栈中的 effect（用于克隆告警测试）
            self._mask_effects = []      # mask 栈中的 effect
            self._material_source = None
            self._source_mode = None

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
            self._mask_background = background

        def has_mask(self):
            return self._has_mask

        def get_mask_background(self):
            return self._mask_background

        def content_effects(self):
            return list(self._content_effects)

        def mask_effects(self):
            return list(self._mask_effects)

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
            "has_mask": has_mask, "get_mask_background": get_mask_background,
            "content_effects": content_effects, "mask_effects": mask_effects,
            "get_parent": get_parent, "get_next_sibling": get_next_sibling,
            "get_previous_sibling": get_previous_sibling,
            "source_mode": property(lambda self: self._source_mode),
            "get_material_source": lambda self: self._material_source,
            "active_channels": property(lambda self: list(self._sources.keys())),
        }
        return type(class_name, (), ns)

    MockNode = _make_node_class("FillLayerNode")
    MockGroupNode = _make_node_class("GroupLayerNode")
    MockPaintNode = _make_node_class("PaintLayerNode")

    class MockStack:
        # 模拟 pybind11 的 Stack：按 stack_id 值相等（而非对象 identity）。
        # 真实 SP 每次 get_stack()/get_active_stack() 返回不同包装对象但指向
        # 同一底层 stack，==True / is False。让 mock 也如此，才能守住 handler
        # 里「必须用 == 不能用 is」这条（见 set_texture_set_resolution 回归）。
        def __init__(self, stack_id=0):
            self.stack_id = stack_id
        def __eq__(self, other):
            return isinstance(other, MockStack) and self.stack_id == other.stack_id
        def __hash__(self):
            return hash(("MockStack", self.stack_id))

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

    # Global node registry — 用于 lookup 所有节点（含效果节点）
    _node_registry = {}

    def _get_node_by_uid(uid):
        """递归搜索所有节点（根 + 子节点）+ 效果节点注册表。"""
        # 先检查全局注册表
        if uid in _node_registry:
            return _node_registry[uid]
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
    layerstack._node_registry = _node_registry

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

    # ── substance_painter.source ──
    source_mod = types.ModuleType("substance_painter.source")

    class SourceMode(_Enum):
        Split  = _Enum("Split")
        Material = _Enum("Material")

    class MockResourceID:
        def __init__(self, name, ctx="user"):
            self.context = ctx
            self.name = name
            self.version = "1.0"
        def url(self):
            return f"resource://{self.context}/{self.name}"

    # Re-use the existing MockColor from colormanagement
    _MockCMColor = MockCMColor  # alias for color helper

    class SourceSubstance:
        def __init__(self, resource_name="mock_substance"):
            self._params = {"scale": 1.0, "dirt_level": 0.5, "wear_amount": 0.2}
            self._props = {}
            self._outputs = ["output", "roughness", "metallic"]
            self._inputs = ["height", "mask"]
            self._active_output = "output"
            self._mask_output = None
            self._resource_id = MockResourceID(resource_name)
            self._presets = ["Default", "Worn", "Polished", "Rusty"]
            self._mapping = {}
        @property
        def resource_id(self):
            return self._resource_id
        def get_parameters(self):
            return {k: PropertyValue(v) for k, v in self._params.items()}
        def set_parameters(self, params):
            for k, v in params.items():
                self._params[k] = v.value() if hasattr(v, 'value') else v
        def get_properties(self):
            return {k: Property(k, v) for k, v in self._params.items()}
        def get_preset_list(self):
            return list(self._presets)
        def apply_preset(self, name):
            if name not in self._presets:
                raise ValueError(f"Preset {name!r} not found")
        @property
        def image_inputs(self):
            return list(self._inputs)
        @property
        def image_outputs(self):
            return list(self._outputs)
        @property
        def active_output(self):
            return self._active_output
        @active_output.setter
        def active_output(self, v):
            if v not in self._outputs:
                raise ValueError(f"Output {v!r} not found")
            self._active_output = v
        @property
        def mask_output(self):
            return self._mask_output
        @mask_output.setter
        def mask_output(self, v):
            self._mask_output = v
        @property
        def output_mapping(self):
            return dict(self._mapping)

    class SourceUniformColor:
        def __init__(self, r=0.5, g=0.5, b=0.5):
            self._color = MockCMColor(r, g, b)
        def get_color(self):
            return self._color

    class SourceBitmap:
        def __init__(self, resource_name="mock_bitmap"):
            self._resource_id = MockResourceID(resource_name) if resource_name else None
            self._color_space = _Enum("sRGB")
        @property
        def resource_id(self):
            return self._resource_id
        def get_color_space(self):
            return self._color_space

    class SourceReference:
        def __init__(self):
            self._anchor = None
            self._alpha_matte = _Enum("Disabled")
        @property
        def anchor(self):
            return self._anchor
        @property
        def alpha_matte(self):
            return self._alpha_matte

    class SourceFont:
        def __init__(self, resource_name="mock_font"):
            self._resource_id = MockResourceID(resource_name)
            self._params = _FontParams()
        @property
        def resource_id(self):
            return self._resource_id
        def get_parameters(self):
            return self._params

    class _FontParams:
        def __init__(self):
            self.text = "Sample"
            self.size = 24

    class SourceVectorial:
        def __init__(self, resource_name="mock_svg"):
            self._resource_id = MockResourceID(resource_name)
        @property
        def resource_id(self):
            return self._resource_id
        def get_parameters(self):
            return _VectorialParams()

    class _VectorialParams:
        def __init__(self):
            self.artboard_id = "default"
            self.scope = "fill"

    # 分辨率相关枚举
    class FontResolutionMode(_Enum):
        Absolute = _Enum("Absolute")
        Relative = _Enum("Relative")

    class VectorialResolutionMode(_Enum):
        Static = _Enum("Static")
        Dynamic = _Enum("Dynamic")

    source_mod.SourceMode = SourceMode
    source_mod.SourceSubstance = SourceSubstance
    source_mod.SourceUniformColor = SourceUniformColor
    source_mod.SourceBitmap = SourceBitmap
    source_mod.SourceReference = SourceReference
    source_mod.SourceFont = SourceFont
    source_mod.SourceVectorial = SourceVectorial
    source_mod.FontResolutionMode = FontResolutionMode
    source_mod.VectorialResolutionMode = VectorialResolutionMode
    source_mod.MockResourceID = MockResourceID

    # ── substance_painter.properties ──
    properties_mod = types.ModuleType("substance_painter.properties")

    class PropertyValue:
        def __init__(self, value):
            if isinstance(value, PropertyValue):
                value = value._value
            self._value = value
        def value(self):
            return self._value
        def __repr__(self):
            return f"PropertyValue({self._value!r})"

    class Property:
        def __init__(self, name, value):
            self._name = name
            self._value = value
        def type(self):
            return _Enum("Float1")
        def description(self):
            return f"Parameter: {self._name}"
        def value(self):
            return PropertyValue(self._value)

    properties_mod.PropertyValue = PropertyValue
    properties_mod.Property = Property

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
        def set_resolution(self, new_resolution):
            # 实机（SP 10.0.1）：set_resolution 接受单个 Resolution 对象，
            # 而非 (width, height)。mock 同步该签名，逼出 handler 误传两参数。
            self._resolution = MockResolution(new_resolution.width,
                                              new_resolution.height)
        def get_stack(self):
            # 每次返回新包装对象（== 按 stack_id 相等，is 为 False），
            # 精确模拟 pybind11，逼出 handler 里误用 is 的 bug。
            return MockStack(stack_id=self._stack.stack_id)
        @property
        def material_id(self):
            return self._id

    _mock_texture_sets = [
        MockTextureSet(1, "Default"),
        MockTextureSet(2, "MetalParts"),
    ]
    # 真实 SP 里活动 stack 必属于某个纹理集。让 "Default" 纹理集的 stack_id 与
    # 全局活动 stack 一致，使 get_active_stack() 能按值（==）匹配到它；但二者是
    # 不同的 Python 包装对象（is 为 False），从而守住「必须用 == 不能用 is」。
    _mock_texture_sets[0]._stack = MockStack(stack_id=_mock_stack.stack_id)

    textureset.get_active_stack = lambda: MockStack(stack_id=_mock_stack.stack_id)
    textureset.set_active_stack = lambda stack: None
    textureset.all_texture_sets = lambda: list(_mock_texture_sets)
    # 实机有 textureset.Resolution(width, height)；set_resolution 收它。
    textureset.Resolution = MockResolution
    textureset.Stack = MockStack
    textureset.Resolution = MockResolution
    # Add from_name static method to MockTextureSet
    @staticmethod
    def _ts_from_name(name):
        for ts in _mock_texture_sets:
            if ts.name() == name:
                return ts
        return MockTextureSet(99, name)
    MockTextureSet.from_name = _ts_from_name
    textureset.TextureSet = MockTextureSet  # Alias for handler compatibility
    textureset._mock_texture_sets = _mock_texture_sets

    # ── substance_painter.display ──
    display_mod = types.ModuleType("substance_painter.display")

    class ToneMappingFunction(_Enum):
        Linear = _Enum("Linear")
        ACES   = _Enum("ACES")

    class MockCameraFull:
        _position = [0.0, 0.0, 5.0]
        _rotation = [0.0, 0.0, 0.0]
        _fov = 45.0
        _focal_length = 50.0
        _focus_distance = 100.0
        _aperture = 2.8
        _orthographic_height = 10.0
        _projection_type = _Enum("Perspective")
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
        @property
        def focal_length(self): return self._focal_length
        @focal_length.setter
        def focal_length(self, v): self._focal_length = v
        @property
        def focus_distance(self): return self._focus_distance
        @focus_distance.setter
        def focus_distance(self, v): self._focus_distance = v
        @property
        def aperture(self): return self._aperture
        @aperture.setter
        def aperture(self, v): self._aperture = v
        @property
        def orthographic_height(self): return self._orthographic_height
        @orthographic_height.setter
        def orthographic_height(self, v): self._orthographic_height = v
        @property
        def projection_type(self): return self._projection_type
        @projection_type.setter
        def projection_type(self, v): self._projection_type = v

    _mock_camera = MockCameraFull()
    display_mod.Camera = type("Camera", (), {
        "get_default_camera": staticmethod(lambda: _mock_camera),
    })
    display_mod.ToneMappingFunction = ToneMappingFunction
    display_mod._mock_camera = _mock_camera

    _mock_tone_mapping = ToneMappingFunction.Linear
    def _get_tone_mapping():
        return _mock_tone_mapping
    def _set_tone_mapping(tm):
        nonlocal _mock_tone_mapping
        _mock_tone_mapping = tm
    display_mod.get_tone_mapping = _get_tone_mapping
    display_mod.set_tone_mapping = _set_tone_mapping

    _mock_color_lut_resource = None
    def _get_color_lut_resource():
        return _mock_color_lut_resource
    def _set_color_lut_resource(rid):
        nonlocal _mock_color_lut_resource
        _mock_color_lut_resource = rid
    display_mod.get_color_lut_resource = _get_color_lut_resource
    display_mod.set_color_lut_resource = _set_color_lut_resource

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

    # 真实 SP 10.0.1：没有 ExportConfig 类；export_project_textures 接受 JSON
    # dict 配置，返回值的 .textures 是 {stack: [files]} 的 dict（非列表），
    # 且带 .status（ExportStatus 枚举）。mock 同步这些，逼出 handler 误用。
    class _ExportStatus:
        Success = type("ExportStatus", (), {"name": "Success"})()

    class ExportResult:
        def __init__(self):
            self.textures = {
                "Default": ["/tmp/export/BaseColor.png",
                            "/tmp/export/Roughness.png",
                            "/tmp/export/Metallic.png",
                            "/tmp/export/Normal.png"],
            }
            self.status = _ExportStatus.Success

    def _export_project_textures(json_config):
        # 校验传入的是 dict 配置（不是 ExportConfig 对象），并含必需键。
        assert isinstance(json_config, dict), "export config must be a JSON dict"
        assert "exportPath" in json_config
        assert "defaultExportPreset" in json_config
        return ExportResult()

    export.export_project_textures = _export_project_textures
    export.ExportStatus = _ExportStatus

    # 导出预设经 export 模块列出（不在 resource.search 里）。
    # PredefinedExportPreset 有 .name + .url（字符串属性）；
    # ResourceExportPreset 有 .resource_id（带 .url() 方法 + .name）。
    class _PredefPreset:
        def __init__(self, name):
            self.name = name
            self.url = f"export-preset-generator://{name.replace(' ', '').lower()}"
    class _ResPreset:
        def __init__(self, name): self.resource_id = MockResourceID(name)
    export.list_predefined_export_presets = lambda: [
        _PredefPreset("PBR Metallic Roughness"), _PredefPreset("2D View")]
    export.list_resource_export_presets = lambda: [
        _ResPreset("Unity HD Render Pipeline"), _ResPreset("Unreal Engine 4")]

    # ── substance_painter.resource ──
    resource = types.ModuleType("substance_painter.resource")

    # 真实 SP 10.0.1: Type 只有这些粗类（不含 FILTER/GENERATOR/TEXTURE/ENVIRONMENT）。
    class ResourceType:
        SMART_MATERIAL = "smartmaterial"
        SMART_MASK = "smartmask"
        SUBSTANCE = "substance"
        FONT = "font"
        IMAGE = "image"
        PRESET = "preset"
        SHADER = "shader"
        SCRIPT = "script"
        BRUSH = "brush"
    resource.Type = ResourceType

    class MockResourceID:
        def __init__(self, name, ctx="user"):
            self.name = name
            self.context = ctx
            self.version = "1.0"
        def url(self):
            return f"resource://{self.context}/{self.name}"

    class MockResource:
        # res_type 是粗类（Type）；usages 是用途列表（Usage），与真实 API 一致：
        # 用途概念（filter/generator/texture/environment）在 usages() 里。
        def __init__(self, name, res_type="smartmaterial", usages=None):
            self._name = name
            self._type = res_type
            self._usages = usages if usages is not None else [res_type]
            self._id = MockResourceID(name)
        def gui_name(self):
            return self._name
        def identifier(self):
            return self._id
        def type(self):
            return self._type
        def usages(self):
            return list(self._usages)

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
            # Regular Materials (SUBSTANCE type, usage=PROCEDURAL)
            MockResource("Carbon Fiber", "substance", ["procedural"]),
            MockResource("Concrete Raw", "substance", ["procedural"]),
            MockResource("Fabric Felt", "substance", ["procedural"]),
            MockResource("Leather Grain", "substance", ["procedural"]),
            MockResource("Metal Rust", "substance", ["procedural"]),
            MockResource("Plastic Glossy", "substance", ["procedural"]),
            MockResource("Wood Bark", "substance", ["procedural"]),
            # Filters / Generators / Textures (Type=SUBSTANCE/IMAGE, usage 区分用途)
            MockResource("Blur", "substance", ["filter"]),
            MockResource("Sharpen", "substance", ["filter"]),
            MockResource("Metal Edge Wear", "substance", ["generator"]),
            MockResource("Dirt Generator", "substance", ["generator"]),
            MockResource("Grunge Map 001", "image", ["texture"]),
            MockResource("Noise Fractal", "image", ["texture"]),
            # Environments (Type=IMAGE, usage=ENVIRONMENT)
            MockResource("Studio", "image", ["environment"]),
            MockResource("Sunrise", "image", ["environment"]),
            MockResource("Night", "image", ["environment"]),
        ]
        if not query:
            return all_resources
        return [r for r in all_resources if query.lower() in r._name.lower()]

    resource.search = resource_search
    resource.ResourceID = MockResourceID

    # 真实 SP 10.0.1 的 Usage 枚举成员（用途概念在此，而非 Type）。
    class ResourceUsage:
        ALPHA = "alpha"
        BASE_MATERIAL = "base_material"
        BRUSH = "brush"
        COLOR_LUT = "color_lut"
        ENVIRONMENT = "environment"
        EXPORT = "export"
        FILTER = "filter"
        FONT = "font"
        GENERATOR = "generator"
        PROCEDURAL = "procedural"
        SHADER = "shader"
        SMART_MASK = "smartmask"
        SMART_MATERIAL = "smartmaterial"
        TEXTURE = "texture"
    resource.Usage = ResourceUsage

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
        def copy(self, x=None, y=None, w=None, h=None):
            # 无参 copy() → 整图副本；带参 → 裁剪区域副本
            if w is None or h is None:
                return _MockQImage(self._data, self._w, self._h, self.Format_ARGB32)
            return _MockQImage(self._data, w, h, self.Format_ARGB32)

    class _MockQPixmap:
        def __init__(self):
            self._data = b""; self._w = 0; self._h = 0
        @staticmethod
        def fromImage(img):
            pm = _MockQPixmap()
            pm._data = img._data; pm._w = img._w; pm._h = img._h
            return pm
        def width(self): return self._w
        def height(self): return self._h
        def save(self, target, fmt):
            png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
            # target 可以是文件路径(str)或 QBuffer(有 write 方法)
            if hasattr(target, "write"):
                target.write(png)
            else:
                with open(target, 'wb') as f:
                    f.write(png)

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
    sp.source        = source_mod
    sp.properties    = properties_mod

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
    sys.modules["substance_painter.source"]      = source_mod
    sys.modules["substance_painter.properties"]  = properties_mod

    # ── substance_painter.levels (new mock) ──
    levels_mod = types.ModuleType("substance_painter.levels")

    class MockLevelsChannel:
        def __init__(self, in_low=0.0, in_mid=0.5, in_high=1.0,
                     out_low=0.0, out_high=1.0, gamma=1.0, clamp=False):
            self.in_low = in_low
            self.in_mid = in_mid
            self.in_high = in_high
            self.out_low = out_low
            self.out_high = out_high
            self.gamma = gamma
            self.clamp = clamp

    class MockLevelsParamsMono:
        def __init__(self):
            self.mono = MockLevelsChannel()

    class MockLevelsParamsRGB:
        def __init__(self):
            self.red = MockLevelsChannel()
            self.green = MockLevelsChannel()
            self.blue = MockLevelsChannel()

    levels_mod.LevelsParamsMono = MockLevelsParamsMono
    levels_mod.LevelsParamsRGB = MockLevelsParamsRGB
    sp.levels = levels_mod
    sys.modules["substance_painter.levels"] = levels_mod

    # ── substance_painter.textureset extensions (MeshMapUsage, UVTile) ──
    class MeshMapUsage(_Enum):
        AO         = _Enum("AO")
        Curvature  = _Enum("Curvature")
        Normal     = _Enum("Normal")
        Height     = _Enum("Height")
        ID         = _Enum("ID")
        Opacity    = _Enum("Opacity")
        Position   = _Enum("Position")
        Thickness  = _Enum("Thickness")
        WorldSpaceNormal = _Enum("WorldSpaceNormal")
        BentNormals = _Enum("BentNormals")

    textureset.MeshMapUsage = MeshMapUsage

    class MockUVTile:
        def __init__(self, u=0, v=0, material_id=0):
            self.u = u
            self.v = v
            self._material_id = material_id
        @staticmethod
        def _belong_to_texture_set(tiles, material_id):
            return True
    textureset.UVTile = MockUVTile

    # Add uv_tile method to MockTextureSet
    def _ts_uv_tile(self, u, v):
        return MockUVTile(u, v, self.material_id)
    MockTextureSet.uv_tile = _ts_uv_tile

    # Add Channel.is_color() mock
    class MockChannel:
        def __init__(self, is_color=True):
            self._is_color = is_color
        def is_color(self):
            return self._is_color

    textureset.Channel = MockChannel

    # ── substance_painter.layerstack extensions (effect nodes, selection) ──
    class NodeStack:
        Content  = "Content"
        Mask     = "Mask"
        Substack = "Substack"

    layerstack.NodeStack = NodeStack

    # Effect node classes
    def _make_effect_node_class(class_name):
        """创建效果节点 mock。"""
        def __init__(self, uid_or_name):
            if isinstance(uid_or_name, int):
                self._uid = uid_or_name
                self._name = f"{class_name}_{uid_or_name}"
            else:
                self._uid = 0
                self._name = uid_or_name or class_name
            self._source = None
            self._params = None
            self._affected_channel = ChannelType.BaseColor
            self._stack_obj = None
            self._parent = None
            self._children = []

        def uid(self):
            return self._uid

        def get_name(self):
            return self._name

        def set_name(self, v):
            self._name = v

        def get_stack(self):
            return self._stack_obj

        ns = {"__init__": __init__, "uid": uid, "get_name": get_name,
              "set_name": set_name, "get_stack": get_stack}
        return type(class_name, (), ns)

    FilterEffectNode = _make_effect_node_class("FilterEffectNode")
    GeneratorEffectNode = _make_effect_node_class("GeneratorEffectNode")
    LevelsEffectNode = _make_effect_node_class("LevelsEffectNode")
    CompareMaskEffectNode = _make_effect_node_class("CompareMaskEffectNode")
    ColorSelectionEffectNode = _make_effect_node_class("ColorSelectionEffectNode")
    AnchorPointEffectNode = _make_effect_node_class("AnchorPointEffectNode")

    # Add effect-specific methods
    def _filter_gen_get_source(self):
        return self._source
    def _filter_gen_set_source(self, source):
        self._source = source
        return source
    FilterEffectNode.get_source = _filter_gen_get_source
    FilterEffectNode.set_source = _filter_gen_set_source
    GeneratorEffectNode.get_source = _filter_gen_get_source
    GeneratorEffectNode.set_source = _filter_gen_set_source

    def _levels_get_params(self):
        if self._params is None:
            self._params = MockLevelsParamsMono()
        return self._params
    def _levels_set_params(self, params):
        self._params = params
    LevelsEffectNode.get_parameters = _levels_get_params
    LevelsEffectNode.set_parameters = _levels_set_params
    LevelsEffectNode.affected_channel = property(
        lambda self: self._affected_channel,
        lambda self, v: setattr(self, '_affected_channel', v))

    # CompareMaskEffectOperand and CompareMaskEffectOperation
    class CompareMaskEffectOperand(_Enum):
        Source         = _Enum("Source")
        Target         = _Enum("Target")
        CurrentState   = _Enum("CurrentState")
        Constant       = _Enum("Constant")

    class CompareMaskEffectOperation(_Enum):
        Equal           = _Enum("Equal")
        NotEqual        = _Enum("NotEqual")
        Greater         = _Enum("Greater")
        Less            = _Enum("Less")
        GreaterOrEqual   = _Enum("GreaterOrEqual")
        LessOrEqual      = _Enum("LessOrEqual")
        WithinTolerance = _Enum("WithinTolerance")

    class MockCompareMaskParams:
        def __init__(self):
            self.channel = ChannelType.BaseColor
            self.left_operand = CompareMaskEffectOperand.Source
            self.right_operand = CompareMaskEffectOperand.Target
            self.operation = CompareMaskEffectOperation.Equal
            self.constant = 0.5
            self.tolerance = 0.1
            self.hardness = 0.5

    def _compare_get_params(self):
        if self._params is None:
            self._params = MockCompareMaskParams()
        return self._params
    def _compare_set_params(self, params):
        self._params = params
    CompareMaskEffectNode.get_parameters = _compare_get_params
    CompareMaskEffectNode.set_parameters = _compare_set_params

    # ColorSelection
    class ColorSelectionBackgroundColor(_Enum):
        Black = _Enum("Black")
        White = _Enum("White")
        Transparent = _Enum("Transparent")

    class MockColorSelectionParams:
        def __init__(self):
            self.id_mask = None
            self.output_value = 1.0
            self.hardness = 0.5
            self.tolerance = 0.1
            self.background_color = ColorSelectionBackgroundColor.Black
            self.colors = []

    def _color_sel_get_params(self):
        if self._params is None:
            self._params = MockColorSelectionParams()
        return self._params
    def _color_sel_set_params(self, params):
        self._params = params
    ColorSelectionEffectNode.get_parameters = _color_sel_get_params
    ColorSelectionEffectNode.set_parameters = _color_sel_set_params

    # Register effect classes
    layerstack.FilterEffectNode = FilterEffectNode
    layerstack.GeneratorEffectNode = GeneratorEffectNode
    layerstack.LevelsEffectNode = LevelsEffectNode
    layerstack.CompareMaskEffectNode = CompareMaskEffectNode
    layerstack.ColorSelectionEffectNode = ColorSelectionEffectNode
    layerstack.AnchorPointEffectNode = AnchorPointEffectNode
    layerstack.CompareMaskEffectOperand = CompareMaskEffectOperand
    layerstack.CompareMaskEffectOperation = CompareMaskEffectOperation
    layerstack.ColorSelectionBackgroundColor = ColorSelectionBackgroundColor

    # Insert functions for effects — 返回 mock node 对象（有 uid() 方法）
    _next_effect_uid = [1000]
    def _next_euid():
        _next_effect_uid[0] += 1
        return _next_effect_uid[0]

    # Effect node classes with proper type().name matching the real API
    _effect_node_classes = {}
    for _effect_type_name in ("FilterEffectNode", "GeneratorEffectNode",
                               "LevelsEffectNode", "CompareMaskEffectNode",
                               "ColorSelectionEffectNode", "AnchorPointEffectNode",
                               "PaintEffectNode", "FillEffectNode"):
        _effect_node_classes[_effect_type_name] = type(_effect_type_name, (), {
            "__init__": lambda self, uid_val, nt=_effect_type_name: setattr(self, "_uid", uid_val) or setattr(self, "_name", f"{nt}_{uid_val}"),
            "uid": lambda self: self._uid,
            "get_name": lambda self: self._name,
            "set_name": lambda self, v: setattr(self, "_name", v),
            "get_stack": lambda self: _mock_stack,
        })
    layerstack._effect_node_classes = _effect_node_classes

    # Patch effect-specific methods onto the right classes
    LevelsEffectNodeCls = _effect_node_classes["LevelsEffectNode"]
    setattr(LevelsEffectNodeCls, "get_parameters",
            lambda self: MockLevelsParamsMono())
    setattr(LevelsEffectNodeCls, "set_parameters",
            lambda self, p: setattr(self, "_levels_params", p))
    setattr(LevelsEffectNodeCls, "affected_channel",
            property(lambda self: ChannelType.BaseColor,
                     lambda self, v: setattr(self, "_affected_channel", v)))

    CompareMaskEffectNodeCls = _effect_node_classes["CompareMaskEffectNode"]
    setattr(CompareMaskEffectNodeCls, "get_parameters",
            lambda self: MockCompareMaskParams())
    setattr(CompareMaskEffectNodeCls, "set_parameters",
            lambda self, p: setattr(self, "_cmp_params", p))

    ColorSelectionEffectNodeCls = _effect_node_classes["ColorSelectionEffectNode"]
    setattr(ColorSelectionEffectNodeCls, "get_parameters",
            lambda self: MockColorSelectionParams())
    setattr(ColorSelectionEffectNodeCls, "set_parameters",
            lambda self, p: setattr(self, "_cs_params", p))

    FilterEffectNodeCls = _effect_node_classes["FilterEffectNode"]
    setattr(FilterEffectNodeCls, "get_source",
            lambda self: getattr(self, "_source", None))
    setattr(FilterEffectNodeCls, "set_source",
            lambda self, src: setattr(self, "_source", src) or src)
    setattr(FilterEffectNodeCls, "remove_source",
            lambda self: setattr(self, "_source", None))

    GeneratorEffectNodeCls = _effect_node_classes["GeneratorEffectNode"]
    setattr(GeneratorEffectNodeCls, "get_source",
            lambda self: getattr(self, "_source", None))
    setattr(GeneratorEffectNodeCls, "set_source",
            lambda self, src: setattr(self, "_source", src) or src)
    setattr(GeneratorEffectNodeCls, "remove_source",
            lambda self: setattr(self, "_source", None))

    def _make_effect_node(effect_type_name, uid):
        """创建一个带有 uid() 方法的类型正确的 mock effect node。"""
        cls = _effect_node_classes.get(effect_type_name)
        if cls is None:
            cls = type(effect_type_name, (), {
                "uid": lambda self: uid,
                "get_name": lambda self: effect_type_name,
                "get_stack": lambda self: _mock_stack,
            })
        return cls(uid)

    def _insert_levels_effect(pos_tuple):
        n = _make_effect_node("LevelsEffectNode", _next_euid())
        _node_registry[n.uid()] = n; return n
    def _insert_compare_mask_effect(pos_tuple):
        n = _make_effect_node("CompareMaskEffectNode", _next_euid())
        _node_registry[n.uid()] = n; return n
    def _insert_filter_effect(pos_tuple, url):
        n = _make_effect_node("FilterEffectNode", _next_euid())
        _node_registry[n.uid()] = n; return n
    def _insert_generator_effect(pos_tuple, url):
        n = _make_effect_node("GeneratorEffectNode", _next_euid())
        _node_registry[n.uid()] = n; return n
    def _insert_anchor_point_effect(pos_tuple, name):
        n = _make_effect_node("AnchorPointEffectNode", _next_euid())
        _node_registry[n.uid()] = n; return n
    def _insert_color_selection_effect(pos_tuple):
        n = _make_effect_node("ColorSelectionEffectNode", _next_euid())
        _node_registry[n.uid()] = n; return n

    layerstack.insert_levels_effect = _insert_levels_effect
    layerstack.insert_compare_mask_effect = _insert_compare_mask_effect
    layerstack.insert_filter_effect = _insert_filter_effect
    layerstack.insert_generator_effect = _insert_generator_effect
    layerstack.insert_anchor_point_effect = _insert_anchor_point_effect
    layerstack.insert_color_selection_effect = _insert_color_selection_effect

    # Selection API
    _mock_selected_nodes = []
    def _get_selected_nodes(stack):
        return list(_mock_selected_nodes)
    def _set_selected_nodes(nodes):
        _mock_selected_nodes.clear()
        _mock_selected_nodes.extend(nodes)
    layerstack.get_selected_nodes = _get_selected_nodes
    layerstack.set_selected_nodes = _set_selected_nodes

    # ── substance_painter.baking (new mock) ──
    baking_mod = types.ModuleType("substance_painter.baking")

    class BakingStatus(_Enum):
        Success = _Enum("Success")
        Cancel  = _Enum("Cancel")
        Fail    = _Enum("Fail")

    class CurvatureMethod(_Enum):
        FromMesh       = _Enum("FromMesh")
        FromNormalMap  = _Enum("FromNormalMap")

    class MockBakingParameters:
        def __init__(self, material_id=0):
            self.material_id = material_id
            self._common = {
                "OutputSize": Property("OutputSize", [2048, 2048]),
                "HipolyMesh": Property("HipolyMesh", ""),
                "NormalFormat": Property("NormalFormat", _Enum("OpenGL")),
            }
            self._curvature = CurvatureMethod.FromMesh
            self._ts_enabled = True
            self._enabled_bakers = [MeshMapUsage.AO, MeshMapUsage.Normal,
                                    MeshMapUsage.Curvature]
            self._enabled_uv_tiles = [(0, 0)]

        @staticmethod
        def from_texture_set(texture_set):
            return MockBakingParameters(texture_set.material_id)

        @staticmethod
        def from_texture_set_name(name):
            return MockBakingParameters(1)

        def texture_set(self):
            return textureset.MockTextureSet(self.material_id, "BakingTS")

        def common(self):
            return dict(self._common)

        def baker(self, usage):
            return {}

        @staticmethod
        def set(property_values):
            pass

        def get_curvature_method(self):
            return self._curvature

        def set_curvature_method(self, method):
            self._curvature = method

        def is_baker_enabled(self, usage):
            return usage in self._enabled_bakers

        def set_baker_enabled(self, usage, enable):
            if enable:
                if usage not in self._enabled_bakers:
                    self._enabled_bakers.append(usage)
            else:
                if usage in self._enabled_bakers:
                    self._enabled_bakers.remove(usage)

        def get_enabled_bakers(self):
            return list(self._enabled_bakers)

        def set_enabled_bakers(self, usages):
            self._enabled_bakers = list(usages)

        def is_textureset_enabled(self):
            return self._ts_enabled

        def set_textureset_enabled(self, enable):
            self._ts_enabled = enable

        def is_uv_tile_enabled(self, tile):
            return (tile.u, tile.v) in self._enabled_uv_tiles

        def set_uv_tile_enabled(self, tile, enable):
            t = (tile.u, tile.v)
            if enable:
                if t not in self._enabled_uv_tiles:
                    self._enabled_uv_tiles.append(t)
            else:
                if t in self._enabled_uv_tiles:
                    self._enabled_uv_tiles.remove(t)

        def get_enabled_uv_tiles(self):
            return [MockUVTile(u, v, self.material_id)
                    for u, v in self._enabled_uv_tiles]

        def set_enabled_uv_tiles(self, tiles):
            self._enabled_uv_tiles = [(t.u, t.v) for t in tiles]

    def _bake_async(ts):
        # StopSource：真实 SP 10.0.1 的取消方法是 request_stop()。mock 同步，
        # 退路 cancel() 保留兼容。handler 会按 request_stop→cancel→stop 探测。
        return types.SimpleNamespace(request_stop=lambda: None,
                                     cancel=lambda: None)
    def _bake_selected_async():
        return types.SimpleNamespace(request_stop=lambda: None,
                                     cancel=lambda: None)

    baking_mod.BakingParameters = MockBakingParameters
    baking_mod.BakingStatus = BakingStatus
    baking_mod.CurvatureMethod = CurvatureMethod
    baking_mod.bake_async = _bake_async
    baking_mod.bake_selected_textures_async = _bake_selected_async
    baking_mod.set_linked_group = lambda group, ref, usage: None
    baking_mod.set_linked_group_common_parameters = lambda group, ref: None
    baking_mod.unlink_all = lambda usage: None
    baking_mod.unlink_all_common_parameters = lambda: None
    baking_mod.get_link_group = lambda usage: []
    baking_mod.get_link_group_common_parameters = lambda: []
    baking_mod.get_linked_texture_sets = lambda ts, usage: [ts]
    baking_mod.get_linked_texture_sets_common_parameters = lambda ts: [ts]

    sp.baking = baking_mod
    sys.modules["substance_painter.baking"] = baking_mod

    # ── substance_painter.project extensions ──
    class ProjectSaveMode(_Enum):
        Full         = _Enum("Full")
        Incremental  = _Enum("Incremental")

    class NormalMapFormat(_Enum):
        OpenGL  = _Enum("OpenGL")
        DirectX = _Enum("DirectX")

    class TangentSpace(_Enum):
        PerVertex   = _Enum("PerVertex")
        PerFragment = _Enum("PerFragment")

    class ProjectWorkflow(_Enum):
        Default             = _Enum("Default")
        TextureSetPerUVTile = _Enum("TextureSetPerUVTile")
        UVTile              = _Enum("UVTile")

    project_mod.ProjectSaveMode = ProjectSaveMode
    project_mod.NormalMapFormat = NormalMapFormat
    project_mod.TangentSpace = TangentSpace
    project_mod.ProjectWorkflow = ProjectWorkflow

    class MockSettings:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    class MockUsdSettings:
        def __init__(self):
            self.scope_name = "/"
            self.variants = None
            self.subdivision_level = 1
            self.frame = 0

    class MockMeshReloadingSettings:
        def __init__(self, import_cameras=True, preserve_strokes=True,
                     usd_settings=None):
            self.import_cameras = import_cameras
            self.preserve_strokes = preserve_strokes
            self.usd_settings = usd_settings

    project_mod.Settings = MockSettings
    project_mod.UsdSettings = MockUsdSettings
    project_mod.MeshReloadingSettings = MockMeshReloadingSettings

    _mock_project_state = {"is_open": True, "name": "MockProject",
                           "path": "/mock/project.spp", "needs_saving": False}

    def _project_create(mesh, maps, template, settings_dict):
        _mock_project_state["is_open"] = True
        _mock_project_state["name"] = "NewProject"
    def _project_open(path):
        _mock_project_state["is_open"] = True
        _mock_project_state["path"] = path
        _mock_project_state["name"] = "OpenedProject"
    def _project_close():
        _mock_project_state["is_open"] = False
    def _project_is_open():
        return _mock_project_state["is_open"]
    def _project_needs_saving():
        return _mock_project_state["needs_saving"]
    def _project_name():
        return _mock_project_state["name"]
    def _project_file_path():
        return _mock_project_state["path"]
    def _project_reload_mesh(path, settings_dict, cb):
        pass

    project_mod.create = _project_create
    project_mod.open = _project_open
    project_mod.close = _project_close
    project_mod.is_open = _project_is_open
    project_mod.needs_saving = _project_needs_saving
    project_mod.name = _project_name
    project_mod.file_path = _project_file_path
    project_mod.reload_mesh = _project_reload_mesh

    # Metadata mock
    class MockMetadata:
        def __init__(self, context):
            self._context = context
            self._store = {}

        @staticmethod
        def _get_store():
            if not hasattr(MockMetadata, '_global_store'):
                MockMetadata._global_store = {}
            return MockMetadata._global_store

        def list(self):
            store = self._get_store()
            prefix = self._context + "/"
            return [k[len(prefix):] for k in store
                    if k.startswith(prefix)]

        def get(self, key):
            return self._get_store().get(self._context + "/" + key)

        def set(self, key, value):
            self._get_store()[self._context + "/" + key] = value

    project_mod.Metadata = MockMetadata

    # ── substance_painter.event (new mock) ──
    event_mod = types.ModuleType("substance_painter.event")

    class MockDispatcher:
        def __init__(self):
            self._callbacks = {}  # {event_cls_name: [callback,...]}
        def connect(self, event_cls, callback):
            self._callbacks.setdefault(event_cls.__name__, []).append(callback)
        def connect_strong(self, event_cls, callback):
            self._callbacks.setdefault(event_cls.__name__, []).append(callback)
        def disconnect(self, event_cls, callback):
            lst = self._callbacks.get(event_cls.__name__, [])
            if callback in lst:
                lst.remove(callback)
        def _trigger(self, evt_cls):
            """测试辅助：模拟某事件发生，触发已注册回调。"""
            name = evt_cls if isinstance(evt_cls, str) else getattr(evt_cls, "__name__", str(evt_cls))
            ev = types.SimpleNamespace()
            for cb in list(self._callbacks.get(name, [])):
                cb(ev)

    event_mod.DISPATCHER = MockDispatcher()
    event_mod.Dispatcher = MockDispatcher

    # Event classes
    for evt_name in ("ProjectOpened", "ProjectCreated", "ProjectAboutToClose",
                     "ProjectAboutToSave", "ProjectSaved", "ProjectEditionEntered",
                     "ProjectEditionLeft", "BusyStatusChanged",
                     "BakingProcessAboutToStart", "BakingProcessProgress",
                     "BakingProcessEnded", "ExportTexturesAboutToStart",
                     "ExportTexturesEnded", "TextureStateEvent",
                     "CameraPropertiesChanged", "LayerStacksModelDataChanged",
                     "EngineComputationsStatusChanged",
                     "ShelfCrawlingStarted", "ShelfCrawlingEnded"):
        setattr(event_mod, evt_name, type(evt_name, (), {}))

    sp.event = event_mod
    sys.modules["substance_painter.event"] = event_mod

    # ── UI mode switching mock ──
    class UIMode(_Enum):
        Edition       = _Enum("Edition")
        Visualisation = _Enum("Visualisation")
        Baking        = _Enum("Baking")
    ui.UIMode = UIMode
    ui.switch_to_mode = lambda mode: None

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
