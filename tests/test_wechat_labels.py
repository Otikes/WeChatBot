# -*- coding: utf-8 -*-
"""微信通讯录标签「好友成员」读取的单元测试。

背景：微信 4.x 的 contact.db **没有**独立的「标签 ↔ 联系人」关联表，
每个联系人的标签 id 逗号串存在 ``contact.extra_buffer`` protobuf 的
field 30（4.1.15.13 实测）。旧实现只探关联表/contact 里的 label 列，
所以标签列表能显示、成员永远为空。这里用合成的 contact.db 覆盖主路径、
跨版本自动探字段、旧版关联表回退与昵称补全。
"""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.wechat.wxdb_reader import WeChatDB, _pb_fields, _pb_label_ids


def _varint(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        out.append(byte | 0x80 if value else byte)
        if not value:
            return bytes(out)


def _pb_string(field_no: int, text: str) -> bytes:
    data = text.encode("utf-8")
    return _varint(field_no << 3 | 2) + _varint(len(data)) + data


def _pb_varint_field(field_no: int, value: int) -> bytes:
    return _varint(field_no << 3) + _varint(value)


def _extra_buffer(labels: str, field_no: int = 30) -> bytes:
    """模仿真实 extra_buffer：一堆无关字段 + 一个标签 id 串字段。"""
    return (
        _pb_varint_field(2, 1)
        + _pb_string(4, "湖南")
        + _pb_string(5, "CN")
        + _pb_string(27, "https://mmbiz.qpic.cn/avatar/xxx")
        + _pb_string(field_no, labels)
        + _pb_varint_field(35, 0)
    )


class _StubDB(WeChatDB):
    """只替换 _contact_conn，其余方法走真实实现。"""

    def __init__(self, path: Path):
        self._path = str(path)

    def _contact_conn(self):
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        return conn


class _ContactDbMixin:
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db_path = Path(self._tmp.name) / "contact.db"
        self.conn = sqlite3.connect(self.db_path)
        self.addCleanup(self.conn.close)
        self.conn.executescript(
            """
            CREATE TABLE contact_label (
                label_id_ INTEGER, label_name_ TEXT, sort_order_ INTEGER
            );
            CREATE TABLE contact (
                id INTEGER, username TEXT, remark TEXT, nick_name TEXT,
                extra_buffer BLOB
            );
            """
        )
        self.conn.executemany(
            "INSERT INTO contact_label VALUES (?, ?, ?)",
            [(1, "同学", 0), (2, "G1702", 1), (3, "G1706", 2)],
        )
        self.conn.commit()

    def add_contact(self, username, remark, labels=None, field_no=30,
                    blob=None, extra=b""):
        if blob is None and labels is not None:
            blob = _extra_buffer(labels, field_no) + extra
        self.conn.execute(
            "INSERT INTO contact (id, username, remark, nick_name, extra_buffer) "
            "VALUES (?, ?, ?, ?, ?)",
            (len(self._contacts) + 1, username, remark, "昵称-" + username, blob),
        )
        self._contacts.append(username)
        self.conn.commit()

    @property
    def _contacts(self):
        if not hasattr(self, "_contact_list"):
            self._contact_list = []
        return self._contact_list

    def report(self):
        return _StubDB(self.db_path).contact_label_report()


class ProtobufHelperTests(unittest.TestCase):
    def test_pb_fields_decodes_mixed_wire_types(self):
        blob = (
            _pb_varint_field(2, 1)
            + _pb_string(30, "1,2")
            + _varint(35 << 3 | 5) + b"\x01\x02\x03\x04"
        )
        fields = _pb_fields(blob)
        self.assertIn((2, 0, 1), fields)
        self.assertIn((30, 2, b"1,2"), fields)
        self.assertEqual(fields[-1][0], 35)
        self.assertEqual(fields[-1][1], 5)

    def test_pb_fields_stops_on_truncated_or_unknown_wire(self):
        self.assertEqual(_pb_fields(b"\xf2\x01\x05ab"), [])  # 长度超出
        self.assertEqual(_pb_fields(b"\x0e"), [])             # wire type 6 未知
        self.assertEqual(_pb_fields(_pb_string(30, "1") + b"\x80"),
                         [(30, 2, b"1")])

    def test_pb_label_ids_validates_against_known_labels(self):
        known = {"1", "2", "3"}
        self.assertEqual(_pb_label_ids(b"1,2,3", known), ["1", "2", "3"])
        self.assertEqual(_pb_label_ids(b"25", known), [])
        self.assertEqual(_pb_label_ids(b"1,999", known), [])  # 含未知 id 整串不采信
        self.assertEqual(_pb_label_ids(b"https://x/1,2", known), [])
        self.assertEqual(_pb_label_ids("1,2", known), [])     # 非 bytes
        self.assertEqual(_pb_label_ids(b"\xff\xfe", known), [])


class ExtraBufferLabelTests(_ContactDbMixin, unittest.TestCase):
    def test_members_and_names_are_read_from_field_30(self):
        self.add_contact("wxid_a", "张三", "1,2")
        self.add_contact("wxid_b", "李四", "2")
        self.add_contact("wxid_c", "王五", "3")
        self.add_contact("wxid_none", "无标签")  # extra_buffer 为空

        report = self.report()
        self.assertTrue(report["available"])
        self.assertEqual(report["source"], "contact.extra_buffer#30")
        self.assertIn("contact", report["tables"])
        by_name = {label["name"]: label for label in report["labels"]}
        self.assertEqual(by_name["同学"]["members"], ["wxid_a"])
        self.assertEqual(set(by_name["G1702"]["members"]), {"wxid_a", "wxid_b"})
        self.assertEqual(by_name["G1706"]["members"], ["wxid_c"])
        self.assertEqual(report["member_names"]["wxid_a"], "张三")
        self.assertEqual(report["member_names"]["wxid_b"], "李四")
        self.assertEqual(report["member_names"]["wxid_c"], "王五")
        self.assertNotIn("wxid_none", report["member_names"])
        self.assertIn("3 位好友", report["note"])

    def test_multiple_labels_dedupe_and_empty_labels(self):
        self.add_contact("wxid_a", "张三", "1,1,2")
        report = self.report()
        by_name = {label["name"]: label for label in report["labels"]}
        self.assertEqual(by_name["同学"]["members"], ["wxid_a"])
        self.assertEqual(by_name["同学"]["member_count"], 1)
        self.assertEqual(by_name["G1706"]["members"], [])
        self.assertEqual(by_name["G1706"]["member_count"], 0)

    def test_auto_detects_field_number_when_not_30(self):
        # 换字段号 + 放一个「单数字」诱饵字段，验证按标签种类/多标签打分
        decoy = _pb_string(7, "1")  # 单数字诱饵字段，不应盖过真正的标签字段
        self.add_contact("wxid_a", "张三", "1,2", field_no=42, extra=decoy)
        self.add_contact("wxid_b", "李四", "3", field_no=42, extra=decoy)
        self.add_contact("wxid_c", "王五", "1", field_no=42, extra=decoy)

        report = self.report()
        self.assertEqual(report["source"], "contact.extra_buffer#42")
        by_name = {label["name"]: label for label in report["labels"]}
        self.assertEqual(set(by_name["同学"]["members"]), {"wxid_a", "wxid_c"})
        self.assertEqual(by_name["G1706"]["members"], ["wxid_b"])

    def test_unknown_label_ids_are_ignored(self):
        self.add_contact("wxid_a", "张三", "1,999")
        self.add_contact("wxid_b", "李四", "2")
        report = self.report()
        by_name = {label["name"]: label for label in report["labels"]}
        self.assertEqual(by_name["同学"]["members"], [])
        self.assertEqual(by_name["G1702"]["members"], ["wxid_b"])

    def test_no_label_definitions_is_unavailable(self):
        self.conn.execute("DELETE FROM contact_label")
        self.conn.commit()
        report = self.report()
        self.assertFalse(report["available"])
        self.assertEqual(report["labels"], [])
        self.assertIn("contact_label", report["note"])


class LegacyRelationTableTests(unittest.TestCase):
    """旧版微信：无 extra_buffer，靠独立关联表拿成员。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db_path = Path(self._tmp.name) / "contact.db"
        conn = sqlite3.connect(self.db_path)
        conn.executescript(
            """
            CREATE TABLE contact_label (
                label_id_ INTEGER, label_name_ TEXT, sort_order_ INTEGER
            );
            CREATE TABLE contact (id INTEGER, username TEXT, remark TEXT,
                                  nick_name TEXT);
            CREATE TABLE contact_label_contact (
                label_id_ INTEGER, username_ TEXT
            );
            """
        )
        conn.executemany(
            "INSERT INTO contact_label VALUES (?, ?, ?)",
            [(1, "同学", 0), (2, "同事", 1)],
        )
        conn.executemany(
            "INSERT INTO contact VALUES (?, ?, ?, ?)",
            [(1, "wxid_a", "张三", "A"), (2, "wxid_b", "李四", "B")],
        )
        conn.executemany(
            "INSERT INTO contact_label_contact VALUES (?, ?)",
            [(1, "wxid_a"), (1, "wxid_b"), (2, "wxid_a")],
        )
        conn.commit()
        conn.close()

    def test_relation_table_fallback(self):
        report = _StubDB(self.db_path).contact_label_report()
        self.assertTrue(report["available"])
        self.assertEqual(report["source"],
                         "contact_label_contact.label_id_/username_")
        by_name = {label["name"]: label for label in report["labels"]}
        self.assertEqual(set(by_name["同学"]["members"]), {"wxid_a", "wxid_b"})
        self.assertEqual(by_name["同事"]["members"], ["wxid_a"])
        self.assertEqual(report["member_names"]["wxid_a"], "张三")
        self.assertEqual(report["member_names"]["wxid_b"], "李四")


class LabelNameEnrichmentTests(unittest.TestCase):
    def test_read_contact_labels_merges_cached_and_db_names(self):
        from src.wechat.labels import read_contact_labels

        raw = {
            "available": True,
            "labels": [{
                "label_id": "1", "name": "同学", "sort_order": 0,
                "member_count": 2,
                "members": ["wxid_a", "wxid_b"],
            }],
            "source": "contact.extra_buffer#30",
            "tables": ["contact_label", "contact"],
            "member_names": {"wxid_a": "数据库备注A", "wxid_b": "数据库备注B"},
            "note": "ok",
        }
        client = type("C", (), {"get_contact_labels": lambda self: raw.copy()})()
        with patch("src.wechat.labels._running_client", return_value=client), \
             patch("src.wechat.labels._friend_names",
                   return_value={"wxid_a": "好友缓存A"}):
            out = read_contact_labels()

        self.assertNotIn("member_names", out)
        self.assertEqual(out["labels"][0]["members"], [
            {"wxid": "wxid_a", "name": "好友缓存A"},
            {"wxid": "wxid_b", "name": "数据库备注B"},
        ])
        self.assertEqual(out["labels"][0]["member_count"], 2)

    def test_read_contact_labels_tolerates_already_enriched_members(self):
        from src.wechat.labels import read_contact_labels

        raw = {
            "available": True,
            "labels": [{
                "label_id": "1", "name": "同学", "sort_order": 0,
                "member_count": 1,
                "members": [{"wxid": "wxid_a", "name": ""}],
            }],
            "source": "contact.extra_buffer#30", "tables": [],
            "member_names": {"wxid_a": "张三"}, "note": "",
        }
        client = type("C", (), {"get_contact_labels": lambda self: raw.copy()})()
        with patch("src.wechat.labels._running_client", return_value=client), \
             patch("src.wechat.labels._friend_names", return_value={}):
            out = read_contact_labels()
        self.assertEqual(out["labels"][0]["members"],
                         [{"wxid": "wxid_a", "name": "张三"}])


if __name__ == "__main__":
    unittest.main()
