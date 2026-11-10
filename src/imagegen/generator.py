"""Image generation API client.

仅使用标准库 urllib，避免新增依赖。兼容:
- OpenAI / 各类 OpenAI 兼容中转（NewAPI、OneAPI、OpenRouter 等）
- 智谱 cogview、通义万相、硅基流动等提供 /images/generations 的服务
- 阿里云百炼 / DashScope Qwen-Image 原生同步接口

响应兼容两种返回形态:
1. data[0].b64_json — base64 图片数据，直接解码落盘
2. data[0].url      — 图片 URL，下载后落盘
3. output.choices[0].message.content[*].image — DashScope 图片 URL
"""

import base64
import json
import logging
import math
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from urllib import request as urlrequest

from src.config import webot_data_path
from src.utils.ai_compat import normalize_openai_base_url

logger = logging.getLogger(__name__)

# 生图通常较慢，给足超时；下载图片单独使用较短超时
GENERATE_TIMEOUT_SEC = 180
DOWNLOAD_TIMEOUT_SEC = 120
# 单张图片最大 20MB，防止异常响应撑爆磁盘
MAX_IMAGE_BYTES = 20 * 1024 * 1024
DASHSCOPE_QWEN_BASE_URL = "https://dashscope.aliyuncs.com/api/v1"
GOOGLE_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


def normalize_image_gen_protocol(raw: str) -> str:
    """Normalize image generation protocol aliases."""
    protocol = (raw or "").strip().lower().replace("-", "_")
    aliases = {
        "": "openai_images",
        "openai": "openai_images",
        "openai_compatible": "openai_images",
        "images": "openai_images",
        "newapi": "openai_images",
        "new_api": "openai_images",
        "oneapi": "openai_images",
        "one_api": "openai_images",
        "gpt": "openai_images",
        "dashscope": "dashscope_qwen",
        "dashscope_qwen_image": "dashscope_qwen",
        "qwen": "dashscope_qwen",
        "qwen_image": "dashscope_qwen",
        "aliyun": "dashscope_qwen",
        "aliyun_bailian": "dashscope_qwen",
        "bailian": "dashscope_qwen",
        "tongyi": "dashscope_qwen",
        "google": "google_gemini_image",
        "gemini": "google_gemini_image",
        "google_gemini": "google_gemini_image",
        "gemini_image": "google_gemini_image",
        "nano_banana": "google_gemini_image",
    }
    return aliases.get(protocol, protocol or "openai_images")


def infer_image_gen_protocol(protocol: str, base_url: str, model: str) -> str:
    """Infer DashScope for older Qwen-Image configs that used compatible-mode."""
    normalized = normalize_image_gen_protocol(protocol)
    if normalized != "openai_images":
        return normalized
    lower_url = (base_url or "").lower()
    lower_model = (model or "").lower()
    if "aliyuncs.com" in lower_url and "compatible-mode" in lower_url and "qwen-image" in lower_model:
        return "dashscope_qwen"
    if "generativelanguage.googleapis.com" in lower_url and "gemini" in lower_model:
        return "google_gemini_image"
    return normalized


def normalize_dashscope_base_url(raw: str) -> str:
    """Return a DashScope base URL ending before /services."""
    value = (raw or "").strip() or DASHSCOPE_QWEN_BASE_URL
    if "://" not in value:
        value = f"https://{value}"

    parts = urlsplit(value)
    path = parts.path.rstrip("/")
    path_lower = path.lower()

    suffixes = (
        "/services/aigc/multimodal-generation/generation",
        "/services/aigc/text2image/image-synthesis",
    )
    for suffix in suffixes:
        if path_lower.endswith(suffix):
            path = path[: -len(suffix)].rstrip("/")
            path_lower = path.lower()
            break

    if path_lower.endswith("/compatible-mode/v1"):
        path = path[: -len("/compatible-mode/v1")].rstrip("/") + "/api/v1"
    elif path_lower.endswith("/compatible-mode"):
        path = path[: -len("/compatible-mode")].rstrip("/") + "/api/v1"
    elif path_lower.endswith("/api/v1"):
        path = path
    elif path_lower.endswith("/v1") and "compatible-mode" not in path_lower:
        path = path[: -len("/v1")].rstrip("/") + "/api/v1"
    elif not path_lower.endswith("/api/v1"):
        path = path.rstrip("/") + "/api/v1"

    return urlunsplit((
        parts.scheme,
        parts.netloc,
        path or "/api/v1",
        parts.query,
        "",
    )).rstrip("/")


def normalize_google_gemini_base_url(raw: str) -> str:
    """Return a Google Gemini API base URL ending before /interactions."""
    value = (raw or "").strip() or GOOGLE_GEMINI_BASE_URL
    if "://" not in value:
        value = f"https://{value}"

    parts = urlsplit(value)
    path = parts.path.rstrip("/")
    path_lower = path.lower()
    if path_lower.endswith("/interactions"):
        path = path[: -len("/interactions")].rstrip("/")
        path_lower = path.lower()
    if not (path_lower.endswith("/v1beta") or path_lower.endswith("/v1")):
        path = path.rstrip("/") + "/v1beta"

    return urlunsplit((
        parts.scheme,
        parts.netloc,
        path or "/v1beta",
        parts.query,
        "",
    )).rstrip("/")


def google_response_format_from_size(size: str) -> dict:
    """Map the existing size field to Gemini Interactions response_format."""
    response_format = {"type": "image"}
    raw = (size or "").strip()
    if not raw:
        return response_format

    common_resolutions = {
        "1024x1024": ("1:1", "1K"),
        "1536x1024": ("3:2", "1K"),
        "1024x1536": ("2:3", "1K"),
        "1792x1024": ("16:9", "1K"),
        "1024x1792": ("9:16", "1K"),
    }
    allowed_aspects = {
        "1:1", "1:4", "1:8", "2:3", "3:2", "3:4", "4:3", "4:5",
        "5:4", "4:1", "8:1", "9:16", "16:9", "21:9",
    }
    allowed_sizes = {
        "512PX": "512px",
        "0.5K": "0.5K",
        "05.K": "0.5K",
        "1K": "1K",
        "2K": "2K",
        "4K": "4K",
    }

    for part in raw.replace(",", " ").split():
        token = part.strip()
        normalized_token = token.lower().replace("×", "x")
        if normalized_token in common_resolutions:
            aspect_ratio, image_size = common_resolutions[normalized_token]
            response_format["aspect_ratio"] = aspect_ratio
            response_format["image_size"] = image_size
            continue
        if "x" in normalized_token:
            pieces = normalized_token.split("x", 1)
            try:
                width = int(pieces[0])
                height = int(pieces[1])
            except (TypeError, ValueError):
                continue
            if width > 0 and height > 0:
                divisor = math.gcd(width, height)
                aspect_ratio = f"{width // divisor}:{height // divisor}"
                if aspect_ratio in allowed_aspects:
                    response_format["aspect_ratio"] = aspect_ratio
            continue
        if token in allowed_aspects:
            response_format["aspect_ratio"] = token
            continue
        upper_token = token.upper()
        if upper_token in allowed_sizes:
            response_format["image_size"] = allowed_sizes[upper_token]

    return response_format


def normalize_dashscope_size(size: str) -> str:
    """Convert the shared UI size format to DashScope's width*height form."""
    return (size or "").strip().replace("×", "*").replace("x", "*")


class ImageGenerator:
    """文生图客户端 — 输入提示词，输出本地图片文件路径。

    Usage:
        gen = ImageGenerator(api_key="sk-...", base_url="https://api.x.com/v1",
                             model="gpt-image-1")
        path = gen.generate("赛博朋克风格的猫")
    """

    def __init__(self, api_key: str, base_url: str, model: str,
                 size: str = "", timeout: int = GENERATE_TIMEOUT_SEC,
                 protocol: str = "openai_images"):
        model = (model or "").strip()
        if not model:
            raise ValueError("生图模型未设置，请先获取并选择一个生图模型")
        self.api_key = (api_key or "").strip()
        self.model = model
        self.size = (size or "").strip()
        self.timeout = timeout
        self.protocol = infer_image_gen_protocol(protocol, base_url, model)
        if self.protocol == "dashscope_qwen":
            self.base_url = normalize_dashscope_base_url(base_url)
        elif self.protocol == "google_gemini_image":
            self.base_url = normalize_google_gemini_base_url(base_url)
        else:
            self.base_url = normalize_openai_base_url(base_url)

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

        if self.protocol == "dashscope_qwen":
            return self._generate_dashscope_qwen(prompt)
        if self.protocol == "google_gemini_image":
            return self._generate_google_gemini_image(prompt)
        return self._generate_openai_images(prompt)

    def _generate_openai_images(self, prompt: str) -> Path:
        payload: dict = {"model": self.model, "prompt": prompt, "n": 1}
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
            "Image generation start: protocol=%s model=%s size=%s prompt=%r",
            self.protocol, self.model, self.size or "default", prompt[:60],
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

    def _generate_dashscope_qwen(self, prompt: str) -> Path:
        content = [{"text": prompt}]
        payload: dict = {
            "model": self.model,
            "input": {"messages": [{"role": "user", "content": content}]},
            "parameters": {"negative_prompt": ""},
        }
        dashscope_size = normalize_dashscope_size(self.size)
        if dashscope_size:
            payload["parameters"]["size"] = dashscope_size

        url = f"{self.base_url}/services/aigc/multimodal-generation/generation"
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        logger.info(
            "Image generation start: protocol=%s model=%s size=%s prompt=%r",
            self.protocol, self.model, self.size or "default", prompt[:60],
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

    def _generate_google_gemini_image(self, prompt: str) -> Path:
        payload: dict = {
            "model": self.model,
            "input": [{"type": "text", "text": prompt}],
            "response_format": google_response_format_from_size(self.size),
        }

        url = f"{self.base_url}/interactions"
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.api_key:
            headers["x-goog-api-key"] = self.api_key

        logger.info(
            "Image generation start: protocol=%s model=%s size=%s prompt=%r",
            self.protocol, self.model, self.size or "default", prompt[:60],
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
            image_b64 = self._extract_google_image_b64(body)
            if image_b64:
                return self._decode_b64_image(image_b64)
            image_url = self._extract_dashscope_image_url(body)
            if image_url:
                return self._download(image_url)
            raise ValueError("生图服务返回格式异常：缺少 data 字段")

        first = items[0] or {}
        b64_data = first.get("b64_json")
        if b64_data:
            return base64.b64decode(b64_data)

        image_url = (first.get("url") or "").strip()
        if image_url:
            return self._download(image_url)

        image_url = self._extract_dashscope_image_url(body)
        if image_url:
            return self._download(image_url)

        image_b64 = self._extract_google_image_b64(body)
        if image_b64:
            return self._decode_b64_image(image_b64)

        raise ValueError("生图服务未返回图片数据（缺少 b64_json/url/image）")

    @staticmethod
    def _decode_b64_image(raw: str) -> bytes:
        value = (raw or "").strip()
        if "," in value and value.lower().startswith("data:"):
            value = value.split(",", 1)[1]
        return base64.b64decode(value)

    @staticmethod
    def _extract_dashscope_image_url(body: dict) -> str:
        if not isinstance(body, dict):
            return ""
        choices = ((body.get("output") or {}).get("choices") or [])
        if not choices or not isinstance(choices, list):
            return ""
        message = (choices[0] or {}).get("message") or {}
        content = message.get("content") or []
        if not isinstance(content, list):
            return ""
        for item in content:
            if isinstance(item, dict):
                image_url = (item.get("image") or item.get("url") or "").strip()
                if image_url:
                    return image_url
        return ""

    @staticmethod
    def _extract_google_image_b64(body: dict) -> str:
        if not isinstance(body, dict):
            return ""

        output_image = body.get("output_image") or body.get("outputImage")
        if isinstance(output_image, dict):
            image_b64 = (
                output_image.get("data")
                or output_image.get("bytesBase64Encoded")
                or ""
            )
            if str(image_b64).strip():
                return str(image_b64).strip()

        steps = body.get("steps") or []
        if isinstance(steps, list):
            for step in steps:
                if not isinstance(step, dict):
                    continue
                if step.get("type") and step.get("type") != "model_output":
                    continue
                content = step.get("content") or []
                if not isinstance(content, list):
                    continue
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") != "image":
                        continue
                    image_b64 = block.get("data") or block.get("bytesBase64Encoded") or ""
                    if str(image_b64).strip():
                        return str(image_b64).strip()

        candidates = body.get("candidates") or []
        if isinstance(candidates, list):
            for candidate in candidates:
                parts = (((candidate or {}).get("content") or {}).get("parts") or [])
                if not isinstance(parts, list):
                    continue
                for part in parts:
                    inline_data = (part or {}).get("inlineData") or (part or {}).get("inline_data") or {}
                    if isinstance(inline_data, dict):
                        image_b64 = inline_data.get("data") or ""
                        if str(image_b64).strip():
                            return str(image_b64).strip()

        predictions = body.get("predictions") or []
        if isinstance(predictions, list):
            for prediction in predictions:
                if isinstance(prediction, dict):
                    image_b64 = prediction.get("bytesBase64Encoded") or ""
                    if str(image_b64).strip():
                        return str(image_b64).strip()

        return ""

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
        """将图片写入 WeChatBot 数据目录下的 images/ 子目录。"""
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
    protocol = infer_image_gen_protocol(
        getattr(config, "image_gen_protocol", "openai_images"),
        getattr(config, "image_gen_base_url", ""),
        config.image_gen_model,
    )
    base_url = (config.image_gen_base_url or "").strip()
    if protocol == "dashscope_qwen" and not base_url:
        base_url = DASHSCOPE_QWEN_BASE_URL
    elif protocol == "google_gemini_image" and not base_url:
        base_url = GOOGLE_GEMINI_BASE_URL
    elif not base_url:
        logger.warning(
            "Image generation enabled but IMAGE_GEN_BASE_URL is empty — disabled"
        )
        return None
    try:
        return ImageGenerator(
            api_key=config.image_gen_api_key,
            base_url=base_url,
            model=config.image_gen_model,
            size=config.image_gen_size,
            protocol=protocol,
        )
    except ValueError as e:
        logger.warning("Image generator init failed: %s", e)
        return None
