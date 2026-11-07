"""Claim lifecycle: who may do what, in which status (spec section 4).

Draft -> Submitted -> ManagerApproved -> Verified -> InPayoutBatch -> Paid
Submitted / ManagerApproved -> Returned (employee fixes and resubmits) or Rejected (final)
"""

import hashlib
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import (
    Attachment,
    Category,
    Claim,
    ClaimEvent,
    ClaimLine,
    ClaimStatus,
    LineStatus,
    PaymentMode,
    User,
    utcnow,
)
from ..schemas import LineDecision, LineIn, ReviewIn
from . import notify, storage
from .errors import Conflict, Forbidden, Invalid, NotFound
from .policy import compute_warnings, duplicate_claim_ids

EDITABLE = {ClaimStatus.DRAFT, ClaimStatus.RETURNED}
PAYOUT_VISIBLE = {ClaimStatus.VERIFIED, ClaimStatus.IN_PAYOUT_BATCH, ClaimStatus.PAID}

STATUS_LABEL = {
    ClaimStatus.DRAFT: "Draft",
    ClaimStatus.SUBMITTED: "Submitted",
    ClaimStatus.RETURNED: "Returned to you",
    ClaimStatus.MANAGER_APPROVED: "Approved by manager",
    ClaimStatus.VERIFIED: "Verified by Accounts",
    ClaimStatus.IN_PAYOUT_BATCH: "In payout batch",
    ClaimStatus.PAID: "Paid",
    ClaimStatus.REJECTED: "Rejected",
}

ALLOWED_TYPES = {
    "application/pdf": (".pdf", b"%PDF"),
    "image/jpeg": (".jpg", b"\xff\xd8\xff"),
    "image/png": (".png", b"\x89PNG\r\n\x1a\n"),
}


# ---- visibility & permissions ---------------------------------------------


def can_view(user: User, claim: Claim) -> bool:
    if user.is_admin or claim.employee_id == user.id or claim.approver_id == user.id:
        return True
    if claim.status == ClaimStatus.DRAFT:
        return False
    if claim.employee.manager_id == user.id or user.can_verify:
        return True
    return user.can_pay and claim.status in PAYOUT_VISIBLE


def _is_manager_reviewer(user: User, claim: Claim) -> bool:
    return claim.approver_id == user.id and claim.employee_id != user.id


def _is_accounts_reviewer(user: User, claim: Claim) -> bool:
    # Nobody verifies their own claim (BR-8).
    return user.can_verify and claim.employee_id != user.id


def allowed_actions(user: User, claim: Claim) -> list[str]:
    actions: list[str] = []
    owner = claim.employee_id == user.id
    if owner and claim.status in EDITABLE:
        actions += ["edit", "submit"]
    if owner and claim.status == ClaimStatus.SUBMITTED:
        actions.append("withdraw")
    if claim.status == ClaimStatus.SUBMITTED and _is_manager_reviewer(user, claim):
        actions += ["approve", "return", "reject"]
    if claim.status == ClaimStatus.MANAGER_APPROVED and _is_accounts_reviewer(user, claim):
        actions += ["verify", "return", "reject"]
    if can_view(user, claim):
        actions.append("comment")
    return actions


def get_claim(db: Session, user: User, claim_id: int) -> Claim:
    claim = db.get(Claim, claim_id)
    # Same answer for "missing" and "not yours" so ids can't be probed.
    if claim is None or not can_view(user, claim):
        raise NotFound("Claim not found")
    return claim


def _require_owner_editable(user: User, claim: Claim) -> None:
    if claim.employee_id != user.id:
        raise Forbidden("Only the employee who owns this claim can change it")
    if claim.status not in EDITABLE:
        raise Conflict(f"A claim that is '{STATUS_LABEL[claim.status]}' can't be edited")


# ---- audit ---------------------------------------------------------------


def record(
    db: Session,
    claim: Claim,
    actor: User,
    action: str,
    *,
    from_status: ClaimStatus | None = None,
    to_status: ClaimStatus | None = None,
    comment: str | None = None,
    details: dict | None = None,
) -> ClaimEvent:
    ev = ClaimEvent(
        claim_id=claim.id,
        actor_id=actor.id,
        action=action,
        from_status=from_status.value if from_status else None,
        to_status=to_status.value if to_status else None,
        comment=comment,
        details=details,
    )
    db.add(ev)
    claim.events.append(ev)
    return ev


def _move(
    db: Session,
    claim: Claim,
    actor: User,
    new: ClaimStatus,
    action: str,
    comment: str | None = None,
    details: dict | None = None,
) -> None:
    old = claim.status
    claim.status = new
    claim.status_changed_at = utcnow()
    record(db, claim, actor, action, from_status=old, to_status=new, comment=comment, details=details)


def _tell_employee(db: Session, claim: Claim, actor: User, comment: str | None = None) -> None:
    body = (
        f"Your reimbursement claim for {claim.period} is now: {STATUS_LABEL[claim.status]}"
        f" (by {actor.name}).\n"
    )
    if comment:
        body += f"\nComment: {comment}\n"
    body += f"\n{notify.claim_link(claim.id)}\n"
    notify.queue(db, claim.employee, f"Claim {claim.period}: {STATUS_LABEL[claim.status]}", body)


# ---- employee actions ----------------------------------------------------


def get_or_create_claim(db: Session, user: User, period: str) -> tuple[Claim, bool]:
    today = date.today()
    if period > f"{today:%Y-%m}":
        raise Invalid("You can't open a claim for a future month")
    existing = db.scalar(select(Claim).where(Claim.employee_id == user.id, Claim.period == period))
    if existing:
        return existing, False
    claim = Claim(employee_id=user.id, period=period, status=ClaimStatus.DRAFT)
    claim.employee = user
    db.add(claim)
    db.flush()
    record(db, claim, user, "created", to_status=ClaimStatus.DRAFT)
    return claim, True


def _check_line(db: Session, data: LineIn) -> Category:
    cat = db.get(Category, data.category_id)
    if cat is None or not cat.is_active:
        raise Invalid("Unknown or inactive category")
    if data.expense_date > date.today():
        raise Invalid("Expense date can't be in the future")
    if data.tax_amount is not None and data.tax_amount > data.amount:
        raise Invalid("Tax amount can't exceed the line amount")
    return cat


def add_line(db: Session, user: User, claim: Claim, data: LineIn) -> ClaimLine:
    _require_owner_editable(user, claim)
    cat = _check_line(db, data)
    line = ClaimLine(**data.model_dump(), status=LineStatus.PENDING)
    line.category = cat
    claim.lines.append(line)
    db.flush()
    return line


def _get_line(claim: Claim, line_id: int) -> ClaimLine:
    for line in claim.lines:
        if line.id == line_id:
            return line
    raise NotFound("Line not found on this claim")


def update_line(db: Session, user: User, claim: Claim, line_id: int, data: LineIn) -> ClaimLine:
    _require_owner_editable(user, claim)
    line = _get_line(claim, line_id)
    cat = _check_line(db, data)
    for key, value in data.model_dump().items():
        setattr(line, key, value)
    line.category = cat
    db.flush()
    return line


def delete_line(db: Session, user: User, claim: Claim, line_id: int) -> None:
    _require_owner_editable(user, claim)
    line = _get_line(claim, line_id)
    keys = [a.storage_key for a in line.attachments]
    claim.lines.remove(line)
    db.flush()
    for key in keys:
        storage.delete(key)


def add_attachment(
    db: Session,
    user: User,
    claim: Claim,
    line_id: int,
    filename: str,
    content_type: str,
    data: bytes,
) -> tuple[Attachment, list[int]]:
    _require_owner_editable(user, claim)
    line = _get_line(claim, line_id)
    if content_type not in ALLOWED_TYPES:
        raise Invalid("Bills must be PDF, JPG or PNG")
    suffix, magic = ALLOWED_TYPES[content_type]
    # Check the bytes too: the browser-supplied type is easy to fake.
    if not data.startswith(magic):
        raise Invalid("The file's contents don't match its type")
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise Invalid(f"Bills must be {settings.max_upload_mb} MB or smaller")
    if not data:
        raise Invalid("The file is empty")

    sha = hashlib.sha256(data).hexdigest()
    # Looked up before this file is added, so it only finds earlier copies (including on this claim).
    dupes = duplicate_claim_ids(db, sha)
    key = storage.save(data, suffix)
    att = Attachment(
        original_name=Path(filename or "bill").name[:255],
        content_type=content_type,
        size_bytes=len(data),
        sha256=sha,
        storage_key=key,
        uploaded_by_id=user.id,
    )
    line.attachments.append(att)
    db.flush()
    return att, dupes


def delete_attachment(db: Session, user: User, claim: Claim, attachment_id: int) -> None:
    _require_owner_editable(user, claim)
    for line in claim.lines:
        for att in line.attachments:
            if att.id == attachment_id:
                key = att.storage_key
                line.attachments.remove(att)
                db.flush()
                storage.delete(key)
                return
    raise NotFound("Attachment not found on this claim")


def find_attachment(claim: Claim, attachment_id: int) -> Attachment:
    for line in claim.lines:
        for att in line.attachments:
            if att.id == attachment_id:
                return att
    raise NotFound("Attachment not found on this claim")


def resolve_approver(db: Session, employee: User) -> User:
    """The employee's manager; people without one (founders, CXOs) go to a fallback approver."""
    mgr = employee.manager
    if mgr is not None and mgr.is_active and mgr.id != employee.id:
        return mgr
    fallback = db.scalar(
        select(User)
        .where(User.is_fallback_approver, User.is_active, User.id != employee.id)
        .order_by(User.id)
    )
    if fallback is None:
        raise Conflict("No approver is set up for you. Ask an admin to set your manager.")
    return fallback


def submit(db: Session, user: User, claim: Claim) -> None:
    _require_owner_editable(user, claim)
    if not claim.lines:
        raise Invalid("Add at least one expense before submitting")
    for line in claim.lines:
        label = f"{line.expense_date:%d %b} {line.category.name}"
        # BR-5: online payments always need a bill; cash needs a bill or a self-declaration.
        if line.payment_mode == PaymentMode.ONLINE and not line.attachments:
            raise Invalid(f"{label}: online payments need a bill attached")
        if line.payment_mode == PaymentMode.CASH and not line.attachments and not line.no_bill_declaration:
            raise Invalid(f"{label}: attach a bill or tick the no-bill declaration")

    approver = resolve_approver(db, claim.employee)
    for line in claim.lines:
        line.status = LineStatus.PENDING
        line.approved_amount = None
        line.adjust_reason = None
    claim.approver_id = approver.id
    claim.approver = approver
    claim.submitted_at = utcnow()
    warnings = compute_warnings(db, claim)
    _move(
        db, claim, user, ClaimStatus.SUBMITTED, "submitted",
        details={"total_claimed": str(claim.total_claimed), "warnings": [w.message for w in warnings]},
    )
    notify.queue(
        db, approver,
        f"Claim to approve: {claim.employee.name}, {claim.period}",
        f"{claim.employee.name} submitted a claim for {claim.period} totalling ₹{claim.total_claimed:,.2f}.\n\n"
        f"{notify.claim_link(claim.id)}\n",
    )


def withdraw(db: Session, user: User, claim: Claim) -> None:
    if claim.employee_id != user.id:
        raise Forbidden("Only the employee who owns this claim can withdraw it")
    if claim.status != ClaimStatus.SUBMITTED:
        raise Conflict("Only a claim waiting for the manager can be withdrawn")
    _move(db, claim, user, ClaimStatus.DRAFT, "withdrawn")


def add_comment(db: Session, user: User, claim: Claim, comment: str) -> ClaimEvent:
    ev = record(db, claim, user, "comment", comment=comment)
    if user.id != claim.employee_id:
        notify.queue(
            db, claim.employee, f"New comment on your {claim.period} claim",
            f"{user.name}: {comment}\n\n{notify.claim_link(claim.id)}\n",
        )
    elif claim.status == ClaimStatus.SUBMITTED:
        notify.queue(
            db, claim.approver, f"{user.name} commented on their {claim.period} claim",
            f"{comment}\n\n{notify.claim_link(claim.id)}\n",
        )
    return ev


# ---- reviewer actions ----------------------------------------------------


def _line_state(line: ClaimLine) -> dict:
    return {
        "status": line.status.value,
        "approved_amount": None if line.approved_amount is None else str(line.approved_amount),
    }


def _apply_decisions(claim: Claim, decisions: list[LineDecision], *, allow_unreject: bool) -> list[dict]:
    """Applies per-line decisions and returns before/after records for the audit log (BR-6)."""
    by_id = {line.id: line for line in claim.lines}
    seen: set[int] = set()
    changes: list[dict] = []
    for d in decisions:
        line = by_id.get(d.line_id)
        if line is None:
            raise Invalid(f"Line {d.line_id} is not on this claim")
        if d.line_id in seen:
            raise Invalid(f"Line {d.line_id} has more than one decision")
        seen.add(d.line_id)
        before = _line_state(line)

        if d.decision == "reject":
            if not d.reason:
                raise Invalid("Give a reason for rejecting a line")
            line.status = LineStatus.REJECTED
            line.approved_amount = None
            line.adjust_reason = d.reason
        else:
            if line.status == LineStatus.REJECTED and not allow_unreject:
                raise Conflict("A line the manager rejected can't be re-approved by Accounts")
            current = line.approved_amount if line.approved_amount is not None else line.amount
            amount = d.approved_amount if d.approved_amount is not None else current
            if amount > line.amount:
                raise Invalid("The approved amount can't be more than the amount claimed")
            if amount != line.amount and not d.reason:
                raise Invalid("Give a reason when changing the approved amount")
            line.status = LineStatus.APPROVED
            line.approved_amount = amount
            line.adjust_reason = d.reason if amount != line.amount else None

        after = _line_state(line)
        if after != before:
            changes.append({
                "line_id": line.id,
                "claimed": str(line.amount),
                "before": before,
                "after": after,
                "reason": line.adjust_reason,
            })
    if all(line.status == LineStatus.REJECTED for line in claim.lines):
        raise Invalid("Every line is rejected; reject the whole claim instead")
    return changes


def manager_approve(db: Session, user: User, claim: Claim, review: ReviewIn) -> None:
    if claim.status != ClaimStatus.SUBMITTED:
        raise Conflict("This claim isn't waiting for manager approval")
    if not _is_manager_reviewer(user, claim):
        raise Forbidden("Only the assigned approver can approve this claim")
    # Default: everything approved in full; decisions below override per line.
    for line in claim.lines:
        line.status = LineStatus.APPROVED
        line.approved_amount = line.amount
        line.adjust_reason = None
    changes = _apply_decisions(claim, review.lines, allow_unreject=True)
    claim.manager_approved_at = utcnow()
    claim.manager_approved_by_id = user.id
    _move(
        db, claim, user, ClaimStatus.MANAGER_APPROVED, "manager_approved", review.comment,
        details={"changes": changes, "total_approved": str(claim.total_approved)},
    )
    _tell_employee(db, claim, user, review.comment)


def verify(db: Session, user: User, claim: Claim, review: ReviewIn) -> None:
    if claim.status != ClaimStatus.MANAGER_APPROVED:
        raise Conflict("This claim isn't waiting for Accounts verification")
    if not _is_accounts_reviewer(user, claim):
        raise Forbidden("You can't verify this claim")
    changes = _apply_decisions(claim, review.lines, allow_unreject=False)
    claim.verified_at = utcnow()
    claim.verified_by_id = user.id
    _move(
        db, claim, user, ClaimStatus.VERIFIED, "verified", review.comment,
        details={"changes": changes, "total_approved": str(claim.total_approved)},
    )
    _tell_employee(db, claim, user, review.comment)


def _require_reviewer(user: User, claim: Claim) -> None:
    if claim.status == ClaimStatus.SUBMITTED:
        if not _is_manager_reviewer(user, claim):
            raise Forbidden("Only the assigned approver can act on this claim now")
    elif claim.status == ClaimStatus.MANAGER_APPROVED:
        if not _is_accounts_reviewer(user, claim):
            raise Forbidden("Only Accounts can act on this claim now")
    else:
        raise Conflict(f"A claim that is '{STATUS_LABEL[claim.status]}' can't be returned or rejected")


def return_claim(db: Session, user: User, claim: Claim, comment: str) -> None:
    _require_reviewer(user, claim)
    _move(db, claim, user, ClaimStatus.RETURNED, "returned", comment)
    _tell_employee(db, claim, user, comment)


def reject_claim(db: Session, user: User, claim: Claim, comment: str) -> None:
    _require_reviewer(user, claim)
    _move(db, claim, user, ClaimStatus.REJECTED, "rejected", comment)
    _tell_employee(db, claim, user, comment)
