"""Conversational agent (Claude Agent SDK) shared by the web chat and the Telegram bot.

The agent has NO built-in tools (no shell, no file access, no web): only the payables tools below,
served from an in-process MCP server. Every correction it makes goes through invoices.update_invoice,
which records feedback and regression tests for the self-improvement loop.
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from typing import Any, Awaitable, Callable

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    create_sdk_mcp_server,
    query,
    tool,
)

from . import db, improve, invoices, pipeline, playbook, report
from .config import get_settings

log = logging.getLogger(__name__)
SERVER = "payables"
_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

SYSTEM_PROMPT = """You are the payables assistant for {company}. You help the finance team and the board \
understand which supplier invoices must be paid and when, using invoices extracted automatically from the \
{mailbox} mailbox. Today is {today} ({tz}). Currency is {currency} unless stated.

How to work:
- Get every figure from the tools. Never estimate or add up amounts yourself when a tool can return them.
- "Due in the next N days" means due between today and today+N; overdue is shown separately.
- When someone tells you extracted data is wrong (amount, date, supplier, number...), fix it with update_invoice \
and put their explanation in `comment`. This automatically teaches the extraction agent.
- When someone says an email was NOT a payable invoice, set status "ignored" with a comment. When an invoice was \
missed, find the email with search_emails and use add_missed_invoice.
- When someone confirms an invoice is correct, call confirm_invoice.
- Opinions about the report or the process ("show categories", "leave out X") go to record_feedback with kind \
"report" or "general". Tell them it will be applied at the next improvement cycle (or run it if they ask).
- You cannot make payments. Marking an invoice paid only records that it was paid elsewhere. Before marking more \
than three invoices paid at once, list them and ask for confirmation.
- Be brief and concrete. Use short lists. Format money like £1,234.56 and dates like Mon 17 Nov.
{channel_hint}"""

CHANNEL_HINTS = {
    "telegram": "- You are replying in Telegram: plain text only, no Markdown tables, at most ~15 lines.",
    "web": "- You are replying in a web chat that renders Markdown; tables are fine.",
}


def _ok(data: Any) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(data, default=str, indent=1)}]}


def _err(msg: str) -> dict:
    return {"content": [{"type": "text", "text": msg}], "is_error": True}


def _slim(inv: dict) -> dict:
    keys = ("id", "supplier", "invoice_number", "invoice_date", "due_date", "due_date_source", "currency",
            "total_amount", "amount_due", "status", "description", "category", "needs_review", "review_reasons",
            "po_number", "payment_reference", "email_id")
    return {k: inv.get(k) for k in keys}


def _guard(fn: Callable[[dict], Awaitable[dict]]) -> Callable[[dict], Awaitable[dict]]:
    async def wrapper(args: dict) -> dict:
        try:
            return await fn(args)
        except ValueError as e:
            return _err(str(e))
        except Exception as e:  # surface as a tool error so the agent can explain it
            log.exception("Tool failed")
            return _err(f"Tool failed: {e}")
    return wrapper


def build_tools(source: str, author: str | None) -> list:
    T = asyncio.to_thread

    @tool("cash_summary", "Headline payables: overdue, due within 7/14/30 days, total outstanding, top suppliers, "
          "counts needing review. Call this first for any 'how much do we owe / need to pay' question.",
          {"type": "object", "properties": {}})
    @_guard
    async def cash_summary(args: dict) -> dict:
        sm = await T(report.compute_summary)
        return _ok({k: sm[k] for k in ("as_of", "base_currency", "headline", "other_currencies", "counts", "open_count",
                                       "suppliers", "credits_total")}
                   | {"needs_review": len(sm["needs_review"]), "extraction_errors": len(sm["extraction_errors"])})

    @tool("list_invoices", "List invoices with filters, sorted by due date.", {
        "type": "object",
        "properties": {
            "search": {"type": "string", "description": "Matches supplier, invoice number, description or PO"},
            "status": {"type": "string", "enum": ["unpaid", "paid", "disputed", "ignored", "any"], "default": "unpaid"},
            "due_within_days": {"type": "integer", "description": "Due on or before today + N days (includes overdue)"},
            "overdue_only": {"type": "boolean"},
            "needs_review": {"type": "boolean"},
            "limit": {"type": "integer", "default": 50},
        },
    })
    @_guard
    async def list_invoices(args: dict) -> dict:
        status = args.get("status", "unpaid")
        rows = await T(invoices.find_invoices, args.get("search"), None if status == "any" else status,
                       args.get("due_within_days"), bool(args.get("overdue_only")), args.get("needs_review"),
                       min(int(args.get("limit") or 50), 200))
        total: dict[str, float] = defaultdict(float)
        for r in rows:
            total[r["currency"]] += r["amount_due"] or 0
        return _ok({"count": len(rows), "total_amount_due": {k: round(v, 2) for k, v in total.items()},
                    "invoices": [_slim(r) for r in rows]})

    @tool("get_invoice", "Full details of one invoice, including the source email.",
          {"type": "object", "properties": {"invoice_id": {"type": "integer"}}, "required": ["invoice_id"]})
    @_guard
    async def get_invoice(args: dict) -> dict:
        inv = await T(invoices.get_invoice, int(args["invoice_id"]))
        return _ok(inv) if inv else _err("Invoice not found")

    @tool("update_invoice", "Correct extracted fields or change status/notes of an invoice. Corrections are recorded "
          "as feedback and become regression tests for the extractor.", {
        "type": "object",
        "properties": {
            "invoice_id": {"type": "integer"},
            "changes": {"type": "object", "description": "Field -> new value. Fields: " + ", ".join(sorted(invoices.EDITABLE_FIELDS))
                        + ", status (unpaid|paid|disputed|ignored), notes. Dates YYYY-MM-DD."},
            "comment": {"type": "string", "description": "Why - in the user's words"},
        },
        "required": ["invoice_id", "changes"],
    })
    @_guard
    async def update_invoice(args: dict) -> dict:
        inv = await T(lambda: invoices.update_invoice(int(args["invoice_id"]), args["changes"], source=source,
                                                      author=author, comment=args.get("comment")))
        return _ok({"updated": _slim(inv)})

    @tool("confirm_invoice", "Record that a human checked an invoice and the extracted data is correct.",
          {"type": "object", "properties": {"invoice_id": {"type": "integer"}}, "required": ["invoice_id"]})
    @_guard
    async def confirm_invoice(args: dict) -> dict:
        inv = await T(lambda: invoices.confirm_invoice(int(args["invoice_id"]), source=source, author=author))
        return _ok({"confirmed": _slim(inv)})

    @tool("mark_paid", "Record invoices as paid (payment was made outside this system).", {
        "type": "object",
        "properties": {"invoice_ids": {"type": "array", "items": {"type": "integer"}},
                       "comment": {"type": "string"}},
        "required": ["invoice_ids"],
    })
    @_guard
    async def mark_paid(args: dict) -> dict:
        done = []
        for iid in args["invoice_ids"]:
            inv = await T(lambda i=iid: invoices.update_invoice(int(i), {"status": "paid"}, source=source, author=author,
                                                                comment=args.get("comment")))
            done.append(_slim(inv))
        return _ok({"marked_paid": done})

    @tool("add_missed_invoice", "Add an invoice the extractor missed. Required fields: supplier, invoice_number, "
          "amount_due, due_date. Link email_id when known so the extractor learns from it.", {
        "type": "object",
        "properties": {"fields": {"type": "object"}, "email_id": {"type": "integer"}, "comment": {"type": "string"}},
        "required": ["fields"],
    })
    @_guard
    async def add_missed_invoice(args: dict) -> dict:
        inv = await T(lambda: invoices.create_manual_invoice(args["fields"], email_id=args.get("email_id"), source=source,
                                                             author=author, comment=args.get("comment")))
        return _ok({"created": _slim(inv)})

    @tool("search_emails", "Search stored emails from the accounts mailbox by subject or sender.", {
        "type": "object",
        "properties": {"query": {"type": "string"},
                       "status": {"type": "string", "enum": ["processed", "not_invoice", "skipped", "error", "new", "any"]},
                       "limit": {"type": "integer", "default": 20}},
        "required": ["query"],
    })
    @_guard
    async def search_emails(args: dict) -> dict:
        q = f"%{args['query']}%"
        sql = ("SELECT id, received_at, from_addr, subject, status, classification, error FROM emails"
               " WHERE (subject LIKE ? OR from_addr LIKE ?)")
        params: list[Any] = [q, q]
        if args.get("status") and args["status"] != "any":
            sql += " AND status=?"
            params.append(args["status"])
        sql += " ORDER BY received_at DESC LIMIT ?"
        params.append(min(int(args.get("limit") or 20), 100))
        return _ok(await T(db.rows, sql, tuple(params)))

    @tool("reprocess_email", "Run extraction again on one stored email with the current playbook.",
          {"type": "object", "properties": {"email_id": {"type": "integer"}}, "required": ["email_id"]})
    @_guard
    async def reprocess_email(args: dict) -> dict:
        return _ok(await T(pipeline.process_email, int(args["email_id"])))

    @tool("run_ingest", "Check the accounts mailbox now and extract any new invoices.",
          {"type": "object", "properties": {}})
    @_guard
    async def run_ingest(args: dict) -> dict:
        return _ok(await T(pipeline.run_ingest))

    @tool("generate_report", "Create the board payables report now. Optionally notify the Telegram report recipients.",
          {"type": "object", "properties": {"notify": {"type": "boolean", "default": False}}})
    @_guard
    async def generate_report(args: dict) -> dict:
        from . import notify
        rep = await report.generate_report()
        if args.get("notify"):
            await notify.send_report(rep)
        s = get_settings()
        return _ok({"report_id": rep["id"], "headline": rep["summary"]["headline"],
                    "view_url": f"{s.public_base_url.rstrip('/')}/reports/{rep['id']}",
                    "board_link": f"{s.public_base_url.rstrip('/')}/r/{rep['share_token']}" if s.public_share_links else None,
                    "notified": bool(args.get("notify"))})

    @tool("record_feedback", "Store feedback about the report, the process or extraction quality for the "
          "self-improvement loop.", {
        "type": "object",
        "properties": {"kind": {"type": "string", "enum": ["report", "general", "classification"]},
                       "comment": {"type": "string"}, "invoice_id": {"type": "integer"}},
        "required": ["kind", "comment"],
    })
    @_guard
    async def record_feedback(args: dict) -> dict:
        fid = await T(lambda: improve.record_feedback(source=source, author=author, kind=args["kind"],
                                                      comment=args["comment"],
                                                      target_type="invoice" if args.get("invoice_id") else None,
                                                      target_id=args.get("invoice_id")))
        return _ok({"feedback_id": fid, "pending_feedback": len(await T(improve.pending_feedback))})

    @tool("run_improvement_cycle", "Ask the optimizer to learn from pending feedback now. Produces a new playbook "
          "version that must pass the regression evals; it then waits for human approval unless auto-apply is on.",
          {"type": "object", "properties": {}})
    @_guard
    async def run_improvement_cycle(args: dict) -> dict:
        return _ok(await T(improve.run_improvement_cycle, True))

    @tool("playbook_status", "Show the active playbook (learned rules), pending candidates and pending feedback count.",
          {"type": "object", "properties": {}})
    @_guard
    async def playbook_status(args: dict) -> dict:
        versions = await T(playbook.list_versions)
        active = next((v for v in versions if v["status"] == "active"), None)
        return _ok({"active": active and {"version": active["version"], "rules": active["rules"]},
                    "candidates": [{"version": v["version"], "score": v["eval_score"], "baseline": v["baseline_score"],
                                    "rationale": v["rationale"]} for v in versions if v["status"] == "candidate"],
                    "pending_feedback": len(await T(improve.pending_feedback))})

    return [cash_summary, list_invoices, get_invoice, update_invoice, confirm_invoice, mark_paid, add_missed_invoice,
            search_emails, reprocess_email, run_ingest, generate_report, record_feedback, run_improvement_cycle,
            playbook_status]


def _options(source: str, author: str | None, resume: str | None) -> ClaudeAgentOptions:
    s = get_settings()
    from .invoices import today_local

    tools = build_tools(source, author)
    server = create_sdk_mcp_server(name=SERVER, version="1.0.0", tools=tools)
    env = {"ANTHROPIC_API_KEY": s.anthropic_api_key} if s.anthropic_api_key else {}
    return ClaudeAgentOptions(
        system_prompt=SYSTEM_PROMPT.format(company=s.company_name, mailbox=s.imap_user, today=today_local().isoformat(),
                                           tz=s.timezone, currency=s.base_currency,
                                           channel_hint=CHANNEL_HINTS.get(source, "")),
        mcp_servers={SERVER: server},
        tools=[],  # no built-in tools at all
        allowed_tools=[f"mcp__{SERVER}__{t.name}" for t in tools],
        permission_mode="dontAsk",
        setting_sources=[],
        cwd=str(s.data_dir.resolve()),
        model=s.agent_model,
        max_turns=25,
        max_budget_usd=s.agent_max_budget_usd,
        resume=resume,
        env=env,
    )


async def ask(chat_key: str, prompt: str, *, source: str, author: str | None = None) -> str:
    """Send one user message to the agent, continuing that chat's session."""
    async with _locks[chat_key]:
        row = db.one("SELECT agent_session_id FROM chat_sessions WHERE chat_key=?", (chat_key,))
        resume = row["agent_session_id"] if row else None
        try:
            text, session_id = await _run(prompt, _options(source, author, resume))
        except Exception:
            if not resume:
                raise
            log.warning("Resuming session %s failed; starting a new one", resume, exc_info=True)
            text, session_id = await _run(prompt, _options(source, author, None))
        if session_id:
            db.execute("INSERT INTO chat_sessions (chat_key, agent_session_id, updated_at) VALUES (?,?,?)"
                       " ON CONFLICT(chat_key) DO UPDATE SET agent_session_id=excluded.agent_session_id,"
                       " updated_at=excluded.updated_at", (chat_key, session_id, db.now_iso()))
        return text


async def _run(prompt: str, options: ClaudeAgentOptions) -> tuple[str, str | None]:
    parts: list[str] = []
    final: str | None = None
    session_id: str | None = None
    async for message in query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            parts += [b.text for b in message.content if isinstance(b, TextBlock)]
        elif isinstance(message, ResultMessage):
            session_id = message.session_id
            if message.subtype == "success" and message.result:
                final = message.result
            elif message.subtype != "success":
                log.warning("Agent ended with %s", message.subtype)
                final = (parts[-1] if parts else "") + f"\n\n(Stopped early: {message.subtype.replace('_', ' ')}.)"
    return (final or (parts[-1] if parts else "Sorry, I could not produce an answer.")).strip(), session_id


def reset(chat_key: str) -> None:
    db.execute("DELETE FROM chat_sessions WHERE chat_key=?", (chat_key,))
