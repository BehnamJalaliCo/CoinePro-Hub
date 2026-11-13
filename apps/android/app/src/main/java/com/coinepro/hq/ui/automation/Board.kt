package com.coinepro.hq.ui.automation

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.BOARD_KINDS
import com.coinepro.hq.core.data.autoStateFa
import com.coinepro.hq.core.data.boardGroups
import com.coinepro.hq.core.data.faNum
import com.coinepro.hq.core.data.healthKeyFa
import com.coinepro.hq.core.data.healthLineFa
import com.coinepro.hq.core.data.healthTone
import com.coinepro.hq.core.data.lineRunStateFa
import com.coinepro.hq.core.data.lineRunStateTone
import com.coinepro.hq.core.data.versionFa
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.format.jTime
import com.coinepro.hq.core.format.jWeekday
import com.coinepro.hq.core.format.usd
import com.coinepro.hq.core.net.AutomationBoard
import com.coinepro.hq.core.net.BoardItem
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
import com.coinepro.hq.designsystem.HqSwitch
import com.coinepro.hq.designsystem.LiveDot
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.ScrollRow
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.StatRow
import com.coinepro.hq.designsystem.StatTile
import com.coinepro.hq.designsystem.Text
import com.coinepro.hq.designsystem.facts
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.companyOf
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v29.plain
import com.coinepro.hq.ui.v29.served

// Contract §59.10 ⟨1.37⟩: «اتوماسیون‌ها», one place for everything that runs by itself: the working groups' daily flows (n8n ticks
// them), the standing routines, the standing word on publishing, the production lines, the automations from one sentence and the archive's
// rules. At its head the road's health (n8n, IG-Hub, each company's publish path, the helpers' browser, AI Studio, the workshop) and
// today in three figures; the owner's day in one line; then each automation with its switch (his, one tap), its last run and the next.
// On a hub before §59 the page is the automations from one sentence (§31.7), as before.

@Composable
internal fun rememberBoard() = rememberQuery("automation-board", "automations", maxAgeMs = 15_000) { gated(HubFeature.AUTOMATIONS) { automationBoard() } }

@Composable
internal fun rememberToday() = rememberQuery("automations-today", "automations", maxAgeMs = 60_000) { gated(HubFeature.AUTOMATIONS) { automationsToday() } }

@Composable
fun AutomationsBoardScreen() {
    if (!served(HubFeature.AUTOMATIONS)) { com.coinepro.hq.ui.v31.AutomationsScreen(); return }
    val env = LocalEnv.current
    val nav = LocalNav.current
    val c = Divan.colors
    val q = rememberBoard()
    val today = rememberToday()
    val companies = rememberCompanies()
    val r = refresher(q, today)
    var kind by rememberSaveable { mutableStateOf<String?>(null) }
    var company by rememberSaveable { mutableStateOf<String?>(null) }
    LaunchedEffect(env) { env.stream.events.collect { e -> if (e.type.startsWith("automation.")) { q.refresh(); if (e.type == "automation.summary") today.refresh() } } }
    val b: AutomationBoard? = q.data
    val on = served(HubFeature.AUTOMATIONS)
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item(key = "head") {
            PageHeader("اتوماسیون‌ها", eyebrow = "هر چه خودش اجرا میشود؛ کلید هر کدام با توست") {
                HqButton("تقویم", { nav.go("automations/calendar") }, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.PLANNER)
            }
        }
        when {
            b == null && q.error != null -> item(key = "err") { ErrorBlock(q.error, { q.refresh() }) }
            b == null && !on -> item(key = "none") { Empty("این بخش با به‌روزرسانی بعدی هاب می‌آید", icon = DivanIcon.SETTINGS) }
            b == null -> items(3, key = { "sk-$it" }) { Skeleton(Modifier.fillMaxWidth().height(if (it == 0) 120.dp else 88.dp), radius = 14.dp) }
            else -> {
                item(key = "health") { HealthCard(b) }
                item(key = "today") {
                    StatRow {
                        StatTile("اجرای امروز", faNum(b.today.runs), Modifier.weight(1f), figure = false)
                        StatTile("منتشر شد", faNum(b.today.published), Modifier.weight(1f), figure = false)
                        StatTile("هزینه‌ی امروز", usd(b.today.costUsd), Modifier.weight(1f))
                    }
                }
                today.data?.takeIf { it.lineFa.isNotBlank() }?.let { d -> item(key = "day") { DayCard(d.lineFa) } }
                item(key = "filters") {
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        val kinds = BOARD_KINDS.filter { (k, _) -> b.items.any { it.kind == k } }
                        if (kinds.size > 1) ScrollRow {
                            FilterChip("همه", kind == null, { kind = null }, count = b.items.size)
                            for ((k, fa) in kinds) FilterChip(fa, kind == k, { kind = if (kind == k) null else k }, count = b.items.count { it.kind == k })
                        }
                        val codes = b.items.mapNotNull { it.company }.distinct()
                        if (codes.size > 1) ScrollRow {
                            FilterChip("همه‌ی شرکت‌ها", company == null, { company = null })
                            for (code in codes) FilterChip(b.items.firstOrNull { it.company == code }?.companyFa ?: companyOf(companies, code).nameFa, company == code, { company = if (company == code) null else code })
                        }
                    }
                }
                val shown = b.items.filter { (kind == null || it.kind == kind) && (company == null || it.company == company) }
                if (shown.isEmpty()) item(key = "empty") {
                    Empty("اتوماسیونی نیست", icon = DivanIcon.SETTINGS, body = "از «کتابخانه‌ی کارگروه‌ها» یک کارگروه را در شرکتی به کار ببر، یا با یک جمله بساز.")
                }
                // one list, in the order of the kinds (each row says its kind); the chips above narrow it
                val ordered = boardGroups(shown).flatMap { (_, g) -> g }
                if (ordered.isNotEmpty()) item(key = "list") {
                    HqCard(Modifier.fillMaxWidth(), padding = PaddingValues(vertical = 4.dp)) {
                        ordered.forEachIndexed { i, it ->
                            if (i > 0) HorizontalDivider(color = c.lineDivider)
                            BoardRow(it, onChanged = { q.refresh() })
                        }
                    }
                }
                item(key = "make") {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        HqButton("از کتابخانه", { nav.go("playbooks") }, Modifier.weight(1f), variant = BtnVariant.SECONDARY, icon = DivanIcon.DEPARTMENT)
                        HqButton("از یک جمله", { nav.go("automations/sentence") }, Modifier.weight(1f), variant = BtnVariant.SECONDARY, icon = DivanIcon.EDIT)
                    }
                }
            }
        }
    }
}

/** The road in one line and its parts as dots: green, amber, red, each with its own short words. */
@Composable
private fun HealthCard(b: AutomationBoard) {
    val c = Divan.colors
    val (line, tone) = remember(b.health) { healthLineFa(b.health) }
    HqCard(Modifier.fillMaxWidth().testTag("board-health")) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            DIcon(if (tone == Tone.POS) DivanIcon.SEAL else DivanIcon.URGENT, size = 16.dp, tint = toneInk(tone))
            Text(plain(line), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, modifier = Modifier.weight(1f), maxLines = 2, overflow = TextOverflow.Ellipsis)
        }
        if (b.health.isNotEmpty()) FlowRow(Modifier.padding(top = 10.dp), horizontalArrangement = Arrangement.spacedBy(10.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            for (h in b.health) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(5.dp)) {
                LiveDot(toneInk(healthTone(h.state)), live = false)
                Text(healthKeyFa(h.key), style = Divan.type.micro, color = c.textSecondary, maxLines = 1)
            }
        }
    }
}

@Composable
private fun toneInk(t: Tone) = when (t) { Tone.POS -> Divan.colors.positive; Tone.WARN -> Divan.colors.warning; Tone.NEG -> Divan.colors.negative; else -> Divan.colors.textMuted }

/** The owner's day in one line (§59.9): «امروز: ریلز «…» منتشر شد، ۱۲ کامنت، ۹ دایرکت، ۴ کلیک». */
@Composable
internal fun DayCard(line: String, modifier: Modifier = Modifier) {
    val c = Divan.colors
    Row(
        modifier.fillMaxWidth().testTag("day-card").clip(RoundedCornerShape(14.dp)).background(c.tile).padding(12.dp),
        verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        DIcon(DivanIcon.REPORT, size = 18.dp, tint = c.silverInk)
        Text(plain(line), style = Divan.type.small, color = c.textPrimary, modifier = Modifier.weight(1f))
    }
}

/** One automation: its name, whose and what it comes from, when it runs, its last run and the next, today's cost; its switch. */
@Composable
private fun BoardRow(it: BoardItem, onChanged: () -> Unit) {
    val env = LocalEnv.current
    val nav = LocalNav.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val go = rememberAction()
    var on by remember(it.ref, it.state) { mutableStateOf(it.state == "on") }
    Row(
        Modifier.fillMaxWidth().testTag("board-row").clickable(role = Role.Button, onClickLabel = "باز کن", enabled = it.opens != null) { it.opens?.let(nav::go) }
            .padding(horizontal = 14.dp, vertical = 11.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
            Text(plain(it.titleFa.ifBlank { "اتوماسیون" }), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text(
                remember(it) { facts(com.coinepro.hq.core.data.boardKindOneFa(it.kind), it.companyFa, it.version?.let { v -> versionFa(v) }, it.whenFa.ifBlank { null }) },
                style = Divan.type.micro, color = c.textMuted, maxLines = 1, overflow = TextOverflow.Ellipsis,
            )
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                val last = it.last
                if (last != null && last.state.isNotBlank()) {
                    Pill(lineRunStateFa(last.state), lineRunStateTone(last.state), dot = last.state != "running", live = last.state == "running")
                    Text(
                        remember(it) { facts(last.at?.let { a -> ago(a) }, last.noteFa.ifBlank { null }) },
                        style = Divan.type.micro, color = c.textSecondary, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f, fill = false),
                    )
                } else if (it.state != "on") {
                    val (fa, tone) = autoStateFa(it.state)
                    Pill(fa, tone)
                }
            }
            val tail = facts(it.nextAt?.let { n -> "بعدی ${jWeekday(n)} ${jTime(n)}" }, it.costTodayUsd?.let { x -> "امروز ${usd(x)}" })
            if (tail.isNotEmpty()) Text(tail, style = Divan.type.micro, color = c.textMuted, maxLines = 1)
        }
        if (it.switchable) HqSwitch(on, { want ->
            on = want
            go.run(onError = { e -> on = !want; toasts.error(e.messageFa) }) {
                env.api.switchAutomation(it.ref, want)
                env.cache.invalidate("automations", "groups", "playbooks")
                toasts.ok(if (want) "«${it.titleFa}» روشن شد." else "«${it.titleFa}» خاموش شد.")
                onChanged()
            }
        }, if (on) "روشن" else "خاموش")
        else Pill(autoStateFa(it.state).first, autoStateFa(it.state).second)
    }
}

/** The home's one quiet line (§59.13): how many run by themselves and the owner's day; a tap opens the board. Nothing on an older hub. */
@Composable
fun AutomationsLine(modifier: Modifier = Modifier) {
    if (!served(HubFeature.AUTOMATIONS)) return
    val b = rememberBoard().data ?: return
    val day = rememberToday().data
    val nav = LocalNav.current
    val c = Divan.colors
    val on = b.items.count { it.state == "on" }
    if (b.items.isEmpty()) return
    Row(
        modifier.fillMaxWidth().heightIn(min = 40.dp).testTag("automations-line").clip(RoundedCornerShape(10.dp))
            .clickable(role = Role.Button, onClickLabel = "اتوماسیون‌ها") { nav.go("automations") }.padding(vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Box(Modifier.size(15.dp), contentAlignment = Alignment.Center) { DIcon(DivanIcon.SETTINGS, size = 15.dp, tint = c.silverInk) }
        Text(
            remember(b, day) { facts("اتوماسیون‌ها: ${faNum(on)} روشن", day?.lineFa?.ifBlank { null }?.removePrefix("امروز: ")?.let { "امروز $it" }) },
            style = Divan.type.caption, color = c.textSecondary, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f),
        )
        DIcon(DivanIcon.NEXT, size = 14.dp, tint = c.textMuted)
    }
}

/** «تقویم اجراهای پیش رو»: every automation's next fourteen days, each day with its runs and their topics. */
@Composable
fun AutomationsCalendarScreen() {
    val nav = LocalNav.current
    val c = Divan.colors
    val from = remember { com.coinepro.hq.core.format.HqClock.now().toString().take(10) }
    val to = remember { com.coinepro.hq.core.format.HqClock.now().plus(14, java.time.temporal.ChronoUnit.DAYS).toString().take(10) }
    val q = rememberQuery("automations-calendar:$from", "automations", maxAgeMs = 60_000) { gated(HubFeature.AUTOMATIONS) { automationsCalendar(from, to) } }
    Page(onRefresh = { q.refresh() }, refreshing = q.state.refreshing) {
        item(key = "head") { PageHeader("تقویم اتوماسیون‌ها", eyebrow = "دو هفته‌ی پیش رو و موضوع هر روز") }
        val cal = q.data
        when {
            cal == null && q.error != null -> item(key = "err") { ErrorBlock(q.error, { q.refresh() }) }
            cal == null -> item(key = "sk") { Skeleton(Modifier.fillMaxWidth().height(240.dp), radius = 14.dp) }
            cal.days.all { it.items.isEmpty() } -> item(key = "empty") { Empty("در دو هفته‌ی پیش رو اجرایی نیست", icon = DivanIcon.PLANNER) }
            else -> for (d in cal.days.filter { it.items.isNotEmpty() }) {
                item(key = "d-${d.day}") {
                    HqCard(Modifier.fillMaxWidth(), padding = PaddingValues(vertical = 4.dp)) {
                        Text(jWeekday(d.day + "T12:00:00Z"), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, modifier = Modifier.padding(horizontal = 14.dp, vertical = 8.dp))
                        d.items.forEachIndexed { i, e ->
                            if (i > 0) HorizontalDivider(color = c.lineDivider)
                            Row(
                                Modifier.fillMaxWidth().clickable(role = Role.Button) { nav.go("automation/${e.ref}") }.padding(horizontal = 14.dp, vertical = 9.dp),
                                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
                            ) {
                                Text(jTime(e.at), style = Divan.type.caption, color = c.textSecondary)
                                Column(Modifier.weight(1f)) {
                                    Text(facts(e.titleFa, e.companyFa.ifBlank { null }), style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, maxLines = 1, overflow = TextOverflow.Ellipsis)
                                    Text(plain(e.topicFa ?: "موضوع روز اجرا انتخاب میشود"), style = Divan.type.micro, color = c.textMuted, maxLines = 1, overflow = TextOverflow.Ellipsis)
                                }
                                if (e.state == "skipped") Pill("رد", Tone.SILVER)
                                else if (e.state != "planned") Pill(lineRunStateFa(e.state), lineRunStateTone(e.state))
                            }
                        }
                    }
                }
            }
        }
    }
}
