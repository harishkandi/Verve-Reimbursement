from sqlalchemy import Select, select
from sqlalchemy.orm import selectinload

from ..models import Claim, ClaimLine


def claims_query() -> Select[tuple[Claim]]:
    # Lists show totals, so lines are loaded up front instead of one query per claim.
    return select(Claim).options(
        selectinload(Claim.lines).selectinload(ClaimLine.category),
        selectinload(Claim.employee),
        selectinload(Claim.approver),
    )
