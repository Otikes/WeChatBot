"""按需同步微信通讯录缓存（无需启动机器人）。

控制台在机器人停止时也能刷新群聊 / 群成员 / 好友缓存：
只打开微信本地数据库读取通讯录，不启动消息轮询线程，也不发送任何消息。
"""

from __future__ import annotations

import json
import logging
import threading

from src.config import webot_data_path
from src.wechat.wcdb_backend import WcdbBackend
from src.wechat.local_wcdb_client import LocalWcdbClient

logger = logging.getLogger(__name__)

_sync_lock = threading.Lock()


def cache_counts() -> tuple[int, int]:
    """读取本地缓存后的 (群聊数, 好友数)。"""
    groups = 0
    path = webot_data_path("group_names.json")
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                # 只统计仍在群里的（active != False）
                groups = sum(
                    1 for key, val in raw.items()
                    if str(key).endswith("@chatroom")
                    and WcdbBackend._cache_entry_active(val)
                )
        except (OSError, json.JSONDecodeError):
            pass

    friends = 0
    path = webot_data_path("friend_names.json")
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            entries = raw.get("friends") if isinstance(raw, dict) else None
            if isinstance(entries, dict):
                friends = sum(
                    1 for val in entries.values()
                    if WcdbBackend._cache_entry_active(val)
                )
            elif isinstance(raw, dict):
                friends = sum(1 for key in raw if not str(key).startswith("_") and key != "account")
        except (OSError, json.JSONDecodeError):
            pass
    return groups, friends


def sync_wechat_caches() -> dict:
    """打开微信数据库并刷新本地缓存，返回同步后的群聊/好友数量。"""
    if not _sync_lock.acquire(blocking=False):
        raise RuntimeError("正在同步微信数据，请稍候重试")

    client = None
    try:
        client = LocalWcdbClient()
        client.init()
        client.open()
        backend = WcdbBackend(groups=["*"], friends=[])
        backend._client = client
        backend._prepare_account_caches()
        backend._resolve_groups()
        backend._resolve_friends()
        groups, friends = cache_counts()
        logger.info("WeChat cache synced: %d groups, %d friends", groups, friends)
        return {"groups": groups, "friends": friends}
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                logger.debug("Failed to close WCDB client", exc_info=True)
        _sync_lock.release()
