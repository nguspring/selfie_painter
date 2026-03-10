"""ComfyUI 工作流 API 客户端

通过本地或远程 ComfyUI 实例的 HTTP API 生成图片：
- 加载工作流 JSON 模板
- 替换占位符 → 提交任务 → 轮询结果 → 下载图片

配置映射：
  base_url  → ComfyUI 服务地址（如 http://127.0.0.1:8188）
  model     → 工作流文件名（相对 workflow/ 目录）
  api_key   → 不需要，留空
  seed      → 随机种子，-1 表示自动随机

工作流占位符（在 JSON 中使用 "${xxx}" 格式）：
  ${prompt}           ← 用户提示词 + custom_prompt_add
  ${seed}             ← seed 配置值（-1 时自动随机）
  ${negative_prompt}  ← negative_prompt_add
  ${steps}            ← num_inference_steps
  ${cfg}              ← guidance_scale
  ${width}            ← 从 size 解析的宽度
  ${height}           ← 从 size 解析的高度
  ${denoise}          ← 图生图降噪强度（strength）
  ${image}            ← 图生图输入图片（自动上传）
"""

import base64
import json
import os
import random
import time
import uuid
import urllib.parse
import urllib.request
from typing import Dict, Any, Tuple, Optional

from .base_client import BaseApiClient, logger


class ComfyUIClient(BaseApiClient):
    """ComfyUI 工作流 API 客户端"""

    format_name = "comfyui"

    def _build_opener(self) -> Tuple[urllib.request.OpenerDirector, int]:
        """构建 opener（支持代理），返回 (opener, timeout)"""
        proxy_config = self._get_proxy_config()
        if proxy_config:
            proxy_handler = urllib.request.ProxyHandler({
                'http': proxy_config['http'],
                'https': proxy_config['https']
            })
            opener = urllib.request.build_opener(proxy_handler)
            timeout = proxy_config.get('timeout', 120)
        else:
            opener = urllib.request.build_opener()
            timeout = 120
        return opener, timeout

    def _make_request(
        self,
        prompt: str,
        model_config: Dict[str, Any],
        size: str,
        strength: Optional[float] = None,
        input_image_base64: Optional[str] = None
    ) -> Tuple[bool, str]:
        """通过 ComfyUI 工作流生成图片"""
        base_url = model_config.get("base_url", "http://127.0.0.1:8188").rstrip("/")
        workflow_name = model_config.get("model", "")
        seed = model_config.get("seed", -1)
        custom_prompt_add = model_config.get("custom_prompt_add", "")
        full_prompt = prompt + custom_prompt_add

        # 构建 opener（局部使用，不污染全局）
        opener, default_timeout = self._build_opener()

        # ---- 1. 定位工作流文件 ----
        if not workflow_name:
            return False, "未配置工作流文件名（model 字段）"

        if os.path.isabs(workflow_name):
            workflow_file = workflow_name
        else:
            plugin_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            workflow_file = os.path.join(plugin_dir, "workflow", workflow_name)

        if not os.path.exists(workflow_file):
            return False, f"工作流文件不存在: {workflow_file}"

        logger.info(f"{self.log_prefix} (ComfyUI) 加载工作流: {workflow_file}")

        try:
            with open(workflow_file, "r", encoding="utf-8") as f:
                workflow_template = f.read()
        except Exception as e:
            return False, f"读取工作流文件失败: {e}"

        # ---- 2. 替换占位符 ----
        if seed == -1:
            seed = random.randint(1, 10_000_000_000)

        workflow_str = workflow_template.replace('"${prompt}"', json.dumps(full_prompt))
        workflow_str = workflow_str.replace('"${seed}"', str(seed))

        # negative_prompt_add → ${negative_prompt}
        negative_prompt = model_config.get("negative_prompt_add", "")
        workflow_str = workflow_str.replace('"${negative_prompt}"', json.dumps(negative_prompt))

        # num_inference_steps → ${steps}
        steps = model_config.get("num_inference_steps", 20)
        workflow_str = workflow_str.replace('"${steps}"', str(int(steps)))

        # guidance_scale → ${cfg}
        cfg = model_config.get("guidance_scale", 7)
        workflow_str = workflow_str.replace('"${cfg}"', str(float(cfg)))

        # size → ${width} / ${height}
        try:
            w, h = size.lower().split("x")
            width, height = int(w), int(h)
        except (AttributeError, ValueError) as exc:
            logger.debug(f"{self.log_prefix} (ComfyUI) 尺寸解析失败，回退默认 1024x1024: {exc}")
            width, height = 1024, 1024
        workflow_str = workflow_str.replace('"${width}"', str(width))
        workflow_str = workflow_str.replace('"${height}"', str(height))

        # strength → ${denoise}（图生图降噪强度）
        if strength is not None:
            workflow_str = workflow_str.replace('"${denoise}"', str(float(strength)))

        # ---- 3. 图生图：上传图片并替换 ${image} ----
        if input_image_base64 and '"${image}"' in workflow_str:
            uploaded = self._upload_image_sync(base_url, input_image_base64, opener)
            if uploaded:
                workflow_str = workflow_str.replace('"${image}"', json.dumps(uploaded))
                logger.info(f"{self.log_prefix} (ComfyUI) 图片已上传: {uploaded}")
            else:
                logger.warning(f"{self.log_prefix} (ComfyUI) 图片上传失败，${'{image}'} 占位符未替换")

        # ---- 4. 解析工作流 JSON ----
        try:
            workflow = json.loads(workflow_str)
        except json.JSONDecodeError as e:
            return False, f"工作流 JSON 解析失败: {e}"

        # ---- 5. 提交任务 ----
        logger.info(f"{self.log_prefix} (ComfyUI) 提交任务, seed={seed}, prompt={full_prompt[:60]}...")
        prompt_id = self._queue_prompt_sync(base_url, workflow, opener)
        if not prompt_id:
            return False, "提交任务到 ComfyUI 失败，请检查服务是否运行"

        logger.info(f"{self.log_prefix} (ComfyUI) 任务已提交, prompt_id={prompt_id}")

        # ---- 6. 轮询结果 ----
        image_filename = self._poll_history_sync(base_url, prompt_id, opener, timeout=default_timeout)
        if not image_filename:
            return False, "等待 ComfyUI 生成结果超时"

        logger.info(f"{self.log_prefix} (ComfyUI) 生成完成, filename={image_filename}")

        # ---- 7. 下载图片 ----
        image_b64 = self._download_image_sync(base_url, image_filename, opener)
        if not image_b64:
            return False, f"下载图片失败: {image_filename}"

        logger.info(f"{self.log_prefix} (ComfyUI) 图片下载成功, base64 长度: {len(image_b64)}")
        return True, image_b64

    # ================================================================
    #  辅助方法
    # ================================================================

    def _queue_prompt_sync(self, base_url: str, workflow: dict, opener: urllib.request.OpenerDirector) -> Optional[str]:
        """同步提交工作流到 ComfyUI，返回 prompt_id"""
        url = f"{base_url}/prompt"
        payload = json.dumps({"prompt": workflow}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")

        try:
            with opener.open(req, timeout=30) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    return data.get("prompt_id")
                else:
                    logger.error(f"{self.log_prefix} (ComfyUI) 提交任务失败, status={resp.status}")
        except Exception as e:
            logger.error(f"{self.log_prefix} (ComfyUI) 提交任务异常: {e}")
        return None

    def _poll_history_sync(self, base_url: str, prompt_id: str, opener: urllib.request.OpenerDirector, timeout: int = 120) -> Optional[str]:
        """同步轮询 ComfyUI history，等待任务完成并返回输出图片文件名"""
        url = f"{base_url}/history/{prompt_id}"
        start = time.time()

        while time.time() - start < timeout:
            try:
                req = urllib.request.Request(url, method="GET")
                with opener.open(req, timeout=10) as resp:
                    if resp.status == 200:
                        history = json.loads(resp.read().decode("utf-8"))
                        if prompt_id in history:
                            return self._extract_filename(history[prompt_id])
            except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
                logger.debug(f"{self.log_prefix} (ComfyUI) 轮询中断，继续重试: {exc}")
            time.sleep(1)

        logger.error(f"{self.log_prefix} (ComfyUI) 轮询超时 ({timeout}s)")
        return None

    @staticmethod
    def _extract_filename(task_data: dict) -> Optional[str]:
        """从 history 条目中提取输出图片文件名"""
        try:
            outputs = task_data.get("outputs", {})
            for _node_id, node_output in outputs.items():
                if "images" in node_output:
                    for img in node_output["images"]:
                        if "filename" in img:
                            return img["filename"]
        except (AttributeError, TypeError, KeyError) as exc:
            logger.debug(f"(ComfyUI) 提取输出文件名失败: {exc}")
        return None

    def _download_image_sync(self, base_url: str, filename: str, opener: urllib.request.OpenerDirector) -> Optional[str]:
        """从 ComfyUI 下载生成的图片，返回 base64 字符串"""
        url = f"{base_url}/view?filename={urllib.parse.quote(filename)}&subfolder=&type=output"
        try:
            req = urllib.request.Request(url, method="GET")
            with opener.open(req, timeout=30) as resp:
                if resp.status == 200:
                    return base64.b64encode(resp.read()).decode("utf-8")
                else:
                    logger.error(f"{self.log_prefix} (ComfyUI) 下载图片失败, status={resp.status}")
        except Exception as e:
            logger.error(f"{self.log_prefix} (ComfyUI) 下载图片异常: {e}")
        return None

    def _upload_image_sync(self, base_url: str, image_base64: str, opener: urllib.request.OpenerDirector) -> Optional[str]:
        """同步上传图片到 ComfyUI /upload/image，返回上传后的文件路径"""
        clean_b64 = self._get_clean_base64(image_base64)
        image_bytes = base64.b64decode(clean_b64)
        mime_type = self._detect_mime_type(clean_b64)

        ext_map = {
            "image/jpeg": "jpg",
            "image/png": "png",
            "image/webp": "webp",
            "image/gif": "gif",
        }
        ext = ext_map.get(mime_type, "png")
        filename = f"upload_{uuid.uuid4().hex[:8]}.{ext}"
        subfolder = "temp"

        # 构建 multipart/form-data
        boundary = uuid.uuid4().hex
        body = b""

        # image 字段
        body += f"--{boundary}\r\n".encode()
        body += f'Content-Disposition: form-data; name="image"; filename="{filename}"\r\n'.encode()
        body += f"Content-Type: {mime_type}\r\n\r\n".encode()
        body += image_bytes
        body += b"\r\n"

        # subfolder 字段
        body += f"--{boundary}\r\n".encode()
        body += b'Content-Disposition: form-data; name="subfolder"\r\n\r\n'
        body += subfolder.encode()
        body += b"\r\n"

        # overwrite 字段
        body += f"--{boundary}\r\n".encode()
        body += b'Content-Disposition: form-data; name="overwrite"\r\n\r\n'
        body += b"true\r\n"

        body += f"--{boundary}--\r\n".encode()

        url = f"{base_url}/upload/image"
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")

        try:
            with opener.open(req, timeout=60) as resp:
                if resp.status == 200:
                    result = json.loads(resp.read().decode("utf-8"))
                    name = result.get("name")
                    if name:
                        sub = result.get("subfolder", subfolder)
                        return f"{sub}/{name}" if sub else name
                    logger.error(f"{self.log_prefix} (ComfyUI) 上传响应缺少 name: {result}")
                else:
                    logger.error(f"{self.log_prefix} (ComfyUI) 上传图片失败, status={resp.status}")
        except Exception as e:
            logger.error(f"{self.log_prefix} (ComfyUI) 上传图片异常: {e}")
        return None
