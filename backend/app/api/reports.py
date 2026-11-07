import csv
import io
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import Select

from ..auth import DB, CurrentUser
from ..models import Claim, ClaimStatus, User, as_utc, utcnow
from ..schemas import ClaimSummary, PendingRow
from ..serializers import claim_summary
from .common import claims_query

router = APIRouter(prefix="/api/reports", tags=["reports"])

WAITING_WITH = {
    ClaimStatus.SUBMITTED: "Manager",
    ClaimStatus.MANAGER_APPROVED: "Accounts (verify)",
    ClaimStatus.VERIFIED: "Accounts (add to payout)",
    ClaimStatus.IN_PAYOUT_BATCH: "Accounts (pay)",
}


def require_finance(user: CurrentUser) -> User:
    if not (user.is_admin or user.can_verify or user.can_pay):
        raise HTTPException(403, "Accounts or admin access required")
    return user


FinanceUser = Annotated[User, Depends(require_finance)]


def _register_query(
    month: str | None, status: ClaimStatus | None, department: str | None, employee_id: int | None
) -> Select[tuple[Claim]]:
    stmt = claims_query().join(Claim.employee).where(Claim.status != ClaimStatus.DRAFT)
    if month:
        stmt = stmt.where(Claim.period == month)
    if status:
        stmt = stmt.where(Claim.status == status)
    if department:
        stmt = stmt.where(User.department == department)
    if employee_id:
        stmt = stmt.where(Claim.employee_id == employee_id)
    return stmt.order_by(Claim.period.desc(), User.name)


@router.get("/register", response_model=list[ClaimSummary])
def register(
    user: FinanceUser,
    db: DB,
    month: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}$")] = None,
    status: ClaimStatus | None = None,
    department: str | None = None,
    employee_id: int | None = None,
):
    return [claim_summary(c) for c in db.scalars(_register_query(month, status, department, employee_id))]


@router.get("/register/export")
def register_export(
    user: FinanceUser,
    db: DB,
    month: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}$")] = None,
    status: ClaimStatus | None = None,
    department: str | None = None,
    employee_id: int | None = None,
):
    """One row per expense line, for Accounts' own analysis in Excel."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([
        "Claim ID", "Month", "Claim status", "Employee code", "Employee", "Department",
        "Expense date", "Category", "Description", "Payment mode", "Claimed (INR)",
        "Approved (INR)", "Line status", "Adjust reason", "No-bill declaration", "GSTIN",
        "Tax (INR)", "Bills", "Payment reference",
    ])
    for c in db.scalars(_register_query(month, status, department, employee_id)):
        e = c.employee
        for line in c.lines:
            w.writerow([
                c.id, c.period, c.status.value, e.employee_code or "", e.name, e.department or "",
                line.expense_date.isoformat(), line.category.name, line.description,
                line.payment_mode.value, f"{line.amount:.2f}",
                "" if line.approved_amount is None else f"{line.approved_amount:.2f}",
                line.status.value, line.adjust_reason or "", "yes" if line.no_bill_declaration else "",
                line.gstin or "", "" if line.tax_amount is None else f"{line.tax_amount:.2f}",
                len(line.attachments), c.payment_reference or "",
            ])
    name = f"claims-register-{month or 'all'}.csv"
    return Response(
        ("﻿" + buf.getvalue()).encode("utf-8"), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@router.get("/pending", response_model=list[PendingRow])
def pending(user: FinanceUser, db: DB):
    now = utcnow()
    rows = db.scalars(
        claims_query().where(Claim.status.in_(list(WAITING_WITH))).order_by(Claim.status_changed_at)
    )
    out = []
    for c in rows:
        waiting = WAITING_WITH[c.status]
        if c.status == ClaimStatus.SUBMITTED and c.approver:
            waiting = f"Manager ({c.approver.name})"
        out.append(PendingRow(
            claim=claim_summary(c),
            stage=c.status,
            waiting_with=waiting,
            days_waiting=(now - as_utc(c.status_changed_at)).days,
        ))
    return out
