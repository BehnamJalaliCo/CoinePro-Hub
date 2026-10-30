package com.coinepro.hq

import com.coinepro.hq.core.format.HqClock
import com.coinepro.hq.core.net.StreamEvent
import java.time.Instant
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
import kotlinx.serialization.json.put

/**
 * Debug builds only: the owner's orders as the hub keeps them (contract §4, §16.2), so «فرمان‌های من», the order's page and its
 * notifications show working in the demo.
 *
 * - Seven orders in every stage: just given (in the queue), taken by its CEO (a run on it), delegated (a child not started), at work (a
 *   manager and two employees under it, one done), delivered with its output, done, and failed with the CEO's reason; each with its
 *   events, the runs on it and under it (step summaries only), and its output's page.
 * - Two works the agents opened themselves (not the owner's), so the live stream's lines about them resolve too.
 * - `GET /work` (with its filters), `GET /work/{id}`, `/events`, `/runs`; an id the hub has no work for answers 404, as it does.
 * - `POST /work`: a new order joins the list and moves on its own: its CEO takes it, delegates it, the manager starts and delivers.
 * - Live ([tick], from [DemoLive]): the delegated order's manager starts and delivers, the queued one is taken and delegated, so the
 *   stream carries `work.*`, `run.*` and `deliverable.created` and the app's notices fire.
 */
internal class OrdersDemo(private val store: MutableMap<String, Pair<Int, JsonElement>>) {
    private data class Emp(val code: String, val company: String, val kind: String, val dept: String?, val title: String)

    private class Ev(val at: Instant, val kind: String, val actor: String, val actorKind: String, val data: Map<String, String> = emptyMap())

    private class Step(val at: Instant, val summary: String, val tool: String, val ref: String? = null)

    private class RunRec(val id: String, val employee: String, var state: String, val started: Instant, var finished: Instant?, val steps: MutableList<Step>)

    private inner class Node(
        val id: String,
        val ref: String,
        val company: String,
        val title: String,
        val brief: String,
        val priority: String,
        var status: String,
        val assignee: Emp,
        val owner: Boolean,
        val parent: Node?,
        val created: Instant,
        var updated: Instant = created,
        var progress: Int? = null,
        var note: String? = null,
        var deliverable: String? = null,
        var reason: String? = null,
        /** ⟨1.9⟩ §27.1 who plays it, and the model its runs used; a media council's kind. */
        var player: String = "auto",
        var mode: String = "single",
        val model: String = "claude-sonnet-5-5",
        val media: String? = null,
    ) {
        val events = mutableListOf<Ev>()
        val runs = mutableListOf<RunRec>()
        val depth: Int get() = (parent?.depth?.plus(1)) ?: if (assignee.kind == "ceo") 0 else 1
    }

    private val nodes = mutableListOf<Node>()

    /** ⟨1.9⟩ §27.2: one player of a council and the council itself, by its work's id. */
    private class Member(val player: String, val model: String, var state: String, var runId: String? = null, var ref: String? = null, var reason: String? = null, var creative: String? = null)

    /** A media council's version by a player (player, work ref, kind) → its Creative's ref ([CouncilDemo] draws and serves it). */
    var mediaMaker: ((String, String, String) -> String)? = null
    private class CouncilRec(val node: Node, val members: MutableList<Member>, var synthesis: String? = null, var state: String = "running")
    private val councils = mutableMapOf<String, CouncilRec>()
    private val now: Instant = HqClock.now()
    private var seq = 219
    private var outSeq = 47
    private var lastTick = 0
    /** Beats waiting for their tick: the live part of the demo. */
    private val beats = mutableListOf<Pair<Int, () -> List<StreamEvent>>>()

    private fun ago(min: Long): Instant = now.minus(min, ChronoUnit.MINUTES)

    init {
        val tyCeo = Emp("TY-CEO", "TY", "ceo", null, "مدیرعامل")
        val tyGrowth = Emp("TY-GROWTH-MGR", "TY", "manager", "GROWTH", "مدیر رشد")
        val tySeo = Emp("TY-GROWTH-01", "TY", "employee", "GROWTH", "تحلیلگر سئوی فنی")
        val tyCamp = Emp("TY-GROWTH-02", "TY", "employee", "GROWTH", "تحلیلگر کمپین")
        val fxCeo = Emp("FX-CEO", "FX", "ceo", null, "مدیرعامل")
        val fxTech = Emp("FX-TECH-MGR", "FX", "manager", "TECH", "مدیر فنی")
        val pcCeo = Emp("PC-CEO", "PC", "ceo", null, "مدیرعامل")
        val pcGrowth = Emp("PC-GROWTH-MGR", "PC", "manager", "GROWTH", "مدیر رشد")
        val pcTech = Emp("PC-TECH-MGR", "PC", "manager", "TECH", "مدیر فنی")
        val hqAi = Emp("HQ-AIOPS-MGR", "HQ", "manager", "AIOPS", "مدیر عملیات AI")

        // At work: the CEO gave it to the growth manager, who split it between two analysts (one delivered, one at 40%).
        val o1 = order("W-000210", 1, tyCeo, "گزارش رقبای صرافی در ۳۰ روز گذشته", "P2", "waiting", 190,
            "کارمزد، کمپین‌ها و تغییرات محصول سه رقیب اصلی در ۳۰ روز گذشته؛ با منبع برای هر ادعا. تا پایان امروز.")
        accepted(o1, 186); run(o1, 186, 171, "done", "فرمان را خواند و دامنه‌ی کار را روشن کرد" to "work.read", "کار را به مدیر رشد سپرد" to "work.delegate")
        val k1 = child(o1, "W-000215", tyGrowth, "تحلیل رقبا: کارمزد، کمپین و محصول", "waiting", 170)
        accepted(k1, 160); run(k1, 160, 150, "done", "دو بخش کار را جدا کرد" to "work.read", "به دو تحلیلگر سپرد" to "work.delegate")
        val g1 = child(k1, "W-000217", tySeo, "کارمزد و کمپین‌های سه رقیب", "in_progress", 150, progress = 40, note = "دو رقیب از سه بررسی شد.")
        accepted(g1, 120); progress(g1, 25, 40)
        run(g1, 30, null, "running", "صفحه‌ی کارمزد رقیب اول را خواند" to "web.fetch", "جدول کارمزدها را ساخت" to "sheet.write", "کمپین‌های رقیب دوم را جمع کرد" to "web.fetch")
        val g2 = child(k1, "W-000218", tyCamp, "تغییرات محصول سه رقیب", "delivered", 150)
        accepted(g2, 140); run(g2, 140, 95, "done", "یادداشت‌های انتشار سه رقیب را خواند" to "web.fetch", "خلاصه را با منبع تحویل داد" to "work.deliver")
        delivered(g2, 95, deliverable(g2, "O-000046", "تغییرات محصول سه رقیب، ۳۰ روز", "دو رقیب کارمزد معامله‌ی آنی را کم کردند؛ یکی اپ موبایل تازه داد.", 95))

        // Delegated: the FX CEO gave it to its technical manager, who has not started yet.
        val o2 = order("W-000211", 2, fxCeo, "کاهش زمان بارگذاری داشبورد سیگنال", "P1", "waiting", 45,
            "داشبورد سیگنال روی موبایل بیش از ۴ ثانیه بالا میاید؛ زیر ۲ ثانیه شود. بدون تغییر ظاهر.")
        accepted(o2, 42); run(o2, 42, 31, "done", "گزارش سرعت صفحه را خواند" to "health.sites", "کار را به مدیر فنی سپرد" to "work.delegate")
        val k2 = child(o2, "W-000214", fxTech, "بهینه‌سازی بارگذاری داشبورد سیگنال", "queued", 30)

        // Taken: the CEO is on it, nobody under it yet.
        val o3 = order("W-000212", 3, fxCeo, "خلاصه‌ی عملکرد سیگنال‌های هفته", "P3", "in_progress", 14, "دقت، سود و زیان و سیگنال‌های منقضی هفته، در یک صفحه.")
        accepted(o3, 12); run(o3, 11, null, "running", "گزارش‌های دقت هفته را خواند" to "knowledge.search", "سیگنال‌های منقضی را شمرد" to "db.read")

        // Just given: in the queue.
        val o4 = order("W-000213", 4, tyCeo, "پیش‌نویس سیاست بازگشت وجه کاربران", "P3", "queued", 3, "یک صفحه، روشن و قابل انتشار؛ با موارد استثنا.")

        // Delivered: its output waits for the owner's look.
        val o5 = order("W-000206", 5, tyCeo, "تحلیل ریزش کاربران مهر", "P2", "delivered", 1560, "چرا کاربران مهر ریزش کردند و سه پیشنهاد برای برگرداندنشان.")
        accepted(o5, 1550)
        val k5 = child(o5, "W-000207", tyCamp, "داده‌ی ریزش مهر به تفکیک مرحله", "done", 1540)
        accepted(k5, 1530); delivered(k5, 400, null); run(k5, 1500, 410, "done", "داده‌ی ورود و واریز مهر را خواند" to "db.read", "مرحله‌ی بیشترین افت را پیدا کرد" to "sheet.write")
        delivered(o5, 70, deliverable(o5, "O-000044", "تحلیل ریزش کاربران مهر", "بیشترین ریزش بعد از تأیید هویت بود (۴۱٪)؛ سه پیشنهاد: یادآوری، راهنمای تصویری، پشتیبانی زنده.", 70))
        run(o5, 120, 70, "done", "یافته‌های تحلیلگر را خواند" to "work.read", "گزارش نهایی را نوشت و تحویل داد" to "work.deliver")

        // Done: delivered and rated by the owner.
        val o6 = order("W-000201", 6, fxCeo, "گزارش هزینه‌ی سرورهای مهر", "P4", "done", 4320, "هزینه‌ی هر سرور در مهر، با مقایسه‌ی شهریور.")
        accepted(o6, 4300); run(o6, 4300, 4200, "done", "صورت‌حساب‌های مهر را خواند" to "archive.search", "جدول مقایسه را تحویل داد" to "work.deliver")
        delivered(o6, 4200, deliverable(o6, "O-000045", "هزینه‌ی سرورهای مهر", "هزینه‌ی مهر ۸٪ کمتر از شهریور؛ یک سرور بی‌کار شناسایی شد.", 4200))
        o6.events += Ev(ago(3000), "completed", "owner", "owner", mapOf("evidence" to "1"))
        o6.updated = ago(3000)

        // Failed: the company is stopped and the campaign had no approved e-mail policy.
        val o7 = order("W-000204", 7, pcCeo, "کمپین ایمیلی نوروز", "P3", "failed", 2880, "پیش‌نویس و زمان‌بندی کمپین ایمیلی نوروز برای کاربران فعال.")
        accepted(o7, 2870)
        val k7 = child(o7, "W-000205", pcGrowth, "متن و زمان‌بندی کمپین نوروز", "cancelled", 2860)
        k7.events += Ev(ago(40), "cancelled", "PC-CEO", "agent", mapOf("reason" to "شرکت متوقف شد."))
        failed(o7, 38, "پرو-چارت متوقف است و سیاست ارسال ایمیل هنوز مُهر نشده؛ کمپین بدون آن اجرا نمیشود.")

        // Opened by agents, not the owner (the live stream talks about them too).
        agentWork("W-000108", pcTech, "PC-CEO", "رفع خطای نمایش قیمت در ترمینال", "P1", "in_progress", 300)
        agentWork("W-000130", hqAi, "HQ-AIOPS-MGR", "بازبینی مصرف توکن هفته", "P3", "in_progress", 90)

        // ⟨1.9⟩ §27.1: an order the owner left to the router, done; one given to GPT, delivered with GPT's answer.
        val o8 = order("W-000196", 8, fxCeo, "برنامه‌ی محتوای هفته‌ی کانال تلگرام", "P3", "done", 5800, "هفت پست برای هفته‌ی آینده، با موضوع و زمان هر کدام.")
        accepted(o8, 5790); run(o8, 5790, 5700, "done", "تقویم انتشار هفته را خواند" to "media.calendar", "برنامه را تحویل داد" to "work.deliver")
        delivered(o8, 5700, deliverable(o8, "O-000150", "برنامه‌ی محتوای هفته‌ی کانال", "هفت پست: سه آموزشی، دو تحلیلی و دو اطلاع‌رسانی، با زمان هر کدام.", 5700))
        o8.events += Ev(ago(5000), "completed", "owner", "owner", mapOf("evidence" to "1"))
        o8.updated = ago(5000)
        val o9 = order("W-000197", 9, tyCeo, "بازبینی متن‌های صفحه‌ی ثبت‌نام", "P3", "delivered", 420,
            "متن دکمه‌ها و پیام‌های خطای ثبت‌نام را روان و یکدست کن؛ فهرست تغییرها با دلیل هر کدام.", player = "gpt", model = "gpt-5.5")
        accepted(o9, 415)
        run(o9, 415, 330, "done", "متن‌های فعلی صفحه را خواند" to "web.fetch", "پیشنهادها را با GPT نوشت" to "substitute.call", "فهرست تغییرها را تحویل داد" to "work.deliver")
        delivered(o9, 330, deliverable(o9, "O-000151", "بازبینی متن‌های ثبت‌نام", "۱۴ متن روان‌تر شد؛ سه پیام خطا حالا میگوید کاربر چه کند.", 330, model = "gpt-5.5"))

        // ⟨1.9⟩ §27.2: a council of four (Gemini kept out by its daily cap) with Claude's synthesis, and a media council of two images.
        val o10 = order("W-000198", 10, tyCeo, "پشتیبانی زنده‌ی ۲۴ ساعته: ارزش هزینه‌اش را دارد؟", "P2", "delivered", 900,
            "هزینه و اثر پشتیبانی زنده‌ی شبانه‌روزی برای تریدیار را بسنج؛ با عدد و ریسک، و یک پیشنهاد روشن.", mode = "council")
        accepted(o10, 895)
        run(o10, 890, 760, "done", "شرح را برای بازیکن‌های شورا یکسان کرد" to "work.read", "پاسخ سه بازیکن را خواند" to "work.read", "جمع‌بندی را نوشت و تحویل داد" to "work.deliver")
        val a1 = deliverable(o10, "O-000152", "پاسخ Claude: پشتیبانی زنده‌ی ۲۴ ساعته", "شب‌ها با پاسخ خودکار و یک نفر آنکال؛ ۲۴ ساعته بعد از سه ماه سنجش.", 820, body = CLAUDE_ANSWER)
        val a2 = deliverable(o10, "O-000153", "پاسخ GPT: پشتیبانی زنده‌ی ۲۴ ساعته", "۲۴ ساعته از همین ماه؛ ریزش شبانه گران‌تر از هزینه است.", 815, model = "gpt-5.5", body = GPT_ANSWER)
        val a3 = deliverable(o10, "O-000154", "پاسخ DeepSeek: پشتیبانی زنده‌ی ۲۴ ساعته", "پشتیبانی شب برون‌سپاری شود؛ هزینه نصف، با ریسک کیفیت.", 810, model = "deepseek-v3.2", body = DEEPSEEK_ANSWER)
        val syn = deliverable(o10, "O-000155", "جمع‌بندی شورا: پشتیبانی زنده‌ی ۲۴ ساعته", "هر سه شب را نیازمند پاسخ میدانند؛ درباره‌ی چگونگی و زمان اختلاف دارند. پیشنهاد: آزمون سه‌ماهه.", 760, body = SYNTHESIS_MD)
        delivered(o10, 760, syn)
        councils[o10.id] = CouncilRec(o10, mutableListOf(
            Member("claude", "claude-sonnet-5-5", "done", idOf(700), a1),
            Member("gpt", "gpt-5.5", "done", idOf(701), a2),
            Member("gemini", "gemini-3.8", "skipped", reason = "سقف روزانه‌ی Gemini پر شده بود؛ شورا بی آن ادامه داد و در یک پاکت ماند."),
            Member("deepseek", "deepseek-v3.2", "done", idOf(702), a3),
        ), synthesis = syn, state = "done")
        val o11 = order("W-000199", 11, fxCeo, "تصویر استوری برای دوره‌ی رایگان طلا", "P3", "delivered", 240,
            "استوری اینستاگرام برای جلسه‌ی دوم دوره‌ی رایگان تحلیل طلا؛ هر بازیکن نسخه‌ی خودش را بسازد.", mode = "council", media = "image")
        accepted(o11, 236)
        run(o11, 236, 180, "done", "prompt بی‌متن را از روی برند نوشت" to "brand.read", "از دو بازیکن تصویر خواست" to "substitute.call", "دو نسخه را با brief سنجید" to "vision.check")
        delivered(o11, 180, null)
        councils[o11.id] = CouncilRec(o11, mutableListOf(
            Member("gpt", "gpt-5.5", "done", idOf(703), creative = "CR-0101"),
            Member("gemini", "gemini-3.8", "done", idOf(704), creative = "CR-0102"),
        ), state = "done")

        // Live: the delegated order's manager starts, then delivers; the queued one is taken and delegated (DemoLive's ticks).
        at(9) { take(o4) }
        at(19) { delegate(o4, tyGrowth, "پیش‌نویس سیاست بازگشت وجه", "W-000216") }
        at(31) { start(k2) }
        at(47) { deliverUp(k2, o2) }
        DemoLive.orders = this
    }

    // ------------------------------------------------------------- build --
    private fun idOf(n: Int): String = "0193b1c2-%04x-7d4f-8a2e-%012x".format(n, 0x5a1000L + n)

    private fun order(
        ref: String, n: Int, ceo: Emp, title: String, priority: String, status: String, min: Long, brief: String,
        player: String = "auto", mode: String = "single", model: String = "claude-sonnet-5-5", media: String? = null,
    ): Node {
        val node = Node(idOf(n), ref, ceo.company, title, brief, priority, status, ceo, owner = true, parent = null, created = ago(min), player = player, mode = mode, model = model, media = media)
        node.events += Ev(ago(min), "created", "owner", "owner", mapOf("assignee" to ceo.code))
        nodes += node
        return node
    }

    private fun child(parent: Node, ref: String, to: Emp, title: String, status: String, min: Long, progress: Int? = null, note: String? = null): Node {
        val node = Node(idOf(100 + nodes.size), ref, parent.company, title, "", parent.priority, status, to, owner = false, parent = parent, created = ago(min), progress = progress, note = note)
        node.events += Ev(ago(min), "created", parent.assignee.code, "agent", mapOf("assignee" to to.code))
        parent.events += Ev(ago(min), "delegated", parent.assignee.code, "agent", mapOf("child" to ref, "to" to to.code))
        nodes += node
        return node
    }

    private fun agentWork(ref: String, to: Emp, by: String, title: String, priority: String, status: String, min: Long) {
        val node = Node(idOf(200 + nodes.size), ref, to.company, title, "", priority, status, to, owner = false, parent = null, created = ago(min))
        node.events += Ev(ago(min), "created", by, "agent", mapOf("assignee" to to.code))
        nodes += node
    }

    private fun accepted(n: Node, min: Long) {
        n.events += Ev(ago(min), "accepted", n.assignee.code, "agent")
        n.updated = maxOf(n.updated, ago(min))
    }

    private fun progress(n: Node, min: Long, pct: Int) {
        n.events += Ev(ago(min), "progress", n.assignee.code, "agent", mapOf("pct" to pct.toString()))
        n.updated = maxOf(n.updated, ago(min))
    }

    private fun delivered(n: Node, min: Long, out: String?) {
        n.deliverable = out
        n.events += Ev(ago(min), "delivered", n.assignee.code, "agent", out?.let { mapOf("deliverable" to it) }.orEmpty())
        n.updated = maxOf(n.updated, ago(min))
    }

    private fun failed(n: Node, min: Long, reason: String) {
        n.reason = reason
        n.events += Ev(ago(min), "failed", n.assignee.code, "agent", mapOf("reason" to reason))
        n.updated = maxOf(n.updated, ago(min))
    }

    private fun run(n: Node, from: Long, to: Long?, state: String, vararg steps: Pair<String, String>) {
        val span = (from - (to ?: 0)).coerceAtLeast(steps.size.toLong())
        val list = steps.mapIndexed { i, (s, tool) -> Step(ago(from - span * i / steps.size.coerceAtLeast(1)), s, tool, n.ref) }.toMutableList()
        n.runs += RunRec(idOf(500 + nodes.size * 10 + n.runs.size), n.assignee.code, state, ago(from), to?.let(::ago), list)
        n.updated = maxOf(n.updated, list.lastOrNull()?.at ?: ago(from))
    }

    /** An output of [n] as the outputs' page serves it (its own page only, so the outputs list stays as the web's fixtures have it). */
    private fun deliverable(
        n: Node, ref: String, title: String, summary: String, min: Long, at: Instant = ago(min), model: String = "claude-sonnet-5-5", body: String? = null,
    ): String {
        store["/deliverables/$ref"] = 200 to buildJsonObject {
            put("id", "o-${ref.lowercase()}"); put("ref", ref); put("company", n.company); put("work_id", n.id); put("work_ref", n.ref)
            put("producer", emp(n.assignee)); put("title", title); put("summary", summary)
            put("body", body ?: "## خلاصه\n$summary\n\n## منبع‌ها\n- پایش ۳۰ روزه\n- گزارش‌های عمومی")
            put("attachments", JsonArray(emptyList())); put("evidence", JsonArray(emptyList()))
            put("produced_with", buildJsonObject {
                put("model", model); put("effort", "medium")
                put("label_fa", if (model.startsWith("claude")) "Sonnet 5.5 · medium" else "${com.coinepro.hq.ui.v18.subModel(model)} · بازیکن ذخیره")
            })
            put("usage", JsonObject(emptyMap())); put("rating", JsonNull); put("created_at", at.toString())
        }
        return ref
    }

    // -------------------------------------------------------------- live --
    private fun at(tick: Int, beat: () -> List<StreamEvent>) { beats += tick to beat }

    /** What is still to come happens at the next tick (the background link's script: the owner's orders move while the app is closed). */
    @Synchronized
    fun rush() {
        val next = beats.map { (lastTick + 1) to it.second }
        beats.clear()
        beats += next
    }

    @Synchronized
    fun tick(tick: Int): List<StreamEvent> {
        lastTick = tick
        val due = beats.filter { it.first <= tick }
        beats.removeAll(due)
        return due.flatMap { it.second() }
    }

    private fun ev(company: String, type: String, ref: String?, vararg data: Pair<String, String>) =
        StreamEvent("demo-o-${System.nanoTime()}", type, HqClock.now().toString(), company, ref, JsonObject(data.toMap().mapValues { JsonPrimitive(it.value) }))

    private fun take(n: Node): List<StreamEvent> {
        val t = HqClock.now()
        n.status = "in_progress"; n.updated = t
        n.events += Ev(t, "accepted", n.assignee.code, "agent")
        val r = RunRec(idOf(900 + n.runs.size + nodes.size), n.assignee.code, "running", t, null, mutableListOf(Step(t, "فرمان را خواند و دامنه‌ی کار را روشن کرد", "work.read", n.ref)))
        n.runs += r
        return listOf(
            ev(n.company, "work.updated", n.ref, "status" to "in_progress"),
            ev(n.company, "run.started", r.id, "employee" to n.assignee.code, "trigger" to "work", "work" to n.ref),
        )
    }

    private fun delegate(n: Node, to: Emp, title: String, ref: String): List<StreamEvent> {
        val t = HqClock.now()
        val k = Node(idOf(300 + nodes.size), ref, n.company, title, "", n.priority, "queued", to, owner = false, parent = n, created = t)
        k.events += Ev(t, "created", n.assignee.code, "agent", mapOf("assignee" to to.code))
        nodes += k
        n.status = "waiting"; n.updated = t
        n.events += Ev(t, "delegated", n.assignee.code, "agent", mapOf("child" to ref, "to" to to.code))
        val r = n.runs.lastOrNull()?.also { it.state = "done"; it.finished = t; it.steps += Step(t, "کار را به ${to.title} سپرد", "work.delegate", ref) }
        return listOfNotNull(
            ev(n.company, "work.created", ref, "assignee" to to.code, "depth" to k.depth.toString()),
            ev(n.company, "work.delegated", n.ref, "child" to ref, "to" to to.code),
            r?.let { ev(n.company, "run.finished", it.id, "employee" to it.employee, "state" to "done") },
        )
    }

    private fun start(k: Node): List<StreamEvent> {
        val t = HqClock.now()
        k.status = "in_progress"; k.updated = t; k.progress = 20
        k.events += Ev(t, "accepted", k.assignee.code, "agent")
        val r = RunRec(idOf(950 + nodes.size + k.runs.size), k.assignee.code, "running", t, null, mutableListOf(Step(t, "اندازه‌ی بسته‌های صفحه را خواند", "health.sites", k.ref)))
        k.runs += r
        return listOf(
            ev(k.company, "work.updated", k.ref, "status" to "in_progress"),
            ev(k.company, "run.started", r.id, "employee" to k.assignee.code, "trigger" to "work", "work" to k.ref),
        )
    }

    private fun deliverUp(k: Node, root: Node): List<StreamEvent> {
        val t = HqClock.now()
        val kidOut = deliverable(k, "O-%06d".format(outSeq++), "بهینه‌سازی بارگذاری داشبورد", "بسته‌ها کوچک شدند؛ بارگذاری روی موبایل از ۴٫۲ به ۱٫۷ ثانیه رسید.", 0, t)
        k.status = "delivered"; k.updated = t; k.progress = 100; k.deliverable = kidOut
        k.events += Ev(t, "delivered", k.assignee.code, "agent", mapOf("deliverable" to kidOut))
        k.runs.lastOrNull()?.let { it.state = "done"; it.finished = t; it.steps += Step(t, "تغییر را با شاهد سرعت تحویل داد", "work.deliver", k.ref) }
        val out = deliverable(root, "O-%06d".format(outSeq++), root.title, "زمان بارگذاری داشبورد سیگنال روی موبایل به ۱٫۷ ثانیه رسید؛ ظاهر دست نخورد.", 0, t)
        root.status = "delivered"; root.updated = t; root.deliverable = out
        root.events += Ev(t, "delivered", root.assignee.code, "agent", mapOf("deliverable" to out))
        k.status = "done"
        return listOf(
            // ⟨1.7.4⟩ the hub names the owner's order each output belongs to (`root_ref`).
            ev(k.company, "deliverable.created", kidOut, "work" to k.ref, "producer" to k.assignee.code, "root_ref" to root.ref),
            ev(k.company, "work.updated", k.ref, "status" to "delivered"),
            ev(root.company, "deliverable.created", out, "work" to root.ref, "producer" to root.assignee.code, "root_ref" to root.ref),
            ev(root.company, "work.updated", root.ref, "status" to "delivered"),
            ev(k.company, "work.completed", k.ref, "by" to root.assignee.code),
        )
    }

    // ------------------------------------------------------------ answers --
    /** Answers the work reads and the new order, or null to let the rest of the demo (and the web's fixtures) answer. */
    @Synchronized
    fun handle(method: String, path: String, query: Map<String, String?>, body: JsonObject?): Pair<Int, JsonElement>? {
        if (method == "GET" && path == "/work") return 200 to page(filtered(query))
        if (method == "POST" && path == "/work") return create(body ?: JsonObject(emptyMap()))
        // ⟨1.9⟩ §27.1: the owner changes who plays a work (a voice order's choice set on the work it made).
        if (method == "PATCH") Regex("^/work/([^/]+)$").find(path)?.let { p ->
            val n = nodes.firstOrNull { it.id == p.groupValues[1] || it.ref == p.groupValues[1] } ?: return null
            body?.str("player")?.let { n.player = it }
            body?.str("mode")?.let { n.mode = it }
            n.updated = HqClock.now()
            return 200 to detail(n)
        }
        val m = Regex("^/work/([^/]+)(/events|/runs|/council)?$").find(path) ?: return null
        if (method != "GET") return null
        val key = m.groupValues[1]
        val n = nodes.firstOrNull { it.id == key || it.ref == key }
        if (n == null) {
            // An id the hub has no work for: 404, as the hub answers (the fixtures' own ids still answer below).
            return if (UUID.matches(key)) 404 to buildJsonObject { put("code", "not_found"); put("message_fa", "این کار پیدا نشد."); put("status", 404); put("title", "Not Found"); put("type", "about:blank") } else null
        }
        return when (m.groupValues[2]) {
            "/events" -> 200 to page(n.events.mapIndexed { i, e -> event(e, i + 1) }.sortedBy { it.jsonObject["at"].toString() })
            "/runs" -> 200 to JsonArray(n.runs.map { runJson(n, it) })
            // ⟨1.9⟩ §27.2: a work given with `mode: "council"` has one; any other answers 404.
            "/council" -> councils[n.id]?.let { 200 to councilJson(it) }
                ?: (404 to buildJsonObject { put("code", "not_found"); put("message_fa", "این کار شورا ندارد."); put("status", 404); put("title", "Not Found"); put("type", "about:blank") })
            else -> 200 to detail(n)
        }
    }

    private fun filtered(q: Map<String, String?>): List<JsonElement> {
        val mine = nodes.sortedByDescending { it.created }.map { work(it) }
        val fixtures = (store["/work"]?.second?.jsonObject?.get("items") as? JsonArray).orEmpty()
        val text = q["q"]?.trim()?.takeIf { it.isNotEmpty() }
        return (mine + fixtures).map { it.jsonObject }.filter { w ->
            (q["company"] == null || w.str("company") == q["company"]) &&
                (q["status"] == null || w.str("status") == q["status"]) &&
                (q["assignee"] == null || (w["assignee"] as? JsonObject)?.str("code") == q["assignee"]) &&
                (text == null || w.str("ref") == text || w.str("title").orEmpty().contains(text))
        }
    }

    private fun create(b: JsonObject): Pair<Int, JsonElement> {
        val co = b.str("company") ?: return 422 to buildJsonObject { put("code", "validation_failed"); put("message_fa", "شرکت لازم است."); put("status", 422) }
        val ceo = Emp("$co-CEO", co, "ceo", null, "مدیرعامل")
        val t = HqClock.now()
        val ref = "W-%06d".format(++seq)
        val player = b.str("player") ?: "auto"
        val mode = b.str("mode") ?: "single"
        val model = when (player) { "gpt" -> "gpt-5.5"; "gemini" -> "gemini-3.8"; "deepseek" -> "deepseek-v3.2"; else -> "claude-sonnet-5-5" }
        val media = b.str("media")?.takeIf { mode == "council" }
        val n = Node(idOf(400 + seq), ref, co, b.str("title").orEmpty(), b.str("brief").orEmpty(), b.str("priority") ?: "P3", "queued", ceo, owner = true, parent = null, created = t, player = player, mode = mode, model = model, media = media)
        n.events += Ev(t, "created", "owner", "owner", mapOf("assignee" to ceo.code))
        nodes += n
        if (mode == "council") return 201 to work(n).also { council(n) }
        // It moves on its own: taken in ~5 s, delegated in ~11 s, started in ~18 s, delivered in ~27 s.
        val mgr = Emp("$co-GROWTH-MGR", co, "manager", "GROWTH", "مدیر رشد")
        val k = "W-%06d".format(++seq)
        at(lastTick + 8) { take(n) }
        at(lastTick + 18) { delegate(n, mgr, n.title, k) }
        at(lastTick + 30) { nodes.firstOrNull { it.ref == k }?.let(::start).orEmpty() }
        at(lastTick + 45) { nodes.firstOrNull { it.ref == k }?.let { deliverUp(it, n) }.orEmpty() }
        return 201 to work(n)
    }

    /**
     * ⟨1.9⟩ §27.2 live: the CEO takes the order; every ready player starts (one kept out shows why), they answer one by one, Claude
     * writes the synthesis and the order is delivered; each change rides `work.council` on the stream.
     */
    private fun council(n: Node) {
        val subs = (store["/substitutes"]?.second as? JsonArray).orEmpty().mapNotNull { it as? JsonObject }
        fun seat(p: String, model: String): Member {
            val s = subs.firstOrNull { it.str("player") == p }
            val web = (s?.get("web") as? JsonObject)?.str("state") == "signed_in"
            val cli = s?.str("runner") != null && ((s["login"] as? JsonObject)?.str("state") == "signed_in")
            return when {
                s == null -> Member(p, model, "skipped", reason = "این بازیکن روی هاب وصل نیست.")
                s.str("status") != "ready" -> Member(p, model, "skipped", reason = s.str("status_reason") ?: "در دسترس نیست.")
                !web && !cli -> Member(p, model, "skipped", reason = "از حسابش خارج است.")
                else -> Member(p, model, "queued")
            }
        }
        val rec = if (n.media != null) {
            // A media council: every player that makes the kind (ChatGPT and Gemini images, Gemini videos) makes its own version.
            val makers = if (n.media == "video") listOf("gemini" to "gemini-3.8") else listOf("gpt" to "gpt-5.5", "gemini" to "gemini-3.8")
            CouncilRec(n, makers.map { (p, m) -> seat(p, m) }.toMutableList())
        } else CouncilRec(n, mutableListOf(Member("claude", "claude-sonnet-5-5", "queued"), seat("gpt", "gpt-5.5"), seat("gemini", "gemini-3.8"), seat("deepseek", "deepseek-v3.2")))
        councils[n.id] = rec
        fun changed(vararg data: Pair<String, String>) = ev(n.company, "work.council", n.ref, "state" to rec.state, *data)
        at(lastTick + 5) { take(n) + rec.members.filter { it.state == "queued" }.map { it.state = "working"; it.runId = idOf(980 + seq + rec.members.indexOf(it)); changed("player" to it.player, "member" to "working") } }
        rec.members.filter { it.state == "queued" }.forEachIndexed { i, m ->
            at(lastTick + 12 + i * 5) {
                m.state = "done"
                val maker = mediaMaker
                if (n.media != null && maker != null) m.creative = maker(m.player, n.ref, n.media)
                else m.ref = deliverable(n, "O-%06d".format(outSeq++), "پاسخ ${com.coinepro.hq.core.data.playerFa(m.player)}: ${n.title}", "پاسخ مستقل ${com.coinepro.hq.core.data.playerFa(m.player)} به همان شرح.", 0, HqClock.now(), model = m.model)
                if (rec.members.none { it.state == "working" || it.state == "queued" }) rec.state = "synthesising"
                listOf(changed("player" to m.player, "member" to "done"))
            }
        }
        at(lastTick + 12 + rec.members.count { it.state == "queued" } * 5 + 8) {
            val t = HqClock.now()
            rec.state = "done"
            // Words: Claude's synthesis is the output; media: the versions wait for the owner's pick.
            if (n.media == null) rec.synthesis = deliverable(n, "O-%06d".format(outSeq++), "جمع‌بندی شورا: ${n.title}", "جمع‌بندی Claude از پاسخ بازیکن‌ها.", 0, t, body = SYNTHESIS_MD)
            n.status = "delivered"; n.updated = t; n.deliverable = rec.synthesis
            n.events += Ev(t, "delivered", n.assignee.code, "agent", rec.synthesis?.let { mapOf("deliverable" to it) }.orEmpty())
            n.runs.lastOrNull()?.let { it.state = "done"; it.finished = t; it.steps += Step(t, "جمع‌بندی شورا را نوشت و تحویل داد", "work.deliver", n.ref) }
            listOfNotNull(
                changed(),
                rec.synthesis?.let { ev(n.company, "deliverable.created", it, "work" to n.ref, "producer" to n.assignee.code, "root_ref" to n.ref) },
                ev(n.company, "work.updated", n.ref, "status" to "delivered"),
            )
        }
    }

    // ------------------------------------------------------------- shapes --
    private fun emp(e: Emp) = buildJsonObject { put("code", e.code); put("company", e.company); put("kind", e.kind); put("department", e.dept); put("title_fa", e.title) }

    private fun work(n: Node): JsonObject = buildJsonObject {
        put("id", n.id); put("ref", n.ref); put("company", n.company); put("department", n.assignee.dept); put("title", n.title); put("brief", n.brief)
        put("kind", "one_off"); put("priority", n.priority); put("status", n.status); put("assignee", emp(n.assignee))
        put("created_by", if (n.owner) buildJsonObject { put("kind", "owner"); put("code", "owner"); put("display_fa", "مدیر کل") }
            else buildJsonObject { put("kind", "agent"); put("code", n.parent?.assignee?.code ?: n.events.firstOrNull()?.actor ?: n.assignee.code); put("display_fa", JsonNull) })
        put("created_at", n.created.toString()); put("updated_at", n.updated.toString()); put("due_at", JsonNull); put("overdue", false)
        put("progress_pct", n.progress?.let(::JsonPrimitive) ?: JsonNull); put("progress_note", n.note)
        put("budget", buildJsonObject { put("tokens", 400000); put("tokens_used", 12000L * (n.runs.size + 1)); put("usd", JsonNull); put("usd_used", "%.2f".format(java.util.Locale.US, 0.21 * (n.runs.size + 1))) })
        put("schedule", JsonNull); put("depth", n.depth); put("parent_id", n.parent?.id); put("root_id", root(n).id)
        put("deliverable_ids", buildJsonArray { n.deliverable?.let { add(JsonPrimitive("o-${it.lowercase()}")) } })
        put("evidence", JsonArray(emptyList())); put("version", 1 + n.events.size)
        put("player", n.player); put("mode", n.mode); put("media", n.media); put("player_fallback", false)
    }

    private fun councilJson(c: CouncilRec) = buildJsonObject {
        put("work_ref", c.node.ref); put("synthesis_ref", c.synthesis); put("state", c.state); put("media", c.node.media)
        put("members", JsonArray(c.members.map { m ->
            buildJsonObject {
                put("player", m.player); put("model", m.model); put("state", m.state); put("run_id", m.runId); put("deliverable_ref", m.ref); put("reason", m.reason)
                put("creative_ref", m.creative)
            }
        }))
    }

    private fun root(n: Node): Node = n.parent?.let(::root) ?: n

    private fun step(n: Node) = buildJsonObject {
        put("id", n.id); put("ref", n.ref); put("depth", n.depth); put("status", n.status); put("assignee", emp(n.assignee)); put("created_at", n.created.toString())
        put("tokens_used", 12000L * (n.runs.size + 1)); put("usd_used", 0.21 * (n.runs.size + 1))
    }

    private fun detail(n: Node): JsonObject {
        val chain = generateSequence(n) { it.parent }.toList().reversed()
        return JsonObject(work(n) + mapOf(
            "chain" to JsonArray(chain.map(::step)),
            "children" to JsonArray(nodes.filter { it.parent === n }.sortedBy { it.created }.map(::step)),
        ))
    }

    private fun event(e: Ev, id: Int) = buildJsonObject {
        put("id", id); put("at", e.at.toString()); put("kind", e.kind); put("actor_code", e.actor); put("actor_kind", e.actorKind)
        put("data", JsonObject(e.data.mapValues { JsonPrimitive(it.value) }))
    }

    private fun runJson(n: Node, r: RunRec) = buildJsonObject {
        put("id", r.id); put("employee", r.employee); put("company", n.company); put("work_ref", n.ref); put("thread", JsonNull); put("state", r.state)
        put("trigger", "work"); put("reason", "کار ${n.ref}"); put("priority", n.priority); put("model", n.model); put("effort", "medium")
        put("queued_at", r.started.minusSeconds(20).toString()); put("started_at", r.started.toString()); put("finished_at", r.finished?.toString())
        put("steps", r.steps.size); put("tool_calls", r.steps.size)
        put("tokens", buildJsonObject { put("input", 21000 * r.steps.size); put("output", 1800 * r.steps.size); put("cache_read", 9000); put("cache_write", 1200) })
        put("cost_usd", "0.00"); put("equiv_cost_usd", "%.2f".format(java.util.Locale.US, 0.12 * r.steps.size)); put("error_code", JsonNull); put("partial", false)
        put("steps_detail", JsonArray(r.steps.mapIndexed { i, s ->
            buildJsonObject {
                put("run_id", r.id); put("n", i + 1); put("at", s.at.toString()); put("summary_fa", s.summary)
                put("actions", buildJsonArray { add(buildJsonObject { put("tool", s.tool); put("outcome", "ok"); put("ref", s.ref); put("class", JsonNull) }) })
            }
        }))
    }

    private fun page(items: List<JsonElement>) = buildJsonObject { put("items", JsonArray(items)); put("next_cursor", JsonNull) }
    private fun JsonObject.str(k: String): String? = (this[k] as? JsonPrimitive)?.takeIf { it.isString }?.contentOrNull

    private companion object {
        // ⟨1.9⟩ §27.2: the council's answers and Claude's synthesis (agree, differ and why, the recommendation, each answer whole).
        const val CLAUDE_ANSWER = "## پاسخ\nشب‌ها (۰ تا ۸) ۱۸٪ پیام‌ها میرسد و نیمی از آن درباره‌ی واریز است. پیشنهاد: پاسخ خودکار برای واریز و برداشت، و یک نفر آنکال برای موارد فوری؛ بعد از سه ماه با داده تصمیم بگیر.\n\n## ریسک\n- رضایت شبانه پایین‌تر میماند تا آزمون تمام شود."
        const val GPT_ANSWER = "## پاسخ\nپشتیبانی ۲۴ ساعته از همین ماه. ریزش کاربرانی که شب بی‌پاسخ میمانند حدود دو برابر است و ارزش طول عمرشان از هزینه‌ی دو نیروی شیفت شب بیشتر است.\n\n## ریسک\n- هزینه‌ی ثابت ماهانه، پیش از اثبات اثر."
        const val DEEPSEEK_ANSWER = "## پاسخ\nشیفت شب را برون‌سپاری کن: هزینه حدود نصف نیروی داخلی است. منبع‌ها: دو گزارش عمومی از صرافی‌های منطقه.\n\n## ریسک\n- کیفیت پاسخ و دسترسی بیرونی به داده‌ی کاربران."
        const val SYNTHESIS_MD = "## کجا هم‌نظرند\n- هر سه بازیکن شب را بی‌پاسخ نمیخواهند: ۱۸٪ پیام‌ها شب میرسد.\n- واریز و برداشت بیشترین پرسش شبانه است.\n\n" +
            "## کجا فرق دارند و چرا\n- **زمان:** GPT از همین ماه میخواهد (ریزش شبانه را گران‌تر میداند)؛ Claude سه ماه سنجش (اثر را هنوز ثابت‌نشده میداند).\n" +
            "- **چگونه:** DeepSeek برون‌سپاری را ارزان‌تر میبیند؛ Claude و GPT آن را برای داده‌ی کاربران پرخطر میدانند.\n\n" +
            "## پیشنهاد\nآزمون سه‌ماهه: پاسخ خودکار برای واریز و برداشت و یک نفر آنکال شب، با سنجش ریزش شبانه. اگر ریزش ۳۰٪ کم شد، ۲۴ ساعته کامل؛ برون‌سپاری نه، به‌خاطر داده‌ی کاربران.\n\n" +
            "## پاسخ هر بازیکن، کامل\n### Claude\nشب‌ها پاسخ خودکار و یک نفر آنکال؛ بعد از سه ماه با داده تصمیم بگیر.\n### GPT\nپشتیبانی ۲۴ ساعته از همین ماه؛ ریزش شبانه گران‌تر از هزینه است.\n### DeepSeek\nشیفت شب برون‌سپاری شود؛ هزینه حدود نصف."

        val UUID = Regex("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
    }
}
