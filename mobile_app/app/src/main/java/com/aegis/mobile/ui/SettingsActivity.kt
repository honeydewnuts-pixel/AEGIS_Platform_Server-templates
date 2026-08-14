package com.aegis.mobile.ui

import android.os.Bundle
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.datastore.preferences.core.edit
import androidx.lifecycle.lifecycleScope
import com.aegis.mobile.R
import com.aegis.mobile.data.DEFAULT_BROKER_NAME
import com.aegis.mobile.data.DEFAULT_MIN_CONFIDENCE
import com.aegis.mobile.data.DEFAULT_SERVER_URL
import com.aegis.mobile.data.PrefKeys
import com.aegis.mobile.data.dataStore
import com.aegis.mobile.models.Mt5ConnectRequest
import com.aegis.mobile.network.RetrofitClient
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch

class SettingsActivity : AppCompatActivity() {

    private lateinit var etUrl: EditText
    private lateinit var etApiKey: EditText
    private lateinit var etAccountId: EditText
    private lateinit var etMt5Broker: EditText
    private lateinit var etMt5Server: EditText
    private lateinit var etMt5Login: EditText
    private lateinit var etMt5Password: EditText
    private lateinit var cbMt5Execution: CheckBox
    private lateinit var cbAutoExecute: CheckBox
    private lateinit var etMinConfidence: EditText

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_settings)

        etUrl = findViewById(R.id.etServerIp)
        etApiKey = findViewById(R.id.etApiKey)
        etAccountId = findViewById(R.id.etAccountId)
        etMt5Broker = findViewById(R.id.etMt5Broker)
        etMt5Server = findViewById(R.id.etMt5Server)
        etMt5Login = findViewById(R.id.etMt5Login)
        etMt5Password = findViewById(R.id.etMt5Password)
        cbMt5Execution = findViewById(R.id.cbMt5Execution)
        cbAutoExecute = findViewById(R.id.cbAutoExecute)
        etMinConfidence = findViewById(R.id.etMinConfidence)
        val btnSave = findViewById<Button>(R.id.btnSave)
        val btnSaveAndConnect = findViewById<Button>(R.id.btnSaveAndConnect)

        lifecycleScope.launch {
            val prefs = applicationContext.dataStore.data.first()
            etUrl.setText(prefs[PrefKeys.SERVER_URL] ?: DEFAULT_SERVER_URL)
            etApiKey.setText(prefs[PrefKeys.API_KEY] ?: "")
            etAccountId.setText(prefs[PrefKeys.ACCOUNT_ID] ?: "")
            etMt5Broker.setText(prefs[PrefKeys.MT5_BROKER_NAME] ?: DEFAULT_BROKER_NAME)
            etMt5Server.setText(prefs[PrefKeys.MT5_SERVER] ?: "")
            etMt5Login.setText(prefs[PrefKeys.MT5_LOGIN] ?: "")
            etMt5Password.setText(prefs[PrefKeys.MT5_PASSWORD] ?: "")
            cbMt5Execution.isChecked = prefs[PrefKeys.MT5_EXECUTION_ENABLED] ?: true
            cbAutoExecute.isChecked = prefs[PrefKeys.AUTO_EXECUTE] ?: false
            etMinConfidence.setText(
                prefs[PrefKeys.MIN_CONFIDENCE] ?: DEFAULT_MIN_CONFIDENCE.toString()
            )
        }

        btnSave.setOnClickListener {
            lifecycleScope.launch {
                persistSettings()
                Toast.makeText(this@SettingsActivity, "Settings saved", Toast.LENGTH_SHORT).show()
                finish()
            }
        }

        btnSaveAndConnect.setOnClickListener {
            lifecycleScope.launch {
                persistSettings()
                val ok = connectMt5()
                if (ok) {
                    Toast.makeText(
                        this@SettingsActivity,
                        "Saved and MT5 connect requested",
                        Toast.LENGTH_LONG
                    ).show()
                    finish()
                }
            }
        }
    }

    private suspend fun persistSettings() {
        applicationContext.dataStore.edit { settings ->
            settings[PrefKeys.SERVER_URL] = etUrl.text.toString().trim()
            settings[PrefKeys.API_KEY] = etApiKey.text.toString().trim()
            settings[PrefKeys.ACCOUNT_ID] = etAccountId.text.toString().trim()
            settings[PrefKeys.MT5_BROKER_NAME] =
                etMt5Broker.text.toString().trim().ifBlank { DEFAULT_BROKER_NAME }
            settings[PrefKeys.MT5_SERVER] = etMt5Server.text.toString().trim()
            settings[PrefKeys.MT5_LOGIN] = etMt5Login.text.toString().trim()
            settings[PrefKeys.MT5_PASSWORD] = etMt5Password.text.toString()
            settings[PrefKeys.MT5_EXECUTION_ENABLED] = cbMt5Execution.isChecked
            settings[PrefKeys.AUTO_EXECUTE] = cbAutoExecute.isChecked
            settings[PrefKeys.MIN_CONFIDENCE] =
                etMinConfidence.text.toString().trim().ifBlank {
                    DEFAULT_MIN_CONFIDENCE.toString()
                }
        }
    }

    private suspend fun connectMt5(): Boolean {
        val login = etMt5Login.text.toString().trim()
        val password = etMt5Password.text.toString()
        val server = etMt5Server.text.toString().trim()
        if (login.isEmpty() || password.isEmpty() || server.isEmpty()) {
            Toast.makeText(
                this,
                "MT5 login, password and server are required to connect",
                Toast.LENGTH_LONG
            ).show()
            return false
        }

        val prefs = applicationContext.dataStore.data.first()
        val accountId = prefs[PrefKeys.ACCOUNT_ID]?.takeIf { it.isNotBlank() }
            ?: android.provider.Settings.Secure.getString(
                contentResolver,
                android.provider.Settings.Secure.ANDROID_ID
            )
        val broker = etMt5Broker.text.toString().trim().ifBlank { DEFAULT_BROKER_NAME }

        return try {
            val api = RetrofitClient.getApiService(this)
            val body = Mt5ConnectRequest(
                account_id = accountId,
                broker_name = broker,
                server = server,
                login = login,
                trading_password = password,
                execution_enabled = cbMt5Execution.isChecked
            )
            val response = api.connectMt5(body)
            if (response.isSuccessful) {
                true
            } else {
                val err = try {
                    response.errorBody()?.string()?.take(300)
                } catch (_: Exception) {
                    null
                }
                Toast.makeText(
                    this,
                    "Connect failed ${response.code()}: ${err ?: ""}",
                    Toast.LENGTH_LONG
                ).show()
                false
            }
        } catch (e: Exception) {
            Toast.makeText(this, "Connect error: ${e.message}", Toast.LENGTH_LONG).show()
            false
        }
    }
}
