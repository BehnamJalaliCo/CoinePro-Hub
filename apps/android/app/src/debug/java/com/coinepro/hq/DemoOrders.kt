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
    ) {
        val events = mutableListOf<Ev>()
        val runs = mutableListOf<RunRec>()
        val depth: Int get() = (parent?.depth?.plus(1)) ?: if (assignee.kind == "ceo") 0 else 1
    }

    private val nodes = mutableListOf<Node>()
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

        // Live: the delegated order's manager starts, then delivers; the queued one is taken and delegated (DemoLive's ticks).
        at(9) { take(o4) }
        at(19) { delegate(o4, tyGrowth, "پیش‌نویس سیاست بازگشت وجه", "W-000216") }
        at(31) { start(k2) }
        at(47) { deliverUp(k2, o2) }
        DemoLive.orders = this
    }

    // ------------------------------------------------------------- build --
    private fun idOf(n: Int): String = "0193b1c2-%04x-7d4f-8a2e-%012x".format(n, 0x5a1000L + n)

    private fun order(ref: String, n: Int, ceo: Emp, title: String, priority: String, status: String, min: Long, brief: String): Node {
        val node = Node(idOf(n), ref, ceo.company, title, brief, priority, status, ceo, owner = true, parent = null, created = ago(min))
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
    private fun deliverable(n: Node, ref: String, title: String, summary: String, min: Long, at: Instant = ago(min)): String {
        store["/deliverables/$ref"] = 200 to buildJsonObject {
            put("id", "o-${ref.lowercase()}"); put("ref", ref); put("company", n.company); put("work_id", n.id); put("work_ref", n.ref)
            put("producer", emp(n.assignee)); put("title", title); put("summary", summary); put("body", "## خلاصه\n$summary\n\n## منبع‌ها\n- پایش ۳۰ روزه\n- گزارش‌های عمومی")
            put("attachments", JsonArray(emptyList())); put("evidence", JsonArray(emptyList()))
            put("produced_with", buildJsonObject { put("model", "claude-sonnet-5-5"); put("effort", "medium"); put("label_fa", "Sonnet 5.5 · medium") })
            put("usage", JsonObject(emptyMap())); put("rating", JsonNull); put("created_at", at.toString())
        }
        return ref
    }

    // -------------------------------------------------------------- live --
    private fun at(tick: Int, beat: () -> List<StreamEvent>) { beats += tick to beat }

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
            ev(k.company, "deliverable.created", kidOut, "work" to k.ref, "producer" to k.assignee.code),
            ev(k.company, "work.updated", k.ref, "status" to "delivered"),
            ev(root.company, "deliverable.created", out, "work" to root.ref, "producer" to root.assignee.code),
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
        val m = Regex("^/work/([^/]+)(/events|/runs)?$").find(path) ?: return null
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
        val n = Node(idOf(400 + seq), ref, co, b.str("title").orEmpty(), b.str("brief").orEmpty(), b.str("priority") ?: "P3", "queued", ceo, owner = true, parent = null, created = t)
        n.events += Ev(t, "created", "owner", "owner", mapOf("assignee" to ceo.code))
        nodes += n
        // It moves on its own: taken in ~5 s, delegated in ~11 s, started in ~18 s, delivered in ~27 s.
        val mgr = Emp("$co-GROWTH-MGR", co, "manager", "GROWTH", "مدیر رشد")
        val k = "W-%06d".format(++seq)
        at(lastTick + 8) { take(n) }
        at(lastTick + 18) { delegate(n, mgr, n.title, k) }
        at(lastTick + 30) { nodes.firstOrNull { it.ref == k }?.let(::start).orEmpty() }
        at(lastTick + 45) { nodes.firstOrNull { it.ref == k }?.let { deliverUp(it, n) }.orEmpty() }
        return 201 to work(n)
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
        put("trigger", "work"); put("reason", "کار ${n.ref}"); put("priority", n.priority); put("model", "claude-sonnet-5-5"); put("effort", "medium")
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
        val UUID = Regex("^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
    }
}
