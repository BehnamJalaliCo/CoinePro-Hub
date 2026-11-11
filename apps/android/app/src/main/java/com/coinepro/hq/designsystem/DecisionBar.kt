package com.coinepro.hq.designsystem

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.runtime.setValue
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.coinepro.hq.designsystem.generated.DivanIcon
import kotlinx.coroutines.delay

// ⟨1.0.1⟩ Part C, «نوار تصمیم» (C0.2): what waits for the owner is answered where he sees it, with one tap. ONE shared bar, stuck to
// the bottom: one optional line of what is decided, ONE primary action (the screen's only full gold), up to two quiet actions beside
// it. While the act is on its way the primary shows a small arc and is disabled; when it is done a tick draws itself (M8), and the
// bar leaves ([onLeft]).
//
// How it is used:
// - In a sheet: `HqSheet(…, bar = { DecisionBar("ثبت", onPrimary = …, state = …) }) { … }` (or [SpringSheet]). The sheet sticks it to its
//   bottom, above the system inset and the keyboard.
// - On a page: `DecisionPage(bar = { DecisionBar("تأیید و انتشار", …, quiet = listOf(QuietAction("اصلاح") { … }), place = DecisionPlace.PAGE) }) { page }`.
//   The page gives the bar its own room, so nothing hides behind it.
// - The action it carries is REMOVED from the bottom of the scroll (never two), and no other filled gold stays on that screen.
// - Haptics are the caller's: `haptics.seal()` when the approval was sent, `haptics.error()` when it failed.

enum class DecisionState { IDLE, WORKING, DONE }

/** `SHEET`: the bottom of a sheet (a hairline above it). `PAGE`: a raised bar at the bottom of a page, above the navigation. */
enum class DecisionPlace { SHEET, PAGE }

/** A quiet action beside the primary («اصلاح», «بعداً», «برگرد»): outlined, never filled. [danger]: a quiet red outline. */
class QuietAction(val label: String, val danger: Boolean = false, val enabled: Boolean = true, val icon: DivanIcon? = null, val onClick: () -> Unit)

private const val DONE_MS = 900L

@Composable
fun DecisionBar(
    primary: String,
    onPrimary: () -> Unit,
    modifier: Modifier = Modifier,
    /** One sentence: what is decided here. */
    context: String? = null,
    /** The hub's own words when the act failed; shown in place of [context]. */
    error: String? = null,
    /** At most two. */
    quiet: List<QuietAction> = emptyList(),
    state: DecisionState = DecisionState.IDLE,
    enabled: Boolean = true,
    icon: DivanIcon? = null,
    doneLabel: String = "انجام شد",
    /** Called once the «done» tick has been seen: the caller takes the bar (or its sheet) away. */
    onLeft: (() -> Unit)? = null,
    place: DecisionPlace = DecisionPlace.SHEET,
) {
    val c = Divan.colors
    val left by rememberUpdatedState(onLeft)
    LaunchedEffect(state) {
        if (state == DecisionState.DONE) { delay(DONE_MS); left?.invoke() }
    }
    val body: @Composable () -> Unit = {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            when {
                error != null -> Text(error, style = Divan.type.caption, color = c.negative, modifier = Modifier.semantics { liveRegion = LiveRegionMode.Polite })
                context != null -> Text(context, style = Divan.type.caption, color = c.textSecondary)
            }
            if (state == DecisionState.DONE) {
                Row(
                    Modifier.fillMaxWidth().height(BtnSize.LG.height).settle().semantics(mergeDescendants = true) { liveRegion = LiveRegionMode.Polite },
                    verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp, Alignment.CenterHorizontally),
                ) {
                    DrawnMark(true, c.positive, size = 18.dp)
                    Text(doneLabel, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                }
            } else {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    HqButton(
                        primary, onPrimary, Modifier.weight(1f), variant = BtnVariant.PRIMARY, size = BtnSize.LG, icon = icon,
                        loading = state == DecisionState.WORKING, enabled = enabled,
                    )
                    for (q in quiet.take(2)) HqButton(
                        q.label, q.onClick, variant = if (q.danger) BtnVariant.DANGER else BtnVariant.SECONDARY, size = BtnSize.LG, icon = q.icon,
                        enabled = q.enabled && state != DecisionState.WORKING,
                    )
                }
            }
        }
    }
    when (place) {
        DecisionPlace.SHEET -> Column(modifier.fillMaxWidth().background(c.overlay)) {
            HorizontalDivider(color = c.lineDivider)
            Box(Modifier.padding(start = 16.dp, end = 16.dp, top = 12.dp, bottom = 12.dp)) { body() }
        }
        DecisionPlace.PAGE -> {
            val shape = RoundedCornerShape(Radius.card)
            Box(
                modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp)
                    .clip(shape).background(c.raised).border(1.dp, c.lineDivider, shape).padding(12.dp),
            ) { body() }
        }
    }
}

/** How tall the decision bar of the page on screen is (the shell lifts the round command button above it). */
class PageDock {
    var barHeight by androidx.compose.runtime.mutableIntStateOf(0)
}

val LocalPageDock = androidx.compose.runtime.compositionLocalOf<PageDock?> { null }

/** The room the round command button takes at the bottom of the page on screen (the shell says so on a top-level page): a page
 *  that scrolls adds it under its last row, so nothing stays hidden behind the button. Zero where there is no button. */
val LocalCommandRoom = androidx.compose.runtime.compositionLocalOf { 0.dp }

/** A page with its decision bar: the page takes the room above, [bar] sits at the bottom (above the navigation), and nothing of the
 *  page hides behind it. [bar] null: just the page. */
@Composable
fun DecisionPage(bar: (@Composable () -> Unit)?, modifier: Modifier = Modifier, content: @Composable () -> Unit) {
    val dock = LocalPageDock.current
    androidx.compose.runtime.DisposableEffect(dock, bar == null) { onDispose { dock?.barHeight = 0 } }
    Column(modifier) {
        Box(Modifier.weight(1f)) { content() }
        if (bar != null) Box(Modifier.onSizeChanged { dock?.barHeight = it.height }) { bar() }
    }
}
