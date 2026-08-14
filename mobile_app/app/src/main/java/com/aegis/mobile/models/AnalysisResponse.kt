package com.aegis.mobile.models

data class AnalysisResponse(
    val signal: String,           // "BUY", "SELL", "HOLD"
    val confidence: Float,        // 0.0 to 1.0
    val details: String,          // human-readable reason
    val timestamp: Long,          // when brain analyzed it (ms)
    val rule_name: String? = null // which rulebook rule fired, if any
)
