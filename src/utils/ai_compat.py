"""Utilities for OpenAI-compatible AI provider configuration."""

from urllib.parse import urlsplit, urlunsplit


OPENAI_COMPATIBLE_BASE_URL = "https://api.openai.com/v1"
OPENAI_COMPATIBLE_LOCAL_API_KEY = "webot-local-compatible"

_OPENAI_ENDPOINT_SUFFIXES = (
    "/chat/completions",
    "/images/generations",
    "/responses",
    "/models",
)


def normalize_ai_backend(raw: str) -> str:
    """Normalize user-facing AI backend aliases to internal identifiers."""
    backend = (raw or "").strip().lower().replace("-", "_")
    aliases = {
        "anthropic": "claude",
        "anthropic_messages": "claude",
        "messages": "claude",
        "openai": "openai_compatible",
        "openai_compat": "openai_compatible",
        "chat_completions": "openai_compatible",
        "chat_completion": "openai_compatible",
        "compatible": "openai_compatible",
        "custom": "openai_compatible",
        "newapi": "openai_compatible",
        "new_api": "openai_compatible",
        "oneapi": "openai_compatible",
        "one_api": "openai_compatible",
        "litellm": "openai_compatible",
        "lite_llm": "openai_compatible",
        "openrouter": "openai_compatible",
        "open_router": "openai_compatible",
    }
    return aliases.get(backend, backend)


def normalize_openai_base_url(raw: str,
                              default: str = OPENAI_COMPATIBLE_BASE_URL) -> str:
    """Return a base URL suitable for OpenAI SDK ``chat.completions`` calls.

    Users often paste either a base URL (``.../v1``) or a complete endpoint
    (``.../v1/chat/completions``).  The OpenAI SDK appends
    ``/chat/completions`` itself, so complete endpoints must be trimmed first.
    """
    value = (raw or "").strip()
    if not value:
        return default

    if "://" not in value:
        lower = value.lower()
        local_prefixes = ("localhost", "127.", "0.0.0.0", "10.", "172.", "192.168.")
        scheme = "http" if lower.startswith(local_prefixes) else "https"
        value = f"{scheme}://{value}"

    parts = urlsplit(value)
    path = parts.path.rstrip("/")
    path_lower = path.lower()
    for suffix in _OPENAI_ENDPOINT_SUFFIXES:
        if path_lower.endswith(suffix):
            path = path[: -len(suffix)].rstrip("/")
            break

    return urlunsplit((
        parts.scheme,
        parts.netloc,
        path or "",
        parts.query,
        "",
    )).rstrip("/")


def openai_api_key_for_client(raw: str) -> str:
    """Return an SDK-safe key, allowing no-auth local compatible services."""
    return (raw or "").strip() or OPENAI_COMPATIBLE_LOCAL_API_KEY
