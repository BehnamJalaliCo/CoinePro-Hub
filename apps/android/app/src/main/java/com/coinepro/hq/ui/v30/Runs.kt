package com.coinepro.hq.ui.v30

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.background
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.costText
import com.coinepro.hq.core.data.lineRunEnded
import com.coinepro.hq.core.data.lineRunStateFa
import com.coinepro.hq.core.data.lineRunStateTone
import com.coinepro.hq.core.data.platformFa
import com.coinepro.hq.core.data.runTriggerFa
import com.coinepro.hq.core.data.stepKindFa
import com.coinepro.hq.core.data.stepKindIcon
import com.coinepro.hq.core.data.stepStateFa
import com.coinepro.hq.core.data.stepStateTone
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.format.instant
import com.coinepro.hq.core.format.jDateTime
import com.coinepro.hq.core.format.jTime
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.Line
import com.coinepro.hq.core.net.LineRun
import com.coinepro.hq.core.net.StepRun
import com.coinepro.hq.core.net.gated
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.Chevron
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.Expand
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.itemMotion
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberOnScreen
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v29.CoName
import com.coinepro.hq.ui.v29.Para
import com.coinepro.hq.ui.v29.plain
import kotlinx.coroutines.delay

// Contract §30.3 ⟨1.12⟩: a line's runs, and one run as a timeline of its steps: each with its state, time and cost, and what it made shown
// as it deserves. A run waiting for the owner's seal asks for it here («تأیید و انتشار» or «رد»); any finished step can run again.

/** «چند ثانیه» · «2 دقیقه» between two instants. */
fun durationFa(startIso: String?, endIso: String?): String? {
    val a = instant(startIso) ?: return null
    val b = instant(endIso) ?: return null
    val s = (b.epochSecond - a.epochSecond).coerceAtLeast(0)
    return when {
        s < 2 -> "کمتر از یک ثانیه"
        s < 60 -> "$s ثانیه"
        s < 3600 -> "${s / 60} دقیقه"
        else -> "${s / 3600} ساعت"
    }
}

// ----------------------------------------------------------------- the list --
/** The runs of one line, newest first. */
@Composable
fun LineRunsScreen(ref: String) {
    val nav = LocalNav.current
    val lq = rememberQuery("line:$ref", "lines", maxAgeMs = 20_000) { gated(HubFeature.LINES) { line(ref) } }
    val q = rememberQuery("line-runs:$ref", "line-runs", "lines", maxAgeMs = 15_000) { gated(HubFeature.LINES) { lineRuns(ref) } }
    val r = refresher(q, lq)
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item { PageHeader("اجراهای خط", eyebrow = lq.data?.titleFa) }
        item {
            HqButton("خود خط", { nav.go("lines/$ref") }, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.NEXT)
        }
        val list = q.data
        when {
            list == null && q.error != null -> item { ErrorBlock(q.error, { q.refresh() }) }
            list == null -> item { Skeleton(Modifier.fillMaxWidth().height(140.dp), radius = 16.dp) }
            list.isEmpty() -> item { Empty("هنوز اجرایی نبوده", icon = DivanIcon.RESUME, body = "در صفحه‌ی خط «آزمایش کامل» را بزن تا اولین اجرا بیاید.") }
            else -> items(list, key = { it.ref }) { x -> Box(itemMotion()) { RunRow(x) { nav.go("line-runs/${x.ref}") } } }
        }
    }
}

/** One run in a list: its state, how it started, when, what it cost and what it published. */
@Composable
fun RunRow(x: LineRun, onClick: () -> Unit) {
    val c = Divan.colors
    HqCard(Modifier.fillMaxWidth(), onClick = onClick) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(plain(x.titleFa ?: (runTriggerFa(x.trigger) + "، " + jDateTime(x.at))), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), maxLines = 2)
                Text(plain(runTriggerFa(x.trigger) + "، " + ago(x.at)), style = Divan.type.caption, color = c.textMuted)
            }
            if (x.dry) Pill("آزمایشی", Tone.LAPIS)
            Pill(lineRunStateFa(x.state), lineRunStateTone(x.state), dot = true, live = x.state == "running")
        }
        val cost = costText(x.cost.tokens, x.cost.usdEquiv)
        val tail = listOfNotNull(cost.ifBlank { null }, x.published.takeIf { it.isNotEmpty() }?.let { "${it.size} انتشار" }).joinToString("، ")
        if (tail.isNotBlank()) Text(plain(tail), style = Divan.type.micro, color = c.textMuted, modifier = Modifier.padding(top = 6.dp))
    }
}

// ----------------------------------------------------------------- one run --
/** One run: header, the seal when it waits, and the timeline of its steps. [open0] names the steps that start open. */
@Composable
fun LineRunScreen(ref: String, open0: Set<String>? = null) {
    val q = rememberQuery("line-run:$ref", "line-runs", "lines", maxAgeMs = 10_000) { gated(HubFeature.LINES) { lineRun(ref) } }
    val run = q.data
    val lref = run?.line.orEmpty()
    val lq = rememberQuery("line:$lref", "lines", maxAgeMs = 30_000) { if (lref.isBlank()) null else gated(HubFeature.LINES) { line(lref) } }
    val onScreen = rememberOnScreen()
    // A moving run is read again every few seconds while the page is on screen (the stream's `line_run.` events refresh it too).
    LaunchedEffect(run?.state, onScreen) {
        while (onScreen && (run?.state == "queued" || run?.state == "running")) { delay(5_000); q.refresh() }
    }
    val r = refresher(q, lq)
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        when {
            run == null && q.error != null -> item { ErrorBlock(q.error, { q.refresh() }) }
            run == null -> item { Skeleton(Modifier.fillMaxWidth().height(260.dp), radius = 16.dp) }
            else -> item(key = "run") { RunBody(run, lq.data, open0) }
        }
    }
}

/** The run as a page body (also what the screenshot draws). */
@Composable
fun RunBody(run: LineRun, line: Line?, open0: Set<String>? = null) {
    val env = LocalEnv.current
    val nav = LocalNav.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val cancel = rememberAction()
    val opened = remember(run.ref) { mutableStateMapOf<String, Boolean>() }
    val lastDone = run.steps.lastOrNull { it.state == "done" }?.key
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        PageHeader(line?.titleFa ?: run.titleFa ?: "اجرای خط", eyebrow = "اجرای " + runTriggerFa(run.trigger))
        HqCard(Modifier.fillMaxWidth()) {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    val co = line?.company ?: run.company
                    if (co != null) CoName(co, Modifier.weight(1f), height = 13.dp, color = c.textPrimary, bold = true) else Box(Modifier.weight(1f))
                    if (run.dry) Pill("آزمایشی؛ چیزی منتشر نمیشود", Tone.LAPIS)
                    Pill(lineRunStateFa(run.state), lineRunStateTone(run.state), dot = true, live = run.state == "running")
                }
                Text(plain(buildString {
                    append(jDateTime(run.at))
                    durationFa(run.at, run.endedAt)?.let { append("، ").append(it) }
                    val cost = costText(run.cost.tokens, run.cost.usdEquiv)
                    if (cost.isNotBlank()) append("، ").append(cost)
                }), style = Divan.type.caption, color = c.textMuted)
                if (run.noteFa.isNotBlank()) Para(run.noteFa)
                if (line != null) Text(plain(platformFa(line.platform) + (if (line.channel.subject.isNotBlank()) "، " + line.channel.subject else "")), style = Divan.type.caption, color = c.textSecondary)
                if (!lineRunEnded(run.state)) HqButton("لغو اجرا", {
                    cancel.run { env.api.cancelLineRun(run.ref); env.cache.invalidate("line-runs", "lines"); toasts.ok("اجرا لغو شد.") }
                }, variant = BtnVariant.GHOST, size = BtnSize.SM, icon = DivanIcon.CLOSE, loading = cancel.busy)
            }
        }
        if (run.state == "waiting") SealCard(run)
        if (run.published.isNotEmpty()) PublishedCard(run)
        SectionTitle("مرحله‌ها", note = "هر مرحله با زمان، هزینه و خروجی‌اش")
        Column {
            run.steps.forEachIndexed { i, s ->
                val def = line?.steps?.firstOrNull { it.key == s.key }
                val open = opened[s.key] ?: (open0?.contains(s.key) ?: (s.state == "waiting" || s.state == "failed" || s.key == lastDone))
                TimelineStep(
                    run, s, title = def?.titleFa?.ifBlank { null } ?: stepKindFa(s.kind), last = i == run.steps.lastIndex, open = open,
                    onOpen = { opened[s.key] = !open },
                    canRerun = s.state in setOf("done", "failed") && (lineRunEnded(run.state) || run.state == "waiting"),
                    onRerun = { nav.go("line-runs/$it") },
                )
            }
        }
        run.metrics.let { m ->
            if (m.h24 != null || m.d7 != null) {
                SectionTitle("نتیجه‌ی انتشار", note = "عددهای پست، بعد از یک روز و یک هفته")
                m.h24?.let { Text("بعد از ۲۴ ساعت", style = Divan.type.caption, color = c.textMuted); DataTable(it) }
                m.d7?.let { Text("بعد از ۷ روز", style = Divan.type.caption, color = c.textMuted); DataTable(it) }
            }
        }
    }
}

/** A run waiting for the owner: publish it, or refuse it with a reason (the line learns from the reason). */
@Composable
fun SealCard(run: LineRun) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val yes = rememberAction()
    val no = rememberAction()
    var note by rememberSaveable(run.ref) { mutableStateOf("") }
    HqCard(Modifier.fillMaxWidth(), color = c.softGold, tahrir = true) {
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                DIcon(DivanIcon.SEAL, size = 20.dp, tint = c.goldInk)
                Text("این اجرا منتظر مُهر توست", style = Divan.type.bodyStrong, color = c.textPrimary)
            }
            Text("خروجی‌ها را در پایین ببین. با مُهر تو منتشر میشود؛ ردش کنی چیزی منتشر نمیشود.", style = Divan.type.caption, color = c.textSecondary)
            HqTextField(note, { note = it }, "دلیل (اختیاری)", Modifier.fillMaxWidth(), singleLine = false, minLines = 2, maxLength = 500)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                HqButton("تأیید و انتشار", {
                    yes.run {
                        env.api.sealLineRun(run.ref, true, note.trim().ifBlank { null })
                        env.cache.invalidate("line-runs", "lines", "decisions", "inbox")
                        toasts.ok("مُهر شد؛ منتشر میشود.")
                    }
                }, Modifier.weight(1f), variant = BtnVariant.PRIMARY, icon = DivanIcon.SEAL, loading = yes.busy, enabled = !no.busy)
                HqButton("رد", {
                    no.run {
                        env.api.sealLineRun(run.ref, false, note.trim().ifBlank { null })
                        env.cache.invalidate("line-runs", "lines", "decisions", "inbox")
                        toasts.ok("رد شد؛ چیزی منتشر نمیشود.")
                    }
                }, variant = BtnVariant.DANGER, icon = DivanIcon.REJECT, loading = no.busy, enabled = !yes.busy)
            }
        }
    }
}

/** What the run published, each with its link. */
@Composable
private fun PublishedCard(run: LineRun) {
    val c = Divan.colors
    val uri = LocalUriHandler.current
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("منتشر شد")
        Column(Modifier.padding(top = 6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            for (p in run.published) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(plain(platformFa(p.platform).takeIf { it != "خروجی" } ?: p.platform), style = Divan.type.small, modifier = Modifier.weight(1f))
                p.at?.let { Text(jTime(it), style = Divan.type.caption, color = c.textMuted) }
                p.url?.takeIf { it.startsWith("https://") }?.let { u -> HqButton("باز کن", { runCatching { uri.openUri(u) } }, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.NEXT) }
            }
        }
    }
}

/** One step on the timeline: a dot and a rail on the start side; its card beside it. */
@Composable
fun TimelineStep(run: LineRun, s: StepRun, title: String, last: Boolean, open: Boolean, onOpen: () -> Unit, canRerun: Boolean, onRerun: (String) -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val again = rememberAction()
    val dot = when (s.state) {
        "done" -> c.positive
        "failed" -> c.negative
        "waiting" -> c.warning
        "running" -> c.goldFill
        else -> c.lineStrong
    }
    val rail = c.lineStrong
    Row(
        Modifier.fillMaxWidth().drawBehind {
            val x = if (layoutDirection == LayoutDirection.Rtl) size.width - 10.dp.toPx() else 10.dp.toPx()
            drawLine(rail, Offset(x, 20.dp.toPx()), Offset(x, if (last) 20.dp.toPx() else size.height), strokeWidth = 2.dp.toPx())
        },
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Box(Modifier.width(20.dp).padding(top = 14.dp), contentAlignment = Alignment.TopCenter) {
            Box(Modifier.size(12.dp).clip(CircleShape).background(dot))
        }
        Column(Modifier.weight(1f).padding(bottom = 12.dp)) {
            HqCard(Modifier.fillMaxWidth(), padding = androidx.compose.foundation.layout.PaddingValues(12.dp)) {
                Row(
                    Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).clickable(role = Role.Button, onClickLabel = if (open) "بستن" else "باز کردن", onClick = onOpen),
                    verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    DIcon(stepKindIcon(s.kind), size = 20.dp, tint = c.textSecondary)
                    Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Text(plain(title), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), maxLines = 2)
                        val facts = listOfNotNull(
                            s.startedAt?.let { jTime(it) }, durationFa(s.startedAt, s.endedAt),
                            costText(s.tokens, s.usdEquiv).ifBlank { null }, if (s.attempt > 1) "تلاش ${s.attempt}" else null,
                        ).joinToString("، ")
                        if (facts.isNotBlank()) Text(plain(facts), style = Divan.type.micro, color = c.textMuted)
                    }
                    Pill(stepStateFa(s.state), stepStateTone(s.state), dot = true, live = s.state == "running")
                    Chevron(open, tint = c.textMuted)
                }
                Expand(open) {
                    Column(Modifier.padding(top = 12.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        s.errorFa?.takeIf { it.isNotBlank() }?.let { Para(it, color = c.negative) }
                        s.via?.takeIf { it.isNotBlank() }?.let { Text(plain("با: $it"), style = Divan.type.micro, color = c.textMuted) }
                        if (s.state == "pending") Text("هنوز نوبتش نرسیده.", style = Divan.type.caption, color = c.textMuted)
                        else OutputView(s.output)
                        if (canRerun) HqButton("اجرای دوباره از این مرحله", {
                            again.run {
                                val made = env.api.rerunLineRun(run.ref, s.key)
                                env.cache.invalidate("line-runs", "lines")
                                toasts.ok("اجرای تازه از همین مرحله شروع شد.")
                                onRerun(made.ref)
                            }
                        }, Modifier.fillMaxWidth(), variant = BtnVariant.SILVER, size = BtnSize.SM, icon = DivanIcon.REFRESH, loading = again.busy)
                    }
                }
            }
        }
    }
}
