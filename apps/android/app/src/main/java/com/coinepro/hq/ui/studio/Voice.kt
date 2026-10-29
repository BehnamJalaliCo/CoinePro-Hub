package com.coinepro.hq.ui.studio

import android.Manifest
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableDoubleStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.format.jDateTime
import com.coinepro.hq.core.media.VoiceRecorder
import com.coinepro.hq.core.media.clock
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.Voice
import com.coinepro.hq.core.net.mediaError
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
import com.coinepro.hq.designsystem.LiveDot
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.RatingRow
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.activity
import com.coinepro.hq.ui.media.Waveform
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.v14.figs
import com.coinepro.hq.ui.v16.ChipRow
import com.coinepro.hq.ui.v16.prose
import com.coinepro.hq.ui.v18.AudioPlayer
import com.coinepro.hq.ui.v19.LicenceBadge
import com.coinepro.hq.ui.v19.media
import java.util.Locale
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

// The hub's own voice (contract §22.3), mirroring apps/web/src/app/(app)/media/voice/page.tsx and components/v19/voice.tsx: the active
// voice and the owner's choice, the owner's own recorded reference, the blind listening test and the measured candidates.

private val LETTERS = listOf("الف", "ب", "ج", "د", "ه", "و", "ز", "ح")
private val VOICE_STATUS = mapOf("active" to ("فعال" to Tone.POS), "candidate" to ("نامزد" to Tone.NEUTRAL), "retired" to ("کنار گذاشته" to Tone.NEUTRAL))
private val RULES = listOf(
    "بی پرداخت به سرویس صدا" to "صدا روی خود هاب ساخته میشود، با مدل متن‌باز؛ همان موتوری که گزارش صوتی صبح را میخواند.",
    "انتخاب با گوش تو" to "هر نامزد همان متن‌های فارسی را میخواند (عدد، اصطلاح لاتین، کلمه‌ی کریپتو، جمله‌ی بلند)؛ سرور RTF و حافظه را اندازه میگیرد و تو کور نمره میدهی.",
    "لایسنس روی هر استفاده" to "صدای غیرتجاری بی‌انتخاب صریح تو فعال نمیشود و برچسبش همه‌جا دیده میشود.",
    "صدای خودت فقط روی هاب" to "نمونه‌ی ضبط‌شده‌ات مثل هر فایل تو نگه داشته میشود و هیچ‌جا فرستاده نمیشود.",
)

/** The order of the blind test: by a hash of each voice's id, so it says nothing about the voice (the web's own). */
private fun blind(id: String): Int = "$id·blind".fold(17) { a, ch -> (a * 33 + ch.code) % 100_003 }

private fun rtfFa(v: Voice): String = v.rtf?.let { String.format(Locale.US, "%.2f×", it) } ?: "—"

/** صدای هاب: what speaks now, the owner's choice, the blind test, the candidates and the owner's own voice. */
@Composable
fun VoiceScreen() {
    val c = Divan.colors
    val q = rememberQuery("media:voices", "media") { voices() }
    val r = refresher(q)
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item { PageHeader("صدای هاب", eyebrow = "متن‌باز، روی خود هاب، انتخاب با گوش تو") }
        item {
            Text(prose("برای ریلزها، استوری‌های صدادار و گزارش‌های صوتی. هیچ سرویس پولی صدا نیست؛ نامزدها روی CPU هاب اندازه گرفته میشوند و تو بی‌دیدن نام، با گوش انتخاب میکنی."), style = Divan.type.small, color = c.textSecondary)
        }
        val voices = q.data
        when {
            voices == null && q.error != null -> item { ErrorBlock(q.error, { q.refresh() }) }
            voices == null -> item { Skeleton(Modifier.fillMaxWidth().height(360.dp), radius = 16.dp) }
            else -> {
                item { ActiveVoice(voices) }
                item { BlindTest(voices) }
                item { VoiceRegistry(voices) }
                item { ReferenceCard() }
                item {
                    HqCard(Modifier.fillMaxWidth()) {
                        SectionTitle("قاعده‌ی صدا", note = "هیچ استثنایی ندارد")
                        Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            for ((t, b) in RULES) Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                                DIcon(DivanIcon.MIC, Modifier.padding(top = 2.dp), size = 16.dp, tint = c.goldInk)
                                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                                    Text(t, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                                    Text(prose(b), style = Divan.type.caption, color = c.textSecondary)
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

/** The owner's explicit choice, 🔏 `voice.activate`; a non-commercial voice is acknowledged first, in words. */
@Composable
private fun Activate(v: Voice) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val act = activity()
    val c = Divan.colors
    val action = rememberAction()
    var ask by remember { mutableStateOf(false) }
    fun go() = action.media(toasts) {
        env.api.activateVoice(v) { a, t -> env.auth.stepUp(act, a, t) }
        env.cache.invalidate("media")
        ask = false
        toasts.ok("«${v.nameFa}» صدای فعال هاب شد؛ گزارش‌های صوتی و برنامه‌های رسانه از همین میخوانند.")
    }
    HqButton("فعال کن", { if (v.licenceCommercial) go() else ask = true }, variant = BtnVariant.PRIMARY, size = BtnSize.SM, icon = DivanIcon.SEAL, loading = action.busy)
    if (ask) AlertDialog(
        onDismissRequest = { ask = false },
        containerColor = c.overlay,
        title = { Text("صدای غیرتجاری", style = Divan.type.h3) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(buildAnnotatedString {
                    append("کارت مدل «"); append(prose(v.nameFa)); append("» لایسنس "); fig(v.licence)
                    append(" را غیرتجاری میداند. فعال شدنش انتخاب صریح توست، و روی هر استفاده برچسب «غیرتجاری» میخورد.")
                }, style = Divan.type.small, color = c.textSecondary)
                Text("مسئله‌ی حقوقی با خود توست؛ هاب فقط آنچه روی کارت مدل آمده را نشان میدهد.", style = Divan.type.caption, color = c.textMuted)
            }
        },
        confirmButton = { HqButton("میدانم؛ با گذرکلید فعال کن", { go() }, variant = BtnVariant.PRIMARY, icon = DivanIcon.SEAL, loading = action.busy) },
        dismissButton = { HqButton("نه", { ask = false }, variant = BtnVariant.GHOST) },
    )
}

@Composable
private fun ActiveVoice(voices: List<Voice>) {
    val c = Divan.colors
    val active = voices.firstOrNull { it.status == "active" }
    val choice = voices.firstOrNull { it.id == "v-xtts-owner" } ?: voices.firstOrNull { it.speaker == "owner" }
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        HqCard(Modifier.fillMaxWidth()) {
            SectionTitle("صدای فعال", note = "گزارش صوتی صبح، نامه‌ی مدیرعامل‌ها و هر برنامه‌ی رسانه با صدا")
            if (active == null) Empty("هنوز صدایی فعال نیست", icon = DivanIcon.MIC)
            else Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(prose(active.nameFa), style = Divan.type.h3, color = c.textPrimary)
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp), itemVerticalAlignment = Alignment.CenterVertically) {
                    Fig(active.engine, style = Divan.type.figureSmall, color = c.textMuted)
                    LicenceBadge(active.licenceCommercial, active.licence)
                }
                Text(buildAnnotatedString {
                    append("RTF "); fig(rtfFa(active)); append(" · اوج حافظه "); fig(active.memFa); append(" روی CPU هاب")
                }, style = Divan.type.caption, color = c.textSecondary)
                active.heard.firstOrNull()?.file?.let { AudioPlayer(it.id, "نمونه‌ی ${active.nameFa}", compact = true) }
                active.noteFa?.let { Text(prose(it), style = Divan.type.caption, color = c.textMuted) }
            }
        }
        if (choice != null && choice.status != "active") HqCard(Modifier.fillMaxWidth(), tahrir = true) {
            SectionTitle("انتخاب تو", note = "۳۰ مهر: ParsVoice-XTTS، با صدای خود تو اگر نمونه ضبط کنی")
            Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(prose(choice.nameFa), style = Divan.type.bodyStrong, color = c.textPrimary)
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp), itemVerticalAlignment = Alignment.CenterVertically) {
                    LicenceBadge(choice.licenceCommercial, choice.licence)
                    Text(buildAnnotatedString { append("RTF "); fig(rtfFa(choice)); append(" · "); fig(choice.memFa) }, style = Divan.type.caption, color = c.textMuted)
                }
                Text("شنیدن کور پایین فقط تأیید نهایی است. بعد از گوش دادن، با یک مُهر فعالش کن؛ صدای غیرتجاری بی‌انتخاب صریح تو فعال نمیشود.", style = Divan.type.caption, color = c.textSecondary)
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Activate(choice)
                    if (choice.ownerScore != null) Pill("نمره‌ی کور تو: ${choice.ownerScore}", Tone.GOLD) else Pill("هنوز کور نشنیده‌ای", Tone.NEUTRAL, icon = DivanIcon.MIC)
                }
            }
        }
    }
}

/** The owner listens without names: clips labelled الف، ب، …, in an order that says nothing; a voice's name shows once it is scored. */
@Composable
private fun BlindTest(voices: List<Voice>) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val action = rememberAction()
    val speaking = remember(voices) { voices.filter { it.heard.isNotEmpty() }.sortedBy { blind(it.id) } }
    val scripts = speaking.firstOrNull()?.heard.orEmpty()
    var script by rememberSaveable { mutableStateOf<String?>(null) }
    val sc = script ?: scripts.firstOrNull()?.script
    val text = scripts.firstOrNull { it.script == sc }
    val scored = speaking.count { it.ownerScore != null }
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("شنیدن کور", note = "$scored از ${speaking.size} صدا نمره گرفته؛ نام هر صدا بعد از نمره‌ی تو دیده میشود")
        if (speaking.isEmpty()) return@HqCard Empty("هنوز نمونه‌ای اندازه‌گیری نشده", icon = DivanIcon.MIC)
        Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            ChipRow { for (s in scripts) FilterChip(s.titleFa, sc == s.script, { script = s.script }) }
            text?.let { Text(figs("«${it.textFa}»"), Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp), style = Divan.type.body, color = c.textPrimary) }
            speaking.forEachIndexed { i, v ->
                val clip = v.heard.firstOrNull { it.script == sc }
                val label = LETTERS.getOrNull(i) ?: (i + 1).toString()
                val shown = v.ownerScore != null
                Column(
                    Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(if (shown) c.tile else c.card)
                        .then(if (shown) Modifier else Modifier.border(1.dp, c.lineStrong, RoundedCornerShape(14.dp))).padding(12.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        Box(Modifier.size(36.dp).clip(CircleShape).background(c.softGold), contentAlignment = Alignment.Center) {
                            Text(label, style = Divan.type.small.copy(fontWeight = FontWeight.Bold), color = c.goldInk)
                        }
                        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                            Text(if (shown) prose(v.nameFa) else buildAnnotatedString { append("صدای $label") }, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, maxLines = 1, overflow = TextOverflow.Ellipsis)
                            if (shown) FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(2.dp), itemVerticalAlignment = Alignment.CenterVertically) {
                                LicenceBadge(v.licenceCommercial, v.licence)
                                if (v.speaker == "owner") Text("صدای خود تو", style = Divan.type.micro, color = c.textMuted)
                            } else Text("نام بعد از نمره", style = Divan.type.micro, color = c.textMuted)
                        }
                        if (shown) Pill(v.ownerScore.toString(), Tone.GOLD)
                    }
                    if (clip?.file != null) AudioPlayer(clip.file.id, "صدای $label، ${clip.titleFa}", compact = true)
                    else Text("این متن را نخوانده.", style = Divan.type.caption, color = c.textMuted)
                    Text("نمره‌ی تو", style = Divan.type.micro, color = c.textMuted)
                    RatingRow(v.ownerScore ?: 0, { n ->
                        action.media(toasts) {
                            env.api.scoreVoice(v.id, n)
                            env.cache.invalidate("media")
                            toasts.ok("صدای $label: نمره‌ی $n. حالا اسمش را میبینی.")
                        }
                    }, size = 26.dp)
                }
            }
        }
    }
}

/** Every candidate as the server measured it: RTF and peak memory on the hub's CPU, the licence as its card states it. */
@Composable
private fun VoiceRegistry(voices: List<Voice>) {
    val c = Divan.colors
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("نامزدها و اندازه‌گیری", note = "RTF و اوج حافظه روی CPU خود هاب؛ لایسنس همان‌طور که کارت هر مدل گفته")
        Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            for (v in voices) {
                val (stFa, stTone) = VOICE_STATUS[v.status] ?: VOICE_STATUS.getValue("candidate")
                val scored = v.ownerScore != null
                Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(prose(v.nameFa), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp), itemVerticalAlignment = Alignment.CenterVertically) {
                        Pill(stFa, stTone, dot = true)
                        if (v.speaker == "owner") Pill("صدای تو", Tone.GOLD, icon = DivanIcon.OWNER)
                        LicenceBadge(v.licenceCommercial, v.licence)
                    }
                    Fig(v.engine, style = Divan.type.figureSmall, color = c.textMuted)
                    Text(buildAnnotatedString {
                        append("RTF "); fig(rtfFa(v), c.textPrimary)
                        append("   حافظه "); fig(v.memFa, c.textPrimary)
                        append("   نمره‌ی کور ${v.ownerScore ?: "—"}")
                    }, style = Divan.type.caption, color = c.textSecondary)
                    v.measuredAt?.let { Text("اندازه‌گیری ${jDateTime(it)}", style = Divan.type.micro, color = c.textMuted) }
                    v.noteFa?.let { note ->
                        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            DIcon(DivanIcon.INFO, Modifier.padding(top = 2.dp), size = 13.dp, tint = c.textMuted)
                            Text(prose(note), Modifier.weight(1f), style = Divan.type.caption, color = c.textMuted)
                        }
                    }
                    if (v.status != "active" && v.heard.isNotEmpty() && scored) Activate(v)
                }
            }
        }
    }
}

/** The owner's own voice: 1–3 minutes of clean speech, recorded here, kept like any owner file on the hub and never sent anywhere. */
@Composable
private fun ReferenceCard() {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val ctx = LocalContext.current
    val c = Divan.colors
    val scope = rememberCoroutineScope()
    val q = rememberQuery("media:voices:reference", "media") { voiceReference() }
    val rec = remember(env) { VoiceRecorder(env.media.context, env.media.scratch("voice")) }
    var recording by remember { mutableStateOf(false) }
    var uploading by remember { mutableStateOf(false) }
    var elapsed by remember { mutableDoubleStateOf(0.0) }
    val levels = remember { mutableStateListOf<Float>().apply { repeat(32) { add(0f) } } }
    var ticker by remember { mutableStateOf<Job?>(null) }
    val r = q.data
    LaunchedEffect(r?.state) { while (r?.state == "processing") { delay(4_000); q.refresh() } }
    DisposableEffect(rec) { onDispose { ticker?.cancel(); rec.cancel() } }

    fun finish() {
        ticker?.cancel()
        recording = false
        val (file, seconds) = rec.stop() ?: return toasts.info("صدایی ضبط نشد.")
        elapsed = 0.0
        for (i in levels.indices) levels[i] = 0f
        if (seconds < 60) { file.delete(); return toasts.info("کمتر از یک دقیقه بود؛ دست‌کم یک دقیقه صدای تمیز لازم است.") }
        uploading = true
        scope.launch {
            try {
                val f = withContext(Dispatchers.IO) { env.api.upload("owner-reference.m4a", "audio/mp4", file.length(), { file.inputStream() }) }
                q.set(env.api.setVoiceReference(f.id))
                env.cache.invalidate("media")
                toasts.ok("نمونه‌ی صدایت روی هاب نشست؛ نامزدهای ساخت صدا از آن، متن‌های آزمون را دوباره میخوانند.")
            } catch (e: ApiException) {
                toasts.error(mediaError(e))
            } finally {
                uploading = false
                file.delete()
            }
        }
    }
    fun begin() {
        if (!rec.start()) return toasts.error("میکروفون در دسترس نیست.")
        recording = true
        ticker = scope.launch {
            while (isActive && rec.recording) {
                delay(90)
                elapsed = rec.seconds
                levels.removeAt(0); levels.add(rec.level())
                if (elapsed >= 180) { finish(); break }
            }
        }
    }
    val ask = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { ok ->
        if (ok) begin() else toasts.error("اجازه‌ی میکروفون داده نشده؛ از تنظیمات گوشی برای این اپ روشنش کن.")
    }

    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("صدای خود تو", note = "۱ تا ۳ دقیقه صدای تمیز؛ مثل هر فایل تو روی هاب میماند و هیچ‌جا فرستاده نمیشود")
        Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            when {
                q.loading -> Skeleton(Modifier.fillMaxWidth().height(40.dp))
                r != null -> FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp), itemVerticalAlignment = Alignment.CenterVertically) {
                    when (r.state) {
                        "ready" -> Pill("آماده", Tone.POS, dot = true)
                        "processing" -> Pill("در حال پردازش", Tone.LAPIS, live = true)
                        else -> Pill("پذیرفته نشد", Tone.NEG, dot = true)
                    }
                    if (r.durationS > 0) Text(buildAnnotatedString { append("نمونه‌ی "); fig(clock(r.durationS)) }, style = Divan.type.caption, color = c.textSecondary)
                    Text("ضبط ${ago(r.createdAt)}", style = Divan.type.caption, color = c.textSecondary)
                    r.reasonFa?.let { Text(it, style = Divan.type.caption, color = c.negative) }
                }
                else -> Text("هنوز نمونه‌ای ضبط نکرده‌ای. با نمونه، ParsVoice-XTTS و Chatterbox متن‌های آزمون را با صدای خودت هم میخوانند.".let(::prose), style = Divan.type.small, color = c.textSecondary)
            }
            Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                if (recording) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        LiveDot(c.negative, size = 10.dp)
                        Fig(clock(elapsed), style = Divan.type.figure, color = c.textPrimary)
                        Waveform(levels, Modifier.weight(1f).height(32.dp))
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        HqButton("تمام", { finish() }, variant = BtnVariant.PRIMARY, size = BtnSize.SM, icon = DivanIcon.STOP)
                        HqButton("دور بریز", { ticker?.cancel(); rec.cancel(); recording = false; elapsed = 0.0 }, variant = BtnVariant.GHOST, size = BtnSize.SM)
                    }
                } else {
                    Text(buildAnnotatedString { append("یک جای ساکت؛ با صدای معمولی یک متن آموزشی بخوان، مثل وقتی برای کانال حرف میزنی. حداکثر "); fig("3:00"); append(".") }, style = Divan.type.caption, color = c.textSecondary)
                    HqButton(if (r != null) "ضبط دوباره" else "ضبط نمونه", {
                        if (ContextCompat.checkSelfPermission(ctx, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) begin() else ask.launch(Manifest.permission.RECORD_AUDIO)
                    }, size = BtnSize.SM, icon = DivanIcon.MIC, loading = uploading)
                }
            }
        }
    }
}
