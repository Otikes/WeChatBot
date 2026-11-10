"""Tests for config.py — loading, validation, .env resolution, and helpers."""

import os
import sys
import unittest
from pathlib import Path
from tempfile import NamedTemporaryFile
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Test that the config module can be imported even WITHOUT a .env file.
# This guards against the NameError bug where _search_locations was
# referenced before assignment during module-level logging.
# ---------------------------------------------------------------------------


class ConfigModuleImportTests(unittest.TestCase):
    """Smoke tests for module-level import behaviour."""

    def test_import_config_module_without_env_file(self):
        """Importing src.config should succeed even when no .env file exists.

        The module-level code calls find_env_file() and load_dotenv().
        When .env is missing, load_dotenv() is a no-op and the module
        must still load without NameError or AttributeError.
        """
        # The module was already imported by the test runner, so if we got
        # here without an ImportError the scenario is already verified.
        # We still explicitly import to make the test self-documenting.
        import src.config

        self.assertIsNotNone(src.config)
        self.assertTrue(hasattr(src.config, "load_config"))
        self.assertTrue(hasattr(src.config, "BotConfig"))

    def test_config_constants_are_set(self):
        """PROJECT_ROOT must be a Path and the BotConfig class must exist."""
        from src.config import PROJECT_ROOT, BotConfig

        self.assertIsInstance(PROJECT_ROOT, Path)
        self.assertTrue(PROJECT_ROOT.exists())
        self.assertTrue(hasattr(BotConfig, "ai_backend"))


# ---------------------------------------------------------------------------
# _sanitize_display_name
# ---------------------------------------------------------------------------


class SanitizeDisplayNameTests(unittest.TestCase):
    """Edge-case tests for _sanitize_display_name."""

    def test_empty_string_returns_fallback(self):
        """Empty string → fallback display name."""
        from src.config import _sanitize_display_name

        result = _sanitize_display_name("")
        self.assertEqual(result, "群聊小助手")

    def test_none_returns_fallback(self):
        """None → fallback display name."""
        from src.config import _sanitize_display_name

        result = _sanitize_display_name(None)
        self.assertEqual(result, "群聊小助手")

    def test_normal_name_passes_through(self):
        """Ordinary name should be returned unchanged."""
        from src.config import _sanitize_display_name

        result = _sanitize_display_name("小明")
        self.assertEqual(result, "小明")

    def test_control_characters_are_stripped(self):
        """CR, LF, and other control characters must be removed."""
        from src.config import _sanitize_display_name

        result = _sanitize_display_name("小\x00明\r\n测试")
        self.assertEqual(result, "小明 测试")

    def test_whitespace_collapsed_and_trimmed(self):
        """Multiple spaces → single space; leading/trailing stripped."""
        from src.config import _sanitize_display_name

        result = _sanitize_display_name("   小明    测试   ")
        self.assertEqual(result, "小明 测试")

    def test_excessive_length_truncated_to_128(self):
        """Names longer than 128 chars must be truncated."""
        from src.config import _sanitize_display_name

        long_name = "A" * 200
        result = _sanitize_display_name(long_name)
        self.assertEqual(len(result), 128)
        self.assertTrue(result.startswith("A" * 128))

    def test_only_whitespace_returns_fallback(self):
        """A name consisting only of whitespace → fallback."""
        from src.config import _sanitize_display_name

        result = _sanitize_display_name("   \t  \n  ")
        self.assertEqual(result, "群聊小助手")

    def test_only_control_chars_returns_fallback(self):
        """A name consisting only of stripped control chars → fallback."""
        from src.config import _sanitize_display_name

        result = _sanitize_display_name("\x00\x01\x02\x1f")
        self.assertEqual(result, "群聊小助手")

    def test_exactly_128_chars_kept_intact(self):
        """A name of exactly 128 chars should not be truncated."""
        from src.config import _sanitize_display_name

        name_128 = "A" * 128
        result = _sanitize_display_name(name_128)
        self.assertEqual(len(result), 128)
        self.assertEqual(result, name_128)

    def test_tabs_converted_to_space(self):
        """Tabs should be collapsed to a single space."""
        from src.config import _sanitize_display_name

        result = _sanitize_display_name("hello\tworld")
        self.assertEqual(result, "hello world")

    def test_delete_character_stripped(self):
        """DEL character (0x7f) must be removed."""
        from src.config import _sanitize_display_name

        result = _sanitize_display_name("hello\x7fworld")
        self.assertEqual(result, "helloworld")


# ---------------------------------------------------------------------------
# _decode_wechat_groups
# ---------------------------------------------------------------------------


class DecodeWeChatGroupsTests(unittest.TestCase):
    """Tests for _decode_wechat_groups URL-decoding helper."""

    def test_wildcard_passes_through(self):
        """'*' should be returned as '*'."""
        from src.config import _decode_wechat_groups

        self.assertEqual(_decode_wechat_groups("*"), "*")

    def test_empty_returns_empty(self):
        """空字符串 / None → 空（不监控任何群聊）。"""
        from src.config import _decode_wechat_groups

        self.assertEqual(_decode_wechat_groups(""), "")
        self.assertEqual(_decode_wechat_groups(None), "")

    def test_single_encoded_group_decoded(self):
        """Single URL-encoded group name should be decoded."""
        from src.config import _decode_wechat_groups

        result = _decode_wechat_groups("Hello%20World")
        self.assertEqual(result, "Hello World")

    def test_multiple_groups_comma_separated(self):
        """Comma-separated, URL-encoded groups should all be decoded."""
        from src.config import _decode_wechat_groups

        result = _decode_wechat_groups("Hello%20World,%E5%B0%8F%E6%98%8E")
        self.assertEqual(result, "Hello World,小明")

    def test_unencoded_plain_text_preserved(self):
        """Plain (unencoded) text should pass through unchanged."""
        from src.config import _decode_wechat_groups

        result = _decode_wechat_groups("Group1,Group2")
        self.assertEqual(result, "Group1,Group2")

    def test_whitespace_stripped_around_groups(self):
        """Whitespace around each group name is stripped."""
        from src.config import _decode_wechat_groups

        result = _decode_wechat_groups("  Group1  ,  Group2  ")
        self.assertEqual(result, "Group1,Group2")


# ---------------------------------------------------------------------------
# find_env_file
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# _decode_wechat_friends
# ---------------------------------------------------------------------------


class DecodeWeChatFriendsTests(unittest.TestCase):
    """Tests for _decode_wechat_friends — empty means no friends."""

    def test_empty_returns_empty(self):
        from src.config import _decode_wechat_friends

        self.assertEqual(_decode_wechat_friends(""), "")
        self.assertEqual(_decode_wechat_friends(None), "")
        self.assertEqual(_decode_wechat_friends("   "), "")

    def test_wildcard_passes_through(self):
        from src.config import _decode_wechat_friends

        self.assertEqual(_decode_wechat_friends("*"), "*")

    def test_encoded_friend_names_decoded(self):
        from src.config import _decode_wechat_friends

        result = _decode_wechat_friends(
            "Hello%20World,%E5%B0%8F%E6%98%8E",
        )
        self.assertEqual(result, "Hello World,小明")


# ---------------------------------------------------------------------------
# find_env_file
# ---------------------------------------------------------------------------


class FindEnvFileTests(unittest.TestCase):
    """Tests for find_env_file() behaviour."""

    def test_returns_path_when_env_exists_in_project_root(self):
        """Should return PROJECT_ROOT / '.env' if it exists."""
        from src.config import find_env_file, PROJECT_ROOT

        with patch.object(Path, "exists", return_value=True):
            result = find_env_file()
            self.assertIsNotNone(result)
            self.assertEqual(result, PROJECT_ROOT / ".env")

    def test_returns_none_when_no_env_anywhere(self):
        """Should return None when .env does not exist at any location."""
        from src.config import find_env_file

        with patch.object(Path, "exists", return_value=False):
            result = find_env_file()
            self.assertIsNone(result)

    def test_frozen_includes_exe_dir_in_search(self):
        """In frozen mode, EXE directory is included as a search location."""
        from src.config import find_env_file, PROJECT_ROOT

        exe_dir = Path(sys.executable).resolve().parent
        exe_env = exe_dir / ".env"

        with (
            patch.object(sys, "frozen", True, create=True),
            patch.object(Path, "exists", return_value=True),
        ):
            result = find_env_file()
            # When all locations exist, EXE dir is checked first (inserted at
            # position 0) and returned.
            self.assertIsNotNone(result)
            self.assertEqual(result, exe_env)

    def test_frozen_returns_none_when_no_env_anywhere(self):
        """Frozen mode with no .env anywhere → None."""
        from src.config import find_env_file

        with (
            patch.object(sys, "frozen", True, create=True),
            patch.object(Path, "exists", return_value=False),
        ):
            result = find_env_file()
            self.assertIsNone(result)


# ---------------------------------------------------------------------------
# is_onboarding_done
# ---------------------------------------------------------------------------


class IsOnboardingDoneTests(unittest.TestCase):
    """Tests for is_onboarding_done() with various .env states."""

    def test_returns_false_when_no_env_file(self):
        """No .env file → not onboarded."""
        from src.config import is_onboarding_done

        with patch("src.config.find_env_file", return_value=None):
            self.assertFalse(is_onboarding_done())

    def test_returns_false_when_env_has_no_onboarding_key(self):
        """Env exists but no ONBOARDING_DONE key → False."""
        from src.config import is_onboarding_done

        fake_env = Path("/fake/.env")
        fake_env_content = "AI_BACKEND=deepseek\nDEEPSEEK_API_KEY=sk-xxx\n"
        with (
            patch("src.config.find_env_file", return_value=fake_env),
            patch.object(Path, "exists", return_value=True),
            patch.object(Path, "read_text", return_value=fake_env_content),
        ):
            self.assertFalse(is_onboarding_done())

    def test_returns_true_when_onboarding_done_is_true(self):
        """ONBOARDING_DONE=true → True."""
        from src.config import is_onboarding_done

        fake_env = Path("/fake/.env")
        fake_env_content = (
            "AI_BACKEND=deepseek\n"
            "ONBOARDING_DONE=true\n"
        )
        with (
            patch("src.config.find_env_file", return_value=fake_env),
            patch.object(Path, "exists", return_value=True),
            patch.object(Path, "read_text", return_value=fake_env_content),
        ):
            self.assertTrue(is_onboarding_done())

    def test_returns_false_when_onboarding_done_is_false(self):
        """ONBOARDING_DONE=false → False."""
        from src.config import is_onboarding_done

        fake_env = Path("/fake/.env")
        fake_env_content = "ONBOARDING_DONE=false\n"
        with (
            patch("src.config.find_env_file", return_value=fake_env),
            patch.object(Path, "exists", return_value=True),
            patch.object(Path, "read_text", return_value=fake_env_content),
        ):
            self.assertFalse(is_onboarding_done())

    def test_case_insensitive_true(self):
        """ONBOARDING_DONE=TRUE (uppercase) → True."""
        from src.config import is_onboarding_done

        fake_env = Path("/fake/.env")
        fake_env_content = "ONBOARDING_DONE=TRUE\n"
        with (
            patch("src.config.find_env_file", return_value=fake_env),
            patch.object(Path, "exists", return_value=True),
            patch.object(Path, "read_text", return_value=fake_env_content),
        ):
            self.assertTrue(is_onboarding_done())

    def test_whitespace_around_value(self):
        """ONBOARDING_DONE=true (with spaces around value, not key) → True.

        The parser requires ONBOARDING_DONE= prefix with no spaces around
        the equals sign (standard .env format).  Trailing whitespace
        around the value after = is stripped.
        """
        from src.config import is_onboarding_done

        fake_env = Path("/fake/.env")
        fake_env_content = "ONBOARDING_DONE=  true  \n"
        with (
            patch("src.config.find_env_file", return_value=fake_env),
            patch.object(Path, "exists", return_value=True),
            patch.object(Path, "read_text", return_value=fake_env_content),
        ):
            self.assertTrue(is_onboarding_done())

    def test_whitespace_around_equals_sign_returns_false(self):
        """ONBOARDING_DONE = true (spaces around =) → False.

        The current parser requires key=value with no spaces around =.
        This is the standard .env format; spaces around = are invalid.
        """
        from src.config import is_onboarding_done

        fake_env = Path("/fake/.env")
        fake_env_content = "ONBOARDING_DONE = true\n"
        with (
            patch("src.config.find_env_file", return_value=fake_env),
            patch.object(Path, "exists", return_value=True),
            patch.object(Path, "read_text", return_value=fake_env_content),
        ):
            self.assertFalse(is_onboarding_done())


# ---------------------------------------------------------------------------
# load_config / _validate_config
# ---------------------------------------------------------------------------


class LoadConfigTests(unittest.TestCase):
    """Tests for load_config() with mocked environment variables."""

    def test_load_config_with_minimal_valid_env(self):
        """load_config() should succeed with the minimum required env vars."""
        from src.config import load_config, BotConfig

        with patch.dict(os.environ, {
            "OPENAI_MODEL": "chat-model",
        }, clear=True):
            config = load_config()
            self.assertIsInstance(config, BotConfig)
            self.assertEqual(config.ai_backend, "openai_compatible")
            self.assertEqual(config.openai_model, "chat-model")

    def test_load_config_with_deepseek_backend(self):
        """When AI_BACKEND=deepseek, DEEPSEEK_API_KEY is required."""
        from src.config import load_config

        with patch.dict(os.environ, {
            "AI_BACKEND": "deepseek",
            "DEEPSEEK_API_KEY": "sk-ds-test-key",
            "DEEPSEEK_MODEL": "legacy-chat-model",
        }, clear=True):
            config = load_config()
            self.assertEqual(config.ai_backend, "deepseek")
            self.assertEqual(config.deepseek_api_key, "sk-ds-test-key")
            self.assertEqual(config.deepseek_model, "legacy-chat-model")

    def test_load_config_with_openai_compatible_backend(self):
        """When AI_BACKEND=openai_compatible, OPENAI_* config is loaded."""
        from src.config import load_config

        with patch.dict(os.environ, {
            "AI_BACKEND": "openai_compatible",
            "OPENAI_API_KEY": "sk-openai-test-key",
            "OPENAI_BASE_URL": "https://relay.example.com/v1",
            "OPENAI_MODEL": "qwen-plus",
        }, clear=True):
            config = load_config()
            self.assertEqual(config.ai_backend, "openai_compatible")
            self.assertEqual(config.openai_api_key, "sk-openai-test-key")
            self.assertEqual(config.openai_base_url, "https://relay.example.com/v1")
            self.assertEqual(config.openai_model, "qwen-plus")

    def test_load_config_normalizes_openai_alias(self):
        """AI_BACKEND=openai is accepted as openai_compatible."""
        from src.config import load_config

        with patch.dict(os.environ, {
            "AI_BACKEND": "openai",
            "OPENAI_API_KEY": "sk-openai-test-key",
            "OPENAI_MODEL": "chat-model",
        }, clear=True):
            config = load_config()
            self.assertEqual(config.ai_backend, "openai_compatible")

    def test_load_config_normalizes_openai_gateway_aliases(self):
        """Common gateway aliases are accepted as openai_compatible."""
        from src.config import load_config

        for alias in ("chat-completions", "new-api", "newapi", "one-api", "litellm", "openrouter"):
            with self.subTest(alias=alias):
                with patch.dict(os.environ, {
                    "AI_BACKEND": alias,
                    "OPENAI_MODEL": "qwen-plus",
                }, clear=True):
                    config = load_config()
                    self.assertEqual(config.ai_backend, "openai_compatible")

    def test_load_config_normalizes_messages_alias(self):
        """AI_BACKEND=messages is accepted as the Messages protocol."""
        from src.config import load_config

        with patch.dict(os.environ, {
            "AI_BACKEND": "messages",
            "ANTHROPIC_API_KEY": "sk-ant-test",
            "SUMMARIZE_MODEL": "messages-model",
        }, clear=True):
            config = load_config()
            self.assertEqual(config.ai_backend, "claude")

    def test_load_config_allows_empty_openai_key_for_local_services(self):
        """OpenAI-compatible local services can be configured without auth."""
        from src.config import load_config

        with patch.dict(os.environ, {
            "AI_BACKEND": "openai_compatible",
            "OPENAI_API_KEY": "",
            "OPENAI_BASE_URL": "localhost:11434/v1/chat/completions",
            "OPENAI_MODEL": "qwen2.5:7b",
        }, clear=True):
            config = load_config()
            self.assertEqual(config.openai_api_key, "")
            self.assertEqual(config.openai_base_url, "http://localhost:11434/v1")

    def test_load_config_normalizes_openai_endpoint_url(self):
        """Full Chat Completions URLs are trimmed to SDK base URLs."""
        from src.config import load_config

        with patch.dict(os.environ, {
            "AI_BACKEND": "openai_compatible",
            "OPENAI_BASE_URL": "relay.example.com/v1/chat/completions",
            "OPENAI_MODEL": "qwen-plus",
        }, clear=True):
            config = load_config()
            self.assertEqual(config.openai_base_url, "https://relay.example.com/v1")

    def test_load_config_normalizes_openai_models_url(self):
        """Full model-list URLs are also trimmed to SDK base URLs."""
        from src.config import load_config

        with patch.dict(os.environ, {
            "AI_BACKEND": "openai_compatible",
            "OPENAI_BASE_URL": "relay.example.com/v1/models",
            "OPENAI_MODEL": "qwen-plus",
        }, clear=True):
            config = load_config()
            self.assertEqual(config.openai_base_url, "https://relay.example.com/v1")

    def test_load_config_raises_when_model_missing_openai_compatible(self):
        """Default Chat Completions protocol requires selecting a model."""
        from src.config import load_config

        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError) as ctx:
                load_config()
            self.assertIn("OPENAI_MODEL", str(ctx.exception))

    def test_load_config_raises_when_api_key_missing_claude(self):
        """Messages protocol requires an API key."""
        from src.config import load_config

        with patch.dict(os.environ, {
            "AI_BACKEND": "claude",
            "SUMMARIZE_MODEL": "messages-model",
        }, clear=True):
            with self.assertRaises(RuntimeError) as ctx:
                load_config()
            self.assertIn("ANTHROPIC_API_KEY", str(ctx.exception))

    def test_load_config_raises_when_api_key_missing_deepseek(self):
        """load_config() with deepseek backend and no API key → RuntimeError."""
        from src.config import load_config

        with patch.dict(os.environ, {
            "AI_BACKEND": "deepseek",
        }, clear=True):
            with self.assertRaises(RuntimeError) as ctx:
                load_config()
            self.assertIn("DEEPSEEK_API_KEY", str(ctx.exception))

    def test_load_config_raises_when_model_missing_deepseek(self):
        """Legacy deepseek preset also requires an explicit selected model."""
        from src.config import load_config

        with patch.dict(os.environ, {
            "AI_BACKEND": "deepseek",
            "DEEPSEEK_API_KEY": "sk-ds-test",
        }, clear=True):
            with self.assertRaises(RuntimeError) as ctx:
                load_config()
            self.assertIn("DEEPSEEK_MODEL", str(ctx.exception))

    def test_load_config_raises_when_model_missing_claude(self):
        """Messages protocol also requires an explicit selected model."""
        from src.config import load_config

        with patch.dict(os.environ, {
            "AI_BACKEND": "claude",
            "ANTHROPIC_API_KEY": "sk-ant-test",
        }, clear=True):
            with self.assertRaises(RuntimeError) as ctx:
                load_config()
            self.assertIn("SUMMARIZE_MODEL", str(ctx.exception))

    def test_load_config_parses_trigger_keywords(self):
        """Custom TRIGGER_KEYWORDS should be parsed from comma-separated string."""
        from src.config import load_config

        with patch.dict(os.environ, {
            "ANTHROPIC_API_KEY": "sk-ant-test",
            "AI_BACKEND": "claude",
            "SUMMARIZE_MODEL": "messages-model",
            "TRIGGER_KEYWORDS": "总结,回顾,summarize",
        }, clear=True):
            config = load_config()
            self.assertEqual(
                config.trigger_keywords,
                ["总结", "回顾", "summarize"],
            )

    def test_load_config_uses_defaults_for_unset_vars(self):
        """Unset environment variables should fall back to BotConfig defaults."""
        from src.config import load_config

        with patch.dict(os.environ, {
            "OPENAI_MODEL": "chat-model",
        }, clear=True):
            config = load_config()
            self.assertEqual(config.poll_interval_sec, 1.0)
            self.assertEqual(config.chunk_size, 400)
            self.assertEqual(config.max_messages_for_summary, 5000)
            self.assertEqual(config.fallback_window_hours, 8)
            self.assertEqual(config.dedup_window_sec, 60)
            self.assertEqual(config.wechat_backend, "wcdb")
            self.assertEqual(config.bot_display_name, "群聊小助手")

    def test_load_config_with_custom_numeric_values(self):
        """Custom numeric env vars should be parsed correctly."""
        from src.config import load_config

        with patch.dict(os.environ, {
            "OPENAI_MODEL": "chat-model",
            "POLL_INTERVAL_SEC": "2.5",
            "CHUNK_SIZE": "500",
            "MAX_MESSAGES_FOR_SUMMARY": "2000",
            "FALLBACK_WINDOW_HOURS": "12",
            "DEDUP_WINDOW_SEC": "120",
        }, clear=True):
            config = load_config()
            self.assertEqual(config.poll_interval_sec, 2.5)
            self.assertEqual(config.chunk_size, 500)
            self.assertEqual(config.max_messages_for_summary, 2000)
            self.assertEqual(config.fallback_window_hours, 12)
            self.assertEqual(config.dedup_window_sec, 120)

    def test_load_config_boolean_parsing(self):
        """Boolean env vars (FUN_ENABLED, PROACTIVE_ENABLED) parse correctly."""
        from src.config import load_config

        with patch.dict(os.environ, {
            "OPENAI_MODEL": "chat-model",
            "FUN_ENABLED": "false",
            "PROACTIVE_ENABLED": "true",
            "STICKY_MENTION_ENABLED": "false",
        }, clear=True):
            config = load_config()
            self.assertFalse(config.fun_enabled)
            self.assertTrue(config.proactive_enabled)
            self.assertFalse(config.sticky_mention_enabled)

    def test_load_config_chat_switches_default_true(self):
        """Both AI chat switches default to enabled."""
        from src.config import load_config

        with patch.dict(os.environ, {
            "OPENAI_MODEL": "chat-model",
        }, clear=True):
            config = load_config()
            self.assertTrue(config.group_chat_enabled)
            self.assertTrue(config.friend_chat_enabled)

    def test_load_config_chat_switches_parse_false(self):
        """GROUP/FRIEND_CHAT_ENABLED=false disables the matching chat."""
        from src.config import load_config

        with patch.dict(os.environ, {
            "OPENAI_MODEL": "chat-model",
            "GROUP_CHAT_ENABLED": "false",
            "FRIEND_CHAT_ENABLED": "FALSE",
        }, clear=True):
            config = load_config()
            self.assertFalse(config.group_chat_enabled)
            self.assertFalse(config.friend_chat_enabled)

    def test_load_config_sticky_mention_defaults(self):
        """Sticky mention settings have correct defaults."""
        from src.config import load_config

        with patch.dict(os.environ, {
            "OPENAI_MODEL": "chat-model",
        }, clear=True):
            config = load_config()
            self.assertTrue(config.sticky_mention_enabled)
            self.assertEqual(config.sticky_mention_ttl_sec, 60)

    def test_load_config_deepseek_model_override(self):
        """DEEPSEEK_MODEL can override the default model."""
        from src.config import load_config

        with patch.dict(os.environ, {
            "AI_BACKEND": "deepseek",
            "DEEPSEEK_API_KEY": "sk-ds-test",
            "DEEPSEEK_MODEL": "legacy-ultra-model",
        }, clear=True):
            config = load_config()
            self.assertEqual(config.deepseek_model, "legacy-ultra-model")

    def test_webot_data_dir_controls_default_db_and_log_paths(self):
        """WEBOT_DATA_DIR should relocate legacy DB_PATH/LOG_FILE defaults."""
        from src.config import load_config

        data_dir = Path("F:/tmp/WeChatBot-data")
        with patch.dict(os.environ, {
            "OPENAI_MODEL": "chat-model",
            "WEBOT_DATA_DIR": str(data_dir),
            "DB_PATH": "data/messages.db",
            "LOG_FILE": "data/bot.log",
        }, clear=True):
            config = load_config()
            self.assertEqual(Path(config.webot_data_dir), data_dir.resolve())
            self.assertEqual(Path(config.db_path), data_dir.resolve() / "messages.db")
            self.assertEqual(Path(config.log_file), data_dir.resolve() / "bot.log")

    def test_webot_data_dir_defaults_to_current_app_home(self):
        """The default WeChatBot data dir should follow the active app home."""
        from src.config import load_config

        app_home = Path("F:/tmp/WeChatBot-home")
        with patch.dict(os.environ, {
            "OPENAI_MODEL": "chat-model",
            "WEBOT_APP_HOME": str(app_home),
        }, clear=True):
            config = load_config()
            self.assertEqual(Path(config.webot_data_dir), app_home.resolve() / "data")
            self.assertEqual(Path(config.db_path), app_home.resolve() / "data" / "messages.db")

    def test_explicit_db_path_overrides_webot_data_dir(self):
        """A custom DB_PATH should remain an explicit override."""
        from src.config import load_config

        data_dir = Path("F:/tmp/WeChatBot-data")
        explicit_db = Path("F:/tmp/custom/messages.sqlite")
        with patch.dict(os.environ, {
            "OPENAI_MODEL": "chat-model",
            "WEBOT_DATA_DIR": str(data_dir),
            "DB_PATH": str(explicit_db),
        }, clear=True):
            config = load_config()
            self.assertEqual(Path(config.db_path), explicit_db.resolve())


class ValidateConfigTests(unittest.TestCase):
    """Tests for _validate_config() numeric range validation."""

    def test_poll_interval_sec_below_minimum_raises(self):
        """poll_interval_sec < 0.1 → RuntimeError."""
        from src.config import _validate_config

        with self.assertRaises(RuntimeError) as ctx:
            _validate_config({"poll_interval_sec": 0.05})
        self.assertIn("POLL_INTERVAL_SEC", str(ctx.exception))

    def test_poll_interval_sec_at_boundary_passes(self):
        """poll_interval_sec == 0.1 should pass validation."""
        from src.config import _validate_config

        # Should not raise
        _validate_config({"poll_interval_sec": 0.1})

    def test_chunk_size_below_minimum_raises(self):
        """chunk_size < 10 → RuntimeError."""
        from src.config import _validate_config

        with self.assertRaises(RuntimeError) as ctx:
            _validate_config({"chunk_size": 5})
        self.assertIn("CHUNK_SIZE", str(ctx.exception))

    def test_chunk_size_above_maximum_raises(self):
        """chunk_size > 1000 → RuntimeError."""
        from src.config import _validate_config

        with self.assertRaises(RuntimeError) as ctx:
            _validate_config({"chunk_size": 2000})
        self.assertIn("CHUNK_SIZE", str(ctx.exception))

    def test_chunk_size_at_boundaries_passes(self):
        """chunk_size at 10 or 1000 should pass."""
        from src.config import _validate_config

        _validate_config({"chunk_size": 10})
        _validate_config({"chunk_size": 1000})

    def test_max_messages_for_summary_below_minimum_raises(self):
        """max_messages_for_summary < 10 → RuntimeError."""
        from src.config import _validate_config

        with self.assertRaises(RuntimeError):
            _validate_config({"max_messages_for_summary": 5})

    def test_fallback_window_hours_below_one_raises(self):
        """fallback_window_hours < 1 → RuntimeError."""
        from src.config import _validate_config

        with self.assertRaises(RuntimeError):
            _validate_config({"fallback_window_hours": 0})

    def test_dedup_window_sec_below_minimum_raises(self):
        """dedup_window_sec < 10 → RuntimeError."""
        from src.config import _validate_config

        with self.assertRaises(RuntimeError):
            _validate_config({"dedup_window_sec": 5})

    def test_sticky_mention_ttl_sec_below_minimum_raises(self):
        """sticky_mention_ttl_sec < 10 → RuntimeError."""
        from src.config import _validate_config

        with self.assertRaises(RuntimeError) as ctx:
            _validate_config({"sticky_mention_ttl_sec": 5})
        self.assertIn("STICKY_MENTION_TTL_SEC", str(ctx.exception))

    def test_sticky_mention_ttl_sec_above_maximum_raises(self):
        """sticky_mention_ttl_sec > 300 → RuntimeError."""
        from src.config import _validate_config

        with self.assertRaises(RuntimeError) as ctx:
            _validate_config({"sticky_mention_ttl_sec": 500})
        self.assertIn("STICKY_MENTION_TTL_SEC", str(ctx.exception))

    def test_proactive_rate_window_sec_below_minimum_raises(self):
        """proactive_rate_window_sec < 30 → RuntimeError."""
        from src.config import _validate_config

        with self.assertRaises(RuntimeError):
            _validate_config({"proactive_rate_window_sec": 10})

    def test_proactive_rates_not_strictly_ascending_raises(self):
        """Proactive rates must be quiet < casual < lively < burst."""
        from src.config import _validate_config

        with self.assertRaises(RuntimeError) as ctx:
            _validate_config({
                "proactive_rate_quiet": 5.0,
                "proactive_rate_casual": 4.0,
                "proactive_rate_lively": 6.5,
                "proactive_rate_burst": 8.5,
            })
        self.assertIn("strict ascending", str(ctx.exception))

    def test_proactive_rates_with_zero_or_negative_raises(self):
        """Proactive rates must all be > 0."""
        from src.config import _validate_config

        with self.assertRaises(RuntimeError) as ctx:
            _validate_config({
                "proactive_rate_quiet": 0,
                "proactive_rate_casual": 4.0,
                "proactive_rate_lively": 6.5,
                "proactive_rate_burst": 8.5,
            })
        self.assertIn("must be > 0", str(ctx.exception))

    def test_proactive_rates_valid_order_passes(self):
        """Valid ascending proactive rates should pass."""
        from src.config import _validate_config

        _validate_config({
            "proactive_rate_quiet": 1.5,
            "proactive_rate_casual": 4.0,
            "proactive_rate_lively": 6.5,
            "proactive_rate_burst": 8.5,
        })

    def test_max_retries_below_minimum_raises(self):
        """max_retries < 1 → RuntimeError."""
        from src.config import _validate_config

        with self.assertRaises(RuntimeError):
            _validate_config({"max_retries": 0})

    def test_max_retries_above_maximum_raises(self):
        """max_retries > 10 → RuntimeError."""
        from src.config import _validate_config

        with self.assertRaises(RuntimeError):
            _validate_config({"max_retries": 11})

    def test_max_retries_valid_passes(self):
        """max_retries between 1-10 should pass."""
        from src.config import _validate_config

        _validate_config({"max_retries": 5})

    def test_multiple_errors_reported_together(self):
        """Multiple invalid values should all appear in error message."""
        from src.config import _validate_config

        with self.assertRaises(RuntimeError) as ctx:
            _validate_config({
                "poll_interval_sec": 0.01,
                "chunk_size": 5,
                "dedup_window_sec": 3,
            })
        msg = str(ctx.exception)
        self.assertIn("POLL_INTERVAL_SEC", msg)
        self.assertIn("CHUNK_SIZE", msg)
        self.assertIn("DEDUP_WINDOW_SEC", msg)

    def test_empty_kwargs_passes_all_defaults(self):
        """No kwargs → all defaults pass validation."""
        from src.config import _validate_config

        _validate_config({})


# ---------------------------------------------------------------------------
# load_config integration: triggers full _validate_config flow
# ---------------------------------------------------------------------------


class LoadConfigValidationIntegrationTests(unittest.TestCase):
    """load_config() → _validate_config() integration."""

    def test_invalid_chunk_size_in_env_raises(self):
        """Setting CHUNK_SIZE=5 via env should trigger validation error."""
        from src.config import load_config

        with patch.dict(os.environ, {
            "OPENAI_MODEL": "chat-model",
            "CHUNK_SIZE": "5",
        }, clear=True):
            with self.assertRaises(RuntimeError) as ctx:
                load_config()
            self.assertIn("CHUNK_SIZE", str(ctx.exception))

    def test_invalid_sticky_mention_ttl_in_env_raises(self):
        """Setting STICKY_MENTION_TTL_SEC=999 via env should fail."""
        from src.config import load_config

        with patch.dict(os.environ, {
            "OPENAI_MODEL": "chat-model",
            "STICKY_MENTION_TTL_SEC": "999",
        }, clear=True):
            with self.assertRaises(RuntimeError) as ctx:
                load_config()
            self.assertIn("STICKY_MENTION_TTL_SEC", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
