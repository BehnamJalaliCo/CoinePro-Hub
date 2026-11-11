package com.coinepro.hq.ui.session

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import com.coinepro.hq.designsystem.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.ChatRow
import com.coinepro.hq.core.data.blockerFa
import com.coinepro.hq.core.data.blockersFa
import com.coinepro.hq.core.data.eventsCountFa
import com.coinepro.hq.core.data.eventsSpan
import com.coinepro.hq.core.data.outputKindFa
import com.coinepro.hq.core.data.outputsFa
import com.coinepro.hq.core.data.quietLine
import com.coinepro.hq.core.data.stepWithSpeaker
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.format.jDateTime
import com.coinepro.hq.core.format.jTime
import com.coinepro.hq.core.net.Blocker
import com.coinepro.hq.core.net.OrderCard
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.Chevron
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.designsystem.smoothSize
import com.coinepro.hq.designsystem.timesFig
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.v29.FixButton

// ⟨0.19.0⟩ The session's chat in order (the owner, 2026-11-08: «مرتب و منظم نباشه»). One rhythm: every row, card and bubble on the same
// 16dp margins, gaps of 8, 12 and 16 only, right-aligned; each time at the end of its row, small, a Latin figure. The steps between two
// turns are one quiet row that opens to every line whole (never cut with «…»), the results that arrive together one card, and what blocks
// the work a compact banner over the composer. No ref is ever a word.

private val ROW = RoundedCornerShape(12.dp)

/** A clock time (or a range, «05:34–05:40») at the end of a row: small, muted, one Latin figure read left to right (two times set apart
 *  would read backwards in a right-to-left line). A date with its month's name is set as a sentence with its time a figure. */
@Composable
private fun RowTime(text: String) {
    if (text.isBlank()) return
    val figure = text.all { it.isDigit() || it == ':' || it == '–' }
    Text(
        if (figure) buildAnnotatedString { fig(text) } else timesFig(text),
        style = Divan.type.micro, color = Divan.colors.textMuted, maxLines = 1,
    )
}

/** A quiet line of the chat (when the session began, a word about its talk): its words whole and its time at the end. */
@Composable
internal fun QuietRow(text: String, at: String, date: Boolean = false) {
    val c = Divan.colors
    Row(
        Modifier.fillMaxWidth().clip(ROW).background(c.tile.copy(alpha = 0.55f)).padding(horizontal = 12.dp, vertical = 8.dp),
        verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Text(timesFig(text), style = Divan.type.micro, color = c.textMuted, modifier = Modifier.weight(1f))
        RowTime(if (at.isBlank()) "" else if (date) jDateTime(at) else jTime(at))
    }
}

/**
 * The steps between two turns. One: the line itself, whole. Several: one row, «۳ رویداد · 05:34–05:40», that opens to each line whole
 * with its time (and who, when it came through someone). [whoOf] names the persona a step was written under.
 */
@Composable
internal fun EventsRow(r: ChatRow.Events, whoOf: (String) -> String) {
    val c = Divan.colors
    val steps = r.steps
    fun text(i: Int): String = steps[i].let { s -> stepWithSpeaker(quietLine(s.text), s.by?.let(whoOf)) }
    if (steps.size == 1) {
        Row(
            Modifier.fillMaxWidth().testTag("chat-event").clip(ROW).background(c.tile.copy(alpha = 0.55f)).padding(horizontal = 12.dp, vertical = 8.dp),
            verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Box(Modifier.padding(top = 6.dp).size(5.dp).clip(CircleShape).background(c.lineStrong))
            Text(timesFig(text(0)), style = Divan.type.micro, color = c.textSecondary, modifier = Modifier.weight(1f))
            RowTime(steps[0].at.takeIf { it.isNotBlank() }?.let(::jTime).orEmpty())
        }
        return
    }
    var open by rememberSaveable(r.key) { mutableStateOf(false) }
    Column(Modifier.fillMaxWidth().testTag("chat-events").clip(ROW).background(c.tile.copy(alpha = 0.55f)).smoothSize()) {
        Row(
            Modifier.fillMaxWidth().clickable(role = Role.Button, onClickLabel = if (open) "ببند" else "همه‌ی رویدادها") { open = !open }
                .padding(horizontal = 12.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            DIcon(DivanIcon.TIME, size = 14.dp, tint = c.textMuted)
            Text(eventsCountFa(steps.size), style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
            Chevron(open, size = 12.dp, tint = c.textMuted)
            Box(Modifier.weight(1f))
            RowTime(eventsSpan(steps, ::jTime))
        }
        if (open) Column(Modifier.padding(start = 12.dp, end = 12.dp, bottom = 12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            HorizontalDivider(color = c.lineDivider)
            steps.indices.forEach { i ->
                Row(verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Box(Modifier.padding(top = 6.dp).size(5.dp).clip(CircleShape).background(c.lineStrong))
                    Text(timesFig(text(i)), style = Divan.type.micro, color = c.textSecondary, modifier = Modifier.weight(1f))
                    RowTime(steps[i].at.takeIf { it.isNotBlank() }?.let(::jTime).orEmpty())
                }
            }
        }
    }
}

/**
 * The results delivered between two turns: one quiet line, «۲ خروجی تحویل شد» (or «ریلز تحویل شد») and its time, that opens to each title
 * with «باز کن». ⟨0.19.4⟩ the owner: a card of every output in the middle of the talk crowded the question he had to answer; they are one
 * line now, and all of them are in «جزئیات» too.
 */
@Composable
internal fun OutputsCard(outputs: List<com.coinepro.hq.core.data.SessionEntry.Output>, key: String = outputs.firstOrNull()?.output?.ref.orEmpty()) {
    val c = Divan.colors
    val nav = LocalNav.current
    val at = outputs.map { it.at }.filter { it.isNotBlank() }
    var open by rememberSaveable(key) { mutableStateOf(false) }
    Column(
        Modifier.fillMaxWidth().testTag("chat-outputs").clip(ROW).background(c.tile.copy(alpha = 0.55f)).smoothSize(),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Row(
            Modifier.fillMaxWidth().clickable(role = Role.Button, onClickLabel = if (open) "ببند" else "دیدن خروجی‌ها") { open = !open }
                .padding(horizontal = 12.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            DIcon(DivanIcon.DELIVERABLE, size = 14.dp, tint = c.goldInk)
            Text(outputsFa(outputs.map { it.output }), style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = c.goldInk)
            Chevron(open, size = 12.dp, tint = c.textMuted)
            Box(Modifier.weight(1f))
            RowTime(if (at.isEmpty()) "" else if (at.size == 1 || jTime(at.first()) == jTime(at.last())) jTime(at.first()) else "${jTime(at.first())}–${jTime(at.last())}")
        }
        if (open) outputs.forEachIndexed { i, e ->
            val x = e.output
            if (i > 0) HorizontalDivider(Modifier.padding(end = 8.dp), color = c.lineDivider)
            Row(
                Modifier.fillMaxWidth().clip(ROW).clickable(role = Role.Button, onClickLabel = "باز کردن") { nav.go("outputs/${x.ref}") },
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Column(Modifier.weight(1f).padding(start = 32.dp)) {
                    Text(timesFig(quietLine(x.titleFa.ifBlank { outputKindFa(x.kind) })), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, maxLines = 2, overflow = TextOverflow.Ellipsis)
                    if (outputs.size > 1) Text(outputKindFa(x.kind), style = Divan.type.micro, color = c.textMuted, maxLines = 1)
                }
                HqButton("باز کن", { nav.go("outputs/${x.ref}") }, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.NEXT)
            }
        }
        if (open) Spacer(Modifier.height(4.dp))
    }
}

/**
 * What blocks the work, over the composer (never in the chat). One: its icon, its words in one line (a tap opens the whole of it and since
 * when) and its fix. Several: «۲ گیر» and the first, a tap opens each with its fix.
 */
@Composable
internal fun BlockersBanner(
    blockers: List<Blocker>, company: String?, orderRef: String?, budget: Long?,
    /** ⟨0.19.4⟩ opened (read): the owner has been told; [onClosed] once he closes it again, and it is not shown again. */
    onRead: (Set<String>) -> Unit = {}, onClosed: () -> Unit = {},
) {
    val c = Divan.colors
    var open by rememberSaveable(orderRef) { mutableStateOf(false) }
    fun budgetOf(b: Blocker): Long? = if (b.fix?.action == "budget.add") maxOf(100_000L, (budget ?: 0L) / 4) else null
    Column(Modifier.fillMaxWidth().testTag("blockers").clip(ROW).background(c.softNegative).smoothSize()) {
        Row(
            Modifier.fillMaxWidth().clickable(role = Role.Button, onClickLabel = if (open) "خواندم؛ ببند" else "همه‌ی آن") {
                open = !open
                if (open) onRead(blockers.map(::blockerKey).toSet()) else onClosed()
            }.padding(start = 12.dp, end = 8.dp, top = 8.dp, bottom = 8.dp),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            DIcon(DivanIcon.URGENT, size = 18.dp, tint = c.negative)
            val first = blockers.first()
            if (blockers.size == 1) {
                Text(
                    timesFig(quietLine(blockerFa(first.kind, first.titleFa))), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary,
                    maxLines = if (open) Int.MAX_VALUE else 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f),
                )
                first.fix?.let { FixButton(it, company, orderRef, budgetTokens = budgetOf(first)) }
            } else {
                Text(blockersFa(blockers.size), style = Divan.type.small.copy(fontWeight = FontWeight.Bold), color = c.negative)
                Text(
                    timesFig(quietLine(blockerFa(first.kind, first.titleFa))), style = Divan.type.small, color = c.textSecondary,
                    maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f),
                )
                Chevron(open, size = 14.dp, tint = c.textMuted)
            }
        }
        if (open) Column(Modifier.padding(start = 12.dp, end = 8.dp, bottom = 8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            if (blockers.size == 1) BlockerDetail(blockers.first())
            else blockers.forEachIndexed { i, b ->
                if (i > 0) HorizontalDivider(color = c.negative.copy(alpha = 0.18f))
                // Each: its words and why (and since when) beside its fix.
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Column(Modifier.weight(1f)) {
                        Text(timesFig(quietLine(blockerFa(b.kind, b.titleFa))), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                        BlockerDetail(b)
                    }
                    b.fix?.let { FixButton(it, company, orderRef, budgetTokens = budgetOf(b)) }
                }
            }
        }
    }
}

/**
 * ⟨0.19.6⟩ The cards of this session that wait for a decision, over the composer: each with who raised it, whom it waits for, and «مُهر»,
 * which opens that very card. The owner, in his own session: «بیار مهر کنم» — the holder had said «کارت منتظر مُهر شماست» and the card
 * was on another page.
 */
@Composable
internal fun WaitingCards(cards: List<OrderCard>) {
    if (cards.isEmpty()) return
    val c = Divan.colors
    val nav = LocalNav.current
    Column(
        Modifier.fillMaxWidth().testTag("waiting-cards").clip(ROW).background(c.tile).smoothSize().padding(start = 12.dp, end = 8.dp, top = 8.dp, bottom = 8.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        cards.forEachIndexed { i, card ->
            if (i > 0) HorizontalDivider(color = c.lineDivider)
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                DIcon(DivanIcon.SEAL, size = 18.dp, tint = c.goldInk)
                Column(Modifier.weight(1f)) {
                    Text(timesFig(quietLine(card.titleFa)), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                    val sub = listOfNotNull(card.byFa?.ifBlank { null }, card.waitsFa.ifBlank { null }).joinToString(" · ")
                    if (sub.isNotEmpty()) Text(timesFig(quietLine(sub)), style = Divan.type.micro, color = c.textSecondary)
                }
                HqButton("مُهر", { nav.go("cartable/${card.ref}") }, variant = BtnVariant.PRIMARY, size = BtnSize.SM)
            }
        }
    }
}

/** One blocker, as the phone remembers that the owner read it (its kind and words; a new one shows again). */
internal fun blockerKey(b: Blocker): String = "${b.kind}|${b.titleFa}"

/**
 * ⟨0.19.4⟩ The owner's own folds in a session, on this phone only: the head folded to its status and progress, and the blockers he has
 * opened and read (shown once, then gone; a new blocker is shown again).
 */
internal class SessionUiPrefs(context: android.content.Context) {
    private val sp = context.getSharedPreferences("hq.session.ui", android.content.Context.MODE_PRIVATE)
    var headFolded: Boolean
        get() = sp.getBoolean("head_folded", false)
        set(v) { sp.edit().putBoolean("head_folded", v).apply() }
    fun readBlockers(ref: String): Set<String> = sp.getStringSet("read_blockers:$ref", emptySet()).orEmpty().toSet()
    fun markRead(ref: String, keys: Set<String>) { sp.edit().putStringSet("read_blockers:$ref", readBlockers(ref) + keys).apply() }
}

@Composable
internal fun rememberSessionUiPrefs(): SessionUiPrefs {
    val ctx = androidx.compose.ui.platform.LocalContext.current
    return remember { SessionUiPrefs(ctx.applicationContext) }
}

/** Why it blocks, and since when, in one quiet paragraph. */
@Composable
private fun BlockerDetail(b: Blocker) {
    val c = Divan.colors
    val text = listOfNotNull(quietLine(b.detailFa).trimEnd('.', '،', '؛', ' ').ifBlank { null }, b.since?.let { "از ${ago(it)}" }).joinToString(" · ")
    if (text.isNotBlank()) Text(timesFig(text), style = Divan.type.caption, color = c.textSecondary)
}
