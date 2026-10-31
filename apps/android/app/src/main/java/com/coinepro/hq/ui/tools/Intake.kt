package com.coinepro.hq.ui.tools

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.foundation.background
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.net.IntakeSourceIn
import com.coinepro.hq.core.net.PRODUCT_EVENTS
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.CompanyMark
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.activity
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v16.Chip
import com.coinepro.hq.ui.v16.ChipRow
import com.coinepro.hq.ui.v16.CompanyChips
import com.coinepro.hq.ui.v16.INTAKE_KIND
import com.coinepro.hq.ui.v16.Labelled
import com.coinepro.hq.ui.v16.TerminalCommand
import com.coinepro.hq.ui.v16.go
import com.coinepro.hq.ui.v14.HqSheet

private val IP = Regex("^(?:\\d{1,3}(?:\\.\\d{1,3}){3}|[0-9a-fA-F:]+:[0-9a-fA-F:]*)(?:/\\d{1,3})?$")

/** ورودی‌ها از بیرون (contract §19.8): the only new public routes — Telegram webhooks, Chatwoot and product events — each signed;
 *  a source's secret is set in the owner's terminal, never through the API. */
@Composable
fun IntakeCard() {
    val c = Divan.colors
    val q = rememberQuery("intake:sources", "intake", maxAgeMs = 120_000) { intakeSources() }
    var neu by remember { mutableStateOf(false) }
    HqCard(Modifier.fillMaxWidth(), padding = PaddingValues(horizontal = 14.dp, vertical = 12.dp)) {
        SectionTitle("ورودی‌ها از بیرون", note = "تلگرام، Chatwoot و رویداد محصول؛ هر کدام با امضا، رمزش فقط در ترمینال تو") {
            HqButton("ثبت منبع", { neu = true }, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.ADD)
        }
        val list = q.data
        when {
            list == null && q.error != null -> ErrorBlock(q.error, { q.refresh() })
            list == null -> Skeleton(Modifier.fillMaxWidth().padding(top = 10.dp).height(120.dp))
            else -> Column(Modifier.padding(top = 6.dp)) {
                list.forEachIndexed { i, s ->
                    if (i > 0) HorizontalDivider(color = c.lineDivider)
                    Column(Modifier.padding(vertical = 10.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            CompanyMark(s.company, height = 12.dp, mono = true, ink = c.textSecondary)
                            Text(INTAKE_KIND[s.kind] ?: s.kind, style = Divan.type.small, modifier = Modifier.weight(1f))
                            Pill(if (s.configured) "پیکربندی‌شده" else "بی‌رمز", if (s.configured) Tone.POS else Tone.NEUTRAL, dot = true)
                        }
                        FlowRow(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                            Text(if (s.lastEventAt != null) "آخرین رویداد ${ago(s.lastEventAt)}" else "هنوز رویدادی نرسیده", style = Divan.type.micro, color = c.textMuted)
                            Text(buildAnnotatedString { append("۲۴ ساعت: "); fig(s.events24h.toString(), c.textSecondary); append(" رویداد") }, style = Divan.type.micro, color = c.textMuted)
                            Text(buildAnnotatedString { append("رد: "); fig(s.rejected24h.toString()) }, style = Divan.type.micro, color = if (s.rejected24h > 0) c.negative else c.textMuted)
                        }
                        if (!s.configured) TerminalCommand("make intake-secret COMPANY=${s.company} SOURCE=${s.kind}")
                    }
                }
            }
        }
    }
    if (neu) RegisterSheet { neu = false }
}

@Composable
private fun RegisterSheet(onClose: () -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val act = activity()
    val c = Divan.colors
    val action = rememberAction()
    var company by rememberSaveable { mutableStateOf<String?>(null) }
    var kind by rememberSaveable { mutableStateOf("product") }
    var ips by rememberSaveable { mutableStateOf("") }
    var events by rememberSaveable { mutableStateOf(PRODUCT_EVENTS) }
    val list = ips.split(Regex("[\\s,]+")).map { it.trim() }.filter { it.isNotEmpty() }
    // Telegram is accepted only from its own published ranges; the others need their sources' addresses.
    val valid = company != null && list.all { IP.matches(it) } && (kind == "telegram" || list.isNotEmpty()) && (kind != "product" || events.isNotEmpty())
    HqSheet(onClose, "ثبت منبع ورودی", sub = "ثبت با اثر انگشت و روی همین متن؛ رمز منبع هرگز از API نمیگذرد.") {
        Labelled("شرکت") { CompanyChips(company, { company = it }, all = false) }
        Labelled("نوع") { ChipRow { for ((k, fa) in INTAKE_KIND) FilterChip(fa, kind == k, { kind = k }) } }
        Labelled("IPهای مجاز (هر خط یکی، CIDR هم میشود)") {
            HqTextField(ips, { ips = it }, if (kind == "telegram") "Telegram: published ranges only" else "203.0.113.10", Modifier.fillMaxWidth(), singleLine = false, minLines = 3, maxLength = 2000, figure = true)
            if (kind == "telegram") Text("تلگرام فقط از بازه‌های IP منتشرشده‌ی خودش پذیرفته میشود؛ خالی بگذار مگر محدودتر بخواهی.", style = Divan.type.micro, color = c.textMuted)
        }
        if (kind == "product") Labelled("رویدادهای پذیرفته") {
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                for (e in PRODUCT_EVENTS) Chip(e in events, { events = if (e in events) events - e else PRODUCT_EVENTS.filter { it in events || it == e } }) { ink ->
                    Fig(e, style = Divan.type.figureSmall, color = ink)
                }
            }
        }
        Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("بعد از ثبت، در ترمینال خودت روی سرور:", style = Divan.type.caption, color = c.textSecondary)
            TerminalCommand("make intake-secret COMPANY=${company ?: "…"} SOURCE=$kind")
            Text(buildAnnotatedString { append("امضای بد یا timestamp کهنه بی‌هیچ جزئیاتی "); fig("401"); append(" میگیرد و هیچ ردیفی نمیسازد.") }, style = Divan.type.micro, color = c.textMuted)
        }
        HqButton("ثبت با اثر انگشت", {
            val co = company ?: return@HqButton
            action.go(toasts) {
                env.api.registerIntake(IntakeSourceIn(co, kind, list, if (kind == "product") events else emptyList())) { a, t -> env.auth.stepUp(act, a, t) }
                env.cache.invalidate("intake")
                toasts.ok("منبع ثبت شد؛ رمزش را در ترمینال خودت بگذار.")
                onClose()
            }
        }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, size = BtnSize.LG, icon = DivanIcon.SEAL, enabled = valid, loading = action.busy)
    }
}
