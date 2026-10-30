package com.coinepro.hq.ui.work

import android.Manifest
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.coinepro.hq.core.data.OrderEnd
import com.coinepro.hq.core.data.OrderStage
import com.coinepro.hq.core.data.OrderTrack
import com.coinepro.hq.core.data.Part
import com.coinepro.hq.core.data.StreamState
import com.coinepro.hq.core.data.endOf
import com.coinepro.hq.core.data.holdersOf
import com.coinepro.hq.core.data.lastActivityOf
import com.coinepro.hq.core.data.orderTrack
import com.coinepro.hq.core.data.ownerOrders
import com.coinepro.hq.core.data.progressOf
import com.coinepro.hq.core.data.reasonOf
import com.coinepro.hq.core.data.stageOf
import com.coinepro.hq.core.data.takenFa
import com.coinepro.hq.core.data.timelineOf
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.format.jDate
import com.coinepro.hq.core.format.jTime
import com.coinepro.hq.core.format.ownerDay
import com.coinepro.hq.core.net.EmployeeRef
import com.coinepro.hq.core.net.Work
import com.coinepro.hq.designsystem.BarTone
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.CompanyMark
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.MeterBar
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.Radius
import com.coinepro.hq.designsystem.ScrollRow
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.Space
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.designsystem.rememberBreath
import com.coinepro.hq.designsystem.smoothSize
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.QueryHandle
import com.coinepro.hq.ui.companyOf
import com.coinepro.hq.ui.itemMotion
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.shell.LocalLive

private val ACTIVE = setOf("queued", "in_progress", "waiting")
private val DELIVERED = setOf("delivered", "done")
private val ENDED = setOf("failed", "cancelled")

/** The owner's orders (newest first), shared by the home card and «فرمان‌های من»; every work they carry seeds the titles cache. */
@Composable
fun rememberOrders(): QueryHandle<List<Work>> {
    val env = LocalEnv.current
    val q = rememberQuery("orders", "work", maxAgeMs = 15_000) { ownerOrders() }
    LaunchedEffect(q.data) { q.data?.let(env.works::seed) }
    return q
}

/** One order and what is under it; [full] adds its events and runs and its children's (the order's own page). */
@Composable
fun rememberTrack(id: String, full: Boolean = false): QueryHandle<OrderTrack> =
    rememberQuery(if (full) "order:$id:full" else "order:$id", "work", "runs", "deliverables", maxAgeMs = 15_000) { orderTrack(id, full) }

// ----------------------------------------------------------------- screen --
/**
 * «فرمان‌های من»: every order the owner gave, by state (on the way, delivered, ended), each with its company, title, stage on a stepper,
 * an estimate of how far along it is, who holds it now, when it last moved, and its output when it has one. The stream keeps it live.
 */
@Composable
fun OrdersScreen(onNewOrder: () -> Unit = {}, tab0: String = "active") {
    val nav = LocalNav.current
    val c = Divan.colors
    val q = rememberOrders()
    var tab by rememberSaveable { mutableStateOf(tab0) }
    val r = refresher(q)
    val all = q.data.orEmpty()
    val groups = mapOf(
        "active" to all.filter { it.status in ACTIVE },
        "delivered" to all.filter { it.status in DELIVERED },
        "ended" to all.filter { it.status in ENDED },
        "all" to all,
    )
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item(key = "header") {
            PageHeader("فرمان‌های من", eyebrow = "هر فرمانی که دادی، از ثبت تا تحویل؛ زنده") {
                HqButton("فرمان تازه", onNewOrder, size = BtnSize.SM, variant = BtnVariant.PRIMARY, icon = DivanIcon.COMMAND)
                HqButton("کارتابل", { nav.go("cartable") }, size = BtnSize.SM, variant = BtnVariant.TEXT, icon = DivanIcon.CARTABLE)
            }
        }
        item(key = "notify") { NotifyCard() }
        item(key = "tabs") {
            ScrollRow {
                for ((k, l) in listOf("active" to "در جریان", "delivered" to "تحویل‌شده", "ended" to "ناموفق یا لغو", "all" to "همه")) {
                    FilterChip(l, tab == k, { tab = k }, count = q.data?.let { groups.getValue(k).size })
                }
            }
        }
        val list = groups.getValue(tab)
        when {
            q.data == null && q.error != null -> item(key = "error") { ErrorBlock(q.error, { q.refresh() }) }
            q.data == null -> items(3, key = { "sk-$it" }) { Skeleton(Modifier.fillMaxWidth().height(212.dp), radius = Radius.card) }
            list.isEmpty() -> item(key = "empty") {
                HqCard(Modifier.fillMaxWidth()) {
                    Empty(
                        when (tab) { "active" -> "فرمانی در جریان نیست"; "delivered" -> "هنوز فرمانی تحویل نشده"; "ended" -> "فرمان ناموفق یا لغوشده‌ای نیست"; else -> "هنوز فرمانی نداده‌ای" },
                        icon = DivanIcon.COMMAND,
                        body = "هر فرمانی که بدهی این‌جا مرحله‌به‌مرحله دیده میشود: ثبت، مدیرعامل، واگذاری، انجام و تحویل.",
                        action = { HqButton("فرمان تازه", onNewOrder, icon = DivanIcon.COMMAND) },
                    )
                }
            }
            else -> items(list, key = { it.id }) { w -> Box(itemMotion()) { OrderCard(w) } }
        }
        item(key = "note") {
            Text(
                "درصد پیشرفت تخمینی است: از مرحله‌ی فرمان و سهم کارهای زیرمجموعه‌ی تمام‌شده حساب میشود و فقط وقتی چیزی واقعاً اتفاق بیفتد جلو میرود.",
                style = Divan.type.micro, color = c.textMuted,
            )
        }
    }
}

/** Android 13+ asks before an app may notify; until the owner says yes, the orders' changes are told in the app only (and the background
 *  link, which tells them with the app closed, stays off). */
@Composable
private fun NotifyCard() {
    val ctx = LocalContext.current
    var allowed by remember { mutableStateOf(com.coinepro.hq.device.AlertNotifier.allowed(ctx)) }
    val ask = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) {
        allowed = com.coinepro.hq.device.AlertNotifier.allowed(ctx)
        // The background link follows the permission (on by default once it is granted).
        (ctx.applicationContext as? com.coinepro.hq.HqApp)?.graph?.link?.refresh()
    }
    if (allowed) return
    val c = Divan.colors
    HqCard(Modifier.fillMaxWidth(), color = c.softLapis) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Space.sm)) {
            DIcon(DivanIcon.BELL, size = 20.dp, tint = c.lapis)
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text("اعلان فرمان‌ها روی گوشی خاموش است", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold))
                Text("واگذاری، تحویل، شکست یا پایان هر فرمان، حتی با اپ بسته، در اعلان‌های گوشی گفته میشود.", style = Divan.type.caption, color = c.textSecondary)
            }
            HqButton("روشن کن", {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) ask.launch(Manifest.permission.POST_NOTIFICATIONS)
                else runCatching {
                    ctx.startActivity(android.content.Intent(android.provider.Settings.ACTION_APP_NOTIFICATION_SETTINGS).putExtra(android.provider.Settings.EXTRA_APP_PACKAGE, ctx.packageName).addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK))
                }
            }, size = BtnSize.SM)
        }
    }
}

/** One order: its company and priority, the title, the stepper, the estimate, who holds it, its output. */
@Composable
fun OrderCard(w: Work) {
    val nav = LocalNav.current
    val c = Divan.colors
    val companies = rememberCompanies()
    val t = rememberTrack(w.id)
    val track = t.data
    HqCard(Modifier.fillMaxWidth(), onClick = { nav.go("work/${w.id}") }, onClickLabel = "باز کردن فرمان") {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            CompanyMark(w.company, height = 13.dp, mono = true, ink = c.textSecondary)
            Text(companyOf(companies, w.company).let { if (it.holding) "هلدینگ" else it.nameFa }, style = Divan.type.caption, color = c.textSecondary, maxLines = 1)
            Text(buildAnnotatedString { append("· "); fig(w.ref) }, style = Divan.type.caption, color = c.textMuted)
            Spacer(Modifier.weight(1f))
            PriorityTag(w.priority, compact = true)
        }
        Spacer(Modifier.height(6.dp))
        Text(w.title, style = Divan.type.bodyStrong, maxLines = 2, overflow = TextOverflow.Ellipsis)
        Spacer(Modifier.height(Space.sm))
        if (track == null) {
            if (t.error != null) Text(t.error?.messageFa.orEmpty(), style = Divan.type.caption, color = c.textMuted)
            else Skeleton(Modifier.fillMaxWidth().height(96.dp), radius = Radius.tile)
        } else Column(Modifier.smoothSize(), verticalArrangement = Arrangement.spacedBy(Space.sm)) {
            OrderStepper(track)
            OrderMeter(track)
            HolderLine(track)
            OutputsRow(track)
            Text("آخرین حرکت: ${ago(lastActivityOf(track))}", style = Divan.type.micro, color = c.textMuted)
        }
    }
}

// ---------------------------------------------------------------- stepper --
/** The six stages, right to left: finished in gold, the current one ringed (breathing while it moves), the rest waiting. A failed or
 *  cancelled order marks the stage it stopped at; a finished one is green throughout. */
@Composable
fun OrderStepper(t: OrderTrack, modifier: Modifier = Modifier) {
    val c = Divan.colors
    val stage = stageOf(t)
    val end = endOf(t.root)
    val cur = stage.ordinal
    val done = stage == OrderStage.DONE
    val pastInk = if (done) c.positive else c.goldFill
    val stopInk = if (end == OrderEnd.FAILED) c.negative else c.textMuted
    val labels = OrderStage.entries.map { if (it == OrderStage.TAKEN) takenFa(t.root) else it.fa }
    Row(modifier.fillMaxWidth().semantics { contentDescription = "مرحله: ${labels[cur]}" + if (end != OrderEnd.NONE) "، متوقف" else "" }) {
        OrderStage.entries.forEachIndexed { i, s ->
            val current = i == cur
            val line = c.lineStrong
            val before = if (i <= cur) pastInk else line
            val after = if (i < cur) pastInk else line
            Column(Modifier.weight(1f), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(5.dp)) {
                Box(
                    Modifier.fillMaxWidth().height(16.dp).drawBehind {
                        val y = size.height / 2
                        val mid = size.width / 2
                        val startIsRight = layoutDirection == LayoutDirection.Rtl
                        val sx = if (startIsRight) size.width else 0f
                        val ex = if (startIsRight) 0f else size.width
                        if (i > 0) drawLine(before, Offset(sx, y), Offset(mid, y), 2.dp.toPx())
                        if (i < OrderStage.entries.lastIndex) drawLine(after, Offset(mid, y), Offset(ex, y), 2.dp.toPx())
                    },
                    contentAlignment = Alignment.Center,
                ) {
                    when {
                        current && end != OrderEnd.NONE -> Box(Modifier.size(16.dp).clip(CircleShape).background(if (end == OrderEnd.FAILED) c.softNegative else c.tile).border(1.5.dp, stopInk, CircleShape), contentAlignment = Alignment.Center) {
                            DIcon(DivanIcon.CLOSE, size = 10.dp, tint = stopInk)
                        }
                        current && done -> Box(Modifier.size(16.dp).clip(CircleShape).background(c.positive), contentAlignment = Alignment.Center) { DIcon(DivanIcon.SEAL, size = 10.dp, tint = c.page) }
                        current -> {
                            val b = rememberBreath(stage != OrderStage.DELIVERED, periodMs = 1800)
                            Box(Modifier.size(16.dp).clip(CircleShape).background(c.page).border(2.dp, c.goldInk, CircleShape), contentAlignment = Alignment.Center) {
                                Box(Modifier.size(6.dp).graphicsLayer { alpha = 1f - 0.55f * b.value }.clip(CircleShape).background(c.goldInk))
                            }
                        }
                        i < cur -> Box(Modifier.size(12.dp).clip(CircleShape).background(pastInk))
                        else -> Box(Modifier.size(10.dp).clip(CircleShape).background(c.page).border(1.5.dp, line, CircleShape))
                    }
                }
                Text(
                    labels[i], style = Divan.type.micro.copy(fontSize = 10.5.sp, lineHeight = 14.sp, fontWeight = if (current) FontWeight.Bold else FontWeight.Normal),
                    color = when { current && end == OrderEnd.FAILED -> c.negative; current -> c.textPrimary; i < cur -> c.textSecondary; else -> c.textMuted },
                    textAlign = TextAlign.Center, maxLines = 2, minLines = 2, overflow = TextOverflow.Ellipsis,
                )
            }
        }
    }
}

/** The estimate as a bar and in words, said to be an estimate. */
@Composable
fun OrderMeter(t: OrderTrack) {
    val c = Divan.colors
    val p = progressOf(t)
    val end = endOf(t.root)
    val stage = stageOf(t)
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            Text(
                when (end) {
                    OrderEnd.FAILED -> "ناموفق ماند؛ تا حدود $p٪ رسیده بود"
                    OrderEnd.CANCELLED -> "لغو شد؛ تا حدود $p٪ رسیده بود"
                    OrderEnd.NONE -> if (stage == OrderStage.DONE) "تمام شد" else "حدود $p٪"
                },
                style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold),
                color = when (end) { OrderEnd.FAILED -> c.negative; OrderEnd.CANCELLED -> c.textSecondary; else -> c.textPrimary },
            )
            if (end == OrderEnd.NONE && stage != OrderStage.DONE) Text("تخمینی", style = Divan.type.micro, color = c.textMuted)
        }
        MeterBar(p.toDouble(), tone = when { end == OrderEnd.FAILED -> BarTone.NEG; end == OrderEnd.CANCELLED -> BarTone.SILVER; stage == OrderStage.DONE -> BarTone.POS; else -> BarTone.GOLD })
    }
}

/** Who holds it now: the path from its assignee down to whoever works on it, the first of them and how many more. */
@Composable
fun HolderLine(t: OrderTrack) {
    val c = Divan.colors
    val holders = holdersOf(t)
    val stage = stageOf(t)
    val end = endOf(t.root)
    val text: AnnotatedString = when {
        end != OrderEnd.NONE -> buildAnnotatedString { append(reasonOf(t)?.let { "دلیل: $it" } ?: if (end == OrderEnd.FAILED) "دلیلی ثبت نشده؛ رویدادهایش را ببین." else "لغو شد.") }
        stage == OrderStage.DONE -> buildAnnotatedString { append("بسته شد؛ چیزی منتظر تو نیست.") }
        stage == OrderStage.DELIVERED -> buildAnnotatedString { append("منتظر نگاه تو: خروجی را ببین و امتیاز بده تا بسته شود.") }
        holders.isEmpty() -> buildAnnotatedString { append("در صف؛ هنوز کسی برنداشته.") }
        stage == OrderStage.RECEIVED -> buildAnnotatedString { append("در صف "); append(t.root.assignee?.titleFa ?: "مجری"); append("؛ هنوز برنداشته.") }
        else -> buildAnnotatedString {
            append("الان دست ")
            pathText(holders.first())
            if (holders.size > 1) append(" و ${holders.size - 1} نفر دیگر")
        }
    }
    Row(verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        DIcon(
            when { end != OrderEnd.NONE -> DivanIcon.URGENT; stage >= OrderStage.DELIVERED -> DivanIcon.OWNER; else -> DivanIcon.DELEGATE },
            Modifier.padding(top = 2.dp), size = 15.dp, tint = if (end == OrderEnd.FAILED) c.negative else c.textMuted,
        )
        Text(text, style = Divan.type.caption, color = if (end == OrderEnd.FAILED) c.negative else c.textSecondary, maxLines = 3, overflow = TextOverflow.Ellipsis)
    }
}

/** "مدیرعامل ← مدیر رشد ← تحلیلگر کمپین": the titles, the delegation arrow pointing the way the order went. */
private fun AnnotatedString.Builder.pathText(path: List<EmployeeRef>) {
    path.forEachIndexed { i, e ->
        if (i > 0) append(" ← ")
        pushStyle(androidx.compose.ui.text.SpanStyle(fontWeight = if (i == path.lastIndex) FontWeight.SemiBold else FontWeight.Normal))
        append(e.titleFa)
        pop()
    }
}

/** Its outputs, each a way into Outputs. */
@Composable
fun OutputsRow(t: OrderTrack) {
    if (t.deliverables.isEmpty()) return
    val nav = LocalNav.current
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        for (ref in t.deliverables.take(3)) RefButton("دیدن خروجی", ref, DivanIcon.DELIVERABLE) { nav.go("outputs/$ref") }
    }
}

/** A gold-ink action that names a ref in Latin figures (a plain button's text would draw it in Persian digits). */
@Composable
fun RefButton(label: String, ref: String, icon: DivanIcon, modifier: Modifier = Modifier, onClick: () -> Unit) {
    val c = Divan.colors
    Row(
        modifier.heightIn(min = 40.dp).clip(RoundedCornerShape(Radius.control)).background(c.softGold).clickable(role = Role.Button, onClick = onClick).padding(horizontal = 12.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        DIcon(icon, size = 18.dp, tint = c.goldInk)
        Text(buildAnnotatedString { append("$label "); fig(ref, weight = FontWeight.Bold) }, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.goldInk)
        Spacer(Modifier.weight(1f))
        DIcon(DivanIcon.NEXT, size = 14.dp, tint = c.goldInk)
    }
}

// --------------------------------------------------------------- the page --
/** On the order's own page: the stepper, the estimate, who holds it and its outputs, with the stream's state. */
@Composable
fun OrderTrackerCard(t: OrderTrack) {
    val live = LocalLive.current
    HqCard(Modifier.fillMaxWidth(), tahrir = stageOf(t) == OrderStage.DELIVERED) {
        SectionTitle("پیگیری فرمان", note = "مرحله، پیشرفت تخمینی و این‌که الان دست کیست") {
            when (live.state) {
                StreamState.LIVE -> Pill("زنده", Tone.POS, live = true)
                StreamState.CONNECTING -> Pill("در حال وصل", Tone.NEUTRAL, dot = true)
                StreamState.OFFLINE -> Pill("قطع؛ خودکار وصل میشود", Tone.WARN, dot = true)
            }
        }
        Spacer(Modifier.height(Space.md))
        Column(verticalArrangement = Arrangement.spacedBy(Space.sm)) {
            OrderStepper(t)
            OrderMeter(t)
            HolderLine(t)
            OutputsRow(t)
        }
    }
}

/** The order's life, newest first: its events, its children's, and its runs' starts, step summaries and ends. Live from the stream. */
@Composable
fun TimelineCard(t: OrderTrack) {
    val c = Divan.colors
    val nav = LocalNav.current
    val moments = remember(t) { timelineOf(t) }
    var all by rememberSaveable { mutableStateOf(false) }
    if (moments.isEmpty()) return
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("روند کار", note = "رویدادها و قدم‌های اجرا، تازه‌ترین بالا؛ فقط خلاصه")
        Spacer(Modifier.height(Space.sm))
        val shown = if (all) moments else moments.take(10)
        var day: String? = null
        Column(Modifier.smoothSize()) {
            shown.forEachIndexed { i, m ->
                val d = ownerDay(m.at)
                if (d != day) {
                    day = d
                    Text(jDate(m.at), style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = c.textMuted, modifier = Modifier.padding(top = if (i == 0) 0.dp else 8.dp, bottom = 4.dp))
                }
                val (icon, tint) = momentIcon(m.kind)
                val ref = m.parts.firstOrNull { it.fig && Regex("^[WO]-\\d+$").matches(it.text) }?.text
                Row(
                    Modifier.fillMaxWidth().clip(RoundedCornerShape(Radius.small))
                        .then(if (ref != null) Modifier.clickable { com.coinepro.hq.ui.v17.refRoute(ref)?.let(nav::go) } else Modifier)
                        .padding(vertical = 5.dp, horizontal = 2.dp),
                    verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    com.coinepro.hq.designsystem.Fig(jTime(m.at), style = Divan.type.figureSmall, color = c.textMuted, modifier = Modifier.width(38.dp).padding(top = 2.dp))
                    Box(Modifier.padding(top = 1.dp).size(22.dp).clip(CircleShape).background(tint.copy(alpha = 0.12f)), contentAlignment = Alignment.Center) { DIcon(icon, size = 12.dp, tint = tint) }
                    Text(
                        partsText(m.parts), style = if (m.sub) Divan.type.caption else Divan.type.small, color = if (m.sub) c.textSecondary else c.textPrimary,
                        modifier = Modifier.weight(1f).padding(start = if (m.sub) 6.dp else 0.dp), maxLines = 3, overflow = TextOverflow.Ellipsis,
                    )
                }
            }
        }
        if (moments.size > 10) HqButton(if (all) "کمتر" else "همه‌ی ${moments.size} مورد", { all = !all }, variant = BtnVariant.TEXT, size = BtnSize.SM)
    }
}

/** A timeline line's words, its figures Latin. */
fun partsText(parts: List<Part>): AnnotatedString = buildAnnotatedString { for (p in parts) if (p.fig) fig(p.text) else append(p.text) }

@Composable
private fun momentIcon(kind: String): Pair<DivanIcon, Color> {
    val c = Divan.colors
    return when {
        kind == "created" -> DivanIcon.COMMAND to c.goldInk
        kind == "accepted" -> DivanIcon.AGENT to c.goldInk
        kind == "delegated" -> DivanIcon.DELEGATE to c.lapis
        kind == "progress" -> DivanIcon.CHART to c.silverInk
        kind == "delivered" -> DivanIcon.DELIVERABLE to c.positive
        kind == "completed" -> DivanIcon.SEAL to c.positive
        kind == "failed" || kind == "declined" -> DivanIcon.URGENT to c.negative
        kind == "cancelled" -> DivanIcon.CLOSE to c.textMuted
        kind == "run.started" -> DivanIcon.AGENT to c.silverInk
        kind == "run.step" -> DivanIcon.TASK to c.silverInk
        kind == "run.finished:done" -> DivanIcon.SEAL to c.positive
        kind.startsWith("run.finished") -> DivanIcon.URGENT to c.warning
        else -> DivanIcon.INFO to c.silverInk
    }
}

// ------------------------------------------------------------------ home --
/** The home card: the orders on their way (or the last delivered), each with its stage and estimate; the way to all of them. */
@Composable
fun HomeOrdersCard(onNewOrder: () -> Unit) {
    val nav = LocalNav.current
    val c = Divan.colors
    val q = rememberOrders()
    val list = q.data
    val active = list.orEmpty().filter { it.status in ACTIVE }
    val shown = (active + list.orEmpty().filter { it.status in DELIVERED && it !in active }).take(3)
    HqCard(Modifier.fillMaxWidth(), tahrir = list.orEmpty().any { it.status == "delivered" }) {
        SectionTitle("فرمان‌های من", note = if (list == null) "از ثبت تا تحویل، زنده" else if (active.isEmpty()) "فرمانی در جریان نیست" else "${active.size} فرمان در جریان") {
            HqButton("همه", { nav.go("orders") }, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.NEXT)
        }
        when {
            list == null -> Skeleton(Modifier.fillMaxWidth().height(150.dp).padding(top = 8.dp), radius = Radius.tile)
            shown.isEmpty() -> Column(Modifier.padding(top = 8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("هر فرمانی بدهی این‌جا مرحله‌به‌مرحله دیده میشود.", style = Divan.type.caption, color = c.textMuted)
                HqButton("فرمان تازه", onNewOrder, size = BtnSize.SM, icon = DivanIcon.COMMAND)
            }
            else -> Column(Modifier.padding(top = 6.dp)) {
                shown.forEachIndexed { i, w ->
                    if (i > 0) HorizontalDivider(color = c.lineDivider)
                    HomeOrderRow(w) { nav.go("work/${w.id}") }
                }
            }
        }
    }
}

@Composable
private fun HomeOrderRow(w: Work, onClick: () -> Unit) {
    val c = Divan.colors
    val t = rememberTrack(w.id).data
    Column(Modifier.fillMaxWidth().clickable(role = Role.Button, onClick = onClick).padding(vertical = 10.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            CompanyMark(w.company, height = 12.dp, mono = true, ink = c.textSecondary)
            Text(w.title, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
            if (t == null) Skeleton(Modifier.size(width = 64.dp, height = 14.dp))
            else {
                val end = endOf(t.root)
                val stage = stageOf(t)
                val label = if (stage == OrderStage.TAKEN) takenFa(t.root) else stage.fa
                Text(label, style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = when { end == OrderEnd.FAILED -> c.negative; stage == OrderStage.DELIVERED -> c.goldInk; else -> c.textSecondary })
            }
        }
        if (t == null) Skeleton(Modifier.fillMaxWidth().height(6.dp))
        else Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            val p = progressOf(t)
            Box(Modifier.weight(1f)) { MeterBar(p.toDouble(), tone = if (stageOf(t) == OrderStage.DONE) BarTone.POS else BarTone.GOLD) }
            Text("حدود $p٪، ${ago(lastActivityOf(t))}", style = Divan.type.micro, color = c.textMuted)
        }
    }
}
