package com.aegis.mobile.network

import android.content.Context
import com.aegis.mobile.data.DEFAULT_SERVER_URL
import com.aegis.mobile.data.PrefKeys
import com.aegis.mobile.data.dataStore
import com.google.gson.GsonBuilder
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.runBlocking
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.util.concurrent.TimeUnit

object RetrofitClient {

    /**
     * Resolves the base URL to hit. Prefers the new SERVER_URL pref (a
     * full "https://your-app.onrender.com/" style URL). Falls back to
     * the legacy SERVER_IP pref (bare LAN IP) wrapped as
     * "http://ip:5000/" ONLY for backward compatibility with devices
     * that saved settings before this update - Render itself is never
     * reachable that way (it terminates HTTPS on 443, not a raw
     * IP:5000, and Android blocks cleartext http by default).
     */
    private suspend fun resolveBaseUrl(context: Context): String {
        val prefs = context.dataStore.data.first()

        prefs[PrefKeys.SERVER_URL]?.let { url ->
            if (url.isNotBlank()) {
                return if (url.endsWith("/")) url else "$url/"
            }
        }

        prefs[PrefKeys.SERVER_IP]?.let { ip ->
            if (ip.isNotBlank()) {
                return "http://$ip:5000/"
            }
        }

        return DEFAULT_SERVER_URL
    }

    fun getApiService(context: Context): ApiService {
        val baseUrl = runBlocking { resolveBaseUrl(context) }

        val apiKey = runBlocking {
            context.dataStore.data.first()[PrefKeys.API_KEY] ?: ""
        }

        val logging = HttpLoggingInterceptor().apply {
            level = HttpLoggingInterceptor.Level.BODY
        }

        val authInterceptor = okhttp3.Interceptor { chain ->
            val newRequest = chain.request().newBuilder()
                .addHeader("X-API-Key", apiKey)
                .build()

            chain.proceed(newRequest)
        }

        // Timeouts sized for Render free-tier cold starts (container wake
        // + Postgres/Redis + first OpenCV load can exceed 30s). Live
        // captures after the service is warm finish well under these.
        val client = OkHttpClient.Builder()
            .addInterceptor(authInterceptor)
            .addInterceptor(logging)
            .connectTimeout(30, TimeUnit.SECONDS)
            .readTimeout(90, TimeUnit.SECONDS)
            .writeTimeout(60, TimeUnit.SECONDS)
            .callTimeout(120, TimeUnit.SECONDS)
            .retryOnConnectionFailure(true)
            .build()

        val gson = GsonBuilder()
            .setLenient()
            .create()

        return Retrofit.Builder()
            .baseUrl(baseUrl)
            .client(client)
            .addConverterFactory(GsonConverterFactory.create(gson))
            .build()
            .create(ApiService::class.java)
    }
}
