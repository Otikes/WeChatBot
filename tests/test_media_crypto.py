# -*- coding: utf-8 -*-
"""Tests for WeChat image / emoji decryption helpers (src.wechat.dat2img)."""

import hashlib
import struct
import unittest

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from src.wechat import dat2img


def _pkcs7(data: bytes) -> bytes:
    pad = 16 - len(data) % 16
    return data + bytes([pad]) * pad


def _aes_ecb_encrypt(key: bytes, data: bytes) -> bytes:
    encryptor = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
    return encryptor.update(_pkcs7(data)) + encryptor.finalize()


def _aes_cbc_encrypt(key: bytes, data: bytes) -> bytes:
    encryptor = Cipher(algorithms.AES(key), modes.CBC(key)).encryptor()
    return encryptor.update(_pkcs7(data)) + encryptor.finalize()


JPEG = b"\xff\xd8\xff" + b"payload!" * 8 + b"\xff\xd9"


def _build_v2(plain: bytes, aes_len: int, aes_key: bytes, xor_key: int,
              tail: bytes) -> bytes:
    prefix = plain[:aes_len]
    middle = plain[aes_len:]
    body = (
        _aes_ecb_encrypt(aes_key, prefix)
        + middle
        + bytes(b ^ xor_key for b in tail)
    )
    header = dat2img.V2_MAGIC + struct.pack("<II", aes_len, len(tail)) + b"\x00"
    return header + body


class TestImageKeys(unittest.TestCase):
    def test_derive_image_keys(self):
        aes_key, xor_key = dat2img.derive_image_keys(0x12345678, "wxid_test")
        expected = hashlib.md5(b"305419896wxid_test").hexdigest()[:16].encode("ascii")
        self.assertEqual(aes_key, expected)
        self.assertEqual(len(aes_key), 16)
        self.assertEqual(xor_key, 0x78)

    def test_looks_like_image(self):
        self.assertEqual(dat2img.looks_like_image(b"\xff\xd8\xffxx"), "jpg")
        self.assertEqual(dat2img.looks_like_image(b"\x89PNG\r\n\x1a\nxx"), "png")
        self.assertEqual(dat2img.looks_like_image(b"GIF89a"), "gif")
        self.assertEqual(dat2img.looks_like_image(b"RIFFxxxxWEBPVP8 "), "webp")
        self.assertEqual(dat2img.looks_like_image(b"wxgf\x00"), "wxgf")
        self.assertEqual(dat2img.looks_like_image(b"BM1234"), "bmp")
        self.assertEqual(dat2img.looks_like_image(b"not-an-image"), "")


class TestXorDecrypt(unittest.TestCase):
    def test_roundtrip_trims_footer(self):
        xor_key = 0x48
        cipher = bytes(b ^ xor_key for b in JPEG + b"12345678")
        plain, ext = dat2img.decrypt_xor_only(cipher, xor_key)
        self.assertEqual(ext, "jpg")
        self.assertEqual(plain, JPEG)


class TestDatDecrypt(unittest.TestCase):
    def setUp(self):
        self.aes_key = b"0123456789abcdef"
        self.xor_key = 0x5A

    def test_decrypt_v2(self):
        raw = _build_v2(JPEG, 32, self.aes_key, self.xor_key, b"garbage-tail")
        plain, ext, note = dat2img.decrypt_dat(raw, self.aes_key, self.xor_key)
        self.assertEqual(ext, "jpg")
        self.assertEqual(note, "")
        self.assertEqual(plain, JPEG)

    def test_decrypt_v1_magic(self):
        raw = _build_v2(JPEG, 16, self.aes_key, self.xor_key, b"tail")
        raw = dat2img.V1_MAGIC + raw[len(dat2img.V2_MAGIC):]
        plain, ext, _ = dat2img.decrypt_dat(raw, self.aes_key, self.xor_key)
        self.assertEqual(ext, "jpg")
        self.assertEqual(plain, JPEG)

    def test_plain_xor_container(self):
        raw = bytes(b ^ self.xor_key for b in JPEG)
        plain, ext, note = dat2img.decrypt_dat(raw, self.aes_key, self.xor_key)
        self.assertEqual(ext, "jpg")
        self.assertEqual(plain, JPEG)
        self.assertIn("XOR", note)

    def test_short_or_unknown(self):
        self.assertEqual(dat2img.decrypt_dat(b"short", self.aes_key, self.xor_key)[1], "")
        self.assertEqual(
            dat2img.decrypt_dat(b"x" * 64, self.aes_key, self.xor_key)[1], "",
        )


class TestEmojiDecrypt(unittest.TestCase):
    def test_cbc_roundtrip(self):
        key_hex = "0123456789abcdef0123456789abcdef"
        gif = b"GIF89a" + b"\x00" * 20 + b";"
        encrypted = _aes_cbc_encrypt(bytes.fromhex(key_hex), gif)
        plain, ext = dat2img.decrypt_emoji(encrypted, key_hex)
        self.assertEqual(ext, "gif")
        self.assertEqual(plain, gif)

    def test_invalid_key(self):
        self.assertEqual(dat2img.decrypt_emoji(b"x" * 32, "not-a-hex-key"), (b"", ""))
        # 长度不合法直接拒绝；密钥正确但内容不是图片时只返回空扩展名
        plain, ext = dat2img.decrypt_emoji(b"x" * 16, "0123456789abcdef0123456789abcdef")
        self.assertEqual(ext, "")


class TestWxgfDecode(unittest.TestCase):
    def test_rejects_non_wxgf(self):
        plain, ext, note = dat2img.decode_wxgf(b"not-wxgf-data")
        self.assertEqual((plain, ext), (b"", ""))
        self.assertIn("wxgf", note)

    def test_missing_hevc_stream(self):
        plain, ext, note = dat2img.decode_wxgf(b"wxgf" + b"\x00" * 64)
        self.assertEqual((plain, ext), (b"", ""))
        self.assertIn("HEVC", note)

    def test_converts_to_jpeg_with_av(self):
        import sys
        import types
        from unittest.mock import patch

        from PIL import Image

        class FakeFrame:
            def to_image(self):
                return Image.new("RGB", (4, 3), (255, 0, 0))

        class FakeContainer:
            def decode(self, video=0):
                yield FakeFrame()

            def close(self):
                pass

        fake_av = types.ModuleType("av")
        fake_av.open = lambda source, format=None: FakeContainer()
        payload = b"wxgf\x00\x00" + b"\x00\x00\x00\x01\x40\x01" + b"\x00" * 32
        with patch.dict(sys.modules, {"av": fake_av}):
            plain, ext, note = dat2img.decode_wxgf(payload)
        self.assertEqual(ext, "jpg")
        self.assertEqual(note, "")
        self.assertTrue(plain.startswith(b"\xff\xd8\xff"))
        self.assertTrue(plain.endswith(b"\xff\xd9"))


if __name__ == "__main__":
    unittest.main()
