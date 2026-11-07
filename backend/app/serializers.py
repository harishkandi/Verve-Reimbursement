"""ORM -> response models. Kept in one place so every endpoint shapes claims the same way."""

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from .models import ZERO, Claim, ClaimLine, PayoutBatch, User
from .schemas import (
    AttachmentOut,
    BatchDetail,
    BatchSummary,
    ClaimDetail,
    ClaimSummary,
    EventOut,
    LineOut,
    MeOut,
    UserBrief,
    UserOut,
)
from .services.claims import allowed_actions
from .services.policy import compute_warnings


def brief(user: User | None) -> UserBrief | None:
    return None if user is None else UserBrief.model_validate(user)


def me_out(db: Session, user: User) -> MeOut:
    has_reports = db.scalar(select(exists().where(User.manager_id == user.id, User.is_active)))
    return MeOut(
        **UserOut.model_validate(user).model_dump(),
        is_approver=bool(has_reports) or user.is_fallback_approver,
        manager=brief(user.manager),
    )


def claim_summary(claim: Claim, db: Session | None = None) -> ClaimSummary:
    """Pass `db` to include the policy-warning count (costs a few queries per claim)."""
    return ClaimSummary(
        warning_count=len(compute_warnings(db, claim)) if db is not None and claim.lines else None,
        id=claim.id,
        period=claim.period,
        status=claim.status,
        employee=brief(claim.employee),
        employee_department=claim.employee.department,
        approver=brief(claim.approver),
        total_claimed=claim.total_claimed,
        total_approved=claim.total_approved,
        line_count=len(claim.lines),
        submitted_at=claim.submitted_at,
        status_changed_at=claim.status_changed_at,
        payout_batch_id=claim.payout_batch_id,
        payment_reference=claim.payment_reference,
        paid_at=claim.paid_at,
    )


def line_out(line: ClaimLine) -> LineOut:
    return LineOut(
        id=line.id,
        expense_date=line.expense_date,
        category_id=line.category_id,
        category_name=line.category.name,
        description=line.description,
        payment_mode=line.payment_mode,
        amount=line.amount,
        approved_amount=line.approved_amount,
        status=line.status,
        adjust_reason=line.adjust_reason,
        no_bill_declaration=line.no_bill_declaration,
        gstin=line.gstin,
        tax_amount=line.tax_amount,
        attachments=[AttachmentOut.model_validate(a) for a in line.attachments],
    )


def claim_detail(db: Session, claim: Claim, viewer: User) -> ClaimDetail:
    return ClaimDetail(
        **claim_summary(claim).model_dump(),
        lines=[line_out(line) for line in claim.lines],
        events=[
            EventOut(
                id=e.id, action=e.action, from_status=e.from_status, to_status=e.to_status,
                comment=e.comment, details=e.details, created_at=e.created_at, actor=brief(e.actor),
            )
            for e in claim.events
        ],
        warnings=compute_warnings(db, claim) if claim.lines else [],
        allowed_actions=allowed_actions(viewer, claim),
    )


def batch_summary(batch: PayoutBatch) -> BatchSummary:
    return BatchSummary(
        id=batch.id,
        payout_date=batch.payout_date,
        status=batch.status,
        created_by=brief(batch.created_by),
        created_at=batch.created_at,
        paid_on=batch.paid_on,
        reference=batch.reference,
        claim_count=len(batch.claims),
        total=sum((c.total_approved for c in batch.claims), ZERO),
    )


def batch_detail(batch: PayoutBatch) -> BatchDetail:
    return BatchDetail(
        **batch_summary(batch).model_dump(),
        claims=[claim_summary(c) for c in batch.claims],
    )
