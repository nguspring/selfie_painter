# 🎨 画家麦麦的自拍日常 (selfie_painter)

<p align="center">
  <strong>集智能绘画与自拍生成于一体的 MaiBot 插件</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/版本-v3.6.3-blue" alt="Version">
  <img src="https://img.shields.io/badge/MaiBot-0.10.x+-green" alt="MaiBot">
  <img src="https://img.shields.io/badge/License-AGPL--3.0-orange" alt="License">
</p>

---

> 🚀 **从 v3.5.x 升级到 v3.6.3？** 请先阅读下方 [升级指南](#-从-v35x-升级到-v363)。

> ✨ **v3.6.3 修复**：梦羽 AI 自拍在衣柜系统选中中文穿搭时，会先转换为英文提示词再注入自拍 prompt，避免中文服装标签直接进入 SD 提示词导致的出图失败。

---

> **📌 关于本仓库**
>
> 本仓库是 nguspring 维护的**改版**画图插件，发展脉络如下：
>
> 1. 最初基于原版 [custom_pic_plugin](https://github.com/1021143806/custom_pic_plugin) 修改，发布为 `selfie_painter`（v3.4.x ~ v3.5.x）
> 2. 原作者后来将 custom_pic_plugin 升级重构为 [mais-art-journal](https://github.com/1021143806/mais-art-journal)（v3.4.0）
> 3. 本仓库基于 mais-art-journal 重新合并重构，发布为 `selfie_painter_v2`（v3.6.3）
>
> | 项目 | 链接 |
> |------|------|
> | 原版仓库（已更名） | [custom_pic_plugin](https://github.com/1021143806/custom_pic_plugin) → [mais-art-journal](https://github.com/1021143806/mais-art-journal) |
> | 本仓库（改版） | https://github.com/nguspring/selfie_painter |
> | 当前版本 | v3.6.3 |
>
> **改版定位**：在上游画图能力的基础上，增加**内置日程系统**、**衣柜系统**、**日程注入系统**、**SSE 流式响应**等增强功能，让 Bot 更像真人。

---

## 🔄 从 v3.5.x 升级到 v3.6.3

v3.6.3 延续 v3.6.x 的插件结构与配置格式；若你是从 v3.5.x 直接升级，仍需按下述方式重新安装。

**请删除旧版插件目录后重新安装：**

```shell
cd MaiBot/plugins
# 1. 删除旧版目录（如有需要请先手动备份 config.toml）
rm -rf selfie_painter
# 2. 重新安装
git clone https://github.com/nguspring/selfie_painter.git -b dev
```

重启 MaiBot 后会自动生成默认 `config.toml`，按 [新手快速配置指南](#-新手快速配置指南) 配置即可。

> ⚠️ 旧版 `config.toml` 的配置项名称和结构已大幅变动，无法直接复用。建议参考旧配置手动填写新配置中对应的 API 密钥和模型信息。
---

## ⚠️ 已知问题

| 问题 | 状态 | 说明 |
|------|------|------|
| grok2api 通过 `openai-chat` 接口生图不稳定 | 🔧 修复中 | 部分 grok2api 实例可以正常生图，部分不行。正在尽力排查兼容性问题 |

---

## 💡 插件定位

**画家麦麦的自拍日常** = 🎨 **画图功能** + 📸 **自拍功能** + 📅 **日程系统** + 👗 **衣柜系统**

| 功能 | 描述 |
|------|------|
| 🎨 **画图** | 支持文生图/图生图智能识别，兼容 OpenAI、豆包、Gemini、魔搭、ComfyUI 等 10 种 API 格式 |
| 📸 **自拍** | 三种自拍模式（standard/mirror/photo），LLM 生成风格感知的手部动作，支持参考图图生图 |
| 📅 **日程** | 内置日程管理，LLM 生成每日日程，回复自动注入当前活动，不再依赖外部插件 |
| 👗 **衣柜** | 根据日程活动自动换装，支持管理员手动设置临时穿搭 |

## ✨ 主要特性

### 🎯 智能图片生成
- **自动模式识别**：智能判断文生图或图生图模式
- **自拍模式**：支持 standard（前置自拍）/ mirror（对镜自拍）/ photo（第三人称照片）三种风格
- **提示词优化**：自动将中文描述优化为专业英文 SD 提示词
- **结果缓存**：相同参数复用之前的结果
- **自动撤回**：可按模型配置延时撤回

### 🛠️ 多 API 格式支持

| format | 平台 | 说明 |
|--------|------|------|
| `openai` | OpenAI / 硅基流动 / Grok / NewAPI 等 | 通用 `/images/generations` 接口 |
| `openai-chat` | 支持生图的 Chat 模型 | 通过 `/chat/completions` 生图，支持 SSE 流式响应 |
| `doubao` | 豆包（火山引擎） | 使用 Ark SDK |
| `gemini` | Google Gemini | 原生 `generateContent` 接口 |
| `modelscope` | 魔搭社区 | 异步任务模式，自动轮询结果 |
| `shatangyun` | 砂糖云 (NovelAI) | GET 请求 |
| `mengyuai` | 梦羽 AI | 不支持图生图 |
| `zai` | Zai (Gemini 转发) | OpenAI 兼容 |
| `comfyui` | 本地 ComfyUI | 加载工作流 JSON，替换占位符，轮询结果 |

### 🎨 /dr 命令系统

#### 图片生成

| 命令 | 说明 |
|------|------|
| `/dr <风格名>` | 对最近的图片应用预设风格（图生图） |
| `/dr <描述>` | 自然语言生成图片（自动判断文/图生图） |
| `/dr 用model2画一只猫` | 指定模型生成 |

#### 风格管理

| 命令 | 说明 |
|------|------|
| `/dr styles` | 列出所有可用风格 |
| `/dr style <名>` | 查看风格详情 |
| `/dr help` | 帮助信息 |

#### 配置管理（需管理员权限）

| 命令 | 说明 |
|------|------|
| `/dr list` | 列出所有模型 |
| `/dr config` | 显示当前聊天流配置 |
| `/dr set <模型ID>` | 设置 /dr 命令使用的模型 |
| `/dr default <模型ID>` | 设置 Action 组件默认模型 |
| `/dr model on\|off <模型ID>` | 开关指定模型 |
| `/dr recall on\|off <模型ID>` | 开关指定模型的撤回 |
| `/dr on` / `/dr off` | 开关插件（当前聊天流） |
| `/dr selfie on\|off` | 开关自拍日程增强（当前聊天流） |
| `/dr selfie standard\|mirror\|photo` | 切换自拍风格（当前聊天流） |
| `/dr reset` | 重置当前聊天流的所有运行时配置 |
| `/dr refresh <角色名>` | 刷新角色参考图（搜索 + 下载 + VLM 提取特征） |
| `/dr status <角色名>` | 查看角色参考图状态 |
| `/dr clear <角色名>` | 清除角色参考缓存 |

#### 衣柜命令

| 命令 | 说明 |
|------|------|
| `/dr wardrobe list` | 列出穿搭列表（仅自拍生效） |
| `/dr wardrobe status` | 查看当前穿搭状态（含临时穿搭） |
| `/dr wardrobe wear <衣服>` | 设置今日临时穿搭（需管理员，次日自动重置） |
| `/dr wardrobe help` | 显示衣柜帮助信息 |
| `/dr 衣柜 ...` | 衣柜命令的中文别名 |

#### 日程命令

| 命令 | 说明 |
|------|------|
| `/schedule` | 查看今日日程 |
| `/schedule regen` | 用 LLM 重新生成今日日程 |

> 运行时配置（模型切换、开关等）仅保存在内存中，重启后恢复为 config.toml 的全局设置。

### 📅 内置日程系统

插件自带日程管理，不再依赖外部 `autonomous_planning` 插件。

- 每日自动通过 LLM 生成当天日程（可配置生成时间和模型）
- LLM 不可用时自动使用工作日/周末兜底模板
- 日程数据存储在本地 SQLite 数据库（`data/schedule.db`）
- 在 LLM 生成聊天回复前自动注入麦麦当前活动信息
- 支持 smart（按时间/消息数节流）和 always 两种注入模式

### 👗 衣柜系统

让麦麦的自拍可以根据日程活动自动切换服装。

- 中文穿搭词会优先映射或翻译成英文提示词后再注入自拍 prompt，提升梦羽 AI 等基于 SD 的接口兼容性。

**穿搭优先级**（从高到低）：
1. 临时穿搭 — `/dr wardrobe wear` 设置（当天有效）
2. 场景匹配 — `custom_scenes` 规则匹配当前日程活动
3. 日程 outfit — 日程生成时确定的穿搭
4. 每日随机 — 从 `daily_outfits` 随机选（同一天固定）

### ⏰ 自动自拍

定时生成自拍图片并发布到 QQ 空间说说（需配合 [Maizone](https://github.com/Rabbit-Jia-Er/Maizone) 插件）。

- 可配置间隔（默认 2 小时）
- 安静时段控制（默认 00:00-07:00 不发）
- LLM 根据日程活动描述生成风格感知的英文 SD 场景标签
- 支持参考图片进行图生图自拍
- 连续失败指数退避，重启后自动恢复上次自拍时间

---

## 🆕 新手快速配置指南

> 如果你是第一次使用这个插件，请按照下面的步骤操作，5 分钟让麦麦学会画画！

### 第一步：安装插件

```shell
cd MaiBot/plugins
git clone https://github.com/nguspring/selfie_painter.git -b dev
```

### 第二步：获取 API 密钥

| 平台 | 价格 | 推荐理由 |
|------|------|----------|
| **魔搭社区** | 免费 | 完全免费，适合新手体验 |
| **硅基流动** | 便宜 | 新用户送额度，速度快 |
| **豆包** | 便宜 | 字节跳动出品，质量不错 |
| **本地 ComfyUI** | 免费 | 需要有显卡，完全本地运行 |

**魔搭社区获取密钥步骤**：
1. 打开 https://modelscope.cn/
2. 注册/登录账号
3. 进入「我的 → API-KEY管理」
4. 创建新的 API Key

### 第三步：修改配置文件

重启 MaiBot 后，插件会自动生成 `config.toml` 文件。打开它，配置你的模型：

```toml
[plugin]
enabled = true

[models.model1]
name = "魔搭免费模型"
base_url = "https://api-inference.modelscope.cn/v1"
api_key = "Bearer 你的密钥"
format = "modelscope"
model = "cancel13/liaocao"
```

### 第四步：测试

重启 MaiBot，然后在群里发送：

```
麦麦，画一只可爱的小猫
```

如果麦麦回复了一张图片，恭喜你，配置成功了！🎉

---

## 📖 专业术语通俗解释

| 术语 | 通俗解释 | 推荐值 |
|------|----------|--------|
| **seed（随机种子）** | `-1` 每次不同，固定值可复现 | `-1` |
| **guidance_scale（引导强度）** | 值越高越"听话"，太高会生硬 | `2.5-7.5` |
| **num_inference_steps（推理步数）** | 步数越多越精细，但更慢 | `20-50` |
| **negative_prompt（负面提示词）** | 告诉 AI "不要画什么" | `lowres, bad anatomy, text` |

---

## ⚙️ 配置说明

配置文件: `config.toml`，首次启动自动生成。版本更新时自动备份到 `old/` 目录。

### 基础设置

```toml
[plugin]
enabled = true

[generation]
default_model = "model1"          # Action 组件默认使用的模型 ID

[components]
enable_unified_generation = true  # 启用智能生图 Action
enable_pic_command = true         # 启用 /dr 图片生成命令
enable_pic_config = true          # 启用 /dr 配置管理命令
enable_pic_style = true           # 启用 /dr 风格管理命令
pic_command_model = "model1"      # /dr 命令默认模型
admin_users = ["12345"]           # 管理员 QQ 号列表（字符串格式）
max_retries = 2                   # API 失败重试次数
enable_debug_info = false         # 显示调试信息
enable_verbose_debug = false      # 打印完整请求/响应报文
```

### 模型配置

```toml
[models.model1]
name = "我的模型"
base_url = "https://api.siliconflow.cn/v1"
api_key = "Bearer sk-xxx"
format = "openai"                          # 见上文"多 API 格式支持"
model = "Kwai-Kolors/Kolors"
fixed_size_enabled = false
default_size = "1024x1024"
seed = -1
guidance_scale = 2.5
num_inference_steps = 20
custom_prompt_add = ", best quality"       # 追加正面提示词
negative_prompt_add = "lowres, bad anatomy" # 追加负面提示词
support_img2img = true
auto_recall_delay = 0                      # 自动撤回延时（秒），0=不撤回
```

### 自拍配置

```toml
[selfie]
enabled = true
reference_image_path = ""         # 参考图路径（留空=纯文生图）
prompt_prefix = "blue hair, red eyes, 1girl"  # Bot 外观描述
negative_prompt = ""
schedule_enabled = true           # 日程增强
default_style = "standard"        # standard / mirror / photo
```

### 衣柜配置

```toml
[wardrobe]
enabled = false
daily_outfits = ["哥特洛丽塔", "宽松休闲装", "黑丝JK"]
auto_scene_change = true
custom_scenes = ["睡觉的时候穿可爱睡衣", "运动的时候穿运动服"]
```

### 自动自拍配置

```toml
[auto_selfie]
enabled = false
interval_minutes = 120
selfie_model = "model1"
quiet_hours_start = "00:00"
quiet_hours_end = "07:00"
caption_enabled = true
```

### 日程配置

```toml
[schedule]
schedule_identity = ""           # 身份补充
schedule_interest = ""           # 兴趣爱好
schedule_lifestyle = ""          # 生活规律
schedule_history_days = 1        # 历史参考天数
schedule_custom_prompt = ""      # 日程风格要求
schedule_multi_round = true      # 启用多轮优化
schedule_max_rounds = 2
schedule_quality_threshold = 0.8

[schedule_inject]
schedule_intent_enable = true    # 启用意图识别
schedule_context_cache_ttl_minutes = 30
schedule_context_cache_max_turns = 10
```

### 风格配置

```toml
[styles]
cartoon = "cartoon style, anime style, colorful, vibrant colors"
watercolor = "watercolor painting style, soft colors, artistic"

[style_aliases]
cartoon = "卡通,动漫"
watercolor = "水彩"
```

### ComfyUI 配置

```toml
[models.comfyui]
name = "ComfyUI-本地"
base_url = "http://127.0.0.1:8188"
api_key = ""
format = "comfyui"
model = "my_workflow.json"       # 工作流文件（相对 workflow/ 目录）
fixed_size_enabled = true
default_size = "1024x1024"
seed = -1
guidance_scale = 8
num_inference_steps = 30
```

**工作流占位符**：在 API 格式 JSON 中使用 `"${prompt}"`、`"${seed}"`、`"${negative_prompt}"`、`"${steps}"`、`"${cfg}"`、`"${width}"`、`"${height}"`、`"${denoise}"`、`"${image}"` 等占位符。

---

## 常见平台配置速查

| 平台 | base_url | format |
|------|----------|--------|
| 魔搭社区 | `https://api-inference.modelscope.cn/v1` | `modelscope` |
| 硅基流动 | `https://api.siliconflow.cn/v1` | `openai` |
| 豆包 | `https://ark.cn-beijing.volces.com/api/v3` | `doubao` |
| OpenAI | `https://api.openai.com/v1` | `openai` |
| 本地 ComfyUI | `http://127.0.0.1:8188` | `comfyui` |

## 魔搭链接及教程

1. 注册一个[魔搭](https://modelscope.cn/)账号
2. 根据[官网阿里云绑定教程](https://modelscope.cn/docs/accounts/aliyun-binding-and-authorization)完成认证
3. 到主页申请 API key，参考[API推理介绍](https://modelscope.cn/docs/model-service/API-Inference/intro)
4. 去[模型库](https://modelscope.cn/models)挑选生图模型，取模型名称
5. 在 `config.toml` 中填入 key 和模型名称

---

## 🔧 依赖说明

- Python 3.12+
- MaiBot 插件系统 0.10.x+
- 火山方舟 SDK：`pip install 'volcengine-python-sdk[ark]'`（使用豆包时）
- 可选依赖：`pip install aiohttp beautifulsoup4`（搜图功能）

---

## 💡 使用示例

### 自然语言生图
```
用户：麦麦，画一张美少女
麦麦：[生成图片]

用户：[发送图片] 麦麦，把背景换成海滩
麦麦：[图生图生成]
```

### 自拍模式
```
用户：麦麦，来张自拍！
麦麦：[生成角色自拍照片]
```

### 命令式风格转换
```
用户：[发送图片]
用户：/dr cartoon
麦麦：[应用卡通风格]
```

---

## ⚠️ 注意事项

- 请妥善保管 API 密钥，不要在公开场合泄露
- 各平台 API 可能有调用频率限制，请注意控制使用频率
- 模型是否支持图生图请参考各平台官方文档
- 生成的图片内容受模型和提示词影响，请遵守相关平台的使用规范

## 常见问题

- **API 密钥未配置/错误**：请检查 `config.toml` 中对应模型的 `api_key` 配置
- **图片尺寸无效**：支持如 `1024x1024`，宽高范围 100~10000
- **依赖缺失**：请确保 MaiBot 插件系统相关依赖已安装
- **API 错误码**：400=参数错误 / 401=Key 错误 / 403=权限不足 / 429=频率限制 / 503/504=服务高负载

---

## 🙏 致谢

感谢以下开发者为本插件做出的贡献：

- **原作者**：1021143806 (Ptrel) — 创建了原版 custom_pic_plugin 插件（现 mais-art-journal）
- **Rabbit-Jia-Er** — 添加了多模型调用和命令功能
- **saberlights Kiuon** — 添加了自拍功能和自然语言命令功能
- **A-Dawn** — 感谢对代码问题排查提供的思路，以及 A_MIND 插件带来的灵感启发；感谢提供反重力反代 gemini-3-pro-image 无法使用问题的热修复补丁
- **XXXxx7258** — 感谢 Mai_Only_You 插件带来的灵感启发
- **xuqian13** — 内置日程系统基于 [autonomous_planning_plugin](https://github.com/xuqian13/autonomous_planning_plugin) 的设计思路

本插件搜图功能部分代码来自于 https://github.com/XXXxx7258/google_search_plugin

**特别感谢**：感谢我的小乐作为首席体验官在线试毒:)

---

## 📝 更新日志

### v3.6.2 (改版) — 2026-03-16

- 🔧 修复自拍风格值在不同链路中的标准化问题，避免异常值静默回退到 `standard`
- 🔧 新增后台日志完整提示词开关，便于排查本次生图实际使用的提示词
- 🔧 修复晚间补启动首次自拍时活动回退错误：未命中区间时按当前时刻选择最近已开始活动，避免误回退到早晨时段
- 📝 统一插件元数据、配置版本与文档版本号到 3.6.2

### v3.6.0 (改版) — 2026-03-07

**🌟 大版本重构：合并上游 mais-art-journal + 多项新功能**

本版本基于上游 [mais-art-journal](https://github.com/1021143806/mais-art-journal) 进行合并重构，同时引入大量改版独有的新功能。

#### 合并自上游 mais-art-journal

以下功能来自原作者的 mais-art-journal，本版本合并并适配：

- 🔧 **API 客户端模块化**：`core/api_clients/` 引入 `BaseApiClient` 基类，每个 API 格式独立文件
- 🔧 **自拍系统模块化**：`core/selfie/` 目录，提示词常量、场景动作生成器独立管理
- 🆕 **ComfyUI 支持**：新增 `comfyui` 格式，支持本地/远程 ComfyUI 工作流 JSON 加载和占位符替换
- 🆕 **photo 自拍模式**：新增第三人称照片模式，与 standard/mirror 并列
- 🔧 角色参考图命令（`/dr refresh`、`/dr status`、`/dr clear`）

#### 改版新增功能（nguspring）

以下功能为本改版独有，不存在于上游：

- 🆕 **内置日程系统**：完整的日程管理模块（`core/schedule/`，含 LLM 生成器、人设构建器、质量评估器、SQLite 持久化、兜底模板等 10 个文件）
- 🆕 **日程人设驱动**：日程生成读取麦麦人设配置（性格、兴趣、生活规律）
- 🆕 **日程历史记忆**：参考昨天日程，让日程有连续性
- 🆕 **日程质量评分**：多轮生成优化，质量不达标自动重试
- 🆕 **日程智能注入**：意图识别 + 对话上下文缓存，避免不相关场景注入（`core/inject/`，5 个文件）
- 🆕 **衣柜系统**：`[wardrobe]` 配置，每日随机穿搭、场景自动换装、管理员临时穿搭（`core/wardrobe/`）
- 🆕 **SSE 流式响应**：`openai-chat` 格式支持 SSE 流式解析，兼容 grok2api 等强制流式服务
- 🆕 **衣柜命令**：`/dr wardrobe list/status/wear/help`，中文别名 `/dr 衣柜`
- 🆕 **日程命令**：`/schedule`、`/schedule regen`
- 🆕 **代理配置**：新增 `[proxy]` 配置段
- 🆕 **提示词优化器自定义 API**：支持 `custom_api_base_url`、`custom_api_key`、`custom_model` 配置
- 🆕 **自动自拍目标群/用户**：`send_to_chat` 配置 `target_groups`/`target_users`（替代旧版 `chat_id_list`）

#### 其他改进

- 🔧 **自拍三模式提示词修复**：修复 standard/mirror/photo 提示词冲突
- 🔧 **衣柜持久化**：临时穿搭存储到 `schedule.db`，重启不丢失
- 🔧 **许可证信息统一**：当前发布材料统一为 AGPL-3.0
- 🔧 **工具函数整理**：`core/utils/` 目录，共享常量和工具函数

#### ⚠️ 破坏性变更

- ⚠️ 代码结构大幅重构，直接替换旧版文件可能不兼容
- ⚠️ 部分旧配置项已移除或重命名，请删除旧版后重新安装（详见 [升级指南](#-从-v35x-升级到-v360)）

---

<details>
<summary>📜 v3.5.x 历史更新日志（点击展开）</summary>

### v3.5.2 (修改版) — 2026-02-01

- 🐛 修复日程生成 `parse_failed`：使用 `JSONDecoder.raw_decode` 提取完整 JSON 数组
- ✅ 日程生成 fallback 时必落"失败包"
- ✅ 人设变更触发当日日程自动重生成（基于签名）
- ✅ 跨天去重：保留最近 N 天日程文件并回灌摘要到 prompt
- ✅ fallback 模板升级为多套（base+variant）
- ✅ 变体闭环：生成图像使用 `SceneVariation`
- ✅ 配文贴图：图片生成后做 VLM 视觉摘要注入配文
- ✅ 叙事连贯：发送成功后更新 `DailyNarrativeState`

### v3.5.1 (修改版) — 2026-01-25

- 🐛 修复回退日程错位：改为按时间接近度智能匹配

### v3.5.0 (修改版) — 2026-01-24

- 🌟 智能日程模式 (Smart Mode)
- 📝 配文多样化（5种类型）
- 🎭 人设注入功能
- 🎲 间隔补充发送
- 🆕 OpenAI-Chat 格式支持
- 🆕 手动自拍读取日程
- 🔧 代码架构精简（移除约 800 行冗余代码）

</details>

<details>
<summary>📜 v3.4.x 及更早历史（点击展开）</summary>

### v3.4.1 (修改版)
- 🆕 定时自拍黑白名单
- 🆕 定时自拍持久化
- 🆕 多时间点自拍

### v3.4.0
- ⏰ 定时自拍功能正式版
- 🔍 内置搜图引擎
- 🎨 7个魔搭模型预设

### v3.3.x
- 砂糖云/梦羽 AI/Zai 格式支持
- 提示词优化器
- 自动撤回
- 聊天流独立配置

### v3.2.0
- 自拍模式
- 自然语言命令
- Gemini 尺寸配置

### v3.1.x
- 多模型配置
- 缓存机制
- 命令式配置管理
- 风格别名系统

</details>

---

## 🤝 基于 MaiBot 项目

- 支持 0.10.x+（目前改为一直支持最新版）
- MaiBot 项目地址：https://github.com/MaiM-with-u/MaiBot

## 插件开发历程

1. 最初基于 MaiBot 早期官方豆包生图示例插件修改而来
2. MaiBot 0.8 版本更新，根据新插件系统进行重构
3. Rabbit-Jia-Er 加入，添加多模型调用和命令功能
4. saberlights Kiuon 加入，添加自拍功能和自然语言命令功能
5. 原作者将 custom_pic_plugin 升级为 [mais-art-journal](https://github.com/1021143806/mais-art-journal)
6. nguspring 加入，基于原版开发修改版 selfie_painter（v3.4.x ~ v3.5.x）：日程系统重大升级（人设驱动、历史记忆、多轮生成、智能注入）
7. v3.6.2：基于 mais-art-journal 合并重构为 selfie_painter_v2，并持续修复自拍与提示词相关问题

## 🔗 版权信息

- 作者：nguspring
- 许可证：AGPL-3.0
- 项目主页：https://github.com/nguspring/selfie_painter

## 贡献和反馈

欢迎提交 Issue 和 Pull Request！

联系 QQ：1021143806，3082618311
