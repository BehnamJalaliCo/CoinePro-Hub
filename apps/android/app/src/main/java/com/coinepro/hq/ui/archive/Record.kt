package com.coinepro.hq.ui.archive

import android.content.Intent
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.pdf.PdfRenderer
import android.os.ParcelFileDescriptor
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.core.content.FileProvider
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.actorFa
import com.coinepro.hq.core.media.describe
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.ArchiveRecord
import com.coinepro.hq.core.net.FieldDef
import com.coinepro.hq.core.net.FileBytes
import com.coinepro.hq.core.net.LinkTarget
import com.coinepro.hq.core.net.PartyRole
import com.coinepro.hq.core.net.RecordFile
import com.coinepro.hq.core.net.RecordLink
import com.coinepro.hq.core.net.RecordVersion
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.Md
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.Seal
import com.coinepro.hq.designsystem.SealState
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.activity
import com.coinepro.hq.ui.cartable.SealButton
import com.coinepro.hq.ui.companyOf
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.v14.HqSheet
import com.coinepro.hq.ui.v16.prose
import com.coinepro.hq.ui.v17.ActorAvatar
import com.coinepro.hq.ui.v17.RefChip
import com.coinepro.hq.ui.v17.RefTone
import java.io.File
import java.io.IOException
import java.time.LocalDate
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

// A record of the archive (contract §23.1), mirroring apps/web/src/components/v20/record.tsx: metadata by its class, files and versions,
// links, holds, the seal and the level, retention and reminders, and the access log; a draft is completed and filed here; a disposed
// record shows only its tombstone.

/** Values that need a whole row even on a phone; the rest sit two to a row. */
private val WIDE = setOf("long_text", "date_range", "party", "url", "ref", "multi_enum", "email", "text")

/** The `fields` a refused write named, as the form reads them. */
private fun ApiException.errs(): Map<String, String> = fields

@Composable
fun RecordScreen(ref: String) {
    val q = rememberQuery("archive:record:$ref", "archive") { record(ref) }
    val arch = rememberArchive()
    val r = refresher(q, arch.q)
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        val x = q.data
        val e = q.error
        when {
            x == null && e != null && (e.code == "clearance" || e.status == 404) -> item {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Fig(ref, style = Divan.type.figureSmall, color = Divan.colors.textMuted)
                    Empty(com.coinepro.hq.core.net.archiveError(e), icon = if (e.code == "clearance") DivanIcon.LOCK else DivanIcon.SEARCH, body = "از بایگانی جستجو کن یا فیلترها را عوض کن.")
                }
            }
            x == null && e != null -> item { ErrorBlock(e, { q.refresh() }) }
            x == null || arch.q.data == null -> item { Skeleton(Modifier.fillMaxWidth().height(420.dp), radius = 16.dp) }
            x.state == "disposed" -> item { TombstoneView(x, arch.m) }
            else -> {
                val m = arch.m
                item { RecordHeader(x, m) }
                if (x.state == "draft") item(key = "draft:${x.version}") { DraftPanel(x, m) { q.set(it) } }
                if (x.state != "draft") item { MetadataPanel(x, m) { q.set(it) } }
                item { FilesPanel(x, m) { q.set(it) } }
                item { LinksPanel(x, m) { q.set(it) } }
                item { SealPanel(x, m) { q.set(it) } }
                if (x.holds.isNotEmpty()) item { HoldsPanel(x) }
                if (x.state != "draft") item { RetentionPanel(x, m) }
                item { AccessPanel(x, m) }
            }
        }
    }
}

@Composable
private fun RecordHeader(r: ArchiveRecord, m: ArchiveMaps) {
    val c = Divan.colors
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(2.dp), itemVerticalAlignment = Alignment.CenterVertically) {
            Fig(r.ref, style = Divan.type.figureSmall, color = c.textMuted)
            ClassTag(r.cls, m)
            ScopeTag(r.scope)
        }
        Text(prose(r.titleFa), style = Divan.type.h2, color = c.textPrimary)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp), itemVerticalAlignment = Alignment.CenterVertically) {
            StatePill(r.state)
            LevelPill(r.level, m)
            if (r.holds.isNotEmpty()) Pill(if (r.holds.size > 1) "توقیف (${r.holds.size})" else "توقیف", Tone.NEG, icon = DivanIcon.LOCK)
            if (r.source.kind == "system") Pill("بایگانی خودکار", Tone.LAPIS, icon = DivanIcon.SETTINGS)
            r.docDate?.let { Text(buildAnnotatedString { append("تاریخ سند "); append(jDay(it)) }, style = Divan.type.caption, color = c.textMuted) }
        }
    }
}

// ------------------------------------------------------------------ a disposed record --
/** After the owner's disposal seal only the tombstone stays: ref, class, title, dates, hashes and the decision (§23.0). */
@Composable
fun TombstoneView(r: ArchiveRecord, m: ArchiveMaps) {
    val c = Divan.colors
    val t = r.tombstone
    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        RecordHeader(r, m)
        Panel("سنگ‌نشان", note = buildAnnotatedString { append("فایل‌ها با کارت امحا نابود شدند؛ این سنگ‌نشان میماند.") }) {
            FactLine("تصمیم") { t?.decision?.takeIf { it.isNotBlank() }?.let { RefChip(it) } ?: Text("—", style = Divan.type.caption) }
            FactLine("امحا") { Text(jStamp(t?.at, year = true), style = Divan.type.caption, color = c.textPrimary) }
            FactLine("ساخته") { Text(jStamp(r.createdAt, year = true), style = Divan.type.caption, color = c.textPrimary) }
            FactLine("ثبت") { Text(jStamp(r.filedAt, year = true), style = Divan.type.caption, color = c.textPrimary) }
            if (!t?.hashes.isNullOrEmpty()) {
                Text("hash فایل‌های نابودشده", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.goldInk)
                for (h in t!!.hashes) Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(c.tile).padding(horizontal = 12.dp, vertical = 8.dp)) {
                    Fig(h.name, style = Divan.type.figureSmall, color = c.textPrimary)
                    Fig(h.sha256, style = Divan.type.figureSmall, color = c.textMuted, maxLines = 2)
                }
            }
        }
    }
}

// ------------------------------------------------------------------ a draft: complete it, then file it --
@Composable
private fun DraftPanel(r: ArchiveRecord, m: ArchiveMaps, onSaved: (ArchiveRecord) -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val save = rememberAction()
    val file = rememberAction()
    var d by remember(r.version) { mutableStateOf(draftOf(r)) }
    var errors by remember { mutableStateOf<Map<String, String>>(emptyMap()) }
    var failure by remember { mutableStateOf<ApiException?>(null) }
    val cls = m.cls(d.cls)
    val lacking = cls?.let { missingRequired(it.fields, d.metadata) }.orEmpty()
    val s = r.suggestion
    fun apply() {
        if (s == null) return
        val k = d.cls ?: s.cls
        val nc = m.cls(k)
        val md = d.metadata.toMutableMap()
        for ((key, v) in s.metadata) if (emptyValue(md[key])) md[key] = v
        d = d.copy(
            cls = k, titleFa = s.titleFa ?: d.titleFa, metadata = md,
            level = if (nc != null && m.rank(nc.defaultLevel) > m.rank(d.level)) nc.defaultLevel else d.level,
            folder = d.folder ?: nc?.let { m.folders.firstOrNull { f -> f.scope == r.scope && nc.key in f.classes }?.ref },
        )
    }
    fun body(): JsonObject = buildJsonObject {
        if (d.cls != r.cls) put("class", d.cls)
        put("title_fa", d.titleFa.trim())
        put("metadata", JsonObject(metaFor(m, d)))
        put("folder", d.folder)
        put("parties", partiesJson(partiesFor(m, d, s?.parties.orEmpty())))
        if (d.level != null && d.level != r.level) put("level", d.level)
    }
    fun fail(e: ApiException) { errors = e.errs(); failure = e }
    Panel("پیش‌نویس، منتظر ثبت", note = buildAnnotatedString { append("بایگان طبقه‌بندی میکند و مشخصات را کامل؛ ثبت با توست. پیشنهاد هیچ‌وقت خودش ثبت نمیشود.") }, ring = c.lineTahrir) {
        if (s != null) Row(
            Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.softLearning).padding(12.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.Top,
        ) {
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                SuggestionLine(s, m)
                s.noteFa?.let { Text(prose(it), style = Divan.type.caption, color = c.textPrimary) }
                HqButton("پیشنهاد را بگذار", { apply() }, size = BtnSize.SM, icon = DivanIcon.EDIT)
            }
        }
        RecordForm(r.scope, d, { d = it }, errors, m)
        ErrorLine(failure)
        if (cls != null && lacking.isNotEmpty()) Text("برای ثبت کم است: ${lacking.joinToString("، ") { "«${it.titleFa}»" }}.", style = Divan.type.caption, color = c.textMuted)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            HqButton("ثبت کن", {
                errors = emptyMap(); failure = null
                file.run(onError = ::fail) {
                    val saved = env.api.patchRecord(r, body())
                    val out = env.api.fileDraft(saved)
                    env.cache.invalidate("archive", "decisions")
                    onSaved(out)
                    toasts.ok("سند ${r.ref} ثبت شد.")
                }
            }, variant = BtnVariant.PRIMARY, icon = DivanIcon.SEAL, enabled = cls != null && lacking.isEmpty() && d.titleFa.isNotBlank(), loading = file.busy)
            HqButton("ذخیره‌ی پیش‌نویس", {
                errors = emptyMap(); failure = null
                save.run(onError = ::fail) {
                    val out = env.api.patchRecord(r, body())
                    env.cache.invalidate("archive")
                    onSaved(out)
                    toasts.info("پیش‌نویس ذخیره شد.")
                }
            }, enabled = d.titleFa.isNotBlank(), loading = save.busy)
        }
    }
}

internal fun partiesJson(xs: List<PartyRole>) = JsonArray(xs.map { p -> buildJsonObject { put("party", p.party); put("role_fa", p.roleFa) } })

// ------------------------------------------------------------------ metadata, by the class's fields --
@Composable
private fun MetadataPanel(r: ArchiveRecord, m: ArchiveMaps, onSaved: (ArchiveRecord) -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val action = rememberAction()
    var editing by remember(r.version) { mutableStateOf<RecordDraft?>(null) }
    var errors by remember { mutableStateOf<Map<String, String>>(emptyMap()) }
    var failure by remember { mutableStateOf<ApiException?>(null) }
    val cls = m.cls(r.cls)
    val fields = cls?.fields.orEmpty()
    val known = fields.map { it.key }.toSet()
    val extra = r.metadata.keys.filter { it !in known }
    val held = r.holds.isNotEmpty()
    val sealed = r.state == "sealed"
    Panel(
        "مشخصات",
        note = cls?.let { buildAnnotatedString { append("طبق نوع «${it.titleFa}»، نسخه‌ی "); fig("${r.classVersion ?: it.version}") } },
        action = {
            when {
                editing != null -> {}
                sealed -> Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    DIcon(DivanIcon.LOCK, size = 12.dp, tint = c.textMuted)
                    Text("مُهرشده؛ اصلاح یعنی نسخه‌ی تازه", style = Divan.type.micro, color = c.textMuted)
                }
                else -> HqButton("ویرایش", { editing = draftOf(r); errors = emptyMap(); failure = null }, variant = BtnVariant.GHOST, size = BtnSize.SM, icon = DivanIcon.EDIT, enabled = !held)
            }
        },
    ) {
        val e = editing
        if (e != null) {
            RecordForm(r.scope, e, { editing = it }, errors, m, lockClass = true, hideLevel = true)
            ErrorLine(failure)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                HqButton("ذخیره", {
                    errors = emptyMap(); failure = null
                    action.run(onError = { x -> errors = x.errs(); failure = x }) {
                        val out = env.api.patchRecord(r, buildJsonObject {
                            put("title_fa", e.titleFa.trim()); put("metadata", JsonObject(metaFor(m, e))); put("folder", e.folder); put("parties", partiesJson(partiesFor(m, e)))
                        })
                        env.cache.invalidate("archive")
                        onSaved(out)
                        editing = null
                        toasts.info("مشخصات ذخیره شد.")
                    }
                }, variant = BtnVariant.PRIMARY, loading = action.busy)
                HqButton("انصراف", { editing = null }, variant = BtnVariant.GHOST)
            }
        } else {
            val shown = fields.filter { it.status == "active" || r.metadata[it.key] != null } +
                extra.map { FieldDef(it, it, "text", status = "retired") }
            // Two to a row, a wide value alone; a short value waits for the next short one (dense, as the web's grid).
            val rows = ArrayList<List<FieldDef>>()
            var pending: FieldDef? = null
            for (f in shown) {
                if (f.type in WIDE) rows += listOf(f)
                else if (pending != null) { rows += listOf(pending, f); pending = null }
                else pending = f
            }
            pending?.let { rows += listOf(it) }
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                for (row in rows) Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    for (f in row) Column(
                        Modifier.weight(1f).clip(RoundedCornerShape(12.dp)).background(c.tile).padding(10.dp),
                        verticalArrangement = Arrangement.spacedBy(4.dp),
                    ) {
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                            Text(f.titleFa + if (f.status == "retired") " (بازنشسته)" else "", style = Divan.type.micro, color = c.textMuted, maxLines = 1, overflow = TextOverflow.Ellipsis)
                            if (f.sensitive) DIcon(DivanIcon.LOCK, size = 10.dp, tint = c.textMuted)
                        }
                        FieldValue(f, r.metadata[f.key], m, masked = f.key in r.masked)
                    }
                    if (row.size == 1 && row[0].type !in WIDE) Box(Modifier.weight(1f))
                }
            }
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                FactLine("پوشه") { FolderPath(r.folder, m) }
                FactLine("طرف‌ها") {
                    if (r.parties.isEmpty()) Text("—", style = Divan.type.caption, color = c.textMuted)
                    else FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) { for (p in r.parties) PartyChip(p.party, m, p.roleFa) }
                }
                FactLine("منبع") {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        Text(SOURCE_KIND[r.source.kind] ?: r.source.kind, style = Divan.type.caption, color = c.textPrimary)
                        r.source.ref?.let { Fig(it, style = Divan.type.figureSmall, color = c.textMuted) }
                    }
                }
                FactLine("ثبت") {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        ActorAvatar(r.createdBy, size = 18.dp)
                        Text(buildAnnotatedString { append(actorFa(r.createdBy) + "، "); append(jStamp(r.filedAt ?: r.createdAt, year = true)) }, style = Divan.type.caption, color = c.textPrimary)
                    }
                }
            }
        }
    }
}

// ------------------------------------------------------------------ files and versions --
@Composable
private fun FilesPanel(r: ArchiveRecord, m: ArchiveMaps, onSaved: (ArchiveRecord) -> Unit) {
    var view by remember { mutableStateOf<RecordFile?>(null) }
    var adding by remember { mutableStateOf(false) }
    Panel(
        "فایل‌ها و نسخه‌ها", note = buildAnnotatedString { append("هر فایل با "); fig("SHA-256"); append(" خودش؛ مُهر روی manifest نسخه‌ی جاری است.") },
        action = { if (r.state != "draft") HqButton("نسخه‌ی تازه", { adding = true }, variant = BtnVariant.GHOST, size = BtnSize.SM, icon = DivanIcon.ADD) },
    ) {
        for (v in r.versions.sortedByDescending { it.n }) VersionCard(r, v) { view = it }
    }
    view?.let { f ->
        HqSheet({ view = null }, f.name, sub = null) { FileViewer(r, f, m) }
    }
    if (adding) HqSheet({ adding = false }, "نسخه‌ی تازه", sub = "اصلاح هیچ‌وقت روی نسخه‌ی قبلی نیست: همه‌ی فایل‌های نسخه‌ی تازه را بیاور؛ نسخه‌ی قبلی جایگزین‌شده میماند.") {
        VersionContent(r, { adding = false }) { onSaved(it) }
    }
}

@Composable
private fun VersionCard(r: ArchiveRecord, v: RecordVersion, onView: (RecordFile) -> Unit) {
    val c = Divan.colors
    val current = v.n == r.currentVersion
    Column(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(if (current) c.tile else c.page).padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(4.dp), itemVerticalAlignment = Alignment.CenterVertically) {
            Text("نسخه‌ی ${v.n}", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
            if (current) Pill("جاری", Tone.POS, dot = true) else Pill("جایگزین‌شده", Tone.NEUTRAL, icon = DivanIcon.REFRESH)
            if (v.sealed) Pill("مُهرشده", Tone.GOLD, icon = DivanIcon.SEAL)
        }
        Text(buildAnnotatedString { append(jStamp(v.createdAt, year = true)); append("، " + actorFa(v.createdBy)) }, style = Divan.type.micro, color = c.textMuted)
        v.noteFa?.let { Text(prose(it), style = Divan.type.caption, color = c.textSecondary) }
        for (f in v.files) Row(
            Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(c.card).clickable(role = Role.Button, onClickLabel = "نمایش ${f.name}") { onView(f) }.padding(horizontal = 10.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            DIcon(if (f.mime.startsWith("image/")) DivanIcon.IMAGE else DivanIcon.REPORT, size = 16.dp, tint = c.textMuted)
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Fig(f.name, style = Divan.type.figureSmall, color = c.textPrimary)
                FileFacts(f)
            }
            Text("نمایش", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.goldInk)
        }
        Text(buildAnnotatedString { append("manifest: "); fig(shaShort(v.manifestSha256)) }, style = Divan.type.micro, color = c.textMuted)
    }
}

/** One file, as the hub serves it: a level with `step_up_to_view` waits for the passkey (once, for this record); every view is a row
 *  of the access log, and a watermarked level comes back watermarked. Images show here; a PDF's pages are drawn here too, or it opens
 *  in another app. */
@Composable
fun FileViewer(r: ArchiveRecord, f: RecordFile, m: ArchiveMaps) {
    val env = LocalEnv.current
    val ctx = LocalContext.current
    val act = activity()
    val c = Divan.colors
    val scope = rememberCoroutineScope()
    val lvl = m.level(r.level)
    val needs = lvl?.stepUpToView == true
    var bytes by remember(f.fileId) { mutableStateOf<FileBytes?>(null) }
    var busy by remember(f.fileId) { mutableStateOf(false) }
    var error by remember(f.fileId) { mutableStateOf<ApiException?>(null) }
    fun load(withPasskey: Boolean) {
        if (busy) return
        busy = true; error = null
        scope.launch {
            try {
                bytes = env.api.recordFile(r.ref, f.fileId, if (withPasskey) { a, t -> env.auth.stepUp(act, a, t) } else null)
                env.cache.invalidate("access:${r.ref}")
            } catch (e: ApiException) {
                error = e
            } finally {
                busy = false
            }
        }
    }
    LaunchedEffect(f.fileId) { if (!needs) load(false) }
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        FileFacts(f)
        if (lvl?.watermark == true) Row(
            Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.softWarning).padding(12.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            DIcon(DivanIcon.INFO, size = 16.dp, tint = c.warning)
            Text(buildAnnotatedString { append("این نسخه ته‌نقش دارد: نام تو، زمان دیدن و "); fig(r.ref); append(" روی هر صفحه. هر دیدن در دفتر دسترسی ثبت میشود.") }, style = Divan.type.caption, color = c.textPrimary)
        } else Text("هر دیدن در دفتر دسترسی ثبت میشود.", style = Divan.type.caption, color = c.textMuted)
        val b = bytes
        if (needs && b == null) Column(
            Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(c.tile).padding(20.dp),
            horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Box(Modifier.size(48.dp).clip(CircleShape).background(c.softNegative), contentAlignment = Alignment.Center) { DIcon(DivanIcon.LOCK, size = 22.dp, tint = c.negative) }
            Text("دیدن سند «${lvl?.titleFa}» با اثر انگشت است", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, textAlign = TextAlign.Center)
            Text(buildAnnotatedString { append("یک بار، فقط برای همین سند ("); fig("archive.view"); append("، هدف "); fig(r.ref); append(").") }, style = Divan.type.caption, color = c.textMuted, textAlign = TextAlign.Center)
            HqButton("با اثر انگشت باز کن", { load(true) }, variant = BtnVariant.PRIMARY, icon = DivanIcon.LOCK, loading = busy)
        }
        ErrorLine(error)
        if (busy && b == null && !needs) Skeleton(Modifier.fillMaxWidth().height(280.dp), radius = 12.dp)
        if (b != null) {
            if (b.mime.startsWith("image/") || f.mime.startsWith("image/")) {
                val bmp = remember(b) { runCatching { BitmapFactory.decodeByteArray(b.bytes, 0, b.bytes.size) }.getOrNull() }
                if (bmp != null) Image(bmp.asImageBitmap(), f.name, Modifier.fillMaxWidth().heightIn(max = 560.dp).clip(RoundedCornerShape(12.dp)).background(c.page), contentScale = ContentScale.Fit)
                else Text("این تصویر اینجا باز نشد.", style = Divan.type.caption, color = c.textMuted)
            } else PdfPages(b, f)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                HqButton("باز کردن در برنامه‌ی دیگر", {
                    scope.launch {
                        runCatching {
                            val name = f.name.replace(Regex("[^\\p{L}\\p{N}._-]"), "_").ifBlank { "file" }
                            val out = withContext(Dispatchers.IO) { File(env.media.scratch("shared"), name).apply { writeBytes(b.bytes) } }
                            val uri = FileProvider.getUriForFile(ctx, "${ctx.packageName}.files", out)
                            val view = Intent(Intent.ACTION_VIEW).setDataAndType(uri, f.mime.ifBlank { b.mime }).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                            ctx.startActivity(Intent.createChooser(view, f.name).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                        }.onFailure { com.coinepro.hq.core.diag.Diag.note("app", com.coinepro.hq.core.diag.LEVEL_WARNING, "file not opened", it::class.java.simpleName) }
                    }
                }, icon = DivanIcon.SHARE, size = BtnSize.SM)
            }
        }
    }
}

/** A PDF's pages drawn on the phone (PdfRenderer); when the platform cannot draw it, a line says so and the file opens elsewhere. */
@Composable
private fun PdfPages(b: FileBytes, f: RecordFile) {
    val ctx = LocalContext.current
    val c = Divan.colors
    val pages = remember(b) { mutableStateListOf<Bitmap>() }
    var failed by remember(b) { mutableStateOf(false) }
    LaunchedEffect(b) {
        val out = withContext(Dispatchers.IO) {
            runCatching {
                val tmp = File(ctx.cacheDir, "archive-view").apply { mkdirs() }.let { File(it, "page.pdf") }
                tmp.writeBytes(b.bytes)
                try {
                    ParcelFileDescriptor.open(tmp, ParcelFileDescriptor.MODE_READ_ONLY).use { fd ->
                        PdfRenderer(fd).use { pdf ->
                            (0 until minOf(pdf.pageCount, 12)).map { i ->
                                pdf.openPage(i).use { p ->
                                    val w = 1080
                                    val h = (w.toFloat() * p.height / p.width).toInt().coerceAtLeast(1)
                                    Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888).also { bmp ->
                                        bmp.eraseColor(android.graphics.Color.WHITE)
                                        p.render(bmp, null, null, PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY)
                                    }
                                }
                            }
                        }
                    }
                } finally {
                    tmp.delete()
                }
            }.getOrNull()
        }
        if (out.isNullOrEmpty()) failed = true else pages.addAll(out)
    }
    when {
        failed -> Column(
            Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(c.tile).padding(20.dp),
            horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            DIcon(DivanIcon.REPORT, size = 28.dp, tint = c.goldInk)
            Text("فایل آماده است؛ با برنامه‌ی دیگری بازش کن.", style = Divan.type.caption, color = c.textSecondary)
        }
        pages.isEmpty() -> Skeleton(Modifier.fillMaxWidth().height(280.dp), radius = 12.dp)
        else -> Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            pages.forEachIndexed { i, p -> Image(p.asImageBitmap(), "${f.name}، صفحه‌ی ${i + 1}", Modifier.fillMaxWidth().clip(RoundedCornerShape(8.dp)), contentScale = ContentScale.FillWidth) }
        }
    }
    DisposableEffect(b) { onDispose { pages.forEach { it.recycle() } } }
}

/** A correction: every file of the new version, uploaded, and what changed. */
@Composable
private fun VersionContent(r: ArchiveRecord, onClose: () -> Unit, onSaved: (ArchiveRecord) -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val ctx = LocalContext.current
    val c = Divan.colors
    val scope = rememberCoroutineScope()
    val action = rememberAction()
    val files = remember { mutableStateListOf<Triple<String, String?, Int>>() }
    var note by remember { mutableStateOf("") }
    var failure by remember { mutableStateOf<ApiException?>(null) }
    val pick = rememberLauncherForActivityResult(ActivityResultContracts.OpenMultipleDocuments()) { uris ->
        scope.launch {
            for (u in uris.take(20)) {
                val d = withContext(Dispatchers.IO) { ctx.contentResolver.describe(u) }
                val i = files.size
                files.add(Triple(d.name, null, 0))
                try {
                    val ref = withContext(Dispatchers.IO) { env.api.upload(d.name, d.mime, d.size, { ctx.contentResolver.openInputStream(u) ?: throw IOException("unreadable") }) }
                    files[i] = Triple(d.name, ref.id, 100)
                } catch (e: ApiException) {
                    failure = e
                } catch (e: IOException) {
                    failure = ApiException(0, "upload_failed", "فایل خوانده نشد.")
                }
            }
        }
    }
    val refused = failure?.takeIf { it.code == "secret_in_document" }?.let { (it.fields.keys + it.fieldKeys).firstOrNull() }
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        HqButton("انتخاب فایل", { pick.launch(arrayOf("*/*")) }, icon = DivanIcon.ATTACH)
        for ((name, id, _) in files) Row(
            Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(if (refused == name) c.softNegative else c.tile).padding(horizontal = 12.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Fig(name, Modifier.weight(1f), style = Divan.type.figureSmall, color = c.textPrimary)
            Fig(if (id != null) "ok" else "…", style = Divan.type.figureSmall, color = c.textMuted)
        }
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            FieldLabel("چه چیزی عوض شد")
            HqTextField(note, { note = it }, "مثلاً: الحاقیه‌ی ۲، کمیسیون تازه", Modifier.fillMaxWidth(), singleLine = false, minLines = 3, maxLength = 2000)
        }
        if (refused != null) Text(buildAnnotatedString { append("«"); fig(refused); append("» رد شد: الگوی رمز، کلید خصوصی یا عبارت بازیابی در آن بود. ذخیره نشد و هیچ بخشی از آن ثبت نشد.") },
            Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.softNegative).padding(12.dp), style = Divan.type.caption, color = c.negative)
        else ErrorLine(failure)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            HqButton("نسخه‌ی تازه را ثبت کن", {
                failure = null
                action.run(onError = { failure = it }) {
                    val out = env.api.addVersion(r.ref, files.mapNotNull { it.second }, note.trim())
                    env.cache.invalidate("archive")
                    onSaved(out)
                    toasts.ok(if (r.state == "sealed") "نسخه‌ی تازه آمد؛ نسخه‌ی مُهرشده جایگزین شد و سند دوباره منتظر مُهر است." else "نسخه‌ی تازه آمد.")
                    onClose()
                }
            }, variant = BtnVariant.PRIMARY, icon = DivanIcon.ADD, enabled = files.isNotEmpty() && files.all { it.second != null } && note.isNotBlank(), loading = action.busy)
            HqButton("انصراف", onClose, variant = BtnVariant.GHOST)
        }
    }
}

// ------------------------------------------------------------------ links --
@Composable
private fun LinksPanel(r: ArchiveRecord, m: ArchiveMaps, onSaved: (ArchiveRecord) -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val action = rememberAction()
    val kinds = m.schema?.linkKinds.orEmpty().filter { it.status != "retired" }
    var kind by remember { mutableStateOf<String?>(null) }
    val k = kinds.firstOrNull { it.key == kind } ?: kinds.firstOrNull()
    var toKind by remember { mutableStateOf<String?>(null) }
    val tk = toKind?.takeIf { k != null && it in k.toKinds } ?: k?.toKinds?.firstOrNull() ?: "record"
    var to by remember { mutableStateOf("") }
    var failure by remember { mutableStateOf<ApiException?>(null) }
    var removing by remember { mutableStateOf<RecordLink?>(null) }
    val held = r.holds.isNotEmpty()
    Panel("پیوندها", note = buildAnnotatedString { append(if (held) "توقیف: پیوندها هم تا آزاد شدن دست نمیخورند." else "پیوندی که با نسخه‌ی مُهرشده آمده برداشته نمیشود.") }) {
        if (r.links.isEmpty()) Text("پیوندی ندارد.", style = Divan.type.caption, color = c.textMuted)
        for (l in r.links) {
            val lk = m.linkKind(l.kind)
            val t = l.target
            Row(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(c.tile).padding(horizontal = 10.dp, vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(4.dp), itemVerticalAlignment = Alignment.CenterVertically) {
                        Text(if (l.inverse) lk?.inverseFa ?: l.kind else lk?.titleFa ?: l.kind, style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
                        RefChip(t.ref, note = if (t.kind != "record") REF_KIND_FA[t.kind] ?: t.kind else null)
                    }
                    l.titleFa?.let { Text(prose(it), style = Divan.type.caption, color = c.textPrimary, maxLines = 1, overflow = TextOverflow.Ellipsis) }
                }
                when {
                    l.sealed -> Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(3.dp)) {
                        DIcon(DivanIcon.LOCK, size = 12.dp, tint = c.textMuted)
                        Text("مُهرشده", style = Divan.type.micro, color = c.textMuted)
                    }
                    l.inverse -> Text("از آن سو", style = Divan.type.micro, color = c.textMuted)
                    else -> DIcon(DivanIcon.CLOSE, Modifier.clickable(enabled = !held, role = Role.Button, onClickLabel = "برداشتن پیوند ${t.ref}") { removing = l }, size = 16.dp, tint = if (held) c.disabledText else c.textMuted)
                }
            }
        }
        if (r.state != "draft" && k != null) Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Labelled("نوع پیوند", Modifier.weight(1f)) { Select(k.key, kinds.map { Opt(it.key, it.titleFa) }, { kind = it }, "نوع پیوند", Modifier.fillMaxWidth()) }
                Labelled("به", Modifier.weight(1f)) { Select(tk, k.toKinds.map { Opt(it, REF_KIND_FA[it] ?: it) }, { toKind = it }, "مقصد پیوند از چه نوع", Modifier.fillMaxWidth()) }
            }
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                HqTextField(to, { to = it.uppercase() }, when (tk) { "record" -> "AR-000000"; "case" -> "LC-0001"; "decision" -> "D-000000"; else -> "" }, Modifier.weight(1f), maxLength = 40, figure = true)
                HqButton("پیوند", {
                    failure = null
                    action.run(onError = { failure = it }) {
                        val out = env.api.link(r.ref, k.key, LinkTarget(tk, to.trim()))
                        env.cache.invalidate("archive")
                        onSaved(out)
                        to = ""
                        toasts.info("پیوند اضافه شد.")
                    }
                }, icon = DivanIcon.ADD, size = BtnSize.SM, enabled = to.isNotBlank() && !held, loading = action.busy)
            }
        }
        ErrorLine(failure)
    }
    removing?.let { l ->
        AlertDialog(
            onDismissRequest = { removing = null },
            containerColor = c.overlay,
            title = { Text("برداشتن پیوند", style = Divan.type.h3) },
            text = { Text(buildAnnotatedString { append("پیوند «${m.linkKind(l.kind)?.titleFa ?: l.kind}» به "); fig(l.target.ref); append(" برداشته میشود. خود سندها دست نمیخورند.") }, style = Divan.type.small, color = c.textSecondary) },
            confirmButton = {
                HqButton("بردار", {
                    action.run(onError = { removing = null; failure = it }) {
                        val out = env.api.unlink(r.ref, l.kind, l.target)
                        env.cache.invalidate("archive")
                        onSaved(out)
                        removing = null
                        toasts.info("پیوند برداشته شد.")
                    }
                }, variant = BtnVariant.DANGER, loading = action.busy)
            },
            dismissButton = { HqButton("نه", { removing = null }, variant = BtnVariant.GHOST) },
        )
    }
}

// ------------------------------------------------------------------ seal and level --
@Composable
private fun SealPanel(r: ArchiveRecord, m: ArchiveMaps, onSaved: (ArchiveRecord) -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val act = activity()
    val c = Divan.colors
    val companies = rememberCompanies()
    val co = companyOf(companies, r.scope)
    val seal = rememberAction()
    val change = rememberAction()
    var failure by remember { mutableStateOf<ApiException?>(null) }
    var level by remember { mutableStateOf<String?>(null) }
    val cur = r.current
    val held = r.holds.isNotEmpty()
    val lower = level != null && m.rank(level) < m.rank(r.level)
    Panel("مُهر و سطح") {
        when (r.state) {
            "sealed" -> Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Seal(r.scope, co.nameFa, co.nameEn, holding = co.holding, state = SealState.SEALED, size = 64.dp)
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text(buildAnnotatedString { append("مُهر خورد، "); append(jStamp(r.sealedAt, year = true)) }, style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                    Text(buildAnnotatedString { append("روی manifest نسخه‌ی ${r.currentVersion}: "); fig(shaShort(cur?.manifestSha256)) }, style = Divan.type.micro, color = c.textSecondary)
                    Text("اصلاح فقط با نسخه‌ی تازه؛ نسخه‌ی مُهرشده جایگزین‌شده میماند.", style = Divan.type.micro, color = c.textSecondary)
                }
            }
            "filed" -> Column(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(c.tile).padding(14.dp),
                horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                if (held) {
                    Seal(r.scope, co.nameFa, co.nameEn, holding = co.holding, state = SealState.READY, size = 64.dp)
                    Text("توقیف: مُهر هم تا آزاد شدن صبر میکند.", style = Divan.type.caption, color = c.textMuted, textAlign = TextAlign.Center)
                } else {
                    SealButton(r.scope, co.nameFa, co.nameEn, co.holding, busy = seal.busy, size = 80.dp) {
                        failure = null
                        seal.run(onError = { failure = it }) {
                            val out = env.api.sealRecord(r) { a, t -> env.auth.stepUp(act, a, t) }
                            env.cache.invalidate("archive")
                            onSaved(out)
                            toasts.ok("سند ${r.ref} مُهر شد؛ از این به بعد فقط نسخه‌ی تازه.")
                        }
                    }
                    Text(buildAnnotatedString { append("مُهر روی manifest نسخه‌ی ${r.currentVersion} است: "); fig(shaShort(cur?.manifestSha256)) }, style = Divan.type.micro, color = c.textSecondary, textAlign = TextAlign.Center)
                    Text(buildAnnotatedString { append("با اثر انگشت تو ("); fig("archive.seal"); append("). بعد از مُهر، سند و پیوندهایش دست نمیخورند.") }, style = Divan.type.micro, color = c.textMuted, textAlign = TextAlign.Center)
                }
            }
            else -> Text(if (r.state == "draft") "پیش‌نویس مُهر نمیشود؛ اول ثبتش کن." else "این سند مُهر نمیشود.", style = Divan.type.caption, color = c.textMuted)
        }
        if (r.state != "draft") Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("سطح فعلی", style = Divan.type.caption, color = c.textSecondary)
                LevelPill(r.level, m)
            }
            if (r.state == "sealed" && !held) Text("سطح بیرون از manifest است: عوض کردنش مُهر را برنمیدارد و فقط همین سطح عوض میشود.", style = Divan.type.micro, color = c.textMuted)
            if (held) Text("توقیف: سطح هم تا آزاد شدن عوض نمیشود.", style = Divan.type.micro, color = c.textMuted)
            else FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                for (l in m.levels.filter { it.key != r.level && it.status != "retired" }) {
                    val down = m.rank(l.key) < m.rank(r.level)
                    HqButton((if (down) "پایین به " else "بالا به ") + l.titleFa, { level = l.key }, variant = if (down) BtnVariant.SECONDARY else BtnVariant.GHOST, size = BtnSize.SM, icon = if (down) DivanIcon.LOCK else null)
                }
            }
        }
        ErrorLine(failure)
    }
    level?.let { to ->
        AlertDialog(
            onDismissRequest = { level = null },
            containerColor = c.overlay,
            title = { Text(if (lower) "پایین آوردن سطح" else "بالا بردن سطح", style = Divan.type.h3) },
            text = {
                Text(buildAnnotatedString {
                    append("از «${m.level(r.level)?.titleFa ?: r.level}» به «${m.level(to)?.titleFa ?: to}». ")
                    if (lower) {
                        append("فقط کار توست و با اثر انگشت بسته به همین سند، همین نسخه و همین سطح: "); fig("${r.ref}@${r.version}:$to")
                        append(". هر کس مجوز سطح تازه را دارد آن را خواهد دید.")
                        if (r.state == "sealed") append(" مُهر و manifest دست نمیخورند.")
                    } else append("بالا بردن اثر انگشت نمیخواهد؛ پایین آوردنش میخواهد.")
                }, style = Divan.type.small, color = c.textSecondary)
            },
            confirmButton = {
                HqButton(if (lower) "با اثر انگشت پایین بیاور" else "بالا ببر", {
                    failure = null
                    change.run(onError = { level = null; failure = it }) {
                        val out = if (lower) env.api.declassify(r, to) { a, t -> env.auth.stepUp(act, a, t) } else env.api.patchRecord(r, buildJsonObject { put("level", to) })
                        env.cache.invalidate("archive")
                        onSaved(out)
                        level = null
                        toasts.info("سطح سند «${m.level(to)?.titleFa ?: to}» شد.")
                    }
                }, variant = BtnVariant.PRIMARY, icon = if (lower) DivanIcon.LOCK else null, loading = change.busy)
            },
            dismissButton = { HqButton("انصراف", { level = null }, variant = BtnVariant.GHOST) },
        )
    }
}

// ------------------------------------------------------------------ holds, retention, reminders, access --
@Composable
private fun HoldsPanel(r: ArchiveRecord) {
    val c = Divan.colors
    val nav = LocalNav.current
    val q = rememberQuery("archive:holds:active:", "archive") { legalHolds("active") }
    Panel("توقیف قانونی", note = buildAnnotatedString { append("جز نسخه‌ی تازه هیچ تغییری پذیرفته نمیشود و امحا نمیشود.") }, ring = c.negative.copy(alpha = 0.45f)) {
        for (ref in r.holds) {
            val h = q.data?.firstOrNull { it.ref == ref }
            Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.softNegative).padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(4.dp), itemVerticalAlignment = Alignment.CenterVertically) {
                    DIcon(DivanIcon.LOCK, size = 14.dp, tint = c.negative)
                    Fig(ref, Modifier.clickable(role = Role.Button) { nav.go("archive-holds/$ref") }, style = Divan.type.figureSmall, color = c.negative)
                    h?.let { Text(prose(it.titleFa), style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary) }
                    h?.case?.let { RefChip(it, note = "پرونده") }
                }
                h?.reasonMd?.let { Md(it, style = Divan.type.caption) }
            }
        }
    }
}

private fun addKeep(d: String, years: Int, months: Int): String? = runCatching { LocalDate.parse(d.take(10)).plusYears(years.toLong()).plusMonths(months.toLong()).toString() }.getOrNull()

@Composable
private fun RetentionPanel(r: ArchiveRecord, m: ArchiveMaps) {
    val c = Divan.colors
    val rule = m.schema?.retention?.firstOrNull { it.ref == r.retention.rule }
    val cls = m.cls(r.cls)
    fun fieldFa(k: String) = cls?.fields?.firstOrNull { it.key == k }?.titleFa ?: k
    // When it ends: the review date the server gives, else the trigger plus the rule's term.
    val end = r.retention.reviewAt ?: rule?.takeIf { !it.permanent }?.let { rr -> r.retention.triggerAt?.let { addKeep(it, rr.years, rr.months) } }
    Panel("نگهداری و یادآور") {
        FactLine("قاعده") {
            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(4.dp), itemVerticalAlignment = Alignment.CenterVertically) {
                r.retention.rule?.let { RefChip(it) }
                if (rule != null) Text(prose(rule.titleFa), style = Divan.type.caption, color = c.textPrimary) else Text("—", style = Divan.type.caption, color = c.textMuted)
            }
        }
        r.retention.triggerAt?.let { FactLine("آغاز") { Text(jDay(it), style = Divan.type.caption, color = c.textPrimary) } }
        if (rule != null) FactLine("پایان") {
            Text(buildAnnotatedString {
                when {
                    rule.permanent -> append("دائمی")
                    end != null -> { append(jDay(end)); append("، " + (THEN_FA[rule.then] ?: rule.then)) }
                    else -> append((THEN_FA[rule.then] ?: rule.then) + "؛ " + when {
                        rule.trigger == "case_closed" -> "شمارش از بسته شدن پرونده"
                        rule.trigger == "superseded" -> "شمارش از جایگزین شدن"
                        rule.trigger.startsWith("field:") -> "شمارش از «${fieldFa(rule.trigger.removePrefix("field:"))}» که هنوز پر نشده"
                        else -> "شمارش از ثبت"
                    })
                }
            }, style = Divan.type.caption, color = c.textPrimary)
        }
        if (r.retention.disposable) FactLine("وضع") { Pill("نگهداری تمام شده؛ در کارت امحا", Tone.WARN, icon = DivanIcon.TIME) }
        for (x in r.reminders) {
            val left = daysTo(x.at)
            Row(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(c.tile).padding(horizontal = 10.dp, vertical = 8.dp),
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                DIcon(DivanIcon.TIME, size = 14.dp, tint = c.textSecondary)
                Text(fieldFa(x.field), style = Divan.type.caption, color = c.textPrimary)
                Text(jDay(x.at), Modifier.weight(1f), style = Divan.type.caption, color = c.textSecondary)
                Text(if (x.state == "done") "انجام شد" else daysLeftFa(left), style = Divan.type.caption,
                    color = when { x.state == "done" -> c.textMuted; left <= 7 -> c.negative; left <= 30 -> c.warning; else -> c.textSecondary })
            }
        }
    }
}

@Composable
private fun AccessPanel(r: ArchiveRecord, m: ArchiveMaps) {
    val c = Divan.colors
    val q = rememberQuery("archive:access:${r.ref}", "archive", "access:${r.ref}") { accessLog(r.ref) }
    val names = r.versions.flatMap { v -> v.files.map { it.fileId to it.name } }.toMap()
    Panel("دفتر دسترسی", note = buildAnnotatedString { append("چه کسی چه چیزی را کی دید یا دریافت کرد، و هر تغییر سطح؛ فقط تو میبینی.") }) {
        val xs = q.data
        when {
            xs == null && q.error != null -> ErrorLine(q.error)
            xs == null -> Skeleton(Modifier.fillMaxWidth().height(56.dp), radius = 10.dp)
            xs.isEmpty() -> Text("هنوز کسی فایل‌های این سند را باز نکرده و سطحش عوض نشده.", style = Divan.type.caption, color = c.textMuted)
            else -> for (a in xs) {
                val (fa, icon) = ACCESS_FA[a.action] ?: (a.action to DivanIcon.INFO)
                Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(c.tile).padding(horizontal = 10.dp, vertical = 8.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(4.dp), itemVerticalAlignment = Alignment.CenterVertically) {
                        DIcon(icon, size = 14.dp, tint = c.textSecondary)
                        Text(actorFa(a.actor), style = Divan.type.caption, color = c.textPrimary)
                        Text(fa, style = Divan.type.caption, color = c.textSecondary)
                        if (a.action == "level") {
                            Text("از", style = Divan.type.micro, color = c.textMuted); LevelPill(a.levelFrom, m)
                            Text("به", style = Divan.type.micro, color = c.textMuted); LevelPill(a.levelTo, m)
                        }
                        a.fileId?.let { Fig(names[it] ?: it, style = Divan.type.figureSmall, color = c.textMuted) }
                        a.version?.let { Text("نسخه‌ی $it", style = Divan.type.micro, color = c.textMuted) }
                    }
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text(jStamp(a.at), Modifier.weight(1f), style = Divan.type.micro, color = c.textMuted)
                        if (a.stepUp) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(2.dp)) {
                            DIcon(DivanIcon.LOCK, size = 11.dp, tint = c.goldInk)
                            Fig("passkey", style = Divan.type.figureSmall, color = c.goldInk)
                        }
                        if (a.watermarked) Text("ته‌نقش", style = Divan.type.micro, color = c.textMuted)
                    }
                }
            }
        }
    }
}
