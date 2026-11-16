"""Central configuration, loaded from environment variables / .env."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Company / report ----------------------------------------------------
    company_name: str = "Life on Walls"
    base_currency: str = "GBP"
    timezone: str = "Europe/London"
    public_base_url: str = "http://localhost:8000"  # used in Telegram links / share links

    # --- Mailbox (IMAP, read-only) -------------------------------------------
    imap_host: str = "imap.gmail.com"
    imap_port: int = 993
    imap_user: str = "accounts@lifeonwalls.co.uk"
    imap_password: str = ""  # app password; never commit
    imap_folders: str = "INBOX"  # comma separated
    initial_lookback_days: int = 60
    # Only emails that have an attachment OR match one of these words are sent to Claude.
    prefilter_keywords: str = (
        "invoice,bill,payment,due,statement,remittance,receipt,amount,overdue,reminder,"
        "credit note,proforma,pro-forma,balance,account,vat"
    )
    max_attachment_mb: int = 20

    # --- Claude ----------------------------------------------------------------
    anthropic_api_key: str = ""
    extraction_model: str = "claude-opus-5-5"
    extraction_effort: str = "medium"
    fallback_model: str = "claude-opus-5"  # retried once if the primary model declines
    agent_model: str = "claude-opus-5-5"
    optimizer_model: str = "claude-opus-5-5"
    optimizer_effort: str = "high"
    agent_max_budget_usd: float = 1.0  # per chat turn
    commentary_enabled: bool = True  # Claude-written board commentary in reports

    # --- Due date defaults -----------------------------------------------------
    default_payment_terms_days: int = 30

    # --- Web UI ----------------------------------------------------------------
    web_username: str = "admin"
    web_password: str = ""  # required to log in; empty disables login (refuses all)
    session_secret: str = ""  # validated by `python -m app check`; web.py refuses to start without it
    public_share_links: bool = True  # /r/<token> read-only report links for the board

    # --- Telegram --------------------------------------------------------------
    telegram_bot_token: str = ""
    telegram_allowed_chat_ids: str = ""  # comma separated; who may talk to the bot
    telegram_notify_chat_ids: str = ""  # comma separated; who receives report notifications

    # --- Scheduling (cron, in `timezone`) --------------------------------------
    ingest_cron: str = "0 */2 * * *"  # every 2 hours
    report_cron: str = "0 8 * * mon"  # Monday 08:00
    improve_cron: str = "0 7 * * sun"  # Sunday 07:00
    scheduler_enabled: bool = True

    # --- Self-improvement ------------------------------------------------------
    auto_apply_improvements: bool = False  # False = a human approves each new playbook
    eval_max_cases: int = 40
    min_feedback_for_improvement: int = 1

    # --- Storage ---------------------------------------------------------------
    data_dir: Path = Path("data")

    @property
    def db_path(self) -> Path:
        return self.data_dir / "invoices.db"

    @property
    def attachments_dir(self) -> Path:
        return self.data_dir / "attachments"

    @property
    def reports_dir(self) -> Path:
        return self.data_dir / "reports"

    @staticmethod
    def _csv(value: str) -> list[str]:
        return [v.strip() for v in value.split(",") if v.strip()]

    @property
    def folders(self) -> list[str]:
        return self._csv(self.imap_folders)

    @property
    def keywords(self) -> list[str]:
        return [k.lower() for k in self._csv(self.prefilter_keywords)]

    @property
    def allowed_chat_ids(self) -> set[int]:
        return {int(x) for x in self._csv(self.telegram_allowed_chat_ids)}

    @property
    def notify_chat_ids(self) -> list[int]:
        ids = self._csv(self.telegram_notify_chat_ids) or self._csv(self.telegram_allowed_chat_ids)
        return [int(x) for x in ids]


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    for d in (s.data_dir, s.attachments_dir, s.reports_dir):
        d.mkdir(parents=True, exist_ok=True)
    return s
