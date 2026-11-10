"""Tests for 1-on-1 friend chat routing in MessageRouter."""

import time
import unittest
from types import SimpleNamespace

try:
    from src.router import AT_MENTION_MAX_AGE_SEC, MessageRouter
    IMPORT_ERROR = None
except Exception as exc:  # pragma: no cover - import guard
    MessageRouter = None
    IMPORT_ERROR = exc


class FakeSummarizer:
    def __init__(self, reply="你好呀"):
        self.reply = reply
        self.calls = []

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        return self.reply


class FakeNicknames:
    @staticmethod
    def resolve_name(sender_id):
        return sender_id

    @staticmethod
    def resolve_wxids(text):
        return text


class FakeStore:
    @staticmethod
    def insert_message(msg):
        return True

    @staticmethod
    def get_messages_since(chat_id, since, limit=20):
        return []

    @staticmethod
    def get_group_memory(chat_id):
        return None


class FakeDetector:
    @staticmethod
    def is_trigger(**kwargs):
        return False


def _router():
    router = object.__new__(MessageRouter)
    router._store = FakeStore()
    router._summarizer = FakeSummarizer()
    router._nicks = FakeNicknames()
    router._config = SimpleNamespace(
        bot_display_name="小助手",
        friend_chat_enabled=True,
    )
    return router


def _group_router(group_chat_enabled=True):
    router = _router()
    router._config = SimpleNamespace(
        bot_display_name="小助手",
        welcome_enabled=False,
        fun_enabled=False,
        admin_wxid="",
        image_gen_enabled=False,
        group_chat_enabled=group_chat_enabled,
        friend_chat_enabled=True,
    )
    router._memory = SimpleNamespace(schedule=lambda *a: None)
    router._sticky = None
    router._feishu_export = None
    router._admin = SimpleNamespace(handle=lambda content, name: None)
    router._todo_handler = None
    router._todo_store = None
    router._image_gen = None
    router._detector = FakeDetector()
    router.messages_processed = 0
    return router


def _msg(**overrides):
    msg = {
        "message_id": "m1",
        "chat_id": "wxid_alice",
        "group_name": "Alice",
        "sender_id": "wxid_alice",
        "sender_name": "Alice",
        "content": "今天好累",
        "msg_type": 1,
        "timestamp": int(time.time()),
        "is_at_mentioned": False,
        "is_group": False,
    }
    msg.update(overrides)
    return msg


@unittest.skipIf(MessageRouter is None, f"router unavailable: {IMPORT_ERROR}")
class FriendChatRoutingTests(unittest.TestCase):
    def test_text_message_gets_reply_without_at_prefix(self):
        router = _router()
        reply = router._handle_friend_chat(_msg())

        self.assertEqual(reply, "你好呀")
        call = router._summarizer.calls[0]
        self.assertTrue(call["is_private"])
        self.assertEqual(call["message"], "今天好累")
        self.assertEqual(call["group_name"], "Alice")

    def test_group_chat_reply_still_has_at_prefix(self):
        router = _router()
        reply = router._handle_chat(_msg(is_group=True), "hi")

        self.assertEqual(reply, "@Alice 你好呀")

    def test_non_text_message_is_ignored(self):
        router = _router()
        reply = router._handle_friend_chat(
            _msg(msg_type=3, content="[图片]"),
        )

        self.assertIsNone(reply)
        self.assertEqual(router._summarizer.calls, [])

    def test_untranscribed_voice_message_is_ignored(self):
        router = _router()
        reply = router._handle_friend_chat(
            _msg(msg_type=34, content="[语音]"),
        )

        self.assertIsNone(reply)

    def test_transcribed_voice_message_is_replied_to(self):
        router = _router()
        reply = router._handle_friend_chat(
            _msg(msg_type=34, content="[语音] 今天好累"),
        )

        self.assertEqual(reply, "你好呀")

    def test_stale_message_is_ignored(self):
        router = _router()
        reply = router._handle_friend_chat(
            _msg(timestamp=int(time.time()) - AT_MENTION_MAX_AGE_SEC - 10),
        )

        self.assertIsNone(reply)
        self.assertEqual(router._summarizer.calls, [])

    def test_reply_quote_prefix_is_stripped(self):
        router = _router()
        router._handle_friend_chat(
            _msg(content="wxid_alice:\n今天好累"),
        )

        self.assertEqual(router._summarizer.calls[0]["message"], "今天好累")

    def test_friend_chat_switch_off_returns_none(self):
        router = _router()
        router._config.friend_chat_enabled = False
        reply = router._handle_friend_chat(_msg())

        self.assertIsNone(reply)
        self.assertEqual(router._summarizer.calls, [])

    def test_group_chat_switch_off_skips_ai_chat(self):
        router = _group_router(group_chat_enabled=False)
        reply = router.handle(_msg(
            is_group=True,
            is_at_mentioned=True,
            content="@小助手 今天好累",
        ))

        self.assertIsNone(reply)
        self.assertEqual(router._summarizer.calls, [])

    def test_group_chat_switch_on_still_replies(self):
        router = _group_router(group_chat_enabled=True)
        reply = router.handle(_msg(
            is_group=True,
            is_at_mentioned=True,
            content="@小助手 今天好累",
        ))

        self.assertEqual(reply, "@Alice 你好呀")


if __name__ == "__main__":
    unittest.main()
