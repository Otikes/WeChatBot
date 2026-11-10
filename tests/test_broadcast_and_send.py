"""Tests for broadcast groups, MCP message tools and WeChat native labels.

Message sending is always mocked — these tests never touch a real WeChat window.
"""

import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


class _TempDataMixin:
    """Shared temp data dir + env setup (mirrors test_mcp_server.TestMcpServer)."""

    def _setup_data(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data_dir = Path(self.tmp.name)

        db_path = self.data_dir / "messages.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            """CREATE TABLE messages (
                   id INTEGER PRIMARY KEY AUTOINCREMENT,
                   message_id TEXT UNIQUE NOT NULL, chat_id TEXT NOT NULL,
                   sender_id TEXT NOT NULL, sender_name TEXT NOT NULL,
                   content TEXT NOT NULL DEFAULT '', msg_type INTEGER NOT NULL DEFAULT 1,
                   timestamp INTEGER NOT NULL,
                   created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
               )"""
        )
        conn.commit()
        conn.close()

        (self.data_dir / "group_names.json").write_text(json.dumps({
            "111@chatroom": {"name": "获客交流群", "member_count": 2},
        }, ensure_ascii=False), encoding="utf-8")
        (self.data_dir / "group_members.json").write_text(
            json.dumps({"111@chatroom": {"wxid_a": "客户A"}}, ensure_ascii=False),
            encoding="utf-8",
        )
        (self.data_dir / "friend_names.json").write_text(json.dumps({
            "account": "wxid_me",
            "friends": {"wxid_friend": {"name": "好友张三", "alias": "zhangsan"}},
        }, ensure_ascii=False), encoding="utf-8")

        env_file = self.data_dir / ".env"
        env_file.write_text(
            "MCP_ENABLED=true\nMCP_API_KEY=test_key_123456\n", encoding="utf-8"
        )
        self.env_patch = patch.dict(os.environ, {
            "WEBOT_DATA_DIR": str(self.data_dir),
            "DB_PATH": str(db_path),
            "WEBOT_ENV_FILE": str(env_file),
            "MCP_ENABLED": "true",
            "MCP_API_KEY": "test_key_123456",
            "MCP_HISTORY_SOURCE": "messages",
        }, clear=False)
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)

        from src.mcp_server import server as mcp_server

        with mcp_server._auth_lock:
            mcp_server._auth_failures.clear()

    def _call(self, name, args):
        from src.mcp_server.server import handle_rpc

        return handle_rpc({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": name, "arguments": args},
        })

    @staticmethod
    def _payload(response):
        return response["result"]["structuredContent"]

    @staticmethod
    def _error(response):
        return response["result"]["isError"]


class BroadcastConfigTests(_TempDataMixin, unittest.TestCase):
    def setUp(self):
        self._setup_data()

    def test_default_is_empty(self):
        from src import broadcast

        self.assertEqual(broadcast.load(), {"version": 1, "groups": []})

    def test_save_load_roundtrip_mixed_targets(self):
        from src import broadcast

        saved = broadcast.save({"groups": [{
            "name": "客户通知",
            "targets": [
                {"type": "friend", "id": "wxid_friend", "name": "好友张三"},
                {"type": "group", "id": "111@chatroom", "name": "获客交流群"},
            ],
        }]})
        self.assertEqual(len(saved["groups"][0]["targets"]), 2)
        self.assertEqual(broadcast.load(), saved)
        self.assertTrue((self.data_dir / "broadcast_groups.json").exists())

    def test_find_group_case_insensitive_and_target_ids(self):
        from src import broadcast

        broadcast.save({"groups": [{
            "name": "Customer", "targets": [
                {"type": "friend", "id": "wxid_friend"},
                {"type": "group", "id": "111@chatroom"},
            ],
        }]})
        group = broadcast.find_group("customer")
        self.assertIsNotNone(group)
        self.assertEqual(broadcast.target_ids(group), ["wxid_friend", "111@chatroom"])
        self.assertIsNone(broadcast.find_group("不存在"))

    def test_duplicate_group_name_rejected(self):
        from src import broadcast

        with self.assertRaisesRegex(ValueError, "重复"):
            broadcast.validate({"groups": [
                {"name": "A", "targets": []}, {"name": "A", "targets": []},
            ]})

    def test_invalid_type_and_empty_id_rejected(self):
        from src import broadcast

        with self.assertRaisesRegex(ValueError, "friend 或 group"):
            broadcast.validate({"groups": [{
                "name": "A", "targets": [{"type": "channel", "id": "x"}],
            }]})
        with self.assertRaisesRegex(ValueError, "缺少 id"):
            broadcast.validate({"groups": [{
                "name": "A", "targets": [{"type": "friend", "id": ""}],
            }]})

    def test_duplicate_targets_deduped(self):
        from src import broadcast

        saved = broadcast.save({"groups": [{
            "name": "A", "targets": [
                {"type": "friend", "id": "wxid_friend", "name": "张三"},
                {"type": "friend", "id": "wxid_friend", "name": "张三"},
                {"type": "group", "id": "wxid_friend", "name": "同 id 不同类型"},
            ],
        }]})
        self.assertEqual(len(saved["groups"][0]["targets"]), 2)

    def test_corrupted_file_falls_back_to_empty(self):
        from src import broadcast

        (self.data_dir / "broadcast_groups.json").write_text("{broken", encoding="utf-8")
        self.assertEqual(broadcast.groups(), [])

    def test_too_many_groups_rejected(self):
        from src import broadcast

        with self.assertRaisesRegex(ValueError, "不能超过"):
            broadcast.validate({
                "groups": [{"name": f"g{i}", "targets": []} for i in range(101)]
            })


class McpMessageToolTests(_TempDataMixin, unittest.TestCase):
    def setUp(self):
        self._setup_data()

    def test_send_message_dry_run_needs_no_bot(self):
        response = self._call("send_message", {
            "chat": "111@chatroom", "content": "周末活动通知", "dry_run": True,
        })
        data = self._payload(response)
        self.assertTrue(data["ok"])
        self.assertTrue(data["dry_run"])
        self.assertEqual(data["chat_id"], "111@chatroom")

    def test_send_message_resolves_group_name(self):
        backend = Mock()
        backend.send_text.return_value = True
        with patch("src.web.server._bot_control.get_backend", return_value=backend):
            response = self._call("send_message", {
                "chat": "获客交流群", "content": "你好",
            })
        data = self._payload(response)
        self.assertTrue(data["ok"])
        backend.send_text.assert_called_once_with("111@chatroom", "你好")
        self.assertNotIn("content", data)
        self.assertNotIn("你好", json.dumps(data, ensure_ascii=False))

    def test_send_message_resolves_friend_alias(self):
        backend = Mock()
        backend.send_text.return_value = True
        with patch("src.web.server._bot_control.get_backend", return_value=backend):
            response = self._call("send_message", {
                "chat": "zhangsan", "content": "在吗",
            })
        self.assertTrue(self._payload(response)["ok"])
        backend.send_text.assert_called_once_with("wxid_friend", "在吗")

    def test_send_message_requires_running_bot(self):
        with patch("src.web.server._bot_control.get_backend", return_value=None):
            response = self._call("send_message", {
                "chat": "111@chatroom", "content": "hi",
            })
        self.assertTrue(self._error(response))
        self.assertIn("机器人未启动", self._payload(response)["error"])

    def test_send_message_reports_send_failure_per_target(self):
        backend = Mock()
        backend.send_text.return_value = False
        with patch("src.web.server._bot_control.get_backend", return_value=backend):
            response = self._call("send_message", {
                "chat": "111@chatroom", "content": "hi",
            })
        data = self._payload(response)
        self.assertFalse(data["ok"])
        self.assertIn("发送失败", data["error"])

    def test_empty_content_and_too_long_rejected(self):
        for content, keyword in (("", "缺少 content"), ("x" * 2001, "不能超过")):
            with self.subTest(keyword=keyword):
                response = self._call("send_message", {
                    "chat": "111@chatroom", "content": content,
                })
                self.assertTrue(self._error(response))
                self.assertIn(keyword, self._payload(response)["error"])

    def test_batch_by_group_name(self):
        from src import broadcast

        broadcast.save({"groups": [{
            "name": "客户通知", "targets": [
                {"type": "group", "id": "111@chatroom", "name": "获客交流群"},
                {"type": "friend", "id": "wxid_friend", "name": "好友张三"},
            ],
        }]})
        backend = Mock()
        backend.send_text.return_value = True
        with patch("src.web.server._bot_control.get_backend", return_value=backend):
            response = self._call("batch_send_messages", {
                "group": "客户通知", "content": "放假通知", "interval_ms": 0,
            })
        data = self._payload(response)
        self.assertEqual(data["total"], 2)
        self.assertEqual(data["succeeded"], 2)
        self.assertEqual(backend.send_text.call_count, 2)
        self.assertEqual({c.args[0] for c in backend.send_text.call_args_list},
                         {"111@chatroom", "wxid_friend"})

    def test_batch_chats_and_group_merged_and_deduped(self):
        from src import broadcast

        broadcast.save({"groups": [{
            "name": "G", "targets": [{"type": "group", "id": "111@chatroom"}],
        }]})
        response = self._call("batch_send_messages", {
            "content": "hi", "group": "G",
            "chats": ["111@chatroom", "wxid_friend"], "dry_run": True,
        })
        data = self._payload(response)
        self.assertEqual(data["total"], 2)
        self.assertEqual(data["succeeded"], 2)

    def test_batch_dry_run_does_not_call_send_text(self):
        backend = Mock()
        with patch("src.web.server._bot_control.get_backend", return_value=backend):
            response = self._call("batch_send_messages", {
                "chats": ["111@chatroom"], "content": "hi", "dry_run": True,
            })
        self.assertEqual(self._payload(response)["succeeded"], 1)
        backend.send_text.assert_not_called()

    def test_batch_unknown_group_and_missing_targets(self):
        response = self._call("batch_send_messages", {
            "group": "不存在", "content": "hi", "dry_run": True,
        })
        self.assertTrue(self._error(response))
        self.assertIn("找不到群发分组", self._payload(response)["error"])

        response = self._call("batch_send_messages", {"content": "hi"})
        self.assertTrue(self._error(response))
        self.assertIn("chats", self._payload(response)["error"])

    def test_batch_rejects_over_limit(self):
        response = self._call("batch_send_messages", {
            "chats": [f"wxid_{i}" for i in range(51)],
            "content": "hi", "dry_run": True,
        })
        self.assertTrue(self._error(response))
        self.assertIn("最多发送", self._payload(response)["error"])

    def test_scope_filter_hides_blocked_targets(self):
        from src import broadcast

        broadcast.save({"groups": [{
            "name": "G", "targets": [
                {"type": "group", "id": "111@chatroom", "name": "获客交流群"},
                {"type": "friend", "id": "wxid_friend", "name": "好友张三"},
            ],
        }]})
        with patch.dict(os.environ, {"MCP_GROUPS": "none"}, clear=False):
            response = self._call("list_broadcast_groups", {})
            data = self._payload(response)
            blocked = self._call("batch_send_messages", {
                "group": "G", "content": "hi", "dry_run": True,
            })
        self.assertEqual(data["groups"][0]["hidden_count"], 1)
        self.assertEqual([t["id"] for t in data["groups"][0]["targets"]],
                         ["wxid_friend"])
        results = self._payload(blocked)["results"]
        self.assertFalse(next(r for r in results if r["chat"] == "111@chatroom")["ok"])
        self.assertIn("不在 MCP 数据范围内",
                      next(r for r in results if r["chat"] == "111@chatroom")["error"])

    def test_list_wechat_labels_is_read_only_and_degrades(self):
        report = {
            "available": True, "source": "contact_label_contact.label_id_/contact_",
            "tables": ["contact_label", "contact_label_contact"], "note": "",
            "labels": [{"label_id": "1", "name": "同事", "sort_order": 0,
                        "member_count": 1,
                        "members": [{"wxid": "wxid_friend", "name": "好友张三"}]}],
        }
        with patch("src.wechat.labels.read_contact_labels", return_value=report):
            response = self._call("list_wechat_labels", {})
        data = self._payload(response)
        self.assertEqual(data["scope"], "wechat_native_labels")
        self.assertIn("不会导入系统群发分组", data["note"])
        self.assertEqual(data["labels"][0]["members"][0]["name"], "好友张三")

        degraded = {"available": False, "labels": [], "source": "",
                    "tables": [], "note": "微信本地数据库不可用"}
        with patch("src.wechat.labels.read_contact_labels", return_value=degraded):
            response = self._call("list_wechat_labels", {})
        self.assertFalse(self._payload(response)["available"])


if __name__ == "__main__":
    unittest.main()
