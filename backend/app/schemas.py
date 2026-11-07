from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints

from .models import BatchStatus, ClaimStatus, LineStatus, PaymentMode

Money = Annotated[Decimal, Field(max_digits=12, decimal_places=2)]
PositiveMoney = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]
NonNegMoney = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]
Text500 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
Period = Annotated[str, StringConstraints(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---- users ---------------------------------------------------------------


class UserBrief(ORM):
    id: int
    name: str
    email: str


class UserOut(ORM):
    id: int
    email: str
    name: str
    employee_code: str | None
    department: str | None
    manager_id: int | None
    is_admin: bool
    can_verify: bool
    can_pay: bool
    is_fallback_approver: bool
    is_active: bool


class MeOut(UserOut):
    # Drives whether the UI shows the Approvals inbox.
    is_approver: bool
    # Shown before submission so employees know who will review their claim.
    manager: UserBrief | None = None


class UserAdminOut(UserOut):
    bank_account_name: str | None
    bank_account_number: str | None
    bank_ifsc: str | None


class UserIn(BaseModel):
    email: EmailStr
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    employee_code: str | None = None
    department: str | None = None
    manager_id: int | None = None
    is_admin: bool = False
    can_verify: bool = False
    can_pay: bool = False
    is_fallback_approver: bool = False
    is_active: bool = True
    bank_account_name: str | None = None
    bank_account_number: str | None = None
    bank_ifsc: Annotated[str | None, StringConstraints(max_length=11)] = None


class ImportResult(BaseModel):
    created: int
    updated: int
    errors: list[str]


# ---- settings ------------------------------------------------------------


class CategoryOut(ORM):
    id: int
    name: str
    is_active: bool
    per_item_limit: Money | None
    monthly_limit: Money | None
    sort_order: int


class CategoryIn(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    is_active: bool = True
    per_item_limit: NonNegMoney | None = None
    monthly_limit: NonNegMoney | None = None
    sort_order: int = 0


class PolicyOut(ORM):
    submission_due_day: int
    max_age_days: int
    cash_no_bill_item_limit: Money | None
    cash_no_bill_month_limit: Money | None


class PolicyIn(BaseModel):
    submission_due_day: Annotated[int, Field(ge=1, le=28)]
    max_age_days: Annotated[int, Field(ge=1, le=365)]
    cash_no_bill_item_limit: NonNegMoney | None = None
    cash_no_bill_month_limit: NonNegMoney | None = None


# ---- claims --------------------------------------------------------------


class ClaimCreate(BaseModel):
    period: Period


class LineIn(BaseModel):
    expense_date: date
    category_id: int
    description: Text500
    payment_mode: PaymentMode
    amount: PositiveMoney
    no_bill_declaration: bool = False
    gstin: Annotated[str | None, StringConstraints(strip_whitespace=True, max_length=15)] = None
    tax_amount: NonNegMoney | None = None


class AttachmentOut(ORM):
    id: int
    original_name: str
    content_type: str
    size_bytes: int
    created_at: datetime


class LineOut(BaseModel):
    id: int
    expense_date: date
    category_id: int
    category_name: str
    description: str
    payment_mode: PaymentMode
    amount: Money
    approved_amount: Money | None
    status: LineStatus
    adjust_reason: str | None
    no_bill_declaration: bool
    gstin: str | None
    tax_amount: Money | None
    attachments: list[AttachmentOut]


class PolicyWarning(BaseModel):
    code: str
    message: str
    line_id: int | None = None


class EventOut(BaseModel):
    id: int
    action: str
    from_status: str | None
    to_status: str | None
    comment: str | None
    details: dict | None
    created_at: datetime
    actor: UserBrief


class ClaimSummary(BaseModel):
    id: int
    period: str
    status: ClaimStatus
    employee: UserBrief
    employee_department: str | None
    approver: UserBrief | None
    total_claimed: Money
    total_approved: Money
    line_count: int
    submitted_at: datetime | None
    status_changed_at: datetime
    payout_batch_id: int | None
    payment_reference: str | None
    paid_at: datetime | None
    # Only filled on reviewer inboxes, where it helps triage; None elsewhere.
    warning_count: int | None = None


class ClaimDetail(ClaimSummary):
    lines: list[LineOut]
    events: list[EventOut]
    warnings: list[PolicyWarning]
    allowed_actions: list[str]


class LineDecision(BaseModel):
    line_id: int
    decision: Literal["approve", "reject"]
    approved_amount: NonNegMoney | None = None
    reason: Annotated[str | None, StringConstraints(strip_whitespace=True, max_length=500)] = None


class ReviewIn(BaseModel):
    # Lines not listed are approved in full (manager) or left as they are (Accounts).
    lines: list[LineDecision] = []
    comment: Annotated[str | None, StringConstraints(strip_whitespace=True, max_length=2000)] = None


class CommentIn(BaseModel):
    comment: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class AttachmentUploadOut(BaseModel):
    attachment: AttachmentOut
    duplicate_of_claim_ids: list[int]


# ---- payouts -------------------------------------------------------------


class BatchCreate(BaseModel):
    payout_date: date
    claim_ids: Annotated[list[int], Field(min_length=1)]


class BatchSummary(BaseModel):
    id: int
    payout_date: date
    status: BatchStatus
    created_by: UserBrief
    created_at: datetime
    paid_on: date | None
    reference: str | None
    claim_count: int
    total: Money


class BatchDetail(BatchSummary):
    claims: list[ClaimSummary]


class MarkPaidIn(BaseModel):
    paid_on: date
    reference: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    # Per-claim payment references (e.g. one UTR per transfer); falls back to `reference`.
    claim_references: dict[int, str] = {}


# ---- reports -------------------------------------------------------------


class PendingRow(BaseModel):
    claim: ClaimSummary
    stage: ClaimStatus
    waiting_with: str
    days_waiting: int


class AuthOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: MeOut


class DevLoginIn(BaseModel):
    email: EmailStr
