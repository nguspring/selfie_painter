"""自动撤回工具

- 记录发送时间戳，精确筛选消息
- 轮询多次获取消息 ID（应对平台回调延迟）
- 只匹配图片消息，避免误撤回文字
- 区分真实 ID 和占位 ID，占位 ID 会二次解析
"""

import asyncio
import time as time_module
from typing import Callable, Awaitable, Any, Optional

from src.common.logger import get_logger

logger = get_logger("mais_art.recall")

# ==================== 消息匹配工具 ====================

def _is_image_message(msg) -> bool:
    """判断消息是否为图片消息"""
    # 方法1：检查 message_segment
    seg = getattr(msg, "message_segment", None)
    if seg is not None:
        seg_type = getattr(seg, "type", None)
        if seg_type in ("image", "imageurl", "emoji"):
            return True
        # 递归检查 seglist
        if seg_type == "seglist":
            data = getattr(seg, "data", None)
            if data and isinstance(data, (list, tuple)):
                for child in data:
                    child_type = getattr(child, "type", None)
                    if child_type in ("image", "imageurl", "emoji"):
                        return True

    # 方法2：检查 is_picid 标记
    if getattr(msg, "is_picid", False):
        return True

    # 方法3：检查文本特征
    text = ""
    if hasattr(msg, "processed_plain_text"):
        text = msg.processed_plain_text or ""
    elif hasattr(msg, "raw_message"):
        text = msg.raw_message or ""

    text_lower = text.strip().lower()
    image_prefixes = ("[图片", "[image", "[imageurl", "[picid", "picid:")
    for prefix in image_prefixes:
        if text_lower.startswith(prefix):
            return True

    return False


def _extract_user_id(msg) -> Optional[str]:
    """从消息中提取发送者用户 ID"""
    # message_info.user_info.user_id
    msg_info = getattr(msg, "message_info", None)
    if msg_info:
        user_info = getattr(msg_info, "user_info", None)
        if user_info:
            uid = getattr(user_info, "user_id", None)
            if uid:
                return str(uid)

    # user_info.user_id（直接属性）
    user_info = getattr(msg, "user_info", None)
    if user_info:
        uid = getattr(user_info, "user_id", None)
        if uid:
            return str(uid)

    # 直接 user_id
    uid = getattr(msg, "user_id", None)
    if uid:
        return str(uid)

    return None


def _get_message_time(msg) -> float:
    """获取消息的时间戳"""
    t = getattr(msg, "time", None)
    if t is not None:
        return float(t)
    t = getattr(msg, "timestamp", None)
    if t is not None:
        return float(t)
    return 0.0


# ==================== 核心逻辑 ====================

async def _find_bot_image_message_id(
    chat_id: str,
    send_timestamp: float,
    log_prefix: str,
    poll_attempts: int = 5,
    poll_interval: float = 0.5,
) -> Optional[str]:
    """轮询查找 Bot 发送的图片消息 ID

    Args:
        chat_id: 聊天流 ID
        send_timestamp: 图片发送时的时间戳
        log_prefix: 日志前缀
        poll_attempts: 轮询次数
        poll_interval: 每次轮询间隔（秒）

    Returns:
        消息 ID 字符串，找不到返回 None
    """
    from src.plugin_system.apis import message_api
    from src.config.config import global_config

    bot_id = str(global_config.bot.qq_account)
    placeholder_id = None

    for attempt in range(poll_attempts):
        try:
            messages = message_api.get_messages_by_time_in_chat(
                chat_id=chat_id,
                start_time=send_timestamp - 2,
                end_time=time_module.time() + 1,
                limit=10,
                limit_mode="latest",
            )
        except Exception as e:
            logger.debug(f"{log_prefix} 查询消息失败 (第{attempt + 1}次): {e}")
            await asyncio.sleep(poll_interval)
            continue

        # 倒序遍历（最新的在前）
        for msg in reversed(messages):
            # 只匹配图片消息
            if not _is_image_message(msg):
                continue

            # 只匹配 Bot 自己发的
            sender_id = _extract_user_id(msg)
            if sender_id and sender_id != bot_id:
                continue
            if not sender_id:
                # 无法确认发送者，宁可不撤回也不误撤回
                continue

            # 检查时间：必须在发送时间之后
            msg_time = _get_message_time(msg)
            if msg_time > 0 and msg_time < send_timestamp - 1:
                continue

            mid = str(getattr(msg, "message_id", ""))
            if not mid:
                continue

            # 优先选真实 ID（纯数字），占位 ID 作为后备
            if mid.isdigit():
                logger.info(
                    f"{log_prefix} 找到目标消息 ID: {mid} (第{attempt + 1}次轮询)"
                )
                return mid
            elif not mid.startswith("send_api_"):
                # 非标准格式但也非占位符，可以尝试
                logger.info(
                    f"{log_prefix} 找到非标准消息 ID: {mid} (第{attempt + 1}次轮询)"
                )
                return mid
            else:
                placeholder_id = mid

        if attempt < poll_attempts - 1:
            await asyncio.sleep(poll_interval)

    if placeholder_id:
        logger.warning(f"{log_prefix} 仅找到占位消息 ID: {placeholder_id}")
    else:
        logger.warning(f"{log_prefix} 未找到 Bot 的图片消息 ID")

    return placeholder_id


async def schedule_auto_recall(
    chat_id: str,
    delay_seconds: int,
    log_prefix: str,
    send_command_fn: Callable[..., Awaitable[Any]],
    send_timestamp: float = 0.0,
):
    """安排消息自动撤回后台任务

    Args:
        chat_id: 聊天流 ID
        delay_seconds: 撤回延时（秒）
        log_prefix: 日志前缀
        send_command_fn: 发送平台命令的异步函数
        send_timestamp: 图片发送时的时间戳（time.time()），
            0 表示使用当前时间
    """
    if send_timestamp <= 0:
        send_timestamp = time_module.time()

    async def _recall_task():
        try:
            # 等待消息入库
            await asyncio.sleep(1.0)

            # 轮询获取消息 ID
            target_message_id = await _find_bot_image_message_id(
                chat_id, send_timestamp, log_prefix
            )

            if not target_message_id:
                logger.warning(f"{log_prefix} 无法获取消息 ID，放弃撤回")
                return

            logger.info(
                f"{log_prefix} 安排自动撤回，延时: {delay_seconds}秒，消息ID: {target_message_id}"
            )

            # 等待撤回延时
            await asyncio.sleep(delay_seconds)

            # 如果之前拿到的是占位 ID，再尝试解析一次真实 ID
            if target_message_id.startswith("send_api_"):
                resolved = await _find_bot_image_message_id(
                    chat_id, send_timestamp, log_prefix,
                    poll_attempts=3, poll_interval=1.0,
                )
                if resolved and not resolved.startswith("send_api_"):
                    logger.info(f"{log_prefix} 占位 ID 解析为真实 ID: {resolved}")
                    target_message_id = resolved

            # 尝试撤回
            success = await _try_recall_message(
                target_message_id, send_command_fn, log_prefix
            )
            if not success:
                logger.warning(
                    f"{log_prefix} 自动撤回失败，消息ID: {target_message_id}"
                )

        except asyncio.CancelledError:
            logger.debug(f"{log_prefix} 自动撤回任务被取消")
        except Exception as e:
            logger.error(f"{log_prefix} 自动撤回异常: {e}")

    asyncio.create_task(_recall_task())


async def _try_recall_message(
    message_id: str,
    send_command_fn: Callable[..., Awaitable[Any]],
    log_prefix: str,
) -> bool:
    """尝试撤回消息"""
    commands = ["DELETE_MSG", "delete_msg", "RECALL_MSG", "recall_msg"]

    for cmd in commands:
        try:
            result = await send_command_fn(
                command_name=cmd,
                args={"message_id": str(message_id)},
                storage_message=False,
            )
            if isinstance(result, bool) and result:
                logger.info(
                    f"{log_prefix} 撤回成功，命令: {cmd}，消息ID: {message_id}"
                )
                return True
            elif isinstance(result, dict):
                status = str(result.get("status", "")).lower()
                if (
                    status in ("ok", "success")
                    or result.get("retcode") == 0
                    or result.get("code") == 0
                ):
                    logger.info(
                        f"{log_prefix} 撤回成功，命令: {cmd}，消息ID: {message_id}"
                    )
                    return True
        except Exception as e:
            logger.debug(f"{log_prefix} 撤回命令 {cmd} 失败: {e}")
            continue

    return False
