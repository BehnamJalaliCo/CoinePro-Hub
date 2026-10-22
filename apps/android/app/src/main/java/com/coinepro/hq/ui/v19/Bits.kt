package com.coinepro.hq.ui.v19

import android.content.Context
import android.content.Intent
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
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.core.content.FileProvider
import androidx.media3.common.MediaItem
import androidx.media3.ui.PlayerView
import coil3.compose.AsyncImage
import com.coinepro.hq.core.Env
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.jDateTime
import com.coinepro.hq.core.media.fileSize
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.CheckResult
import com.coinepro.hq.core.net.EmailDraft
import com.coinepro.hq.core.net.FileRef
import com.coinepro.hq.core.net.MEDIA_CHECKS
import com.coinepro.hq.core.net.MediaItem as Item
import com.coinepro.hq.core.net.PublishRow
import com.coinepro.hq.core.net.mediaError
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.ActionRunner
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.Toasts
import com.coinepro.hq.ui.media.rememberPlayer
import com.coinepro.hq.ui.v14.Label
import com.coinepro.hq.ui.v16.prose
import java.io.File
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.Request

// Shared pieces of the media studio and the legal counsel (contract §22), mirroring apps/web/src/components/v19/bits.tsx.

// ------------------------------------------------------------------ labels --
/** One step of the pipeline (§22.2): each a work item to its role; code moves the item on. */
data class Stage(val key: String, val fa: String, val icon: DivanIcon, val states: Set<String>, val who: String)

val STAGES = listOf(
    Stage("script", "سناریو", DivanIcon.EDIT, setOf("scripting"), "سناریست"),
    Stage("direction", "کارگردانی", DivanIcon.VIDEO, setOf("directing"), "کارگردان"),
    Stage("motion", "موشن", DivanIcon.CODE, setOf("composing"), "طراح موشن، با کد"),
    Stage("voice", "صدا", DivanIcon.MIC, setOf("voicing"), "تهیه‌کننده‌ی صدا"),
    Stage("render", "رندر", DivanIcon.SERVER, setOf("rendering"), "کد، در سندباکس"),
    Stage("checks", "چک‌ها", DivanIcon.SEAL, setOf("checking", "review"), "کد و مدیر رسانه"),
    Stage("ready", "آماده", DivanIcon.TIME, setOf("scheduled", "waiting_owner"), "زمان‌بندی یا کارت تو"),
    Stage("published", "منتشرشده", DivanIcon.SEND, setOf("published"), "API رسمی"),
)
val STOPPED = setOf("held", "failed", "rejected")

fun stageOf(state: String): Int = STAGES.indexOfFirst { state in it.states }

val ITEM_STATE = mapOf(
    "scripting" to Label("سناریو", Tone.LAPIS, live = true), "directing" to Label("کارگردانی", Tone.LAPIS, live = true),
    "composing" to Label("ترکیب‌بندی با کد", Tone.LAPIS, live = true), "voicing" to Label("ساخت صدا", Tone.LAPIS, live = true),
    "rendering" to Label("رندر در سندباکس", Tone.LAPIS, live = true), "checking" to Label("چک‌ها", Tone.LAPIS, live = true),
    "review" to Label("بازبینی مدیر رسانه", Tone.GOLD), "scheduled" to Label("زمان‌بندی‌شده", Tone.POS), "published" to Label("منتشر شد", Tone.POS),
    "waiting_owner" to Label("منتظر تو", Tone.GOLD), "held" to Label("نگه‌داشته‌ی ناظر", Tone.NEG), "failed" to Label("شکست", Tone.NEG),
    "rejected" to Label("رد یا پایین آمد", Tone.NEUTRAL),
)

data class KindMeta(val fa: String, val icon: DivanIcon)

val KIND_FA = linkedMapOf(
    "reel" to KindMeta("ریلز", DivanIcon.VIDEO), "story" to KindMeta("استوری", DivanIcon.IMAGE), "post" to KindMeta("پست", DivanIcon.IMAGE),
    "carousel" to KindMeta("کاروسل", DivanIcon.IMAGE), "design" to KindMeta("طراحی رابط", DivanIcon.CODE),
)
val PLACEMENT_FA = linkedMapOf(
    "instagram_reel" to "ریلز اینستاگرام", "instagram_story" to "استوری اینستاگرام", "instagram_post" to "پست اینستاگرام",
    "telegram_post" to "پست کانال تلگرام", "telegram_story" to "استوری کانال تلگرام",
)
val CHANNEL_FA = mapOf("telegram" to "تلگرام", "instagram" to "اینستاگرام")

data class CheckMeta(val fa: String, val rule: String)

val CHECK_FA = mapOf(
    "brand" to CheckMeta("برند", "فقط IRANYekanX، رنگ‌ها از پالت شرکت، نشان در جای خودش"),
    "red_lines" to CheckMeta("خطوط قرمز", "الگوهای خط قرمز اساسنامه روی سناریو، متن تصویر و زیرنویس"),
    "risk_warning" to CheckMeta("هشدار ریسک", "هر محتوای ترید هشدار ریسک دارد، در صدا یا زیرنویس و در caption"),
    "facts" to CheckMeta("منبع عددها", "هر عدد سناریو منبع و تاریخ دارد"),
    "rights" to CheckMeta("حق استفاده", "فقط فایل خود شرکت، ساخته‌شده یا موسیقی کتابخانه‌ی مجاز"),
    "platform" to CheckMeta("محدودیت پلتفرم", "نسبت، طول، حجم و codec طبق محدودیت خود پلتفرم"),
    "qc" to CheckMeta("بازبینی مدیر رسانه", "رأی مدیر رسانه (media.review)"),
)

data class Result(val fa: String, val tone: Tone, val icon: DivanIcon)

val RESULT = mapOf(
    "pass" to Result("قبول", Tone.POS, DivanIcon.SEAL), "fail" to Result("رد", Tone.NEG, DivanIcon.URGENT), "n/a" to Result("لازم نیست", Tone.NEUTRAL, DivanIcon.INFO),
)
val QC_VERDICT = mapOf("pass" to Label("قبول", Tone.POS), "changes" to Label("اصلاح لازم", Tone.WARN), "reject" to Label("رد", Tone.NEG))
val PUBLISH_ERROR = mapOf(
    "no_api" to "API رسمی ندارد؛ با دست خودت", "account_not_configured" to "حساب کلید ندارد", "removed" to "از API حذف شد",
    "remove_by_hand" to "API حذف را اجازه نداد؛ از خود اپ پایین بیاور", "platform_limit" to "سقف خود پلتفرم پر بود",
    "series_not_sealed" to "برنامه مُهر نبود", "held" to "نگه‌داشته‌ی ناظر",
)

data class StatusMeta(val fa: String, val tone: Tone, val icon: DivanIcon)

val SERIES_STATUS = linkedMapOf(
    "draft" to StatusMeta("پیش‌نویس، مُهرنشده", Tone.NEUTRAL, DivanIcon.EDIT), "proposed" to StatusMeta("منتظر مُهر تو", Tone.GOLD, DivanIcon.SEAL),
    "sealed" to StatusMeta("مُهرشده", Tone.POS, DivanIcon.SEAL), "paused" to StatusMeta("متوقف", Tone.WARN, DivanIcon.PAUSE),
    "retired" to StatusMeta("بازنشسته", Tone.NEUTRAL, DivanIcon.CLOSE),
)
val CASE_KIND = linkedMapOf(
    "platform_restriction" to "محدودیت پلتفرم", "account_appeal" to "اعتراض حساب", "takedown" to "درخواست حذف", "partner_dispute" to "اختلاف با شریک",
    "policy_review" to "بازبینی سیاست", "contract_review" to "بازبینی قرارداد", "compliance" to "انطباق", "other" to "دیگر",
)
val CASE_STATUS = linkedMapOf(
    "waiting_owner" to Label("منتظر تو", Tone.GOLD), "open" to Label("باز", Tone.LAPIS), "waiting_reply" to Label("منتظر جواب", Tone.NEUTRAL, live = true),
    "resolved" to Label("حل شد", Tone.POS), "closed" to Label("بسته", Tone.NEUTRAL),
)
val TIMELINE = mapOf(
    "note" to KindMeta("یادداشت", DivanIcon.EDIT), "email_out" to KindMeta("ایمیل رفت", DivanIcon.SEND), "email_in" to KindMeta("ایمیل آمد", DivanIcon.MESSAGES),
    "form" to KindMeta("فرم", DivanIcon.REPORT), "decision" to KindMeta("تصمیم", DivanIcon.SEAL),
)
val ROLE_STATE = mapOf(
    "drafting" to Label("مدیر مینویسد", Tone.LAPIS, live = true), "in_review" to Label("بازبینی ناظر", Tone.LAPIS, live = true),
    "eval" to Label("آزمون خودش", Tone.LAPIS, live = true), "proposed" to Label("منتظر تأیید", Tone.GOLD), "active" to Label("فعال", Tone.POS),
    "rejected" to Label("رد شد", Tone.NEG), "retired" to Label("بازنشسته", Tone.NEUTRAL),
)
val ROLE_GATES = listOf("drafting" to "نوشتن", "in_review" to "بازبینی ناظر", "eval" to "آزمون", "proposed" to "تأیید", "active" to "فعال")

/** The overseer's five checks of a role draft (§18.15, §22.5). */
val REVIEW_CHECK_19 = linkedMapOf("injection" to "تزریق دستور", "secrets" to "رمز و کلید", "conflicts" to "تناقض با اساسنامه", "policy" to "اختیار و سیاست", "ceiling" to "سقف دپارتمان")

// ------------------------------------------------------------------ schedules (RRULE, owner TZ) --
val DAY_ORDER = listOf("SA", "SU", "MO", "TU", "WE", "TH", "FR")
val DAY_FA = mapOf("SA" to "شنبه", "SU" to "یکشنبه", "MO" to "دوشنبه", "TU" to "سه‌شنبه", "WE" to "چهارشنبه", "TH" to "پنجشنبه", "FR" to "جمعه")
val DAY_SHORT = mapOf("SA" to "ش", "SU" to "ی", "MO" to "د", "TU" to "س", "WE" to "چ", "TH" to "پ", "FR" to "ج")

/** The simple RRULEs the series editor writes: daily, or weekly on chosen days, at one time; anything else is shown raw. */
data class Rule(val freq: String, val days: List<String>, val hour: Int, val minute: Int)

fun parseRrule(s: String): Rule? {
    val p = s.split(';').mapNotNull { kv -> kv.split('=').takeIf { it.size == 2 }?.let { it[0] to it[1] } }.toMap()
    val freq = p["FREQ"]?.takeIf { it == "DAILY" || it == "WEEKLY" } ?: return null
    if (p["BYHOUR"].orEmpty().contains(',')) return null
    val hour = p["BYHOUR"]?.toIntOrNull() ?: return null
    val minute = (p["BYMINUTE"] ?: "0").toIntOrNull() ?: return null
    return Rule(freq, if (freq == "WEEKLY") p["BYDAY"].orEmpty().split(',').filter { it.isNotBlank() } else emptyList(), hour, minute)
}

fun buildRrule(r: Rule): String {
    val days = DAY_ORDER.filter { it in r.days }
    return if (r.freq == "DAILY" || days.isEmpty()) "FREQ=DAILY;BYHOUR=${r.hour};BYMINUTE=${r.minute}"
    else "FREQ=WEEKLY;BYDAY=${days.joinToString(",")};BYHOUR=${r.hour};BYMINUTE=${r.minute}"
}

fun hhmm(h: Int, m: Int) = "%02d:%02d".format(java.util.Locale.US, h, m)

/** «شنبه، سه‌شنبه، ساعت 18:30»: the days in words, the time a Latin figure; an RRULE the editor does not write stays raw. */
fun scheduleText(rrule: String): AnnotatedString = buildAnnotatedString {
    val r = parseRrule(rrule)
    if (r == null) { fig(rrule); return@buildAnnotatedString }
    append(if (r.freq == "DAILY") "هر روز" else DAY_ORDER.filter { it in r.days }.joinToString("، ") { DAY_FA.getValue(it) })
    append("، ساعت ")
    fig(hhmm(r.hour, r.minute))
}

// ------------------------------------------------------------------ figures --
fun ratioOf(aspect: String): Float = aspect.split(':').mapNotNull { it.toFloatOrNull() }.takeIf { it.size == 2 && it[1] > 0 }?.let { it[0] / it[1] } ?: 1f

/** An item's picture shape: its render's own size, else what its kind is. */
fun aspectOfItem(x: Item): String {
    val r = x.render
    if (r?.width != null && r.height != null) return "${r.width}:${r.height}"
    return when (x.kind) { "design" -> "16:10"; "post" -> "1:1"; "carousel" -> "4:5"; else -> "9:16" }
}

/** A seconds figure: "2.4s", "10s". */
fun secs(v: Double): String = (if (v % 1.0 == 0.0) v.toLong().toString() else "%.1f".format(java.util.Locale.US, v)) + "s"

/** A §22 action: a failed call says its §22.6 code in Persian ([mediaError]) instead of the server's sentence. */
fun ActionRunner.media(toasts: Toasts, onError: ((ApiException) -> Boolean)? = null, block: suspend () -> Unit) =
    run(onError = { e -> if (onError?.invoke(e) != true) toasts.error(mediaError(e)) }, block = block)

/** A file of the hub, fetched through the API's client (the session rides along) and handed to the phone's share sheet: a channel story
 *  the Bot API cannot post goes to Telegram from here, by the owner's hand. */
suspend fun shareFile(context: Context, env: Env, f: FileRef) {
    val out = withContext(Dispatchers.IO) {
        val file = File(env.media.scratch("shared"), f.name.replace(Regex("[^\\p{L}\\p{N}._-]"), "_"))
        env.api.client.newCall(Request.Builder().url(env.media.url(f.id)).build()).execute().use { r ->
            check(r.isSuccessful)
            file.outputStream().use { r.body.byteStream().copyTo(it) }
        }
        file
    }
    val uri = FileProvider.getUriForFile(context, "${context.packageName}.files", out)
    val send = Intent(Intent.ACTION_SEND).setType(f.mime).putExtra(Intent.EXTRA_STREAM, uri).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    context.startActivity(Intent.createChooser(send, f.name).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
}

// ------------------------------------------------------------------ pieces --
/** A render as the owner checks it: a film's poster with a play mark (it plays full screen), a still, or what is happening while
 *  there is none. The aspect is the render's own. */
@Composable
fun RenderPreview(file: FileRef?, aspect: String, label: String, modifier: Modifier = Modifier, compact: Boolean = false) {
    val media = LocalEnv.current.media
    val c = Divan.colors
    var playing by remember { mutableStateOf(false) }
    val video = file?.mime?.startsWith("video/") == true
    Box(
        modifier.aspectRatio(ratioOf(aspect)).clip(RoundedCornerShape(if (compact) 8.dp else 12.dp)).background(c.page)
            .then(if (video && !compact) Modifier.clickable(role = Role.Button, onClickLabel = "پخش") { playing = true } else Modifier)
            .semantics { contentDescription = label },
        contentAlignment = Alignment.Center,
    ) {
        when {
            file != null && video -> AsyncImage(media.imageModel(file.id, "poster"), label, media.images, Modifier.fillMaxSize(), contentScale = ContentScale.Crop)
            file != null && file.mime.startsWith("image/") -> AsyncImage(media.imageModel(file.id), label, media.images, Modifier.fillMaxSize(), contentScale = ContentScale.Crop)
            else -> Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(6.dp)) {
                DIcon(DivanIcon.VIDEO, size = if (compact) 18.dp else 28.dp, tint = c.textMuted)
                if (!compact) Text("هنوز رندر نشده", style = Divan.type.micro, color = c.textMuted)
            }
        }
        if (video) Box(Modifier.size(if (compact) 26.dp else 44.dp).clip(CircleShape).background(Color(0xA80B0D14)), contentAlignment = Alignment.Center) {
            DIcon(DivanIcon.RESUME, size = if (compact) 14.dp else 22.dp, tint = Color(0xFFF2EEE4))
        }
    }
    if (playing && file != null) VideoDialog(file.id) { playing = false }
}

/** A film full screen with the platform's controls, streamed through the API's client. */
@Composable
fun VideoDialog(fileId: String, onClose: () -> Unit) {
    val media = LocalEnv.current.media
    Dialog(onClose, DialogProperties(usePlatformDefaultWidth = false, decorFitsSystemWindows = false)) {
        val player = rememberPlayer(media)
        LaunchedEffect(fileId) {
            player.setMediaItem(MediaItem.fromUri(media.url(fileId)))
            player.prepare()
            player.play()
        }
        Box(Modifier.fillMaxSize().background(Color.Black)) {
            AndroidView({ PlayerView(it).apply { this.player = player } }, Modifier.fillMaxSize())
            Box(Modifier.statusBarsPadding().padding(8.dp).size(44.dp).clip(CircleShape).clickable(role = Role.Button, onClickLabel = "بستن", onClick = onClose), contentAlignment = Alignment.Center) {
                DIcon(DivanIcon.CLOSE, size = 24.dp, tint = Color.White)
            }
        }
    }
}

/** Where an item is in the pipeline: the steps, the current one marked; a stopped item says why. A design has four steps. */
@Composable
fun StageTrack(state: String, design: Boolean = false) {
    val c = Divan.colors
    val steps = if (design) STAGES.filter { it.key in setOf("script", "motion", "render", "checks") } else STAGES
    val idx = steps.indexOfFirst { state in it.states }
    FlowRow(horizontalArrangement = Arrangement.spacedBy(4.dp), verticalArrangement = Arrangement.spacedBy(4.dp), itemVerticalAlignment = Alignment.CenterVertically) {
        steps.forEachIndexed { i, s ->
            val done = idx > i || state == "published"
            val now = idx == i && state != "published"
            val (bg, fg) = when { now -> c.softGold to c.goldInk; done -> c.softPositive to c.positive; else -> c.tile to c.textMuted }
            Row(Modifier.clip(CircleShape).background(bg).padding(horizontal = 8.dp, vertical = 4.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                DIcon(if (done) DivanIcon.SEAL else s.icon, size = 12.dp, tint = fg)
                if (design && s.key == "script") Fig("brief", style = Divan.type.figureSmall, color = fg)
                else Text(s.fa, style = Divan.type.micro.copy(fontWeight = if (now) FontWeight.SemiBold else FontWeight.Normal), color = fg)
            }
        }
        if (state in STOPPED) ITEM_STATE[state]?.let { Pill(it.fa, it.tone, icon = DivanIcon.URGENT) }
    }
}

/** The seven checks of §22.2 by code (a design has two); a missing one is still running. */
@Composable
fun CheckGrid(checks: List<CheckResult>, design: Boolean = false) {
    val c = Divan.colors
    val keys = if (design) listOf("brand", "rights") else MEDIA_CHECKS
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        for (k in keys) {
            val x = checks.firstOrNull { it.key == k }
            val r = x?.let { RESULT[it.result] ?: RESULT.getValue("n/a") }
            Row(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(if (x?.result == "fail") c.softNegative else c.tile).padding(10.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                DIcon(r?.icon ?: DivanIcon.TIME, Modifier.padding(top = 2.dp), size = 15.dp, tint = when (r?.tone) { Tone.POS -> c.positive; Tone.NEG -> c.negative; else -> c.textMuted })
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        Text(CHECK_FA[k]?.fa ?: k, style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                        Text(r?.fa ?: "در صف", style = Divan.type.micro, color = if (r == null) c.textMuted else if (r.tone == Tone.NEG) c.negative else c.textSecondary)
                    }
                    Text(prose(x?.noteFa ?: CHECK_FA[k]?.rule.orEmpty()), style = Divan.type.micro, color = c.textMuted)
                }
            }
        }
    }
}

/** Where and when it goes out, through which official API, and what came back. */
@Composable
fun PublishRows(rows: List<PublishRow>) {
    val c = Divan.colors
    if (rows.isEmpty()) return Text("جای انتشاری ندارد.", style = Divan.type.caption, color = c.textMuted)
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        for (r in rows) {
            Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(c.tile).padding(horizontal = 12.dp, vertical = 8.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(PLACEMENT_FA[r.placement] ?: r.placement, Modifier.weight(1f), style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                    when {
                        r.error != null -> Pill(PUBLISH_ERROR[r.error] ?: r.error, if (r.error == "removed") Tone.NEUTRAL else Tone.WARN, icon = DivanIcon.URGENT)
                        r.externalId != null -> Pill(if (r.externalId == "manual") "با دست تو گذاشته شد" else "منتشر شد", Tone.POS, icon = DivanIcon.SEAL)
                        r.at != null -> Pill("در صف زمان‌بندی", Tone.LAPIS, icon = DivanIcon.TIME)
                        else -> Pill("هنوز نه", Tone.NEUTRAL)
                    }
                }
                if (r.at != null || (r.externalId != null && r.externalId != "manual")) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    r.at?.let { Text(jDateTime(it), style = Divan.type.micro, color = c.textMuted) }
                    Box(Modifier.weight(1f))
                    if (r.externalId != null && r.externalId != "manual") Fig(r.externalId, style = Divan.type.figureSmall, color = if (r.url != null) c.goldInk else c.textMuted)
                }
            }
        }
    }
}

/** A file as a small Latin chip: its name and size; its content lives in the hub's store. */
@Composable
fun FileChip(f: FileRef, icon: DivanIcon = DivanIcon.ATTACH, modifier: Modifier = Modifier) {
    val c = Divan.colors
    Row(modifier.clip(CircleShape).background(c.tile).padding(horizontal = 10.dp, vertical = 4.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        DIcon(icon, size = 12.dp, tint = c.textSecondary)
        Fig(f.name, Modifier.weight(1f, fill = false), style = Divan.type.figureSmall, color = c.textSecondary)
        Fig(fileSize(f.size), style = Divan.type.figureSmall, color = c.textMuted)
    }
}

/** «غیرتجاری» is said on every use of such a voice (§22.3). */
@Composable
fun LicenceBadge(commercial: Boolean, licence: String) {
    val c = Divan.colors
    Row(
        Modifier.clip(CircleShape).background(if (commercial) c.tile else c.softWarning).padding(horizontal = 8.dp, vertical = 2.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        DIcon(if (commercial) DivanIcon.LOCK else DivanIcon.URGENT, size = 11.dp, tint = if (commercial) c.textSecondary else c.warning)
        if (!commercial) Text("غیرتجاری ·", style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = c.warning)
        Fig(licence, style = Divan.type.figureSmall, color = if (commercial) c.textSecondary else c.warning)
    }
}

/** The exact message the seal is bound to (§22.4): from, to, cc, subject, body, the attachments' hashes and the digest. Nothing is
 *  ever sent without it, and any change is a new card. */
@Composable
fun ExactEmail(e: EmailDraft) {
    val c = Divan.colors
    val ltr = e.lang == "en"
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.card).padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            @Composable fun Line(label: String, value: String, strong: Boolean = false) = Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Text(label, Modifier.width(52.dp), style = Divan.type.caption, color = c.textMuted)
                if (ltr || !strong) Fig(value, Modifier.weight(1f), style = Divan.type.figureSmall.copy(fontWeight = if (strong) FontWeight.SemiBold else FontWeight.Normal), color = c.textPrimary, maxLines = 3)
                else Text(value, Modifier.weight(1f), style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
            }
            Line("از", e.from)
            Line("به", e.to.joinToString(", "))
            if (e.cc.isNotEmpty()) Line("رونوشت", e.cc.joinToString(", "))
            Line("موضوع", e.subject, strong = true)
        }
        Box(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.card).padding(12.dp)) {
            if (ltr) Fig(e.bodyMd, style = Divan.type.figureSmall.copy(lineHeight = Divan.type.small.lineHeight), color = c.textPrimary, maxLines = 60)
            else Text(prose(e.bodyMd), style = Divan.type.small, color = c.textPrimary)
        }
        if (e.attachments.isNotEmpty()) FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(4.dp), itemVerticalAlignment = Alignment.CenterVertically) {
            Text("پیوست:", style = Divan.type.micro, color = c.textMuted)
            for (a in e.attachments) {
                FileChip(a)
                Fig("sha256 ${a.sha256.take(8)}", style = Divan.type.figureSmall, color = c.textMuted)
            }
        }
        Text(
            buildAnnotatedString {
                append("مُهر به همین پیام بسته است: "); fig("digest ${e.digest.take(16)}…")
                append(". همان یک بار فرستاده میشود؛ هر تغییری بعد از دیدن تو کارت تازه میخواهد. هیچ ایمیلی خودکار فرستاده نمیشود.")
            },
            style = Divan.type.micro, color = c.textMuted,
        )
    }
}

/** A titled block with an optional end action (the web's Block). */
@Composable
fun Block(title: String, modifier: Modifier = Modifier, action: (@Composable () -> Unit)? = null, content: @Composable () -> Unit) {
    Column(modifier, verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(title, Modifier.weight(1f), style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = Divan.colors.goldInk, maxLines = 2, overflow = TextOverflow.Ellipsis)
            action?.invoke()
        }
        content()
    }
}
