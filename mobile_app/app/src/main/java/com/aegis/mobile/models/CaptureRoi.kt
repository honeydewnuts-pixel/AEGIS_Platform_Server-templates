package com.aegis.mobile.models

import com.google.gson.annotations.SerializedName

data class CaptureRoi(
    @SerializedName("capture_top_percent") val captureTopPercent: Float,
    @SerializedName("capture_bottom_percent") val captureBottomPercent: Float
)
