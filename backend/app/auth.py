from datetime import timedelta
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import User, utcnow

ALGORITHM = "HS256"
bearer = HTTPBearer(auto_error=False)


def create_token(user: User) -> str:
    now = utcnow()
    payload = {
        "sub": str(user.id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expiry_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def get_current_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
    if creds is None:
        raise unauthorized
    try:
        payload = jwt.decode(creds.credentials, settings.jwt_secret, algorithms=[ALGORITHM])
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise unauthorized from None
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise unauthorized
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
DB = Annotated[Session, Depends(get_db)]


def require_admin(user: CurrentUser) -> User:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admins only")
    return user


def require_verifier(user: CurrentUser) -> User:
    if not user.can_verify:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Accounts verification access required")
    return user


def require_payer(user: CurrentUser) -> User:
    if not user.can_pay:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Accounts payout access required")
    return user


AdminUser = Annotated[User, Depends(require_admin)]
VerifierUser = Annotated[User, Depends(require_verifier)]
PayerUser = Annotated[User, Depends(require_payer)]
