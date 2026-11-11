package com.coinepro.hq.ui.look

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.FlowRowScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.layout.Layout
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.MemberLook
import com.coinepro.hq.core.data.RUN_DOTS
import com.coinepro.hq.core.data.RUN_FA
import com.coinepro.hq.core.data.deskDayFa
import com.coinepro.hq.core.data.lastSeven
import com.coinepro.hq.core.data.memberWordFa
import com.coinepro.hq.core.data.quietLine
import com.coinepro.hq.core.data.runDotsFa
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.format.jTime
import com.coinepro.hq.core.net.RoutineRun
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.Chevron
import com.coinepro.hq.designsystem.CollapsingHeader
import com.coinepro.hq.designsystem.CompanyMark
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Expand
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.Text
import com.coinepro.hq.designsystem.WorkBand
import com.coinepro.hq.designsystem.bidi
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.sep
import com.coinepro.hq.designsystem.smoothSize
import com.coinepro.hq.ui.v29.plain

// ⟨1.0.1⟩ Part C, the working group (C3.4), the pieces its pages are built from: a state as a shape and a word, a member company's
// head (its state, its last run, its next run, a silver work line only while something of it runs, and when it stands still its
// one-line reason with a quiet «راه بینداز»), a routine's last seven runs as dots (done, failed, skipped, in the queue: each its own
// shape), one grouped block of a member's settings with hairlines between its rows, a part that stays folded until he wants it
// («تعریف کارگروه»), and the page's header that folds to its title (M18). Nothing here is gold: the page's one gold is its decision
// bar («مُهر کارگروه»).
//
// How it is used:
// - `GroupHeader({ collapse.value }, eyebrow, title, state = { StateWord("on", "مُهر شده") }, facts = …, actions = { … })` above a page's list.
// - `MemberHead(company, name, on, look, runsKnown, next, onStart, starting) { quiet link }` at the top of a member's tile.
// - `SettingsBlock { SettingRow("انتشار خودکار", line, action = { … }) { what opens in place } … }` under it.
// - `RunDots(runs, label)` beside a routine's name; `whenAt(iso)` inside a line for «فردا 07:00».
// - `Fold("تعریف کارگروه", summary) { … }` for what is read only when wanted.

// ===================================================================================================== a state ==
/** A state as a shape and a word, never a colour alone: `on` a filled dot, `wait` a ring, `off` a short bar. */
@Composable
fun StateWord(kind: String, word: String, modifier: Modifier = Modifier) {
    val c = Divan.colors
    val ink = when (kind) { "on" -> c.silverInk; "wait" -> c.textPrimary; else -> c.textMuted }
    Row(modifier.testTag("state-word").semantics(mergeDescendants = true) {}, verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        Canvas(Modifier.size(10.dp)) {
            val r = size.minDimension / 2
            when (kind) {
                "on" -> drawCircle(ink, r * 0.8f)
                "wait" -> drawCircle(ink, r - 1.dp.toPx(), style = Stroke(1.5.dp.toPx()))
                else -> drawRoundRect(ink, Offset(0f, center.y - 1.dp.toPx()), Size(size.width, 2.dp.toPx()), CornerRadius(1.dp.toPx()))
            }
        }
        Text(word, style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = ink, maxLines = 1)
    }
}

/** «امروز 18:30», «فردا 07:00», «۲۵ آبان 09:00»: a moment to come, its hour a Latin figure. */
fun AnnotatedString.Builder.whenAt(iso: String) {
    append(deskDayFa(iso))
    append(" ")
    fig(jTime(iso))
}

// ============================================================================================ the last seven runs ==
/**
 * The last seven runs of a routine, oldest first, read left to right in both directions (time runs that way): done is a filled dot,
 * failed a red square, skipped a hollow dot, in the queue a ring; a routine with fewer runs keeps the faint places of the rest.
 */
@Composable
fun RunDots(runs: List<RoutineRun>, label: String, modifier: Modifier = Modifier) {
    val c = Divan.colors
    val last = remember(runs) { lastSeven(runs) }
    val dot = 8.dp
    val gap = 4.dp
    Canvas(
        modifier.size(width = dot * RUN_DOTS + gap * (RUN_DOTS - 1), height = dot).testTag("run-dots").semantics { contentDescription = runDotsFa(label, last) },
    ) {
        val d = dot.toPx()
        val step = d + gap.toPx()
        val pad = RUN_DOTS - last.size
        for (i in 0 until RUN_DOTS) {
            val centre = Offset(i * step + d / 2, d / 2)
            val run = last.getOrNull(i - pad)
            when (run?.state) {
                null -> drawCircle(c.lineDivider, d / 2 - 0.5.dp.toPx(), centre, style = Stroke(1.dp.toPx()))
                "done" -> drawCircle(c.positive, d / 2, centre)
                "failed" -> drawRoundRect(c.negative, Offset(i * step, 0f), Size(d, d), CornerRadius(2.dp.toPx()))
                "queued" -> drawCircle(c.silverInk, d / 2 - 0.75.dp.toPx(), centre, style = Stroke(1.5.dp.toPx()))
                else -> drawCircle(c.lineStrong, d / 2 - 0.75.dp.toPx(), centre, style = Stroke(1.5.dp.toPx()))
            }
        }
    }
}

// =================================================================================================== a member ==
/**
 * The head of a member's tile: its mark and name, its state as a shape and a word («فعال», «در کار», «ایستاده»), its last and next
 * run, its one-line reason with «راه بینداز» when it stands still, and its silver work line while something of it runs.
 * [look]: what its runs say (`memberLook`). [runsKnown]: the hub serves the runs (else nothing is said of them). [next]: when its
 * next routine runs. [onStart] null: it cannot be started from here. [action]: a quiet link at the end of its first line.
 */
@Composable
fun MemberHead(
    company: String, nameFa: String, on: Boolean, look: MemberLook, runsKnown: Boolean, next: String?,
    onStart: (() -> Unit)?, starting: Boolean, modifier: Modifier = Modifier, action: (@Composable () -> Unit)? = null,
) {
    val c = Divan.colors
    Column(modifier.fillMaxWidth().testTag("member-head"), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            CompanyMark(company, height = 18.dp, mono = true, ink = c.textSecondary)
            Text(nameFa, style = Divan.type.bodyStrong, color = c.textPrimary, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
            StateWord(if (on) "on" else "wait", memberWordFa(on, look.running))
            action?.invoke()
        }
        val last = look.last
        val runsLine = remember(last, runsKnown, next, on) {
            buildAnnotatedString {
                var any = false
                if (last != null) { append("آخرین نوبت ${ago(last.at)}، ${RUN_FA[last.state] ?: last.state}"); any = true }
                else if (runsKnown) { append("هنوز نوبتی نداشته"); any = true }
                if (on && next != null) { if (any) sep(); append("نوبت بعد "); whenAt(next) }
            }
        }
        if (runsLine.isNotEmpty()) Text(runsLine, style = Divan.type.caption, color = c.textSecondary, modifier = Modifier.testTag("member-runs"))
        // Why it stands still, in one line, and the one quiet way out of it.
        look.why?.let { why ->
            Row(Modifier.testTag("member-still"), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(plain(quietLine(why)), style = Divan.type.caption, color = c.textSecondary, modifier = Modifier.weight(1f))
                if (onStart != null) HqButton("راه بینداز", onStart, variant = BtnVariant.SECONDARY, size = BtnSize.SM, loading = starting)
            }
        }
        // The silver work line shows only while something of this company runs.
        if (on && look.running) WorkBand(true, c.silverInk, Modifier.fillMaxWidth(), height = 3.dp, word = null)
    }
}

// ================================================================================== a member's settings, one block ==
/**
 * One grouped block of settings: each child is a row, with a hairline between two rows that are there (a row the hub does not serve
 * draws nothing and leaves no line). Nothing at all when no row is there.
 */
@Composable
fun SettingsBlock(modifier: Modifier = Modifier, content: @Composable () -> Unit) {
    val c = Divan.colors
    val line = c.lineDivider
    val cuts = remember { ArrayList<Int>() }
    Layout(
        content,
        modifier.fillMaxWidth().testTag("member-settings").clip(RoundedCornerShape(12.dp)).background(c.tile).drawWithContent {
            drawContent()
            val inset = 12.dp.toPx()
            for (y in cuts) drawLine(line, Offset(inset, y.toFloat()), Offset(size.width - inset, y.toFloat()), 1.dp.toPx())
        },
    ) { measurables, constraints ->
        val rows = measurables.map { it.measure(constraints.copy(minHeight = 0)) }.filter { it.height > 0 }
        layout(constraints.maxWidth, rows.sumOf { it.height }) {
            cuts.clear()
            var y = 0
            for ((i, row) in rows.withIndex()) {
                if (i > 0) cuts += y
                row.placeRelative(0, y)
                y += row.height
            }
        }
    }
}

/**
 * A row of a settings block: what it is ([title]), where it stands ([line], in the secondary ink; never gold), a quiet [note] under
 * it, its quiet [action] at the end, and [under] it what a tap opens in place.
 */
@Composable
fun SettingRow(
    title: String, line: AnnotatedString, modifier: Modifier = Modifier, note: String? = null,
    action: @Composable RowScope.() -> Unit = {}, under: (@Composable ColumnScope.() -> Unit)? = null,
) {
    val c = Divan.colors
    Column(modifier.fillMaxWidth().smoothSize().padding(start = 12.dp, end = 6.dp, top = 8.dp, bottom = 8.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            Column(Modifier.weight(1f).padding(vertical = 2.dp), verticalArrangement = Arrangement.spacedBy(1.dp)) {
                Text(title, style = Divan.type.small, color = c.textPrimary)
                if (line.isNotEmpty()) Text(line, style = Divan.type.micro, color = c.textSecondary, maxLines = 2, overflow = TextOverflow.Ellipsis)
                if (note != null) Text(plain(note), style = Divan.type.micro, color = c.textMuted)
            }
            action()
        }
        under?.invoke(this)
    }
}

// ========================================================================================== what stays folded ==
/** A part of the page that is read only when wanted: its [title], a one-line [summary] beside it, and its content under a tap. */
@Composable
fun Fold(title: String, summary: AnnotatedString?, modifier: Modifier = Modifier, open0: Boolean = false, tag: String = "fold", content: @Composable ColumnScope.() -> Unit) {
    val c = Divan.colors
    var open by rememberSaveable(title) { mutableStateOf(open0) }
    Column(modifier.fillMaxWidth().testTag(tag).smoothSize().clip(RoundedCornerShape(16.dp)).background(c.card)) {
        Row(
            Modifier.fillMaxWidth().clickable(role = Role.Button, onClickLabel = if (open) "ببند" else "باز کن") { open = !open }.padding(horizontal = 16.dp, vertical = 14.dp),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text(title, style = Divan.type.bodyStrong, color = c.textPrimary, modifier = Modifier.weight(1f).semantics { heading() })
            if (summary != null) Text(summary, style = Divan.type.micro, color = c.textMuted, maxLines = 1)
            Chevron(open, size = 14.dp, tint = c.textMuted)
        }
        Expand(open) { Column(Modifier.fillMaxWidth().padding(start = 16.dp, end = 16.dp, bottom = 16.dp), verticalArrangement = Arrangement.spacedBy(14.dp), content = content) }
    }
}

// ================================================================================================== the header ==
/**
 * The head of a working group's page, above its list: where it is ([eyebrow]), its [title] and [state], a line of [facts] and its
 * quiet [actions]. As the page scrolls it folds to the title and the state on one line (M18; [fraction] from `rememberCollapse`).
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun GroupHeader(
    fraction: () -> Float, eyebrow: String?, title: String, modifier: Modifier = Modifier,
    state: (@Composable () -> Unit)? = null, facts: (@Composable () -> Unit)? = null, actions: (@Composable FlowRowScope.() -> Unit)? = null,
) {
    val c = Divan.colors
    CollapsingHeader(
        fraction, modifier.fillMaxWidth().background(c.page).testTag("group-header"),
        line = {
            Row(Modifier.fillMaxWidth().height(52.dp).padding(horizontal = 16.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Text(plain(title), style = Divan.type.bodyStrong, color = c.textPrimary, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
                state?.invoke()
            }
        },
        full = {
            Column(Modifier.fillMaxWidth().padding(start = 16.dp, end = 16.dp, top = 12.dp, bottom = 6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                if (eyebrow != null) Text(eyebrow, style = Divan.type.caption, color = c.textMuted)
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text(plain(title), style = Divan.type.h1, color = c.textPrimary, modifier = Modifier.weight(1f).semantics { heading() })
                    state?.invoke()
                }
                facts?.invoke()
                if (actions != null) FlowRow(Modifier.padding(top = 2.dp), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(6.dp), itemVerticalAlignment = Alignment.CenterVertically, content = actions)
            }
        },
    )
}

/** A quiet word that opens something («جلسه‌اش», «آمادگی»): silver ink, never a filled button. */
@Composable
fun QuietLink(label: String, onClick: () -> Unit, modifier: Modifier = Modifier) {
    val c = Divan.colors
    Text(
        label, modifier.clip(RoundedCornerShape(8.dp)).clickable(role = Role.Button, onClick = onClick).padding(horizontal = 8.dp, vertical = 6.dp),
        style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.silverInk, maxLines = 1,
    )
}

/** Facts in one line whose last part is a moment to come («نوبت بعد فردا 07:00»). */
fun factsWhen(parts: List<String?>, nextLabel: String?, nextIso: String?): AnnotatedString = buildAnnotatedString {
    var first = true
    for (p in parts) {
        if (p.isNullOrBlank()) continue
        if (!first) sep()
        bidi(p.trim())
        first = false
    }
    if (nextLabel != null && nextIso != null) {
        if (!first) sep()
        append(nextLabel)
        append(" ")
        whenAt(nextIso)
    }
}
