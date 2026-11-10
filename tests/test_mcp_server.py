"""Tests for the MCP server (protocol, auth and read-only data tools)."""

import io
import json
import os
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch


def _create_messages_db(path: Path, rows: list[tuple]) -> None:
    """rows: (message_id, chat_id, sender_id, sender_name, content, msg_type, ts)."""
    conn = sqlite3.connect(str(path))
    conn.execute(
        """CREATE TABLE messages (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               message_id TEXT UNIQUE NOT NULL,
               chat_id TEXT NOT NULL,
               sender_id TEXT NOT NULL,
               sender_name TEXT NOT NULL,
               content TEXT NOT NULL DEFAULT '',
               msg_type INTEGER NOT NULL DEFAULT 1,
               timestamp INTEGER NOT NULL,
               created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
           )"""
    )
    conn.executemany(
        """INSERT INTO messages
               (message_id, chat_id, sender_id, sender_name, content, msg_type, timestamp)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )
    conn.commit()
    conn.close()


class FakeHandler:
    """Minimal stand-in for BaseHTTPRequestHandler used by handle_http()."""

    def __init__(self, command: str, path: str, body: bytes = b"", headers: dict | None = None):
        self.command = command
        self.path = path
        self.headers = headers or {}
        self.headers.setdefault("Host", "127.0.0.1:7327")
        self.headers.setdefault("Content-Length", str(len(body)))
        self.client_address = ("127.0.0.1", 12345)
        self.rfile = io.BytesIO(body)
        self.wfile = io.BytesIO()
        self.status = None
        self.response_headers: list[tuple[str, str]] = []
        self.close_connection = False

    def send_response(self, code):
        self.status = code

    def send_header(self, key, value):
        self.response_headers.append((key, value))

    def end_headers(self):
        pass


class TestMcpServer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

        self.db_path = self.data_dir / "messages.db"
        now = int(time.time())
        self.now = now
        _create_messages_db(self.db_path, [
            ("m1", "111@chatroom", "wxid_a", "客户A", "你们的产品怎么卖？", 1, now - 10 * 86400),
            ("m2", "111@chatroom", "wxid_a", "客户A", "预算大概多少", 1, now - 2 * 86400),
            ("m3", "111@chatroom", "wxid_b", "客户B", "我想了解一下报价方案", 1, now - 86400),
            ("m4", "wxid_friend", "wxid_friend", "好友张三", "在吗？", 1, now - 3600),
            ("m5", "222@chatroom", "wxid_c", "客户C", "支持定制吗", 1, now - 7200),
        ])

        (self.data_dir / "group_names.json").write_text(json.dumps({
            "111@chatroom": {"name": "获客交流群", "member_count": 2},
        }, ensure_ascii=False), encoding="utf-8")
        (self.data_dir / "group_members.json").write_text(json.dumps({
            "111@chatroom": {"wxid_a": "客户A-群昵称", "wxid_b": "客户B"},
        }, ensure_ascii=False), encoding="utf-8")
        (self.data_dir / "friend_names.json").write_text(json.dumps({
            "account": "wxid_me",
            "friends": {"wxid_friend": {"name": "好友张三", "alias": "zhangsan"}},
        }, ensure_ascii=False), encoding="utf-8")

        self.env_file = self.data_dir / ".env"
        self.env_file.write_text(
            "MCP_ENABLED=true\nMCP_API_KEY=test_key_123456\n",
            encoding="utf-8",
        )
        self.env_patch = patch.dict(os.environ, {
            "WEBOT_DATA_DIR": str(self.data_dir),
            "DB_PATH": str(self.db_path),
            "WEBOT_ENV_FILE": str(self.env_file),
            "MCP_ENABLED": "true",
            "MCP_API_KEY": "test_key_123456",
            # 单元测试不触碰真实微信本地库，显式只用 messages.db
            "MCP_HISTORY_SOURCE": "messages",
        }, clear=False)
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)

        from src.mcp_server import server as mcp_server

        with mcp_server._auth_lock:
            mcp_server._auth_failures.clear()

    # ── 协议 ────────────────────────────────────────────────────────

    def test_initialize_and_tools_list(self):
        from src.mcp_server.server import handle_rpc

        init = handle_rpc({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-03-26", "capabilities": {}},
        })
        self.assertEqual(init["result"]["protocolVersion"], "2025-03-26")
        self.assertEqual(init["result"]["serverInfo"]["name"], "webot-mcp")
        self.assertIn("tools", init["result"]["capabilities"])

        listing = handle_rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = {tool["name"] for tool in listing["result"]["tools"]}
        expected = {
            "get_data_overview", "list_groups", "get_group", "list_group_members",
            "list_friends", "get_messages", "get_message_media", "list_chat_media",
            "search_messages", "get_group_activity",
            "get_member_activity", "search_contacts", "find_new_senders",
            "get_contact_profile",
            "list_broadcast_groups", "send_message", "batch_send_messages",
            "list_wechat_labels",
        }
        self.assertEqual(names, expected)
        write_tools = {"send_message", "batch_send_messages"}
        for tool in listing["result"]["tools"]:
            annotations = tool["annotations"]
            if tool["name"] in write_tools:
                self.assertFalse(annotations["readOnlyHint"])
                self.assertTrue(annotations["destructiveHint"])
                self.assertFalse(annotations["idempotentHint"])
            else:
                self.assertTrue(annotations["readOnlyHint"])
                self.assertFalse(annotations["destructiveHint"])

    def test_notification_returns_none(self):
        from src.mcp_server.server import handle_rpc

        self.assertIsNone(handle_rpc({
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        }))

    def test_unknown_method(self):
        from src.mcp_server.server import handle_rpc

        response = handle_rpc({"jsonrpc": "2.0", "id": 9, "method": "nope"})
        self.assertEqual(response["error"]["code"], -32601)

    def test_unknown_tool(self):
        from src.mcp_server.server import handle_rpc

        response = handle_rpc({
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "missing_tool", "arguments": {}},
        })
        self.assertEqual(response["error"]["code"], -32602)

    # ── 鉴权与传输 ──────────────────────────────────────────────────

    def test_verify_api_key(self):
        from src.mcp_server.server import verify_api_key

        self.assertTrue(verify_api_key({"Authorization": "Bearer test_key_123456"}))
        self.assertTrue(verify_api_key({"X-API-Key": "test_key_123456"}))
        self.assertFalse(verify_api_key({}))
        self.assertFalse(verify_api_key({"Authorization": "Bearer wrong_key"}))
        self.assertTrue(verify_api_key({}, {"key": ["test_key_123456"]}))

    def test_http_requires_key(self):
        from src.mcp_server.server import handle_http

        handler = FakeHandler("POST", "/mcp", body=b"{}")
        handled = handle_http(handler)
        self.assertTrue(handled)
        self.assertEqual(handler.status, 401)

    def test_http_rejects_untrusted_host(self):
        from src.mcp_server.server import handle_http

        handler = FakeHandler("POST", "/mcp", body=b"{}", headers={
            "Host": "evil.example.com",
            "Authorization": "Bearer test_key_123456",
        })
        self.assertTrue(handle_http(handler))
        self.assertEqual(handler.status, 403)

    def test_http_rejects_untrusted_origin(self):
        from src.mcp_server.server import handle_http

        handler = FakeHandler("POST", "/mcp", body=b"{}", headers={
            "Origin": "http://evil.example.com",
            "Authorization": "Bearer test_key_123456",
        })
        self.assertTrue(handle_http(handler))
        self.assertEqual(handler.status, 403)

    def test_http_echoes_trusted_origin(self):
        from src.mcp_server.server import handle_http

        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}).encode()
        handler = FakeHandler("POST", "/mcp", body=body, headers={
            "Origin": "http://127.0.0.1:7327",
            "Authorization": "Bearer test_key_123456",
        })
        self.assertTrue(handle_http(handler))
        self.assertEqual(handler.status, 200)
        cors = dict(handler.response_headers).get("Access-Control-Allow-Origin")
        self.assertEqual(cors, "http://127.0.0.1:7327")

    def test_http_rejects_query_key_for_streamable(self):
        from src.mcp_server.server import handle_http

        handler = FakeHandler(
            "POST", "/mcp?key=test_key_123456",
            body=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}).encode(),
        )
        self.assertTrue(handle_http(handler))
        self.assertEqual(handler.status, 401)

    def test_sse_session_limit(self):
        from src.mcp_server import server as mcp_server

        with mcp_server._sse_lock:
            for index in range(mcp_server.MAX_SSE_SESSIONS):
                mcp_server._sse_sessions[f"fake{index}"] = None

        def _clear_sessions():
            with mcp_server._sse_lock:
                mcp_server._sse_sessions.clear()

        self.addCleanup(_clear_sessions)
        handler = FakeHandler("GET", "/mcp/sse", headers={
            "Authorization": "Bearer test_key_123456",
        })
        self.assertTrue(mcp_server.handle_http(handler))
        self.assertEqual(handler.status, 429)

    def test_batch_limit(self):
        from src.mcp_server.server import MAX_BATCH_ITEMS, handle_rpc

        response = handle_rpc([
            {"jsonrpc": "2.0", "id": index, "method": "ping"}
            for index in range(MAX_BATCH_ITEMS + 1)
        ])
        self.assertEqual(response["error"]["code"], -32600)

    def test_http_initialize(self):
        from src.mcp_server.server import handle_http

        body = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {}},
        }).encode()
        handler = FakeHandler("POST", "/mcp", body=body, headers={
            "Authorization": "Bearer test_key_123456",
            "Content-Type": "application/json",
        })
        self.assertTrue(handle_http(handler))
        self.assertEqual(handler.status, 200)
        payload = json.loads(handler.wfile.getvalue())
        self.assertEqual(payload["result"]["serverInfo"]["name"], "webot-mcp")

    def test_http_notification_returns_202(self):
        from src.mcp_server.server import handle_http

        body = json.dumps({
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        }).encode()
        handler = FakeHandler("POST", "/mcp", body=body, headers={
            "Authorization": "Bearer test_key_123456",
        })
        self.assertTrue(handle_http(handler))
        self.assertEqual(handler.status, 202)
        self.assertEqual(handler.wfile.getvalue(), b"")

    def test_http_parse_error(self):
        from src.mcp_server.server import handle_http

        handler = FakeHandler("POST", "/mcp", body=b"{invalid", headers={
            "Authorization": "Bearer test_key_123456",
        })
        self.assertTrue(handle_http(handler))
        self.assertEqual(handler.status, 400)

    def test_http_unknown_path_not_handled(self):
        from src.mcp_server.server import handle_http

        handler = FakeHandler("GET", "/api/status")
        self.assertFalse(handle_http(handler))

    # ── 数据工具 ────────────────────────────────────────────────────

    def test_list_groups_merges_db_chats(self):
        from src.mcp_server.server import handle_rpc

        response = handle_rpc({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "list_groups", "arguments": {}},
        })
        data = response["result"]["structuredContent"]
        groups = {group["chat_id"]: group for group in data["groups"]}
        self.assertIn("111@chatroom", groups)
        self.assertIn("222@chatroom", groups)
        self.assertEqual(groups["111@chatroom"]["name"], "获客交流群")
        self.assertEqual(groups["111@chatroom"]["message_count"], 3)

    def test_list_group_members(self):
        from src.mcp_server.server import handle_rpc

        response = handle_rpc({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "list_group_members", "arguments": {"chat": "获客交流群"}},
        })
        data = response["result"]["structuredContent"]
        members = {member["wxid"]: member for member in data["members"]}
        self.assertEqual(members["wxid_a"]["name"], "客户A-群昵称")
        self.assertEqual(members["wxid_a"]["message_count"], 2)
        self.assertEqual(members["wxid_b"]["message_count"], 1)

    def test_list_friends(self):
        from src.mcp_server.server import handle_rpc

        response = handle_rpc({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "list_friends", "arguments": {}},
        })
        data = response["result"]["structuredContent"]
        self.assertEqual(data["account"], "wxid_me")
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["friends"][0]["wxid"], "wxid_friend")
        self.assertEqual(data["friends"][0]["message_count"], 1)

    def test_get_messages_resolves_group_name(self):
        from src.mcp_server.server import handle_rpc

        response = handle_rpc({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "get_messages", "arguments": {
                "chat": "获客交流群", "limit": 10, "order": "asc",
            }},
        })
        data = response["result"]["structuredContent"]
        self.assertEqual(data["chat_id"], "111@chatroom")
        self.assertEqual(data["count"], 3)
        self.assertEqual(data["messages"][0]["content"], "你们的产品怎么卖？")
        self.assertEqual(data["messages"][0]["msg_type_label"], "text")

    def test_get_messages_time_filter(self):
        from src.mcp_server.server import handle_rpc

        since = time.strftime("%Y-%m-%d", time.localtime(self.now - 3 * 86400))
        response = handle_rpc({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "get_messages", "arguments": {
                "chat": "111@chatroom", "since": since,
            }},
        })
        data = response["result"]["structuredContent"]
        self.assertEqual(data["count"], 2)

    def test_search_messages(self):
        from src.mcp_server.server import handle_rpc

        response = handle_rpc({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "search_messages", "arguments": {"keyword": "报价"}},
        })
        data = response["result"]["structuredContent"]
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["messages"][0]["sender_name"], "客户B")
        self.assertEqual(data["messages"][0]["chat_name"], "获客交流群")

    def test_group_activity_counts_new_senders(self):
        from src.mcp_server.server import handle_rpc

        response = handle_rpc({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "get_group_activity", "arguments": {
                "since": self.now - 3 * 86400,
                "until": self.now,
            }},
        })
        data = response["result"]["structuredContent"]
        groups = {group["chat_id"]: group for group in data["groups"]}
        self.assertEqual(groups["111@chatroom"]["message_count"], 2)
        self.assertEqual(groups["111@chatroom"]["active_sender_count"], 2)
        self.assertEqual(groups["111@chatroom"]["new_sender_count"], 1)
        self.assertIn("222@chatroom", groups)

    def test_member_activity(self):
        from src.mcp_server.server import handle_rpc

        response = handle_rpc({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "get_member_activity", "arguments": {"chat": "获客交流群"}},
        })
        data = response["result"]["structuredContent"]
        self.assertEqual(data["total_messages"], 3)
        self.assertEqual(data["members"][0]["wxid"], "wxid_a")
        self.assertEqual(data["members"][0]["name"], "客户A-群昵称")
        self.assertEqual(data["source"], "messages_db")

    # ── 微信本地完整历史 ────────────────────────────────────────────

    def test_get_messages_uses_local_history(self):
        from src.mcp_server import data as mcp_data

        rows = [{
            "local_id": 9001,
            "server_id": 501,
            "shard": "message_0.db",
            "sender_id": 7,
            "sender_username": "wxid_a",
            "is_self": False,
            "content": "很久以前的历史消息",
            "local_type": 1,
            "timestamp": self.now - 200 * 86400,
        }]
        with patch.object(
            mcp_data.history_source, "display_names", return_value={}
        ), patch.object(
            mcp_data.history_source, "query_messages", return_value=(rows, True)
        ) as query:
            data = mcp_data.get_messages({
                "chat": "111@chatroom", "limit": 10,
            })

        self.assertEqual(data["source"], "wechat_db")
        self.assertTrue(data["has_more"])
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["messages"][0]["message_id"], "message_0.db:9001")
        self.assertEqual(data["messages"][0]["sender_name"], "客户A-群昵称")
        self.assertEqual(data["messages"][0]["content"], "很久以前的历史消息")
        self.assertEqual(query.call_args.kwargs["limit"], 10)
        self.assertEqual(query.call_args.kwargs["offset"], 0)

    def test_get_messages_falls_back_when_history_unavailable(self):
        from src.mcp_server import data as mcp_data

        with patch.object(
            mcp_data.history_source,
            "query_messages",
            side_effect=mcp_data.history_source.HistoryUnavailable("微信未运行"),
        ):
            data = mcp_data.get_messages({"chat": "111@chatroom"})

        self.assertEqual(data["source"], "messages_db")
        self.assertEqual(data["count"], 3)
        self.assertIn("微信未运行", data["note"])

    def test_get_messages_explicit_wechat_source_raises(self):
        from src.mcp_server import data as mcp_data

        with patch.object(
            mcp_data.history_source,
            "query_messages",
            side_effect=mcp_data.history_source.HistoryUnavailable("微信未运行"),
        ):
            with self.assertRaises(ValueError):
                mcp_data.get_messages({
                    "chat": "111@chatroom", "source": "wechat_db",
                })

    def test_search_messages_with_chat_uses_local_history(self):
        from src.mcp_server import data as mcp_data

        rows = [{
            "local_id": 9002,
            "server_id": 502,
            "shard": "message_1.db",
            "sender_id": 8,
            "sender_username": "wxid_b",
            "is_self": False,
            "content": "完整历史里的报价方案",
            "local_type": 1,
            "timestamp": self.now - 100 * 86400,
        }]
        with patch.object(
            mcp_data.history_source, "display_names", return_value={}
        ), patch.object(
            mcp_data.history_source, "query_messages", return_value=(rows, False)
        ) as query:
            data = mcp_data.search_messages({
                "keyword": "报价", "chat": "111@chatroom",
            })

        self.assertEqual(data["source"], "wechat_db")
        self.assertEqual(data["keyword"], "报价")
        self.assertEqual(data["messages"][0]["content"], "完整历史里的报价方案")
        self.assertEqual(query.call_args.kwargs["keyword"], "报价")

    def test_search_messages_without_chat_uses_messages_db(self):
        from src.mcp_server import data as mcp_data

        data = mcp_data.search_messages({"keyword": "报价"})

        self.assertEqual(data["source"], "messages_db")
        self.assertEqual(data["count"], 1)
        self.assertIn("未指定 chat", data["note"])

    def test_member_activity_uses_local_history(self):
        from src.mcp_server import data as mcp_data

        stats = [{
            "sender_username": "wxid_a",
            "real_sender_id": 7,
            "message_count": 25,
            "first_ts": self.now - 30 * 86400,
            "last_ts": self.now - 86400,
        }]
        with patch.object(
            mcp_data.history_source, "display_names", return_value={}
        ), patch.object(
            mcp_data.history_source, "sender_stats", return_value=stats
        ):
            data = mcp_data.get_member_activity({"chat": "获客交流群"})

        self.assertEqual(data["source"], "wechat_db")
        self.assertEqual(data["total_messages"], 25)
        self.assertEqual(data["members"][0]["wxid"], "wxid_a")
        self.assertEqual(data["members"][0]["name"], "客户A-群昵称")
        self.assertEqual(data["members"][0]["share"], 1.0)

    def test_search_contacts(self):
        from src.mcp_server.server import handle_rpc

        response = handle_rpc({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "search_contacts", "arguments": {"query": "客户A"}},
        })
        data = response["result"]["structuredContent"]
        self.assertTrue(data["group_members"])
        self.assertEqual(data["group_members"][0]["wxid"], "wxid_a")

    def test_data_overview(self):
        from src.mcp_server.server import handle_rpc

        response = handle_rpc({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "get_data_overview", "arguments": {}},
        })
        data = response["result"]["structuredContent"]
        self.assertEqual(data["account"], "wxid_me")
        self.assertEqual(data["message_count"], 5)
        self.assertEqual(data["group_count"], 1)
        self.assertGreater(data["db_size_bytes"], 0)
        self.assertTrue(data["db_updated_time"])

    def test_find_new_senders(self):
        from src.mcp_server.server import handle_rpc

        response = handle_rpc({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "find_new_senders", "arguments": {
                "since": self.now - 3 * 86400,
                "until": self.now,
            }},
        })
        data = response["result"]["structuredContent"]
        senders = {item["wxid"]: item for item in data["new_senders"]}
        # wxid_a 在 10 天前就发过言，不算新联系人
        self.assertNotIn("wxid_a", senders)
        self.assertIn("wxid_b", senders)
        self.assertIn("wxid_c", senders)
        self.assertEqual(senders["wxid_c"]["chat_id"], "222@chatroom")
        self.assertEqual(senders["wxid_c"]["first_message"], "支持定制吗")
        self.assertEqual(senders["wxid_b"]["message_count"], 1)

    def test_find_new_senders_min_messages(self):
        from src.mcp_server.server import handle_rpc

        response = handle_rpc({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "find_new_senders", "arguments": {
                "since": self.now - 3 * 86400,
                "min_messages": 2,
            }},
        })
        data = response["result"]["structuredContent"]
        self.assertEqual(data["count"], 0)

    def test_get_contact_profile(self):
        from src.mcp_server.server import handle_rpc

        response = handle_rpc({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "get_contact_profile", "arguments": {"contact": "客户A"}},
        })
        data = response["result"]["structuredContent"]
        self.assertEqual(data["wxid"], "wxid_a")
        self.assertEqual(data["name"], "客户A-群昵称")
        self.assertFalse(data["is_friend"])
        self.assertTrue(data["found"])
        self.assertEqual(data["total_message_count"], 2)
        self.assertEqual(data["group_count"], 1)
        self.assertEqual(data["groups"][0]["chat_id"], "111@chatroom")
        self.assertEqual(len(data["recent_messages"]), 2)

    def test_get_contact_profile_friend(self):
        from src.mcp_server.server import handle_rpc

        response = handle_rpc({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "get_contact_profile", "arguments": {"contact": "好友张三"}},
        })
        data = response["result"]["structuredContent"]
        self.assertEqual(data["wxid"], "wxid_friend")
        self.assertTrue(data["is_friend"])
        self.assertEqual(data["alias"], "zhangsan")
        self.assertEqual(data["private_message_count"], 1)
        self.assertEqual(data["group_count"], 0)

    def test_message_content_truncated(self):
        from src.mcp_server.server import handle_rpc

        long_text = "长" * 2500
        conn = sqlite3.connect(str(self.db_path))
        conn.execute(
            """INSERT INTO messages
                   (message_id, chat_id, sender_id, sender_name, content, msg_type, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            ("m_long", "111@chatroom", "wxid_d", "客户D", long_text, 1, self.now),
        )
        conn.commit()
        conn.close()

        response = handle_rpc({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "get_messages", "arguments": {
                "chat": "111@chatroom", "sender": "wxid_d",
            }},
        })
        data = response["result"]["structuredContent"]
        self.assertEqual(data["count"], 1)
        message = data["messages"][0]
        self.assertTrue(message["content_truncated"])
        self.assertEqual(len(message["content"]), 2000 + len("…(已截断)"))

    def test_tool_argument_error_is_tool_error(self):
        from src.mcp_server.server import handle_rpc

        response = handle_rpc({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "get_messages", "arguments": {}},
        })
        self.assertTrue(response["result"]["isError"])
        self.assertIn("chat", response["result"]["content"][0]["text"])

    def test_describe_server(self):
        from src.mcp_server.server import describe_server

        data = describe_server("http://127.0.0.1:7327")
        self.assertTrue(data["ok"])
        self.assertEqual(data["endpoint"], "http://127.0.0.1:7327/mcp")
        self.assertEqual(data["sse_endpoint"], "http://127.0.0.1:7327/mcp/sse")
        self.assertEqual(data["api_key"], "test_key_123456")
        self.assertEqual(len(data["tools"]), 18)
        self.assertIn("127.0.0.1", data["allowed_hosts"])

    def test_update_settings_roundtrip(self):
        from src.mcp_server.server import get_settings, update_settings

        update_settings(enabled=False)
        self.assertFalse(get_settings()["enabled"])
        self.assertIn("MCP_ENABLED=false", self.env_file.read_text(encoding="utf-8"))

        update_settings(enabled=True, regenerate=True)
        settings = get_settings()
        self.assertTrue(settings["enabled"])
        self.assertTrue(settings["api_key"].startswith("webot_"))
        self.assertNotEqual(settings["api_key"], "test_key_123456")

    def test_api_key_rotation(self):
        from src.mcp_server.server import handle_http, update_settings

        old_key = "test_key_123456"
        new_key = update_settings(regenerate=True)["api_key"]
        self.assertNotEqual(new_key, old_key)
        self.assertEqual(len(new_key), len("webot_") + 43)
        self.assertIn(f"MCP_API_KEY={new_key}", self.env_file.read_text(encoding="utf-8"))

        body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}).encode()
        old_handler = FakeHandler("POST", "/mcp", body=body, headers={
            "Authorization": f"Bearer {old_key}",
        })
        self.assertTrue(handle_http(old_handler))
        self.assertEqual(old_handler.status, 401)

        new_handler = FakeHandler("POST", "/mcp", body=body, headers={
            "Authorization": f"Bearer {new_key}",
        })
        self.assertTrue(handle_http(new_handler))
        self.assertEqual(new_handler.status, 200)

        # 再轮换一次，上一轮的新密钥同样立即失效
        latest_key = update_settings(regenerate=True)["api_key"]
        latest_handler = FakeHandler("POST", "/mcp", body=body, headers={
            "Authorization": f"Bearer {new_key}",
        })
        handle_http(latest_handler)
        self.assertEqual(latest_handler.status, 401)
        self.assertNotEqual(latest_key, new_key)

    def test_parse_time_formats(self):
        from src.mcp_server.data import parse_time

        self.assertEqual(parse_time("100"), 100)
        self.assertIsNotNone(parse_time("7d"))
        self.assertIsNotNone(parse_time("2026-01-01"))
        with self.assertRaises(ValueError):
            parse_time("not-a-time")

    # ── 数据范围 ────────────────────────────────────────────────────

    def _set_scope(self, groups=None, friends=None):
        values = {}
        if groups is not None:
            values["MCP_GROUPS"] = groups
        if friends is not None:
            values["MCP_FRIENDS"] = friends
        patcher = patch.dict(os.environ, values, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _call(self, name, arguments=None):
        from src.mcp_server.server import handle_rpc

        return handle_rpc({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": name, "arguments": arguments or {}},
        })

    def test_scope_defaults_to_all(self):
        from src.mcp_server.server import describe_server

        data = describe_server("http://127.0.0.1:7327")
        self.assertEqual(data["scope"], {"groups": "*", "friends": "*"})
        self.assertTrue(data["scope_options"]["groups"])
        self.assertTrue(data["scope_options"]["friends"])

        result = self._call("search_messages", {"keyword": "在吗"})
        self.assertEqual(result["result"]["structuredContent"]["count"], 1)

    def test_scope_limits_groups_and_friends(self):
        self._set_scope(groups="111@chatroom", friends="none")

        groups = self._call("list_groups")["result"]["structuredContent"]["groups"]
        self.assertEqual([group["chat_id"] for group in groups], ["111@chatroom"])

        friends = self._call("list_friends")["result"]["structuredContent"]
        self.assertEqual(friends["count"], 0)

        allowed = self._call("get_messages", {"chat": "111@chatroom"})
        self.assertEqual(allowed["result"]["structuredContent"]["count"], 3)

        blocked = self._call("get_messages", {"chat": "222@chatroom"})
        self.assertTrue(blocked["result"]["isError"])
        self.assertIn("数据范围", blocked["result"]["content"][0]["text"])

        self.assertEqual(
            self._call("search_messages", {"keyword": "报价"})["result"]["structuredContent"]["count"],
            1,
        )
        self.assertEqual(
            self._call("search_messages", {"keyword": "支持定制"})["result"]["structuredContent"]["count"],
            0,
        )

        overview = self._call("get_data_overview")["result"]["structuredContent"]
        self.assertEqual(overview["message_count"], 3)
        self.assertEqual(overview["scope"], {"groups": "111@chatroom", "friends": "none"})

        activity = self._call("get_group_activity", {
            "since": self.now - 3 * 86400, "until": self.now,
        })["result"]["structuredContent"]
        self.assertEqual([group["chat_id"] for group in activity["groups"]], ["111@chatroom"])

        contacts = self._call("search_contacts", {"query": "客户C"})["result"]["structuredContent"]
        self.assertFalse(any(row["chat_id"] == "222@chatroom" for row in contacts["group_members"]))

    def test_scope_none_blocks_everything(self):
        self._set_scope(groups="none", friends="none")

        self.assertEqual(self._call("list_groups")["result"]["structuredContent"]["count"], 0)
        self.assertEqual(self._call("list_friends")["result"]["structuredContent"]["count"], 0)
        self.assertEqual(
            self._call("search_messages", {"keyword": "支持"})["result"]["structuredContent"]["count"],
            0,
        )
        overview = self._call("get_data_overview")["result"]["structuredContent"]
        self.assertEqual(overview["message_count"], 0)
        self.assertEqual(overview["group_count"], 0)

    def test_scope_url_encoded_ids(self):
        from src.mcp_server.data import get_scope, is_chat_allowed

        self._set_scope(groups="111%40chatroom")
        self.assertTrue(is_chat_allowed("111@chatroom"))
        self.assertFalse(is_chat_allowed("222@chatroom"))
        self.assertEqual(get_scope()["groups"], "111%40chatroom")

    def test_scope_update_settings(self):
        from src.mcp_server.server import update_settings

        settings = update_settings(groups="111@chatroom,222@chatroom", friends="none")
        self.assertEqual(settings["scope"]["groups"], "111@chatroom,222@chatroom")
        self.assertEqual(settings["scope"]["friends"], "none")
        text = self.env_file.read_text(encoding="utf-8")
        self.assertIn("MCP_GROUPS=111@chatroom,222@chatroom", text)
        self.assertIn("MCP_FRIENDS=none", text)

        reset = update_settings(groups="*", friends="")
        self.assertEqual(reset["scope"], {"groups": "*", "friends": "*"})


if __name__ == "__main__":
    unittest.main()
