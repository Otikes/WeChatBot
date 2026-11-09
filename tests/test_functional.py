"""Functional/E2E tests — verify real HTTP + browser behavior.

These tests start the web server, then verify the full stack (React frontend
+ Python backend) works correctly via real HTTP requests and headless Chromium.

Requirements:  pip install playwright && python -m playwright install chromium
"""

import http.client
import json
import os
import socket
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

# ── Helpers ────────────────────────────────────────────────────────────────

SERVER_HOST = "127.0.0.1"
SERVER_PORT = None  # discovered at fixture time
BASE_URL = None


def _write_dashboard_env(env_path: Path):
    """Put the app in completed-onboarding state for dashboard E2E tests."""
    env_path.write_text(
        "AI_BACKEND=openai_compatible\n"
        "OPENAI_API_KEY=\n"
        "OPENAI_MODEL=chat-model\n"
        "WECHAT_GROUPS=*\n"
        "ONBOARDING_DONE=true\n",
        encoding="utf-8",
    )
    os.environ.update({
        "AI_BACKEND": "openai_compatible",
        "OPENAI_API_KEY": "",
        "OPENAI_MODEL": "chat-model",
        "WECHAT_GROUPS": "*",
        "ONBOARDING_DONE": "true",
    })


def _find_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_server(port):
    """Start the web server in a daemon thread. Returns when ready."""
    import traceback
    from src.web.server import _run_server

    start_errors = []

    def _run_catching():
        try:
            _run_server(SERVER_HOST, port)
        except Exception:
            start_errors.append(traceback.format_exc())

    t = threading.Thread(target=_run_catching, daemon=True)
    t.start()

    for _ in range(50):
        if start_errors:
            raise RuntimeError(f"Server thread crashed:\n{start_errors[0]}")
        try:
            conn = http.client.HTTPConnection(SERVER_HOST, port, timeout=0.5)
            conn.request("GET", "/api/status")
            resp = conn.getresponse()
            resp.read()
            conn.close()
            return t
        except Exception:
            time.sleep(0.1)
    raise RuntimeError(f"Server did not start within 5 seconds on port {port}")


def _api_get(path):
    """GET request to test server, bypassing system proxy."""
    conn = http.client.HTTPConnection(SERVER_HOST, SERVER_PORT, timeout=5)
    conn.request("GET", path)
    resp = conn.getresponse()
    data = json.loads(resp.read())
    conn.close()
    return resp.status, data


def _api_post(path, body_dict=None, raw_body=None, timeout=5):
    """POST request to test server, bypassing system proxy."""
    conn = http.client.HTTPConnection(SERVER_HOST, SERVER_PORT, timeout=timeout)
    body = raw_body if raw_body is not None else json.dumps(body_dict or {}).encode()
    conn.request("POST", path, body=body, headers={"Content-Type": "application/json"})
    try:
        resp = conn.getresponse()
        data = json.loads(resp.read())
        conn.close()
        return resp.status, data
    except (TimeoutError, ConnectionError, OSError):
        conn.close()
        raise


@pytest.fixture(scope="module")
def server():
    """Module-level fixture: start the web server once for all tests."""
    global SERVER_PORT, BASE_URL

    ui_dist = Path(__file__).resolve().parent.parent / "ui" / "dist" / "index.html"
    if not ui_dist.exists():
        pytest.skip("UI not built. Run: cd ui && npm run build")

    SERVER_PORT = _find_free_port()
    BASE_URL = f"http://{SERVER_HOST}:{SERVER_PORT}"

    project_root = Path(__file__).resolve().parent.parent
    env_path = project_root / ".env"
    original_env = env_path.read_text(encoding="utf-8") if env_path.exists() else None
    _write_dashboard_env(env_path)  # skip onboarding -> dashboard loads directly

    t = _start_server(SERVER_PORT)
    try:
        yield
    finally:
        if original_env is None:
            env_path.unlink(missing_ok=True)
        else:
            env_path.write_text(original_env, encoding="utf-8")


# ── API-level functional tests ──────────────────────────────────────────────

class TestDiagnoseApi:
    """Verify /api/onboarding/diagnose returns correct structure."""

    def test_diagnose_returns_200(self, server):
        status, data = _api_get("/api/onboarding/diagnose")
        assert status == 200
        assert data["ok"] is True
        diag = data["diagnostics"]
        for key in ("python", "requirements", "wechat", "env", "db"):
            assert key in diag, f"Missing diagnostics key: {key}"
            assert "ok" in diag[key]
            assert "value" in diag[key]

    def test_diagnose_python_ok(self, server):
        _, data = _api_get("/api/onboarding/diagnose")
        assert data["diagnostics"]["python"]["ok"] is True
        assert "Python 3" in data["diagnostics"]["python"]["value"]


class TestSandboxApi:
    """Verify /api/sandbox/test endpoint is routed correctly.

    Note: sending a real message triggers an AI API call which may take 10–30s.
    These tests only verify the endpoint accepts POST requests and returns JSON.
    """

    def test_sandbox_invalid_json_returns_error(self, server):
        status, data = _api_post("/api/sandbox/test", raw_body=b"not json")
        assert status == 200
        assert "ok" in data


class TestConfigDeepseekBaseUrl:
    """Verify deepseek_base_url is loaded and has a default."""

    def test_default_value(self):
        from src.config import BotConfig
        assert BotConfig.deepseek_base_url == "https://api.deepseek.com"

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://custom-proxy.example.com")
        monkeypatch.setenv("AI_BACKEND", "deepseek")
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
        monkeypatch.setenv("DEEPSEEK_MODEL", "legacy-chat-model")
        from src.config import load_config
        config = load_config()
        assert config.deepseek_base_url == "https://custom-proxy.example.com"


class TestConfigAnthropicBaseUrl:
    """Verify anthropic_base_url is loaded and has a default."""

    def test_default_value(self):
        from src.config import BotConfig
        assert BotConfig.anthropic_base_url == "https://api.anthropic.com"

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://claude-proxy.example.com")
        monkeypatch.setenv("AI_BACKEND", "claude")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
        monkeypatch.setenv("SUMMARIZE_MODEL", "messages-model")
        from src.config import load_config
        config = load_config()
        assert config.anthropic_base_url == "https://claude-proxy.example.com"


class TestConfigOpenAICompatibleBaseUrl:
    """Verify openai_base_url is loaded and has a default."""

    def test_default_value(self):
        from src.config import BotConfig
        assert BotConfig.openai_base_url == "https://api.openai.com/v1"

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("OPENAI_BASE_URL", "https://relay.example.com/v1")
        monkeypatch.setenv("AI_BACKEND", "openai_compatible")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")
        monkeypatch.setenv("OPENAI_MODEL", "chat-model")
        from src.config import load_config
        config = load_config()
        assert config.openai_base_url == "https://relay.example.com/v1"


class TestSummarizerBaseUrl:
    """Verify AI factory forwards provider-specific Base URLs."""

    def test_claude_factory_passes_anthropic_base_url(self, monkeypatch):
        from src.config import BotConfig
        import src.summarize as summarize

        captured = {}

        class FakeClaudeSummarizer:
            def __init__(self, api_key, model, base_url, chunk_size):
                captured.update({
                    "api_key": api_key,
                    "model": model,
                    "base_url": base_url,
                    "chunk_size": chunk_size,
                })

        monkeypatch.setattr(summarize, "ClaudeSummarizer", FakeClaudeSummarizer)

        config = BotConfig(
            ai_backend="claude",
            anthropic_api_key="sk-ant-test",
            anthropic_base_url="https://claude-proxy.example.com",
            summarize_model="claude-test",
            chunk_size=123,
        )

        summarize.create_summarizer(config)

        assert captured["api_key"] == "sk-ant-test"
        assert captured["model"] == "claude-test"
        assert captured["base_url"] == "https://claude-proxy.example.com"
        assert captured["chunk_size"] == 123

    def test_openai_compatible_factory_passes_openai_base_url(self, monkeypatch):
        from src.config import BotConfig
        import src.summarize as summarize

        captured = {}

        class FakeOpenAISummarizer:
            def __init__(self, api_key, model, base_url, chunk_size):
                captured.update({
                    "api_key": api_key,
                    "model": model,
                    "base_url": base_url,
                    "chunk_size": chunk_size,
                })

        monkeypatch.setattr(summarize, "OpenAICompatibleSummarizer", FakeOpenAISummarizer)

        config = BotConfig(
            ai_backend="openai_compatible",
            openai_api_key="sk-openai-test",
            openai_base_url="https://relay.example.com/v1",
            openai_model="qwen-plus",
            chunk_size=42,
        )

        summarize.create_summarizer(config)

        assert captured["api_key"] == "sk-openai-test"
        assert captured["model"] == "qwen-plus"
        assert captured["base_url"] == "https://relay.example.com/v1"
        assert captured["chunk_size"] == 42


class TestOpenAICompatibleBackend:
    """Verify compatibility helpers used by the generic backend."""

    def test_constructor_normalizes_base_url_and_allows_empty_key(self):
        from src.summarize.openai_compatible_backend import OpenAICompatibleSummarizer

        summarizer = OpenAICompatibleSummarizer(
            api_key="",
            base_url="localhost:11434/v1/chat/completions",
            model="qwen2.5:7b",
        )

        assert summarizer.base_url == "http://localhost:11434/v1"

    def test_parse_fenced_json_summary_response(self):
        from src.summarize.openai_compatible_backend import _parse_summary_from_response

        response = SimpleNamespace(choices=[
            SimpleNamespace(message=SimpleNamespace(
                tool_calls=None,
                content=(
                    "```json\n"
                    "{\"summary_text\":\"聊了部署\","
                    "\"topics\":\"上线\","
                    "\"participants\":[\"小王\"]}"
                    "\n```"
                ),
            ))
        ])

        result = _parse_summary_from_response(response)

        assert result.summary_text == "聊了部署"
        assert result.topics == ["上线"]
        assert result.participants[0].name == "小王"


class TestPostAllowlist:
    """Verify /api/sandbox/test is in POST allowlist (doesn't return 405)."""

    def test_sandbox_post_not_405(self, server):
        """Invalid JSON still returns 200 (not 405), proving the route is registered."""
        status, _ = _api_post("/api/sandbox/test", raw_body=b"not json")
        assert status == 200

    def test_unknown_post_path_returns_405(self, server):
        conn = http.client.HTTPConnection(SERVER_HOST, SERVER_PORT, timeout=5)
        conn.request("POST", "/api/unknown-path", body=b"{}",
                     headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        conn.close()
        assert resp.status == 405


class TestLogsApi:
    """Verify log read/clear routes against a real HTTP server."""

    def test_clear_logs_endpoint_truncates_file(self, server):
        project_root = Path(__file__).resolve().parent.parent
        log_path = project_root / "data" / "bot.log"
        original = log_path.read_text(encoding="utf-8") if log_path.exists() else None
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(
                "2024-06-01 12:00:00 [INFO] test: Persisted API log\n",
                encoding="utf-8",
            )

            status, data = _api_post("/api/logs/clear")

            assert status == 200
            assert data["ok"] is True
            assert data["cleared"] is True
            assert log_path.read_text(encoding="utf-8") == ""
        finally:
            if original is None:
                log_path.unlink(missing_ok=True)
            else:
                log_path.write_text(original, encoding="utf-8")


# ── Playwright browser-level functional tests ───────────────────────────────

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


@pytest.fixture(scope="module")
def browser():
    if not PLAYWRIGHT_AVAILABLE:
        pytest.skip("Playwright not installed. Run: pip install playwright")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        yield browser
        browser.close()


@pytest.fixture
def page(browser, server):
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()
    yield page
    context.close()


class TestPageLoads:
    def test_index_html_loads(self, page):
        page.goto(BASE_URL, timeout=10000)
        assert page.title() is not None

    def test_runtime_reset_button_visible(self, page):
        page.goto(BASE_URL, timeout=10000)
        page.wait_for_timeout(1000)
        reset_btn = page.locator("button:has-text('重置数据')")
        assert reset_btn.count() > 0

    def test_runtime_reset_returns_to_onboarding_flow(self, page):
        project_root = Path(__file__).resolve().parent.parent
        env_path = project_root / ".env"
        try:
            page.goto(BASE_URL, timeout=10000)
            page.wait_for_selector("button:has-text('重置数据')", timeout=5000)
            page.once("dialog", lambda dialog: dialog.accept())
            page.locator("button:has-text('重置数据')").click()
            page.wait_for_selector("text=环境准备与密钥", timeout=5000)
            page.wait_for_selector("button:has-text('开始自动获取')", timeout=5000)
            page.wait_for_selector("text=本地环境配置文件", timeout=5000)
            status, data = _api_get("/api/onboarding/status")
            assert status == 200
            assert data["onboarding_done"] is False
            assert not env_path.exists()
        finally:
            _write_dashboard_env(env_path)


class TestThemeToggle:
    def test_default_theme_is_dark(self, page):
        page.goto(BASE_URL, timeout=10000)
        page.wait_for_timeout(1000)
        html_classes = page.evaluate("document.documentElement.className")
        assert "dark" in html_classes, f"Expected 'dark' class, got: {html_classes}"

    def test_toggle_button_exists(self, page):
        page.goto(BASE_URL, timeout=10000)
        page.wait_for_timeout(1000)
        toggle_btn = page.locator('button[title*="切换"]')
        if toggle_btn.count() > 0:
            toggle_btn.first.click()
            page.wait_for_timeout(500)
            html_classes = page.evaluate("document.documentElement.className")
            assert "dark" not in html_classes


class TestSidebarNavigation:
    def test_sidebar_has_tabs(self, page):
        page.goto(BASE_URL, timeout=10000)
        page.wait_for_timeout(1000)
        page_text = page.inner_text("body")
        assert "运行状态" in page_text
        assert "系统配置" in page_text
        assert "运行日志" in page_text

    def test_sandbox_subtab_visible(self, page):
        page.goto(BASE_URL, timeout=10000)
        page.wait_for_timeout(1000)
        config_btn = page.locator("button:has-text('系统配置')")
        if config_btn.count() > 0:
            config_btn.first.click()
            page.wait_for_timeout(500)
            page_text = page.inner_text("body")
            assert "提示词沙箱" in page_text


class TestFriendChatConfig:
    def test_friend_chat_checklist_visible(self, page):
        resp = page.request.get(f"{BASE_URL}/api/friends")
        assert resp.ok
        data = resp.json()
        assert data["ok"] is True
        assert "friends" in data

        page.goto(BASE_URL, timeout=10000)
        page.wait_for_timeout(1000)
        config_btn = page.locator("button:has-text('系统配置')")
        if config_btn.count() > 0:
            config_btn.first.click()
            page.wait_for_timeout(300)
        identity_btn = page.locator("button:has-text('机器人身份')")
        if identity_btn.count() > 0:
            identity_btn.first.click()
            page.wait_for_timeout(500)
        page_text = page.inner_text("body")
        assert "好友私聊" in page_text
        assert "未勾选任何好友" in page_text


class TestConfigExportImport:
    def test_backup_ui_visible(self, page):
        page.goto(BASE_URL, timeout=10000)
        page.wait_for_timeout(1000)
        config_btn = page.locator("button:has-text('系统配置')")
        if config_btn.count() > 0:
            config_btn.first.click()
            page.wait_for_timeout(500)
            page_text = page.inner_text("body")
            assert "导出备份" in page_text or "配置备份" in page_text


class TestLogViewer:
    def test_clear_button_clears_persisted_logs(self, page):
        project_root = Path(__file__).resolve().parent.parent
        log_path = project_root / "data" / "bot.log"
        original = log_path.read_text(encoding="utf-8") if log_path.exists() else None
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_text(
                "2024-06-01 12:00:00 [INFO] test: Persisted browser log\n",
                encoding="utf-8",
            )

            page.goto(BASE_URL, timeout=10000)
            page.wait_for_timeout(1000)
            page.locator("button:has-text('运行日志')").first.click()
            page.wait_for_selector("text=Persisted browser log", timeout=5000)
            page.locator('button[title="清空日志文件"]').click()
            page.wait_for_selector("text=Terminal Cleared", timeout=5000)

            assert log_path.read_text(encoding="utf-8") == ""
        finally:
            if original is None:
                log_path.unlink(missing_ok=True)
            else:
                log_path.write_text(original, encoding="utf-8")
