package com.coinepro.hq.ui.archive

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.Party
import com.coinepro.hq.core.net.PartyIn
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
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.v14.HqSheet
import com.coinepro.hq.ui.v16.prose
import java.util.UUID
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

// طرح بایگانی (contract §23.10), mirroring apps/web/src/app/(app)/archive/settings/page.tsx: the open layer, one tab per part, every form
// drawn from the schema and its closed vocabulary; the parties registry and the system sources beside them.

private data class Tab(val key: String, val fa: String, val icon: DivanIcon)

/** The open layer. [tab0] and [open0] arrive from a ref (RR-…, RM-…, AU-…) or the cartable; [new0] opens a new row. */
@Composable
fun ArchiveSettingsScreen(tab0: String? = null, open0: String? = null, new0: Boolean = false) {
    val c = Divan.colors
    val arch = rememberArchive()
    val m = arch.m
    val parts = m.schema?.parts ?: com.coinepro.hq.core.net.SCHEMA_PARTS
    val tabs = parts.map { p -> partUI(p, m.schema?.rows(p).orEmpty()).let { Tab(p, it.fa, it.icon) } } +
        Tab("parties", "طرف‌ها", DivanIcon.COMPANIES) + Tab("sources", "منبع‌های خودکار", DivanIcon.SERVER)
    var tab by rememberSaveable { mutableStateOf(tab0?.takeIf { t -> t in parts || t == "parties" || t == "sources" } ?: "classes") }
    var sel by rememberSaveable { mutableStateOf(open0) }
    var isNew by remember { mutableStateOf(new0) }
    val r = refresher(arch.q)
    val rows = m.schema?.rows(tab).orEmpty()
    val ui = partUI(tab, rows)
    val editing = sel?.let { k -> rows.firstOrNull { rowKey(ui, it) == k } }
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item { PageHeader("طرح بایگانی", eyebrow = "بایگانی · لایه‌ی باز: همه‌چیزی که بایگانی را توصیف میکند داده است") }
        item {
            Text(
                "نوع سندها و فیلدهایشان، پوشه‌ها، سطح‌ها، مجوزها، نگهداری، یادآورها، طرف‌ها، پیوندها و خودکارها را خودت از همین‌جا عوض میکنی، بی‌انتشار تازه. هر ذخیره اول اثرش را نشان میدهد، بعد اثر انگشت میخواهد. هیچ چیزی حذف نمیشود؛ فقط بازنشسته. ایجنت‌ها فقط پیشنهاد میدهند (کارت «تغییر طرح بایگانی»).",
                style = Divan.type.small, color = c.textSecondary,
            )
        }
        item {
            // The tab it opened on is brought into view (a ref chip or the cartable may open one far along the row).
            val strip = rememberLazyListState()
            val at = tabs.indexOfFirst { it.key == tab }
            LaunchedEffect(Unit) { if (at > 1) strip.scrollToItem(at - 1) }
            LazyRow(Modifier.fillMaxWidth(), state = strip, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                items(tabs.size) { i ->
                    val t = tabs[i]
                    val on = t.key == tab
                    Row(
                        Modifier.height(36.dp).clip(CircleShape).background(if (on) c.softGold else androidx.compose.ui.graphics.Color.Transparent)
                            .border(1.dp, if (on) c.lineTahrir else c.lineStrong, CircleShape).clickable(role = Role.Tab) { tab = t.key; sel = null; isNew = false }.padding(horizontal = 14.dp),
                        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp),
                    ) {
                        DIcon(t.icon, size = 15.dp, tint = if (on) c.goldInk else c.textSecondary)
                        Text(t.fa, style = Divan.type.small.copy(fontWeight = if (on) FontWeight.SemiBold else FontWeight.Normal), color = if (on) c.goldInk else c.textSecondary, maxLines = 1)
                    }
                }
            }
        }
        item {
            when {
                arch.q.data == null && arch.q.error != null -> ErrorBlock(arch.q.error, { arch.q.refresh() })
                arch.q.data == null -> Skeleton(Modifier.fillMaxWidth().height(260.dp), radius = 16.dp)
                tab == "sources" -> SourcesTab()
                tab == "parties" -> PartiesTab(m, sel) { sel = it }
                else -> PartRows(tab, ui, rows, m, { row -> if (row == null) { isNew = true; sel = null } else { sel = rowKey(ui, row); isNew = false } })
            }
        }
    }
    if (m.schema != null && tab != "sources" && tab != "parties" && (editing != null || isNew)) {
        val title = editing?.let { it["title_fa"].prim ?: subjectFa(it["subject"]) } ?: "${ui.fa}: تازه"
        val k = editing?.let { rowKey(ui, it) }
        val v = editing?.get("version").int
        HqSheet({ sel = null; isNew = false }, title, sub = ui.note, ref = k?.let { if (v != null) "$it · v$v" else it }) {
            // A row changed on the hub (a newer version) opens fresh.
            androidx.compose.runtime.key("$tab:${sel ?: "new"}:${v ?: ""}") {
                RowEditorContent(tab, ui, editing, { sel = null; isNew = false })
            }
        }
    }
}

@Composable
private fun PartRows(part: String, ui: PartUI, rows: List<JsonObject>, m: ArchiveMaps, open: (JsonObject?) -> Unit) {
    val c = Divan.colors
    val companies = rememberCompanies()
    val sorted = rows.sortedBy { if (it["status"].prim == "retired") 1 else 0 }
    // The two attributes after the title say most about a row when the part has no summary of its own.
    val shown = ui.attrs.filter { it.key != "title_fa" && it.kind !in setOf(AttrKind.FIELDS, AttrKind.WHEN, AttrKind.DO, AttrKind.JSON) }.take(2)
    HqCard(Modifier.fillMaxWidth(), padding = PaddingValues(8.dp)) {
        Row(Modifier.padding(horizontal = 6.dp, vertical = 4.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(ui.note, Modifier.weight(1f), style = Divan.type.micro, color = c.textMuted)
            HqButton("تازه", { open(null) }, size = BtnSize.SM, icon = DivanIcon.ADD)
        }
        if (sorted.isEmpty()) Empty("هنوز چیزی نیست", icon = ui.icon)
        sorted.forEachIndexed { i, r ->
            if (i > 0) HorizontalDivider(color = c.lineDivider)
            val k = rowKey(ui, r)
            val retired = r["status"].prim == "retired"
            val title = when (part) {
                "clearance" -> subjectFa(r["subject"])
                "reminders" -> "${m.cls(r["class"].prim)?.titleFa ?: r["class"].prim}: ${m.cls(r["class"].prim)?.fields?.firstOrNull { it.key == r["field"].prim }?.titleFa ?: r["field"].prim}"
                else -> r["title_fa"].prim ?: k
            }
            Column(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).clickable(role = Role.Button) { open(r) }.alpha(if (retired) 0.6f else 1f).padding(horizontal = 6.dp, vertical = 10.dp),
                verticalArrangement = Arrangement.spacedBy(4.dp),
            ) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(title, Modifier.weight(1f), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    if (retired) Pill("بازنشسته", Tone.NEUTRAL)
                    ui.usage?.invoke(r)?.let { Text(it, style = Divan.type.micro, color = c.textMuted) }
                }
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(2.dp), itemVerticalAlignment = Alignment.CenterVertically) {
                    Fig(k + (r["version"].int?.let { " · v$it" } ?: ""), style = Divan.type.figureSmall, color = c.textMuted)
                    val sub = ui.sub
                    if (sub != null) Text(sub(r, m, companies), style = Divan.type.micro, color = c.textMuted, maxLines = 2, overflow = TextOverflow.Ellipsis)
                    else for (a in shown) Text(buildAnnotatedString { append(a.fa + ": "); append(attrText(a, r[a.key], m, r, companies)) }, style = Divan.type.micro, color = c.textMuted, maxLines = 1)
                }
            }
        }
    }
}

/** What the hub files by itself (§23.8): the list is the closed vocabulary; switching each one on or off is the owner's. */
@Composable
private fun SourcesTab() {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val arch = rememberArchive()
    val action = rememberAction()
    val q = rememberQuery("archive:sources", "archive") { archiveSources() }
    HqCard(Modifier.fillMaxWidth(), padding = PaddingValues(8.dp)) {
        Text("آنچه هاب خودش بایگانی میکند، هر کدام ثبت‌شده با نوع سند خودش و منبع «خودکار». فهرست منبع‌ها واژگان بسته است؛ روشن یا خاموش کردنش با توست.",
            Modifier.padding(horizontal = 6.dp, vertical = 4.dp), style = Divan.type.micro, color = c.textMuted)
        val xs = q.data
        when {
            xs == null && q.error != null -> ErrorBlock(q.error, { q.refresh() })
            xs == null -> Skeleton(Modifier.fillMaxWidth().height(200.dp), radius = 12.dp)
            else -> xs.forEachIndexed { i, s ->
                if (i > 0) HorizontalDivider(color = c.lineDivider)
                Row(Modifier.fillMaxWidth().padding(horizontal = 6.dp, vertical = 10.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Text(prose(s.titleFa), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(2.dp), itemVerticalAlignment = Alignment.CenterVertically) {
                            Fig(s.key, style = Divan.type.figureSmall, color = c.textMuted)
                            ClassTag(s.cls, arch.m)
                            Text(if (s.filed > 0) "${s.filed} سند بایگانی کرده" else "هنوز سندی نیامده", style = Divan.type.micro, color = c.textMuted)
                            s.lastAt?.let { Text(buildAnnotatedString { append("آخرین: "); append(jStamp(it)) }, style = Divan.type.micro, color = c.textMuted) }
                        }
                        s.noteFa?.let { Text(com.coinepro.hq.ui.v16.prose(it), style = Divan.type.caption, color = c.textSecondary) }
                    }
                    HqSwitch(s.enabled, { on ->
                        action.archive(toasts) {
                            q.set(env.api.setSources(mapOf(s.key to on)))
                            env.cache.invalidate("archive")
                            toasts.info(if (on) "روشن شد؛ از این به بعد خودش بایگانی میکند." else "خاموش شد؛ سندهای قبلی میمانند.")
                        }
                    }, s.titleFa, enabled = !action.busy)
                }
            }
        }
    }
}

/** The parties registry: a document is tied to its parties, and the rules find a known party in the text. */
@Composable
private fun PartiesTab(m: ArchiveMaps, sel: String?, onOpen: (String?) -> Unit) {
    val c = Divan.colors
    val nav = LocalNav.current
    val q = rememberQuery("archive:parties", "archive") { parties() }
    var making by remember { mutableStateOf(false) }
    val xs = q.data.orEmpty().sortedBy { if (it.status == "retired") 1 else 0 }
    val open = sel?.let { s -> xs.firstOrNull { it.ref == s } }
    HqCard(Modifier.fillMaxWidth(), padding = PaddingValues(8.dp)) {
        Row(Modifier.padding(horizontal = 6.dp, vertical = 4.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("رجیستری طرف‌ها: هر سند به طرف‌هایش وصل است و قاعده‌ها طرف شناخته را از متن پیدا میکنند. شناسه‌های حساس فقط تا چهار رقم آخر نشان داده میشوند.",
                Modifier.weight(1f), style = Divan.type.micro, color = c.textMuted)
            HqButton("طرف تازه", { making = true }, size = BtnSize.SM, icon = DivanIcon.ADD)
        }
        when {
            q.data == null && q.error != null -> ErrorBlock(q.error, { q.refresh() })
            q.data == null -> Skeleton(Modifier.fillMaxWidth().height(200.dp), radius = 12.dp)
            xs.isEmpty() -> Empty("طرفی نیست", icon = DivanIcon.COMPANIES)
            else -> xs.forEachIndexed { i, p ->
                if (i > 0) HorizontalDivider(color = c.lineDivider)
                val k = m.partyKind(p.kind)
                Row(Modifier.fillMaxWidth().alpha(if (p.status == "retired") 0.6f else 1f).padding(horizontal = 6.dp, vertical = 10.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Column(Modifier.weight(1f).clickable(role = Role.Button) { onOpen(p.ref) }, verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(2.dp), itemVerticalAlignment = Alignment.CenterVertically) {
                            Text(p.nameFa, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                            p.nameEn?.let { Fig(it, style = Divan.type.figureSmall, color = c.textMuted) }
                            if (p.status == "retired") Pill("بازنشسته", Tone.NEUTRAL)
                        }
                        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(2.dp), itemVerticalAlignment = Alignment.CenterVertically) {
                            Fig(p.ref, style = Divan.type.figureSmall, color = c.textMuted)
                            Text(k?.titleFa ?: p.kind, style = Divan.type.micro, color = c.textMuted)
                            Fig(p.scopes.joinToString(" · "), style = Divan.type.figureSmall, color = c.textMuted)
                            for (f in k?.identifierFields.orEmpty().filter { p.identifiers[it.key] != null }.take(2)) {
                                Text(buildAnnotatedString { append(f.titleFa + ": "); fig(plainValue(f, p.identifiers[f.key], m)) }, style = Divan.type.micro, color = c.textMuted, maxLines = 1)
                            }
                        }
                    }
                    if (p.records > 0) Text("${p.records} سند", Modifier.clickable(role = Role.Button) { nav.go("archive-in/party/${p.ref}") }, style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.goldInk)
                }
            }
        }
    }
    if (open != null) HqSheet({ onOpen(null) }, open.nameFa, ref = open.ref) {
        androidx.compose.runtime.key("${open.ref}:${open.version ?: 1}") { PartyContent(open, m) { onOpen(null) } }
    }
    if (making) HqSheet({ making = false }, "طرف تازه", sub = "صرافی، تأمین‌کننده، بانک، نهاد دولتی یا شخص؛ شناسه‌ها طبق نوعش.") { PartyContent(null, m) { making = false } }
}

/** One party of the registry: its kind decides which identifiers it has (the kind's fields, typed). No passkey: the registry is data the
 *  archivist keeps too; a party is retired, never deleted. */
@Composable
fun PartyContent(p: Party?, m: ArchiveMaps, onClose: () -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val companies = rememberCompanies()
    val action = rememberAction()
    val kinds = m.schema?.partyKinds.orEmpty().filter { it.status != "retired" || it.key == p?.kind }
    var kind by remember { mutableStateOf(p?.kind ?: kinds.firstOrNull()?.key ?: "other") }
    var nameFa by remember { mutableStateOf(p?.nameFa.orEmpty()) }
    var nameEn by remember { mutableStateOf(p?.nameEn.orEmpty()) }
    var ids by remember { mutableStateOf(p?.identifiers.orEmpty()) }
    var scopes by remember { mutableStateOf(p?.scopes.orEmpty()) }
    var key by remember { mutableStateOf(UUID.randomUUID().toString()) }
    var errors by remember { mutableStateOf<Map<String, String>>(emptyMap()) }
    var failure by remember { mutableStateOf<ApiException?>(null) }
    val k = m.partyKind(kind)
    val fields = k?.identifierFields.orEmpty().filter { it.status != "retired" || ids[it.key] != null }
    val ie = metaErrors(errors)
    fun body(): PartyIn = PartyIn(kind, nameFa.trim(), nameEn.trim().ifEmpty { null }, ids.filter { (key2, v) -> !emptyValue(v) && fields.any { it.key == key2 } }, scopes)
    fun save(status: String? = null) {
        errors = emptyMap(); failure = null
        action.run(onError = { e -> if (e.status != 0) key = UUID.randomUUID().toString(); errors = e.fields; failure = e }) {
            if (p != null) {
                val b: JsonObject = if (status != null) buildJsonObject { put("status", status) }
                else com.coinepro.hq.core.net.Api.jsonBody.encodeToJsonElement(PartyIn.serializer(), body()) as JsonObject
                env.api.patchParty(p, b)
            } else env.api.createParty(body(), key)
            env.cache.invalidate("archive")
            toasts.info(if (status == "retired") "طرف بازنشسته شد؛ سندهایش میمانند." else "رجیستری طرف‌ها ذخیره شد.")
            onClose()
        }
    }
    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            FieldLabel("نوع")
            Select(kind, kinds.map { Opt(it.key, it.titleFa) }, { kind = it ?: kind }, "نوع طرف", Modifier.fillMaxWidth(), error = errors["kind"] != null)
        }
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            FieldLabel("نام فارسی")
            HqTextField(nameFa, { nameFa = it }, "نام فارسی", Modifier.fillMaxWidth(), maxLength = 160)
            errors["name_fa"]?.let { Text(it, style = Divan.type.caption, color = c.negative) }
        }
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            FieldLabel("نام لاتین")
            HqTextField(nameEn, { nameEn = it }, "Name", Modifier.fillMaxWidth(), maxLength = 160, figure = true)
        }
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            FieldLabel("برای کدام دامنه‌ها")
            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                for (co in companies) FilterChip(co.nameFa ?: co.code, co.code in scopes, { scopes = if (co.code in scopes) scopes - co.code else scopes + co.code })
            }
        }
        for (f in fields) FieldInput(f, ids[f.key], { v -> ids = if (v == null) ids - f.key else ids + (f.key to v) }, m, null, ie[f.key])
        ErrorLine(failure)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            HqButton("ذخیره", { save() }, variant = BtnVariant.PRIMARY, enabled = nameFa.isNotBlank(), loading = action.busy)
            HqButton("انصراف", onClose, variant = BtnVariant.GHOST)
            if (p != null && p.status != "retired") HqButton("بازنشسته کن", { save("retired") }, variant = BtnVariant.DANGER, size = BtnSize.SM, icon = DivanIcon.PAUSE)
        }
    }
}
