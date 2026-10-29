package com.coinepro.hq.core.diag

import android.content.Context
import android.os.Build
import com.coinepro.hq.BuildConfig
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.ApiFailure
import com.coinepro.hq.core.net.FailureSink
import java.io.File
import java.time.Instant
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicLong
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.serialization.Serializable
import kotlinx.serialization.builtins.ListSerializer

/** One recorded failure («خطاخوان»): an API error, a contract mismatch, a network failure or a crash. Never a body, a token, a cookie,
 *  passkey data or customer data: paths are masked ([ErrorLog.maskPath]), only a Problem's code and title are kept, a decoder's
 *  message loses the JSON it quotes, and a crash keeps its classes and line numbers. */
@Serializable
data class ErrorEntry(
    val id: Long,
    val at: String,
    /** http · decode · network · crash */
    val kind: String,
    /** The app's version when it happened (versionName and code). */
    val app: String,
    /** The screen (navigation route) it happened on. */
    val screen: String? = null,
    val method: String? = null,
    val path: String? = null,
    val status: Int? = null,
    val code: String? = null,
    val title: String? = null,
    val requestId: String? = null,
    /** decode: the JSON path the decoder stopped at. */
    val field: String? = null,
    /** decode: what it expected; crash: the exception's class and message. */
    val detail: String? = null,
    /** crash: the stack trace, trimmed. */
    val stack: String? = null,
    /** The same failure again within a minute is counted, not repeated. */
    val count: Int = 1,
    val lastAt: String? = null,
)

/**
 * The app's own error log: the last [MAX] failures, on the phone only, in the app's private files (never backed up). The API records
 * every failed call here through [FailureSink]; [installCrashHandler] saves an uncaught exception before the app dies. Settings →
 * «خطاخوان» shows it, copies it or shares it as a text report ([report]) for the developer.
 */
class ErrorLog(context: Context, private val dir: File = File(context.filesDir, "diag")) : FailureSink {
    private val file = File(dir.apply { mkdirs() }, "errors.json")
    private val io = Executors.newSingleThreadExecutor { r -> Thread(r, "hq-errorlog").apply { isDaemon = true } }
    private val seq = AtomicLong(System.currentTimeMillis())
    private val state = MutableStateFlow(load())

    /** Newest first. */
    val entries: StateFlow<List<ErrorEntry>> = state.asStateFlow()

    /** The screen on show (the shell updates it), recorded with each failure. */
    @Volatile var screen: String? = null

    override fun record(f: ApiFailure): Long? = add(
        ErrorEntry(
            id = seq.incrementAndGet(), at = now(), kind = f.kind, app = APP, screen = screen,
            method = f.method, path = maskPath(f.path), status = f.status, code = f.code?.take(60), title = f.title?.let(::mask)?.take(120),
            requestId = f.requestId?.take(80), field = f.field?.take(200), detail = f.detail?.let(::mask)?.take(300),
        ),
    )

    override fun forget(id: Long) = update { list -> list.filterNot { it.id == id } }

    fun clear() = update { emptyList() }

    /** Records [e] as a crash and writes the log at once (the process is about to end). */
    fun crash(thread: Thread, e: Throwable) {
        val entry = ErrorEntry(
            id = seq.incrementAndGet(), at = now(), kind = "crash", app = APP, screen = screen,
            detail = mask("${e::class.java.name}: ${e.message.orEmpty()}").take(280) + " (thread ${thread.name.take(40)})", stack = stackOf(e),
        )
        val next = (listOf(entry) + state.value).take(MAX)
        state.value = next
        runCatching { write(next) }
    }

    /** Saves an uncaught exception before the default handler ends the app. */
    fun installCrashHandler() {
        val previous = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { t, e ->
            runCatching { crash(t, e) }
            previous?.uncaughtException(t, e)
        }
    }

    /** The whole log as one plain-text report, newest first: a header with the app and the device, then one block per failure. */
    fun report(list: List<ErrorEntry> = state.value): String = buildString {
        appendLine("CoinePro HQ — error log (خطاخوان)")
        appendLine("app ${APP} · ${BuildConfig.APPLICATION_ID} · ${device()}")
        appendLine("exported ${stamp(now())} · ${list.size} ${if (list.size == 1) "entry" else "entries"}, newest first")
        for ((i, e) in list.withIndex()) {
            appendLine()
            append(block(e, i + 1))
        }
    }.trimEnd() + "\n"

    private fun add(e: ErrorEntry): Long {
        var id = e.id
        update { list ->
            val head = list.firstOrNull()
            // The same failure again within a minute (a retry, a refresh loop) raises the count of the newest entry.
            if (head != null && head.same(e) && secondsBetween(head.lastAt ?: head.at, e.at) < 60) {
                id = head.id
                listOf(head.copy(count = head.count + 1, lastAt = e.at, screen = e.screen ?: head.screen)) + list.drop(1)
            } else (listOf(e) + list).take(MAX)
        }
        return id
    }

    private fun update(f: (List<ErrorEntry>) -> List<ErrorEntry>) {
        synchronized(this) { state.value = f(state.value) }
        val snapshot = state.value
        io.execute { runCatching { write(snapshot) } }
    }

    private fun load(): List<ErrorEntry> = runCatching {
        if (file.exists()) Api.json.decodeFromString(ListSerializer(ErrorEntry.serializer()), file.readText()).take(MAX) else emptyList()
    }.getOrDefault(emptyList())

    @Synchronized
    private fun write(list: List<ErrorEntry>) {
        val tmp = File(dir, "errors.json.tmp")
        tmp.writeText(Api.json.encodeToString(ListSerializer(ErrorEntry.serializer()), list))
        if (!tmp.renameTo(file)) { file.delete(); tmp.renameTo(file) }
    }

    companion object {
        const val MAX = 300
        private val APP = "${BuildConfig.VERSION_NAME} (${BuildConfig.VERSION_CODE})"
        private val STAMP = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss 'UTC'").withZone(ZoneOffset.UTC)

        /** The app's clock (pinned in the screenshot tests). */
        fun now(): String = com.coinepro.hq.core.format.HqClock.now().toString()

        fun stamp(iso: String): String = runCatching { STAMP.format(Instant.parse(iso)) }.getOrDefault(iso)

        fun device(): String = "${Build.MANUFACTURER} ${Build.MODEL} · Android ${Build.VERSION.RELEASE} (API ${Build.VERSION.SDK_INT})"

        private fun secondsBetween(a: String, b: String): Long =
            runCatching { java.time.Duration.between(Instant.parse(a), Instant.parse(b)).seconds }.getOrDefault(Long.MAX_VALUE)

        private fun ErrorEntry.same(o: ErrorEntry) =
            kind == o.kind && method == o.method && path == o.path && status == o.status && code == o.code && field == o.field && kind != "crash"

        private val UUID = Regex("\\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\\b")
        private val HEX = Regex("\\b[0-9a-fA-F]{16,}\\b")
        private val EMAIL = Regex("[\\w.+-]+@[\\w-]+(\\.[\\w-]+)+")
        /** An international number or an Iranian mobile (09…); a date ("2026-10-17") is not a phone. */
        private val PHONE = Regex("\\+\\d[\\d ()-]{7,}\\d|\\b09\\d{9}\\b")
        private val TOKEN = Regex("\\b[A-Za-z0-9_-]{28,}\\b")
        private val LONGNUM = Regex("(?<![A-Z]-)\\b\\d{7,}\\b")
        /** Query parameters whose values say nothing about anyone; every other value is dropped (a search, a cursor). */
        private val SAFE_QUERY = setOf(
            "period", "status", "state", "kind", "unrated", "seen", "category", "limit", "company", "risk", "level", "scope", "mode",
            "purpose", "active", "day", "from", "to", "role", "latest", "subject_kind", "channel", "department", "month", "type",
        )

        /** Ids, hashes, tokens, e-mail addresses and phone numbers out of a sentence; refs (`D-000123`) and codes (`TY-CEO`) stay. */
        fun mask(s: String): String = s
            .replace(UUID, "{id}").replace(EMAIL, "{email}").replace(HEX, "{hash}").replace(TOKEN, "{token}")
            .replace(PHONE, "{phone}").replace(LONGNUM, "{n}")

        /** A request path with its ids masked and its query reduced to the parameters that carry no data about anyone. */
        fun maskPath(path: String): String {
            val p = path.substringBefore('?')
            val q = path.substringAfter('?', "")
            val segs = p.split('/').joinToString("/") { seg ->
                val s = java.net.URLDecoder.decode(seg, "UTF-8")
                when {
                    UUID.matches(s) -> "{id}"
                    EMAIL.containsMatchIn(s) -> "{email}"
                    HEX.matches(s) -> "{hash}"
                    TOKEN.matches(s) -> "{token}"
                    LONGNUM.matches(s) -> "{n}"
                    else -> mask(s)
                }
            }
            if (q.isBlank()) return segs
            val kept = q.split('&').mapNotNull { kv ->
                val k = kv.substringBefore('=')
                if (k.isBlank()) null else if (k in SAFE_QUERY) "$k=${mask(java.net.URLDecoder.decode(kv.substringAfter('=', ""), "UTF-8"))}" else "$k=…"
            }
            return if (kept.isEmpty()) segs else segs + "?" + kept.joinToString("&")
        }

        /** The stack of [e] and its causes, our frames and the framework's first few, at most ~40 lines. */
        fun stackOf(e: Throwable): String = buildString {
            var t: Throwable? = e
            var depth = 0
            while (t != null && depth < 4) {
                if (depth > 0) appendLine("caused by ${t::class.java.name}: ${mask(t.message.orEmpty()).take(200)}")
                for (f in t.stackTrace.take(if (depth == 0) 24 else 8)) appendLine("  at $f")
                t = t.cause?.takeIf { it !== t }
                depth++
            }
        }.trimEnd().take(6000)

        /** One entry as the report shows it: a heading line and the facts beneath, each on its own line. */
        fun block(e: ErrorEntry, n: Int): String = buildString {
            val what = when (e.kind) {
                "decode" -> "contract mismatch (the answer does not decode)"
                "http" -> "HTTP error"
                "network" -> "network failure (no answer)"
                "crash" -> "crash"
                else -> e.kind
            }
            appendLine("#$n · ${stamp(e.at)} · $what" + if (e.count > 1) " ×${e.count} (last ${stamp(e.lastAt ?: e.at)})" else "")
            appendLine("app: ${e.app}" + (e.screen?.let { " · screen: $it" } ?: ""))
            if (e.method != null || e.path != null) appendLine("request: ${e.method.orEmpty()} ${e.path.orEmpty()}" + (e.status?.let { " → $it" } ?: ""))
            if (e.code != null || e.title != null) appendLine("problem: ${listOfNotNull(e.code, e.title).joinToString(" — ")}")
            e.field?.let { appendLine("field: $it") }
            e.detail?.let { appendLine("detail: $it") }
            e.requestId?.let { appendLine("request-id: $it") }
            e.stack?.let { appendLine("stack:"); appendLine(it) }
        }
    }
}
