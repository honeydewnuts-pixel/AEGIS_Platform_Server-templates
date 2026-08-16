package com.aegis.mobile.ui

import android.annotation.SuppressLint
import android.app.Service
import android.content.Intent
import android.graphics.Color
import android.graphics.PixelFormat
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.util.DisplayMetrics
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.WindowManager
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.TextView
import com.aegis.mobile.data.HealthStatus
import com.aegis.mobile.data.SignalRepository

/**
 * Quarter-screen draggable operator panel.
 * Sits over MT5 so the main AEGIS activity can leave the foreground.
 * Hidden for a few ms around each capture so MediaProjection does not
 * photograph this overlay instead of the chart.
 */
class FloatingHudService : Service() {

    private var windowManager: WindowManager? = null
    private var root: LinearLayout? = null
    private lateinit var params: WindowManager.LayoutParams
    private lateinit var titleView: TextView
    private lateinit var signalView: TextView
    private lateinit var statusView: TextView
    private lateinit var preview: ImageView
    private val mainHandler = Handler(Looper.getMainLooper())
    private var dragDx = 0
    private var dragDy = 0
    private var moving = false

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_HIDE -> {
                stopSelf()
                return START_NOT_STICKY
            }
            ACTION_CAPTURE_HIDE -> {
                setPanelVisible(false)
            }
            ACTION_CAPTURE_SHOW -> {
                setPanelVisible(true)
            }
            else -> {
                isRunning = true
                setPanelVisible(true)
            }
        }
        return START_STICKY
    }

    @SuppressLint("ClickableViewAccessibility")
    override fun onCreate() {
        isRunning = true
        super.onCreate()
        windowManager = getSystemService(WINDOW_SERVICE) as WindowManager

        val metrics = DisplayMetrics()
        @Suppress("DEPRECATION")
        windowManager!!.defaultDisplay.getMetrics(metrics)
        val panelW = (metrics.widthPixels * 0.42f).toInt().coerceIn(280, 480)
        val panelH = (metrics.heightPixels * 0.38f).toInt().coerceIn(320, 560)

        val type = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O)
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
        else
            @Suppress("DEPRECATION")
            WindowManager.LayoutParams.TYPE_PHONE

        params = WindowManager.LayoutParams(
            panelW,
            panelH,
            type,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN or
                WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
            PixelFormat.TRANSLUCENT
        )
        params.gravity = Gravity.TOP or Gravity.START
        params.x = 24
        params.y = metrics.heightPixels / 10

        root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(16, 14, 16, 14)
            setBackgroundColor(Color.parseColor("#E6111828"))
            elevation = 16f
        }

        titleView = TextView(this).apply {
            text = "AEGIS · drag to move"
            setTextColor(Color.parseColor("#F0D78C"))
            textSize = 12f
            setPadding(0, 0, 0, 8)
        }

        val previewFrame = FrameLayout(this).apply {
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                0,
                1.2f
            )
            setBackgroundColor(Color.parseColor("#0B1220"))
        }
        preview = ImageView(this).apply {
            scaleType = ImageView.ScaleType.CENTER_CROP
            layoutParams = FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            )
        }
        previewFrame.addView(preview)

        signalView = TextView(this).apply {
            text = "SIGNAL: —"
            setTextColor(Color.WHITE)
            textSize = 18f
            setPadding(0, 10, 0, 4)
        }
        statusView = TextView(this).apply {
            text = "Tap START in app, then leave this panel over MT5"
            setTextColor(Color.parseColor("#5EEAD4"))
            textSize = 11f
        }

        root!!.addView(titleView)
        root!!.addView(previewFrame)
        root!!.addView(signalView)
        root!!.addView(statusView)

        root!!.setOnTouchListener { _, event ->
            when (event.action) {
                MotionEvent.ACTION_DOWN -> {
                    dragDx = event.rawX.toInt() - params.x
                    dragDy = event.rawY.toInt() - params.y
                    moving = false
                    true
                }
                MotionEvent.ACTION_MOVE -> {
                    val nx = event.rawX.toInt() - dragDx
                    val ny = event.rawY.toInt() - dragDy
                    if (kotlin.math.abs(nx - params.x) > 4 || kotlin.math.abs(ny - params.y) > 4) {
                        moving = true
                    }
                    // END gravity: x is offset from the right edge
                    params.x = nx.coerceAtLeast(0)
                    params.y = ny.coerceAtLeast(0)
                    try {
                        windowManager?.updateViewLayout(root, params)
                    } catch (_: Exception) {
                    }
                    true
                }
                MotionEvent.ACTION_UP -> true
                else -> false
            }
        }

        try {
            windowManager?.addView(root, params)
        } catch (e: Exception) {
            stopSelf()
            return
        }

        // Observe preview + signal on main thread
        mainHandler.post {
            HealthStatus.lastPreviewBitmap.observeForever(previewObserver)
            SignalRepository.latestSignal.observeForever(signalObserver)
            HealthStatus.lastUploadStatus.observeForever(statusObserver)
            HealthStatus.mediaProjectionActive.observeForever(runningObserver)
        }
    }

    private val previewObserver = androidx.lifecycle.Observer<android.graphics.Bitmap?> { bmp ->
        if (bmp != null) preview.setImageBitmap(bmp)
    }
    private val signalObserver = androidx.lifecycle.Observer<String> { sig ->
        signalView.text = "SIGNAL: ${sig ?: "—"}"
        when (sig) {
            "BUY" -> signalView.setTextColor(Color.parseColor("#4ADE80"))
            "SELL" -> signalView.setTextColor(Color.parseColor("#F87171"))
            else -> signalView.setTextColor(Color.WHITE)
        }
    }
    private val statusObserver = androidx.lifecycle.Observer<String> { st ->
        statusView.text = "Upload: ${st ?: "—"}"
    }
    private val runningObserver = androidx.lifecycle.Observer<Boolean> { on ->
        titleView.text = if (on == true) "AEGIS · capturing · drag" else "AEGIS · idle · drag"
    }

    private fun setPanelVisible(visible: Boolean) {
        mainHandler.post {
            root?.visibility = if (visible) View.VISIBLE else View.INVISIBLE
        }
    }

    override fun onDestroy() {
        isRunning = false
        try {
            HealthStatus.lastPreviewBitmap.removeObserver(previewObserver)
            SignalRepository.latestSignal.removeObserver(signalObserver)
            HealthStatus.lastUploadStatus.removeObserver(statusObserver)
            HealthStatus.mediaProjectionActive.removeObserver(runningObserver)
        } catch (_: Exception) {
        }
        try {
            if (root != null) windowManager?.removeView(root)
        } catch (_: Exception) {
        }
        root = null
        super.onDestroy()
    }

    companion object {
        @JvmField
        @Volatile
        var isRunning: Boolean = false

        const val ACTION_SHOW = "com.aegis.mobile.HUD_SHOW"
        const val ACTION_HIDE = "com.aegis.mobile.HUD_HIDE"
        const val ACTION_CAPTURE_HIDE = "com.aegis.mobile.HUD_CAPTURE_HIDE"
        const val ACTION_CAPTURE_SHOW = "com.aegis.mobile.HUD_CAPTURE_SHOW"
    }
}
