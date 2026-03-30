"""selfie_painter_v2 共享常量"""

# Base64 图片格式前缀，用于区分 base64 数据与 URL
# JPEG: /9j/  PNG: iVBORw  WEBP: UklGR  GIF: R0lGOD
BASE64_IMAGE_PREFIXES = ("iVBORw", "/9j/", "UklGR", "R0lGOD")

# 自拍通用手部质量负面提示词（所有自拍风格共用）
# 只保留最常用、最有效的 SD 标签，避免重复堆叠。
SELFIE_HAND_NEGATIVE = "bad hands, extra digits, fewer digits, extra arms, bad anatomy"

# 标准自拍专用：强调前摄自拍感，不要把设备本体画进画面
ANTI_DUAL_PHONE_PROMPT = "phone, smartphone, camera, device, selfie stick"

# 第三人称照片专用：只防止手持拍摄设备出现在画面主体上
ANTI_CAMERA_DEVICE_PROMPT = "phone, smartphone, selfie stick"

# 对镜自拍专用：避免镜子崩坏效果（人从镜子里出来/镜子变传送门）
ANTI_MIRROR_PORTAL_PROMPT = "person coming out of mirror, mirror portal, breaking fourth wall, extra reflections, deformed reflection, mirror as window"

VALID_SELFIE_STYLES = {"standard", "mirror", "photo"}

SELFIE_STYLE_DISPLAY_NAMES = {
    "standard": "标准自拍",
    "mirror": "对镜自拍",
    "photo": "第三人称照片",
}


def normalize_selfie_style(style: object, fallback: str = "standard") -> str:
    """标准化自拍风格值，异常值自动回退。"""
    normalized_fallback = str(fallback).strip().lower()
    if normalized_fallback not in VALID_SELFIE_STYLES:
        normalized_fallback = "standard"

    if style is None:
        return normalized_fallback

    normalized = str(style).strip().lower()
    if normalized in VALID_SELFIE_STYLES:
        return normalized
    return normalized_fallback


def get_selfie_style_display_name(style: object, fallback: str = "standard") -> str:
    """返回自拍风格的中文显示名。"""
    normalized = normalize_selfie_style(style, fallback)
    return SELFIE_STYLE_DISPLAY_NAMES.get(normalized, SELFIE_STYLE_DISPLAY_NAMES["standard"])


# 向后兼容别名
ANTI_DUAL_HANDS_PROMPT = f"{SELFIE_HAND_NEGATIVE}, {ANTI_DUAL_PHONE_PROMPT}"
