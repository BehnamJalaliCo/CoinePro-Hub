package com.coinepro.hq.core.media

import com.coinepro.hq.core.net.FileRef

/**
 * ⟨1.18⟩ Contract §36.1: what a file sent in a session is. `POST /files` takes pictures, films, voice, PDFs (§17.1), and fonts
 * (TrueType, OpenType, WOFF, WOFF2), plain text and Markdown, and ZIP archives. The hub checks every file again by its first bytes
 * and while it streams; this only keeps a pointless upload from starting, and names the file the way the owner calls it.
 *
 * A phone often reports a font (and sometimes a ZIP or a Markdown file) as `application/octet-stream`: those are known by their
 * extension, and sent with their real type.
 */
enum class FileKind(
    /** `FileRef.kind` on the hub. */
    val hub: String,
    /** How the owner calls it. */
    val fa: String,
    /** The most the hub takes. */
    val maxBytes: Long,
) {
    IMAGE("image", "عکس", 20 * MB),
    VIDEO("video", "فیلم", 200 * MB),
    AUDIO("audio", "صدا", 25 * MB),
    PDF("document", "PDF", 30 * MB),
    FONT("font", "فونت", 20 * MB),
    TEXT("document", "متن", 50 * MB),
    ZIP("document", "ZIP", 50 * MB),
    ;

    /** The key a pending file is drawn by (the composer's chip). */
    val key: String get() = name.lowercase()

    companion object {
        fun ofKey(key: String): FileKind? = entries.firstOrNull { it.key == key }
    }
}

private const val MB = 1024L * 1024

/** Everything the session's paperclip asks the system picker for: fonts and Markdown also as the octet-stream phones call them. */
val SESSION_PICKER_TYPES: Array<String> = arrayOf(
    "image/*", "video/*", "audio/*", "application/pdf",
    "font/*", "application/x-font-ttf", "application/x-font-otf", "application/font-sfnt", "application/vnd.ms-opentype",
    "application/font-woff", "application/font-woff2", "application/x-font-woff",
    "text/plain", "text/markdown", "text/x-markdown",
    "application/zip", "application/x-zip-compressed", "application/x-zip",
    "application/octet-stream",
)

private val IMAGE_MIME = setOf("image/jpeg", "image/jpg", "image/pjpeg", "image/png", "image/webp", "image/heic", "image/heif")
private val VIDEO_MIME = setOf("video/mp4", "video/webm", "video/quicktime", "video/3gpp")
private val AUDIO_MIME = setOf(
    "audio/mp4", "audio/x-m4a", "audio/m4a", "audio/aac", "audio/x-aac", "audio/ogg", "audio/opus", "audio/webm",
    "audio/wav", "audio/x-wav", "audio/wave", "audio/vnd.wave", "audio/mpeg", "audio/mp3",
)
private val FONT_MIME = mapOf(
    "font/ttf" to "font/ttf", "font/sfnt" to "font/ttf", "application/x-font-ttf" to "font/ttf", "application/x-font-truetype" to "font/ttf",
    "application/font-sfnt" to "font/ttf",
    "font/otf" to "font/otf", "application/x-font-otf" to "font/otf", "application/x-font-opentype" to "font/otf", "application/vnd.ms-opentype" to "font/otf",
    "font/woff" to "font/woff", "application/font-woff" to "font/woff", "application/x-font-woff" to "font/woff",
    "font/woff2" to "font/woff2", "application/font-woff2" to "font/woff2",
)
private val TEXT_MIME = mapOf("text/plain" to "text/plain", "text/markdown" to "text/markdown", "text/x-markdown" to "text/markdown")
private val ZIP_MIME = setOf("application/zip", "application/x-zip-compressed", "application/x-zip", "multipart/x-zip")

/** By extension, with the type the file is sent as: what a phone that says `application/octet-stream` (or nothing) has picked. */
private val BY_EXT: Map<String, Pair<FileKind, String>> = mapOf(
    "jpg" to (FileKind.IMAGE to "image/jpeg"), "jpeg" to (FileKind.IMAGE to "image/jpeg"), "png" to (FileKind.IMAGE to "image/png"),
    "webp" to (FileKind.IMAGE to "image/webp"), "heic" to (FileKind.IMAGE to "image/heic"), "heif" to (FileKind.IMAGE to "image/heif"),
    "mp4" to (FileKind.VIDEO to "video/mp4"), "webm" to (FileKind.VIDEO to "video/webm"), "mov" to (FileKind.VIDEO to "video/quicktime"),
    "m4a" to (FileKind.AUDIO to "audio/mp4"), "aac" to (FileKind.AUDIO to "audio/aac"), "ogg" to (FileKind.AUDIO to "audio/ogg"),
    "opus" to (FileKind.AUDIO to "audio/ogg"), "oga" to (FileKind.AUDIO to "audio/ogg"), "wav" to (FileKind.AUDIO to "audio/wav"),
    "mp3" to (FileKind.AUDIO to "audio/mpeg"),
    "pdf" to (FileKind.PDF to "application/pdf"),
    "ttf" to (FileKind.FONT to "font/ttf"), "otf" to (FileKind.FONT to "font/otf"), "woff" to (FileKind.FONT to "font/woff"),
    "woff2" to (FileKind.FONT to "font/woff2"),
    "txt" to (FileKind.TEXT to "text/plain"), "text" to (FileKind.TEXT to "text/plain"), "md" to (FileKind.TEXT to "text/markdown"),
    "markdown" to (FileKind.TEXT to "text/markdown"),
    "zip" to (FileKind.ZIP to "application/zip"),
)

private fun extOf(name: String): String = name.substringAfterLast('/').substringAfterLast('.', "").lowercase()

/**
 * What a picked file is and the type it is sent as, or null when a session does not take it. A font, a ZIP and a Markdown file are
 * known by their extension first (phones disagree on their types); everything else by its type, then by its extension when the phone
 * gave no useful type.
 */
fun sessionFileKind(name: String, mime: String?): Pair<FileKind, String>? {
    val m = mime?.substringBefore(';')?.trim()?.lowercase().orEmpty()
    val ext = extOf(name)
    BY_EXT[ext]?.takeIf { it.first == FileKind.FONT || it.first == FileKind.ZIP || ext == "md" || ext == "markdown" }?.let { return it }
    when {
        m in IMAGE_MIME -> return FileKind.IMAGE to (if (m == "image/jpg" || m == "image/pjpeg") "image/jpeg" else m)
        m in VIDEO_MIME -> return FileKind.VIDEO to m
        m in AUDIO_MIME -> return FileKind.AUDIO to m
        m == "application/pdf" -> return FileKind.PDF to m
        m in FONT_MIME -> return FileKind.FONT to FONT_MIME.getValue(m)
        m in TEXT_MIME -> return FileKind.TEXT to TEXT_MIME.getValue(m)
        m in ZIP_MIME -> return FileKind.ZIP to "application/zip"
    }
    // A type the phone made up or left out: the extension decides. A type it knows and the hub does not (a GIF, a Word file) is refused.
    val vague = m.isEmpty() || m == "application/octet-stream" || m == "binary/octet-stream" || m == "application/unknown" || m == "*/*"
    return if (vague) BY_EXT[ext] else null
}

/** Why a file cannot go in a session, in plain Persian; null when it can. */
fun sessionReject(name: String, mime: String?, size: Long): String? {
    val (kind, _) = sessionFileKind(name, mime) ?: return "«$name»: این نوع فایل را نمیشود فرستاد؛ عکس، فیلم، صدا، PDF، فونت، متن یا ZIP بفرست."
    if (size == 0L) return "«$name»: فایل خالی است."
    if (size > kind.maxBytes) return "«$name»: ${kind.fa} حداکثر ${fileSize(kind.maxBytes)} است و این فایل ${fileSize(size)} است."
    return null
}

/** What a file of the hub is, the way the owner calls it; null for a kind the app does not know yet (shown as «فایل»). */
fun fileKindOf(f: FileRef): FileKind? = when (f.kind) {
    "image" -> FileKind.IMAGE
    "video" -> FileKind.VIDEO
    "audio" -> FileKind.AUDIO
    "font" -> FileKind.FONT
    "document" -> sessionFileKind(f.name, f.mime)?.first?.takeIf { it == FileKind.PDF || it == FileKind.TEXT || it == FileKind.ZIP || it == FileKind.FONT }
    else -> null
}

/** The line under a file's name: its kind (a font with its family) and its size. Sizes stay Latin figures, drawn by the caller. */
fun fileKindFa(f: FileRef): String {
    val k = fileKindOf(f)
    return when {
        k == FileKind.FONT && f.family != null -> "فونت ${f.family}"
        k != null -> k.fa
        else -> "فایل"
    }
}

/** ⟨1.18⟩ The words a turn carries when the owner sent only files and the hub wants a line of text. */
const val FILES_ONLY_TEXT = "فایل"

/** The policy a composer checks its files with: what it takes, what each is, and the type it is sent as. */
interface FilePolicy {
    /** Why [f] cannot go, in Persian; null when it can. */
    fun reject(f: LocalFile): String?

    /** The key the pending file is drawn by (`image` · `video` · `audio` · …). */
    fun kind(f: LocalFile): String

    /** [f] with the type it is sent as. */
    fun normalize(f: LocalFile): LocalFile = f

    companion object {
        /** §17.1 the messages' composer: pictures, films, voice and PDFs. */
        val MESSAGE: FilePolicy = object : FilePolicy {
            override fun reject(f: LocalFile) = Limits.reject(f)
            override fun kind(f: LocalFile) = kindOf(f.mime)
        }

        /** ⟨1.18⟩ §36.1 a session's composer: also fonts, text and ZIP. */
        val SESSION: FilePolicy = object : FilePolicy {
            override fun reject(f: LocalFile) = sessionReject(f.name, f.mime, f.size)
            override fun kind(f: LocalFile) = sessionFileKind(f.name, f.mime)?.first?.key ?: "document"
            override fun normalize(f: LocalFile) = sessionFileKind(f.name, f.mime)?.let { f.copy(mime = it.second) } ?: f
        }
    }
}
