package com.coinepro.hq.ui.look

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.Stable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.selected
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.coinepro.hq.core.data.COMMAND_FA
import com.coinepro.hq.core.data.COMMAND_PLACEHOLDER_FA
import com.coinepro.hq.core.data.COMMAND_TEMPLATES
import com.coinepro.hq.core.data.CommandCompany
import com.coinepro.hq.core.data.CommandTemplate
import com.coinepro.hq.core.data.PACE_FA
import com.coinepro.hq.core.data.ROUTINE_PLACEHOLDER_FA
import com.coinepro.hq.core.data.ROUTINE_TEMPLATE_FA
import com.coinepro.hq.core.data.commandReady
import com.coinepro.hq.core.data.namesFa
import com.coinepro.hq.core.data.routineReady
import com.coinepro.hq.core.data.templateText
import com.coinepro.hq.core.format.jDateTime
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.Company
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.SessionRoutine
import com.coinepro.hq.core.net.commandOrder
import com.coinepro.hq.core.net.gated
import com.coinepro.hq.designsystem.CompanyMark
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.DecisionBar
import com.coinepro.hq.designsystem.DecisionState
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.DrawnMark
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.Monogram
import com.coinepro.hq.designsystem.QuietAction
import com.coinepro.hq.designsystem.ScrollRow
import com.coinepro.hq.designsystem.SpringSheet
import com.coinepro.hq.designsystem.Text
import com.coinepro.hq.designsystem.facts
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.designsystem.pressScale
import com.coinepro.hq.designsystem.rememberHaptics
import com.coinepro.hq.designsystem.timesFig
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.session.PaceAsk
import com.coinepro.hq.ui.v29.served
import kotlinx.coroutines.launch
import java.util.UUID

// ⟨1.0.1⟩ Part C, «نوار فرمان همه‌جا» (C2.1): one round button on every top-level screen (the HQ mark inside a thin gold ring, never a
// filled gold), and the one spring sheet it opens, «چه میخواهی؟»: the words, the template chips that only fill the starting text, the
// companies as their own marks (any number; none picked = the holding decides), the pace, and «باز کن» in the decision bar. The path
// is the one path: the existing new-order call, and the owner lands in the session it opens. «کارمند ۲۴ ساعته» turns the same sheet
// into the routine form: one sentence, one company, «بساز» (`POST /routines`; no card, no fingerprint).
//
// How it is used: the shell provides [LocalCommand]; any screen opens the sheet with `LocalCommand.current(null)` (or with words
// already in it: `LocalCommand.current(CommandOpen(text = "…"))`). The home's entry is [CommandRow].

/** What the command sheet opens on: words already written, and the order form or the routine form. */
data class CommandOpen(val text: String = "", val routine: Boolean = false)

/** Opens the command sheet from anywhere under the shell (a screenshot or a preview has none: it does nothing). */
val LocalCommand = staticCompositionLocalOf<(CommandOpen?) -> Unit> { {} }

// ------------------------------------------------------------------------------------------------ the button --
/** The HQ mark inside a thin gold ring: the command, never a filled gold. */
@Composable
fun CommandMark(size: Dp = 56.dp, modifier: Modifier = Modifier) {
    val c = Divan.colors
    Box(modifier.size(size).clip(CircleShape).background(c.raised).border(1.5.dp, c.goldInk, CircleShape), contentAlignment = Alignment.Center) {
        Monogram(size * 0.46f)
    }
}

/** The round command button: the same corner on every top-level screen, above the navigation. */
@Composable
fun CommandButton(onClick: () -> Unit, modifier: Modifier = Modifier) {
    val src = remember { MutableInteractionSource() }
    Box(
        modifier.pressScale(src, 0.94f).clip(CircleShape)
            .clickable(src, androidx.compose.material3.ripple(), role = Role.Button, onClickLabel = COMMAND_FA, onClick = onClick)
            .semantics { contentDescription = COMMAND_FA }.testTag("command-button"),
    ) { CommandMark() }
}

/** The home's command entry: one row that opens the sheet (the old inline «فرمان تازه» card). */
@Composable
fun CommandRow(modifier: Modifier = Modifier) {
    val c = Divan.colors
    val open = LocalCommand.current
    Row(
        modifier.fillMaxWidth().heightIn(min = 56.dp).clip(RoundedCornerShape(16.dp)).background(c.card)
            .clickable(role = Role.Button, onClickLabel = COMMAND_FA) { open(null) }.padding(horizontal = 14.dp, vertical = 10.dp).testTag("command-row"),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        CommandMark(36.dp)
        Column(Modifier.weight(1f)) {
            Text(COMMAND_FA, style = Divan.type.bodyStrong, color = c.textPrimary)
            Text("بنویس؛ برایش یک جلسه باز میشود", style = Divan.type.caption, color = c.textMuted, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
        DIcon(DivanIcon.NEXT, size = 18.dp, tint = c.textMuted)
    }
}

// ------------------------------------------------------------------------------------------------- the sheet --
/** What the sheet shows: the order form, the routine form, or the routine's quiet confirmation. */
enum class CommandMode { ORDER, ROUTINE, MADE }

/** The sheet's own state, kept apart so a screenshot can show each of its states. */
@Stable
class CommandState(open: CommandOpen = CommandOpen(), mode0: CommandMode? = null) {
    var mode by mutableStateOf(mode0 ?: if (open.routine) CommandMode.ROUTINE else CommandMode.ORDER)
    var text by mutableStateOf(open.text)
    var sentence by mutableStateOf("")
    var picked by mutableStateOf<List<String>>(emptyList())
    var one by mutableStateOf<String?>(null)
    var pace by mutableStateOf<String?>(null)
    var template by mutableStateOf<CommandTemplate?>(null)
    var busy by mutableStateOf(false)
    var error by mutableStateOf<String?>(null)
    var made by mutableStateOf<SessionRoutine?>(null)
    /** One key per press of «بساز», kept across a retry of the same press. */
    var routineKey: String = ""
}

/** «چه میخواهی؟»: the order form, the routine form, and the routine's quiet confirmation, in the one sheet. */
@Composable
fun CommandSheet(onDismiss: () -> Unit, open: CommandOpen = CommandOpen()) {
    val env = LocalEnv.current
    val nav = LocalNav.current
    val haptics = rememberHaptics()
    val scope = rememberCoroutineScope()
    val companies = rememberCompanies().filter { it.kind != "holding" }
    val routineOn = served(HubFeature.ROUTINES)
    val s = remember { CommandState(open) }

    fun nameOf(code: String) = companies.firstOrNull { it.code == code }?.nameFa ?: code
    fun send() {
        val pace = s.pace ?: return
        if (!commandReady(s.text) || s.busy) return
        s.busy = true
        s.error = null
        scope.launch {
            try {
                val o = env.api.commandOrder(s.text, s.picked.map { CommandCompany(it, nameOf(it)) }, pace)
                haptics.seal()
                env.cache.invalidate("orders", "work", "sessions", "office", "home", "decisions", "inbox")
                // The owner is in the session it opened.
                onDismiss()
                nav.go("session/${o.ref}")
            } catch (e: ApiException) {
                // The words stay; the hub's own sentence stands above the bar.
                haptics.error()
                s.error = e.messageFa
            } finally {
                s.busy = false
            }
        }
    }
    fun build() {
        if (!routineReady(s.sentence) || s.busy) return
        s.busy = true
        s.error = null
        if (s.routineKey.isEmpty()) s.routineKey = UUID.randomUUID().toString()
        scope.launch {
            try {
                val made = env.api.gated(HubFeature.ROUTINES) { newRoutine(s.sentence, null, s.routineKey, s.one) }
                s.routineKey = ""
                if (made == null) s.mode = CommandMode.ORDER // a hub before the routine route: the form goes back to the order
                else {
                    haptics.seal()
                    env.cache.invalidate("automations", "orders", "office")
                    s.made = made
                    s.mode = CommandMode.MADE
                }
            } catch (e: ApiException) {
                // A sentence the hub could not make a routine of (422): its own words above the bar, the text kept.
                if (e.status == 422) e.logged?.let { env.api.failures?.forget(it) }
                haptics.error()
                s.error = e.messageFa
            } finally {
                s.busy = false
            }
        }
    }

    SpringSheet(
        onDismiss,
        title = if (s.mode == CommandMode.ORDER) COMMAND_FA else ROUTINE_TEMPLATE_FA,
        sub = if (s.mode == CommandMode.ROUTINE) "یک جمله بنویس که چه کاری، هر چند وقت یک بار." else null,
        bar = { CommandDecisionBar(s, companies, onSend = ::send, onBuild = ::build, onDone = onDismiss) },
    ) {
        CommandFields(s, companies, routineOn, autofocus = true)
    }
}

/** The sheet's decision bar: «باز کن», «بساز» with «برگرد», or «باشه». */
@Composable
fun CommandDecisionBar(s: CommandState, companies: List<Company>, onSend: () -> Unit, onBuild: () -> Unit, onDone: () -> Unit) {
    fun nameOf(code: String) = companies.firstOrNull { it.code == code }?.nameFa ?: code
    when (s.mode) {
        CommandMode.ORDER -> {
            val ready = commandReady(s.text)
            val pace = s.pace
            DecisionBar(
                "باز کن", onSend, error = s.error,
                context = when {
                    !ready -> null
                    pace == null -> "اول «${PACE_FA["step"]}» یا «${PACE_FA["auto"]}» را انتخاب کن؛ بعد جلسه باز میشود."
                    else -> "${if (s.picked.isEmpty()) "هلدینگ خودش میسپارد" else namesFa(s.picked.map(::nameOf))} · ${PACE_FA[pace]}"
                },
                enabled = ready && pace != null, state = if (s.busy) DecisionState.WORKING else DecisionState.IDLE,
            )
        }
        CommandMode.ROUTINE -> DecisionBar(
            "بساز", onBuild, error = s.error,
            context = s.one?.let { "برای ${nameOf(it)}، بی کارت و بی اثر انگشت." } ?: "بی کارت و بی اثر انگشت؛ همین حالا روشن میشود.",
            enabled = routineReady(s.sentence), state = if (s.busy) DecisionState.WORKING else DecisionState.IDLE,
            quiet = listOf(QuietAction("برگرد") { s.mode = CommandMode.ORDER; s.error = null }),
        )
        CommandMode.MADE -> DecisionBar("باشه", onDone)
    }
}

/** The sheet's fields for its mode. */
@Composable
fun CommandFields(s: CommandState, companies: List<Company>, routineOn: Boolean, autofocus: Boolean = false) {
    val c = Divan.colors
    val haptics = rememberHaptics()
    val focus = remember { FocusRequester() }
    fun nameOf(code: String) = companies.firstOrNull { it.code == code }?.nameFa ?: code
    if (autofocus) LaunchedEffect(s.mode) { if (s.mode != CommandMode.MADE) runCatching { focus.requestFocus() } }
    when (s.mode) {
        CommandMode.ORDER -> {
            HqTextField(
                s.text, { s.text = it; s.error = null }, COMMAND_PLACEHOLDER_FA,
                Modifier.fillMaxWidth().focusRequester(focus).testTag("command-text"), singleLine = false, minLines = 3, maxLength = 10_000,
            )
            // A template only fills the starting text: the path is the same one path.
            ScrollRow {
                for (t in COMMAND_TEMPLATES) FilterChip(t.label, false, {
                    haptics.tick()
                    s.template = t
                    s.text = templateText(t, s.picked.map(::nameOf))
                    s.error = null
                })
                if (routineOn) FilterChip(ROUTINE_TEMPLATE_FA, false, {
                    haptics.tick()
                    s.mode = CommandMode.ROUTINE
                    s.error = null
                    if (s.picked.size == 1) s.one = s.picked.single()
                })
            }
            CompanyMarks("برای کدام شرکت؟", companies, s.picked) { code ->
                haptics.tick()
                val before = s.picked
                val next = if (code in before) before - code else before + code
                // The template's own words follow the companies while the owner has not written past them.
                s.template?.let { t -> if (s.text == templateText(t, before.map(::nameOf))) s.text = templateText(t, next.map(::nameOf)) }
                s.picked = next
            }
            PaceAsk(s.pace, { haptics.tick(); s.pace = it })
        }
        CommandMode.ROUTINE -> {
            HqTextField(
                s.sentence, { s.sentence = it; s.error = null }, ROUTINE_PLACEHOLDER_FA,
                Modifier.fillMaxWidth().focusRequester(focus).testTag("command-sentence"), singleLine = false, minLines = 3, maxLength = 1000,
            )
            CompanyMarks("برای کدام شرکت؟", companies, listOfNotNull(s.one)) { code -> haptics.tick(); s.one = if (s.one == code) null else code }
        }
        CommandMode.MADE -> s.made?.let { r ->
            Row(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(c.card).padding(14.dp).testTag("routine-made"),
                horizontalArrangement = Arrangement.spacedBy(12.dp), verticalAlignment = Alignment.Top,
            ) {
                Box(Modifier.padding(top = 2.dp).size(32.dp).clip(CircleShape).background(c.softPositive), contentAlignment = Alignment.Center) { DrawnMark(true, c.positive, size = 16.dp) }
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text(r.sentenceFa, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                    Text(
                        remember(r) { facts(r.whenFa, r.nextAt?.let { "نوبت بعد: ${jDateTime(it)}" }) },
                        style = Divan.type.caption, color = c.textSecondary,
                    )
                    if (r.previewFa.isNotBlank()) Text(timesFig(r.previewFa), style = Divan.type.caption, color = c.textMuted)
                }
            }
        }
    }
}

/** The companies as their own marks, in the hub's order: one tile each (any number), a row that scrolls sideways. A silver ring = picked. */
@Composable
private fun CompanyMarks(label: String, companies: List<Company>, picked: List<String>, onToggle: (String) -> Unit) {
    if (companies.isEmpty()) return
    val c = Divan.colors
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(label, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, modifier = Modifier.semantics { heading() })
        ScrollRow(spacing = 6.dp) {
            for (co in companies) {
                val on = co.code in picked
                val name = co.nameFa ?: co.code
                val tile = RoundedCornerShape(16.dp)
                Column(
                    Modifier.width(76.dp).clip(RoundedCornerShape(14.dp))
                        .clickable(role = Role.Checkbox, onClickLabel = name) { onToggle(co.code) }
                        .semantics(mergeDescendants = true) { selected = on; contentDescription = name }
                        .padding(horizontal = 4.dp, vertical = 6.dp),
                    horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    Box(
                        Modifier.size(52.dp).clip(tile).background(if (on) c.raised else c.tile).border(if (on) 2.dp else 1.dp, if (on) c.silverInk else c.lineDivider, tile),
                        contentAlignment = Alignment.Center,
                    ) { CompanyMark(co.code, height = 24.dp, label = name) }
                    Text(
                        name, style = Divan.type.micro.copy(fontSize = 11.sp, lineHeight = 16.sp, fontWeight = if (on) FontWeight.SemiBold else FontWeight.Normal),
                        color = if (on) c.textPrimary else c.textSecondary, textAlign = TextAlign.Center, maxLines = 2, minLines = 2, overflow = TextOverflow.Ellipsis,
                    )
                }
            }
        }
    }
}
