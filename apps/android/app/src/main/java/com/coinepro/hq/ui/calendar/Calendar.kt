package com.coinepro.hq.ui.calendar

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.HqClock
import com.coinepro.hq.core.format.OWNER_TZ
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.instant
import com.coinepro.hq.core.format.jDate
import com.coinepro.hq.core.format.jTime
import com.coinepro.hq.core.format.jWeekday
import com.coinepro.hq.core.net.CalendarEvent
import com.coinepro.hq.core.net.CalendarIn
import com.coinepro.hq.core.net.Conflict
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v14.HqSheet
import com.coinepro.hq.ui.v14.LabelPill
import com.coinepro.hq.ui.v16.ChipRow
import com.coinepro.hq.ui.v16.Labelled
import com.coinepro.hq.ui.v16.appendProse
import com.coinepro.hq.ui.v16.prose
import com.coinepro.hq.ui.v17.CAL_KIND
import com.coinepro.hq.ui.v17.CAL_RISK
import com.coinepro.hq.ui.v17.CAL_STATUS
import com.coinepro.hq.ui.v17.CONFLICT_RULE
import com.coinepro.hq.ui.v17.CoMark
import com.coinepro.hq.ui.v17.FilterRow
import com.coinepro.hq.ui.v17.IconTile
import com.coinepro.hq.ui.v17.RefChip
import com.coinepro.hq.ui.v17.RefTone
import com.coinepro.hq.ui.v17.ScopeChips
import com.coinepro.hq.ui.v17.calColor
import com.coinepro.hq.ui.v17.gov
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter

private val ZONE: ZoneId = ZoneId.of(OWNER_TZ)
private val OWNED = listOf("campaign", "event", "maintenance", "freeze")
private val LOCAL: DateTimeFormatter = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm")

private fun tehranDay(iso: String): LocalDate? = instant(iso)?.atZone(ZONE)?.toLocalDate()

/** The day an event's end belongs to: an event ending at midnight ends the day before. */
private fun endDay(iso: String): LocalDate? = instant(iso)?.minusMillis(1)?.atZone(ZONE)?.toLocalDate()

/** تقویم تغییرات (contract §20.9): deploys, freezes, campaigns, events, maintenance, meetings and the official holidays, with the
 *  conflicts the code finds. The calendar never decides: a deploy card stays the owner's. */
@Composable
fun CalendarScreen() {
    val c = Divan.colors
    var company by rememberSaveable { mutableStateOf<String?>(null) }
    var kind by rememberSaveable { mutableStateOf<String?>(null) }
    var past by rememberSaveable { mutableStateOf(false) }
    var create by remember { mutableStateOf(false) }
    // Whole days, so the range (and the query) moves once a day.
    val today = HqClock.today()
    val from = today.minusDays(7).toString()
    val to = today.plusDays(35).toString()
    val q = rememberQuery("calendar:${company.orEmpty()}:$from:$to:${kind.orEmpty()}", "calendar", "planner") { calendar(company, from, to, kind) }
    val r = refresher(q)
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item {
            PageHeader("تقویم تغییرات", eyebrow = "انتشار، فریز، کمپین، جلسه و تعطیلی؛ تقویم تصمیم نمیگیرد") {
                HqButton("رویداد تازه", { create = true }, variant = BtnVariant.PRIMARY, icon = DivanIcon.ADD)
            }
        }
        item {
            Text(
                "کد از کارت‌های deploy، فریزها، جلسه‌ها، پنجره‌های backup و تعطیلی‌های رسمی پرش میکند. انتشار داخل فریز یا هم‌زمان با کمپین همان شرکت تداخل «بالا» است؛ دو انتشار هم‌زمان، روز ممنوع ماتریس اختیار، تعطیلی و نگه‌داری هم‌زمان «متوسط». تداخل روی خود کارت deploy هم میاید.",
                style = Divan.type.small, color = c.textSecondary,
            )
        }
        item {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                ScopeChips(company, { company = it }, holding = false)
                FilterRow("همه‌ی نوع‌ها", kind, CAL_KIND.mapValues { it.value.fa }) { kind = it }
            }
        }
        val view = q.data
        when {
            view == null && q.error != null -> item { ErrorBlock(q.error, { q.refresh() }) }
            view == null -> item { Skeleton(Modifier.fillMaxWidth().height(320.dp), radius = 16.dp) }
            else -> {
                val byRef = view.events.associateBy { it.ref }
                if (view.conflicts.isNotEmpty()) item(key = "conflicts") { Conflicts(view.conflicts, byRef) }
                val now = HqClock.now()
                val days = view.events.groupBy { e ->
                    val d = tehranDay(e.startsAt) ?: today
                    if (d < today && (instant(e.endsAt)?.isAfter(now) == true)) today else d
                }.toSortedMap()
                val shown = days.filterKeys { past || it >= today }
                if (days.keys.any { it < today }) item(key = "past") {
                    HqButton(if (past) "پنهان کردن گذشته" else "نشان دادن هفته‌ی گذشته", { past = !past }, variant = BtnVariant.GHOST, size = BtnSize.SM)
                }
                if (shown.isEmpty()) item { Empty("رویدادی در این بازه نیست", icon = DivanIcon.TIME) }
                for ((d, xs) in shown) item(key = "day:$d") {
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        val iso = d.atTime(12, 0).atZone(ZONE).toInstant().toString()
                        Text((if (d == today) "امروز، " else "") + jWeekday(iso), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = if (d == today) c.goldInk else c.textPrimary)
                        for (e in xs) EventRow(e, view.conflicts.filter { it.a == e.ref })
                    }
                }
            }
        }
    }
    if (create) NewEvent { create = false }
}

@Composable
private fun Conflicts(xs: List<Conflict>, byRef: Map<String, CalendarEvent>) {
    val c = Divan.colors
    val high = xs.count { it.severity == "high" }
    HqCard(Modifier.fillMaxWidth(), color = if (high > 0) c.softNegative else c.softWarning) {
        SectionTitle("${xs.size} تداخل", note = if (high > 0) "$high تداخل بالا" else "همه متوسط")
        Spacer(Modifier.height(8.dp))
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            for (x in xs) Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Pill(if (x.severity == "high") "بالا" else "متوسط", if (x.severity == "high") Tone.NEG else Tone.WARN, dot = true)
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    Text(buildAnnotatedString {
                        pushStyle(androidx.compose.ui.text.SpanStyle(fontWeight = FontWeight.SemiBold))
                        appendProse(byRef[x.a]?.titleFa ?: x.a)
                        pop()
                        if (x.b != x.a) {
                            pushStyle(androidx.compose.ui.text.SpanStyle(color = c.textMuted))
                            append(" با ")
                            pop()
                            appendProse(byRef[x.b]?.titleFa ?: x.b)
                        }
                    }, style = Divan.type.small, color = c.textPrimary)
                    Text(CONFLICT_RULE[x.rule] ?: x.rule, style = Divan.type.caption, color = c.textSecondary)
                }
            }
        }
    }
}

/** An event's time: «تمام روز» for a holiday, a span within one day, or from a day to another. */
@Composable
private fun Span(e: CalendarEvent) {
    val c = Divan.colors
    val a = tehranDay(e.startsAt)
    val b = endDay(e.endsAt)
    val text = when {
        e.kind == "holiday" -> buildAnnotatedString { append(if (a == b) "تمام روز" else "${jDate(e.startsAt)} تا ${jDate(e.endsAt)}") }
        a == b -> buildAnnotatedString { fig("${jTime(e.startsAt)}–${jTime(e.endsAt)}") }
        else -> buildAnnotatedString { append(jDate(e.startsAt) + " "); fig(jTime(e.startsAt)); append(" تا ${jDate(e.endsAt)} "); fig(jTime(e.endsAt)) }
    }
    Text(text, style = Divan.type.micro, color = c.textMuted)
}

@Composable
private fun EventRow(e: CalendarEvent, flags: List<Conflict>) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val action = rememberAction()
    val k = CAL_KIND[e.kind]
    val mine = e.kind in OWNED && e.status == "planned"
    fun set(status: String, ok: String) = action.gov(toasts) {
        env.api.patchEvent(e, status)
        env.cache.invalidate("calendar", "planner")
        toasts.ok(ok)
    }
    Column(
        Modifier.fillMaxWidth().alpha(if (e.status != "planned") 0.6f else 1f).clip(RoundedCornerShape(12.dp)).background(c.card)
            .border(1.dp, if (flags.any { it.severity == "high" }) c.negative.copy(alpha = 0.45f) else c.lineDivider, RoundedCornerShape(12.dp)).padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            IconTile(k?.icon ?: DivanIcon.TIME, c.onGold, bg = calColor(e.kind), size = 28.dp)
            Text(prose(e.titleFa), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, modifier = Modifier.weight(1f))
            CoMark(e.company, ink = c.textMuted)
        }
        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(4.dp), itemVerticalAlignment = Alignment.CenterVertically) {
            Pill(k?.fa ?: e.kind, Tone.NEUTRAL)
            if (e.kind == "deploy") LabelPill(CAL_RISK[e.risk], e.risk)
            if (e.status != "planned") Pill(CAL_STATUS[e.status] ?: e.status, Tone.NEUTRAL)
        }
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Span(e)
            e.source.ref?.let { RefChip(it, tone = RefTone.NEUTRAL) }
            Fig(e.ref, style = Divan.type.figureSmall, color = c.textMuted)
            Spacer(Modifier.weight(1f))
            if (mine) {
                HqButton("انجام شد", { set("done", "انجام‌شده ثبت شد.") }, variant = BtnVariant.GHOST, size = BtnSize.SM)
                HqButton("لغو", { set("cancelled", "لغو شد.") }, variant = BtnVariant.GHOST, size = BtnSize.SM)
            }
        }
        for (f in flags) Row(
            Modifier.fillMaxWidth().clip(RoundedCornerShape(8.dp)).background(if (f.severity == "high") c.softNegative else c.softWarning).padding(horizontal = 8.dp, vertical = 6.dp),
            horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            DIcon(DivanIcon.URGENT, Modifier.padding(top = 3.dp), size = 13.dp, tint = if (f.severity == "high") c.negative else c.warning)
            Text(buildAnnotatedString {
                pushStyle(androidx.compose.ui.text.SpanStyle(fontWeight = FontWeight.SemiBold)); append(CONFLICT_RULE[f.rule] ?: f.rule); pop()
                append(" · "); append(prose(f.noteFa))
            }, style = Divan.type.caption, color = c.textPrimary)
        }
    }
}

/** A campaign, event, maintenance window or freeze; deploys come from deploy cards, meetings and holidays by themselves. */
@Composable
private fun NewEvent(onClose: () -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val action = rememberAction()
    var company by rememberSaveable { mutableStateOf<String?>(null) }
    var kind by rememberSaveable { mutableStateOf("campaign") }
    var title by rememberSaveable { mutableStateOf("") }
    var from by rememberSaveable { mutableStateOf("") }
    var to by rememberSaveable { mutableStateOf("") }
    var risk by rememberSaveable { mutableStateOf("low") }
    fun at(s: String) = runCatching { LocalDateTime.parse(s.trim(), LOCAL).atZone(ZONE).toInstant() }.getOrNull()
    val a = at(from)
    val b = at(to)
    val valid = title.isNotBlank() && a != null && b != null && b.isAfter(a)
    HqSheet(onClose, "رویداد تازه در تقویم", sub = "انتشارها از کارت‌های deploy، جلسه‌ها و تعطیلی‌ها خودکار میایند.") {
        Labelled("کجا") { ScopeChips(company, { company = it }, allLabel = "همه‌ی شرکت‌ها") }
        Labelled("نوع") { ChipRow { for (k in OWNED) FilterChip(CAL_KIND.getValue(k).fa, kind == k, { kind = k }) } }
        Labelled("عنوان") { HqTextField(title, { title = it }, "عنوان", Modifier.fillMaxWidth(), maxLength = 200) }
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Labelled("از", Modifier.weight(1f)) {
                CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) { HqTextField(from, { from = it }, "2026-10-20 14:00", Modifier.fillMaxWidth(), maxLength = 16, figure = true) }
            }
            Labelled("تا", Modifier.weight(1f)) {
                CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) { HqTextField(to, { to = it }, "2026-10-20 18:00", Modifier.fillMaxWidth(), maxLength = 16, figure = true) }
            }
        }
        Labelled("ریسک") { ChipRow { for (x in listOf("low", "medium", "high")) FilterChip(CAL_RISK.getValue(x).fa, risk == x, { risk = x }) } }
        HqButton("ثبت", {
            val s = a ?: return@HqButton
            val e = b ?: return@HqButton
            action.gov(toasts) {
                val out = env.api.createEvent(CalendarIn(company, kind, title.trim(), s.toString(), e.toString(), risk))
                env.cache.invalidate("calendar", "planner")
                toasts.ok("رویداد ${out.ref} در تقویم ثبت شد؛ تداخل‌ها را کد میسنجد.")
                onClose()
            }
        }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, size = BtnSize.LG, icon = DivanIcon.ADD, enabled = valid, loading = action.busy)
        Text("زمان به وقت تهران.", style = Divan.type.micro, color = c.textMuted)
    }
}
