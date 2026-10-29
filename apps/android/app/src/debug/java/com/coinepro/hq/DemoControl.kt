package com.coinepro.hq

import com.coinepro.hq.core.format.HqClock
import com.coinepro.hq.core.net.StreamEvent
import java.time.temporal.ChronoUnit
import java.util.concurrent.ConcurrentLinkedQueue
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.put

/**
 * Debug builds only: the owner's control over the demo holding (contract §9) as the hub answers it, so the screens and their
 * screenshots show it working.
 *
 * - A holding in mixed states: Pro-Chart stopped by its CEO forty minutes ago (with its reason), CoinePro FX's deploys closed by the
 *   release pipeline, TradeYar and the holding running; their history (who, when, why) in the audit rows and the owner's own
 *   control actions with their reasons (`GET /owner/interactions?kind=control`).
 * - `POST /control/kill-switch`: engaging needs nothing, releasing needs the step-up header (`403 step_up_required` without it);
 *   the switch, the company rows and the history change, and the stream says so ([DemoLive]): a stopped company's runs end.
 * - `POST /control/deploy-freeze`: a span closes the deploys, a past `until` lifts every freeze of the company.
 */
internal class ControlDemo(private val store: MutableMap<String, Pair<Int, JsonElement>>) {
    private val audit = mutableListOf<JsonObject>()
    private val interactions = mutableListOf<JsonObject>()
    private var seq = 5000L

    init {
        fun at(minutes: Long) = HqClock.now().minus(minutes, ChronoUnit.MINUTES).toString()
        // Pro-Chart: stopped by its CEO, who found the terminal's prices wrong in production.
        val reason = "قیمت‌های ترمینال در تولید اشتباه نمایش داده میشد؛ تا رفع خطا متوقف شد."
        switch("company:PC", "engaged", reason, "PC-CEO", at(38))
        row("PC", "kill_switch.engage", "kill_switch", "company:PC", agent("PC-CEO", "مدیرعامل پرو-چارت"), at(38), "changed: engaged")
        // The holding's own switch, tested by the owner last week.
        row("HQ", "kill_switch.release", "kill_switch", "holding", OWNER, at(60 * 24 * 6 - 12), "changed: released", stepUp = true)
        row("HQ", "kill_switch.engage", "kill_switch", "holding", OWNER, at(60 * 24 * 6), "changed: engaged")
        interaction("HQ", "kill_switch.set", "kill_switch", "holding", at(60 * 24 * 6 - 12), "released", "آزمایش تمام شد.")
        interaction("HQ", "kill_switch.set", "kill_switch", "holding", at(60 * 24 * 6), "engaged", "آزمایش کلید توقف کل هلدینگ")
        // TradeYar: stopped by the owner three days ago over a campaign's spend, released an hour later.
        row("TY", "kill_switch.release", "kill_switch", "company:TY", OWNER, at(60 * 72 - 70), "changed: released", stepUp = true)
        row("TY", "kill_switch.engage", "kill_switch", "company:TY", OWNER, at(60 * 72), "changed: engaged")
        interaction("TY", "kill_switch.set", "kill_switch", "company:TY", at(60 * 72 - 70), "released", "سقف روزانه‌ی کمپین درست شد.")
        interaction("TY", "kill_switch.set", "kill_switch", "company:TY", at(60 * 72), "engaged", "مصرف کمپین پاییز از کنترل خارج شد.")
        // CoinePro FX: the release pipeline closed its deploys while a release is out.
        row("FX", "deploy_freeze.set", "company", "FX", buildJsonObject { put("kind", "service"); put("code", "pipeline"); put("display_fa", "خط انتشار") }, at(25), "active")
        companies("PC") { JsonObject(it + ("kill_switch" to JsonPrimitive("engaged"))) }
        DemoLive.reset(stopped = setOf("PC"))
    }

    fun handle(method: String, path: String, query: Map<String, String?>, body: JsonObject?, stepUp: String?): Pair<Int, JsonElement>? {
        if (method == "GET" && path == "/audit" && (query["company"] != null || query["action"] != null)) {
            // The fixture's own rows are a sample of every kind; a company's control history is this demo's.
            val rows = (audit + list("/audit").map { it.jsonObject }.filterNot { it.str("action").orEmpty().let { a -> a.startsWith("kill_switch.") || a.startsWith("deploy_freeze.") } })
                .filter { r -> (query["company"] == null || r.str("company") == query["company"]) && (query["action"] == null || r.str("action") == query["action"]) }
                .sortedByDescending { it.str("at") }
            return 200 to page(rows.take(query["limit"]?.toIntOrNull() ?: 50))
        }
        if (method == "GET" && path == "/owner/interactions") {
            return 200 to page(interactions.filter { query["kind"] == null || it.str("kind") == query["kind"] }.sortedByDescending { it.str("at") })
        }
        if (method == "POST" && path == "/control/kill-switch") return killSwitch(body ?: JsonObject(emptyMap()), stepUp)
        if (method == "POST" && path == "/control/deploy-freeze") return freeze(body ?: JsonObject(emptyMap()))
        return null
    }

    private fun killSwitch(b: JsonObject, stepUp: String?): Pair<Int, JsonElement> {
        val scope = b.str("scope") ?: return 422 to problem(422, "validation_failed", "دامنه لازم است.")
        val state = b.str("state") ?: "engaged"
        val reason = b.str("reason").orEmpty()
        if (state == "released" && stepUp == null) return 403 to problem(403, "step_up_required", "این کار تأیید با اثر انگشت یا چهره میخواهد.")
        val code = if (scope == "holding") holdingCode() else scope.removePrefix("company:")
        val now = HqClock.now().toString()
        switch(scope, state, reason, "owner", now)
        companies(code) { JsonObject(it + ("kill_switch" to JsonPrimitive(state))) }
        row(code, "kill_switch.${if (state == "engaged") "engage" else "release"}", "kill_switch", scope, OWNER, now, "changed: $state", stepUp = stepUp != null)
        interaction(code, "kill_switch.set", "kill_switch", scope, now, state, reason)
        DemoLive.stopped = if (state == "engaged") DemoLive.stopped + code else DemoLive.stopped - code
        DemoLive.control(code, scope, state)
        return 200 to store["/control/state"]!!.second
    }

    private fun freeze(b: JsonObject): Pair<Int, JsonElement> {
        val co = b.str("company") ?: return 422 to problem(422, "validation_failed", "شرکت لازم است.")
        if (co == holdingCode()) return 422 to problem(422, "validation_failed", "هلدینگ deploy ندارد؛ کلید توقفش را بزن.")
        val until = b.str("until") ?: return 422 to problem(422, "validation_failed", "زمان لازم است.")
        val reason = b.str("reason").orEmpty()
        val active = java.time.Instant.parse(until).isAfter(HqClock.now())
        edit("/control/state") { c ->
            val rest = c["deploy_freezes"]!!.jsonArray.filter { it.jsonObject.str("company") != co }
            c + ("deploy_freezes" to JsonArray(if (active) rest + buildJsonObject { put("company", co); put("until", until); put("reason", reason); put("created_by", "owner") } else rest))
        }
        companies(co) { JsonObject(it + ("deploy_freeze_until" to if (active) JsonPrimitive(until) else JsonNull)) }
        val now = HqClock.now().toString()
        row(co, "deploy_freeze.set", "company", co, OWNER, now, if (active) "active" else "lifted")
        interactions.add(0, buildJsonObject {
            put("id", "i${seq++}"); put("at", now); put("company", co); put("kind", "control"); put("action", "deploy_freeze.set")
            put("target", buildJsonObject { put("kind", "company"); put("ref", co) })
            put("data", buildJsonObject { put("until", until); put("reason", reason) })
        })
        DemoLive.control(co, "company:$co", if (active) "frozen" else "open")
        return 200 to buildJsonObject { put("company", co); put("active", active); put("until", until) }
    }

    // ----------------------------------------------------------------- store --
    private fun switch(scope: String, state: String, reason: String, by: String, at: String) {
        val change = mapOf("state" to JsonPrimitive(state), "reason" to JsonPrimitive(reason), "changed_at" to JsonPrimitive(at), "changed_by" to JsonPrimitive(by))
        edit("/control/state") { c ->
            if (scope == "holding") c + ("holding" to JsonObject(c["holding"]!!.jsonObject + change))
            else c + ("companies" to JsonArray(c["companies"]!!.jsonArray.map { k -> if (k.jsonObject.str("scope") == scope) JsonObject(k.jsonObject + change) else k }))
        }
    }

    private fun companies(code: String, f: (JsonObject) -> JsonObject) {
        store["/companies"]?.let { (st, v) -> store["/companies"] = st to JsonArray(v.jsonArray.map { c -> if (c.jsonObject.str("code") == code) f(c.jsonObject) else c }) }
        store["/companies/$code"]?.let { (st, v) -> store["/companies/$code"] = st to f(v.jsonObject) }
    }

    private fun row(company: String, action: String, kind: String, ref: String, actor: JsonObject, at: String, summary: String, stepUp: Boolean = false) {
        audit.add(buildJsonObject {
            put("seq", seq++); put("at", at); put("actor", actor); put("principal_kind", actor.str("kind") ?: "owner"); put("company", company)
            put("action", action); put("action_class", "A2"); put("target", buildJsonObject { put("kind", kind); put("ref", ref) })
            put("request_id", JsonNull); put("ip_hash", JsonNull); put("step_up", stepUp); put("summary", summary); put("prev_hash", "…"); put("hash", "…")
        })
    }

    private fun interaction(company: String, action: String, kind: String, ref: String, at: String, state: String, reason: String) {
        interactions.add(buildJsonObject {
            put("id", "i${seq++}"); put("at", at); put("company", company); put("kind", "control"); put("action", action)
            put("target", buildJsonObject { put("kind", kind); put("ref", ref) })
            put("data", buildJsonObject { put("state", state); put("reason", reason) })
        })
    }

    private fun holdingCode(): String = list("/companies").map { it.jsonObject }.firstOrNull { it.str("kind") == "holding" }?.str("code") ?: "HQ"

    private fun edit(key: String, f: (JsonObject) -> Map<String, JsonElement>) {
        val (st, v) = store[key] ?: return
        store[key] = st to JsonObject(f(v.jsonObject))
    }

    private fun list(key: String): List<JsonElement> = store[key]?.second?.let { (it as? JsonObject)?.get("items") ?: it }?.jsonArray.orEmpty()
    private fun page(items: List<JsonElement>) = buildJsonObject { put("items", JsonArray(items)); put("next_cursor", JsonNull) }
    private fun problem(status: Int, code: String, fa: String) = buildJsonObject { put("code", code); put("message_fa", fa); put("status", status); put("title", code); put("type", "about:blank") }
    private fun JsonObject.str(k: String): String? = (this[k] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull

    private companion object {
        val OWNER = buildJsonObject { put("kind", "owner"); put("code", "owner"); put("display_fa", "مدیر کل") }
        fun agent(code: String, fa: String) = buildJsonObject { put("kind", "agent"); put("code", code); put("display_fa", fa) }
    }
}

/**
 * The demo holding's live stream (debug builds): a calm script of runs starting and finishing, outputs and cards arriving, every few
 * seconds; a company the owner stopped stays quiet; and what the owner's control actions cause comes first (`control.changed`, the
 * stopped company's runs ending).
 */
internal object DemoLive {
    @Volatile var stopped: Set<String> = emptySet()
    private val queue = ConcurrentLinkedQueue<StreamEvent>()
    private var seq = 0
    private var step = 0
    /** Runs the script started and has not finished yet, by company. */
    private val running = mutableMapOf<String, MutableList<Pair<String, String>>>()

    private data class Beat(val company: String, val type: String, val ref: String?, val data: Map<String, String>)

    /** The script: one beat about every two and a half seconds, in a loop. */
    private val SCRIPT = listOf(
        Beat("TY", "run.started", "run-d1", mapOf("employee" to "TY-GROWTH-01", "trigger" to "work", "work" to "W-000102")),
        Beat("FX", "run.step", "run-0", mapOf("employee" to "FX-TECH-MGR")),
        Beat("PC", "run.started", "run-d2", mapOf("employee" to "PC-TECH-MGR", "trigger" to "work", "work" to "W-000108")),
        Beat("TY", "deliverable.created", "O-000041", mapOf("producer" to "TY-GROWTH-01")),
        Beat("TY", "run.finished", "run-d1", mapOf("employee" to "TY-GROWTH-01", "state" to "done")),
        Beat("FX", "decision.created", "D-000085", mapOf("kind" to "email_send")),
        Beat("PC", "run.finished", "run-d2", mapOf("employee" to "PC-TECH-MGR", "state" to "done")),
        Beat("FX", "run.started", "run-d3", mapOf("employee" to "FX-QUANT-02", "trigger" to "schedule")),
        Beat("HQ", "work.updated", "W-000130", mapOf("status" to "in_progress")),
        Beat("FX", "deliverable.created", "O-000042", mapOf("producer" to "FX-QUANT-02")),
        Beat("FX", "run.finished", "run-d3", mapOf("employee" to "FX-QUANT-02", "state" to "done")),
    )

    /** A new demo session starts from the script's beginning, with nothing queued. */
    fun reset(stopped: Set<String>) {
        this.stopped = stopped
        queue.clear()
        step = 0
        synchronized(running) { running.clear() }
    }

    fun next(tick: Int): List<StreamEvent> {
        val out = mutableListOf<StreamEvent>()
        while (true) out += queue.poll() ?: break
        if (tick % 4 == 0) beat()?.let { out += it }
        return out
    }

    /** What a change of control makes the stream say; stopping a company ends its runs. */
    fun control(code: String, scope: String, state: String) {
        queue += event(code, "control.changed", scope, mapOf("state" to state, "by" to "owner"))
        if (state == "engaged") {
            val gone = synchronized(running) { running.remove(code).orEmpty() }
            for ((run, employee) in gone) {
                queue += event(code, "run.finished", run, mapOf("employee" to employee, "state" to "refused", "code" to "company_locked"))
                queue += event(code, "activity.changed", employee, mapOf("activity" to "sleeping"))
            }
        }
    }

    private fun beat(): List<StreamEvent>? {
        repeat(SCRIPT.size) {
            val b = SCRIPT[step++ % SCRIPT.size]
            if (b.company in stopped && b.type != "run.finished") return@repeat
            val employee = b.data["employee"]
            synchronized(running) {
                when (b.type) {
                    "run.started" -> if (employee != null) running.getOrPut(b.company) { mutableListOf() }.add(b.ref!! to employee)
                    "run.finished" -> if (running[b.company]?.removeAll { it.first == b.ref } != true) return@repeat
                }
            }
            val main = event(b.company, b.type, b.ref, b.data)
            val activity = when (b.type) {
                "run.started" -> employee?.let { event(b.company, "activity.changed", it, mapOf("activity" to "working")) }
                "run.finished" -> employee?.let { event(b.company, "activity.changed", it, mapOf("activity" to "sleeping")) }
                else -> null
            }
            return listOfNotNull(main, activity)
        }
        return null
    }

    private fun event(company: String, type: String, ref: String?, data: Map<String, String>) =
        StreamEvent("demo-${++seq}", type, HqClock.now().toString(), company, ref, JsonObject(data.mapValues { JsonPrimitive(it.value) }))
}
