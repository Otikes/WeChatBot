"""微信通讯录标签的只读入口。

**与系统群发分组完全独立**：这里读的是微信自带的通讯录标签，
不会被导入、同步或合并到 ``src.broadcast`` 维护的群发分组里。
供 Web API 与 MCP 工具共用，避免两处各自解密数据库。
"""

from __future__ import annotations

import json
import logging

from src.config import webot_data_path

logger = logging.getLogger(__name__)


def _running_client():
    """优先复用运行中机器人已解密的 WCDB 客户端，避免重复取密钥/解密。"""
    try:
        from src.web.server import _bot_control

        backend = _bot_control.get_backend()
        client = getattr(backend, "_client", None)
        if client is not None and getattr(client, "_db", None) is not None:
            return client
    except Exception:
        pass
    return None


def _friend_names() -> dict[str, str]:
    """从好友缓存读出 wxid → 展示名，用于给标签成员补昵称。"""
    path = webot_data_path("friend_names.json")
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    entries = raw.get("friends")
    if not isinstance(entries, dict):
        entries = raw
    out: dict[str, str] = {}
    for wxid, value in entries.items():
        if isinstance(value, dict):
            out[str(wxid)] = str(value.get("name") or wxid)
        elif value:
            out[str(wxid)] = str(value)
    return out


def read_contact_labels() -> dict:
    """返回微信原生通讯录标签报告（含成员昵称）。

    失败时返回 ``available=False`` + ``note``，不抛异常；调用方应把
    ``note`` 展示给用户，说明是微信版本/登录状态导致读不到。
    """
    client = _running_client()
    if client is None:
        try:
            from src.wechat.local_wcdb_client import LocalWcdbClient

            client = LocalWcdbClient()
            client.init()
        except Exception as exc:
            logger.warning("WeChat label read unavailable: %s", exc)
            return {
                "available": False, "labels": [], "source": "",
                "tables": [], "note": f"微信本地数据库不可用：{exc}",
            }

    report = client.get_contact_labels()
    names = _friend_names()
    for label in report.get("labels", []):
        label["members"] = [
            {"wxid": wxid, "name": names.get(wxid, "")}
            for wxid in label.get("members", [])
        ]
    return report
