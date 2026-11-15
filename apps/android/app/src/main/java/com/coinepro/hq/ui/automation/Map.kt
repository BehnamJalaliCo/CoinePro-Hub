package com.coinepro.hq.ui.automation

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.animation.core.animateFloat
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTransformGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.absoluteOffset
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.Stable
import androidx.compose.runtime.State
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.AbsoluteAlignment
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.TransformOrigin
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.layout.layout
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Constraints
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.FlowMapLayout
import com.coinepro.hq.core.data.MapDims
import com.coinepro.hq.core.data.NODE_PENDING
import com.coinepro.hq.core.data.NodeBox
import com.coinepro.hq.core.data.Pt
import com.coinepro.hq.core.data.centreOn
import com.coinepro.hq.core.data.clampPan
import com.coinepro.hq.core.data.dayLive
import com.coinepro.hq.core.data.dayStates
import com.coinepro.hq.core.data.faNum
import com.coinepro.hq.core.data.fitScale
import com.coinepro.hq.core.data.flowDayStateFa
import com.coinepro.hq.core.data.flowDayStateTone
import com.coinepro.hq.core.data.flowMapLayout
import com.coinepro.hq.core.data.focusKey
import com.coinepro.hq.core.data.helperFa
import com.coinepro.hq.core.data.laneFa
import com.coinepro.hq.core.data.legendOf
import com.coinepro.hq.core.data.mapDayFa
import com.coinepro.hq.core.data.minutesBetween
import com.coinepro.hq.core.data.modelFa
import com.coinepro.hq.core.data.nodeStateFa
import com.coinepro.hq.core.data.nodeStateTone
import com.coinepro.hq.core.data.zoomAbout
import com.coinepro.hq.core.format.jTime
import com.coinepro.hq.core.format.usd
import com.coinepro.hq.core.net.FlowAutomation
import com.coinepro.hq.core.net.FlowGraph
import com.coinepro.hq.core.net.FlowGraphNode
import com.coinepro.hq.core.net.FlowRunRef
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.LineRun
import com.coinepro.hq.core.net.NodeState
import com.coinepro.hq.core.net.gated
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.LocalReducedMotion
import com.coinepro.hq.designsystem.ModelMark
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.ScrollRow
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.SpringSheet
import com.coinepro.hq.designsystem.Text
import com.coinepro.hq.designsystem.facts
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.designsystem.rememberBreath
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.playbook.StepWhat
import com.coinepro.hq.ui.rememberOnScreen
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v29.Para
import com.coinepro.hq.ui.v29.plain
import kotlinx.coroutines.delay

// Contract §59.7.1 ⟨1.38⟩: an automation's map, as n8n draws one (the owner: «که من به صورت گرافیکی ببینم روند کار رو، مثل خود n8n»).
// The lanes are faint bands, each with its doer's name; a node is a card with its doer's mark, its title and one line, a model chip on a
// workshop node; an edge is a curve with an arrow and its label. Right to left: the first step is on the right. Every node takes the chosen
// day's state (grey, lapis and breathing at work, amber with a clock, green with a tick, red, dashed when its hour had gone) and dots flow
// into the one at work. Pinch, drag, «همه در صفحه»; a tap opens the node's sheet. Nothing of a map is written here: it all comes from `graph`.

// ------------------------------------------------------------------------------------------- the day --
/** The days a map can show (the latest seven of `runs`, newest first and chosen), and the chosen one's run, read again every 15 s while live. */
@Stable
internal class MapDay(val days: List<FlowRunRef>, val ref: String?, val run: LineRun?, val states: Map<String, String>, val pick: (String) -> Unit) {
    val chosen: FlowRunRef? get() = days.firstOrNull { it.ref == ref }
}

@Composable
internal fun rememberMapDay(flowRef: String, runs: List<FlowRunRef>, onTick: () -> Unit): MapDay {
    var chosen by rememberSaveable(flowRef) { mutableStateOf<String?>(null) }
    val days = remember(runs) { runs.take(7) }
    val ref = chosen?.takeIf { c -> days.any { it.ref == c } } ?: days.firstOrNull()?.ref
    val q = rememberQuery("map-day:${ref ?: "-"}", "lines", "automations", maxAgeMs = 5_000) { ref?.let { lineRun(it) } }
    val run = q.data?.takeIf { it.ref == ref }
    val state = run?.state ?: days.firstOrNull { it.ref == ref }?.state
    val onScreen = rememberOnScreen()
    LaunchedEffect(ref, state, onScreen) { while (onScreen && ref != null && dayLive(state)) { delay(15_000); q.refresh(); onTick() } }
    val states = remember(run) { dayStates(run) }
    return MapDay(days, ref, run, states) { chosen = it }
}

/** The days as chips, and the chosen one in a line: its state, what it says, its cost, and its timeline. */
@Composable
internal fun MapDays(d: MapDay, onTimeline: (String) -> Unit) {
    val c = Divan.colors
    if (d.days.isEmpty()) {
        Text("هنوز روزی اجرا نشده؛ رنگ هر گره از اولین روز می‌آید.", style = Divan.type.caption, color = c.textMuted)
        return
    }
    Column(Modifier.fillMaxWidth().testTag("map-days"), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        ScrollRow { for (r in d.days) FilterChip(mapDayFa(r.at), r.ref == d.ref, { d.pick(r.ref) }) }
        val r = d.chosen ?: return@Column
        val state = d.run?.state ?: r.state
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Pill(flowDayStateFa(state), flowDayStateTone(state), live = state == "running", dot = state != "running")
            Text(
                remember(d.run, r) { facts((d.run?.noteFa ?: r.noteFa).ifBlank { null }, (d.run?.cost?.usd ?: r.costUsd)?.takeIf { it > 0.0 }?.let { usd(it) }) },
                style = Divan.type.caption, color = c.textSecondary, maxLines = 2, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f),
            )
            HqButton("خط زمان", { onTimeline(r.ref) }, variant = BtnVariant.TEXT, size = BtnSize.SM)
        }
    }
}

// ----------------------------------------------------------------------------------------- the canvas --
@Stable
private class MapView {
    var scale by mutableFloatStateOf(MapDims.START_SCALE)
    var pan by mutableStateOf(Pt(0f, 0f))
    var ready by mutableStateOf(false)
    var fitted by mutableStateOf(false)
}

/**
 * The canvas of [graph] coloured by [states] (a node with none is pending; no states at all: no colours). It looks first where the day is
 * now, and again when [focusOn] (the chosen day) changes or its states arrive; a live read does not move what the owner is looking at.
 */
@Composable
internal fun FlowCanvas(
    graph: FlowGraph,
    states: Map<String, String>,
    modifier: Modifier = Modifier,
    focusOn: Any? = null,
    onNode: (String) -> Unit,
    onFull: (() -> Unit)? = null,
) {
    val c = Divan.colors
    val density = LocalDensity.current.density
    val layout = remember(graph) { flowMapLayout(graph, rtl = true) }
    val v = remember(layout) { MapView() }
    var view by remember { mutableStateOf(IntSize.Zero) }
    val vw = view.width / density
    val vh = view.height / density
    val focus = remember(layout, states) { focusKey(layout, states) }
    LaunchedEffect(layout, focusOn, states.isNotEmpty(), view) {
        if (view == IntSize.Zero) return@LaunchedEffect
        v.scale = maxOf(MapDims.START_SCALE, fitScale(layout, vw, vh))
        v.pan = centreOn(layout, focus, v.scale, vw, vh)
        v.fitted = false
        v.ready = true
    }
    val shape = RoundedCornerShape(16.dp)
    Box(
        modifier
            .testTag("flow-map")
            .clip(shape)
            .background(c.page)
            .border(1.dp, c.lineHairline, shape)
            .onSizeChanged { view = it }
            .pointerInput(layout) {
                detectTransformGestures { centroid, delta, zoom, _ ->
                    if (!v.ready) return@detectTransformGestures
                    val w = size.width / density
                    val h = size.height / density
                    val next = (v.scale * zoom).coerceIn(MapDims.MIN_SCALE, MapDims.MAX_SCALE)
                    val z = zoomAbout(v.pan, v.scale, next, Pt(centroid.x / density, centroid.y / density))
                    v.pan = clampPan(Pt(z.x + delta.x / density, z.y + delta.y / density), next, layout, w, h)
                    v.scale = next
                    v.fitted = false
                }
            },
    ) {
        if (v.ready) {
            World(layout, states, v, onNode)
            // each band's name stays on the view's right edge (where the canvas starts), at the band's top, as the canvas moves
            for (b in layout.lanes) LaneChip(
                b.key,
                Modifier.align(AbsoluteAlignment.TopRight)
                    // a band thinner than its name (the whole canvas on the view) leaves it out, rather than piling the names up
                    .graphicsLayer { alpha = if (b.height * v.scale < 30f) 0f else 1f }
                    .absoluteOffset {
                        val top = v.pan.y + b.top * v.scale
                        val y = maxOf(top + 4f, 4f).coerceAtMost(top + b.height * v.scale - 26f)
                        IntOffset((-6).dp.roundToPx(), y.dp.roundToPx())
                    },
            )
        }
        Row(Modifier.align(Alignment.BottomEnd).padding(8.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            MapChip(if (v.fitted) "نزدیک" else "همه در صفحه", if (v.fitted) DivanIcon.SEARCH else DivanIcon.SCOPE) {
                if (v.fitted) {
                    v.scale = MapDims.START_SCALE
                    v.pan = centreOn(layout, focus, v.scale, vw, vh)
                    v.fitted = false
                } else {
                    v.scale = fitScale(layout, vw, vh)
                    v.pan = clampPan(Pt(0f, 0f), v.scale, layout, vw, vh)
                    v.fitted = true
                }
            }
            if (onFull != null) MapChip("تمام‌صفحه", DivanIcon.NEXT, onFull)
        }
    }
}

/** The canvas at its own size, scaled and moved in its layer only (a pinch redraws, it does not recompose). */
@Composable
private fun World(l: FlowMapLayout, states: Map<String, String>, v: MapView, onNode: (String) -> Unit) {
    val c = Divan.colors
    val working = states.values.any { it == "running" }
    val reduced = LocalReducedMotion.current
    val flow: State<Float> =
        if (working && !reduced) rememberInfiniteTransition(label = "map-flow").animateFloat(0f, 1f, infiniteRepeatable(tween(1400, easing = LinearEasing)), label = "map-flow")
        else remember { mutableFloatStateOf(0.3f) }
    val breath = rememberBreath(working, periodMs = 1600)
    Box(
        Modifier
            .layout { m, cons ->
                val p = m.measure(Constraints.fixed(l.width.dp.roundToPx(), l.height.dp.roundToPx()))
                layout(cons.maxWidth, cons.maxHeight) { p.place(0, 0) }
            }
            .graphicsLayer {
                transformOrigin = TransformOrigin(0f, 0f)
                scaleX = v.scale
                scaleY = v.scale
                translationX = v.pan.x.dp.toPx()
                translationY = v.pan.y.dp.toPx()
            },
        // the canvas is in absolute places (its right-to-left is in the layout's columns): children from its top left, never its start
        contentAlignment = AbsoluteAlignment.TopLeft,
    ) {
        val lane = c.tile
        val ink = MapInk(c.positive, c.lapis, c.warning, c.negative, c.lineStrong)
        Canvas(Modifier.fillMaxSize()) {
            val d = density
            for (b in l.lanes) drawRoundRect(lane, Offset(MapDims.MARGIN / 2f * d, b.top * d), Size((l.width - MapDims.MARGIN) * d, b.height * d), CornerRadius(14.dp.toPx()))
            for (e in l.edges) {
                val ts = states[e.edge.target]
                val col = ink.edge(ts)
                val path = Path().apply {
                    moveTo(e.from.x * d, e.from.y * d)
                    cubicTo(e.c1.x * d, e.c1.y * d, e.c2.x * d, e.c2.y * d, e.land.x * d, e.land.y * d)
                    lineTo(e.to.x * d, e.to.y * d)
                }
                drawPath(
                    path, col,
                    style = Stroke(
                        width = (if (ts == "running") 2.2f else 1.6f).dp.toPx(), cap = StrokeCap.Round,
                        pathEffect = if (ts == "skipped") PathEffect.dashPathEffect(floatArrayOf(6.dp.toPx(), 5.dp.toPx())) else null,
                    ),
                )
                arrow(e.to.x * d, e.to.y * d, e.arrowDir, col)
                if (ts == "running") for (i in 0 until 3) {
                    val p = e.at((flow.value + i / 3f) % 1f)
                    drawCircle(ink.running, radius = 3.dp.toPx(), center = Offset(p.x * d, p.y * d))
                }
            }
        }
        for (e in l.edges) {
            val label = e.edge.labelFa.takeIf { it.isNotBlank() } ?: continue
            // just above the edge's level run, beside its own target
            val p = e.label
            val w = MapDims.LAND - 4f
            Box(Modifier.absoluteOffset((p.x - w / 2f).dp, (p.y - 33f).dp).size(w.dp, 30.dp), contentAlignment = Alignment.BottomCenter) {
                Text(
                    plain(label), style = Divan.type.micro, color = c.textSecondary, maxLines = 2, overflow = TextOverflow.Ellipsis, textAlign = TextAlign.Center,
                    modifier = Modifier.clip(RoundedCornerShape(6.dp)).background(c.page).padding(horizontal = 3.dp),
                )
            }
        }
        for (b in l.nodes) MapNode(b, if (states.isEmpty()) null else states[b.node.key] ?: NODE_PENDING, breath) { onNode(b.node.key) }
    }
}

/** The state colours of the map, read once from the theme. */
private class MapInk(val done: Color, val running: Color, val waiting: Color, val failed: Color, val idle: Color) {
    fun edge(target: String?): Color = when (target) {
        "running" -> running
        "done" -> done.copy(alpha = 0.6f)
        "waiting" -> waiting.copy(alpha = 0.75f)
        "failed" -> failed.copy(alpha = 0.7f)
        else -> idle
    }
}

private fun DrawScope.arrow(x: Float, y: Float, dir: Float, color: Color) {
    val a = 8.dp.toPx()
    val w = 4.5.dp.toPx()
    drawPath(Path().apply { moveTo(x, y); lineTo(x - dir * a, y - w); lineTo(x - dir * a, y + w); close() }, color)
}

/** A band's name: its doer's mark and name, small, on the view's edge. */
@Composable
private fun LaneChip(lane: String, modifier: Modifier) {
    val c = Divan.colors
    Row(
        modifier.testTag("lane-chip").clip(RoundedCornerShape(10.dp)).background(c.raised.copy(alpha = 0.94f)).border(1.dp, c.lineHairline, RoundedCornerShape(10.dp))
            .padding(start = 4.dp, end = 8.dp, top = 2.dp, bottom = 2.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(5.dp),
    ) {
        Mark(laneProvider(lane), laneIcon(lane), 18.dp)
        Text(plain(laneFa(lane)), style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary, maxLines = 1)
    }
}

/** One step: its doer's mark, its title and one line, a model chip on a workshop node, its state in the corner. */
@Composable
private fun MapNode(b: NodeBox, state: String?, breath: State<Float>, onClick: () -> Unit) {
    val c = Divan.colors
    val n = b.node
    val shape = RoundedCornerShape(14.dp)
    val line = when (state) { "done" -> c.positive; "running" -> c.lapis; "waiting" -> c.warning; "failed" -> c.negative; else -> c.lineStrong }
    val faint = state == "skipped"
    val glow = c.lapis
    Box(Modifier.absoluteOffset(b.x.dp, b.y.dp).size(b.w.dp, b.h.dp).testTag("map-node")) {
        Box(
            Modifier
                .fillMaxSize()
                .drawBehind {
                    if (state == "running") drawRoundRect(glow.copy(alpha = 0.18f + 0.32f * breath.value), Offset(-4.dp.toPx(), -4.dp.toPx()), Size(size.width + 8.dp.toPx(), size.height + 8.dp.toPx()), CornerRadius(18.dp.toPx()), style = Stroke(4.dp.toPx()))
                }
                .clip(shape)
                .background(if (state == "failed") c.softNegative else c.card)
                .drawBehind {
                    val s = 1.5.dp.toPx()
                    drawRoundRect(
                        line, Offset(s / 2, s / 2), Size(size.width - s, size.height - s), CornerRadius(14.dp.toPx() - s / 2),
                        style = Stroke(s, pathEffect = if (faint) PathEffect.dashPathEffect(floatArrayOf(5.dp.toPx(), 4.dp.toPx())) else null),
                    )
                }
                .clickable(role = Role.Button, onClickLabel = "باز کن", onClick = onClick)
                .padding(horizontal = 10.dp, vertical = 8.dp),
        ) {
            Row(Modifier.fillMaxSize(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Mark(nodeProvider(n), nodeIcon(n), 30.dp)
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    Text(plain(n.titleFa.ifBlank { n.key }), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = if (faint) c.textMuted else c.textPrimary, maxLines = 2, overflow = TextOverflow.Ellipsis)
                    if (n.noteFa.isNotBlank()) Text(plain(n.noteFa), style = Divan.type.caption, color = c.textMuted, maxLines = 1, overflow = TextOverflow.Ellipsis)
                }
            }
        }
        StateBadge(state, breath, 20.dp, Modifier.align(Alignment.TopStart).offset(x = (-7).dp, y = (-7).dp))
        modelFa(n.model)?.let { m ->
            Row(
                Modifier.align(Alignment.TopEnd).offset(x = (-12).dp, y = (-9).dp).clip(CircleShape).background(c.raised).border(1.dp, c.lineStrong, CircleShape)
                    .padding(horizontal = 6.dp, vertical = 1.dp),
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp),
            ) {
                ModelMark(n.model, provider = "anthropic".takeIf { n.model?.startsWith("claude") == true }, size = 10.dp)
                Text(m, style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary, maxLines = 1)
            }
        }
    }
}

/** A state's mark: a tick on green, lapis breathing, a clock on amber, «!» on red, a dash for one whose hour had gone, a ring for pending. */
@Composable
private fun StateBadge(state: String?, breath: State<Float>, size: Dp, modifier: Modifier = Modifier) {
    val c = Divan.colors
    if (state == null) return
    val fill = when (state) { "done" -> c.positive; "running" -> c.lapis; "waiting" -> c.warning; "failed" -> c.negative; "skipped" -> c.textMuted; else -> c.page }
    val glyph = c.page
    val ring = c.lineStrong
    Canvas(modifier.size(size).testTag("state-$state")) {
        val r = this.size.minDimension / 2f
        val o = center
        val alpha = if (state == "running") 1f - 0.45f * breath.value else 1f
        drawCircle(glyph, r, o)
        if (state == NODE_PENDING) drawCircle(ring, r - 2.dp.toPx(), o, style = Stroke(1.5.dp.toPx()))
        else drawCircle(fill.copy(alpha = alpha), r - 2.dp.toPx(), o)
        val s = Stroke(1.7.dp.toPx(), cap = StrokeCap.Round)
        val u = r / 2.2f
        when (state) {
            "done" -> drawPath(Path().apply { moveTo(o.x - u, o.y); lineTo(o.x - u * 0.25f, o.y + u * 0.7f); lineTo(o.x + u, o.y - u * 0.6f) }, glyph, style = s)
            "waiting" -> {
                drawCircle(glyph, u * 1.05f, o, style = Stroke(1.3.dp.toPx()))
                drawLine(glyph, o, Offset(o.x, o.y - u * 0.7f), 1.3.dp.toPx(), StrokeCap.Round)
                drawLine(glyph, o, Offset(o.x + u * 0.55f, o.y), 1.3.dp.toPx(), StrokeCap.Round)
            }
            "failed" -> {
                drawLine(glyph, Offset(o.x, o.y - u * 0.8f), Offset(o.x, o.y + u * 0.2f), 1.8.dp.toPx(), StrokeCap.Round)
                drawCircle(glyph, 1.1.dp.toPx(), Offset(o.x, o.y + u * 0.75f))
            }
            "skipped" -> drawLine(glyph, Offset(o.x - u * 0.7f, o.y), Offset(o.x + u * 0.7f, o.y), 1.8.dp.toPx(), StrokeCap.Round)
            "running" -> drawCircle(glyph, u * 0.45f, o)
        }
    }
}

@Composable
private fun Mark(provider: String?, icon: DivanIcon, size: Dp) {
    val c = Divan.colors
    Box(Modifier.size(size).clip(CircleShape).background(c.tile), contentAlignment = Alignment.Center) {
        if (provider != null) ModelMark(null, provider = provider, size = size * 0.52f)
        else DIcon(icon, size = size * 0.52f, tint = c.silverInk)
    }
}

/** Whose logo a node carries: ChatGPT's, Google's (Gemini, AI Studio), Claude's for the workshop's model; else the app's own mark. */
private fun nodeProvider(n: FlowGraphNode): String? = when {
    n.helper == "gpt" -> "openai"
    n.helper == "gemini" || n.helper == "aistudio" -> "google"
    n.model?.startsWith("claude") == true || n.helper == "workshop" -> "anthropic"
    else -> null
}

private fun nodeIcon(n: FlowGraphNode): DivanIcon = when {
    n.kind == "n8n" || n.lane == "n8n" -> DivanIcon.TIME
    n.kind == "order" -> DivanIcon.COMMAND
    n.kind == "package" -> DivanIcon.DELIVERABLE
    n.kind == "report" -> DivanIcon.BELL
    n.lane == "voice" -> DivanIcon.MIC
    n.lane == "ighub" || n.helper == "ighub" -> DivanIcon.SEND
    n.lane == "hub" -> DivanIcon.HOLDING
    else -> DivanIcon.CODE
}

private fun laneProvider(lane: String): String? = when (lane) { "workshop" -> "anthropic"; "chatgpt" -> "openai"; "gemini" -> "google"; else -> null }

private fun laneIcon(lane: String): DivanIcon = when (lane) {
    "n8n" -> DivanIcon.TIME
    "hub" -> DivanIcon.HOLDING
    "voice" -> DivanIcon.MIC
    "ighub" -> DivanIcon.SEND
    else -> DivanIcon.SETTINGS
}

@Composable
private fun MapChip(text: String, icon: DivanIcon, onClick: () -> Unit) {
    val c = Divan.colors
    Row(
        Modifier.clip(CircleShape).background(c.raised).border(1.dp, c.lineStrong, CircleShape).clickable(role = Role.Button, onClick = onClick)
            .padding(horizontal = 10.dp, vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(5.dp),
    ) {
        DIcon(icon, size = 14.dp, tint = c.textSecondary)
        Text(text, style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
    }
}

/** The states on the canvas that day, each with its mark and its name. */
@Composable
internal fun MapLegend(nodes: List<FlowGraphNode>, states: Map<String, String>) {
    val c = Divan.colors
    val shown = remember(nodes, states) { legendOf(nodes, states) }
    if (shown.isEmpty()) return
    val still = remember { mutableFloatStateOf(0f) }
    FlowRow(Modifier.fillMaxWidth().testTag("map-legend"), horizontalArrangement = Arrangement.spacedBy(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        for (s in shown) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(5.dp)) {
            StateBadge(s, still, 14.dp)
            Text(nodeStateFa(s), style = Divan.type.micro, color = c.textSecondary)
        }
    }
}

// --------------------------------------------------------------------------------------- the node sheet --
/** A node opened: what it does (its step), that day (state, start and end, minutes, model, why it did not), its files, the day's timeline. */
@Composable
internal fun NodeSheet(f: FlowAutomation, key: String, run: LineRun?, onDismiss: () -> Unit, onTimeline: (String) -> Unit) {
    val (title, sub) = nodeHead(f, key, run)
    SpringSheet(onDismiss, title, sub = sub) { NodeSheetBody(f, key, run, onTimeline) }
}

/** The sheet's title (the node's) and its line: who does it, with what, on which model. */
internal fun nodeHead(f: FlowAutomation, key: String, run: LineRun?): Pair<String, String?> {
    val node = f.graph?.nodes?.firstOrNull { it.key == key }
    val step = f.steps.firstOrNull { it.key == key }
    val sr = run?.steps?.firstOrNull { it.key == key }
    val title = node?.titleFa?.ifBlank { null } ?: step?.titleFa?.ifBlank { null } ?: sr?.titleFa?.ifBlank { null } ?: key
    val model = sr?.model ?: node?.model ?: step?.model
    val who = node?.lane?.let(::laneFa)
    // the doer once: «کارگاه Claude», not «کارگاه Claude، کارگاه»; the model is in the sheet (its figures stay Latin there)
    val helper = helperFa(sr?.helper ?: node?.helper ?: step?.helper)?.takeIf { h -> h != "کد هاب" && who?.contains(h) != true }
    return title to facts(who, helper).text.ifBlank { null }
}

@Composable
internal fun NodeSheetBody(f: FlowAutomation, key: String, run: LineRun?, onTimeline: (String) -> Unit) {
    val c = Divan.colors
    val node = f.graph?.nodes?.firstOrNull { it.key == key }
    val step = f.steps.firstOrNull { it.key == key }
    val sr = run?.steps?.firstOrNull { it.key == key }
    val model = sr?.model ?: node?.model ?: step?.model
    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        modelFa(model)?.let { m ->
            Row(Modifier.testTag("node-model"), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                ModelMark(model, size = 14.dp)
                Text(facts(m, com.coinepro.hq.core.data.effortFa(sr?.effort ?: step?.effort)), style = Divan.type.caption, color = c.textSecondary)
            }
        }
        if (run != null) {
            val state = sr?.state ?: NODE_PENDING
            Column(
                Modifier.fillMaxWidth().testTag("node-day").clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp),
                verticalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Pill(nodeStateFa(state), nodeStateTone(state), live = state == "running", dot = state != "running")
                    Text(mapDayFa(run.at), style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
                }
                val minutes = minutesBetween(sr?.startedAt, sr?.endedAt)
                val line = facts(
                    sr?.startedAt?.let { "شروع ${jTime(it)}" }, sr?.endedAt?.takeIf { it != sr.startedAt }?.let { "پایان ${jTime(it)}" },
                    minutes?.let { if (it < 1) "کمتر از یک دقیقه" else "${faNum(it)} دقیقه" }, sr?.costUsd?.takeIf { it > 0.0 }?.let { usd(it) },
                )
                if (line.isNotEmpty()) Text(line, style = Divan.type.caption, color = c.textSecondary)
                sr?.errorFa?.takeIf { it.isNotBlank() }?.let { Text(plain(it), style = Divan.type.caption, color = c.negative, modifier = Modifier.testTag("node-error")) }
            }
        }
        Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("چه میکند", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textMuted)
            if (step != null && (step.inputFa.isNotBlank() || step.outputFa.isNotBlank() || step.rulesFa.isNotEmpty())) StepWhat(step)
            else Para(node?.noteFa?.ifBlank { null } ?: "همین قدم روند.", style = Divan.type.caption, color = c.textSecondary)
        }
        if (sr != null && sr.outputs.isNotEmpty()) Column(Modifier.testTag("node-files"), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("فایل‌های همین روز", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textMuted)
            StepOutputs(sr, legacyText = false)
        }
        if (run != null) HqButton("خط زمان همین روز", { onTimeline(run.ref) }, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.TIME)
    }
}

// ---------------------------------------------------------------------------------------- full screen --
/** The map alone, as big as the screen: the days above, the canvas filling the rest, the legend under it. */
@Composable
fun FlowMapScreen(ref: String) {
    val nav = LocalNav.current
    val c = Divan.colors
    val q = rememberFlow(ref)
    val runs = rememberQuery("flow-runs:$ref", "automations", maxAgeMs = 15_000) { gated(HubFeature.AUTOMATIONS) { flowRuns(ref) } }
    val f = q.data
    var node by rememberSaveable { mutableStateOf<String?>(null) }
    val day = rememberMapDay(ref, runs.data?.items.orEmpty()) { runs.refresh() }
    Column(Modifier.fillMaxSize().padding(horizontal = 16.dp, vertical = 12.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        PageHeader(f?.titleFa?.ifBlank { null } ?: "نقشه", eyebrow = f?.let { facts("نقشه‌ی روند", it.companyFa.ifBlank { null }).text } ?: "نقشه‌ی روند")
        val g = f?.graph
        when {
            f == null && q.error != null -> ErrorBlock(q.error, { q.refresh() })
            f == null -> Skeleton(Modifier.fillMaxWidth().weight(1f), radius = 16.dp)
            g == null -> Empty("این اتوماسیون نقشه ندارد؛ قدم‌هایش در صفحه‌ی خودش است.", icon = DivanIcon.SETTINGS)
            else -> {
                MapDays(day) { nav.go("flow-run/$it") }
                FlowCanvas(g, day.states, Modifier.fillMaxWidth().weight(1f), focusOn = day.ref, onNode = { node = it })
                MapLegend(g.nodes, day.states)
            }
        }
    }
    val k = node
    if (f != null && k != null) NodeSheet(f, k, day.run, { node = null }) { node = null; nav.go("flow-run/$it") }
}

// ------------------------------------------------------------------------------------- the board's strip --
/** Under an n8n card (§59.10 `last.steps`, when the hub sends it): the last day's nodes as a thin strip of their colours. */
@Composable
internal fun NodeStrip(steps: List<NodeState>, modifier: Modifier = Modifier) {
    val c = Divan.colors
    if (steps.isEmpty()) return
    val ink = MapInk(c.positive, c.lapis, c.warning, c.negative, c.lineStrong)
    val muted = c.textMuted
    Canvas(modifier.fillMaxWidth().height(4.dp).testTag("node-strip")) {
        val gap = 2.dp.toPx()
        val w = (size.width - gap * (steps.size - 1)) / steps.size
        val rtl = layoutDirection == androidx.compose.ui.unit.LayoutDirection.Rtl
        steps.forEachIndexed { i, s ->
            val x = if (rtl) size.width - (i + 1) * w - i * gap else i * (w + gap)
            val col = when (s.state) { "done" -> ink.done; "running" -> ink.running; "waiting" -> ink.waiting; "failed" -> ink.failed; "skipped" -> muted.copy(alpha = 0.45f); else -> ink.idle }
            drawRoundRect(col, Offset(x, 0f), Size(w, size.height), CornerRadius(size.height / 2f))
        }
    }
}
