"""
自动自拍后台任务

定时执行自拍流程：
1. 从 ScheduleProvider 获取当前活动
2. 用 SceneActionGenerator 生成自拍提示词
3. 用 generate_image_standalone 生成图片
4. 用 CaptionGenerator 生成配文
5. 通过 Maizone QZone API 发布到QQ空间说说

支持：
- 可配置间隔（如每 2 小时）
- 安静时段控制
"""

import asyncio
import base64
import datetime
from importlib import import_module
import os
import time
from typing import Any, Optional

from src.common.logger import get_logger  # pyright: ignore[reportMissingImports]

from .schedule_provider import get_schedule_provider
from .scene_action_generator import convert_to_selfie_prompt, get_negative_prompt_for_style
from .caption_generator import generate_caption
from ..api_clients import generate_image_standalone
from ..utils import (
    get_model_config,
    normalize_selfie_style,
    get_selfie_style_display_name,
    build_target_context_id,
    is_chat_allowed_for_model,
)

logger = get_logger("auto_selfie.task")


def _safe_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return default


class AutoSelfieTask:
    """自动自拍后台定时任务

    轮询模型：每 _POLL_INTERVAL 秒检查一次是否该拍照。
    判断条件：
    1. 不在安静时段
    2. 今天醒来后还没拍过 → 立即拍（醒来自拍）
    3. 距上次自拍 ≥ interval → 拍（间隔自拍）
    """

    _POLL_INTERVAL = 60  # 轮询间隔（秒）
    _HEARTBEAT_EVERY = 5  # 每隔多少次轮询打一次心跳日志（即 5 分钟）
    _RESTART_THROTTLE = 30.0  # 自动重启最小间隔（秒）
    _LOAD_FAILED: object = object()  # 哨兵值：DB 读取失败

    def __init__(self, plugin) -> None:
        """
        Args:
            plugin: 插件实例，用于读取配置
        """
        self.plugin = plugin
        self.is_running: bool = False
        self.task: Optional[asyncio.Task[None]] = None
        self._consecutive_failures: int = 0
        self._last_selfie_ts: Optional[float] = None  # 上次成功自拍的 Unix 时间戳
        self._last_restart_ts: float = 0.0  # 上次自动重启的时间戳

    # ------------------------------------------------------------------ #
    #  配置读取
    # ------------------------------------------------------------------ #

    def get_config(self, key: str, default=None):
        return self.plugin.get_config(key, default)

    # ------------------------------------------------------------------ #
    #  启停 & 自动恢复
    # ------------------------------------------------------------------ #

    async def start(self) -> None:
        """启动自动自拍任务"""
        if self.is_running:
            return
        self.is_running = True
        self.task = asyncio.create_task(self._selfie_loop())
        self.task.add_done_callback(self._on_task_done)
        logger.info("自动自拍任务已启动")

    async def stop(self) -> None:
        """停止自动自拍任务"""
        if not self.is_running:
            return
        self.is_running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        logger.info("自动自拍任务已停止")

    def _on_task_done(self, task: asyncio.Task[None]) -> None:
        """任务结束回调：is_running 仍为 True 说明是意外退出，自动重启（带节流）"""
        if not self.is_running:
            return

        # 节流：防止崩溃热循环
        now = time.time()
        elapsed = now - self._last_restart_ts
        if elapsed < self._RESTART_THROTTLE:
            logger.error(f"自拍循环在 {elapsed:.0f}s 内再次退出，跳过重启以防热循环")
            self.is_running = False
            return

        try:
            exc = task.exception()
            if exc:
                logger.error(f"自拍循环意外退出（{exc}），自动重启...")
            else:
                logger.warning("自拍循环正常退出但 is_running 仍为 True，自动重启...")
        except asyncio.CancelledError:
            logger.warning("自拍循环被意外取消，自动重启...")
        try:
            self._last_restart_ts = now
            self.task = asyncio.create_task(self._selfie_loop())
            self.task.add_done_callback(self._on_task_done)
        except RuntimeError:
            logger.error("无法重启自拍循环（事件循环可能已关闭）")

    # ------------------------------------------------------------------ #
    #  时间判断（仅 2 个方法）
    # ------------------------------------------------------------------ #

    def _is_quiet_hours(self) -> bool:
        """当前是否在安静时段 [start, end)（半开区间）"""
        from ..utils.time_utils import to_minutes

        start_min = to_minutes(self.get_config("auto_selfie.quiet_hours_start", "00:00"))
        end_min = to_minutes(self.get_config("auto_selfie.quiet_hours_end", "07:00"))
        now = datetime.datetime.now()
        current_min = now.hour * 60 + now.minute

        if start_min == end_min:
            return False
        if end_min < start_min:  # 跨午夜（如 23:00-07:00）
            return current_min >= start_min or current_min < end_min
        return start_min <= current_min < end_min  # 不跨午夜（如 00:00-07:00）

    def _is_today_after_wake(self, ts: float) -> bool:
        """判断时间戳是否是今天且在醒来时间之后"""
        from ..utils.time_utils import to_minutes

        dt = datetime.datetime.fromtimestamp(ts)
        if dt.date() != datetime.date.today():
            return False
        wake_min = to_minutes(self.get_config("auto_selfie.quiet_hours_end", "07:00"))
        return dt.hour * 60 + dt.minute >= wake_min

    # ------------------------------------------------------------------ #
    #  持久化（只存 1 个 key：auto_selfie_last_success_ts）
    # ------------------------------------------------------------------ #

    async def _load_last_selfie_ts(self) -> float | None | object:
        """从数据库读取上次自拍的 Unix 时间戳

        Returns:
            float: 成功读取到的时间戳
            None: 无历史记录（或持久化未启用）
            _LOAD_FAILED: 数据库读取异常
        """
        if not self.get_config("auto_selfie.persist_state", True):
            return None
        try:
            from ..schedule.schedule_manager import get_schedule_manager

            manager = get_schedule_manager()
            await manager.ensure_db_initialized()
            raw = await manager.get_state("auto_selfie_last_success_ts")
            if raw:
                return float(raw)
            return None
        except Exception as e:
            logger.warning(f"读取上次自拍时间失败: {e}")
            return self._LOAD_FAILED

    async def _save_last_selfie_ts(self, ts: float) -> None:
        """持久化自拍时间戳"""
        if not self.get_config("auto_selfie.persist_state", True):
            return
        try:
            from ..schedule.schedule_manager import get_schedule_manager

            manager = get_schedule_manager()
            await manager.set_state("auto_selfie_last_success_ts", str(ts))
        except Exception as e:
            logger.warning(f"持久化自拍时间失败: {e}")

    # ------------------------------------------------------------------ #
    #  主循环（轮询模型）
    # ------------------------------------------------------------------ #

    async def _selfie_loop(self) -> None:
        """主循环：每 _POLL_INTERVAL 秒检查一次条件，满足则拍照"""
        interval = self.get_config("auto_selfie.interval_minutes", 120)
        interval_seconds = max(interval, 10) * 60  # 至少 10 分钟

        # 启动延迟
        await asyncio.sleep(10.0)

        # 从持久化恢复上次自拍时间
        loaded = await self._load_last_selfie_ts()
        if loaded is self._LOAD_FAILED:
            logger.error("启动时数据库读取失败，将在后续轮询中重试")
            # _last_selfie_ts 保持 None，但标记需要重试加载
            db_load_pending = True
        else:
            self._last_selfie_ts = loaded if isinstance(loaded, float) else None
            db_load_pending = False
            if self._last_selfie_ts:
                dt = datetime.datetime.fromtimestamp(self._last_selfie_ts)
                logger.info(f"恢复上次自拍时间: {dt.strftime('%Y-%m-%d %H:%M:%S')}")
            else:
                logger.info("无历史自拍记录，将在醒来时拍第一张")

        poll_count = 0

        while self.is_running:
            try:
                poll_count += 1

                # ---- 心跳日志 ----
                if poll_count % self._HEARTBEAT_EVERY == 0:
                    self._log_heartbeat(interval_seconds)

                # ---- 安静时段：跳过 ----
                if self._is_quiet_hours():
                    await asyncio.sleep(self._POLL_INTERVAL)
                    continue

                # ---- DB 加载重试 ----
                if db_load_pending:
                    loaded = await self._load_last_selfie_ts()
                    if loaded is self._LOAD_FAILED:
                        logger.warning("数据库仍不可用，跳过本次轮询")
                        await asyncio.sleep(self._POLL_INTERVAL)
                        continue
                    self._last_selfie_ts = loaded if isinstance(loaded, float) else None
                    db_load_pending = False
                    logger.info("数据库恢复，已加载上次自拍时间")

                # ---- 判断是否该拍照 ----
                now_ts = time.time()
                should_take = False
                reason = ""

                if self._last_selfie_ts is None:
                    should_take = True
                    reason = "首次自拍（无历史记录）"
                elif not self._is_today_after_wake(self._last_selfie_ts):
                    should_take = True
                    reason = "醒来第一张自拍"
                elif now_ts - self._last_selfie_ts >= interval_seconds:
                    should_take = True
                    elapsed_min = (now_ts - self._last_selfie_ts) / 60
                    reason = f"间隔到达（已过 {elapsed_min:.0f} 分钟）"

                if not should_take:
                    await asyncio.sleep(self._POLL_INTERVAL)
                    continue

                # ---- 执行自拍 ----
                logger.info(f"触发自拍: {reason}")
                try:
                    await self._execute_selfie()
                    self._last_selfie_ts = time.time()
                    await self._save_last_selfie_ts(self._last_selfie_ts)
                    self._consecutive_failures = 0
                    logger.info("自拍完成，计时器重置")
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    self._consecutive_failures += 1
                    logger.error(f"自拍执行出错 (连续第{self._consecutive_failures}次): {e}")
                    # 简单退避：失败越多等越久，但不超过一个间隔
                    backoff = min(self._consecutive_failures * 60, interval_seconds)
                    logger.warning(f"退避等待 {backoff // 60} 分钟后重试")
                    # 分块退避：每 _HEARTBEAT_EVERY * _POLL_INTERVAL 秒发一次心跳
                    heartbeat_interval = self._HEARTBEAT_EVERY * self._POLL_INTERVAL
                    remaining = backoff
                    while remaining > 0 and self.is_running:
                        chunk = min(remaining, heartbeat_interval)
                        await asyncio.sleep(chunk)
                        remaining -= chunk
                        if remaining > 0:
                            logger.info(f"[自动自拍] 心跳: 退避中，剩余 {remaining / 60:.0f} 分钟")
                    continue  # 退避后直接回到循环顶部，不再叠加 POLL_INTERVAL

                await asyncio.sleep(self._POLL_INTERVAL)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"自拍主循环异常: {e}", exc_info=True)
                await asyncio.sleep(60.0)

    def _log_heartbeat(self, interval_seconds: float) -> None:
        """每 _HEARTBEAT_EVERY 次轮询输出一次心跳日志"""
        if self._is_quiet_hours():
            from ..utils.time_utils import to_minutes

            wake_min = to_minutes(self.get_config("auto_selfie.quiet_hours_end", "07:00"))
            now = datetime.datetime.now()
            current_min = now.hour * 60 + now.minute
            if current_min < wake_min:
                remaining = wake_min - current_min
            else:
                remaining = (24 * 60 - current_min) + wake_min
            logger.info(f"[自动自拍] 心跳: 安静时段，距醒来约 {remaining} 分钟")
        elif self._last_selfie_ts:
            elapsed = time.time() - self._last_selfie_ts
            next_in = max(0, interval_seconds - elapsed) / 60
            logger.info(f"[自动自拍] 心跳: 运行中，距下次自拍约 {next_in:.0f} 分钟")
        else:
            logger.info("[自动自拍] 心跳: 运行中，等待首次自拍时机")

    async def _execute_selfie(self):
        """执行一次完整的自拍流程"""
        logger.info("开始执行自动自拍流程...")

        # 1. 获取当前活动
        provider = get_schedule_provider()
        activity = await provider.get_current_activity()

        logger.info(f"当前活动: {activity.description} ({activity.activity_type.value})")

        # 2. 生成自拍提示词
        selfie_style = normalize_selfie_style(self.get_config("selfie.default_style", "standard"))
        bot_appearance = self.get_config("selfie.prompt_prefix", "")
        try:
            wardrobe_enabled = self.get_config("wardrobe.enabled", False)
            if _safe_bool(wardrobe_enabled, False):
                from ..wardrobe.selector import (
                    build_simple_wardrobe_config,
                    load_temp_override,
                    select_outfit_from_schedule,
                )

                wardrobe_config_simple = build_simple_wardrobe_config(self.get_config)
                current_override: str = await load_temp_override()

                outfit_prompt: str = select_outfit_from_schedule(
                    schedule_item=activity,
                    wardrobe_config=wardrobe_config_simple,
                    temp_override=current_override,
                )

                if outfit_prompt:
                    logger.info("Wardrobe: 选择穿搭 → %s", outfit_prompt)
                    if not bot_appearance:
                        bot_appearance = outfit_prompt
                    else:
                        bot_appearance = f"{bot_appearance}, {outfit_prompt}"
                else:
                    logger.debug("Wardrobe: 未匹配到穿搭")
        except Exception as exc:
            logger.warning("Wardrobe injection failed: %s", exc)
        raw_mode: bool = bool(self.get_config("selfie.raw_mode", False))
        prompt = await convert_to_selfie_prompt(activity, selfie_style, bot_appearance, raw_mode=raw_mode)
        if not prompt:
            logger.warning("LLM 自拍提示词生成失败，跳过本次自拍")
            return

        negative_prompt = get_negative_prompt_for_style(
            selfie_style,
            self.get_config("selfie.negative_prompt", ""),
            raw_mode=raw_mode,
        )

        logger.info(f"自动自拍风格: {get_selfie_style_display_name(selfie_style)}（{selfie_style}）")
        logger.info(f"自拍提示词: {prompt[:100]}...")

        # 3. 生成图片
        selfie_model = self.get_config("auto_selfie.selfie_model", "model1")
        model_config = self._get_model_config(selfie_model)
        if not model_config:
            logger.error(f"模型配置获取失败: {selfie_model}")
            return

        # 透传代理配置
        extra_config = {}
        if self.get_config("proxy.enabled", False):
            extra_config["proxy"] = {
                "enabled": True,
                "url": self.get_config("proxy.url", "http://127.0.0.1:7890"),
                "timeout": self.get_config("proxy.timeout", 60),
            }

        # 检查参考图片（图生图模式）
        reference_image = self._load_reference_image()
        strength = None
        if reference_image:
            if model_config.get("support_img2img", True):
                strength = 0.6
                logger.info("使用参考图片进行图生图自拍")
            else:
                reference_image = None
                logger.warning(f"模型 {selfie_model} 不支持图生图，回退文生图")

        success, image_data = await generate_image_standalone(
            prompt=prompt,
            model_config=model_config,
            size=model_config.get("default_size", "1024x1024"),
            negative_prompt=negative_prompt,
            strength=strength,
            input_image_base64=reference_image,
            max_retries=2,
            extra_config=extra_config if extra_config else None,
        )

        if not success:
            logger.error(f"自拍图片生成失败: {image_data}")
            return

        logger.info(f"自拍图片生成成功，数据长度: {len(image_data)}")

        # 4. 生成配文
        caption = ""
        if self.get_config("auto_selfie.caption_enabled", True):
            caption = await generate_caption(activity)
            if not caption:
                logger.warning("配文生成失败，跳过本次自拍发布")
                return
            logger.info(f"配文: {caption}")

        # 5. 发布到目标频道
        send_to_qzone = self.get_config("auto_selfie.send_to_qzone", False)
        send_to_chat = self.get_config("auto_selfie.send_to_chat", False)
        target_groups = self.get_config("auto_selfie.target_groups", [])
        target_users = self.get_config("auto_selfie.target_users", [])
        caption_enabled = self.get_config("auto_selfie.caption_enabled", True)

        # 5a. 发布到 QQ 空间
        if send_to_qzone:
            try:
                qzone_module = import_module("plugins.Maizone.qzone")
                helpers_module = import_module("plugins.Maizone.helpers")
                plugin_core_module = import_module("src.plugin_system.core")
                plugin_apis_module = import_module("src.plugin_system.apis")

                create_qzone_api = qzone_module.create_qzone_api
                get_napcat_config_and_renew = helpers_module.get_napcat_config_and_renew
                component_registry = plugin_core_module.component_registry
                config_api = plugin_apis_module.config_api

                # 刷新 Cookie
                maizone_cfg = component_registry.get_plugin_config("MaizonePlugin")
                if maizone_cfg:

                    def get_config_fn(key, default=None):
                        return config_api.get_plugin_config(maizone_cfg, key, default)

                    await get_napcat_config_and_renew(get_config_fn)

                # 将 image_data 转为 bytes
                image_bytes = await self._resolve_image_to_bytes(image_data)
                if not image_bytes:
                    logger.error("图片数据转换失败，无法发布到QQ空间")
                else:
                    # 发布说说
                    qzone = create_qzone_api()
                    if not qzone:
                        logger.error("QZone API 创建失败（Cookie 不存在或无效），无法发布自拍")
                    else:
                        tid = await qzone.publish_emotion(caption, [image_bytes])
                        logger.info(f"自拍已发布到QQ空间，tid: {tid}")
            except ImportError:
                logger.error("Maizone 插件未安装，无法发布自拍到QQ空间")
            except Exception as e:
                logger.warning(f"[SelfiePainterV2] QQ空间发送失败: {e}")

        # 5b. 发布到群聊/私聊
        if send_to_chat:
            try:
                # 主动从数据库加载所有历史聊天流，确保即使长时间无互动也能找到目标
                try:
                    chat_stream_module = import_module("src.chat.chat_stream")
                    get_chat_manager = chat_stream_module.get_chat_manager

                    chat_manager = get_chat_manager()
                    if hasattr(chat_manager, "load_all_streams"):
                        await chat_manager.load_all_streams()
                        logger.info("[SelfiePainterV2] 已从数据库加载所有历史聊天流")
                except Exception as e:
                    logger.warning(f"[SelfiePainterV2] 加载历史聊天流失败（仅使用内存中的活跃流）: {e}")

                plugin_system_module = import_module("src.plugin_system")
                plugin_apis_module = import_module("src.plugin_system.apis")
                chat_api = plugin_system_module.chat_api
                send_api = plugin_apis_module.send_api
                import base64

                # 图片转 base64
                if isinstance(image_data, bytes):
                    image_b64 = base64.b64encode(image_data).decode("utf-8")
                else:
                    image_b64 = image_data  # 已经是 base64 字符串

                # 发送到目标群聊
                for group_id in target_groups:
                    try:
                        group_stream_id = build_target_context_id(group_id, "group")
                        if group_stream_id and not is_chat_allowed_for_model(
                            self.get_config, group_stream_id, selfie_model
                        ):
                            logger.info(f"[SelfiePainterV2] 群 {group_id} 被模型 {selfie_model} 的访问规则跳过")
                            continue
                        stream = chat_api.get_stream_by_group_id(str(group_id))
                        if stream:
                            await send_api.image_to_stream(image_b64, stream.stream_id)
                            if caption_enabled and caption:
                                await send_api.text_to_stream(caption, stream.stream_id)
                            logger.info(f"自拍已发送到群 {group_id}")
                        else:
                            logger.info(f"[SelfiePainterV2] 群 {group_id} 无活跃stream，跳过")
                    except Exception as e:
                        logger.warning(f"[SelfiePainterV2] 发送到群 {group_id} 失败: {e}")

                # 发送到目标私聊
                for user_id in target_users:
                    try:
                        user_stream_id = build_target_context_id(user_id, "private")
                        if user_stream_id and not is_chat_allowed_for_model(
                            self.get_config, user_stream_id, selfie_model
                        ):
                            logger.info(f"[SelfiePainterV2] 用户 {user_id} 被模型 {selfie_model} 的访问规则跳过")
                            continue
                        stream = chat_api.get_stream_by_user_id(str(user_id))
                        if stream:
                            await send_api.image_to_stream(image_b64, stream.stream_id)
                            if caption_enabled and caption:
                                await send_api.text_to_stream(caption, stream.stream_id)
                            logger.info(f"自拍已发送到用户 {user_id}")
                        else:
                            logger.info(f"[SelfiePainterV2] 用户 {user_id} 无活跃stream，跳过")
                    except Exception as e:
                        logger.warning(f"[SelfiePainterV2] 发送到用户 {user_id} 失败: {e}")

            except Exception as e:
                logger.warning(f"[SelfiePainterV2] 群聊/私聊发送失败: {e}")

        # 6. 持久化成功时间戳
        if self.get_config("auto_selfie.persist_state", True):
            try:
                from ..schedule.schedule_manager import get_schedule_manager

                manager = get_schedule_manager()
                await manager.set_state("auto_selfie_last_success_ts", str(time.time()))
                logger.debug("已更新 auto_selfie_last_success_ts")
            except Exception as e:
                logger.warning(f"持久化自拍时间戳失败: {e}")

    def _get_model_config(self, model_id: str) -> Optional[dict[str, Any]]:
        """获取模型配置"""
        return get_model_config(self.get_config, model_id, log_prefix="[AutoSelfie]")

    def _load_reference_image(self) -> Optional[str]:
        """加载自拍参考图片的base64编码

        Returns:
            图片的base64编码，如果不存在则返回None
        """
        image_path = self.get_config("selfie.reference_image_path", "").strip()
        if not image_path:
            return None

        try:
            # 处理相对路径（相对于插件目录）
            if not os.path.isabs(image_path):
                plugin_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                image_path = os.path.join(plugin_dir, image_path)

            if os.path.exists(image_path):
                with open(image_path, "rb") as f:
                    image_data = f.read()
                image_base64 = base64.b64encode(image_data).decode("utf-8")
                logger.info(f"[AutoSelfie] 从文件加载自拍参考图片: {image_path}")
                return image_base64
            else:
                logger.warning(f"[AutoSelfie] 自拍参考图片文件不存在: {image_path}")
                return None
        except Exception as e:
            logger.error(f"[AutoSelfie] 加载自拍参考图片失败: {e}")
            return None

    @staticmethod
    async def _resolve_image_to_bytes(image_data: str) -> Optional[bytes]:
        """将 base64 或 URL 格式的图片数据转为 bytes"""
        if image_data.startswith(("http://", "https://")):
            import httpx

            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(image_data)
                resp.raise_for_status()
                return resp.content
        else:
            return base64.b64decode(image_data)
