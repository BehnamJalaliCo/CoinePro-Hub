package com.coinepro.hq.ui.v30

import android.content.Context
import android.net.Uri
import android.provider.OpenableColumns
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.lazy.items
import com.coinepro.hq.designsystem.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import coil3.compose.AsyncImage
import com.coinepro.hq.core.data.LIBRARY_KINDS
import com.coinepro.hq.core.data.assetKindFa
import com.coinepro.hq.core.data.assetKindIcon
import com.coinepro.hq.core.data.settingText
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.Asset
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.TtsVoice
import com.coinepro.hq.core.net.gated
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.ScrollRow
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.itemMotion
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v29.IconTile
import com.coinepro.hq.ui.v29.Para
import com.coinepro.hq.ui.v29.plain
import com.coinepro.hq.ui.v29.served
import java.io.IOException
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

// Contract §30.5 ⟨1.12⟩: the library of the lines, per company and for the whole holding: cover folders (pick images and upload them),
// the speakers, prompts and patterns the lines use.

/** The library page. [company0] opens a company's own; otherwise the holding's (for every company). */
@Composable
fun LibraryScreen(company0: String? = null) {
    var scope by rememberSaveable { mutableStateOf(company0) }
    var kind by rememberSaveable { mutableStateOf(LIBRARY_KINDS.first()) }
    var editing by rememberSaveable { mutableStateOf<String?>(null) }
    var adding by rememberSaveable { mutableStateOf(false) }
    val companies = rememberCompanies().filter { it.kind != "holding" }
    val q = rememberQuery("library:${scope.orEmpty()}:$kind", "library", "lines", maxAgeMs = 30_000) { gated(HubFeature.LINES) { library(scope, kind) } }
    val voices = rememberQuery("tts-voices", "lines", maxAgeMs = 3_600_000) { gated(HubFeature.LINES) { ttsVoices() } }
    val r = refresher(q)
    val has = served(HubFeature.LINES)
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item { PageHeader("کتابخانه‌ی تولید", eyebrow = "پوشه‌های کاور، صدا، پرامپت و الگو") }
        item(key = "scope") {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                ScrollRow {
                    FilterChip("همه‌ی هلدینگ", scope == null, { scope = null })
                    for (co in companies) FilterChip(co.nameFa ?: co.code, scope == co.code, { scope = co.code })
                }
                ScrollRow { for (k in LIBRARY_KINDS) FilterChip(assetKindFa(k), kind == k, { kind = k }) }
                if (has) HqButton(
                    when (kind) { "cover_folder" -> "پوشه‌ی کاور تازه"; "voice" -> "صدای تازه"; "prompt" -> "پرامپت تازه"; else -> "الگوی تازه" },
                    { adding = true }, variant = BtnVariant.PRIMARY, size = BtnSize.SM, icon = DivanIcon.ADD,
                )
            }
        }
        // Without a company the page shows the holding's own (the hub's list may hold every company's).
        val list = q.data?.filter { scope != null || it.company == null }
        when {
            !has -> item { Empty("کتابخانه با به‌روزرسانی بعدی هاب میاید", icon = DivanIcon.IMAGE) }
            list == null && q.error != null -> item { ErrorBlock(q.error, { q.refresh() }) }
            list == null -> item { Skeleton(Modifier.fillMaxWidth().height(140.dp), radius = 16.dp) }
            list.isEmpty() -> item { Empty("اینجا هنوز چیزی نیست", icon = assetKindIcon(kind), body = if (scope == null) "چیزی که اینجا بگذاری برای همه‌ی شرکت‌ها در دسترس است." else "فقط خط‌های همین شرکت از این‌ها استفاده میکنند.") }
            else -> items(list, key = { it.id }) { a -> Box(itemMotion()) { AssetCard(a) { editing = a.id } } }
        }
    }
    if (adding) com.coinepro.hq.ui.v14.HqSheet({ adding = false }, "افزودن " + assetKindFa(kind), sub = if (scope == null) "برای همه‌ی شرکت‌ها" else null) {
        AssetForm(null, kind, scope, voices.data.orEmpty()) { adding = false }
    }
    editing?.let { id ->
        q.data?.firstOrNull { it.id == id }?.let { a ->
            com.coinepro.hq.ui.v14.HqSheet({ editing = null }, a.titleFa.ifBlank { assetKindFa(a.kind) }, sub = assetKindFa(a.kind)) {
                AssetForm(a, a.kind, a.company, voices.data.orEmpty()) { editing = null }
            }
        }
    }
}

/** One entry: its title, what it holds, and a look at it (pictures, a sample of the voice, the first lines of a prompt). */
@Composable
fun AssetCard(a: Asset, onClick: () -> Unit) {
    val c = Divan.colors
    val media = LocalEnv.current.media
    HqCard(Modifier.fillMaxWidth(), onClick = onClick) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            IconTile(assetKindIcon(a.kind), c.goldInk, c.softGold)
            Column(Modifier.weight(1f)) {
                Text(plain(a.titleFa.ifBlank { assetKindFa(a.kind) }), style = Divan.type.bodyStrong, maxLines = 2)
                Text(plain(summaryOf(a)), style = Divan.type.caption, color = c.textMuted, maxLines = 1)
            }
            if (a.company == null) Text("همه‌ی شرکت‌ها", style = Divan.type.micro, color = c.textMuted)
        }
        when (a.kind) {
            "cover_folder", "pattern" -> if (a.files.isNotEmpty()) FlowRow(Modifier.padding(top = 10.dp), horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                for (id in a.files.take(6)) AsyncImage(media.imageModel(id), null, media.images, Modifier.size(56.dp).clip(RoundedCornerShape(8.dp)).background(c.tile), contentScale = ContentScale.Crop)
            }
            "voice" -> a.files.firstOrNull()?.let { Box(Modifier.padding(top = 10.dp)) { com.coinepro.hq.ui.v18.AudioPlayer(it, "نمونه‌ی " + a.titleFa, compact = true) } }
            "prompt" -> settingText(a.config["text"]).takeIf { it.isNotBlank() }?.let { Para(it, Modifier.padding(top = 8.dp), style = Divan.type.caption, maxLines = 3) }
        }
    }
}

private fun summaryOf(a: Asset): String = when (a.kind) {
    "cover_folder" -> "${a.files.size} تصویر"
    "voice" -> listOf(settingText(a.config["voice"]), settingText(a.config["style"])).filter { it.isNotBlank() }.joinToString("، ").ifBlank { assetKindFa(a.kind) }
    "pattern" -> settingText(a.config["query"]).ifBlank { "${a.files.size} نمونه" }
    "prompt" -> "متن آماده برای مرحله‌ها"
    else -> assetKindFa(a.kind)
}

/** The content URI as an upload: name, type and size from the provider; the bytes stream when the upload runs. */
private fun uploadOf(ctx: Context, uri: Uri): Api.LibraryUpload {
    var name = "image.jpg"
    var size = -1L
    ctx.contentResolver.query(uri, null, null, null, null)?.use { cur ->
        val ni = cur.getColumnIndex(OpenableColumns.DISPLAY_NAME)
        val si = cur.getColumnIndex(OpenableColumns.SIZE)
        if (cur.moveToFirst()) {
            if (ni >= 0) name = cur.getString(ni) ?: name
            if (si >= 0 && !cur.isNull(si)) size = cur.getLong(si)
        }
    }
    val mime = ctx.contentResolver.getType(uri) ?: "image/jpeg"
    return Api.LibraryUpload(name, mime, size) { ctx.contentResolver.openInputStream(uri) ?: throw IOException("unreadable") }
}

/**
 * Making an entry ([a] null) or changing one. A cover folder (or a pattern) takes pictures from the gallery, uploaded in one go; a voice
 * takes a speaker and a style; a prompt its text; a pattern its search words. Deleting asks once.
 */
@Composable
fun AssetForm(a: Asset?, kind: String, company: String?, voices: List<TtsVoice>, onDone: () -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val ctx = LocalContext.current
    val c = Divan.colors
    val save = rememberAction()
    val del = rememberAction()
    var title by rememberSaveable(a?.id) { mutableStateOf(a?.titleFa.orEmpty()) }
    var speaker by rememberSaveable(a?.id) { mutableStateOf(settingText(a?.config?.get("voice"))) }
    var style by rememberSaveable(a?.id) { mutableStateOf(settingText(a?.config?.get("style"))) }
    var text by rememberSaveable(a?.id) { mutableStateOf(settingText(a?.config?.get("text"))) }
    var query by rememberSaveable(a?.id) { mutableStateOf(settingText(a?.config?.get("query"))) }
    var picked by remember { mutableStateOf<List<Uri>>(emptyList()) }
    var confirm by rememberSaveable { mutableStateOf(false) }
    val pick = rememberLauncherForActivityResult(ActivityResultContracts.PickMultipleVisualMedia(30)) { picked = it }
    val withImages = kind == "cover_folder" || kind == "pattern"
    val config: JsonObject = buildJsonObject {
        when (kind) {
            "voice" -> { put("voice", speaker.trim()); if (style.isNotBlank()) put("style", style.trim()) }
            "prompt" -> put("text", text.trim())
            "pattern" -> put("query", query.trim())
            else -> Unit
        }
    }
    val ready = title.trim().length >= 2 && when (kind) {
        "voice" -> speaker.isNotBlank()
        "prompt" -> text.trim().length >= 3
        "pattern" -> query.isNotBlank() || picked.isNotEmpty() || a != null
        else -> a != null || picked.isNotEmpty()
    }
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("نام", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
        HqTextField(title, { title = it }, "مثلاً کاورهای طلای تریدیار", Modifier.fillMaxWidth(), maxLength = 120)
        when (kind) {
            "voice" -> {
                Text("گوینده", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
                if (voices.isEmpty()) HqTextField(speaker, { speaker = it }, "نام گوینده", Modifier.fillMaxWidth(), maxLength = 80)
                else FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    for (v in voices) FilterChip(v.titleFa.ifBlank { v.name }, v.name == speaker, { speaker = v.name })
                }
                voices.firstOrNull { it.name == speaker }?.sampleFile?.let { com.coinepro.hq.ui.v18.AudioPlayer(it, "نمونه‌ی صدا", compact = true) }
                Text("سبک خواندن", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
                HqTextField(style, { style = it }, "مثلاً آرام و مطمئن، مثل گوینده‌ی خبر", Modifier.fillMaxWidth(), singleLine = false, minLines = 2, maxLength = 300)
            }
            "prompt" -> {
                Text("متن", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
                HqTextField(text, { text = it }, "متن پرامپت", Modifier.fillMaxWidth(), singleLine = false, minLines = 6, maxLength = 8000)
            }
            "pattern" -> {
                Text("عبارت جست‌وجو", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
                HqTextField(query, { query = it }, "مثلاً طراحی ریلز آموزشی", Modifier.fillMaxWidth(), maxLength = 200)
            }
        }
        if (withImages && a == null) {
            Text("تصویرها", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
            HqButton(if (picked.isEmpty()) "انتخاب از گالری" else "${picked.size} تصویر انتخاب شد؛ عوض کن", {
                pick.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly))
            }, Modifier.fillMaxWidth(), variant = BtnVariant.SILVER, icon = DivanIcon.IMAGE)
        }
        if (a != null && a.files.isNotEmpty()) Text(plain("${a.files.size} فایل در این مورد است."), style = Divan.type.caption, color = c.textMuted)
        HqButton(if (a == null) "بساز" else "ذخیره", {
            save.run {
                if (a == null) {
                    env.api.addAsset(company, kind, title.trim(), config, picked.map { uploadOf(ctx, it) })
                    toasts.ok(if (picked.isEmpty()) "به کتابخانه افزوده شد." else "به کتابخانه افزوده شد؛ تصویرها بارگذاری شدند.")
                } else {
                    env.api.putAsset(a.id, buildJsonObject { put("title_fa", title.trim()); put("config", config) })
                    toasts.ok("ذخیره شد.")
                }
                env.cache.invalidate("library")
                onDone()
            }
        }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, icon = DivanIcon.SEAL, enabled = ready, loading = save.busy)
        if (a != null) {
            if (!confirm) HqButton("حذف", { confirm = true }, Modifier.fillMaxWidth(), variant = BtnVariant.DANGER, size = BtnSize.SM, icon = DivanIcon.DISMISS)
            else {
                Text("اگر خطی از این استفاده میکند، دیگر پیدایش نمیکند. مطمئنی؟", style = Divan.type.caption, color = c.negative)
                HqButton("بله، حذف کن", {
                    del.run { env.api.deleteAsset(a.id); env.cache.invalidate("library"); toasts.ok("حذف شد."); onDone() }
                }, Modifier.fillMaxWidth(), variant = BtnVariant.DANGER, size = BtnSize.SM, icon = DivanIcon.DISMISS, loading = del.busy)
            }
        }
    }
}
