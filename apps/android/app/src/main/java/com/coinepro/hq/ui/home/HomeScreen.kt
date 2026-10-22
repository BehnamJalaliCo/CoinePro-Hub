package com.coinepro.hq.ui.home

import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.absoluteOffset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.remember
import androidx.compose.ui.AbsoluteAlignment
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.WORK_STATUS
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.format.jTime
import com.coinepro.hq.core.format.jWeekday
import com.coinepro.hq.core.format.tokens
import com.coinepro.hq.core.format.usd
import com.coinepro.hq.core.net.Company
import com.coinepro.hq.core.net.StreamEvent
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.CompanyMark
import com.coinepro.hq.designsystem.Avatar
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.MeterBar
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.Seal
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.StatTile
import com.coinepro.hq.designsystem.budgetTone
import com.coinepro.hq.designsystem.fig
import androidx.compose.ui.text.buildAnnotatedString
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.Loadable
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.cartable.DecisionRow
import com.coinepro.hq.ui.companyOf
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.stories.StoriesBar
import com.coinepro.hq.ui.workshop.SessionRow
import com.coinepro.hq.ui.workshop.rememberGrants
import com.coinepro.hq.ui.workshop.rememberSessions
import com.coinepro.hq.ui.workshop.rememberWorkspaces
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.shell.LocalLive
import com.coinepro.hq.core.data.StreamState
import java.time.LocalTime
import java.time.ZoneId
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sin

/** The command center (D2): greeting, what happened while away, the four numbers, the cartable, the live
 *  holding orbit, today from the planner, and the month's budgets. */
@Composable
fun HomeScreen(onNewOrder: () -> Unit, onVoiceOrder: () -> Unit = {}) {
    val nav = LocalNav.current
    val inbox = rememberQuery("inbox", "inbox", maxAgeMs = 30_000) { inbox() }
    val away = rememberQuery("away", "away") { away() }
    val presence = rememberQuery("presence", "presence") { presence() }
    val day = rememberQuery("treasury:day", "treasury") { treasury("day") }
    val month = rememberQuery("treasury:month", "treasury") { treasury("month") }
    val pending = rememberQuery("decisions:pending", "decisions") { decisions("pending") }
    val today = com.coinepro.hq.core.format.HqClock.today().toString()
    val planner = rememberQuery("planner:$today", "planner", "work") { planner(today, today) }
    val companies = rememberCompanies()
    val sessions = rememberSessions()
    val workspaces = rememberWorkspaces()
    val grants = rememberGrants()
    val r = refresher(inbox, away, presence, day, month, pending, planner, sessions)
    val c = Divan.colors

    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item {
            val h = LocalTime.ofInstant(com.coinepro.hq.core.format.HqClock.now(), ZoneId.of(com.coinepro.hq.core.format.OWNER_TZ)).hour  // the pinned clock, so screenshots do not change with the time of day
            val hello = when { h < 12 -> "صبح بخیر"; h < 17 -> "روز بخیر"; else -> "عصر بخیر" }
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text(jWeekday(com.coinepro.hq.core.format.HqClock.now().toString()), style = Divan.type.caption, color = c.textMuted)
                Text("$hello، مدیر کل", style = Divan.type.display.copy(fontSize = Divan.type.h1.fontSize, lineHeight = Divan.type.h1.lineHeight))
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp), itemVerticalAlignment = Alignment.CenterVertically) {
                    HqButton("فرمان صوتی", onVoiceOrder, variant = BtnVariant.PRIMARY, icon = DivanIcon.MIC)
                    HqButton("فرمان تازه", onNewOrder, icon = DivanIcon.COMMAND)
                    if (presence.data?.khalvat == true) Pill("خلوت روشن؛ فقط فوری میرسد", Tone.LEARN, icon = DivanIcon.KHALVAT)
                }
            }
        }
        // ⟨1.4.3⟩ the companies' stories, at the top like Instagram (contract §18.12)
        item { StoriesBar() }
        away.data?.let { a ->
            val n = a.decisions.new + a.deliverables.new + a.messages.new
            if (n > 0) item {
                HqCard(Modifier.fillMaxWidth()) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        Box(Modifier.size(40.dp).clip(CircleShape).background(c.softGold), contentAlignment = Alignment.Center) { DIcon(DivanIcon.KHALVAT, size = 20.dp, tint = c.goldInk) }
                        Column(Modifier.weight(1f)) {
                            Text("در نبودت چه گذشت", style = Divan.type.bodyStrong)
                            Text("از ${ago(a.since)}: ${a.decisions.new} تصمیم تازه، ${a.deliverables.new} خروجی، ${a.messages.new} پیام", style = Divan.type.caption, color = c.textSecondary)
                        }
                    }
                }
            }
        }
        item {
            val i = inbox.data
            if (i == null) Skeleton(Modifier.fillMaxWidth().height(220.dp), radius = 14.dp)
            else Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    StatTile("منتظر مُهر تو", i.decisionsPending.toString(), Modifier.weight(1f).clickable { nav.go("cartable") },
                        sub = if (i.decisionsByRisk.high > 0) "${i.decisionsByRisk.high} با ریسک بالا" else "بدون ریسک بالا",
                        tone = if (i.decisionsByRisk.high > 0) Tone.WARN else null, figure = false)
                    StatTile("خروجی بی‌امتیاز", i.deliverablesUnrated.toString(), Modifier.weight(1f).clickable { nav.go("outputs") }, sub = "امتیاز تو ۴۰٪ نمره‌ی کارمند است", figure = false)
                }
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    StatTile("پیام نخوانده", i.messagesUnread.toString(), Modifier.weight(1f).clickable { nav.go("messages") }, sub = "از مدیرعامل‌ها و مشاور", figure = false)
                    val t = day.data?.totals
                    StatTile("مصرف امروز (معادل)", usd(t?.equivCostUsd), Modifier.weight(1f).clickable { nav.go("treasury") },
                        subRich = t?.let { buildAnnotatedString { fig(tokens(it.inputTokens + it.outputTokens)); append(" توکن، ${it.calls} فراخوانی") } })
                }
            }
        }
        item { OverseerCard() }
        item {
            HqCard(Modifier.fillMaxWidth()) {
                SectionTitle("کارتابل", note = "فقط چیزهایی که مُهر تو را لازم دارند") {
                    HqButton("همه", { nav.go("cartable") }, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.NEXT)
                }
                Loadable(pending) { page ->
                    if (page.items.isEmpty()) Empty("کارتابل خالی است", icon = DivanIcon.SEAL, body = "هر تصمیمی که امضای تو را بخواهد این‌جا میاید.")
                    else Column(Modifier.padding(top = 6.dp)) {
                        page.items.take(5).forEach { d -> DecisionRow(d, companies) { nav.go("cartable/${d.ref}") } }
                    }
                }
            }
        }
        // Code Workshop sessions that are moving or waiting for the owner; nothing when none are.
        val open = sessions.data.orEmpty().filter { it.open }.sortedByDescending { it.state == "waiting_approval" }
        if (open.isNotEmpty()) item {
            HqCard(Modifier.fillMaxWidth()) {
                val waiting = open.count { it.state == "waiting_approval" }
                SectionTitle("کارگاه کد", note = if (waiting > 0) "$waiting جلسه منتظر اجازه‌ی تو" else "${open.size} جلسه در جریان") {
                    HqButton("کارگاه", { nav.go("workshop") }, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.NEXT)
                }
                Column(Modifier.padding(top = 8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    open.take(3).forEach { s -> SessionRow(s, workspaces.data, grants.data?.firstOrNull { it.ref == s.grant }) { nav.go("workshop/${s.ref}") } }
                }
            }
        }
        item { LiveCard(companies) }
        item {
            HqCard(Modifier.fillMaxWidth()) {
                SectionTitle("امروز", note = "از پلنر") { HqButton("پلنر", { nav.go("planner") }, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.NEXT) }
                val items = planner.data?.days?.firstOrNull()?.items.orEmpty()
                when {
                    planner.data == null -> Skeleton(Modifier.fillMaxWidth().height(80.dp).padding(top = 8.dp))
                    items.isEmpty() -> Text("برای امروز کاری ثبت نشده.", style = Divan.type.caption, color = c.textMuted, modifier = Modifier.padding(vertical = 16.dp).fillMaxWidth())
                    else -> Column(Modifier.padding(top = 6.dp)) {
                        items.forEachIndexed { idx, it ->
                            if (idx > 0) HorizontalDivider(color = c.lineDivider)
                            Row(Modifier.fillMaxWidth().clickable { nav.go("work/${it.ref}") }.padding(vertical = 10.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                                Text(jTime(it.at), style = Divan.type.caption, color = c.textMuted, modifier = Modifier.width(40.dp))
                                Box(Modifier.size(8.dp).clip(CircleShape).background(if (it.status == "done") c.positive else if (it.priority <= "P1") c.negative else c.silverInk))
                                Text(it.title, style = Divan.type.small, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
                                if (it.recurring) DIcon(DivanIcon.REFRESH, size = 14.dp, tint = c.textMuted)
                                CompanyMark(it.company, height = 12.dp, mono = true, ink = c.textSecondary)
                                Text(WORK_STATUS[it.status] ?: it.status, style = Divan.type.micro, color = c.textMuted)
                            }
                        }
                    }
                }
            }
        }
        item {
            HqCard(Modifier.fillMaxWidth()) {
                SectionTitle("بودجه‌ی ماه", note = "هشدار در ۷۰٪ و ۹۰٪") { HqButton("خزانه", { nav.go("treasury") }, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.NEXT) }
                Loadable(month) { m ->
                    Column(Modifier.padding(top = 8.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                        m.budgets.forEach { b -> BudgetLine(b.scopeType == "holding", b.company, companyOf(companies, b.company).nameFa, b.tokensUsed, b.tokenLimit, b.pct) }
                    }
                }
            }
        }
    }
}

@Composable
fun BudgetLine(holding: Boolean, code: String, name: String, used: Long, limit: Long?, pct: Double?) {
    val c = Divan.colors
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            if (holding) Text("کل هلدینگ", style = Divan.type.caption, color = c.textSecondary)
            else {
                CompanyMark(code, height = 13.dp, mono = true, ink = c.textSecondary)
                Text(name, style = Divan.type.caption, color = c.textSecondary)
            }
            Box(Modifier.weight(1f))
            Fig("${tokens(used)} / ${tokens(limit)}", style = Divan.type.figureSmall, color = c.textMuted)
            val p = pct ?: 0.0
            Text("${p.toInt()}٪", style = Divan.type.caption, color = when { p >= 90 -> c.negative; p >= 70 -> c.warning; else -> c.textSecondary }, modifier = Modifier.width(36.dp))
        }
        MeterBar(pct ?: 0.0, tone = budgetTone(pct))
    }
}

@Composable
private fun LiveCard(companies: List<Company>) {
    val c = Divan.colors
    val live = LocalLive.current
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("استریم زنده‌ی هلدینگ", note = "ذره‌ی طلایی فرمان تو، نقره‌ای تحویل ایجنت‌ها") {
            Pill(if (live.state == StreamState.LIVE) "زنده" else "قطع", if (live.state == StreamState.LIVE) Tone.POS else Tone.WARN, live = live.state == StreamState.LIVE)
        }
        if (companies.isEmpty()) Skeleton(Modifier.fillMaxWidth().aspectRatio(1f).padding(top = 8.dp), radius = 999.dp)
        else Orbit(companies, live.last, Modifier.padding(vertical = 8.dp))
        HorizontalDivider(color = c.lineDivider)
        Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            if (live.feed.isEmpty()) Text("هنوز رویدادی نرسیده؛ ایجنت‌ها تا رسیدن کار خواب‌اند.", style = Divan.type.caption, color = c.textMuted)
            live.feed.take(4).forEach { e ->
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Box(Modifier.size(6.dp).clip(CircleShape).background(c.silverInk))
                    e.company?.let { CompanyMark(it, height = 12.dp, mono = true, ink = c.textSecondary) }
                    Fig(e.type, style = Divan.type.figureSmall, color = c.textMuted, modifier = Modifier.weight(1f))
                    Text(if (e.at.isBlank()) "همین الان" else ago(e.at), style = Divan.type.micro, color = c.textMuted)
                }
            }
        }
    }
}

private data class Pulse(val id: Long, val company: String, val out: Boolean)

/** The holding orbit (D2·2): the holding seal at the centre, every company on the ring; gold particles are the
 *  owner's orders going out, silver ones are deliveries coming back. Any number of companies. */
@Composable
fun Orbit(companies: List<Company>, last: StreamEvent?, modifier: Modifier = Modifier) {
    val nav = LocalNav.current
    val c = Divan.colors
    val ring = companies.filter { it.kind != "holding" }
    val holding = companies.firstOrNull { it.kind == "holding" }
    val pulses = remember { mutableStateListOf<Pair<Pulse, Animatable<Float, *>>>() }
    LaunchedEffect(last) {
        val e = last ?: return@LaunchedEffect
        val co = e.company ?: return@LaunchedEffect
        if (co == holding?.code || ring.none { it.code == co }) return@LaunchedEffect
        val out = e.type.startsWith("work") && (e.type.contains("delegated") || e.type.contains("created"))
        val a = Animatable(0f)
        val p = Pulse(System.nanoTime(), co, out) to a
        pulses.add(p)
        while (pulses.size > 10) pulses.removeAt(0)
        a.animateTo(1f, tween(1600, easing = LinearEasing))
        pulses.remove(p)
    }
    BoxWithConstraints(modifier.fillMaxWidth().aspectRatio(1f)) {
        val s = min(maxWidth.value, 520f)
        val sizeDp = s.dp
        val cx = s / 2
        val r = s * 0.38f
        val node = max(44f, min(68f, (2 * PI.toFloat() * r) / max(ring.size, 1) / 2.2f))
        fun pos(i: Int): Offset {
            val a = -PI / 2 + 2 * PI * i / max(ring.size, 1)
            return Offset(cx + r * cos(a).toFloat(), cx + r * sin(a).toFloat())
        }
        Box(Modifier.size(sizeDp).align(Alignment.Center)) {
            Canvas(Modifier.size(sizeDp)) {
                val k = size.width / s
                drawCircle(c.lineTahrir, r * k, Offset(cx * k, cx * k), style = androidx.compose.ui.graphics.drawscope.Stroke(1f, pathEffect = PathEffect.dashPathEffect(floatArrayOf(4f, 12f))))
                drawCircle(c.lineDivider, r * 0.52f * k, Offset(cx * k, cx * k), style = androidx.compose.ui.graphics.drawscope.Stroke(1f))
                ring.forEachIndexed { i, _ -> drawLine(c.lineDivider, Offset(cx * k, cx * k), pos(i) * k, 1f) }
                for ((p, a) in pulses) {
                    val i = ring.indexOfFirst { it.code == p.company }
                    if (i < 0) continue
                    val from = if (p.out) Offset(cx, cx) else pos(i)
                    val to = if (p.out) pos(i) else Offset(cx, cx)
                    val t = a.value
                    val alpha = when { t < 0.15f -> t / 0.15f; t > 0.85f -> (1 - t) / 0.15f; else -> 1f }
                    drawCircle((if (p.out) c.goldFill else c.silverInk).copy(alpha = alpha), 4.dp.toPx(), (from + (to - from) * t) * k)
                }
            }
            Box(Modifier.align(Alignment.Center)) {
                Seal(holding?.code ?: "HQ", holding?.nameFa ?: "هلدینگ", holding?.nameEn ?: "Holding", holding = true, size = (s * 0.27f).dp)
            }
            ring.forEachIndexed { i, co ->
                val p = pos(i)
                val active = pulses.any { it.first.company == co.code }
                val locked = co.killSwitch == "engaged"
                Column(
                    Modifier
                        .align(AbsoluteAlignment.TopLeft)
                        .absoluteOffset { IntOffset(((p.x - 50f).dp.roundToPx()), ((p.y - node / 2).dp.roundToPx())) }
                        .width(100.dp)
                        .clickable(role = Role.Button) { nav.go("companies/${co.code}") }
                        .semantics { contentDescription = "${co.nameFa}: ${co.counts.workOpen} کار باز، ${co.counts.decisionsPending} تصمیم منتظر" },
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.spacedBy(4.dp),
                ) {
                    Box(
                        Modifier
                            .size(node.dp)
                            .clip(CircleShape)
                            .background(c.tile)
                            .border(if (active) 2.dp else 1.dp, if (locked) c.negative else if (active) c.textPrimary else c.lineStrong, CircleShape),
                        contentAlignment = Alignment.Center,
                    ) { CompanyMark(co.code, height = (node * 0.42f).dp, ink = c.textPrimary) }
                    Text(co.nameFa ?: co.code, style = Divan.type.micro.copy(fontWeight = androidx.compose.ui.text.font.FontWeight.SemiBold), maxLines = 1)
                    Text("${co.counts.workOpen} کار باز", style = Divan.type.micro, color = c.textMuted)
                }
                if (co.counts.decisionsPending > 0) {
                    com.coinepro.hq.designsystem.Badge(
                        co.counts.decisionsPending,
                        Modifier.align(AbsoluteAlignment.TopLeft).absoluteOffset { IntOffset(((p.x + node / 2 - 12f).dp.roundToPx()), ((p.y - node / 2 - 4f).dp.roundToPx())) },
                    )
                }
            }
        }
    }
}

/** The Chief Overseer at a glance (contract §18.1): what it holds for the owner, how many serious findings are open,
 *  and the last "while you were away" report. Gold-ringed when something waits on the owner. */
@Composable
private fun OverseerCard() {
    val nav = LocalNav.current
    val c = Divan.colors
    val q = rememberQuery("oversight:summary", "oversight", maxAgeMs = 30_000) { oversight() }
    val s = q.data ?: return
    val serious = (s.findingsOpen["critical"] ?: 0) + (s.findingsOpen["high"] ?: 0)
    HqCard(Modifier.fillMaxWidth(), tahrir = s.holdsWaiting > 0, onClick = { nav.go("oversight") }) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Avatar("overseer", size = 44.dp, state = if (s.watch.on) "working" else "idle")
            Column(Modifier.weight(1f)) {
                Text("ناظر کل", style = Divan.type.bodyStrong)
                Text(
                    listOfNotNull(
                        s.holdsWaiting.takeIf { it > 0 }?.let { "$it اقدام نگه‌داشته منتظر تو" },
                        serious.takeIf { it > 0 }?.let { "$it یافته‌ی جدی" },
                    ).joinToString("، ").ifEmpty { "همه‌چیز زیر نظر است" },
                    style = Divan.type.caption, color = if (s.holdsWaiting > 0 || serious > 0) c.negative else c.textSecondary,
                )
            }
            DIcon(DivanIcon.NEXT, size = 18.dp, tint = c.textMuted)
        }
        if (s.watch.summaryMd.isNotBlank()) com.coinepro.hq.designsystem.Md(s.watch.summaryMd, Modifier.padding(top = 10.dp))
    }
}
