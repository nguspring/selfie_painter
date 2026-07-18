"""魔搭客户端请求体测试。"""

import asyncio
import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path


def _load_modelscope_client_module():
    """在不启动 MaiBot 的情况下加载魔搭客户端模块。"""
    client_dir = Path(__file__).resolve().parents[1] / "core" / "api_clients"
    package_name = "selfie_painter_v2_test_modelscope_api_clients"

    logger_module = types.ModuleType("src.common.logger")

    class _LoggerStub:
        """避免测试依赖宿主日志系统。"""

        def debug(self, *args, **kwargs):
            pass

        def info(self, *args, **kwargs):
            pass

        def warning(self, *args, **kwargs):
            pass

        def error(self, *args, **kwargs):
            pass

    logger_module.get_logger = lambda name: _LoggerStub()
    sys.modules.setdefault("src", types.ModuleType("src"))
    sys.modules.setdefault("src.common", types.ModuleType("src.common"))
    sys.modules["src.common.logger"] = logger_module

    package = types.ModuleType(package_name)
    package.__path__ = [str(client_dir)]
    sys.modules[package_name] = package

    base_spec = importlib.util.spec_from_file_location(f"{package_name}.base_client", client_dir / "base_client.py")
    assert base_spec is not None and base_spec.loader is not None
    base_module = importlib.util.module_from_spec(base_spec)
    sys.modules[f"{package_name}.base_client"] = base_module
    base_spec.loader.exec_module(base_module)

    client_spec = importlib.util.spec_from_file_location(
        f"{package_name}.modelscope_client", client_dir / "modelscope_client.py"
    )
    assert client_spec is not None and client_spec.loader is not None
    client_module = importlib.util.module_from_spec(client_spec)
    sys.modules[f"{package_name}.modelscope_client"] = client_module
    client_spec.loader.exec_module(client_module)
    return client_module


class _ActionStub:
    """提供客户端初始化所需的最小宿主接口。"""

    log_prefix = "[test]"

    def get_config(self, key, default=None):
        """测试不启用代理，直接返回传入的默认值。"""
        return default


class _ResponseStub:
    """让测试在发送请求后立即结束。"""

    status_code = 400
    text = "unsupported sampler"


class _RequestsStub:
    """记录 JSON 请求体，避免向真实服务发送请求。"""

    def __init__(self):
        self.post_calls = []

    def post(self, **kwargs):
        """保存请求参数并返回失败响应，阻止后续轮询。"""
        self.post_calls.append(kwargs)
        return _ResponseStub()


class ModelscopeClientTest(unittest.TestCase):
    """验证公开魔搭请求只在文生图中传递采样器。"""

    def setUp(self):
        """为每个测试创建独立客户端和请求记录器。"""
        self.module = _load_modelscope_client_module()
        self.requests = _RequestsStub()
        self.module.get_requests_module = lambda: self.requests
        self.client = self.module.ModelscopeClient(_ActionStub())
        self.model_config = {
            "api_key": "test-token",
            "model": "HingXuan/WAI-illustrious-SDXL-v17",
            "sampler": "Euler a",
            "seed": 123,
            "num_inference_steps": 28,
            "guidance_scale": 6,
        }

    def test_text_to_image_sends_configured_sampler(self):
        """文生图请求必须发送配置中的采样器原始值。"""
        with self.assertRaises(self.module.NonRetryableError):
            self.client._make_request("1girl", self.model_config, "1024x1024")

        payload = json.loads(self.requests.post_calls[0]["data"].decode("utf-8"))
        self.assertEqual(payload["sampler"], "Euler a")
        self.assertEqual(payload["steps"], 28)
        self.assertEqual(payload["guidance"], 6)

    def test_image_to_image_does_not_send_sampler(self):
        """图生图保持现有公共接口请求体，不能猜测性添加采样器。"""
        success, result = self.client._make_request(
            "redraw this",
            self.model_config,
            "1024x1024",
            input_image_base64="iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB",
        )

        self.assertIs(success, False)
        self.assertEqual(result, "请求失败: unsupported sampler")
        payload = json.loads(self.requests.post_calls[0]["data"].decode("utf-8"))
        self.assertNotIn("sampler", payload)
        self.assertIn("image_url", payload)

    def test_text_to_image_http_400_does_not_retry_sampler_request(self):
        """参数被服务端拒绝时不应重复提交同一份采样器请求。"""
        success, result = asyncio.run(
            self.client.generate_image("1girl", self.model_config, "1024x1024")
        )

        self.assertIs(success, False)
        self.assertEqual(result, "请求失败: unsupported sampler")
        self.assertEqual(len(self.requests.post_calls), 1)

    def test_text_to_image_http_400_without_sampler_keeps_existing_retries(self):
        """未携带采样器的旧请求仍沿用客户端原有重试策略。"""
        model_config = self.model_config.copy()
        model_config.pop("sampler")

        success, result = asyncio.run(self.client.generate_image("1girl", model_config, "1024x1024"))

        self.assertIs(success, False)
        self.assertEqual(result, "请求失败: unsupported sampler")
        self.assertEqual(len(self.requests.post_calls), 3)


if __name__ == "__main__":
    unittest.main()
