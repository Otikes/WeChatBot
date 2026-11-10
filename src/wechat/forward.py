# -*- coding: utf-8 -*-
"""微信 appmsg 结构化解析：合并转发（type=19）与引用回复（type=57）。

消息正文是 XML，合并转发的真正内容在 ``<recorditem><![CDATA[...]]></recorditem>``
里，需要先取 CDATA 再二次解析。所有函数解析失败时返回 ``None``，不抛异常。
"""

from __future__ import annotations

import html
import re
from typing import Optional

_RECORD_RE = re.compile(
    r"<recorditem>\s*(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?\s*</recorditem>",
    re.S | re.I,
)
_REFER_RE = re.compile(r"<refermsg>(.*?)</refermsg>", re.S | re.I)
_APPMSG_TYPE_RE = re.compile(r"<appmsg>.*?<type>\s*(\d+)\s*</type>", re.S | re.I)
_DATAITEM_RE = re.compile(r"<dataitem\b([^>]*)>(.*?)</dataitem>", re.S | re.I)

_DATATYPE_NAMES = {
    1: "text",
    2: "image",
    3: "image",
    4: "video",
    5: "link",
    6: "file",
    8: "emoji",
    17: "file",
}


def _unescape(text: str) -> str:
    return html.unescape(text or "").strip()


def _tag_text(xml: str, name: str) -> str:
    match = re.search(
        r"<%s\b[^>]*>(.*?)</%s>" % (re.escape(name), re.escape(name)),
        xml or "",
        re.S | re.I,
    )
    if not match:
        return ""
    value = match.group(1).strip()
    cdata = re.match(r"<!\[CDATA\[(.*?)\]\]>", value, re.S)
    if cdata:
        value = cdata.group(1)
    return _unescape(value)


def appmsg_type(content: str) -> Optional[int]:
    """读取 ``<appmsg><type>``；不是 appmsg 时返回 None。"""
    match = _APPMSG_TYPE_RE.search(content or "")
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def parse_forward(content: str) -> Optional[dict]:
    """解析合并转发记录，返回 ``{title, desc, count, items}``。"""
    outer = _RECORD_RE.search(content or "")
    if not outer:
        return None
    inner = outer.group(1).strip()
    if not inner:
        return None

    info = _tag_text(inner, "info") or _tag_text(content, "title")
    title = _tag_text(inner, "title") or _tag_text(content, "title") or info
    count_text = ""
    count_match = re.search(r"<datalist\b[^>]*\bcount\s*=\s*[\"']?(\d+)", inner, re.I)
    if count_match:
        count_text = count_match.group(1)

    items: list[dict] = []
    for attr_text, body in _DATAITEM_RE.findall(inner):
        datatype_match = re.search(r"datatype\s*=\s*[\"']?(\d+)", attr_text or "", re.I)
        datatype = int(datatype_match.group(1)) if datatype_match else 0
        size_text = _tag_text(body, "datasize")
        try:
            size = int(size_text) if size_text else 0
        except ValueError:
            size = 0
        item = {
            "datatype": datatype,
            "type": _DATATYPE_NAMES.get(datatype, "unknown"),
            "text": _tag_text(body, "datadesc") or _tag_text(body, "title"),
            "md5": _tag_text(body, "fullmd5") or _tag_text(body, "md5"),
            "size": size,
            "fmt": _tag_text(body, "datafmt"),
            "duration": _tag_text(body, "duration"),
            "sender": _tag_text(body, "sourcename"),
            "time": _tag_text(body, "sourcetime"),
        }
        items.append(item)

    try:
        count = int(count_text) if count_text else len(items)
    except ValueError:
        count = len(items)
    return {"title": title, "desc": info, "count": count, "items": items}


def parse_reference(content: str) -> Optional[dict]:
    """解析引用回复，返回 ``{title, display_name, content, chatusr}``。"""
    match = _REFER_RE.search(content or "")
    if not match:
        return None
    refer = match.group(1)
    title = _tag_text(content, "title")
    return {
        "title": title,
        "display_name": _tag_text(refer, "displayname"),
        "content": _tag_text(refer, "content"),
        "chatusr": _tag_text(refer, "chatusr") or _tag_text(refer, "fromusr"),
    }
