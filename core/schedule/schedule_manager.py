"""
日程管理器：对外提供 async API，内部通过 asyncio.to_thread 调用 ScheduleDB。
"""

from __future__ import annotations

import asyncio
import datetime
import logging
from typing import Any

from .schedule_db import ScheduleDB
from .schedule_llm_generator import generate_schedule_via_llm
from .schedule_models import (
    ActivityInfo,
    ActivityType,
    ScheduleItem,
    from_db_row,
    is_minutes_in_range,
    schedule_item_to_activity_info,
    to_db_dict,
)
from .schedule_templates import get_template_schedule

logger = logging.getLogger(__name__)

_manager_instance: ScheduleManager | None = None


def get_schedule_manager() -> "ScheduleManager":
    """获取全局日程管理器。"""
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = ScheduleManager()
    return _manager_instance


class ScheduleManager:
    """进程级日程管理器。"""

    def __init__(self):
        """初始化数据库。"""
        self._db: ScheduleDB = ScheduleDB()

    async def ensure_db_initialized(self) -> None:
        """确保数据库 schema 已建立。"""
        await asyncio.to_thread(self._db.ensure_schema)

    async def ensure_today_schedule(self, plugin: Any | None = None) -> None:
        """确保今日有日程，优先模板，再异步尝试 LLM 覆盖。"""
        today = datetime.date.today().isoformat()
        items = await asyncio.to_thread(self._db.list_schedule_items, today)

        if not items:
            template_items = get_template_schedule(today)
            await asyncio.to_thread(
                self._db.replace_schedule_items,
                today,
                [to_db_dict(item) for item in template_items],
            )
            await asyncio.to_thread(self._db.set_state, "schedule_last_generated_date", today)
            await asyncio.to_thread(self._db.set_state, "schedule_last_generated_source", "template")

        if plugin is not None:
            _ = asyncio.create_task(self._try_llm_override(plugin, today))

    async def _try_llm_override(self, plugin: Any, target_date: str) -> None:
        """尝试使用 LLM 覆盖今日日程。"""
        try:
            model_id = str(plugin.get_config("schedule.model_id", "planner"))
            # 使用增强版生成器，传入 schedule_manager 以支持历史记忆
            items = await generate_schedule_via_llm(
                plugin=plugin,
                target_date=target_date,
                model_id=model_id,
                schedule_manager=self,  # 传入 self 以支持历史记忆
            )
            if not items:
                return

            await asyncio.to_thread(
                self._db.replace_schedule_items,
                target_date,
                [to_db_dict(item) for item in items],
            )
            await asyncio.to_thread(self._db.set_state, "schedule_last_generated_date", target_date)
            await asyncio.to_thread(self._db.set_state, "schedule_last_generated_source", "llm")
            logger.info("[ScheduleManager] LLM 覆盖日程成功: %s", target_date)
        except Exception as exc:
            logger.error("[ScheduleManager] LLM 覆盖异常: %s", exc, exc_info=True)

    @staticmethod
    def _pick_activity_fallback_item(items: list[ScheduleItem], current_minutes: int) -> ScheduleItem | None:
        """未命中时间区间时，选择最贴近“当前时刻”的活动项。

        规则：
        1. 优先选择“已经开始”的最后一项（start_min <= current_minutes 的最大项）
        2. 若当前时间早于当天首项，则回退到第一项
        """
        if not items:
            return None

        started_items = [item for item in items if item.start_min <= current_minutes]
        if started_items:
            return started_items[-1]

        return items[0]

    async def get_current_activity(self):
        """获取当前活动，永不返回 None。"""
        now = datetime.datetime.now()
        today = now.date().isoformat()
        current_minutes = now.hour * 60 + now.minute
        now_str = now.strftime("%H:%M")

        rows = await asyncio.to_thread(self._db.list_schedule_items, today)

        if rows:
            items = [from_db_row(row) for row in rows]
            for item in items:
                if is_minutes_in_range(current_minutes, item.start_min, item.end_min):
                    return schedule_item_to_activity_info(item, now_str)

            fallback_item = self._pick_activity_fallback_item(items, current_minutes)
            if fallback_item is not None:
                return schedule_item_to_activity_info(fallback_item, now_str)

        fallback_items = get_template_schedule(today)
        for item in fallback_items:
            if is_minutes_in_range(current_minutes, item.start_min, item.end_min):
                return schedule_item_to_activity_info(item, now_str)

        fallback_item = self._pick_activity_fallback_item(fallback_items, current_minutes)
        if fallback_item is not None:
            return schedule_item_to_activity_info(fallback_item, now_str)

        return ActivityInfo(
            activity_type=ActivityType.OTHER,
            description="日常活动",
            mood="neutral",
            time_point=now_str,
        )

    async def get_future_activities(self, limit: int = 3) -> list[Any]:
        """获取后续活动列表。"""
        now = datetime.datetime.now()
        today = now.date().isoformat()
        current_minutes = now.hour * 60 + now.minute

        rows = await asyncio.to_thread(self._db.list_schedule_items, today)
        items = [from_db_row(row) for row in rows]

        future = [item for item in items if item.start_min > current_minutes]
        return [schedule_item_to_activity_info(item) for item in future[: max(0, limit)]]

    async def list_schedule_items(self, schedule_date: str) -> list[ScheduleItem]:
        """按日期获取日程项列表。"""
        rows = await asyncio.to_thread(self._db.list_schedule_items, schedule_date)
        return [from_db_row(row) for row in rows]

    async def regen_today_schedule_via_llm(self, plugin: Any) -> bool:
        """手动触发 LLM 重生成。"""
        today = datetime.date.today().isoformat()
        model_id = str(plugin.get_config("schedule.model_id", "planner"))
        items = await generate_schedule_via_llm(plugin, today, model_id=model_id)
        if not items:
            return False

        await asyncio.to_thread(
            self._db.replace_schedule_items,
            today,
            [to_db_dict(item) for item in items],
        )
        await asyncio.to_thread(self._db.set_state, "schedule_last_generated_date", today)
        await asyncio.to_thread(self._db.set_state, "schedule_last_generated_source", "llm")
        return True

    async def get_inject_override(self, stream_id: str) -> bool | None:
        """读取注入覆盖开关。"""
        value = await asyncio.to_thread(self._db.get_state, f"schedule_inject_enabled_override:{stream_id}")
        if value is None:
            return None
        return value.lower() == "true"

    async def set_inject_override(self, stream_id: str, enabled: bool) -> None:
        """写入注入覆盖开关。"""
        await asyncio.to_thread(
            self._db.set_state,
            f"schedule_inject_enabled_override:{stream_id}",
            "true" if enabled else "false",
        )

    async def get_state(self, key: str) -> str | None:
        """读取状态。"""
        return await asyncio.to_thread(self._db.get_state, key)

    async def set_state(self, key: str, value: str) -> None:
        """写入状态。"""
        await asyncio.to_thread(self._db.set_state, key, value)

    # ========== 历史记忆相关方法 ==========

    async def get_history_schedule_items(self, days: int = 1) -> dict[str, list[Any]]:
        """
        获取历史日程数据。

        Args:
            days: 历史天数（默认1=昨天）

        Returns:
            dict[str, list]: 日期到日程项列表的映射
            例如：{"2026-03-01": [ScheduleItem, ...], "2026-03-02": [...]}

        示例：
            # 获取昨天的日程
            history = await manager.get_history_schedule_items(days=1)
            # 获取最近3天的日程
            history = await manager.get_history_schedule_items(days=3)
        """
        if days <= 0:
            return {}

        today = datetime.date.today()
        result: dict[str, list[Any]] = {}

        for i in range(1, days + 1):
            date = today - datetime.timedelta(days=i)
            date_str = date.isoformat()
            rows = await asyncio.to_thread(self._db.list_schedule_items, date_str)
            if rows:
                items = [from_db_row(row) for row in rows]
                result[date_str] = items

        return result

    async def get_history_schedule_summary(self, days: int = 1, max_length: int = 500) -> str:
        """
        获取历史日程摘要（用于 LLM 上下文）。

        将历史日程压缩为简短的摘要字符串，用于日程生成的连续性参考。

        Args:
            days: 历史天数（默认1=昨天）
            max_length: 最大字符长度限制

        Returns:
            str: 历史日程摘要

        示例输出：
            "昨天(2026-03-01)的日程：
            08:00-09:00 起床洗漱
            09:00-12:00 写代码
            ...
            主要活动：工作(4h)、休息(2h)、学习(3h)"
        """
        history = await self.get_history_schedule_items(days)

        if not history:
            return ""

        parts: list[str] = []
        total_length = 0

        for date_str, items in sorted(history.items(), reverse=True):
            # 计算各类型活动的时长
            type_durations: dict[str, int] = {}
            day_parts: list[str] = []

            for item in items:
                duration = item.end_min - item.start_min
                activity_type = item.activity_type
                type_durations[activity_type] = type_durations.get(activity_type, 0) + duration

                # 格式化时间
                start_h, start_m = divmod(item.start_min, 60)
                end_h, end_m = divmod(item.end_min, 60)
                time_str = f"{start_h:02d}:{start_m:02d}-{end_h:02d}:{end_m:02d}"
                day_parts.append(f"{time_str} {item.description}")

            # 活动类型统计（转换为小时）
            type_summary = ", ".join(
                f"{t}({d // 60}h)" for t, d in sorted(type_durations.items(), key=lambda x: -x[1])[:3]
            )

            day_str = f"{date_str}的日程：{'; '.join(day_parts[:5])}... 主要活动：{type_summary}"

            if total_length + len(day_str) > max_length:
                break

            parts.append(day_str)
            total_length += len(day_str)

        if not parts:
            return ""

        return "\n".join(parts)

    async def cleanup_old_schedule_data(self, retention_days: int) -> int:
        """
        清理旧的日程数据。

        Args:
            retention_days: 保留天数（-1=永久保留）

        Returns:
            int: 删除的记录数
        """
        return await asyncio.to_thread(self._db.cleanup_old_schedule_items, retention_days)
