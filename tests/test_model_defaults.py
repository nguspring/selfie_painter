"""内置模型默认值测试。"""

import importlib.util
import sys
import tomllib
import types
import unittest
from pathlib import Path


EXPECTED_MODELS = [
    ("Krea-2-Turbo", "krea/Krea-2-Turbo", "natural_language", 1, 8, "Euler"),
    ("Z-Image-Turbo", "Tongyi-MAI/Z-Image-Turbo", "natural_language", 1, 12, "Euler"),
    ("WAI-illustrious-SDXL-v17", "HingXuan/WAI-illustrious-SDXL-v17", "sd", 6, 30, "Euler a"),
    ("ChenkinNoob-XL-V0.5", "ChenkinNoob/ChenkinNoob-XL-V0.5", "sd", 6, 30, "Euler a"),
    ("MiaoMiao RealSkin EPS-v1.3", "mixLine/miaomiaoRealskin", "sd", 6, 30, "Euler a"),
    ("MiaoMiao Harem v1.9", "qsdq2423432/miaomiaoHarem_v19", "sd", 6, 30, "Euler a"),
]

REALSKIN_POSITIVE = (
    "masterpiece,very aesthetic,best quality,absurdres,newest,highres,ultra detailed ,"
    "anime coloring,depth of field,pale_skin,"
)
REALSKIN_NEGATIVE = (
    "lowres,(bad),bad hands,limb asymmetry,bad feet,text,error,fewer,extra,missing,worst quality,"
    "jpeg artifacts,low quality,watermark,unfinished,displeasing,oldest,early,chromatic aberration,"
    "signature,simple_background,artistic error,username,scan,[abstract],english text,shiny_skin"
)
HAREM_POSITIVE = (
    "masterpiece, best quality, absurdres, newest, very aesthetic, amazing quality,highres,sensitive,"
    "complex background, highres, ultra detailed, best anatomy, HDR, 8K, high detail RAW color art, "
    "high contrast, depth of field"
)
HAREM_NEGATIVE = (
    "lowres,(bad),limb asymmetry,bad feet,text,error,fewer,extra,missing,worst quality,jpeg artifacts,"
    "low quality,watermark,unfinished,displeasing,oldest,early,chromatic aberration,signature,"
    "simple_background,artistic error,username,scan,[abstract],english text,shiny_skin"
)


def _load_schema_module():
    """加载 schema，避免测试依赖完整 MaiBot 运行时。"""
    for name in ("src", "src.plugin_system", "src.plugin_system.base"):
        sys.modules.setdefault(name, types.ModuleType(name))

    config_types = types.ModuleType("src.plugin_system.base.config_types")

    class _ConfigValue:
        """记录 schema 构造参数的最小替身。"""

        def __init__(self, *args, **kwargs):
            self.__dict__.update(kwargs)

    config_types.ConfigField = _ConfigValue
    config_types.ConfigSection = _ConfigValue
    config_types.ConfigLayout = _ConfigValue
    config_types.ConfigTab = _ConfigValue
    sys.modules["src.plugin_system.base.config_types"] = config_types

    schema_path = Path(__file__).resolve().parents[1] / "plugin_schema.py"
    spec = importlib.util.spec_from_file_location("selfie_painter_v2_model_defaults_schema", schema_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _assert_model_defaults(test_case, fields, expected):
    """断言单个模型的公共默认参数与预期一致。"""
    actual = (
        fields["name"].default,
        fields["model"].default,
        fields["optimizer_mode_override"].default,
        fields["guidance_scale"].default,
        fields["num_inference_steps"].default,
        fields["sampler"].default,
    )
    test_case.assertEqual(actual, expected)
    test_case.assertEqual(fields["format"].default, "modelscope")
    test_case.assertIs(fields["fixed_size_enabled"].default, True)
    test_case.assertEqual(fields["default_size"].default, "1024x1024")
    test_case.assertIs(fields["support_img2img"].default, True)


class ModelDefaultsTest(unittest.TestCase):
    """验证新用户 schema 和当前运行配置拥有相同的六模型默认值。"""

    def test_schema_contains_six_ordered_model_defaults(self):
        """新用户首次配置必须包含顺序固定的六个模型。"""
        module = _load_schema_module()

        self.assertEqual(
            [key for key in module.CONFIG_SCHEMA if key.startswith("models.")],
            [f"models.model{index}" for index in range(1, 7)],
        )
        for index, expected in enumerate(EXPECTED_MODELS, start=1):
            _assert_model_defaults(self, module.CONFIG_SCHEMA[f"models.model{index}"], expected)

        self.assertEqual(module.CONFIG_SCHEMA["models.model5"]["custom_prompt_add"].default, REALSKIN_POSITIVE)
        self.assertEqual(module.CONFIG_SCHEMA["models.model5"]["negative_prompt_add"].default, REALSKIN_NEGATIVE)
        self.assertEqual(module.CONFIG_SCHEMA["models.model6"]["custom_prompt_add"].default, HAREM_POSITIVE)
        self.assertEqual(module.CONFIG_SCHEMA["models.model6"]["negative_prompt_add"].default, HAREM_NEGATIVE)

    def test_runtime_config_matches_six_model_defaults(self):
        """当前运行配置必须和新用户六模型默认值保持一致。"""
        config_path = Path(__file__).resolve().parents[1] / "config.toml"
        if not config_path.exists():
            self.skipTest("config.toml 是本机忽略的运行配置，干净 checkout 不包含该文件")
        config = tomllib.loads(config_path.read_text(encoding="utf-8"))

        self.assertEqual(list(config["models"]), [f"model{index}" for index in range(1, 7)])
        self.assertEqual(config["generation"]["default_model"], "model1")
        self.assertEqual(config["components"]["pic_command_model"], "model1")
        self.assertEqual(config["auto_selfie"]["selfie_model"], "model1")
        for index, expected in enumerate(EXPECTED_MODELS, start=1):
            model = config["models"][f"model{index}"]
            actual = (
                model["name"],
                model["model"],
                model["optimizer_mode_override"],
                model["guidance_scale"],
                model["num_inference_steps"],
                model["sampler"],
            )
            self.assertEqual(actual, expected)
            self.assertEqual(model["format"], "modelscope")
            self.assertIs(model["fixed_size_enabled"], True)
            self.assertEqual(model["default_size"], "1024x1024")
            self.assertIs(model["support_img2img"], True)

        self.assertEqual(config["models"]["model5"]["custom_prompt_add"], REALSKIN_POSITIVE)
        self.assertEqual(config["models"]["model5"]["negative_prompt_add"], REALSKIN_NEGATIVE)
        self.assertEqual(config["models"]["model6"]["custom_prompt_add"], HAREM_POSITIVE)
        self.assertEqual(config["models"]["model6"]["negative_prompt_add"], HAREM_NEGATIVE)


if __name__ == "__main__":
    unittest.main()
