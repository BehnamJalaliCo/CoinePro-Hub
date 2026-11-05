package com.coinepro.hq.ui.v33

import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.clipRect
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.coinepro.hq.core.data.moneyFigure
import com.coinepro.hq.core.data.retainedPercents
import com.coinepro.hq.core.format.jMonth
import com.coinepro.hq.core.net.RevCohort
import com.coinepro.hq.core.net.RevForecast
import com.coinepro.hq.core.net.RevMonth
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.FigureFace
import com.coinepro.hq.designsystem.LocalReducedMotion
import com.coinepro.hq.designsystem.Motion
import com.coinepro.hq.designsystem.TextFace
import com.coinepro.hq.designsystem.axisOf
import com.coinepro.hq.designsystem.springIn
import com.coinepro.hq.ui.v16.compact

// Contract §33.3 ⟨1.15⟩: the pictures of the revenue board. The monthly revenue line draws in from the start, the forecast continues it as a
// dashed line inside its band, a press shows the month's figure; the bars show who came and who left; the cohort grid shows who stayed.

/** The monthly revenue (solid), its forecast (dashed) and the band the forecast is likely to stay inside (soft fill). Time runs left to right. */
@Composable
fun MrrChart(months: List<RevMonth>, forecast: List<RevForecast>, modifier: Modifier = Modifier, height: Dp = 190.dp) {
    val c = Divan.colors
    val measurer = rememberTextMeasurer()
    val hist = months.map { it.mrrUsdt }
    val h = hist.size
    val n = h + forecast.size
    val labels = months.map { jMonth(it.month) } + forecast.map { jMonth(it.month) }
    val (yMax, yStep) = remember(months, forecast) { axisOf(hist + forecast.flatMap { listOf(it.mrrUsdt, it.high) }) }
    val reduced = LocalReducedMotion.current
    val reveal = remember(months, forecast) { Animatable(if (reduced) 1f else 0f) }
    LaunchedEffect(months, forecast, reduced) { if (reduced) reveal.snapTo(1f) else reveal.animateTo(1f, tween(Motion.EMPHASISED + 400, easing = Motion.Emphasised)) }
    var hi by remember { mutableStateOf<Int?>(null) }
    val axis = androidx.compose.ui.text.TextStyle(fontFamily = FigureFace, fontSize = 11.sp, color = c.textMuted)
    val label = androidx.compose.ui.text.TextStyle(fontFamily = TextFace, fontSize = 11.sp, color = c.textMuted)
    val tip = androidx.compose.ui.text.TextStyle(fontFamily = FigureFace, fontSize = 12.sp, color = c.textPrimary, fontWeight = FontWeight.SemiBold)
    val line = c.goldFill
    val fc = c.lapis
    val desc = "درآمد ماهانه ${hist.lastOrNull()?.let { moneyFigure(it) } ?: ""}"
    CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
        Canvas(
            modifier.fillMaxWidth().height(height).semantics { contentDescription = desc }
                .pointerInput(n) {
                    detectTapGestures(onPress = { p ->
                        val l = 40.dp.toPx(); val r = 14.dp.toPx()
                        hi = (((p.x - l) / (size.width - l - r)) * (n - 1).coerceAtLeast(1)).let { Math.round(it).toInt() }.takeIf { n > 0 && it in 0 until n }
                        tryAwaitRelease()
                        hi = null
                    })
                },
        ) {
            if (n == 0) return@Canvas
            val l = 40.dp.toPx(); val r = 14.dp.toPx(); val t = 22.dp.toPx(); val b = 22.dp.toPx()
            val w = size.width; val ht = size.height
            fun x(i: Int) = if (n <= 1) (l + w - r) / 2 else l + i.toFloat() / (n - 1) * (w - l - r)
            fun y(v: Double) = (ht - b - (v / yMax) * (ht - t - b)).toFloat()
            for (k in 0..4) {
                val v = yStep * k
                drawLine(c.lineDivider, Offset(l, y(v)), Offset(w - r, y(v)), 1f)
                val lay = measurer.measure(compact(v), axis)
                drawText(lay, topLeft = Offset(l - 6.dp.toPx() - lay.size.width, y(v) - lay.size.height / 2))
            }
            val every = maxOf(1, Math.ceil(n / 5.0).toInt())
            labels.forEachIndexed { i, s ->
                if (i % every == 0 || i == n - 1) {
                    val lay = measurer.measure(s, label)
                    drawText(lay, topLeft = Offset((x(i) - lay.size.width / 2).coerceIn(0f, w - lay.size.width), ht - lay.size.height))
                }
            }
            val p = reveal.value
            clipRect(right = l + (w - l - r) * p + 6.dp.toPx()) {
                // The band first, under the lines: high forward, low backward, starting at the last real month.
                if (forecast.isNotEmpty() && h > 0) {
                    val band = Path()
                    band.moveTo(x(h - 1), y(hist.last()))
                    forecast.forEachIndexed { k, f -> band.lineTo(x(h + k), y(f.high)) }
                    for (k in forecast.indices.reversed()) band.lineTo(x(h + k), y(forecast[k].low))
                    band.close()
                    drawPath(band, fc.copy(alpha = 0.16f))
                    val fl = Path()
                    fl.moveTo(x(h - 1), y(hist.last()))
                    forecast.forEachIndexed { k, f -> fl.lineTo(x(h + k), y(f.mrrUsdt)) }
                    drawPath(fl, fc, style = Stroke(2.dp.toPx(), cap = StrokeCap.Round, join = StrokeJoin.Round, pathEffect = PathEffect.dashPathEffect(floatArrayOf(7.dp.toPx(), 6.dp.toPx()))))
                }
                val hl = Path()
                hist.forEachIndexed { i, v -> if (i == 0) hl.moveTo(x(i), y(v)) else hl.lineTo(x(i), y(v)) }
                drawPath(hl, line, style = Stroke(2.5.dp.toPx(), cap = StrokeCap.Round, join = StrokeJoin.Round))
            }
            if (h > 0) {
                val shown = ((p - 0.7f).coerceIn(0f, 0.3f) / 0.3f)
                drawCircle(c.card.copy(alpha = shown), 6.dp.toPx(), Offset(x(h - 1), y(hist.last())))
                drawCircle(line.copy(alpha = shown), 4.5.dp.toPx(), Offset(x(h - 1), y(hist.last())))
            }
            hi?.let { i ->
                drawLine(c.lineStrong, Offset(x(i), t), Offset(x(i), ht - b), 1f)
                val v = if (i < h) hist[i] else forecast[i - h].mrrUsdt
                drawCircle(c.card, 5.5.dp.toPx(), Offset(x(i), y(v)))
                drawCircle(if (i < h) line else fc, 4.dp.toPx(), Offset(x(i), y(v)))
                val text = moneyFigure(v) + if (i >= h) " (${moneyFigure(forecast[i - h].low)}–${moneyFigure(forecast[i - h].high)})" else ""
                val lay = measurer.measure(text, tip)
                drawText(lay, topLeft = Offset((x(i) - lay.size.width / 2).coerceIn(0f, w - lay.size.width), 0f))
            }
        }
    }
}

/** Who came (up, positive) and who left (down, negative) in each month; the month's name under its pair. */
@Composable
fun FlowBars(months: List<RevMonth>, modifier: Modifier = Modifier, height: Dp = 120.dp) {
    val c = Divan.colors
    val measurer = rememberTextMeasurer()
    val max = (months.maxOfOrNull { maxOf(it.newCustomers, it.churned) } ?: 0).coerceAtLeast(1)
    val reduced = LocalReducedMotion.current
    val grow = remember(months) { Animatable(if (reduced) 1f else 0f) }
    LaunchedEffect(months, reduced) { if (reduced) grow.snapTo(1f) else grow.animateTo(1f, tween(Motion.EMPHASISED, easing = Motion.Emphasised)) }
    val label = androidx.compose.ui.text.TextStyle(fontFamily = TextFace, fontSize = 11.sp, color = c.textMuted)
    val fig = androidx.compose.ui.text.TextStyle(fontFamily = FigureFace, fontSize = 11.sp, color = c.textSecondary, fontWeight = FontWeight.SemiBold)
    CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
        Canvas(modifier.fillMaxWidth().height(height).semantics { contentDescription = "مشتری تازه و رفته در هر ماه" }) {
            val n = months.size
            if (n == 0) return@Canvas
            val bottom = 20.dp.toPx()
            val mid = (size.height - bottom) / 2f
            val slot = size.width / n
            val bw = minOf(slot * 0.28f, 18.dp.toPx())
            val room = mid - 14.dp.toPx()
            drawLine(c.lineDivider, Offset(0f, mid), Offset(size.width, mid), 1f)
            months.forEachIndexed { i, m ->
                val cx = slot * i + slot / 2
                val up = room * (m.newCustomers.toFloat() / max) * grow.value
                val down = room * (m.churned.toFloat() / max) * grow.value
                if (m.newCustomers > 0) drawRoundRect(c.positive, Offset(cx - bw - 1.dp.toPx(), mid - up), Size(bw, up), CornerRadius(3.dp.toPx()))
                if (m.churned > 0) drawRoundRect(c.negative, Offset(cx + 1.dp.toPx(), mid), Size(bw, down), CornerRadius(3.dp.toPx()))
                val lay = measurer.measure(jMonth(m.month), label)
                drawText(lay, topLeft = Offset(cx - lay.size.width / 2, size.height - lay.size.height))
                if (m.newCustomers > 0) {
                    val f = measurer.measure(m.newCustomers.toString(), fig)
                    drawText(f, topLeft = Offset(cx - bw / 2 - 1.dp.toPx() - f.size.width / 2, (mid - up - f.size.height - 1.dp.toPx()).coerceAtLeast(0f)))
                }
                if (m.churned > 0) {
                    val f = measurer.measure(m.churned.toString(), fig)
                    drawText(f, topLeft = Offset(cx + bw / 2 + 1.dp.toPx() - f.size.width / 2, mid + down + 1.dp.toPx()))
                }
            }
        }
    }
}

/** Who stayed: a row per month of joining, a cell per month since, darker for more people kept. Shows up to [columns] months. */
@Composable
fun CohortGrid(cohorts: List<RevCohort>, modifier: Modifier = Modifier, columns: Int = 6) {
    val c = Divan.colors
    val cols = minOf(columns, cohorts.maxOfOrNull { it.retained.size } ?: 0)
    if (cols == 0) return
    Column(modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Row(horizontalArrangement = Arrangement.spacedBy(4.dp), verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.width(64.dp))
            for (k in 0 until cols) Text(com.coinepro.hq.ui.v29.plain(if (k == 0) "ماه ۰" else "$k"), Modifier.weight(1f), style = Divan.type.micro, color = c.textMuted, textAlign = androidx.compose.ui.text.style.TextAlign.Center)
        }
        cohorts.forEachIndexed { r, co ->
            val pcts = retainedPercents(co)
            Row(Modifier.springIn(r), horizontalArrangement = Arrangement.spacedBy(4.dp), verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.width(64.dp)) {
                    Text(jMonth(co.startMonth), style = Divan.type.caption, color = c.textSecondary, maxLines = 1)
                    Text(com.coinepro.hq.ui.v29.plain("${co.size} نفر"), style = Divan.type.micro, color = c.textMuted, maxLines = 1)
                }
                for (k in 0 until cols) {
                    val v = pcts.getOrNull(k)
                    Box(
                        Modifier.weight(1f).height(26.dp).clip(RoundedCornerShape(6.dp))
                            .background(if (v == null) Color.Transparent else c.positive.copy(alpha = (0.12f + 0.55f * (v / 100.0).toFloat()).coerceIn(0.1f, 0.7f))),
                        contentAlignment = Alignment.Center,
                    ) {
                        if (v != null) Text(String.format(java.util.Locale.US, "%.0f", v), style = Divan.type.figureSmall, color = c.textPrimary, maxLines = 1)
                    }
                }
            }
        }
        Text("درصدِ کسانی که هنوز می‌مانند", Modifier.padding(top = 2.dp), style = Divan.type.micro, color = c.textMuted)
    }
}
