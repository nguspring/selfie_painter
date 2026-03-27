"""OpenAI Chat Completions 格式API客户端

通过 chat/completions 接口生成图片，适用于支持图片生成的 chat 模型。
支持流式（SSE）和非流式响应，兼容 grok2api 等强制流式服务。
多策略图片提取：Markdown图片链接、Data URI、Base64特征、URL。
"""

import json
import re
import urllib.request
from typing import Dict, Any, Tuple, Optional

from .base_client import BaseApiClient, logger


class OpenAIChatClient(BaseApiClient):
    """OpenAI Chat Completions 格式API客户端

    通过 /chat/completions 端点请求图片生成，
    从模型的文本响应中提取图片数据。
    """

    format_name = "openai-chat"

    def _make_request(
        self,
        prompt: str,
        model_config: Dict[str, Any],
        size: str,
        strength: Optional[float] = None,
        input_image_base64: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """发送 Chat Completions 格式的HTTP请求生成图片"""
        base_url = model_config.get("base_url", "")
        api_key = model_config.get("api_key", "")
        model = model_config.get("model", "")

        endpoint = f"{base_url.rstrip('/')}/chat/completions"

        # 获取模型特定的配置参数
        custom_prompt_add = model_config.get("custom_prompt_add", "")
        negative_prompt_add = model_config.get("negative_prompt_add", "")
        full_prompt = prompt + custom_prompt_add

        # 如果有负面提示词，追加到提示中
        if negative_prompt_add:
            full_prompt += f"\n\nNegative prompt (avoid these): {negative_prompt_add}"

        # 构建 chat messages
        messages: list[Dict[str, Any]] = []

        # 系统消息：指导模型生成图片
        system_content = (
            "You are an image generation assistant. Generate an image based on the user's description. "
            f"Target image size: {size}."
        )
        messages.append({"role": "system", "content": system_content})

        # 用户消息
        user_content_parts = []

        # 如果有输入图片（图生图场景），添加图片
        if input_image_base64:
            image_data_uri = self._prepare_image_data_uri(input_image_base64)
            user_content_parts.append({"type": "image_url", "image_url": {"url": image_data_uri}})
            strength_text = f" (modification strength: {strength})" if strength else ""
            user_content_parts.append(
                {
                    "type": "text",
                    "text": f"Please modify this image based on the following description{strength_text}: {full_prompt}",
                }
            )
            messages.append({"role": "user", "content": user_content_parts})
        else:
            messages.append({"role": "user", "content": f"Please generate an image: {full_prompt}"})

        # 构建请求体
        payload_dict: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": True,  # 启用流式以兼容强制流式服务（如 grok2api）
        }

        # 添加可选的生成参数
        seed = model_config.get("seed", -1)
        if seed is not None and seed != -1:
            payload_dict["seed"] = seed

        # 某些模型支持 size 参数
        if size:
            payload_dict["size"] = size
        data = json.dumps(payload_dict, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream, application/json",
            "Authorization": f"{api_key}",
        }

        # 详细调试信息
        verbose_debug = False
        try:
            verbose_debug = self.action.get_config("components.enable_verbose_debug", False)
        except (AttributeError, TypeError, KeyError) as exc:
            logger.debug(f"{self.log_prefix} (OpenAI-Chat) 读取详细调试开关失败，使用默认值: {exc}")

        if verbose_debug:
            safe_payload: Dict[str, Any] = payload_dict.copy()
            # 清理敏感数据
            if "messages" in safe_payload:
                raw_messages = safe_payload.get("messages", [])
                if isinstance(raw_messages, list):
                    safe_msgs: list[Dict[str, Any]] = []
                    for msg in raw_messages:
                        if not isinstance(msg, dict):
                            continue
                        msg_content = msg.get("content")
                        if isinstance(msg_content, list):
                            safe_parts: list[Dict[str, Any]] = []
                            for part in msg_content:
                                if isinstance(part, dict) and part.get("type") == "image_url":
                                    safe_parts.append({"type": "image_url", "image_url": {"url": "[BASE64_DATA...]"}})
                                elif isinstance(part, dict):
                                    safe_parts.append(part)
                            safe_msgs.append({"role": msg.get("role", "user"), "content": safe_parts})
                        else:
                            safe_msgs.append(msg)
                    safe_payload["messages"] = safe_msgs
            safe_headers = headers.copy()
            if "Authorization" in safe_headers:
                auth_value = safe_headers["Authorization"]
                if auth_value.startswith("Bearer "):
                    safe_headers["Authorization"] = "Bearer ***"
                else:
                    safe_headers["Authorization"] = "***"
            logger.info(f"{self.log_prefix} (OpenAI-Chat) 详细调试 - 请求端点: {endpoint}")
            logger.info(f"{self.log_prefix} (OpenAI-Chat) 详细调试 - 请求头: {safe_headers}")
            logger.info(
                f"{self.log_prefix} (OpenAI-Chat) 详细调试 - 请求体: {json.dumps(safe_payload, ensure_ascii=False, indent=2)}"
            )

        logger.info(
            f"{self.log_prefix} (OpenAI-Chat) 发起 chat/completions 请求: {model}, Prompt: {full_prompt[:30]}... To: {endpoint}"
        )

        # 获取代理配置
        proxy_config = self._get_proxy_config()

        req = urllib.request.Request(endpoint, data=data, headers=headers, method="POST")

        try:
            # 构建 opener（局部使用，不污染全局）
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
                response_status = response.status
                content_type = response.headers.get("Content-Type", "")

                logger.info(
                    f"{self.log_prefix} (OpenAI-Chat) 响应状态: {response_status}, Content-Type: {content_type}"
                )

                if 200 <= response_status < 300:
                    # 检测是否为 SSE 流式响应（优先通过 Content-Type 判断）
                    is_sse = "text/event-stream" in content_type

                    if is_sse:
                        # SSE 流式响应：逐行读取避免 read() 返回空
                        logger.info(f"{self.log_prefix} (OpenAI-Chat) 检测到 SSE 流式响应，开始逐行读取")
                        sse_lines: list[str] = []
                        for raw_line in response:
                            line = raw_line.decode("utf-8", errors="replace")
                            sse_lines.append(line)
                        response_body_str = "".join(sse_lines)
                    else:
                        # 非流式响应：一次性读取
                        response_body_bytes = response.read()
                        response_body_str = response_body_bytes.decode("utf-8")

                    if verbose_debug:
                        cleaned = self._clean_log_content(response_body_str)
                        logger.info(f"{self.log_prefix} (OpenAI-Chat) 详细调试 - 响应体: {cleaned[:500]}")

                    stripped = response_body_str.strip()
                    logger.info(
                        f"{self.log_prefix} (OpenAI-Chat) 响应体长度: {len(stripped)}, 前200字符: {stripped[:200]}"
                    )

                    if is_sse or stripped.startswith("data:") or stripped.startswith("event:"):
                        # SSE 流式响应（grok2api 等服务强制返回流式）
                        content, image_result = self._parse_sse_stream(stripped)
                        if image_result:
                            logger.info(f"{self.log_prefix} (OpenAI-Chat) SSE 流式响应中提取到图片数据")
                            return True, image_result
                        if content:
                            return self._extract_image_from_content(content)

                        logger.error(f"{self.log_prefix} (OpenAI-Chat) SSE 流式响应中无有效内容")
                        return False, "SSE 流式响应中未找到图片数据"
                    else:
                        # 普通 JSON 响应（非流式服务或服务端忽略了 stream 参数）
                        response_data = json.loads(stripped)
                        return self._extract_image_from_response(response_data)
                else:
                    response_body_bytes = response.read()
                    response_body_str = response_body_bytes.decode("utf-8")
                    logger.error(
                        f"{self.log_prefix} (OpenAI-Chat) API请求失败. 状态: {response_status}. 正文: {response_body_str[:300]}..."
                    )
                    return False, f"Chat API请求失败(状态码 {response_status})"

        except Exception as e:
            logger.error(f"{self.log_prefix} (OpenAI-Chat) 请求异常: {e!r}", exc_info=True)
            return False, f"Chat API请求异常: {str(e)[:100]}"

    def _parse_sse_stream(self, raw_sse: str) -> Tuple[str, Optional[str]]:
        """解析 SSE（Server-Sent Events）流式响应。

        SSE 格式示例（OpenAI chat completion chunk）：
            data: {"id":"xxx","object":"chat.completion.chunk","choices":[{"delta":{"content":"..."}}]}
            data: [DONE]

        Args:
            raw_sse: 原始 SSE 响应文本

        Returns:
            (拼接后的完整 content 文本, 提取到的图片数据)
        """
        content_parts: list[str] = []
        image_result: Optional[str] = None

        for line in raw_sse.split("\n"):
            line = line.strip()
            if not line:
                continue

            # 跳过 event: 行和其他非 data 行
            if not line.startswith("data:"):
                continue

            data_str = line[len("data:") :].strip()

            # 结束标记
            if data_str == "[DONE]":
                break

            # 解析 JSON chunk
            try:
                chunk = json.loads(data_str)
            except json.JSONDecodeError:
                logger.debug(f"{self.log_prefix} (OpenAI-Chat) SSE 跳过无效 JSON: {data_str[:80]}")
                continue

            # 从 chunk 中提取 delta.content
            try:
                choices = chunk.get("choices", [])
                if choices:
                    choice = choices[0]
                    delta = choice.get("delta", {})

                    if not image_result and isinstance(delta, dict):
                        image_result = self._extract_image_from_message(delta)
                    if not image_result:
                        message = choice.get("message", {})
                        if isinstance(message, dict):
                            image_result = self._extract_image_from_message(message)

                    delta_content = delta.get("content", "")
                    if isinstance(delta_content, str) and delta_content:
                        content_parts.append(delta_content)
            except (IndexError, KeyError, TypeError):
                pass

        full_content = "".join(content_parts)
        if full_content:
            logger.info(f"{self.log_prefix} (OpenAI-Chat) SSE 解析完成，内容长度: {len(full_content)}")
        return full_content, image_result

    def _extract_image_from_content(self, content: str) -> Tuple[bool, str]:
        """从拼接后的文本内容中提取图片数据

        复用 _extract_image_from_response 的多策略提取逻辑，
        但直接接收 content 字符串而非完整的 response_data dict。

        Args:
            content: 拼接后的完整文本（可能包含 Markdown 图片、URL、Base64 等）

        Returns:
            (成功标志, 图片数据或错误信息)
        """
        if not content:
            logger.error(f"{self.log_prefix} (OpenAI-Chat) 响应中无内容")
            return False, "Chat API响应中无内容"

        extracted = self._extract_image_from_text(content)
        if extracted:
            return True, extracted

        logger.error(f"{self.log_prefix} (OpenAI-Chat) 无法从响应中提取图片。内容预览: {content[:200]}...")
        return False, "无法从 Chat API 响应中提取图片数据"

    def _extract_image_from_part(self, part: Dict[str, Any]) -> Optional[str]:
        """从单个多模态片段中提取图片数据。"""
        if not isinstance(part, dict):
            return None

        image_url = part.get("image_url")
        if isinstance(image_url, dict):
            url = image_url.get("url")
            if isinstance(url, str) and url:
                return url

        for key in ("url", "b64_json"):
            value = part.get(key)
            if isinstance(value, str) and value:
                return value

        return None

    def _extract_image_from_message(self, message: Dict[str, Any]) -> Optional[str]:
        """从 chat/completions 的 message 或 delta 结构中提取图片数据。"""
        if not isinstance(message, dict):
            return None

        images = message.get("images")
        if isinstance(images, list):
            for image_part in images:
                if not isinstance(image_part, dict):
                    continue
                extracted = self._extract_image_from_part(image_part)
                if extracted:
                    logger.info(f"{self.log_prefix} (OpenAI-Chat) 从 message.images 提取到图片数据")
                    return extracted

        content = message.get("content", "")
        if isinstance(content, list):
            for item in content:
                if not isinstance(item, dict):
                    continue
                extracted = self._extract_image_from_part(item)
                if extracted:
                    logger.info(f"{self.log_prefix} (OpenAI-Chat) 从多模态 content 提取到图片数据")
                    return extracted

                if item.get("type") == "text":
                    text = item.get("text", "")
                    if isinstance(text, str):
                        extracted = self._extract_image_from_text(text)
                        if extracted:
                            return extracted

        return None

    def _extract_image_from_text(self, content: str) -> Optional[str]:
        """从文本中提取图片数据。"""
        if not content:
            return None

        # 策略1：Markdown 图片链接 ![alt](url)
        md_pattern = r"!\[.*?\]\((https?://[^\s\)]+)\)"
        md_matches = re.findall(md_pattern, content)
        if md_matches:
            image_url = md_matches[0]
            logger.info(f"{self.log_prefix} (OpenAI-Chat) 从 Markdown 提取到图片URL: {image_url[:70]}...")
            return image_url

        # 策略2：Data URI (data:image/xxx;base64,...)
        data_uri_pattern = r"data:image/[a-zA-Z]+;base64,([A-Za-z0-9+/=]+)"
        data_uri_matches = re.findall(data_uri_pattern, content)
        if data_uri_matches:
            b64_data = data_uri_matches[0]
            logger.info(f"{self.log_prefix} (OpenAI-Chat) 从 Data URI 提取到 Base64 数据，长度: {len(b64_data)}")
            return b64_data

        # 策略3：Base64 特征检测（连续长 base64 字符串）
        b64_pattern = r"(?<![A-Za-z0-9+/])([A-Za-z0-9+/]{200,}={0,2})(?![A-Za-z0-9+/])"
        b64_matches = re.findall(b64_pattern, content)
        if b64_matches:
            # 取最长的匹配
            longest = max(b64_matches, key=len)
            # 验证是否是有效的 base64 图片数据
            if longest.startswith(("/9j/", "iVBORw", "UklGR", "R0lGOD")) or len(longest) > 1000:
                logger.info(f"{self.log_prefix} (OpenAI-Chat) 检测到 Base64 图片数据，长度: {len(longest)}")
                return longest

        # 策略4：普通 URL（http/https 图片链接）
        url_pattern = r'(https?://[^\s<>"\']+\.(?:png|jpg|jpeg|gif|webp|bmp)(?:\?[^\s<>"\']*)?)'
        url_matches = re.findall(url_pattern, content, re.IGNORECASE)
        if url_matches:
            image_url = url_matches[0]
            logger.info(f"{self.log_prefix} (OpenAI-Chat) 从内容提取到图片URL: {image_url[:70]}...")
            return image_url

        # 策略5：任意 URL（可能是不带扩展名的图片链接）
        any_url_pattern = r'(https?://[^\s<>"\']+)'
        any_url_matches = re.findall(any_url_pattern, content)
        if any_url_matches:
            # 只取第一个 URL，可能是图片
            image_url = any_url_matches[0]
            logger.info(f"{self.log_prefix} (OpenAI-Chat) 从内容提取到候选URL: {image_url[:70]}...")
            return image_url

        return None

    def _extract_image_from_response(self, response_data: Dict[str, Any]) -> Tuple[bool, str]:
        """从 chat/completions 响应中提取图片数据。

        兼容结构：
        1. choices[0].message.images[].image_url.url
        2. choices[0].message.content 中的多模态图片片段
        3. content 文本里的 Markdown/Data URI/Base64/URL
        """
        content = ""
        try:
            choices = response_data.get("choices", [])
            if choices:
                message = choices[0].get("message", {})
                if isinstance(message, dict):
                    extracted = self._extract_image_from_message(message)
                    if extracted:
                        return True, extracted

                    content_value = message.get("content", "")
                    if isinstance(content_value, str):
                        content = content_value
            else:
                top_level_images = response_data.get("images")
                if isinstance(top_level_images, list):
                    extracted = self._extract_image_from_message({"images": top_level_images})
                    if extracted:
                        return True, extracted
        except (IndexError, KeyError, TypeError):
            pass

        if not content:
            logger.error(f"{self.log_prefix} (OpenAI-Chat) 响应中无内容")
            return False, "Chat API响应中无内容"

        logger.debug(f"{self.log_prefix} (OpenAI-Chat) 提取图片，内容长度: {len(content)}")

        extracted = self._extract_image_from_text(content)
        if extracted:
            return True, extracted

        logger.error(f"{self.log_prefix} (OpenAI-Chat) 无法从响应中提取图片。内容预览: {content[:200]}...")
        return False, "无法从 Chat API 响应中提取图片数据"

    def _clean_log_content(self, content: str) -> str:
        """清理日志中的长 base64 数据"""
        # 替换长 base64 字符串
        cleaned = re.sub(r"[A-Za-z0-9+/]{200,}={0,2}", "[BASE64_DATA...]", content)
        return cleaned
