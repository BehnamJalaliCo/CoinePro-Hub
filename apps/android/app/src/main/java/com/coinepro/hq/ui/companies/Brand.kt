package com.coinepro.hq.ui.companies

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.CircularProgressIndicator
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
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import coil3.compose.AsyncImage
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.jDate
import com.coinepro.hq.core.net.ActiveBrand
import com.coinepro.hq.core.net.BrandOptions
import com.coinepro.hq.core.net.CompanyBrand
import com.coinepro.hq.designsystem.BrandMarkImage
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.DivanTheme
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.LiveBrand
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.Seal
import com.coinepro.hq.designsystem.SealState
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.SegOption
import com.coinepro.hq.designsystem.Segmented
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.argbOf
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.designsystem.generated.MarkLayer
import com.coinepro.hq.designsystem.generated.MarkRole
import com.coinepro.hq.designsystem.viewBoxOf
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.activity
import com.coinepro.hq.ui.media.rememberAttachments
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery
import java.util.Locale
import kotlinx.coroutines.delay
import com.coinepro.hq.core.net.BrandMark as WireMark
import com.coinepro.hq.designsystem.generated.BrandMark as DrawnMark

// Contract §18.14 (mirrors apps/web/src/components/brand/brand-block.tsx): the owner gives the company's PNG logo, the hub
// traces it into a two-layer mark (code, no model), the owner looks at it beside the original, in every size and both themes,
// in the seal ready and sealed, and seals it.

private val REASON_FA = mapOf(
    "no_background" to "لوگو را با زمینه‌ی شفاف یا یکدست بدهید",
    "too_complex" to "لوگو برای نشان خیلی پیچیده است؛ جزئیات را کم کن",
)
private val LOGO_TYPES = setOf("image/png", "image/webp", "image/jpeg")
private val SIZES = listOf(48, 24, 16)

// ------------------------------------------------------------- the data --
fun WireMark.drawn(): DrawnMark = DrawnMark(viewBoxOf(vb), layers.map { MarkLayer(if (it.role == "accent") MarkRole.ACCENT else MarkRole.INK, argbOf(it.color), it.d) })

fun ActiveBrand.live() = LiveBrand(mark.drawn(), wordmark?.drawn(), accent?.let(::argbOf), accentNight?.let(::argbOf), accentDay?.let(::argbOf))

fun CompanyBrand.live(): LiveBrand? = mark?.let { LiveBrand(it.drawn(), wordmark?.drawn(), accent?.let(::argbOf), accentNight?.let(::argbOf), accentDay?.let(::argbOf)) }

/** Every company's active brand for [com.coinepro.hq.designsystem.LocalBrands]: fetched once a session, kept in the query cache;
 *  it changes only when the owner seals a brand, and `brand.updated` on the stream refreshes it. */
@Composable
fun rememberBrands(): Map<String, LiveBrand> {
    val q = rememberQuery("brands", "brands", maxAgeMs = 3_600_000) { brands() }
    return remember(q.data) { q.data?.companies?.mapValues { it.value.live() }.orEmpty() }
}

// ------------------------------------------------------------ previews --
/** One theme: the mark at 160, 48, 24 and 16 dp (24 and below in one ink, as lists draw it), the wordmark, and the seal ready
 *  and sealed. The pane brings its own theme, so night and day show side by side whatever the app's theme is. */
@Composable
private fun Pane(b: LiveBrand, code: String, nameFa: String, nameEn: String, night: Boolean, modifier: Modifier = Modifier) {
    DivanTheme(night) {
        val c = Divan.colors
        Column(
            modifier.clip(RoundedCornerShape(14.dp)).background(c.page).border(1.dp, c.lineTahrir, RoundedCornerShape(14.dp)).padding(14.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            Text(if (night) "شب" else "روز", style = Divan.type.micro, color = c.textMuted, modifier = Modifier.align(Alignment.Start))
            Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(6.dp)) {
                BrandMarkImage(b.mark, 160.dp, ink = c.textPrimary, brand = b)
                Fig("160dp", style = Divan.type.figureSmall, color = c.textMuted)
            }
            b.wordmark?.let { BrandMarkImage(it, 26.dp, ink = c.textPrimary, brand = b) }
            Row(verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(20.dp)) {
                for (h in SIZES) Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    BrandMarkImage(b.mark, h.dp, mono = h <= 24, ink = c.textPrimary, brand = b)
                    Fig("${h}dp", style = Divan.type.figureSmall, color = c.textMuted)
                }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                Seal(code, nameFa, nameEn, size = 96.dp, mark = b.mark)
                Seal(code, nameFa, nameEn, size = 96.dp, mark = b.mark, state = SealState.SEALED)
            }
        }
    }
}

@Composable
private fun Previews(b: LiveBrand, code: String, nameFa: String, nameEn: String) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Pane(b, code, nameFa, nameEn, night = true, modifier = Modifier.fillMaxWidth())
        Pane(b, code, nameFa, nameEn, night = false, modifier = Modifier.fillMaxWidth())
    }
}

/** A checkerboard behind the logo, so transparency shows. */
private fun Modifier.checker(a: Color, b: Color) = drawBehind {
    val s = 8.dp.toPx()
    drawRect(a)
    var y = 0f
    var row = 0
    while (y < size.height) {
        var x = if (row % 2 == 0) 0f else s
        while (x < size.width) { drawRect(b, Offset(x, y), Size(s, s)); x += 2 * s }
        y += s
        row++
    }
}

/** What the owner gave, beside the facts the trace started from. */
@Composable
private fun Original(v: CompanyBrand) {
    val media = LocalEnv.current.media
    val c = Divan.colors
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        Box(Modifier.size(112.dp).clip(RoundedCornerShape(12.dp)).checker(c.tile, c.card).padding(8.dp), contentAlignment = Alignment.Center) {
            val id = v.source.fileId
            if (id != null) AsyncImage(media.imageModel(id), "لوگوی اصلی", media.images, Modifier.fillMaxSize(), contentScale = ContentScale.Fit)
            else DIcon(DivanIcon.IMAGE, size = 26.dp, tint = c.textMuted)
        }
        Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text("اصل", style = Divan.type.caption, color = c.textSecondary)
            Fig("${v.source.width}×${v.source.height}", style = Divan.type.figureSmall, color = c.textMuted)
            Text(if (v.source.hasAlpha) "شفاف" else "بدون شفافیت", style = Divan.type.micro, color = c.textMuted)
        }
    }
}

@Composable
private fun Checks(v: CompanyBrand) {
    val k = v.checks ?: return
    val c = Divan.colors
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        if (k.warnings.isEmpty()) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            DIcon(DivanIcon.SEAL, size = 14.dp, tint = c.positive, active = true)
            Text("همه‌ی سنجش‌ها پذیرفته شد", style = Divan.type.small, color = c.positive)
        }
        for (w in k.warnings) Row(
            Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(c.softWarning).padding(horizontal = 12.dp, vertical = 8.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            DIcon(DivanIcon.INFO, size = 16.dp, tint = c.warning, modifier = Modifier.padding(top = 2.dp))
            Text(w, style = Divan.type.small, color = c.textPrimary)
        }
        FlowRow(horizontalArrangement = Arrangement.spacedBy(14.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Figure("وفاداری", "IoU " + String.format(Locale.US, "%.2f", k.iou))
            Figure("نازک‌ترین جزء در ۱۶ پیکسل", String.format(Locale.US, "%.1fpx", k.minFeaturePx16))
            k.contrastNight?.let { Figure("کنتراست شب", String.format(Locale.US, "%.1f:1", it)) }
            k.contrastDay?.let { Figure("کنتراست روز", String.format(Locale.US, "%.1f:1", it)) }
        }
        if (v.palette.isNotEmpty()) FlowRow(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            for (p in v.palette) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(5.dp)) {
                Box(Modifier.size(14.dp).clip(CircleShape).background(Color(argbOf(p.hex))).border(1.dp, c.lineStrong, CircleShape))
                Fig("${p.hex} · ${(p.share * 100).toInt()}%", style = Divan.type.figureSmall, color = c.textMuted)
            }
        }
    }
}

@Composable
private fun Figure(label: String, value: String) {
    val c = Divan.colors
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(label, style = Divan.type.micro, color = c.textMuted)
        Fig(value, style = Divan.type.figureSmall, color = c.textSecondary)
    }
}

@Composable
private fun Labelled(label: String, content: @Composable () -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(label, style = Divan.type.caption, color = Divan.colors.textSecondary)
        content()
    }
}

// --------------------------------------------------------------- block --
/** «نشان و مُهر»: the active brand, a new logo traced into a mark, the proposal with its checks, retrace and seal. Shared by the
 *  company screen and the founding's step «مُهر شرکت» (which names itself and shows the founding's own brand state in [badge]). */
@Composable
fun BrandBlock(code: String, nameFa: String, nameEn: String, title: String = "نشان و مُهر", badge: (@Composable RowScope.() -> Unit)? = null) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val act = activity()
    val ctx = LocalContext.current
    val c = Divan.colors
    val q = rememberQuery("brand:$code", "brand", "companies") { companyBrand(code) }
    val action = rememberAction()
    val files = rememberAttachments(1)
    var part by rememberSaveable { mutableStateOf("mark") }
    var colors by rememberSaveable { mutableStateOf("auto") }
    var detail by rememberSaveable { mutableStateOf("3") }
    // The version this screen started (an upload or a retrace), followed until it is traced.
    var work by remember(code) { mutableStateOf<CompanyBrand?>(null) }
    val pick = rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri ->
        if (uri == null) return@rememberLauncherForActivityResult
        if (ctx.contentResolver.getType(uri) !in LOGO_TYPES) toasts.error("لوگو باید PNG (بهتر با زمینه‌ی شفاف)، WebP یا JPEG باشد.")
        else files.add(listOf(uri))
    }
    LaunchedEffect(work?.version, work?.state) {
        val w = work?.takeIf { it.state == "processing" } ?: return@LaunchedEffect
        while (true) {
            delay(1_500)
            val next = runCatching { env.api.brandVersions(code).firstOrNull { it.version == w.version } }.getOrNull() ?: continue
            if (next.state != "processing") {
                work = next
                env.cache.invalidate("brand")
                break
            }
        }
    }
    val view = q.data
    val active = view?.active
    // An older proposal than the active version is history, not something to seal.
    val proposed = view?.proposed?.takeIf { p -> active == null || p.version > active.version }
    val shown = work?.takeIf { it.state != "active" && it.state != "retired" } ?: proposed
    val options = BrandOptions(colors.toIntOrNull(), detail.toInt())
    val logo = files.items.firstOrNull()
    val activeLive = remember(active) { active?.live() }
    val shownLive = remember(shown) { shown?.live() }

    Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
        SectionTitle(
            title,
            note = active?.let { "نسخه‌ی ${it.version}، مُهرشده ${jDate(it.activatedAt, withYear = true)}" + if (it.source.kind == "seed") "، از فایل‌های طراحی" else "" }
                ?: "هنوز نشانی مُهر نشده؛ تا آن موقع شرکت با کدش دیده میشود.",
            action = badge ?: { if (active != null) Pill("فعال", Tone.POS, icon = DivanIcon.SEAL) else Pill("بدون نشان", Tone.WARN, dot = true) },
        )
        when {
            view == null && q.error != null -> ErrorBlock(q.error, { q.refresh() })
            view == null -> Skeleton(Modifier.fillMaxWidth().height(240.dp), radius = 14.dp)
        }
        activeLive?.let { Previews(it, code, nameFa, nameEn) }

        shown?.let { v ->
            HorizontalDivider(color = c.lineDivider)
            SectionTitle(
                if (v.state == "failed") "ساخت نشان انجام نشد" else "نشان تازه",
                note = "نسخه‌ی ${v.version}، رنگ‌ها ${v.options.colors ?: "خودکار"}، جزئیات ${v.options.detail}",
                action = {
                    when (v.state) {
                        "processing" -> Pill("در حال ساخت", Tone.LAPIS, live = true)
                        "failed" -> Pill("ناموفق", Tone.NEG, dot = true)
                        else -> Pill("منتظر مُهر تو", Tone.GOLD, dot = true)
                    }
                },
            )
            when (v.state) {
                "processing" -> Row(
                    Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(14.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    CircularProgressIndicator(Modifier.size(16.dp), color = c.goldInk, strokeWidth = 2.dp)
                    Text("زمینه جدا میشود، رنگ‌ها شمرده میشوند و هر لایه به مسیر برداری تبدیل میشود…", style = Divan.type.small, color = c.textSecondary)
                }
                "failed" -> Row(
                    Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.softNegative).padding(14.dp),
                    horizontalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    DIcon(DivanIcon.URGENT, size = 18.dp, tint = c.negative)
                    Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Text(REASON_FA[v.statusReason] ?: "نشان از این لوگو ساخته نشد.", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                        Text("گزینه‌ها را عوض کن و دوباره بساز، یا لوگوی دیگری بده.", style = Divan.type.caption, color = c.textSecondary)
                    }
                }
                else -> {
                    Original(v)
                    shownLive?.let { Previews(it, code, nameFa, nameEn) }
                    Checks(v)
                }
            }
            if (v.state != "processing") FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                if (v.state == "proposed") HqButton("مُهر کن", {
                    action.run {
                        env.api.activateBrand(v) { a, t -> env.auth.stepUp(act, a, t) }
                        work = null
                        env.cache.invalidate("brand", "brands", "companies", "founding")
                        toasts.ok("مُهر شد؛ نشان تازه‌ی $nameFa همه‌جا دیده میشود.")
                    }
                }, variant = BtnVariant.PRIMARY, icon = DivanIcon.SEAL, loading = action.busy)
                HqButton("دوباره بساز", {
                    action.run { work = env.api.retraceBrand(code, v.version, options) }
                }, icon = DivanIcon.REFRESH, enabled = !action.busy)
            }
        }

        HorizontalDivider(color = c.lineDivider)
        SectionTitle("لوگوی تازه", note = "PNG با زمینه‌ی شفاف بهترین است؛ WebP و JPEG هم پذیرفته میشوند. حداکثر ۴۰۹۶ پیکسل.")
        Labelled("بخش") { Segmented(listOf(SegOption("mark", "نشان"), SegOption("wordmark", "لوگوتایپ")), part, { part = it }, Modifier.fillMaxWidth()) }
        Labelled("رنگ‌ها") { Segmented(listOf("auto", "1", "2", "3", "4").map { SegOption(it, if (it == "auto") "خودکار" else it) }, colors, { colors = it }, Modifier.fillMaxWidth()) }
        Labelled("جزئیات") { Segmented(listOf("1", "2", "3", "4", "5").map { SegOption(it, it) }, detail, { detail = it }, Modifier.fillMaxWidth()) }
        if (logo == null) {
            HqButton("لوگوی تازه (PNG)", { pick.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly)) }, Modifier.fillMaxWidth(), icon = DivanIcon.IMAGE)
        } else {
            Row(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(8.dp),
                verticalAlignment = Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                Box(Modifier.size(48.dp).clip(RoundedCornerShape(8.dp)).checker(c.card, c.tile), contentAlignment = Alignment.Center) {
                    AsyncImage(logo.file.uri, null, env.media.images, Modifier.fillMaxSize(), contentScale = ContentScale.Fit)
                }
                Column(Modifier.weight(1f)) {
                    Text(logo.file.name, style = Divan.type.small, color = c.textPrimary, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    when (logo.state) {
                        "uploading" -> Fig("${(logo.progress * 100).toInt()}%", style = Divan.type.figureSmall, color = c.textMuted)
                        "failed" -> Text(logo.error ?: "بارگذاری نشد.", style = Divan.type.micro, color = c.negative)
                        else -> Text("بارگذاری شد", style = Divan.type.micro, color = c.textMuted)
                    }
                }
                if (logo.state == "failed") HqButton("دوباره", { files.retry(logo) }, variant = BtnVariant.GHOST, size = BtnSize.SM, icon = DivanIcon.REFRESH)
                Box(
                    Modifier.size(32.dp).clip(CircleShape).clickable(role = Role.Button, onClickLabel = "برداشتن لوگو") { files.remove(logo) },
                    contentAlignment = Alignment.Center,
                ) { DIcon(DivanIcon.CLOSE, size = 16.dp, tint = c.textSecondary) }
            }
            HqButton("نشان را بساز", {
                val id = logo.ref?.id ?: return@HqButton
                action.run {
                    work = env.api.uploadBrand(code, id, part, options)
                    files.clear()
                }
            }, Modifier.fillMaxWidth(), icon = DivanIcon.EDIT, enabled = logo.state == "ready" && shown?.state != "processing", loading = action.busy)
        }
    }
}
