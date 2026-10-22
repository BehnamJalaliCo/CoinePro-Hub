package com.coinepro.hq.ui.v18

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableDoubleStateOf
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import androidx.media3.common.MediaItem
import androidx.media3.common.Player
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.media.clock
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.mgmtError
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.ModelMark
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.designsystem.toneColors
import com.coinepro.hq.ui.ActionRunner
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.Toasts
import com.coinepro.hq.ui.media.rememberPlayer
import com.coinepro.hq.ui.v14.Label
import com.coinepro.hq.ui.v17.Named
import java.util.Locale
import kotlinx.coroutines.delay

// Shared pieces of the management tools (contract §21), mirroring apps/web/src/components/v18/bits.tsx.

// ------------------------------------------------------------------ labels --
val REC = mapOf("approve" to Label("تأیید", Tone.POS), "reject" to Label("رد", Tone.NEG), "return" to Label("برگشت", Tone.WARN), "ask" to Label("اول بپرس", Tone.LAPIS))
val MEMO_STATE = mapOf(
    "writing" to Label("در حال نوشتن", Tone.LAPIS, live = true), "ready" to Label("آماده", Tone.POS), "failed" to Label("نوشته نشد", Tone.NEG),
    "stale" to Label("کهنه؛ کارت عوض شده", Tone.WARN),
)
val LEVEL3 = mapOf("low" to "کم", "medium" to "متوسط", "high" to "زیاد")
val TRIGGER = mapOf(
    "budget" to Named("بودجه", DivanIcon.BUDGET), "quota" to Named("سهمیه", DivanIcon.TREASURY), "compliance" to Named("انطباق", DivanIcon.OVERSEER),
    "incident" to Named("حادثه", DivanIcon.URGENT), "revenue" to Named("درآمد", DivanIcon.CHART), "waiting_decisions" to Named("کارت‌های منتظر", DivanIcon.CARTABLE),
    "finding" to Named("یافته", DivanIcon.SEARCH), "okr" to Named("OKR", DivanIcon.PLANNER),
)
val TRIGGER_STATE = mapOf("sent" to Label("فرستاده شد", Tone.POS), "deferred" to Label("فردا؛ سهم روز تمام", Tone.WARN), "capped" to Label("بالای سقف روزانه", Tone.NEUTRAL))
val CITATION = mapOf(
    "resolution" to Named("مصوبه", DivanIcon.SEAL), "decision" to Named("تصمیم", DivanIcon.DECISION), "deliverable" to Named("خروجی", DivanIcon.DELIVERABLE),
    "work" to Named("کار", DivanIcon.TASK), "message" to Named("پیام", DivanIcon.MESSAGES), "doc" to Named("سند", DivanIcon.REPORT), "code" to Named("کد", DivanIcon.CODE),
)
val AGENDA = mapOf(
    "decision" to Named("کارت منتظر", DivanIcon.CARTABLE), "risk" to Named("ریسک", DivanIcon.URGENT), "okr" to Named("OKR", DivanIcon.PLANNER),
    "finding" to Named("یافته", DivanIcon.SEARCH), "budget" to Named("بودجه", DivanIcon.BUDGET), "revenue" to Named("درآمد", DivanIcon.CHART),
    "outcome_review" to Named("بازبینی نتیجه", DivanIcon.REFRESH), "note" to Named("یادداشت", DivanIcon.EDIT),
)
val REVIEW_STATE = mapOf(
    "ready" to Label("آماده‌ی شروع", Tone.GOLD), "in_progress" to Label("در جریان", Tone.LAPIS, live = true), "done" to Label("انجام شد", Tone.POS),
    "skipped" to Label("رد شد", Tone.NEUTRAL),
)
val ITEM_STATUS = mapOf("open" to Label("باز", Tone.NEUTRAL), "done" to Label("انجام شد", Tone.POS), "deferred" to Label("عقب افتاد", Tone.WARN))
val AUDIO_STATE = mapOf(
    "ready" to Label("صدا آماده", Tone.POS), "pending" to Label("در حال ساخت صدا", Tone.LAPIS, live = true), "off" to Label("صدا خاموش", Tone.NEUTRAL),
    "failed" to Label("صدا ساخته نشد", Tone.WARN),
)
val HR_FLAG = mapOf(
    "promote_candidate" to Label("نامزد ارتقا", Tone.POS), "coach" to Label("آموزش", Tone.LAPIS), "demote_candidate" to Label("نامزد تنزل", Tone.WARN),
    "dismiss_candidate" to Label("نامزد برکناری", Tone.NEG), "probation_end" to Label("پایان دوره‌ی آزمایشی", Tone.GOLD),
)
val HR_STATE = mapOf("drafting" to Label("در حال نوشتن", Tone.LAPIS), "proposed" to Label("کارت‌ها منتظر تو", Tone.GOLD), "done" to Label("تمام شد", Tone.POS))

data class Rec(val fa: String, val tone: Tone, val icon: DivanIcon)

val RECOMMENDATION = mapOf(
    "promote" to Rec("ارتقا", Tone.POS, DivanIcon.STAR), "demote" to Rec("تنزل", Tone.WARN, DivanIcon.BACK), "dismiss" to Rec("برکناری", Tone.NEG, DivanIcon.DISMISS),
    "confirm" to Rec("تثبیت", Tone.GOLD, DivanIcon.SEAL),
)
val WASTE = linkedMapOf(
    "failed_runs" to ("اجرای شکست‌خورده" to "اجرای failed یا refused"), "cancelled_work" to ("کار لغوشده" to "اجرای کاری که بعد لغو شد"),
    "no_progress_runs" to ("اجرای بی‌پیشرفت" to "تعریف PR-022"), "retry_loops" to ("حلقه‌ی تکرار" to "۳ اجرا یا بیشتر روی یک کار در ۲۴ ساعت"),
    "router_errors" to ("خطای مسیریاب" to "فراخوانی خطادار با هزینه"), "duplicate_calls" to ("فراخوانی تکراری" to "همان درخواست در ۱۰ دقیقه"),
    "cache_miss" to ("از دست رفتن کش" to "ورودی بزرگ با همان پیشوند و بی‌خواندن کش"), "over_model" to ("مدل بالاتر از لازم" to "بالاتر از assignment پیش‌فرض"),
)
val NOTE_STATUS = linkedMapOf("open" to Label("باز", Tone.GOLD), "promoted" to Label("تبدیل شد", Tone.POS), "archived" to Label("بایگانی", Tone.NEUTRAL))

data class Promote(val fa: String, val icon: DivanIcon, val note: String)

val PROMOTE = linkedMapOf(
    "work" to Promote("کار", DivanIcon.TASK, "یک کار برای مدیرعامل همان شرکت (§4)"),
    "order" to Promote("فرمان", DivanIcon.COMMAND, "مثل فرمان صوتی، با مسیریابی قاعده‌محور (§17.4)"),
    "errand" to Promote("کار دستیار", DivanIcon.ASSISTANT, "دستیار شخصی انجامش میدهد (§18.3)"),
)
val REMINDER = mapOf("half" to "نیمه‌ی زمان", "before_expiry" to "۶ ساعت پیش از انقضا", "age_24h" to "۲۴ ساعت", "age_72h" to "۷۲ ساعت", "age_7d" to "۷ روز")

data class Verdict(val fa: String, val tone: Tone, val icon: DivanIcon)

val VERDICT_CLAIM = mapOf(
    "confirmed" to Verdict("تأیید شد", Tone.POS, DivanIcon.SEAL), "refuted" to Verdict("رد شد", Tone.NEG, DivanIcon.REJECT),
    "unverifiable" to Verdict("سنجش‌ناپذیر", Tone.NEUTRAL, DivanIcon.INFO),
)
val HEALTH = linkedMapOf(
    "truth" to (Label("راستی", Tone.NEG) to "دست‌کم ۲۰٪ ادعای رد شده از ۵ بررسی یا بیشتر"),
    "reliability" to (Label("پایداری", Tone.WARN) to "دست‌کم ۲۵٪ اجرای شکست‌خورده"),
    "loops" to (Label("حلقه", Tone.WARN) to "دو حلقه‌ی تکرار یا بیشتر"),
)
val VERDICT3 = mapOf("approve" to Label("تأیید", Tone.POS), "reject" to Label("رد", Tone.NEG), "return" to Label("برگشت", Tone.WARN))
val PRINCIPLE = mapOf("proposed" to Label("پیشنهادی", Tone.GOLD), "active" to Label("فعال", Tone.POS), "retired" to Label("کنار گذاشته", Tone.NEUTRAL))

/** A substitute player: its name as the owner knows it and its provider (for the logo). */
data class PlayerInfo(val fa: String, val provider: String)

val PLAYER = mapOf("gpt" to PlayerInfo("ChatGPT", "openai"), "gemini" to PlayerInfo("Gemini", "google"), "deepseek" to PlayerInfo("DeepSeek", "deepseek"))
val SEAT = linkedMapOf(
    "advisor_second_opinion" to ("نظر دوم مشاور" to "کنار هر یادداشت تصمیم، بی‌دیدن یادداشت مشاور"),
    "code_review" to ("بازبینی دوم کد" to "PR کارت انتشار، ممیزی تأسیس، diff کارگاه؛ هرگز تأیید یا مسدود نمیکند"),
    "overseer_cross_check" to ("بررسی دوم ناظر" to "ادعاهای نمونه‌ی PR-001 پیش از رأی"),
    "assistant_errand" to ("پیش‌نویس دستیار" to "خلاصه، ترجمه، بازنویسی؛ دستیار تمامش میکند"),
    "content_draft" to ("پیش‌نویس محتوا" to "کپشن، عنوان، توضیح متا برای ایجنت مسئول"),
    "long_read" to ("خواندن سند بلند" to "خلاصه با شماره‌ی خط یا صفحه که صداکننده میسنجد"),
    "quick_search" to ("جستجوی سریع" to "جواب با منبع؛ صداکننده هر منبع را خودش میخواند"),
    "third_opinion" to ("نظر سوم" to "کنار یادداشت مشاور و نظر دوم، بی‌دیدن هیچ‌کدام"),
    "creative" to ("عکس و ویدیو" to "از مرورگر لاگین‌شده؛ متن فارسی را هاب میگذارد"),
)
val SUB_STATUS = mapOf("ready" to Label("آماده", Tone.POS), "limited" to Label("محدود", Tone.WARN), "off" to Label("خاموش", Tone.NEUTRAL), "error" to Label("خطا", Tone.NEG))
val LOGIN = mapOf(
    "signed_in" to Label("وارد", Tone.POS), "signing_in" to Label("در حال ورود", Tone.LAPIS), "signed_out" to Label("خارج", Tone.NEUTRAL),
    "expired" to Label("منقضی", Tone.WARN),
)
val CAP = mapOf("cli" to "CLI", "web" to "وب", "api" to "API", "off" to "خاموش")
val PLACEMENT = linkedMapOf(
    "telegram_post" to "پست تلگرام", "telegram_story" to "استوری تلگرام", "instagram_post" to "پست اینستاگرام",
    "instagram_story" to "استوری اینستاگرام", "banner" to "بنر", "other" to "دیگر",
)
val CREATIVE = linkedMapOf(
    "queued" to Label("در صف", Tone.NEUTRAL, live = true), "generating" to Label("در حال ساخت", Tone.LAPIS, live = true), "review" to Label("منتظر نظر تو", Tone.GOLD),
    "accepted" to Label("پذیرفته", Tone.POS), "rejected" to Label("رد شد", Tone.NEUTRAL), "failed" to Label("ساخته نشد", Tone.NEG),
)
/** Connection statuses, §10 and §21.7 (⟨1.5.1⟩ `verifying` between created and ready). */
val CONN = mapOf(
    "enabled" to Label("روشن", Tone.POS), "ready" to Label("آماده", Tone.POS), "disabled" to Label("خاموش", Tone.NEUTRAL), "quota_exhausted" to Label("سهمیه تمام", Tone.WARN),
    "pending_secret" to Label("منتظر کلید", Tone.GOLD), "verifying" to Label("در حال بررسی", Tone.LAPIS, live = true), "error" to Label("خطا", Tone.NEG),
)

// ------------------------------------------------------- figures and dates --
private val J_MONTH = listOf("فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند")

/** "1405-07" → «مهر ۱۴۰۵» (a date in prose: the text face draws the digits). */
fun jMonth(key: String?): String {
    val m = Regex("^(\\d{4})-(\\d{1,2})$").find(key.orEmpty()) ?: return key ?: "—"
    return "${J_MONTH.getOrNull(m.groupValues[2].toInt() - 1) ?: m.groupValues[2]} ${m.groupValues[1]}"
}

/** "gpt-5.5" → "GPT 5.5", "deepseek-v3.2" → "DeepSeek V3.2"; other ids as they are. */
fun subModel(id: String?): String {
    if (id.isNullOrBlank()) return "—"
    val m = Regex("^(gpt|gemini|deepseek)-(.+)$", RegexOption.IGNORE_CASE).find(id) ?: return id
    val name = when (m.groupValues[1].lowercase()) { "gpt" -> "GPT"; "gemini" -> "Gemini"; else -> "DeepSeek" }
    return "$name ${m.groupValues[2].uppercase()}"
}

/** A 0..1 as a Latin percentage with [digits] decimals. */
fun pct01(v: Double?, digits: Int = 0): String = if (v == null || !v.isFinite()) "—" else String.format(Locale.US, "%.${digits}f%%", v * 100)

/** Hours in prose: «۳۶ ساعت» under two days, else whole days. */
fun hoursFa(h: Int): String = if (h < 48) "$h ساعت" else "${(h + 12) / 24} روز"

/** The owner's day (Asia/Tehran) [n] days ago, YYYY-MM-DD. */
fun tehDay(n: Int): String = com.coinepro.hq.core.format.HqClock.today().minusDays(n.toLong()).toString()

/** A §21 action: a failed call says its §21.12 code in Persian ([mgmtError]) instead of the server's sentence. */
fun ActionRunner.mgmt(toasts: Toasts, onError: ((ApiException) -> Boolean)? = null, block: suspend () -> Unit) =
    run(onError = { e -> if (onError?.invoke(e) != true) toasts.error(mgmtError(e)) }, block = block)

// ------------------------------------------------------------------ pieces --
/** The provider's logo beside a substitute player's name (or its model, Latin). */
@Composable
fun PlayerName(player: String, model: String? = null, size: Dp = 14.dp, color: Color = Divan.colors.textPrimary) {
    val p = PLAYER[player] ?: PlayerInfo(player, player)
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        ModelMark(model, provider = p.provider, size = size)
        Fig(if (model != null) subModel(model) else p.fa, style = Divan.type.figureSmall, color = color)
    }
}

/** What a substitute returns is labelled and never evidence (§21.13). */
@Composable
fun SubstituteNote(modifier: Modifier = Modifier) {
    val c = Divan.colors
    Row(modifier, verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        DIcon(DivanIcon.INFO, size = 12.dp, tint = c.textMuted)
        Text("بازیکن ذخیره؛ شاهد نیست", style = Divan.type.micro, color = c.textMuted)
    }
}

/** A confidence as a short bar and a Latin percentage (gold for the advisor's own, silver for anyone else's). */
@Composable
fun Confidence(v: Double, silver: Boolean = false) {
    val c = Divan.colors
    Row(Modifier.semantics { contentDescription = "اطمینان ${pct01(v)}" }, verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
            Box(Modifier.width(48.dp).height(6.dp).clip(CircleShape).background(c.tile)) {
                Box(Modifier.fillMaxWidth(v.toFloat().coerceIn(0f, 1f)).height(6.dp).clip(CircleShape).background(if (silver) c.silverInk else c.goldFill))
            }
        }
        Fig(pct01(v), style = Divan.type.figureSmall, color = c.textSecondary)
    }
}

/** A small titled block (gold heading) with an optional action at its end, like the web's Section. */
@Composable
fun Section(title: String, action: (@Composable () -> Unit)? = null, content: @Composable ColumnScope.() -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(title, Modifier.weight(1f), style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = Divan.colors.goldInk)
            action?.invoke()
        }
        content()
    }
}

/** A tone-coloured rounded tag with an optional icon (an opinion's agreement, a severity). */
@Composable
fun ToneTag(text: String, tone: Tone, icon: DivanIcon? = null, figure: Boolean = false) {
    val (bg, fg) = toneColors(tone)
    Row(Modifier.clip(CircleShape).background(bg).padding(horizontal = 8.dp, vertical = 2.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        if (icon != null) DIcon(icon, size = 12.dp, tint = fg)
        if (figure) Fig(text, style = Divan.type.figureSmall, color = fg) else Text(text, style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = fg, maxLines = 1)
    }
}

private val SPEEDS = listOf(1f, 1.25f, 1.5f)

/** The briefing player (§21.4): play or pause, a seekable bar, Latin time and the speed. The audio is Ogg/Opus from the hub (in the
 *  demo a short clip); it streams through the API's client, so nothing leaves the hub's session. Timelines run left to right. */
@Composable
fun AudioPlayer(fileId: String, label: String, compact: Boolean = false) {
    val media = LocalEnv.current.media
    val c = Divan.colors
    val player = rememberPlayer(media)
    var playing by remember { mutableStateOf(false) }
    var pos by remember { mutableDoubleStateOf(0.0) }
    var dur by remember { mutableDoubleStateOf(0.0) }
    var speed by remember { mutableFloatStateOf(1f) }
    DisposableEffect(player) {
        val l = object : Player.Listener {
            override fun onIsPlayingChanged(isPlaying: Boolean) { playing = isPlaying }
            override fun onPlaybackStateChanged(state: Int) {
                if (state == Player.STATE_READY && player.duration > 0) dur = player.duration / 1000.0
                if (state == Player.STATE_ENDED) { player.pause(); player.seekTo(0); pos = 0.0 }
            }
        }
        player.addListener(l)
        onDispose { player.removeListener(l) }
    }
    LaunchedEffect(playing) { while (playing) { pos = player.currentPosition / 1000.0; delay(150) } }
    fun load() { if (player.mediaItemCount == 0) { player.setMediaItem(MediaItem.fromUri(media.url(fileId))); player.prepare() } }
    Row(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(c.tile).padding(if (compact) 8.dp else 12.dp).semantics { contentDescription = label },
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Box(
            Modifier.size(if (compact) 36.dp else 44.dp).clip(CircleShape).background(c.goldFill)
                .clickable(role = Role.Button, onClickLabel = if (playing) "توقف" else "پخش") { load(); if (player.isPlaying) player.pause() else player.play() },
            contentAlignment = Alignment.Center,
        ) { DIcon(if (playing) DivanIcon.PAUSE else DivanIcon.RESUME, size = if (compact) 16.dp else 20.dp, tint = c.onGold, active = true) }
        CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                val p = if (dur > 0) (pos / dur).toFloat().coerceIn(0f, 1f) else 0f
                Box(
                    Modifier.fillMaxWidth().height(14.dp).pointerInput(dur) {
                        detectTapGestures { o -> if (dur > 0) { load(); player.seekTo((o.x / size.width * dur * 1000).toLong()); pos = o.x / size.width * dur } }
                    }.semantics { contentDescription = "جای پخش" },
                    contentAlignment = Alignment.CenterStart,
                ) {
                    Box(Modifier.fillMaxWidth().height(4.dp).clip(CircleShape).background(c.lineStrong))
                    Box(Modifier.fillMaxWidth(p).height(4.dp).clip(CircleShape).background(c.goldInk))
                }
                Row {
                    Fig(clock(pos), style = Divan.type.figureSmall, color = c.textMuted)
                    Box(Modifier.weight(1f))
                    Fig(clock(dur), style = Divan.type.figureSmall, color = c.textMuted)
                }
            }
        }
        Fig(
            "${if (speed % 1f == 0f) speed.toInt().toString() else speed.toString()}×",
            Modifier.clip(CircleShape).border(1.dp, c.lineStrong, CircleShape)
                .clickable(role = Role.Button, onClickLabel = "سرعت پخش") { speed = SPEEDS[(SPEEDS.indexOf(speed) + 1) % SPEEDS.size]; player.setPlaybackSpeed(speed) }
                .padding(horizontal = 8.dp, vertical = 3.dp),
            style = Divan.type.figureSmall, color = c.textSecondary,
        )
    }
}

/** A write-only secret (a key, a sign-in code): masked, left to right, never kept beyond the screen. */
@Composable
fun SecretField(value: String, onChange: (String) -> Unit, placeholder: String, label: String, modifier: Modifier = Modifier) {
    val c = Divan.colors
    CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
        BasicTextField(
            value, { if (it.length <= 500) onChange(it) },
            modifier.fillMaxWidth().semantics { contentDescription = label },
            singleLine = true,
            textStyle = Divan.type.figure.copy(color = c.textPrimary),
            cursorBrush = SolidColor(c.goldInk),
            visualTransformation = PasswordVisualTransformation(),
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, autoCorrectEnabled = false),
            decorationBox = { inner ->
                Box(Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(c.tile).border(1.dp, c.lineStrong, RoundedCornerShape(10.dp)).padding(12.dp)) {
                    if (value.isEmpty()) Fig(placeholder, style = Divan.type.figure, color = c.textMuted)
                    inner()
                }
            },
        )
    }
}
