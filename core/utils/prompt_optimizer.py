"""提示词优化器模块。

使用 LLM 将用户描述优化为适合生图的最终提示词。
支持自定义 API（OpenAI 兼容格式）或使用 MaiBot 主 LLM。
纯净调用，不带人设和回复风格。
"""

from __future__ import annotations

from typing import Optional, Tuple

import aiohttp

from src.common.logger import get_logger
from src.plugin_system.apis import llm_api

logger = get_logger("mais_art.optimizer")

# NAI 格式生成器提示词
NAI_GENERATOR_SYSTEM_PROMPT = """You are a professional NovelAI (NAI) prompt engineer. Convert all input information into a flat, comma-separated English tag stream suitable for direct use with NAI image generation.

## Output Rules

### Length Control
Total output must be 300~450 tokens. Never exceed 512 tokens. If input has many characters, simplify background/secondary character details rather than exceeding the limit. If input is sparse (single character, simple scene), add more detail to reach at least 300 tokens.

### Weight Format
Use ONLY `n::tag::` format for emphasis. n>1.0 strengthens, n<1.0 weakens.
Example: `1.5::pink hair::` (strong emphasis), `0.6::utility pole::` (de-emphasized)
Do NOT use bracket weights like (tag:1.5) or {{tag}}.

### Tag Ordering (strict, from macro to micro)
1. [Global]: rating tag (SFW/NSFW) → character count (1girl, solo, duo, etc.) → character relationships (hetero, yuri, etc.)
2. [Scene]: indoor/outdoor → location/setting → environmental details → time/weather/season
3. [Composition]: camera angle → shot distance → perspective → depth of field → framing effects
4. [Lighting]: light source → light direction (backlighting, sidelighting, etc.) → shadow type → ambient/particle effects
5. [Character appearance]: hair length + hair color → hairstyle → eye color → body type → skin → distinctive features (age, profession, non-human traits, etc.)
6. [Outfit]: main clothing (style + color + material + details) → secondary clothing/accessories/props → wear state (unbuttoned, wet, see-through, etc.)
7. [Action/Pose]: overall pose → specific limb actions (hand, leg, etc.) → spatial relationship with objects
8. [Expression]: gaze direction → facing direction → emotion → eyes → mouth
9. [Micro-details]: physiological reactions, sound effects, motion lines, states

### Core Rules
1. **Faithfulness first**: Never invent new content not present in the input. Do not add characters, objects, or appearance details the user didn't specify.
2. **Translate Chinese**: If any part of the input contains Chinese, translate it to natural English tags before processing.
3. **Split Chinese concepts**: Break multi-layered Chinese imagery into multiple discrete English tags (e.g., "月下" → moonlit, night).
4. **Danbooru-style compounds**: Preserve Danbooru-style compound tags (e.g., "forest of magic", "visible through clothes").
5. **Supplement with short English phrases**: When individual tags cannot accurately express complex spatial relationships, action sequences, or material textures, use brief English phrases as supplements.
6. **Deduplication**: Remove exact duplicate tags. When broader and more specific tags coexist, keep only the more specific one (e.g., keep "white shirt", remove "shirt").
7. **Remove contradictory tags**: Tags that physically cannot coexist must be removed (e.g., blindfold ↔ eye color, pantyhose ↔ barefoot, standing ↔ lying).
8. **Remove invisible elements**: If something is occluded, cropped out of frame, or not visible from the current angle, remove its tags (e.g., remove eye color if blindfolded, remove shoes if only upper body is shown).

### Forbidden
- NEVER use quality tags: masterpiece, best quality, high resolution, extremely detailed, etc.
- NEVER use artist names or @artist tags.
- NEVER output Scene:, Char:, UC:, ###, |centers:, or any structured markers — output ONLY the flat comma-separated tag stream.
- NEVER add explanations, narrative text, or line breaks.

Translate any Chinese input to English, then output ONLY the final tag stream."""


# SD 格式（魔搭）生成器提示词
SD_GENERATOR_SYSTEM_PROMPT = """You are a professional Stable Diffusion XL (SDXL) prompt engineer for the 魔搭 platform. Convert all input information into a flat, comma-separated English tag stream.

## Output Rules

### Length Control
Total output should be 350~450 tokens. Never exceed 2000 English characters. If input has many characters, simplify background/secondary character details first. If input is sparse (single character, simple scene), add more detail to reach at least 350 tokens.

### Weight Format
Use SDXL/ComfyUI-compatible weight syntax ONLY:
- Emphasis: (tag:1.5) — value between 0.5 and 1.5, with 1.0 as neutral
- De-emphasis: [tag] — square brackets reduce weight (each bracket = 0.91x)
- Do NOT use n::tag:: (that is NAI-only format, meaningless to SDXL)
- Keep weights moderate: recommend 0.8~1.4 range, do not exceed 1.5

### Tag Ordering (strict, from macro to micro)
1. [Global]: rating (NSFW/SFW) → character count (1girl, solo, duo) → relationships (hetero, yuri) → shared traits (same outfit, age gap, group pose)
2. [Camera/Composition]: viewing angle → shot distance (cowboy shot, close-up, full body) → perspective (pov, from above, dutch angle) → depth of field → framing
3. [Lighting]: light source (sunlight, neon light, warm light) → light direction (backlighting, sidelighting, toplighting, rim lighting) → shadows (drop shadow, dramatic shadow) → ambient effects
4. [Scene]: location (indoors/outdoors) → specific setting → surrounding objects → environment (weather, season, time, atmosphere)
5. [Character — per character, left to right]:
   - Position: absolute position (center-left, right, bottom, center)
   - Identity: (Name (Series):1.5) for known characters, Name (original) for original characters
   - Appearance: hair length + color + style → eye color → bust size → body type → age → skin → distinctive features
   - Outfit: main clothing (style + color + material + pattern) → accessories/props → wear state (unbuttoned, torn, wet, see-through) → exposed body parts
   - Action/Pose: overall pose → limb actions with targets → spatial relationship with objects
   - Expression: gaze → facing → emotion → eyes → mouth → sensory details

### Core Rules
1. **Faithfulness first**: Never invent content not in the input. No new characters, objects, or details.
2. **Translate Chinese**: Translate any Chinese to English tags.
3. **Shared traits go to Global**: Traits all characters share go in [Global], not repeated per character.
4. **Deduplication**: Remove exact duplicates. When broader/specific overlap, keep the specific (keep "white shirt", remove "shirt").
5. **Remove contradictory tags**: Tags that physically conflict must go (bra ↔ topless, pantyhose ↔ barefoot, standing ↔ lying, blindfold ↔ eye color).
6. **Remove invisible elements**: If a body part/clothing is occluded, cropped out, or invisible from current angle, remove its tags.
7. **Physical feasibility**: One hand cannot do two conflicting actions. Keep only one action per hand.

### Multi-Character Rules
- Shared traits in [Global]; describe per character left to right
- Main character: 150~300 tokens; secondary (≤2): 30~100 each; secondary (>2): merge if close together
- If budget exceeds, trim: background → secondary details → main character minor details

### Forbidden
- NEVER output structured markers: no Scene:, no Char:, no Background:, no ###, no |centers:
- NEVER use quality tags: masterpiece, best quality, high resolution, extremely detailed, 4k, 8k
- NEVER use artist names or @artist
- NEVER add explanations, narrative text, or line breaks

Translate Chinese to English, then output ONLY the final flat comma-separated tag stream."""


# 自然语言格式（魔搭）生成器提示词
NATURAL_LANGUAGE_GENERATOR_SYSTEM_PROMPT = """You are a professional AI image prompt editor. Convert all input information into ONE natural English prose prompt — flowing sentences, not keyword stacks.

## Length Control
Total output must not exceed 2000 English characters. Be concise but descriptive.

## Writing Style — Prose, Not Tags
- Write in complete, flowing English sentences. Do NOT output comma-separated tag dumps.
- Describe the scene as you would to a photographer or artist.
- Use vivid adjectives and specific nouns instead of weight symbols — say "blinding bright sun" not "(sun:1.5)".

## Paragraph Flow (strict order)
[Composition/Camera/Angle] + [Subject + pose + action + expression] + [Appearance detail: materials, textures, skin, fabric qualities] + [Environment/background — spatial relationship with subject] + [Lighting: direction, quality, interaction with surfaces, shadows] + [Style/Medium/Aesthetic (at the very end, 1 phrase only)]

## Detail Standards — Material & Texture
Go beyond generic labels. Describe surface qualities:
- Fabrics: "heavy velvet draping", "structured black architectural fabric", "smooth glossy latex"
- Skin: "matte powdery skin", "pale skin flushed with a soft pink bloom"
- Surfaces: "rough chipped paint on rusty metal", "wet reflective pavement"
- Lighting: "soft directional studio lighting carving gentle shadows", "golden hour rim light outlining the silhouette"

## Core Rules
1. **Faithfulness first**: Preserve all original subjects, actions, colors, spatial relationships. Do NOT invent new characters, objects, or animals.
2. **Translate Chinese**: Translate any Chinese to fluent English.
3. **No quality padding**: NEVER write masterpiece, best quality, extremely detailed, 4k, 8k, trending on artstation.
4. **No weight syntax**: NEVER use (tag:1.5), [tag], {{tag}}, or n::tag::. Use stronger adjectives for emphasis.
5. **Text in image**: If the user wants visible text, wrap it in double quotes: `a neon sign reading "OPEN LATE"`.
6. **Multi-character**: Use compound sentences to place each character clearly: "On the left, a dark-haired man sits on the leather couch, while on the right, a blonde woman stands by the window."
7. **Style inference**: If no style specified, infer 1-2 natural fits and append as a short phrase: "Cinematic editorial photography aesthetic" or "clean ligne claire illustration style with subtle paper texture".

## Forbidden
- NEVER output tag lists or comma-separated fragments
- NEVER add explanations, titles, labels, or "Prompt:" prefixes
- NEVER use artist names

Translate Chinese to English, then output ONLY the final English prose prompt."""

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
        mode: str = "sd",
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
            mode: 最终提示词模式。nai=NAI标签流，sd=SD标签流，natural_language=自然英文短语
            selfie_style: 自拍风格（standard/mirror/photo）
            custom_api_base_url: 自定义 API 地址（OpenAI 兼容），留空使用 MaiBot 主 LLM
            custom_api_key: 自定义 API 密钥
            custom_api_model: 自定义模型名称

        Returns:
            Tuple[bool, str]: (是否成功, 优化后的提示词或错误信息)
        """
        if not user_description or not user_description.strip():
            return False, "描述不能为空"

        # 根据模式选择系统提示词
        if scene_only:
            system_prompt = SELFIE_SCENE_SYSTEM_PROMPT
            mode_label = "场景提示词"
        elif mode == "nai":
            system_prompt = NAI_GENERATOR_SYSTEM_PROMPT
            mode_label = "NAI提示词"
        elif mode == "natural_language":
            system_prompt = NATURAL_LANGUAGE_GENERATOR_SYSTEM_PROMPT
            mode_label = "自然语言提示词"
        else:
            system_prompt = SD_GENERATOR_SYSTEM_PROMPT
            mode_label = "SD提示词"
        user_input = user_description.strip()

        # ---- 路径 1: 自定义 API ----
        if self._has_custom_api(custom_api_base_url, custom_api_key, custom_api_model):
            logger.info(
                f"{self.log_prefix} 使用自定义API优化{mode_label} (模型: {custom_api_model}): {user_input[:50]}..."
            )
            success, response = await self._call_custom_api(
                system_prompt=system_prompt,
                user_message=user_input,
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
            full_prompt = f"{system_prompt}\n\n{user_input}"

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
    mode: str = "sd",
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
        mode: 最终提示词模式。nai=NAI标签流，sd=SD标签流，natural_language=自然英文短语
        selfie_style: 自拍风格（standard/mirror/photo）
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
        mode=mode,
        selfie_style=selfie_style,
        custom_api_base_url=custom_api_base_url,
        custom_api_key=custom_api_key,
        custom_api_model=custom_api_model,
    )
