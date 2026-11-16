"""Telegram interface: notifications, commands, free-text chat with the agent and feedback capture."""
from __future__ import annotations

import asyncio
import html
import logging

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from . import agent, improve, notify, pipeline, playbook, report
from .config import get_settings
from .report import money

log = logging.getLogger(__name__)
_app: Application | None = None

HELP = """<b>Payables assistant</b>
/summary – cash needed: overdue, 7 / 14 / 30 days
/due 14 – invoices due in the next N days
/review – invoices that need a human check
/report – build the board report now and send it here
/ingest – check the accounts mailbox now
/feedback &lt;text&gt; – tell the agent what to do better
/improve – learn from feedback now
/playbook – show learned rules and pending versions
/approve &lt;v&gt; · /reject &lt;v&gt; – decide on a new playbook version
/new – start a fresh conversation

Or just write a question, e.g. “what do we owe Travis Perkins?” or “invoice 4471 is actually due on 30 Nov”.
Reply to a report message to give feedback on that report."""


def _allowed(update: Update) -> bool:
    allowed = get_settings().allowed_chat_ids
    chat = update.effective_chat
    return bool(chat and (chat.id in allowed))


def _author(update: Update) -> str:
    u = update.effective_user
    return f"telegram:{u.username or u.full_name}" if u else "telegram"


async def _guarded(update: Update, fn) -> None:
    if not _allowed(update):
        if update.effective_chat:
            log.warning("Rejected Telegram chat %s", update.effective_chat.id)
            await update.effective_message.reply_text(
                f"This chat is not authorised. Ask an admin to add chat id {update.effective_chat.id}.")
        return
    try:
        await fn()
    except Exception as e:
        log.exception("Telegram handler failed")
        await update.effective_message.reply_text(f"Something went wrong: {e}")


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await _guarded(update, lambda: update.effective_message.reply_html(HELP))


async def cmd_summary(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    async def run():
        sm = await asyncio.to_thread(report.compute_summary)
        h, cur = sm["headline"], sm["base_currency"]
        lines = [f"<b>Payables as of {report.fmt_date(sm['as_of'])}</b>",
                 f"Overdue: <b>{money(h['overdue'], cur)}</b> ({sm['counts'].get('overdue', 0)})",
                 f"Next 7 days: <b>{money(h['within_7'], cur)}</b>",
                 f"Next 14 days: <b>{money(h['within_14'], cur)}</b>",
                 f"Next 30 days: <b>{money(h['within_30'], cur)}</b>",
                 f"Total outstanding: {money(h['outstanding'], cur)} ({sm['open_count']} invoices)"]
        if sm["needs_review"]:
            lines.append(f"⚠️ {len(sm['needs_review'])} need a check – /review")
        await update.effective_message.reply_html("\n".join(lines))
    await _guarded(update, run)


async def cmd_due(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    async def run():
        from .invoices import find_invoices
        days = int(ctx.args[0]) if ctx.args and ctx.args[0].isdigit() else 7
        rows = await asyncio.to_thread(find_invoices, None, "unpaid", days)
        if not rows:
            await update.effective_message.reply_text(f"Nothing due in the next {days} days.")
            return
        total = sum(r["amount_due"] for r in rows if r["currency"] == get_settings().base_currency)
        lines = [f"<b>Due within {days} days (incl. overdue): {money(total)}</b>"]
        for r in rows[:30]:
            flag = " ⚠️" if r["needs_review"] else ""
            lines.append(f"{report.fmt_date(r['due_date'])[:10]} · {html.escape(r['supplier'])} · "
                         f"{html.escape(r['invoice_number'])} · <b>{money(r['amount_due'], r['currency'])}</b>{flag}")
        if len(rows) > 30:
            lines.append(f"…and {len(rows) - 30} more")
        await update.effective_message.reply_html("\n".join(lines))
    await _guarded(update, run)


async def cmd_review(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    async def run():
        from .invoices import find_invoices
        rows = await asyncio.to_thread(find_invoices, None, "unpaid", None, False, True)
        if not rows:
            await update.effective_message.reply_text("Nothing needs review. 👍")
            return
        lines = ["<b>Needs a human check</b>"]
        for r in rows[:20]:
            lines.append(f"#{r['id']} {html.escape(r['supplier'])} {html.escape(r['invoice_number'])} "
                         f"{money(r['amount_due'], r['currency'])} – {html.escape('; '.join(r['review_reasons'])[:150])}")
        lines.append("\nReply in plain words to correct or confirm, e.g. “#12 is correct” or “#12 due date is 28 Nov”.")
        await update.effective_message.reply_html("\n".join(lines))
    await _guarded(update, run)


async def cmd_report(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    async def run():
        await update.effective_message.reply_text("Building the report…")
        rep = await report.generate_report()
        await notify.send_report(rep, [update.effective_chat.id])
    await _guarded(update, run)


async def cmd_ingest(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    async def run():
        await update.effective_message.reply_text("Checking the accounts mailbox…")
        res = await asyncio.to_thread(pipeline.run_ingest)
        msg = (f"New emails: {res['new_emails']}\nProcessed: {res['processed']}\n"
               f"Invoices found/updated: {res['invoices_found']}")
        if res["payment_notes"]:
            msg += "\n" + "\n".join(res["payment_notes"])
        if res["errors"]:
            msg += f"\n⚠️ {len(res['errors'])} email(s) failed – see the web UI"
        await update.effective_message.reply_text(msg)
    await _guarded(update, run)


async def cmd_feedback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    async def run():
        text = " ".join(ctx.args or []).strip()
        if not text:
            await update.effective_message.reply_text("Usage: /feedback <what should be better>")
            return
        await asyncio.to_thread(lambda: improve.record_feedback(source="telegram", author=_author(update),
                                                                kind="general", comment=text))
        await update.effective_message.reply_text("Thanks – noted. It will be used in the next improvement cycle (/improve to run now).")
    await _guarded(update, run)


async def cmd_improve(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    async def run():
        await update.effective_message.reply_text("Learning from feedback and replaying the regression tests… (a few minutes)")
        res = await asyncio.to_thread(improve.run_improvement_cycle, True)
        await update.effective_message.reply_html(format_improvement(res))
    await _guarded(update, run)


async def cmd_playbook(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    async def run():
        versions = await asyncio.to_thread(playbook.list_versions)
        active = next(v for v in versions if v["status"] == "active")
        lines = [f"<b>Active playbook v{active['version']}</b>"]
        lines += [f"• {html.escape(r)}" for r in active["rules"]["extraction_rules"][:15]]
        if active["rules"]["supplier_rules"]:
            lines.append(f"+ {len(active['rules']['supplier_rules'])} supplier rules")
        cands = [v for v in versions if v["status"] == "candidate"]
        for c in cands:
            lines.append(f"\nCandidate v{c['version']}: score {c['eval_score']} vs {c['baseline_score']} – "
                         f"/approve {c['version']} or /reject {c['version']}")
        pending = len(await asyncio.to_thread(improve.pending_feedback))
        lines.append(f"\nPending feedback items: {pending}")
        await update.effective_message.reply_html("\n".join(lines)[:4000])
    await _guarded(update, run)


async def cmd_approve(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    async def run():
        if not ctx.args or not ctx.args[0].isdigit():
            await update.effective_message.reply_text("Usage: /approve <version>")
            return
        v = int(ctx.args[0])
        n = await asyncio.to_thread(improve.apply_version, v)
        await update.effective_message.reply_text(f"Playbook v{v} is now active. Re-checked {n} email(s) with it.")
    await _guarded(update, run)


async def cmd_reject(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    async def run():
        if not ctx.args or not ctx.args[0].isdigit():
            await update.effective_message.reply_text("Usage: /reject <version>")
            return
        await asyncio.to_thread(playbook.reject, int(ctx.args[0]))
        await update.effective_message.reply_text(f"Playbook v{ctx.args[0]} rejected.")
    await _guarded(update, run)


async def cmd_new(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    async def run():
        agent.reset(f"telegram:{update.effective_chat.id}")
        await update.effective_message.reply_text("Started a fresh conversation.")
    await _guarded(update, run)


async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    async def run():
        msg = update.effective_message
        text = msg.text or ""
        reply_to = msg.reply_to_message
        if reply_to and (update.effective_chat.id, reply_to.message_id) in notify.report_messages:
            rid = notify.report_messages[(update.effective_chat.id, reply_to.message_id)]
            await asyncio.to_thread(lambda: improve.record_feedback(
                source="telegram", author=_author(update), kind="report", comment=text,
                target_type="report", target_id=rid))
            text = f"[This message is feedback on board report #{rid}; it has already been recorded as report feedback.]\n{text}"
        log.info("Telegram message from chat %s (%s): %s", update.effective_chat.id, _author(update), text[:200])

        async def keep_typing():  # Telegram's "typing…" lasts 5 s; keep it up while the agent works
            while True:
                try:
                    await ctx.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
                except Exception:
                    pass
                await asyncio.sleep(4)

        typing = asyncio.create_task(keep_typing())
        try:
            answer = await asyncio.wait_for(
                agent.ask(f"telegram:{update.effective_chat.id}", text, source="telegram", author=_author(update)),
                timeout=300)
        except asyncio.TimeoutError:
            answer = "Sorry, that took too long (over 5 minutes) and was stopped. Please try again or ask in smaller steps."
        finally:
            typing.cancel()
        log.info("Agent replied to chat %s (%d chars)", update.effective_chat.id, len(answer))
        for i in range(0, len(answer), 4000):
            await msg.reply_text(answer[i:i + 4000])
    await _guarded(update, run)


def format_improvement(res: dict) -> str:
    st = res.get("status")
    if st == "skipped":
        return f"No improvement run: {html.escape(res.get('reason', ''))}"
    head = {"activated": "✅ New playbook activated", "awaiting_approval": "🧠 New playbook ready for approval",
            "rejected_by_eval": "↩️ Proposed playbook rejected by the regression tests"}.get(st, st)
    lines = [f"<b>{head}</b> (v{res.get('version')})",
             f"Eval score: {res.get('candidate')} vs current {res.get('baseline')}"]
    if res.get("regressions"):
        lines.append(f"Would have broken {len(res['regressions'])} previously-correct case(s).")
    if res.get("rationale"):
        lines.append(html.escape(res["rationale"][:1500]))
    if st == "awaiting_approval":
        lines.append(f"\n/approve {res['version']} or /reject {res['version']}")
    return "\n".join(lines)


async def start() -> Application | None:
    global _app
    s = get_settings()
    if not s.telegram_bot_token:
        log.info("TELEGRAM_BOT_TOKEN not set; Telegram disabled")
        return None
    app = Application.builder().token(s.telegram_bot_token).concurrent_updates(True).build()
    for name, fn in [("start", cmd_help), ("help", cmd_help), ("summary", cmd_summary), ("due", cmd_due),
                     ("review", cmd_review), ("report", cmd_report), ("ingest", cmd_ingest), ("feedback", cmd_feedback),
                     ("improve", cmd_improve), ("playbook", cmd_playbook), ("approve", cmd_approve),
                     ("reject", cmd_reject), ("new", cmd_new)]:
        app.add_handler(CommandHandler(name, fn))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    notify.set_bot(app.bot)
    _app = app
    log.info("Telegram bot started")
    return app


async def stop() -> None:
    if _app:
        await _app.updater.stop()
        await _app.stop()
        await _app.shutdown()
