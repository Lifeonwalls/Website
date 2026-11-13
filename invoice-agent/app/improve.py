"""Self-improvement harness.

Loop:  feedback  ->  eval cases  ->  optimizer proposes a new playbook  ->  replay evals
       ->  accept only if the score does not drop and no previously-passing case breaks
       ->  human approval (default) or auto-apply  ->  re-run extraction on invoices still needing review.

Every human correction is turned into a regression test (see invoices.refresh_eval_case), so the
agent can only "learn" a rule if it fixes the reported mistake without breaking anything it got right before.
"""
from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from . import db, extract, llm, pipeline, playbook
from .config import get_settings
from .invoices import PAYABLE_CLASSES, invoice_number_key, parse_date, resolve_due_date, supplier_key
from .models import EmailExtraction, Playbook, PlaybookProposal

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------
def _field_match(field: str, expected: Any, actual: Any) -> bool:
    if expected is None:
        return True
    if actual is None:
        return False
    if field in ("total_amount", "amount_due", "net_amount", "vat_amount"):
        try:
            return abs(abs(float(expected)) - abs(float(actual))) <= 0.01
        except (TypeError, ValueError):
            return False
    if field in ("invoice_date", "due_date"):
        return parse_date(expected) == parse_date(actual)
    if field == "supplier":
        a, b = supplier_key(str(expected)), supplier_key(str(actual))
        return a == b or (min(len(a), len(b)) >= 4 and (a in b or b in a))
    if field == "invoice_number":
        return invoice_number_key(str(expected)) == invoice_number_key(str(actual))
    return str(expected).strip().lower() == str(actual).strip().lower()


def score_case(expected: dict, actual: EmailExtraction, received_at: str | None = None) -> dict:
    predicted = []
    if actual.classification in PAYABLE_CLASSES:
        default_days = get_settings().default_payment_terms_days
        for inv in actual.invoices:
            d = inv.model_dump()
            # Compare the due date the system would actually store (stated, or derived from terms).
            d["due_date"] = resolve_due_date(inv, received_at, default_days)[0].isoformat()
            predicted.append(d)
    if not expected.get("is_payable"):
        ok = not predicted
        return {"score": 1.0 if ok else 0.0, "passed": ok,
                "diffs": [] if ok else [f"Should not be a payable; model returned {len(predicted)} invoice(s) "
                                        f"as '{actual.classification}'"]}
    diffs: list[str] = []
    total = matched = 0
    remaining = list(predicted)
    for exp in expected["invoices"]:
        match = next((p for p in remaining if _field_match("invoice_number", exp.get("invoice_number"),
                                                           p.get("invoice_number"))), None)
        if match is None:
            match = next((p for p in remaining if _field_match("amount_due", exp.get("amount_due"), p.get("amount_due"))), None)
        fields = [f for f in exp if exp[f] is not None]
        total += len(fields)
        if match is None:
            diffs.append(f"Missed invoice {exp.get('invoice_number')} from {exp.get('supplier')}")
            continue
        remaining.remove(match)
        for f in fields:
            actual_val = match.get(f)
            if _field_match(f, exp[f], actual_val):
                matched += 1
            else:
                diffs.append(f"{exp.get('invoice_number')}: {f} expected {exp[f]!r}, got {actual_val!r}")
    if remaining:
        total += 2 * len(remaining)
        diffs += [f"Unexpected extra invoice {p.get('invoice_number')} ({p.get('supplier')})" for p in remaining]
    score = matched / total if total else 1.0
    return {"score": round(score, 4), "passed": not diffs, "diffs": diffs}


def evaluate(pb: Playbook, cases: list[dict], workers: int = 4) -> dict:
    def run(case: dict) -> tuple[int, dict]:
        try:
            result = extract.extract_email(case["email_id"], pb)
            received = (db.one("SELECT received_at FROM emails WHERE id=?", (case["email_id"],)) or {}).get("received_at")
            return case["email_id"], score_case(json.loads(case["expected_json"]), result, received)
        except Exception as e:  # an API failure counts as a failed case but is labelled
            return case["email_id"], {"score": 0.0, "passed": False, "diffs": [f"error: {e}"], "error": True}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        per_case = dict(pool.map(run, cases))
    score = sum(c["score"] for c in per_case.values()) / len(per_case) if per_case else None
    return {"score": round(score, 4) if score is not None else None,
            "passed": sum(1 for c in per_case.values() if c["passed"]), "total": len(per_case),
            "cases": {str(k): v for k, v in per_case.items()}}


# ---------------------------------------------------------------------------
# Optimizer
# ---------------------------------------------------------------------------
OPTIMIZER_SYSTEM = """You maintain the "playbook" - the learned instructions for an accounts-payable extraction \
agent at {company} and for its weekly board payables report. You receive the current playbook, new human \
feedback, and the evaluation failures of the current playbook. Produce an improved playbook.

Rules for a good playbook:
- Fix the root cause of each mistake with a GENERAL rule where possible; use a supplier rule only when the \
behaviour is specific to one supplier's documents.
- Never hard-code a specific invoice number, amount or date - the rule must work for future invoices.
- Keep rules that still serve a purpose; merge or delete duplicated or contradicted rules. At most 25 extraction \
rules and 40 supplier rules. Each rule is one or two sentences.
- report_preferences captures how the board/finance team want the report written (from 'report' and 'general' \
feedback). Only add excluded_suppliers if someone explicitly asked to leave a supplier out.
- Ignore feedback that is not about extraction or reporting (e.g. a payment status change).
- If feedback contradicts itself, prefer the most recent.
"""


def _feedback_context(items: list[dict]) -> list[dict]:
    out = []
    for f in items:
        ctx = {k: f[k] for k in ("id", "created_at", "source", "kind", "field", "old_value", "new_value", "comment")
               if f.get(k) is not None}
        if f.get("target_type") == "invoice" and f.get("target_id"):
            inv = db.one("SELECT i.supplier, i.supplier_email, i.invoice_number, e.subject, e.from_addr FROM invoices i"
                         " LEFT JOIN emails e ON e.id=i.email_id WHERE i.id=?", (f["target_id"],))
            if inv:
                ctx["invoice"] = inv
        out.append(ctx)
    return out


def propose(pb: Playbook, feedback: list[dict], baseline: dict) -> PlaybookProposal:
    s = get_settings()
    failures = []
    for email_id, c in baseline.get("cases", {}).items():
        if not c["passed"] and not c.get("error"):
            e = db.one("SELECT from_addr, subject FROM emails WHERE id=?", (int(email_id),)) or {}
            failures.append({"email_id": int(email_id), "from": e.get("from_addr"), "subject": e.get("subject"),
                             "diffs": c["diffs"][:10]})
    payload = {
        "current_playbook": pb.model_dump(),
        "new_feedback": _feedback_context(feedback),
        "current_eval": {"score": baseline.get("score"), "passed": baseline.get("passed"), "total": baseline.get("total"),
                         "failures": failures[:40]},
    }
    return llm.parse(schema=PlaybookProposal, system=OPTIMIZER_SYSTEM.format(company=s.company_name),
                     content="Improve the playbook.\n\n" + json.dumps(payload, default=str, indent=1),
                     model=s.optimizer_model, effort=s.optimizer_effort, max_tokens=16000)


# ---------------------------------------------------------------------------
# Cycle
# ---------------------------------------------------------------------------
def pending_feedback() -> list[dict]:
    return db.rows("SELECT * FROM feedback WHERE used_in_version IS NULL ORDER BY created_at")


def run_improvement_cycle(force: bool = False) -> dict:
    s = get_settings()
    run_id = db.execute("INSERT INTO runs (kind, started_at) VALUES ('improve', ?)", (db.now_iso(),))
    try:
        feedback = pending_feedback()
        version, pb = playbook.get_active()
        cases = db.rows("SELECT * FROM eval_cases ORDER BY updated_at DESC LIMIT ?", (s.eval_max_cases,))
        if len(feedback) < s.min_feedback_for_improvement and not force:
            result = {"status": "skipped", "reason": f"only {len(feedback)} new feedback item(s)", "active_version": version}
            db.execute("UPDATE runs SET finished_at=?, ok=1, summary=? WHERE id=?", (db.now_iso(), json.dumps(result), run_id))
            return result

        baseline = evaluate(pb, cases)
        if not feedback and baseline["total"] and baseline["passed"] == baseline["total"]:
            result = {"status": "skipped", "reason": "no feedback and all eval cases pass", "baseline": baseline["score"]}
            db.execute("UPDATE runs SET finished_at=?, ok=1, summary=? WHERE id=?", (db.now_iso(), json.dumps(result), run_id))
            return result

        proposal = propose(pb, feedback, baseline)
        candidate_eval = evaluate(proposal.playbook, cases)
        regressions = [cid for cid, c in baseline["cases"].items()
                       if c["passed"] and not candidate_eval["cases"].get(cid, {}).get("passed")]
        base_score = baseline["score"] if baseline["score"] is not None else 1.0
        cand_score = candidate_eval["score"] if candidate_eval["score"] is not None else 1.0
        passes_gate = cand_score >= base_score and not regressions
        details = {"baseline": baseline, "candidate": candidate_eval, "regressions": regressions,
                   "feedback_ids": [f["id"] for f in feedback], "addressed": proposal.feedback_ids_addressed}

        if not passes_gate:
            new_v = playbook.save_candidate(proposal.playbook, version, proposal.rationale, cand_score, base_score,
                                            details, status="rejected")
            result = {"status": "rejected_by_eval", "version": new_v, "baseline": base_score, "candidate": cand_score,
                      "regressions": regressions, "rationale": proposal.rationale}
        else:
            status = "active" if s.auto_apply_improvements else "candidate"
            new_v = playbook.save_candidate(proposal.playbook, version, proposal.rationale, cand_score, base_score,
                                            details, status="candidate")
            ids = [f["id"] for f in feedback]
            if ids:
                db.execute(f"UPDATE feedback SET used_in_version=? WHERE id IN ({','.join('?' * len(ids))})", (new_v, *ids))
            reprocessed = 0
            if status == "active":
                reprocessed = apply_version(new_v)
            result = {"status": "activated" if status == "active" else "awaiting_approval", "version": new_v,
                      "baseline": base_score, "candidate": cand_score, "cases": candidate_eval["total"],
                      "rationale": proposal.rationale, "reprocessed_emails": reprocessed}
        db.execute("UPDATE runs SET finished_at=?, ok=1, summary=? WHERE id=?", (db.now_iso(), json.dumps(result), run_id))
        return result
    except Exception as e:
        log.exception("Improvement cycle failed")
        db.execute("UPDATE runs SET finished_at=?, ok=0, summary=? WHERE id=?", (db.now_iso(), str(e), run_id))
        raise


def apply_version(version: int) -> int:
    """Activate a playbook and re-extract emails whose invoices still need review (human-locked fields are kept)."""
    playbook.activate(version)
    emails = db.rows("SELECT DISTINCT e.id FROM emails e LEFT JOIN invoices i ON i.email_id=e.id"
                     " WHERE e.status='error' OR (i.needs_review=1 AND i.status='unpaid')")
    for e in emails:
        pipeline.process_email(e["id"])
    return len(emails)


def describe_diff(old: Playbook, new: Playbook) -> dict:
    def diff(a: list, b: list) -> dict:
        return {"added": [x for x in b if x not in a], "removed": [x for x in a if x not in b]}
    return {
        "extraction_rules": diff(old.extraction_rules, new.extraction_rules),
        "supplier_rules": diff([r.model_dump() for r in old.supplier_rules], [r.model_dump() for r in new.supplier_rules]),
        "report_preferences": diff(old.report_preferences, new.report_preferences),
        "excluded_suppliers": diff(old.excluded_suppliers, new.excluded_suppliers),
    }


def record_feedback(*, source: str, kind: str, comment: str, author: str | None = None,
                    target_type: str | None = None, target_id: int | None = None) -> int:
    if kind not in ("report", "general", "classification", "field_correction"):
        kind = "general"
    return db.execute("INSERT INTO feedback (created_at, source, author, kind, target_type, target_id, comment)"
                      " VALUES (?,?,?,?,?,?,?)", (db.now_iso(), source, author, kind, target_type, target_id, comment))
