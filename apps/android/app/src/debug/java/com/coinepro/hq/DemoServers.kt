package com.coinepro.hq

import com.coinepro.hq.core.format.HqClock
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.AttachRules
import com.coinepro.hq.core.net.StreamEvent
import java.time.temporal.ChronoUnit
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.long
import kotlinx.serialization.json.put
import kotlinx.serialization.json.putJsonArray
import kotlinx.serialization.json.putJsonObject
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.Protocol
import okhttp3.Request
import okhttp3.Response
import okhttp3.ResponseBody.Companion.asResponseBody
import okhttp3.ResponseBody.Companion.toResponseBody
import okio.Buffer
import okio.Source
import okio.Timeout
import okio.buffer

/**
 * Debug builds only: the holding's servers (contract §26 ⟨1.8⟩) as `company-ops` would answer, so every server screen works offline.
 *
 * - CoinePro FX's server (`fx-main`, 10.10.1.2, user `forex`) reachable with a rich map; TradeYar's (`ty-web`) reachable; Pro-Chart's
 *   (`pc-app`) attached and still pending (and locked: Pro-Chart is stopped in the demo).
 * - Activity: FX's CTO deploying (one call still running), TradeYar's SEO analyst reading the nginx config, a Claude Code session on TY's
 *   server (`runtime: company_server`) working live; one destructive command (`DROP TABLE`) waiting for the seal as a `server_destructive`
 *   card.
 * - The owner's terminal answers a few commands as a server would, streamed line by line as SSE; a destructive one becomes a card (202),
 *   a stopped company refuses (423). Attach, re-pin, detach and the policy check the step-up header like the hub.
 *
 * The world wakes the first time anything asks for `/infra/servers` (the owner opens a server page), so screens that never show servers,
 * and their screenshots, see the holding exactly as before.
 */
internal class ServersDemo(private val store: MutableMap<String, Pair<Int, JsonElement>>) {
    @Volatile var awake = false
        private set
    /** For the screenshot tests: nothing moves on its own (no session steps revealed, no agents' calls on the stream). */
    @Volatile var still = false
    private var wokeTick: Int? = null
    private var beat = 0
    private var seq = 100
    private val servers = mutableListOf<JsonObject>()
    private val maps = mutableMapOf<String, JsonObject>()
    private val activity = mutableMapOf<String, MutableList<JsonObject>>()
    private var policy = listOf("db_drop", "volume_delete", "backup_delete", "disk_wipe", "access_change", "server_delete")
    private val scripts = mutableMapOf<String, MutableList<JsonObject>>()
    private val mine = mutableSetOf<String>()
    /** Polls of the server list since an attach, so a new server turns reachable a few seconds later. */
    private val attaching = mutableMapOf<String, Int>()
    private val queue = java.util.concurrent.ConcurrentLinkedQueue<StreamEvent>()
    private var nextCard = 202

    init { DemoLive.servers = this }

    private fun at(minutes: Long) = HqClock.now().plus(minutes, ChronoUnit.MINUTES).toString()
    private val now: String get() = HqClock.now().toString()

    /** The servers, their maps and activity, the session on TY and the card waiting for the seal: made once, on first use. */
    @Synchronized
    fun wake() {
        if (awake) return
        awake = true
        servers += server("srv-fx-1", "FX", "fx-main", "10.10.1.2", "forex", "SHA256:q3XmF0b8Zk1v7R2pTnYw4cJdL6eUa9sHgVxQ5oNiB0M", "reachable", at(-1), at(-12))
        servers += server("srv-ty-1", "TY", "ty-web", "10.10.1.3", "tradeyar", "SHA256:Lr8Yk2dWq5NfT0xHb3VzCm7Pj9aEs4GuK1oRiD6tXcQ", "reachable", at(-2), at(-40))
        servers += server("srv-pc-1", "PC", "pc-app", "10.10.1.1", "prochart", "SHA256:Ze4Tn8Qa1LmW6xVb0RkJy3Ps9DfGh5Uc2oNiE7tKsHw", "pending", null, null)
        maps["srv-fx-1"] = fxMap(at(-12))
        maps["srv-ty-1"] = tyMap(at(-40))
        activity["srv-fx-1"] = mutableListOf(
            call("FX-TECH-MGR", "مدیر فنی FX", "server.exec", "انتشار API: ساخت و بالا آوردن کانتینر تازه", "docker compose up -d --build api", null, null, -1),
            call("FX-TECH-MGR", "مدیر فنی FX", "server.exec", "migration پایگاه داده اجرا شد", "docker compose exec -T api alembic upgrade head", 0, 6_420, -3),
            call("FX-TECH-MGR", "مدیر فنی FX", "server.exec", "آخرین کد از GitHub", "git pull --ff-only origin claude/wizardly-edison-zyWyW", 0, 2_310, -4),
            call("FX-TECH-MGR", "مدیر فنی FX", "server.exec", "تست‌های فاز ۱۵ پیش از انتشار سبز", "python -m pytest tests/test_phase15*.py -q", 0, 48_900, -9, transcript = true),
            call("FX-QUANT-02", "پایشگر سیگنال", "server.read", "خواندن لاگ موتور سیگنال", "tail -n 200 logs/signals.log", 0, 140, -18),
            call("HQ-SYS", "سیستم", "server.map", "نقشه‌ی سرور گرفته شد", null, 0, 3_870, -12),
        ).also { it.sortByDescending { r -> r.s("at") } }
        // A Claude Code session on TradeYar's server, run by its CTO, live; and its SEO analyst reading the nginx config.
        val ref = "S-0011"
        mine += ref
        val tech = actor("TY-TECH-MGR", "مدیر فنی تریدیار", "manager")
        activity["srv-ty-1"] = mutableListOf(
            call("TY-TECH-MGR", "مدیر فنی تریدیار", "server.claude", "Claude Code روی سرور: کش nginx صفحه‌های بازار", null, null, null, -6, session = ref),
            call("TY-TECH-MGR", "مدیر فنی تریدیار", "server.exec", "پیکربندی nginx سالم است", "sudo nginx -t", 0, 210, -3, session = ref),
            call("TY-GROWTH-01", "تحلیلگر سئوی فنی", "server.read", "خواندن پیکربندی nginx برای canonical و redirectها", "cat /etc/nginx/sites-enabled/tradeyar.conf", 0, 90, -2),
            call("TY-GROWTH-01", "تحلیلگر سئوی فنی", "server.exec", "سرعت پاسخ صفحه‌ی اصلی", "curl -s -o /dev/null -w '%{time_total}' https://tradeyar.com/", 0, 1_180, -7),
        ).also { it.sortByDescending { r -> r.s("at") } }
        val session = buildJsonObject {
            put("id", "s-$ref"); put("ref", ref); put("workspace", ""); put("grant", ""); put("runtime", "company_server"); put("server", "srv-ty-1"); put("company", "TY")
            put("title", "کش nginx برای صفحه‌های بازار"); put("brief", "صفحه‌های بازار تریدیار در ساعت شلوغی کند میشوند. کش nginx را برای مسیرهای /market فعال کن، با nginx -t بسنج، reload کن، زمان پاسخ را قبل و بعد اندازه بگیر و تغییر را در ریپو commit و push کن.")
            put("opened_by", OWNER); put("driver", tech); put("model", "claude-sonnet-5-5"); put("effort", "high"); put("state", "working")
            put("branch", "main"); put("pr_url", JsonNull); putJsonObject("usage") { put("usd", 0.62); put("input_tokens", 84_000); put("output_tokens", 6_100) }
            put("created_at", at(-6)); put("updated_at", at(-1))
        }
        store["/workshop/sessions/$ref"] = 200 to session
        val all = list("/workshop/sessions")
        store["/workshop/sessions"] = 200 to page(listOf<JsonElement>(session) + all)
        val sys = actor("HQ-SYS", "سیستم", "system")
        store["/workshop/sessions/$ref/events"] = 200 to page(listOf(
            ev(1, -6, "state", sys, "Claude Code روی ty-web شروع شد؛ در /home/tradeyar/TradeYar", buildJsonObject { put("state", "working") }),
            ev(2, -6, "message", tech, "شروع کردم. اول زمان پاسخ فعلی /market را میگیرم و پیکربندی nginx را میخوانم."),
            ev(3, -5, "command", tech, "میانگین زمان پاسخ /market در ده درخواست: ۱٫۸ ثانیه", buildJsonObject { put("cmd", "for i in $(seq 10); do curl -s -o /dev/null -w '%{time_total}\\n' https://tradeyar.com/market; done"); put("exit_code", 0); put("duration_s", 19) }),
            ev(4, -4, "file_change", tech, "منطقه‌ی کش و قاعده‌ی /market", buildJsonObject { put("path", "deploy/nginx/tradeyar.conf"); put("added", 14); put("removed", 2) }),
            ev(5, -3, "command", tech, "پیکربندی nginx سالم است", buildJsonObject { put("cmd", "sudo nginx -t"); put("exit_code", 0); put("duration_s", 1) }),
        ))
        scripts[ref] = mutableListOf(
            step("command", tech, "nginx بدون قطع سرویس دوباره بارگذاری شد", buildJsonObject { put("cmd", "sudo systemctl reload nginx"); put("exit_code", 0); put("duration_s", 1) }),
            step("command", tech, "بعد از کش: میانگین ۰٫۲۴ ثانیه (۷ برابر سریع‌تر)", buildJsonObject { put("cmd", "for i in $(seq 10); do curl -s -o /dev/null -w '%{time_total}\\n' https://tradeyar.com/market; done"); put("exit_code", 0); put("duration_s", 4) }),
            step("command", tech, "commit و push روی main", buildJsonObject { put("cmd", "git commit -am 'nginx: cache /market for 60s' && git push origin main"); put("exit_code", 0); put("duration_s", 3) }),
            step("message", tech, "**تمام شد.** کش ۶۰ ثانیه‌ای روی `/market` فعال است، زمان پاسخ از ۱٫۸ به ۰٫۲۴ ثانیه رسید و تغییر در `deploy/nginx/tradeyar.conf` روی main است."),
            step("state", sys, "تمام شد", buildJsonObject { put("state", "done") }),
        )
    }

    /** The card arrives a few seconds after the servers wake (the owner sees it come live, with its toast); the tests raise it at once. */
    @Volatile private var sealRaised = false

    /** FX's CTO wanted an old backtest table gone; the gateway held it (db_drop): the activity row, the card and the stream's event. */
    @Synchronized
    fun raiseSeal() {
        if (sealRaised) return
        wake()
        sealRaised = true
        activity.getOrPut("srv-fx-1") { mutableListOf() }.add(0, call("FX-TECH-MGR", "مدیر فنی FX", "server.exec", "DROP TABLE نگه داشته شد؛ منتظر مُهر مدیر کل", "docker compose exec -T timescaledb psql -U forex -d coinepro -c \"DROP TABLE signals_backtest_2025;\"", null, null, 0, state = "awaiting_seal"))
        val card = buildJsonObject {
            put("id", "d-srv-201"); put("ref", "D-000201"); put("company", "FX"); put("kind", "server_destructive")
            put("title", "پاک کردن جدول بک‌تست پارسال روی fx-main")
            put("what", "اجرای `DROP TABLE signals_backtest_2025;` روی دیتابیس TimescaleDB سرور fx-main.")
            put("why", "جدول بک‌تست سال قبل ۱۸ گیگابایت جا گرفته و دیگر خوانده نمیشود؛ نتیجه‌هایش در گزارش O-000038 بایگانی شده است.")
            put("risk", "high"); put("risk_note", "برگشت‌ناپذیر است؛ آخرین پشتیبان این جدول مال دیشب ساعت ۲:۳۰ است.")
            put("action_class", "A3"); put("reversible", false); put("status", "pending")
            put("proposer", actor("FX-TECH-MGR", "مدیر فنی FX", "manager")); put("created_at", now); put("expires_at", at(60 * 24))
            putJsonObject("payload") {
                putJsonObject("server") { put("id", "srv-fx-1"); put("name", "fx-main") }
                put("company", "FX"); put("category", "db_drop"); put("tool", "server.exec")
                put("cmd", "docker compose exec -T timescaledb psql -U forex -d coinepro -c \"DROP TABLE signals_backtest_2025;\"")
                put("cwd", "/home/forex/CoinePro-FX"); put("detected_by", "pattern"); put("pattern", "DROP TABLE"); put("session_ref", JsonNull)
                put("actor", actor("FX-TECH-MGR", "مدیر فنی FX", "manager"))
            }
            putJsonObject("quota_estimate") { put("tokens", 0); put("usd", "0") }
            put("version", 1); putJsonArray("memos") {}; putJsonArray("reminders") {}; put("waiting_h", 0.0)
        }
        addDecision(card)
        queue += event("FX", "server.awaiting_seal", "srv-fx-1", mapOf("decision_ref" to "D-000201", "server" to "srv-fx-1", "category" to "db_drop"))
    }

    // --------------------------------------------------------------------------------------------- HTTP --
    fun handle(req: Request, path: String, body: JsonObject?, query: Map<String, String?>): Response? {
        val stepUp = req.header("X-Step-Up")
        val m = req.method
        if (path == "/control/server-policy") {
            if (m == "GET") return json(req, 200, policyJson())
            if (m == "PUT") {
                if (stepUp == null) return json(req, 403, problem(403, "step_up_required", "این کار تأیید با گذرکلید لازم دارد."))
                policy = body?.get("seal_required")?.jsonArray?.mapNotNull { it.jsonPrimitive.contentOrNull }.orEmpty()
                return json(req, 200, policyJson())
            }
        }
        if (path == "/workshop/sessions" && m == "POST" && body?.s("runtime") == "company_server") return json(req, 201, newSession(body))
        Regex("^/workshop/sessions/(S-\\d+)/(events|messages|stop)$").find(path)?.let { x ->
            val ref = x.groupValues[1]
            if (ref !in mine) return null
            return when (x.groupValues[2]) {
                "events" -> {
                    val after = query["after"]?.toLongOrNull() ?: 0
                    if (!still && after > 0 && scripts[ref].orEmpty().isNotEmpty() && Math.random() < 0.7) reveal(ref, scripts.getValue(ref).removeAt(0))
                    json(req, 200, page(list("/workshop/sessions/$ref/events").filter { it.jsonObject["seq"]!!.jsonPrimitive.long > after }))
                }
                "messages" -> {
                    val e = reveal(ref, step("message", OWNER, body?.s("body").orEmpty()))
                    val s = session(ref)
                    if (s.s("state") !in setOf("done", "failed", "stopped")) scripts.getOrPut(ref) { mutableListOf() }.add(0, step("message", s["driver"]!!, "دریافت شد؛ با همان نشست Claude روی سرور ادامه میدهم."))
                    json(req, 201, e)
                }
                else -> {
                    scripts[ref]?.clear()
                    reveal(ref, step("state", OWNER, "مدیر کل متوقف کرد؛ فرایند Claude روی سرور بسته شد", buildJsonObject { put("state", "stopped") }))
                    json(req, 200, session(ref))
                }
            }
        }
        // The seal of the waiting card runs the command (the generic demo decides the card itself).
        if (m == "POST" && path == "/decisions/D-000201/approve" && awake) {
            activity["srv-fx-1"]?.let { rows ->
                rows.removeAll { it.s("state") == "awaiting_seal" }
                rows.add(0, call("FX-TECH-MGR", "مدیر فنی FX", "server.exec", "با مُهر مدیر کل: جدول پاک شد، ۱۸ گیگابایت آزاد شد", "docker compose exec -T timescaledb psql -U forex -d coinepro -c \"DROP TABLE signals_backtest_2025;\"", 0, 1_240, 0))
            }
            return null
        }
        if (m == "POST" && path == "/decisions/D-000201/reject" && awake) {
            activity["srv-fx-1"]?.removeAll { it.s("state") == "awaiting_seal" }
            return null
        }
        Regex("^/audit/transcripts/([^/]+)$").find(path)?.let { t ->
            val text = transcript(t.groupValues[1]) ?: return json(req, 404, problem(404, "not_found", "این متن پیدا نشد."))
            return Response.Builder().request(req).protocol(Protocol.HTTP_1_1).code(200).message("demo").body(text.toResponseBody("text/plain; charset=utf-8".toMediaType())).build()
        }
        if (!path.startsWith("/infra/servers")) return null
        wake()
        if (path == "/infra/servers" && m == "GET") {
            // An attached server is reached after a few looks (the hub tries on its own).
            for ((id, n) in attaching.toMap()) {
                if (n >= 2) { attaching.remove(id); edit(id) { it + mapOf("state" to JsonPrimitive("reachable"), "last_seen_at" to JsonPrimitive(now), "map_at" to JsonPrimitive(now)) }; maps[id] = smallMap(now) }
                else attaching[id] = n + 1
            }
            return json(req, 200, JsonArray(servers))
        }
        if (path == "/infra/servers/attach" && m == "POST") return attach(req, body, stepUp)
        val x = Regex("^/infra/servers/([^/]+)(?:/(map|activity|exec|repin))?$").find(path) ?: return null
        val id = x.groupValues[1]
        val s = servers.firstOrNull { it.s("id") == id } ?: return json(req, 404, problem(404, "not_found", "این سرور پیدا نشد."))
        val company = s.s("company")!!
        return when (x.groupValues[2]) {
            "map" -> when {
                m == "GET" -> maps[id]?.let { json(req, 200, it) } ?: json(req, 404, problem(404, "not_found", "هنوز نقشه‌ای گرفته نشده."))
                company in DemoLive.stopped -> json(req, 423, problem(423, "company_locked", "کلید توقف این شرکت زده شده."))
                s.s("state") != "reachable" -> json(req, 409, problem(409, "server_unreachable", "هاب الان به این سرور نمیرسد."))
                else -> {
                    val fresh = JsonObject((maps[id] ?: smallMap(now)) + ("taken_at" to JsonPrimitive(now)))
                    maps[id] = fresh
                    edit(id) { it + ("map_at" to JsonPrimitive(now)) }
                    activity.getOrPut(id) { mutableListOf() }.add(0, call("owner", "مدیر کل", "server.map", "نقشه‌ی تازه به خواست تو", null, 0, 3_400, 0, kind = "owner"))
                    json(req, 200, fresh)
                }
            }
            "activity" -> {
                val rows = activity[id].orEmpty().filter { r -> query["actor"] == null || (r["actor"] as? JsonObject)?.s("code") == query["actor"] }
                json(req, 200, page(rows.take(query["limit"]?.toIntOrNull() ?: 50)))
            }
            "repin" -> {
                if (stepUp == null) return json(req, 403, problem(403, "step_up_required", "این کار تأیید با گذرکلید لازم دارد."))
                val key = body?.s("host_key_sha256")?.let(AttachRules::hostKey) ?: return json(req, 422, problem(422, "validation_failed", "اثر کلید درست نیست."))
                json(req, 200, edit(id) { it + mapOf("host_key_sha256" to JsonPrimitive(key), "state" to JsonPrimitive(if (it.s("state") == "host_key_changed") "reachable" else it.s("state")!!)) })
            }
            "exec" -> exec(req, s, body, stepUp)
            else -> if (m == "DELETE") {
                if (stepUp == null) return json(req, 403, problem(403, "step_up_required", "این کار تأیید با گذرکلید لازم دارد."))
                servers.removeAll { it.s("id") == id }
                Response.Builder().request(req).protocol(Protocol.HTTP_1_1).code(204).message("demo").body("".toResponseBody(null)).build()
            } else null
        }
    }

    private fun attach(req: Request, body: JsonObject?, stepUp: String?): Response {
        if (stepUp == null) return json(req, 403, problem(403, "step_up_required", "این کار تأیید با گذرکلید لازم دارد."))
        val b = body ?: JsonObject(emptyMap())
        val form = com.coinepro.hq.core.net.AttachIn(b.s("company").orEmpty(), b.s("name").orEmpty(), b.s("private_ip").orEmpty(), b.s("user").orEmpty(), b.s("host_key_sha256").orEmpty())
        val errors = AttachRules.validate(form, servers.map { Api.json.decodeFromJsonElement(com.coinepro.hq.core.net.HubServer.serializer(), it) })
        if (errors.isNotEmpty()) return json(req, 422, buildJsonObject {
            put("code", "validation_failed"); put("message_fa", "چند خانه درست نیست."); put("status", 422); put("title", "validation_failed"); put("type", "about:blank")
            putJsonObject("fields") { for ((k, v) in errors) put(k, v) }
        })
        val id = "srv-${form.company.lowercase()}-${servers.size + 1}"
        val s = server(id, form.company, form.name, form.privateIp, form.user, AttachRules.hostKey(form.hostKeySha256)!!, "pending", null, null)
        servers += s
        attaching[id] = 0
        return json(req, 201, JsonObject(s + ("public_key" to JsonPrimitive("ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIHq9dm0Hn4pXr2vT8kLw3sB6yZcJ1fGe5uQ7aN0oRiPx hq-company-ops@${form.company}:${form.name}"))))
    }

    // -------------------------------------------------------------------------------------------- exec --
    private val destructive = listOf(
        Regex("drop\\s+(table|database|schema)|truncate\\s", RegexOption.IGNORE_CASE) to "db_drop",
        Regex("docker\\s+volume\\s+rm|compose\\s+down\\s+.*-v\\b", RegexOption.IGNORE_CASE) to "volume_delete",
        Regex("rm\\s+-[a-z]*r[a-z]*f?.*backup|restic\\s+forget", RegexOption.IGNORE_CASE) to "backup_delete",
        Regex("\\b(mkfs|fdisk|parted|wipefs)\\b") to "disk_wipe",
        Regex("\\b(userdel|passwd|ufw|iptables)\\b|sshd_config|authorized_keys") to "access_change",
    )

    private fun exec(req: Request, s: JsonObject, body: JsonObject?, stepUp: String?): Response {
        if (stepUp == null) return json(req, 403, problem(403, "step_up_required", "این کار تأیید با گذرکلید لازم دارد."))
        val company = s.s("company")!!
        if (company in DemoLive.stopped) return json(req, 423, problem(423, "company_locked", "کلید توقف این شرکت زده شده؛ هر کاری روی سرورهایش ایستاده است."))
        if (s.s("state") != "reachable") return json(req, 409, problem(409, "server_unreachable", "هاب الان به این سرور نمیرسد."))
        val cmd = body?.s("cmd").orEmpty().trim()
        val id = s.s("id")!!
        val cat = destructive.firstOrNull { it.first.containsMatchIn(cmd) }?.second
        if (cat != null && cat in policy) {
            val ref = "D-%06d".format(nextCard++)
            addDecision(buildJsonObject {
                put("id", "d-$ref"); put("ref", ref); put("company", company); put("kind", "server_destructive"); put("title", "فرمان ویرانگر تو روی ${s.s("name")}")
                put("what", "اجرای فرمانی که در ترمینال نوشتی."); put("why", "دروازه آن را ویرانگر شناخت؛ قوانین سرورها میگوید منتظر مُهر بماند.")
                put("risk", "high"); put("action_class", "A3"); put("reversible", false); put("status", "pending"); put("proposer", OWNER); put("created_at", now); put("expires_at", at(60 * 24))
                putJsonObject("payload") {
                    putJsonObject("server") { put("id", id); put("name", s.s("name")) }
                    put("company", company); put("category", cat); put("tool", "server.exec"); put("cmd", cmd); put("detected_by", "pattern"); put("actor", OWNER)
                }
                putJsonObject("quota_estimate") { put("tokens", 0); put("usd", "0") }; put("version", 1)
            })
            activity.getOrPut(id) { mutableListOf() }.add(0, call("owner", "مدیر کل", "server.exec", "فرمان ویرانگر نگه داشته شد؛ منتظر مُهر", cmd, null, null, 0, kind = "owner", state = "awaiting_seal"))
            queue += event(company, "server.awaiting_seal", id, mapOf("decision_ref" to ref, "server" to id, "category" to cat))
            return json(req, 202, buildJsonObject { put("status", "awaiting_seal"); put("decision_ref", ref); put("message_fa", "این فرمان ویرانگر است؛ کارت $ref در کارتابل منتظر مُهر توست.") })
        }
        val (lines, exit) = output(cmd, s)
        val ms = 180L + lines.size * 40
        activity.getOrPut(id) { mutableListOf() }.add(0, call("owner", "مدیر کل", "server.exec", "فرمان تو از ترمینال اپ", cmd, exit, ms, 0, kind = "owner"))
        queue += event(company, "server.call", id, mapOf("server" to id, "actor" to "owner", "tool" to "server.exec", "summary_fa" to "فرمان تو از ترمینال اپ", "exit_code" to exit.toString()))
        val sse = StringBuilder()
        for ((err, text) in lines) sse.append("event: ").append(if (err) "stderr" else "stdout").append('\n').append("data: ").append(Api.json.encodeToString(JsonObject.serializer(), buildJsonObject { put("text", text + "\n") })).append("\n\n")
        sse.append("event: exit\ndata: {\"exit_code\":$exit,\"duration_ms\":$ms}\n\n")
        // Streamed a few lines at a time, as a real command's output arrives.
        val chunks = sse.toString().split("\n\n").filter { it.isNotEmpty() }.map { "$it\n\n" }
        val source = object : Source {
            private var i = 0
            override fun read(sink: Buffer, byteCount: Long): Long {
                if (i >= chunks.size) return -1
                Thread.sleep(35)
                val bytes = chunks[i++].toByteArray()
                sink.write(bytes)
                return bytes.size.toLong()
            }
            override fun timeout() = Timeout.NONE
            override fun close() = Unit
        }
        return Response.Builder().request(req).protocol(Protocol.HTTP_1_1).code(200).message("demo").header("Content-Type", "text/event-stream")
            .body(source.buffer().asResponseBody("text/event-stream".toMediaType(), -1)).build()
    }

    /** What the demo server prints for a command: (stderr?, line) and the exit code. */
    private fun output(cmd: String, s: JsonObject): Pair<List<Pair<Boolean, String>>, Int> {
        val user = s.s("user")!!
        val name = s.s("name")!!
        val first = cmd.removePrefix("sudo ").trim().split(Regex("\\s+")).firstOrNull().orEmpty()
        fun out(vararg l: String) = l.map { false to it }
        val map = maps[s.s("id")]
        return when {
            cmd.startsWith("docker ps") -> {
                val rows = map?.get("containers")?.jsonArray.orEmpty().map { it.jsonObject }
                (out("CONTAINER ID   IMAGE                                STATUS                    NAMES") + rows.mapIndexed { i, c ->
                    false to "%-14s %-36s %-25s %s".format("%012x".format(0x3fa91c2b7d00L + i * 7919), c.s("image").orEmpty(), c.s("status").orEmpty(), c.s("name"))
                }) to 0
            }
            cmd.startsWith("df") -> out(
                "Filesystem      Size  Used Avail Use% Mounted on",
                "/dev/sda1       150G   62G   82G  43% /",
                "tmpfs           7.8G     0  7.8G   0% /dev/shm",
                "/dev/sda15      253M  6.1M  246M   3% /boot/efi",
            ) to 0
            cmd.startsWith("free") -> out(
                "               total        used        free      shared  buff/cache   available",
                "Mem:            15Gi        11Gi       1.2Gi       214Mi       3.1Gi       4.0Gi",
                "Swap:          8.0Gi       1.1Gi       6.9Gi",
            ) to 0
            cmd.startsWith("uptime") -> out(" 08:30:12 up 22 days,  3:41,  1 user,  load average: 0.84, 0.92, 0.88") to 0
            cmd == "whoami" -> out(user) to 0
            cmd == "hostname" -> out(name) to 0
            cmd.contains("list-timers") -> out(
                "NEXT                         LEFT        LAST                         PASSED  UNIT                     ACTIVATES",
                "Sat 2026-10-17 10:05:00 UTC  1h 35min    Fri 2026-10-16 10:05:00 UTC  22h ago fx-backup.timer          fx-backup.service",
                "Sat 2026-10-17 12:00:00 UTC  3h 30min    Sat 2026-10-17 00:00:00 UTC  8h ago  certbot.timer            certbot.service",
                "Sun 2026-10-18 06:12:00 UTC  21h         Sat 2026-10-17 06:09:41 UTC  2h ago  apt-daily-upgrade.timer  apt-daily-upgrade.service",
                "",
                "3 timers listed.",
            ) to 0
            cmd.startsWith("git") && cmd.contains("status") -> out(
                "On branch ${if (name == "fx-main") "claude/wizardly-edison-zyWyW" else "main"}",
                "Your branch is up to date with 'origin/${if (name == "fx-main") "claude/wizardly-edison-zyWyW" else "main"}'.",
                "",
                "nothing to commit, working tree clean",
            ) to 0
            cmd.startsWith("git") && cmd.contains("log") -> out(
                "a41c09e signals: calibrate LightGBM on the last 90 days",
                "7d20f13 api: index users.email (W-000106)",
                "c9b81aa risk: weekend filter for crypto pairs",
            ) to 0
            cmd.startsWith("tail") -> out(
                "Oct 17 08:29:58 $name dockerd[812]: time=\"2026-10-17T08:29:58Z\" level=info msg=\"Container api healthy\"",
                "Oct 17 08:30:01 $name CRON[44121]: ($user) CMD (/home/$user/scripts/healthcheck.sh)",
                "Oct 17 08:30:02 $name systemd[1]: Started fx-healthcheck.service.",
            ) to 0
            cmd.startsWith("ls") -> out("CoinePro-FX  backups  logs  scripts") to 0
            cmd.startsWith("echo ") -> out(cmd.removePrefix("echo ").trim('"', '\'')) to 0
            cmd.startsWith("docker compose logs") -> (out("api-1  | INFO:     Application startup complete.", "api-1  | INFO:     10.10.1.4:51022 - \"GET /health HTTP/1.1\" 200 OK") + listOf(true to "api-1  | WARNING:  model drift above 0.12 on EURUSD (daily)")) to 0
            first in setOf("cat", "grep", "systemctl", "docker", "git", "curl", "python", "pytest", "make", "bash", "sh", "journalctl", "nginx", "ps", "top", "htop", "du") ->
                out("(demo) ran on $name as $user; a real server prints its own output here.") to 0
            else -> listOf(true to "bash: $first: command not found") to 127
        }
    }

    // ---------------------------------------------------------------------------------------- sessions --
    private fun newSession(b: JsonObject): JsonObject {
        val id = b.s("server")
        val s = servers.firstOrNull { it.s("id") == id }
        val ref = "S-%04d".format(20 + mine.size)
        mine += ref
        val code = b.s("driver")
        val e = list("/employees").map { it.jsonObject }.firstOrNull { it.s("code") == code }
        val driver = e?.let { actor(it.s("code")!!, it.s("title_fa") + " " + (s?.s("company") ?: ""), it.s("kind")!!) } ?: OWNER
        val session = buildJsonObject {
            put("id", "s-$ref"); put("ref", ref); put("workspace", ""); put("grant", ""); put("runtime", "company_server"); put("server", id); put("company", s?.s("company"))
            put("title", b.s("title")); put("brief", b.s("brief")); put("opened_by", OWNER); put("driver", driver); put("model", "claude-sonnet-5-5"); put("effort", "high")
            put("state", "starting"); put("branch", JsonNull); put("pr_url", JsonNull); putJsonObject("usage") { put("usd", 0.0); put("input_tokens", 0); put("output_tokens", 0) }
            put("created_at", now); put("updated_at", now)
        }
        store["/workshop/sessions/$ref"] = 200 to session
        store["/workshop/sessions"] = 200 to page(listOf<JsonElement>(session) + list("/workshop/sessions"))
        store["/workshop/sessions/$ref/events"] = 200 to page(emptyList())
        val sys = actor("HQ-SYS", "سیستم", "system")
        scripts[ref] = mutableListOf(
            step("state", sys, "Claude Code روی ${s?.s("name")} شروع شد", buildJsonObject { put("state", "working") }),
            step("message", driver, "شروع کردم: ${b.s("title")}. اول وضعیت ریپو و سرویس‌ها را میبینم."),
            step("command", driver, "ریپو تمیز است و روی آخرین commit", buildJsonObject { put("cmd", "git status -sb && git log --oneline -3"); put("exit_code", 0); put("duration_s", 1) }),
            step("command", driver, "همه‌ی سرویس‌ها بالا هستند", buildJsonObject { put("cmd", "docker compose ps"); put("exit_code", 0); put("duration_s", 2) }),
            step("progress", driver, "جای تغییر پیدا شد؛ در حال نوشتن و تست."),
        )
        activity.getOrPut(id.orEmpty()) { mutableListOf() }.add(0, call(driver.s("code")!!, driver.s("display_fa")!!, "server.claude", "Claude Code روی سرور: ${b.s("title")}", null, null, null, 0, session = ref, kind = driver.s("kind")!!))
        return session
    }

    private fun session(ref: String) = store["/workshop/sessions/$ref"]!!.second.jsonObject

    private fun reveal(ref: String, e: JsonObject): JsonObject {
        val key = "/workshop/sessions/$ref/events"
        val items = list(key)
        val ev = JsonObject(e + mapOf("seq" to JsonPrimitive((items.lastOrNull()?.jsonObject?.get("seq")?.jsonPrimitive?.long ?: 0) + 1), "at" to JsonPrimitive(now)))
        store[key] = 200 to page(items + ev)
        val s = session(ref)
        val state = when {
            e.s("type") == "state" -> e["data"]!!.jsonObject.s("state") ?: s.s("state")
            s.s("state") == "starting" -> "working"
            else -> s.s("state")
        }
        val usd = ((s["usage"]!!.jsonObject["usd"]!!.jsonPrimitive.content.toDouble() + 0.05) * 100).let { Math.round(it) / 100.0 }
        val next = JsonObject(s + mapOf("state" to JsonPrimitive(state), "updated_at" to JsonPrimitive(now), "usage" to JsonObject(s["usage"]!!.jsonObject + ("usd" to JsonPrimitive(usd)))))
        store["/workshop/sessions/$ref"] = 200 to next
        store["/workshop/sessions"] = 200 to page(list("/workshop/sessions").map { if (it.jsonObject.s("ref") == ref) next else it })
        return ev
    }

    // ------------------------------------------------------------------------------------------- live --
    /** The stream's server events: what the owner's calls caused, then (well after waking) the agents' calls one by one. */
    fun tick(tick: Int): List<StreamEvent> {
        val out = mutableListOf<StreamEvent>()
        while (true) out += queue.poll() ?: break
        if (!awake || still) return out
        val start = wokeTick ?: tick.also { wokeTick = it }
        if (!sealRaised && tick - start >= 12) { raiseSeal(); while (true) out += queue.poll() ?: break }
        if (tick - start < 40 || (tick - start) % 12 != 0) return out
        val b = BEATS[beat++ % BEATS.size]
        if (b.company in DemoLive.stopped) return out
        val row = call(b.actor, b.actorFa, b.tool, b.summary, b.cmd, 0, b.ms, 0)
        activity.getOrPut(b.server) { mutableListOf() }.add(0, row)
        edit(b.server) { it + ("last_seen_at" to JsonPrimitive(now)) }
        out += event(b.company, "server.call", b.server, mapOf("server" to b.server, "actor" to b.actor, "actor_fa" to b.actorFa, "tool" to b.tool, "summary_fa" to b.summary, "exit_code" to "0", "duration_ms" to b.ms.toString()))
        return out
    }

    private data class Beat(val company: String, val server: String, val actor: String, val actorFa: String, val tool: String, val summary: String, val cmd: String?, val ms: Long)

    private val BEATS = listOf(
        Beat("FX", "srv-fx-1", "FX-TECH-MGR", "مدیر فنی FX", "server.exec", "سلامت API بعد از انتشار: 200", "curl -fsS http://127.0.0.1:8000/health", 120),
        Beat("TY", "srv-ty-1", "TY-GROWTH-01", "تحلیلگر سئوی فنی", "server.read", "خواندن sitemap تولیدشده", "cat /var/www/tradeyar/sitemap.xml", 60),
        Beat("FX", "srv-fx-1", "FX-QUANT-02", "پایشگر سیگنال", "server.exec", "صف celery خالی است", "docker compose exec -T api celery -A src inspect active", 2_100),
        Beat("TY", "srv-ty-1", "TY-TECH-MGR", "مدیر فنی تریدیار", "server.exec", "لاگ خطای nginx در یک ساعت گذشته خالی است", "sudo tail -n 100 /var/log/nginx/error.log", 80),
    )

    // ------------------------------------------------------------------------------------------ store --
    private fun addDecision(d: JsonObject) {
        val ref = d.s("ref")!!
        store["/decisions/$ref"] = 200 to d
        for (k in listOf("/decisions?status=pending", "/decisions?status=all")) store[k] = 200 to page(listOf<JsonElement>(d) + list(k).filter { it.jsonObject.s("ref") != ref })
    }

    private fun edit(id: String, f: (JsonObject) -> Map<String, JsonElement>): JsonObject {
        val i = servers.indexOfFirst { it.s("id") == id }
        if (i < 0) return JsonObject(emptyMap())
        servers[i] = JsonObject(f(servers[i]))
        return servers[i]
    }

    private fun server(id: String, co: String, name: String, ip: String, user: String, key: String, state: String, seen: String?, mapAt: String?) = buildJsonObject {
        put("id", id); put("company", co); put("name", name); put("origin", "attached"); put("private_ip", ip); put("user", user); put("host_key_sha256", key)
        put("state", state); put("last_seen_at", seen?.let(::JsonPrimitive) ?: JsonNull); put("map_at", mapAt?.let(::JsonPrimitive) ?: JsonNull)
    }

    private fun call(code: String, fa: String, tool: String, summary: String, cmd: String?, exit: Int?, ms: Long?, minutes: Long, session: String? = null, kind: String = "agent", state: String? = null, transcript: Boolean = false) = buildJsonObject {
        val n = seq++
        put("id", "call-$n"); put("at", at(minutes)); put("actor", actor(code, fa, if (code == "owner") "owner" else kind)); put("tool", tool); put("summary_fa", summary)
        put("cmd_masked", cmd?.let(::JsonPrimitive) ?: JsonNull); put("exit_code", exit?.let(::JsonPrimitive) ?: JsonNull); put("duration_ms", ms?.let(::JsonPrimitive) ?: JsonNull)
        put("session_ref", session?.let(::JsonPrimitive) ?: JsonNull)
        put("transcript_url", if (transcript || cmd != null) JsonPrimitive("/api/v1/audit/transcripts/call-$n") else JsonNull)
        if (state != null) put("state", state)
    }

    private fun ev(seq: Long, minutes: Long, type: String, actor: JsonObject, summary: String, data: JsonObject = JsonObject(emptyMap())) = buildJsonObject {
        put("seq", seq); put("at", at(minutes)); put("type", type); put("actor", actor); put("summary_fa", summary); put("data", data)
    }

    private fun step(type: String, actor: JsonElement, summary: String, data: JsonObject = JsonObject(emptyMap())) =
        buildJsonObject { put("type", type); put("actor", actor); put("summary_fa", summary); put("data", data) }

    private fun policyJson() = buildJsonObject { put("seal_required", buildJsonArray { policy.forEach { add(JsonPrimitive(it)) } }) }

    private fun event(company: String, type: String, ref: String?, data: Map<String, String>) =
        StreamEvent("demo-srv-${seq++}", type, now, company, ref, JsonObject(data.mapValues { JsonPrimitive(it.value) }))

    private fun json(req: Request, status: Int, body: JsonElement): Response =
        Response.Builder().request(req).protocol(Protocol.HTTP_1_1).code(status).message("demo").body(body.toString().toResponseBody("application/json".toMediaType())).build()

    private fun list(key: String): List<JsonElement> = store[key]?.second?.let { (it as? JsonObject)?.get("items") ?: it }?.jsonArray.orEmpty()
    private fun page(items: List<JsonElement>) = buildJsonObject { put("items", JsonArray(items)); put("next_cursor", JsonNull) }
    private fun problem(status: Int, code: String, fa: String) = buildJsonObject { put("code", code); put("message_fa", fa); put("status", status); put("title", code); put("type", "about:blank") }
    private fun JsonObject.s(k: String): String? = (this[k] as? JsonPrimitive)?.takeIf { it !is JsonNull }?.contentOrNull

    /** A transcript the activity links to: the call's command and what it printed, as the hub stores it. */
    private fun transcript(id: String): String? = activity.values.flatten().firstOrNull { it.s("id") == id }?.let { r ->
        "$ ${r.s("cmd_masked").orEmpty()}\n" + when {
            r.s("cmd_masked").orEmpty().contains("pytest") -> "........................................................ [ 61%]\n...................................                      [100%]\n91 passed in 48.71s\n"
            else -> "(exit ${r.s("exit_code") ?: "—"})\n"
        }
    }

    private companion object {
        val OWNER = buildJsonObject { put("kind", "owner"); put("code", "owner"); put("display_fa", "مدیر کل") }
        fun actor(code: String, fa: String, kind: String) = buildJsonObject { put("kind", kind); put("code", code); put("display_fa", fa) }

        const val GIB = 1024L * 1024 * 1024

        fun fxMap(at: String) = buildJsonObject {
            put("taken_at", at); put("hostname", "coinepro-fx")
            putJsonObject("os") { put("name", "Ubuntu"); put("version", "24.04.1 LTS"); put("kernel", "6.8.0-47-generic") }
            put("cpus", 8); put("uptime_s", 1_900_800); putJsonArray("load") { add(JsonPrimitive(0.84)); add(JsonPrimitive(0.92)); add(JsonPrimitive(0.88)) }
            putJsonArray("disks") { add(buildJsonObject { put("mount", "/"); put("total_bytes", 150 * GIB); put("used_bytes", 62 * GIB) }) }
            putJsonObject("memory") { put("total_bytes", 15 * GIB + GIB / 2); put("used_bytes", 11 * GIB + GIB / 5) }
            putJsonObject("swap") { put("total_bytes", 8 * GIB); put("used_bytes", GIB + GIB / 10) }
            putJsonArray("containers") {
                for ((n, img, st) in listOf(
                    Triple("coinepro-fx-api-1", "coinepro-fx-api:a41c09e", "Up 3 minutes (healthy)"),
                    Triple("coinepro-fx-celery-worker-1", "coinepro-fx-api:a41c09e", "Up 3 minutes"),
                    Triple("coinepro-fx-celery-beat-1", "coinepro-fx-api:a41c09e", "Up 3 minutes"),
                    Triple("coinepro-fx-timescaledb-1", "timescale/timescaledb:2.17.2-pg16", "Up 22 days (healthy)"),
                    Triple("coinepro-fx-redis-1", "redis:7.4-alpine", "Up 22 days (healthy)"),
                    Triple("coinepro-fx-bot-1", "coinepro-fx-bot:a41c09e", "Up 3 minutes"),
                    Triple("coinepro-fx-website-1", "coinepro-fx-website:7d20f13", "Up 2 days"),
                    Triple("coinepro-fx-admin-1", "coinepro-fx-admin:7d20f13", "Up 2 days"),
                    Triple("coinepro-fx-n8n-1", "n8nio/n8n:1.68.0", "Up 9 days"),
                    Triple("coinepro-fx-backtest-1", "coinepro-fx-api:c9b81aa", "Exited (0) 6 hours ago"),
                )) add(buildJsonObject { put("name", n); put("image", img); put("state", if (st.startsWith("Up")) "running" else "exited"); put("status", st); put("compose_project", "coinepro-fx") })
            }
            putJsonArray("compose") { add(buildJsonObject { put("project", "coinepro-fx"); put("dir", "/home/forex/CoinePro-FX"); put("services", 10); put("running", 9) }) }
            putJsonObject("systemd") {
                putJsonArray("units") {
                    for ((n, st) in listOf("docker.service" to "active", "ssh.service" to "active", "caddy.service" to "active", "unattended-upgrades.service" to "active", "fx-healthcheck.service" to "inactive"))
                        add(buildJsonObject { put("name", n); put("state", st) })
                }
                putJsonArray("timers") {
                    add(buildJsonObject { put("unit", "fx-backup.timer"); put("next", HqClock.now().plus(95, ChronoUnit.MINUTES).toString()); put("activates", "fx-backup.service") })
                    add(buildJsonObject { put("unit", "certbot.timer"); put("next", HqClock.now().plus(210, ChronoUnit.MINUTES).toString()); put("activates", "certbot.service") })
                    add(buildJsonObject { put("unit", "apt-daily-upgrade.timer"); put("next", HqClock.now().plus(21, ChronoUnit.HOURS).toString()); put("activates", "apt-daily-upgrade.service") })
                }
            }
            putJsonArray("cron") {
                add(buildJsonObject { put("schedule", "*/5 * * * *"); put("command", "/home/forex/CoinePro-FX/scripts/healthcheck.sh"); put("user", "forex") })
                add(buildJsonObject { put("schedule", "30 2 * * *"); put("command", "cd /home/forex/CoinePro-FX && bash scripts/backup.sh"); put("user", "forex") })
            }
            putJsonArray("ports") {
                for ((p, a, proc) in listOf(Triple(22, "10.10.1.2", "sshd"), Triple(80, "0.0.0.0", "caddy"), Triple(443, "0.0.0.0", "caddy"), Triple(8000, "127.0.0.1", "docker-proxy"), Triple(5432, "127.0.0.1", "docker-proxy"), Triple(6379, "127.0.0.1", "docker-proxy"), Triple(5678, "127.0.0.1", "n8n")))
                    add(buildJsonObject { put("port", p); put("proto", "tcp"); put("address", a); put("process", proc) })
            }
            putJsonArray("repos") {
                add(buildJsonObject { put("path", "/home/forex/CoinePro-FX"); put("remote", "git@github.com:behnamjalalico/CoineProFx.git"); put("branch", "claude/wizardly-edison-zyWyW"); put("head", "a41c09e"); put("dirty", false) })
            }
            putJsonObject("n8n") {
                putJsonArray("workflows") {
                    add(buildJsonObject { put("name", "گزارش روزانه‌ی سیگنال‌ها به تلگرام"); put("active", true); put("trigger", "cron 08:00") })
                    add(buildJsonObject { put("name", "هشدار افت دقت مدل"); put("active", true); put("trigger", "webhook") })
                    add(buildJsonObject { put("name", "بک‌تست هفتگی"); put("active", false); put("trigger", "cron Fri 22:00") })
                }
            }
            putJsonArray("automations") {
                add(buildJsonObject { put("kind", "celery-beat"); put("name", "به‌روزرسانی کندل‌ها"); put("active", true); put("detail", "refresh_candles · every 1m") })
                add(buildJsonObject { put("kind", "celery-beat"); put("name", "پایش drift مدل‌ها"); put("active", true); put("detail", "drift_check · every 1h") })
            }
            putJsonArray("sites") {
                add(buildJsonObject { put("domain", "coineprofx.com"); put("upstream", "website:80"); put("tls", true); put("server", "caddy") })
                add(buildJsonObject { put("domain", "api.coineprofx.com"); put("upstream", "api:8000"); put("tls", true); put("server", "caddy") })
                add(buildJsonObject { put("domain", "admin.coineprofx.com"); put("upstream", "admin:80"); put("tls", true); put("server", "caddy") })
            }
        }

        /** TradeYar's map, written the way `df -h` and `docker compose ls` print (sizes as text, `running(4)`), as a mapper may send it. */
        fun tyMap(at: String) = buildJsonObject {
            put("taken_at", at); put("hostname", "tradeyar-web"); put("os", "Ubuntu 24.04.1 LTS"); put("kernel", "6.8.0-45-generic"); put("cpus", 8); put("uptime_s", 4_406_400)
            putJsonObject("disk") { put("mount", "/"); put("size", "150G"); put("used", "97G") }
            putJsonObject("memory") { put("total", "15Gi"); put("available", "5.1Gi") }
            putJsonArray("containers") {
                for ((n, st) in listOf("tradeyar-app-1" to "Up 5 days", "tradeyar-worker-1" to "Up 5 days", "tradeyar-postgres-1" to "Up 41 days", "tradeyar-redis-1" to "Up 41 days"))
                    add(buildJsonObject { put("names", n); put("image", n.removePrefix("tradeyar-").removeSuffix("-1")); put("status", st); putJsonObject("labels") { put("com.docker.compose.project", "tradeyar") } })
            }
            putJsonArray("compose") { add(buildJsonObject { put("name", "tradeyar"); put("config_files", "/home/tradeyar/TradeYar/docker-compose.yml"); put("status", "running(4)"); put("services", 4) }) }
            putJsonArray("timers") { add(buildJsonObject { put("unit", "ty-sitemap.timer"); put("next", HqClock.now().plus(50, ChronoUnit.MINUTES).toString()); put("activates", "ty-sitemap.service") }) }
            putJsonArray("cron") { add(JsonPrimitive("0 3 * * * /home/tradeyar/TradeYar/scripts/backup.sh")) }
            putJsonArray("listening") { add(JsonPrimitive("0.0.0.0:443")); add(JsonPrimitive("0.0.0.0:80")); add(JsonPrimitive("10.10.1.3:22")); add(JsonPrimitive("127.0.0.1:3000")); add(JsonPrimitive("127.0.0.1:5432")) }
            putJsonArray("repos") { add(buildJsonObject { put("path", "/home/tradeyar/TradeYar"); putJsonArray("remotes") { add(buildJsonObject { put("name", "origin"); put("url", "git@github.com:behnamjalalico/TradeYar.git") }) }; put("branch", "main"); put("commit", "5be0a7d91c3e") }) }
            putJsonArray("sites") {
                add(buildJsonObject { put("server_name", "tradeyar.com"); put("proxy_pass", "http://127.0.0.1:3000"); put("https", true); put("via", "nginx") })
                add(buildJsonObject { put("server_name", "www.tradeyar.com"); put("proxy_pass", "301 → tradeyar.com"); put("https", true); put("via", "nginx") })
            }
        }

        fun smallMap(at: String) = buildJsonObject {
            put("taken_at", at); put("os", "Ubuntu 24.04.1 LTS"); put("cpus", 4)
            putJsonObject("disk") { put("total_bytes", 80 * GIB); put("used_bytes", 12 * GIB) }
            putJsonObject("memory") { put("total_bytes", 8 * GIB); put("used_bytes", 2 * GIB) }
        }
    }
}
