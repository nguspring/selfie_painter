"""
日程质量评分器

用于评估生成的日程质量，输出分数和问题列表。

评分维度（总分 1.0）：
- 基础分：0.5（有日程就有基础分）
- 活动数量：0.2（8-15条满分，接近得0.5，太少得0）
- 描述长度：0.15（平均20-50字满分，接近得0.5，太短得0）
- 时间覆盖：0.15（覆盖7:00-23:00的比例）
- 警告惩罚：-0.05/条（最多扣0.3）

功能：
1. 评估日程质量
2. 识别具体问题
3. 提供修复建议
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .schedule_models import ScheduleItem

@dataclass
class QualityIssue:
    """质量问题"""

    severity: str  # "error" | "warning"
    category: str  # "count" | "length" | "coverage" | "format"
    message: str
    suggestion: str


@dataclass
class EvalResult:
    """评估结果"""

    score: float  # 0.0 - 1.0
    issues: list[str]  # 问题描述列表（用于重试 Prompt）
    details: dict[str, Any] = field(default_factory=dict)  # 详细信息
    quality_issues: list[QualityIssue] = field(default_factory=list)  # 结构化问题列表


class ScheduleQualityEvaluator:
    """
    日程质量评分器

    负责评估生成的日程质量，输出分数、问题列表和修复建议。

    使用示例：
        evaluator = ScheduleQualityEvaluator()
        result = evaluator.evaluate(items, warnings)

        if result.score < 0.8:
            print("质量问题：", result.issues)
    """

    # 评分参数
    MIN_ACTIVITIES = 8  # 最少活动数量
    MAX_ACTIVITIES = 15  # 最多活动数量
    MIN_DESC_LENGTH = 20  # 最短描述长度
    MAX_DESC_LENGTH = 50  # 最长描述长度
    TARGET_DESC_LENGTH = 35  # 目标描述长度

    # 时间覆盖范围（分钟）
    COVERAGE_START = 7 * 60  # 7:00
    COVERAGE_END = 23 * 60  # 23:00
    COVERAGE_TOTAL = COVERAGE_END - COVERAGE_START  # 16小时

    def __init__(self):
        """初始化评分器"""
        pass

    def evaluate(self, items: list[ScheduleItem], warnings: list[str] | None = None) -> EvalResult:
        """
        评估日程质量

        Args:
            items: 日程项列表
            warnings: 解析过程中的警告列表

        Returns:
            EvalResult: 评估结果（分数、问题列表、详细信息）

        示例：
            result = evaluator.evaluate(items, ["时间格式错误"])
            print(f"分数: {result.score}")
            print(f"问题: {result.issues}")
        """
        if warnings is None:
            warnings = []

        issues: list[str] = []
        quality_issues: list[QualityIssue] = []
        details: dict[str, Any] = {}

        # 基础分
        score = 0.5
        details["base_score"] = 0.5

        # 如果没有日程项，直接返回低分
        if not items:
            return EvalResult(
                score=0.0,
                issues=["没有生成任何日程项"],
                details={"error": "empty_schedule"},
                quality_issues=[
                    QualityIssue(
                        severity="error",
                        category="count",
                        message="没有生成任何日程项",
                        suggestion="请生成至少8条日程活动",
                    )
                ],
            )

        # 1. 活动数量评分 (0.2)
        count_score, count_issues, count_quality_issues = self._evaluate_count(items)
        score += count_score
        issues.extend(count_issues)
        quality_issues.extend(count_quality_issues)
        details["count_score"] = count_score
        details["activity_count"] = len(items)

        # 2. 描述长度评分 (0.15)
        length_score, length_issues, length_quality_issues = self._evaluate_description_length(items)
        score += length_score
        issues.extend(length_issues)
        quality_issues.extend(length_quality_issues)
        details["length_score"] = length_score
        details["avg_desc_length"] = sum(len(i.description) for i in items) / len(items) if items else 0

        # 3. 时间覆盖评分 (0.15)
        coverage_score, coverage_issues, coverage_quality_issues = self._evaluate_time_coverage(items)
        score += coverage_score
        issues.extend(coverage_issues)
        quality_issues.extend(coverage_quality_issues)
        details["coverage_score"] = coverage_score
        details["time_coverage"] = coverage_score / 0.15  # 转换为比例

        # 4. 警告惩罚 (-0.05/条，最多扣0.3)
        warning_penalty = min(len(warnings) * 0.05, 0.3)
        score -= warning_penalty
        details["warning_penalty"] = warning_penalty
        details["warning_count"] = len(warnings)

        if warnings:
            issues.append(f"解析警告：{', '.join(warnings)}")
            for w in warnings:
                quality_issues.append(
                    QualityIssue(
                        severity="warning",
                        category="format",
                        message=f"解析警告：{w}",
                        suggestion="检查输出格式是否符合要求",
                    )
                )

        # 确保分数在 0-1 范围内
        score = max(0.0, min(1.0, score))

        return EvalResult(score=score, issues=issues, details=details, quality_issues=quality_issues)

    def _evaluate_count(self, items: list[ScheduleItem]) -> tuple[float, list[str], list[QualityIssue]]:
        """
        评估活动数量

        Returns:
            tuple: (分数, 问题列表, 结构化问题列表)
        """
        issues: list[str] = []
        quality_issues: list[QualityIssue] = []
        count = len(items)

        if self.MIN_ACTIVITIES <= count <= self.MAX_ACTIVITIES:
            # 完美
            return 0.2, [], []
        elif count >= 6:
            # 接近要求
            issue_msg = f"活动数量偏少（{count}个，建议{self.MIN_ACTIVITIES}-{self.MAX_ACTIVITIES}个）"
            issues.append(issue_msg)
            quality_issues.append(
                QualityIssue(
                    severity="warning",
                    category="count",
                    message=issue_msg,
                    suggestion=f"建议增加{self.MIN_ACTIVITIES - count}个活动",
                )
            )
            return 0.1, issues, quality_issues
        else:
            # 不达标
            issue_msg = f"活动数量不足（{count}个，需要至少{self.MIN_ACTIVITIES}个）"
            issues.append(issue_msg)
            quality_issues.append(
                QualityIssue(
                    severity="error",
                    category="count",
                    message=issue_msg,
                    suggestion=f"请增加活动，确保至少有{self.MIN_ACTIVITIES}个",
                )
            )
            return 0.0, issues, quality_issues

    def _evaluate_description_length(self, items: list[ScheduleItem]) -> tuple[float, list[str], list[QualityIssue]]:
        """
        评估描述长度

        Returns:
            tuple: (分数, 问题列表, 结构化问题列表)
        """
        issues: list[str] = []
        quality_issues: list[QualityIssue] = []

        if not items:
            return 0.0, [], []

        avg_length = sum(len(i.description) for i in items) / len(items)

        if avg_length >= self.TARGET_DESC_LENGTH:
            # 达到目标
            return 0.15, [], []
        elif avg_length >= self.MIN_DESC_LENGTH:
            # 达到最低要求
            issue_msg = f"描述平均长度偏短（{avg_length:.1f}字，建议{self.TARGET_DESC_LENGTH}字以上）"
            issues.append(issue_msg)
            quality_issues.append(
                QualityIssue(
                    severity="warning",
                    category="length",
                    message=issue_msg,
                    suggestion="建议扩充活动描述，让描述更有生活感",
                )
            )
            return 0.075, issues, quality_issues
        else:
            # 不达标
            issue_msg = f"描述太短（平均{avg_length:.1f}字，需要至少{self.MIN_DESC_LENGTH}字）"
            issues.append(issue_msg)
            quality_issues.append(
                QualityIssue(
                    severity="error",
                    category="length",
                    message=issue_msg,
                    suggestion="请扩充每条活动的描述，让描述更详细、更有生活感",
                )
            )
            return 0.0, issues, quality_issues

    def _evaluate_time_coverage(self, items: list[ScheduleItem]) -> tuple[float, list[str], list[QualityIssue]]:
        """
        评估时间覆盖

        检查日程是否覆盖了 7:00-23:00 的时间段

        Returns:
            tuple: (分数, 问题列表, 结构化问题列表)
        """
        issues: list[str] = []
        quality_issues: list[QualityIssue] = []

        if not items:
            return 0.0, [], []

        # 创建时间覆盖数组（每分钟一个标记）
        covered = [False] * self.COVERAGE_TOTAL

        for item in items:
            start = max(item.start_min, self.COVERAGE_START) - self.COVERAGE_START
            end = min(item.end_min, self.COVERAGE_END) - self.COVERAGE_START

            if start < end:
                for i in range(start, end):
                    if 0 <= i < self.COVERAGE_TOTAL:
                        covered[i] = True

        # 计算覆盖率
        covered_minutes = sum(covered)
        coverage_ratio = covered_minutes / self.COVERAGE_TOTAL

        # 根据覆盖率给分
        score = coverage_ratio * 0.15

        if coverage_ratio < 0.8:
            # 找出空档时间段
            gaps = self._find_gaps(items)
            if gaps:
                gap_strs = [f"{s // 60:02d}:{s % 60:02d}-{e // 60:02d}:{e % 60:02d}" for s, e in gaps[:3]]
                issue_msg = f"时间覆盖不完整（覆盖率{coverage_ratio * 100:.1f}%），空档：{', '.join(gap_strs)}"
                issues.append(issue_msg)
                quality_issues.append(
                    QualityIssue(
                        severity="warning" if coverage_ratio >= 0.5 else "error",
                        category="coverage",
                        message=issue_msg,
                        suggestion="请在空档时间段添加活动，确保时间连续",
                    )
                )

        return score, issues, quality_issues

    def _find_gaps(self, items: list[ScheduleItem]) -> list[tuple[int, int]]:
        """
        找出时间空档

        Returns:
            list[tuple]: 空档列表 [(start_min, end_min), ...]
        """
        if not items:
            return [(self.COVERAGE_START, self.COVERAGE_END)]

        # 按开始时间排序
        sorted_items = sorted(items, key=lambda x: x.start_min)

        gaps = []
        current = self.COVERAGE_START

        for item in sorted_items:
            if item.start_min > current:
                # 发现空档
                gap_start = max(current, self.COVERAGE_START)
                gap_end = min(item.start_min, self.COVERAGE_END)
                if gap_start < gap_end:
                    gaps.append((gap_start, gap_end))
            current = max(current, item.end_min)

        # 检查末尾是否有空档
        if current < self.COVERAGE_END:
            gaps.append((current, self.COVERAGE_END))

        return gaps


# 模块级单例实例
_evaluator_instance: ScheduleQualityEvaluator | None = None


def get_quality_evaluator() -> ScheduleQualityEvaluator:
    """
    获取质量评分器单例实例

    Returns:
        ScheduleQualityEvaluator: 评分器实例
    """
    global _evaluator_instance
    if _evaluator_instance is None:
        _evaluator_instance = ScheduleQualityEvaluator()
    return _evaluator_instance


def evaluate_schedule_quality(items: list[ScheduleItem], warnings: list[str] | None = None) -> EvalResult:
    """
    快捷函数：评估日程质量

    Args:
        items: 日程项列表
        warnings: 解析警告列表

    Returns:
        EvalResult: 评估结果
    """
    return get_quality_evaluator().evaluate(items, warnings)
