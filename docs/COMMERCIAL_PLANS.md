# Commercial plans (fintech-style)

| Plan | Devices | Trades / day | Live trading |
|------|---------|--------------|--------------|
| demo | 1 | 5 | No |
| starter | 1 | 15 | Yes |
| pro | 1 | 50 | Yes |
| business | 3 | 200 | Yes |
| enterprise | 10 | Unlimited | Yes |

Assign via Operator Console → **Tenants & plans** or:

`POST /api/admin/tenants/set-plan` `{ "account_id": "ACC-…", "plan": "business" }`

Device registration respects `max_devices`. Market orders respect daily trade quota (HTTP 429 when exceeded).

## Operator console tabs

Overview · Audit log · Tenants & plans · API keys · Devices · Downloads · Uploads · Alerts

## Alert channels

Email, Telegram, Slack, SMS (Twilio), **WhatsApp** (Twilio WhatsApp sandbox/number: `TWILIO_WHATSAPP_FROM`, `ALERT_WHATSAPP_TO` as `whatsapp:+E164`).
