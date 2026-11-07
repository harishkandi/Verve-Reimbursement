"""Policy checks. In v1 every rule here only warns; nothing blocks submission (spec BR-1..BR-5)."""

from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    ZERO,
    Attachment,
    Claim,
    ClaimLine,
    ClaimStatus,
    PaymentMode,
    Policy,
    as_utc,
    utcnow,
)
from ..schemas import PolicyWarning


def get_policy(db: Session) -> Policy:
    policy = db.get(Policy, 1)
    if policy is None:
        policy = Policy(id=1)
        db.add(policy)
        db.flush()
    return policy


def _rupees(value: Decimal) -> str:
    return f"₹{value:,.2f}"


def due_date(period: str, due_day: int) -> date:
    year, month = (int(p) for p in period.split("-"))
    year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return date(year, month, due_day)


def duplicate_claim_ids(db: Session, sha256: str, exclude_line_id: int | None = None) -> list[int]:
    """Other live claims carrying a file with the same content."""
    stmt = (
        select(Claim.id)
        .join(ClaimLine, ClaimLine.claim_id == Claim.id)
        .join(Attachment, Attachment.line_id == ClaimLine.id)
        .where(Attachment.sha256 == sha256, Claim.status != ClaimStatus.REJECTED)
    )
    if exclude_line_id is not None:
        stmt = stmt.where(ClaimLine.id != exclude_line_id)
    return sorted(set(db.scalars(stmt)))


def compute_warnings(db: Session, claim: Claim) -> list[PolicyWarning]:
    policy = get_policy(db)
    warnings: list[PolicyWarning] = []
    reference_day = (as_utc(claim.submitted_at) or utcnow()).date()

    year, month = (int(p) for p in claim.period.split("-"))
    per_category: dict[int, Decimal] = defaultdict(lambda: ZERO)
    no_bill_total = ZERO

    for line in claim.lines:
        cat = line.category
        per_category[cat.id] += line.amount
        label = f"{line.expense_date:%d %b} {cat.name}"

        if cat.per_item_limit is not None and line.amount > cat.per_item_limit:
            warnings.append(PolicyWarning(
                code="over_item_limit", line_id=line.id,
                message=f"{label}: {_rupees(line.amount)} is over the {cat.name} limit of {_rupees(cat.per_item_limit)}",
            ))
        if (reference_day - line.expense_date).days > policy.max_age_days:
            warnings.append(PolicyWarning(
                code="too_old", line_id=line.id,
                message=f"{label}: older than {policy.max_age_days} days; needs Finance approval",
            ))
        if (line.expense_date.year, line.expense_date.month) != (year, month):
            warnings.append(PolicyWarning(
                code="outside_period", line_id=line.id,
                message=f"{label}: expense date is outside {claim.period}",
            ))
        if line.payment_mode == PaymentMode.CASH and not line.attachments and line.no_bill_declaration:
            no_bill_total += line.amount
            limit = policy.cash_no_bill_item_limit
            if limit is not None and line.amount > limit:
                warnings.append(PolicyWarning(
                    code="no_bill_over_limit", line_id=line.id,
                    message=f"{label}: cash without a bill above {_rupees(limit)}",
                ))
        for att in line.attachments:
            dupes = [cid for cid in duplicate_claim_ids(db, att.sha256, line.id)]
            if dupes:
                warnings.append(PolicyWarning(
                    code="duplicate_bill", line_id=line.id,
                    message=f"{label}: bill '{att.original_name}' also appears on claim(s) {', '.join(f'#{c}' for c in dupes)}",
                ))

    cats = {line.category.id: line.category for line in claim.lines}
    for cat_id, total in per_category.items():
        cat = cats[cat_id]
        if cat.monthly_limit is not None and total > cat.monthly_limit:
            warnings.append(PolicyWarning(
                code="over_monthly_limit",
                message=f"{cat.name}: {_rupees(total)} this month is over the monthly limit of {_rupees(cat.monthly_limit)}",
            ))

    month_limit = policy.cash_no_bill_month_limit
    if month_limit is not None and no_bill_total > month_limit:
        warnings.append(PolicyWarning(
            code="no_bill_month_over_limit",
            message=f"Cash without bills totals {_rupees(no_bill_total)}, over the monthly limit of {_rupees(month_limit)}",
        ))

    due = due_date(claim.period, policy.submission_due_day)
    if reference_day > due:
        warnings.append(PolicyWarning(
            code="late_submission",
            message=f"Submitted after the {due:%d %b %Y} deadline for {claim.period}",
        ))
    return warnings
