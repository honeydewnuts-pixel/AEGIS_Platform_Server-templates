package com.aegis.mobile.ui

import androidx.lifecycle.LiveData
import androidx.lifecycle.map
import androidx.lifecycle.ViewModel
import com.aegis.mobile.data.SignalRepository
import com.aegis.mobile.models.AnalysisResponse

class StatusViewModel : ViewModel() {

    // Raw latest result from the "brain" server
    val currentResult: LiveData<AnalysisResponse> = SignalRepository.latestResult

    // Convenience streams derived from currentResult, used directly by MainActivity
    val signal: LiveData<String> = currentResult.map { it.signal }
    val details: LiveData<String> = currentResult.map { it.details }
    val confidence: LiveData<Float> = currentResult.map { it.confidence }
}
