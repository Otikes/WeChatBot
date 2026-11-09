"""Pure-Python WCDB client for WeChat 4.x — no native DLL required.

Replacement for the ``wcdb_api.dll`` ctypes client.  Reads the encrypted
SQLCipher databases directly:

1. keys are extracted from ``Weixin.exe`` memory (``Config.Cipher`` scan)
   and cached in ``%TEMP%/wechatauto_db/<account>/keys.json``;
2. each database is decrypted page-by-page into a temp cache;
3. queries run through the standard ``sqlite3`` module.

This avoids the proprietary, DRM-protected ``wcdb_api.dll`` entirely
(that DLL now self-destructs on load and raised
``wcdb_api.dll not found`` / ``wcdb_init failed`` during startup).

The public surface mirrors :class:`src.wechat.wcdb_client.WcdbNativeClient`
so ``WcdbBackend`` can switch implementations without other changes.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Optional

from .data_dir import find_wxid_and_dbpath
from .wxdb_reader import WeChatDB

logger = logging.getLogger(__name__)

DEFAULT_SESSION_LIMIT = 500
CONTACT_CACHE_SEC = 30.0
MEMBER_CACHE_SEC = 60.0


class LocalWcdbClient:
    """WCDB reader backed by pure-Python decryption (no ``wcdb_api.dll``)."""

    def __init__(self, dll_dir=None, config_path=None):
        # Signature kept compatible with WcdbNativeClient call sites.
        self._dll_dir = dll_dir
        self._config_path = config_path
        self._db: Optional[WeChatDB] = None
        self._base_dir = ""
        self._account = ""
        self._contacts_cache: tuple[float, list[dict]] = (0.0, [])
        self._members_cache: dict[str, tuple[float, list[dict]]] = {}
        self._lock = threading.Lock()

    # ── Lifecycle ─────────────────────────────────────────────────────

    def init(self) -> None:
        """Open WeChatDB and verify at least the session database is readable."""
        custom_dir = ""
        try:
            from src.config import load_config
            custom_dir = load_config().wechat_data_dir
        except Exception as exc:
            # Config may be incomplete during onboarding — auto-detection
            # still works without it.
            logger.debug("load_config unavailable, using auto-detection: %s", exc)

        wxid, base_dir = find_wxid_and_dbpath(custom_dir)
        self._account = wxid
        self._base_dir = base_dir
        logger.info("Opening WeChat data: account=%s base=%s", wxid, base_dir)

        started = time.monotonic()
        with self._lock:
            self._db = WeChatDB(db_dir=base_dir, account=wxid)
        logger.info(
            "WeChatDB ready in %.1fs (%d/%d databases keyed)",
            time.monotonic() - started,
            len(self._db._keys),
            len(self._db._db_files),
        )

        unkeyed = {
            str(rel).replace("\\", "/")
            for rel in (getattr(self._db, "unkeyed", None) or [])
        }
        if "session/session.db" in unkeyed:
            raise RuntimeError(
                "无法解密微信数据库：未能在微信进程内存中找到会话库密钥。"
                "请确认微信已登录并保持运行，然后重试。"
            )

    def open(self) -> bool:
        """Compatibility hook — WeChatDB is opened in :meth:`init`."""
        if self._db is None:
            raise RuntimeError("LocalWcdbClient.init() was not called")
        self.get_sessions(limit=1)
        return True

    def close(self) -> None:
        with self._lock:
            self._db = None
        self._members_cache.clear()
        self._contacts_cache = (0.0, [])

    def health(self) -> bool:
        try:
            self._require_db()
            self.get_sessions(limit=1)
            return True
        except Exception as exc:
            logger.warning("LocalWcdbClient health check failed: %s", exc)
            return False

    # ── Sessions / contacts / names ───────────────────────────────────

    def get_sessions(self, limit: int = DEFAULT_SESSION_LIMIT) -> list[dict]:
        db = self._require_db()
        rows = db.get_sessions(limit=max(1, int(limit or DEFAULT_SESSION_LIMIT)))
        names = self._nickname_map(db)
        out: list[dict] = []
        for row in rows:
            username = str(row.get("username") or "").strip()
            if not username:
                continue
            display = names.get(username) or ""
            if display == username:
                display = ""
            out.append({
                **row,
                "username": username,
                "nick_name": display,
                "remark": display,
                "display": display,
                "chat": display,
                "is_group": username.endswith("@chatroom"),
            })
        return out

    def get_contacts(self, limit: int = 5000) -> list[dict]:
        """Return all contacts (``contact.db``) — used for group/friend discovery."""
        cached_at, cached_rows = self._contacts_cache
        if cached_rows and time.monotonic() - cached_at < CONTACT_CACHE_SEC:
            return cached_rows[: max(1, int(limit or 5000))]

        db = self._require_db()
        conn = db._contact_conn()
        if conn is None:
            return []
        try:
            rows = conn.execute(
                "SELECT username, nick_name, remark FROM contact"
            ).fetchall()
        except Exception as exc:
            logger.warning("Failed to read contact.db: %s", exc)
            return []
        finally:
            conn.close()

        out: list[dict] = []
        for row in rows:
            username = str(row["username"] or "").strip()
            if not username:
                continue
            nickname = str(row["nick_name"] or "").strip()
            remark = str(row["remark"] or "").strip()
            display = remark or nickname or username
            out.append({
                "username": username,
                "nick_name": nickname,
                "remark": remark,
                "display": display,
                "nickname": display,
                "name": username,
            })
        self._contacts_cache = (time.monotonic(), out)
        return out[: max(1, int(limit or 5000))]

    def resolve_nickname(self, wxid: str) -> str:
        """Return a human-readable name for ``wxid`` (falls back to the wxid)."""
        user = str(wxid or "").strip()
        if not user:
            return ""
        db = self._require_db()
        names = self._nickname_map(db)
        name = names.get(user)
        if name:
            return name
        try:
            name = db.get_nickname(user)
        except Exception:
            name = ""
        if name and name != user:
            if getattr(db, "_nick_cache", None) is not None:
                db._nick_cache[user] = name
            return name
        return user

    def get_display_names(self, wxids: list[str]) -> dict[str, str]:
        return {str(wxid): self.resolve_nickname(str(wxid)) for wxid in (wxids or [])}

    def get_group_members(self, chatroom: str) -> list[dict]:
        room = str(chatroom or "").strip()
        if not room:
            return []
        cached = self._members_cache.get(room)
        if cached and time.monotonic() - cached[0] < MEMBER_CACHE_SEC:
            return cached[1]
        db = self._require_db()
        try:
            members = db.get_group_members(room)
        except Exception as exc:
            logger.warning("Failed to read members of %s: %s", room, exc)
            return []
        self._members_cache[room] = (time.monotonic(), members)
        return members

    # ── Messages ─────────────────────────────────────────────────────

    def get_messages(self, talker: str, limit: int = 50, offset: int = 0) -> list[dict]:
        """Read recent messages of a chat, normalised to WcdbBackend's field names."""
        who = str(talker or "").strip()
        if not who:
            return []
        db = self._require_db()
        rows = db.get_messages(who, limit=max(1, int(limit)), offset=max(0, int(offset)))
        out: list[dict] = []
        for row in rows:
            content = row.get("content") or ""
            sender = row.get("sender_username") or ""
            # WeChat 4.x group rows prefix the body with "<sender wxid>:\n".
            if sender and content.startswith(f"{sender}:\n"):
                content = content[len(sender) + 2:]
            out.append({
                # Keep raw ids for dedup; `shard` disambiguates local_id across
                # message_N.db shards, so make the dedup id composite.
                "local_id": row.get("local_id"),
                "server_id": row.get("server_id"),
                "shard": row.get("shard"),
                "sender_id": row.get("sender_id"),
                "sender_username": sender,
                "message_content": content,
                "content": content,
                "local_type": row.get("local_type") or 0,
                "msg_type": row.get("local_type") or 0,
                "create_time": row.get("create_time") or 0,
                "timestamp": row.get("create_time") or 0,
            })
        return out

    # ── Internals ────────────────────────────────────────────────────

    def _require_db(self) -> WeChatDB:
        if self._db is None:
            raise RuntimeError("LocalWcdbClient.init() was not called")
        return self._db

    @staticmethod
    def _nickname_map(db: WeChatDB) -> dict[str, str]:
        try:
            return db.nickname_map()
        except Exception as exc:
            logger.warning("nickname_map failed: %s", exc)
            return {}
