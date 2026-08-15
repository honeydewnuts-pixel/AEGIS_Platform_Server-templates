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

        /** Official + common broker-skinned package id prefixes. */
        private val MT5_PACKAGES = setOf(
            "net.metaquotes.metatrader5",
            "net.metaquotes.metatrader5x",
        )

        private fun isMt5Package(pkg: String?): Boolean {
            if (pkg.isNullOrBlank()) return false
            if (pkg in MT5_PACKAGES) return true
            // Broker builds often embed "metatrader5" in the package name.
            val lower = pkg.lowercase()
            return lower.contains("metatrader5") || lower.contains("metatrader.5")
        }

        @Volatile
        var instance: Mt5AccessibilityService? = null

        /** Updated from window-state events; diagnostics only (capture is not gated). */
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
            val active = isMt5Package(pkg)
            isMt5Foreground = active
            HealthStatus.mt5Foreground.postValue(active)
        }
    }

    override fun onServiceConnected() {
        super.onServiceConnected()
        instance = this
        val info = AccessibilityServiceInfo().apply {
            eventTypes = AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED or
                AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED
            packageNames = null
            feedbackType = AccessibilityServiceInfo.FEEDBACK_GENERIC
            flags = AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS or
                AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS
        }
        this.serviceInfo = info
        // MT5 may already be open before AEGIS starts — sample the active window now.
        refreshCurrentForeground()
        Log.d("AEGIS-Auto", "Accessibility Service Connected; mt5Fg=$isMt5Foreground")
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        if (event == null) return
        when (event.eventType) {
            AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED -> {
                setForegroundPackage(event.packageName?.toString())
            }
            AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED -> {
                // Keep status fresh if MT5 was already running before we connected.
                refreshCurrentForeground()
            }
        }
    }

    /** Read the active window package (works when MT5 was already in front). */
    private fun refreshCurrentForeground() {
        try {
            val pkg = rootInActiveWindow?.packageName?.toString()
            if (pkg != null) {
                setForegroundPackage(pkg)
            }
        } catch (e: Exception) {
            Log.w("AEGIS-Auto", "refreshCurrentForeground: ${e.message}")
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
