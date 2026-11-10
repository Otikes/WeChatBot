# -*- coding: utf-8 -*-
"""Tests for appmsg parsing: merged forward (19) and reference reply (57)."""

import unittest

from src.wechat.forward import appmsg_type, parse_forward, parse_reference

FORWARD_XML = """<msg><appmsg><title>群聊的聊天记录</title><type>19</type>
<recorditem><![CDATA[<recordinfo><info>群聊的聊天记录</info>
<datalist count="2">
<dataitem datatype="1"><datadesc>第一条消息</datadesc><sourcename>张三</sourcename>
<sourcetime>2024-01-02 10:00</sourcetime></dataitem>
<dataitem datatype="2"><fullmd5>0123456789abcdef0123456789abcdef</fullmd5>
<datafmt>jpg</datafmt><datasize>1234</datasize><sourcename>李四</sourcename></dataitem>
</datalist></recordinfo>]]></recorditem></appmsg></msg>"""

REFERENCE_XML = """<msg><appmsg><title>好的，我看下</title><type>57</type>
<refermsg><displayname>张三</displayname><content>报价单什么时候发？</content>
<chatusr>wxid_zhangsan</chatusr></refermsg></appmsg></msg>"""

MINI_PROGRAM_XML = """<msg><appmsg><title>玉小达</title><type>33</type>
<appattach><totallen>173606</totallen><fileext /><filename /></appattach></appmsg></msg>"""

FILE_XML = """<msg><appmsg><title>报考须知.pdf</title><type>6</type>
<appattach><totallen>661670</totallen><fileext>pdf</fileext></appattach></appmsg></msg>"""


class TestAppmsgType(unittest.TestCase):
    def test_types(self):
        self.assertEqual(appmsg_type(FORWARD_XML), 19)
        self.assertEqual(appmsg_type(REFERENCE_XML), 57)
        self.assertIsNone(appmsg_type("<msg><appmsg><title>x</title></appmsg></msg>"))
        self.assertIsNone(appmsg_type(""))


class TestParseForward(unittest.TestCase):
    def test_parse(self):
        data = parse_forward(FORWARD_XML)
        self.assertIsNotNone(data)
        self.assertEqual(data["title"], "群聊的聊天记录")
        self.assertEqual(data["count"], 2)
        self.assertEqual(len(data["items"]), 2)

        first = data["items"][0]
        self.assertEqual(first["datatype"], 1)
        self.assertEqual(first["type"], "text")
        self.assertEqual(first["text"], "第一条消息")
        self.assertEqual(first["sender"], "张三")
        self.assertEqual(first["time"], "2024-01-02 10:00")

        second = data["items"][1]
        self.assertEqual(second["type"], "image")
        self.assertEqual(second["md5"], "0123456789abcdef0123456789abcdef")
        self.assertEqual(second["size"], 1234)
        self.assertEqual(second["fmt"], "jpg")

    def test_not_forward(self):
        self.assertIsNone(parse_forward(REFERENCE_XML))
        self.assertIsNone(parse_forward("<msg></msg>"))

    def test_attributes_with_spaces(self):
        spaced = FORWARD_XML.replace('datatype="1"', 'datatype = "1"').replace(
            'count="2"', 'count = "2"'
        )
        data = parse_forward(spaced)
        self.assertEqual(data["count"], 2)
        self.assertEqual(data["items"][0]["datatype"], 1)


class TestParseReference(unittest.TestCase):
    def test_parse(self):
        data = parse_reference(REFERENCE_XML)
        self.assertIsNotNone(data)
        self.assertEqual(data["title"], "好的，我看下")
        self.assertEqual(data["display_name"], "张三")
        self.assertEqual(data["content"], "报价单什么时候发？")
        self.assertEqual(data["chatusr"], "wxid_zhangsan")

    def test_not_reference(self):
        self.assertIsNone(parse_reference(FORWARD_XML))


class TestMediaAppmsgHelpers(unittest.TestCase):
    def test_tag_attrs_tolerates_spaces(self):
        from src.wechat.media import _tag_attrs
        attrs = _tag_attrs(
            '<emoji md5="abc" aeskey= "4458" cdnurl = "http://x?a=1&amp;b=2" />',
            "emoji",
        )
        self.assertEqual(attrs["md5"], "abc")
        self.assertEqual(attrs["aeskey"], "4458")
        self.assertEqual(attrs["cdnurl"], "http://x?a=1&b=2")

    def test_file_appmsg_detection(self):
        from src.wechat.media import _is_file_appmsg
        self.assertTrue(_is_file_appmsg(FILE_XML))
        # 小程序/链接也带 appattach，但没有 fileext/filename，不能误判为文件
        self.assertFalse(_is_file_appmsg(MINI_PROGRAM_XML))
        self.assertFalse(_is_file_appmsg(REFERENCE_XML))


class TestHelperFormatting(unittest.TestCase):
    def test_forward_summary(self):
        from src.wechat.helpers import _format_app_message
        self.assertEqual(
            _format_app_message(FORWARD_XML),
            "[合并转发: 群聊的聊天记录 (2条)]",
        )

    def test_reference_summary(self):
        from src.wechat.helpers import _format_app_message
        self.assertEqual(_format_app_message(REFERENCE_XML), "[引用: 好的，我看下]")


if __name__ == "__main__":
    unittest.main()
