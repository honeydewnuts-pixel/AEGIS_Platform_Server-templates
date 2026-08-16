package com.aegis.mobile.capture

import android.Manifest
import android.annotation.SuppressLint
import android.app.*
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.PixelFormat
import android.hardware.display.DisplayManager
import android.hardware.display.VirtualDisplay
import android.media.ImageReader
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.BatteryManager
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.os.PowerManager
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import com.aegis.mobile.R
import com.aegis.mobile.data.HealthStatus
import com.aegis.mobile.data.PrefKeys
import com.aegis.mobile.data.SignalRepository
import com.aegis.mobile.data.dataStore
import com.aegis.mobile.models.AnalysisResponse
import com.aegis.mobile.models.HeartbeatRequest
import com.aegis.mobile.network.RetrofitClient
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.first
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.RequestBody
import okhttp3.RequestBody.Companion.asRequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.File
import java.io.FileOutputStream

class ScreenCaptureService : Service() {

    private lateinit var mediaProjectionManager: MediaProjectionManager
    private var mediaProjection: MediaProjection? = null
    private var virtualDisplay: VirtualDisplay? = null
    private var imageReader: ImageReader? = null
    private val handler = Handler(Looper.getMainLooper())
    private val scope = CoroutineScope(Dispatchers.IO)
    private lateinit var apiService: com.aegis.mobile.network.ApiService
    private lateinit var powerManager: PowerManager
    private var wakeLock: PowerManager.WakeLock? = null
    private lateinit var cacheManager: ScreenshotCacheManager

    // Defaults to "no crop" (send the full frame) until a real ROI is
    // fetched - safe fallback if the config endpoint is unreachable, since
    // sending too much is a bandwidth cost, sending too little could crop
    // off real chart data the brain needs.
    @Volatile private var captureTopPercent: Float = 0.06f
    @Volatile private var captureBottomPercent: Float = 0.88f

    companion object {
        const val EXTRA_RESULT_CODE = "result_code"
        const val EXTRA_RESULT_DATA = "result_data"
        const val ACTION_STOP = "com.aegis.mobile.STOP_CAPTURE"
        const val ACTION_START = "com.aegis.mobile.START_CAPTURE"
        private const val NOTIF_ID = 1001
        private const val CAPTURE_INTERVAL = 3000L      // 3 seconds
        private const val HEARTBEAT_INTERVAL = 60000L   // 1 minute - independent of the capture loop
        private const val CACHE_DRAIN_INTERVAL = 15000L // how often we try to flush the offline backlog
        private const val MAX_DRAIN_PER_CYCLE = 5        // catch up gradually, not in one burst, after reconnecting
        private const val ROI_REFRESH_INTERVAL = 6 * 60 * 60 * 1000L  // 6 hours - config rarely changes
        private const val WAKELOCK_TIMEOUT_MS = 10000L  // safety cap so a stuck capture can't hold the lock forever
    }

    override fun onCreate() {
        super.onCreate()
        apiService = RetrofitClient.getApiService(this)
        mediaProjectionManager = getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
        powerManager = getSystemService(Context.POWER_SERVICE) as PowerManager
        cacheManager = ScreenshotCacheManager(this)
        startForeground(NOTIF_ID, buildNotification("Starting..."))
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        // Explicit stop from the UI — do not restart.
        if (intent?.action == ACTION_STOP) {
            Log.i("AEGIS", "Stop capture requested")
            stopCaptureSession()
            stopForeground(STOP_FOREGROUND_REMOVE)
            stopSelf()
            return START_NOT_STICKY
        }

        val resultCode = intent?.getIntExtra(EXTRA_RESULT_CODE, 0) ?: 0
        val resultData = intent?.getParcelableExtra<Intent>(EXTRA_RESULT_DATA)
        if (resultData == null || resultCode == 0) {
            // System may restart a sticky service without the MediaProjection token.
            // We cannot capture without a fresh user grant — shut down cleanly.
            Log.w("AEGIS", "No MediaProjection token; not restarting capture")
            HealthStatus.mediaProjectionActive.postValue(false)
            stopSelf()
            return START_NOT_STICKY
        }

        // If already running, ignore duplicate start intents.
        if (mediaProjection != null && HealthStatus.mediaProjectionActive.value == true) {
            Log.i("AEGIS", "Capture already active")
            return START_NOT_STICKY
        }

        mediaProjection = mediaProjectionManager.getMediaProjection(resultCode, resultData)
        mediaProjection?.registerCallback(object : MediaProjection.Callback() {
            override fun onStop() {
                Log.w("AEGIS", "MediaProjection stopped by system/user")
                handler.post {
                    stopCaptureSession()
                    stopForeground(STOP_FOREGROUND_REMOVE)
                    stopSelf()
                }
            }
        }, handler)

        HealthStatus.mediaProjectionActive.postValue(true)
        setupVirtualDisplay()
        scope.launch { refreshCaptureRoi() }
        handler.removeCallbacks(captureRunnable)
        handler.removeCallbacks(heartbeatRunnable)
        handler.removeCallbacks(cacheDrainRunnable)
        handler.removeCallbacks(roiRefreshRunnable)
        handler.postDelayed(captureRunnable, CAPTURE_INTERVAL)
        handler.postDelayed(heartbeatRunnable, HEARTBEAT_INTERVAL)
        handler.postDelayed(cacheDrainRunnable, CACHE_DRAIN_INTERVAL)
        handler.postDelayed(roiRefreshRunnable, ROI_REFRESH_INTERVAL)
        updateNotification("Capturing MT5 chart region")
        acquireServiceWakeLock()
        // NOT sticky: prevents auto-restart without a valid projection token (which
        // made Stop appear to "restart" capture and left the UI inconsistent).
        return START_NOT_STICKY
    }

    private fun acquireServiceWakeLock() {
        try {
            if (wakeLock == null) {
                wakeLock = powerManager.newWakeLock(
                    PowerManager.PARTIAL_WAKE_LOCK,
                    "AEGIS::ServiceAlive"
                )
            }
            if (wakeLock?.isHeld != true) {
                @Suppress("DEPRECATION")
                wakeLock?.acquire()
            }
        } catch (_: Exception) {
        }
    }

    private fun stopCaptureSession() {
        handler.removeCallbacks(captureRunnable)
        handler.removeCallbacks(heartbeatRunnable)
        handler.removeCallbacks(cacheDrainRunnable)
        handler.removeCallbacks(roiRefreshRunnable)
        try { virtualDisplay?.release() } catch (_: Exception) {}
        virtualDisplay = null
        try { mediaProjection?.stop() } catch (_: Exception) {}
        mediaProjection = null
        try { imageReader?.close() } catch (_: Exception) {}
        imageReader = null
        if (wakeLock?.isHeld == true) {
            try { wakeLock?.release() } catch (_: Exception) {}
        }
        HealthStatus.mediaProjectionActive.postValue(false)
        Log.i("AEGIS", "Capture session cleaned up")
    }

    private fun setupVirtualDisplay() {
        val metrics = resources.displayMetrics
        imageReader = ImageReader.newInstance(metrics.widthPixels, metrics.heightPixels, PixelFormat.RGBA_8888, 2)

        virtualDisplay = mediaProjection?.createVirtualDisplay(
            "AEGIS_ScreenCapture",
            metrics.widthPixels, metrics.heightPixels, metrics.densityDpi,
            DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
            imageReader?.surface, null, null
        )
    }

    private val captureRunnable = object : Runnable {
        override fun run() {
            captureAndSend()
            handler.postDelayed(this, CAPTURE_INTERVAL)
        }
    }

    private val heartbeatRunnable = object : Runnable {
        override fun run() {
            scope.launch { sendHeartbeat() }
            handler.postDelayed(this, HEARTBEAT_INTERVAL)
        }
    }

    private val cacheDrainRunnable = object : Runnable {
        override fun run() {
            scope.launch { drainCache() }
            handler.postDelayed(this, CACHE_DRAIN_INTERVAL)
        }
    }

    private val roiRefreshRunnable = object : Runnable {
        override fun run() {
            scope.launch { refreshCaptureRoi() }
            handler.postDelayed(this, ROI_REFRESH_INTERVAL)
        }
    }

    /**
     * Fetches the capture crop bounds from the backend (single source of
     * truth: colors_config.json's roi section) rather than hardcoding a
     * copy in the app - so tightening the crop later is a config change,
     * not an app update. Failure here just keeps whatever bounds were
     * already in memory (defaults to "no crop" on first-ever failure) -
     * capture must never block or fail because this fetch failed.
     */
    private suspend fun refreshCaptureRoi() {
        try {
            val response = apiService.getCaptureRoi()
            if (response.isSuccessful) {
                response.body()?.let {
                    captureTopPercent = it.captureTopPercent
                    captureBottomPercent = it.captureBottomPercent
                    Log.d("AEGIS", "Capture ROI updated: $captureTopPercent - $captureBottomPercent")
                }
            }
        } catch (e: Exception) {
            Log.w("AEGIS", "Could not refresh capture ROI, keeping previous bounds: ${e.message}")
        }
    }

    /**
     * Sends cached (previously failed) screenshots oldest-first, stopping
     * as soon as one fails (still offline - try again next cycle) rather
     * than burning through retries against a backend that's still down.
     * Drains a bounded batch per cycle so a large backlog catches up
     * gradually instead of hammering the network the instant it returns.
     */
    private suspend fun drainCache() {
        val pending = cacheManager.listPendingOldestFirst()
        if (pending.isEmpty()) return

        for (file in pending.take(MAX_DRAIN_PER_CYCLE)) {
            val parsed = cacheManager.parse(file)
            if (parsed == null) {
                cacheManager.remove(file)  // malformed filename - can't recover this one, drop it
                continue
            }
            val (capturedAtMs, accountId) = parsed
            val sent = trySend(file, accountId, capturedAtMs)
            if (sent) {
                cacheManager.remove(file)
                HealthStatus.pendingCacheCount.postValue(cacheManager.pendingCount())
            } else {
                break  // still offline - stop draining, try again next cycle
            }
        }
    }

    /**
     * Held only for the duration of one capture-and-encode cycle, then released
     * immediately - not a continuous lock. This just protects against the CPU
     * suspending mid-capture on aggressive power-saving devices; it deliberately
     * does not try to keep the whole app "awake" between cycles, since that would
     * defeat the point of a wakelock and drain the battery for no benefit.
     */
    private fun withBriefWakeLock(block: () -> Unit) {
        if (wakeLock == null) {
            wakeLock = powerManager.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "AEGIS::CaptureLock")
        }
        try {
            wakeLock?.acquire(WAKELOCK_TIMEOUT_MS)
            block()
        } finally {
            if (wakeLock?.isHeld == true) wakeLock?.release()
        }
    }

    private fun captureAndSend() {
        val mt5Fg = com.aegis.mobile.automation.Mt5AccessibilityService.isMt5Foreground
        HealthStatus.mt5Foreground.postValue(mt5Fg)
        updateNotification(
            if (mt5Fg) "Capturing MT5 chart region"
            else "Capturing chart ROI — keep MT5 visible under HUD"
        )

        // Hide operator overlay so it is not painted into the frame sent to the brain.
        try {
            startService(Intent(this, com.aegis.mobile.ui.FloatingHudService::class.java).apply {
                action = com.aegis.mobile.ui.FloatingHudService.ACTION_CAPTURE_HIDE
            })
            Thread.sleep(40)
        } catch (_: Exception) {
        }

        withBriefWakeLock {
            val image = imageReader?.acquireLatestImage()
            if (image == null) {
                HealthStatus.recordCaptureFailure(networkError = false)
                return@withBriefWakeLock
            }
            val capturedAtMs = System.currentTimeMillis()
            val planes = image.planes
            val buffer = planes[0].buffer
            val pixelStride = planes[0].pixelStride
            val rowStride = planes[0].rowStride
            val rowPadding = rowStride - pixelStride * image.width

            val bitmap = Bitmap.createBitmap(
                image.width + rowPadding / pixelStride,
                image.height,
                Bitmap.Config.ARGB_8888
            )
            bitmap.copyPixelsFromBuffer(buffer)
            image.close()

            val croppedBitmap = applyRoiCrop(bitmap)
            HealthStatus.publishPreview(croppedBitmap)

            scope.launch {
                val accountId = resolveAccountId()
                val tempFile = File(cacheDir, "live_capture_tmp.jpg")
                FileOutputStream(tempFile).use { out ->
                    croppedBitmap.compress(Bitmap.CompressFormat.JPEG, 80, out)
                }

                val sent = trySend(tempFile, accountId, capturedAtMs)
                if (!sent) {
                    // Backend unreachable - queue it instead of losing it. The
                    // drain loop will retry this (in correct chronological
                    // order relative to other cached frames) once connectivity
                    // returns.
                    cacheManager.cache(croppedBitmap, capturedAtMs, accountId)
                    HealthStatus.pendingCacheCount.postValue(cacheManager.pendingCount())
                    updateNotification("Offline - ${cacheManager.pendingCount()} screenshots queued")
                }
                tempFile.delete()
            }
        }
        try {
            startService(Intent(this, com.aegis.mobile.ui.FloatingHudService::class.java).apply {
                action = com.aegis.mobile.ui.FloatingHudService.ACTION_CAPTURE_SHOW
            })
        } catch (_: Exception) {
        }
    }

    /**
     * Crops out anything above captureTopPercent or below captureBottomPercent
     * (status bar, MT5 toolbar chrome, nav bar - whatever isn't part of the
     * price/indicator panels). Currently a no-op with the default 0.0/1.0
     * bounds until colors_config.json's roi values are tightened based on a
     * real device measurement - see refreshCaptureRoi() and
     * app/api/config_router.py on the backend for where these come from.
     */
    private fun applyRoiCrop(bitmap: Bitmap): Bitmap {
        if (captureTopPercent <= 0.0f && captureBottomPercent >= 1.0f) {
            return bitmap  // no-op fast path - avoids an unnecessary copy when there's nothing to crop
        }
        val top = (bitmap.height * captureTopPercent).toInt().coerceIn(0, bitmap.height - 1)
        val bottom = (bitmap.height * captureBottomPercent).toInt().coerceIn(top + 1, bitmap.height)
        return Bitmap.createBitmap(bitmap, 0, top, bitmap.width, bottom - top)
    }

    /**
     * Shared send path for both live captures and replayed cached ones.
     * One quick retry on transient failures (Render cold start, brief
     * network blip). Persistent errors fall through to the offline cache.
     */
    private suspend fun trySend(file: File, accountId: String, capturedAtMs: Long): Boolean {
        repeat(2) { attempt ->
            val ok = trySendOnce(file, accountId, capturedAtMs)
            if (ok) return true
            if (attempt == 0) {
                delay(2_500)
            }
        }
        return false
    }

    private suspend fun trySendOnce(file: File, accountId: String, capturedAtMs: Long): Boolean {
        val t0 = System.currentTimeMillis()
        return try {
            val requestFile = file.asRequestBody("image/jpeg".toMediaTypeOrNull())
            // Explicit filename + content type helps proxies that strip part headers.
            val body = MultipartBody.Part.createFormData("image", "capture.jpg", requestFile)
            val accountIdBody: RequestBody = accountId.toRequestBody("text/plain".toMediaTypeOrNull())
            val capturedAtBody: RequestBody = capturedAtMs.toString().toRequestBody("text/plain".toMediaTypeOrNull())

            val response = apiService.analyzeScreenshot(body, accountIdBody, capturedAtBody)
            if (response.isSuccessful) {
                val result: AnalysisResponse? = response.body()
                Log.d("AEGIS", "Brain Response: ${result?.signal} - ${result?.confidence}")
                result?.let {
                    SignalRepository.latestResult.postValue(it)
                    SignalRepository.latestSignal.postValue(it.signal)
                }
                HealthStatus.recordCaptureSuccess(httpCode = response.code(), latencyMs = System.currentTimeMillis() - t0)
                val pending = cacheManager.pendingCount()
                val suffix = if (pending > 0) " ($pending queued)" else ""
                updateNotification("Last signal: ${result?.signal ?: "HOLD"} @ ${timeNow()}$suffix")
                true
            } else {
                val errBody = try {
                    response.errorBody()?.string()?.take(500)
                } catch (_: Exception) {
                    null
                }
                Log.e("AEGIS", "Brain Error: ${response.code()} body=${errBody ?: "(empty)"}")
                HealthStatus.recordCaptureFailure(httpCode = response.code(), networkError = false, latencyMs = System.currentTimeMillis() - t0)
                false
            }
        } catch (e: Exception) {
            Log.e("AEGIS", "Send failed: ${e.javaClass.simpleName}: ${e.message}")
            HealthStatus.recordCaptureFailure(httpCode = null, networkError = true, latencyMs = System.currentTimeMillis() - t0)
            false
        }
    }

    private suspend fun resolveAccountId(): String {
        val storedAccountId = applicationContext.dataStore.data.first()[PrefKeys.ACCOUNT_ID]
        return storedAccountId?.takeIf { it.isNotBlank() }
            ?: android.provider.Settings.Secure.getString(contentResolver, android.provider.Settings.Secure.ANDROID_ID)
    }

    private suspend fun sendHeartbeat() {
        try {
            val batteryManager = getSystemService(Context.BATTERY_SERVICE) as BatteryManager
            val batteryPercent = batteryManager.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY)
            val isCharging = batteryManager.getIntProperty(BatteryManager.BATTERY_PROPERTY_STATUS) ==
                BatteryManager.BATTERY_STATUS_CHARGING

            val exempt = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                powerManager.isIgnoringBatteryOptimizations(packageName)
            } else true

            val heartbeat = HeartbeatRequest(
                accountId = resolveAccountId(),
                batteryPercent = batteryPercent,
                isCharging = isCharging,
                lastCaptureTimeMs = HealthStatus.lastCaptureTimeMs.value ?: 0L,
                lastCaptureSucceeded = HealthStatus.lastCaptureSucceeded.value ?: true,
                consecutiveFailures = HealthStatus.consecutiveFailures.value ?: 0,
                captureCount = HealthStatus.captureCount.value ?: 0L,
                mediaProjectionActive = HealthStatus.mediaProjectionActive.value ?: false,
                batteryOptimizationExempt = exempt,
                cachedScreenshotCount = cacheManager.pendingCount(),
                appVersion = "3.0.0"
            )
            apiService.sendHeartbeat(heartbeat)
        } catch (e: Exception) {
            Log.e("AEGIS", "Heartbeat failed: ${e.message}")
        }
    }

    private fun timeNow(): String {
        val sdf = java.text.SimpleDateFormat("HH:mm:ss", java.util.Locale.getDefault())
        return sdf.format(java.util.Date())
    }

    private fun buildNotification(status: String): Notification {
        val channel = NotificationChannel("aegis_service", "AEGIS Service", NotificationManager.IMPORTANCE_LOW)
        getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
        return NotificationCompat.Builder(this, "aegis_service")
            .setContentTitle("AEGIS Active")
            .setContentText(status)
            .setSmallIcon(android.R.drawable.ic_menu_camera)
            .setOngoing(true)
            .build()
    }

    /**
     * On Android 13+ (TIRAMISU), posting a notification requires the runtime
     * POST_NOTIFICATIONS permission. This only guards the *ongoing status update*
     * notify() calls used to refresh the existing foreground notification's text
     * (e.g. "Last signal: BUY @ 10:02:31") - it does not affect startForeground()
     * in onCreate(), which the OS allows regardless so the foreground service
     * itself can still run even if the user never grants notification access.
     * If the permission isn't granted, we simply skip the update rather than
     * crash or spam SecurityExceptions - the service keeps working either way,
     * the user just won't see live status text in the notification shade.
     */
    @SuppressLint("NotificationPermission")
    private fun updateNotification(status: String) {
        val hasPermission = Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU ||
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) ==
                PackageManager.PERMISSION_GRANTED

        if (hasPermission) {
            val manager = getSystemService(NotificationManager::class.java)
            manager.notify(NOTIF_ID, buildNotification(status))
        }
    }

    override fun onDestroy() {
        stopCaptureSession()
        scope.cancel()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null
}
