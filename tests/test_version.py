# -*- coding: utf-8 -*-
"""版本号单一来源与解析/比较逻辑；并守住发布时的多处同步。"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from src import version

ROOT = Path(__file__).resolve().parent.parent


class VersionHelperTests(unittest.TestCase):
    def test_parse_version_accepts_common_forms(self):
        self.assertEqual(version.parse_version("v1.3.0"), (1, 3, 0))
        self.assertEqual(version.parse_version("1.3.0"), (1, 3, 0))
        self.assertEqual(version.parse_version("1.4"), (1, 4, 0))
        self.assertEqual(version.parse_version("V2"), (2, 0, 0))
        self.assertEqual(version.parse_version("2.0.0-beta.1"), (2, 0, 0))

    def test_parse_version_rejects_garbage(self):
        for bad in ("", None, "beta", "v", "abc.def"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                version.parse_version(bad)

    def test_is_newer(self):
        self.assertTrue(version.is_newer("1.3.1", "1.3.0"))
        self.assertTrue(version.is_newer("v1.4.0", "1.3.0"))
        self.assertTrue(version.is_newer("2.0.0", "1.9.9"))
        self.assertFalse(version.is_newer("1.3.0", "1.3.0"))
        self.assertFalse(version.is_newer("1.2.9", "1.3.0"))
        self.assertFalse(version.is_newer("garbage", "1.3.0"))

    def test_release_url(self):
        self.assertEqual(
            version.release_url("v1.3.0"),
            "https://github.com/Otikes/WeChatBot/releases/tag/v1.3.0",
        )
        self.assertEqual(version.release_url(""), version.RELEASES_URL)

    def test_github_urls_are_fixed_to_this_repo(self):
        self.assertEqual(
            version.GITHUB_URL, "https://github.com/Otikes/WeChatBot")
        self.assertEqual(
            version.LATEST_RELEASE_API,
            "https://api.github.com/repos/Otikes/WeChatBot/releases/latest",
        )
        self.assertEqual(version.INSTALLER_ASSET_NAME, "WeChatBot-setup.exe")


class VersionConsistencyTests(unittest.TestCase):
    """发布新版本时最容易漏改的几处，统一在这里卡住。"""

    def test_installer_nsi_matches(self):
        text = (ROOT / "installer.nsi").read_text(encoding="utf-8")
        match = re.search(
            r"!ifndef PRODUCT_VERSION\s*\n\s*!define PRODUCT_VERSION \"([^\"]+)\"",
            text,
        )
        self.assertIsNotNone(match, "installer.nsi 中未找到 PRODUCT_VERSION 默认值")
        self.assertEqual(match.group(1), version.APP_VERSION)

    def test_ui_package_json_matches(self):
        data = json.loads((ROOT / "ui" / "package.json").read_text(encoding="utf-8"))
        self.assertEqual(data["version"], version.APP_VERSION)

    def test_ci_default_tags_match(self):
        text = (ROOT / ".github" / "workflows" /
                "build-windows-release.yml").read_text(encoding="utf-8")
        self.assertIn(f'default: "v{version.APP_VERSION}"', text)


if __name__ == "__main__":
    unittest.main()
