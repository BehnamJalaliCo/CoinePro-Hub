package com.coinepro.hq.ui.publish

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.coinepro.hq.core.data.DayRow
import com.coinepro.hq.core.data.J_WEEK_FA
import com.coinepro.hq.core.data.MonthCell
import com.coinepro.hq.core.data.PUB_CHANNELS
import com.coinepro.hq.core.data.atHandle
import com.coinepro.hq.core.data.cardsByDay
import com.coinepro.hq.core.data.cellCountFa
import com.coinepro.hq.core.data.dayAccounts
import com.coinepro.hq.core.data.dayHeadFa
import com.coinepro.hq.core.data.dayRows
import com.coinepro.hq.core.data.faHour
import com.coinepro.hq.core.data.faNum
import com.coinepro.hq.core.data.hitRange
import com.coinepro.hq.core.data.jDayFa
import com.coinepro.hq.core.data.jMonthFa
import com.coinepro.hq.core.data.kindTabs
import com.coinepro.hq.core.data.matchFa
import com.coinepro.hq.core.data.monthGrid
import com.coinepro.hq.core.data.monthSpan
import com.coinepro.hq.core.data.nextMonth
import com.coinepro.hq.core.data.pubChannelFa
import com.coinepro.hq.core.data.pubKindFa
import com.coinepro.hq.core.data.pubStateFa
import com.coinepro.hq.core.data.setProgressFa
import com.coinepro.hq.core.data.tehranDate
import com.coinepro.hq.core.data.toJalali
import com.coinepro.hq.core.format.HqClock
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.PublicationCard
import com.coinepro.hq.core.net.Waiting
import com.coinepro.hq.core.net.gated
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.CompanyMark
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.IconBtn
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.ScrollRow
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.Text
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v29.plain
import com.coinepro.hq.ui.v29.served
import java.time.LocalDate
import java.time.ZoneId
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

// ⟨1.39⟩ Contract §60.2 and D6: the centre's tabs «امروز · میز · تقویم · بایگانی», an account's page, the search and «منتظر شما». The desk
// is §55.2's page with the centre's head (Desk.kt).

private fun todayTehran(): LocalDate = HqClock.now().atZone(ZoneId.of(com.coinepro.hq.core.format.OWNER_TZ)).toLocalDate()

/** A hub before §60: the centre says so once, and the desk is there as before. */
@Composable
private fun OldHub() {
    val nav = LocalNav.current
    Empty("مرکز انتشار با به‌روزرسانی بعدی هاب می‌آید", icon = DivanIcon.SEND, body = "تا آن وقت «میز انتشار» و «خروجی‌ها» مثل قبل کار میکنند.", action = {
        HqButton("میز انتشار", { nav.go("publish-desk") }, variant = BtnVariant.SECONDARY)
    })
}

@Composable
private fun Skeletons(n: Int = 4) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) { repeat(n) { Skeleton(Modifier.fillMaxWidth().height(72.dp), radius = 16.dp) } }
}

// ------------------------------------------------------------------------------------------------------------- today --
/** «امروز»: every page's day on one line of Tehran hours, sets as one row, what is still to be made dashed, «اکنون» between. */
@Composable
fun PublishTodayScreen() {
    val c = Divan.colors
    val q = rememberPubToday()
    val has = served(HubFeature.PUBLICATIONS)
    var account by rememberSaveable { mutableStateOf<String?>(null) }
    OnPublication { q.refresh() }
    Every(60_000) { q.refresh() }
    Page(onRefresh = { q.refresh() }, refreshing = q.state.refreshing) {
        item(key = "head") { CentreHead("publish") }
        if (!has) { item(key = "old") { OldHub() }; return@Page }
        item(key = "waiting") { WaitingBanner() }
        val t = q.data
        when {
            t == null && q.error != null -> item(key = "error") { ErrorBlock(q.error, { q.refresh() }) }
            t == null -> item(key = "sk") { Skeletons() }
            else -> {
                val accounts = dayAccounts(t)
                if (accounts.size > 1) item(key = "chips") {
                    ScrollRow(Modifier.testTag("today-chips"), spacing = 8.dp) {
                        FilterChip("همه‌ی پیج‌ها", account == null, { account = null })
                        for (a in accounts) FilterChip("@$a", account == a, { account = if (account == a) null else a }, figure = true)
                    }
                }
                val total = t.counts.published + t.counts.scheduled + t.counts.held + t.counts.failed + t.planned.size
                item(key = "day") {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text("${jDayFa(todayTehran())} · ${faNum(total)} مورد", style = Divan.type.small, color = c.textSecondary, modifier = Modifier.weight(1f))
                        Text("ساعت تهران", style = Divan.type.micro, color = c.textMuted)
                    }
                }
                val rows = dayRows(t, HqClock.millis(), account)
                if (rows.none { it !is DayRow.Now }) item(key = "empty") {
                    Empty("امروز هنوز چیزی در برنامه نیست", icon = DivanIcon.SEND, body = "اتوماسیون‌ها هر روز خودشان می‌سازند و این‌جا می‌آیند.")
                } else items(rows, key = { r -> when (r) { is DayRow.Item -> "i-${r.card.ref}"; is DayRow.Plan -> "p-${r.plan.automation}"; is DayRow.Now -> "now" } }) { r ->
                    when (r) {
                        is DayRow.Now -> NowLine(r.minute)
                        is DayRow.Item -> TimeRow(r.card.at) { PubRow(r.card) }
                        is DayRow.Plan -> TimeRow(r.plan.publishAt) { PlanRow(r.plan) }
                    }
                }
                item(key = "foot") { Text("هر ردیف با یک لمس صفحه‌ی همان مورد را باز میکند؛ دسته‌ی استوری، نمای ورق‌زدنی را.", style = Divan.type.micro, color = c.textMuted, textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth()) }
            }
        }
    }
}

@Composable
private fun TimeRow(at: String, content: @Composable () -> Unit) {
    val c = Divan.colors
    Row(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.Top) {
        Text(faHour(at), style = Divan.type.micro, color = c.textMuted, modifier = Modifier.width(40.dp).padding(top = 12.dp))
        Box(Modifier.weight(1f)) { content() }
    }
}

// ---------------------------------------------------------------------------------------------------------- calendar --
private val BRIGHTS = listOf(Color(0xFF2BB89F), Color(0xFF86A6FF), Color(0xFFB48CFF), Color(0xFFE2B65A), Color(0xFFFF8A8A), Color(0xFF7FD3E6))
fun brightOf(account: String): Color = BRIGHTS[Math.floorMod(account.removePrefix("@").hashCode(), BRIGHTS.size)]

/** «تقویم»: the Jalali month (Saturday first), each day with what went out or is planned, its pages as dots; a day's list under it. */
@Composable
fun PublishCalendarScreen() {
    val c = Divan.colors
    val today = remember { todayTehran() }
    var monthKey by rememberSaveable { mutableStateOf(toJalali(today).let { it.y * 12 + it.m - 1 }) }
    val month = com.coinepro.hq.core.data.JDate(monthKey / 12, monthKey % 12 + 1, 1)
    var picked by rememberSaveable { mutableStateOf(today.toString()) }
    var view by rememberSaveable { mutableStateOf("month") }
    val (from, to) = remember(monthKey) { monthSpan(month) }
    val q = rememberQuery("pub-cal:$from", *PUB_TAGS, maxAgeMs = 60_000) { gated(HubFeature.PUBLICATIONS) { publicationsCalendar(from.toString(), to.toString()) } }
    val dayQ = rememberQuery("pub-day:$picked", *PUB_TAGS, maxAgeMs = 30_000) { gated(HubFeature.PUBLICATIONS) { publications(from = picked, to = picked, limit = 60) } }
    val has = served(HubFeature.PUBLICATIONS)
    OnPublication { q.refresh(); dayQ.refresh() }
    Page(onRefresh = { q.refresh(); dayQ.refresh() }, refreshing = q.state.refreshing) {
        item(key = "head") { CentreHead("publish/calendar") }
        if (!has) { item(key = "old") { OldHub() }; return@Page }
        item(key = "month") {
            Row(verticalAlignment = Alignment.CenterVertically) {
                IconBtn(DivanIcon.NEXT, "ماه قبل", { monthKey -= 1 }, flip = true)
                Text(jMonthFa(month), style = Divan.type.h3, modifier = Modifier.semantics { heading() })
                IconBtn(DivanIcon.NEXT, "ماه بعد", { monthKey += 1 })
                Spacer(Modifier.weight(1f))
                Row(Modifier.clip(RoundedCornerShape(12.dp)).background(c.tile).padding(3.dp)) {
                    for ((k, l) in listOf("month" to "ماه", "week" to "هفته", "day" to "روز")) {
                        val on = view == k
                        Box(Modifier.clip(RoundedCornerShape(9.dp)).then(if (on) Modifier.background(c.raised) else Modifier).clickable(role = Role.Tab) { view = k }.padding(horizontal = 10.dp, vertical = 5.dp)) {
                            Text(l, style = Divan.type.micro.copy(fontWeight = if (on) FontWeight.SemiBold else FontWeight.Normal), color = if (on) c.textPrimary else c.textSecondary)
                        }
                    }
                }
            }
        }
        val cal = q.data
        when {
            cal == null && q.error != null -> item(key = "error") { ErrorBlock(q.error, { q.refresh() }) }
            cal == null -> item(key = "sk") { Skeleton(Modifier.fillMaxWidth().height(360.dp), radius = 16.dp) }
            else -> {
                val grid = monthGrid(month, cal.days, today)
                if (view != "day") item(key = "grid") {
                    val weeks = if (view == "week") grid.filter { w -> w.any { it?.date?.toString() == picked } }.ifEmpty { grid.take(1) } else grid
                    Column(Modifier.testTag("pub-month"), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) { for (w in J_WEEK_FA) Text(w, style = Divan.type.micro, color = c.textMuted, textAlign = TextAlign.Center, modifier = Modifier.weight(1f)) }
                        for (w in weeks) Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                            for (cell in w) Box(Modifier.weight(1f)) { if (cell != null) DayCell(cell, cell.date.toString() == picked) { picked = cell.date.toString() } else Spacer(Modifier.height(if (view == "week") 72.dp else 58.dp)) }
                        }
                    }
                }
                item(key = "legend") {
                    val accs = cal.days.flatMap { it.accounts }.distinct()
                    if (accs.isNotEmpty()) com.coinepro.hq.designsystem.ScrollX {
                        Row(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.CenterVertically) {
                            for (a in accs) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                                Box(Modifier.size(8.dp).clip(CircleShape).background(brightOf(a)))
                                Text(plain("@$a"), style = Divan.type.micro, color = c.textSecondary)
                            }
                            Text("خط‌چین: ساخته میشود", style = Divan.type.micro, color = c.textMuted)
                        }
                    }
                }
                val pd = LocalDate.parse(picked)
                val dayInfo = cal.days.firstOrNull { it.day == picked }
                item(key = "dayhead") {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(dayHeadFa(pd, today), style = Divan.type.h3, modifier = Modifier.weight(1f).semantics { heading() })
                        dayInfo?.let { d ->
                            val all = d.published + d.scheduled + d.held + d.failed + d.planned
                            if (all > 0) Pill(if (pd.isAfter(today)) "${faNum(all)} برنامه" else "${faNum(d.published)} منتشر شد", if (pd.isAfter(today)) Tone.NEUTRAL else Tone.POS)
                        }
                    }
                }
                val list = dayQ.data?.items
                when {
                    list == null -> item(key = "daysk") { Skeletons(2) }
                    list.isEmpty() && (dayInfo?.planned ?: 0) == 0 -> item(key = "dayempty") { Text("این روز چیزی نرفته و چیزی در برنامه نیست.", style = Divan.type.small, color = c.textSecondary) }
                    else -> items(list.sortedBy { com.coinepro.hq.core.data.instant(it.at) }, key = { "d-${it.ref}" }) { k -> TimeRow(k.at) { PubRow(k) } }
                }
                if ((dayInfo?.planned ?: 0) > 0) item(key = "planned") {
                    com.coinepro.hq.designsystem.HqCard(Modifier.fillMaxWidth()) {
                        Text("${faNum(dayInfo!!.planned)} مورد ساخته میشود", style = Divan.type.bodyStrong)
                        Text("روز آینده از برنامه‌ی اتوماسیون‌ها حساب میشود؛ وقتی ساخته شد، هر مورد عنوان و کاور خودش را میگیرد.", style = Divan.type.micro, color = c.textMuted)
                    }
                }
            }
        }
    }
}

@Composable
private fun DayCell(cell: MonthCell, picked: Boolean, onPick: () -> Unit) {
    val c = Divan.colors
    val shape = RoundedCornerShape(12.dp)
    val count = cellCountFa(cell)
    Column(
        Modifier.fillMaxWidth().height(58.dp).testTag(if (cell.today) "cal-today" else "cal-day").clip(shape)
            .then(if (cell.future) Modifier.drawWithDash(c.lineStrong, 12.dp) else Modifier.background(if (cell.today) c.softGold else c.card).border(1.dp, if (cell.today || picked) c.goldFill.copy(alpha = if (cell.today) 0.8f else 0.5f) else c.lineHairline, shape))
            .then(if (picked && cell.future) Modifier.border(1.dp, c.goldFill.copy(alpha = 0.5f), shape) else Modifier)
            .clickable(role = Role.Button, onClickLabel = jDayFa(cell.date)) { onPick() }.padding(horizontal = 5.dp, vertical = 4.dp),
        verticalArrangement = Arrangement.SpaceBetween,
    ) {
        Text(faNum(cell.j.d), style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = if (cell.today) c.goldInk else if (cell.future) c.textMuted else c.textPrimary)
        Row(verticalAlignment = Alignment.CenterVertically) {
            if (count != null) Text(count, style = Divan.type.micro.copy(fontSize = 9.sp, lineHeight = 12.sp), color = c.textSecondary, maxLines = 1, modifier = Modifier.weight(1f))
            else Spacer(Modifier.weight(1f))
            if (!cell.future) Row(horizontalArrangement = Arrangement.spacedBy(2.dp)) {
                for (a in cell.day?.accounts.orEmpty().take(4)) Box(Modifier.size(5.dp).clip(CircleShape).background(brightOf(a)))
            }
        }
    }
}

// ----------------------------------------------------------------------------------------------------------- archive --
/** «بایگانی»: company → page (with its counts by kind), over a range; a channel without rows is dim until its route exists. */
@Composable
fun PublishArchiveScreen() {
    val c = Divan.colors
    val nav = LocalNav.current
    var range by rememberSaveable { mutableStateOf(30) }
    var channel by rememberSaveable { mutableStateOf<String?>(null) }
    val today = remember { todayTehran() }
    val from = if (range == 365) com.coinepro.hq.core.data.fromJalali(com.coinepro.hq.core.data.JDate(toJalali(today).y, 1, 1)) else today.minusDays(range - 1L)
    val q = rememberQuery("pub-tree:$range", *PUB_TAGS, maxAgeMs = 60_000) { gated(HubFeature.PUBLICATIONS) { publicationsTree(from.toString(), today.toString()) } }
    val has = served(HubFeature.PUBLICATIONS)
    val companies = com.coinepro.hq.ui.rememberCompanies()
    Page(onRefresh = { q.refresh() }, refreshing = q.state.refreshing) {
        item(key = "head") { CentreHead("publish/archive") }
        if (!has) { item(key = "old") { OldHub() }; return@Page }
        item(key = "range") {
            ScrollRow(spacing = 8.dp) {
                for ((d, l) in listOf(30 to "۳۰ روز", 7 to "۷ روز", 365 to "امسال")) FilterChip(l, range == d, { range = d })
            }
        }
        val t = q.data
        item(key = "channels") {
            val have = t?.companies.orEmpty().flatMap { co -> co.accounts.map { it.channel } }.toSet()
            ScrollRow(spacing = 8.dp) {
                FilterChip("همه‌ی کانال‌ها", channel == null, { channel = null })
                for (ch in PUB_CHANNELS) Box(Modifier.then(if (ch !in have) Modifier.padding(0.dp) else Modifier)) {
                    if (ch in have) FilterChip(pubChannelFa(ch), channel == ch, { channel = if (channel == ch) null else ch })
                    else Box(Modifier.clip(RoundedCornerShape(18.dp)).border(1.dp, c.lineDivider, RoundedCornerShape(18.dp)).padding(horizontal = 14.dp, vertical = 8.dp)) {
                        Text(pubChannelFa(ch), style = Divan.type.small, color = c.textMuted.copy(alpha = 0.6f))
                    }
                }
            }
        }
        when {
            t == null && q.error != null -> item(key = "error") { ErrorBlock(q.error, { q.refresh() }) }
            t == null -> item(key = "sk") { Skeletons(3) }
            t.companies.isEmpty() -> item(key = "empty") { Empty("در این بازه چیزی منتشر نشده", icon = DivanIcon.SEND) }
            else -> {
                items(t.companies, key = { "co-${it.code}" }) { co ->
                    val accounts = co.accounts.filter { channel == null || it.channel == channel }
                    if (accounts.isNotEmpty()) com.coinepro.hq.designsystem.HqCard(Modifier.fillMaxWidth().testTag("archive-company")) {
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                            Box(Modifier.size(40.dp).clip(RoundedCornerShape(13.dp)).background(c.tile).border(1.dp, c.goldFill.copy(alpha = 0.35f), RoundedCornerShape(13.dp)), contentAlignment = Alignment.Center) {
                                CompanyMark(co.code, height = 18.dp)
                            }
                            Column(Modifier.weight(1f)) {
                                Text(plain(co.nameFa), style = Divan.type.bodyStrong)
                                Text(if (range == 365) "امسال" else "${faNum(range)} روز اخیر" + if (co.accounts.size > 1) " · ${faNum(co.accounts.size)} پیج" else "", style = Divan.type.micro, color = c.textMuted)
                            }
                            Text(faNum(co.total), style = Divan.type.h2)
                        }
                        for (a in accounts) Row(
                            Modifier.fillMaxWidth().padding(top = 10.dp).testTag("archive-page").clip(RoundedCornerShape(16.dp)).background(c.tile)
                                .clickable(role = Role.Button, onClickLabel = "صفحه‌ی این پیج") { nav.go("publish/page/${a.account}") }.padding(10.dp),
                            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
                        ) {
                            Avatar(a.account)
                            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                                Text(plain("@${a.account}"), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold))
                                Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                                    for ((k, n) in a.byKind.entries.sortedByDescending { it.value }) Box(Modifier.clip(RoundedCornerShape(8.dp)).background(c.card).padding(horizontal = 6.dp, vertical = 1.dp)) {
                                        Text("${pubKindFa(k)} ${faNum(n)}", style = Divan.type.micro, color = c.textSecondary)
                                    }
                                }
                            }
                            DIcon(DivanIcon.NEXT, size = 14.dp, tint = c.textMuted)
                        }
                    }
                }
                // a company of the holding with nothing in the range: dim, so none is forgotten (no fixed number of companies)
                val quiet = companies.filter { co -> co.code != "HQ" && t.companies.none { it.code == co.code } }
                items(quiet, key = { "quiet-${it.code}" }) { co ->
                    Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(18.dp)).background(c.card.copy(alpha = 0.6f)).padding(14.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        CompanyMark(co.code, height = 16.dp, mono = true, ink = c.textMuted)
                        Text(plain(co.nameFa ?: co.code), style = Divan.type.small, color = c.textSecondary, modifier = Modifier.weight(1f))
                        Text("هنوز انتشاری ندارد", style = Divan.type.micro, color = c.textMuted)
                    }
                }
                item(key = "foot") { Text("هر شرکت و هر پیج داده است؛ پیج تازه با اولین انتشارش این‌جا می‌آید.", style = Divan.type.micro, color = c.textMuted) }
            }
        }
    }
}

@Composable
fun Avatar(account: String, size: androidx.compose.ui.unit.Dp = 38.dp) {
    val c = Divan.colors
    Box(Modifier.size(size).clip(CircleShape).border(1.5.dp, c.goldFill, CircleShape).padding(2.dp).clip(CircleShape).background(tintOf(account)), contentAlignment = Alignment.Center) {
        Text(account.removePrefix("@").take(1), style = Divan.type.small.copy(fontWeight = FontWeight.Bold), color = Color(0xFFF7F2E6))
    }
}

// -------------------------------------------------------------------------------------------------------- one page --
/** An account's page: its kinds as tabs, a grid of covers by day (newest first, a set as one), its states as filters. */
@Composable
fun PublishPageScreen(account: String) {
    val c = Divan.colors
    val uri = LocalUriHandler.current
    var kind by rememberSaveable(account) { mutableStateOf<String?>(null) }
    var state by rememberSaveable(account) { mutableStateOf<String?>(null) }
    val tree = rememberPubTree().data
    val entry = tree?.companies?.flatMap { co -> co.accounts.map { co to it } }?.firstOrNull { it.second.account == account }
    val q = rememberQuery("pub-page:$account:${kind.orEmpty()}:${state.orEmpty()}", *PUB_TAGS, maxAgeMs = 30_000) {
        gated(HubFeature.PUBLICATIONS) { publications(account = account, kind = kind, state = state, limit = 60) }
    }
    OnPublication { q.refresh() }
    val today = remember { todayTehran() }
    Page(onRefresh = { q.refresh() }, refreshing = q.state.refreshing) {
        item(key = "head") {
            PageHeader("@$account", eyebrow = listOfNotNull(entry?.first?.nameFa, pubChannelFa(entry?.second?.channel ?: "instagram")).joinToString(" · "), actions = {
                IconBtn(DivanIcon.GLOBE, "باز کردن در اینستاگرام", { runCatching { uri.openUri("https://instagram.com/$account") } })
            })
        }
        entry?.second?.let { a ->
            item(key = "stats") {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Count(a.total, "در ۳۰ روز")
                    Count(a.automations, "اتوماسیون")
                    Column(Modifier.weight(1f).clip(RoundedCornerShape(14.dp)).drawWithDash(c.lineStrong, 14.dp).padding(horizontal = 10.dp, vertical = 8.dp)) {
                        Text("—", style = Divan.type.h2, color = c.textMuted)
                        Text("بینش، وقتی داده آمد", style = Divan.type.micro, color = c.textMuted, maxLines = 1)
                    }
                }
            }
            item(key = "kinds") {
                ScrollRow(Modifier.testTag("page-kinds"), spacing = 8.dp) {
                    for ((k, n) in kindTabs(a.byKind)) FilterChip(if (k == null) "همه" else pubKindFa(k), kind == k, { kind = k }, count = n.takeIf { it > 0 })
                }
            }
        }
        item(key = "states") {
            ScrollRow(spacing = 8.dp) {
                for ((s, l) in listOf(null to "همه‌ی وضعیت‌ها", "published" to "منتشرشده", "scheduled" to "در صف", "held" to "نگه‌داشته", "failed" to "ناموفق"))
                    FilterChip(l, state == s, { state = if (state == s) null else s })
            }
        }
        val page = q.data
        when {
            page == null && q.error != null -> item(key = "error") { ErrorBlock(q.error, { q.refresh() }) }
            page == null -> item(key = "sk") { Skeleton(Modifier.fillMaxWidth().height(400.dp), radius = 16.dp) }
            page.items.isEmpty() -> item(key = "empty") { Empty("در این بازه چیزی منتشر نشده", icon = DivanIcon.SEND, body = "فیلترها را بردار یا تاریخ دیگری ببین.") }
            else -> {
                for ((d, cards) in cardsByDay(page.items)) {
                    item(key = "dh-$d") { Text(dayHeadFa(d, today), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary, modifier = Modifier.semantics { heading() }) }
                    items(cards.chunked(3), key = { row -> "dr-$d-${row.first().ref}" }) { row ->
                        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            for (k in row) PubTile(k, Modifier.weight(1f))
                            repeat(3 - row.size) { Spacer(Modifier.weight(1f)) }
                        }
                    }
                }
                item(key = "foot") { Text("عدد پایین هر کاور بازدید است، وقتی بینش برسد؛ تا آن موقع جایش خالی میماند.", style = Divan.type.micro, color = c.textMuted) }
            }
        }
    }
}

/** A cover in the page's grid: its kind or set, its hour, its state when it is not out. */
@Composable
fun PubTile(k: PublicationCard, modifier: Modifier = Modifier) {
    val c = Divan.colors
    val nav = LocalNav.current
    val set = k.set
    val shape = RoundedCornerShape(14.dp)
    Box(
        modifier.aspectRatio(9f / 16f).testTag("pub-tile").clip(shape)
            .then(if (k.state == "failed") Modifier.border(2.dp, c.negative, shape) else Modifier)
            .clickable(role = Role.Button, onClickLabel = "باز کردن") { nav.go(if (set != null) "publication/${k.ref}/set" else "publication/${k.ref}") },
    ) {
        PubCover(k.account, "", k.thumbFileId, Modifier.fillMaxSize(), radius = 14.dp, text = false)
        Column(Modifier.fillMaxSize().padding(8.dp), verticalArrangement = Arrangement.SpaceBetween) {
            val badge = when {
                k.state == "failed" -> "ناموفق"
                k.state == "held" -> "نگه‌داشته"
                set != null -> "${faNum(set.n)} استوری"
                k.state == "scheduled" -> faHour(k.at)
                else -> pubKindFa(k.kind)
            }
            Box(Modifier.clip(CircleShape).background(if (k.state == "failed") c.negative else Color.Black.copy(alpha = 0.55f)).padding(horizontal = 7.dp, vertical = 1.dp)) {
                Text(badge, style = Divan.type.micro.copy(fontSize = 10.sp, lineHeight = 14.sp, fontWeight = FontWeight.Bold), color = Color.White, maxLines = 1)
            }
            if (k.thumbFileId == null) Text(plain(k.titleFa), style = Divan.type.micro.copy(fontWeight = FontWeight.Bold, fontSize = 12.sp, lineHeight = 17.sp), color = Color(0xFFF7F2E6), maxLines = 4, overflow = TextOverflow.Ellipsis)
            Row {
                Text(if (k.state == "failed") (k.stateNoteFa ?: "") else faHour(k.at), style = Divan.type.micro.copy(fontSize = 10.sp, lineHeight = 13.sp), color = if (k.state == "failed") Color(0xFFFFD3D9) else Color(0xFFF7F2E6), maxLines = 2, modifier = Modifier.weight(1f))
                if (set != null) Text(setProgressFa(set.done, set.n), style = Divan.type.micro.copy(fontSize = 10.sp, lineHeight = 13.sp), color = Color(0xFFF7F2E6))
                else if (k.state == "scheduled") Text("در صف", style = Divan.type.micro.copy(fontSize = 10.sp, lineHeight = 13.sp), color = Color(0xFFF7F2E6))
            }
        }
    }
}

// ------------------------------------------------------------------------------------------------------------ search --
/** The search over every page and date: titles, topics, captions and words, folded the hub's way; each hit marked in its line. */
@Composable
fun PublishSearchScreen() {
    val c = Divan.colors
    var text by rememberSaveable { mutableStateOf("") }
    var asked by rememberSaveable { mutableStateOf("") }
    var scope by rememberSaveable { mutableStateOf<String?>(null) }
    LaunchedEffect(text) { delay(350); asked = text.trim() }
    val q = rememberQuery("pub-search:$asked", *PUB_TAGS, maxAgeMs = 30_000) {
        if (asked.isEmpty()) null else gated(HubFeature.PUBLICATIONS) { publications(q = asked, limit = 60) }
    }
    Page {
        item(key = "head") { PageHeader("جستجو در انتشارها", eyebrow = "همه‌ی پیج‌ها و همه‌ی تاریخ‌ها") }
        item(key = "field") {
            Box(Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(c.tile).border(1.dp, c.goldFill.copy(alpha = 0.5f), RoundedCornerShape(14.dp)).padding(horizontal = 14.dp, vertical = 12.dp)) {
                HqTextField(text, { text = it }, "موضوع، کپشن، کلمه یا عنوان", Modifier.fillMaxWidth().testTag("pub-search"))
            }
        }
        item(key = "scope") {
            ScrollRow(spacing = 8.dp) {
                for ((s, l) in listOf(null to "همه", "topic" to "موضوع", "caption" to "کپشن", "word" to "کلمه", "title" to "عنوان")) FilterChip(l, scope == s, { scope = s })
            }
        }
        if (asked.isNotEmpty()) item(key = "fold") { Text(plain("نوشتن «بلاکچین»، «بلاک چین» یا «بلاک‌چین» همان را پیدا میکند."), style = Divan.type.micro, color = c.textMuted) }
        val page = q.data
        when {
            asked.isEmpty() -> item(key = "hint") { Text("یک کلمه بنویس؛ هر ریلز، استوری، کپشن یا کلمه‌ای که آن را داشته باشد، از هر پیج، این‌جا می‌آید.", style = Divan.type.small, color = c.textSecondary) }
            page == null && q.error != null -> item(key = "error") { ErrorBlock(q.error, { q.refresh() }) }
            page == null -> item(key = "sk") { Skeletons(3) }
            else -> {
                val hits = page.items.filter { scope == null || it.match == scope }
                if (hits.isEmpty()) item(key = "none") { Empty("چیزی پیدا نشد", icon = DivanIcon.SEARCH, body = "کلمه‌ی دیگری امتحان کن.") }
                for ((acc, list) in hits.groupBy { it.account }) {
                    item(key = "sh-$acc") { Text(plain("@$acc · ${faNum(list.size)}"), style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = c.textMuted) }
                    items(list, key = { "s-${it.ref}" }) { k -> SearchHit(k, asked) }
                }
            }
        }
    }
}

@Composable
private fun SearchHit(k: PublicationCard, query: String) {
    val c = Divan.colors
    val nav = LocalNav.current
    Row(
        Modifier.fillMaxWidth().testTag("search-hit").clip(RoundedCornerShape(12.dp)).clickable(role = Role.Button) { nav.go(if (k.set != null) "publication/${k.ref}/set" else "publication/${k.ref}") }.padding(vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        PubCover(k.account, if (k.set != null) "${faNum(k.set.n)} تا" else pubKindFa(k.kind), k.thumbFileId, Modifier.size(width = 44.dp, height = 62.dp))
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(marked(k.titleFa, query, c.goldInk, c.softGold), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), maxLines = 2, overflow = TextOverflow.Ellipsis)
            val where = matchFa(k.match)
            val snippet = k.snippetFa?.takeIf { k.match != "title" }
            if (snippet != null) Text(marked("${where ?: ""}: «$snippet»", query, c.goldInk, c.softGold), style = Divan.type.micro, color = c.textMuted, maxLines = 2, overflow = TextOverflow.Ellipsis)
            Text("${tehranDate(k.at)?.let { jDayFa(it) } ?: ""} · ${pubStateFa(k.state)}", style = Divan.type.micro, color = c.textMuted, maxLines = 1)
        }
    }
}

private fun marked(text: String, query: String, ink: Color, bg: Color) = buildAnnotatedString {
    val r = hitRange(text, query)
    if (r == null) { append(text); return@buildAnnotatedString }
    append(text.substring(0, r.first))
    pushStyle(SpanStyle(color = ink, background = bg, fontWeight = FontWeight.Bold))
    append(text.substring(r.first, r.last + 1))
    pop()
    append(text.substring(r.last + 1))
}

// ----------------------------------------------------------------------------------------------------------- waiting --
/** «منتظر شما»: only what cannot move without him; each with its own buttons, one tap. Empty: said plainly. */
@Composable
fun PublishWaitingScreen() {
    val c = Divan.colors
    val q = rememberWaiting()
    Page(onRefresh = { q.refresh() }, refreshing = q.state.refreshing) {
        item(key = "head") { PageHeader("منتظر شما", eyebrow = "فقط چیزی که بی تو جلو نمیرود") }
        val w = q.data
        when {
            w == null && q.error != null -> item(key = "error") { ErrorBlock(q.error, { q.refresh() }) }
            w == null -> item(key = "sk") { Skeletons(2) }
            w.items.isEmpty() -> item(key = "none") { Empty("چیزی منتظر تو نیست", icon = DivanIcon.SEAL, body = "هر چه خودکار است، خودش جلو میرود.") }
            else -> items(w.items, key = { it.id }) { WaitingCard(it) { q.refresh() } }
        }
        item(key = "foot") {
            Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text("این‌جا نمی‌آید:", style = Divan.type.micro, color = c.textMuted)
                Text("اعلان روزمره · پیشنهاد ایجنت‌ها · کارت استخدام · هر چیزی که خودکار جلو میرود", style = Divan.type.micro, color = c.textMuted)
            }
        }
    }
}

@Composable
private fun WaitingCard(w: Waiting, onDone: () -> Unit) {
    val c = Divan.colors
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val scope = rememberCoroutineScope()
    var busy by remember { mutableStateOf<String?>(null) }
    val p = w.publication
    com.coinepro.hq.designsystem.HqCard(Modifier.fillMaxWidth().testTag("waiting-card")) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(listOfNotNull(p?.automationFa?.let { "کارگروه «$it»" }, "هر بار بپرس".takeIf { w.kind == "publish_ask" }).joinToString(" · "), style = Divan.type.micro, color = c.textMuted, modifier = Modifier.weight(1f))
            w.deadlineAt?.let { Text("تا پایان امروز", style = Divan.type.micro, color = c.goldInk) }
        }
        Row(Modifier.padding(top = 10.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            if (p != null) PubCover(p.account, p.titleFa, p.thumbFileId, Modifier.size(width = 84.dp, height = 150.dp), radius = 12.dp)
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(plain(w.titleFa), style = Divan.type.bodyStrong)
                if (p != null) Text(plain("${atHandle(p.account)} · ساعت ${faHour(p.at)}"), style = Divan.type.micro, color = c.textMuted)
            }
        }
        Row(Modifier.padding(top = 12.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            for (a in w.actions) HqButton(a.labelFa, {
                if (busy != null) return@HqButton
                busy = a.key
                scope.launch {
                    try { env.api.actOnWaiting(w.id, a.key); toasts.info("انجام شد"); onDone() } catch (_: Exception) { toasts.error("انجام نشد؛ دوباره امتحان کن.") } finally { busy = null }
                }
            }, Modifier.weight(1f), variant = if (a.primary) BtnVariant.PRIMARY else BtnVariant.SECONDARY, size = BtnSize.LG, loading = busy == a.key)
        }
        Text("اگر تا پایان روز جواب ندهی، این نوبت منتشر نمیشود و همین در بایگانی ثبت میشود.", style = Divan.type.micro, color = c.textMuted, modifier = Modifier.padding(top = 8.dp))
    }
}
