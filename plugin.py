# pyright: reportIncompatibleVariableOverride=false
# pyright: reportIncompatibleMethodOverride=false
# pyright: reportMissingImports=false
# pyright: reportMissingTypeArgument=false

from typing import List, Tuple, Type, Dict, Any

from src.common.logger import get_logger
from src.plugin_system.base.base_plugin import BasePlugin
from src.plugin_system.base.component_types import ComponentInfo, PythonDependency
from src.plugin_system import register_plugin
from src.plugin_system.base.config_types import ConfigField, ConfigSection
from .plugin_components import build_plugin_components
from .plugin_config_runtime import load_raw_config
from .plugin_meta import (
    CONFIG_FILE_NAME,
    DEPENDENCIES,
    ENABLE_PLUGIN,
    PLUGIN_AUTHOR,
    PLUGIN_NAME,
    PLUGIN_VERSION,
    PYTHON_DEPENDENCIES,
)
from .plugin_schema import CONFIG_LAYOUT, CONFIG_SCHEMA, CONFIG_SECTION_DESCRIPTIONS, MODEL_FIELD_TEMPLATE
from .plugin_runtime import PluginRuntimeMixin

logger = get_logger("selfie_painter_v2")


@register_plugin
class SelfiePainterV2Plugin(PluginRuntimeMixin, BasePlugin):
    """麦麦绘卷 v2 (selfie_painter_v2) - 智能多模型图片生成插件，支持文生图和图生图"""

    # 插件基本信息
    plugin_name = PLUGIN_NAME
    plugin_version = PLUGIN_VERSION
    plugin_author = PLUGIN_AUTHOR
    enable_plugin = ENABLE_PLUGIN
    dependencies: List[str] = DEPENDENCIES
    python_dependencies: List[PythonDependency] = PYTHON_DEPENDENCIES
    config_file_name = CONFIG_FILE_NAME

    # 配置元数据与 schema 定义
    config_section_descriptions = CONFIG_SECTION_DESCRIPTIONS
    config_layout = CONFIG_LAYOUT
    config_schema = CONFIG_SCHEMA
    _MODEL_FIELD_TEMPLATE: Dict[str, Any] = MODEL_FIELD_TEMPLATE

    def _inject_dynamic_config_layout(self, raw_config: dict[str, Any] | None) -> None:
        """
        根据 config.toml 里的实际内容，动态更新 WEBUI 布局。

        这个方法会做三件事：
        1. 找出 config.toml 里所有 [models.xxx] 节的 key
        2. 为每个模型生成对应的 config_schema 字段、config_section_descriptions 元数据
           和 config_layout 里 models 标签页的 sections 列表
        3. 对 styles / style_aliases 也做同样的动态读取，
           确保 WEBUI 能显示用户在 toml 里自定义的风格
        4. 动态注入 wardrobe.outfits.<outfit_id>，让 WebUI 能编辑每套穿搭

        注意：修改的是实例属性，会覆盖类属性，不影响其他实例。
        调用时机：super().__init__() 之前，确保 WEBUI 读 self.config_schema 时已是最新版本。
        """
        import copy

        # BasePlugin / PluginBase 在类型标注里把部分配置项定义成 @property。
        # 但本插件需要在 super().__init__() 之前动态覆写这些“实例属性”，让 WebUI
        # 能读取到最新的 schema/layout。
        # 这里用 Any 规避静态类型检查对 property setter 的误报（不影响运行时）。
        self_any: Any = self

        def _safe_float(value: Any, default: float) -> float:
            """把 value 尽量转成 float；失败则回退 default。"""
            try:
                return float(value)
            except (TypeError, ValueError):
                return default

        def _safe_str_list(value: Any) -> list[str]:
            """把 value 尽量转成 list[str]；非 list 则返回空列表。"""
            if not isinstance(value, list):
                return []
            return [str(x) for x in value]

        # ── 1. 深拷贝类属性，变成实例属性（避免修改影响类本身）──
        self_any.config_schema = copy.deepcopy(type(self).config_schema)
        self_any.config_section_descriptions = copy.deepcopy(type(self).config_section_descriptions)
        # config_layout 内部有 tabs 列表，需要深拷贝
        self_any.config_layout = copy.deepcopy(type(self).config_layout)

        # ── 2. 收集 config.toml 里实际存在的模型 key ──
        model_keys: list[str] = []  # 例如 ["model1", "model2", "model3"]
        model_names: dict[str, str] = {}  # key -> name，用于 Section 标题
        if raw_config and isinstance(raw_config.get("models"), dict):
            for key, val in raw_config["models"].items():
                if isinstance(val, dict):  # 过滤掉非节的标量值
                    model_keys.append(key)
                    model_names[key] = val.get("name", key)  # 没有 name 就用 key

        # 如果 config.toml 不存在或为空，至少保证 model1 存在（兜底）
        if not model_keys:
            model_keys = ["model1"]
            model_names["model1"] = "模型1"

        # ── 2.5 动态收集 wardrobe.outfits ──
        # 目标：
        # - config.toml 存在时：以用户实际写入的 [wardrobe.outfits.<id>] 为准
        # - config.toml 不存在/缺少 outfits 时：不注入默认服装，保持 WebUI 干净
        #   用户需要手动在 config.toml 中添加 [wardrobe.outfits.<id>] 才会显示对应小板块
        default_outfits: dict[str, dict[str, Any]] = {}

        outfit_keys: list[str] = []
        outfit_data_map: dict[str, dict[str, Any]] = {}
        if raw_config and isinstance(raw_config.get("wardrobe"), dict):
            wardrobe_cfg = raw_config.get("wardrobe", {})
            outfits_cfg = wardrobe_cfg.get("outfits")
            if isinstance(outfits_cfg, dict):
                for outfit_id, outfit_val in outfits_cfg.items():
                    if isinstance(outfit_val, dict):
                        outfit_keys.append(str(outfit_id))
                        outfit_data_map[str(outfit_id)] = outfit_val

        if not outfit_keys:
            # 不再注入默认服装：如果 config.toml 中没有 [wardrobe.outfits] 配置，则保持空列表
            # 用户需要手动在 config.toml 中添加服装配置才会显示对应的 WebUI 小板块
            outfit_keys = []
            outfit_data_map = {}

        # ── 3. 动态注入每个模型的 config_schema / config_section_descriptions ──
        base_order = 13  # models.model1 的 order 是 13，后续模型依次递增
        for idx, key in enumerate(model_keys):
            section_key = f"models.{key}"
            display_name = model_names.get(key, key)

            # 3a. 注入 config_section_descriptions（Section 元数据）
            self_any.config_section_descriptions[section_key] = ConfigSection(
                title=display_name,  # 用模型 name 字段作为标题
                icon="box",
                order=base_order + idx,
            )

            # 3b. 注入 config_schema（字段定义）
            # 如果已经有这个节（比如 model1 已在类属性里），跳过，不覆盖已精心定制的字段
            if section_key not in self_any.config_schema:
                # 从模板构造 ConfigField 字典
                fields: Dict[str, ConfigField] = {}
                for field_name, spec in self._MODEL_FIELD_TEMPLATE.items():
                    spec_copy = dict(spec)  # 浅拷贝，避免修改模板
                    # 用 toml 里的实际值作为默认值（如果有）
                    if raw_config and isinstance(raw_config.get("models"), dict):
                        model_data = raw_config["models"].get(key, {})
                        if field_name in model_data:
                            spec_copy["default"] = model_data[field_name]
                    # 重新构造，把所有支持的参数传进去
                    field_kwargs: Dict[str, Any] = {"type": spec_copy["type"], "default": spec_copy["default"]}
                    for extra_key in (
                        "label",
                        "description",
                        "hint",
                        "input_type",
                        "rows",
                        "choices",
                        "placeholder",
                        "item_type",
                        "min",
                        "max",
                        "step",
                        "group",
                        "order",
                        "required",
                        "disabled",
                    ):
                        if extra_key in spec_copy:
                            field_kwargs[extra_key] = spec_copy[extra_key]
                    fields[field_name] = ConfigField(**field_kwargs)
                self_any.config_schema[section_key] = fields
            else:
                # model1-5（或已存在的节）已在类属性里定义好了，
                # 用 config.toml 里的实际值覆盖 ConfigField.default，
                # 否则 WebUI 会显示类属性里的硬编码模板默认值而非用户实际配置
                model_data: dict[str, Any] = {}
                if raw_config and isinstance(raw_config.get("models"), dict):
                    loaded_model_data = raw_config["models"].get(key, {})
                    if isinstance(loaded_model_data, dict):
                        model_data = loaded_model_data

                existing_fields = self_any.config_schema[section_key]
                if isinstance(existing_fields, dict):
                    for field_name, spec in self._MODEL_FIELD_TEMPLATE.items():
                        if field_name in existing_fields:
                            continue

                        spec_copy = dict(spec)
                        if field_name in model_data:
                            spec_copy["default"] = model_data[field_name]

                        field_kwargs: Dict[str, Any] = {
                            "type": spec_copy["type"],
                            "default": spec_copy["default"],
                        }
                        for extra_key in (
                            "label",
                            "description",
                            "hint",
                            "input_type",
                            "rows",
                            "choices",
                            "placeholder",
                            "item_type",
                            "min",
                            "max",
                            "step",
                            "group",
                            "order",
                            "required",
                            "disabled",
                        ):
                            if extra_key in spec_copy:
                                field_kwargs[extra_key] = spec_copy[extra_key]

                        existing_fields[field_name] = ConfigField(**field_kwargs)

                    for field_name, field_obj in existing_fields.items():
                        if isinstance(field_obj, ConfigField) and field_name in model_data:
                            field_obj.default = model_data[field_name]

        # ── 4. 更新 config_layout 里 models 标签页的 sections ──
        # 找到 id="models" 的 tab，重写其 sections 列表
        for tab in self_any.config_layout.tabs:
            if tab.id == "models":
                tab.sections = ["access_control", "models"] + [f"models.{k}" for k in model_keys]
                break

        # ── 4.5 更新 config_layout 里 features 标签页的 sections（插入 wardrobe + outfits）──
        for tab in self_any.config_layout.tabs:
            if tab.id == "features":
                # 去掉上一次注入的动态节，避免重复
                base_sections = [
                    s for s in list(tab.sections) if s != "wardrobe" and not str(s).startswith("wardrobe.outfits.")
                ]
                insert_at = base_sections.index("selfie") + 1 if "selfie" in base_sections else 0
                dynamic_sections = ["wardrobe"] + [f"wardrobe.outfits.{k}" for k in outfit_keys]
                tab.sections = base_sections[:insert_at] + dynamic_sections + base_sections[insert_at:]
                break

        # ── 4.6 注入 wardrobe.outfits.<id> 的 config_schema / config_section_descriptions ──
        wardrobe_section_base_order = 50
        for idx, outfit_id in enumerate(outfit_keys):
            section_key = f"wardrobe.outfits.{outfit_id}"
            raw_outfit = outfit_data_map.get(outfit_id, {})

            outfit_display_name = raw_outfit.get("name", outfit_id)
            if not isinstance(outfit_display_name, str) or not outfit_display_name.strip():
                outfit_display_name = outfit_id

            self_any.config_section_descriptions[section_key] = ConfigSection(
                title=str(outfit_display_name),
                description="配置一套穿搭（仅服装标签）。prompt 建议用英文逗号分隔，例如：hoodie, jeans, sneakers",
                icon="shirt",
                order=wardrobe_section_base_order + idx,
            )

            # 构造字段默认值：先用内置默认，再用 config.toml 覆盖（如果有）
            merged_defaults: dict[str, Any] = {}
            if outfit_id in default_outfits:
                merged_defaults.update(default_outfits[outfit_id])
            if isinstance(raw_outfit, dict):
                merged_defaults.update(raw_outfit)

            self_any.config_schema[section_key] = {
                "enabled": ConfigField(
                    type=bool,
                    default=bool(merged_defaults.get("enabled", True)),
                    description="是否启用该穿搭",
                    label="启用",
                    order=1,
                ),
                "name": ConfigField(
                    type=str,
                    default=str(merged_defaults.get("name", outfit_id)),
                    description="穿搭显示名称（用于 WebUI 列表/标题）",
                    label="名称",
                    placeholder="日常休闲",
                    order=2,
                ),
                "prompt": ConfigField(
                    type=str,
                    default=str(merged_defaults.get("prompt", "")),
                    description="穿搭提示词（只写衣服/饰品等标签；英文逗号分隔；不要写人物/场景/动作）",
                    label="穿搭标签",
                    input_type="textarea",
                    rows=4,
                    placeholder="hoodie, jeans, sneakers",
                    order=3,
                ),
                "base_weight": ConfigField(
                    type=float,
                    default=_safe_float(merged_defaults.get("base_weight"), 0.0),
                    description="基础权重：在没有临时覆盖时，该穿搭被选中的倾向（0=几乎不会选）",
                    label="基础权重",
                    min=0.0,
                    step=0.1,
                    order=4,
                ),
                "override_weight": ConfigField(
                    type=float,
                    default=_safe_float(merged_defaults.get("override_weight"), 0.0),
                    description="覆盖权重：在“临时覆盖”生效时，该穿搭被选中的倾向（0=几乎不会选）",
                    label="覆盖权重",
                    min=0.0,
                    step=0.1,
                    order=5,
                ),
                "allowed_activity_types": ConfigField(
                    type=list,
                    default=_safe_str_list(merged_defaults.get("allowed_activity_types")),
                    description="允许的活动类型列表（留空表示不限制）。例如：['sleeping', 'exercising']",
                    label="允许活动类型",
                    item_type="string",
                    placeholder="sleeping",
                    order=6,
                ),
                "forbidden_activity_types": ConfigField(
                    type=list,
                    default=_safe_str_list(merged_defaults.get("forbidden_activity_types")),
                    description="禁止的活动类型列表（留空表示不禁止）。如果同时命中允许/禁止，以禁止为准",
                    label="禁止活动类型",
                    item_type="string",
                    placeholder="work",
                    order=7,
                ),
            }

        # ── 5. 动态读取 styles / style_aliases，更新 config_schema ──
        # styles：每个风格 key 对应一个 ConfigField（textarea 输入提示词）
        if raw_config and isinstance(raw_config.get("styles"), dict):
            styles_schema: Dict[str, ConfigField] = {}
            for idx, (style_key, style_val) in enumerate(raw_config["styles"].items()):
                styles_schema[style_key] = ConfigField(
                    type=str,
                    default=style_val if isinstance(style_val, str) else "",
                    description=f"{style_key} 风格的提示词",
                    label=style_key,
                    input_type="textarea",
                    rows=3,
                    order=idx + 1,
                )
            if styles_schema:
                self_any.config_schema["styles"] = styles_schema

        # style_aliases：每个别名 key 对应一个 ConfigField（普通文本输入）
        if raw_config and isinstance(raw_config.get("style_aliases"), dict):
            aliases_schema: Dict[str, ConfigField] = {}
            for idx, (alias_key, alias_val) in enumerate(raw_config["style_aliases"].items()):
                aliases_schema[alias_key] = ConfigField(
                    type=str,
                    default=alias_val if isinstance(alias_val, str) else alias_key,
                    description=f"{alias_key} 风格的中文别名，支持多别名用逗号分隔",
                    label=f"{alias_key} 别名",
                    placeholder="别名1,别名2",
                    order=idx + 1,
                )
            if aliases_schema:
                self_any.config_schema["style_aliases"] = aliases_schema

        logger.info(
            "WEBUI 动态布局注入完成：%s 个模型 %s，%s 套穿搭，%s 个风格",
            len(model_keys),
            model_keys,
            len(outfit_keys),
            len(raw_config.get("styles", {})) if raw_config else 0,
        )

    def __init__(self, plugin_dir: str):
        """初始化插件"""
        original_config = load_raw_config(plugin_dir, self.config_file_name, logger)
        # ── 动态注入：根据 config.toml 里的实际模型/风格，更新 WEBUI 布局 ──
        self._inject_dynamic_config_layout(original_config)

        # 先调用父类初始化，这会加载配置并可能触发 MaiBot 迁移
        BasePlugin.__init__(self, plugin_dir)
        self._initialize_runtime_state()
        self._bootstrap_runtime_tasks()

    def get_plugin_components(self) -> List[Tuple[ComponentInfo, Type]]:
        """返回插件包含的组件列表"""
        return build_plugin_components(self)
