package com.coinepro.hq.ui.archive

import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.media.describe
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.Intake
import com.coinepro.hq.core.net.RecordIn
import com.coinepro.hq.core.net.archiveError
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqSwitch
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.v17.ScopeChips
import java.io.IOException
import java.util.UUID
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

// «سند تازه» (contract §23.12 POST /archive/intake), mirroring the web's IntakeSheet: files picked with the system picker are uploaded
// (§17.1), then the hub scans them for secrets, hashes them, reads their text and suggests a class and metadata; the owner makes a draft
// or files it at once. A file with a secret pattern is refused by name, never by what it held.

private data class Up(val key: String, val uri: Uri, val name: String, val mime: String, val size: Long, val pct: Int = 0, val id: String? = null, val error: String? = null, val refused: Boolean = false)

private fun stem(n: String) = n.replace(Regex("\\.[A-Za-z0-9]+$"), "").replace(Regex("[-_]+"), " ")

/** The intake's content (a sheet). [picked0] are files already chosen (a share into the app, or the screenshots). */
@Composable
fun IntakeContent(scope0: String?, onClose: () -> Unit, picked0: List<Uri> = emptyList()) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val nav = LocalNav.current
    val ctx = LocalContext.current
    val c = Divan.colors
    val scopeRunner = rememberCoroutineScope()
    val arch = rememberArchive()
    val m = arch.m
    val action = rememberAction()
    var scope by remember { mutableStateOf(scope0) }
    val ups = remember { mutableStateListOf<Up>() }
    var got by remember { mutableStateOf<Intake?>(null) }
    var scanning by remember { mutableStateOf(false) }
    var touched by remember { mutableStateOf(false) }
    var form by remember { mutableStateOf(RecordDraft(null, "", emptyMap(), null, null)) }
    var errors by remember { mutableStateOf<Map<String, String>>(emptyMap()) }
    var failure by remember { mutableStateOf<ApiException?>(null) }
    // Kept for a retry after a lost answer; a refused attempt (any answer) gets a fresh key with the corrected body.
    var key by remember { mutableStateOf(UUID.randomUUID().toString()) }
    var split by remember { mutableStateOf(false) }
    val live = ups.filter { !it.refused }
    val ready = live.isNotEmpty() && live.all { it.id != null } && got != null
    val busy = ups.any { it.id == null && it.error == null && !it.refused } || scanning

    fun patch(k: String, f: (Up) -> Up) { val i = ups.indexOfFirst { it.key == k }; if (i >= 0) ups[i] = f(ups[i]) }

    /** The secret scan, hashes and text of every accepted file; a refused file is named and dropped, the rest go again. */
    suspend fun scan(keepForm: Boolean) {
        var ids = ups.filter { !it.refused && it.id != null }.mapNotNull { it.id }
        failure = null
        scanning = true
        try {
            while (ids.isNotEmpty()) {
                try {
                    val out = env.api.intake(ids)
                    got = out
                    if (!keepForm) {
                        val s = out.suggestion
                        val cls = s?.cls
                        val first = ups.firstOrNull { !it.refused && it.id != null }
                        form = RecordDraft(
                            cls, s?.titleFa ?: first?.let { stem(it.name) }.orEmpty(), s?.metadata.orEmpty(),
                            m.cls(cls)?.defaultLevel ?: m.levels.firstOrNull { it.key == "internal" }?.key ?: m.levels.firstOrNull()?.key,
                            scope?.let { m.defaultFolder(it, cls) },
                        )
                    }
                    return
                } catch (e: ApiException) {
                    if (e.code == "secret_in_document") {
                        // The refusal names the file (its key in `fields`), never what it held.
                        val names = e.fields.keys + e.fieldKeys
                        val hit = ups.firstOrNull { !it.refused && it.id in ids && it.name in names } ?: ups.firstOrNull { it.id == ids.first() }
                        if (hit == null) { failure = e; return }
                        patch(hit.key) { it.copy(refused = true) }
                        ids = ids - hit.id!!
                        if (ids.isEmpty()) got = null
                        continue
                    }
                    failure = e
                    return
                }
            }
        } finally {
            scanning = false
        }
    }

    fun add(uris: List<Uri>) {
        if (uris.isEmpty()) return
        scopeRunner.launch {
            val fresh = withContext(Dispatchers.IO) { uris.take(20).map { u -> ctx.contentResolver.describe(u).let { Up(UUID.randomUUID().toString(), u, it.name, it.mime, it.size) } } }
            ups.addAll(fresh)
            fresh.map { u ->
                async {
                    try {
                        val ref = withContext(Dispatchers.IO) {
                            env.api.upload(u.name, u.mime, u.size, { ctx.contentResolver.openInputStream(u.uri) ?: throw IOException("unreadable") }) { p ->
                                scopeRunner.launch { patch(u.key) { it.copy(pct = (p * 100).toInt()) } }
                            }
                        }
                        patch(u.key) { it.copy(id = ref.id, pct = 100) }
                    } catch (e: ApiException) {
                        patch(u.key) { it.copy(error = archiveError(e)) }
                    } catch (e: IOException) {
                        patch(u.key) { it.copy(error = "فایل خوانده نشد.") }
                    }
                }
            }.awaitAll()
            scan(touched)
        }
    }

    fun remove(k: String) {
        ups.removeAll { it.key == k }
        if (ups.any { !it.refused && it.id != null }) scopeRunner.launch { scan(touched) } else got = null
    }

    val pick = rememberLauncherForActivityResult(ActivityResultContracts.OpenMultipleDocuments()) { add(it) }
    LaunchedEffect(Unit) { if (picked0.isNotEmpty()) add(picked0) }

    val cls = m.cls(form.cls)
    val lacking = cls?.let { missingRequired(it.fields, form.metadata) }.orEmpty()
    val enough = cls != null && live.size >= cls.requiredFiles

    fun make(file: Boolean) {
        val sc = scope ?: return
        val k = form.cls ?: return
        errors = emptyMap(); failure = null
        action.run(onError = { e -> if (e.status != 0) key = UUID.randomUUID().toString(); errors = e.fields; failure = e }) {
            val r = env.api.createRecord(
                RecordIn(sc, k, form.titleFa.trim(), metaFor(m, form), form.level, form.folder, live.mapNotNull { it.id }, partiesFor(m, form, got?.suggestion?.parties.orEmpty()), file),
                "$key:${if (file) "file" else "draft"}",
            )
            env.cache.invalidate("archive", "decisions", "legal")
            toasts.ok(if (file) "سند ${r.ref} ثبت شد." else "پیش‌نویس ${r.ref} ساخته شد؛ هر وقت کامل شد ثبتش کن.")
            onClose()
            nav.go("archive/${r.ref}")
        }
    }

    fun importAll() {
        val sc = scope ?: return
        failure = null
        action.run(onError = { e -> failure = e }) {
            val out = env.api.importFiles(sc, live.mapNotNull { it.id })
            env.cache.invalidate("archive")
            toasts.ok("${out.size} پیش‌نویس ساخته شد؛ بایگان نوع و مشخصاتشان را پیشنهاد میدهد.")
            onClose()
        }
    }

    Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            FieldLabel("برای کجا")
            ScopeChips(scope, { s -> scope = s; if (s != null) form = form.copy(folder = m.defaultFolder(s, form.cls)) }, all = false)
        }
        Column(
            Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).border(1.5.dp, c.lineStrong, RoundedCornerShape(14.dp)).clickable(role = Role.Button, onClickLabel = "انتخاب فایل") { pick.launch(arrayOf("*/*")) }.padding(18.dp),
            horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            DIcon(DivanIcon.ATTACH, size = 26.dp, tint = c.goldInk)
            Text("فایل‌ها را از گوشی انتخاب کن", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
            Text("PDF، اسکن یا عکس؛ هر فایل یک بار، با hash خودش.", style = Divan.type.caption, color = c.textMuted, textAlign = TextAlign.Center)
            HqButton("انتخاب فایل", { pick.launch(arrayOf("*/*")) }, size = BtnSize.SM, icon = DivanIcon.ADD)
        }
        if (ups.isNotEmpty()) Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            for (u in ups) {
                val f = got?.files?.firstOrNull { it.fileId == u.id }
                Row(
                    Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(if (u.refused) c.softNegative else c.tile).padding(12.dp),
                    horizontalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    DIcon(if (u.refused) DivanIcon.LOCK else if (f != null) DivanIcon.SEAL else DivanIcon.ATTACH, Modifier.padding(top = 2.dp), size = 16.dp,
                        tint = if (u.refused) c.negative else if (f != null) c.positive else c.textMuted)
                    Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Fig(u.name, style = Divan.type.figureSmall, color = c.textPrimary)
                        when {
                            u.refused -> Text("رد شد: الگوی رمز، کلید خصوصی یا عبارت بازیابی در این فایل بود. ذخیره نشد و هیچ بخشی از آن جایی ثبت نشد. آن بخش را بردار و دوباره بفرست.", style = Divan.type.caption, color = c.negative)
                            u.error != null -> Text(u.error, style = Divan.type.caption, color = c.negative)
                            f != null -> FileFacts(f)
                            u.id != null -> Text("بررسی رمز، hash و متن…", style = Divan.type.caption, color = c.textMuted)
                            else -> Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                                Text("در حال بارگذاری", style = Divan.type.caption, color = c.textMuted)
                                Fig("${u.pct}%", style = Divan.type.figureSmall, color = c.textMuted)
                            }
                        }
                    }
                    DIcon(DivanIcon.CLOSE, Modifier.clickable(role = Role.Button, onClickLabel = "برداشتن ${u.name}") { remove(u.key) }, size = 16.dp, tint = c.textMuted)
                }
            }
        }
        if (busy && got == null) Skeleton(Modifier.fillMaxWidth().height(96.dp), radius = 12.dp)
        if (failure?.code != "validation_failed") ErrorLine(failure)
        if (live.size > 1) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            HqSwitch(split, { split = it }, "هر فایل یک پیش‌نویس جدا")
            Text("هر فایل یک پیش‌نویس جدا؛ بایگان نوع و مشخصات هر کدام را پیشنهاد میدهد.", Modifier.weight(1f), style = Divan.type.caption, color = c.textSecondary)
        }
        val g = got
        if (g != null && !split) Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            if (g.suggestion != null) Column(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.softLearning).padding(12.dp),
                verticalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                SuggestionLine(g.suggestion, m)
                g.suggestion.noteFa?.let { Text(com.coinepro.hq.ui.v16.prose(it), style = Divan.type.caption, color = c.textPrimary) }
            } else Text("قاعده‌ها نوع این سند را پیدا نکردند؛ خودت انتخاب کن.", Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp), style = Divan.type.caption, color = c.textSecondary)
            val sc = scope
            if (sc != null) RecordForm(sc, form, { touched = true; form = it }, errors, m) else Text("اول بگو برای کجاست.", style = Divan.type.caption, color = c.warning)
            if (failure?.code == "validation_failed") ErrorLine(failure)
            if (cls != null && (lacking.isNotEmpty() || !enough)) Text(
                "برای ثبت مستقیم کم است: " + (lacking.map { "«${it.titleFa}»" } + if (!enough) listOf("دست‌کم ${cls.requiredFiles} فایل") else emptyList()).joinToString("، ") +
                    ". پیش‌نویس بدون آن‌ها هم ساخته میشود.",
                style = Divan.type.caption, color = c.textMuted,
            )
        }
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            if (split && live.size > 1) {
                HqButton("${live.size} پیش‌نویس بساز", { importAll() }, variant = BtnVariant.PRIMARY, icon = DivanIcon.ADD, enabled = scope != null && ready, loading = action.busy)
            } else {
                HqButton("پیش‌نویس بساز", { make(false) }, variant = BtnVariant.PRIMARY, icon = DivanIcon.ADD, enabled = scope != null && ready && form.cls != null && form.titleFa.isNotBlank(), loading = action.busy)
                HqButton("همین حالا ثبت کن", { make(true) }, icon = DivanIcon.SEAL, enabled = scope != null && ready && form.titleFa.isNotBlank() && enough && lacking.isEmpty() && !action.busy)
            }
            HqButton("انصراف", onClose, variant = BtnVariant.GHOST)
        }
    }
}
