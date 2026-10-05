"""Password hashing (argon2id), signed session tokens backed by revocable DB sessions, CSRF tokens,
and symmetric encryption for provider secrets stored in the database."""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken

from app.config.settings import get_settings
from app.core.timeutil import utcnow

_ph = PasswordHasher()  # argon2id with library defaults (memory-hard)
SESSION_COOKIE = "nivara_session"
CSRF_COOKIE = "nivara_csrf"
CSRF_HEADER = "x-csrf-token"


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_problems(password: str) -> list[str]:
    problems = []
    if len(password) < 10:
        problems.append("at least 10 characters")
    if password.lower() == password or password.upper() == password:
        problems.append("mixed case")
    if not any(ch.isdigit() for ch in password):
        problems.append("a digit")
    return problems


def new_session_id() -> str:
    return secrets.token_urlsafe(32)


def make_token(session_id: str, user_id: int, ttl_minutes: int | None = None) -> tuple[str, datetime]:
    s = get_settings()
    exp = utcnow() + timedelta(minutes=ttl_minutes or s.session_ttl_minutes)
    tok = jwt.encode({"sid": session_id, "sub": str(user_id), "exp": exp, "iat": utcnow()}, s.secret_key, "HS256")
    return tok, exp


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, get_settings().secret_key, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


def csrf_for(session_id: str) -> str:
    """CSRF token bound to the session (HMAC), validated against the double-submit cookie."""
    key = get_settings().secret_key.encode()
    return hmac.new(key, f"csrf:{session_id}".encode(), hashlib.sha256).hexdigest()


def csrf_valid(session_id: str, cookie_val: str | None, header_val: str | None) -> bool:
    if not cookie_val or not header_val:
        return False
    expected = csrf_for(session_id)
    return hmac.compare_digest(cookie_val, header_val) and hmac.compare_digest(header_val, expected)


def _fernet() -> Fernet:
    s = get_settings()
    if s.encryption_key:
        return Fernet(s.encryption_key.encode())
    # Derive a key from SECRET_KEY when no dedicated key is configured (dev only).
    digest = hashlib.sha256(("enc:" + s.secret_key).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(plain: str) -> str:
    return _fernet().encrypt(plain.encode()).decode()


def decrypt_secret(token: str) -> str | None:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        return None


def mask_secret(value: str | None) -> str | None:
    if not value:
        return None
    return value[:2] + "•" * max(len(value) - 6, 4) + value[-4:]
