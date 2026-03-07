"""角色参考图管理 — 搜索、下载、VLM 特征提取与缓存"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

import aiohttp

from src.common.logger import get_logger
from src.config.config import model_config as maibot_model_config
from src.llm_models.utils_model import LLMRequest

from ..image_search_adapter import ImageSearchAdapter

logger = get_logger("mais_art.role_reference")


class _ConfigProxy:
    """为不直接提供 get_config 的调用方提供统一接口"""

    def __init__(self, getter: Callable[[str, Any], Any]) -> None:
        self._getter = getter

    def get_config(self, key: str, default: Any = None) -> Any:
        return self._getter(key, default)


class RoleReferenceStore:
    """管理角色参考图缓存、特征提取与状态查询。

    通过 Bing 搜索角色图片 → 下载保存 → VLM 提取特征描述，
    供生图时自动注入角色特征到提示词中。
    """

    def __init__(
        self,
        plugin_instance: Any = None,
        plugin_dir: Optional[str] = None,
        config_getter: Optional[Callable[[str, Any], Any]] = None,
    ) -> None:
        self.plugin = self._resolve_plugin_context(plugin_instance, config_getter)
        self.plugin_dir = self._resolve_plugin_dir(plugin_instance, plugin_dir)
        self.base_dir: str = os.path.join(self.plugin_dir, "data", "image_reference")
        self.index_path: str = os.path.join(self.base_dir, "index.json")
        os.makedirs(self.base_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # 初始化辅助
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_plugin_context(
        plugin_instance: Any,
        config_getter: Optional[Callable[[str, Any], Any]],
    ) -> Any:
        if plugin_instance and hasattr(plugin_instance, "get_config"):
            return plugin_instance
        if callable(config_getter):
            return _ConfigProxy(config_getter)
        return _ConfigProxy(lambda _key, default=None: default)

    @staticmethod
    def _resolve_plugin_dir(plugin_instance: Any, plugin_dir: Optional[str]) -> str:
        if plugin_dir:
            return plugin_dir
        if plugin_instance and hasattr(plugin_instance, "plugin_dir"):
            value = getattr(plugin_instance, "plugin_dir")
            if isinstance(value, str) and value:
                return value
        # 回退：假设当前文件在 core/utils/ 目录
        return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    # ------------------------------------------------------------------
    # 角色名解析
    # ------------------------------------------------------------------

    @staticmethod
    def extract_role_name(text: str) -> Optional[str]:
        """从用户输入中提取角色名"""
        if not text:
            return None
        content = text.strip()

        patterns = [
            r"角色\s*[=:：]\s*([^\s,，。]+)",
            r"(?:画|帮我画|生成|来一张|请画)\s*([^\s,，。]{1,24})",
        ]

        for pattern in patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if not match:
                continue
            role = match.group(1).strip()
            role = re.sub(r"^(一个|一位|一只|一张)", "", role).strip()
            if role:
                return role
        return None

    @staticmethod
    def normalize_role_name(role_name: str) -> str:
        return re.sub(r"\s+", "", role_name.strip())

    @staticmethod
    def role_hash(role_name: str) -> str:
        return hashlib.sha256(role_name.encode("utf-8")).hexdigest()[:16]

    # ------------------------------------------------------------------
    # 索引 & 元数据
    # ------------------------------------------------------------------

    def _load_index(self) -> Dict[str, Any]:
        if not os.path.exists(self.index_path):
            return {}
        try:
            with open(self.index_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except Exception as e:
            logger.warning(f"读取参考图索引失败: {e}")
        return {}

    def _save_index(self, index: Dict[str, Any]) -> None:
        with open(self.index_path, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)

    def _role_dir(self, role_hash: str) -> str:
        return os.path.join(self.base_dir, role_hash)

    def _images_dir(self, role_hash: str) -> str:
        return os.path.join(self._role_dir(role_hash), "images")

    def _metadata_path(self, role_hash: str) -> str:
        return os.path.join(self._role_dir(role_hash), "metadata.json")

    def _read_metadata(self, role_hash: str) -> Dict[str, Any]:
        path = self._metadata_path(role_hash)
        if not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        return {}

    def _write_metadata(self, role_hash: str, data: Dict[str, Any]) -> None:
        os.makedirs(self._role_dir(role_hash), exist_ok=True)
        with open(self._metadata_path(role_hash), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------
    # 核心功能
    # ------------------------------------------------------------------

    async def refresh_role(self, role_name: str) -> Tuple[bool, str]:
        """搜索并更新角色参考图"""
        role_name = self.normalize_role_name(role_name)
        if not role_name:
            return False, "角色名为空"

        top_k = int(self.plugin.get_config("search_reference.search_top_k", 6) or 6)
        max_images = int(self.plugin.get_config("search_reference.max_images_per_role", 3) or 3)

        urls = await ImageSearchAdapter.search_multiple(role_name, max_results=max(top_k, max_images))
        if not urls:
            return False, "没有搜到可用图片"

        rhash = self.role_hash(role_name)
        images_dir = self._images_dir(rhash)
        os.makedirs(images_dir, exist_ok=True)

        kept_urls: List[str] = []
        image_paths: List[str] = []

        for url in urls:
            if len(image_paths) >= max_images:
                break
            ok, image_bytes = await self._download_image(url)
            if not ok or not image_bytes:
                continue

            file_path = os.path.join(images_dir, f"{len(image_paths) + 1}.jpg")
            try:
                with open(file_path, "wb") as f:
                    f.write(image_bytes)
                image_paths.append(file_path)
                kept_urls.append(url)
            except Exception as e:
                logger.warning(f"保存参考图失败: {e}")

        if not image_paths:
            return False, "参考图下载失败"

        features = await self._extract_features(image_paths)

        metadata: Dict[str, Any] = {
            "role_name": role_name,
            "role_hash": rhash,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "images": [os.path.basename(p) for p in image_paths],
            "source_urls": kept_urls,
            "features": features,
        }
        self._write_metadata(rhash, metadata)

        index = self._load_index()
        index[role_name] = {"role_hash": rhash, "updated_at": metadata["updated_at"]}
        self._save_index(index)

        self._cleanup_role_dir(rhash, keep_count=max_images)
        self._enforce_cache_limit()

        return True, f"已更新角色参考图（{len(image_paths)}张）"

    def clear_role(self, role_name: str) -> Tuple[bool, str]:
        """清除指定角色的缓存"""
        role_name = self.normalize_role_name(role_name)
        if not role_name:
            return False, "角色名为空"

        index = self._load_index()
        role_info = index.get(role_name)
        if not isinstance(role_info, dict):
            return False, "该角色没有缓存"

        rhash = str(role_info.get("role_hash", ""))
        if rhash:
            shutil.rmtree(self._role_dir(rhash), ignore_errors=True)

        index.pop(role_name, None)
        self._save_index(index)
        return True, "已清除该角色缓存"

    def role_status(self, role_name: str) -> Tuple[bool, Dict[str, Any]]:
        """查询角色参考图状态"""
        role_name = self.normalize_role_name(role_name)
        if not role_name:
            return False, {"message": "角色名为空"}

        index = self._load_index()
        role_info = index.get(role_name)
        if not isinstance(role_info, dict):
            return False, {"message": "该角色没有缓存"}

        rhash = str(role_info.get("role_hash", ""))
        metadata = self._read_metadata(rhash)
        images = metadata.get("images", []) if isinstance(metadata.get("images"), list) else []
        size_mb = self._dir_size_mb(self._role_dir(rhash))
        return True, {
            "role_name": role_name,
            "image_count": len(images),
            "size_mb": round(size_mb, 2),
            "updated_at": metadata.get("updated_at", "未知"),
        }

    def get_role_features(self, role_name: str) -> str:
        """获取已缓存的角色特征描述"""
        role_name = self.normalize_role_name(role_name)
        index = self._load_index()
        role_info = index.get(role_name)
        if not isinstance(role_info, dict):
            return ""
        rhash = str(role_info.get("role_hash", ""))
        metadata = self._read_metadata(rhash)
        features = metadata.get("features", "")
        return str(features).strip()

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    async def _download_image(self, url: str) -> Tuple[bool, Optional[bytes]]:
        timeout = aiohttp.ClientTimeout(total=20)
        proxy_enabled = self.plugin.get_config("proxy.enabled", False)
        proxy_url = self.plugin.get_config("proxy.url", "") if proxy_enabled else None
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, proxy=proxy_url) as resp:
                    if resp.status != 200:
                        return False, None
                    return True, await resp.read()
        except Exception:
            return False, None

    async def _extract_features(self, image_paths: List[str]) -> str:
        """使用 VLM 从参考图中提取角色特征"""
        if not image_paths:
            return ""

        prompt = str(
            self.plugin.get_config(
                "search_reference.vision_prompt",
                "请用中文详细描述这张图片中主要人物的特征是什么，纯粹描述即可。输出为一段平文本，总字数最多不超过120字。",
            )
        )

        vlm_request = LLMRequest(
            model_set=maibot_model_config.model_task_config.vlm,
            request_type="plugin.role_reference.vlm",
        )
        features: List[str] = []

        for image_path in image_paths[:3]:
            try:
                with open(image_path, "rb") as f:
                    image_bytes = f.read()
                image_base64 = base64.b64encode(image_bytes).decode("utf-8")
                content, _ = await vlm_request.generate_response_for_image(
                    prompt=prompt,
                    image_base64=image_base64,
                    image_format="jpeg",
                    max_tokens=220,
                )
                text = str(content).strip().replace("\n", " ")
                text = re.sub(r"\s+", "", text)
                if text:
                    features.append(text)
            except Exception as e:
                logger.warning(f"VLM提取参考图特征失败: {e}")

        if not features:
            return ""

        merged = "；".join(features)
        if len(merged) > 240:
            merged = merged[:240]
        return merged

    def _cleanup_role_dir(self, role_hash: str, keep_count: int) -> None:
        images_dir = self._images_dir(role_hash)
        if not os.path.isdir(images_dir):
            return
        files = [name for name in os.listdir(images_dir) if os.path.isfile(os.path.join(images_dir, name))]
        files.sort()
        for name in files[keep_count:]:
            try:
                os.remove(os.path.join(images_dir, name))
            except Exception:
                continue

    def _enforce_cache_limit(self) -> None:
        max_cache_mb = int(self.plugin.get_config("search_reference.max_cache_size_mb", 100) or 100)
        max_bytes = max_cache_mb * 1024 * 1024

        index = self._load_index()
        items: List[Tuple[str, str, str]] = []
        for role_name, role_info in index.items():
            if not isinstance(role_info, dict):
                continue
            rhash = str(role_info.get("role_hash", ""))
            updated_at = str(role_info.get("updated_at", ""))
            if rhash:
                items.append((role_name, rhash, updated_at))

        def _total_size() -> int:
            total = 0
            for _, rh, _ in items:
                role_dir = self._role_dir(rh)
                if not os.path.isdir(role_dir):
                    continue
                for root, _, filenames in os.walk(role_dir):
                    for fname in filenames:
                        try:
                            total += os.path.getsize(os.path.join(root, fname))
                        except OSError:
                            continue
            return total

        items.sort(key=lambda x: x[2])
        total = _total_size()

        while total > max_bytes and items:
            role_name, rhash, _ = items.pop(0)
            shutil.rmtree(self._role_dir(rhash), ignore_errors=True)
            index.pop(role_name, None)
            total = _total_size()

        self._save_index(index)

    def _dir_size_mb(self, directory: str) -> float:
        total = 0
        if not os.path.isdir(directory):
            return 0.0
        for root, _, filenames in os.walk(directory):
            for fname in filenames:
                try:
                    total += os.path.getsize(os.path.join(root, fname))
                except OSError:
                    continue
        return total / (1024 * 1024)
