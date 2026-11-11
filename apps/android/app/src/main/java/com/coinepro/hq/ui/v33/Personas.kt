package com.coinepro.hq.ui.v33

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import com.coinepro.hq.designsystem.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.PERSONA_SOURCE_FA
import com.coinepro.hq.core.data.personaOf
import com.coinepro.hq.core.data.scoreTone
import com.coinepro.hq.core.data.wouldActCount
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.jDateTime
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.PersonaDraft
import com.coinepro.hq.core.net.PersonaIn
import com.coinepro.hq.core.net.PersonaSuggestion
import com.coinepro.hq.core.net.PersonaTest
import com.coinepro.hq.core.net.SalesPersona
import com.coinepro.hq.core.net.gated
import com.coinepro.hq.designsystem.BarTone
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.MeterBar
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.StatRow
import com.coinepro.hq.designsystem.StatTile
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v29.Para
import com.coinepro.hq.ui.v29.plain
import com.coinepro.hq.ui.v29.served

// Contract §33.9 ⟨1.15⟩ «مخاطب‌ها»: the company's personas (its data; the owner edits them), up to four suggested from the company's
// knowledge base (saved only when kept), and the message test: one text read by every persona, each with a score, whether they would
// act, their objection and a fix.

/** The company's «مخاطب‌ها» tab. [test0] and [suggest0] open it with a result already there (the screenshots). */
@Composable
fun CompanyPersonas(code: String, test0: PersonaTest? = null, text0: String = "", suggest0: PersonaSuggestion? = null) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val has = served(HubFeature.JOURNEY)
    val q = rememberQuery("personas:$code", "personas", maxAgeMs = 60_000) { gated(HubFeature.JOURNEY) { personas(code) } }
    var editing by rememberSaveable { mutableStateOf<String?>(null) }
    var removing by rememberSaveable { mutableStateOf<String?>(null) }
    var suggestion by remember(code) { mutableStateOf(suggest0) }
    val suggest = rememberAction()
    val del = rememberAction()
    val list = q.data
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        if (!has) {
            Empty("مخاطب‌ها با به‌روزرسانی بعدی هاب میایند", icon = DivanIcon.OWNER)
            return@Column
        }
        MessageTest(code, list.orEmpty(), test0, text0)
        SectionTitle("مخاطب‌های شرکت", note = "چه کسی، چه دردی دارد و چه ایرادی میگیرد") {
            HqButton("مخاطب تازه", { editing = "new" }, variant = BtnVariant.SILVER, size = BtnSize.SM, icon = DivanIcon.ADD)
        }
        when {
            list == null && q.error != null -> ErrorBlock(q.error, { q.refresh() })
            list == null -> Skeleton(Modifier.fillMaxWidth().height(200.dp), radius = 16.dp)
            list.isEmpty() -> Empty("هنوز مخاطبی تعریف نشده", icon = DivanIcon.OWNER, body = "یکی بنویس، یا بگذار از دانش شرکت پیشنهاد بیاید.")
            else -> for (p in list) androidx.compose.runtime.key(p.id) { PersonaCard(p, { editing = p.id }, { removing = p.id }) }
        }
        HqButton("از دانش شرکت پیشنهاد بگیر", {
            suggest.run { suggestion = env.api.suggestPersonas(code) }
        }, Modifier.fillMaxWidth(), variant = BtnVariant.SECONDARY, icon = DivanIcon.KNOWLEDGE, loading = suggest.busy)
        suggestion?.let { s -> SuggestionCard(code, s) { kept -> suggestion = s.copy(personas = s.personas - kept) } }
    }
    editing?.let { id ->
        val p = list?.firstOrNull { it.id == id }
        com.coinepro.hq.ui.v14.HqSheet({ editing = null }, if (p == null) "مخاطب تازه" else "تغییر مخاطب", sub = p?.nameFa) {
            PersonaForm(code, p) { editing = null }
        }
    }
    removing?.let { id ->
        val p = list?.firstOrNull { it.id == id }
        com.coinepro.hq.ui.v14.HqSheet({ removing = null }, "کنار گذاشتن مخاطب", sub = p?.nameFa) {
            Para("از فهرست و از آزمون پیام بیرون میرود؛ سابقه‌اش میماند.")
            HqButton("کنار بگذار", {
                del.run {
                    env.api.deletePersona(id)
                    env.cache.invalidate("personas")
                    toasts.ok("کنار گذاشته شد.")
                    removing = null
                }
            }, Modifier.fillMaxWidth(), variant = BtnVariant.DANGER, loading = del.busy)
        }
    }
}

@Composable
fun PersonaCard(p: SalesPersona, onEdit: () -> Unit, onRemove: () -> Unit) {
    val c = Divan.colors
    HqCard(Modifier.fillMaxWidth()) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(plain(p.nameFa), Modifier.weight(1f), style = Divan.type.bodyStrong)
            Pill(PERSONA_SOURCE_FA[p.source] ?: "از طرف تو", if (p.source == "kb_suggested") Tone.LAPIS else Tone.SILVER)
        }
        Para(p.summaryFa, Modifier.padding(top = 6.dp))
        PersonaLists(p.painsFa, p.objectionsFa, p.channelFa)
        Row(Modifier.padding(top = 10.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            HqButton("تغییر", onEdit, variant = BtnVariant.GHOST, size = BtnSize.SM, icon = DivanIcon.EDIT)
            HqButton("کنار بگذار", onRemove, variant = BtnVariant.GHOST, size = BtnSize.SM, icon = DivanIcon.CLOSE)
        }
    }
}

@Composable
private fun PersonaLists(pains: List<String>, objections: List<String>, channel: String) {
    val c = Divan.colors
    Column(Modifier.padding(top = 8.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        if (pains.isNotEmpty()) Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text("دردها", style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = c.textMuted)
            for (x in pains) Para("• $x", style = Divan.type.caption, color = c.textSecondary)
        }
        if (objections.isNotEmpty()) Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text("ایرادها", style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = c.textMuted)
            for (x in objections) Para("• $x", style = Divan.type.caption, color = c.textSecondary)
        }
        if (channel.isNotBlank()) Text(plain("کجا پیدایش میکنی: $channel"), style = Divan.type.caption, color = c.textMuted)
    }
}

/** Up to four suggestions from the knowledge base, each kept (saved as `kb_suggested`) or left. */
@Composable
private fun SuggestionCard(code: String, s: PersonaSuggestion, onKept: (PersonaDraft) -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val keep = rememberAction()
    HqCard(Modifier.fillMaxWidth(), color = c.softGold.copy(alpha = 0.5f)) {
        SectionTitle("پیشنهاد دانش شرکت", note = "تا نگه نداری ذخیره نمیشود", icon = DivanIcon.KNOWLEDGE)
        if (s.basisFa.isNotBlank()) Para(s.basisFa, Modifier.padding(top = 6.dp), style = Divan.type.caption, color = c.textMuted)
        if (s.personas.isEmpty()) Text("پیشنهاد دیگری نماند.", Modifier.padding(top = 8.dp), style = Divan.type.caption, color = c.textMuted)
        Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            for (d in s.personas) Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.card).padding(12.dp)) {
                Text(plain(d.nameFa), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold))
                Para(d.summaryFa, Modifier.padding(top = 4.dp), style = Divan.type.caption)
                PersonaLists(d.painsFa, d.objectionsFa, d.channelFa)
                Box(Modifier.padding(top = 8.dp)) {
                    HqButton("نگه دار", {
                        keep.run {
                            env.api.addPersona(code, PersonaIn(d.nameFa, d.summaryFa, d.painsFa, d.objectionsFa, d.channelFa, source = "kb_suggested"))
                            env.cache.invalidate("personas")
                            toasts.ok("«${d.nameFa}» اضافه شد.")
                            onKept(d)
                        }
                    }, variant = BtnVariant.PRIMARY, size = BtnSize.SM, icon = DivanIcon.ADD, loading = keep.busy)
                }
            }
        }
    }
}

/** A persona written or changed by the owner: one line per pain and per objection. */
@Composable
fun PersonaForm(code: String, p: SalesPersona?, onDone: () -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val save = rememberAction()
    val key = p?.id ?: "new"
    var name by rememberSaveable(key) { mutableStateOf(p?.nameFa.orEmpty()) }
    var summary by rememberSaveable(key) { mutableStateOf(p?.summaryFa.orEmpty()) }
    var pains by rememberSaveable(key) { mutableStateOf(p?.painsFa.orEmpty().joinToString("\n")) }
    var objections by rememberSaveable(key) { mutableStateOf(p?.objectionsFa.orEmpty().joinToString("\n")) }
    var channel by rememberSaveable(key) { mutableStateOf(p?.channelFa.orEmpty()) }
    fun lines(s: String) = s.lines().map { it.trim().trimStart('•', '-', ' ') }.filter { it.isNotEmpty() }
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text("نام", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
        HqTextField(name, { name = it }, "مثلاً معامله‌گر تازه‌کار", Modifier.fillMaxWidth(), maxLength = 120)
        Text("در یک جمله", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
        HqTextField(summary, { summary = it }, "", Modifier.fillMaxWidth(), singleLine = false, minLines = 2, maxLength = 600)
        Text("دردها (هر خط یکی)", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
        HqTextField(pains, { pains = it }, "", Modifier.fillMaxWidth(), singleLine = false, minLines = 3, maxLength = 2000)
        Text("ایرادها (هر خط یکی)", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
        HqTextField(objections, { objections = it }, "", Modifier.fillMaxWidth(), singleLine = false, minLines = 3, maxLength = 2000)
        Text("کجا پیدایش میکنی", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
        HqTextField(channel, { channel = it }, "مثلاً کانال تلگرام و اینستاگرام", Modifier.fillMaxWidth(), maxLength = 200)
        HqButton(if (p == null) "اضافه کن" else "ذخیره", {
            save.run {
                val body = PersonaIn(name.trim(), summary.trim(), lines(pains), lines(objections), channel.trim(), source = if (p == null) "owner" else null)
                if (p == null) env.api.addPersona(code, body) else env.api.editPersona(p.id, body)
                env.cache.invalidate("personas")
                toasts.ok("ذخیره شد.")
                onDone()
            }
        }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, enabled = name.isNotBlank() && summary.isNotBlank(), loading = save.busy)
    }
}

/** «آزمون پیام»: one text, read by every persona at once. */
@Composable
fun MessageTest(code: String, personas: List<SalesPersona>, test0: PersonaTest? = null, text0: String = "") {
    val env = LocalEnv.current
    val c = Divan.colors
    val run = rememberAction()
    var text by rememberSaveable(code) { mutableStateOf(text0.ifEmpty { test0?.text.orEmpty() }) }
    var result by remember(code) { mutableStateOf(test0) }
    HqCard(Modifier.fillMaxWidth(), tahrir = true) {
        SectionTitle("آزمون پیام", note = "یک متن بنویس؛ هر مخاطب میگوید چه حسی دارد و چه چیزی را عوض کنی", icon = DivanIcon.SEND)
        HqTextField(text, { text = it }, "متن پست، پیام یا تبلیغ", Modifier.padding(top = 10.dp).fillMaxWidth(), singleLine = false, minLines = 3, maxLength = 4000)
        HqButton("بسنج", {
            run.run { result = env.api.testMessage(code, text.trim()) }
        }, Modifier.padding(top = 10.dp).fillMaxWidth(), variant = BtnVariant.PRIMARY, icon = DivanIcon.SCOPE,
            enabled = text.isNotBlank() && personas.isNotEmpty(), loading = run.busy)
        if (personas.isEmpty()) Text("اول دست‌کم یک مخاطب تعریف کن.", Modifier.padding(top = 6.dp), style = Divan.type.caption, color = c.textMuted)
        result?.let { r ->
            Column(Modifier.padding(top = 14.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                StatRow {
                    StatTile("میانگین", "${r.average}", Modifier.weight(1f), sub = "از 100", tone = scoreTone(r.average))
                    StatTile("کمترین", "${r.lowest}", Modifier.weight(1f), sub = "از 100", tone = scoreTone(r.lowest))
                    StatTile("اقدام میکنند", "${wouldActCount(r.results)}", Modifier.weight(1f), sub = "از ${r.results.size} مخاطب")
                }
                for (s in r.results.sortedBy { it.score }) {
                    val name = s.nameFa.ifBlank { personaOf(personas, s)?.nameFa.orEmpty() }
                    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Text(plain(name), Modifier.weight(1f), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold))
                            if (s.wouldAct) Pill("اقدام میکند", Tone.POS) else Pill("اقدام نمیکند", Tone.SILVER)
                            Fig("${s.score}", style = Divan.type.figure, color = c.textPrimary)
                        }
                        MeterBar(s.score.toDouble(), tone = when (scoreTone(s.score)) { Tone.POS -> BarTone.POS; Tone.WARN -> BarTone.WARN; else -> BarTone.NEG }, height = 5.dp)
                        s.objectionFa?.takeIf { it.isNotBlank() }?.let { Para("ایراد: $it", style = Divan.type.caption, color = c.textSecondary) }
                        s.fixFa?.takeIf { it.isNotBlank() }?.let { Para("پیشنهاد: $it", style = Divan.type.caption, color = c.silverInk) }
                    }
                }
                Text(plain("سنجیده شد ${jDateTime(r.at)}"), style = Divan.type.micro, color = c.textMuted)
            }
        }
    }
}
