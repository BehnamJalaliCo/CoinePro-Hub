package com.coinepro.hq.ui.cartable

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
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
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.net.Decision
import com.coinepro.hq.core.net.DisposalCardPayload
import com.coinepro.hq.core.net.SchemaCardPayload
import com.coinepro.hq.core.net.payloadAs
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.archive.ArchiveMaps
import com.coinepro.hq.ui.archive.AttrKind
import com.coinepro.hq.ui.archive.ClassTag
import com.coinepro.hq.ui.archive.ImpactLine
import com.coinepro.hq.ui.archive.attrText
import com.coinepro.hq.ui.archive.jDay
import com.coinepro.hq.ui.archive.partUI
import com.coinepro.hq.ui.archive.rememberArchive
import com.coinepro.hq.ui.archive.rowKey
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v17.RefChip
import com.coinepro.hq.ui.v17.RefTone
import com.coinepro.hq.ui.v16.prose
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull

// The two cards of the archive (contract §23.11, §23.12), mirroring apps/web/src/components/v20/decision.tsx: `archive_schema` (the exact
// PUT an agent proposes, read against the current row; void once that row has changed) and `archive_disposal` (the week's batch of records
// whose retention ended; a held one is skipped and stays). Both are approved with the usual `decision.approve` step-up, target the ref.

private fun same(a: JsonElement?, b: JsonElement?) = (a ?: JsonNull) == (b ?: JsonNull)
private val JsonElement?.p: String? get() = (this as? JsonPrimitive)?.takeIf { it !is JsonNull }?.contentOrNull

/** The schema row an `archive_schema` card was written against, and whether the card is void (that row changed since). Null while the
 *  schema loads. */
private class SchemaCardState(val p: SchemaCardPayload, val current: JsonObject?, val void: Boolean?)

@Composable
private fun rememberSchemaCard(d: Decision): Pair<SchemaCardState, ArchiveMaps> {
    val arch = rememberArchive()
    val p = d.payloadAs(SchemaCardPayload.serializer()) ?: SchemaCardPayload()
    val schema = arch.m.schema ?: return SchemaCardState(p, null, null) to arch.m
    val rows = schema.rows(p.part)
    val ui = partUI(p.part, rows)
    val current = rows.firstOrNull { rowKey(ui, it) == p.key }
    val v = current?.get("version").p?.toIntOrNull()?.takeIf { it > 0 }
    return SchemaCardState(p, current, d.status == "pending" && v != p.baseVersion) to arch.m
}

@Composable
private fun Change(label: String, before: AnnotatedString?, after: AnnotatedString, isNew: Boolean) {
    val c = Divan.colors
    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(c.tile).padding(10.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(label, style = Divan.type.micro, color = c.textMuted)
        if (isNew || before == null) Text(after, style = Divan.type.caption, color = c.textPrimary)
        else FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(4.dp), itemVerticalAlignment = Alignment.CenterVertically) {
            Text(before, Modifier.clip(RoundedCornerShape(6.dp)).background(c.softNegative).padding(horizontal = 6.dp), style = Divan.type.caption.copy(textDecoration = TextDecoration.LineThrough), color = c.textSecondary)
            Text("←", style = Divan.type.caption, color = c.textMuted)
            Text(after, Modifier.clip(RoundedCornerShape(6.dp)).background(c.softPositive).padding(horizontal = 6.dp), style = Divan.type.caption, color = c.textPrimary)
        }
    }
}

private val FIELD_ATTRS = listOf("title_fa" to "عنوان", "required" to "لازم", "searchable" to "در جستجو", "sensitive" to "حساس", "options" to "گزینه‌ها", "ref_kinds" to "به", "currency" to "واحد", "help_fa" to "راهنما")

private fun fieldVal(v: JsonElement?): String = when {
    v == null || v is JsonNull || v.p == "" -> "—"
    v is JsonPrimitive && !v.isString && v.contentOrNull?.toBooleanStrictOrNull() != null -> if (v.content.toBoolean()) "بله" else "نه"
    v is JsonArray -> v.joinToString("، ") { x -> (x as? JsonObject)?.get("title_fa").p ?: x.p ?: x.toString() }
    else -> v.p ?: v.toString()
}

/** A class's (or a party kind's) fields, field by field: new, retired, changed, and the rest unchanged. */
@Composable
private fun FieldsDiff(before: List<JsonObject>, after: List<JsonObject>, m: ArchiveMaps) {
    val c = Divan.colors
    @Composable
    fun Tag(f: JsonObject) = FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(2.dp), itemVerticalAlignment = Alignment.CenterVertically) {
        Text(f["title_fa"].p.orEmpty(), style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
        Fig(f["key"].p.orEmpty(), style = Divan.type.figureSmall, color = c.textMuted)
        Text(buildAnnotatedString { append(m.typeFa(f["type"].p.orEmpty())); if (f["type"].p == "money" && f["currency"].p != null) { append(" · "); fig(f["currency"].p!!) } }, style = Divan.type.micro, color = c.textSecondary)
        if ((f["required"] as? JsonPrimitive)?.contentOrNull == "true") Pill("لازم", Tone.WARN)
    }
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        for (f in after) {
            val old = before.firstOrNull { it["key"].p == f["key"].p }
            when {
                old == null -> Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(c.softPositive).padding(10.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text("فیلد تازه", style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = c.positive)
                    Tag(f)
                    if ((f["options"] as? JsonArray)?.isNotEmpty() == true) Text("گزینه‌ها: ${fieldVal(f["options"])}", style = Divan.type.micro, color = c.textSecondary)
                }
                old["status"].p != "retired" && f["status"].p == "retired" -> Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(c.softNegative).padding(10.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text("بازنشسته میشود؛ مقدارهایش میمانند", style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = c.negative)
                    Tag(f)
                }
                else -> {
                    val diffs = FIELD_ATTRS.filter { (k, _) -> !same(old[k], f[k]) }
                    if (diffs.isNotEmpty()) Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(c.tile).padding(10.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Tag(f)
                        for ((k, fa) in diffs) Text(buildAnnotatedString {
                            append("$fa: ")
                            withStyle(SpanStyle(textDecoration = TextDecoration.LineThrough)) { append(fieldVal(old[k])) }
                            append(" ← ")
                            withStyle(SpanStyle(color = c.textPrimary)) { append(fieldVal(f[k])) }
                        }, style = Divan.type.micro, color = c.textSecondary)
                    }
                }
            }
        }
        val untouched = after.count { f -> val o = before.firstOrNull { it["key"].p == f["key"].p }; o != null && FIELD_ATTRS.all { (k, _) -> same(o[k], f[k]) } && o["status"].p == f["status"].p }
        if (before.isNotEmpty() && untouched > 0) Text("$untouched فیلد دیگر همان است.", style = Divan.type.micro, color = c.textMuted)
    }
}

/** `archive_schema`: the exact PUT, read against the current row; void when that row changed after the card was written. */
@Composable
private fun SchemaCard(d: Decision) {
    val c = Divan.colors
    val nav = LocalNav.current
    val companies = rememberCompanies()
    val (st, m) = rememberSchemaCard(d)
    if (st.void == null) return Skeleton(Modifier.fillMaxWidth().height(160.dp), radius = 14.dp)
    val p = st.p
    val current = st.current
    val rows = m.schema?.rows(p.part).orEmpty()
    val ui = partUI(p.part, rows)
    val body = p.body
    val isNew = current == null
    val view = JsonObject((current ?: JsonObject(emptyMap())) + body)
    fun empty(v: JsonElement?) = v == null || v is JsonNull || v.p == "" || (v is JsonArray && v.isEmpty())
    // A new row lists what it sets; a change lists what differs from the current row.
    val changed = ui.attrs.filter { a -> a.key in body && if (isNew) !empty(body[a.key]) else !same(current?.get(a.key), body[a.key]) }
    val simple = changed.filter { it.kind != AttrKind.FIELDS }
    val fields = changed.firstOrNull { it.kind == AttrKind.FIELDS }
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text("تغییر طرح بایگانی", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.goldInk)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp), itemVerticalAlignment = Alignment.CenterVertically) {
            Pill(ui.fa, Tone.NEUTRAL, icon = ui.icon)
            Fig(p.key, style = Divan.type.figureSmall, color = c.textPrimary)
            if (isNew) Pill("تازه", Tone.POS, icon = DivanIcon.ADD)
            else Text(buildAnnotatedString {
                if (p.baseVersion == null) { append("کارت برای کلید تازه نوشته شده؛ الان نسخه‌ی "); fig(current?.get("version").p ?: "—"); append(" هست") }
                else { append("نسخه‌ی پایه "); fig("${p.baseVersion}"); append("، الان "); fig(current?.get("version").p ?: "—") }
            }, style = Divan.type.micro, color = c.textSecondary)
            Text("در طرح بایگانی", Modifier.clickable(role = Role.Button) { nav.go("archive-settings/${p.part}" + if (current != null) "/${p.key}" else "") },
                style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.goldInk)
        }
        if (st.void == true) Row(
            Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.softNegative).padding(12.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            DIcon(DivanIcon.URGENT, Modifier.padding(top = 2.dp), size = 16.dp, tint = c.negative)
            Text(buildAnnotatedString {
                append("این کارت باطل است: ")
                if (p.baseVersion == null) append("این کلید بعد از نوشتن کارت ساخته شد")
                else { append("این بخش بعد از نوشتن کارت عوض شده (کارت روی نسخه‌ی "); fig("${p.baseVersion}"); append("، الان "); fig(current?.get("version").p ?: "—"); append(")") }
                append(". مُهر نمیخورد؛ بایگان پیشنهاد تازه مینویسد.")
            }, style = Divan.type.small, color = c.textPrimary)
        }
        for (a in simple) Change(a.fa, if (isNew) null else attrText(a, current?.get(a.key), m, current ?: view, companies), attrText(a, body[a.key], m, view, companies), isNew)
        if (fields != null) Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(fields.fa, style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
            FieldsDiff((current?.get(fields.key) as? JsonArray).orEmpty().mapNotNull { it as? JsonObject }, (body[fields.key] as? JsonArray).orEmpty().mapNotNull { it as? JsonObject }, m)
        }
        if (changed.isEmpty()) Text("با ردیف فعلی فرقی ندارد.", style = Divan.type.caption, color = c.textMuted)
        p.impact?.let { ImpactLine(it, p.part) }
        Text("با مُهر، دقیقاً همین بدنه اعمال میشود و نسخه‌ی تازه‌ای از این بخش ساخته میشود؛ چیزی حذف نمیشود. سندهای ثبت‌شده نسخه‌ی خودشان را نگه میدارند.", style = Divan.type.micro, color = c.textMuted)
    }
}

/** `archive_disposal`: the records the week's batch would destroy; a held one is skipped and stays. */
@Composable
private fun DisposalCard(d: Decision) {
    val c = Divan.colors
    val nav = LocalNav.current
    val arch = rememberArchive()
    val m = arch.m
    val list = d.payloadAs(DisposalCardPayload.serializer())?.records.orEmpty()
    // Each record as the reader may see it now: one above the reader's clearance or already disposed comes back as an error or a tombstone.
    val q = rememberQuery("archive:disposal:${d.ref}", "archive") { list.map { x -> runCatching { record(x.ref) }.getOrNull() } }
    val got = q.data
    val held = got.orEmpty().count { (it?.holds?.size ?: 0) > 0 }
    val gone = got.orEmpty().count { it?.state == "disposed" }
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text("سندهای این کارت", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.goldInk)
        Text(buildAnnotatedString {
            append("${list.size - held - gone} سند امحا میشود")
            if (held > 0) { append("؛ "); withStyle(SpanStyle(fontWeight = FontWeight.SemiBold, color = c.negative)) { append("$held سند توقیف دارد و رد میشود") } }
            if (gone > 0) append("؛ $gone سند پیش‌تر امحا شده")
            append(".")
        }, style = Divan.type.small, color = c.textSecondary)
        list.forEachIndexed { i, x ->
            val r = got?.getOrNull(i)
            val isHeld = (r?.holds?.size ?: 0) > 0
            val rule = m.schema?.retention?.firstOrNull { it.ref == x.retentionRule }
            Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(if (isHeld) c.softNegative else c.tile).padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(prose(x.titleFa), Modifier.weight(1f).clickable(role = Role.Button) { nav.go("archive/${x.ref}") }, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, maxLines = 2, overflow = TextOverflow.Ellipsis)
                    when {
                        got == null -> Skeleton(Modifier.width(56.dp).height(20.dp))
                        isHeld -> Pill("توقیف؛ رد میشود", Tone.NEG, icon = DivanIcon.LOCK)
                        r?.state == "disposed" -> Pill("امحا شد", Tone.NEUTRAL, icon = DivanIcon.CLOSE)
                        r == null -> Pill("دیده نمیشود", Tone.NEUTRAL)
                        else -> Pill("امحا", Tone.WARN, icon = DivanIcon.TIME)
                    }
                }
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp), itemVerticalAlignment = Alignment.CenterVertically) {
                    Fig(x.ref, style = Divan.type.figureSmall, color = c.textSecondary)
                    ClassTag(x.cls, m)
                    RefChip(x.retentionRule, note = rule?.titleFa, tone = RefTone.NEUTRAL)
                    x.triggerAt?.let { Text(buildAnnotatedString { append("آغاز "); append(jDay(it)) }, style = Divan.type.micro, color = c.textMuted) }
                    // The holds that keep it, each opening its page.
                    if (isHeld) for (h in r!!.holds) RefChip(h, tone = RefTone.NEUTRAL)
                }
            }
        }
        Text("با مُهر، فایل‌ها نابود میشوند و برای هر سند سنگ‌نشان میماند (شناسه، نوع، عنوان، تاریخ‌ها، hash و همین تصمیم). سندی که تا لحظه‌ی مُهر توقیف شود رد میشود و میماند.", style = Divan.type.micro, color = c.textMuted)
    }
}

/** The payload of a §23 card. */
@Composable
fun ArchiveDecisionPayload(d: Decision) {
    when (d.kind) {
        "archive_schema" -> SchemaCard(d)
        "archive_disposal" -> DisposalCard(d)
    }
}

/** The seal of an `archive_schema` card, only while the card is not void: a stale card is never sealed (§23.12). */
@Composable
fun SchemaSealGate(d: Decision, content: @Composable () -> Unit) {
    val c = Divan.colors
    val (st, _) = rememberSchemaCard(d)
    when (st.void) {
        null -> Skeleton(Modifier.size(96.dp), radius = 48.dp)
        true -> Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.Top) {
            DIcon(DivanIcon.URGENT, Modifier.padding(top = 3.dp), size = 16.dp, tint = c.negative)
            Text("این کارت باطل است و مُهر نمیخورد؛ ردش کن یا با یادداشت برگردان تا بایگان روی نسخه‌ی تازه بنویسد.", style = Divan.type.small, color = c.textSecondary, textAlign = TextAlign.Start)
        }
        false -> content()
    }
}
