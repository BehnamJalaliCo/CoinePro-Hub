package com.coinepro.hq.designsystem

import androidx.compose.runtime.Composable
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.compositionLocalOf
import com.coinepro.hq.designsystem.generated.BrandData
import com.coinepro.hq.designsystem.generated.BrandMark

// Contract §18.14: a company's mark and seal come from its record (GET /brands), then from the marks built into the app
// (design/brand/companies/), and when neither has one the company shows its code. The holding's own marks are not data.

/** One company's active brand, ready to draw: its mark and wordmark, its signature colour ([accent]) and that colour per theme
 *  where it fails 3:1 on the theme's page ([accentNight], [accentDay]). Colours are ARGB. */
@Immutable
class LiveBrand(val mark: BrandMark, val wordmark: BrandMark?, val accent: Long?, val accentNight: Long?, val accentDay: Long?)

/** The companies' active brands, keyed by code: empty until the session has fetched them (and in previews). */
val LocalBrands = compositionLocalOf<Map<String, LiveBrand>> { emptyMap() }

/** "366 260 562 723" → the viewBox array the built-in marks carry. */
fun viewBoxOf(vb: String): FloatArray = vb.trim().split(Regex("[\\s,]+")).map { it.toFloat() }.toFloatArray()

/** "#FD990D" → opaque ARGB. */
fun argbOf(hex: String): Long = 0xFF000000L or hex.removePrefix("#").take(6).toLong(16)

/** The mark a company is drawn with, as both CompanyMark and Seal resolve it; null → its code (or the CP monogram in a seal). */
@Composable
fun companyMarkOf(code: String, wordmark: Boolean = false): BrandMark? {
    val live = LocalBrands.current[code]
    if (live != null) return if (wordmark) live.wordmark ?: live.mark else live.mark
    val built = BrandData.companies[code] ?: return null
    return if (wordmark) built.wordmark ?: built.mark else built.mark
}

/** The accent to draw instead of [LiveBrand.accent] in this theme, as (accent → replacement); null when it passes as it is. */
internal fun LiveBrand.themedAccent(night: Boolean): Pair<Long, Long>? {
    val a = accent ?: return null
    val to = (if (night) accentNight else accentDay) ?: return null
    return a to to
}
