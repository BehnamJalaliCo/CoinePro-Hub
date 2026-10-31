package com.coinepro.hq.ui.substitutes

import com.coinepro.hq.ui.itemMotion
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.format.jDateTime
import com.coinepro.hq.core.format.jDayOfMonth
import com.coinepro.hq.core.format.tokens
import com.coinepro.hq.core.format.until
import com.coinepro.hq.core.format.usd
import com.coinepro.hq.core.net.CLI_LOGIN_CMD
import com.coinepro.hq.core.net.SeatIn
import com.coinepro.hq.core.net.Substitute
import com.coinepro.hq.core.net.SubstituteLogin
import com.coinepro.hq.core.net.WEB_LOGIN_CMD
import com.coinepro.hq.core.net.toIn
import com.coinepro.hq.designsystem.BarTone
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.HqSwitch
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.MeterBar
import com.coinepro.hq.designsystem.ModelMark
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.activity
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.v14.HqSheet
import com.coinepro.hq.ui.v14.LabelPill
import com.coinepro.hq.ui.v16.ChipRow
import com.coinepro.hq.ui.v16.Notice
import com.coinepro.hq.ui.v16.TerminalCommand
import com.coinepro.hq.ui.v18.CAP
import com.coinepro.hq.ui.v18.LOGIN
import com.coinepro.hq.ui.v18.PLAYER
import com.coinepro.hq.ui.v18.PlayerInfo
import com.coinepro.hq.ui.v18.SEAT
import com.coinepro.hq.ui.v18.SUB_STATUS
import com.coinepro.hq.ui.v18.SecretField
import com.coinepro.hq.ui.v18.mgmt
import com.coinepro.hq.ui.v18.pct01
import com.coinepro.hq.ui.v18.subModel
import kotlinx.coroutines.delay

// بازیکن‌های ذخیره (contract §21.13), mirroring apps/web/src/app/(app)/substitutes/page.tsx and components/v18/substitutes.tsx:
// GPT, Gemini and DeepSeek, their CLI and browser sign-ins, their seats and their Jalali month against the subscription's $20, and
// the creatives they render. Claude holds the project; a substitute answers one bounded question and is never evidence.

private val RULES = listOf(
    "Claude صاحب پروژه است" to "کد، تصمیم، رأی، یافته، متن مشتری، هر کار A2 به بالا و هر خروجی نهایی با ایجنت Claude مسئول میماند.",
    "یک سؤال محدود" to "بازیکن ذخیره رشته‌ی پیام، حافظه و مسیر نوشتن ندارد؛ با مشتری حرف نمیزند و چیزی منتشر نمیکند.",
    "ورودی ماسک‌شده" to "هیچ داده یا گفت‌وگوی مشتری، رمز یا فایل شرکت دیگر؛ کد فقط در بازبینی کد، از checkout فقط‌خواندنی.",
    "خروجی برچسب‌دار، نه شاهد" to "هر جواب منبعش را دارد و با لوگوی ارائه‌دهنده دیده میشود؛ هیچ یافته یا ادعایی فقط با حرف او بسته یا رد نمیشود.",
    "هیچ جابه‌جایی پنهانی" to "بازیکن محدود، خارج‌شده یا خاموش، جایگاهش رد میشود و صداکننده با مدل خودش ادامه میدهد؛ اجرای Claude هیچ‌وقت به بازیکن ذخیره نمیرود.",
    "سقف خودش" to "از سقف روزانه‌ی توکن ایجنت‌ها کم نمیکند؛ اشتراک و سقف روزانه‌ی هر جایگاه محدودش میکنند و خزانه با هزینه‌ی معادل ثبتش میکند.",
)

@Composable
fun SubstitutesScreen(creative0: String? = null) {
    val c = Divan.colors
    val q = rememberQuery("substitutes", "substitutes", "treasury", maxAgeMs = 60_000) { substitutes() }
    val r = refresher(q)
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item { PageHeader("بازیکن‌های ذخیره", eyebrow = "Claude کل پروژه را در دست دارد؛ این‌ها برای یک کار محدود به زمین میآیند") }
        item {
            Text(
                "ChatGPT Plus و Google AI Pro را میپردازی، پس باید در طول ماه کار کنند: مدل‌های کدنویسی‌شان از CLI برای بررسی، نظر دوم، پیش‌نویس و خواندن سند بلند، و چت و ساخت عکس و ویدیو از مرورگر لاگین‌شده‌ی هاب برای تبلیغات. DeepSeek رایگان، فقط از مرورگر، برای جستجوی سریع و نظر سوم.",
                style = Divan.type.small, color = c.textSecondary,
            )
        }
        val list = q.data
        when {
            list == null && q.error != null -> item { ErrorBlock(q.error, { q.refresh() }) }
            list == null -> items(2) { Skeleton(Modifier.fillMaxWidth().height(380.dp), radius = 16.dp) }
            else -> items(list, key = { it.player }) { Box(itemMotion()) { PlayerCard(it) } }
        }
        item { CreativesCard(creative0) }
        item {
            HqCard(Modifier.fillMaxWidth()) {
                SectionTitle("قاعده‌ی نیمکت", note = "هیچ استثنایی ندارد")
                Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    for ((t, b) in RULES) Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        DIcon(DivanIcon.LOCK, size = 16.dp, tint = c.goldInk, modifier = Modifier.padding(top = 2.dp))
                        Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                            Text(t, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                            Text(b, style = Divan.type.caption, color = c.textSecondary)
                        }
                    }
                }
            }
        }
    }
}

// ------------------------------------------------------------------------- player --
/** One substitute player: who it is, whether it can play today, what it did this Jalali month against its price, and its seats. */
@Composable
fun PlayerCard(s: Substitute) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val act = activity()
    val c = Divan.colors
    val conns = rememberQuery("connections", "treasury") { connections() }
    val settings = rememberQuery("owner-settings", "settings") { ownerSettings() }
    val action = rememberAction()
    var seats by remember { mutableStateOf(false) }
    var login by remember { mutableStateOf(false) }
    var webOut by remember { mutableStateOf(false) }
    val p = PLAYER[s.player] ?: PlayerInfo(s.player, s.player)
    val conn = conns.data?.firstOrNull { it.key == s.connection }
    val m = s.month
    val ratio = m.valueRatio
    val behind = settings.data?.substitutes?.behindRatio ?: 0.4
    // The 15th of the Jalali month (§21.13): behind the ratio by then, the morning report suggests seats to widen.
    val late = ratio != null && ratio < behind && jDayOfMonth() >= 15
    HqCard(Modifier.fillMaxWidth()) {
        Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Box(Modifier.size(44.dp).clip(RoundedCornerShape(12.dp)).background(c.tile), contentAlignment = Alignment.Center) { ModelMark(null, provider = p.provider, size = 24.dp) }
                Column(Modifier.weight(1f)) {
                    Text(p.fa, style = Divan.type.bodyStrong)
                    Text(buildAnnotatedString {
                        append(s.login.planFa + " · "); fig(s.connection)
                        if (s.runner != null) { append(" · "); fig(s.runner) } else append(" · بی‌CLI")
                    }, style = Divan.type.micro, color = c.textMuted)
                }
                LabelPill(SUB_STATUS[s.status], s.status)
            }
            s.statusReason?.let { reason ->
                Text(reason + (s.limitedUntil?.let { "، ${until(it)}" } ?: ""), Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(c.softWarning).padding(horizontal = 12.dp, vertical = 8.dp), style = Divan.type.caption, color = c.textPrimary)
            }
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("این ماه", Modifier.weight(1f), style = Divan.type.caption, color = c.textSecondary)
                    Fig(usd(m.equivUsd), style = Divan.type.figureSmall, color = c.textPrimary)
                    if ((m.priceUsd.toDoubleOrNull() ?: 0.0) > 0) Text(buildAnnotatedString { append("از "); fig(usd(m.priceUsd)) }, style = Divan.type.caption, color = c.textMuted)
                    else Text("رایگان", style = Divan.type.caption, color = c.textMuted)
                    if (ratio != null) Fig(pct01(ratio), style = Divan.type.figureSmall.copy(fontWeight = FontWeight.SemiBold), color = if (late) c.warning else c.textPrimary)
                }
                if (ratio != null) Box(contentAlignment = Alignment.CenterStart) {
                    MeterBar(minOf(100.0, ratio * 100), tone = if (late) BarTone.WARN else BarTone.GOLD)
                    // The threshold (behind_ratio) as a thin mark from the bar's start.
                    Box(Modifier.fillMaxWidth(behind.toFloat().coerceIn(0f, 1f))) { Box(Modifier.align(Alignment.CenterEnd).width(2.dp).height(10.dp).clip(RoundedCornerShape(1.dp)).background(c.textMuted)) }
                }
                FlowRow(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    Text("${m.calls} فراخوانی", style = Divan.type.micro, color = c.textMuted)
                    Text("${m.skipped} رد شده", style = Divan.type.micro, color = c.textMuted)
                    Fig("${tokens(m.inputTokens)} in · ${tokens(m.outputTokens)} out", style = Divan.type.figureSmall, color = c.textMuted)
                    if (m.estimated) Text("تخمینی (CLI عدد نداد)", style = Divan.type.micro, color = c.textMuted)
                }
                if (late) Text("از نیمه‌ی ماه گذشته و ارزش مصرف زیر آستانه است؛ چند جایگاه را باز کن تا اشتراک هدر نرود. هیچ چیز خودبه‌خود باز نمیشود.", style = Divan.type.micro, color = c.warning)
            }
            Row(Modifier.height(IntrinsicSize.Min), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Column(Modifier.weight(1f).fillMaxHeight().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(10.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text("ورود CLI", Modifier.weight(1f), style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
                        if (s.runner != null) LabelPill(LOGIN[s.login.state], s.login.state) else Text("CLI ندارد", style = Divan.type.micro, color = c.textMuted)
                    }
                    if (s.runner != null) {
                        Text(s.login.lastOkAt?.let { "آخرین موفق ${ago(it)}" } ?: "—", style = Divan.type.micro, color = c.textMuted)
                        if (s.login.state != "signed_in") HqButton("ورود", { login = true }, size = BtnSize.SM, icon = DivanIcon.LOCK, enabled = conn != null)
                        else if (conn != null) HqButton("خروج با اثر انگشت", {
                            action.mgmt(toasts) {
                                env.api.connectionLogout(conn.id) { a, t -> env.auth.stepUp(act, a, t) }
                                env.cache.invalidate("substitutes", "treasury")
                                toasts.info("ورود CLI پاک شد.")
                            }
                        }, size = BtnSize.SM, variant = BtnVariant.GHOST, loading = action.busy)
                    } else Text("همه‌ی جایگاه‌هایش از مرورگر لاگین‌شده است.", style = Divan.type.micro, color = c.textMuted)
                }
                Column(Modifier.weight(1f).fillMaxHeight().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(10.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text("مرورگر هاب", Modifier.weight(1f), style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
                        LabelPill(LOGIN[s.web.state], s.web.state)
                    }
                    Fig("${s.web.account} · ${s.web.recipeVersion}", style = Divan.type.figureSmall, color = c.textMuted, maxLines = 2)
                    s.web.lastFailure?.let { Text(it, style = Divan.type.micro, color = c.warning) } ?: Text(s.web.lastOkAt?.let { "آخرین کار ${ago(it)}" } ?: "—", style = Divan.type.micro, color = c.textMuted)
                    if (s.web.state == "signed_in") HqButton("پاک کردن پروفایل", { webOut = true }, size = BtnSize.SM, variant = BtnVariant.GHOST)
                }
            }
            if (s.web.state != "signed_in") Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("ورود مرورگر فقط از ترمینال خودت (noVNC روی 127.0.0.1 با تونل SSH):", style = Divan.type.micro, color = c.textMuted)
                TerminalCommand(WEB_LOGIN_CMD[s.player] ?: "make web-login")
            }
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text("جایگاه‌ها", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
                        Text(listOf("متن" to s.capabilities.text, "عکس" to s.capabilities.image, "ویدیو" to s.capabilities.video).joinToString(" · ") { (k, v) -> "$k: ${CAP[v] ?: v}" }, style = Divan.type.micro, color = c.textMuted)
                    }
                    HqButton("ویرایش", { seats = true }, size = BtnSize.SM, variant = BtnVariant.TEXT, icon = DivanIcon.EDIT)
                }
                for (x in s.seats) {
                    val usedPct = if (x.perDay > 0) x.usedToday * 100.0 / x.perDay else 0.0
                    val skipped = !x.enabled || s.status != "ready" || (if (x.via == "web") s.web.state != "signed_in" else s.login.state != "signed_in")
                    Column(Modifier.fillMaxWidth().padding(vertical = 4.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Text(SEAT[x.seat]?.first ?: x.seat, style = Divan.type.small, color = if (skipped) c.textMuted else c.textPrimary, maxLines = 1)
                            Fig("${CAP[x.via] ?: x.via} · ${subModel(x.model)}", style = Divan.type.figureSmall, color = c.textMuted)
                            if (!x.enabled) Text("خاموش", style = Divan.type.micro, color = c.textMuted) else if (skipped) Text("رد میشود", style = Divan.type.micro, color = c.warning)
                            Box(Modifier.weight(1f))
                            Text(buildAnnotatedString {
                                fig("${x.usedToday}/${x.perDay}")
                                if (x.perDayVideo != null) { append(" · ویدیو "); fig("${x.usedTodayVideo ?: 0}/${x.perDayVideo}") }
                            }, style = Divan.type.small, color = c.textSecondary)
                        }
                        MeterBar(usedPct, tone = if (usedPct >= 100) BarTone.WARN else BarTone.SILVER, height = 4.dp)
                    }
                }
            }
            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                s.models.forEach { x ->
                    Fig("${x.label} · ${x.tier}${if (x.available) "" else " · —"}", Modifier.clip(CircleShape).background(if (x.available) c.tile else c.softWarning).padding(horizontal = 8.dp, vertical = 2.dp),
                        style = Divan.type.figureSmall, color = if (x.available) c.textSecondary else c.warning)
                }
            }
        }
    }
    if (seats) HqSheet({ seats = false }, "جایگاه‌های ${p.fa}", sub = "مُهر به همین فهرست بسته است. جایگاه متنی پیش‌فرض CLI است (اندازه‌پذیر و سریع)؛ «وب» یعنی چت نامحدود در مرورگر لاگین‌شده‌ی هاب.") {
        SeatsEditor(s) { seats = false }
    }
    if (login && conn != null) HqSheet({ login = false }, "ورود CLI ${p.fa}", sub = "هاب رمز تو را هرگز نمیبیند؛ اعتبار فقط در volume خود runner میماند (بیرون از backup) و هیچ پاسخ، لاگ یا Audit آن را ندارد.") {
        LoginContent(s, conn.id)
    }
    if (webOut) AlertDialog(
        onDismissRequest = { webOut = false },
        containerColor = c.overlay,
        title = { Text("پاک کردن پروفایل مرورگر", style = Divan.type.h3) },
        text = {
            Text(buildAnnotatedString {
                append("پروفایل "); fig(s.web.account); append(" و کوکی‌هایش پاک میشود. جایگاه‌هایی که از وب کار میکنند تا وقتی خودت دوباره وارد شوی رد میشوند (")
                fig(WEB_LOGIN_CMD[s.player].orEmpty()); append(").")
                s.web.lastOkAt?.let { append(" آخرین کار: "); append(com.coinepro.hq.designsystem.timesFig(jDateTime(it))); append(".") }
            }, style = Divan.type.small, color = c.textSecondary)
        },
        confirmButton = {
            HqButton("پاک کن، با اثر انگشت", {
                action.mgmt(toasts) {
                    env.api.webLogout(s.player) { a, t -> env.auth.stepUp(act, a, t) }
                    env.cache.invalidate("substitutes", "treasury")
                    webOut = false
                    toasts.info("پروفایل پاک شد؛ جایگاه‌های وب تا ورود دوباره رد میشوند.")
                }
            }, variant = BtnVariant.DANGER, loading = action.busy)
        },
        dismissButton = { HqButton("انصراف", { webOut = false }, variant = BtnVariant.GHOST) },
    )
}

// -------------------------------------------------------------------------- seats --
/** Every seat of one player: on or off, CLI or web, the model and the daily caps; saved whole with the passkey on the exact list. */
@Composable
fun SeatsEditor(s: Substitute, onDone: () -> Unit = {}) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val act = activity()
    val c = Divan.colors
    val action = rememberAction()
    val rows = remember(s.player, s.version) { mutableStateListOf<SeatIn>().apply { addAll(s.seats.map { it.toIn() }) } }
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        rows.forEachIndexed { i, r ->
            Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(if (r.enabled) c.tile else c.card).padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Column(Modifier.weight(1f)) {
                        Text(SEAT[r.seat]?.first ?: r.seat, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                        Text(SEAT[r.seat]?.second.orEmpty(), style = Divan.type.micro, color = c.textMuted)
                    }
                    HqSwitch(r.enabled, { rows[i] = r.copy(enabled = it) }, "${SEAT[r.seat]?.first ?: r.seat}: روشن")
                }
                ChipRow {
                    for (v in listOf("cli", "web")) {
                        val on = r.via == v
                        val ok = v != "cli" || s.runner != null
                        Text(CAP[v] ?: v, Modifier.clip(CircleShape).background(if (on) c.softGold else c.card).clickable(enabled = ok, role = Role.RadioButton) { rows[i] = r.copy(via = v) }.padding(horizontal = 12.dp, vertical = 5.dp),
                            style = Divan.type.small.copy(fontWeight = if (on) FontWeight.SemiBold else FontWeight.Normal), color = if (!ok) c.disabledText else if (on) c.goldInk else c.textSecondary)
                    }
                    for (m in s.models) {
                        val on = r.model == m.id
                        Fig(m.label + if (m.available) "" else " (نیست)", Modifier.clip(CircleShape).background(if (on) c.softGold else c.card).clickable(enabled = m.available, role = Role.RadioButton) { rows[i] = r.copy(model = m.id) }.padding(horizontal = 12.dp, vertical = 5.dp),
                            style = Divan.type.figureSmall, color = if (!m.available) c.disabledText else if (on) c.goldInk else c.textSecondary)
                    }
                }
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("در روز", style = Divan.type.caption, color = c.textSecondary)
                    HqTextField(r.perDay.toString(), { v -> rows[i] = r.copy(perDay = v.filter(Char::isDigit).take(3).toIntOrNull() ?: 0) }, "0", Modifier.width(72.dp), figure = true, maxLength = 3)
                    if (r.perDayVideo != null) {
                        Text("ویدیو", style = Divan.type.caption, color = c.textSecondary)
                        HqTextField(r.perDayVideo.toString(), { v -> rows[i] = r.copy(perDayVideo = v.filter(Char::isDigit).take(2).toIntOrNull() ?: 0) }, "0", Modifier.width(60.dp), figure = true, maxLength = 2)
                    }
                }
            }
        }
        HqButton("ذخیره با اثر انگشت", {
            action.mgmt(toasts) {
                env.api.putSeats(s, rows.toList()) { a, t -> env.auth.stepUp(act, a, t) }
                env.cache.invalidate("substitutes", "treasury")
                toasts.ok("جایگاه‌ها ذخیره شد.")
                onDone()
            }
        }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, icon = DivanIcon.SEAL, loading = action.busy)
    }
}

// ------------------------------------------------------------------------ sign-in --
/** The CLI's own headless sign-in, from the app: a device code, or an auth code pasted back (write-only, ≤ 10 minutes). */
@Composable
fun LoginContent(s: Substitute, connectionId: String) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val act = activity()
    val uri = LocalUriHandler.current
    val c = Divan.colors
    val action = rememberAction()
    var l by remember { mutableStateOf<SubstituteLogin?>(null) }
    var notReady by remember { mutableStateOf(false) }
    var code by remember { mutableStateOf("") }
    val waiting = l?.state == "waiting"
    LaunchedEffect(waiting) {
        while (waiting) {
            delay(2_000)
            val cur = l ?: break
            runCatching { env.api.connectionLoginState(connectionId, cur.id) }.getOrNull()?.let { l = it; if (it.state == "done") env.cache.invalidate("substitutes") }
        }
    }
    val cmd = CLI_LOGIN_CMD[s.player]
    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        val x = l
        if (x == null && !notReady) {
            Text("با اثر انگشت شروع کن؛ runner ورود بی‌مرورگر خود CLI را شروع میکند و نشانی ورود را میدهد. روی گوشی وارد شو.", style = Divan.type.small, color = c.textSecondary)
            HqButton("شروع ورود با اثر انگشت", {
                action.mgmt(toasts, onError = { e -> if (e.code == "not_ready") { notReady = true; true } else false }) {
                    l = env.api.connectionLogin(connectionId) { a, t -> env.auth.stepUp(act, a, t) }
                    env.cache.invalidate("substitutes")
                }
            }, variant = BtnVariant.PRIMARY, icon = DivanIcon.LOCK, loading = action.busy)
        }
        if (notReady) Notice(DivanIcon.INFO, c.tile, c.textSecondary) {
            Text("این نسخه‌ی CLI ورود بی‌مرورگر ندارد؛ از ترمینال خودت وارد شو:", style = Divan.type.small, color = c.textPrimary)
            cmd?.let { TerminalCommand(it) }
        }
        if (x != null) when (x.state) {
            "done" -> Notice(DivanIcon.SEAL, c.softPositive, c.positive) { Text("وارد شد. جایگاه‌های CLI از همین حالا کار میکنند.", style = Divan.type.small, color = c.textPrimary) }
            "waiting" -> Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Row(Modifier.clip(CircleShape).clickable(role = Role.Button, onClickLabel = "باز کردن نشانی ورود") { runCatching { uri.openUri(x.verificationUrl) } }.padding(4.dp),
                    verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    DIcon(DivanIcon.GLOBE, size = 16.dp, tint = c.goldInk)
                    Fig(x.verificationUrl, style = Divan.type.figureSmall, color = c.goldInk)
                }
                if (x.method == "device_code" && x.userCode != null) Column(
                    Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(c.tile).padding(16.dp),
                    horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(4.dp),
                ) {
                    Text("این کد را آن‌جا بزن", style = Divan.type.caption, color = c.textMuted)
                    Fig(x.userCode, style = Divan.type.figureL, color = c.textPrimary)
                    Text("${until(x.expiresAt)}؛ این صفحه خودش میفهمد.", style = Divan.type.micro, color = c.textMuted)
                } else Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("کدی که گوگل نشان داد", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
                    SecretField(code, { code = it }, "4/0Ab…", "کد ورود")
                    Text("فقط‌نوشتنی؛ ${until(x.expiresAt)}.", style = Divan.type.micro, color = c.textMuted)
                    HqButton("بفرست", {
                        action.mgmt(toasts) { l = env.api.connectionLoginCode(connectionId, x.id, code.trim()); code = ""; env.cache.invalidate("substitutes") }
                    }, variant = BtnVariant.PRIMARY, enabled = code.trim().length >= 6, loading = action.busy)
                }
            }
            else -> Notice(DivanIcon.URGENT, c.softWarning, c.warning) { Text(if (x.state == "expired") "وقتش گذشت؛ دوباره شروع کن." else "نشد: ${x.statusReason ?: "—"}", style = Divan.type.small, color = c.textPrimary) }
        }
        if (cmd != null && !notReady) Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("یا از ترمینال خودت:", style = Divan.type.micro, color = c.textMuted)
            TerminalCommand(cmd)
        }
    }
}
