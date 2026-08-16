package com.aegis.mobile.ui

import android.annotation.SuppressLint
import android.app.Service
import android.content.Intent
import android.graphics.Color
import android.graphics.PixelFormat
import android.graphics.drawable.GradientDrawable
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
import kotlin.math.abs

/**
 * Draggable operator panel over MT5.
 * - Expanded (~40% panel): preview + signal + status + Minimize
 * - Minimized: small floating bubble (always on top of other apps)
 * Tap bubble to expand again from any screen.
 */
class FloatingHudService : Service() {

    private var windowManager: WindowManager? = null
    private var root: LinearLayout? = null
    private lateinit var params: WindowManager.LayoutParams
    private lateinit var headerRow: LinearLayout
    private lateinit var titleView: TextView
    private lateinit var toggleBtn: TextView
    private lateinit var signalView: TextView
    private lateinit var statusView: TextView
    private lateinit var preview: ImageView
    private lateinit var previewFrame: FrameLayout
    private lateinit var body: LinearLayout

    private val mainHandler = Handler(Looper.getMainLooper())
    private var panelW = 320
    private var panelH = 400
    private var bubbleSize = 96
    private var collapsed = false
    private var dragDx = 0
    private var dragDy = 0
    private var moved = false

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_HIDE -> {
                stopSelf()
                return START_NOT_STICKY
            }
            ACTION_CAPTURE_HIDE -> setRootVisible(false)
            ACTION_CAPTURE_SHOW -> setRootVisible(true)
            ACTION_EXPAND -> mainHandler.post { setCollapsed(false) }
            ACTION_COLLAPSE -> mainHandler.post { setCollapsed(true) }
            else -> {
                isRunning = true
                setRootVisible(true)
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
        panelW = (metrics.widthPixels * 0.42f).toInt().coerceIn(280, 480)
        panelH = (metrics.heightPixels * 0.38f).toInt().coerceIn(320, 560)
        bubbleSize = (56 * metrics.density).toInt().coerceIn(56, 88)

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

        val bg = GradientDrawable().apply {
            setColor(Color.parseColor("#E6111828"))
            cornerRadius = 18f * resources.displayMetrics.density
            setStroke((1 * resources.displayMetrics.density).toInt(), Color.parseColor("#44D4AF37"))
        }

        root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(12), dp(10), dp(12), dp(10))
            background = bg
            elevation = 16f
        }

        headerRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            )
        }

        titleView = TextView(this).apply {
            text = "AEGIS"
            setTextColor(Color.parseColor("#F0D78C"))
            textSize = 13f
            layoutParams = LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f)
        }

        toggleBtn = TextView(this).apply {
            text = "MIN"
            setTextColor(Color.WHITE)
            textSize = 12f
            setPadding(dp(10), dp(6), dp(10), dp(6))
            background = GradientDrawable().apply {
                setColor(Color.parseColor("#2563EB"))
                cornerRadius = 10f * resources.displayMetrics.density
            }
            setOnClickListener {
                setCollapsed(!collapsed)
            }
        }

        headerRow.addView(titleView)
        headerRow.addView(toggleBtn)

        body = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.MATCH_PARENT
            )
        }

        previewFrame = FrameLayout(this).apply {
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
            textSize = 17f
            setPadding(0, dp(8), 0, dp(2))
        }
        statusView = TextView(this).apply {
            text = "Drag · MIN hides · tap bubble to restore"
            setTextColor(Color.parseColor("#5EEAD4"))
            textSize = 11f
        }

        body.addView(previewFrame)
        body.addView(signalView)
        body.addView(statusView)

        root!!.addView(headerRow)
        root!!.addView(body)

        root!!.setOnTouchListener { _, event ->
            when (event.action) {
                MotionEvent.ACTION_DOWN -> {
                    dragDx = params.x - event.rawX.toInt()
                    dragDy = params.y - event.rawY.toInt()
                    moved = false
                    true
                }
                MotionEvent.ACTION_MOVE -> {
                    val nx = event.rawX.toInt() + dragDx
                    val ny = event.rawY.toInt() + dragDy
                    if (abs(nx - params.x) > 6 || abs(ny - params.y) > 6) moved = true
                    params.x = nx.coerceAtLeast(0)
                    params.y = ny.coerceAtLeast(0)
                    try {
                        windowManager?.updateViewLayout(root, params)
                    } catch (_: Exception) {
                    }
                    true
                }
                MotionEvent.ACTION_UP -> {
                    // In bubble mode, a clean tap expands again
                    if (collapsed && !moved) {
                        setCollapsed(false)
                    }
                    true
                }
                else -> false
            }
        }

        try {
            windowManager?.addView(root, params)
        } catch (_: Exception) {
            stopSelf()
            return
        }

        mainHandler.post {
            HealthStatus.lastPreviewBitmap.observeForever(previewObserver)
            SignalRepository.latestSignal.observeForever(signalObserver)
            HealthStatus.lastUploadStatus.observeForever(statusObserver)
            HealthStatus.mediaProjectionActive.observeForever(runningObserver)
        }
    }

    private fun setCollapsed(collapse: Boolean) {
        collapsed = collapse
        isCollapsed = collapse
        if (collapse) {
            body.visibility = View.GONE
            toggleBtn.text = "▲"
            titleView.text = signalView.text?.toString()?.removePrefix("SIGNAL: ")?.trim() ?: "AEGIS"
            titleView.textSize = 14f
            titleView.gravity = Gravity.CENTER
            headerRow.gravity = Gravity.CENTER
            toggleBtn.visibility = View.GONE
            root?.setPadding(dp(10), dp(10), dp(10), dp(10))
            params.width = bubbleSize
            params.height = bubbleSize
            // Compact round bubble
            root?.background = GradientDrawable().apply {
                shape = GradientDrawable.OVAL
                setColor(Color.parseColor("#F015653C"))
                setStroke(dp(2), Color.parseColor("#F0D78C"))
            }
        } else {
            body.visibility = View.VISIBLE
            toggleBtn.visibility = View.VISIBLE
            toggleBtn.text = "MIN"
            titleView.text = if (HealthStatus.mediaProjectionActive.value == true)
                "AEGIS · capturing" else "AEGIS · idle"
            titleView.textSize = 13f
            titleView.gravity = Gravity.START
            headerRow.gravity = Gravity.CENTER_VERTICAL
            root?.setPadding(dp(12), dp(10), dp(12), dp(10))
            params.width = panelW
            params.height = panelH
            root?.background = GradientDrawable().apply {
                setColor(Color.parseColor("#E6111828"))
                cornerRadius = 18f * resources.displayMetrics.density
                setStroke(dp(1), Color.parseColor("#44D4AF37"))
            }
        }
        try {
            windowManager?.updateViewLayout(root, params)
        } catch (_: Exception) {
        }
    }

    private fun setRootVisible(visible: Boolean) {
        mainHandler.post {
            // During capture hide: stay invisible even if expanded
            root?.visibility = if (visible) View.VISIBLE else View.INVISIBLE
        }
    }

    private fun dp(v: Int): Int = (v * resources.displayMetrics.density).toInt()

    private val previewObserver = androidx.lifecycle.Observer<android.graphics.Bitmap?> { bmp ->
        if (bmp != null) preview.setImageBitmap(bmp)
    }
    private val signalObserver = androidx.lifecycle.Observer<String> { sig ->
        signalView.text = "SIGNAL: ${sig ?: "—"}"
        when (sig) {
            "BUY" -> {
                signalView.setTextColor(Color.parseColor("#4ADE80"))
                if (collapsed) titleView.text = "BUY"
            }
            "SELL" -> {
                signalView.setTextColor(Color.parseColor("#F87171"))
                if (collapsed) titleView.text = "SELL"
            }
            else -> {
                signalView.setTextColor(Color.WHITE)
                if (collapsed) titleView.text = sig ?: "AEGIS"
            }
        }
    }
    private val statusObserver = androidx.lifecycle.Observer<String> { st ->
        statusView.text = "Upload: ${st ?: "—"}  ·  MIN to hide"
    }
    private val runningObserver = androidx.lifecycle.Observer<Boolean> { on ->
        if (!collapsed) {
            titleView.text = if (on == true) "AEGIS · capturing" else "AEGIS · idle"
        }
    }

    override fun onDestroy() {
        isRunning = false
        isCollapsed = false
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

        @JvmField
        @Volatile
        var isCollapsed: Boolean = false

        const val ACTION_SHOW = "com.aegis.mobile.HUD_SHOW"
        const val ACTION_HIDE = "com.aegis.mobile.HUD_HIDE"
        const val ACTION_CAPTURE_HIDE = "com.aegis.mobile.HUD_CAPTURE_HIDE"
        const val ACTION_CAPTURE_SHOW = "com.aegis.mobile.HUD_CAPTURE_SHOW"
        const val ACTION_EXPAND = "com.aegis.mobile.HUD_EXPAND"
        const val ACTION_COLLAPSE = "com.aegis.mobile.HUD_COLLAPSE"
    }
}
