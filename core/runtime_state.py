"""兼容入口：转发到 ``core.utils.runtime_state``。"""

from .utils.runtime_state import ChatStreamState, RuntimeStateManager, runtime_state

__all__ = ["ChatStreamState", "RuntimeStateManager", "runtime_state"]
