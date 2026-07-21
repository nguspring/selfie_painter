from typing import Optional, Dict, Any
import asyncio
import hashlib

from src.common.logger import get_logger

logger = get_logger("mais_art.cache")

class CacheManager:
    """缓存管理器

    每个聊天流拥有独立的缓存空间，避免跨会话污染。
    使用 asyncio.Lock 保护并发访问，避免阻塞事件循环。
    """

    # 类级别的缓存存储：stream_id -> {'txt2img': {}, 'img2img': {}}
    _global_caches: Dict[str, Dict[str, Dict[str, str]]] = {}
    _cache_lock = asyncio.Lock()  # 异步锁，避免阻塞事件循环

    def __init__(self, action_instance):
        self.action = action_instance
        self.log_prefix = action_instance.log_prefix
        # 获取聊天流 ID 用于缓存隔离
        self.stream_id = getattr(action_instance, 'chat_id', None) or 'unknown'

        # 确保当前流的缓存空间已初始化（非异步操作，无需加锁）
        if self.stream_id not in self._global_caches:
            self._global_caches[self.stream_id] = {
                'txt2img': {},
                'img2img': {}
            }

    def _get_max_size(self) -> int:
        """获取最大缓存数量配置"""
        return self.action.get_config("cache.max_size", 10)

    async def get_cached_result(
        self,
        description: str,
        model: str,
        size: str,
        strength: Optional[float] = None,
        is_img2img: bool = False,
        input_image_data: Optional[bytes] = None,
    ) -> Optional[str]:
        """获取缓存的结果

        Args:
            description: 图片描述
            model: 模型名称
            size: 图片尺寸
            strength: 图生图强度（可选）
            is_img2img: 是否为图生图
            input_image_data: 输入图片的字节数据（图生图时必须提供）

        Returns:
            缓存的结果，如果没有则返回 None
        """
        if not self.action.get_config("cache.enabled", True):
            return None

        try:
            async with self._cache_lock:
                cache_type = 'img2img' if is_img2img else 'txt2img'
                cache_dict = self._global_caches[self.stream_id][cache_type]

                if is_img2img:
                    cache_key = self._get_img2img_cache_key(
                        self.stream_id, description, model, size, strength, input_image_data
                    )
                else:
                    cache_key = self._get_cache_key(self.stream_id, description, model, size)

                if cache_key in cache_dict:
                    logger.debug(f"{self.log_prefix} 找到缓存结果: {cache_key}")
                    return cache_dict[cache_key]

                return None
        except Exception as e:
            logger.warning(f"{self.log_prefix} 获取缓存失败: {e}")
            return None

    async def cache_result(
        self,
        description: str,
        model: str,
        size: str,
        strength: Optional[float] = None,
        is_img2img: bool = False,
        result: Optional[str] = None,
        input_image_data: Optional[bytes] = None,
    ):
        """缓存结果

        Args:
            description: 图片描述
            model: 模型名称
            size: 图片尺寸
            strength: 图生图强度（可选）
            is_img2img: 是否为图生图
            result: 要缓存的结果
            input_image_data: 输入图片的字节数据（图生图时必须提供）
        """
        if not self.action.get_config("cache.enabled", True) or not result:
            return

        try:
            async with self._cache_lock:
                cache_type = 'img2img' if is_img2img else 'txt2img'
                cache_dict = self._global_caches[self.stream_id][cache_type]

                if is_img2img:
                    cache_key = self._get_img2img_cache_key(
                        self.stream_id, description, model, size, strength, input_image_data
                    )
                else:
                    cache_key = self._get_cache_key(self.stream_id, description, model, size)

                max_size = self._get_max_size()

                # 添加到缓存
                cache_dict[cache_key] = result
                logger.debug(f"{self.log_prefix} 缓存结果: {cache_key}")

                # 清理过期缓存（仅清理当前流的缓存）
                if len(cache_dict) > max_size:
                    self._cleanup_cache_dict(cache_dict, max_size)

        except Exception as e:
            logger.warning(f"{self.log_prefix} 缓存结果失败: {e}")

    async def remove_cached_result(
        self,
        description: str,
        model: str,
        size: str,
        strength: Optional[float] = None,
        is_img2img: bool = False,
        input_image_data: Optional[bytes] = None,
    ):
        """移除缓存的结果

        Args:
            description: 图片描述
            model: 模型名称
            size: 图片尺寸
            strength: 图生图强度（可选）
            is_img2img: 是否为图生图
            input_image_data: 输入图片的字节数据（图生图时必须提供）
        """
        try:
            async with self._cache_lock:
                cache_type = 'img2img' if is_img2img else 'txt2img'
                cache_dict = self._global_caches[self.stream_id][cache_type]

                if is_img2img:
                    cache_key = self._get_img2img_cache_key(
                        self.stream_id, description, model, size, strength, input_image_data
                    )
                else:
                    cache_key = self._get_cache_key(self.stream_id, description, model, size)

                if cache_key in cache_dict:
                    del cache_dict[cache_key]
                    logger.debug(f"{self.log_prefix} 移除失效缓存: {cache_key}")

        except Exception as e:
            logger.warning(f"{self.log_prefix} 移除缓存失败: {e}")

    async def clear_cache(self, cache_type: str = "all"):
        """清空当前聊天流的缓存

        Args:
            cache_type: 缓存类型，可选值: "all", "txt2img", "img2img"
        """
        try:
            async with self._cache_lock:
                if cache_type == "all" or cache_type == "txt2img":
                    self._global_caches[self.stream_id]['txt2img'].clear()
                    logger.info(f"{self.log_prefix} 清空文生图缓存")

                if cache_type == "all" or cache_type == "img2img":
                    self._global_caches[self.stream_id]['img2img'].clear()
                    logger.info(f"{self.log_prefix} 清空图生图缓存")

        except Exception as e:
            logger.warning(f"{self.log_prefix} 清空缓存失败: {e}")

    async def get_cache_stats(self) -> Dict[str, Any]:
        """获取当前聊天流的缓存统计信息"""
        try:
            async with self._cache_lock:
                max_size = self._get_max_size()
                txt2img_count = len(self._global_caches[self.stream_id]['txt2img'])
                img2img_count = len(self._global_caches[self.stream_id]['img2img'])
                return {
                    "txt2img_cache_size": txt2img_count,
                    "txt2img_cache_max": max_size,
                    "img2img_cache_size": img2img_count,
                    "img2img_cache_max": max_size,
                    "cache_enabled": self.action.get_config("cache.enabled", True)
                }
        except Exception as e:
            logger.warning(f"{self.log_prefix} 获取缓存统计失败: {e}")
            return {}

    @classmethod
    def _get_cache_key(cls, stream_id: str, description: str, model: str, size: str) -> str:
        """生成文生图缓存键，包含 stream_id 用于隔离不同会话的缓存

        Args:
            stream_id: 聊天流 ID，用于缓存隔离
            description: 图片描述
            model: 模型名称
            size: 图片尺寸

        Returns:
            缓存键字符串
        """
        return f"txt2img_{stream_id}|{description[:100]}|{model}|{size}"

    @classmethod
    def _get_img2img_cache_key(
        cls,
        stream_id: str,
        description: str,
        model: str,
        size: str,
        strength: Optional[float] = None,
        input_image_data: Optional[bytes] = None,
    ) -> str:
        """生成图生图缓存键，包含 stream_id 和输入图片哈希用于精确匹配

        Args:
            stream_id: 聊天流 ID，用于缓存隔离
            description: 图片描述
            model: 模型名称
            size: 图片尺寸
            strength: 图生图强度
            input_image_data: 输入图片的字节数据，用于计算哈希值

        Returns:
            缓存键字符串
        """
        strength_str = str(strength) if strength is not None else "default"

        # 计算输入图片的 SHA-256 哈希值（取前 16 位）
        # 使用流式哈希避免大文件 OOM
        if input_image_data:
            hasher = hashlib.sha256()
            # 分块处理：每次处理 64KB
            chunk_size = 65536  # 64KB
            for i in range(0, len(input_image_data), chunk_size):
                chunk = input_image_data[i:i + chunk_size]
                hasher.update(chunk)
            image_hash = hasher.hexdigest()[:16]
        else:
            image_hash = "no_input"

        return f"img2img_{stream_id}|{description[:50]}|{model}|{size}|{strength_str}|{image_hash}"

    @classmethod
    def _cleanup_cache_dict(cls, cache_dict: Dict, max_size: int):
        """清理缓存字典"""
        if len(cache_dict) > max_size:
            # 移除一半的最旧条目
            keys_to_remove = list(cache_dict.keys())[: -max_size // 2]
            for key in keys_to_remove:
                del cache_dict[key]
