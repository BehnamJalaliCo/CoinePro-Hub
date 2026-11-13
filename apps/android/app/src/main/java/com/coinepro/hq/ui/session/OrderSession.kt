package com.coinepro.hq.ui.session

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.SideEffect
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.layout.onSizeChanged
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.coinepro.hq.core.data.CLOSED_FA
import com.coinepro.hq.core.data.ChatRow
import com.coinepro.hq.core.data.DIRECT_FA
import com.coinepro.hq.core.data.FIXED_PEOPLE_FA
import com.coinepro.hq.core.data.PACE_FA
import com.coinepro.hq.core.data.PACE_HINT_FA
import com.coinepro.hq.core.data.PLAYER_FA
import com.coinepro.hq.core.data.PlayerOption
import com.coinepro.hq.core.data.SessionEntry
import com.coinepro.hq.core.data.StreamState
import com.coinepro.hq.core.data.activityEventOf
import com.coinepro.hq.core.data.activityFromReport
import com.coinepro.hq.core.data.addresseeFa
import com.coinepro.hq.core.data.applyActivity
import com.coinepro.hq.core.data.briefOf
import com.coinepro.hq.core.data.chatRows
import com.coinepro.hq.core.data.isPlayer
import com.coinepro.hq.core.data.keyPatterns
import com.coinepro.hq.core.data.isCall
import com.coinepro.hq.core.data.knotWhy
import com.coinepro.hq.core.data.liveWorkers
import com.coinepro.hq.core.data.leadFile
import com.coinepro.hq.core.data.liveWorkRef
import com.coinepro.hq.core.data.mergeFetched
import com.coinepro.hq.core.data.moodOf
import com.coinepro.hq.core.data.moodWordFa
import com.coinepro.hq.core.data.oneLine
import com.coinepro.hq.core.data.orderParticipants
import com.coinepro.hq.core.data.orderedTasks
import com.coinepro.hq.core.data.outputKindFa
import com.coinepro.hq.core.data.paceToastFa
import com.coinepro.hq.core.data.participantTitle
import com.coinepro.hq.core.data.personaIdTitle
import com.coinepro.hq.core.data.playersToAdd
import com.coinepro.hq.core.data.quietLine
import com.coinepro.hq.core.data.readyAnswers
import com.coinepro.hq.core.data.segmentsOf
import com.coinepro.hq.core.data.sessionBadge
import com.coinepro.hq.core.data.sessionClosed
import com.coinepro.hq.core.data.sessionTimeline
import com.coinepro.hq.core.data.standingTaskFa
import com.coinepro.hq.core.data.stillOf
import com.coinepro.hq.core.data.taskFa
import com.coinepro.hq.core.data.taskOf
import com.coinepro.hq.core.data.taskProgress
import com.coinepro.hq.core.data.tickedState
import com.coinepro.hq.core.data.tookFa
import com.coinepro.hq.core.data.usageOf
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.format.jDateTime
import com.coinepro.hq.core.media.FilePolicy
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.FileRef
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.OrderReport
import com.coinepro.hq.core.net.SessionActivity
import com.coinepro.hq.core.net.SessionParticipant
import com.coinepro.hq.core.net.SessionTask
import com.coinepro.hq.core.net.TalkCard
import com.coinepro.hq.core.net.TalkPersona
import com.coinepro.hq.core.net.gated
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.CollapsingHeader
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.DecisionBar
import com.coinepro.hq.designsystem.DecisionPlace
import com.coinepro.hq.designsystem.DecisionState
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.DrawnMark
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.IconBtn
import com.coinepro.hq.designsystem.QuietAction
import com.coinepro.hq.designsystem.ScrollRow
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.Text
import com.coinepro.hq.designsystem.continuity
import com.coinepro.hq.designsystem.facts
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.designsystem.motionMedium
import com.coinepro.hq.designsystem.rememberHaptics
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.activity
import com.coinepro.hq.ui.live.rememberTicker
import com.coinepro.hq.ui.look.AnswerSent
import com.coinepro.hq.ui.look.EndLeaf
import com.coinepro.hq.ui.look.FilesStrip
import com.coinepro.hq.ui.look.IdleNudge
import com.coinepro.hq.ui.look.KnotCard
import com.coinepro.hq.ui.look.LiveTail
import com.coinepro.hq.ui.look.MoodLight
import com.coinepro.hq.ui.look.NowBar
import com.coinepro.hq.ui.look.SegmentLine
import com.coinepro.hq.ui.look.SessionCards
import com.coinepro.hq.ui.look.StillCard
import com.coinepro.hq.ui.look.WaitingCard
import com.coinepro.hq.ui.media.FileThumbs
import com.coinepro.hq.ui.media.MessageMedia
import com.coinepro.hq.ui.media.rememberAttachments
import com.coinepro.hq.ui.media.rememberPickers
import com.coinepro.hq.ui.outputs.PublishFor
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v29.Para
import com.coinepro.hq.ui.v29.plain
import com.coinepro.hq.ui.v29.rememberOrderReport
import com.coinepro.hq.ui.v29.served
import com.coinepro.hq.ui.v32.CHAT_TAIL
import com.coinepro.hq.ui.v32.JumpToEnd
import com.coinepro.hq.ui.v32.LiveBubble
import com.coinepro.hq.ui.v32.Phase
import com.coinepro.hq.ui.v32.TalkBubble
import com.coinepro.hq.ui.v32.TalkComposer
import com.coinepro.hq.ui.v32.TalkSession
import com.coinepro.hq.ui.v32.faCount
import com.coinepro.hq.ui.v32.rememberChatFollow
import com.coinepro.hq.ui.v32.rememberHandsFree
import java.util.UUID
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonObject

// Contract §34–§35 ⟨1.16, 1.17⟩: one order, one session the owner talks in.
// ⟨1.0.1⟩ Part C, the session redesigned (C2.2), with the workshop inside it and the direct session's display:
// - a header that is ONE line (the short title, «کار ۳ از ۴», the pace, the mood light) and opens at the top of the thread; a tap on
//   it opens «جزئیات» (the whole order, the plan, the people, the files). Under it the plan as a line of parts: done silver, the
//   owner's part gold, the rest empty;
// - the thread: bubbles (the owner's with a thin gold edge; «کپی» and the time come with a long press), the steps of the work as thin
//   centred lines at their time, each output where it arrived as a strip of its files (a video plays in place), the live steps at its
//   end, and a closed session's end leaf;
// - right above the composer: the «الان» bar while something works (with the build ring of a workshop or direct turn, and «نگه دار»),
//   then the owner's own thing: the «منتظر تو» card with its ready answers, the session's cards, the «گره» card with its one action,
//   or the decision bar («تأیید و انتشار» of what the session waits on, else «تأیید و بستن»): the page's one full gold;
// - ⟨2026-11-11⟩ an open session that nobody works on and that none of those explains is «ایستاده» after twenty minutes: one calm card
//   there says so, with the last thing done and «ادامه بده».
// Nothing technical and no ref is shown: the ref is the key only.

private enum class SessionSheet { NONE, DETAILS, LIVE, PERSON, MODEL, CLOSE, LINE, KEY, PARTICIPANT, ERASE, ROUTINE, TEAM_SEAT, TEAM_HIRE, TEAM_NARRATOR }

/** How long «جوابت رفت» stays said where the question was. */
private const val SAID_MS = 6_000L

/**
 * «اصلاح» of an output's page lands in its session with the output named: the words the session's composer opens with. Kept in
 * memory only, from the tap to the session's first frame.
 */
object ComposerSeeds {
    private val seeds = mutableStateMapOf<String, String>()
    fun put(order: String, text: String) { seeds[order] = text }
    fun peek(order: String): String? = seeds[order]
    fun take(order: String) { seeds.remove(order) }
}

@Composable
fun OrderSessionScreen(ref: String) {
    val env = LocalEnv.current
    val nav = LocalNav.current
    val toasts = LocalToasts.current
    val haptics = rememberHaptics()
    val c = Divan.colors
    val scope = rememberCoroutineScope()
    val act = activity()
    val q = rememberOrderReport(ref)
    val o = q.data
    val has = served(HubFeature.ORDER_REPORT)
    val sessionsOn = served(HubFeature.SESSIONS)
    val talk = remember(env, ref) { TalkSession(env, scope, toasts) }
    DisposableEffect(talk) { onDispose { talk.release() } }
    // ⟨1.18⟩ §36 files in the session: picked by the paperclip, uploaded at once, sent with the owner's next turn.
    val filesOn = served(HubFeature.TALK_FILES)
    val attach = rememberAttachments(max = Api.MAX_TURN_FILES, policy = FilePolicy.SESSION, key = ref)
    val pick = rememberPickers(attach)

    // The order's talk (§34.2): the report names it; a hub of ⟨1.16⟩ makes it once on POST /orders/{ref}/talk.
    var cv by rememberSaveable(ref) { mutableStateOf<String?>(null) }
    LaunchedEffect(env, ref) { talk.loadPersonas() }
    LaunchedEffect(o?.conversationRef, o != null) {
        if (o == null) return@LaunchedEffect
        val known = o.conversationRef?.ifBlank { null } ?: cv
        val r = known ?: try {
            env.api.gated(HubFeature.SESSIONS) { orderTalk(ref) }?.conversationRef?.ifBlank { null }
        } catch (e: ApiException) {
            e.logged?.let { env.api.failures?.forget(it) }
            null
        }
        if (r != null && r != talk.conv?.ref) { cv = r; talk.open(r) }
    }
    // ⟨1.23⟩ §41.1 the work, live: the hub's `/activity` on open and on each of its stream events (refetched by the tag, at most once in
    // two seconds), each `session.activity` line appended the moment it arrives; a hub without it, the activity read from the report.
    val liveOn = served(HubFeature.SESSION_ACTIVITY)
    val aq = rememberQuery("session-activity:$ref", "session-activity", maxAgeMs = 5_000) { gated(HubFeature.SESSION_ACTIVITY) { sessionActivity(ref) } }
    var live by remember(ref) { mutableStateOf<SessionActivity?>(null) }
    LaunchedEffect(aq.data) { aq.data?.let { live = mergeFetched(it, live) } }
    // The stream: a turn or card changed (the conversation), the session moved (its report), a step of its work (the live lines).
    LaunchedEffect(env, ref) {
        env.stream.events.collect { e ->
            when {
                e.type.startsWith("talk.") && !talk.busy -> talk.reload()
                e.type == "session.activity" -> activityEventOf(e)?.takeIf { it.order == ref }?.let { ev -> live = applyActivity(live ?: aq.data ?: SessionActivity(), ev) }
                (e.type == "session.updated" || e.type == "order.report") && e.ref == ref -> q.refresh()
            }
        }
    }
    // Without the stream (the phone between networks, a hub restarting) the page asks again on its own: often while someone works.
    val streamState by env.stream.state.collectAsStateWithLifecycle()
    val workingNow = live?.working?.isNotEmpty() == true
    // ⟨2026-11-11⟩ audit: the report and the talk too (a turn or a question that came while the stream was down), and on a hub without
    // the live work as well
    LaunchedEffect(ref, liveOn, streamState, workingNow) {
        if (streamState == StreamState.LIVE) return@LaunchedEffect
        while (true) {
            delay(if (workingNow) 10_000 else 30_000)
            if (liveOn) aq.refresh()
            q.refresh()
            if (!talk.busy) talk.reload()
        }
    }

    val closed = o?.let(::sessionClosed) == true
    val asked = o?.turn != null && !closed
    // The owner's words go to the order's reply while the holder waits for him (§34.3), or while there is no talk at all.
    SideEffect {
        talk.interceptor = if (o != null && !closed && (asked || cv == null)) { text, _ ->
            try {
                val out = env.api.orderReply(ref, text, UUID.randomUUID().toString())
                q.set(out)
                env.cache.invalidate("sessions", "office", "orders")
                talk.reload()
                true
            } catch (e: ApiException) {
                // ⟨2026-11-09⟩ F-0013: the hub refused the word (422) and it was lost. With the session's talk open the words go there
                // as the owner's turn (the hub carries a working session's word to its holder from the talk too); the refusal stays in
                // the error log with the field the hub named.
                if (e.status == 422 && talk.conv != null) null
                else { toasts.error(e.messageFa); false }
            }
        } else null
    }

    var sheet by rememberSaveable { mutableStateOf(SessionSheet.NONE) }
    var picked by remember { mutableStateOf<SessionParticipant?>(null) }
    // ⟨1.35⟩ §57 the session's team: one row under the header; a filled seat's side talk ([seatCode] its code), an empty one's hire (its key).
    val teamQ = rememberSessionTeam(ref)
    var seatCode by rememberSaveable(ref) { mutableStateOf<String?>(null) }
    var caught by remember { mutableStateOf("") }
    val hf = rememberHandsFree(talk, { keyPatterns(emptyList()) }) { k -> caught = k; sheet = SessionSheet.KEY }

    val participants = orderParticipants(o?.participants.orEmpty())
    val faces = sessionFaces(talk.personas, participants)
    val company = o?.let(::companyOfOrder)
    val companies = rememberCompanies()
    val companyName: (String?) -> String? = remember(companies) { { code -> companies.firstOrNull { it.code == code }?.nameFa } }

    suspend fun refreshAll() { q.refresh(); env.cache.invalidate("sessions", "office", "orders"); talk.reload() }
    suspend fun runCard(card: TalkCard, payload: JsonObject?) {
        env.api.runTalkCard(card.idText, payload) { a, t -> env.auth.stepUp(act, a, t) }
        toasts.ok("انجام شد.")
        env.cache.invalidate("talk", "orders", "work", "decisions", "rules", "automations", "planner", "hiring", "home", "groups", "lines", "order-report", "sessions", "office")
        talk.reload()
    }
    suspend fun dismissCard(card: TalkCard) { env.api.dismissTalkCard(card.idText); env.cache.invalidate("talk"); talk.reload() }
    fun hide() = scope.launch {
        val r = o ?: return@launch
        try {
            if (r.session?.hidden == true) env.api.unhideSession(ref) else env.api.hideSession(ref)
            env.cache.invalidate("sessions", "office")
            toasts.ok(if (r.session?.hidden == true) "دوباره در فهرست است." else "پنهان شد؛ چیزی پاک نشد.")
            if (r.session?.hidden != true) nav.back() else q.refresh()
        } catch (e: ApiException) { toasts.error(e.messageFa) }
    }
    val reopening = rememberAction()
    fun reopen() = reopening.run {
        q.set(env.api.reopenSession(ref))
        env.cache.invalidate("sessions", "office", "orders")
        toasts.ok("دوباره باز شد؛ مسئول خبر دارد.")
        talk.reload()
    }
    // §34.1, §41.2 the pace, from the details: shown at once, the hub's report when it answers (back as it was if it refuses).
    var paceAsked by remember(ref) { mutableStateOf<String?>(null) }
    fun setPace(p: String) = scope.launch {
        paceAsked = p
        try {
            q.set(env.api.setPace(ref, p))
            env.cache.invalidate("sessions", "office")
            toasts.ok(paceToastFa(p))
        } catch (e: ApiException) { toasts.error(e.messageFa) }
        finally { paceAsked = null }
    }
    // «نگه دار»: the live work is stopped with one tap; the bar then reads «ادامه بده» until the holder is told to go on.
    val stopOn = served(HubFeature.WORK_STOP)
    val workRef = o?.let(::liveWorkRef)
    var stopped by remember(ref) { mutableStateOf(false) }
    // ⟨2026-11-11⟩ audit: the hold ends whenever the work is seen at work again (a nudge from anywhere, his word, the hub's own wake)
    LaunchedEffect(workingNow) { if (workingNow) stopped = false }
    val hold = rememberAction()
    fun holdNow() {
        val w = workRef ?: return
        hold.run(onError = { e: ApiException -> haptics.error(); toasts.error(e.messageFa) }) {
            if (env.api.gated(HubFeature.WORK_STOP) { stopWork(w) } == null) toasts.info("این نسخه‌ی هاب هنوز نگه داشتن کار را ندارد.")
            else {
                haptics.tick()
                stopped = true
                aq.refresh()
                env.cache.invalidate("sessions", "office", "work")
            }
        }
    }
    // §41.3 «ادامه بده»: the holder woken now with the plan's next task. One key per press, kept across a retry of the same press.
    val nudge = rememberAction()
    var nudgeKey by remember(ref) { mutableStateOf(UUID.randomUUID().toString()) }
    fun nudgeNow() = nudge.run {
        val out = env.api.nudgeSession(ref, nudgeKey)
        nudgeKey = UUID.randomUUID().toString()
        stopped = false
        live = mergeFetched(out, live)
        aq.set(out)
        toasts.ok("${o?.let { r -> r.participants.firstOrNull { it.kind == "holder" }?.let(::participantTitle) } ?: "مسئول"} دوباره دست به کار شد.")
        q.refresh()
        env.cache.invalidate("sessions", "office")
    }
    // A ready answer goes through the session's own reply; it stays said for a moment where the question was.
    var said by remember(ref) { mutableStateOf<String?>(null) }
    var answering by remember(ref) { mutableStateOf<String?>(null) }
    LaunchedEffect(said) { if (said != null) { delay(SAID_MS); said = null } }
    fun answer(text: String) {
        if (answering != null) return
        answering = text
        scope.launch {
            try {
                q.set(env.api.orderReply(ref, text, UUID.randomUUID().toString()))
                haptics.seal()
                said = text
                env.cache.invalidate("sessions", "office", "orders")
                talk.reload()
            } catch (e: ApiException) { haptics.error(); toasts.error(e.messageFa) }
            finally { answering = null }
        }
    }

    if (!has) {
        Box(Modifier.fillMaxSize().padding(16.dp), contentAlignment = Alignment.Center) { Empty("جلسه‌ی فرمان با به‌روزرسانی بعدی هاب میاید", icon = DivanIcon.MEETING) }
        return
    }

    // ⟨1.35⟩ §57.6 the outputs of the session with their files; of a chain of versions only the newest is drawn, with «نسخه‌ی n».
    val outsAll = rememberSessionOutputs(o?.outputs.orEmpty())
    val revs = rememberRevisions(o?.outputs.orEmpty(), outsAll)
    val outs = remember(outsAll, revs) { if (revs.hidden.isEmpty()) outsAll else outsAll.filter { it.ref !in revs.hidden } }
    // The chat in time order; drawn bottom-up, so it opens at its newest word.
    val entries = sessionTimeline(talk.turns.toList(), o, hasTalk = cv != null).let { e ->
        if (revs.hidden.isEmpty()) e else e.filterNot { it is SessionEntry.Output && it.output.ref in revs.hidden }
    }
    val rows = remember(entries) { chatRows(entries) }
    val newest = entries.lastOrNull()
    val list = rememberLazyListState()
    val follow = rememberChatFollow(list, entries.size, newest?.key, (newest as? SessionEntry.Said)?.turn?.owner == true)
    // A speaker's name over the first of his answers in a row (a turn of the owner starts a new row).
    val named = remember(entries) {
        var lastBy: String? = null
        entries.filterIsInstance<SessionEntry.Said>().associate { e ->
            val show = !e.turn.owner && e.turn.by != lastBy
            lastBy = if (e.turn.owner) null else e.turn.by
            e.key to show
        }
    }
    val speaking = talk.phase != Phase.IDLE || talk.liveText.isNotBlank() || talk.liveFailed != null

    // ⟨1.23⟩ §41 what is shown of the work: the hub's activity, else (a hub before it) the report read as one.
    // (⟨2026-11-11⟩ a failed read of the live work falls back to the report, so the page still knows when the session stands still)
    val read = when {
        o == null || closed -> null
        liveOn -> live ?: aq.error?.let { activityFromReport(o) }
        else -> activityFromReport(o)
    }
    // An outside call past its deadline is no longer at work (the hub may drop it without a word on the stream): looked at every minute
    val callTick = rememberTicker(60_000, on = read?.working?.any(::isCall) == true)
    val shown = read?.let { r -> liveWorkers(r.working, callTick).let { w -> if (w.size == r.working.size) r else r.copy(working = w) } }
    val working = shown?.working.orEmpty()
    val now = rememberTicker(1_000, on = working.isNotEmpty())
    val badge = o?.let(::sessionBadge) ?: "moving"
    // ⟨2026-11-11⟩ An open session nobody works on, that the hub has not explained, is «ایستاده» with its own card (looked at again
    // every minute); never «آرام» for hours with nothing to press.
    val minute = rememberTicker(60_000, on = o != null && !closed && working.isEmpty())
    // The report standing in for the live work (a failed read, or a hub before it) cannot see a long quiet turn: while the hub's own
    // badge says someone is at work, the page does not say nobody is.
    val reportBusy = read != null && read !== live && badge == "moving" &&
        o?.session?.reasonFa?.trim()?.startsWith("در حال کار") == true
    val still = if (o == null || closed || stopped || reportBusy) null else remember(o, shown, minute) { stillOf(o, shown, minute) }
    val mood = if (still != null) "still" else moodOf(shown, closed, badge, asked)
    val pace = paceAsked ?: o?.pace ?: "auto"

    // The ONE thing of the owner's above the composer (where the page's gold is).
    val ready = badge == "ready" && !closed && sessionsOn
    val blockers = if (closed) emptyList() else o?.blockers.orEmpty()
    val knot = o != null && !closed && !asked && (blockers.isNotEmpty() || (mood == "stuck" && !shown?.stuckFa.isNullOrBlank()))
    // What the session waits on: the first file of its outputs that can be published and has no publication that stands.
    val waitsOn: Pair<String, FileRef>? = if (ready) outs.firstNotNullOfOrNull { so -> leadFile(so.panel, so.files)?.let { so.ref to it } } else null
    var closeState by remember(ref) { mutableStateOf(DecisionState.IDLE) }
    val bar = (ready && !asked) || closeState != DecisionState.IDLE
    // One key per press, kept across a retry of the same press; ⟨2026-11-11⟩ audit: a fresh one after a close went through (a session
    // reopened and closed again is a new close, never the old one replayed).
    var closeKey by remember(ref) { mutableStateOf(UUID.randomUUID().toString()) }
    fun closeNow() {
        if (closeState != DecisionState.IDLE) return
        closeState = DecisionState.WORKING
        scope.launch {
            try {
                val out = env.api.closeSession(ref, "ok", null, closeKey)
                closeKey = UUID.randomUUID().toString()
                haptics.seal()
                closeState = DecisionState.DONE
                q.set(out)
                toasts.ok("جلسه بسته و بایگانی شد.")
                refreshAll()
            } catch (e: ApiException) { haptics.error(); closeState = DecisionState.IDLE; toasts.error(e.messageFa) }
        }
    }
    var asking by remember { mutableStateOf<Pair<String, String>?>(null) }
    val focus = remember { FocusRequester() }
    val allFiles = outs.flatMap { it.files }
    val used = outsAll.sumOf { so -> so.d?.let { usageOf(it).first } ?: 0L }

    // M18: the header is one line while older words are above; at the top of the thread it opens. It lies over the thread's top (the
    // thread keeps the open header's room there), so folding it never moves a word under the owner's finger.
    val density = LocalDensity.current
    var headPx by remember { mutableIntStateOf(0) }
    val foldedNow by remember(list) { derivedStateOf { list.canScrollForward } }
    val fold by animateFloatAsState(if (foldedNow) 1f else 0f, motionMedium(), label = "session-header")
    // ⟨1.35⟩ §57.7 «تیم این جلسه» under the header while someone besides the holder (or the narrator) is there; a hub without `/team`
    // shows nothing. The thread keeps its room too.
    val team = teamQ.data
    val teamOn = o != null && !closed && com.coinepro.hq.core.data.teamShown(team)
    var teamPx by remember { mutableIntStateOf(0) }
    LaunchedEffect(teamOn) { if (!teamOn) teamPx = 0 }
    fun onSeat(s: com.coinepro.hq.core.net.SessionSeat) {
        val t = team ?: return
        when {
            // the main thread is the holder's: his chip goes to the session's own composer
            s.holder -> { talk.addressee = null; scope.launch { list.animateScrollToItem(0) }; runCatching { focus.requestFocus() } }
            s.empty -> { seatCode = s.key; sheet = SessionSheet.TEAM_HIRE }
            else -> { seatCode = s.code; teamQ.set(com.coinepro.hq.core.data.teamRead(t, s.code)); sheet = SessionSheet.TEAM_SEAT }
        }
    }

    // The page's one full gold is over the composer (the decision bar, the knot's action, or the send): the cards of the thread are outlined.
    androidx.compose.runtime.CompositionLocalProvider(com.coinepro.hq.ui.v32.LocalQuietCards provides true) {
    Column(Modifier.fillMaxSize().imePadding()) {
        Box(Modifier.weight(1f).fillMaxWidth()) {
            LazyColumn(
                Modifier.fillMaxSize().testTag("session-chat"), state = list, reverseLayout = true,
                contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = with(density) { (headPx + teamPx).toDp() } + 12.dp, bottom = 8.dp),
                // An open session rests on its newest word; a closed one reads from its top (nothing is typed under it).
                verticalArrangement = Arrangement.spacedBy(12.dp, if (closed) Alignment.Top else Alignment.Bottom),
            ) {
                // The foot of the chat (a hair of space): what waits for the owner is over the composer, never in the chat.
                item(key = CHAT_TAIL) { Spacer(Modifier.height(2.dp)) }
                if (speaking) item(key = "live") {
                    LiveBubble(talk.phase, talk.liveText, talk.liveFailed, faces.firstOrNull { it.id == (talk.addressee?.takeIf { a -> a != "all" } ?: talk.conv?.persona) }, talk.liveCards.toList(), talk.speaking, ::runCard, ::dismissCard)
                }
                // A closed session ends with what it made, how long it took and what it used.
                if (o != null && closed) item(key = "end") {
                    EndLeaf(
                        cancelled = o.state == "cancelled", outputs = o.outputs.size, tookFa = tookFa(o.at, o.session?.closedAt), used = used.takeIf { it > 0 },
                        onReopen = if (sessionsOn) ({ reopen() }) else null, reopening = reopening.busy,
                        made = if (allFiles.isEmpty()) null else ({ FilesStrip(allFiles) }),
                    )
                }
                // The steps of the work that is live, as thin lines at the end of the thread.
                if (working.isNotEmpty() && shown?.last?.isNotEmpty() == true) item(key = "live-tail") { LiveTail(shown, companyName) }
                // In order: each turn a bubble; between two turns, the steps as one thin line and each output where it arrived.
                items(rows.asReversed(), key = { it.key }) { r ->
                    when (r) {
                        is ChatRow.Turn -> {
                            val t = r.said.turn
                            TalkBubble(
                                t, faces.firstOrNull { it.id == t.by }, faces + talk.personas, named[r.key] == true,
                                onReplay = if (t.audio.isEmpty()) null else ({ t.audio.sortedBy { a -> a.seq }.forEach(talk::play) }),
                                onRun = ::runCard, onDismiss = ::dismissCard, timeAtEnd = true, quiet = true,
                            )
                        }
                        is ChatRow.Events -> EventsRow(r) { by -> personaIdTitle(by, faces + talk.personas) }
                        is ChatRow.Outputs -> OutputsRow(r, outs, lead = waitsOn?.second?.id, versions = revs.version) { output, f -> asking = output to f.id }
                    }
                }
                if (talk.loading && talk.turns.isEmpty() && cv != null) items(2, key = { "tsk-$it" }) { i -> Skeleton(Modifier.fillMaxWidth(if (i == 0) 0.5f else 0.7f).height(56.dp), radius = 16.dp) }
                // The top of the chat: when the session began, and a word when its talk is not open yet.
                if (o != null) item(key = "start") {
                    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        if (o.at.isNotBlank()) QuietRow("جلسه باز شد", o.at, date = true)
                        if (cv == null && !closed) QuietRow("گفتگوی این فرمان هنوز باز نشده؛ جوابت مستقیم به فرمان میرود.", "")
                    }
                }
            }
            Column(Modifier.fillMaxWidth().background(c.page)) {
                when {
                    // ⟨1.0.1⟩ M14: the card that was tapped (the office, the sessions list) grows into this header.
                    o != null -> SessionHeader(
                        o, closed, mood, moodWordFa(mood, shown), pace, waiting = asked || ready, working = working.isNotEmpty(),
                        lastStepAt = shown?.last?.lastOrNull()?.at?.ifBlank { null } ?: shown?.idleSince,
                        fraction = { fold }, onDetails = { sheet = SessionSheet.DETAILS }, modifier = Modifier.continuity("session/$ref"),
                        onOpenHeight = { headPx = it },
                    )
                    q.error != null -> Box(Modifier.fillMaxWidth().padding(16.dp)) { ErrorBlock(q.error, { q.refresh() }) }
                    else -> Skeleton(Modifier.fillMaxWidth().padding(16.dp).height(44.dp), radius = 12.dp)
                }
                if (teamOn && team != null) TeamRow(team, ::onSeat, onNarrator = { sheet = SessionSheet.TEAM_NARRATOR }, Modifier.onSizeChanged { teamPx = it.height })
                HorizontalDivider(color = c.lineDivider)
            }
            JumpToEnd(follow)
        }
        if (o != null) Column(Modifier.fillMaxWidth().background(c.page).padding(bottom = 8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            val side = Modifier.padding(horizontal = 12.dp)
            if (!closed) {
                NowBar(
                    working, held = stopped, now = now, onOpen = { sheet = SessionSheet.LIVE }, modifier = side,
                    canHold = stopOn && workRef != null, holding = hold.busy, onHold = { holdNow() }, resuming = nudge.busy, onResume = { nudgeNow() },
                )
                val turn = o.turn
                if (turn != null) WaitingCard(
                    whoFa = turn.whoFa.ifBlank { addresseeFa(null, participants) }, questionFa = turn.questionFa, askedAt = turn.at.ifBlank { null },
                    standingFa = standingTaskFa(o.tasks), answers = remember(turn.questionFa) { readyAnswers(turn.questionFa) }, busy = answering,
                    onAnswer = { answer(it) }, modifier = side,
                ) else said?.let { AnswerSent(it, side) }
                // The session's cards that wait for a decision, answered here (never «برو پیدایش کن»).
                SessionCards(o.cards, side) { scope.launch { q.refresh() } }
                if (knot) KnotCard(
                    knotWhy(shown?.stuckFa.takeIf { blockers.isEmpty() }, blockers).orEmpty(), blockers, company, o.ref, o.route?.budgetTokens, lead = !bar,
                    canNudge = liveOn && sessionsOn, nudging = nudge.busy, onNudge = { nudgeNow() }, modifier = side,
                    onFixed = { scope.launch { q.refresh() } },
                )
                // Nobody works and nothing above says why: one calm card and «ادامه بده».
                still?.let { StillCard(it, minute, canNudge = liveOn && sessionsOn, nudging = nudge.busy, onNudge = { nudgeNow() }, modifier = side, lead = !bar) }
            }
            if (bar) {
                val revise = QuietAction("اصلاح", enabled = !closed) { runCatching { focus.requestFocus() } }
                DecisionBar(
                    if (waitsOn != null) "تأیید و انتشار" else "تأیید و بستن",
                    { if (waitsOn != null) asking = waitsOn.first to waitsOn.second.id else closeNow() },
                    context = if (waitsOn != null) "کار تمام شده؛ با تأیید تو همین فایل منتشر میشود." else "کار تمام شده؛ با تأیید تو جلسه بسته و بایگانی میشود.",
                    quiet = if (waitsOn != null) listOf(revise, QuietAction("فقط ببند") { closeNow() }) else listOf(revise),
                    state = closeState, icon = if (waitsOn != null) DivanIcon.SEND else DivanIcon.SEAL,
                    doneLabel = "جلسه بسته شد", onLeft = { closeState = DecisionState.IDLE }, place = DecisionPlace.PAGE,
                )
            }
            if (!closed) Column(side.padding(horizontal = 4.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                if (!asked && cv != null && participants.size > 1) AddresseeRow(participants, talk.addressee) { talk.addressee = it }
                // The paperclip once the session's talk is open (files go with a turn of it) and the hub takes them.
                TalkComposer(
                    talk, hf, onKey = { k -> caught = k; sheet = SessionSheet.KEY },
                    files = attach.takeIf { cv != null && filesOn }, pick = pick,
                    onFilesSent = { scope.launch { q.refresh(); env.cache.invalidate("sessions", "office") } },
                    seed = ComposerSeeds.peek(ref), onSeeded = { ComposerSeeds.take(ref) },
                    // The page's one gold is the decision bar's, the knot's action or the still card's; the send steps back beside them.
                    quietSend = bar || knot || (still != null && liveOn && sessionsOn), quietMic = true, placeholder = "به مسئول بگو چه بکند…", focus = focus,
                )
            } else if (closeState == DecisionState.IDLE) {
                Text(CLOSED_FA, style = Divan.type.caption, color = c.textMuted, modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 6.dp).testTag("session-closed"))
            }
        }
    }
    }

    asking?.let { (output, file) ->
        PublishFor(output, file, onDismiss = { asking = null }) { scope.launch { q.refresh(); env.cache.invalidate("sessions", "office") } }
    }

    when (sheet) {
        SessionSheet.NONE -> Unit
        SessionSheet.LIVE -> (shown ?: SessionActivity()).let { a ->
            com.coinepro.hq.ui.v14.HqSheet({ sheet = SessionSheet.NONE }, "کار زنده", sub = "هر قدم کار این جلسه، همان لحظه که برداشته میشود.") {
                LiveWorkSheetBody(a, ready = badge == "ready", canNudge = liveOn && sessionsOn && !stopped, nudging = nudge.busy, onNudge = { nudgeNow() }, companyName = companyName)
            }
        }
        SessionSheet.DETAILS -> o?.let { r ->
            com.coinepro.hq.ui.v14.HqSheet({ sheet = SessionSheet.NONE }, "جزئیات جلسه", sub = "همه‌ی چیزهایی که کنار گفتگو لازم میشوند") {
                SessionDetailsBody(
                    r, closed, sessionsOn, participants, talk.addressee,
                    onPick = { p -> if (p.kind == "holder") { talk.addressee = null; sheet = SessionSheet.NONE } else { picked = p; sheet = SessionSheet.PARTICIPANT } },
                    onAddPerson = { sheet = SessionSheet.PERSON }, onAddModel = { sheet = SessionSheet.MODEL },
                    onPace = { p -> setPace(p) },
                    pace = pace,
                    onTasksChanged = { q.refresh() },
                    onClose = { sheet = SessionSheet.CLOSE },
                    onReopen = { sheet = SessionSheet.NONE; reopen() },
                    onHide = { sheet = SessionSheet.NONE; hide() },
                    onErase = { sheet = SessionSheet.ERASE },
                    // ⟨1.22⟩ §40.2 the draft's card is in the chat now: back to it.
                    onDrafted = { sheet = SessionSheet.NONE; scope.launch { q.refresh(); talk.reload() } },
                    // ⟨1.0.1⟩ §50 a standing routine from one sentence
                    onRoutine = { sheet = SessionSheet.ROUTINE },
                    activity = shown, nudging = nudge.busy, onNudge = { nudgeNow() }, canNudge = liveOn && sessionsOn,
                )
            }
        }
        // ⟨1.0.1⟩ §50 «روال دائمی»: made, it is a row of the details the sheet goes back to (and a line of the session).
        SessionSheet.ROUTINE -> com.coinepro.hq.ui.v14.HqSheet({ sheet = SessionSheet.NONE }, "روال دائمی", sub = "یک جمله بگو؛ همان‌جا ساخته و روشن میشود.") {
            RoutineForm(ref) { made ->
                o?.let { r -> q.set(r.copy(routines = listOf(made) + r.routines.orEmpty().filter { it.ref != made.ref })) }
                toasts.ok("روال دائمی ساخته شد.")
                sheet = SessionSheet.DETAILS
                scope.launch { q.refresh(); talk.reload() }
            }
        }
        SessionSheet.PERSON -> com.coinepro.hq.ui.v14.HqSheet({ sheet = SessionSheet.NONE }, "آدم تازه در جلسه", sub = "مدیر یا کارمند هر شرکت، یا مشاور و ناظر؛ با جلسه حرف میزند و از داده‌ی خودش جواب میدهد.") {
            PersonPicker(company) { key ->
                sheet = SessionSheet.NONE
                scope.launch { addParticipant(env, toasts, ref, "person", key) { q.set(it); talk.reload() } }
            }
        }
        SessionSheet.MODEL -> com.coinepro.hq.ui.v14.HqSheet({ sheet = SessionSheet.NONE }, "مدل تازه در جلسه", sub = "هر مدل فقط همین گفتگو را میبیند و نظرش را میگوید؛ «نظر همه» یعنی هر حاضر یک جواب کوتاه، بعد جمع‌بندی مسئول.") {
            val left = playersToAdd(participants)
            if (left.isEmpty()) Text("هر سه مدل در جلسه‌اند.", style = Divan.type.small, color = c.textMuted)
            for (k in left) Row(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(c.card).clickable(role = Role.Button) {
                    sheet = SessionSheet.NONE
                    scope.launch { addParticipant(env, toasts, ref, "player", k) { q.set(it); talk.reload() } }
                }.padding(14.dp),
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                com.coinepro.hq.ui.work.PlayerLogo(PlayerOption.entries.firstOrNull { it.key == k } ?: PlayerOption.AUTO, size = 22.dp)
                Text(PLAYER_FA.getValue(k), style = Divan.type.bodyStrong, modifier = Modifier.weight(1f))
                DIcon(DivanIcon.ADD, size = 18.dp, tint = c.textSecondary)
            }
        }
        SessionSheet.PARTICIPANT -> picked?.let { p ->
            com.coinepro.hq.ui.v14.HqSheet(
                { sheet = SessionSheet.NONE; picked = null }, participantTitle(p), sub = if (isPlayer(p.key)) "مدل بیرونی در این جلسه" else "در این جلسه",
                bar = {
                    DecisionBar(
                        "حرف بعدی‌ام با او", { talk.addressee = p.key; sheet = SessionSheet.NONE }, icon = DivanIcon.MESSAGES,
                        quiet = if (!closed && sessionsOn) listOf(QuietAction("بیرون برود", danger = true) {
                            sheet = SessionSheet.NONE
                            scope.launch {
                                try { env.api.removeParticipant(ref, p.key); if (talk.addressee == p.key) talk.addressee = null; q.refresh(); talk.reload() }
                                catch (e: ApiException) { toasts.error(e.messageFa) }
                            }
                        }) else emptyList(),
                    )
                },
            ) {
                Text("حرف بعدی‌ات را به او میگویی؛ بقیه‌ی جلسه همان است.", style = Divan.type.small, color = c.textSecondary)
            }
        }
        SessionSheet.CLOSE -> o?.let { r ->
            CloseSheet(r, company, onDismiss = { sheet = SessionSheet.NONE },
                // ⟨0.18.0⟩ §40: the working group is drafted from this session (its card comes into the chat to edit and seal)
                onGroup = {
                    sheet = SessionSheet.NONE
                    scope.launch {
                        try {
                            env.api.draftPlaybook(r.ref, UUID.randomUUID().toString())
                            env.cache.invalidate("talk", "order-report", *com.coinepro.hq.ui.playbook.PLAYBOOK_TAGS)
                            toasts.ok("پیش‌نویس کارگروه آماده است؛ کارتش در گفتگوست.")
                            refreshAll()
                        } catch (e: ApiException) { toasts.error(e.messageFa) }
                    }
                },
                onLine = { sheet = SessionSheet.LINE },
                onClosed = { out -> sheet = SessionSheet.NONE; q.set(out); scope.launch { refreshAll() } })
        }
        SessionSheet.LINE -> company?.let { co ->
            com.coinepro.hq.ui.v14.HqSheet({ sheet = SessionSheet.NONE }, "خط تولید پیش از بستن", sub = "خط تولید بعد از بستن جلسه هم کار را ادامه میدهد؛ مُهر خودش را میخواهد.") {
                com.coinepro.hq.ui.v30.TemplateGallery(co) { sheet = SessionSheet.NONE; toasts.ok("خط تولید ساخته شد؛ حالا میتوانی جلسه را ببندی."); env.cache.invalidate("lines") }
            }
        }
        // ⟨1.19⟩ §37.1 erased for good: the session, its talk, files, outputs and works; then back to where he came from.
        SessionSheet.ERASE -> EraseSheet(com.coinepro.hq.core.net.EraseKind.SESSION, ref, onDismiss = { sheet = SessionSheet.NONE }) {
            sheet = SessionSheet.NONE
            nav.back()
        }
        SessionSheet.KEY -> com.coinepro.hq.ui.v32.TalkSheet(onDismiss = { sheet = SessionSheet.NONE; caught = "" }) {
            com.coinepro.hq.ui.v32.KeyBody({ sheet = SessionSheet.NONE; caught = "" }, initial = caught)
        }
        // ⟨1.35⟩ §57 one person of the session, in a small room of his own; closed, he goes on with his work.
        SessionSheet.TEAM_SEAT -> team?.seats?.firstOrNull { !it.empty && !it.holder && it.code == seatCode }?.let { s ->
            SideTalkSheet(ref, s, closed) { sheet = SessionSheet.NONE; seatCode = null; teamQ.refresh() }
        }
        SessionSheet.TEAM_HIRE -> team?.seats?.firstOrNull { it.empty && it.key == seatCode }?.let { s ->
            HireSeatSheet(ref, s, onDismiss = { sheet = SessionSheet.NONE; seatCode = null }) { out ->
                teamQ.set(out)
                sheet = SessionSheet.NONE
                seatCode = null
                scope.launch { q.refresh() }
            }
        }
        SessionSheet.TEAM_NARRATOR -> team?.narrator?.let { n ->
            TeamNarratorSheet(n.company, onDismiss = { sheet = SessionSheet.NONE }) { sheet = SessionSheet.NONE; teamQ.refresh() }
        }
    }
}

private suspend fun addParticipant(env: com.coinepro.hq.core.Env, toasts: com.coinepro.hq.ui.Toasts, ref: String, kind: String, key: String, done: suspend (OrderReport) -> Unit) {
    try {
        done(env.api.addParticipant(ref, kind, key))
        env.cache.invalidate("sessions", "office")
        toasts.ok("به جلسه آمد.")
    } catch (e: ApiException) {
        toasts.error(e.messageFa)
    }
}

/** The company an order belongs to: the route's first, else its holder's. */
internal fun companyOfOrder(o: OrderReport): String? =
    o.route?.companies?.firstOrNull() ?: o.participants.firstOrNull { it.kind == "holder" }?.company ?: o.ack?.assigned?.firstOrNull()?.company

/** The faces of the session's people: the hub's personas when it knows them, else made from the participant (a model, a manager). */
internal fun sessionFaces(known: List<TalkPersona>, participants: List<SessionParticipant>): List<TalkPersona> = participants.map { p ->
    known.firstOrNull { it.id == p.key } ?: when {
        isPlayer(p.key) -> TalkPersona(key = p.key, titleFa = participantTitle(p))
        '@' in p.key -> TalkPersona(key = "manager", role = p.key.substringBefore('@'), company = p.key.substringAfter('@'), titleFa = participantTitle(p))
        else -> TalkPersona(key = p.key, titleFa = participantTitle(p))
    }
}

// ---------------------------------------------------------------- header --
/**
 * ⟨1.0.1⟩ The session's header (C2.2, feature 13; M18). Folded it is ONE line: the short title, «کار ۳ از ۴» and the pace, the mood
 * light, «جزئیات». Open (at the top of the thread): where it came from, the title in two lines, and the facts (the task, the pace,
 * who holds it, and when the work last took a step while nobody works). Under it the plan as a line of parts. A tap anywhere on it
 * opens «جزئیات». [fraction]: how far it has folded. [waiting]: the session waits for the owner (the first open part is his).
 * [onOpenHeight]: how tall the open header is, in pixels (the thread keeps that room at its top).
 */
@Composable
internal fun SessionHeader(
    o: OrderReport, closed: Boolean, mood: String, moodWord: String, pace: String, waiting: Boolean, working: Boolean,
    lastStepAt: String?, fraction: () -> Float, onDetails: () -> Unit, modifier: Modifier = Modifier, onOpenHeight: (Int) -> Unit = {},
) {
    val c = Divan.colors
    val badge = sessionBadge(o)
    val task = taskOf(o.tasks)
    val holder = o.participants.firstOrNull { it.kind == "holder" }?.let(::participantTitle)
    val title = remember(o.textFa) { plain(oneLine(o.textFa)) }
    val parts = remember(o.tasks, waiting) { segmentsOf(o.tasks, waiting && !closed) }
    val paceFa = (PACE_FA[pace] ?: PACE_FA.getValue("auto")).takeIf { !closed }
    var fullPx by remember { mutableIntStateOf(0) }
    var restPx by remember { mutableIntStateOf(0) }
    LaunchedEffect(fullPx, restPx) { onOpenHeight(fullPx + restPx) }
    Column(modifier.fillMaxWidth().background(c.page).testTag("session-header").clickable(role = Role.Button, onClickLabel = "جزئیات جلسه", onClick = onDetails)) {
        CollapsingHeader(
            fraction, Modifier.fillMaxWidth(),
            line = {
                Row(Modifier.fillMaxWidth().height(48.dp).padding(start = 16.dp, end = 4.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(title, style = Divan.type.bodyStrong, color = c.textPrimary, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
                    val said = remember(task, paceFa) { facts(task?.let(::taskFa), paceFa) }
                    if (said.isNotEmpty()) Text(said, style = Divan.type.micro, color = c.textSecondary, maxLines = 1)
                    MoodLight(mood, word = moodWord)
                    IconBtn(DivanIcon.MORE, "جزئیات جلسه", onDetails, tint = c.textSecondary)
                }
            },
            full = {
                Column(Modifier.fillMaxWidth().onSizeChanged { fullPx = it.height }.padding(start = 16.dp, end = 4.dp, top = 6.dp, bottom = 8.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    // ⟨1.22⟩ §40.3 a session opened to adapt a playbook says so, small; a tap opens the playbook.
                    o.session?.source?.takeIf { it.isNotBlank() }?.let { com.coinepro.hq.ui.playbook.SourceChip(it, Modifier.padding(top = 2.dp)) }
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text(title, style = Divan.type.bodyStrong, color = c.textPrimary, maxLines = 2, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
                        IconBtn(DivanIcon.MORE, "جزئیات جلسه", onDetails, tint = c.textSecondary)
                    }
                    Row(Modifier.padding(end = 12.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        MoodLight(mood, word = moodWord)
                        Text(
                            remember(task, paceFa, holder) { facts(task?.let(::taskFa), paceFa, holder) },
                            style = Divan.type.micro, color = c.textSecondary, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f),
                        )
                        // ⟨1.24⟩ SS-1: while nobody works, when the work last took a step and the ring toward the hub's idle sweep.
                        if (!closed && !working) StallWatch(badge, lastStepAt ?: o.updatedAt.ifBlank { null })
                    }
                }
            },
        )
        if (parts.isNotEmpty()) Box(Modifier.onSizeChanged { restPx = it.height }.padding(horizontal = 16.dp).padding(bottom = 8.dp)) { SegmentLine(parts) }
    }
}

// ---------------------------------------------------------------- details --
/** «جزئیات»: everything that is not the chat. The order's words whole, «چه شد · حالا چه · از تو چه», the files the session made, what it
 *  remembers, its working group and routines, its state and pace, the people and models (and «+»), the plan, the results, what went
 *  out, the files he sent; then close (or reopen), hide and erase. Nothing in it is gold. */
@Composable
internal fun SessionDetailsBody(
    o: OrderReport,
    closed: Boolean,
    sessionsOn: Boolean,
    participants: List<SessionParticipant>,
    addressee: String?,
    onPick: (SessionParticipant) -> Unit,
    onAddPerson: () -> Unit,
    onAddModel: () -> Unit,
    onPace: (String) -> Unit,
    onTasksChanged: () -> Unit,
    onClose: () -> Unit,
    onReopen: () -> Unit,
    onHide: () -> Unit,
    onErase: () -> Unit,
    onDrafted: (com.coinepro.hq.core.net.Playbook) -> Unit = {},
    pace: String = o.pace,
    /** ⟨1.0.1⟩ §50 opens «روال دائمی». */
    onRoutine: () -> Unit = {},
    /** ⟨1.0.1⟩ what the session's work is doing now (null: not known here), and the nudge of a quiet one. */
    activity: SessionActivity? = null,
    nudging: Boolean = false,
    onNudge: () -> Unit = {},
    canNudge: Boolean = false,
) {
    val c = Divan.colors
    val brief = briefOf(o)
    val playbooksOn = served(HubFeature.PLAYBOOKS)
    val eraseOn = served(HubFeature.ERASE)
    val asked = o.turn != null && !closed
    val still = remember(o, activity, closed) { if (closed) null else stillOf(o, activity) }
    val mood = if (still != null) "still" else moodOf(activity, closed, sessionBadge(o), asked)
    val outsAll = rememberSessionOutputs(o.outputs)
    val revs = rememberRevisions(o.outputs, outsAll)
    val made = outsAll.filter { it.ref !in revs.hidden }.flatMap { it.files }
    Column(Modifier.testTag("details-order"), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text("متن فرمان", style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = c.textMuted)
        com.coinepro.hq.ui.Selectable { Para(o.textFa, style = Divan.type.body, color = c.textPrimary) }
        Text(
            plain(listOfNotNull(o.at.takeIf { it.isNotBlank() }?.let { "داده شد ${jDateTime(it)}" }, o.updatedAt.takeIf { it.isNotBlank() }?.let { "آخرین حرکت ${ago(it)}" }, o.session?.closedAt?.let { "بسته شد ${jDateTime(it)}" }).joinToString("؛ ")),
            style = Divan.type.micro, color = c.textMuted,
        )
    }
    HqCard(Modifier.fillMaxWidth(), color = c.card, padding = PaddingValues(14.dp)) {
        com.coinepro.hq.ui.Selectable {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                BriefLine("چه شد", brief.doneFa.ifBlank { "هنوز قدمی برداشته نشده." }, c.positive)
                BriefLine("حالا چه", brief.nowFa.ifBlank { "مسئول برنامه را مینویسد." }, c.silverInk)
                BriefLine("از تو چه", brief.needFa.ifBlank { "فعلاً چیزی لازم نیست." }, c.goldInk)
            }
        }
    }
    // ⟨1.0.1⟩ feature 29: everything the session made, at hand whatever the thread has scrolled to.
    if (made.isNotEmpty()) HqCard(Modifier.fillMaxWidth().testTag("details-files")) {
        SectionTitle("فایل‌های خروجی", note = "هر چه در این جلسه ساخته شد")
        FilesStrip(made, Modifier.padding(top = 10.dp))
    }
    // ⟨1.22⟩ §40.1 what the session remembers, and §40.2 its result as a working group (open or closed alike).
    o.memoryMd?.takeIf { it.isNotBlank() }?.let { com.coinepro.hq.ui.playbook.MemoryCard(it) }
    if (playbooksOn) com.coinepro.hq.ui.playbook.SessionPlaybooks(o.ref, onDrafted)
    // ⟨1.0.1⟩ §50 the standing routines asked for here, and the way to a new one (a hub before §50 sends no `routines`: neither shows).
    o.routines?.takeIf { served(HubFeature.ROUTINES) }?.let { rs ->
        SessionRoutines(rs, onChanged = onTasksChanged)
        if (sessionsOn) RoutineAction(onRoutine)
    }
    HqCard(Modifier.fillMaxWidth().testTag("details-state")) {
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            SectionTitle("وضعیت و روش کار")
            MoodLight(mood, word = moodWordFa(mood, activity))
            PaceRow(pace, enabled = !closed && sessionsOn, onPace = onPace)
            // ⟨1.0.1⟩ §54 a direct session: its holder is one session with the hub's tools; nothing else changes for the owner.
            if (o.direct) Text(DIRECT_FA, style = Divan.type.caption, color = c.textSecondary, modifier = Modifier.testTag("direct-session"))
            // §41 a quiet session never stalls unseen: when it last worked, and one tap that takes it up again (the page's still card
            // carries that tap once the session stands still; the line stays here).
            if (!closed && !asked && (mood == "idle" || mood == "still") && canNudge) IdleNudge(activity, nudging, onNudge, button = still == null)
        }
    }
    PeopleBar(participants, open = !closed && sessionsOn, addressee = addressee, onPick = onPick, onAddPerson = onAddPerson, onAddModel = onAddModel)
    if (o.tasks.isNotEmpty() || (sessionsOn && !closed)) TasksCard(o.ref, o.tasks, editable = sessionsOn && !closed, onChanged = onTasksChanged)
    if (o.outputs.isNotEmpty()) ResultsCard(o, revs)
    // ⟨1.0.1⟩ §51 what went out or is set to go out from this session; a scheduled one is taken back here.
    SessionPublishes(o.publishes, onChanged = onTasksChanged)
    if (o.files.any { it.id.isNotBlank() }) FilesCard(o.files.filter { it.id.isNotBlank() })
    if (sessionsOn) HqCard(Modifier.fillMaxWidth().testTag("details-end")) {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            SectionTitle("پایان جلسه")
            if (closed) HqButton("دوباره باز کن", onReopen, Modifier.fillMaxWidth(), variant = BtnVariant.SECONDARY, icon = DivanIcon.REFRESH)
            else {
                HqButton("تأیید و بستن", onClose, Modifier.fillMaxWidth(), variant = BtnVariant.SECONDARY, icon = DivanIcon.SEAL)
                Text("بستن یا لغو این فرمان، و کارگروه یا خط تولیدی که بعد از بستن بماند، در همان برگه است.", style = Divan.type.micro, color = c.textMuted)
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                HqButton(if (o.session?.hidden == true) "دوباره در فهرست بیاید" else "پنهان کن", onHide, Modifier.weight(1f), variant = BtnVariant.GHOST, size = BtnSize.SM, icon = DivanIcon.FILTER)
                // ⟨1.19⟩ §37.1 open or closed, hidden or not: for good, after the preview and the passkey.
                if (eraseOn) HqButton("پاک کردن برای همیشه", onErase, Modifier.weight(1f), variant = BtnVariant.DANGER, size = BtnSize.SM, icon = DivanIcon.REJECT)
            }
        }
    }
}

@Composable
private fun BriefLine(title: String, body: String, tint: androidx.compose.ui.graphics.Color) {
    val c = Divan.colors
    Row(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.Top) {
        Box(Modifier.padding(top = 6.dp).size(7.dp).clip(CircleShape).background(tint))
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(1.dp)) {
            Text(title, style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = c.textMuted)
            Text(plain(body), style = Divan.type.small, color = c.textPrimary)
        }
    }
}

/** «نتیجه‌ها»: each output of the session by its title; a tap opens its page. */
@Composable
private fun ResultsCard(o: OrderReport, revs: com.coinepro.hq.core.data.Revisions = com.coinepro.hq.core.data.Revisions()) {
    val nav = LocalNav.current
    val c = Divan.colors
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("نتیجه‌ها", note = "آنچه تا حالا ساخته شده")
        Column(Modifier.padding(top = 6.dp)) {
            // ⟨1.35⟩ §57.6 a chain of versions is its newest, with «نسخه‌ی n»
            o.outputs.filter { it.ref !in revs.hidden }.forEachIndexed { i, x ->
                if (i > 0) HorizontalDivider(color = c.lineDivider)
                Row(
                    Modifier.fillMaxWidth().clickable(role = Role.Button, onClickLabel = "باز کردن") { nav.go("outputs/${x.ref}") }.padding(vertical = 10.dp),
                    verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    DrawnMark(true, c.positive, size = 14.dp)
                    Text(plain(quietLine(x.titleFa)), style = Divan.type.small, color = c.textPrimary, maxLines = 2, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
                    revs.version[x.ref]?.let { com.coinepro.hq.ui.v14.Tag(com.coinepro.hq.core.data.versionFa(it)) }
                    Text(outputKindFa(x.kind), style = Divan.type.micro, color = c.textMuted)
                }
            }
        }
    }
}

// ---------------------------------------------------------------- people --
/** The holder, the people and the models in the session; tapping one talks to him next. «+ آدم» and «+ مدل» bring more in. */
@Composable
private fun PeopleBar(participants: List<SessionParticipant>, open: Boolean, addressee: String?, onPick: (SessionParticipant) -> Unit, onAddPerson: () -> Unit, onAddModel: () -> Unit) {
    val c = Divan.colors
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text("در جلسه", style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = c.textMuted)
        ScrollRow {
            for (p in participants) {
                val on = (p.kind == "holder" && addressee == null) || addressee == p.key
                Row(
                    Modifier.clip(CircleShape).background(if (on) c.raised else c.tile).border(1.dp, if (on) com.coinepro.hq.designsystem.silverLine() else c.lineDivider, CircleShape)
                        .clickable(role = Role.Button, onClickLabel = "با ${participantTitle(p)}") { onPick(p) }.padding(horizontal = 10.dp, vertical = 6.dp),
                    verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    if (isPlayer(p.key)) com.coinepro.hq.ui.work.PlayerLogo(PlayerOption.entries.firstOrNull { it.key == p.key.removePrefix("player:") } ?: PlayerOption.AUTO, size = 14.dp)
                    else DIcon(if (p.kind == "holder") DivanIcon.OWNER else DivanIcon.AGENT, size = 14.dp, tint = if (on) c.textPrimary else c.textSecondary)
                    Text(participantTitle(p), style = Divan.type.micro.copy(fontWeight = if (on) FontWeight.SemiBold else FontWeight.Normal), color = c.textPrimary, maxLines = 1)
                    if (p.kind == "holder") Text("مسئول", style = Divan.type.micro, color = c.textMuted)
                }
            }
            if (open) {
                AddChip("آدم", DivanIcon.HIRE, onAddPerson)
                AddChip("مدل", DivanIcon.MODEL, onAddModel)
            }
        }
    }
}

@Composable
private fun AddChip(label: String, icon: DivanIcon, onClick: () -> Unit) {
    val c = Divan.colors
    Row(
        Modifier.clip(CircleShape).border(1.dp, c.lineStrong, CircleShape).clickable(role = Role.Button, onClickLabel = "$label تازه", onClick = onClick).padding(horizontal = 10.dp, vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        DIcon(DivanIcon.ADD, size = 14.dp, tint = c.textSecondary)
        DIcon(icon, size = 14.dp, tint = c.textSecondary)
        Text(label, style = Divan.type.micro, color = c.textPrimary)
    }
}

/** Who the next word goes to: the holder, «همه», or one participant. */
@Composable
private fun AddresseeRow(participants: List<SessionParticipant>, addressee: String?, onPick: (String?) -> Unit) {
    val c = Divan.colors
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        Text("به", style = Divan.type.micro, color = c.textMuted)
        ScrollRow(Modifier.weight(1f)) {
            com.coinepro.hq.designsystem.FilterChip(addresseeFa(null, participants), addressee == null, { onPick(null) })
            com.coinepro.hq.designsystem.FilterChip("همه", addressee == "all", { onPick("all") })
            for (p in participants.filter { it.kind != "holder" }) com.coinepro.hq.designsystem.FilterChip(participantTitle(p), addressee == p.key, { onPick(p.key) })
        }
    }
}

/** A person to bring in: the advisor, the overseer, the assistant, or a manager of any company. */
@Composable
private fun PersonPicker(company0: String?, onPick: (String) -> Unit) {
    val c = Divan.colors
    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(c.card)) {
        FIXED_PEOPLE_FA.entries.filter { it.key != "secretary" }.forEachIndexed { i, (k, fa) ->
            if (i > 0) HorizontalDivider(color = c.lineDivider)
            Row(
                Modifier.fillMaxWidth().clickable(role = Role.Button) { onPick(k) }.padding(14.dp),
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                DIcon(when (k) { "advisor" -> DivanIcon.ADVISOR; "overseer" -> DivanIcon.OVERSEER; else -> DivanIcon.ASSISTANT }, size = 20.dp, tint = c.silverInk)
                Text(fa, style = Divan.type.bodyStrong, modifier = Modifier.weight(1f))
                DIcon(DivanIcon.ADD, size = 18.dp, tint = c.textSecondary)
            }
        }
    }
    com.coinepro.hq.ui.v32.InviteBody(onPick = { role, co, _ -> onPick("$role@$co") }, company0 = company0)
}

// ------------------------------------------------------------------- pace --
/** §34.1, §35.3 the pace: «با من» (one step, then he asks) or «خودکار» (to the end, stopping only for a seal); the owner switches it
 *  at any time (`POST /orders/{ref}/pace`). A closed session, or a hub without the route, shows it read-only. */
@Composable
private fun PaceRow(pace: String, enabled: Boolean, onPace: (String) -> Unit) {
    val c = Divan.colors
    Column(Modifier.fillMaxWidth().testTag("pace"), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Column {
            Text("روش کار: ${PACE_FA[pace] ?: "خودکار"}", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
            Text(PACE_HINT_FA[pace] ?: PACE_HINT_FA.getValue("auto"), style = Divan.type.micro, color = c.textMuted)
        }
        if (enabled) com.coinepro.hq.designsystem.Segmented(
            listOf(com.coinepro.hq.designsystem.SegOption("step", PACE_FA.getValue("step"), DivanIcon.OWNER), com.coinepro.hq.designsystem.SegOption("auto", PACE_FA.getValue("auto"), DivanIcon.RESUME)),
            pace, { p -> if (p != pace) onPace(p) }, Modifier.fillMaxWidth(),
        )
    }
}

// ------------------------------------------------------------------ tasks --
/** The plan, like a Claude Code task list: the holder writes it and ticks it; the owner adds, ticks and drops. */
@Composable
private fun TasksCard(ref: String, tasks: List<SessionTask>, editable: Boolean, onChanged: () -> Unit, modifier: Modifier = Modifier) {
    val env = LocalEnv.current
    val c = Divan.colors
    val toasts = LocalToasts.current
    val scope = rememberCoroutineScope()
    val add = rememberAction()
    var draft by rememberSaveable(ref) { mutableStateOf("") }
    val (done, total) = taskProgress(tasks)
    HqCard(modifier.fillMaxWidth()) {
        SectionTitle("برنامه", note = if (total == 0) "مسئول برنامه را مینویسد" else "$done از $total کار", icon = DivanIcon.TASK)
        Column(Modifier.padding(top = 8.dp)) {
            for (t in orderedTasks(tasks)) {
                val isDone = t.state == "done"
                val dropped = t.state == "dropped"
                Row(Modifier.fillMaxWidth().padding(vertical = 6.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    Box(
                        Modifier.size(22.dp).clip(CircleShape).background(if (isDone) c.positive else c.tile).border(1.dp, if (isDone) c.positive else c.lineStrong, CircleShape)
                            .clickable(enabled = editable && !dropped, role = Role.Checkbox, onClickLabel = if (isDone) "برگردان" else "تیک بزن") {
                                scope.launch {
                                    try { env.api.patchSessionTask(ref, t.id, state = tickedState(t.state)); onChanged() } catch (e: ApiException) { toasts.error(e.messageFa) }
                                }
                            },
                        contentAlignment = Alignment.Center,
                    ) { if (isDone) DIcon(DivanIcon.SEAL, size = 13.dp, tint = c.onGold) else if (t.state == "doing") Box(Modifier.size(8.dp).clip(CircleShape).background(c.silverInk)) }
                    Column(Modifier.weight(1f)) {
                        Text(
                            plain(t.titleFa), style = Divan.type.small.copy(textDecoration = if (isDone || dropped) TextDecoration.LineThrough else null),
                            color = if (dropped) c.textMuted else c.textPrimary, maxLines = 2, overflow = TextOverflow.Ellipsis,
                        )
                        val meta = remember(t) { facts(t.whoFa?.ifBlank { null }, if (t.by == "owner") "از تو" else null, if (t.state == "doing") "در کار" else null, if (dropped) "کنار رفت" else null) }
                        if (meta.isNotEmpty()) Text(meta, style = Divan.type.micro, color = c.textMuted)
                    }
                    if (editable && !isDone && !dropped) IconBtn(DivanIcon.CLOSE, "کنار بگذار", {
                        scope.launch { try { env.api.patchSessionTask(ref, t.id, state = "dropped"); onChanged() } catch (e: ApiException) { toasts.error(e.messageFa) } }
                    }, tint = c.textMuted)
                }
            }
            if (editable) Row(Modifier.padding(top = 6.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                HqTextField(draft, { draft = it }, "کار تازه در برنامه", Modifier.weight(1f), maxLength = 200)
                HqButton("افزودن", {
                    add.run { env.api.addSessionTask(ref, draft.trim()); draft = ""; onChanged() }
                }, size = BtnSize.SM, icon = DivanIcon.ADD, enabled = draft.trim().length >= 2, loading = add.busy)
            }
        }
    }
}

// ----------------------------------------------------------------- files --
/** ⟨1.18⟩ §36.3 the files the owner sent in this session, newest first: they belong to the order, and every work of it sees them.
 *  Pictures as thumbnails (a tap opens them), every other file a row with its kind and size that opens or saves it. */
@Composable
private fun FilesCard(files: List<FileRef>) {
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("فایل‌ها", note = "${faCount(files.size)} فایل از تو؛ هر کار این فرمان آن‌ها را میبیند", icon = DivanIcon.ATTACH)
        val (images, rest) = files.partition { it.kind == "image" }
        Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            FileThumbs(images)
            MessageMedia(rest, labelled = true)
        }
    }
}

// ------------------------------------------------------------------ close --
/**
 * «تأیید و بستن جلسه»: first what should stay after it (a working group, a production line), a sentence for the end, then the close
 * itself in the sheet's decision bar; the cancel is its quiet action, asked once more before it goes.
 */
@Composable
private fun CloseSheet(o: OrderReport, company: String?, onDismiss: () -> Unit, onGroup: () -> Unit, onLine: () -> Unit, onClosed: (OrderReport) -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val haptics = rememberHaptics()
    val c = Divan.colors
    val ok = rememberAction()
    val cancel = rememberAction()
    var note by rememberSaveable { mutableStateOf("") }
    var sure by rememberSaveable { mutableStateOf(false) }
    // One key per press, kept across a retry of the same press. The hub takes only a UUID as an Idempotency-Key (0.15.0: a key made from
    // the close's, «…-cancel», was a 422), so «لغو» has its own.
    val key = remember { UUID.randomUUID().toString() }
    val cancelKey = remember { UUID.randomUUID().toString() }
    val left = o.tasks.count { it.state == "todo" || it.state == "doing" }
    com.coinepro.hq.ui.v14.HqSheet(
        onDismiss, "تأیید و بستن جلسه", sub = "بعد از بستن، جلسه بایگانی میشود و هر وقت خواستی دوباره بازش میکنی.",
        bar = {
            DecisionBar(
                "تأیید و ببند", {
                    ok.run {
                        val out = env.api.closeSession(o.ref, "ok", note.trim(), key)
                        haptics.seal()
                        toasts.ok("جلسه بسته و بایگانی شد.")
                        onClosed(out)
                    }
                },
                context = when {
                    sure -> "با لغو، کارهای باز این فرمان می‌ایستند."
                    left > 0 -> "$left کار هنوز مانده؛ با بستن جلسه لغو میشوند."
                    else -> null
                },
                quiet = listOf(
                    if (sure) QuietAction("بله، لغو کن", danger = true, enabled = !cancel.busy) {
                        cancel.run {
                            val out = env.api.closeSession(o.ref, "cancel", note.trim(), cancelKey)
                            toasts.info("لغو و بایگانی شد.")
                            onClosed(out)
                        }
                    } else QuietAction("لغو فرمان") { sure = true },
                ),
                state = if (ok.busy) DecisionState.WORKING else DecisionState.IDLE, icon = DivanIcon.SEAL,
            )
        },
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("پیش از بستن، اگر کار تکرارشدنی است", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
            Text("یک کارگروه یا یک خط تولید راه بینداز تا این کار بعد از بسته شدن جلسه هم ادامه پیدا کند؛ کارتش همین‌جا در گفتگو می‌آید.", style = Divan.type.caption, color = c.textSecondary)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                HqButton("کارگروه از این جلسه", onGroup, Modifier.weight(1f), icon = DivanIcon.DEPARTMENT, size = BtnSize.SM)
                if (company != null) HqButton("خط تولید راه بینداز", onLine, Modifier.weight(1f), icon = DivanIcon.VIDEO, size = BtnSize.SM)
            }
        }
        HqTextField(note, { note = it }, "یک جمله برای پایان (اختیاری)", Modifier.fillMaxWidth(), singleLine = false, minLines = 2, maxLength = 1000)
    }
}
