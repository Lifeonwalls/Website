# Payables Tracker — 30-Day Outgoing Payments Dashboard

**Client:** Life on Walls (Green Lease Ltd) · internal tool
**Role:** Process design, automation and dashboard build
**Stack:** Gmail accounts inbox · AI invoice-extraction agent · Google Sheets · QuickBooks Online (Projects) · live dashboard · Telegram AI assistant
**Status:** Live
**Result:** Replaces 3–4 hours of manual work every week

---

## Short description (for project cards)

A live accounts tool that captures every supplier invoice in one inbox, reads it with AI, and turns it into a 30-day view of money going out. Each bill is tagged to a job and sorted by due date, with a red, amber or green status. A Telegram AI assistant keeps management updated and answers questions on the go, like "what's due this week?" or "what have we spent on this project?". It replaces 3–4 hours of manual reporting every week.

---

## The challenge

Life on Walls designs, installs and maintains living walls. Projects run for weeks or months and draw on several suppliers, most of them on 30-day terms. Outgoing payments were hard to see:

- **Invoices came in through many channels.** Personal inboxes, WhatsApp, the accounts email and paper receipts.
- **Purchases were made three different ways.** Company card, personal card and bank transfer, often bought on site in real time.
- **No forward view.** Recurring costs and maintenance were tracked, but supplier bills on live projects weren't in one report. Knowing what was due next month relied on memory.
- **Seasonal pressure.** The winter slowdown is the quietest period for the industry, which made cash-flow visibility most urgent then.

The director asked for something simple: a list of invoices received, their due dates, red/green status, and known monthly costs, all in one place.

## The solution

A lightweight payables pipeline that fits the tools the team already uses rather than adding a purchase-order system:

1. **One front door.** Every invoice, receipt and money-related message is forwarded to a single accounts inbox.
2. **AI capture.** An extraction agent reads each document and pulls out the supplier, invoice number, amount, VAT, invoice date and job/project tag. It works out the due date from the supplier's terms (30 days by default).
3. **Structured ledger.** Each record goes into a live Google Sheet, checked against QuickBooks so nothing is entered twice.
4. **Job costing.** Costs are posted against QuickBooks Projects, so each installation shows its committed spend next to its quoted value.
5. **30-day dashboard.** A separate, accounts-only dashboard shows everything due in the next 30 days. That includes supplier bills, plus salaries, rent and card repayments, ordered by due date and flagged red, amber or green.
6. **Telegram AI assistant.** Management gets regular payables updates in Telegram and can ask for custom reports in plain English from anywhere, without opening a spreadsheet or waiting for the weekly meeting.

## Key features

- **Due-date timeline:** a week-by-week view of outgoing payments for the next 30 days
- **Red / amber / green status:** overdue, due within 7 days, or scheduled
- **Per-project spend:** committed costs against each live job, linked to QuickBooks Projects
- **Fixed and variable costs together:** recurring overheads (salaries, rent, card) sit beside supplier invoices
- **"Due soon" summary:** the total value of invoices received in the last 4 weeks that fall due in the next fortnight, ready for the weekly meeting
- **Telegram updates:** regular summaries of what's due and new invoices received, sent straight to management
- **Custom reports on request:** ask the AI assistant for a breakdown by supplier, project or date range and get an answer in the chat
- **Access control:** limited to the director and bookkeeper, separate from the team-wide weekly report

## Impact

- **3–4 hours saved every week.** Collecting invoices, working out due dates, building the report and answering management questions is now automated
- One source of truth for outgoing payments, replacing memory and scattered inboxes
- Management kept informed in real time, with answers in Telegram in seconds rather than waiting for a manual report
- Supplier payments planned ahead of the 30-day terms, protecting relationships with key suppliers
- Cash-flow visibility through the seasonal slowdown
- Groundwork for weekly budget-vs-actual reporting and per-job profitability

## Visuals

| File | Use |
|---|---|
| `images/payables-dashboard.png` | Hero image: the 30-day payables dashboard |
| `images/payables-workflow.png` | How it works: invoice to dashboard pipeline |
| `images/payables-timeline.png` | Detail: 30-day outgoing payments by week |
| `images/payables-telegram.png` | Telegram AI assistant: updates and on-demand reports |

SVG versions are in the same folder for crisp scaling on the web. All figures and supplier names in the visuals are illustrative sample data.
