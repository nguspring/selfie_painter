"""提示词优化模式解析工具。"""

from __future__ import annotations

from typing import Any, Callable

PromptOptimizerMode = str

VALID_PROMPT_OPTIMIZER_MODES: tuple[str, ...] = ("sd", "natural_language")
VALID_PROMPT_OPTIMIZER_OVERRIDES: tuple[str, ...] = ("follow_global", "sd", "natural_language")


def normalize_prompt_optimizer_mode(value: Any, default: PromptOptimizerMode = "sd") -> PromptOptimizerMode:
    """标准化全局优化模式。"""
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in VALID_PROMPT_OPTIMIZER_MODES:
            return normalized
    return default


def normalize_prompt_optimizer_override(value: Any, default: str = "follow_global") -> str:
    """标准化模型级优化模式覆盖值。"""
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in VALID_PROMPT_OPTIMIZER_OVERRIDES:
            return normalized
    return default


def resolve_effective_prompt_optimizer_mode(
    get_config: Callable[[str, Any], Any],
    model_id: str | None = None,
) -> PromptOptimizerMode:
    """按“模型覆盖优先，其次全局配置”的规则解析手动画图优化模式。"""
    global_mode = normalize_prompt_optimizer_mode(get_config("prompt_optimizer.mode", "sd"))
    if not model_id:
        return global_mode

    override_mode = normalize_prompt_optimizer_override(
        get_config(f"models.{model_id}.optimizer_mode_override", "follow_global")
    )
    if override_mode == "follow_global":
        return global_mode
    return normalize_prompt_optimizer_mode(override_mode, global_mode)


__all__ = [
    "PromptOptimizerMode",
    "VALID_PROMPT_OPTIMIZER_MODES",
    "VALID_PROMPT_OPTIMIZER_OVERRIDES",
    "normalize_prompt_optimizer_mode",
    "normalize_prompt_optimizer_override",
    "resolve_effective_prompt_optimizer_mode",
]
