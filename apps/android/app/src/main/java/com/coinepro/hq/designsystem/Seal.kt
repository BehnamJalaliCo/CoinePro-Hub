package com.coinepro.hq.designsystem

import android.graphics.Paint
import android.graphics.Typeface
import androidx.compose.animation.core.CubicBezierEasing
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.requiredSize
import androidx.compose.foundation.layout.size
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.draw.scale
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.drawIntoCanvas
import androidx.compose.ui.graphics.nativeCanvas
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.core.content.res.ResourcesCompat
import com.coinepro.hq.R
import com.coinepro.hq.designsystem.generated.BrandData
import com.coinepro.hq.designsystem.generated.DivanFixed
import com.coinepro.hq.designsystem.generated.DivanMotion
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.max
import kotlin.math.sin

enum class SealState { READY, HOLDING, SEALED }

private val Ceremony = CubicBezierEasing(DivanMotion.CEREMONY[0], DivanMotion.CEREMONY[1], DivanMotion.CEREMONY[2], DivanMotion.CEREMONY[3])

private fun star(cx: Float, cy: Float, ro: Float, ri: Float, n: Int, rot: Float = -90f): Path = Path().apply {
    for (k in 0 until 2 * n) {
        val r = if (k % 2 == 0) ro else ri
        val a = ((rot + (180f / n) * k) * PI / 180).toFloat()
        val x = cx + r * cos(a)
        val y = cy + r * sin(a)
        if (k == 0) moveTo(x, y) else lineTo(x, y)
    }
    close()
}

/** The seal ("مُهر", owner decision 2026-10-17). A company seal carries the company's own mark with its name
 *  around it; the holding seal is the distinct one (24-ray sunburst, lapis jewel when sealed, two-metal CP). */
@Composable
fun Seal(
    code: String,
    nameFa: String,
    nameEn: String,
    modifier: Modifier = Modifier,
    holding: Boolean = false,
    state: SealState = SealState.READY,
    size: Dp = 88.dp,
    progress: Float = 0f,
    dateLabel: String? = null,
) {
    val c = Divan.colors
    val ctx = LocalContext.current
    val faces = remember {
        val fa = ResourcesCompat.getFont(ctx, R.font.iranyekanx_fanum)
        val la = ResourcesCompat.getFont(ctx, R.font.iranyekanx_latin)
        Typeface.create(fa, 700, false) to Typeface.create(la, 700, false)
    }
    val sealed = state == SealState.SEALED
    val rot by animateFloatAsState(if (sealed) -6f else 0f, tween(DivanMotion.CEREMONY_MS, easing = Ceremony), label = "seal-rot")
    val sc by animateFloatAsState(if (state == SealState.HOLDING) 0.96f else 1f, tween(DivanMotion.CEREMONY_MS, easing = Ceremony), label = "seal-scale")
    val showText = size >= 80.dp
    val name = if (holding) "هلدینگ کوینه‌پرو" else nameFa

    Column(
        modifier.semantics { contentDescription = if (sealed) "مُهر $name خورد" else "مُهر $name" },
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Box(Modifier.size(size), contentAlignment = Alignment.Center) {
            if (state == SealState.HOLDING) {
                Canvas(Modifier.requiredSize(size + 12.dp)) {
                    val r = this.size.minDimension / 2 - 1.5.dp.toPx()
                    drawCircle(c.lineTahrir, r, style = Stroke(3.dp.toPx()))
                    drawArc(
                        c.goldFill, -90f, 360f * progress.coerceIn(0f, 1f), false,
                        topLeft = Offset(center.x - r, center.y - r), size = androidx.compose.ui.geometry.Size(2 * r, 2 * r),
                        style = Stroke(3.dp.toPx(), cap = StrokeCap.Round),
                    )
                }
            }
            Box(Modifier.size(size).rotate(rot).scale(sc), contentAlignment = Alignment.Center) {
                Canvas(Modifier.size(size)) {
                    if (holding) drawHolding(sealed, showText, c.goldFill, c.goldInk, c.page, faces.first, faces.second)
                    else drawCompany(sealed, showText, nameFa, nameEn, c.goldFill, c.goldInk, if (sealed) c.onGold else c.goldInk, c.page, faces.first, faces.second)
                }
                if (holding) {
                    val ink = if (sealed) null else c.goldInk
                    if (sealed) SealedMonogram(size * 0.34f) else Monogram(size * 0.34f, ink = ink)
                } else {
                    val ink = if (sealed) c.onGold else c.goldInk
                    if (BrandData.companies.containsKey(code)) CompanyMark(code, height = size * (if (showText) 0.36f else 0.5f), mono = true, ink = ink)
                    else Monogram(size * 0.3f, ink = ink)
                }
            }
        }
        if (sealed && dateLabel != null) Text(dateLabel, style = Divan.type.micro, color = c.goldInk)
    }
}

/** The CP monogram in its fixed metals, on the lapis jewel of a sealed holding seal. */
@Composable
private fun SealedMonogram(size: Dp) = Monogram(size, metals = Color(0xFFDBDBDB) to Color(0xFFD8A848))

private fun DrawScope.arcText(text: String, r: Float, fs: Float, color: Color, top: Boolean, face: Typeface, latin: Boolean) {
    val cx = size.width / 2
    val rb = if (top) r - fs * 0.35f else r + fs * 0.35f
    val path = android.graphics.Path().apply {
        addArc(cx - rb, cx - rb, cx + rb, cx + rb, 180f, if (top) 180f else -180f)
    }
    val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        typeface = face
        textSize = fs
        this.color = color.toArgb()
        letterSpacing = if (latin) 0.22f else 0.02f
    }
    val len = (PI * rb).toFloat()
    val w = paint.measureText(text)
    drawIntoCanvas { it.nativeCanvas.drawTextOnPath(text, path, max(0f, (len - w) / 2), 0f, paint) }
}

private fun DrawScope.drawHolding(sealed: Boolean, showText: Boolean, gold: Color, goldInk: Color, page: Color, fa: Typeface, la: Typeface) {
    val s = size.minDimension
    val cx = s / 2
    val metal = if (sealed) gold else goldInk
    if (sealed) drawPath(star(cx, cx, s / 2, s / 2 * 0.92f, 24), metal)
    else drawPath(star(cx, cx, s / 2 - 0.6f, s / 2 * 0.92f, 24), metal, style = Stroke(1.dp.toPx(), join = androidx.compose.ui.graphics.StrokeJoin.Round))
    drawCircle(if (sealed) DivanFixed.lapisDisc else page, s / 2 * 0.89f)
    drawCircle(metal, s / 2 * 0.85f, style = Stroke(1.2.dp.toPx()))
    drawCircle(metal.copy(alpha = 0.55f), s / 2 * 0.57f, style = Stroke(1.dp.toPx()))
    if (showText) {
        val rTxt = (s / 2 * 0.85f + s / 2 * 0.57f) / 2
        arcText("ستاد کوینه‌پرو · مُهر مدیر کل", rTxt, s * 0.068f, metal, true, fa, false)
        arcText("COINEPRO HOLDING", rTxt, s * 0.05f, metal, false, la, true)
        for (ang in listOf(180.0, 0.0)) {
            val a = ang * PI / 180
            drawPath(star(cx + rTxt * cos(a).toFloat(), cx + rTxt * sin(a).toFloat(), s * 0.03f, s * 0.013f, 8), metal)
        }
    }
}

private fun DrawScope.drawCompany(sealed: Boolean, showText: Boolean, nameFa: String, nameEn: String, gold: Color, goldInk: Color, ink: Color, page: Color, fa: Typeface, la: Typeface) {
    val s = size.minDimension
    val cx = s / 2
    val rOut = s / 2 - 1.dp.toPx()
    val rIn = s / 2 * 0.6f
    drawCircle(if (sealed) gold else page, rOut)
    drawCircle(if (sealed) gold else goldInk, rOut, style = Stroke(1.5.dp.toPx()))
    drawCircle(ink.copy(alpha = 0.35f), rOut - s * 0.045f, style = Stroke(0.8.dp.toPx()))
    drawCircle(ink.copy(alpha = 0.5f), rIn, style = Stroke(1.dp.toPx()))
    if (showText) {
        val rTxt = (rOut - s * 0.045f + rIn) / 2
        arcText(nameFa, rTxt, s * 0.088f, ink, true, fa, false)
        arcText(nameEn.uppercase(), rTxt, s * 0.056f, ink, false, la, true)
        for (ang in listOf(180.0, 0.0)) {
            val a = ang * PI / 180
            drawCircle(ink, max(1f, s * 0.014f), Offset(cx + rTxt * cos(a).toFloat(), cx + rTxt * sin(a).toFloat()))
        }
    }
}
