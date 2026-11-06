package com.coinepro.hq.ui.v29

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
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.blockerFa
import com.coinepro.hq.core.data.isOwnerOrder
import com.coinepro.hq.core.data.orderEnded
import com.coinepro.hq.core.data.outputKindFa
import com.coinepro.hq.core.data.routeLineFa
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.format.jDateTime
import com.coinepro.hq.core.format.jTime
import com.coinepro.hq.core.net.Blocker
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.OrderReport
import com.coinepro.hq.core.net.Work
import com.coinepro.hq.core.net.gated
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.Md
import com.coinepro.hq.designsystem.Radius
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.companyOf
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.rememberQuery

// Contract §29.2 ⟨1.11⟩: every order is answered. Its report: the state, the receipt and the assignee's plan, the route it took, the
// steps in plain Persian, what blocks it (each with its one-tap fix), its outputs, and when it ends «چه شد · چه ماند · از شما چه لازم است».
// Live: the stream's `order.report` refreshes it.

@Composable
fun rememberOrderReport(ref: String) = rememberQuery("order-report:$ref", "order-report", maxAgeMs = 15_000) { gated(HubFeature.ORDER_REPORT) { orderReport(ref) } }

/** «گزارش فرمان»: one order of the owner (`F-…`), from the receipt to the end summary. */
@Composable
fun OrderReportScreen(ref: String) {
    val q = rememberOrderReport(ref)
    val r = refresher(q)
    val has = served(HubFeature.ORDER_REPORT)
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        val o = q.data
        when {
            !has -> item { Empty("گزارش فرمان با به‌روزرسانی بعدی هاب میاید", icon = DivanIcon.REPORT, body = "تا آن موقع پیشرفت هر فرمان در «فرمان‌های من» دیده میشود.") }
            o == null && q.error != null -> item { ErrorBlock(q.error, { q.refresh() }) }
            o == null -> item { Skeleton(Modifier.fillMaxWidth().height(320.dp), radius = 16.dp) }
            else -> {
                item(key = "head") { ReportHead(o) }
                if (o.blockers.isNotEmpty()) item(key = "blockers") { BlockersCard(o) }
                o.summary?.takeIf { orderEnded(o.state) }?.let { s -> item(key = "summary") { SummaryCard(o, s) } }
                item(key = "plan") { PlanCard(o) }
                // ⟨1.15⟩ §33.10 a work on its company's own server, with «توقف»; §33.7 a split work's parts side by side.
                for (w in o.workspaces) item(key = "ws-${w.workRef}") { com.coinepro.hq.ui.v33.WorkspaceCard(w) }
                for (s in o.parts) item(key = "split-${s.workRef}") { com.coinepro.hq.ui.v33.SplitCard(s) }
                item(key = "steps") { StepsCard(o) }
                if (o.outputs.isNotEmpty()) item(key = "outputs") { OutputsCard(o) }
            }
        }
    }
}

@Composable
private fun ReportHead(o: OrderReport) {
    val c = Divan.colors
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("فرمان تو", style = Divan.type.caption, color = c.textMuted, modifier = Modifier.weight(1f))
            OrderStatePill(o.state)
        }
        com.coinepro.hq.ui.Selectable { Para(o.textFa, style = Divan.type.body, color = c.textPrimary) }
        Text(
            plain("داده شد ${jDateTime(o.at)}" + (o.updatedAt.takeIf { it.isNotBlank() }?.let { "؛ آخرین تغییر ${ago(it)}" } ?: "")),
            style = Divan.type.micro, color = c.textMuted,
        )
    }
}

/** What stops the order now, each with its fix. */
@Composable
private fun BlockersCard(o: OrderReport) {
    val c = Divan.colors
    val company = o.route?.companies?.firstOrNull() ?: o.ack?.assigned?.firstOrNull()?.company
    HqCard(Modifier.fillMaxWidth(), tahrir = true) {
        SectionTitle("چه چیزی جلویش را گرفته", note = "هر مورد را با یک ضربه درست کن", icon = DivanIcon.URGENT)
        Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            for (b in o.blockers) BlockerRow(b, company, o.ref, o.route?.budgetTokens)
        }
    }
}

@Composable
fun BlockerRow(b: Blocker, company: String?, orderRef: String?, budget: Long? = null) {
    val c = Divan.colors
    Column(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(Radius.tile)).background(c.softNegative).padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Text(plain(blockerFa(b.kind, b.titleFa)), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
        if (b.detailFa.isNotBlank()) Text(plain(b.detailFa), style = Divan.type.caption.copy(textAlign = TextAlign.Justify), color = c.textSecondary)
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            b.since?.let { Text("از ${ago(it)}", style = Divan.type.micro, color = c.textMuted, modifier = Modifier.weight(1f)) } ?: Box(Modifier.weight(1f))
            // +X for a short budget: a quarter of the order's own budget, at least 100K.
            b.fix?.let { FixButton(it, company, orderRef, budgetTokens = if (it.action == "budget.add") maxOf(100_000L, (budget ?: 0L) / 4) else null) }
        }
    }
}

/** The end report: what was done, what is left, and what is needed from the owner. */
@Composable
private fun SummaryCard(o: OrderReport, s: com.coinepro.hq.core.net.OrderSummary) {
    val c = Divan.colors
    HqCard(Modifier.fillMaxWidth(), tahrir = o.state == "delivered") {
        SectionTitle("پایان کار", note = "گزارش آخر، به زبان ساده", icon = DivanIcon.REPORT)
        Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Part("چه شد", s.doneFa, DivanIcon.SEAL, c.positive)
            Part("چه ماند", s.leftFa, DivanIcon.TIME, c.warning)
            Part("از شما چه لازم است", s.needFa.ifBlank { "چیزی لازم نیست." }, DivanIcon.OWNER, c.goldInk)
        }
    }
}

@Composable
private fun Part(title: String, body: String, icon: DivanIcon, tint: androidx.compose.ui.graphics.Color) {
    val c = Divan.colors
    if (body.isBlank()) return
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            Box(Modifier.size(22.dp).clip(CircleShape).background(tint.copy(alpha = 0.14f)), contentAlignment = Alignment.Center) { DIcon(icon, size = 13.dp, tint = tint) }
            Text(title, style = Divan.type.small.copy(fontWeight = FontWeight.Bold), color = c.textPrimary)
        }
        com.coinepro.hq.ui.Selectable { Para(body) }
    }
}

/** The receipt and the assignee's plan: who has it, by when, and the route the secretary gave it. */
@Composable
private fun PlanCard(o: OrderReport) {
    val c = Divan.colors
    val companies = rememberCompanies()
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("رسید و برنامه", note = o.ack?.let { "رسید ${ago(it.at)}" } ?: "رسید؛ برنامه هنوز نوشته نشده", icon = DivanIcon.PLANNER)
        Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            o.route?.let { r ->
                Text(plain(routeLineFa(r, { companyOf(companies, it).nameFa })), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.goldInk)
            }
            val a = o.ack
            if (a == null) Text("دریافت شد و سپرده شد؛ کسی که آن را گرفته باید تا ده دقیقه برنامه‌اش را بنویسد.", style = Divan.type.caption.copy(textAlign = TextAlign.Justify), color = c.textSecondary)
            else {
                if (a.planFa.isNotBlank()) com.coinepro.hq.ui.Selectable { Para(a.planFa) }
                for (x in a.assigned) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    CoName(x.company)
                    Text(plain(x.titleFa), style = Divan.type.caption, color = c.textPrimary, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
                }
                a.dueAt?.let { Text(plain("تا ${jDateTime(it)}"), style = Divan.type.caption, color = c.textMuted) }
            }
        }
    }
}

/** The steps in plain Persian, newest last: when, who, what. */
@Composable
internal fun StepsCard(o: OrderReport) {
    val c = Divan.colors
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("قدم‌ها", note = if (o.steps.isEmpty()) "هنوز قدمی برداشته نشده" else "${o.steps.size} قدم، آخری پایین", icon = DivanIcon.TASK)
        // The steps are selectable as one text (a long press, then the phone's handles and «کپی»).
        com.coinepro.hq.ui.Selectable { Column(Modifier.padding(top = 10.dp)) {
            o.steps.forEachIndexed { i, s ->
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                        Box(Modifier.padding(top = 5.dp).size(8.dp).clip(CircleShape).background(if (i == o.steps.lastIndex) c.goldFill else c.silverInk))
                        if (i < o.steps.lastIndex) Box(Modifier.width(1.dp).height(36.dp).background(c.lineDivider))
                    }
                    Column(Modifier.weight(1f).padding(bottom = 10.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Text(plain(s.whatFa), style = Divan.type.small, color = c.textPrimary)
                        Text(plain(listOf(s.whoFa, jTime(s.at)).filter { it.isNotBlank() && it != "—" }.joinToString(" · ")), style = Divan.type.micro, color = c.textMuted)
                    }
                }
            }
        } }
    }
}

@Composable
internal fun OutputsCard(o: OrderReport) {
    val nav = LocalNav.current
    val c = Divan.colors
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("خروجی‌ها", icon = DivanIcon.DELIVERABLE)
        Column(Modifier.padding(top = 6.dp)) {
            o.outputs.forEachIndexed { i, x ->
                if (i > 0) HorizontalDivider(color = c.lineDivider)
                Row(
                    Modifier.fillMaxWidth().clickable(role = Role.Button, onClickLabel = "باز کردن") { nav.go("outputs/${x.ref}") }.padding(vertical = 10.dp),
                    verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    DIcon(DivanIcon.DELIVERABLE, size = 16.dp, tint = c.goldInk)
                    Text(plain(x.titleFa), style = Divan.type.small, maxLines = 2, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
                    Text(outputKindFa(x.kind), style = Divan.type.micro, color = c.textMuted)
                }
            }
        }
    }
}

/** On an order's work page: its report in one line (state and summary) and the way to the whole of it. */
@Composable
fun OrderReportOnWork(w: Work) {
    if (!isOwnerOrder(w) || w.depth > 0 || !served(HubFeature.ORDER_REPORT)) return
    val nav = LocalNav.current
    val c = Divan.colors
    val orders = rememberQuery("voice-orders", "orders", maxAgeMs = 10_000) { orders().items }
    val o = orders.data?.firstOrNull { x -> x.routes.any { it.workRef == w.ref } } ?: return
    HqCard(Modifier.fillMaxWidth(), onClick = { nav.go("session/${o.ref}") }) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            IconTile(DivanIcon.REPORT, c.goldInk, c.softGold, 36.dp)
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text("گزارش این فرمان", style = Divan.type.bodyStrong)
                Text(
                    plain(o.summary?.doneFa?.takeIf { it.isNotBlank() } ?: "رسید، برنامه، قدم‌ها و هر چیزی که جلویش را گرفته"),
                    style = Divan.type.caption, color = c.textSecondary, maxLines = 2, overflow = TextOverflow.Ellipsis,
                )
            }
            o.state?.let { OrderStatePill(it) }
            HqButton(null, { nav.go("session/${o.ref}") }, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.NEXT, label = "گزارش فرمان")
        }
    }
}
