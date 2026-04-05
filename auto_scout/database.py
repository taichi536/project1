"""
送信済みスカウトの追跡とログ管理、およびタグ→テンプレートのマッピング管理。
"""
import sqlite3
import os
from datetime import datetime
from typing import Dict, List, Optional
from .models import ScoutResult


class Database:
    def __init__(self, db_path: str):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sent_scouts (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    platform    TEXT NOT NULL,
                    candidate_id TEXT NOT NULL,
                    candidate_name TEXT,
                    tag         TEXT,
                    position    TEXT,
                    message     TEXT,
                    success     INTEGER NOT NULL DEFAULT 1,
                    error       TEXT,
                    sent_at     TEXT NOT NULL,
                    UNIQUE(platform, candidate_id)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_platform_candidate
                ON sent_scouts(platform, candidate_id)
            """)
            # タグ → テンプレートのマッピング（ダッシュボードから管理）
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tag_mappings (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    platform   TEXT NOT NULL,
                    tag        TEXT NOT NULL,
                    position   TEXT NOT NULL,
                    note       TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(platform, tag)
                )
            """)
            # タグ機能がないプラットフォーム向けのURLキュー
            conn.execute("""
                CREATE TABLE IF NOT EXISTS scout_queue (
                    id             INTEGER PRIMARY KEY AUTOINCREMENT,
                    platform       TEXT NOT NULL,
                    profile_url    TEXT NOT NULL,
                    candidate_name TEXT,
                    position       TEXT NOT NULL,
                    note           TEXT,
                    status         TEXT NOT NULL DEFAULT 'pending',
                    added_at       TEXT NOT NULL,
                    processed_at   TEXT,
                    UNIQUE(platform, profile_url)
                )
            """)

    def already_sent(self, platform: str, candidate_id: str) -> bool:
        """このプラットフォームのこの候補者にすでにスカウトを送信済みか確認する。"""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM sent_scouts WHERE platform=? AND candidate_id=? AND success=1",
                (platform, candidate_id),
            ).fetchone()
        return row is not None

    def record(self, result: ScoutResult) -> None:
        """スカウト送信結果を記録する。"""
        c = result.candidate
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO sent_scouts
                    (platform, candidate_id, candidate_name, tag, position, message, success, error, sent_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    c.platform,
                    c.candidate_id,
                    c.name,
                    c.tag,
                    c.position,
                    result.sent_message,
                    1 if result.success else 0,
                    result.error,
                    result.sent_at.isoformat(),
                ),
            )

    def daily_sent_count(self, platform: str) -> int:
        """今日送信したスカウト数を返す。"""
        today = datetime.now().strftime("%Y-%m-%d")
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM sent_scouts WHERE platform=? AND sent_at LIKE ? AND success=1",
                (platform, f"{today}%"),
            ).fetchone()
        return row[0] if row else 0

    # ------------------------------------------------------------------
    # タグ→テンプレート マッピング管理
    # ------------------------------------------------------------------

    def get_tag_mappings(self, platform: Optional[str] = None) -> List[dict]:
        """マッピング一覧を返す。platform を指定するとそのプラットフォームのみ。"""
        with self._connect() as conn:
            if platform:
                rows = conn.execute(
                    "SELECT * FROM tag_mappings WHERE platform=? ORDER BY platform, tag",
                    (platform,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM tag_mappings ORDER BY platform, tag"
                ).fetchall()
        return [dict(r) for r in rows]

    def get_tag_to_position(self, platform: str) -> Dict[str, str]:
        """指定プラットフォームの {タグ名: テンプレート名} 辞書を返す。"""
        rows = self.get_tag_mappings(platform)
        return {r["tag"]: r["position"] for r in rows}

    def upsert_tag_mapping(self, platform: str, tag: str, position: str, note: str = "") -> None:
        """マッピングを追加または更新する。"""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO tag_mappings (platform, tag, position, note, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(platform, tag) DO UPDATE SET
                    position=excluded.position,
                    note=excluded.note
                """,
                (platform, tag, position, note, datetime.now().isoformat()),
            )

    def delete_tag_mapping(self, mapping_id: int) -> None:
        """マッピングを削除する。"""
        with self._connect() as conn:
            conn.execute("DELETE FROM tag_mappings WHERE id=?", (mapping_id,))

    # ------------------------------------------------------------------
    # スカウトキュー管理（タグ機能のないプラットフォーム向け）
    # ------------------------------------------------------------------

    def queue_add(self, platform: str, profile_url: str, position: str,
                  candidate_name: str = "", note: str = "") -> int:
        """キューにURLを追加する。重複の場合は pendingにリセットして更新。"""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO scout_queue
                    (platform, profile_url, candidate_name, position, note, status, added_at)
                VALUES (?, ?, ?, ?, ?, 'pending', ?)
                ON CONFLICT(platform, profile_url) DO UPDATE SET
                    candidate_name = excluded.candidate_name,
                    position       = excluded.position,
                    note           = excluded.note,
                    status         = 'pending',
                    added_at       = excluded.added_at,
                    processed_at   = NULL
                """,
                (platform, profile_url, candidate_name, position, note,
                 datetime.now().isoformat()),
            )
            row = conn.execute(
                "SELECT id FROM scout_queue WHERE platform=? AND profile_url=?",
                (platform, profile_url),
            ).fetchone()
        return row["id"] if row else -1

    def queue_get_pending(self, platform: Optional[str] = None) -> List[dict]:
        """処理待ちのキューアイテムを返す。"""
        with self._connect() as conn:
            if platform:
                rows = conn.execute(
                    "SELECT * FROM scout_queue WHERE status='pending' AND platform=?"
                    " ORDER BY added_at",
                    (platform,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM scout_queue WHERE status='pending' ORDER BY platform, added_at"
                ).fetchall()
        return [dict(r) for r in rows]

    def queue_get_all(self, platform: Optional[str] = None, limit: int = 100) -> List[dict]:
        """全キューアイテムを返す（ダッシュボード表示用）。"""
        with self._connect() as conn:
            if platform:
                rows = conn.execute(
                    "SELECT * FROM scout_queue WHERE platform=?"
                    " ORDER BY added_at DESC LIMIT ?",
                    (platform, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM scout_queue ORDER BY added_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [dict(r) for r in rows]

    def queue_update_status(self, queue_id: int, status: str) -> None:
        """ステータスを更新する。status: 'sent' | 'error' | 'skipped'"""
        with self._connect() as conn:
            conn.execute(
                "UPDATE scout_queue SET status=?, processed_at=? WHERE id=?",
                (status, datetime.now().isoformat(), queue_id),
            )

    def queue_delete(self, queue_id: int) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM scout_queue WHERE id=?", (queue_id,))

    def get_stats(self) -> dict:
        """プラットフォームごとの送信統計を返す。"""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT platform,
                       COUNT(*) as total,
                       SUM(success) as succeeded,
                       MAX(sent_at) as last_sent
                FROM sent_scouts
                GROUP BY platform
                """
            ).fetchall()
        return {
            row["platform"]: {
                "total": row["total"],
                "succeeded": row["succeeded"],
                "last_sent": row["last_sent"],
            }
            for row in rows
        }
