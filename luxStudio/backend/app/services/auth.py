import base64
import hashlib
import hmac
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from passlib.context import CryptContext
from sqlalchemy.orm import Session

from ..database import engine
from ..models import User

COMPANY_NAME = "SALVI LIGHTING"
TOKEN_TTL_HOURS = 12
password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _secret_key() -> bytes:
    return os.getenv("AUTH_SECRET_KEY", "lux-studio-local-dev-secret-change-me").encode("utf-8")


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def hash_password(password: str) -> str:
    return password_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    if password_hash.startswith("pbkdf2_sha256$"):
        try:
            algorithm, iterations, salt, expected = password_hash.split("$", 3)
            if algorithm != "pbkdf2_sha256":
                return False
            digest = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode("utf-8"),
                _b64url_decode(salt),
                int(iterations),
            )
            return hmac.compare_digest(_b64url(digest), expected)
        except Exception:
            return False
    return password_context.verify(password, password_hash)


def create_token(user: User) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "role": user.role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=TOKEN_TTL_HOURS)).timestamp()),
    }
    signing_input = f"{_b64url(json.dumps(header, separators=(',', ':')).encode())}.{_b64url(json.dumps(payload, separators=(',', ':')).encode())}"
    signature = hmac.new(_secret_key(), signing_input.encode("ascii"), hashlib.sha256).digest()
    return f"{signing_input}.{_b64url(signature)}"


def decode_token(token: str) -> dict[str, Any]:
    try:
        header_b64, payload_b64, signature_b64 = token.split(".", 2)
        signing_input = f"{header_b64}.{payload_b64}"
        expected = hmac.new(_secret_key(), signing_input.encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(_b64url(expected), signature_b64):
            raise ValueError("Invalid signature")
        payload = json.loads(_b64url_decode(payload_b64))
        if int(payload.get("exp", 0)) < int(datetime.now(timezone.utc).timestamp()):
            raise ValueError("Expired token")
        return payload
    except Exception as exc:
        raise ValueError("Invalid token") from exc


def ensure_users_table() -> None:
    User.__table__.create(bind=engine, checkfirst=True)


def ensure_initial_admin(db: Session) -> None:
    ensure_users_table()
    if db.query(User).count() > 0:
        return

    email = os.getenv("ADMIN_EMAIL", "admin@salvi.lighting")
    password = os.getenv("ADMIN_PASSWORD", "Admin123!")
    name = os.getenv("ADMIN_NAME", "Admin SALVI")
    user = User(
        company_name=COMPANY_NAME,
        email=email.lower().strip(),
        name=name,
        password_hash=hash_password(password),
        role="ADMIN",
        is_active=True,
        must_reset_password=True,
    )
    db.add(user)
    db.commit()
    print(
        "Initial ADMIN user created for SALVI LIGHTING. "
        f"Email: {email}. Change the initial password after first login."
    )
