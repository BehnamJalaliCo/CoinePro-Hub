package com.coinepro.hq.ui.settings

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.net.ManagementSettings
import com.coinepro.hq.core.net.management
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.HqSwitch
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.SegOption
import com.coinepro.hq.designsystem.Segmented
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v17.WEEKDAY_FA
import com.coinepro.hq.ui.v18.mgmt
import java.util.Locale

private val TIME = Regex("^([01]\\d|2[0-3]):[0-5]\\d$")

/** «ابزار مدیریت» in the settings (§21.12): every switch the owner may change, saved as the changed blocks with the version. */
@Composable
fun ManagementSettingsCard() {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val nav = LocalNav.current
    val c = Divan.colors
    val q = rememberQuery("owner-settings", "settings") { ownerSettings() }
    val dceo = rememberQuery("dceo:view", "dceo") { digitalCeo() }
    val action = rememberAction()
    val base = q.data?.management() ?: return
    var draft by remember { mutableStateOf<ManagementSettings?>(null) }
    // A time typed half-way stays in the field and only reaches the draft when it reads HH:MM.
    var reviewAt by remember(base.weeklyReview.at) { mutableStateOf(base.weeklyReview.at) }
    val d = draft ?: base
    val changed = d.changedFrom(base)
    val dirty = changed.isNotEmpty()
    val hidden = dceo.data?.hidden ?: 0
    fun set(x: ManagementSettings) { draft = x }

    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("ابزار مدیریت", note = "یادداشت خودکار، مرور هفتگی، گزارش صوتی، یادآوری، مدیر کل دیجیتال و بازیکن‌های ذخیره")
        Column(Modifier.padding(top = 6.dp)) {
            SettingRow("یادداشت خودکار مشاور", "کارت پرریسک، انتشار، تأسیس و طرح سرور") {
                Num(d.advisor.autoMemo.maxPerDay, "سقف روزانه") { set(d.copy(advisor = d.advisor.copy(autoMemo = d.advisor.autoMemo.copy(maxPerDay = it)))) }
                UnitLabel("در روز")
                HqSwitch(d.advisor.autoMemo.enabled, { set(d.copy(advisor = d.advisor.copy(autoMemo = d.advisor.autoMemo.copy(enabled = it)))) }, "یادداشت خودکار مشاور")
            }
            Div()
            SettingRow("گزارش فعال مشاور", "هرگز فوری؛ بالای سقف ثبت میشود و نمیرود") {
                Num(d.advisor.proactivePerDay, "سقف گزارش فعال") { set(d.copy(advisor = d.advisor.copy(proactivePerDay = it))) }
                UnitLabel("در روز")
            }
            Div()
            SettingRow("مرور هفتگی با مشاور", "دستور ۳۰ دقیقه پیش‌تر با کد ساخته میشود") {
                CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
                    HqTextField(reviewAt, { t ->
                        reviewAt = t
                        if (TIME.matches(t)) set(d.copy(weeklyReview = d.weeklyReview.copy(at = t)))
                    }, "10:00", Modifier.width(76.dp), maxLength = 5, figure = true)
                }
                HqSwitch(d.weeklyReview.enabled, { set(d.copy(weeklyReview = d.weeklyReview.copy(enabled = it))) }, "مرور هفتگی")
            }
            FlowRow(Modifier.padding(bottom = 8.dp), horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                for ((k, fa) in WEEKDAY_FA) {
                    val day = k.lowercase(Locale.US)
                    FilterChip(fa, d.weeklyReview.day == day, { set(d.copy(weeklyReview = d.weeklyReview.copy(day = day))) })
                }
            }
            Div()
            SettingRow("گزارش صبحگاهی صوتی", "Piper روی خود هاب؛ هیچ صدایی بیرون نمیرود") {
                HqSwitch(d.audioBriefings.morning, { set(d.copy(audioBriefings = d.audioBriefings.copy(morning = it))) }, "گزارش صبحگاهی صوتی")
            }
            Div()
            SettingRow("نامه‌ی هفتگی مدیرعامل‌ها", "شنبه‌ها؛ نسخه‌ی صوتی جدا", link = "نامه‌ها" to { nav.go("letter") }) {
                UnitLabel("صدا")
                HqSwitch(d.audioBriefings.ceoLetters, { set(d.copy(audioBriefings = d.audioBriefings.copy(ceoLetters = it))) }, "صدای نامه‌ها")
                UnitLabel("نامه")
                HqSwitch(d.ceoWeeklyLetter.enabled, { set(d.copy(ceoWeeklyLetter = d.ceoWeeklyLetter.copy(enabled = it))) }, "نامه‌ی هفتگی")
            }
            Div()
            SettingRow("یادآوری کارتابل", "نیمه‌ی زمان و ۶ ساعت پیش از انقضا؛ بی‌انقضا در ۲۴ و ۷۲ ساعت و ۷ روز") {
                HqSwitch(d.reminders.enabled, { set(d.copy(reminders = d.reminders.copy(enabled = it))) }, "یادآوری کارتابل")
            }
            Div()
            SettingRow("مدیر کل دیجیتال", "فقط پیش‌بینی", link = "دقت و اصول" to { nav.go("digital-ceo") }) {
                HqSwitch(d.digitalCeo.enabled, { set(d.copy(digitalCeo = d.digitalCeo.copy(enabled = it))) }, "مدیر کل دیجیتال")
            }
            Segmented(
                listOf(SegOption("after", "بعد از تصمیم"), SegOption("before", "پیش از تصمیم")), d.digitalCeo.reveal,
                { set(d.copy(digitalCeo = d.digitalCeo.copy(reveal = it))) }, Modifier.fillMaxWidth().padding(bottom = 8.dp),
            )
            if (d.digitalCeo.reveal == "before" && hidden < 30) {
                Row(
                    Modifier.fillMaxWidth().padding(bottom = 8.dp).clip(RoundedCornerShape(10.dp)).background(c.softWarning).padding(10.dp),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    DIcon(DivanIcon.URGENT, size = 14.dp, tint = c.warning)
                    Text(
                        "دقت هنوز سنجیده نشده: فقط $hidden پیش‌بینی پنهان داریم (دست‌کم ۳۰ لازم است). پیش‌بینی‌هایی که پیش از تصمیم ببینی در دقت «تمیز» شمرده نمیشوند.",
                        style = Divan.type.caption, color = c.textPrimary,
                    )
                }
            }
            Div()
            SettingRow("بازیکن‌های ذخیره", "اگر روز ۱۵ ماه ارزش مصرف زیر این نسبت باشد، پیشنهاد باز کردن جایگاه میاید؛ خودبه‌خود باز نمیشود", link = "بازیکن‌ها" to { nav.go("substitutes") }) {
                Ratio(d.substitutes.behindRatio) { set(d.copy(substitutes = d.substitutes.copy(behindRatio = it))) }
            }
            Text("بازیکن پیش‌فرض عکس", style = Divan.type.caption, color = c.textMuted, modifier = Modifier.padding(bottom = 6.dp))
            Segmented(
                listOf(SegOption("gpt", "ChatGPT"), SegOption("gemini", "Gemini")), d.substitutes.creativeDefaultImage,
                { set(d.copy(substitutes = d.substitutes.copy(creativeDefaultImage = it))) }, Modifier.fillMaxWidth(),
            )
        }
        Row(Modifier.fillMaxWidth().padding(top = 14.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            HqButton("ذخیره‌ی ابزار مدیریت", {
                val version = q.data?.version ?: return@HqButton
                action.mgmt(toasts) {
                    q.set(env.api.saveOwnerSettings(version, changed))
                    env.cache.invalidate("settings", "dceo")
                    draft = null
                    toasts.ok("تنظیمات ابزار مدیریت ذخیره شد.")
                }
            }, Modifier.weight(1f), variant = BtnVariant.PRIMARY, enabled = dirty, loading = action.busy)
            if (dirty) HqButton("برگرداندن", { draft = null; reviewAt = base.weeklyReview.at }, variant = BtnVariant.GHOST)
        }
    }
}

@Composable
private fun SettingRow(label: String, note: String, link: Pair<String, () -> Unit>? = null, controls: @Composable () -> Unit) {
    val c = Divan.colors
    Row(Modifier.fillMaxWidth().padding(vertical = 8.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(label, style = Divan.type.small, color = c.textPrimary)
            Text(note, style = Divan.type.micro, color = c.textMuted)
            if (link != null) HqButton(link.first, link.second, variant = BtnVariant.TEXT, size = com.coinepro.hq.designsystem.BtnSize.SM)
        }
        controls()
    }
}

@Composable
private fun ColumnScope.Div() = HorizontalDivider(color = Divan.colors.lineDivider)

@Composable
private fun UnitLabel(text: String) = Text(text, style = Divan.type.micro, color = Divan.colors.textMuted)

/** A count in Latin digits: the field reads and writes the number, an empty field is zero. */
@Composable
private fun Num(value: Int, label: String, onChange: (Int) -> Unit) {
    CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
        HqTextField(value.toString(), { t ->
            val digits = t.map { ch -> if (ch in '۰'..'۹') '0' + (ch - '۰') else ch }.filter { it.isDigit() }.joinToString("")
            onChange(digits.take(3).toIntOrNull() ?: 0)
        }, label, Modifier.width(60.dp), maxLength = 3, figure = true)
    }
}

/** A ratio 0..1; a half-typed "0." stays in the field. */
@Composable
private fun Ratio(value: Double, onChange: (Double) -> Unit) {
    var text by remember(value) { mutableStateOf(value.toString()) }
    CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
        HqTextField(text, { t ->
            text = t
            t.replace('٫', '.').toDoubleOrNull()?.let { onChange(it.coerceIn(0.0, 1.0)) }
        }, "0.4", Modifier.width(68.dp), maxLength = 4, figure = true)
    }
}
