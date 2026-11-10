package com.coinepro.hq

import com.coinepro.hq.core.format.HqClock
import java.time.temporal.ChronoUnit
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull

/**
 * Debug builds only: contract §40 ⟨1.22⟩, a session becomes a working group the owner can give to any company or platform.
 *
 * - **The library:** PB-0002 «سئوی هفتگی سایت», a draft from F-0104 (Pro-Chart's SEO session: a seat the drafter dropped, said in
 *   `note_fa`); PB-0001 «کمپین مناسبتی», sealed from F-0098 (TradeYar's Nowruz campaign), at work in TradeYar and paused in CoinePro FX;
 *   PB-0003 «نگهبان هویت بصری», retired.
 * - **In F-0104's talk:** the owner asks for a working group, the holder posts the draft's card (`{playbook}`); then the owner asks for
 *   DeepSeek beside the writer and the holder offers the rewrite (`{playbook, draft}`), which «اجرا کن» stores.
 * - **Routes:** `POST /orders/{ref}/playbook` drafts one from any session (its people as seats, the models in it as helpers) and posts
 *   its card; `PATCH` (a draft only), `seal`, `apply` (as is: a membership; else a new session for that company, F-0106…, opened from the
 *   playbook) and `retire`, with the hub's refusals (409) where it refuses.
 */
internal class V40Demo(private val v35: V35Demo) {
    private val now = HqClock.now()
    private fun at(minAgo: Long): String = now.minus(minAgo, ChronoUnit.MINUTES).toString()

    private val names = mapOf("TY" to "تریدیار", "FX" to "کوینه‌پرو FX", "PC" to "پرو-چارت", "HQ" to "هلدینگ کوینه‌پرو")

    private fun seat(seat: String, role: String, title: String, duties: String, vararg helpers: String) =
        jo("seat" to seat, "role" to role, "title_fa" to title, "duties_fa" to duties, "helpers" to JsonArray(helpers.map(::JsonPrimitive)), "model" to null)
    private fun routine(key: String, title: String, seat: String, rrule: String, brief: String) =
        jo("key" to key, "title_fa" to title, "seat" to seat, "schedule" to rrule, "brief_md" to brief, "max_tokens" to 40000)
    private fun member(code: String, state: String, order: String? = null, publish: JsonObject = word(false)) =
        jo("company" to code, "name_fa" to names[code], "state" to state, "order" to order, "publish" to publish)
    /** ⟨0.19.9⟩ §45 the owner's standing word on publishing, as the hub answers it. */
    private fun word(auto: Boolean, account: String? = null, story: Boolean = false, hour: String? = null, best: Boolean = false) =
        jo("mode" to if (auto) "auto" else "ask", "account" to account.takeIf { auto }, "story" to (auto && story), "since" to if (auto) at(13_000) else null,
            // ⟨1.31⟩ §49 the hub chooses the hour itself; the fixed one is what it falls back on
            "at" to hour.takeIf { auto }, "best" to (auto && best))
    /** The Instagram accounts each company registered (FX has two: the standing word asks which). */
    private val accounts = mapOf("TY" to listOf("tradeyar"), "FX" to listOf("coineprofx", "coineprofx.academy"), "PC" to listOf("pro.chart"))
    private fun wordOf(code: String, body: JsonObject?): Pair<JsonObject?, String?> {
        val p = body?.get("publish") as? JsonObject ?: body?.takeIf { it["mode"] != null } ?: return null to null
        if (p.str("mode") != "auto") return word(false) to null
        val mine = accounts[code].orEmpty()
        val asked = p.str("account")?.removePrefix("@") ?: mine.singleOrNull()
        if (mine.isNotEmpty() && asked !in mine) return null to ("one of: " + mine.joinToString(", ") { "@$it" })
        return word(true, asked, (p["story"] as? JsonPrimitive)?.booleanOrNull == true, p.str("at"), (p["best"] as? JsonPrimitive)?.booleanOrNull == true) to null
    }
    private fun strs(vararg s: String) = JsonArray(s.map(::JsonPrimitive))

    private val seoWriter = seat("writer", "content_writer", "نویسنده‌ی مقاله", "هفته‌ای دو مقاله‌ی آموزشی؛ موضوع را با ChatGPT پیدا میکند.", "gpt")

    /** The library, newest first (as the hub sends it). */
    private val books = mutableListOf(
        jo(
            "ref" to "PB-0002", "title_fa" to "سئوی هفتگی سایت",
            "purpose_fa" to "هر هفته رقبای «چارت طلا» بررسی شوند، صفحه‌های عقب‌مانده بهتر شوند و دو مقاله‌ی تازه منتشر شود تا سایت در جستجو بالا بماند.",
            "state" to "draft", "version" to 2, "platform" to "site",
            "seats" to JsonArray(listOf(
                seat("seo", "seo_specialist", "کارشناس سئو", "هر شنبه سه رقیب اول را بررسی میکند و فهرست صفحه‌هایی را که باید بهتر شوند مینویسد.", "gemini"),
                seoWriter,
                seat("lead", "ceo", "مدیرعامل پرو-چارت", "برنامه‌ی هفته و تأیید نهایی هر مقاله پیش از انتشار."),
            )),
            "routines" to JsonArray(listOf(
                routine("rivals", "بررسی رقبا", "seo", "FREQ=WEEKLY;BYDAY=SA;BYHOUR=9;BYMINUTE=0",
                    "سه رقیب اول جستجوی «چارت طلا» را ببین و بنویس:\n- جایگاه هر کدام این هفته\n- صفحه‌ی تازه‌ای که ساخته‌اند\n- یک صفحه‌ی ما که باید بهتر شود، با دلیلش"),
                routine("article", "مقاله‌ی آموزشی", "writer", "FREQ=WEEKLY;BYDAY=MO,TH;BYHOUR=10;BYMINUTE=30",
                    "یک مقاله‌ی آموزشی درباره‌ی چارت طلا، دست‌کم ۱۲۰۰ کلمه، با منبع؛ عددهای بازار با رقم لاتین."),
                routine("ranks", "گزارش رتبه‌ها", "lead", "FREQ=WEEKLY;BYDAY=FR;BYHOUR=18;BYMINUTE=0",
                    "رتبه‌ی «چارت طلا» و سه عبارت دیگر را با هفته‌ی قبل بسنج؛ سه خط برای مدیر کل."),
            )),
            "kpis" to JsonArray(listOf(
                jo("key" to "rank", "title_fa" to "جایگاه «چارت طلا» در گوگل", "source" to "search_console", "unit" to ""),
                jo("key" to "visits", "title_fa" to "بازدید از جستجو", "source" to "search_console", "unit" to "بازدید"),
            )),
            "connections" to strs("search_console", "ga4"),
            "rules_fa" to strs("عددهای بازار با رقم لاتین نوشته شوند.", "هیچ مقاله‌ای بدون منبع منتشر نشود.", "پیش از انتشار، مدیرعامل متن را تأیید کند."),
            "source" to jo("order" to "F-0104", "company" to "PC", "conversation" to "CV-0504"),
            "members" to JsonArray(emptyList()), "parent" to null, "created_at" to at(50), "sealed_at" to null, "retired_at" to null, "group" to null,
            "note_fa" to "جایگاه «طراح کاور» کنار رفت: در پرو-چارت چنین نقشی تعریف نشده است.",
        ),
        jo(
            "ref" to "PB-0001", "title_fa" to "کمپین مناسبتی",
            "purpose_fa" to "برای هر مناسبت یک کمپین کوتاه روی اینستاگرام: موضوع هر روز، کاور هر پست، سه ریلز در هفته و گزارش پایان هفته.",
            "state" to "sealed", "version" to 3, "platform" to "instagram",
            "seats" to JsonArray(listOf(
                seat("writer", "content_writer", "نویسنده‌ی محتوا", "موضوع هر روز کمپین را با ChatGPT پیدا میکند و متن ریلز و استوری را مینویسد.", "gpt"),
                seat("designer", "designer", "طراح کاور", "کاور و تصویر هر پست را با Gemini در AI Studio میسازد.", "gemini", "aistudio"),
                seat("media", "media_manager", "مدیر رسانه", "زمان انتشار، استوری‌ها و جواب پیام‌ها.", "deepseek"),
            )),
            "routines" to JsonArray(listOf(
                routine("topic", "موضوع روز", "writer", "FREQ=DAILY;BYHOUR=9;BYMINUTE=0", "موضوع امروز کمپین را پیدا کن و متن یک ریلز و یک استوری بنویس."),
                routine("cover", "کاور روز", "designer", "FREQ=DAILY;BYHOUR=11;BYMINUTE=0", "برای متن امروز یک کاور در قاب ۹ به ۱۶ بساز، با رنگ‌های شرکت."),
                routine("reels", "انتشار ریلز", "media", "FREQ=WEEKLY;BYDAY=SA,MO,WE;BYHOUR=18;BYMINUTE=30", "ریلز آماده را منتشر کن و استوری‌اش را بگذار."),
                routine("weekly", "گزارش هفته", "media", "FREQ=WEEKLY;BYDAY=FR;BYHOUR=20;BYMINUTE=0", "دیده‌شدن هر ریلز و پیام‌های رسیده؛ سه خط."),
            )),
            "kpis" to JsonArray(listOf(jo("key" to "reach", "title_fa" to "دیده‌شدن ریلزها", "source" to "instagram", "unit" to "نفر"))),
            "connections" to strs("instagram"),
            "rules_fa" to strs("هر ریلز زیر ۴۵ ثانیه.", "عددهای بازار با رقم لاتین.", "هیچ پیشنهاد ویژه‌ای بی مُهر مدیر کل منتشر نشود."),
            "source" to jo("order" to "F-0098", "company" to "TY", "conversation" to "CV-0598"),
            "members" to JsonArray(listOf(member("TY", "on", "F-0098", word(true, "tradeyar", story = true, hour = "18:30", best = true)), member("FX", "paused"))),
            "parent" to null, "created_at" to at(14_500), "sealed_at" to at(13_000), "retired_at" to null, "group" to "pb_1", "note_fa" to null,
        ),
        jo(
            "ref" to "PB-0003", "title_fa" to "نگهبان هویت بصری",
            "purpose_fa" to "هر خروجی تصویری شرکت‌ها پیش از انتشار با راهنمای هویت بصری هلدینگ سنجیده شود.",
            "state" to "retired", "version" to 1, "platform" to "any",
            "seats" to JsonArray(listOf(seat("brand", "designer", "طراح ارشد", "هر کاور را با راهنمای رنگ و لوگو میسنجد.", "aistudio"))),
            "routines" to JsonArray(listOf(routine("check", "بازبینی روزانه", "brand", "FREQ=DAILY;BYHOUR=17;BYMINUTE=0", "کاورهای امروز همه‌ی شرکت‌ها را با راهنما بسنج."))),
            "kpis" to JsonArray(emptyList()), "connections" to JsonArray(emptyList()), "rules_fa" to strs("لوگو هرگز کشیده یا رنگی دیگر نشود."),
            "source" to jo("order" to "F-0099", "company" to "HQ", "conversation" to "CV-0599"),
            "members" to JsonArray(listOf(member("TY", "paused"))),
            "parent" to null, "created_at" to at(43_000), "sealed_at" to at(40_000), "retired_at" to at(4_300), "group" to "pb_3", "note_fa" to null,
        ),
    )
    private var seq = 4
    private var cardSeq = 403

    init {
        // F-0104's talk: the draft's card, then the owner's word and the holder's rewrite of the draft with it.
        val rewrite = JsonObject(draftOf(find("PB-0002")!!) + ("seats" to JsonArray(listOf(
            seat("seo", "seo_specialist", "کارشناس سئو", "هر شنبه سه رقیب اول را بررسی میکند و فهرست صفحه‌هایی را که باید بهتر شوند مینویسد.", "gemini"),
            seat("writer", "content_writer", "نویسنده‌ی مقاله", "هفته‌ای دو مقاله‌ی آموزشی؛ موضوع را با ChatGPT پیدا میکند و DeepSeek متنش را میسنجد.", "gpt", "deepseek"),
            seat("lead", "ceo", "مدیرعامل پرو-چارت", "برنامه‌ی هفته و تأیید نهایی هر مقاله پیش از انتشار."),
        ))))
        v35.append("F-0104", listOf(
            Triple("owner", "از این جلسه یک کارگروه بساز که هر هفته همین کار را تکرار کند.", 60L to emptyList()),
            Triple(null, "کارگروه از این جلسه آماده است؛ بازش کن، اگر خواستی ویرایش کن و مُهر بزن.", 50L to listOf(card("TC-401", "PB-0002", "سئوی هفتگی سایت", null))),
            Triple("owner", "نویسنده‌ی مقاله با DeepSeek هم متنش را بسنجد.", 20L to emptyList()),
            Triple(null, "پیش‌نویس را این‌طور عوض کردم؛ اگر درست است بزن تا ثبت شود.", 18L to listOf(card("TC-402", "PB-0002", "سئوی هفتگی سایت", rewrite))),
        ))
    }

    private fun card(id: String, pb: String, title: String, draft: JsonObject?) = jo(
        "id" to id, "turn" to null, "kind" to "playbook", "title_fa" to "کارگروه از این جلسه: $title",
        "body_fa" to (find(pb)?.str("purpose_fa") ?: ""),
        "payload" to JsonObject(listOfNotNull("playbook" to JsonPrimitive(pb), draft?.let { "draft" to it }).toMap()),
        "state" to "offered", "made" to JsonArray(emptyList()), "reason_fa" to null,
    )

    /** A playbook's fields a draft (PATCH, the holder's rewrite) may carry. */
    private fun draftOf(pb: JsonObject) = JsonObject(pb.filterKeys { it in EDITABLE })

    private fun find(ref: String): JsonObject? = books.firstOrNull { it.str("ref") == ref }
    private fun put(pb: JsonObject): JsonObject { books[books.indexOfFirst { it.str("ref") == pb.str("ref") }] = pb; return pb }

    // -------------------------------------------------------------- routes --
    @Synchronized
    fun handle(method: String, path: String, query: Map<String, String?>, body: JsonObject?): Pair<Int, JsonElement>? {
        Regex("^/orders/(F-\\d+)/playbook$").find(path)?.let { m ->
            if (method != "POST") return null
            val s = v35.look(m.groupValues[1]) ?: return 404 to problem(404, "not_found", "این جلسه پیدا نشد.")
            Thread.sleep(900) // the holder's model writes the draft
            return 201 to draft(s)
        }
        if (path == "/playbooks" && method == "GET") return 200 to JsonArray(books.filter { query["state"] == null || it.str("state") == query["state"] })
        Regex("^/talk/cards/(TC-4\\d\\d)/(run|dismiss)$").find(path)?.let { m ->
            if (method != "POST") return null
            val c = v35.card(m.groupValues[1])?.takeIf { it.str("kind") == "playbook" } ?: return null
            val p = c["payload"] as JsonObject
            val ref = p.str("playbook").orEmpty()
            val done = m.groupValues[2] == "run"
            if (done) (p["draft"] as? JsonObject)?.let { d ->
                val pb = find(ref) ?: return 404 to problem(404, "not_found", "این کارگروه پیدا نشد.")
                if (pb.str("state") != "draft") return 409 to problem(409, "validation_failed", "این کارگروه مُهر شده است؛ پیش‌نویسش دیگر عوض نمیشود.")
                put(edited(pb, d))
            }
            val upd = JsonObject(c + mapOf("state" to JsonPrimitive(if (done) "done" else "dismissed"), "made" to JsonArray(if (done) listOf(JsonPrimitive(ref)) else emptyList())))
            v35.setCard(c.str("id")!!, upd)
            return 200 to jo("made" to upd["made"], "card" to upd)
        }
        // ⟨0.19.9⟩ §45 the owner's standing word for one member of a playbook's group
        Regex("^/groups/(pb_\\d+)/members/([A-Z]{2,5})/publish$").find(path)?.let { g ->
            if (method != "PUT") return null
            val (key, code) = g.destructured
            val pb = books.firstOrNull { it.str("group") == key } ?: return 404 to problem(404, "not_found", "این کارگروه پیدا نشد.")
            val mine = (pb["members"] as JsonArray).map { it as JsonObject }.firstOrNull { it.str("company") == code }
                ?: return 404 to problem(404, "not_found", "این شرکت عضو این کارگروه نیست.")
            val (said, refused) = wordOf(code, body)
            if (refused != null) return 422 to pick(refused)
            val next = JsonObject(mine + ("publish" to (said ?: word(false))))
            put(JsonObject(pb + ("members" to JsonArray((pb["members"] as JsonArray).map { if ((it as JsonObject).str("company") == code) next else it }))))
            return 200 to jo("group" to key, "company" to code, "state" to mine.str("state"), "joined_at" to at(13_000), "seats" to JsonArray(emptyList()), "publish" to next["publish"])
        }
        val m = Regex("^/playbooks/(PB-\\d+)(/[a-z]+)?$").find(path) ?: return null
        val pb = find(m.groupValues[1]) ?: return 404 to problem(404, "not_found", "این کارگروه پیدا نشد.")
        val ref = pb.str("ref")!!
        val state = pb.str("state")
        return when (m.groupValues[2].removePrefix("/")) {
            "" -> when (method) {
                "GET" -> 200 to pb
                "PATCH" -> {
                    if (state != "draft") return 409 to problem(409, "validation_failed", "این کارگروه مُهر شده است؛ پیش‌نویسش دیگر عوض نمیشود.")
                    val given = (body ?: JsonObject(emptyMap())).filterKeys { it in EDITABLE }.filterValues { it !is JsonNull }
                    if (given.isEmpty()) return 422 to problem(422, "validation_failed", "چیزی برای تغییر داده نشد.")
                    200 to put(edited(pb, JsonObject(given)))
                }
                else -> null
            }
            "seal" -> {
                if (method != "POST") return null
                if (state != "draft") return 409 to problem(409, "validation_failed", "فقط پیش‌نویس مُهر میشود.")
                val src = (pb["source"] as JsonObject)
                val first = src.str("company")?.takeIf { it != "HQ" }?.let { listOf(member(it, "on", src.str("order"), wordOf(it, body).first ?: word(false))) }.orEmpty()
                200 to put(JsonObject(pb + mapOf(
                    "state" to JsonPrimitive("sealed"), "sealed_at" to JsonPrimitive(now.toString()), "group" to JsonPrimitive("pb_" + ref.removePrefix("PB-").trimStart('0')),
                    "members" to JsonArray(first),
                )))
            }
            "apply" -> {
                if (method != "POST") return null
                if (state == "retired") return 409 to problem(409, "validation_failed", "این کارگروه بازنشسته شده است.")
                val code = body?.str("company").orEmpty()
                val name = names[code]?.takeIf { code != "HQ" } ?: return 404 to problem(404, "not_found", "این شرکت را نمیشناسم.")
                if ((body?.get("as_is") as? JsonPrimitive)?.booleanOrNull == true) {
                    if (state != "sealed") return 409 to problem(409, "validation_failed", "عضویت مستقیم فقط برای کارگروه مُهرشده است؛ این یکی را اول مُهر بزنید.")
                    val (said, refused) = wordOf(code, body)
                    if (refused != null) return 422 to pick(refused)
                    val joined = member(code, "on", publish = said ?: word(false))
                    val members = (pb["members"] as JsonArray).filter { (it as JsonObject).str("company") != code } + joined
                    val out = put(JsonObject(pb + ("members" to JsonArray(members))))
                    return 200 to jo("playbook" to out, "member" to joined, "order" to null, "conversation" to null)
                }
                val platform = body?.str("platform")
                val where = platform?.let { " روی ${PLATFORM_FA[it] ?: it}" }.orEmpty()
                val note = body?.str("note_fa")?.trim()?.ifBlank { null }?.let { ": $it" }.orEmpty()
                // The owner's first word there: his line, then the playbook as Markdown (as the hub's `PB.apply_text` writes it).
                val text = buildString {
                    append("این کارگروه را برای $name$where پیاده کن$note\n\n# کارگروه $ref: ${pb.str("title_fa")}\n\n${pb.str("purpose_fa")}\n\n")
                    append("پلتفرم: ${PLATFORM_FA[pb.str("platform")] ?: pb.str("platform")}\n\n## جایگاه‌ها\n")
                    for (s in (pb["seats"] as JsonArray).map { it as JsonObject }) {
                        val helpers = (s["helpers"] as JsonArray).mapNotNull { (it as? JsonPrimitive)?.contentOrNull?.let { h -> HELPER[h] } }
                        append("- ${s.str("title_fa")}${if (helpers.isEmpty()) "" else " (با ${helpers.joinToString("، ")})"}: ${s.str("duties_fa")}\n")
                    }
                    append("\n## قاعده‌ها\n")
                    for (r in (pb["rules_fa"] as JsonArray)) append("- ${(r as JsonPrimitive).content}\n")
                }.trim()
                val (order, cv) = v35.openFrom(ref, pb.str("title_fa").orEmpty(), code, name, text)
                200 to jo("playbook" to pb, "member" to null, "order" to order, "conversation" to cv)
            }
            "retire" -> {
                if (method != "POST") return null
                if (state == "retired") return 409 to problem(409, "validation_failed", "این کارگروه پیش از این بازنشسته شده است.")
                val members = (pb["members"] as JsonArray).map { JsonObject((it as JsonObject) + ("state" to JsonPrimitive("paused"))) }
                200 to put(JsonObject(pb + mapOf("state" to JsonPrimitive("retired"), "retired_at" to JsonPrimitive(now.toString()), "members" to JsonArray(members))))
            }
            else -> null
        }
    }

    /** [pb] with the given fields over it; the version counts up. */
    private fun edited(pb: JsonObject, given: JsonObject) =
        JsonObject(pb + given.filterKeys { it in EDITABLE } + ("version" to JsonPrimitive(((pb["version"] as? JsonPrimitive)?.contentOrNull?.toIntOrNull() ?: 1) + 1)))

    /** §40.2 a draft from a session: its people as seats (the models in it as their helpers), a weekly report, one rule; and its card. */
    private fun draft(s: V35Demo.Look): JsonObject {
        val ref = "PB-" + (seq++).toString().padStart(4, '0')
        val helpers = s.participants.mapNotNull { it.str("key")?.takeIf { k -> k.startsWith("player:") }?.removePrefix("player:") }
        val people = s.participants.filter { it.str("kind") != "player" }
        val seats = people.map { p ->
            val key = p.str("key").orEmpty()
            val role = key.substringBefore('@').ifBlank { key }
            seat(role, role, p.str("title_fa").orEmpty().ifBlank { s.holderFa }, if (key == s.holder) "مسئول کارگروه؛ برنامه و تأیید پیش از انتشار." else "همان کاری که در جلسه داشت.", *helpers.toTypedArray())
        }
        val title = s.text.substringBefore('؛').substringBefore('.').trim().take(60)
        val pb = jo(
            "ref" to ref, "title_fa" to title, "purpose_fa" to s.text, "state" to "draft", "version" to 1, "platform" to "any",
            "seats" to JsonArray(seats),
            "routines" to JsonArray(listOf(routine("weekly", "گزارش هفته", s.holder.substringBefore('@'), "FREQ=WEEKLY;BYDAY=SA;BYHOUR=10;BYMINUTE=0", "کار هفته را در سه خط برای مدیر کل بنویس."))),
            "kpis" to JsonArray(emptyList()), "connections" to JsonArray(emptyList()), "rules_fa" to strs("پیش از انتشار، مسئول کارگروه متن را تأیید کند."),
            "source" to jo("order" to s.ref, "company" to s.company, "conversation" to s.cv), "members" to JsonArray(emptyList()),
            "parent" to null, "created_at" to now.toString(), "sealed_at" to null, "retired_at" to null, "group" to null, "note_fa" to null,
        )
        books.add(0, pb)
        v35.append(s.ref, listOf(Triple(null, "کارگروه از این جلسه آماده است؛ بازش کن، اگر خواستی ویرایش کن و مُهر بزن.", 0L to listOf(card("TC-${cardSeq++}", ref, title, null)))), stepFa = "کارگروه از این جلسه پیش‌نویس شد: «$title»")
        return pb
    }

    companion object {
        private val EDITABLE = setOf("title_fa", "purpose_fa", "platform", "seats", "routines", "kpis", "connections", "rules_fa")
        private val HELPER = mapOf("gpt" to "ChatGPT", "gemini" to "Gemini", "deepseek" to "DeepSeek", "aistudio" to "AI Studio")
        private val PLATFORM_FA = mapOf("instagram" to "اینستاگرام", "youtube" to "یوتیوب", "telegram" to "تلگرام", "site" to "سایت", "any" to "هر پلتفرمی")
    }

    private fun JsonObject.str(k: String): String? = (this[k] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull
    private fun jo(vararg kv: Pair<String, Any?>): JsonObject = JsonObject(kv.associate { (k, v) ->
        k to when (v) {
            null -> JsonNull; is JsonElement -> v; is String -> JsonPrimitive(v); is Number -> JsonPrimitive(v); is Boolean -> JsonPrimitive(v)
            else -> error("unsupported ${v::class}")
        }
    })
    private fun problem(status: Int, code: String, fa: String) = jo("code" to code, "message_fa" to fa, "status" to status, "title" to code, "type" to "about:blank")
    /** A company with several accounts and none named: the hub names them in `fields.account`. */
    private fun pick(accounts: String) = JsonObject(problem(422, "validation_failed", "این شرکت چند حساب دارد؛ یکی را انتخاب کنید.") + ("fields" to jo("account" to accounts)))
}
