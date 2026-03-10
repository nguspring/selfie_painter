"""
对话上下文缓存

用于保存最近 N 轮对话的摘要/关键句，支持连续对话理解。

功能：
1. 缓存最近的对话内容
2. 支持按时间过期（TTL）
3. 支持最大轮数限制
4. 全局共享（麦麦作为一个整体）
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import Optional


@dataclass
class ConversationTurn:
    """对话轮次"""

    timestamp: float  # 时间戳
    user_message: str  # 用户消息
    bot_response: str  # 机器人回复
    summary: str = ""  # 摘要（可选）


class ConversationContextCache:
    """
    对话上下文缓存

    保存最近的对话轮次，用于连续对话理解。

    使用示例：
        cache = ConversationContextCache(max_turns=10, ttl_minutes=30)

        # 添加对话轮次
        cache.add_turn("你在干嘛？", "我在写代码呢～")

        # 获取上下文
        context = cache.get_context()
        # 输出：["用户：你在干嘛？", "麦麦：我在写代码呢～"]
    """

    def __init__(self, max_turns: int = 10, ttl_minutes: int = 30):
        """
        初始化对话上下文缓存

        Args:
            max_turns: 最大轮数（默认10轮）
            ttl_minutes: 过期时间（分钟，默认30分钟）
        """
        self.max_turns = max_turns
        self.ttl_seconds = ttl_minutes * 60
        self._turns: deque[ConversationTurn] = deque(maxlen=max_turns)

    def add_turn(self, user_message: str, bot_response: str, summary: str = "") -> None:
        """
        添加一轮对话

        Args:
            user_message: 用户消息
            bot_response: 机器人回复
            summary: 摘要（可选）
        """
        turn = ConversationTurn(
            timestamp=time.time(),
            user_message=user_message[:200],  # 限制长度
            bot_response=bot_response[:200],
            summary=summary[:100] if summary else "",
        )
        self._turns.append(turn)

    def get_context(self, max_length: int = 500) -> str:
        """
        获取对话上下文

        Args:
            max_length: 最大字符长度

        Returns:
            str: 格式化的对话上下文
        """
        # 清理过期轮次
        self._cleanup_expired()

        if not self._turns:
            return ""

        parts: list[str] = []
        total_length = 0

        for turn in reversed(list(self._turns)):
            line = f"用户：{turn.user_message}\n麦麦：{turn.bot_response}"

            if total_length + len(line) > max_length:
                break

            parts.insert(0, line)
            total_length += len(line)

        return "\n\n".join(parts)

    def get_recent_messages(self, count: int = 3) -> list[str]:
        """
        获取最近 N 条用户消息

        Args:
            count: 数量

        Returns:
            list[str]: 用户消息列表
        """
        self._cleanup_expired()

        messages = []
        for turn in reversed(list(self._turns)):
            messages.insert(0, turn.user_message)
            if len(messages) >= count:
                break

        return messages

    def is_discussing_schedule(self) -> bool:
        """
        判断是否正在讨论日程话题

        通过关键词匹配判断最近的对话是否与日程相关。

        Returns:
            bool: 是否正在讨论日程
        """
        self._cleanup_expired()

        if not self._turns:
            return False

        schedule_keywords = [
            "日程",
            "安排",
            "计划",
            "今天",
            "明天",
            "昨天",
            "在干嘛",
            "在做什么",
            "忙",
            "闲",
            "起床",
            "睡觉",
            "吃饭",
            "休息",
            "工作",
        ]

        recent_messages = self.get_recent_messages(3)

        for msg in recent_messages:
            for keyword in schedule_keywords:
                if keyword in msg:
                    return True

        return False

    def clear(self) -> None:
        """清空缓存"""
        self._turns.clear()

    def _cleanup_expired(self) -> None:
        """清理过期轮次"""
        current_time = time.time()

        while self._turns:
            oldest = self._turns[0]
            if current_time - oldest.timestamp > self.ttl_seconds:
                self._turns.popleft()
            else:
                break

    @property
    def turn_count(self) -> int:
        """当前轮数"""
        return len(self._turns)


# 模块级单例实例（全局共享）
_cache_instance: Optional[ConversationContextCache] = None


def get_context_cache(max_turns: int = 10, ttl_minutes: int = 30) -> ConversationContextCache:
    """
    获取对话上下文缓存单例实例

    Args:
        max_turns: 最大轮数
        ttl_minutes: 过期时间（分钟）

    Returns:
        ConversationContextCache: 缓存实例
    """
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = ConversationContextCache(max_turns=max_turns, ttl_minutes=ttl_minutes)
    return _cache_instance
