"""selfie_painter_v2 共享常量"""

# Base64 图片格式前缀，用于区分 base64 数据与 URL
# JPEG: /9j/  PNG: iVBORw  WEBP: UklGR  GIF: R0lGOD
BASE64_IMAGE_PREFIXES = ("iVBORw", "/9j/", "UklGR", "R0lGOD")

# 自拍通用手部质量负面提示词（所有自拍风格共用）
SELFIE_HAND_NEGATIVE = (
    # 手指数量
    "extra fingers, missing fingers, fused fingers, "
    # 手部整体质量
    "bad hands, mutated hands, "
    # 多余肢体
    "extra hands, extra arms, multiple hands, "
    # 手指形态
    "interlocked fingers, "
    # 通用解剖
    "bad anatomy, anatomical errors, "
    # 通用绘制质量
    "poorly drawn hands, poorly drawn fingers, "
    "wrong hand proportions"
)

# 标准自拍专用：防止生成双手拿手机等不自然姿态
ANTI_DUAL_PHONE_PROMPT = (
    "two phones, dual phones, camera in both hands, "
    "holding phone with both hands, "
    "both hands holding phone, "
    "both hands holding device, "
    "two hands gripping phone, "
    "selfie stick"
)

# 第三人称照片专用：禁止拍照设备出现在画面中
ANTI_CAMERA_DEVICE_PROMPT = (
    "phone in hand, holding phone, holding camera, "
    "camera in hand, visible camera, visible phone, "
    "selfie stick, recording device, "
    "smartphone in frame, camera in frame"
)

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
