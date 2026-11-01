"""API key and JSON Web Token authentication helpers."""

from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext

from api.config import Settings
from api.errors import APIError

password_context = CryptContext(schemes=["argon2"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash a password with Argon2."""
    return password_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its Argon2 hash."""
    return password_context.verify(password, password_hash)


def create_access_token(username: str, settings: Settings) -> str:
    """Create a short-lived access token."""
    if not settings.jwt_secret:
        raise RuntimeError("JWT_SECRET must be set when AUTH_MODE=jwt.")
    expires = datetime.now(timezone.utc) + timedelta(minutes=45)
    return jwt.encode({"sub": username, "exp": expires}, settings.jwt_secret, algorithm="HS256")


def decode_access_token(token: str, settings: Settings) -> str:
    """Decode a signed token and return its subject."""
    if not settings.jwt_secret:
        raise APIError(401, "invalid_token", "Sign in again to continue.")
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.InvalidTokenError as error:
        raise APIError(401, "invalid_token", "Sign in again to continue.") from error
    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject:
        raise APIError(401, "invalid_token", "Sign in again to continue.")
    return subject
