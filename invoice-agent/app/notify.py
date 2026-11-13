"""Outbound Telegram notifications (used by the scheduler, web UI and agent tools)."""
from __future__ import annotations

import logging
from pathlib import Path

from .config import get_settings

log = logging.getLogger(__name__)
_bot = None  # telegram.Bot, set by telegram_bot.start()
# Maps Telegram message ids of report notifications -> report id, so replies become report feedback.
report_messages: dict[tuple[int, int], int] = {}


def set_bot(bot) -> None:
    global _bot
    _bot = bot


async def send_text(text: str, chat_ids: list[int] | None = None) -> None:
    if _bot is None:
        log.info("Telegram not configured; message not sent: %s", text[:200])
        return
    for chat_id in chat_ids or get_settings().notify_chat_ids:
        try:
            await _bot.send_message(chat_id=chat_id, text=text[:4000], parse_mode="HTML", disable_web_page_preview=True)
        except Exception:
            log.exception("Telegram send to %s failed", chat_id)


async def send_report(report: dict, chat_ids: list[int] | None = None) -> None:
    from .report import telegram_summary

    if _bot is None:
        log.info("Telegram not configured; report %s not sent", report["id"])
        return
    text = telegram_summary(report)
    attachment = report.get("pdf_path") or report.get("html_path")
    for chat_id in chat_ids or get_settings().notify_chat_ids:
        try:
            msg = await _bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML", disable_web_page_preview=True)
            report_messages[(chat_id, msg.message_id)] = report["id"]
            if attachment and Path(attachment).exists():
                with open(attachment, "rb") as fh:
                    doc = await _bot.send_document(chat_id=chat_id, document=fh, filename=Path(attachment).name,
                                                   caption="Full report")
                report_messages[(chat_id, doc.message_id)] = report["id"]
        except Exception:
            log.exception("Telegram report send to %s failed", chat_id)
