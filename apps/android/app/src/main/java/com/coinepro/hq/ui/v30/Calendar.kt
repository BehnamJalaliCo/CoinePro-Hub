package com.coinepro.hq.ui.v30

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material3.HorizontalDivider
import com.coinepro.hq.designsystem.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.calendarWeek
import com.coinepro.hq.core.data.lineRunStateFa
import com.coinepro.hq.core.data.lineRunStateTone
import com.coinepro.hq.core.data.platformFa
import com.coinepro.hq.core.data.platformIcon
import com.coinepro.hq.core.format.HqClock
import com.coinepro.hq.core.format.jDate
import com.coinepro.hq.core.format.jTime
import com.coinepro.hq.core.format.jWeekday
import com.coinepro.hq.core.net.CalendarDay
import com.coinepro.hq.core.net.CalendarItem
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.gated
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.ScrollRow
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v29.CoName
import com.coinepro.hq.ui.v29.served
import com.coinepro.hq.ui.v29.plain

// Contract §30.5 ⟨1.12⟩: the calendar of every company's lines (from the holding menu, beside the groups and the rules): what is scheduled,
// and what ran, a week at a time (Saturday to Friday), by day.

@Composable
fun CalendarScreen() {
    val nav = LocalNav.current
    var offset by rememberSaveable { mutableIntStateOf(0) }
    var company by rememberSaveable { mutableStateOf<String?>(null) }
    val week = calendarWeek(offset)
    val from = week.first
    val to = week.second
    val companies = rememberCompanies().filter { it.kind != "holding" }
    val q = rememberQuery("lines-cal:$from:$to:${company.orEmpty()}", "lines", "line-runs", maxAgeMs = 30_000) { gated(HubFeature.LINES) { lineCalendar(from, to, company) } }
    val r = refresher(q)
    val has = served(HubFeature.LINES)
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item { PageHeader("تقویم تولید", eyebrow = "آنچه قرار است منتشر شود و آنچه شد") }
        if (has) item(key = "nav") {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    HqButton("هفته‌ی قبل", { offset-- }, variant = BtnVariant.GHOST, size = BtnSize.SM, icon = DivanIcon.BACK, label = "هفته‌ی قبل")
                    Text(plain(jDate(from) + " تا " + jDate(to)), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), modifier = Modifier.weight(1f), maxLines = 1)
                    if (offset != 0) HqButton("این هفته", { offset = 0 }, variant = BtnVariant.TEXT, size = BtnSize.SM)
                    HqButton("هفته‌ی بعد", { offset++ }, variant = BtnVariant.GHOST, size = BtnSize.SM, icon = DivanIcon.NEXT, label = "هفته‌ی بعد")
                }
                ScrollRow {
                    FilterChip("همه‌ی شرکت‌ها", company == null, { company = null })
                    for (co in companies) FilterChip(co.nameFa ?: co.code, company == co.code, { company = co.code })
                }
            }
        }
        val cal = q.data
        when {
            !has -> item { Empty("تقویم تولید با به‌روزرسانی بعدی هاب میاید", icon = DivanIcon.PLANNER) }
            cal == null && q.error != null -> item { ErrorBlock(q.error, { q.refresh() }) }
            cal == null -> item { Skeleton(Modifier.fillMaxWidth().height(200.dp), radius = 16.dp) }
            cal.days.none { it.items.isNotEmpty() } -> item { Empty("این هفته چیزی در برنامه نیست", icon = DivanIcon.PLANNER, body = "برنامه‌ی هر خط را در صفحه‌ی خودش میگذاری.") }
            else -> cal.days.filter { it.items.isNotEmpty() }.sortedBy { it.day }.forEach { d ->
                item(key = "day-${d.day}") { DayCard(d) { i -> nav.go(i.run?.let { "line-runs/$it" } ?: "lines/${i.line}") } }
            }
        }
    }
}

/** One day: what is scheduled and what ran, by the hour. */
@Composable
fun DayCard(d: CalendarDay, onOpen: (CalendarItem) -> Unit) {
    val c = Divan.colors
    val today = HqClock.today().toString()
    HqCard(Modifier.fillMaxWidth()) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(plain(jWeekday(d.day)), style = Divan.type.bodyStrong, modifier = Modifier.weight(1f))
            if (d.day == today) Pill("امروز", com.coinepro.hq.core.format.Tone.SILVER)
            Text(plain("${d.items.size} مورد"), style = Divan.type.caption, color = c.textMuted)
        }
        Column(Modifier.padding(top = 6.dp)) {
            d.items.sortedBy { it.at }.forEachIndexed { i, x ->
                if (i > 0) HorizontalDivider(color = c.lineDivider)
                Row(
                    Modifier.fillMaxWidth().clickable(role = Role.Button) { onOpen(x) }.padding(vertical = 10.dp),
                    verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    Text(com.coinepro.hq.designsystem.timesFig(jTime(x.at)), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, modifier = Modifier.width(44.dp))
                    DIcon(platformIcon(x.platform), size = 18.dp, tint = c.textSecondary)
                    Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Text(plain(x.titleFa ?: platformFa(x.platform)), style = Divan.type.small, maxLines = 2)
                        CoName(x.company, height = 11.dp, color = c.textMuted)
                    }
                    Pill(lineRunStateFa(x.state), lineRunStateTone(x.state), dot = true, live = x.state == "running")
                }
            }
        }
    }
}
