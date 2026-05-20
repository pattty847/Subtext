"""
SQLite-backed chat thread store for the private web service.

Threads anchor optionally to a transcript via a content hash so that opening
the same transcript later re-surfaces prior conversations. The synchronous
sqlite3 API is wrapped in run_in_executor to stay non-blocking inside the
FastAPI event loop — matching the existing Ollama/LM Studio bridging pattern.
"""
from __future__ import annotations

import asyncio
import hashlib
import sqlite3
import time
import uuid
from pathlib import Path
from typing import List, Optional


def transcript_hash(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    normalized = text.strip()
    if not normalized:
        return None
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()


class ChatStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    async def _run(self, fn, *args, **kwargs):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    async def init_schema(self) -> None:
        def _init() -> None:
            with self._connect() as conn:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS threads (
                        id              TEXT PRIMARY KEY,
                        transcript_hash TEXT,
                        transcript_text TEXT,
                        title           TEXT NOT NULL DEFAULT '',
                        model           TEXT NOT NULL DEFAULT '',
                        created_at      REAL NOT NULL,
                        updated_at      REAL NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_threads_transcript_hash
                        ON threads(transcript_hash);
                    CREATE INDEX IF NOT EXISTS idx_threads_updated_at
                        ON threads(updated_at DESC);

                    CREATE TABLE IF NOT EXISTS messages (
                        id          INTEGER PRIMARY KEY AUTOINCREMENT,
                        thread_id   TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
                        role        TEXT NOT NULL,
                        content     TEXT NOT NULL,
                        created_at  REAL NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_messages_thread
                        ON messages(thread_id, id);
                    """
                )

        await self._run(_init)

    async def create_thread(
        self,
        transcript_hash_value: Optional[str],
        transcript_text: Optional[str],
        title: str,
        model: str,
    ) -> dict:
        def _create() -> dict:
            now = time.time()
            tid = uuid.uuid4().hex
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO threads"
                    "(id, transcript_hash, transcript_text, title, model, created_at, updated_at) "
                    "VALUES(?, ?, ?, ?, ?, ?, ?)",
                    (tid, transcript_hash_value, transcript_text, title, model, now, now),
                )
            return {
                "id": tid,
                "transcript_hash": transcript_hash_value,
                "transcript_text": transcript_text,
                "title": title,
                "model": model,
                "created_at": now,
                "updated_at": now,
                "message_count": 0,
            }

        return await self._run(_create)

    async def list_threads(
        self,
        transcript_hash_value: Optional[str] = None,
        limit: int = 100,
    ) -> List[dict]:
        def _list() -> List[dict]:
            with self._connect() as conn:
                if transcript_hash_value:
                    rows = conn.execute(
                        "SELECT t.*, "
                        "       (SELECT COUNT(*) FROM messages m WHERE m.thread_id = t.id) AS message_count "
                        "FROM threads t WHERE transcript_hash = ? "
                        "ORDER BY updated_at DESC LIMIT ?",
                        (transcript_hash_value, limit),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        "SELECT t.*, "
                        "       (SELECT COUNT(*) FROM messages m WHERE m.thread_id = t.id) AS message_count "
                        "FROM threads t ORDER BY updated_at DESC LIMIT ?",
                        (limit,),
                    ).fetchall()
            return [dict(r) for r in rows]

        return await self._run(_list)

    async def get_thread(self, thread_id: str) -> Optional[dict]:
        def _get() -> Optional[dict]:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT * FROM threads WHERE id = ?", (thread_id,)
                ).fetchone()
            return dict(row) if row else None

        return await self._run(_get)

    async def get_messages(self, thread_id: str) -> List[dict]:
        def _get() -> List[dict]:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT role, content, created_at FROM messages "
                    "WHERE thread_id = ? ORDER BY id ASC",
                    (thread_id,),
                ).fetchall()
            return [dict(r) for r in rows]

        return await self._run(_get)

    async def append_messages(
        self,
        thread_id: str,
        new_messages: List[dict],
        model: Optional[str] = None,
        title_if_empty: Optional[str] = None,
    ) -> None:
        """Append messages and bump updated_at. Optionally set the title if the
        thread doesn't have one yet (used to backfill from the first user
        message)."""
        def _append() -> None:
            now = time.time()
            with self._connect() as conn:
                conn.execute("BEGIN")
                try:
                    for msg in new_messages:
                        conn.execute(
                            "INSERT INTO messages(thread_id, role, content, created_at) "
                            "VALUES(?, ?, ?, ?)",
                            (thread_id, msg["role"], msg["content"], now),
                        )
                    if title_if_empty:
                        conn.execute(
                            "UPDATE threads SET title = ? "
                            "WHERE id = ? AND (title IS NULL OR title = '')",
                            (title_if_empty, thread_id),
                        )
                    if model:
                        conn.execute(
                            "UPDATE threads SET model = ?, updated_at = ? WHERE id = ?",
                            (model, now, thread_id),
                        )
                    else:
                        conn.execute(
                            "UPDATE threads SET updated_at = ? WHERE id = ?",
                            (now, thread_id),
                        )
                    conn.execute("COMMIT")
                except Exception:
                    conn.execute("ROLLBACK")
                    raise

        await self._run(_append)

    async def delete_thread(self, thread_id: str) -> bool:
        def _delete() -> bool:
            with self._connect() as conn:
                cur = conn.execute("DELETE FROM threads WHERE id = ?", (thread_id,))
                return cur.rowcount > 0

        return await self._run(_delete)

    async def rename_thread(self, thread_id: str, title: str) -> bool:
        def _rename() -> bool:
            with self._connect() as conn:
                cur = conn.execute(
                    "UPDATE threads SET title = ?, updated_at = ? WHERE id = ?",
                    (title, time.time(), thread_id),
                )
                return cur.rowcount > 0

        return await self._run(_rename)
