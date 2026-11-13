"""Fill a database with realistic demo invoices so the UI and report can be previewed without a mailbox.

    DATA_DIR=data-demo python scripts/seed_demo.py
"""
import random
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import db, invoices  # noqa: E402
from app.models import ExtractedInvoice  # noqa: E402

SUPPLIERS = [("Travis Perkins", "Materials"), ("Dulux Decorator Centre", "Materials"), ("Brandon Hire Station", "Plant hire"),
             ("Green Roof Systems Ltd", "Subcontractors"), ("Biotecture", "Subcontractors"), ("Xero", "Software"),
             ("Octopus Energy", "Utilities"), ("Workspace Group", "Rent"), ("Smith & Co Accountants", "Professional fees"),
             ("Hortus Plants Ltd", "Plants")]


def main() -> None:
    db.init_db()
    random.seed(7)
    today = invoices.today_local()
    for n in range(26):
        sup, cat = random.choice(SUPPLIERS)
        inv_date = today - timedelta(days=random.randint(2, 50))
        terms = random.choice([14, 30, 30, 30, 60])
        net = round(random.uniform(80, 6500), 2)
        stated = random.random() > 0.25
        eid = db.execute("INSERT INTO emails (message_id, from_addr, subject, received_at, body_text, status, classification)"
                         " VALUES (?,?,?,?,?,'processed','invoice_to_pay')",
                         (f"<demo-{n}@example>", f"accounts@{sup.split()[0].lower()}.example", f"Invoice {1000 + n} from {sup}",
                          inv_date.isoformat() + "T09:00:00+00:00", "Please find attached."))
        ex = ExtractedInvoice(
            doc_type="invoice", supplier=sup, supplier_email=None, invoice_number=f"{sup[:3].upper()}-{1000 + n}",
            invoice_date=inv_date.isoformat(), due_date=(inv_date + timedelta(days=terms)).isoformat() if stated else None,
            payment_terms=f"{terms} days" if random.random() > 0.2 else None,
            payment_terms_days=terms if random.random() > 0.2 else None, currency="GBP", net_amount=net,
            vat_amount=round(net * 0.2, 2), total_amount=round(net * 1.2, 2), amount_due=round(net * 1.2, 2),
            already_paid=random.random() < 0.1, payment_reference=None, bank_details=None, po_number=None,
            description=f"{cat} – job {random.randint(200, 260)}", category=cat, source="invoice.pdf",
            confidence=random.choice([0.95, 0.9, 0.92, 0.6]), uncertainties=[])
        invoices.upsert_extracted(eid, inv_date.isoformat(), ex, 0)
    print("Seeded demo data into", db.get_settings().db_path if hasattr(db, "get_settings") else "data dir")


if __name__ == "__main__":
    main()
