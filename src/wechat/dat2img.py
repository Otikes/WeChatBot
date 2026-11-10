# -*- coding: utf-8 -*-
"""微信 4.x 图片 / 表情解密（纯字节处理，不访问数据库）。

图片 .dat 解密依据本机实测与开源实现（WeChatMsg / wechat-log dat2img）：

    [6B magic 07 08 56 32 08 07][4B aes_len LE][4B xor_len LE][1B unknown]
    [AES-ECB 密文段][明文中间段][XOR 密文尾段]

- AES 段长度：``(aes_len // 16) * 16 + 16``，解密后按 PKCS#7 去填充并截到 ``aes_len``；
- 中间段：``data[15 + aes_len0 : len(data) - xor_len]``；
- 尾段逐字节 XOR 单字节 ``xor_key``；
- 图片密钥：``md5(f"{cfg_dword}{wxid}").hexdigest()[:16].encode()``（16 字节 ASCII）；
- XOR 密钥：``cfg_dword & 0xFF``。

表情包（type 47）走 AES-128-CBC，key 与 IV 都等于消息里的 32 位 hex ``aeskey``。
"""

from __future__ import annotations

import hashlib
from typing import Tuple

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

V1_MAGIC = b"\x07\x08\x56\x31\x08\x07"
V2_MAGIC = b"\x07\x08\x56\x32\x08\x07"
DAT_HEADER_SIZE = 15

_JPEG_SOI = b"\xff\xd8\xff"
_JPEG_EOI = b"\xff\xd9"
_PNG_SIG = b"\x89PNG\r\n\x1a\n"
_PNG_END = b"IEND\xaeB`\x82"
_GIF_END = b"\x3b"
MAX_FOOTER = 32


def derive_image_keys(cfg_dword: int, wxid: str) -> Tuple[bytes, int]:
    """由 cfgDword + wxid 派生图片 AES key 与 XOR key。"""
    text = "%d%s" % (int(cfg_dword), wxid or "")
    aes_key = hashlib.md5(text.encode("utf-8")).hexdigest()[:16].encode("ascii")
    return aes_key, int(cfg_dword) & 0xFF


def looks_like_image(data: bytes) -> str:
    """按魔数判断图片类型，返回 jpg/png/gif/webp/wxgf/bmp 或空串。"""
    if not data:
        return ""
    if data.startswith(_JPEG_SOI):
        return "jpg"
    if data.startswith(_PNG_SIG):
        return "png"
    if data.startswith(b"GIF8"):
        return "gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data.startswith(b"wxgf"):
        return "wxgf"
    if data.startswith(b"BM"):
        return "bmp"
    return ""


def _unpad_pkcs7(data: bytes) -> bytes:
    if not data:
        return data
    pad = data[-1]
    if 1 <= pad <= 16 and data[-pad:] == bytes([pad]) * pad:
        return data[:-pad]
    return data


def trim_image_footer(data: bytes) -> bytes:
    """裁剪 JPEG/PNG 结束标记之后的少量页脚（微信 Sns 缓存常见 24 字节）。"""
    if not data:
        return data
    if data.startswith(_JPEG_SOI):
        idx = data.rfind(_JPEG_EOI)
        if idx >= 0 and 0 <= len(data) - (idx + 2) <= MAX_FOOTER:
            return data[: idx + 2]
        return data
    if data.startswith(_PNG_SIG):
        idx = data.rfind(_PNG_END)
        if idx >= 0:
            end = idx + len(_PNG_END)
            if 0 <= len(data) - end <= MAX_FOOTER:
                return data[:end]
        return data
    if data.startswith(b"GIF8"):
        idx = data.rfind(_GIF_END)
        if idx >= 0 and 0 <= len(data) - (idx + 1) <= MAX_FOOTER:
            return data[: idx + 1]
    return data


def decrypt_xor_only(data: bytes, xor_key: int) -> Tuple[bytes, str]:
    """整文件单字节 XOR（``_W.dat`` / ``_t_W.dat``）。"""
    if not data:
        return b"", ""
    key = int(xor_key) & 0xFF
    plain = bytes(b ^ key for b in data)
    plain = trim_image_footer(plain)
    return plain, looks_like_image(plain)


def _aes_ecb_decrypt(key: bytes, data: bytes) -> bytes:
    if len(data) % 16:
        data = data[: len(data) // 16 * 16]
    if not data:
        return b""
    decryptor = Cipher(algorithms.AES(key), modes.ECB()).decryptor()
    return decryptor.update(data) + decryptor.finalize()


def decrypt_dat(data: bytes, aes_key: bytes, xor_key: int) -> Tuple[bytes, str, str]:
    """解密 V1/V2 图片 .dat，返回 ``(plain, ext, note)``；无法识别时 plain 为空。"""
    if not data or len(data) < DAT_HEADER_SIZE + 16:
        return b"", "", "文件过短，不是微信图片容器"
    if not (data.startswith(V2_MAGIC) or data.startswith(V1_MAGIC)):
        plain, ext = decrypt_xor_only(data, xor_key)
        if ext:
            return plain, ext, "整文件 XOR"
        return b"", "", "未知图片容器格式"

    aes_len = int.from_bytes(data[6:10], "little")
    xor_len = int.from_bytes(data[10:14], "little")
    body = data[DAT_HEADER_SIZE:]
    aes_len0 = min((aes_len // 16) * 16 + 16, len(body))
    if aes_len0 <= 0:
        return b"", "", "AES 段长度无效"

    aes_plain = _unpad_pkcs7(_aes_ecb_decrypt(aes_key, body[:aes_len0]))
    if aes_len > 0:
        aes_plain = aes_plain[:aes_len]

    middle_end = len(body) - xor_len
    if middle_end < aes_len0:
        middle_end = aes_len0
    middle = body[aes_len0:middle_end]

    tail = b""
    if xor_len > 0 and middle_end < len(body):
        key = int(xor_key) & 0xFF
        tail = bytes(b ^ key for b in body[middle_end:])

    plain = trim_image_footer(aes_plain + middle + tail)
    ext = looks_like_image(plain)
    if ext == "wxgf":
        return plain, ext, "wxgf 私有图，需专用解码"
    if ext:
        return plain, ext, ""
    return b"", "", "解密后未识别出图片魔数"


def decrypt_emoji(data: bytes, aes_key_hex: str) -> Tuple[bytes, str]:
    """解密表情包：AES-128-CBC，key 与 IV 均为 32 位 hex aeskey。"""
    text = str(aes_key_hex or "").strip()
    if len(text) != 32:
        return b"", ""
    try:
        key = bytes.fromhex(text)
    except ValueError:
        return b"", ""
    if not data or len(data) % 16:
        return b"", ""
    decryptor = Cipher(algorithms.AES(key), modes.CBC(key)).decryptor()
    plain = decryptor.update(data) + decryptor.finalize()
    plain = _unpad_pkcs7(plain)
    plain = trim_image_footer(plain)
    return plain, looks_like_image(plain)


WXGF_MAGIC = b"wxgf"
# wxgf 自定义头之后是 Annex B HEVC，首个 NAL 为 VPS（0x40 >> 1 = 32）
_HEVC_START_CODES = (b"\x00\x00\x00\x01\x40\x01", b"\x00\x00\x01\x40\x01")


def decode_wxgf(data: bytes) -> Tuple[bytes, str, str]:
    """把微信 wxgf 私有图（自定义头 + Annex B HEVC）转成 JPEG。

    返回 ``(jpeg_bytes, "jpg", note)``；失败时返回 ``(b"", "", note)``。
    依赖 PyAV（打包时需包含 ``av``），缺失时降级为返回空。
    """
    if not data or not data.startswith(WXGF_MAGIC):
        return b"", "", "不是 wxgf 格式"
    start = -1
    for code in _HEVC_START_CODES:
        start = data.find(code)
        if start >= 0:
            break
    if start < 0:
        return b"", "", "wxgf 中未找到 HEVC 数据"

    try:
        import io

        import av
    except ImportError:
        return b"", "", "缺少 HEVC 解码组件 PyAV"
    try:
        container = av.open(io.BytesIO(data[start:]), format="hevc")
        try:
            frame = next(container.decode(video=0), None)
            if frame is None:
                return b"", "", "HEVC 解码无输出"
            image = frame.to_image()
            out = io.BytesIO()
            image.save(out, format="JPEG", quality=95)
            return out.getvalue(), "jpg", ""
        finally:
            container.close()
    except Exception as exc:  # noqa: BLE001 - 解码失败要降级而不是中断整个工具
        return b"", "", "HEVC 解码失败: %s" % exc
