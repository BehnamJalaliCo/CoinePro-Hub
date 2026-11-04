package com.coinepro.hq.ui.v31

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.AD_ACTION_FA
import com.coinepro.hq.core.data.adFigures
import com.coinepro.hq.core.data.adPlatformFa
import com.coinepro.hq.core.data.roasText
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.jDate
import com.coinepro.hq.core.format.tokens
import com.coinepro.hq.core.net.AdAccount
import com.coinepro.hq.core.net.AdCampaign
import com.coinepro.hq.core.net.AdRule
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.StepUp
import com.coinepro.hq.core.net.gated
import com.coinepro.hq.core.net.idText
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.ChartLine
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.HqSwitch
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.LinesChart
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.activity
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v29.Para
import com.coinepro.hq.ui.v29.plain
import com.coinepro.hq.ui.v29.served
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

// Contract §31.6 ⟨1.13⟩ the company's «تبلیغات» tab: its ad accounts, each campaign's spend and return over 30 days, and the rules that
// stop a campaign by themselves. A rule only ever pauses (reversible) or tells; it never raises a budget. «ادامه» for a paused campaign
// and a higher daily cap are signed with the passkey.

@Composable
fun CompanyAds(code: String) {
    val ads = rememberQuery("ads:$code", "ads", "growth", maxAgeMs = 30_000) { gated(HubFeature.GROWTH) { ads(code) } }
    val rules = rememberQuery("ad-rules:$code", "ads", "growth", maxAgeMs = 30_000) { gated(HubFeature.GROWTH) { adRules(code) } }
    val has = served(HubFeature.GROWTH)
    var editing by rememberSaveable { mutableStateOf<String?>(null) }
    val a = ads.data
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        when {
            !has -> Empty("تبلیغات با به‌روزرسانی بعدی هاب میاید", icon = DivanIcon.TREASURY)
            a == null && ads.error != null -> ErrorBlock(ads.error, { ads.refresh() })
            a == null -> Skeleton(Modifier.fillMaxWidth().height(180.dp), radius = 16.dp)
            else -> {
                AccountsCard(a.accounts)
                CampaignsCard(a.campaigns)
                RulesCard(code, rules.data.orEmpty(), a.campaigns) { editing = it }
            }
        }
    }
    editing?.let { id ->
        val rule = rules.data.orEmpty().firstOrNull { it.id.idText == id }
        com.coinepro.hq.ui.v14.HqSheet({ editing = null }, if (id == "new") "قاعده‌ی تازه" else "ویرایش قاعده", sub = "قاعده فقط متوقف میکند یا خبر میدهد.") {
            RuleForm(code, rule, ads.data?.campaigns.orEmpty()) { editing = null }
        }
    }
}

@Composable
fun AccountsCard(list: List<AdAccount>) {
    val c = Divan.colors
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("حساب‌های تبلیغاتی")
        if (list.isEmpty()) Text("هنوز حسابی وصل نیست؛ از «اتصال‌ها» وصلش کن.", style = Divan.type.caption, color = c.textMuted, modifier = Modifier.padding(top = 8.dp))
        else Column(Modifier.padding(top = 8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            for (x in list) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(adPlatformFa(x.platform), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), modifier = Modifier.weight(1f))
                Text(x.accountId, style = Divan.type.figureSmall, color = c.textMuted)
                Pill(if (x.state == "connected") "وصل" else "وصل نیست", if (x.state == "connected") Tone.POS else Tone.WARN, dot = true)
            }
        }
    }
}

/** Each campaign with 30 days of spend and return, the ROAS chart, and for a paused one why, and «ادامه». */
@Composable
fun CampaignsCard(list: List<AdCampaign>) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val act = activity()
    val c = Divan.colors
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("کمپین‌ها", note = "۳۰ روز گذشته؛ بازده یعنی فروش به خرج")
        if (list.isEmpty()) Text("کمپینی نیست.", style = Divan.type.caption, color = c.textMuted, modifier = Modifier.padding(top = 8.dp))
        else Column(Modifier.padding(top = 8.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            val days = list.flatMap { it.days.map { d -> d.day } }.distinct().sorted()
            if (days.size >= 2) LinesChart(
                days.map { jDate(it) },
                list.mapIndexed { i, k -> ChartLine(k.id, k.titleFa ?: k.id, c.chart[i % c.chart.size], days.map { d -> k.days.firstOrNull { it.day == d }?.roas }) },
                fmt = { roasText(it) }, label = "بازده‌ی روزانه‌ی کمپین‌ها", height = 180.dp,
            )
            list.forEachIndexed { i, k ->
                if (i > 0) HorizontalDivider(color = c.lineDivider)
                val f = adFigures(k)
                val resume = rememberAction()
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text(plain(k.titleFa ?: k.id), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), modifier = Modifier.weight(1f))
                        Pill(if (k.state == "on") "روشن" else "متوقف", if (k.state == "on") Tone.POS else Tone.WARN, dot = true)
                    }
                    Text(plain("${adPlatformFa(k.platform)}؛ خرج ${tokens(f.spend.toLong())}، فروش ${tokens(f.revenue.toLong())}، بازده ${roasText(f.roas)}"), style = Divan.type.caption, color = c.textSecondary)
                    Text(plain("${f.clicks} کلیک، ${f.conversions} خرید"), style = Divan.type.micro, color = c.textMuted)
                    if (k.state == "paused") {
                        k.pausedReasonFa?.let { Para(it, style = Divan.type.caption, color = c.warning) }
                        HqButton("ادامه", {
                            resume.run {
                                val sign: StepUp = { a, t -> env.auth.stepUp(act, a, t) }
                                env.api.resumeAd(k.platform, k.id, sign)
                                env.cache.invalidate("ads", "campaign-calendar")
                                toasts.ok("کمپین دوباره روشن شد.")
                            }
                        }, variant = BtnVariant.PRIMARY, size = BtnSize.SM, icon = DivanIcon.SEAL, loading = resume.busy)
                    }
                }
            }
        }
    }
}

@Composable
fun RulesCard(code: String, rules: List<AdRule>, campaigns: List<AdCampaign>, onEdit: (String) -> Unit) {
    val env = LocalEnv.current
    val c = Divan.colors
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("قاعده‌های توقف", note = "اگر خرج بالا رفت و بازده نیامد، خودش متوقف میکند") {
            HqButton("قاعده‌ی تازه", { onEdit("new") }, variant = BtnVariant.SILVER, size = BtnSize.SM, icon = DivanIcon.ADD)
        }
        if (rules.isEmpty()) Text("قاعده‌ای نیست؛ تبلیغ بی‌مراقب میماند.", style = Divan.type.caption, color = c.warning, modifier = Modifier.padding(top = 8.dp))
        else Column(Modifier.padding(top = 8.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            rules.forEachIndexed { i, r ->
                if (i > 0) HorizontalDivider(color = c.lineDivider)
                val toggle = rememberAction()
                val remove = rememberAction()
                val scope = if (r.scope == "account") "کل حساب" else campaigns.firstOrNull { it.id == r.scope }?.titleFa ?: r.scope
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text(plain(scope), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), modifier = Modifier.weight(1f))
                        Pill(AD_ACTION_FA[r.action] ?: r.action, if (r.action == "pause") Tone.WARN else Tone.LAPIS)
                        HqSwitch(r.state == "on", { on ->
                            toggle.run { env.api.saveAdRule(code, r.id.idText, buildJsonObject { put("state", if (on) "on" else "off") }); env.cache.invalidate("ads") }
                        }, "روشن بودن قاعده")
                    }
                    Text(plain("سقف خرج روزانه ${tokens(r.dailyCap.toLong())}؛ در ${r.windowDays} روز اگر بازده کمتر از ${roasText(r.minRoas)} بود (بعد از خرج ${tokens(r.minSpendBeforeJudging.toLong())})"), style = Divan.type.caption, color = c.textSecondary)
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        HqButton("ویرایش", { onEdit(r.id.idText) }, variant = BtnVariant.GHOST, size = BtnSize.SM, icon = DivanIcon.EDIT)
                        HqButton("حذف", { remove.run { env.api.deleteAdRule(code, r.id.idText); env.cache.invalidate("ads") } }, variant = BtnVariant.GHOST, size = BtnSize.SM, loading = remove.busy)
                    }
                }
            }
        }
    }
}

/** A rule made or changed. A higher daily cap than the rule had is signed (🔏 `ads.cap`). */
@Composable
fun RuleForm(code: String, rule: AdRule?, campaigns: List<AdCampaign>, onDone: () -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val act = activity()
    val action = rememberAction()
    val c = Divan.colors
    var scope by rememberSaveable(rule?.id?.idText) { mutableStateOf(rule?.scope ?: "account") }
    var cap by rememberSaveable(rule?.id?.idText) { mutableStateOf(rule?.dailyCap?.toLong()?.toString().orEmpty()) }
    var window by rememberSaveable(rule?.id?.idText) { mutableStateOf((rule?.windowDays ?: 7).toString()) }
    var roas by rememberSaveable(rule?.id?.idText) { mutableStateOf(rule?.minRoas?.toString() ?: "1.2") }
    var minSpend by rememberSaveable(rule?.id?.idText) { mutableStateOf(rule?.minSpendBeforeJudging?.toLong()?.toString().orEmpty()) }
    var act2 by rememberSaveable(rule?.id?.idText) { mutableStateOf(rule?.action ?: "pause") }
    val capN = cap.toLongOrNull()
    val valid = capN != null && capN > 0 && window.toIntOrNull() != null && roas.toDoubleOrNull() != null && minSpend.toLongOrNull() != null
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("برای", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            FilterChip("کل حساب", scope == "account", { scope = "account" })
            for (k in campaigns) FilterChip(k.titleFa ?: k.id, scope == k.id, { scope = k.id })
        }
        for ((label, v, set) in listOf(
            Triple("سقف خرج روزانه", cap, { x: String -> cap = x.filter { it.isDigit() } }),
            Triple("چند روز را بسنجد", window, { x: String -> window = x.filter { it.isDigit() } }),
            Triple("کمترین بازده", roas, { x: String -> roas = x.filter { it.isDigit() || it == '.' } }),
            Triple("حداقل خرج پیش از قضاوت", minSpend, { x: String -> minSpend = x.filter { it.isDigit() } }),
        )) {
            Text(label, style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
            HqTextField(v, set, label, Modifier.fillMaxWidth(), figure = true, maxLength = 12)
        }
        Text("اگر رسید", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            for ((k, l) in AD_ACTION_FA) FilterChip(l, act2 == k, { act2 = k })
        }
        if (rule != null) Text("بالا بردن سقف با مُهر توست.", style = Divan.type.micro, color = c.textMuted)
        HqButton(if (rule == null) "بساز" else "ذخیره", {
            action.run {
                val body = buildJsonObject {
                    put("scope", scope); put("daily_cap", capN ?: 0L); put("window_days", window.toInt()); put("min_roas", roas.toDouble())
                    put("min_spend_before_judging", minSpend.toLong()); put("action", act2); put("state", rule?.state ?: "on")
                }
                val raised = rule != null && (capN ?: 0L) > rule.dailyCap
                val sign: StepUp = { a, t -> env.auth.stepUp(act, a, t) }
                env.api.saveAdRule(code, rule?.id?.idText, body, if (raised) sign else null)
                env.cache.invalidate("ads")
                toasts.ok("قاعده ذخیره شد.")
                onDone()
            }
        }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, icon = DivanIcon.SEAL, enabled = valid, loading = action.busy)
    }
}
