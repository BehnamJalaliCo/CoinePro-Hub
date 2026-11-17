package com.coinepro.hq.ui.automation

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.countdownFa
import com.coinepro.hq.core.data.faHour
import com.coinepro.hq.core.data.faNum
import com.coinepro.hq.core.data.flowEffortFa
import com.coinepro.hq.core.data.flowKindFa
import com.coinepro.hq.core.data.hoursLineFa
import com.coinepro.hq.core.data.modelShort
import com.coinepro.hq.core.data.nextWhenFa
import com.coinepro.hq.core.data.usdShort
import com.coinepro.hq.core.format.HqClock
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.instant
import com.coinepro.hq.core.net.FlowDef
import com.coinepro.hq.core.net.FlowList
import com.coinepro.hq.core.net.Health
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.gated
import com.coinepro.hq.designsystem.CompanyMark
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqSwitch
import com.coinepro.hq.designsystem.IconBtn
import com.coinepro.hq.designsystem.MeterBar
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
import com.coinepro.hq.ui.publish.Every
import com.coinepro.hq.ui.publish.OnPublication
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v29.plain
import com.coinepro.hq.ui.v29.served
import java.util.UUID

// ⟨1.39⟩ Contract §61 and D6: the automations as data. The board (company → page → each automation's card: what it makes, its hours,
// model and effort, the switch, the next one with its countdown, today's and the month's cost against its warning line, its health), the
// home's card, and the queries the flow's page shares.

internal val FLOW_TAGS = arrayOf("flows", "automations")

@Composable
internal fun rememberFlows() = rememberQuery("flows", *FLOW_TAGS, maxAgeMs = 15_000) { gated(HubFeature.FLOWS) { flows() } }

@Composable
internal fun rememberFlowDef(ref: String) = rememberQuery("flowdef:$ref", *FLOW_TAGS, maxAgeMs = 10_000) { gated(HubFeature.FLOWS) { flowDef(ref) } }

@Composable
internal fun rememberFlowOptions() = rememberQuery("flow-options", *FLOW_TAGS, maxAgeMs = 300_000) { gated(HubFeature.FLOWS) { flowOptions() } }

/** A health key in the owner's words. */
fun healthKeyFa(k: String): String = when (k) {
    "n8n" -> "ساعت هاب"; "ighub" -> "IG-Hub"; "workshop" -> "کارگاه"; "helpers_browser" -> "ChatGPT"; "aistudio" -> "AI Studio"; "publish_path" -> "مسیر انتشار"
    else -> k
}

@Composable
private fun healthColor(state: String): Color = Divan.colors.let { c -> when (state) { "ok" -> c.positive; "warn" -> c.warning; else -> c.negative } }

/** The road's health as dots; the first that is not well, said in its line. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun HealthDots(h: List<Health>, withNote: Boolean = true) {
    val c = Divan.colors
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        FlowRow(Modifier.testTag("flow-health"), horizontalArrangement = Arrangement.spacedBy(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            for (x in h) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(5.dp)) {
                Box(Modifier.size(9.dp).clip(CircleShape).background(healthColor(x.state)))
                Text(plain(healthKeyFa(x.key)), style = Divan.type.micro, color = c.textSecondary)
            }
        }
        if (withNote) h.firstOrNull { it.state != "ok" }?.let { Text(plain(it.noteFa), style = Divan.type.micro, color = if (it.state == "down") c.negative else c.warning) }
    }
}

// ----------------------------------------------------------------------------------------------------- the home card --
/** «اتوماسیون‌ها» on the home: on and off, the road's health, the next build, what is building, today's and the month's cost. */
@Composable
fun AutomationsCard(modifier: Modifier = Modifier) {
    if (!served(HubFeature.FLOWS)) return
    val q = rememberFlows()
    val l = q.data ?: return
    val nav = LocalNav.current
    val c = Divan.colors
    Every(60_000) { q.refresh() }
    val now = HqClock.millis()
    val on = l.items.count { it.state == "on" }
    val building = l.items.count { f -> f.next?.let { n -> (instant(n.buildAt)?.toEpochMilli() ?: Long.MAX_VALUE) <= now && (instant(n.publishAt)?.toEpochMilli() ?: 0) > now } == true }
    val next = l.items.filter { it.state == "on" }.mapNotNull { f -> f.next?.let { n -> f to n } }
        .filter { (instant(it.second.buildAt)?.toEpochMilli() ?: 0) > now }.minByOrNull { instant(it.second.buildAt)?.toEpochMilli() ?: Long.MAX_VALUE }
    val month = l.items.sumOf { it.monthCostUsd }
    val alerts = l.items.sumOf { it.alertsOpen }
    val shape = RoundedCornerShape(22.dp)
    Column(
        modifier.fillMaxWidth().testTag("automations-card").clip(shape).background(c.card).border(1.dp, c.lineHairline, shape)
            .clickable(role = Role.Button, onClickLabel = "اتوماسیون‌ها") { nav.go("automations") }.padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            DIcon(DivanIcon.SETTINGS, size = 20.dp, tint = c.goldInk)
            Text("اتوماسیون‌ها", style = Divan.type.h3, modifier = Modifier.weight(1f))
            Text("${faNum(on)} روشن · ${faNum(l.items.size - on)} خاموش", style = Divan.type.micro, color = c.textSecondary)
        }
        if (l.health.isNotEmpty()) HealthDots(l.health)
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Column(Modifier.weight(1f)) {
                Text("ساخت بعدی", style = Divan.type.micro, color = c.textMuted)
                Text(next?.let { (f, n) -> "${f.titleFa} · از ${faHour(n.buildAt)}" } ?: "امروز ساختی نمانده", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
            if (building > 0) Pill("${faNum(building)} در کار", Tone.LAPIS, dot = true, live = true)
        }
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("هزینه‌ی امروز", style = Divan.type.micro, color = c.textSecondary, modifier = Modifier.weight(1f))
                Text(plain(usdShort(l.today.costUsd)), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold))
            }
            Text(plain("این ماه ${usdShort(month)} · " + if (alerts > 0) "${faNum(alerts)} هشدار باز" else "هیچ هشداری باز نیست"), style = Divan.type.micro, color = c.textMuted)
        }
    }
}

// ---------------------------------------------------------------------------------------------------------- the board --
/** The board of §61: on a hub before it, §59.10's. */
@Composable
fun FlowsBoardScreen() {
    if (!served(HubFeature.FLOWS)) { AutomationsBoardScreen(); return }
    val c = Divan.colors
    val nav = LocalNav.current
    val q = rememberFlows()
    var company by rememberSaveable { mutableStateOf<String?>(null) }
    val more = served(HubFeature.FLOWS_MORE)
    val old = served(HubFeature.AUTOMATIONS)
    OnPublication { q.refresh() }
    Every(60_000) { q.refresh() }
    Page(onRefresh = { q.refresh() }, refreshing = q.state.refreshing) {
        item(key = "head") {
            PageHeader("اتوماسیون‌ها", eyebrow = "هر چه خودش میسازد و منتشر میکند؛ هر کدام با یک لمس", actions = {
                IconBtn(DivanIcon.PLANNER, "تقویم اجراها", { nav.go("publish/calendar") })
                IconBtn(DivanIcon.ADD, "اتوماسیون تازه", { nav.go("automations/new") }, active = true)
            })
        }
        val l = q.data
        when {
            l == null && q.error != null -> item(key = "error") { ErrorBlock(q.error, { q.refresh() }) }
            l == null -> item(key = "sk") { Column(verticalArrangement = Arrangement.spacedBy(12.dp)) { repeat(3) { Skeleton(Modifier.fillMaxWidth().height(150.dp), radius = 22.dp) } } }
            else -> {
                item(key = "today") {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Count(l.today.runs, "اجرای امروز")
                        Count(l.today.published, "منتشر شد")
                        Column(Modifier.weight(1f).clip(RoundedCornerShape(14.dp)).background(c.tile).padding(horizontal = 10.dp, vertical = 8.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                            Text(plain(usdShort(l.today.costUsd)), style = Divan.type.h2.copy(fontWeight = FontWeight.Bold), maxLines = 1)
                            Text("هزینه‌ی امروز", style = Divan.type.micro, color = c.textSecondary)
                        }
                    }
                }
                if (l.health.isNotEmpty()) item(key = "health") {
                    Box(Modifier.fillMaxWidth().clip(RoundedCornerShape(18.dp)).background(c.card).padding(horizontal = 14.dp, vertical = 12.dp)) { HealthDots(l.health) }
                }
                val companies = l.items.map { it.company to it.companyFa }.distinct()
                if (companies.size > 1) item(key = "chips") {
                    ScrollRow(spacing = 8.dp) {
                        FilterChip("همه", company == null, { company = null }, count = l.items.size)
                        for ((co, fa) in companies) FilterChip(fa.ifBlank { co }, company == co, { company = if (company == co) null else co })
                    }
                }
                val shown = l.items.filter { company == null || it.company == company }
                val (live, off) = shown.partition { it.state != "off" }
                if (shown.isEmpty()) item(key = "empty") { Empty("اتوماسیونی نیست", icon = DivanIcon.SETTINGS, body = "با «اتوماسیون تازه» یکی بساز.") }
                for ((co, list) in live.groupBy { it.company }) {
                    val first = list.first()
                    item(key = "co-$co") {
                        Row(Modifier.padding(top = 6.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            CompanyMark(co, height = 16.dp)
                            Text(plain(first.companyFa.ifBlank { co }), style = Divan.type.h3)
                            Text(plain(list.map { it.account }.filter { it.isNotBlank() }.distinct().joinToString(" · ") { "@$it" }), style = Divan.type.micro, color = c.textMuted, maxLines = 1, overflow = TextOverflow.Ellipsis)
                        }
                    }
                    items(list, key = { "f-${it.ref}" }) { f -> FlowCard(f) { q.refresh() } }
                }
                if (off.isNotEmpty()) {
                    item(key = "off") { Text("خاموش · ${faNum(off.size)}", style = Divan.type.h3, color = c.textMuted, modifier = Modifier.padding(top = 6.dp)) }
                    items(off, key = { "off-${it.ref}" }) { f -> FlowCard(f, compact = true) { q.refresh() } }
                }
                if (more) item(key = "week") {
                    Row(
                        Modifier.fillMaxWidth().clip(RoundedCornerShape(18.dp)).border(1.dp, c.lineHairline, RoundedCornerShape(18.dp))
                            .clickable(role = Role.Button, onClickLabel = "خلاصه‌ی هفته") { nav.go("automations/week") }.padding(14.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text("خلاصه‌ی این هفته", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), modifier = Modifier.weight(1f))
                        DIcon(DivanIcon.NEXT, size = 14.dp, tint = c.textMuted)
                    }
                }
                if (old) item(key = "others") {
                    Row(
                        Modifier.fillMaxWidth().clip(RoundedCornerShape(18.dp)).clickable(role = Role.Button, onClickLabel = "دیگر خودکارها") { nav.go("automations/all") }.padding(vertical = 10.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text("روال‌ها، قاعده‌ها و دیگر خودکارها", style = Divan.type.small, color = c.textSecondary, modifier = Modifier.weight(1f))
                        DIcon(DivanIcon.NEXT, size = 14.dp, tint = c.textMuted)
                    }
                }
            }
        }
    }
}

/** One automation on the board. [compact]: an off one, its title and switch only. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun FlowCard(f: FlowDef, compact: Boolean = false, onChanged: () -> Unit) {
    val c = Divan.colors
    val nav = LocalNav.current
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val act = rememberAction()
    val now = HqClock.millis()
    val shape = RoundedCornerShape(22.dp)
    Column(
        Modifier.fillMaxWidth().testTag("flow-card").clip(shape).background(c.card).border(1.dp, c.lineHairline, shape)
            .clickable(role = Role.Button, onClickLabel = "صفحه‌ی این اتوماسیون") { nav.go("automation/${f.ref}") }
            .then(if (compact) Modifier.padding(horizontal = 14.dp, vertical = 10.dp) else Modifier.padding(14.dp)),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            if (!compact) Box(Modifier.size(10.dp).clip(CircleShape).background(healthColor(f.health.state)))
            Text(plain(f.titleFa), style = if (compact) Divan.type.small else Divan.type.bodyStrong, color = if (compact) c.textSecondary else c.textPrimary, modifier = Modifier.weight(1f), maxLines = 2, overflow = TextOverflow.Ellipsis)
            HqSwitch(f.state == "on", { on ->
                act.run { env.api.flowDefState(f.ref, on, UUID.randomUUID().toString()); env.cache.invalidate(*FLOW_TAGS); toasts.ok(if (on) "روشن شد" else "خاموش شد"); onChanged() }
            }, label = if (f.state == "on") "خاموش کن" else "روشن کن", enabled = !act.busy)
        }
        if (compact) return@Column
        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Tag(if (f.account.isBlank()) "منتشر نمیشود" else "${flowKindFa(f.kind)} · @${f.account}")
            Tag(hoursLineFa(f))
            Tag("${modelShort(f.model, f.modelFa)} · ${flowEffortFa(f.effort)}")
            if (f.cycle.size > 1) Tag("چرخه‌ی ${faNum(f.cycle.size)} نوع")
        }
        val n = f.next
        if (f.state == "paused") Text("مکث" + (f.pausedUntil?.let { " تا ${nextWhenFa(it, now)}" } ?: ""), style = Divan.type.small, color = c.warning)
        else if (n != null) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            val building = (instant(n.buildAt)?.toEpochMilli() ?: Long.MAX_VALUE) <= now
            Text(
                plain(if (building) "در کارگاه ساخته میشود · انتشار ${nextWhenFa(n.publishAt, now)}" else "ساخت ${nextWhenFa(n.buildAt, now)} · انتشار ${faHour(n.publishAt)}" + (n.kindFa?.let { " · $it" } ?: "")),
                style = Divan.type.small, color = c.textSecondary, modifier = Modifier.weight(1f), maxLines = 2,
            )
            if (building) Pill("در کار", Tone.LAPIS, dot = true, live = true)
            else countdownFa(n.buildAt, now)?.let { Pill(it, Tone.NEUTRAL, icon = DivanIcon.TIME) }
        }
        if (f.health.state != "ok") Text(plain(f.health.noteFa), style = Divan.type.micro, color = if (f.health.state == "down") c.negative else c.warning)
        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Row {
                Text(plain("امروز ${usdShort(f.today.costUsd)} · ماه ${usdShort(f.monthCostUsd)}"), style = Divan.type.micro, color = c.textSecondary, modifier = Modifier.weight(1f))
                Text(plain("هشدار از ${usdShort(f.budget.usdCap)}"), style = Divan.type.micro, color = c.textMuted)
            }
            val share = if (f.budget.usdCap > 0) (f.today.costUsd / f.budget.usdCap) else 0.0
            MeterBar(share.coerceIn(0.0, 1.0) * 100, color = if (share >= 1) c.warning else c.goldFill, height = 5.dp)
        }
    }
}

@Composable
internal fun Tag(text: String) {
    val c = Divan.colors
    Box(Modifier.clip(RoundedCornerShape(9.dp)).background(c.tile).padding(horizontal = 9.dp, vertical = 4.dp)) {
        Text(plain(text), style = Divan.type.micro, color = c.textSecondary, maxLines = 1)
    }
}
