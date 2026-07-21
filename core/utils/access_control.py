"""聊天流访问控制工具。"""

from __future__ import annotations

from typing import Callable


_MODE_BLACKLIST = "blacklist"
_MODE_WHITELIST = "whitelist"
_PRIVATE_ALIASES = {"private", "user"}


def normalize_access_mode(mode: object) -> str:
    """将访问模式标准化为 blacklist / whitelist。"""
    if isinstance(mode, str) and mode.strip().lower() == _MODE_WHITELIST:
        return _MODE_WHITELIST
    return _MODE_BLACKLIST


def normalize_context_id(context_id: object) -> str:
    """标准化聊天流 ID，兼容 private 的常见别名写法。"""
    if not isinstance(context_id, str):
        return ""

    normalized: str = context_id.strip().lower()
    if not normalized:
        return ""

    parts: list[str] = [part.strip() for part in normalized.split(":")]
    if len(parts) == 3:
        if parts[2] in _PRIVATE_ALIASES:
            parts[2] = "private"
        return ":".join(parts)
    return normalized


def normalize_access_list(access_list: object) -> list[str]:
    """标准化访问列表。"""
    if not isinstance(access_list, list):
        return []

    normalized_list: list[str] = []
    for item in access_list:
        normalized_item: str = normalize_context_id(item)
        if normalized_item:
            normalized_list.append(normalized_item)
    return normalized_list


def build_target_context_id(target_id: object, scope: str) -> str:
    """为自动自拍目标构建聊天流 ID。"""
    normalized_target_id: str = str(target_id).strip()
    if not normalized_target_id:
        return ""
    return normalize_context_id(f"qq:{normalized_target_id}:{scope}")


def extract_context_id_from_chat_stream(chat_stream: object) -> str:
    """从 ChatStream 对象提取规范化的上下文 ID。

    Args:
        chat_stream: ChatStream 对象，必须包含 platform、group_info 和 user_info 属性

    Returns:
        规范化的上下文 ID，格式为 "platform:id:scope"
        如果无法提取则返回空字符串

    Examples:
        群聊：qq:114514:group
        私聊：qq:1919810:private
    """
    if not chat_stream:
        return ""

    try:
        # 提取平台信息
        platform: str = getattr(chat_stream, "platform", "")
        if not platform:
            return ""

        # 提取群组信息
        group_info = getattr(chat_stream, "group_info", None)
        if group_info:
            group_id = getattr(group_info, "group_id", None)
            if group_id:
                return normalize_context_id(f"{platform}:{group_id}:group")

        # 提取用户信息（私聊）
        user_info = getattr(chat_stream, "user_info", None)
        if user_info:
            user_id = getattr(user_info, "user_id", None)
            if user_id:
                return normalize_context_id(f"{platform}:{user_id}:private")

        return ""
    except Exception:
        return ""


def is_context_allowed(mode: object, access_list: object, stream_id: str) -> bool:
    """根据黑白名单配置判断聊天流是否允许访问。"""
    normalized_mode: str = normalize_access_mode(mode)
    normalized_stream_id: str = normalize_context_id(stream_id)
    normalized_access_list: list[str] = normalize_access_list(access_list)

    if not normalized_stream_id:
        return normalized_mode == _MODE_BLACKLIST

    matched: bool = normalized_stream_id in normalized_access_list
    if normalized_mode == _MODE_WHITELIST:
        return matched
    return not matched


def is_chat_allowed_for_model(config_getter: Callable[[str, object], object], stream_id: str, model_id: str) -> bool:
    """同时检查全局与模型级聊天流访问规则。"""
    global_allowed: bool = is_context_allowed(
        config_getter("access_control.mode", _MODE_BLACKLIST),
        config_getter("access_control.list", []),
        stream_id,
    )
    if not global_allowed:
        return False

    return is_context_allowed(
        config_getter(f"models.{model_id}.access_mode", _MODE_BLACKLIST),
        config_getter(f"models.{model_id}.access_list", []),
        stream_id,
    )


def describe_access_rule(mode: object, access_list: object) -> str:
    """返回访问规则的简短摘要。"""
    normalized_mode: str = normalize_access_mode(mode)
    normalized_access_list: list[str] = normalize_access_list(access_list)

    if not normalized_access_list:
        if normalized_mode == _MODE_WHITELIST:
            return "白名单（空列表）"
        return "黑名单（空列表，默认全部允许）"

    mode_text: str = "白名单" if normalized_mode == _MODE_WHITELIST else "黑名单"
    return f"{mode_text}: {', '.join(normalized_access_list)}"
