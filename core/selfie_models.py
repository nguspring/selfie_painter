"""
定时自拍功能的数据模型模块

包含配文类型枚举、叙事场景定义、每日叙事状态和配文权重配置等数据类型。
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


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
class NarrativeScene:
    """
    叙事场景定义

    描述一个特定时间段的场景，包含场景ID、时间范围、描述、
    图片生成提示词和推荐的配文类型。

    Attributes:
        scene_id: 场景ID，如 "morning_wakeup"
        time_start: 开始时间，格式 "HH:MM"，如 "07:00"
        time_end: 结束时间，格式 "HH:MM"，如 "09:00"
        description: 场景描述
        image_prompt: 图片生成提示词
        caption_type: 推荐的配文类型
        prev_scene_ids: 前置场景ID列表（用于连贯性判断）
    """

    scene_id: str
    time_start: str
    time_end: str
    description: str
    image_prompt: str
    caption_type: CaptionType
    prev_scene_ids: Optional[List[str]] = None


@dataclass
class DailyNarrativeState:
    """
    每日叙事状态

    跟踪当天的叙事进度，包括已完成的场景、上下文记忆和当前情绪等。

    Attributes:
        date: 当前日期，格式 "YYYY-MM-DD"
        script_id: 当日剧本ID
        completed_scenes: 已完成的场景ID列表
        context_memory: 上下文记忆，存储场景相关的信息
        current_mood: 当前情绪
        last_caption: 上一条配文内容
        last_scene_time: 上一个场景时间
    """

    date: str
    script_id: str = "default"
    completed_scenes: List[str] = field(default_factory=list)
    context_memory: List[Dict[str, Any]] = field(default_factory=list)
    current_mood: str = "neutral"
    last_caption: str = ""
    last_scene_time: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """
        转换为字典，用于JSON序列化

        Returns:
            包含所有属性的字典
        """
        return {
            "date": self.date,
            "script_id": self.script_id,
            "completed_scenes": self.completed_scenes.copy(),
            "context_memory": [m.copy() for m in self.context_memory],
            "current_mood": self.current_mood,
            "last_caption": self.last_caption,
            "last_scene_time": self.last_scene_time,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DailyNarrativeState":
        """
        从字典创建实例

        Args:
            data: 包含状态数据的字典

        Returns:
            DailyNarrativeState 实例
        """
        return cls(
            date=data.get("date", ""),
            script_id=data.get("script_id", "default"),
            completed_scenes=data.get("completed_scenes", []).copy(),
            context_memory=[m.copy() for m in data.get("context_memory", [])],
            current_mood=data.get("current_mood", "neutral"),
            last_caption=data.get("last_caption", ""),
            last_scene_time=data.get("last_scene_time", ""),
        )

    def add_completed_scene(self, scene_id: str, caption: str, timestamp: str) -> None:
        """
        添加已完成的场景

        将场景ID添加到已完成列表，并更新上下文记忆。

        Args:
            scene_id: 场景ID
            caption: 该场景的配文内容
            timestamp: 完成时间戳
        """
        if scene_id not in self.completed_scenes:
            self.completed_scenes.append(scene_id)

        # 添加到上下文记忆
        self.context_memory.append(
            {"scene_id": scene_id, "caption": caption, "timestamp": timestamp}
        )

        # 更新最后的配文和时间
        self.last_caption = caption
        self.last_scene_time = timestamp

    def is_scene_completed(self, scene_id: str) -> bool:
        """
        检查场景是否已完成

        Args:
            scene_id: 要检查的场景ID

        Returns:
            如果场景已完成返回 True，否则返回 False
        """
        return scene_id in self.completed_scenes


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


# 默认日常剧本定义
# 注意：时间范围已优化，消除了重叠问题
# 匹配常用的 schedule_times: ['08:00', '12:00', '16:00', '19:00']
DEFAULT_NARRATIVE_SCRIPTS: Dict[str, List[NarrativeScene]] = {
    "default": [
        # 早晨场景 - 匹配 08:00
        NarrativeScene(
            scene_id="morning_wakeup",
            time_start="06:30",
            time_end="08:30",
            description="刚睡醒",
            image_prompt="bedroom, pajamas, sleepy, morning light, just woke up, messy hair",
            caption_type=CaptionType.NARRATIVE,
            prev_scene_ids=None,
        ),
        NarrativeScene(
            scene_id="morning_breakfast",
            time_start="08:30",
            time_end="10:00",
            description="吃早餐",
            image_prompt="kitchen, breakfast, coffee, toast, morning, cozy",
            caption_type=CaptionType.SHARE,
            prev_scene_ids=["morning_wakeup"],
        ),
        NarrativeScene(
            scene_id="morning_ready",
            time_start="10:00",
            time_end="11:30",
            description="准备出门",
            image_prompt="mirror, getting ready, outfit, makeup, natural light",
            caption_type=CaptionType.ASK,
            prev_scene_ids=["morning_wakeup", "morning_breakfast"],
        ),
        # 午间场景 - 匹配 12:00
        NarrativeScene(
            scene_id="lunch_time",
            time_start="11:30",
            time_end="13:00",
            description="午餐时间",
            image_prompt="restaurant, lunch, food, eating, happy",
            caption_type=CaptionType.SHARE,
            prev_scene_ids=["morning_ready"],
        ),
        NarrativeScene(
            scene_id="afternoon_rest",
            time_start="13:00",
            time_end="15:00",
            description="午后小憩",
            image_prompt="cafe, relaxing, tea, afternoon, window light",
            caption_type=CaptionType.MONOLOGUE,
            prev_scene_ids=["lunch_time"],
        ),
        # 下午场景 - 匹配 16:00
        NarrativeScene(
            scene_id="afternoon_activity",
            time_start="15:00",
            time_end="17:30",
            description="下午活动",
            image_prompt="outdoor, walking, park, sunshine, casual",
            caption_type=CaptionType.SHARE,
            prev_scene_ids=["afternoon_rest"],
        ),
        NarrativeScene(
            scene_id="evening_dinner",
            time_start="17:30",
            time_end="19:00",
            description="晚餐时间",
            image_prompt="dinner, home cooking, warm light, evening",
            caption_type=CaptionType.SHARE,
            prev_scene_ids=["afternoon_activity"],
        ),
        # 晚间场景 - 匹配 19:00
        NarrativeScene(
            scene_id="evening_relax",
            time_start="19:00",
            time_end="21:30",
            description="晚间放松",
            image_prompt="living room, couch, relaxing, tv, cozy evening",
            caption_type=CaptionType.MONOLOGUE,
            prev_scene_ids=["evening_dinner"],
        ),
        NarrativeScene(
            scene_id="night_routine",
            time_start="21:30",
            time_end="23:00",
            description="睡前准备",
            image_prompt="bedroom, skincare, night routine, soft light, peaceful",
            caption_type=CaptionType.NARRATIVE,
            prev_scene_ids=["evening_relax"],
        ),
        NarrativeScene(
            scene_id="night_sleep",
            time_start="23:00",
            time_end="01:00",
            description="准备睡觉",
            image_prompt="bed, night, sleepy, dimmed light, goodnight",
            caption_type=CaptionType.NARRATIVE,
            prev_scene_ids=["night_routine"],
        ),
    ],
    "weekend": [
        # 周末早晨 - 匹配 08:00（用户要求 07:00-11:00）
        NarrativeScene(
            scene_id="weekend_morning",
            time_start="07:00",
            time_end="11:00",
            description="周末懒觉",
            image_prompt="bedroom, lazy morning, weekend, sleeping in, cozy",
            caption_type=CaptionType.NARRATIVE,
            prev_scene_ids=None,
        ),
        # 周末早午餐 - 匹配 12:00（消除与早晨的重叠）
        NarrativeScene(
            scene_id="weekend_brunch",
            time_start="11:00",
            time_end="13:30",
            description="周末早午餐",
            image_prompt="brunch, pancakes, coffee, weekend vibes, relaxed",
            caption_type=CaptionType.SHARE,
            prev_scene_ids=["weekend_morning"],
        ),
        # 周末外出 - 匹配 16:00
        NarrativeScene(
            scene_id="weekend_outing",
            time_start="13:30",
            time_end="18:00",
            description="周末外出",
            image_prompt="outdoor, shopping, friends, weekend fun, city",
            caption_type=CaptionType.SHARE,
            prev_scene_ids=["weekend_brunch"],
        ),
        # 周末晚间 - 匹配 19:00
        NarrativeScene(
            scene_id="weekend_evening",
            time_start="18:00",
            time_end="22:00",
            description="周末晚间",
            image_prompt="home, movie night, popcorn, cozy, weekend",
            caption_type=CaptionType.MONOLOGUE,
            prev_scene_ids=["weekend_outing"],
        ),
    ],
}
