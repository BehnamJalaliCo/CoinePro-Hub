package com.coinepro.hq.ui.office

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.absoluteOffset
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import com.coinepro.hq.designsystem.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.AbsoluteAlignment
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.LINK_KIND_FA
import com.coinepro.hq.core.data.LINK_KIND_HINT_FA
import com.coinepro.hq.core.data.Spot
import com.coinepro.hq.core.data.canLink
import com.coinepro.hq.core.data.clampSpot
import com.coinepro.hq.core.data.layoutCanvas
import com.coinepro.hq.core.data.linkAt
import com.coinepro.hq.core.data.linkKindFa
import com.coinepro.hq.core.data.linkTone
import com.coinepro.hq.core.data.nodeAt
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.Canvas as HubCanvas
import com.coinepro.hq.core.net.CanvasNode
import com.coinepro.hq.core.net.CompanyLink
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.CompanyMark
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.HqSwitch
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.Monogram
import com.coinepro.hq.designsystem.ScrollRow
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.designsystem.toneColors
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.v29.plain
import kotlin.math.roundToInt
import kotlinx.coroutines.launch

// Contract §35.6 ⟨1.17⟩: the canvas («بوم») of the owner's office. The hub sits in the centre and the companies around it (where the
// owner put them, else on a circle); every company is linked to the hub (the quiet dotted lines), and the owner shapes the links between
// companies: a line in its kind's colour (service, publishing, data, sales, support), dashed when turned off, with its open works on it.
// Tap a company: its state. Drag one company onto another: a new link. Drag it to an empty place: it stays there (saved on the hub).
// Tap a line: change it or turn it off. Nothing is ever deleted.

private sealed interface CanvasSheet {
    data object None : CanvasSheet
    data class Company(val code: String) : CanvasSheet
    data class NewLink(val from: String?, val to: String?) : CanvasSheet
    data class EditLink(val link: CompanyLink) : CanvasSheet
}

private val NODE = 52.dp
private val LABEL_W = 88.dp

@Composable
fun CanvasCard(canvas: HubCanvas, editable: Boolean, modifier: Modifier = Modifier) {
    val env = LocalEnv.current
    val c = Divan.colors
    val scope = rememberCoroutineScope()
    val toasts = LocalToasts.current
    val density = LocalDensity.current
    // A node moved here stays where it was put until the hub's canvas comes back with it.
    val moved = remember { mutableStateMapOf<String, Spot>() }
    var dragging by remember { mutableStateOf<String?>(null) }
    var dragAt by remember { mutableStateOf<Spot?>(null) }
    var sheet by remember { mutableStateOf<CanvasSheet>(CanvasSheet.None) }
    val base = remember(canvas.nodes) { layoutCanvas(canvas.nodes) }
    val spots = base + moved
    val spotsNow by rememberUpdatedState(spots)
    val holding = canvas.nodes.firstOrNull { it.kind == "holding" }

    HqCard(modifier.fillMaxWidth()) {
        SectionTitle("بوم شرکت‌ها", note = if (editable) "لمس: وضع شرکت · کشیدن روی دیگری: پیوند تازه" else "هلدینگ و شرکت‌هایش", icon = DivanIcon.HOLDING) {
            if (editable) HqButton("پیوند", { sheet = CanvasSheet.NewLink(null, null) }, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.ADD)
        }
        BoxWithConstraints(Modifier.fillMaxWidth().aspectRatio(1f).padding(top = 8.dp).clip(RoundedCornerShape(16.dp)).background(c.tile)) {
            val w = constraints.maxWidth.toFloat().coerceAtLeast(1f)
            val h = constraints.maxHeight.toFloat().coerceAtLeast(1f)
            val divider = c.lineDivider
            val gold = c.goldFill
            val inks = LINK_KIND_FA.keys.associateWith { linkInk(it, true) }
            val links = canvas.links
            Canvas(
                Modifier.fillMaxSize().pointerInput(links, editable) {
                    detectTapGestures { p -> linkAt(spotsNow, links, p.x / w, p.y / h)?.let { if (editable) sheet = CanvasSheet.EditLink(it) } }
                },
            ) {
                fun at(s: Spot) = Offset(s.x * size.width, s.y * size.height)
                val hub = holding?.let { spots[it.code] }
                // Every company to the hub, implicitly: quiet and dotted.
                if (hub != null) for (n in canvas.nodes) if (n.kind != "holding") spots[n.code]?.let { s ->
                    drawLine(divider, at(hub), at(s), strokeWidth = 1.dp.toPx(), pathEffect = PathEffect.dashPathEffect(floatArrayOf(3.dp.toPx(), 5.dp.toPx())))
                }
                for (l in links) {
                    val a = spots[l.from] ?: continue
                    val b = spots[l.to] ?: continue
                    val on = l.state == "on"
                    val ink = (inks[l.kind] ?: divider).let { if (on) it else it.copy(alpha = 0.4f) }
                    drawLine(ink, at(a), at(b), strokeWidth = (if (on) 3 else 2).dp.toPx(), cap = StrokeCap.Round, pathEffect = if (on) null else PathEffect.dashPathEffect(floatArrayOf(6.dp.toPx(), 5.dp.toPx())))
                    // The direction: a dot two thirds of the way, towards the company it reaches.
                    val t = 0.68f
                    drawCircle(ink, 4.dp.toPx(), Offset(at(a).x + (at(b).x - at(a).x) * t, at(a).y + (at(b).y - at(a).y) * t))
                }
                val from = dragging
                val to = dragAt
                if (from != null && to != null) spots[from]?.let { s ->
                    drawLine(gold, at(s), at(to), strokeWidth = 2.dp.toPx(), pathEffect = PathEffect.dashPathEffect(floatArrayOf(6.dp.toPx(), 4.dp.toPx())))
                }
            }
            // The open works along each link, on its middle.
            for (l in links) {
                if (l.openWorks <= 0) continue
                val a = spots[l.from] ?: continue
                val b = spots[l.to] ?: continue
                val mx = (a.x + b.x) / 2 * w
                val my = (a.y + b.y) / 2 * h
                with(density) {
                    Text(
                        "${l.openWorks} کار", style = Divan.type.micro, color = c.textPrimary,
                        // Placed from the canvas's left edge whatever the reading direction (the lines are drawn that way too).
                        modifier = Modifier.align(AbsoluteAlignment.TopLeft).absoluteOffset { IntOffset((mx - 22.dp.toPx()).roundToInt(), (my - 9.dp.toPx()).roundToInt()) }
                            .clip(CircleShape).background(c.card).padding(horizontal = 7.dp, vertical = 2.dp),
                    )
                }
            }
            for (n in canvas.nodes) {
                val home = spots[n.code] ?: continue
                // The node follows the finger; the gold dashed line runs from where it was.
                val shown = if (dragging == n.code) dragAt ?: home else home
                val half = with(density) { (LABEL_W / 2).toPx() }
                val top = with(density) { (NODE / 2).toPx() }
                NodeView(
                    n, lifted = dragging == n.code,
                    modifier = Modifier
                        .align(AbsoluteAlignment.TopLeft)
                        .absoluteOffset { IntOffset((shown.x * w - half).roundToInt(), (shown.y * h - top).roundToInt()) }
                        .pointerInput(n.code) { detectTapGestures(onTap = { sheet = CanvasSheet.Company(n.code) }) }
                        .pointerInput(n.code, editable) {
                            if (!editable) return@pointerInput
                            detectDragGestures(
                                onDragStart = { dragging = n.code; dragAt = spotsNow[n.code] },
                                onDragEnd = {
                                    val end = dragAt
                                    val code = dragging
                                    dragging = null; dragAt = null
                                    if (end == null || code == null) return@detectDragGestures
                                    val target = nodeAt(spotsNow - code, end.x, end.y)
                                    val targetNode = canvas.nodes.firstOrNull { it.code == target }
                                    when {
                                        // Onto another company: a new link between the two (the hub's own link is already there).
                                        target != null && targetNode?.kind != "holding" && n.kind != "holding" -> sheet = CanvasSheet.NewLink(code, target)
                                        target != null -> Unit
                                        else -> {
                                            val p = clampSpot(end.x, end.y)
                                            moved[code] = p
                                            scope.launch {
                                                try { env.api.putCanvasNode(code, p.x.toDouble(), p.y.toDouble()) } catch (e: ApiException) { toasts.error(e.messageFa) }
                                            }
                                        }
                                    }
                                },
                                onDragCancel = { dragging = null; dragAt = null },
                                onDrag = { change, amount ->
                                    change.consume()
                                    val now = dragAt ?: return@detectDragGestures
                                    dragAt = Spot(now.x + amount.x / w, now.y + amount.y / h)
                                },
                            )
                        },
                )
            }
        }
        // The kinds of link, in their colours.
        FlowRow(Modifier.padding(top = 10.dp), horizontalArrangement = Arrangement.spacedBy(10.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            for ((k, fa) in LINK_KIND_FA) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                Box(Modifier.size(width = 14.dp, height = 3.dp).clip(CircleShape).background(linkInk(k, true)))
                Text(fa, style = Divan.type.micro, color = c.textSecondary)
            }
        }
    }

    when (val s = sheet) {
        CanvasSheet.None -> Unit
        is CanvasSheet.Company -> CompanySheet(canvas, s.code, editable, onLink = { sheet = it }, onDismiss = { sheet = CanvasSheet.None })
        is CanvasSheet.NewLink -> NewLinkSheet(canvas, s.from, s.to, onDismiss = { sheet = CanvasSheet.None })
        is CanvasSheet.EditLink -> EditLinkSheet(canvas, s.link, onDismiss = { sheet = CanvasSheet.None })
    }
}

@Composable
private fun linkInk(kind: String, on: Boolean): androidx.compose.ui.graphics.Color {
    val ink = toneColors(linkTone(kind)).second
    return if (on) ink else ink.copy(alpha = 0.4f)
}

/** A company (or the hub) on the canvas: its mark in a disc, its open sessions, its name. */
@Composable
private fun NodeView(n: CanvasNode, lifted: Boolean, modifier: Modifier) {
    val c = Divan.colors
    val hub = n.kind == "holding"
    Column(modifier.width(LABEL_W).semantics(mergeDescendants = true) { contentDescription = n.nameFa.ifBlank { n.code } }, horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(3.dp)) {
        Box {
            Box(
                Modifier.size(if (hub) NODE + 8.dp else NODE).clip(CircleShape).background(if (hub) c.softGold else c.card)
                    .border(if (lifted) 2.dp else 1.dp, if (hub || lifted) c.lineTahrir else c.lineStrong, CircleShape),
                contentAlignment = Alignment.Center,
            ) {
                if (hub) Monogram(30.dp) else CompanyMark(n.code, height = 18.dp, mono = true, ink = c.textPrimary)
            }
            if (n.openSessions > 0) Text(
                "${n.openSessions}", style = Divan.type.micro.copy(fontWeight = FontWeight.Bold), color = c.onGold,
                modifier = Modifier.align(Alignment.TopEnd).clip(CircleShape).background(c.goldFill).padding(horizontal = 6.dp),
            )
        }
        Text(n.nameFa.ifBlank { n.code }, style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, maxLines = 1, overflow = TextOverflow.Ellipsis, textAlign = TextAlign.Center)
    }
}

private fun nameOf(canvas: HubCanvas, code: String?): String = canvas.nodes.firstOrNull { it.code == code }?.nameFa?.ifBlank { null } ?: code.orEmpty()

// ---------------------------------------------------------------- sheets --
/** A company's state: its line, its open sessions and its links; the way to its page, and a new link from it. */
@Composable
private fun CompanySheet(canvas: HubCanvas, code: String, editable: Boolean, onLink: (CanvasSheet) -> Unit, onDismiss: () -> Unit) {
    val nav = LocalNav.current
    val c = Divan.colors
    val n = canvas.nodes.firstOrNull { it.code == code } ?: return
    val mine = canvas.links.filter { it.from == code || it.to == code }
    com.coinepro.hq.ui.v14.HqSheet(onDismiss, n.nameFa.ifBlank { code }, sub = n.lineFa.ifBlank { null }) {
        Text(if (n.openSessions > 0) "${n.openSessions} جلسه‌ی باز" else "جلسه‌ی بازی ندارد", style = Divan.type.small, color = c.textSecondary)
        if (n.kind != "holding") {
            Text("پیوندها", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textMuted)
            if (mine.isEmpty()) Text("جز هاب به جایی وصل نیست.", style = Divan.type.caption, color = c.textMuted)
            Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(c.card)) {
                mine.forEachIndexed { i, l ->
                    if (i > 0) HorizontalDivider(color = c.lineDivider)
                    LinkRow(canvas, l) { if (editable) onLink(CanvasSheet.EditLink(l)) }
                }
            }
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            HqButton("صفحه‌ی شرکت", { onDismiss(); nav.go("companies/$code") }, Modifier.weight(1f), icon = DivanIcon.COMPANIES)
            if (editable && n.kind != "holding") HqButton("پیوند تازه", { onLink(CanvasSheet.NewLink(code, null)) }, Modifier.weight(1f), variant = BtnVariant.PRIMARY, icon = DivanIcon.ADD)
        }
    }
}

@Composable
private fun LinkRow(canvas: HubCanvas, l: CompanyLink, onClick: () -> Unit) {
    val c = Divan.colors
    Row(
        Modifier.fillMaxWidth().clickable(role = Role.Button, onClick = onClick).padding(12.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Box(Modifier.size(width = 16.dp, height = 4.dp).clip(CircleShape).background(linkInk(l.kind, l.state == "on")))
        Column(Modifier.weight(1f)) {
            Text(plain("${nameOf(canvas, l.from)} ← ${nameOf(canvas, l.to)}: ${linkKindFa(l.kind)}"), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
            if (l.purposeFa.isNotBlank()) Text(plain(l.purposeFa), style = Divan.type.micro, color = c.textMuted, maxLines = 2)
        }
        Text(if (l.state == "on") (if (l.openWorks > 0) "${l.openWorks} کار" else "روشن") else "خاموش", style = Divan.type.micro, color = if (l.state == "on") c.textSecondary else c.textMuted)
    }
}

/** A new link: from which company to which, its kind and one sentence on what it is for. */
@Composable
private fun NewLinkSheet(canvas: HubCanvas, from0: String?, to0: String?, onDismiss: () -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val action = rememberAction()
    val companies = canvas.nodes.filter { it.kind != "holding" }
    var from by rememberSaveable { mutableStateOf(from0) }
    var to by rememberSaveable { mutableStateOf(to0) }
    var kind by rememberSaveable { mutableStateOf("serves") }
    var purpose by rememberSaveable { mutableStateOf("") }
    com.coinepro.hq.ui.v14.HqSheet(onDismiss, "پیوند تازه", sub = "هر شرکت خودش به هاب وصل است؛ این پیوند دو شرکت را به هم وصل میکند.") {
        Text("از", style = Divan.type.caption, color = c.textMuted)
        ScrollRow { for (n in companies) FilterChip(n.nameFa.ifBlank { n.code }, from == n.code, { from = n.code }) }
        Text("به", style = Divan.type.caption, color = c.textMuted)
        ScrollRow { for (n in companies.filter { it.code != from }) FilterChip(n.nameFa.ifBlank { n.code }, to == n.code, { to = n.code }) }
        Text("نوع پیوند", style = Divan.type.caption, color = c.textMuted)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            for ((k, fa) in LINK_KIND_FA) FilterChip(fa, kind == k, { kind = k })
        }
        LINK_KIND_HINT_FA[kind]?.let { Text(it, style = Divan.type.micro, color = c.textSecondary) }
        HqTextField(purpose, { purpose = it }, "برای چه؟ یک جمله", Modifier.fillMaxWidth(), singleLine = false, minLines = 2, maxLength = 300)
        val ok = canLink(from, to, canvas.links, kind)
        if (!ok && from != null && to != null && from != to) Text("این پیوند همین حالا روشن است.", style = Divan.type.micro, color = c.warning)
        HqButton("وصل کن", {
            action.run {
                env.api.newLink(from!!, to!!, kind, purpose.trim())
                env.cache.invalidate("office", "links")
                toasts.ok("پیوند ساخته شد.")
                onDismiss()
            }
        }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, icon = DivanIcon.DELEGATE, enabled = ok && purpose.trim().length >= 3, loading = action.busy)
    }
}

/** A link changed: its kind, its sentence, on or off (never deleted). */
@Composable
private fun EditLinkSheet(canvas: HubCanvas, l: CompanyLink, onDismiss: () -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val action = rememberAction()
    var kind by rememberSaveable(l.id) { mutableStateOf(l.kind) }
    var purpose by rememberSaveable(l.id) { mutableStateOf(l.purposeFa) }
    var on by rememberSaveable(l.id) { mutableStateOf(l.state == "on") }
    com.coinepro.hq.ui.v14.HqSheet(onDismiss, "${nameOf(canvas, l.from)} ← ${nameOf(canvas, l.to)}", sub = if (l.openWorks > 0) "${l.openWorks} کار باز روی این پیوند" else "کار بازی روی این پیوند نیست") {
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            for ((k, fa) in LINK_KIND_FA) FilterChip(fa, kind == k, { kind = k })
        }
        HqTextField(purpose, { purpose = it }, "برای چه؟ یک جمله", Modifier.fillMaxWidth(), singleLine = false, minLines = 2, maxLength = 300)
        HqSwitch(on, { on = it }, if (on) "روشن است" else "خاموش است؛ چیزی پاک نمیشود")
        HqButton("ذخیره", {
            action.run {
                env.api.patchLink(
                    l.id, kind = kind.takeIf { it != l.kind }, purposeFa = purpose.trim().takeIf { it != l.purposeFa },
                    state = (if (on) "on" else "off").takeIf { it != l.state },
                )
                env.cache.invalidate("office", "links")
                toasts.ok("پیوند به‌روز شد.")
                onDismiss()
            }
        }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, icon = DivanIcon.SEAL, loading = action.busy)
    }
}
