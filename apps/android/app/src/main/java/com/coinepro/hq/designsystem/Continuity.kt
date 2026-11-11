package com.coinepro.hq.designsystem

import androidx.compose.animation.AnimatedVisibilityScope
import androidx.compose.animation.BoundsTransform
import androidx.compose.animation.ExperimentalSharedTransitionApi
import androidx.compose.animation.SharedTransitionLayout
import androidx.compose.animation.SharedTransitionScope
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.spring
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.compositionLocalOf
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Rect

// ⟨1.0.1⟩ Part C, M14 «پیوستگی» (C0.3): a tapped card grows into the screen it opens (a session, an output, a working group, a
// company's treasury), 320 ms, a spring without a bounce. Built on Compose's shared-element transition:
//
// - The shell wraps its pages in [ContinuityHost] and every page of the navigation in [ContinuityPage] (Shell.kt does both).
// - The card: `Modifier.continuity("session/$ref")`. The page it opens puts the SAME key on its header: `Modifier.continuity("session/$ref")`.
//   The key is the page's route, so a card and its page always agree. One element per key on a screen.
// - Outside the shell (a screenshot, a preview, a sheet), or when the phone removes animations, the modifier does nothing: the
//   page simply opens.

@OptIn(ExperimentalSharedTransitionApi::class)
private val LocalContinuityScope = compositionLocalOf<SharedTransitionScope?> { null }
private val LocalContinuityPage = compositionLocalOf<AnimatedVisibilityScope?> { null }

/** Around the pages of a navigation host: cards and the headers they become are matched inside it. */
@OptIn(ExperimentalSharedTransitionApi::class)
@Composable
fun ContinuityHost(modifier: Modifier = Modifier, content: @Composable () -> Unit) {
    if (LocalReducedMotion.current) { androidx.compose.foundation.layout.Box(modifier) { content() }; return }
    SharedTransitionLayout(modifier) {
        CompositionLocalProvider(LocalContinuityScope provides this) { content() }
    }
}

/** Around one page of the navigation host ([scope]: the page's own enter/exit scope, the receiver of a `composable { }` block). */
@Composable
fun ContinuityPage(scope: AnimatedVisibilityScope, content: @Composable () -> Unit) {
    CompositionLocalProvider(LocalContinuityPage provides scope) { content() }
}

/** 320 ms and no bounce: the bounds of the card become the bounds of the header it opens into. */
@OptIn(ExperimentalSharedTransitionApi::class)
private val Settle = BoundsTransform { _: Rect, _: Rect -> spring(dampingRatio = Spring.DampingRatioNoBouncy, stiffness = 380f) }

/**
 * M14: this element and the one with the same [key] on the page that opens are one thing; while the page changes, its bounds travel
 * from the one to the other and the two cross-fade. [key] null, no host around it, or animations removed: nothing.
 */
@OptIn(ExperimentalSharedTransitionApi::class)
@Composable
fun Modifier.continuity(key: String?): Modifier {
    val host = LocalContinuityScope.current
    val page = LocalContinuityPage.current
    if (key == null || host == null || page == null) return this
    return with(host) {
        this@continuity.sharedBounds(
            rememberSharedContentState("m14:$key"), page,
            enter = fadeIn(tween(Grammar.CROSSFADE, easing = Motion.Standard)),
            exit = fadeOut(tween(Grammar.CROSSFADE, easing = Motion.Standard)),
            boundsTransform = Settle,
        )
    }
}
