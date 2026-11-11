package com.coinepro.hq.ui.v31

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.CAL_KIND31_FA
import com.coinepro.hq.core.data.PLATFORM_FA
import com.coinepro.hq.core.data.calStateFa
import com.coinepro.hq.core.data.calendarWeek
import com.coinepro.hq.core.data.platformFa
import com.coinepro.hq.core.data.platformIcon
import com.coinepro.hq.core.format.HqClock
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.jDate
import com.coinepro.hq.core.format.jTime
import com.coinepro.hq.core.format.jWeekday
import com.coinepro.hq.core.net.Campaign
import com.coinepro.hq.core.net.CampaignItem
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.gated
import com.coinepro.hq.core.net.idText
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.ScrollRow
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v29.CoName
import com.coinepro.hq.ui.v29.Para
import com.coinepro.hq.ui.v29.plain
import com.coinepro.hq.ui.v29.served
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.put

// Contract §31.5 ⟨1.13⟩ «تقویم کمپین»: one calendar for every company: line runs, newsletters, ad campaigns and campaigns, a week at a time
// (Saturday to Friday). Conflicts (two posts on one channel too close, a holiday) are marked on the item. The lines' calendar of §30 is
// the «خط تولید» filter here. Campaigns are added and changed on this page.

@Composable
fun CampaignCalendarScreen(kind0: String? = null) {
    val nav = LocalNav.current
    var offset by rememberSaveable { mutableIntStateOf(0) }
    var company by rememberSaveable { mutableStateOf<String?>(null) }
    var kind by rememberSaveable { mutableStateOf(kind0) }
    var editing by rememberSaveable { mutableStateOf<String?>(null) }
    val week = calendarWeek(offset)
    val from = week.first
    val to = week.second
    val companies = rememberCompanies().filter { it.kind != "holding" }
    val q = rememberQuery("campaign-calendar:$from:$to:${company.orEmpty()}", "campaign-calendar", "lines", "line-runs", "growth", maxAgeMs = 30_000) { gated(HubFeature.GROWTH) { campaignCalendar(from, to, company) } }
    val camps = rememberQuery("campaigns:${company.orEmpty()}", "campaign-calendar", "growth", maxAgeMs = 30_000) { gated(HubFeature.GROWTH) { campaigns(company) } }
    val r = refresher(q, camps)
    val has = served(HubFeature.GROWTH)
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item { PageHeader("تقویم کمپین", eyebrow = "هر چه قرار است منتشر یا فرستاده شود، برای همه‌ی شرکت‌ها") }
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
                ScrollRow {
                    FilterChip("همه‌ی نوع‌ها", kind == null, { kind = null })
                    for ((k, l) in CAL_KIND31_FA) FilterChip(l, kind == k, { kind = k })
                }
            }
        }
        val items = q.data?.filter { kind == null || it.kind == kind }
        when {
            !has -> item { Empty("تقویم کمپین با به‌روزرسانی بعدی هاب میاید", icon = DivanIcon.PLANNER) }
            items == null && q.error != null -> item { ErrorBlock(q.error, { q.refresh() }) }
            items == null -> item { Skeleton(Modifier.fillMaxWidth().height(200.dp), radius = 16.dp) }
            else -> {
                val conflicts = items.count { it.conflictFa != null }
                if (conflicts > 0) item(key = "conflicts") {
                    HqCard(Modifier.fillMaxWidth(), color = Divan.colors.softWarning) {
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            DIcon(DivanIcon.URGENT, size = 18.dp, tint = Divan.colors.warning)
                            Text(plain("$conflicts تداخل در این هفته؛ روی هر مورد دلیلش آمده"), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = Divan.colors.textPrimary)
                        }
                    }
                }
                if (items.isEmpty()) item(key = "empty") { Empty("این هفته چیزی در برنامه نیست", icon = DivanIcon.PLANNER, body = "برنامه‌ی هر خط یا خبرنامه را در صفحه‌ی خودش میگذاری؛ کمپین را همین پایین.") }
                else items.groupBy { it.day }.toSortedMap().forEach { (day, list) ->
                    item(key = "day-$day") { CalendarDay(day, list) { x -> routeOf(x)?.let(nav::go) } }
                }
            }
        }
        item(key = "campaigns") {
            CampaignsSection(camps.data, camps.error == null || camps.data != null, onAdd = { editing = "new" }, onEdit = { editing = it })
        }
    }
    editing?.let { id ->
        val camp = camps.data.orEmpty().firstOrNull { it.id.idText == id }
        com.coinepro.hq.ui.v14.HqSheet({ editing = null }, if (id == "new") "کمپین تازه" else "ویرایش کمپین", sub = "کمپین روی تقویم میافتد و با انتشارهای هم‌زمان مقایسه میشود.") {
            CampaignForm(camp, company) { editing = null }
        }
    }
}

/** Where a calendar item opens (a line, or nothing for what has no page of its own). */
fun routeOf(x: CampaignItem): String? = when (x.kind) {
    "line" -> x.ref.takeIf { it.startsWith("LN-") }?.let { "lines/$it" }
    else -> null
}

/** One day: each item with its hour, kind, company and state; a conflicting one is tinted and says why. */
@Composable
fun CalendarDay(day: String, list: List<CampaignItem>, onOpen: (CampaignItem) -> Unit) {
    val c = Divan.colors
    val today = HqClock.today().toString()
    HqCard(Modifier.fillMaxWidth()) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(plain(jWeekday(day)), style = Divan.type.bodyStrong, modifier = Modifier.weight(1f))
            if (day == today) Pill("امروز", Tone.SILVER)
            Text(plain("${list.size} مورد"), style = Divan.type.caption, color = c.textMuted)
        }
        Column(Modifier.padding(top = 6.dp)) {
            list.sortedBy { it.at ?: "" }.forEachIndexed { i, x ->
                if (i > 0) HorizontalDivider(color = c.lineDivider)
                val st = calStateFa(x.state)
                Column(
                    Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).then(if (x.conflictFa != null) Modifier.background(c.softWarning) else Modifier)
                        .clickable(role = Role.Button, enabled = routeOf(x) != null) { onOpen(x) }.padding(vertical = 10.dp, horizontal = 4.dp),
                    verticalArrangement = Arrangement.spacedBy(4.dp),
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        Text(plain(x.at?.let { jTime(it) } ?: "تمام روز"), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, modifier = Modifier.width(52.dp))
                        DIcon(x.platform?.let { platformIcon(it) } ?: DivanIcon.PLANNER, size = 18.dp, tint = c.textSecondary)
                        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                            Text(plain(x.titleFa), style = Divan.type.small, maxLines = 2)
                            Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                                CoName(x.company, height = 11.dp, color = c.textMuted)
                                Text(CAL_KIND31_FA[x.kind] ?: x.kind, style = Divan.type.micro, color = c.textMuted)
                            }
                        }
                        Pill(st.first, st.second, dot = true)
                    }
                    x.conflictFa?.let { Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) { DIcon(DivanIcon.URGENT, size = 14.dp, tint = c.warning); Para(it, Modifier.weight(1f), style = Divan.type.caption, color = c.warning) } }
                }
            }
        }
    }
}

@Composable
fun CampaignsSection(list: List<Campaign>?, ok: Boolean, onAdd: () -> Unit, onEdit: (String) -> Unit) {
    val c = Divan.colors
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        SectionTitle("کمپین‌ها", note = "بازه‌ی چند‌روزه با هدف، کانال و بودجه") {
            HqButton("کمپین تازه", onAdd, variant = BtnVariant.PRIMARY, size = BtnSize.SM, icon = DivanIcon.ADD)
        }
        when {
            list == null && ok -> Skeleton(Modifier.fillMaxWidth().height(80.dp), radius = 16.dp)
            list.isNullOrEmpty() -> Text("هنوز کمپینی نیست.", style = Divan.type.caption, color = c.textMuted)
            else -> for (k in list) HqCard(Modifier.fillMaxWidth(), onClick = { onEdit(k.id.idText) }) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Column(Modifier.weight(1f)) {
                        Text(plain(k.titleFa), style = Divan.type.bodyStrong, maxLines = 2)
                        CoName(k.company, height = 11.dp, color = c.textMuted)
                    }
                    Pill(calStateFa(k.state).first, calStateFa(k.state).second)
                }
                Text(plain(jDate(k.starts) + " تا " + jDate(k.ends) + (if (k.channels.isNotEmpty()) "؛ " + k.channels.joinToString("، ") { platformFa(it) } else "")), style = Divan.type.caption, color = c.textSecondary, modifier = Modifier.padding(top = 6.dp))
                if (k.goalFa.isNotBlank()) Text(plain("هدف: " + k.goalFa), style = Divan.type.caption, color = c.textMuted)
            }
        }
    }
}

/** A campaign made or changed (a day is written «2026-11-05»). */
@Composable
fun CampaignForm(camp: Campaign?, company0: String?, onDone: () -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val action = rememberAction()
    val del = rememberAction()
    val c = Divan.colors
    val companies = rememberCompanies().filter { it.kind != "holding" }
    val key = camp?.id?.idText
    var co by rememberSaveable(key) { mutableStateOf(camp?.company ?: company0 ?: companies.firstOrNull()?.code.orEmpty()) }
    var title by rememberSaveable(key) { mutableStateOf(camp?.titleFa.orEmpty()) }
    var goal by rememberSaveable(key) { mutableStateOf(camp?.goalFa.orEmpty()) }
    var starts by rememberSaveable(key) { mutableStateOf(camp?.starts ?: HqClock.today().plusDays(1).toString()) }
    var ends by rememberSaveable(key) { mutableStateOf(camp?.ends ?: HqClock.today().plusDays(7).toString()) }
    var channels by rememberSaveable(key) { mutableStateOf(camp?.channels.orEmpty().joinToString(",")) }
    var budget by rememberSaveable(key) { mutableStateOf(camp?.budget?.toLong()?.toString().orEmpty()) }
    val picked = channels.split(',').filter { it.isNotBlank() }
    val dayOk = Regex("^\\d{4}-\\d{2}-\\d{2}$")
    val valid = co.isNotBlank() && title.trim().length >= 2 && dayOk.matches(starts) && dayOk.matches(ends) && ends >= starts
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("شرکت", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            for (x in companies) FilterChip(x.nameFa ?: x.code, co == x.code, { if (camp == null) co = x.code })
        }
        Text("نام کمپین", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
        HqTextField(title, { title = it }, "مثلاً هفته‌ی آموزش طلا", Modifier.fillMaxWidth(), maxLength = 120)
        Text("هدف", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
        HqTextField(goal, { goal = it }, "مثلاً هزار دنبال‌کننده‌ی تازه", Modifier.fillMaxWidth(), maxLength = 200)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text("از (میلادی)", style = Divan.type.micro, color = c.textMuted)
                HqTextField(starts, { starts = it }, "2026-11-05", Modifier.fillMaxWidth(), figure = true, maxLength = 10)
            }
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text("تا (میلادی)", style = Divan.type.micro, color = c.textMuted)
                HqTextField(ends, { ends = it }, "2026-11-11", Modifier.fillMaxWidth(), figure = true, maxLength = 10)
            }
        }
        Text("کانال‌ها", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            for (p in PLATFORM_FA.keys) FilterChip(platformFa(p), p in picked, { channels = (if (p in picked) picked - p else picked + p).joinToString(",") })
        }
        Text("بودجه (اختیاری)", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
        HqTextField(budget, { budget = it.filter { ch -> ch.isDigit() } }, "—", Modifier.fillMaxWidth(), figure = true, maxLength = 12)
        HqButton(if (camp == null) "بساز" else "ذخیره", {
            action.run {
                val body = buildJsonObject {
                    put("company", co); put("title_fa", title.trim()); put("goal_fa", goal.trim()); put("starts", starts); put("ends", ends)
                    put("channels", JsonArray(picked.map { JsonPrimitive(it) })); put("budget", budget.toLongOrNull())
                }
                env.api.saveCampaign(key, body)
                env.cache.invalidate("campaign-calendar")
                toasts.ok("کمپین ذخیره شد.")
                onDone()
            }
        }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, icon = DivanIcon.SEAL, enabled = valid, loading = action.busy)
        if (camp != null) HqButton("حذف", { del.run { env.api.deleteCampaign(camp.id.idText); env.cache.invalidate("campaign-calendar"); toasts.ok("کمپین حذف شد."); onDone() } }, Modifier.fillMaxWidth(), variant = BtnVariant.DANGER, size = BtnSize.SM, icon = DivanIcon.DISMISS, loading = del.busy)
    }
}
