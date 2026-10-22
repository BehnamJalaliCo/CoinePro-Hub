package com.coinepro.hq.core.media

import android.content.ContentResolver
import android.content.Context
import android.media.MediaMetadataRetriever
import android.net.Uri
import android.provider.OpenableColumns
import android.util.Base64
import androidx.annotation.OptIn
import androidx.media3.common.util.UnstableApi
import androidx.media3.datasource.DataSource
import androidx.media3.datasource.DefaultDataSource
import androidx.media3.datasource.okhttp.OkHttpDataSource
import coil3.ImageLoader
import coil3.network.okhttp.OkHttpNetworkFetcherFactory
import coil3.request.crossfade
import com.coinepro.hq.core.net.Api
import java.io.File

/** Pictures, films and voice notes for one session: everything loads through the API's OkHttp client, so the
 *  Bearer session and `X-HQ-Client` ride along and nothing bypasses the contract (§17.1). */
class MediaKit(context: Context, private val api: Api) {
    val context: Context = context.applicationContext
    private val app = this.context

    val images: ImageLoader = ImageLoader.Builder(app)
        .components { add(OkHttpNetworkFetcherFactory(callFactory = { api.client })) }
        .crossfade(true)
        .build()

    /** Media3: https through OkHttp; data:, file: and content: handled by the default source. */
    @OptIn(UnstableApi::class)
    val dataSource: DataSource.Factory = DefaultDataSource.Factory(app, OkHttpDataSource.Factory(api.client))

    /** Scratch space for recordings, camera captures and opened documents (cleared by the system when low). */
    fun scratch(dir: String): File = File(app.cacheDir, dir).apply { mkdirs() }

    fun url(id: String, variant: String? = null): String = api.fileUrl(id, variant)

    /** Coil model for an image id: data: URLs (demo) decode to bytes, everything else is a URL. */
    fun imageModel(id: String, variant: String? = null): Any =
        if (id.startsWith("data:")) Base64.decode(id.substringAfter(','), Base64.DEFAULT) else url(id, variant)
}

/** What a picked file is, before anything is uploaded. */
data class LocalFile(val uri: Uri, val name: String, val mime: String, val size: Long)

fun ContentResolver.describe(uri: Uri): LocalFile {
    var name = uri.lastPathSegment ?: "file"
    var size = -1L
    runCatching {
        query(uri, arrayOf(OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE), null, null, null)?.use { c ->
            if (c.moveToFirst()) {
                c.getColumnIndex(OpenableColumns.DISPLAY_NAME).takeIf { it >= 0 }?.let { c.getString(it) }?.let { name = it }
                c.getColumnIndex(OpenableColumns.SIZE).takeIf { it >= 0 && !c.isNull(it) }?.let { size = c.getLong(it) }
            }
        }
    }
    if (size < 0 && uri.scheme == "file") size = uri.path?.let { File(it).length() } ?: -1
    val mime = getType(uri) ?: MIME_BY_EXT[name.substringAfterLast('.', "").lowercase()] ?: "application/octet-stream"
    return LocalFile(uri, name, mime, size)
}

/** Length of a local film in seconds, or null when the platform cannot tell. */
fun videoSeconds(context: Context, uri: Uri): Double? = runCatching {
    MediaMetadataRetriever().run {
        try {
            setDataSource(context, uri)
            extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION)?.toLongOrNull()?.div(1000.0)
        } finally {
            release()
        }
    }
}.getOrNull()

private val MIME_BY_EXT = mapOf(
    "jpg" to "image/jpeg", "jpeg" to "image/jpeg", "png" to "image/png", "webp" to "image/webp", "heic" to "image/heic", "heif" to "image/heif",
    "mp4" to "video/mp4", "webm" to "video/webm", "mov" to "video/quicktime", "m4a" to "audio/mp4", "pdf" to "application/pdf",
    // ⟨1.7⟩ the archive's other document types (§23.2 allowed_mime).
    "txt" to "text/plain", "eml" to "message/rfc822", "docx" to "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
)

fun kindOf(mime: String): String = when {
    mime.startsWith("image/") -> "image"
    mime.startsWith("video/") -> "video"
    mime.startsWith("audio/") -> "audio"
    else -> "document"
}

/** Contract §17.1 limits. The server checks again, by content and while streaming; this only saves a pointless upload. */
object Limits {
    private const val MB = 1024L * 1024
    val types = mapOf(
        "image" to setOf("image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"),
        "video" to setOf("video/mp4", "video/webm", "video/quicktime", "video/3gpp"),
        "audio" to setOf("audio/mp4", "audio/x-m4a", "audio/aac", "audio/ogg", "audio/webm", "audio/wav", "audio/x-wav", "audio/mpeg"),
        "document" to setOf("application/pdf"),
    )
    val max = mapOf("image" to 20 * MB, "video" to 200 * MB, "audio" to 25 * MB, "document" to 30 * MB)
    private val fa = mapOf("image" to "عکس", "video" to "فیلم", "audio" to "صدا", "document" to "PDF")
    const val VIDEO_SECONDS = 600.0
    const val VOICE_SECONDS = 15 * 60

    /** Why a file cannot go, in Persian; null when it can. */
    fun reject(f: LocalFile): String? {
        val kind = kindOf(f.mime)
        if (f.mime !in types.getValue(kind)) return "«${f.name}»: این نوع فایل پذیرفته نمیشود (عکس، فیلم یا PDF)."
        val cap = max.getValue(kind)
        if (f.size > cap) return "«${f.name}»: ${fa[kind]} حداکثر ${fileSize(cap)} است."
        return null
    }
}

fun fileSize(bytes: Long): String = when {
    bytes < 1024 -> "$bytes B"
    bytes < 1024 * 1024 -> "${bytes / 1024} KB"
    bytes < 10L * 1024 * 1024 -> String.format(java.util.Locale.US, "%.1f MB", bytes / 1048576.0)
    else -> "${bytes / 1048576} MB"
}

/** "0:42", "12:05" — figures stay Latin. */
fun clock(seconds: Double): String {
    val s = seconds.toLong().coerceAtLeast(0)
    return "${s / 60}:${(s % 60).toString().padStart(2, '0')}"
}
