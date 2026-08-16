package com.aegis.mobile.network

import com.aegis.mobile.models.AnalysisResponse
import com.aegis.mobile.models.CaptureRoi
import com.aegis.mobile.models.HeartbeatRequest
import com.aegis.mobile.models.Mt5ConnectRequest
import okhttp3.MultipartBody
import okhttp3.RequestBody
import retrofit2.Response
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.Multipart
import retrofit2.http.POST
import retrofit2.http.Part
import retrofit2.http.Path
import retrofit2.http.Query

interface ApiService {

    @Multipart
    @POST("/aegis/analyze")
    suspend fun analyzeScreenshot(
        @Part image: MultipartBody.Part,
        @Part("account_id") accountId: RequestBody,
        @Part("captured_at_ms") capturedAtMs: RequestBody
    ): Response<AnalysisResponse>

    @POST("/api/devices/heartbeat")
    suspend fun sendHeartbeat(@Body heartbeat: HeartbeatRequest): Response<Unit>

    @GET("/api/config/capture-roi")
    suspend fun getCaptureRoi(): Response<CaptureRoi>

    @POST("/api/trading/connect")
    suspend fun connectMt5(@Body body: Mt5ConnectRequest): Response<Map<String, Any>>

    @POST("/api/trading/disconnect/{accountId}")
    suspend fun disconnectMt5(@Path("accountId") accountId: String): Response<Map<String, Any>>

    @GET("/api/trading/health")
    suspend fun tradingHealth(@Query("account_id") accountId: String): Response<Map<String, Any>>

    @GET("/")
    suspend fun pingRoot(): Response<Map<String, Any>>

    @GET("/health")
    suspend fun pingHealth(): Response<Map<String, Any>>

    @POST("/api/devices/register")
    suspend fun registerDevice(@Body body: Map<String, @JvmSuppressWildcards Any>): Response<Map<String, Any>>

    @GET("/api/templates/active")
    suspend fun getActiveTemplates(): Response<Map<String, @JvmSuppressWildcards Any>>

    @POST("/api/support/report")
    suspend fun reportIssue(@Body body: Map<String, @JvmSuppressWildcards Any?>): Response<Map<String, Any>>

}
