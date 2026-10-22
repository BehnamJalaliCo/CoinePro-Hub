package com.coinepro.hq.ui.archive

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.HqClock
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.jDate
import com.coinepro.hq.core.format.jDateTime
import com.coinepro.hq.core.format.roleFa
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.ArchiveSchema
import com.coinepro.hq.core.net.FieldDef
import com.coinepro.hq.core.net.FolderNode
import com.coinepro.hq.core.net.Level
import com.coinepro.hq.core.net.LinkKind
import com.coinepro.hq.core.net.Party
import com.coinepro.hq.core.net.PartyKind
import com.coinepro.hq.core.net.RecordClass
import com.coinepro.hq.core.net.Suggestion
import com.coinepro.hq.core.net.Vocab
import com.coinepro.hq.core.net.archiveError
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.ActionRunner
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.QueryHandle
import com.coinepro.hq.ui.Toasts
import com.coinepro.hq.ui.companyOf
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v14.figs
import com.coinepro.hq.ui.v16.prose
import com.coinepro.hq.ui.v17.CoMark
import com.coinepro.hq.ui.v17.RefChip
import java.time.LocalDate
import java.time.temporal.ChronoUnit
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull

// Shared pieces of the archive (contract §23), mirroring apps/web/src/components/v20/bits.tsx. Every map below translates a value the
// server sends; an unknown value (a new event, action or kind added on the hub) falls back to its key in Latin figures, so the screens keep
// working without a new release.

// ------------------------------------------------------------------ labels (§23) --
data class StateMeta(val fa: String, val tone: Tone, val icon: DivanIcon)

val RECORD_STATE = mapOf(
    "draft" to StateMeta("پیش‌نویس", Tone.LAPIS, DivanIcon.EDIT), "filed" to StateMeta("ثبت‌شده", Tone.SILVER, DivanIcon.DELIVERABLE),
    "sealed" to StateMeta("مُهرشده", Tone.GOLD, DivanIcon.SEAL), "superseded" to StateMeta("جایگزین‌شده", Tone.NEUTRAL, DivanIcon.REFRESH),
    "disposed" to StateMeta("امحاشده", Tone.NEUTRAL, DivanIcon.CLOSE),
)
val TEXT_STATE = mapOf("none" to "بی‌متن", "text_layer" to "لایه‌ی متن", "ocr" to "OCR", "failed" to "OCR نشد")
val SOURCE_KIND = mapOf("owner" to "مدیر کل", "agent" to "ایجنت", "system" to "خودکار")
val EVENT_FA = linkedMapOf(
    "filed" to "وقتی ثبت شد", "sealed" to "وقتی مُهر خورد", "reminder_due" to "وقتی یادآور رسید", "retention_due" to "وقتی نگهداری تمام شد",
    "hold_set" to "وقتی توقیف شد", "version_added" to "وقتی نسخه‌ی تازه آمد",
)
val ACTION_FA = linkedMapOf(
    "notify" to "اعلان", "work_item" to "کار برای یک نقش", "link" to "پیوند", "move_to_folder" to "انتقال به پوشه", "raise_level" to "بالا بردن سطح", "add_reminder" to "افزودن یادآور",
)
val OP_FA = linkedMapOf("eq" to "برابر با", "lt" to "کمتر از", "gt" to "بیشتر از", "contains" to "شامل")
val REF_KIND_FA = linkedMapOf(
    "decision" to "کارت تصمیم", "resolution" to "مصوبه", "case" to "پرونده‌ی حقوقی", "work" to "کار", "record" to "سند بایگانی", "employee" to "کارمند", "revenue_account" to "حساب درآمد",
)
val THEN_FA = linkedMapOf("review" to "بازبینی بایگان", "dispose_card" to "کارت امحا برای تو")
val CHANNEL_FA = linkedMapOf("cartable" to "کارتابل", "digest" to "خلاصه‌ی روزانه")
val NOTIFY_LEVEL_FA = linkedMapOf("info" to "اطلاع", "report" to "گزارش", "decision" to "تصمیم")
val ACCESS_FA = mapOf(
    "view" to ("دید" to DivanIcon.SEARCH), "download" to ("دریافت کرد" to DivanIcon.DOWNLOAD), "metadata" to ("مشخصات را خواند" to DivanIcon.REPORT),
    "level" to ("سطح را عوض کرد" to DivanIcon.LOCK),
)

/** A clearance subject's role; `*` is every agent role. */
fun archRoleFa(r: String): String = if (r == "*") "هر نقش ایجنت" else roleFa(r)

/** Who a reminder goes to (§23.6): the owner, a role, or the company's CEO. */
fun reminderToFa(t: JsonElement?): String = when {
    t is JsonPrimitive && t.contentOrNull == "owner" -> "تو"
    t is JsonObject && t["role"] != null -> archRoleFa(t["role"].str.orEmpty())
    t is JsonObject -> "مدیرعامل همان شرکت"
    else -> t?.str ?: "—"
}

/** Level colour by its stored slot; colour is never alone, the title always goes with it. */
private val LEVEL_TONE = listOf(Tone.NEUTRAL, Tone.SILVER, Tone.WARN, Tone.NEG, Tone.LAPIS, Tone.LEARN)
fun levelTone(colorIndex: Int?): Tone = LEVEL_TONE.getOrElse(colorIndex ?: 0) { Tone.NEUTRAL }

fun iconOf(id: String?): DivanIcon = DivanIcon.entries.firstOrNull { it.id == id } ?: DivanIcon.REPORT

// ------------------------------------------------------------------ JSON values --
internal val JsonElement?.str: String? get() = (this as? JsonPrimitive)?.takeIf { it.isString }?.content
internal val JsonElement?.prim: String? get() = (this as? JsonPrimitive)?.takeIf { it !is JsonNull }?.contentOrNull
internal val JsonElement?.obj: JsonObject? get() = this as? JsonObject
internal val JsonElement?.arr: JsonArray? get() = this as? JsonArray
internal val JsonElement?.bool: Boolean? get() = (this as? JsonPrimitive)?.takeIf { !it.isString }?.contentOrNull?.toBooleanStrictOrNull()
internal val JsonElement?.int: Int? get() = (this as? JsonPrimitive)?.takeIf { !it.isString }?.contentOrNull?.toDoubleOrNull()?.toInt()
internal fun jstr(s: String?): JsonElement = if (s == null) JsonNull else JsonPrimitive(s)
internal fun jobj(vararg kv: Pair<String, JsonElement?>): JsonObject = JsonObject(kv.associate { (k, v) -> k to (v ?: JsonNull) })
internal fun jarr(xs: List<String>): JsonArray = JsonArray(xs.map(::JsonPrimitive))
internal fun JsonElement?.strings(): List<String> = (this as? JsonArray)?.mapNotNull { it.prim }.orEmpty()

/** Is a value empty, as the server reads it (an empty money amount too)? */
fun emptyValue(v: JsonElement?): Boolean = v == null || v is JsonNull || (v is JsonPrimitive && v.isString && v.content.isEmpty()) ||
    (v is JsonArray && v.isEmpty()) || (v is JsonObject && v.containsKey("amount") && v["amount"].prim.isNullOrEmpty()) || (v is JsonObject && v.isEmpty())

// ------------------------------------------------------------------ the schema, as maps --
/** The archive's schema (§23.10) as lookups every screen shares. */
class ArchiveMaps(val schema: ArchiveSchema?) {
    val classes: List<RecordClass> = schema?.classes.orEmpty()
    val levels: List<Level> = schema?.levels.orEmpty()
    val folders: List<FolderNode> = schema?.folders.orEmpty()
    val parties: List<Party> = schema?.parties.orEmpty()
    val vocab: Vocab = schema?.vocab ?: Vocab()
    private val cm = classes.associateBy { it.key }
    private val lm = levels.associateBy { it.key }
    private val fm = folders.associateBy { it.ref }
    private val pm = parties.associateBy { it.ref }
    private val lk = schema?.linkKinds.orEmpty().associateBy { it.key }
    private val pk = schema?.partyKinds.orEmpty().associateBy { it.key }
    private val ft = schema?.fieldTypes.orEmpty().associateBy { it.key }

    fun cls(k: String?): RecordClass? = k?.let { cm[it] }
    fun level(k: String?): Level? = k?.let { lm[it] }
    fun rank(k: String?): Int = k?.let { lm[it]?.rank } ?: 0
    fun folder(r: String?): FolderNode? = r?.let { fm[it] }
    fun party(r: String?): Party? = r?.let { pm[it] }
    fun linkKind(k: String): LinkKind? = lk[k]
    fun partyKind(k: String): PartyKind? = pk[k]
    fun typeFa(k: String): String = ft[k]?.titleFa ?: k

    /** A folder as its path in the file plan, root first. */
    fun folderPath(ref: String?): List<FolderNode> {
        val out = ArrayList<FolderNode>()
        var f = folder(ref)
        while (f != null && out.size < 12) { out.add(0, f); f = folder(f.parent) }
        return out
    }

    /** The default folder of a class in a scope (§23.12): the first folder of that scope that lists the class, else the class's own default. */
    fun defaultFolder(scope: String, cls: String?): String? {
        if (cls == null) return null
        folders.firstOrNull { it.scope == scope && it.status == "active" && cls in it.classes }?.let { return it.ref }
        val d = cls(cls)?.defaultFolder
        return d?.takeIf { folder(it)?.scope == scope }
    }
}

class ArchiveHandle(val q: QueryHandle<ArchiveSchema>, val m: ArchiveMaps)

@Composable
fun rememberArchive(): ArchiveHandle {
    val q = rememberQuery("archive:schema", "archive", maxAgeMs = 30_000) { archiveSchema() }
    val m = remember(q.data) { ArchiveMaps(q.data) }
    return ArchiveHandle(q, m)
}

// ------------------------------------------------------------------ dates and figures --
/** A Jalali day with Latin figures and the Persian month name, in reading order («12 مرداد 1405»). A stored calendar day is that day in
 *  the owner's zone; anything unreadable stays as it came, as a figure. */
fun jDay(d: String?, year: Boolean = true): AnnotatedString = when {
    d.isNullOrBlank() -> AnnotatedString("—")
    com.coinepro.hq.core.format.instant(d) == null -> buildAnnotatedString { fig(d) }
    else -> figs(jDate(d, year))
}

/** A moment: the Jalali day and the time, both in Latin figures. */
fun jStamp(at: String?, year: Boolean = false): AnnotatedString =
    if (at.isNullOrBlank()) AnnotatedString("—") else if (year) figs("${jDate(at, true)}، ${com.coinepro.hq.core.format.jTime(at)}") else figs(jDateTime(at))

/** Whole days from today to a calendar day (negative = past), in the owner's zone. */
fun daysTo(d: String): Long = runCatching { ChronoUnit.DAYS.between(HqClock.today(), LocalDate.parse(d.take(10))) }.getOrDefault(0)

/** «۲۵ روز مانده» / «امروز» / «۳ روز گذشته»: a count, so Persian digits (the text face draws them). */
fun daysLeftFa(n: Long): String = when { n == 0L -> "امروز"; n > 0 -> "$n روز مانده"; else -> "${-n} روز گذشته" }

/** A decimal string with thousands separators, its fraction exactly as stored. */
fun amountFig(amount: String): String {
    val t = amount.trim()
    val neg = t.startsWith("-")
    val i = t.removePrefix("-").substringBefore('.')
    val f = if ('.' in t) "." + t.substringAfter('.') else ""
    return (if (neg) "-" else "") + i.reversed().chunked(3).joinToString(",").reversed() + f
}

fun moneyFig(v: JsonObject): String = "${amountFig(v["amount"].prim.orEmpty())} ${v["currency"].prim.orEmpty()}".trim()

/** A SHA-256 shortened for reading. */
fun shaShort(v: String?, label: String = "sha256"): String = if (v.isNullOrBlank()) "—" else "$label ${v.take(10)}…${v.takeLast(4)}"

/** The last four characters of an identifier; the rest as dots (§23.2 `id_code`, `iban`). */
fun last4(s: String): String = if (s.length <= 4) s else "•••• ${s.takeLast(4)}"

// ------------------------------------------------------------------ small pieces --
@Composable
fun LevelPill(level: String?, m: ArchiveMaps) {
    val l = m.level(level)
    when {
        l != null -> Pill(l.titleFa, levelTone(l.colorIndex), icon = if (l.stepUpToView) DivanIcon.LOCK else null, dot = !l.stepUpToView)
        level != null -> Pill(level, Tone.NEUTRAL, figure = true)
    }
}

@Composable
fun StatePill(state: String) {
    val s = RECORD_STATE[state]
    if (s == null) Pill(state, Tone.NEUTRAL, figure = true) else Pill(s.fa, s.tone, icon = s.icon)
}

@Composable
fun ClassTag(cls: String?, m: ArchiveMaps, color: androidx.compose.ui.graphics.Color = Divan.colors.textMuted) {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        if (cls == null) {
            DIcon(DivanIcon.INFO, size = 12.dp, tint = color)
            Text("نوع‌نشده", style = Divan.type.micro, color = color)
        } else {
            val c = m.cls(cls)
            DIcon(iconOf(c?.icon), size = 12.dp, tint = color)
            if (c != null) Text(c.titleFa, style = Divan.type.micro, color = color, maxLines = 1) else Fig(cls, style = Divan.type.figureSmall, color = color)
        }
    }
}

@Composable
fun ScopeTag(scope: String, color: androidx.compose.ui.graphics.Color = Divan.colors.textMuted) {
    val companies = rememberCompanies()
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        CoMark(scope, height = 10.dp, ink = color)
        Text(companyOf(companies, scope).nameFa, style = Divan.type.micro, color = color, maxLines = 1)
    }
}

/** A party of the registry as a chip that opens its records. */
@Composable
fun PartyChip(ref: String, m: ArchiveMaps, role: String? = null) {
    val c = Divan.colors
    val nav = LocalNav.current
    val p = m.party(ref)
    Row(
        Modifier.clip(CircleShape).background(c.tile).clickable(role = Role.Button, onClickLabel = "سندهای این طرف") { nav.go("archive-in/party/$ref") }
            .padding(horizontal = 10.dp, vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        DIcon(when (p?.kind) { "person" -> DivanIcon.OWNER; "government" -> DivanIcon.HOLDING; else -> DivanIcon.COMPANIES }, size = 12.dp, tint = c.textSecondary)
        if (p != null) Text(p.nameFa, style = Divan.type.caption, color = c.textPrimary, maxLines = 1, overflow = TextOverflow.Ellipsis)
        else Fig(ref, style = Divan.type.figureSmall, color = c.textPrimary)
        if (!role.isNullOrBlank()) Text("· $role", style = Divan.type.micro, color = c.textMuted, maxLines = 1)
    }
}

/** A folder as its path in the file plan, each step a filter. */
@Composable
fun FolderPath(ref: String?, m: ArchiveMaps) {
    val c = Divan.colors
    val nav = LocalNav.current
    val path = m.folderPath(ref)
    when {
        ref == null -> Text("بی‌پوشه", style = Divan.type.caption, color = c.textMuted)
        path.isEmpty() -> Fig(ref, style = Divan.type.figureSmall, color = c.textPrimary)
        else -> FlowRow(horizontalArrangement = Arrangement.spacedBy(4.dp), verticalArrangement = Arrangement.spacedBy(2.dp), itemVerticalAlignment = Alignment.CenterVertically) {
            path.forEachIndexed { i, f ->
                if (i > 0) Text("‹", style = Divan.type.caption, color = c.textMuted)
                Text(f.titleFa, Modifier.clickable(role = Role.Button) { nav.go("archive-in/folder/${f.ref}") }, style = Divan.type.caption, color = c.textPrimary)
            }
        }
    }
}

/** An identifier masked to its last four, shown whole on a touch. */
@Composable
fun Masked4(v: String) {
    val c = Divan.colors
    var show by rememberSaveable(v) { mutableStateOf(false) }
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Fig(if (show) v else last4(v), style = Divan.type.figureSmall.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
        Text(if (show) "پنهان" else "نمایش", Modifier.clickable(role = Role.Button) { show = !show }, style = Divan.type.micro, color = c.goldInk)
    }
}

private val PERSIAN = Regex("[\\u0600-\\u06FF]")

/** One metadata value, typed by its field (§23.2, §23.12 values). */
@Composable
fun FieldValue(f: FieldDef, v: JsonElement?, m: ArchiveMaps, masked: Boolean = false) {
    val c = Divan.colors
    val companies = rememberCompanies()
    val uri = LocalUriHandler.current
    val strong = Divan.type.small.copy(fontWeight = FontWeight.SemiBold)
    val figStyle = Divan.type.figureSmall.copy(fontWeight = FontWeight.SemiBold)
    if (masked) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            DIcon(DivanIcon.LOCK, size = 12.dp, tint = c.textMuted)
            if (!v.str.isNullOrBlank()) Fig(v.str!!, style = figStyle, color = c.textMuted) else Text("پنهان برای سطح تو", style = Divan.type.caption, color = c.textMuted)
        }
        return
    }
    if (emptyValue(v)) return Text("—", style = strong, color = c.textMuted)
    fun opt(k: String?) = f.options.firstOrNull { it.key == k }?.titleFa ?: k.orEmpty()
    when (f.type) {
        "money" -> v.obj?.let { Fig(moneyFig(it), style = figStyle, color = c.textPrimary) } ?: Fig(v.prim.orEmpty(), style = figStyle, color = c.textPrimary)
        "percent" -> Fig("${v.prim}%", style = figStyle, color = c.textPrimary)
        "number" -> Fig(v.prim?.toDoubleOrNull()?.let { if (it % 1.0 == 0.0) String.format(java.util.Locale.US, "%,d", it.toLong()) else v.prim } ?: v.prim.orEmpty(), style = figStyle, color = c.textPrimary)
        "date" -> Text(jDay(v.prim), style = strong, color = c.textPrimary)
        "date_range" -> Text(buildAnnotatedString { append(jDay(v.obj?.get("from").prim)); append(" تا "); append(jDay(v.obj?.get("to").prim)) }, style = strong, color = c.textPrimary)
        "enum" -> Text(opt(v.prim), style = strong, color = c.textPrimary)
        "multi_enum" -> FlowRow(horizontalArrangement = Arrangement.spacedBy(4.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            for (k in (v.arr?.mapNotNull { it.prim } ?: listOfNotNull(v.prim))) Text(opt(k), Modifier.clip(CircleShape).background(c.card).padding(horizontal = 8.dp, vertical = 2.dp), style = Divan.type.caption, color = c.textPrimary)
        }
        "boolean" -> Text(if (v.bool == true) "بله" else "نه", style = strong, color = c.textPrimary)
        "party" -> v.str?.let { PartyChip(it, m) } ?: Fig(v.toString(), style = figStyle)
        "company" -> Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            CoMark(v.prim, height = 11.dp, ink = c.textPrimary)
            Text(companyOf(companies, v.prim).nameFa, style = strong, color = c.textPrimary)
        }
        "ref" -> v.obj?.get("ref").str?.let { RefChip(it, note = v.obj?.get("kind").str?.let { k -> REF_KIND_FA[k] ?: k }) } ?: Fig(v.prim.orEmpty(), style = figStyle)
        "url" -> Fig(v.prim.orEmpty(), Modifier.clickable(role = Role.Button) { runCatching { uri.openUri(v.prim.orEmpty()) } }, style = figStyle, color = c.goldInk, maxLines = 3)
        "email" -> Fig(v.prim.orEmpty(), Modifier.clickable(role = Role.Button) { runCatching { uri.openUri("mailto:${v.prim}") } }, style = figStyle, color = c.goldInk, maxLines = 2)
        "phone" -> Fig(v.prim.orEmpty(), style = figStyle, color = c.textPrimary)
        "id_code", "iban" -> Masked4(v.prim.orEmpty())
        "long_text" -> Text(prose(v.prim.orEmpty()), style = Divan.type.small, color = c.textPrimary)
        else -> {
            val s = v.prim ?: v.toString()
            if (!PERSIAN.containsMatchIn(s)) Fig(s, style = figStyle, color = c.textPrimary, maxLines = 3) else Text(prose(s), style = strong, color = c.textPrimary)
        }
    }
}

/** A value as plain text (a value inside a row summary). */
fun plainValue(f: FieldDef, v: JsonElement?, m: ArchiveMaps): String = when {
    emptyValue(v) -> "—"
    f.type == "id_code" || f.type == "iban" -> last4(v.prim.orEmpty())
    f.type == "party" -> m.party(v.str)?.nameFa ?: v.prim.orEmpty()
    f.type == "ref" -> v.obj?.get("ref").prim.orEmpty()
    else -> v.prim ?: v.toString()
}

/** A refusal in Persian, next to what it refers to (sealed_record 409, held 423, schema_invalid 422 …). */
@Composable
fun ErrorLine(error: ApiException?, modifier: Modifier = Modifier) {
    if (error == null) return
    val c = Divan.colors
    Row(
        modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.softNegative).padding(12.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        DIcon(if (error.code == "held" || error.code == "sealed_record" || error.code == "clearance") DivanIcon.LOCK else DivanIcon.URGENT, Modifier.padding(top = 2.dp), size = 16.dp, tint = c.negative)
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(prose(archiveError(error)), style = Divan.type.small, color = c.textPrimary)
            Fig(error.code, style = Divan.type.figureSmall, color = c.textMuted)
        }
    }
}

/** A labelled block of a record page. */
@Composable
fun Panel(title: String, modifier: Modifier = Modifier, note: AnnotatedString? = null, ring: androidx.compose.ui.graphics.Color? = null, action: (@Composable () -> Unit)? = null, content: @Composable ColumnScope.() -> Unit) {
    val c = Divan.colors
    val shape = RoundedCornerShape(16.dp)
    Column(
        modifier.fillMaxWidth().clip(shape).background(c.card).then(if (ring != null) Modifier.border(1.dp, ring, shape) else Modifier).padding(14.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Column(Modifier.weight(1f)) {
                Text(title, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                if (note != null) Text(note, style = Divan.type.micro, color = c.textMuted)
            }
            action?.invoke()
        }
        content()
    }
}

/** The draft's suggestion, said as what it is: never filed by itself. */
@Composable
fun SuggestionLine(s: Suggestion?, m: ArchiveMaps) {
    if (s == null) return
    val c = Divan.colors
    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(4.dp), itemVerticalAlignment = Alignment.CenterVertically) {
        Row(
            Modifier.clip(CircleShape).background(c.softLearning).padding(horizontal = 8.dp, vertical = 2.dp),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            DIcon(if (s.by == "archivist") DivanIcon.AGENT else DivanIcon.SETTINGS, size = 12.dp, tint = c.learning)
            Text(if (s.by == "archivist") "پیشنهاد بایگان" else "پیشنهاد قاعده‌ها", style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = c.learning)
        }
        // One sentence, parts by «؛»: a middle dot beside a count reads as a Persian zero.
        val said = listOfNotNull(
            if (s.cls != null) "نوع: ${m.cls(s.cls)?.titleFa ?: s.cls}" else "نوع پیدا نشد",
            s.metadata.size.takeIf { it > 0 }?.let { "$it فیلد" },
            s.parties.takeIf { it.isNotEmpty() }?.let { ps -> "طرف: " + ps.joinToString("، ") { m.party(it)?.nameFa ?: it } },
        )
        Text(said.joinToString("؛ "), style = Divan.type.micro, color = c.textSecondary)
    }
}

// ------------------------------------------------------------------ inputs --
data class Opt(val v: String, val t: String, val figure: Boolean = false)

/** A select in the field style: the current option, the list in a menu. An unknown value stays shown as itself (a figure); a ref or a
 *  scope inside an option's words stays Latin. */
@Composable
fun Select(
    value: String?, options: List<Opt>, onChange: (String?) -> Unit, label: String, modifier: Modifier = Modifier,
    nullable: Boolean = false, none: String? = null, error: Boolean = false, enabled: Boolean = true,
) {
    val c = Divan.colors
    var open by remember { mutableStateOf(false) }
    val cur = options.firstOrNull { it.v == value }
    val empty = none ?: if (nullable) "— هیچ —" else "— انتخاب کن —"
    val shape = RoundedCornerShape(10.dp)
    Box(modifier) {
        Row(
            Modifier.fillMaxWidth().heightIn(min = 44.dp).clip(shape).background(c.tile).border(1.dp, if (error) c.negative else c.lineStrong, shape)
                .clickable(enabled = enabled, role = Role.DropdownList, onClickLabel = label) { open = true }
                .semantics { contentDescription = label }.padding(horizontal = 12.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            val ink = if (!enabled) c.textMuted else if (cur == null && value == null) c.textMuted else c.textPrimary
            when {
                cur != null && cur.figure -> Fig(cur.t, Modifier.weight(1f), style = Divan.type.figureSmall, color = ink)
                cur != null -> Text(prose(cur.t), Modifier.weight(1f), style = Divan.type.small, color = ink, maxLines = 1, overflow = TextOverflow.Ellipsis)
                value != null -> Fig(value, Modifier.weight(1f), style = Divan.type.figureSmall, color = ink)
                else -> Text(empty, Modifier.weight(1f), style = Divan.type.small, color = ink, maxLines = 1)
            }
            DIcon(DivanIcon.CHEVRON, size = 14.dp, tint = c.textMuted)
        }
        DropdownMenu(open, { open = false }, Modifier.widthIn(min = 200.dp), containerColor = c.overlay) {
            if (nullable || value == null) DropdownMenuItem(text = { Text(empty, style = Divan.type.small, color = c.textMuted) }, onClick = { open = false; onChange(null) })
            for (o in options) DropdownMenuItem(
                text = {
                    val ink = if (o.v == value) c.goldInk else c.textPrimary
                    if (o.figure) Fig(o.t, style = Divan.type.figureSmall, color = ink) else Text(prose(o.t), style = Divan.type.small, color = ink)
                },
                onClick = { open = false; onChange(o.v) },
            )
        }
    }
}

/** A field's label line: its title, a required mark, its type, and whether it is sensitive. */
@Composable
fun FieldLabel(title: String, required: Boolean = false, type: String? = null, sensitive: Boolean = false) {
    val c = Divan.colors
    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), itemVerticalAlignment = Alignment.CenterVertically) {
        Text(title, style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
        if (required) Text("*", style = Divan.type.caption, color = c.negative, modifier = Modifier.semantics { contentDescription = "لازم" })
        if (type != null) Text(type, style = Divan.type.micro, color = c.textMuted)
        if (sensitive) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(2.dp)) {
            DIcon(DivanIcon.LOCK, size = 10.dp, tint = c.textMuted)
            Text("حساس", style = Divan.type.micro, color = c.textMuted)
        }
    }
}

/** A date input: the Gregorian day typed (Latin figures), the Jalali day beside it (§23.12). */
@Composable
fun DateField(value: String?, onChange: (String?) -> Unit, label: String, modifier: Modifier = Modifier, error: Boolean = false) {
    val c = Divan.colors
    var text by remember(value) { mutableStateOf(value.orEmpty()) }
    val ok = value != null && Regex("^\\d{4}-\\d{2}-\\d{2}$").matches(value)
    Row(modifier, verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Box(Modifier.widthIn(min = 132.dp, max = 160.dp).semantics { contentDescription = label }) {
            com.coinepro.hq.designsystem.HqTextField(text, { t ->
                val x = t.filter { it.isDigit() || it == '-' }.map { ch -> "۰۱۲۳۴۵۶۷۸۹".indexOf(ch).takeIf { it >= 0 }?.digitToChar() ?: ch }.joinToString("")
                text = x
                onChange(x.ifBlank { null })
            }, "YYYY-MM-DD", Modifier.fillMaxWidth().then(if (error) Modifier.border(1.dp, c.negative, RoundedCornerShape(10.dp)) else Modifier), maxLength = 10, figure = true)
        }
        if (ok) Text(jDay(value), style = Divan.type.caption, color = c.textSecondary)
    }
}

/** A §23 action: a failed call says its §23.11 code in Persian ([archiveError]) instead of the server's sentence. */
fun ActionRunner.archive(toasts: Toasts, onError: ((ApiException) -> Boolean)? = null, block: suspend () -> Unit) =
    run(onError = { e -> if (onError?.invoke(e) != true) toasts.error(archiveError(e)) }, block = block)

/** A small labelled fact (the record's own facts). */
@Composable
fun FactLine(label: String, content: @Composable () -> Unit) {
    val c = Divan.colors
    Row(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.Top) {
        Text(label, Modifier.widthIn(min = 56.dp).padding(top = 2.dp), style = Divan.type.caption, color = c.textMuted)
        Box(Modifier.weight(1f)) { content() }
    }
}

/** An icon in a tinted square. */
@Composable
fun IconSquare(icon: DivanIcon, size: androidx.compose.ui.unit.Dp = 32.dp) {
    val c = Divan.colors
    Box(Modifier.size(size).clip(RoundedCornerShape(10.dp)).background(c.tile), contentAlignment = Alignment.Center) { DIcon(icon, size = size * 0.5f, tint = c.goldInk) }
}
