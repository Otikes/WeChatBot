"""Tests for WCDB backend group resolution fallbacks."""

from collections import deque
import threading
import time
import unittest
from unittest.mock import patch

try:
    from src.wechat.wcdb_backend import WcdbBackend
    from src.wechat.helpers import DedupSet
    IMPORT_ERROR = None
except Exception as exc:  # pragma: no cover - non-Windows import guard
    WcdbBackend = None
    DedupSet = None
    IMPORT_ERROR = exc


class FakeWcdbClient:
    def __init__(self, sessions=None, contacts=None, names=None, messages=None):
        self.sessions = sessions or []
        self.contacts = contacts or []
        self.names = names or {}
        self.messages = messages or []

    def get_sessions(self):
        return self.sessions

    def get_contacts(self):
        return self.contacts

    def get_group_members(self, chat_id):
        return []

    def get_messages(self, talker, limit=50):
        return self.messages[:limit]

    def get_display_names(self, usernames):
        return {username: self.names.get(username, username) for username in usernames}

    def resolve_nickname(self, wxid):
        return self.names.get(wxid, wxid)


def _backend(groups, client):
    backend = object.__new__(WcdbBackend)
    backend._groups = groups
    backend._client = client
    backend._talker_ids = {"stale": "stale@chatroom"}
    return backend


@unittest.skipIf(WcdbBackend is None, f"wcdb_backend unavailable: {IMPORT_ERROR}")
class WcdbBackendGroupResolutionTests(unittest.TestCase):
    def test_resolves_auto_groups_from_contacts_when_sessions_have_no_groups(self):
        client = FakeWcdbClient(
            sessions=[{"username": "wxid_friend"}],
            contacts=[{"userName": "123456@chatroom", "nickName": "测试群"}],
        )
        backend = _backend(["*"], client)

        with (
            patch.object(WcdbBackend, "_load_cached_group_names", return_value={}),
            patch.object(WcdbBackend, "_save_group_names"),
            patch.object(WcdbBackend, "_save_group_members"),
        ):
            backend._resolve_groups()

        self.assertEqual(backend._talker_ids, {"测试群": "123456@chatroom"})
        self.assertEqual(backend._groups, ["测试群"])

    def test_resolves_manual_group_from_cache_when_sessions_have_no_groups(self):
        client = FakeWcdbClient(sessions=[{"username": "wxid_friend"}])
        backend = _backend(["缓存群"], client)
        cached = {
            "654321@chatroom": {
                "name": "缓存群",
                "member_count": 12,
            }
        }

        with (
            patch.object(WcdbBackend, "_load_cached_group_names", return_value=cached),
            patch.object(WcdbBackend, "_save_group_names"),
            patch.object(WcdbBackend, "_save_group_members"),
        ):
            backend._resolve_groups()

        self.assertEqual(backend._talker_ids, {"缓存群": "654321@chatroom"})

    def test_accepts_configured_direct_chatroom_id_without_session_record(self):
        client = FakeWcdbClient(sessions=[], names={"999999@chatroom": "直连群"})
        backend = _backend(["999999@chatroom"], client)

        with (
            patch.object(WcdbBackend, "_load_cached_group_names", return_value={}),
            patch.object(WcdbBackend, "_save_group_names"),
            patch.object(WcdbBackend, "_save_group_members"),
        ):
            backend._resolve_groups()

        self.assertEqual(backend._talker_ids, {"999999@chatroom": "999999@chatroom"})


@unittest.skipIf(WcdbBackend is None, f"wcdb_backend unavailable: {IMPORT_ERROR}")
class WcdbBackendPollingTests(unittest.TestCase):
    def _polling_backend(self, messages):
        backend = object.__new__(WcdbBackend)
        backend._client = FakeWcdbClient(
            names={"wxid_alice": "Alice", "wxid_bob": "Bob"},
            messages=messages,
        )
        backend._client_lock = threading.Lock()
        backend._known_ids = DedupSet(max_size=100)
        backend._recent_sends = deque(maxlen=32)
        backend._running = True
        backend._pool = None
        backend._bot_name = "Bot"
        backend._store = None
        backend._voice = False
        backend._voice_config = None
        return backend

    def test_poll_group_keeps_distinct_messages_when_server_id_is_zero(self):
        messages = [
            {
                "server_id": 0,
                "local_id": 2,
                "sender_username": "wxid_bob",
                "message_content": "second",
                "localType": 1,
                "create_time": 200,
            },
            {
                "server_id": 0,
                "local_id": 1,
                "sender_username": "wxid_alice",
                "message_content": "first",
                "localType": 1,
                "create_time": 100,
            },
        ]
        backend = self._polling_backend(messages)
        seen = []

        backend._poll_group(
            "Test Group", "test@chatroom", lambda msg: seen.append(msg) or None,
        )

        self.assertEqual([m["content"] for m in seen], ["first", "second"])
        self.assertEqual(len({m["message_id"] for m in seen}), 2)

    def test_recent_self_send_skip_is_scoped_to_the_same_chat(self):
        messages = [
            {
                "server_id": 0,
                "local_id": 1,
                "sender_username": "wxid_alice",
                "message_content": "same reply",
                "localType": 1,
                "create_time": 100,
            },
        ]
        backend = self._polling_backend(messages)
        backend._recent_sends.append(("other@chatroom", "same reply", time.time()))
        seen = []

        backend._poll_group(
            "Test Group", "test@chatroom", lambda msg: seen.append(msg) or None,
        )

        self.assertEqual(len(seen), 1)

        backend = self._polling_backend(messages)
        backend._recent_sends.append(("test@chatroom", "same reply", time.time()))
        seen = []

        backend._poll_group(
            "Test Group", "test@chatroom", lambda msg: seen.append(msg) or None,
        )

        self.assertEqual(seen, [])

    def test_standardize_keeps_empty_image_message_as_placeholder(self):
        backend = self._polling_backend([])
        raw = {
            "server_id": 0,
            "local_id": 10,
            "sender_username": "wxid_alice",
            "message_content": "",
            "localType": 3,
            "create_time": 100,
        }

        msg = backend._standardize(raw, "Test Group", "test@chatroom")

        self.assertIsNotNone(msg)
        self.assertEqual(msg["content"], "[图片]")
        self.assertEqual(msg["msg_type"], 3)

    def test_standardize_summarizes_image_xml_without_leaking_xml(self):
        backend = self._polling_backend([])
        raw = {
            "server_id": 0,
            "local_id": 11,
            "sender_username": "wxid_alice",
            "message_content": '<msg><img length="2048" md5="secret" /></msg>',
            "localType": 3,
            "create_time": 100,
        }

        msg = backend._standardize(raw, "Test Group", "test@chatroom")

        self.assertEqual(msg["content"], "[图片 2.0 KB]")
        self.assertNotIn("<msg", msg["content"])
        self.assertNotIn("secret", msg["content"])

    def test_standardize_summarizes_emoji_xml_without_leaking_xml(self):
        backend = self._polling_backend([])
        raw = {
            "server_id": 0,
            "local_id": 12,
            "sender_username": "wxid_alice",
            "message_content": '<msg><emoji len="4096" md5="secret" /></msg>',
            "localType": "47",
            "create_time": 100,
        }

        msg = backend._standardize(raw, "Test Group", "test@chatroom")

        self.assertEqual(msg["content"], "[表情 4.0 KB]")
        self.assertEqual(msg["msg_type"], 47)
        self.assertNotIn("secret", msg["content"])

    def test_standardize_summarizes_pdf_or_ppt_file_appmsg(self):
        backend = self._polling_backend([])
        raw = {
            "server_id": 0,
            "local_id": 13,
            "sender_username": "wxid_alice",
            "message_content": (
                "<msg><appmsg><title>方案.pptx</title>"
                "<des></des><appattach><totallen>2097152</totallen>"
                "<fileext>pptx</fileext></appattach></appmsg></msg>"
            ),
            "localType": 49,
            "create_time": 100,
        }

        msg = backend._standardize(raw, "Test Group", "test@chatroom")

        self.assertEqual(msg["content"], "[文件: 方案.pptx (PPT, 2.0 MB)]")
        self.assertEqual(msg["msg_type"], 49)

    def test_standardize_marks_private_chat_as_not_group(self):
        backend = self._polling_backend([])
        raw = {
            "server_id": 0,
            "local_id": 15,
            "sender_username": "wxid_alice",
            "message_content": "hello",
            "localType": 1,
            "create_time": 100,
        }

        msg = backend._standardize(raw, "Alice", "wxid_alice", is_group=False)

        self.assertIsNotNone(msg)
        self.assertFalse(msg["is_group"])
        self.assertEqual(msg["group_name"], "Alice")

    def test_private_chat_keeps_messages_containing_group_notice_words(self):
        backend = self._polling_backend([])
        raw = {
            "server_id": 0,
            "local_id": 16,
            "sender_username": "wxid_alice",
            "message_content": "周末我邀请你吃饭",
            "localType": 1,
            "create_time": 100,
        }

        msg = backend._standardize(raw, "Alice", "wxid_alice", is_group=False)

        self.assertIsNotNone(msg)
        self.assertEqual(msg["content"], "周末我邀请你吃饭")

    def test_private_chat_filters_recall_notice(self):
        backend = self._polling_backend([])
        raw = {
            "server_id": 0,
            "local_id": 17,
            "sender_username": "wxid_alice",
            "message_content": "撤回了一条消息",
            "localType": 10000,
            "create_time": 100,
        }

        msg = backend._standardize(raw, "Alice", "wxid_alice", is_group=False)

        self.assertIsNone(msg)

    def test_standardize_summarizes_plain_file_name_without_xml(self):
        backend = self._polling_backend([])
        raw = {
            "server_id": 0,
            "local_id": 14,
            "sender_username": "wxid_alice",
            "message_content": r"C:\Users\Alice\Documents\复盘.pdf",
            "localType": "file",
            "create_time": 100,
        }

        msg = backend._standardize(raw, "Test Group", "test@chatroom")

        self.assertEqual(msg["content"], "[文件: 复盘.pdf (PDF)]")
        self.assertEqual(msg["msg_type"], 49)


@unittest.skipIf(WcdbBackend is None, f"wcdb_backend unavailable: {IMPORT_ERROR}")
class WcdbBackendFriendResolutionTests(unittest.TestCase):
    """Friend discovery and selection gate for 1-on-1 AI chat."""

    def _friend_backend(self, friends, client):
        backend = object.__new__(WcdbBackend)
        backend._friends = friends
        backend._friend_ids = {}
        backend._session_cache = []
        backend._client = client
        return backend

    def _resolve(self, backend):
        with (
            patch.object(WcdbBackend, "_load_cached_friend_names", return_value={}),
            patch.object(WcdbBackend, "_save_friend_names"),
        ):
            backend._resolve_friends()

    def test_auto_discovers_friends_and_skips_groups_and_official_accounts(self):
        client = FakeWcdbClient(
            sessions=[
                {"username": "wxid_alice", "displayName": "Alice"},
                {"username": "123456@chatroom", "displayName": "测试群"},
                {"username": "filehelper", "displayName": "文件传输助手"},
            ],
            contacts=[
                {"userName": "wxid_alice", "remark": "爱丽丝"},
                {"userName": "wxid_bob", "nickName": "Bob"},
                {"userName": "gh_news", "nickName": "新闻"},
            ],
        )
        backend = self._friend_backend(["*"], client)

        self._resolve(backend)

        self.assertEqual(
            backend._friend_ids,
            {"爱丽丝": "wxid_alice", "Bob": "wxid_bob"},
        )

    def test_only_selected_friend_is_resolved(self):
        client = FakeWcdbClient(
            sessions=[
                {"username": "wxid_alice", "displayName": "Alice"},
                {"username": "wxid_bob", "displayName": "Bob"},
            ],
        )
        backend = self._friend_backend(["Bob"], client)

        self._resolve(backend)

        self.assertEqual(backend._friend_ids, {"Bob": "wxid_bob"})

    def test_empty_selection_resolves_no_friends(self):
        client = FakeWcdbClient(
            sessions=[{"username": "wxid_alice", "displayName": "Alice"}],
        )
        backend = self._friend_backend([], client)

        self._resolve(backend)

        self.assertEqual(backend._friend_ids, {})

    def test_unmatched_selection_is_ignored(self):
        client = FakeWcdbClient(
            sessions=[{"username": "wxid_alice", "displayName": "Alice"}],
        )
        backend = self._friend_backend(["陌生人"], client)

        self._resolve(backend)

        self.assertEqual(backend._friend_ids, {})

    def test_poll_cycle_only_polls_selected_friends(self):
        backend = object.__new__(WcdbBackend)
        backend._groups = []
        backend._talker_ids = {}
        backend._friend_ids = {"Alice": "wxid_alice"}
        backend._poll_sec = 0
        backend._running = True

        polled = []
        with (
            patch.object(
                WcdbBackend, "_poll_group",
                side_effect=lambda name, talker, cb, is_group=True:
                    polled.append((name, talker, is_group)),
            ),
            patch("src.wechat.wcdb_backend.time.sleep"),
        ):
            backend._poll_cycle(callback=lambda msg: None)

        self.assertEqual(polled, [("Alice", "wxid_alice", False)])

    def test_talker_to_name_covers_friends(self):
        backend = object.__new__(WcdbBackend)
        backend._talker_ids = {}
        backend._friend_ids = {"Alice": "wxid_alice"}

        self.assertEqual(backend._talker_to_name("wxid_alice"), "Alice")


if __name__ == "__main__":
    unittest.main()
