package com.coinepro.hq.designsystem

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.compositionLocalOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp

// ⟨1.0.1⟩ Part C, M15 «برگه‌ی فنری» (C0.3): the ONE sheet of the app. A handle; as tall as its content (never a full-height sheet with
// an empty half); it follows the finger, settles with the platform's spring, and a drag down closes it; its primary action is stuck
// to its bottom ([bar]: a [DecisionBar]). When the phone removes animations it is simply there.
//
// How it is used:
// - `SpringSheet(onDismiss = { open = false }, title = "چه میخواهی؟", bar = { DecisionBar("باز کن", …) }) { fields… }`.
//   The content scrolls inside when it is taller than the screen; the bar never scrolls away, and it rides above the keyboard.
// - `HqSheet` (ui/v14/Bits.kt, the sheet most screens already open) is this sheet: give it `bar = { … }` to stick its action down.
// - A screenshot or a preview draws the sheet's inside with [SpringSheetBody] on the overlay surface, aligned to the bottom.
// - A form that lives in its own composable (its fields and its state together) sticks its action down from inside:
//   `SheetBar { DecisionBar("بساز", …) }` as the last thing it draws. In a sheet the bar is stuck to the sheet's bottom; drawn on
//   its own (a screenshot of the form, a page) it simply stands where it was written.
// - While any sheet is open [LocalSheetsOpen] counts it: the round command button hides itself.

/** How many spring sheets are open now (the shell hides the command button while this is above zero). */
class SheetsOpen {
    var count by mutableIntStateOf(0)
}

val LocalSheetsOpen = compositionLocalOf<SheetsOpen?> { null }

@Composable
fun SpringSheet(
    onDismiss: () -> Unit,
    title: String? = null,
    sub: String? = null,
    /** The sheet's decision bar, stuck to its bottom. */
    bar: (@Composable () -> Unit)? = null,
    content: @Composable ColumnScope.() -> Unit,
) {
    SpringSheetFrame(onDismiss) { SpringSheetBody(title, sub, bar, content = content) }
}

/**
 * The sheet itself, for a sheet that lays out its own inside (its own scrolling, a composer, a player): the handle, the height by
 * content, the finger and the spring are the same. Everything else uses [SpringSheet].
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SpringSheetFrame(onDismiss: () -> Unit, content: @Composable ColumnScope.() -> Unit) {
    val c = Divan.colors
    val open = LocalSheetsOpen.current
    DisposableEffect(open) {
        open?.let { it.count++ }
        onDispose { open?.let { it.count = (it.count - 1).coerceAtLeast(0) } }
    }
    ModalBottomSheet(
        onDismissRequest = onDismiss,
        // No half-open stop: the sheet is as tall as what it holds.
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true),
        containerColor = c.overlay,
        contentColor = c.textPrimary,
        shape = RoundedCornerShape(topStart = 20.dp, topEnd = 20.dp),
        dragHandle = { SheetHandle() },
        // A sheet opened from inside another sheet has its own bar: a form in it never reaches the outer one's.
        content = { androidx.compose.runtime.CompositionLocalProvider(LocalSheetBar provides null) { content() } },
    )
}

/** Where a form inside a sheet puts the sheet's decision bar ([SheetBar]). */
class SheetBarSlot {
    var content by mutableStateOf<(@Composable () -> Unit)?>(null)
}

val LocalSheetBar = compositionLocalOf<SheetBarSlot?> { null }

/** The decision bar of the sheet this is drawn in, said from inside its content (see the head of this file). */
@Composable
fun SheetBar(content: @Composable () -> Unit) {
    val slot = LocalSheetBar.current
    if (slot == null) { content(); return }
    val latest by androidx.compose.runtime.rememberUpdatedState(content)
    DisposableEffect(slot) {
        slot.content = { latest() }
        onDispose { slot.content = null }
    }
}

/** The handle the sheet is dragged by. */
@Composable
fun SheetHandle() {
    Box(Modifier.fillMaxWidth().padding(top = 10.dp, bottom = 8.dp), contentAlignment = Alignment.Center) {
        Box(Modifier.width(36.dp).height(4.dp).clip(CircleShape).background(Divan.colors.lineStrong))
    }
}

/** The inside of a [SpringSheet]: the title, the content (it scrolls when it is taller than the room it has) and the bar under it.
 *  [scroll] false: laid out whole (a preview inside a page that scrolls itself). */
@Composable
fun SpringSheetBody(title: String?, sub: String?, bar: (@Composable () -> Unit)?, modifier: Modifier = Modifier, scroll: Boolean = true, content: @Composable ColumnScope.() -> Unit) {
    val c = Divan.colors
    val slot = remember { SheetBarSlot() }
    val stuck = bar ?: slot.content
    Column(modifier.fillMaxWidth().imePadding()) {
        Column(
            (if (scroll) Modifier.weight(1f, fill = false).fillMaxWidth().verticalScroll(rememberScrollState()) else Modifier.fillMaxWidth())
                .padding(horizontal = 16.dp).padding(bottom = if (stuck != null) 16.dp else 24.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp),
        ) {
            if (title != null) Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                RichText(title, Modifier.semantics { heading() }, style = Divan.type.h2, color = c.textPrimary)
                if (sub != null) Text(sub, style = Divan.type.caption, color = c.textMuted)
            }
            // A form of the content may stick its own action to the sheet's bottom (SheetBar).
            androidx.compose.runtime.CompositionLocalProvider(LocalSheetBar provides if (bar == null) slot else null) { content() }
        }
        stuck?.invoke()
    }
}

/** The sheet as it stands over its page, without its window: for a screenshot or a preview. The page behind is dimmed, and the sheet
 *  is as tall as what it holds. [fill]: it stands at the bottom of the whole screen and scrolls inside when it is taller (a
 *  screenshot of a sheet alone); otherwise it is laid out whole (a preview inside a page that scrolls itself). */
@Composable
fun SpringSheetPreview(
    title: String?, sub: String? = null, bar: (@Composable () -> Unit)? = null, fill: Boolean = false,
    content: @Composable ColumnScope.() -> Unit,
) {
    val c = Divan.colors
    Box((if (fill) Modifier.fillMaxSize() else Modifier.fillMaxWidth()).background(c.scrim).padding(top = 24.dp), contentAlignment = Alignment.BottomCenter) {
        Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(topStart = 20.dp, topEnd = 20.dp)).background(c.overlay)) {
            SheetHandle()
            SpringSheetBody(title, sub, bar, scroll = fill, content = content)
        }
    }
}
