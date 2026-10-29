package com.coinepro.hq.ui.planner

import com.coinepro.hq.designsystem.Segmented
import com.coinepro.hq.designsystem.SegOption
import com.coinepro.hq.designsystem.FilterChip
import androidx.compose.runtime.mutableStateOf
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.OWNER_TZ
import com.coinepro.hq.core.format.WORK_STATUS
import com.coinepro.hq.core.format.jDate
import com.coinepro.hq.core.format.jTime
import com.coinepro.hq.core.format.jWeekday
import com.coinepro.hq.core.net.PlannerItem
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.CompanyMark
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.IconBtn
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.refresher
import java.time.DayOfWeek
import java.time.LocalDate
import java.time.ZoneId
import java.time.temporal.TemporalAdjusters

/** The three-level planner (§1.9): the owner's, a company's or a department's; a view over work, by week or by Persian month.
 *  The Persian week starts on Saturday. */
@Composable
fun PlannerScreen(onNewOrder: () -> Unit) {
    val nav = LocalNav.current
    val c = Divan.colors
    val companies = com.coinepro.hq.ui.rememberCompanies().filter { it.kind != "holding" }
    var week by rememberSaveable { mutableIntStateOf(0) }
    var month by rememberSaveable { mutableStateOf(false) }
    var company by rememberSaveable { mutableStateOf<String?>(null) }
    var dept by rememberSaveable { mutableStateOf<String?>(null) }
    val today = com.coinepro.hq.core.format.HqClock.today()
    val (start, end) = if (month) jMonth(today, week) else today.with(TemporalAdjusters.previousOrSame(DayOfWeek.SATURDAY)).plusWeeks(week.toLong()).let { it to it.plusDays(6) }
    val scope = company?.let { co -> dept?.let { "department:$co-$it" } ?: "company:$co" }
    val q = rememberQuery("planner:$start:$end:${scope ?: "owner"}", "planner", "work") { planner(start.toString(), end.toString(), scope) }
    val depts = company?.let { co -> rememberQuery("departments:$co", "companies") { departments(co) }.data.orEmpty() }.orEmpty()
    val r = refresher(q)
    val unit = if (month) "ماه" else "هفته"
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item {
            PageHeader("پلنر", eyebrow = if (month) monthTitle(start) else "${jDate(start.toString() + "T12:00:00Z")} تا ${jDate(end.toString() + "T12:00:00Z", withYear = true)}") {
                HqButton("فرمان تازه", onNewOrder, variant = BtnVariant.PRIMARY, icon = DivanIcon.COMMAND, size = BtnSize.SM)
                IconBtn(DivanIcon.NEXT, "${unit}ی قبل", { week-- }, flip = true)
                HqButton("این $unit", { week = 0 }, size = BtnSize.SM, enabled = week != 0)
                IconBtn(DivanIcon.NEXT, "${unit}ی بعد", { week++ })
            }
        }
        item { Segmented(listOf(SegOption(false, "هفته"), SegOption(true, "ماه")), month, { month = it; week = 0 }, Modifier.fillMaxWidth()) }
        item {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                com.coinepro.hq.designsystem.ScrollRow {
                    FilterChip("پلنر من", company == null, { company = null; dept = null })
                    companies.forEach { co -> FilterChip(co.nameFa ?: co.code, company == co.code, { company = co.code; dept = null }) }
                }
                if (company != null && depts.isNotEmpty()) com.coinepro.hq.designsystem.ScrollRow {
                    FilterChip("همه‌ی شرکت", dept == null, { dept = null })
                    depts.filter { it.status == "active" }.forEach { d -> FilterChip(d.nameFa, dept == d.code, { dept = d.code }) }
                }
            }
        }
        val days = q.data?.days
        when {
            days == null && q.error == null -> items(4) { Skeleton(Modifier.fillMaxWidth().height(96.dp), radius = 16.dp) }
            days == null -> item { ErrorBlock(q.error, { q.refresh() }) }
            month -> item {
                MonthGrid(start, end, days, today) { d ->
                    month = false
                    val sat = today.with(TemporalAdjusters.previousOrSame(DayOfWeek.SATURDAY))
                    week = Math.floorDiv(java.time.temporal.ChronoUnit.DAYS.between(sat, d), 7L).toInt()
                }
            }
            else -> items(days, key = { it.date }) { d ->
                val isToday = d.date == today.toString()
                HqCard(Modifier.fillMaxWidth(), tahrir = isToday) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(jWeekday(d.date + "T12:00:00Z"), style = Divan.type.bodyStrong, color = if (isToday) c.goldInk else c.textPrimary, modifier = Modifier.weight(1f))
                        if (isToday) Text("امروز", style = Divan.type.micro, color = c.goldInk)
                    }
                    if (d.items.isEmpty()) Text("کاری ثبت نشده.", style = Divan.type.caption, color = c.textMuted, modifier = Modifier.padding(top = 6.dp))
                    else Column(Modifier.padding(top = 8.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        d.items.sortedBy { it.at }.forEach { PlanRow(it) { nav.go("work/${it.ref}") } }
                    }
                }
            }
        }
    }
}

private val PDAY = android.icu.text.SimpleDateFormat("d", android.icu.util.ULocale("fa_IR@calendar=persian;numbers=latn")).apply { timeZone = android.icu.util.TimeZone.getTimeZone(OWNER_TZ) }
private val PMONTH = android.icu.text.SimpleDateFormat("MMMM y", android.icu.util.ULocale("fa_IR@calendar=persian;numbers=latn")).apply { timeZone = android.icu.util.TimeZone.getTimeZone(OWNER_TZ) }
private fun noon(d: LocalDate) = java.util.Date.from(d.atTime(12, 0).atZone(ZoneId.of(OWNER_TZ)).toInstant())
private fun jDay(d: LocalDate) = PDAY.format(noon(d)).toInt()
private fun jStart(d: LocalDate) = d.minusDays(jDay(d) - 1L)
private fun monthTitle(first: LocalDate) = PMONTH.format(noon(first.plusDays(10)))

/** First and last day of the Persian month [offset] months from [today] (a month is at most 31 days, so +32 lands in the next). */
private fun jMonth(today: LocalDate, offset: Int): Pair<LocalDate, LocalDate> {
    var first = jStart(today)
    repeat(kotlin.math.abs(offset)) { first = if (offset > 0) jStart(first.plusDays(32)) else jStart(first.minusDays(1)) }
    return first to jStart(first.plusDays(32)).minusDays(1)
}

@Composable
private fun MonthGrid(first: LocalDate, last: LocalDate, days: List<com.coinepro.hq.core.net.PlannerDay>, today: LocalDate, onDay: (LocalDate) -> Unit) {
    val c = Divan.colors
    val byDate = days.associateBy { it.date }
    val lead = (first.dayOfWeek.value % 7 + 1) % 7 // Saturday = 0
    val cells: List<LocalDate?> = List(lead) { null } + generateSequence(first) { it.plusDays(1) }.takeWhile { !it.isAfter(last) }.toList()
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Row { listOf("ش", "ی", "د", "س", "چ", "پ", "ج").forEach { Text(it, style = Divan.type.micro, color = c.textMuted, modifier = Modifier.weight(1f), textAlign = androidx.compose.ui.text.style.TextAlign.Center) } }
        cells.chunked(7).forEach { week ->
            Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                (week + List(7 - week.size) { null }).forEach { d ->
                    val n = d?.let { byDate[it.toString()]?.items?.size } ?: 0
                    Column(
                        Modifier.weight(1f).height(52.dp).clip(RoundedCornerShape(10.dp)).background(if (d == null) androidx.compose.ui.graphics.Color.Transparent else if (d == today) c.softGold else c.card)
                            .clickable(enabled = d != null) { d?.let(onDay) }.padding(4.dp),
                        horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.SpaceBetween,
                    ) {
                        if (d != null) {
                            Fig("${jDay(d)}", style = Divan.type.figureSmall, color = if (d == today) c.goldInk else c.textSecondary)
                            if (n > 0) Text("$n", style = Divan.type.micro, color = c.onGold, modifier = Modifier.clip(RoundedCornerShape(8.dp)).background(c.goldFill).padding(horizontal = 6.dp))
                        }
                    }
                }
            }
        }
        Text("روی هر روز بزن تا هفته‌اش باز شود.", style = Divan.type.micro, color = c.textMuted)
    }
}

@Composable
private fun PlanRow(i: PlannerItem, onClick: () -> Unit) {
    val c = Divan.colors
    val bar = when { i.status == "done" -> c.positive; com.coinepro.hq.core.format.isUrgentPriority(i.priority) -> c.negative; else -> c.silverInk }
    Row(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(c.tile).clickable(role = Role.Button, onClick = onClick).padding(10.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Box(Modifier.width(3.dp).height(32.dp).clip(RoundedCornerShape(2.dp)).background(bar))
        Column(Modifier.weight(1f)) {
            Text(i.title, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), maxLines = 1, overflow = TextOverflow.Ellipsis, color = if (i.status == "done") c.textMuted else c.textPrimary)
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(jTime(i.at), style = Divan.type.micro, color = c.textMuted)
                if (i.recurring) DIcon(DivanIcon.REFRESH, size = 12.dp, tint = c.textMuted)
                Text(WORK_STATUS[i.status] ?: i.status, style = Divan.type.micro, color = c.textMuted)
            }
        }
        CompanyMark(i.company, height = 12.dp, mono = true, ink = c.textSecondary)
        com.coinepro.hq.ui.work.PriorityTag(i.priority, compact = true)
    }
}
