"""插件配置预读取与动态布局注入辅助函数。"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

try:
    import tomllib
except ModuleNotFoundError:
    tomllib = None

if tomllib is not None:
    _TOMLDecodeError = tomllib.TOMLDecodeError
else:
    _TOMLDecodeError = ValueError


def load_raw_config(plugin_dir: str, config_file_name: str, logger) -> Optional[Dict[str, Any]]:
    """在 BasePlugin 初始化前预读取原始配置文件。"""
    config_path = os.path.join(plugin_dir, config_file_name)
    original_config: Optional[Dict[str, Any]] = None
    if os.path.exists(config_path):
        if tomllib is None:
            logger.warning("当前 Python 环境不支持 tomllib，跳过预读取配置：%s", config_path)
        else:
            try:
                with open(config_path, "rb") as file_obj:
                    original_config = tomllib.load(file_obj)
                logger.debug("预读取原始配置文件成功: %s", config_path)
            except (OSError, _TOMLDecodeError) as exc:
                logger.warning("预读取原始配置失败，将使用默认布局: %s", exc)
    return original_config


__all__ = ["load_raw_config"]
