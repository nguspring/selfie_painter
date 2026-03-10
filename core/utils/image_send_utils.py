"""图片数据处理工具

统一 base64 vs URL 图片数据的解析逻辑，消除 pic_action / pic_command 中的重复。
"""

import asyncio
import base64
import binascii
import html
import re
from typing import Tuple, Callable

from src.common.logger import get_logger

from .shared_constants import BASE64_IMAGE_PREFIXES

logger = get_logger("mais_art.image_send")

_MARKDOWN_IMAGE_PATTERN = re.compile(
    r"!\[[^\]]*\]\(\s*<?(https?://[^\s>]+?)>?\s*\)",
    flags=re.IGNORECASE,
)
_URL_PATTERN = re.compile(r"https?://[^\s<>\"']+", flags=re.IGNORECASE)
_DATA_URI_PATTERN = re.compile(
    r"^data:image/[A-Za-z0-9.+-]+;base64,(?P<data>[A-Za-z0-9+/=\s]+)$",
    flags=re.IGNORECASE,
)
_BASE64_BODY_PATTERN = re.compile(r"^[A-Za-z0-9+/=]+$")

_IMAGE_MAGIC_HEADERS = (
    b"\xff\xd8\xff",  # JPEG
    b"\x89PNG\r\n\x1a\n",  # PNG
    b"GIF87a",  # GIF87a
    b"GIF89a",  # GIF89a
    b"BM",  # BMP
)


def _normalize_base64_payload(payload: str) -> str:
    """去掉 base64 中可能出现的空白符。"""
    return re.sub(r"\s+", "", payload)


def _looks_like_image_base64(payload: str) -> bool:
    """检测字符串是否像图片 base64。"""
    normalized = _normalize_base64_payload(payload)
    if len(normalized) < 64:
        return False
    if not _BASE64_BODY_PATTERN.fullmatch(normalized):
        return False
    if normalized.startswith(BASE64_IMAGE_PREFIXES):
        return True

    try:
        decoded = base64.b64decode(normalized, validate=True)
    except (binascii.Error, ValueError):
        return False

    if decoded.startswith(_IMAGE_MAGIC_HEADERS):
        return True

    # WEBP: RIFF....WEBP
    return decoded.startswith(b"RIFF") and len(decoded) >= 12 and decoded[8:12] == b"WEBP"


def _clean_url_candidate(url: str) -> str:
    """清理 URL 候选，去掉常见包裹符与多余尾字符。"""
    cleaned = html.unescape(url.strip().strip("<>").strip("\"'"))

    while cleaned and cleaned[-1] in ".,;!?":
        cleaned = cleaned[:-1]

    # URL 出现在 markdown/文本中时，末尾可能多带一个 ")" 或 "]"
    while cleaned.endswith(")") and cleaned.count("(") < cleaned.count(")"):
        cleaned = cleaned[:-1]
    while cleaned.endswith("]"):
        cleaned = cleaned[:-1]

    return cleaned


def _extract_first_url(raw: str) -> str:
    """从 markdown/plain text 中提取首个 URL。"""
    md_match = _MARKDOWN_IMAGE_PATTERN.search(raw)
    if md_match:
        return _clean_url_candidate(md_match.group(1))

    url_match = _URL_PATTERN.search(raw)
    if url_match:
        return _clean_url_candidate(url_match.group(0))

    return ""


async def resolve_image_data(
    image_data: str,
    download_fn: Callable[[str], Tuple[bool, str]],
    log_prefix: str = "",
) -> Tuple[bool, str]:
    """将图片数据统一为 base64 格式

    如果 image_data 已是 base64 编码则原样返回；
    如果是 URL 则通过 download_fn 下载并转为 base64。

    Args:
        image_data: base64 字符串或图片 URL
        download_fn: 同步下载函数，签名 (url) -> (success, base64_or_error)
        log_prefix: 日志前缀

    Returns:
        (success, base64_data_or_error_message)
    """
    if image_data.startswith(BASE64_IMAGE_PREFIXES):
        return True, image_data

    raw_candidate = image_data.strip()

    data_uri_match = _DATA_URI_PATTERN.match(raw_candidate)
    if data_uri_match:
        data_payload = _normalize_base64_payload(data_uri_match.group("data"))
        if _looks_like_image_base64(data_payload):
            return True, data_payload
        logger.warning(f"{log_prefix} Data URI 看起来不是有效图片，内容预览: {raw_candidate[:120]}")
        return False, "返回内容中的Data URI无效"

    if _looks_like_image_base64(raw_candidate):
        logger.info(f"{log_prefix} 检测到纯Base64图片数据")
        return True, _normalize_base64_payload(raw_candidate)

    if raw_candidate.lower().startswith(("http://", "https://")):
        image_url = _clean_url_candidate(raw_candidate)
    else:
        image_url = _extract_first_url(raw_candidate)
        if not image_url:
            logger.warning(f"{log_prefix} 无法从返回内容中提取图片URL，内容预览: {raw_candidate[:160]}")
            return False, "返回内容不是可识别的图片URL/Base64"
        logger.info(f"{log_prefix} 检测到非纯URL图片数据，已提取URL: {image_url[:80]}...")

    # URL: 下载并转为 base64
    try:
        encode_success, encode_result = await asyncio.to_thread(download_fn, image_url)
        if encode_success:
            return True, encode_result
        else:
            logger.warning(f"{log_prefix} 图片下载失败: {encode_result}")
            return False, f"图片下载失败: {encode_result}"
    except Exception as e:
        logger.error(f"{log_prefix} 图片下载编码失败: {e!r}")
        return False, "图片下载失败"
