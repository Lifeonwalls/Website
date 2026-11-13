"""Pydantic schemas shared by extraction, the playbook and the optimizer."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

Classification = Literal[
    "invoice_to_pay",       # a bill we owe
    "payment_reminder",     # chaser / overdue notice for invoices we owe
    "statement",            # supplier statement listing open items
    "credit_note",
    "receipt_already_paid", # card payment / direct debit already taken
    "remittance_or_payment_confirmation",  # confirms WE paid something
    "sales_invoice_issued_by_us",           # our own invoice to a customer (receivable, not payable)
    "quote_or_proforma",
    "not_finance",
]


class ExtractedInvoice(BaseModel):
    doc_type: Literal["invoice", "credit_note"]
    supplier: str = Field(description="Legal/trading name of the company that issued the invoice")
    supplier_email: Optional[str]
    invoice_number: str = Field(description="Exactly as printed. Use 'UNKNOWN' if truly absent.")
    invoice_date: Optional[str] = Field(description="YYYY-MM-DD")
    due_date: Optional[str] = Field(description="YYYY-MM-DD, only if stated or directly derivable from stated terms")
    payment_terms: Optional[str] = Field(description="Terms as written, e.g. '30 days from invoice date'")
    payment_terms_days: Optional[int]
    currency: str = Field(description="ISO 4217 code, e.g. GBP")
    net_amount: Optional[float]
    vat_amount: Optional[float]
    total_amount: Optional[float]
    amount_due: float = Field(description="Balance still payable on this invoice (positive number; credit notes positive too)")
    already_paid: bool = Field(description="True if the document says it was paid (card, direct debit, 'PAID' stamp)")
    payment_reference: Optional[str]
    bank_details: Optional[str] = Field(description="Sort code / account / IBAN as printed")
    po_number: Optional[str]
    description: Optional[str] = Field(description="One line: what the invoice is for")
    category: Optional[str] = Field(description="Spend category, e.g. Materials, Subcontractors, Software, Utilities, Rent, Professional fees")
    source: str = Field(description="Attachment filename or 'email body'")
    confidence: float = Field(description="0.0-1.0 overall confidence in the extracted values")
    uncertainties: list[str] = Field(description="Anything ambiguous a human should check")


class EmailExtraction(BaseModel):
    classification: Classification
    summary: str = Field(description="One sentence describing the email")
    invoices: list[ExtractedInvoice] = Field(description="Every payable invoice / credit note found; empty if none")
    paid_invoice_numbers: list[str] = Field(
        description="Invoice numbers this email confirms have been PAID by us (remittances, payment confirmations)"
    )


# ---------------------------------------------------------------------------
# Playbook: the learned, versioned instructions the self-improvement loop edits.
# ---------------------------------------------------------------------------
class SupplierRule(BaseModel):
    supplier_match: str = Field(description="Case-insensitive substring of the supplier name or sender email")
    rule: str


class Playbook(BaseModel):
    extraction_rules: list[str]
    supplier_rules: list[SupplierRule]
    report_preferences: list[str] = Field(description="How the board wants the report written/structured")
    excluded_suppliers: list[str] = Field(description="Suppliers (substring match) to leave out of payables reports")


class PlaybookProposal(BaseModel):
    playbook: Playbook
    rationale: str = Field(description="What changed and which feedback each change addresses")
    feedback_ids_addressed: list[int]


DEFAULT_PLAYBOOK = Playbook(
    extraction_rules=[
        "Only invoices that the company must PAY are payables. Invoices issued BY the company to its own customers are 'sales_invoice_issued_by_us' and must not be listed.",
        "If a PDF and the email body describe the same invoice, report it once, using the PDF values.",
        "amount_due is the outstanding balance; if a part-payment or deposit is shown, subtract it.",
        "Do not invent a due date. If only terms are given (e.g. '30 days'), fill payment_terms_days and leave due_date empty unless the date is printed.",
        "Payment reminders and statements: extract each open invoice listed with its own number, date and balance.",
        "Direct debits and card payments that have already been collected are already_paid=true.",
        "Dates in UK documents are day-first (03/04/2026 = 3 April 2026).",
    ],
    supplier_rules=[],
    report_preferences=[
        "Lead with the cash required in the next 7 days, then 14 and 30.",
        "Call out overdue invoices and anything needing review before payment.",
        "Keep commentary to 3-5 short bullet points; plain British English; no jargon.",
    ],
    excluded_suppliers=[],
)
