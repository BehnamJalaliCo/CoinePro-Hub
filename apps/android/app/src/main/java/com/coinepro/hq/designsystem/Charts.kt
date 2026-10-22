package com.coinepro.hq.designsystem

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlin.math.abs
import kotlin.math.ceil
import kotlin.math.floor
import kotlin.math.log10
import kotlin.math.pow
import kotlin.math.roundToInt

/** One segment of a stacked bar; identity is never by colour alone (legend with words). */
data class Seg(val key: String, val label: String, val value: Double, val color: Color, val valueText: String)

/** A single stacked bar with a legend under it. 2dp surface gaps between segments, rounded ends. */
@Composable
fun StackedBar(segs: List<Seg>, label: String, modifier: Modifier = Modifier, height: Dp = 14.dp) {
    val c = Divan.colors
    val total = segs.sumOf { it.value }.takeIf { it > 0 } ?: 1.0
    Column(modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(Modifier.fillMaxWidth().height(height).semantics { contentDescription = label }, horizontalArrangement = Arrangement.spacedBy(2.dp)) {
            for (s in segs.filter { it.value > 0 }) {
                Box(Modifier.weight((s.value / total).toFloat()).height(height).clip(RoundedCornerShape(4.dp)).background(s.color))
            }
        }
        FlowRow(horizontalArrangement = Arrangement.spacedBy(14.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            for (s in segs) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Box(Modifier.size(8.dp).clip(CircleShape).background(s.color))
                    Text(s.label, style = Divan.type.caption, color = c.textSecondary)
                    Fig(s.valueText, style = Divan.type.figureSmall, color = c.textPrimary)
                }
            }
        }
    }
}

data class HBarRow(val key: String, val value: Double, val valueText: String, val color: Color? = null, val sub: String? = null, val label: @Composable () -> Unit)

/** Horizontal bars, one per row: label and value above, the bar under them. Values are figures. */
@Composable
fun HBars(rows: List<HBarRow>, modifier: Modifier = Modifier, max: Double? = null) {
    val c = Divan.colors
    val m = (max ?: rows.maxOfOrNull { it.value } ?: 1.0).takeIf { it > 0 } ?: 1.0
    Column(modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        for (r in rows) {
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.weight(1f)) { r.label() }
                    if (r.sub != null) {
                        Text(r.sub, style = Divan.type.micro, color = c.textMuted)
                        Spacer(Modifier.width(8.dp))
                    }
                    Fig(r.valueText, style = Divan.type.figure, color = c.textPrimary)
                }
                MeterBar((r.value / m * 100).coerceAtLeast(1.5), height = 8.dp, color = r.color ?: c.silverInk)
            }
        }
    }
}

/** Cumulative use against a budget line, with a dashed forecast to the end of the period. Time runs left to
 *  right (data-chart convention); press or drag for the crosshair and its readout. */
@Composable
fun CumulativeChart(days: List<Pair<String, Double>>, budget: Double?, forecastTo: Int, fmt: (Double) -> String, modifier: Modifier = Modifier, height: Dp = 220.dp) {
    val c = Divan.colors
    val measurer = rememberTextMeasurer()
    var hi by remember { mutableStateOf<Int?>(null) }
    val cum = remember(days) { days.runningFold(0.0) { a, d -> a + d.second }.drop(1) }
    val n = maxOf(forecastTo, days.size)
    val last = cum.lastOrNull() ?: 0.0
    val rate = if (days.isNotEmpty()) last / days.size else 0.0
    val fc = if (n > days.size) last + rate * (n - days.size) else last
    val yMax = maxOf(budget ?: 0.0, fc, last, 1.0) * 1.08
    val axis = TextStyle(fontFamily = FigureFace, fontSize = 11.sp, color = c.textMuted)
    CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
        Column(modifier.fillMaxWidth()) {
            Box(Modifier.fillMaxWidth().height(24.dp)) {
                val i = hi
                if (i != null && i < cum.size) {
                    Row(Modifier.align(Alignment.CenterStart), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        Text(days[i].first, style = Divan.type.caption, color = c.textMuted)
                        Fig(fmt(cum[i]), style = Divan.type.figure, color = c.textPrimary)
                        Fig("+" + fmt(days[i].second), style = Divan.type.figure, color = c.textSecondary)
                    }
                }
            }
            Canvas(
                Modifier
                    .fillMaxWidth()
                    .height(height)
                    .semantics { contentDescription = "مصرف تجمعی در برابر بودجه" }
                    .pointerInput(n, cum.size) {
                        fun pick(x: Float) {
                            val l = 48.dp.toPx(); val r = 12.dp.toPx()
                            val i = (((x - l) / (size.width - l - r)) * (n - 1)).roundToInt()
                            hi = i.takeIf { it in cum.indices }
                        }
                        detectTapGestures(onPress = { pick(it.x); tryAwaitRelease(); hi = null })
                    }
                    .pointerInput(n, cum.size) {
                        detectDragGestures(onDragEnd = { hi = null }, onDragCancel = { hi = null }) { ch, _ ->
                            val l = 48.dp.toPx(); val r = 12.dp.toPx()
                            val i = (((ch.position.x - l) / (size.width - l - r)) * (n - 1)).roundToInt()
                            hi = i.takeIf { it in cum.indices }
                        }
                    },
            ) {
                val l = 48.dp.toPx(); val r = 12.dp.toPx(); val t = 12.dp.toPx(); val b = 24.dp.toPx()
                val w = size.width; val h = size.height
                fun x(i: Int) = l + (i.toFloat() / maxOf(n - 1, 1)) * (w - l - r)
                fun y(v: Double) = (h - b - (v / yMax) * (h - t - b)).toFloat()
                for (k in 0..4) {
                    val v = yMax * k / 4
                    drawLine(c.lineDivider, Offset(l, y(v)), Offset(w - r, y(v)), 1f)
                    val lay = measurer.measure(fmt(v), axis)
                    drawText(lay, topLeft = Offset(l - 6.dp.toPx() - lay.size.width, y(v) - lay.size.height / 2))
                }
                if (budget != null && budget > 0) {
                    drawLine(c.negative, Offset(l, y(budget)), Offset(w - r, y(budget)), 1.5.dp.toPx(), pathEffect = PathEffect.dashPathEffect(floatArrayOf(12f, 10f)))
                    val lay = measurer.measure(fmt(budget), axis.copy(color = c.negative))
                    drawText(lay, topLeft = Offset(w - r - lay.size.width, y(budget) - lay.size.height - 2.dp.toPx()))
                }
                if (cum.isNotEmpty()) {
                    val line = Path().apply { cum.forEachIndexed { i, v -> if (i == 0) moveTo(x(i), y(v)) else lineTo(x(i), y(v)) } }
                    val area = Path().apply { addPath(line); lineTo(x(cum.size - 1), y(0.0)); lineTo(x(0), y(0.0)); close() }
                    drawPath(area, c.chart[0].copy(alpha = 0.12f))
                    drawPath(line, c.chart[0], style = Stroke(2.dp.toPx(), cap = StrokeCap.Round, join = StrokeJoin.Round))
                    if (n > cum.size) {
                        drawLine(c.chart[0].copy(alpha = 0.7f), Offset(x(cum.size - 1), y(last)), Offset(x(n - 1), y(fc)), 2.dp.toPx(), pathEffect = PathEffect.dashPathEffect(floatArrayOf(8f, 12f)))
                    }
                }
                val every = maxOf(1, (days.size + 3) / 4)
                days.forEachIndexed { i, d ->
                    if (i % every == 0) {
                        val lay = measurer.measure(d.first, axis.copy(fontFamily = TextFace))
                        drawText(lay, topLeft = Offset((x(i) - lay.size.width / 2).coerceIn(0f, w - lay.size.width), h - lay.size.height))
                    }
                }
                hi?.let { i ->
                    if (i in cum.indices) {
                        drawLine(c.lineStrong, Offset(x(i), t), Offset(x(i), h - b), 1f)
                        drawCircle(c.card, 7.dp.toPx(), Offset(x(i), y(cum[i])))
                        drawCircle(c.chart[0], 5.dp.toPx(), Offset(x(i), y(cum[i])))
                    }
                }
            }
        }
    }
}

/** One series of [LinesChart]: a value per day, null where the day has no data (a gap in the line, never a zero). [mark] is drawn
 *  beside its name in the legend (a company's mark). */
data class ChartLine(val key: String, val label: String, val color: Color, val values: List<Double?>, val mark: (@Composable () -> Unit)? = null)

/** 1, 2, 2.5, 5 or 10 times a power of ten, at least [v]: the axis top. */
private fun niceCeil(v: Double): Double {
    val e = 10.0.pow(floor(log10(v)))
    val m = v / e
    return e * when { m <= 1 -> 1.0; m <= 2 -> 2.0; m <= 2.5 -> 2.5; m <= 5 -> 5.0; else -> 10.0 }
}

/** Several series over the same days on one axis (the web's LinesChart): a legend above (identity is never by colour alone; a
 *  press focuses one line), each line's last value as a direct label in the end gutter (a leader joins a label that had to move,
 *  or a line that ended early), and press or drag for a crosshair with every line's value. Time runs left to right; a missing
 *  day is a gap in the line, never a zero. [days] are the axis labels, one per value. */
@Composable
fun LinesChart(days: List<String>, lines: List<ChartLine>, fmt: (Double) -> String, label: String, modifier: Modifier = Modifier, tick: (Double) -> String = fmt, height: Dp = 220.dp) {
    val c = Divan.colors
    val measurer = rememberTextMeasurer()
    val density = LocalDensity.current
    var hi by remember { mutableStateOf<Int?>(null) }
    var focus by remember { mutableStateOf<String?>(null) }
    var width by remember { mutableIntStateOf(0) }
    val n = days.size
    val yMax = remember(lines) { niceCeil(maxOf(1.0, lines.flatMap { it.values.filterNotNull() }.maxOrNull() ?: 0.0) * 1.06) }
    val axis = TextStyle(fontFamily = FigureFace, fontSize = 11.sp, color = c.textMuted)
    val endText = axis.copy(color = c.textSecondary, fontWeight = FontWeight.SemiBold)
    val padL = 44.dp; val padR = 64.dp; val padT = 12.dp; val padB = 24.dp
    Column(modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        FlowRow(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            for (l in lines) {
                Row(
                    Modifier
                        .clip(RoundedCornerShape(6.dp))
                        .clickable(role = Role.Button, onClickLabel = l.label) { focus = if (focus == l.key) null else l.key }
                        .alpha(if (focus != null && focus != l.key) 0.5f else 1f)
                        .padding(horizontal = 4.dp, vertical = 3.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    Box(Modifier.width(14.dp).height(2.dp).clip(CircleShape).background(l.color))
                    l.mark?.invoke()
                    Text(l.label, style = Divan.type.caption, color = c.textSecondary)
                }
            }
        }
        CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
            Box(Modifier.fillMaxWidth().onSizeChanged { width = it.width }) {
                fun pick(px: Float, w: Float): Int? {
                    val l = with(density) { padL.toPx() }; val r = with(density) { padR.toPx() }
                    val i = (((px - l) / (w - l - r)) * (n - 1)).roundToInt()
                    return i.takeIf { n > 0 && it in 0 until n }
                }
                Canvas(
                    Modifier
                        .fillMaxWidth()
                        .height(height)
                        .semantics { contentDescription = label }
                        .pointerInput(n) { detectTapGestures(onPress = { hi = pick(it.x, size.width.toFloat()); tryAwaitRelease(); hi = null }) }
                        .pointerInput(n) {
                            detectDragGestures(onDragEnd = { hi = null }, onDragCancel = { hi = null }) { ch, _ -> hi = pick(ch.position.x, size.width.toFloat()) }
                        },
                ) {
                    val l = padL.toPx(); val r = padR.toPx(); val t = padT.toPx(); val b = padB.toPx()
                    val w = size.width; val h = size.height
                    fun x(i: Int) = l + (if (n <= 1) 0f else i.toFloat() / (n - 1) * (w - l - r))
                    fun y(v: Double) = (h - b - (v / yMax) * (h - t - b)).toFloat()
                    for (k in 0..4) {
                        val v = yMax * k / 4
                        drawLine(c.lineDivider, Offset(l, y(v)), Offset(x(n - 1), y(v)), 1f)
                        val lay = measurer.measure(tick(v), axis)
                        drawText(lay, topLeft = Offset(l - 6.dp.toPx() - lay.size.width, y(v) - lay.size.height / 2))
                    }
                    val every = maxOf(1, ceil(n / 4.0).toInt())
                    days.forEachIndexed { i, d ->
                        if ((i % every == 0 || i == n - 1) && (i == n - 1 || n - 1 - i >= every / 2.0)) {
                            val lay = measurer.measure(d, axis.copy(fontFamily = TextFace))
                            drawText(lay, topLeft = Offset((x(i) - lay.size.width / 2).coerceIn(0f, w - lay.size.width), h - lay.size.height))
                        }
                    }
                    for (ln in lines) {
                        val dim = focus != null && focus != ln.key
                        val path = Path()
                        var pen = false
                        ln.values.forEachIndexed { i, v ->
                            if (v == null) pen = false
                            else {
                                if (pen) path.lineTo(x(i), y(v)) else path.moveTo(x(i), y(v))
                                pen = true
                            }
                        }
                        drawPath(path, ln.color.copy(alpha = if (dim) 0.25f else 1f), style = Stroke(2.dp.toPx(), cap = StrokeCap.Round, join = StrokeJoin.Round))
                    }
                    hi?.let { i -> drawLine(c.lineStrong, Offset(x(i), t), Offset(x(i), h - b), 1f) }
                    // End labels: sorted top to bottom, each pushed down until it clears the one above.
                    class End(val key: String, val color: Color, val i: Int, val v: Double, val at: Float, var ly: Float)
                    val ends = lines.mapNotNull { ln ->
                        val i = ln.values.indexOfLast { it != null }
                        if (i < 0) null else End(ln.key, ln.color, i, ln.values[i]!!, y(ln.values[i]!!), y(ln.values[i]!!))
                    }.sortedBy { it.at }
                    val gap = 14.dp.toPx()
                    ends.forEachIndexed { k, e -> if (k > 0 && e.ly - ends[k - 1].ly < gap) e.ly = ends[k - 1].ly + gap }
                    val gx = x(n - 1) + 10.dp.toPx()
                    for (e in ends) {
                        val a = if (focus != null && focus != e.key) 0.3f else 1f
                        if (e.i < n - 1 || abs(e.ly - e.at) > 1f) {
                            drawLine(c.lineStrong.copy(alpha = c.lineStrong.alpha * a), Offset(x(e.i) + 5.dp.toPx(), e.at), Offset(gx - 3.dp.toPx(), e.ly), 1f)
                        }
                        drawCircle(c.card, 5.5.dp.toPx(), Offset(x(e.i), e.at))
                        drawCircle(e.color.copy(alpha = a), 4.dp.toPx(), Offset(x(e.i), e.at))
                        val lay = measurer.measure(fmt(e.v), endText.copy(color = endText.color.copy(alpha = a)))
                        drawText(lay, topLeft = Offset(gx, e.ly - lay.size.height / 2))
                    }
                    hi?.let { i ->
                        for (ln in lines) ln.values.getOrNull(i)?.let { v ->
                            drawCircle(c.card, 5.5.dp.toPx(), Offset(x(i), y(v)))
                            drawCircle(ln.color, 4.dp.toPx(), Offset(x(i), y(v)))
                        }
                    }
                }
                val i = hi
                if (i != null && width > 0 && n > 0) {
                    val boxW = with(density) { 176.dp.toPx() }
                    val l = with(density) { padL.toPx() }; val r = with(density) { padR.toPx() }; val edge = with(density) { 8.dp.toPx() }
                    val x = l + (if (n <= 1) 0f else i.toFloat() / (n - 1) * (width - l - r))
                    val left = (x - boxW / 2).coerceIn(edge, maxOf(edge, width - boxW - edge))
                    Column(
                        Modifier
                            .offset { IntOffset(left.roundToInt(), 8.dp.roundToPx()) }
                            .width(176.dp)
                            .clip(RoundedCornerShape(10.dp))
                            .background(c.raised)
                            .padding(horizontal = 10.dp, vertical = 8.dp),
                        verticalArrangement = Arrangement.spacedBy(2.dp),
                    ) {
                        CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Rtl) {
                            Text(days[i], style = Divan.type.caption, color = c.textMuted)
                            for (ln in lines.sortedByDescending { it.values.getOrNull(i) ?: -1.0 }) {
                                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                    Box(Modifier.width(12.dp).height(2.dp).clip(CircleShape).background(ln.color))
                                    Text(ln.label, style = Divan.type.caption, color = c.textSecondary, modifier = Modifier.weight(1f), maxLines = 1)
                                    Fig(ln.values.getOrNull(i)?.let(fmt) ?: "—", style = Divan.type.figureSmall, color = c.textPrimary)
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
