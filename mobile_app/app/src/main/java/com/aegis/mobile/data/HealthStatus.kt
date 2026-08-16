package com.aegis.mobile.data

import android.graphics.Bitmap
import androidx.lifecycle.MutableLiveData
import java.util.ArrayDeque

/**
 * Observable diagnostics for the capture / upload loop.
 */
object HealthStatus {
    val lastCaptureTimeMs = MutableLiveData<Long>(0L)
    val lastCaptureSucceeded = MutableLiveData<Boolean>(true)
    val consecutiveFailures = MutableLiveData<Int>(0)
    val captureCount = MutableLiveData<Long>(0L)
    val mediaProjectionActive = MutableLiveData<Boolean>(false)
    val pendingCacheCount = MutableLiveData<Int>(0)

    val backendReachable = MutableLiveData<Boolean?>(null)
    val lastHttpCode = MutableLiveData<Int?>(null)
    val lastUploadStatus = MutableLiveData<String>("—")
    val lastUploadTimeMs = MutableLiveData<Long>(0L)
    val mt5Foreground = MutableLiveData<Boolean>(false)

    /** Downscaled last frame for UI "streaming" preview (main thread safe via LiveData). */
    val lastPreviewBitmap = MutableLiveData<Bitmap?>(null)
    val lastPreviewTimeMs = MutableLiveData<Long>(0L)

    /** Rolling local history (newest first), max 100. */
    data class UploadRecord(
        val timeMs: Long,
        val success: Boolean,
        val httpCode: Int?,
        val latencyMs: Long?,
        val status: String
    )

    private val uploadHistory = ArrayDeque<UploadRecord>(100)
    val uploadHistoryVersion = MutableLiveData(0)

    @Synchronized
    fun historySnapshot(): List<UploadRecord> = uploadHistory.toList()

    @Synchronized
    private fun pushHistory(rec: UploadRecord) {
        if (uploadHistory.size >= 100) uploadHistory.removeLast()
        uploadHistory.addFirst(rec)
        uploadHistoryVersion.postValue((uploadHistoryVersion.value ?: 0) + 1)
    }

    fun recordCaptureSuccess(httpCode: Int = 200, latencyMs: Long? = null) {
        val now = System.currentTimeMillis()
        lastCaptureTimeMs.postValue(now)
        lastCaptureSucceeded.postValue(true)
        consecutiveFailures.postValue(0)
        captureCount.postValue((captureCount.value ?: 0L) + 1)
        backendReachable.postValue(true)
        lastHttpCode.postValue(httpCode)
        lastUploadStatus.postValue("SUCCESS")
        lastUploadTimeMs.postValue(now)
        pushHistory(UploadRecord(now, true, httpCode, latencyMs, "SUCCESS"))
    }

    fun recordCaptureFailure(httpCode: Int? = null, networkError: Boolean = false, latencyMs: Long? = null) {
        val now = System.currentTimeMillis()
        lastCaptureSucceeded.postValue(false)
        consecutiveFailures.postValue((consecutiveFailures.value ?: 0) + 1)
        val status = if (networkError) "NETWORK" else "FAILED"
        lastUploadStatus.postValue(status)
        lastUploadTimeMs.postValue(now)
        if (httpCode != null) {
            lastHttpCode.postValue(httpCode)
            backendReachable.postValue(httpCode in 100..599)
        } else if (networkError) {
            lastHttpCode.postValue(null)
            backendReachable.postValue(false)
        }
        pushHistory(UploadRecord(now, false, httpCode, latencyMs, status))
    }

    fun recordSkippedNotMt5() {
        lastUploadStatus.postValue("SKIPPED (not MT5)")
    }

    fun recordBackendPing(ok: Boolean) {
        backendReachable.postValue(ok)
    }

    fun failureRateLast(n: Int = 20): Double {
        val snap = historySnapshot().take(n)
        if (snap.isEmpty()) return 0.0
        val fails = snap.count { !it.success }
        return fails.toDouble() / snap.size
    }

    fun avgLatencyLast(n: Int = 20): Long? {
        val vals = historySnapshot().take(n).mapNotNull { it.latencyMs }
        if (vals.isEmpty()) return null
        return vals.average().toLong()
    }

    fun publishPreview(source: Bitmap) {
        try {
            val maxW = 720
            val scale = if (source.width > maxW) maxW.toFloat() / source.width else 1f
            val w = (source.width * scale).toInt().coerceAtLeast(1)
            val h = (source.height * scale).toInt().coerceAtLeast(1)
            val copy = Bitmap.createScaledBitmap(source, w, h, true)
            lastPreviewBitmap.postValue(copy)
            lastPreviewTimeMs.postValue(System.currentTimeMillis())
        } catch (_: Exception) {
        }
    }
}
