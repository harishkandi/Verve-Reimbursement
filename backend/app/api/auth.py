from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select

from ..auth import DB, CurrentUser, create_token
from ..config import settings
from ..models import User
from ..schemas import AuthOut, DevLoginIn, MeOut, UserBrief
from ..serializers import me_out

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/me", response_model=MeOut)
def me(user: CurrentUser, db: DB):
    return me_out(db, user)


# Sign-in for local development only. Production uses company SSO (Google/Microsoft, spec Q5),
# which will exchange the provider's ID token for the same JWT.
@router.post("/dev-login", response_model=AuthOut)
def dev_login(body: DevLoginIn, db: DB):
    if not settings.dev_login_enabled:
        raise HTTPException(404, "Not found")
    user = db.scalar(select(User).where(func.lower(User.email) == body.email.lower()))
    if user is None or not user.is_active:
        raise HTTPException(401, "No active user with that email")
    return AuthOut(access_token=create_token(user), user=me_out(db, user))


class DevUser(UserBrief):
    role: str


@router.get("/dev-users", response_model=list[DevUser])
def dev_users(db: DB):
    if not settings.dev_login_enabled:
        raise HTTPException(404, "Not found")
    users = db.scalars(select(User).where(User.is_active).order_by(User.name)).all()
    managers = {u.manager_id for u in users if u.manager_id}

    def role(u: User) -> str:
        if u.is_admin:
            return "Admin"
        if u.can_verify or u.can_pay:
            return "Accounts"
        if u.id in managers or u.is_fallback_approver:
            return "Manager"
        return "Employee"

    return [DevUser(id=u.id, name=u.name, email=u.email, role=role(u)) for u in users]
