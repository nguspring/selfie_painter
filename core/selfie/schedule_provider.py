"""
日程适配层

提供统一的日程/活动信息接口：
- PlanningPluginProvider: 读取 autonomous_planning 插件的 SQLite 数据库
- get_schedule_provider(): 工厂函数，自动选择可用的 provider
"""

import datetime
from dataclasses import dataclass
from enum import Enum

from src.common.logger import get_logger

logger = get_logger("auto_selfie.schedule")


class ActivityType(Enum):
    """活动类型枚举"""
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
    """活动信息数据类 - 统一的活动描述格式"""
    activity_type: ActivityType
    description: str          # 活动描述（中文）
    mood: str = "neutral"     # 情绪
    time_point: str = ""      # 时间点 "HH:MM"


class ScheduleProvider:
    """日程提供者基类"""

    async def get_current_activity(self) -> ActivityInfo:
        """获取当前时间对应的活动信息"""
        raise NotImplementedError


class EmbeddedScheduleProvider(ScheduleProvider):
    """
    内置日程提供者
    
    从 selfie_painter_v2 内置的 SQLite 数据库读取日程，
    替代原来依赖外部 autonomous_planning 插件的方案。
    """

    async def get_current_activity(self) -> ActivityInfo:
        """获取当前时间对应的活动信息（永远返回非 None）"""
        try:
            from ..schedule.schedule_manager import get_schedule_manager

            manager = get_schedule_manager()
            return await manager.get_current_activity()
        except Exception as e:
            logger.warning(f"从内置日程获取活动失败，使用默认值: {e}")
            return ActivityInfo(
                activity_type=ActivityType.OTHER,
                description="日常活动",
                mood="neutral",
                time_point=datetime.datetime.now().strftime("%H:%M"),
            )


def get_schedule_provider() -> ScheduleProvider:
    """
    获取日程提供者实例（永远返回可用的 provider）
    
    使用内置日程系统，不再依赖外部插件。
    """
    return EmbeddedScheduleProvider()
