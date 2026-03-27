# pyright: reportIncompatibleVariableOverride=false
# pyright: reportIncompatibleMethodOverride=false
# pyright: reportMissingImports=false
# pyright: reportMissingTypeArgument=false

from typing import List, Tuple, Type, Dict, Any, Optional
import asyncio
import os

from src.common.logger import get_logger
from src.plugin_system.base.base_plugin import BasePlugin
from src.plugin_system.base.component_types import ComponentInfo, PythonDependency
from src.plugin_system import register_plugin
from src.plugin_system.base.config_types import (
    ConfigField,
    ConfigSection,
    ConfigLayout,
    ConfigTab,
)

from .core.pic_action import SelfiePainterAction
from .core.pic_command import PicGenerationCommand, PicConfigCommand, PicStyleCommand
from .core.wardrobe_command import WardrobeCommand
from .core.schedule_inject_handler import ScheduleInjectHandler
from .core.schedule_command import ScheduleCommand

try:
    import tomllib
except ModuleNotFoundError:
    tomllib = None

if tomllib is not None:
    _TOMLDecodeError = tomllib.TOMLDecodeError
else:
    _TOMLDecodeError = ValueError

logger = get_logger("selfie_painter_v2")


@register_plugin
class SelfiePainterV2Plugin(BasePlugin):
    """麦麦绘卷 v2 (selfie_painter_v2) - 智能多模型图片生成插件，支持文生图和图生图"""

    # 插件基本信息
    plugin_name = "selfie_painter_v2"
    plugin_version = "3.6.4"
    plugin_author = "Ptrel，Rabbit，saberlights Kiuon，nguspring"
    enable_plugin = True
    dependencies: List[str] = []
    python_dependencies: List[PythonDependency] = [
        PythonDependency(
            package_name="requests",
            optional=True,
            description="用于部分图片后端（如魔搭、Gemini、砂糖云）的 HTTP 请求",
        ),
        PythonDependency(
            package_name="httpx",
            optional=True,
            description="用于自动自拍发布时拉取网络图片",
        ),
        PythonDependency(
            package_name="volcengine-python-sdk",
            install_name="volcengine-python-sdk[ark]",
            optional=True,
            description="用于豆包（Ark）模型接入",
        ),
        PythonDependency(
            package_name="beautifulsoup4",
            install_name="beautifulsoup4",
            optional=True,
            description="用于角色参考图功能的 Bing 图片搜索解析",
        ),
    ]
    config_file_name = "config.toml"

    # 配置节元数据
    config_section_descriptions = {
        # ---- basic 标签页 ----
        "plugin": ConfigSection(title="插件启用配置", icon="info", order=1),
        "generation": ConfigSection(title="图片生成默认配置", icon="image", order=2),
        "components": ConfigSection(title="组件启用配置", icon="puzzle-piece", order=3),
        # ---- network 标签页 ----
        "proxy": ConfigSection(title="代理设置", icon="globe", order=4),
        "cache": ConfigSection(title="结果缓存配置", icon="database", order=5),
        # ---- features 标签页 ----
        "selfie": ConfigSection(title="自拍模式配置", icon="camera", order=6),
        "wardrobe": ConfigSection(
            title="衣柜系统",
            description="管理“穿搭(Outfit)”的配置入口：你可以在这里添加多套衣服标签，并让自拍根据日程活动自动注入合适的服装提示词；中文穿搭会优先映射或翻译成英文标签后再注入",
            icon="shirt",
            order=11,
        ),
        "schedule": ConfigSection(
            title="内置日程配置", description="内置 SQLite 日程系统（模板兜底 + LLM 生成）", icon="calendar", order=7
        ),
        "auto_selfie": ConfigSection(
            title="自动自拍配置",
            description="定时自动生成自拍并发送到聊天流或QQ空间。发送到聊天流无需额外插件；发布到QQ空间需安装 Maizone 插件。日程数据由内置日程系统提供",
            icon="camera",
            order=8,
        ),
        "schedule_inject": ConfigSection(
            title="日程注入配置",
            description="在 LLM 生成回复前注入麦麦当前日程信息，让回复更有代入感",
            icon="inject",
            order=9,
        ),
        "auto_recall": ConfigSection(title="自动撤回配置", icon="trash", order=11),
        "search_reference": ConfigSection(
            title="角色参考图配置",
            description="通过搜索引擎获取角色参考图，VLM 提取特征后注入提示词以提升角色一致性",
            icon="search",
            order=10,
        ),
        "prompt_optimizer": ConfigSection(
            title="提示词优化器",
            description="使用 MaiBot 主 LLM 将用户描述优化为专业绘画提示词",
            icon="wand-2",
            order=10,
        ),
        # ---- styles 标签页 ----
        "styles": ConfigSection(
            title="风格定义",
            description='预设风格的提示词。添加更多风格请直接编辑 config.toml，格式：风格英文名 = "提示词"',
            icon="palette",
            order=10,
        ),
        "style_aliases": ConfigSection(
            title="风格别名", description="风格的中文别名映射。添加更多别名请直接编辑 config.toml", icon="tag", order=11
        ),
        # ---- models 标签页 ----
        "access_control": ConfigSection(
            title="聊天流访问控制",
            description="全局聊天流黑白名单。默认黑名单模式，即默认所有聊天流都可用，只有命中黑名单才会禁用",
            icon="shield",
            order=12,
        ),
        "models": ConfigSection(
            title="多模型配置",
            description="添加更多模型请直接编辑 config.toml，复制 [models.model1] 整节并改名为 model2、model3 等",
            icon="cpu",
            order=12,
        ),
        "models.model1": ConfigSection(title="模型1配置", icon="box", order=13),
    }

    # 自定义布局：标签页
    config_layout = ConfigLayout(
        type="tabs",
        tabs=[
            ConfigTab(id="basic", title="基础设置", sections=["plugin", "generation", "components"], icon="settings"),
            ConfigTab(id="network", title="网络配置", sections=["proxy", "cache"], icon="wifi"),
            ConfigTab(
                id="features",
                title="功能配置",
                sections=[
                    "selfie",
                    "wardrobe",
                    "schedule",
                    "schedule_inject",
                    "auto_selfie",
                    "auto_recall",
                    "prompt_optimizer",
                    "search_reference",
                ],
                icon="zap",
            ),
            ConfigTab(id="styles", title="风格管理", sections=["styles", "style_aliases"], icon="palette"),
            ConfigTab(
                id="models", title="模型管理", sections=["access_control", "models", "models.model1"], icon="cpu"
            ),
        ],
    )

    # 配置Schema
    config_schema = {
        "plugin": {
            "name": ConfigField(
                type=str,
                default="麦麦绘卷",
                description="麦麦绘卷（Claude MAInet）— 智能多模型图片生成插件，支持文生图/图生图自动识别",
                label="插件名称",
                required=True,
                disabled=True,
                order=1,
            ),
            "config_version": ConfigField(
                type=str, default="3.6.4", description="插件配置版本号", label="配置版本", disabled=True, order=2
            ),
            "enabled": ConfigField(
                type=bool,
                default=False,
                description="是否启用插件。开启后麦麦可以画画，关闭则所有画图功能都不可用",
                label="启用插件",
                order=3,
            ),
        },
        "generation": {
            "default_model": ConfigField(
                type=str,
                default="model1",
                description="默认使用的模型ID（对应模型管理中的配置）。第一次画图时使用这个模型，之后可通过 /dr set 命令切换",
                label="默认模型",
                hint="对应模型管理中的模型ID（如model1、model2）",
                example="model1",
                placeholder="model1",
                order=1,
            ),
        },
        "access_control": {
            "mode": ConfigField(
                type=str,
                default="blacklist",
                description="全局聊天流访问模式。blacklist=黑名单（默认，名单内禁用，其他全部允许）；whitelist=白名单（仅名单内允许）",
                label="全局模式",
                choices=["blacklist", "whitelist"],
                order=1,
            ),
            "list": ConfigField(
                type=list,
                default=[],
                description="全局聊天流列表。格式示例：qq:114514:private、qq:1919810:group",
                label="全局聊天流列表",
                item_type="string",
                placeholder="qq:1919810:group",
                hint="每行一个聊天流ID",
                order=2,
            ),
        },
        "cache": {
            "enabled": ConfigField(
                type=bool,
                default=True,
                description="是否启用结果缓存。开启后，相同的画图请求会复用之前的结果，节省时间和API费用",
                label="启用缓存",
                order=1,
            ),
            "max_size": ConfigField(
                type=int,
                default=10,
                description="最大缓存数量。缓存图片超过这个数量后，会删除最旧的。建议 5-20",
                label="最大缓存数",
                min=1,
                max=100,
                depends_on="cache.enabled",
                depends_value=True,
                order=2,
            ),
        },
        "components": {
            "enable_unified_generation": ConfigField(
                type=bool,
                default=True,
                description="是否启用智能画图功能。开启后麦麦会根据对话内容自动决定是否画图（支持文生图和图生图）",
                label="智能生图",
                order=1,
            ),
            "enable_pic_command": ConfigField(
                type=bool,
                default=True,
                description="是否启用 /dr 命令。开启后可使用 /dr 风格名、/dr 描述 等命令画图",
                label="图片生成命令",
                order=2,
            ),
            "enable_pic_config": ConfigField(
                type=bool,
                default=True,
                description="是否启用配置管理命令（/dr list、/dr set 等）。需要管理员权限才能使用",
                label="配置管理",
                order=3,
            ),
            "enable_pic_style": ConfigField(
                type=bool,
                default=True,
                description="是否启用风格管理命令（/dr styles、/dr style 等）",
                label="风格管理",
                order=4,
            ),
            "pic_command_model": ConfigField(
                type=str,
                default="model1",
                description="/dr 命令使用的模型ID。可通过 /dr set 命令动态切换",
                label="Command模型",
                placeholder="model1",
                order=5,
            ),
            "enable_debug_info": ConfigField(
                type=bool,
                default=False,
                description="是否显示调试信息。开启后会显示画图参数、耗时等信息，方便排查问题",
                label="调试信息",
                order=6,
            ),
            "enable_verbose_debug": ConfigField(
                type=bool,
                default=False,
                description="是否显示详细调试信息。开启后会打印完整的HTTP请求报文（适合开发者调试）",
                label="详细调试",
                order=7,
            ),
            "show_all_prompts": ConfigField(
                type=bool,
                default=False,
                description="是否在后台日志中显示本次实际送去生图接口的完整提示词。开启后日志会记录完整正面提示词、负面提示词和自拍风格，不会发送到QQ聊天界面",
                label="显示全部提示词",
                order=8,
            ),
            "admin_users": ConfigField(
                type=list,
                default=[],
                description="管理员QQ号列表（字符串格式）。只有管理员才能使用 /dr set、/dr model 等配置命令",
                label="管理员列表",
                hint='字符串形式的用户ID，如 ["12345", "67890"]',
                item_type="string",
                placeholder='["用户ID1", "用户ID2"]',
                order=9,
            ),
            "max_retries": ConfigField(
                type=int,
                default=2,
                description="API调用失败时的重试次数。建议 1-3 次，太多会浪费时间",
                label="重试次数",
                min=0,
                max=10,
                order=10,
            ),
        },
        "proxy": {
            "enabled": ConfigField(
                type=bool,
                default=False,
                description="是否启用代理。开启后所有API请求都会通过代理服务器发送（适合网络受限的环境）",
                label="启用代理",
                order=1,
            ),
            "url": ConfigField(
                type=str,
                default="http://127.0.0.1:7890",
                description="代理服务器地址。格式：http://IP:端口 或 socks5://IP:端口。示例: http://127.0.0.1:7890",
                label="代理地址",
                hint="支持 HTTP、HTTPS、SOCKS5 代理",
                example="http://127.0.0.1:7890",
                placeholder="http://127.0.0.1:7890",
                depends_on="proxy.enabled",
                depends_value=True,
                order=2,
            ),
            "timeout": ConfigField(
                type=int,
                default=60,
                description="代理连接超时时间（秒）。建议 30-120 秒，太小可能连接失败",
                label="超时时间",
                min=10,
                max=300,
                depends_on="proxy.enabled",
                depends_value=True,
                order=3,
            ),
        },
        "styles": {
            "cartoon": ConfigField(
                type=str,
                default="cartoon style, anime style, colorful, vibrant colors, clean lines",
                description="卡通风格提示词",
                label="卡通风格",
                input_type="textarea",
                rows=3,
                order=1,
            )
        },
        "style_aliases": {
            "cartoon": ConfigField(
                type=str,
                default="卡通",
                description="cartoon 风格的中文别名，支持多别名用逗号分隔",
                label="卡通别名",
                placeholder="卡通,动漫",
                order=1,
            )
        },
        "selfie": {
            "enabled": ConfigField(
                type=bool,
                default=False,
                description="是否启用自拍模式。开启后麦麦可以发自拍（会自动添加角色外观描述）",
            ),
            "reference_image_path": ConfigField(
                type=str,
                default="",
                description="自拍参考图片路径。配置后会用这张图作为参考生成自拍（图生图模式），留空则纯文字生成",
                label="参考图片",
                placeholder="images/reference.png",
                depends_on="selfie.enabled",
                depends_value=True,
                order=2,
            ),
            "prompt_prefix": ConfigField(
                type=str,
                default="",
                description="自拍专用外观描述。描述麦麦的样子（发色、瞳色、服装等），会自动添加到所有自拍提示词前",
                label="提示词前缀",
                input_type="textarea",
                rows=2,
                placeholder="blue hair, red eyes, school uniform, 1girl",
                depends_on="selfie.enabled",
                depends_value=True,
                order=3,
            ),
            "negative_prompt": ConfigField(
                type=str,
                default="",
                description="自拍专用负面提示词。避免生成不想要的内容（手部畸形、多指等会自动添加）",
                label="负面提示词",
                input_type="textarea",
                rows=3,
                placeholder="lowres, bad anatomy, bad hands, extra fingers",
                depends_on="selfie.enabled",
                depends_value=True,
                order=4,
            ),
            "schedule_enabled": ConfigField(
                type=bool,
                default=True,
                description="是否启用日程增强自拍。开启后自拍会结合当前日程活动生成更贴合情境的场景",
                label="日程增强",
                depends_on="selfie.enabled",
                depends_value=True,
                order=5,
            ),
            "default_style": ConfigField(
                type=str,
                default="standard",
                description="默认自拍风格。standard=前置自拍（拿手机），mirror=对镜自拍，photo=第三人称照片",
                label="默认自拍风格",
                choices=["standard", "mirror", "photo"],
                depends_on="selfie.enabled",
                depends_value=True,
                order=6,
            ),
            "show_prompt_details": ConfigField(
                type=bool,
                default=False,
                description="是否在后台日志中完整显示自拍模式本次使用的提示词与负面提示词，仅用于排查风格是否真的切换，不会发送到QQ聊天界面",
                label="自拍显示提示词",
                depends_on="selfie.enabled",
                depends_value=True,
                order=7,
            ),
        },
        "wardrobe": {
            # ========== 总开关（默认关闭） ==========
            "enabled": ConfigField(
                type=bool,
                default=False,
                description="是否启用衣柜系统。开启后自拍会根据日程活动自动选择合适的服装",
                label="启用衣柜",
                order=1,
            ),
            # ========== 每日穿搭 ==========
            "daily_outfits": ConfigField(
                type=list,
                default=["哥特洛丽塔", "宽松休闲装", "黑丝JK", "白丝JK"],
                description="每日穿搭列表。每天随机选一套作为当日穿搭。可写简短名称（如'哥特洛丽塔'）由LLM补充细节",
                label="每日穿搭",
                depends_on="wardrobe.enabled",
                depends_value=True,
                order=10,
            ),
            # ========== 自动换装 ==========
            "auto_scene_change": ConfigField(
                type=bool,
                default=True,
                description="自动场景换装。开启后根据日程活动自动匹配场景并换装（如睡觉时换睡衣）",
                label="自动换装",
                depends_on="wardrobe.enabled",
                depends_value=True,
                order=20,
            ),
            # ========== 自定义场景 ==========
            "custom_scenes": ConfigField(
                type=list,
                default=["睡觉的时候穿可爱睡衣", "运动的时候穿运动服"],
                description="自定义场景规则。一句话格式：'在XX的时候穿XX'。例如：'在实验室的时候穿实验服'",
                label="自定义场景",
                depends_on="wardrobe.auto_scene_change",
                depends_value=True,
                order=30,
            ),
        },
        "auto_recall": {
            "enabled": ConfigField(
                type=bool,
                default=False,
                description="是否启用自动撤回功能（总开关）。关闭后所有模型的撤回都不生效",
                label="启用撤回",
                order=1,
            )
        },
        "prompt_optimizer": {
            "enabled": ConfigField(
                type=bool,
                default=True,
                description="是否启用提示词优化器。开启后会使用 LLM 将用户描述优化为专业英文提示词（优先使用下方自定义API，未配置则使用 MaiBot 主 LLM）",
                label="启用优化器",
                order=1,
            ),
            "custom_api_base_url": ConfigField(
                type=str,
                default="",
                description="自定义API地址（OpenAI兼容格式）。留空则使用 MaiBot 主 LLM。示例：https://api.deepseek.com/v1、https://api.siliconflow.cn/v1",
                label="自定义API地址",
                placeholder="https://api.deepseek.com/v1",
                depends_on="prompt_optimizer.enabled",
                depends_value=True,
                order=2,
            ),
            "custom_api_key": ConfigField(
                type=str,
                default="",
                description="自定义API密钥。直接填密钥即可（如 sk-xxx），系统会自动添加 Bearer 前缀。留空则使用 MaiBot 主 LLM",
                label="自定义API密钥",
                input_type="text",
                placeholder="sk-xxx",
                depends_on="prompt_optimizer.enabled",
                depends_value=True,
                order=3,
            ),
            "custom_api_model": ConfigField(
                type=str,
                default="",
                description="自定义模型名称。例如：deepseek-chat、gpt-4o-mini、Qwen/Qwen2.5-7B-Instruct。留空则使用 MaiBot 主 LLM",
                label="自定义模型名称",
                placeholder="deepseek-chat",
                depends_on="prompt_optimizer.enabled",
                depends_value=True,
                order=4,
            ),
        },
        "search_reference": {
            "enabled": ConfigField(
                type=bool,
                default=False,
                description="是否启用角色参考图（提升角色一致性）。启用后可通过 /dr refresh <角色名> 下载参考图",
                label="启用角色参考",
                order=1,
            ),
            "character_only": ConfigField(
                type=bool,
                default=True,
                description="仅在'画某角色'这类请求时触发特征注入（关闭则所有生图请求都会尝试匹配）",
                label="仅角色请求触发",
                order=2,
            ),
            "max_images_per_role": ConfigField(
                type=int,
                default=3,
                description="每个角色最多保存几张参考图",
                label="最大参考图数",
                min=1,
                max=10,
                order=3,
            ),
            "search_top_k": ConfigField(
                type=int,
                default=6,
                description="每次搜索候选图数量（越大越慢但命中率越高）",
                label="搜索候选数",
                min=3,
                max=20,
                order=4,
            ),
            "max_cache_size_mb": ConfigField(
                type=int,
                default=100,
                description="参考图库总容量上限 MB（超出会自动清理旧数据）",
                label="缓存上限 MB",
                min=10,
                max=1024,
                order=5,
            ),
            "feature_boost_weight": ConfigField(
                type=float,
                default=1.25,
                description="特征注入权重（越高越强调角色特征，1.0=不增强，2.0=最大增强）",
                label="特征注入权重",
                min=1.0,
                max=2.0,
                step=0.05,
                order=6,
            ),
            "vision_prompt": ConfigField(
                type=str,
                default="请用中文详细描述这张图片中主要人物的特征是什么，纯粹描述即可。输出为一段平文本，总字数最多不超过120字。",
                description="VLM 识图提示词（一般不需修改）",
                label="识图提示词",
                input_type="textarea",
                rows=3,
                order=7,
            ),
            "hint": ConfigField(
                type=str,
                default="命令：/dr refresh <角色名>、/dr status <角色名>、/dr clear <角色名>",
                description="使用提示",
                disabled=True,
                order=8,
            ),
        },
        "schedule": {
            # ========== 自动生成配置 ==========
            "auto_generate_enabled": ConfigField(
                type=bool,
                default=True,
                description="每日自动生成日程（内置日程系统，无需外部插件）",
                label="自动生成日程",
                order=1,
            ),
            "auto_generate_time": ConfigField(
                type=str,
                default="06:30",
                description="每日自动生成时间，格式 HH:MM",
                label="生成时间",
                placeholder="06:30",
                order=2,
            ),
            "model_id": ConfigField(
                type=str,
                default="planner",
                description="日程生成使用的麦麦 LLM 模型。可用值：utils（组件模型）、tool_use（工具调用模型）、replyer（首要回复模型）、planner（决策模型，推荐）、vlm（图像识别模型）",
                label="日程模型",
                placeholder="planner",
                order=3,
            ),
            # ========== 人设补充配置 ==========
            # 这些配置用于补充主程序人设，让日程更贴合麦麦的性格
            "schedule_identity": ConfigField(
                type=str,
                default="",
                description="身份补充，用于让日程更贴合麦麦的身份设定。例如：'是一个二次元爱好者，喜欢画画'。会与主程序的人设配置合并使用",
                label="身份补充",
                placeholder="是一个二次元爱好者，喜欢画画",
                order=10,
            ),
            "schedule_interest": ConfigField(
                type=str,
                default="",
                description="兴趣爱好，用于让日程活动更符合麦麦的兴趣。例如：'画画、听音乐、打游戏、看番'。日程生成时会优先安排这些活动",
                label="兴趣爱好",
                placeholder="画画、听音乐、打游戏、看番",
                order=11,
            ),
            "schedule_lifestyle": ConfigField(
                type=str,
                default="",
                description="生活规律，用于让日程作息更符合麦麦的习惯。例如：'习惯晚睡，经常熬夜，早上起不来'。会影响日程的时间安排",
                label="生活规律",
                placeholder="习惯晚睡，经常熬夜",
                order=12,
            ),
            # ========== 历史记忆配置 ==========
            # 让日程有连续性，昨天的日程会影响今天的安排
            "schedule_history_days": ConfigField(
                type=int,
                default=1,
                description="历史日程参考天数。1=仅参考昨天(默认)；2=参考前两天；0=不参考历史。参考历史可让日程有连续性，比如昨天在学Python，今天继续学",
                label="历史参考天数",
                min=0,
                max=7,
                order=20,
            ),
            "schedule_history_retention_days": ConfigField(
                type=int,
                default=-1,
                description="历史日程保留天数。-1=永久保留(默认，数据量很小)；7=保留一周；30=保留一个月。超期的历史日程会被自动清理",
                label="历史保留天数",
                min=-1,
                max=365,
                order=21,
            ),
            # ========== 自定义Prompt配置 ==========
            "schedule_custom_prompt": ConfigField(
                type=str,
                default="",
                description="自定义日程风格要求(可选)。例如：'日程安排要宽松一些'。注意：不能改变输出格式，只能追加风格要求。留空则使用默认风格",
                label="日程风格要求",
                placeholder="日程安排要宽松一些，多安排休息时间",
                order=30,
            ),
            # ========== 多轮生成配置 ==========
            # 提升日程生成质量，避免空档、描述过短等问题
            "schedule_multi_round": ConfigField(
                type=bool,
                default=True,
                description="是否启用多轮生成优化。开启后如果生成的日程质量不达标会自动重试修复。建议开启，可以避免日程空档、描述过短等问题",
                label="多轮生成优化",
                order=40,
            ),
            "schedule_max_rounds": ConfigField(
                type=int,
                default=2,
                description="最大重试轮数。当日程质量不达标时最多重试几次。建议2-3次，太多会消耗更多token",
                label="最大重试轮数",
                min=1,
                max=5,
                depends_on="schedule.schedule_multi_round",
                depends_value=True,
                order=41,
            ),
            "schedule_quality_threshold": ConfigField(
                type=float,
                default=0.8,
                description="质量分数阈值(0.0-1.0)。生成的日程分数低于此阈值时会触发重试。建议0.75-0.85，太高可能导致频繁重试",
                label="质量阈值",
                min=0.5,
                max=1.0,
                depends_on="schedule.schedule_multi_round",
                depends_value=True,
                order=42,
            ),
        },
        "schedule_inject": {
            # ========== 基础注入配置 ==========
            "enabled": ConfigField(
                type=bool,
                default=True,
                description="是否在 LLM 生成回复前注入麦麦当前日程信息",
                label="启用日程注入",
                order=1,
            ),
            "mode": ConfigField(
                type=str,
                default="smart",
                description="注入模式。smart=智能节流（按时间/消息数触发），always=每次都注入",
                label="注入模式",
                placeholder="smart",
                order=2,
            ),
            "min_messages": ConfigField(
                type=int,
                default=5,
                description="smart 模式下，同一会话收到多少条消息后再次注入",
                label="最小消息数",
                depends_on="schedule_inject.enabled",
                depends_value=True,
                order=3,
            ),
            "min_seconds": ConfigField(
                type=int,
                default=300,
                description="smart 模式下，距离上次注入多少秒后再次注入",
                label="最小间隔（秒）",
                depends_on="schedule_inject.enabled",
                depends_value=True,
                order=4,
            ),
            # ========== 智能注入增强配置 ==========
            # 这些配置用于让注入更智能，避免在不相关的问题上注入日程
            "schedule_intent_enable": ConfigField(
                type=bool,
                default=True,
                description="是否启用意图识别。开启后系统会识别用户意图，只在相关问题上注入日程。例如：技术问答时不注入，询问日程时注入。建议开启",
                label="意图识别",
                depends_on="schedule_inject.enabled",
                depends_value=True,
                order=10,
            ),
            "schedule_context_cache_ttl_minutes": ConfigField(
                type=int,
                default=30,
                description="对话上下文缓存TTL(分钟)。用于记住最近的对话内容，让连续对话更自然。建议15-60分钟",
                label="上下文缓存TTL",
                min=5,
                max=120,
                depends_on="schedule_inject.enabled",
                depends_value=True,
                order=11,
            ),
            "schedule_context_cache_max_turns": ConfigField(
                type=int,
                default=10,
                description="对话上下文最大轮数。缓存最近的N轮对话，用于连续对话理解。建议5-20轮",
                label="上下文最大轮数",
                min=1,
                max=50,
                depends_on="schedule_inject.enabled",
                depends_value=True,
                order=12,
            ),
        },
        "auto_selfie": {
            "enabled": ConfigField(
                type=bool,
                default=False,
                description="是否启用自动自拍。日程数据由内置日程系统自动提供，发送到聊天流无需额外插件（若需发布到QQ空间，则需安装 Maizone 插件）",
                label="启用自动自拍",
                order=1,
            ),
            "interval_minutes": ConfigField(
                type=int,
                default=120,
                description="自拍间隔（分钟）。建议 60-240 分钟，太频繁可能被限制",
                label="自拍间隔",
                min=10,
                max=1440,
                depends_on="auto_selfie.enabled",
                depends_value=True,
                order=2,
            ),
            "selfie_model": ConfigField(
                type=str,
                default="model1",
                description="自拍使用的模型ID。对应模型管理中的配置（如 model1、model2）",
                label="自拍模型",
                placeholder="model1",
                depends_on="auto_selfie.enabled",
                depends_value=True,
                order=3,
            ),
            "quiet_hours_start": ConfigField(
                type=str,
                default="00:00",
                description="安静时段开始时间（HH:MM）。此时段内不发自拍，避免半夜打扰",
                label="安静开始",
                example="00:00",
                placeholder="00:00",
                depends_on="auto_selfie.enabled",
                depends_value=True,
                order=4,
            ),
            "quiet_hours_end": ConfigField(
                type=str,
                default="07:00",
                description="安静时段结束时间（HH:MM）",
                label="安静结束",
                placeholder="07:00",
                depends_on="auto_selfie.enabled",
                depends_value=True,
                order=5,
            ),
            "caption_enabled": ConfigField(
                type=bool,
                default=True,
                description="是否为自拍生成配文。开启后会用 LLM 根据日程生成文字描述",
                label="生成配文",
                depends_on="auto_selfie.enabled",
                depends_value=True,
                order=6,
            ),
            "send_to_qzone": ConfigField(
                type=bool,
                default=False,
                description="是否将自动自拍发布到 QQ 空间说说。需要安装 Maizone 插件",
                label="发送到QQ空间",
                order=7,
            ),
            "send_to_chat": ConfigField(
                type=bool,
                default=False,
                description="是否将自动自拍发送到指定群聊和私聊",
                label="发送到群聊/私聊",
                order=8,
            ),
            "target_groups": ConfigField(
                type=list,
                default=[],
                description="目标群号列表（纯数字字符串）。每行一个群号，send_to_chat 开启时生效",
                label="目标群号",
                item_type="string",
                placeholder="123456789",
                hint="填群号，每行一个",
                order=9,
            ),
            "target_users": ConfigField(
                type=list,
                default=[],
                description="目标私聊QQ号列表（纯数字字符串）。每行一个QQ号，send_to_chat 开启时生效",
                label="目标私聊QQ号",
                item_type="string",
                placeholder="987654321",
                hint="填QQ号，每行一个",
                order=10,
            ),
            "persist_state": ConfigField(
                type=bool,
                default=True,
                description="是否持久化自拍状态。开启后重启不会立即自拍，而是等待剩余间隔",
                label="持久化自拍状态",
                depends_on="auto_selfie.enabled",
                depends_value=True,
                order=11,
            ),
        },
        "models": {},
        # 基础模型配置模板
        "models.model1": {
            "name": ConfigField(
                type=str,
                default="Tongyi-MAI/Z-Image-Turbo",
                description="模型显示名称。在 /dr list 命令中显示，方便识别",
                label="模型名称",
                group="connection",
                order=1,
            ),
            "base_url": ConfigField(
                type=str,
                default="https://api-inference.modelscope.cn/v1",
                description="API服务地址。各平台地址不同：魔搭=https://api-inference.modelscope.cn/v1，硅基流动=https://api.siliconflow.cn/v1，豆包=https://ark.cn-beijing.volces.com/api/v3",
                label="API地址",
                required=True,
                group="connection",
                order=2,
            ),
            "api_key": ConfigField(
                type=str,
                default="Bearer YOUR_MODELSCOPE_TOKEN",
                description="API密钥。统一填写 'Bearer xxx' 格式，部分平台会自动处理",
                label="API密钥",
                input_type="text",
                required=True,
                group="connection",
                order=3,
            ),
            "format": ConfigField(
                type=str,
                default="modelscope",
                description="API格式。不同平台接口不同：openai=通用格式，modelscope=魔搭，doubao=豆包，gemini=Gemini，shatangyun=砂糖云(NovelAI)，comfyui=本地ComfyUI",
                label="API格式",
                choices=[
                    "openai",
                    "openai-chat",
                    "gemini",
                    "doubao",
                    "modelscope",
                    "shatangyun",
                    "mengyuai",
                    "zai",
                    "comfyui",
                ],
                required=True,
                group="connection",
                order=4,
            ),
            "model": ConfigField(
                type=str,
                default="Tongyi-MAI/Z-Image-Turbo",
                description="模型标识。填模型ID或模型名称，如 cancel13/liaocao。ComfyUI格式填工作流文件名",
                label="模型标识",
                required=True,
                group="connection",
                order=5,
            ),
            "fixed_size_enabled": ConfigField(
                type=bool,
                default=False,
                description="是否固定图片尺寸。开启后强制使用 default_size，关闭则由 LLM 自动选择合适尺寸",
            ),
            "default_size": ConfigField(
                type=str,
                default="1024x1024",
                description="默认图片尺寸。格式：宽x高。常见值：1024x1024、512x768、768x512",
                label="默认尺寸",
                group="params",
                order=7,
            ),
            "seed": ConfigField(
                type=int,
                default=-1,
                description="随机种子。-1=每次随机；固定值（如 42）可复现相同结果",
                label="随机种子",
                min=-1,
                max=2147483647,
                group="params",
                order=8,
            ),
            "guidance_scale": ConfigField(
                type=float,
                default=2.5,
                description="引导强度（CFG）。控制AI'听话程度'。值越高越严格遵循提示词。推荐：魔搭/硅基流动 2.5-7.5",
                label="引导强度",
                min=0.0,
                max=20.0,
                step=0.5,
                group="params",
                order=9,
            ),
            "num_inference_steps": ConfigField(
                type=int,
                default=30,
                description="推理步数。影响质量和速度。推荐 20-50，太少质量差，太多太慢",
                label="推理步数",
                min=1,
                max=150,
                group="params",
                order=10,
            ),
            "watermark": ConfigField(
                type=bool,
                default=True,
                description="是否添加水印。部分平台会自动添加",
            ),
            "custom_prompt_add": ConfigField(
                type=str,
                default="",
                description="正面提示词增强。自动添加到用户描述后面，用于统一风格",
                label="正面增强词",
                input_type="textarea",
                rows=2,
                group="prompts",
                order=12,
            ),
            "negative_prompt_add": ConfigField(
                type=str,
                default="low quality, worst quality, blurry, text, watermark",
                description="负面提示词。避免生成不想要的内容（低质量、模糊、水印等）。豆包/Gemini 不支持此参数",
                label="负面提示词",
                input_type="textarea",
                rows=2,
                group="prompts",
                order=13,
            ),
            "artist": ConfigField(
                type=str,
                default="",
                description="艺术家风格标签。仅砂糖云格式生效，留空则不添加",
                label="艺术家标签",
                group="prompts",
                order=14,
            ),
            "support_img2img": ConfigField(
                type=bool,
                default=True,
                description="是否支持图生图。根据模型能力填写，不支持会自动降级为文生图",
                label="支持图生图",
                group="prompts",
                order=15,
            ),
            "auto_recall_delay": ConfigField(
                type=int,
                default=0,
                description="自动撤回延时（秒）。大于0时启用撤回，需先开启自动撤回总开关",
                label="撤回延时",
                min=0,
                max=120,
                group="prompts",
                order=16,
            ),
            "cfg": ConfigField(
                type=float,
                default=0,
                description="CFG Rescale 参数。仅砂糖云格式生效，一般填 0",
                label="CFG Rescale",
                hint="仅砂糖云格式生效",
                min=0.0,
                max=1.0,
                step=0.1,
                group="platform",
                order=20,
            ),
            "sampler": ConfigField(
                type=str,
                default="k_euler_ancestral",
                description="采样器名称。仅砂糖云格式生效。推荐 k_euler_ancestral",
                label="采样器",
                hint="仅砂糖云格式生效",
                choices=[
                    "k_euler_ancestral",
                    "k_euler",
                    "k_dpmpp_2s_ancestral",
                    "k_dpmpp_2m_sde",
                    "k_dpmpp_2m",
                    "k_dpmpp_sde",
                ],
                group="platform",
                order=21,
            ),
            "nocache": ConfigField(
                type=int,
                default=0,
                description="是否禁用缓存。仅砂糖云格式生效。0=使用缓存，1=禁用",
                label="禁用缓存",
                hint="仅砂糖云格式生效",
                min=0,
                max=1,
                group="platform",
                order=22,
            ),
            "noise_schedule": ConfigField(
                type=str,
                default="karras",
                description="噪声调度方案。仅砂糖云格式生效。推荐 karras",
                label="噪声调度",
                hint="仅砂糖云格式生效",
                choices=["karras", "native", "exponential", "polyexponential"],
                group="platform",
                order=23,
            ),
        },
        "models.model2": {
            "name": ConfigField(
                type=str,
                default="QWQ114514123/WAI-illustrious-SDXL-v16",
                description="模型显示名称",
                label="模型名称",
                group="connection",
                order=1,
            ),
            "base_url": ConfigField(
                type=str,
                default="https://api-inference.modelscope.cn/v1",
                description="API服务地址",
                label="API地址",
                required=True,
                group="connection",
                order=2,
            ),
            "api_key": ConfigField(
                type=str,
                default="Bearer YOUR_MODELSCOPE_TOKEN",
                description="API密钥，格式：Bearer xxx",
                label="API密钥",
                input_type="text",
                required=True,
                group="connection",
                order=3,
            ),
            "format": ConfigField(
                type=str,
                default="modelscope",
                description="API格式",
                label="API格式",
                choices=[
                    "openai",
                    "openai-chat",
                    "gemini",
                    "doubao",
                    "modelscope",
                    "shatangyun",
                    "mengyuai",
                    "zai",
                    "comfyui",
                ],
                required=True,
                group="connection",
                order=4,
            ),
            "model": ConfigField(
                type=str,
                default="QWQ114514123/WAI-illustrious-SDXL-v16",
                description="模型标识",
                label="模型标识",
                required=True,
                group="connection",
                order=5,
            ),
            "fixed_size_enabled": ConfigField(
                type=bool, default=False, description="是否固定图片尺寸", label="固定尺寸", group="params", order=6
            ),
            "default_size": ConfigField(
                type=str, default="1024x1024", description="默认图片尺寸", label="默认尺寸", group="params", order=7
            ),
            "seed": ConfigField(
                type=int,
                default=-1,
                description="随机种子",
                label="随机种子",
                min=-1,
                max=2147483647,
                group="params",
                order=8,
            ),
            "guidance_scale": ConfigField(
                type=float,
                default=2.5,
                description="引导强度",
                label="引导强度",
                min=0.0,
                max=20.0,
                step=0.5,
                group="params",
                order=9,
            ),
            "num_inference_steps": ConfigField(
                type=int, default=20, description="推理步数", label="推理步数", min=1, max=150, group="params", order=10
            ),
            "watermark": ConfigField(
                type=bool, default=True, description="是否添加水印", label="水印", group="params", order=11
            ),
            "custom_prompt_add": ConfigField(
                type=str,
                default="",
                description="正面提示词增强",
                label="正面增强词",
                input_type="textarea",
                rows=2,
                group="prompts",
                order=12,
            ),
            "negative_prompt_add": ConfigField(
                type=str,
                default="low quality, worst quality, blurry, text, watermark",
                description="负面提示词",
                label="负面提示词",
                input_type="textarea",
                rows=2,
                group="prompts",
                order=13,
            ),
            "artist": ConfigField(
                type=str,
                default="",
                description="艺术家风格标签（砂糖云专用）",
                label="艺术家标签",
                group="prompts",
                order=14,
            ),
            "support_img2img": ConfigField(
                type=bool, default=True, description="是否支持图生图", label="支持图生图", group="prompts", order=15
            ),
            "auto_recall_delay": ConfigField(
                type=int,
                default=0,
                description="自动撤回延时（秒）",
                label="撤回延时",
                min=0,
                max=120,
                group="prompts",
                order=16,
            ),
            "cfg": ConfigField(
                type=float,
                default=0,
                description="CFG Rescale（仅砂糖云格式生效）",
                label="CFG Rescale",
                hint="仅砂糖云格式生效",
                min=0.0,
                max=1.0,
                step=0.1,
                group="platform",
                order=20,
            ),
            "sampler": ConfigField(
                type=str,
                default="k_euler_ancestral",
                description="采样器（仅砂糖云格式生效）",
                label="采样器",
                hint="仅砂糖云格式生效",
                choices=[
                    "k_euler_ancestral",
                    "k_euler",
                    "k_dpmpp_2s_ancestral",
                    "k_dpmpp_2m_sde",
                    "k_dpmpp_2m",
                    "k_dpmpp_sde",
                ],
                group="platform",
                order=21,
            ),
            "nocache": ConfigField(
                type=int,
                default=0,
                description="是否禁用缓存（仅砂糖云格式生效）",
                label="禁用缓存",
                hint="仅砂糖云格式生效",
                min=0,
                max=1,
                group="platform",
                order=22,
            ),
            "noise_schedule": ConfigField(
                type=str,
                default="karras",
                description="噪声调度方案（仅砂糖云格式生效）",
                label="噪声调度",
                hint="仅砂糖云格式生效",
                choices=["karras", "native", "exponential", "polyexponential"],
                group="platform",
                order=23,
            ),
        },
        "models.model3": {
            "name": ConfigField(
                type=str,
                default="cancel13/liaocao",
                description="模型显示名称",
                label="模型名称",
                group="connection",
                order=1,
            ),
            "base_url": ConfigField(
                type=str,
                default="https://api-inference.modelscope.cn/v1",
                description="API服务地址",
                label="API地址",
                required=True,
                group="connection",
                order=2,
            ),
            "api_key": ConfigField(
                type=str,
                default="Bearer YOUR_MODELSCOPE_TOKEN",
                description="API密钥，格式：Bearer xxx",
                label="API密钥",
                input_type="text",
                required=True,
                group="connection",
                order=3,
            ),
            "format": ConfigField(
                type=str,
                default="openai",
                description="API格式",
                label="API格式",
                choices=[
                    "openai",
                    "openai-chat",
                    "gemini",
                    "doubao",
                    "modelscope",
                    "shatangyun",
                    "mengyuai",
                    "zai",
                    "comfyui",
                ],
                required=True,
                group="connection",
                order=4,
            ),
            "model": ConfigField(
                type=str,
                default="cancel13/liaocao",
                description="模型标识",
                label="模型标识",
                required=True,
                group="connection",
                order=5,
            ),
            "fixed_size_enabled": ConfigField(
                type=bool, default=False, description="是否固定图片尺寸", label="固定尺寸", group="params", order=6
            ),
            "default_size": ConfigField(
                type=str, default="1024x1024", description="默认图片尺寸", label="默认尺寸", group="params", order=7
            ),
            "seed": ConfigField(
                type=int,
                default=-1,
                description="随机种子",
                label="随机种子",
                min=-1,
                max=2147483647,
                group="params",
                order=8,
            ),
            "guidance_scale": ConfigField(
                type=float,
                default=2.5,
                description="引导强度",
                label="引导强度",
                min=0.0,
                max=20.0,
                step=0.5,
                group="params",
                order=9,
            ),
            "num_inference_steps": ConfigField(
                type=int, default=20, description="推理步数", label="推理步数", min=1, max=150, group="params", order=10
            ),
            "watermark": ConfigField(
                type=bool, default=True, description="是否添加水印", label="水印", group="params", order=11
            ),
            "custom_prompt_add": ConfigField(
                type=str,
                default=", Nordic picture book art style, minimalist flat design, liaocao",
                description="正面提示词增强",
                label="正面增强词",
                input_type="textarea",
                rows=2,
                group="prompts",
                order=12,
            ),
            "negative_prompt_add": ConfigField(
                type=str,
                default="Pornography,nudity,lowres, bad anatomy, bad hands, text, error",
                description="负面提示词",
                label="负面提示词",
                input_type="textarea",
                rows=2,
                group="prompts",
                order=13,
            ),
            "artist": ConfigField(
                type=str,
                default="",
                description="艺术家风格标签（砂糖云专用）",
                label="艺术家标签",
                group="prompts",
                order=14,
            ),
            "support_img2img": ConfigField(
                type=bool, default=True, description="是否支持图生图", label="支持图生图", group="prompts", order=15
            ),
            "auto_recall_delay": ConfigField(
                type=int,
                default=0,
                description="自动撤回延时（秒）",
                label="撤回延时",
                min=0,
                max=120,
                group="prompts",
                order=16,
            ),
            "cfg": ConfigField(
                type=float,
                default=0,
                description="CFG Rescale（仅砂糖云格式生效）",
                label="CFG Rescale",
                hint="仅砂糖云格式生效",
                min=0.0,
                max=1.0,
                step=0.1,
                group="platform",
                order=20,
            ),
            "sampler": ConfigField(
                type=str,
                default="k_euler_ancestral",
                description="采样器（仅砂糖云格式生效）",
                label="采样器",
                hint="仅砂糖云格式生效",
                choices=[
                    "k_euler_ancestral",
                    "k_euler",
                    "k_dpmpp_2s_ancestral",
                    "k_dpmpp_2m_sde",
                    "k_dpmpp_2m",
                    "k_dpmpp_sde",
                ],
                group="platform",
                order=21,
            ),
            "nocache": ConfigField(
                type=int,
                default=0,
                description="是否禁用缓存（仅砂糖云格式生效）",
                label="禁用缓存",
                hint="仅砂糖云格式生效",
                min=0,
                max=1,
                group="platform",
                order=22,
            ),
            "noise_schedule": ConfigField(
                type=str,
                default="karras",
                description="噪声调度方案（仅砂糖云格式生效）",
                label="噪声调度",
                hint="仅砂糖云格式生效",
                choices=["karras", "native", "exponential", "polyexponential"],
                group="platform",
                order=23,
            ),
        },
        "models.model4": {
            "name": ConfigField(
                type=str,
                default="yuleai/Z-Image-Turbo-anime",
                description="模型显示名称",
                label="模型名称",
                group="connection",
                order=1,
            ),
            "base_url": ConfigField(
                type=str,
                default="https://api-inference.modelscope.cn/v1",
                description="API服务地址",
                label="API地址",
                required=True,
                group="connection",
                order=2,
            ),
            "api_key": ConfigField(
                type=str,
                default="Bearer YOUR_MODELSCOPE_TOKEN",
                description="API密钥，格式：Bearer xxx",
                label="API密钥",
                input_type="text",
                required=True,
                group="connection",
                order=3,
            ),
            "format": ConfigField(
                type=str,
                default="modelscope",
                description="API格式",
                label="API格式",
                choices=[
                    "openai",
                    "openai-chat",
                    "gemini",
                    "doubao",
                    "modelscope",
                    "shatangyun",
                    "mengyuai",
                    "zai",
                    "comfyui",
                ],
                required=True,
                group="connection",
                order=4,
            ),
            "model": ConfigField(
                type=str,
                default="yuleai/Z-Image-Turbo-anime",
                description="模型标识",
                label="模型标识",
                required=True,
                group="connection",
                order=5,
            ),
            "fixed_size_enabled": ConfigField(
                type=bool, default=False, description="是否固定图片尺寸", label="固定尺寸", group="params", order=6
            ),
            "default_size": ConfigField(
                type=str, default="1024x1024", description="默认图片尺寸", label="默认尺寸", group="params", order=7
            ),
            "seed": ConfigField(
                type=int,
                default=-1,
                description="随机种子",
                label="随机种子",
                min=-1,
                max=2147483647,
                group="params",
                order=8,
            ),
            "guidance_scale": ConfigField(
                type=float,
                default=2.5,
                description="引导强度",
                label="引导强度",
                min=0.0,
                max=20.0,
                step=0.5,
                group="params",
                order=9,
            ),
            "num_inference_steps": ConfigField(
                type=int, default=20, description="推理步数", label="推理步数", min=1, max=150, group="params", order=10
            ),
            "watermark": ConfigField(
                type=bool, default=True, description="是否添加水印", label="水印", group="params", order=11
            ),
            "custom_prompt_add": ConfigField(
                type=str,
                default="",
                description="正面提示词增强",
                label="正面增强词",
                input_type="textarea",
                rows=2,
                group="prompts",
                order=12,
            ),
            "negative_prompt_add": ConfigField(
                type=str,
                default="low quality, worst quality, blurry, text, watermark",
                description="负面提示词",
                label="负面提示词",
                input_type="textarea",
                rows=2,
                group="prompts",
                order=13,
            ),
            "artist": ConfigField(
                type=str,
                default="",
                description="艺术家风格标签（砂糖云专用）",
                label="艺术家标签",
                group="prompts",
                order=14,
            ),
            "support_img2img": ConfigField(
                type=bool, default=True, description="是否支持图生图", label="支持图生图", group="prompts", order=15
            ),
            "auto_recall_delay": ConfigField(
                type=int,
                default=0,
                description="自动撤回延时（秒）",
                label="撤回延时",
                min=0,
                max=120,
                group="prompts",
                order=16,
            ),
            "cfg": ConfigField(
                type=float,
                default=0,
                description="CFG Rescale（仅砂糖云格式生效）",
                label="CFG Rescale",
                hint="仅砂糖云格式生效",
                min=0.0,
                max=1.0,
                step=0.1,
                group="platform",
                order=20,
            ),
            "sampler": ConfigField(
                type=str,
                default="k_euler_ancestral",
                description="采样器（仅砂糖云格式生效）",
                label="采样器",
                hint="仅砂糖云格式生效",
                choices=[
                    "k_euler_ancestral",
                    "k_euler",
                    "k_dpmpp_2s_ancestral",
                    "k_dpmpp_2m_sde",
                    "k_dpmpp_2m",
                    "k_dpmpp_sde",
                ],
                group="platform",
                order=21,
            ),
            "nocache": ConfigField(
                type=int,
                default=0,
                description="是否禁用缓存（仅砂糖云格式生效）",
                label="禁用缓存",
                hint="仅砂糖云格式生效",
                min=0,
                max=1,
                group="platform",
                order=22,
            ),
            "noise_schedule": ConfigField(
                type=str,
                default="karras",
                description="噪声调度方案（仅砂糖云格式生效）",
                label="噪声调度",
                hint="仅砂糖云格式生效",
                choices=["karras", "native", "exponential", "polyexponential"],
                group="platform",
                order=23,
            ),
        },
        "models.model5": {
            "name": ConfigField(
                type=str,
                default="Sawata/Qwen-image-2512-Anime",
                description="模型显示名称",
                label="模型名称",
                group="connection",
                order=1,
            ),
            "base_url": ConfigField(
                type=str,
                default="https://api-inference.modelscope.cn/v1",
                description="API服务地址",
                label="API地址",
                required=True,
                group="connection",
                order=2,
            ),
            "api_key": ConfigField(
                type=str,
                default="Bearer YOUR_MODELSCOPE_TOKEN",
                description="API密钥，格式：Bearer xxx",
                label="API密钥",
                input_type="text",
                required=True,
                group="connection",
                order=3,
            ),
            "format": ConfigField(
                type=str,
                default="modelscope",
                description="API格式",
                label="API格式",
                choices=[
                    "openai",
                    "openai-chat",
                    "gemini",
                    "doubao",
                    "modelscope",
                    "shatangyun",
                    "mengyuai",
                    "zai",
                    "comfyui",
                ],
                required=True,
                group="connection",
                order=4,
            ),
            "model": ConfigField(
                type=str,
                default="Sawata/Qwen-image-2512-Anime",
                description="模型标识",
                label="模型标识",
                required=True,
                group="connection",
                order=5,
            ),
            "fixed_size_enabled": ConfigField(
                type=bool, default=False, description="是否固定图片尺寸", label="固定尺寸", group="params", order=6
            ),
            "default_size": ConfigField(
                type=str, default="1024x1024", description="默认图片尺寸", label="默认尺寸", group="params", order=7
            ),
            "seed": ConfigField(
                type=int,
                default=-1,
                description="随机种子",
                label="随机种子",
                min=-1,
                max=2147483647,
                group="params",
                order=8,
            ),
            "guidance_scale": ConfigField(
                type=float,
                default=2.5,
                description="引导强度",
                label="引导强度",
                min=0.0,
                max=20.0,
                step=0.5,
                group="params",
                order=9,
            ),
            "num_inference_steps": ConfigField(
                type=int, default=20, description="推理步数", label="推理步数", min=1, max=150, group="params", order=10
            ),
            "watermark": ConfigField(
                type=bool, default=True, description="是否添加水印", label="水印", group="params", order=11
            ),
            "custom_prompt_add": ConfigField(
                type=str,
                default="",
                description="正面提示词增强",
                label="正面增强词",
                input_type="textarea",
                rows=2,
                group="prompts",
                order=12,
            ),
            "negative_prompt_add": ConfigField(
                type=str,
                default="low quality, worst quality, blurry, text, watermark",
                description="负面提示词",
                label="负面提示词",
                input_type="textarea",
                rows=2,
                group="prompts",
                order=13,
            ),
            "artist": ConfigField(
                type=str,
                default="",
                description="艺术家风格标签（砂糖云专用）",
                label="艺术家标签",
                group="prompts",
                order=14,
            ),
            "support_img2img": ConfigField(
                type=bool, default=True, description="是否支持图生图", label="支持图生图", group="prompts", order=15
            ),
            "auto_recall_delay": ConfigField(
                type=int,
                default=0,
                description="自动撤回延时（秒）",
                label="撤回延时",
                min=0,
                max=120,
                group="prompts",
                order=16,
            ),
            "cfg": ConfigField(
                type=float,
                default=0,
                description="CFG Rescale（仅砂糖云格式生效）",
                label="CFG Rescale",
                hint="仅砂糖云格式生效",
                min=0.0,
                max=1.0,
                step=0.1,
                group="platform",
                order=20,
            ),
            "sampler": ConfigField(
                type=str,
                default="k_euler_ancestral",
                description="采样器（仅砂糖云格式生效）",
                label="采样器",
                hint="仅砂糖云格式生效",
                choices=[
                    "k_euler_ancestral",
                    "k_euler",
                    "k_dpmpp_2s_ancestral",
                    "k_dpmpp_2m_sde",
                    "k_dpmpp_2m",
                    "k_dpmpp_sde",
                ],
                group="platform",
                order=21,
            ),
            "nocache": ConfigField(
                type=int,
                default=0,
                description="是否禁用缓存（仅砂糖云格式生效）",
                label="禁用缓存",
                hint="仅砂糖云格式生效",
                min=0,
                max=1,
                group="platform",
                order=22,
            ),
            "noise_schedule": ConfigField(
                type=str,
                default="karras",
                description="噪声调度方案（仅砂糖云格式生效）",
                label="噪声调度",
                hint="仅砂糖云格式生效",
                choices=["karras", "native", "exponential", "polyexponential"],
                group="platform",
                order=23,
            ),
        },
    }

    # ---- 模型字段模板（用于动态注入） ----
    # 这是一个类级别的「字段工厂」，_inject_dynamic_config_layout 会用它来为新模型克隆字段
    _MODEL_FIELD_TEMPLATE: Dict[str, Any] = {
        "name": {
            "type": str,
            "default": "新模型",
            "group": "connection",
            "order": 1,
            "label": "模型名称",
            "description": "模型的显示名称",
        },
        "base_url": {
            "type": str,
            "default": "https://api-inference.modelscope.cn/v1",
            "required": True,
            "group": "connection",
            "order": 2,
            "label": "API 地址",
            "description": "推理 API 的 Base URL",
        },
        "api_key": {
            "type": str,
            "default": "Bearer xxxxxx",
            "input_type": "text",
            "required": True,
            "group": "connection",
            "order": 3,
            "label": "API Key",
            "description": "API 鉴权密钥，Bearer token 格式",
        },
        "format": {
            "type": str,
            "default": "openai",
            "choices": [
                "openai",
                "openai-chat",
                "gemini",
                "doubao",
                "modelscope",
                "shatangyun",
                "mengyuai",
                "zai",
                "comfyui",
            ],
            "required": True,
            "group": "connection",
            "order": 4,
            "label": "接口格式",
            "description": "API 接口类型/格式",
        },
        "model": {
            "type": str,
            "default": "",
            "required": True,
            "group": "connection",
            "order": 5,
            "label": "模型 ID",
            "description": "模型名称或 ID，如 cancel13/liaocao",
        },
        "fixed_size_enabled": {
            "type": bool,
            "default": False,
            "group": "params",
            "order": 6,
            "label": "固定尺寸",
            "description": "是否强制使用 default_size 指定的固定分辨率",
        },
        "default_size": {
            "type": str,
            "default": "1024x1024",
            "group": "params",
            "order": 7,
            "label": "默认尺寸",
            "description": "图片默认分辨率，格式为 宽x高",
        },
        "seed": {
            "type": int,
            "default": -1,
            "min": -1,
            "max": 2147483647,
            "group": "params",
            "order": 8,
            "label": "随机种子",
            "description": "生成种子，-1 为随机",
        },
        "guidance_scale": {
            "type": float,
            "default": 2.5,
            "min": 0.0,
            "max": 20.0,
            "step": 0.5,
            "group": "params",
            "order": 9,
            "label": "引导强度",
            "description": "提示词引导强度（CFG Scale）",
        },
        "num_inference_steps": {
            "type": int,
            "default": 20,
            "min": 1,
            "max": 150,
            "group": "params",
            "order": 10,
            "label": "推理步数",
            "description": "扩散推理步数，越高越精细但越慢",
        },
        "watermark": {
            "type": bool,
            "default": True,
            "group": "params",
            "order": 11,
            "label": "水印",
            "description": "是否为生成图片加水印",
        },
        "custom_prompt_add": {
            "type": str,
            "default": "",
            "input_type": "textarea",
            "rows": 2,
            "group": "prompts",
            "order": 12,
            "label": "正面增强词",
            "description": "正面提示词增强，自动添加到用户描述后",
        },
        "negative_prompt_add": {
            "type": str,
            "default": "Pornography,nudity,lowres, bad anatomy, bad hands, text, error",
            "input_type": "textarea",
            "rows": 2,
            "group": "prompts",
            "order": 13,
            "label": "负面提示词",
            "description": "负面提示词，避免不良内容。豆包/Gemini 格式不支持此参数可留空",
        },
        "artist": {
            "type": str,
            "default": "",
            "group": "prompts",
            "order": 14,
            "label": "艺术家标签",
            "description": "艺术家风格标签（砂糖云专用）。留空则不添加",
        },
        "support_img2img": {
            "type": bool,
            "default": True,
            "group": "prompts",
            "order": 15,
            "label": "支持图生图",
            "description": "该模型是否支持图生图功能。设为false时会自动降级为文生图",
        },
        "auto_recall_delay": {
            "type": int,
            "default": 0,
            "min": 0,
            "max": 120,
            "hint": "需先在「自动撤回配置」中开启总开关",
            "group": "prompts",
            "order": 16,
            "label": "撤回延时",
            "description": "自动撤回延时（秒）。大于0时启用撤回，0表示不撤回",
        },
        "access_mode": {
            "type": str,
            "default": "blacklist",
            "choices": ["blacklist", "whitelist"],
            "group": "prompts",
            "order": 17,
            "label": "聊天流模式",
            "description": "该模型的聊天流访问模式。blacklist=黑名单（默认，名单内禁用）；whitelist=白名单（仅名单内允许）",
        },
        "access_list": {
            "type": list,
            "default": [],
            "item_type": "string",
            "placeholder": "qq:1919810:group",
            "group": "prompts",
            "order": 18,
            "label": "聊天流列表",
            "description": "该模型的聊天流列表。格式示例：qq:114514:private、qq:1919810:group",
        },
        "cfg": {
            "type": float,
            "default": 0,
            "min": 0.0,
            "max": 1.0,
            "step": 0.1,
            "hint": "仅砂糖云格式生效",
            "group": "platform",
            "order": 20,
            "label": "CFG Rescale",
            "description": "砂糖云专用：CFG Rescale 参数",
        },
        "sampler": {
            "type": str,
            "default": "k_euler_ancestral",
            "choices": [
                "k_euler_ancestral",
                "k_euler",
                "k_dpmpp_2s_ancestral",
                "k_dpmpp_2m_sde",
                "k_dpmpp_2m",
                "k_dpmpp_sde",
            ],
            "hint": "仅砂糖云格式生效",
            "group": "platform",
            "order": 21,
            "label": "采样器",
            "description": "砂糖云专用：采样器名称",
        },
        "nocache": {
            "type": int,
            "default": 0,
            "min": 0,
            "max": 1,
            "hint": "仅砂糖云格式生效",
            "group": "platform",
            "order": 22,
            "label": "禁用缓存",
            "description": "砂糖云专用：是否禁用缓存，0=使用缓存，1=禁用",
        },
        "noise_schedule": {
            "type": str,
            "default": "karras",
            "choices": ["karras", "native", "exponential", "polyexponential"],
            "hint": "仅砂糖云格式生效",
            "group": "platform",
            "order": 23,
            "label": "噪声调度",
            "description": "砂糖云专用：噪声调度方案",
        },
    }

    def _inject_dynamic_config_layout(self, raw_config: dict[str, Any] | None) -> None:
        """
        根据 config.toml 里的实际内容，动态更新 WEBUI 布局。

        这个方法会做三件事：
        1. 找出 config.toml 里所有 [models.xxx] 节的 key
        2. 为每个模型生成对应的 config_schema 字段、config_section_descriptions 元数据
           和 config_layout 里 models 标签页的 sections 列表
        3. 对 styles / style_aliases 也做同样的动态读取，
           确保 WEBUI 能显示用户在 toml 里自定义的风格
        4. 动态注入 wardrobe.outfits.<outfit_id>，让 WebUI 能编辑每套穿搭

        注意：修改的是实例属性，会覆盖类属性，不影响其他实例。
        调用时机：super().__init__() 之前，确保 WEBUI 读 self.config_schema 时已是最新版本。
        """
        import copy

        # BasePlugin / PluginBase 在类型标注里把部分配置项定义成 @property。
        # 但本插件需要在 super().__init__() 之前动态覆写这些“实例属性”，让 WebUI
        # 能读取到最新的 schema/layout。
        # 这里用 Any 规避静态类型检查对 property setter 的误报（不影响运行时）。
        self_any: Any = self

        def _safe_float(value: Any, default: float) -> float:
            """把 value 尽量转成 float；失败则回退 default。"""
            try:
                return float(value)
            except (TypeError, ValueError):
                return default

        def _safe_str_list(value: Any) -> list[str]:
            """把 value 尽量转成 list[str]；非 list 则返回空列表。"""
            if not isinstance(value, list):
                return []
            return [str(x) for x in value]

        # ── 1. 深拷贝类属性，变成实例属性（避免修改影响类本身）──
        self_any.config_schema = copy.deepcopy(type(self).config_schema)
        self_any.config_section_descriptions = copy.deepcopy(type(self).config_section_descriptions)
        # config_layout 内部有 tabs 列表，需要深拷贝
        self_any.config_layout = copy.deepcopy(type(self).config_layout)

        # ── 2. 收集 config.toml 里实际存在的模型 key ──
        model_keys: list[str] = []  # 例如 ["model1", "model2", "model3"]
        model_names: dict[str, str] = {}  # key -> name，用于 Section 标题
        if raw_config and isinstance(raw_config.get("models"), dict):
            for key, val in raw_config["models"].items():
                if isinstance(val, dict):  # 过滤掉非节的标量值
                    model_keys.append(key)
                    model_names[key] = val.get("name", key)  # 没有 name 就用 key

        # 如果 config.toml 不存在或为空，至少保证 model1 存在（兜底）
        if not model_keys:
            model_keys = ["model1"]
            model_names["model1"] = "模型1"

        # ── 2.5 动态收集 wardrobe.outfits ──
        # 目标：
        # - config.toml 存在时：以用户实际写入的 [wardrobe.outfits.<id>] 为准
        # - config.toml 不存在/缺少 outfits 时：不注入默认服装，保持 WebUI 干净
        #   用户需要手动在 config.toml 中添加 [wardrobe.outfits.<id>] 才会显示对应小板块
        default_outfits: dict[str, dict[str, Any]] = {}

        outfit_keys: list[str] = []
        outfit_data_map: dict[str, dict[str, Any]] = {}
        if raw_config and isinstance(raw_config.get("wardrobe"), dict):
            wardrobe_cfg = raw_config.get("wardrobe", {})
            outfits_cfg = wardrobe_cfg.get("outfits")
            if isinstance(outfits_cfg, dict):
                for outfit_id, outfit_val in outfits_cfg.items():
                    if isinstance(outfit_val, dict):
                        outfit_keys.append(str(outfit_id))
                        outfit_data_map[str(outfit_id)] = outfit_val

        if not outfit_keys:
            # 不再注入默认服装：如果 config.toml 中没有 [wardrobe.outfits] 配置，则保持空列表
            # 用户需要手动在 config.toml 中添加服装配置才会显示对应的 WebUI 小板块
            outfit_keys = []
            outfit_data_map = {}

        # ── 3. 动态注入每个模型的 config_schema / config_section_descriptions ──
        base_order = 13  # models.model1 的 order 是 13，后续模型依次递增
        for idx, key in enumerate(model_keys):
            section_key = f"models.{key}"
            display_name = model_names.get(key, key)

            # 3a. 注入 config_section_descriptions（Section 元数据）
            self_any.config_section_descriptions[section_key] = ConfigSection(
                title=display_name,  # 用模型 name 字段作为标题
                icon="box",
                order=base_order + idx,
            )

            # 3b. 注入 config_schema（字段定义）
            # 如果已经有这个节（比如 model1 已在类属性里），跳过，不覆盖已精心定制的字段
            if section_key not in self_any.config_schema:
                # 从模板构造 ConfigField 字典
                fields: Dict[str, ConfigField] = {}
                for field_name, spec in self._MODEL_FIELD_TEMPLATE.items():
                    spec_copy = dict(spec)  # 浅拷贝，避免修改模板
                    # 用 toml 里的实际值作为默认值（如果有）
                    if raw_config and isinstance(raw_config.get("models"), dict):
                        model_data = raw_config["models"].get(key, {})
                        if field_name in model_data:
                            spec_copy["default"] = model_data[field_name]
                    # 重新构造，把所有支持的参数传进去
                    field_kwargs: Dict[str, Any] = {"type": spec_copy["type"], "default": spec_copy["default"]}
                    for extra_key in (
                        "label",
                        "description",
                        "hint",
                        "input_type",
                        "rows",
                        "choices",
                        "placeholder",
                        "item_type",
                        "min",
                        "max",
                        "step",
                        "group",
                        "order",
                        "required",
                        "disabled",
                    ):
                        if extra_key in spec_copy:
                            field_kwargs[extra_key] = spec_copy[extra_key]
                    fields[field_name] = ConfigField(**field_kwargs)
                self_any.config_schema[section_key] = fields
            else:
                # model1-5（或已存在的节）已在类属性里定义好了，
                # 用 config.toml 里的实际值覆盖 ConfigField.default，
                # 否则 WebUI 会显示类属性里的硬编码模板默认值而非用户实际配置
                model_data: dict[str, Any] = {}
                if raw_config and isinstance(raw_config.get("models"), dict):
                    loaded_model_data = raw_config["models"].get(key, {})
                    if isinstance(loaded_model_data, dict):
                        model_data = loaded_model_data

                existing_fields = self_any.config_schema[section_key]
                if isinstance(existing_fields, dict):
                    for field_name, spec in self._MODEL_FIELD_TEMPLATE.items():
                        if field_name in existing_fields:
                            continue

                        spec_copy = dict(spec)
                        if field_name in model_data:
                            spec_copy["default"] = model_data[field_name]

                        field_kwargs: Dict[str, Any] = {
                            "type": spec_copy["type"],
                            "default": spec_copy["default"],
                        }
                        for extra_key in (
                            "label",
                            "description",
                            "hint",
                            "input_type",
                            "rows",
                            "choices",
                            "placeholder",
                            "item_type",
                            "min",
                            "max",
                            "step",
                            "group",
                            "order",
                            "required",
                            "disabled",
                        ):
                            if extra_key in spec_copy:
                                field_kwargs[extra_key] = spec_copy[extra_key]

                        existing_fields[field_name] = ConfigField(**field_kwargs)

                    for field_name, field_obj in existing_fields.items():
                        if isinstance(field_obj, ConfigField) and field_name in model_data:
                            field_obj.default = model_data[field_name]

        # ── 4. 更新 config_layout 里 models 标签页的 sections ──
        # 找到 id="models" 的 tab，重写其 sections 列表
        for tab in self_any.config_layout.tabs:
            if tab.id == "models":
                tab.sections = ["access_control", "models"] + [f"models.{k}" for k in model_keys]
                break

        # ── 4.5 更新 config_layout 里 features 标签页的 sections（插入 wardrobe + outfits）──
        for tab in self_any.config_layout.tabs:
            if tab.id == "features":
                # 去掉上一次注入的动态节，避免重复
                base_sections = [
                    s for s in list(tab.sections) if s != "wardrobe" and not str(s).startswith("wardrobe.outfits.")
                ]
                insert_at = base_sections.index("selfie") + 1 if "selfie" in base_sections else 0
                dynamic_sections = ["wardrobe"] + [f"wardrobe.outfits.{k}" for k in outfit_keys]
                tab.sections = base_sections[:insert_at] + dynamic_sections + base_sections[insert_at:]
                break

        # ── 4.6 注入 wardrobe.outfits.<id> 的 config_schema / config_section_descriptions ──
        wardrobe_section_base_order = 50
        for idx, outfit_id in enumerate(outfit_keys):
            section_key = f"wardrobe.outfits.{outfit_id}"
            raw_outfit = outfit_data_map.get(outfit_id, {})

            outfit_display_name = raw_outfit.get("name", outfit_id)
            if not isinstance(outfit_display_name, str) or not outfit_display_name.strip():
                outfit_display_name = outfit_id

            self_any.config_section_descriptions[section_key] = ConfigSection(
                title=str(outfit_display_name),
                description="配置一套穿搭（仅服装标签）。prompt 建议用英文逗号分隔，例如：hoodie, jeans, sneakers",
                icon="shirt",
                order=wardrobe_section_base_order + idx,
            )

            # 构造字段默认值：先用内置默认，再用 config.toml 覆盖（如果有）
            merged_defaults: dict[str, Any] = {}
            if outfit_id in default_outfits:
                merged_defaults.update(default_outfits[outfit_id])
            if isinstance(raw_outfit, dict):
                merged_defaults.update(raw_outfit)

            self_any.config_schema[section_key] = {
                "enabled": ConfigField(
                    type=bool,
                    default=bool(merged_defaults.get("enabled", True)),
                    description="是否启用该穿搭",
                    label="启用",
                    order=1,
                ),
                "name": ConfigField(
                    type=str,
                    default=str(merged_defaults.get("name", outfit_id)),
                    description="穿搭显示名称（用于 WebUI 列表/标题）",
                    label="名称",
                    placeholder="日常休闲",
                    order=2,
                ),
                "prompt": ConfigField(
                    type=str,
                    default=str(merged_defaults.get("prompt", "")),
                    description="穿搭提示词（只写衣服/饰品等标签；英文逗号分隔；不要写人物/场景/动作）",
                    label="穿搭标签",
                    input_type="textarea",
                    rows=4,
                    placeholder="hoodie, jeans, sneakers",
                    order=3,
                ),
                "base_weight": ConfigField(
                    type=float,
                    default=_safe_float(merged_defaults.get("base_weight"), 0.0),
                    description="基础权重：在没有临时覆盖时，该穿搭被选中的倾向（0=几乎不会选）",
                    label="基础权重",
                    min=0.0,
                    step=0.1,
                    order=4,
                ),
                "override_weight": ConfigField(
                    type=float,
                    default=_safe_float(merged_defaults.get("override_weight"), 0.0),
                    description="覆盖权重：在“临时覆盖”生效时，该穿搭被选中的倾向（0=几乎不会选）",
                    label="覆盖权重",
                    min=0.0,
                    step=0.1,
                    order=5,
                ),
                "allowed_activity_types": ConfigField(
                    type=list,
                    default=_safe_str_list(merged_defaults.get("allowed_activity_types")),
                    description="允许的活动类型列表（留空表示不限制）。例如：['sleeping', 'exercising']",
                    label="允许活动类型",
                    item_type="string",
                    placeholder="sleeping",
                    order=6,
                ),
                "forbidden_activity_types": ConfigField(
                    type=list,
                    default=_safe_str_list(merged_defaults.get("forbidden_activity_types")),
                    description="禁止的活动类型列表（留空表示不禁止）。如果同时命中允许/禁止，以禁止为准",
                    label="禁止活动类型",
                    item_type="string",
                    placeholder="work",
                    order=7,
                ),
            }

        # ── 5. 动态读取 styles / style_aliases，更新 config_schema ──
        # styles：每个风格 key 对应一个 ConfigField（textarea 输入提示词）
        if raw_config and isinstance(raw_config.get("styles"), dict):
            styles_schema: Dict[str, ConfigField] = {}
            for idx, (style_key, style_val) in enumerate(raw_config["styles"].items()):
                styles_schema[style_key] = ConfigField(
                    type=str,
                    default=style_val if isinstance(style_val, str) else "",
                    description=f"{style_key} 风格的提示词",
                    label=style_key,
                    input_type="textarea",
                    rows=3,
                    order=idx + 1,
                )
            if styles_schema:
                self_any.config_schema["styles"] = styles_schema

        # style_aliases：每个别名 key 对应一个 ConfigField（普通文本输入）
        if raw_config and isinstance(raw_config.get("style_aliases"), dict):
            aliases_schema: Dict[str, ConfigField] = {}
            for idx, (alias_key, alias_val) in enumerate(raw_config["style_aliases"].items()):
                aliases_schema[alias_key] = ConfigField(
                    type=str,
                    default=alias_val if isinstance(alias_val, str) else alias_key,
                    description=f"{alias_key} 风格的中文别名，支持多别名用逗号分隔",
                    label=f"{alias_key} 别名",
                    placeholder="别名1,别名2",
                    order=idx + 1,
                )
            if aliases_schema:
                self_any.config_schema["style_aliases"] = aliases_schema

        logger.info(
            "WEBUI 动态布局注入完成：%s 个模型 %s，%s 套穿搭，%s 个风格",
            len(model_keys),
            model_keys,
            len(outfit_keys),
            len(raw_config.get("styles", {})) if raw_config else 0,
        )

    def __init__(self, plugin_dir: str):
        """初始化插件"""
        # 在父类初始化前读取原始配置文件，用于动态构建 WebUI 模型/风格布局
        config_path = os.path.join(plugin_dir, self.config_file_name)
        original_config: Optional[Dict[str, Any]] = None
        if os.path.exists(config_path):
            if tomllib is None:
                logger.warning("当前 Python 环境不支持 tomllib，跳过预读取配置：%s", config_path)
            else:
                try:
                    with open(config_path, "rb") as f:
                        original_config = tomllib.load(f)
                    logger.debug("预读取原始配置文件成功: %s", config_path)
                except (OSError, _TOMLDecodeError) as exc:
                    logger.warning("预读取原始配置失败，将使用默认布局: %s", exc)

        # ── 动态注入：根据 config.toml 里的实际模型/风格，更新 WEBUI 布局 ──
        self._inject_dynamic_config_layout(original_config)

        # 先调用父类初始化，这会加载配置并可能触发 MaiBot 迁移
        super().__init__(plugin_dir)

        # 初始化自动自拍任务
        self._auto_selfie_task = None
        self._auto_selfie_pending = False
        if self.get_config("auto_selfie.enabled", False):
            from .core.selfie import AutoSelfieTask

            self._auto_selfie_task = AutoSelfieTask(self)
            try:
                asyncio.create_task(self._start_auto_selfie_after_delay())
            except RuntimeError:
                # 事件循环未就绪，标记待启动，在首次组件执行时懒启动
                self._auto_selfie_pending = True
                logger.info("事件循环未就绪，自动自拍任务将在首次执行时懒启动")

        # --- 日程管理器初始化 ---
        self._schedule_gen_task: Optional[asyncio.Task] = None
        self._schedule_pending = False
        try:
            asyncio.create_task(self._start_schedule_gen_after_delay())
        except RuntimeError:
            self._schedule_pending = True

    async def _start_auto_selfie_after_delay(self):
        """延迟启动自动自拍任务"""
        await asyncio.sleep(15)
        if self._auto_selfie_task:
            await self._auto_selfie_task.start()
            self._auto_selfie_pending = False

    def try_start_auto_selfie(self):
        """尝试懒启动自动自拍任务（供组件首次执行时调用）"""
        if not self._auto_selfie_pending or not self._auto_selfie_task:
            return
        try:
            asyncio.create_task(self._start_auto_selfie_after_delay())
            self._auto_selfie_pending = False
        except RuntimeError as exc:
            logger.debug("自动自拍懒启动失败，等待下次重试: %s", exc)

    def try_start_schedule_gen(self):
        """尝试懒启动日程后台任务。"""
        if not self._schedule_pending:
            return
        try:
            asyncio.create_task(self._start_schedule_gen_after_delay())
            self._schedule_pending = False
        except RuntimeError as exc:
            logger.debug("日程任务懒启动失败，等待下次重试: %s", exc)

    async def _start_schedule_gen_after_delay(self) -> None:
        """延迟15秒后初始化日程管理器并确保今日有日程。"""
        await asyncio.sleep(15)
        try:
            from .core.schedule import get_schedule_manager

            mgr = get_schedule_manager()
            await mgr.ensure_db_initialized()
            await mgr.ensure_today_schedule(plugin=self)
            if self.get_config("schedule.auto_generate_enabled", True):
                self._schedule_gen_task = asyncio.create_task(self._schedule_gen_loop())
        except Exception as e:
            logger.error("[SelfiePainter] 日程初始化失败: %s", e, exc_info=True)

    async def _schedule_gen_loop(self) -> None:
        """每日在指定时间重新生成日程。"""
        import datetime
        import random

        while True:
            try:
                gen_time_str = self.get_config("schedule.auto_generate_time", "06:30")
                now = datetime.datetime.now()
                hour, minute = map(int, gen_time_str.split(":"))
                target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if target <= now:
                    target += datetime.timedelta(days=1)
                jitter = random.randint(0, 60)
                wait_seconds = (target - now).total_seconds() + jitter
                await asyncio.sleep(wait_seconds)

                from .core.schedule import get_schedule_manager

                mgr = get_schedule_manager()
                await mgr.ensure_today_schedule(plugin=self)
                logger.info("[SelfiePainter] 每日日程生成完成")
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error("[SelfiePainter] 日程生成循环异常: %s", e, exc_info=True)
                await asyncio.sleep(300)

    async def on_plugin_unload(self) -> None:
        """插件卸载时停止后台任务。"""
        await self._stop_auto_selfie_task()
        await self._stop_schedule_gen_task()

    async def _stop_auto_selfie_task(self) -> None:
        """停止自动自拍后台任务，避免重载后残留。"""
        if not self._auto_selfie_task:
            self._auto_selfie_pending = False
            return

        try:
            await self._auto_selfie_task.stop()
        except Exception as exc:
            logger.warning("停止自动自拍任务失败: %s", exc, exc_info=True)
        finally:
            self._auto_selfie_task = None
            self._auto_selfie_pending = False

    async def _stop_schedule_gen_task(self) -> None:
        """停止日程后台任务。"""
        if self._schedule_gen_task and not self._schedule_gen_task.done():
            self._schedule_gen_task.cancel()
            try:
                await self._schedule_gen_task
            except asyncio.CancelledError:
                pass
        self._schedule_gen_task = None
        self._schedule_pending = False

    def get_plugin_components(self) -> List[Tuple[ComponentInfo, Type]]:
        """返回插件包含的组件列表"""
        enable_unified_generation = self.get_config("components.enable_unified_generation", True)
        enable_pic_command = self.get_config("components.enable_pic_command", True)
        enable_pic_config = self.get_config("components.enable_pic_config", True)
        enable_pic_style = self.get_config("components.enable_pic_style", True)
        components = []

        if enable_unified_generation:
            components.append((SelfiePainterAction.get_action_info(), SelfiePainterAction))

        # 优先注册更具体的配置管理命令，避免被通用风格命令拦截
        if enable_pic_config:
            components.append((PicConfigCommand.get_command_info(), PicConfigCommand))

        if enable_pic_style:
            components.append((PicStyleCommand.get_command_info(), PicStyleCommand))

        # 最后注册通用的风格命令，以免覆盖特定命令
        if enable_pic_command:
            components.append((WardrobeCommand.get_command_info(), WardrobeCommand))
            components.append((PicGenerationCommand.get_command_info(), PicGenerationCommand))

        # 注册 /schedule 命令
        components.append((ScheduleCommand.get_command_info(), ScheduleCommand))
        # 注册日程注入 EventHandler
        if self.get_config("schedule_inject.enabled", True):
            components.append((ScheduleInjectHandler.get_handler_info(), ScheduleInjectHandler))

        return components
