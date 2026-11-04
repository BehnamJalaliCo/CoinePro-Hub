package com.coinepro.hq.ui.v31

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.AUTO_STATE_FA
import com.coinepro.hq.core.data.ruleLineFa
import com.coinepro.hq.core.data.lineRunStateFa
import com.coinepro.hq.core.data.lineRunStateTone
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.format.jDateTime
import com.coinepro.hq.core.net.GrowthAutomation
import com.coinepro.hq.core.net.Compiled
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.StepUp
import com.coinepro.hq.core.net.gated
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.Chevron
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.Expand
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.HqSwitch
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.ScrollRow
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.activity
import com.coinepro.hq.ui.itemMotion
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v29.CoName
import com.coinepro.hq.ui.v29.Para
import com.coinepro.hq.ui.v29.plain
import com.coinepro.hq.ui.v29.served

// Contract §31.7 ⟨1.13⟩ «اتوماسیون از یک جمله»: the owner writes one sentence; the hub turns it into a rule from a short list of allowed
// actions and says it back in plain words, with what it refuses. Nothing runs before the owner's seal. Running is code, never a model.

@Composable
fun AutomationsScreen(sentence0: String = "", compiled0: Compiled? = null) {
    val q = rememberQuery("automations", "automations", "growth", maxAgeMs = 20_000) { gated(HubFeature.GROWTH) { automations() } }
    val r = refresher(q)
    val has = served(HubFeature.GROWTH)
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item { PageHeader("اتوماسیون از یک جمله", eyebrow = "بنویس چه شود؛ منشی میفهمد، تو مُهر میکنی، کد انجام میدهد") }
        if (has) item(key = "new") { NewAutomation(sentence0, compiled0) }
        val list = q.data
        when {
            !has -> item { Empty("اتوماسیون با به‌روزرسانی بعدی هاب میاید", icon = DivanIcon.SETTINGS) }
            list == null && q.error != null -> item { ErrorBlock(q.error, { q.refresh() }) }
            list == null -> item { Skeleton(Modifier.fillMaxWidth().height(140.dp), radius = 16.dp) }
            list.isEmpty() -> item { Empty("هنوز اتوماسیونی نداری", icon = DivanIcon.SETTINGS, body = "مثلاً بنویس: «هر شنبه ساعت ۱۰ یک ریلز بساز».") }
            else -> {
                item(key = "title") { SectionTitle("اتوماسیون‌های من") }
                items(list, key = { it.ref }) { a -> Box(itemMotion()) { AutomationCard(a) } }
            }
        }
    }
}

/** The sentence, what the hub understood, what it refuses, and the seal. */
@Composable
fun NewAutomation(sentence0: String = "", compiled0: Compiled? = null) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val act = activity()
    val c = Divan.colors
    val ask = rememberAction()
    val seal = rememberAction()
    val companies = rememberCompanies().filter { it.kind != "holding" }
    var sentence by rememberSaveable { mutableStateOf(sentence0) }
    var company by rememberSaveable { mutableStateOf<String?>(null) }
    var compiled by remember { mutableStateOf(compiled0) }
    HqCard(Modifier.fillMaxWidth()) {
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("یک جمله بنویس", style = Divan.type.bodyStrong)
            HqTextField(sentence, { sentence = it; compiled = null }, "مثلاً: هر شنبه ساعت ۱۰ یک ریلز بساز و اگر بازده تبلیغ زیر یک و دو شد تبلیغ را متوقف کن", Modifier.fillMaxWidth(), singleLine = false, minLines = 3, maxLength = 500)
            if (companies.isNotEmpty()) ScrollRow {
                FilterChip("برای همه", company == null, { company = null })
                for (co in companies) FilterChip(co.nameFa ?: co.code, company == co.code, { company = co.code })
            }
            HqButton("بفهم", {
                ask.run { compiled = env.api.compileAutomation(sentence.trim(), company) }
            }, Modifier.fillMaxWidth(), variant = BtnVariant.SILVER, icon = DivanIcon.NEXT, enabled = sentence.trim().length >= 5, loading = ask.busy)
            compiled?.let { k ->
                if (k.previewFa.isNotBlank()) Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text("این‌طور فهمیدم", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
                    Para(k.previewFa, style = Divan.type.small, color = c.textPrimary)
                }
                if (k.refusedFa.isNotEmpty()) Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text("این را انجام نمیدهم", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.negative)
                    for (t in k.refusedFa) Para(t, style = Divan.type.caption, color = c.negative)
                }
                if (k.previewFa.isNotBlank()) {
                    Text("تا مُهر نکنی چیزی اجرا نمیشود.", style = Divan.type.micro, color = c.textMuted)
                    HqButton("مُهر و روشن کن", {
                        seal.run {
                            val made = env.api.newAutomation(k.rule, sentence.trim(), company)
                            val sign: StepUp = { a, t -> env.auth.stepUp(act, a, t) }
                            env.api.sealAutomation(made.ref, sign)
                            env.cache.invalidate("automations")
                            toasts.ok("مُهر شد؛ از همین حالا کار میکند.")
                            sentence = ""; compiled = null
                        }
                    }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, icon = DivanIcon.SEAL, loading = seal.busy)
                }
            }
        }
    }
}

/** One automation: its sentence, what it does, its state and runs; proposed ones wait for the seal, the others switch on and off. */
@Composable
fun AutomationCard(a: GrowthAutomation) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val act = activity()
    val c = Divan.colors
    val seal = rememberAction()
    val toggle = rememberAction()
    var open by rememberSaveable(a.ref) { mutableStateOf(false) }
    val st = AUTO_STATE_FA[a.state] ?: (a.state to Tone.SILVER)
    val detail = rememberQuery("automation:${a.ref}:$open", "automations", maxAgeMs = 20_000) { if (open) gated(HubFeature.GROWTH) { automation(a.ref) } else null }
    HqCard(Modifier.fillMaxWidth()) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            if (a.company != null) CoName(a.company, Modifier.weight(1f), height = 12.dp)
            else Text("برای همه‌ی شرکت‌ها", style = Divan.type.caption, color = c.textMuted, modifier = Modifier.weight(1f))
            Pill(st.first, st.second, dot = true)
        }
        Text(plain(a.sentenceFa), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, modifier = Modifier.padding(top = 8.dp))
        Para(a.previewFa?.takeIf { it.isNotBlank() } ?: ruleLineFa(a.rule), Modifier.padding(top = 6.dp), style = Divan.type.caption)
        Row(Modifier.padding(top = 8.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(plain("${a.runCount} اجرا" + (a.lastRunAt?.let { "، آخرین ${ago(it)}" } ?: "")), style = Divan.type.micro, color = c.textMuted, modifier = Modifier.weight(1f))
            when (a.state) {
                "proposed" -> HqButton("مُهر کن", {
                    seal.run {
                        val sign: StepUp = { x, t -> env.auth.stepUp(act, x, t) }
                        env.api.sealAutomation(a.ref, sign)
                        env.cache.invalidate("automations")
                        toasts.ok("مُهر شد؛ از همین حالا کار میکند.")
                    }
                }, variant = BtnVariant.PRIMARY, size = BtnSize.SM, icon = DivanIcon.SEAL, loading = seal.busy)
                else -> HqSwitch(a.state == "on", { on -> toggle.run { env.api.setAutomationState(a.ref, if (on) "on" else "off"); env.cache.invalidate("automations") } }, "روشن بودن اتوماسیون")
            }
        }
        Row(
            Modifier.fillMaxWidth().padding(top = 6.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            HqButton(if (open) "بستن اجراها" else "اجراها", { open = !open }, variant = BtnVariant.TEXT, size = BtnSize.SM)
            Chevron(open, tint = c.textMuted)
        }
        Expand(open) {
            Column(Modifier.padding(top = 6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                val runs = (detail.data ?: a).runList
                if (runs.isEmpty()) Text("هنوز اجرایی نبوده.", style = Divan.type.caption, color = c.textMuted)
                for (r in runs) Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text(plain(jDateTime(r.at)), style = Divan.type.micro, color = c.textMuted)
                    Pill(lineRunStateFa(r.state), lineRunStateTone(r.state), dot = true)
                    if (r.noteFa.isNotBlank()) Text(plain(r.noteFa), style = Divan.type.caption, color = c.textSecondary, modifier = Modifier.weight(1f), maxLines = 2)
                }
            }
        }
    }
}
