"""
注入优化器

用于决定注入策略，如何最优地将日程信息注入到对话中。

策略：
- INSERT: 在合适位置插入新活动
- REPLACE: 替换已有活动
- APPEND: 追加到日程末尾
- SKIP: 跳过注入
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from .state_analyzer import TimeSlot, ScheduleAnalysis
from .intent_classifier import IntentType


class InjectStrategy(Enum):
    """注入策略"""

    INSERT = "insert"  # 插入
    REPLACE = "replace"  # 替换
    APPEND = "append"  # 追加
    SKIP = "skip"  # 跳过


@dataclass
class InjectDecision:
    """注入决策"""

    strategy: InjectStrategy
    target_slot: Optional[TimeSlot]  # 目标时间段
    reason: str  # 决策原因
    priority: int  # 优先级（1-5，5最高）


class InjectOptimizer:
    """
    注入优化器

    根据意图、日程分析结果、生活规律等信息，决定最优的注入策略。

    使用示例：
        optimizer = InjectOptimizer()
        decision = optimizer.optimize(
            intent=IntentType.SCHEDULE_QUERY,
            analysis=analysis,
            lifestyle="习惯晚睡"
        )

        if decision.strategy != InjectStrategy.SKIP:
            print("注入位置：", decision.target_slot)
    """

    def __init__(self):
        """初始化优化器"""
        pass

    def optimize(
        self, intent: IntentType, analysis: ScheduleAnalysis, lifestyle: str = "", user_preferences: str = ""
    ) -> InjectDecision:
        """
        决定最优注入策略

        Args:
            intent: 用户意图
            analysis: 日程分析结果
            lifestyle: 生活规律
            user_preferences: 用户偏好

        Returns:
            InjectDecision: 注入决策
        """
        # 技术问答或命令 → 跳过
        if intent in (IntentType.TECH_QUESTION, IntentType.COMMAND):
            return InjectDecision(
                strategy=InjectStrategy.SKIP, target_slot=None, reason=f"意图为 {intent.value}，不需要注入", priority=0
            )

        # 询问日程 → 高优先级注入
        if intent == IntentType.SCHEDULE_QUERY:
            return self._decide_for_query(analysis)

        # 修改日程 → 高优先级注入
        if intent == IntentType.SCHEDULE_MODIFY:
            return self._decide_for_modify(analysis, lifestyle)

        # 闲聊或其他 → 低优先级注入
        return InjectDecision(strategy=InjectStrategy.APPEND, target_slot=None, reason="默认追加式注入", priority=2)

    def _decide_for_query(self, analysis: ScheduleAnalysis) -> InjectDecision:
        """处理询问日程的决策"""
        # 如果有空档，建议填充
        if analysis.gaps:
            # 选择最大的空档
            largest_gap = max(analysis.gaps, key=lambda g: g.end_min - g.start_min)
            return InjectDecision(
                strategy=InjectStrategy.INSERT,
                target_slot=largest_gap,
                reason=f"发现空档 {largest_gap.format()}，建议填充",
                priority=4,
            )

        # 如果密度过低，建议增加活动
        if analysis.density < 0.3:
            return InjectDecision(
                strategy=InjectStrategy.APPEND, target_slot=None, reason="日程过松，可以增加活动", priority=3
            )

        # 正常状态，简单追加
        return InjectDecision(
            strategy=InjectStrategy.APPEND, target_slot=None, reason="日程正常，简单追加注入", priority=3
        )

    def _decide_for_modify(self, analysis: ScheduleAnalysis, lifestyle: str) -> InjectDecision:
        """处理修改日程的决策"""
        # 如果过密，建议替换而非增加
        if analysis.density > 0.8:
            return InjectDecision(
                strategy=InjectStrategy.REPLACE, target_slot=None, reason="日程过密，建议替换而非增加", priority=4
            )

        # 如果有空档，插入
        if analysis.gaps:
            smallest_gap = min(analysis.gaps, key=lambda g: g.end_min - g.start_min)
            return InjectDecision(
                strategy=InjectStrategy.INSERT,
                target_slot=smallest_gap,
                reason=f"在空档 {smallest_gap.format()} 插入新活动",
                priority=4,
            )

        # 默认追加
        return InjectDecision(strategy=InjectStrategy.APPEND, target_slot=None, reason="追加新活动", priority=3)

    def get_recommended_time(
        self, analysis: ScheduleAnalysis, activity_type: str = "relaxing", duration_minutes: int = 60
    ) -> Optional[TimeSlot]:
        """
        获取推荐的时间段

        Args:
            analysis: 日程分析结果
            activity_type: 活动类型
            duration_minutes: 所需时长（分钟）

        Returns:
            Optional[TimeSlot]: 推荐的时间段，没有合适时间段返回 None
        """
        if not analysis.gaps:
            return None

        # 找到足够大的空档
        for gap in sorted(analysis.gaps, key=lambda g: g.start_min):
            gap_duration = gap.end_min - gap.start_min
            if gap_duration >= duration_minutes:
                # 返回空档的前半部分
                return TimeSlot(gap.start_min, gap.start_min + duration_minutes)

        return None


# 模块级单例实例
_optimizer_instance: Optional[InjectOptimizer] = None


def get_inject_optimizer() -> InjectOptimizer:
    """
    获取注入优化器单例实例

    Returns:
        InjectOptimizer: 优化器实例
    """
    global _optimizer_instance
    if _optimizer_instance is None:
        _optimizer_instance = InjectOptimizer()
    return _optimizer_instance


def optimize_injection(
    intent: IntentType, analysis: ScheduleAnalysis, lifestyle: str = "", user_preferences: str = ""
) -> InjectDecision:
    """
    快捷函数：优化注入决策

    Args:
        intent: 用户意图
        analysis: 日程分析结果
        lifestyle: 生活规律
        user_preferences: 用户偏好

    Returns:
        InjectDecision: 注入决策
    """
    return get_inject_optimizer().optimize(
        intent=intent, analysis=analysis, lifestyle=lifestyle, user_preferences=user_preferences
    )
