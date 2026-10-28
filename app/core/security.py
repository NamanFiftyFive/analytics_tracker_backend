import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import settings

_hasher = PasswordHasher()

# Verified against when the email is unknown, so a login for a missing user
# takes as long as one with a wrong password (no account enumeration by timing).
_DUMMY_HASH = _hasher.hash("dummy-password-for-timing")


class PasswordService:
    """Argon2 password hashing."""

    @staticmethod
    def hash(password: str) -> str:
        return _hasher.hash(password)

    @staticmethod
    def verify(password: str, password_hash: str | None) -> bool:
        """Pass password_hash=None for an unknown user; still does the full hash work."""
        if password_hash is None:
            PasswordService._verify(password, _DUMMY_HASH)
            return False
        return PasswordService._verify(password, password_hash)

    @staticmethod
    def _verify(password: str, password_hash: str) -> bool:
        try:
            return _hasher.verify(password_hash, password)
        except (VerifyMismatchError, InvalidHashError):
            return False


class TokenService:
    """JWT access tokens and opaque refresh tokens."""

    @staticmethod
    def create_access_token(user_id: UUID) -> tuple[str, int]:
        """Returns (token, lifetime in seconds)."""
        lifetime = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        now = datetime.now(UTC)
        payload = {"sub": str(user_id), "type": "access", "iat": now, "exp": now + lifetime}
        token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
        return token, int(lifetime.total_seconds())

    @staticmethod
    def decode_access_token(token: str) -> UUID | None:
        """Returns the user id, or None if the token is invalid, expired or not an access token."""
        try:
            payload = jwt.decode(
                token,
                settings.JWT_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM],
                options={"require": ["exp", "sub"]},
            )
            if payload.get("type") != "access":
                return None
            return UUID(payload["sub"])
        except (jwt.PyJWTError, ValueError):
            return None

    @staticmethod
    def new_refresh_token() -> tuple[str, str, datetime]:
        """Returns (token for the client, hash to store, expiry)."""
        token = secrets.token_urlsafe(48)
        expires_at = datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        return token, TokenService.hash_refresh_token(token), expires_at

    @staticmethod
    def hash_refresh_token(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()


class ApiKeyGenerator:
    """Project API keys used by SDKs to send events, e.g. pk_live_Xq3...

    Keys are long random strings, so a fast SHA-256 hash is enough to store them safely
    (unlike passwords, which are short and guessable and need slow argon2)."""

    PREFIX = "pk_live_"
    VISIBLE_CHARS = 12  # stored in clear so people can tell keys apart: "pk_live_Xq3a"

    @staticmethod
    def generate() -> tuple[str, str, str]:
        """Returns (full key for the user, visible prefix, hash to store)."""
        key = ApiKeyGenerator.PREFIX + secrets.token_urlsafe(32)
        return key, key[: ApiKeyGenerator.VISIBLE_CHARS], ApiKeyGenerator.hash(key)

    @staticmethod
    def hash(key: str) -> str:
        return hashlib.sha256(key.encode()).hexdigest()
