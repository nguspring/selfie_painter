"""
Wardrobe selector (v2.0 - 智能场景匹配版)。

核心功能：
1. 自定义场景匹配：一句话格式"在XX的时候穿XX"，LLM 智能解析
2. 每日随机穿搭：从 daily_outfits 随机选一套（同一天固定）
3. 季节建议：根据当前季节给出穿搭建议

优先级：
1. 用户命令（/dr wear）
2. selfie.prompt_prefix（用户配置的衣服）
3. 场景匹配（自定义场景）
4. 日程中的 outfit
5. 每日随机
"""

from __future__ import annotations

import hashlib
import random
from datetime import datetime
from collections.abc import Callable
from typing import Any, Protocol


class HasDescription(Protocol):
    """任何拥有 description 属性的对象（ScheduleItem / ActivityInfo 等）。"""

    @property
    def description(self) -> str: ...



def get_season() -> str:
    """根据当前月份判断季节。"""
    month: int = datetime.now().month
    if month in [3, 4, 5]:
        return "spring"
    elif month in [6, 7, 8]:
        return "summer"
    elif month in [9, 10, 11]:
        return "autumn"
    else:
        return "winter"


def get_season_suggestion(season: str) -> str:
    """获取季节穿搭建议。"""
    suggestions: dict[str, str] = {
        "spring": "春天气温适中，可以选择薄外套或毛衣",
        "summer": "夏天炎热，建议选择短袖、裙子等清凉穿搭",
        "autumn": "秋天气温转凉，建议选择长袖、薄外套",
        "winter": "冬天寒冷，建议选择厚外套、毛衣、围巾等保暖穿搭",
    }
    return suggestions.get(season, "")


def parse_scene_rule(rule: str) -> tuple[str, str] | None:
    """
    解析自定义场景规则（一句话格式）。

    支持格式：
    - "睡觉的时候穿可爱睡衣" -> ("睡觉", "可爱睡衣")
    - "在实验室的时候穿实验服" -> ("实验室", "实验服")
    - "下雨天穿雨衣" -> ("下雨天", "雨衣")
    - "去约会的时候穿洛丽塔" -> ("约会", "洛丽塔")

    Args:
        rule: 场景规则字符串

    Returns:
        tuple: (场景关键词, 服装) 或 None（解析失败）
    """
    # 常见的关键词分隔符
    separators: list[str] = [
        "的时候穿",
        "的时候，穿",
        "时穿",
        "时，穿",
        "穿",
    ]

    for sep in separators:
        if sep in rule:
            parts: list[str] = rule.split(sep, 1)
            if len(parts) == 2:
                scene: str = parts[0].strip()
                outfit: str = parts[1].strip()

                # 清理场景描述中的冗余词
                scene = scene.replace("在", "").replace("去", "").strip()

                if scene and outfit:
                    return (scene, outfit)

    return None


def match_custom_scene(
    description: str,
    custom_scenes: list[str],
) -> str | None:
    """
    匹配自定义场景。

    Args:
        description: 活动描述
        custom_scenes: 自定义场景规则列表

    Returns:
        str: 匹配到的服装（未匹配返回 None）
    """
    description_lower: str = description.lower()

    for rule in custom_scenes:
        parsed: tuple[str, str] | None = parse_scene_rule(rule)
        if parsed:
            scene, outfit = parsed

            # 场景关键词匹配（支持模糊匹配）
            scene_lower: str = scene.lower()
            if scene_lower in description_lower or any(keyword in description_lower for keyword in scene_lower.split()):
                return outfit

    return None



def build_simple_wardrobe_config(get_config: Callable[..., Any]) -> dict[str, Any]:
    """
    从插件配置构造简洁版衣柜配置字典。

    Args:
        get_config: 插件的 get_config 方法（或兼容的可调用对象）

    Returns:
        dict[str, Any]: 衣柜配置字典
    """
    return {
        "enabled": True,
        "daily_outfits": get_config("wardrobe.daily_outfits", []),
        "auto_scene_change": get_config("wardrobe.auto_scene_change", True),
        "custom_scenes": get_config("wardrobe.custom_scenes", []),
    }

def select_outfit_from_schedule(
    schedule_item: HasDescription | None,
    wardrobe_config: dict[str, Any],
    temp_override: str = "",
) -> str:
    """
    从日程获取穿搭。

    优先级（从高到低）：
    1. temp_override（wear 命令设置的临时穿搭）
    2. 场景匹配（custom_scenes）
    3. 日程中的 outfit
    4. 每日随机（daily_outfits）

    Args:
        schedule_item: 当前时段的日程项
        wardrobe_config: 衣柜配置
        temp_override: 临时穿搭覆盖（最高优先级）

    Returns:
        str: 穿搭描述（如果没有则返回空字符串）
    """
    if not wardrobe_config.get("enabled", False):
        return ""

    # 最高优先级：wear 命令设置的临时穿搭
    if temp_override:
        return temp_override

    # 自动场景换装
    if wardrobe_config.get("auto_scene_change", True) and schedule_item:
        custom_scenes: list[str] = wardrobe_config.get("custom_scenes", [])
        matched_outfit: str | None = match_custom_scene(
            description=schedule_item.description,
            custom_scenes=custom_scenes,
        )
        if matched_outfit:
            return matched_outfit

        # 日程中有穿搭信息（仅 ScheduleItem 等带 outfit 属性的对象）
        outfit_val: str = getattr(schedule_item, "outfit", "")
        if outfit_val:
            return outfit_val

    # 从每日穿搭中随机选
    daily_outfits: list[str] = wardrobe_config.get("daily_outfits", [])
    if daily_outfits:
        # 使用日期作为种子，保证同一天选同一套
        today: str = datetime.now().strftime("%Y-%m-%d")
        seed: int = int(hashlib.sha256(f"wardrobe-{today}".encode()).hexdigest()[:8], 16)
        rng: random.Random = random.Random(seed)
        return rng.choice(daily_outfits)

    return ""


def build_wardrobe_info_for_prompt(wardrobe_config: dict[str, Any]) -> str:
    """
    构建 LLM prompt 中的衣柜信息。

    Args:
        wardrobe_config: 衣柜配置

    Returns:
        str: 格式化的衣柜信息
    """
    if not wardrobe_config.get("enabled", False):
        return "（衣柜系统未启用，请根据活动场景自行选择合适的穿搭）"

    parts: list[str] = []

    # 每日穿搭
    daily_outfits: list[str] = wardrobe_config.get("daily_outfits", [])
    if daily_outfits:
        parts.append(f"日常穿搭：{', '.join(daily_outfits)}")

    # 自定义场景换装
    custom_scenes: list[str] = wardrobe_config.get("custom_scenes", [])
    if custom_scenes and wardrobe_config.get("auto_scene_change", True):
        scene_list: list[str] = []
        for rule in custom_scenes:
            parsed: tuple[str, str] | None = parse_scene_rule(rule)
            if parsed:
                scene, outfit = parsed
                scene_list.append(f"{scene}→{outfit}")
        if scene_list:
            parts.append(f"场景换装：{', '.join(scene_list)}")

    # 季节建议
    season: str = get_season()
    season_suggestion: str = get_season_suggestion(season)
    if season_suggestion:
        parts.append(f"当前季节：{season}（{season_suggestion}）")

    return "\n".join(parts)


_TEMP_OVERRIDE_KEY: str = "wardrobe.temp_override"


async def load_temp_override() -> str:
    """
    从数据库读取临时穿搭覆盖。

    返回当天设置的临时穿搭，跨天自动失效。

    Returns:
        str: 穿搭描述（空字符串表示无覆盖）
    """
    try:
        import json as _json

        from ..schedule.schedule_manager import get_schedule_manager

        manager = get_schedule_manager()
        await manager.ensure_db_initialized()
        raw: str | None = await manager.get_state(_TEMP_OVERRIDE_KEY)
        if not raw:
            return ""
        data: dict[str, str] = _json.loads(raw)
        today: str = datetime.now().strftime("%Y-%m-%d")
        if data.get("date") != today:
            return ""
        return data.get("outfit", "")
    except Exception:
        return ""


async def save_temp_override(outfit: str) -> None:
    """
    持久化临时穿搭覆盖。

    Args:
        outfit: 穿搭描述（空字符串清除覆盖）
    """
    import json as _json

    from ..schedule.schedule_manager import get_schedule_manager

    manager = get_schedule_manager()
    await manager.ensure_db_initialized()
    if not outfit:
        await manager.set_state(_TEMP_OVERRIDE_KEY, "")
        return
    today: str = datetime.now().strftime("%Y-%m-%d")
    payload: str = _json.dumps({"outfit": outfit, "date": today}, ensure_ascii=False)
    await manager.set_state(_TEMP_OVERRIDE_KEY, payload)


# 兼容旧版接口
def select_outfit_for_activity(
    config: dict[str, Any],
    state: dict[str, Any] | None,
    today_date: str,
    activity_type: str,
    description: str = "",
) -> tuple[str, str]:
    """
    兼容旧版的选择接口。

    Args:
        config: 衣柜配置
        state: 状态（新版不需要）
        today_date: 日期
        activity_type: 活动类型
        description: 活动描述

    Returns:
        tuple: (穿搭描述, 原因说明)
    """
    if not config.get("enabled", False):
        return ("", "衣柜系统未启用")

    # 场景匹配（新版自定义场景）
    if config.get("auto_scene_change", True):
        custom_scenes: list[str] = config.get("custom_scenes", [])
        matched_outfit: str | None = match_custom_scene(
            description=description,
            custom_scenes=custom_scenes,
        )
        if matched_outfit:
            return (matched_outfit, "匹配到自定义场景")

    # 从每日穿搭随机选
    daily_outfits: list[str] = config.get("daily_outfits", [])
    if daily_outfits:
        seed: int = int(hashlib.sha256(f"wardrobe-{today_date}".encode()).hexdigest()[:8], 16)
        rng: random.Random = random.Random(seed)
        outfit: str = rng.choice(daily_outfits)
        return (outfit, "每日随机选择")

    return ("", "没有可用的穿搭")
