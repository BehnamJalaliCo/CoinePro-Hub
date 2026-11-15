package com.coinepro.hq

import com.coinepro.hq.core.format.HqClock
import java.time.temporal.ChronoUnit
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

/**
 * Debug builds only: contract §59.7.1 ⟨1.38⟩, an automation's map, as the hub serves it (domain/flow_view.py, commit cba9fbb4).
 *
 * - **`N8:zaribsad_stories`** «۷ استوری روزانه‌ی ضریب صد» (TradeYar, @zaribsad, Fable 5.2): its graph fans out from «زمان‌بندی» to seven stories,
 *   one row each, their hours on the edges, and its DM rule follows the first story that goes out. Today's day is the live sample of
 *   2026-11-15 (F-0029): three stories past their hour, the 4th out, three waiting for theirs (`waiting`, «۱ از ۴ استوری منتشر شد»);
 *   yesterday's went out whole; the day before failed at the pictures.
 * - **`N8:prochart_reels`** «ریلز اول پروچارت» (Opus 5.5): today's day is at work in the render (dots flow into it); yesterday's went out.
 * - **`N8:zaribsad_noon`**: on the board only, switched off.
 * The board gets these three as kind `n8n`, each with `last.steps` for the strip. The controls the hub keeps for its Claude answer 409.
 */
internal class MapDemo {
    private val now = HqClock.now()
    private fun at(minAgo: Long): String = now.minus(minAgo, ChronoUnit.MINUTES).toString()
    private fun ahead(min: Long): String = now.plus(min, ChronoUnit.MINUTES).toString()

    private class S(val key: String, val title: String, val kind: String, val helper: String, val input: String = "", val output: String = "", val model: String? = null, val rules: List<String> = emptyList())

    private val fable = "claude-fable-5-2"
    private val opus = "claude-opus-5-5"
    private val faHours = listOf("۰۸:۳۰", "۱۰:۳۰", "۱۳:۳۰", "۱۵:۳۰", "۱۷:۳۰", "۲۰:۳۰", "۲۲:۳۰")
    private val faDigits = "۰۱۲۳۴۵۶۷"

    private val storySteps: List<S> = listOf(
        S("n8n", "n8n روند را روشن میکند", "n8n", "code", "هر روز ساعت ۰۶:۰۰ تهران", "درخواست امضاشده به هاب برای همان روز"),
        S("order", "سفارش روز در هاب", "order", "code", output = "یک جلسه‌ی خودکار در کارگاه، روی $fable؛ بی پرسش و بی انتظار",
            rules = listOf("۷ استوری، از ۰۸:۳۰ تا ۲۲:۳۰", "سقف هزینه‌ی هر روز ۵ دلار؛ بیشتر شد، کار میایستد و خبر میرسد")),
        S("data", "داده‌ی بازار و کارنامه‌ی VIP", "workshop", "code", output = "قیمت‌ها، ترس و طمع، آمار سیگنال‌ها از سایت تریدیار"),
        S("word", "کلمه‌ی امروز", "workshop", "workshop", model = fable, rules = listOf("کلمه‌ی تازه؛ هیچ‌وقت کلمه‌ای که پیش از این گرفته شده")),
        S("pictures", "۷ عکس واقعی با ChatGPT", "workshop", "gpt", output = "عکس تازه‌ی همان روز، بی متن", rules = listOf("بی انیمه، بی جمله‌ی هشدار")),
        S("compose", "متن، نشان پیج و دعوت روی هر عکس", "workshop", "workshop", output = "story_1.jpg تا story_7.jpg", model = fable),
        S("dm", "جواب دایرکت با سه دکمه", "workshop", "workshop", output = "comment.txt: ورود رایگان VIP، ثبت‌نام LBank، راهنما", model = fable),
        S("package", "بسته‌ی روز", "package", "code", rules = listOf("تا همه‌ی عکس‌ها و جواب دایرکت نرسیده، چیزی منتشر نمیشود")),
        S("schedule", "زمان‌بندی روی IG-Hub", "publish", "ighub", output = "هر استوری در ساعت خودش روی @zaribsad", rules = listOf("ساعتی که بیش از نیم ساعت گذشته باشد جا میماند")),
    ) + faHours.mapIndexed { i, h -> S("s${i + 1}", "استوری ${faDigits[i + 1]}", "publish", "ighub", "ساعت $h", "story_${i + 1}.jpg") } + listOf(
        S("rule", "جواب دایرکت استوری‌ها", "publish", "ighub", output = "هر کس کلمه‌ی امروز را بفرستد، دعوت VIP با سه دکمه میگیرد"),
        S("report", "خبر به مدیر کل", "report", "code", output = "«آماده شد» با کلمه‌ی امروز"),
    )

    private val reelSteps: List<S> = listOf(
        S("n8n", "n8n روند را روشن میکند", "n8n", "code", "هر روز ساعت ۱۳:۰۰ تهران", "درخواست امضاشده به هاب برای روز بعد"),
        S("order", "سفارش روز در هاب", "order", "code", output = "یک جلسه‌ی خودکار در کارگاه، روی $opus؛ بی پرسش و بی انتظار"),
        S("topic", "موضوع روز از بانک موضوع‌ها", "workshop", "workshop", output = "topic.txt", model = opus),
        S("script", "سناریو", "workshop", "gpt", output = "متن گوینده", rules = listOf("اگر ChatGPT جواب نداد، Claude خودش مینویسد")),
        S("voice", "صدای گوینده", "workshop", "gemini", output = "فایل صدا"),
        S("voice_check", "بازبینی صدا و زمان هر کلمه", "workshop", "code"),
        S("direction", "کارگردانی و تدوین روی کاغذ", "workshop", "workshop", model = opus),
        S("render", "ساخت ویدیو، یک بار رندر", "workshop", "workshop", output = "video.mp4", model = opus),
        S("story", "برش استوری", "workshop", "code", output = "story.mp4 (حداکثر ۵۹٫۸ ثانیه)"),
        S("cover", "کاور با المان همان روز", "workshop", "workshop", output = "cover.jpg", model = opus),
        S("texts", "کپشن و متن کامنت", "workshop", "workshop", output = "caption.txt، comment.txt", model = opus),
        S("package", "بسته‌ی کامل", "package", "code", rules = listOf("تا هر شش فایل نرسیده، چیزی منتشر نمیشود")),
        S("schedule", "زمان‌بندی روی IG-Hub", "publish", "ighub", output = "ریلز و استوری @pro.chart"),
        S("publish", "انتشار در ساعت خودش", "publish", "ighub"),
        S("replies", "کامنت هوشمند و جواب استوری", "publish", "ighub", output = "دایرکت با دکمه‌ی لینک، ده جواب عمومی"),
        S("report", "خبر به مدیر کل", "report", "code", output = "«آماده شد» و «منتشر شد» با لینک"),
    )

    private fun lane(s: S): String = when (s.key) {
        "n8n" -> "n8n"
        "order", "package", "report" -> "hub"
        "schedule", "publish", "replies", "rule" -> "ighub"
        "script", "keyart", "cover_gpt", "pictures" -> "chatgpt"
        "voice" -> "voice"
        else -> when (s.helper) { "gpt" -> "chatgpt"; "ighub" -> "ighub"; else -> "workshop" }
    }

    /** As the hub draws it: a node per step on its lane, in time; the stories fan out from «schedule», the rule follows the first. */
    private fun graph(steps: List<S>): JsonObject {
        val posts = steps.map { it.key }.filter { it.length > 1 && it[0] == 's' && it.drop(1).all(Char::isDigit) }
        val nodes = ArrayList<JsonObject>()
        val edges = ArrayList<JsonObject>()
        var col = 0
        var prev: String? = null
        for (s in steps) {
            if (s.key in posts) {
                nodes += jo("key" to s.key, "title_fa" to s.title, "kind" to s.kind, "helper" to s.helper, "lane" to "ighub", "col" to col, "row" to posts.indexOf(s.key), "note_fa" to s.input, "model" to null)
                edges += jo("source" to "schedule", "target" to s.key, "label_fa" to s.input)
                if (s.key == posts.last()) { col++; prev = posts.first() }
                continue
            }
            nodes += jo("key" to s.key, "title_fa" to s.title, "kind" to s.kind, "helper" to s.helper, "lane" to lane(s), "col" to col, "row" to 0, "note_fa" to s.output, "model" to s.model)
            prev?.let { p -> edges += jo("source" to p, "target" to s.key, "label_fa" to if (posts.isNotEmpty() && p == posts.first()) "وقتی اولین استوری رفت" else "") }
            prev = s.key
            col++
        }
        val used = nodes.map { (it["lane"] as JsonPrimitive).content }.toSet()
        return jo("lanes" to strs(*listOf("n8n", "hub", "workshop", "chatgpt", "voice", "ighub").filter { it in used }.toTypedArray()), "nodes" to JsonArray(nodes), "edges" to JsonArray(edges))
    }

    private fun stepJson(s: S) = jo(
        "key" to s.key, "title_fa" to s.title, "seat" to "", "kind" to s.kind, "helper" to s.helper, "model" to s.model, "effort" to if (s.model != null) "max" else null,
        "input_fa" to s.input, "output_fa" to s.output, "rules_fa" to strs(*s.rules.toTypedArray()), "inputs" to JsonArray(emptyList()), "gate" to "auto",
        "optional" to false, "max_attempts" to 1, "timeout_s" to null,
    )

    private fun sf(id: String, name: String, mime: String, kind: String, text: String? = null) = jo("id" to id, "name" to name, "mime" to mime, "size" to 120_000, "kind" to kind, "text" to text)

    // ------------------------------------------------------------------------------------- the days --
    private class Day(val ref: String, val key: String, val state: String, val note: String, val atIso: String, val createdMinAgo: Long, val cost: Double, val states: Map<String, String>, val permalink: String? = null)

    private val storyDays: List<Day> = run {
        val head = listOf("n8n", "order", "data", "word", "pictures", "compose", "dm", "package", "schedule")
        listOf(
            Day("F-0029", "zaribsad_stories", "waiting", "۱ از ۴ استوری منتشر شد", at(30), 6 * 60, 1.84,
                head.associateWith { "done" } + mapOf("s1" to "skipped", "s2" to "skipped", "s3" to "skipped", "s4" to "done", "s5" to "waiting", "s6" to "waiting", "s7" to "waiting", "rule" to "done", "report" to "done")),
            Day("F-0027", "zaribsad_stories", "done", "۷ استوری منتشر شد", at(1_440 + 30), 1_440 + 6 * 60, 1.62, storySteps.associate { it.key to "done" }),
            Day("F-0025", "zaribsad_stories", "failed", "ساخت به نتیجه نرسید", at(2 * 1_440 + 30), 2 * 1_440 + 6 * 60, 0.41,
                mapOf("n8n" to "done", "order" to "done", "data" to "done", "word" to "done", "pictures" to "failed")),
        )
    }

    private val reelDays: List<Day> = run {
        val doneTo = listOf("n8n", "order", "topic", "script", "voice", "voice_check", "direction")
        listOf(
            Day("F-0030", "prochart_reels", "running", "در کارگاه ساخته میشود", at(10), 50, 2.12, doneTo.associateWith { "done" } + ("render" to "running")),
            Day("F-0028", "prochart_reels", "done", "منتشر شد", at(1_440 - 6 * 60), 1_440 + 3 * 60, 3.05, reelSteps.associate { it.key to "done" }, "https://www.instagram.com/reel/Dfq-Zc4lNve/"),
        )
    }

    private fun outputsOf(d: Day, key: String): List<JsonObject> = when {
        d.states[key] != "done" -> emptyList()
        key == "compose" -> (1..3).map { sf("/demo/ty-story-stoploss-poster.webp", "story_$it.jpg", "image/webp", "image") }
        key == "dm" -> listOf(sf("/demo/t-dm", "comment.txt", "text/plain", "text", "کلمه‌ی امروز: «حمایت»\nورود رایگان VIP · ثبت‌نام LBank · راهنما"))
        key == "s4" -> listOf(sf("/demo/ty-story-stoploss-poster.webp", "story_4.jpg", "image/webp", "image"))
        key == "topic" -> listOf(sf("/demo/t-topic", "topic.txt", "text/plain", "text", "سه خطای رایج در کشیدن خط روند"))
        key == "voice" -> listOf(sf("/demo/fx-reel-levels-voice.m4a", "voice.m4a", "audio/mp4", "audio"))
        key == "render" -> listOf(sf("/demo/fx-reel-levels.mp4", "video.mp4", "video/mp4", "video"))
        key == "cover" -> listOf(sf("/demo/fx-reel-levels-poster.webp", "cover.jpg", "image/webp", "image"))
        else -> emptyList()
    }

    private fun lineRun(d: Day): JsonObject {
        val steps = if (d.key == "prochart_reels") reelSteps else storySteps
        val started = d.createdMinAgo
        val stepRuns = steps.mapIndexed { i, s ->
            val st = d.states[s.key] ?: "pending"
            val begin = started - i * 3
            jo(
                "key" to s.key, "kind" to s.kind, "title_fa" to s.title, "state" to st, "attempt" to 1,
                "started_at" to if (st in setOf("done", "running", "failed")) at(begin) else null,
                "ended_at" to if (st in setOf("done", "failed")) at(begin - 2) else null,
                "output" to jo("text" to s.output.ifBlank { null }), "via" to s.helper, "tokens" to 0, "usd_equiv" to 0,
                "error_fa" to if (st == "failed") "ChatGPT سه بار عکس نساخت؛ مرورگر کمک‌کارها از حساب بیرون افتاده بود." else null,
                "gate" to null, "sealed_at" to null, "sealed_by" to null, "reused" to false, "missing" to JsonArray(emptyList()),
                "helper" to s.helper, "model" to s.model, "effort" to if (s.model != null) "max" else null, "outputs" to JsonArray(outputsOf(d, s.key)),
            )
        }
        val title = if (d.key == "prochart_reels") "ریلز اول پروچارت" else "۷ استوری روزانه‌ی ضریب صد"
        return jo(
            "ref" to d.ref, "line" to "", "company" to if (d.key == "prochart_reels") "PC" else "TY", "title_fa" to title, "platform" to "instagram",
            "line_version" to 1, "trigger" to "n8n", "dry" to false, "state" to d.state, "at" to at(d.createdMinAgo),
            "ended_at" to if (d.state == "done") at(d.createdMinAgo - 60) else null, "steps" to JsonArray(stepRuns),
            "cost" to jo("tokens" to 0, "usd_equiv" to d.cost, "usd" to d.cost),
            "published" to JsonArray(listOfNotNull(d.permalink?.let { jo("platform" to "instagram", "kind" to "reel", "external_id" to "1790", "at" to d.atIso, "url" to it, "permalink" to it) })),
            "metrics" to jo(), "note_fa" to d.note, "decision" to null, "rerun_of" to null, "from_step" to null,
            "automation" to "N8:${d.key}", "company_fa" to if (d.key == "prochart_reels") "پرو-چارت" else "تریدیار", "topic_fa" to null,
            "results" to d.permalink?.let { jo("permalink" to it) }, "minutes" to if (d.state == "done") 52.0 else null,
        )
    }

    private fun runRef(d: Day) = jo("ref" to d.ref, "at" to d.atIso, "state" to d.state, "topic_fa" to null, "note_fa" to d.note, "cost_usd" to d.cost,
        "results" to d.permalink?.let { jo("permalink" to it) })

    // ---------------------------------------------------------------------------------- the automations --
    private val on = mutableMapOf("zaribsad_stories" to true, "prochart_reels" to true, "zaribsad_noon" to false)

    private fun automation(key: String): JsonObject? {
        val stories = key == "zaribsad_stories"
        if (!stories && key != "prochart_reels") return null
        val days = if (stories) storyDays else reelDays
        val steps = if (stories) storySteps else reelSteps
        val state = if (on.getValue(key)) "on" else "off"
        val upcoming = (0 until 14).map { i -> jo("at" to ahead(if (stories) 22 * 60L + i * 1_440 else 27 * 60L + i * 1_440), "topic_fa" to null, "skip" to false) }
        return jo(
            "ref" to "N8:$key", "kind" to "flow", "company" to if (stories) "TY" else "PC", "company_fa" to if (stories) "تریدیار" else "پرو-چارت",
            "playbook" to null, "playbook_fa" to "", "version" to null, "line" to null,
            "title_fa" to if (stories) "۷ استوری روزانه‌ی ضریب صد" else "ریلز اول پروچارت", "state" to state, "paused_until" to null,
            "schedule" to jo("mode" to "fixed", "at" to if (stories) "06:00" else "13:00", "days" to null,
                "when_fa" to if (stories) "هر روز ۰۶:۰۰ ساخت، ۷ استوری از ۰۸:۳۰ تا ۲۲:۳۰" else "هر روز ۱۳:۰۰ ساخت، انتشار فردا ۱۹:۳۰"),
            "account" to if (stories) "zaribsad" else "pro.chart", "story" to true, "mode" to "auto",
            "budget" to jo("per_run_usd" to 5.0, "per_day_usd" to 5.0, "spent_today_usd" to days.first().cost),
            "replies" to jo(), "steps" to JsonArray(steps.map(::stepJson)),
            "next" to if (state == "on") upcoming.first() else null, "upcoming" to JsonArray(if (state == "on") upcoming else emptyList()),
            "last_run" to runRef(days.first()), "today" to jo("runs" to 1, "cost_usd" to days.first().cost),
            "n8n" to jo("workflow" to "n8n", "last_tick_at" to at(1)), "created_at" to at(3 * 1_440), "by_fa" to "Claude سرور هاب، به دستور مدیر کل",
            "graph" to graph(steps),
        )
    }

    private fun boardItem(key: String, title: String, co: String, coFa: String, whenFa: String, day: Day?): JsonObject {
        val steps = if (key == "prochart_reels") reelSteps else storySteps
        return jo(
            "ref" to "N8:$key", "kind" to "n8n", "title_fa" to title, "company" to co, "company_fa" to coFa, "playbook" to null, "playbook_fa" to null, "version" to null,
            "when_fa" to whenFa, "state" to if (on.getValue(key)) "on" else "off", "switchable" to true,
            "last" to day?.let { d -> jo("at" to d.atIso, "state" to d.state, "note_fa" to d.note, "steps" to JsonArray(steps.map { s -> jo("key" to s.key, "state" to (d.states[s.key] ?: "pending")) })) },
            "next_at" to if (on.getValue(key)) ahead(5 * 60) else null, "cost_today_usd" to day?.cost, "opens" to "automation/N8:$key",
        )
    }

    /** The board of §59.10 with the n8n flows first. */
    fun board(path: String, method: String, answer: Pair<Int, JsonElement>): Pair<Int, JsonElement> {
        if (path != "/automations/board" || method != "GET") return answer
        val body = answer.second as? JsonObject ?: return answer
        val items = (body["items"] as? JsonArray).orEmpty()
        val n8n = listOf(
            boardItem("zaribsad_stories", "۷ استوری روزانه‌ی ضریب صد", "TY", "تریدیار", "هر روز ۰۶:۰۰ ساخت، ۷ استوری از ۰۸:۳۰ تا ۲۲:۳۰", storyDays.first()),
            boardItem("prochart_reels", "ریلز اول پروچارت", "PC", "پرو-چارت", "هر روز ۱۳:۰۰ ساخت، انتشار فردا ۱۹:۳۰", reelDays.first()),
            boardItem("zaribsad_noon", "ریلز چرخشی ضریب صد", "TY", "تریدیار", "هر روز ۰۷:۰۰ ساخت، انتشار امروز ۱۲:۰۰", null),
        )
        return answer.first to JsonObject(body + ("items" to JsonArray(n8n + items)))
    }

    @Synchronized
    fun handle(method: String, path: String): Pair<Int, JsonElement>? {
        Regex("^/line-runs/(F-\\d{4})$").find(path)?.let { m ->
            val d = (storyDays + reelDays).firstOrNull { it.ref == m.groupValues[1] } ?: return 404 to problem(404, "not_found", "این روز پیدا نشد.")
            return 200 to lineRun(d)
        }
        val m = Regex("^/automations/N8:([a-z_0-9]+)(?:/(.+))?$").find(path) ?: return null
        val key = m.groupValues[1]
        val tail = m.groupValues[2]
        if (key !in on) return 404 to problem(404, "not_found", "این اتوماسیون پیدا نشد.")
        return when {
            tail == "" && method == "GET" -> automation(key)?.let { 200 to it } ?: (404 to problem(404, "not_found", "نقشه‌ی این روند در نسخه‌ی نمایشی نیست."))
            tail == "state" && method == "POST" -> { on[key] = !on.getValue(key); 200 to (automation(key) ?: jo("ref" to "N8:$key", "state" to if (on.getValue(key)) "on" else "off")) }
            tail == "runs" && method == "GET" -> 200 to jo("items" to JsonArray((if (key == "prochart_reels") reelDays else if (key == "zaribsad_stories") storyDays else emptyList()).map(::runRef)), "next_cursor" to null)
            tail == "audit" && method == "GET" -> 200 to JsonArray(listOf(jo("at" to at(2 * 1_440), "who_fa" to "Claude سرور هاب", "action" to "automation.created", "summary_fa" to "به دستور مدیر کل ساخته شد")))
            else -> 409 to problem(409, "validation_failed", "این اتوماسیون را Claude سرور هاب تنظیم میکند؛ همین را در گفتگو بگو.")
        }
    }

    private fun strs(vararg s: String) = JsonArray(s.map(::JsonPrimitive))
    private fun jo(vararg kv: Pair<String, Any?>): JsonObject = JsonObject(kv.associate { (k, v) ->
        k to when (v) {
            null -> JsonNull; is JsonElement -> v; is String -> JsonPrimitive(v); is Number -> JsonPrimitive(v); is Boolean -> JsonPrimitive(v)
            else -> error("unsupported ${v::class}")
        }
    })
    private fun problem(status: Int, code: String, fa: String) = jo("code" to code, "message_fa" to fa, "status" to status, "title" to code, "type" to "about:blank")
}
