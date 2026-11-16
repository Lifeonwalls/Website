"""Pre-flight checks: `python -m app check`. Tests every external connection without changing anything."""
from __future__ import annotations

import imaplib
import json
import socket
import urllib.error
import urllib.request
from datetime import datetime, timedelta

from .config import get_settings

OK, WARN, FAIL = "\033[32m✔\033[0m", "\033[33m!\033[0m", "\033[31m✘\033[0m"


def _telegram(method: str, token: str) -> dict:
    with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/{method}", timeout=15) as r:
        return json.loads(r.read())


def check_anthropic() -> bool:
    s = get_settings()
    import anthropic

    if not s.anthropic_api_key:
        print(f"{FAIL} ANTHROPIC_API_KEY is empty")
        return False
    try:
        anthropic.Anthropic(api_key=s.anthropic_api_key).models.retrieve(s.extraction_model)
        print(f"{OK} Anthropic API key works; model {s.extraction_model} is available")
        return True
    except anthropic.AuthenticationError:
        print(f"{FAIL} Anthropic API key was rejected - copy it again from console.anthropic.com")
    except anthropic.NotFoundError:
        print(f"{FAIL} Model {s.extraction_model} not available to this key")
    except Exception as e:
        print(f"{FAIL} Anthropic API: {e}")
    return False


def check_imap() -> bool:
    s = get_settings()
    if not s.imap_password:
        print(f"{FAIL} IMAP_PASSWORD is empty")
        return False
    try:
        conn = imaplib.IMAP4_SSL(s.imap_host, s.imap_port, timeout=30)
    except Exception as e:
        print(f"{FAIL} Cannot reach {s.imap_host}:{s.imap_port}: {e}")
        return False
    try:
        conn.login(s.imap_user, s.imap_password)
    except imaplib.IMAP4.error as e:
        msg = str(e)
        print(f"{FAIL} Login as {s.imap_user} failed: {msg}")
        if "gmail" in s.imap_host:
            print("    Google Workspace needs: IMAP enabled for the user, 2-Step Verification on, and an App Password")
            print("    (myaccount.google.com/apppasswords while signed in as the accounts user).")
        return False
    ok = True
    since = (datetime.now() - timedelta(days=s.initial_lookback_days)).strftime("%d-%b-%Y")
    for folder in s.folders:
        typ, _ = conn.select(f'"{folder}"', readonly=True)
        if typ != "OK":
            print(f"{FAIL} Folder '{folder}' not found")
            ok = False
            continue
        typ, data = conn.uid("SEARCH", None, f"SINCE {since}")
        n = len((data[0] or b"").split())
        print(f"{OK} Mailbox {s.imap_user} / {folder}: {n} emails in the last {s.initial_lookback_days} days (read-only)")
    conn.logout()
    return ok


def check_telegram() -> bool:
    s = get_settings()
    if not s.telegram_bot_token:
        print(f"{WARN} TELEGRAM_BOT_TOKEN empty - Telegram is disabled (web UI still works)")
        return True
    try:
        me = _telegram("getMe", s.telegram_bot_token)["result"]
    except urllib.error.HTTPError:
        print(f"{FAIL} Telegram token rejected - copy it again from @BotFather")
        return False
    except Exception as e:
        print(f"{FAIL} Telegram: {e}")
        return False
    print(f"{OK} Telegram bot @{me['username']} is reachable")
    chats: dict[int, str] = {}
    try:
        for u in _telegram("getUpdates", s.telegram_bot_token).get("result", []):
            msg = u.get("message") or u.get("my_chat_member") or u.get("channel_post") or {}
            chat = msg.get("chat")
            if chat:
                chats[chat["id"]] = chat.get("title") or " ".join(
                    x for x in (chat.get("first_name"), chat.get("last_name")) if x) or chat.get("username", "")
    except Exception:
        pass
    if chats:
        print("    Chats that have messaged the bot recently:")
        for cid, name in chats.items():
            print(f"      {cid:>16}  {name}")
    else:
        print(f"    No recent messages. Send any message to @{me['username']} (and add it to the board group),")
        print("    then run this check again to see the chat ids.")
    if not s.allowed_chat_ids:
        print(f"{WARN} TELEGRAM_ALLOWED_CHAT_IDS is empty - nobody can use the bot yet")
    return True


def check_web() -> bool:
    s = get_settings()
    ok = True
    if len(s.web_password) < 12:
        print(f"{FAIL} WEB_PASSWORD must be at least 12 characters")
        ok = False
    if s.session_secret in ("change-me", "") or len(s.session_secret) < 32:
        print(f"{FAIL} SESSION_SECRET must be a random string of 32+ characters")
        ok = False
    host = s.public_base_url.split("://")[-1].split("/")[0].split(":")[0]
    try:
        print(f"{OK} {host} resolves to {socket.gethostbyname(host)} (must be this server's public IP)")
    except OSError:
        print(f"{WARN} {host} does not resolve yet - add a DNS A record pointing at this server")
    if ok:
        print(f"{OK} Web login configured for user '{s.web_username}'")
    return ok


def run() -> int:
    print("Checking configuration…\n")
    results = [check_web(), check_anthropic(), check_imap(), check_telegram()]
    print()
    if all(results):
        print(f"{OK} All checks passed.")
        return 0
    print(f"{FAIL} Fix the items above, then run the check again.")
    return 1
