"""Tests for WCDB backend group resolution fallbacks."""

from collections import deque
import json
from pathlib import Path
import tempfile
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
    def __init__(self, sessions=None, contacts=None, names=None, messages=None,
                 groups=None, account=""):
        self.sessions = sessions or []
        self.contacts = contacts or []
        self.names = names or {}
        self.messages = messages or []
        self.groups = groups or []
        self.account = account

    def get_sessions(self):
        return self.sessions

    def get_contacts(self):
        return self.contacts

    def get_groups(self):
        return self.groups

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
    backend._groups_lock = threading.RLock()
    backend._chatrooms = {}
    backend._auto_discover = bool(groups) and groups[0].strip() in ("*", "all", "")
    backend._last_group_refresh = 0.0
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

    def test_resolves_new_group_from_chat_room_table(self):
        # A brand-new, not yet renamed group has no session row and may not
        # be in the contact table either; only chat_room knows about it.
        client = FakeWcdbClient(
            sessions=[],
            contacts=[],
            groups=[{
                "username": "555555@chatroom",
                "name": "555555@chatroom",
                "member_count": 6,
            }],
        )
        backend = _backend(["*"], client)

        with (
            patch.object(WcdbBackend, "_load_cached_group_names", return_value={}),
            patch.object(WcdbBackend, "_save_group_names"),
            patch.object(WcdbBackend, "_save_group_members"),
        ):
            backend._resolve_groups()

        self.assertEqual(
            backend._talker_ids,
            {"555555@chatroom": "555555@chatroom"},
        )
        self.assertEqual(backend._chatrooms["555555@chatroom"]["member_count"], 6)

    def test_refresh_picks_up_group_created_after_startup(self):
        client = FakeWcdbClient(sessions=[])
        backend = _backend(["*"], client)
        backend._chatrooms = {}
        backend._last_group_refresh = 0.0

        with (
            patch.object(WcdbBackend, "_load_cached_group_names", return_value={}),
            patch.object(WcdbBackend, "_save_group_names"),
            patch.object(WcdbBackend, "_save_group_members"),
        ):
            backend._resolve_groups()
        self.assertEqual(backend._talker_ids, {})

        client.groups = [{
            "username": "666666@chatroom",
            "name": "666666@chatroom",
            "member_count": 3,
        }]
        backend._last_group_refresh = 0.0
        with (
            patch.object(WcdbBackend, "_save_group_names"),
            patch.object(WcdbBackend, "_save_group_members"),
        ):
            self.assertTrue(backend.refresh_group_cache(force=True))

        self.assertEqual(
            backend._talker_ids,
            {"666666@chatroom": "666666@chatroom"},
        )
        self.assertEqual(backend._groups, ["666666@chatroom"])


@unittest.skipIf(WcdbBackend is None, f"wcdb_backend unavailable: {IMPORT_ERROR}")
class WcdbBackendPollingTests(unittest.TestCase):
    def _polling_backend(self, messages):
        backend = object.__new__(WcdbBackend)
        backend._client = FakeWcdbClient(
            names={"wxid_alice": "Alice", "wxid_bob": "Bob"},
            messages=messages,
        )
        backend._client_lock = threading.Lock()
        backend._groups_lock = threading.RLock()
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
        backend._groups_lock = threading.RLock()
        backend._chatrooms = {}
        backend._auto_discover = True
        backend._last_group_refresh = 0.0
        backend._client = FakeWcdbClient()

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
        backend._groups_lock = threading.RLock()

        self.assertEqual(backend._talker_to_name("wxid_alice"), "Alice")

    def test_contacts_without_remark_or_nickname_are_skipped(self):
        client = FakeWcdbClient(
            contacts=[
                {"username": "wxid_named", "remark": "有备注", "nick_name": ""},
                {"username": "wxid_noname", "remark": "", "nick_name": ""},
            ],
        )
        backend = self._friend_backend(["*"], client)

        self._resolve(backend)

        self.assertEqual(backend._friend_ids, {"有备注": "wxid_named"})

    def test_system_service_accounts_are_skipped(self):
        client = FakeWcdbClient(
            contacts=[
                {"username": "brandservicesessionholder", "nickName": "品牌服务"},
                {"username": "brandsessionholder", "nickName": "品牌会话"},
                {"username": "gh_news", "nickName": "新闻"},
                {"username": "officialaccounts", "nickName": "公众号"},
                {"username": "wxid_alice", "remark": "Alice"},
            ],
        )
        backend = self._friend_backend(["*"], client)

        self._resolve(backend)

        self.assertEqual(backend._friend_ids, {"Alice": "wxid_alice"})

    def test_sessions_not_in_contacts_are_not_listed_as_friends(self):
        client = FakeWcdbClient(
            sessions=[
                {"username": "wxid_alice", "displayName": "Alice"},
                {"username": "wxid_stranger", "displayName": "临时会话"},
            ],
            contacts=[{"username": "wxid_alice", "remark": "Alice"}],
        )
        backend = self._friend_backend(["*"], client)

        self._resolve(backend)

        self.assertEqual(backend._friend_ids, {"Alice": "wxid_alice"})

    def test_duplicate_display_names_are_all_polled(self):
        client = FakeWcdbClient(
            contacts=[
                {"username": "wxid_a", "remark": "同名"},
                {"username": "wxid_b", "remark": "同名"},
            ],
        )
        backend = self._friend_backend(["*"], client)

        self._resolve(backend)

        self.assertEqual(len(backend._friend_ids), 2)
        self.assertEqual(
            set(backend._friend_ids.values()), {"wxid_a", "wxid_b"}
        )

    def test_ambiguous_name_selection_is_skipped(self):
        client = FakeWcdbClient(
            contacts=[
                {"username": "wxid_a", "remark": "同名"},
                {"username": "wxid_b", "remark": "同名"},
            ],
        )
        backend = self._friend_backend(["同名"], client)

        self._resolve(backend)

        self.assertEqual(backend._friend_ids, {})

    def test_cached_friends_from_another_account_are_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "friend_names.json"
            cache.write_text(
                json.dumps({
                    "account": "wxid_old_account",
                    "friends": {"wxid_old_friend": {"name": "旧账号好友"}},
                }, ensure_ascii=False),
                encoding="utf-8",
            )
            client = FakeWcdbClient(account="wxid_current_account")
            backend = self._friend_backend([], client)

            with (
                patch(
                    "src.wechat.wcdb_backend.webot_data_path",
                    return_value=cache,
                ),
                patch.object(WcdbBackend, "_save_friend_names"),
            ):
                backend._resolve_friends()

            self.assertEqual(backend._friend_ids, {})

    def test_cached_friends_of_same_account_are_reused_when_db_unreadable(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "friend_names.json"
            cache.write_text(
                json.dumps({
                    "account": "wxid_current_account",
                    "friends": {"wxid_alice": {"name": "Alice"}},
                }, ensure_ascii=False),
                encoding="utf-8",
            )
            client = FakeWcdbClient(account="wxid_current_account")
            backend = self._friend_backend(["Alice"], client)

            with (
                patch(
                    "src.wechat.wcdb_backend.webot_data_path",
                    return_value=cache,
                ),
                patch.object(WcdbBackend, "_save_friend_names"),
            ):
                backend._resolve_friends()

            self.assertEqual(backend._friend_ids, {"Alice": "wxid_alice"})

    def test_legacy_cache_without_account_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "friend_names.json"
            cache.write_text(
                json.dumps({"wxid_alice": {"name": "Alice"}}, ensure_ascii=False),
                encoding="utf-8",
            )
            client = FakeWcdbClient(account="wxid_current_account")
            backend = self._friend_backend([], client)

            with (
                patch(
                    "src.wechat.wcdb_backend.webot_data_path",
                    return_value=cache,
                ),
                patch.object(WcdbBackend, "_save_friend_names"),
            ):
                backend._resolve_friends()

            self.assertEqual(backend._friend_ids, {})

    def test_strangers_and_non_friend_contact_types_are_skipped(self):
        client = FakeWcdbClient(
            contacts=[
                {"username": "wxid_friend", "local_type": 1, "flag": 3, "remark": "好友"},
                {"username": "wxid_starred", "local_type": 1, "flag": 1,
                 "nickName": "星标好友"},
                {"username": "wxid_stranger", "local_type": 0, "nickName": "陌生人"},
                {"username": "wxid_group_member", "local_type": 3, "flag": 4,
                 "nickName": "群成员档案"},
                {"username": "wxid_deleted", "local_type": 1, "flag": 3, "delete_flag": 1,
                 "remark": "已删除"},
                {"username": "2598@openim", "local_type": 6, "nickName": "企业联系人"},
            ],
        )
        backend = self._friend_backend(["*"], client)

        self._resolve(backend)

        self.assertEqual(
            backend._friend_ids,
            {"好友": "wxid_friend", "星标好友": "wxid_starred"},
        )

    def test_contacts_with_non_friend_flag_bits_are_skipped(self):
        client = FakeWcdbClient(
            contacts=[
                {"username": "wxid_friend", "local_type": 1, "flag": 3, "remark": "好友"},
                {"username": "wxid_blocked", "local_type": 1, "flag": 259,
                 "nickName": "已拉黑"},
                {"username": "wxid_service", "local_type": 1, "flag": 65539,
                 "nickName": "企业服务"},
            ],
        )
        backend = self._friend_backend(["*"], client)

        self._resolve(backend)

        self.assertEqual(backend._friend_ids, {"好友": "wxid_friend"})

    def test_group_cache_from_another_account_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            group_cache = Path(tmp) / "group_names.json"
            marker = Path(tmp) / "wechat_account.txt"
            group_cache.write_text(
                json.dumps({"old@chatroom": "旧账号的群"}, ensure_ascii=False),
                encoding="utf-8",
            )
            marker.write_text("wxid_old_account", encoding="utf-8")
            client = FakeWcdbClient(account="wxid_current_account")
            backend = self._friend_backend([], client)

            with patch(
                "src.wechat.wcdb_backend.webot_data_path",
                side_effect=lambda name: Path(tmp) / name,
            ):
                self.assertEqual(backend._load_cached_group_names(), {})

    def test_account_switch_clears_group_caches_and_updates_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            group_cache = Path(tmp) / "group_names.json"
            members_cache = Path(tmp) / "group_members.json"
            marker = Path(tmp) / "wechat_account.txt"
            for path in (group_cache, members_cache, marker):
                path.write_text("{}" if path != marker else "wxid_old_account",
                                encoding="utf-8")
            client = FakeWcdbClient(account="wxid_new_account")
            backend = self._friend_backend([], client)

            with patch(
                "src.wechat.wcdb_backend.webot_data_path",
                side_effect=lambda name: Path(tmp) / name,
            ):
                backend._prepare_account_caches()

            self.assertFalse(group_cache.exists())
            self.assertFalse(members_cache.exists())
            self.assertEqual(marker.read_text(encoding="utf-8"), "wxid_new_account")

    def test_group_members_do_not_merge_across_accounts(self):
        with tempfile.TemporaryDirectory() as tmp:
            members_cache = Path(tmp) / "group_members.json"
            marker = Path(tmp) / "wechat_account.txt"
            members_cache.write_text(
                json.dumps({"old@chatroom": {"wxid_old": "旧成员"}},
                           ensure_ascii=False),
                encoding="utf-8",
            )
            marker.write_text("wxid_old_account", encoding="utf-8")
            client = FakeWcdbClient(account="wxid_current_account")
            backend = self._friend_backend([], client)

            with patch(
                "src.wechat.wcdb_backend.webot_data_path",
                side_effect=lambda name: Path(tmp) / name,
            ):
                backend._save_group_members(
                    {"new@chatroom": {"wxid_new": "新成员"}}
                )

            saved = json.loads(members_cache.read_text(encoding="utf-8"))
            self.assertEqual(saved, {"new@chatroom": {"wxid_new": "新成员"}})
            self.assertEqual(
                marker.read_text(encoding="utf-8"), "wxid_current_account"
            )

    def test_selection_accepts_visible_wechat_alias(self):
        client = FakeWcdbClient(
            contacts=[
                {"username": "wxid_alice", "alias": "YY_25408", "remark": "Alice"},
            ],
        )
        backend = self._friend_backend(["YY_25408"], client)

        self._resolve(backend)

        self.assertEqual(backend._friend_ids, {"Alice": "wxid_alice"})


if __name__ == "__main__":
    unittest.main()
