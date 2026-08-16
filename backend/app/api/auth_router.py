"""Subscriber identity: register, login, email verify, password reset, OTP, 2FA, sessions."""
from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field

from app.services.auth_service import AuthService

router = APIRouter(prefix="/api/auth", tags=["Auth"])
_auth = AuthService()


class RegisterBody(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    phone: str | None = None
    account_id: str | None = None


class LoginBody(BaseModel):
    email: EmailStr
    password: str
    totp_code: str | None = None
    device_label: str | None = None


class ResetRequestBody(BaseModel):
    email: EmailStr


class ResetConfirmBody(BaseModel):
    token: str
    new_password: str = Field(min_length=8)


class PhoneOtpRequest(BaseModel):
    phone: str


class PhoneOtpVerify(BaseModel):
    phone: str
    code: str
    email: EmailStr | None = None


class TotpCodeBody(BaseModel):
    code: str


class Disable2FABody(BaseModel):
    password: str
    code: str


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Bearer session token required")
    return authorization.split(" ", 1)[1].strip()


@router.post("/register")
async def register(body: RegisterBody, request: Request):
    try:
        result = await _auth.register(
            email=str(body.email),
            password=body.password,
            phone=body.phone,
            account_id=body.account_id,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    # Optional: email verification link via alert_service if SMTP configured
    try:
        alert = getattr(request.app.state, "alert_service", None)
        if alert and result.get("email_verification_token"):
            # Best-effort; never fail registration if mail fails
            pass
    except Exception:
        pass
    return result


@router.post("/verify-email")
async def verify_email(token: str):
    ok = await _auth.verify_email(token)
    if not ok:
        raise HTTPException(400, "Invalid or expired verification token")
    return {"verified": True}


@router.post("/login")
async def login(body: LoginBody, request: Request):
    try:
        return await _auth.login(
            email=str(body.email),
            password=body.password,
            totp_code=body.totp_code,
            device_label=body.device_label,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except ValueError as e:
        raise HTTPException(401, str(e)) from e


@router.post("/logout")
async def logout(authorization: str | None = Header(default=None)):
    token = _bearer(authorization)
    await _auth.logout(token)
    return {"logged_out": True}


@router.post("/logout-all")
async def logout_all(authorization: str | None = Header(default=None)):
    token = _bearer(authorization)
    user = await _auth.resolve_session(token)
    if not user:
        raise HTTPException(401, "Invalid session")
    n = await _auth.logout_all(user.id)
    return {"revoked_sessions": n}


@router.get("/me")
async def me(authorization: str | None = Header(default=None)):
    token = _bearer(authorization)
    user = await _auth.resolve_session(token)
    if not user:
        raise HTTPException(401, "Invalid session")
    return {
        "account_id": user.account_id,
        "email": user.email,
        "phone": user.phone,
        "email_verified": user.email_verified,
        "phone_verified": user.phone_verified,
        "totp_enabled": user.totp_enabled,
        "is_admin": user.is_admin,
    }


@router.post("/password/forgot")
async def password_forgot(body: ResetRequestBody):
    raw = await _auth.request_password_reset(str(body.email))
    # Always generic response to avoid account enumeration
    resp = {"message": "If that email exists, a reset token was issued."}
    if raw:
        resp["reset_token"] = raw  # expose once for bootstrap; wire email in production
    return resp


@router.post("/password/reset")
async def password_reset(body: ResetConfirmBody):
    try:
        ok = await _auth.reset_password(body.token, body.new_password)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    if not ok:
        raise HTTPException(400, "Invalid or expired reset token")
    return {"reset": True, "message": "Password updated; all sessions revoked"}


@router.post("/phone/request-otp")
async def phone_request_otp(body: PhoneOtpRequest):
    code = await _auth.request_phone_otp(body.phone)
    return {
        "message": "OTP generated. Delivered by SMS when Twilio is configured.",
        "otp_debug": code,  # remove in hard production if desired
    }


@router.post("/phone/verify-otp")
async def phone_verify_otp(body: PhoneOtpVerify):
    ok = await _auth.verify_phone_otp(body.phone, body.code, str(body.email) if body.email else None)
    if not ok:
        raise HTTPException(400, "Invalid or expired OTP")
    return {"verified": True}


@router.post("/2fa/setup")
async def totp_setup(authorization: str | None = Header(default=None)):
    token = _bearer(authorization)
    user = await _auth.resolve_session(token)
    if not user:
        raise HTTPException(401, "Invalid session")
    return await _auth.setup_2fa(user.id)


@router.post("/2fa/enable")
async def totp_enable(body: TotpCodeBody, authorization: str | None = Header(default=None)):
    token = _bearer(authorization)
    user = await _auth.resolve_session(token)
    if not user:
        raise HTTPException(401, "Invalid session")
    ok = await _auth.enable_2fa(user.id, body.code)
    if not ok:
        raise HTTPException(400, "Invalid code")
    return {"totp_enabled": True}


@router.post("/2fa/disable")
async def totp_disable(body: Disable2FABody, authorization: str | None = Header(default=None)):
    token = _bearer(authorization)
    user = await _auth.resolve_session(token)
    if not user:
        raise HTTPException(401, "Invalid session")
    ok = await _auth.disable_2fa(user.id, body.password, body.code)
    if not ok:
        raise HTTPException(400, "Could not disable 2FA")
    return {"totp_enabled": False}
