package com.coinepro.hq.ui.session

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.key
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.ChatRow
import com.coinepro.hq.core.data.Revisions
import com.coinepro.hq.core.data.revisionOf
import com.coinepro.hq.core.data.revisions
import com.coinepro.hq.core.data.versionFa
import com.coinepro.hq.core.data.SessionEntry
import com.coinepro.hq.core.data.eventsCountFa
import com.coinepro.hq.core.data.eventsSpan
import com.coinepro.hq.core.data.faceOf
import com.coinepro.hq.core.data.goesOut
import com.coinepro.hq.core.data.isImage
import com.coinepro.hq.core.data.isVideo
import com.coinepro.hq.core.data.madeWithFa
import com.coinepro.hq.core.data.outputKindFa
import com.coinepro.hq.core.data.quietLine
import com.coinepro.hq.core.data.stepWithSpeaker
import com.coinepro.hq.core.format.jDateTime
import com.coinepro.hq.core.format.jTime
import com.coinepro.hq.core.net.Blocker
import com.coinepro.hq.core.net.Deliverable
import com.coinepro.hq.core.net.FileRef
import com.coinepro.hq.core.net.PublishPanel
import com.coinepro.hq.core.net.ReportOutput
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.Chevron
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.DrawnMark
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.Text
import com.coinepro.hq.designsystem.bidi
import com.coinepro.hq.designsystem.facts
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.sep
import com.coinepro.hq.designsystem.smoothSize
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.look.FilesStrip
import com.coinepro.hq.ui.outputs.PublishUnder
import com.coinepro.hq.ui.outputs.coverOf
import com.coinepro.hq.ui.outputs.kindFromMime
import com.coinepro.hq.ui.outputs.rememberPublishPanel
import com.coinepro.hq.ui.rememberQuery

// ⟨1.0.1⟩ Part C, the session's work timeline (C2.2, feature 14). The steps of the work are thin centred lines without a box («مدیر
// رسانه آمد | 09:30»): one step is its own line, several between two turns fold into one («۴ رویداد | 10:20–10:25») that opens to
// every line whole (never cut with «…»). An output is seen where it arrived: a calm ticked line with its title, then its files as a
// strip of tiles (features 29 and 30). What blocks the work is the «گره» card over the composer, never in the chat. No ref is ever a word.

/** A fact and its time on one centred line; the time (a clock, or a range «05:34–05:40») is one Latin run, a date is set as a sentence. */
private fun lineOf(text: String, time: String) = buildAnnotatedString {
    bidi(text)
    if (time.isNotBlank()) {
        sep()
        if (time.all { it.isDigit() || it == ':' || it == '–' }) fig(time) else bidi(time)
    }
}

/** A quiet line of the chat (when the session began, a word about its talk): centred, its words whole and its time after them. */
@Composable
internal fun QuietRow(text: String, at: String, date: Boolean = false) {
    val c = Divan.colors
    Text(
        remember(text, at, date) { lineOf(text, if (at.isBlank()) "" else if (date) jDateTime(at) else jTime(at)) },
        Modifier.fillMaxWidth().padding(horizontal = 12.dp), style = Divan.type.micro, color = c.textMuted, textAlign = TextAlign.Center,
    )
}

/**
 * The steps between two turns. One: the line itself, whole, centred, with its clock time. Several: one line, «۳ رویداد | 05:34–05:40»,
 * that opens to each line whole with its time (and who, when it came through someone). [whoOf] names the persona a step was written under.
 */
@Composable
internal fun EventsRow(r: ChatRow.Events, whoOf: (String) -> String) {
    val c = Divan.colors
    val steps = r.steps
    fun text(i: Int): String = steps[i].let { s -> stepWithSpeaker(quietLine(s.text), s.by?.let(whoOf)) }
    fun time(i: Int): String = steps[i].at.takeIf { it.isNotBlank() }?.let(::jTime).orEmpty()
    if (steps.size == 1) {
        Text(lineOf(text(0), time(0)), Modifier.fillMaxWidth().testTag("chat-event").padding(horizontal = 12.dp), style = Divan.type.micro, color = c.textMuted, textAlign = TextAlign.Center)
        return
    }
    var open by rememberSaveable(r.key) { mutableStateOf(false) }
    Column(Modifier.fillMaxWidth().testTag("chat-events").smoothSize(), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Row(
            Modifier.clip(RoundedCornerShape(8.dp)).clickable(role = Role.Button, onClickLabel = if (open) "ببند" else "همه‌ی رویدادها") { open = !open }.padding(horizontal = 10.dp, vertical = 4.dp),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            Text(lineOf(eventsCountFa(steps.size), eventsSpan(steps, ::jTime)), style = Divan.type.micro, color = c.textMuted, maxLines = 1)
            Chevron(open, size = 11.dp, tint = c.textMuted)
        }
        if (open) steps.indices.forEach { i ->
            Text(lineOf(text(i), time(i)), Modifier.fillMaxWidth().padding(horizontal = 12.dp), style = Divan.type.micro, color = c.textSecondary, textAlign = TextAlign.Center)
        }
    }
}

// ================================================================================================ the outputs ==
/** A session's output with what its page knows of it: its files (the deliverable's attachments) and where their publications stand. */
internal data class SessionOutput(val ref: String, val titleFa: String, val kind: String, val d: Deliverable?, val loading: Boolean, val panel: PublishPanel?) {
    val files: List<FileRef> get() = d?.attachments.orEmpty().map(::kindFromMime).filter { it.id.isNotBlank() }
}

private const val OUTPUTS_SHOWN = 12

/** The deliverable and the publish panel of each output of the session: the same cached reads the output's own page uses. */
@Composable
internal fun rememberSessionOutputs(outputs: List<ReportOutput>): List<SessionOutput> {
    val out = ArrayList<SessionOutput>()
    for (o in outputs.take(OUTPUTS_SHOWN)) key(o.ref) {
        val q = rememberQuery("deliverable:${o.ref}", "deliverables") { deliverable(o.ref) }
        val d = q.data
        val publishable = d?.attachments.orEmpty().map(::kindFromMime).any(::goesOut)
        val panel = if (publishable) rememberPublishPanel(o.ref).data else null
        out += SessionOutput(o.ref, o.titleFa, o.kind, d, q.loading, panel)
    }
    return out
}

/** ⟨1.35⟩ §57.6 the chains of versions among a session's outputs: the report's word on each, else its deliverable's `produced_with`. */
@Composable
internal fun rememberRevisions(outputs: List<ReportOutput>, outs: List<SessionOutput>): Revisions {
    val made = outs.map { it.ref to it.d?.producedWith }
    return remember(outputs, made) {
        val pw = made.toMap()
        val byRef = outputs.associateBy { it.ref }
        revisions(outputs.map { it.ref }) { r -> byRef[r]?.let { revisionOf(it, pw[r]) } }
    }
}

/**
 * One output in the talk, where it arrived: a calm ticked line with its title and «باز کن», then its files as a strip of tiles (a
 * video plays in place). Under the file that goes out (its video, else its first picture), its quiet «تأیید و انتشار» or where its
 * publication stands; what the session waits on ([lead]) is in the decision bar instead; a reel's cover says so. The last quiet line
 * says how it was made.
 */
@Composable
internal fun OutputTiles(o: SessionOutput, lead: String?, onAsk: (String, FileRef) -> Unit, version: Int? = null) {
    val c = Divan.colors
    val nav = LocalNav.current
    val files = o.files
    val main = faceOf(files)?.id
    val cover = if (files.any(::isVideo)) coverOf(files.filter(::isImage))?.id else null
    Column(Modifier.fillMaxWidth().testTag("chat-output"), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            DrawnMark(true, c.positive, size = 14.dp)
            Text(
                remember(o.kind, o.titleFa, files.isEmpty()) {
                    buildAnnotatedString {
                        append(if (o.kind == "partial") "خروجی ناقص رسید" else "خروجی تحویل شد")
                        sep()
                        withStyle(SpanStyle(fontWeight = FontWeight.SemiBold, color = c.textPrimary)) { bidi(quietLine(o.titleFa.ifBlank { outputKindFa(o.kind) })) }
                    }
                },
                style = Divan.type.caption, color = c.textSecondary, modifier = Modifier.weight(1f),
            )
            // ⟨1.35⟩ §57.6 the newest of a chain of versions says which it is; the older ones are not drawn
            version?.let { com.coinepro.hq.ui.v14.Tag(versionFa(it), Modifier.testTag("output-version")) }
            HqButton("باز کن", { nav.go("outputs/${o.ref}") }, variant = BtnVariant.TEXT, size = BtnSize.SM)
        }
        when {
            files.isNotEmpty() -> FilesStrip(files) { f ->
                when (f.id) {
                    main -> PublishUnder(f, o.panel, lead = lead == f.id) { onAsk(o.ref, f) }
                    cover -> Text("کاور ریلز", style = Divan.type.micro, color = c.textMuted)
                    else -> Unit
                }
            }
            o.loading -> Skeleton(Modifier.width(116.dp).height(148.dp), radius = 12.dp)
        }
        o.d?.let { madeWithFa(it.producedWith) }?.let { made ->
            Text(remember(made) { facts(*("ساخت: $made").split(" · ").toTypedArray()) }, style = Divan.type.micro, color = c.textMuted, modifier = Modifier.testTag("made-with"))
        }
    }
}

/** The outputs delivered between two turns, each where it arrived. */
@Composable
internal fun OutputsRow(row: ChatRow.Outputs, outs: List<SessionOutput>, lead: String?, versions: Map<String, Int> = emptyMap(), onAsk: (String, FileRef) -> Unit) {
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        for (e: SessionEntry.Output in row.outputs) {
            val o = outs.firstOrNull { it.ref == e.output.ref } ?: SessionOutput(e.output.ref, e.output.titleFa, e.output.kind, null, false, null)
            OutputTiles(o, lead, onAsk, versions[o.ref])
        }
    }
}

/** One blocker, by its kind and words (a new one is a new knot). */
internal fun blockerKey(b: Blocker): String = "${b.kind}|${b.titleFa}"
