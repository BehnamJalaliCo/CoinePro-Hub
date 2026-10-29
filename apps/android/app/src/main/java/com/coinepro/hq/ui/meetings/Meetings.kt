package com.coinepro.hq.ui.meetings

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
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.coinepro.hq.core.format.OWNER_TZ
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.jTime
import com.coinepro.hq.core.format.jWeekday
import com.coinepro.hq.core.format.until
import com.coinepro.hq.core.net.Meeting
import com.coinepro.hq.core.net.MeetingItemIn
import com.coinepro.hq.core.net.MeetingType
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
import com.coinepro.hq.designsystem.HqSwitch
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.MeterBar
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.SegOption
import com.coinepro.hq.designsystem.Segmented
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.budgetTone
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.activity
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v14.HqSheet
import com.coinepro.hq.ui.v14.LabelPill
import com.coinepro.hq.ui.v14.rruleFa
import com.coinepro.hq.ui.v16.ChipRow
import com.coinepro.hq.ui.v16.CompanyChips
import com.coinepro.hq.ui.v16.Labelled
import com.coinepro.hq.ui.v17.ACTOR_ROLE_FA
import com.coinepro.hq.ui.v17.CoMark
import com.coinepro.hq.ui.v17.FilterRow
import com.coinepro.hq.ui.v17.IconTile
import com.coinepro.hq.ui.v17.MEETING_STATE
import com.coinepro.hq.ui.v17.MEETING_TYPE
import com.coinepro.hq.ui.v17.PRESENCE_FA
import com.coinepro.hq.ui.v17.ScopeChips
import com.coinepro.hq.ui.v17.budgetFig
import com.coinepro.hq.ui.v17.gov
import com.coinepro.hq.ui.v17.mmss
import com.coinepro.hq.ui.v17.pctOf
import com.coinepro.hq.ui.v17.rememberSecond
import java.time.LocalDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.UUID

private val TYPES = listOf("board", "company", "strategy", "war_room", "postmortem", "standup")

/** اتاق جلسه (contract §20.1): meetings run by code under a budget the owner sees beforehand; resolutions only by the owner's seal. */
@Composable
fun MeetingsScreen(tab0: String = "list") {
    val c = Divan.colors
    var tab by rememberSaveable { mutableStateOf(tab0) }
    var company by rememberSaveable { mutableStateOf<String?>(null) }
    var type by rememberSaveable { mutableStateOf<String?>(null) }
    var create by remember { mutableStateOf(false) }
    val q = rememberQuery("meetings:list:${type.orEmpty()}:${company.orEmpty()}", "meetings", "planner") { meetings(type, company) }
    val settings = rememberQuery("meetings:settings", "meetings", maxAgeMs = 60_000) { meetingSettings() }
    val r = refresher(q, settings)
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item {
            PageHeader("اتاق جلسه", eyebrow = "جلسه را کد اداره میکند؛ مصوبه فقط با مُهر تو") {
                HqButton("جلسه‌ی تازه", { create = true }, variant = BtnVariant.PRIMARY, icon = DivanIcon.ADD)
            }
        }
        item {
            Text(
                "حداکثر دو دور و چند سخنگوی مشخص در هر دستور، بودجه‌ی توکن جدا که پیش از شروع جلوی توست، هر ادعا با منبع و مخالف‌خوان از نظارت. مشاور کل در جلسه فقط با تو نجوا میکند و تو هر وقت بخواهی با صدا یا متن وارد میشوی.",
                style = Divan.type.small, color = c.textSecondary,
            )
        }
        item { Segmented(listOf(SegOption("list", "جلسه‌ها"), SegOption("settings", "تنظیمات")), tab, { tab = it }, Modifier.fillMaxWidth()) }
        if (tab == "settings") {
            item { MeetingSettings(settings.data, settings.error) { settings.refresh() } }
        } else {
            item {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    ScopeChips(company, { company = it }, allLabel = "همه‌ی جلسه‌ها")
                    FilterRow("همه‌ی نوع‌ها", type, TYPES.associateWith { MEETING_TYPE.getValue(it).fa }) { type = it }
                }
            }
            val xs = q.data
            when {
                xs == null && q.error != null -> item { ErrorBlock(q.error, { q.refresh() }) }
                xs == null -> item { Skeleton(Modifier.fillMaxWidth().height(260.dp), radius = 16.dp) }
                xs.isEmpty() -> item { Empty("جلسه‌ای نیست", icon = DivanIcon.MEETING) }
                else -> {
                    val live = xs.filter { it.live }
                    val next = xs.filter { it.before }.sortedBy { it.startsAt }
                    val past = xs.filter { it.state == "ended" || it.state == "cancelled" }.sortedByDescending { it.startsAt }
                    for (m in live) item(key = "live:${m.ref}") { LiveHero(m) }
                    item(key = "next") { MeetingGroup("پیش رو", "بودجه پیش از شروع جلوی توست", next, "جلسه‌ای پیش رو نیست.") }
                    item(key = "past") { MeetingGroup("گذشته", "با صورت‌جلسه و مصوبه‌ها", past, "هنوز جلسه‌ای تمام نشده.") }
                }
            }
        }
    }
    if (create) NewMeetingSheet { create = false }
}

@Composable
private fun MeetingGroup(title: String, note: String, xs: List<Meeting>, empty: String) {
    val c = Divan.colors
    HqCard(Modifier.fillMaxWidth(), padding = PaddingValues(horizontal = 8.dp, vertical = 8.dp)) {
        SectionTitle(title, Modifier.padding(horizontal = 8.dp), note = note)
        Spacer(Modifier.height(4.dp))
        if (xs.isEmpty()) Text(empty, Modifier.padding(12.dp), style = Divan.type.small, color = c.textMuted)
        for (m in xs) MeetingRow(m)
    }
}

/** One meeting in a list: its type, company, time, ref, the minutes' first line, and the budget (estimate before it starts). */
@Composable
private fun MeetingRow(m: Meeting) {
    val c = Divan.colors
    val nav = LocalNav.current
    val t = MEETING_TYPE[m.type]
    val over = m.budget.cap != null && m.budget.estimate > m.budget.cap
    Row(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).clickable(role = Role.Button) { nav.go("meetings/${m.ref}") }.padding(horizontal = 8.dp, vertical = 10.dp),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        IconTile(t?.icon ?: DivanIcon.MEETING, if (m.type == "war_room") c.negative else c.goldInk)
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
            Text(m.titleFa, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), maxLines = 1, overflow = TextOverflow.Ellipsis)
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                CoMark(m.company, ink = c.textMuted)
                Text(t?.fa.orEmpty(), style = Divan.type.micro, color = c.textMuted, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f, fill = false))
                Fig(m.ref, style = Divan.type.figureSmall, color = c.textMuted)
            }
            Text(
                listOfNotNull("${jWeekday(m.startsAt)}، ${jTime(m.startsAt)}", if (m.before) until(m.startsAt) else null).joinToString(" · "),
                style = Divan.type.micro, color = c.textMuted, maxLines = 1, overflow = TextOverflow.Ellipsis,
            )
            m.minutes?.let { mi ->
                val first = mi.summaryMd.orEmpty().replace(Regex("[*_`#>-]"), "").lines().firstOrNull { it.isNotBlank() }?.trim().orEmpty()
                Text(com.coinepro.hq.ui.v16.prose(first), style = Divan.type.caption, color = c.textSecondary, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                LabelPill(MEETING_STATE[m.state], m.state)
                if (m.mode == "written") Pill("نوشتاری", Tone.WARN)
                if (m.trimmedFa != null && m.mode != "written") Pill("کوتاه شد", Tone.LAPIS, icon = DivanIcon.INFO)
                Spacer(Modifier.weight(1f))
                Fig(if (m.before) budgetFig(m.budget.estimate, m.budget.cap) else budgetFig(m.budget.used, m.budget.cap), style = Divan.type.figureSmall, color = if (over) c.negative else c.textSecondary)
            }
        }
    }
}

/** A live meeting on top of the list: the room's seal, the item in progress, the budget, and the way in. */
@Composable
private fun LiveHero(m: Meeting) {
    val c = Divan.colors
    val nav = LocalNav.current
    val now = rememberSecond()
    val it = m.currentItem
    val share = pctOf(m.budget.used, m.budget.cap)
    HqCard(Modifier.fillMaxWidth(), tahrir = true) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            RoomSeal(m, 52.dp)
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    LiveClockPill(m, now)
                    Fig(m.ref, style = Divan.type.figureSmall, color = c.textMuted)
                }
                Text(m.titleFa, style = Divan.type.h3)
                if (it != null) Text(
                    "دستور ${it.n} از ${m.items.count { x -> x.state != "skipped" }}، دور ${it.round}: ${it.titleFa}",
                    style = Divan.type.caption, color = c.textSecondary,
                )
            }
        }
        Spacer(Modifier.height(12.dp))
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("بودجه‌ی توکن", style = Divan.type.micro, color = c.textMuted, modifier = Modifier.weight(1f))
            Fig(budgetFig(m.budget.used, m.budget.cap), style = Divan.type.figureSmall, color = c.textSecondary)
        }
        Spacer(Modifier.height(4.dp))
        MeterBar(share, tone = budgetTone(share))
        Spacer(Modifier.height(12.dp))
        HqButton("ورود به اتاق", { nav.go("meetings/${m.ref}") }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, icon = DivanIcon.MEETING)
    }
}

/** «زنده · 26:00»: how long the meeting has run. */
@Composable
internal fun LiveClockPill(m: Meeting, now: Long) {
    val start = com.coinepro.hq.core.format.instant(m.startsAt)?.toEpochMilli()
    val st = MEETING_STATE[m.state]
    if (st?.live == true && start != null) {
        val (bg, fg) = com.coinepro.hq.designsystem.toneColors(st.tone)
        Row(
            Modifier.height(24.dp).clip(CircleShape).background(bg).padding(horizontal = 10.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            com.coinepro.hq.designsystem.LiveDot(fg)
            Text(
                buildAnnotatedString { append("${st.fa} · "); fig(mmss(now - start)) },
                style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold, fontSize = 12.sp),
                color = fg, maxLines = 1,
            )
        }
    } else LabelPill(st, m.state)
}

// ---------------------------------------------------------------- settings --
private fun scheduleFa(t: MeetingType): String {
    val s = t.schedule ?: return if (t.key == "war_room") "خودکار با هشدار فوری" else "بعد از هر حادثه"
    if (t.key == "company") return "هفتگی · یکی برای هر شرکت، پخش بین روزها"
    if ("FREQ=MONTHLY" in s && "BYDAY=-1TH" in s) return "ماهانه · آخرین پنجشنبه"
    return rruleFa(s.replace(Regex("BYDAY=([A-Z]{2}),[^;]*"), "BYDAY=$1"))
}

/** The meeting types: when, who, the caps and the owner's presence; saved whole and sealed on the exact body. */
@Composable
private fun MeetingSettings(data: List<MeetingType>?, error: com.coinepro.hq.core.net.ApiException?, retry: () -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val act = activity()
    val c = Divan.colors
    val action = rememberAction()
    val edit = remember { mutableStateMapOf<String, MeetingType>() }
    var confirm by remember { mutableStateOf(false) }
    when {
        data == null && error != null -> ErrorBlock(error, retry)
        data == null -> Skeleton(Modifier.fillMaxWidth().height(300.dp), radius = 16.dp)
        else -> {
            val rows = data.map { edit[it.key] ?: it }
            HqCard(Modifier.fillMaxWidth()) {
                SectionTitle("تنظیمات جلسه‌ها", note = "روز، اعضا، سقف‌ها و حضور تو؛ ذخیره با اثر انگشت") {
                    HqButton("ذخیره", { confirm = true }, variant = BtnVariant.PRIMARY, size = BtnSize.SM, icon = DivanIcon.SEAL, enabled = edit.isNotEmpty())
                }
                for (t in rows) {
                    Spacer(Modifier.height(12.dp))
                    Box(Modifier.fillMaxWidth().height(1.dp).background(c.lineDivider))
                    Spacer(Modifier.height(12.dp))
                    TypeRow(t) { next -> val base = data.first { it.key == t.key }; if (next == base) edit.remove(t.key) else edit[t.key] = next }
                }
                Spacer(Modifier.height(12.dp))
                Text(
                    "«حضور تو»: زنده، خلاصه‌ی متنی، یا نسخه‌ی صوتی بعد از جلسه (تا text-to-speech بیاید مثل خلاصه). همه‌ی رزروهای جلسه‌ی یک روز روی هم حداکثر سهم روزانه‌ی جلسه‌ها از سقف ایجنت‌هاست؛ جلسه‌ای که جا نشود نوشتاری میشود. اتاق جنگ بیرون از این سهم است.",
                    style = Divan.type.caption, color = c.textMuted,
                )
            }
            if (confirm) AlertDialog(
                onDismissRequest = { confirm = false },
                containerColor = c.overlay,
                title = { Text("ذخیره‌ی تنظیمات جلسه‌ها", style = Divan.type.h3) },
                text = {
                    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Text("این جلسه‌ها عوض میشوند:", style = Divan.type.small, color = c.textSecondary)
                        for (k in edit.keys) Text(rows.firstOrNull { it.key == k }?.titleFa ?: k, style = Divan.type.small, color = c.textPrimary)
                        Text("مُهر به همین فهرست دقیق بسته است.", style = Divan.type.caption, color = c.textMuted)
                    }
                },
                confirmButton = {
                    HqButton("مُهر با passkey", {
                        action.gov(toasts) {
                            env.api.saveMeetingSettings(rows) { a, x -> env.auth.stepUp(act, a, x) }
                            env.cache.invalidate("meetings")
                            edit.clear(); confirm = false
                            toasts.ok("تنظیمات جلسه‌ها مُهر و ذخیره شد.")
                        }
                    }, variant = BtnVariant.PRIMARY, icon = DivanIcon.SEAL, loading = action.busy)
                },
                dismissButton = { HqButton("انصراف", { confirm = false }, variant = BtnVariant.GHOST) },
            )
        }
    }
}

@Composable
private fun TypeRow(t: MeetingType, onChange: (MeetingType) -> Unit) {
    val c = Divan.colors
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            DIcon(MEETING_TYPE[t.key]?.icon ?: DivanIcon.MEETING, size = 18.dp, tint = if (t.key == "war_room") c.negative else c.goldInk)
            Text(t.titleFa, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), modifier = Modifier.weight(1f))
            Text("فعال", style = Divan.type.caption, color = c.textSecondary)
            HqSwitch(t.enabled, { onChange(t.copy(enabled = it)) }, "فعال: ${t.titleFa}")
        }
        Text(scheduleFa(t) + " · " + t.members.roles.joinToString("، ") { ACTOR_ROLE_FA[it] ?: it }, style = Divan.type.caption, color = c.textSecondary)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Stepper(t.maxRounds, 1..3, "دور") { onChange(t.copy(maxRounds = it)) }
            Stepper(t.maxSpeakers, 2..8, "نفر") { onChange(t.copy(maxSpeakers = it)) }
            val b = t.budgetTokens
            if (b == null) Box(Modifier.height(32.dp), contentAlignment = Alignment.Center) { Text("بودجه: بی‌سقف", style = Divan.type.caption, color = c.textSecondary) }
            else Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("بودجه", style = Divan.type.caption, color = c.textSecondary)
                CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
                    HqTextField((b / 1000).toString(), { v -> onChange(t.copy(budgetTokens = (v.filter(Char::isDigit).toLongOrNull() ?: 0) * 1000)) }, "0", Modifier.width(72.dp), maxLength = 5, figure = true)
                }
                Fig("K", style = Divan.type.figureSmall, color = c.textMuted)
            }
        }
        ChipRow { for ((k, v) in PRESENCE_FA) FilterChip(v.first, t.ownerPresence == k, { onChange(t.copy(ownerPresence = k)) }) }
    }
}

/** − n unit +, inside [range]. */
@Composable
private fun Stepper(value: Int, range: IntRange, unit: String, onChange: (Int) -> Unit) {
    val c = Divan.colors
    Row(Modifier.height(32.dp).clip(CircleShape).border(1.dp, c.lineStrong, CircleShape), verticalAlignment = Alignment.CenterVertically) {
        StepKey("−", value > range.first) { onChange(value - 1) }
        Text("$value $unit", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, modifier = Modifier.padding(horizontal = 4.dp))
        StepKey("+", value < range.last) { onChange(value + 1) }
    }
}

@Composable
private fun StepKey(sign: String, enabled: Boolean, onClick: () -> Unit) {
    val c = Divan.colors
    Box(Modifier.size(32.dp).clip(CircleShape).clickable(enabled = enabled, role = Role.Button, onClickLabel = if (sign == "+") "بیشتر" else "کمتر", onClick = onClick), contentAlignment = Alignment.Center) {
        Fig(sign, style = Divan.type.figure, color = if (enabled) c.goldInk else c.disabledText)
    }
}

// -------------------------------------------------------------- new meeting --
private val AD_HOC = listOf("board", "company", "strategy", "postmortem")
private val BOXES = listOf(5, 10, 15, 20, 30)
private val LOCAL: DateTimeFormatter = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm")

/** An ad-hoc meeting: the same speaker rule, budget and daily share as a scheduled one. */
@Composable
private fun NewMeetingSheet(onClose: () -> Unit) {
    val env = LocalEnv.current
    val nav = LocalNav.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val action = rememberAction()
    var type by rememberSaveable { mutableStateOf("company") }
    var company by rememberSaveable { mutableStateOf<String?>(null) }
    var whenText by rememberSaveable { mutableStateOf("") }
    val titles = remember { mutableStateListOf("") }
    val boxes = remember { mutableStateListOf(10) }
    var key by remember { mutableStateOf<String?>(null) }
    val perCompany = type == "company" || type == "postmortem"
    val at = runCatching { LocalDateTime.parse(whenText.trim(), LOCAL).atZone(ZoneId.of(OWNER_TZ)).toInstant() }.getOrNull()
    val valid = at != null && (!perCompany || company != null) && titles.any { it.isNotBlank() }
    HqSheet(onClose, "جلسه‌ی تازه", sub = "سخنگوها، بودجه و سهم روزانه همان قاعده‌ی جلسه‌های زمان‌بندی‌شده است.") {
        Labelled("نوع") { ChipRow { for (k in AD_HOC) FilterChip(MEETING_TYPE.getValue(k).fa, type == k, { type = k }) } }
        if (perCompany) Labelled("شرکت") { CompanyChips(company, { company = it }, all = false) }
        Labelled("زمان شروع") {
            CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
                HqTextField(whenText, { whenText = it }, "2026-10-20 14:00", Modifier.fillMaxWidth(), maxLength = 16, figure = true)
            }
        }
        Labelled("دستورها") {
            for (i in titles.indices) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                HqTextField(titles[i], { titles[i] = it }, "دستور ${i + 1}", Modifier.weight(1f), maxLength = 200)
                // One tap moves the item's time box to the next length.
                Box(
                    Modifier.height(44.dp).clip(RoundedCornerShape(10.dp)).border(1.dp, c.lineStrong, RoundedCornerShape(10.dp))
                        .clickable(role = Role.Button, onClickLabel = "وقت دستور") { boxes[i] = BOXES[(BOXES.indexOf(boxes[i]) + 1) % BOXES.size] }.padding(horizontal = 10.dp),
                    contentAlignment = Alignment.Center,
                ) { Text("${boxes[i]} دقیقه", style = Divan.type.caption, color = c.textSecondary, textAlign = TextAlign.Center) }
                if (titles.size > 1) com.coinepro.hq.designsystem.IconBtn(DivanIcon.CLOSE, "حذف دستور", { titles.removeAt(i); boxes.removeAt(i) })
            }
            if (titles.size < 8) HqButton("دستور دیگر", { titles.add(""); boxes.add(10) }, variant = BtnVariant.GHOST, size = BtnSize.SM, icon = DivanIcon.ADD)
        }
        HqButton("بساز", {
            val start = at ?: return@HqButton
            val k = key ?: UUID.randomUUID().toString().also { key = it }
            action.gov(toasts) {
                val items = titles.indices.filter { titles[it].isNotBlank() }.map { MeetingItemIn(titles[it].trim(), boxes[it]) }
                val m = env.api.createMeeting(type, if (perCompany) company else null, start.toString(), items, k)
                key = null
                env.cache.invalidate("meetings", "planner", "calendar")
                toasts.ok("جلسه‌ی ${m.ref} ساخته شد؛ بودجه و سخنگوها با قاعده.")
                onClose()
                nav.go("meetings/${m.ref}")
            }
        }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, size = BtnSize.LG, icon = DivanIcon.ADD, enabled = valid, loading = action.busy)
        if (at == null && whenText.isNotBlank()) Text(buildAnnotatedString { append("زمان را این‌طور بنویس: "); fig("2026-10-20 14:00") }, style = Divan.type.caption, color = c.warning)
        Text("زمان به وقت تهران.", style = Divan.type.micro, color = c.textMuted)
    }
}
