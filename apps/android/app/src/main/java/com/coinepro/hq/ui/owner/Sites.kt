package com.coinepro.hq.ui.owner

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.format.jDateTime
import com.coinepro.hq.core.net.Site
import com.coinepro.hq.core.net.SiteIn
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.CompanyMark
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
import com.coinepro.hq.designsystem.IconBtn
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.activity
import com.coinepro.hq.ui.companyOf
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v14.HqSheet
import java.util.Locale

private fun uptime(v: Double?) = if (v == null) "—" else if (v >= 0.999 || v == 0.0) "${(v * 100).toInt()}%" else String.format(Locale.US, "%.1f%%", v * 100)

@Composable
private fun SiteRow(s: Site) {
    val c = Divan.colors
    val down = s.enabled && s.last?.ok == false
    Column(
        Modifier.fillMaxWidth().alpha(if (s.enabled) 1f else 0.6f).clip(RoundedCornerShape(12.dp)).background(if (down) c.softNegative else c.tile).padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Box(Modifier.size(9.dp).clip(CircleShape).background(if (!s.enabled) c.textMuted else if (down) c.negative else c.positive))
            Fig(s.url.removePrefix("https://").removePrefix("http://"), style = Divan.type.figureSmall, color = c.textPrimary, modifier = Modifier.weight(1f))
            if (s.canary) Pill("canary", figure = true)
            if (!s.enabled) Pill("خاموش")
        }
        FlowRow(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Fig("${s.kind} · ${s.method}", style = Divan.type.figureSmall, color = c.textMuted)
            Fig("24h ${uptime(s.uptime24h)}", style = Divan.type.figureSmall, color = c.textSecondary)
            s.last?.let { l -> Fig("${l.status ?: "—"} · ${l.ms?.let { "${it}ms" } ?: "—"}", style = Divan.type.figureSmall, color = c.textMuted) }
            s.last?.at?.let { Text(ago(it), style = Divan.type.micro, color = c.textMuted) }
            if (s.consecutiveFailures > 0) Text("${s.consecutiveFailures} شکست پشت هم", style = Divan.type.micro, color = c.negative)
            s.last?.error?.let { Fig(it, style = Divan.type.figureSmall, color = c.negative) }
        }
    }
}

/** Site checks and incidents (§16.4): every product URL, its last check, 24 h uptime, and the incidents it opened. */
@Composable
fun SitesScreen() {
    val c = Divan.colors
    val nav = LocalNav.current
    val companies = rememberCompanies()
    val sites = rememberQuery("ops:sites", "ops", maxAgeMs = 60_000) { sites() }
    val incidents = rememberQuery("ops:incidents", "ops", maxAgeMs = 60_000) { incidents() }
    val r = refresher(sites, incidents)
    var edit by rememberSaveable { mutableStateOf<String?>(null) }
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item { PageHeader("پایش سایت‌ها", eyebrow = "هر دقیقه از بیرون؛ با شکست پشت هم، حادثه و بیدار شدن SRE") }
        val all = sites.data
        when {
            all == null && sites.error != null -> item { ErrorBlock(sites.error, { sites.refresh() }) }
            all == null -> item { Skeleton(Modifier.fillMaxWidth().height(220.dp), radius = 16.dp) }
            all.isEmpty() -> item { Empty("سایتی ثبت نشده", icon = DivanIcon.SERVER) }
            else -> items(all.groupBy { it.company }.toList(), key = { it.first }) { (co, list) ->
                HqCard(Modifier.fillMaxWidth()) {
                    SectionTitle(companyOf(companies, co).nameFa, action = if (co != "HQ") ({ HqButton("ویرایش", { edit = co }, size = BtnSize.SM, variant = BtnVariant.TEXT, icon = DivanIcon.EDIT) }) else null)
                    Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) { list.forEach { SiteRow(it) } }
                }
            }
        }
        item {
            HqCard(Modifier.fillMaxWidth()) {
                SectionTitle("حادثه‌ها", note = "باز بالا")
                val list = incidents.data
                when {
                    list == null && incidents.error != null -> ErrorBlock(incidents.error, { incidents.refresh() })
                    list == null -> Skeleton(Modifier.fillMaxWidth().height(96.dp))
                    list.isEmpty() -> Text("حادثه‌ای ثبت نشده.", style = Divan.type.caption, color = c.textMuted, modifier = Modifier.padding(top = 8.dp))
                    else -> Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        list.sortedBy { it.closedAt != null }.forEach { x ->
                            Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(if (x.closedAt == null) c.softNegative else c.tile).padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                    Fig(x.ref, style = Divan.type.figureSmall, color = c.textPrimary)
                                    CompanyMark(x.company, height = 11.dp, mono = true, ink = c.textSecondary)
                                    Box(Modifier.weight(1f))
                                    if (x.closedAt == null) Pill("باز", Tone.NEG, icon = DivanIcon.URGENT) else Pill("بسته", Tone.POS, dot = true)
                                }
                                Fig(x.url.removePrefix("https://"), style = Divan.type.figureSmall, color = c.textSecondary)
                                FlowRow(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                                    Text("از ${jDateTime(x.openedAt)}", style = Divan.type.micro, color = c.textMuted)
                                    x.closedAt?.let { Text("تا ${jDateTime(it)}", style = Divan.type.micro, color = c.textMuted) }
                                    x.lastError?.let { Fig(it, style = Divan.type.figureSmall, color = c.textMuted) }
                                    x.workRef?.let { w -> Fig(w, style = Divan.type.figureSmall, color = c.goldInk, modifier = Modifier.clickable { nav.go("work/$w") }) }
                                }
                            }
                        }
                    }
                }
                Row(Modifier.padding(top = 10.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    DIcon(DivanIcon.INFO, size = 14.dp, tint = c.textMuted)
                    Text("فقط بیرون سایت دیده میشود. متریک داخل سرورها منتظر CR-001 است (تصمیم تو).", style = Divan.type.micro, color = c.textMuted)
                }
            }
        }
    }
    edit?.let { co -> EditSitesSheet(co, sites.data.orEmpty().filter { it.company == co && !it.canary }) { edit = null } }
}

/** One company's list replaced as a whole (§16.6 PUT /ops/sites): left-out URLs are switched off, never deleted; canaries stay. */
@Composable
private fun EditSitesSheet(company: String, current: List<Site>, onDismiss: () -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val act = activity()
    val action = rememberAction()
    val c = Divan.colors
    val rows = remember { mutableStateListOf(*current.map { SiteIn(it.url, it.kind, it.method, it.intervalS, it.enabled) }.toTypedArray()) }
    val valid = rows.all { Regex("^https://[^\\s/]+\\.\\S+$").matches(it.url.trim()) } && rows.map { it.url.trim() }.toSet().size == rows.size
    HqSheet(onDismiss, "سایت‌های ${companyOf(rememberCompanies(), company).nameFa}", sub = "نشانی‌ای که برداری خاموش میشود و تاریخچه‌اش میماند. نشانی داخلی یا خصوصی پذیرفته نمیشود.") {
        rows.forEachIndexed { i, s ->
            Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(10.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
                        HqTextField(s.url, { rows[i] = s.copy(url = it) }, "https://…", Modifier.weight(1f), maxLength = 500, figure = true)
                    }
                    IconBtn(DivanIcon.CLOSE, "برداشتن", { rows.removeAt(i) })
                }
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    listOf("web", "api", "bot").forEach { k -> FilterChip(k, s.kind == k, { rows[i] = s.copy(kind = k) }) }
                    listOf("GET", "HEAD").forEach { m -> FilterChip(m, s.method == m, { rows[i] = s.copy(method = m) }) }
                }
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    listOf(30 to "۳۰ ثانیه", 60 to "یک دقیقه", 300 to "پنج دقیقه").forEach { (n, l) -> FilterChip(l, s.intervalS == n, { rows[i] = s.copy(intervalS = n) }) }
                    Box(Modifier.weight(1f))
                    HqSwitch(s.enabled, { rows[i] = s.copy(enabled = it) }, "روشن")
                }
            }
        }
        if (rows.size < 50) HqButton("نشانی تازه", { rows.add(SiteIn("https://")) }, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.ADD)
        HqButton("ذخیره با گذرکلید", {
            action.run {
                env.api.putSites(company, rows.map { it.copy(url = it.url.trim()) }) { target -> env.auth.stepUp(act, "sites.update", target) }
                env.cache.invalidate("ops")
                toasts.ok("فهرست سایت‌ها ذخیره شد.")
                onDismiss()
            }
        }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, size = BtnSize.LG, icon = DivanIcon.SEAL, enabled = valid, loading = action.busy)
    }
}
