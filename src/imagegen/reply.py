"""Reply type carrying a generated image.

普通文本回复是 str；生图回复使用 ImageReply 包装，
后端发送时据此走"剪贴板粘贴图片"的发送通道。
"""

from dataclasses import dataclass


@dataclass
class ImageReply:
    """携带图片文件路径的回复对象。

    Attributes:
        image_path: 本地图片文件绝对路径（PNG/JPEG 等常见格式）。
        caption: 可选的说明文字；当前发送通道只发图片，保留字段供扩展。
    """

    image_path: str
    caption: str = ""
