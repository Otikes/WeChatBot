"""DeepSeek summarization preset.

DeepSeek implements an OpenAI-compatible Chat Completions API, so this class
reuses the generic OpenAI-compatible backend with DeepSeek defaults.
"""

from .openai_compatible_backend import OpenAICompatibleSummarizer

# DeepSeek API base URL
DEEPSEEK_BASE_URL = "https://api.deepseek.com"


class DeepSeekSummarizer(OpenAICompatibleSummarizer):
    """Summarization via DeepSeek API (OpenAI-compatible preset)."""

    # 1M context window -> 900K safe budget.
    token_budget = 900_000

    def __init__(self, api_key: str,
                 model: str = "",
                 base_url: str = DEEPSEEK_BASE_URL,
                 chunk_size: int = 400,
                 max_retries: int = 3):
        super().__init__(
            api_key=api_key,
            model=model,
            base_url=base_url,
            chunk_size=chunk_size,
            max_retries=max_retries,
            extra_body={"thinking": {"type": "disabled"}},
        )
