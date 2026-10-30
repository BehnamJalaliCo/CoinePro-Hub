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
// Contract §26 (prompt 17): the holding's full access to the companies' servers. The hub reaches each attached server over SSH through
// `company-ops`; agents (and the owner from this app) run commands, read and write files, start Claude Code on the server and map it.
// Everything runs free except six destructive categories, which wait for the owner's seal (`server_destructive`, 🔏 `server.destructive`
// on `<CODE>:<server>`). Same rules as Models.kt: camelCase here, snake_case on the wire. Servers and companies are data: nothing here
// counts them.

/** One server the hub can reach (§26.4 `GET /infra/servers`): made by the provisioner, or an existing company server attached. */
@Serializable
data class HubServer(
    val id: String,
    val company: String = "",
    val name: String = "",
    /** `provisioned` · `attached` */
    val origin: String = "attached",
    val privateIp: String = "",
    /** The server's own work user the hub logs in as (`forex` on FX), never root. */
    val user: String = "",
    /** `SHA256:…`, pinned at attach time; a different key is `409 host_key_changed` until the owner re-pins. */
    val hostKeySha256: String = "",
    /** `pending` · `reachable` · `unreachable` · `host_key_changed` */
    val state: String = "pending",
    val lastSeenAt: String? = null,
    /** When the latest `server.map` was taken; null before the first. */
    val mapAt: String? = null,
) {
    val reachable: Boolean get() = state == "reachable"

    /** The step-up target of every seal scoped to this server (§26.3 writes `<CODE>:<server>` for `server.destructive`; the app uses the
     *  same target for re-pinning and detaching, which §26.4 leaves unnamed). */
    val target: String get() = "$company:$name"

    /** `forex@10.10.1.2`, as the owner would type it. */
    val login: String get() = if (user.isBlank()) privateIp else "$user@$privateIp"
}

/** `201` of `POST /infra/servers/attach`: the server (pending) and the one line to add to the work user's `authorized_keys`. */
data class AttachOut(val server: HubServer?, val publicKey: String)

@Serializable
data class AttachIn(val company: String, val name: String, val privateIp: String, val user: String, val hostKeySha256: String)

/** One call of a server tool, as the activity page and the Audit ledger keep it (§26.3: secrets masked by name and pattern). */
@Serializable
data class ServerCall(
    val id: String? = null,
    val at: String = "",
    val actor: Actor = Actor(),
    /** `server.exec` · `server.read` · `server.write` · `server.claude` · `server.map` */
    val tool: String = "server.exec",
    val summaryFa: String = "",
    val cmdMasked: String? = null,
    /** Null while the call runs (and for a call waiting for the seal). */
    val exitCode: Int? = null,
    val durationMs: Long? = null,
    /** The Claude Code session the call belongs to (`S-…`, the Workshop's session page). */
    val sessionRef: String? = null,
    /** The full transcript, owner-readable (§26.3). */
    val transcriptUrl: String? = null,
    val server: String? = null,
    /** Not in §26.4's row; read when the hub sends it: `awaiting_seal` · `refused`. */
    val state: String? = null,
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
    SealCategory("access_change", "تغییر SSH، کاربرها یا فایروال همین سرور", "sshd_config · authorized_keys · userdel · passwd · ufw · iptables", "ممکن است راه ورود تو و هاب به سرور بسته شود."),
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

enum class CallOutcome { OK, FAILED, RUNNING, AWAITING_SEAL, REFUSED }

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
) {
    val byOwner: Boolean get() = actor.kind == "owner"
}

private fun outcomeOf(exit: Int?, durationMs: Long?, state: String?, code: String?): CallOutcome = when {
    state == "awaiting_seal" || code == "awaiting_seal" -> CallOutcome.AWAITING_SEAL
    state == "refused" || code == "company_locked" || code == "host_key_changed" || code == "deploy_frozen" -> CallOutcome.REFUSED
    exit == null && durationMs == null -> CallOutcome.RUNNING
    exit == 0 -> CallOutcome.OK
    exit == null -> CallOutcome.OK
    else -> CallOutcome.FAILED
}

fun callRow(c: ServerCall): ServerCallRow = ServerCallRow(
    c.at, c.actor, c.tool, SERVER_TOOL_FA[c.tool] ?: c.tool, c.summaryFa, c.cmdMasked?.takeIf { it.isNotBlank() },
    outcomeOf(c.exitCode, c.durationMs, c.state, null), c.exitCode, duration(c.durationMs), c.sessionRef, c.transcriptUrl, c.server,
)

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

// ------------------------------------------------------------------ attaching a server (§26.4) --
/** The checks the app makes before `POST /infra/servers/attach`; the hub checks again. Keys are the wire names, so a `422`'s `fields`
 *  land on the same fields. */
object AttachRules {
    /** The hub's own private address: never attached to itself. */
    const val HUB_IP = "10.10.1.4"

    private val NAME = Regex("^[a-z0-9][a-z0-9-]{1,30}[a-z0-9]$")
    private val USER = Regex("^[a-z_][a-z0-9_-]{0,31}$")
    private val FINGERPRINT = Regex("SHA256:([A-Za-z0-9+/]{43})=?")

    fun ipv4(s: String): IntArray? {
        val parts = s.trim().split('.')
        if (parts.size != 4) return null
        val out = IntArray(4)
        for ((i, p) in parts.withIndex()) {
            if (p.isEmpty() || p.length > 3 || !p.all(Char::isDigit) || (p.length > 1 && p[0] == '0')) return null
            out[i] = p.toInt().takeIf { it in 0..255 } ?: return null
        }
        return out
    }

    /** RFC 1918: 10/8, 172.16/12, 192.168/16 (the Hetzner private network is one of them). */
    fun isPrivate(ip: String): Boolean {
        val a = ipv4(ip) ?: return false
        return a[0] == 10 || (a[0] == 172 && a[1] in 16..31) || (a[0] == 192 && a[1] == 168)
    }

    /** The `SHA256:…` fingerprint inside whatever the owner pasted (`ssh-keygen -lf` prints `256 SHA256:… root@fx (ED25519)`); null when
     *  there is none. The base64 of 32 bytes is 43 characters without its padding. */
    fun hostKey(raw: String): String? = FINGERPRINT.find(raw.trim())?.let { "SHA256:" + it.groupValues[1] }

    /** Every field's problem in Persian; empty when the form can be sent. */
    fun validate(f: AttachIn, existing: List<HubServer> = emptyList()): Map<String, String> {
        val e = linkedMapOf<String, String>()
        if (f.company.isBlank()) e["company"] = "شرکت را انتخاب کن."
        val name = f.name.trim()
        when {
            name.isEmpty() -> e["name"] = "یک نام کوتاه لاتین بده؛ مثلاً fx-main."
            !NAME.matches(name) -> e["name"] = "فقط حروف کوچک لاتین، عدد و خط تیره؛ ۳ تا ۳۲ نویسه."
            existing.any { it.company == f.company && it.name == name } -> e["name"] = "این شرکت سروری با همین نام دارد."
        }
        val ip = f.privateIp.trim()
        when {
            ip.isEmpty() -> e["private_ip"] = "آدرس خصوصی سرور را بنویس؛ مثلاً 10.10.1.2."
            ipv4(ip) == null -> e["private_ip"] = "این یک آدرس IPv4 درست نیست."
            !isPrivate(ip) -> e["private_ip"] = "فقط آدرس شبکه‌ی خصوصی (10.x، 172.16–31.x، 192.168.x)؛ هاب از اینترنت به سرور شرکت وصل نمیشود."
            ip == HUB_IP -> e["private_ip"] = "این آدرس خود هاب است."
            existing.any { it.privateIp == ip } -> e["private_ip"] = "سروری با همین آدرس از قبل وصل است."
        }
        val user = f.user.trim()
        when {
            user.isEmpty() -> e["user"] = "کاربر کاری سرور را بنویس؛ مثلاً forex."
            user == "root" -> e["user"] = "هاب با root وارد نمیشود؛ کاربر کاری همان سرور را بده."
            !USER.matches(user) -> e["user"] = "نام کاربر لینوکس: حروف کوچک لاتین، عدد، _ و -."
        }
        when {
            f.hostKeySha256.isBlank() -> e["host_key_sha256"] = "اثر کلید میزبان را بچسبان؛ خروجی ssh-keygen -lf روی همان سرور."
            hostKey(f.hostKeySha256) == null -> e["host_key_sha256"] = "باید به شکل SHA256: و ۴۳ نویسه باشد."
        }
        return e
    }

    /** The line the server's work user adds to `~/.ssh/authorized_keys`, with the restrictions of COMPANY_SERVER_ACCESS_SETUP.md: the
     *  hub's `public_key` as sent when it already carries its options, else those options in front of it. */
    fun authorizedLine(publicKey: String): String {
        val k = publicKey.trim()
        return if (k.startsWith("ssh-") || k.startsWith("ecdsa-")) "from=\"$HUB_IP\",no-agent-forwarding,no-X11-forwarding,no-port-forwarding $k" else k
    }

    /** The body as sent: trimmed, the fingerprint normalised. */
    fun body(f: AttachIn): AttachIn = AttachIn(f.company.trim(), f.name.trim(), f.privateIp.trim(), f.user.trim(), hostKey(f.hostKeySha256) ?: f.hostKeySha256.trim())
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

data class MapContainer(val name: String, val image: String?, val state: String, val status: String?, val project: String?)
data class MapCompose(val project: String, val dir: String?, val services: Int?, val running: Int?)
data class MapUnit(val name: String, val state: String?, val description: String?)
data class MapTimer(val unit: String, val next: String?, val last: String?, val activates: String?)
data class MapCron(val schedule: String, val command: String, val user: String?)
data class MapPort(val port: Int, val proto: String, val address: String?, val process: String?)
data class MapRepo(val path: String, val remote: String?, val branch: String?, val head: String?, val dirty: Boolean?)
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
        val n8n = o["n8n"]
        return ServerMap(
            at = at,
            hostname = o.s("hostname") ?: o.s("host"),
            os = os,
            kernel = kernel,
            cpus = (o["cpus"] as? JsonPrimitive)?.intOrNull ?: (o["cpu"] as? JsonObject)?.let { (it["cores"] as? JsonPrimitive)?.intOrNull ?: (it["count"] as? JsonPrimitive)?.intOrNull },
            uptimeS = (o["uptime_s"] as? JsonPrimitive)?.longOrNull ?: (o["uptime"] as? JsonPrimitive)?.longOrNull,
            load = (o["load"] as? JsonPrimitive)?.doubleOrNull ?: ((o["load"] as? JsonArray)?.firstOrNull() as? JsonPrimitive)?.doubleOrNull,
            disks = (o["disks"] ?: o["disk"]).let { d ->
                when (d) {
                    is JsonArray -> d.mapNotNull { usage(it as? JsonObject, "/") }
                    is JsonObject -> listOfNotNull(usage(d, "/"))
                    else -> emptyList()
                }
            },
            memory = usage((o["memory"] ?: o["mem"] ?: o["ram"]) as? JsonObject, "RAM"),
            swap = usage(o["swap"] as? JsonObject ?: (o["memory"] as? JsonObject)?.get("swap") as? JsonObject, "swap")?.takeIf { it.totalBytes > 0 },
            containers = list(o["containers"] ?: (o["docker"] as? JsonObject)?.get("containers")).mapNotNull(::container),
            compose = list(o["compose"] ?: o["compose_projects"] ?: (o["docker"] as? JsonObject)?.get("compose")).mapNotNull(::compose),
            units = list(systemd?.get("units") ?: systemd?.get("services") ?: o["units"] ?: o["services"]).mapNotNull(::unit),
            timers = list(systemd?.get("timers") ?: o["timers"]).mapNotNull(::timer),
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
        return MapContainer(name.removePrefix("/"), o.s("image"), state.lowercase(), status, o.s("compose_project") ?: o.s("project") ?: labels?.s("com.docker.compose.project"))
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
        val cmd = o.s("command") ?: o.s("cmd") ?: return null
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
        return MapPort(port, o.s("proto") ?: o.s("protocol") ?: "tcp", o.s("address") ?: o.s("bind") ?: o.s("host"), o.s("process") ?: o.s("program") ?: o.s("service"))
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
        return MapRepo(path, remote, o.s("branch"), (o.s("head") ?: o.s("commit"))?.take(12), o.b("dirty"))
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
    "host_key_changed" to "کلید میزبان این سرور عوض شده؛ تا دوباره pin نکنی هیچ فرمانی اجرا نمیشود.",
    "company_locked" to "کلید توقف این شرکت زده شده؛ هر کاری روی سرورهایش ایستاده است.",
    "deploy_frozen" to "deploy این شرکت بسته است؛ فرمان‌های انتشار رد میشوند.",
    "awaiting_seal" to "این کار ویرانگر است و منتظر مُهر تو ماند.",
    "server_unreachable" to "هاب الان به این سرور نمیرسد.",
)

/** A §26 refusal in Persian (the hub's sentence for any other code). */
fun serverError(e: ApiException): String = CODE_FA_21[e.code] ?: e.messageFa
