"""SQLite persistence for Bluefish.

Tables
------
meta          key/value store for small runtime facts (learn timestamps, etc.)
self_profile  the learned "self": one row per known-good signature
self_numeric  learned distributions of numeric features (mean/stddev)
events        a rolling record of observed events (antigens)
alerts        raised alerts with detector scores and (optional) LLM verdict
memory        confirmed-threat signatures (immune memory cells)

The store is deliberately simple and synchronous. A single daemon process
writes; the CLI mostly reads. WAL mode keeps concurrent readers unblocked.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS self_profile (
    signature   TEXT PRIMARY KEY,
    source      TEXT NOT NULL,
    first_seen  REAL NOT NULL,
    last_seen   REAL NOT NULL,
    count       INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS self_numeric (
    name    TEXT PRIMARY KEY,
    n       INTEGER NOT NULL,
    mean    REAL NOT NULL,
    m2      REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ts         REAL NOT NULL,
    source     TEXT NOT NULL,
    signature  TEXT NOT NULL,
    raw        TEXT NOT NULL,
    features   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);

CREATE TABLE IF NOT EXISTS alerts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            REAL NOT NULL,
    signature     TEXT NOT NULL,
    source        TEXT NOT NULL,
    severity      TEXT NOT NULL,
    novelty       REAL NOT NULL,
    inflammation  REAL NOT NULL,
    reasons       TEXT NOT NULL,
    raw           TEXT NOT NULL,
    verdict       TEXT,
    confidence    REAL,
    analysis      TEXT,
    actions       TEXT,
    from_memory   INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_alerts_ts ON alerts(ts);

CREATE TABLE IF NOT EXISTS memory (
    signature   TEXT PRIMARY KEY,
    verdict     TEXT NOT NULL,
    severity    TEXT NOT NULL,
    reason      TEXT NOT NULL,
    created_at  REAL NOT NULL,
    hits        INTEGER NOT NULL DEFAULT 0,
    last_hit    REAL
);
"""


class Store:
    """A thin, synchronous wrapper over the Bluefish SQLite database."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # --- meta -----------------------------------------------------------
    def set_meta(self, key: str, value: Any) -> None:
        self._conn.execute(
            "INSERT INTO meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, json.dumps(value)),
        )
        self._conn.commit()

    def get_meta(self, key: str, default: Any = None) -> Any:
        row = self._conn.execute(
            "SELECT value FROM meta WHERE key=?", (key,)
        ).fetchone()
        return json.loads(row["value"]) if row else default

    # --- self profile: signatures --------------------------------------
    def add_self_signatures(self, entries: Iterable[tuple[str, str]]) -> int:
        """Record (signature, source) pairs as self. Returns rows touched."""
        now = time.time()
        cur = self._conn.executemany(
            "INSERT INTO self_profile(signature, source, first_seen, last_seen, count) "
            "VALUES(?, ?, ?, ?, 1) "
            "ON CONFLICT(signature) DO UPDATE SET "
            "last_seen=excluded.last_seen, count=count+1",
            [(sig, src, now, now) for sig, src in entries],
        )
        self._conn.commit()
        return cur.rowcount

    def is_self_signature(self, signature: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM self_profile WHERE signature=?", (signature,)
        ).fetchone()
        return row is not None

    def self_signature_count(self) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS c FROM self_profile"
        ).fetchone()
        return int(row["c"])

    # --- self profile: numeric distributions ---------------------------
    def update_numeric(self, name: str, value: float) -> None:
        """Update a running mean/variance (Welford) for a numeric feature."""
        row = self._conn.execute(
            "SELECT n, mean, m2 FROM self_numeric WHERE name=?", (name,)
        ).fetchone()
        if row is None:
            n, mean, m2 = 1, float(value), 0.0
        else:
            n = row["n"] + 1
            delta = value - row["mean"]
            mean = row["mean"] + delta / n
            m2 = row["m2"] + delta * (value - mean)
        self._conn.execute(
            "INSERT INTO self_numeric(name, n, mean, m2) VALUES(?, ?, ?, ?) "
            "ON CONFLICT(name) DO UPDATE SET n=excluded.n, mean=excluded.mean, m2=excluded.m2",
            (name, n, mean, m2),
        )
        self._conn.commit()

    def get_numeric(self, name: str) -> tuple[int, float, float] | None:
        """Return (n, mean, stddev) for a numeric feature, or None."""
        row = self._conn.execute(
            "SELECT n, mean, m2 FROM self_numeric WHERE name=?", (name,)
        ).fetchone()
        if row is None:
            return None
        n = row["n"]
        variance = row["m2"] / n if n > 0 else 0.0
        return n, row["mean"], variance ** 0.5

    # --- events ---------------------------------------------------------
    def add_event(
        self, ts: float, source: str, signature: str, raw: str, features: dict
    ) -> int:
        cur = self._conn.execute(
            "INSERT INTO events(ts, source, signature, raw, features) VALUES(?,?,?,?,?)",
            (ts, source, signature, raw, json.dumps(features)),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def prune_events(self, keep: int = 10000) -> None:
        """Keep only the most recent ``keep`` events."""
        self._conn.execute(
            "DELETE FROM events WHERE id NOT IN "
            "(SELECT id FROM events ORDER BY id DESC LIMIT ?)",
            (keep,),
        )
        self._conn.commit()

    # --- alerts ---------------------------------------------------------
    def add_alert(self, alert: dict) -> int:
        cur = self._conn.execute(
            "INSERT INTO alerts(ts, signature, source, severity, novelty, "
            "inflammation, reasons, raw, verdict, confidence, analysis, actions, "
            "from_memory) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                alert["ts"],
                alert["signature"],
                alert["source"],
                alert["severity"],
                alert["novelty"],
                alert["inflammation"],
                json.dumps(alert.get("reasons", [])),
                alert.get("raw", ""),
                alert.get("verdict"),
                alert.get("confidence"),
                alert.get("analysis"),
                json.dumps(alert.get("actions", [])) if alert.get("actions") else None,
                1 if alert.get("from_memory") else 0,
            ),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def get_alert(self, alert_id: int) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM alerts WHERE id=?", (alert_id,)
        ).fetchone()
        return _alert_row_to_dict(row) if row else None

    def recent_alerts(self, limit: int = 20) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM alerts ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [_alert_row_to_dict(r) for r in rows]

    def alert_count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) AS c FROM alerts").fetchone()
        return int(row["c"])

    # --- memory ---------------------------------------------------------
    def remember(
        self, signature: str, verdict: str, severity: str, reason: str
    ) -> None:
        self._conn.execute(
            "INSERT INTO memory(signature, verdict, severity, reason, created_at) "
            "VALUES(?,?,?,?,?) "
            "ON CONFLICT(signature) DO UPDATE SET "
            "verdict=excluded.verdict, severity=excluded.severity, reason=excluded.reason",
            (signature, verdict, severity, reason, time.time()),
        )
        self._conn.commit()

    def recall(self, signature: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM memory WHERE signature=?", (signature,)
        ).fetchone()
        if row is None:
            return None
        # Record the hit (secondary-response bookkeeping).
        self._conn.execute(
            "UPDATE memory SET hits=hits+1, last_hit=? WHERE signature=?",
            (time.time(), signature),
        )
        self._conn.commit()
        return dict(row)

    def memory_entries(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM memory ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def _alert_row_to_dict(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["reasons"] = json.loads(data["reasons"]) if data.get("reasons") else []
    data["actions"] = json.loads(data["actions"]) if data.get("actions") else []
    data["from_memory"] = bool(data.get("from_memory"))
    return data
