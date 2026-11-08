package com.coinepro.hq.ui.live

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.clipPath
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.coinepro.hq.core.data.CompanyLive
import com.coinepro.hq.core.data.LiveState
import com.coinepro.hq.core.data.activityOrder
import com.coinepro.hq.core.data.ageFa
import com.coinepro.hq.core.data.companyStateOf
import com.coinepro.hq.core.data.dotsOf
import com.coinepro.hq.core.data.faNum
import com.coinepro.hq.core.data.inFlight
import com.coinepro.hq.core.data.pulseOf
import com.coinepro.hq.core.data.spendPct
import com.coinepro.hq.designsystem.CompanyMark
import com.coinepro.hq.designsystem.Crossfading
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.Glint
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.WorkBand
import com.coinepro.hq.designsystem.animateFill
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.v16.companyColor
import java.util.Locale

// Contract §42 ⟨1.24⟩ ⟨0.20.0⟩: the office's live views. OF-1 the pulse (is my holding working, is anything waiting for me), MO-1 the
// token meter (the holding's real cost, moving as it is spent), CO-1 each company's live card (alive, working, healthy, what it costs
// today) — any number of companies.

// ------------------------------------------------------------------ figures --
/** «12.8K», «1.86M», «940» — a token figure, Latin. */
fun tokFig(n: Long): String = when {
    n >= 1_000_000 -> String.format(Locale.US, "%.2fM", n / 1_000_000.0)
    n >= 1_000 -> String.format(Locale.US, "%.1fK", n / 1_000.0)
    else -> n.toString()
}

/** «$11.70» — dollars with cents, Latin. */
fun usdCents(v: Double): String = String.format(Locale.US, "$%,.2f", v)

// ------------------------------------------------------------------ OF-1 --
/**
 * OF-1 «نبض دفتر»: four figures on top of the office — who works now (of all), sessions moving, what waits for the owner (cards to seal
 * and sessions on his turn), tokens a minute. A figure changes by crossfade (M2) and its tahrir glints once (M13): gold when it concerns
 * the owner, silver for the agents' work. Missing data is «—».
 */
@Composable
fun OfficePulse(modifier: Modifier = Modifier) {
    val c = Divan.colors
    val nav = LocalNav.current
    val live = rememberLive()
    val now = rememberTicker(15_000)
    val p = pulseOf(live, now)
    Column(modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("نبض دفتر", style = Divan.type.h3, modifier = Modifier.weight(1f))
            MissedChip()
            LiveBeat(compact = true)
        }
        Row(Modifier.fillMaxWidth().height(androidx.compose.foundation.layout.IntrinsicSize.Min), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            PulseTile(
                "الان کار میکنند", p.working?.let { faNum(it) } ?: "—", p.total?.let { "از ${faNum(it)}" }, gold = false,
                note = "مدلی فکر میکند یا ابزاری کار میکند", modifier = Modifier.weight(1f).fillMaxHeight(),
            )
            PulseTile("سشن در جریان", p.moving?.let { faNum(it) } ?: "—", null, gold = false, note = "کاری که الان قدمی دارد", modifier = Modifier.weight(1f).fillMaxHeight(), onClick = { nav.go("sessions") })
        }
        Row(Modifier.fillMaxWidth().height(androidx.compose.foundation.layout.IntrinsicSize.Min), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            PulseTile("منتظر تو", p.waitingYou?.let { faNum(it) } ?: "—", null, gold = true, note = "تصمیم برای مُهر و سشن در نوبت تو", modifier = Modifier.weight(1f).fillMaxHeight(), onClick = { nav.go("cartable") })
            PulseTile("توکن در دقیقه", p.perMin?.let(::tokFig) ?: "—", null, gold = false, figure = p.perMin != null, note = "خزانه‌ی توکن · زنده", modifier = Modifier.weight(1f).fillMaxHeight())
        }
    }
}

@Composable
private fun PulseTile(label: String, value: String, sub: String?, gold: Boolean, note: String, modifier: Modifier = Modifier, figure: Boolean = false, onClick: (() -> Unit)? = null) {
    val c = Divan.colors
    HqCard(modifier.semantics(mergeDescendants = true) { liveRegion = LiveRegionMode.Polite }, onClick = onClick, padding = PaddingValues(horizontal = 14.dp, vertical = 12.dp)) {
        Text(label, style = Divan.type.caption, color = c.textSecondary, maxLines = 1)
        Row(Modifier.padding(top = 2.dp), verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            Crossfading(value) { v ->
                if (figure) Fig(v, style = Divan.type.figureL.copy(fontSize = 26.sp, lineHeight = 34.sp, fontWeight = FontWeight.Bold), color = c.textPrimary)
                else Text(v, style = Divan.type.h1.copy(fontSize = 26.sp, lineHeight = 34.sp, fontWeight = FontWeight.Bold), color = if (gold && v != "—" && v != "۰") c.goldInk else c.textPrimary)
            }
            sub?.let { Text(it, style = Divan.type.caption, color = c.textMuted, modifier = Modifier.padding(bottom = 4.dp)) }
        }
        Glint(value, gold, Modifier.padding(vertical = 6.dp))
        Text(note, style = Divan.type.micro, color = c.textMuted, maxLines = 2, overflow = TextOverflow.Ellipsis)
    }
}

// ------------------------------------------------------------------ MO-1 --
/** MO-1's state in words and tone: under 70 %, past 70, past 90, the budget reached. */
internal fun meterStateFa(pct: Double?): Pair<String, com.coinepro.hq.core.format.Tone> = when {
    pct == null -> "بی‌سقف" to com.coinepro.hq.core.format.Tone.SILVER
    pct >= 100 -> "سقف رسید" to com.coinepro.hq.core.format.Tone.NEG
    pct >= 90 -> "نزدیک سقف" to com.coinepro.hq.core.format.Tone.WARN
    pct >= 70 -> "از ۷۰٪ گذشت" to com.coinepro.hq.core.format.Tone.WARN
    else -> "در محدوده" to com.coinepro.hq.core.format.Tone.POS
}

/**
 * MO-1 «کنتور توکن»: today's tokens and dollars against the daily budget. One track with marks at 70, 90 and 100 %, filled in four stacked
 * segments (input, output, cache, thinking: chart slots 1–4, 2 dp gaps) with a legend of values (the day palette carries a colour-blind
 * warning), and the burn rate a minute. The fill advances per tick (M12); the work band rides its leading edge only while calls are in
 * flight (M5). Past 70 % the mark turns amber, past 90 the fill, at 100 it is red with 🔴. The fill jumps when animations are removed.
 */
@Composable
fun TokenMeter(modifier: Modifier = Modifier) {
    val c = Divan.colors
    val live = rememberLive()
    val now = rememberTicker(10_000)
    val t = live.tokens
    val pct = spendPct(t)
    val (stateFa, tone) = meterStateFa(pct)
    val (_, toneInk) = com.coinepro.hq.designsystem.toneColors(tone)
    val flying = inFlight(t, now) > 0
    HqCard(modifier.fillMaxWidth()) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("کنتور توکن · امروز", style = Divan.type.h3, modifier = Modifier.weight(1f))
            com.coinepro.hq.designsystem.Pill(if ((pct ?: 0.0) >= 100) "🔴 $stateFa" else stateFa, tone)
            LiveBeat(compact = true)
        }
        Row(Modifier.padding(top = 8.dp), verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Crossfading(t.usdToday?.let(::usdCents) ?: "—") { v -> Fig(v, style = Divan.type.figureL.copy(fontSize = 28.sp, lineHeight = 36.sp, fontWeight = FontWeight.Bold), color = c.textPrimary) }
            Text(
                buildAnnotatedString { append("از سقف روزانه‌ی "); if (t.budgetUsd != null) fig(usdCents(t.budgetUsd)) else append("—") },
                style = Divan.type.caption, color = c.textSecondary, modifier = Modifier.padding(bottom = 5.dp).weight(1f),
            )
            Text(buildAnnotatedString { fig(t.today?.let(::tokFig) ?: "—"); append(" توکن") }, style = Divan.type.caption, color = c.textMuted, modifier = Modifier.padding(bottom = 5.dp))
        }
        MeterTrack(pct, t.kinds, Modifier.padding(top = 12.dp))
        // M5 on the fill's leading edge, only while calls are in flight (with animations removed: still, and «در حال مصرف»).
        val lead by animateFill(((pct ?: 0.0) / 100.0).toFloat().coerceIn(0f, 1f))
        androidx.compose.foundation.layout.BoxWithConstraints(Modifier.fillMaxWidth().padding(top = 2.dp)) {
            val bandW = 44.dp
            val start = (maxWidth * lead - bandW).coerceIn(0.dp, (maxWidth - bandW).coerceAtLeast(0.dp))
            if (com.coinepro.hq.designsystem.LocalReducedMotion.current) WorkBand(flying, c.goldInk, Modifier.fillMaxWidth(), height = 3.dp, word = "در حال مصرف")
            else WorkBand(flying, c.goldInk, Modifier.padding(start = start).width(bandW), height = 3.dp)
        }
        Marks(pct, Modifier.padding(top = 2.dp))
        Kinds(t.kinds, Modifier.padding(top = 10.dp))
        Row(Modifier.padding(top = 8.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("توکن در دقیقه", style = Divan.type.micro, color = c.textMuted)
            Fig(com.coinepro.hq.core.data.perMin(t, now)?.let(::tokFig) ?: "—", style = Divan.type.figureSmall, color = toneInk.takeIf { tone == com.coinepro.hq.core.format.Tone.NEG } ?: c.textSecondary)
        }
    }
}

/** The four kinds' colours (palette v2 slots 1–4, [com.coinepro.hq.designsystem.generated.TokenTypeSlot]). */
@Composable
private fun kindInks(): List<Color> = Divan.colors.chart.take(4)

@Composable
private fun MeterTrack(pct: Double?, kinds: com.coinepro.hq.core.data.TokenKinds?, modifier: Modifier = Modifier) {
    val c = Divan.colors
    val rtl = LocalLayoutDirection.current == LayoutDirection.Rtl
    val f by animateFill(((pct ?: 0.0) / 100.0).toFloat().coerceIn(0f, 1f))
    val inks = kindInks()
    val shares = kinds?.takeIf { it.total > 0 }?.let { k -> listOf(k.input, k.output, k.cache, k.thinking).map { it.toFloat() / k.total } }
    val fillInk = when {
        pct == null -> c.silverInk
        pct >= 100 -> c.negative
        pct >= 90 -> c.warning
        else -> null
    }
    Canvas(
        modifier.fillMaxWidth().height(14.dp)
            .semantics { contentDescription = pct?.let { "مصرف امروز ${faNum(it.toInt())} درصد سقف" } ?: "سقف روزانه تعیین نشده" },
    ) {
        val w = size.width
        val h = size.height
        val rad = androidx.compose.ui.geometry.CornerRadius(h / 2)
        drawRoundRect(c.tile, cornerRadius = rad)
        val total = w * f
        // The 70, 90 and 100 % marks across the track (from the start edge, as the fill grows): amber once passed, red at 100.
        fun marks() {
            for (m in listOf(70, 90, 100)) {
                val hit = (pct ?: 0.0) >= m
                val at = (w * m / 100f).coerceAtMost(w - 1.dp.toPx())
                val x = if (rtl) w - at else at
                drawLine(if (!hit) c.lineStrong else if (m == 100) c.negative else c.warning, Offset(x, -3.dp.toPx()), Offset(x, h + 3.dp.toPx()), 1.5.dp.toPx())
            }
        }
        if (total <= 0f) { marks(); return@Canvas }
        val gap = 2.dp.toPx()
        val segs = if (fillInk != null || shares == null) listOf((fillInk ?: c.silverInk) to 1f) else inks.zip(shares).filter { it.second > 0f }
        var x = 0f
        val avail = (total - gap * (segs.size - 1)).coerceAtLeast(0f)
        clipPath(androidx.compose.ui.graphics.Path().apply {
            addRoundRect(androidx.compose.ui.geometry.RoundRect(if (rtl) w - total else 0f, 0f, if (rtl) w else total, h, rad))
        }) {
            for ((ink, share) in segs) {
                val sw = avail * share
                val left = if (rtl) w - x - sw else x
                drawRect(ink, topLeft = Offset(left, 0f), size = androidx.compose.ui.geometry.Size(sw, h))
                x += sw + gap
            }
        }
        marks()
    }
}

/** The 70, 90 and 100 % marks' words under the track (their lines cross it): past 70 amber, at 100 red. */
@Composable
private fun Marks(pct: Double?, modifier: Modifier = Modifier) {
    val c = Divan.colors
    androidx.compose.foundation.layout.BoxWithConstraints(modifier.fillMaxWidth().height(14.dp)) {
        val w = maxWidth
        for (m in listOf(70, 90, 100)) {
            val hit = (pct ?: 0.0) >= m
            val ink = when {
                !hit -> c.textMuted
                m == 100 -> c.negative
                else -> c.warning
            }
            // From the start edge (right, RTL), as the fill grows.
            val x = w * (m / 100f)
            Box(Modifier.padding(start = (x - 15.dp).coerceIn(0.dp, (w - 30.dp).coerceAtLeast(0.dp))).width(30.dp), contentAlignment = Alignment.Center) {
                Text("${faNum(m)}٪", style = Divan.type.micro.copy(fontSize = 10.sp, lineHeight = 12.sp), color = ink, maxLines = 1)
            }
        }
    }
}

@Composable
private fun Kinds(k: com.coinepro.hq.core.data.TokenKinds?, modifier: Modifier = Modifier) {
    val c = Divan.colors
    val inks = kindInks()
    val rows = listOf("ورودی" to k?.input, "خروجی" to k?.output, "کش" to k?.cache, "فکر" to k?.thinking)
    Column(modifier, verticalArrangement = Arrangement.spacedBy(4.dp)) {
        for (pair in rows.chunked(2)) Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
            for ((i, r) in pair.withIndex()) {
                val idx = rows.indexOf(r)
                Row(Modifier.weight(1f), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Box(Modifier.size(10.dp).clip(RoundedCornerShape(3.dp)).background(inks[idx]))
                    Text(r.first, style = Divan.type.caption, color = c.textSecondary, modifier = Modifier.weight(1f))
                    Fig(r.second?.let(::tokFig) ?: "—", style = Divan.type.figureSmall, color = c.textSecondary)
                }
                if (i == 0 && pair.size == 1) Spacer(Modifier.weight(1f))
            }
        }
    }
}

// ------------------------------------------------------------------ CO-1 --
/** «همین الان»، «۳۵ ثانیه پیش»، «۴ دقیقه پیش» — the age of a company's last event; «—» without one. */
fun lastFa(at: Long?, now: Long): String = when {
    at == null -> "—"
    now - at < 5_000 -> "همین الان"
    else -> ageFa(now - at) + " پیش"
}

/** The companies' live state, from the store (seeded) or the list the app already has (each «—» until the store knows). */
@Composable
fun rememberLiveCompanies(live: LiveState): List<CompanyLive> {
    val list = rememberCompanies()
    val codes = (live.companies.keys + list.filter { it.kind != "holding" && it.status != "archived" }.map { it.code }).distinct().filter { it != "HQ" }
    val named = codes.map { code -> (live.companies[code] ?: CompanyLive(code)).let { cl -> cl.copy(nameFa = cl.nameFa.ifBlank { list.firstOrNull { it.code == code }?.nameFa ?: code }) } }
    return activityOrder(named.map { it.code }, live.companies).mapNotNull { code -> named.firstOrNull { it.code == code } }
}

/**
 * CO-1: one company at a glance — its mark with an activity arc (the share of its people at work, in its chart colour, M12), its servers
 * online (a shape per state), its people at work (a dot each, at most twelve, then «+n»), its open sessions, today's spend against its cap
 * and the age of its last event. Hatched when it is locked. The only loop is the work band, and only while a run of it really runs.
 */
@Composable
fun LiveCompanyRow(co: CompanyLive, live: LiveState, now: Long, modifier: Modifier = Modifier, onClick: (() -> Unit)? = null) {
    val c = Divan.colors
    val env = LocalEnv.current
    val pulses by env.stream.activity.state.collectAsStateWithLifecycle()
    val running = pulses[co.code]?.runs?.isNotEmpty() == true
    val state = companyStateOf(co, live.control)
    val locked = state == "locked"
    val servers = live.serverStates.values.filter { it.company == co.code && it.state.isNotBlank() }
    val dots = dotsOf(live, co)
    val shape = RoundedCornerShape(14.dp)
    Column(
        modifier.fillMaxWidth().clip(shape).background(c.tile)
            .then(if (locked) Modifier.drawBehind { hatch(c.softNegative) } else Modifier)
            .then(if (onClick != null) Modifier.clickable(role = Role.Button, onClickLabel = "باز کردن ${co.nameFa}", onClick = onClick) else Modifier)
            .padding(horizontal = 12.dp, vertical = 10.dp)
            .semantics(mergeDescendants = true) {},
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            ActivityArc(co, size = 44.dp)
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(co.nameFa, style = Divan.type.bodyStrong, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
                    Text(if (locked) "قفل" else lastFa(co.lastEventAt, now), style = Divan.type.micro, color = if (locked) c.negative else c.textMuted, maxLines = 1)
                }
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    PeopleDots(dots)
                    Text(
                        co.working?.let { w -> "${faNum(w)} در کار" + (co.total?.let { " از ${faNum(it)}" } ?: "") } ?: "در کار: —",
                        style = Divan.type.caption, color = c.textSecondary, maxLines = 1,
                    )
                }
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    ServersBadge(co, servers.map { it.state })
                    Text(
                        "سشن: " + (co.sessionsOpen?.let { if (it == 0) "هیچ" else "${faNum(it)} باز" } ?: "—"),
                        style = Divan.type.caption, color = c.textSecondary, maxLines = 1,
                    )
                }
            }
        }
        SpendBar(co)
        WorkBand(running && !locked, c.silverInk, Modifier.fillMaxWidth(), height = 3.dp)
    }
}

/** The mark in its octagon-like disc with the activity arc around it: the share of people at work, in the company's chart colour. */
@Composable
fun ActivityArc(co: CompanyLive, size: Dp = 44.dp) {
    val c = Divan.colors
    val ink = companyColor(co.code)
    val share = if ((co.total ?: 0) > 0) ((co.working ?: 0).toFloat() / co.total!!).coerceIn(0f, 1f) else 0f
    val f by animateFill(share)
    Box(Modifier.size(size), contentAlignment = Alignment.Center) {
        Canvas(Modifier.size(size)) {
            val st = 3.dp.toPx()
            val r = this.size.minDimension / 2 - st / 2
            drawCircle(c.lineDivider, r, style = Stroke(st))
            if (f > 0f) drawArc(ink, -90f, 360f * f, false, topLeft = Offset(center.x - r, center.y - r), size = androidx.compose.ui.geometry.Size(2 * r, 2 * r), style = Stroke(st, cap = StrokeCap.Round))
        }
        Box(Modifier.size(size - 12.dp).clip(CircleShape).background(c.card), contentAlignment = Alignment.Center) {
            CompanyMark(co.code, height = size * 0.38f, ink = c.textPrimary)
        }
    }
}

/** «۲ از ۲ سرور» with a shape per server state. */
@Composable
private fun ServersBadge(co: CompanyLive, states: List<String>) {
    val c = Divan.colors
    if (co.serversTotal == null && states.isEmpty()) return
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(3.dp)) {
        val shown = states.ifEmpty { List(co.serversOnline ?: 0) { "online" } + List(((co.serversTotal ?: 0) - (co.serversOnline ?: 0)).coerceAtLeast(0)) { "offline" } }
        for (s in shown.take(4)) ServerGlyph(s, size = 9.dp)
        Text(
            "${(co.serversOnline ?: states.count { it == "online" }).let(::faNum)} از ${(co.serversTotal ?: states.size).let(::faNum)} سرور",
            style = Divan.type.micro, color = c.textMuted, maxLines = 1,
        )
    }
}

/** Today's spend against the company's cap: «$0.68 / $8» and a thin bar (the cap «—» when it has none). */
@Composable
private fun SpendBar(co: CompanyLive) {
    val c = Divan.colors
    val pct = co.spendTodayUsd?.let { s -> co.budgetUsd?.takeIf { it > 0 }?.let { s / it } }
    val f by animateFill((pct ?: 0.0).toFloat().coerceIn(0f, 1f))
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(
            buildAnnotatedString { fig((co.spendTodayUsd?.let(::usdCents) ?: "—") + " / " + (co.budgetUsd?.let(::usdCents) ?: "—")) },
            style = Divan.type.micro, color = c.textSecondary, maxLines = 1,
        )
        Box(Modifier.weight(1f).height(4.dp).clip(CircleShape).background(c.card)) {
            if (f > 0f) Box(Modifier.fillMaxWidth(f).fillMaxHeight().clip(CircleShape).background(if ((pct ?: 0.0) >= 0.9) c.warning else c.silverInk))
        }
    }
}

/** A locked company's 45° hatch (GL-2 on its card and on the map). */
fun androidx.compose.ui.graphics.drawscope.DrawScope.hatch(ink: Color, step: Float = 8.dp.value) {
    val s = step * density
    val n = ((size.width + size.height) / s).toInt() + 1
    for (i in 0..n) {
        val x = i * s
        drawLine(ink, Offset(x, 0f), Offset(x - size.height, size.height), strokeWidth = 2.dp.toPx())
    }
}

/** «شرکت‌ها · زنده» on the office: every company's live card, the busiest first; past [max], «همه‌ی شرکت‌ها». */
@Composable
fun LiveCompaniesCard(modifier: Modifier = Modifier, max: Int = 6) {
    val c = Divan.colors
    val nav = LocalNav.current
    val live = rememberLive()
    val now = rememberTicker(15_000)
    val list = rememberLiveCompanies(live)
    if (list.isEmpty()) return
    HqCard(modifier.fillMaxWidth()) {
        SectionTitle("شرکت‌ها · زنده", note = "${faNum(list.size)} شرکت، از داده؛ پرکارترها اول", icon = DivanIcon.COMPANIES) {
            if (list.size > max) HqButton("همه", { nav.go("companies") }, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.NEXT)
        }
        Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            for (co in list.take(max)) androidx.compose.runtime.key(co.code) { LiveCompanyRow(co, live, now) { nav.go("companies/${co.code}") } }
        }
        PersonLegend(Modifier.padding(top = 10.dp))
    }
}

/**
 * CO-1 inside a company's control card (the companies list): servers, people at work, sessions, today's spend and the last event, in one
 * strip under its name. Nothing when the store knows nothing of it yet.
 */
@Composable
fun CompanyLiveStrip(code: String, modifier: Modifier = Modifier) {
    val c = Divan.colors
    val live = rememberLive()
    val co = live.companies[code] ?: return
    val now = rememberTicker(15_000)
    val servers = live.serverStates.values.filter { it.company == code && it.state.isNotBlank() }
    Column(modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(horizontal = 10.dp, vertical = 8.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        FlowRow(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalArrangement = Arrangement.spacedBy(4.dp), itemVerticalAlignment = Alignment.CenterVertically) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                PeopleDots(dotsOf(live, co))
                Text(co.working?.let { "${faNum(it)} در کار" } ?: "در کار: —", style = Divan.type.micro, color = c.textSecondary)
            }
            ServersBadge(co, servers.map { it.state })
            Text("سشن: " + (co.sessionsOpen?.let { if (it == 0) "هیچ" else "${faNum(it)} باز" } ?: "—"), style = Divan.type.micro, color = c.textSecondary)
            Text(lastFa(co.lastEventAt, now), style = Divan.type.micro, color = c.textMuted)
        }
        SpendBar(co)
    }
}
