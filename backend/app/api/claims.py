from fastapi import APIRouter, File, Response, UploadFile, status
from fastapi.responses import FileResponse

from ..auth import DB, CurrentUser
from ..config import settings
from ..models import Claim
from ..schemas import (
    AttachmentOut,
    AttachmentUploadOut,
    ClaimCreate,
    ClaimDetail,
    ClaimSummary,
    CommentIn,
    LineIn,
    ReviewIn,
)
from ..serializers import claim_detail, claim_summary
from ..services import claims as svc
from ..services import storage
from ..services.errors import Invalid
from ..services.notify import commit
from .common import claims_query

router = APIRouter(prefix="/api/claims", tags=["claims"])


def _done(db, claim: Claim, user) -> ClaimDetail:
    commit(db)
    db.refresh(claim)
    return claim_detail(db, claim, user)


@router.get("", response_model=list[ClaimSummary])
def my_claims(user: CurrentUser, db: DB):
    rows = db.scalars(claims_query().where(Claim.employee_id == user.id).order_by(Claim.period.desc()))
    return [claim_summary(c) for c in rows]


@router.post("", response_model=ClaimDetail)
def open_claim(body: ClaimCreate, user: CurrentUser, db: DB, response: Response):
    claim, created = svc.get_or_create_claim(db, user, body.period)
    if created:
        response.status_code = status.HTTP_201_CREATED
    return _done(db, claim, user)


@router.get("/{claim_id}", response_model=ClaimDetail)
def get_claim(claim_id: int, user: CurrentUser, db: DB):
    return claim_detail(db, svc.get_claim(db, user, claim_id), user)


@router.post("/{claim_id}/lines", response_model=ClaimDetail)
def add_line(claim_id: int, body: LineIn, user: CurrentUser, db: DB):
    claim = svc.get_claim(db, user, claim_id)
    svc.add_line(db, user, claim, body)
    return _done(db, claim, user)


@router.put("/{claim_id}/lines/{line_id}", response_model=ClaimDetail)
def update_line(claim_id: int, line_id: int, body: LineIn, user: CurrentUser, db: DB):
    claim = svc.get_claim(db, user, claim_id)
    svc.update_line(db, user, claim, line_id, body)
    return _done(db, claim, user)


@router.delete("/{claim_id}/lines/{line_id}", response_model=ClaimDetail)
def delete_line(claim_id: int, line_id: int, user: CurrentUser, db: DB):
    claim = svc.get_claim(db, user, claim_id)
    svc.delete_line(db, user, claim, line_id)
    return _done(db, claim, user)


@router.post("/{claim_id}/lines/{line_id}/attachments", response_model=AttachmentUploadOut)
async def upload_bill(claim_id: int, line_id: int, user: CurrentUser, db: DB, file: UploadFile = File(...)):
    claim = svc.get_claim(db, user, claim_id)
    limit = settings.max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise Invalid(f"Bills must be {settings.max_upload_mb} MB or smaller")
    att, dupes = svc.add_attachment(
        db, user, claim, line_id, file.filename or "bill", file.content_type or "", data
    )
    commit(db)
    return AttachmentUploadOut(attachment=AttachmentOut.model_validate(att), duplicate_of_claim_ids=dupes)


@router.get("/{claim_id}/attachments/{attachment_id}")
def download_bill(claim_id: int, attachment_id: int, user: CurrentUser, db: DB):
    claim = svc.get_claim(db, user, claim_id)
    att = svc.find_attachment(claim, attachment_id)
    return FileResponse(
        storage.path_for(att.storage_key),
        media_type=att.content_type,
        filename=att.original_name,
        content_disposition_type="inline",
    )


@router.delete("/{claim_id}/attachments/{attachment_id}", response_model=ClaimDetail)
def delete_bill(claim_id: int, attachment_id: int, user: CurrentUser, db: DB):
    claim = svc.get_claim(db, user, claim_id)
    svc.delete_attachment(db, user, claim, attachment_id)
    return _done(db, claim, user)


@router.post("/{claim_id}/submit", response_model=ClaimDetail)
def submit(claim_id: int, user: CurrentUser, db: DB):
    claim = svc.get_claim(db, user, claim_id)
    svc.submit(db, user, claim)
    return _done(db, claim, user)


@router.post("/{claim_id}/withdraw", response_model=ClaimDetail)
def withdraw(claim_id: int, user: CurrentUser, db: DB):
    claim = svc.get_claim(db, user, claim_id)
    svc.withdraw(db, user, claim)
    return _done(db, claim, user)


@router.post("/{claim_id}/comments", response_model=ClaimDetail)
def comment(claim_id: int, body: CommentIn, user: CurrentUser, db: DB):
    claim = svc.get_claim(db, user, claim_id)
    svc.add_comment(db, user, claim, body.comment)
    return _done(db, claim, user)


@router.post("/{claim_id}/approve", response_model=ClaimDetail)
def approve(claim_id: int, body: ReviewIn, user: CurrentUser, db: DB):
    claim = svc.get_claim(db, user, claim_id)
    svc.manager_approve(db, user, claim, body)
    return _done(db, claim, user)


@router.post("/{claim_id}/verify", response_model=ClaimDetail)
def verify(claim_id: int, body: ReviewIn, user: CurrentUser, db: DB):
    claim = svc.get_claim(db, user, claim_id)
    svc.verify(db, user, claim, body)
    return _done(db, claim, user)


@router.post("/{claim_id}/return", response_model=ClaimDetail)
def return_claim(claim_id: int, body: CommentIn, user: CurrentUser, db: DB):
    claim = svc.get_claim(db, user, claim_id)
    svc.return_claim(db, user, claim, body.comment)
    return _done(db, claim, user)


@router.post("/{claim_id}/reject", response_model=ClaimDetail)
def reject(claim_id: int, body: CommentIn, user: CurrentUser, db: DB):
    claim = svc.get_claim(db, user, claim_id)
    svc.reject_claim(db, user, claim, body.comment)
    return _done(db, claim, user)
