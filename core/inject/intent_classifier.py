"""
意图分类器

用于识别用户消息的意图，决定是否需要注入日程信息。

意图类型：
- SCHEDULE_QUERY: 询问日程（如"你在干嘛"、"今天有什么安排"）
- SCHEDULE_MODIFY: 修改日程（如"别那么忙"、"多休息"）
- TECH_QUESTION: 技术问答（如"Python怎么安装"）
- COMMAND: 命令执行（如"/schedule"）
- CASUAL_CHAT: 闲聊（如"你好"、"晚安"）
- OTHER: 其他
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class IntentType(Enum):
    """意图类型"""

    SCHEDULE_QUERY = "schedule_query"  # 询问日程
    SCHEDULE_MODIFY = "schedule_modify"  # 修改日程
    TECH_QUESTION = "tech_question"  # 技术问答
    COMMAND = "command"  # 命令执行
    CASUAL_CHAT = "casual_chat"  # 闲聊
    OTHER = "other"  # 其他


@dataclass
class IntentResult:
    """意图识别结果"""

    intent: IntentType
    confidence: float  # 0.0 - 1.0
    slots: dict[str, str]  # 槽位信息（如时间、活动等）
    raw_message: str


class IntentClassifier:
    """
    意图分类器

    基于规则和关键词匹配识别用户意图。

    使用示例：
        classifier = IntentClassifier()
        result = classifier.classify("你在干嘛？")

        if result.intent == IntentType.SCHEDULE_QUERY:
            print("用户在询问日程")
    """

    # 意图关键词映射
    INTENT_KEYWORDS = {
        IntentType.SCHEDULE_QUERY: [
            "在干嘛",
            "在做什么",
            "在干啥",
            "干嘛呢",
            "今天安排",
            "明天安排",
            "有什么计划",
            "有什么安排",
            "日程",
            "时间表",
            "忙不忙",
            "有空吗",
            "几点",
            "什么时候",
        ],
        IntentType.SCHEDULE_MODIFY: [
            "别太累",
            "多休息",
            "少工作",
            "轻松点",
            "别那么忙",
            "放松",
            "早点睡",
            "晚点起",
            "安排个",
            "加个",
            "去掉",
            "取消",
        ],
        IntentType.TECH_QUESTION: [
            "怎么",
            "如何",
            "为什么",
            "什么是",
            "安装",
            "配置",
            "设置",
            "错误",
            "报错",
            "代码",
            "编程",
            "Python",
            "Java",
            "JS",
            "教程",
            "文档",
            "API",
        ],
        IntentType.COMMAND: [
            "/",
            "！",
            "！",
        ],
        IntentType.CASUAL_CHAT: [
            "你好",
            "早安",
            "晚安",
            "再见",
            "拜拜",
            "谢谢",
            "感谢",
            "对不起",
            "抱歉",
            "哈哈",
            "呵呵",
            "嘿嘿",
            "笑死",
        ],
    }

    # 时间模式
    TIME_PATTERNS = [
        r"(\d{1,2})[点时:：](\d{0,2})?",
        r"(早上|上午|中午|下午|晚上|傍晚|凌晨)",
        r"(今天|明天|后天|昨天|大后天)",
    ]

    def __init__(self):
        """初始化意图分类器"""
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        """预编译正则表达式"""
        self._time_regex = [re.compile(p) for p in self.TIME_PATTERNS]

    def classify(self, message: str) -> IntentResult:
        """
        分类用户消息的意图

        Args:
            message: 用户消息

        Returns:
            IntentResult: 意图识别结果
        """
        message = message.strip()

        # 检查命令
        if message.startswith("/") or message.startswith("！"):
            return IntentResult(intent=IntentType.COMMAND, confidence=1.0, slots={}, raw_message=message)

        # 计算各意图的匹配分数
        scores: dict[IntentType, float] = {}

        for intent, keywords in self.INTENT_KEYWORDS.items():
            score = 0.0
            for keyword in keywords:
                if keyword in message:
                    score += len(keyword) / len(message)
            scores[intent] = min(score, 1.0)

        # 找到最高分意图
        best_intent = IntentType.OTHER
        best_score = 0.0

        for intent, score in scores.items():
            if score > best_score:
                best_intent = intent
                best_score = score

        # 提取槽位
        slots = self._extract_slots(message)

        return IntentResult(intent=best_intent, confidence=best_score, slots=slots, raw_message=message)

    def _extract_slots(self, message: str) -> dict[str, str]:
        """
        提取槽位信息

        Args:
            message: 用户消息

        Returns:
            dict: 槽位信息
        """
        slots: dict[str, str] = {}

        # 提取时间
        for regex in self._time_regex:
            match = regex.search(message)
            if match:
                slots["time"] = match.group(0)
                break

        return slots

    def should_inject_schedule(self, message: str) -> tuple[bool, str]:
        """
        判断是否应该注入日程信息

        Args:
            message: 用户消息

        Returns:
            tuple[bool, str]: (是否注入, 原因)
        """
        result = self.classify(message)

        # 询问日程 → 注入
        if result.intent == IntentType.SCHEDULE_QUERY:
            return True, "用户询问日程"

        # 修改日程 → 注入
        if result.intent == IntentType.SCHEDULE_MODIFY:
            return True, "用户想修改日程"

        # 技术问答 → 不注入
        if result.intent == IntentType.TECH_QUESTION:
            return False, "技术问答，不需要日程信息"

        # 命令 → 不注入
        if result.intent == IntentType.COMMAND:
            return False, "命令消息，不需要日程信息"

        # 闲聊 → 可选注入（低优先级）
        if result.intent == IntentType.CASUAL_CHAT:
            return True, "闲聊，可以注入日程增加自然感"

        # 其他 → 可选注入
        return True, "默认注入"


# 模块级单例实例
_classifier_instance: Optional[IntentClassifier] = None


def get_intent_classifier() -> IntentClassifier:
    """
    获取意图分类器单例实例

    Returns:
        IntentClassifier: 分类器实例
    """
    global _classifier_instance
    if _classifier_instance is None:
        _classifier_instance = IntentClassifier()
    return _classifier_instance


def classify_intent(message: str) -> IntentResult:
    """
    快捷函数：分类意图

    Args:
        message: 用户消息

    Returns:
        IntentResult: 意图识别结果
    """
    return get_intent_classifier().classify(message)
