import json
import sqlite3
import threading
import time
from dataclasses import dataclass
from typing import Any, Iterable

from app.config import settings


_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id            TEXT PRIMARY KEY,
    youtube_url   TEXT NOT NULL,
    direction     TEXT,
    status        TEXT NOT NULL,
    created_at    INTEGER NOT NULL,
    updated_at    INTEGER NOT NULL,
    output_path   TEXT,
    failure       TEXT
);

CREATE TABLE IF NOT EXISTS events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    TEXT NOT NULL REFERENCES sessions(id),
    seq           INTEGER NOT NULL,
    type          TEXT NOT NULL,
    payload       TEXT NOT NULL,
    created_at    INTEGER NOT NULL,
    UNIQUE(session_id, seq)
);
CREATE INDEX IF NOT EXISTS events_by_session ON events(session_id, seq);

CREATE TABLE IF NOT EXISTS step_results (
    session_id    TEXT NOT NULL REFERENCES sessions(id),
    step_key      TEXT NOT NULL,
    status        TEXT NOT NULL,
    result        TEXT NOT NULL,
    created_at    INTEGER NOT NULL,
    PRIMARY KEY(session_id, step_key)
);

CREATE TABLE IF NOT EXISTS transcript_cache (
    youtube_url     TEXT NOT NULL,
    clip_start_sec  REAL NOT NULL,
    clip_end_sec    REAL NOT NULL,
    transcript      TEXT NOT NULL,
    created_at      INTEGER NOT NULL,
    PRIMARY KEY(youtube_url, clip_start_sec, clip_end_sec)
);
"""

# Sentinel used in transcript_cache when clip bounds are unspecified — SQLite
# treats NULLs as distinct in PKs, which would defeat the lookup.
_CLIP_UNSET = -1.0


_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def _connect() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(
            str(settings.db_path), check_same_thread=False, isolation_level=None
        )
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA journal_mode=WAL")
        _conn.execute("PRAGMA foreign_keys=ON")
        with _lock:
            _conn.executescript(_SCHEMA)
            for col_def in ("clip_start_sec REAL", "clip_end_sec REAL", "title TEXT"):
                try:
                    _conn.execute(f"ALTER TABLE sessions ADD COLUMN {col_def}")
                except sqlite3.OperationalError:
                    pass
    return _conn


def now() -> int:
    return int(time.time())


@dataclass
class Session:
    id: str
    youtube_url: str
    direction: str | None
    status: str
    created_at: int
    updated_at: int
    output_path: str | None
    failure: str | None
    clip_start_sec: float | None = None
    clip_end_sec: float | None = None
    title: str | None = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Session":
        return cls(**{k: row[k] for k in row.keys()})


@dataclass
class Event:
    id: int
    session_id: str
    seq: int
    type: str
    payload: dict
    created_at: int

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Event":
        return cls(
            id=row["id"],
            session_id=row["session_id"],
            seq=row["seq"],
            type=row["type"],
            payload=json.loads(row["payload"]),
            created_at=row["created_at"],
        )


# ---------- sessions ----------

def create_session(
    session_id: str,
    youtube_url: str,
    direction: str | None,
    clip_start_sec: float | None = None,
    clip_end_sec: float | None = None,
    title: str | None = None,
) -> Session:
    conn = _connect()
    ts = now()
    with _lock:
        conn.execute(
            "INSERT INTO sessions (id, youtube_url, direction, status, created_at, updated_at, clip_start_sec, clip_end_sec, title) "
            "VALUES (?, ?, ?, 'queued', ?, ?, ?, ?, ?)",
            (session_id, youtube_url, direction, ts, ts, clip_start_sec, clip_end_sec, title),
        )
    return get_session(session_id)  # type: ignore


def get_session(session_id: str) -> Session | None:
    conn = _connect()
    row = conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
    return Session.from_row(row) if row else None


def list_sessions(limit: int = 100) -> list[Session]:
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM sessions ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    return [Session.from_row(r) for r in rows]


def update_session(
    session_id: str,
    *,
    status: str | None = None,
    output_path: str | None = None,
    failure: str | None = None,
) -> None:
    conn = _connect()
    fields: list[str] = ["updated_at=?"]
    args: list[Any] = [now()]
    if status is not None:
        fields.append("status=?")
        args.append(status)
    if output_path is not None:
        fields.append("output_path=?")
        args.append(output_path)
    if failure is not None:
        fields.append("failure=?")
        args.append(failure)
    args.append(session_id)
    with _lock:
        conn.execute(f"UPDATE sessions SET {', '.join(fields)} WHERE id=?", args)


# ---------- events ----------

def append_event(session_id: str, type_: str, payload: dict) -> Event:
    conn = _connect()
    ts = now()
    with _lock:
        cur = conn.execute(
            "SELECT COALESCE(MAX(seq), 0) AS m FROM events WHERE session_id=?",
            (session_id,),
        )
        seq = cur.fetchone()["m"] + 1
        conn.execute(
            "INSERT INTO events (session_id, seq, type, payload, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (session_id, seq, type_, json.dumps(payload), ts),
        )
        ev_id = conn.execute("SELECT last_insert_rowid() AS r").fetchone()["r"]
    return Event(id=ev_id, session_id=session_id, seq=seq, type=type_, payload=payload, created_at=ts)


def list_events(session_id: str, after_seq: int = 0) -> list[Event]:
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM events WHERE session_id=? AND seq>? ORDER BY seq ASC",
        (session_id, after_seq),
    ).fetchall()
    return [Event.from_row(r) for r in rows]


# ---------- step_results ----------

def get_step_result(session_id: str, step_key: str) -> dict | None:
    conn = _connect()
    row = conn.execute(
        "SELECT status, result FROM step_results WHERE session_id=? AND step_key=?",
        (session_id, step_key),
    ).fetchone()
    if not row:
        return None
    return {"status": row["status"], "result": json.loads(row["result"])}


def put_step_result(session_id: str, step_key: str, status: str, result: Any) -> None:
    conn = _connect()
    with _lock:
        conn.execute(
            "INSERT OR REPLACE INTO step_results (session_id, step_key, status, result, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (session_id, step_key, status, json.dumps(result), now()),
        )


def list_step_results(session_id: str, prefix: str | None = None) -> list[dict]:
    conn = _connect()
    if prefix:
        rows = conn.execute(
            "SELECT step_key, status, result FROM step_results "
            "WHERE session_id=? AND step_key LIKE ? ORDER BY created_at ASC",
            (session_id, f"{prefix}%"),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT step_key, status, result FROM step_results WHERE session_id=? ORDER BY created_at ASC",
            (session_id,),
        ).fetchall()
    return [
        {"step_key": r["step_key"], "status": r["status"], "result": json.loads(r["result"])}
        for r in rows
    ]


# ---------- transcript_cache ----------

def _clip_key(v: float | None) -> float:
    return _CLIP_UNSET if v is None else float(v)


def get_cached_transcript(
    youtube_url: str,
    clip_start_sec: float | None,
    clip_end_sec: float | None,
) -> dict | None:
    conn = _connect()
    row = conn.execute(
        "SELECT transcript FROM transcript_cache "
        "WHERE youtube_url=? AND clip_start_sec=? AND clip_end_sec=?",
        (youtube_url, _clip_key(clip_start_sec), _clip_key(clip_end_sec)),
    ).fetchone()
    return json.loads(row["transcript"]) if row else None


def put_cached_transcript(
    youtube_url: str,
    clip_start_sec: float | None,
    clip_end_sec: float | None,
    transcript: dict,
) -> None:
    conn = _connect()
    with _lock:
        conn.execute(
            "INSERT OR REPLACE INTO transcript_cache "
            "(youtube_url, clip_start_sec, clip_end_sec, transcript, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                youtube_url,
                _clip_key(clip_start_sec),
                _clip_key(clip_end_sec),
                json.dumps(transcript, ensure_ascii=False),
                now(),
            ),
        )


def init_db() -> None:
    _connect()
