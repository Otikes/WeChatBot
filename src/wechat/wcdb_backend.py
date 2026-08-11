"""
WCDB Native Backend — zero external dependencies.

Reads WeChat messages directly from the encrypted WCDB database via
patched wcdb_api.dll (ctypes).  Uses WeChatWindowController for sending.

WCDB native access — reads encrypted database in-process, no external dependencies.
"""
import concurrent.futures
import hashlib
import json
import logging
import os
import re
import threading
import time
from collections import deque
from pathlib import Path
from typing import Optional

from .base import AbstractWeChatBackend, MessageCallback
from .wcdb_client import WcdbNativeClient
from .window_controller import WeChatWindowController
from .helpers import DedupSet, format_nontext_content, normalize_msg_type
from src.config import webot_data_path

logger = logging.getLogger(__name__)

DEFAULT_POLL_SEC = 1.0
MAX_DEDUP_SIZE = 5000
MAX_CONSECUTIVE_ERRORS = 5   # trigger reinit after this many consecutive failures


class WcdbBackend(AbstractWeChatBackend):
    """Native WCDB backend — database read + window send.

    Reads messages directly from WeChat's session.db via wcdb_api.dll
    with one-byte DRM patch. Sends via WeChatWindowController.

    Usage:
        backend = WcdbBackend(
            bot_display_name="机器人",
            groups=["摸鱼群"],
            poll_sec=1.0,
        )
        backend.start(my_callback)
    """

    def __init__(self,
                 bot_display_name: str = "",
                 groups: list[str] | None = None,
                 poll_sec: float = DEFAULT_POLL_SEC,
                 store=None,
                 config=None):
        self._bot_name = bot_display_name
        self._groups = groups or []
        self._poll_sec = poll_sec
        self._store = store  # MessageStore fallback for name resolution
        self._running = False
        self._client: Optional[WcdbNativeClient] = None
        self._window = WeChatWindowController()
        self._talker_ids: dict[str, str] = {}
        self._known_ids = DedupSet(max_size=MAX_DEDUP_SIZE)
        # Thread safety: WCDB DLL (ctypes) may not be thread-safe internally.
        # All _client calls are serialized through this lock.
        self._client_lock = threading.Lock()
        # Callback thread pool — fire-and-forget AI calls so the poll loop
        # never blocks on a slow summarization.
        self._pool: concurrent.futures.ThreadPoolExecutor | None = None
        # Voice recognition pipeline (lazy-init when voice_asr_enabled)
        self._voice: Optional[object] = None
        self._voice_config = config
        # Recent own sends: (talker, content, timestamp).  Content-based self-skip so
        # the bot never reacts to its own replies, even when the configured
        # display name doesn't match the WCDB-resolved sender name.
        self._recent_sends: deque = deque(maxlen=32)

    # ── Public API ─────────────────────────────────────────────────

    def start(self, callback: MessageCallback) -> None:
        if not self._groups:
            logger.error("No groups configured. Set WECHAT_GROUPS in .env")
            return

        logger.info(
            "WcdbBackend starting (groups=%s, poll=%ss, bot=%r)",
            self._groups, self._poll_sec, self._bot_name,
        )

        # Init and open database
        try:
            self._client = WcdbNativeClient()
            self._client.init()
            self._client.open()
            logger.info("WCDB database opened successfully")
        except Exception as e:
            if isinstance(e, (KeyboardInterrupt, SystemExit)):
                raise
            logger.error("Failed to initialize WCDB: %s", e)
            # Push error to Web UI so the user sees a recovery path
            try:
                from src.web.server import update_status
                update_status(running=False, error=str(e))
            except Exception:
                pass
            return

        # Resolve group talker IDs
        self._resolve_groups()

        if not self._talker_ids:
            logger.error("No groups resolved. Check WECHAT_GROUPS.")
            return

        # Pre-find WeChat window
        hwnd = self._window.find_hwnd()
        if hwnd:
            logger.info("WeChat window pre-detected: HWND=%s", hwnd)
        else:
            logger.warning("WeChat window not found — will retry on first send")

        self._pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=4, thread_name_prefix="bot-cb-",
        )
        self._running = True
        consecutive_errors = 0

        # Import once to avoid per-iteration overhead
        from src.web.server import is_shutting_down as _is_shutting_down

        try:
            while self._running and not _is_shutting_down():
                try:
                    self._poll_cycle(callback)
                    consecutive_errors = 0
                except KeyboardInterrupt:
                    break
                except Exception as e:
                    consecutive_errors += 1

                    # After MAX_CONSECUTIVE_ERRORS consecutive failures,
                    # attempt full reinitialization (WeChat may have restarted).
                    if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                        logger.error(
                            "Hit %d consecutive errors — attempting "
                            "reinitialization...", consecutive_errors,
                        )
                        try:
                            self._reinitialize()
                            consecutive_errors = 0
                            continue
                        except Exception as reinit_err:
                            logger.error(
                                "Reinitialization failed: %s", reinit_err,
                            )
                            # Fall through to backoff; will retry next cycle.
                            push_error = str(reinit_err)
                            try:
                                from src.web.server import update_status
                                update_status(error=push_error)
                            except Exception:
                                pass

                    wait = min(2 ** min(consecutive_errors % MAX_CONSECUTIVE_ERRORS, 5), 30)
                    logger.warning(
                        "Poll error #%d (%s): %s. Retry in %ss...",
                        consecutive_errors, type(e).__name__, e, wait,
                    )
                    time.sleep(wait)
        finally:
            # Drain in-flight callbacks gracefully
            self._pool.shutdown(wait=True, cancel_futures=True)
            self._pool = None
            if self._client:
                self._client.close()
        logger.info("WcdbBackend stopped.")

    def send_text(self, chat_id: str, content: str) -> bool:
        if not content:
            return False

        group_name = self._talker_to_name(chat_id)
        if not group_name:
            logger.error("Cannot resolve chat_id=%s to group name", chat_id)
            return False

        return self._send_and_confirm(group_name, chat_id, content)

    def stop(self) -> None:
        self._running = False
        if self._pool:
            self._pool.shutdown(wait=False)

    # ── Recovery ─────────────────────────────────────────────────────

    def _reinitialize(self) -> None:
        """Close and re-open the WCDB client after persistent errors.

        Called when the poll loop hits MAX_CONSECUTIVE_ERRORS consecutive
        failures — typically because WeChat was restarted and the DB handle
        or HWND became stale.
        """
        logger.warning("Reinitializing WCDB backend after consecutive errors...")
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
        try:
            self._client = WcdbNativeClient()
            self._client.init()
            self._client.open()
            logger.info("WCDB reinitialized successfully")
        except Exception as e:
            logger.error("WCDB reinitialization failed: %s", e)
            raise
        # Clear dedup set — WCDB may return messages with new IDs
        self._known_ids = DedupSet(max_size=MAX_DEDUP_SIZE)
        # Re-resolve groups (talker IDs may have changed)
        self._resolve_groups()
        # Re-find WeChat window
        hwnd = self._window.find_hwnd()
        if hwnd:
            logger.info("WeChat window re-detected: HWND=%s", hwnd)
        else:
            logger.warning("WeChat window not found after reinit")

    # ── Group resolution ────────────────────────────────────────────

    @staticmethod
    def _record_text(record: dict, *keys: str) -> str:
        """Return the first non-empty text field from a WCDB record."""
        for key in keys:
            value = record.get(key)
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
        return ""

    @classmethod
    def _record_username(cls, record: dict) -> str:
        """Extract a chat/contact username from varied WCDB JSON shapes."""
        return cls._record_text(
            record,
            "username",
            "userName",
            "UserName",
            "user_name",
            "name",
        )

    @classmethod
    def _record_display_name(cls, record: dict, username: str) -> str:
        """Extract a human-readable chat title from a session/contact row."""
        display = cls._record_text(
            record,
            "displayName",
            "displayname",
            "display_name",
            "display",
            "chat",
            "nickname",
            "nickName",
            "nick_name",
            "remark",
            "Remark",
            "conRemark",
            "last_sender_display_name",
            "lastSenderDisplayName",
        )
        return display if display and display != username else ""

    @staticmethod
    def _records_from_payload(payload, *list_keys: str) -> list[dict]:
        """Normalize list/dict WCDB payloads to a list of dict records."""
        if isinstance(payload, list):
            records = payload
        elif isinstance(payload, dict):
            records = []
            for key in list_keys:
                value = payload.get(key)
                if isinstance(value, list):
                    records = value
                    break
        else:
            records = []
        return [item for item in records if isinstance(item, dict)]

    @staticmethod
    def _safe_int(value, default: int = 0) -> int:
        """Convert cached numeric metadata without trusting file contents."""
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _merge_chatrooms(target: dict[str, dict], source: dict[str, dict]) -> int:
        """Merge chatroom metadata, preferring real names over raw IDs."""
        added = 0
        for username, info in source.items():
            if not username.endswith("@chatroom"):
                continue
            current = target.get(username)
            if current is None:
                target[username] = {
                    "name": str(info.get("name") or username).strip() or username,
                    "member_count": WcdbBackend._safe_int(info.get("member_count")),
                }
                added += 1
                continue

            new_name = str(info.get("name") or "").strip()
            if new_name and current.get("name") in ("", username):
                current["name"] = new_name
            current["member_count"] = max(
                WcdbBackend._safe_int(current.get("member_count")),
                WcdbBackend._safe_int(info.get("member_count")),
            )
        return added

    def _chatrooms_from_records(self, records) -> dict[str, dict]:
        """Build chatroom metadata from session/contact records."""
        chatrooms: dict[str, dict] = {}
        for record in self._records_from_payload(
            records, "sessions", "contacts", "chatrooms", "data",
        ):
            username = self._record_username(record)
            if not username.endswith("@chatroom"):
                continue

            display = self._record_display_name(record, username)
            if not display:
                try:
                    display = self._client.resolve_nickname(username)
                except Exception:
                    display = ""
            if not display or display == username:
                display = username

            member_count = 0
            try:
                members = self._client.get_group_members(username)
                if members:
                    member_count = len(members)
            except Exception:
                pass

            chatrooms[username] = {
                "name": display,
                "member_count": member_count,
            }
        return chatrooms

    def _chatrooms_from_contacts(self) -> dict[str, dict]:
        """Load group chats from contact records as a fallback to sessions."""
        get_contacts = getattr(self._client, "get_contacts", None)
        if not callable(get_contacts):
            return {}
        try:
            return self._chatrooms_from_records(get_contacts())
        except Exception as exc:
            logger.warning("Failed to load chatrooms from contacts: %s", exc)
            return {}

    @staticmethod
    def _load_cached_group_names() -> dict[str, dict]:
        """Load persisted chatroom metadata from group_names.json."""
        path = webot_data_path("group_names.json")
        if not path.exists():
            return {}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed to load cached group names from %s: %s", path, exc)
            return {}
        if not isinstance(raw, dict):
            return {}

        chatrooms: dict[str, dict] = {}
        for username, info in raw.items():
            username = str(username or "").strip()
            if not username.endswith("@chatroom"):
                continue
            if isinstance(info, dict):
                display = str(info.get("name") or info.get("display") or username).strip()
                member_count = WcdbBackend._safe_int(info.get("member_count"))
            else:
                display = str(info or username).strip()
                member_count = 0
            chatrooms[username] = {
                "name": display or username,
                "member_count": member_count,
            }
        if chatrooms:
            logger.info("Loaded %d cached group-name mappings from %s", len(chatrooms), path)
        return chatrooms

    def _add_configured_chatroom_ids(self, chatrooms: dict[str, dict]) -> int:
        """Accept explicit WECHAT_GROUPS entries like 123456@chatroom."""
        added = 0
        for group_name in self._groups:
            username = str(group_name or "").strip()
            if not username.endswith("@chatroom") or username in chatrooms:
                continue
            try:
                display = self._client.resolve_nickname(username)
            except Exception:
                display = ""
            if not display or display == username:
                display = username
            chatrooms[username] = {
                "name": display,
                "member_count": 0,
            }
            added += 1
        return added

    def _resolve_groups(self) -> None:
        """Map configured group names to talker IDs from WCDB data.

        Session rows only contain recent chats, so groups may be absent when
        they are not pinned/recent.  Fall back to contacts, persisted group
        names, and explicit @chatroom IDs before treating resolution as failed.
        """
        self._talker_ids.clear()
        sessions = self._client.get_sessions()

        # Build a map of all known @chatroom entries:
        # username -> {name, member_count}.
        all_chatrooms = self._chatrooms_from_records(sessions)
        if all_chatrooms:
            logger.info("Found %d group chats in WCDB sessions", len(all_chatrooms))
        else:
            logger.warning(
                "No @chatroom sessions found in WCDB (total sessions: %d); "
                "trying contacts and cached group mappings.",
                len(sessions),
            )

        contact_chatrooms = self._chatrooms_from_contacts()
        if contact_chatrooms:
            added = self._merge_chatrooms(all_chatrooms, contact_chatrooms)
            logger.info(
                "Loaded %d group chats from contacts (%d new)",
                len(contact_chatrooms), added,
            )

        cached_chatrooms = self._load_cached_group_names()
        if cached_chatrooms:
            added = self._merge_chatrooms(all_chatrooms, cached_chatrooms)
            logger.info(
                "Loaded %d group chats from cache (%d new)",
                len(cached_chatrooms), added,
            )

        direct_count = self._add_configured_chatroom_ids(all_chatrooms)
        if direct_count:
            logger.info("Accepted %d configured direct @chatroom IDs", direct_count)

        if not all_chatrooms:
            logger.error(
                "No @chatroom groups found in WCDB sessions, contacts, cache, "
                "or WECHAT_GROUPS direct IDs (total sessions: %d). Open the "
                "target group once or set WECHAT_GROUPS to a known "
                "123456@chatroom ID.",
                len(sessions),
            )
            return

        auto_discover = (
            not self._groups
            or (len(self._groups) == 1 and self._groups[0].strip() in ("*", "all", ""))
        )

        if auto_discover:
            for username, info in all_chatrooms.items():
                self._talker_ids[info["name"]] = username
            logger.info(
                "Auto-discovered %d group chats: %s",
                len(self._talker_ids), list(self._talker_ids.keys()),
            )
            self._groups = list(self._talker_ids.keys())

        else:
            # Manual mode: match configured names against resolved display names
            for group_name in self._groups:
                found = None
                # Direct lookup: maybe group_name IS a username like 20968749111@chatroom
                if group_name in all_chatrooms:
                    found = group_name
                if not found:
                    for username, info in all_chatrooms.items():
                        display = info["name"]
                        if group_name.lower() == display.lower():
                            found = username
                            break
                if not found:
                    for username, info in all_chatrooms.items():
                        display = info["name"]
                        if group_name.lower() in display.lower() or display.lower() in group_name.lower():
                            found = username
                            break
                if found:
                    self._talker_ids[group_name] = found
                    logger.info("Resolved '%s' -> %s (display='%s')", group_name, found, all_chatrooms[found]["name"])
                else:
                    logger.warning(
                        "Could not resolve group '%s'. Available: %s",
                        group_name, [
                            f"{info['name']} ({username})"
                            for username, info in all_chatrooms.items()
                        ],
                    )

        # Persist chat_id -> display_name so the web UI can show
        # human-readable group names in the nickname dropdown.
        if all_chatrooms:
            self._save_group_names(all_chatrooms)

        # ── Resolve and persist group members ──────────────────────────
        group_members: dict[str, dict[str, str]] = {}
        for username, info in all_chatrooms.items():
            try:
                members = self._client.get_group_members(username)
                if not members:
                    continue
                wxids = [m.get("username", "") for m in members if m.get("username")]
                if not wxids:
                    continue
                # Resolve display names in batches of 200
                names = {}
                for i in range(0, len(wxids), 200):
                    batch = wxids[i:i + 200]
                    names.update(self._client.get_display_names(batch))
                # Filter out unresolved (where name == wxid) and save
                group_members[username] = {
                    wxid: names.get(wxid, wxid)
                    for wxid in wxids
                }
                logger.info(
                    "Resolved %d/%d member names for %s",
                    len(group_members[username]), len(wxids), info["name"],
                )
            except Exception as e:
                logger.warning("Failed to resolve members for %s: %s", username, e)
        if group_members:
            self._save_group_members(group_members)

    @staticmethod
    def _save_group_members(chat_members: dict[str, dict[str, str]]) -> None:
        """Persist chat_id -> {wxid: display_name} to group_members.json."""
        import os as _os
        path = webot_data_path("group_members.json")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = path.with_suffix(".tmp")
            data = json.dumps(chat_members, ensure_ascii=False, indent=2)
            tmp_path.write_text(data, encoding="utf-8")
            _os.replace(tmp_path, path)
            total = sum(len(m) for m in chat_members.values())
            logger.info("Saved %d member names across %d groups to %s", total, len(chat_members), path)
        except Exception as e:
            logger.warning("Failed to persist group_members.json: %s", e)

    @staticmethod
    def _save_group_names(chatrooms: dict[str, dict]) -> None:
        """Persist chat_id -> {name, member_count} to group_names.json atomically."""
        import os as _os
        path = webot_data_path("group_names.json")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = path.with_suffix(".tmp")
            data = json.dumps(chatrooms, ensure_ascii=False, indent=2)
            tmp_path.write_text(data, encoding="utf-8")
            _os.replace(tmp_path, path)
            logger.info(
                "Saved %d group-name mappings to %s",
                len(chatrooms), path,
            )
        except Exception as e:
            logger.warning("Failed to persist group_names.json: %s", e)

    def _talker_to_name(self, talker_id: str) -> str:
        for name, tid in self._talker_ids.items():
            if tid == talker_id:
                return name
        return ""

    # ── Message polling ──────────────────────────────────────────────

    def _poll_cycle(self, callback: MessageCallback) -> None:
        for group_name in list(self._groups):
            if not self._running:
                break
            talker = self._talker_ids.get(group_name)
            if not talker:
                continue
            self._poll_group(group_name, talker, callback)
        # Check shutdown signal before sleeping so stop() is responsive
        if not self._running:
            return
        time.sleep(self._poll_sec)

    def _poll_group(self, group_name: str, talker: str,
                    callback: MessageCallback) -> None:
        """Fetch messages for one group and dispatch new ones.

        AI-triggering callbacks are submitted to the thread pool so slow
        summarization in one group never blocks polling of other groups.
        """
        with self._client_lock:
            messages = self._client.get_messages(talker=talker, limit=50)
        if not messages:
            return

        for msg in reversed(messages):
            if not self._running:
                break

            # Root-cause fix for the per-poll reprocessing loop: cheap
            # raw-field dedup BEFORE standardize.  Previously _standardize
            # (DLL nickname resolution, join detection, logging) ran for
            # all 50 fetched messages on every poll cycle, so old messages
            # were re-processed — and re-logged — once per second forever.
            raw_key = self._raw_message_key(msg, talker)
            if raw_key in self._known_ids:
                continue

            standardized = self._standardize(msg, group_name, talker)
            # Mark as seen even when filtered out (None), so it is never
            # standardized again on later polls.
            self._known_ids.add(raw_key)
            if standardized is None:
                continue

            msg_id = standardized["message_id"]
            if msg_id in self._known_ids:
                continue
            self._known_ids.add(msg_id)

            # Content-based self-skip: never react to our own replies, even
            # when the name-based check below misses them (configured
            # BOT_DISPLAY_NAME != WCDB-resolved sender name).
            now = time.time()
            while self._recent_sends and now - self._recent_sends[0][2] > 300:
                self._recent_sends.popleft()
            if any(
                t == talker and c == standardized["content"]
                for t, c, _ in self._recent_sends
            ):
                continue

            if self._bot_name and self._bot_name in standardized["sender_name"]:
                continue

            # Per-new-message visibility: log what arrived and whether the
            # @mention was detected, so silently-dropped triggers are
            # diagnosable from the Web UI log.
            if standardized["is_system_join"]:
                logger.info(
                    "Join event detected: new_member=%s group=%s",
                    standardized["new_member_id"], group_name[:20],
                )
            logger.info(
                "New message: group='%s' sender='%s' at=%s content=%r",
                group_name, standardized["sender_name"],
                standardized["is_at_mentioned"], standardized["content"][:60],
            )

            self._trim_dedup()

            # Fire-and-forget: callback (potentially AI call) + send run in
            # a thread pool worker so the poll loop continues immediately.
            if self._pool:
                self._pool.submit(
                    self._handle_message,
                    group_name, talker, standardized, callback,
                )
            else:
                # Fallback (pool already shut down): run inline
                self._handle_message(
                    group_name, talker, standardized, callback,
                )

    def _handle_message(self, group_name: str, talker: str,
                        standardized: dict, callback: MessageCallback) -> None:
        """Execute callback and send reply (runs in thread pool worker)."""
        if not self._running:
            return

        try:
            cb_start = time.monotonic()
            reply = callback(standardized)
            cb_elapsed = time.monotonic() - cb_start
            if cb_elapsed > 0.5:
                logger.debug(
                    "Callback took %.2fs (msg_id=%s, group='%s')",
                    cb_elapsed, standardized["message_id"], group_name,
                )

            if reply:
                logger.info(
                    "Reply ready: group='%s' sender='%s' len=%d",
                    group_name, standardized["sender_name"], len(reply),
                )
                with self._client_lock:
                    success = self._send_and_confirm(group_name, talker, reply)
                if success:
                    logger.info(
                        "Reply sent: group='%s' (%d chars)",
                        group_name, len(reply),
                    )
                else:
                    logger.error(
                        "Reply FAILED: group='%s' — check WeChat window",
                        group_name,
                    )
        except Exception:
            logger.exception(
                "Unhandled error in callback worker (group='%s', sender='%s')",
                group_name, standardized.get("sender_name", "?"),
            )

    # ── Voice recognition helpers ────────────────────────────────────

    def _get_voice(self):
        """Lazy-init the VoicePipeline (avoids import unless enabled)."""
        if self._voice is not None:
            return self._voice
        if self._voice_config is None:
            self._voice = False  # Sentinel: no config → disabled
            return False
        try:
            from src.voice import VoicePipeline
            self._voice = VoicePipeline(self._voice_config)
        except Exception:
            logger.exception("VoicePipeline init failed — voice disabled")
            self._voice = False
        return self._voice

    def _try_voice(self, msg: dict) -> Optional[str]:
        """Attempt voice recognition; return text or None on failure."""
        voice = self._get_voice()
        if not voice:  # False or None → disabled
            return None
        try:
            return voice.process(msg)
        except Exception:
            logger.exception("VoicePipeline.process failed")
            return None

    # ── Message standardization ──────────────────────────────────────

    @staticmethod
    def _stable_id_text(value) -> str:
        """Return a usable WCDB id string, ignoring empty / zero placeholders."""
        if value is None:
            return ""
        text = str(value).strip()
        if not text or text == "0":
            return ""
        return text

    @classmethod
    def _raw_message_key(cls, msg: dict, talker: str) -> str:
        """Build a stable per-chat key before expensive message standardization."""
        for key in (
            "server_id", "serverId", "msgSvrId", "msg_svr_id", "newMsgId",
            "local_id", "localId", "localID", "localId64",
        ):
            value = cls._stable_id_text(msg.get(key))
            if value:
                return f"{talker}|{key}|{value}"

        sender = str(
            msg.get("sender_username", msg.get("senderUsername", msg.get("sender", "")))
        )
        content = str(msg.get("message_content", msg.get("content", "")))
        ts = msg.get("create_time", msg.get("createTime", msg.get("timestamp", "")))
        local_type = msg.get("localType", msg.get("msg_type", ""))
        return f"{talker}|{sender}|{content}|{ts}|{local_type}"

    def _standardize(self, msg: dict, group_name: str,
                     talker: str) -> Optional[dict]:
        """Convert WCDB raw message to standard format."""
        # WCDB message fields: sender_username, message_content, local_type, create_time
        sender = str(msg.get("sender_username", msg.get("senderUsername", msg.get("sender", ""))))
        raw_content = str(msg.get("message_content", msg.get("content", ""))).strip()
        local_type = normalize_msg_type(msg.get("localType", msg.get("msg_type", 1)))
        content = raw_content

        # ── Voice recognition ──────────────────────────────────────
        # Voice messages (localType=34) have empty message_content;
        # we must recognise them BEFORE the empty-content check below.
        if local_type == 34:
            voice_text = self._try_voice(msg)
            if voice_text:
                content = f"[语音] {voice_text}"
            else:
                content = "[语音]"
        elif local_type not in (1, 10000):
            content = format_nontext_content(local_type, raw_content)
        elif not content:
            return None

        # ── System message handling ───────────────────────────────
        # Extract "xxx joined the group" events → welcome feature.
        # Pattern matches:
        #   "张三"加入了群聊                    → 张三
        #   "张三"通过扫描二维码加入了群聊      → 张三
        #   "李四"邀请"张三"加入了群聊          → 张三 (last quoted name)
        # Using [^"]+ (cannot cross quote boundaries) instead of .+?
        # to avoid backtracking into the wrong quoted string.
        _JOIN_PATTERN = re.compile(r'"([^"]+)"(?:通过[^"]*)?加入了群聊')
        join_match = _JOIN_PATTERN.search(content)
        # WeChat stores placeholder names as "\xa0" (NBSP); strip() removes it
        # so stale/placeholder join events don't carry a bogus member id.
        new_member_id: str = join_match.group(1).strip() if join_match else ""
        is_system_join: bool = bool(join_match)
        # NOTE: "Join event detected" is logged in _poll_group AFTER the dedup
        # check — logging here would fire once per poll cycle for old messages.

        # Filter other system messages (but NOT join events)
        if not is_system_join:
            _FILTER_KEYWORDS = (
                "修改群名", "退出了群聊",
                "撤回了一条消息", "被移除", "开启了朋友验证",
                "邀请", "移出了群聊",
            )
            if any(kw in content for kw in _FILTER_KEYWORDS):
                return None

        # Parse timestamp
        ts = msg.get("create_time", msg.get("createTime", msg.get("timestamp", 0)))
        try:
            ts = int(ts)
        except (TypeError, ValueError):
            ts = int(time.time())

        # Resolve sender display name
        sender_name = self._client.resolve_nickname(sender)

        # Fallback: if WCDB DLL can't resolve (user not in contacts),
        # try the messages table for a previously seen display name
        if sender_name == sender and self._store is not None:
            prev = self._store.get_sender_display_name(sender)
            if prev:
                sender_name = prev

        # Resolve @mentions in content
        resolved_content = content
        mentioned_names: list[str] = []
        if "@" in content:
            def _replace_at(match):
                at_wxid = match.group(0)[1:]
                name = self._client.resolve_nickname(at_wxid)
                if name != at_wxid:
                    mentioned_names.append(name)
                return f"@{name}" if name != at_wxid else match.group(0)
            resolved_content = re.sub(r'@wxid_[a-zA-Z0-9]+', _replace_at, content)

        # Detect @mention of bot.
        # Exact match first.  Then fuzzy: WeChat renders the mention with the
        # group alias / remark name, which may differ slightly from
        # BOT_DISPLAY_NAME (e.g. config='小俞' but the mention shows '@俞').
        # Without fuzzy matching such @mentions were silently ignored.
        is_at = False
        bot_mention_text = ""
        if self._bot_name:
            bot = self._bot_name.strip()
            if f"@{bot}" in resolved_content or f"@{bot}" in content:
                is_at = True
                bot_mention_text = f"@{bot}"
            else:
                candidates = list(mentioned_names)
                # Newer WeChat stores mentions as literal "@displayname"
                # text (no @wxid_ token) — scan those too.
                candidates += re.findall(
                    r"@([^\s@,，。！？!?：:；;]+)", resolved_content,
                )
                for name in candidates:
                    alias = name.strip()
                    if alias and (alias == bot or alias in bot or bot in alias):
                        is_at = True
                        bot_mention_text = f"@{name}"
                        # DEBUG: _standardize runs every poll for old
                        # messages; INFO here would flood the log.
                        logger.debug(
                            "Fuzzy @mention match: mention='%s' config='%s'",
                            alias, bot,
                        )
                        break

        # Generate stable message ID.
        # For system join messages, use a content-based ID to avoid
        # volatile WCDB server_id/local_id causing dedup misses.
        if is_system_join:
            raw_id = f"join|{talker}|{new_member_id}|{content}|{ts}"
        else:
            raw_id = self._raw_message_key(msg, talker)
        msg_id = hashlib.md5(str(raw_id).encode()).hexdigest()

        return {
            "message_id": msg_id,
            "chat_id": talker,
            "group_name": group_name,
            "sender_id": str(sender),
            "sender_name": str(sender_name),
            "content": resolved_content,
            "msg_type": local_type,
            "timestamp": ts,
            "is_at_mentioned": bool(is_at),
            "bot_mention_text": bot_mention_text,
            "is_group": True,
            "is_system_join": is_system_join,
            "new_member_id": new_member_id,
        }

    def _trim_dedup(self) -> None:
        """DedupSet handles this internally."""
        pass

    # ── Message sending ──────────────────────────────────────────────

    def _send_and_confirm(self, group_name: str, talker: str,
                          content: str) -> bool:
        """Send via WeChatWindowController (fire-and-forget).

        Returns True if the keyboard send action completed successfully.
        No confirmation polling — the window controller already retries
        on failure, and polling WCDB adds 3s of latency for marginal gain.
        """
        success = self._window.send_to_chat(group_name, content)
        if success:
            self._recent_sends.append((talker, content, time.time()))
        return success
