"""
人设驱动上下文构建器

用于构建日程生成所需的人设上下文，让 LLM 知道"麦麦是谁"。

功能：
1. 从主程序读取人设配置（nickname, personality, reply_style）
2. 从插件配置读取补充信息（identity, interest, lifestyle）
3. 合并生成完整的人设上下文字符串
"""

from typing import Optional

from src.plugin_system.apis import config_api


class PersonaContextBuilder:
    """
    人设上下文构建器

    负责从多个来源收集人设信息，并合并成可用于日程生成的上下文字符串。

    数据来源：
    - 主程序配置：bot.nickname, personality.personality, personality.reply_style
    - 插件配置：schedule_identity, schedule_interest, schedule_lifestyle

    使用示例：
        builder = PersonaContextBuilder()
        context = builder.build(
            schedule_identity="是一个二次元爱好者",
            schedule_interest="画画、打游戏",
            schedule_lifestyle="习惯晚睡"
        )
    """

    def __init__(self):
        """初始化人设上下文构建器"""
        pass

    def get_bot_nickname(self) -> str:
        """
        获取 Bot 名称

        从主程序配置读取 bot.nickname

        Returns:
            str: Bot 名称，默认为 "麦麦"
        """
        return config_api.get_global_config("bot.nickname", "麦麦")

    def get_personality(self) -> str:
        """
        获取人设描述

        从主程序配置读取 personality.personality

        Returns:
            str: 人设描述，默认为 "是一个女大学生"
        """
        return config_api.get_global_config("personality.personality", "是一个女大学生")

    def get_reply_style(self) -> str:
        """
        获取回复风格

        从主程序配置读取 personality.reply_style

        Returns:
            str: 回复风格描述，默认为空字符串
        """
        return config_api.get_global_config("personality.reply_style", "")

    def build(self, schedule_identity: str = "", schedule_interest: str = "", schedule_lifestyle: str = "") -> str:
        """
        构建完整的人设上下文字符串

        将主程序人设配置和插件补充配置合并，生成用于日程生成的人设上下文。

        Args:
            schedule_identity: 身份补充（如"是一个二次元爱好者"）
            schedule_interest: 兴趣爱好（如"画画、打游戏"）
            schedule_lifestyle: 生活规律（如"习惯晚睡"）

        Returns:
            str: 完整的人设上下文字符串

        示例输出：
            你是麦麦，是一个女大学生

            【身份】
            是一个二次元爱好者，喜欢画画

            【兴趣】
            画画、打游戏、听音乐

            【生活规律】
            习惯晚睡，经常熬夜

            【回复风格】
            说话活泼可爱，喜欢用颜文字
        """
        # 获取主程序人设配置
        nickname = self.get_bot_nickname()
        personality = self.get_personality()
        reply_style = self.get_reply_style()

        # 构建基础人设
        parts = [f"你是{nickname}，{personality}"]

        # 添加身份补充（合并主程序人设和插件补充）
        if schedule_identity:
            parts.append(f"\n【身份】\n{schedule_identity}")

        # 添加兴趣爱好
        if schedule_interest:
            parts.append(f"\n【兴趣】\n{schedule_interest}")

        # 添加生活规律
        if schedule_lifestyle:
            parts.append(f"\n【生活规律】\n{schedule_lifestyle}")

        # 添加回复风格
        if reply_style:
            parts.append(f"\n【回复风格】\n{reply_style}")

        return "\n".join(parts)

    def build_for_schedule(
        self, schedule_identity: str = "", schedule_interest: str = "", schedule_lifestyle: str = ""
    ) -> str:
        """
        构建用于日程生成的人设上下文

        这是 build() 方法的别名，提供更明确的语义。

        Args:
            schedule_identity: 身份补充
            schedule_interest: 兴趣爱好
            schedule_lifestyle: 生活规律

        Returns:
            str: 用于日程生成的人设上下文
        """
        return self.build(schedule_identity, schedule_interest, schedule_lifestyle)


# 模块级单例实例，方便直接调用
_builder_instance: Optional[PersonaContextBuilder] = None


def get_persona_builder() -> PersonaContextBuilder:
    """
    获取人设上下文构建器单例实例

    Returns:
        PersonaContextBuilder: 构建器实例
    """
    global _builder_instance
    if _builder_instance is None:
        _builder_instance = PersonaContextBuilder()
    return _builder_instance


def build_persona_context(
    schedule_identity: str = "", schedule_interest: str = "", schedule_lifestyle: str = ""
) -> str:
    """
    快捷函数：构建人设上下文

    Args:
        schedule_identity: 身份补充
        schedule_interest: 兴趣爱好
        schedule_lifestyle: 生活规律

    Returns:
        str: 完整的人设上下文字符串
    """
    return get_persona_builder().build(
        schedule_identity=schedule_identity, schedule_interest=schedule_interest, schedule_lifestyle=schedule_lifestyle
    )
