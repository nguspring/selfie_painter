"""Wardrobe translator (selfie_painter_v2).

把衣柜系统返回的中文穿搭短语翻译成适合 SD 的英文提示词。
自动自拍和手动自拍共用本模块，避免中文穿搭被 NovelAI 等模型以 CJK 规则拒绝。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from src.common.logger import get_logger

logger = get_logger("mais_art.wardrobe")

# 预定义的中文穿搭 → 英文 SD 标签映射
# 命中本地映射可跳过 LLM 调用，既省 token 又保证稳定输出
_PREDEFINED_OUTFIT_MAP: dict[str, str] = {
    "哥特洛丽塔": "gothic lolita dress, frilled lace, elegant dark fashion",
    "宽松休闲装": "oversized casual outfit, relaxed everyday wear",
    "黑丝JK": "school uniform, black stockings, pleated skirt",
    "白丝JK": "school uniform, white stockings, pleated skirt",
    "连衣裙": "floral dress",
    "短裙": "short skirt, stylish casual outfit",
    "机能风服装": "techwear outfit, functional fashion",
    "可爱服装": "cute outfit, soft fashion details",
    "可爱睡衣": "cute pajamas, cozy sleepwear",
    "运动服": "sportswear, athletic outfit",
    "实验服": "lab coat, research outfit",
    "雨衣": "raincoat, weatherproof outerwear",
    "洛丽塔": "lolita dress, elegant frills",
}


def _has_cjk(text: str) -> bool:
    """检测字符串是否含 CJK 统一表意文字"""
    return any("\u4e00" <= ch <= "\u9fff" for ch in text)


async def translate_wardrobe_outfit_prompt(
    outfit_prompt: str,
    config_getter: Callable[..., Any],
    log_prefix: str = "[Wardrobe]",
) -> str:
    """将衣柜返回的中文穿搭短语转换为适合 SD 的英文提示词

    处理顺序：
    1. 无 CJK → 原样返回（纯英文穿搭直接放行）
    2. 命中本地映射表 → 返回映射值（免 LLM 调用）
    3. 调用提示词优化器翻译 → 校验翻译结果无 CJK 才采用
    4. 翻译失败或结果仍含 CJK → 返回空字符串（丢弃穿搭，避免污染提示词）

    Args:
        outfit_prompt: 衣柜系统选出的穿搭短语（可能含中文）
        config_getter: 插件配置读取函数 (key, default) -> value，
            用于读取 prompt_optimizer 自定义 API 配置
        log_prefix: 日志前缀

    Returns:
        翻译后的英文提示词；无 CJK 时原样返回；翻译失败时返回空字符串
    """
    outfit_prompt_clean: str = outfit_prompt.strip()
    if not outfit_prompt_clean:
        return ""

    # 无 CJK 直接放行，省去后续开销
    if not _has_cjk(outfit_prompt_clean):
        return outfit_prompt_clean

    # 本地映射命中，跳过 LLM
    mapped: str = _PREDEFINED_OUTFIT_MAP.get(outfit_prompt_clean, "")
    if mapped:
        logger.info(f"{log_prefix} 中文穿搭命中本地映射 → {outfit_prompt_clean} => {mapped}")
        return mapped

    # 兜底：调提示词优化器做翻译
    try:
        from ..utils import optimize_prompt

        logger.info(f"{log_prefix} 检测到中文穿搭，尝试翻译为英文提示词 → {outfit_prompt_clean}")
        custom_base_url: str = str(config_getter("prompt_optimizer.custom_api_base_url", ""))
        custom_api_key: str = str(config_getter("prompt_optimizer.custom_api_key", ""))
        custom_model: str = str(config_getter("prompt_optimizer.custom_api_model", ""))
        translate_success, translated_outfit = await optimize_prompt(
            outfit_prompt_clean,
            log_prefix=f"{log_prefix} [wardrobe-translate]",
            scene_only=False,
            custom_api_base_url=custom_base_url,
            custom_api_key=custom_api_key,
            custom_api_model=custom_model,
        )
    except Exception as translate_exc:
        logger.warning(f"{log_prefix} 翻译中文穿搭失败，跳过注入: {translate_exc}")
        return ""

    translated_outfit_clean: str = translated_outfit.strip() if isinstance(translated_outfit, str) else ""
    # 校验翻译结果：仍含 CJK 视为失败，避免把中文透传给拒绝 CJK 的模型
    if translate_success and translated_outfit_clean and not _has_cjk(translated_outfit_clean):
        logger.info(f"{log_prefix} 中文穿搭已翻译为英文提示词 → {translated_outfit_clean}")
        return translated_outfit_clean

    logger.info(f"{log_prefix} 翻译结果不可用，跳过注入 → {outfit_prompt_clean}")
    return ""
