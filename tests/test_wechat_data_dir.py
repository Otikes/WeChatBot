"""Tests for WeChat data directory detection helpers."""

import tempfile
import unittest
import os
from pathlib import Path
from unittest.mock import patch

from src.wechat import data_dir


def _make_account(base: Path, wxid: str) -> Path:
    account = base / wxid
    session_dir = account / "db_storage" / "session"
    session_dir.mkdir(parents=True)
    (session_dir / "session.db").write_bytes(b"sqlite")
    return account


class WeChatDataDirTests(unittest.TestCase):
    def test_extracts_wechat_files_path_from_command_line(self):
        cmd = (
            r'"C:\Tencent\Weixin\WeChatAppEx.exe" '
            r'--lang=zh-CN --wechat-files-path="E:\File Data\Tencent\Weixin\xwechat_files"'
        )

        self.assertEqual(
            data_dir._extract_paths_from_command_line(cmd),
            [r"E:\File Data\Tencent\Weixin\xwechat_files"],
        )

    def test_finds_account_from_running_process_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "xwechat_files"
            base.mkdir()
            old = _make_account(base, "wxid_old")
            newest = _make_account(base, "wxid_new")
            os.utime(old / "db_storage" / "session" / "session.db", (1000, 1000))
            os.utime(newest / "db_storage" / "session" / "session.db", (2000, 2000))

            with (
                patch.object(data_dir, "_wechat_files_paths_from_processes", return_value=[str(base)]),
                patch.object(data_dir, "_default_candidate_dirs", return_value=[]),
            ):
                wxid, detected_base = data_dir.find_wxid_and_dbpath("")

            self.assertEqual(wxid, "wxid_new")
            self.assertEqual(Path(detected_base), base)

    def test_custom_account_dir_normalizes_to_parent(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "xwechat_files"
            base.mkdir()
            account = _make_account(base, "wxid_custom")

            with (
                patch.object(data_dir, "_wechat_files_paths_from_processes", return_value=[]),
                patch.object(data_dir, "_default_candidate_dirs", return_value=[]),
            ):
                wxid, detected_base = data_dir.find_wxid_and_dbpath(str(account))

            self.assertEqual(wxid, "wxid_custom")
            self.assertEqual(Path(detected_base), base)

    def test_list_accounts_in_data_dir_ignores_accounts_without_session_db(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / "xwechat_files"
            base.mkdir()
            _make_account(base, "wxid_ready")
            (base / "wxid_empty").mkdir()

            accounts = data_dir.list_accounts_in_data_dir(base)

            self.assertEqual([account.wxid for account in accounts], ["wxid_ready"])


if __name__ == "__main__":
    unittest.main()
