"""
活动状态分析器

用于分析当前日程的状态，找出空档、冲突、过密过松等问题。

分析结果：
- 空档时间段
- 时间冲突
- 活动密度（过密/过松）
- 重复主题
- 与生活规律的冲突
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class TimeSlot:
    """时间段"""

    start_min: int  # 开始时间（分钟）
    end_min: int  # 结束时间（分钟）

    def format(self) -> str:
        """格式化为字符串"""
        start_h, start_m = divmod(self.start_min, 60)
        end_h, end_m = divmod(self.end_min, 60)
        return f"{start_h:02d}:{start_m:02d}-{end_h:02d}:{end_m:02d}"


@dataclass
class ScheduleAnalysis:
    """日程分析结果"""

    # 空档时间段
    gaps: list[TimeSlot] = field(default_factory=list)

    # 时间冲突
    conflicts: list[tuple[TimeSlot, TimeSlot]] = field(default_factory=list)

    # 活动密度（0.0-1.0，0=过松，1=过密）
    density: float = 0.5

    # 主要活动类型
    main_activities: list[str] = field(default_factory=list)

    # 问题列表
    issues: list[str] = field(default_factory=list)

    # 建议
    suggestions: list[str] = field(default_factory=list)

    @property
    def has_issues(self) -> bool:
        """是否有问题"""
        return bool(self.gaps or self.conflicts or self.issues)


class ActivityStateAnalyzer:
    """
    活动状态分析器

    分析当前日程的状态，提供改进建议。

    使用示例：
        analyzer = ActivityStateAnalyzer()
        analysis = analyzer.analyze(items)

        if analysis.has_issues:
            print("发现问题：", analysis.issues)
            print("建议：", analysis.suggestions)
    """

    # 时间范围
    DAY_START = 7 * 60  # 7:00
    DAY_END = 23 * 60  # 23:00

    # 密度阈值
    DENSITY_LOW = 0.3  # 过松
    DENSITY_HIGH = 0.8  # 过密

    def __init__(self):
        """初始化分析器"""
        pass

    def analyze(self, items: list[Any], lifestyle: str = "") -> ScheduleAnalysis:
        """
        分析日程状态

        Args:
            items: 日程项列表（ScheduleItem 或类似结构）
            lifestyle: 生活规律描述

        Returns:
            ScheduleAnalysis: 分析结果
        """
        analysis = ScheduleAnalysis()

        if not items:
            analysis.issues.append("没有日程数据")
            analysis.suggestions.append("需要生成日程")
            return analysis

        # 1. 分析空档
        analysis.gaps = self._find_gaps(items)
        if analysis.gaps:
            gap_strs = [g.format() for g in analysis.gaps[:3]]
            analysis.issues.append(f"时间空档：{', '.join(gap_strs)}")
            analysis.suggestions.append("在空档时间段添加活动")

        # 2. 分析冲突
        analysis.conflicts = self._find_conflicts(items)
        if analysis.conflicts:
            analysis.issues.append(f"发现 {len(analysis.conflicts)} 处时间冲突")
            analysis.suggestions.append("调整冲突的活动时间")

        # 3. 计算密度
        analysis.density = self._calculate_density(items)
        if analysis.density < self.DENSITY_LOW:
            analysis.issues.append("日程过于稀疏")
            analysis.suggestions.append("增加更多活动安排")
        elif analysis.density > self.DENSITY_HIGH:
            analysis.issues.append("日程过于紧凑")
            analysis.suggestions.append("适当安排休息时间")

        # 4. 分析主要活动类型
        analysis.main_activities = self._get_main_activities(items)

        # 5. 检查生活规律冲突
        if lifestyle:
            lifestyle_issues = self._check_lifestyle_conflicts(items, lifestyle)
            analysis.issues.extend(lifestyle_issues)

        return analysis

    def _find_gaps(self, items: list[Any]) -> list[TimeSlot]:
        """找出时间空档"""
        if not items:
            return [TimeSlot(self.DAY_START, self.DAY_END)]

        # 按开始时间排序
        sorted_items = sorted(items, key=lambda x: getattr(x, "start_min", 0))

        gaps = []
        current = self.DAY_START

        for item in sorted_items:
            start = getattr(item, "start_min", 0)
            end = getattr(item, "end_min", 0)

            if start > current:
                # 发现空档
                gap_start = max(current, self.DAY_START)
                gap_end = min(start, self.DAY_END)
                if gap_start < gap_end and gap_end - gap_start >= 30:  # 至少30分钟才算空档
                    gaps.append(TimeSlot(gap_start, gap_end))

            current = max(current, end)

        # 检查末尾
        if current < self.DAY_END:
            remaining = self.DAY_END - current
            if remaining >= 30:
                gaps.append(TimeSlot(current, self.DAY_END))

        return gaps

    def _find_conflicts(self, items: list[Any]) -> list[tuple[TimeSlot, TimeSlot]]:
        """找出时间冲突"""
        conflicts = []

        for i, item1 in enumerate(items):
            for item2 in items[i + 1 :]:
                start1 = getattr(item1, "start_min", 0)
                end1 = getattr(item1, "end_min", 0)
                start2 = getattr(item2, "start_min", 0)
                end2 = getattr(item2, "end_min", 0)

                # 检查重叠
                if start1 < end2 and start2 < end1:
                    slot1 = TimeSlot(start1, end1)
                    slot2 = TimeSlot(start2, end2)
                    conflicts.append((slot1, slot2))

        return conflicts

    def _calculate_density(self, items: list[Any]) -> float:
        """计算活动密度"""
        if not items:
            return 0.0

        total_minutes = self.DAY_END - self.DAY_START
        covered_minutes = 0

        # 创建时间覆盖数组
        covered = [False] * total_minutes

        for item in items:
            start = max(getattr(item, "start_min", 0), self.DAY_START) - self.DAY_START
            end = min(getattr(item, "end_min", 0), self.DAY_END) - self.DAY_START

            for i in range(start, end):
                if 0 <= i < total_minutes:
                    covered[i] = True

        covered_minutes = sum(covered)
        return covered_minutes / total_minutes

    def _get_main_activities(self, items: list[Any]) -> list[str]:
        """获取主要活动类型"""
        type_durations: dict[str, int] = {}

        for item in items:
            activity_type = getattr(item, "activity_type", "other")
            duration = getattr(item, "end_min", 0) - getattr(item, "start_min", 0)
            type_durations[activity_type] = type_durations.get(activity_type, 0) + duration

        # 按时长排序
        sorted_types = sorted(type_durations.items(), key=lambda x: -x[1])
        return [t for t, _ in sorted_types[:3]]

    def _check_lifestyle_conflicts(self, items: list[Any], lifestyle: str) -> list[str]:
        """检查生活规律冲突"""
        issues = []

        # 检查早起/晚起冲突
        if "晚起" in lifestyle or "起不来" in lifestyle:
            for item in items:
                start = getattr(item, "start_min", 0)
                if start < 8 * 60 and "起床" in getattr(item, "description", ""):
                    issues.append("早起活动与生活规律冲突（习惯晚起）")
                    break

        # 检查晚睡冲突
        if "早睡" in lifestyle:
            for item in items:
                end = getattr(item, "end_min", 0)
                if end > 23 * 60:
                    issues.append("晚间活动与生活规律冲突（习惯早睡）")
                    break

        return issues

    def get_current_state_description(self, items: list[Any], current_time_min: int) -> str:
        """
        获取当前状态的描述

        Args:
            items: 日程项列表
            current_time_min: 当前时间（分钟）

        Returns:
            str: 状态描述
        """
        if not items:
            return "目前没有安排"

        # 找到当前活动
        for item in items:
            start = getattr(item, "start_min", 0)
            end = getattr(item, "end_min", 0)

            if start <= current_time_min < end:
                _activity_type = getattr(item, "activity_type", "other")
                description = getattr(item, "description", "在忙")
                mood = getattr(item, "mood", "neutral")

                # 根据心情调整描述
                mood_modifiers = {
                    "happy": "开心地",
                    "sleepy": "迷迷糊糊地",
                    "focused": "专心地",
                    "tired": "有点累地",
                    "excited": "兴奋地",
                    "bored": "无聊地",
                }

                modifier = mood_modifiers.get(mood, "")

                return f"{modifier}{description}" if modifier else description

        # 找下一个活动
        for item in sorted(items, key=lambda x: getattr(x, "start_min", 0)):
            start = getattr(item, "start_min", 0)
            if start > current_time_min:
                start_h, start_m = divmod(start, 60)
                return f"接下来 {start_h:02d}:{start_m:02d} {item.description}"

        return "今天的安排已经结束了"


# 模块级单例实例
_analyzer_instance: Optional[ActivityStateAnalyzer] = None


def get_state_analyzer() -> ActivityStateAnalyzer:
    """
    获取状态分析器单例实例

    Returns:
        ActivityStateAnalyzer: 分析器实例
    """
    global _analyzer_instance
    if _analyzer_instance is None:
        _analyzer_instance = ActivityStateAnalyzer()
    return _analyzer_instance


def analyze_schedule_state(items: list[Any], lifestyle: str = "") -> ScheduleAnalysis:
    """
    快捷函数：分析日程状态

    Args:
        items: 日程项列表
        lifestyle: 生活规律描述

    Returns:
        ScheduleAnalysis: 分析结果
    """
    return get_state_analyzer().analyze(items, lifestyle)
