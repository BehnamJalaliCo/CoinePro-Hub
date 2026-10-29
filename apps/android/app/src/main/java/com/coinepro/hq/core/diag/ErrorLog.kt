package com.coinepro.hq.core.diag

import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.Build
import com.coinepro.hq.BuildConfig
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.ApiFailure
import com.coinepro.hq.core.net.FailureSink
import java.io.File
import java.time.Instant
import java.time.ZoneId
import java.time.ZoneOffset
import java.time.format.DateTimeFormatter
import java.util.concurrent.Executors
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.serialization.Serializable
import kotlinx.serialization.builtins.ListSerializer

/**
 * One entry of «خطاخوان»: an API error, a contract mismatch, a network failure, a burst of them while the hub was unreachable, a crash,
 * a stream that dropped or came back, a passkey or speech failure, or the start of a session. Never a body, a token, a cookie, passkey
 * data or customer data: paths are masked ([ErrorLog.maskPath]), free text is redacted and masked ([ErrorLog.mask]), only an allow-list of
 * response headers is kept ([ErrorLog.safeHeaders]), and a crash keeps its classes and line numbers.
 */
@Serializable
data class ErrorEntry(
    /** The monotonic sequence number within this version's log (1 is the session that opened it). */
    val id: Long,
    /** UTC, with milliseconds; shown in the owner's zone and in UTC. */
    val at: String,
    /** http · decode · network · unreachable · stream · crash · passkey · speech · session · app */
    val kind: String,
    /** error · warning · info */
    val level: String = LEVEL_ERROR,
    /** The app's version when it happened (versionName and code). */
    val app: String,
    /** The screen (navigation route) it happened on. */
    val screen: String? = null,
    val method: String? = null,
    val path: String? = null,
    val status: Int? = null,
    val code: String? = null,
    val title: String? = null,
    /** The server's own sentence (the Problem's detail or Persian message), trimmed, redacted and masked. */
    val message: String? = null,
    /** The hub's X-Request-ID: the app sends its own on every call and the hub echoes it, so the hub's logs match this entry. */
    val requestId: String? = null,
    val durationMs: Long? = null,
    /** wifi · cellular · ethernet · vpn · offline · other */
    val network: String? = null,
    /** Whether the app was on screen. */
    val foreground: Boolean? = null,
    /** The last screens and actions before it, oldest first ("14:02:10.120 screen home"). */
    val breadcrumbs: List<String> = emptyList(),
    /** An allow-list of the response's headers (server, via, retry-after, content-type), redacted. */
    val headers: Map<String, String> = emptyMap(),
    /** decode: the JSON path the decoder stopped at. */
    val field: String? = null,
    /** decode: what it expected; crash: the exception's class and message; others: what happened. */
    val detail: String? = null,
    /** crash: the stack trace, trimmed. */
    val stack: String? = null,
    /** The same failure again within a minute is counted, not repeated; a burst counts its requests. */
    val count: Int = 1,
    val lastAt: String? = null,
    /** unreachable: how many of each failure ("502" → 12, "network" → 3). */
    val tally: Map<String, Int> = emptyMap(),
    /** unreachable: the requests that failed, at most [ErrorLog.BURST_PATHS]. */
    val paths: List<String> = emptyList(),
) {
    val transient: Boolean get() = isTransient(kind, status, code)
}

const val LEVEL_ERROR = "error"
const val LEVEL_WARNING = "warning"
const val LEVEL_INFO = "info"

/** A 502, 503 or 504 (the proxy answering for a hub that is not there) or no answer at all: what a restarting hub looks like. */
fun isTransient(kind: String, status: Int?, code: String? = "hub_unreachable"): Boolean = when (kind) {
    "network" -> true
    "stream" -> status == null || (status in 502..504 && code == "hub_unreachable")
    "http" -> status in 502..504 && code == "hub_unreachable"
    else -> false
}

/** The log of an earlier version of the app, kept on the phone and shown apart. */
data class ArchivedLog(val app: String, val entries: Int, val file: File)

@Serializable
private data class Stored(val app: String, val entries: List<ErrorEntry> = emptyList())

/**
 * The app's own forensic log («خطاخوان»): every failure of this version of the app, on the phone only, in the app's private files (never
 * backed up). A new version starts an empty log and keeps the previous one apart ([archives], the last [KEEP_VERSIONS]). The API records
 * every failed call through [FailureSink] (a burst of 502s while the hub restarts becomes one entry); [installCrashHandler] saves an
 * uncaught exception before the app dies; [note] records the rest (the stream, passkeys, speech); each launch opens with a session line.
 */
class ErrorLog(
    private val context: Context,
    private val dir: File = File(context.filesDir, "diag"),
    val app: String = APP,
    startSession: Boolean = true,
) : FailureSink {
    private val file = File(dir.apply { mkdirs() }, "current.json")
    private val archiveDir = File(dir, "versions").apply { mkdirs() }
    private val io = Executors.newSingleThreadExecutor { r -> Thread(r, "hq-errorlog").apply { isDaemon = true } }
    private val state = MutableStateFlow(open())
    private var seq: Long = state.value.maxOfOrNull { it.id } ?: 0L
    private val crumbs = ArrayDeque<String>()

    /** Newest first. */
    val entries: StateFlow<List<ErrorEntry>> = state.asStateFlow()

    /** The screen on show (the shell updates it): recorded with each entry and as a breadcrumb. */
    @Volatile var screen: String? = null
        set(value) {
            if (value != null && value != field) crumb("screen $value")
            field = value
        }

    /** Whether the app is on screen (the process lifecycle updates it). */
    @Volatile var foreground: Boolean = true
        set(value) {
            if (value != field) crumb(if (value) "app foreground" else "app background")
            field = value
        }

    init {
        if (startSession) note("session", LEVEL_INFO, "app started", "app started v$app on ${device()}")
    }

    /** A step before a failure: a screen, a sheet, the stream's state, an action. The last [CRUMBS] are kept with each entry. */
    fun crumb(text: String) {
        synchronized(crumbs) {
            crumbs.addLast("${clock(now())} ${mask(text).take(80)}")
            while (crumbs.size > CRUMBS) crumbs.removeFirst()
        }
    }

    private fun trail(): List<String> = synchronized(crumbs) { crumbs.toList() }

    override fun record(f: ApiFailure): Long? = add(
        ErrorEntry(
            id = 0, at = now(), kind = f.kind, level = f.level ?: levelOf(f), app = app, screen = screen,
            method = f.method, path = maskPath(f.path), status = f.status, code = f.code?.take(60), title = f.title?.let(::mask)?.take(120),
            message = f.message?.let(::mask)?.take(300), requestId = f.requestId?.take(80), durationMs = f.durationMs,
            network = network(), foreground = foreground, breadcrumbs = trail(), headers = safeHeaders(f.headers),
            field = f.field?.take(200), detail = f.detail?.let(::mask)?.take(300),
        ),
    )

    /** Anything that is not an API call: the stream dropped or came back, a passkey or speech failure, the app's own moments. */
    fun note(kind: String, level: String, title: String, detail: String? = null, code: String? = null): Long = add(
        ErrorEntry(
            id = 0, at = now(), kind = kind, level = level, app = app, screen = screen, code = code?.take(60), title = mask(title).take(120),
            detail = detail?.let(::mask)?.take(300), network = network(), foreground = foreground,
            breadcrumbs = if (level == LEVEL_INFO) emptyList() else trail(),
        ),
    )

    override fun forget(id: Long) = update { list -> list.filterNot { it.id == id && it.kind != "unreachable" } }

    /** Empties this version's log (the archived versions stay). */
    fun clear() = update { emptyList() }

    /** Records [e] as a crash and writes the log at once (the process is about to end); the next launch shows it. */
    fun crash(thread: Thread, e: Throwable) {
        val entry = ErrorEntry(
            id = next(), at = now(), kind = "crash", level = LEVEL_ERROR, app = app, screen = screen,
            detail = mask("${e::class.java.name}: ${e.message.orEmpty()}").take(280) + " (thread ${thread.name.take(40)})", stack = stackOf(e),
            network = network(), foreground = foreground, breadcrumbs = trail(),
        )
        val next = synchronized(this) { (listOf(entry) + state.value).take(MAX).also { state.value = it } }
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

    // ----------------------------------------------------------- versions --
    /** The logs of earlier versions, newest first. */
    fun archives(): List<ArchivedLog> = archiveFiles()
        .mapNotNull { f -> readStored(f)?.let { ArchivedLog(it.app, it.entries.size, f) } }

    /** One earlier version's entries, newest first. */
    fun archived(app: String): List<ErrorEntry> = archives().firstOrNull { it.app == app }?.let { readStored(it.file)?.entries }.orEmpty()

    // ------------------------------------------------------------- report --
    /** The log as one plain-text report, newest first: a header with the app, the device, the zone and the export time, then one block
     *  per entry. */
    fun report(list: List<ErrorEntry> = state.value, version: String = app): String = buildString {
        val stamp = now()
        appendLine("CoinePro HQ — error log (خطاخوان)")
        appendLine("app $version · ${BuildConfig.APPLICATION_ID}" + if (version != app) " (an earlier version; this phone runs $app)" else "")
        appendLine("device ${device()}")
        appendLine("time zone $OWNER_ZONE (the owner's) · device ${ZoneId.systemDefault().id}")
        appendLine("exported ${local(stamp)} $OWNER_ZONE · ${utc(stamp)} UTC")
        val e = list.count { it.level == LEVEL_ERROR }
        val w = list.count { it.level == LEVEL_WARNING }
        val i = list.count { it.level == LEVEL_INFO }
        appendLine("${list.size} ${if (list.size == 1) "entry" else "entries"} ($e error, $w warning, $i info), newest first")
        for (x in list) {
            appendLine()
            append(block(x))
        }
    }.trimEnd() + "\n"

    // ------------------------------------------------------------ storage --
    private fun next(): Long = synchronized(this) { ++seq }

    private fun add(e0: ErrorEntry): Long {
        var id = 0L
        update { list ->
            val e = e0.copy(id = ++seq)
            id = e.id
            val head = list.firstOrNull()
            when {
                e.transient -> {
                    // A burst while the hub restarts: the failures of the last [BURST_WINDOW_S] collapse into one "hub unreachable" entry.
                    if (head != null && head.kind == "unreachable" && secondsBetween(head.lastAt ?: head.at, e.at) <= BURST_WINDOW_S) {
                        id = head.id
                        listOf(merge(head, e)) + list.drop(1)
                    } else {
                        val recent = list.takeWhile { it.transient && secondsBetween(it.lastAt ?: it.at, e.at) <= BURST_WINDOW_S }
                        if (recent.sumOf { it.count } + 1 >= BURST_MIN) {
                            val chrono = recent.reversed() + e
                            var burst = burstOf(chrono.first())
                            for (x in chrono.drop(1)) burst = merge(burst, x)
                            id = burst.id
                            (listOf(burst) + list.drop(recent.size)).take(MAX)
                        } else plain(list, e).also { id = it.first().id }
                    }
                }
                else -> plain(list, e).also { id = it.first().id }
            }
        }
        return id
    }

    /** The same failure again within a minute (a retry, a refresh loop) raises the count of the newest entry. */
    private fun plain(list: List<ErrorEntry>, e: ErrorEntry): List<ErrorEntry> {
        val head = list.firstOrNull()
        return if (head != null && head.same(e) && secondsBetween(head.lastAt ?: head.at, e.at) < 60) {
            listOf(head.copy(count = head.count + 1, lastAt = e.at, screen = e.screen ?: head.screen, durationMs = e.durationMs ?: head.durationMs)) + list.drop(1)
        } else (listOf(e) + list).take(MAX)
    }

    private fun update(f: (List<ErrorEntry>) -> List<ErrorEntry>) {
        val snapshot = synchronized(this) { f(state.value).also { state.value = it } }
        io.execute { runCatching { write(snapshot) } }
    }

    /** The current version's log; another version's is archived first (and a log from before versions were kept, too). */
    private fun open(): List<ErrorEntry> {
        val legacy = File(dir, "errors.json")
        if (legacy.exists()) {
            runCatching {
                val old = Api.json.decodeFromString(ListSerializer(ErrorEntry.serializer()), legacy.readText())
                if (old.isNotEmpty()) archive(Stored(old.first().app, old))
            }
            legacy.delete()
        }
        val stored = readStored(file)
        val mine = if (stored != null && stored.app != app) {
            if (stored.entries.isNotEmpty()) archive(stored)
            emptyList()
        } else stored?.entries.orEmpty()
        prune()
        return mine
    }

    /** Archived logs, newest first: each file is named by its archiving order ("000007_0.3.0_300.json"). */
    private fun archiveFiles(): List<File> = archiveDir.listFiles { f -> f.name.endsWith(".json") }?.sortedByDescending { it.name }.orEmpty()

    private fun archive(s: Stored) {
        val next = (archiveFiles().firstOrNull()?.name?.substringBefore('_')?.toIntOrNull() ?: 0) + 1
        val f = File(archiveDir, "%06d_%s.json".format(next, safeName(s.app)))
        runCatching { f.writeText(Api.json.encodeToString(Stored.serializer(), s)) }
    }

    private fun prune() {
        archiveFiles().drop(KEEP_VERSIONS).forEach { it.delete() }
    }

    private fun readStored(f: File): Stored? = runCatching { if (f.exists()) Api.json.decodeFromString(Stored.serializer(), f.readText()) else null }.getOrNull()

    @Synchronized
    private fun write(list: List<ErrorEntry>) {
        val tmp = File(dir, "current.json.tmp")
        tmp.writeText(Api.json.encodeToString(Stored.serializer(), Stored(app, list)))
        if (!tmp.renameTo(file)) { file.delete(); tmp.renameTo(file) }
    }

    /** The phone's connection now: wifi, cellular, ethernet, vpn, other, or offline. */
    private fun network(): String? = runCatching {
        val cm = context.getSystemService(Context.CONNECTIVITY_SERVICE) as? ConnectivityManager ?: return@runCatching null
        val caps = cm.getNetworkCapabilities(cm.activeNetwork) ?: return@runCatching "offline"
        when {
            caps.hasTransport(NetworkCapabilities.TRANSPORT_VPN) -> "vpn"
            caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) -> "wifi"
            caps.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR) -> "cellular"
            caps.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET) -> "ethernet"
            else -> "other"
        }
    }.getOrNull()

    companion object {
        /** Entries kept per version. */
        const val MAX = 1000
        /** Earlier versions kept on the phone. */
        const val KEEP_VERSIONS = 3
        /** Breadcrumbs kept with each entry. */
        const val CRUMBS = 10
        /** Transient failures this close together are one burst … */
        const val BURST_WINDOW_S = 30L
        /** … once there are at least this many. */
        const val BURST_MIN = 3
        const val BURST_PATHS = 8
        const val OWNER_ZONE = com.coinepro.hq.core.format.OWNER_TZ

        private val APP = "${BuildConfig.VERSION_NAME} (${BuildConfig.VERSION_CODE})"
        private val LOCAL = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss.SSS").withZone(ZoneId.of(OWNER_ZONE))
        private val UTC = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss.SSS").withZone(ZoneOffset.UTC)
        private val CLOCK = DateTimeFormatter.ofPattern("HH:mm:ss.SSS").withZone(ZoneId.of(OWNER_ZONE))
        private val ISO = DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'").withZone(ZoneOffset.UTC)

        /** The app's clock (pinned in the screenshot tests), UTC with milliseconds. */
        fun now(): String = ISO.format(com.coinepro.hq.core.format.HqClock.now())

        /** "2026-10-29 14:03:12.345" in the owner's zone (Latin digits). */
        fun local(iso: String): String = runCatching { LOCAL.format(Instant.parse(iso)) }.getOrDefault(iso)
        /** "2026-10-29 10:33:12.345" in UTC. */
        fun utc(iso: String): String = runCatching { UTC.format(Instant.parse(iso)) }.getOrDefault(iso)
        private fun clock(iso: String): String = runCatching { CLOCK.format(Instant.parse(iso)) }.getOrDefault(iso)
        /** Kept for older callers: the UTC stamp. */
        fun stamp(iso: String): String = utc(iso) + " UTC"

        fun device(): String = "${Build.MANUFACTURER} ${Build.MODEL} · Android ${Build.VERSION.RELEASE} (API ${Build.VERSION.SDK_INT})"

        private fun safeName(app: String) = app.replace(Regex("[^A-Za-z0-9._-]+"), "_").take(60)

        private fun secondsBetween(a: String, b: String): Long =
            runCatching { java.time.Duration.between(Instant.parse(a), Instant.parse(b)).seconds }.getOrDefault(Long.MAX_VALUE)

        private fun ErrorEntry.same(o: ErrorEntry) =
            kind == o.kind && level == o.level && method == o.method && path == o.path && status == o.status && code == o.code && field == o.field &&
                title == o.title && detail == o.detail && kind != "crash" && kind != "session"

        private fun tallyKey(e: ErrorEntry): String = if (e.kind == "network" || e.status == null) "network" else e.status.toString()

        /** A burst's first entry: "hub unreachable", starting at [first]. */
        private fun burstOf(first: ErrorEntry): ErrorEntry = ErrorEntry(
            id = first.id, at = first.at, kind = "unreachable", level = LEVEL_WARNING, app = first.app, screen = first.screen,
            code = "hub_unreachable", title = "hub unreachable", network = first.network, foreground = first.foreground,
            breadcrumbs = first.breadcrumbs, count = first.count, lastAt = first.lastAt ?: first.at,
            tally = if (first.kind == "unreachable") first.tally else mapOf(tallyKey(first) to first.count),
            paths = if (first.kind == "unreachable") first.paths else listOfNotNull(first.pathLine()),
            requestId = first.requestId, headers = first.headers,
        )

        private fun ErrorEntry.pathLine(): String? = path?.let { listOfNotNull(method, it).joinToString(" ") + (status?.let { s -> " → $s" } ?: " → no answer") }

        /** One more transient failure in a burst: its count, the tally, the last time and the requests it touched. */
        private fun merge(b: ErrorEntry, x: ErrorEntry): ErrorEntry {
            val base = if (b.kind == "unreachable") b else burstOf(b)
            val k = if (x.kind == "unreachable") null else tallyKey(x)
            val tally = if (k == null) base.tally else base.tally + (k to (base.tally[k] ?: 0) + x.count)
            val paths = (base.paths + listOfNotNull(x.pathLine())).distinct().take(BURST_PATHS)
            return base.copy(count = base.count + x.count, lastAt = x.lastAt ?: x.at, tally = tally, paths = paths, screen = x.screen ?: base.screen, network = x.network ?: base.network)
        }

        /** The level of a failed call: a broken contract or a server fault is an error; the rest is a warning. */
        fun levelOf(f: ApiFailure): String = when {
            f.kind == "decode" || f.kind == "crash" -> LEVEL_ERROR
            f.kind == "http" && (f.status ?: 0) >= 500 && f.code != "hub_unreachable" -> LEVEL_ERROR
            else -> LEVEL_WARNING
        }

        private val UUID = Regex("\\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\\b")
        private val HEX = Regex("\\b[0-9a-fA-F]{16,}\\b")
        private val EMAIL = Regex("[\\w.+-]+@[\\w-]+(\\.[\\w-]+)+")
        /** An international number or an Iranian mobile (09…); a date ("2026-10-17") is not a phone. */
        private val PHONE = Regex("\\+\\d[\\d ()-]{7,}\\d|\\b09\\d{9}\\b")
        /** A long run of letters and digits with at least one digit: a token, not a class name ("GetCredentialCancellationException"). */
        private val TOKEN = Regex("\\b(?=[A-Za-z_-]*\\d)[A-Za-z0-9_-]{28,}\\b")
        private val LONGNUM = Regex("(?<![A-Z]-)\\b\\d{7,}\\b")
        /** A secret named in text: `Authorization: Bearer …`, `"password": "…"`, `token=…`, `X-Step-Up: …`; the name stays, the value goes. */
        private val SECRET = Regex(
            "(?i)(\"?(?:authorization|proxy-authorization|cookie|set-cookie|x-step-up|x-api-key|api[_-]?key|access[_-]?token|refresh[_-]?token|session[_-]?token|token|password|passwd|pass|secret|client[_-]?secret|passkey|credential|otp|signature|private[_-]?key)\"?\\s*[:=]\\s*)" +
                "(\"[^\"]*\"|(?:bearer|basic)\\s+[^\\s,;&\"}]+|[^\\s,;&\"}]+)",
        )
        /** Response headers worth keeping (who answered, how long to wait); nothing else is ever logged. */
        private val SAFE_HEADERS = setOf("server", "via", "retry-after", "content-type", "x-request-id", "date", "x-hq-offline")
        private val SECRET_HEADERS = setOf("authorization", "proxy-authorization", "cookie", "set-cookie", "x-step-up", "x-api-key")
        /** Query parameters whose values say nothing about anyone; every other value is dropped (a search, a cursor). */
        private val SAFE_QUERY = setOf(
            "period", "status", "state", "kind", "unrated", "seen", "category", "limit", "company", "risk", "level", "scope", "mode",
            "purpose", "active", "day", "from", "to", "role", "latest", "subject_kind", "channel", "department", "month", "type",
        )

        /** Secrets named in a sentence lose their values; then ids, hashes, tokens, e-mail addresses and phone numbers are masked.
         *  Refs (`D-000123`) and codes (`TY-CEO`) stay. */
        fun mask(s: String): String = redact(s)
            .replace(UUID, "{id}").replace(EMAIL, "{email}").replace(HEX, "{hash}").replace(TOKEN, "{token}")
            .replace(PHONE, "{phone}").replace(LONGNUM, "{n}")

        /** `Authorization: Bearer abc` → `Authorization: {redacted}`; `"password": "x"` → `"password": {redacted}`. */
        fun redact(s: String): String = s.replace(SECRET) { m -> m.groupValues[1] + "{redacted}" }

        /** The response headers the log may keep: the allow-list only, a secret header never, values redacted and masked. */
        fun safeHeaders(h: Map<String, String>): Map<String, String> = h.entries
            .filter { (k, _) -> k.lowercase() in SAFE_HEADERS && k.lowercase() !in SECRET_HEADERS }
            .associate { (k, v) -> k.lowercase() to mask(v).take(120) }

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

        /** What an entry is, in English for the report. */
        fun what(e: ErrorEntry): String = when (e.kind) {
            "decode" -> "contract mismatch (the answer does not decode)"
            "http" -> "HTTP error"
            "network" -> "network failure (no answer)"
            "unreachable" -> "hub unreachable, ${e.count} ${if (e.count == 1) "request" else "requests"}, ${clock(e.at)}–${clock(e.lastAt ?: e.at)}"
            "stream" -> "live stream: ${e.title ?: "dropped"}"
            "crash" -> "crash"
            "passkey" -> "passkey: ${e.title ?: "failed"}"
            "speech" -> "speech recognition: ${e.title ?: "failed"}"
            "session" -> "session: ${e.title ?: "started"}"
            else -> e.title ?: e.kind
        }

        /** One entry as the report shows it: a heading line and the facts beneath, each on its own line. */
        fun block(e: ErrorEntry, n: Long = e.id): String = buildString {
            appendLine("#$n · ${e.level} · ${what(e)}" + if (e.count > 1 && e.kind != "unreachable") " ×${e.count}" else "")
            appendLine("  time: ${local(e.at)} $OWNER_ZONE · ${utc(e.at)} UTC" + if (e.lastAt != null && e.lastAt != e.at) " (last ${local(e.lastAt)} · ${utc(e.lastAt)} UTC)" else "")
            appendLine("  app: ${e.app}" + listOfNotNull(
                e.screen?.let { "screen: $it" },
                e.foreground?.let { if (it) "foreground" else "background" },
                e.network?.let { "network: $it" },
            ).joinToString("") { " · $it" })
            if (e.method != null || e.path != null) appendLine("  request: ${e.method.orEmpty()} ${e.path.orEmpty()}" + (e.status?.let { " → $it" } ?: "") + (e.durationMs?.let { " · $it ms" } ?: ""))
            if (e.tally.isNotEmpty()) appendLine("  failures: " + e.tally.entries.sortedByDescending { it.value }.joinToString(", ") { "${it.key} ×${it.value}" })
            if (e.paths.isNotEmpty()) appendLine("  requests: " + e.paths.joinToString(" | "))
            if (e.code != null || e.title != null) appendLine("  problem: ${listOfNotNull(e.code, e.title).joinToString(" — ")}")
            e.message?.let { appendLine("  message: $it") }
            e.field?.let { appendLine("  field: $it") }
            e.detail?.let { appendLine("  detail: $it") }
            e.requestId?.let { appendLine("  request-id: $it") }
            if (e.headers.isNotEmpty()) appendLine("  headers: " + e.headers.entries.joinToString(", ") { "${it.key}=${it.value}" })
            if (e.breadcrumbs.isNotEmpty()) appendLine("  before: " + e.breadcrumbs.joinToString(" › "))
            e.stack?.let { appendLine("  stack:"); appendLine(it.prependIndent("  ")) }
        }
    }
}

/** The log for code that has no graph at hand (speech, passkeys, the stream): set by the app for a real session, null in the demo. */
object Diag {
    @Volatile var log: ErrorLog? = null

    fun note(kind: String, level: String, title: String, detail: String? = null, code: String? = null) { log?.note(kind, level, title, detail, code) }

    fun crumb(text: String) { log?.crumb(text) }
}
