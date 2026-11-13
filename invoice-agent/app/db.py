"""SQLite storage. One file, WAL mode, safe for the single-process deployment."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from .config import get_settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS mail_state (
    folder TEXT PRIMARY KEY,
    uidvalidity INTEGER NOT NULL,
    last_uid INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS emails (
    id INTEGER PRIMARY KEY,
    message_id TEXT UNIQUE NOT NULL,
    folder TEXT, uid INTEGER,
    from_addr TEXT, subject TEXT, received_at TEXT,
    body_text TEXT,
    status TEXT NOT NULL DEFAULT 'new',   -- new | skipped | processed | not_invoice | error
    classification TEXT,
    error TEXT,
    playbook_version INTEGER,
    processed_at TEXT
);

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    email_id INTEGER NOT NULL REFERENCES emails(id),
    filename TEXT, mime TEXT, sha256 TEXT, path TEXT
);

CREATE TABLE IF NOT EXISTS invoices (
    id INTEGER PRIMARY KEY,
    email_id INTEGER REFERENCES emails(id),
    doc_type TEXT NOT NULL DEFAULT 'invoice',  -- invoice | credit_note
    supplier TEXT NOT NULL,
    supplier_key TEXT NOT NULL,
    supplier_email TEXT,
    invoice_number TEXT NOT NULL,
    invoice_number_key TEXT NOT NULL,
    invoice_date TEXT,
    due_date TEXT,
    due_date_source TEXT,                       -- stated | terms | default
    currency TEXT NOT NULL DEFAULT 'GBP',
    net_amount REAL, vat_amount REAL, total_amount REAL,
    amount_due REAL NOT NULL,
    payment_terms TEXT, payment_reference TEXT, bank_details TEXT, po_number TEXT,
    description TEXT, category TEXT,
    status TEXT NOT NULL DEFAULT 'unpaid',      -- unpaid | paid | disputed | ignored
    paid_at TEXT,
    confidence REAL,
    needs_review INTEGER NOT NULL DEFAULT 0,
    review_reasons TEXT,                        -- json list
    extracted_json TEXT,
    locked_fields TEXT NOT NULL DEFAULT '[]',   -- fields a human corrected; never overwritten by re-extraction
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (supplier_key, invoice_number_key)
);

CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,
    as_of TEXT NOT NULL,
    html_path TEXT, pdf_path TEXT,
    summary_json TEXT,
    share_token TEXT UNIQUE,
    playbook_version INTEGER
);

CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,
    source TEXT NOT NULL,          -- web | telegram | agent
    author TEXT,
    kind TEXT NOT NULL,            -- field_correction | classification | report | general
    target_type TEXT, target_id INTEGER,
    field TEXT, old_value TEXT, new_value TEXT,
    comment TEXT,
    used_in_version INTEGER        -- playbook version that consumed it (NULL = pending)
);

CREATE TABLE IF NOT EXISTS playbooks (
    version INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL,          -- active | candidate | rejected | archived
    parent_version INTEGER,
    rules_json TEXT NOT NULL,
    rationale TEXT,
    eval_score REAL,
    baseline_score REAL,
    eval_details TEXT
);

CREATE TABLE IF NOT EXISTS eval_cases (
    id INTEGER PRIMARY KEY,
    email_id INTEGER UNIQUE NOT NULL REFERENCES emails(id),
    expected_json TEXT NOT NULL,   -- {"is_payable": bool, "invoices": [{field: value}]}
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_sessions (
    chat_key TEXT PRIMARY KEY,
    agent_session_id TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT,
    ok INTEGER, summary TEXT
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(get_settings().db_path, timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def tx() -> Iterator[sqlite3.Connection]:
    """Connection inside an explicit transaction (commit on success, rollback on error)."""
    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def init_db() -> None:
    conn = connect()
    try:
        conn.executescript(SCHEMA)
    finally:
        conn.close()


def rows(sql: str, params: tuple | dict = ()) -> list[dict[str, Any]]:
    conn = connect()
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def one(sql: str, params: tuple | dict = ()) -> dict[str, Any] | None:
    r = rows(sql, params)
    return r[0] if r else None


def execute(sql: str, params: tuple | dict = ()) -> int:
    conn = connect()
    try:
        cur = conn.execute(sql, params)
        return cur.lastrowid or cur.rowcount
    finally:
        conn.close()


def jloads(value: str | None, default: Any = None) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default
