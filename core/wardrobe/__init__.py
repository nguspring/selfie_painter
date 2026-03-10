"""Wardrobe domain (selfie_painter_v2).

简洁版衣柜系统：
- 每日随机穿搭（daily_outfits 字符串列表）
- 自定义场景匹配（custom_scenes 一句话规则）
- 临时穿搭覆盖（/dr wardrobe wear 命令）
"""

from .selector import (
    build_simple_wardrobe_config,
    build_wardrobe_info_for_prompt,
    load_temp_override,
    save_temp_override,
    select_outfit_from_schedule,
)

__all__ = [
    "build_simple_wardrobe_config",
    "build_wardrobe_info_for_prompt",
    "load_temp_override",
    "save_temp_override",
    "select_outfit_from_schedule",
]
