"""Tests for WCDB backend group resolution fallbacks."""

import unittest
from unittest.mock import patch

try:
    from src.wechat.wcdb_backend import WcdbBackend
    IMPORT_ERROR = None
except Exception as exc:  # pragma: no cover - non-Windows import guard
    WcdbBackend = None
    IMPORT_ERROR = exc


class FakeWcdbClient:
    def __init__(self, sessions=None, contacts=None, names=None):
        self.sessions = sessions or []
        self.contacts = contacts or []
        self.names = names or {}

    def get_sessions(self):
        return self.sessions

    def get_contacts(self):
        return self.contacts

    def get_group_members(self, chat_id):
        return []

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


if __name__ == "__main__":
    unittest.main()
