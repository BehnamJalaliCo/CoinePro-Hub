package com.coinepro.hq.ui.v29

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.CircularProgressIndicator
import com.coinepro.hq.designsystem.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.OUTPUT_KIND_FA
import com.coinepro.hq.core.data.PlayerOption
import com.coinepro.hq.core.data.routeLineFa
import com.coinepro.hq.core.format.DEPT_FA
import com.coinepro.hq.core.format.tokens
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.OrderRoute29
import com.coinepro.hq.core.net.gated
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.Radius
import com.coinepro.hq.designsystem.SegOption
import com.coinepro.hq.designsystem.Segmented
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.companyOf
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.rememberQuery
import kotlinx.coroutines.delay

// Contract §29.4 ⟨1.11⟩: the holding's secretary. When the owner has said or written an order, one line says where it goes, what comes
// out and with what budget («→ تریدیار/رسانه + IG-Hub/انتشار؛ خروجی: 3 ریلز؛ بودجه: …»); the owner may change the company, the
// department, who works with it, the output, the mode and the player, then «بفرست» sends the order with that route, followed exactly.

/** The secretary's preview of [text] (debounced while the owner edits); [edited] keeps the owner's own route. Null: none yet, or this
 *  hub has no secretary ([HubFeature.PREVIEW]), and the order goes as before. */
class Preview {
    var route by mutableStateOf<OrderRoute29?>(null)
    var loading by mutableStateOf(false)
    var edited by mutableStateOf(false)
}

@Composable
fun rememberPreview(text: String, source: String, on: Boolean, preview0: OrderRoute29? = null): Preview {
    val env = LocalEnv.current
    val p = remember { Preview().apply { route = preview0 } }
    LaunchedEffect(text, on) {
        if (!on || p.edited || preview0 != null || text.trim().length < 8 || !env.api.gaps.has(HubFeature.PREVIEW)) return@LaunchedEffect
        delay(650)
        p.loading = true
        try {
            p.route = env.api.gated(HubFeature.PREVIEW) { orderPreview(text.trim(), source) }
        } catch (e: ApiException) {
            // The preview is a help, never a gate: without it the hub decides as before.
            e.logged?.let { env.api.failures?.forget(it) }
        } finally {
            p.loading = false
        }
    }
    return p
}

/** The one line, with «تغییر» to edit it. */
@Composable
fun PreviewLine(p: Preview, onEdit: () -> Unit, modifier: Modifier = Modifier) {
    val c = Divan.colors
    val companies = rememberCompanies()
    val r = p.route
    if (r == null && !p.loading) return
    Column(
        modifier.fillMaxWidth().clip(RoundedCornerShape(Radius.tile)).background(c.softGold).border(1.dp, c.lineTahrir, RoundedCornerShape(Radius.tile))
            .padding(horizontal = 12.dp, vertical = 10.dp).semantics(mergeDescendants = true) { contentDescription = "پیش‌نمایش منشی" },
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            DIcon(DivanIcon.DELEGATE, size = 16.dp, tint = c.goldInk)
            Text(if (p.edited) "مسیر، با تغییر تو" else "منشی هلدینگ این‌طور میفرستد", style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = c.silverInk, modifier = Modifier.weight(1f))
            if (p.loading) CircularProgressIndicator(Modifier.size(14.dp), color = c.goldInk, strokeWidth = 2.dp)
            else HqButton("تغییر", onEdit, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.EDIT)
        }
        if (r != null) {
            Text(plain(routeLineFa(r, { companyOf(companies, it).nameFa })), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
            if (r.whyFa.isNotBlank() && !p.edited) Text(plain(r.whyFa), style = Divan.type.micro, color = c.textSecondary)
        }
    }
}

/** The route's editor in its sheet. */
@Composable
fun RouteEditor(r0: OrderRoute29, onDone: (OrderRoute29) -> Unit, onCancel: () -> Unit) {
    com.coinepro.hq.ui.v14.HqSheet(onCancel, "مسیر فرمان", sub = "منشی پیشنهاد داد؛ هر چه را بخواهی عوض کن. فرمان دقیقاً همین‌طور میرود.") { RouteEditorBody(r0, onDone) }
}

/** The route's editor: company, department, who works with it, the output and its count, single or council, and the player. */
@Composable
fun RouteEditorBody(r0: OrderRoute29, onDone: (OrderRoute29) -> Unit) {
    val c = Divan.colors
    val companies = rememberCompanies().filter { it.kind != "holding" }
    var r by remember(r0) { mutableStateOf(r0) }
    val first = r.companies.firstOrNull()
    val depts = if (first != null) rememberQuery("departments:$first", "companies") { departments(first) }.data.orEmpty() else emptyList()
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Label("شرکت")
        com.coinepro.hq.ui.v16.ChipRow {
            for (co in companies) com.coinepro.hq.ui.v16.CoChip(co.code, co.nameFa ?: co.code, first == co.code) {
                r = r.copy(companies = listOf(co.code) + r.companies.drop(1).filter { it != co.code }, department = null)
            }
        }
        if (depts.isNotEmpty()) {
            Label("دپارتمان")
            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                FilterChip("مدیرعامل تصمیم بگیرد", r.department == null, { r = r.copy(department = null) })
                for (d in depts.sortedBy { it.sort }) FilterChip(d.nameFa.ifBlank { DEPT_FA[d.code] ?: d.code }, r.department == d.code, { r = r.copy(department = d.code) })
            }
        }
        Label("همکار")
        com.coinepro.hq.ui.v16.ChipRow {
            for (co in companies.filter { it.code != first }) {
                val on = co.code in r.collaborators
                com.coinepro.hq.ui.v16.CoChip(co.code, co.nameFa ?: co.code, on) {
                    r = r.copy(collaborators = if (on) r.collaborators - co.code else r.collaborators + co.code)
                }
            }
        }
        Label("خروجی")
        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            for ((k, fa) in OUTPUT_KIND_FA) FilterChip(fa, r.outputKind == k, { r = r.copy(outputKind = k) })
        }
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("تعداد", style = Divan.type.caption, color = c.textMuted, modifier = Modifier.weight(1f))
            HqButton("−", { r = r.copy(count = ((r.count ?: 1) - 1).takeIf { it >= 1 }) }, variant = BtnVariant.SECONDARY, size = BtnSize.SM, label = "کمتر")
            Fig(r.count?.toString() ?: "—", style = Divan.type.figure, color = c.textPrimary)
            HqButton("+", { r = r.copy(count = minOf(50, (r.count ?: 0) + 1)) }, variant = BtnVariant.SECONDARY, size = BtnSize.SM, label = "بیشتر")
        }
        Label("روش")
        Segmented(
            listOf(SegOption("single", "یک بازیکن"), SegOption("council", "شورای مدل‌ها", DivanIcon.MEETING)),
            r.mode, { m -> r = r.copy(mode = m) }, Modifier.fillMaxWidth(),
        )
        if (r.mode == "single") {
            Label("بازیکن")
            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                for (o in PlayerOption.entries.filter { it != PlayerOption.COUNCIL }) FilterChip(o.fa, r.player == o.player, { r = r.copy(player = o.player) })
            }
        }
        r.budgetTokens?.let { b ->
            Text(plain("بودجه: ${tokens(b)} واحد مصرف؛ هیچ‌وقت کمتر از کف دپارتمان نیست."), style = Divan.type.caption, color = c.textMuted)
        }
        Text(plain(routeLineFa(r.copy(previewFa = ""), { companyOf(companies, it).nameFa })), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.silverInk)
        HqButton("همین مسیر", { onDone(r.copy(previewFa = "")) }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, icon = DivanIcon.SEAL, enabled = r.companies.isNotEmpty())
    }
}

@Composable
private fun Label(text: String) {
    Text(text, style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = Divan.colors.textSecondary, modifier = Modifier.padding(top = 2.dp))
}
