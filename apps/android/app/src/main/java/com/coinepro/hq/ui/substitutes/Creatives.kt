package com.coinepro.hq.ui.substitutes

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import coil3.compose.AsyncImage
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.actorFa
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.net.Creative
import com.coinepro.hq.core.net.Overlay
import com.coinepro.hq.core.net.PLACEMENT_ASPECT
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.HqSwitch
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.Md
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.SegOption
import com.coinepro.hq.designsystem.Segmented
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v14.HqSheet
import com.coinepro.hq.ui.v14.LabelPill
import com.coinepro.hq.ui.v16.Chip
import com.coinepro.hq.ui.v16.ChipRow
import com.coinepro.hq.ui.v17.ActorAvatar
import com.coinepro.hq.ui.v17.CoMark
import com.coinepro.hq.ui.v17.RefChip
import com.coinepro.hq.ui.v17.ScopeChips
import com.coinepro.hq.ui.v18.CREATIVE
import com.coinepro.hq.ui.v18.PLACEMENT
import com.coinepro.hq.ui.v18.PlayerName
import com.coinepro.hq.ui.v18.mgmt
import java.util.UUID
import kotlinx.coroutines.delay

// The companies' ad creatives (contract §21.13), mirroring apps/web/src/components/v18/creatives.tsx: asked by an agent or the owner,
// rendered by a substitute on the owner's plan through the hub's signed-in browser, composed (the Persian text is the hub's, never the
// model's) and reviewed on the hub. Every one is AI-generated; publishing one anywhere is a decision card, always.

private fun ratioOf(aspect: String): Float = aspect.split(':').mapNotNull { it.toFloatOrNull() }.takeIf { it.size == 2 && it[1] > 0 }?.let { it[0] / it[1] } ?: 1f
private val STATES = listOf<String?>(null, "review", "generating", "accepted", "rejected", "failed")

/** The creative's picture: the composed file (or the raw one) in its aspect, else what is happening; the aspect in a corner.
 *  ⟨1.9⟩ also a media council's gallery (§27.2). */
@Composable
internal fun Thumb(c: Creative, modifier: Modifier = Modifier, raw: Boolean = false) {
    val media = LocalEnv.current.media
    val col = Divan.colors
    val file = if (raw) c.files.firstOrNull() else c.composed ?: c.files.firstOrNull()
    Box(modifier.aspectRatio(ratioOf(c.aspect)).clip(RoundedCornerShape(12.dp)).background(col.page), contentAlignment = Alignment.Center) {
        if (file != null && c.kind == "image") AsyncImage(media.imageModel(file.id), c.overlay?.titleFa ?: c.briefMd, media.images, Modifier.fillMaxSize(), contentScale = ContentScale.Crop)
        else Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(6.dp)) {
            DIcon(if (c.kind == "video") DivanIcon.VIDEO else DivanIcon.IMAGE, size = 26.dp, tint = col.textMuted)
            Text(CREATIVE[c.state]?.fa.orEmpty(), style = Divan.type.micro, color = col.textMuted)
        }
        Fig(c.aspect, Modifier.align(Alignment.TopEnd).padding(6.dp).clip(CircleShape).background(Color(0xB80B0D14)).padding(horizontal = 6.dp, vertical = 1.dp), style = Divan.type.figureSmall, color = Color(0xFFF2EEE4))
    }
}

/** The list: by company and state, newest first, each in its own aspect; one opens in a sheet, a new one is asked for here. */
@Composable
fun CreativesCard(open0: String? = null) {
    val c = Divan.colors
    var company by rememberSaveable { mutableStateOf<String?>(null) }
    var state by rememberSaveable { mutableStateOf<String?>(null) }
    var open by rememberSaveable { mutableStateOf(open0) }
    var making by remember { mutableStateOf(false) }
    val q = rememberQuery("creatives:list:${company ?: ""}:${state ?: ""}", "creatives") { creatives(company, state).items }
    val list = q.data
    val live = list?.any { it.live } == true
    LaunchedEffect(live) { while (live) { delay(3_000); q.refresh() } }
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("عکس و ویدیوی تبلیغ", note = "هر کدام ساخته‌ی هوش مصنوعی است؛ انتشارش همیشه کارت تصمیم میخواهد") {
            HqButton("درخواست تازه", { making = true }, size = BtnSize.SM, variant = BtnVariant.PRIMARY, icon = DivanIcon.ADD)
        }
        Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            ScopeChips(company, { company = it }, holding = false, allLabel = "همه‌ی شرکت‌ها")
            ChipRow { for (s in STATES) FilterChip(s?.let { CREATIVE[it]?.fa } ?: "همه", state == s, { state = s }) }
            when {
                list == null -> Skeleton(Modifier.fillMaxWidth().height(240.dp), radius = 12.dp)
                list.isEmpty() -> Empty("درخواستی نیست", icon = DivanIcon.IMAGE)
                else -> for (row in list.chunked(2)) Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    for (x in row) CreativeTile(x, Modifier.weight(1f)) { open = x.ref }
                    if (row.size == 1) Box(Modifier.weight(1f))
                }
            }
        }
    }
    open?.let { ref -> HqSheet({ open = null }, "درخواست تبلیغ", sub = "متن فارسی هرگز ساخته‌ی مدل نیست: هاب آن را با IRANYekanX و پالت برند، در حاشیه‌ی امن جای انتشار، روی نتیجه میچیند.", ref = ref) { CreativeView(ref) { open = null } } }
    if (making) HqSheet({ making = false }, "عکس یا ویدیوی تبلیغ", sub = "ایجنت Claude مسئول همان شرکت prompt را از روی brief، جای انتشار و برند مینویسد و «بی‌متن» میخواهد؛ بازیکن ذخیره فقط میسازد.") {
        NewCreative { ref -> making = false; open = ref }
    }
}

@Composable
private fun CreativeTile(x: Creative, modifier: Modifier, onClick: () -> Unit) {
    val c = Divan.colors
    Column(
        modifier.clip(RoundedCornerShape(14.dp)).background(if (x.state == "review") c.softGold else c.tile).clickable(role = Role.Button, onClick = onClick).padding(8.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Thumb(x, Modifier.fillMaxWidth())
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            CoMark(x.company, height = 11.dp)
            Text(x.overlay?.titleFa ?: x.briefMd, Modifier.weight(1f), style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
        LabelPill(CREATIVE[x.state], x.state)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(2.dp), itemVerticalAlignment = Alignment.CenterVertically) {
            Text(PLACEMENT[x.placement] ?: x.placement, style = Divan.type.micro, color = c.textMuted)
            PlayerName(x.player, size = 11.dp, color = c.textMuted)
        }
    }
}

/** One creative whole: the composed result beside the raw one, the brief, the hub's text, the agent's prompt and review; accept or
 *  reject while it waits for the owner. */
@Composable
fun CreativeView(ref: String, onDone: () -> Unit = {}) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val action = rememberAction()
    val q = rememberQuery("creatives:$ref", "creatives") { creative(ref) }
    val x = q.data
    val live = x?.live == true
    LaunchedEffect(live) { while (live) { delay(2_500); q.refresh() } }
    var note by remember { mutableStateOf("") }
    if (x == null) return Skeleton(Modifier.fillMaxWidth().height(320.dp), radius = 12.dp)
    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(6.dp), itemVerticalAlignment = Alignment.CenterVertically) {
            Text(PLACEMENT[x.placement] ?: x.placement, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
            LabelPill(CREATIVE[x.state], x.state)
            CoMark(x.company, height = 12.dp)
            PlayerName(x.player, x.model, size = 13.dp)
            Fig(x.path, style = Divan.type.figureSmall, color = c.textMuted)
            x.durationS?.let { Text("$it ثانیه", style = Divan.type.caption, color = c.textSecondary) }
            Pill("ساخته‌ی هوش مصنوعی", Tone.NEUTRAL, icon = DivanIcon.INFO)
        }
        val portrait = x.aspect == "9:16" || x.aspect == "4:5"
        val both = x.files.isNotEmpty() && x.composed != null
        @Composable fun Shown(label: String, raw: Boolean, m: Modifier) = Column(m, verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(label, style = Divan.type.micro, color = c.textMuted)
            Thumb(x, Modifier.fillMaxWidth(), raw = raw)
        }
        if (both && portrait) Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Shown("نسخه‌ی نهایی با متن هاب", false, Modifier.weight(1f))
            Shown("خروجی خام بازیکن (بی‌متن)", true, Modifier.weight(1f))
        } else {
            Shown("نسخه‌ی نهایی با متن هاب", false, if (portrait) Modifier.width(220.dp) else Modifier.fillMaxWidth())
            if (both) Shown("خروجی خام بازیکن (بی‌متن)", true, Modifier.fillMaxWidth())
        }
        Block("brief") { Text(x.briefMd, style = Divan.type.body, color = c.textPrimary) }
        x.overlay?.let { o ->
            Block("متن روی تصویر") {
                for ((k, v) in listOfNotNull("عنوان" to o.titleFa, o.bodyFa?.let { "متن" to it }, o.ctaFa?.let { "دعوت" to it }, "نشان" to if (o.mark) "با نشان شرکت" else "بی‌نشان")) {
                    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        Text(k, Modifier.width(48.dp), style = Divan.type.small, color = c.textMuted)
                        Text(v, Modifier.weight(1f), style = Divan.type.small, color = c.textPrimary)
                    }
                }
            }
        }
        Block("prompt (نوشته‌ی ایجنت Claude مسئول)") {
            Fig(x.promptMd, Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(c.tile).padding(12.dp), style = Divan.type.figureSmall, color = c.textSecondary, maxLines = 20)
        }
        x.reviewMd?.let { Block("بازبینی") { Md(it, color = c.textPrimary) } }
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp), itemVerticalAlignment = Alignment.CenterVertically) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                ActorAvatar(x.requestedBy, size = 18.dp)
                Text(actorFa(x.requestedBy), style = Divan.type.micro, color = c.textMuted)
            }
            Text(ago(x.createdAt), style = Divan.type.micro, color = c.textMuted)
            x.workRef?.let { RefChip(it) }
            x.source?.let { Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) { Text("منبع:", style = Divan.type.micro, color = c.textMuted); Fig("${it.player} · ${it.model}", style = Divan.type.figureSmall, color = c.textMuted) } }
        }
        Text("پذیرفتن یعنی آماده‌ی استفاده؛ انتشار در کانال یا استوری کار بیرونی است و همیشه کارت تصمیم (A3) میخواهد.", style = Divan.type.micro, color = c.textMuted)
        if (x.state == "review") {
            HqTextField(note, { note = it }, "یادداشت برای ایجنت مسئول (اختیاری)", Modifier.fillMaxWidth(), maxLength = 500)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                HqButton("بپذیر", {
                    action.mgmt(toasts) { q.set(env.api.acceptCreative(x.ref, note.trim())); env.cache.invalidate("creatives"); toasts.ok("پذیرفته شد. انتشار جایی، کار بیرونی است و کارت تصمیم میخواهد."); onDone() }
                }, variant = BtnVariant.PRIMARY, icon = DivanIcon.SEAL, loading = action.busy)
                HqButton("رد", {
                    action.mgmt(toasts) { q.set(env.api.rejectCreative(x.ref, note.trim())); env.cache.invalidate("creatives"); toasts.info("رد شد؛ یادداشتت برای ایجنت مسئول رفت."); onDone() }
                }, variant = BtnVariant.DANGER, icon = DivanIcon.REJECT, loading = action.busy)
            }
        }
    }
}

@Composable
private fun Block(title: String, content: @Composable () -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(title, style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = Divan.colors.goldInk)
        content()
    }
}

/** The owner's request: the company, image or video (Gemini, ≤ 10 s), where it goes (which sets the aspect and safe zones), the
 *  brief, and the Persian text the hub sets over it. */
@Composable
fun NewCreative(onMade: (String) -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val action = rememberAction()
    val companies = rememberCompanies().filter { it.kind != "holding" }
    val settings = rememberQuery("owner-settings", "settings") { ownerSettings() }
    val key = remember { UUID.randomUUID().toString() }
    var company by rememberSaveable { mutableStateOf<String?>(null) }
    var kind by rememberSaveable { mutableStateOf("image") }
    var placement by rememberSaveable { mutableStateOf("telegram_post") }
    var brief by rememberSaveable { mutableStateOf("") }
    var title by rememberSaveable { mutableStateOf("") }
    var body by rememberSaveable { mutableStateOf("") }
    var cta by rememberSaveable { mutableStateOf("") }
    var mark by rememberSaveable { mutableStateOf(true) }
    var dur by rememberSaveable { mutableIntStateOf(8) }
    var player by rememberSaveable { mutableStateOf<String?>(null) }
    val def = settings.data?.substitutes?.creativeDefaultImage ?: "gpt"
    val who = if (kind == "video") "gemini" else player ?: def
    val ok = company != null && brief.trim().length >= 8 && (kind == "image" || dur in 1..10)
    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        ChipRow {
            for (co in companies) Chip(company == co.code, { company = co.code }) { ink ->
                CoMark(co.code, height = 11.dp, ink = ink)
                Text(co.nameFa ?: co.code, style = Divan.type.small, color = ink, maxLines = 1)
            }
        }
        Segmented(listOf(SegOption("image", "عکس", DivanIcon.IMAGE), SegOption("video", "ویدیو (Gemini، ≤ ۱۰ ثانیه)", DivanIcon.VIDEO)), kind, { kind = it }, Modifier.fillMaxWidth())
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("جای انتشار", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                for ((k, fa) in PLACEMENT) Chip(placement == k, { placement = k }) { ink ->
                    Text(fa, style = Divan.type.small, color = ink, maxLines = 1)
                    Fig(PLACEMENT_ASPECT[k].orEmpty(), style = Divan.type.figureSmall, color = ink.copy(alpha = 0.7f))
                }
            }
            Text("نسبت و حاشیه‌ی امن را جای انتشار تعیین میکند.", style = Divan.type.micro, color = c.textMuted)
        }
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("brief", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
            HqTextField(brief, { brief = it }, "مثلاً: تصویر تبلیغ کانال تلگرام FX برای دوره‌ی آموزش رایگان تحلیل طلا", Modifier.fillMaxWidth(), singleLine = false, minLines = 3, maxLength = 1000)
            Text("هیچ داده‌ی مشتری؛ ورودی ماسک میشود.", style = Divan.type.micro, color = c.textMuted)
        }
        Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("متن فارسی روی تصویر (هاب میگذارد)", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
            HqTextField(title, { title = it }, "عنوان", Modifier.fillMaxWidth(), maxLength = 60)
            HqTextField(body, { body = it }, "متن کوتاه (اختیاری)", Modifier.fillMaxWidth(), maxLength = 120)
            HqTextField(cta, { cta = it }, "دعوت به اقدام (اختیاری)", Modifier.fillMaxWidth(), maxLength = 30)
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                HqSwitch(mark, { mark = it }, "نشان شرکت")
                Text("نشان شرکت", style = Divan.type.small, color = c.textSecondary)
            }
        }
        if (kind == "video") Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("مدت", style = Divan.type.small, color = c.textSecondary)
            HqTextField(dur.toString(), { v -> dur = minOf(10, v.filter(Char::isDigit).take(2).toIntOrNull() ?: 0) }, "8", Modifier.width(64.dp), figure = true, maxLength = 2)
            Text("ثانیه", style = Divan.type.small, color = c.textSecondary)
        } else ChipRow {
            Text("بازیکن:", style = Divan.type.caption, color = c.textSecondary)
            FilterChip("پیش‌فرض (${if (def == "gpt") "ChatGPT" else "Gemini"})", player == null, { player = null })
            for (p in listOf("gpt", "gemini")) Chip(player == p, { player = p }) { ink -> PlayerName(p, size = 12.dp, color = ink) }
        }
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            DIcon(DivanIcon.GLOBE, size = 13.dp, tint = c.textMuted)
            Text("از مرورگر لاگین‌شده‌ی هاب، با اشتراک نامحدود تو:", style = Divan.type.micro, color = c.textMuted)
            PlayerName(who, size = 11.dp, color = c.textMuted)
        }
        HqButton("بفرست", {
            val co = company ?: return@HqButton
            action.mgmt(toasts) {
                val out = env.api.createCreative(
                    co, kind, brief.trim(), placement,
                    title.trim().takeIf { it.isNotEmpty() }?.let { Overlay(it, body.trim().ifEmpty { null }, cta.trim().ifEmpty { null }, mark) },
                    if (kind == "video") dur else null, if (kind == "image") player else null, key,
                )
                env.cache.invalidate("creatives", "substitutes")
                toasts.ok("درخواست ${out.ref} رفت؛ ایجنت مسئول prompt را مینویسد.")
                onMade(out.ref)
            }
        }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, icon = DivanIcon.SEND, enabled = ok, loading = action.busy)
    }
}
