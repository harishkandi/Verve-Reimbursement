"""Payout batches: Accounts groups verified claims, pays them outside the tool, then records the payment."""

import csv
import io
from datetime import date

from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import BatchStatus, Claim, ClaimStatus, PayoutBatch, User, utcnow
from .claims import _move, _tell_employee
from .errors import Conflict, Invalid, NotFound

EXPORT_HEADERS = [
    "Claim ID", "Employee code", "Employee", "Email", "Department", "Month",
    "Amount (INR)", "Account name", "Account number", "IFSC", "Payout date",
]


def get_batch(db: Session, batch_id: int) -> PayoutBatch:
    batch = db.get(PayoutBatch, batch_id)
    if batch is None:
        raise NotFound("Payout batch not found")
    return batch


def create_batch(db: Session, user: User, payout_date: date, claim_ids: list[int]) -> PayoutBatch:
    claims = list(db.scalars(select(Claim).where(Claim.id.in_(set(claim_ids)))))
    if len(claims) != len(set(claim_ids)):
        raise Invalid("Some claims were not found")
    not_ready = [c.id for c in claims if c.status != ClaimStatus.VERIFIED]
    if not_ready:
        raise Conflict(f"Only verified claims can be batched; not ready: {not_ready}")
    batch = PayoutBatch(payout_date=payout_date, created_by_id=user.id, status=BatchStatus.OPEN)
    batch.created_by = user
    db.add(batch)
    db.flush()
    for claim in claims:
        claim.payout_batch = batch
        _move(db, claim, user, ClaimStatus.IN_PAYOUT_BATCH, "added_to_batch",
              details={"batch_id": batch.id, "payout_date": payout_date.isoformat()})
    return batch


def remove_claim(db: Session, user: User, batch: PayoutBatch, claim_id: int) -> None:
    if batch.status != BatchStatus.OPEN:
        raise Conflict("A paid batch can't be changed")
    claim = next((c for c in batch.claims if c.id == claim_id), None)
    if claim is None:
        raise NotFound("That claim isn't in this batch")
    claim.payout_batch = None
    _move(db, claim, user, ClaimStatus.VERIFIED, "removed_from_batch", details={"batch_id": batch.id})


def mark_paid(
    db: Session,
    user: User,
    batch: PayoutBatch,
    paid_on: date,
    reference: str,
    claim_references: dict[int, str],
) -> None:
    if batch.status != BatchStatus.OPEN:
        raise Conflict("This batch is already paid")
    if not batch.claims:
        raise Conflict("This batch has no claims")
    unknown = set(claim_references) - {c.id for c in batch.claims}
    if unknown:
        raise Invalid(f"Claims not in this batch: {sorted(unknown)}")
    now = utcnow()
    for claim in batch.claims:
        ref = (claim_references.get(claim.id) or reference).strip()[:100]
        claim.paid_at = now
        claim.payment_reference = ref
        _move(db, claim, user, ClaimStatus.PAID, "paid",
              details={"batch_id": batch.id, "paid_on": paid_on.isoformat(), "reference": ref})
        _tell_employee(db, claim, user, f"₹{claim.total_approved:,.2f} paid on {paid_on:%d %b %Y}, reference {ref}")
    batch.status = BatchStatus.PAID
    batch.paid_on = paid_on
    batch.reference = reference


def _rows(batch: PayoutBatch) -> list[list]:
    rows = []
    for c in batch.claims:
        e = c.employee
        rows.append([
            c.id, e.employee_code or "", e.name, e.email, e.department or "", c.period,
            f"{c.total_approved:.2f}", e.bank_account_name or "", e.bank_account_number or "",
            e.bank_ifsc or "", batch.payout_date.isoformat(),
        ])
    return rows


def export_csv(batch: PayoutBatch) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(EXPORT_HEADERS)
    writer.writerows(_rows(batch))
    # BOM so Excel opens the ₹ and names correctly.
    return ("﻿" + buf.getvalue()).encode("utf-8")


def export_xlsx(batch: PayoutBatch) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = f"Payout {batch.payout_date.isoformat()}"
    ws.append(EXPORT_HEADERS)
    for row in _rows(batch):
        row[6] = float(row[6])
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
