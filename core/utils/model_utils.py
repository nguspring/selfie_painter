"""统一的模型配置工具

提供模型配置获取、负面提示词合并、Gemini/Zai 尺寸注入等公共方法，
消除 pic_action / pic_command / auto_selfie_task / api_clients 中的重复逻辑。
"""
from typing import Dict, Any, Optional, Callable
from src.common.logger import get_logger

logger = get_logger("mais_art.model_utils")


def get_model_config(
    config_getter: Callable,
    model_id: str,
    default_model_id: str = "model1",
    log_prefix: str = "",
) -> Optional[Dict[str, Any]]:
    """
    统一的模型配置获取。

    兼容 BaseAction/BaseCommand 的 self.get_config 和
    AutoSelfieTask 的 self.plugin.get_config。

    Args:
        config_getter: (key, default) -> value 形式的 callable
        model_id: 模型标识，如 "model1"
        default_model_id: model_id 找不到时回退的默认模型
        log_prefix: 日志前缀

    Returns:
        模型配置字典，或 None
    """
    # 主路径：直接读嵌套 dict
    model_config = config_getter(f"models.{model_id}", None)
    if isinstance(model_config, dict) and model_config.get("base_url"):
        return model_config

    # 回退：逐字段组装
    fields = [
        "name", "base_url", "api_key", "format", "model",
        "fixed_size_enabled", "default_size", "seed",
        "guidance_scale", "num_inference_steps", "watermark",
        "custom_prompt_add", "negative_prompt_add", "artist",
        "support_img2img", "auto_recall_delay",
        # 以下字段代码中有默认值，不在 config_schema 中暴露，
        # 但保留在 fields 列表中以支持用户手动配置时的回退组装
        "cfg", "sampler", "nocache", "noise_schedule",
        "img2img_model_index", "image_upload_url",
        "default_width", "default_height",
        "safety_settings",
    ]
    assembled = {}
    for field in fields:
        val = config_getter(f"models.{model_id}.{field}", None)
        if val is not None:
            assembled[field] = val

    if assembled.get("base_url"):
        logger.debug(f"{log_prefix} 模型 {model_id} 配置逐字段组装完成")
        return assembled

    # 尝试 default_model_id
    if model_id != default_model_id:
        logger.warning(f"{log_prefix} 模型 {model_id} 配置不存在，尝试默认模型 {default_model_id}")
        fallback = config_getter(f"models.{default_model_id}", None)
        if isinstance(fallback, dict) and fallback.get("base_url"):
            return fallback

    logger.warning(f"{log_prefix} 模型配置未找到: {model_id}")
    return None


def merge_negative_prompt(
    model_config: Dict[str, Any],
    extra_negative: str,
) -> Dict[str, Any]:
    """
    将额外的负面提示词合并进 model_config。
    返回浅拷贝，不修改原 dict。
    """
    if not extra_negative:
        return model_config
    config = dict(model_config)
    existing = config.get("negative_prompt_add", "")
    if existing:
        config["negative_prompt_add"] = f"{existing}, {extra_negative}"
    else:
        config["negative_prompt_add"] = extra_negative
    return config


def inject_llm_original_size(
    model_config: Dict[str, Any],
    llm_original_size: str,
) -> Dict[str, Any]:
    """
    对 Gemini/Zai 格式，注入 _llm_original_size。
    返回浅拷贝，不修改原 dict。非 Gemini/Zai 格式时直接返回原 dict。
    """
    api_format = model_config.get("format", "openai")
    if api_format in ("gemini", "zai") and llm_original_size:
        config = dict(model_config)
        config["_llm_original_size"] = llm_original_size
        return config
    return model_config
