package com.aegis.mobile.data

import android.content.Context
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore

// Single shared DataStore instance for the whole app.
val Context.dataStore by preferencesDataStore(name = "aegis_settings")

object PrefKeys {

    // Full HTTPS base URL for the AEGIS backend (Render, etc.)
    val SERVER_URL = stringPreferencesKey("server_url")

    // Legacy LAN IP fallback (RetrofitClient.resolveBaseUrl)
    val SERVER_IP = stringPreferencesKey("server_ip")

    val ACCOUNT_ID = stringPreferencesKey("account_id")
    val API_KEY = stringPreferencesKey("api_key")

    // Safety / execution controls
    val AUTO_EXECUTE = booleanPreferencesKey("auto_execute")
    val MIN_CONFIDENCE = stringPreferencesKey("min_confidence")

    // MT5 broker credentials (sent to backend /api/trading/connect)
    val MT5_LOGIN = stringPreferencesKey("mt5_login")
    val MT5_PASSWORD = stringPreferencesKey("mt5_password")
    val MT5_SERVER = stringPreferencesKey("mt5_server")
    val MT5_BROKER_NAME = stringPreferencesKey("mt5_broker_name")
    val MT5_EXECUTION_ENABLED = booleanPreferencesKey("mt5_execution_enabled")
}

// Default Render URL when Settings has never been saved.
// Override in Settings with your real service hostname.
const val DEFAULT_SERVER_URL =
    "https://aegis-api-0z1p.onrender.com"

const val DEFAULT_MIN_CONFIDENCE = 0.70f
const val DEFAULT_BROKER_NAME = "MetaTrader5"
