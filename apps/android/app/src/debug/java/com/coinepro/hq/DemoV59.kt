package com.coinepro.hq

import com.coinepro.hq.core.format.HqClock
import java.time.LocalDate
import java.time.ZoneId
import java.time.temporal.ChronoUnit
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull

/**
 * Debug builds only: contract §59 ⟨1.37⟩, the library of working groups and the automations.
 *
 * - **The library (§59.1):** PB-0004 «ریلز روزانه‌ی پروچارت», the working group of the F-0018 kind: sealed v2 (v1 before it), its flow of
 *   twelve steps in the owner's order (topic, script and cover with ChatGPT, the voice with Gemini 3.8 Flash TTS and its check, the
 *   direction with Opus 5.5 at its highest effort, a fresh reference, the build in the workshop, the package, the reel and the story at
 *   the best hour, the rules, the day's report), its package, six lessons from the fault log, and its figures; Pro-Chart runs v2. The
 *   §40 playbooks of [V40Demo] get their figures and versions too. `revise` makes v3 a draft, `compare` answers code's lines,
 *   `members/{code}/version` moves a member, `export` answers the file, `copy` and `import` make drafts.
 * - **The form (§59.4):** `dry` answers the preview (the days in order, the cost, what the hub settles itself); without, a membership and
 *   a new flow (AT-0701…) on the board.
 * - **The automations (§59.7–§59.10):** AT-0700 Pro-Chart's daily reels (best hour, story, «خودکار کامل», $5 a run, $8 a day), its four runs
 *   (today's at work in the workshop step, yesterday's done with its figures, one done before, one that failed at the cover), the next
 *   fourteen days, its replies (ten in turn) and links, the audit; the board beside it holds a standing word, a routine, a line, two
 *   rules from a sentence (one waiting for the seal) and an archive rule; the road's health has the helpers' browser on amber.
 */
internal class V59Demo(private val v40: V40Demo) {
    private val now = HqClock.now()
    private fun at(minAgo: Long): String = now.minus(minAgo, ChronoUnit.MINUTES).toString()
    private fun ahead(min: Long): String = now.plus(min, ChronoUnit.MINUTES).toString()
    private val tehran = ZoneId.of("Asia/Tehran")

    private fun step(key: String, title: String, seat: String, kind: String, helper: String?, model: String?, effort: String?, input: String, output: String, vararg rules: String) =
        jo("key" to key, "title_fa" to title, "seat" to seat, "kind" to kind, "helper" to helper, "model" to model, "effort" to effort,
            "input_fa" to input, "output_fa" to output, "rules_fa" to strs(*rules), "inputs" to JsonArray(emptyList()), "gate" to "auto", "optional" to false,
            "max_attempts" to if (kind == "tts" || kind == "cover") 3 else 1, "timeout_s" to null)

    private val steps = listOf(
        step("topic", "موضوع تازه", "writer", "topic", "model", "claude-sonnet-5-5", null, "دفتر موضوع‌های پروچارت و نتیجه‌ی روزهای قبل", "یک موضوع که هیچ‌وقت گفته نشده", "هیچ موضوعی دو بار نه؛ دفتر موضوع‌ها تکراری را رد میکند."),
        step("script", "سناریو و متن", "writer", "gpt_text", "gpt", null, null, "موضوع روز", "متن گوینده، زیر ۴۵ ثانیه، با کلمه‌ی کامنت در آن", "هر کار یک صفحه‌ی جدا؛ متن در چت موقت.", "کلمه‌ی کامنت در متن گفته شود."),
        step("cover", "کاور", "designer", "cover", "gpt", null, null, "متن و رنگ‌های برند", "کاور JPG در قاب ۹ به ۱۶", "هر تصویر در چت معمولیِ تازه؛ چت موقت تصویر نمیسازد."),
        step("voice", "صدا", "voice", "tts", "aistudio", "gemini-3.8-flash-tts", null, "متن گوینده", "فایل صدا با گوینده‌ی شرکت (Cruz، بی حالت)", "اول API، اگر نشد صفحه‌ی AI Studio.", "هرگز مدل lite نه."),
        step("voice_check", "بازبینی صدا", "voice", "voice_check", "code", null, null, "صدا و متن", "صدای پذیرفته، یا ساخت دوباره", "تطابق کلمه‌ها دست‌کم ۸۵٪؛ سکوت بیش از ۲ ثانیه نه."),
        step("direction", "کارگردانی", "director", "opus_build", "model", "claude-opus-5-5", "max", "متن، صدا و کاور", "نقشه‌ی نماها، برای هر کلمه و هر جمله"),
        step("inspire", "الهام", "director", "inspire", "code", null, null, "موضوع روز", "یک ویدیوی مشابه یا پین تازه", "هر بار تازه؛ نمونه‌ای که قبلاً دیده شده نه."),
        step("build", "ساخت ویدیو", "motion", "workshop", "workshop", "claude-opus-5-5", "max", "نقشه‌ی نماها، صدا، کاور و الهام", "ویدیوی نهایی MP4", "موشن‌گرافی و انیمه با هم، برای هر کلمه و هر جمله.", "یک ساخت نهایی؛ ویدیوی پیش‌نمایش نه.", "رندر با حداکثر ۲ پردازش؛ کارگاه ۴ گیگ حافظه دارد."),
        step("package", "بسته", "media", "package", "code", null, null, "ویدیو، کاور و متن", "caption.txt، comment.txt و topic.txt کنار ویدیو و کاور", "ده جواب عمومی یا بیشتر، به نوبت."),
        step("publish", "انتشار ریلز و استوری", "media", "publish", "ighub", null, null, "بسته", "ریلز و استوری در بهترین ساعت", "بی دکمه‌ی مالک."),
        step("rules", "قاعده‌ها", "media", "publish", "ighub", null, null, "پست منتشرشده", "کامنت روی همان پست؛ استوری و دایرکت با کلمه"),
        step("report", "گزارش روزانه", "media", "report", "code", null, null, "نتیجه‌ی روز", "یک خط برای مدیر کل"),
    )
    private val seats = JsonArray(listOf(
        seat("writer", "scriptwriter", "نویسنده", "موضوع و متن هر روز با ChatGPT.", "gpt"),
        seat("designer", "designer", "طراح کاور", "کاور هر ریلز با ChatGPT.", "gpt"),
        seat("voice", "voice_producer", "گوینده", "صدای هر ریلز با Gemini در AI Studio.", "aistudio"),
        seat("director", "video_director", "کارگردان", "نقشه‌ی نماها و الهام.", "gemini"),
        seat("motion", "motion_designer", "موشن‌گرافی", "ساخت ویدیو در کارگاه."),
        seat("media", "media_manager", "مدیر رسانه", "بسته، انتشار، قاعده‌ها و گزارش."),
    ))
    private fun seat(seat: String, role: String, title: String, duties: String, vararg helpers: String) =
        jo("seat" to seat, "role" to role, "title_fa" to title, "duties_fa" to duties, "helpers" to strs(*helpers), "model" to null)
    private val pkg = JsonArray(listOf(
        jo("name" to "video.mp4", "title_fa" to "ویدیو", "step" to "build", "required" to true),
        jo("name" to "cover.jpg", "title_fa" to "کاور", "step" to "cover", "required" to true),
        jo("name" to "caption.txt", "title_fa" to "کپشن", "step" to "package", "required" to true),
        jo("name" to "comment.txt", "title_fa" to "کامنت و دایرکت", "step" to "package", "required" to true),
        jo("name" to "topic.txt", "title_fa" to "موضوع", "step" to "package", "required" to false),
    ))
    private fun lesson(n: Int, title: String, cause: String, fix: String, rule: String, step: String?) =
        jo("n" to n, "title_fa" to title, "cause_fa" to cause, "fix_fa" to fix, "rule_fa" to rule, "step" to step)
    private val lessons = JsonArray(listOf(
        lesson(1, "فرمان به دو مدیرعامل رفت", "متن فرمان کار شرکت دوم را هم داشت؛ دو برنامه ساخته شد.", "فقط مسئول اول برنامه میدهد.", "هر کارگروه یک مسئول دارد.", null),
        lesson(2, "مصرف توکن بسیار زیاد", "هر قدم یک نشست مستقیم بود با همه‌ی ابزارها.", "هر قدم یک فراخوانی؛ فهرست ابزار کوتاه.", "Opus در بیشترین سطح فقط برای ساخت ویدیو.", "build"),
        lesson(5, "صدا ساخته نمیشد", "صفحه‌ی AI Studio عوض شده بود.", "اول API جمینای، بعد صفحه‌ی وب.", "صدا اول با API.", "voice"),
        lesson(16, "ساخت ویدیو از کار افتاد", "حافظه‌ی ۴ گیگ کارگاه و رندر با ۷ مرورگر.", "رندر با حداکثر ۲ پردازش.", "رندر با حداکثر ۲ پردازش.", "build"),
        lesson(17, "پینترست زودتر از نوبتش", "ترتیب قدم‌ها با دستور مدیر کل نبود.", "قدم‌ها به ترتیب پرامپت اول.", "ترتیب قدم‌ها همان ترتیب مدیر کل.", "inspire"),
        lesson(18, "کاور ساخته نشد", "چت موقت ChatGPT تصویر نمیسازد.", "هر تصویر در چت معمولیِ تازه.", "کاور در چت معمولیِ تازه.", "cover"),
    ))

    private val versions = mutableListOf(
        jo("version" to 2, "state" to "sealed", "at" to at(1_500), "by_fa" to "مدیر کل", "members" to 1, "changelog_fa" to strs(
            "قدم «بازبینی صدا» اضافه شد", "قدم «الهام» بعد از «کارگردانی» آمد", "قاعده‌ی «رندر با حداکثر ۲ پردازش» اضافه شد", "درس «کاور ساخته نشد» اضافه شد",
        )),
        jo("version" to 1, "state" to "sealed", "at" to at(2_900), "by_fa" to "مدیر کل", "members" to 0, "changelog_fa" to JsonArray(emptyList())),
    )
    private var draft3: JsonObject? = null

    private fun pb4(version: Int = 2): JsonObject {
        val v = versions.firstOrNull { it.int("version") == version } ?: versions.first()
        val stepsOf = if (version == 1) steps.filter { it.str("key") !in setOf("voice_check", "inspire") } else steps
        return jo(
            "ref" to "PB-0004", "title_fa" to "ریلز روزانه‌ی پروچارت",
            "purpose_fa" to "هر روز یک ریلز تازه برای پروچارت، از موضوع تا انتشار و جواب کامنت‌ها، بی دکمه‌ی مدیر کل.",
            "state" to v.str("state"), "version" to version, "edits" to 4, "draft_version" to draft3?.let { 3 }, "platform" to "instagram",
            "seats" to seats, "routines" to JsonArray(emptyList()),
            "kpis" to JsonArray(listOf(jo("key" to "views", "title_fa" to "بازدید ریلز", "source" to "instagram", "unit" to "بازدید"), jo("key" to "clicks", "title_fa" to "کلیک لینک", "source" to "ighub", "unit" to "کلیک"))),
            "connections" to strs("instagram"), "rules_fa" to strs("هر روز موضوعی تازه.", "گوینده‌ی شرکت ثابت است.", "مدیر کل دکمه‌ی انتشار نمیزند."),
            "source" to jo("order" to "F-0094", "company" to "PC", "conversation" to "CV-0594"),
            "members" to JsonArray(listOf(jo("company" to "PC", "name_fa" to "پرو-چارت", "state" to "on", "order" to "F-0094",
                "publish" to jo("mode" to "auto", "account" to "pro.chart", "story" to true, "since" to at(1_500), "at" to null, "best" to true),
                "version" to 2, "automation" to "AT-0700"))),
            "parent" to null, "created_at" to at(2_950), "sealed_at" to at(1_500), "retired_at" to null, "group" to "pb_4", "note_fa" to null,
            "versions" to JsonArray(listOfNotNull(draft3?.let { jo("version" to 3, "state" to "draft", "at" to now.toString(), "by_fa" to "مدیر کل", "members" to 0, "changelog_fa" to JsonArray(emptyList())) }) + versions),
            "steps" to JsonArray(stepsOf), "package" to pkg, "lessons" to lessons,
            "stats" to stats(9, 8, 88.9, 3.42, 38.0, at(300), 1), "companies_fa" to strs("پرو-چارت"),
        )
    }
    private fun stats(runs: Int, done: Int, pct: Double?, cost: Double?, min: Double?, last: String?, cos: Int) =
        jo("runs" to runs, "done" to done, "success_pct" to pct, "avg_cost_usd" to cost, "avg_minutes" to min, "last_run_at" to last, "companies" to cos)

    /** §40's playbooks with their §59 figures (the library's cards read them). */
    private fun augmented(pb: JsonObject): JsonObject {
        val members = (pb["members"] as? JsonArray)?.mapNotNull { (it as? JsonObject)?.str("name_fa") }.orEmpty()
        val extra = when (pb.str("ref")) {
            "PB-0001" -> stats(23, 21, 91.3, 1.18, 22.0, at(900), 2)
            else -> stats(0, 0, null, null, null, null, members.size)
        }
        val v = pb.int("version") ?: 1
        return JsonObject(pb + mapOf("stats" to extra, "companies_fa" to strs(*members.toTypedArray()),
            "versions" to JsonArray(listOf(jo("version" to v, "state" to pb.str("state"), "at" to (pb.str("sealed_at") ?: pb.str("created_at")), "by_fa" to "مدیر کل", "members" to members.size, "changelog_fa" to JsonArray(emptyList()))))))
    }

    // ------------------------------------------------------------------ the flow --
    private var flow = jo(
        "ref" to "AT-0700", "kind" to "flow", "company" to "PC", "company_fa" to "پرو-چارت", "playbook" to "PB-0004", "playbook_fa" to "ریلز روزانه‌ی پروچارت",
        "version" to 2, "line" to "LN-0701", "title_fa" to "ریلز روزانه‌ی پروچارت", "state" to "on", "paused_until" to null,
        "schedule" to jo("mode" to "best", "at" to null, "days" to null, "when_fa" to "هر روز، بهترین ساعت (حالا 19:00)"),
        "account" to "pro.chart", "story" to true, "mode" to "auto",
        "budget" to jo("per_run_usd" to 5.0, "per_day_usd" to 8.0, "spent_today_usd" to 2.31),
        "replies" to jo(
            "comment" to jo("match" to "per_video"), "story" to true, "dm" to true,
            "public_pool" to strs("برو دایرکتت رو چک کن فرستادم برات، موفق باشی 🤍", "فرستادم! یه سر به دایرکتت بزن 🙌", "توی دایرکت منتظرته 🎁 روز خوبی داشته باشی"),
            "dm_template" to jo("text_fa" to "این هم {topic} که خواستی 👇 با پروچارت نمودارت همیشه کنارته.", "buttons" to JsonArray(listOf(jo("title_fa" to "ورود به پرو چارت", "section" to null)))),
            "per_video_dm" to true, "repeat" to jo("mode" to "once_a_year", "days" to null), "section" to null,
        ),
        "steps" to JsonArray(steps),
        "next" to jo("at" to ahead(24 * 60 + 150), "topic_fa" to null, "skip" to false),
        "upcoming" to JsonArray((1..14).map { d -> jo("at" to ahead(d * 24 * 60L + 150), "topic_fa" to if (d == 1) "سطح‌های حمایت در یک دقیقه" else null, "skip" to false) }),
        "last_run" to null, "today" to jo("runs" to 1, "cost_usd" to 2.31),
        "n8n" to jo("workflow" to "hq-flows", "last_tick_at" to at(0)), "created_at" to at(1_500), "by_fa" to "مدیر کل",
    )
    private val made = mutableListOf<JsonObject>()
    private var autoSeq = 701

    private fun sf(id: String, name: String, mime: String, kind: String, text: String? = null) =
        jo("id" to id, "name" to name, "mime" to mime, "size" to (text?.length ?: 1_200_000), "kind" to kind, "text" to text)

    private val script = "خط روند رو کجا بکشیم؟ سه خطای رایج که حساب رو خالی میکنه. اول: کشیدن خط روی سایه‌ها... آخرش کامنت کن «روند» تا لینک آموزش برات بیاد."
    private val caption = "سه خطای رایج در کشیدن خط روند 📉\nکامنت کن «روند» تا لینک آموزش برات بیاد 👇\n#پروچارت #تحلیل_تکنیکال"
    private val commentTxt = "keyword: روند\nmatch: any\nreply: این هم آموزش خط روند 👇 با پروچارت نمودارت همیشه کنارته.\nlink: https://pro-chart.com\npublic: برو دایرکتت رو چک کن فرستادم برات، موفق باشی 🤍"

    private fun stepRun(key: String, state: String, minAgo: Long, dur: Long, cost: Double?, outputs: List<JsonObject> = emptyList(), error: String? = null): JsonObject {
        val d = steps.first { it.str("key") == key }
        val started = at(minAgo)
        return jo(
            "key" to key, "kind" to d.str("kind"), "state" to state, "attempt" to 1, "started_at" to if (state == "pending") null else started,
            "ended_at" to if (state in setOf("done", "failed")) at(minAgo - dur) else null,
            "output" to jo("text" to null, "file_id" to null, "files" to JsonArray(emptyList()), "data" to JsonObject(emptyMap())),
            "via" to null, "tokens" to 0, "usd_equiv" to null, "error_fa" to error, "title_fa" to d.str("title_fa"), "gate" to null,
            "seat_fa" to (seats.firstOrNull { (it as JsonObject).str("seat") == d.str("seat") } as? JsonObject)?.str("title_fa"),
            "helper" to d.str("helper"), "model" to d.str("model"), "effort" to d.str("effort"), "cost_usd" to cost, "outputs" to JsonArray(outputs),
        )
    }

    private fun run(ref: String, state: String, minAgo: Long, topic: String, stepRuns: List<JsonObject>, results: JsonObject?, cost: Double?, note: String, minutes: Double?) = jo(
        "ref" to ref, "line" to "LN-0701", "line_version" to 2, "trigger" to "n8n", "dry" to false, "state" to state, "at" to at(minAgo),
        "ended_at" to if (state in setOf("done", "failed", "skipped")) at(minAgo - (minutes ?: 0.0).toLong()) else null,
        "steps" to JsonArray(stepRuns), "cost" to jo("tokens" to 0, "usd_equiv" to null, "usd" to cost),
        "published" to JsonArray(if (results != null) listOf(jo("platform" to "instagram", "kind" to "reel", "external_id" to "1786", "at" to at(minAgo - 40), "url" to results.str("permalink"), "permalink" to results.str("permalink")),
            jo("platform" to "instagram", "kind" to "story", "external_id" to "1812", "at" to at(minAgo - 40), "url" to results.str("story_permalink"), "permalink" to results.str("story_permalink"))) else emptyList()),
        "metrics" to jo("h24" to null, "d7" to null), "note_fa" to note, "company" to "PC", "title_fa" to "ریلز روزانه‌ی پروچارت", "platform" to "instagram_reel",
        "decision" to null, "rerun_of" to null, "from_step" to null,
        "automation" to "AT-0700", "playbook" to "PB-0004", "playbook_fa" to "ریلز روزانه‌ی پروچارت", "version" to 2, "company_fa" to "پرو-چارت",
        "topic_fa" to topic, "results" to results, "minutes" to minutes,
    )

    private val runs: MutableMap<String, JsonObject> = run {
        val today = run("RN-000704", "running", 34, "سه خطای رایج در کشیدن خط روند", listOf(
            stepRun("topic", "done", 34, 1, 0.04, listOf(sf("/demo/t1", "topic.txt", "text/plain", "text", "سه خطای رایج در کشیدن خط روند"))),
            stepRun("script", "done", 33, 4, 0.0, listOf(sf("/demo/t2", "script.md", "text/markdown", "text", script))),
            stepRun("cover", "done", 29, 3, 0.0, listOf(sf("/demo/fx-reel-levels-poster.webp", "cover.jpg", "image/webp", "image"))),
            stepRun("voice", "done", 26, 2, 0.03, listOf(sf("/demo/fx-reel-levels-voice.m4a", "voice.m4a", "audio/mp4", "audio"))),
            stepRun("voice_check", "done", 24, 1, null),
            stepRun("direction", "done", 23, 6, 1.12),
            stepRun("inspire", "done", 17, 2, null),
            stepRun("build", "running", 15, 0, 1.12),
            stepRun("package", "pending", 0, 0, null), stepRun("publish", "pending", 0, 0, null), stepRun("rules", "pending", 0, 0, null), stepRun("report", "pending", 0, 0, null),
        ), null, 2.31, "ساخت ویدیو در کارگاه؛ هر کلمه و هر جمله با موشن‌گرافی و انیمه.", null)
        val yesterday = run("RN-000703", "done", 1_440 + 60, "بازپخش جلسه‌ی زنده‌ی طلا", steps.map { d ->
            val k = d.str("key")!!
            when (k) {
                "build" -> stepRun(k, "done", 1_440 + 40, 18, 1.94, listOf(sf("/demo/fx-reel-levels.mp4", "reel.mp4", "video/mp4", "video")))
                "package" -> stepRun(k, "done", 1_440 + 20, 1, null, listOf(sf("/demo/t3", "caption.txt", "text/plain", "text", caption), sf("/demo/t4", "comment.txt", "text/plain", "text", commentTxt)))
                else -> stepRun(k, "done", 1_440 + 55, 2, if (k == "direction") 1.08 else null)
            }
        }, jo("permalink" to "https://www.instagram.com/reel/Dfq-Zc4lNve/", "story_permalink" to "https://www.instagram.com/stories/pro.chart/", "comments" to 12, "dms_sent" to 9, "clicks" to 4,
            "views" to null, "reach" to null, "likes" to 87, "saves" to null, "shares" to null, "read_at" to at(30)), 3.21, "منتشر شد؛ قاعده‌های کامنت، استوری و دایرکت روشن شد.", 41.0)
        val older = run("RN-000702", "done", 2 * 1_440 + 60, "اندیکاتور RSI در یک دقیقه", emptyList(),
            jo("permalink" to "https://www.instagram.com/reel/DfmA1/", "story_permalink" to null, "comments" to 7, "dms_sent" to 6, "clicks" to 2, "views" to null, "reach" to null, "likes" to 54, "saves" to null, "shares" to null, "read_at" to at(1_400)), 3.64, "منتشر شد.", 44.0)
        val failed = run("RN-000701", "failed", 3 * 1_440 + 60, "ابزار هشدار قیمت", listOf(
            stepRun("topic", "done", 3 * 1_440 + 60, 1, 0.04), stepRun("script", "done", 3 * 1_440 + 59, 4, 0.0),
            stepRun("cover", "failed", 3 * 1_440 + 55, 9, 0.0, error = "ChatGPT سه بار تصویر نساخت؛ مرورگر کمک‌کارها از حساب بیرون افتاده بود."),
            stepRun("voice", "pending", 0, 0, null),
        ), null, 0.04, "کاور ساخته نشد؛ این نوبت منتشر نشد.", 13.0)
        mutableMapOf(today.str("ref")!! to today, yesterday.str("ref")!! to yesterday, older.str("ref")!! to older, failed.str("ref")!! to failed)
    }

    private fun runRef(r: JsonObject) = jo("ref" to r.str("ref"), "at" to r.str("at"), "state" to r.str("state"), "topic_fa" to r.str("topic_fa"), "note_fa" to r.str("note_fa"),
        "cost_usd" to ((r["cost"] as JsonObject)["usd"]), "results" to r["results"])

    private fun flowNow(): JsonObject = JsonObject(flow + ("last_run" to runRef(runs.getValue("RN-000704"))))

    private val audit = mutableListOf(
        jo("at" to at(1_500), "who_fa" to "مدیر کل", "action" to "playbook.use", "summary_fa" to "ساخته شد از «ریلز روزانه‌ی پروچارت» نسخه‌ی ۲"),
        jo("at" to at(900), "who_fa" to "مدیر کل", "action" to "automation.replies", "summary_fa" to "جواب‌های عمومی: سه جواب خود مدیر کل اول"),
        jo("at" to at(400), "who_fa" to "مدیر کل", "action" to "automation.patch", "summary_fa" to "ساعت: ثابت 18:30 ← بهترین ساعت"),
    )

    private fun boardItems(): List<JsonObject> {
        val f = flowNow()
        val last = runs.getValue("RN-000704")
        return listOf(
            jo("ref" to "AT-0700", "kind" to "flow", "title_fa" to "ریلز روزانه‌ی پروچارت", "company" to "PC", "company_fa" to "پرو-چارت", "playbook" to "PB-0004", "playbook_fa" to "ریلز روزانه‌ی پروچارت",
                "version" to 2, "when_fa" to "هر روز، بهترین ساعت", "state" to f.str("state"), "switchable" to true,
                "last" to jo("at" to last.str("at"), "state" to "running", "note_fa" to "ساخت ویدیو"), "next_at" to (f["next"] as JsonObject).str("at"), "cost_today_usd" to 2.31, "opens" to "automation/AT-0700"),
        ) + made.map { m ->
            jo("ref" to m.str("ref"), "kind" to "flow", "title_fa" to m.str("title_fa"), "company" to m.str("company"), "company_fa" to m.str("company_fa"), "playbook" to m.str("playbook"),
                "playbook_fa" to m.str("playbook_fa"), "version" to m.int("version"), "when_fa" to "هر روز، بهترین ساعت", "state" to m.str("state"), "switchable" to true,
                "last" to null, "next_at" to (m["next"] as JsonObject).str("at"), "cost_today_usd" to null, "opens" to "automation/${m.str("ref")}")
        } + listOf(
            jo("ref" to "SP:pb_1:TY", "kind" to "standing_publish", "title_fa" to "انتشار خودکار «کمپین مناسبتی»", "company" to "TY", "company_fa" to "تریدیار", "playbook" to "PB-0001", "playbook_fa" to "کمپین مناسبتی",
                "version" to 3, "when_fa" to "هر خروجی، بهترین ساعت", "state" to standing, "switchable" to true,
                "last" to jo("at" to at(1_380), "state" to "done", "note_fa" to "ریلز به @tradeyar رفت"), "next_at" to null, "cost_today_usd" to null, "opens" to "groups/pb_1"),
            jo("ref" to "AT-0902", "kind" to "routine", "title_fa" to "خلاصه‌ی روزانه‌ی رتبه‌های سئو", "company" to "PC", "company_fa" to "پرو-چارت", "playbook" to null, "playbook_fa" to null,
                "version" to null, "when_fa" to "هر روز ساعت 09:00", "state" to "on", "switchable" to true,
                "last" to jo("at" to at(600), "state" to "done", "note_fa" to "خلاصه به جلسه رفت"), "next_at" to ahead(17 * 60), "cost_today_usd" to 0.08, "opens" to "session/F-0100"),
            jo("ref" to "LN-0002", "kind" to "line", "title_fa" to "پست روزانه‌ی کانال کوینه‌پرو", "company" to "FX", "company_fa" to "کوینه‌پرو FX", "playbook" to null, "playbook_fa" to null,
                "version" to null, "when_fa" to "هر روز ساعت 09:00", "state" to line2, "switchable" to true,
                "last" to jo("at" to at(1_400), "state" to "done", "note_fa" to "در کانال منتشر شد"), "next_at" to ahead(17 * 60), "cost_today_usd" to 0.0, "opens" to "lines/LN-0002"),
            jo("ref" to "AT-0001", "kind" to "rule", "title_fa" to "ریلز آموزشی شنبه‌ها، و خبر اگر دنبال‌کننده کم شد", "company" to "TY", "company_fa" to "تریدیار", "playbook" to null, "playbook_fa" to null,
                "version" to null, "when_fa" to "هر شنبه ساعت 10:00", "state" to "on", "switchable" to true, "last" to null, "next_at" to null, "cost_today_usd" to null, "opens" to "automations/sentence"),
            jo("ref" to "AT-0002", "kind" to "rule", "title_fa" to "توقف تبلیغ کم‌بازده", "company" to "FX", "company_fa" to "کوینه‌پرو FX", "playbook" to null, "playbook_fa" to null,
                "version" to null, "when_fa" to "وقتی بازده زیر ۱٫۲ شد", "state" to "proposed", "switchable" to false, "last" to null, "next_at" to null, "cost_today_usd" to null, "opens" to "automations/sentence"),
            jo("ref" to "AU-0001", "kind" to "archive", "title_fa" to "یادآور تمدید قراردادها", "company" to null, "company_fa" to "هلدینگ", "playbook" to null, "playbook_fa" to null,
                "version" to null, "when_fa" to "سی روز پیش از پایان", "state" to archive, "switchable" to true, "last" to null, "next_at" to null, "cost_today_usd" to null, "opens" to "archive-settings"),
        )
    }
    private var standing = "on"
    private var line2 = "on"
    private var archive = "on"

    private val health = JsonArray(listOf(
        jo("key" to "n8n", "state" to "ok", "note_fa" to "هر دقیقه سر میزند"),
        jo("key" to "ighub", "state" to "ok", "note_fa" to "پاسخ میدهد"),
        jo("key" to "publish_path", "state" to "ok", "note_fa" to "مسیر هر سه شرکت ثبت است"),
        jo("key" to "helpers_browser", "state" to "warn", "note_fa" to "AI Studio از حساب بیرون است؛ صدا از API میرود"),
        jo("key" to "workshop", "state" to "ok", "note_fa" to "آخرین نوبت ۱۵ دقیقه پیش"),
    ))

    private val siteLinks = mutableMapOf(
        "PC" to jo("company" to "PC", "site" to jo("url" to "https://pro-chart.com", "title_fa" to "پرو چارت"), "sections" to JsonArray(emptyList()),
            "utm" to jo("source" to "instagram", "campaign" to "{flow}", "medium" to jo("comment" to "comment", "story" to "story", "dm" to "dm")), "updated_at" to at(900), "by_fa" to "مدیر کل"),
    )

    // ------------------------------------------------------------------- routes --
    @Synchronized
    fun handle(method: String, path: String, query: Map<String, String?>, body: JsonObject?): Pair<Int, JsonElement>? {
        // the library
        if (path == "/playbooks" && method == "GET") {
            val base = (v40.handle("GET", "/playbooks", mapOf("state" to query["state"]), null)?.second as? JsonArray)?.mapNotNull { it as? JsonObject }.orEmpty().map(::augmented)
            val mine = listOf(pb4()).filter { query["state"] == null || it.str("state") == query["state"] }
            return 200 to JsonArray(mine + base)
        }
        if (path == "/playbooks/import" && method == "POST") return 201 to JsonObject(pb4() + mapOf("ref" to JsonPrimitive("PB-0004"), "state" to JsonPrimitive("draft")))
        Regex("^/playbooks/(PB-\\d+)/(use|compare|export|copy|revise|versions)$").find(path)?.let { m ->
            val (ref, what) = m.destructured
            val pb = if (ref == "PB-0004") pb4() else (v40.handle("GET", "/playbooks/$ref", emptyMap(), null)?.second as? JsonObject)?.let(::augmented)
                ?: return 404 to problem(404, "not_found", "این کارگروه پیدا نشد.")
            return when (what) {
                "versions" -> 200 to (pb["versions"] ?: JsonArray(emptyList()))
                "compare" -> 200 to jo("a" to (query["a"]?.toIntOrNull() ?: 1), "b" to (query["b"]?.toIntOrNull() ?: 2), "changes" to JsonArray(listOf(
                    jo("part" to "step", "key" to "voice_check", "kind" to "added", "before_fa" to null, "after_fa" to "بازبینی صدا"),
                    jo("part" to "step", "key" to "inspire", "kind" to "changed", "before_fa" to "الهام پیش از کارگردانی", "after_fa" to "الهام"),
                    jo("part" to "rule", "key" to "build", "kind" to "added", "before_fa" to null, "after_fa" to "رندر با حداکثر ۲ پردازش"),
                    jo("part" to "lesson", "key" to "18", "kind" to "added", "before_fa" to null, "after_fa" to "کاور ساخته نشد"),
                )))
                "export" -> 200 to jo("format" to "coinepro.playbook/1", "version" to pb.int("version"), "exported_at" to now.toString(), "playbook" to JsonObject(pb.filterKeys {
                    it in setOf("title_fa", "purpose_fa", "platform", "seats", "steps", "package", "routines", "kpis", "connections", "rules_fa", "lessons")
                }))
                "revise" -> {
                    if (method != "POST") return null
                    if (ref != "PB-0004") return 409 to problem(409, "validation_failed", "این کارگروه هنوز نسخه ندارد.")
                    if (draft3 == null) draft3 = jo("version" to 3)
                    201 to JsonObject(pb4(2) + mapOf("version" to JsonPrimitive(3), "state" to JsonPrimitive("draft"), "draft_version" to JsonPrimitive(3)))
                }
                "copy" -> {
                    if (method != "POST") return null
                    val copy = JsonObject(pb + mapOf("ref" to JsonPrimitive("PB-0004"), "state" to JsonPrimitive("draft"), "platform" to (body?.get("platform") ?: JsonPrimitive("youtube"))))
                    200 to jo("playbook" to copy, "member" to null, "order" to null, "conversation" to null)
                }
                else -> use(pb, body ?: JsonObject(emptyMap()))
            }
        }
        Regex("^/playbooks/PB-0004/members/([A-Z]{2,5})/version$").find(path)?.let { m ->
            if (method != "PUT") return null
            return 200 to jo("company" to m.groupValues[1], "name_fa" to "پرو-چارت", "state" to "on", "order" to "F-0094", "version" to body?.int("version"), "automation" to "AT-0700",
                "publish" to jo("mode" to "auto", "account" to "pro.chart", "story" to true, "since" to at(1_500), "at" to null, "best" to true))
        }
        if (path == "/playbooks/PB-0004") {
            if (method == "GET") {
                val v = query["version"]?.toIntOrNull()
                return 200 to if (v == 3 && draft3 != null) JsonObject(pb4(2) + mapOf("version" to JsonPrimitive(3), "state" to JsonPrimitive("draft"))) else pb4(v ?: 2)
            }
            return 409 to problem(409, "validation_failed", "این نسخه مُهر شده؛ تغییر، نسخه‌ی تازه میسازد.")
        }
        if (path == "/narrators/sample" && method == "POST") return 200 to jo("file" to jo("id" to "/demo/voice/piper-gyro-numbers.m4a", "name" to "sample.m4a", "mime" to "audio/mp4", "size" to 90_000, "sha256" to "demo", "kind" to "audio"))
        Regex("^/companies/([A-Z]{2,5})/site-links$").find(path)?.let { m ->
            val code = m.groupValues[1]
            if (method == "PUT" && body != null) { siteLinks[code] = JsonObject(body + mapOf("company" to JsonPrimitive(code), "updated_at" to JsonPrimitive(now.toString()), "by_fa" to JsonPrimitive("مدیر کل"))) }
            return 200 to (siteLinks[code] ?: jo("company" to code, "site" to jo("url" to "", "title_fa" to ""), "sections" to JsonArray(emptyList()),
                "utm" to jo("source" to "instagram", "campaign" to "{flow}", "medium" to jo("comment" to "comment", "story" to "story", "dm" to "dm")), "updated_at" to null, "by_fa" to null))
        }
        // the automations
        if (path == "/automations/board" && method == "GET") {
            val items = boardItems().filter { query["kind"] == null || it.str("kind") == query["kind"] }.filter { query["company"] == null || it.str("company") == query["company"] }
            return 200 to jo("items" to JsonArray(items), "health" to health, "today" to jo("runs" to 3, "published" to 1, "cost_usd" to 2.39))
        }
        if (path == "/automations/today" && method == "GET") return 200 to jo(
            "day" to LocalDate.now(tehran).toString(), "line_fa" to "امروز: ریلز «بازپخش جلسه‌ی زنده‌ی طلا» منتشر شد، ۱۲ کامنت، ۹ دایرکت، ۴ کلیک",
            "items" to JsonArray(listOf(jo("automation" to "AT-0700", "title_fa" to "ریلز روزانه‌ی پروچارت", "company_fa" to "پرو-چارت", "state" to "done",
                "published" to JsonArray(listOf(jo("kind" to "reel", "url" to "https://www.instagram.com/reel/Dfq-Zc4lNve/"))), "comments" to 12, "dms_sent" to 9, "clicks" to 4, "cost_usd" to 3.21, "note_fa" to ""))),
            "cost_usd" to 3.21,
        )
        if (path == "/automations/calendar" && method == "GET") {
            val start = LocalDate.now(tehran)
            return 200 to jo("days" to JsonArray((0..13).map { d ->
                val day = start.plusDays(d.toLong())
                val t = day.atTime(19, 0).atZone(tehran).toInstant().toString()
                jo("day" to day.toString(), "items" to JsonArray(listOf(jo("ref" to "AT-0700", "at" to t, "title_fa" to "ریلز روزانه‌ی پروچارت", "company_fa" to "پرو-چارت",
                    "topic_fa" to when (d) { 0 -> "سه خطای رایج در کشیدن خط روند"; 1 -> "سطح‌های حمایت در یک دقیقه"; else -> null },
                    "state" to if (d == 0) "running" else "planned"))))
            }))
        }
        Regex("^/automations/(AT-07\\d\\d|SP:[^/]+|LN-0002|AU-0001|AT-0001)(?:/(state|run-now|pause|skip|runs|audit|replies|replies/preview))?$").find(path)?.let { m ->
            val (ref, what) = m.destructured
            if (ref == "AT-0001" && what != "state") return null
            if (what == "state" && method == "POST") {
                val on = body?.str("state") == "on"
                when {
                    ref == "AT-0700" -> flow = JsonObject(flow + ("state" to JsonPrimitive(if (on) "on" else "off")))
                    ref.startsWith("SP:") -> standing = if (on) "on" else "off"
                    ref == "LN-0002" -> line2 = if (on) "on" else "off"
                    ref == "AU-0001" -> archive = if (on) "on" else "off"
                    ref == "AT-0001" -> return null
                    else -> made.replaceAll { if (it.str("ref") == ref) JsonObject(it + ("state" to JsonPrimitive(if (on) "on" else "off"))) else it }
                }
                audit.add(0, jo("at" to now.toString(), "who_fa" to "مدیر کل", "action" to "automation.state", "summary_fa" to if (on) "روشن شد" else "خاموش شد"))
                return 200 to jo("ref" to ref, "state" to if (on) "on" else "off")
            }
            if (ref != "AT-0700" && made.none { it.str("ref") == ref }) return null
            val cur = if (ref == "AT-0700") flowNow() else made.first { it.str("ref") == ref }
            return when (what) {
                "" -> when (method) {
                    "GET" -> 200 to cur
                    "PATCH" -> {
                        val given = (body ?: JsonObject(emptyMap())).filterKeys { it in setOf("schedule", "account", "story", "mode", "budget", "title_fa") }
                        val merged = JsonObject(cur + given.mapValues { (k, v) ->
                            when (k) {
                                "schedule" -> JsonObject((cur["schedule"] as JsonObject) + (v as JsonObject) + ("when_fa" to JsonPrimitive("")))
                                "budget" -> JsonObject((cur["budget"] as JsonObject) + (v as JsonObject))
                                else -> v
                            }
                        })
                        if (ref == "AT-0700") flow = merged
                        audit.add(0, jo("at" to now.toString(), "who_fa" to "مدیر کل", "action" to "automation.patch", "summary_fa" to "تنظیم عوض شد: ${given.keys.joinToString("، ")}"))
                        200 to merged
                    }
                    else -> null
                }
                "run-now" -> 201 to runRef(runs.getValue("RN-000704"))
                "pause" -> { val o = JsonObject(cur + mapOf("state" to JsonPrimitive("paused"), "paused_until" to (body?.get("until") ?: JsonNull))); if (ref == "AT-0700") flow = o; 200 to o }
                "skip" -> {
                    val skip = (body?.get("skip") as? JsonPrimitive)?.booleanOrNull ?: true
                    val at = body?.str("at")
                    val up = (cur["upcoming"] as JsonArray).map { o -> o as JsonObject; if (at == null || o.str("at") == at) JsonObject(o + ("skip" to JsonPrimitive(skip))) else o }
                    val next = (cur["next"] as? JsonObject)?.let { n -> if (at == null || n.str("at") == at) JsonObject(n + ("skip" to JsonPrimitive(skip))) else n }
                    val o = JsonObject(cur + mapOf("upcoming" to JsonArray(up), "next" to (next ?: JsonNull)))
                    if (ref == "AT-0700") flow = o
                    200 to o
                }
                "runs" -> 200 to jo("items" to JsonArray(if (ref == "AT-0700") runs.values.sortedByDescending { it.str("at") }.map(::runRef) else emptyList()), "next_cursor" to null)
                "audit" -> 200 to JsonArray(audit)
                "replies" -> {
                    if (method != "PUT" || body == null) return null
                    val o = JsonObject(cur + ("replies" to body))
                    if (ref == "AT-0700") flow = o
                    audit.add(0, jo("at" to now.toString(), "who_fa" to "مدیر کل", "action" to "automation.replies", "summary_fa" to "جواب‌ها عوض شد"))
                    200 to o
                }
                "replies/preview" -> {
                    val r = cur["replies"] as JsonObject
                    val own = (r["public_pool"] as JsonArray).mapNotNull { (it as? JsonPrimitive)?.contentOrNull }
                    val pool = (own + POOL.filter { it !in own }).take(maxOf(10, own.size))
                    val dm = (r["dm_template"] as JsonObject)
                    200 to jo("dm" to jo("text" to (dm.str("text_fa") ?: "").replace("{topic}", "آموزش خط روند"),
                        "buttons" to JsonArray((dm["buttons"] as JsonArray).map { b -> jo("title" to (b as JsonObject).str("title_fa"), "url" to "https://pro-chart.com/?utm_source=instagram&utm_medium=dm&utm_campaign=at-0700") })),
                        "public" to strs(*pool.toTypedArray()), "comment_fa" to "هر ویدیو خودش انتخاب میکند؛ امروز «هر کامنتی»",
                        "story_fa" to "با کلمه‌ی «روند»", "dm_fa" to "با کلمه‌ی «روند»")
                }
                else -> null
            }
        }
        Regex("^/line-runs/(RN-0007\\d\\d)(/rerun|/cancel)?$").find(path)?.let { m ->
            val r = runs[m.groupValues[1]] ?: return 404 to problem(404, "not_found", "این اجرا پیدا نشد.")
            return when (m.groupValues[2]) {
                "" -> 200 to r
                "/rerun" -> 201 to runs.getValue("RN-000704")
                "/cancel" -> { val o = JsonObject(r + mapOf("state" to JsonPrimitive("skipped"), "note_fa" to JsonPrimitive("این نوبت رد شد؛ موضوعش آزاد شد."))); runs[r.str("ref")!!] = o; 200 to o }
                else -> null
            }
        }
        return null
    }

    private fun use(pb: JsonObject, body: JsonObject): Pair<Int, JsonElement> {
        val code = body.str("company") ?: return 422 to problem(422, "validation_failed", "شرکت را انتخاب کن.")
        val name = mapOf("TY" to "تریدیار", "FX" to "کوینه‌پرو FX", "PC" to "پرو-چارت")[code] ?: code
        if ((pb["members"] as? JsonArray)?.any { (it as JsonObject).str("company") == code } == true) return 409 to problem(409, "validation_failed", "این شرکت همین کارگروه را دارد.")
        val accounts = (body["accounts"] as? JsonArray)?.mapNotNull { (it as? JsonPrimitive)?.contentOrNull }.orEmpty()
        if (code == "FX" && accounts.isEmpty()) return 422 to JsonObject(problem(422, "validation_failed", "این شرکت چند حساب دارد؛ یکی را انتخاب کن.") + ("fields" to jo("accounts" to "one of: @coineprofx, @coineprofx.academy")))
        val time = body["time"] as? JsonObject
        val hour = if (time?.str("mode") == "fixed") "ساعت ${time.str("at")}" else "در بهترین ساعت حساب"
        if ((body["dry"] as? JsonPrimitive)?.booleanOrNull == true) return 200 to jo(
            "lines_fa" to strs(
                "n8n ساعت شروع را میزند؛ موضوع تازه از دفتر موضوع‌های $name.", "متن و کاور با ChatGPT؛ صدا با گوینده‌ی $name.", "ساخت ویدیو در کارگاه با Opus 5.5.",
                "ریلز${if (time?.get("story")?.let { (it as JsonPrimitive).booleanOrNull } != false) " و استوری" else ""} $hour به ${accounts.firstOrNull()?.let { "@$it" } ?: "حساب ثبت‌شده‌ی $name"} میرود.",
                "قاعده‌های کامنت، استوری و دایرکت با لینک‌های $name روشن میشود.", "ساعت ۲۱:۳۰ یک خط گزارش برای تو.",
            ),
            "first_at" to ahead(20 * 60), "cost_estimate_usd" to 3.4,
            "warnings" to JsonArray(listOf(jo("key" to "seat", "text_fa" to "$name موشن‌دیزاینر ندارد؛ در سقف پاکت استخدام میشود.", "by_hub" to true),
                jo("key" to "aistudio", "text_fa" to "صفحه‌ی AI Studio از حساب بیرون است؛ صدا از API میرود.", "by_hub" to true))),
        )
        val ref = "AT-%04d".format(autoSeq++)
        val auto = JsonObject(flow + mapOf("ref" to JsonPrimitive(ref), "company" to JsonPrimitive(code), "company_fa" to JsonPrimitive(name), "playbook" to JsonPrimitive(pb.str("ref")),
            "playbook_fa" to JsonPrimitive(pb.str("title_fa")), "title_fa" to JsonPrimitive("${pb.str("title_fa")} · $name"), "account" to (accounts.firstOrNull()?.let(::JsonPrimitive) ?: JsonNull),
            "mode" to JsonPrimitive(body.str("mode") ?: "auto"), "today" to jo("runs" to 0, "cost_usd" to 0.0), "last_run" to JsonNull))
        made += auto
        val member = jo("company" to code, "name_fa" to name, "state" to "on", "order" to null, "version" to pb.int("version"), "automation" to ref,
            "publish" to jo("mode" to (body.str("mode") ?: "auto"), "account" to accounts.firstOrNull(), "story" to true, "since" to now.toString(), "at" to null, "best" to (time?.str("mode") != "fixed")))
        return 201 to jo("playbook" to JsonObject(pb + ("members" to JsonArray(((pb["members"] as? JsonArray).orEmpty()) + member))), "member" to member, "automation" to auto)
    }

    companion object {
        private val POOL = listOf(
            "برو دایرکتت رو چک کن، فرستادم برات؛ موفق باشی 🤍", "فرستادم! یه سر به دایرکتت بزن 🙌", "دایرکتت رو ببین، همه‌چی اون‌جاست 💌",
            "برات ارسال شد ✅ امیدوارم به کارت بیاد 🌱", "توی دایرکت منتظرته 🎁 روز خوبی داشته باشی", "ارسال شد 🚀 دایرکت رو چک کن",
            "لینکش آماده‌ست، توی دایرکتته 🔗💛", "حله! برات فرستادیم 😊 دایرکت رو ببین", "جوابت رفت توی دایرکت 📬 ممنون که همراهمونی",
            "دایرکتت رو باز کن، یه چیز خوب برات فرستادیم ✨",
        )
    }

    private fun strs(vararg s: String) = JsonArray(s.map(::JsonPrimitive))
    private fun JsonObject.str(k: String): String? = (this[k] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull
    private fun JsonObject.int(k: String): Int? = (this[k] as? JsonPrimitive)?.contentOrNull?.toIntOrNull()
    private fun jo(vararg kv: Pair<String, Any?>): JsonObject = JsonObject(kv.associate { (k, v) ->
        k to when (v) {
            null -> JsonNull; is JsonElement -> v; is String -> JsonPrimitive(v); is Number -> JsonPrimitive(v); is Boolean -> JsonPrimitive(v)
            else -> error("unsupported ${v::class}")
        }
    })
    private fun problem(status: Int, code: String, fa: String) = jo("code" to code, "message_fa" to fa, "status" to status, "title" to code, "type" to "about:blank")
}
