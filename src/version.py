# -*- coding: utf-8 -*-
"""WeChatBot 版本号与 GitHub 发布地址（唯一来源）。

发布新版本时请同步以下四处，``tests/test_version.py`` 会自动校验前三者 +
CI 默认 tag 一致：

1. 本文件 ``APP_VERSION``
2. ``installer.nsi`` 的 ``PRODUCT_VERSION``
3. ``ui/package.json`` 的 ``version``
4. ``.github/workflows/build-windows-release.yml`` 中 ``tag`` 的 ``default``

CI 构建时也可以用 ``makensis.exe /DPRODUCT_VERSION=x.y.z installer.nsi``
覆盖安装包版本，无需改源码。
"""

from __future__ import annotations

import re

APP_VERSION = "1.3.1"

GITHUB_OWNER = "Otikes"
GITHUB_REPO = "WeChatBot"
GITHUB_URL = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}"
RELEASES_URL = f"{GITHUB_URL}/releases"
LATEST_RELEASE_API = (
    f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
)
INSTALLER_ASSET_NAME = "WeChatBot-setup.exe"

_VERSION_RE = re.compile(r"^[vV]?(\d+)(?:\.(\d+))?(?:\.(\d+))?")


def parse_version(text: str) -> tuple[int, int, int]:
    """把版本字符串解析成三段数字，忽略预发布后缀。

    ``"v1.3.0"`` → ``(1, 3, 0)``，``"1.4"`` → ``(1, 4, 0)``，
    ``"2.0.0-beta"`` → ``(2, 0, 0)``；无法解析时抛 ``ValueError``。
    """
    match = _VERSION_RE.match(str(text or "").strip())
    if not match:
        raise ValueError(f"unsupported version: {text!r}")
    return tuple(int(part or 0) for part in match.groups())  # type: ignore[return-value]


def is_newer(latest: str, current: str = APP_VERSION) -> bool:
    """``latest`` 是否比 ``current`` 新；任一无法解析时保守返回 False。"""
    try:
        return parse_version(latest) > parse_version(current)
    except ValueError:
        return False


def release_url(tag: str) -> str:
    """tag → 对应 Release 页面；空 tag 回退到 Releases 列表。"""
    if not tag:
        return RELEASES_URL
    return f"{GITHUB_URL}/releases/tag/{tag}"
