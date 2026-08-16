"""
Identity service: email/password, phone OTP, email verify, password reset,
server sessions, optional TOTP 2FA.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import struct
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update

from app.db.base import async_session_factory
from app.db.models import AuthSession, AuthToken, UserAccount

logger = logging.getLogger(__name__)

PBKDF2_ITERATIONS = 120_000
SESSION_DAYS = 30
TOKEN_HOURS = 24
OTP_MINUTES = 10


def _hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), PBKDF2_ITERATIONS
    )
    return dk.hex(), salt


def _verify_password(password: str, password_hash: str, salt: str) -> bool:
    calc, _ = _hash_password(password, salt)
    return hmac.compare_digest(calc, password_hash)


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _totp(secret_b32: str, for_time: int | None = None, step: int = 30) -> str:
    """Minimal TOTP (RFC 6238) without external deps. secret is base32."""
    import base64

    key = base64.b32decode(secret_b32.upper() + "=" * ((8 - len(secret_b32) % 8) % 8), casefold=True)
    counter = int((for_time if for_time is not None else time.time()) // step)
    msg = struct.pack(">Q", counter)
    h = hmac.new(key, msg, hashlib.sha1).digest()
    o = h[-1] & 0x0F
    code = (struct.unpack(">I", h[o : o + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return f"{code:06d}"


def verify_totp(secret_b32: str, code: str, window: int = 1) -> bool:
    now = int(time.time())
    for w in range(-window, window + 1):
        if hmac.compare_digest(_totp(secret_b32, now + w * 30), code.strip()):
            return True
    return False


def new_totp_secret() -> str:
    # 20 bytes → base32 without padding
    import base64

    return base64.b32encode(secrets.token_bytes(20)).decode("utf-8").rstrip("=")


class AuthService:
    async def ensure_tables(self) -> None:
        from app.db.base import Base, engine
        # Import models so metadata is complete
        import app.db.models  # noqa: F401

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def register(
        self,
        email: str,
        password: str,
        phone: str | None = None,
        account_id: str | None = None,
    ) -> dict:
        email = email.strip().lower()
        if not email or len(password) < 8:
            raise ValueError("Valid email and password (min 8 chars) required")
        account_id = (account_id or "").strip() or f"ACC-{secrets.token_hex(5).upper()}"
        pw_hash, salt = _hash_password(password)
        now = datetime.now(timezone.utc)
        async with async_session_factory() as session:
            exists = (
                await session.execute(select(UserAccount).where(UserAccount.email == email))
            ).scalar_one_or_none()
            if exists:
                raise ValueError("Email already registered")
            if phone:
                phone = phone.strip()
                p_exists = (
                    await session.execute(select(UserAccount).where(UserAccount.phone == phone))
                ).scalar_one_or_none()
                if p_exists:
                    raise ValueError("Phone already registered")
            user = UserAccount(
                account_id=account_id,
                email=email,
                phone=phone,
                password_hash=pw_hash,
                password_salt=salt,
                email_verified=False,
                phone_verified=False,
                is_admin=False,
                totp_enabled=False,
                created_at=now,
                updated_at=now,
            )
            session.add(user)
            await session.flush()
            verify_raw = secrets.token_urlsafe(32)
            session.add(
                AuthToken(
                    user_id=user.id,
                    email=email,
                    purpose="email_verify",
                    token_hash=_hash_token(verify_raw),
                    expires_at=now + timedelta(hours=TOKEN_HOURS),
                    used=False,
                    created_at=now,
                )
            )
            await session.commit()
            uid = user.id
        logger.info("Registered user email=%s account_id=%s", email, account_id)
        return {
            "account_id": account_id,
            "email": email,
            "user_id": uid,
            "email_verification_token": verify_raw,  # also emailed when SMTP configured
            "message": "Check email to verify. Token also returned once for bootstrap.",
        }

    async def verify_email(self, token: str) -> bool:
        th = _hash_token(token)
        now = datetime.now(timezone.utc)
        async with async_session_factory() as session:
            row = (
                await session.execute(
                    select(AuthToken).where(
                        AuthToken.token_hash == th,
                        AuthToken.purpose == "email_verify",
                        AuthToken.used == False,  # noqa: E712
                    )
                )
            ).scalar_one_or_none()
            if not row or row.expires_at.replace(tzinfo=timezone.utc) < now:
                return False
            row.used = True
            if row.user_id:
                user = (
                    await session.execute(select(UserAccount).where(UserAccount.id == row.user_id))
                ).scalar_one_or_none()
                if user:
                    user.email_verified = True
                    user.updated_at = now
            await session.commit()
            return True

    async def login(
        self,
        email: str,
        password: str,
        totp_code: str | None = None,
        device_label: str | None = None,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> dict:
        email = email.strip().lower()
        async with async_session_factory() as session:
            user = (
                await session.execute(select(UserAccount).where(UserAccount.email == email))
            ).scalar_one_or_none()
            if not user or not _verify_password(password, user.password_hash, user.password_salt):
                raise ValueError("Invalid email or password")
            if user.totp_enabled:
                if not totp_code or not user.totp_secret or not verify_totp(user.totp_secret, totp_code):
                    raise ValueError("Invalid or missing 2FA code")
            raw_session = secrets.token_urlsafe(48)
            now = datetime.now(timezone.utc)
            session.add(
                AuthSession(
                    session_token_hash=_hash_token(raw_session),
                    user_id=user.id,
                    account_id=user.account_id,
                    device_label=device_label,
                    ip=ip,
                    user_agent=(user_agent or "")[:400] or None,
                    created_at=now,
                    expires_at=now + timedelta(days=SESSION_DAYS),
                    revoked=False,
                )
            )
            user.last_login_at = now
            await session.commit()
            return {
                "session_token": raw_session,
                "account_id": user.account_id,
                "email": user.email,
                "email_verified": user.email_verified,
                "totp_enabled": user.totp_enabled,
                "is_admin": user.is_admin,
                "expires_in_days": SESSION_DAYS,
            }

    async def resolve_session(self, session_token: str) -> UserAccount | None:
        th = _hash_token(session_token)
        now = datetime.now(timezone.utc)
        async with async_session_factory() as session:
            row = (
                await session.execute(
                    select(AuthSession).where(
                        AuthSession.session_token_hash == th,
                        AuthSession.revoked == False,  # noqa: E712
                    )
                )
            ).scalar_one_or_none()
            if not row:
                return None
            exp = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)
            if exp < now:
                return None
            user = (
                await session.execute(select(UserAccount).where(UserAccount.id == row.user_id))
            ).scalar_one_or_none()
            return user

    async def logout(self, session_token: str) -> bool:
        th = _hash_token(session_token)
        now = datetime.now(timezone.utc)
        async with async_session_factory() as session:
            row = (
                await session.execute(select(AuthSession).where(AuthSession.session_token_hash == th))
            ).scalar_one_or_none()
            if not row:
                return False
            row.revoked = True
            row.revoked_at = now
            await session.commit()
            return True

    async def logout_all(self, user_id: int) -> int:
        now = datetime.now(timezone.utc)
        async with async_session_factory() as session:
            rows = (
                await session.execute(
                    select(AuthSession).where(
                        AuthSession.user_id == user_id,
                        AuthSession.revoked == False,  # noqa: E712
                    )
                )
            ).scalars().all()
            for r in rows:
                r.revoked = True
                r.revoked_at = now
            await session.commit()
            return len(rows)

    async def request_password_reset(self, email: str) -> str | None:
        email = email.strip().lower()
        async with async_session_factory() as session:
            user = (
                await session.execute(select(UserAccount).where(UserAccount.email == email))
            ).scalar_one_or_none()
            if not user:
                return None
            raw = secrets.token_urlsafe(32)
            now = datetime.now(timezone.utc)
            session.add(
                AuthToken(
                    user_id=user.id,
                    email=email,
                    purpose="password_reset",
                    token_hash=_hash_token(raw),
                    expires_at=now + timedelta(hours=TOKEN_HOURS),
                    used=False,
                    created_at=now,
                )
            )
            await session.commit()
            return raw

    async def reset_password(self, token: str, new_password: str) -> bool:
        if len(new_password) < 8:
            raise ValueError("Password min 8 characters")
        th = _hash_token(token)
        now = datetime.now(timezone.utc)
        async with async_session_factory() as session:
            row = (
                await session.execute(
                    select(AuthToken).where(
                        AuthToken.token_hash == th,
                        AuthToken.purpose == "password_reset",
                        AuthToken.used == False,  # noqa: E712
                    )
                )
            ).scalar_one_or_none()
            if not row:
                return False
            exp = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)
            if exp < now:
                return False
            user = (
                await session.execute(select(UserAccount).where(UserAccount.id == row.user_id))
            ).scalar_one_or_none()
            if not user:
                return False
            pw_hash, salt = _hash_password(new_password)
            user.password_hash = pw_hash
            user.password_salt = salt
            user.updated_at = now
            row.used = True
            # revoke all sessions
            sessions = (
                await session.execute(
                    select(AuthSession).where(
                        AuthSession.user_id == user.id,
                        AuthSession.revoked == False,  # noqa: E712
                    )
                )
            ).scalars().all()
            for s in sessions:
                s.revoked = True
                s.revoked_at = now
            await session.commit()
            return True

    async def request_phone_otp(self, phone: str) -> str:
        phone = phone.strip()
        code = f"{secrets.randbelow(1_000_000):06d}"
        now = datetime.now(timezone.utc)
        async with async_session_factory() as session:
            session.add(
                AuthToken(
                    user_id=None,
                    phone=phone,
                    purpose="phone_otp",
                    token_hash=_hash_token(code),
                    expires_at=now + timedelta(minutes=OTP_MINUTES),
                    used=False,
                    created_at=now,
                )
            )
            await session.commit()
        # When Twilio SMS is configured, AlertService can send; always log in DEBUG.
        logger.info("Phone OTP for %s (deliver via SMS when configured)", phone)
        return code  # returned only so non-SMS envs can test; production should omit

    async def verify_phone_otp(self, phone: str, code: str, email: str | None = None) -> bool:
        th = _hash_token(code.strip())
        now = datetime.now(timezone.utc)
        async with async_session_factory() as session:
            row = (
                await session.execute(
                    select(AuthToken).where(
                        AuthToken.token_hash == th,
                        AuthToken.purpose == "phone_otp",
                        AuthToken.phone == phone.strip(),
                        AuthToken.used == False,  # noqa: E712
                    )
                )
            ).scalar_one_or_none()
            if not row:
                return False
            exp = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)
            if exp < now:
                return False
            row.used = True
            if email:
                user = (
                    await session.execute(
                        select(UserAccount).where(UserAccount.email == email.strip().lower())
                    )
                ).scalar_one_or_none()
                if user:
                    user.phone = phone.strip()
                    user.phone_verified = True
                    user.updated_at = now
            await session.commit()
            return True

    async def setup_2fa(self, user_id: int) -> dict:
        secret = new_totp_secret()
        async with async_session_factory() as session:
            user = (
                await session.execute(select(UserAccount).where(UserAccount.id == user_id))
            ).scalar_one_or_none()
            if not user:
                raise ValueError("User not found")
            user.totp_secret = secret
            user.totp_enabled = False  # enable after confirm
            user.updated_at = datetime.now(timezone.utc)
            await session.commit()
            email = user.email
        return {
            "totp_secret": secret,
            "otpauth_url": f"otpauth://totp/AEGIS:{email}?secret={secret}&issuer=LeverageFx",
            "message": "Scan with authenticator app, then POST /api/auth/2fa/enable with a code",
        }

    async def enable_2fa(self, user_id: int, code: str) -> bool:
        async with async_session_factory() as session:
            user = (
                await session.execute(select(UserAccount).where(UserAccount.id == user_id))
            ).scalar_one_or_none()
            if not user or not user.totp_secret:
                return False
            if not verify_totp(user.totp_secret, code):
                return False
            user.totp_enabled = True
            user.updated_at = datetime.now(timezone.utc)
            await session.commit()
            return True

    async def disable_2fa(self, user_id: int, password: str, code: str) -> bool:
        async with async_session_factory() as session:
            user = (
                await session.execute(select(UserAccount).where(UserAccount.id == user_id))
            ).scalar_one_or_none()
            if not user:
                return False
            if not _verify_password(password, user.password_hash, user.password_salt):
                return False
            if user.totp_enabled and (not user.totp_secret or not verify_totp(user.totp_secret, code)):
                return False
            user.totp_enabled = False
            user.totp_secret = None
            user.updated_at = datetime.now(timezone.utc)
            await session.commit()
            return True
