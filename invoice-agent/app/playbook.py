"""Versioned playbook (learned rules). Exactly one version is 'active' at a time."""
from __future__ import annotations

import json

from . import db
from .models import DEFAULT_PLAYBOOK, Playbook


def _ensure_seed() -> None:
    if not db.one("SELECT version FROM playbooks LIMIT 1"):
        db.execute(
            "INSERT INTO playbooks (version, created_at, status, rules_json, rationale) VALUES (1, ?, 'active', ?, ?)",
            (db.now_iso(), DEFAULT_PLAYBOOK.model_dump_json(), "Initial hand-written playbook"),
        )


def get_active() -> tuple[int, Playbook]:
    _ensure_seed()
    row = db.one("SELECT version, rules_json FROM playbooks WHERE status='active' ORDER BY version DESC LIMIT 1")
    assert row is not None
    return row["version"], Playbook.model_validate_json(row["rules_json"])


def get(version: int) -> Playbook | None:
    row = db.one("SELECT rules_json FROM playbooks WHERE version=?", (version,))
    return Playbook.model_validate_json(row["rules_json"]) if row else None


def list_versions() -> list[dict]:
    _ensure_seed()
    out = db.rows("SELECT * FROM playbooks ORDER BY version DESC")
    for r in out:
        r["rules"] = json.loads(r.pop("rules_json"))
        r["eval_details"] = db.jloads(r.get("eval_details"), {})
    return out


def save_candidate(pb: Playbook, parent: int, rationale: str, score: float | None,
                   baseline: float | None, details: dict, status: str = "candidate") -> int:
    _ensure_seed()
    version = (db.one("SELECT MAX(version) AS v FROM playbooks") or {"v": 0})["v"] + 1
    db.execute(
        "INSERT INTO playbooks (version, created_at, status, parent_version, rules_json, rationale, eval_score,"
        " baseline_score, eval_details) VALUES (?,?,?,?,?,?,?,?,?)",
        (version, db.now_iso(), status, parent, pb.model_dump_json(), rationale, score, baseline, json.dumps(details)),
    )
    return version


def activate(version: int) -> None:
    if not db.one("SELECT version FROM playbooks WHERE version=?", (version,)):
        raise ValueError(f"Playbook v{version} does not exist")
    with db.tx() as conn:
        conn.execute("UPDATE playbooks SET status='archived' WHERE status='active'")
        conn.execute("UPDATE playbooks SET status='active' WHERE version=?", (version,))


def reject(version: int) -> None:
    db.execute("UPDATE playbooks SET status='rejected' WHERE version=? AND status='candidate'", (version,))


def render_for_extraction(pb: Playbook) -> str:
    lines = ["## Extraction rules (learned from accounts-team feedback)"]
    lines += [f"- {r}" for r in pb.extraction_rules]
    if pb.supplier_rules:
        lines.append("\n## Supplier-specific rules (apply when supplier name or sender matches)")
        lines += [f"- [{r.supplier_match}] {r.rule}" for r in pb.supplier_rules]
    return "\n".join(lines)


def is_excluded(pb: Playbook, supplier: str, supplier_email: str | None = None) -> bool:
    hay = f"{supplier} {supplier_email or ''}".lower()
    return any(x.strip().lower() in hay for x in pb.excluded_suppliers if x.strip())
