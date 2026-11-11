# -*- coding: utf-8 -*-
"""检查 GitHub Releases 上是否有 WeChatBot 新版本。

纯只读、只访问固定的 ``LATEST_RELEASE_API``，不接受任何用户传入的 URL；
断网 / 限流 / 仓库暂无 Release 时静默降级（``ok=False`` + ``error``），
绝不影响控制台主流程。成功结果缓存 10 分钟，失败结果不缓存以便随时重试。
"""

from __future__ import annotations

import json
import logging
import threading
import time
from urllib import error as urlerror
from urllib import request as urlrequest

from src.version import (
    APP_VERSION,
    GITHUB_URL,
    INSTALLER_ASSET_NAME,
    LATEST_RELEASE_API,
    RELEASES_URL,
    is_newer,
    release_url,
)

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 5.0
CACHE_TTL = 600.0
_NOTES_LIMIT = 600

_cache_lock = threading.Lock()
_cache: dict = {"at": 0.0, "data": None}


def _empty(ok: bool, error: str = "") -> dict:
    """统一返回结构；即使检查失败也带上当前版本与各个固定链接。"""
    return {
        "ok": ok,
        "error": error,
        "current_version": APP_VERSION,
        "latest_version": "",
        "has_update": False,
        "published_at": "",
        "notes": "",
        "release_url": RELEASES_URL,
        "download_url": "",
        "repo_url": GITHUB_URL,
        "releases_url": RELEASES_URL,
    }


def _normalize_tag(tag: str) -> str:
    tag = str(tag or "").strip()
    return tag[1:] if tag[:1] in ("v", "V") else tag


def _fetch_latest() -> dict:
    request = urlrequest.Request(
        LATEST_RELEASE_API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"WeChatBot/{APP_VERSION}",
        },
    )
    try:
        with urlrequest.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urlerror.HTTPError as exc:
        if exc.code == 404:
            return _empty(False, "该仓库还没有发布过 Release")
        if exc.code == 403:
            return _empty(False, "GitHub API 请求次数超限，请稍后再试")
        return _empty(False, f"GitHub API 返回 HTTP {exc.code}")
    except (urlerror.URLError, TimeoutError, OSError) as exc:
        return _empty(False, f"无法连接 GitHub：{exc}")
    except ValueError as exc:  # json.JSONDecodeError 是 ValueError 的子类
        return _empty(False, f"GitHub 返回数据解析失败：{exc}")

    if not isinstance(payload, dict):
        return _empty(False, "GitHub 返回数据格式异常")

    tag = str(payload.get("tag_name") or "").strip()
    latest = _normalize_tag(tag)
    fallback_url = release_url(tag)
    download_url = ""
    for asset in payload.get("assets") or []:
        if isinstance(asset, dict) and asset.get("name") == INSTALLER_ASSET_NAME:
            download_url = str(asset.get("browser_download_url") or "")
            break

    result = _empty(True)
    result.update({
        "latest_version": latest,
        "has_update": is_newer(latest),
        "published_at": str(payload.get("published_at") or ""),
        "notes": str(payload.get("body") or "")[:_NOTES_LIMIT],
        "release_url": fallback_url,
        "download_url": download_url or fallback_url,
    })
    return result


def clear_cache() -> None:
    """清空缓存（测试或强制刷新时用）。"""
    with _cache_lock:
        _cache["at"] = 0.0
        _cache["data"] = None


def check_latest_release(force: bool = False) -> dict:
    """查询最新版本；``force=True`` 跳过缓存重新请求。

    Returns:
        ``{"ok", "error", "current_version", "latest_version", "has_update",
        "published_at", "notes", "release_url", "download_url", "repo_url",
        "releases_url"}``。任何异常都被转换成 ``ok=False``，不向外抛。
    """
    now = time.monotonic()
    if not force:
        with _cache_lock:
            cached = _cache["data"]
            if cached is not None and now - _cache["at"] < CACHE_TTL:
                return dict(cached)
    try:
        data = _fetch_latest()
    except Exception as exc:  # 防御：绝不因检查更新拖垮 Web 服务
        logger.warning("Update check failed: %s", exc)
        data = _empty(False, f"检查更新失败：{exc}")
    if data.get("ok"):
        with _cache_lock:
            _cache["at"] = now
            _cache["data"] = data
    return dict(data)
