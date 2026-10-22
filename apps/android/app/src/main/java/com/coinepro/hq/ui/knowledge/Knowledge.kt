package com.coinepro.hq.ui.knowledge

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
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
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.DEPT_FA
import com.coinepro.hq.core.format.HqClock
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.actorFa
import com.coinepro.hq.core.format.jDate
import com.coinepro.hq.core.net.KnowledgeEntry
import com.coinepro.hq.core.net.KnowledgeIn
import com.coinepro.hq.core.net.Page
import com.coinepro.hq.core.net.Source
import com.coinepro.hq.core.net.VALID_DAYS
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
import com.coinepro.hq.designsystem.IconBtn
import com.coinepro.hq.designsystem.Md
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v14.HqSheet
import com.coinepro.hq.ui.v14.LabelPill
import com.coinepro.hq.ui.v16.ChipRow
import com.coinepro.hq.ui.v16.CompanyChips
import com.coinepro.hq.ui.v16.Labelled
import com.coinepro.hq.ui.v16.Notice
import com.coinepro.hq.ui.v16.prose
import com.coinepro.hq.ui.v17.CoMark
import com.coinepro.hq.ui.v17.FilterRow
import com.coinepro.hq.ui.v17.Heading
import com.coinepro.hq.ui.v17.KNOWLEDGE_KIND
import com.coinepro.hq.ui.v17.KNOWLEDGE_STATUS
import com.coinepro.hq.ui.v17.LAYER_FA
import com.coinepro.hq.ui.v17.REVIEW_CHECK
import com.coinepro.hq.ui.v17.REVIEW_VERDICT
import com.coinepro.hq.ui.v17.RefChip
import com.coinepro.hq.ui.v17.RefTone
import com.coinepro.hq.ui.v17.ScopeChips
import com.coinepro.hq.ui.v17.dayEnd
import com.coinepro.hq.ui.v17.daysFrom
import com.coinepro.hq.ui.v17.gov
import java.time.LocalDate

/** دانشنامه (contract §20.3): one store in four layers, every entry sourced and dated. [open0] opens one entry. */
@Composable
fun KnowledgeScreen(open0: String? = null) {
    val c = Divan.colors
    var company by rememberSaveable { mutableStateOf<String?>(null) }
    var layer by rememberSaveable { mutableStateOf<String?>(null) }
    var kind by rememberSaveable { mutableStateOf<String?>(null) }
    var status by rememberSaveable { mutableStateOf<String?>(null) }
    var text by rememberSaveable { mutableStateOf("") }
    var expired by rememberSaveable { mutableStateOf(false) }
    var pages by rememberSaveable { mutableIntStateOf(1) }
    var open by rememberSaveable { mutableStateOf(open0) }
    var edit by remember { mutableStateOf<KnowledgeEntry?>(null) }
    var create by remember { mutableStateOf(false) }
    val q = rememberQuery("knowledge:list:${layer.orEmpty()}:${company.orEmpty()}:${kind.orEmpty()}:${status.orEmpty()}:${text.trim()}:$expired:$pages", "knowledge") {
        // Pages one after another, as many as the owner asked for (each holds 50).
        var cursor: String? = null
        val all = mutableListOf<KnowledgeEntry>()
        repeat(pages) {
            val p = knowledge(layer, company, null, kind, status, text, expired, cursor)
            all += p.items; cursor = p.nextCursor
            if (cursor == null) return@rememberQuery Page(all, null)
        }
        Page(all, cursor)
    }
    val r = refresher(q)
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item {
            PageHeader("دانشنامه", eyebrow = "چهار لایه؛ هر ورودی با منبع و تاریخ انقضا") {
                HqButton("ورودی تازه", { create = true }, variant = BtnVariant.PRIMARY, icon = DivanIcon.ADD)
            }
        }
        item {
            Text(
                "هلدینگ برای همه، شرکت برای همان شرکت و هلدینگ، دپارتمان برای همان دپارتمان و مدیرعاملش. لایه‌ی کارمند همان حافظه‌ی خود اوست و فقط دیده میشود؛ مقاله‌های پشتیبانی هم این‌جا فقط دیده میشوند و ویرایششان از پشتیبانی است. ورودی منقضی به ایجنت‌ها نمیرسد و منبع پذیرفته نمیشود.",
                style = Divan.type.small, color = c.textSecondary,
            )
        }
        item {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                HqTextField(text, { text = it }, "جستجو در عنوان و متن…", Modifier.fillMaxWidth(), maxLength = 200)
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    HqSwitch(expired, { expired = it }, "نشان دادن منقضی‌ها")
                    Text("منقضی‌ها هم", style = Divan.type.caption, color = c.textSecondary)
                }
                ScopeChips(company, { company = it }, allLabel = "همه‌ی شرکت‌ها")
                FilterRow("همه‌ی لایه‌ها", layer, LAYER_FA.mapValues { it.value.fa }) { layer = it }
                FilterRow("همه‌ی نوع‌ها", kind, KNOWLEDGE_KIND) { kind = it }
                FilterRow("همه‌ی وضعیت‌ها", status, KNOWLEDGE_STATUS.mapValues { it.value.fa }) { status = it }
            }
        }
        val items = q.data?.items
        val expiring = items.orEmpty().filter { e -> e.status == "approved" && e.kind != "support" && (daysFrom(dayEnd(e.validUntil)) ?: 99) in 0..14 }
        if (expiring.isNotEmpty()) item { ExpiringCard(expiring) { open = it } }
        when {
            items == null && q.error != null -> item { ErrorBlock(q.error, { q.refresh() }) }
            items == null -> item { Skeleton(Modifier.fillMaxWidth().height(260.dp), radius = 16.dp) }
            items.isEmpty() -> item { Empty("ورودی‌ای پیدا نشد", icon = DivanIcon.KNOWLEDGE) }
            else -> {
                for (e in items) item(key = e.ref) { EntryCard(e) { open = e.ref } }
                if (q.data?.nextCursor != null) item { HqButton("بیشتر", { pages++ }, size = BtnSize.SM, loading = q.state.refreshing) }
            }
        }
    }
    open?.let { ref -> HqSheet({ open = null }, "دانشنامه", ref = ref) { EntryView(ref, onEdit = { e -> open = null; edit = e }, onRetired = { open = null }) } }
    if (create || edit != null) EntryEditor(edit) { create = false; edit = null }
}

/** «تا ۲۵ آذر ۱۴۰۵»، «۱۲ روز مانده»، «منقضی»: the expiry in words; under 14 days it warns (a review work item is already out). */
@Composable
private fun Expiry(e: KnowledgeEntry) {
    val c = Divan.colors
    val d = daysFrom(dayEnd(e.validUntil))
    val end = dayEnd(e.validUntil)
    val gone = e.status == "expired" || (d != null && d < 0)
    val soon = !gone && d != null && d <= 14
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        if (gone || soon) DIcon(DivanIcon.TIME, size = 12.dp, tint = c.warning)
        Text(
            if (gone) "منقضی از ${jDate(end)}" else "تا ${jDate(end, withYear = true)}" + if (soon) "، $d روز مانده" else "",
            style = Divan.type.micro, color = if (gone || soon) c.warning else c.textMuted,
        )
    }
}

@Composable
private fun EntryCard(e: KnowledgeEntry, onOpen: () -> Unit) {
    val c = Divan.colors
    val l = LAYER_FA[e.layer]
    HqCard(Modifier.fillMaxWidth().alpha(if (e.status == "retired" || e.status == "expired") 0.7f else 1f), onClick = onOpen) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            DIcon(l?.icon ?: DivanIcon.KNOWLEDGE, size = 14.dp, tint = c.textSecondary)
            Text(l?.fa ?: e.layer, style = Divan.type.micro, color = c.textSecondary)
            CoMark(e.company, ink = c.textMuted)
            e.department?.let { Text(DEPT_FA[it] ?: it, style = Divan.type.micro, color = c.textMuted) }
            Text("· ${KNOWLEDGE_KIND[e.kind] ?: e.kind}", style = Divan.type.micro, color = c.textMuted, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
            LabelPill(KNOWLEDGE_STATUS[e.status], e.status)
        }
        Spacer(Modifier.height(8.dp))
        Text(prose(e.titleFa), style = Divan.type.bodyStrong, color = c.textPrimary)
        Spacer(Modifier.height(4.dp))
        Text(e.bodyMd.replace(Regex("[*_`#>]"), "").replace(Regex("\\n+"), " "), style = Divan.type.small, color = c.textSecondary, maxLines = 2, overflow = TextOverflow.Ellipsis)
        Spacer(Modifier.height(8.dp))
        FlowRow(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalArrangement = Arrangement.spacedBy(4.dp), itemVerticalAlignment = Alignment.CenterVertically) {
            Fig("${e.ref}@${e.version}", style = Divan.type.figureSmall, color = c.textMuted)
            Expiry(e)
            Text("${e.sources.size} منبع", style = Divan.type.micro, color = c.textMuted)
            e.review?.let { rv -> REVIEW_VERDICT[rv.verdict]?.let { Pill("بازبینی: ${it.fa}", it.tone) } }
        }
    }
}

@Composable
private fun ExpiringCard(items: List<KnowledgeEntry>, onOpen: (String) -> Unit) {
    val c = Divan.colors
    HqCard(Modifier.fillMaxWidth(), color = c.softWarning) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            DIcon(DivanIcon.TIME, size = 16.dp, tint = c.warning)
            Text("${items.size} ورودی تا ۱۴ روز دیگر منقضی میشود", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
        }
        Spacer(Modifier.height(6.dp))
        for (e in items) Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(8.dp)).clickable(role = Role.Button) { onOpen(e.ref) }.padding(vertical = 4.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Fig(e.ref, style = Divan.type.figureSmall, color = c.textMuted)
                Text(prose(e.titleFa), style = Divan.type.small, color = c.textPrimary, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f, fill = false))
            }
            Expiry(e)
        }
    }
}

/** One entry: its text, sources, review, versions; a new version or retirement when the owner may write it. */
@Composable
fun EntryView(ref: String, onEdit: (KnowledgeEntry) -> Unit = {}, onRetired: () -> Unit = {}) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val q = rememberQuery("knowledge:one:$ref", "knowledge") { knowledgeEntry(ref) }
    val versions = rememberQuery("knowledge:versions:$ref", "knowledge") { knowledgeVersions(ref) }
    val action = rememberAction()
    var retire by remember { mutableStateOf(false) }
    val e = q.data
    if (e == null) { if (q.error != null) ErrorBlock(q.error, { q.refresh() }) else Skeleton(Modifier.fillMaxWidth().height(240.dp)); return }
    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Text(prose(e.titleFa), style = Divan.type.h2, color = c.textPrimary)
        Text("${LAYER_FA[e.layer]?.fa ?: e.layer} · ${KNOWLEDGE_KIND[e.kind] ?: e.kind}", style = Divan.type.caption, color = c.textMuted)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalArrangement = Arrangement.spacedBy(4.dp), itemVerticalAlignment = Alignment.CenterVertically) {
            LabelPill(KNOWLEDGE_STATUS[e.status], e.status)
            Fig("${e.ref}@${e.version}", style = Divan.type.figureSmall, color = c.textMuted)
            Expiry(e)
        }
        if (e.kind == "support") Notice(DivanIcon.INFO, c.tile, c.textMuted) {
            Text("مقاله‌ی دانشنامه‌ی پشتیبانی است: این‌جا فقط دیده میشود. ویرایش و مُهرش فقط از پشتیبانی است.", style = Divan.type.caption, color = c.textSecondary)
        }
        if (e.layer == "employee") Notice(DivanIcon.MEMORY, c.tile, c.textMuted) {
            Text(buildAnnotatedString { append("حافظه‌ی خود کارمند است ("); fig(e.createdBy?.code.orEmpty()); append(")؛ فقط خواندنی و کپی نمیشود.") }, style = Divan.type.caption, color = c.textSecondary)
        }
        Md(e.bodyMd)
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Heading("منبع‌ها")
            for (s in e.sources) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Fig(s.kind, style = Divan.type.figureSmall, color = c.textMuted)
                RefChip(s.ref, tone = RefTone.NEUTRAL)
                if (s.note.isNotBlank()) Text(prose(s.note), style = Divan.type.caption, color = c.textSecondary, modifier = Modifier.weight(1f))
            }
        }
        e.review?.let { rv ->
            Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Heading("بازبینی")
                    REVIEW_VERDICT[rv.verdict]?.let { Pill(it.fa, it.tone) }
                    Text("${actorFa(rv.by)}، ${jDate(rv.at)}", style = Divan.type.micro, color = c.textMuted)
                }
                FlowRow(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    for ((k, ok) in rv.checks) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                        DIcon(if (ok) DivanIcon.SEAL else DivanIcon.URGENT, size = 12.dp, tint = if (ok) c.positive else c.negative)
                        Text(REVIEW_CHECK[k] ?: k, style = Divan.type.caption, color = if (ok) c.positive else c.negative)
                    }
                }
                if (rv.notesMd.isNotBlank()) Md(rv.notesMd)
            }
        } ?: if (e.status == "in_review") Text("منتظر بازبینی ناظر یا ایمنی AI است (تزریق، رمز، تناقض با اساسنامه، اختیار).", style = Divan.type.caption, color = c.textMuted) else Unit
        FlowRow(horizontalArrangement = Arrangement.spacedBy(14.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text("نوشته‌ی ${actorFa(e.createdBy)}", style = Divan.type.caption, color = c.textMuted)
            e.approvedBy?.let { Text("تأیید ${actorFa(it)}", style = Divan.type.caption, color = c.textMuted) }
            Text("به‌روز ${jDate(e.updatedAt, withYear = true)}", style = Divan.type.caption, color = c.textMuted)
        }
        val vs = versions.data.orEmpty()
        if (vs.size > 1) Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Heading("نسخه‌ها")
            for (v in vs) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Fig("v${v.version}", Modifier.width(28.dp), style = Divan.type.figureSmall, color = c.textPrimary)
                Text(prose(v.titleFa), style = Divan.type.caption, color = c.textSecondary, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
                LabelPill(KNOWLEDGE_STATUS[v.status], v.status)
            }
        }
        if (!e.readOnly && e.status != "retired") Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            HqButton("نسخه‌ی تازه", { onEdit(e) }, Modifier.weight(1f), variant = BtnVariant.PRIMARY, icon = DivanIcon.EDIT)
            HqButton("بازنشسته", { retire = true }, variant = BtnVariant.DANGER)
        }
    }
    if (retire) AlertDialog(
        onDismissRequest = { retire = false },
        containerColor = c.overlay,
        title = { Text("بازنشسته کردن این ورودی", style = Divan.type.h3) },
        text = { Text("ورودی پاک نمیشود؛ فقط دیگر به ایجنت‌ها نمیرسد و به‌عنوان منبع پذیرفته نمیشود.", style = Divan.type.small, color = c.textSecondary) },
        confirmButton = {
            HqButton("بازنشسته کن", {
                action.gov(toasts) {
                    env.api.retireKnowledge(e.ref)
                    env.cache.invalidate("knowledge")
                    retire = false
                    toasts.info("بازنشسته شد؛ از جستجوی ایجنت‌ها بیرون رفت.")
                    onRetired()
                }
            }, variant = BtnVariant.DANGER, loading = action.busy)
        },
        dismissButton = { HqButton("انصراف", { retire = false }, variant = BtnVariant.GHOST) },
    )
}

private val KINDS = listOf("principle", "policy", "fact", "faq", "playbook")
private val SOURCE_KINDS = listOf("doc", "deliverable", "decision", "resolution", "work", "kpi", "charter", "support_kb", "url")

/** A new entry or a new version: at least one source and an expiry inside the kind's longest validity. */
@Composable
private fun EntryEditor(from: KnowledgeEntry?, onClose: () -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val action = rememberAction()
    val companies = rememberCompanies()
    val holding = companies.firstOrNull { it.kind == "holding" }?.code ?: "HQ"
    var layer by rememberSaveable { mutableStateOf(from?.layer?.takeIf { it != "employee" } ?: "company") }
    var company by rememberSaveable { mutableStateOf(from?.company) }
    var department by rememberSaveable { mutableStateOf(from?.department) }
    var kind by rememberSaveable { mutableStateOf(from?.kind?.takeIf { it != "support" } ?: "faq") }
    var title by rememberSaveable { mutableStateOf(from?.titleFa.orEmpty()) }
    var body by rememberSaveable { mutableStateOf(from?.bodyMd.orEmpty()) }
    var until by rememberSaveable { mutableStateOf(from?.validUntil.orEmpty()) }
    val sources = remember { mutableStateListOf<Source>().apply { addAll(from?.sources?.ifEmpty { null } ?: listOf(Source("doc", "", ""))) } }
    val co = if (layer == "holding") holding else company
    val today = HqClock.today()
    val max = today.plusDays(VALID_DAYS.getValue(kind).toLong())
    val untilDate = runCatching { LocalDate.parse(until.trim()) }.getOrNull()
    val untilOk = untilDate != null && untilDate > today && untilDate <= max
    val valid = co != null && title.isNotBlank() && body.isNotBlank() && sources.any { it.ref.isNotBlank() } && untilOk && (layer != "department" || department != null)
    val deps = if (layer == "department" && company != null) rememberQuery("departments:$company", "companies") { departments(company!!) }.data.orEmpty() else emptyList()
    HqSheet(onClose, if (from != null) "نسخه‌ی تازه‌ی ${from.ref}" else "ورودی تازه‌ی دانشنامه", sub = "هر ورودی دست‌کم یک منبع و تاریخ انقضا دارد.") {
        if (from == null) {
            Labelled("لایه") { ChipRow { for (l in listOf("holding", "company", "department")) FilterChip(LAYER_FA.getValue(l).fa, layer == l, { layer = l }) } }
            if (layer != "holding") Labelled("شرکت") { CompanyChips(company, { company = it; department = null }, all = false) }
            if (layer == "department" && company != null) Labelled("دپارتمان") {
                ChipRow { for (d in deps) FilterChip(d.nameFa, department == d.code, { department = d.code }) }
            }
        }
        Labelled("نوع") { ChipRow { for (k in KINDS) FilterChip(KNOWLEDGE_KIND.getValue(k), kind == k, { kind = k }) } }
        Labelled("عنوان") { HqTextField(title, { title = it }, "عنوان", Modifier.fillMaxWidth(), maxLength = 200) }
        Labelled("متن") { HqTextField(body, { body = it }, "متن", Modifier.fillMaxWidth(), singleLine = false, minLines = 6, maxLength = 20_000) }
        Labelled("منبع‌ها") {
            sources.forEachIndexed { i, s ->
                Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).border(1.dp, c.lineDivider, RoundedCornerShape(12.dp)).padding(10.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        // One tap moves the source to the next kind.
                        Box(
                            Modifier.height(36.dp).clip(RoundedCornerShape(8.dp)).border(1.dp, c.lineStrong, RoundedCornerShape(8.dp))
                                .clickable(role = Role.Button, onClickLabel = "نوع منبع") { sources[i] = s.copy(kind = SOURCE_KINDS[(SOURCE_KINDS.indexOf(s.kind) + 1) % SOURCE_KINDS.size]) }.padding(horizontal = 10.dp),
                            contentAlignment = Alignment.Center,
                        ) { Fig(s.kind, style = Divan.type.figureSmall, color = c.textSecondary) }
                        CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
                            HqTextField(s.ref, { sources[i] = s.copy(ref = it) }, "O-000031", Modifier.weight(1f), maxLength = 120, figure = true)
                        }
                        if (sources.size > 1) IconBtn(DivanIcon.CLOSE, "حذف منبع", { sources.removeAt(i) })
                    }
                    HqTextField(s.note, { sources[i] = s.copy(note = it) }, "یادداشت", Modifier.fillMaxWidth(), maxLength = 200)
                }
            }
            HqButton("منبع دیگر", { sources.add(Source("doc", "", "")) }, variant = BtnVariant.GHOST, size = BtnSize.SM, icon = DivanIcon.ADD)
        }
        Labelled("معتبر تا") {
            CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
                HqTextField(until, { until = it }, max.toString(), Modifier.fillMaxWidth(), maxLength = 10, figure = true)
            }
            Text(
                buildAnnotatedString {
                    append("حداکثر ${VALID_DAYS.getValue(kind)} روز برای «${KNOWLEDGE_KIND.getValue(kind)}» (تا "); fig(max.toString()); append("). چهارده روز پیش از انقضا یک کار بازبینی برای نگه‌دار لایه ساخته میشود.")
                },
                style = Divan.type.micro, color = if (until.isNotBlank() && !untilOk) c.negative else c.textMuted,
            )
        }
        HqButton("ثبت", {
            val cc = co ?: return@HqButton
            action.gov(toasts) {
                val b = KnowledgeIn(
                    layer, cc, if (layer == "department") department else null, kind, title.trim(), body.trim(),
                    sources.filter { it.ref.isNotBlank() }.map { Source(it.kind, it.ref.trim(), it.note.trim()) }, until.trim(),
                )
                val out = if (from != null) env.api.updateKnowledge(from.ref, b) else env.api.createKnowledge(b)
                env.cache.invalidate("knowledge")
                toasts.ok("ورودی ${out.ref}@${out.version} ثبت شد؛ نوشته‌ی تو با همین کار تأیید است.")
                onClose()
            }
        }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, size = BtnSize.LG, icon = DivanIcon.KNOWLEDGE, enabled = valid, loading = action.busy)
    }
}
