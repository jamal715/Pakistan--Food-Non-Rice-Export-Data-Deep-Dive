from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

SCHEMA = """
CREATE TABLE IF NOT EXISTS ntn_source (
    ntn TEXT NOT NULL,
    chapter TEXT NOT NULL,
    exporter_name TEXT,
    PRIMARY KEY (ntn, chapter, exporter_name)
);
CREATE TABLE IF NOT EXISTS profile (
    ntn TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    payload_json TEXT,
    identity_status TEXT,
    name_match_status TEXT,
    name_match_score REAL,
    raw_html_path TEXT,
    screenshot_path TEXT,
    error TEXT,
    verified_at TEXT
);
CREATE TABLE IF NOT EXISTS business_activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ntn TEXT NOT NULL,
    business_sr TEXT,
    business_name TEXT,
    business_address TEXT,
    activity_code TEXT,
    activity_level_1 TEXT,
    activity_level_2 TEXT,
    activity_detail TEXT,
    principal_activity_raw TEXT
);
CREATE TABLE IF NOT EXISTS run_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ntn TEXT,
    status TEXT NOT NULL,
    message TEXT,
    created_at TEXT NOT NULL
);
"""

@contextmanager
def connect(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def replace_ntn_source(conn: sqlite3.Connection, rows: pd.DataFrame) -> None:
    conn.execute("DELETE FROM ntn_source")
    data = rows[["ntn", "chapter", "exporter_name"]].where(pd.notna(rows), None).itertuples(index=False, name=None)
    conn.executemany("INSERT OR IGNORE INTO ntn_source(ntn, chapter, exporter_name) VALUES (?, ?, ?)", data)


def source_names(conn: sqlite3.Connection, ntn: str) -> list[str]:
    rows = conn.execute("SELECT DISTINCT exporter_name FROM ntn_source WHERE ntn=? AND exporter_name IS NOT NULL", (ntn,)).fetchall()
    return [r[0] for r in rows if r[0]]


def pending_ntns(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        """
        SELECT DISTINCT s.ntn
        FROM ntn_source s
        LEFT JOIN profile p ON p.ntn=s.ntn AND p.status='complete'
        WHERE p.ntn IS NULL
        ORDER BY CAST(s.ntn AS INTEGER), s.ntn
        """
    ).fetchall()
    return [r[0] for r in rows]


def upsert_profile(conn: sqlite3.Connection, ntn: str, status: str, payload: dict | None = None,
                   identity_status: str | None = None, name_match_status: str | None = None,
                   name_match_score: float | None = None, raw_html_path: str | None = None,
                   screenshot_path: str | None = None, error: str | None = None) -> None:
    conn.execute(
        """
        INSERT INTO profile(ntn,status,payload_json,identity_status,name_match_status,name_match_score,
                            raw_html_path,screenshot_path,error,verified_at)
        VALUES(?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(ntn) DO UPDATE SET
            status=excluded.status,
            payload_json=excluded.payload_json,
            identity_status=excluded.identity_status,
            name_match_status=excluded.name_match_status,
            name_match_score=excluded.name_match_score,
            raw_html_path=excluded.raw_html_path,
            screenshot_path=excluded.screenshot_path,
            error=excluded.error,
            verified_at=excluded.verified_at
        """,
        (ntn, status, json.dumps(payload or {}, ensure_ascii=False), identity_status, name_match_status,
         name_match_score, raw_html_path, screenshot_path, error, now_iso()),
    )


def replace_activities(conn: sqlite3.Connection, ntn: str, activities: pd.DataFrame) -> None:
    conn.execute("DELETE FROM business_activity WHERE ntn=?", (ntn,))
    if activities.empty:
        return
    cols = ["ntn", "business_sr", "business_name", "business_address", "activity_code",
            "activity_level_1", "activity_level_2", "activity_detail", "principal_activity_raw"]
    rows = activities[cols].where(pd.notna(activities), None).itertuples(index=False, name=None)
    conn.executemany(
        """
        INSERT INTO business_activity(ntn,business_sr,business_name,business_address,activity_code,
                                      activity_level_1,activity_level_2,activity_detail,principal_activity_raw)
        VALUES(?,?,?,?,?,?,?,?,?)
        """,
        rows,
    )


def log(conn: sqlite3.Connection, ntn: str | None, status: str, message: str = "") -> None:
    conn.execute("INSERT INTO run_log(ntn,status,message,created_at) VALUES(?,?,?,?)",
                 (ntn, status, message, now_iso()))
