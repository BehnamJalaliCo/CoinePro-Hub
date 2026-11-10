package com.coinepro.hq.ui.playbook

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.cardStateFa
import com.coinepro.hq.core.data.faNum
import com.coinepro.hq.core.data.helperOf
import com.coinepro.hq.core.data.memberStateFa
import com.coinepro.hq.core.data.memoryFolds
import com.coinepro.hq.core.data.membersFa
import com.coinepro.hq.core.data.pbPlatformLineFa
import com.coinepro.hq.core.data.PlaybookCard
import com.coinepro.hq.core.data.playbookStateFa
import com.coinepro.hq.core.data.playbooksOf
import com.coinepro.hq.core.data.routineTimeFa
import com.coinepro.hq.core.data.seatTitleFa
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.plainOfMd
import com.coinepro.hq.core.data.accountsNamed
import com.coinepro.hq.core.data.clockOf
import com.coinepro.hq.core.data.publishes
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.MemberPublish
import com.coinepro.hq.core.net.Playbook
import com.coinepro.hq.core.net.PlaybookRoutine
import com.coinepro.hq.core.net.PlaybookSeat
import com.coinepro.hq.core.net.TalkCard
import com.coinepro.hq.core.net.gated
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Expand
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.HqSwitch
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.IconBtn
import com.coinepro.hq.designsystem.Md
import com.coinepro.hq.designsystem.ModelMark
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.designsystem.smoothSize
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.activity
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v14.HqSheet
import com.coinepro.hq.ui.v29.Para
import com.coinepro.hq.ui.v29.plain
import java.util.UUID
import kotlinx.serialization.json.JsonObject

// Contract §40 ⟨1.22⟩: the pieces of a working group drawn from a session (a playbook) that the chat, the session's «جزئیات», the
// playbook's page and the library share: a seat with its helpers' logos, a routine's time in plain Persian, the rules; the `playbook`
// card in the chat; the session's memory («تا اینجا»); and the small «از کارگروه …» chip of a session opened from one.

@Composable
fun rememberPlaybook(ref: String) = rememberQuery("playbook:$ref", "playbooks", "groups", maxAgeMs = 15_000) { gated(HubFeature.PLAYBOOKS) { playbook(ref) } }

@Composable
fun rememberPlaybooks() = rememberQuery("playbooks", "playbooks", "groups", maxAgeMs = 20_000) { gated(HubFeature.PLAYBOOKS) { playbooks() } }

/** The caches a playbook's change touches: its page, the library, the working groups and the office. */
internal val PLAYBOOK_TAGS = arrayOf("playbooks", "groups", "home", "office")

// ----------------------------------------------------------------- helpers --
/** A seat's helper: its logo (ChatGPT, Gemini, DeepSeek; AI Studio carries Google's) and its product name, small. */
@Composable
fun HelperChip(key: String) {
    val c = Divan.colors
    val h = helperOf(key)
    Row(
        Modifier.clip(CircleShape).background(c.raised).border(1.dp, c.lineDivider, CircleShape).padding(start = 6.dp, end = 8.dp, top = 2.dp, bottom = 2.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        ModelMark(null, provider = h.provider, size = 12.dp)
        Text(plain(h.name), style = Divan.type.micro, color = c.textSecondary, maxLines = 1)
    }
}

/** A seat: its name, what it does, its helpers; a draft's seat can be taken out ([onRemove]). */
@Composable
fun SeatRow(s: PlaybookSeat, compact: Boolean = false, onRemove: (() -> Unit)? = null) {
    val c = Divan.colors
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        Box(Modifier.padding(top = 2.dp).size(if (compact) 26.dp else 32.dp).clip(CircleShape).background(c.softGold), contentAlignment = Alignment.Center) {
            DIcon(DivanIcon.AGENT, size = if (compact) 14.dp else 16.dp, tint = c.goldInk)
        }
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
            Text(plain(s.titleFa.ifBlank { s.seat }), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
            if (s.dutiesFa.isNotBlank()) Text(
                plain(s.dutiesFa), style = Divan.type.caption, color = c.textSecondary,
                maxLines = if (compact) 2 else Int.MAX_VALUE, overflow = TextOverflow.Ellipsis,
            )
            if (s.helpers.isNotEmpty()) FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                for (h in s.helpers) HelperChip(h)
            }
        }
        if (onRemove != null) IconBtn(DivanIcon.CLOSE, "این جایگاه را بردار", onRemove, tint = c.textMuted)
    }
}

/** A routine: its name, when it runs in plain Persian, and whose it is. */
@Composable
fun RoutineLine(pb: Playbook, r: PlaybookRoutine, trailing: (@Composable () -> Unit)? = null) {
    val c = Divan.colors
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        DIcon(DivanIcon.TIME, size = 16.dp, tint = c.lapis)
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(1.dp)) {
            Text(plain(r.titleFa.ifBlank { r.key }), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
            Text(plain("${routineTimeFa(r.schedule)} · ${seatTitleFa(pb, r.seat)}"), style = Divan.type.micro, color = c.textMuted)
        }
        trailing?.invoke()
    }
}

/** A rule of the group, one line with its mark. */
@Composable
fun RuleLine(text: String, trailing: (@Composable () -> Unit)? = null) {
    val c = Divan.colors
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Text("•", style = Divan.type.small, color = c.goldInk)
        Text(plain(text), style = Divan.type.small, color = c.textPrimary, modifier = Modifier.weight(1f))
        trailing?.invoke()
    }
}

@Composable
private fun SubHead(text: String) = Text(text, style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = Divan.colors.textMuted)

@Composable
private fun More(n: Int, what: String) {
    if (n > 0) Text("و ${faNum(n)} $what دیگر", style = Divan.type.micro, color = Divan.colors.textMuted)
}

/** A playbook in short, for the chat's card: the platform, the seats, the routines, the rules (a few of each; the page has them all). */
@Composable
fun PlaybookSummary(pb: Playbook) {
    val c = Divan.colors
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(plain(pb.titleFa), style = Divan.type.bodyStrong, color = c.textPrimary)
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            DIcon(DivanIcon.GLOBE, size = 14.dp, tint = c.textMuted)
            Text("روی ${pbPlatformLineFa(pb.platform)}", style = Divan.type.caption, color = c.textSecondary)
        }
        if (pb.purposeFa.isNotBlank()) Para(pb.purposeFa, style = Divan.type.caption, maxLines = 3)
        if (pb.seats.isNotEmpty()) {
            SubHead("جایگاه‌ها")
            for (s in pb.seats.take(4)) SeatRow(s, compact = true)
            More(pb.seats.size - 4, "جایگاه")
        }
        if (pb.routines.isNotEmpty()) {
            SubHead("کارهای روتین")
            for (r in pb.routines.take(3)) RoutineLine(pb, r)
            More(pb.routines.size - 3, "کار روتین")
        }
        if (pb.rulesFa.isNotEmpty()) {
            SubHead("قاعده‌ها")
            for (r in pb.rulesFa.take(3)) RuleLine(r)
            More(pb.rulesFa.size - 3, "قاعده")
        }
    }
}

// ---------------------------------------------------------------- the card --
/**
 * The `playbook` card (§40.2) in the session's chat. The card the draft posts carries the playbook only: it is drawn from the playbook
 * itself, live (its state, its seats with their helpers, its routines in plain Persian, its rules), with «باز کن» and, while a draft,
 * «مُهر کن» (🔏 `playbook.seal`). The holder's rewrite in words carries the whole new draft: it shows that draft, and its «اجرا کن»
 * stores it; «باز کن» goes to the page where it stands now.
 */
@Composable
fun PlaybookCardView(card: TalkCard, pc: PlaybookCard, onRun: suspend (TalkCard, JsonObject?) -> Unit, onDismiss: suspend (TalkCard) -> Unit, modifier: Modifier = Modifier) {
    val env = LocalEnv.current
    val nav = LocalNav.current
    val toasts = LocalToasts.current
    val act = activity()
    val c = Divan.colors
    val run = rememberAction()
    val no = rememberAction()
    val seal = rememberAction()
    val rewrite = pc.draft != null
    val q = if (rewrite) null else rememberPlaybook(pc.ref)
    val pb = pc.draft ?: q?.data
    val shape = RoundedCornerShape(14.dp)
    Column(
        modifier.fillMaxWidth().clip(shape).background(c.tile).border(1.dp, c.lineTahrir, shape).padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Pill(if (rewrite) "بازنویسی کارگروه" else "کارگروه از این جلسه", Tone.LAPIS, icon = DivanIcon.DEPARTMENT)
            Spacer(Modifier.weight(1f))
            val state = if (rewrite) cardStateFa(card.state) else q?.data?.let { playbookStateFa(it.state) }
            state?.let { (fa, tone) -> Pill(fa, tone, dot = true) }
        }
        when {
            pb != null -> PlaybookSummary(pb)
            q != null && q.error == null -> Skeleton(Modifier.fillMaxWidth().height(96.dp), radius = 10.dp)
            else -> {
                if (card.titleFa.isNotBlank()) Text(plain(card.titleFa), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                Para(card.bodyFa, style = Divan.type.caption)
            }
        }
        card.reasonFa?.takeIf { card.state == "failed" }?.let { Text(plain(it), style = Divan.type.caption, color = c.negative) }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
            if (rewrite && (card.state == "offered" || card.state == "failed")) {
                HqButton(
                    if (card.state == "failed") "دوباره" else "پیش‌نویس همین شود", { run.run { onRun(card, null) } },
                    variant = BtnVariant.PRIMARY, size = BtnSize.SM, icon = DivanIcon.EDIT, loading = run.busy, modifier = Modifier.weight(1f, fill = false),
                )
            }
            HqButton("باز کن", { nav.go("playbook/${pc.ref}") }, variant = if (rewrite || pb?.draft == true) BtnVariant.SILVER else BtnVariant.SECONDARY, size = BtnSize.SM, icon = DivanIcon.NEXT)
            if (!rewrite && pb?.draft == true) HqButton("مُهر کن", {
                seal.run {
                    // ⟨0.19.9⟩ §45 a working group that publishes is sealed with his standing word, as he asked; the line below says so
                    val word = MemberPublish(mode = "auto").takeIf { publishes(pb) }
                    val out = env.api.sealPlaybook(pc.ref, word) { a, t -> env.auth.stepUp(act, a, t) }
                    q?.set(out)
                    env.cache.invalidate(*PLAYBOOK_TAGS)
                    toasts.ok(sealedFa(out, word))
                }
            }, variant = BtnVariant.PRIMARY, size = BtnSize.SM, icon = DivanIcon.SEAL, loading = seal.busy)
            if (rewrite && (card.state == "offered" || card.state == "failed")) HqButton("نه", { no.run { onDismiss(card) } }, variant = BtnVariant.TEXT, size = BtnSize.SM, loading = no.busy)
        }
        if (!rewrite && pb?.draft == true && publishes(pb)) Text(
            "با مُهر، از نوبت بعد خروجی هر روز خودکار منتشر میشود؛ در صفحه‌ی کارگروه میشود خاموشش کرد.",
            style = Divan.type.micro, color = c.textMuted,
        )
    }
}

/** What the seal's toast says: the routines start, and whether each day's output goes out by itself. */
internal fun sealedFa(out: Playbook, word: MemberPublish?): String = when {
    word?.auto != true -> "مُهر شد؛ کارهای روتینش از نوبت بعدی راه میافتند."
    out.members.any { it.publish.auto } -> "مُهر شد؛ از نوبت بعد خودش میسازد و خودکار منتشر میکند."
    // a hub before §45 seals it and does not know the standing word yet
    else -> "مُهر شد. انتشار خودکار بعد از به‌روز شدن هاب روشن میشود؛ تا آن وقت هر خروجی منتظر تأیید تو است."
}

// ------------------------------------------------------- the standing word --
/**
 * ⟨0.19.9⟩ §45 The owner's standing word, asked where he seals a working group or gives it to a company (his words, 2026-11-10:
 * «به صورت خودکار از روز دوم انجام بشه … نه اینکه هر بار من تایید کنم»). On: each day's package goes out by itself.
 */
@Composable
fun StandingChoice(value: MemberPublish, onChange: (MemberPublish) -> Unit, modifier: Modifier = Modifier) {
    val c = Divan.colors
    Column(modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text("انتشار خودکار", style = Divan.type.bodyStrong, color = c.textPrimary)
                Text(
                    if (value.auto) "خروجی هر روز بی تأیید تو منتشر میشود. هر وقت خواستی خاموشش کن."
                    else "هر خروجی منتظر «تأیید و انتشار» تو میماند.",
                    style = Divan.type.micro, color = c.textMuted,
                )
            }
            HqSwitch(value.auto, { onChange(value.copy(mode = if (it) "auto" else "ask")) }, "انتشار خودکار")
        }
        Expand(value.auto) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FilterChip("استوری هم بشود", value.story, { onChange(value.copy(story = !value.story)) })
                // ⟨0.20.0⟩ §46 the hour each day's package goes out at; empty: as soon as it is ready
                HqTextField(value.at.orEmpty(), { onChange(value.copy(at = it.ifBlank { null })) }, "ساعت انتشار، مثل ۱۸:۳۰", Modifier.weight(1f), maxLength = 5, figure = true)
            }
        }
    }
}

/** A member's standing word in one line: where its daily output goes by itself, or that each waits for him. */
internal fun standingFa(p: MemberPublish): String = when {
    !p.auto -> "هر بار بپرس"
    // the hour first: the line is one row, and the hour is what he looks for
    else -> listOfNotNull("خودکار", clockOf(p.at)?.let { "ساعت $it" }, p.account?.let { "\u2066@$it\u2069" }, "استوری هم".takeIf { p.story }).joinToString(" · ")
}

/**
 * One member's standing word under its row: a switch, his tap, no passkey. A company with several accounts is asked which one (the
 * hub names them); a hub before §45 has no such route, said once and then not offered.
 */
@Composable
private fun StandingRow(group: String, company: String, value: MemberPublish, onChanged: (MemberPublish) -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val go = rememberAction()
    var picking by remember { mutableStateOf<List<String>>(emptyList()) }
    var editing by remember { mutableStateOf<MemberPublish?>(null) }
    suspend fun say(next: MemberPublish) {
        try {
            val out = env.api.gated(HubFeature.STANDING_PUBLISH) { setMemberPublish(group, company, next) }
            if (out == null) {
                toasts.info("این نسخه‌ی هاب هنوز انتشار خودکار ندارد؛ بعد از به‌روز شدن هاب می‌آید.")
                return
            }
            picking = emptyList()
            env.cache.invalidate(*PLAYBOOK_TAGS)
            onChanged(out.publish)
            toasts.ok(if (out.publish.auto) "از نوبت بعد خودکار منتشر میشود." else "از این به بعد هر خروجی منتظر تأیید تو است.")
        } catch (e: ApiException) {
            val named = accountsNamed(e.fields["account"])
            if (e.status != 422 || named.isEmpty()) throw e
            e.logged?.let { env.api.failures?.forget(it) }
            picking = named
        }
    }
    Row(
        Modifier.fillMaxWidth().padding(start = 24.dp, bottom = 8.dp), verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(1.dp)) {
            Text("انتشار خودکار", style = Divan.type.caption, color = c.textSecondary)
            Text(standingFa(value), style = Divan.type.micro, color = if (value.auto) c.goldInk else c.textMuted, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
        // ⟨0.20.0⟩ §46 its hour and «استوری هم», changed in a small sheet
        if (value.auto) HqButton("تنظیم", { editing = value }, variant = BtnVariant.TEXT, size = BtnSize.SM)
        HqSwitch(value.auto, { on -> go.run { say(value.copy(mode = if (on) "auto" else "ask")) } }, "انتشار خودکار", enabled = !go.busy)
    }
    editing?.let { draft ->
        HqSheet({ editing = null }, "انتشار خودکار", sub = "ساعت و استوری همین شرکت در این کارگروه") {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                StandingChoice(draft, { editing = it })
                val badHour = draft.auto && !draft.at.isNullOrBlank() && clockOf(draft.at) == null
                HqButton("ذخیره", { go.run { say(draft); editing = null } }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, size = BtnSize.LG, enabled = !badHour, loading = go.busy)
                if (badHour) Text("ساعت را به شکل ۱۸:۳۰ بنویسید.", style = Divan.type.micro, color = c.textMuted)
            }
        }
    }
    if (picking.isNotEmpty()) HqSheet({ picking = emptyList() }, "کدام حساب؟", sub = "خروجی هر روز این کارگروه به همین حساب میرود") {
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            for (a in picking) FilterChip("@$a", false, { go.run { say(value.copy(mode = "auto", account = a)) } }, figure = true)
        }
    }
}

// ------------------------------------------------------------------ memory --
/** ⟨1.22⟩ §40.1 «تا اینجا»: what the session remembers (decided, who does what with which helper, open points). Selectable and
 *  copyable whole; a long one is folded under a soft edge and opens with a tap. */
@Composable
fun MemoryCard(memory: String) {
    val c = Divan.colors
    val md = remember(memory) { com.coinepro.hq.core.data.withoutRefs(memory) }
    val folds = remember(md) { memoryFolds(md) }
    var open by rememberSaveable(md.length) { mutableStateOf(false) }
    HqCard(Modifier.fillMaxWidth(), color = c.card, padding = androidx.compose.foundation.layout.PaddingValues(14.dp)) {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                DIcon(DivanIcon.MEMORY, size = 18.dp, tint = c.goldInk)
                Column(Modifier.weight(1f)) {
                    Text("تا اینجا", style = Divan.type.bodyStrong, color = c.textPrimary)
                    Text("آنچه این جلسه به یاد دارد؛ هر کس در جلسه همین را میخواند.", style = Divan.type.micro, color = c.textMuted)
                }
                com.coinepro.hq.ui.CopyAction(plainOfMd(md))
            }
            Box(Modifier.fillMaxWidth().smoothSize().then(if (folds && !open) Modifier.heightIn(max = 176.dp).clipToBounds() else Modifier)) {
                com.coinepro.hq.ui.Selectable { Md(md, color = c.textPrimary) }
                if (folds && !open) Box(
                    Modifier.align(Alignment.BottomCenter).fillMaxWidth().height(44.dp)
                        .background(Brush.verticalGradient(listOf(Color.Transparent, c.card))),
                )
            }
            if (folds) Text(
                if (open) "کوتاه کن" else "همه‌اش را بخوان",
                Modifier.clip(CircleShape).clickable(role = Role.Button) { open = !open }.padding(horizontal = 6.dp, vertical = 2.dp),
                style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.goldInk,
            )
        }
    }
}

// ------------------------------------------------------ from the session --
/**
 * The session's own playbooks and the way to a new one, in its «جزئیات»: «کارگروه از این جلسه بساز» (`POST /orders/{ref}/playbook`, one
 * key per press, kept across its retry) and, under it, each playbook drafted from this session with its state, opening its page.
 * [onDrafted] closes the sheet and refreshes the chat, where the card has just been posted.
 */
@Composable
fun SessionPlaybooks(order: String, onDrafted: (Playbook) -> Unit) {
    val env = LocalEnv.current
    val nav = LocalNav.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val lib = rememberPlaybooks()
    val mine = playbooksOf(order, lib.data.orEmpty())
    val draft = rememberAction()
    var key by remember(order) { mutableStateOf(UUID.randomUUID().toString()) }
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        HqButton("کارگروه از این جلسه بساز", {
            draft.run {
                val pb = env.api.draftPlaybook(order, key)
                key = UUID.randomUUID().toString()
                env.cache.invalidate("talk", "order-report", *PLAYBOOK_TAGS)
                toasts.ok("پیش‌نویس کارگروه آماده است؛ کارتش در گفتگوست.")
                onDrafted(pb)
            }
        }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, icon = DivanIcon.DEPARTMENT, loading = draft.busy)
        Text(
            if (draft.busy) "مسئول جلسه از روی «تا اینجا» و برنامه‌ی جلسه پیش‌نویس را مینویسد؛ چند ثانیه…"
            else "نتیجه‌ی این جلسه، ماندگار: چه کسی چه میکند، با کدام ابزار و کِی. تا مُهر تو، هیچ چیز راه نمیافتد.",
            style = Divan.type.micro, color = c.textMuted, modifier = Modifier.padding(horizontal = 4.dp),
        )
        if (mine.isNotEmpty()) Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(c.card)) {
            mine.forEachIndexed { i, pb ->
                if (i > 0) HorizontalDivider(color = c.lineDivider)
                PlaybookRow(pb, null) { nav.go("playbook/${pb.ref}") }
            }
        }
    }
}

/** One playbook in a list: its title, its platform, how many companies run it (Persian digits) and where it came from; its state. */
@Composable
fun PlaybookRow(pb: Playbook, sourceFa: String?, showState: Boolean = true, onClick: () -> Unit) {
    val c = Divan.colors
    Row(
        Modifier.fillMaxWidth().clickable(role = Role.Button, onClickLabel = "باز کن", onClick = onClick).padding(horizontal = 12.dp, vertical = 11.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Box(Modifier.size(34.dp).clip(CircleShape).background(if (pb.sealed) c.softPositive else c.softGold), contentAlignment = Alignment.Center) {
            DIcon(DivanIcon.DEPARTMENT, size = 18.dp, tint = if (pb.sealed) c.positive else c.goldInk)
        }
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(plain(pb.titleFa.ifBlank { "کارگروه بی‌نام" }), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, maxLines = 1, overflow = TextOverflow.Ellipsis)
            val meta = listOfNotNull(pbPlatformLineFa(pb.platform), membersFa(pb.members.size), sourceFa?.let { "از $it" }).joinToString(" · ")
            Text(meta, style = Divan.type.micro, color = c.textMuted, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
        if (showState) playbookStateFa(pb.state).let { (fa, tone) -> Pill(fa, tone, dot = true) }
        DIcon(DivanIcon.NEXT, size = 14.dp, tint = c.textMuted)
    }
}

/** A member company of a sealed group: its name, at work or paused; a tap opens the session it came from, when there is one. */
@Composable
fun MemberRow(company: String, nameFa: String, state: String, onClick: (() -> Unit)?) {
    val c = Divan.colors
    Row(
        Modifier.fillMaxWidth().then(if (onClick != null) Modifier.clickable(role = Role.Button, onClickLabel = "جلسه‌اش", onClick = onClick) else Modifier).padding(vertical = 9.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        com.coinepro.hq.designsystem.CompanyMark(company, height = 14.dp, mono = true, ink = c.textSecondary)
        Text(nameFa, style = Divan.type.small, color = c.textPrimary, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
        memberStateFa(state).let { (fa, tone) -> Pill(fa, tone, dot = true) }
        if (onClick != null) DIcon(DivanIcon.NEXT, size = 14.dp, tint = c.textMuted)
    }
}

// ----------------------------------------------------------- source chip --
/** ⟨1.22⟩ §40.3 a session opened from a playbook: «از کارگروه …», small, in its head; a tap opens the playbook. */
@Composable
fun SourceChip(ref: String, modifier: Modifier = Modifier) {
    val nav = LocalNav.current
    val c = Divan.colors
    val pb = rememberPlaybook(ref).data
    Row(
        modifier.clip(CircleShape).background(c.softLapis).clickable(role = Role.Button, onClickLabel = "کارگروه") { nav.go("playbook/$ref") }
            .padding(horizontal = 10.dp, vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        DIcon(DivanIcon.DEPARTMENT, size = 13.dp, tint = c.lapis)
        Text(
            plain(pb?.titleFa?.ifBlank { null }?.let { "از کارگروه «$it»" } ?: "از کارگروه"),
            style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = c.lapis, maxLines = 1, overflow = TextOverflow.Ellipsis,
        )
    }
}

/** The members of a sealed group, for the page. */
@Composable
fun MembersBlock(pb: Playbook) {
    val nav = LocalNav.current
    val c = Divan.colors
    val companies = com.coinepro.hq.ui.rememberCompanies()
    val gaps by LocalEnv.current.api.gaps.missing.collectAsState()
    // what he just said, shown at once (the playbook is read again behind it)
    val said = remember(pb.ref) { mutableStateMapOf<String, MemberPublish>() }
    Column {
        if (pb.members.isEmpty()) Text("هنوز هیچ شرکتی عضو نیست.", style = Divan.type.caption, color = c.textMuted, modifier = Modifier.padding(vertical = 8.dp))
        pb.members.forEachIndexed { i, m ->
            if (i > 0) HorizontalDivider(color = c.lineDivider)
            val name = m.nameFa.ifBlank { com.coinepro.hq.ui.companyOf(companies, m.company).nameFa }
            MemberRow(m.company, name, m.state, m.order?.let { o -> { nav.go("session/$o") } })
            // ⟨0.19.9⟩ §45 his standing word for this company (a working group that publishes, on a hub that knows the route)
            val group = pb.group
            if (group != null && pb.sealed && publishes(pb) && HubFeature.STANDING_PUBLISH !in gaps) {
                StandingRow(group, m.company, said[m.company] ?: m.publish) { said[m.company] = it }
            }
        }
    }
}
