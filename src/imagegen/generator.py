"""OpenAI-compatible Images API client (/v1/images/generations).

仅使用标准库 urllib，避免新增依赖。兼容:
- OpenAI / 各类 OpenAI 兼容中转（NewAPI、OneAPI、OpenRouter 等）
- 智谱 cogview、通义万相、硅基流动等提供 /images/generations 的服务

响应兼容两种返回形态:
1. data[0].b64_json — base64 图片数据，直接解码落盘
2. data[0].url      — 图片 URL，下载后落盘
"""

import base64
import json
import logging
import time
import uuid
from pathlib import Path
from urllib import request as urlrequest

from src.config import webot_data_path
from src.utils.ai_compat import normalize_openai_base_url

logger = logging.getLogger(__name__)

# 生图通常较慢，给足超时；下载图片单独使用较短超时
GENERATE_TIMEOUT_SEC = 180
DOWNLOAD_TIMEOUT_SEC = 120
# 单张图片最大 20MB，防止异常响应撑爆磁盘
MAX_IMAGE_BYTES = 20 * 1024 * 1024


class ImageGenerator:
    """文生图客户端 — 输入提示词，输出本地图片文件路径。

    Usage:
        gen = ImageGenerator(api_key="sk-...", base_url="https://api.x.com/v1",
                             model="gpt-image-1")
        path = gen.generate("赛博朋克风格的猫")
    """

    def __init__(self, api_key: str, base_url: str, model: str,
                 size: str = "", timeout: int = GENERATE_TIMEOUT_SEC):
        model = (model or "").strip()
        if not model:
            raise ValueError("生图模型未设置，请先获取并选择一个生图模型")
        self.api_key = (api_key or "").strip()
        self.base_url = normalize_openai_base_url(base_url)
        self.model = model
        self.size = (size or "").strip()
        self.timeout = timeout

    # ── Public API ──────────────────────────────────────────────

    def generate(self, prompt: str) -> Path:
        """调用 Images API 生成图片并保存到 images 目录。

        Returns:
            生成图片的本地路径（PNG/JPEG，取决于服务端返回）。

        Raises:
            ValueError: 提示词为空或服务端未返回图片数据。
            urllib.error.URLError: 网络或服务端错误。
        """
        prompt = (prompt or "").strip()
        if not prompt:
            raise ValueError("生图提示词为空")

        payload: dict = {
            "model": self.model,
            "prompt": prompt,
            "n": 1,
        }
        # size 为可选参数：部分服务商不支持，留空时不传
        if self.size:
            payload["size"] = self.size

        url = f"{self.base_url}/images/generations"
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        logger.info(
            "Image generation start: model=%s size=%s prompt=%r",
            self.model, self.size or "default", prompt[:60],
        )
        started = time.time()

        req = urlrequest.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urlrequest.urlopen(req, timeout=self.timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))

        image_bytes = self._extract_image_bytes(body)
        out_path = self._save_image(image_bytes)

        logger.info(
            "Image generation done in %.1fs → %s (%d bytes)",
            time.time() - started, out_path, len(image_bytes),
        )
        return out_path

    # ── Internals ───────────────────────────────────────────────

    def _extract_image_bytes(self, body: dict) -> bytes:
        """从 Images API 响应中提取图片二进制。

        兼容 b64_json 内联数据与 url 外链两种形态。
        """
        items = body.get("data") if isinstance(body, dict) else None
        if not items or not isinstance(items, list):
            raise ValueError("生图服务返回格式异常：缺少 data 字段")

        first = items[0] or {}
        b64_data = first.get("b64_json")
        if b64_data:
            return base64.b64decode(b64_data)

        image_url = (first.get("url") or "").strip()
        if image_url:
            return self._download(image_url)

        raise ValueError("生图服务未返回图片数据（缺少 b64_json/url）")

    @staticmethod
    def _download(image_url: str) -> bytes:
        """下载外链图片，限制最大体积。"""
        req = urlrequest.Request(
            image_url,
            headers={"Accept": "image/*,*/*;q=0.8"},
        )
        with urlrequest.urlopen(req, timeout=DOWNLOAD_TIMEOUT_SEC) as resp:
            data = resp.read(MAX_IMAGE_BYTES + 1)
        if len(data) > MAX_IMAGE_BYTES:
            raise ValueError("生图服务返回的图片超过 20MB 限制")
        if not data:
            raise ValueError("生图服务返回了空图片")
        return data

    @staticmethod
    def _save_image(image_bytes: bytes) -> Path:
        """将图片写入 webot 数据目录下的 images/ 子目录。"""
        out_dir = webot_data_path("images")
        out_dir.mkdir(parents=True, exist_ok=True)

        # 依据魔数推断扩展名，默认 png
        ext = ".png"
        if image_bytes[:3] == b"\xff\xd8\xff":
            ext = ".jpg"
        elif image_bytes[:8] == b"\x89PNG\r\n\x1a\n":
            ext = ".png"
        elif image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
            ext = ".webp"

        name = f"imggen_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}{ext}"
        out_path = out_dir / name
        out_path.write_bytes(image_bytes)
        return out_path


def create_image_generator(config) -> ImageGenerator | None:
    """根据 BotConfig 创建 ImageGenerator。

    未启用或关键配置缺失时返回 None（调用方负责跳过生图）。
    """
    if not getattr(config, "image_gen_enabled", False):
        return None
    if not (config.image_gen_model or "").strip():
        logger.warning(
            "Image generation enabled but IMAGE_GEN_MODEL is empty — disabled"
        )
        return None
    if not (config.image_gen_base_url or "").strip():
        logger.warning(
            "Image generation enabled but IMAGE_GEN_BASE_URL is empty — disabled"
        )
        return None
    try:
        return ImageGenerator(
            api_key=config.image_gen_api_key,
            base_url=config.image_gen_base_url,
            model=config.image_gen_model,
            size=config.image_gen_size,
        )
    except ValueError as e:
        logger.warning("Image generator init failed: %s", e)
        return None
