"""tuercha-NAI 客户端契约测试。"""

import importlib.util
import sys
import types
import unittest
from pathlib import Path


def _load_tuercha_client_class():
    """绕开 MaiBot 运行时依赖，直接加载待测客户端类。"""
    client_dir = Path(__file__).resolve().parents[1] / "core" / "api_clients"
    package_name = "selfie_painter_v2_test_api_clients"

    logger_module = types.ModuleType("src.common.logger")

    class _LoggerStub:
        """测试用日志桩，避免加载 MaiBot 完整日志依赖。"""

        def debug(self, *args, **kwargs):
            """忽略调试日志。"""

        def info(self, *args, **kwargs):
            """忽略信息日志。"""

        def warning(self, *args, **kwargs):
            """忽略警告日志。"""

        def error(self, *args, **kwargs):
            """忽略错误日志。"""

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
        f"{package_name}.tuercha_nai_client", client_dir / "tuercha_nai_client.py"
    )
    assert client_spec is not None and client_spec.loader is not None
    client_module = importlib.util.module_from_spec(client_spec)
    sys.modules[f"{package_name}.tuercha_nai_client"] = client_module
    client_spec.loader.exec_module(client_module)
    return client_module.TuerchaNAIClient


def _load_api_clients_init_module():
    """加载 api_clients 包入口，验证格式映射不依赖完整插件启动。"""
    client_dir = Path(__file__).resolve().parents[1] / "core" / "api_clients"
    package_name = "selfie_painter_v2_test_registered_api_clients"

    logger_module = types.ModuleType("src.common.logger")

    class _LoggerStub:
        """测试用日志桩，避免加载 MaiBot 完整日志依赖。"""

        def debug(self, *args, **kwargs):
            """忽略调试日志。"""

        def info(self, *args, **kwargs):
            """忽略信息日志。"""

        def warning(self, *args, **kwargs):
            """忽略警告日志。"""

        def error(self, *args, **kwargs):
            """忽略错误日志。"""

    logger_module.get_logger = lambda name: _LoggerStub()
    sys.modules.setdefault("src", types.ModuleType("src"))
    sys.modules.setdefault("src.common", types.ModuleType("src.common"))
    sys.modules["src.common.logger"] = logger_module

    package = types.ModuleType(package_name)
    package.__path__ = [str(client_dir)]
    sys.modules[package_name] = package

    dummy_clients = {
        "openai_client": "OpenAIClient",
        "openai_chat_client": "OpenAIChatClient",
        "doubao_client": "DoubaoClient",
        "gemini_client": "GeminiClient",
        "modelscope_client": "ModelscopeClient",
        "shatangyun_client": "ShatangyunClient",
        "mengyuai_client": "MengyuaiClient",
        "zai_client": "ZaiClient",
        "comfyui_client": "ComfyUIClient",
    }
    for module_name, class_name in dummy_clients.items():
        module = types.ModuleType(f"{package_name}.{module_name}")
        module.__dict__[class_name] = type(class_name, (), {})
        sys.modules[f"{package_name}.{module_name}"] = module

    base_spec = importlib.util.spec_from_file_location(f"{package_name}.base_client", client_dir / "base_client.py")
    assert base_spec is not None and base_spec.loader is not None
    base_module = importlib.util.module_from_spec(base_spec)
    sys.modules[f"{package_name}.base_client"] = base_module
    base_spec.loader.exec_module(base_module)

    client_spec = importlib.util.spec_from_file_location(
        f"{package_name}.tuercha_nai_client", client_dir / "tuercha_nai_client.py"
    )
    assert client_spec is not None and client_spec.loader is not None
    client_module = importlib.util.module_from_spec(client_spec)
    sys.modules[f"{package_name}.tuercha_nai_client"] = client_module
    client_spec.loader.exec_module(client_module)

    init_spec = importlib.util.spec_from_file_location(
        package_name, client_dir / "__init__.py", submodule_search_locations=[str(client_dir)]
    )
    assert init_spec is not None and init_spec.loader is not None
    init_module = importlib.util.module_from_spec(init_spec)
    sys.modules[package_name] = init_module
    init_spec.loader.exec_module(init_module)
    return init_module


class _ActionStub:
    """提供 BaseApiClient 初始化所需的最小 Action 接口。"""

    log_prefix = "[test]"

    def get_config(self, key, default=None):
        """测试中不启用代理和详细调试。"""
        return default


class TuerchaNAIClientTest(unittest.TestCase):
    """验证 tuercha-NAI 客户端和接入文档约定一致。"""

    def test_build_inner_payload_maps_existing_model_fields_to_provider_contract(self):
        """现有模型字段应被映射为 tuercha-NAI 内层绘图 JSON。"""
        client = _load_tuercha_client_class()(_ActionStub())

        payload = client._build_inner_payload(
            prompt="1girl, solo",
            model_config={
                "custom_prompt_add": ", masterpiece",
                "negative_prompt_add": "lowres, text",
                "num_inference_steps": 35,
                "guidance_scale": 5,
                "sampler": "k_euler_ancestral",
                "seed": 123,
                "cfg": 0.5,
                "noise_schedule": "karras",
                "image_format": "webp",
            },
            size="832x1216",
            strength=None,
            input_image_base64=None,
        )

        self.assertEqual(
            payload,
            {
                "prompt": "1girl, solo, masterpiece",
                "size": [832, 1216],
                "steps": 28,
                "scale": 5,
                "sampler": "k_euler_ancestral",
                "image_format": "webp",
                "negative_prompt": "lowres, text",
                "seed": 123,
                "cfg_rescale": 0.5,
                "noise_schedule": "karras",
            },
        )

    def test_build_inner_payload_adds_i2i_when_input_image_is_available(self):
        """现有单图参考链路应变成提供方的 i2i 字段。"""
        client = _load_tuercha_client_class()(_ActionStub())

        payload = client._build_inner_payload(
            prompt="redraw this",
            model_config={},
            size="1024x1024",
            strength=0.6,
            input_image_base64="iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB",
        )

        self.assertEqual(
            payload["i2i"],
            {
                "image": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB",
                "strength": 0.6,
                "noise": 0,
            },
        )

    def test_extract_image_base64_reads_markdown_data_uri_response(self):
        """服务端 markdown 图片响应应被解析成纯 base64。"""
        client = _load_tuercha_client_class()(_ActionStub())

        success, result = client._extract_image_base64(
            {
                "choices": [
                    {
                        "message": {
                            "content": "![image_0](data:image/png;base64,iVBORw0KGgo=)\n<!-- seeds:[123] -->"
                        }
                    }
                ]
            }
        )

        self.assertIs(success, True)
        self.assertEqual(result, "iVBORw0KGgo=")

    def test_get_client_class_resolves_tuercha_nai_format(self):
        """配置里的混合大小写格式应能解析到新客户端。"""
        api_clients = _load_api_clients_init_module()

        self.assertIs(api_clients.get_client_class("tuercha-NAI"), api_clients.TuerchaNAIClient)
        self.assertIs(api_clients.get_client_class("tuercha-nai"), api_clients.TuerchaNAIClient)


if __name__ == "__main__":
    unittest.main()
