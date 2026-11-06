package com.coinepro.hq.ui.session

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
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
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.SideEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.FIXED_PEOPLE_FA
import com.coinepro.hq.core.data.PACE_FA
import com.coinepro.hq.core.data.PACE_HINT_FA
import com.coinepro.hq.core.data.PLAYER_FA
import com.coinepro.hq.core.data.PlayerOption
import com.coinepro.hq.core.data.addresseeFa
import com.coinepro.hq.core.data.briefOf
import com.coinepro.hq.core.data.isPlayer
import com.coinepro.hq.core.data.keyPatterns
import com.coinepro.hq.core.data.orderParticipants
import com.coinepro.hq.core.data.orderedTasks
import com.coinepro.hq.core.data.participantTitle
import com.coinepro.hq.core.data.playersToAdd
import com.coinepro.hq.core.data.sessionBadge
import com.coinepro.hq.core.data.sessionClosed
import com.coinepro.hq.core.data.taskProgress
import com.coinepro.hq.core.data.tickedState
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.format.jDateTime
import com.coinepro.hq.core.media.FilePolicy
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.FileRef
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.OrderReport
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
import com.coinepro.hq.ui.v32.LiveBubble
import com.coinepro.hq.ui.v32.Phase
import com.coinepro.hq.ui.v32.TalkBubble
import com.coinepro.hq.ui.v32.TalkComposer
import com.coinepro.hq.ui.v32.TalkSession
import com.coinepro.hq.ui.v32.faCount
import com.coinepro.hq.ui.v32.rememberHandsFree
import java.util.UUID
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonObject

// Contract §34–§35 ⟨1.16, 1.17⟩: one order, one session, like a Claude Code session. The order's words and its badge at the top
// («نوبت تو» when the holder asks), «چه شد · حالا چه · از تو چه», the people and models in it, the pace, the plan, what blocks it (each
// with its fix), the results, and the live conversation with the holder (or one participant, or «همه»), the cards of the work done in
// place inline. «تأیید و بستن» closes and archives it, after offering a working group or a production line that keeps going; from the
// archive it opens again. Nothing technical and no ref is shown: the ref is the key only.

private enum class SessionSheet { NONE, PERSON, MODEL, CLOSE, LINE, KEY, PARTICIPANT, ERASE }

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

    if (!has) {
        Box(Modifier.fillMaxSize().padding(16.dp), contentAlignment = Alignment.Center) { Empty("جلسه‌ی فرمان با به‌روزرسانی بعدی هاب میاید", icon = DivanIcon.MEETING) }
        return
    }

    Column(Modifier.fillMaxSize().imePadding()) {
        val list = rememberLazyListState()
        val reduced = com.coinepro.hq.designsystem.LocalReducedMotion.current
        val total = talk.turns.size + (if (talk.phase != Phase.IDLE || talk.liveText.isNotBlank()) 1 else 0)
        var seen by remember { mutableIntStateOf(-1) }
        // A new word in the conversation brings it into view; opening the session starts at its top (the badge, the brief).
        LaunchedEffect(total, talk.liveText.length, talk.loading) {
            if (talk.loading) return@LaunchedEffect
            if (seen >= 0 && total > seen || (talk.liveText.isNotBlank() && seen >= 0)) {
                val last = (list.layoutInfo.totalItemsCount - 2).coerceAtLeast(0)
                if (reduced) list.scrollToItem(last) else list.animateScrollToItem(last)
            }
            seen = total
        }
        LazyColumn(Modifier.weight(1f).fillMaxWidth(), state = list, contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 12.dp, bottom = 16.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            when {
                o == null && q.error != null -> item(key = "error") { ErrorBlock(q.error, { q.refresh() }) }
                o == null -> item(key = "skeleton") { Skeleton(Modifier.fillMaxWidth().height(260.dp), radius = 16.dp) }
                else -> {
                    item(key = "head") { SessionHead(o, closed, sessionsOn, onHide = {
                        scope.launch {
                            try {
                                if (o.session?.hidden == true) env.api.unhideSession(ref) else env.api.hideSession(ref)
                                env.cache.invalidate("sessions", "office")
                                toasts.ok(if (o.session?.hidden == true) "دوباره در فهرست است." else "پنهان شد؛ چیزی پاک نشد.")
                                if (o.session?.hidden != true) nav.back() else q.refresh()
                            } catch (e: ApiException) { toasts.error(e.messageFa) }
                        }
                    }, onErase = { sheet = SessionSheet.ERASE }) }
                    item(key = "people") {
                        PeopleBar(participants, open = !closed && sessionsOn, addressee = talk.addressee,
                            onPick = { p -> if (p.kind == "holder") talk.addressee = null else { picked = p; sheet = SessionSheet.PARTICIPANT } },
                            onAddPerson = { sheet = SessionSheet.PERSON }, onAddModel = { sheet = SessionSheet.MODEL })
                    }
                    item(key = "pace") {
                        PaceRow(o.pace, enabled = !closed && sessionsOn) { p ->
                            scope.launch {
                                try {
                                    q.set(env.api.setPace(ref, p))
                                    env.cache.invalidate("sessions", "office")
                                    toasts.ok(if (p == "step") "از این به بعد قدم‌به‌قدم با تو." else "از این به بعد خودش تا آخر میرود.")
                                } catch (e: ApiException) { toasts.error(e.messageFa) }
                            }
                        }
                    }
                    if (o.blockers.isNotEmpty() && !closed) item(key = "blockers") {
                        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                            for (b in o.blockers) BlockerRow(b, company, o.ref, o.route?.budgetTokens)
                        }
                    }
                    if (o.tasks.isNotEmpty() || (sessionsOn && !closed)) item(key = "tasks") { TasksCard(ref, o.tasks, editable = sessionsOn && !closed) { q.refresh() } }
                    if (o.outputs.isNotEmpty()) item(key = "outputs") { OutputsCard(o) }
                    if (o.files.any { it.id.isNotBlank() }) item(key = "files") { FilesCard(o.files.filter { it.id.isNotBlank() }) }
                    item(key = "talk-title") {
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.padding(top = 4.dp)) {
                            DIcon(DivanIcon.MESSAGES, size = 16.dp, tint = c.textMuted)
                            Text("گفتگو", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textMuted, modifier = Modifier.weight(1f))
                            if (cv == null) Text("گفتگوی این فرمان هنوز باز نشده؛ جوابت مستقیم به فرمان میرود.", style = Divan.type.micro, color = c.textMuted)
                        }
                    }
                    if (talk.loading && talk.turns.isEmpty() && cv != null) items(2, key = { "tsk-$it" }) { i -> Skeleton(Modifier.fillMaxWidth(if (i == 0) 0.7f else 0.5f).height(56.dp), radius = 16.dp) }
                    var lastBy: String? = null
                    items(talk.turns.toList(), key = { "t-" + it.idText.ifBlank { "n${it.n}" } + it.n }) { t ->
                        val show = !t.owner && t.by != lastBy
                        lastBy = if (t.owner) null else t.by
                        TalkBubble(
                            t, faces.firstOrNull { it.id == t.by }, faces + talk.personas, show,
                            onReplay = if (t.audio.isEmpty()) null else ({ t.audio.sortedBy { a -> a.seq }.forEach(talk::play) }),
                            onRun = ::runCard, onDismiss = ::dismissCard,
                        )
                    }
                    if (talk.phase != Phase.IDLE || talk.liveText.isNotBlank() || talk.liveFailed != null) item(key = "live") {
                        LiveBubble(talk.phase, talk.liveText, talk.liveFailed, faces.firstOrNull { it.id == (talk.addressee?.takeIf { a -> a != "all" } ?: talk.conv?.persona) }, talk.liveCards.toList(), talk.speaking, ::runCard, ::dismissCard)
                    }
                    item(key = "end") {
                        EndBlock(o, closed, sessionsOn, onClose = { sheet = SessionSheet.CLOSE }, onReopen = {
                            scope.launch {
                                try { q.set(env.api.reopenSession(ref)); env.cache.invalidate("sessions", "office", "orders"); toasts.ok("دوباره باز شد؛ مسئول خبر دارد."); talk.reload() }
                                catch (e: ApiException) { toasts.error(e.messageFa) }
                            }
                        })
                    }
                }
            }
        }
        // Who answers, and the composer (typing, holding to talk, hands-free).
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
        }
    }

    when (sheet) {
        SessionSheet.NONE -> Unit
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
@Composable
private fun SessionHead(o: OrderReport, closed: Boolean, sessionsOn: Boolean, onHide: () -> Unit, onErase: () -> Unit) {
    val c = Divan.colors
    val badge = sessionBadge(o)
    val brief = briefOf(o)
    var menu by remember { mutableStateOf(false) }
    val eraseOn = served(HubFeature.ERASE)
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("جلسه‌ی فرمان", style = Divan.type.caption, color = c.textMuted, modifier = Modifier.weight(1f))
            BadgePill(badge)
            if (sessionsOn) Box {
                IconBtn(DivanIcon.MORE, "گزینه‌های جلسه", { menu = true })
                DropdownMenu(menu, { menu = false }, containerColor = c.overlay) {
                    DropdownMenuItem(
                        text = { Text(if (o.session?.hidden == true) "دوباره در فهرست بیاید" else "پنهان کن", style = Divan.type.body, color = c.textPrimary) },
                        leadingIcon = { DIcon(DivanIcon.FILTER, size = 20.dp, tint = c.textSecondary) },
                        onClick = { menu = false; onHide() },
                    )
                    // ⟨1.19⟩ §37.1 open or closed, hidden or not: for good, after the preview and the passkey.
                    if (eraseOn) DropdownMenuItem(
                        text = { Text("پاک کردن برای همیشه", style = Divan.type.body, color = c.negative) },
                        leadingIcon = { DIcon(DivanIcon.REJECT, size = 20.dp, tint = c.negative) },
                        onClick = { menu = false; onErase() },
                    )
                }
            }
        }
        com.coinepro.hq.ui.Selectable { Para(o.textFa, style = Divan.type.h3, color = c.textPrimary, maxLines = 6) }
        val reason = o.session?.reasonFa.orEmpty()
        if (reason.isNotBlank() && o.turn == null) Text(plain(reason), style = Divan.type.small, color = if (badge == "stuck") c.negative else c.textSecondary)
        Text(
            plain(listOfNotNull(o.at.takeIf { it.isNotBlank() }?.let { "داده شد ${jDateTime(it)}" }, o.updatedAt.takeIf { it.isNotBlank() }?.let { "آخرین حرکت ${ago(it)}" }, o.session?.closedAt?.let { "بسته شد ${jDateTime(it)}" }).joinToString("؛ ")),
            style = Divan.type.micro, color = c.textMuted,
        )
        // §34.3 the holder waits for the owner: the question, gold, before anything else.
        o.turn?.takeIf { !closed }?.let { t ->
            Column(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(c.softGold).border(1.dp, c.lineTahrir, RoundedCornerShape(14.dp)).padding(14.dp),
                verticalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    DIcon(DivanIcon.OWNER, size = 18.dp, tint = c.goldInk)
                    Text("نوبت تو", style = Divan.type.bodyStrong, color = c.goldInk, modifier = Modifier.weight(1f))
                    if (t.at.isNotBlank()) Text(ago(t.at), style = Divan.type.micro, color = c.textMuted)
                }
                com.coinepro.hq.ui.Selectable { Text(plain(t.questionFa), style = Divan.type.body, color = c.textPrimary) }
                Text(plain("${t.whoFa.ifBlank { "مسئول" }} میپرسد؛ پایین جواب بده، بنویس یا بگو."), style = Divan.type.micro, color = c.textSecondary)
            }
        }
        HqCard(Modifier.fillMaxWidth(), padding = PaddingValues(14.dp)) {
            com.coinepro.hq.ui.Selectable {
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    BriefLine("چه شد", brief.doneFa.ifBlank { "هنوز قدمی برداشته نشده." }, c.positive)
                    BriefLine("حالا چه", brief.nowFa.ifBlank { "مسئول برنامه را مینویسد." }, c.lapis)
                    BriefLine("از تو چه", brief.needFa.ifBlank { "فعلاً چیزی لازم نیست." }, c.goldInk)
                }
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

// ------------------------------------------------------------------- end --
@Composable
private fun EndBlock(o: OrderReport, closed: Boolean, sessionsOn: Boolean, onClose: () -> Unit, onReopen: () -> Unit) {
    val c = Divan.colors
    if (!sessionsOn) return
    val ready = sessionBadge(o) == "ready"
    Column(Modifier.fillMaxWidth().padding(top = 6.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        if (closed) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Pill("بسته و بایگانی شد", com.coinepro.hq.core.format.Tone.SILVER, icon = DivanIcon.DELIVERABLE)
                o.session?.closedAt?.let { Text(ago(it), style = Divan.type.micro, color = c.textMuted) }
            }
            HqButton("باز کردن دوباره", onReopen, Modifier.fillMaxWidth(), icon = DivanIcon.REFRESH)
        } else {
            if (ready) Text("کار تحویل شد؛ اگر راضی هستی ببند، یا پیش از بستن بگو چه بماند.", style = Divan.type.caption, color = c.textSecondary)
            HqButton("تأیید و بستن", onClose, Modifier.fillMaxWidth(), variant = if (ready) BtnVariant.PRIMARY else BtnVariant.SECONDARY, icon = DivanIcon.SEAL)
        }
    }
}

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
