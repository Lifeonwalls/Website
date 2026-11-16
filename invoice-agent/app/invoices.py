"""Invoice persistence: normalisation, due-date resolution, upserts and human corrections."""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from typing import Any

from dateutil import parser as dateparser

from . import db
from .config import get_settings
from .models import ExtractedInvoice

PAYABLE_CLASSES = {"invoice_to_pay", "payment_reminder", "statement", "credit_note", "receipt_already_paid"}
EDITABLE_FIELDS = {
    "supplier", "supplier_email", "invoice_number", "invoice_date", "due_date", "currency", "net_amount",
    "vat_amount", "total_amount", "amount_due", "payment_terms", "payment_reference", "bank_details",
    "po_number", "description", "category", "doc_type",
}
STATUS_VALUES = {"unpaid", "paid", "disputed", "ignored"}
EVAL_FIELDS = ["doc_type", "supplier", "invoice_number", "invoice_date", "due_date", "currency",
               "total_amount", "amount_due"]

_SUFFIXES = r"\b(ltd|limited|plc|llp|llc|inc|co|company|uk|the|group|services)\b"


def supplier_key(name: str) -> str:
    s = re.sub(r"[^a-z0-9 ]", " ", (name or "").lower())
    s = re.sub(_SUFFIXES, " ", s)
    return re.sub(r"\s+", "", s) or "unknown"


def invoice_number_key(number: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (number or "").upper()) or "UNKNOWN"


def parse_date(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        try:
            return dateparser.parse(str(value), dayfirst=True).date()
        except (ValueError, OverflowError, TypeError):
            return None


def resolve_due_date(inv: ExtractedInvoice, received_at: str | None, default_days: int) -> tuple[date, str]:
    """Return (due_date, source) where source is stated | terms | default."""
    stated = parse_date(inv.due_date)
    if stated:
        return stated, "stated"
    base = parse_date(inv.invoice_date) or parse_date(received_at) or today_local()
    terms = (inv.payment_terms or "").lower()
    if inv.payment_terms_days is not None and inv.payment_terms_days >= 0:
        return base + timedelta(days=inv.payment_terms_days), "terms"
    if any(k in terms for k in ("on receipt", "immediate", "upon receipt", "due now")):
        return base, "terms"
    return base + timedelta(days=default_days), "default"


def review_reasons(inv: ExtractedInvoice, due_source: str) -> list[str]:
    reasons = list(inv.uncertainties)
    if inv.confidence < 0.7:
        reasons.append(f"Low extraction confidence ({inv.confidence:.0%})")
    if due_source == "default":
        reasons.append("No due date or terms found - default terms assumed")
    if invoice_number_key(inv.invoice_number) == "UNKNOWN":
        reasons.append("Invoice number missing")
    if inv.amount_due <= 0:
        reasons.append("Amount due is zero or negative")
    if inv.net_amount is not None and inv.vat_amount is not None and inv.total_amount is not None:
        if abs(inv.net_amount + inv.vat_amount - inv.total_amount) > 0.05:
            reasons.append("Net + VAT does not equal total")
    return reasons


def upsert_extracted(email_id: int, received_at: str | None, inv: ExtractedInvoice, idx: int) -> int:
    s = get_settings()
    due, due_source = resolve_due_date(inv, received_at, s.default_payment_terms_days)
    reasons = review_reasons(inv, due_source)
    num_key = invoice_number_key(inv.invoice_number)
    if num_key == "UNKNOWN":
        num_key = f"UNKNOWN{email_id}X{idx}"
    sup_key = supplier_key(inv.supplier)
    status = "paid" if inv.already_paid else "unpaid"
    values = {
        "email_id": email_id, "doc_type": inv.doc_type, "supplier": inv.supplier.strip(),
        "supplier_key": sup_key, "supplier_email": inv.supplier_email, "invoice_number": inv.invoice_number.strip(),
        "invoice_number_key": num_key, "invoice_date": (parse_date(inv.invoice_date) or None) and str(parse_date(inv.invoice_date)),
        "due_date": due.isoformat(), "due_date_source": due_source, "currency": (inv.currency or s.base_currency).upper()[:3],
        "net_amount": inv.net_amount, "vat_amount": inv.vat_amount, "total_amount": inv.total_amount,
        "amount_due": abs(inv.amount_due), "payment_terms": inv.payment_terms, "payment_reference": inv.payment_reference,
        "bank_details": inv.bank_details, "po_number": inv.po_number, "description": inv.description,
        "category": inv.category, "confidence": inv.confidence, "needs_review": int(bool(reasons)),
        "review_reasons": json.dumps(reasons), "extracted_json": inv.model_dump_json(),
    }
    now = db.now_iso()
    with db.tx() as conn:
        existing = conn.execute(
            "SELECT id, status, locked_fields FROM invoices WHERE supplier_key=? AND invoice_number_key=?",
            (sup_key, num_key),
        ).fetchone()
        if existing:
            locked = set(json.loads(existing["locked_fields"] or "[]"))
            upd = {k: v for k, v in values.items() if k not in locked and k not in ("supplier_key", "invoice_number_key")}
            if existing["status"] in ("paid", "ignored", "disputed"):
                upd.pop("email_id", None)  # keep provenance, keep human status
            elif status == "paid":
                upd["status"], upd["paid_at"] = "paid", values["invoice_date"] or now[:10]
            sets = ", ".join(f"{k}=?" for k in upd)
            conn.execute(f"UPDATE invoices SET {sets}, updated_at=? WHERE id=?", (*upd.values(), now, existing["id"]))
            return existing["id"]
        cols = list(values) + ["status", "paid_at", "created_at", "updated_at"]
        params = list(values.values()) + [status, (values["invoice_date"] or now[:10]) if status == "paid" else None, now, now]
        cur = conn.execute(f"INSERT INTO invoices ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", params)
        return cur.lastrowid


def mark_paid_by_numbers(numbers: list[str], email_id: int) -> list[str]:
    notes = []
    for n in numbers:
        matches = db.rows("SELECT id, supplier FROM invoices WHERE invoice_number_key=? AND status='unpaid'",
                          (invoice_number_key(n),))
        if len(matches) == 1:
            db.execute("UPDATE invoices SET status='paid', paid_at=?, notes=COALESCE(notes,'') || ?, updated_at=? WHERE id=?",
                       (db.now_iso()[:10], f"\nMarked paid from payment confirmation email #{email_id}.", db.now_iso(),
                        matches[0]["id"]))
            notes.append(f"{n} ({matches[0]['supplier']}) marked paid")
        elif len(matches) > 1:
            notes.append(f"{n}: several unpaid invoices share this number - not changed")
    return notes


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------
def get_invoice(invoice_id: int) -> dict | None:
    r = db.one("SELECT i.*, e.subject AS email_subject, e.from_addr AS email_from FROM invoices i"
               " LEFT JOIN emails e ON e.id=i.email_id WHERE i.id=?", (invoice_id,))
    if r:
        r["review_reasons"] = db.jloads(r["review_reasons"], [])
        r["locked_fields"] = db.jloads(r["locked_fields"], [])
    return r


def find_invoices(search: str | None = None, status: str | None = "unpaid", due_within_days: int | None = None,
                  overdue_only: bool = False, needs_review: bool | None = None, limit: int = 200) -> list[dict]:
    sql = ["SELECT * FROM invoices WHERE 1=1"]
    params: list[Any] = []
    if status:
        sql.append("AND status=?")
        params.append(status)
    if search:
        sql.append("AND (supplier LIKE ? OR invoice_number LIKE ? OR description LIKE ? OR po_number LIKE ?)")
        params += [f"%{search}%"] * 4
    today = today_local()
    if overdue_only:
        sql.append("AND due_date < ?")
        params.append(today.isoformat())
    elif due_within_days is not None:
        sql.append("AND due_date <= ?")
        params.append((today + timedelta(days=due_within_days)).isoformat())
    if needs_review is not None:
        sql.append("AND needs_review=?")
        params.append(int(needs_review))
    sql.append("ORDER BY due_date ASC, amount_due DESC LIMIT ?")
    params.append(limit)
    out = db.rows(" ".join(sql), tuple(params))
    for r in out:
        r["review_reasons"] = db.jloads(r["review_reasons"], [])
    return out


# ---------------------------------------------------------------------------
# Human actions (each one feeds the self-improvement loop)
# ---------------------------------------------------------------------------
def _coerce(field: str, value: Any) -> Any:
    if value in ("", None):
        return None
    if field in ("net_amount", "vat_amount", "total_amount", "amount_due"):
        return round(float(str(value).replace(",", "").replace("£", "").strip()), 2)
    if field in ("invoice_date", "due_date"):
        d = parse_date(value)
        if not d:
            raise ValueError(f"Cannot read date '{value}' for {field}")
        return d.isoformat()
    if field == "doc_type" and value not in ("invoice", "credit_note"):
        raise ValueError("doc_type must be invoice or credit_note")
    if field == "currency":
        return str(value).upper()[:3]
    return str(value).strip()


def update_invoice(invoice_id: int, changes: dict[str, Any], *, source: str, author: str | None = None,
                   comment: str | None = None) -> dict:
    inv = get_invoice(invoice_id)
    if not inv:
        raise ValueError(f"Invoice {invoice_id} not found")
    unknown = set(changes) - EDITABLE_FIELDS - {"status", "notes"}
    if unknown:
        raise ValueError(f"Fields not editable: {', '.join(sorted(unknown))}")
    now = db.now_iso()
    applied: dict[str, Any] = {}
    locked = set(inv["locked_fields"])
    extraction_changed = False
    for field, raw in changes.items():
        if field == "status":
            if raw not in STATUS_VALUES:
                raise ValueError(f"status must be one of {sorted(STATUS_VALUES)}")
            new = raw
        elif field == "notes":
            new = str(raw)
        else:
            new = _coerce(field, raw)
        old = inv.get(field)
        if str(old if old is not None else "") == str(new if new is not None else ""):
            continue
        applied[field] = new
        if field in EDITABLE_FIELDS:
            locked.add(field)
            extraction_changed = True
            db.execute("INSERT INTO feedback (created_at, source, author, kind, target_type, target_id, field, old_value,"
                       " new_value, comment) VALUES (?,?,?,?,?,?,?,?,?,?)",
                       (now, source, author, "field_correction", "invoice", invoice_id, field,
                        None if old is None else str(old), None if new is None else str(new), comment))
        elif field == "status" and new == "ignored":
            extraction_changed = True
            db.execute("INSERT INTO feedback (created_at, source, author, kind, target_type, target_id, field, old_value,"
                       " new_value, comment) VALUES (?,?,?,?,?,?,?,?,?,?)",
                       (now, source, author, "classification", "invoice", invoice_id, "status", old, new,
                        comment or "Marked as not a payable invoice"))
    if not applied:
        return inv
    if "supplier" in applied:
        applied["supplier_key"] = supplier_key(applied["supplier"])
    if "invoice_number" in applied:
        applied["invoice_number_key"] = invoice_number_key(applied["invoice_number"])
    if "due_date" in applied:
        applied["due_date_source"] = "stated"
    if applied.get("status") == "paid":
        applied["paid_at"] = now[:10]
    if extraction_changed:
        applied["needs_review"] = 0
    applied["locked_fields"] = json.dumps(sorted(locked))
    sets = ", ".join(f"{k}=?" for k in applied)
    db.execute(f"UPDATE invoices SET {sets}, updated_at=? WHERE id=?", (*applied.values(), now, invoice_id))
    if extraction_changed and inv.get("email_id"):
        refresh_eval_case(inv["email_id"])
    return get_invoice(invoice_id)  # type: ignore[return-value]


def confirm_invoice(invoice_id: int, *, source: str, author: str | None = None) -> dict:
    """A human says the extraction is correct: becomes a positive regression test."""
    inv = get_invoice(invoice_id)
    if not inv:
        raise ValueError(f"Invoice {invoice_id} not found")
    db.execute("UPDATE invoices SET needs_review=0, locked_fields=?, updated_at=? WHERE id=?",
               (json.dumps(sorted(set(inv["locked_fields"]) | {"_confirmed"})), db.now_iso(), invoice_id))
    if inv.get("email_id"):
        refresh_eval_case(inv["email_id"])
    return get_invoice(invoice_id)  # type: ignore[return-value]


def create_manual_invoice(fields: dict[str, Any], *, email_id: int | None, source: str,
                          author: str | None = None, comment: str | None = None) -> dict:
    """Add an invoice the extractor missed."""
    data = {k: _coerce(k, v) for k, v in fields.items() if k in EDITABLE_FIELDS}
    for req in ("supplier", "invoice_number", "amount_due", "due_date"):
        if data.get(req) in (None, ""):
            raise ValueError(f"{req} is required")
    now = db.now_iso()
    data.update({
        "email_id": email_id, "supplier_key": supplier_key(data["supplier"]),
        "invoice_number_key": invoice_number_key(data["invoice_number"]), "due_date_source": "stated",
        "currency": data.get("currency") or get_settings().base_currency, "doc_type": data.get("doc_type") or "invoice",
        "status": "unpaid", "confidence": 1.0, "needs_review": 0, "review_reasons": "[]",
        "locked_fields": json.dumps(sorted(EDITABLE_FIELDS & set(fields))), "notes": comment,
        "created_at": now, "updated_at": now,
    })
    cols = list(data)
    new_id = db.execute(f"INSERT INTO invoices ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                        tuple(data.values()))
    db.execute("INSERT INTO feedback (created_at, source, author, kind, target_type, target_id, comment)"
               " VALUES (?,?,?,?,?,?,?)", (now, source, author, "classification", "invoice", new_id,
                                           comment or "Invoice was missed by the extractor and added manually"))
    if email_id:
        db.execute("UPDATE emails SET status='processed' WHERE id=? AND status IN ('not_invoice','skipped')", (email_id,))
        refresh_eval_case(email_id)
    return get_invoice(new_id)  # type: ignore[return-value]


def refresh_eval_case(email_id: int) -> None:
    """Rebuild the expected output for an email from its human-reviewed invoices."""
    invs = db.rows("SELECT * FROM invoices WHERE email_id=? AND status!='ignored'", (email_id,))
    expected_invoices = []
    for i in invs:
        locked = set(db.jloads(i["locked_fields"], []))
        exp = {f: i[f] for f in EVAL_FIELDS if i.get(f) is not None}
        if i.get("due_date_source") != "stated" and "due_date" not in locked:
            exp.pop("due_date", None)  # only test due dates that were printed or human-confirmed
        expected_invoices.append(exp)
    expected = {"is_payable": bool(expected_invoices), "invoices": expected_invoices}
    now = db.now_iso()
    db.execute("INSERT INTO eval_cases (email_id, expected_json, created_at, updated_at) VALUES (?,?,?,?)"
               " ON CONFLICT(email_id) DO UPDATE SET expected_json=excluded.expected_json, updated_at=excluded.updated_at",
               (email_id, json.dumps(expected), now, now))


def today_local() -> date:
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo(get_settings().timezone)).date()


def mark_paid(*, numbers: list[str], suppliers: list[str], ids: list[int], paid_date: str | None,
              source: str, author: str | None, comment: str | None) -> dict:
    """Mark invoices paid by invoice number (as typed by a person) and/or id. Never guesses between matches."""
    when = (parse_date(paid_date) or today_local()).isoformat() if paid_date else today_local().isoformat()
    marked, already, not_found, ambiguous = [], [], [], []
    targets: list[int] = list(ids)
    for i, raw in enumerate(numbers):
        key = invoice_number_key(raw)
        rows = db.rows("SELECT id, supplier, invoice_number, status, amount_due, currency FROM invoices "
                       "WHERE invoice_number_key=? AND status != 'ignored'", (key,))
        if len(rows) > 1 and i < len(suppliers) and suppliers[i]:
            sk = supplier_key(suppliers[i])
            rows = [r for r in rows if sk in supplier_key(r["supplier"]) or supplier_key(r["supplier"]) in sk]
        unpaid = [r for r in rows if r["status"] != "paid"]
        if not rows:
            not_found.append(raw)
        elif not unpaid:
            already.append({"invoice_number": rows[0]["invoice_number"], "supplier": rows[0]["supplier"]})
        elif len(unpaid) > 1:
            ambiguous.append({"invoice_number": raw, "candidates": [
                {"id": r["id"], "supplier": r["supplier"], "amount_due": r["amount_due"]} for r in unpaid]})
        else:
            targets.append(unpaid[0]["id"])
    for iid in dict.fromkeys(targets):
        inv = get_invoice(iid)
        if not inv:
            not_found.append(f"id {iid}")
            continue
        if inv["status"] == "paid":
            already.append({"invoice_number": inv["invoice_number"], "supplier": inv["supplier"]})
            continue
        update_invoice(iid, {"status": "paid"}, source=source, author=author, comment=comment)
        db.execute("UPDATE invoices SET paid_at=? WHERE id=?", (when, iid))
        marked.append({"id": iid, "supplier": inv["supplier"], "invoice_number": inv["invoice_number"],
                       "amount_due": inv["amount_due"], "currency": inv["currency"]})
    total: dict[str, float] = {}
    for m in marked:
        total[m["currency"]] = round(total.get(m["currency"], 0) + (m["amount_due"] or 0), 2)
    return {"marked_paid": marked, "total_marked": total, "already_paid": already, "not_found": not_found,
            "ambiguous": ambiguous, "paid_date": when}
