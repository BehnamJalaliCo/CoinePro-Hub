package com.coinepro.hq.ui.session

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.HorizontalDivider
import com.coinepro.hq.designsystem.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.faNum
import com.coinepro.hq.core.data.routineReady
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.jDateTime
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.SessionRoutine
import com.coinepro.hq.core.net.gated
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.HqSwitch
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.designsystem.timesFig
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.v29.served
import java.util.UUID

/*
 * Contract §50: a standing routine from one sentence («کارمند ۲۴ ساعته»). The owner's decision (2026-11-10): it is no hire and no card; he
 * says one sentence in the session and it is on, switched off with one tap. In the session's «جزئیات»: the routines asked for here, each
 * with when it runs, what it does, its next run and its switch; and «روال دائمی», a small sheet with the one sentence.
 */

/** The session's routines, newest first; hidden while it has none. [onChanged] reads the report again after a switch. */
@Composable
internal fun SessionRoutines(routines: List<SessionRoutine>, onChanged: () -> Unit) {
    if (routines.isEmpty()) return
    val c = Divan.colors
    HqCard(Modifier.fillMaxWidth().testTag("session-routines")) {
        SectionTitle("روال‌های دائمی", note = "${faNum(routines.size)} روال از این جلسه؛ هر کدام با یک ضربه خاموش میشود", icon = DivanIcon.TIME)
        Column(Modifier.padding(top = 6.dp)) {
            routines.forEachIndexed { i, r ->
                if (i > 0) HorizontalDivider(color = c.lineDivider)
                RoutineRow(r, onChanged)
            }
        }
    }
}

@Composable
private fun RoutineRow(r: SessionRoutine, onChanged: () -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val go = rememberAction()
    // what he just switched, shown at once (the report is read again behind it)
    var said by remember(r.ref, r.state) { mutableStateOf<Boolean?>(null) }
    val on = said ?: (r.state == "on")
    Row(Modifier.fillMaxWidth().padding(vertical = 10.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            // its time as prose, in the digits of the line under it («هر روز ساعت ۰۹:۰۰»)
            Text(r.whenFa.ifBlank { r.sentenceFa }, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
            val what = r.previewFa.ifBlank { r.sentenceFa.takeIf { r.whenFa.isNotBlank() }.orEmpty() }
            if (what.isNotBlank()) Text(timesFig(what), style = Divan.type.caption, color = c.textSecondary)
            // its next run while it is on (the hub names none for one that is off)
            r.nextAt?.takeIf { on }?.let { Text("نوبت بعد: ${jDateTime(it)}", style = Divan.type.micro, color = c.textMuted) }
            r.noteFa?.trim()?.ifBlank { null }?.let { Text(timesFig(it), style = Divan.type.micro, color = c.warning) }
        }
        // one the holder proposed still waits for the owner's seal: its switch comes with the seal
        if (r.state == "proposed") Pill("منتظر مُهر", Tone.WARN, dot = true)
        else HqSwitch(on, { want ->
            go.run {
                env.api.setAutomationState(r.ref, if (want) "on" else "off")
                said = want
                env.cache.invalidate("automations", "order-report")
                toasts.ok(if (want) "روشن شد؛ از نوبت بعد کار میکند." else "خاموش شد.")
                onChanged()
            }
        }, "روشن بودن این روال", enabled = !go.busy)
    }
}

/** «روال دائمی» among the session's actions, with what it is in one line. */
@Composable
internal fun RoutineAction(onClick: () -> Unit) {
    val c = Divan.colors
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        HqButton("روال دائمی", onClick, Modifier.fillMaxWidth(), icon = DivanIcon.TIME)
        Text(
            "کاری که باید هر روز یا هر هفته خودش انجام شود، با یک جمله. بی کارت و بی اثر انگشت؛ هر وقت خواستی خاموشش کن.",
            style = Divan.type.micro, color = c.textMuted, modifier = Modifier.padding(horizontal = 4.dp),
        )
    }
}

/**
 * The sheet's content: one sentence and «بساز». The hub compiles it and switches it on at once; a sentence that is no plain timed
 * routine comes back with the hub's own words under the field, and the text stays. One key per sentence, kept across a retry of the
 * same press. [sentence0] and [refused0] are for the screenshots.
 */
@Composable
internal fun RoutineForm(order: String, sentence0: String = "", refused0: String? = null, onMade: (SessionRoutine) -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val go = rememberAction()
    var sentence by rememberSaveable(order) { mutableStateOf(sentence0) }
    var refused by rememberSaveable(order) { mutableStateOf(refused0) }
    val key = remember(sentence) { UUID.randomUUID().toString() }
    val on = served(HubFeature.ROUTINES)
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            HqTextField(
                sentence, { sentence = it; refused = null }, "مثلاً: هر روز ساعت ۹ رتبه‌های سئوی سایت را ببین و خلاصه بده",
                Modifier.fillMaxWidth().testTag("routine-sentence"), singleLine = false, minLines = 3, maxLength = 1000,
            )
            refused?.let { Text(timesFig(it), style = Divan.type.caption, color = c.negative, modifier = Modifier.padding(horizontal = 4.dp)) }
        }
        Row(verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            DIcon(DivanIcon.INFO, size = 14.dp, tint = c.textMuted)
            Text(
                "بگو کِی و چه کاری: «هر روز ساعت ۹ …»، «هر جمعه …». همان لحظه روشن میشود و کارش در سقف پاکت ماه شرکت انجام میشود.",
                style = Divan.type.micro, color = c.textMuted, modifier = Modifier.weight(1f),
            )
        }
        // ⟨1.0.1⟩ C0.2: the sheet's one primary action, stuck to its bottom.
        com.coinepro.hq.designsystem.SheetBar {
            com.coinepro.hq.designsystem.DecisionBar(
                "بساز", {
                    go.run(onError = { e: ApiException ->
                        // a sentence the hub could not make a routine of: its own words under the field, the text kept
                        if (e.status == 422) { e.logged?.let { env.api.failures?.forget(it) }; refused = e.messageFa } else toasts.error(e.messageFa)
                    }) {
                        val made = env.api.gated(HubFeature.ROUTINES) { newRoutine(sentence, order, key) }
                        if (made == null) toasts.info("این نسخه‌ی هاب هنوز روال دائمی ندارد؛ بعد از به‌روز شدن هاب می‌آید.")
                        else {
                            env.cache.invalidate("automations", "order-report")
                            onMade(made)
                        }
                    }
                },
                context = "بی کارت و بی اثر انگشت؛ همین حالا روشن میشود.",
                icon = DivanIcon.TIME, enabled = on && routineReady(sentence), state = if (go.busy) com.coinepro.hq.designsystem.DecisionState.WORKING else com.coinepro.hq.designsystem.DecisionState.IDLE,
            )
        }
    }
}
