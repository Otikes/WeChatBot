# -*- coding: utf-8 -*-
"""微信媒体定位与落地。

把消息行（``WeChatDB.get_message_row`` 返回的原始字段）解析成可用的本地文件：

- 图片：``msg/attach/<md5(chat)>/<YYYY-MM>/Img/<id>*.dat``，按变体解密后缓存；
- 视频：``msg/video/<YYYY-MM>/<id>.mp4``；
- 文件：``msg/file/<YYYY-MM>/<原文件名>``；
- 语音：``msg/voice/<server_id>/`` 或 ``media_*.db.VoiceInfo.voice_data``；
- 表情：消息 XML / ``emoticon.db`` 取 ``aeskey`` 与 CDN 地址，下载并解密；
- 合并转发 / 引用：交给 ``src.wechat.forward`` 解析。

所有方法都不抛异常：单项失败写入 ``errors``，同时尽量返回原始路径。
"""

from __future__ import annotations

import base64
import hashlib
import html
import json
import logging
import mimetypes
import os
import re
import urllib.request
from datetime import datetime
from pathlib import Path, PurePath
from typing import Any, Optional

from src.config import webot_data_path
from src.voice.file_locator import VoiceFileLocator
from src.wechat import dat2img
from src.wechat.forward import appmsg_type, parse_forward, parse_reference
from src.wechat.wxdb_reader import WeChatDB

logger = logging.getLogger(__name__)

IMAGE_MIME = {
    "jpg": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "webp": "image/webp",
    "bmp": "image/bmp",
    "wxgf": "image/wxgf",
}

_MAX_INLINE_BYTES = 2 * 1024 * 1024
_INLINE_IMAGE_MIMES = {
    "image/jpeg", "image/png", "image/gif", "image/webp", "image/bmp",
}
_MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024
_HEX32_RE = re.compile(rb"[0-9a-fA-F]{32}")
_MD5_ATTR_RE = re.compile(r'(?:md5|fullmd5|externmd5)="([0-9a-fA-F]{32})"', re.I)


def _hex_id(value: Any) -> str:
    if isinstance(value, bytes):
        match = _HEX32_RE.search(value)
        return match.group(0).decode("ascii").lower() if match else ""
    if isinstance(value, str):
        match = re.search(r"[0-9a-fA-F]{32}", value)
        return match.group(0).lower() if match else ""
    return ""


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
    return html.unescape(value).strip()


def _tag_attrs(xml: str, name: str) -> dict:
    match = re.search(r"<%s\b([^>]*)>" % re.escape(name), xml or "", re.I)
    if not match:
        return {}
    attrs = {}
    # 微信 XML 常写成 ``aeskey= "xxx"`` / ``cdnurl = "xxx"``，等号两侧可能有空格
    for key, value in re.findall(r'([\w:-]+)\s*=\s*"([^"]*)"', match.group(1)):
        attrs[key] = html.unescape(value)
    return attrs


def _is_file_appmsg(text: str) -> bool:
    """判断 appmsg 是否是文件消息。

    很多 app 消息（小程序、链接）也带 ``<appattach>``，不能只看该标签；
    以 ``<fileext>`` / ``<filename>`` 或 ``<type>6</type>`` 为准。
    """
    if _tag_text(text, "fileext") or _tag_text(text, "filename"):
        return True
    return appmsg_type(text) in (6, 74)


class MediaResolver:
    def __init__(self, db: WeChatDB, cache_root: Path | None = None) -> None:
        self.db = db
        self.account_dir = Path(db.account_dir)
        self.cache_root = Path(cache_root) if cache_root else webot_data_path("media_cache")
        self._image_keys: tuple[bytes, int] | None | bool = False
        self._voice_cache: dict | None = None

    # ------------------------------------------------------------------
    # 对外入口
    # ------------------------------------------------------------------
    def resolve(self, chat_id: str, row: dict, *, kind: str = "auto",
                inline: bool = False, download: bool = True) -> dict:
        errors: list[str] = []
        local_type = int(row.get("local_type") or 0)
        base_type = local_type & 0xFFFFFFFF
        text = self._content_text(row)

        if kind and kind != "auto":
            result = self._dispatch(chat_id, row, text, kind, download, errors)
        else:
            result = self._dispatch(chat_id, row, text, base_type, download, errors)

        result.setdefault("kind", "unknown")
        result.setdefault("available", bool(result.get("items")))
        result.setdefault("items", [])
        result["md5"] = result.get("md5") or _hex_id(text)
        result["errors"] = errors
        if inline:
            self._attach_inline(result)
        return result

    def summarize(self, chat_id: str, row: dict) -> dict:
        """只判断媒体是否存在，不解密、不下载。"""
        local_type = int(row.get("local_type") or 0)
        base_type = local_type & 0xFFFFFFFF
        text = self._content_text(row)
        summary: dict = {"kind": "unknown", "available": False, "md5": ""}

        try:
            if base_type == 3:
                image_id = _hex_id(row.get("packed_info")) or _hex_id(text)
                summary["kind"] = "image"
                summary["md5"] = image_id
                path = self._find_image_any(chat_id, image_id, row.get("create_time"))
                summary["available"] = bool(path)
                summary["path"] = str(path) if path else ""
            elif base_type == 43:
                video_id = _hex_id(row.get("packed_info")) or _hex_id(text)
                summary["kind"] = "video"
                summary["md5"] = video_id
                path = self._find_video_path(video_id, row.get("create_time"))
                summary["available"] = bool(path)
                summary["path"] = str(path) if path else ""
            elif base_type == 34:
                summary["kind"] = "voice"
                path = self._find_voice_path(chat_id, row)
                summary["available"] = bool(path)
                summary["path"] = str(path) if path else ""
            elif base_type == 47:
                attrs = _tag_attrs(text, "emoji")
                md5 = (attrs.get("md5") or _hex_id(text)).lower()
                summary["kind"] = "emoji"
                summary["md5"] = md5
                path = self._emoji_cached(md5) or self._emoji_local_encrypted(md5)
                summary["available"] = bool(path)
                summary["path"] = str(path) if path else ""
            elif base_type == 49:
                app_type = appmsg_type(text)
                if app_type == 19:
                    data = parse_forward(text) or {}
                    summary.update({"kind": "forward", "available": bool(data),
                                    "count": data.get("count", 0)})
                elif app_type == 57:
                    data = parse_reference(text) or {}
                    summary.update({"kind": "reference", "available": bool(data),
                                    "title": data.get("title", "")})
                elif _is_file_appmsg(text):
                    name = PurePath(_tag_text(text, "title")).name
                    path = self._find_file_path(name, row.get("create_time"))
                    summary.update({"kind": "file", "available": bool(path),
                                    "path": str(path) if path else ""})
                else:
                    summary["kind"] = "app"
        except Exception as exc:  # 摘要接口不因单个媒体失败而中断
            logger.debug("media summarize failed: %s", exc)
        return summary

    # ------------------------------------------------------------------
    # 分发
    # ------------------------------------------------------------------
    def _dispatch(self, chat_id: str, row: dict, text: str,
                  kind: Any, download: bool, errors: list[str]) -> dict:
        if kind == 3 or kind == "image":
            return self._resolve_image(chat_id, row, text, errors)
        if kind == 43 or kind == "video":
            return self._resolve_video(chat_id, row, text, errors)
        if kind == 34 or kind == "voice":
            return self._resolve_voice(chat_id, row, errors)
        if kind == 47 or kind == "emoji":
            return self._resolve_emoji(text, download, errors)
        if kind == 49:
            app_type = appmsg_type(text)
            if app_type == 19:
                return self._resolve_forward(chat_id, row, text, errors)
            if app_type == 57:
                return self._resolve_reference(text)
            if _is_file_appmsg(text):
                return self._resolve_file(row, text, errors)
            return self._resolve_app(text)
        if kind == "forward":
            return self._resolve_forward(chat_id, row, text, errors)
        if kind == "reference":
            return self._resolve_reference(text)
        if kind == "file":
            return self._resolve_file(row, text, errors)
        if kind == "app":
            return self._resolve_app(text)
        return {"kind": "unknown", "items": [], "available": False}

    # ------------------------------------------------------------------
    # 图片
    # ------------------------------------------------------------------
    def _resolve_image(self, chat_id: str, row: dict, text: str,
                       errors: list[str]) -> dict:
        image_id = _hex_id(row.get("packed_info"))
        if not image_id:
            image_id = _hex_id(_tag_attrs(text, "img").get("md5")) or _hex_id(text)
        if not image_id:
            errors.append("图片消息缺少 32 位文件 id")
            return {"kind": "image", "items": [], "available": False}

        keys = self._get_image_keys()
        chat_md5 = hashlib.md5(chat_id.encode("utf-8")).hexdigest()
        months = self._months(row.get("create_time"))
        variants = (
            ("_W.dat", "full", "xor"),
            ("_h.dat", "full", "dat"),
            (".dat", "full", "dat"),
            ("_t_W.dat", "thumb", "xor"),
            ("_t.dat", "thumb", "dat"),
        )
        items: list[dict] = []
        for suffix, role, mode in variants:
            path = self._find_attach(chat_md5, "Img", image_id + suffix, months)
            if path is None:
                continue
            if mode == "raw":
                items.append(self._item(path, role, "application/octet-stream",
                                        note="加密格式未知，仅返回原路径"))
                continue
            try:
                raw = path.read_bytes()
            except OSError as exc:
                errors.append("读取 %s 失败: %s" % (path.name, exc))
                continue
            if mode == "xor":
                if keys is None:
                    items.append(self._item(path, role, "application/octet-stream",
                                            note="图片密钥不可用，仅返回 .dat 路径"))
                    continue
                plain, ext = dat2img.decrypt_xor_only(raw, keys[1])
            else:
                if keys is None:
                    items.append(self._item(path, role, "application/octet-stream",
                                            note="图片密钥不可用，仅返回 .dat 路径"))
                    continue
                plain, ext, note = dat2img.decrypt_dat(raw, keys[0], keys[1])
                if not ext:
                    items.append(self._item(path, role, "application/octet-stream",
                                            note=note or "解密失败"))
                    continue
                if ext == "wxgf":
                    # 微信 4.x 原图：wxgf 头 + Annex B HEVC，转成 JPEG 后再缓存
                    jpg, jext, jnote = dat2img.decode_wxgf(plain)
                    if jpg and jext == "jpg":
                        cache_path = self._image_cache_path(
                            chat_id, image_id + suffix, "jpg"
                        )
                        cached = self._write(cache_path, jpg)
                        items.append(self._item(
                            cache_path, role, "image/jpeg",
                            size=len(jpg), cached=cached, note="wxgf 已转 JPEG",
                        ))
                    else:
                        items.append(self._item(
                            path, role, IMAGE_MIME["wxgf"],
                            note=jnote or "wxgf 私有图，需专用解码",
                        ))
                    continue
                if note:
                    errors.append("%s: %s" % (path.name, note))
            if not ext or not plain:
                items.append(self._item(path, role, "application/octet-stream",
                                        note="解密后未识别图片"))
                continue
            cache_path = self._image_cache_path(chat_id, image_id + suffix, ext)
            cached = self._write(cache_path, plain)
            items.append(self._item(cache_path, role, IMAGE_MIME.get(ext, "image/jpeg"),
                                    size=len(plain), cached=cached))

        if not items:
            errors.append("本地未找到图片文件（可能已被微信清理）")
        has_image = any(i["mime"].startswith("image/") for i in items)
        return {"kind": "image", "md5": image_id, "items": items,
                "available": has_image or bool(items)}

    def _get_image_keys(self) -> tuple[bytes, int] | None:
        if self._image_keys is not False:
            return self._image_keys  # type: ignore[return-value]
        cfg = self.db.cfg_dword
        if not cfg:
            try:
                got = self.db.extract_master_key()
                if got:
                    cfg = got[1]
                    self.db.cfg_dword = cfg
            except Exception as exc:
                logger.debug("extract_master_key failed: %s", exc)
        if not cfg:
            self._image_keys = None
            return None
        keys = dat2img.derive_image_keys(int(cfg), self.db.wxid)
        self._image_keys = keys
        return keys

    # ------------------------------------------------------------------
    # 视频
    # ------------------------------------------------------------------
    def _resolve_video(self, chat_id: str, row: dict, text: str,
                       errors: list[str]) -> dict:
        video_id = _hex_id(row.get("packed_info"))
        if not video_id:
            attrs = _tag_attrs(text, "videomsg")
            video_id = _hex_id(attrs.get("md5") or attrs.get("newmd5")) or _hex_id(text)
        if not video_id:
            errors.append("视频消息缺少 32 位文件 id")
            return {"kind": "video", "items": [], "available": False}

        months = self._months(row.get("create_time"))
        items: list[dict] = []
        for suffix, role in ((".mp4", "full"), ("_raw.mp4", "full"), ("_thumb.jpg", "thumb")):
            path = self._find_video(video_id + suffix, months)
            if path is None:
                continue
            try:
                size = path.stat().st_size
                head = path.read_bytes()[:12] if suffix != "_thumb.jpg" else b""
            except OSError as exc:
                errors.append("读取 %s 失败: %s" % (path.name, exc))
                continue
            mime = "image/jpeg" if suffix == "_thumb.jpg" else "video/mp4"
            if suffix != "_thumb.jpg" and head[4:8] != b"ftyp":
                errors.append("%s 不是有效 MP4" % path.name)
            items.append(self._item(path, role, mime, size=size))
        if not items:
            errors.append("本地未找到视频文件（可能未下载或已被清理）")
        return {"kind": "video", "md5": video_id, "items": items,
                "available": any(i["mime"] == "video/mp4" for i in items)}

    # ------------------------------------------------------------------
    # 文件
    # ------------------------------------------------------------------
    def _resolve_file(self, row: dict, text: str, errors: list[str]) -> dict:
        title = _tag_text(text, "title") or _tag_text(text, "filename")
        name = PurePath(title).name if title else ""
        if not name:
            errors.append("文件消息缺少文件名")
            return {"kind": "file", "items": [], "available": False}
        path = self._find_file_path(name, row.get("create_time"))
        if path is None:
            errors.append("本地未找到文件: %s" % name)
            return {"kind": "file", "items": [], "available": False}

        try:
            actual = path.stat().st_size
        except OSError:
            actual = 0
        expected = _tag_text(text, "totallen")
        if expected.isdigit() and actual and int(expected) != actual:
            errors.append("文件大小不一致: 期望 %s，实际 %s" % (expected, actual))
        mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
        return {"kind": "file", "md5": _tag_text(text, "md5"),
                "items": [self._item(path, "document", mime, size=actual)],
                "available": True}

    # ------------------------------------------------------------------
    # 语音
    # ------------------------------------------------------------------
    def _resolve_voice(self, chat_id: str, row: dict, errors: list[str]) -> dict:
        path = self._find_voice_path(chat_id, row)
        items: list[dict] = []
        if path is not None:
            try:
                size = path.stat().st_size
            except OSError:
                size = 0
            items.append(self._item(path, "audio", "audio/silk", size=size))
        else:
            data = self._voice_from_media_db(chat_id, row)
            if data:
                name = "%s_%s.silk" % (row.get("local_id"), row.get("server_id") or "")
                target = self._cache_dir("voice") / name
                cached = self._write(target, data)
                items.append(self._item(target, "audio", "audio/silk",
                                        size=len(data), cached=cached))
            else:
                errors.append("本地未找到语音文件，语音库中也没有 voice_data")

        result = {"kind": "voice", "items": items, "available": bool(items)}
        svr_id = str(row.get("server_id") or "")
        if svr_id:
            result["text"] = self._voice_text(svr_id)
        return result

    def _find_voice_path(self, chat_id: str, row: dict) -> Optional[Path]:
        try:
            locator = VoiceFileLocator(self.db.db_dir, account_dir=self.db.account_dir)
            found = locator.find_voice_file({
                "server_id": row.get("server_id"),
                "msg_svr_id": row.get("server_id"),
            })
            if found:
                return found
        except Exception as exc:
            logger.debug("voice locator failed: %s", exc)

        account = self.account_dir
        svr = row.get("server_id")
        if svr:
            for sub in ("voice", "attach"):
                base = account / "msg" / sub / str(svr)
                for ext in (".silk", ".amr"):
                    candidate = base / ("%s%s" % (svr, ext))
                    if candidate.is_file():
                        return candidate
        return None

    def _voice_from_media_db(self, chat_id: str, row: dict) -> bytes:
        local_id = row.get("local_id")
        if local_id is None:
            return b""
        for rel, path, _ in self.db._db_files:
            name = os.path.basename(path).lower()
            if not (name.startswith("media_") and name.endswith(".db")):
                continue
            try:
                conn = self.db._open(rel)
            except Exception:
                continue
            try:
                got = conn.execute(
                    "SELECT voice_data FROM VoiceInfo WHERE chat_name_id="
                    "(SELECT rowid FROM Name2Id WHERE user_name=?) AND local_id=?",
                    (chat_id, int(local_id)),
                ).fetchone()
                if got and got[0]:
                    return bytes(got[0])
            except Exception as exc:
                logger.debug("read voice_data from %s failed: %s", rel, exc)
            finally:
                conn.close()
        return b""

    def _voice_text(self, server_id: str) -> str:
        if self._voice_cache is None:
            path = webot_data_path("voice_cache.json")
            try:
                self._voice_cache = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                self._voice_cache = {}
        entry = self._voice_cache.get(server_id)
        if isinstance(entry, dict):
            return str(entry.get("text") or "")
        return ""

    # ------------------------------------------------------------------
    # 表情
    # ------------------------------------------------------------------
    def _resolve_emoji(self, text: str, download: bool, errors: list[str]) -> dict:
        attrs = _tag_attrs(text, "emoji")
        md5 = (attrs.get("md5") or "").lower()
        if not md5:
            md5 = _hex_id(text)
        if not md5:
            errors.append("表情消息缺少 md5")
            return {"kind": "emoji", "items": [], "available": False}

        cached = self._emoji_cached(md5)
        if cached is not None:
            return {"kind": "emoji", "md5": md5,
                    "items": [self._item(cached, "full", IMAGE_MIME.get(cached.suffix.lstrip("."), "image/gif"),
                                         size=cached.stat().st_size, cached=True)],
                    "available": True}

        meta = {}
        if not attrs.get("aeskey"):
            try:
                meta = self.db.get_emoticon_meta(md5) or {}
            except Exception as exc:
                logger.debug("get_emoticon_meta failed: %s", exc)
        aeskey = attrs.get("aeskey") or meta.get("aes_key") or ""
        urls = (
            ("plain", attrs.get("cdnurl") or meta.get("cdn_url") or ""),
            ("encrypted", attrs.get("encrypturl") or meta.get("encrypt_url") or ""),
            ("thumb", attrs.get("thumburl") or meta.get("thumb_url") or ""),
        )

        if download:
            for role, url in urls:
                if not url:
                    continue
                try:
                    data = self._http_get(url)
                except Exception as exc:
                    errors.append("表情下载失败(%s): %s" % (role, exc))
                    continue
                plain, ext = b"", ""
                if role == "encrypted" and aeskey:
                    plain, ext = dat2img.decrypt_emoji(data, aeskey)
                else:
                    plain = data
                    ext = dat2img.looks_like_image(data)
                    if not ext and aeskey:
                        plain, ext = dat2img.decrypt_emoji(data, aeskey)
                if not ext or not plain:
                    errors.append("表情下载内容无法识别(%s)" % role)
                    continue
                target = self._emoji_cache_path(md5, ext)
                self._write(target, plain)
                return {"kind": "emoji", "md5": md5,
                        "items": [self._item(target, "full", IMAGE_MIME.get(ext, "image/gif"),
                                             size=len(plain), cached=True)],
                        "available": True}

        local = self._emoji_local_encrypted(md5)
        if local is not None:
            items = [self._item(local, "encrypted", "application/octet-stream",
                                note="本地缓存为加密格式，联网后可解密预览")]
            if not download:
                errors.append("未开启下载，仅返回本地加密缓存")
            return {"kind": "emoji", "md5": md5, "items": items, "available": False}
        errors.append("表情无可用下载地址或本地缓存")
        return {"kind": "emoji", "md5": md5, "items": [], "available": False}

    # ------------------------------------------------------------------
    # 合并转发 / 引用 / 应用消息
    # ------------------------------------------------------------------
    def _resolve_forward(self, chat_id: str, row: dict, text: str,
                         errors: list[str]) -> dict:
        data = parse_forward(text)
        if not data:
            errors.append("合并转发内容解析失败")
            return {"kind": "forward", "items": [], "available": False}
        chat_md5 = hashlib.md5(chat_id.encode("utf-8")).hexdigest()
        months = self._months(row.get("create_time"))
        for item in data.get("items", []):
            if not item.get("md5"):
                continue
            if item.get("type") == "image":
                item["path"] = str(self._find_forward_media(chat_md5, "Img",
                                                            item["md5"], months) or "")
            elif item.get("type") == "video":
                item["path"] = str(self._find_video(item["md5"], months) or "")
        return {"kind": "forward", "items": [], "available": True,
                "md5": data.get("items", [{}])[0].get("md5", "") if data.get("items") else "",
                "forward": data}

    def _resolve_reference(self, text: str) -> dict:
        data = parse_reference(text)
        if not data:
            return {"kind": "reference", "items": [], "available": False}
        return {"kind": "reference", "items": [], "available": True, "reference": data}

    def _resolve_app(self, text: str) -> dict:
        return {"kind": "app", "items": [], "available": False,
                "title": _tag_text(text, "title"),
                "url": _tag_text(text, "url")}

    # ------------------------------------------------------------------
    # 路径与缓存
    # ------------------------------------------------------------------
    def _content_text(self, row: dict) -> str:
        content = row.get("content")
        if isinstance(content, bytes):
            try:
                content = WeChatDB._friendly_content(
                    content, WeChatDB._msg_type_name(int(row.get("local_type") or 0)))
            except Exception:
                content = ""
        return str(content or "")

    @staticmethod
    def _months(timestamp: Any) -> list[str]:
        try:
            dt = datetime.fromtimestamp(int(timestamp))
        except (TypeError, ValueError, OSError):
            return [datetime.now().strftime("%Y-%m")]
        out = []
        year, month = dt.year, dt.month
        for delta in (0, -1, 1):
            m = month + delta
            y = year
            while m <= 0:
                m += 12
                y -= 1
            while m > 12:
                m -= 12
                y += 1
            out.append("%04d-%02d" % (y, m))
        return out

    def _find_attach(self, chat_md5: str, sub: str, name: str,
                     months: list[str]) -> Optional[Path]:
        for month in months:
            path = self.account_dir / "msg" / "attach" / chat_md5 / month / sub / name
            if path.is_file():
                return path
        return None

    def _find_image_any(self, chat_id: str, image_id: str,
                        timestamp: Any) -> Optional[Path]:
        if not image_id:
            return None
        chat_md5 = hashlib.md5(chat_id.encode("utf-8")).hexdigest()
        months = self._months(timestamp)
        for suffix in ("_W.dat", "_h.dat", ".dat", "_t_W.dat", "_t.dat"):
            path = self._find_attach(chat_md5, "Img", image_id + suffix, months)
            if path is not None:
                return path
        return None

    def _find_video(self, name: str, months: list[str]) -> Optional[Path]:
        for month in months:
            path = self.account_dir / "msg" / "video" / month / name
            if path.is_file():
                return path
        return None

    def _find_video_path(self, video_id: str, timestamp: Any) -> Optional[Path]:
        if not video_id:
            return None
        months = self._months(timestamp)
        for suffix in (".mp4", "_raw.mp4"):
            path = self._find_video(video_id + suffix, months)
            if path is not None:
                return path
        return None

    def _find_file_path(self, name: str, timestamp: Any) -> Optional[Path]:
        if not name:
            return None
        for month in self._months(timestamp):
            path = self.account_dir / "msg" / "file" / month / name
            if path.is_file():
                return path
        root = self.account_dir / "msg" / "file"
        if root.is_dir():
            try:
                for path in root.rglob("*"):
                    if path.is_file() and path.name == name:
                        return path
            except OSError:
                pass
        return None

    def _find_forward_media(self, chat_md5: str, sub: str, md5: str,
                            months: list[str]) -> Optional[Path]:
        for month in months:
            base = self.account_dir / "msg" / "attach" / chat_md5 / month / sub
            if not base.is_dir():
                continue
            try:
                for path in base.iterdir():
                    if path.is_file() and path.name.startswith(md5):
                        return path
            except OSError:
                continue
        return None

    def _cache_dir(self, kind: str) -> Path:
        safe = re.sub(r"[^0-9A-Za-z_.-]", "_", self.db.account or "account")
        return self.cache_root / safe / kind

    def _image_cache_path(self, chat_id: str, name: str, ext: str) -> Path:
        chat_md5 = hashlib.md5(chat_id.encode("utf-8")).hexdigest()[:8]
        return self._cache_dir("image") / chat_md5 / ("%s.%s" % (name, ext))

    def _emoji_cache_path(self, md5: str, ext: str) -> Path:
        return self._cache_dir("emoji") / ("%s.%s" % (md5, ext))

    def _emoji_cached(self, md5: str) -> Optional[Path]:
        if not md5:
            return None
        for ext in ("gif", "png", "jpg", "webp"):
            path = self._emoji_cache_path(md5, ext)
            if path.is_file():
                return path
        return None

    def _emoji_local_encrypted(self, md5: str) -> Optional[Path]:
        if not md5:
            return None
        prefix = md5[:2]
        patterns = (
            "cache/*/Emoticon/%s/%s" % (prefix, md5),
            "business/emoticon/Persist/%s/%s" % (prefix, md5),
        )
        for pattern in patterns:
            try:
                for path in self.account_dir.glob(pattern):
                    if path.is_file():
                        return path
            except OSError:
                continue
        return None

    @staticmethod
    def _write(path: Path, data: bytes) -> bool:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".part")
            tmp.write_bytes(data)
            os.replace(tmp, path)
            return True
        except OSError as exc:
            logger.debug("write cache %s failed: %s", path, exc)
            return False

    @staticmethod
    def _item(path: Path, role: str, mime: str, *, size: int = 0,
              cached: bool = False, note: str = "") -> dict:
        actual = size
        try:
            actual = size or path.stat().st_size
        except OSError:
            actual = size
        item = {
            "role": role,
            "path": str(path),
            "mime": mime,
            "size": actual,
            "cached": cached,
        }
        if note:
            item["note"] = note
        return item

    @staticmethod
    def _http_get(url: str) -> bytes:
        text = html.unescape(str(url or "").strip())
        if not text.lower().startswith(("http://", "https://")):
            raise ValueError("不支持的下载地址")
        request = urllib.request.Request(text, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=10) as response:
            data = response.read(_MAX_DOWNLOAD_BYTES + 1)
        if len(data) > _MAX_DOWNLOAD_BYTES:
            raise ValueError("表情文件超过 20MB")
        return data

    def _attach_inline(self, result: dict) -> None:
        for item in result.get("items", []):
            path = Path(item.get("path") or "")
            mime = item.get("mime", "")
            # 只内联可直接预览的标准图片；wxgf 需专用解码，跳过改用缩略图
            if mime not in _INLINE_IMAGE_MIMES:
                continue
            try:
                size = path.stat().st_size
                if size <= 0 or size > _MAX_INLINE_BYTES:
                    continue
                data = base64.b64encode(path.read_bytes()).decode("ascii")
            except OSError:
                continue
            result["_content_blocks"] = [{
                "type": "image",
                "data": data,
                "mimeType": mime,
            }]
            return
