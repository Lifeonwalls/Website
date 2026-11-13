"""Ingest pipeline: mailbox -> Claude extraction -> invoices table. Idempotent and safe to re-run."""
from __future__ import annotations

import logging

from . import db, extract, invoices, mail, playbook

log = logging.getLogger(__name__)


def process_email(email_id: int) -> dict:
    version, pb = playbook.get_active()
    row = db.one("SELECT id, received_at FROM emails WHERE id=?", (email_id,))
    if not row:
        raise ValueError(f"Email {email_id} not found")
    try:
        result = extract.extract_email(email_id, pb)
    except Exception as e:  # keep going with other emails; error is visible in the UI
        log.exception("Extraction failed for email %s", email_id)
        db.execute("UPDATE emails SET status='error', error=?, processed_at=? WHERE id=?",
                   (str(e)[:2000], db.now_iso(), email_id))
        return {"email_id": email_id, "error": str(e)}

    invoice_ids: list[int] = []
    notes: list[str] = []
    if result.classification in invoices.PAYABLE_CLASSES:
        for idx, inv in enumerate(result.invoices):
            invoice_ids.append(invoices.upsert_extracted(email_id, row["received_at"], inv, idx))
    if result.paid_invoice_numbers:
        notes += invoices.mark_paid_by_numbers(result.paid_invoice_numbers, email_id)

    status = "processed" if invoice_ids or notes else "not_invoice"
    db.execute("UPDATE emails SET status=?, classification=?, error=NULL, playbook_version=?, processed_at=? WHERE id=?",
               (status, result.classification, version, db.now_iso(), email_id))
    return {"email_id": email_id, "classification": result.classification, "invoice_ids": invoice_ids, "notes": notes}


def process_pending(limit: int = 200) -> list[dict]:
    pending = db.rows("SELECT id FROM emails WHERE status IN ('new','error') ORDER BY received_at LIMIT ?", (limit,))
    return [process_email(r["id"]) for r in pending]


def run_ingest() -> dict:
    """Fetch new mail and extract invoices. Returns a summary dict."""
    run_id = db.execute("INSERT INTO runs (kind, started_at) VALUES ('ingest', ?)", (db.now_iso(),))
    try:
        new_ids = mail.fetch_new()
        results = process_pending()
        summary = {
            "new_emails": len(new_ids),
            "processed": len(results),
            "invoices_found": sum(len(r.get("invoice_ids", [])) for r in results),
            "errors": [r for r in results if "error" in r],
            "payment_notes": [n for r in results for n in r.get("notes", [])],
        }
        db.execute("UPDATE runs SET finished_at=?, ok=1, summary=? WHERE id=?",
                   (db.now_iso(), str(summary), run_id))
        return summary
    except Exception as e:
        db.execute("UPDATE runs SET finished_at=?, ok=0, summary=? WHERE id=?", (db.now_iso(), str(e), run_id))
        raise
