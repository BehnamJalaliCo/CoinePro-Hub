package com.coinepro.hq.ui.session

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
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.SideEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.FIXED_PEOPLE_FA
import com.coinepro.hq.core.data.PACE_FA
import com.coinepro.hq.core.data.PACE_HINT_FA
import com.coinepro.hq.core.data.PLAYER_FA
import com.coinepro.hq.core.data.PlayerOption
import com.coinepro.hq.core.data.SessionEntry
import com.coinepro.hq.core.data.addresseeFa
import com.coinepro.hq.core.data.briefOf
import com.coinepro.hq.core.data.isPlayer
import com.coinepro.hq.core.data.keyPatterns
import com.coinepro.hq.core.data.orderParticipants
import com.coinepro.hq.core.data.orderedTasks
import com.coinepro.hq.core.data.outputKindFa
import com.coinepro.hq.core.data.participantTitle
import com.coinepro.hq.core.data.playersToAdd
import com.coinepro.hq.core.data.sessionBadge
import com.coinepro.hq.core.data.sessionClosed
import com.coinepro.hq.core.data.sessionStatusLine
import com.coinepro.hq.core.data.sessionTimeline
import com.coinepro.hq.core.data.stepWithSpeaker
import com.coinepro.hq.core.data.personaIdTitle
import com.coinepro.hq.core.data.taskProgress
import com.coinepro.hq.core.data.tickedState
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.format.jDateTime
import com.coinepro.hq.core.format.jTime
import com.coinepro.hq.core.media.FilePolicy
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.FileRef
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.OrderReport
import com.coinepro.hq.core.net.ReportOutput
import com.coinepro.hq.core.net.SessionParticipant
import com.coinepro.hq.core.net.SessionTask
import com.coinepro.hq.core.net.TalkCard
import com.coinepro.hq.core.net.TalkPersona
import com.coinepro.hq.core.net.gated
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.IconBtn
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.ScrollRow
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.designsystem.smoothSize
import com.coinepro.hq.designsystem.timesFig
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.activity
import com.coinepro.hq.ui.media.FileThumbs
import com.coinepro.hq.ui.media.MessageMedia
import com.coinepro.hq.ui.media.rememberAttachments
import com.coinepro.hq.ui.media.rememberPickers
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.v29.BlockerRow
import com.coinepro.hq.ui.v29.OutputsCard
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
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonObject

// Contract §34–§35 ⟨1.16, 1.17⟩: one order, one session, like a Claude Code session. ⟨0.17.0⟩ «ساده و شیک»: a chat that gets things
// done. A compact head (the order's words in two lines that open on a tap, the badge and one line of what is happening, «جزئیات»); the
// chat takes the screen and opens at its newest word, the steps of the work in it as one quiet line each at their time, each result
// delivered as one compact card; what blocks it, with its fix, at the foot of the chat. Everything else (the brief, the people and models,
// the pace, the plan, the results and files, close, cancel, hide and erase) is in the «جزئیات» sheet; «تأیید و بستن» is also a pill in
// the head once the work is ready. Nothing technical and no ref is shown: the ref is the key only.

private enum class SessionSheet { NONE, DETAILS, PERSON, MODEL, CLOSE, LINE, KEY, PARTICIPANT, ERASE }

@Composable
fun OrderSessionScreen(ref: String) {
    val env = LocalEnv.current
    val nav = LocalNav.current
    val toasts = LocalToasts.current
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
    // The stream: a turn or card changed (the conversation), the session moved (its report).
    LaunchedEffect(env, ref) {
        env.stream.events.collect { e ->
            when {
                e.type.startsWith("talk.") && !talk.busy -> talk.reload()
                (e.type == "session.updated" || e.type == "order.report") && e.ref == ref -> q.refresh()
            }
        }
    }

    val closed = o?.let(::sessionClosed) == true
    val turnOpen = o?.turn != null && !closed
    // The owner's words go to the order's reply while the holder waits for him (§34.3), or while there is no talk at all.
    SideEffect {
        talk.interceptor = if (o != null && !closed && (turnOpen || cv == null)) { text, _ ->
            try {
                val out = env.api.orderReply(ref, text, UUID.randomUUID().toString())
                q.set(out)
                env.cache.invalidate("sessions", "office", "orders")
                talk.reload()
                true
            } catch (e: ApiException) {
                toasts.error(e.messageFa)
                false
            }
        } else null
    }

    var sheet by rememberSaveable { mutableStateOf(SessionSheet.NONE) }
    var picked by remember { mutableStateOf<SessionParticipant?>(null) }
    var caught by remember { mutableStateOf("") }
    val hf = rememberHandsFree(talk, { keyPatterns(emptyList()) }) { k -> caught = k; sheet = SessionSheet.KEY }

    val participants = orderParticipants(o?.participants.orEmpty())
    val faces = sessionFaces(talk.personas, participants)
    val company = o?.let(::companyOfOrder)

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
    fun reopen() = scope.launch {
        try { q.set(env.api.reopenSession(ref)); env.cache.invalidate("sessions", "office", "orders"); toasts.ok("دوباره باز شد؛ مسئول خبر دارد."); talk.reload() }
        catch (e: ApiException) { toasts.error(e.messageFa) }
    }

    if (!has) {
        Box(Modifier.fillMaxSize().padding(16.dp), contentAlignment = Alignment.Center) { Empty("جلسه‌ی فرمان با به‌روزرسانی بعدی هاب میاید", icon = DivanIcon.MEETING) }
        return
    }

    // The chat in time order; drawn bottom-up, so it opens at its newest word.
    val entries = sessionTimeline(talk.turns.toList(), o, hasTalk = cv != null)
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
    val live = talk.phase != Phase.IDLE || talk.liveText.isNotBlank() || talk.liveFailed != null

    Column(Modifier.fillMaxSize().imePadding()) {
        when {
            o != null -> SessionHead(o, closed, sessionsOn, onDetails = { sheet = SessionSheet.DETAILS }, onClose = { sheet = SessionSheet.CLOSE })
            q.error != null -> Box(Modifier.fillMaxWidth().padding(16.dp)) { ErrorBlock(q.error, { q.refresh() }) }
            else -> Skeleton(Modifier.fillMaxWidth().padding(16.dp).height(58.dp), radius = 12.dp)
        }
        HorizontalDivider(color = c.lineDivider)
        Box(Modifier.weight(1f).fillMaxWidth()) {
            LazyColumn(
                Modifier.fillMaxSize().testTag("session-chat"), state = list, reverseLayout = true,
                contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 12.dp, bottom = 8.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp, Alignment.Bottom),
            ) {
                // The foot of the chat: what blocks the work now, each with its fix (or a hair of space).
                item(key = CHAT_TAIL) {
                    val blockers = o?.blockers.orEmpty().takeIf { !closed }.orEmpty()
                    if (blockers.isEmpty()) Spacer(Modifier.height(2.dp))
                    else Column(verticalArrangement = Arrangement.spacedBy(8.dp)) { for (b in blockers) BlockerRow(b, company, o?.ref, o?.route?.budgetTokens) }
                }
                if (live) item(key = "live") {
                    LiveBubble(talk.phase, talk.liveText, talk.liveFailed, faces.firstOrNull { it.id == (talk.addressee?.takeIf { a -> a != "all" } ?: talk.conv?.persona) }, talk.liveCards.toList(), talk.speaking, ::runCard, ::dismissCard)
                }
                items(entries.asReversed(), key = { it.key }) { e ->
                    when (e) {
                        is SessionEntry.Said -> {
                            val t = e.turn
                            TalkBubble(
                                t, faces.firstOrNull { it.id == t.by }, faces + talk.personas, named[e.key] == true,
                                onReplay = if (t.audio.isEmpty()) null else ({ t.audio.sortedBy { a -> a.seq }.forEach(talk::play) }),
                                onRun = ::runCard, onDismiss = ::dismissCard,
                            )
                        }
                        is SessionEntry.Step -> StepLine(stepWithSpeaker(e.text, e.by?.let { b -> personaIdTitle(b, faces + talk.personas) }), e.at)
                        is SessionEntry.Output -> OutputLine(e.output, e.at)
                    }
                }
                if (talk.loading && talk.turns.isEmpty() && cv != null) items(2, key = { "tsk-$it" }) { i -> Skeleton(Modifier.fillMaxWidth(if (i == 0) 0.5f else 0.7f).height(56.dp), radius = 16.dp) }
                // The top of the chat: when the session began, and a word when its talk is not open yet.
                if (o != null) item(key = "start") {
                    Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        if (o.at.isNotBlank()) StepLine("جلسه باز شد ${jDateTime(o.at)}", "")
                        if (cv == null && !closed) StepLine("گفتگوی این فرمان هنوز باز نشده؛ جوابت مستقیم به فرمان میرود.", "")
                    }
                }
            }
            JumpToEnd(follow)
        }
        // Who answers, and the composer (typing, holding to talk, hands-free); a closed session, its way back.
        if (o != null && !closed) Column(Modifier.fillMaxWidth().background(c.page).padding(horizontal = 12.dp).padding(bottom = 8.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            HorizontalDivider(color = c.lineDivider)
            if (turnOpen) Text(plain("جوابت به «${o.turn?.whoFa?.ifBlank { null } ?: addresseeFa(null, participants)}» میرود"), style = Divan.type.micro, color = c.goldInk, modifier = Modifier.padding(horizontal = 4.dp))
            else if (cv != null && participants.size > 1) AddresseeRow(participants, talk.addressee) { talk.addressee = it }
            // The paperclip once the session's talk is open (files go with a turn of it) and the hub takes them.
            TalkComposer(
                talk, hf, onKey = { k -> caught = k; sheet = SessionSheet.KEY },
                files = attach.takeIf { cv != null && filesOn }, pick = pick,
                onFilesSent = { scope.launch { q.refresh(); env.cache.invalidate("sessions", "office") } },
            )
        } else if (o != null && sessionsOn) ClosedBar(o, onReopen = { reopen() })
    }

    when (sheet) {
        SessionSheet.NONE -> Unit
        SessionSheet.DETAILS -> o?.let { r ->
            com.coinepro.hq.ui.v14.HqSheet({ sheet = SessionSheet.NONE }, "جزئیات جلسه") {
                SessionDetailsBody(
                    r, closed, sessionsOn, participants, talk.addressee,
                    onPick = { p -> if (p.kind == "holder") { talk.addressee = null; sheet = SessionSheet.NONE } else { picked = p; sheet = SessionSheet.PARTICIPANT } },
                    onAddPerson = { sheet = SessionSheet.PERSON }, onAddModel = { sheet = SessionSheet.MODEL },
                    onPace = { p ->
                        scope.launch {
                            try {
                                q.set(env.api.setPace(ref, p))
                                env.cache.invalidate("sessions", "office")
                                toasts.ok(if (p == "step") "از این به بعد قدم‌به‌قدم با تو." else "از این به بعد خودش تا آخر میرود.")
                            } catch (e: ApiException) { toasts.error(e.messageFa) }
                        }
                    },
                    onTasksChanged = { q.refresh() },
                    onClose = { sheet = SessionSheet.CLOSE },
                    onReopen = { sheet = SessionSheet.NONE; reopen() },
                    onHide = { sheet = SessionSheet.NONE; hide() },
                    onErase = { sheet = SessionSheet.ERASE },
                    // ⟨1.22⟩ §40.2 the draft's card is in the chat now: back to it.
                    onDrafted = { sheet = SessionSheet.NONE; scope.launch { q.refresh(); talk.reload() } },
                )
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
                DIcon(DivanIcon.ADD, size = 18.dp, tint = c.goldInk)
            }
        }
        SessionSheet.PARTICIPANT -> picked?.let { p ->
            com.coinepro.hq.ui.v14.HqSheet({ sheet = SessionSheet.NONE; picked = null }, participantTitle(p), sub = if (isPlayer(p.key)) "مدل بیرونی در این جلسه" else "در این جلسه") {
                HqButton("حرف بعدی‌ام با او", { talk.addressee = p.key; sheet = SessionSheet.NONE }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, icon = DivanIcon.MESSAGES)
                if (!closed && sessionsOn) HqButton("از جلسه بیرون برود", {
                    sheet = SessionSheet.NONE
                    scope.launch {
                        try { env.api.removeParticipant(ref, p.key); if (talk.addressee == p.key) talk.addressee = null; q.refresh(); talk.reload() }
                        catch (e: ApiException) { toasts.error(e.messageFa) }
                    }
                }, Modifier.fillMaxWidth(), variant = BtnVariant.GHOST, icon = DivanIcon.CLOSE)
            }
        }
        SessionSheet.CLOSE -> o?.let { r ->
            CloseSheet(r, company, onDismiss = { sheet = SessionSheet.NONE },
                onGroup = { sheet = SessionSheet.NONE; scope.launch { talk.addressee = null; talk.interceptor = null; talk.send("پیش از بستن، برای این کار یک کارگروه راه بینداز که بعد از بستن جلسه هم ادامه بدهد.") } },
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

// ------------------------------------------------------------------ head --
/** ⟨0.17.0⟩ The head, compact: the order's words in at most two lines (a tap opens them all), the badge and one line of what is
 *  happening, «جزئیات» for everything else; «تأیید و بستن» beside the badge once the work is ready. */
@Composable
private fun SessionHead(o: OrderReport, closed: Boolean, sessionsOn: Boolean, onDetails: () -> Unit, onClose: () -> Unit) {
    val c = Divan.colors
    val badge = sessionBadge(o)
    val line = sessionStatusLine(o)
    var open by rememberSaveable(o.ref) { mutableStateOf(false) }
    Column(Modifier.fillMaxWidth().background(c.page).padding(start = 16.dp, end = 8.dp, top = 6.dp, bottom = 10.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        // ⟨1.22⟩ §40.3 a session opened to adapt a playbook says so, small; a tap opens the playbook.
        o.session?.source?.takeIf { it.isNotBlank() }?.let { com.coinepro.hq.ui.playbook.SourceChip(it, Modifier.padding(top = 4.dp, end = 8.dp)) }
        Row(verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(
                plain(o.textFa.trim()), style = Divan.type.bodyStrong, color = c.textPrimary,
                maxLines = if (open) Int.MAX_VALUE else 2, overflow = TextOverflow.Ellipsis,
                modifier = Modifier.weight(1f).padding(top = 6.dp).smoothSize()
                    .clickable(role = Role.Button, onClickLabel = if (open) "کوتاه کن" else "همه‌ی متن فرمان") { open = !open },
            )
            HqButton("جزئیات", onDetails, variant = BtnVariant.GHOST, size = BtnSize.SM, icon = DivanIcon.MORE, label = "جزئیات جلسه")
        }
        Row(Modifier.padding(end = 8.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            BadgePill(badge)
            Text(
                plain(line), style = Divan.type.caption, color = if (badge == "stuck") c.negative else c.textSecondary,
                maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f),
            )
            if (badge == "ready" && !closed && sessionsOn) HqButton("تأیید و بستن", onClose, variant = BtnVariant.PRIMARY, size = BtnSize.SM, icon = DivanIcon.SEAL)
        }
    }
}

// --------------------------------------------------------------- the chat --
/** A step of the work in the chat: one quiet, centred line, its time always in view; a tap shows the whole of it. */
@Composable
private fun StepLine(text: String, at: String) {
    val c = Divan.colors
    var open by remember { mutableStateOf(false) }
    Box(Modifier.fillMaxWidth().padding(horizontal = 20.dp), contentAlignment = Alignment.Center) {
        Row(
            Modifier.clip(RoundedCornerShape(10.dp)).background(c.tile.copy(alpha = 0.6f))
                .clickable(role = Role.Button, onClickLabel = if (open) "کوتاه کن" else "همه‌ی این خط") { open = !open }
                .padding(horizontal = 10.dp, vertical = 3.dp),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            Text(
                plain(text), style = Divan.type.micro.copy(textAlign = TextAlign.Center), color = c.textMuted,
                maxLines = if (open) Int.MAX_VALUE else 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f, fill = false),
            )
            if (at.isNotBlank()) Text(timesFig(jTime(at)), style = Divan.type.micro, color = c.textMuted, maxLines = 1)
        }
    }
}

/** A result delivered, in the chat at its time: one compact card, its title and «باز کن». */
@Composable
private fun OutputLine(x: ReportOutput, at: String) {
    val c = Divan.colors
    val nav = LocalNav.current
    val shape = RoundedCornerShape(14.dp)
    Row(
        Modifier.fillMaxWidth().clip(shape).background(c.card).border(1.dp, c.lineTahrir, shape)
            .clickable(role = Role.Button, onClickLabel = "باز کردن") { nav.go("outputs/${x.ref}") }.padding(start = 12.dp, end = 4.dp, top = 8.dp, bottom = 8.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Box(Modifier.size(34.dp).clip(CircleShape).background(c.softGold), contentAlignment = Alignment.Center) { DIcon(DivanIcon.DELIVERABLE, size = 18.dp, tint = c.goldInk) }
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(1.dp)) {
            Text(plain(x.titleFa.ifBlank { outputKindFa(x.kind) }), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text(
                buildAnnotatedString { append("${outputKindFa(x.kind)} تحویل شد"); if (at.isNotBlank()) { append("  ·  "); append(timesFig(jTime(at))) } },
                style = Divan.type.micro, color = c.textMuted, maxLines = 1,
            )
        }
        HqButton("باز کن", { nav.go("outputs/${x.ref}") }, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.NEXT)
    }
}

/** A closed session's foot, where the composer was: archived, when, and «باز کردن دوباره». */
@Composable
private fun ClosedBar(o: OrderReport, onReopen: () -> Unit) {
    val c = Divan.colors
    Column(Modifier.fillMaxWidth().background(c.page)) {
        HorizontalDivider(color = c.lineDivider)
        Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 10.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Pill("بسته و بایگانی شد", com.coinepro.hq.core.format.Tone.SILVER, icon = DivanIcon.DELIVERABLE)
            Text(o.session?.closedAt?.let(::ago).orEmpty(), style = Divan.type.micro, color = c.textMuted, modifier = Modifier.weight(1f), maxLines = 1)
            HqButton("باز کردن دوباره", onReopen, size = BtnSize.SM, icon = DivanIcon.REFRESH)
        }
    }
}

// ---------------------------------------------------------------- details --
/** «جزئیات»: everything that is not the chat. The order's words whole, «چه شد · حالا چه · از تو چه», the people and models (and «+»), the
 *  pace, the plan, the results and the files; then close (or reopen), hide and erase. */
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
) {
    val c = Divan.colors
    val brief = briefOf(o)
    val playbooksOn = served(HubFeature.PLAYBOOKS)
    val ready = sessionBadge(o) == "ready"
    val eraseOn = served(HubFeature.ERASE)
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
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
                BriefLine("حالا چه", brief.nowFa.ifBlank { "مسئول برنامه را مینویسد." }, c.lapis)
                BriefLine("از تو چه", brief.needFa.ifBlank { "فعلاً چیزی لازم نیست." }, c.goldInk)
            }
        }
    }
    // ⟨1.22⟩ §40.1 what the session remembers, and §40.2 its result as a working group (open or closed alike).
    o.memoryMd?.takeIf { it.isNotBlank() }?.let { com.coinepro.hq.ui.playbook.MemoryCard(it) }
    if (playbooksOn) com.coinepro.hq.ui.playbook.SessionPlaybooks(o.ref, onDrafted)
    PeopleBar(participants, open = !closed && sessionsOn, addressee = addressee, onPick = onPick, onAddPerson = onAddPerson, onAddModel = onAddModel)
    PaceRow(o.pace, enabled = !closed && sessionsOn, onPace = onPace)
    if (o.tasks.isNotEmpty() || (sessionsOn && !closed)) TasksCard(o.ref, o.tasks, editable = sessionsOn && !closed, onChanged = onTasksChanged)
    if (o.outputs.isNotEmpty()) OutputsCard(o)
    if (o.files.any { it.id.isNotBlank() }) FilesCard(o.files.filter { it.id.isNotBlank() })
    if (sessionsOn) Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        if (closed) HqButton("باز کردن دوباره", onReopen, Modifier.fillMaxWidth(), icon = DivanIcon.REFRESH)
        else {
            HqButton("تأیید و بستن", onClose, Modifier.fillMaxWidth(), variant = if (ready) BtnVariant.PRIMARY else BtnVariant.SECONDARY, icon = DivanIcon.SEAL)
            Text("بستن یا لغو این فرمان، و کارگروه یا خط تولیدی که بعد از بستن بماند، در همان برگه است.", style = Divan.type.micro, color = c.textMuted, modifier = Modifier.padding(horizontal = 4.dp))
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            HqButton(if (o.session?.hidden == true) "دوباره در فهرست بیاید" else "پنهان کن", onHide, Modifier.weight(1f), variant = BtnVariant.GHOST, size = BtnSize.SM, icon = DivanIcon.FILTER)
            // ⟨1.19⟩ §37.1 open or closed, hidden or not: for good, after the preview and the passkey.
            if (eraseOn) HqButton("پاک کردن برای همیشه", onErase, Modifier.weight(1f), variant = BtnVariant.DANGER, size = BtnSize.SM, icon = DivanIcon.REJECT)
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
                    Modifier.clip(CircleShape).background(if (on) c.softGold else c.tile).border(1.dp, if (on) c.lineTahrir else c.lineDivider, CircleShape)
                        .clickable(role = Role.Button, onClickLabel = "با ${participantTitle(p)}") { onPick(p) }.padding(horizontal = 10.dp, vertical = 6.dp),
                    verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    if (isPlayer(p.key)) com.coinepro.hq.ui.work.PlayerLogo(PlayerOption.entries.firstOrNull { it.key == p.key.removePrefix("player:") } ?: PlayerOption.AUTO, size = 14.dp)
                    else DIcon(if (p.kind == "holder") DivanIcon.OWNER else DivanIcon.AGENT, size = 14.dp, tint = if (on) c.goldInk else c.textSecondary)
                    Text(participantTitle(p), style = Divan.type.micro.copy(fontWeight = if (on) FontWeight.SemiBold else FontWeight.Normal), color = c.textPrimary, maxLines = 1)
                    if (p.kind == "holder") Text("مسئول", style = Divan.type.micro, color = c.goldInk)
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
        DIcon(DivanIcon.ADD, size = 14.dp, tint = c.goldInk)
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
                DIcon(when (k) { "advisor" -> DivanIcon.ADVISOR; "overseer" -> DivanIcon.OVERSEER; else -> DivanIcon.ASSISTANT }, size = 20.dp, tint = c.goldInk)
                Text(fa, style = Divan.type.bodyStrong, modifier = Modifier.weight(1f))
                DIcon(DivanIcon.ADD, size = 18.dp, tint = c.goldInk)
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
    Column(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(horizontal = 12.dp, vertical = 10.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            DIcon(if (pace == "step") DivanIcon.OWNER else DivanIcon.RESUME, size = 18.dp, tint = c.goldInk)
            Column(Modifier.weight(1f)) {
                Text("روش کار: ${PACE_FA[pace] ?: "خودکار"}", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                Text(PACE_HINT_FA[pace] ?: PACE_HINT_FA.getValue("auto"), style = Divan.type.micro, color = c.textMuted)
            }
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
private fun TasksCard(ref: String, tasks: List<SessionTask>, editable: Boolean, onChanged: () -> Unit) {
    val env = LocalEnv.current
    val c = Divan.colors
    val toasts = LocalToasts.current
    val scope = rememberCoroutineScope()
    val add = rememberAction()
    var draft by rememberSaveable(ref) { mutableStateOf("") }
    val (done, total) = taskProgress(tasks)
    HqCard(Modifier.fillMaxWidth()) {
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
                    ) { if (isDone) DIcon(DivanIcon.SEAL, size = 13.dp, tint = c.onGold) else if (t.state == "doing") Box(Modifier.size(8.dp).clip(CircleShape).background(c.goldFill)) }
                    Column(Modifier.weight(1f)) {
                        Text(
                            plain(t.titleFa), style = Divan.type.small.copy(textDecoration = if (isDone || dropped) TextDecoration.LineThrough else null),
                            color = if (dropped) c.textMuted else c.textPrimary, maxLines = 2, overflow = TextOverflow.Ellipsis,
                        )
                        val meta = listOfNotNull(t.whoFa?.ifBlank { null }, if (t.by == "owner") "از تو" else null, if (t.state == "doing") "در کار" else null, if (dropped) "کنار رفت" else null).joinToString(" · ")
                        if (meta.isNotBlank()) Text(meta, style = Divan.type.micro, color = c.textMuted)
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
/** «تأیید و بستن»: first what should stay after it (a working group, a production line), then the close itself, or the cancel. */
@Composable
private fun CloseSheet(o: OrderReport, company: String?, onDismiss: () -> Unit, onGroup: () -> Unit, onLine: () -> Unit, onClosed: (OrderReport) -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val ok = rememberAction()
    val cancel = rememberAction()
    var note by rememberSaveable { mutableStateOf("") }
    // One key per press, kept across a retry of the same press. The hub takes only a UUID as an Idempotency-Key (0.15.0: a key made from
    // the close's, «…-cancel», was a 422), so «لغو» has its own.
    val key = remember { UUID.randomUUID().toString() }
    val cancelKey = remember { UUID.randomUUID().toString() }
    com.coinepro.hq.ui.v14.HqSheet(onDismiss, "تأیید و بستن", sub = "جلسه بسته و بایگانی میشود؛ هر وقت خواستی از بایگانی دوباره بازش میکنی.") {
        Text("پیش از بستن، چیزی بماند؟", style = Divan.type.bodyStrong, color = c.textPrimary)
        Text("کارگروه یا خط تولید بعد از بستن هم کار را ادامه میدهد؛ بقیه‌ی کارهای باز این جلسه بسته میشوند.", style = Divan.type.caption, color = c.textMuted)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            HqButton("کارگروه راه بینداز", onGroup, Modifier.weight(1f), icon = DivanIcon.DEPARTMENT, size = BtnSize.SM)
            if (company != null) HqButton("خط تولید راه بینداز", onLine, Modifier.weight(1f), icon = DivanIcon.VIDEO, size = BtnSize.SM)
        }
        HorizontalDivider(color = c.lineDivider)
        HqTextField(note, { note = it }, "یک جمله برای پایان (اختیاری)", Modifier.fillMaxWidth(), singleLine = false, minLines = 2, maxLength = 1000)
        HqButton("تأیید و بستن", {
            ok.run {
                val out = env.api.closeSession(o.ref, "ok", note.trim(), key)
                toasts.ok("بسته و بایگانی شد.")
                onClosed(out)
            }
        }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, size = BtnSize.LG, icon = DivanIcon.SEAL, loading = ok.busy)
        HqButton("لغو این فرمان", {
            cancel.run {
                val out = env.api.closeSession(o.ref, "cancel", note.trim(), cancelKey)
                toasts.info("لغو و بایگانی شد.")
                onClosed(out)
            }
        }, Modifier.fillMaxWidth(), variant = BtnVariant.TEXT, icon = DivanIcon.REJECT, loading = cancel.busy)
    }
}
