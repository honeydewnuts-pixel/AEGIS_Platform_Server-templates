package com.aegis.mobile.ui

import android.app.Service
import android.content.Intent
import android.graphics.Color
import android.graphics.PixelFormat
import android.os.Build
import android.os.IBinder
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.WindowManager
import android.widget.LinearLayout
import android.widget.TextView
import com.aegis.mobile.data.HealthStatus
import com.aegis.mobile.data.SignalRepository

/**
 * Draggable floating bubble that can expand to show signal + diagnostics.
 * Requires SYSTEM_ALERT_WINDOW (Settings → Display over other apps).
 */
class FloatingHudService : Service() {

    private var windowManager: WindowManager? = null
    private var bubble: LinearLayout? = null
    private var expanded = false
    private lateinit var params: WindowManager.LayoutParams
    private lateinit var titleView: TextView
    private lateinit var detailView: TextView

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        windowManager = getSystemService(WINDOW_SERVICE) as WindowManager
        val type = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O)
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
        else
            @Suppress("DEPRECATION")
            WindowManager.LayoutParams.TYPE_PHONE

        params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            type,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,
            PixelFormat.TRANSLUCENT
        )
        params.gravity = Gravity.TOP or Gravity.START
        params.x = 40
        params.y = 200

        bubble = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(28, 20, 28, 20)
            setBackgroundColor(Color.parseColor("#CC1B2838"))
            elevation = 12f
        }

        titleView = TextView(this).apply {
            text = "AEGIS · HOLD"
            setTextColor(Color.WHITE)
            textSize = 14f
            setTypeface(typeface, android.graphics.Typeface.BOLD)
        }
        detailView = TextView(this).apply {
            text = "Tap to expand"
            setTextColor(Color.parseColor("#AABBCC"))
            textSize = 11f
            visibility = View.GONE
        }
        bubble!!.addView(titleView)
        bubble!!.addView(detailView)

        var downX = 0f
        var downY = 0f
        var paramX = 0
        var paramY = 0
        var moved = false

        bubble!!.setOnTouchListener { _, e ->
            when (e.action) {
                MotionEvent.ACTION_DOWN -> {
                    downX = e.rawX
                    downY = e.rawY
                    paramX = params.x
                    paramY = params.y
                    moved = false
                    true
                }
                MotionEvent.ACTION_MOVE -> {
                    val dx = (e.rawX - downX).toInt()
                    val dy = (e.rawY - downY).toInt()
                    if (kotlin.math.abs(dx) > 8 || kotlin.math.abs(dy) > 8) moved = true
                    params.x = paramX + dx
                    params.y = paramY + dy
                    windowManager?.updateViewLayout(bubble, params)
                    true
                }
                MotionEvent.ACTION_UP -> {
                    if (!moved) toggleExpand()
                    true
                }
                else -> false
            }
        }

        windowManager?.addView(bubble, params)

        SignalRepository.latestResult.observeForever { res ->
            val sig = res?.signal ?: "HOLD"
            val conf = res?.confidence ?: 0f
            titleView.text = "AEGIS · $sig"
            titleView.setTextColor(
                when (sig) {
                    "BUY" -> Color.parseColor("#3FB950")
                    "SELL" -> Color.parseColor("#F85149")
                    else -> Color.WHITE
                }
            )
            if (expanded) refreshDetail(sig, conf)
        }
        HealthStatus.lastUploadStatus.observeForever {
            if (expanded) {
                val conf = SignalRepository.latestResult.value?.confidence ?: 0f
                val sig = SignalRepository.latestResult.value?.signal ?: "HOLD"
                refreshDetail(sig, conf)
            }
        }
    }

    private fun toggleExpand() {
        expanded = !expanded
        detailView.visibility = if (expanded) View.VISIBLE else View.GONE
        if (expanded) {
            val conf = SignalRepository.latestResult.value?.confidence ?: 0f
            val sig = SignalRepository.latestResult.value?.signal ?: "HOLD"
            refreshDetail(sig, conf)
        } else {
            detailView.text = "Tap to expand"
        }
    }

    private fun refreshDetail(sig: String, conf: Float) {
        val reach = when (HealthStatus.backendReachable.value) {
            true -> "YES"
            false -> "NO"
            null -> "—"
        }
        val http = HealthStatus.lastHttpCode.value?.toString() ?: "—"
        val status = HealthStatus.lastUploadStatus.value ?: "—"
        val cache = HealthStatus.pendingCacheCount.value ?: 0
        detailView.text = "Conf ${"%.0f".format(conf * 100)}%\n" +
            "Upload: $status · HTTP $http\n" +
            "Backend: $reach · Cache: $cache\n" +
            "(drag to move · tap to minimize)"
    }

    override fun onDestroy() {
        super.onDestroy()
        if (bubble != null) {
            windowManager?.removeView(bubble)
            bubble = null
        }
    }

    companion object {
        const val ACTION_SHOW = "com.aegis.mobile.HUD_SHOW"
        const val ACTION_HIDE = "com.aegis.mobile.HUD_HIDE"
    }
}
