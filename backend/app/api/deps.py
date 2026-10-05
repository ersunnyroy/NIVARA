from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import CSRF_COOKIE, CSRF_HEADER, SESSION_COOKIE, csrf_valid, decode_token
from app.core.timeutil import utcnow
from app.models import User, UserSession

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _token_from(request: Request) -> tuple[str | None, bool]:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip(), False
    return request.cookies.get(SESSION_COOKIE), True


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token, from_cookie = _token_from(request)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    claims = decode_token(token)
    if not claims:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session")
    sess = db.get(UserSession, claims.get("sid"))
    if sess is None or sess.revoked_at is not None or sess.expires_at.replace(tzinfo=sess.expires_at.tzinfo or utcnow().tzinfo) < utcnow():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired or revoked")
    # Cookie-authenticated state-changing requests must carry the CSRF double-submit token.
    if from_cookie and request.method not in SAFE_METHODS:
        if not csrf_valid(sess.id, request.cookies.get(CSRF_COOKIE), request.headers.get(CSRF_HEADER)):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "CSRF token missing or invalid")
    user = db.get(User, int(claims["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User inactive")
    request.state.user_id = user.id
    request.state.session_id = sess.id
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin only")
    return user


def client_ip(request: Request) -> str | None:
    """Peer address. Behind the bundled nginx, uvicorn's --proxy-headers sets this from X-Forwarded-For, which
    nginx overwrites with the real client address (never trust a client-supplied header directly)."""
    return request.client.host if request.client else None
