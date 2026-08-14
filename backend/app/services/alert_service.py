"""
Multi-channel ops alerts: email, Telegram, Slack, SMS (Twilio).
All channels are optional — missing credentials skip that channel.
"""

from __future__ import annotations

import logging
from email.message import EmailMessage
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger("AEGIS.alerts")


class AlertService:
    async def send(
        self,
        subject: str,
        body: str,
        *,
        severity: str = "info",
        channels: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        channels: subset of email|telegram|slack|sms — default all configured.
        """
        wanted = set(c.lower() for c in (channels or ["email", "telegram", "slack", "sms", "whatsapp"]))
        results: dict[str, Any] = {}
        text = f"[{severity.upper()}] {subject}\n\n{body}"

        if "email" in wanted:
            results["email"] = await self._email(subject, text)
        if "telegram" in wanted:
            results["telegram"] = await self._telegram(text)
        if "slack" in wanted:
            results["slack"] = await self._slack(text)
        if "sms" in wanted:
            results["sms"] = await self._sms(f"{subject}: {body[:120]}")
        if "whatsapp" in wanted:
            results["whatsapp"] = await self._whatsapp(f"{subject}: {body[:800]}")
        return results

    async def _email(self, subject: str, body: str) -> str:
        host = settings.SMTP_HOST
        if not host or not settings.ALERT_EMAIL_TO:
            return "skipped"
        try:
            import aiosmtplib

            msg = EmailMessage()
            msg["From"] = settings.SMTP_FROM or settings.ALERT_EMAIL_TO
            msg["To"] = settings.ALERT_EMAIL_TO
            msg["Subject"] = f"[AEGIS] {subject}"
            msg.set_content(body)
            await aiosmtplib.send(
                msg,
                hostname=host,
                port=settings.SMTP_PORT,
                username=settings.SMTP_USER or None,
                password=settings.SMTP_PASSWORD or None,
                start_tls=settings.SMTP_TLS,
            )
            return "sent"
        except Exception as exc:  # noqa: BLE001
            logger.exception("email alert failed")
            return f"error:{exc}"

    async def _telegram(self, text: str) -> str:
        token = settings.TELEGRAM_BOT_TOKEN
        chat = settings.TELEGRAM_CHAT_ID
        if not token or not chat:
            return "skipped"
        try:
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.post(url, json={"chat_id": chat, "text": text[:4000]})
            return "sent" if r.is_success else f"error:{r.status_code}"
        except Exception as exc:  # noqa: BLE001
            logger.exception("telegram alert failed")
            return f"error:{exc}"

    async def _slack(self, text: str) -> str:
        url = settings.SLACK_WEBHOOK_URL
        if not url:
            return "skipped"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.post(url, json={"text": text[:3000]})
            return "sent" if r.is_success else f"error:{r.status_code}"
        except Exception as exc:  # noqa: BLE001
            logger.exception("slack alert failed")
            return f"error:{exc}"

    async def _sms(self, text: str) -> str:
        sid = settings.TWILIO_ACCOUNT_SID
        token = settings.TWILIO_AUTH_TOKEN
        from_n = settings.TWILIO_FROM_NUMBER
        to_n = settings.ALERT_SMS_TO
        if not all([sid, token, from_n, to_n]):
            return "skipped"
        try:
            url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.post(
                    url,
                    data={"From": from_n, "To": to_n, "Body": text[:300]},
                    auth=(sid, token),
                )
            return "sent" if r.is_success else f"error:{r.status_code}"
        except Exception as exc:  # noqa: BLE001
            logger.exception("sms alert failed")
            return f"error:{exc}"

    async def _whatsapp(self, text: str) -> str:
        """Twilio WhatsApp channel (From/To must be whatsapp:+E164)."""
        sid = settings.TWILIO_ACCOUNT_SID
        token = settings.TWILIO_AUTH_TOKEN
        from_n = settings.TWILIO_WHATSAPP_FROM or ""
        to_n = settings.ALERT_WHATSAPP_TO or ""
        if not all([sid, token, from_n, to_n]):
            return "skipped"
        if not from_n.startswith("whatsapp:"):
            from_n = "whatsapp:" + from_n
        if not to_n.startswith("whatsapp:"):
            to_n = "whatsapp:" + to_n
        try:
            url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.post(
                    url,
                    data={"From": from_n, "To": to_n, "Body": text[:1500]},
                    auth=(sid, token),
                )
            return "sent" if r.is_success else f"error:{r.status_code}"
        except Exception as exc:  # noqa: BLE001
            logger.exception("whatsapp alert failed")
            return f"error:{exc}"
