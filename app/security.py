from datetime import UTC, datetime, timedelta

import bcrypt
from jose import JWTError, jwt

from app.config import settings
from app.models import UserRole


def hash_password(password: str) -> str:
    """Hash password with bcrypt (avoids passlib vs bcrypt>=4.1 incompatibility)."""
    pw = password.encode("utf-8")
    if len(pw) > 72:
        pw = pw[:72]
    digest = bcrypt.hashpw(pw, bcrypt.gensalt())
    return digest.decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain.encode("utf-8"),
            hashed.encode("ascii"),
        )
    except ValueError:
        return False


def create_access_token(*, user_id: int, role: UserRole) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "role": role.value,
        "exp": expire,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])


def parse_user_id_from_payload(payload: dict) -> int:
    sub = payload.get("sub")
    if sub is None:
        raise JWTError("missing sub")
    return int(sub)
