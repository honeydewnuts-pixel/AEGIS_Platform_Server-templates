from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # Render and most hosts inject env vars in UPPER_SNAKE_CASE.
        # Extra keys are ignored so unknown Render vars do not crash startup.
        extra="ignore",
        case_sensitive=False,
    )

    APP_NAME: str = "AEGIS"
    APP_VERSION: str = "3.1.0"
    APP_DESCRIPTION: str = (
        "Autonomous Enterprise Global Intelligence System"
    )

    API_PREFIX: str = "/api"

    DEBUG: bool = False

    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Security
    SECRET_KEY: str = "CHANGE_THIS_TO_A_RANDOM_SECRET_KEY"
    # Set this in Render Environment. On first boot (or when
    # FORCE_ADMIN_KEY_RESET=true) this value becomes the admin API key.
    ADMIN_BOOTSTRAP_KEY: str = ""
    # When true, revoke existing admin keys and re-register ADMIN_BOOTSTRAP_KEY.
    # Use once after losing the original key, then set back to false.
    FORCE_ADMIN_KEY_RESET: bool = False
    # Base64-encoded 32-byte key for broker credential encryption at rest.
    AEGIS_MASTER_KEY: str = ""

    ALLOWED_ORIGINS: str = "http://localhost:3000"
    PORTAL_BASE_URL: str = "http://localhost:8000/portal"

    # Render injects these via blueprint fromDatabase / fromService.
    DATABASE_URL: str = "postgresql://postgres:postgres@postgres:5432/aegis"
    REDIS_URL: str = "redis://redis:6379/0"

    # Worker pool — default 100 concurrent account workers on one host.
    # For hundreds of thousands of accounts, run remote Windows worker fleets
    # against the same Redis (see WorkerPoolManager module docstring).
    WORKER_IDLE_TIMEOUT_SECONDS: int = 900
    WORKER_JOB_TIMEOUT_SECONDS: int = 30
    MAX_CONCURRENT_WORKERS: int = 100

    # API key lifecycle (0 = never expire / no scheduled rotation)
    API_KEY_DEFAULT_TTL_DAYS: int = 365
    API_KEY_ROTATION_DAYS: int = 90
    API_RATE_LIMIT_PER_MINUTE: int = 120
    AUDIT_RETENTION_DAYS: int = 90


    # Multi-channel alerts (all optional)
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""
    SMTP_TLS: bool = True
    ALERT_EMAIL_TO: str = ""
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""
    SLACK_WEBHOOK_URL: str = ""
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_FROM_NUMBER: str = ""
    ALERT_SMS_TO: str = ""
    # WhatsApp via Twilio WhatsApp-enabled number (whatsapp:+E164)
    TWILIO_WHATSAPP_FROM: str = ""
    ALERT_WHATSAPP_TO: str = ""


    # Payment providers
    PAYSTACK_SECRET_KEY: str = ""
    FLUTTERWAVE_SECRET_KEY: str = ""
    FLUTTERWAVE_WEBHOOK_HASH: str = ""
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""

    # Subscription enforcement
    SUBSCRIPTION_GRACE_PERIOD_DAYS: int = 5
    SUBSCRIPTION_SWEEP_INTERVAL_SECONDS: int = 300
    APK_FILE_PATH: str = "release/aegis-mobile.apk"
    DOWNLOAD_TOKEN_TTL_SECONDS: int = 3600

    # Tracing
    TRACING_ENABLED: bool = False
    OTLP_ENDPOINT: str = "tempo:4317"


settings = Settings()


def get_allowed_origins() -> list[str]:
    return [o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()]
