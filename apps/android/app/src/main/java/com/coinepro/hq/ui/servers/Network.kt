package com.coinepro.hq.ui.servers

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.absoluteOffset
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.AbsoluteAlignment
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.format.jTime
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.CheckProgress
import com.coinepro.hq.core.net.HubLine
import com.coinepro.hq.core.net.LinkHealth
import com.coinepro.hq.core.net.NetNode
import com.coinepro.hq.core.net.NetPath
import com.coinepro.hq.core.net.NetSummary
import com.coinepro.hq.core.net.Network
import com.coinepro.hq.core.net.NetworkMap
import com.coinepro.hq.core.net.serverError
import com.coinepro.hq.designsystem.BarTone
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.CompanyMark
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.LocalReducedMotion
import com.coinepro.hq.designsystem.MeterBar
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.QueryHandle
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v16.companyColor
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlin.math.cos
import kotlin.math.hypot
import kotlin.math.sin

// ⟨1.8⟩ Contract §26.6: the holding's network map. The hub in the centre, each company's server around it, the road from each to the hub
// coloured by its health and labelled with the road (private or public) and its round trip; a server's own checks of the others, port by
// port, a tap away; «بررسی دوباره» asks every runner to check now and follows the results as they come.

@Composable
fun rememberNetwork(): QueryHandle<NetworkMap> = rememberQuery("network", "network", maxAgeMs = 30_000) { network() }

/** A check the owner started: how far it is (which runners answered) and whether it has ended, done or out of time. */
data class NetCheckRun(val before: NetworkMap?, val progress: CheckProgress, val waitedMs: Long = 0, val ended: Boolean = false, val at: String? = null) {
    val timedOut: Boolean get() = ended && !progress.done
}

/** «شبکه‌ی هلدینگ»: what is broken in words first, then the map, then the tapped server's roads to every other server. [map0] shows that
 *  map instead of the hub's (the screenshots' healthy network). */
@Composable
fun NetworkScreen(selected0: String? = null, check0: NetCheckRun? = null, map0: NetworkMap? = null) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val q = rememberNetwork()
    val names = rememberNetNames(map0 ?: q.data)
    var selected by rememberSaveable { mutableStateOf(selected0) }
    var run by remember { mutableStateOf(check0) }
    val scope = rememberCoroutineScope()
    val r = refresher(q)
    val checking = run?.ended == false

    fun check() {
        if (checking) return
        val before = q.data
        run = NetCheckRun(before, Network.progress(before, before ?: NetworkMap()).copy(reported = emptySet()))
        scope.launch {
            try {
                env.api.checkNetwork()
            } catch (e: ApiException) {
                run = null
                toasts.error(serverError(e))
                return@launch
            }
            var waited = 0L
            var p = run?.progress ?: CheckProgress(emptySet(), emptySet())
            // Every 3 s, at most a minute: the runners answer on their next poll, each in its own time.
            while (waited < Network.MAX_WAIT_MS) {
                delay(Network.POLL_MS)
                waited += Network.POLL_MS
                val now = runCatching { env.api.network() }.getOrNull()
                if (now != null) {
                    q.set(now)
                    p = Network.progress(before, now)
                }
                run = run?.copy(progress = p, waitedMs = waited)
                if (p.done) break
            }
            run = run?.copy(progress = p, waitedMs = waited, ended = true, at = q.data?.lastAt)
            env.cache.invalidate("servers")
            if (p.done) toasts.ok("بررسی تمام شد؛ همه‌ی سرورها جواب دادند.")
            else toasts.info("بررسی تمام شد؛ ${(p.expected - p.reported).size} سرور در یک دقیقه جواب نداد.")
        }
    }

    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item(key = "header") {
            PageHeader("شبکه‌ی هلدینگ", eyebrow = "هاب و سرورهای شرکت‌ها روی شبکه‌ی خصوصی هتزنر") {
                HqButton("بررسی دوباره", { check() }, variant = BtnVariant.PRIMARY, size = BtnSize.SM, icon = DivanIcon.REFRESH, loading = checking, enabled = q.data != null)
            }
        }
        val m = map0 ?: q.data
        when {
            m == null && q.error == null -> item(key = "skeleton") {
                Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
                    Skeleton(Modifier.fillMaxWidth().height(96.dp), radius = 16.dp)
                    Skeleton(Modifier.fillMaxWidth().height(380.dp), radius = 16.dp)
                }
            }
            m == null -> item(key = "error") { ErrorBlock(q.error, { q.refresh() }) }
            else -> {
                run?.let { x -> item(key = "check") { CheckCard(x, names) } }
                item(key = "summary") { SummaryCard(Network.summary(m), names) }
                item(key = "map") {
                    HqCard(Modifier.fillMaxWidth()) {
                        NetworkMapView(m, names, selected, waiting = if (checking) run?.progress?.let { it.expected - it.reported }.orEmpty() else emptySet()) { id ->
                            selected = if (selected == id) null else id
                        }
                        Legend(Modifier.padding(top = 12.dp))
                        m.lastAt?.let { at ->
                            Text(com.coinepro.hq.designsystem.timesFig(buildAnnotatedString { append("آخرین بررسی "); fig(jTime(at)); append(" · " + ago(at)) }), Modifier.padding(top = 8.dp), style = Divan.type.micro, color = Divan.colors.textMuted)
                        }
                    }
                }
                val node = selected?.let { m.node(it) }?.takeIf { !it.isHub }
                if (node != null) item(key = "node-$selected") { NodeDetail(m, node, names) { selected = null } }
                else item(key = "tap") {
                    Text("روی هر سرور بزن تا ببینی به سرورهای دیگر، پورت به پورت، میرسد یا نه.", style = Divan.type.caption, color = Divan.colors.textMuted)
                }
                item(key = "note") {
                    Text(
                        buildAnnotatedString {
                            append("هر "); fig("runner"); append(" با "); fig("HTTPS"); append(" به هاب وصل میشود؛ هاب به هیچ سروری وارد نمیشود. «بررسی دوباره» از هر ")
                            fig("runner"); append(" میخواهد هاب را روی پورت "); fig("443"); append(" و سرورهای دیگر را روی پورت‌های "); fig("22")
                            append("، "); fig("80"); append(" و "); fig("443")
                            append(" بسنجد؛ همین بررسی هر روز خودکار هم انجام میشود و ناظر اگر راهی که کار میکرد قطع شود خبر میدهد.")
                        },
                        style = Divan.type.micro, color = Divan.colors.textMuted,
                    )
                }
            }
        }
    }
}

/** Every node's name as the owner's rule says (the company; the server's own name too when the company has several). */
@Composable
internal fun rememberNetNames(m: NetworkMap?): (NetNode) -> ServerName {
    val companies = rememberCompanies()
    val servers = m?.servers.orEmpty()
    return remember(companies, servers) {
        { n ->
            if (n.isHub) ServerName("HQ", "هاب", null)
            else {
                // A company the list does not know yet (a server paired before its company was founded in the hub) goes by its server's name.
                val known = companies.firstOrNull { it.code == n.company }
                if (known == null) ServerName(n.company, n.name.ifBlank { n.company }, null)
                else serverNameOf(n.company, known.nameFa, n.name, servers.count { it.company == n.company })
            }
        }
    }
}

// ------------------------------------------------------------------ the summary --
/** What the summary card says, in words: its headline and its tone. */
internal fun headline(s: NetSummary): Pair<String, Tone> = when {
    s.servers == 0 -> "هنوز سروری روی شبکه نیست" to Tone.NEUTRAL
    s.failed.isNotEmpty() -> "${s.failed.size} مسیر قطع است" to Tone.NEG
    s.allOk -> "همه‌ی سرورها به هاب وصل‌اند" to Tone.POS
    s.slow.isNotEmpty() && s.outside.isEmpty() && s.fellBack.isEmpty() -> "همه‌ی سرورها به هاب وصل‌اند؛ ${s.slow.size} راه کند است" to Tone.WARN
    else -> "همه‌ی سرورها به هاب وصل‌اند" to Tone.WARN
}

@Composable
private fun SummaryCard(s: NetSummary, names: (NetNode) -> ServerName) {
    val c = Divan.colors
    val (title, tone) = headline(s)
    val (bg, fg) = when (tone) {
        Tone.POS -> c.softPositive to c.positive
        Tone.NEG -> c.softNegative to c.negative
        Tone.WARN -> c.softWarning to c.warning
        else -> c.tile to c.textSecondary
    }
    HqCard(Modifier.fillMaxWidth()) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Box(Modifier.size(40.dp).clip(CircleShape).background(bg), contentAlignment = Alignment.Center) {
                DIcon(if (tone == Tone.NEG) DivanIcon.URGENT else if (tone == Tone.POS) DivanIcon.SEAL else DivanIcon.GLOBE, size = 20.dp, tint = fg)
            }
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(title, style = Divan.type.h3, color = c.textPrimary)
                Text(
                    when {
                        s.servers == 0 -> "وقتی runner اولین سرور وصل شد، راهش به هاب اینجا دیده میشود."
                        s.allOk -> "هر ${s.servers} سرور از شبکه‌ی خصوصی به هاب میرسند و به هم راه دارند."
                        s.failed.isEmpty() -> "هیچ راهی قطع نیست؛ ولی این‌ها را ببین:"
                        else -> "این راه‌ها جواب ندادند:"
                    },
                    style = Divan.type.caption, color = c.textSecondary,
                )
            }
        }
        if (!s.allOk && s.servers > 0) Column(Modifier.padding(top = 12.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            for (p in s.failed) Issue(c.negative) {
                PathLine(p, names)
                Text(isolated(pathHint(p, names)), style = Divan.type.caption, color = c.textSecondary)
            }
            for (n in s.outside) Issue(c.warning) {
                Text(buildAnnotatedString { append(names(n).text); append(" از راه عمومی به هاب وصل است") }, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold))
                Text(isolated(outsideHint(s.nextFreeIp)), style = Divan.type.caption, color = c.textSecondary)
            }
            for (n in s.fellBack) Issue(c.warning) {
                Text(buildAnnotatedString { append(names(n).text); append(" این بار از راه عمومی آمد") }, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold))
                Text(isolated("در شبکه‌ی خصوصی هست، ولی آدرس خصوصی هاب جواب نداد و runner به آدرس عمومی برگشت. اگر تکرار شد، Claude همان سرور با hq-runner status و ip addr علتش را ببیند."), style = Divan.type.caption, color = c.textSecondary)
            }
            for (l in s.slow) Issue(c.warning) {
                Text(buildAnnotatedString { append(names(l.node).text); append(" کند به هاب میرسد · "); fig(Network.ms(l.rttMs) ?: "—") }, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold))
                Text(buildAnnotatedString { append("بیشتر از "); fig("${Network.SLOW_MS.toInt()} ms"); append("؛ کار میکند ولی هر فرمان دیرتر جواب میدهد.") }, style = Divan.type.caption, color = c.textSecondary)
            }
            for (n in s.unknown) Issue(c.textMuted) {
                Text(buildAnnotatedString { append(names(n).text); append(": runner هنوز تماس نگرفته") }, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold))
                Text("راهش به هاب بعد از اولین تماس runner دیده میشود.", style = Divan.type.caption, color = c.textSecondary)
            }
        }
    }
}

/** What to do about a broken road, in plain words. */
internal fun pathHint(p: NetPath, names: (NetNode) -> ServerName): String = when {
    p.toHub && p.error == "offline" -> "runner این سرور تماس نمیگیرد: سرور خاموش است، سرویس hq-runner ایستاده یا به شبکه نمیرسد. Claude همان سرور با hq-runner status علتش را ببیند."
    p.toHub -> "${Network.errorFa(p.error)}؛ runner این سرور به هاب نمیرسد و کاری رویش اجرا نمیشود."
    else -> "${Network.errorFa(p.error)}؛ ${names(p.from).text} روی پورت ${p.ports.joinToString(" و ")} به ${names(p.to).text} نمیرسد. اگر این راه لازم است، از Claude سرور ${names(p.to).text} بخواه فایروال همان سرور را ببیند. کار میان شرکت‌ها به این راه نیاز ندارد و همیشه از هاب میگذرد."
}

/** A server outside the private network: the owner adds it from the Hetzner console (§26.1a), at the next free address. */
internal fun outsideHint(nextIp: String?): String =
    "یعنی هنوز در شبکه‌ی خصوصی نیست: از کنسول هتزنر، Networks، این سرور را به شبکه‌ی هلدینگ اضافه کن" +
        (nextIp?.let { " (آدرس آزاد بعدی $it)" } ?: "") + ". تا آن موقع از آدرس عمومی با TLS کار میکند."

@Composable
private fun Issue(color: Color, content: @Composable () -> Unit) {
    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        Box(Modifier.padding(top = 6.dp).size(8.dp).clip(CircleShape).background(color))
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) { content() }
    }
}

/** «پروچارت → کوینه‌پرو FX · 22» */
@Composable
private fun PathLine(p: NetPath, names: (NetNode) -> ServerName) {
    Text(buildAnnotatedString {
        append(names(p.from).text); append(" ← ")
        append(names(p.to).text)
        if (!p.toHub) { append(" · پورت "); fig(p.ports.joinToString(", ")) }
    }, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = Divan.colors.textPrimary)
}

// ------------------------------------------------------------------ the check --
@Composable
private fun CheckCard(x: NetCheckRun, names: (NetNode) -> ServerName) {
    val c = Divan.colors
    val p = x.progress
    val n = p.expected.size
    val got = p.reported.intersect(p.expected).size
    HqCard(Modifier.fillMaxWidth(), color = if (x.ended && !x.timedOut) c.softPositive else c.card) {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                DIcon(if (x.ended) (if (x.timedOut) DivanIcon.TIME else DivanIcon.SEAL) else DivanIcon.REFRESH, size = 18.dp, tint = if (x.ended && !x.timedOut) c.positive else c.goldInk)
                Text(
                    when {
                        !x.ended -> "در حال بررسی… $got از $n سرور جواب دادند"
                        x.timedOut -> "بررسی تمام شد؛ $got از $n سرور در یک دقیقه جواب دادند"
                        else -> "بررسی تمام شد؛ هر $n سرور جواب دادند"
                    },
                    Modifier.weight(1f), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold),
                )
                if (!x.ended) Fig("${x.waitedMs / 1000}s", style = Divan.type.figureSmall, color = c.textMuted)
            }
            if (!x.ended) MeterBar(p.fraction * 100.0, tone = BarTone.SILVER, height = 5.dp, color = c.goldInk)
            if (!x.ended) Text("هر runner در تماس بعدی‌اش میسنجد؛ حداکثر یک دقیقه.", style = Divan.type.micro, color = c.textMuted)
            if (x.timedOut) {
                val silent = (p.expected - p.reported)
                Text("جواب ندادند: " + silent.joinToString("، ") { id -> x.before?.node(id)?.let { names(it).text } ?: id }, style = Divan.type.caption, color = c.textSecondary)
            }
        }
    }
}

// ------------------------------------------------------------------ the map --
private val NODE = 48.dp
private val HUB_NODE = 60.dp
private val NODE_W = 100.dp
/** The height of a node's name under it (one line of caption and its gap). */
private val NAME_H = 26.dp
private val MAP_H = 380.dp

/** The colour of a road's health. */
@Composable
internal fun healthColor(h: LinkHealth): Color = when (h) {
    LinkHealth.OK -> Divan.colors.positive
    LinkHealth.SLOW -> Divan.colors.warning
    LinkHealth.FAIL -> Divan.colors.negative
    LinkHealth.UNKNOWN -> Divan.colors.textMuted
}

/** Where each server sits: around the hub, the servers of one company next to each other with a gap between companies. */
internal fun ringAngles(nodes: List<NetNode>): List<Double> {
    if (nodes.isEmpty()) return emptyList()
    val groups = nodes.map { it.company }.distinct()
    val gaps = if (groups.size > 1) groups.size else 0
    val slots = nodes.size + gaps
    var slot = 0
    var last: String? = null
    return nodes.map { n ->
        if (last != null && n.company != last) slot++
        last = n.company
        (-90.0 + 360.0 * slot++ / slots)
    }
}

@Composable
private fun NetworkMapView(m: NetworkMap, names: (NetNode) -> ServerName, selected: String?, waiting: Set<String>, onSelect: (String) -> Unit) {
    val c = Divan.colors
    val companies = rememberCompanies()
    val order = companies.map { it.code }
    // Companies are data: one group per company, in the companies' own order, those the list does not know at the end.
    val servers = m.servers.sortedWith(compareBy({ order.indexOf(it.company).let { i -> if (i < 0) Int.MAX_VALUE else i } }, { it.company }, { it.name }))
    val lines = servers.map { Network.hubLine(m, it) }
    val angles = ringAngles(servers)
    val colors = lines.map { healthColor(it.health) }
    val marks = servers.map { companyColor(it.company) }
    val reduced = LocalReducedMotion.current
    val travel = if (waiting.isNotEmpty() && !reduced) {
        rememberInfiniteTransition(label = "netcheck").animateFloat(0f, 1f, infiniteRepeatable(tween(1_200, easing = LinearEasing)), label = "netcheck")
    } else null
    // The broken roads between servers, drawn as thin red chords (the hub's own roads are the spokes).
    val chords = Network.summary(m).failed.filter { !it.toHub }
    // Every piece is placed from the top left, whatever the app's direction: the map is a picture, not a line of text.
    BoxWithConstraints(Modifier.fillMaxWidth().height(MAP_H), contentAlignment = AbsoluteAlignment.TopLeft) {
        val w = maxWidth
        val h = maxHeight
        val cx = w / 2
        val cy = h / 2
        val rx = (w / 2 - NODE_W / 2).coerceAtLeast(60.dp)
        val ry = h / 2 - 58.dp
        val pos = angles.map { a -> Pair(cx + rx * cos(Math.toRadians(a)).toFloat(), cy + ry * sin(Math.toRadians(a)).toFloat()) }
        val idx = servers.mapIndexed { i, n -> n.id to i }.toMap()
        Canvas(Modifier.fillMaxSize()) {
            val hub = Offset(cx.toPx(), cy.toPx())
            for ((i, l) in lines.withIndex()) {
                val p = Offset(pos[i].first.toPx(), pos[i].second.toPx())
                val (a, b) = trim(hub, p, HUB_NODE.toPx() / 2 + 4.dp.toPx(), NODE.toPx() / 2 + 4.dp.toPx())
                val sel = servers[i].id == selected
                // A runner the check still waits for is drawn faint until it answers.
                val faint = servers[i].id in waiting
                drawLine(
                    colors[i].copy(alpha = if (faint) 0.3f else if (l.health == LinkHealth.UNKNOWN) 0.6f else 0.9f), a, b,
                    strokeWidth = (if (sel) 4.dp else 2.5.dp).toPx(), cap = StrokeCap.Round,
                    pathEffect = if (l.via == "public" || l.health == LinkHealth.UNKNOWN) PathEffect.dashPathEffect(floatArrayOf(10.dp.toPx(), 7.dp.toPx())) else null,
                )
                // While a check runs, a spark travels out to every runner that has not answered yet.
                val t = travel?.value
                if (t != null && servers[i].id in waiting) {
                    drawCircle(c.goldInk, radius = 4.dp.toPx(), center = a + (b - a) * t)
                }
            }
            for (p in chords) {
                val i = idx[p.from.id] ?: continue
                val j = idx[p.to.id] ?: continue
                val from = Offset(pos[i].first.toPx(), pos[i].second.toPx())
                val to = Offset(pos[j].first.toPx(), pos[j].second.toPx())
                // A node's name sits under it: a chord that leaves downward or arrives from below stops short of the name.
                val name = NAME_H.toPx()
                val (a, b) = trim(from, to, NODE.toPx() / 2 + 6.dp.toPx() + (if (to.y > from.y) name else 0f), NODE.toPx() / 2 + 6.dp.toPx() + (if (to.y > from.y) 0f else name))
                drawLine(c.negative.copy(alpha = 0.75f), a, b, strokeWidth = 1.5.dp.toPx(), cap = StrokeCap.Round, pathEffect = PathEffect.dashPathEffect(floatArrayOf(4.dp.toPx(), 4.dp.toPx())))
                // An arrow head at the far end: who could not reach whom.
                val d = (b - a)
                val len = hypot(d.x, d.y).takeIf { it > 0f } ?: continue
                val u = Offset(d.x / len, d.y / len)
                val n = Offset(-u.y, u.x)
                val s = 7.dp.toPx()
                val head = Path().apply {
                    moveTo(b.x, b.y)
                    lineTo(b.x - u.x * s + n.x * s * 0.55f, b.y - u.y * s + n.y * s * 0.55f)
                    lineTo(b.x - u.x * s - n.x * s * 0.55f, b.y - u.y * s - n.y * s * 0.55f)
                    close()
                }
                drawPath(head, c.negative)
            }
            // The selected server's ring.
            selected?.let { idx[it] }?.let { i ->
                drawCircle(c.goldInk, radius = NODE.toPx() / 2 + 5.dp.toPx(), center = Offset(pos[i].first.toPx(), pos[i].second.toPx()), style = Stroke(2.dp.toPx()))
            }
        }
        // The labels on the spokes: the road and the round trip.
        for ((i, l) in lines.withIndex()) {
            val (x, y) = pos[i]
            // In the middle of the free part of the spoke: from the hub's ring to the node's ring, past the node's name when the name
            // lies on the spoke (a node above the hub).
            val dist = kotlin.math.hypot((x - cx).value, (y - cy).value).coerceAtLeast(1f)
            val t0 = (HUB_NODE / 2 + 4.dp).value / dist
            val t1 = 1f - (NODE / 2 + 4.dp + (if (y < cy) NAME_H else 0.dp)).value / dist
            val t = ((t0 + t1) / 2).coerceIn(0.3f, 0.7f)
            val lx = cx + (x - cx) * t
            val ly = cy + (y - cy) * t
            SpokeLabel(l, colors[i], Modifier.absoluteOffset(x = lx - 30.dp, y = ly - 17.dp).width(60.dp))
        }
        for (p in chords) {
            val i = idx[p.from.id] ?: continue
            val j = idx[p.to.id] ?: continue
            // Beside the chord's middle, not on it, so neither the line nor a node's name runs under the chip.
            val mx = (pos[i].first + pos[j].first) / 2
            val my = (pos[i].second + pos[j].second) / 2
            val dx = (pos[j].first - pos[i].first).value
            val dy = (pos[j].second - pos[i].second).value
            val len = kotlin.math.hypot(dx, dy).coerceAtLeast(1f)
            val lx = mx + (-dy / len * 16f).dp
            val ly = my + (dx / len * 16f).dp
            Box(Modifier.absoluteOffset(x = lx - 28.dp, y = ly - 10.dp).width(56.dp), contentAlignment = Alignment.Center) {
                Row(Modifier.clip(RoundedCornerShape(10.dp)).background(c.softNegative).padding(horizontal = 6.dp, vertical = 1.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(3.dp)) {
                    Tick(false, c.negative, 9.dp)
                    Fig(p.ports.joinToString(","), style = Divan.type.figureSmall, color = c.negative)
                }
            }
        }
        // The hub.
        Column(Modifier.absoluteOffset(x = cx - NODE_W / 2, y = cy - HUB_NODE / 2).width(NODE_W), horizontalAlignment = Alignment.CenterHorizontally) {
            Column(
                Modifier.size(HUB_NODE).clip(CircleShape).background(c.softGold).border(2.dp, c.goldInk, CircleShape).semantics { contentDescription = "هاب" },
                horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center,
            ) {
                DIcon(DivanIcon.HOLDING, size = 20.dp, tint = c.goldInk)
                Text("هاب", style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = c.goldInk)
            }
        }
        // The servers.
        for ((i, n) in servers.withIndex()) {
            val (x, y) = pos[i]
            val name = names(n)
            Column(
                Modifier.absoluteOffset(x = x - NODE_W / 2, y = y - NODE / 2).width(NODE_W)
                    .clip(RoundedCornerShape(14.dp)).clickable(role = Role.Button, onClickLabel = "راه‌های ${name.text}") { onSelect(n.id) },
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                Box(
                    Modifier.size(NODE).clip(CircleShape).background(marks[i].copy(alpha = 0.16f)).border(2.dp, colors[i], CircleShape)
                        .semantics { contentDescription = name.text },
                    contentAlignment = Alignment.Center,
                ) {
                    CompanyMark(n.company, height = 20.dp, ink = c.textPrimary)
                }
                Text(name.companyFa, Modifier.padding(top = 4.dp), style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, maxLines = 1, overflow = TextOverflow.Ellipsis, textAlign = TextAlign.Center)
                name.server?.let { Fig(it, style = Divan.type.figureSmall, color = c.textMuted) }
            }
        }
    }
}

/** A spoke between [a] and [b] cut back by the two circles it joins. */
private fun trim(a: Offset, b: Offset, ra: Float, rb: Float): Pair<Offset, Offset> {
    val d = b - a
    val len = hypot(d.x, d.y)
    if (len <= ra + rb) return a to a
    val u = Offset(d.x / len, d.y / len)
    return (a + u * ra) to (b - u * rb)
}

/** «خصوصی» over «3 ms» on a spoke (two short lines fit between the circles); «قطع» on a broken one. */
@Composable
private fun SpokeLabel(l: HubLine, color: Color, modifier: Modifier) {
    val c = Divan.colors
    Box(modifier, contentAlignment = Alignment.Center) {
        Column(
            Modifier.clip(RoundedCornerShape(9.dp)).background(c.card).border(1.dp, color.copy(alpha = 0.6f), RoundedCornerShape(9.dp)).padding(horizontal = 6.dp, vertical = 1.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            when (l.health) {
                LinkHealth.FAIL -> Text(if (l.error == "offline") "آفلاین" else "قطع", style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = color)
                LinkHealth.UNKNOWN -> Text("نامعلوم", style = Divan.type.micro, color = color)
                else -> {
                    Text(viaFa(l.via), style = Divan.type.micro, color = c.textSecondary)
                    Network.ms(l.rttMs)?.let { Fig(it, style = Divan.type.figureSmall, color = color) }
                }
            }
        }
    }
}

internal fun viaFa(via: String?): String = when (via) {
    "private" -> "خصوصی"
    "public" -> "عمومی"
    else -> "—"
}

@Composable
private fun Legend(modifier: Modifier = Modifier) {
    val c = Divan.colors
    FlowRow(modifier, horizontalArrangement = Arrangement.spacedBy(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp), itemVerticalAlignment = Alignment.CenterVertically) {
        for ((h, t) in listOf(LinkHealth.OK to "سالم", LinkHealth.SLOW to "کند", LinkHealth.FAIL to "قطع", LinkHealth.UNKNOWN to "نامعلوم")) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                Box(Modifier.size(width = 14.dp, height = 3.dp).clip(RoundedCornerShape(2.dp)).background(healthColor(h)))
                Text(t, style = Divan.type.micro, color = c.textSecondary)
            }
        }
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            Canvas(Modifier.size(width = 18.dp, height = 3.dp)) {
                drawLine(c.textSecondary, Offset(0f, size.height / 2), Offset(size.width, size.height / 2), strokeWidth = size.height, pathEffect = PathEffect.dashPathEffect(floatArrayOf(4.dp.toPx(), 3.dp.toPx())))
            }
            Text("از راه عمومی", style = Divan.type.micro, color = c.textSecondary)
        }
        // One sentence, the figure isolated left to right: «بیش از 150 ms یعنی کند».
        Text(buildAnnotatedString { append("بیش از "); fig("${Network.SLOW_MS.toInt()} ms"); append(" یعنی کند") }, style = Divan.type.micro, color = c.textMuted)
    }
}

/** A drawn ✓ or ✗ (no font has to carry the glyph). */
@Composable
private fun Tick(ok: Boolean, color: Color, size: Dp = 12.dp) {
    Canvas(Modifier.size(size)) {
        val w = this.size.width
        val s = Stroke(width = w * 0.16f, cap = StrokeCap.Round)
        if (ok) {
            drawPath(Path().apply { moveTo(w * 0.12f, w * 0.55f); lineTo(w * 0.4f, w * 0.82f); lineTo(w * 0.9f, w * 0.2f) }, color, style = s)
        } else {
            drawLine(color, Offset(w * 0.18f, w * 0.18f), Offset(w * 0.82f, w * 0.82f), strokeWidth = s.width, cap = StrokeCap.Round)
            drawLine(color, Offset(w * 0.82f, w * 0.18f), Offset(w * 0.18f, w * 0.82f), strokeWidth = s.width, cap = StrokeCap.Round)
        }
    }
}

// ------------------------------------------------------------------ a server's roads --
/** The tapped server: its road to the hub, then from it to every other server on 22, 80 and 443 (✓ with the time, ✗ with why), the
 *  roads that failed towards it, and when it last checked. */
@Composable
internal fun NodeDetail(m: NetworkMap, n: NetNode, names: (NetNode) -> ServerName, onClose: () -> Unit) {
    val c = Divan.colors
    val nav = LocalNav.current
    val name = names(n)
    val hub = Network.hubLine(m, n)
    val others = m.servers.filter { it.id != n.id }
    val mine = m.links.filter { it.from == n.id }
    val last = mine.mapNotNull { it.at }.maxOrNull()
    HqCard(Modifier.fillMaxWidth()) {
        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                ServerTitle(name, Modifier.weight(1f), style = Divan.type.h3, markHeight = 16.dp)
                HqButton(null, onClose, variant = BtnVariant.GHOST, size = BtnSize.SM, icon = DivanIcon.CLOSE, label = "بستن")
            }
            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp), itemVerticalAlignment = Alignment.CenterVertically) {
                val (t, tone) = when (hub.health) {
                    LinkHealth.OK -> "به هاب: ${viaFa(hub.via)}" to Tone.POS
                    LinkHealth.SLOW -> "به هاب: کند" to Tone.WARN
                    LinkHealth.FAIL -> "به هاب: ${Network.errorFa(hub.error)}" to Tone.NEG
                    LinkHealth.UNKNOWN -> "به هاب: نامعلوم" to Tone.NEUTRAL
                }
                Pill(t, tone, dot = true)
                Network.ms(hub.rttMs)?.let { Fig(it, style = Divan.type.figureSmall, color = c.textSecondary) }
                n.privateIp?.takeIf { it.isNotBlank() }?.let { Fig(it, style = Divan.type.figureSmall, color = c.textMuted) }
                    ?: Text("بیرون از شبکه‌ی خصوصی", style = Divan.type.micro, color = c.warning)
            }
            if (n.outside) com.coinepro.hq.ui.v16.Notice(DivanIcon.GLOBE, c.softWarning, c.warning) {
                Text(isolated(outsideHint(Network.nextFreeIp(m))), style = Divan.type.caption, color = c.textSecondary)
            }
            Text("از این سرور به سرورهای دیگر", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.goldInk)
            Matrix(m, n, others, names)
            Text(buildAnnotatedString { append("زمان‌ها به "); fig("ms"); append("؛ «—» یعنی هنوز بررسی نشده و «·» یعنی هاب روی آن پورت سنجیده نمیشود.") }, style = Divan.type.micro, color = c.textMuted)
            val incoming = m.links.filter { it.to == n.id && it.ok == false && m.link(it.from, it.to, it.port)?.ok == false }
                .groupBy { it.from }.mapNotNull { (from, ls) -> m.node(from)?.let { it to ls.map { l -> l.port }.distinct().sorted() } }
            if (incoming.isNotEmpty()) {
                Text("به این سرور نرسیدند", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.negative)
                for ((from, ports) in incoming) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Tick(false, c.negative, 10.dp)
                    Text(buildAnnotatedString { append(names(from).text); append(" · پورت "); fig(ports.joinToString(", ")) }, style = Divan.type.caption, color = c.textSecondary)
                }
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    buildAnnotatedString { if (last != null) { append("آخرین بررسی این سرور "); fig(jTime(last)); append(" · " + ago(last)) } else append("این سرور هنوز چیزی نسنجیده") },
                    Modifier.weight(1f), style = Divan.type.micro, color = c.textMuted,
                )
                if (!n.isHub) HqButton("باز کردن سرور", { nav.go("servers/${n.id}") }, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.NEXT)
            }
        }
    }
}

@Composable
private fun Matrix(m: NetworkMap, n: NetNode, others: List<NetNode>, names: (NetNode) -> ServerName) {
    val c = Divan.colors
    val ports = NetworkMap.PORTS
    val rows = listOf(m.all.first()) + others
    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile)) {
        Row(Modifier.fillMaxWidth().padding(horizontal = 10.dp, vertical = 7.dp), verticalAlignment = Alignment.CenterVertically) {
            Text("مقصد", Modifier.weight(1.3f), style = Divan.type.micro, color = c.textMuted)
            for (p in ports) Box(Modifier.weight(1f), contentAlignment = Alignment.Center) { Fig(p.toString(), style = Divan.type.figureSmall.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary) }
        }
        for (to in rows) {
            HorizontalDivider(color = c.lineDivider)
            Row(Modifier.fillMaxWidth().padding(horizontal = 10.dp, vertical = 7.dp), verticalAlignment = Alignment.CenterVertically) {
                Row(Modifier.weight(1.3f), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(5.dp)) {
                    if (to.isHub) DIcon(DivanIcon.HOLDING, size = 13.dp, tint = c.goldInk)
                    else CompanyMark(to.company, height = 12.dp, mono = true, ink = c.textSecondary)
                    Text(names(to).text, style = Divan.type.caption, color = c.textPrimary, maxLines = 1, overflow = TextOverflow.Ellipsis)
                }
                for (p in ports) Box(Modifier.weight(1f), contentAlignment = Alignment.Center) {
                    // The hub is checked on 443 only (§26.6).
                    val l = if (to.isHub && p != 443) null else m.link(n.id, to.id, p)
                    Cell(l?.ok, l?.ms, l?.error, applies = !(to.isHub && p != 443))
                }
            }
        }
    }
}

@Composable
private fun Cell(ok: Boolean?, ms: Double?, error: String?, applies: Boolean) {
    val c = Divan.colors
    when {
        !applies -> Text("·", style = Divan.type.caption, color = c.textMuted)
        ok == null -> Text("—", style = Divan.type.caption, color = c.textMuted)
        ok -> Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(3.dp)) {
            val color = healthColor(Network.health(true, ms))
            Tick(true, color, 11.dp)
            Network.ms(ms)?.let { Fig(it.removeSuffix(" ms"), style = Divan.type.figureSmall, color = c.textSecondary) }
        }
        else -> Row(
            Modifier.semantics { contentDescription = Network.errorFa(error) },
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(3.dp),
        ) {
            Tick(false, c.negative, 11.dp)
            Text(Network.errorFa(error).let { if (it.length > 10) "قطع" else it }, style = Divan.type.micro, color = c.negative, maxLines = 1)
        }
    }
}

// ------------------------------------------------------------------ the entry points --
/** «شبکه‌ی هلدینگ» as a line on «همه‌ی سرورها» and in the control room: the headline and a way in. */
@Composable
fun NetworkLink(modifier: Modifier = Modifier) {
    val nav = LocalNav.current
    val c = Divan.colors
    val q = rememberNetwork()
    val s = q.data?.let { Network.summary(it) }
    val (title, tone) = s?.let { headline(it) } ?: ("راه هر سرور به هاب و به سرورهای دیگر" to Tone.NEUTRAL)
    HqCard(modifier.fillMaxWidth(), onClick = { nav.go("network") }, onClickLabel = "شبکه‌ی هلدینگ") {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            com.coinepro.hq.ui.v17.IconTile(DivanIcon.GLOBE, c.goldInk, size = 40.dp)
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text("شبکه‌ی هلدینگ", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold))
                Text(title, style = Divan.type.caption, color = when (tone) { Tone.NEG -> c.negative; Tone.WARN -> c.warning; Tone.POS -> c.positive; else -> c.textMuted })
            }
            DIcon(DivanIcon.NEXT, size = 16.dp, tint = c.textMuted)
        }
    }
}
