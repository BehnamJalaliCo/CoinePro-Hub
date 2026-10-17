package com.coinepro.hq.designsystem

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.LocalContentColor
import androidx.compose.material3.LocalTextStyle
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.ReadOnlyComposable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontVariation
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.LineHeightStyle
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.sp
import com.coinepro.hq.R
import com.coinepro.hq.core.ThemeMode
import com.coinepro.hq.designsystem.generated.DayPalette
import com.coinepro.hq.designsystem.generated.DivanPalette
import com.coinepro.hq.designsystem.generated.DivanType
import com.coinepro.hq.designsystem.generated.NightPalette

// One typeface, IRANYekanX (variable, weight axis). The FaNum cut draws ASCII digits as Persian and is the
// text face; the Latin cut keeps figures Latin (money, tokens, codes, model names) with tabular digits.
private val WEIGHTS = listOf(400, 500, 600, 700)

private fun family(res: Int) = FontFamily(
    WEIGHTS.map { w -> Font(res, FontWeight(w), variationSettings = FontVariation.Settings(FontVariation.weight(w))) },
)

val TextFace: FontFamily = family(R.font.iranyekanx_fanum)
val FigureFace: FontFamily = family(R.font.iranyekanx_latin)

@Immutable
class DivanTypography(
    val display: TextStyle,
    val h1: TextStyle,
    val h2: TextStyle,
    val h3: TextStyle,
    val body: TextStyle,
    val bodyStrong: TextStyle,
    val small: TextStyle,
    val caption: TextStyle,
    val micro: TextStyle,
    /** Figures: Latin digits, tabular. */
    val figureL: TextStyle,
    val figureM: TextStyle,
    val figure: TextStyle,
    val figureSmall: TextStyle,
)

private val trimmed = LineHeightStyle(LineHeightStyle.Alignment.Center, LineHeightStyle.Trim.None)

private fun text(size: Int, line: Int, weight: Int = 400) =
    TextStyle(fontFamily = TextFace, fontSize = size.sp, lineHeight = line.sp, fontWeight = FontWeight(weight), lineHeightStyle = trimmed)

private fun figure(size: Int, line: Int, weight: Int = 600) =
    TextStyle(fontFamily = FigureFace, fontSize = size.sp, lineHeight = line.sp, fontWeight = FontWeight(weight), fontFeatureSettings = "tnum", lineHeightStyle = trimmed)

val DivanTypeScale = DivanTypography(
    display = text(DivanType.DISPLAY_SIZE, DivanType.DISPLAY_LINE, 700),
    h1 = text(DivanType.H1_SIZE, DivanType.H1_LINE, 600),
    h2 = text(DivanType.H2_SIZE, DivanType.H2_LINE, 600),
    h3 = text(DivanType.H3_SIZE, DivanType.H3_LINE, 600),
    body = text(DivanType.BODY_SIZE, DivanType.BODY_LINE),
    bodyStrong = text(DivanType.BODY_SIZE, DivanType.BODY_LINE, 600),
    small = text(13, 22),
    caption = text(DivanType.CAPTION_SIZE, DivanType.CAPTION_LINE),
    micro = text(DivanType.MICRO_SIZE, DivanType.MICRO_LINE),
    figureL = figure(DivanType.FIGUREL_SIZE, 34),
    figureM = figure(DivanType.FIGUREM_SIZE, 26),
    figure = figure(14, 20),
    figureSmall = figure(11, 16, 500),
)

private val LocalPalette = staticCompositionLocalOf { NightPalette }
private val LocalNight = staticCompositionLocalOf { true }

/** Access to the Divan theme from any composable. */
object Divan {
    val colors: DivanPalette
        @Composable @ReadOnlyComposable get() = LocalPalette.current
    val type: DivanTypography
        @Composable @ReadOnlyComposable get() = DivanTypeScale
    val night: Boolean
        @Composable @ReadOnlyComposable get() = LocalNight.current
}

@Composable
fun isNight(mode: ThemeMode): Boolean = when (mode) {
    ThemeMode.NIGHT -> true
    ThemeMode.DAY -> false
    ThemeMode.SYSTEM -> isSystemInDarkTheme()
}

/** The Divan theme: night or day palette, IRANYekanX everywhere, right-to-left always (the product is Persian). */
@Composable
fun DivanTheme(night: Boolean, content: @Composable () -> Unit) {
    val p = if (night) NightPalette else DayPalette
    val scheme = if (night) {
        darkColorScheme(
            primary = p.goldFill, onPrimary = p.onGold, secondary = p.silverInk, onSecondary = p.onSilver,
            background = p.page, onBackground = p.textPrimary, surface = p.card, onSurface = p.textPrimary,
            surfaceVariant = p.tile, onSurfaceVariant = p.textSecondary, surfaceContainer = p.overlay,
            surfaceContainerHigh = p.raised, surfaceContainerLow = p.card, surfaceContainerLowest = p.page,
            outline = p.lineStrong, outlineVariant = p.lineDivider, error = p.negative, scrim = p.scrim,
        )
    } else {
        lightColorScheme(
            primary = p.goldFill, onPrimary = p.onGold, secondary = p.silverInk, onSecondary = p.onSilver,
            background = p.page, onBackground = p.textPrimary, surface = p.card, onSurface = p.textPrimary,
            surfaceVariant = p.tile, onSurfaceVariant = p.textSecondary, surfaceContainer = p.overlay,
            surfaceContainerHigh = p.raised, surfaceContainerLow = p.card, surfaceContainerLowest = p.page,
            outline = p.lineStrong, outlineVariant = p.lineDivider, error = p.negative, scrim = p.scrim,
        )
    }
    val t = DivanTypeScale
    val m3 = Typography(
        displayLarge = t.display, displayMedium = t.display, displaySmall = t.h1,
        headlineLarge = t.h1, headlineMedium = t.h2, headlineSmall = t.h3,
        titleLarge = t.h2, titleMedium = t.h3, titleSmall = t.bodyStrong,
        bodyLarge = t.body, bodyMedium = t.small, bodySmall = t.caption,
        labelLarge = t.bodyStrong, labelMedium = t.caption, labelSmall = t.micro,
    )
    MaterialTheme(colorScheme = scheme, typography = m3) {
        CompositionLocalProvider(
            LocalPalette provides p,
            LocalNight provides night,
            LocalLayoutDirection provides LayoutDirection.Rtl,
            LocalContentColor provides p.textPrimary,
            LocalTextStyle provides t.body.copy(color = p.textPrimary),
            content = content,
        )
    }
}
