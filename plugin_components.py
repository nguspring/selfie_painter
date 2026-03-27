"""插件组件装配逻辑。"""

from __future__ import annotations

from typing import Any, List, Tuple, Type

from src.plugin_system.base.component_types import ComponentInfo

from .core.pic_action import SelfiePainterAction
from .core.pic_command import PicConfigCommand, PicGenerationCommand, PicStyleCommand
from .core.schedule_command import ScheduleCommand
from .core.schedule_inject_handler import ScheduleInjectHandler
from .core.wardrobe_command import WardrobeCommand


def build_plugin_components(plugin: Any) -> List[Tuple[ComponentInfo, Type[Any]]]:
    """根据当前配置构建插件组件列表。"""
    enable_unified_generation = plugin.get_config("components.enable_unified_generation", True)
    enable_pic_command = plugin.get_config("components.enable_pic_command", True)
    enable_pic_config = plugin.get_config("components.enable_pic_config", True)
    enable_pic_style = plugin.get_config("components.enable_pic_style", True)
    components: List[Tuple[ComponentInfo, Type[Any]]] = []

    if enable_unified_generation:
        components.append((SelfiePainterAction.get_action_info(), SelfiePainterAction))

    if enable_pic_config:
        components.append((PicConfigCommand.get_command_info(), PicConfigCommand))

    if enable_pic_style:
        components.append((PicStyleCommand.get_command_info(), PicStyleCommand))

    if enable_pic_command:
        components.append((WardrobeCommand.get_command_info(), WardrobeCommand))
        components.append((PicGenerationCommand.get_command_info(), PicGenerationCommand))

    components.append((ScheduleCommand.get_command_info(), ScheduleCommand))
    if plugin.get_config("schedule_inject.enabled", True):
        components.append((ScheduleInjectHandler.get_handler_info(), ScheduleInjectHandler))

    return components


__all__ = ["build_plugin_components"]
