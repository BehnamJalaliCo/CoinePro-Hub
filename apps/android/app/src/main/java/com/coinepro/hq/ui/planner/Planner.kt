package com.coinepro.hq.ui.planner

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

/** The planner (D2·2): the owner's week starts on Saturday. A phone shows the week as a day list; each day
 *  carries its scheduled and recurring work across every company. */
@Composable
fun PlannerScreen(onNewOrder: () -> Unit) {
    val nav = LocalNav.current
    val c = Divan.colors
    var week by rememberSaveable { mutableIntStateOf(0) }
    val today = LocalDate.now(ZoneId.of(OWNER_TZ))
    val start = today.with(TemporalAdjusters.previousOrSame(DayOfWeek.SATURDAY)).plusWeeks(week.toLong())
    val end = start.plusDays(6)
    val q = rememberQuery("planner:$start:$end", "planner", "work") { planner(start.toString(), end.toString()) }
    val r = refresher(q)
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item {
            PageHeader("پلنر", eyebrow = "${jDate(start.toString() + "T12:00:00Z")} تا ${jDate(end.toString() + "T12:00:00Z", withYear = true)}") {
                HqButton("فرمان تازه", onNewOrder, variant = BtnVariant.PRIMARY, icon = DivanIcon.COMMAND, size = BtnSize.SM)
                IconBtn(DivanIcon.NEXT, "هفته‌ی قبل", { week-- }, flip = true)
                HqButton("این هفته", { week = 0 }, size = BtnSize.SM, enabled = week != 0)
                IconBtn(DivanIcon.NEXT, "هفته‌ی بعد", { week++ })
            }
        }
        val days = q.data?.days
        when {
            days == null && q.error == null -> items(4) { Skeleton(Modifier.fillMaxWidth().height(96.dp), radius = 16.dp) }
            days == null -> item { ErrorBlock(q.error, { q.refresh() }) }
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

@Composable
private fun PlanRow(i: PlannerItem, onClick: () -> Unit) {
    val c = Divan.colors
    val bar = when { i.status == "done" -> c.positive; i.priority <= "P1" -> c.negative; else -> c.silverInk }
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
        Fig(i.priority, style = Divan.type.figureSmall, color = c.textMuted, modifier = Modifier.size(width = 22.dp, height = 16.dp))
    }
}
