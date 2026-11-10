"""LLM Token 用量统计 — SQLite 持久化与聚合查询。

独立数据库文件（默认 ``webot 数据目录/token_usage.db``），不随
「重置本地数据」被清空，保证消耗统计长期可追溯。

每次 AI 请求由后端在拿到响应后调用 :func:`record_usage` 写入一条记录；
Web 控制台通过 :func:`get_summary` / :func:`get_timeseries` /
:func:`get_logs` 读取聚合结果。
"""

import logging
import sqlite3
import threading
import time

from src.config import webot_data_path
from src.db.schema import ThreadSafeConnection

logger = logging.getLogger(__name__)

DB_FILENAME = "token_usage.db"

SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA busy_timeout=5000;
PRAGMA synchronous=NORMAL;

CREATE TABLE IF NOT EXISTS token_usage (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at        INTEGER NOT NULL,
    provider          TEXT    NOT NULL DEFAULT '',
    model             TEXT    NOT NULL DEFAULT '',
    call_type         TEXT    NOT NULL DEFAULT '',
    prompt_tokens     INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens      INTEGER NOT NULL DEFAULT 0,
    duration_ms       INTEGER NOT NULL DEFAULT 0,
    status            TEXT    NOT NULL DEFAULT 'success',
    error             TEXT    NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_token_usage_time
    ON token_usage(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_token_usage_model
    ON token_usage(model, created_at DESC);
"""

RANGE_KEYS = ("today", "7d", "30d", "all")
_RANGE_DAYS = {"today": 1, "7d": 7, "30d": 30}

_conn: ThreadSafeConnection | None = None
_conn_lock = threading.Lock()


def _get_conn() -> ThreadSafeConnection:
    """懒加载统计库连接（模块级单例，线程安全）。"""
    global _conn
    if _conn is None:
        with _conn_lock:
            if _conn is None:
                path = webot_data_path(DB_FILENAME)
                path.parent.mkdir(parents=True, exist_ok=True)
                raw = sqlite3.connect(str(path), check_same_thread=False)
                raw.row_factory = sqlite3.Row
                raw.executescript(SCHEMA_SQL)
                raw.commit()
                _conn = ThreadSafeConnection(raw)
    return _conn


# ── 写入 ─────────────────────────────────────────────────────────────


def record_usage(*, provider: str, model: str, call_type: str,
                 prompt_tokens: int = 0, completion_tokens: int = 0,
                 duration_ms: int = 0, status: str = "success",
                 error: str = "") -> None:
    """记录一次 AI 请求的 token 消耗。

    统计失败绝不影响业务请求，所有异常在此吞掉并写日志。
    """
    try:
        conn = _get_conn()
        prompt = max(0, int(prompt_tokens or 0))
        completion = max(0, int(completion_tokens or 0))
        with conn:
            conn.execute(
                """INSERT INTO token_usage
                   (created_at, provider, model, call_type, prompt_tokens,
                    completion_tokens, total_tokens, duration_ms, status, error)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    int(time.time()),
                    str(provider or ""),
                    str(model or ""),
                    str(call_type or ""),
                    prompt,
                    completion,
                    prompt + completion,
                    max(0, int(duration_ms or 0)),
                    "error" if status == "error" else "success",
                    str(error or "")[:500],
                ),
            )
    except Exception:
        logger.exception("Failed to record token usage")


# ── 时间范围 ─────────────────────────────────────────────────────────


def normalize_range(range_key: str) -> str:
    return range_key if range_key in RANGE_KEYS else "today"


def range_start_ts(range_key: str, now_ts: int | None = None) -> int:
    """返回范围起点：today=今日 0 点，7d/30d=含今天在内的自然日，all=0。"""
    now = int(time.time() if now_ts is None else now_ts)
    days = _RANGE_DAYS.get(normalize_range(range_key))
    if not days:
        return 0
    lt = time.localtime(now)
    midnight = int(time.mktime(
        (lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1)
    ))
    return midnight - (days - 1) * 86400


# ── 聚合查询 ─────────────────────────────────────────────────────────


def get_summary(range_key: str = "today") -> dict:
    """KPI 汇总 + 各模型消耗分布。"""
    range_key = normalize_range(range_key)
    since = range_start_ts(range_key)
    conn = _get_conn()

    row = conn.execute(
        """SELECT COUNT(*) AS requests,
                  COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,
                  COALESCE(SUM(completion_tokens), 0) AS completion_tokens,
                  COALESCE(SUM(total_tokens), 0) AS total_tokens,
                  COALESCE(SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END), 0)
                      AS errors,
                  COALESCE(AVG(duration_ms), 0) AS avg_duration_ms
           FROM token_usage
           WHERE created_at >= ?""",
        (since,),
    ).fetchone()

    summary = {
        "requests": int(row["requests"] or 0),
        "prompt_tokens": int(row["prompt_tokens"] or 0),
        "completion_tokens": int(row["completion_tokens"] or 0),
        "total_tokens": int(row["total_tokens"] or 0),
        "errors": int(row["errors"] or 0),
        "avg_duration_ms": int(row["avg_duration_ms"] or 0),
    }

    model_rows = conn.execute(
        """SELECT model,
                  provider,
                  COUNT(*) AS requests,
                  COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,
                  COALESCE(SUM(completion_tokens), 0) AS completion_tokens,
                  COALESCE(SUM(total_tokens), 0) AS total_tokens,
                  COALESCE(SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END), 0)
                      AS errors
           FROM token_usage
           WHERE created_at >= ?
           GROUP BY model, provider
           ORDER BY total_tokens DESC, requests DESC""",
        (since,),
    ).fetchall()

    models = [
        {
            "model": item["model"] or "(unknown)",
            "provider": item["provider"] or "",
            "requests": int(item["requests"] or 0),
            "prompt_tokens": int(item["prompt_tokens"] or 0),
            "completion_tokens": int(item["completion_tokens"] or 0),
            "total_tokens": int(item["total_tokens"] or 0),
            "errors": int(item["errors"] or 0),
        }
        for item in model_rows
    ]

    return {
        "range": range_key,
        "since": since,
        "summary": summary,
        "models": models,
    }


def _floor_ts(ts: int, step: int, granularity: str) -> int:
    lt = time.localtime(ts)
    if granularity == "hour":
        return int(time.mktime(
            (lt.tm_year, lt.tm_mon, lt.tm_mday, lt.tm_hour, 0, 0, 0, 0, -1)
        ))
    return int(time.mktime(
        (lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1)
    ))


def get_timeseries(range_key: str = "today",
                   granularity: str = "hour") -> dict:
    """按小时/天聚合消耗趋势，并补齐空缺时段（值为 0）。"""
    range_key = normalize_range(range_key)
    granularity = "day" if granularity == "day" else "hour"
    now = int(time.time())
    since = range_start_ts(range_key, now)
    conn = _get_conn()

    # 小时粒度最多回看 7 天，避免返回上千个空桶拖慢图表
    if granularity == "hour":
        since = max(since, now - 7 * 86400)

    if since == 0:
        first = conn.execute(
            "SELECT MIN(created_at) AS first FROM token_usage"
        ).fetchone()
        since = int(first["first"] or now) if first else now

    fmt = "%Y-%m-%d %H:00" if granularity == "hour" else "%Y-%m-%d"
    step = 3600 if granularity == "hour" else 86400

    rows = conn.execute(
        f"""SELECT strftime('{fmt}', created_at, 'unixepoch', 'localtime')
                AS bucket,
                   COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,
                   COALESCE(SUM(completion_tokens), 0) AS completion_tokens,
                   COALESCE(SUM(total_tokens), 0) AS total_tokens,
                   COUNT(*) AS requests
            FROM token_usage
            WHERE created_at >= ?
            GROUP BY bucket
            ORDER BY bucket ASC""",
        (since,),
    ).fetchall()

    by_bucket = {row["bucket"]: row for row in rows}
    points = []
    cursor = _floor_ts(since, step, granularity)
    # 防御：异常数据导致桶数量过大时截断到最近 1000 个
    if (now - cursor) // step > 1000:
        cursor = _floor_ts(now - 999 * step, step, granularity)
    while cursor <= now:
        label = time.strftime(fmt, time.localtime(cursor))
        row = by_bucket.get(label)
        points.append({
            "label": label,
            "prompt_tokens": int(row["prompt_tokens"]) if row else 0,
            "completion_tokens": int(row["completion_tokens"]) if row else 0,
            "total_tokens": int(row["total_tokens"]) if row else 0,
            "requests": int(row["requests"]) if row else 0,
        })
        cursor += step

    return {
        "range": range_key,
        "granularity": granularity,
        "since": since,
        "points": points,
    }


CALL_TYPE_LABELS = {
    "chat": "AI 对话",
    "proactive": "主动发言",
    "summarize": "聊天总结",
    "summarize_chunk": "总结分片",
    "summarize_merge": "总结合并",
    "memory": "记忆整理",
}


def get_logs(range_key: str = "today", page: int = 1, page_size: int = 20,
             model: str = "", status: str = "") -> dict:
    """请求日志明细分页查询。"""
    range_key = normalize_range(range_key)
    since = range_start_ts(range_key)

    page = max(1, int(page or 1))
    page_size = min(100, max(5, int(page_size or 20)))

    where = ["created_at >= ?"]
    params: list = [since]
    if model:
        where.append("model = ?")
        params.append(model)
    if status in ("success", "error"):
        where.append("status = ?")
        params.append(status)
    where_sql = " AND ".join(where)

    conn = _get_conn()
    total_row = conn.execute(
        f"SELECT COUNT(*) AS cnt FROM token_usage WHERE {where_sql}",
        tuple(params),
    ).fetchone()
    total = int(total_row["cnt"] or 0) if total_row else 0
    pages = max(1, (total + page_size - 1) // page_size)
    page = min(page, pages)

    rows = conn.execute(
        f"""SELECT id, created_at, provider, model, call_type,
                   prompt_tokens, completion_tokens, total_tokens,
                   duration_ms, status, error
            FROM token_usage
            WHERE {where_sql}
            ORDER BY id DESC
            LIMIT ? OFFSET ?""",
        tuple(params) + (page_size, (page - 1) * page_size),
    ).fetchall()

    items = [
        {
            "id": int(row["id"]),
            "time": time.strftime(
                "%Y-%m-%d %H:%M:%S", time.localtime(int(row["created_at"]))
            ),
            "provider": row["provider"] or "",
            "model": row["model"] or "",
            "call_type": row["call_type"] or "",
            "call_type_label": CALL_TYPE_LABELS.get(
                row["call_type"] or "", row["call_type"] or "—"
            ),
            "prompt_tokens": int(row["prompt_tokens"] or 0),
            "completion_tokens": int(row["completion_tokens"] or 0),
            "total_tokens": int(row["total_tokens"] or 0),
            "duration_ms": int(row["duration_ms"] or 0),
            "status": row["status"] or "success",
            "error": row["error"] or "",
        }
        for row in rows
    ]

    return {
        "range": range_key,
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": pages,
    }


def clear_usage() -> int:
    """清空全部统计记录，返回删除条数。"""
    conn = _get_conn()
    with conn:
        cursor = conn.execute("DELETE FROM token_usage")
        deleted = cursor.rowcount
    logger.info("Cleared %d token usage records", deleted)
    return int(deleted or 0)
