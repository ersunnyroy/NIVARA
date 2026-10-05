from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import client_ip, get_current_user
from app.config.settings import get_settings
from app.core.audit import audit
from app.core.db import get_db
from app.core.ratelimit import limiter
from app.core.security import (
    CSRF_COOKIE,
    SESSION_COOKIE,
    csrf_for,
    hash_password,
    make_token,
    new_session_id,
    password_problems,
    verify_password,
)
from app.core.timeutil import utcnow
from app.models import User, UserSession

router = APIRouter(prefix="/auth", tags=["auth"])


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=255)  # validated at registration, not at login
    password: str = Field(min_length=1, max_length=256)


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)
    full_name: str | None = Field(None, max_length=255)


class UserOut(BaseModel):
    id: int
    email: str
    full_name: str | None
    role: str


def _issue(response: Response, db: Session, user: User, request: Request) -> dict:
    s = get_settings()
    sid = new_session_id()
    token, exp = make_token(sid, user.id)
    db.add(UserSession(id=sid, user_id=user.id, created_at=utcnow(), expires_at=exp, ip=client_ip(request),
                       user_agent=(request.headers.get("user-agent") or "")[:500]))
    user.last_login_at = utcnow()
    max_age = s.session_ttl_minutes * 60
    response.set_cookie(SESSION_COOKIE, token, max_age=max_age, httponly=True, secure=s.cookie_secure,
                        samesite="lax", path="/")
    csrf = csrf_for(sid)
    response.set_cookie(CSRF_COOKIE, csrf, max_age=max_age, httponly=False, secure=s.cookie_secure,
                        samesite="lax", path="/")
    return {"user": UserOut(id=user.id, email=user.email, full_name=user.full_name, role=user.role).model_dump(),
            "csrf_token": csrf, "access_token": token, "expires_at": exp.isoformat()}


@router.get("/status")
def auth_status(db: Session = Depends(get_db)) -> dict:
    """Whether first-run registration is open (no users yet)."""
    n = db.scalar(select(func.count()).select_from(User)) or 0
    return {"registration_open": n == 0}


@router.post("/register", status_code=201)
def register(body: RegisterIn, request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    """First-run bootstrap: only allowed while there are no users. The first user becomes admin.
    Further users are created by an admin via /api/admin/users."""
    n = db.scalar(select(func.count()).select_from(User)) or 0
    if n > 0:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Registration is closed; ask an admin to create your account")
    probs = password_problems(body.password)
    if probs:
        raise HTTPException(422, "Password needs " + ", ".join(probs))
    user = User(email=body.email.lower(), password_hash=hash_password(body.password), full_name=body.full_name,
                role="admin")
    db.add(user)
    db.flush()
    out = _issue(response, db, user, request)
    audit(db, "user.register", user.id, "user", user.id, ip=client_ip(request))
    db.commit()
    return out


@router.post("/login")
def login(body: Credentials, request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    ip = client_ip(request) or "unknown"
    ok, _ = limiter.hit(f"login:{ip}", get_settings().login_rate_limit_per_minute)
    ok2, _ = limiter.hit(f"login-user:{body.email.lower()}", get_settings().login_rate_limit_per_minute)
    if not (ok and ok2):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many login attempts; try again in a minute")
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        audit(db, "auth.login_failed", None, "user", None, {"email": body.email.lower()}, ip)
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    out = _issue(response, db, user, request)
    audit(db, "auth.login", user.id, ip=ip)
    db.commit()
    return out


@router.post("/logout")
def logout(request: Request, response: Response, user: User = Depends(get_current_user),
           db: Session = Depends(get_db)) -> dict:
    sess = db.get(UserSession, request.state.session_id)
    if sess:
        sess.revoked_at = utcnow()
    audit(db, "auth.logout", user.id, ip=client_ip(request))
    db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut(id=user.id, email=user.email, full_name=user.full_name, role=user.role)


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=10, max_length=256)


@router.post("/password")
def change_password(body: PasswordChange, request: Request, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)) -> dict:
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    probs = password_problems(body.new_password)
    if probs:
        raise HTTPException(422, "Password needs " + ", ".join(probs))
    user.password_hash = hash_password(body.new_password)
    # Revoke other sessions.
    for s in db.scalars(select(UserSession).where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None))):
        if s.id != request.state.session_id:
            s.revoked_at = utcnow()
    audit(db, "auth.password_changed", user.id, ip=client_ip(request))
    db.commit()
    return {"ok": True}


