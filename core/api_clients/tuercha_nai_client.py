"""tuercha-NAI API 客户端。

该服务使用 OpenAI Chat Completions 外壳承载 NovelAI 绘图参数：
外层 `model` 是真实模型名，`messages[0].content` 必须是 JSON 对象字符串。
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple

from .base_client import BaseApiClient, logger


class TuerchaNAIClient(BaseApiClient):
    """tuercha-NAI 绘图客户端。

    负责把插件统一的生图参数转换为服务端要求的 chat/completions 请求体，
    并从 markdown 图片响应中提取 base64 图片数据。
    """

    format_name = "tuercha-NAI"

    _DATA_URI_RE = re.compile(r"data:image/(?:png|webp|jpeg|jpg);base64,([A-Za-z0-9+/=]+)")
    _MARKDOWN_DATA_URI_RE = re.compile(r"!\[[^\]]*\]\((data:image/[^;)]+;base64,[^)]+)\)")

    def _parse_size(self, size: str) -> list[int]:
        """把插件的 `宽x高` 字符串转换成提供方要求的整数数组。

        Args:
            size: 插件内部传入的尺寸字符串，例如 `832x1216`。

        Returns:
            `[width, height]` 整数数组。

        Raises:
            ValueError: 当尺寸不是 `宽x高` 或宽高不是正整数时抛出。
        """
        if not isinstance(size, str) or "x" not in size.lower():
            raise ValueError("tuercha-NAI 要求尺寸格式为 宽x高，例如 832x1216")

        width_text, height_text = size.lower().split("x", 1)
        width = int(width_text.strip())
        height = int(height_text.strip())
        if width <= 0 or height <= 0:
            raise ValueError("tuercha-NAI 要求宽高必须为正整数")
        return [width, height]

    def _build_inner_payload(
        self,
        prompt: str,
        model_config: Dict[str, Any],
        size: str,
        strength: Optional[float],
        input_image_base64: Optional[str],
    ) -> Dict[str, Any]:
        """构建 `messages[0].content` 内部 JSON 对象。

        Args:
            prompt: 已由上游准备好的正向提示词。
            model_config: 当前模型配置。
            size: 图片尺寸字符串。
            strength: 图生图强度，只有传入参考图时使用。
            input_image_base64: 可选参考图 base64。

        Returns:
            可直接 `json.dumps` 的内部绘图参数。
        """
        full_prompt = f"{prompt}{model_config.get('custom_prompt_add', '')}"
        payload: Dict[str, Any] = {
            "prompt": full_prompt,
            "size": self._parse_size(size or model_config.get("default_size", "832x1216")),
            "steps": min(int(model_config.get("num_inference_steps", 23)), 28),
            "scale": model_config.get("guidance_scale", 5),
            "sampler": model_config.get("sampler", "k_euler_ancestral"),
            "image_format": model_config.get("image_format", "png"),
        }

        negative_prompt = model_config.get("negative_prompt_add", "")
        if negative_prompt:
            payload["negative_prompt"] = negative_prompt

        seed = model_config.get("seed", -1)
        if seed is not None and seed != -1:
            payload["seed"] = seed

        cfg_rescale = model_config.get("cfg", None)
        if cfg_rescale not in (None, "", 0):
            payload["cfg_rescale"] = cfg_rescale

        noise_schedule = model_config.get("noise_schedule", "")
        if noise_schedule in {"karras", "exponential", "polyexponential"}:
            payload["noise_schedule"] = noise_schedule

        variety_boost = model_config.get("variety_boost", None)
        if isinstance(variety_boost, bool):
            payload["variety_boost"] = variety_boost

        if input_image_base64:
            payload["i2i"] = {
                "image": self._prepare_image_data_uri(input_image_base64),
                "strength": strength if strength is not None else 0.7,
                "noise": model_config.get("i2i_noise", 0),
            }

        return payload

    def _extract_image_base64(self, response_data: Dict[str, Any]) -> Tuple[bool, str]:
        """从 chat/completions 响应里提取第一张 data URI 图片。

        Args:
            response_data: 服务端 JSON 响应。

        Returns:
            `(True, base64)` 或 `(False, 错误说明)`。
        """
        try:
            content = response_data["choices"][0]["message"].get("content", "")
        except (KeyError, IndexError, TypeError):
            return False, "tuercha-NAI 响应缺少 choices[0].message.content"

        if not isinstance(content, str) or not content:
            return False, "tuercha-NAI 响应内容为空"

        markdown_matches = self._MARKDOWN_DATA_URI_RE.findall(content)
        if markdown_matches:
            data_uri = markdown_matches[0]
            match = self._DATA_URI_RE.search(data_uri)
            if match:
                return True, match.group(1)

        match = self._DATA_URI_RE.search(content)
        if match:
            return True, match.group(1)

        return False, f"tuercha-NAI 响应中未找到 data:image base64 图片，预览: {content[:160]}"

    def _make_request(
        self,
        prompt: str,
        model_config: Dict[str, Any],
        size: str,
        strength: Optional[float] = None,
        input_image_base64: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """发送 tuercha-NAI chat/completions 请求生成图片。"""
        base_url = str(model_config.get("base_url", "")).rstrip("/")
        api_key = str(model_config.get("api_key", ""))
        model = str(model_config.get("model", ""))
        endpoint = f"{base_url}/chat/completions"

        try:
            inner_payload = self._build_inner_payload(prompt, model_config, size, strength, input_image_base64)
        except (TypeError, ValueError) as exc:
            logger.error(f"{self.log_prefix} (tuercha-NAI) 参数构建失败: {exc}")
            return False, str(exc)

        outer_payload: Dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": json.dumps(inner_payload, ensure_ascii=False)}],
            "stream": False,
            "max_tokens": int(model_config.get("max_tokens", 100000)),
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": api_key,
        }

        verbose_debug = False
        try:
            verbose_debug = bool(self.action.get_config("components.enable_verbose_debug", False))
        except (AttributeError, TypeError, KeyError):
            verbose_debug = False

        if verbose_debug:
            safe_payload = json.loads(json.dumps(outer_payload, ensure_ascii=False))
            content = json.loads(safe_payload["messages"][0]["content"])
            if "i2i" in content:
                content["i2i"]["image"] = "[BASE64_DATA...]"
            safe_payload["messages"][0]["content"] = json.dumps(content, ensure_ascii=False)
            safe_headers = headers.copy()
            safe_headers["Authorization"] = "Bearer ***" if api_key.startswith("Bearer ") else "***"
            logger.info(f"{self.log_prefix} (tuercha-NAI) 详细调试 - 请求端点: {endpoint}")
            logger.info(f"{self.log_prefix} (tuercha-NAI) 详细调试 - 请求头: {safe_headers}")
            logger.info(
                f"{self.log_prefix} (tuercha-NAI) 详细调试 - 请求体: {json.dumps(safe_payload, ensure_ascii=False, indent=2)}"
            )

        logger.info(f"{self.log_prefix} (tuercha-NAI) 发起图片请求: {model}, Size: {inner_payload.get('size')}")
        data = json.dumps(outer_payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(endpoint, data=data, headers=headers, method="POST")
        proxy_config = self._get_proxy_config()

        try:
            if proxy_config:
                proxy_handler = urllib.request.ProxyHandler(
                    {"http": proxy_config["http"], "https": proxy_config["https"]}
                )
                opener = urllib.request.build_opener(proxy_handler)
                timeout = proxy_config.get("timeout", 600)
            else:
                opener = urllib.request.build_opener()
                timeout = 600

            with opener.open(req, timeout=timeout) as response:
                response_body = response.read().decode("utf-8")
                if not 200 <= response.status < 300:
                    logger.error(
                        f"{self.log_prefix} (tuercha-NAI) 请求失败: HTTP {response.status}, 正文: {response_body[:300]}"
                    )
                    return False, f"tuercha-NAI 请求失败(状态码 {response.status})"

                response_data = json.loads(response_body)
                return self._extract_image_base64(response_data)
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            logger.error(f"{self.log_prefix} (tuercha-NAI) HTTP错误: {exc.code}, 正文: {error_body[:300]}")
            return False, f"tuercha-NAI 请求失败(状态码 {exc.code})"
        except json.JSONDecodeError as exc:
            logger.error(f"{self.log_prefix} (tuercha-NAI) 响应 JSON 解析失败: {exc}")
            return False, "tuercha-NAI 响应不是合法 JSON"
        except Exception as exc:
            logger.error(f"{self.log_prefix} (tuercha-NAI) 请求异常: {exc!r}", exc_info=True)
            return False, f"tuercha-NAI 请求异常: {str(exc)[:100]}"
