package com.coinepro.hq.designsystem

import androidx.compose.foundation.Image
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Icon
import androidx.compose.material3.LocalContentColor
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.PathFillType
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.addPathNodes
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.coinepro.hq.designsystem.generated.BrandData
import com.coinepro.hq.designsystem.generated.BrandMark
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.designsystem.generated.MarkRole

private val iconCache = HashMap<Pair<DivanIcon, Boolean>, ImageVector>()

/** The glyph as a vector: 24-grid outline, plus the filled heart when active. Directional glyphs mirror in RTL. */
fun DivanIcon.vector(active: Boolean = false): ImageVector = synchronized(iconCache) {
    iconCache.getOrPut(this to active) {
        ImageVector.Builder(name = id, defaultWidth = 24.dp, defaultHeight = 24.dp, viewportWidth = 24f, viewportHeight = 24f, autoMirror = mirror)
            .apply {
                addPath(
                    pathData = addPathNodes(stroke), fill = null, stroke = SolidColor(Color.Black),
                    strokeLineWidth = 1.6f, strokeLineCap = StrokeCap.Round, strokeLineJoin = StrokeJoin.Round,
                )
                if (active && heart != null) addPath(pathData = addPathNodes(heart), fill = SolidColor(Color.Black), fillAlpha = 0.9f)
            }
            .build()
    }
}

/** A Divan icon. Colour = the current content colour unless [tint] is given. */
@Composable
fun DIcon(icon: DivanIcon, modifier: Modifier = Modifier, size: Dp = 22.dp, tint: Color = LocalContentColor.current, active: Boolean = false, label: String? = null) {
    Icon(imageVector = icon.vector(active), contentDescription = label, modifier = modifier.size(size), tint = tint)
}

// ----------------------------------------------------------------- marks --
private fun buildMark(name: String, vb: FloatArray, layers: List<Pair<String, Color>>): ImageVector {
    val b = ImageVector.Builder(name = name, defaultWidth = vb[2].dp, defaultHeight = vb[3].dp, viewportWidth = vb[2], viewportHeight = vb[3])
    b.addGroup(translationX = -vb[0], translationY = -vb[1])
    for ((d, c) in layers) b.addPath(pathData = addPathNodes(d), fill = SolidColor(c), pathFillType = PathFillType.EvenOdd)
    b.clearGroup()
    return b.build()
}

/** The CP monogram in two metals (silver + gold by night, graphite + ink gold by day) or one [ink]. */
@Composable
fun Monogram(size: Dp, modifier: Modifier = Modifier, ink: Color? = null, metals: Pair<Color, Color>? = null) {
    val c = Divan.colors
    val silver = ink ?: metals?.first ?: c.markSilver
    val gold = ink ?: metals?.second ?: c.markGold
    val v = remember(silver, gold) {
        buildMark("monogram", BrandData.monogramViewBox, listOf(BrandData.MONOGRAM_SILVER to silver, BrandData.MONOGRAM_GOLD to gold))
    }
    val vb = BrandData.monogramViewBox
    Image(v, contentDescription = null, modifier = modifier.size(width = size, height = size * (vb[3] / vb[2])))
}

/** The owner's CoinePro wordmark: silver "Coine" + gold "Pro". */
@Composable
fun Wordmark(width: Dp, modifier: Modifier = Modifier) {
    val c = Divan.colors
    val v = remember(c.markSilver, c.markGold) {
        buildMark("wordmark", BrandData.wordmarkViewBox, listOf(BrandData.WORDMARK_SILVER to c.markSilver, BrandData.WORDMARK_GOLD to c.markGold))
    }
    val vb = BrandData.wordmarkViewBox
    Image(v, contentDescription = "CoinePro", modifier = modifier.size(width = width, height = width * (vb[3] / vb[2])))
}

private fun BrandMark.vector(code: String, ink: Color, mono: Boolean): ImageVector =
    buildMark(code, viewBox, layers.map { it.path to if (mono || it.role == MarkRole.INK) ink else Color(it.color) })

/** A company's own mark (data keyed by company code). [mono] draws it in one ink (lists, seals).
 *  A company without a mark shows its code in a small cartouche. */
@Composable
fun CompanyMark(
    code: String,
    height: Dp = 16.dp,
    modifier: Modifier = Modifier,
    mono: Boolean = false,
    ink: Color = LocalContentColor.current,
    wordmark: Boolean = false,
    label: String? = null,
) {
    val brand = BrandData.companies[code]
    val mark = if (wordmark) brand?.wordmark ?: brand?.mark else brand?.mark
    if (mark == null) {
        Box(
            modifier
                .height(maxOf(16.dp, height))
                .border(1.dp, Divan.colors.lineStrong, RoundedCornerShape(5.dp))
                .padding(horizontal = 5.dp)
                .semantics { contentDescription = label ?: code },
            contentAlignment = Alignment.Center,
        ) {
            Text(code, style = Divan.type.figureSmall.copy(fontSize = 10.sp, fontWeight = FontWeight.Bold), color = Divan.colors.textPrimary)
        }
        return
    }
    val v = remember(code, ink, mono, wordmark) { mark.vector(code, ink, mono) }
    val vb = mark.viewBox
    Image(v, contentDescription = label ?: code, modifier = modifier.size(width = height * (vb[2] / vb[3]), height = height))
}
