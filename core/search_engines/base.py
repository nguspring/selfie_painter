"""图片搜索引擎基类"""

from __future__ import annotations

import random
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

try:
    import aiohttp
except ImportError:
    aiohttp = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

HEADERS: Dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/92.0.4515.131 Safari/537.36"
    ),
    "Accept": "*/*",
    "Connection": "keep-alive",
    "Accept-Language": "en-GB,en;q=0.5",
}

USER_AGENTS: List[str] = [
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/92.0.4515.131 Safari/537.36"
    ),
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/92.0.4515.131 Safari/537.36"
    ),
]


@dataclass
class SearchResult:
    """搜索结果数据类"""

    title: str
    url: str
    snippet: str = ""
    image: str = ""
    thumbnail: str = ""


class BaseSearchEngine:
    """搜索引擎基类"""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config: Dict[str, Any] = config or {}
        self.timeout: int = self.config.get("timeout", 15)
        self.max_results: int = self.config.get("max_results", 5)
        self.headers: Dict[str, str] = HEADERS.copy()
        self.proxy: Optional[str] = self.config.get("proxy")

    async def _get_html(self, url: str, data: Optional[Dict[str, Any]] = None) -> str:
        """获取 HTML 内容"""
        if aiohttp is None:
            logger.error("aiohttp 未安装，无法执行HTTP请求")
            return ""

        headers = self.headers.copy()
        headers["Referer"] = url
        headers["User-Agent"] = random.choice(USER_AGENTS)

        try:
            async with aiohttp.ClientSession() as session:
                timeout = aiohttp.ClientTimeout(total=self.timeout)
                if data:
                    async with session.post(url, headers=headers, data=data, timeout=timeout, proxy=self.proxy) as resp:
                        resp.raise_for_status()
                        return await resp.text()
                else:
                    async with session.get(url, headers=headers, timeout=timeout, proxy=self.proxy) as resp:
                        resp.raise_for_status()
                        return await resp.text()
        except Exception as e:
            logger.error(f"获取HTML失败: {url} - {e}")
            return ""

    async def search_images(self, query: str, num_results: int = 5) -> List[SearchResult]:
        """搜索图片（子类需要实现）"""
        raise NotImplementedError("子类需要实现 search_images 方法")
