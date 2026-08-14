from pydantic import BaseModel, Field


class HeartbeatRequest(BaseModel):
    account_id: str = Field(..., alias="accountId")
    battery_percent: int = Field(..., alias="batteryPercent")
    is_charging: bool = Field(..., alias="isCharging")
    last_capture_time_ms: int = Field(..., alias="lastCaptureTimeMs")
    last_capture_succeeded: bool = Field(..., alias="lastCaptureSucceeded")
    consecutive_failures: int = Field(..., alias="consecutiveFailures")
    capture_count: int = Field(..., alias="captureCount")
    media_projection_active: bool = Field(..., alias="mediaProjectionActive")
    battery_optimization_exempt: bool = Field(..., alias="batteryOptimizationExempt")
    cached_screenshot_count: int = Field(..., alias="cachedScreenshotCount")
    app_version: str = Field(..., alias="appVersion")

    class Config:
        populate_by_name = True
