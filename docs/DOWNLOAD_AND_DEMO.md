# APK distribution, device binding, demo vs live

## Website download (subscribers only)

1. After payment webhook activation (or admin action), issue a token:
   `POST /api/download/token` with admin key → `{ download_url, token }`.
2. Show `download_url` only on the authenticated success page / email.
3. `GET /api/download/apk?token=…` consumes the token (default **1 use**).
4. Without a valid token → **403** (no public APK).

## One phone per subscription

1. App calls `POST /api/devices/register` with `account_id` + `ANDROID_ID` on launch.
2. First device is stored in `device_bindings`.
3. Second device → **403** until admin `DELETE /api/devices/binding/{account_id}`.

## Demo plan

`POST /api/subscriptions/demo/signup` (public):

- Creates `plan=demo`, status active, ~14 days
- Issues mobile API key + portal token + **one-time download URL**
- Brain / screenshot analysis allowed
- **Live market orders blocked** (`allows_live_trading` is false)
- Device binding still applies

Upgrade path: paid checkout moves plan to `live`.

## Alerts

Configure any of: SMTP_*, TELEGRAM_*, SLACK_WEBHOOK_URL, TWILIO_*, ALERT_EMAIL_TO, ALERT_SMS_TO.  
Test from admin UI or `POST /api/admin/alerts/test`.
