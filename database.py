"""
database.py
───────────
SQLite database handler.

RENDER NOTE:
  Render's free tier does NOT have persistent disk storage.
  This means the SQLite database resets every time the app restarts.
  
  For now this is fine — scan history is stored per-session.
  
  When you upgrade to a paid plan or Step 6 (User Accounts),
  swap SQLite for PostgreSQL using Render's free Postgres addon:
    pip install asyncpg databases
    Change DB_URL to: postgresql://user:pass@host/dbname
"""
from __future__ import annotations
import os, sqlite3, json, time
from pathlib import Path
from typing import Optional

# On Render, use /tmp for writable storage (it survives the session)
# Locally, use the project folder
if os.environ.get("ENVIRONMENT") == "production":
    DB_PATH = Path("/tmp/webpulse.db")
else:
    DB_PATH = Path(__file__).parent / "webpulse.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create tables if they don't exist. Safe to call multiple times."""
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS scans (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                url               TEXT    NOT NULL,
                scanned_at        REAL    NOT NULL,
                duration_ms       REAL    NOT NULL,
                status            TEXT    NOT NULL DEFAULT 'completed',
                error_msg         TEXT,
                score_overall     INTEGER,
                score_seo         INTEGER,
                score_bugs        INTEGER,
                score_performance INTEGER,
                issues_high       INTEGER DEFAULT 0,
                issues_medium     INTEGER DEFAULT 0,
                issues_low        INTEGER DEFAULT 0,
                result_json       TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_scans_url        ON scans(url);
            CREATE INDEX IF NOT EXISTS idx_scans_scanned_at ON scans(scanned_at DESC);
        """)


def save_scan(url: str, duration_ms: float, result: dict,
              status: str = "completed", error_msg: Optional[str] = None) -> int:
    scores = result.get("scores", {})
    counts = result.get("issue_counts", {})
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO scans "
            "(url,scanned_at,duration_ms,status,error_msg,"
            "score_overall,score_seo,score_bugs,score_performance,"
            "issues_high,issues_medium,issues_low,result_json) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (url, time.time(), round(duration_ms, 1), status, error_msg,
             scores.get("overall"), scores.get("seo"),
             scores.get("bugs"), scores.get("performance"),
             counts.get("High", 0), counts.get("Medium", 0), counts.get("Low", 0),
             json.dumps(result))
        )
        return cursor.lastrowid


def get_recent_scans(limit: int = 20) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id,url,scanned_at,duration_ms,status,"
            "score_overall,score_seo,score_bugs,score_performance,"
            "issues_high,issues_medium,issues_low "
            "FROM scans ORDER BY scanned_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(row) for row in rows]


def get_scan_by_id(scan_id: int) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM scans WHERE id=?", (scan_id,)
        ).fetchone()
    if not row:
        return None
    result = dict(row)
    if result.get("result_json"):
        result["result"] = json.loads(result["result_json"])
    return result
