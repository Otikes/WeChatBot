"""MCP 协议与 HTTP 传输实现。

支持的传输方式：
- Streamable HTTP：``POST /mcp``（JSON-RPC 2.0，返回 application/json）
- 兼容旧版 HTTP+SSE：``GET /mcp/sse`` + ``POST /mcp/messages?session_id=...``

鉴权（任一方式）：
- ``Authorization: Bearer <MCP_API_KEY>``
- ``X-API-Key: <MCP_API_KEY>``
- ``?key=<MCP_API_KEY>``（仅用于无法自定义请求头的旧版 SSE 客户端）
"""

from __future__ import annotations

import hmac
import json
import logging
import os
import queue
import secrets
import threading
import time
import uuid
from urllib.parse import parse_qs, urlparse

from src.config import PROJECT_ROOT, find_env_file
from src.mcp_server.data import (
    MCP_FRIENDS_ENV,
    MCP_GROUPS_ENV,
    TOOL_FUNCTIONS,
    get_scope,
    scope_options,
)

logger = logging.getLogger(__name__)

MCP_SERVER_NAME = "webot-mcp"
MCP_SERVER_VERSION = "1.0.0"

SUPPORTED_PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
DEFAULT_PROTOCOL_VERSION = "2025-06-18"
MAX_BODY_BYTES = 4 * 1024 * 1024
MAX_BATCH_ITEMS = 20
MAX_SSE_SESSIONS = 20
AUTH_FAILURE_LIMIT = 20
AUTH_FAILURE_WINDOW = 60.0

MCP_ENABLED_ENV = "MCP_ENABLED"
MCP_API_KEY_ENV = "MCP_API_KEY"
MCP_ALLOWED_HOSTS_ENV = "MCP_ALLOWED_HOSTS"

DEFAULT_ALLOWED_HOSTS = {"127.0.0.1", "localhost", "::1"}

READ_ONLY_ANNOTATIONS = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": False,
}


# ── 工具定义 ─────────────────────────────────────────────────────────

def _object(properties: dict | None = None, required: list[str] | None = None) -> dict:
    schema: dict = {
        "type": "object",
        "properties": properties or {},
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    return schema


_TIME_PROPS = {
    "since": {
        "type": "string",
        "description": "起始时间：unix 秒、YYYY-MM-DD[ HH:MM[:SS]]、7d/24h/today 等",
    },
    "until": {
        "type": "string",
        "description": "结束时间：unix 秒、YYYY-MM-DD[ HH:MM[:SS]]、now 等",
    },
}

_SOURCE_PROP = {
    "source": {
        "type": "string",
        "enum": ["auto", "wechat_db", "messages_db"],
        "default": "auto",
        "description": (
            "数据源：auto=优先微信本地完整历史，不可用时回退已采集消息库；"
            "wechat_db=只用完整历史（不可用则报错）；"
            "messages_db=只用已采集消息库"
        ),
    },
}

TOOLS: list[dict] = [
    {
        "name": "get_data_overview",
        "description": (
            "数据总览。返回当前微信账号、群聊数、好友数、已采集消息数、"
            "最早/最新消息时间、近 7 天消息量与活跃会话数，以及微信本地"
            "完整历史数据源的可用状态。建议在分析前先调用。"
        ),
        "inputSchema": _object(),
    },
    {
        "name": "list_groups",
        "description": (
            "列出机器人已采集的微信群聊，返回群 ID、群名、成员数、消息数、"
            "活跃人数、最近消息时间。可按最近活跃时间排序。"
        ),
        "inputSchema": _object({
            "refresh": {
                "type": "boolean",
                "description": "是否先从微信数据库刷新群列表（需机器人正在运行）",
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 2000,
                "default": 200,
                "description": "最多返回多少个群",
            },
        }),
    },
    {
        "name": "get_group",
        "description": "查看单个群聊的详细信息：群名、成员数、消息量、活跃人数、首末消息时间。",
        "inputSchema": _object({
            "chat": {
                "type": "string",
                "description": "群 ID（xxx@chatroom）或群名",
            },
        }, ["chat"]),
    },
    {
        "name": "list_group_members",
        "description": (
            "列出群成员及群内显示名，并附带每位成员的发言数、"
            "首次/最近发言时间，可用于识别群内活跃用户。"
        ),
        "inputSchema": _object({
            "chat": {
                "type": "string",
                "description": "群 ID（xxx@chatroom）或群名",
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 5000,
                "default": 500,
                "description": "最多返回多少位成员",
            },
        }, ["chat"]),
    },
    {
        "name": "list_friends",
        "description": (
            "列出微信好友（wxid、昵称、备注/别名），并附带私聊消息数与"
            "最近互动时间，可用于好友/客户盘点。"
        ),
        "inputSchema": _object({
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 5000,
                "default": 500,
                "description": "最多返回多少个好友",
            },
        }),
    },
    {
        "name": "get_messages",
        "description": (
            "读取指定群聊或好友的消息记录，支持时间范围、发送者、关键词过滤与分页。"
            "默认优先读取微信本地数据库的完整历史（不仅限于机器人采集的最近消息），"
            "本地库不可用时自动回退到已采集消息库，返回的 source 字段标明实际数据源。"
        ),
        "inputSchema": _object({
            "chat": {
                "type": "string",
                "description": "群 ID、群名、好友 wxid 或好友昵称",
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 500,
                "default": 50,
                "description": "每页条数",
            },
            "offset": {
                "type": "integer",
                "minimum": 0,
                "default": 0,
                "description": "分页偏移，可反复翻页读取全部历史",
            },
            "order": {
                "type": "string",
                "enum": ["desc", "asc"],
                "default": "desc",
                "description": "按时间倒序（desc）或正序（asc）",
            },
            "sender": {
                "type": "string",
                "description": "按发送者 wxid 精确匹配或昵称精确匹配",
            },
            "keyword": {
                "type": "string",
                "description": "消息内容关键词",
            },
            "include_media": {
                "type": "boolean",
                "default": False,
                "description": (
                    "是否为非文本消息附带媒体摘要（图片/视频/语音/表情/文件等，"
                    "只返回存在性与路径，不解密、不内联）"
                ),
            },
            **_TIME_PROPS,
            **_SOURCE_PROP,
        }, ["chat"]),
    },
    {
        "name": "get_message_media",
        "description": (
            "获取单条消息的媒体内容：图片/视频/文件/语音/表情包/合并转发/引用回复。"
            "返回本地文件路径与元数据（类型、大小、尺寸、时长等），图片会解密并缓存到 "
            "data/media_cache。inline=true 时对图片额外返回 base64 内容块，可直接查看。"
            "需先通过 get_messages(include_media=true) 或 list_chat_media 获取 local_id。"
        ),
        "inputSchema": _object({
            "chat": {
                "type": "string",
                "description": "群 ID、群名、好友 wxid 或好友昵称",
            },
            "local_id": {
                "type": "integer",
                "description": "消息的 local_id（由 get_messages / list_chat_media 返回）",
            },
            "shard": {
                "type": "string",
                "description": "可选：消息所在分片（get_messages 返回的 shard）",
            },
            "kind": {
                "type": "string",
                "enum": [
                    "auto", "image", "video", "file", "voice",
                    "emoji", "forward", "reference",
                ],
                "default": "auto",
                "description": "媒体类型；auto 按消息类型自动判断",
            },
            "inline": {
                "type": "boolean",
                "default": False,
                "description": "图片是否内联返回（base64 内容块，≤2MB）",
            },
        }, ["chat", "local_id"]),
    },
    {
        "name": "list_chat_media",
        "description": (
            "按类型列出会话中的媒体消息（图片/视频/文件/语音/表情包），"
            "返回每条消息的 local_id、时间、是否存在本地文件与路径。"
            "resolve=false（默认）只查存在性；resolve=true 时解密图片、下载表情并返回路径。"
        ),
        "inputSchema": _object({
            "chat": {
                "type": "string",
                "description": "群 ID、群名、好友 wxid 或好友昵称",
            },
            "kind": {
                "type": "string",
                "enum": ["all", "image", "video", "file", "voice", "emoji"],
                "default": "all",
                "description": "媒体类型",
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 200,
                "default": 50,
                "description": "每页条数",
            },
            "offset": {
                "type": "integer",
                "minimum": 0,
                "default": 0,
                "description": "分页偏移",
            },
            "resolve": {
                "type": "boolean",
                "default": False,
                "description": "是否解密/下载并把文件落到 data/media_cache",
            },
            **_TIME_PROPS,
        }, ["chat"]),
    },
    {
        "name": "search_messages",
        "description": (
            "按关键词搜索消息。指定 chat 时默认检索该会话的微信本地完整历史；"
            "不指定 chat 时仅在已采集消息库中跨会话搜索。"
            "适合查找产品咨询、报价、联系方式等线索，也可用于整理周报素材。"
        ),
        "inputSchema": _object({
            "keyword": {
                "type": "string",
                "description": "搜索关键词",
            },
            "chat": {
                "type": "string",
                "description": "可选：限定群 ID、群名、好友 wxid 或昵称（指定后可检索完整历史）",
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 200,
                "default": 50,
                "description": "最多返回多少条",
            },
            "offset": {
                "type": "integer",
                "minimum": 0,
                "default": 0,
                "description": "分页偏移",
            },
            "sender": {
                "type": "string",
                "description": "可选：按发送者过滤",
            },
            **_TIME_PROPS,
            **_SOURCE_PROP,
        }, ["keyword"]),
    },
    {
        "name": "get_group_activity",
        "description": (
            "群活跃度报表（运营分析工具）。按时间范围统计每个群的消息量、"
            "活跃发言人数、首次发言的新成员数，以及发言最多的 Top 成员，"
            "可用于周报、群活跃度复盘。统计基于机器人已采集消息库；"
            "单群的完整历史活跃排行请用 get_member_activity。"
        ),
        "inputSchema": _object({
            "since": {
                "type": "string",
                "description": "统计起始时间，默认 7 天前（支持 7d/24h/today 或日期）",
            },
            "until": {
                "type": "string",
                "description": "统计结束时间，默认当前时间",
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 500,
                "default": 50,
                "description": "最多返回多少个群",
            },
            "top_members": {
                "type": "integer",
                "minimum": 0,
                "maximum": 50,
                "default": 5,
                "description": "每个群返回的 Top 成员数",
            },
            "include_friends": {
                "type": "boolean",
                "description": "是否把好友私聊也纳入统计（默认只统计群聊）",
            },
        }),
    },
    {
        "name": "get_member_activity",
        "description": (
            "群成员发言排行。默认基于微信本地完整历史统计，返回每位成员的"
            "消息数、发言占比、首次/最近发言时间，可按时间范围过滤，"
            "用于识别活跃成员和周报统计。"
        ),
        "inputSchema": _object({
            "chat": {
                "type": "string",
                "description": "群 ID 或群名",
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 1000,
                "default": 100,
                "description": "最多返回多少位成员",
            },
            **_TIME_PROPS,
            **_SOURCE_PROP,
        }, ["chat"]),
    },
    {
        "name": "search_contacts",
        "description": (
            "按关键词在群聊、好友、群成员中查找联系人，返回群名、成员所在群、"
            "wxid 与显示名，便于把线索关联到具体的人。"
        ),
        "inputSchema": _object({
            "query": {
                "type": "string",
                "description": "姓名、昵称、备注、群名或 wxid 的一部分",
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 200,
                "default": 30,
                "description": "每类结果最多返回多少条",
            },
        }, ["query"]),
    },
    {
        "name": "find_new_senders",
        "description": (
            "找出时间范围内首次发言的新联系人（新成员追踪工具）。"
            "返回所在群 ID/群名、wxid、昵称、首条消息内容、发言数与首末发言时间，"
            "可用于周报、群运营与新成员跟进，可按群过滤或包含好友私聊。"
            "统计基于机器人已采集消息库。"
        ),
        "inputSchema": _object({
            "chat": {
                "type": "string",
                "description": "可选：只看某个群 ID 或群名",
            },
            "since": {
                "type": "string",
                "description": "起始时间，默认 7 天前（支持 7d/24h/today 或日期）",
            },
            "until": {
                "type": "string",
                "description": "结束时间，默认当前时间",
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 500,
                "default": 100,
                "description": "最多返回多少位新联系人",
            },
            "min_messages": {
                "type": "integer",
                "minimum": 1,
                "maximum": 1000,
                "default": 1,
                "description": "至少有这么多条发言才算（用于过滤偶发噪音）",
            },
            "include_friends": {
                "type": "boolean",
                "description": "是否包含好友私聊（默认只统计群聊）",
            },
        }),
    },
    {
        "name": "get_contact_profile",
        "description": (
            "查询单个联系人的完整画像（联系人分析工具）。聚合好友信息、"
            "所在群聊、跨群发言统计、私聊消息数与最近消息，"
            "可用于客户跟进、成员背调与周报素材整理；"
            "可输入 wxid、昵称、备注或群内昵称。发言统计基于机器人已采集消息库。"
        ),
        "inputSchema": _object({
            "contact": {
                "type": "string",
                "description": "wxid、昵称、备注或群内昵称",
            },
            "recent_limit": {
                "type": "integer",
                "minimum": 0,
                "maximum": 100,
                "default": 20,
                "description": "返回最近消息条数（0 表示不返回）",
            },
        }, ["contact"]),
    },

    # ── 系统群发分组 + 消息发送（写操作） ────────────────────────────
    {
        "name": "list_broadcast_groups",
        "description": (
            "列出控制台「系统配置 → 群发分组」里用户自定义的所有分组。"
            "每个分组可同时包含好友和群聊。发送前先调用它确认分组名和目标，"
            "再配合 batch_send_messages 的 group 参数按分组发送。"
            "注意：这是系统自己的分组，与微信自带的通讯录标签无关。"
            "受 MCP 数据范围限制，不在范围内的目标会被隐藏（hidden_count）。"
        ),
        "inputSchema": _object({
            "name": {
                "type": "string",
                "description": "可选：按名称模糊筛选分组",
            },
        }),
    },
    {
        "name": "send_message",
        "description": (
            "向单个好友或群聊发送一条文本消息（写操作）。"
            "chat 可填群 ID（xxx@chatroom）、群名、好友 wxid、昵称或备注；"
            "不确定目标时先用 search_contacts 查询。"
            "前置条件：机器人已启动、微信已登录且窗口可见；受 MCP 数据范围约束。"
            "建议先用 dry_run=true 预览解析结果，确认无误后再真正发送。"
        ),
        "inputSchema": _object({
            "chat": {
                "type": "string",
                "description": "群 ID / 群名 / 好友 wxid / 昵称 / 备注",
            },
            "content": {
                "type": "string",
                "description": f"消息正文，最长 {2000} 个字符",
            },
            "dry_run": {
                "type": "boolean",
                "default": False,
                "description": "true=只解析和校验、不实际发送，用于预览",
            },
        }, ["chat", "content"]),
        "annotations": {
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    },
    {
        "name": "batch_send_messages",
        "description": (
            "批量向多个好友/群聊发送同一条文本消息（写操作，串行发送）。"
            "三种用法：① chats 传入目标数组；② group 传群发分组名"
            "（先调 list_broadcast_groups 获取）；③ 两者同时传，自动合并去重。"
            "返回每个目标的逐条结果。前置条件：机器人已启动、微信窗口可见；"
            "受 MCP 数据范围约束；单次最多 50 个目标，默认每条间隔 800ms。"
            "强烈建议先 dry_run=true 预览，确认目标清单后再真正发送。"
        ),
        "inputSchema": _object({
            "content": {
                "type": "string",
                "description": f"消息正文，最长 {2000} 个字符",
            },
            "chats": {
                "type": "array",
                "items": {"type": "string"},
                "description": "目标数组：群 ID / 群名 / 好友 wxid / 昵称",
            },
            "group": {
                "type": "string",
                "description": "系统内群发分组名（与 chats 可同时使用，会合并去重）",
            },
            "interval_ms": {
                "type": "integer",
                "minimum": 0,
                "maximum": 5000,
                "default": 800,
                "description": "每条之间的间隔毫秒数，默认 800",
            },
            "dry_run": {
                "type": "boolean",
                "default": False,
                "description": "true=只解析和校验、不实际发送，用于预览目标清单",
            },
        }, ["content"]),
        "annotations": {
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": False,
            "openWorldHint": True,
        },
    },
    {
        "name": "list_wechat_labels",
        "description": (
            "只读列出微信自带的通讯录标签及各标签下的好友（wxid 与昵称）。"
            "底层动态探测微信本地 contact.db 的关联表，不同微信版本结构可能不同；"
            "读不到时 available=false 并给出 note，此时标签成员为空。"
            "注意：这是微信原生标签的只读视图，与系统群发分组完全独立，"
            "不会导入、不会影响群发分组。"
        ),
        "inputSchema": _object(),
    },
]

for _tool in TOOLS:
    _tool.setdefault("annotations", dict(READ_ONLY_ANNOTATIONS))


# ── 配置读写 ─────────────────────────────────────────────────────────

def _env_path():
    return find_env_file() or (PROJECT_ROOT / ".env")


_env_lock = threading.RLock()


def _write_env_updates(updates: dict[str, str]) -> None:
    """原子写入 .env 并同步当前进程环境变量。"""
    with _env_lock:
        path = _env_path()
        lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        new_lines: list[str] = []
        seen: set[str] = set()
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key = stripped.split("=", 1)[0].strip()
                if key in updates:
                    new_lines.append(f"{key}={updates[key]}")
                    seen.add(key)
                    continue
            new_lines.append(line)
        for key, value in updates.items():
            if key not in seen:
                new_lines.append(f"{key}={value}")
        tmp = path.with_suffix(".tmp")
        tmp.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        os.replace(tmp, path)
        for key, value in updates.items():
            os.environ[key] = value


def get_settings() -> dict:
    """读取 MCP 开关、密钥与数据范围（默认启用、默认全部可访问）。"""
    raw_enabled = os.getenv(MCP_ENABLED_ENV, "").strip().lower()
    enabled = raw_enabled not in ("0", "false", "no", "off") if raw_enabled else True
    return {
        "enabled": enabled,
        "api_key": os.getenv(MCP_API_KEY_ENV, "").strip(),
        "scope": get_scope(),
    }


def ensure_api_key() -> str:
    """返回现有密钥；不存在时生成并写入 .env。"""
    current = os.getenv(MCP_API_KEY_ENV, "").strip()
    if current:
        return current
    key = "webot_" + secrets.token_urlsafe(32)
    _write_env_updates({MCP_API_KEY_ENV: key})
    logger.info("Generated a new MCP API key")
    return key


def _normalize_scope(value: str) -> str:
    """规范化数据范围：* = 全部，none = 不允许，其余为 URL 编码的逗号列表。"""
    text = str(value or "").strip()
    if not text or text == "*":
        return "*"
    if text.lower() in ("none", "-"):
        return "none"
    items: list[str] = []
    for part in text.split(","):
        part = part.strip()
        if part and part not in items:
            items.append(part)
    return ",".join(items) if items else "none"


def update_settings(*, enabled: bool | None = None,
                    api_key: str | None = None,
                    regenerate: bool = False,
                    groups: str | None = None,
                    friends: str | None = None) -> dict:
    """更新 MCP 开关/密钥/数据范围，返回最新配置。"""
    updates: dict[str, str] = {}
    if enabled is not None:
        updates[MCP_ENABLED_ENV] = "true" if enabled else "false"
    if regenerate:
        updates[MCP_API_KEY_ENV] = "webot_" + secrets.token_urlsafe(32)
    elif api_key is not None:
        cleaned = str(api_key).strip()
        if len(cleaned) < 8:
            raise ValueError("API Key 至少需要 8 个字符")
        updates[MCP_API_KEY_ENV] = cleaned
    if groups is not None:
        updates[MCP_GROUPS_ENV] = _normalize_scope(groups)
    if friends is not None:
        updates[MCP_FRIENDS_ENV] = _normalize_scope(friends)
    if updates:
        _write_env_updates(updates)
        if MCP_API_KEY_ENV in updates:
            # 轮换后清空失败计数，避免合法用户被此前的爆破记录误伤
            with _auth_lock:
                _auth_failures.clear()
            logger.info("MCP API key rotated")
        if MCP_ENABLED_ENV in updates:
            logger.info("MCP server enabled=%s", updates[MCP_ENABLED_ENV])
    return get_settings()


def _mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 10:
        return key[:2] + "****"
    return f"{key[:6]}...{key[-4:]}"


def describe_server(base_url: str | None = None) -> dict:
    """供控制台展示的连接信息与工具清单。"""
    settings = get_settings()
    key = settings["api_key"]
    if settings["enabled"] and not key:
        key = ensure_api_key()
    base = (base_url or "http://127.0.0.1:7327").rstrip("/")
    return {
        "ok": True,
        "enabled": settings["enabled"],
        "server": {"name": MCP_SERVER_NAME, "version": MCP_SERVER_VERSION},
        "endpoint": f"{base}/mcp",
        "sse_endpoint": f"{base}/mcp/sse",
        "api_key": key,
        "api_key_masked": _mask_key(key),
        "allowed_hosts": sorted(_allowed_hosts()),
        "auth_headers": [
            "Authorization: Bearer <API_KEY>",
            "X-API-Key: <API_KEY>",
        ],
        "protocol_versions": list(SUPPORTED_PROTOCOL_VERSIONS),
        "tools": [
            {
                "name": tool["name"],
                "description": tool["description"],
                "input_schema": tool["inputSchema"],
            }
            for tool in TOOLS
        ],
        "scope": settings["scope"],
        "scope_options": scope_options(),
    }


# ── Host / Origin 校验（防 DNS rebinding 与跨站读取） ─────────────────


def _hostname(value: str) -> str:
    """从 Host / Origin 值中取出主机名（去掉端口与 IPv6 方括号）。"""
    text = str(value or "").strip().lower()
    if not text:
        return ""
    if "://" in text:
        text = urlparse(text).netloc
    if text.startswith("["):
        end = text.find("]")
        return text[1:end] if end > 0 else text
    if text.count(":") == 1:
        return text.split(":", 1)[0]
    return text


def _allowed_hosts() -> set[str]:
    """可信主机名：默认仅回环地址，可用 MCP_ALLOWED_HOSTS 追加（tunnel/反代域名）。"""
    hosts = set(DEFAULT_ALLOWED_HOSTS)
    for item in os.getenv(MCP_ALLOWED_HOSTS_ENV, "").split(","):
        host = _hostname(item)
        if host:
            hosts.add(host)
    return hosts


def _is_trusted_host(value: str) -> bool:
    host = _hostname(value)
    return bool(host) and host in _allowed_hosts()


def is_trusted_origin(value: str) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return True  # 非浏览器客户端通常不带 Origin
    if text == "null":
        return False  # sandbox iframe / file:// 一律拒绝
    parsed = urlparse(text)
    if parsed.scheme not in ("http", "https"):
        return False
    return _is_trusted_host(parsed.netloc)


def is_trusted_request(handler) -> bool:
    """Host 必须是可信主机；带 Origin 时也必须是可信来源。"""
    headers = getattr(handler, "headers", None) or {}
    return (
        _is_trusted_host(headers.get("Host", ""))
        and is_trusted_origin(headers.get("Origin", ""))
    )


# ── 鉴权 ─────────────────────────────────────────────────────────────


def _request_api_key(headers, query: dict | None = None) -> str:
    auth = str(headers.get("Authorization", "") or "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    for name in ("X-API-Key", "x-api-key", "Api-Key", "api-key"):
        value = headers.get(name)
        if value:
            return str(value).strip()
    if query:
        for name in ("key", "api_key"):
            values = query.get(name)
            if values:
                return str(values[0]).strip()
    return ""


def verify_api_key(headers, query: dict | None = None) -> bool:
    """校验请求携带的 API Key（常量时间比较）。"""
    expected = get_settings()["api_key"]
    if not expected:
        return False
    provided = _request_api_key(headers, query)
    if not provided:
        return False
    try:
        return hmac.compare_digest(provided, expected)
    except TypeError:
        return False


def _auth_failure_reason(headers, query: dict | None = None) -> str:
    settings = get_settings()
    if not settings["api_key"]:
        return "MCP_API_KEY 未配置，请在 Web 控制台「MCP 服务」中生成密钥"
    if not _request_api_key(headers, query):
        return "缺少 API Key：请使用 Authorization: Bearer <key> 或 X-API-Key: <key>"
    return "API Key 无效"


def _client_ip(handler) -> str:
    try:
        return str(handler.client_address[0])
    except (AttributeError, IndexError, TypeError):
        return "unknown"


_auth_failures: dict[str, list[float]] = {}
_auth_lock = threading.Lock()


def _auth_blocked(ip: str) -> bool:
    """同一来源在窗口期内失败次数过多则暂时拒绝（防暴力猜解）。"""
    now = time.monotonic()
    with _auth_lock:
        recent = [t for t in _auth_failures.get(ip, []) if now - t < AUTH_FAILURE_WINDOW]
        if recent:
            _auth_failures[ip] = recent
        else:
            _auth_failures.pop(ip, None)
        return len(recent) >= AUTH_FAILURE_LIMIT


def _record_auth_failure(ip: str) -> None:
    now = time.monotonic()
    with _auth_lock:
        _auth_failures.setdefault(ip, []).append(now)
        if len(_auth_failures) > 512:
            cutoff = now - AUTH_FAILURE_WINDOW
            for key in [
                key for key, stamps in _auth_failures.items()
                if not stamps or stamps[-1] < cutoff
            ]:
                _auth_failures.pop(key, None)


def _clear_auth_failures(ip: str) -> None:
    with _auth_lock:
        _auth_failures.pop(ip, None)


# ── JSON-RPC 2.0 ─────────────────────────────────────────────────────


def _rpc_result(request_id, result) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _rpc_error(request_id, code: int, message: str, data=None) -> dict:
    error: dict = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}


def _tool_result(data, *, is_error: bool = False) -> dict:
    # 工具可在返回体里附带 _content_blocks（例如内联图片），单独取出后
    # 追加到 content 列表，避免污染 structuredContent。
    blocks = None
    if isinstance(data, dict):
        blocks = data.pop("_content_blocks", None)
    text = json.dumps(data, ensure_ascii=False, indent=2)
    result = {
        "content": [{"type": "text", "text": text}],
        "isError": is_error,
    }
    if blocks:
        result["content"].extend(blocks)
    if isinstance(data, dict):
        result["structuredContent"] = data
    else:
        result["structuredContent"] = {"result": data}
    return result


def _call_tool(name: str, arguments: dict) -> dict:
    if not name:
        raise ValueError("tools/call 缺少 name 参数")
    func = TOOL_FUNCTIONS.get(name)
    if func is None:
        raise KeyError(f"未知工具: {name}")
    return func(arguments or {})


def _handle_single(request) -> dict | None:
    if not isinstance(request, dict):
        return _rpc_error(None, -32600, "Invalid Request")

    is_notification = "id" not in request
    request_id = request.get("id")
    method = request.get("method")
    params = request.get("params") or {}

    if not isinstance(method, str):
        return None if is_notification else _rpc_error(request_id, -32600, "Invalid Request")

    if method in ("notifications/initialized", "notifications/cancelled"):
        return None
    if method == "notifications/progress":
        return None

    if method == "initialize":
        requested = str(params.get("protocolVersion") or "")
        version = (
            requested if requested in SUPPORTED_PROTOCOL_VERSIONS
            else DEFAULT_PROTOCOL_VERSION
        )
        return _rpc_result(request_id, {
            "protocolVersion": version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": MCP_SERVER_NAME, "version": MCP_SERVER_VERSION},
            "instructions": (
                "WeChatBot MCP：提供微信群聊、群成员、好友与消息数据，以及消息发送能力。"
                "只要 WeChatBot 控制台进程在运行，无需启动机器人即可查询数据。"
                "get_messages / search_messages（指定 chat 时）/ get_member_activity "
                "默认读取微信本地数据库的完整历史（要求微信已登录；不可用时自动"
                "回退到机器人采集的 messages.db，并在返回的 source/note 中说明）。"
                "建议先调用 get_data_overview 了解数据范围与 history_source 状态，再用 "
                "list_groups / list_group_members / list_friends 分析群聊与联系人，"
                "用 find_new_senders 追踪新成员、get_contact_profile 查看联系人画像，"
                "用 get_group_activity / get_member_activity 做活跃度统计，也可用于周报汇总。"
                "媒体消息：get_messages(include_media=true) 可为图片/视频/文件/语音/"
                "表情/转发/引用附加媒体摘要；list_chat_media 按类型批量列出，"
                "get_message_media 用 local_id 取单个媒体（图片解密缓存到 data/media_cache，"
                "inline=true 可直接返回图片内容）。"
                "发送消息：先用 search_contacts 确认目标，再用 send_message 单发；"
                "批量发送先用 list_broadcast_groups 查看系统群发分组，再用 "
                "batch_send_messages 传 group 分组名或 chats 目标数组。"
                "发送属于写操作，要求机器人已启动且微信窗口可见，务必先 dry_run=true "
                "预览目标清单、向用户确认后再真正发送，不要擅自群发。"
                "list_wechat_labels 只读查看微信自带通讯录标签，与系统群发分组无关。"
            ),
        })

    if method == "ping":
        return _rpc_result(request_id, {})
    if method == "tools/list":
        return _rpc_result(request_id, {"tools": TOOLS})
    if method == "resources/list":
        return _rpc_result(request_id, {"resources": []})
    if method == "prompts/list":
        return _rpc_result(request_id, {"prompts": []})
    if method == "logging/setLevel":
        return _rpc_result(request_id, {})

    if method == "tools/call":
        if is_notification:
            return None
        name = str(params.get("name") or "").strip()
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            return _rpc_error(request_id, -32602, "arguments 必须是对象")
        try:
            data = _call_tool(name, arguments)
        except KeyError as exc:
            return _rpc_error(request_id, -32602, str(exc))
        except ValueError as exc:
            return _rpc_result(request_id, _tool_result(
                {"error": str(exc)}, is_error=True,
            ))
        except Exception as exc:  # noqa: BLE001 - 工具异常以 isError 返回
            logger.exception("MCP tool %s failed", name)
            return _rpc_result(request_id, _tool_result(
                {"error": f"{type(exc).__name__}: {exc}"}, is_error=True,
            ))
        return _rpc_result(request_id, _tool_result(data))

    if is_notification:
        return None
    return _rpc_error(request_id, -32601, f"Method not found: {method}")


def handle_rpc(payload):
    """处理单条或批量 JSON-RPC 请求；通知类请求返回 None。"""
    if isinstance(payload, list):
        if not payload:
            return _rpc_error(None, -32600, "Invalid Request: empty batch")
        if len(payload) > MAX_BATCH_ITEMS:
            return _rpc_error(
                None, -32600,
                f"Invalid Request: 批量请求最多 {MAX_BATCH_ITEMS} 条",
            )
        responses = [
            response for response in (_handle_single(item) for item in payload)
            if response is not None
        ]
        return responses or None
    return _handle_single(payload)


def _audit_tool_calls(handler, payload) -> None:
    """审计日志：只记录工具名与来源 IP，不记录参数与消息内容。"""
    entries = payload if isinstance(payload, list) else [payload]
    ip = _client_ip(handler)
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("method") != "tools/call":
            continue
        params = entry.get("params") or {}
        name = str(params.get("name") or "<missing>")
        logger.info("MCP tools/call %s from %s", name, ip)


# ── HTTP 传输 ────────────────────────────────────────────────────────


def _cors_origin(handler) -> str:
    """仅对可信 Origin 回显 CORS 头，避免任意网页读取本机接口。"""
    headers = getattr(handler, "headers", None) or {}
    origin = str(headers.get("Origin", "") or "").strip()
    return origin if origin and is_trusted_origin(origin) else ""


def _send_json(handler, status: int, body: dict | list, *,
               extra_headers: dict | None = None) -> None:
    raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(raw)))
    handler.send_header("Cache-Control", "no-store")
    for key, value in (extra_headers or {}).items():
        handler.send_header(key, value)
    origin = _cors_origin(handler)
    if origin:
        handler.send_header("Access-Control-Allow-Origin", origin)
        handler.send_header("Vary", "Origin")
        handler.send_header("Access-Control-Expose-Headers", "Mcp-Session-Id")
    handler.end_headers()
    handler.wfile.write(raw)


def _send_empty(handler, status: int) -> None:
    handler.send_response(status)
    handler.send_header("Content-Length", "0")
    origin = _cors_origin(handler)
    if origin:
        handler.send_header("Access-Control-Allow-Origin", origin)
        handler.send_header("Vary", "Origin")
    handler.end_headers()


def _read_body(handler) -> bytes:
    try:
        length = int(handler.headers.get("Content-Length", 0) or 0)
    except (TypeError, ValueError):
        length = 0
    if length <= 0:
        return b""
    if length > MAX_BODY_BYTES:
        raise ValueError("请求体过大")
    return handler.rfile.read(length)


def _check_access(handler, query: dict | None = None, *,
                  allow_query_key: bool = True) -> bool:
    """校验来源、开关与密钥；未通过时直接写响应并返回 False。"""
    if not is_trusted_request(handler):
        _send_json(handler, 403, {
            "ok": False,
            "error": "拒绝访问：Host/Origin 不受信任",
            "hint": "默认只允许本机访问；如使用隧道或反向代理，请配置 MCP_ALLOWED_HOSTS",
        })
        return False
    if not get_settings()["enabled"]:
        _send_json(handler, 403, {
            "ok": False,
            "error": "MCP 服务未启用",
            "hint": "请在 Web 控制台「MCP 服务」中开启",
        })
        return False
    ip = _client_ip(handler)
    if _auth_blocked(ip):
        _send_json(handler, 429, {
            "ok": False,
            "error": "鉴权失败次数过多，请稍后重试",
        }, extra_headers={"Retry-After": str(int(AUTH_FAILURE_WINDOW))})
        return False
    if not verify_api_key(handler.headers, query if allow_query_key else None):
        _record_auth_failure(ip)
        _send_json(handler, 401, {
            "ok": False,
            "error": _auth_failure_reason(
                handler.headers, query if allow_query_key else None,
            ),
        })
        return False
    _clear_auth_failures(ip)
    return True


def _handle_streamable(handler) -> None:
    if handler.command != "POST":
        _send_json(handler, 405, {
            "ok": False,
            "error": "请使用 POST /mcp（Streamable HTTP）；旧版客户端可用 GET /mcp/sse",
        })
        return
    if not _check_access(handler, allow_query_key=False):
        return
    try:
        raw = _read_body(handler)
    except ValueError as exc:
        _send_json(handler, 413, {"ok": False, "error": str(exc)})
        return
    try:
        payload = json.loads(raw.decode("utf-8") if raw else "null")
    except (UnicodeDecodeError, json.JSONDecodeError):
        _send_json(handler, 400, _rpc_error(None, -32700, "Parse error"))
        return
    if payload is None:
        _send_json(handler, 400, _rpc_error(None, -32600, "Invalid Request"))
        return
    _audit_tool_calls(handler, payload)
    try:
        response = handle_rpc(payload)
    except Exception as exc:  # noqa: BLE001
        logger.exception("MCP request failed")
        _send_json(handler, 500, _rpc_error(None, -32603, f"Internal error: {exc}"))
        return
    if response is None:
        _send_empty(handler, 202)
    else:
        _send_json(handler, 200, response)


# ── 旧版 HTTP+SSE（兼容 Trae / Claude 等老客户端） ───────────────────

_sse_sessions: dict[str, queue.Queue] = {}
_sse_lock = threading.Lock()


def _sse_write(handler, event: str, data: str) -> None:
    handler.wfile.write(
        f"event: {event}\ndata: {data}\n\n".encode("utf-8")
    )
    handler.wfile.flush()


def _handle_sse(handler) -> None:
    if handler.command != "GET":
        _send_json(handler, 405, {"ok": False, "error": "请使用 GET /mcp/sse"})
        return
    if not _check_access(handler):
        return

    session_id = uuid.uuid4().hex
    session_queue: queue.Queue = queue.Queue(maxsize=200)
    with _sse_lock:
        if len(_sse_sessions) >= MAX_SSE_SESSIONS:
            too_many = True
        else:
            too_many = False
            _sse_sessions[session_id] = session_queue
    if too_many:
        _send_json(handler, 429, {
            "ok": False,
            "error": f"SSE 连接数已达上限（{MAX_SSE_SESSIONS}），请关闭闲置客户端后重试",
        })
        return

    try:
        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
        handler.send_header("Cache-Control", "no-cache, no-transform")
        handler.send_header("Connection", "keep-alive")
        handler.send_header("X-Accel-Buffering", "no")
        origin = _cors_origin(handler)
        if origin:
            handler.send_header("Access-Control-Allow-Origin", origin)
            handler.send_header("Vary", "Origin")
        handler.end_headers()
        _sse_write(
            handler,
            "endpoint",
            f"/mcp/messages?session_id={session_id}",
        )
        while True:
            try:
                message = session_queue.get(timeout=15)
            except queue.Empty:
                handler.wfile.write(b": ping\n\n")
                handler.wfile.flush()
                continue
            _sse_write(handler, "message", json.dumps(message, ensure_ascii=False))
    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
        pass
    except Exception:  # noqa: BLE001
        logger.debug("MCP SSE stream closed", exc_info=True)
    finally:
        with _sse_lock:
            _sse_sessions.pop(session_id, None)
        handler.close_connection = True


def _handle_sse_message(handler, parsed) -> None:
    if handler.command != "POST":
        _send_json(handler, 405, {"ok": False, "error": "请使用 POST /mcp/messages"})
        return
    query = parse_qs(parsed.query)
    session_id = str((query.get("session_id") or [""])[0]).strip()
    if not session_id:
        _send_json(handler, 400, {"ok": False, "error": "缺少 session_id"})
        return
    if not _check_access(handler, query):
        return
    with _sse_lock:
        session_queue = _sse_sessions.get(session_id)
    if session_queue is None:
        _send_json(handler, 404, {
            "ok": False,
            "error": "SSE 会话不存在或已断开，请重新连接 /mcp/sse",
        })
        return
    try:
        raw = _read_body(handler)
        payload = json.loads(raw.decode("utf-8") if raw else "null")
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        _send_json(handler, 400, _rpc_error(None, -32700, "Parse error"))
        return

    _audit_tool_calls(handler, payload)
    try:
        response = handle_rpc(payload)
    except Exception as exc:  # noqa: BLE001
        logger.exception("MCP SSE request failed")
        response = _rpc_error(None, -32603, f"Internal error: {exc}")
    if response is not None:
        try:
            session_queue.put_nowait(response)
        except queue.Full:
            logger.warning("MCP SSE queue full; dropping response")
    _send_empty(handler, 202)


def handle_http(handler) -> bool:
    """在 WeChatBot 的 HTTP 服务中处理 MCP 请求；命中时返回 True。"""
    parsed = urlparse(handler.path)
    path = parsed.path.rstrip("/") or "/"
    if path == "/mcp":
        _handle_streamable(handler)
        return True
    if path == "/mcp/sse":
        _handle_sse(handler)
        return True
    if path == "/mcp/messages":
        _handle_sse_message(handler, parsed)
        return True
    return False
