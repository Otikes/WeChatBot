# -*- coding: utf-8 -*-
"""Tests for src/imagegen — 生图意图识别、提示词提取、生成客户端与路由接入。

覆盖范围:
- intent.py: 关键词匹配（长词优先）、意图判定、提示词提取边界
- generator.py: 初始化校验、响应解析（b64_json）、图片落盘扩展名、工厂函数
- reply.py: ImageReply 数据类
- config.py: BotConfig 生图字段默认值
- server.py: 生图配置读写辅助函数
"""

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from src.config import BotConfig
from src.imagegen import ImageReply
from src.imagegen.generator import (
    ImageGenerator,
    create_image_generator,
    google_response_format_from_size,
    infer_image_gen_protocol,
    normalize_dashscope_base_url,
    normalize_dashscope_size,
    normalize_google_gemini_base_url,
    normalize_image_gen_protocol,
)
from src.imagegen.intent import (
    extract_image_prompt,
    is_image_gen_intent,
    match_image_gen_keyword,
)

DEFAULT_KEYWORDS = BotConfig().image_gen_keywords


# ---------------------------------------------------------------------------
# intent.py — 关键词匹配
# ---------------------------------------------------------------------------


class MatchKeywordTests(unittest.TestCase):
    """match_image_gen_keyword 的匹配规则。"""

    def test_hit_keyword(self):
        """消息包含关键词时应命中。"""
        self.assertEqual(
            match_image_gen_keyword("画一张赛博朋克风格的猫", DEFAULT_KEYWORDS),
            "画一张",
        )

    def test_no_hit_returns_empty(self):
        """不含任何关键词时返回空串。"""
        self.assertEqual(match_image_gen_keyword("今天天气不错", DEFAULT_KEYWORDS), "")

    def test_empty_text_returns_empty(self):
        """空文本不命中。"""
        self.assertEqual(match_image_gen_keyword("", DEFAULT_KEYWORDS), "")

    def test_longer_keyword_wins(self):
        """长词优先：'生成图片' 应优先于 '生图' 命中。"""
        self.assertEqual(
            match_image_gen_keyword("帮我生成图片", DEFAULT_KEYWORDS),
            "生成图片",
        )

    def test_blank_keywords_ignored(self):
        """关键词列表中的空白项被忽略，不报错。"""
        self.assertEqual(match_image_gen_keyword("画一张猫", ["", "  ", "画一张"]), "画一张")


class IsImageGenIntentTests(unittest.TestCase):
    """is_image_gen_intent 的布尔判定。"""

    def test_positive(self):
        self.assertTrue(is_image_gen_intent("生图：一只柯基", DEFAULT_KEYWORDS))

    def test_negative(self):
        self.assertFalse(is_image_gen_intent("帮我总结一下", DEFAULT_KEYWORDS))


# ---------------------------------------------------------------------------
# intent.py — 提示词提取
# ---------------------------------------------------------------------------


class ExtractPromptTests(unittest.TestCase):
    """extract_image_prompt 的提取与清理规则。"""

    def test_basic_extraction(self):
        """去掉命中关键词，保留描述主体。"""
        self.assertEqual(
            extract_image_prompt("画一张赛博朋克风格的猫", DEFAULT_KEYWORDS),
            "赛博朋克风格的猫",
        )

    def test_keeps_chinese_characters(self):
        """清理只针对首尾标点，不能误伤正文汉字（如'一只猫'）。"""
        self.assertEqual(extract_image_prompt("画一只猫", DEFAULT_KEYWORDS), "猫")
        self.assertEqual(
            extract_image_prompt("画一只在草地上奔跑的柯基", DEFAULT_KEYWORDS),
            "在草地上奔跑的柯基",
        )

    def test_strips_edge_punctuation(self):
        """首尾标点与空白被清理。"""
        self.assertEqual(
            extract_image_prompt("画一张，星空下的湖面。", DEFAULT_KEYWORDS),
            "星空下的湖面",
        )

    def test_removes_only_first_occurrence(self):
        """关键词仅移除首次出现，描述中合理重复的词保留。"""
        self.assertEqual(
            extract_image_prompt("画一张画", DEFAULT_KEYWORDS),
            "画",
        )

    def test_fallback_to_full_text(self):
        """提取结果为空时回退完整文本。"""
        self.assertEqual(extract_image_prompt("生图", DEFAULT_KEYWORDS), "生图")


# ---------------------------------------------------------------------------
# generator.py — ImageGenerator
# ---------------------------------------------------------------------------


class ImageGeneratorInitTests(unittest.TestCase):
    """初始化参数校验。"""

    def test_missing_model_raises(self):
        """未设置模型应抛出 ValueError。"""
        with self.assertRaises(ValueError):
            ImageGenerator(api_key="sk-x", base_url="https://api.x.com/v1", model="")

    def test_base_url_normalized(self):
        """base_url 保存时自动去掉尾部 /images/generations 等后缀。"""
        gen = ImageGenerator(
            api_key="sk-x",
            base_url="https://api.x.com/v1/images/generations",
            model="m",
        )
        self.assertEqual(gen.base_url, "https://api.x.com/v1")

    def test_dashscope_compatible_url_normalized(self):
        """阿里云 compatible-mode 地址在 DashScope 协议下会转为原生 /api/v1。"""
        gen = ImageGenerator(
            api_key="sk-x",
            base_url="https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
            model="qwen-image-2.0-pro",
            protocol="dashscope_qwen",
        )
        self.assertEqual(
            gen.base_url,
            "https://token-plan.cn-beijing.maas.aliyuncs.com/api/v1",
        )


class ExtractImageBytesTests(unittest.TestCase):
    """_extract_image_bytes 的响应解析。"""

    def setUp(self):
        self.gen = ImageGenerator(api_key="sk-x", base_url="https://api.x.com/v1", model="m")

    def test_b64_json(self):
        """兼容 b64_json 内联数据。"""
        import base64

        payload = base64.b64encode(b"\x89PNG\r\n\x1a\nfakepng").decode()
        body = {"data": [{"b64_json": payload}]}
        self.assertEqual(self.gen._extract_image_bytes(body), b"\x89PNG\r\n\x1a\nfakepng")

    def test_missing_data_raises(self):
        """缺少 data 字段应报错。"""
        with self.assertRaises(ValueError):
            self.gen._extract_image_bytes({"error": "bad"})

    def test_missing_image_fields_raises(self):
        """data 中既无 b64_json 也无 url 应报错。"""
        with self.assertRaises(ValueError):
            self.gen._extract_image_bytes({"data": [{}]})

    def test_dashscope_image_url(self):
        """兼容 DashScope output.choices[].message.content[].image 响应。"""
        body = {
            "output": {
                "choices": [{
                    "message": {
                        "content": [{"image": "https://img.example.com/a.png"}]
                    }
                }]
            }
        }
        with patch.object(self.gen, "_download", return_value=b"\x89PNG\r\n\x1a\ndata") as download:
            self.assertEqual(self.gen._extract_image_bytes(body), b"\x89PNG\r\n\x1a\ndata")
        download.assert_called_once_with("https://img.example.com/a.png")

    def test_google_image_b64(self):
        """兼容 Google Gemini Interactions 的 steps image base64 响应。"""
        import base64

        payload = base64.b64encode(b"\x89PNG\r\n\x1a\ngoogle").decode()
        body = {
            "steps": [{
                "type": "model_output",
                "content": [{"type": "image", "data": payload}],
            }]
        }
        self.assertEqual(self.gen._extract_image_bytes(body), b"\x89PNG\r\n\x1a\ngoogle")


class ImageGenProtocolTests(unittest.TestCase):
    """生图协议与地址归一化。"""

    def test_protocol_aliases(self):
        self.assertEqual(normalize_image_gen_protocol("dashscope"), "dashscope_qwen")
        self.assertEqual(normalize_image_gen_protocol("openai_compatible"), "openai_images")
        self.assertEqual(normalize_image_gen_protocol("new_api"), "openai_images")
        self.assertEqual(normalize_image_gen_protocol("google"), "google_gemini_image")

    def test_infers_dashscope_for_qwen_image_compatible_mode(self):
        self.assertEqual(
            infer_image_gen_protocol(
                "openai_images",
                "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode",
                "qwen-image-2.0-pro",
            ),
            "dashscope_qwen",
        )

    def test_normalize_dashscope_base_url(self):
        self.assertEqual(
            normalize_dashscope_base_url(
                "token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
            ),
            "https://token-plan.cn-beijing.maas.aliyuncs.com/api/v1",
        )
        self.assertEqual(
            normalize_dashscope_base_url("https://dashscope.aliyuncs.com/api/v1"),
            "https://dashscope.aliyuncs.com/api/v1",
        )
        self.assertEqual(
            normalize_dashscope_base_url(
                "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
            ),
            "https://dashscope.aliyuncs.com/api/v1",
        )

    def test_normalize_google_gemini_base_url(self):
        self.assertEqual(
            normalize_google_gemini_base_url(
                "generativelanguage.googleapis.com/v1beta/interactions"
            ),
            "https://generativelanguage.googleapis.com/v1beta",
        )

    def test_google_response_format_from_size(self):
        self.assertEqual(
            google_response_format_from_size("1024x1792"),
            {
                "type": "image",
                "aspect_ratio": "9:16",
                "image_size": "1K",
            },
        )
        self.assertEqual(
            google_response_format_from_size("16:9 2K"),
            {
                "type": "image",
                "aspect_ratio": "16:9",
                "image_size": "2K",
            },
        )

    def test_normalize_dashscope_size(self):
        self.assertEqual(normalize_dashscope_size("1024x1024"), "1024*1024")


class SaveImageTests(unittest.TestCase):
    """_save_image 的落盘与扩展名推断。"""

    def test_png_and_jpg_extension(self):
        """按魔数选择扩展名，文件写入 images 子目录。"""
        with TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "images"
            with patch("src.imagegen.generator.webot_data_path", return_value=out_dir):
                png_path = ImageGenerator._save_image(b"\x89PNG\r\n\x1a\n" + b"x" * 8)
                jpg_path = ImageGenerator._save_image(b"\xff\xd8\xff" + b"y" * 8)
            self.assertEqual(png_path.suffix, ".png")
            self.assertEqual(jpg_path.suffix, ".jpg")
            self.assertTrue(png_path.exists())
            self.assertTrue(jpg_path.parent == out_dir)


class CreateImageGeneratorTests(unittest.TestCase):
    """create_image_generator 工厂的启用条件。"""

    def _config(self, **overrides):
        kwargs = dict(
            image_gen_enabled=True,
            image_gen_protocol="openai_images",
            image_gen_api_key="sk-x",
            image_gen_base_url="https://api.x.com/v1",
            image_gen_model="gpt-image-1",
        )
        kwargs.update(overrides)
        return BotConfig(**kwargs)

    def test_disabled_returns_none(self):
        self.assertIsNone(create_image_generator(self._config(image_gen_enabled=False)))

    def test_missing_model_returns_none(self):
        self.assertIsNone(create_image_generator(self._config(image_gen_model="")))

    def test_missing_base_url_returns_none(self):
        self.assertIsNone(create_image_generator(self._config(image_gen_base_url="")))

    def test_valid_config_returns_generator(self):
        gen = create_image_generator(self._config())
        self.assertIsInstance(gen, ImageGenerator)
        self.assertEqual(gen.model, "gpt-image-1")

    def test_qwen_compatible_mode_config_infers_dashscope(self):
        gen = create_image_generator(self._config(
            image_gen_base_url="https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode",
            image_gen_model="qwen-image-2.0-pro",
        ))
        self.assertEqual(gen.protocol, "dashscope_qwen")
        self.assertEqual(
            gen.base_url,
            "https://token-plan.cn-beijing.maas.aliyuncs.com/api/v1",
        )

    def test_google_config_can_use_default_base_url(self):
        gen = create_image_generator(self._config(
            image_gen_protocol="google_gemini_image",
            image_gen_base_url="",
            image_gen_model="gemini-3.1-flash-image",
        ))
        self.assertEqual(gen.protocol, "google_gemini_image")
        self.assertEqual(gen.base_url, "https://generativelanguage.googleapis.com/v1beta")


# ---------------------------------------------------------------------------
# reply.py — ImageReply
# ---------------------------------------------------------------------------


class ImageReplyTests(unittest.TestCase):
    """ImageReply 数据类的基本行为。"""

    def test_defaults(self):
        reply = ImageReply(image_path="C:/tmp/a.png")
        self.assertEqual(reply.image_path, "C:/tmp/a.png")
        self.assertEqual(reply.caption, "")


# ---------------------------------------------------------------------------
# config.py — BotConfig 生图字段默认值
# ---------------------------------------------------------------------------


class BotConfigImageGenDefaultsTests(unittest.TestCase):
    """BotConfig 生图字段的默认值。"""

    def test_defaults(self):
        cfg = BotConfig()
        self.assertFalse(cfg.image_gen_enabled)
        self.assertEqual(cfg.image_gen_protocol, "openai_images")
        self.assertEqual(cfg.image_gen_api_key, "")
        self.assertEqual(cfg.image_gen_base_url, "")
        self.assertEqual(cfg.image_gen_model, "")
        self.assertEqual(cfg.image_gen_size, "")
        self.assertIn("画一张", cfg.image_gen_keywords)
        self.assertIn("生图", cfg.image_gen_keywords)


# ---------------------------------------------------------------------------
# server.py — 生图配置读写辅助函数
# ---------------------------------------------------------------------------


class SecretUpdateTests(unittest.TestCase):
    """_secret_update: 掩码值回传时必须保留原密钥。"""

    def test_masked_value_keeps_old(self):
        from src.web.server import _secret_update

        self.assertEqual(_secret_update("sk-a***wxyz", "sk-abcd-secret-wxyz"), "sk-abcd-secret-wxyz")

    def test_new_value_replaces(self):
        from src.web.server import _secret_update

        self.assertEqual(_secret_update("sk-new-key", "sk-old"), "sk-new-key")

    def test_none_returns_none(self):
        """None 表示前端未提交该字段 — 不更新。"""
        from src.web.server import _secret_update

        self.assertIsNone(_secret_update(None, "sk-old"))


class ImageGenServerHelpersTests(unittest.TestCase):
    """_image_gen_config_from_raw / _image_gen_updates_from_config。"""

    def test_from_raw_returns_plain_key(self):
        """读取配置时 API Key 与 LLM 配置保持一致，明文返回给本地 UI。"""
        from src.web.server import _image_gen_config_from_raw

        raw = {
            "IMAGE_GEN_ENABLED": "true",
            "IMAGE_GEN_PROTOCOL": "dashscope_qwen",
            "IMAGE_GEN_API_KEY": "sk-abcdefgh1234",
            "IMAGE_GEN_BASE_URL": "https://api.x.com/v1",
            "IMAGE_GEN_MODEL": "gpt-image-1",
            "IMAGE_GEN_SIZE": "1024x1024",
        }
        cfg = _image_gen_config_from_raw(raw)
        self.assertTrue(cfg["image_gen_enabled"])
        self.assertEqual(cfg["image_gen_protocol"], "dashscope_qwen")
        self.assertEqual(cfg["image_gen_api_key"], "sk-abcdefgh1234")
        self.assertEqual(cfg["image_gen_model"], "gpt-image-1")

    def test_updates_from_config(self):
        """保存配置时生成正确的 env 更新项。"""
        from src.web.server import _image_gen_updates_from_config

        config = {
            "image_gen_enabled": True,
            "image_gen_protocol": "dashscope_qwen",
            "image_gen_api_key": "sk-new-image-key",
            "image_gen_base_url": "https://token-plan.cn-beijing.maas.aliyuncs.com/compatible-mode",
            "image_gen_model": "qwen-image-2.0-pro",
            "image_gen_size": "1024x1024",
        }
        updates = _image_gen_updates_from_config(config)
        self.assertEqual(updates["IMAGE_GEN_ENABLED"], "true")
        self.assertEqual(updates["IMAGE_GEN_PROTOCOL"], "dashscope_qwen")
        self.assertEqual(updates["IMAGE_GEN_API_KEY"], "sk-new-image-key")
        self.assertEqual(
            updates["IMAGE_GEN_BASE_URL"],
            "https://token-plan.cn-beijing.maas.aliyuncs.com/api/v1",
        )
        self.assertEqual(updates["IMAGE_GEN_MODEL"], "qwen-image-2.0-pro")
        self.assertEqual(updates["IMAGE_GEN_SIZE"], "1024x1024")

    def test_updates_from_config_google(self):
        """Google Gemini Image 协议保存时会归一化 base URL。"""
        from src.web.server import _image_gen_updates_from_config

        updates = _image_gen_updates_from_config({
            "image_gen_protocol": "google_gemini_image",
            "image_gen_api_key": "google-key",
            "image_gen_base_url": "generativelanguage.googleapis.com/v1beta/interactions",
            "image_gen_model": "gemini-3.1-flash-image",
        })
        self.assertEqual(updates["IMAGE_GEN_PROTOCOL"], "google_gemini_image")
        self.assertEqual(updates["IMAGE_GEN_API_KEY"], "google-key")
        self.assertEqual(
            updates["IMAGE_GEN_BASE_URL"],
            "https://generativelanguage.googleapis.com/v1beta",
        )


if __name__ == "__main__":
    unittest.main()
