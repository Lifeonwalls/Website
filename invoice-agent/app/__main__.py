"""CLI: python -m app <command>

  serve            run web UI + Telegram bot + scheduler
  ingest           fetch mail and extract invoices once
  report [--send]  build the board report (optionally send to Telegram)
  improve          run one self-improvement cycle
  import-eml PATH  import .eml file(s) and extract them (testing / back-fill)
  ask "question"   one-off question to the agent
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    from . import db
    db.init_db()
    args = sys.argv[1:]
    cmd = args[0] if args else "serve"

    if cmd == "serve":
        import uvicorn
        uvicorn.run("app.web:app", host="0.0.0.0", port=8000, proxy_headers=True, forwarded_allow_ips="*")
    elif cmd == "ingest":
        from .pipeline import run_ingest
        print(json.dumps(run_ingest(), indent=1, default=str))
    elif cmd == "report":
        from . import notify, report, telegram_bot

        async def go():
            rep = await report.generate_report()
            print(f"Report {rep['id']}: {rep['html_path']} {rep.get('pdf_path') or ''}")
            if "--send" in args:
                await telegram_bot.start()
                await notify.send_report(rep)
                await telegram_bot.stop()
        asyncio.run(go())
    elif cmd == "improve":
        from .improve import run_improvement_cycle
        print(json.dumps(run_improvement_cycle(force=True), indent=1, default=str))
    elif cmd == "import-eml":
        from .mail import import_eml
        from .pipeline import process_email
        for p in args[1:]:
            for f in ([Path(p)] if Path(p).is_file() else sorted(Path(p).glob("*.eml"))):
                eid = import_eml(f)
                print(f, "->", process_email(eid) if eid else "already imported")
    elif cmd == "ask":
        from .agent import ask
        print(asyncio.run(ask("cli", " ".join(args[1:]), source="web", author="cli")))
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
