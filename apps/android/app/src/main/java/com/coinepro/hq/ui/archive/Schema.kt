package com.coinepro.hq.ui.archive

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.Company
import com.coinepro.hq.core.net.Impact
import com.coinepro.hq.core.net.SchemaResult
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqSwitch
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.SegOption
import com.coinepro.hq.designsystem.Segmented
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.activity
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.v16.Chip
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

// The open layer (contract §23.2–§23.10, §23.12), mirroring apps/web/src/components/v20/schema.tsx. Every editor below is drawn from rows
// of data: an attribute's kind picks the input, its source picks the options from the schema the server sent (`GET /archive/schema`, its
// `vocab` included). A new value in the closed vocabulary (a field type, an event, an action, a currency) appears in the editors without a
// release; a new part of the schema gets the generic editor (its attributes read off its rows).

enum class AttrKind { TEXT, INT, BOOL, SELECT, MULTI, FIELDS, KEEP, TRIGGER, LEAD_DAYS, TO, WHEN, DO, SCOPES, GRANTS, SUBJECT, COLOR, JSON, LIST }
enum class Source { LEVELS, FOLDERS, CLASSES, RETENTION, LINK_KINDS, PARTY_KINDS, EVENTS, ACTIONS, OPS, REF_KINDS, CURRENCIES, MIMES, COMPANIES, THEN, CHANNELS, DATE_FIELDS, REF_FIELDS, SCOPE_FOLDERS, ICONS }

data class Attr(
    val key: String, val fa: String, val kind: AttrKind, val source: Source? = null, val help: String? = null, val nullable: Boolean = false,
    val locked: ((JsonObject, Boolean) -> String?)? = null,
)

/** How a part is shown and edited: `by` is what names a row (key, ref or subject). */
class PartUI(
    val fa: String, val icon: DivanIcon, val note: String, val by: String, val attrs: List<Attr>, val retire: Boolean,
    val blank: (ArchiveMaps) -> JsonObject,
    val usage: ((JsonObject) -> String?)? = null,
    val sub: ((JsonObject, ArchiveMaps, List<Company>) -> AnnotatedString)? = null,
)

private fun used(r: JsonObject) = r["records"].int ?: 0
private fun usedNote(r: JsonObject) = used(r).takeIf { it > 0 }?.let { "$it سند" }
private val ROLES = listOf("archivist", "legal_counsel", "ceo", "manager", "advisor", "overseer", "revenue_analyst", "support_lead")

fun subjectFa(s: JsonElement?): String {
    val o = s.obj
    val kind = o?.get("kind").prim ?: s.prim?.substringBefore(':') ?: "role"
    val ref = o?.get("ref").prim ?: s.prim?.substringAfter(':', "") ?: ""
    return if (kind == "role") archRoleFa(ref) else ref
}

private fun scopeFa(s: String, companies: List<Company>) = when (s) { "own" -> "شرکت خودش"; "all" -> "همه‌ی دامنه‌ها"; else -> companies.firstOrNull { it.code == s }?.nameFa ?: s }

fun keepFa(k: JsonElement?): String = when {
    k.prim == "permanent" -> "دائمی"
    k is JsonObject -> listOfNotNull(k["years"].int?.takeIf { it > 0 }?.let { "$it سال" }, k["months"].int?.takeIf { it > 0 }?.let { "$it ماه" }).joinToString(" و ").ifEmpty { "—" }
    else -> "—"
}

fun triggerFa(t: JsonElement?, m: ArchiveMaps): String {
    val s = t.prim.orEmpty()
    return when {
        s == "filed" -> "ثبت سند"
        s == "case_closed" -> "بسته شدن پرونده"
        s == "superseded" -> "جایگزین شدن"
        s.startsWith("field:") -> s.removePrefix("field:").let { k -> "فیلد «${m.classes.flatMap { it.fields }.firstOrNull { it.key == k }?.titleFa ?: k}»" }
        else -> s
    }
}

private fun figText(s: String) = buildAnnotatedString { fig(s) }

val PART_UI: Map<String, PartUI> = linkedMapOf(
    "classes" to PartUI(
        "نوع سندها", DivanIcon.REPORT, "هر نوع سند و فیلدهایش؛ تغییر یک نسخه‌ی تازه میسازد و سندها نسخه‌ی خودشان را نگه میدارند.", "key",
        listOf(
            Attr("title_fa", "عنوان", AttrKind.TEXT),
            Attr("parent", "زیرنوعِ", AttrKind.SELECT, Source.CLASSES, nullable = true),
            Attr("scopes", "برای", AttrKind.SCOPES),
            Attr("icon", "نشانه", AttrKind.SELECT, Source.ICONS),
            Attr("default_level", "سطح پیش‌فرض", AttrKind.SELECT, Source.LEVELS),
            Attr("default_folder", "پوشه‌ی پیش‌فرض", AttrKind.SELECT, Source.FOLDERS, nullable = true),
            Attr("retention", "قاعده‌ی نگهداری", AttrKind.SELECT, Source.RETENTION, nullable = true),
            Attr("required_files", "کمترین تعداد فایل", AttrKind.INT),
            Attr("ocr", "OCR روی اسکن‌ها", AttrKind.BOOL),
            Attr("allowed_mime", "نوع فایل‌های مجاز", AttrKind.MULTI, Source.MIMES),
            Attr("fields", "فیلدها", AttrKind.FIELDS),
            Attr("reminder_fields", "فیلدهای یادآور", AttrKind.MULTI, Source.DATE_FIELDS),
            Attr("auto_link", "پیوند خودکار", AttrKind.LIST, Source.REF_FIELDS),
        ),
        true,
        { m ->
            jobj(
                "key" to JsonPrimitive(""), "title_fa" to JsonPrimitive(""), "parent" to JsonNull, "scopes" to JsonPrimitive("all"), "icon" to JsonPrimitive("report"),
                "default_level" to jstr(m.levels.firstOrNull { it.key == "internal" }?.key ?: m.levels.firstOrNull()?.key ?: ""), "default_folder" to JsonNull,
                "fields" to JsonArray(emptyList()), "required_files" to JsonPrimitive(1), "allowed_mime" to jarr(listOf("application/pdf")), "ocr" to JsonPrimitive(true),
                "retention" to JsonNull, "reminder_fields" to JsonArray(emptyList()), "auto_link" to JsonArray(emptyList()),
            )
        },
        usage = ::usedNote,
        sub = { r, _, _ -> AnnotatedString("${r["fields"].arr?.size ?: 0} فیلد") },
    ),
    "folders" to PartUI(
        "طرح پوشه‌ها", DivanIcon.DELIVERABLE, "درخت پوشه‌های هر دامنه؛ اولین پوشه‌ای که نوع سند را بپذیرد پیش‌فرض آن نوع است.", "ref",
        listOf(
            Attr("title_fa", "عنوان", AttrKind.TEXT),
            Attr("scope", "دامنه", AttrKind.SELECT, Source.COMPANIES, locked = { _, saved -> if (saved) "دامنه‌ی پوشه بعد از ساخت عوض نمیشود" else null }),
            Attr("parent", "زیرپوشه‌ی", AttrKind.SELECT, Source.SCOPE_FOLDERS, nullable = true),
            Attr("classes", "نوع سندهایی که میپذیرد", AttrKind.MULTI, Source.CLASSES),
            Attr("default_level", "کمترین سطح", AttrKind.SELECT, Source.LEVELS, nullable = true),
            Attr("order", "ترتیب", AttrKind.INT),
        ),
        true,
        { jobj("title_fa" to JsonPrimitive(""), "scope" to JsonPrimitive("HQ"), "parent" to JsonNull, "classes" to JsonArray(emptyList()), "default_level" to JsonNull, "order" to JsonPrimitive(0)) },
        usage = ::usedNote,
        sub = { r, m, _ -> buildAnnotatedString { fig(r["scope"].prim.orEmpty()); r["parent"].prim?.let { append(" · زیر " + (m.folder(it)?.titleFa ?: it)) } } },
    ),
    "levels" to PartUI(
        "سطح‌ها", DivanIcon.LOCK, "سطح دسترسی هر سند؛ رتبه‌ی سطحی که سند دارد دیگر عوض نمیشود. سطح تازه را با رتبه‌ای میان دو سطح بساز.", "key",
        listOf(
            Attr("title_fa", "عنوان", AttrKind.TEXT),
            Attr("rank", "رتبه", AttrKind.INT, help = "بزرگ‌تر یعنی محرمانه‌تر", locked = { r, _ -> if (used(r) > 0) "رتبه‌ی سطحی که ${used(r)} سند دارد عوض نمیشود" else null }),
            Attr("color_index", "رنگ", AttrKind.COLOR),
            Attr("watermark", "ته‌نقش روی هر نمایش", AttrKind.BOOL),
            Attr("encrypt", "رمزگذاری با کلید OpenBao", AttrKind.BOOL),
            Attr("step_up_to_view", "دیدن با اثر انگشت", AttrKind.BOOL),
            Attr("agents_max", "سقف مجوز ایجنت‌ها", AttrKind.BOOL, help = "هیچ ایجنتی بالاتر از این سطح مجوز نمیگیرد"),
        ),
        true,
        { m ->
            jobj(
                "key" to JsonPrimitive(""), "title_fa" to JsonPrimitive(""), "rank" to JsonPrimitive((m.levels.lastOrNull()?.rank ?: 0) + 5), "color_index" to JsonPrimitive(4),
                "watermark" to JsonPrimitive(false), "encrypt" to JsonPrimitive(false), "step_up_to_view" to JsonPrimitive(false), "agents_max" to JsonPrimitive(false),
            )
        },
        usage = ::usedNote,
        sub = { r, _, _ ->
            buildAnnotatedString {
                append("رتبه‌ی "); fig(r["rank"].prim.orEmpty())
                if (r["watermark"].bool == true) append("، ته‌نقش"); if (r["encrypt"].bool == true) append("، رمزگذاری")
                if (r["step_up_to_view"].bool == true) append("، اثر انگشت"); if (r["agents_max"].bool == true) append("، سقف ایجنت‌ها")
            }
        },
    ),
    "clearance" to PartUI(
        "مجوز دیدن", DivanIcon.OWNER, "هر نقش یا کارمند تا چه سطحی در کدام دامنه میبیند؛ تو همه چیز را میبینی. ذخیره با اثر انگشت (archive.clearance).", "subject",
        listOf(
            Attr("subject", "برای", AttrKind.SUBJECT, locked = { _, saved -> if (saved) "برای کس دیگر، ردیف تازه بساز" else null }),
            Attr("grants", "مجوزها", AttrKind.GRANTS),
            Attr("metadata_level", "مشخصات سندهایی که خودش ثبت میکند تا سطح", AttrKind.SELECT, Source.LEVELS, nullable = true,
                help = "برای بایگان: مشخصات هر سندی را که خودش ثبت میکند میبیند، حتی بالاتر از سطح محتوایش"),
        ),
        false,
        { jobj("subject" to jobj("kind" to JsonPrimitive("role"), "ref" to JsonPrimitive("")), "grants" to JsonArray(listOf(jobj("scope" to JsonPrimitive("own"), "level" to JsonPrimitive("internal")))), "metadata_level" to JsonNull) },
        sub = { r, m, cos ->
            buildAnnotatedString {
                append(r["grants"].arr.orEmpty().joinToString("؛ ") { g -> "${scopeFa(g.obj?.get("scope").prim.orEmpty(), cos)}: ${m.level(g.obj?.get("level").prim)?.titleFa ?: g.obj?.get("level").prim}" })
                r["metadata_level"].prim?.let { append(" · مشخصات تا " + (m.level(it)?.titleFa ?: it)) }
            }
        },
    ),
    "retention" to PartUI(
        "نگهداری", DivanIcon.MEMORY, "هر سند چه مدت میماند و بعدش چه میشود؛ پیش‌فرض‌اند، نه نظر حقوقی. امحا فقط با مُهر تو روی کارت.", "ref",
        listOf(
            Attr("title_fa", "عنوان", AttrKind.TEXT),
            Attr("trigger", "شمارش از", AttrKind.TRIGGER),
            Attr("keep", "مدت", AttrKind.KEEP),
            Attr("then", "بعد از آن", AttrKind.SELECT, Source.THEN),
        ),
        true,
        { jobj("title_fa" to JsonPrimitive(""), "trigger" to JsonPrimitive("filed"), "keep" to jobj("years" to JsonPrimitive(5)), "then" to JsonPrimitive("review")) },
        usage = ::usedNote,
        sub = { r, m, _ -> AnnotatedString(keepFa(r["keep"]) + (if (r["keep"].prim == "permanent") "" else " از ${triggerFa(r["trigger"], m)}") + "، بعد " + (THEN_FA[r["then"].prim] ?: r["then"].prim.orEmpty())) },
    ),
    "reminders" to PartUI(
        "یادآورها", DivanIcon.TIME, "چند روز پیش از یک تاریخ، به چه کسی و کجا.", "ref",
        listOf(
            Attr("class", "نوع سند", AttrKind.SELECT, Source.CLASSES),
            Attr("field", "فیلد تاریخ", AttrKind.SELECT, Source.DATE_FIELDS),
            Attr("lead_days", "چند روز پیش", AttrKind.LEAD_DAYS),
            Attr("to", "برای", AttrKind.TO),
            Attr("channel", "کجا", AttrKind.SELECT, Source.CHANNELS),
        ),
        true,
        { jobj("class" to JsonPrimitive(""), "field" to JsonPrimitive(""), "lead_days" to JsonArray(listOf(JsonPrimitive(30), JsonPrimitive(7))), "to" to JsonPrimitive("owner"), "channel" to JsonPrimitive("cartable")) },
        sub = { r, m, _ ->
            val c = m.cls(r["class"].prim)
            buildAnnotatedString {
                append((c?.titleFa ?: r["class"].prim.orEmpty()) + " · " + (c?.fields?.firstOrNull { it.key == r["field"].prim }?.titleFa ?: r["field"].prim.orEmpty()) + " · ")
                fig(r["lead_days"].strings().joinToString("، ")); append(" روز پیش · " + reminderToFa(r["to"]))
            }
        },
    ),
    "party_kinds" to PartUI(
        "نوع طرف‌ها", DivanIcon.COMPANIES, "صرافی، تأمین‌کننده، نهاد دولتی… و شناسه‌هایی که هر کدام دارد.", "key",
        listOf(Attr("title_fa", "عنوان", AttrKind.TEXT), Attr("identifier_fields", "شناسه‌ها", AttrKind.FIELDS)),
        true,
        { jobj("key" to JsonPrimitive(""), "title_fa" to JsonPrimitive(""), "identifier_fields" to JsonArray(emptyList())) },
        usage = { r -> (r["parties"].int ?: 0).takeIf { it > 0 }?.let { "$it طرف" } },
        sub = { r, _, _ -> AnnotatedString("${r["identifier_fields"].arr?.size ?: 0} شناسه") },
    ),
    "link_kinds" to PartUI(
        "نوع پیوندها", DivanIcon.SHARE, "سندها چطور به هم و به کارت، پرونده و کار وصل میشوند؛ هر پیوند از آن سو هم خوانده میشود.", "key",
        listOf(Attr("title_fa", "عنوان", AttrKind.TEXT), Attr("inverse_fa", "از آن سو", AttrKind.TEXT), Attr("to_kinds", "به", AttrKind.MULTI, Source.REF_KINDS)),
        true,
        { jobj("key" to JsonPrimitive(""), "title_fa" to JsonPrimitive(""), "inverse_fa" to JsonPrimitive(""), "to_kinds" to jarr(listOf("record"))) },
        usage = ::usedNote,
        sub = { r, _, _ -> AnnotatedString("${r["title_fa"].prim.orEmpty()} ↔ ${r["inverse_fa"].prim.orEmpty()}") },
    ),
    "automations" to PartUI(
        "خودکارها", DivanIcon.REFRESH, "فقط قاعده، هرگز مدل: یک رویداد، چند شرط و چند اقدام از واژگان بسته.", "ref",
        listOf(Attr("title_fa", "عنوان", AttrKind.TEXT), Attr("on", "رویداد", AttrKind.SELECT, Source.EVENTS), Attr("when", "شرط‌ها", AttrKind.WHEN), Attr("do", "اقدام‌ها", AttrKind.DO)),
        true,
        { m -> jobj("title_fa" to JsonPrimitive(""), "on" to JsonPrimitive(m.vocab.events.firstOrNull() ?: "filed"), "when" to JsonObject(emptyMap()), "do" to JsonArray(emptyList())) },
        usage = { r -> (r["runs_30d"].int ?: 0).takeIf { it > 0 }?.let { "$it اجرا در ۳۰ روز" } },
        sub = { r, _, _ -> AnnotatedString(EVENT_FA[r["on"].prim] ?: r["on"].prim.orEmpty()) },
    ),
)

/** A part the app has no descriptor for: its attributes read off its rows. */
fun inferAttrs(rows: List<JsonObject>): List<Attr> {
    val skip = setOf("key", "ref", "version", "status", "records", "parties", "runs_30d", "last_run_at")
    val sample = rows.firstOrNull() ?: jobj("title_fa" to JsonPrimitive(""))
    return sample.entries.filter { it.key !in skip }.map { (k, v) ->
        Attr(k, k, when {
            v is JsonPrimitive && v.bool != null -> AttrKind.BOOL
            v is JsonPrimitive && !v.isString && v !is JsonNull -> AttrKind.INT
            v is JsonPrimitive && v.isString -> AttrKind.TEXT
            else -> AttrKind.JSON
        })
    }
}

fun partUI(part: String, rows: List<JsonObject> = emptyList()): PartUI = PART_UI[part] ?: inferAttrs(rows).let { attrs ->
    PartUI(part, DivanIcon.SETTINGS, "بخشی تازه از طرح بایگانی.", if (rows.any { "ref" in it }) "ref" else "key", attrs, true, {
        JsonObject(attrs.associate { a -> a.key to when (a.kind) { AttrKind.BOOL -> JsonPrimitive(false); AttrKind.INT -> JsonPrimitive(0); AttrKind.JSON -> JsonNull; else -> JsonPrimitive("") } })
    })
}

fun rowKey(ui: PartUI, row: JsonObject): String = if (ui.by == "subject") {
    val s = row["subject"]
    "${s.obj?.get("kind").prim ?: s.prim?.substringBefore(':')}:${s.obj?.get("ref").prim ?: s.prim?.substringAfter(':', "")}"
} else row[ui.by].prim.orEmpty()

/** The exact body of a PUT: the descriptor's attributes, nothing the server computes. */
fun bodyOf(ui: PartUI, row: JsonObject): JsonObject = JsonObject(ui.attrs.associate { it.key to (row[it.key] ?: JsonNull) })

// ================================================================== options --
private val ICONS = listOf("report", "found", "share", "lock", "budget", "globe", "send", "seal", "image", "meeting", "attach", "deliverable", "companies", "knowledge", "server", "decision", "chart", "treasury")

fun options(src: Source?, m: ArchiveMaps, row: JsonObject, companies: List<Company>): List<Opt> {
    val v = m.vocab
    return when (src) {
        Source.LEVELS -> m.levels.filter { it.status != "retired" }.map { Opt(it.key, it.titleFa) }
        Source.FOLDERS -> m.folders.filter { it.status != "retired" }.map { Opt(it.ref, "${it.titleFa} · ${it.scope}") }
        Source.SCOPE_FOLDERS -> m.folders.filter { f -> f.status != "retired" && f.scope == row["scope"].prim && f.ref != row["ref"].prim && m.folderPath(f.ref).none { it.ref == row["ref"].prim } }.map { Opt(it.ref, it.titleFa) }
        Source.CLASSES -> m.classes.filter { it.status != "retired" && it.key != row["key"].prim }.map { Opt(it.key, it.titleFa) }
        Source.RETENTION -> m.schema?.retention.orEmpty().filter { it.status != "retired" }.map { Opt(it.ref, it.titleFa) }
        Source.LINK_KINDS -> m.schema?.linkKinds.orEmpty().filter { it.status != "retired" }.map { Opt(it.key, it.titleFa) }
        Source.PARTY_KINDS -> m.schema?.partyKinds.orEmpty().filter { it.status != "retired" }.map { Opt(it.key, it.titleFa) }
        Source.EVENTS -> v.events.map { Opt(it, EVENT_FA[it] ?: it, figure = it !in EVENT_FA) }
        Source.ACTIONS -> v.actions.map { Opt(it, ACTION_FA[it] ?: it, figure = it !in ACTION_FA) }
        Source.OPS -> v.ops.map { Opt(it, OP_FA[it] ?: it, figure = it !in OP_FA) }
        Source.REF_KINDS -> v.refKinds.map { Opt(it, REF_KIND_FA[it] ?: it, figure = it !in REF_KIND_FA) }
        Source.CURRENCIES -> v.currencies.map { Opt(it, it, figure = true) }
        Source.MIMES -> v.mimes.map { Opt(it, it.replace("application/vnd.openxmlformats-officedocument.wordprocessingml.document", "docx").removePrefix("application/").replace("message/rfc822", "eml"), figure = true) }
        Source.COMPANIES -> companies.map { Opt(it.code, it.nameFa ?: it.code) }
        Source.THEN -> THEN_FA.map { Opt(it.key, it.value) }
        Source.CHANNELS -> CHANNEL_FA.map { Opt(it.key, it.value) }
        Source.DATE_FIELDS -> {
            // The date fields of this row: its own (a class) or its class's (a reminder rule).
            val fs = row["fields"].arr?.mapNotNull { it.obj }
                ?: m.cls(row["class"].prim)?.fields?.map { f -> jobj("key" to JsonPrimitive(f.key), "title_fa" to JsonPrimitive(f.titleFa), "type" to JsonPrimitive(f.type), "status" to JsonPrimitive(f.status)) }.orEmpty()
            fs.filter { (it["type"].prim == "date" || it["type"].prim == "date_range") && it["status"].prim != "retired" && !it["key"].prim.isNullOrBlank() }
                .map { Opt(it["key"].prim!!, it["title_fa"].prim?.ifBlank { null } ?: it["key"].prim!!) }
        }
        Source.REF_FIELDS -> row["fields"].arr.orEmpty().mapNotNull { it.obj }.filter { it["type"].prim == "ref" && it["status"].prim != "retired" }.map { Opt(it["key"].prim.orEmpty(), it["title_fa"].prim?.ifBlank { null } ?: it["key"].prim.orEmpty()) }
        Source.ICONS -> ICONS.map { Opt(it, it, figure = true) }
        null -> emptyList()
    }
}

// ================================================================== reading a value --
/** One attribute as words, for row summaries and the cartable diff. */
fun attrText(a: Attr, v: JsonElement?, m: ArchiveMaps, row: JsonObject, companies: List<Company>): AnnotatedString {
    if (v == null || v is JsonNull || (v is JsonPrimitive && v.isString && v.content.isEmpty()) || (v is JsonArray && v.isEmpty())) return AnnotatedString("—")
    fun label(x: String?) = options(a.source, m, row, companies).firstOrNull { it.v == x }
    return when (a.kind) {
        AttrKind.BOOL -> AnnotatedString(if (v.bool == true) "بله" else "نه")
        AttrKind.INT, AttrKind.COLOR -> figText(v.prim.orEmpty())
        AttrKind.SELECT -> label(v.prim)?.let { if (it.figure) figText(it.t) else AnnotatedString(it.t) } ?: figText(v.prim.orEmpty())
        AttrKind.MULTI -> buildAnnotatedString {
            v.strings().forEachIndexed { i, x -> if (i > 0) append("، "); val o = label(x); if (o == null || o.figure) fig(o?.t ?: x) else append(o.t) }
        }
        AttrKind.SCOPES -> AnnotatedString(if (v.prim == "all") "همه‌ی دامنه‌ها" else v.strings().joinToString("، ") { scopeFa(it, companies) })
        AttrKind.KEEP -> AnnotatedString(keepFa(v))
        AttrKind.TRIGGER -> AnnotatedString(triggerFa(v, m))
        AttrKind.LEAD_DAYS -> buildAnnotatedString { fig(v.strings().joinToString("، ")); append(" روز پیش") }
        AttrKind.TO -> AnnotatedString(reminderToFa(v))
        AttrKind.SUBJECT -> AnnotatedString(subjectFa(v))
        AttrKind.GRANTS -> AnnotatedString(v.arr.orEmpty().joinToString("؛ ") { g -> "${scopeFa(g.obj?.get("scope").prim.orEmpty(), companies)}: ${m.level(g.obj?.get("level").prim)?.titleFa ?: g.obj?.get("level").prim}" })
        AttrKind.WHEN -> AnnotatedString(whenFa(v.obj ?: JsonObject(emptyMap()), m, companies))
        AttrKind.DO -> AnnotatedString(v.arr.orEmpty().mapNotNull { it.obj }.joinToString("\n") { stepFa(it, m) })
        AttrKind.LIST -> AnnotatedString(v.arr.orEmpty().mapNotNull { it.obj }.joinToString("، ") { "${it["field"].prim} → ${m.linkKind(it["link_kind"].prim.orEmpty())?.titleFa ?: it["link_kind"].prim}" })
        AttrKind.FIELDS -> AnnotatedString("${v.arr?.size ?: 0} فیلد")
        AttrKind.JSON -> figText(v.toString())
        AttrKind.TEXT -> AnnotatedString(v.prim ?: v.toString())
    }
}

fun whenFa(w: JsonObject, m: ArchiveMaps, companies: List<Company>): String {
    val parts = ArrayList<String>()
    w["class"].prim?.let { parts += "نوع «${m.cls(it)?.titleFa ?: it}»" }
    w["scope"].prim?.let { parts += "دامنه‌ی ${scopeFa(it, companies)}" }
    w["level_min"].prim?.let { parts += "سطح دست‌کم ${m.level(it)?.titleFa ?: it}" }
    w["field"].obj?.let { f ->
        val k = f["key"].prim.orEmpty()
        parts += "«${m.cls(w["class"].prim)?.fields?.firstOrNull { it.key == k }?.titleFa ?: k}» ${OP_FA[f["op"].prim] ?: f["op"].prim} ${f["value"].prim.orEmpty()}"
    }
    return if (parts.isEmpty()) "هر سندی" else parts.joinToString(" و ")
}

fun stepFa(s: JsonObject, m: ArchiveMaps): String {
    val a = s["args"].obj ?: JsonObject(emptyMap())
    val act = s["action"].prim.orEmpty()
    val what = when (act) {
        "notify" -> "اعلان «${NOTIFY_LEVEL_FA[a["level"].prim] ?: a["level"].prim}» به ${if (a["to"].prim == "owner") "تو" else archRoleFa(a["to"].prim.orEmpty())}: ${a["text_fa"].prim.orEmpty()}"
        "work_item" -> "کار برای ${archRoleFa(a["role"].prim.orEmpty())}: ${a["title_fa"].prim.orEmpty()}"
        "move_to_folder" -> "به پوشه‌ی ${m.folder(a["folder"].prim)?.titleFa ?: a["folder"].prim}"
        "raise_level" -> "سطح دست‌کم ${m.level(a["level"].prim)?.titleFa ?: a["level"].prim}"
        "add_reminder" -> "یادآور روی ${a["field"].prim.orEmpty()}، ${a["lead_days"].strings().joinToString("، ")} روز پیش"
        "link" -> "پیوند ${m.linkKind(a["kind"].prim.orEmpty())?.titleFa ?: a["kind"].prim} به ${a["to"].obj?.get("ref").prim.orEmpty()}"
        else -> "$act $a"
    }
    return (ACTION_FA[act]?.let { "$it: " } ?: "") + what
}

// ================================================================== inputs --
private val NUMBER = Regex("^-?\\d+(\\.\\d+)?$")
private fun latin(s: String) = s.map { ch -> "۰۱۲۳۴۵۶۷۸۹".indexOf(ch).takeIf { it >= 0 }?.digitToChar() ?: ch }.joinToString("")
private fun toInts(s: String): JsonArray = JsonArray(latin(s).split(Regex("[\\s,،]+")).filter { it.isNotBlank() }.mapNotNull { it.toIntOrNull() }.map(::JsonPrimitive))

/** Errors under a prefix (`fields.amount.type` → under `fields`), for the editors of nested parts. */
fun under(errors: Map<String, String>, prefix: String): Map<String, String> =
    errors.filterKeys { it == prefix || it.startsWith("$prefix.") }.mapKeys { it.key.removePrefix(prefix).removePrefix(".") }

private fun JsonObject.with(vararg kv: Pair<String, JsonElement?>): JsonObject = JsonObject(this + kv.associate { (k, v) -> k to (v ?: JsonNull) })

@Composable
private fun ErrText(e: String?) { if (e != null) Text(e, style = Divan.type.caption, color = Divan.colors.negative) }

@Composable
private fun SmallLabel(text: String) = Text(text, style = Divan.type.micro, color = Divan.colors.textMuted)

@Composable
private fun Chips(value: List<String>, onChange: (List<String>) -> Unit, opts: List<Opt>) {
    if (opts.isEmpty()) return Text("گزینه‌ای نیست.", style = Divan.type.caption, color = Divan.colors.textMuted)
    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        for (o in opts) {
            val on = o.v in value
            Chip(on, { onChange(if (on) value - o.v else value + o.v) }) { ink ->
                if (o.figure) Fig(o.t, style = Divan.type.figureSmall, color = ink) else Text(o.t, style = Divan.type.small, color = ink, maxLines = 1)
            }
        }
    }
}

/** The field list of a class or a party kind: the type only from the closed list, a saved field never deleted (only retired), and a
 *  saved field's key and type fixed. */
@Composable
private fun FieldsEditor(value: List<JsonObject>, onChange: (List<JsonObject>) -> Unit, saved: Set<String>, errors: Map<String, String>, m: ArchiveMaps) {
    val c = Divan.colors
    val companies = rememberCompanies()
    val types = m.schema?.fieldTypes.orEmpty()
    fun set(i: Int, vararg kv: Pair<String, JsonElement?>) = onChange(value.mapIndexed { j, f -> if (j == i) f.with(*kv) else f })
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        value.forEachIndexed { i, f ->
            val k = f["key"].prim?.ifBlank { null } ?: "$i"
            val e = under(errors, k)
            val isSaved = f["key"].prim in saved
            val retired = f["status"].prim == "retired"
            val t = f["type"].prim.orEmpty()
            Column(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).border(1.dp, c.lineDivider, RoundedCornerShape(12.dp)).alpha(if (retired) 0.6f else 1f).padding(10.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                SmallLabel("عنوان")
                HqTextField(f["title_fa"].prim.orEmpty(), { set(i, "title_fa" to JsonPrimitive(it)) }, "فیلد ${i + 1}", Modifier.fillMaxWidth(), maxLength = 120)
                ErrText(e["title_fa"])
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        SmallLabel("کلید")
                        if (isSaved) Fig(f["key"].prim.orEmpty(), Modifier.padding(vertical = 10.dp), style = Divan.type.figureSmall, color = c.textMuted)
                        else HqTextField(f["key"].prim.orEmpty(), { set(i, "key" to JsonPrimitive(it.trim())) }, "snake_case", Modifier.fillMaxWidth(), maxLength = 40, figure = true)
                        ErrText(e["key"])
                    }
                    Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        SmallLabel("نوع")
                        Select(t, types.map { Opt(it.key, it.titleFa) }, { set(i, "type" to jstr(it ?: "text")) }, "فیلد ${i + 1}: نوع", Modifier.fillMaxWidth(), enabled = !isSaved, error = e["type"] != null)
                        ErrText(e["type"])
                    }
                }
                if (t == "enum" || t == "multi_enum") OptionsEditor(f["options"].arr.orEmpty().mapNotNull { it.obj }, { set(i, "options" to JsonArray(it)) }, e["options"])
                if (t == "ref") Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    SmallLabel("به چه چیزی")
                    Chips(f["ref_kinds"].strings(), { set(i, "ref_kinds" to jarr(it)) }, options(Source.REF_KINDS, m, JsonObject(emptyMap()), companies))
                    ErrText(e["ref_kinds"])
                }
                if (t == "money") Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    SmallLabel("واحد پول")
                    Select(f["currency"].prim, options(Source.CURRENCIES, m, JsonObject(emptyMap()), companies), { set(i, "currency" to jstr(it)) }, "فیلد ${i + 1}: واحد", Modifier.width(140.dp), error = e["currency"] != null)
                    ErrText(e["currency"])
                }
                FlowRow(horizontalArrangement = Arrangement.spacedBy(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp), itemVerticalAlignment = Alignment.CenterVertically) {
                    for ((key, fa) in listOf("required" to "لازم", "searchable" to "در جستجو", "sensitive" to "حساس (پنهان زیر محرمانه)")) {
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            HqSwitch(f[key].bool == true, { set(i, key to JsonPrimitive(it)) }, "فیلد ${i + 1}: $fa", enabled = !(retired && key == "required"))
                            Text(fa, style = Divan.type.caption, color = c.textSecondary)
                        }
                    }
                }
                HqTextField(f["help_fa"].prim.orEmpty(), { set(i, "help_fa" to (it.ifEmpty { null }?.let(::JsonPrimitive) ?: JsonNull)) }, "راهنما (اختیاری)", Modifier.fillMaxWidth(), maxLength = 300)
                for (msg in e.filterKeys { it !in setOf("", "title_fa", "key", "type", "options", "ref_kinds", "currency") }.values) ErrText(msg)
                if (isSaved) HqButton(if (retired) "برگردان" else "بازنشسته کن", { set(i, "status" to JsonPrimitive(if (retired) "active" else "retired"), "required" to JsonPrimitive(false)) },
                    variant = BtnVariant.GHOST, size = BtnSize.SM, icon = if (retired) DivanIcon.REFRESH else DivanIcon.PAUSE)
                else HqButton("بردار", { onChange(value.filterIndexed { j, _ -> j != i }) }, variant = BtnVariant.GHOST, size = BtnSize.SM, icon = DivanIcon.CLOSE)
            }
        }
        // Errors that name no field of the list (a saved field removed, the list itself).
        for ((k, msg) in errors) if (value.none { f -> val key = f["key"].prim?.ifBlank { null }; k.startsWith("${key ?: value.indexOf(f)}.") }) ErrText(msg)
        HqButton("فیلد تازه", {
            onChange(value + jobj("key" to JsonPrimitive(""), "title_fa" to JsonPrimitive(""), "type" to JsonPrimitive("text"), "required" to JsonPrimitive(false),
                "searchable" to JsonPrimitive(false), "sensitive" to JsonPrimitive(false), "help_fa" to JsonNull, "status" to JsonPrimitive("active")))
        }, size = BtnSize.SM, icon = DivanIcon.ADD)
    }
}

@Composable
private fun OptionsEditor(value: List<JsonObject>, onChange: (List<JsonObject>) -> Unit, err: String?) {
    val c = Divan.colors
    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(c.tile).padding(8.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        SmallLabel("گزینه‌ها")
        value.forEachIndexed { j, o ->
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                HqTextField(o["title_fa"].prim.orEmpty(), { t -> onChange(value.mapIndexed { k, x -> if (k == j) x.with("title_fa" to JsonPrimitive(t)) else x }) }, "عنوان", Modifier.weight(1f), maxLength = 80)
                HqTextField(o["key"].prim.orEmpty(), { t -> onChange(value.mapIndexed { k, x -> if (k == j) x.with("key" to JsonPrimitive(t.trim())) else x }) }, "key", Modifier.width(104.dp), maxLength = 40, figure = true)
                DIcon(DivanIcon.CLOSE, Modifier.clickable(role = Role.Button, onClickLabel = "برداشتن گزینه") { onChange(value.filterIndexed { k, _ -> k != j }) }, size = 16.dp, tint = c.textMuted)
            }
        }
        ErrText(err)
        Text("+ گزینه", Modifier.clickable(role = Role.Button) { onChange(value + jobj("key" to JsonPrimitive(""), "title_fa" to JsonPrimitive(""))) }, style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.goldInk)
    }
}

/** «when» of an automation: class, scope, a minimum level, and one field condition; each optional. */
@Composable
private fun WhenEditor(value: JsonObject, onChange: (JsonObject) -> Unit, errors: Map<String, String>, m: ArchiveMaps) {
    val c = Divan.colors
    val companies = rememberCompanies()
    val f = value["field"].obj
    fun set(vararg kv: Pair<String, JsonElement?>) = onChange(JsonObject((value + kv.associate { (k, v) -> k to (v ?: JsonNull) }).filterValues { it !is JsonNull && !(it is JsonPrimitive && it.isString && it.content.isEmpty()) }))
    val fields = m.cls(value["class"].prim)?.fields.orEmpty()
    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(10.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Labelled("نوع سند") { Select(value["class"].prim, options(Source.CLASSES, m, JsonObject(emptyMap()), companies), { set("class" to jstr(it), "field" to if (it == value["class"].prim) value["field"] else null) }, "شرط: نوع سند", Modifier.fillMaxWidth(), nullable = true, error = errors["class"] != null) }
        ErrText(errors["class"])
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Labelled("دامنه", Modifier.weight(1f)) { Select(value["scope"].prim, options(Source.COMPANIES, m, JsonObject(emptyMap()), companies), { set("scope" to jstr(it)) }, "شرط: دامنه", Modifier.fillMaxWidth(), nullable = true, error = errors["scope"] != null) }
            Labelled("سطح دست‌کم", Modifier.weight(1f)) { Select(value["level_min"].prim, options(Source.LEVELS, m, JsonObject(emptyMap()), companies), { set("level_min" to jstr(it)) }, "شرط: سطح دست‌کم", Modifier.fillMaxWidth(), nullable = true, error = errors["level_min"] != null) }
        }
        Labelled("فیلد") {
            if (fields.isNotEmpty()) Select(f?.get("key").prim, fields.filter { it.status != "retired" }.map { Opt(it.key, it.titleFa) }, { k ->
                set("field" to k?.let { jobj("key" to JsonPrimitive(it), "op" to JsonPrimitive(f?.get("op").prim ?: "eq"), "value" to (f?.get("value") ?: JsonPrimitive(""))) })
            }, "شرط: فیلد", Modifier.fillMaxWidth(), nullable = true)
            else HqTextField(f?.get("key").prim.orEmpty(), { k ->
                set("field" to k.trim().ifEmpty { null }?.let { jobj("key" to JsonPrimitive(it), "op" to JsonPrimitive(f?.get("op").prim ?: "eq"), "value" to (f?.get("value") ?: JsonPrimitive(""))) })
            }, "field_key", Modifier.fillMaxWidth(), maxLength = 40, figure = true)
        }
        if (f != null) Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Labelled("چطور", Modifier.weight(1f)) { Select(f["op"].prim, options(Source.OPS, m, JsonObject(emptyMap()), companies), { set("field" to f.with("op" to jstr(it ?: "eq"))) }, "شرط: عملگر", Modifier.fillMaxWidth()) }
            Labelled("مقدار", Modifier.weight(1f)) {
                HqTextField(f["value"].prim.orEmpty(), { t ->
                    val x = latin(t.trim())
                    set("field" to f.with("value" to if (NUMBER.matches(x)) JsonPrimitive(x.toBigDecimal()) else JsonPrimitive(t)))
                }, "", Modifier.fillMaxWidth(), maxLength = 120, figure = f["value"] is JsonPrimitive && !(f["value"] as JsonPrimitive).isString)
            }
        }
        ErrText(errors["field"])
    }
}

/** The arguments each action of the closed list takes (§23.12); an action without a row here gets a JSON box. */
private data class ArgSpec(val key: String, val fa: String, val kind: String, val source: String? = null)

private val ACTION_ARGS = mapOf(
    "notify" to listOf(ArgSpec("to", "به", "select", "recipients"), ArgSpec("level", "سطح اعلان", "select", "notify_levels"), ArgSpec("text_fa", "متن", "text")),
    "work_item" to listOf(ArgSpec("role", "نقش", "select", "roles"), ArgSpec("title_fa", "عنوان کار", "text")),
    "link" to listOf(ArgSpec("kind", "نوع پیوند", "select", "link_kinds"), ArgSpec("to", "به", "target")),
    "move_to_folder" to listOf(ArgSpec("folder", "پوشه", "select", "folders")),
    "raise_level" to listOf(ArgSpec("level", "سطح", "select", "levels")),
    "add_reminder" to listOf(ArgSpec("field", "فیلد تاریخ", "text"), ArgSpec("lead_days", "چند روز پیش", "lead_days")),
)

private fun argOptions(src: String?, m: ArchiveMaps, companies: List<Company>): List<Opt> = when (src) {
    "recipients" -> listOf(Opt("owner", "تو")) + ROLES.map { Opt(it, archRoleFa(it)) }
    "roles" -> ROLES.map { Opt(it, archRoleFa(it)) }
    // Never `urgent` (§6): only the fixity alarm is.
    "notify_levels" -> NOTIFY_LEVEL_FA.map { Opt(it.key, it.value) }
    "link_kinds" -> options(Source.LINK_KINDS, m, JsonObject(emptyMap()), companies)
    "folders" -> options(Source.FOLDERS, m, JsonObject(emptyMap()), companies)
    "levels" -> options(Source.LEVELS, m, JsonObject(emptyMap()), companies)
    else -> emptyList()
}

@Composable
private fun DoEditor(value: List<JsonObject>, onChange: (List<JsonObject>) -> Unit, errors: Map<String, String>, m: ArchiveMaps) {
    val c = Divan.colors
    val companies = rememberCompanies()
    fun set(i: Int, s: JsonObject) = onChange(value.mapIndexed { j, x -> if (j == i) s else x })
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        value.forEachIndexed { i, s ->
            val act = s["action"].prim.orEmpty()
            val spec = ACTION_ARGS[act]
            val a = s["args"].obj ?: JsonObject(emptyMap())
            val e = under(errors, "$i")
            fun setArg(k: String, v: JsonElement?) = set(i, s.with("args" to a.with(k to v)))
            Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(10.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Labelled("اقدام ${i + 1}", Modifier.weight(1f)) {
                        Select(act, options(Source.ACTIONS, m, JsonObject(emptyMap()), companies), { set(i, jobj("action" to jstr(it), "args" to JsonObject(emptyMap()))) }, "اقدام ${i + 1}", Modifier.fillMaxWidth(), error = e["action"] != null)
                    }
                    DIcon(DivanIcon.CLOSE, Modifier.clickable(role = Role.Button, onClickLabel = "برداشتن اقدام ${i + 1}") { onChange(value.filterIndexed { j, _ -> j != i }) }, size = 18.dp, tint = c.textMuted)
                }
                ErrText(e["action"])
                if (spec != null) for (x in spec) Labelled(x.fa) {
                    when (x.kind) {
                        "select" -> Select(a[x.key].prim, argOptions(x.source, m, companies), { setArg(x.key, jstr(it)) }, "اقدام ${i + 1}: ${x.fa}", Modifier.fillMaxWidth(), error = e[x.key] != null)
                        "lead_days" -> LeadDays(a[x.key], { setArg(x.key, it) }, "اقدام ${i + 1}: ${x.fa}")
                        "target" -> Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                            val to = a["to"].obj
                            Select(to?.get("kind").prim ?: "record", options(Source.REF_KINDS, m, JsonObject(emptyMap()), companies), { k -> setArg("to", jobj("kind" to jstr(k ?: "record"), "ref" to (to?.get("ref") ?: JsonPrimitive("")))) }, "اقدام ${i + 1}: مقصد از چه نوع", Modifier.width(132.dp))
                            HqTextField(to?.get("ref").prim.orEmpty(), { t -> setArg("to", jobj("kind" to jstr(to?.get("kind").prim ?: "record"), "ref" to JsonPrimitive(t.trim().uppercase()))) }, "AR-000000", Modifier.weight(1f), maxLength = 40, figure = true)
                        }
                        else -> HqTextField(a[x.key].prim.orEmpty(), { setArg(x.key, JsonPrimitive(it)) }, x.fa, Modifier.fillMaxWidth(), maxLength = 300)
                    }
                    ErrText(e[x.key])
                } else if (act.isNotEmpty()) JsonBox(a, { set(i, s.with("args" to (it ?: JsonObject(emptyMap())))) }, "اقدام ${i + 1}: ورودی‌ها")
                for ((k, msg) in e) if (k != "action" && spec?.any { it.key == k } != true) ErrText(msg)
            }
        }
        ErrText(errors[""])
        HqButton("اقدام تازه", { onChange(value + jobj("action" to JsonPrimitive(m.vocab.actions.firstOrNull() ?: "notify"), "args" to JsonObject(emptyMap()))) }, size = BtnSize.SM, icon = DivanIcon.ADD)
    }
}

@Composable
private fun LeadDays(v: JsonElement?, onChange: (JsonElement) -> Unit, label: String) {
    var text by remember { mutableStateOf(v.strings().joinToString(", ")) }
    Box(Modifier.fillMaxWidth().semantics { contentDescription = label }) {
        HqTextField(text, { text = it; onChange(toInts(it)) }, "60, 30, 7", Modifier.fillMaxWidth(), maxLength = 60, figure = true)
    }
}

@Composable
private fun JsonBox(value: JsonElement?, onChange: (JsonObject?) -> Unit, label: String) {
    val c = Divan.colors
    var text by remember { mutableStateOf(value?.toString() ?: "null") }
    var bad by remember { mutableStateOf(false) }
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        HqTextField(text, { t ->
            text = t
            val parsed = runCatching { Api.json.parseToJsonElement(t) }.getOrNull()
            bad = parsed == null
            if (parsed != null) onChange(parsed as? JsonObject)
        }, label, Modifier.fillMaxWidth(), singleLine = false, minLines = 3, maxLength = 4000, figure = true)
        if (bad) Text("JSON درست نیست.", style = Divan.type.micro, color = c.negative)
    }
}

@Composable
private fun GrantsEditor(value: List<JsonObject>, onChange: (List<JsonObject>) -> Unit, errors: Map<String, String>, m: ArchiveMaps) {
    val c = Divan.colors
    val companies = rememberCompanies()
    val scopes = listOf(Opt("own", "شرکت خودش"), Opt("all", "همه‌ی دامنه‌ها")) + options(Source.COMPANIES, m, JsonObject(emptyMap()), companies)
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        value.forEachIndexed { i, g ->
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Select(g["scope"].prim, scopes, { s -> onChange(value.mapIndexed { j, x -> if (j == i) x.with("scope" to jstr(s ?: "own")) else x }) }, "مجوز ${i + 1}: دامنه", Modifier.weight(1f), error = errors["$i.scope"] != null)
                Select(g["level"].prim, options(Source.LEVELS, m, JsonObject(emptyMap()), companies), { l -> onChange(value.mapIndexed { j, x -> if (j == i) x.with("level" to jstr(l ?: "")) else x }) }, "مجوز ${i + 1}: سطح", Modifier.weight(1f), error = errors["$i.level"] != null)
                DIcon(DivanIcon.CLOSE, Modifier.clickable(role = Role.Button, onClickLabel = "برداشتن مجوز ${i + 1}") { onChange(value.filterIndexed { j, _ -> j != i }) }, size = 16.dp, tint = c.textMuted)
            }
            ErrText(errors["$i.level"] ?: errors["$i.scope"])
        }
        HqButton("مجوز", { onChange(value + jobj("scope" to JsonPrimitive("own"), "level" to jstr(m.levels.getOrNull(1)?.key ?: m.levels.firstOrNull()?.key ?: ""))) }, size = BtnSize.SM, icon = DivanIcon.ADD)
    }
}

/** One attribute's input, by its kind and source. */
@Composable
private fun AttrInput(a: Attr, row: JsonObject, set: (Pair<String, JsonElement?>) -> Unit, errors: Map<String, String>, saved: Boolean, savedFields: Set<String>, m: ArchiveMaps) {
    val c = Divan.colors
    val companies = rememberCompanies()
    val v = row[a.key]
    val err = errors[a.key]
    val lock = a.locked?.invoke(row, saved)
    val opts = options(a.source, m, row, companies)
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(a.fa, style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
        when (a.kind) {
            AttrKind.TEXT -> if (lock != null) Text(v.prim.orEmpty(), style = Divan.type.small, color = c.textMuted)
                else HqTextField(v.prim.orEmpty(), { set(a.key to JsonPrimitive(it)) }, a.fa, Modifier.fillMaxWidth(), maxLength = 300)
            AttrKind.INT -> if (lock != null) Fig(v.prim.orEmpty(), style = Divan.type.figure, color = c.textMuted)
                else HqTextField(v.prim.orEmpty(), { t -> set(a.key to latin(t.trim()).ifEmpty { null }?.let { it.toIntOrNull()?.let(::JsonPrimitive) ?: JsonPrimitive(it) }) }, "0", Modifier.width(128.dp), maxLength = 8, figure = true)
            AttrKind.BOOL -> HqSwitch(v.bool == true, { set(a.key to JsonPrimitive(it)) }, a.fa)
            AttrKind.SELECT -> Select(v.prim, opts, { set(a.key to jstr(it)) }, a.fa, Modifier.fillMaxWidth(), nullable = a.nullable, error = err != null, enabled = lock == null)
            AttrKind.MULTI -> Chips(v.strings(), { set(a.key to jarr(it)) }, opts)
            AttrKind.COLOR -> FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                for (i in 0..5) Box(
                    Modifier.clip(CircleShape).then(if (v.int == i) Modifier.border(2.dp, c.goldInk, CircleShape) else Modifier).clickable(role = Role.RadioButton, onClickLabel = "رنگ $i") { set(a.key to JsonPrimitive(i)) }.padding(3.dp),
                ) { Pill("$i", levelTone(i), dot = true, figure = true) }
            }
            AttrKind.SCOPES -> {
                val all = v.prim == "all"
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    FilterChip("همه‌ی دامنه‌ها", all, { set(a.key to if (all) JsonArray(emptyList()) else JsonPrimitive("all")) })
                    if (!all) for (co in companies) {
                        val xs = v.strings()
                        FilterChip(co.nameFa ?: co.code, co.code in xs, { set(a.key to jarr(if (co.code in xs) xs - co.code else xs + co.code)) })
                    }
                }
            }
            AttrKind.KEEP -> {
                val perm = v.prim == "permanent"
                val k = v.obj
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Segmented(listOf(SegOption("term", "مدت‌دار"), SegOption("permanent", "دائمی")), if (perm) "permanent" else "term", { x -> set(a.key to if (x == "permanent") JsonPrimitive("permanent") else jobj("years" to JsonPrimitive(5))) }, Modifier.fillMaxWidth())
                    if (!perm) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        fun put(field: String, t: String) {
                            val n = latin(t.trim()).toIntOrNull()
                            val base = (k ?: JsonObject(emptyMap())).filterKeys { it != field }
                            set(a.key to JsonObject(if (n != null) base + (field to JsonPrimitive(n)) else base))
                        }
                        HqTextField(k?.get("years").prim.orEmpty(), { put("years", it) }, "0", Modifier.width(72.dp), maxLength = 3, figure = true)
                        Text("سال", style = Divan.type.caption, color = c.textMuted)
                        HqTextField(k?.get("months").prim.orEmpty(), { put("months", it) }, "0", Modifier.width(72.dp), maxLength = 2, figure = true)
                        Text("ماه", style = Divan.type.caption, color = c.textMuted)
                    }
                }
            }
            AttrKind.TRIGGER -> {
                val dateKeys = m.classes.flatMap { it.fields }.filter { it.type == "date" || it.type == "date_range" }.distinctBy { it.key }
                Select(v.prim, listOf(Opt("filed", "ثبت سند"), Opt("case_closed", "بسته شدن پرونده"), Opt("superseded", "جایگزین شدن")) + dateKeys.map { Opt("field:${it.key}", "فیلد «${it.titleFa}» (${it.key})") },
                    { set(a.key to jstr(it)) }, a.fa, Modifier.fillMaxWidth(), error = err != null)
            }
            AttrKind.LEAD_DAYS -> LeadDays(v, { set(a.key to it) }, a.fa)
            AttrKind.TO -> {
                val kind = when { v.prim == "owner" -> "owner"; v.obj?.containsKey("company_ceo") == true -> "ceo"; else -> "role" }
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Select(kind, listOf(Opt("owner", "تو"), Opt("ceo", "مدیرعامل همان شرکت"), Opt("role", "یک نقش")), { x ->
                        set(a.key to when (x) { "owner" -> JsonPrimitive("owner"); "ceo" -> jobj("company_ceo" to JsonPrimitive(true)); else -> jobj("role" to JsonPrimitive("archivist")) })
                    }, a.fa, Modifier.weight(1f), error = err != null)
                    if (kind == "role") Select(v.obj?.get("role").prim, ROLES.map { Opt(it, archRoleFa(it)) }, { set(a.key to jobj("role" to jstr(it ?: "archivist"))) }, "${a.fa}: نقش", Modifier.weight(1f))
                }
            }
            AttrKind.SUBJECT -> {
                val s = v.obj
                val kind = s?.get("kind").prim ?: "role"
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Select(kind, listOf(Opt("role", "نقش"), Opt("employee", "کارمند")), { x -> set(a.key to jobj("kind" to jstr(x ?: "role"), "ref" to JsonPrimitive(""))) }, "${a.fa}: نوع", Modifier.width(108.dp), enabled = lock == null)
                    if (kind == "role") Select(s?.get("ref").prim?.ifEmpty { null }, (listOf("*") + ROLES).map { Opt(it, archRoleFa(it)) }, { x -> set(a.key to jobj("kind" to JsonPrimitive("role"), "ref" to jstr(x ?: ""))) }, a.fa, Modifier.weight(1f), enabled = lock == null, error = errors["key"] != null)
                    else HqTextField(s?.get("ref").prim.orEmpty(), { t -> set(a.key to jobj("kind" to JsonPrimitive("employee"), "ref" to JsonPrimitive(t.trim().uppercase()))) }, "FX-TECH-MGR", Modifier.weight(1f), maxLength = 40, figure = true)
                }
                ErrText(errors["key"])
            }
            AttrKind.GRANTS -> GrantsEditor(v.arr.orEmpty().mapNotNull { it.obj }, { set(a.key to JsonArray(it)) }, under(errors, a.key), m)
            AttrKind.FIELDS -> FieldsEditor(v.arr.orEmpty().mapNotNull { it.obj }, { set(a.key to JsonArray(it)) }, if (saved) savedFields else emptySet(), under(errors, a.key), m)
            AttrKind.WHEN -> WhenEditor(v.obj ?: JsonObject(emptyMap()), { set(a.key to it) }, under(errors, a.key), m)
            AttrKind.DO -> DoEditor(v.arr.orEmpty().mapNotNull { it.obj }, { set(a.key to JsonArray(it)) }, under(errors, a.key) + (err?.let { mapOf("" to it) } ?: emptyMap()), m)
            AttrKind.LIST -> {
                val xs = v.arr.orEmpty().mapNotNull { it.obj }
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    xs.forEachIndexed { i, x ->
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            Select(x["field"].prim, opts, { f -> set(a.key to JsonArray(xs.mapIndexed { j, y -> if (j == i) y.with("field" to jstr(f ?: "")) else y })) }, "پیوند خودکار ${i + 1}: فیلد", Modifier.weight(1f))
                            Select(x["link_kind"].prim, options(Source.LINK_KINDS, m, row, companies), { k -> set(a.key to JsonArray(xs.mapIndexed { j, y -> if (j == i) y.with("link_kind" to jstr(k ?: "")) else y })) }, "پیوند خودکار ${i + 1}: نوع", Modifier.weight(1f))
                            DIcon(DivanIcon.CLOSE, Modifier.clickable(role = Role.Button, onClickLabel = "برداشتن پیوند خودکار ${i + 1}") { set(a.key to JsonArray(xs.filterIndexed { j, _ -> j != i })) }, size = 16.dp, tint = c.textMuted)
                        }
                    }
                    if (opts.isNotEmpty()) Text("+ پیوند خودکار", Modifier.clickable(role = Role.Button) {
                        set(a.key to JsonArray(xs + jobj("field" to JsonPrimitive(opts.first().v), "link_kind" to JsonPrimitive(m.schema?.linkKinds?.firstOrNull()?.key ?: "about"))))
                    }, style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.goldInk)
                    else Text("فیلد ارجاعی ندارد.", style = Divan.type.caption, color = c.textMuted)
                }
            }
            AttrKind.JSON -> JsonBox(v, { set(a.key to it) }, a.fa)
        }
        when {
            err != null && a.kind !in setOf(AttrKind.GRANTS, AttrKind.FIELDS, AttrKind.WHEN, AttrKind.DO) -> ErrText(err)
            lock != null -> Text(lock, style = Divan.type.micro, color = c.textMuted)
            a.help != null -> Text(a.help, style = Divan.type.micro, color = c.textMuted)
        }
    }
}

// ================================================================== the save flow --
/** «N records, M missing a required field» in plain Persian (counts, so Persian digits). */
@Composable
fun ImpactLine(impact: Impact, part: String) {
    val c = Divan.colors
    Row(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        DIcon(DivanIcon.CHART, Modifier.padding(top = 2.dp), size = 16.dp, tint = c.goldInk)
        Text(buildAnnotatedString {
            append(
                if (impact.records > 0) "${impact.records} سند " + when (part) { "clearance" -> "با این مجوز دیده میشود"; "automations" -> "زیر این خودکار میآید"; else -> "از این استفاده میکند" }
                else "هیچ سندی " + when (part) { "clearance" -> "با این مجوز دیده نمیشود"; "automations" -> "فعلاً زیر این خودکار نمیآید"; else -> "از این استفاده نمیکند" },
            )
            if (impact.missingRequired > 0) {
                append("؛ ")
                pushStyle(androidx.compose.ui.text.SpanStyle(fontWeight = FontWeight.SemiBold, color = c.warning))
                append("${impact.missingRequired} سند فیلد اجباری را ندارد")
                pop()
                append(" و بایگان یک کار برای پر کردنشان میگیرد.")
            } else append(".")
            if (part == "classes") append(" سندهای ثبت‌شده نسخه‌ی خودشان را نگه میدارند.")
        }, style = Divan.type.small, color = c.textPrimary)
    }
}

/** The editor of one row: every save is a dry run first (the impact, and the server's validation next to the inputs), then the passkey,
 *  then the PUT with If-Match. Retire, never delete. [preview0] runs the dry run at once (the screenshots); [blank0] starts a new row. */
@Composable
fun RowEditorContent(part: String, ui: PartUI, row0: JsonObject?, onClose: () -> Unit, preview0: Boolean = false, blank0: JsonObject? = null) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val act = activity()
    val c = Divan.colors
    val arch = rememberArchive()
    val m = arch.m
    val action = rememberAction()
    val saved = row0 != null
    var row by remember { mutableStateOf(row0 ?: blank0 ?: ui.blank(m)) }
    // Which fields existed when the editor opened: their key and type stay fixed, they are retired, never removed.
    val savedFields = remember { (row0?.get("fields") ?: row0?.get("identifier_fields")).arr.orEmpty().mapNotNull { it.obj?.get("key").prim }.toSet() }
    var errors by remember { mutableStateOf<Map<String, String>>(emptyMap()) }
    var checked by remember { mutableStateOf<Pair<String, SchemaResult>?>(null) }
    var failure by remember { mutableStateOf<ApiException?>(null) }
    var retiring by remember { mutableStateOf<SchemaResult?>(null) }
    val key = when { saved -> rowKey(ui, row0!!); ui.by == "ref" -> "new"; ui.by == "subject" -> rowKey(ui, row); else -> row["key"].prim.orEmpty().trim() }
    val version = if (saved) row0!!["version"].int?.takeIf { it > 0 } else null
    val body = bodyOf(ui, row)
    val text = body.toString()
    val fresh = checked?.first == text
    fun fail(e: ApiException) { failure = e; if (e.fields.isNotEmpty()) errors = e.fields }
    fun preview() {
        errors = emptyMap(); failure = null; checked = null
        action.run(onError = ::fail) { checked = text to env.api.schemaPreview(part, key, body, version) }
    }
    LaunchedEffect(Unit) { if (preview0) preview() }
    val isRetired = row0?.get("status").prim == "retired"
    val loose = errors.filterKeys { k -> ui.attrs.none { k == it.key || k.startsWith("${it.key}.") } && k != "key" }
    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        if (isRetired) Text("بازنشسته است: در سندهای قبلی میماند و دیگر برای سند تازه پیشنهاد نمیشود.", Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp), style = Divan.type.caption, color = c.textSecondary)
        if (!saved && ui.by == "key") Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("کلید", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
            HqTextField(row["key"].prim.orEmpty(), { row = row.with("key" to JsonPrimitive(it.trim())) }, "snake_case", Modifier.fillMaxWidth(), maxLength = 40, figure = true)
            Text(errors["key"] ?: "حروف کوچک لاتین، عدد و _؛ بعد از ساخت عوض نمیشود.", style = Divan.type.micro, color = if (errors["key"] != null) c.negative else c.textMuted)
        }
        for (a in ui.attrs) AttrInput(a, row, { (k, v) -> row = row.with(k to v) }, errors, saved, savedFields, m)
        if (loose.isNotEmpty()) Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.softNegative).padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            for ((k, v) in loose) Text(buildAnnotatedString { fig(k, c.textMuted); append("  $v") }, style = Divan.type.caption, color = c.negative)
        }
        ErrorLine(failure)
        val ck = checked
        if (ck != null && fresh) ImpactLine(ck.second.impact, part) else if (ck != null) Text("بعد از بررسی عوض شد؛ دوباره بررسی کن.", style = Divan.type.caption, color = c.warning)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp), itemVerticalAlignment = Alignment.CenterVertically) {
            if (ck != null && fresh) HqButton("ذخیره با اثر انگشت", {
                failure = null
                action.run(onError = { e -> checked = null; fail(e) }) {
                    val out = env.api.schemaSave(part, key, Api.json.parseToJsonElement(text) as JsonObject, version) { a, t -> env.auth.stepUp(act, a, t) }
                    env.cache.invalidate("archive", "decisions")
                    toasts.ok("ذخیره شد؛ نسخه‌ی ${out.version} از «${row["title_fa"].prim ?: subjectFa(row["subject"] ?: JsonPrimitive(key))}».")
                    onClose()
                }
            }, variant = BtnVariant.PRIMARY, icon = DivanIcon.LOCK, loading = action.busy)
            else HqButton("بررسی اثر", { preview() }, variant = BtnVariant.PRIMARY, icon = DivanIcon.SEARCH, enabled = !isRetired && (saved || ui.by != "key" || key.isNotEmpty()), loading = action.busy)
            HqButton("انصراف", onClose, variant = BtnVariant.GHOST)
            if (saved && ui.retire && !isRetired && version != null) HqButton("بازنشسته کن", {
                failure = null
                action.run(onError = ::fail) { retiring = env.api.schemaRetirePreview(part, key, version) }
            }, variant = BtnVariant.DANGER, size = BtnSize.SM, icon = DivanIcon.PAUSE)
        }
    }
    retiring?.let { rr ->
        AlertDialog(
            onDismissRequest = { retiring = null },
            containerColor = c.overlay,
            title = { Text("بازنشسته کردن", style = Divan.type.h3) },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    ImpactLine(rr.impact, part)
                    Text("هیچ چیزی پاک نمیشود؛ سندهایی که از آن استفاده میکنند همان‌طور میمانند و در جستجو هستند. فقط برای سند تازه پیشنهاد نمیشود.", style = Divan.type.small, color = c.textSecondary)
                }
            },
            confirmButton = {
                HqButton("با اثر انگشت بازنشسته کن", {
                    val v = version ?: return@HqButton
                    action.run(onError = { e -> retiring = null; fail(e) }) {
                        env.api.schemaRetire(part, key, v) { a, t -> env.auth.stepUp(act, a, t) }
                        env.cache.invalidate("archive", "decisions")
                        retiring = null
                        toasts.info("بازنشسته شد؛ هیچ سندی که از آن استفاده میکند پاک نشد.")
                        onClose()
                    }
                }, variant = BtnVariant.DANGER, icon = DivanIcon.LOCK, loading = action.busy)
            },
            dismissButton = { HqButton("نه", { retiring = null }, variant = BtnVariant.GHOST) },
        )
    }
}
