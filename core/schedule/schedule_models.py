"""
日程数据模型及辅助函数。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any


class ActivityType(Enum):
    """活动类型枚举。"""

    SLEEPING = "sleeping"
    WAKING_UP = "waking_up"
    EATING = "eating"
    WORKING = "working"
    STUDYING = "studying"
    EXERCISING = "exercising"
    RELAXING = "relaxing"
    SOCIALIZING = "socializing"
    COMMUTING = "commuting"
    HOBBY = "hobby"
    SELF_CARE = "self_care"
    OTHER = "other"


@dataclass
class ActivityInfo:
    """统一的活动描述格式。"""

    activity_type: ActivityType
    description: str
    mood: str = "neutral"
    time_point: str = ""


@dataclass
class ScheduleItem:
    """日程项模型。"""

    schedule_date: str
    start_min: int
    end_min: int
    activity_type: str
    description: str
    mood: str = "neutral"
    outfit: str = ""  # 穿搭（日程生成时确定）
    source: str = "template"


def parse_hhmm(s: str) -> int:
    """'HH:MM' -> 分钟数(0-1439)。非法则抛 ValueError。"""
    matched = re.fullmatch(r"(\d{1,2}):(\d{2})", s.strip())
    if not matched:
        raise ValueError(f"无效时间格式: {s!r}")
    hour, minute = int(matched.group(1)), int(matched.group(2))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"时间范围越界: {s!r}")
    return hour * 60 + minute


def is_minutes_in_range(current: int, start: int, end: int) -> bool:
    """判断 current 是否在 [start, end) 区间内（支持跨午夜）。"""
    if start <= end:
        return start <= current < end
    return current >= start or current < end


def to_db_dict(item: ScheduleItem) -> dict[str, Any]:
    """ScheduleItem 转 DB 字典。"""
    return {
        "start_min": int(item.start_min),
        "end_min": int(item.end_min),
        "activity_type": item.activity_type,
        "description": item.description,
        "mood": item.mood,
        "outfit": item.outfit,
        "source": item.source,
    }


def from_db_row(row: dict[str, Any]) -> ScheduleItem:
    """DB 行字典转 ScheduleItem。"""
    return ScheduleItem(
        schedule_date=str(row.get("schedule_date", "")),
        start_min=int(row.get("start_min", 0)),
        end_min=int(row.get("end_min", 0)),
        activity_type=str(row.get("activity_type", "other")),
        description=str(row.get("description", "")),
        mood=str(row.get("mood", "neutral")),
        outfit=str(row.get("outfit", "")),
        source=str(row.get("source", "template")),
    )


def schedule_item_to_activity_info(item: ScheduleItem, current_time: str = ""):
    """ScheduleItem -> ActivityInfo。"""
    try:
        activity_type = ActivityType(item.activity_type)
    except ValueError:
        activity_type = ActivityType.OTHER

    return ActivityInfo(
        activity_type=activity_type,
        description=item.description,
        mood=item.mood,
        time_point=current_time,
    )
