"""Weekly payables report: deterministic numbers + optional Claude commentary, rendered to HTML (and PDF)."""
from __future__ import annotations

import html
import json
import logging
import secrets
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import BaseModel, Field

from . import db, llm, playbook
from .config import get_settings
from .invoices import parse_date, today_local

log = logging.getLogger(__name__)
TEMPLATES = Path(__file__).parent / "templates"
env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html"]))


def money(value: float | None, currency: str = "GBP") -> str:
    if value is None:
        return "-"
    symbol = {"GBP": "£", "EUR": "€", "USD": "$"}.get(currency, currency + " ")
    sign = "-" if value < 0 else ""
    return f"{sign}{symbol}{abs(value):,.2f}"


env.filters["money"] = money


def fmt_date(value: Any) -> str:
    d = parse_date(value)
    return d.strftime("%a %d %b %Y") if d else "-"


env.filters["date"] = fmt_date


# ---------------------------------------------------------------------------
# Numbers
# ---------------------------------------------------------------------------
def compute_summary(as_of: date | None = None) -> dict:
    s = get_settings()
    as_of = as_of or today_local()
    version, pb = playbook.get_active()
    all_unpaid = db.rows("SELECT * FROM invoices WHERE status IN ('unpaid','disputed') ORDER BY due_date, amount_due DESC")
    excluded = [i for i in all_unpaid if playbook.is_excluded(pb, i["supplier"], i["supplier_email"])]
    open_items = [i for i in all_unpaid if i not in excluded]
    payables = [i for i in open_items if i["doc_type"] == "invoice"]
    credits = [i for i in open_items if i["doc_type"] == "credit_note"]

    def bucket_of(due: date) -> str:
        days = (due - as_of).days
        if days < 0:
            return "overdue"
        if days <= 7:
            return "d0_7"
        if days <= 14:
            return "d8_14"
        if days <= 30:
            return "d15_30"
        return "d31_plus"

    totals: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    counts: dict[str, int] = defaultdict(int)
    weekly: dict[str, float] = defaultdict(float)
    by_supplier: dict[tuple[str, str], dict] = {}
    detail = []
    for i in payables:
        due = parse_date(i["due_date"]) or as_of
        b = bucket_of(due)
        cur = i["currency"]
        amt = i["amount_due"] or 0.0
        totals[cur][b] += amt
        totals[cur]["outstanding"] += amt
        counts[b] += 1
        days = (due - as_of).days
        if cur == s.base_currency:
            weekly["overdue" if days < 0 else (f"w{days // 7}" if days < 56 else "later")] += amt
        key = (i["supplier"], cur)
        sup = by_supplier.setdefault(key, {"supplier": i["supplier"], "currency": cur, "amount": 0.0, "count": 0,
                                           "next_due": due})
        sup["amount"] += amt
        sup["count"] += 1
        sup["next_due"] = min(sup["next_due"], due)
        detail.append({**i, "bucket": b, "days_to_due": days, "review_reasons": db.jloads(i["review_reasons"], [])})

    for cur, t in totals.items():
        t["overdue"] += 0
        t["within_7"] = t["d0_7"]
        t["within_14"] = t["d0_7"] + t["d8_14"]
        t["within_30"] = t["within_14"] + t["d15_30"]
        t["cash_7_incl_overdue"] = t["overdue"] + t["within_7"]

    week_start = as_of - timedelta(days=as_of.weekday())
    chart = [{"label": "Overdue", "value": round(weekly.get("overdue", 0.0), 2), "status": "overdue"}]
    for w in range(8):
        start = as_of + timedelta(days=7 * w)
        chart.append({"label": start.strftime("%d %b"), "value": round(weekly.get(f"w{w}", 0.0), 2),
                      "status": "upcoming", "range": f"{start:%d %b} - {start + timedelta(days=6):%d %b}"})
    chart.append({"label": "Later", "value": round(weekly.get("later", 0.0), 2), "status": "upcoming"})

    since = (as_of - timedelta(days=7)).isoformat()
    new_this_week = db.rows("SELECT * FROM invoices WHERE created_at >= ? AND doc_type='invoice' ORDER BY created_at DESC",
                            (since,))
    paid_this_week = db.rows("SELECT * FROM invoices WHERE status='paid' AND paid_at >= ? ORDER BY paid_at DESC", (since,))
    errors = db.rows("SELECT id, subject, from_addr, error FROM emails WHERE status='error' ORDER BY received_at DESC")

    base = {k: round(v, 2) for k, v in totals.get(s.base_currency, {}).items()}
    for k in ("overdue", "within_7", "within_14", "within_30", "cash_7_incl_overdue", "outstanding", "d31_plus"):
        base.setdefault(k, 0.0)
    return {
        "company": s.company_name,
        "as_of": as_of.isoformat(),
        "week_commencing": week_start.isoformat(),
        "base_currency": s.base_currency,
        "playbook_version": version,
        "headline": base,
        "other_currencies": {c: {k: round(v, 2) for k, v in t.items()} for c, t in totals.items() if c != s.base_currency},
        "counts": dict(counts),
        "open_count": len(payables),
        "chart": chart,
        "suppliers": sorted(({**v, "amount": round(v["amount"], 2), "next_due": v["next_due"].isoformat()}
                             for v in by_supplier.values()), key=lambda x: -x["amount"])[:10],
        "detail": detail,
        "credits": credits,
        "credits_total": round(sum(c["amount_due"] or 0 for c in credits if c["currency"] == s.base_currency), 2),
        "needs_review": [d for d in detail if d["needs_review"]],
        "new_this_week": new_this_week,
        "paid_this_week": paid_this_week,
        "excluded": excluded,
        "extraction_errors": errors,
        "report_preferences": pb.report_preferences,
    }


# ---------------------------------------------------------------------------
# Commentary (Claude) - numbers are passed in; the model must not compute new ones
# ---------------------------------------------------------------------------
class Commentary(BaseModel):
    headline: str = Field(description="One sentence for the board")
    bullets: list[str] = Field(description="3-6 short bullet points")


def write_commentary(summary: dict) -> Commentary | None:
    s = get_settings()
    if not s.commentary_enabled:
        return None
    compact = {k: summary[k] for k in ("as_of", "base_currency", "headline", "other_currencies", "counts", "open_count",
                                       "suppliers", "credits_total")}
    compact["overdue_items"] = [{k: d[k] for k in ("supplier", "invoice_number", "amount_due", "currency", "due_date")}
                                for d in summary["detail"] if d["bucket"] == "overdue"][:20]
    compact["needs_review_count"] = len(summary["needs_review"])
    compact["new_this_week_count"] = len(summary["new_this_week"])
    compact["paid_this_week_count"] = len(summary["paid_this_week"])
    system = (f"You write the payables commentary in {s.company_name}'s weekly board report. Use ONLY the figures "
              "provided; do not calculate new totals or estimate anything not given. Money in the given currency "
              "with two decimals.\n\nBoard preferences (learned from feedback):\n"
              + "\n".join(f"- {p}" for p in summary["report_preferences"]))
    try:
        return llm.parse(schema=Commentary, system=system, content=json.dumps(compact, default=str),
                         model=s.extraction_model, effort="low", max_tokens=4000)
    except Exception:
        log.exception("Commentary generation failed; report will be produced without it")
        return None


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
def render_html(summary: dict, commentary: Commentary | None, share: bool = False) -> str:
    max_val = max([c["value"] for c in summary["chart"]] + [1.0])
    return env.get_template("report.html").render(s=summary, c=commentary, max_val=max_val, share=share,
                                                  settings=get_settings())


async def render_pdf(html_path: Path) -> Path | None:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        log.info("Playwright not installed; skipping PDF")
        return None
    pdf_path = html_path.with_suffix(".pdf")
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.goto(html_path.resolve().as_uri(), wait_until="networkidle")
            await page.pdf(path=str(pdf_path), format="A4", print_background=True,
                           margin={"top": "12mm", "bottom": "14mm", "left": "10mm", "right": "10mm"})
            await browser.close()
        return pdf_path
    except Exception:
        log.exception("PDF rendering failed")
        return None


async def generate_report(as_of: date | None = None) -> dict:
    """Compute, write commentary, render, persist. Returns the report row."""
    import asyncio

    s = get_settings()
    summary = await asyncio.to_thread(compute_summary, as_of)
    commentary = await asyncio.to_thread(write_commentary, summary)
    token = secrets.token_urlsafe(24)
    stamp = f"{summary['as_of']}_{token[:6]}"
    html_path = s.reports_dir / f"payables_{stamp}.html"
    html_path.write_text(render_html(summary, commentary), encoding="utf-8")
    pdf_path = await render_pdf(html_path)
    stored = {k: v for k, v in summary.items() if k not in ("detail", "excluded")}
    stored["commentary"] = commentary.model_dump() if commentary else None
    report_id = db.execute(
        "INSERT INTO reports (created_at, as_of, html_path, pdf_path, summary_json, share_token, playbook_version)"
        " VALUES (?,?,?,?,?,?,?)",
        (db.now_iso(), summary["as_of"], str(html_path), str(pdf_path) if pdf_path else None,
         json.dumps(stored, default=str), token, summary["playbook_version"]),
    )
    return get_report(report_id)  # type: ignore[return-value]


def get_report(report_id: int) -> dict | None:
    r = db.one("SELECT * FROM reports WHERE id=?", (report_id,))
    if r:
        r["summary"] = db.jloads(r.pop("summary_json"), {})
    return r


def latest_report() -> dict | None:
    r = db.one("SELECT id FROM reports ORDER BY id DESC LIMIT 1")
    return get_report(r["id"]) if r else None


def telegram_summary(report: dict) -> str:
    s = get_settings()
    sm = report["summary"]
    h = sm["headline"]
    cur = sm["base_currency"]
    lines = [
        f"<b>{html.escape(s.company_name)} – payables report</b> (as of {fmt_date(sm['as_of'])})",
        "",
        f"Overdue: <b>{money(h['overdue'], cur)}</b>",
        f"Due next 7 days: <b>{money(h['within_7'], cur)}</b>",
        f"Due next 14 days: <b>{money(h['within_14'], cur)}</b>",
        f"Due next 30 days: <b>{money(h['within_30'], cur)}</b>",
        f"Total outstanding: {money(h['outstanding'], cur)} across {sm['open_count']} invoices",
    ]
    for c, t in sm.get("other_currencies", {}).items():
        lines.append(f"Also outstanding in {c}: {money(t.get('outstanding', 0), c)}")
    review = len(sm.get("needs_review", []))
    if review:
        lines.append(f"⚠️ {review} invoice(s) need a human check before payment")
    com = sm.get("commentary")
    if com:
        lines += ["", f"<i>{html.escape(com['headline'])}</i>"]
    if s.public_share_links:
        lines += ["", f"Board link: {s.public_base_url.rstrip('/')}/r/{report['share_token']}"]
    lines += ["", "Reply to this message with any feedback on the report."]
    return "\n".join(lines)
