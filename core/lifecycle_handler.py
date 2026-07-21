"""插件生命周期事件处理器。

处理 ON_START 和 ON_STOP 事件，用于启动和停止后台任务。
修复 F1：匹配宿主事件处理器契约（execute、五元组、name 字段）。
修复 F6：在 ON_STOP 中清理后台任务（需宿主调用支持）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Tuple, Any

from src.plugin_system.base.base_events_handler import BaseEventHandler
from src.plugin_system.base.component_types import (
    EventType,
    EventHandlerInfo,
    ComponentType,
)
from src.common.logger import get_logger

if TYPE_CHECKING:
    from src.plugin_system.base.component_types import MaiMessages

logger = get_logger("selfie_painter_v2.lifecycle")


class LifecycleStartHandler(BaseEventHandler):
    """ON_START 事件处理器，用于启动后台任务。"""

    event_type = EventType.ON_START
    handler_name = "selfie_painter_v2_start"
    handler_description = "插件启动时初始化后台任务（自动自拍、日程生成）"

    @classmethod
    def get_handler_info(cls) -> EventHandlerInfo:
        """返回事件处理器信息。"""
        return EventHandlerInfo(
            name=cls.handler_name,
            component_type=ComponentType.EVENT_HANDLER,
            description=cls.handler_description,
            event_type=cls.event_type,
        )

    async def execute(self, message: MaiMessages) -> Tuple[bool, bool, str | None, Any, MaiMessages]:
        """处理 ON_START 事件，启动后台任务。

        Args:
            message: 事件消息对象

        Returns:
            (success, continue_processing, return_message, custom_result, modified_message)
        """
        try:
            # 通过插件名从注册表获取插件实例
            from src.plugin_system.core.plugin_manager import plugin_manager
            plugin_instance = plugin_manager.loaded_plugins.get(self.plugin_name)

            if plugin_instance and hasattr(plugin_instance, "_bootstrap_runtime_tasks"):
                plugin_instance._bootstrap_runtime_tasks()
                logger.info("[SelfiePainterV2] 后台任务已启动")
                return (True, True, "后台任务已启动", None, message)
            else:
                logger.warning("[SelfiePainterV2] 插件实例不存在或不支持后台任务启动")
                return (True, True, None, None, message)
        except Exception as exc:
            logger.error("[SelfiePainterV2] 启动后台任务失败: %s", exc, exc_info=True)
            return (False, True, f"启动失败: {exc}", None, message)


class LifecycleStopHandler(BaseEventHandler):
    """ON_STOP 事件处理器，用于停止后台任务。"""

    event_type = EventType.ON_STOP
    handler_name = "selfie_painter_v2_stop"
    handler_description = "插件停止时清理后台任务（自动自拍、日程生成）"

    @classmethod
    def get_handler_info(cls) -> EventHandlerInfo:
        """返回事件处理器信息。"""
        return EventHandlerInfo(
            name=cls.handler_name,
            component_type=ComponentType.EVENT_HANDLER,
            description=cls.handler_description,
            event_type=cls.event_type,
        )

    async def execute(self, message: MaiMessages) -> Tuple[bool, bool, str | None, Any, MaiMessages]:
        """处理 ON_STOP 事件，停止后台任务。

        Args:
            message: 事件消息对象

        Returns:
            (success, continue_processing, return_message, custom_result, modified_message)
        """
        try:
            # 通过插件名从注册表获取插件实例
            from src.plugin_system.core.plugin_manager import plugin_manager
            plugin_instance = plugin_manager.loaded_plugins.get(self.plugin_name)

            if plugin_instance and hasattr(plugin_instance, "on_plugin_unload"):
                await plugin_instance.on_plugin_unload()
                logger.info("[SelfiePainterV2] 后台任务已停止")
                return (True, True, "后台任务已停止", None, message)
            else:
                logger.warning("[SelfiePainterV2] 插件实例不存在或不支持后台任务停止")
                return (True, True, None, None, message)
        except Exception as exc:
            logger.error("[SelfiePainterV2] 停止后台任务失败: %s", exc, exc_info=True)
            return (False, True, f"停止失败: {exc}", None, message)


__all__ = ["LifecycleStartHandler", "LifecycleStopHandler"]
