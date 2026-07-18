# 提示词优化器 v3 设计进度

> 状态：设计完成，全部决策已确认
> 日期：2026-07-16

---

## 一、背景

`selfie_painter_v2` 的提示词优化器基于 SillyTavern 世界书 `(主体)文生图5.26[3].json` 设计。现在世界书更新到了 `(主体)文生图7.16[3].json`，需要同步升级，并支持三种模式。

**参考文件：**
- 新世界书（NAI）：`E:\Download\- (主体)文生图7.16[3].json`
- 旧世界书（SD）：`E:\Download\- (主体)文生图5.26[3] .json`
- 当前优化器：`plugins/selfie_painter_v2/core/utils/prompt_optimizer.py`
- 当前模式定义：`plugins/selfie_painter_v2/core/utils/optimizer_mode.py`
- API客户端映射：`plugins/selfie_painter_v2/core/api_clients/__init__.py`

## 二、目标

将提示词优化器从旧的两种模式（sd / natural_language）升级为三种模式：

1. **NAI格式** — 对标 7.16 世界书，平铺 tag 流输出，上限 512 tokens
2. **SD格式（魔搭）** — 对标 5.26/7.16 世界书 SD 规则，平铺 tag 流输出，上限 2000 英文字符
3. **自然语言格式（魔搭）** — 通用自然语言描述，上限 2000 英文字符

## 三、已确认的设计决策

### 3.1 整体方案：方案 A（纯净 System Prompt 驱动）
- 三个模式各对应一个精心设计的 system prompt
- 所有输入信息（用户描述 + 角色外观 + 服装 + 场景）拼成 user message
- LLM 按 system prompt 规则自行生成最终 prompt
- **输入来源**：所有信息（用户原始描述 + prompt_builder 拼好的角色/服装/场景等）
- **生成逻辑**：生成器模式，忠于原始描述，不编造内容

### 3.2 输出格式
- **平铺 tag 流**（不用 Scene/Char/坐标结构化标记）
- **负向提示词**：优化器不生成，由模型配置 `negative_prompt_add` 负责

### 3.3 长度控制
- NAI：上限 512 tokens，system prompt 告知 LLM 自行控制
- SD（魔搭）：上限 2000 英文字符，system prompt 告知 LLM 自行控制
- 自然语言（魔搭）：上限 2000 英文字符，system prompt 告知 LLM 自行控制

### 3.4 代码改动范围
| 文件 | 改动 |
|---|---|
| `core/utils/optimizer_mode.py` | 模式枚举从 `("sd", "natural_language")` 扩为 `("nai", "sd", "natural_language")` |
| `core/utils/prompt_optimizer.py` | 废弃旧的 `OPTIMIZER_SYSTEM_PROMPT`、`SD_NORMALIZER_SYSTEM_PROMPT`、`NATURAL_LANGUAGE_SYSTEM_PROMPT`，替换为三个新生成器 prompt；更新 `optimize()` 方法的 mode 分发逻辑 |
| `core/prompt_optimizer.py` | 兼容入口，无需改动 |
| `plugin_meta.py` / `config.toml` | 可能需要调整默认 mode |

### 3.5 API 层影响
- `tuercha_nai_client.py`（对应 NAI）：已支持 `prompt` + `negative_prompt`，512 token 限制由优化器控制
- `modelscope_client.py`（对应 SD/自然语言）：已支持 `prompt` + `negative_prompt`，2000 字符限制由优化器控制
- 无需新增 API 客户端

---

## 四、三份 System Prompt 终稿

### 4.1 NAI 格式

```
You are a professional NovelAI (NAI) prompt engineer. Convert all input information into a flat, comma-separated English tag stream suitable for direct use with NAI image generation.

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

Translate any Chinese input to English, then output ONLY the final tag stream.
```

### 4.2 SD 格式（魔搭）

```
You are a professional Stable Diffusion XL (SDXL) prompt engineer for the 魔搭 platform. Convert all input information into a flat, comma-separated English tag stream.

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
   - Identity: (1.5::Name (Series):) for known characters, Name (original) for original characters
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

Translate Chinese to English, then output ONLY the final flat comma-separated tag stream.
```

### 4.3 自然语言格式（魔搭）

```
You are a professional AI image prompt editor. Convert all input information into ONE natural English prose prompt — flowing sentences, not keyword stacks.

## Length Control
Total output must not exceed 2000 English characters. Be concise but descriptive.

## Writing Style — Prose, Not Tags
- Write in complete, flowing English sentences. Do NOT output comma-separated tag dumps.
- Describe the scene as you would to a photographer or artist.
- Use vivid adjectives and specific nouns instead of weight symbols — say "blinding bright sun" not "(sun:1.5)".

## Paragraph Flow (strict order)
```
[Composition/Camera/Angle]
+ [Subject + pose + action + expression]
+ [Appearance detail: materials, textures, skin, fabric qualities]
+ [Environment/background — spatial relationship with subject]
+ [Lighting: direction, quality, interaction with surfaces, shadows]
+ [Style/Medium/Aesthetic (at the very end, 1 phrase only)]
```

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

Translate Chinese to English, then output ONLY the final English prose prompt.
```

---

## 五、后续确认的决策

### 5.1 prompt_builder 对接方式
- **调用方不动**：pic_action.py 的 `_process_selfie_prompt()` 继续把角色外观、穿搭、场景、用户描述拼成逗号 tag 串传给优化器；pic_command.py 继续把用户原始文本传给优化器。
- 优化器作为"生成器"，接收这些拼接好的 tag 串/原始文本，由 system prompt 引导 LLM 重新整理生成。

### 5.2 全局默认 mode
- 默认仍为 `"sd"`。

### 5.3 默认模型配置

| 模型 | 分辨率 | 模式 | 采样器 | 步数 | CFG | 默认正面 | 默认负面 |
|---|---|---|---|---|---|---|---|
| Krea-2-Turbo | 1024x1024（固定） | natural_language | Euler | 8 | 1 | — | — |
| Z-Image-Turbo | 1024x1024（固定） | natural_language | Euler | 12 | 1 | — | — |
| WAI-illustrious-SDXL-v17 | 1024x1024（固定） | sd | Euler a | 30 | 6 | masterpiece, best quality, newest, highres, aesthetic | worst quality, low quality, bad hands, mutated hands, blurry, lowres |
| ChenkinNoob-XL-V0.5 | 1024x1024（固定） | sd | Euler a | 30 | 6 | masterpiece, best quality, newest, highres, aesthetic | worst quality, low quality, bad hands, mutated hands, blurry, lowres |
| MiaoMiao RealSkin EPS-v1.3 | 1024x1024（固定） | sd | Euler a | 30 | 6 | masterpiece,very aesthetic,best quality,absurdres,newest,highres,ultra detailed, anime coloring,depth of field,pale_skin | lowres,(bad),bad hands,limb asymmetry,bad feet,text,error,fewer,extra,missing,worst quality,jpeg artifacts,low quality,watermark,unfinished,displeasing,oldest,early,chromatic aberration,signature,simple_background,artistic error,username,scan,[abstract],english text,shiny_skin |
| MiaoMiao Harem v1.9 | 1024x1024（固定） | sd | Euler a | 30 | 6 | masterpiece, best quality, absurdres, newest, very aesthetic, amazing quality,highres,sensitive,complex background, highres, ultra detailed, best anatomy, HDR, 8K, high detail RAW color art, high contrast, depth of field | lowres,(bad),limb asymmetry,bad feet,text,error,fewer,extra,missing,worst quality,jpeg artifacts,low quality,watermark,unfinished,displeasing,oldest,early,chromatic aberration,signature,simple_background,artistic error,username,scan,[abstract],english text,shiny_skin |

> 分辨率统一 **1024×1024**。

> 魔搭文生图请求会把配置的 `sampler` 作为公开 API 的顶层字段发送；该字段来自魔搭 AIGC 网页的采样器名称。魔搭官方 API-Inference 参数表尚未列出它，因此服务端接受情况必须以实际响应为准。图生图请求不发送该字段。

## 六、设计已确认，进入实施阶段
