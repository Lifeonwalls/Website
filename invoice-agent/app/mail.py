"""Read-only IMAP ingestion of the accounts mailbox.

The mailbox is opened with EXAMINE (read-only) and bodies are fetched with BODY.PEEK,
so nothing is marked as read and nothing is moved or deleted.
"""
from __future__ import annotations

import email
import hashlib
import imaplib
import logging
import re
from datetime import datetime, timedelta, timezone
from email.header import decode_header, make_header
from email.message import Message
from email.utils import parseaddr, parsedate_to_datetime
from html import unescape
from pathlib import Path

from . import db
from .config import get_settings

log = logging.getLogger(__name__)

SUPPORTED_MIME = {
    "application/pdf": ".pdf",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "text/xml": ".xml",
    "application/xml": ".xml",
    "text/csv": ".csv",
    "text/plain": ".txt",
}
EXT_TO_MIME = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
               ".gif": "image/gif", ".webp": "image/webp", ".xml": "application/xml", ".csv": "text/csv"}
MIN_IMAGE_BYTES = 15_000  # skip logos / signature images


def _decode(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def html_to_text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    html = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>|</h\d>", "\n", html)
    html = re.sub(r"(?i)</td>|</th>", " | ", html)
    text = unescape(re.sub(r"<[^>]+>", " ", html))
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def parse_message(raw: bytes) -> dict:
    msg: Message = email.message_from_bytes(raw)
    plain, html, attachments = [], [], []
    for part in msg.walk():
        if part.is_multipart():
            continue
        ctype = part.get_content_type()
        filename = _decode(part.get_filename())
        disposition = (part.get("Content-Disposition") or "").lower()
        payload = part.get_payload(decode=True) or b""
        is_attachment = bool(filename) or "attachment" in disposition
        if not is_attachment and ctype == "text/plain":
            plain.append(payload.decode(part.get_content_charset() or "utf-8", errors="replace"))
        elif not is_attachment and ctype == "text/html":
            html.append(payload.decode(part.get_content_charset() or "utf-8", errors="replace"))
        elif is_attachment or ctype.startswith("image/"):
            ext = Path(filename).suffix.lower() if filename else ""
            mime = ctype if ctype in SUPPORTED_MIME else EXT_TO_MIME.get(ext, ctype)
            if mime not in SUPPORTED_MIME:
                continue
            if mime.startswith("image/") and len(payload) < MIN_IMAGE_BYTES:
                continue
            attachments.append({"filename": filename or f"attachment{SUPPORTED_MIME[mime]}", "mime": mime, "data": payload})

    body = "\n".join(plain).strip() or html_to_text("\n".join(html))
    try:
        received = parsedate_to_datetime(msg.get("Date")).astimezone(timezone.utc).isoformat(timespec="seconds")
    except Exception:
        received = db.now_iso()
    message_id = (msg.get("Message-ID") or "").strip() or "sha256:" + hashlib.sha256(raw).hexdigest()
    return {
        "message_id": message_id,
        "from_addr": _decode(msg.get("From")),
        "subject": _decode(msg.get("Subject")),
        "received_at": received,
        "body_text": body,
        "attachments": attachments,
    }


def passes_prefilter(parsed: dict) -> bool:
    if any(a["mime"] in ("application/pdf", "application/xml", "text/xml") for a in parsed["attachments"]):
        return True
    hay = f"{parsed['subject']}\n{parsed['body_text'][:5000]}".lower()
    return any(k in hay for k in get_settings().keywords)


def store_email(parsed: dict, folder: str, uid: int | None) -> int | None:
    """Insert email + attachments. Returns the new email id, or None if already stored."""
    s = get_settings()
    if db.one("SELECT id FROM emails WHERE message_id=?", (parsed["message_id"],)):
        return None
    status = "new" if passes_prefilter(parsed) else "skipped"
    with db.tx() as conn:
        cur = conn.execute(
            "INSERT INTO emails (message_id, folder, uid, from_addr, subject, received_at, body_text, status)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (parsed["message_id"], folder, uid, parsed["from_addr"], parsed["subject"], parsed["received_at"],
             parsed["body_text"], status),
        )
        email_id = cur.lastrowid
        for att in parsed["attachments"]:
            if len(att["data"]) > s.max_attachment_mb * 1024 * 1024:
                log.warning("Skipping oversized attachment %s on email %s", att["filename"], email_id)
                continue
            sha = hashlib.sha256(att["data"]).hexdigest()
            path = s.attachments_dir / f"{sha}{SUPPORTED_MIME[att['mime']]}"
            if not path.exists():
                path.write_bytes(att["data"])
            conn.execute(
                "INSERT INTO documents (email_id, filename, mime, sha256, path) VALUES (?,?,?,?,?)",
                (email_id, att["filename"], att["mime"], sha, str(path)),
            )
    return email_id


def _uidvalidity(conn: imaplib.IMAP4_SSL, folder: str) -> int:
    typ, data = conn.status(f'"{folder}"', "(UIDVALIDITY)")
    m = re.search(rb"UIDVALIDITY (\d+)", data[0] or b"")
    return int(m.group(1)) if m else 0


def fetch_new() -> list[int]:
    """Fetch new messages from every configured folder. Returns ids of newly stored emails."""
    s = get_settings()
    if not s.imap_password:
        raise RuntimeError("IMAP_PASSWORD is not set")
    new_ids: list[int] = []
    conn = imaplib.IMAP4_SSL(s.imap_host, s.imap_port)
    try:
        conn.login(s.imap_user, s.imap_password)
        for folder in s.folders:
            validity = _uidvalidity(conn, folder)
            typ, _ = conn.select(f'"{folder}"', readonly=True)
            if typ != "OK":
                log.error("Cannot open folder %s", folder)
                continue
            state = db.one("SELECT * FROM mail_state WHERE folder=?", (folder,))
            if state and state["uidvalidity"] == validity:
                typ, data = conn.uid("SEARCH", None, f"UID {state['last_uid'] + 1}:*")
                last_uid = state["last_uid"]
            else:
                since = (datetime.now() - timedelta(days=s.initial_lookback_days)).strftime("%d-%b-%Y")
                typ, data = conn.uid("SEARCH", None, f"SINCE {since}")
                last_uid = 0
            uids = sorted(int(u) for u in (data[0] or b"").split() if int(u) > last_uid)
            log.info("Folder %s: %d new message(s)", folder, len(uids))
            for uid in uids:
                typ, msg_data = conn.uid("FETCH", str(uid), "(BODY.PEEK[])")
                raw = next((p[1] for p in msg_data if isinstance(p, tuple)), None)
                if raw:
                    eid = store_email(parse_message(raw), folder, uid)
                    if eid:
                        new_ids.append(eid)
                last_uid = max(last_uid, uid)
            db.execute(
                "INSERT INTO mail_state (folder, uidvalidity, last_uid) VALUES (?,?,?)"
                " ON CONFLICT(folder) DO UPDATE SET uidvalidity=excluded.uidvalidity, last_uid=excluded.last_uid",
                (folder, validity, last_uid),
            )
    finally:
        try:
            conn.logout()
        except Exception:
            pass
    return new_ids


def import_eml(path: Path) -> int | None:
    """Manually import a .eml file (useful for testing and back-filling)."""
    return store_email(parse_message(path.read_bytes()), "import", None)
