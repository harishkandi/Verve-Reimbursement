from fastapi import APIRouter
from sqlalchemy import select

from ..auth import DB, CurrentUser, VerifierUser
from ..models import Category, Claim, ClaimStatus, User
from ..schemas import CategoryOut, ClaimSummary, PolicyOut
from ..serializers import claim_summary
from ..services.policy import get_policy
from .common import claims_query

router = APIRouter(prefix="/api", tags=["inbox"])


@router.get("/inbox/approvals", response_model=list[ClaimSummary])
def approvals(user: CurrentUser, db: DB):
    rows = db.scalars(
        claims_query()
        .where(
            Claim.approver_id == user.id,
            Claim.status == ClaimStatus.SUBMITTED,
            Claim.employee_id != user.id,
        )
        .order_by(Claim.submitted_at)
    )
    return [claim_summary(c, db) for c in rows]


@router.get("/inbox/team", response_model=list[ClaimSummary])
def team_history(user: CurrentUser, db: DB):
    """Claims from the user's direct reports, or that they approved, excluding drafts."""
    report_ids = select(User.id).where(User.manager_id == user.id)
    rows = db.scalars(
        claims_query()
        .where(
            (Claim.employee_id.in_(report_ids)) | (Claim.approver_id == user.id),
            Claim.employee_id != user.id,
            Claim.status != ClaimStatus.DRAFT,
        )
        .order_by(Claim.status_changed_at.desc())
        .limit(200)
    )
    return [claim_summary(c) for c in rows]


@router.get("/inbox/verification", response_model=list[ClaimSummary])
def verification(user: VerifierUser, db: DB):
    rows = db.scalars(
        claims_query()
        .where(Claim.status == ClaimStatus.MANAGER_APPROVED, Claim.employee_id != user.id)
        .order_by(Claim.manager_approved_at)
    )
    return [claim_summary(c, db) for c in rows]


@router.get("/categories", response_model=list[CategoryOut])
def categories(user: CurrentUser, db: DB, include_inactive: bool = False):
    stmt = select(Category).order_by(Category.sort_order, Category.name)
    if not (include_inactive and user.is_admin):
        stmt = stmt.where(Category.is_active)
    return db.scalars(stmt).all()


@router.get("/policy", response_model=PolicyOut)
def policy(user: CurrentUser, db: DB):
    return get_policy(db)
