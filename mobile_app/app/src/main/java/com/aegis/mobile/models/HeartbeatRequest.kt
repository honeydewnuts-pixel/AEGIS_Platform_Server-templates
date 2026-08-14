package com.aegis.mobile.models

data class HeartbeatRequest(
    val accountId: String,
    val batteryPercent: Int,
    val isCharging: Boolean,
    val lastCaptureTimeMs: Long,
    val lastCaptureSucceeded: Boolean,
    val consecutiveFailures: Int,
    val captureCount: Long,
    val mediaProjectionActive: Boolean,
    val batteryOptimizationExempt: Boolean,
    val cachedScreenshotCount: Int,
    val appVersion: String
)
