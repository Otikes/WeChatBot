"""Database schema and initialization.

Idempotent — safe to call on every startup.
"""

import sqlite3
import threading
from pathlib import Path


class _CursorProxy:
    """Materialized cursor — safe to use after the DB lock is released."""

    def __init__(self, cursor):
        self._rows = cursor.fetchall()
        self._index = 0
        self.rowcount = cursor.rowcount
        self.lastrowid = cursor.lastrowid

    def fetchone(self):
        if self._index >= len(self._rows):
            return None
        row = self._rows[self._index]
        self._index += 1
        return row

    def fetchmany(self, size=1):
        rows = self._rows[self._index:self._index + size]
        self._index += len(rows)
        return rows

    def fetchall(self):
        rows = self._rows[self._index:]
        self._index = len(self._rows)
        return rows

    def __iter__(self):
        return iter(self._rows)


class ThreadSafeConnection:
    """Proxy serializing all sqlite3 calls behind a single RLock.

    WeChatBot shares one connection across poll workers, the web server and
    the health monitor; sqlite3 connections are not thread-reentrant,
    which caused sporadic InterfaceError / UNIQUE-constraint failures
    under concurrent inserts (silently dropping messages).  Results are
    materialized so cursors remain usable after the lock is released.
    """

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self._lock = threading.RLock()

    def execute(self, sql, params=()):
        with self._lock:
            return _CursorProxy(self._conn.execute(sql, params))

    def executemany(self, sql, seq_of_params):
        with self._lock:
            return _CursorProxy(self._conn.executemany(sql, seq_of_params))

    def executescript(self, script):
        with self._lock:
            self._conn.executescript(script)
            return self

    def commit(self):
        with self._lock:
            self._conn.commit()

    def rollback(self):
        with self._lock:
            self._conn.rollback()

    def close(self):
        with self._lock:
            self._conn.close()

    def __enter__(self):
        self._lock.acquire()
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type is None:
                self._conn.commit()
            else:
                self._conn.rollback()
        finally:
            self._lock.release()
        return False


SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
PRAGMA busy_timeout=5000;
PRAGMA synchronous=NORMAL;

-- Every message received from any monitored group chat
CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id  TEXT    UNIQUE NOT NULL,
    chat_id     TEXT    NOT NULL,
    sender_id   TEXT    NOT NULL,
    sender_name TEXT    NOT NULL,
    content     TEXT    NOT NULL DEFAULT '',
    msg_type    INTEGER NOT NULL DEFAULT 1,
    timestamp   INTEGER NOT NULL,
    created_at  INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);

-- Fast lookup: "all messages in chat X since time T"
CREATE INDEX IF NOT EXISTS idx_msg_chat_time
    ON messages(chat_id, timestamp DESC);

-- Fast lookup: "last message from user S in chat X"
CREATE INDEX IF NOT EXISTS idx_msg_chat_sender_time
    ON messages(chat_id, sender_id, timestamp DESC);

-- Materialized last-message-time per user per chat.
-- Updated via UPSERT on every message insert.
CREATE TABLE IF NOT EXISTS user_last_message (
    chat_id        TEXT    NOT NULL,
    sender_id      TEXT    NOT NULL,
    sender_name    TEXT    NOT NULL,
    last_timestamp INTEGER NOT NULL,
    PRIMARY KEY (chat_id, sender_id)
);

-- Prevent duplicate trigger responses.
CREATE TABLE IF NOT EXISTS trigger_log (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id            TEXT    NOT NULL,
    requester_id       TEXT    NOT NULL,
    trigger_message_id TEXT    NOT NULL,
    processed_at       INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);

-- Per-group long-term memory. Consolidates conversation history into
-- a first-person diary-style text that is injected into every prompt,
-- giving the bot a persistent sense of identity and group awareness.
CREATE TABLE IF NOT EXISTS group_memory (
    chat_id           TEXT    PRIMARY KEY,
    memory_text       TEXT    NOT NULL DEFAULT '',
    message_count     INTEGER NOT NULL DEFAULT 0,
    last_message_id   TEXT,
    last_consolidated REAL,
    created_at        REAL    NOT NULL DEFAULT (unixepoch()),
    updated_at        REAL    NOT NULL DEFAULT (unixepoch())
);

-- Single-row structured application state for onboarding drafts.
-- Final runtime configuration is still mirrored to .env for compatibility
-- with the existing config loader.
CREATE TABLE IF NOT EXISTS onboarding_state (
    id                      INTEGER PRIMARY KEY CHECK (id = 1),
    step1_done              INTEGER NOT NULL DEFAULT 0,
    step2_done              INTEGER NOT NULL DEFAULT 0,
    step3_done              INTEGER NOT NULL DEFAULT 0,
    step4_done              INTEGER NOT NULL DEFAULT 0,
    onboarding_done         INTEGER NOT NULL DEFAULT 0,
    wcdb_key                TEXT    NOT NULL DEFAULT '',
    wxid                    TEXT    NOT NULL DEFAULT '',
    db_path                 TEXT    NOT NULL DEFAULT '',
    bot_display_name        TEXT    NOT NULL DEFAULT '',
    wechat_groups           TEXT    NOT NULL DEFAULT '*',
    wechat_backend          TEXT    NOT NULL DEFAULT 'wcdb',
    ai_backend              TEXT    NOT NULL DEFAULT 'openai_compatible',
    deepseek_api_key        TEXT    NOT NULL DEFAULT '',
    deepseek_base_url       TEXT    NOT NULL DEFAULT 'https://api.deepseek.com',
    deepseek_model          TEXT    NOT NULL DEFAULT '',
    openai_api_key          TEXT    NOT NULL DEFAULT '',
    openai_base_url         TEXT    NOT NULL DEFAULT 'https://api.openai.com/v1',
    openai_model            TEXT    NOT NULL DEFAULT '',
    anthropic_api_key       TEXT    NOT NULL DEFAULT '',
    anthropic_base_url      TEXT    NOT NULL DEFAULT 'https://api.anthropic.com',
    summarize_model         TEXT    NOT NULL DEFAULT '',
    fun_enabled             INTEGER NOT NULL DEFAULT 1,
    proactive_enabled       INTEGER NOT NULL DEFAULT 0,
    sticky_mention_enabled  INTEGER NOT NULL DEFAULT 1,
    created_at              INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    updated_at              INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);

CREATE INDEX IF NOT EXISTS idx_trigger_chat_time
    ON trigger_log(chat_id, processed_at DESC);
"""


def initialize_db(db_path: str) -> sqlite3.Connection:
    """Initialize the SQLite database, creating tables if they don't exist.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        A ThreadSafeConnection proxy wrapping a sqlite3.Connection with
        WAL mode enabled and row_factory set.
    """
    # Ensure the parent directory exists
    db_file = Path(db_path)
    db_file.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    return ThreadSafeConnection(conn)
