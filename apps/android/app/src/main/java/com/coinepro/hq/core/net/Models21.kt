package com.coinepro.hq.core.net

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.longOrNull

// ------------------------------------------------------------------ v1.8 --
// Contract §26 (prompt 17, revised): the holding works on the companies' own servers through a pull runner. Each company server runs
// `hq-runner` under its work user; the runner opens outbound HTTPS to the hub, long-polls for jobs, streams their events and posts results.
// The hub never connects into a company server: no SSH key, no inbound port. A server joins by device-code pairing (the runner shows a
// short code, the owner approves it here with the passkey); detaching revokes the runner's token. Agents (and the owner from this app)
// run commands, read and write files, start Claude Code on the server and map it. Everything runs free except six destructive
// categories, which wait for the owner's seal (`server_destructive`, 🔏 `server.destructive` on `<CODE>:<server>`). Same rules as
// Models.kt: camelCase here, snake_case on the wire. Servers and companies are data: nothing here counts them.

/** One server of the holding (§26.4 `GET /infra/servers`): made by the provisioner, or a company server paired through its runner. */
@Serializable
data class HubServer(
    val id: String,
    val company: String = "",
    val name: String = "",
    /** `provisioned` · `attached` */
    val origin: String = "attached",
    val privateIp: String = "",
    /** The server's own work user the runner runs as (`forex` on FX), never root. */
    val user: String = "",
    /** What the runner reported at pairing (`coinepro-fx`). */
    val hostname: String? = null,
    /** The `hq-runner` version on the server (`0.1.0`). */
    val runnerVersion: String? = null,
    /** `pending` (approved, the runner has not taken its token yet) · `online` · `offline` · `revoked` */
    val state: String = "pending",
    /** The runner's last poll. */
    val lastSeenAt: String? = null,
    /** When the latest `server.map` was taken; null before the first. */
    val mapAt: String? = null,
    /** How the runner reached the hub on its last poll (§26.1a): `private` · `public` (the fallback); null before the first. */
    val via: String? = null,
    /** The round trip of that poll (§26.6). */
    val hubRttMs: Double? = null,
) {
    /** The runner polls: jobs run on it. */
    val online: Boolean get() = state == "online"

    val revoked: Boolean get() = state == "revoked"

    /** The step-up target of every seal scoped to this server (§26.3 `server.destructive`, §26.4 `server.detach`: `<CODE>:<server>`). */
    val target: String get() = "$company:$name"

    /** `forex@coinepro-fx`, as the server's own shell prompt writes it (the private address when the runner sent no hostname). */
    val login: String get() {
        val host = hostname?.takeIf { it.isNotBlank() } ?: privateIp
        return if (user.isBlank()) host else "$user@$host"
    }
}

/** §26.4 `POST /runners/approve {user_code}` 🔏 `server.attach` on `company:<CODE>`. */
@Serializable
data class ApproveIn(val userCode: String)

/**
 * The short code `hq-runner pair` prints on the server (§26.1, `ABCD-1234`): Latin letters and digits, two groups of four. The field
 * formats as the owner types — Persian or Arabic digits become Latin, letters upper case, anything else dropped, the dash put in after
 * the fourth character — so whatever the owner copies or reads off the server lands in the one shape the hub knows.
 */
object PairCode {
    const val LENGTH = 8
    private val VALID = Regex("^[A-Z0-9]{4}-[A-Z0-9]{4}$")

    /** The code as typed so far, formatted: `abcd12` → `ABCD-12`. */
    fun format(raw: String): String {
        val chars = raw.mapNotNull { ch ->
            when (ch) {
                in '0'..'9', in 'A'..'Z' -> ch
                in 'a'..'z' -> ch.uppercaseChar()
                in '۰'..'۹' -> '0' + (ch - '۰')
                in '٠'..'٩' -> '0' + (ch - '٠')
                else -> null
            }
        }.take(LENGTH).joinToString("")
        return if (chars.length > 4) chars.substring(0, 4) + "-" + chars.substring(4) else chars
    }

    fun valid(code: String): Boolean = VALID.matches(code)

    /** Why the hub refused the code, in Persian, from the Problem's code (and its status when the code is not one of these). */
    fun refusal(e: ApiException): String? = when {
        e.code in EXPIRED || e.status == 410 -> "این کد منقضی شده؛ هر کد فقط ۱۵ دقیقه اعتبار دارد. روی سرور دوباره hq-runner pair را اجرا کن و کد تازه را بنویس."
        e.code in UNKNOWN || e.status == 404 -> "این کد پیدا نشد. همان کدی را بنویس که hq-runner pair روی سرور نشان داد."
        e.code in USED -> "این کد یک بار تأیید شده است؛ سرورش در فهرست هست."
        e.code == "company_mismatch" -> "این کد برای شرکت دیگری ساخته شده؛ شرکت درست را انتخاب کن."
        else -> null
    }

    private val EXPIRED = setOf("expired_token", "code_expired", "user_code_expired", "expired")
    private val UNKNOWN = setOf("invalid_user_code", "unknown_user_code", "user_code_unknown", "invalid_code", "not_found")
    private val USED = setOf("code_used", "already_approved", "user_code_used")

    /** The command the server's own Claude runs (§26.1 step 1), the company's code filled in. */
    fun pairCommand(company: String?): String = "hq-runner pair --company ${company?.takeIf { it.isNotBlank() } ?: "<CODE>"} --name <name>"
}

/**
 * One row of a server's activity (§26.4 `GET …/activity`: a Page of jobs and their commands). A job (§26.2) carries `kind`, `args`,
 * `state` and its times; a command inside a job (or the stream's `server.call`) carries `tool`, `cmd_masked` and `duration_ms`. Both are
 * read into this one row; secrets are masked by name and pattern before the hub stores either (§26.3).
 */
@Serializable
data class ServerCall(
    val id: String? = null,
    val at: String = "",
    val actor: Actor = Actor(),
    /** `server.exec` · `server.read` · `server.write` · `server.claude` · `server.map`; a job names its `kind` instead. */
    val tool: String? = null,
    /** A job's kind: `map` · `exec` · `read` · `write` · `claude`. */
    val kind: String? = null,
    /** A job's arguments (`{cmd, cwd?, timeout_s, sudo?}` for `exec`, `{path}` for a file, `{cwd, brief}` for `claude`). */
    val args: JsonObject? = null,
    val summaryFa: String? = null,
    val cmdMasked: String? = null,
    /** Null while the call runs (and for a call waiting for the seal). */
    val exitCode: Int? = null,
    val durationMs: Long? = null,
    /** The Claude Code session the call belongs to (`S-…`, the Workshop's session page). */
    val sessionRef: String? = null,
    /** The full transcript, owner-readable (§26.3). */
    val transcriptUrl: String? = null,
    val server: String? = null,
    /** A job's `queued` · `running` · `awaiting_seal` · `done` · `failed` · `cancelled` (§26.2); a refused call may say `refused`. */
    val state: String? = null,
    val createdAt: String? = null,
    val startedAt: String? = null,
    val finishedAt: String? = null,
)

/** §26.4 `GET/PUT /control/server-policy`: the categories that wait for the owner's seal; everything else runs free. */
@Serializable
data class ServerPolicy(val sealRequired: List<String> = SEAL_CATEGORIES.map { it.key }) {
    fun requires(key: String): Boolean = key in sealRequired

    /** The policy with [key] on or off: the six categories in their canonical order, any key a newer hub adds kept after them. */
    fun with(key: String, on: Boolean): ServerPolicy {
        val set = sealRequired.toMutableSet().apply { if (on) add(key) else remove(key) }
        val known = SEAL_CATEGORIES.map { it.key }
        return ServerPolicy(known.filter { it in set } + sealRequired.filter { it !in known && it in set }.distinct() + (if (on && key !in known && key !in sealRequired) listOf(key) else emptyList()))
    }

    /** What changes from this policy to [next]: each key with whether it now waits for the seal. */
    fun changes(next: ServerPolicy): List<Pair<String, Boolean>> {
        val all = (SEAL_CATEGORIES.map { it.key } + sealRequired + next.sealRequired).distinct()
        return all.mapNotNull { k -> if (requires(k) != next.requires(k)) k to next.requires(k) else null }
    }
}

/** One destructive category: its words, what the gateway catches (Latin, as typed on a server) and why it waits. */
data class SealCategory(val key: String, val titleFa: String, val catches: String, val whyFa: String)

/** The six categories of §26.3, in the contract's order. */
val SEAL_CATEGORIES = listOf(
    SealCategory("db_drop", "پاک کردن یا خالی کردن دیتابیس", "DROP DATABASE · DROP TABLE · TRUNCATE", "داده‌ی مشتری‌ها و تاریخچه، بی‌بازگشت از دست میرود."),
    SealCategory("volume_delete", "پاک کردن volume داده", "docker volume rm · docker compose down -v", "هر چه کانتینرها نگه داشته‌اند با volume میرود."),
    SealCategory("backup_delete", "پاک کردن پشتیبان", "rm -rf …/backups · restic forget --prune", "آخرین راه برگشت است."),
    SealCategory("disk_wipe", "پاک کردن یا پارتیشن کردن دیسک", "mkfs · fdisk · parted · wipefs", "کل دیسک و هر چه رویش است."),
    SealCategory("access_change", "تغییر SSH، کاربرها یا فایروال همین سرور", "sshd_config · authorized_keys · userdel · passwd · ufw · iptables", "ممکن است راه ورود خودت به سرور بسته شود."),
    SealCategory("server_delete", "حذف سرور", "Hetzner API · delete server", "سرور و هر چه رویش است میرود."),
)

fun sealCategory(key: String?): SealCategory? = SEAL_CATEGORIES.firstOrNull { it.key == key }

/** What runs without a card (§26.3), said to the owner in one place. */
val FREE_ON_SERVERS = listOf("کد زدن", "commit و push", "merge", "deploy", "ریستارت سرویس‌ها", "تغییر تنظیمات", "نصب بسته", "اتوماسیون تازه")

// ------------------------------------------------------------------ the server's tools (§26.2) --
val SERVER_TOOL_FA = linkedMapOf(
    "server.exec" to "فرمان",
    "server.read" to "خواندن فایل",
    "server.write" to "نوشتن فایل",
    "server.claude" to "Claude Code",
    "server.map" to "نقشه",
)

/** How a job or call stands (§26.2's job states, plus a refusal the hub answered before queueing). */
enum class CallOutcome { QUEUED, RUNNING, AWAITING_SEAL, OK, FAILED, CANCELLED, REFUSED }

/** One line of a server's activity as the app draws it, from the activity page or from the stream's `server.call` (summary only). */
data class ServerCallRow(
    val at: String,
    val actor: Actor,
    val tool: String,
    val toolFa: String,
    val summaryFa: String,
    val cmd: String?,
    val outcome: CallOutcome,
    val exitCode: Int?,
    /** `41s`, `1m 12s`: a figure, Latin. */
    val duration: String?,
    val sessionRef: String?,
    val transcriptUrl: String?,
    val server: String?,
    /** The folder the job runs in (`args.cwd`: a `claude` job's repository, an `exec`'s working directory). */
    val cwd: String? = null,
) {
    val byOwner: Boolean get() = actor.kind == "owner"
    /** Still to finish: in the queue, running, or held for the seal. */
    val open: Boolean get() = outcome == CallOutcome.QUEUED || outcome == CallOutcome.RUNNING || outcome == CallOutcome.AWAITING_SEAL
}

private fun outcomeOf(exit: Int?, durationMs: Long?, state: String?, code: String?): CallOutcome = when {
    state == "awaiting_seal" || code == "awaiting_seal" -> CallOutcome.AWAITING_SEAL
    state == "refused" || code == "company_locked" || code == "deploy_frozen" -> CallOutcome.REFUSED
    state == "queued" -> CallOutcome.QUEUED
    state == "running" -> CallOutcome.RUNNING
    state == "cancelled" -> CallOutcome.CANCELLED
    state == "failed" -> CallOutcome.FAILED
    state == "done" -> if (exit != null && exit != 0) CallOutcome.FAILED else CallOutcome.OK
    exit == null && durationMs == null -> CallOutcome.RUNNING
    exit == null || exit == 0 -> CallOutcome.OK
    else -> CallOutcome.FAILED
}

private fun argStr(a: JsonObject?, k: String): String? = (a?.get(k) as? JsonPrimitive)?.takeIf { it !is JsonNull }?.contentOrNull?.takeIf { it.isNotBlank() }

/** A job's duration from its times when the hub sent no `duration_ms`. */
private fun spanMs(from: String?, to: String?): Long? {
    val a = from?.let { runCatching { java.time.Instant.parse(it) }.getOrNull() } ?: return null
    val b = to?.let { runCatching { java.time.Instant.parse(it) }.getOrNull() } ?: return null
    return java.time.Duration.between(a, b).toMillis().takeIf { it >= 0 }
}

fun callRow(c: ServerCall): ServerCallRow {
    val tool = c.tool ?: c.kind?.let { "server.$it" } ?: "server.exec"
    val cmd = c.cmdMasked?.takeIf { it.isNotBlank() } ?: argStr(c.args, "cmd") ?: argStr(c.args, "path")
    return ServerCallRow(
        c.at.ifBlank { c.startedAt ?: c.createdAt.orEmpty() }, c.actor, tool, SERVER_TOOL_FA[tool] ?: tool,
        c.summaryFa ?: argStr(c.args, "title") ?: "", cmd,
        outcomeOf(c.exitCode, c.durationMs ?: spanMs(c.startedAt, c.finishedAt), c.state, null), c.exitCode,
        duration(c.durationMs ?: spanMs(c.startedAt, c.finishedAt)), c.sessionRef, c.transcriptUrl, c.server, argStr(c.args, "cwd"),
    )
}

/** The stream's `server.call` (§26.4: one per call, summary only); null for any other event. `actor` may be an Actor or its code. */
fun callRow(e: StreamEvent): ServerCallRow? {
    if (e.type != "server.call") return null
    val d = e.data
    val actor = when (val a = d["actor"]) {
        is JsonObject -> runCatching { Api.json.decodeFromJsonElement(Actor.serializer(), a) }.getOrNull() ?: Actor()
        is JsonPrimitive -> a.contentOrNull?.let { Actor(it, if (it == "owner") "owner" else "agent", d.str("actor_fa")) } ?: Actor()
        else -> Actor()
    }
    val tool = d.str("tool") ?: "server.exec"
    val exit = (d["exit_code"] as? JsonPrimitive)?.intOrNull
    val ms = (d["duration_ms"] as? JsonPrimitive)?.longOrNull
    return ServerCallRow(
        e.at, actor, tool, SERVER_TOOL_FA[tool] ?: tool, d.str("summary_fa").orEmpty(), d.str("cmd_masked")?.takeIf { it.isNotBlank() },
        outcomeOf(exit, ms, d.str("state"), d.str("code")), exit, duration(ms), d.str("session_ref"), d.str("transcript_url"), d.str("server") ?: e.ref,
        d.str("cwd"),
    )
}

/** `380ms`, `2.4s`, `41s`, `3m 12s`, `1h 05m` — a figure (Latin). */
fun duration(ms: Long?): String? {
    if (ms == null || ms < 0) return null
    return when {
        ms < 1_000 -> "${ms}ms"
        ms < 10_000 -> String.format(java.util.Locale.US, "%.1fs", ms / 1000.0)
        ms < 60_000 -> "${ms / 1000}s"
        ms < 3_600_000 -> "${ms / 60_000}m ${(ms / 1000) % 60}s"
        else -> String.format(java.util.Locale.US, "%dh %02dm", ms / 3_600_000, (ms / 60_000) % 60)
    }
}

// ------------------------------------------------------------------ the seal card (§26.3) --
/** A `server_destructive` card read for the owner: the exact command, where, what kind of loss, who asked and from which session. */
data class SealCard(
    val ref: String,
    val company: String,
    val serverId: String?,
    val serverName: String,
    val category: SealCategory?,
    val categoryKey: String?,
    /** Exactly what will run, as the gateway stopped it (secrets masked by name). */
    val cmd: String,
    val cwd: String?,
    val tool: String,
    val actor: Actor,
    val sessionRef: String?,
    /** `pattern` · `tool` */
    val detectedBy: String?,
    val pattern: String?,
    val pending: Boolean,
    val createdAt: String,
    val expiresAt: String?,
) {
    /** 🔏 `server.destructive` is bound to `<CODE>:<server>` (§26.3). */
    val target: String get() = "$company:$serverName"
}

const val SERVER_DESTRUCTIVE = "server_destructive"

private fun JsonObject.str(k: String): String? = (this[k] as? JsonPrimitive)?.takeIf { it !is JsonNull }?.contentOrNull?.takeIf { it.isNotBlank() }

/** The card's payload as the seal needs it; null for any other kind. A sparse payload still names the server from the card's title. */
fun sealCardOf(d: Decision): SealCard? {
    if (d.kind != SERVER_DESTRUCTIVE) return null
    val p = d.payload
    val server = p["server"]
    val (id, name) = when (server) {
        is JsonObject -> server.str("id") to (server.str("name") ?: p.str("server_name"))
        is JsonPrimitive -> server.contentOrNull to p.str("server_name")
        else -> null to p.str("server_name")
    }
    val actor = (p["actor"] as? JsonObject)?.let { runCatching { Api.json.decodeFromJsonElement(Actor.serializer(), it) }.getOrNull() } ?: d.proposer
    val cat = p.str("category")
    return SealCard(
        d.ref, p.str("company") ?: d.company, id, name ?: id ?: "—", sealCategory(cat), cat,
        p.str("cmd") ?: p.str("cmd_masked") ?: p.str("command") ?: "", p.str("cwd"), p.str("tool") ?: "server.exec", actor,
        p.str("session_ref"), p.str("detected_by"), p.str("pattern"), d.status == "pending", d.createdAt, d.expiresAt,
    )
}

// ------------------------------------------------------------------ the owner's terminal (§26.4 exec) --
/** The owner's command (`POST /infra/servers/{id}/exec`), the same fields as the agents' `server.exec` (§26.2). */
@Serializable
data class ExecIn(val cmd: String, val cwd: String? = null, val timeoutS: Int = 600, val sudo: Boolean = false)

sealed interface TermEvent {
    data class Out(val text: String, val err: Boolean = false) : TermEvent
    data class Exit(val code: Int, val durationMs: Long?) : TermEvent
    data class Failed(val code: String, val messageFa: String) : TermEvent
    /** `202 awaiting_seal`: a destructive command became a card (§26.3). */
    data class AwaitingSeal(val decisionRef: String?, val messageFa: String) : TermEvent
}

/** One server-sent event. */
data class SseMessage(val event: String?, val data: String, val id: String?)

/** A line-by-line reader of `text/event-stream` (several `data:` lines join with a newline; a blank line ends an event; `:` lines are
 *  comments, such as the hub's heartbeats). */
class SseParser {
    private var event: String? = null
    private var id: String? = null
    private val data = StringBuilder()
    private var any = false

    fun line(raw: String): SseMessage? {
        val l = raw.removeSuffix("\r")
        if (l.isEmpty()) return flush()
        if (l.startsWith(":")) return null
        val k = l.substringBefore(':')
        val v = if (':' in l) l.substringAfter(':').removePrefix(" ") else ""
        when (k) {
            "event" -> event = v
            "id" -> id = v
            "data" -> { if (any) data.append('\n'); data.append(v); any = true }
        }
        return null
    }

    /** The stream ended: an event without its blank line still counts. */
    fun end(): SseMessage? = flush()

    private fun flush(): SseMessage? {
        val m = if (any || event != null) SseMessage(event, data.toString(), id) else null
        event = null; data.setLength(0); any = false
        return m
    }
}

private fun jsonOf(s: String): JsonObject? = runCatching { Api.json.parseToJsonElement(s) as? JsonObject }.getOrNull()

/** An exec stream's event as the terminal reads it: `stdout`/`stderr` (raw text or `{text}`), `exit` (`{exit_code, duration_ms}`),
 *  `error` (a Problem) and `awaiting_seal`; an unnamed event with a JSON body says which by its keys. */
fun termEventOf(m: SseMessage): TermEvent? {
    val o = jsonOf(m.data)
    fun text(): String = o?.str("text") ?: o?.str("data") ?: m.data
    return when (m.event ?: o?.str("type") ?: o?.str("stream")) {
        "stdout", "out", "output" -> TermEvent.Out(text())
        "stderr", "err" -> TermEvent.Out(text(), err = true)
        "exit", "done", "end" -> TermEvent.Exit((o?.get("exit_code") as? JsonPrimitive)?.intOrNull ?: 0, (o?.get("duration_ms") as? JsonPrimitive)?.longOrNull)
        "error" -> TermEvent.Failed(o?.str("code") ?: "internal_error", o?.str("message_fa") ?: o?.str("detail") ?: m.data)
        "awaiting_seal" -> TermEvent.AwaitingSeal(o?.str("decision_ref") ?: o?.str("decision") ?: o?.str("ref"), o?.str("message_fa") ?: "این فرمان ویرانگر است و منتظر مُهر تو ماند.")
        null, "message" -> when {
            o == null -> if (m.data.isEmpty()) null else TermEvent.Out(m.data)
            o["exit_code"] != null -> TermEvent.Exit((o["exit_code"] as? JsonPrimitive)?.intOrNull ?: 0, (o["duration_ms"] as? JsonPrimitive)?.longOrNull)
            o["stderr"] != null -> TermEvent.Out(o.str("stderr").orEmpty(), err = true)
            o["stdout"] != null -> TermEvent.Out(o.str("stdout").orEmpty())
            else -> null
        }
        else -> null
    }
}

/** The events of an answer that came whole as JSON (`{stdout, stderr, exit_code, duration_ms}`) instead of a stream. */
fun termEventsOfJson(o: JsonObject): List<TermEvent> = buildList {
    o.str("stdout")?.let { add(TermEvent.Out(if (it.endsWith("\n")) it else "$it\n")) }
    o.str("stderr")?.let { add(TermEvent.Out(if (it.endsWith("\n")) it else "$it\n", err = true)) }
    (o["exit_code"] as? JsonPrimitive)?.intOrNull?.let { add(TermEvent.Exit(it, (o["duration_ms"] as? JsonPrimitive)?.longOrNull)) }
}

enum class TermKind { CMD, OUT, ERR, INFO, OK, FAIL }

data class TermLine(val kind: TermKind, val text: String)

/**
 * What the terminal shows: the command typed, then its output line by line as it streams. A chunk without a newline waits for the rest of
 * its line; a carriage return (a progress bar) rewrites the line; colour codes are dropped. The oldest lines go past [max].
 */
class TerminalBuffer(private val max: Int = 4_000) {
    private val done = ArrayDeque<TermLine>()
    private val pending = mutableMapOf(false to "", true to "")
    var running: Boolean = false
        private set
    var lastExit: Int? = null
        private set

    /** Everything to draw: the finished lines, then what is still coming on each stream. */
    val lines: List<TermLine>
        get() = done.toList() + listOfNotNull(
            pending.getValue(false).takeIf { it.isNotEmpty() }?.let { TermLine(TermKind.OUT, it) },
            pending.getValue(true).takeIf { it.isNotEmpty() }?.let { TermLine(TermKind.ERR, it) },
        )

    fun command(cmd: String, login: String) {
        flush()
        push(TermLine(TermKind.CMD, "$login\$ $cmd"))
        running = true
        lastExit = null
    }

    fun info(text: String) = push(TermLine(TermKind.INFO, text))

    fun apply(e: TermEvent) {
        when (e) {
            is TermEvent.Out -> out(e.text, e.err)
            is TermEvent.Exit -> {
                flush()
                lastExit = e.code
                push(TermLine(if (e.code == 0) TermKind.OK else TermKind.FAIL, "exit ${e.code}" + (duration(e.durationMs)?.let { " · $it" } ?: "")))
                running = false
            }
            is TermEvent.Failed -> { flush(); push(TermLine(TermKind.FAIL, e.messageFa)); running = false }
            is TermEvent.AwaitingSeal -> { flush(); push(TermLine(TermKind.INFO, e.messageFa)); running = false }
        }
    }

    /** The stream closed without an exit (the owner stopped it, or the line dropped). */
    fun ended(note: String?) {
        flush()
        if (running && note != null) push(TermLine(TermKind.INFO, note))
        running = false
    }

    fun clear() { done.clear(); pending[false] = ""; pending[true] = "" }

    private fun out(chunk: String, err: Boolean) {
        val text = pending.getValue(err) + chunk.replace(ANSI, "").replace("\r\n", "\n")
        val parts = text.split('\n')
        for (p in parts.dropLast(1)) push(TermLine(if (err) TermKind.ERR else TermKind.OUT, p.substringAfterLast('\r')))
        pending[err] = parts.last().substringAfterLast('\r')
    }

    private fun flush() {
        for (err in listOf(false, true)) {
            val p = pending.getValue(err)
            if (p.isNotEmpty()) push(TermLine(if (err) TermKind.ERR else TermKind.OUT, p))
            pending[err] = ""
        }
    }

    private fun push(l: TermLine) {
        done.addLast(l)
        while (done.size > max) done.removeFirst()
    }

    private companion object {
        val ANSI = Regex("\u001B\\[[0-9;?]*[ -/]*[@-~]")
    }
}

/** The owner's last commands on one server, newest first, each once. Kept in memory only: a command can hold a secret. */
class TermHistory(private val max: Int = 20) {
    private val list = ArrayDeque<String>()
    val items: List<String> get() = list.toList()

    fun add(cmd: String) {
        val c = cmd.trim()
        if (c.isEmpty()) return
        list.remove(c)
        list.addFirst(c)
        while (list.size > max) list.removeLast()
    }

    /** Merged with what the hub recorded for the owner (`cmd_masked`), the phone's own first. */
    fun with(recorded: List<String>): List<String> = (items + recorded.map { it.trim() }.filter { it.isNotEmpty() }).distinct().take(max)

    companion object {
        private val byServer = mutableMapOf<String, TermHistory>()
        @Synchronized fun of(server: String): TermHistory = byServer.getOrPut(server) { TermHistory() }
    }
}

// ------------------------------------------------------------------ server.map (§26.2) --
/** A used/total pair in bytes (a disk's mount, memory, swap). */
data class DiskUsage(val label: String, val usedBytes: Long, val totalBytes: Long) {
    val pct: Double get() = if (totalBytes <= 0) 0.0 else (usedBytes * 100.0 / totalBytes).coerceIn(0.0, 100.0)
}

data class MapContainer(val name: String, val image: String?, val state: String, val status: String?, val project: String?, val health: String? = null)
data class MapCompose(val project: String, val dir: String?, val services: Int?, val running: Int?)
data class MapUnit(val name: String, val state: String?, val description: String?)
data class MapTimer(val unit: String, val next: String?, val last: String?, val activates: String?)
data class MapCron(val schedule: String, val command: String, val user: String?)
/** [public]: §26.5 says whether the port is open beyond the machine; null when the map did not say (the address decides). */
data class MapPort(val port: Int, val proto: String, val address: String?, val process: String?, val public: Boolean? = null)
data class MapRepo(val path: String, val remote: String?, val branch: String?, val head: String?, val dirty: Boolean?, val lastCommitAt: String? = null)
data class MapAutomation(val kind: String, val name: String, val active: Boolean?, val detail: String?)
data class MapSite(val domain: String, val upstream: String?, val tls: Boolean?, val server: String?)

/**
 * The latest `server.map` (§26.2), read for the owner: OS, disk and memory, containers and compose projects, systemd units and timers,
 * cron, listening ports, repositories with their remotes, n8n and other automations, the sites served. §26 names the parts and not their
 * fields, so [ServerMaps.parse] reads the shapes a mapper is likely to write (bytes as numbers or "150G", lists of objects or of plain
 * strings, systemd as one object or two lists) and leaves out what it cannot read; nothing it meets makes it fail.
 */
data class ServerMap(
    val at: String? = null,
    val hostname: String? = null,
    val os: String? = null,
    val kernel: String? = null,
    val cpus: Int? = null,
    val uptimeS: Long? = null,
    val load: Double? = null,
    val disks: List<DiskUsage> = emptyList(),
    val memory: DiskUsage? = null,
    val swap: DiskUsage? = null,
    val containers: List<MapContainer> = emptyList(),
    val compose: List<MapCompose> = emptyList(),
    val units: List<MapUnit> = emptyList(),
    val timers: List<MapTimer> = emptyList(),
    val cron: List<MapCron> = emptyList(),
    val ports: List<MapPort> = emptyList(),
    val repos: List<MapRepo> = emptyList(),
    val automations: List<MapAutomation> = emptyList(),
    val sites: List<MapSite> = emptyList(),
) {
    val runningContainers: Int get() = containers.count { it.state == "running" }
    val empty: Boolean get() = os == null && disks.isEmpty() && memory == null && containers.isEmpty() && repos.isEmpty() && sites.isEmpty()
}

object ServerMaps {
    private const val KIB = 1024L
    private val SIZE = Regex("^\\s*([0-9]+(?:\\.[0-9]+)?)\\s*([KMGTP]?)(i?B?|b)?\\s*$", RegexOption.IGNORE_CASE)

    /** Bytes from a number (bytes) or a human size ("150G", "15.6GiB", "512 MB", "800K"). */
    fun bytes(e: JsonElement?): Long? {
        val p = e as? JsonPrimitive ?: return null
        if (p is JsonNull) return null
        if (!p.isString) return p.doubleOrNull?.toLong()
        val m = SIZE.find(p.content) ?: return null
        val n = m.groupValues[1].toDouble()
        val mul = when (m.groupValues[2].uppercase()) { "K" -> KIB; "M" -> KIB * KIB; "G" -> KIB * KIB * KIB; "T" -> KIB * KIB * KIB * KIB; "P" -> KIB * KIB * KIB * KIB * KIB; else -> 1L }
        return (n * mul).toLong()
    }

    /** "41 GB", "1.2 TB", "512 MB" — a figure (Latin), binary units as `df -h` and `free -h` count them. */
    fun size(b: Long): String {
        val units = listOf("B", "KB", "MB", "GB", "TB", "PB")
        var v = b.toDouble()
        var i = 0
        while (v >= 1024 && i < units.lastIndex) { v /= 1024; i++ }
        val s = if (v >= 100 || i == 0) String.format(java.util.Locale.US, "%.0f", v) else String.format(java.util.Locale.US, "%.1f", v).removeSuffix(".0")
        return "$s ${units[i]}"
    }

    fun parse(e: JsonElement?): ServerMap? {
        val root = e as? JsonObject ?: return null
        // A wrapper ({map: {...}, taken_at}) or the map itself.
        val o = (root["map"] as? JsonObject) ?: root
        val at = root.s("taken_at") ?: root.s("at") ?: root.s("map_at") ?: o.s("taken_at") ?: o.s("at")
        val osEl = o["os"]
        val os = when (osEl) {
            is JsonObject -> osEl.s("pretty_name") ?: listOfNotNull(osEl.s("name") ?: osEl.s("distro"), osEl.s("version")).joinToString(" ").ifBlank { null }
            is JsonPrimitive -> osEl.takeIf { it.isString }?.contentOrNull
            else -> null
        }
        val kernel = (osEl as? JsonObject)?.s("kernel") ?: o.s("kernel")
        val systemd = o["systemd"] as? JsonObject
        // §26.5: `systemd` is one list, each entry a unit or (`timer: true`) a timer.
        val systemdList = (o["systemd"] as? JsonArray).orEmpty()
        val isTimer = { e: JsonElement -> ((e as? JsonObject)?.get("timer") as? JsonPrimitive)?.booleanOrNull == true }
        val cpu = o["cpu"] as? JsonObject
        val mem = (o["memory"] ?: o["mem"] ?: o["ram"]) as? JsonObject
        val n8n = o["n8n"]
        return ServerMap(
            at = at,
            hostname = o.s("hostname") ?: o.s("host"),
            os = os,
            kernel = kernel,
            cpus = (o["cpus"] as? JsonPrimitive)?.intOrNull ?: (o["cpu"] as? JsonObject)?.let { (it["cores"] as? JsonPrimitive)?.intOrNull ?: (it["count"] as? JsonPrimitive)?.intOrNull },
            uptimeS = (o["uptime_s"] as? JsonPrimitive)?.longOrNull ?: (o["uptime"] as? JsonPrimitive)?.longOrNull,
            load = (o["load"] as? JsonPrimitive)?.doubleOrNull ?: ((o["load"] as? JsonArray)?.firstOrNull() as? JsonPrimitive)?.doubleOrNull
                ?: (cpu?.get("load1") as? JsonPrimitive)?.doubleOrNull,
            disks = (o["disks"] ?: o["disk"]).let { d ->
                when (d) {
                    is JsonArray -> d.mapNotNull { usage(it as? JsonObject, "/") }
                    is JsonObject -> listOfNotNull(usage(d, "/"))
                    else -> emptyList()
                }
            },
            memory = usage(mem, "RAM"),
            swap = (usage(o["swap"] as? JsonObject ?: mem?.get("swap") as? JsonObject, "swap") ?: mem?.let { m ->
                // §26.5 writes swap beside the memory: `swap_total_mb`, `swap_used_mb`.
                val total = m.mb("swap_total_mb") ?: return@let null
                DiskUsage("swap", (m.mb("swap_used_mb") ?: 0L).coerceAtLeast(0), total)
            })?.takeIf { it.totalBytes > 0 },
            containers = list(o["containers"] ?: (o["docker"] as? JsonObject)?.get("containers")).mapNotNull(::container),
            compose = list(o["compose"] ?: o["compose_projects"] ?: (o["docker"] as? JsonObject)?.get("compose")).mapNotNull(::compose),
            units = list(systemd?.get("units") ?: systemd?.get("services") ?: o["units"] ?: o["services"]).mapNotNull(::unit) +
                systemdList.filterNot(isTimer).mapNotNull(::unit),
            timers = list(systemd?.get("timers") ?: o["timers"]).mapNotNull(::timer) + systemdList.filter(isTimer).mapNotNull(::timer),
            cron = list(o["cron"] ?: o["crontab"]).mapNotNull(::cron),
            ports = list(o["ports"] ?: o["listening"]).mapNotNull(::port).distinctBy { "${it.port}/${it.proto}/${it.address}" }.sortedBy { it.port },
            repos = list(o["repos"] ?: o["repositories"]).mapNotNull(::repo),
            automations = list(o["automations"]).mapNotNull { automation(it, null) } +
                list(if (n8n is JsonObject) n8n["workflows"] else n8n).mapNotNull { automation(it, "n8n") },
            sites = list(o["sites"]).mapNotNull(::site),
        )
    }

    private fun list(e: JsonElement?): List<JsonElement> = when (e) {
        is JsonArray -> e
        is JsonObject -> e["items"] as? JsonArray ?: emptyList()
        else -> emptyList()
    }

    private fun JsonObject.s(k: String): String? = (this[k] as? JsonPrimitive)?.takeIf { it !is JsonNull }?.contentOrNull?.takeIf { it.isNotBlank() }
    private fun JsonObject.b(k: String): Boolean? = (this[k] as? JsonPrimitive)?.booleanOrNull
    private fun JsonObject.i(k: String): Int? = (this[k] as? JsonPrimitive)?.intOrNull
    private fun JsonElement.text(): String? = (this as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull?.trim()?.takeIf { it.isNotEmpty() }

    private fun usage(o: JsonObject?, label: String): DiskUsage? {
        o ?: return null
        val total = bytes(o["total_bytes"]) ?: bytes(o["size_bytes"]) ?: bytes(o["total"]) ?: bytes(o["size"])
            ?: o.mb("total_mb") ?: o.gb("total_gb") ?: return null
        val used = bytes(o["used_bytes"]) ?: bytes(o["used"]) ?: o.mb("used_mb") ?: o.gb("used_gb")
            ?: (bytes(o["available_bytes"]) ?: bytes(o["available"]) ?: bytes(o["avail"]) ?: bytes(o["free_bytes"]) ?: bytes(o["free"]) ?: o.mb("available_mb") ?: o.gb("available_gb"))?.let { total - it }
            ?: return null
        return DiskUsage(o.s("mount") ?: o.s("mountpoint") ?: o.s("path") ?: o.s("device") ?: label, used.coerceAtLeast(0), total)
    }

    private fun JsonObject.mb(k: String): Long? = (this[k] as? JsonPrimitive)?.doubleOrNull?.let { (it * KIB * KIB).toLong() }
    private fun JsonObject.gb(k: String): Long? = (this[k] as? JsonPrimitive)?.doubleOrNull?.let { (it * KIB * KIB * KIB).toLong() }

    private fun container(e: JsonElement): MapContainer? {
        e.text()?.let { return MapContainer(it, null, "running", null, null) }
        val o = e as? JsonObject ?: return null
        val name = o.s("name") ?: (o["names"] as? JsonArray)?.firstOrNull()?.text() ?: o.s("names") ?: return null
        val labels = o["labels"] as? JsonObject
        val status = o.s("status")
        val state = o.s("state") ?: status?.let { if (it.startsWith("Up", true)) "running" else "exited" } ?: "unknown"
        return MapContainer(name.removePrefix("/"), o.s("image"), state.lowercase(), status, o.s("compose_project") ?: o.s("project") ?: labels?.s("com.docker.compose.project"), o.s("health"))
    }

    private fun compose(e: JsonElement): MapCompose? {
        e.text()?.let { return MapCompose(it, null, null, null) }
        val o = e as? JsonObject ?: return null
        val name = o.s("project") ?: o.s("name") ?: return null
        val dir = o.s("dir") ?: o.s("path") ?: o.s("working_dir") ?: (o["config_files"] as? JsonArray)?.firstOrNull()?.text() ?: o.s("config_files")
        val services = (o["services"] as? JsonArray)?.size ?: o.i("services")
        // `docker compose ls` writes "running(5)".
        val running = o.i("running") ?: o.s("status")?.let { Regex("running\\((\\d+)\\)").find(it)?.groupValues?.get(1)?.toIntOrNull() }
        return MapCompose(name, dir, services, running)
    }

    private fun unit(e: JsonElement): MapUnit? {
        e.text()?.let { return MapUnit(it, null, null) }
        val o = e as? JsonObject ?: return null
        val name = o.s("name") ?: o.s("unit") ?: return null
        return MapUnit(name, o.s("state") ?: o.s("active") ?: o.s("sub"), o.s("description"))
    }

    private fun timer(e: JsonElement): MapTimer? {
        e.text()?.let { return MapTimer(it, null, null, null) }
        val o = e as? JsonObject ?: return null
        val name = o.s("unit") ?: o.s("name") ?: o.s("timer") ?: return null
        return MapTimer(name, o.s("next") ?: o.s("next_at"), o.s("last") ?: o.s("last_at"), o.s("activates") ?: o.s("service"))
    }

    private fun cron(e: JsonElement): MapCron? {
        e.text()?.let { line ->
            if (line.startsWith("#")) return null
            // "*/5 * * * * cmd …" or "@daily cmd …"
            val parts = line.split(Regex("\\s+"))
            return if (line.startsWith("@")) MapCron(parts[0], parts.drop(1).joinToString(" "), null)
            else if (parts.size > 5) MapCron(parts.take(5).joinToString(" "), parts.drop(5).joinToString(" "), null) else null
        }
        val o = e as? JsonObject ?: return null
        val cmd = o.s("cmd_masked") ?: o.s("command") ?: o.s("cmd") ?: return null
        return MapCron(o.s("schedule") ?: o.s("when") ?: "?", cmd, o.s("user"))
    }

    private fun port(e: JsonElement): MapPort? {
        (e as? JsonPrimitive)?.let { p ->
            if (!p.isString) return p.intOrNull?.let { MapPort(it, "tcp", null, null) }
            // "0.0.0.0:443", "127.0.0.1:5432/tcp", "[::]:22"
            val s = p.content.trim()
            val proto = s.substringAfter('/', "tcp")
            val hostPort = s.substringBefore('/')
            val port = hostPort.substringAfterLast(':').toIntOrNull() ?: return null
            return MapPort(port, proto, hostPort.substringBeforeLast(':', "").ifBlank { null }, null)
        }
        val o = e as? JsonObject ?: return null
        val port = o.i("port") ?: return null
        return MapPort(port, o.s("proto") ?: o.s("protocol") ?: "tcp", o.s("address") ?: o.s("bind") ?: o.s("host"), o.s("process") ?: o.s("program") ?: o.s("service"), o.b("public"))
    }

    private fun repo(e: JsonElement): MapRepo? {
        e.text()?.let { return MapRepo(it, null, null, null, null) }
        val o = e as? JsonObject ?: return null
        val path = o.s("path") ?: o.s("dir") ?: return null
        val remote = o.s("remote") ?: o.s("origin") ?: when (val r = o["remotes"]) {
            is JsonArray -> r.firstOrNull()?.let { x -> x.text() ?: (x as? JsonObject)?.let { it.s("url") ?: it.s("fetch") } }
            is JsonObject -> r.s("origin") ?: r.values.firstOrNull()?.text()
            else -> null
        }
        return MapRepo(path, remote, o.s("branch"), (o.s("head") ?: o.s("commit"))?.take(12), o.b("dirty"), o.s("last_commit_at"))
    }

    private fun automation(e: JsonElement, kind: String?): MapAutomation? {
        e.text()?.let { return MapAutomation(kind ?: "automation", it, null, null) }
        val o = e as? JsonObject ?: return null
        val name = o.s("name") ?: o.s("title") ?: return null
        return MapAutomation(o.s("kind") ?: o.s("type") ?: kind ?: "automation", name, o.b("active") ?: o.b("enabled"), o.s("detail") ?: o.s("trigger") ?: o.s("schedule"))
    }

    private fun site(e: JsonElement): MapSite? {
        e.text()?.let { return MapSite(it, null, null, null) }
        val o = e as? JsonObject ?: return null
        val domain = o.s("domain") ?: o.s("host") ?: o.s("server_name") ?: (o["domains"] as? JsonArray)?.firstOrNull()?.text() ?: return null
        return MapSite(domain, o.s("upstream") ?: o.s("proxy_pass") ?: o.s("root") ?: o.s("target"), o.b("tls") ?: o.b("https"), o.s("server") ?: o.s("via"))
    }
}

// ------------------------------------------------------------------ codes (§26, §14) --
private val CODE_FA_21 = mapOf(
    "company_locked" to "کلید توقف این شرکت زده شده؛ هر کاری روی سرورهایش ایستاده است.",
    "deploy_frozen" to "deploy این شرکت بسته است؛ فرمان‌های انتشار رد میشوند.",
    "awaiting_seal" to "این کار ویرانگر است و منتظر مُهر تو ماند.",
    "server_offline" to "runner این سرور الان آفلاین است؛ تا دوباره تماس نگیرد کاری رویش اجرا نمیشود.",
    "server_unreachable" to "runner این سرور الان آفلاین است؛ تا دوباره تماس نگیرد کاری رویش اجرا نمیشود.",
    "runner_revoked" to "runner این سرور باطل شده؛ برای کار دوباره، روی سرور از نو جفتش کن.",
)

/** A §26 refusal in Persian (the hub's sentence for any other code). */
fun serverError(e: ApiException): String = CODE_FA_21[e.code] ?: e.messageFa

// ------------------------------------------------------------------ the holding's network map (§26.6) --
/** One machine on the holding's network map (§26.6 `GET /infra/network`): the hub (`hub`, `10.10.1.4`) or a company server, with how its
 *  runner reaches the hub (`via`) and how long that takes (`hub_rtt_ms`), both from its last poll. */
@Serializable
data class NetNode(
    val id: String,
    val company: String = "",
    val name: String = "",
    val privateIp: String? = null,
    /** `private` · `public` (the runner fell back to the hub's public address) · null for the hub, or before the first poll. */
    val via: String? = null,
    /** The runner's state (§26.4): `online` · `offline` · `pending` · `revoked`. */
    val state: String = "online",
    val hubRttMs: Double? = null,
) {
    val isHub: Boolean get() = id == NetworkMap.HUB
    val online: Boolean get() = isHub || state == "online"
    /** Not on the holding's private network at all: no private address (it reaches the hub over the internet until the owner adds it). */
    val outside: Boolean get() = !isHub && privateIp.isNullOrBlank()
    /** On the private network, but its runner came over the public address this time (the private one did not answer). */
    val fellBack: Boolean get() = !isHub && !outside && via == "public"
}

/** One TCP connect of a `netcheck` (§26.6): [from] tried [to] on [port]; `ok`, `ms` (null when it failed) and the error it met. */
@Serializable
data class NetLink(
    val from: String,
    val to: String,
    val port: Int = 0,
    val ok: Boolean? = null,
    val ms: Double? = null,
    val error: String? = null,
    val at: String? = null,
)

/** §26.6 `GET /infra/network`: the nodes and every link the latest checks tried. */
@Serializable
data class NetworkMap(val at: String? = null, val nodes: List<NetNode> = emptyList(), val links: List<NetLink> = emptyList()) {
    /** The hub first (made up from the contract when the hub leaves itself out), then the servers that are attached; the revoked are gone. */
    val all: List<NetNode> get() = listOf(nodes.firstOrNull { it.isHub } ?: NetNode(HUB, "HQ", "hub", HUB_IP)) + servers
    val servers: List<NetNode> get() = nodes.filter { !it.isHub && it.state != "revoked" }

    fun node(id: String): NetNode? = all.firstOrNull { it.id == id }

    /** What [from] found when it tried [to] on [port]; null when that was never checked. */
    fun link(from: String, to: String, port: Int): NetLink? = links.lastOrNull { it.from == from && it.to == to && it.port == port }

    /** When the latest result came in. */
    val lastAt: String? get() = links.mapNotNull { it.at }.maxByOrNull { instantOrMin(it) } ?: at

    companion object {
        const val HUB = "hub"
        const val HUB_IP = "10.10.1.4"
        /** The ports every runner tries on every other server (§26.6); the hub is tried on 443. */
        val PORTS = listOf(22, 80, 443)
    }
}

private fun instantOrMin(s: String?): java.time.Instant = s?.let { runCatching { java.time.Instant.parse(it) }.getOrNull() } ?: java.time.Instant.MIN

/** How a line on the map is drawn: green, amber (slower than [Network.SLOW_MS]), red, or grey when nothing is known. */
enum class LinkHealth { OK, SLOW, FAIL, UNKNOWN }

/** The line between the hub and one server: its health, the road (`private`/`public`), the round trip and why it failed. */
data class HubLine(val node: NetNode, val health: LinkHealth, val via: String?, val rttMs: Double?, val error: String?)

/** A broken road between two machines, every port that failed on it together. */
data class NetPath(val from: NetNode, val to: NetNode, val ports: List<Int>, val error: String?, val toHub: Boolean)

/** What the map says in words: what is broken, what is slow, who is outside the private network or came over the public road. */
data class NetSummary(
    val servers: Int,
    val failed: List<NetPath>,
    val slow: List<HubLine>,
    val outside: List<NetNode>,
    val fellBack: List<NetNode>,
    /** The servers whose runner has never reported a road (pending), so nothing is known about them yet. */
    val unknown: List<NetNode>,
    /** The private address the next server should take (§26.1a: the owner adds it in the Hetzner console). */
    val nextFreeIp: String?,
) {
    /** Every server reaches the hub, over the private network, and the servers reach each other. */
    val allOk: Boolean get() = failed.isEmpty() && slow.isEmpty() && outside.isEmpty() && fellBack.isEmpty() && unknown.isEmpty()
    val hubOk: Boolean get() = failed.none { it.toHub }
}

/** Where a check stands: which online runners have answered since it was queued. */
data class CheckProgress(val expected: Set<String>, val reported: Set<String>) {
    val done: Boolean get() = expected.isNotEmpty() && reported.containsAll(expected)
    val fraction: Float get() = if (expected.isEmpty()) 0f else reported.intersect(expected).size.toFloat() / expected.size
}

object Network {
    /** Slower than this (ms) is amber on the map. */
    const val SLOW_MS = 150.0
    /** A check is followed every few seconds, for at most a minute. */
    const val POLL_MS = 3_000L
    const val MAX_WAIT_MS = 60_000L

    fun health(ok: Boolean?, ms: Double?): LinkHealth = when {
        ok == null -> LinkHealth.UNKNOWN
        !ok -> LinkHealth.FAIL
        ms != null && ms > SLOW_MS -> LinkHealth.SLOW
        else -> LinkHealth.OK
    }

    /** `3 ms`, `0.4 ms`, `41 ms`, `1.2 s` — a figure, Latin. */
    fun ms(v: Double?): String? = when {
        v == null || v < 0 -> null
        v < 10 -> String.format(java.util.Locale.US, "%.1f", v).removeSuffix(".0") + " ms"
        v < 1_000 -> "${Math.round(v)} ms"
        else -> String.format(java.util.Locale.US, "%.1f", v / 1000).removeSuffix(".0") + " s"
    }

    /** The hub ↔ [n] line: a runner that stopped polling is a broken line; one that never polled is unknown; otherwise its own check of the
     *  hub (443) if there is one, else the round trip its polls report. */
    fun hubLine(m: NetworkMap, n: NetNode): HubLine {
        val l = NetworkMap.PORTS.reversed().firstNotNullOfOrNull { m.link(n.id, NetworkMap.HUB, it) }
        val rtt = n.hubRttMs ?: l?.takeIf { it.ok == true }?.ms
        val h = when {
            n.state == "offline" -> LinkHealth.FAIL
            n.state != "online" -> LinkHealth.UNKNOWN
            l?.ok == false -> LinkHealth.FAIL
            rtt != null || l?.ok == true -> health(true, rtt)
            else -> LinkHealth.UNKNOWN
        }
        val err = when {
            n.state == "offline" -> "offline"
            l?.ok == false -> l.error ?: "failed"
            else -> null
        }
        return HubLine(n, h, n.via, rtt.takeIf { h != LinkHealth.FAIL }, err)
    }

    /** The map in words. A server outside the private network cannot reach the others' private addresses: that is one issue (add it to
     *  the network), not a broken road per address. */
    fun summary(m: NetworkMap): NetSummary {
        val servers = m.servers
        val lines = servers.map { hubLine(m, it) }
        val failed = mutableListOf<NetPath>()
        val hub = m.all.first()
        for (l in lines) if (l.health == LinkHealth.FAIL) failed += NetPath(l.node, hub, listOf(443), l.error, toHub = true)
        val byId = servers.associateBy { it.id }
        m.links.filter { it.ok == false && it.to != NetworkMap.HUB && it.from != NetworkMap.HUB }
            .groupBy { it.from to it.to }
            .forEach { (k, ls) ->
                val from = byId[k.first] ?: return@forEach
                val to = byId[k.second] ?: return@forEach
                if (from.outside || to.outside || from.state == "offline" || to.state == "offline") return@forEach
                // The latest result of each port decides: a port that answered since is not broken.
                val ports = ls.map { it.port }.distinct().filter { p -> m.link(from.id, to.id, p)?.ok == false }.sorted()
                if (ports.isNotEmpty()) failed += NetPath(from, to, ports, ls.last().error, toHub = false)
            }
        return NetSummary(
            servers.size, failed,
            lines.filter { it.health == LinkHealth.SLOW },
            servers.filter { it.outside },
            servers.filter { it.fellBack && it.online },
            servers.filter { it.state == "pending" },
            nextFreeIp(m),
        )
    }

    /** The lowest free address in the hub's /24 (the hub's own and every server's taken). */
    fun nextFreeIp(m: NetworkMap): String? {
        val hubIp = m.all.first().privateIp?.takeIf { it.isNotBlank() } ?: NetworkMap.HUB_IP
        val prefix = hubIp.substringBeforeLast('.', "").ifBlank { return null }
        val taken = m.all.mapNotNull { n -> n.privateIp?.takeIf { it.startsWith("$prefix.") }?.substringAfterLast('.')?.toIntOrNull() }.toSet()
        return (1..254).firstOrNull { it !in taken }?.let { "$prefix.$it" }
    }

    /** Which online runners have reported since [before] (the map as it was when the check was queued): a link from them newer than
     *  anything [before] held. The check is done when every online server has. */
    fun progress(before: NetworkMap?, now: NetworkMap): CheckProgress {
        val base = instantOrMin(before?.lastAt)
        val expected = now.servers.filter { it.online }.map { it.id }.toSet()
        val reported = now.links.filter { instantOrMin(it.at) > base }.map { it.from }.toSet()
        return CheckProgress(expected, reported)
    }

    /** A connect error in Persian (the runner's word kept beside it, Latin). */
    fun errorFa(e: String?): String = when {
        e == null -> "وصل نشد"
        e == "offline" -> "runner تماس نمیگیرد"
        e.contains("refused", true) -> "پورت بسته است"
        e.contains("timeout", true) || e.contains("timed out", true) -> "پاسخی نیامد"
        e.contains("unreachable", true) || e.contains("no route", true) -> "راهی به مقصد نیست"
        else -> "وصل نشد"
    }
}
