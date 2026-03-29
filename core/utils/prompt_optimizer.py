"""提示词优化器模块

使用 LLM 将用户描述优化为专业的绘画提示词。
支持自定义 API（OpenAI 兼容格式）或使用 MaiBot 主 LLM。
纯净调用，不带人设和回复风格。
"""

from typing import Optional, Tuple

import aiohttp

from src.common.logger import get_logger
from src.plugin_system.apis import llm_api

logger = get_logger("mais_art.optimizer")

# 提示词优化系统提示词（before 模式：中文/简短描述 → 完整英文 prompt）
OPTIMIZER_SYSTEM_PROMPT = """You are a professional AI art prompt engineer. Your task is to convert user descriptions into high-quality English prompts for image generation models (Stable Diffusion, DALL-E, etc.).

## Rules:
1. Output ONLY the English prompt, no explanations or translations
2. Use comma-separated tags/phrases
3. Follow structure: subject, action/pose, scene/background, lighting, style, quality tags
4. Use weight syntax for emphasis: (keyword:1.2) for important elements
5. Keep prompts concise but descriptive (50-150 words ideal)
6. Always end with quality tags: masterpiece, best quality, high resolution
7. Remove duplicate tags from your output. If the same concept appears multiple times with different weights (e.g. "red hair", "(red hair:1.2)"), keep only the highest-weight version.

## Examples:

Input: 海边的女孩
Output: 1girl, solo, standing on beach, ocean waves, sunset sky, orange and pink clouds, warm lighting, summer dress, wind blowing hair, peaceful expression, masterpiece, best quality, high resolution

Input: 可爱的猫咪睡觉
Output: cute cat, sleeping, curled up on soft blanket, fluffy fur, closed eyes, peaceful, warm indoor lighting, cozy atmosphere, detailed fur texture, masterpiece, best quality, high resolution

Input: 赛博朋克城市
Output: cyberpunk cityscape, neon lights, futuristic buildings, flying cars, rain, reflective wet streets, holographic advertisements, purple and blue color scheme, atmospheric, cinematic lighting, masterpiece, best quality, high resolution

Now convert the following description to an English prompt:"""


# 提示词规范化系统提示词（after 模式：已组装好的 tag 串 → 规范化输出）
NORMALIZER_SYSTEM_PROMPT = """You are a professional AI art prompt normalizer. You will receive a pre-assembled English tag string for image generation. Your job is to NORMALIZE it — not rewrite it.

## What you MUST do:

### 1. DEDUPLICATION
Remove duplicate tags. Rules:
- Exact duplicates: remove all but one (e.g. "solo, solo" → "solo")
- Weighted duplicates: if the same root word appears with and without weight, keep the highest-weight version only (e.g. "red hair, (red hair:1.2)" → "(red hair:1.2)")
- Multi-character tags are NOT duplicates: "1girl, 1boy" must be fully preserved
- Different but related tags are NOT duplicates: "red hair, vibrant red hair" are different — keep both

### 2. REORDER
Sort tags in this order:
[character count/gender] → [appearance: hair/eyes/face] → [outfit/accessories] → [action/pose] → [expression/emotional state] → [scene/background] → [lighting/atmosphere] → [quality tags]
Keep closely related tags adjacent to each other.

### 3. QUALITY TAGS
If the following quality tags are missing, append them at the very end:
masterpiece, best quality, high resolution
Do not duplicate them if already present.

### 4. HAND CONFLICT — standard selfie mode only
Activate this rule when the input contains selfie-related tags such as: selfie, looking at viewer, phone, holding phone, (selfie:1.4).
- In standard selfie, one hand holds the phone (arm extended toward camera, hand out of frame).
- Only ONE visible hand action is valid.
- If multiple conflicting hand action tags exist (e.g. "peace sign, hand on hip, holding bag"), keep exactly one — prefer the most expressive/specific one.
- If the input contains a user-specified hand action (tagged with context: free_hand_action), that action has the HIGHEST priority and must be kept.
- Ensure these clarifying tags are present: arm reaching toward camera, one hand out of frame
- Remove any tags that imply more than two visible hands.

### 5. WEIGHT FORMAT
Use (tag:1.x) format only. Do not use any other weight syntax (no [[tag]], no {tag}, no <tag>).

## What you MUST NOT do:
- Do NOT add new appearance tags (hair color, eye color, clothing, body type, etc.) that are not in the input
- Do NOT remove or change character count tags (1girl, 1boy, 2girls, etc.)
- Do NOT add tags that have no basis in the input
- Do NOT rewrite, paraphrase, or replace existing tags with synonyms
- Do NOT change the meaning of any existing tag
- Do NOT add narrative text or explanations

## Output format:
Output ONLY the normalized tag string. No explanations. No line breaks. Comma-separated tags only."""

# 自拍场景专用提示词：只生成场景/环境/光线/氛围，不生成角色外观
SELFIE_SCENE_SYSTEM_PROMPT = """You are a scene description assistant for selfie image generation. The character's appearance is already defined separately. Your task is to convert the user's description into English tags describing ONLY the scene, environment, lighting, mood, and atmosphere.

## Rules:
1. Output ONLY English tags, no explanations
2. Use comma-separated tags/phrases
3. NEVER include character appearance (hair color, eye color, clothing, body type, etc.)
4. NEVER include character names or franchise references
5. Focus on: background, environment, lighting, weather, mood, atmosphere, time of day
6. Keep it concise (20-60 words)
7. If the description is just "selfie" or similar with no scene info, output a simple generic scene

## Examples:

Input: 在海边自拍
Output: beach background, ocean waves, golden sunset, warm sunlight, sand, gentle breeze, summer atmosphere

Input: 图书馆学习
Output: library interior, bookshelves, warm ambient lighting, quiet atmosphere, wooden desk, soft focus background

Input: 来张自拍
Output: casual indoor setting, soft natural lighting, clean background

Input: 下雨天在咖啡店
Output: coffee shop interior, rainy window, warm cozy atmosphere, soft indoor lighting, rain drops on glass, bokeh background

Now convert the following description to English scene tags:"""


class PromptOptimizer:
    """提示词优化器

    支持两种模式：
    1. 自定义 API（OpenAI 兼容 chat/completions），优先使用
    2. MaiBot 主 LLM（llm_api），作为回退方案
    """

    def __init__(self, log_prefix: str = "[PromptOptimizer]"):
        self.log_prefix = log_prefix
        self._model_config = None

    def _get_model_config(self):
        """获取可用的 MaiBot LLM 模型配置"""
        if self._model_config is None:
            try:
                models = llm_api.get_available_models()
                # 使用 replyer 模型（首要回复模型）
                if "replyer" in models:
                    self._model_config = models["replyer"]
                else:
                    logger.warning(f"{self.log_prefix} 没有找到 replyer 模型")
                    return None
            except Exception as e:
                logger.error(f"{self.log_prefix} 获取模型配置失败: {e}")
                return None
        return self._model_config

    @staticmethod
    def _has_custom_api(
        custom_api_base_url: str,
        custom_api_key: str,
        custom_api_model: str,
    ) -> bool:
        """判断是否配置了有效的自定义 API（三个字段都必须非空）"""
        return bool(
            custom_api_base_url
            and custom_api_base_url.strip()
            and custom_api_key
            and custom_api_key.strip()
            and custom_api_model
            and custom_api_model.strip()
        )

    async def _call_custom_api(
        self,
        system_prompt: str,
        user_message: str,
        base_url: str,
        api_key: str,
        model: str,
    ) -> Tuple[bool, str]:
        """调用自定义 OpenAI 兼容 API

        Args:
            system_prompt: 系统提示词
            user_message: 用户消息
            base_url: API 地址（如 https://api.deepseek.com/v1）
            api_key: API 密钥
            model: 模型名称

        Returns:
            Tuple[bool, str]: (是否成功, 生成内容或错误信息)
        """
        url = f"{base_url.rstrip('/')}/chat/completions"

        # 处理 API Key 格式：自动添加 Bearer 前缀
        auth_key = api_key.strip()
        if auth_key.lower().startswith("bearer "):
            authorization = auth_key
        else:
            authorization = f"Bearer {auth_key}"

        headers = {
            "Content-Type": "application/json",
            "Authorization": authorization,
        }

        payload = {
            "model": model.strip(),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "temperature": 0.7,
        }

        try:
            timeout = aiohttp.ClientTimeout(total=60)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        content: str = data["choices"][0]["message"]["content"]
                        return True, content
                    else:
                        error_text = await resp.text()
                        logger.error(f"{self.log_prefix} 自定义API返回错误 (HTTP {resp.status}): {error_text[:200]}")
                        return False, f"自定义API错误: HTTP {resp.status}"
        except aiohttp.ClientError as e:
            logger.error(f"{self.log_prefix} 自定义API连接失败: {e}")
            return False, f"自定义API连接失败: {e}"
        except KeyError as e:
            logger.error(f"{self.log_prefix} 自定义API响应格式异常，缺少字段: {e}")
            return False, f"自定义API响应格式异常: {e}"
        except Exception as e:
            logger.error(f"{self.log_prefix} 自定义API调用异常: {e}")
            return False, f"自定义API调用异常: {e}"

    async def optimize(
        self,
        user_description: str,
        scene_only: bool = False,
        normalize_mode: bool = False,
        selfie_style: str = "",
        custom_api_base_url: str = "",
        custom_api_key: str = "",
        custom_api_model: str = "",
    ) -> Tuple[bool, str]:
        """优化用户描述为专业绘画提示词

        优先使用自定义 API，未配置时回退到 MaiBot 主 LLM。

        Args:
            user_description: 用户原始描述（中文或英文）
            scene_only: 仅生成场景/环境描述（自拍模式用，不包含角色外观）
            normalize_mode: 规范化模式（after 时机用），对已组装好的 tag 串做查重/排序/补全
            selfie_style: 自拍风格（standard/mirror/photo），normalize_mode 下用于激活手部冲突检测
            custom_api_base_url: 自定义 API 地址（OpenAI 兼容），留空使用 MaiBot 主 LLM
            custom_api_key: 自定义 API 密钥
            custom_api_model: 自定义模型名称

        Returns:
            Tuple[bool, str]: (是否成功, 优化后的提示词或错误信息)
        """
        if not user_description or not user_description.strip():
            return False, "描述不能为空"

        # 根据模式选择系统提示词
        if normalize_mode:
            system_prompt = NORMALIZER_SYSTEM_PROMPT
            mode_label = "规范化提示词"
        elif scene_only:
            system_prompt = SELFIE_SCENE_SYSTEM_PROMPT
            mode_label = "场景提示词"
        else:
            system_prompt = OPTIMIZER_SYSTEM_PROMPT
            mode_label = "提示词"
        user_input = user_description.strip()

        # ---- 路径 1: 自定义 API ----
        if self._has_custom_api(custom_api_base_url, custom_api_key, custom_api_model):
            logger.info(
                f"{self.log_prefix} 使用自定义API优化{mode_label} (模型: {custom_api_model}): {user_input[:50]}..."
            )
            success, response = await self._call_custom_api(
                system_prompt=system_prompt,
                user_message=f"{user_input}" if normalize_mode else f"Input: {user_input}\nOutput:",
                base_url=custom_api_base_url,
                api_key=custom_api_key,
                model=custom_api_model,
            )
            if success and response:
                optimized = self._clean_response(response)
                logger.info(f"{self.log_prefix} 自定义API优化成功 (模型: {custom_api_model}): {optimized[:80]}...")
                return True, optimized
            else:
                logger.warning(f"{self.log_prefix} 自定义API优化失败，降级使用原始描述: {user_input[:50]}...")
                return True, user_description

        # ---- 路径 2: MaiBot 主 LLM (回退) ----
        model_config = self._get_model_config()
        if not model_config:
            # 降级：直接返回原始描述
            logger.warning(f"{self.log_prefix} 无可用模型，降级使用原始描述")
            return True, user_description

        try:
            # 构建完整 prompt（normalize_mode 直接输入 tag 串，否则用 Input/Output 格式）
            full_prompt = (
                f"{system_prompt}\n\n{user_input}"
                if normalize_mode
                else f"{system_prompt}\n\nInput: {user_input}\nOutput:"
            )

            logger.info(f"{self.log_prefix} 使用MaiBot主LLM优化{mode_label}: {user_input[:50]}...")

            # 调用 LLM（不传递 temperature 和 max_tokens，使用模型默认值）
            success, response, reasoning, model_name = await llm_api.generate_with_model(
                prompt=full_prompt,
                model_config=model_config,
                request_type="plugin.prompt_optimize",
            )

            if success and response:
                # 清理响应（移除可能的前缀/后缀）
                optimized = self._clean_response(response)
                logger.info(f"{self.log_prefix} 优化成功 (模型: {model_name}): {optimized[:80]}...")
                return True, optimized
            else:
                logger.warning(f"{self.log_prefix} LLM 返回空响应，降级使用原始描述: {user_input[:50]}...")
                return True, user_description

        except Exception as e:
            logger.error(f"{self.log_prefix} 优化失败: {e}，使用原始描述: {user_input[:50]}...")
            # 降级：返回原始描述
            return True, user_description

    def _clean_response(self, response: str) -> str:
        """清理 LLM 响应

        移除可能的前缀、后缀、引号等
        """
        result = response.strip()

        # 移除可能的 "Output:" 前缀
        prefixes_to_remove = ["Output:", "output:", "Prompt:", "prompt:"]
        for prefix in prefixes_to_remove:
            if result.startswith(prefix):
                result = result[len(prefix) :].strip()

        # 移除首尾引号
        if (result.startswith('"') and result.endswith('"')) or (result.startswith("'") and result.endswith("'")):
            result = result[1:-1]

        # 移除多余换行
        result = " ".join(result.split())

        return result


# 全局优化器实例
_optimizer_instance: Optional[PromptOptimizer] = None


def get_optimizer(log_prefix: str = "[PromptOptimizer]") -> PromptOptimizer:
    """获取提示词优化器实例（单例）"""
    global _optimizer_instance
    if _optimizer_instance is None:
        _optimizer_instance = PromptOptimizer(log_prefix)
    else:
        _optimizer_instance.log_prefix = log_prefix
    return _optimizer_instance


async def optimize_prompt(
    user_description: str,
    log_prefix: str = "[PromptOptimizer]",
    scene_only: bool = False,
    normalize_mode: bool = False,
    selfie_style: str = "",
    custom_api_base_url: str = "",
    custom_api_key: str = "",
    custom_api_model: str = "",
) -> Tuple[bool, str]:
    """便捷函数：优化提示词

    Args:
        user_description: 用户原始描述
        log_prefix: 日志前缀
        scene_only: 仅生成场景/环境描述（自拍模式用）
        normalize_mode: 规范化模式（after 时机用），对已组装好的 tag 串做查重/排序/补全
        selfie_style: 自拍风格（standard/mirror/photo），normalize_mode 下激活手部冲突检测
        custom_api_base_url: 自定义 API 地址（OpenAI 兼容），留空使用 MaiBot 主 LLM
        custom_api_key: 自定义 API 密钥
        custom_api_model: 自定义模型名称

    Returns:
        Tuple[bool, str]: (是否成功, 优化后的提示词)
    """
    optimizer = get_optimizer(log_prefix)
    return await optimizer.optimize(
        user_description,
        scene_only=scene_only,
        normalize_mode=normalize_mode,
        selfie_style=selfie_style,
        custom_api_base_url=custom_api_base_url,
        custom_api_key=custom_api_key,
        custom_api_model=custom_api_model,
    )
