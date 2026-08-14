package com.aegis.mobile.ui

import android.os.Bundle
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.aegis.mobile.network.RetrofitClient
import kotlinx.coroutines.launch

/**
 * Guided checklist so every client installs the same MT5 indicator stack
 * in the same order/colors. MT5 Mobile cannot be auto-configured by AEGIS;
 * this screen is the enforced human template.
 */
class IndicatorSetupActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val scroll = ScrollView(this)
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(40, 40, 40, 40)
        }
        scroll.addView(root)
        setContentView(scroll)

        val title = TextView(this).apply {
            text = "AEGIS Indicator Template"
            textSize = 20f
            setPadding(0, 0, 0, 16)
        }
        val version = TextView(this).apply {
            text = "Loading active profile…"
            textSize = 13f
            setPadding(0, 0, 0, 12)
        }
        val body = TextView(this).apply {
            text = ""
            textSize = 13f
            setPadding(0, 0, 0, 20)
        }
        val refresh = Button(this).apply { text = "REFRESH FROM SERVER" }
        val markDone = Button(this).apply { text = "I INSTALLED THIS TEMPLATE" }

        root.addView(title)
        root.addView(version)
        root.addView(body)
        root.addView(refresh)
        root.addView(markDone)

        fun load() {
            lifecycleScope.launch {
                try {
                    val api = RetrofitClient.getApiService(this@IndicatorSetupActivity)
                    val res = api.getActiveTemplates()
                    if (!res.isSuccessful || res.body() == null) {
                        body.text = "Failed to load template (${res.code()}). Check backend URL / API key."
                        return@launch
                    }
                    val data = res.body()!!
                    val stackVer = data["indicator_stack_version"]?.toString() ?: "?"
                    val bookVer = data["rulebook_version"]?.toString() ?: "?"
                    version.text = "Indicator stack $stackVer · Rulebook $bookVer"

                    @Suppress("UNCHECKED_CAST")
                    val stack = data["indicator_stack"] as? Map<String, Any?>
                    val order = stack?.get("install_order") as? List<*>
                    val sb = StringBuilder()
                    sb.append("Install on MetaTrader 5 (mobile) in this exact order.\n")
                    sb.append("Theme: Dark · Match colors exactly.\n\n")
                    order?.forEachIndexed { i, step ->
                        val m = step as? Map<*, *> ?: return@forEachIndexed
                        sb.append("${i + 1}. ${m["display_name"]}\n")
                        sb.append("   MT5: ${m["mt5_name"]}  |  Panel: ${m["panel"]}\n")
                        sb.append("   Params: ${m["params"]}\n")
                        sb.append("   Color: ${m["color"]}\n")
                        if (m["notes"] != null) sb.append("   ${m["notes"]}\n")
                        sb.append("\n")
                    }
                    sb.append("Rulebook: $bookVer — brain evaluates screenshots against this version.\n")
                    sb.append("When the operator activates a new version, open this screen and update MT5.\n")
                    body.text = sb.toString()
                } catch (e: Exception) {
                    body.text = "Error: ${e.message}"
                }
            }
        }

        refresh.setOnClickListener { load() }
        markDone.setOnClickListener {
            getSharedPreferences("aegis_prefs", MODE_PRIVATE)
                .edit()
                .putBoolean("indicator_template_confirmed", true)
                .putLong("indicator_template_confirmed_at", System.currentTimeMillis())
                .apply()
            Toast.makeText(this, "Template marked installed", Toast.LENGTH_SHORT).show()
            finish()
        }
        load()
    }
}
