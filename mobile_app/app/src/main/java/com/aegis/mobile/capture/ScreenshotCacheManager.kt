package com.aegis.mobile.capture

import android.content.Context
import android.graphics.Bitmap
import android.util.Log
import java.io.File
import java.io.FileOutputStream

/**
 * Disk-backed FIFO cache for screenshots that couldn't be sent (backend
 * unreachable, timeout, non-2xx response). Filenames encode the original
 * capture timestamp so files sort chronologically for free, and so the
 * backend can be told the real capture time rather than "whenever it
 * finally got sent" - see IndicatorHistoryService.kt on the backend for
 * why that ordering matters.
 *
 * Bounded to MAX_CACHED_FILES - if the backend is down for a long time,
 * the OLDEST cached screenshots are dropped to make room for newer ones,
 * since more recent chart context is more useful once connectivity
 * returns than very stale frames would be.
 */
class ScreenshotCacheManager(context: Context) {

    companion object {
        private const val MAX_CACHED_FILES = 200   // ~10 minutes of backlog at a 3s interval
        private const val TAG = "AEGIS-Cache"
    }

    private val cacheDir: File = File(context.cacheDir, "pending_screenshots").apply { mkdirs() }

    /** filename pattern: {capturedAtMs}_{accountId}.jpg - sorts chronologically by name. */
    private fun fileFor(capturedAtMs: Long, accountId: String): File =
        File(cacheDir, "${capturedAtMs}_${accountId}.jpg")

    fun cache(bitmap: Bitmap, capturedAtMs: Long, accountId: String) {
        try {
            enforceCapBeforeInsert()
            val file = fileFor(capturedAtMs, accountId)
            FileOutputStream(file).use { out ->
                bitmap.compress(Bitmap.CompressFormat.JPEG, 80, out)
            }
            Log.d(TAG, "Cached screenshot (${pendingCount()} pending)")
        } catch (e: Exception) {
            Log.e(TAG, "Failed to cache screenshot: ${e.message}")
        }
    }

    private fun enforceCapBeforeInsert() {
        val files = listPendingOldestFirst()
        if (files.size >= MAX_CACHED_FILES) {
            val toDrop = files.size - MAX_CACHED_FILES + 1
            files.take(toDrop).forEach {
                Log.w(TAG, "Cache full - dropping oldest pending screenshot: ${it.name}")
                it.delete()
            }
        }
    }

    fun listPendingOldestFirst(): List<File> =
        cacheDir.listFiles()?.filter { it.name.endsWith(".jpg") }?.sortedBy { it.name } ?: emptyList()

    fun pendingCount(): Int = listPendingOldestFirst().size

    fun remove(file: File) {
        file.delete()
    }

    /** Parses "{capturedAtMs}_{accountId}.jpg" back into its parts. */
    fun parse(file: File): Pair<Long, String>? {
        val name = file.nameWithoutExtension
        val parts = name.split("_", limit = 2)
        if (parts.size != 2) return null
        val ts = parts[0].toLongOrNull() ?: return null
        return ts to parts[1]
    }
}
