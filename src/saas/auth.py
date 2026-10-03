"""Authentication and authorization for the SaaS layer."""

from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel

from saas.database import row
from saas.models import User
from saas.repositories import get_user, get_user_by_email
from saas.security import create_access_token, decode_token, verify_password

oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=False)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict[str, Any]


class CurrentUser(BaseModel):
    user: User
    token_claims: dict[str, Any]


async def authenticate(tenant_id: int, email: str, password: str | None = None) -> User:
    user = get_user_by_email(tenant_id, email)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    if password is not None and user.hashed_password and not verify_password(password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    return user


def login_for_token(tenant_id: int, form_data: OAuth2PasswordRequestForm) -> TokenOut:
    user = authenticate(tenant_id, form_data.username, form_data.password)
    token = create_access_token(subject=str(user.id))
    return TokenOut(access_token=token, user=_user_payload(user))


def _user_payload(user: User) -> dict[str, Any]:
    return {"id": user.id, "tenant_id": user.tenant_id, "email": user.email, "display_name": user.display_name,
            "role": user.role}


async def get_current(authorization: str | None = Depends(oauth2)) -> CurrentUser:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated")
    token = authorization.split(" ", 1)[1].strip()
    claims = decode_token(token)
    sub = claims.get("sub")
    if not sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token claims")
    user = get_user_by_email(int(claims.get("tid", 0)), "") or get_user(int(sub))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user not found")
    return CurrentUser(user=user, token_claims=claims)


def require_roles(*roles: str):
    allowed = set(roles)

    def checker(current: CurrentUser = Depends(get_current)) -> CurrentUser:
        if current.user.role not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="forbidden")
        return current

    return checker
