import json
from datetime import date, timedelta

import pytest

from app import db, improve, invoices, playbook, report
from app.models import EmailExtraction, ExtractedInvoice


def inv(**kw) -> ExtractedInvoice:
    base = dict(doc_type="invoice", supplier="Acme Paints Ltd", supplier_email="ar@acme.test", invoice_number="INV-1001",
                invoice_date="2026-11-01", due_date="2026-12-01", payment_terms="30 days", payment_terms_days=30,
                currency="GBP", net_amount=100.0, vat_amount=20.0, total_amount=120.0, amount_due=120.0,
                already_paid=False, payment_reference=None, bank_details=None, po_number=None, description="Paint",
                category="Materials", source="invoice.pdf", confidence=0.95, uncertainties=[])
    base.update(kw)
    return ExtractedInvoice(**base)


def add_email(subject="Invoice INV-1001", received="2026-11-02T09:00:00+00:00") -> int:
    return db.execute("INSERT INTO emails (message_id, from_addr, subject, received_at, body_text, status)"
                      " VALUES (?,?,?,?,?, 'processed')", (f"<{subject}-{received}>", "ar@acme.test", subject, received, "body"))


# --- due dates ---------------------------------------------------------------
def test_due_date_stated_terms_default():
    assert invoices.resolve_due_date(inv(), None, 30) == (date(2026, 12, 1), "stated")
    assert invoices.resolve_due_date(inv(due_date=None, payment_terms_days=14), None, 30) == (date(2026, 11, 15), "terms")
    assert invoices.resolve_due_date(inv(due_date=None, payment_terms_days=None, payment_terms="Due on receipt"), None, 30) == (date(2026, 11, 1), "terms")
    assert invoices.resolve_due_date(inv(due_date=None, payment_terms_days=None, payment_terms=None), None, 30) == (date(2026, 12, 1), "default")


def test_keys_normalise():
    assert invoices.supplier_key("Acme Paints Ltd.") == invoices.supplier_key("ACME PAINTS LIMITED")
    assert invoices.invoice_number_key("inv-1001") == invoices.invoice_number_key("INV 1001")


# --- upserts & human corrections -----------------------------------------------
def test_upsert_dedupes_and_respects_locked_fields():
    e1 = add_email()
    iid = invoices.upsert_extracted(e1, "2026-11-02", inv(), 0)
    invoices.update_invoice(iid, {"amount_due": "99.50"}, source="web", comment="part paid")
    # reminder email for the same invoice arrives later with the original amount
    e2 = add_email("Reminder INV-1001", "2026-11-20T09:00:00+00:00")
    iid2 = invoices.upsert_extracted(e2, "2026-11-20", inv(supplier="ACME PAINTS LIMITED", invoice_number="inv 1001"), 0)
    assert iid2 == iid
    row = invoices.get_invoice(iid)
    assert row["amount_due"] == 99.5  # human correction kept
    assert db.one("SELECT COUNT(*) n FROM invoices")["n"] == 1


def test_correction_creates_feedback_and_eval_case():
    e1 = add_email()
    iid = invoices.upsert_extracted(e1, "2026-11-02", inv(), 0)
    invoices.update_invoice(iid, {"due_date": "2026-12-15"}, source="telegram", comment="footer date")
    fb = db.rows("SELECT * FROM feedback")
    assert fb[0]["kind"] == "field_correction" and fb[0]["new_value"] == "2026-12-15"
    case = json.loads(db.one("SELECT expected_json FROM eval_cases WHERE email_id=?", (e1,))["expected_json"])
    assert case["is_payable"] and case["invoices"][0]["due_date"] == "2026-12-15"


def test_ignored_becomes_negative_case():
    e1 = add_email("Newsletter")
    iid = invoices.upsert_extracted(e1, "2026-11-02", inv(), 0)
    invoices.update_invoice(iid, {"status": "ignored"}, source="web")
    case = json.loads(db.one("SELECT expected_json FROM eval_cases")["expected_json"])
    assert case == {"is_payable": False, "invoices": []}


def test_already_paid_and_remittance():
    e1 = add_email()
    iid = invoices.upsert_extracted(e1, None, inv(already_paid=True, invoice_number="DD-1"), 0)
    assert invoices.get_invoice(iid)["status"] == "paid"
    iid2 = invoices.upsert_extracted(e1, None, inv(invoice_number="INV-2002"), 1)
    notes = invoices.mark_paid_by_numbers(["INV2002"], e1)
    assert invoices.get_invoice(iid2)["status"] == "paid" and notes


# --- report ----------------------------------------------------------------
def test_summary_buckets(monkeypatch):
    today = date(2026, 11, 16)
    monkeypatch.setattr(report, "today_local", lambda: today)
    e = add_email()
    for n, days, amt in [("A", -3, 100), ("B", 2, 200), ("C", 10, 300), ("D", 20, 400), ("E", 45, 500)]:
        invoices.upsert_extracted(e, None, inv(invoice_number=n, due_date=(today + timedelta(days=days)).isoformat(),
                                               amount_due=amt), 0)
    invoices.upsert_extracted(e, None, inv(invoice_number="USD1", currency="USD", amount_due=50,
                                           due_date=today.isoformat()), 0)
    sm = report.compute_summary(today)
    h = sm["headline"]
    assert (h["overdue"], h["within_7"], h["within_14"], h["within_30"], h["outstanding"]) == (100, 200, 500, 900, 1500)
    assert h["cash_7_incl_overdue"] == 300
    assert sm["other_currencies"]["USD"]["within_7"] == 50
    assert sm["chart"][0]["value"] == 100
    html = report.render_html(sm, None)
    assert "Due next 7 days" in html and "£200.00" in html


def test_excluded_supplier(monkeypatch):
    e = add_email()
    invoices.upsert_extracted(e, None, inv(supplier="HMRC", invoice_number="VAT1"), 0)
    pb = playbook.get_active()[1]
    pb.excluded_suppliers = ["hmrc"]
    v = playbook.save_candidate(pb, 1, "exclude", 1, 1, {})
    playbook.activate(v)
    assert report.compute_summary()["open_count"] == 0


# --- self-improvement harness -------------------------------------------------
def extraction(*invs, cls="invoice_to_pay"):
    return EmailExtraction(classification=cls, summary="x", invoices=list(invs), paid_invoice_numbers=[])


def test_score_case():
    exp = {"is_payable": True, "invoices": [{"supplier": "Acme Paints", "invoice_number": "INV-1001",
                                              "amount_due": 120.0, "due_date": "2026-12-01"}]}
    assert improve.score_case(exp, extraction(inv()))["passed"]
    bad = improve.score_case(exp, extraction(inv(amount_due=12.0)))
    assert not bad["passed"] and bad["score"] == 0.75
    neg = improve.score_case({"is_payable": False, "invoices": []}, extraction(inv()))
    assert neg["score"] == 0
    assert improve.score_case({"is_payable": False, "invoices": []}, extraction(cls="not_finance"))["passed"]


def _setup_cases():
    e1, e2 = add_email("a"), add_email("b", "2026-11-03T00:00:00+00:00")
    i1 = invoices.upsert_extracted(e1, None, inv(invoice_number="X1"), 0)
    i2 = invoices.upsert_extracted(e2, None, inv(invoice_number="X2"), 0)
    invoices.confirm_invoice(i1, source="web")
    invoices.update_invoice(i2, {"amount_due": "60"}, source="web", comment="deposit paid")
    return e1, e2


def test_improvement_cycle_accepts_fix_and_rejects_regression(monkeypatch):
    from app.models import Playbook, PlaybookProposal
    e1, e2 = _setup_cases()

    def fake_extract(email_id, pb):
        fixed = any("DEPOSITFIX" in r for r in pb.extraction_rules)
        broken = any("BREAK" in r for r in pb.extraction_rules)
        if email_id == e1:
            return extraction(inv(invoice_number="X1", amount_due=1.0 if broken else 120.0))
        return extraction(inv(invoice_number="X2", amount_due=60.0 if fixed else 120.0))

    monkeypatch.setattr(improve.extract, "extract_email", fake_extract)

    def proposer(rule):
        def _p(pb, fb, baseline):
            new = Playbook.model_validate(pb.model_dump())
            new.extraction_rules.append(rule)
            return PlaybookProposal(playbook=new, rationale=rule, feedback_ids_addressed=[f["id"] for f in fb])
        return _p

    monkeypatch.setattr(improve, "propose", proposer("DEPOSITFIX subtract deposit shown"))
    res = improve.run_improvement_cycle()
    assert res["status"] == "awaiting_approval" and res["candidate"] > res["baseline"]
    assert not improve.pending_feedback()

    improve.record_feedback(source="web", kind="general", comment="something")
    monkeypatch.setattr(improve, "propose", proposer("BREAK everything"))
    res2 = improve.run_improvement_cycle()
    assert res2["status"] == "rejected_by_eval" and res2["regressions"]

    monkeypatch.setattr(improve.pipeline, "process_email", lambda eid: {})
    improve.apply_version(res["version"])
    assert playbook.get_active()[0] == res["version"]


def test_mark_paid_by_numbers():
    e = add_email()
    a = invoices.upsert_extracted(e, None, inv(supplier="Metro Timber", invoice_number="2502-113161", amount_due=239.76), 0)
    b = invoices.upsert_extracted(e, None, inv(supplier="Energy & Environmental Alliance Ltd", invoice_number="INV-0262", amount_due=1200), 0)
    invoices.upsert_extracted(e, None, inv(supplier="Acme", invoice_number="DUP-1"), 0)
    invoices.upsert_extracted(e, None, inv(supplier="Other Co", invoice_number="DUP-1"), 0)
    res = invoices.mark_paid(numbers=["2502-113161", "inv 0262", "NOPE-9", "DUP-1"], suppliers=[], ids=[],
                             paid_date="2026-11-10", source="web", author="t", comment=None)
    assert {m["id"] for m in res["marked_paid"]} == {a, b}
    assert res["total_marked"] == {"GBP": 1439.76}
    assert res["not_found"] == ["NOPE-9"] and res["ambiguous"][0]["invoice_number"] == "DUP-1"
    assert invoices.get_invoice(a)["status"] == "paid" and invoices.get_invoice(a)["paid_at"] == "2026-11-10"
    again = invoices.mark_paid(numbers=["2502-113161"], suppliers=[], ids=[], paid_date=None, source="web",
                               author="t", comment=None)
    assert again["already_paid"] and not again["marked_paid"]
    # supplier disambiguates duplicates
    res2 = invoices.mark_paid(numbers=["DUP-1"], suppliers=["Other Co Ltd"], ids=[], paid_date=None, source="web",
                              author="t", comment=None)
    assert [m["supplier"] for m in res2["marked_paid"]] == ["Other Co"]
