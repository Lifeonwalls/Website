"""Background jobs: mailbox ingest, weekly report, weekly self-improvement."""
from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from . import improve, notify, pipeline, report
from .config import get_settings

log = logging.getLogger(__name__)
_scheduler: AsyncIOScheduler | None = None


async def job_ingest() -> None:
    try:
        res = await asyncio.to_thread(pipeline.run_ingest)
        log.info("Ingest: %s", res)
        if res["errors"]:
            await notify.send_text(f"⚠️ {len(res['errors'])} email(s) in the accounts mailbox could not be read automatically.")
    except Exception as e:
        log.exception("Scheduled ingest failed")
        await notify.send_text(f"⚠️ Mailbox check failed: {e}")


async def job_report() -> None:
    try:
        await job_ingest()  # make sure the report includes this morning's emails
        rep = await report.generate_report()
        await notify.send_report(rep)
    except Exception as e:
        log.exception("Scheduled report failed")
        await notify.send_text(f"⚠️ Weekly payables report failed: {e}")


async def job_improve() -> None:
    from .telegram_bot import format_improvement
    try:
        res = await asyncio.to_thread(improve.run_improvement_cycle, False)
        if res.get("status") != "skipped":
            await notify.send_text(format_improvement(res))
    except Exception as e:
        log.exception("Scheduled improvement failed")
        await notify.send_text(f"⚠️ Self-improvement cycle failed: {e}")


def start() -> AsyncIOScheduler | None:
    global _scheduler
    s = get_settings()
    if not s.scheduler_enabled:
        return None
    sch = AsyncIOScheduler(timezone=s.timezone)
    sch.add_job(job_ingest, CronTrigger.from_crontab(s.ingest_cron, timezone=s.timezone), id="ingest",
                max_instances=1, coalesce=True)
    sch.add_job(job_report, CronTrigger.from_crontab(s.report_cron, timezone=s.timezone), id="report",
                max_instances=1, coalesce=True)
    sch.add_job(job_improve, CronTrigger.from_crontab(s.improve_cron, timezone=s.timezone), id="improve",
                max_instances=1, coalesce=True)
    sch.start()
    _scheduler = sch
    log.info("Scheduler started: ingest=%s report=%s improve=%s", s.ingest_cron, s.report_cron, s.improve_cron)
    return sch


def stop() -> None:
    if _scheduler:
        _scheduler.shutdown(wait=False)
