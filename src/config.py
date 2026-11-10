"""Configuration loading from .env file."""

import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote

from dotenv import load_dotenv

from src.utils.ai_compat import (
    OPENAI_COMPATIBLE_BASE_URL,
    normalize_ai_backend as _normalize_ai_backend,
    normalize_openai_base_url,
)


def _decode_wechat_groups(raw: str) -> str:
    """Decode URL-encoded group names from .env WECHAT_GROUPS value.

    We store each group name URL-encoded (via encodeURIComponent / urllib.parse.quote)
    so that commas, equals signs, and newlines in real group names don't break the
    .env format or our comma-separated delimiter.  This function reverses that encoding
    with a fallback: if decoding a chunk doesn't change it (or raises), the original
    is kept — for backward compatibility with old unencoded .env files.

    "*" still means every group (legacy configs), while an empty value means
    no groups at all — group participation is an explicit checklist in the UI.
    """
    if not raw or not raw.strip():
        return ""
    if raw.strip() == "*":
        return "*"
    decoded = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            d = unquote(chunk)
            decoded.append(d)
        except Exception:
            decoded.append(chunk)
    return ",".join(decoded) if decoded else "*"


def _decode_wechat_friends(raw: str) -> str:
    """Decode URL-encoded friend names from .env WECHAT_FRIENDS value.

    Unlike WECHAT_GROUPS, an empty value means "no friends" (not "*"):
    friends are auto-replied only when explicitly selected in the UI.
    """
    if not raw or not raw.strip():
        return ""
    return _decode_wechat_groups(raw)


def _sanitize_display_name(name: str) -> str:
    """Remove only truly dangerous characters from a display name.

    This preserves the user's actual name (including quotes, braces, etc.)
    and relies on *usage-point escaping* (``repr()`` in logs, ``_esc()``
    in ``str.format()`` calls) to prevent injection at each call site.

    Only stripped:
    - Control characters (CR/LF → log-line injection)
    - Leading/trailing whitespace + quotes (almost certainly accidental)
    - Excessive length (> 128 chars)
    """
    if not name:
        return "群聊小助手"

    # 1. Strip control chars (except space) — prevents log-line injection
    name = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", name)

    # 2. Collapse whitespace and strip
    name = re.sub(r"\s+", " ", name).strip()

    # 3. Truncate to reasonable length
    if len(name) > 128:
        name = name[:128]

    # 4. Fallback
    if not name:
        return "群聊小助手"

    return name


def _resolve_project_root() -> Path:
    app_home = os.getenv("WEBOT_APP_HOME", "").strip()
    if app_home:
        return Path(app_home).expanduser().resolve()

    # In a PyInstaller EXE, __file__ resolves inside the temp extraction dir.
    # We want writable data (.env, data/*) in the EXE directory, not in the temp dir.
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


PROJECT_ROOT = _resolve_project_root()


def _clean_path_value(raw: str | Path | None) -> str:
    """Normalize a path-like config value without touching path separators."""
    if raw is None:
        return ""
    return os.path.expandvars(str(raw).strip().strip('"').strip("'"))


def resolve_webot_data_dir(raw: str | Path | None = None) -> Path:
    """Return the effective directory for WeChatBot-owned runtime data.

    ``WEBOT_DATA_DIR`` is intentionally separate from ``WECHAT_DATA_DIR``:
    the former stores files created by WeChatBot itself, while the latter points
    at WeChat's own account data directory.
    """
    value = _clean_path_value(
        os.getenv("WEBOT_DATA_DIR", "").strip() if raw is None else raw
    )
    app_home = _clean_path_value(os.getenv("WEBOT_APP_HOME", ""))
    base_dir = Path(app_home).expanduser().resolve() if app_home else PROJECT_ROOT
    data_dir = Path(value).expanduser() if value else base_dir / "data"
    if not data_dir.is_absolute():
        data_dir = base_dir / data_dir
    return data_dir.resolve()


def get_webot_data_dir() -> Path:
    """Return the current WeChatBot-owned data directory from environment."""
    return resolve_webot_data_dir()


def webot_data_path(*parts: str | Path) -> Path:
    """Return a path under the configured WeChatBot data directory."""
    return get_webot_data_dir().joinpath(*parts)


def resolve_webot_storage_path(
    raw: str | Path | None,
    legacy_default: str,
) -> Path:
    """Resolve a configurable WeChatBot-owned file path.

    Legacy defaults such as ``data/messages.db`` and ``data/bot.log`` are
    treated as relative to ``WEBOT_DATA_DIR`` so old .env files automatically
    follow the new data directory.  Any other explicit path remains an override.
    """
    value = _clean_path_value(raw)
    legacy = _clean_path_value(legacy_default)

    def _norm(path_value: str) -> str:
        return path_value.replace("\\", "/").lstrip("./")

    if not value or _norm(value) == _norm(legacy):
        legacy_path = Path(legacy)
        parts = legacy_path.parts
        if parts and parts[0].lower() == "data":
            parts = parts[1:]
        return webot_data_path(*parts)

    path = Path(value).expanduser()
    if not path.is_absolute():
        app_home = _clean_path_value(os.getenv("WEBOT_APP_HOME", ""))
        base_dir = Path(app_home).expanduser().resolve() if app_home else PROJECT_ROOT
        path = base_dir / path
    return path.resolve()


def find_env_file() -> Path | None:
    """Find the .env file using a consistent search order.

    Order: WEBOT_ENV_FILE override → EXE directory (frozen) → project root → current working directory.
    Returns the Path if found, or None if no .env exists anywhere.
    """
    explicit_env = os.getenv("WEBOT_ENV_FILE", "").strip()
    if explicit_env:
        explicit_path = Path(explicit_env).expanduser()
        if explicit_path.exists():
            return explicit_path

    locations = [
        PROJECT_ROOT / ".env",
        Path.cwd() / ".env",
    ]
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        locations.insert(0, exe_dir / ".env")

    for loc in locations:
        if loc.exists():
            return loc
    return None


_env_path = find_env_file()

if _env_path:
    load_dotenv(_env_path)
else:
    load_dotenv()

# Log which .env was loaded (helpful for debugging EXE packaging issues)
import logging as _logging
_log = _logging.getLogger(__name__)
if _env_path:
    _log.info("Loaded .env from: %s", _env_path)
else:
    _search_locations = [
        PROJECT_ROOT / ".env",
        Path.cwd() / ".env",
    ]
    if getattr(sys, "frozen", False):
        _search_locations.insert(0, Path(sys.executable).resolve().parent / ".env")
    _log.warning(
        ".env not found in any search path (%s). Using defaults.",
        ", ".join(str(p) for p in _search_locations),
    )


@dataclass
class BotConfig:
    """All configuration for the WeChat summarizer bot."""

    # === AI protocol/backend ===
    # "openai_compatible" (Chat Completions) or "claude" (Messages).
    # "deepseek" is accepted as a legacy OpenAI-compatible preset.
    ai_backend: str = "openai_compatible"

    # === Claude (Anthropic) ===
    anthropic_api_key: str = ""
    anthropic_base_url: str = "https://api.anthropic.com"
    summarize_model: str = ""

    # === DeepSeek ===
    deepseek_api_key: str = ""
    deepseek_model: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"

    # === OpenAI-compatible ===
    openai_api_key: str = ""
    openai_base_url: str = OPENAI_COMPATIBLE_BASE_URL
    openai_model: str = ""

    # === WeChat Backend ===
    wechat_backend: str = "wcdb"
    # Comma-separated group names to monitor. "*" = auto-discover all groups.
    wechat_groups: str = "*"
    # Comma-separated friend names for 1-on-1 AI chat.  Empty = no friends
    # are auto-replied; "*" = all discovered friends.  Selected friends get
    # an automatic AI reply to every text message they send.
    wechat_friends: str = ""
    # AI conversation switches.  Disabling one only stops chat replies in
    # that context; summaries, image generation and other features are
    # unaffected.
    group_chat_enabled: bool = True
    friend_chat_enabled: bool = True
    # Custom WeChat data directory. Leave empty to auto-detect from Documents.
    # Set to the parent directory containing wxid_* folders (e.g. D:\WeChatData).
    wechat_data_dir: str = ""

    # === WeChatBot Data Storage ===
    # Custom directory for files created by WeChatBot itself (SQLite DB, logs,
    # nicknames, welcome templates, caches).  Leave empty to use ./data.
    webot_data_dir: str = "data"

    # === Bot Identity ===
    bot_display_name: str = "群聊小助手"
    # Admin wxid (can manage nicknames and bot settings)
    admin_wxid: str = ""

    # === Trigger Keywords ===
    trigger_keywords: list[str] = field(default_factory=lambda: [
        "总结一下", "之前发了什么", "错过了什么", "summarize",
        "what did i miss", "聊天总结", "帮我总结", "前面说了什么",
        "说了啥", "发生了什么",
    ])

    # === Summarization ===
    summarize_enabled: bool = True
    fallback_window_hours: int = 8

    # === Feishu / Lark Export ===
    feishu_export_enabled: bool = False
    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    # knowledge, spreadsheet, bitable, or docx
    feishu_export_mode: str = "knowledge"
    feishu_export_window_hours: int = 8
    feishu_auto_sync_enabled: bool = False
    feishu_auto_sync_min_messages: int = 20
    feishu_auto_sync_cooldown_sec: int = 1800
    feishu_knowledge_base_name: str = "webot 群聊沉淀"
    feishu_knowledge_folder_token: str = ""
    feishu_export_trigger_keywords: list[str] = field(default_factory=lambda: [
        "同步到飞书", "导出到飞书", "写到飞书", "沉淀到飞书",
    ])
    feishu_spreadsheet_token: str = ""
    feishu_spreadsheet_range: str = "Sheet1!A:H"
    feishu_bitable_app_token: str = ""
    feishu_bitable_table_id: str = ""
    feishu_doc_folder_token: str = ""

    # === Database ===
    db_path: str = "data/messages.db"

    # === Fun Features ===
    # @抽签 — draw a fortune lot (大吉/中吉/小吉/末吉/凶)
    fun_enabled: bool = True

    # === Proactive Participation ===
    # Master switch — enable autonomous chat participation without @mention
    proactive_enabled: bool = False
    # Rate thresholds for each mode (msgs/min).  When the message rate
    # exceeds a threshold, the bot enters that mode.  Calibrate these
    # by running:  python tools/analyze_chat_rhythm.py
    proactive_rate_window_sec: int = 120  # rate calculation window
    proactive_rate_quiet: float = 1.5     # SLEEP → QUIET  boundary
    proactive_rate_casual: float = 4.0    # QUIET → CASUAL boundary
    proactive_rate_lively: float = 6.5    # CASUAL → LIVELY boundary
    proactive_rate_burst: float = 8.5     # LIVELY → BURST  boundary

    # === Welcome New Member ===
    # Master switch — automatically send a welcome message when a new
    # member joins a group chat.  Welcome templates and per-group settings
    # are stored in the configured WeChatBot data directory.
    welcome_enabled: bool = False

    # === Sticky Mention ===
    # When a user sends @bot with no message text, enter sticky listening
    # mode.  The user's next message in the same group is treated as if it
    # were @mentioned (one-shot).  Set enabled=false to disable entirely.
    sticky_mention_enabled: bool = True
    sticky_mention_ttl_sec: int = 60  # max wait for follow-up message

    # === Group Todo ===
    # Master switch — @bot mention triggers todo management commands.
    todo_enabled: bool = True
    # Comma-separated group names where todo is active. "*" = all groups.
    todo_groups: list[str] = field(default_factory=lambda: ["*"])
    todo_max_per_group: int = 50           # max active todos per group (1-200)
    todo_completed_retention_days: int = 30  # auto-clean completed (0=forever)
    todo_deleted_retention_days: int = 30    # auto-clean deleted (0=forever)
    todo_add_keywords: list[str] = field(default_factory=lambda: [
        "记一下", "添加待办", "新建待办", "帮我记", "待办",
    ])
    todo_complete_keywords: list[str] = field(default_factory=lambda: [
        "搞定", "做完了", "完成", "完成了", "done",
    ])
    todo_delete_keywords: list[str] = field(default_factory=lambda: [
        "删掉", "删除", "取消", "不要了",
    ])

    # === Tuning ===
    poll_interval_sec: float = 1.0
    dedup_window_sec: int = 60
    max_messages_for_summary: int = 5000
    chunk_size: int = 400

    # === Logging ===
    log_level: str = "INFO"
    log_file: str = "data/bot.log"

    # === Voice Recognition ===
    # Master switch (default off — user must opt in)
    voice_asr_enabled: bool = False
    # "local_whisper" (free, offline) | "openai_whisper" (cloud, $0.006/min)
    voice_asr_backend: str = "local_whisper"
    voice_asr_language: str = "zh"
    # OpenAI Whisper API
    voice_openai_api_key: str = ""
    voice_openai_base_url: str = ""
    # Local Whisper model size: tiny / base / small / medium
    voice_local_model: str = "small"
    # Convert traditional Chinese → simplified (opencc t2s)
    voice_asr_to_simplified: bool = True

    # === Image Generation (文生图) ===
    # Master switch (default off — user must opt in).
    # When enabled, @bot + an image-generation intent keyword triggers
    # the configured Images API and the result is pasted into the chat.
    image_gen_enabled: bool = False
    # "openai_images" (/v1/images/generations) | "google_gemini_image" | "dashscope_qwen"
    image_gen_protocol: str = "openai_images"
    # Image generation API credentials.
    image_gen_api_key: str = ""
    image_gen_base_url: str = ""
    # Selected image model id (from the "获取模型" list)
    image_gen_model: str = ""
    # Optional image size like "1024x1024"; empty = provider default
    image_gen_size: str = ""
    # Intent keywords — an @mention whose text contains any of these
    # is treated as an image-generation request.
    image_gen_keywords: list[str] = field(default_factory=lambda: [
        "画一张", "画一个", "画一幅", "画一只", "画个", "帮我画",
        "生成一张", "生成一幅", "生成图片", "生图", "来一张图", "画出来",
    ])


def _validate_config(kwargs: dict) -> None:
    """Validate numeric config values.  Prints clear errors and exits on bad values."""
    errors: list[str] = []

    # poll_interval_sec
    poll_interval_sec = kwargs.get("poll_interval_sec", 1.0)
    if poll_interval_sec < 0.1:
        errors.append(
            f"POLL_INTERVAL_SEC must be >= 0.1, got {poll_interval_sec}"
        )

    # chunk_size
    chunk_size = kwargs.get("chunk_size", 400)
    if not (10 <= chunk_size <= 1000):
        errors.append(
            f"CHUNK_SIZE must be between 10 and 1000, got {chunk_size}"
        )

    # max_retries (optional, used by some backends)
    if "max_retries" in kwargs:
        max_retries = kwargs.get("max_retries")
        if not (1 <= max_retries <= 10):
            errors.append(
                f"MAX_RETRIES must be between 1 and 10, got {max_retries}"
            )

    # max_messages_for_summary
    max_messages_for_summary = kwargs.get("max_messages_for_summary", 5000)
    if max_messages_for_summary < 10:
        errors.append(
            f"MAX_MESSAGES_FOR_SUMMARY must be >= 10, got {max_messages_for_summary}"
        )

    # fallback_window_hours
    fallback_window_hours = kwargs.get("fallback_window_hours", 8)
    if fallback_window_hours < 1:
        errors.append(
            f"FALLBACK_WINDOW_HOURS must be >= 1, got {fallback_window_hours}"
        )

    # dedup_window_sec
    dedup_window_sec = kwargs.get("dedup_window_sec", 60)
    if dedup_window_sec < 10:
        errors.append(
            f"DEDUP_WINDOW_SEC must be >= 10, got {dedup_window_sec}"
        )

    # sticky_mention_ttl_sec
    sticky_mention_ttl_sec = kwargs.get("sticky_mention_ttl_sec", 60)
    if not (10 <= sticky_mention_ttl_sec <= 300):
        errors.append(
            f"STICKY_MENTION_TTL_SEC must be between 10 and 300, "
            f"got {sticky_mention_ttl_sec}"
        )

    # proactive_rate_window_sec
    proactive_rate_window_sec = kwargs.get("proactive_rate_window_sec", 120)
    if proactive_rate_window_sec < 30:
        errors.append(
            f"PROACTIVE_RATE_WINDOW_SEC must be >= 30, got {proactive_rate_window_sec}"
        )

    # proactive_rate thresholds: all > 0 and in strict ascending order
    quiet = kwargs.get("proactive_rate_quiet", 1.5)
    casual = kwargs.get("proactive_rate_casual", 4.0)
    lively = kwargs.get("proactive_rate_lively", 6.5)
    burst = kwargs.get("proactive_rate_burst", 8.5)

    rate_names = ("quiet", "casual", "lively", "burst")
    rate_values = (quiet, casual, lively, burst)

    if any(v <= 0 for v in rate_values):
        errors.append(
            "All PROACTIVE_RATE_* values must be > 0, got: "
            + ", ".join(f"{n}={v}" for n, v in zip(rate_names, rate_values))
        )

    if not (quiet < casual < lively < burst):
        errors.append(
            "PROACTIVE_RATE_* values must be in strict ascending order "
            "(quiet < casual < lively < burst), got: "
            + ", ".join(f"{n}={v}" for n, v in zip(rate_names, rate_values))
        )

    # feishu_export_mode
    feishu_export_mode = kwargs.get("feishu_export_mode", "knowledge")
    if feishu_export_mode not in ("knowledge", "spreadsheet", "bitable", "docx"):
        errors.append(
            "FEISHU_EXPORT_MODE must be one of knowledge, spreadsheet, bitable, docx, "
            f"got {feishu_export_mode}"
        )

    # feishu_export_window_hours
    feishu_export_window_hours = kwargs.get("feishu_export_window_hours", 8)
    if not (1 <= feishu_export_window_hours <= 168):
        errors.append(
            "FEISHU_EXPORT_WINDOW_HOURS must be between 1 and 168, "
            f"got {feishu_export_window_hours}"
        )

    feishu_auto_sync_min_messages = kwargs.get("feishu_auto_sync_min_messages", 20)
    if not (1 <= feishu_auto_sync_min_messages <= 500):
        errors.append(
            "FEISHU_AUTO_SYNC_MIN_MESSAGES must be between 1 and 500, "
            f"got {feishu_auto_sync_min_messages}"
        )

    feishu_auto_sync_cooldown_sec = kwargs.get("feishu_auto_sync_cooldown_sec", 1800)
    if not (60 <= feishu_auto_sync_cooldown_sec <= 86400):
        errors.append(
            "FEISHU_AUTO_SYNC_COOLDOWN_SEC must be between 60 and 86400, "
            f"got {feishu_auto_sync_cooldown_sec}"
        )

    if errors:
        msg = "配置值无效:\n" + "\n".join(f"  - {err}" for err in errors)
        raise RuntimeError(msg)


def load_config() -> BotConfig:
    """Load configuration from environment variables.

    Returns a validated BotConfig instance.
    Raises RuntimeError if required configuration is missing.
    """
    ai_backend = _normalize_ai_backend(os.getenv("AI_BACKEND", "openai_compatible"))
    if ai_backend not in ("claude", "deepseek", "openai_compatible"):
        raise RuntimeError(
            f"AI_BACKEND must be one of claude, deepseek, openai_compatible; got {ai_backend}"
        )

    # Validate required API keys based on selected backend
    if ai_backend == "deepseek":
        api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
        if not api_key:
            msg = "DEEPSEEK_API_KEY 未设置，请在 .env 文件中配置或通过引导页完成设置"
            raise RuntimeError(msg)
        if not os.getenv("DEEPSEEK_MODEL", "").strip():
            msg = "DEEPSEEK_MODEL 未设置，请先获取并选择一个模型"
            raise RuntimeError(msg)
    elif ai_backend == "claude":
        api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        if not api_key:
            msg = "ANTHROPIC_API_KEY 未设置，请在 .env 文件中配置或通过引导页完成设置"
            raise RuntimeError(msg)
        if not os.getenv("SUMMARIZE_MODEL", "").strip():
            msg = "SUMMARIZE_MODEL 未设置，请先获取并选择一个模型"
            raise RuntimeError(msg)
    elif ai_backend == "openai_compatible":
        if not os.getenv("OPENAI_MODEL", "").strip():
            msg = "OPENAI_MODEL 未设置，请先获取并选择一个模型"
            raise RuntimeError(msg)

    # Parse trigger keywords from comma-separated string
    keywords_str = os.getenv("TRIGGER_KEYWORDS", "").strip()
    trigger_keywords = (
        [kw.strip() for kw in keywords_str.split(",") if kw.strip()]
        if keywords_str
        else None  # let the dataclass default apply
    )
    feishu_keywords_str = os.getenv("FEISHU_EXPORT_TRIGGER_KEYWORDS", "").strip()
    feishu_export_trigger_keywords = (
        [kw.strip() for kw in feishu_keywords_str.split(",") if kw.strip()]
        if feishu_keywords_str
        else None
    )
    todo_add_kw_str = os.getenv("TODO_ADD_KEYWORDS", "").strip()
    todo_add_keywords = (
        [kw.strip() for kw in todo_add_kw_str.split(",") if kw.strip()]
        if todo_add_kw_str else None
    )
    todo_complete_kw_str = os.getenv("TODO_COMPLETE_KEYWORDS", "").strip()
    todo_complete_keywords = (
        [kw.strip() for kw in todo_complete_kw_str.split(",") if kw.strip()]
        if todo_complete_kw_str else None
    )
    todo_delete_kw_str = os.getenv("TODO_DELETE_KEYWORDS", "").strip()
    todo_delete_keywords = (
        [kw.strip() for kw in todo_delete_kw_str.split(",") if kw.strip()]
        if todo_delete_kw_str else None
    )
    image_gen_kw_str = os.getenv("IMAGE_GEN_KEYWORDS", "").strip()
    image_gen_keywords = (
        [kw.strip() for kw in image_gen_kw_str.split(",") if kw.strip()]
        if image_gen_kw_str else None
    )

    kwargs: dict = {
        "ai_backend": ai_backend,
        "anthropic_api_key": os.getenv("ANTHROPIC_API_KEY", "").strip(),
        "anthropic_base_url": os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com").strip(),
        "summarize_model": os.getenv("SUMMARIZE_MODEL", "").strip(),
        "deepseek_api_key": os.getenv("DEEPSEEK_API_KEY", "").strip(),
        "deepseek_base_url": os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip(),
        # deepseek_model handled conditionally below (dataclass default)
        "openai_api_key": os.getenv("OPENAI_API_KEY", "").strip(),
        "openai_base_url": normalize_openai_base_url(
            os.getenv("OPENAI_BASE_URL", OPENAI_COMPATIBLE_BASE_URL)
        ),
        "openai_model": os.getenv("OPENAI_MODEL", "").strip(),
        "wechat_backend": os.getenv("WECHAT_BACKEND", "wcdb").strip(),
        "wechat_groups": _decode_wechat_groups(os.getenv("WECHAT_GROUPS", "*")),
        "wechat_friends": _decode_wechat_friends(os.getenv("WECHAT_FRIENDS", "")),
        "group_chat_enabled": os.getenv("GROUP_CHAT_ENABLED", "true").strip().lower() == "true",
        "friend_chat_enabled": os.getenv("FRIEND_CHAT_ENABLED", "true").strip().lower() == "true",
        "wechat_data_dir": os.getenv("WECHAT_DATA_DIR", "").strip(),
        "webot_data_dir": str(get_webot_data_dir()),
        "bot_display_name": _sanitize_display_name(os.getenv("BOT_DISPLAY_NAME", "群聊小助手")),
        "admin_wxid": os.getenv("ADMIN_WXID", "").strip(),
        "db_path": str(resolve_webot_storage_path(
            os.getenv("DB_PATH", "data/messages.db"),
            "data/messages.db",
        )),
        "poll_interval_sec": float(os.getenv("POLL_INTERVAL_SEC", "1.0")),
        "dedup_window_sec": int(os.getenv("DEDUP_WINDOW_SEC", "60")),
        "max_messages_for_summary": int(os.getenv("MAX_MESSAGES_FOR_SUMMARY", "5000")),
        "chunk_size": int(os.getenv("CHUNK_SIZE", "400")),
        "fallback_window_hours": int(os.getenv("FALLBACK_WINDOW_HOURS", "8")),
        "feishu_export_enabled": os.getenv("FEISHU_EXPORT_ENABLED", "false").strip().lower() == "true",
        "feishu_app_id": os.getenv("FEISHU_APP_ID", "").strip(),
        "feishu_app_secret": os.getenv("FEISHU_APP_SECRET", "").strip(),
        "feishu_export_mode": os.getenv("FEISHU_EXPORT_MODE", "knowledge").strip().lower(),
        "feishu_export_window_hours": int(os.getenv("FEISHU_EXPORT_WINDOW_HOURS", "8")),
        "feishu_auto_sync_enabled": os.getenv("FEISHU_AUTO_SYNC_ENABLED", "false").strip().lower() == "true",
        "feishu_auto_sync_min_messages": int(os.getenv("FEISHU_AUTO_SYNC_MIN_MESSAGES", "20")),
        "feishu_auto_sync_cooldown_sec": int(os.getenv("FEISHU_AUTO_SYNC_COOLDOWN_SEC", "1800")),
        "feishu_knowledge_base_name": os.getenv("FEISHU_KNOWLEDGE_BASE_NAME", "webot 群聊沉淀").strip(),
        "feishu_knowledge_folder_token": os.getenv("FEISHU_KNOWLEDGE_FOLDER_TOKEN", "").strip(),
        "feishu_spreadsheet_token": os.getenv("FEISHU_SPREADSHEET_TOKEN", "").strip(),
        "feishu_spreadsheet_range": os.getenv("FEISHU_SPREADSHEET_RANGE", "Sheet1!A:H").strip(),
        "feishu_bitable_app_token": os.getenv("FEISHU_BITABLE_APP_TOKEN", "").strip(),
        "feishu_bitable_table_id": os.getenv("FEISHU_BITABLE_TABLE_ID", "").strip(),
        "feishu_doc_folder_token": os.getenv("FEISHU_DOC_FOLDER_TOKEN", "").strip(),
        "fun_enabled": os.getenv("FUN_ENABLED", "true").strip().lower() == "true",
        "summarize_enabled": os.getenv("SUMMARIZE_ENABLED", "true").strip().lower() == "true",
        "proactive_enabled": os.getenv("PROACTIVE_ENABLED", "false").strip().lower() == "true",
        # proactive_rate_window_sec handled conditionally below (dataclass default)
        "proactive_rate_quiet": float(os.getenv("PROACTIVE_RATE_QUIET", "1.5")),
        "proactive_rate_casual": float(os.getenv("PROACTIVE_RATE_CASUAL", "4.0")),
        "proactive_rate_lively": float(os.getenv("PROACTIVE_RATE_LIVELY", "6.5")),
        "proactive_rate_burst": float(os.getenv("PROACTIVE_RATE_BURST", "8.5")),
        "welcome_enabled": os.getenv("WELCOME_ENABLED", "false").strip().lower() == "true",
        "sticky_mention_enabled": os.getenv("STICKY_MENTION_ENABLED", "true").strip().lower() == "true",
        "sticky_mention_ttl_sec": int(os.getenv("STICKY_MENTION_TTL_SEC", "60")),
        # Group Todo
        "todo_enabled": os.getenv("TODO_ENABLED", "true").strip().lower() == "true",
        "todo_groups": [g.strip() for g in os.getenv("TODO_GROUPS", "*").split(",") if g.strip()],
        "todo_max_per_group": int(os.getenv("TODO_MAX_PER_GROUP", "50")),
        "todo_completed_retention_days": int(os.getenv("TODO_COMPLETED_RETENTION_DAYS", "30")),
        "todo_deleted_retention_days": int(os.getenv("TODO_DELETED_RETENTION_DAYS", "30")),
        "log_level": os.getenv("LOG_LEVEL", "INFO").strip(),
        "log_file": str(resolve_webot_storage_path(
            os.getenv("LOG_FILE", "data/bot.log"),
            "data/bot.log",
        )),
        # Voice recognition
        "voice_asr_enabled": os.getenv("VOICE_ASR_ENABLED", "false").strip().lower() == "true",
        "voice_asr_backend": os.getenv("VOICE_ASR_BACKEND", "local_whisper").strip(),
        "voice_asr_language": os.getenv("VOICE_ASR_LANGUAGE", "zh").strip(),
        "voice_openai_api_key": os.getenv("VOICE_OPENAI_API_KEY", "").strip(),
        "voice_openai_base_url": os.getenv("VOICE_OPENAI_BASE_URL", "").strip(),
        "voice_local_model": os.getenv("VOICE_LOCAL_MODEL", "small").strip(),
        "voice_asr_to_simplified": os.getenv("VOICE_ASR_TO_SIMPLIFIED", "true").strip().lower() == "true",
        # Image generation (文生图)
        "image_gen_enabled": os.getenv("IMAGE_GEN_ENABLED", "false").strip().lower() == "true",
        "image_gen_protocol": os.getenv("IMAGE_GEN_PROTOCOL", "openai_images").strip() or "openai_images",
        "image_gen_api_key": os.getenv("IMAGE_GEN_API_KEY", "").strip(),
        "image_gen_base_url": os.getenv("IMAGE_GEN_BASE_URL", "").strip(),
        "image_gen_model": os.getenv("IMAGE_GEN_MODEL", "").strip(),
        "image_gen_size": os.getenv("IMAGE_GEN_SIZE", "").strip(),
    }

    deepseek_model = os.getenv("DEEPSEEK_MODEL")
    if deepseek_model is not None:
        kwargs["deepseek_model"] = deepseek_model.strip()

    openai_model = os.getenv("OPENAI_MODEL")
    if openai_model is not None:
        kwargs["openai_model"] = openai_model.strip()

    proactive_rate_window_sec = os.getenv("PROACTIVE_RATE_WINDOW_SEC")
    if proactive_rate_window_sec is not None:
        kwargs["proactive_rate_window_sec"] = int(proactive_rate_window_sec)

    if trigger_keywords is not None:
        kwargs["trigger_keywords"] = trigger_keywords
    if feishu_export_trigger_keywords is not None:
        kwargs["feishu_export_trigger_keywords"] = feishu_export_trigger_keywords
    if todo_add_keywords is not None:
        kwargs["todo_add_keywords"] = todo_add_keywords
    if todo_complete_keywords is not None:
        kwargs["todo_complete_keywords"] = todo_complete_keywords
    if todo_delete_keywords is not None:
        kwargs["todo_delete_keywords"] = todo_delete_keywords
    if image_gen_keywords is not None:
        kwargs["image_gen_keywords"] = image_gen_keywords

    _validate_config(kwargs)

    return BotConfig(**kwargs)


def is_onboarding_done() -> bool:
    """Check if onboarding has been completed without loading full config.

    Uses find_env_file() for consistent .env resolution.
    """
    env_path = find_env_file()
    if env_path and env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("ONBOARDING_DONE="):
                return line.split("=", 1)[1].strip().lower() == "true"
        return False  # .env exists but no ONBOARDING_DONE key
    return False  # No .env found
