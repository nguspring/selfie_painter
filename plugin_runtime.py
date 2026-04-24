"""插件后台任务生命周期逻辑。"""

from __future__ import annotations

import asyncio
from typing import Any

from src.common.logger import get_logger

logger = get_logger("selfie_painter_v2")


class PluginRuntimeMixin:
    """提供自动自拍与日程后台任务的生命周期管理。"""

    _auto_selfie_task: Any | None = None
    _auto_selfie_pending: bool = False
    _schedule_gen_task: asyncio.Task[Any] | None = None
    _schedule_pending: bool = False

    def _initialize_runtime_state(self) -> None:
        """初始化后台任务运行时状态。"""
        self._auto_selfie_task = None
        self._auto_selfie_pending = False
        self._schedule_gen_task = None
        self._schedule_pending = False

    @staticmethod
    def _schedule_background_task(coro_func) -> bool:
        """在事件循环已运行时创建后台任务，否则返回 False。"""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return False
        loop.create_task(coro_func())
        return True

    def _bootstrap_runtime_tasks(self) -> None:
        """按配置启动后台任务，事件循环未就绪时改为懒启动。"""
        if self.get_config("auto_selfie.enabled", False):
            from .core.selfie import AutoSelfieTask

            self._auto_selfie_task = AutoSelfieTask(self)
            if not self._schedule_background_task(self._start_auto_selfie_after_delay):
                self._auto_selfie_pending = True
                logger.info("事件循环未就绪，自动自拍任务将在首次执行时懒启动")

        if not self._schedule_background_task(self._start_schedule_gen_after_delay):
            self._schedule_pending = True

    async def _start_auto_selfie_after_delay(self):
        """延迟启动自动自拍任务。"""
        await asyncio.sleep(15)
        if self._auto_selfie_task:
            await self._auto_selfie_task.start()
            self._auto_selfie_pending = False

    def try_start_auto_selfie(self):
        """尝试懒启动自动自拍任务（供组件首次执行时调用）。"""
        if not self._auto_selfie_pending or not self._auto_selfie_task:
            return
        if self._schedule_background_task(self._start_auto_selfie_after_delay):
            self._auto_selfie_pending = False
        else:
            logger.debug("自动自拍懒启动失败，等待下次重试: 事件循环未就绪")

    def try_start_schedule_gen(self):
        """尝试懒启动日程后台任务。"""
        if not self._schedule_pending:
            return
        if self._schedule_background_task(self._start_schedule_gen_after_delay):
            self._schedule_pending = False
        else:
            logger.debug("日程任务懒启动失败，等待下次重试: 事件循环未就绪")

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
        except Exception as exc:
            logger.error("[SelfiePainter] 日程初始化失败: %s", exc, exc_info=True)

    async def _schedule_gen_loop(self) -> None:
        """每日在指定时间强制重新生成日程。"""
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
                logger.info("[SelfiePainter] 下次日程生成时间: %s (约 %.0f 秒后)", target, wait_seconds)
                await asyncio.sleep(wait_seconds)

                from .core.schedule import get_schedule_manager

                mgr = get_schedule_manager()
                # 到达预定时间：强制重新生成，覆盖旧数据
                success = await mgr.regen_today_schedule_via_llm(self)
                if success:
                    logger.info("[SelfiePainter] 每日日程强制重新生成完成")
                else:
                    logger.warning("[SelfiePainter] 每日日程重新生成失败，保留旧数据")

                # 按需清理过期历史数据
                retention_days = self.get_config("schedule.schedule_history_retention_days", -1)
                if retention_days >= 0:
                    deleted = await mgr.cleanup_old_schedule_data(retention_days)
                    if deleted > 0:
                        logger.info("[SelfiePainter] 清理旧日程: %s 条", deleted)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("[SelfiePainter] 日程生成循环异常: %s", exc, exc_info=True)
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


__all__ = ["PluginRuntimeMixin"]
