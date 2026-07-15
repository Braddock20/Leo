"""SQLite models and helpers. Tiny ORM-less layer to keep deps minimal."""
import sqlite3
import json
import threading
from datetime import datetime, timezone
from contextlib import contextmanager
from .config import Config

_LOCK = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions_meta (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_username TEXT UNIQUE NOT NULL,
    encrypted_cookies TEXT NOT NULL,
    ig_user_id TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,           -- like | follow | unfollow | dm | story_view | post
    status TEXT NOT NULL,         -- pending | running | done | failed | cancelled
    payload TEXT NOT NULL,        -- JSON
    scheduled_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    result TEXT,
    error TEXT,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_jobs_status_sched ON jobs(status, scheduled_at);

CREATE TABLE IF NOT EXISTS action_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day TEXT NOT NULL,            -- YYYY-MM-DD
    kind TEXT NOT NULL,
    target TEXT,
    success INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_action_log_day ON action_log(day, kind);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


@contextmanager
def get_conn():
    with _LOCK:
        conn = sqlite3.connect(Config.DB_PATH, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        try:
            yield conn
        finally:
            conn.close()


def init_db():
    with get_conn() as c:
        c.executescript(SCHEMA)


def add_action(day: str, kind: str, target: str, success: bool):
    with get_conn() as c:
        c.execute(
            "INSERT INTO action_log(day, kind, target, success, created_at) VALUES (?,?,?,?,?)",
            (day, kind, target, 1 if success else 0, _now()),
        )


def count_actions_today(kind: str) -> int:
    from datetime import date
    day = date.today().isoformat()
    with get_conn() as c:
        row = c.execute(
            "SELECT COUNT(*) AS n FROM action_log WHERE day=? AND kind=? AND success=1",
            (day, kind),
        ).fetchone()
        return int(row["n"]) if row else 0
