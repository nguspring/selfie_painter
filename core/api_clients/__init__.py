"""API客户端模块

支持多种图片生成API：
- OpenAI 格式 (OpenAI, 硅基流动, NewAPI等)
- OpenAI Chat 格式 (通过 chat/completions 接口生图)
- Doubao 豆包格式
- Gemini 格式
- Modelscope 魔搭格式
- Shatangyun 砂糖云格式 (NovelAI)
- Mengyuai 梦羽AI格式
- Zai 格式 (Gemini转发)
- ComfyUI 格式 (本地ComfyUI工作流)
"""

from typing import Dict, Any, Tuple, Optional

from .base_client import BaseApiClient
from .openai_client import OpenAIClient
from .openai_chat_client import OpenAIChatClient
from .doubao_client import DoubaoClient
from .gemini_client import GeminiClient
from .modelscope_client import ModelscopeClient
from .shatangyun_client import ShatangyunClient
from .mengyuai_client import MengyuaiClient
from .zai_client import ZaiClient
from .comfyui_client import ComfyUIClient

__all__ = [
    'BaseApiClient',
    'OpenAIClient',
    'OpenAIChatClient',
    'DoubaoClient',
    'GeminiClient',
    'ModelscopeClient',
    'ShatangyunClient',
    'MengyuaiClient',
    'ZaiClient',
    'ComfyUIClient',
    'ApiClient',
    'get_client_class',
    'generate_image_standalone',
]


# API格式到客户端类的映射
CLIENT_MAPPING = {
    'openai': OpenAIClient,
    'openai-chat': OpenAIChatClient,
    'doubao': DoubaoClient,
    'gemini': GeminiClient,
    'modelscope': ModelscopeClient,
    'shatangyun': ShatangyunClient,
    'mengyuai': MengyuaiClient,
    'zai': ZaiClient,
    'comfyui': ComfyUIClient,
}


def get_client_class(api_format: str):
    """根据API格式获取对应的客户端类

    Args:
        api_format: API格式名称

    Returns:
        客户端类，如果不存在则返回OpenAIClient作为默认
    """
    return CLIENT_MAPPING.get(api_format.lower(), OpenAIClient)


class ApiClient:
    """统一的API客户端包装类

    根据模型配置中的format字段自动选择正确的客户端
    提供与BaseApiClient相同的接口
    """

    def __init__(self, action_instance):
        self.action = action_instance
        self._clients = {}  # 缓存客户端实例

    def _get_client(self, api_format: str):
        """获取指定格式的客户端实例（带缓存）"""
        if api_format not in self._clients:
            client_class = get_client_class(api_format)
            self._clients[api_format] = client_class(self.action)
        return self._clients[api_format]

    async def generate_image(
        self,
        prompt: str,
        model_config: dict,
        size: str,
        strength: Optional[float] = None,
        input_image_base64: Optional[str] = None,
        max_retries: int = 2
    ):
        """生成图片，自动选择正确的API客户端

        Args:
            prompt: 提示词
            model_config: 模型配置（必须包含format字段）
            size: 图片尺寸
            strength: 图生图强度
            input_image_base64: 输入图片的base64编码
            max_retries: 最大重试次数

        Returns:
            (成功标志, 结果数据或错误信息)
        """
        api_format = model_config.get("format", "openai")
        client = self._get_client(api_format)
        return await client.generate_image(
            prompt=prompt,
            model_config=model_config,
            size=size,
            strength=strength,
            input_image_base64=input_image_base64,
            max_retries=max_retries
        )


class _StandaloneActionStub:
    """独立调用时使用的 action 桩对象

    提供 BaseApiClient 所需的最小接口（get_config, log_prefix），
    不依赖真实的 Action 实例。
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.log_prefix = "[standalone]"
        self._config = config or {}

    def get_config(self, key: str, default=None):
        """从扁平化 key（如 'proxy.enabled'）读取配置"""
        parts = key.split(".")
        obj = self._config
        for part in parts:
            if isinstance(obj, dict):
                obj = obj.get(part)
            else:
                return default
            if obj is None:
                return default
        return obj


async def generate_image_standalone(
    prompt: str,
    model_config: Dict[str, Any],
    size: str = "1024x1024",
    negative_prompt: Optional[str] = None,
    strength: Optional[float] = None,
    input_image_base64: Optional[str] = None,
    max_retries: int = 2,
    extra_config: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, str]:
    """独立的图片生成接口，不依赖 Action 实例

    供外部插件（如 Maizone）直接调用，只做图片生成，不发送消息。

    Args:
        prompt: 提示词
        model_config: 模型配置字典，必须包含 base_url, api_key, format, model 等字段
        size: 图片尺寸，默认 "1024x1024"
        negative_prompt: 额外负面提示词，会合并到 model_config 的 negative_prompt_add
        strength: 图生图强度（0.0-1.0），仅图生图时使用
        input_image_base64: 输入图片的 base64 编码（图生图用）
        max_retries: 最大重试次数
        extra_config: 额外配置（如 proxy 设置），格式同 config.toml 结构

    Returns:
        (success, image_data): success 为 True 时 image_data 是 base64 或 URL
    """
    from src.common.logger import get_logger
    from ..utils import merge_negative_prompt
    _logger = get_logger("mais_art.standalone")

    # 合并负面提示词
    merged_config = merge_negative_prompt(model_config, negative_prompt) if negative_prompt else model_config

    # 创建桩对象
    stub = _StandaloneActionStub(config=extra_config)

    # 获取客户端
    api_format = merged_config.get("format", "openai")
    client_class = get_client_class(api_format)
    client = client_class(stub)

    _logger.info(f"[standalone] 独立生图: format={api_format}, model={merged_config.get('model', '?')}, size={size}")

    try:
        success, result = await client.generate_image(
            prompt=prompt,
            model_config=merged_config,
            size=size,
            strength=strength,
            input_image_base64=input_image_base64,
            max_retries=max_retries,
        )
        if success:
            _logger.info(f"[standalone] 生图成功，数据长度: {len(result) if result else 0}")
        else:
            _logger.warning(f"[standalone] 生图失败: {result}")
        return success, result
    except Exception as e:
        _logger.error(f"[standalone] 生图异常: {e!r}")
        return False, f"独立生图异常: {str(e)[:100]}"
