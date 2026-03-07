"""
内容模板引擎

用于将日程信息渲染成符合麦麦风格的描述文本。

功能：
1. 根据人设风格润色描述
2. 生成自然、有生活感的文本
3. 支持多种模板风格
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import random


@dataclass
class TemplateContext:
    """模板上下文"""

    nickname: str = "麦麦"
    personality: str = "是一个女大学生"
    reply_style: str = ""
    current_activity: str = ""
    current_description: str = ""
    current_mood: str = "neutral"
    next_activity: str = ""
    next_time: str = ""


class ContentTemplateEngine:
    """
    内容模板引擎

    将日程信息渲染成符合麦麦风格的文本。

    使用示例：
        engine = ContentTemplateEngine()
        text = engine.render_injection_content(
            current_description="在写代码",
            current_mood="focused",
            next_activity="休息",
            next_time="15:00"
        )
    """

    # 心情修饰词
    MOOD_MODIFIERS = {
        "happy": ["开心地", "愉快地", "心情不错地"],
        "sleepy": ["迷迷糊糊地", "打着哈欠", "睡眼惺忪地"],
        "focused": ["专心地", "全神贯注地", "认真地"],
        "tired": ["有点累地", "疲惫地", "打着精神"],
        "excited": ["兴奋地", "激动地", "跃跃欲试地"],
        "bored": ["无聊地", "百无聊赖地", "发着呆"],
        "calm": ["平静地", "淡定地", "从容地"],
        "anxious": ["有点焦虑地", "坐立不安地"],
        "neutral": ["", "", ""],
    }

    # 活动描述模板
    ACTIVITY_TEMPLATES = {
        "working": [
            "在{description}",
            "{description}中",
            "正忙着{description}",
        ],
        "studying": [
            "在{description}",
            "正在学习，{description}",
        ],
        "relaxing": [
            "正在{description}",
            "{description}放松一下",
        ],
        "eating": [
            "正在{description}",
            "{description}～",
        ],
        "sleeping": [
            "在睡觉",
            "正在休息",
            "睡着了",
        ],
        "hobby": [
            "在{description}",
            "正{description}",
        ],
        "other": [
            "在{description}",
            "正在{description}",
        ],
    }

    # 注入文本模板
    INJECTION_TEMPLATES = [
        "现在{activity}，{mood_modifier}{description}",
        "目前正在{activity}",
        "{mood_modifier}{description}中",
    ]

    def __init__(self):
        """初始化模板引擎"""
        pass

    def render_injection_content(
        self,
        current_activity: str = "",
        current_description: str = "",
        current_mood: str = "neutral",
        next_activity: str = "",
        next_time: str = "",
        future_activities: list[str] | None = None,
        nickname: str = "麦麦",
        reply_style: str = "",
    ) -> str:
        """
        渲染注入内容

        Args:
            current_activity: 当前活动类型
            current_description: 当前活动描述
            current_mood: 当前心情
            next_activity: 下一个活动
            next_time: 下一个活动时间
            future_activities: 未来活动列表
            nickname: 昵称
            reply_style: 回复风格

        Returns:
            str: 渲染后的注入文本

        示例输出：
            【当前状态】
            正在写代码，专心地敲键盘

            【接下来】
            15:00 休息一下
            16:00 继续工作
        """
        parts = []

        # 当前状态
        if current_description:
            mood_modifier = self._get_mood_modifier(current_mood)
            activity_text = self._render_activity(current_activity, current_description)

            current_text = f"【当前状态】\n{mood_modifier}{activity_text}"
            parts.append(current_text)

        # 接下来的安排
        if next_activity or (future_activities and len(future_activities) > 0):
            next_parts = ["【接下来】"]

            if next_activity and next_time:
                next_parts.append(f"{next_time} {next_activity}")

            if future_activities:
                for act in future_activities[:3]:
                    next_parts.append(act)

            parts.append("\n".join(next_parts))

        # 如果没有任何内容，返回空
        if not parts:
            return ""

        # 添加提示语
        hint = "\n把这些当作背景信息，自然地融入对话，不要刻意提及日程表。"

        return "\n\n".join(parts) + hint

    def render_simple_injection(
        self, current_description: str, current_mood: str = "neutral", next_activities: list[str] | None = None
    ) -> str:
        """
        渲染简单注入内容

        简化版，只包含核心信息。

        Args:
            current_description: 当前活动描述
            current_mood: 当前心情
            next_activities: 接下来的活动列表

        Returns:
            str: 简单的注入文本
        """
        mood_modifier = self._get_mood_modifier(current_mood)

        text = "【可选上下文 - 麦麦当前日程】\n"
        text += f"现在：{mood_modifier}{current_description}"

        if next_activities:
            text += f"\n接下来：{', '.join(next_activities[:3])}"

        text += "\n把这些当作背景信息，自然地融入对话，不要刻意提及日程表。"

        return text

    def _get_mood_modifier(self, mood: str) -> str:
        """获取心情修饰词"""
        modifiers = self.MOOD_MODIFIERS.get(mood, [""])
        return random.choice(modifiers)

    def _render_activity(self, activity_type: str, description: str) -> str:
        """渲染活动描述"""
        templates = self.ACTIVITY_TEMPLATES.get(activity_type, self.ACTIVITY_TEMPLATES["other"])
        template = random.choice(templates)
        return template.format(description=description)


# 模块级单例实例
_engine_instance: Optional[ContentTemplateEngine] = None


def get_content_template_engine() -> ContentTemplateEngine:
    """
    获取内容模板引擎单例实例

    Returns:
        ContentTemplateEngine: 模板引擎实例
    """
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = ContentTemplateEngine()
    return _engine_instance


def render_injection_content(
    current_activity: str = "",
    current_description: str = "",
    current_mood: str = "neutral",
    next_activity: str = "",
    next_time: str = "",
    future_activities: list[str] | None = None,
    nickname: str = "麦麦",
    reply_style: str = "",
) -> str:
    """
    快捷函数：渲染注入内容

    Args:
        current_activity: 当前活动类型
        current_description: 当前活动描述
        current_mood: 当前心情
        next_activity: 下一个活动
        next_time: 下一个活动时间
        future_activities: 未来活动列表
        nickname: 昵称
        reply_style: 回复风格

    Returns:
        str: 渲染后的注入文本
    """
    return get_content_template_engine().render_injection_content(
        current_activity=current_activity,
        current_description=current_description,
        current_mood=current_mood,
        next_activity=next_activity,
        next_time=next_time,
        future_activities=future_activities,
        nickname=nickname,
        reply_style=reply_style,
    )
