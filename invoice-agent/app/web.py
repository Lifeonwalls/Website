"""Web UI + JSON API (FastAPI). Runs the scheduler and Telegram bot in the same process."""
from __future__ import annotations

import asyncio
import logging
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware

from . import agent, db, improve, invoices, notify, pipeline, playbook, report, scheduler, telegram_bot
from .config import get_settings
from .invoices import today_local
from .models import Playbook

log = logging.getLogger(__name__)
BASE = Path(__file__).parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    if len(s.session_secret) < 32 or not s.web_password:
        raise RuntimeError("SESSION_SECRET (32+ chars) and WEB_PASSWORD must be set - run ./setup.sh "
                           "or `python -m app check` to see what is missing")
    db.init_db()
    playbook.get_active()
    scheduler.start()
    await telegram_bot.start()
    yield
    await telegram_bot.stop()
    scheduler.stop()


app = FastAPI(title="Payables Agent", lifespan=lifespan)
settings = get_settings()
app.add_middleware(SessionMiddleware, secret_key=settings.session_secret, same_site="strict",
                   https_only=settings.public_base_url.startswith("https"), max_age=60 * 60 * 24 * 14)
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")
templates.env.filters["money"] = report.money
templates.env.filters["date"] = report.fmt_date
_failed_logins: dict[str, list[float]] = {}


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
class NotAuthenticated(Exception):
    pass


@app.exception_handler(NotAuthenticated)
async def _redirect_login(request: Request, exc: NotAuthenticated):
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": "Not logged in"}, status_code=401)
    return RedirectResponse(f"/login?next={request.url.path}", status_code=303)


def user(request: Request) -> str:
    u = request.session.get("user")
    if not u:
        raise NotAuthenticated()
    return u


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str = "/"):
    return templates.TemplateResponse(request, "login.html", {"next": next, "error": None, "settings": settings})


@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...), next: str = Form("/")):
    ip = request.client.host if request.client else "?"
    recent = [t for t in _failed_logins.get(ip, []) if time.time() - t < 900]
    if len(recent) >= 5:
        return templates.TemplateResponse(request, "login.html", {"next": next, "error": "Too many attempts. Try again in 15 minutes.", "settings": settings},
                                          status_code=429)
    ok = (settings.web_password and secrets.compare_digest(username, settings.web_username)
          and secrets.compare_digest(password, settings.web_password))
    if not ok:
        _failed_logins[ip] = recent + [time.time()]
        await asyncio.sleep(1)
        return templates.TemplateResponse(request, "login.html", {"next": next, "error": "Wrong username or password.", "settings": settings},
                                          status_code=401)
    request.session["user"] = username
    return RedirectResponse(next if next.startswith("/") and not next.startswith("//") else "/", status_code=303)


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@app.get("/health")
async def health():
    return {"ok": True}


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------
def page(request: Request, name: str, u: str, **ctx: Any) -> HTMLResponse:
    pending = len(improve.pending_feedback())
    candidates = len([v for v in playbook.list_versions() if v["status"] == "candidate"])
    return templates.TemplateResponse(request, name, {"user": u, "settings": settings, "pending_feedback": pending,
                                                      "candidates": candidates, "now_iso": today_local().isoformat(), **ctx})


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, u: str = Depends(user)):
    sm = await asyncio.to_thread(report.compute_summary)
    runs = db.rows("SELECT * FROM runs ORDER BY id DESC LIMIT 6")
    return page(request, "dashboard.html", u, s=sm, latest=report.latest_report(), runs=runs,
                max_val=max([c["value"] for c in sm["chart"]] + [1.0]))


@app.get("/invoices", response_class=HTMLResponse)
async def invoices_page(request: Request, status: str = "unpaid", q: str = "", review: str = "",
                        u: str = Depends(user)):
    rows = invoices.find_invoices(q or None, None if status == "any" else status, None, False,
                                  True if review == "1" else None, 500)
    return page(request, "invoices.html", u, rows=rows, status=status, q=q, review=review,
                editable=sorted(invoices.EDITABLE_FIELDS))


@app.get("/emails", response_class=HTMLResponse)
async def emails_page(request: Request, status: str = "", u: str = Depends(user)):
    sql = "SELECT e.*, (SELECT COUNT(*) FROM invoices i WHERE i.email_id=e.id) AS n_invoices FROM emails e"
    params: tuple = ()
    if status:
        sql += " WHERE e.status=?"
        params = (status,)
    rows = db.rows(sql + " ORDER BY received_at DESC LIMIT 300", params)
    return page(request, "emails.html", u, rows=rows, status=status)


@app.get("/reports", response_class=HTMLResponse)
async def reports_page(request: Request, u: str = Depends(user)):
    rows = db.rows("SELECT id, created_at, as_of, pdf_path, share_token, playbook_version FROM reports ORDER BY id DESC LIMIT 100")
    return page(request, "reports.html", u, rows=rows)


@app.get("/reports/{report_id}", response_class=HTMLResponse)
async def view_report(report_id: int, u: str = Depends(user)):
    r = report.get_report(report_id)
    if not r:
        raise HTTPException(404)
    return HTMLResponse(Path(r["html_path"]).read_text(encoding="utf-8"))


@app.get("/reports/{report_id}/pdf")
async def report_pdf(report_id: int, u: str = Depends(user)):
    r = report.get_report(report_id)
    if not r or not r.get("pdf_path") or not Path(r["pdf_path"]).exists():
        raise HTTPException(404, "No PDF for this report (install Playwright to enable PDFs)")
    return FileResponse(r["pdf_path"], media_type="application/pdf", filename=Path(r["pdf_path"]).name)


@app.get("/r/{token}", response_class=HTMLResponse)
async def shared_report(token: str):
    """Read-only board link. Unguessable token; can be disabled with PUBLIC_SHARE_LINKS=false."""
    if not settings.public_share_links:
        raise HTTPException(404)
    r = db.one("SELECT html_path FROM reports WHERE share_token=?", (token,))
    if not r:
        raise HTTPException(404)
    return HTMLResponse(Path(r["html_path"]).read_text(encoding="utf-8"),
                        headers={"X-Robots-Tag": "noindex, nofollow", "Referrer-Policy": "no-referrer"})


@app.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request, u: str = Depends(user)):
    return page(request, "chat.html", u)


@app.get("/improve", response_class=HTMLResponse)
async def improve_page(request: Request, u: str = Depends(user)):
    versions = playbook.list_versions()
    active = next(v for v in versions if v["status"] == "active")
    active_pb = Playbook.model_validate(active["rules"])
    for v in versions:
        v["diff"] = improve.describe_diff(active_pb, Playbook.model_validate(v["rules"])) if v["status"] == "candidate" else None
    feedback = db.rows("SELECT * FROM feedback ORDER BY id DESC LIMIT 100")
    cases = db.one("SELECT COUNT(*) AS n FROM eval_cases")["n"]
    return page(request, "improve.html", u, versions=versions, active=active, feedback=feedback, n_cases=cases)


# ---------------------------------------------------------------------------
# JSON API
# ---------------------------------------------------------------------------
class InvoiceUpdate(BaseModel):
    changes: dict[str, Any]
    comment: str | None = None


class PaidIn(BaseModel):
    paid_date: str | None = None


class ManualInvoice(BaseModel):
    fields: dict[str, Any]
    email_id: int | None = None
    comment: str | None = None


class ChatIn(BaseModel):
    message: str


class FeedbackIn(BaseModel):
    kind: str = "general"
    comment: str
    invoice_id: int | None = None


class ReportIn(BaseModel):
    notify: bool = False


def _bad(e: Exception) -> HTTPException:
    return HTTPException(400, str(e))


@app.get("/api/invoices/{invoice_id}")
async def api_invoice(invoice_id: int, u: str = Depends(user)):
    inv = invoices.get_invoice(invoice_id)
    if not inv:
        raise HTTPException(404)
    inv["documents"] = db.rows("SELECT id, filename, mime FROM documents WHERE email_id=?", (inv["email_id"],)) if inv["email_id"] else []
    return inv


@app.post("/api/invoices/{invoice_id}")
async def api_update_invoice(invoice_id: int, body: InvoiceUpdate, u: str = Depends(user)):
    try:
        return await asyncio.to_thread(lambda: invoices.update_invoice(invoice_id, body.changes, source="web",
                                                                       author=f"web:{u}", comment=body.comment))
    except ValueError as e:
        raise _bad(e)


@app.post("/api/invoices/{invoice_id}/confirm")
async def api_confirm(invoice_id: int, u: str = Depends(user)):
    try:
        return await asyncio.to_thread(lambda: invoices.confirm_invoice(invoice_id, source="web", author=f"web:{u}"))
    except ValueError as e:
        raise _bad(e)


@app.post("/api/invoices/{invoice_id}/paid")
async def api_mark_paid(invoice_id: int, body: PaidIn, u: str = Depends(user)):
    """Manual payment from the UI. Records who did it; paid_date defaults to today."""
    try:
        res = await asyncio.to_thread(lambda: invoices.mark_paid(
            numbers=[], suppliers=[], ids=[invoice_id], paid_date=body.paid_date, source="web",
            author=f"web:{u}", comment="Marked paid manually in the dashboard"))
    except ValueError as e:
        raise _bad(e)
    if res["not_found"]:
        raise HTTPException(404, "Invoice not found")
    return res


@app.post("/api/invoices/{invoice_id}/unpaid")
async def api_mark_unpaid(invoice_id: int, u: str = Depends(user)):
    try:
        return await asyncio.to_thread(lambda: invoices.update_invoice(
            invoice_id, {"status": "unpaid"}, source="web", author=f"web:{u}", comment="Payment undone in the dashboard"))
    except ValueError as e:
        raise _bad(e)


@app.post("/api/invoices")
async def api_add_invoice(body: ManualInvoice, u: str = Depends(user)):
    try:
        return await asyncio.to_thread(lambda: invoices.create_manual_invoice(
            body.fields, email_id=body.email_id, source="web", author=f"web:{u}", comment=body.comment))
    except ValueError as e:
        raise _bad(e)


@app.get("/api/documents/{doc_id}")
async def api_document(doc_id: int, u: str = Depends(user)):
    d = db.one("SELECT * FROM documents WHERE id=?", (doc_id,))
    if not d or not Path(d["path"]).exists():
        raise HTTPException(404)
    return FileResponse(d["path"], media_type=d["mime"], filename=d["filename"],
                        content_disposition_type="inline")


@app.post("/api/emails/{email_id}/reprocess")
async def api_reprocess(email_id: int, u: str = Depends(user)):
    return await asyncio.to_thread(pipeline.process_email, email_id)


@app.post("/api/ingest")
async def api_ingest(u: str = Depends(user)):
    try:
        return await asyncio.to_thread(pipeline.run_ingest)
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/reports")
async def api_generate_report(body: ReportIn, u: str = Depends(user)):
    rep = await report.generate_report()
    if body.notify:
        await notify.send_report(rep)
    return {"id": rep["id"], "share_token": rep["share_token"]}


@app.post("/api/chat")
async def api_chat(body: ChatIn, u: str = Depends(user)):
    if not body.message.strip():
        raise HTTPException(400, "Empty message")
    answer = await agent.ask(f"web:{u}", body.message, source="web", author=f"web:{u}")
    return {"answer": answer}


@app.post("/api/chat/reset")
async def api_chat_reset(u: str = Depends(user)):
    agent.reset(f"web:{u}")
    return {"ok": True}


@app.post("/api/feedback")
async def api_feedback(body: FeedbackIn, u: str = Depends(user)):
    fid = improve.record_feedback(source="web", author=f"web:{u}", kind=body.kind, comment=body.comment,
                                  target_type="invoice" if body.invoice_id else None, target_id=body.invoice_id)
    return {"id": fid}


@app.post("/api/improve/run")
async def api_improve(u: str = Depends(user)):
    try:
        return await asyncio.to_thread(improve.run_improvement_cycle, True)
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/playbooks/{version}/approve")
async def api_approve(version: int, u: str = Depends(user)):
    try:
        n = await asyncio.to_thread(improve.apply_version, version)
    except ValueError as e:
        raise _bad(e)
    await notify.send_text(f"🧠 Playbook v{version} approved by {u} and activated ({n} email(s) re-checked).")
    return {"ok": True, "reprocessed": n}


@app.post("/api/playbooks/{version}/reject")
async def api_reject(version: int, u: str = Depends(user)):
    playbook.reject(version)
    return {"ok": True}
