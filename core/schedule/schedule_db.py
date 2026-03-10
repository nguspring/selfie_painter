"""
内置日程 SQLite 数据库管理器

使用 WAL 模式 + 线程本地连接，所有操作必须在 asyncio.to_thread 内调用。
"""

from __future__ import annotations

import importlib
import logging
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DB_SCHEMA_VERSION = 1


class ScheduleDB:
    """线程安全的 SQLite 封装。只能在同步线程（asyncio.to_thread）内调用。"""

    _thread_local: threading.local = threading.local()

    @staticmethod
    def resolve_db_path() -> str:
        """解析 DB 文件路径，确保 data/ 目录存在。"""
        plugin_root: str | None = None

        try:
            plugin_manage_api = importlib.import_module("src.plugin_system.apis.plugin_manage_api")
            get_plugin_path = getattr(plugin_manage_api, "get_plugin_path", None)
            if callable(get_plugin_path):
                plugin_root = str(get_plugin_path("selfie_painter_v2"))
        except Exception:
            plugin_root = None

        if not plugin_root:
            p = Path(__file__).resolve()
            for _ in range(6):
                p = p.parent
                if (p / "_manifest.json").exists():
                    plugin_root = str(p)
                    break

        if not plugin_root:
            plugin_root = str(Path(__file__).resolve().parent.parent.parent)

        data_dir = Path(plugin_root) / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        return str(data_dir / "schedule.db")

    def __init__(self, db_path: str | None = None):
        """初始化数据库连接参数。"""
        self.db_path: str = db_path or self.resolve_db_path()

    def _get_conn(self) -> sqlite3.Connection:
        """获取当前线程的连接。"""
        if not hasattr(self._thread_local, "conn") or self._thread_local.conn is None:
            conn = sqlite3.connect(
                self.db_path,
                check_same_thread=False,
                timeout=30.0,
            )
            conn.row_factory = sqlite3.Row
            _ = conn.execute("PRAGMA journal_mode=WAL")
            _ = conn.execute("PRAGMA foreign_keys=ON")
            _ = conn.execute("PRAGMA synchronous=NORMAL")
            self._thread_local.conn = conn
        return self._thread_local.conn

    @contextmanager
    def _transaction(self):
        """事务上下文。"""
        conn = self._get_conn()
        try:
            yield conn
            conn.commit()
        except Exception as exc:
            conn.rollback()
            logger.error("[ScheduleDB] 事务回滚: %s", exc)
            raise

    def ensure_schema(self) -> None:
        """幂等建表。"""
        with self._transaction() as conn:
            _ = conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schedule_items (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    schedule_date TEXT NOT NULL,
                    start_min     INTEGER NOT NULL,
                    end_min       INTEGER NOT NULL,
                    activity_type TEXT NOT NULL DEFAULT 'other',
                    description   TEXT NOT NULL DEFAULT '',
                    mood          TEXT NOT NULL DEFAULT 'neutral',
                    source        TEXT NOT NULL DEFAULT 'template',
                    created_at    TEXT NOT NULL
                )
                """
            )
            _ = conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_schedule_items_date
                ON schedule_items (schedule_date)
                """
            )
            _ = conn.execute(
                """
                CREATE TABLE IF NOT EXISTS state (
                    key         TEXT PRIMARY KEY,
                    value       TEXT NOT NULL,
                    updated_at  TEXT NOT NULL
                )
                """
            )
        logger.debug("[ScheduleDB] schema 初始化完成: %s (v%s)", self.db_path, _DB_SCHEMA_VERSION)

    def get_state(self, key: str) -> str | None:
        """读取状态值。"""
        conn = self._get_conn()
        row: sqlite3.Row | None = conn.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
        return str(row["value"]) if row else None

    def set_state(self, key: str, value: str) -> None:
        """写入状态值。"""
        now = datetime.now(timezone.utc).isoformat()
        with self._transaction() as conn:
            _ = conn.execute(
                "INSERT OR REPLACE INTO state (key, value, updated_at) VALUES (?,?,?)",
                (key, value, now),
            )

    def replace_schedule_items(self, schedule_date: str, items: list[dict[str, Any]]) -> None:
        """同日全量替换（DELETE + INSERT）。"""
        now = datetime.now(timezone.utc).isoformat()
        with self._transaction() as conn:
            _ = conn.execute("DELETE FROM schedule_items WHERE schedule_date=?", (schedule_date,))
            for item in items:
                _ = conn.execute(
                    """
                    INSERT INTO schedule_items
                    (schedule_date, start_min, end_min, activity_type, description, mood, source, created_at)
                    VALUES (?,?,?,?,?,?,?,?)
                    """,
                    (
                        schedule_date,
                        int(item["start_min"]),
                        int(item["end_min"]),
                        str(item.get("activity_type", "other")),
                        str(item.get("description", "")),
                        str(item.get("mood", "neutral")),
                        str(item.get("source", "template")),
                        now,
                    ),
                )

    def list_schedule_items(self, schedule_date: str) -> list[dict[str, Any]]:
        """按日期查询日程项。"""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM schedule_items WHERE schedule_date=? ORDER BY start_min ASC",
            (schedule_date,),
        ).fetchall()
        return [dict(row) for row in rows]

    def list_schedule_items_by_range(
        self, start_date: str, end_date: str
    ) -> list[dict[str, Any]]:
        """
        按日期范围查询日程项。

        Args:
            start_date: 开始日期（格式：YYYY-MM-DD）
            end_date: 结束日期（格式：YYYY-MM-DD）

        Returns:
            list[dict]: 日程项列表，按日期和时间排序

        示例：
            # 查询最近3天的日程
            items = db.list_schedule_items_by_range("2026-03-01", "2026-03-03")
        """
        conn = self._get_conn()
        rows = conn.execute(
            """
            SELECT * FROM schedule_items
            WHERE schedule_date BETWEEN ? AND ?
            ORDER BY schedule_date ASC, start_min ASC
            """,
            (start_date, end_date),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_dates_with_schedule(self, start_date: str, end_date: str) -> list[str]:
        """
        获取指定日期范围内有日程的日期列表。

        Args:
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            list[str]: 有日程的日期列表
        """
        conn = self._get_conn()
        rows = conn.execute(
            """
            SELECT DISTINCT schedule_date FROM schedule_items
            WHERE schedule_date BETWEEN ? AND ?
            ORDER BY schedule_date ASC
            """,
            (start_date, end_date),
        ).fetchall()
        return [str(row["schedule_date"]) for row in rows]

    def cleanup_old_schedule_items(self, retention_days: int) -> int:
        """
        清理旧的日程数据。

        Args:
            retention_days: 保留天数，超过此天数的数据会被删除

        Returns:
            int: 删除的记录数

        注意：
            - retention_days = -1 表示永久保留，不执行清理
            - 清理的是日程数据本身，不是历史摘要
        """
        if retention_days < 0:
            logger.info("[ScheduleDB] 永久保留模式，跳过清理")
            return 0

        from datetime import datetime, timedelta

        cutoff_date = (datetime.now() - timedelta(days=retention_days)).strftime("%Y-%m-%d")

        with self._transaction() as conn:
            cursor = conn.execute(
                "DELETE FROM schedule_items WHERE schedule_date < ?",
                (cutoff_date,)
            )
            deleted_count = cursor.rowcount

        logger.info(
            "[ScheduleDB] 清理完成：删除 %d 条记录（%s 之前）",
            deleted_count, cutoff_date
        )
        return deleted_count
