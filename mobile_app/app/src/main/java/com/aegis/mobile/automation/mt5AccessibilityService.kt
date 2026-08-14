package com.aegis.mobile.automation

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.AccessibilityServiceInfo
import android.util.Log
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import com.aegis.mobile.data.HealthStatus
import com.aegis.mobile.data.SignalRepository

class Mt5AccessibilityService : AccessibilityService() {

    companion object {
        const val MT5_PACKAGE = "net.metaquotes.metatrader5"

        @Volatile
        var instance: Mt5AccessibilityService? = null

        /** Updated from window-state events; read by ScreenCaptureService. */
        @Volatile
        var isMt5Foreground: Boolean = false
            private set

        private const val COOLDOWN_MS = 60_000L

        fun executeTrade(signal: String): Boolean {
            val now = System.currentTimeMillis()
            if (now - SignalRepository.lastExecutionTimeMs < COOLDOWN_MS) {
                Log.d("AEGIS-Auto", "Skipped $signal - still in cooldown")
                return false
            }
            val svc = instance ?: run {
                Log.e("AEGIS-Auto", "Accessibility service not connected")
                return false
            }
            SignalRepository.lastExecutionTimeMs = now
            svc.performMt5Click(signal)
            return true
        }

        internal fun setForegroundPackage(pkg: String?) {
            val active = pkg == MT5_PACKAGE
            isMt5Foreground = active
            HealthStatus.mt5Foreground.postValue(active)
        }
    }

    override fun onServiceConnected() {
        super.onServiceConnected()
        instance = this
        val info = AccessibilityServiceInfo().apply {
            // Track window changes so we know when MT5 is foreground.
            eventTypes = AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED or
                AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED
            // Listen to all packages for foreground detection; clicks still target MT5.
            packageNames = null
            feedbackType = AccessibilityServiceInfo.FEEDBACK_GENERIC
            flags = AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS
        }
        this.serviceInfo = info
        Log.d("AEGIS-Auto", "Accessibility Service Connected")
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        if (event == null) return
        if (event.eventType == AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED) {
            val pkg = event.packageName?.toString()
            setForegroundPackage(pkg)
        }
    }

    override fun onInterrupt() {}

    override fun onDestroy() {
        instance = null
        isMt5Foreground = false
        super.onDestroy()
    }

    private fun performMt5Click(signal: String) {
        val root = rootInActiveWindow ?: return
        val buttonText = if (signal == "BUY") "Buy" else "Sell"
        val found = findAndClick(root, buttonText)
        Log.d("AEGIS-Auto", "Attempted to click: $buttonText, found=$found")
    }

    private fun findAndClick(node: AccessibilityNodeInfo, text: String): Boolean {
        if (node.text?.toString()?.contains(text, ignoreCase = true) == true && node.isClickable) {
            return node.performAction(AccessibilityNodeInfo.ACTION_CLICK)
        }
        for (i in 0 until node.childCount) {
            node.getChild(i)?.let {
                if (findAndClick(it, text)) return true
            }
        }
        return false
    }
}
