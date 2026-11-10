package com.coinepro.hq.ui.playbook

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.genderFa
import com.coinepro.hq.core.data.narratorLineFa
import com.coinepro.hq.core.data.narratorStepFa
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.Narrator
import com.coinepro.hq.core.net.gated
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.designsystem.timesFig
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.outputs.SelectCheck
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v14.HqSheet

// Contract §48: a company's narrator, set once. The owner's order: «گوینده یک بار برای همیشه تنظیم شود». The voice and its style were
// words a model passed along each time; here they are the company's own, chosen once, and every piece of its content is spoken with them.
// One component for both places: under the company's row in a working group, and on the company's own page.

@Composable
internal fun rememberNarrator(company: String) =
    rememberQuery("narrator:$company", "narrator", maxAgeMs = 60_000) { gated(HubFeature.NARRATOR) { narrator(company) } }

/**
 * «گوینده‌ی محتوا» of one company in one row: the voice and its style, or that none is set; a tap opens the picker. [inset]: under a
 * member's row of a working group (as its standing word is). Nothing on a hub before §48.
 */
@Composable
fun NarratorRow(company: String, modifier: Modifier = Modifier, inset: Boolean = true, titled: Boolean = true) {
    val c = Divan.colors
    val q = rememberNarrator(company)
    val n = q.data ?: return
    var open by rememberSaveable(company) { mutableStateOf(false) }
    Row(
        modifier.fillMaxWidth().testTag("narrator-row").clickable(role = Role.Button, onClickLabel = "گوینده‌ی محتوا") { open = true }
            .padding(start = if (inset) 24.dp else 0.dp, bottom = if (inset) 8.dp else 0.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(1.dp)) {
            if (titled) Text("گوینده‌ی محتوا", style = Divan.type.caption, color = c.textSecondary)
            Text(timesFig(narratorLineFa(n)), style = if (titled) Divan.type.micro else Divan.type.small, color = if (n.set) c.goldInk else c.textMuted, maxLines = 1, overflow = TextOverflow.Ellipsis)
            // the only step of his there is here: the hub's own sign-in fell out
            narratorStepFa(n)?.let { Text(it, style = Divan.type.micro, color = c.warning) }
        }
        HqButton(if (n.set) "تغییر" else "تنظیم", { open = true }, variant = BtnVariant.TEXT, size = BtnSize.SM)
    }
    if (open) HqSheet({ open = false }, "گوینده‌ی محتوا", sub = "یک بار برای همیشه: هر ریلز و ویدیوی این شرکت با همین صدا و همین سبک گفته میشود.") {
        NarratorPicker(n) { out -> q.set(out); open = false }
    }
}

/** The same row as a card of the company's own page (nothing while the hub does not know narrators). */
@Composable
fun NarratorCard(company: String, modifier: Modifier = Modifier) {
    if (rememberNarrator(company).data == null) return
    HqCard(modifier.fillMaxWidth()) {
        SectionTitle("گوینده‌ی محتوا", note = "صدا و سبکی که ریلزها و ویدیوهای این شرکت با آن گفته میشود", icon = DivanIcon.MIC)
        NarratorRow(company, Modifier.padding(top = 8.dp), inset = false, titled = false)
    }
}

/**
 * The picker: the prebuilt voices (each with whose voice it is and its character), one chosen; how it should speak, in his words; «ثبت».
 * His tap, no passkey. A refusal of the hub is said under the field.
 */
@Composable
internal fun NarratorPicker(n: Narrator, onSaved: (Narrator) -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val save = rememberAction()
    var voice by rememberSaveable(n.company) { mutableStateOf(n.voice.takeIf { v -> n.voices.any { it.name == v } }) }
    var style by rememberSaveable(n.company) { mutableStateOf(n.styleFa) }
    var refused by rememberSaveable(n.company) { mutableStateOf<String?>(null) }
    narratorStepFa(n)?.let {
        Text(it, Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.softWarning).padding(12.dp), style = Divan.type.caption, color = c.textPrimary)
    }
    @Composable fun Label(t: String) = Text(t, style = Divan.type.caption.copy(fontWeight = androidx.compose.ui.text.font.FontWeight.SemiBold), color = c.textSecondary)
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Label("صدا")
        if (n.voices.isEmpty()) Text("فهرست صداها هنوز از هاب نرسیده است.", style = Divan.type.caption, color = c.textMuted)
        // the list keeps its own height and scrolls in it, so the style and «ثبت» stay at hand; the chosen voice comes first
        else Column(
            Modifier.fillMaxWidth().testTag("narrator-voices").clip(RoundedCornerShape(12.dp)).background(c.tile).heightIn(max = 304.dp)
                .verticalScroll(rememberScrollState()).selectableGroup().padding(horizontal = 12.dp),
        ) {
            n.voices.sortedByDescending { it.name == n.voice && n.set }.forEachIndexed { i, v ->
                if (i > 0) HorizontalDivider(color = c.lineDivider)
                Row(
                    Modifier.fillMaxWidth().selectable(voice == v.name, role = Role.RadioButton) { voice = v.name; refused = null }.padding(vertical = 10.dp),
                    verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    SelectCheck(voice == v.name)
                    Fig(v.name, style = Divan.type.figure, color = c.textPrimary)
                    Text(v.traitFa, style = Divan.type.small, color = c.textSecondary, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
                    Text(genderFa(v.gender), style = Divan.type.micro, color = c.textMuted)
                }
            }
        }
    }
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Label("سبک گفتن")
        HqTextField(style, { style = it; refused = null }, "مثلاً: آرام و مطمئن، مثل گوینده‌ی خبر", Modifier.fillMaxWidth(), singleLine = false, minLines = 2, maxLength = 500)
        refused?.let { Text(timesFig(it), style = Divan.type.caption, color = c.negative, modifier = Modifier.padding(horizontal = 4.dp)) }
    }
    HqButton("ثبت", {
        val v = voice ?: return@HqButton
        save.run(onError = { e: ApiException ->
            if (e.status == 422) { e.logged?.let { env.api.failures?.forget(it) }; refused = e.messageFa } else toasts.error(e.messageFa)
        }) {
            val out = env.api.setNarrator(n.company, v, style)
            env.cache.invalidate("narrator")
            toasts.ok("گوینده ثبت شد؛ از این به بعد همین صداست.")
            // the hub answers the narrator; the list of voices stays the one already here when it leaves it out
            onSaved(if (out.voices.isEmpty()) out.copy(voices = n.voices) else out)
        }
    }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, size = BtnSize.LG, icon = DivanIcon.SEAL, enabled = voice != null, loading = save.busy)
}
