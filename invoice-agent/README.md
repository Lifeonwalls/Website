# Payables agent – Life on Walls

Reads every email that arrives at **accounts@lifeonwalls.co.uk**, pulls out the supplier invoices that have to be paid, and turns them into a board-ready payables report. The report shows the detailed invoices, the amount due on each, when it is due, and the totals due in the next 7, 14 and 30 days. You can use the agent from a web UI or from Telegram, and it gets better from your feedback.

```
 accounts@ mailbox ──IMAP (read-only)──► extraction (Claude, structured output) ──► SQLite
                                               ▲  playbook vN (learned rules)          │
                                               │                                      ▼
 feedback (web / Telegram / chat) ──► eval cases ──► optimizer ──► regression gate ──► approve
                                                                                      │
 Web UI (dashboard, invoices, chat, learning)  ◄──── Agent (Claude Agent SDK + tools) ┤
 Telegram bot (commands, chat, notifications)  ◄──── weekly report (HTML + PDF, link) ┘
```

## What each part does

| Part | File | Notes |
|---|---|---|
| Mailbox reader | `app/mail.py` | IMAP over TLS. It opens the mailbox with `EXAMINE` (read-only) and fetches bodies with `BODY.PEEK`, so nothing is marked read, moved or deleted. It only looks at messages since the last UID it saw. Emails with no attachment and no invoice-related words are skipped, which keeps cost down. |
| Extraction | `app/extract.py`, `app/models.py` | Sends PDFs, images, XML/CSV and the email body to Claude and asks for structured (Pydantic) output. Each email is classified as invoice / reminder / statement / credit note / already paid / remittance / our own sales invoice / quote / not finance. Remittance emails mark the matching invoices as paid. |
| Invoice store | `app/invoices.py` | Deduplicates on supplier + invoice number, so reminders update the existing invoice. Due dates are labelled *stated*, *from terms* or *estimated*. Anything doubtful is flagged **Check**. Fields a human corrects are locked and never overwritten. |
| Report | `app/report.py`, `templates/report.html` | All figures are calculated in code, not by the model. Covers overdue, due in the next 7/14/30 days (cumulative), weekly chart, suppliers, full invoice table, checks before payment, received/paid this week, credit notes and other currencies. Claude writes a short commentary using only the numbers it is given. The page uses Life on Walls branding and prints to A4 PDF. |
| Agent | `app/agent.py` | Built on the Claude Agent SDK. **Built-in tools are turned off (`tools=[]`)**, so it has no shell, no file access and no web. It has 14 payables tools: summary, list/search, correct, confirm, mark paid, add missed invoice, re-read email, check mailbox, build report, record feedback, run improvement, show playbook. Each chat keeps its own session. |
| Web UI | `app/web.py`, `templates/` | Pages: Dashboard, Invoices (click a row to correct / confirm / mark paid / mark not payable, and open the original PDF), Mailbox, Reports (PDF + board link), Ask the agent, Learning. |
| Telegram | `app/telegram_bot.py` | Commands: `/summary`, `/due 14`, `/review`, `/report`, `/ingest`, `/feedback`, `/improve`, `/playbook`, `/approve v`, `/reject v`, `/new`. Plain text goes to the agent. **Replying to a report message records it as feedback on that report.** Only chat IDs on the allow-list can use it. |
| Scheduler | `app/scheduler.py` | Checks the mailbox every 2 h, builds and sends the report Monday 08:00, and runs a learning cycle Sunday 07:00 (all Europe/London, all configurable). |
| Self-improvement | `app/improve.py`, `app/playbook.py` | See below. |

## How the self-improvement loop works

1. **Feedback is collected everywhere.** Field corrections, "not a payable", "you missed this one", "looks right ✓", report replies on Telegram, and free-text comments in the web UI or chat.
2. **Corrections become tests.** Each email a human corrected or confirmed turns into an eval case with the expected answer.
3. **The optimizer proposes a new playbook.** It reads the current playbook, the pending feedback and the current eval failures, then writes new rules: general extraction rules, supplier-specific rules, report preferences and excluded suppliers. It is told never to hard-code an invoice number or amount.
4. **Regression gate.** The candidate playbook is replayed on every eval case. It is kept only if **the score does not drop and no case that passed before now fails**. Otherwise it is stored as *rejected*, with the reasons.
5. **Human approval (default).** You get a Telegram message with the score and the rationale, and the Learning page shows a rule diff. Approve with `/approve N` or the button. Set `AUTO_APPLY_IMPROVEMENTS=true` once you trust it.
6. **Apply.** The new playbook goes live. Emails whose invoices still need a check are re-read with it, and locked fields are kept. Every version is kept, and you can roll back in one click.

Cost: each cycle runs up to `EVAL_MAX_CASES` (default 40) emails twice through extraction.

## Deploy on the VPS (Docker)

Before you start, have these ready:
- an Ubuntu/Debian VPS you can SSH into, with ports 80 and 443 open;
- a DNS A record (e.g. `payables.lifeonwalls.co.uk`) pointing at the VPS's public IP. If your domain has a wildcard record, the name may already resolve somewhere else, so check that it shows the VPS IP;
- an Anthropic API key, the accounts@ App Password, and a Telegram bot token from @BotFather.

Get the code onto the VPS:
```bash
git clone -b claude/jolly-franklin-4qxo1h https://github.com/lifeonwalls/website.git
```
Go into the project folder:
```bash
cd website/invoice-agent
```
Run the setup:
```bash
./setup.sh
```

`setup.sh` installs Docker if it is missing (it asks first). It asks for each value, hiding secrets as you type, and generates the web password and session secret. It builds the app and tests every connection with `python -m app check`: the API key, the mailbox login and how many emails it can see, the Telegram bot and the chat ids that have messaged it, and DNS. Then it opens the firewall and starts everything behind HTTPS. **If the server already runs Caddy** (for example the one in front of n8n), it doesn't start a second one. It adds a `payables` site block to the existing Caddyfile (after making a backup and asking you), joins the agent to that Caddy's Docker network, and reloads Caddy. If the reload fails, the old Caddyfile is put back. Re-run it at any time to change a value; press Enter to keep the current one.

You can re-test the settings at any point (this changes nothing):
```bash
docker compose run --rm --no-deps agent python -m app check
```

Data lives in `./data` (database, attachments, reports) and `./claude-sessions` (chat history), so back up both.

### Getting the mailbox password (Google Workspace)
1. In the Google Admin console, go to **Apps → Google Workspace → Gmail → End User Access** and make sure IMAP is allowed.
2. Sign in as **accounts@lifeonwalls.co.uk** and turn on **2-Step Verification** (myaccount.google.com/security).
3. Still signed in as accounts@, open **myaccount.google.com/apppasswords**, create one called "Payables agent", and copy the 16 letters.

If App Passwords is missing from that page, an admin has turned it off (Admin console → Security → Authentication → Less secure apps / App passwords). In that case, tell me and I'll switch the mailbox login to Google OAuth.

### Setting up Telegram
1. In Telegram, message **@BotFather**, send `/newbot`, and copy the token.
2. During `setup.sh`, send your new bot any message. For the board, add the bot to the group and post a message there.
3. The check prints each chat's id (groups are negative numbers). Paste them when asked.

### CLI (inside the container)

Check the mailbox once:
```bash
docker compose exec agent python -m app ingest
```
Build the report and send it to Telegram:
```bash
docker compose exec agent python -m app report --send
```
Run one learning cycle:
```bash
docker compose exec agent python -m app improve
```
Ask the agent a one-off question:
```bash
docker compose exec agent python -m app ask "what is due this week?"
```

## Local development

Install the dependencies:
```bash
pip install -r requirements-dev.txt
```
Run the tests (no API calls; Claude is mocked):
```bash
python -m pytest -q
```
Load demo data so the UI can be previewed without a mailbox:
```bash
DATA_DIR=data-demo python scripts/seed_demo.py
```
Start the app against the demo data:
```bash
DATA_DIR=data-demo WEB_PASSWORD=pw SESSION_SECRET=dev-secret-123 python -m app serve
```

## Notes and limits
- **"Paid" is only as accurate as what the system is told.** An invoice becomes paid when a remittance email says so, when it was a card or direct-debit receipt, or when someone marks it paid. The natural next step is a QuickBooks sync to mark bills paid automatically.
- **Other currencies are not converted.** They are shown separately.
- **Estimated due dates are flagged.** When an invoice states no due date and no terms, the system assumes `DEFAULT_PAYMENT_TERMS_DAYS` and marks the date "estimated".
- **Anyone with a board link can view that report.** Links use an unguessable token. Turn them off with `PUBLIC_SHARE_LINKS=false`.
- **Model refusals.** If a model declines a request, extraction retries once on `FALLBACK_MODEL`. If that also fails, the email shows as an error in the Mailbox page.
