"""/dr wardrobe|衣柜 command (simplified version).

简洁版衣柜命令：
- status: 显示当前穿搭状态
- list: 列出穿搭列表
- wear: 临时更换穿搭（当天有效）
- help: 显示帮助
"""

from __future__ import annotations

import logging
from typing import Any

from src.plugin_system.base.base_command import BaseCommand

logger = logging.getLogger(__name__)


class WardrobeCommand(BaseCommand):
    """/dr wardrobe|衣柜 - 简洁版衣柜控制命令"""

    command_name: str = "wardrobe_command"
    command_description: str = "衣柜/穿搭控制：/dr wardrobe|衣柜 <subcommand>"

    command_pattern: str = (
        r"(?:.*，说：\s*)?/dr\s+(?P<action>wardrobe|衣柜)"
        r"(?:\s+(?P<sub>\S+))?"
        r"(?:\s+(?P<arg>.*))?$"
    )

    intercept_level: int = 2

    def _check_permission(self) -> bool:
        """检查管理员权限"""
        try:
            admin_users = self.get_config("components.admin_users", [])
            user_id = (
                str(self.message.message_info.user_info.user_id)
                if self.message and self.message.message_info and self.message.message_info.user_info
                else None
            )
            if user_id is None:
                return False

            if isinstance(admin_users, list):
                return user_id in admin_users
            if isinstance(admin_users, str):
                normalized = [item.strip() for item in admin_users.split(",") if item.strip()]
                return user_id in normalized
            return False
        except (AttributeError, TypeError, KeyError) as exc:
            logger.debug("权限检查失败: %s", exc)
            return False

    async def execute(self) -> tuple[bool, str | None, bool]:
        """执行衣柜命令"""
        try:
            sub_raw = (self.matched_groups.get("sub") or "").strip()
            arg_raw = (self.matched_groups.get("arg") or "").strip()

            sub = sub_raw.lower() if sub_raw else "help"

            # 开放子命令
            if sub in {"help", "?"}:
                return await self._cmd_help(intercept=True)
            if sub == "list":
                return await self._cmd_list(intercept=True)
            if sub == "status":
                return await self._cmd_status(intercept=True)

            # 管理员子命令
            if sub == "wear":
                if not self._check_permission():
                    await self.send_text("你无权使用此命令", storage_message=False)
                    return False, "没有权限", True
                return await self._cmd_wear(arg_raw, intercept=True)

            await self.send_text(
                "未知子命令。\n使用：/dr wardrobe help 查看帮助。",
                storage_message=False,
            )
            return False, f"未知子命令: {sub}", True
        except Exception as exc:
            logger.error("WardrobeCommand execute failed: %r", exc, exc_info=True)
            await self.send_text(f"衣柜命令执行失败：{str(exc)[:120]}")
            return False, f"命令异常: {str(exc)}", True

    async def _cmd_help(self, *, intercept: bool) -> tuple[bool, str | None, bool]:
        """显示帮助"""
        lines: list[str] = [
            "🧥 衣柜命令帮助 (/dr wardrobe | /dr 衣柜)",
            "",
            "📋 通用命令（所有人可用）：",
            "• /dr wardrobe list     — 列出可用穿搭",
            "• /dr wardrobe status   — 查看当前穿搭状态",
            "• /dr wardrobe help     — 查看帮助",
            "",
            "🔒 管理员命令：",
            "• /dr wardrobe wear <衣服>  — 临时更换今日穿搭",
            "",
            "💡 配置说明：",
            "• 每日穿搭在 wardrobe.daily_outfits 中配置",
            "• 场景换装（睡觉/运动）自动匹配关键词",
        ]
        await self.send_text("\n".join(lines))
        return True, "help", intercept

    async def _cmd_list(self, *, intercept: bool) -> tuple[bool, str | None, bool]:
        """列出穿搭"""
        try:
            enabled = self.get_config("wardrobe.enabled", False)
            daily_outfits = self.get_config("wardrobe.daily_outfits", [])
            auto_scene_change = self.get_config("wardrobe.auto_scene_change", True)
            custom_scenes = self.get_config("wardrobe.custom_scenes", [])

            lines: list[str] = ["🧥 穿搭列表"]
            if not enabled:
                lines.append("（提示：当前 wardrobe.enabled = false，衣柜功能未启用）")
            lines.append("")

            # 每日穿搭
            lines.append("📅 每日穿搭：")
            if daily_outfits:
                for i, outfit in enumerate(daily_outfits, 1):
                    lines.append(f"  {i}. {outfit}")
            else:
                lines.append("  （未配置）")

            # 场景换装
            lines.append("")
            lines.append("🌙 场景换装：")
            if auto_scene_change and custom_scenes:
                for rule in custom_scenes:
                    lines.append(f"  • {rule}")
            elif not auto_scene_change:
                lines.append("  （自动换装已关闭）")
            else:
                lines.append("  （未配置自定义场景）")

            await self.send_text("\n".join(lines))
            return True, "list", intercept
        except Exception as exc:
            logger.error("Wardrobe list failed: %r", exc, exc_info=True)
            await self.send_text(f"获取穿搭列表失败：{str(exc)[:120]}")
            return False, f"list异常: {str(exc)}", intercept

    async def _cmd_status(self, *, intercept: bool) -> tuple[bool, str | None, bool]:
        """显示当前穿搭状态"""
        try:
            enabled = self.get_config("wardrobe.enabled", False)

            # 获取当前活动
            current_activity = "（无法获取）"
            current_outfit_from_schedule = "（无法获取）"
            wardrobe_selection = "（未启用）"
            try:
                from .selfie.schedule_provider import get_schedule_provider

                provider = get_schedule_provider()
                activity = await provider.get_current_activity()
                current_activity = f"{activity.activity_type.value} — {activity.description}"
                current_outfit_from_schedule = getattr(activity, "outfit", "") or "（未设置）"

                # 用简洁版衣柜选择器计算当前应穿什么
                if enabled:
                    from .wardrobe.selector import (
                        build_simple_wardrobe_config,
                        load_temp_override,
                        select_outfit_from_schedule,
                    )

                    wardrobe_config_simple = build_simple_wardrobe_config(self.get_config)
                    current_override: str = await load_temp_override()
                    outfit_result: str = select_outfit_from_schedule(
                        schedule_item=activity,
                        wardrobe_config=wardrobe_config_simple,
                        temp_override=current_override,
                    )
                    wardrobe_selection = outfit_result if outfit_result else "（无匹配，使用默认外观）"
            except Exception:
                pass

            temp_override_display: str = ""
            try:
                from .wardrobe.selector import load_temp_override as _load_override

                temp_override_display = await _load_override()
            except Exception:
                pass

            lines: list[str] = [
                "🧥 衣柜状态",
                "",
                f"📍 当前活动：{current_activity}",
                f"👕 日程穿搭：{current_outfit_from_schedule}",
            ]
            if temp_override_display:
                lines.append(f"🎯 临时穿搭：{temp_override_display}（今日有效）")
            lines.append(f"🧥 衣柜选择：{wardrobe_selection}")

            if not enabled:
                lines.append("")
                lines.append("⚠️ wardrobe.enabled = false：衣柜功能当前被禁用")

            await self.send_text("\n".join(lines))
            return True, "status", intercept
        except Exception as exc:
            logger.error("Wardrobe status failed: %r", exc, exc_info=True)
            await self.send_text(f"获取衣柜状态失败：{str(exc)[:120]}")
            return False, f"status异常: {str(exc)}", intercept

    async def _cmd_wear(self, arg: str, *, intercept: bool) -> tuple[bool, str | None, bool]:
        """管理员：临时更换今日穿搭（持久化到数据库，当天有效）"""
        outfit: str = (arg or "").strip()
        if not outfit:
            await self.send_text("\n".join([
                "用法：/dr wardrobe wear <衣服描述>",
                "示例：/dr wardrobe wear 黑丝JK",
                "",
                "设置后今天所有自拍都会使用该穿搭，次日自动重置。",
            ]))
            return False, "缺少衣服描述", intercept

        try:
            from .wardrobe.selector import save_temp_override

            await save_temp_override(outfit)
            await self.send_text(
                f"✅ 已设置今日临时穿搭：{outfit}\n"
                f"（今日所有自拍将优先使用此穿搭，次日自动重置）"
            )
            return True, "wear", intercept
        except Exception as exc:
            logger.error("Wardrobe wear failed: %r", exc, exc_info=True)
            await self.send_text(f"设置穿搭失败：{str(exc)[:120]}")
            return False, f"wear异常: {str(exc)}", intercept
