package com.coinepro.hq.ui.automation

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.alertKindFa
import com.coinepro.hq.core.data.alertTone
import com.coinepro.hq.core.data.cardsByDay
import com.coinepro.hq.core.data.countdownFa
import com.coinepro.hq.core.data.dayHeadFa
import com.coinepro.hq.core.data.faHour
import com.coinepro.hq.core.data.faNum
import com.coinepro.hq.core.data.healthFa
import com.coinepro.hq.core.data.jDayFa
import com.coinepro.hq.core.data.nextWhenFa
import com.coinepro.hq.core.data.rollbackBody
import com.coinepro.hq.core.data.tehranDate
import com.coinepro.hq.core.data.usdShort
import com.coinepro.hq.core.format.HqClock
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.instant
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.FlowDef
import com.coinepro.hq.core.net.FlowRunDay
import com.coinepro.hq.core.net.FlowVersion
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
import com.coinepro.hq.ui.publish.Count
import com.coinepro.hq.ui.publish.OnPublication
import com.coinepro.hq.ui.publish.PUB_TAGS
import com.coinepro.hq.ui.publish.PubRow
import com.coinepro.hq.ui.publish.PubTile
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v29.plain
import com.coinepro.hq.ui.v29.served
import java.time.LocalDate
import java.time.ZoneId
import java.util.UUID

// ⟨1.39⟩ Contract §61.3 and D6: one automation's page, in six tabs: «نمای کلی» (the next one, run now, pause, skip; today's map and
// steps from §59.7.1), «تنظیمات» (FlowEdit.kt), «اجراها», «خروجی‌ها» (its publications, §60.2), «نسخه‌ها» (with «برگشت به این
// نسخه») and «سلامت» (and its alerts). The parts of P2 say so on a hub without them.

internal val FLOW_TABS = listOf("overview" to "نمای کلی", "settings" to "تنظیمات", "runs" to "اجراها", "outputs" to "خروجی‌ها", "versions" to "نسخه‌ها", "health" to "سلامت")

/** `automation/{ref}`: a §61 automation (`AF-…`) here; the §59.7 kinds keep their page. */
@Composable
fun AutomationScreen(ref: String) {
    if (ref.startsWith("AF-")) FlowDefScreen(ref) else FlowScreen(ref)
}

@Composable
fun FlowDefScreen(ref: String, tab0: String = "overview") {
    val c = Divan.colors
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val q = rememberFlowDef(ref)
    var tab by rememberSaveable(ref) { mutableStateOf(tab0) }
    val act = rememberAction()
    OnPublication { q.refresh() }
    val f = q.data
    val has = served(HubFeature.FLOWS)
    val more = served(HubFeature.FLOWS_MORE)
    // the editor's state lives with the page, so its save bar stays at the page's foot
    val options = rememberFlowOptions().data ?: com.coinepro.hq.core.net.FlowOptions()
    val base = remember(f?.ref, f?.version) { f?.let { com.coinepro.hq.core.data.flowDraftOf(it) } }
    var draft by remember(f?.ref, f?.version) { mutableStateOf(base) }
    var errors by remember(f?.ref, f?.version) { mutableStateOf<Map<String, String>>(emptyMap()) }
    val saved: (FlowDef) -> Unit = { out -> q.set(out); env.cache.invalidate(*FLOW_TAGS) }
    Box(Modifier.fillMaxSize()) {
    Page(onRefresh = { q.refresh() }, refreshing = q.state.refreshing) {
        item(key = "head") {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Box(Modifier.weight(1f)) {
                    PageHeader(f?.titleFa ?: "اتوماسیون", eyebrow = f?.let { listOfNotNull(it.account.ifBlank { null }?.let { a -> "@$a" }, it.companyFa.ifBlank { null }, "نسخه‌ی ${faNum(it.version)}").joinToString(" · ") })
                }
                if (f != null) HqSwitch(f.state == "on", { on ->
                    act.run { val out = env.api.flowDefState(ref, on, UUID.randomUUID().toString()); q.set(out); env.cache.invalidate(*FLOW_TAGS); toasts.ok(if (on) "روشن شد" else "خاموش شد") }
                }, label = if (f.state == "on") "خاموش کن" else "روشن کن", enabled = !act.busy)
            }
        }
        item(key = "tabs") {
            ScrollRow(Modifier.testTag("flow-tabs"), spacing = 18.dp) {
                for ((k, l) in FLOW_TABS) {
                    val on = k == tab
                    Column(Modifier.clickable(role = Role.Tab, onClickLabel = l) { tab = k }.padding(vertical = 6.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                        Text(l, style = Divan.type.small.copy(fontWeight = if (on) FontWeight.Bold else FontWeight.Normal), color = if (on) c.textPrimary else c.textSecondary)
                        Box(Modifier.padding(top = 6.dp).width(28.dp).height(2.dp).background(if (on) c.goldFill else androidx.compose.ui.graphics.Color.Transparent))
                    }
                }
            }
        }
        when {
            !has -> item(key = "old") { Empty("این بخش با به‌روزرسانی بعدی هاب می‌آید", icon = DivanIcon.SETTINGS) }
            f == null && q.error != null -> item(key = "error") { ErrorBlock(q.error, { q.refresh() }) }
            f == null -> item(key = "sk") { Skeleton(Modifier.fillMaxWidth().height(320.dp), radius = 20.dp) }
            else -> when (tab) {
                "settings" -> {
                    item(key = "editor") {
                        val d = draft ?: return@item
                        FlowEditorBody(f, options, d, { nd -> draft = nd; if (errors.isNotEmpty()) errors = com.coinepro.hq.core.data.checkDraft(nd, f.kind, options).associate { e -> e.field to e.messageFa } }, errors)
                    }
                    item(key = "room") { Spacer(Modifier.height(72.dp)) }
                }
                "runs" -> runsTab(f, more)
                "outputs" -> item(key = "outputs") { OutputsTab(f) }
                "versions" -> item(key = "versions") { VersionsTab(f, more) { q.set(it); env.cache.invalidate(*FLOW_TAGS) } }
                "health" -> item(key = "health") { HealthTab(f, more) }
                else -> overviewTab(f) { q.set(it); env.cache.invalidate(*FLOW_TAGS) }
            }
        }
    }
    val d = draft
    if (tab == "settings" && f != null && base != null && d != null) Box(Modifier.align(Alignment.BottomCenter)) {
        SaveBar(f, base, d, options, { errors = it }, saved)
    }
    }
}

// ------------------------------------------------------------------------------------------------------------ overview --
private fun LazyListScope.overviewTab(f: FlowDef, onChanged: (FlowDef) -> Unit) {
    item(key = "next") { NextCard(f, onChanged) }
    item(key = "map") { TodayMap(f) }
    item(key = "out") { TodayOutput(f) }
}

@Composable
private fun RowScope.Quick(icon: DivanIcon, label: String, enabled: Boolean = true, onClick: () -> Unit) {
    val c = Divan.colors
    Column(
        Modifier.weight(1f).clip(RoundedCornerShape(16.dp)).background(c.tile)
            .clickable(enabled = enabled, role = Role.Button, onClickLabel = label) { onClick() }.padding(vertical = 10.dp),
        horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        DIcon(icon, size = 20.dp, tint = if (enabled) c.goldInk else c.textMuted)
        Text(label, style = Divan.type.micro, color = if (enabled) c.textPrimary else c.textMuted, maxLines = 1)
    }
}

@Composable
private fun NextCard(f: FlowDef, onChanged: (FlowDef) -> Unit) {
    val c = Divan.colors
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val act = rememberAction()
    var pausing by rememberSaveable(f.ref) { mutableStateOf(false) }
    val now = HqClock.millis()
    val n = f.next
    val tehran = ZoneId.of(com.coinepro.hq.core.format.OWNER_TZ)
    HqCard(Modifier.fillMaxWidth().testTag("flow-next")) {
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("انتشار بعدی", style = Divan.type.micro, color = c.textMuted, modifier = Modifier.weight(1f))
                Pill(healthFa(f.health.state), com.coinepro.hq.core.data.healthTone(f.health.state), dot = true)
            }
            when {
                f.state == "off" -> Text("خاموش است؛ با کلید بالا روشن میشود.", style = Divan.type.bodyStrong, color = c.textSecondary)
                f.state == "paused" -> Text("مکث" + (f.pausedUntil?.let { " تا ${nextWhenFa(it, now)}" } ?: ""), style = Divan.type.bodyStrong, color = c.warning)
                n == null -> Text(if (f.account.isBlank()) "نمونه است؛ منتشر نمیشود" else "برنامه‌ای پیدا نشد", style = Divan.type.bodyStrong, color = c.textSecondary)
                else -> {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(nextWhenFa(n.publishAt, now), style = Divan.type.h2, modifier = Modifier.weight(1f))
                        countdownFa(n.publishAt, now)?.let { Pill(it, Tone.GOLD, icon = DivanIcon.TIME) }
                    }
                    val building = (instant(n.buildAt)?.toEpochMilli() ?: Long.MAX_VALUE) <= now
                    Text(plain(if (building) "در کارگاه ساخته میشود" + (n.kindFa?.let { " · $it" } ?: "") else "ساخت ${nextWhenFa(n.buildAt, now)}" + (n.kindFa?.let { " · نوع روز: $it" } ?: "")), style = Divan.type.small, color = c.textSecondary)
                }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Quick(DivanIcon.RESUME, "همین حالا بساز", enabled = !act.busy && f.account.isNotBlank() || f.state == "off") {
                    act.run(onError = { e -> toasts.info(e.messageFa) }) { env.api.runFlowDefNow(f.ref, null, UUID.randomUUID().toString()); toasts.ok("ساخت شروع شد"); env.cache.invalidate(*FLOW_TAGS, *PUB_TAGS) }
                }
                if (f.state == "paused") Quick(DivanIcon.RESUME, "ادامه") {
                    act.run { onChanged(env.api.flowDefState(f.ref, true, UUID.randomUUID().toString())); toasts.ok("دوباره روشن شد") }
                } else Quick(DivanIcon.PAUSE, "مکث تا…", enabled = f.state == "on") { pausing = !pausing }
                Quick(DivanIcon.CLOSE, "این نوبت نه", enabled = n != null && f.state == "on") {
                    val day = n?.publishAt?.let { instant(it)?.atZone(tehran)?.toLocalDate()?.toString() } ?: return@Quick
                    act.run { onChanged(env.api.skipFlowDay(f.ref, day, true, UUID.randomUUID().toString())); toasts.ok("این نوبت رد شد") }
                }
            }
            if (pausing) Row(Modifier.testTag("pause-choices"), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                val today = HqClock.now().atZone(tehran).toLocalDate()
                for ((d, l) in listOf(1L to "تا فردا", 3L to "سه روز", 7L to "یک هفته")) HqButton(l, {
                    act.run { onChanged(env.api.pauseFlowDef(f.ref, today.plusDays(d).toString(), UUID.randomUUID().toString())); pausing = false; toasts.ok("مکث شد") }
                }, Modifier.weight(1f), variant = BtnVariant.SECONDARY, size = BtnSize.SM)
            }
        }
    }
}

/** Today's map and steps, from the same automation's §59.7.1 page (`legacy_ref`); nothing when the hub has none for it. */
@Composable
private fun TodayMap(f: FlowDef) {
    val c = Divan.colors
    val nav = LocalNav.current
    val legacy = f.legacyRef.ifBlank { return }
    val q = rememberFlow(legacy)
    val runs = rememberQuery("flow-runs:$legacy", "automations", maxAgeMs = 15_000) { gated(HubFeature.AUTOMATIONS) { flowRuns(legacy) } }
    val g = q.data?.graph ?: return
    val day = rememberMapDay(legacy, runs.data?.items.orEmpty()) { runs.refresh() }
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("نقشه‌ی امروز", style = Divan.type.h3, modifier = Modifier.weight(1f).semantics { heading() })
            HqButton("نقشه‌ی کامل", { nav.go("automation/$legacy/map") }, variant = BtnVariant.TEXT, size = BtnSize.SM)
        }
        FlowCanvas(g, day.states, Modifier.fillMaxWidth().height(300.dp), focusOn = day.ref, onNode = { nav.go("automation/$legacy/map") }, onFull = { nav.go("automation/$legacy/map") })
        q.data?.let { fa -> if (fa.steps.isNotEmpty()) com.coinepro.hq.ui.playbook.StepsCard(fa.steps, "اجرای امروز", "${faNum(fa.steps.size)} قدم، به همین ترتیب", "flowdef-steps", legacy, states = day.states) }
    }
}

/** Today's output of this automation, in the archive. */
@Composable
private fun TodayOutput(f: FlowDef) {
    if (!served(HubFeature.PUBLICATIONS)) return
    val q = rememberQuery("pub-auto:${f.ref}:1", *PUB_TAGS, maxAgeMs = 30_000) { gated(HubFeature.PUBLICATIONS) { publications(automation = f.ref, limit = 1) } }
    val k = q.data?.items?.firstOrNull() ?: return
    PubRow(k, sub = "آخرین خروجی · ${tehranDate(k.at)?.let { jDayFa(it) } ?: ""}")
}

// ---------------------------------------------------------------------------------------------------------------- runs --
private fun LazyListScope.runsTab(f: FlowDef, more: Boolean) {
    if (!more) { item(key = "runs-old") { P2Later() }; return }
    item(key = "runs") { RunsTab(f) }
}

@Composable
private fun P2Later() = Empty("این بخش با به‌روزرسانی بعدی هاب می‌آید", icon = DivanIcon.SETTINGS, body = "تنظیمات، کلید و خروجی‌ها همین حالا کار میکنند.")

@Composable
private fun RunsTab(f: FlowDef) {
    val c = Divan.colors
    val nav = LocalNav.current
    var filter by rememberSaveable(f.ref) { mutableStateOf<String?>(null) }
    val q = rememberQuery("flow-days:${f.ref}", *FLOW_TAGS, maxAgeMs = 20_000) { gated(HubFeature.FLOWS_MORE) { flowRunDays(f.ref) } }
    val list = q.data?.items
    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        when {
            list == null && q.error != null -> ErrorBlock(q.error, { q.refresh() })
            list == null -> Skeleton(Modifier.fillMaxWidth().height(300.dp), radius = 18.dp)
            list.isEmpty() -> Empty("هنوز اجرایی نیست", icon = DivanIcon.TIME, body = "اولین اجرا: ${f.next?.buildAt?.let { nextWhenFa(it, HqClock.millis()) } ?: "—"}")
            else -> {
                val ran = list.filter { it.state != "skipped" }
                val ok = ran.count { it.state == "done" }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Count(ok, "موفق از ${faNum(ran.size)}")
                    Column(Modifier.weight(1f).clip(RoundedCornerShape(14.dp)).background(c.tile).padding(horizontal = 10.dp, vertical = 8.dp)) {
                        Text(plain(usdShort(if (ran.isEmpty()) 0.0 else ran.sumOf { it.costUsd } / ran.size)), style = Divan.type.h2.copy(fontWeight = FontWeight.Bold))
                        Text("میانگین هر روز", style = Divan.type.micro, color = c.textSecondary)
                    }
                    val mins = ran.mapNotNull { r -> val a = instant(r.startedAt); val b = instant(r.endedAt); if (a != null && b != null) (b.toEpochMilli() - a.toEpochMilli()) / 60_000 else null }.filter { it in 1..600 }
                    Count(if (mins.isEmpty()) 0 else mins.average().toInt(), "دقیقه‌ی ساخت")
                }
                CostBars(list.reversed(), f.budget.usdCap)
                ScrollRow(spacing = 8.dp) {
                    for ((s, l) in listOf(null to "همه", "done" to "منتشرشده", "failed" to "ناموفق", "skipped" to "ردشده")) FilterChip(l, filter == s, { filter = if (filter == s) null else s }, count = if (s == null) null else list.count { it.state == s }.takeIf { it > 0 })
                }
                HqCard(Modifier.fillMaxWidth()) {
                    for ((i, r) in list.filter { filter == null || it.state == filter }.withIndex()) {
                        if (i > 0) Box(Modifier.fillMaxWidth().height(1.dp).background(c.lineHairline))
                        RunLine(r) { nav.go("flow-run/${r.run}") }
                    }
                }
            }
        }
        Text("هر ردیف: یک لمس به خط زمان همان روز. «خروجی‌ها» همه‌ی انتشارهای این اتوماسیون را مثل بایگانی نشان میدهد.", style = Divan.type.micro, color = c.textMuted)
    }
}

@Composable
private fun CostBars(days: List<FlowRunDay>, cap: Double) {
    val c = Divan.colors
    val top = maxOf(cap, days.maxOfOrNull { it.costUsd } ?: 0.0, 0.01)
    HqCard(Modifier.fillMaxWidth().testTag("cost-bars")) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("هزینه‌ی هر روز", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), modifier = Modifier.weight(1f))
            Text(plain("هشدار از ${usdShort(cap)}"), style = Divan.type.micro, color = c.textMuted)
        }
        Row(Modifier.fillMaxWidth().height(64.dp).padding(top = 8.dp), horizontalArrangement = Arrangement.spacedBy(4.dp), verticalAlignment = Alignment.Bottom) {
            for (d in days.takeLast(14)) Box(Modifier.weight(1f).fillMaxHeight((d.costUsd / top).toFloat().coerceIn(0.03f, 1f)).clip(RoundedCornerShape(topStart = 3.dp, topEnd = 3.dp))
                .background(when { d.state == "failed" -> c.negative; d.state == "skipped" -> c.raised; d.costUsd > cap -> c.warning; else -> c.goldFill }))
        }
    }
}

@Composable
private fun RunLine(r: FlowRunDay, onClick: () -> Unit) {
    val c = Divan.colors
    val k = r.publications.firstOrNull()
    val today = HqClock.now().atZone(ZoneId.of(com.coinepro.hq.core.format.OWNER_TZ)).toLocalDate()
    // ⟨1.3.1⟩ a run without its day (the hub's `day: null`) is placed by its start
    val day = r.day?.let { runCatching { LocalDate.parse(it) }.getOrNull() } ?: tehranDate(r.startedAt)
    val dayFa = day?.let { dayHeadFa(it, today) }
    Row(Modifier.fillMaxWidth().testTag("run-line").clickable(role = Role.Button, onClickLabel = "خط زمان این روز") { onClick() }.padding(vertical = 10.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        if (k != null) com.coinepro.hq.ui.publish.PubCover(k.account, k.titleFa, k.thumbFileId, Modifier.size(width = 40.dp, height = 56.dp))
        else com.coinepro.hq.ui.publish.DashedFrame(Modifier.size(width = 40.dp, height = 56.dp)) { Text("—", style = Divan.type.caption, color = c.textMuted) }
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(plain(r.topicFa ?: dayFa ?: "—"), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text(plain(listOfNotNull(if (r.topicFa != null) dayFa else null, r.noteFa.ifBlank { null }).joinToString(" · ")), style = Divan.type.micro, color = if (r.state == "failed") c.negative else c.textMuted, maxLines = 2)
        }
        Column(horizontalAlignment = Alignment.End, verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Pill(when (r.state) { "done" -> "منتشر شد"; "skipped" -> "رد شد"; "failed" -> "ناموفق"; "running" -> "در کار"; else -> r.state },
                when (r.state) { "done" -> Tone.POS; "failed" -> Tone.NEG; "running" -> Tone.LAPIS; else -> Tone.NEUTRAL })
            Text(plain(usdShort(r.costUsd)), style = Divan.type.micro, color = c.textSecondary)
        }
    }
}

// ------------------------------------------------------------------------------------------------------------- outputs --
@Composable
private fun OutputsTab(f: FlowDef) {
    val c = Divan.colors
    val q = rememberQuery("pub-auto:${f.ref}", *PUB_TAGS, maxAgeMs = 30_000) { gated(HubFeature.PUBLICATIONS) { publications(automation = f.ref, limit = 60) } }
    val today = HqClock.now().atZone(ZoneId.of(com.coinepro.hq.core.format.OWNER_TZ)).toLocalDate()
    val page = q.data
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        when {
            !served(HubFeature.PUBLICATIONS) -> P2Later()
            page == null && q.error != null -> ErrorBlock(q.error, { q.refresh() })
            page == null -> Skeleton(Modifier.fillMaxWidth().height(300.dp), radius = 16.dp)
            page.items.isEmpty() -> Empty("هنوز چیزی منتشر نکرده", icon = DivanIcon.SEND)
            else -> for ((d, cards) in cardsByDay(page.items)) {
                Text(dayHeadFa(d, today), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
                for (row in cards.chunked(3)) Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    for (k in row) PubTile(k, Modifier.weight(1f))
                    repeat(3 - row.size) { Spacer(Modifier.weight(1f)) }
                }
            }
        }
    }
}

// ------------------------------------------------------------------------------------------------------------ versions --
@Composable
private fun VersionsTab(f: FlowDef, more: Boolean, onChanged: (FlowDef) -> Unit) {
    val c = Divan.colors
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val act = rememberAction()
    if (!more) { P2Later(); return }
    val q = rememberQuery("flow-versions:${f.ref}:${f.version}", *FLOW_TAGS, maxAgeMs = 30_000) { gated(HubFeature.FLOWS_MORE) { flowVersions(f.ref) } }
    val list = q.data
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        when {
            list == null && q.error != null -> ErrorBlock(q.error, { q.refresh() })
            list == null -> Skeleton(Modifier.fillMaxWidth().height(260.dp), radius = 16.dp)
            else -> HqCard(Modifier.fillMaxWidth().testTag("flow-versions")) {
                for ((i, v) in list.sortedByDescending { it.version }.withIndex()) {
                    if (i > 0) Box(Modifier.fillMaxWidth().height(1.dp).background(c.lineHairline))
                    VersionLine(v, current = v.version == f.version, busy = act.busy) {
                        act.run(onError = { e -> toasts.error(e.messageFa) }) {
                            val out = try { env.api.rollbackFlow(f.ref, v.version, UUID.randomUUID().toString()) } catch (e: ApiException) {
                                // a hub before P2's rollback: the earlier version's body saved again as an edit
                                val body = v.body ?: throw e
                                env.api.patchFlowDef(f.ref, f.version, rollbackBody(body))
                            }
                            onChanged(out); q.refresh(); toasts.ok("به نسخه‌ی ${faNum(v.version)} برگشت؛ نسخه‌ی ${faNum(out.version)} ثبت شد")
                        }
                    }
                }
            }
        }
        Text("برگشت یعنی همان نسخه دوباره، به‌عنوان نسخه‌ی تازه؛ هیچ نسخه‌ای پاک نمیشود.", style = Divan.type.micro, color = c.textMuted)
    }
}

@Composable
private fun VersionLine(v: FlowVersion, current: Boolean, busy: Boolean, onRollback: () -> Unit) {
    val c = Divan.colors
    Row(Modifier.fillMaxWidth().padding(vertical = 12.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        Box(Modifier.size(36.dp).clip(RoundedCornerShape(12.dp)).background(if (current) c.goldFill else c.tile), contentAlignment = Alignment.Center) {
            Text(faNum(v.version), style = Divan.type.bodyStrong, color = if (current) c.onGold else c.textPrimary)
        }
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(plain("${tehranDate(v.at)?.let { jDayFa(it) } ?: ""} · ${v.byFa}"), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), modifier = Modifier.weight(1f), maxLines = 1)
                if (current) Pill("در کار", Tone.GOLD)
            }
            for (ch in v.changes) Text(plain("${ch.labelFa}: ${ch.beforeFa} ← ${ch.afterFa}"), style = Divan.type.small)
            v.noteFa?.let { Text(plain("«$it»"), style = Divan.type.micro, color = c.textMuted) }
            if (!current && (v.body != null || v.version > 0)) HqButton("برگشت به این نسخه", onRollback, variant = BtnVariant.SECONDARY, size = BtnSize.SM, icon = DivanIcon.REFRESH, loading = busy)
        }
    }
}

// -------------------------------------------------------------------------------------------------------------- health --
@Composable
private fun HealthTab(f: FlowDef, more: Boolean) {
    val c = Divan.colors
    val q = rememberQuery("flow-health:${f.ref}", *FLOW_TAGS, maxAgeMs = 30_000) { if (more) gated(HubFeature.FLOWS_MORE) { flowHealth(f.ref) } else null }
    val h = q.data
    val now = HqClock.millis()
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("سلامت", style = Divan.type.h3, modifier = Modifier.weight(1f))
            Pill(healthFa(h?.state ?: f.health.state), com.coinepro.hq.core.data.healthTone(h?.state ?: f.health.state), dot = true)
        }
        Text(plain(h?.noteFa ?: f.health.noteFa), style = Divan.type.small, color = c.textSecondary)
        HqCard(Modifier.fillMaxWidth().testTag("flow-health-card")) {
            h?.lastRun?.let { r -> Line("آخرین اجرا", listOfNotNull(r.at?.let { a -> nextWhenFa(a, now) }, r.noteFa.ifBlank { null }).joinToString(" · ").ifBlank { "—" }) }
            h?.success30d?.let { if (it.all > 0) Line("موفق در ۳۰ روز", "${faNum(it.ok)} از ${faNum(it.all)}") }
            Line("هزینه", "امروز ${usdShort(h?.cost?.today ?: f.today.costUsd)} · ماه ${usdShort(h?.cost?.month ?: f.monthCostUsd)}")
            (h?.next ?: f.next)?.let { Line("اجرای بعدی", "ساخت ${nextWhenFa(it.buildAt, now)} · انتشار ${faHour(it.publishAt)}") }
        }
        val alerts = h?.alerts.orEmpty()
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("هشدارها", style = Divan.type.h3, modifier = Modifier.weight(1f))
            Text("باز: ${if (alerts.none { it.open } && f.alertsOpen == 0) "هیچ" else faNum(alerts.count { it.open }.coerceAtLeast(f.alertsOpen))}", style = Divan.type.micro, color = c.textMuted)
        }
        if (alerts.isNotEmpty()) HqCard(Modifier.fillMaxWidth()) {
            for ((i, a) in alerts.withIndex()) {
                if (i > 0) Box(Modifier.fillMaxWidth().height(1.dp).background(c.lineHairline))
                Row(Modifier.padding(vertical = 10.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    Pill(alertKindFa(a.kind), alertTone(a.kind))
                    Column(Modifier.weight(1f)) {
                        Text(plain(a.noteFa), style = Divan.type.small)
                        Text(plain("${tehranDate(a.openedAt)?.let { jDayFa(it) } ?: ""} ${faHour(a.openedAt)}" + if (a.open) " · باز" else " · بسته شد" + (a.closedFa?.let { "؛ $it" } ?: "")), style = Divan.type.micro, color = c.textMuted)
                    }
                }
            }
        }
        Text("هشدار را کد میسازد، نه مدل. فقط بحرانی واقعی به تو اعلان میشود؛ بقیه همین‌جا میماند.", style = Divan.type.micro, color = c.textMuted)
    }
}

@Composable
private fun Line(k: String, v: String) {
    val c = Divan.colors
    Row(Modifier.fillMaxWidth().padding(vertical = 8.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        Text(k, style = Divan.type.small, color = c.textSecondary)
        Spacer(Modifier.weight(1f))
        Text(plain(v), style = Divan.type.small, maxLines = 2, overflow = TextOverflow.Ellipsis)
    }
}

/** The month's estimate beside a warning line: «تخمین ماه ≈ $300». */
internal fun estimateFa(cap: Double): String = "تخمین ماه ≈ ${usdShort(cap * 30)}"

