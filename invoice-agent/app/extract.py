"""Turn one stored email (+ attachments) into structured invoice data with Claude."""
from __future__ import annotations

import base64
from pathlib import Path

from . import db, llm, playbook as playbook_mod
from .config import get_settings
from .models import EmailExtraction, Playbook

MAX_BODY_CHARS = 60_000
MAX_TEXT_ATTACHMENT_CHARS = 100_000

BASE_SYSTEM = """You are the accounts-payable clerk for {company}, a UK company. You read emails that arrive \
in the {mailbox} mailbox and extract every invoice the company has to PAY.

Work carefully:
- Read every attached document. PDFs and images are the primary source of truth; the email body is secondary.
- Copy identifiers (invoice numbers, references, bank details) exactly as printed.
- Amounts are numbers without currency symbols or thousands separators. Use the document's currency.
- Use YYYY-MM-DD for dates. The email was received on {received}; use that to resolve partial dates.
- If something is unclear, still give your best reading, lower `confidence`, and explain in `uncertainties`.
- Never invent values that are not supported by the email or its attachments.

{playbook}
"""


def build_content(email_row: dict, documents: list[dict]) -> list[dict]:
    content: list[dict] = []
    notes: list[str] = []
    for d in documents:
        path = Path(d["path"])
        if not path.exists():
            notes.append(f"Attachment {d['filename']} is missing from storage.")
            continue
        data = path.read_bytes()
        if d["mime"] == "application/pdf":
            content.append({
                "type": "document",
                "source": {"type": "base64", "media_type": "application/pdf",
                           "data": base64.standard_b64encode(data).decode()},
                "title": d["filename"],
            })
        elif d["mime"].startswith("image/"):
            content.append({"type": "text", "text": f"Attachment image: {d['filename']}"})
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": d["mime"],
                           "data": base64.standard_b64encode(data).decode()},
            })
        else:
            text = data.decode("utf-8", errors="replace")
            if len(text) > MAX_TEXT_ATTACHMENT_CHARS:
                notes.append(f"Attachment {d['filename']} was cut to the first {MAX_TEXT_ATTACHMENT_CHARS} characters.")
                text = text[:MAX_TEXT_ATTACHMENT_CHARS]
            content.append({"type": "text", "text": f"Attachment {d['filename']} ({d['mime']}):\n{text}"})

    body = email_row.get("body_text") or ""
    if len(body) > MAX_BODY_CHARS:
        notes.append(f"Email body was cut to the first {MAX_BODY_CHARS} characters (original {len(body)}).")
        body = body[:MAX_BODY_CHARS]
    header = (
        f"From: {email_row.get('from_addr')}\nSubject: {email_row.get('subject')}\n"
        f"Received: {email_row.get('received_at')}\nAttachments: "
        + (", ".join(d["filename"] for d in documents) or "none")
    )
    if notes:
        header += "\nNotes: " + " ".join(notes) + " Mention this in `uncertainties` if it matters."
    content.append({"type": "text", "text": f"{header}\n\n--- Email body ---\n{body}\n--- End ---\n\n"
                    "Classify this email and extract the payable invoices."})
    return content


def extract_email(email_id: int, pb: Playbook | None = None) -> EmailExtraction:
    """Pure function: no DB writes. Used by both the pipeline and the evaluation harness."""
    s = get_settings()
    email_row = db.one("SELECT * FROM emails WHERE id=?", (email_id,))
    if not email_row:
        raise ValueError(f"Email {email_id} not found")
    documents = db.rows("SELECT * FROM documents WHERE email_id=? ORDER BY id", (email_id,))
    if pb is None:
        _, pb = playbook_mod.get_active()
    system = BASE_SYSTEM.format(
        company=s.company_name, mailbox=s.imap_user, received=email_row["received_at"],
        playbook=playbook_mod.render_for_extraction(pb),
    )
    return llm.parse(schema=EmailExtraction, system=system, content=build_content(email_row, documents),
                     model=s.extraction_model, effort=s.extraction_effort)
