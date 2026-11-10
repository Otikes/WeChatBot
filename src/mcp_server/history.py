"""MCP 完整历史消息数据源（直接读取微信本地数据库）。

MCP 的 ``messages.db`` 只包含机器人轮询后采集到的消息：默认每个会话每轮
只取最新 50 条，启动前的历史最多覆盖那个窗口。要让智能体真正查到"很久
以前"的聊天记录，必须直接读微信本地 SQLCipher 库。

本模块负责：
1. 懒加载 ``LocalWcdbClient``（首次查询时初始化，失败后按 ``RETRY_SEC``
   退避重试，避免每次工具调用都卡在密钥提取上）；
2. 机器人正在运行时复用其已打开的客户端，避免重复解密；
3. 微信未登录 / 密钥失效 / 主动关闭时抛出 ``HistoryUnavailable``，由
   ``data.py`` 决定是否回退到 ``messages.db``。

可用 ``MCP_HISTORY_SOURCE=messages`` 环境变量关闭本地历史读取（测试或
只想看已采集数据时使用）。
"""

from __future__ import annotations

import logging
import os
import threading
import time

logger = logging.getLogger(__name__)

MCP_HISTORY_ENV = "MCP_HISTORY_SOURCE"
RETRY_SEC = 60.0
_DISABLED_VALUES = {
    "messages",
    "messages_db",
    "cache",
    "off",
    "0",
    "false",
    "disable",
    "disabled",
}

_lock = threading.RLock()
_client = None
_owns_client = False
_media_resolver = None
_error = ""
_checked_at = 0.0
_account_checked_at = 0.0
ACCOUNT_CHECK_SEC = 60.0


class HistoryUnavailable(RuntimeError):
    """微信本地历史库不可用（未启用 / 微信未运行 / 密钥失效）。"""


def enabled() -> bool:
    """本地历史读取是否启用（默认启用，可用环境变量关闭）。"""
    value = os.getenv(MCP_HISTORY_ENV, "auto").strip().lower()
    return value not in _DISABLED_VALUES


def _running_bot_client():
    """复用正在运行的机器人已打开的 WCDB 客户端。"""
    try:
        # 延迟导入：server 模块顶层会导入 MCP，避免循环依赖
        from src.web.server import _bot_control

        backend = _bot_control.get_backend()
        client = getattr(backend, "_client", None)
        if client is not None and getattr(client, "_db", None) is not None:
            return client
    except Exception:
        pass
    return None


def _current_account() -> str:
    """当前登录账号目录名。

    只做目录 mtime 启发式，不能 new 一个 ``WeChatDB``——构造函数会立即
    提取/校验密钥，代价太高；这里用 ``__new__`` 跳过初始化。
    """
    from src.wechat.wxdb_reader import WeChatDB, auto_detect_db_dir

    db_dir = auto_detect_db_dir()
    if not db_dir:
        return ""
    probe = WeChatDB.__new__(WeChatDB)
    probe.db_dir = db_dir
    return probe._pick_account(prefer_marker=False)


def _close_owned_locked() -> None:
    global _client, _owns_client

    client = _client
    owns = _owns_client
    _client = None
    _owns_client = False
    if client is not None and owns:
        try:
            client.close()
        except Exception:
            pass


def _get_client():
    global _client, _owns_client, _error, _checked_at, _account_checked_at

    with _lock:
        now = time.monotonic()
        expected_account = ""
        if _client is not None and _owns_client:
            # 机器人启动后优先复用它的实例，避免同一进程里两份客户端
            # 同时重建解密缓存（Windows 上会互相占用临时文件）。
            # 旧实例不主动 close：可能仍有并发查询在用，交给 GC 回收即可。
            shared = _running_bot_client()
            if shared is not None and shared is not _client:
                _client = shared
                _owns_client = False
                _error = ""
                _checked_at = now
                _account_checked_at = now
        if _client is not None:
            # 微信更换登录账号后必须丢弃旧实例，否则会串到上一个账号的数据
            if now - _account_checked_at >= ACCOUNT_CHECK_SEC:
                _account_checked_at = now
                try:
                    current = _current_account()
                except Exception:
                    current = ""
                if current and current != str(getattr(_client, "account", "")):
                    logger.info(
                        "MCP history account switched (%s -> %s), reloading",
                        getattr(_client, "account", ""), current,
                    )
                    _close_owned_locked()
                    _error = ""
                    expected_account = current
                else:
                    return _client
            else:
                return _client

        if not enabled():
            raise HistoryUnavailable(
                "已通过 %s 关闭微信本地历史读取" % MCP_HISTORY_ENV
            )
        if _error and now - _checked_at < RETRY_SEC:
            raise HistoryUnavailable(_error)

        shared = _running_bot_client()
        if shared is not None and expected_account:
            shared_account = str(getattr(shared, "account", ""))
            if shared_account and shared_account != expected_account:
                # 机器人还没来得及切到新账号，先自己打开新账号的库
                shared = None
        if shared is not None:
            _client = shared
            _owns_client = False
            _error = ""
            _checked_at = now
            _account_checked_at = now
            return _client

        from src.wechat.local_wcdb_client import LocalWcdbClient

        client = LocalWcdbClient()
        try:
            client.init()
            client.open()
        except Exception as exc:
            try:
                client.close()
            except Exception:
                pass
            _error = "微信本地数据库不可用：%s" % exc
            _checked_at = now
            logger.info("MCP history source unavailable: %s", exc)
            raise HistoryUnavailable(_error) from exc

        _client = client
        _owns_client = True
        _error = ""
        _checked_at = now
        _account_checked_at = now
        logger.info("MCP history source ready (account=%s)", client.account)
        return _client


def _invalidate(reason: str) -> None:
    """读取失败后丢弃客户端，下次调用重新初始化。"""
    global _client, _owns_client, _media_resolver, _error, _checked_at

    with _lock:
        client = _client
        owns = _owns_client
        _client = None
        _owns_client = False
        _media_resolver = None
        _error = "微信本地数据库读取失败：%s" % reason
        _checked_at = time.monotonic()
        if client is not None and owns:
            try:
                client.close()
            except Exception:
                pass


def reset() -> None:
    """清空缓存客户端（测试或账号切换后调用）。"""
    global _client, _owns_client, _media_resolver, _error, _checked_at, _account_checked_at

    with _lock:
        client = _client
        owns = _owns_client
        _client = None
        _owns_client = False
        _media_resolver = None
        _error = ""
        _checked_at = 0.0
        _account_checked_at = 0.0
        if client is not None and owns:
            try:
                client.close()
            except Exception:
                pass


def status() -> dict:
    """不触发初始化，返回当前历史数据源状态。"""
    with _lock:
        return {
            "enabled": enabled(),
            "ready": _client is not None,
            "shared_with_bot": bool(_client is not None and not _owns_client),
            "account": str(getattr(_client, "account", "") or ""),
            "error": _error,
        }


def get_wechat_db():
    """返回当前已解密的 ``WeChatDB``；不可用时抛 ``HistoryUnavailable``。"""
    client = _get_client()
    db = getattr(client, "_db", None)
    if db is None:
        raise HistoryUnavailable("微信本地数据库尚未打开")
    return db


def get_media_resolver():
    """按当前账号懒加载 ``MediaResolver``，账号切换时自动重建。"""
    global _media_resolver

    from src.wechat.media import MediaResolver

    with _lock:
        db = get_wechat_db()
        account = str(getattr(db, "account", "") or "")
        current = _media_resolver
        if current is None or getattr(current, "_resolver_account", None) != account:
            current = MediaResolver(db)
            setattr(current, "_resolver_account", account)
            _media_resolver = current
        return current


def query_messages(
    chat_id: str,
    *,
    limit: int = 50,
    offset: int = 0,
    order: str = "desc",
    since: int | None = None,
    until: int | None = None,
    sender: str = "",
    keyword: str = "",
) -> tuple[list[dict], bool]:
    """查询会话完整历史，返回 ``(rows, has_more)``。"""
    client = _get_client()
    try:
        return client.query_messages(
            chat_id,
            limit=limit,
            offset=offset,
            order=order,
            since=since,
            until=until,
            sender=sender,
            keyword=keyword,
        )
    except Exception as exc:
        _invalidate(str(exc))
        raise HistoryUnavailable(
            "微信本地数据库读取失败：%s" % exc
        ) from exc


def sender_stats(
    chat_id: str,
    *,
    since: int | None = None,
    until: int | None = None,
) -> list[dict]:
    """按发送者聚合会话完整历史的消息数。"""
    client = _get_client()
    try:
        return client.sender_stats(chat_id, since=since, until=until)
    except Exception as exc:
        _invalidate(str(exc))
        raise HistoryUnavailable(
            "微信本地数据库读取失败：%s" % exc
        ) from exc


def display_names(wxids: list[str]) -> dict[str, str]:
    """从微信通讯录补全 wxid -> 昵称（本地缓存缺失时兜底）。"""
    if not wxids:
        return {}
    client = _get_client()
    try:
        return client.get_display_names(wxids)
    except Exception:
        return {}
