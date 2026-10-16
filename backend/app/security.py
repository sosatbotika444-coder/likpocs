from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from pwdlib import PasswordHash

from app.config import settings

password_hash = PasswordHash.recommended()


def hash_password(value: str) -> str:
    return password_hash.hash(value)


def verify_password(value: str, hashed: str) -> bool:
    try:
        return password_hash.verify(value, hashed)
    except Exception:
        return False


def create_token(user_id: UUID, token_type: str, lifetime: timedelta) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {"sub": str(user_id), "type": token_type, "iat": now, "exp": now + lifetime},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


def create_token_pair(user_id: UUID) -> dict[str, str]:
    return {
        "access_token": create_token(user_id, "access", timedelta(minutes=settings.access_token_minutes)),
        "refresh_token": create_token(user_id, "refresh", timedelta(days=settings.refresh_token_days)),
        "token_type": "bearer",
    }
