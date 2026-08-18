"""Authentication & RBAC (JWT). RADIUS/OIDC can slot in behind the same router."""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import User
from ..schemas import Token

router = APIRouter(prefix="/auth", tags=["auth"])
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/token")
settings = get_settings()

ROLE_RANK = {"viewer": 0, "operator": 1, "admin": 2}


def hash_password(p: str) -> str:
    return pwd.hash(p)


def _make_token(user: User) -> str:
    exp = dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=settings.jwt_ttl_min)
    return jwt.encode({"sub": user.username, "role": user.role, "exp": exp},
                      settings.jwt_secret, algorithm="HS256")


@router.post("/token", response_model=Token)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == form.username))
    if not user or not user.active or not pwd.verify(form.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "bad credentials")
    return Token(access_token=_make_token(user), role=user.role)


def current_user(token: str = Depends(oauth2), db: Session = Depends(get_db)) -> User:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token")
    user = db.scalar(select(User).where(User.username == payload.get("sub")))
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "unknown user")
    return user


def require(role: str):
    def _dep(user: User = Depends(current_user)) -> User:
        if ROLE_RANK.get(user.role, -1) < ROLE_RANK[role]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"requires {role}")
        return user
    return _dep
