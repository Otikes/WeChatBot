"""OpenAI-compatible summarization backend.

This backend talks to providers that implement the OpenAI Chat Completions
protocol. Users only need to configure an API key, a Base URL, and a model
name, which also covers OpenAI-compatible relay services.
"""

import json
import logging
import time
from typing import Any

from openai import (
    APIConnectionError,
    APIStatusError,
    BadRequestError,
    OpenAI,
    RateLimitError,
)

from src.token_stats import record_usage
from src.utils.ai_compat import (
    OPENAI_COMPATIBLE_BASE_URL,
    normalize_openai_base_url,
    openai_api_key_for_client,
)

from .base import AbstractSummarizer
from .models import SummaryResult
from .prompts import (
    CHUNK_SYSTEM_PROMPT,
    MEMORY_CONSOLE_PROMPT,
    MERGE_SYSTEM_PROMPT,
    SYSTEM_PROMPT,
    build_chunk_summary_prompt,
    build_merge_prompt,
    build_summary_prompt,
)

logger = logging.getLogger(__name__)

# Tool schema for structured output -- matches SummaryResult Pydantic model.
STORE_SUMMARY_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "store_summary",
        "description": "Store a structured summary of a group chat conversation",
        "parameters": {
            "type": "object",
            "properties": {
                "summary_text": {
                    "type": "string",
                    "description": "A 2-4 sentence overview of what was discussed",
                },
                "topics": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Main topics discussed in the conversation",
                },
                "participants": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "contributions": {"type": "string"},
                        },
                        "required": ["name", "contributions"],
                        "additionalProperties": False,
                    },
                    "description": "Key participants and what they contributed",
                },
            },
            "required": ["summary_text", "topics", "participants"],
            "additionalProperties": False,
        },
    },
}


def _summary_from_dict(data: dict[str, Any]) -> SummaryResult:
    """Build SummaryResult from a provider-returned dict."""
    raw_topics = data.get("topics", [])
    if isinstance(raw_topics, str):
        topics = [raw_topics]
    elif isinstance(raw_topics, list):
        topics = [str(topic) for topic in raw_topics if topic]
    else:
        topics = []

    participants = []
    for p in data.get("participants", []):
        if isinstance(p, dict):
            participants.append(p)
        elif isinstance(p, str):
            participants.append({"name": p, "contributions": ""})

    return SummaryResult(
        summary_text=str(data.get("summary_text", "")),
        topics=topics,
        participants=participants,
    )


def _loads_json_object(text: str) -> dict[str, Any] | None:
    """Parse a JSON object from plain text or a fenced code block."""
    content = (text or "").strip()
    if not content:
        return None

    if content.startswith("```"):
        lines = content.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        content = "\n".join(lines).strip()

    try:
        data = json.loads(content)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end <= start:
            return None
        try:
            data = json.loads(content[start:end + 1])
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None


def _parse_summary_from_response(response) -> SummaryResult:
    """Extract SummaryResult from an OpenAI-compatible ChatCompletion.

    Tries in order:
    1. Tool call arguments JSON
    2. Message content JSON
    3. Plain text content
    """
    choice = response.choices[0]
    msg = choice.message

    tool_calls = getattr(msg, "tool_calls", None)
    if tool_calls:
        try:
            args_json = tool_calls[0].function.arguments
            data = json.loads(args_json)
            if isinstance(data, dict):
                return _summary_from_dict(data)
        except Exception:
            logger.info("OpenAI-compatible tool call parse failed; trying content")

    content = getattr(msg, "content", "") or ""
    if isinstance(content, str) and content.strip():
        data = _loads_json_object(content)
        if data and "summary_text" in data:
            return _summary_from_dict(data)

        logger.info("OpenAI-compatible backend returned plain text, wrapping as summary")
        return SummaryResult(
            summary_text=content.strip()[:2000],
            topics=[],
            participants=[],
        )

    raise RuntimeError("OpenAI-compatible backend returned empty response")


class OpenAICompatibleSummarizer(AbstractSummarizer):
    """Summarization via OpenAI-compatible Chat Completions APIs.

    Features:
    - Generic API key + Base URL + model configuration
    - Tool calling for structured summaries when supported by the provider
    - Automatic fallback to plain chat completion if tools are rejected
    - Conservative token budget for unknown model context windows
    """

    MODEL_DEFAULT = ""

    # 统计面板中展示的供应商标识（子类可覆盖）
    provider_name = "openai_compatible"

    # A safe default across many compatible providers. Larger-context models
    # still work through map-reduce chunking, just with earlier splitting.
    token_budget = 100_000

    retry_exceptions = (RateLimitError, APIConnectionError, APIStatusError)

    def __init__(self, api_key: str,
                 model: str = MODEL_DEFAULT,
                 base_url: str = OPENAI_COMPATIBLE_BASE_URL,
                 chunk_size: int = 400,
                 max_retries: int = 3,
                 extra_body: dict[str, Any] | None = None):
        normalized_base_url = normalize_openai_base_url(base_url)
        selected_model = (model or "").strip()
        if not selected_model:
            raise ValueError("模型未设置，请先获取并选择一个模型")
        self.client = OpenAI(
            api_key=openai_api_key_for_client(api_key),
            base_url=normalized_base_url,
        )
        self.model = selected_model
        self.base_url = normalized_base_url
        self.chunk_size = chunk_size
        self.max_retries = max_retries
        self._extra_body = extra_body or {}

    # -- Shared request helpers ---------------------------------------

    @staticmethod
    def _should_retry_without_tools(exc: BadRequestError) -> bool:
        text = str(exc).lower()
        return "tool" in text or "function" in text

    def _execute_completion(self, kwargs: dict[str, Any], call_type: str):
        """发起一次 Chat Completions 请求，并记录 token 用量/请求日志。"""
        started = time.time()
        try:
            response = self.client.chat.completions.create(**kwargs)
        except Exception as exc:
            record_usage(
                provider=self.provider_name,
                model=self.model,
                call_type=call_type,
                duration_ms=int((time.time() - started) * 1000),
                status="error",
                error=f"{type(exc).__name__}: {exc}",
            )
            raise

        usage = getattr(response, "usage", None)
        record_usage(
            provider=self.provider_name,
            model=self.model,
            call_type=call_type,
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
            duration_ms=int((time.time() - started) * 1000),
            status="success",
        )
        return response

    def _create_chat_completion(self, *,
                                messages: list[dict],
                                max_tokens: int,
                                use_tools: bool = False,
                                call_type: str = "chat"):
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if self._extra_body:
            kwargs["extra_body"] = self._extra_body
        if use_tools:
            kwargs["tools"] = [STORE_SUMMARY_TOOL]
            kwargs["tool_choice"] = "auto"

        try:
            return self._execute_completion(kwargs, call_type)
        except BadRequestError as exc:
            if use_tools and self._should_retry_without_tools(exc):
                logger.info(
                    "Provider rejected tool calling; retrying without tools"
                )
                kwargs.pop("tools", None)
                kwargs.pop("tool_choice", None)
                return self._execute_completion(kwargs, call_type)
            raise

    # -- Conversational chat API call (called by base class) ----------

    def _call_chat_api(self, system_prompt: str,
                        messages: list[dict],
                        purpose: str = "chat") -> str:
        """Call a generic OpenAI-compatible chat completion endpoint."""
        api_messages = [{"role": "system", "content": system_prompt}] + messages
        response = self._create_chat_completion(
            messages=api_messages,
            max_tokens=400,
            call_type=purpose,
        )
        return response.choices[0].message.content or "..."

    # -- Direct summarization -----------------------------------------

    def _summarize_direct(self, messages: list[dict],
                           requester_name: str) -> SummaryResult:
        """All messages in one call, preferring tool-call structured output."""
        user_prompt = build_summary_prompt(messages, requester_name)

        def call():
            response = self._create_chat_completion(
                max_tokens=8192,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                use_tools=True,
                call_type="summarize",
            )
            return _parse_summary_from_response(response)

        return self._retry_with_backoff(call, "direct summarization")

    # -- Map-Reduce ----------------------------------------------------

    def _summarize_chunk(self, chunk: list[dict], chunk_num: int,
                          total: int, requester_name: str) -> str:
        """Extract key facts from a single chunk as plain text."""
        user_prompt = build_chunk_summary_prompt(
            chunk, chunk_num, total, requester_name
        )

        def call():
            response = self._create_chat_completion(
                max_tokens=1024,
                messages=[
                    {"role": "system", "content": CHUNK_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                call_type="summarize_chunk",
            )
            return response.choices[0].message.content or ""

        return self._retry_with_backoff(call, f"chunk {chunk_num}/{total}")

    def _merge_chunk_summaries(self, chunk_summaries: list[str],
                                requester_name: str) -> SummaryResult:
        """Merge chunk summaries into a final structured result."""
        user_prompt = build_merge_prompt(chunk_summaries, requester_name)

        def call():
            response = self._create_chat_completion(
                max_tokens=8192,
                messages=[
                    {"role": "system", "content": MERGE_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                use_tools=True,
                call_type="summarize_merge",
            )
            return _parse_summary_from_response(response)

        return self._retry_with_backoff(call, "merge chunk summaries")

    # -- Memory consolidation -----------------------------------------

    def consolidate_memory(self, existing_memory: str,
                           new_messages: list[dict]) -> str:
        """Update group memory by incorporating new messages."""
        if not new_messages:
            return existing_memory

        msg_lines = []
        for m in new_messages[-200:]:
            sender = m.get("sender_name", "?")
            content = m.get("content", "")
            if content:
                msg_lines.append(f"{sender}: {content}")

        if not msg_lines:
            return existing_memory

        existing_display = existing_memory if existing_memory else "（暂无，这是第一次整理记忆）"
        escaped_memory = existing_display.replace("{", "{{").replace("}", "}}")
        escaped_msgs = "\n".join(msg_lines).replace("{", "{{").replace("}", "}}")

        system_prompt = MEMORY_CONSOLE_PROMPT.format(
            existing_memory=escaped_memory,
            new_messages=escaped_msgs,
        )

        def call():
            response = self._create_chat_completion(
                max_tokens=2048,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": "请输出更新后的完整记忆日记。"},
                ],
                call_type="memory",
            )
            text = response.choices[0].message.content or ""
            if len(text) > 2000:
                text = text[:2000]
            return text.strip()

        try:
            return self._retry_with_backoff(call, "memory consolidation")
        except RuntimeError as e:
            logger.warning("Memory consolidation failed: %s", e)
            return existing_memory
