package com.coinepro.hq.ui.automation

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.faNum
import com.coinepro.hq.core.data.lineRunStateFa
import com.coinepro.hq.core.data.lineRunStateTone
import com.coinepro.hq.core.data.resultsRowsFa
import com.coinepro.hq.core.data.stepCostFa
import com.coinepro.hq.core.data.stepKindFa
import com.coinepro.hq.core.data.stepKindIcon
import com.coinepro.hq.core.data.stepStateFa
import com.coinepro.hq.core.data.stepStateTone
import com.coinepro.hq.core.data.stepToolFa
import com.coinepro.hq.core.data.versionFa
import com.coinepro.hq.core.format.jDateTime
import com.coinepro.hq.core.format.jTime
import com.coinepro.hq.core.format.usd
import com.coinepro.hq.core.net.LineRun
import com.coinepro.hq.core.net.StepFile
import com.coinepro.hq.core.net.StepRun
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.Text
import com.coinepro.hq.designsystem.facts
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.look.FilesStrip
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberOnScreen
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v29.plain
import kotlinx.coroutines.delay

// Contract §59.8 ⟨1.37⟩: one run of a flow, as a timeline. Its head says the day's topic, where it stands, what it cost and how long it
// took, where it went out (the reel's and the story's links) and how it did. Then each step in order: its state, who did it with what
// model at what effort, when and at what cost, and what it left (the script and caption.txt and comment.txt read in place, the voice to
// play, the cover, the final video). A step that failed says why in one plain line, with «دوباره از همین قدم» and «رد کردن این نوبت».

@Composable
fun FlowRunScreen(ref: String) {
    val env = LocalEnv.current
    val nav = LocalNav.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val q = rememberQuery("line-run:$ref", "lines", "automations", maxAgeMs = 5_000) { lineRun(ref) }
    val run: LineRun? = q.data
    val onScreen = rememberOnScreen()
    // While it runs: the stream says each step, and a quiet read every 15 s keeps it true if the stream is away.
    LaunchedEffect(env, ref) { env.stream.events.collect { e -> if (e.type.startsWith("automation.") || e.type.startsWith("line_run.")) q.refresh() } }
    LaunchedEffect(ref, run?.state, onScreen) { while (onScreen && run != null && run.state in setOf("queued", "running", "waiting")) { delay(15_000); q.refresh() } }
    val retry = rememberAction()
    val skip = rememberAction()
    var which by remember { mutableStateOf<String?>(null) }
    Page(onRefresh = { q.refresh() }, refreshing = q.state.refreshing) {
        item(key = "head") {
            PageHeader(run?.topicFa?.ifBlank { null } ?: run?.titleFa?.ifBlank { null } ?: "اجرای کارگروه", eyebrow = run?.let { facts(it.playbookFa ?: it.titleFa, it.companyFa, it.version?.let { v -> versionFa(v) }).text } ?: "خط زمان")
        }
        when {
            run == null && q.error != null -> item(key = "err") { ErrorBlock(q.error, { q.refresh() }) }
            run == null -> item(key = "sk") { Skeleton(Modifier.fillMaxWidth().height(420.dp), radius = 16.dp) }
            else -> {
                item(key = "sum") { RunHead(run) }
                if (run.results != null || run.published.isNotEmpty()) item(key = "results") { ResultsCard(run) }
                item(key = "steps") {
                    HqCard(Modifier.fillMaxWidth().testTag("run-timeline")) {
                        SectionTitle("قدم‌ها", note = "${faNum(run.steps.count { it.state == "done" })} از ${faNum(run.steps.size)}")
                        Column(Modifier.padding(top = 8.dp)) {
                            run.steps.forEachIndexed { i, s ->
                                StepNode(
                                    s, last = i == run.steps.lastIndex,
                                    onRetry = { which = s.key; retry.run { val out = env.api.rerunLineRun(ref, s.key); env.cache.invalidate("automations"); toasts.ok("از «${s.titleFa ?: stepKindFa(s.kind)}» دوباره شروع شد."); nav.go("flow-run/${out.ref}") } },
                                    onSkip = { which = s.key; skip.run { q.set(env.api.skipLineRun(ref)); env.cache.invalidate("automations"); toasts.ok("این نوبت رد شد؛ موضوعش برای روز دیگری آزاد شد.") } },
                                    busy = (retry.busy || skip.busy) && which == s.key,
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun RunHead(run: LineRun) {
    val c = Divan.colors
    HqCard(Modifier.fillMaxWidth().testTag("run-head")) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Pill(lineRunStateFa(run.state), lineRunStateTone(run.state), live = run.state == "running", dot = run.state != "running")
            Text(
                remember(run) { facts(run.at?.let { jDateTime(it) }, run.minutes?.let { "${faNum(Math.round(it).toInt())} دقیقه" }, (run.cost.usd)?.let { usd(it) }) },
                style = Divan.type.caption, color = c.textSecondary, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f),
            )
        }
        if (run.noteFa.isNotBlank()) Text(plain(run.noteFa), style = Divan.type.small, color = c.textPrimary, modifier = Modifier.padding(top = 8.dp))
    }
}

/** Where it went out (each link opens Instagram) and the figures (§59.9), «—» for what IG-Hub does not give yet. */
@Composable
private fun ResultsCard(run: LineRun) {
    val c = Divan.colors
    val context = LocalContext.current
    HqCard(Modifier.fillMaxWidth().testTag("run-results")) {
        SectionTitle("نتیجه", note = run.results?.readAt?.let { "خوانده شد ${jTime(it)}" })
        val links = run.published.mapNotNull { p -> (p.permalink ?: p.url)?.let { (if (p.kind == "story") "استوری" else "ریلز") to it } } +
            listOfNotNull(run.results?.permalink?.takeIf { pl -> run.published.none { (it.permalink ?: it.url) == pl } }?.let { "ریلز" to it })
        if (links.isNotEmpty()) FlowRow(Modifier.padding(top = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            for ((fa, url) in links) HqButton(fa, { runCatching { context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)) } }, variant = BtnVariant.SECONDARY, size = BtnSize.SM, icon = DivanIcon.SHARE)
        }
        FlowRow(Modifier.padding(top = 10.dp), horizontalArrangement = Arrangement.spacedBy(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            for ((label, value) in resultsRowsFa(run.results)) Column {
                Text(value, style = Divan.type.bodyStrong, color = c.textPrimary)
                Text(label, style = Divan.type.micro, color = c.textMuted)
            }
        }
    }
}

/** One step on the timeline: a dot on the line (tinted by its state), its name, who and with what, when and how much; what it left. */
@Composable
private fun StepNode(s: StepRun, last: Boolean, onRetry: () -> Unit, onSkip: () -> Unit, busy: Boolean) {
    val c = Divan.colors
    var open by rememberSaveable(s.key) { mutableStateOf(s.state == "failed" || s.state == "running") }
    val ink = when (s.state) { "done" -> c.positive; "failed" -> c.negative; "running", "waiting" -> c.silverInk; else -> c.lineDivider }
    Row(Modifier.fillMaxWidth().height(IntrinsicSize.Min).testTag("run-step"), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        Column(Modifier.width(18.dp).fillMaxHeight(), horizontalAlignment = Alignment.CenterHorizontally) {
            Box(Modifier.padding(top = 4.dp).size(12.dp).clip(CircleShape).background(ink))
            if (!last) Box(Modifier.width(2.dp).weight(1f).background(c.lineDivider))
        }
        Column(Modifier.weight(1f).padding(bottom = 14.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Row(
                Modifier.fillMaxWidth().clickable(role = Role.Button, onClickLabel = if (open) "ببند" else "باز کن") { open = !open },
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                DIcon(stepKindIcon(s.kind), size = 14.dp, tint = c.textMuted)
                Text(plain(s.titleFa?.ifBlank { null } ?: stepKindFa(s.kind)), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
                Pill(stepStateFa(s.state), stepStateTone(s.state), live = s.state == "running", dot = s.state != "running")
            }
            Text(
                remember(s) { facts(s.seatFa, stepToolFa(s.helper ?: s.via, s.model, s.effort), stepCostFa(s.costUsd, s.startedAt, s.endedAt), s.attempt.takeIf { it > 1 }?.let { "بار ${faNum(it)}" }) },
                style = Divan.type.micro, color = c.textMuted, maxLines = 2, overflow = TextOverflow.Ellipsis,
            )
            if (s.state == "failed") {
                Text(plain(s.errorFa?.ifBlank { null } ?: "این قدم انجام نشد."), style = Divan.type.caption, color = c.negative, modifier = Modifier.testTag("step-error"))
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    HqButton("دوباره از همین قدم", onRetry, variant = BtnVariant.SECONDARY, size = BtnSize.SM, icon = DivanIcon.REFRESH, loading = busy)
                    HqButton("رد کردن این نوبت", onSkip, variant = BtnVariant.TEXT, size = BtnSize.SM)
                }
            }
            if (open) StepOutputs(s)
        }
    }
}

/** What a step left: text files read in place (scrolling inside a short box), media as tiles that play or open. */
@Composable
private fun StepOutputs(s: StepRun) {
    val c = Divan.colors
    val texts = s.outputs.filter { !it.text.isNullOrBlank() }
    val media = s.outputs.filter { it.text.isNullOrBlank() && it.id.isNotBlank() }
    val legacy = s.output.text?.takeIf { it.isNotBlank() && texts.isEmpty() }
    for (t in texts) TextOut(t.name, t.text.orEmpty())
    if (legacy != null) TextOut(null, legacy)
    if (media.isNotEmpty()) {
        val audio = media.filter { it.kind == "audio" }
        for (a in audio) com.coinepro.hq.ui.v18.AudioPlayer(a.id, a.name, compact = true)
        val rest = media.filter { it.kind != "audio" }
        if (rest.isNotEmpty()) FilesStrip(rest.map(StepFile::asFile))
    } else if (s.output.allFiles.isNotEmpty() && s.outputs.isEmpty()) {
        FilesStrip(s.output.allFiles.map { com.coinepro.hq.core.net.FileRef(id = it) })
    }
    if (texts.isEmpty() && media.isEmpty() && legacy == null && s.state == "done") Text("خروجی‌ای برای دیدن ندارد.", style = Divan.type.micro, color = c.textMuted)
}

@Composable
private fun TextOut(name: String?, text: String) {
    val c = Divan.colors
    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(c.tile).padding(10.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        if (!name.isNullOrBlank()) Text(name, style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = c.textMuted)
        Box(Modifier.heightIn(max = 220.dp).verticalScroll(rememberScrollState())) {
            com.coinepro.hq.ui.Selectable { Text(plain(text), style = Divan.type.caption, color = c.textPrimary) }
        }
    }
}
