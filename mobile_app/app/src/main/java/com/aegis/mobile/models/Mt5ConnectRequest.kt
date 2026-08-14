package com.aegis.mobile.models

/**
 * Body for POST /api/trading/connect — registers MT5 credentials
 * in the backend vault and starts (or reuses) a worker for this account.
 */
data class Mt5ConnectRequest(
    val account_id: String,
    val broker_name: String = "MetaTrader5",
    val server: String,
    val login: String,
    val trading_password: String,
    val investor_password: String? = null,
    val execution_enabled: Boolean = true
)
