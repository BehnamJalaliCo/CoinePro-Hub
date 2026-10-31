package com.coinepro.hq.ui.companies

import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDirection
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.format.jDateTime
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.Catalogue
import com.coinepro.hq.core.net.CatalogueSection
import com.coinepro.hq.core.net.CatalogueServer
import com.coinepro.hq.core.net.CatalogueTable
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.gated
import com.coinepro.hq.core.net.routeMissing
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.Md
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.Radius
import com.coinepro.hq.designsystem.ScrollRow
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.Space
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.designsystem.rememberHaptics
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.companyOf
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v17.RefChip
import kotlinx.coroutines.delay

// ⟨1.10⟩ contract §28.2: a company's catalogue — a deep extraction, not a summary. A read-only `claude` job on every paired server reads
// what runs there (products and services, automations and schedules, data, interfaces, code, risks); the result is filed in the archive
// as a `report` record and delivered to the owner. The CEO starts it for an order to "go through / extract everything".

/** The brief every run follows, as the page shows it before the first one. */
private val BRIEF = listOf(
    DivanIcon.SERVER to "محصولات و سرویس‌ها: هر کانتینر، پروژه‌ی compose، سرویس systemd، پورت، دامنه و سایت، و کار هرکدام",
    DivanIcon.TIME to "اتوماسیون‌ها و زمان‌بندی‌ها: هر workflow در n8n با تریگر، گره‌ها، آخرین اجرا و خطا؛ cron و timer",
    DivanIcon.MEMORY to "داده: دیتابیس‌ها، جدول‌ها با تعداد ردیف (بی محتوای ردیف)، صف‌ها و باکت‌ها",
    DivanIcon.GLOBE to "رابط‌ها: API و مسیرهایش، ربات‌ها و دستورهایشان، webhookها و سرویس‌های بیرونی (فقط نام، هرگز رمز)",
    DivanIcon.CODE to "کد: ریپوها، شاخه‌ها و آخرین commitها؛ خروجی‌ها و گزارش‌ها؛ خطاهای تکراری لاگ",
    DivanIcon.URGENT to "ریسک‌ها: گواهی رو به انقضا، سرویس خراب، پورت عمومی، بسته‌ی کهنه با CVE",
)

/** The latest catalogue, or null while the company has none (the hub's own `404`) or while this hub has no catalogue at all (a missing
 *  route, remembered for this app start: [HubFeature.CATALOGUE]). */
private suspend fun com.coinepro.hq.core.net.Api.catalogueOrNull(code: String): Catalogue? = gated(HubFeature.CATALOGUE) {
    try {
        catalogue(code)
    } catch (e: ApiException) {
        if (e.status != 404 || e.routeMissing) throw e
        e.logged?.let { failures?.forget(it) }
        null
    }
}

/** Whether this hub serves the catalogue (false once its route turned out missing). */
@Composable
internal fun catalogueServed(): Boolean {
    val gaps by LocalEnv.current.api.gaps.missing.collectAsStateWithLifecycle()
    return HubFeature.CATALOGUE !in gaps
}

/** «کاتالوگ کامل» of [code]: start or refresh a run, its live state per server, then the sections with their tables. */
@Composable
fun CatalogueScreen(code: String) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val haptics = rememberHaptics()
    val companies = rememberCompanies()
    val co = companyOf(companies, code)
    val q = rememberQuery("catalogue:$code", "catalogue") { catalogueOrNull(code) }
    val r = refresher(q)
    val start = rememberAction()
    var section by rememberSaveable { mutableStateOf<String?>(null) }
    val k = q.data
    // While it runs, the page follows it.
    val onScreen = com.coinepro.hq.ui.rememberOnScreen()
    LaunchedEffect(k?.running, onScreen) {
        while (k?.running == true && onScreen) {
            delay(4_000)
            q.refresh()
        }
    }
    val served = catalogueServed()
    fun run() = start.run {
        val out = env.api.gated(HubFeature.CATALOGUE) { startCatalogue(code) } ?: return@run
        q.set(out)
        env.cache.invalidate("catalogue")
        haptics.confirm()
        toasts.ok("کاتالوگ ${co.nameFa} شروع شد؛ فقط میخواند و چیزی را تغییر نمیدهد.")
    }
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item {
            PageHeader("کاتالوگ کامل", eyebrow = "${co.nameFa}: هرچه روی سرورهایش هست، جزءبه‌جزء؛ فقط خواندنی") {
                if (served && (q.data != null || (q.error == null && !q.loading))) HqButton(
                    if (k == null) "شروع" else "به‌روز کن", ::run, size = BtnSize.SM, variant = BtnVariant.PRIMARY,
                    icon = DivanIcon.REFRESH, enabled = k?.running != true, loading = start.busy,
                )
            }
        }
        when {
            !served -> item {
                Empty("کاتالوگ با به‌روزرسانی هاب میاید", icon = DivanIcon.KNOWLEDGE, body = "این هاب هنوز کاتالوگ کامل را ندارد؛ بعد از به‌روزرسانی از همین‌جا شروعش کن.")
            }
            q.loading -> item { Skeleton(Modifier.fillMaxWidth().height(220.dp), radius = Radius.card) }
            k == null && q.error != null -> item { ErrorBlock(q.error, { q.refresh() }) }
            k == null -> item {
                HqCard(Modifier.fillMaxWidth()) {
                    Empty(
                        "هنوز کاتالوگی برای ${co.nameFa} نیست", icon = DivanIcon.KNOWLEDGE,
                        body = "روی هر سرور جفت‌شده‌ی ${co.nameFa} یک کار فقط‌خواندنی همه‌چیز را میخواند؛ نتیجه در بایگانی ثبت میشود و برایت میاید.",
                    ) { HqButton("شروع کاتالوگ", ::run, variant = BtnVariant.PRIMARY, icon = DivanIcon.RESUME, loading = start.busy) }
                    BriefList()
                }
            }
            else -> {
                item(key = "cat-state") { StateCard(k, co.nameFa) }
                if (k.sections.isNotEmpty()) {
                    item(key = "cat-chips") {
                        ScrollRow {
                            FilterChip("همه", section == null, { section = null }, count = k.sections.size)
                            for (s in k.sections) FilterChip(s.titleFa.ifBlank { s.key }, section == s.key, { section = if (section == s.key) null else s.key }, count = s.count)
                        }
                    }
                    for (s in k.sections.filter { section == null || it.key == section }) item(key = "cat-${s.key}") { SectionCard(s) }
                }
                if (k.sections.isEmpty() && !k.running) item { HqCard(Modifier.fillMaxWidth()) { BriefList() } }
            }
        }
    }
}

@Composable
private fun BriefList() {
    val c = Divan.colors
    Text("هر اجرا این‌ها را میخواند", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary, modifier = Modifier.padding(bottom = Space.xs))
    Consequences(BRIEF, c.goldInk)
}

/** Where the run is: running (each server's job), failed (why), or done (when, and its archive record and output). */
@Composable
private fun StateCard(k: Catalogue, companyFa: String) {
    val c = Divan.colors
    HqCard(Modifier.fillMaxWidth(), tahrir = k.state == "done", color = if (k.state == "failed") c.softNegative else c.card) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Space.sm)) {
            Box(Modifier.size(40.dp).clip(CircleShape).background(c.tile), contentAlignment = Alignment.Center) {
                DIcon(DivanIcon.KNOWLEDGE, size = 20.dp, tint = when (k.state) { "failed" -> c.negative; "done" -> c.goldInk; else -> c.textSecondary })
            }
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(
                    when (k.state) { "running" -> "سرورها خوانده میشوند"; "failed" -> "کاتالوگ کامل نشد"; else -> "کاتالوگ آماده است" },
                    style = Divan.type.bodyStrong, color = if (k.state == "failed") c.negative else c.textPrimary,
                )
                Text(
                    com.coinepro.hq.designsystem.timesFig(when {
                        k.running -> k.at?.let { "از ${ago(it)}؛ صفحه خودش به‌روز میشود" } ?: "صفحه خودش به‌روز میشود"
                        k.at != null -> "${jDateTime(k.at)}، ${ago(k.at)}"
                        else -> ""
                    }),
                    style = Divan.type.caption, color = c.textMuted,
                )
            }
            when (k.state) {
                "running" -> Pill("در جریان", Tone.GOLD, live = true)
                "failed" -> Pill("ناموفق", Tone.NEG, dot = true)
                else -> Pill("${k.sections.size} بخش", Tone.POS, icon = DivanIcon.SEAL)
            }
        }
        k.reasonFa?.takeIf { k.state == "failed" }?.let { Text(it, style = Divan.type.small, color = c.textPrimary, modifier = Modifier.padding(top = Space.xs)) }
        if (k.servers.isNotEmpty()) {
            Column(Modifier.padding(top = Space.sm).fillMaxWidth().clip(RoundedCornerShape(Radius.tile)).background(c.tile).padding(horizontal = Space.sm, vertical = 4.dp)) {
                k.servers.forEachIndexed { i, s ->
                    if (i > 0) HorizontalDivider(color = c.lineDivider)
                    ServerLine(s, companyFa)
                }
            }
        }
        if (k.record != null || k.deliverable != null) FlowRow(Modifier.padding(top = Space.sm), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            k.record?.let { RefChip(it, "در بایگانی") }
            k.deliverable?.let { RefChip(it, "خروجی") }
        }
    }
}

/** One paired server's job, named by its company («تریدیار · اصلی»). */
@Composable
private fun ServerLine(s: CatalogueServer, companyFa: String) {
    val c = Divan.colors
    Row(Modifier.fillMaxWidth().padding(vertical = 8.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        DIcon(DivanIcon.SERVER, size = 16.dp, tint = c.textSecondary)
        Column(Modifier.weight(1f)) {
            Text(if (s.name.isBlank()) companyFa else "$companyFa · ${s.name}", style = Divan.type.small, color = c.textPrimary, maxLines = 1, overflow = TextOverflow.Ellipsis)
            s.reasonFa?.let { Text(it, style = Divan.type.micro, color = c.negative, maxLines = 2) }
        }
        when (s.state) {
            "running" -> Pill("میخواند", Tone.GOLD, live = true)
            "done" -> Pill("تمام", Tone.POS, dot = true)
            "failed" -> Pill("ناموفق", Tone.NEG, dot = true)
            else -> Pill("در صف", Tone.NEUTRAL, dot = true)
        }
    }
}

private val SECTION_ICON = mapOf(
    "products" to DivanIcon.SERVER, "automations" to DivanIcon.TIME, "data" to DivanIcon.MEMORY,
    "interfaces" to DivanIcon.GLOBE, "code" to DivanIcon.CODE, "risks" to DivanIcon.URGENT,
)

/** A section: its summary, its tables (each scrolls sideways) and any notes. */
@Composable
private fun SectionCard(s: CatalogueSection) {
    val c = Divan.colors
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle(s.titleFa.ifBlank { s.key }, icon = SECTION_ICON[s.key] ?: DivanIcon.REPORT) {
            s.count?.let { Pill("$it مورد", if (s.key == "risks" && it > 0) Tone.NEG else Tone.SILVER) }
        }
        s.summaryMd?.takeIf { it.isNotBlank() }?.let { Md(it, Modifier.padding(top = Space.xs)) }
        for (t in s.tables) CatalogueGrid(t, Modifier.padding(top = Space.sm))
        s.notesMd?.takeIf { it.isNotBlank() }?.let { Md(it, Modifier.padding(top = Space.sm), style = Divan.type.caption, color = c.textSecondary) }
    }
}

/** A cell's width from its column's longest text (the header included), between a narrow and a wide limit. */
internal fun columnWidths(t: CatalogueTable): List<Int> = t.columns.indices.map { i ->
    val longest = (listOf(t.columns[i]) + t.rows.indices.map { r -> t.cell(r, i) }).maxOf { it.length }
    (longest * 7 + 28).coerceIn(84, 240)
}

/** A table that scrolls sideways when it is wider than the card; Latin cells (names, ports, versions) read left to right. */
@Composable
internal fun CatalogueGrid(t: CatalogueTable, modifier: Modifier = Modifier) {
    val c = Divan.colors
    val widths = columnWidths(t)
    Column(modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        t.titleFa?.let { Text(it, style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary) }
        Box(Modifier.fillMaxWidth().clip(RoundedCornerShape(Radius.tile)).background(c.tile)) {
            Column(Modifier.horizontalScroll(rememberScrollState())) {
                Row(Modifier.background(c.lineDivider.copy(alpha = 0.35f)).padding(vertical = 8.dp)) {
                    t.columns.forEachIndexed { i, h -> Cell(h, widths[i], header = true) }
                }
                t.rows.indices.forEach { r ->
                    if (r > 0) Box(Modifier.width(widths.sum().dp).height(1.dp).background(c.lineDivider))
                    Row(Modifier.padding(vertical = 8.dp)) { t.columns.indices.forEach { i -> Cell(t.cell(r, i), widths[i]) } }
                }
            }
        }
        if (t.rows.isEmpty()) Text("موردی پیدا نشد.", style = Divan.type.caption, color = c.textMuted)
    }
}

@Composable
private fun Cell(text: String, width: Int, header: Boolean = false) {
    val c = Divan.colors
    val latin = text.none { it in '؀'..'ۿ' }
    val style = when {
        header -> Divan.type.micro.copy(fontWeight = FontWeight.SemiBold)
        latin -> Divan.type.figureSmall.copy(textDirection = TextDirection.Ltr)
        else -> Divan.type.small
    }
    Text(
        text, Modifier.width(width.dp).padding(horizontal = 10.dp), style = style,
        color = if (header) c.textSecondary else c.textPrimary, maxLines = if (header) 2 else 3, overflow = TextOverflow.Ellipsis,
    )
}

/** The control room's entry: the latest catalogue in one line, and the way to it. */
@Composable
internal fun CatalogueCard(code: String, nameFa: String) {
    val nav = LocalNav.current
    val c = Divan.colors
    val q = rememberQuery("catalogue:$code", "catalogue", maxAgeMs = 60_000) { catalogueOrNull(code) }
    val k = q.data
    // A hub before ⟨1.10⟩: the entry is not shown.
    if (!catalogueServed()) return
    HqCard(Modifier.fillMaxWidth(), onClick = { nav.go("catalogue/$code") }) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Space.sm)) {
            Box(Modifier.size(36.dp).clip(CircleShape).background(c.tile), contentAlignment = Alignment.Center) { DIcon(DivanIcon.KNOWLEDGE, size = 18.dp, tint = c.goldInk) }
            Column(Modifier.weight(1f)) {
                Text("کاتالوگ کامل", style = Divan.type.bodyStrong.copy(fontWeight = FontWeight.SemiBold))
                Text(
                    when {
                        k == null -> "هرچه روی سرورهای $nameFa هست، جزءبه‌جزء؛ هنوز اجرا نشده"
                        k.running -> "در حال خواندن سرورها…"
                        k.state == "failed" -> "آخرین اجرا کامل نشد"
                        else -> "${k.sections.size} بخش، ${k.at?.let(::ago).orEmpty()}"
                    },
                    style = Divan.type.caption, color = c.textMuted, maxLines = 1, overflow = TextOverflow.Ellipsis,
                )
            }
            if (k?.running == true) Pill("در جریان", Tone.GOLD, live = true) else DIcon(DivanIcon.NEXT, size = 16.dp, tint = c.textMuted)
        }
    }
}
