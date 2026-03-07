import base64
import urllib.request
import re
import os
from typing import Optional, Tuple, List

from src.common.logger import get_logger
from maim_message import Seg

logger = get_logger("mais_art.image")

class ImageProcessor:
    """图片处理工具类"""

    def __init__(self, action_instance):
        self.action = action_instance
        self.log_prefix = action_instance.log_prefix

    def _get_processed_plain_text(self) -> str:
        """获取当前消息的 processed_plain_text，兼容 Action 和 Command 组件"""
        text = ''
        if hasattr(self.action, 'action_message') and self.action.action_message:
            text = getattr(self.action.action_message, 'processed_plain_text', '') or ''
        elif hasattr(self.action, 'message') and self.action.message:
            text = getattr(self.action.message, 'processed_plain_text', '') or ''
        return text

    async def get_recent_image(self) -> Optional[str]:
        """获取最近的图片

        查找顺序：
        1. 从当前消息的 message_segment 中直接提取（Command 组件的主要路径）
        2. 从 processed_plain_text 提取 picid → 查 Images 数据库 → 读文件（Action 组件的主要路径）
        """
        try:
            # 方法1：从当前消息的 message_segment 中检索
            message_segments = None
            if hasattr(self.action, 'message') and hasattr(self.action.message, 'message_segment'):
                # Command组件
                message_segments = self.action.message.message_segment
            elif hasattr(self.action, 'action_message') and hasattr(self.action.action_message, 'message_segment'):
                # Action组件
                message_segments = self.action.action_message.message_segment

            if message_segments:
                emoji_base64_list = self.find_and_return_emoji_in_message(message_segments)
                if emoji_base64_list:
                    logger.info(f"{self.log_prefix} 从 message_segment 中找到图片")
                    return emoji_base64_list[0]

            # 方法2：从 processed_plain_text 提取 picid，查 Images 数据库读文件
            from src.common.database.database_model import Images

            text = self._get_processed_plain_text()
            picid = None
            if text:
                match = re.search(r'picid:([a-zA-Z0-9-]+)', text)
                if match:
                    picid = match.group(1)
                    logger.info(f"{self.log_prefix} 从消息文本提取到 picid: {picid}")

            if picid:
                logger.info(f"{self.log_prefix} 尝试通过 picid 获取图片路径: {picid}")
                image = Images.get_or_none(Images.image_id == picid)

                if image and hasattr(image, 'path') and image.path:
                    image_path = image.path
                    try:
                        if os.path.exists(image_path):
                            with open(image_path, 'rb') as f:
                                image_data = f.read()
                            image_base64 = base64.b64encode(image_data).decode('utf-8')
                            logger.info(f"{self.log_prefix} 通过 picid 加载图片成功, 路径: {image_path}")
                            return image_base64
                        else:
                            logger.warning(f"{self.log_prefix} 图片文件不存在: {image_path}")
                    except Exception as e:
                        logger.error(f"{self.log_prefix} 读取图片文件失败: {e!r}")

            logger.warning(f"{self.log_prefix} 未找到可用的图片")
            return None

        except Exception as e:
            logger.error(f"{self.log_prefix} 获取图片失败: {e!r}", exc_info=True)
            return None

    def find_and_return_emoji_in_message(self, message_segments) -> List[str]:
        """从消息中查找并返回表情包/图片的base64数据列表"""
        emoji_base64_list = []

        # 处理单个Seg对象的情况
        if isinstance(message_segments, Seg):
            if message_segments.type == "emoji":
                emoji_base64_list.append(message_segments.data)
            elif message_segments.type == "image":
                emoji_base64_list.append(message_segments.data)
            elif message_segments.type == "seglist":
                emoji_base64_list.extend(self.find_and_return_emoji_in_message(message_segments.data))
            return emoji_base64_list

        # 处理Seg列表的情况
        for seg in message_segments:
            if seg.type == "emoji":
                emoji_base64_list.append(seg.data)
            elif seg.type == "image":
                emoji_base64_list.append(seg.data)
            elif seg.type == "seglist":
                emoji_base64_list.extend(self.find_and_return_emoji_in_message(seg.data))
        return emoji_base64_list

    def download_and_encode_base64(self, image_url: str, proxy_url: str = None) -> Tuple[bool, str]:
        """下载图片或处理Base64数据URL

        Args:
            image_url: 图片 URL 或 data:image/ 数据 URL
            proxy_url: 代理地址（如 http://127.0.0.1:7890），为空则直连
        """
        logger.info(f"{self.log_prefix} (B64) 处理图片: {image_url[:50]}...")

        try:
            # 检查是否为Base64数据URL
            if image_url.startswith('data:image/'):
                logger.info(f"{self.log_prefix} (B64) 检测到Base64数据URL")

                # 从数据URL中提取Base64部分
                if ';base64,' in image_url:
                    base64_data = image_url.split(';base64,', 1)[1]
                    logger.info(f"{self.log_prefix} (B64) 从数据URL提取Base64完成. 长度: {len(base64_data)}")
                    return True, base64_data
                else:
                    error_msg = "Base64数据URL格式不正确"
                    logger.error(f"{self.log_prefix} (B64) {error_msg}")
                    return False, error_msg
            else:
                # 处理普通HTTP URL
                if proxy_url:
                    import requests
                    logger.info(f"{self.log_prefix} (B64) 下载HTTP图片 (proxy: {proxy_url})")
                    resp = requests.get(image_url, timeout=180, proxies={"http": proxy_url, "https": proxy_url})
                    if resp.status_code == 200:
                        base64_encoded_image = base64.b64encode(resp.content).decode("utf-8")
                        logger.info(f"{self.log_prefix} (B64) 图片下载编码完成. Base64长度: {len(base64_encoded_image)}")
                        return True, base64_encoded_image
                    else:
                        error_msg = f"下载图片失败 (状态: {resp.status_code})"
                        logger.error(f"{self.log_prefix} (B64) {error_msg} URL: {image_url[:30]}...")
                        return False, error_msg
                else:
                    logger.info(f"{self.log_prefix} (B64) 下载HTTP图片")
                    with urllib.request.urlopen(image_url, timeout=180) as response:
                        if response.status == 200:
                            image_bytes = response.read()
                            base64_encoded_image = base64.b64encode(image_bytes).decode("utf-8")
                            logger.info(f"{self.log_prefix} (B64) 图片下载编码完成. Base64长度: {len(base64_encoded_image)}")
                            return True, base64_encoded_image
                        else:
                            error_msg = f"下载图片失败 (状态: {response.status})"
                            logger.error(f"{self.log_prefix} (B64) {error_msg} URL: {image_url[:30]}...")
                            return False, error_msg

        except Exception as e:
            logger.error(f"{self.log_prefix} (B64) 处理图片时错误: {e!r}", exc_info=True)
            return False, f"处理图片时发生错误: {str(e)[:50]}"

    def process_api_response(self, result) -> Optional[str]:
        """统一处理API响应，提取图片数据"""
        try:
            # 如果result是字符串，直接返回
            if isinstance(result, str):
                return result

            # 如果result是字典，尝试提取图片数据
            if isinstance(result, dict):
                # 尝试多种可能的字段
                for key in ['url', 'image', 'b64_json', 'data']:
                    if key in result and result[key]:
                        return result[key]

                # 检查嵌套结构
                if 'output' in result and isinstance(result['output'], dict):
                    output = result['output']
                    for key in ['image_url', 'images']:
                        if key in output:
                            data = output[key]
                            return data[0] if isinstance(data, list) and data else data

            return None
        except Exception as e:
            logger.error(f"{self.log_prefix} 处理API响应失败: {str(e)[:50]}")
            return None
