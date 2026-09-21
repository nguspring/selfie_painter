"""自动自拍提示词统一链路的隔离回归测试。"""

import ast
import asyncio
import importlib.util
import json
import logging
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Optional
from unittest.mock import AsyncMock, Mock


ROOT = Path(__file__).resolve().parents[1]


class _StripImports(ast.NodeTransformer):
    """移除宿主导入，让测试只执行插件函数本身。"""

    def visit_Import(self, node):
        return None

    def visit_ImportFrom(self, node):
        return None


def load_module(relative_path: str, namespace: dict) -> dict:
    """提取插件源码并注入隔离依赖，返回执行后的命名空间。"""
    tree = ast.parse((ROOT / relative_path).read_text(encoding="utf-8"))
    tree = _StripImports().visit(tree)
    ast.fix_missing_locations(tree)
    exec(compile(tree, relative_path, "exec"), namespace)
    return namespace


def load_optimizer_mode():
    """加载不依赖宿主的优化模式解析模块。"""
    path = ROOT / "core" / "utils" / "optimizer_mode.py"
    spec = importlib.util.spec_from_file_location("selfie_optimizer_mode_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Activity:
    """提供场景与配文生成器需要的最小活动对象。"""

    def __init__(self, description: str = "在书房看轻小说"):
        self.description = description
        self.activity_type = SimpleNamespace(value="studying")


class _FakeLlmApi:
    """记录模型选择并返回固定结构化结果的假 LLM 接口。"""

    def __init__(self, models):
        self.models = models
        self.calls = []

    def get_available_models(self):
        return self.models

    async def generate_with_model(self, **kwargs):
        self.calls.append(kwargs)
        response = json.dumps(
            {
                "action": "holding book, reading",
                "environment": "study room, bookshelf",
                "expression": "content smile",
                "lighting": "warm desk lamp",
            }
        )
        return True, response, "", "test-model"


def scene_namespace(llm_api):
    """构造场景生成器的隔离依赖。"""
    return {
        "json": json,
        "re": __import__("re"),
        "Dict": dict,
        "List": list,
        "Optional": Optional,
        "ActivityInfo": _Activity,
        "get_logger": lambda _name: logging.getLogger("selfie-test"),
        "llm_api": llm_api,
        "SELFIE_HAND_NEGATIVE": "bad hands",
        "ANTI_DUAL_PHONE_PROMPT": "no duplicate phone",
        "ANTI_CAMERA_DEVICE_PROMPT": "no camera device",
        "ANTI_MIRROR_PORTAL_PROMPT": "no mirror portal",
    }


def auto_task_namespace(optimize_prompt, resolve_mode):
    """构造自动自拍任务中两个纯逻辑函数的隔离依赖。"""
    return {
        "asyncio": asyncio,
        "base64": __import__("base64"),
        "datetime": __import__("datetime"),
        "import_module": Mock(),
        "os": __import__("os"),
        "time": __import__("time"),
        "Any": Any,
        "Callable": Callable,
        "Optional": Optional,
        "get_logger": lambda _name: logging.getLogger("selfie-test"),
        "get_schedule_provider": Mock(),
        "convert_to_selfie_prompt": AsyncMock(),
        "get_negative_prompt_for_style": Mock(),
        "generate_caption": AsyncMock(),
        "generate_image_standalone": AsyncMock(),
        "get_model_config": Mock(),
        "normalize_selfie_style": Mock(),
        "get_selfie_style_display_name": Mock(),
        "build_target_context_id": Mock(),
        "is_chat_allowed_for_model": Mock(),
        "optimize_prompt": optimize_prompt,
        "resolve_effective_prompt_optimizer_mode": resolve_mode,
    }


class AutoPromptUnificationTests(unittest.IsolatedAsyncioTestCase):
    """验证模型分流、严格校验和统一优化器调用契约。"""

    async def test_scene_generation_uses_requested_model_without_fallback(self):
        planner = object()
        replyer = object()
        llm_api = _FakeLlmApi({"planner": planner, "replyer": replyer})
        namespace = load_module("core/selfie/scene_action_generator.py", scene_namespace(llm_api))

        await namespace["generate_scene_with_llm"](_Activity(), model_id="planner")
        self.assertIs(llm_api.calls[-1]["model_config"], planner)
        await namespace["generate_scene_with_llm"](_Activity(), model_id="replyer")
        self.assertIs(llm_api.calls[-1]["model_config"], replyer)

        result = await namespace["generate_scene_with_llm"](_Activity(), model_id="missing")
        self.assertIsNone(result)
        self.assertEqual(len(llm_api.calls), 2)

    async def test_convert_forwards_prompt_model_id(self):
        planner = object()
        llm_api = _FakeLlmApi({"planner": planner})
        namespace = load_module("core/selfie/scene_action_generator.py", scene_namespace(llm_api))

        prompt = await namespace["convert_to_selfie_prompt"](
            _Activity(), bot_appearance="blue hair", llm_model_id="planner"
        )
        self.assertIn("blue hair", prompt)
        self.assertIs(llm_api.calls[0]["model_config"], planner)

    async def test_auto_selfie_uses_actual_model_override_and_keeps_base_on_failure(self):
        resolve_mode = Mock(return_value="natural_language")
        optimizer = AsyncMock(return_value=(True, "A natural English selfie prompt."))
        namespace = load_module("core/selfie/auto_selfie_task.py", auto_task_namespace(optimizer, resolve_mode))

        def get_config(key, default=None):
            return {"models.model1.optimizer_mode_override": "natural_language"}.get(key, default)

        result, mode, optimized = await namespace["_optimize_auto_selfie_prompt"](
            "base prompt", get_config, "model1"
        )
        self.assertEqual((result, mode, optimized), ("A natural English selfie prompt.", "natural_language", True))
        resolve_mode.assert_called_once_with(get_config, "model1")
        self.assertEqual(optimizer.await_args.kwargs["mode"], "natural_language")

        optimizer.reset_mock()
        optimizer.return_value = (False, "optimization failed")
        result, mode, optimized = await namespace["_optimize_auto_selfie_prompt"](
            "base prompt", get_config, "model1"
        )
        self.assertEqual((result, mode, optimized), ("base prompt", "natural_language", False))

    async def test_auto_selfie_passes_optimized_prompt_to_image_api(self):
        optimized = AsyncMock(return_value=(True, "optimized selfie prompt"))
        namespace = load_module(
            "core/selfie/auto_selfie_task.py",
            auto_task_namespace(optimized, Mock(return_value="natural_language")),
        )
        namespace["get_schedule_provider"].return_value = SimpleNamespace(
            get_current_activity=AsyncMock(return_value=_Activity())
        )
        namespace["normalize_selfie_style"].return_value = "standard"
        namespace["get_selfie_style_display_name"].return_value = "标准自拍"
        namespace["convert_to_selfie_prompt"].return_value = "base selfie prompt"
        namespace["get_negative_prompt_for_style"].return_value = ""
        namespace["generate_image_standalone"].return_value = (True, "image-data")

        values = {
            "auto_selfie.prompt_model_id": "planner",
            "selfie.default_style": "standard",
            "selfie.prompt_prefix": "blue hair",
            "wardrobe.enabled": False,
            "selfie.raw_mode": False,
            "selfie.negative_prompt": "",
            "auto_selfie.selfie_model": "model1",
            "prompt_optimizer.enabled": True,
            "auto_selfie.caption_enabled": False,
            "proxy.enabled": False,
        }

        def get_config(key, default=None):
            return values.get(key, default)

        obj = SimpleNamespace(
            get_config=Mock(side_effect=get_config),
            _get_model_config=Mock(return_value=("model1", {"default_size": "1024x1024"})),
            _load_reference_image=Mock(return_value=None),
        )

        with self.assertRaisesRegex(RuntimeError, "所有发送渠道均失败"):
            await namespace["AutoSelfieTask"]._execute_selfie(obj)

        self.assertEqual(namespace["convert_to_selfie_prompt"].await_args.kwargs["llm_model_id"], "planner")
        self.assertEqual(namespace["generate_image_standalone"].await_args.kwargs["prompt"], "optimized selfie prompt")

    def test_optimizer_mode_respects_override_and_follow_global(self):
        optimizer_mode = load_optimizer_mode()

        def config_for(values):
            return lambda key, default=None: values.get(key, default)

        self.assertEqual(
            optimizer_mode.resolve_effective_prompt_optimizer_mode(
                config_for(
                    {
                        "prompt_optimizer.mode": "nai",
                        "models.model1.optimizer_mode_override": "sd",
                    }
                ),
                "model1",
            ),
            "sd",
        )
        self.assertEqual(
            optimizer_mode.resolve_effective_prompt_optimizer_mode(
                config_for(
                    {
                        "prompt_optimizer.mode": "nai",
                        "models.model1.optimizer_mode_override": "follow_global",
                    }
                ),
                "model1",
            ),
            "nai",
        )

    def test_prompt_model_validation_is_strict(self):
        namespace = load_module(
            "core/selfie/auto_selfie_task.py",
            auto_task_namespace(AsyncMock(), Mock(return_value="sd")),
        )
        self.assertEqual(namespace["_resolve_prompt_model_id"](lambda _key, _default: "planner"), "planner")
        self.assertEqual(namespace["_resolve_prompt_model_id"](lambda _key, _default: "replyer"), "replyer")
        with self.assertRaises(ValueError):
            namespace["_resolve_prompt_model_id"](lambda _key, _default: "gpt")

    async def test_caption_uses_requested_model_without_fallback(self):
        replyer = object()
        llm_api = _FakeLlmApi({"replyer": replyer})
        config_api = SimpleNamespace(get_global_config=Mock(side_effect=lambda _key, default: default))
        namespace = load_module(
            "core/selfie/caption_generator.py",
            {
                "datetime": SimpleNamespace(datetime=__import__("datetime").datetime),
                "random": __import__("random"),
                "get_logger": lambda _name: logging.getLogger("selfie-test"),
                "llm_api": llm_api,
                "config_api": config_api,
                "ActivityInfo": _Activity,
            },
        )

        self.assertEqual(await namespace["generate_caption"](_Activity(), model_id="planner"), "")
        self.assertEqual(len(llm_api.calls), 0)

        llm_api.generate_with_model = AsyncMock(return_value=(True, "今天在书房看书呢。", "", "replyer"))
        self.assertEqual(await namespace["generate_caption"](_Activity(), model_id="replyer"), "今天在书房看书呢。")
        llm_api.generate_with_model.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
