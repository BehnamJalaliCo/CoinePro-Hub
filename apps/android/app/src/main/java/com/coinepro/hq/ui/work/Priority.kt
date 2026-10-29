package com.coinepro.hq.ui.work

import androidx.compose.animation.AnimatedContent
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.togetherWith
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.selection.selectableGroup
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.coinepro.hq.core.format.PRIORITIES
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.priority
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Motion
import com.coinepro.hq.designsystem.Radius
import com.coinepro.hq.designsystem.LocalReducedMotion
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.motionShort
import com.coinepro.hq.designsystem.toneColors

/** The ink of a priority: the tone's colour, except "عادی", which stays in the text's own ink. */
@Composable
private fun inkOf(t: Tone): Color = if (t == Tone.NEUTRAL) Divan.colors.textPrimary else toneColors(t).second

/**
 * Choosing a priority: five labelled choices (the Persian name large, the code small and Latin under it), and the chosen one's meaning
 * in one line beneath, so the owner never has to know what "P2" is. Compact enough for a phone's width.
 */
@Composable
fun PriorityPicker(value: String, onChange: (String) -> Unit, modifier: Modifier = Modifier) {
    val c = Divan.colors
    val reduced = LocalReducedMotion.current
    Column(modifier, verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(
            Modifier.fillMaxWidth().clip(RoundedCornerShape(Radius.control)).background(c.tile).padding(4.dp).selectableGroup(),
            horizontalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            for (p in PRIORITIES) {
                val on = p.code == value
                val (soft, _) = toneColors(p.tone)
                val ink = inkOf(p.tone)
                val bg by animateColorAsState(if (on) (if (p.tone == Tone.NEUTRAL) c.raised else soft) else c.raised.copy(alpha = 0f), motionShort(), label = "prio-bg")
                val line by animateColorAsState(if (on) ink.copy(alpha = 0.55f) else Color.Transparent, motionShort(), label = "prio-line")
                Column(
                    Modifier
                        .weight(1f)
                        .heightIn(min = 52.dp)
                        .clip(RoundedCornerShape(Radius.small))
                        .background(bg)
                        .border(1.dp, line, RoundedCornerShape(Radius.small))
                        .selectable(on, role = Role.RadioButton, onClick = { onChange(p.code) })
                        .semantics { contentDescription = "${p.fa}، ${p.code}: ${p.line}" }
                        .padding(horizontal = 2.dp, vertical = 6.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.spacedBy(2.dp, Alignment.CenterVertically),
                ) {
                    Text(
                        p.fa, style = Divan.type.small.copy(fontSize = 12.5.sp, lineHeight = 18.sp, fontWeight = if (on) FontWeight.Bold else FontWeight.Medium),
                        color = if (on) ink else c.textSecondary, maxLines = 1, overflow = TextOverflow.Ellipsis, textAlign = TextAlign.Center,
                    )
                    Text(
                        buildAnnotatedString { fig(p.code) }, style = Divan.type.micro.copy(fontSize = 10.sp, lineHeight = 13.sp),
                        color = if (on) ink.copy(alpha = 0.8f) else c.textMuted, maxLines = 1,
                    )
                }
            }
        }
        val chosen = priority(value)
        // The meaning of the chosen one, under the control; it changes with a quick cross-fade.
        AnimatedContent(
            chosen, label = "prio-line",
            transitionSpec = { if (reduced) fadeIn(Motion.short(true)) togetherWith fadeOut(Motion.short(true)) else fadeIn(Motion.medium()) togetherWith fadeOut(Motion.exit()) },
        ) { p ->
            Row(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(Radius.small)).background(if (p.tone == Tone.NEUTRAL) c.tile else toneColors(p.tone).first).padding(horizontal = 10.dp, vertical = 8.dp),
                verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                DIcon(p.icon, Modifier.padding(top = 2.dp), size = 16.dp, tint = inkOf(p.tone))
                Text(
                    buildAnnotatedString {
                        withStyleBold { append(p.fa) }
                        append(" ("); fig(p.code); append("): ")
                        append(p.line)
                    },
                    style = Divan.type.caption, color = c.textPrimary,
                )
            }
        }
    }
}

private inline fun AnnotatedString.Builder.withStyleBold(block: AnnotatedString.Builder.() -> Unit) {
    val i = pushStyle(androidx.compose.ui.text.SpanStyle(fontWeight = FontWeight.Bold))
    block()
    pop(i)
}

/** A priority shown: the name, and the code small and Latin; a quiet pill for "عادی", the tone for the others. */
@Composable
fun PriorityTag(code: String?, modifier: Modifier = Modifier, compact: Boolean = false) {
    val p = priority(code)
    val c = Divan.colors
    val (bg, _) = toneColors(p.tone)
    val ink = if (p.tone == Tone.NEUTRAL) c.textSecondary else toneColors(p.tone).second
    Row(
        modifier.height(if (compact) 20.dp else 24.dp).clip(CircleShape).background(bg).padding(horizontal = if (compact) 8.dp else 10.dp)
            .semantics { contentDescription = "اولویت ${p.fa}" },
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(5.dp),
    ) {
        if (!compact) DIcon(p.icon, size = 13.dp, tint = ink)
        Text(
            buildAnnotatedString {
                append(p.fa)
                if (p.fa != p.code) { append(" "); fig(p.code, color = ink.copy(alpha = 0.7f)) }
            },
            style = Divan.type.caption.copy(fontSize = if (compact) 11.sp else 12.sp, fontWeight = FontWeight.SemiBold), color = ink, maxLines = 1,
        )
    }
}

/** A list row's small priority mark: the tone's dot for the urgent ones, nothing for the rest. */
@Composable
fun PriorityDot(code: String?, modifier: Modifier = Modifier) {
    val p = priority(code)
    if (p.tone == Tone.NEUTRAL || p.tone == Tone.SILVER) return
    Box(modifier.size(6.dp).clip(CircleShape).background(toneColors(p.tone).second))
}

/** "«هر وقت شد» (P4)" in a sentence, the code Latin. */
fun AnnotatedString.Builder.priorityText(code: String) {
    val p = priority(code)
    append("«${p.fa}»")
    if (p.fa != p.code) { append(" ("); fig(p.code); append(")") }
}
