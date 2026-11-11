package com.coinepro.hq.ui.v31

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.HorizontalDivider
import com.coinepro.hq.designsystem.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.NL_STATE_FA
import com.coinepro.hq.core.format.HqClock
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.jDateTime
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.NlCampaign
import com.coinepro.hq.core.net.NlList
import com.coinepro.hq.core.net.Newsletter
import com.coinepro.hq.core.net.StepUp
import com.coinepro.hq.core.net.gated
import com.coinepro.hq.core.net.idText
import com.coinepro.hq.designsystem.BarTone
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.MeterBar
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.activity
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v29.plain
import com.coinepro.hq.ui.v29.served
import java.time.LocalTime
import java.time.ZoneId

// Contract §31.3 ⟨1.13⟩ the company's «خبرنامه» tab: its lists with their sizes, its campaigns (A/B subject, scheduled send, opens and
// clicks), a new campaign by hand, and the send time. A list over its size limit needs the passkey.

private fun pct(part: Long?, whole: Long?): String = if (part == null || whole == null || whole <= 0) "—" else String.format(java.util.Locale.US, "%.1f%%", part * 100.0 / whole)

@Composable
fun CompanyNewsletter(code: String) {
    val q = rememberQuery("newsletter:$code", "newsletter", "growth", maxAgeMs = 30_000) { gated(HubFeature.GROWTH) { newsletter(code) } }
    val has = served(HubFeature.GROWTH)
    var adding by rememberSaveable { mutableStateOf(false) }
    var scheduling by rememberSaveable { mutableStateOf<String?>(null) }
    val n = q.data
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        SectionTitle("خبرنامه", note = "ایمیل به مخاطبانی که خودشان عضو شده‌اند؛ لغو عضویت یک‌ضربه است") {
            if (has && n != null && n.lists.isNotEmpty()) HqButton("خبرنامه‌ی تازه", { adding = true }, variant = BtnVariant.PRIMARY, size = BtnSize.SM, icon = DivanIcon.ADD)
        }
        when {
            !has -> Empty("خبرنامه با به‌روزرسانی بعدی هاب میاید", icon = DivanIcon.MESSAGES)
            n == null && q.error != null -> ErrorBlock(q.error, { q.refresh() })
            n == null -> Skeleton(Modifier.fillMaxWidth().height(140.dp), radius = 16.dp)
            else -> NewsletterBody(n) { scheduling = it }
        }
    }
    if (adding && n != null) com.coinepro.hq.ui.v14.HqSheet({ adding = false }, "خبرنامه‌ی تازه", sub = "پیش‌نویس ساخته میشود؛ زمان فرستادنش را جدا میگذاری.") {
        NewsletterForm(code, n.lists) { adding = false }
    }
    scheduling?.let { id ->
        val camp = n?.campaigns?.firstOrNull { it.id.idText == id }
        val list = n?.lists?.firstOrNull { it.id.idText == camp?.list?.idText }
        if (camp != null) com.coinepro.hq.ui.v14.HqSheet({ scheduling = null }, "زمان فرستادن", sub = camp.subject) {
            ScheduleBody(camp, list) { scheduling = null }
        }
    }
}

/** Lists and campaigns (also what the screenshot draws). */
@Composable
fun NewsletterBody(n: Newsletter, onSchedule: (String) -> Unit) {
    val c = Divan.colors
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        if (n.lists.isEmpty()) Empty("هنوز فهرستی نیست", icon = DivanIcon.MESSAGES, body = "فهرست مخاطبان را خبرنامه‌ی همین شرکت میسازد؛ بعد از ساخته شدنش اینجا میاید.")
        for (l in n.lists) HqCard(Modifier.fillMaxWidth()) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(plain(l.name), style = Divan.type.bodyStrong, modifier = Modifier.weight(1f))
                Text(plain("${l.subscribers} نفر"), style = Divan.type.caption, color = c.textSecondary)
            }
            val limit = l.sizeLimit
            if (limit != null && limit > 0) {
                val over = l.subscribers > limit
                MeterBar(l.subscribers * 100.0 / limit, Modifier.padding(top = 8.dp), tone = if (over) BarTone.WARN else BarTone.SILVER)
                Text(if (over) plain("از سقف ${limit} نفر گذشته؛ فرستادن به این فهرست مُهر تو را میخواهد.") else plain("سقف فرستادن بدون مُهر: ${limit} نفر"), style = Divan.type.micro, color = if (over) c.warning else c.textMuted, modifier = Modifier.padding(top = 4.dp))
            }
        }
        if (n.campaigns.isNotEmpty()) SectionTitle("آخرین خبرنامه‌ها")
        for (k in n.campaigns) HqCard(Modifier.fillMaxWidth()) {
            val st = NL_STATE_FA[k.state] ?: (k.state to Tone.SILVER)
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(plain(k.subject), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), modifier = Modifier.weight(1f), maxLines = 2)
                Pill(st.first, st.second, dot = true)
            }
            if (!k.subjectB.isNullOrBlank()) Text(plain("موضوع دوم (آزمایش): " + k.subjectB), style = Divan.type.caption, color = c.textSecondary, modifier = Modifier.padding(top = 4.dp))
            k.scheduledAt?.let { Text(plain((if (k.state == "sent") "فرستاده شد " else "زمان فرستادن: ") + jDateTime(it)), style = Divan.type.caption, color = c.textMuted, modifier = Modifier.padding(top = 4.dp)) }
            if (k.state == "sent") Row(Modifier.padding(top = 8.dp), horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                Text(plain("فرستاده: ${k.sent ?: 0}"), style = Divan.type.caption, color = c.textSecondary)
                Text(plain("باز شد: " + pct(k.opens, k.sent)), style = Divan.type.caption, color = c.textSecondary)
                Text(plain("کلیک: " + pct(k.clicks, k.sent)), style = Divan.type.caption, color = c.textSecondary)
            }
            if (k.state == "draft" || k.state == "scheduled") HqButton(if (k.state == "draft") "زمان‌بندی کن" else "زمانش را عوض کن", { onSchedule(k.id.idText) }, Modifier.padding(top = 8.dp), variant = BtnVariant.SILVER, size = BtnSize.SM, icon = DivanIcon.TIME)
        }
    }
}

@Composable
fun NewsletterForm(code: String, lists: List<NlList>, onDone: () -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val action = rememberAction()
    val c = Divan.colors
    var list by rememberSaveable { mutableStateOf(lists.firstOrNull()?.id?.idText.orEmpty()) }
    var subject by rememberSaveable { mutableStateOf("") }
    var subjectB by rememberSaveable { mutableStateOf("") }
    var body by rememberSaveable { mutableStateOf("") }
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        if (lists.size > 1) {
            Text("به کدام فهرست", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                for (l in lists) FilterChip(l.name, list == l.id.idText, { list = l.id.idText })
            }
        }
        Text("موضوع", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
        HqTextField(subject, { subject = it }, "موضوع ایمیل", Modifier.fillMaxWidth(), maxLength = 150)
        Text("موضوع دوم، برای آزمایش (اختیاری)", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
        HqTextField(subjectB, { subjectB = it }, "نصف مخاطبان این را میبینند", Modifier.fillMaxWidth(), maxLength = 150)
        Text("متن", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
        HqTextField(body, { body = it }, "متن خبرنامه", Modifier.fillMaxWidth(), singleLine = false, minLines = 6, maxLength = 20000)
        HqButton("بساز", {
            action.run {
                env.api.newNewsletter(code, list, subject.trim(), subjectB.trim().ifBlank { null }, body.trim())
                env.cache.invalidate("newsletter", "campaign-calendar")
                toasts.ok("پیش‌نویس خبرنامه ساخته شد.")
                onDone()
            }
        }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, icon = DivanIcon.ADD, enabled = list.isNotBlank() && subject.trim().length >= 3 && body.trim().length >= 3, loading = action.busy)
    }
}

/** The send time: a few mornings ahead (07:00, the owner's zone); a list over its limit asks for the passkey. */
@Composable
fun ScheduleBody(camp: NlCampaign, list: NlList?, onDone: () -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val act = activity()
    val action = rememberAction()
    val c = Divan.colors
    val tz = ZoneId.of(com.coinepro.hq.core.format.OWNER_TZ)
    val today = HqClock.today()
    val over = list != null && (list.sizeLimit ?: Long.MAX_VALUE) < list.subscribers
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        if (over) Text("این فهرست از سقفش بزرگ‌تر است؛ زمان‌بندی با مُهر توست.", style = Divan.type.caption, color = c.warning)
        HorizontalDivider(color = c.lineDivider)
        for (n in 1L..3L) {
            val at = today.plusDays(n).atTime(LocalTime.of(7, 0)).atZone(tz).toInstant().toString()
            HqButton(if (n == 1L) "فردا ساعت 07:00" else "$n روز دیگر ساعت 07:00", {
                action.run {
                    val sign: StepUp = { a, t -> env.auth.stepUp(act, a, t) }
                    env.api.scheduleNewsletter(camp.id.idText, at, if (over) sign else null)
                    env.cache.invalidate("newsletter", "campaign-calendar")
                    toasts.ok("زمان فرستادن گذاشته شد.")
                    onDone()
                }
            }, Modifier.fillMaxWidth(), variant = if (n == 1L) BtnVariant.PRIMARY else BtnVariant.SECONDARY, icon = if (over) DivanIcon.SEAL else DivanIcon.TIME, loading = action.busy)
        }
    }
}
