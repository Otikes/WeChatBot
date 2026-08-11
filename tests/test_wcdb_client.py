"""Tests for defensive WCDB client call handling."""

import unittest
from unittest.mock import MagicMock

try:
    from src.wechat.wcdb_client import WcdbNativeClient
    IMPORT_ERROR = None
except Exception as exc:  # pragma: no cover - non-Windows import guard
    WcdbNativeClient = None
    IMPORT_ERROR = exc


@unittest.skipIf(WcdbNativeClient is None, f"wcdb_client unavailable: {IMPORT_ERROR}")
class WcdbClientDefensiveCallTests(unittest.TestCase):
    def test_call_json_catches_ctypes_access_violation(self):
        client = object.__new__(WcdbNativeClient)
        client._dll = MagicMock()

        def crashing_call(*_args):
            raise OSError("exception: access violation reading 0x00000001")

        result = client._call_json(crashing_call, 123)

        self.assertIsNone(result)
        client._dll.wcdb_free_string.assert_not_called()


if __name__ == "__main__":
    unittest.main()

