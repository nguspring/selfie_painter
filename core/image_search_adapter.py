"""图片搜索适配器 — 封装搜索引擎，为角色参考图功能提供统一接口"""

from __future__ import annotations

import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


class ImageSearchAdapter:
    """图片搜索适配器：使用内置 Bing 图片搜索引擎"""

    _engine_cache = None

    @classmethod
    def _get_engine(cls):
        """懒加载搜索引擎实例"""
        if cls._engine_cache is None:
            try:
                from .search_engines.bing import BingImageEngine

                cls._engine_cache = BingImageEngine({"timeout": 20, "region": "zh-CN"})
                logger.info("[ImageSearchAdapter] Bing图片搜索引擎初始化成功")
            except Exception as e:
                logger.error(f"[ImageSearchAdapter] 初始化搜索引擎失败: {e}")
                return None
        return cls._engine_cache

    @classmethod
    async def search(cls, keyword: str, max_results: int = 1) -> Optional[str]:
        """搜索关键词，返回第一张图片的 URL"""
        engine = cls._get_engine()
        if not engine:
            logger.warning("[ImageSearchAdapter] 搜索引擎未初始化")
            return None

        query = f"{keyword} official art character design"
        logger.info(f"[ImageSearchAdapter] 正在搜索图片: {query}")

        try:
            results = await engine.search_images(query, max_results)
            if results:
                first_result = results[0]
                image_url = first_result.image if hasattr(first_result, "image") else None
                if image_url:
                    logger.info(f"[ImageSearchAdapter] 找到图片: {image_url}")
                    return image_url
        except Exception as e:
            logger.error(f"[ImageSearchAdapter] 搜索失败: {e}")

        logger.warning(f"[ImageSearchAdapter] 未找到图片: {keyword}")
        return None

    @classmethod
    async def search_multiple(cls, keyword: str, max_results: int = 3) -> List[str]:
        """搜索关键词，返回多张图片 URL"""
        engine = cls._get_engine()
        if not engine:
            return []

        query = f"{keyword} official art character design"
        logger.info(f"[ImageSearchAdapter] 正在搜索多张图片: {query}")

        try:
            results = await engine.search_images(query, max_results)
            urls: List[str] = []
            for result in results:
                if hasattr(result, "image") and result.image:
                    urls.append(result.image)
            logger.info(f"[ImageSearchAdapter] 找到 {len(urls)} 张图片")
            return urls
        except Exception as e:
            logger.error(f"[ImageSearchAdapter] 搜索失败: {e}")
            return []
