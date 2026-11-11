package com.coinepro.hq.ui.v29

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import com.coinepro.hq.designsystem.Text
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
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.Refs
import com.coinepro.hq.core.data.SUGGESTION_SOURCE_FA
import com.coinepro.hq.core.data.connectionKindFa
import com.coinepro.hq.core.data.figureText
import com.coinepro.hq.core.data.kpiMove
import com.coinepro.hq.core.data.moveText
import com.coinepro.hq.core.data.numberText
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.format.jDate
import com.coinepro.hq.core.net.DayValue
import com.coinepro.hq.core.net.Home
import com.coinepro.hq.core.net.HomeGroup
import com.coinepro.hq.core.net.HomeOrder
import com.coinepro.hq.core.net.HomeProgress
import com.coinepro.hq.core.net.HomeSuggestion
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.Notification
import com.coinepro.hq.core.net.gated
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.Md
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.Radius
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.designsystem.springIn
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull

// Contract §29.13 ⟨1.11⟩: the owner's home. On top the three cards (the most effective suggestion, a good one, and a real move of a
// figure, before → after with its source); then the morning in five lines, each working group's KPI per company, the owner's orders with
// their state, and only critical items. Nothing technical: servers, the watch and findings live under «شرکت ← فنی».

/** The home as the hub serves it; null while it loads, or for good when this hub has no `/home` ([served] then says so). */
@Composable
fun rememberHome() = rememberQuery("home", "home", "orders", maxAgeMs = 30_000) { gated(HubFeature.HOME) { home() } }

/** The three cards: «پیشنهاد مؤثر», «پیشنهاد خوب», «پیشرفت واقعی» (each only when the hub has one). */
@Composable
fun HomeCardsBlock(h: Home) {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        h.cards.effective?.let { SuggestionCard(it, effective = true, modifier = Modifier.springIn(0)) }
        h.cards.good?.let { SuggestionCard(it, effective = false, modifier = Modifier.springIn(1)) }
        h.cards.progress?.let { ProgressCard(it, Modifier.springIn(2)) }
        if (h.cards.effective == null && h.cards.good == null && h.cards.progress == null) HqCard(Modifier.fillMaxWidth()) {
            Text("پیشنهاد تازه‌ای نیست", style = Divan.type.bodyStrong)
            Text(
                "شورا، کارگروه‌ها و مشاور هر روز پیشنهاد میدهند؛ مؤثرترین و یک پیشنهاد خوب این‌جا میاید. پیشرفت واقعی وقتی میاید که عدد یک اتصال جابه‌جا شود.",
                style = Divan.type.caption.copy(textAlign = TextAlign.Justify), color = Divan.colors.textMuted,
            )
        }
    }
}

/** A suggestion with «اجرا کن» (an order is made from it), «بعداً» and «نه» (a short reason the secretary keeps). */
@Composable
fun SuggestionCard(s: HomeSuggestion, effective: Boolean, modifier: Modifier = Modifier, openSession: Boolean = false) {
    val env = LocalEnv.current
    val nav = LocalNav.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val action = rememberAction()
    var asking by rememberSaveable(s.id) { mutableStateOf(false) }
    HqCard(modifier.fillMaxWidth(), tahrir = effective && s.state == "new") {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            IconTile(if (effective) DivanIcon.STAR else DivanIcon.LEARNING, if (effective) c.goldInk else c.lapis, if (effective) c.softGold else c.softLapis)
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(if (effective) "پیشنهاد مؤثر" else "پیشنهاد خوب", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = if (effective) c.goldInk else c.lapis)
                if (s.company.isNotBlank()) CoName(s.company)
            }
            SUGGESTION_SOURCE_FA[s.source]?.let { Text(it, style = Divan.type.micro, color = c.textMuted) }
        }
        Text(plain(s.titleFa), style = Divan.type.bodyStrong, color = c.textPrimary, modifier = Modifier.padding(top = 12.dp))
        if (s.whyFa.isNotBlank()) Para(s.whyFa, Modifier.padding(top = 6.dp))
        // The two facts side by side, always of one height (the taller one's), each arriving a beat after the other.
        if (s.impactFa.isNotBlank() || s.costFa.isNotBlank()) Row(Modifier.padding(top = 12.dp).height(IntrinsicSize.Min), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            if (s.impactFa.isNotBlank()) Fact("اثر", s.impactFa, DivanIcon.CHART, c.positive, Modifier.weight(1f).fillMaxHeight().springIn(0))
            if (s.costFa.isNotBlank()) Fact("هزینه", s.costFa, DivanIcon.BUDGET, c.goldInk, Modifier.weight(1f).fillMaxHeight().springIn(1))
        }
        Box(Modifier.padding(top = 12.dp)) {
            when (s.state) {
                "run" -> Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Pill("فرمانش داده شد", Tone.POS, icon = DivanIcon.SEAL)
                    s.orderRef?.let { ref -> HqButton(if (openSession) "جلسه‌اش" else "گزارش فرمان", { nav.go("session/$ref") }, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.NEXT) }
                }
                "no" -> Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Pill("نه گفتی", Tone.SILVER)
                    s.reasonFa?.takeIf { it.isNotBlank() }?.let { Text(plain("چرا: $it"), style = Divan.type.caption, color = c.textMuted) }
                }
                else -> Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    HqButton("اجرا کن", {
                        action.run {
                            val out = env.api.suggestion(s.id, "run")
                            env.cache.invalidate("home", "orders", "work", "office", "sessions")
                            val ref = (out?.get("order_ref") as? JsonPrimitive)?.contentOrNull
                            // ⟨1.17⟩ §35.5 in the office «اجرا کن» opens the order's session at once.
                            if (ref != null && openSession) nav.go("session/$ref")
                            else if (ref != null) toasts.ok("فرمانش داده شد؛ جلسه‌اش باز شد.", "جلسه") { nav.go("session/$ref") }
                            else toasts.ok("فرمانش داده شد.")
                        }
                    }, Modifier.weight(1f), variant = BtnVariant.PRIMARY, size = BtnSize.SM, icon = DivanIcon.SEND, loading = action.busy)
                    HqButton("بعداً", {
                        action.run { env.api.suggestion(s.id, "later"); env.cache.invalidate("home"); toasts.info("باشد؛ بعداً دوباره میاید.") }
                    }, size = BtnSize.SM)
                    HqButton("نه", { asking = true }, variant = BtnVariant.GHOST, size = BtnSize.SM)
                }
            }
        }
    }
    if (asking) NoReasonSheet(s, onDone = { asking = false })
}

/** One fact of a suggestion (its effect, its cost): an icon and a label in the fact's own colour above the plain sentence. */
@Composable
private fun Fact(label: String, value: String, icon: DivanIcon, tint: Color, modifier: Modifier) {
    val c = Divan.colors
    Column(
        modifier.clip(RoundedCornerShape(Radius.tile)).background(c.tile).padding(horizontal = 12.dp, vertical = 10.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            Box(Modifier.size(22.dp).clip(CircleShape).background(tint.copy(alpha = 0.12f)), contentAlignment = Alignment.Center) {
                DIcon(icon, size = 12.dp, tint = tint)
            }
            Text(label, style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = tint)
        }
        // Not justified: in a half-width tile a short sentence would stretch into gaps.
        Text(plain(value), style = Divan.type.small, color = c.textPrimary)
    }
}

/** «نه» with a short reason: the secretary remembers it and never offers the same again. */
@Composable
private fun NoReasonSheet(s: HomeSuggestion, onDone: () -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val action = rememberAction()
    var reason by rememberSaveable(s.id) { mutableStateOf("") }
    com.coinepro.hq.ui.v14.HqSheet(onDone, "چرا نه؟", sub = "یک جمله کافی است؛ منشی آن را یادش میماند و دیگر همین را پیشنهاد نمیکند.") {
        Text(plain(s.titleFa), style = Divan.type.small, color = c.textSecondary)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            for (q in NO_REASONS) FilterChip(q, reason == q, { reason = q })
        }
        HqTextField(reason, { reason = it }, "یا خودت بنویس", Modifier.fillMaxWidth(), singleLine = false, minLines = 2, maxLength = 300)
        HqButton("ثبت", {
            action.run {
                env.api.suggestion(s.id, "no", reason.trim())
                env.cache.invalidate("home")
                toasts.ok("ثبت شد؛ دیگر پیشنهاد نمیشود.")
                onDone()
            }
        }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, enabled = reason.isNotBlank(), loading = action.busy)
    }
}

private val NO_REASONS = listOf("الان اولویت نیست", "هزینه‌اش زیاد است", "قبلاً امتحان شد", "با برند نمیخواند")

/** A real move of a connection's figure: before → after, each with its day, and the source it was read from. */
@Composable
fun ProgressCard(p: HomeProgress, modifier: Modifier = Modifier) {
    val nav = LocalNav.current
    val c = Divan.colors
    val a = (p.before.value as? JsonPrimitive)?.contentOrNull?.toDoubleOrNull()
    val b = (p.after.value as? JsonPrimitive)?.contentOrNull?.toDoubleOrNull()
    val move = if (a != null && b != null) kpiMove(listOf(DayValue("a", a), DayValue("b", b))) else null
    HqCard(modifier.fillMaxWidth(), onClick = p.workRef?.let { ref -> { nav.go("work/$ref") } }) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            IconTile(DivanIcon.CHART, c.positive, c.softPositive)
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text("پیشرفت واقعی", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.positive)
                if (p.company.isNotBlank()) CoName(p.company)
            }
            move?.pct?.let { Pill(moveText(it), if (it >= 0) Tone.POS else Tone.NEG, figure = true) }
        }
        Text(plain(p.titleFa), style = Divan.type.bodyStrong, modifier = Modifier.padding(top = 12.dp))
        Row(Modifier.padding(top = 10.dp).fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Side("قبل", figureText(p.before.value), p.before.at, Modifier.weight(1f))
            DIcon(DivanIcon.NEXT, size = 18.dp, tint = c.textMuted)
            Side("بعد", figureText(p.after.value), p.after.at, Modifier.weight(1f), strong = true)
        }
        if (p.source.isNotBlank()) Text("منبع: ${connectionKindFa(p.source)}", style = Divan.type.micro, color = c.textMuted, modifier = Modifier.padding(top = 8.dp))
    }
}

@Composable
private fun Side(label: String, value: String, at: String?, modifier: Modifier, strong: Boolean = false) {
    val c = Divan.colors
    Column(modifier.clip(RoundedCornerShape(Radius.tile)).background(if (strong) c.softPositive else c.tile).padding(horizontal = 12.dp, vertical = 10.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Text(label, style = Divan.type.micro, color = c.textMuted)
        com.coinepro.hq.designsystem.Fig(value, style = Divan.type.figureM, color = if (strong) c.positive else c.textPrimary)
        if (at != null) Text(jDate(at), style = Divan.type.micro, color = c.textMuted)
    }
}

/** The morning in five lines (rule-based, 08:00 Tehran): yesterday's outputs, the best move of a KPI, what waits for the owner. */
@Composable
fun MorningCard(lines: List<String>) {
    val c = Divan.colors
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("خلاصه‌ی صبح", note = "پنج خط، از روی عددهای دیروز", icon = DivanIcon.REPORT)
        Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            lines.take(5).forEachIndexed { i, l ->
                Row(verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    Box(Modifier.padding(top = 2.dp).size(20.dp).clip(CircleShape).background(c.tile), contentAlignment = Alignment.Center) {
                        Text("${i + 1}", style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
                    }
                    Text(plain(l), style = Divan.type.small.copy(textAlign = TextAlign.Justify), color = c.textPrimary, modifier = Modifier.weight(1f))
                }
            }
        }
    }
}

/** A working group's KPI, one line per member company (each in its own colour), over the last days; it opens the group. */
@Composable
fun GroupKpiCard(g: HomeGroup) {
    val nav = LocalNav.current
    val k = g.companies.firstNotNullOfOrNull { it.kpi }
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle(g.titleFa, note = k?.titleFa?.let { "$it، هر شرکت جدا" }) {
            HqButton("کارگروه", { nav.go("groups/${g.key}") }, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.NEXT)
        }
        CompanyKpiChart(
            g.companies.map { it.code to (it.kpi?.series ?: emptyList()) },
            label = "${g.titleFa}: ${k?.titleFa.orEmpty()}",
            fmt = { numberText(it, k?.unit.orEmpty()) },
            modifier = Modifier.padding(top = 10.dp),
            unit = k?.unit.orEmpty(),
        )
    }
}

/** The owner's orders with their state and, once ended, the one-line summary; each opens its report. */
@Composable
fun HomeOrdersBlock(orders: List<HomeOrder>, onNewOrder: () -> Unit) {
    val nav = LocalNav.current
    val c = Divan.colors
    val moving = orders.count { it.state !in setOf("delivered", "failed", "cancelled") }
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("فرمان‌های من", note = if (moving > 0) "$moving فرمان در جریان" else "فرمانی در جریان نیست") {
            HqButton("همه", { nav.go("orders") }, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.NEXT)
        }
        if (orders.isEmpty()) Column(Modifier.padding(top = 8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("هر فرمانی بدهی این‌جا با وضعیتش دیده میشود، و وقتی تمام شد میگوید چه شد و چه ماند.", style = Divan.type.caption, color = c.textMuted)
            HqButton("فرمان تازه", onNewOrder, size = BtnSize.SM, icon = DivanIcon.COMMAND)
        }
        else Column(Modifier.padding(top = 6.dp)) {
            orders.take(5).forEachIndexed { i, o ->
                if (i > 0) HorizontalDivider(color = c.lineDivider)
                Column(
                    Modifier.fillMaxWidth().clickable(role = Role.Button, onClickLabel = "گزارش فرمان") { nav.go("session/${o.ref}") }.padding(vertical = 10.dp),
                    verticalArrangement = Arrangement.spacedBy(4.dp),
                ) {
                    Row(verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text(plain(o.textFa), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), maxLines = 2, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
                        OrderStatePill(o.state)
                    }
                    if (o.summaryFa.isNotBlank()) Text(plain(o.summaryFa), style = Divan.type.caption, color = c.textSecondary, maxLines = 2, overflow = TextOverflow.Ellipsis)
                }
            }
        }
    }
}

private val CRITICAL_FA = mapOf("data_leak" to "نشت داده", "product_down" to "محصول از دسترس خارج است", "money" to "پول", "legal" to "حقوقی")

/** Only what is critical (§29.1: a data leak, a product down over 15 minutes, money, legal); nothing else technical reaches the home. */
@Composable
fun CriticalCard(items: List<Notification>) {
    val nav = LocalNav.current
    val c = Divan.colors
    HqCard(Modifier.fillMaxWidth(), color = c.softNegative) {
        SectionTitle("بحرانی", note = "فقط چیزی که همین حالا به تو مربوط است", icon = DivanIcon.URGENT)
        Column(Modifier.padding(top = 8.dp)) {
            items.forEachIndexed { i, n ->
                if (i > 0) HorizontalDivider(color = c.lineDivider)
                val to = Refs.forLink(n.link?.kind, n.link?.ref)
                Column(
                    Modifier.fillMaxWidth().then(if (to != null) Modifier.clickable(role = Role.Button) { nav.go(to) } else Modifier).padding(vertical = 10.dp)
                        .semantics(mergeDescendants = true) { contentDescription = n.titleFa },
                    verticalArrangement = Arrangement.spacedBy(4.dp),
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text(plain(n.titleFa), style = Divan.type.bodyStrong, color = c.textPrimary, modifier = Modifier.weight(1f))
                        n.criticalReason?.let { CRITICAL_FA[it] }?.let { Pill(it, Tone.NEG, dot = true) }
                    }
                    if (n.bodyFa.isNotBlank()) Text(plain(n.bodyFa), style = Divan.type.caption.copy(textAlign = TextAlign.Justify), color = c.textSecondary)
                    Text(ago(n.createdAt), style = Divan.type.micro, color = c.textMuted)
                }
            }
        }
    }
}

/** The home's place while `/home` loads. */
@Composable
fun HomeSkeleton() {
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Skeleton(Modifier.fillMaxWidth().height(180.dp), radius = 16.dp)
        Skeleton(Modifier.fillMaxWidth().height(150.dp), radius = 16.dp)
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) { Skeleton(Modifier.weight(1f).height(18.dp)); Box(Modifier.width(40.dp)) }
    }
}
