package com.coinepro.hq.ui.archive

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
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
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDirection
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.media.fileSize
import com.coinepro.hq.core.net.ArchiveRecord
import com.coinepro.hq.core.net.FieldDef
import com.coinepro.hq.core.net.PartyRole
import com.coinepro.hq.core.net.RecordFile
import com.coinepro.hq.core.net.RecordFilters
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.FigureFace
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v16.prose
import kotlinx.serialization.json.JsonElement

// Records as lists and forms (contract §23.1, §23.12), mirroring apps/web/src/components/v20/records.tsx.

// ------------------------------------------------------------------ search highlight --
/** The same deterministic normaliser the hub searches with (§23.9), one character at a time so a match maps back onto the snippet. */
private fun normChar(ch: Char): String = when {
    ch in 'ً'..'ْ' || ch == 'ٰ' || ch == 'ـ' -> ""
    ch == 'ي' || ch == 'ى' -> "ی"
    ch == 'ك' -> "ک"
    ch == 'ة' -> "ه"
    ch in "أإآ" -> "ا"
    ch == 'ؤ' -> "و"
    ch in "‌‏‎" -> " "
    ch in '۰'..'۹' -> (ch - '۰').toString()
    ch in '٠'..'٩' -> (ch - '٠').toString()
    else -> ch.lowercase()
}

fun normalise(s: String): String = s.map(::normChar).joinToString("").replace(Regex("\\s+"), " ")

/** The snippet with every query term marked, whatever letters or digits the text and the query were typed with. */
fun highlight(text: String, q: String, mark: SpanStyle, latin: Boolean = false): AnnotatedString {
    val terms = normalise(q).split(' ').filter { it.length >= 2 }
    val norm = StringBuilder()
    val at = ArrayList<Int>()
    text.forEachIndexed { i, ch -> for (n in normChar(ch)) { norm.append(n); at.add(i) } }
    val marks = ArrayList<Pair<Int, Int>>()
    for (t in terms) {
        var i = norm.indexOf(t)
        while (i >= 0) { marks.add(at[i] to at[i + t.length - 1] + 1); i = norm.indexOf(t, i + t.length) }
    }
    marks.sortBy { it.first }
    val marked = BooleanArray(text.length)
    var last = 0
    for ((s, e) in marks) if (s >= last) { for (i in s until e) marked[i] = true; last = e }
    // In a Persian line every Latin run (a ref, an invoice number, a year) is a figure, as prose() draws it; a Latin snippet is one.
    val runs = BooleanArray(text.length)
    if (latin) runs.fill(true) else for (r in LATIN_RUN.findAll(text)) {
        val end = r.range.first + r.value.trimEnd('.', ',', ':').length
        for (i in r.range.first until end) runs[i] = true
    }
    val figure = SpanStyle(fontFamily = FigureFace, fontFeatureSettings = "tnum")
    return buildAnnotatedString {
        var i = 0
        while (i < text.length) {
            val run = runs[i]
            var j = i
            while (j < text.length && runs[j] == run) j++
            if (run && !latin) append('⁦')
            var k = i
            while (k < j) {
                val on = marked[k]
                var n = k
                while (n < j && marked[n] == on) n++
                val style = when { run && on -> figure.merge(mark); run -> figure; on -> mark; else -> null }
                if (style != null) withStyle(style) { append(text.substring(k, n)) } else append(text.substring(k, n))
                k = n
            }
            if (run && !latin) append('⁩')
            i = j
        }
    }
}

/** A run of Latin in Persian text, as prose() finds it. */
private val LATIN_RUN = Regex("[A-Za-z0-9$+−][\\w.$%/:+−@-]*(?:[ \\t]+[A-Za-z0-9$][\\w.$%/:+−@-]*)*")

private val PERSIAN = Regex("[\\u0600-\\u06FF]")
fun isLatin(s: String) = !PERSIAN.containsMatchIn(s)

// ------------------------------------------------------------------ a record in a list --
@Composable
fun RecordRow(r: ArchiveRecord, m: ArchiveMaps, snippet: String? = null, q: String? = null, onOpen: (() -> Unit)? = null) {
    val c = Divan.colors
    val nav = LocalNav.current
    val mark = SpanStyle(background = c.softGold, color = c.textPrimary)
    Column(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).clickable(role = Role.Button) { onOpen?.invoke() ?: nav.go("archive/${r.ref}") }.padding(horizontal = 6.dp, vertical = 10.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            IconSquare(iconOf(m.cls(r.cls)?.icon ?: "deliverable"))
            Text(if (q != null) highlight(r.titleFa, q, mark) else prose(r.titleFa), Modifier.weight(1f), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, maxLines = 2, overflow = TextOverflow.Ellipsis)
            LevelPill(r.level, m)
        }
        FlowRow(Modifier.padding(start = 42.dp), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp), itemVerticalAlignment = Alignment.CenterVertically) {
            Fig(r.ref, style = Divan.type.figureSmall, color = c.textSecondary)
            ScopeTag(r.scope)
            ClassTag(r.cls, m)
            r.docDate?.let { Text(jDay(it), style = Divan.type.micro, color = c.textMuted) }
            if (r.state != "filed") StatePill(r.state)
            if (r.holds.isNotEmpty()) Pill("توقیف", Tone.NEG, icon = DivanIcon.LOCK)
            if (r.versions.size > 1) Text("${r.versions.size} نسخه", style = Divan.type.micro, color = c.textMuted)
        }
        if (!snippet.isNullOrBlank()) {
            val latin = isLatin(snippet)
            Text(
                highlight(snippet, q.orEmpty(), mark, latin), Modifier.fillMaxWidth().padding(start = 42.dp),
                style = (if (latin) Divan.type.figureSmall else Divan.type.caption).copy(textDirection = if (latin) TextDirection.Ltr else TextDirection.Rtl), color = c.textSecondary, maxLines = 3, overflow = TextOverflow.Ellipsis,
            )
        }
    }
}

// ------------------------------------------------------------------ the record form (intake, a draft, a correction) --
data class RecordDraft(val cls: String?, val titleFa: String, val metadata: Map<String, JsonElement>, val level: String?, val folder: String?)

fun draftOf(r: ArchiveRecord) = RecordDraft(r.cls, r.titleFa, r.metadata, r.level, r.folder)

/** The metadata to send: only the class's fields (a suggestion may carry keys of another class), nothing empty. */
fun metaFor(m: ArchiveMaps, d: RecordDraft): Map<String, JsonElement> {
    val keys = m.cls(d.cls)?.fields.orEmpty().map { it.key }.toSet()
    return d.metadata.filter { (k, v) -> k in keys && !emptyValue(v) }
}

/** Parties of a record, read from its party fields (the field's title is the role), then any other the suggestion named. */
fun partiesFor(m: ArchiveMaps, d: RecordDraft, extra: List<String> = emptyList()): List<PartyRole> {
    val out = ArrayList<PartyRole>()
    for (f in m.cls(d.cls)?.fields.orEmpty()) {
        val v = d.metadata[f.key].str
        if (f.type == "party" && v != null && out.none { it.party == v }) out += PartyRole(v, f.titleFa)
    }
    for (p in extra) if (out.none { it.party == p }) out += PartyRole(p, "طرف")
    return out
}

/** Class, title, metadata by the class's fields, level and folder: everything a record is filed with, typed by the schema. */
@Composable
fun RecordForm(scope: String, value: RecordDraft, onChange: (RecordDraft) -> Unit, errors: Map<String, String>, m: ArchiveMaps, lockClass: Boolean = false, hideLevel: Boolean = false) {
    val c = Divan.colors
    val cls = m.cls(value.cls)
    val me = metaErrors(errors)
    val fields: List<FieldDef> = cls?.fields.orEmpty().filter { it.status == "active" || !emptyValue(value.metadata[it.key]) }
    val classes = m.classes.filter { (it.status == "active" && it.inScope(scope)) || it.key == value.cls }
    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            FieldLabel("نوع سند")
            if (lockClass) ClassTag(value.cls, m, c.textPrimary)
            else Select(value.cls, classes.map { Opt(it.key, it.titleFa + if (it.status == "retired") " (بازنشسته)" else "") }, { k ->
                val nc = m.cls(k)
                onChange(value.copy(cls = k, level = nc?.defaultLevel ?: value.level, folder = m.defaultFolder(scope, k) ?: value.folder))
            }, "نوع سند", Modifier.fillMaxWidth(), error = errors["class"] != null)
            errors["class"]?.let { Text(it, style = Divan.type.caption, color = c.negative) }
        }
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            FieldLabel("عنوان")
            HqTextField(value.titleFa, { onChange(value.copy(titleFa = it)) }, "عنوان سند", Modifier.fillMaxWidth(), maxLength = 200)
            errors["title_fa"]?.let { Text(it, style = Divan.type.caption, color = c.negative) }
        }
        if (cls != null) for (f in fields) FieldInput(f, value.metadata[f.key], { v -> onChange(value.copy(metadata = if (v == null) value.metadata - f.key else value.metadata + (f.key to v))) }, m, scope, me[f.key])
        else Text("نوع سند را انتخاب کن تا فیلدهایش بیاید.", Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp), style = Divan.type.caption, color = c.textSecondary)
        if (!hideLevel) Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            FieldLabel("سطح")
            Select(value.level, m.levels.filter { it.status != "retired" }.map { Opt(it.key, it.titleFa) }, { onChange(value.copy(level = it)) }, "سطح", Modifier.fillMaxWidth(), error = errors["level"] != null)
        }
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            FieldLabel("پوشه")
            Select(
                value.folder, m.folders.filter { it.scope == scope && (it.status == "active" || it.ref == value.folder) }.map { Opt(it.ref, "— ".repeat((m.folderPath(it.ref).size - 1).coerceAtLeast(0)) + it.titleFa) },
                { onChange(value.copy(folder = it)) }, "پوشه", Modifier.fillMaxWidth(), nullable = true, none = "بی‌پوشه", error = errors["folder"] != null,
            )
            errors["folder"]?.let { Text(it, style = Divan.type.caption, color = c.negative) }
        }
    }
}

// ------------------------------------------------------------------ files as the hub read them --
@Composable
fun FileFacts(f: RecordFile) {
    val c = Divan.colors
    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(2.dp), itemVerticalAlignment = Alignment.CenterVertically) {
        Fig(fileSize(f.sizeBytes), style = Divan.type.figureSmall, color = c.textMuted)
        f.pages?.let { Text("$it صفحه", style = Divan.type.micro, color = c.textMuted) }
        Text(buildAnnotatedString {
            append(TEXT_STATE[f.textState] ?: f.textState)
            f.ocrConfidence?.let { append(" "); fig("${Math.round(it * 100)}%") }
        }, style = Divan.type.micro, color = if (f.textState == "failed") c.warning else c.textMuted)
        Fig(shaShort(f.sha256), style = Divan.type.figureSmall, color = c.textMuted)
    }
}

// ------------------------------------------------------------------ the home's blocks --
/** What expires soonest: the nearest open reminder of every record (a contract's end, a licence's or a domain's expiry, a review date). */
@Composable
fun ExpiringStrip(m: ArchiveMaps) {
    val c = Divan.colors
    val nav = LocalNav.current
    val q = rememberQuery("archive:records:expiring", "archive") { records(RecordFilters(expiringWithinDays = 365)) }
    val rows = q.data?.items.orEmpty().mapNotNull { r ->
        r.reminders.filter { it.state != "done" }.minByOrNull { it.at }?.let { Triple(r, it, daysTo(it.at)) }
    }.sortedBy { it.third }.take(8)
    if (q.data == null && q.error == null) return Skeleton(Modifier.fillMaxWidth().height(112.dp), radius = 14.dp)
    if (rows.isEmpty()) return
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("نزدیک‌ترین سررسیدها", Modifier.weight(1f), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
            Text("همه‌ی یادآورها", Modifier.clickable(role = Role.Button) { nav.go("archive-reminders") }, style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.goldInk)
        }
        com.coinepro.hq.designsystem.ScrollRow {
            for ((r, x, left) in rows) {
                val tone = when { left <= 7 -> c.negative; left <= 30 -> c.warning; else -> c.textSecondary }
                val f = m.cls(r.cls)?.fields?.firstOrNull { it.key == x.field }
                Column(
                    Modifier.width(212.dp).clip(RoundedCornerShape(14.dp)).background(c.card).clickable(role = Role.Button) { nav.go("archive/${r.ref}") }.padding(12.dp),
                    verticalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        DIcon(DivanIcon.TIME, size = 14.dp, tint = tone)
                        Text(daysLeftFa(left), style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = tone)
                    }
                    Text(prose(r.titleFa), style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, maxLines = 2, overflow = TextOverflow.Ellipsis)
                    Text(buildAnnotatedString { append((f?.titleFa ?: x.field) + ": "); append(jDay(x.at)) }, style = Divan.type.micro, color = c.textMuted, maxLines = 1)
                }
            }
        }
    }
}

/** The drafts waiting to be filed, each with the archivist's or the rules' suggestion. */
@Composable
fun DraftsBlock(scope: String?, m: ArchiveMaps) {
    val c = Divan.colors
    val nav = LocalNav.current
    val q = rememberQuery("archive:records:drafts:${scope ?: ""}", "archive") { records(RecordFilters(state = "draft", scope = scope)) }
    val xs = q.data?.items.orEmpty()
    if (q.data == null && q.error == null) return Skeleton(Modifier.fillMaxWidth().height(96.dp), radius = 14.dp)
    if (xs.isEmpty()) return
    Column(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(c.card).padding(horizontal = 10.dp, vertical = 12.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        Row(Modifier.padding(horizontal = 4.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            DIcon(DivanIcon.EDIT, size = 16.dp, tint = c.textPrimary)
            Text("منتظر ثبت", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
            Text("${xs.size} پیش‌نویس", style = Divan.type.caption, color = c.textMuted)
        }
        xs.forEachIndexed { i, r ->
            if (i > 0) HorizontalDivider(color = c.lineDivider)
            Column(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).clickable(role = Role.Button) { nav.go("archive/${r.ref}") }.padding(horizontal = 6.dp, vertical = 10.dp),
                verticalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(prose(r.titleFa), Modifier.weight(1f), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Fig(r.ref, style = Divan.type.figureSmall, color = c.textMuted)
                }
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(2.dp), itemVerticalAlignment = Alignment.CenterVertically) {
                    ScopeTag(r.scope)
                    Text("${r.current?.files?.size ?: 0} فایل", style = Divan.type.micro, color = c.textMuted)
                    Text(ago(r.createdAt), style = Divan.type.micro, color = c.textMuted)
                }
                if (r.suggestion != null) SuggestionLine(r.suggestion, m) else Text("بی‌پیشنهاد؛ بایگان هنوز نگاهش نکرده.", style = Divan.type.micro, color = c.textMuted)
            }
        }
    }
}

/** The last fixity run (§23.10): every stored file re-hashed daily; a failure is a data-loss alarm. */
@Composable
fun FixityLine() {
    val c = Divan.colors
    val nav = LocalNav.current
    val q = rememberQuery("archive:fixity", "archive", maxAgeMs = 600_000) { fixity() }
    val f = q.data ?: return
    FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp), itemVerticalAlignment = Alignment.CenterVertically) {
        if (f.failed.isNotEmpty()) Pill("${f.failed.size} فایل با hash خودش نمیخواند", Tone.NEG, icon = DivanIcon.URGENT) else Pill("سلامت فایل‌ها", Tone.POS, icon = DivanIcon.SEAL)
        Text(buildAnnotatedString {
            append("آخرین بررسی "); append(jStamp(f.at)); append("، ${f.checked} فایل دوباره hash شد" + if (f.failed.isEmpty()) "، همه درست." else ".")
        }, style = Divan.type.caption, color = c.textSecondary)
        for (r in f.failed) Fig(r, Modifier.clickable(role = Role.Button) { nav.go("archive/$r") }, style = Divan.type.figureSmall, color = c.negative)
    }
}

/** The party a filter names: who it is and the identifiers its kind defines (sensitive ones masked to the last four). */
@Composable
fun PartyCard(ref: String, m: ArchiveMaps, onClear: () -> Unit) {
    val c = Divan.colors
    val p = m.party(ref)
    val k = p?.let { m.partyKind(it.kind) }
    Row(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(c.card).padding(12.dp),
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Box(Modifier.size(40.dp).clip(CircleShape).background(c.tile), contentAlignment = Alignment.Center) {
            DIcon(if (p?.kind == "person") DivanIcon.OWNER else DivanIcon.COMPANIES, size = 20.dp, tint = c.goldInk)
        }
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(2.dp), itemVerticalAlignment = Alignment.CenterVertically) {
                Text(p?.nameFa ?: ref, style = Divan.type.body.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                p?.nameEn?.let { Fig(it, style = Divan.type.figureSmall, color = c.textMuted) }
                Fig(ref, style = Divan.type.figureSmall, color = c.textMuted)
                k?.let { Pill(it.titleFa, Tone.NEUTRAL) }
            }
            if (p != null && k != null) for (f in k.identifierFields.filter { p.identifiers[it.key] != null }) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(f.titleFa, style = Divan.type.micro, color = c.textMuted)
                FieldValue(f, p.identifiers[f.key], m)
            }
            FilterChip("برداشتن فیلتر", true, onClear)
        }
    }
}

@Composable
fun RecordsEmpty(filtered: Boolean) {
    Empty(
        if (filtered) "با این فیلترها سندی نیست" else "بایگانی هنوز خالی است", icon = DivanIcon.DELIVERABLE,
        body = if (filtered) "فیلتری را بردار یا جستجو را کوتاه‌تر کن." else "اولین سند را با «سند تازه» بیاور؛ اساسنامه و ایمیل‌های حقوقی خودشان می‌آیند.",
    )
}
