"""WeChat data directory detection helpers.

Windows WeChat 4.x may store account data outside Documents and exposes the
actual root to child processes via ``--wechat-files-path``.  This module keeps
that detection logic in one pure-Python place so the WCDB backend and Web UI
diagnostics agree on the same path.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import os
from pathlib import Path
import re
from typing import Iterable, Sequence

logger = logging.getLogger(__name__)

_WECHAT_FILES_ARG_RE = re.compile(
    r"--wechat-files-path(?:=|\s+)(?:\"([^\"]+)\"|'([^']+)'|([^\s]+))",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class WeChatAccountPath:
    """Detected WeChat account directory with its session database."""

    wxid: str
    base_dir: Path
    account_dir: Path
    session_db: Path


def _clean_arg_value(value: str) -> str:
    return (value or "").strip().strip('"').strip("'")


def _extract_paths_from_command_line(command_line: str) -> list[str]:
    """Extract ``--wechat-files-path`` values from a raw command line."""
    paths: list[str] = []
    for match in _WECHAT_FILES_ARG_RE.finditer(command_line or ""):
        value = _clean_arg_value(next(group for group in match.groups() if group))
        if value:
            paths.append(value)
    return paths


def _extract_paths_from_args(args: Sequence[str]) -> list[str]:
    """Extract ``--wechat-files-path`` values from process argv."""
    paths: list[str] = []
    index = 0
    while index < len(args):
        arg = str(args[index] or "")
        lower = arg.lower()
        if lower == "--wechat-files-path" and index + 1 < len(args):
            value = _clean_arg_value(str(args[index + 1]))
            if value:
                paths.append(value)
            index += 2
            continue
        if lower.startswith("--wechat-files-path="):
            value = _clean_arg_value(arg.split("=", 1)[1])
            if value:
                paths.append(value)
        index += 1
    return paths


def _wechat_files_paths_from_processes() -> list[str]:
    """Return WeChat data roots advertised by running WeChat processes."""
    try:
        import psutil
    except Exception as exc:
        logger.debug("psutil unavailable for WeChat path detection: %s", exc)
        return []

    paths: list[str] = []
    for proc in psutil.process_iter(["name", "cmdline"]):
        try:
            info = proc.info
            name = str(info.get("name") or "").lower()
            cmdline = info.get("cmdline") or []
        except (psutil.Error, OSError):
            continue

        if not (
            "wechat" in name
            or "weixin" in name
            or any("wechat" in str(arg).lower() or "weixin" in str(arg).lower() for arg in cmdline)
        ):
            continue

        if isinstance(cmdline, (list, tuple)):
            paths.extend(_extract_paths_from_args([str(arg) for arg in cmdline]))
            paths.extend(_extract_paths_from_command_line(" ".join(str(arg) for arg in cmdline)))
        else:
            paths.extend(_extract_paths_from_command_line(str(cmdline)))

    return _dedupe_strings(paths)


def _dedupe_strings(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean = _clean_arg_value(value)
        if not clean:
            continue
        key = clean.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(clean)
    return result


def _default_candidate_dirs() -> list[Path]:
    """Return common WeChat data roots without recursive drive scans."""
    home = Path.home()
    candidates: list[Path] = []

    for env_name in ("USERPROFILE", "OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        raw = os.environ.get(env_name, "").strip()
        if not raw:
            continue
        base = Path(raw)
        candidates.extend([
            base / "Documents" / "xwechat_files",
            base / "Documents" / "WeChat Files",
        ])

    candidates.extend([
        home / "Documents" / "xwechat_files",
        home / "Documents" / "WeChat Files",
    ])

    appdata = os.environ.get("APPDATA", "").strip()
    if appdata:
        candidates.extend([
            Path(appdata) / "Tencent" / "xwechat" / "xwechat_files",
            Path(appdata) / "Tencent" / "WeChat Files",
        ])

    localappdata = os.environ.get("LOCALAPPDATA", "").strip()
    if localappdata:
        candidates.append(
            Path(localappdata) / "Tencent" / "WeChat" / "xwechat_files"
        )

    return _dedupe_paths(candidates)


def _dedupe_paths(paths: Iterable[Path]) -> list[Path]:
    seen: set[str] = set()
    result: list[Path] = []
    for path in paths:
        if not str(path):
            continue
        key = str(path).casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result


def _session_db_for_account(account_dir: Path) -> Path:
    return account_dir / "db_storage" / "session" / "session.db"


def _find_account_ancestor(path: Path) -> Path | None:
    for candidate in (path, *path.parents):
        if candidate.name.startswith("wxid_") and _session_db_for_account(candidate).exists():
            return candidate
    return None


def normalize_wechat_data_dir(path: str | Path) -> Path | None:
    """Normalize a user/process path to the parent containing ``wxid_*`` dirs."""
    if not path:
        return None

    candidate = Path(path).expanduser()
    if not candidate.exists():
        return None

    try:
        candidate = candidate.resolve()
    except OSError:
        pass

    if candidate.is_file():
        candidate = candidate.parent

    account_dir = _find_account_ancestor(candidate)
    if account_dir is not None:
        return account_dir.parent

    nested_names = ("xwechat_files", "WeChat Files")
    probe_dirs = [candidate, *(candidate / name for name in nested_names)]
    for probe in probe_dirs:
        if probe.exists() and _accounts_under_base(probe):
            return probe

    return candidate


def _accounts_under_base(base_dir: Path) -> list[WeChatAccountPath]:
    try:
        children = list(base_dir.iterdir())
    except (FileNotFoundError, NotADirectoryError, PermissionError, OSError):
        return []

    accounts: list[WeChatAccountPath] = []
    for child in children:
        if not child.is_dir() or not child.name.startswith("wxid_"):
            continue
        session_db = _session_db_for_account(child)
        if session_db.exists():
            accounts.append(
                WeChatAccountPath(
                    wxid=child.name,
                    base_dir=base_dir,
                    account_dir=child,
                    session_db=session_db,
                )
            )

    return sorted(
        accounts,
        key=lambda account: _mtime(account.session_db, account.account_dir),
        reverse=True,
    )


def _mtime(*paths: Path) -> float:
    for path in paths:
        try:
            return path.stat().st_mtime
        except OSError:
            continue
    return 0.0


def list_accounts_in_data_dir(path: str | Path) -> list[WeChatAccountPath]:
    """List WeChat accounts under a manually supplied data directory."""
    base = normalize_wechat_data_dir(path)
    if base is None:
        return []
    return _accounts_under_base(base)


def _candidate_dirs(custom_base_dir: str = "") -> list[tuple[Path, str]]:
    candidates: list[tuple[Path, str]] = []
    if custom_base_dir:
        candidates.append((Path(custom_base_dir).expanduser(), "custom"))

    for path in _wechat_files_paths_from_processes():
        candidates.append((Path(path).expanduser(), "wechat-process"))

    candidates.extend((path, "default") for path in _default_candidate_dirs())

    seen: set[str] = set()
    result: list[tuple[Path, str]] = []
    for path, source in candidates:
        key = str(path).casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append((path, source))
    return result


def find_wxid_and_dbpath(custom_base_dir: str = "") -> tuple[str, str]:
    """Find the newest WeChat account and return ``(wxid, base_dir)``."""
    checked: list[str] = []
    for raw_base, source in _candidate_dirs(custom_base_dir):
        base = normalize_wechat_data_dir(raw_base)
        if base is None:
            checked.append(str(raw_base))
            if source == "custom":
                logger.warning(
                    "WECHAT_DATA_DIR=%s does not exist or is not a directory; "
                    "falling back to auto-detection",
                    raw_base,
                )
            continue

        checked.append(str(base))
        accounts = _accounts_under_base(base)
        if not accounts:
            continue

        account = accounts[0]
        logger.info(
            "%s-detected WeChat data dir: wxid=%s base=%s",
            source,
            account.wxid,
            account.base_dir,
        )
        return account.wxid, str(account.base_dir)

    details = "; checked: " + ", ".join(_dedupe_strings(checked)) if checked else ""
    raise FileNotFoundError(
        "Cannot find WeChat data directory. Make sure WeChat is installed "
        "and you have logged in at least once." + details
    )


def detect_default_data_dir() -> str:
    """Return the auto-detected WeChat data root, or an empty string."""
    try:
        _, base_dir = find_wxid_and_dbpath("")
        return base_dir
    except FileNotFoundError:
        return ""
