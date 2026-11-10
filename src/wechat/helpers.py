"""Shared utilities for WeChat backends.

These reduce duplication across WeChat backend implementations.
"""

import hashlib
import html
import logging
from pathlib import PurePath
import re
from typing import Any
import xml.etree.ElementTree as ET

from src.wechat.forward import appmsg_type, parse_forward, parse_reference

logger = logging.getLogger(__name__)

# ── Message type mapping ──────────────────────────────────────────

# WeChat localType -> standard integer codes
MSG_TYPE_MAP: dict[str | int, int] = {
    "text": 1,
    "friend": 1,      # wxauto uses 'friend' for some text messages
    "image": 3,
    "img": 3,
    "图片": 3,
    "voice": 34,
    "语音": 34,
    "video": 43,
    "视频": 43,
    "emoji": 47,
    "表情": 47,
    "app_share": 49,   # links, mini-programs
    "app": 49,
    "file": 49,
    "文件": 49,
    "link": 49,
    "链接": 49,
    "system": 10000,
    "系统": 10000,
    # Also support integer keys for lookup
    1: 1,
    3: 3,
    34: 34,
    47: 47,
    49: 49,
    43: 43,
    10000: 10000,
}

# Non-text → human-readable placeholder
_NONTEXT_PLACEHOLDERS: dict[str, str] = {
    "image": "[图片]",
    "voice": "[语音]",
    "emoji": "[表情]",
    "video": "[视频]",
    "file": "[文件]",
    "app_share": "[链接]",
}

# 硬编码反向映射（避免每次调用时重建，且消除 str→int 多对一的歧义）
_REVERSE_MSG_TYPE: dict[int, str] = {
    1: "text", 3: "image", 34: "voice", 47: "emoji",
    43: "video", 49: "file", 10000: "system",
}

_FILE_EXT_LABELS: dict[str, str] = {
    "pdf": "PDF",
    "ppt": "PPT",
    "pptx": "PPT",
    "doc": "Word",
    "docx": "Word",
    "xls": "Excel",
    "xlsx": "Excel",
    "csv": "CSV",
    "txt": "文本",
    "zip": "压缩包",
    "rar": "压缩包",
    "7z": "压缩包",
}


def normalize_msg_type(raw_type: Any) -> int:
    """Convert a backend-specific message type to our standard integer code.

    Handles both string keys ("text", "image", ...) and raw integer codes.
    Unknown types default to 1 (text).
    """
    if raw_type is None:
        return 1
    if isinstance(raw_type, int):
        return MSG_TYPE_MAP.get(raw_type, raw_type)
    if isinstance(raw_type, str):
        label = raw_type.strip().lower()
        if label.isdigit():
            numeric = int(label)
            return MSG_TYPE_MAP.get(numeric, numeric)
        return MSG_TYPE_MAP.get(label, 1)
    return 1


def format_nontext_content(raw_type: Any, raw_content: str = "") -> str:
    """Return a human-readable summary for non-text message types.

    Examples: image → "[图片]", voice → "[语音]", video → "[视频]"
    """
    msg_type = normalize_msg_type(raw_type)
    content = str(raw_content or "").strip()

    # Preserve already-normalized placeholders.
    if content.startswith("[") and content.endswith("]") and len(content) <= 40:
        return content

    if msg_type == 3:
        return _format_media_placeholder("图片", content)
    if msg_type == 47:
        return _format_media_placeholder("表情", content)
    if msg_type == 43:
        return _format_media_placeholder("视频", content)
    if msg_type == 49:
        return _format_app_message(content)
    if msg_type == 34:
        return _NONTEXT_PLACEHOLDERS["voice"]
    if msg_type == 10000:
        return content or "[系统消息]"
    if isinstance(raw_type, str) and raw_type.strip():
        return f"[{raw_type.strip()}]"
    if isinstance(raw_type, int):
        key = _REVERSE_MSG_TYPE.get(msg_type, "")
        return _NONTEXT_PLACEHOLDERS.get(key, f"[消息类型:{msg_type}]")
    return "[未知消息]"


def _format_media_placeholder(label: str, raw_content: str) -> str:
    root = _parse_wechat_xml(raw_content)
    size = ""
    if root is not None:
        for tag in ("img", "emoji", "videomsg"):
            elem = root.find(f".//{tag}")
            if elem is None and root.tag == tag:
                elem = root
            if elem is None:
                continue
            size = _format_size(
                elem.attrib.get("length")
                or elem.attrib.get("len")
                or elem.attrib.get("cdnthumblength")
                or elem.attrib.get("playlength")
            )
            if size:
                break
    return f"[{label} {size}]" if size else f"[{label}]"


def _format_app_message(raw_content: str) -> str:
    root = _parse_wechat_xml(raw_content)
    if root is None:
        return _format_plain_app_content(raw_content)

    kind = appmsg_type(raw_content)
    if kind == 19:
        data = parse_forward(raw_content)
        if not data:
            return "[合并转发]"
        title = str(data.get("title") or "").strip()
        count = data.get("count") or len(data.get("items") or [])
        return f"[合并转发: {title} ({count}条)]" if title else f"[合并转发 ({count}条)]"
    if kind == 57:
        data = parse_reference(raw_content) or {}
        title = str(data.get("title") or "").strip()
        return f"[引用: {title}]" if title else "[引用]"

    title = _first_xml_text(root, ("title", "filename", "fileName"))
    desc = _first_xml_text(root, ("des", "description"))
    file_ext = _first_xml_text(root, ("fileext", "fileExt"))
    if not file_ext and title:
        suffix = PurePath(title).suffix
        file_ext = suffix[1:] if suffix.startswith(".") else suffix
    file_ext = file_ext.lower().strip(".")
    size = _first_xml_text(root, ("totallen", "totalLen", "filesize", "fileSize"))
    size_text = _format_size(size)

    if file_ext or _has_element(root, "appattach"):
        kind = _FILE_EXT_LABELS.get(file_ext, file_ext.upper() if file_ext else "文件")
        title = _file_display_name(title)
        details = ", ".join(part for part in (kind, size_text) if part)
        if title and details:
            return f"[文件: {title} ({details})]"
        if title:
            return f"[文件: {title}]"
        if details:
            return f"[文件 ({details})]"
        return "[文件]"

    if title and desc:
        return f"[链接: {title} - {desc}]"
    if title:
        return f"[链接: {title}]"
    return "[消息]"


def _format_plain_app_content(raw_content: str) -> str:
    text = str(raw_content or "").strip()
    if not text:
        return "[文件]"

    text = re.sub(r"[\r\n\t]+", " ", text).strip()
    if re.match(r"^[a-z][a-z0-9+.-]*://", text, re.IGNORECASE):
        return "[链接]"

    title = _file_display_name(text)
    file_ext = PurePath(title).suffix.lower().lstrip(".")
    if file_ext:
        kind = _FILE_EXT_LABELS.get(file_ext, file_ext.upper())
        return f"[文件: {title} ({kind})]"
    return "[消息]"


def _file_display_name(title: str) -> str:
    text = str(title or "").strip().strip('"').strip("'")
    if not text:
        return ""
    return PurePath(text).name or text[:80]


def _parse_wechat_xml(raw_content: str) -> ET.Element | None:
    payload = _extract_xml_payload(raw_content)
    if not payload:
        return None
    try:
        return ET.fromstring(payload)
    except ET.ParseError:
        return None


def _extract_xml_payload(raw_content: str) -> str:
    text = html.unescape(str(raw_content or "")).strip()
    if "<" not in text:
        return ""
    match = re.search(r"<(?:msg|appmsg|img|emoji|videomsg)\b", text)
    if match:
        text = text[match.start():]
    return text


def _first_xml_text(root: ET.Element, names: tuple[str, ...]) -> str:
    for name in names:
        elem = root.find(f".//{name}")
        if elem is None and root.tag == name:
            elem = root
        if elem is not None and elem.text:
            value = elem.text.strip()
            if value:
                return value
    return ""


def _has_element(root: ET.Element, name: str) -> bool:
    return root.tag == name or root.find(f".//{name}") is not None


def _format_size(raw_size: Any) -> str:
    try:
        size = int(str(raw_size or "").strip())
    except (TypeError, ValueError):
        return ""
    if size <= 0:
        return ""
    units = ("B", "KB", "MB", "GB")
    value = float(size)
    unit = units[0]
    for unit in units:
        if value < 1024 or unit == units[-1]:
            break
        value /= 1024
    if unit == "B":
        return f"{int(value)} {unit}"
    return f"{value:.1f} {unit}"


def generate_message_id(*fields: Any) -> str:
    """Generate a stable, deterministic message ID from one or more fields.

    Each field's string representation is joined with '|' and hashed via MD5.
    """
    raw = "|".join(str(f) for f in fields)
    return hashlib.md5(raw.encode()).hexdigest()


# ── Dedup set ─────────────────────────────────────────────────────

class DedupSet:
    """A size-bounded set for message deduplication.

    Automatically trims to keep the most recent entries when the set
    grows beyond *max_size*. This prevents unbounded memory growth
    in long-running bots.

    Usage:
        seen = DedupSet(max_size=5000)
        if msg_id in seen:
            continue
        seen.add(msg_id)
    """

    def __init__(self, max_size: int = 5000):
        self._max_size = max_size
        self._data: set[str] = set()
        self._insertion_order: list[str] = []

    def __contains__(self, item: str) -> bool:
        return item in self._data

    def add(self, item: str) -> None:
        """Add an item to the set, trimming if necessary."""
        self._data.add(item)
        self._insertion_order.append(item)
        self._trim()

    def _trim(self) -> None:
        """If the set exceeds max_size, keep only the most recent half."""
        if len(self._data) > self._max_size:
            keep = self._max_size // 2
            discard = self._insertion_order[:-keep]
            self._insertion_order = self._insertion_order[-keep:]
            for item in discard:
                self._data.discard(item)
            logger.debug(
                "DedupSet trimmed: %d → %d items",
                len(self._data) + len(discard), len(self._data),
            )

    def __len__(self) -> int:
        return len(self._data)
