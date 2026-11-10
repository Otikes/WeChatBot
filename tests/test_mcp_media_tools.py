# -*- coding: utf-8 -*-
"""Tests for MCP media tools: get_message_media / list_chat_media / include_media."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.mcp_server import data
from src.mcp_server.server import TOOLS, _tool_result

CHAT = "111@chatroom"
IMAGE_BLOCK = {"type": "image", "data": "Zm9v", "mimeType": "image/jpeg"}


class FakeDB:
    def __init__(self):
        self.rows: dict[int, dict] = {}
        self.media_rows: list[dict] = []
        self.media_calls: list[dict] = []

    def get_message_row(self, chat, local_id, local_type=None, shard=None):
        return self.rows.get(int(local_id))

    def get_media_rows(self, chat, types, since=None, until=None, limit=200, offset=0):
        self.media_calls.append({
            "types": set(types), "since": since, "until": until,
            "limit": limit, "offset": offset,
        })
        return self.media_rows[offset:offset + limit]


class FakeResolver:
    def __init__(self):
        self.summarized: list[int] = []
        self.resolved: list[int] = []

    def summarize(self, chat_id, row):
        self.summarized.append(int(row["local_id"]))
        return {"kind": "image", "available": True, "path": "/tmp/cache/a.jpg"}

    def resolve(self, chat_id, row, kind="auto", inline=False, download=True):
        self.resolved.append(int(row["local_id"]))
        result = {
            "kind": "image",
            "available": True,
            "items": [{"path": "/tmp/cache/a.jpg", "mime": "image/jpeg", "size": 3}],
        }
        if inline:
            result["_content_blocks"] = [dict(IMAGE_BLOCK)]
        return result


def _row(local_id=7, local_type=3, timestamp=1700000000, shard="message_0"):
    return {
        "local_id": local_id,
        "local_type": local_type,
        "create_time": timestamp,
        "content": "image-content",
        "packed_info": b"0123456789abcdef0123456789abcdef",
        "shard": shard,
        "server_id": 1000 + local_id,
    }


class TestToolSchemas(unittest.TestCase):
    def test_media_tools_registered(self):
        names = {tool["name"] for tool in TOOLS}
        self.assertIn("get_message_media", names)
        self.assertIn("list_chat_media", names)
        self.assertIn("get_message_media", data.TOOL_FUNCTIONS)
        self.assertIn("list_chat_media", data.TOOL_FUNCTIONS)

    def test_get_messages_include_media(self):
        tool = next(t for t in TOOLS if t["name"] == "get_messages")
        prop = tool["inputSchema"]["properties"]["include_media"]
        self.assertEqual(prop["type"], "boolean")
        self.assertFalse(prop["default"])


class TestToolResultBlocks(unittest.TestCase):
    def test_content_blocks_hoisted(self):
        payload = {"ok": True, "_content_blocks": [dict(IMAGE_BLOCK)]}
        result = _tool_result(payload)
        self.assertEqual(result["content"][0]["type"], "text")
        self.assertEqual(result["content"][1], IMAGE_BLOCK)
        self.assertNotIn("_content_blocks", result["structuredContent"])
        self.assertEqual(json.loads(result["content"][0]["text"]), {"ok": True})

    def test_plain_result(self):
        result = _tool_result({"ok": True})
        self.assertEqual(len(result["content"]), 1)
        self.assertEqual(result["structuredContent"], {"ok": True})


class TestMediaRowsQuery(unittest.TestCase):
    def test_filters_by_base_local_type(self):
        from src.wechat.wxdb_reader import WeChatDB
        db = WeChatDB.__new__(WeChatDB)
        captured = {}

        def fake_shard_rows(tables, sql_ext, params=(), order_ext="", per_shard_limit=None):
            captured["sql"] = sql_ext
            captured["params"] = params
            return []

        db._shard_rows = fake_shard_rows
        db._run_msg_query = lambda user, builder: builder([])
        rows = WeChatDB.get_media_rows(db, CHAT, {3, 49}, limit=5)
        self.assertEqual(rows, [])
        # appmsg 的 local_type 带高位 subtype（如 244813135921），必须按低 32 位匹配
        self.assertIn("local_type & 4294967295", captured["sql"])
        self.assertEqual(list(captured["params"]), [3, 49])


class TestInlineBlocks(unittest.TestCase):
    def _resolver(self):
        from src.wechat.media import MediaResolver
        return MediaResolver.__new__(MediaResolver)

    def test_skips_wxgf_and_uses_previewable_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            wxgf = Path(tmp) / "a.wxgf"
            wxgf.write_bytes(b"wxgf\x00")
            jpg = Path(tmp) / "a.jpg"
            jpg.write_bytes(b"\xff\xd8\xff\xe0" + b"x" * 10)
            result = {"items": [
                {"path": str(wxgf), "mime": "image/wxgf"},
                {"path": str(jpg), "mime": "image/jpeg"},
            ]}
            self._resolver()._attach_inline(result)
            self.assertEqual(result["_content_blocks"][0]["mimeType"], "image/jpeg")

    def test_no_previewable_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            wxgf = Path(tmp) / "a.wxgf"
            wxgf.write_bytes(b"wxgf\x00")
            result = {"items": [{"path": str(wxgf), "mime": "image/wxgf"}]}
            self._resolver()._attach_inline(result)
            self.assertNotIn("_content_blocks", result)


class TestGetMessageMedia(unittest.TestCase):
    def setUp(self):
        self.db = FakeDB()
        self.resolver = FakeResolver()
        self.db.rows[7] = _row()
        self.patches = [
            patch.object(data.history_source, "get_wechat_db", return_value=self.db),
            patch.object(data.history_source, "get_media_resolver", return_value=self.resolver),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def test_resolve_without_inline(self):
        result = data.get_message_media({"chat": CHAT, "local_id": 7})
        self.assertEqual(result["local_id"], 7)
        self.assertEqual(result["msg_type_label"], "image")
        self.assertEqual(result["media"]["kind"], "image")
        self.assertNotIn("_content_blocks", result)
        self.assertEqual(self.resolver.resolved, [7])

    def test_resolve_with_inline(self):
        result = data.get_message_media({"chat": CHAT, "local_id": 7, "inline": True})
        self.assertEqual(result["_content_blocks"], [IMAGE_BLOCK])
        self.assertNotIn("_content_blocks", result["media"])

    def test_missing_local_id(self):
        with self.assertRaises(ValueError):
            data.get_message_media({"chat": CHAT})

    def test_message_not_found(self):
        with self.assertRaises(ValueError):
            data.get_message_media({"chat": CHAT, "local_id": 999})


class TestListChatMedia(unittest.TestCase):
    def setUp(self):
        self.db = FakeDB()
        self.resolver = FakeResolver()
        self.db.media_rows = [_row(7), _row(8, local_type=43)]
        self.patches = [
            patch.object(data.history_source, "get_wechat_db", return_value=self.db),
            patch.object(data.history_source, "get_media_resolver", return_value=self.resolver),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def test_summary_only(self):
        result = data.list_chat_media({"chat": CHAT, "kind": "image"})
        self.assertEqual(result["count"], 2)
        self.assertFalse(result["has_more"])
        self.assertEqual(self.resolver.summarized, [7, 8])
        self.assertEqual(self.resolver.resolved, [])
        self.assertEqual(self.db.media_calls[0]["types"], {3})

    def test_pagination_and_resolve(self):
        result = data.list_chat_media({"chat": CHAT, "limit": 1, "resolve": True})
        self.assertEqual(result["count"], 1)
        self.assertTrue(result["has_more"])
        self.assertEqual(self.resolver.resolved, [7])
        self.assertEqual(result["messages"][0]["media"]["kind"], "image")

    def test_invalid_kind(self):
        with self.assertRaises(ValueError):
            data.list_chat_media({"chat": CHAT, "kind": "unknown"})


class TestIncludeMediaSummary(unittest.TestCase):
    def setUp(self):
        self.db = FakeDB()
        self.resolver = FakeResolver()
        self.db.rows[7] = _row()
        self.patches = [
            patch.object(data.history_source, "get_wechat_db", return_value=self.db),
            patch.object(data.history_source, "get_media_resolver", return_value=self.resolver),
            # 避免解析发送者昵称时触发真实微信库初始化
            patch.object(data, "_history_sender_names", return_value={}),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def test_attaches_media_to_non_text_rows(self):
        rows = [
            {"local_id": 7, "local_type": 3, "timestamp": 1700000000,
             "content": "img", "shard": "message_0", "sender_username": "wxid_a"},
            {"local_id": 8, "local_type": 1, "timestamp": 1700000001,
             "content": "hello", "shard": "message_0", "sender_username": "wxid_a"},
        ]
        result = data._history_messages_result(CHAT, rows, False, 50, 0, include_media=True)
        self.assertEqual(result["messages"][0]["media"]["kind"], "image")
        self.assertNotIn("media", result["messages"][1])
        self.assertEqual(self.resolver.summarized, [7])

    def test_no_media_by_default(self):
        rows = [
            {"local_id": 7, "local_type": 3, "timestamp": 1700000000,
             "content": "img", "shard": "message_0", "sender_username": "wxid_a"},
        ]
        result = data._history_messages_result(CHAT, rows, False, 50, 0)
        self.assertNotIn("media", result["messages"][0])
        self.assertEqual(self.resolver.summarized, [])


if __name__ == "__main__":
    unittest.main()
