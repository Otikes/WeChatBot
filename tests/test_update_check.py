# -*- coding: utf-8 -*-
"""GitHub Release 更新检查：成功解析、离线/限流降级、缓存行为。"""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch
from urllib import error as urlerror

from src import update_check
from src.version import APP_VERSION, LATEST_RELEASE_API, RELEASES_URL, GITHUB_URL


def _release(tag=None, asset=True, body="release notes"):
    # 默认标签跟随 APP_VERSION，避免每次发版都要改测试里的版本字面量
    tag = tag or f"v{APP_VERSION}"
    assets = []
    if asset:
        assets.append({
            "name": "WeChatBot-setup.exe",
            "browser_download_url": (
                f"https://github.com/Otikes/WeChatBot/releases/download/"
                f"{tag}/WeChatBot-setup.exe"
            ),
        })
    return {
        "tag_name": tag,
        "published_at": "2026-11-11T00:37:10Z",
        "body": body,
        "assets": assets,
    }


class FakeResponse:
    def __init__(self, payload=None, raw=None):
        self._raw = raw if raw is not None else json.dumps(payload).encode("utf-8")

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class UpdateCheckTests(unittest.TestCase):
    def setUp(self):
        update_check.clear_cache()

    def tearDown(self):
        update_check.clear_cache()

    def test_same_version_is_up_to_date(self):
        with patch("src.update_check.urlrequest.urlopen",
                   return_value=FakeResponse(_release())) as opened:
            data = update_check.check_latest_release(force=True)
        self.assertTrue(data["ok"])
        self.assertEqual(data["current_version"], APP_VERSION)
        self.assertEqual(data["latest_version"], APP_VERSION)
        self.assertFalse(data["has_update"])
        self.assertEqual(data["published_at"], "2026-11-11T00:37:10Z")
        self.assertEqual(
            data["release_url"],
            f"https://github.com/Otikes/WeChatBot/releases/tag/v{APP_VERSION}",
        )
        self.assertIn("WeChatBot-setup.exe", data["download_url"])
        self.assertEqual(data["repo_url"], GITHUB_URL)
        self.assertEqual(data["releases_url"], RELEASES_URL)
        self.assertEqual(opened.call_args.args[0].full_url, LATEST_RELEASE_API)

    def test_newer_version_is_detected(self):
        # 取「当前主版本 + 1」作为必定更新的标签，避免版本升级后测试失效
        from src.version import parse_version

        newer = f"v{parse_version(APP_VERSION)[0] + 1}.0.0"
        with patch("src.update_check.urlrequest.urlopen",
                   return_value=FakeResponse(_release(newer))):
            data = update_check.check_latest_release(force=True)
        self.assertTrue(data["ok"])
        self.assertTrue(data["has_update"])
        self.assertEqual(data["latest_version"], newer[1:])
        self.assertIn(f"/releases/tag/{newer}", data["release_url"])

    def test_missing_installer_asset_falls_back_to_release_page(self):
        with patch("src.update_check.urlrequest.urlopen",
                   return_value=FakeResponse(_release(asset=False))):
            data = update_check.check_latest_release(force=True)
        self.assertEqual(data["download_url"], data["release_url"])

    def test_notes_are_truncated(self):
        with patch("src.update_check.urlrequest.urlopen",
                   return_value=FakeResponse(_release(body="x" * 5000))):
            data = update_check.check_latest_release(force=True)
        self.assertEqual(len(data["notes"]), update_check._NOTES_LIMIT)

    def test_offline_degrades_without_raising(self):
        with patch("src.update_check.urlrequest.urlopen",
                   side_effect=urlerror.URLError("no network")):
            data = update_check.check_latest_release(force=True)
        self.assertFalse(data["ok"])
        self.assertIn("无法连接 GitHub", data["error"])
        # 即使失败也要带上当前版本与固定链接，前端仍能跳转 Releases
        self.assertEqual(data["current_version"], APP_VERSION)
        self.assertEqual(data["releases_url"], RELEASES_URL)
        self.assertEqual(data["repo_url"], GITHUB_URL)
        self.assertFalse(data["has_update"])

    def test_http_404_and_403_messages(self):
        for code, keyword in ((404, "还没有发布过"), (403, "超限")):
            with self.subTest(code=code):
                err = urlerror.HTTPError(LATEST_RELEASE_API, code, "err", {}, None)
                with patch("src.update_check.urlrequest.urlopen", side_effect=err):
                    data = update_check.check_latest_release(force=True)
                self.assertFalse(data["ok"])
                self.assertIn(keyword, data["error"])

    def test_invalid_json_degrades(self):
        with patch("src.update_check.urlrequest.urlopen",
                   return_value=FakeResponse(raw=b"not json")):
            data = update_check.check_latest_release(force=True)
        self.assertFalse(data["ok"])
        self.assertIn("解析失败", data["error"])

    def test_success_is_cached_and_force_bypasses_it(self):
        with patch("src.update_check.urlrequest.urlopen",
                   return_value=FakeResponse(_release())) as opened:
            first = update_check.check_latest_release()
            second = update_check.check_latest_release()
            self.assertEqual(opened.call_count, 1)
            self.assertEqual(first, second)
            update_check.check_latest_release(force=True)
            self.assertEqual(opened.call_count, 2)

    def test_failure_is_not_cached(self):
        with patch("src.update_check.urlrequest.urlopen",
                   side_effect=urlerror.URLError("offline")):
            update_check.check_latest_release(force=True)
        with patch("src.update_check.urlrequest.urlopen",
                   return_value=FakeResponse(_release())) as opened:
            data = update_check.check_latest_release()
        self.assertEqual(opened.call_count, 1)
        self.assertTrue(data["ok"])

    def test_unexpected_exception_never_escapes(self):
        with patch("src.update_check._fetch_latest", side_effect=RuntimeError("boom")):
            data = update_check.check_latest_release(force=True)
        self.assertFalse(data["ok"])
        self.assertIn("boom", data["error"])


if __name__ == "__main__":
    unittest.main()
