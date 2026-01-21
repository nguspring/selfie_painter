"""
定时自拍功能的数据模型模块

包含配文类型枚举和配文权重配置。

v3.6.0: 精简模块，移除旧版叙事相关类（NarrativeScene, DailyNarrativeState, DEFAULT_NARRATIVE_SCRIPTS）
        这些功能已被 schedule_models.py 中的新版日程系统取代。
"""

from dataclasses import dataclass
from enum import Enum
from typing import List


class CaptionType(Enum):
    """
    配文类型枚举

    定义了5种不同的配文风格，用于生成自拍时的配文选择。
    """

    NARRATIVE = "narrative"  # 叙事式：延续日常故事线
    ASK = "ask"  # 询问式：征求意见（当前默认）
    SHARE = "share"  # 分享式：分享心情/状态
    MONOLOGUE = "monologue"  # 独白式：自言自语
    NONE = "none"  # 无配文：纯图片


@dataclass
class CaptionWeightConfig:
    """
    配文权重配置

    定义不同配文类型的选择权重，权重值越高被选中的概率越大。

    Attributes:
        narrative: 叙事式权重
        ask: 询问式权重
        share: 分享式权重
        monologue: 独白式权重
        none: 无配文权重
    """

    narrative: float = 0.35
    ask: float = 0.25
    share: float = 0.25
    monologue: float = 0.10
    none: float = 0.05

    def get_weights_list(self) -> List[float]:
        """
        返回权重列表，顺序与 CaptionType 枚举对应

        Returns:
            按 CaptionType 枚举顺序排列的权重列表
        """
        return [
            self.narrative,  # CaptionType.NARRATIVE
            self.ask,  # CaptionType.ASK
            self.share,  # CaptionType.SHARE
            self.monologue,  # CaptionType.MONOLOGUE
            self.none,  # CaptionType.NONE
        ]

    @classmethod
    def for_time_period(cls, hour: int) -> "CaptionWeightConfig":
        """
        根据时间段返回不同的权重配置

        - 早上 (6-11): 叙事式权重高，适合开启一天的故事
        - 下午 (12-17): 分享式权重高，适合分享日常活动
        - 晚上 (18-23): 独白式权重高，适合感性表达
        - 深夜 (0-5): 无配文权重高，减少打扰

        Args:
            hour: 24小时制的小时数 (0-23)

        Returns:
            对应时间段的权重配置
        """
        if 6 <= hour < 12:
            # 早上：叙事式权重高
            return cls(
                narrative=0.45,
                ask=0.20,
                share=0.20,
                monologue=0.10,
                none=0.05,
            )
        elif 12 <= hour < 18:
            # 下午：分享式权重高
            return cls(
                narrative=0.25,
                ask=0.25,
                share=0.35,
                monologue=0.10,
                none=0.05,
            )
        elif 18 <= hour < 24:
            # 晚上：独白式权重高
            return cls(
                narrative=0.20,
                ask=0.20,
                share=0.25,
                monologue=0.30,
                none=0.05,
            )
        else:
            # 深夜 (0-5)：无配文权重高
            return cls(
                narrative=0.15,
                ask=0.15,
                share=0.20,
                monologue=0.30,
                none=0.20,
            )
