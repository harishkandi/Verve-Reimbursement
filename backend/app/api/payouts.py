from typing import Literal

from fastapi import APIRouter, Response
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..auth import DB, PayerUser
from ..models import Claim, ClaimStatus, PayoutBatch
from ..schemas import BatchCreate, BatchDetail, BatchSummary, ClaimSummary, MarkPaidIn
from ..serializers import batch_detail, batch_summary, claim_summary
from ..services import payouts as svc
from ..services.notify import commit
from .common import claims_query

router = APIRouter(prefix="/api/payouts", tags=["payouts"])


@router.get("/ready", response_model=list[ClaimSummary])
def ready(user: PayerUser, db: DB):
    rows = db.scalars(claims_query().where(Claim.status == ClaimStatus.VERIFIED).order_by(Claim.verified_at))
    return [claim_summary(c) for c in rows]


@router.get("", response_model=list[BatchSummary])
def batches(user: PayerUser, db: DB):
    rows = db.scalars(
        select(PayoutBatch)
        .options(selectinload(PayoutBatch.claims).selectinload(Claim.lines))
        .order_by(PayoutBatch.payout_date.desc(), PayoutBatch.id.desc())
    )
    return [batch_summary(b) for b in rows]


@router.post("", response_model=BatchDetail, status_code=201)
def create(body: BatchCreate, user: PayerUser, db: DB):
    batch = svc.create_batch(db, user, body.payout_date, body.claim_ids)
    commit(db)
    db.refresh(batch)
    return batch_detail(batch)


@router.get("/{batch_id}", response_model=BatchDetail)
def get(batch_id: int, user: PayerUser, db: DB):
    return batch_detail(svc.get_batch(db, batch_id))


@router.post("/{batch_id}/remove/{claim_id}", response_model=BatchDetail)
def remove(batch_id: int, claim_id: int, user: PayerUser, db: DB):
    batch = svc.get_batch(db, batch_id)
    svc.remove_claim(db, user, batch, claim_id)
    commit(db)
    db.refresh(batch)
    return batch_detail(batch)


@router.post("/{batch_id}/mark-paid", response_model=BatchDetail)
def mark_paid(batch_id: int, body: MarkPaidIn, user: PayerUser, db: DB):
    batch = svc.get_batch(db, batch_id)
    svc.mark_paid(db, user, batch, body.paid_on, body.reference, body.claim_references)
    commit(db)
    db.refresh(batch)
    return batch_detail(batch)


@router.get("/{batch_id}/export")
def export(batch_id: int, user: PayerUser, db: DB, format: Literal["csv", "xlsx"] = "xlsx"):
    batch = svc.get_batch(db, batch_id)
    name = f"payout-{batch.payout_date.isoformat()}-batch{batch.id}"
    if format == "csv":
        return Response(
            svc.export_csv(batch), media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{name}.csv"'},
        )
    return Response(
        svc.export_xlsx(batch),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{name}.xlsx"'},
    )
