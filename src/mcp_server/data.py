"""MCP 工具的数据访问层。

数据来源：
- 微信本地数据库（优先）  完整历史聊天记录，由 ``history`` 模块懒加载读取
- ``messages.db``          机器人运行期间采集到的群聊/私聊消息（回退数据源）
- ``group_names.json``     群 wxid → 群名、成员数
- ``group_members.json``   群 wxid → {成员 wxid: 群内显示名}
- ``friend_names.json``    好友 wxid → 昵称/备注
- ``nicknames.json``       Web 控制台手工维护的 wxid → 昵称覆盖

所有工具只读，不修改任何数据。
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote

from src.config import resolve_webot_storage_path, webot_data_path
from src.mcp_server import history as history_source

logger = logging.getLogger(__name__)

MAX_CONTENT_CHARS = 2000

MSG_TYPE_LABELS = {
    1: "text",
    3: "image",
    34: "voice",
    43: "video",
    47: "emoji",
    48: "location",
    49: "link_or_file",
    50: "voip",
    10000: "system",
    10002: "system",
    11000: "emoji",
}


# ── 基础工具函数 ──────────────────────────────────────────────────────


def _load_json_dict(name: str) -> dict:
    path = webot_data_path(name)
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to read %s: %s", path, exc)
        return {}
    return raw if isinstance(raw, dict) else {}


def _group_index() -> dict[str, dict]:
    """群 wxid → {name, member_count, active}（兼容旧格式 chat_id → 群名）。"""
    raw = _load_json_dict("group_names.json")
    groups: dict[str, dict] = {}
    for chat_id, value in raw.items():
        if str(chat_id).startswith("_"):
            continue
        if isinstance(value, dict):
            name = str(value.get("name") or chat_id)
            try:
                member_count = int(value.get("member_count") or 0)
            except (TypeError, ValueError):
                member_count = 0
            active = value.get("active", True)
            if isinstance(active, str):
                active = active.strip().lower() not in ("0", "false", "no", "off")
        else:
            name = str(value or chat_id)
            member_count = 0
            active = True
        groups[str(chat_id)] = {
            "name": name,
            "member_count": member_count,
            "active": bool(active),
        }
    return groups


def _friend_index() -> tuple[str, dict[str, dict]]:
    """返回 (当前微信账号, 好友 wxid → {name, alias, active})。"""
    raw = _load_json_dict("friend_names.json")
    account = str(raw.get("account") or "").strip()
    entries = raw.get("friends")
    if not isinstance(entries, dict):
        # 旧格式没有账号绑定，直接当作 wxid → 名称映射
        entries = {
            str(key): value
            for key, value in raw.items()
            if not str(key).startswith("_") and key != "account"
        }
    friends: dict[str, dict] = {}
    for wxid, value in entries.items():
        wxid = str(wxid or "").strip()
        if not wxid or "@" in wxid:
            continue
        if isinstance(value, dict):
            name = str(value.get("name") or value.get("display") or wxid).strip()
            alias = str(value.get("alias") or "").strip()
            active = value.get("active", True)
            if isinstance(active, str):
                active = active.strip().lower() not in ("0", "false", "no", "off")
        else:
            name = str(value or wxid).strip()
            alias = ""
            active = True
        friends[wxid] = {"name": name or wxid, "alias": alias, "active": bool(active)}
    return account, friends


def _member_index() -> dict[str, dict[str, str]]:
    """群 wxid → {成员 wxid: 群内显示名}。"""
    raw = _load_json_dict("group_members.json")
    members: dict[str, dict[str, str]] = {}
    for chat_id, value in raw.items():
        if not isinstance(value, dict):
            continue
        members[str(chat_id)] = {
            str(wxid): str(name or wxid)
            for wxid, name in value.items()
            if str(wxid) and not str(wxid).startswith("_")
        }
    return members


def _nickname_overrides() -> dict[str, str]:
    raw = _load_json_dict("nicknames.json")
    return {
        str(wxid): str(name)
        for wxid, name in raw.items()
        if not str(wxid).startswith("_") and str(name or "").strip()
    }


def _messages_db_path() -> Path:
    return resolve_webot_storage_path(
        os.getenv("DB_PATH", "data/messages.db"),
        "data/messages.db",
    )


# ── 数据范围（可访问的群聊 / 好友） ─────────────────────────────────

MCP_GROUPS_ENV = "MCP_GROUPS"
MCP_FRIENDS_ENV = "MCP_FRIENDS"


def _parse_scope(value: str) -> set[str] | None:
    """解析范围配置：空或 ``*`` = 全部（None），``none`` = 不允许，其余为 ID 列表。"""
    text = str(value or "").strip()
    if not text or text == "*":
        return None
    if text.lower() in ("none", "-"):
        return set()
    items: set[str] = set()
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            part = unquote(part)
        except Exception:
            pass
        items.add(part)
    return items


def get_scope() -> dict:
    """返回 MCP 数据范围原始配置（``*`` 表示全部）。"""
    return {
        "groups": os.getenv(MCP_GROUPS_ENV, "").strip() or "*",
        "friends": os.getenv(MCP_FRIENDS_ENV, "").strip() or "*",
    }


def allowed_group_ids() -> set[str] | None:
    return _parse_scope(os.getenv(MCP_GROUPS_ENV, ""))


def allowed_friend_ids() -> set[str] | None:
    return _parse_scope(os.getenv(MCP_FRIENDS_ENV, ""))


def is_chat_allowed(chat_id: str) -> bool:
    """判断某个会话是否在 MCP 可访问范围内。"""
    chat_id = str(chat_id or "")
    allowed = allowed_group_ids() if chat_id.endswith("@chatroom") else allowed_friend_ids()
    return allowed is None or chat_id in allowed


def _require_chat_allowed(chat_id: str) -> None:
    if not is_chat_allowed(chat_id):
        raise ValueError("该会话不在 MCP 数据范围内，请在控制台「MCP 服务 → 数据范围」中放开")


def _scoped_groups() -> dict[str, dict]:
    groups = _group_index()
    allowed = allowed_group_ids()
    if allowed is None:
        return groups
    return {chat_id: info for chat_id, info in groups.items() if chat_id in allowed}


def _scoped_friends() -> dict[str, dict]:
    _, friends = _friend_index()
    allowed = allowed_friend_ids()
    if allowed is None:
        return friends
    return {wxid: info for wxid, info in friends.items() if wxid in allowed}


def _scope_sql(column: str = "chat_id") -> tuple[str, list]:
    """生成数据范围 WHERE 片段（不含 WHERE/AND 前缀）；全部放开时返回空串。"""
    group_ids = allowed_group_ids()
    friend_ids = allowed_friend_ids()
    if group_ids is None and friend_ids is None:
        return "", []
    clauses: list[str] = []
    params: list = []
    if group_ids is None:
        clauses.append(f"{column} LIKE '%@chatroom'")
    elif group_ids:
        clauses.append(
            f"({column} LIKE '%@chatroom' AND {column} IN "
            f"({','.join('?' * len(group_ids))}))"
        )
        params.extend(sorted(group_ids))
    if friend_ids is None:
        clauses.append(f"{column} NOT LIKE '%@chatroom'")
    elif friend_ids:
        clauses.append(
            f"({column} NOT LIKE '%@chatroom' AND {column} IN "
            f"({','.join('?' * len(friend_ids))}))"
        )
        params.extend(sorted(friend_ids))
    if not clauses:
        return "1=0", []
    return "(" + " OR ".join(clauses) + ")", params


def scope_options() -> dict:
    """返回可供选择的数据范围候选（群聊、好友）。"""
    groups = [
        {
            "chat_id": chat_id,
            "name": info["name"],
            "member_count": info["member_count"],
            "active": info.get("active", True),
        }
        for chat_id, info in _group_index().items()
    ]
    groups.sort(key=lambda item: (not item["active"], item["name"]))
    friends = [
        {
            "wxid": wxid,
            "name": info["name"],
            "alias": info["alias"],
            "active": info.get("active", True),
        }
        for wxid, info in _friend_index()[1].items()
    ]
    friends.sort(key=lambda item: (not item["active"], item["name"]))
    return {"groups": groups, "friends": friends}


def _db_conn() -> sqlite3.Connection | None:
    path = _messages_db_path()
    if not path.exists():
        return None
    try:
        conn = sqlite3.connect(str(path), timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        return conn
    except sqlite3.Error as exc:
        logger.warning("Failed to open messages DB %s: %s", path, exc)
        return None


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (name,),
    ).fetchone()
    return row is not None


def _like_escape(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


def _arg_int(args: dict, key: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(args.get(key, default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _arg_bool(args: dict, key: str, default: bool = False) -> bool:
    value = args.get(key, default)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _arg_str(args: dict, key: str, default: str = "") -> str:
    value = args.get(key, default)
    return str(value).strip() if value is not None else default


def parse_time(value, *, end_of_day: bool = False) -> int | None:
    """解析时间参数：unix 秒、ISO 日期时间、``7d``/``24h``/``today`` 等。"""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip()
    if not text:
        return None
    if re.fullmatch(r"-?\d+", text):
        return int(text)

    relative = re.fullmatch(r"(\d+)\s*([smhdw])", text, re.I)
    if relative:
        amount = int(relative.group(1))
        unit = relative.group(2).lower()
        seconds = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}[unit]
        return int(time.time()) - amount * seconds

    lowered = text.lower()
    now = time.localtime()
    midnight = int(time.mktime(
        (now.tm_year, now.tm_mon, now.tm_mday, 0, 0, 0, 0, 0, -1)
    ))
    if lowered == "today":
        return midnight
    if lowered == "yesterday":
        return midnight - 86400

    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d",
    ):
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        ts = int(parsed.timestamp())
        if fmt == "%Y-%m-%d" and end_of_day:
            ts += 86399
        return ts
    raise ValueError(f"无法解析时间参数: {value}（支持 unix 秒、YYYY-MM-DD、7d/24h/today）")


def _fmt_time(ts) -> str:
    try:
        value = int(ts)
    except (TypeError, ValueError):
        return ""
    if value <= 0:
        return ""
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(value))


def _msg_type_label(msg_type) -> str:
    try:
        return MSG_TYPE_LABELS.get(int(msg_type), "other")
    except (TypeError, ValueError):
        return "other"


def _chat_name_map() -> dict[str, str]:
    names = {chat_id: info["name"] for chat_id, info in _scoped_groups().items()}
    names.update({wxid: info["name"] for wxid, info in _scoped_friends().items()})
    return names


def _resolve_chat(raw: str) -> str:
    """把群名 / 好友昵称 / wxid 解析为 chat_id。"""
    text = str(raw or "").strip()
    if not text:
        raise ValueError("缺少 chat 参数（群 ID、群名或好友 wxid/昵称）")
    if text.endswith("@chatroom"):
        return text

    groups = _group_index()
    exact = [chat_id for chat_id, info in groups.items() if info["name"] == text]
    if len(exact) == 1:
        return exact[0]

    _, friends = _friend_index()
    for wxid, info in friends.items():
        if text in (info["name"], info["alias"], wxid):
            return wxid

    fuzzy = [chat_id for chat_id, info in groups.items() if text in info["name"]]
    if len(fuzzy) == 1:
        return fuzzy[0]
    if len(exact) > 1 or len(fuzzy) > 1:
        candidates = exact or fuzzy
        raise ValueError(
            "匹配到多个群，请改用 chat_id: "
            + ", ".join(f"{cid}({groups[cid]['name']})" for cid in candidates[:10])
        )

    return text


def _message_filters(args: dict, chat_id: str = "") -> tuple[str, list]:
    clauses: list[str] = []
    params: list = []
    if chat_id:
        clauses.append("chat_id = ?")
        params.append(chat_id)
    since = parse_time(args.get("since"))
    if since is not None:
        clauses.append("timestamp >= ?")
        params.append(since)
    until = parse_time(args.get("until"), end_of_day=True)
    if until is not None:
        clauses.append("timestamp <= ?")
        params.append(until)
    sender = _arg_str(args, "sender")
    if sender:
        clauses.append("(sender_id = ? OR sender_name LIKE ? ESCAPE '\\')")
        params.extend([sender, f"%{_like_escape(sender)}%"])
    keyword = _arg_str(args, "keyword")
    if keyword:
        clauses.append("content LIKE ? ESCAPE '\\'")
        params.append(f"%{_like_escape(keyword)}%")
    scope_clause, scope_params = _scope_sql("chat_id")
    if scope_clause:
        clauses.append(scope_clause)
        params.extend(scope_params)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params


def _truncate_content(value, limit: int = MAX_CONTENT_CHARS) -> tuple[str, bool]:
    """截断超长消息内容，避免单条记录撑爆智能体上下文。"""
    text = str(value or "")
    if len(text) <= limit:
        return text, False
    return text[:limit] + "…(已截断)", True


def _row_to_message(row: sqlite3.Row, chat_names: dict[str, str]) -> dict:
    timestamp = int(row["timestamp"] or 0)
    chat_id = row["chat_id"]
    content, truncated = _truncate_content(row["content"])
    return {
        "id": int(row["id"]),
        "message_id": row["message_id"],
        "chat_id": chat_id,
        "chat_name": chat_names.get(chat_id, chat_id),
        "sender_id": row["sender_id"],
        "sender_name": row["sender_name"],
        "content": content,
        "content_truncated": truncated,
        "msg_type": int(row["msg_type"] or 0),
        "msg_type_label": _msg_type_label(row["msg_type"]),
        "timestamp": timestamp,
        "time": _fmt_time(timestamp),
    }


# ── 微信本地完整历史 ─────────────────────────────────────────────────

_HISTORY_SOURCES = ("auto", "wechat_db", "messages_db")


def _history_source_arg(args: dict) -> str:
    source = _arg_str(args, "source", "auto").lower() or "auto"
    return source if source in _HISTORY_SOURCES else "auto"


def _history_msg_type_label(value) -> str:
    """微信 local_type 可能带高位标志，取低位再查表。"""
    try:
        raw = int(value)
    except (TypeError, ValueError):
        return "other"
    if raw in MSG_TYPE_LABELS:
        return MSG_TYPE_LABELS[raw]
    base = raw & 0xFFFFFFFF
    if base in MSG_TYPE_LABELS:
        return MSG_TYPE_LABELS[base]
    low = base & 0xFF
    if low in MSG_TYPE_LABELS:
        return MSG_TYPE_LABELS[low]
    return "other"


def _clean_display_name(value) -> str:
    """清理微信昵称里的 NBSP/空白，避免把无效名字当显示名。"""
    return str(value or "").replace("\xa0", " ").strip()


def _history_sender_names(chat_id: str, wxids) -> dict[str, str]:
    """为本地历史消息补全发送者显示名（备注 > 群昵称 > 好友昵称 > 通讯录）。"""
    member_names = _member_index().get(chat_id, {})
    overrides = _nickname_overrides()
    _, friends = _friend_index()
    names: dict[str, str] = {}
    missing: list[str] = []
    seen: set[str] = set()
    for raw in wxids:
        wxid = str(raw or "")
        if not wxid or wxid in seen:
            continue
        seen.add(wxid)
        name = _clean_display_name(
            overrides.get(wxid)
            or member_names.get(wxid)
            or (friends.get(wxid) or {}).get("name", "")
        )
        if name:
            names[wxid] = name
        else:
            missing.append(wxid)
    if missing:
        try:
            names.update({
                wxid: cleaned
                for wxid, name in history_source.display_names(missing).items()
                if (cleaned := _clean_display_name(name))
            })
        except Exception:
            pass
    return names


def _resolve_history_sender(chat_id: str, raw: str) -> tuple[str, bool]:
    """把发送者参数解析成 wxid；无法唯一确定时返回 ``("", False)``。"""
    text = str(raw or "").strip()
    if not text:
        return "", True
    if text.startswith("wxid_") or "@" in text:
        return text, True

    candidates: set[str] = set()
    _, friends = _friend_index()
    for wxid, info in friends.items():
        if text in (info.get("name"), info.get("alias")):
            candidates.add(wxid)
    for wxid, name in _member_index().get(chat_id, {}).items():
        if text == name:
            candidates.add(wxid)
    for wxid, name in _nickname_overrides().items():
        if text == name:
            candidates.add(wxid)
    if len(candidates) == 1:
        return candidates.pop(), True
    return "", False


def _history_row_to_message(
    row: dict,
    chat_id: str,
    chat_name: str,
    sender_names: dict[str, str],
) -> dict:
    timestamp = int(row.get("timestamp") or 0)
    content, truncated = _truncate_content(row.get("content"))
    sender = str(row.get("sender_username") or "").strip()
    sender_id = sender or (
        "real_sender_id:%s" % row.get("sender_id")
        if row.get("sender_id") else ""
    )
    local_id = row.get("local_id")
    shard = str(row.get("shard") or "")
    if row.get("is_self"):
        sender_name = "我"
    else:
        sender_name = _clean_display_name(sender_names.get(sender))
        if not sender_name:
            sender_name = sender or sender_id or "未知用户"
    return {
        "id": int(local_id or 0),
        "local_id": int(local_id or 0),
        "shard": shard,
        "message_id": f"{shard}:{local_id}" if shard else str(row.get("server_id") or local_id or ""),
        "chat_id": chat_id,
        "chat_name": chat_name,
        "sender_id": sender_id,
        "sender_name": sender_name,
        "content": content,
        "content_truncated": truncated,
        "msg_type": int(row.get("local_type") or 0),
        "msg_type_label": _history_msg_type_label(row.get("local_type")),
        "timestamp": timestamp,
        "time": _fmt_time(timestamp),
        "is_self": bool(row.get("is_self")),
    }


def _history_messages_result(
    chat_id: str,
    rows: list[dict],
    has_more: bool,
    limit: int,
    offset: int,
    include_media: bool = False,
) -> dict:
    chat_names = _chat_name_map()
    chat_name = chat_names.get(chat_id, chat_id)
    sender_names = _history_sender_names(
        chat_id, [row.get("sender_username") for row in rows]
    )
    messages = [
        _history_row_to_message(row, chat_id, chat_name, sender_names)
        for row in rows
    ]
    if include_media:
        _attach_media_summaries(chat_id, rows, messages)
    return {
        "chat_id": chat_id,
        "chat_name": chat_name,
        "count": len(messages),
        "has_more": has_more,
        "source": "wechat_db",
        "limit": limit,
        "offset": offset,
        "messages": messages,
    }


def _media_base_type(value) -> int:
    try:
        return int(value) & 0xFFFFFFFF
    except (TypeError, ValueError):
        return 0


def _attach_media_summaries(chat_id: str, rows: list[dict], messages: list[dict]) -> None:
    """给非文本消息附 ``media`` 摘要（只查存在性，不解密、不下载）。"""
    try:
        db = history_source.get_wechat_db()
        resolver = history_source.get_media_resolver()
    except Exception as exc:
        logger.debug("media summary unavailable: %s", exc)
        return
    for row, message in zip(rows, messages):
        if _media_base_type(row.get("local_type")) not in {3, 34, 43, 47, 49}:
            continue
        try:
            detail = db.get_message_row(
                chat_id,
                int(row.get("local_id") or 0),
                local_type=row.get("local_type"),
                shard=row.get("shard"),
            )
            if detail:
                message["media"] = resolver.summarize(chat_id, detail)
        except Exception as exc:
            logger.debug("media summary failed (local_id=%s): %s", row.get("local_id"), exc)


def _history_member_activity(chat_id: str, stats: list[dict], limit: int) -> dict:
    total = sum(int(item.get("message_count") or 0) for item in stats)
    selected = sorted(
        stats,
        key=lambda item: int(item.get("message_count") or 0),
        reverse=True,
    )[:limit]
    names = _history_sender_names(
        chat_id, [item.get("sender_username") for item in selected]
    )
    account = _friend_index()[0]
    members = []
    for item in selected:
        wxid = str(item.get("sender_username") or "")
        count = int(item.get("message_count") or 0)
        first_ts = int(item.get("first_ts") or 0)
        last_ts = int(item.get("last_ts") or 0)
        name = _clean_display_name(names.get(wxid))
        if not name:
            name = "我" if wxid and wxid == account else (wxid or "未知用户")
        members.append({
            "wxid": wxid or "real_sender_id:%s" % item.get("real_sender_id"),
            "name": name,
            "message_count": count,
            "share": round(count / total, 4) if total else 0,
            "first_message_at": first_ts,
            "first_message_time": _fmt_time(first_ts),
            "last_message_at": last_ts,
            "last_message_time": _fmt_time(last_ts),
        })
    return {
        "chat_id": chat_id,
        "chat_name": _group_index().get(chat_id, {}).get("name", chat_id),
        "total_messages": total,
        "member_count": len(members),
        "source": "wechat_db",
        "members": members,
    }


def _group_stats(conn: sqlite3.Connection) -> dict[str, dict]:
    if not _table_exists(conn, "messages"):
        return {}
    rows = conn.execute(
        """SELECT chat_id,
                  COUNT(*) AS message_count,
                  COUNT(DISTINCT sender_id) AS active_senders,
                  MIN(timestamp) AS first_ts,
                  MAX(timestamp) AS last_ts
           FROM messages
           GROUP BY chat_id"""
    ).fetchall()
    return {row["chat_id"]: dict(row) for row in rows}


def _refresh_group_cache() -> bool:
    """请求运行中的机器人刷新群/成员缓存（尽力而为）。"""
    try:
        from src.web.server import _bot_control

        backend = _bot_control.get_backend()
        refresh = getattr(backend, "refresh_group_cache", None)
        if callable(refresh):
            refresh(force=True)
            return True
    except Exception as exc:  # noqa: BLE001 - 刷新失败不影响只读查询
        logger.debug("MCP group cache refresh skipped: %s", exc)
    return False


# ── MCP 工具实现 ─────────────────────────────────────────────────────


def list_groups(args: dict) -> dict:
    """列出全部已采集群聊。"""
    limit = _arg_int(args, "limit", 200, 1, 2000)
    refreshed = False
    if _arg_bool(args, "refresh"):
        refreshed = _refresh_group_cache()

    groups = _scoped_groups()
    conn = _db_conn()
    stats: dict[str, dict] = {}
    if conn is not None:
        try:
            stats = _group_stats(conn)
            for chat_id in stats:
                if (
                    chat_id.endswith("@chatroom")
                    and chat_id not in groups
                    and is_chat_allowed(chat_id)
                ):
                    groups[chat_id] = {"name": chat_id, "member_count": 0}
        finally:
            conn.close()

    items = []
    for chat_id, info in groups.items():
        stat = stats.get(chat_id, {})
        member_count = info["member_count"] or int(stat.get("active_senders") or 0)
        first_ts = int(stat.get("first_ts") or 0)
        last_ts = int(stat.get("last_ts") or 0)
        items.append({
            "chat_id": chat_id,
            "name": info["name"],
            "member_count": member_count,
            "message_count": int(stat.get("message_count") or 0),
            "active_sender_count": int(stat.get("active_senders") or 0),
            "first_message_at": first_ts,
            "first_message_time": _fmt_time(first_ts),
            "last_message_at": last_ts,
            "last_message_time": _fmt_time(last_ts),
        })

    items.sort(
        key=lambda item: (
            -(item["last_message_at"] or 0),
            item["name"],
        )
    )
    return {
        "count": len(items),
        "refreshed": refreshed,
        "groups": items[:limit],
    }


def get_group(args: dict) -> dict:
    """查看单个群的基础信息与活跃概况。"""
    chat_id = _resolve_chat(_arg_str(args, "chat"))
    _require_chat_allowed(chat_id)
    groups = _group_index()
    info = groups.get(chat_id, {"name": chat_id, "member_count": 0})
    conn = _db_conn()
    stat: dict = {}
    if conn is not None:
        try:
            if _table_exists(conn, "messages"):
                row = conn.execute(
                    """SELECT COUNT(*) AS message_count,
                              COUNT(DISTINCT sender_id) AS active_senders,
                              MIN(timestamp) AS first_ts,
                              MAX(timestamp) AS last_ts
                       FROM messages WHERE chat_id=?""",
                    (chat_id,),
                ).fetchone()
                stat = dict(row) if row else {}
        finally:
            conn.close()
    return {
        "chat_id": chat_id,
        "name": info["name"],
        "member_count": info["member_count"] or int(stat.get("active_senders") or 0),
        "message_count": int(stat.get("message_count") or 0),
        "active_sender_count": int(stat.get("active_senders") or 0),
        "first_message_at": int(stat.get("first_ts") or 0),
        "first_message_time": _fmt_time(stat.get("first_ts")),
        "last_message_at": int(stat.get("last_ts") or 0),
        "last_message_time": _fmt_time(stat.get("last_ts")),
    }


def list_group_members(args: dict) -> dict:
    """列出群成员（含群内显示名与发言统计）。"""
    chat_id = _resolve_chat(_arg_str(args, "chat"))
    _require_chat_allowed(chat_id)
    limit = _arg_int(args, "limit", 500, 1, 5000)
    groups = _group_index()
    group_name = groups.get(chat_id, {}).get("name", chat_id)
    member_names = _member_index().get(chat_id, {})
    overrides = _nickname_overrides()

    activity: dict[str, dict] = {}
    conn = _db_conn()
    if conn is not None:
        try:
            if _table_exists(conn, "messages"):
                rows = conn.execute(
                    """SELECT sender_id,
                              MAX(sender_name) AS sender_name,
                              COUNT(*) AS message_count,
                              MIN(timestamp) AS first_ts,
                              MAX(timestamp) AS last_ts
                       FROM messages
                       WHERE chat_id=?
                       GROUP BY sender_id""",
                    (chat_id,),
                ).fetchall()
                for row in rows:
                    activity[row["sender_id"]] = dict(row)
        finally:
            conn.close()

    wxids = set(member_names) | set(activity)
    members = []
    for wxid in wxids:
        stat = activity.get(wxid, {})
        display = overrides.get(wxid) or member_names.get(wxid) or str(
            stat.get("sender_name") or wxid
        )
        first_ts = int(stat.get("first_ts") or 0)
        last_ts = int(stat.get("last_ts") or 0)
        members.append({
            "wxid": wxid,
            "name": display,
            "group_nickname": member_names.get(wxid, ""),
            "nickname_override": overrides.get(wxid, ""),
            "in_member_list": wxid in member_names,
            "message_count": int(stat.get("message_count") or 0),
            "first_message_at": first_ts,
            "first_message_time": _fmt_time(first_ts),
            "last_message_at": last_ts,
            "last_message_time": _fmt_time(last_ts),
        })

    members.sort(key=lambda item: (-item["message_count"], item["name"]))
    member_count = groups.get(chat_id, {}).get("member_count") or len(members)
    return {
        "chat_id": chat_id,
        "group_name": group_name,
        "member_count": member_count,
        "returned": len(members[:limit]),
        "members": members[:limit],
    }


def list_friends(args: dict) -> dict:
    """列出好友及私聊互动统计。"""
    limit = _arg_int(args, "limit", 500, 1, 5000)
    account = _friend_index()[0]
    friends = _scoped_friends()

    stats: dict[str, dict] = {}
    conn = _db_conn()
    if conn is not None:
        try:
            if _table_exists(conn, "messages"):
                rows = conn.execute(
                    """SELECT chat_id,
                              COUNT(*) AS message_count,
                              MIN(timestamp) AS first_ts,
                              MAX(timestamp) AS last_ts
                       FROM messages
                       GROUP BY chat_id"""
                ).fetchall()
                for row in rows:
                    stats[row["chat_id"]] = dict(row)
        finally:
            conn.close()

    items = []
    for wxid, info in friends.items():
        stat = stats.get(wxid, {})
        first_ts = int(stat.get("first_ts") or 0)
        last_ts = int(stat.get("last_ts") or 0)
        items.append({
            "wxid": wxid,
            "name": info["name"],
            "alias": info["alias"],
            "message_count": int(stat.get("message_count") or 0),
            "first_message_at": first_ts,
            "first_message_time": _fmt_time(first_ts),
            "last_message_at": last_ts,
            "last_message_time": _fmt_time(last_ts),
        })
    items.sort(key=lambda item: (-item["last_message_at"], item["name"]))
    return {
        "account": account,
        "count": len(items),
        "friends": items[:limit],
    }


def get_messages(args: dict) -> dict:
    """读取指定群聊/好友的消息记录，优先返回微信本地完整历史。"""
    chat_id = _resolve_chat(_arg_str(args, "chat"))
    _require_chat_allowed(chat_id)
    limit = _arg_int(args, "limit", 50, 1, 500)
    offset = _arg_int(args, "offset", 0, 0, 1_000_000)
    order = "asc" if _arg_str(args, "order", "desc").lower() == "asc" else "desc"
    source = _history_source_arg(args)
    include_media = _arg_bool(args, "include_media")

    history_note = ""
    if source in ("auto", "wechat_db"):
        sender_raw = _arg_str(args, "sender")
        sender, sender_ok = _resolve_history_sender(chat_id, sender_raw)
        if sender_raw and not sender_ok:
            history_note = (
                f"发送者「{sender_raw}」无法唯一解析为 wxid，已改用已采集消息库"
            )
        else:
            try:
                rows, has_more = history_source.query_messages(
                    chat_id,
                    limit=limit,
                    offset=offset,
                    order=order,
                    since=parse_time(args.get("since")),
                    until=parse_time(args.get("until"), end_of_day=True),
                    sender=sender,
                    keyword=_arg_str(args, "keyword"),
                )
                filtered = any((
                    sender_raw,
                    _arg_str(args, "keyword"),
                    args.get("since"),
                    args.get("until"),
                ))
                if rows or filtered:
                    return _history_messages_result(
                        chat_id, rows, has_more, limit, offset, include_media
                    )
                # 本地库没有这个会话的历史（例如微信端清空过），
                # 用机器人采集库兜底，避免明明有数据却返回空。
                fallback = _get_messages_from_db(
                    chat_id, args, limit, offset, order
                )
                if fallback.get("count"):
                    fallback["source"] = "messages_db"
                    fallback["note"] = (
                        "微信本地库未找到该会话历史，已回退到已采集消息库 messages.db"
                    )
                    return fallback
                return _history_messages_result(
                    chat_id, rows, has_more, limit, offset, include_media
                )
            except history_source.HistoryUnavailable as exc:
                history_note = str(exc)
        if source == "wechat_db":
            raise ValueError(history_note or "微信本地历史数据源不可用")

    result = _get_messages_from_db(chat_id, args, limit, offset, order)
    result["source"] = "messages_db"
    if history_note:
        result["note"] = f"{history_note}；已回退到已采集消息库 messages.db"
    return result


_MEDIA_KIND_TYPES = {
    "all": {3, 34, 43, 47, 49},
    "image": {3},
    "video": {43},
    "voice": {34},
    "emoji": {47},
    "file": {49},
}


def _media_message_meta(chat_id: str, row: dict) -> dict:
    timestamp = int(row.get("create_time") or 0)
    return {
        "chat_id": chat_id,
        "chat_name": _chat_name_map().get(chat_id, chat_id),
        "local_id": int(row.get("local_id") or 0),
        "shard": str(row.get("shard") or ""),
        "server_id": row.get("server_id"),
        "msg_type": int(row.get("local_type") or 0),
        "msg_type_label": _history_msg_type_label(row.get("local_type")),
        "timestamp": timestamp,
        "time": _fmt_time(timestamp),
    }


def get_message_media(args: dict) -> dict:
    """取单条消息的媒体文件（图片/视频/文件/语音/表情/转发/引用）。"""
    chat_id = _resolve_chat(_arg_str(args, "chat"))
    _require_chat_allowed(chat_id)

    raw_local_id = args.get("local_id")
    try:
        local_id = int(raw_local_id)
    except (TypeError, ValueError):
        raise ValueError(
            "缺少 local_id 参数；可先用 get_messages 获取消息的 local_id 与 shard"
        )
    shard = _arg_str(args, "shard") or None
    kind = (_arg_str(args, "kind", "auto") or "auto").lower()
    inline = _arg_bool(args, "inline")

    db = history_source.get_wechat_db()
    row = db.get_message_row(chat_id, local_id, shard=shard)
    if not row:
        raise ValueError(
            "未找到该消息（local_id=%s, shard=%s）；可先用 get_messages 确认"
            % (local_id, shard or "任意")
        )

    resolver = history_source.get_media_resolver()
    media = resolver.resolve(chat_id, row, kind=kind, inline=inline)
    blocks = media.pop("_content_blocks", None)
    result = _media_message_meta(chat_id, row)
    result["source"] = "wechat_db"
    result["media"] = media
    if blocks:
        result["_content_blocks"] = blocks
    return result


def list_chat_media(args: dict) -> dict:
    """按类型列出会话中的媒体消息，可只查路径或解密落地。"""
    chat_id = _resolve_chat(_arg_str(args, "chat"))
    _require_chat_allowed(chat_id)

    kind = (_arg_str(args, "kind", "all") or "all").lower()
    types = _MEDIA_KIND_TYPES.get(kind)
    if types is None:
        raise ValueError("kind 仅支持 all/image/video/file/voice/emoji")
    limit = _arg_int(args, "limit", 50, 1, 200)
    offset = _arg_int(args, "offset", 0, 0, 1_000_000)
    resolve = _arg_bool(args, "resolve")

    db = history_source.get_wechat_db()
    rows = db.get_media_rows(
        chat_id,
        types,
        since=parse_time(args.get("since")),
        until=parse_time(args.get("until"), end_of_day=True),
        limit=limit + 1,
        offset=offset,
    )
    has_more = len(rows) > limit
    rows = rows[:limit]

    resolver = history_source.get_media_resolver()
    messages = []
    for row in rows:
        item = _media_message_meta(chat_id, row)
        item["media"] = (
            resolver.resolve(chat_id, row) if resolve else resolver.summarize(chat_id, row)
        )
        messages.append(item)
    return {
        "chat_id": chat_id,
        "chat_name": _chat_name_map().get(chat_id, chat_id),
        "kind": kind,
        "count": len(messages),
        "has_more": has_more,
        "source": "wechat_db",
        "limit": limit,
        "offset": offset,
        "messages": messages,
    }


def _get_messages_from_db(
    chat_id: str,
    args: dict,
    limit: int,
    offset: int,
    order: str,
) -> dict:
    """从 messages.db 读取已采集消息（本地历史不可用时的回退路径）。"""
    conn = _db_conn()
    if conn is None:
        return {"chat_id": chat_id, "count": 0, "messages": [], "note": "messages.db 尚未生成"}
    try:
        if not _table_exists(conn, "messages"):
            return {"chat_id": chat_id, "count": 0, "messages": [], "note": "messages 表不存在"}
        where, params = _message_filters(args, chat_id)
        rows = conn.execute(
            f"""SELECT id, message_id, chat_id, sender_id, sender_name,
                       content, msg_type, timestamp
                FROM messages{where}
                ORDER BY timestamp {order}, id {order}
                LIMIT ? OFFSET ?""",
            tuple(params) + (limit + 1, offset),
        ).fetchall()
    finally:
        conn.close()

    has_more = len(rows) > limit
    chat_names = _chat_name_map()
    messages = [
        _row_to_message(row, chat_names) for row in rows[:limit]
    ]
    return {
        "chat_id": chat_id,
        "chat_name": chat_names.get(chat_id, chat_id),
        "count": len(messages),
        "has_more": has_more,
        "messages": messages,
    }


def search_messages(args: dict) -> dict:
    """按关键词搜索消息；指定 chat 时优先检索微信本地完整历史。"""
    keyword = _arg_str(args, "keyword")
    if not keyword:
        raise ValueError("缺少 keyword 参数")
    limit = _arg_int(args, "limit", 50, 1, 200)
    offset = _arg_int(args, "offset", 0, 0, 1_000_000)
    chat_raw = _arg_str(args, "chat")
    chat_id = _resolve_chat(chat_raw) if chat_raw else ""
    if chat_id:
        _require_chat_allowed(chat_id)
    source = _history_source_arg(args)

    history_note = ""
    if source in ("auto", "wechat_db"):
        if not chat_id:
            if source == "wechat_db":
                raise ValueError(
                    "检索完整历史需要指定 chat 参数（跨会话全库扫描开销过大）"
                )
            history_note = "未指定 chat，跨会话检索仅覆盖已采集消息库"
        else:
            sender_raw = _arg_str(args, "sender")
            sender, sender_ok = _resolve_history_sender(chat_id, sender_raw)
            if sender_raw and not sender_ok:
                history_note = (
                    f"发送者「{sender_raw}」无法唯一解析为 wxid，已改用已采集消息库"
                )
            else:
                try:
                    rows, has_more = history_source.query_messages(
                        chat_id,
                        limit=limit,
                        offset=offset,
                        order="desc",
                        since=parse_time(args.get("since")),
                        until=parse_time(args.get("until"), end_of_day=True),
                        sender=sender,
                        keyword=keyword,
                    )
                    if not rows:
                        # 本地库没有命中时用采集库兜底：既能覆盖微信端清空
                        # 历史的会话，也能补上少数压缩文本漏搜的情况。
                        fallback = _search_messages_from_db(
                            args, chat_id, keyword, limit, offset
                        )
                        if fallback.get("count"):
                            fallback["source"] = "messages_db"
                            fallback["note"] = (
                                "微信本地库未找到匹配消息，已回退到已采集消息库 messages.db"
                            )
                            return fallback
                    result = _history_messages_result(
                        chat_id, rows, has_more, limit, offset
                    )
                    result["keyword"] = keyword
                    return result
                except history_source.HistoryUnavailable as exc:
                    history_note = str(exc)
            if source == "wechat_db":
                raise ValueError(history_note or "微信本地历史数据源不可用")

    result = _search_messages_from_db(args, chat_id, keyword, limit, offset)
    result["source"] = "messages_db"
    if history_note:
        result["note"] = f"{history_note}；已回退到已采集消息库 messages.db"
    return result


def _search_messages_from_db(
    args: dict,
    chat_id: str,
    keyword: str,
    limit: int,
    offset: int,
) -> dict:
    """在 messages.db 中搜索已采集消息（回退路径）。"""
    conn = _db_conn()
    if conn is None:
        return {"keyword": keyword, "count": 0, "messages": [], "note": "messages.db 尚未生成"}
    try:
        if not _table_exists(conn, "messages"):
            return {"keyword": keyword, "count": 0, "messages": [], "note": "messages 表不存在"}
        where, params = _message_filters(args, chat_id)
        rows = conn.execute(
            f"""SELECT id, message_id, chat_id, sender_id, sender_name,
                       content, msg_type, timestamp
                FROM messages{where}
                ORDER BY timestamp DESC, id DESC
                LIMIT ? OFFSET ?""",
            tuple(params) + (limit, offset),
        ).fetchall()
    finally:
        conn.close()

    chat_names = _chat_name_map()
    messages = [_row_to_message(row, chat_names) for row in rows]
    return {
        "keyword": keyword,
        "chat_id": chat_id,
        "count": len(messages),
        "messages": messages,
    }


def get_group_activity(args: dict) -> dict:
    """群活跃度报表：消息量、活跃人数、新增发言人数、Top 成员。"""
    since = parse_time(args.get("since")) if args.get("since") else int(time.time()) - 7 * 86400
    until = parse_time(args.get("until"), end_of_day=True) if args.get("until") else int(time.time())
    limit = _arg_int(args, "limit", 50, 1, 500)
    top_members = _arg_int(args, "top_members", 5, 0, 50)
    include_friends = _arg_bool(args, "include_friends")

    conn = _db_conn()
    if conn is None:
        return {"since": since, "until": until, "groups": [], "note": "messages.db 尚未生成"}
    try:
        if not _table_exists(conn, "messages"):
            return {"since": since, "until": until, "groups": [], "note": "messages 表不存在"}

        scope_clause, scope_params = _scope_sql("chat_id")
        chat_filter = ""
        params: list = [since, until]
        if not include_friends:
            chat_filter += " AND chat_id LIKE '%@chatroom'"
        if scope_clause:
            chat_filter += f" AND {scope_clause}"
            params.extend(scope_params)

        group_rows = conn.execute(
            f"""SELECT chat_id,
                       COUNT(*) AS message_count,
                       COUNT(DISTINCT sender_id) AS active_senders,
                       MIN(timestamp) AS first_ts,
                       MAX(timestamp) AS last_ts
                FROM messages
                WHERE timestamp >= ? AND timestamp <= ?{chat_filter}
                GROUP BY chat_id
                ORDER BY message_count DESC""",
            tuple(params),
        ).fetchall()

        sender_rows = conn.execute(
            f"""SELECT chat_id, sender_id,
                       MAX(sender_name) AS sender_name,
                       COUNT(*) AS message_count
                FROM messages
                WHERE timestamp >= ? AND timestamp <= ?{chat_filter}
                GROUP BY chat_id, sender_id""",
            tuple(params),
        ).fetchall()

        scope_clause_m, scope_params_m = _scope_sql("m.chat_id")
        new_filter = ""
        if not include_friends:
            new_filter += " AND m.chat_id LIKE '%@chatroom'"
        if scope_clause_m:
            new_filter += f" AND {scope_clause_m}"
        new_params = [since, until] + scope_params_m + [since]

        new_rows = conn.execute(
            f"""SELECT m.chat_id, COUNT(DISTINCT m.sender_id) AS new_senders
                FROM messages m
                WHERE m.timestamp >= ? AND m.timestamp <= ?{new_filter}
                  AND NOT EXISTS (
                      SELECT 1 FROM messages p
                      WHERE p.chat_id = m.chat_id
                        AND p.sender_id = m.sender_id
                        AND p.timestamp < ?
                  )
                GROUP BY m.chat_id""",
            tuple(new_params),
        ).fetchall()
    finally:
        conn.close()

    new_counts = {row["chat_id"]: int(row["new_senders"] or 0) for row in new_rows}
    senders_by_chat: dict[str, list[dict]] = {}
    for row in sender_rows:
        senders_by_chat.setdefault(row["chat_id"], []).append(dict(row))

    group_names = _scoped_groups()
    items = []
    for row in group_rows[:limit]:
        chat_id = row["chat_id"]
        message_count = int(row["message_count"] or 0)
        senders = sorted(
            senders_by_chat.get(chat_id, []),
            key=lambda item: -int(item["message_count"] or 0),
        )
        members = []
        for sender in senders[:top_members]:
            count = int(sender["message_count"] or 0)
            members.append({
                "wxid": sender["sender_id"],
                "name": sender["sender_name"] or sender["sender_id"],
                "message_count": count,
                "share": round(count / message_count, 4) if message_count else 0,
            })
        first_ts = int(row["first_ts"] or 0)
        last_ts = int(row["last_ts"] or 0)
        info = group_names.get(chat_id, {})
        items.append({
            "chat_id": chat_id,
            "name": info.get("name", chat_id),
            "is_group": chat_id.endswith("@chatroom"),
            "message_count": message_count,
            "active_sender_count": int(row["active_senders"] or 0),
            "new_sender_count": new_counts.get(chat_id, 0),
            "first_message_at": first_ts,
            "first_message_time": _fmt_time(first_ts),
            "last_message_at": last_ts,
            "last_message_time": _fmt_time(last_ts),
            "top_members": members,
        })

    return {
        "since": since,
        "since_time": _fmt_time(since),
        "until": until,
        "until_time": _fmt_time(until),
        "count": len(items),
        "groups": items,
    }


def get_member_activity(args: dict) -> dict:
    """群成员发言排行，优先基于微信本地完整历史统计。"""
    chat_id = _resolve_chat(_arg_str(args, "chat"))
    _require_chat_allowed(chat_id)
    limit = _arg_int(args, "limit", 100, 1, 1000)
    since = parse_time(args.get("since"))
    until = parse_time(args.get("until"), end_of_day=True)
    source = _history_source_arg(args)

    history_note = ""
    native_result = None
    if source in ("auto", "wechat_db"):
        try:
            stats = history_source.sender_stats(
                chat_id, since=since, until=until
            )
            native_result = _history_member_activity(chat_id, stats, limit)
            if stats or since is not None or until is not None:
                return native_result
        except history_source.HistoryUnavailable as exc:
            history_note = str(exc)
            if source == "wechat_db":
                raise ValueError(history_note) from exc

    conn = _db_conn()
    if conn is None:
        result = {"chat_id": chat_id, "members": [], "note": "messages.db 尚未生成"}
        result["source"] = "messages_db"
        return result
    try:
        if not _table_exists(conn, "messages"):
            result = {"chat_id": chat_id, "members": [], "note": "messages 表不存在"}
            result["source"] = "messages_db"
            return result
        clauses = ["chat_id = ?"]
        params: list = [chat_id]
        if since is not None:
            clauses.append("timestamp >= ?")
            params.append(since)
        if until is not None:
            clauses.append("timestamp <= ?")
            params.append(until)
        where = " AND ".join(clauses)
        rows = conn.execute(
            f"""SELECT sender_id,
                       MAX(sender_name) AS sender_name,
                       COUNT(*) AS message_count,
                       MIN(timestamp) AS first_ts,
                       MAX(timestamp) AS last_ts
                FROM messages
                WHERE {where}
                GROUP BY sender_id
                ORDER BY message_count DESC
                LIMIT ?""",
            tuple(params) + (limit,),
        ).fetchall()
        total_row = conn.execute(
            f"SELECT COUNT(*) AS total FROM messages WHERE {where}",
            tuple(params),
        ).fetchone()
    finally:
        conn.close()

    total = int(total_row["total"] or 0) if total_row else 0
    member_names = _member_index().get(chat_id, {})
    overrides = _nickname_overrides()
    groups = _group_index()
    members = []
    for row in rows:
        wxid = row["sender_id"]
        count = int(row["message_count"] or 0)
        first_ts = int(row["first_ts"] or 0)
        last_ts = int(row["last_ts"] or 0)
        members.append({
            "wxid": wxid,
            "name": overrides.get(wxid)
            or member_names.get(wxid)
            or row["sender_name"]
            or wxid,
            "message_count": count,
            "share": round(count / total, 4) if total else 0,
            "first_message_at": first_ts,
            "first_message_time": _fmt_time(first_ts),
            "last_message_at": last_ts,
            "last_message_time": _fmt_time(last_ts),
        })
    result = {
        "chat_id": chat_id,
        "chat_name": groups.get(chat_id, {}).get("name", chat_id),
        "total_messages": total,
        "member_count": len(members),
        "source": "messages_db",
        "members": members,
    }
    if native_result is not None and total == 0:
        # 本地库没有该会话历史，且采集库也没有数据 → 返回本地库的空结果
        return native_result
    if native_result is not None and total:
        result["note"] = (
            "微信本地库未找到该会话历史，已回退到已采集消息库 messages.db"
        )
    elif history_note:
        result["note"] = f"{history_note}；已回退到已采集消息库 messages.db"
    return result


def search_contacts(args: dict) -> dict:
    """按关键词在群聊、好友、群成员中查找联系人。"""
    query = _arg_str(args, "query")
    if not query:
        raise ValueError("缺少 query 参数")
    limit = _arg_int(args, "limit", 30, 1, 200)
    lowered = query.lower()

    groups = _scoped_groups()
    matched_groups = [
        {"chat_id": chat_id, "name": info["name"], "member_count": info["member_count"]}
        for chat_id, info in groups.items()
        if lowered in info["name"].lower() or lowered in chat_id.lower()
    ][:limit]

    account = _friend_index()[0]
    friends = _scoped_friends()
    matched_friends = [
        {"wxid": wxid, "name": info["name"], "alias": info["alias"]}
        for wxid, info in friends.items()
        if lowered in info["name"].lower()
        or lowered in info.get("alias", "").lower()
        or lowered in wxid.lower()
    ][:limit]

    overrides = _nickname_overrides()
    matched_members = []
    for chat_id, names in _member_index().items():
        if not is_chat_allowed(chat_id):
            continue
        for wxid, name in names.items():
            display = overrides.get(wxid) or name
            if lowered in display.lower() or lowered in wxid.lower():
                matched_members.append({
                    "chat_id": chat_id,
                    "group_name": groups.get(chat_id, {}).get("name", chat_id),
                    "wxid": wxid,
                    "name": display,
                })
                if len(matched_members) >= limit:
                    break
        if len(matched_members) >= limit:
            break

    return {
        "query": query,
        "account": account,
        "count": len(matched_groups) + len(matched_friends) + len(matched_members),
        "groups": matched_groups,
        "friends": matched_friends,
        "group_members": matched_members,
    }


def _resolve_contact(raw: str) -> str:
    """把昵称/备注/群内昵称解析为 wxid，必要时回查消息表。"""
    text = str(raw or "").strip()
    if not text:
        raise ValueError("缺少 contact 参数（wxid、昵称或备注）")
    if text.endswith("@chatroom"):
        raise ValueError("contact 需要个人 wxid 或昵称，不能是群 ID")

    friends = _scoped_friends()
    if text in friends:
        return text

    overrides = _nickname_overrides()
    member_index = _member_index()

    exact: list[str] = []
    for wxid, info in friends.items():
        if text in (info["name"], info["alias"]):
            exact.append(wxid)
    for chat_id, names in member_index.items():
        if not is_chat_allowed(chat_id):
            continue
        for wxid, name in names.items():
            if text in (name, overrides.get(wxid, "")) and wxid not in exact:
                exact.append(wxid)
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        raise ValueError("匹配到多个联系人，请改用 wxid: " + ", ".join(exact[:10]))

    fuzzy: list[str] = []
    for wxid, info in friends.items():
        if text in info["name"] or text in info["alias"] or text in wxid:
            fuzzy.append(wxid)
    for chat_id, names in member_index.items():
        if not is_chat_allowed(chat_id):
            continue
        for wxid, name in names.items():
            display = overrides.get(wxid) or name
            if (text in display or text in wxid) and wxid not in fuzzy:
                fuzzy.append(wxid)
    if len(fuzzy) == 1:
        return fuzzy[0]
    if len(fuzzy) > 1:
        raise ValueError("匹配到多个联系人，请改用 wxid: " + ", ".join(fuzzy[:10]))

    # 缓存里没有：回查消息表的发送者昵称
    conn = _db_conn()
    if conn is not None:
        try:
            if _table_exists(conn, "messages"):
                scope_clause, scope_params = _scope_sql("chat_id")
                scope_and = f" AND {scope_clause}" if scope_clause else ""
                rows = conn.execute(
                    f"""SELECT sender_id FROM messages
                       WHERE sender_name = ?{scope_and}
                       GROUP BY sender_id
                       ORDER BY COUNT(*) DESC
                       LIMIT 2""",
                    (text, *scope_params),
                ).fetchall()
                if len(rows) == 1:
                    return str(rows[0]["sender_id"])
                if len(rows) > 1:
                    raise ValueError(
                        "匹配到多个联系人，请改用 wxid: "
                        + ", ".join(str(row["sender_id"]) for row in rows)
                    )
        finally:
            conn.close()
    return text


def find_new_senders(args: dict) -> dict:
    """找出时间窗内首次发言的新联系人，用于新成员追踪与周报。"""
    since = parse_time(args.get("since")) if args.get("since") else int(time.time()) - 7 * 86400
    until = parse_time(args.get("until"), end_of_day=True) if args.get("until") else int(time.time())
    limit = _arg_int(args, "limit", 100, 1, 500)
    min_messages = _arg_int(args, "min_messages", 1, 1, 10000)
    include_friends = _arg_bool(args, "include_friends")
    chat_raw = _arg_str(args, "chat")
    chat_id = _resolve_chat(chat_raw) if chat_raw else ""
    if chat_id:
        _require_chat_allowed(chat_id)
    account, _ = _friend_index()

    conn = _db_conn()
    if conn is None:
        return {
            "since": since, "since_time": _fmt_time(since),
            "until": until, "until_time": _fmt_time(until),
            "count": 0, "new_senders": [], "note": "messages.db 尚未生成",
        }
    try:
        if not _table_exists(conn, "messages"):
            return {
                "since": since, "since_time": _fmt_time(since),
                "until": until, "until_time": _fmt_time(until),
                "count": 0, "new_senders": [], "note": "messages 表不存在",
            }

        conditions = ["m.timestamp >= ?", "m.timestamp <= ?"]
        params: list = [since, until]
        if chat_id:
            conditions.append("m.chat_id = ?")
            params.append(chat_id)
        elif not include_friends:
            conditions.append("m.chat_id LIKE '%@chatroom'")
        if account:
            conditions.append("m.sender_id != ?")
            params.append(account)
        scope_clause, scope_params = _scope_sql("m.chat_id")
        if scope_clause:
            conditions.append(scope_clause)
            params.extend(scope_params)
        conditions.append(
            "NOT EXISTS (SELECT 1 FROM messages p WHERE p.chat_id = m.chat_id "
            "AND p.sender_id = m.sender_id AND p.timestamp < ?)"
        )
        params.append(since)
        where = " AND ".join(conditions)

        rows = conn.execute(
            f"""SELECT m.chat_id,
                       m.sender_id,
                       MAX(m.sender_name) AS sender_name,
                       COUNT(*) AS message_count,
                       MIN(m.timestamp) AS first_ts,
                       MAX(m.timestamp) AS last_ts,
                       (SELECT p.content FROM messages p
                         WHERE p.chat_id = m.chat_id AND p.sender_id = m.sender_id
                         ORDER BY p.timestamp ASC, p.id ASC LIMIT 1) AS first_content
                FROM messages m
                WHERE {where}
                GROUP BY m.chat_id, m.sender_id
                HAVING COUNT(*) >= ?
                ORDER BY first_ts DESC
                LIMIT ?""",
            tuple(params) + (min_messages, limit),
        ).fetchall()
    finally:
        conn.close()

    groups = _group_index()
    member_index = _member_index()
    overrides = _nickname_overrides()
    items = []
    for row in rows:
        row_chat_id = str(row["chat_id"])
        wxid = str(row["sender_id"])
        display = (
            overrides.get(wxid)
            or member_index.get(row_chat_id, {}).get(wxid)
            or row["sender_name"]
            or wxid
        )
        first_ts = int(row["first_ts"] or 0)
        last_ts = int(row["last_ts"] or 0)
        content, truncated = _truncate_content(row["first_content"], 300)
        items.append({
            "chat_id": row_chat_id,
            "chat_name": groups.get(row_chat_id, {}).get("name", row_chat_id),
            "is_group": row_chat_id.endswith("@chatroom"),
            "wxid": wxid,
            "name": display,
            "message_count": int(row["message_count"] or 0),
            "first_message": content,
            "first_message_truncated": truncated,
            "first_message_at": first_ts,
            "first_message_time": _fmt_time(first_ts),
            "last_message_at": last_ts,
            "last_message_time": _fmt_time(last_ts),
        })

    return {
        "since": since,
        "since_time": _fmt_time(since),
        "until": until,
        "until_time": _fmt_time(until),
        "count": len(items),
        "new_senders": items,
    }


def get_contact_profile(args: dict) -> dict:
    """聚合单个联系人的画像：好友信息、所在群、发言统计与最近消息。"""
    contact = _arg_str(args, "contact")
    if not contact:
        raise ValueError("缺少 contact 参数（wxid、昵称或备注）")
    recent_limit = _arg_int(args, "recent_limit", 20, 0, 100)
    wxid = _resolve_contact(contact)

    account, _ = _friend_index()
    friend = _scoped_friends().get(wxid)
    groups = _scoped_groups()
    member_index = _member_index()
    overrides = _nickname_overrides()
    chat_names = _chat_name_map()

    cached_groups = {
        chat_id: names[wxid]
        for chat_id, names in member_index.items()
        if wxid in names and is_chat_allowed(chat_id)
    }

    scope_clause, scope_params = _scope_sql("chat_id")
    scope_and = f" AND {scope_clause}" if scope_clause else ""

    chat_rows: list[dict] = []
    recent_messages: list[dict] = []
    total_count = 0
    first_ts = last_ts = 0
    latest_sender_name = ""

    conn = _db_conn()
    if conn is not None:
        try:
            if _table_exists(conn, "messages"):
                chat_rows = [
                    dict(row) for row in conn.execute(
                        f"""SELECT chat_id,
                                  MAX(sender_name) AS sender_name,
                                  COUNT(*) AS message_count,
                                  MIN(timestamp) AS first_ts,
                                  MAX(timestamp) AS last_ts
                           FROM messages
                           WHERE sender_id = ?{scope_and}
                           GROUP BY chat_id
                           ORDER BY message_count DESC""",
                        (wxid, *scope_params),
                    ).fetchall()
                ]
                totals = conn.execute(
                    f"""SELECT COUNT(*) AS total,
                              MIN(timestamp) AS first_ts,
                              MAX(timestamp) AS last_ts
                       FROM messages WHERE sender_id = ?{scope_and}""",
                    (wxid, *scope_params),
                ).fetchone()
                if totals:
                    total_count = int(totals["total"] or 0)
                    first_ts = int(totals["first_ts"] or 0)
                    last_ts = int(totals["last_ts"] or 0)
                if recent_limit:
                    recent_rows = conn.execute(
                        f"""SELECT id, message_id, chat_id, sender_id, sender_name,
                                  content, msg_type, timestamp
                           FROM messages WHERE sender_id = ?{scope_and}
                           ORDER BY timestamp DESC, id DESC
                           LIMIT ?""",
                        (wxid, *scope_params, recent_limit),
                    ).fetchall()
                    recent_messages = [
                        _row_to_message(row, chat_names) for row in recent_rows
                    ]
                    if recent_messages:
                        latest_sender_name = str(
                            recent_messages[0].get("sender_name") or ""
                        )
        finally:
            conn.close()

    if not latest_sender_name:
        latest_sender_name = next(
            (str(row.get("sender_name") or "") for row in chat_rows if row.get("sender_name")),
            "",
        )

    group_items = []
    seen_groups: set[str] = set()
    for row in chat_rows:
        chat_id = str(row["chat_id"])
        if not chat_id.endswith("@chatroom"):
            continue
        seen_groups.add(chat_id)
        count = int(row["message_count"] or 0)
        row_first = int(row["first_ts"] or 0)
        row_last = int(row["last_ts"] or 0)
        group_items.append({
            "chat_id": chat_id,
            "name": groups.get(chat_id, {}).get("name", chat_id),
            "group_nickname": cached_groups.get(chat_id, ""),
            "in_member_list": chat_id in cached_groups,
            "message_count": count,
            "first_message_at": row_first,
            "first_message_time": _fmt_time(row_first),
            "last_message_at": row_last,
            "last_message_time": _fmt_time(row_last),
        })
    for chat_id, group_nickname in cached_groups.items():
        if chat_id in seen_groups:
            continue
        group_items.append({
            "chat_id": chat_id,
            "name": groups.get(chat_id, {}).get("name", chat_id),
            "group_nickname": group_nickname,
            "in_member_list": True,
            "message_count": 0,
            "first_message_at": 0,
            "first_message_time": "",
            "last_message_at": 0,
            "last_message_time": "",
        })
    group_items.sort(key=lambda item: (-item["message_count"], item["name"]))

    private_items = []
    for row in chat_rows:
        chat_id = str(row["chat_id"])
        if chat_id.endswith("@chatroom"):
            continue
        count = int(row["message_count"] or 0)
        row_first = int(row["first_ts"] or 0)
        row_last = int(row["last_ts"] or 0)
        private_items.append({
            "chat_id": chat_id,
            "chat_name": chat_names.get(chat_id, chat_id),
            "message_count": count,
            "first_message_at": row_first,
            "first_message_time": _fmt_time(row_first),
            "last_message_at": row_last,
            "last_message_time": _fmt_time(row_last),
        })

    display = (
        overrides.get(wxid)
        or (friend or {}).get("name")
        or next((name for name in cached_groups.values() if name), "")
        or latest_sender_name
        or wxid
    )
    return {
        "wxid": wxid,
        "name": display,
        "alias": (friend or {}).get("alias", ""),
        "is_friend": friend is not None,
        "is_self": bool(account) and wxid == account,
        "found": bool(friend or chat_rows or cached_groups),
        "group_count": len(group_items),
        "group_message_count": sum(item["message_count"] for item in group_items),
        "private_message_count": sum(item["message_count"] for item in private_items),
        "total_message_count": total_count,
        "first_message_at": first_ts,
        "first_message_time": _fmt_time(first_ts),
        "last_message_at": last_ts,
        "last_message_time": _fmt_time(last_ts),
        "groups": group_items,
        "private_chats": private_items,
        "recent_messages": recent_messages,
    }


def get_data_overview(args: dict) -> dict:
    """数据总览：帮助外部智能体快速了解可用数据范围。"""
    account = _friend_index()[0]
    friends = _scoped_friends()
    groups = _scoped_groups()
    scope = get_scope()
    overview = {
        "account": account,
        "group_count": len(groups),
        "friend_count": len(friends),
        "scope": scope,
        "message_count": 0,
        "sender_count": 0,
        "first_message_at": 0,
        "first_message_time": "",
        "last_message_at": 0,
        "last_message_time": "",
        "recent_7d_messages": 0,
        "active_groups_7d": 0,
        "data_dir": str(webot_data_path()),
        "messages_db": str(_messages_db_path()),
        "db_updated_at": 0,
        "db_updated_time": "",
        "db_size_bytes": 0,
        "history_source": history_source.status(),
    }

    db_path = _messages_db_path()
    try:
        if db_path.exists():
            stat = db_path.stat()
            overview["db_updated_at"] = int(stat.st_mtime)
            overview["db_updated_time"] = _fmt_time(stat.st_mtime)
            overview["db_size_bytes"] = int(stat.st_size)
    except OSError:
        pass

    conn = _db_conn()
    if conn is None:
        overview["note"] = "messages.db 尚未生成，机器人尚未采集过消息"
        return overview
    try:
        if not _table_exists(conn, "messages"):
            overview["note"] = "messages 表不存在"
            return overview
        scope_clause, scope_params = _scope_sql("chat_id")
        scope_and = f" AND {scope_clause}" if scope_clause else ""
        row = conn.execute(
            f"""SELECT COUNT(*) AS message_count,
                      COUNT(DISTINCT sender_id) AS sender_count,
                      MIN(timestamp) AS first_ts,
                      MAX(timestamp) AS last_ts
               FROM messages WHERE 1=1{scope_and}""",
            tuple(scope_params),
        ).fetchone()
        if row:
            overview["message_count"] = int(row["message_count"] or 0)
            overview["sender_count"] = int(row["sender_count"] or 0)
            overview["first_message_at"] = int(row["first_ts"] or 0)
            overview["first_message_time"] = _fmt_time(row["first_ts"])
            overview["last_message_at"] = int(row["last_ts"] or 0)
            overview["last_message_time"] = _fmt_time(row["last_ts"])

        week_ago = int(time.time()) - 7 * 86400
        recent = conn.execute(
            f"""SELECT COUNT(*) AS message_count,
                      COUNT(DISTINCT chat_id) AS active_chats
               FROM messages WHERE timestamp >= ?{scope_and}""",
            (week_ago, *scope_params),
        ).fetchone()
        if recent:
            overview["recent_7d_messages"] = int(recent["message_count"] or 0)
            overview["active_groups_7d"] = int(recent["active_chats"] or 0)
    finally:
        conn.close()
    return overview


TOOL_FUNCTIONS = {
    "list_groups": list_groups,
    "get_group": get_group,
    "list_group_members": list_group_members,
    "list_friends": list_friends,
    "get_messages": get_messages,
    "get_message_media": get_message_media,
    "list_chat_media": list_chat_media,
    "search_messages": search_messages,
    "get_group_activity": get_group_activity,
    "get_member_activity": get_member_activity,
    "search_contacts": search_contacts,
    "find_new_senders": find_new_senders,
    "get_contact_profile": get_contact_profile,
    "get_data_overview": get_data_overview,
}
