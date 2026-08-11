"""Image generation (文生图) — OpenAI-compatible Images API client.

模块职责:
- ImageGenerator: 调用 /v1/images/generations 生成图片并落盘
- ImageReply:     携带图片路径的回复对象，由路由返回、后端负责发送
- 意图识别:       基于关键词判断 @消息是否带有生图意图
"""

from .reply import ImageReply
from .generator import ImageGenerator, create_image_generator
from .intent import is_image_gen_intent, extract_image_prompt

__all__ = [
    "ImageReply",
    "ImageGenerator",
    "create_image_generator",
    "is_image_gen_intent",
    "extract_image_prompt",
]
