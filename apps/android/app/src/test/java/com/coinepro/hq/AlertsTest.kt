package com.coinepro.hq

import com.coinepro.hq.core.data.NoticeKind
import com.coinepro.hq.core.data.OrderNotice
import com.coinepro.hq.core.link.Alert
import com.coinepro.hq.core.link.AlertCenter
import com.coinepro.hq.core.link.AlertChannel
import com.coinepro.hq.core.link.AlertRules
import com.coinepro.hq.core.link.AlertSink
import com.coinepro.hq.core.link.AlertSource
import com.coinepro.hq.core.link.AlertTone
import com.coinepro.hq.core.link.LinkStore
import com.coinepro.hq.core.link.MemoryLinkStore
import com.coinepro.hq.core.link.OutputBrief
import com.coinepro.hq.core.link.Trigger
import com.coinepro.hq.core.net.Link
import com.coinepro.hq.core.net.Notification
import com.coinepro.hq.core.net.StreamEvent
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The background link's alerts (core/link/Alerts.kt): which event becomes which alert on which channel, and when nothing is said — an
 * event told before (a replay after a reconnect or a restart), a notification already read (on the web, or here), a card already decided,
 * an output already seen, an order's output (the order speaks for it), the owner's own kill switch, and anything while the app is on screen
 * (its toast speaks instead).
 */
@OptIn(kotlinx.coroutines.ExperimentalCoroutinesApi::class)
class AlertsTest {
    private val now = "2026-10-30T08:00:00Z"
    private var seq = 0
    private fun ev(type: String, ref: String?, company: String = "HQ", id: String = "${++seq}", vararg d: Pair<String, String>) =
        StreamEvent(id, type, now, company, ref, JsonObject(d.toMap().mapValues { JsonPrimitive(it.value) }))

    private fun raised(nid: String, level: String, kind: String? = null, ref: String? = null, id: String = "${++seq}") =
        ev("notification.created", nid, id = id, d = listOfNotNull("level" to level, kind?.let { "link_kind" to it }, ref?.let { "link_ref" to it }).toTypedArray())

    private fun note(id: String, level: String, title: String, kind: String? = null, ref: String? = null, body: String = "", read: String? = null, co: String = "HQ") =
        Notification(id, level, co, title, body, createdAt = now, readAt = read, link = kind?.let { Link(it, ref) })

    // ------------------------------------------------------------- rules --
    @Test
    fun eachLevelGoesToItsChannelAndOpensItsOwnPage() {
        val urgent = AlertRules.ofNotification(note("n1", "urgent", "دیسک هاب پر است", body = "۹۵٪ پر\nخط دوم"))
        assertEquals(AlertChannel.URGENT, urgent.channel)
        assertEquals(AlertTone.ERROR, urgent.tone)
        assertEquals("۹۵٪ پر", urgent.text)
        assertEquals("notifications", urgent.route)
        assertEquals("n1", urgent.notificationId)

        val card = AlertRules.ofNotification(note("n2", "decision", "تصمیم تازه D-000085: ایمیل دوم", "decision", "D-000085", "پیشنهاد HQ-LGL"))
        assertEquals(AlertChannel.CARTABLE, card.channel)
        assertEquals("decision:D-000085", card.key)
        assertEquals("cartable/D-000085", card.route)

        // A hold and a finding raised at the decision level wait for the owner too; they open the overseer.
        assertEquals(AlertChannel.CARTABLE, AlertRules.ofNotification(note("n3", "decision", "ناظر کل نگه داشت", "hold", "H-0004")).channel)
        assertEquals("oversight", AlertRules.ofNotification(note("n3", "decision", "ناظر کل نگه داشت", "hold", "H-0004")).route)

        val report = AlertRules.ofNotification(note("n4", "report", "گزارش صبح", "deliverable", "O-000051"))
        assertEquals(AlertChannel.OUTPUTS, report.channel)
        assertEquals("deliverable:O-000051", report.key)
        assertEquals("outputs/O-000051", report.route)

        // A meeting's ref opens the meeting room, never the work page (Refs).
        assertEquals("meetings/MT-0012", AlertRules.ofNotification(note("n5", "urgent", "جلسه‌ی اضطراری", "meeting", "MT-0012")).route)
        // No body: the line says what it is about.
        assertEquals("تصمیم", AlertRules.ofNotification(note("n6", "decision", "کارت", "decision", "D-1")).text)
        // Raised again while it stands: the count leads the line.
        assertEquals("۳ بار · ۹۵٪ پر", AlertRules.ofNotification(note("n1", "urgent", "دیسک هاب پر است", body = "۹۵٪ پر"), 3).text)
    }

    @Test
    fun onlyTheLevelsThatReachThePhoneAreTriggers() {
        assertNotNull(AlertRules.trigger(raised("a", "urgent")))
        assertNotNull(AlertRules.trigger(raised("b", "decision", "decision", "D-1")))
        assertNotNull(AlertRules.trigger(raised("c", "report")))
        assertNull(AlertRules.trigger(raised("d", "info")))
        assertNull(AlertRules.trigger(raised("e", "learning")))
        // Chatty events are not alerts at all.
        assertNull(AlertRules.trigger(ev("run.started", "run-1")))
        assertNull(AlertRules.trigger(ev("activity.changed", "TY-CEO")))
        assertNull(AlertRules.trigger(ev("work.updated", "W-1", d = arrayOf("status" to "in_progress"))))
        // A deploy freeze or a new company is a control change but not a kill switch.
        assertNull(AlertRules.trigger(ev("control.changed", "company:FX", d = arrayOf("deploy_freeze_until" to now, "by" to "FX-CEO"))))
        assertNull(AlertRules.trigger(ev("control.changed", "FX", d = arrayOf("change" to "company.created"))))
        assertEquals(Trigger.Decided("D-1"), AlertRules.trigger(ev("decision.decided", "D-1", d = arrayOf("status" to "approved"))))
        assertEquals(Trigger.Output("O-1", "W-2", "W-1"), AlertRules.trigger(ev("deliverable.created", "O-1", d = arrayOf("work" to "W-2", "root_ref" to "W-1"))))
    }

    @Test
    fun aKillSwitchIsUrgentUnlessTheOwnerMovedIt() {
        fun sw(scope: String, state: String, by: String) =
            AlertRules.trigger(ev("control.changed", scope, d = arrayOf("kill_switch" to state, "scope" to scope, "by" to by))) as Trigger.Switch
        assertNull(AlertRules.ofSwitch(sw("holding", "engaged", "owner")))
        val holding = AlertRules.ofSwitch(sw("holding", "engaged", "HQ-OVERSEER"))!!
        assertEquals(AlertChannel.URGENT, holding.channel)
        assertEquals("کل هلدینگ متوقف شد", holding.title)
        assertTrue(holding.text.contains("ناظر کل"))
        assertEquals("control", holding.route)
        assertEquals("control:holding", holding.key)
        val company = AlertRules.ofSwitch(sw("company:FX", "engaged", "FX-CEO"))!!
        assertEquals("شرکت FX متوقف شد", company.title)
        // Named as the owner calls it once the names are read; an unknown actor is not shown by its raw code.
        com.coinepro.hq.core.link.CompanyNames.set(mapOf("TY" to "تریدیار"))
        assertEquals("تریدیار متوقف شد", AlertRules.ofSwitch(sw("company:TY", "engaged", "TY-CEO"))!!.title)
        assertTrue(AlertRules.ofSwitch(sw("company:TY", "engaged", "TY-X-9"))!!.text.contains("یکی از ایجنت‌ها"))
        com.coinepro.hq.core.link.CompanyNames.set(emptyMap())
        assertTrue(company.text.contains("مدیرعامل"))
        assertEquals("companies/FX", company.route)
        // Released: the same notification is replaced (same key), not a second one.
        val released = AlertRules.ofSwitch(sw("company:FX", "released", "FX-CEO"))!!
        assertEquals(company.key, released.key)
        assertEquals(AlertTone.INFO, released.tone)
    }

    @Test
    fun anOrdersStageOpensTheOrderOrItsOutput() {
        val delivered = AlertRules.ofOrder(OrderNotice(NoticeKind.DELIVERED, "W-000211", "داشبورد سیگنال", "FX", "id-2", deliverable = "O-000060"))
        assertEquals(AlertChannel.ORDERS, delivered.channel)
        assertEquals("outputs/O-000060", delivered.route)
        assertEquals("order:W-000211", delivered.key)
        assertEquals("خروجی", delivered.action)
        assertEquals("فرمان W-000211 تحویل شد", delivered.title)
        val failed = AlertRules.ofOrder(OrderNotice(NoticeKind.FAILED, "W-000204", "کمپین", "PC", "id-7"))
        assertEquals("work/id-7", failed.route)
        assertEquals(AlertTone.ERROR, failed.tone)
        // Every stage of one order is one notification, replaced as it moves.
        assertEquals(failed.key, AlertRules.ofOrder(OrderNotice(NoticeKind.DONE, "W-000204", "کمپین", "PC", "id-7")).key)
    }

    // ------------------------------------------------------------ center --
    private class Fakes {
        val posted = mutableListOf<Alert>()
        val cancelled = mutableListOf<String>()
        val readCancelled = mutableListOf<String>()
        var unread = mutableListOf<Notification>()
        var reads = 0
        var down = false
        val decisions = mutableMapOf<String, String>()
        val outputs = mutableMapOf<String, OutputBrief>()
        val sink = object : AlertSink {
            override fun allowed() = true
            override fun post(alert: Alert) { posted += alert }
            override fun cancel(key: String) { cancelled += key }
            override fun cancelRead(notificationIds: Collection<String>) { readCancelled += notificationIds }
            override fun sessionExpired(show: Boolean) = Unit
        }
        val source = object : AlertSource {
            override suspend fun unread(limit: Int): List<Notification> {
                reads++
                if (down) throw java.io.IOException("no answer")
                return unread.toList()
            }
            override suspend fun decisionStatus(ref: String) = decisions[ref]
            override suspend fun deliverable(ref: String) = outputs[ref]
        }
    }

    private fun TestScope.center(
        f: Fakes, store: LinkStore = MemoryLinkStore(), fg: Boolean = false, read: Set<String> = emptySet(), owners: Set<String> = emptySet(),
        clock: () -> Long = { 1_000_000L },
    ) = AlertCenter(CoroutineScope(UnconfinedTestDispatcher(testScheduler)), f.source, store, f.sink, { fg }, readHere = { it in read }, ownerOrder = { it in owners }, now = clock)

    @Test
    fun anEventIsToldOnceEvenWhenReplayed() = runTest {
        val f = Fakes()
        f.unread += note("n1", "urgent", "دیسک هاب پر است")
        val store = MemoryLinkStore()
        val e = raised("n1", "urgent", id = "4711")
        center(f, store).handle(e)
        center(f, store).handle(e) // a reconnect replays it (Last-Event-ID), or a restarted process with the same store
        assertEquals(1, f.posted.size)
        assertEquals("دیسک هاب پر است", f.posted.single().title)
    }

    @Test
    fun whatIsAlreadyReadIsNotTold() = runTest {
        val f = Fakes()
        f.unread += note("n2", "decision", "کارت قدیمی", "decision", "D-2")
        val c = center(f, read = setOf("n3"))
        // Read on the web: not in the unread page any more.
        c.handle(raised("n1", "urgent"))
        // Marked read in the app a moment ago (the hub has not confirmed it yet).
        c.handle(raised("n3", "urgent"))
        // Unread, but its card was decided on the web.
        f.decisions["D-2"] = "approved"
        c.handle(raised("n2", "decision", "decision", "D-2"))
        assertTrue(f.posted.isEmpty())
        // A pending card is told; deciding it elsewhere takes the alert away.
        f.unread += note("n4", "decision", "تصمیم تازه D-4", "decision", "D-4")
        f.decisions["D-4"] = "pending"
        c.handle(raised("n4", "decision", "decision", "D-4"))
        assertEquals("decision:D-4", f.posted.single().key)
        c.handle(ev("decision.decided", "D-4", d = arrayOf("status" to "approved")))
        assertEquals(listOf("decision:D-4"), f.cancelled)
        // Read in the app later: its alert leaves the shade.
        c.read(listOf("n4"))
        assertEquals(listOf("n4"), f.readCancelled)
    }

    @Test
    fun theSameAlertAgainUpdatesItsCount() = runTest {
        val f = Fakes()
        val c = center(f)
        f.unread += note("f1", "decision", "یافته‌ی جدی ناظر کل: disk 90.4%", "finding", "FI-0211")
        c.handle(raised("f1", "decision", "finding", "FI-0211"))
        f.unread.add(0, note("f2", "decision", "یافته‌ی جدی ناظر کل: disk 91.2%", "finding", "FI-0212"))
        c.handle(raised("f2", "decision", "finding", "FI-0212"))
        assertEquals(2, f.posted.size)
        assertEquals(f.posted[0].key, f.posted[1].key)
        assertEquals(2, f.posted[1].count)
        assertTrue(f.posted[1].text.startsWith("۲ بار"))
    }

    @Test
    fun whileTheAppIsOnScreenItsToastSpeaksNotTheNotifications() = runTest {
        val f = Fakes()
        f.unread += note("n1", "urgent", "دیسک هاب پر است")
        val c = center(f, fg = true)
        val toasts = mutableListOf<Alert>()
        val listening = backgroundScope.launch(UnconfinedTestDispatcher(testScheduler)) { c.inApp.collect { toasts += it } }
        c.handle(raised("n1", "urgent"))
        c.handle(OrderNotice(NoticeKind.DONE, "W-1", "گزارش", "TY", "id-1"))
        assertTrue(f.posted.isEmpty())
        assertEquals(listOf("دیسک هاب پر است", "فرمان W-1 تمام شد"), toasts.map { it.title })
        // An output makes no toast (the app's badge shows it) and is not told later either.
        f.outputs["O-9"] = OutputBrief("O-9", "گزارش", "TY", seen = false, report = false)
        c.handle(ev("deliverable.created", "O-9"))
        assertEquals(2, toasts.size)
        listening.cancel()
        // On screen but nothing listening (the lock screen, a sheet without the shell): the notification speaks.
        f.unread.add(0, note("n2", "urgent", "دوم"))
        c.handle(raised("n2", "urgent"))
        assertEquals(listOf("دوم"), f.posted.map { it.title })
    }

    @Test
    fun outputsAreToldOnceAndNotForTheOwnersOrders() = runTest {
        val f = Fakes()
        f.outputs["O-1"] = OutputBrief("O-1", "تحلیل رقبا", "TY", seen = false, report = false)
        f.outputs["O-2"] = OutputBrief("O-2", "دیده‌شده", "TY", seen = true, report = false)
        f.outputs["O-3"] = OutputBrief("O-3", "خروجی فرمان", "FX", seen = false, report = false)
        val c = center(f, owners = setOf("W-000211"))
        c.handle(ev("deliverable.created", "O-1"))
        c.handle(ev("deliverable.created", "O-2"))
        c.handle(ev("deliverable.created", "O-3", d = arrayOf("work" to "W-000214", "root_ref" to "W-000211")))
        assertEquals(listOf("deliverable:O-1"), f.posted.map { it.key })
        assertEquals(AlertChannel.OUTPUTS, f.posted.single().channel)
        // The hub's report about the same output later is the same alert: not told again.
        f.unread += note("r1", "report", "گزارش تحلیل رقبا", "deliverable", "O-1")
        c.handle(raised("r1", "report", "deliverable", "O-1"))
        assertEquals(1, f.posted.size)
    }

    @Test
    fun theHoldingsSwitchArrivesOncePerCompanyAndIsToldOnce() = runTest {
        val f = Fakes()
        var t = 1_000_000L
        val c = center(f, clock = { t })
        for (co in listOf("HQ", "TY", "FX", "PC")) {
            c.handle(ev("control.changed", "holding", co, d = arrayOf("kill_switch" to "engaged", "scope" to "holding", "by" to "HQ-OVERSEER")))
        }
        assertEquals(1, f.posted.size)
        // Released later: told (the same notification, replaced).
        t += 60_000
        c.handle(ev("control.changed", "holding", "HQ", d = arrayOf("kill_switch" to "released", "scope" to "holding", "by" to "HQ-OVERSEER")))
        assertEquals(listOf("کل هلدینگ متوقف شد", "هلدینگ دوباره راه افتاد"), f.posted.map { it.title })
    }

    @Test
    fun whenTheHubCannotBeReadOnlyAnUrgentOneIsToldInGeneralWords() = runTest {
        val f = Fakes()
        f.down = true
        val store = MemoryLinkStore()
        val c = center(f, store)
        c.handle(raised("n1", "urgent", id = "10"))
        c.handle(raised("n2", "decision", "decision", "D-5", id = "11"))
        assertEquals(listOf("اعلان فوری تازه از ستاد"), f.posted.map { it.title })
        // The card was not told and not remembered: a replay once the hub answers tells it.
        assertTrue(store.told("ev:10"))
        assertTrue(!store.told("ev:11"))
        f.down = false
        f.unread += note("n2", "decision", "تصمیم تازه D-5", "decision", "D-5")
        f.decisions["D-5"] = "pending"
        c.handle(raised("n2", "decision", "decision", "D-5", id = "11"))
        assertEquals("تصمیم تازه D-5", f.posted.last().title)
    }

    @Test
    fun aBurstOfRaisesReadsTheUnreadPageOnce() = runTest {
        val f = Fakes()
        val c = center(f)
        for (i in 1..5) f.unread += note("b$i", "urgent", "هشدار $i")
        for (i in 1..5) c.handle(raised("b$i", "urgent"))
        assertEquals(5, f.posted.size)
        assertEquals(1, f.reads)
    }
}
