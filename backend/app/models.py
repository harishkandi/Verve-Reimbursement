from __future__ import annotations

import enum
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

MONEY = Numeric(12, 2)
ZERO = Decimal("0.00")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(dt: datetime | None) -> datetime | None:
    # SQLite hands back naive datetimes; everything is stored in UTC.
    if dt is None or dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=timezone.utc)


def str_enum(e: type[enum.Enum]) -> SAEnum:
    # Stored as plain strings so the schema is the same on SQLite and Postgres.
    return SAEnum(
        e,
        native_enum=False,
        length=32,
        values_callable=lambda members: [m.value for m in members],
        validate_strings=True,
    )


class ClaimStatus(str, enum.Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    RETURNED = "returned"
    MANAGER_APPROVED = "manager_approved"
    VERIFIED = "verified"
    IN_PAYOUT_BATCH = "in_payout_batch"
    PAID = "paid"
    REJECTED = "rejected"


class LineStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class PaymentMode(str, enum.Enum):
    CASH = "cash"
    ONLINE = "online"


class BatchStatus(str, enum.Enum):
    OPEN = "open"
    PAID = "paid"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    employee_code: Mapped[str | None] = mapped_column(String(50), unique=True)
    department: Mapped[str | None] = mapped_column(String(100))
    manager_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    can_verify: Mapped[bool] = mapped_column(Boolean, default=False)
    can_pay: Mapped[bool] = mapped_column(Boolean, default=False)
    # Approves claims of people with no manager: founders and CXOs.
    is_fallback_approver: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    bank_account_name: Mapped[str | None] = mapped_column(String(200))
    bank_account_number: Mapped[str | None] = mapped_column(String(34))
    bank_ifsc: Mapped[str | None] = mapped_column(String(11))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    manager: Mapped[User | None] = relationship(remote_side="User.id")


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    per_item_limit: Mapped[Decimal | None] = mapped_column(MONEY)
    monthly_limit: Mapped[Decimal | None] = mapped_column(MONEY)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class Policy(Base):
    """Single row (id=1) of company-wide reimbursement rules."""

    __tablename__ = "policy"

    id: Mapped[int] = mapped_column(primary_key=True)
    submission_due_day: Mapped[int] = mapped_column(Integer, default=5)
    max_age_days: Mapped[int] = mapped_column(Integer, default=60)
    cash_no_bill_item_limit: Mapped[Decimal | None] = mapped_column(MONEY)
    cash_no_bill_month_limit: Mapped[Decimal | None] = mapped_column(MONEY)


class PayoutBatch(Base):
    __tablename__ = "payout_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    payout_date: Mapped[date] = mapped_column(Date)
    status: Mapped[BatchStatus] = mapped_column(str_enum(BatchStatus), default=BatchStatus.OPEN)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    paid_on: Mapped[date | None] = mapped_column(Date)
    reference: Mapped[str | None] = mapped_column(String(100))

    created_by: Mapped[User] = relationship()
    claims: Mapped[list[Claim]] = relationship(back_populates="payout_batch", order_by="Claim.id")


class Claim(Base):
    """One employee's reimbursement claim for one month."""

    __tablename__ = "claims"
    __table_args__ = (UniqueConstraint("employee_id", "period", name="uq_claim_employee_period"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    period: Mapped[str] = mapped_column(String(7))  # YYYY-MM
    status: Mapped[ClaimStatus] = mapped_column(
        str_enum(ClaimStatus), default=ClaimStatus.DRAFT, index=True
    )
    approver_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    status_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    manager_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    manager_approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    payout_batch_id: Mapped[int | None] = mapped_column(ForeignKey("payout_batches.id"))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payment_reference: Mapped[str | None] = mapped_column(String(100))

    employee: Mapped[User] = relationship(foreign_keys=[employee_id])
    approver: Mapped[User | None] = relationship(foreign_keys=[approver_id])
    payout_batch: Mapped[PayoutBatch | None] = relationship(back_populates="claims")
    lines: Mapped[list[ClaimLine]] = relationship(
        back_populates="claim",
        cascade="all, delete-orphan",
        order_by="(ClaimLine.expense_date, ClaimLine.id)",
    )
    events: Mapped[list[ClaimEvent]] = relationship(order_by="ClaimEvent.id")

    @property
    def total_claimed(self) -> Decimal:
        return sum((line.amount for line in self.lines), ZERO)

    @property
    def total_approved(self) -> Decimal:
        return sum(
            (
                line.approved_amount or ZERO
                for line in self.lines
                if line.status == LineStatus.APPROVED
            ),
            ZERO,
        )


class ClaimLine(Base):
    __tablename__ = "claim_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("claims.id", ondelete="CASCADE"), index=True)
    expense_date: Mapped[date] = mapped_column(Date)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    description: Mapped[str] = mapped_column(String(500))
    payment_mode: Mapped[PaymentMode] = mapped_column(str_enum(PaymentMode))
    amount: Mapped[Decimal] = mapped_column(MONEY)
    approved_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    status: Mapped[LineStatus] = mapped_column(str_enum(LineStatus), default=LineStatus.PENDING)
    # Why an approver changed or rejected this line; shown to the employee.
    adjust_reason: Mapped[str | None] = mapped_column(String(500))
    no_bill_declaration: Mapped[bool] = mapped_column(Boolean, default=False)
    gstin: Mapped[str | None] = mapped_column(String(15))
    tax_amount: Mapped[Decimal | None] = mapped_column(MONEY)

    claim: Mapped[Claim] = relationship(back_populates="lines")
    category: Mapped[Category] = relationship()
    attachments: Mapped[list[Attachment]] = relationship(
        back_populates="line", cascade="all, delete-orphan", order_by="Attachment.id"
    )


class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    line_id: Mapped[int] = mapped_column(ForeignKey("claim_lines.id", ondelete="CASCADE"), index=True)
    original_name: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    storage_key: Mapped[str] = mapped_column(String(255), unique=True)
    uploaded_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    line: Mapped[ClaimLine] = relationship(back_populates="attachments")


class ClaimEvent(Base):
    """Append-only audit trail and comment thread for a claim. Never updated or deleted."""

    __tablename__ = "claim_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("claims.id"), index=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(40))
    from_status: Mapped[str | None] = mapped_column(String(32))
    to_status: Mapped[str | None] = mapped_column(String(32))
    comment: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    actor: Mapped[User] = relationship()
