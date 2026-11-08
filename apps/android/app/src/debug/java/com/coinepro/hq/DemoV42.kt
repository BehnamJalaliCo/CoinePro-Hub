package com.coinepro.hq

import com.coinepro.hq.core.format.HqClock
import com.coinepro.hq.core.net.StreamEvent
import java.time.Instant
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
 * Debug builds only: contract §42 ⟨1.24⟩, the holding live. `GET /live/summary` from the demo's own state (people at work by company, the
 * open sessions' badges, the cards waiting for the seal, the servers, today's tokens and dollars, the kill switches), and a script on the
 * stream that moves it, so every live view shows live behaviour: an order of the owner to TradeYar, a cross-company request (FX asks
 * TradeYar, which accepts and delivers back through the hub), a read of FX's data, a publish, jobs on TradeYar's server, FX's server
 * dropping (its runner stopped) and coming back, people thinking, working, stuck and done, and a token tick of each busy company every few
 * seconds. A company the owner stopped stays quiet (Pro-Chart is, in the demo). The script starts at [START], after the beats the
 * screenshots of the older screens are drawn with, so those stay as they were; it loops every [LOOP] ticks.
 */
internal class V42Demo(private val store: MutableMap<String, Pair<Int, JsonElement>>) {
    private class Co(val code: String, val fa: String, val total: Int, val baseWorking: Int, var spend: Double, val budget: Double, var lastAt: Instant)

    private val now0 = HqClock.now()
    private val cos = linkedMapOf(
        "TY" to Co("TY", "تریدیار", 12, 2, 1.12, 1.50, now0.minusSeconds(35)),
        "FX" to Co("FX", "کوینه‌پرو FX", 9, 2, 1.38, 1.50, now0.minusSeconds(80)),
        "PC" to Co("PC", "پرو-چارت", 7, 0, 0.44, 1.00, now0.minusSeconds(60 * 47)),
    )
    /** The people the script moves, by code: (company, state). */
    private val people = linkedMapOf(
        "TY-GROWTH-01" to ("TY" to "idle"),
        "TY-TECH-MGR" to ("TY" to "thinking"),
        "FX-QUANT-02" to ("FX" to "working"),
        "FX-SUPPORT-01" to ("FX" to "waiting"),
    )
    /** The servers of the network map (DemoServers' runners) and whether each is online now. */
    private val servers = linkedMapOf("srv-fx-1" to ("FX" to true), "srv-ty-1" to ("TY" to true), "srv-pc-1" to ("PC" to true), "srv-ig-1" to ("IG" to true))
    private var today = 188_100L
    private var effective = 166_000L
    private var usd = 2.94
    private val budget = 4.00
    private var urgent = 0
    private var seq = 0

    init { DemoLive.live = this }

    // -------------------------------------------------------------- the seed --
    @Synchronized
    fun handle(method: String, path: String): Pair<Int, JsonElement>? {
        if (method != "GET" || path != "/live/summary") return null
        return 200 to summary()
    }

    private fun working(code: String): Int = (cos[code]?.baseWorking ?: 0) + people.values.count { it.first == code && it.second in BUSY }

    private fun summary(): JsonObject {
        val badges = DemoLive.sessions?.liveBadges().orEmpty()
        val locked = DemoLive.stopped
        val decisions = (store["/decisions?status=all"]?.second as? JsonObject)?.get("items")?.jsonArray.orEmpty()
        val approvals = decisions.count { (it.jsonObject["status"] as? JsonPrimitive)?.contentOrNull == "pending" }
        return buildJsonObject {
            put("seq", JsonNull)
            put("at", HqClock.now().toString())
            put("people", buildJsonObject {
                put("working", cos.keys.sumOf { working(it) } - people.values.count { it.second == "thinking" })
                put("thinking", people.values.count { it.second == "thinking" })
                put("waiting", 1 + people.values.count { it.second == "waiting" })
                put("stuck", people.values.count { it.second == "stuck" })
                put("total", cos.values.sumOf { it.total })
            })
            put("sessions", buildJsonObject {
                for ((k, b) in listOf("moving" to "moving", "your_turn" to "your_turn", "stuck" to "stuck", "ready" to "ready")) put(k, badges.count { it.first == b })
            })
            put("approvals", approvals)
            put("urgent_unread", urgent)
            put("servers", buildJsonObject {
                put("online", servers.values.count { it.second })
                put("offline", servers.values.count { !it.second })
                put("total", servers.size)
            })
            put("tokens", buildJsonObject {
                put("today", today); put("effective_today", effective); put("per_min", 7_600)
                put("equiv_usd_today", String.format(java.util.Locale.US, "%.2f", usd)); put("budget_usd", String.format(java.util.Locale.US, "%.2f", budget))
            })
            put("control", buildJsonObject {
                put("holding", "HQ" in locked)
                put("companies_locked", JsonArray(locked.filter { it != "HQ" }.map(::JsonPrimitive)))
            })
            put("companies", JsonArray(cos.values.map { c ->
                val mine = servers.values.filter { it.first == c.code }
                buildJsonObject {
                    put("code", c.code); put("name_fa", c.fa)
                    put("working", if (c.code in locked) 0 else working(c.code)); put("total", c.total)
                    put("sessions_open", badges.count { it.second == c.code })
                    put("servers_online", mine.count { it.second }); put("servers_total", mine.size)
                    put("spend_today_usd", String.format(java.util.Locale.US, "%.2f", c.spend))
                    put("last_event_at", c.lastAt.toString())
                    put("state", when {
                        c.code in locked || "HQ" in locked -> "locked"
                        people.values.any { it.first == c.code && it.second == "stuck" } -> "stuck"
                        working(c.code) > 0 -> "busy"
                        else -> "ok"
                    })
                }
            }))
        }
    }

    // -------------------------------------------------------------- the script --
    /** The stream's beats of the live views at [tick] (about 600 ms each). */
    @Synchronized
    fun tick(tick: Int): List<StreamEvent> {
        if (tick < START) return emptyList()
        val t = (tick - START) % LOOP
        val out = mutableListOf<StreamEvent>()
        fun quiet(vararg codes: String) = codes.any { it in DemoLive.stopped || "HQ" in DemoLive.stopped }
        when (t) {
            0 -> if (!quiet("TY")) out += person("TY-GROWTH-01", "working", work = "W-000102")
            1 -> out += llmTick("TY", calls = 3, inFlight = 2, input = 4_200, output = 900, cacheRead = 1_600, cacheWrite = 300, thinking = 600, usd = 0.11)
            2 -> if (!quiet("TY")) out += flow("hub", "TY", "order", "W-000140", "یک ریلز آموزشی طلا برای امروز")
            4 -> if (!quiet("FX", "TY")) out += flow("FX", "TY", "request", "W-000141", "انتشار سیگنال طلا در کانال تریدیار")
            5 -> out += llmTick("FX", calls = 2, inFlight = 1, input = 2_800, output = 700, cacheRead = 900, cacheWrite = 0, thinking = 400, usd = 0.07)
            6 -> if (!quiet("TY")) out += job("srv-ty-1", "TY", "running", "خواندن sitemap تولیدشده")
            7 -> out += serverState("srv-fx-1", "FX", "offline", "online", "runner_stopped", "runner روی سرور ایستاده؛ خود سرور روشن است", openJobs = 2)
            8 -> if (!quiet("FX")) out += person("FX-SUPPORT-01", "stuck", stuck = "کلید تلگرام پشتیبانی منقضی شده؛ تا تازه نشود جواب نمیدهد")
            9 -> if (!quiet("TY")) out += job("srv-ty-1", "TY", "done", "خواندن sitemap تولیدشده")
            11 -> if (!quiet("FX", "TY")) out += flow("TY", "FX", "accept", "W-000141", null)
            12 -> out += llmTick("TY", calls = 4, inFlight = 1, input = 3_900, output = 1_100, cacheRead = 2_000, cacheWrite = 200, thinking = 900, usd = 0.12)
            14 -> if (!quiet("FX", "TY")) out += flow("FX", "TY", "read", "W-000141", "سیگنال‌های امروز کوینه‌پرو FX")
            16 -> if (!quiet("TY")) out += person("TY-TECH-MGR", "working", work = "W-000141")
            18 -> if (!quiet("FX", "TY")) out += flow("TY", "FX", "deliver", "W-000141", "سیگنال طلا در کانال منتشر شد")
            20 -> if (!quiet("TY")) out += person("TY-GROWTH-01", "done")
            22 -> out += serverState("srv-fx-1", "FX", "online", "offline", null, null, openJobs = 0)
            24 -> out += networkLink("srv-pc-1", "srv-fx-1", 22, ok = false, error = "پورت بسته است")
            26 -> out += llmTick("FX", calls = 1, inFlight = 0, input = 1_500, output = 400, cacheRead = 600, cacheWrite = 0, thinking = 0, usd = 0.04)
            28 -> if (!quiet("TY")) out += flow("TY", "outside", "publish", "W-000140", "ریلز آموزشی طلا")
            30 -> if (!quiet("FX")) out += person("FX-SUPPORT-01", "working", work = "W-000143")
            34 -> if (!quiet("TY")) out += person("TY-GROWTH-01", "idle")
            36 -> if (!quiet("TY")) out += person("TY-TECH-MGR", "thinking")
            40 -> if (!quiet("FX")) out += person("FX-SUPPORT-01", "waiting")
        }
        return out
    }

    private fun event(company: String?, type: String, ref: String?, data: JsonObject): StreamEvent {
        company?.let { code -> cos[code]?.lastAt = HqClock.now() }
        return StreamEvent("demo-lv-${++seq}", type, HqClock.now().toString(), company, ref, data)
    }

    private fun person(id: String, state: String, work: String? = null, stuck: String? = null): StreamEvent {
        val co = people[id]?.first ?: id.substringBefore('-')
        people[id] = co to state
        return event(co, "employee.state", id, buildJsonObject {
            put("employee", id); put("company", co); put("department", "ops"); put("state", state); put("since", HqClock.now().toString())
            put("work_ref", work?.let(::JsonPrimitive) ?: JsonNull); put("root_ref", JsonNull); put("stuck_fa", stuck?.let(::JsonPrimitive) ?: JsonNull)
        })
    }

    private fun flow(from: String, to: String, kind: String, ref: String, label: String?): StreamEvent =
        event(listOf(from, to).firstOrNull { it in cos }, "holding.flow", ref, buildJsonObject {
            put("from", from); put("to", to); put("kind", kind); put("via", "hub"); put("ref", ref); put("root_ref", JsonNull)
            put("label_fa", label?.let(::JsonPrimitive) ?: JsonNull)
        })

    private fun job(server: String, company: String, state: String, summary: String): StreamEvent = event(company, "server.call", server, buildJsonObject {
        put("server", server); put("actor", "$company-TECH-MGR"); put("actor_fa", "مدیر فنی"); put("tool", "server.read"); put("summary_fa", summary)
        put("state", state)
        if (state != "running") { put("exit_code", if (state == "done") "0" else "1"); put("duration_ms", "1800") }
    })

    private fun serverState(server: String, company: String, state: String, prev: String, reason: String?, reasonFa: String?, openJobs: Int): StreamEvent {
        servers[server] = company to (state == "online")
        return event(company, "server.state", server, buildJsonObject {
            put("server", server); put("state", state); put("prev_state", prev); put("since", HqClock.now().toString())
            put("reason", reason?.let(::JsonPrimitive) ?: JsonNull); put("reason_fa", reasonFa?.let(::JsonPrimitive) ?: JsonNull)
            put("via", "private"); put("hub_rtt_ms", if (state == "online") JsonPrimitive(2.8) else JsonNull); put("open_jobs", openJobs)
        })
    }

    private fun networkLink(from: String, to: String, port: Int, ok: Boolean, error: String?): StreamEvent = event(null, "network.link", from, buildJsonObject {
        put("from", from); put("to", to); put("port", port); put("ok", ok); put("ms", JsonNull)
        put("error_fa", error?.let(::JsonPrimitive) ?: JsonNull); put("since", HqClock.now().toString()); put("last_ok_at", JsonNull)
    })

    private fun llmTick(co: String, calls: Int, inFlight: Int, input: Long, output: Long, cacheRead: Long, cacheWrite: Long, thinking: Long, usd: Double): List<StreamEvent> {
        if (co in DemoLive.stopped || "HQ" in DemoLive.stopped) return emptyList()
        val c = cos[co] ?: return emptyList()
        val window = input + output + cacheRead + cacheWrite + thinking
        today += window
        effective += window - cacheRead
        this.usd += usd
        c.spend += usd
        return listOf(event(co, "llm.tick", null, buildJsonObject {
            put("company", co); put("window_s", 5); put("calls", calls); put("in_flight", inFlight)
            put("tokens", buildJsonObject { put("input", input); put("output", output); put("cache_read", cacheRead); put("cache_write", cacheWrite); put("thinking", thinking) })
            put("equiv_usd", String.format(java.util.Locale.US, "%.4f", usd))
            put("day", buildJsonObject {
                put("tokens", JsonNull); put("effective_tokens", JsonNull)
                put("equiv_usd", String.format(java.util.Locale.US, "%.2f", c.spend)); put("budget_usd", String.format(java.util.Locale.US, "%.2f", c.budget))
                put("pct", Math.round(c.spend / c.budget * 1000) / 10.0)
            })
        }))
    }

    companion object {
        /** After the beats the older screens' screenshots are drawn with (ScreensTest plays six). */
        const val START = 8
        const val LOOP = 48
        private val BUSY = setOf("working", "thinking")
    }
}
