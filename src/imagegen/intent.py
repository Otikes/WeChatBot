"""生图意图识别 — 关键词匹配 + 提示词提取。

触发规则: 用户 @机器人 且消息文本包含任一生图关键词。
关键词可通过 IMAGE_GEN_KEYWORDS 环境变量自定义（逗号分隔）。
"""


def match_image_gen_keyword(text: str, keywords: list[str]) -> str:
    """返回文本中命中的第一个关键词；未命中返回空串。

    优先匹配更长的关键词，避免短词（如"生图"）抢先命中
    导致提示词提取残留更长的词根。
    """
    if not text:
        return ""
    for kw in sorted(keywords or [], key=len, reverse=True):
        kw = kw.strip()
        if kw and kw in text:
            return kw
    return ""


def is_image_gen_intent(text: str, keywords: list[str]) -> bool:
    """判断文本是否带有生图意图。"""
    return bool(match_image_gen_keyword(text, keywords))


def extract_image_prompt(text: str, keywords: list[str]) -> str:
    """从消息文本中提取生图提示词。

    去掉命中的关键词（仅首次出现），并清理首尾的标点/空白，
    例如: "画一张赛博朋克风格的猫" → "赛博朋克风格的猫"。
    如果提取结果为空，回退使用完整文本作为提示词。
    """
    kw = match_image_gen_keyword(text, keywords)
    prompt = text
    if kw:
        # 仅移除第一次出现，避免误删描述中合理重复的词
        prompt = prompt.replace(kw, "", 1)
    # 只清理首尾的标点与空白，不碰正文汉字，避免误伤提示词内容
    prompt = prompt.strip(" \t\r\n，,。.：:；;、！!？?~")
    return prompt if prompt else text.strip()
