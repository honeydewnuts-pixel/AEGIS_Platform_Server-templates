package com.aegis.mobile.data

import androidx.lifecycle.MutableLiveData
import com.aegis.mobile.models.AnalysisResponse

/**
 * In-process bridge between ScreenCaptureService (background) and the UI (StatusViewModel).
 * Both run in the same app process, so a LiveData singleton is enough - no need for
 * broadcasts or a bound service.
 */
object SignalRepository {
    val latestResult = MutableLiveData<AnalysisResponse>()

    // Tracks the last time a trade was actually executed, so we can enforce a cooldown
    // and avoid firing a new trade every single capture cycle (every 3s) on a persistent signal.
    var lastExecutionTimeMs: Long = 0L
}
