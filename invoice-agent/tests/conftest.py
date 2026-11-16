import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SCHEDULER_ENABLED", "false")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("WEB_PASSWORD", "pw")
    monkeypatch.setenv("SESSION_SECRET", "test-secret-0123456789-0123456789-abcdef")
    monkeypatch.setenv("COMMENTARY_ENABLED", "false")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    from app.config import get_settings
    get_settings.cache_clear()
    from app import db
    db.init_db()
    yield
    get_settings.cache_clear()
