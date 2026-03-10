"""时间工具模块

提供统一的时间解析和范围检查，消除 auto_selfie_task 和 schedule_provider 中的重复。
"""
import datetime


def to_minutes(time_str: str) -> int:
    """将 HH:MM 格式转换为自午夜起的分钟数"""
    try:
        parts = time_str.strip().split(":")
        return int(parts[0]) * 60 + int(parts[1])
    except (ValueError, IndexError):
        return 0


def is_in_time_range(
    start_str: str,
    end_str: str,
    now: datetime.datetime = None,
) -> bool:
    """
    检查当前时间是否在 [start, end] 范围内。
    支持跨午夜范围（如 23:00-07:00）。
    """
    if now is None:
        now = datetime.datetime.now()

    current_min = now.hour * 60 + now.minute
    start_min = to_minutes(start_str)
    end_min = to_minutes(end_str)

    if end_min < start_min:
        # 跨午夜
        return current_min >= start_min or current_min <= end_min
    return start_min <= current_min <= end_min
