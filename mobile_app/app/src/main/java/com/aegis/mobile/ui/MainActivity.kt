package com.aegis.mobile.ui

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.media.projection.MediaProjectionManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.PowerManager
import android.provider.Settings
import android.widget.Button
import android.widget.ImageView
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.lifecycleScope
import com.aegis.mobile.R
import com.aegis.mobile.automation.Mt5AccessibilityService
import com.aegis.mobile.capture.ScreenCaptureService
import com.aegis.mobile.data.DEFAULT_BROKER_NAME
import com.aegis.mobile.data.DEFAULT_MIN_CONFIDENCE
import com.aegis.mobile.data.HealthStatus
import com.aegis.mobile.data.PrefKeys
import com.aegis.mobile.data.dataStore
import com.aegis.mobile.models.Mt5ConnectRequest
import com.aegis.mobile.network.RetrofitClient
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch

class MainActivity : AppCompatActivity() {

    private lateinit var viewModel: StatusViewModel
    private lateinit var statusText: TextView
    private lateinit var detailsText: TextView
    private lateinit var healthText: TextView
    private lateinit var diagText: TextView
    private lateinit var confidenceText: TextView
    private lateinit var ruleText: TextView
    private lateinit var runningStateText: TextView
    private lateinit var startBtn: Button
    private lateinit var stopBtn: Button
    private lateinit var settingsBtn: Button
    private lateinit var batteryBtn: Button
    private lateinit var accessibilityBtn: Button
    private lateinit var connectMt5Btn: Button
    private lateinit var floatHudBtn: Button
    private lateinit var minimizeBtn: Button
    private lateinit var reportIssueBtn: Button
    private lateinit var previewImage: ImageView
    private lateinit var previewPlaceholder: TextView
    private lateinit var indicatorSetupBtn: Button

    private var captureRunning = false

    private val screenCaptureLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        if (result.resultCode == Activity.RESULT_OK && result.data != null) {
            val serviceIntent = Intent(this, ScreenCaptureService::class.java).apply {
                putExtra(ScreenCaptureService.EXTRA_RESULT_CODE, result.resultCode)
                putExtra(ScreenCaptureService.EXTRA_RESULT_DATA, result.data)
            }
            startForegroundService(serviceIntent)
            setCaptureRunning(true)
            Toast.makeText(
                this,
                "Capturing chart ROI. Operator panel will float over MT5.",
                Toast.LENGTH_LONG
            ).show()
            maybePromptBatteryExemption()
            // Critical: leave the fullscreen AEGIS UI so MediaProjection sees MT5, not this activity.
            ensureOverlayThenOperatorMode()
        } else {
            Toast.makeText(this, "Screen capture permission denied", Toast.LENGTH_SHORT).show()
            setCaptureRunning(false)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        statusText = findViewById(R.id.statusText)
        detailsText = findViewById(R.id.detailsText)
        healthText = findViewById(R.id.healthText)
        diagText = findViewById(R.id.diagText)
        confidenceText = findViewById(R.id.confidenceText)
        ruleText = findViewById(R.id.ruleText)
        runningStateText = findViewById(R.id.runningStateText)
        startBtn = findViewById(R.id.startBtn)
        stopBtn = findViewById(R.id.stopBtn)
        // Keep custom green/red drawables (Material theme would otherwise tint them)
        startBtn.backgroundTintList = null
        stopBtn.backgroundTintList = null
        settingsBtn = findViewById(R.id.settingsBtn)
        batteryBtn = findViewById(R.id.batteryBtn)
        accessibilityBtn = findViewById(R.id.accessibilityBtn)
        connectMt5Btn = findViewById(R.id.connectMt5Btn)
        floatHudBtn = findViewById(R.id.floatHudBtn)
        minimizeBtn = findViewById(R.id.minimizeBtn)
        reportIssueBtn = findViewById(R.id.reportIssueBtn)
        previewImage = findViewById(R.id.previewImage)
        previewPlaceholder = findViewById(R.id.previewPlaceholder)
        indicatorSetupBtn = findViewById(R.id.indicatorSetupBtn)

        // High-contrast text on dark background (theme alone is not always enough)
        val textLight = Color.parseColor("#FFFFFF")
        val textMuted = Color.parseColor("#C5D0E0")
        val textTeal = Color.parseColor("#5EEAD4")
        val textGold = Color.parseColor("#F0D78C")
        statusText.setTextColor(textLight)
        detailsText.setTextColor(textLight)
        healthText.setTextColor(textMuted)
        diagText.setTextColor(textTeal)
        confidenceText.setTextColor(textTeal)
        ruleText.setTextColor(textMuted)
        runningStateText.setTextColor(textMuted)


        viewModel = ViewModelProvider(this)[StatusViewModel::class.java]

        viewModel.signal.observe(this) { signal ->
            statusText.text = signal
            statusText.setTextColor(Color.WHITE)
            when (signal) {
                "BUY" -> statusText.setBackgroundColor(Color.parseColor("#15803D"))
                "SELL" -> statusText.setBackgroundColor(Color.parseColor("#B91C1C"))
                else -> statusText.setBackgroundColor(Color.parseColor("#334155"))
            }

            lifecycleScope.launch {
                val prefs = applicationContext.dataStore.data.first()
                val autoExecute = prefs[PrefKeys.AUTO_EXECUTE] ?: false
                val minConf = prefs[PrefKeys.MIN_CONFIDENCE]?.toFloatOrNull()
                    ?: DEFAULT_MIN_CONFIDENCE
                val confidence = viewModel.confidence.value ?: 0f

                if ((signal == "BUY" || signal == "SELL") && autoExecute) {
                    if (!isAccessibilityEnabled()) {
                        Toast.makeText(this@MainActivity, "Enable Accessibility Service first!", Toast.LENGTH_LONG).show()
                        openAccessibilitySettings()
                    } else if (confidence < minConf) {
                        Toast.makeText(
                            this@MainActivity,
                            "Ignored $signal - confidence $confidence below $minConf",
                            Toast.LENGTH_SHORT
                        ).show()
                    } else {
                        val attempted = Mt5AccessibilityService.executeTrade(signal)
                        if (attempted) {
                            Toast.makeText(this@MainActivity, "Executing $signal on MT5", Toast.LENGTH_SHORT).show()
                        } else {
                            Toast.makeText(this@MainActivity, "$signal skipped (cooldown)", Toast.LENGTH_SHORT).show()
                        }
                    }
                }
            }
        }

        viewModel.details.observe(this) { details ->
            detailsText.text = details
        }

        viewModel.confidence.observe(this) { conf ->
            confidenceText.text = "Confidence: ${"%.0f".format(conf * 100)}%"
        }

        viewModel.currentResult.observe(this) { result ->
            ruleText.text = result.rule_name?.let { "Rule: $it" } ?: ""
        }

        val refreshHealth = {
            val lastCapture = HealthStatus.lastCaptureTimeMs.value ?: 0L
            val secondsAgo = if (lastCapture > 0) (System.currentTimeMillis() - lastCapture) / 1000 else -1
            val failures = HealthStatus.consecutiveFailures.value ?: 0
            val projectionOk = HealthStatus.mediaProjectionActive.value ?: false
            val pendingCache = HealthStatus.pendingCacheCount.value ?: 0
            val cacheSuffix = if (pendingCache > 0) " · $pendingCache queued offline" else ""

            if (!projectionOk && captureRunning) {
                setCaptureRunning(false)
            }

            healthText.text = when {
                lastCapture == 0L && !captureRunning -> "Not started"
                !projectionOk -> "⚠ Capture stopped - tap START to resume"
                failures > 0 -> "⚠ $failures consecutive failures - last ${secondsAgo}s ago$cacheSuffix"
                else -> "✓ Healthy - last capture ${secondsAgo}s ago$cacheSuffix"
            }

            val reachable = HealthStatus.backendReachable.value
            val reachStr = when (reachable) {
                true -> "YES"
                false -> "NO"
                null -> "—"
            }
            val uploadStatus = HealthStatus.lastUploadStatus.value ?: "—"
            val httpCode = HealthStatus.lastHttpCode.value
            val httpStr = httpCode?.toString() ?: "—"
            val uploadAt = HealthStatus.lastUploadTimeMs.value ?: 0L
            val uploadTimeStr = if (uploadAt > 0) {
                java.text.SimpleDateFormat("HH:mm:ss", java.util.Locale.getDefault())
                    .format(java.util.Date(uploadAt))
            } else "—"
            val mt5Fg = when (HealthStatus.mt5Foreground.value) {
                true -> "YES"
                false -> "NO"
                null -> "—"
            }
            val failRate = HealthStatus.failureRateLast(20)
            val avgLat = HealthStatus.avgLatencyLast(20)
            val histN = HealthStatus.historySnapshot().size
            diagText.text = """
Backend Reachable: $reachStr
Last Upload: $uploadStatus
Last HTTP Code: $httpStr
Last Upload Time: $uploadTimeStr
Cached Screenshots: $pendingCache
MT5 Foreground: $mt5Fg
History (local): $histN / 100
Fail rate (last 20): ${"%.0f".format(failRate * 100)}%
Avg latency (last 20): ${avgLat?.let { "${it}ms" } ?: "—"}
""".trimIndent()
        }
        HealthStatus.lastCaptureTimeMs.observe(this) { refreshHealth() }
        HealthStatus.consecutiveFailures.observe(this) { refreshHealth() }
        
        HealthStatus.lastPreviewBitmap.observe(this) { bmp ->
            if (bmp != null) {
                previewImage.setImageBitmap(bmp)
                previewPlaceholder.visibility = android.view.View.GONE
            }
        }

        HealthStatus.mediaProjectionActive.observe(this) { active ->
            setCaptureRunning(active == true)
            refreshHealth()
        }
        HealthStatus.pendingCacheCount.observe(this) { refreshHealth() }
        HealthStatus.backendReachable.observe(this) { refreshHealth() }
        HealthStatus.lastHttpCode.observe(this) { refreshHealth() }
        HealthStatus.lastUploadStatus.observe(this) { refreshHealth() }
        HealthStatus.lastUploadTimeMs.observe(this) { refreshHealth() }
        HealthStatus.mt5Foreground.observe(this) { refreshHealth() }
        HealthStatus.uploadHistoryVersion.observe(this) { refreshHealth() }

        startBtn.setOnClickListener { requestScreenCapturePermission() }
        stopBtn.setOnClickListener { stopCapture() }
        settingsBtn.setOnClickListener {
            startActivity(Intent(this, SettingsActivity::class.java))
        }
        batteryBtn.setOnClickListener { requestBatteryExemption() }
        accessibilityBtn.setOnClickListener { openAccessibilitySettings() }
        connectMt5Btn.setOnClickListener { connectMt5FromPrefs() }
        floatHudBtn.setOnClickListener { toggleFloatingHud() }
        minimizeBtn.setOnClickListener { minimizeApp() }
        reportIssueBtn.setOnClickListener { reportIssue() }
        diagText.setOnLongClickListener { reportIssue(); true }
        healthText.setOnLongClickListener { reportIssue(); true }
        runningStateText.setOnClickListener { minimizeApp() }
        runningStateText.setOnLongClickListener {
            minimizeApp()
            true
        }
        indicatorSetupBtn.setOnClickListener {
            startActivity(Intent(this, IndicatorSetupActivity::class.java))
        }

        setCaptureRunning(HealthStatus.mediaProjectionActive.value == true)
        updateBatteryButtonLabel()
        lifecycleScope.launch { registerDeviceIfNeeded() }
    }


    private fun toggleFloatingHud() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M && !Settings.canDrawOverlays(this)) {
            Toast.makeText(this, "Allow display over other apps for the floating HUD", Toast.LENGTH_LONG).show()
            startActivity(
                Intent(
                    Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                    Uri.parse("package:$packageName")
                )
            )
            return
        }
        if (FloatingHudService.isRunning) {
            val hide = Intent(this, FloatingHudService::class.java).apply {
                action = FloatingHudService.ACTION_HIDE
            }
            stopService(hide)
            Toast.makeText(this, "Floating HUD hidden", Toast.LENGTH_SHORT).show()
        } else {
            val show = Intent(this, FloatingHudService::class.java).apply {
                action = FloatingHudService.ACTION_SHOW
            }
            startService(show)
            Toast.makeText(this, "Floating HUD on — drag to move, tap to expand", Toast.LENGTH_LONG).show()
        }
    }

    /**
     * Put AEGIS in the background and prefer bringing MetaTrader 5 to the front
     * so MediaProjection records the chart (not this UI).
     * Some OEMs ignore moveTaskToBack alone — HOME + explicit MT5 launch is more reliable.
     */

    private fun ensureOverlayThenOperatorMode() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M && !Settings.canDrawOverlays(this)) {
            Toast.makeText(
                this,
                "Allow display over other apps — required for the small AEGIS panel on MT5",
                Toast.LENGTH_LONG
            ).show()
            startActivity(
                Intent(
                    Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                    Uri.parse("package:$packageName")
                )
            )
            return
        }
        try {
            startService(Intent(this, FloatingHudService::class.java).apply {
                action = FloatingHudService.ACTION_SHOW
            })
        } catch (_: Exception) {
        }
        window.decorView.postDelayed({ minimizeApp() }, 400)
    }

    private fun minimizeApp() {
        val mt5Launched = tryLaunchMt5()
        // Go to home / leave this task so we are not covering MT5.
        try {
            val home = Intent(Intent.ACTION_MAIN).apply {
                addCategory(Intent.CATEGORY_HOME)
                flags = Intent.FLAG_ACTIVITY_NEW_TASK
            }
            startActivity(home)
        } catch (_: Exception) {
            moveTaskToBack(true)
        }
        // Also try moveTaskToBack for devices that keep the task in recents cleanly.
        try {
            moveTaskToBack(true)
        } catch (_: Exception) {
        }
        val msg = if (mt5Launched) {
            "Opened MT5 — capture continues in background"
        } else {
            "AEGIS minimized — open MT5 full-screen for chart captures"
        }
        Toast.makeText(this, msg, Toast.LENGTH_LONG).show()
    }

    
    private fun reportIssue() {
        lifecycleScope.launch {
            try {
                val prefs = applicationContext.dataStore.data.first()
                val accountId = prefs[PrefKeys.ACCOUNT_ID] ?: ""
                val http = HealthStatus.lastHttpCode.value
                val body = mutableMapOf<String, Any?>(
                    "account_id" to accountId,
                    "subject" to "Mobile app issue report",
                    "message" to (healthText.text?.toString() ?: "No details"),
                    "last_http_code" to http,
                    "device_model" to "${android.os.Build.MANUFACTURER} ${android.os.Build.MODEL}",
                    "app_version" to "1.0",
                    "android_version" to android.os.Build.VERSION.RELEASE,
                )
                val api = RetrofitClient.getApiService(this@MainActivity)
                val resp = api.reportIssue(body)
                if (resp.isSuccessful) {
                    Toast.makeText(this@MainActivity, "Issue reported (#${resp.body()?.get("ticket_id")})", Toast.LENGTH_LONG).show()
                } else {
                    Toast.makeText(this@MainActivity, "Report failed HTTP ${resp.code()}", Toast.LENGTH_LONG).show()
                }
            } catch (e: Exception) {
                Toast.makeText(this@MainActivity, "Report failed: ${e.message}", Toast.LENGTH_LONG).show()
            }
        }
    }

    private fun tryLaunchMt5(): Boolean {
        val candidates = listOf(
            "net.metaquotes.metatrader5",
            "net.metaquotes.metatrader5x",
        )
        val pm = packageManager
        for (pkg in candidates) {
            try {
                val launch = pm.getLaunchIntentForPackage(pkg)
                if (launch != null) {
                    launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_REORDER_TO_FRONT)
                    startActivity(launch)
                    return true
                }
            } catch (_: Exception) {
            }
        }
        // Broader search for broker-skinned MT5 packages
        try {
            @Suppress("DEPRECATION")
            val packages = pm.getInstalledApplications(PackageManager.GET_META_DATA)
            for (app in packages) {
                val name = app.packageName.lowercase()
                if (name.contains("metatrader5") || name.contains("metatrader.5")) {
                    val launch = pm.getLaunchIntentForPackage(app.packageName) ?: continue
                    launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_REORDER_TO_FRONT)
                    startActivity(launch)
                    return true
                }
            }
        } catch (_: Exception) {
        }
        return false
    }

    private suspend fun registerDeviceIfNeeded() {
        try {
            val prefs = applicationContext.dataStore.data.first()
            val accountId = prefs[PrefKeys.ACCOUNT_ID]?.takeIf { it.isNotBlank() }
                ?: android.provider.Settings.Secure.getString(
                    contentResolver, android.provider.Settings.Secure.ANDROID_ID
                )
            val deviceId = android.provider.Settings.Secure.getString(
                contentResolver, android.provider.Settings.Secure.ANDROID_ID
            ) ?: return
            val api = RetrofitClient.getApiService(this@MainActivity)
            val body = mapOf(
                "account_id" to accountId,
                "device_id" to deviceId,
                "device_label" to (android.os.Build.MODEL ?: "android")
            )
            val res = api.registerDevice(body)
            if (res.code() == 403) {
                runOnUiThread {
                    Toast.makeText(
                        this@MainActivity,
                        "This subscription is bound to another phone. Contact support to transfer.",
                        Toast.LENGTH_LONG
                    ).show()
                }
            }
        } catch (_: Exception) {
            // offline / not configured yet
        }
    }


    override fun onResume() {
        super.onResume()
        updateBatteryButtonLabel()
        val projectionOk = HealthStatus.mediaProjectionActive.value == true
        setCaptureRunning(projectionOk)
    }

    private fun setCaptureRunning(running: Boolean) {
        captureRunning = running
        startBtn.isEnabled = !running
        stopBtn.isEnabled = running
        startBtn.alpha = if (running) 0.45f else 1f
        stopBtn.alpha = if (running) 1f else 0.45f
        runningStateText.text = if (running) "● Running — capture active" else "○ Stopped"
        runningStateText.setTextColor(
            if (running) Color.parseColor("#4ADE80") else Color.parseColor("#C5D0E0")
        )
    }

    private fun stopCapture() {
        // Explicit ACTION_STOP so the service cleans up MediaProjection and does not
        // get auto-restarted without a token (which looked like "Start again by itself").
        val stopIntent = Intent(this, ScreenCaptureService::class.java).apply {
            action = ScreenCaptureService.ACTION_STOP
        }
        try {
            startService(stopIntent)
        } catch (_: Exception) {
        }
        try {
            stopService(Intent(this, ScreenCaptureService::class.java))
        } catch (_: Exception) {
        }
        HealthStatus.mediaProjectionActive.postValue(false)
        setCaptureRunning(false)
        Toast.makeText(this, "AEGIS Stopped", Toast.LENGTH_SHORT).show()
        healthText.text = "Stopped by user"
    }

    private fun requestScreenCapturePermission() {
        lifecycleScope.launch {
            val prefs = applicationContext.dataStore.data.first()
            val key = prefs[PrefKeys.API_KEY]?.trim().orEmpty()
            val url = prefs[PrefKeys.SERVER_URL]?.trim().orEmpty()
            // Capture can run without a live backend (local MT5 screenshots + offline cache).
            // Uploads only succeed after the API is deployed (e.g. Render) and URL + key are set.
            if (key.isEmpty() || url.isEmpty()) {
                Toast.makeText(
                    this@MainActivity,
                    "No Server URL/API Key — capture will run, uploads wait until backend is on Render",
                    Toast.LENGTH_LONG
                ).show()
            }
            val projectionManager =
                getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
            screenCaptureLauncher.launch(projectionManager.createScreenCaptureIntent())
        }
    }

    private fun connectMt5FromPrefs() {
        lifecycleScope.launch {
            val prefs = applicationContext.dataStore.data.first()
            val accountId = prefs[PrefKeys.ACCOUNT_ID]?.takeIf { it.isNotBlank() }
                ?: android.provider.Settings.Secure.getString(
                    contentResolver,
                    android.provider.Settings.Secure.ANDROID_ID
                )
            val login = prefs[PrefKeys.MT5_LOGIN]?.trim().orEmpty()
            val password = prefs[PrefKeys.MT5_PASSWORD]?.trim().orEmpty()
            val server = prefs[PrefKeys.MT5_SERVER]?.trim().orEmpty()
            val broker = prefs[PrefKeys.MT5_BROKER_NAME]?.trim()?.ifBlank { null } ?: DEFAULT_BROKER_NAME
            val execution = prefs[PrefKeys.MT5_EXECUTION_ENABLED] ?: true

            if (login.isEmpty() || password.isEmpty() || server.isEmpty()) {
                Toast.makeText(
                    this@MainActivity,
                    "Fill MT5 login, password and server in Settings first",
                    Toast.LENGTH_LONG
                ).show()
                startActivity(Intent(this@MainActivity, SettingsActivity::class.java))
                return@launch
            }

            connectMt5Btn.isEnabled = false
            Toast.makeText(this@MainActivity, "Connecting MT5…", Toast.LENGTH_SHORT).show()
            try {
                val api = RetrofitClient.getApiService(this@MainActivity)
                val body = Mt5ConnectRequest(
                    account_id = accountId,
                    broker_name = broker,
                    server = server,
                    login = login,
                    trading_password = password,
                    execution_enabled = execution
                )
                val response = api.connectMt5(body)
                if (response.isSuccessful) {
                    Toast.makeText(
                        this@MainActivity,
                        "MT5 connect requested for $accountId",
                        Toast.LENGTH_LONG
                    ).show()
                } else {
                    val err = try {
                        response.errorBody()?.string()?.take(300)
                    } catch (_: Exception) {
                        null
                    }
                    Toast.makeText(
                        this@MainActivity,
                        "Connect failed ${response.code()}: ${err ?: ""}",
                        Toast.LENGTH_LONG
                    ).show()
                }
            } catch (e: Exception) {
                Toast.makeText(
                    this@MainActivity,
                    "Connect error: ${e.message}",
                    Toast.LENGTH_LONG
                ).show()
            } finally {
                connectMt5Btn.isEnabled = true
            }
        }
    }

    private fun isIgnoringBatteryOptimizations(): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.M) return true
        val pm = getSystemService(Context.POWER_SERVICE) as PowerManager
        return pm.isIgnoringBatteryOptimizations(packageName)
    }

    private fun updateBatteryButtonLabel() {
        batteryBtn.text = if (isIgnoringBatteryOptimizations()) {
            "BACKGROUND RUNNING: ALLOWED ✓"
        } else {
            "ALLOW BACKGROUND RUNNING (recommended)"
        }
    }

    private fun requestBatteryExemption() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.M || isIgnoringBatteryOptimizations()) {
            Toast.makeText(this, "Already allowed to run in the background.", Toast.LENGTH_SHORT).show()
            return
        }
        try {
            val intent = Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS).apply {
                data = Uri.parse("package:$packageName")
            }
            startActivity(intent)
        } catch (e: Exception) {
            startActivity(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS))
        }
    }

    private fun maybePromptBatteryExemption() {
        if (!isIgnoringBatteryOptimizations()) {
            Toast.makeText(
                this,
                "Tip: allow background running so Android doesn't kill AEGIS.",
                Toast.LENGTH_LONG
            ).show()
        }
    }

    private fun isAccessibilityEnabled(): Boolean {
        val service = "$packageName/com.aegis.mobile.automation.Mt5AccessibilityService"
        val enabledServices = Settings.Secure.getString(
            contentResolver,
            Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES
        )
        return enabledServices?.contains(service) == true
    }

    private fun openAccessibilitySettings() {
        startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
    }
}
