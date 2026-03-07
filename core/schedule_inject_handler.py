"""
POST_LLM 日程注入处理器（增强版）

在 LLM 生成回复之前，将麦麦当前的日程信息注入到 prompt 中，
让 LLM 知道麦麦"现在在做什么"，从而生成更有代入感的回复。

增强功能：
1. 意图识别：识别用户意图，决定是否注入
2. 对话上下文：记住最近的对话内容
3. 状态分析：分析当前日程状态
4. 智能优化：决定最优注入策略
5. 内容模板：润色注入内容

注入时机：POST_LLM（消息经过前处理后、LLM 调用前）
注入方式：在 llm_prompt 前面追加一段日程上下文
"""

import time
import logging
from typing import Dict, Optional, Tuple

from src.plugin_system.base.base_events_handler import BaseEventHandler
from src.plugin_system.base.component_types import (
    EventType,
    CustomEventHandlerResult,
)

from .inject.context_cache import get_context_cache
from .inject.intent_classifier import classify_intent, IntentType
from .inject.content_template import render_injection_content

logger = logging.getLogger(__name__)

# 内存级 per-stream 节流记录：{stream_id: last_inject_ts}
_stream_throttle: Dict[str, float] = {}
# 内存级 per-stream 消息计数：{stream_id: count_since_last_inject}
_stream_msg_count: Dict[str, int] = {}


class ScheduleInjectHandler(BaseEventHandler):
    """
    日程注入 EventHandler（增强版）

    在 POST_LLM 阶段将麦麦当前活动信息注入到 LLM prompt 中，
    让回复更贴合角色当前的"生活状态"。

    增强功能：
    - 意图识别：避免在技术问答等不相关场景注入
    - 对话上下文：连续对话时保持理解
    - 智能注入：根据分析结果优化注入策略
    """

    event_type = EventType.POST_LLM
    handler_name: str = "selfie_schedule_inject_handler"
    handler_description: str = "在 LLM 调用前注入麦麦当前日程信息（智能增强版）"
    weight: int = 10
    intercept_message: bool = True

    async def execute(
        self,
        message=None,
    ) -> Tuple[bool, bool, Optional[str], Optional[CustomEventHandlerResult], Optional[object]]:
        """
        执行日程注入

        Returns:
            (success, should_continue, optional_msg, custom_result, modified_message)
        """
        if message is None:
            return (True, True, None, None, None)

        # 检查全局开关
        enabled = self.get_config("schedule_inject.enabled", True)
        if not enabled:
            return (True, True, None, None, message)

        # 获取用户消息
        plain_text = getattr(message, "plain_text", "") or ""

        # 跳过命令消息（以 / 开头）
        if plain_text.strip().startswith("/"):
            return (True, True, None, None, message)

        # 获取 stream_id
        stream_id = getattr(message, "stream_id", None) or ""

        # ========== 智能注入增强 ==========

        # 1. 获取对话上下文缓存
        context_cache_ttl = self.get_config("schedule_inject.schedule_context_cache_ttl_minutes", 30)
        context_cache_max_turns = self.get_config("schedule_inject.schedule_context_cache_max_turns", 10)
        context_cache = get_context_cache(max_turns=context_cache_max_turns, ttl_minutes=context_cache_ttl)

        # 2. 意图识别
        intent_enabled = self.get_config("schedule_inject.schedule_intent_enable", True)
        should_inject = True
        inject_reason = ""

        if intent_enabled:
            intent_result = classify_intent(plain_text)
            should_inject, inject_reason = self._should_inject_by_intent(intent_result)

            logger.debug(
                f"[ScheduleInject] 意图识别: {intent_result.intent.value}, "
                f"置信度: {intent_result.confidence:.2f}, "
                f"是否注入: {should_inject}, 原因: {inject_reason}"
            )

            if not should_inject:
                return (True, True, None, None, message)

        # 3. 检查是否正在讨论日程话题
        is_discussing_schedule = context_cache.is_discussing_schedule()
        if is_discussing_schedule:
            logger.debug("[ScheduleInject] 检测到正在讨论日程话题，提高注入优先级")

        # 4. 检查 per-stream DB override
        try:
            override = await self._get_inject_override(stream_id)
            if override is not None and not override:
                return (True, True, None, None, message)
        except Exception as e:
            logger.debug(f"检查注入 override 失败: {e}")

        # 5. 节流检查（smart 模式）
        mode = self.get_config("schedule_inject.mode", "smart")
        if mode == "smart" and not self._should_inject_throttle(stream_id):
            # 增加消息计数
            _stream_msg_count[stream_id] = _stream_msg_count.get(stream_id, 0) + 1
            return (True, True, None, None, message)

        # ========== 获取日程信息 ==========

        try:
            from .schedule.schedule_manager import get_schedule_manager

            manager = get_schedule_manager()
            activity = await manager.get_current_activity()
            future_activities = await manager.get_future_activities(limit=3)
        except Exception as e:
            logger.warning(f"获取日程信息失败: {e}")
            return (True, True, None, None, message)

        # ========== 构建注入文本 ==========

        inject_text = self._build_inject_text_enhanced(
            activity=activity,
            future_activities=future_activities,
            user_message=plain_text,
            is_discussing_schedule=is_discussing_schedule,
        )

        if not inject_text:
            return (True, True, None, None, message)

        # ========== 注入到 llm_prompt ==========

        current_prompt = getattr(message, "llm_prompt", "") or ""
        message.llm_prompt = inject_text + "\n\n" + current_prompt

        # 更新节流状态
        _stream_throttle[stream_id] = time.time()
        _stream_msg_count[stream_id] = 0

        logger.debug(f"已注入日程信息到 stream {stream_id}")
        return (True, True, None, None, message)

    def _should_inject_by_intent(self, intent_result) -> Tuple[bool, str]:
        """
        根据意图判断是否应该注入

        Args:
            intent_result: 意图识别结果

        Returns:
            tuple: (是否注入, 原因)
        """
        intent = intent_result.intent

        # 询问日程 → 注入
        if intent == IntentType.SCHEDULE_QUERY:
            return True, "用户询问日程"

        # 修改日程 → 注入
        if intent == IntentType.SCHEDULE_MODIFY:
            return True, "用户想修改日程"

        # 技术问答 → 不注入
        if intent == IntentType.TECH_QUESTION:
            return False, "技术问答，不需要日程信息"

        # 命令 → 不注入
        if intent == IntentType.COMMAND:
            return False, "命令消息，不需要日程信息"

        # 闲聊 → 注入
        if intent == IntentType.CASUAL_CHAT:
            return True, "闲聊，可以注入日程增加自然感"

        # 其他 → 默认注入
        return True, "默认注入"

    def _should_inject_throttle(self, stream_id: str) -> bool:
        """
        smart 模式下的节流判断

        满足以下任一条件才注入：
        1. 该 stream 从未注入过
        2. 距离上次注入已超过 min_seconds
        3. 距离上次注入已收到 min_messages 条消息
        """
        min_seconds = self.get_config("schedule_inject.min_seconds", 300)
        min_messages = self.get_config("schedule_inject.min_messages", 5)

        last_ts = _stream_throttle.get(stream_id)
        if last_ts is None:
            return True

        elapsed = time.time() - last_ts
        if elapsed >= min_seconds:
            return True

        msg_count = _stream_msg_count.get(stream_id, 0)
        if msg_count >= min_messages:
            return True

        return False

    def _build_inject_text_enhanced(
        self, activity, future_activities, user_message: str = "", is_discussing_schedule: bool = False
    ) -> str:
        """
        构建增强版注入文本

        Args:
            activity: 当前活动
            future_activities: 未来活动列表
            user_message: 用户消息
            is_discussing_schedule: 是否正在讨论日程

        Returns:
            str: 注入文本
        """
        if activity is None:
            return ""

        # 获取当前活动信息
        current_activity_type = (
            activity.activity_type.value if hasattr(activity.activity_type, "value") else str(activity.activity_type)
        )
        current_description = activity.description
        current_mood = activity.mood if hasattr(activity, "mood") else "neutral"

        # 获取未来活动信息
        future_list = []
        if future_activities:
            for fa in future_activities[:3]:
                time_str = fa.time_point if hasattr(fa, "time_point") and fa.time_point else ""
                desc = fa.description if hasattr(fa, "description") else str(fa)
                if time_str:
                    future_list.append(f"{time_str} {desc}")
                else:
                    future_list.append(desc)

        # 使用内容模板引擎渲染
        inject_text = render_injection_content(
            current_activity=current_activity_type,
            current_description=current_description,
            current_mood=current_mood,
            next_activity=future_list[0] if future_list else "",
            next_time="",
            future_activities=future_list[1:] if len(future_list) > 1 else [],
        )

        return inject_text

    def _build_inject_text(self, activity, future_activities) -> str:
        """
        构建注入到 prompt 的日程文本（兼容旧版）
        """
        if activity is None:
            return ""

        lines = ["【可选上下文 - 麦麦当前日程】"]
        lines.append(f"现在：{activity.activity_type.value}（{activity.description}）")

        if future_activities:
            future_parts = []
            for fa in future_activities[:3]:
                time_str = fa.time_point if hasattr(fa, "time_point") and fa.time_point else ""
                if time_str:
                    future_parts.append(f"{time_str} {fa.description}")
                else:
                    future_parts.append(fa.description)
            if future_parts:
                lines.append(f"接下来：{'、'.join(future_parts)}")

        lines.append("把这些当作背景信息，自然地融入对话，不要刻意提及日程表。")
        return "\n".join(lines)

    async def _get_inject_override(self, stream_id: str) -> Optional[bool]:
        """
        从 DB 读取 per-stream 的注入开关 override

        Returns:
            True = 强制开启, False = 强制关闭, None = 使用全局配置
        """
        if not stream_id:
            return None

        try:
            from .schedule.schedule_manager import get_schedule_manager

            manager = get_schedule_manager()
            key = f"schedule_inject_enabled_override:{stream_id}"
            value = await manager.get_state(key)
            if value is None:
                return None
            return value.lower() in ("true", "1", "yes", "on")
        except Exception:
            return None
