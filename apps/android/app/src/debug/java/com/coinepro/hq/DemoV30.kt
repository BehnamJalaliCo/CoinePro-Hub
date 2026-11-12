package com.coinepro.hq

import com.coinepro.hq.core.format.HqClock
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.temporal.ChronoUnit
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull

/**
 * Debug builds only: contract §30 ⟨1.12⟩, production lines. Deterministic (every time from [HqClock]), so the screenshots are the same on
 * any machine.
 *
 * - **Templates (§30.6):** the Instagram reel (twelve steps), the Telegram post and the site article.
 * - **Lines:** `LN-0001` TradeYar's reel on Saturdays and Tuesdays (on, draft mode with four good runs, its newest run waiting for the
 *   owner's seal), `LN-0002` FX's Telegram post every day (automatic), `LN-0003` Pro-Chart's article (just made, a draft).
 * - **Runs:** `RN-000003` waiting at its publish step with an output of every kind (text, audio, a film, a cover, data tables),
 *   `RN-000002` published, `RN-000001` a dry run that failed at the voice; `RN-000004` and `RN-000005` for FX.
 * - **Library:** cover folders, a speaker, prompts and a pattern, per company and for the holding; the speakers AI Studio offers.
 * - **Calendar:** every line's schedule over any week asked, past ones as ran.
 */
internal class V30Demo {
    private val now = HqClock.now()
    private val tehran = ZoneId.of("Asia/Tehran")
    private fun at(minAgo: Long): String = now.minus(minAgo, ChronoUnit.MINUTES).toString()
    private fun atSec(minAgo: Long, plusS: Long): String = now.minus(minAgo, ChronoUnit.MINUTES).plusSeconds(plusS).toString()

    private val lines = linkedMapOf<String, JsonObject>()
    private val versions = linkedMapOf<String, MutableList<JsonObject>>()
    private val runs = linkedMapOf<String, JsonObject>()
    private val assets = mutableListOf<JsonObject>()
    private var lineSeq = 3
    private var runSeq = 5
    private var assetSeq = 6

    private val templates: List<JsonObject> = listOf(
        template("instagram_reel", "ریل آموزشی اینستاگرام", "instagram_reel", reelSteps(),
            "یک ریلز عمودی ۳۰ ثانیه‌ای با صدا، کاور، کپشن و هشتگ؛ بعد از انتشار، استوری همان روز."),
        template("telegram_post", "پست کانال تلگرام", "telegram_post", telegramSteps(), "یک پست کوتاه با متن و تصویر برای کانال تلگرام."),
        template("site_article", "مقاله‌ی سایت", "site_article", articleSteps(), "یک مقاله‌ی کامل با تیتر، توضیح متا و تصویر شاخص."),
    )

    init {
        val reel = reelSteps(speaker = "Kore", folder = "AS-0001")
        lines["LN-0001"] = line("LN-0001", "TY", "instagram_reel", "instagram_reel", jo("kind" to "instagram", "subject" to "tradeyar.official"), "ریلز طلای تریدیار",
            "FREQ=WEEKLY;BYDAY=SA,TU;BYHOUR=18;BYMINUTE=0", "on", "draft", 4, 3, reel, listOf("AS-0001", "AS-0004"), 3 * 24 * 60L, jo("ref" to "RN-000003", "state" to "waiting", "at" to at(50)))
        lines["LN-0002"] = line("LN-0002", "FX", "telegram_post", "telegram_post", jo("kind" to "telegram", "subject" to "coinepro_fx"), "پست روزانه‌ی کانال کوینه‌پرو",
            "FREQ=DAILY;BYHOUR=9;BYMINUTE=0", "on", "auto", 9, 5, telegramSteps(), listOf("AS-0002"), 9 * 24 * 60L, jo("ref" to "RN-000005", "state" to "done", "at" to at(1400)))
        lines["LN-0003"] = line("LN-0003", "PC", "site_article", "site_article", jo("kind" to "site", "subject" to "pro-chart.example"), "مقاله‌ی هفتگی پرو-چارت",
            null, "draft", "draft", 0, 1, articleSteps(), emptyList(), 60L, null)
        for ((ref, l) in lines) versions[ref] = mutableListOf(snapshot(l, "ساخته شد از قالب", "مدیر کل", l.str("created_at")))
        // LN-0001 has a history: two edits.
        val l1 = lines.getValue("LN-0001")
        versions.getValue("LN-0001").add(0, snapshot(l1.with("version" to 2), "دستور فیلمنامه کوتاه‌تر شد", "مدیر کل", at(2 * 24 * 60)))
        versions.getValue("LN-0001").add(0, snapshot(l1, "گوینده عوض شد", "مدیر کل", at(24 * 60)))

        runs["RN-000003"] = waitingRun()
        runs["RN-000002"] = publishedRun()
        runs["RN-000001"] = failedRun()
        runs["RN-000004"] = telegramRun("RN-000004", 1400 + 24 * 60, "done")
        runs["RN-000005"] = telegramRun("RN-000005", 1400, "done")

        assets += asset("AS-0001", "TY", "cover_folder", "کاورهای طلای تریدیار", jo(), listOf("/demo/fx-reel-levels-poster.webp", "/demo/fx-reel-resist-poster.webp", "/demo/ty-story-stoploss-poster.webp"), 20 * 24 * 60)
        assets += asset("AS-0002", "FX", "cover_folder", "کاورهای کانال کوینه‌پرو", jo(), listOf("/demo/fx-reel-resist-poster.webp", "/demo/pc-landing-redesign.webp"), 18 * 24 * 60)
        assets += asset("AS-0003", null, "voice", "گوینده‌ی خبر، آرام", jo("voice" to "Kore", "style" to "آرام و مطمئن، مثل گوینده‌ی خبر"), listOf("/demo/voice/piper-amir-numbers.m4a"), 30 * 24 * 60)
        assets += asset("AS-0004", null, "prompt", "قاعده‌ی منبع برای هر عدد", jo("text" to "هر عدد در متن باید منبع داشته باشد؛ اگر منبع نبود، عدد را ننویس و بنویس «نیاز به بررسی». از وعده‌ی سود و واژه‌ی «تضمین» پرهیز کن."), emptyList(), 25 * 24 * 60)
        assets += asset("AS-0005", "TY", "pattern", "طراحی ریلز آموزشی طلا", jo("query" to "ریلز آموزشی طلا"), listOf("/demo/pc-landing-redesign.webp", "/demo/ty-story-stoploss-poster.webp"), 12 * 24 * 60)
    }

    // -------------------------------------------------------------- routes --
    /** The §30 routes; null for everything else (the rest of the demo answers it). */
    @Synchronized
    fun handle(method: String, path: String, query: Map<String, String?>, body: JsonObject?): Pair<Int, JsonElement>? {
        if (path == "/line-templates" && method == "GET") return 200 to ja(templates)
        Regex("^/line-templates/([^/]+)$").find(path)?.let { m ->
            return templates.firstOrNull { it.str("key") == m.groupValues[1] }?.let { 200 to it } ?: (404 to problem(404, "not_found", "این قالب پیدا نشد."))
        }
        // Lines of a company, and a new one from a template.
        Regex("^/companies/([^/]+)/lines$").find(path)?.let { m ->
            val co = m.groupValues[1]
            return when (method) {
                "GET" -> 200 to ja(lines.values.filter { it.str("company") == co }.map(::listed))
                "POST" -> {
                    val t = templates.firstOrNull { it.str("key") == body?.str("template") } ?: return 422 to problem(422, "validation_failed", "قالب پیدا نشد.")
                    val ref = "LN-%04d".format(++lineSeq)
                    val l = line(ref, co, t.str("key")!!, t.str("platform")!!, (body?.get("channel") as? JsonObject) ?: jo("kind" to "", "subject" to ""), body?.str("title_fa") ?: t.str("title_fa")!!,
                        null, "draft", "draft", 0, 1, t.arr("steps"), emptyList(), 0L, null)
                    lines[ref] = l
                    versions[ref] = mutableListOf(snapshot(l, "ساخته شد از قالب", "مدیر کل", l.str("created_at")))
                    201 to l
                }
                else -> null
            }
        }
        Regex("^/lines/(LN-\\d+)$").find(path)?.let { m ->
            val ref = m.groupValues[1]
            val l = lines[ref] ?: return 404 to problem(404, "not_found", "این خط پیدا نشد.")
            return when (method) {
                "GET" -> 200 to listed(l)
                "PUT" -> {
                    var n = l
                    for (k in listOf("title_fa", "schedule", "steps", "caps", "library")) if (body != null && k in body) n = n.with(k to body[k])
                    n = n.with("version" to l.int("version") + 1, "updated_at" to HqClock.now().toString())
                    lines[ref] = n
                    versions.getValue(ref).add(0, snapshot(n, body?.str("note_fa") ?: "ویرایش از اپ", "مدیر کل", HqClock.now().toString()))
                    200 to listed(n)
                }
                else -> null
            }
        }
        Regex("^/lines/(LN-\\d+)/(state|mode|versions|revert|copy|runs)$").find(path)?.let { m ->
            val ref = m.groupValues[1]
            val l = lines[ref] ?: return 404 to problem(404, "not_found", "این خط پیدا نشد.")
            when (m.groupValues[2]) {
                "state" -> if (method == "POST") { lines[ref] = l.with("state" to (body?.str("state") ?: "paused")); return 200 to listed(lines.getValue(ref)) }
                "mode" -> if (method == "POST") { lines[ref] = l.with("mode" to (body?.str("mode") ?: "draft")); return 200 to listed(lines.getValue(ref)) }
                "versions" -> if (method == "GET") return 200 to ja(versions[ref].orEmpty())
                "revert" -> if (method == "POST") {
                    val v = versions[ref].orEmpty().firstOrNull { it.int("version") == (body?.get("version") as? JsonPrimitive)?.contentOrNull?.toIntOrNull() }
                    val old = v?.get("body") as? JsonObject ?: return 404 to problem(404, "not_found", "این نسخه پیدا نشد.")
                    val n = old.with("version" to l.int("version") + 1, "updated_at" to HqClock.now().toString())
                    lines[ref] = n
                    versions.getValue(ref).add(0, snapshot(n, "برگشت به نسخه‌ی ${v.int("version")}", "مدیر کل", HqClock.now().toString()))
                    return 200 to listed(n)
                }
                "copy" -> if (method == "POST") {
                    val co = body?.str("company") ?: return 422 to problem(422, "validation_failed", "شرکت را بگو.")
                    val nref = "LN-%04d".format(++lineSeq)
                    val n = l.with("ref" to nref, "company" to co, "state" to "draft", "mode" to "draft", "good_runs" to 0, "version" to 1, "created_at" to HqClock.now().toString(), "updated_at" to HqClock.now().toString(), "next_at" to null, "last_run" to null)
                    lines[nref] = n
                    versions[nref] = mutableListOf(snapshot(n, "کپی از $ref", "مدیر کل", HqClock.now().toString()))
                    return 201 to n
                }
                "runs" -> when (method) {
                    "GET" -> return 200 to ja(runsOf(ref, (query["limit"] ?: "30").toIntOrNull() ?: 30))
                    "POST" -> {
                        val dry = (body?.get("dry") as? JsonPrimitive)?.contentOrNull == "true"
                        val from = body?.str("from_step")
                        val id = "RN-%06d".format(++runSeq)
                        val steps = l.arr("steps").filter { it["enabled"]?.let { e -> (e as? JsonPrimitive)?.contentOrNull != "false" } != false }
                        val r = jo(
                            "ref" to id, "line" to ref, "line_version" to l.int("version"), "trigger" to (if (dry) "test" else "owner"), "dry" to dry, "state" to "running", "at" to HqClock.now().toString(),
                            "ended_at" to null, "steps" to ja(steps.mapIndexed { i, s -> pendingStep(s, if (i == 0 || (from != null && s.str("key") == from)) "running" else "pending") }),
                            "cost" to jo("tokens" to 0, "usd_equiv" to "0"), "published" to ja(emptyList()), "metrics" to jo("h24" to null, "d7" to null), "note_fa" to "",
                            "company" to l.str("company"), "title_fa" to l.str("title_fa"),
                        )
                        runs[id] = r
                        return 201 to r
                    }
                }
            }
            return null
        }
        Regex("^/lines/(LN-\\d+)/steps/([^/]+)/test$").find(path)?.let { m ->
            val l = lines[m.groupValues[1]] ?: return 404 to problem(404, "not_found", "این خط پیدا نشد.")
            val s = l.arr("steps").firstOrNull { it.str("key") == m.groupValues[2] } ?: return 404 to problem(404, "not_found", "این مرحله پیدا نشد.")
            return 200 to testOf(s)
        }
        // Runs.
        Regex("^/line-runs/(RN-\\d+)$").find(path)?.let { m ->
            return runs[m.groupValues[1]]?.let { 200 to it } ?: (404 to problem(404, "not_found", "این اجرا پیدا نشد."))
        }
        Regex("^/line-runs/(RN-\\d+)/(rerun|seal|cancel)$").find(path)?.let { m ->
            val ref = m.groupValues[1]
            val r = runs[ref] ?: return 404 to problem(404, "not_found", "این اجرا پیدا نشد.")
            when (m.groupValues[2]) {
                "cancel" -> { runs[ref] = r.with("state" to "cancelled", "ended_at" to HqClock.now().toString()); return 200 to runs.getValue(ref) }
                "seal" -> {
                    val approve = (body?.get("approve") as? JsonPrimitive)?.contentOrNull == "true"
                    val done = r.arr("steps").map { s -> if (s.str("state") == "waiting" || s.str("state") == "pending") s.with("state" to (if (approve) "done" else "skipped")) else s }
                    val pub = if (approve) ja(listOf(jo("platform" to "instagram_reel", "kind" to "reel", "external_id" to "17895", "at" to HqClock.now().toString(), "url" to "https://www.instagram.com/reel/Cdemo3/"))) else ja(emptyList())
                    runs[ref] = r.with("state" to (if (approve) "done" else "cancelled"), "ended_at" to HqClock.now().toString(), "steps" to ja(done), "published" to pub, "note_fa" to (body?.str("note_fa") ?: ""))
                    lines[r.str("line")!!]?.let { l -> if (approve) lines[r.str("line")!!] = l.with("good_runs" to l.int("good_runs") + 1) }
                    return 200 to runs.getValue(ref)
                }
                else -> {
                    val from = body?.str("from_step")
                    val id = "RN-%06d".format(++runSeq)
                    var reached = false
                    val steps = r.arr("steps").map { s ->
                        if (s.str("key") == from) reached = true
                        if (!reached) s else pendingStep(s, if (s.str("key") == from) "running" else "pending")
                    }
                    val n = r.with("ref" to id, "state" to "running", "at" to HqClock.now().toString(), "ended_at" to null, "steps" to ja(steps), "published" to ja(emptyList()), "note_fa" to "", "trigger" to "owner")
                    runs[id] = n
                    return 201 to n
                }
            }
        }
        // Calendar.
        if (path == "/calendar/lines" && method == "GET") return 200 to calendar(query["from"], query["to"], query["company"])
        // Library.
        if (path == "/library") return when (method) {
            "GET" -> 200 to ja(assets.filter { (query["company"] == null || it.str("company") == query["company"] || it.str("company") == null) && (query["kind"] == null || it.str("kind") == query["kind"]) })
            "POST" -> {
                val a = asset("AS-%04d".format(++assetSeq), null, body?.str("kind") ?: "cover_folder", body?.str("title_fa") ?: "پوشه‌ی تازه", (body?.get("config") as? JsonObject) ?: jo(), listOf("/demo/pc-landing-redesign.webp"), 0)
                assets += a
                201 to a
            }
            else -> null
        }
        Regex("^/library/(AS-\\d+)$").find(path)?.let { m ->
            val i = assets.indexOfFirst { it.str("id") == m.groupValues[1] }
            if (i < 0) return 404 to problem(404, "not_found", "این مورد پیدا نشد.")
            return when (method) {
                "PUT" -> { assets[i] = assets[i].with("title_fa" to (body?.str("title_fa") ?: assets[i].str("title_fa")), "config" to (body?.get("config") ?: assets[i]["config"])); 200 to assets[i] }
                "DELETE" -> { val gone = assets.removeAt(i); 200 to gone }
                else -> null
            }
        }
        if (path == "/tts/voices" && method == "GET") return 200 to ja(listOf(
            jo("name" to "Kore", "title_fa" to "کوره", "gender" to "female", "sample_file" to "/demo/voice/piper-amir-numbers.m4a"),
            jo("name" to "Puck", "title_fa" to "پاک", "gender" to "male", "sample_file" to "/demo/voice/piper-gyro-numbers.m4a"),
            jo("name" to "Charon", "title_fa" to "کارون", "gender" to "male", "sample_file" to null),
            jo("name" to "Aoede", "title_fa" to "آئود", "gender" to "female", "sample_file" to null),
        ))
        // The files of the outputs: what the hub's store would say of them.
        Regex("^/files/(/demo/[^?]+)/meta$").find(path)?.let { m -> return fileMeta(m.groupValues[1])?.let { 200 to it } }
        return null
    }

    // ------------------------------------------------------------ the data --
    private fun listed(l: JsonObject): JsonObject {
        val next = nextRun(l)
        return l.with("next_at" to next, "last_run" to (runsOf(l.str("ref")!!, 1).firstOrNull()?.let { r -> jo("ref" to r.str("ref"), "state" to r.str("state"), "at" to r.str("at")) } ?: l["last_run"]))
    }

    private fun runsOf(ref: String, limit: Int): List<JsonObject> =
        runs.values.filter { it.str("line") == ref }.sortedByDescending { it.str("at") }.take(limit)

    /** The next time the line's schedule falls after now. */
    private fun nextRun(l: JsonObject): String? {
        val rr = l.str("schedule") ?: return null
        val today = LocalDate.ofInstant(now, tehran)
        return occurrences(rr, today, today.plusDays(14)).firstOrNull { it.isAfter(now) }?.toString()
    }

    /** The times a simple RRULE (DAILY, or WEEKLY with BYDAY; BYHOUR, BYMINUTE) falls on, from [from] to [to] (days, both inclusive). */
    private fun occurrences(rr: String, from: LocalDate, to: LocalDate): List<Instant> {
        val p = rr.split(';').mapNotNull { kv -> kv.split('=').takeIf { it.size == 2 }?.let { it[0] to it[1] } }.toMap()
        val hour = p["BYHOUR"]?.toIntOrNull() ?: 9
        val min = p["BYMINUTE"]?.toIntOrNull() ?: 0
        val dows = mapOf("MO" to 1, "TU" to 2, "WE" to 3, "TH" to 4, "FR" to 5, "SA" to 6, "SU" to 7)
        val days = if (p["FREQ"] == "WEEKLY") (p["BYDAY"] ?: "SA").split(',').mapNotNull { dows[it] } else null
        val out = mutableListOf<Instant>()
        var d = from
        while (!d.isAfter(to)) {
            if (days == null || d.dayOfWeek.value in days) out += d.atTime(hour, min).atZone(tehran).toInstant()
            d = d.plusDays(1)
        }
        return out
    }

    private fun calendar(from: String?, to: String?, company: String?): JsonObject {
        val a = runCatching { LocalDate.parse(from) }.getOrDefault(LocalDate.ofInstant(now, tehran))
        val b = runCatching { LocalDate.parse(to) }.getOrDefault(a.plusDays(6))
        val byDay = sortedMapOf<String, MutableList<JsonObject>>()
        for (l in lines.values) {
            if (company != null && l.str("company") != company) continue
            if (l.str("state") != "on") continue
            val rr = l.str("schedule") ?: continue
            for (t in occurrences(rr, a, b)) {
                val past = t.isBefore(now)
                val last = runsOf(l.str("ref")!!, 5).firstOrNull { r -> kotlin.math.abs(ChronoUnit.HOURS.between(Instant.parse(r.str("at")), t)) < 24 }
                val state = if (!past) "scheduled" else last?.str("state") ?: "skipped"
                byDay.getOrPut(t.atZone(tehran).toLocalDate().toString()) { mutableListOf() } += jo(
                    "line" to l.str("ref"), "company" to l.str("company"), "platform" to l.str("platform"), "at" to t.toString(),
                    "state" to state, "run" to (if (past) last?.str("ref") else null), "title_fa" to l.str("title_fa"),
                )
            }
        }
        return jo("days" to ja(byDay.map { (d, items) -> jo("day" to d, "items" to ja(items)) }))
    }

    private fun template(key: String, title: String, platform: String, steps: List<JsonObject>, outputs: String) = jo(
        "key" to key, "title_fa" to title, "platform" to platform, "version" to 1, "steps" to ja(steps), "defaults" to jo("auto_after" to 7), "outputs_fa" to ja(listOf(JsonPrimitive(outputs))),
    )

    private fun line(
        ref: String, company: String, template: String, platform: String, channel: JsonObject, title: String, schedule: String?, state: String, mode: String,
        good: Int, version: Int, steps: List<JsonObject>, library: List<String>, ageMin: Long, last: JsonObject?,
    ) = jo(
        "ref" to ref, "company" to company, "template" to template, "template_version" to 1, "platform" to platform, "channel" to channel, "title_fa" to title,
        "schedule" to schedule, "state" to state, "mode" to mode, "good_runs" to good, "auto_after" to 7,
        "caps" to jo("runs_per_day" to 3, "tokens_per_run" to 120_000, "opus_per_day" to 4), "version" to version, "steps" to ja(steps),
        "library" to ja(library.map { JsonPrimitive(it) }), "created_at" to at(ageMin + 60), "updated_at" to at(ageMin), "next_at" to null, "last_run" to last,
    )

    // ⟨2026-11-11⟩ as the hub writes a version: its body without the line's own ref and state, and who made it as `{kind, code}`
    private fun snapshot(l: JsonObject, note: String, by: String, atIso: String?) = jo(
        "line" to l.str("ref"), "version" to l.int("version"), "body" to JsonObject(l - setOf("ref", "state", "company", "created_at", "updated_at", "next_at", "last_run", "version")),
        "by" to jo("kind" to "owner", "code" to "owner", "display_fa" to by), "at" to (atIso ?: at(0)), "note_fa" to note,
    )

    private fun asset(id: String, company: String?, kind: String, title: String, config: JsonObject, files: List<String>, ageMin: Long) = jo(
        "id" to id, "company" to company, "kind" to kind, "title_fa" to title, "config" to config, "files" to ja(files.map { JsonPrimitive(it) }), "created_at" to at(ageMin),
    )

    // --------------------------------------------------------------- steps --
    private fun st(
        key: String, kind: String, title: String, prompt: String? = null, settings: JsonObject = jo(), inputs: List<String> = emptyList(),
        gate: String = "auto", optional: Boolean = false, attempts: Int = 1, timeout: Int = 120,
    ) = jo(
        "key" to key, "kind" to kind, "title_fa" to title, "prompt_fa" to prompt, "settings" to settings, "inputs" to ja(inputs.map { JsonPrimitive(it) }),
        "gate" to gate, "optional" to optional, "enabled" to true, "max_attempts" to attempts, "timeout_s" to timeout,
    )

    private fun reelSteps(speaker: String = "Kore", folder: String = "") = listOf(
        st("script", "gpt_text", "نوشتن فیلمنامه", "یک فیلمنامه‌ی ۳۰ ثانیه‌ای برای ریلز بنویس: قلاب در سه ثانیه‌ی اول، سه نکته‌ی کوتاه با منبع، و در پایان دعوت به دنبال کردن. فارسی روان، بدون اغراق و بدون وعده‌ی سود.", timeout = 180),
        st("dedupe", "dedupe", "بررسی تکراری نبودن", null, jo("threshold" to 0.8), listOf("script"), attempts = 3, timeout = 30),
        st("voice", "tts", "خواندن متن", null, jo("voice" to speaker, "style" to "آرام و مطمئن، مثل گوینده‌ی خبر"), listOf("script"), timeout = 240),
        st("direction", "gpt_text", "نقشه‌ی تصویر", "از روی {{script}} و {{voice}} نقشه‌ی تصویر هر ثانیه را بنویس: نما، حرکت دوربین و متن روی تصویر.", inputs = listOf("script", "voice"), optional = true),
        st("patterns", "pattern_search", "جست‌وجوی الگوی طراحی", null, jo("query" to "ریلز آموزشی طلا", "count" to 5), timeout = 90),
        st("pick", "council_pick", "انتخاب شورا", "از بین {{patterns}} یکی را برای {{direction}} انتخاب کن و دلیلش را کوتاه بگو.", inputs = listOf("direction", "patterns"), timeout = 300),
        st("build", "opus_build", "ساخت ریلز", "با {{script}}، {{voice}}، {{direction}} و {{pick}} مشخصات رندر، کپشن و هشتگ‌ها را بساز. کپشن حداکثر ۲۲۰۰ حرف.", inputs = listOf("script", "voice", "direction", "pick"), timeout = 600),
        st("render", "render", "رندر ویدیو", null, jo("where" to "studio", "aspect" to "9:16", "duration_s" to 30), listOf("build"), timeout = 900),
        st("cover", "cover", "کاور", "برای کاور یک تصویر از پوشه‌ی کاور انتخاب کن و عنوان کوتاه {{script}} را روی آن بگذار.", jo("cover_folder" to folder, "max_files" to 40), listOf("script"), timeout = 240),
        st("quality", "quality", "کنترل کیفیت", null, jo("max_chars" to 2200, "banned_words" to ja(listOf(JsonPrimitive("تضمین سود"), JsonPrimitive("سود قطعی")))), listOf("build"), timeout = 30),
        st("publish", "publish", "انتشار ریلز", null, jo("kind" to "reel", "media_from" to "render", "cover_from" to "cover", "text_from" to "build"), listOf("render", "cover", "build"), gate = "owner", timeout = 300),
        st("story", "publish", "استوری همان روز", null, jo("kind" to "story", "after" to "publish", "delay_min" to 5, "media_from" to "cover"), listOf("publish"), optional = true, timeout = 300),
    )

    private fun telegramSteps() = listOf(
        st("text", "gpt_text", "نوشتن پست", "یک پست کوتاه (حداکثر ۵ خط) درباره‌ی مهم‌ترین خبر بازار امروز بنویس؛ هر عدد با منبع.", timeout = 120),
        st("quality", "quality", "کنترل کیفیت", null, jo("max_chars" to 900), listOf("text"), timeout = 30),
        st("publish", "publish", "انتشار در کانال", null, jo("kind" to "post", "text_from" to "text"), listOf("text", "quality"), gate = "auto", timeout = 120),
    )

    private fun articleSteps() = listOf(
        st("keyword", "gpt_text", "انتخاب عبارت جست‌وجو", "یک عبارت جست‌وجوی تازه برای مقاله‌ی این هفته پیشنهاد بده که هنوز برایش مقاله نداریم.", timeout = 120),
        st("outline", "gpt_text", "سرفصل‌ها", "برای {{keyword}} سرفصل مقاله را بنویس.", inputs = listOf("keyword")),
        st("article", "gpt_text", "نوشتن مقاله", "بر اساس {{outline}} مقاله را کامل بنویس؛ منبع هر عدد در پایان بخش.", inputs = listOf("keyword", "outline"), timeout = 600),
        st("quality", "quality", "کنترل کیفیت", null, jo("min_chars" to 2500), listOf("article"), timeout = 30),
        st("publish", "publish", "انتشار در سایت", null, jo("kind" to "article", "text_from" to "article", "site" to "pro-chart.example"), listOf("article"), gate = "owner", timeout = 300),
    )

    // ---------------------------------------------------------------- runs --
    private fun sr(key: String, kind: String, state: String, startMin: Long, durS: Long, output: JsonObject = jo(), tokens: Long = 0, usd: String? = null, via: String? = null, err: String? = null) = jo(
        "key" to key, "kind" to kind, "state" to state, "attempt" to 1,
        "started_at" to (if (state == "pending") null else at(startMin)), "ended_at" to (if (state in setOf("done", "failed", "skipped")) atSec(startMin, durS).takeIf { startMin * 60 > durS } ?: now.toString() else null),
        "output" to (if (output.isEmpty()) jo("text" to null, "file_id" to null, "files" to ja(emptyList()), "data" to jo()) else output),
        "via" to via, "tokens" to tokens, "usd_equiv" to usd, "error_fa" to err,
    )

    private fun out(text: String? = null, file: String? = null, data: JsonObject = jo()) = jo("text" to text, "file_id" to file, "files" to ja(emptyList()), "data" to data)

    private fun pendingStep(s: JsonObject, state: String) = jo(
        "key" to s.str("key"), "kind" to s.str("kind"), "state" to state, "attempt" to 1, "started_at" to (if (state == "running") HqClock.now().toString() else null),
        "ended_at" to null, "output" to out(), "via" to null, "tokens" to 0, "usd_equiv" to null, "error_fa" to null,
    )

    private fun runBase(ref: String, line: String, trigger: String, dry: Boolean, state: String, startMin: Long, endMin: Long?, steps: List<JsonObject>, tokens: Long, usd: String, published: List<JsonObject>, note: String = "") = jo(
        "ref" to ref, "line" to line, "line_version" to 3, "trigger" to trigger, "dry" to dry, "state" to state, "at" to at(startMin), "ended_at" to endMin?.let { at(it) },
        "steps" to ja(steps), "cost" to jo("tokens" to tokens, "usd_equiv" to usd), "published" to ja(published), "metrics" to jo("h24" to null, "d7" to null), "note_fa" to note,
        "company" to lines[line]?.str("company"), "title_fa" to lines[line]?.str("title_fa"),
    )

    private fun waitingRun(): JsonObject {
        val script = "**قلاب:** طلا دوباره به ۲۰۰۰ دلار رسید؛ خریدارها هنوز هستند؟\n\n" +
            "۱. **حمایت:** قیمت سه بار از ناحیه‌ی ۱۹۸۰ برگشته است (منبع: نمودار روزانه‌ی تریدیار).\n" +
            "۲. **حجم:** حجم معاملات این هفته ۱۲٪ بیشتر از میانگین ماه است.\n" +
            "۳. **ریسک:** شکست زیر ۱۹۷۰ یعنی سناریو باطل است؛ حد ضرر یادت نرود.\n\n" +
            "*برای ریلز بعدی، تریدیار را دنبال کن.*"
        val direction = "۰ تا ۳ ثانیه: نمای نزدیک نمودار با زوم آرام و متن «طلا ۲۰۰۰؟»\n\n۳ تا ۱۸ ثانیه: سه نمای نکته‌ها، هرکدام با خط حمایت روی نمودار.\n\n۱۸ تا ۳۰ ثانیه: لوگوی تریدیار و دعوت به دنبال کردن."
        val steps = listOf(
            sr("script", "gpt_text", "done", 50, 41, out(text = script), 1800, "0.04", "چت‌جی‌پی‌تی"),
            sr("dedupe", "dedupe", "done", 49, 3, out(data = jo("verdict" to "تکراری نیست", "most_alike" to 0.12, "checked" to 40)), 0, null, "کد"),
            sr("voice", "tts", "done", 49, 55, out(file = "/demo/voice/piper-amir-crypto.m4a"), 0, null, "استودیوی گوگل"),
            sr("direction", "gpt_text", "done", 47, 30, out(text = direction), 1400, "0.03", "چت‌جی‌پی‌تی"),
            sr("patterns", "pattern_search", "done", 46, 20, out(data = jo("patterns" to ja(listOf(
                jo("title" to "نمودار با خط حمایت", "source" to "پینترست", "score" to 0.91),
                jo("title" to "عدد درشت روی پس‌زمینه‌ی تیره", "source" to "پینترست", "score" to 0.84),
                jo("title" to "سه کارت نکته", "source" to "پینترست", "score" to 0.8),
            )))), 0, null, "پینترست"),
            sr("pick", "council_pick", "done", 45, 70, out(text = "الگوی «نمودار با خط حمایت» انتخاب شد؛ با موضوع فیلمنامه میخواند و خوانایی عددها بهتر است."), 6200, "0.18", "شورا"),
            sr("build", "opus_build", "done", 44, 220, out(data = jo(
                "caption" to "طلا دوباره ۲۰۰۰ دلار را آزمایش میکند؛ سه نکته که باید بدانی. منبع: نمودار روزانه‌ی تریدیار.",
                "hashtags" to ja(listOf(JsonPrimitive("#طلا"), JsonPrimitive("#تحلیل_تکنیکال"), JsonPrimitive("#تریدیار"))),
                "render" to jo("aspect" to "9:16", "duration_s" to 30, "scenes" to 3),
            )), 9500, "0.31", "ساخت قوی"),
            sr("render", "render", "done", 40, 180, out(file = "/demo/fx-reel-levels.mp4"), 0, null, "استودیوی رسانه"),
            sr("cover", "cover", "done", 36, 60, out(file = "/demo/fx-reel-levels-poster.webp"), 2100, "0.05", "چت‌جی‌پی‌تی"),
            sr("quality", "quality", "done", 35, 2, out(data = jo("checks" to ja(listOf(
                jo("check" to "تکراری نیست", "ok" to "بله"), jo("check" to "منبع هر عدد", "ok" to "بله"),
                jo("check" to "طول کپشن", "ok" to "۱۰۶ از ۲۲۰۰"), jo("check" to "واژه‌ی ممنوع", "ok" to "ندارد"),
            )))), 0, null, "کد"),
            sr("publish", "publish", "waiting", 34, 0),
            sr("story", "publish", "pending", 0, 0),
        )
        return runBase("RN-000003", "LN-0001", "schedule", false, "waiting", 50, null, steps, 21_000, "0.61", emptyList(), "منتظر مُهر توست؛ بعد از آن ریلز منتشر میشود.").with("decision" to "D-000090")
    }

    private fun publishedRun(): JsonObject {
        val steps = reelSteps().map { s ->
            val k = s.str("key")!!
            sr(k, s.str("kind")!!, "done", 3 * 24 * 60L + 60, 30, out(text = if (s.str("kind") == "gpt_text") "خروجی ${s.str("title_fa")}" else null, data = if (s.str("kind") != "gpt_text") jo("نتیجه" to "انجام شد") else jo()), 800, null, "کد")
        }
        val pub = listOf(
            jo("platform" to "instagram_reel", "kind" to "reel", "external_id" to "17850", "at" to at(3 * 24 * 60 + 5), "url" to "https://www.instagram.com/reel/Cdemo2/"),
            jo("platform" to "instagram_story", "kind" to "story", "external_id" to "17851", "at" to at(3 * 24 * 60 + 2), "url" to null),
        )
        return runBase("RN-000002", "LN-0001", "schedule", false, "done", 3 * 24 * 60 + 60, 3 * 24 * 60 + 2, steps, 19_500, "0.55", pub).with(
            "metrics" to jo("h24" to jo("views" to 8420, "likes" to 610, "saves" to 143), "d7" to null),
        )
    }

    private fun failedRun(): JsonObject {
        val steps = listOf(
            sr("script", "gpt_text", "done", 6 * 24 * 60L, 30, out(text = "متن آزمایشی فیلمنامه."), 1500, "0.03", "چت‌جی‌پی‌تی"),
            sr("dedupe", "dedupe", "done", 6 * 24 * 60L - 1, 2, out(data = jo("verdict" to "تکراری نیست")), 0, null, "کد"),
            sr("voice", "tts", "failed", 6 * 24 * 60L - 1, 20, jo(), 0, null, "استودیوی گوگل", "حساب استودیوی گوگل از سیستم بیرون رفته؛ اول دوباره وارد شو، بعد آزمایش را تکرار کن."),
        ) + reelSteps().drop(3).map { s -> sr(s.str("key")!!, s.str("kind")!!, "skipped", 6 * 24 * 60L - 2, 0) }
        return runBase("RN-000001", "LN-0001", "test", true, "failed", 6 * 24 * 60, 6 * 24 * 60 - 3, steps, 1500, "0.03", emptyList())
    }

    private fun telegramRun(ref: String, startMin: Long, state: String): JsonObject {
        val steps = listOf(
            sr("text", "gpt_text", "done", startMin, 20, out(text = "بازار طلا امروز آرام شروع شد؛ قیمت جهانی کمی بالای ۲۰۰۰ دلار ماند (منبع: نمودار روزانه)."), 900, "0.02", "چت‌جی‌پی‌تی"),
            sr("quality", "quality", "done", startMin - 1, 2, out(data = jo("طول" to "۹۸ از ۹۰۰")), 0, null, "کد"),
            sr("publish", "publish", state, startMin - 1, 5, out(data = jo("پیام" to "در کانال منتشر شد")), 0, null, "کد"),
        )
        return runBase(ref, "LN-0002", "schedule", false, state, startMin, startMin - 2, steps, 900, "0.02",
            listOf(jo("platform" to "telegram_post", "kind" to "post", "external_id" to "4412", "at" to at(startMin - 2), "url" to null)))
    }

    /** What «آزمایش همین مرحله» answers: the step alone. */
    private fun testOf(s: JsonObject): JsonObject = when (s.str("kind")) {
        "gpt_text" -> jo("key" to s.str("key"), "kind" to "gpt_text", "state" to "done", "output" to out(text = "**نمونه‌ی آزمایشی:** طلا امروز در محدوده‌ی ۲۰۰۰ دلار نوسان کرد.\n\n- حمایت نزدیک: ۱۹۸۰\n- مقاومت نزدیک: ۲۰۳۰"), "tokens" to 1200, "usd_equiv" to "0.03", "via" to "چت‌جی‌پی‌تی")
        "tts" -> jo("key" to s.str("key"), "kind" to "tts", "state" to "done", "output" to out(file = "/demo/voice/piper-amir-crypto.m4a"), "tokens" to 0, "via" to "استودیوی گوگل")
        else -> jo("key" to s.str("key"), "kind" to s.str("kind"), "state" to "done", "output" to out(data = jo("نتیجه" to "این مرحله آزمایش شد", "زمان" to "۴ ثانیه")), "tokens" to 0, "via" to "کد")
    }

    private fun fileMeta(id: String): JsonObject? = when (id) {
        "/demo/voice/piper-amir-crypto.m4a", "/demo/voice/piper-amir-numbers.m4a", "/demo/voice/piper-gyro-numbers.m4a" ->
            jo("id" to id, "name" to "voice.m4a", "mime" to "audio/mp4", "size" to 180_000, "sha256" to "demo", "kind" to "audio", "status" to "ready", "duration_s" to 28)
        "/demo/fx-reel-levels.mp4" ->
            jo("id" to id, "name" to "reel.mp4", "mime" to "video/mp4", "size" to 1_200_000, "sha256" to "demo", "kind" to "video", "status" to "ready", "width" to 1080, "height" to 1920, "duration_s" to 6, "variants" to jo("poster" to "/demo/fx-reel-levels-poster.webp"))
        "/demo/fx-reel-levels-poster.webp", "/demo/fx-reel-resist-poster.webp", "/demo/ty-story-stoploss-poster.webp", "/demo/pc-landing-redesign.webp" ->
            jo("id" to id, "name" to "cover.webp", "mime" to "image/webp", "size" to 90_000, "sha256" to "demo", "kind" to "image", "status" to "ready", "width" to 1080, "height" to 1350)
        else -> null
    }

    // ------------------------------------------------------------- helpers --
    private fun JsonObject.str(k: String): String? = (this[k] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull
    private fun JsonObject.int(k: String): Int = (this[k] as? JsonPrimitive)?.contentOrNull?.toIntOrNull() ?: 0
    private fun JsonObject.arr(k: String): List<JsonObject> = (this[k] as? JsonArray)?.mapNotNull { it as? JsonObject }.orEmpty()
    private fun JsonObject.with(vararg kv: Pair<String, Any?>): JsonObject = JsonObject(this + jo(*kv))
    private fun ja(xs: List<JsonElement>) = JsonArray(xs)
    private fun jo(vararg kv: Pair<String, Any?>): JsonObject = JsonObject(kv.associate { (k, v) ->
        k to when (v) {
            null -> JsonNull; is JsonElement -> v; is String -> JsonPrimitive(v); is Number -> JsonPrimitive(v); is Boolean -> JsonPrimitive(v)
            else -> error("unsupported ${v::class}")
        }
    })
    private fun problem(status: Int, code: String, fa: String) = jo("code" to code, "message_fa" to fa, "status" to status, "title" to code, "type" to "about:blank")
}
