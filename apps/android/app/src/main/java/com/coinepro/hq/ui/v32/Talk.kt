package com.coinepro.hq.ui.v32

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.FIXED_PERSONAS
import com.coinepro.hq.core.data.PERSONA_FA
import com.coinepro.hq.core.data.enginesInUse
import com.coinepro.hq.core.data.faceOrder
import com.coinepro.hq.core.data.lightState
import com.coinepro.hq.core.data.personaTitle
import com.coinepro.hq.core.data.priceWarning
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.TalkCard
import com.coinepro.hq.core.net.TalkPersona
import com.coinepro.hq.core.net.VoiceEngine
import com.coinepro.hq.core.net.VoiceMeter
import com.coinepro.hq.core.net.gated
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.IconBtn
import com.coinepro.hq.designsystem.LocalReducedMotion
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.designsystem.timesFig
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.activity
import com.coinepro.hq.ui.itemMotion
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v29.served
import java.time.LocalDate
import java.time.ZoneId
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonPrimitive

// Contract §32: the talk screen. A row of faces on top (the holding secretary, the overseer, the personal assistant, the advisor, any manager
// brought in with «+»); the owner and the persona as a chat with the cards of §32.3 inline; the light of each voice and the live meter in
// the header; and the composer for typing, holding to talk and hands-free. A conversation is consult by default: nothing is made until a
// card is tapped.

private enum class TalkSheetKind { NONE, KEY, METER, VOICES, INVITE, ENGINE }

/** The suggestions of an empty conversation, by persona (what the owner may ask first). */
private val STARTERS = mapOf(
    "secretary" to listOf("امروز چه چیزهایی منتظر من است؟", "خلاصه‌ی کارهای امروز شرکت‌ها را بگو", "یک فرمان تازه میخواهم بدهم"),
    "overseer" to listOf("کدام شرکت از پروتکل‌ها عقب است؟", "چه چیزی را نگه داشته‌ای و چرا؟"),
    "assistant" to listOf("برای فردا یک یادآوری بگذار", "خبرهای مهم امروز بازار را بگو"),
    "advisor" to listOf("امروز اول به کدام تصمیم برسم؟", "بزرگ‌ترین ریسک هلدینگ الان چیست؟"),
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TalkScreen(ref0: String? = null, persona0: String = "secretary") {
    val env = LocalEnv.current
    val nav = LocalNav.current
    val toasts = LocalToasts.current
    val act = activity()
    val c = Divan.colors
    val scope = rememberCoroutineScope()
    val has = served(HubFeature.TALK)
    val session = remember(env) { TalkSession(env, scope, toasts) }
    DisposableEffect(session) { onDispose { session.release() } }

    val engines = rememberQuery("voice-engines", "voice", maxAgeMs = 30_000) { voiceEngines() }
    val meter = rememberQuery("voice-meter:month", "voice", maxAgeMs = 10_000) { voiceMeter("month") }
    val settings = rememberQuery("owner-settings", "settings") { ownerSettings() }
    val personasQ = rememberQuery("talk-personas", "talk", maxAgeMs = 30_000) { talkPersonas() }

    // The hub's personas, then the conversation: the one asked for, else the persona's newest (or a new one).
    LaunchedEffect(env, ref0, persona0) {
        val ps = try { env.api.gated(HubFeature.TALK) { talkPersonas() } } catch (_: ApiException) { emptyList() } ?: return@LaunchedEffect
        session.personas = ps
        if (ref0 != null) session.open(ref0) else session.openPersona(persona0)
    }
    LaunchedEffect(personasQ.data) { personasQ.data?.let { session.personas = it } }

    // The stream: a light changed, the meter moved, a turn or card changed elsewhere.
    LaunchedEffect(env) {
        env.stream.events.collect { e ->
            when {
                e.type == "voice.engine" -> {
                    val key = e.data["engine"]?.jsonPrimitive?.contentOrNull ?: e.ref ?: return@collect
                    val state = e.data["state"]?.jsonPrimitive?.contentOrNull ?: return@collect
                    session.engineLight(key, state, e.data["reason_fa"]?.jsonPrimitive?.contentOrNull)
                }
                e.type == "voice.meter" -> runCatching { Api.json.decodeFromJsonElement(VoiceMeter.serializer(), e.data) }.getOrNull()?.let(session::meterFromStream)
                e.type.startsWith("talk.") && !session.busy -> session.reload()
            }
        }
    }

    var sheet by rememberSaveable { mutableStateOf(TalkSheetKind.NONE) }
    // A key caught in the composer: held here for the sheet only (never saved with the screen).
    var caught by remember { mutableStateOf("") }
    var engineOpen by remember { mutableStateOf<VoiceEngine?>(null) }
    var menu by remember { mutableStateOf(false) }
    var ending by remember { mutableStateOf(false) }

    val engineList = engines.data.orEmpty()
    val patterns = com.coinepro.hq.core.data.keyPatterns(engineList)
    val hf = rememberHandsFree(session, { patterns }) { k -> caught = k; sheet = TalkSheetKind.KEY }
    val conv = session.conv
    val present = session.presentIds
    val faces = faceOrder(session.personas, present)
    val inUse = enginesInUse(session.personas, present).ifEmpty { session.personas.firstOrNull { it.key == "secretary" }?.voice?.engine?.let(::listOf).orEmpty() }
    val live = meterOf(session.meterLive, meter.data)
    val today = remember { LocalDate.ofInstant(com.coinepro.hq.core.format.HqClock.now(), ZoneId.of("Asia/Tehran")) }
    val warning = priceWarning(engineList, inUse, today)

    suspend fun runCard(card: TalkCard, payload: JsonObject?) {
        env.api.runTalkCard(card.idText, payload) { a, t -> env.auth.stepUp(act, a, t) }
        toasts.ok("انجام شد.")
        env.cache.invalidate("talk", "orders", "work", "decisions", "rules", "automations", "planner", "hiring", "home")
        session.reload()
    }
    suspend fun dismissCard(card: TalkCard) {
        env.api.dismissTalkCard(card.idText)
        env.cache.invalidate("talk")
        session.reload()
    }

    if (!has) {
        Box(Modifier.fillMaxSize().padding(16.dp), contentAlignment = Alignment.Center) { Empty("گفتگو با به‌روزرسانی بعدی هاب میاید", icon = DivanIcon.MESSAGES) }
        return
    }

    Column(Modifier.fillMaxSize().imePadding()) {
        // The faces, and the menu.
        Row(Modifier.fillMaxWidth().padding(top = 4.dp), verticalAlignment = Alignment.Top) {
            FacesRow(
                faces, conv?.persona, session.speaking || session.phase == Phase.WRITING,
                onPick = { p ->
                    if (p.id != conv?.persona) scope.launch { hf.stop(); session.openPersona(p.id) }
                },
                onAdd = { sheet = TalkSheetKind.INVITE }, modifier = Modifier.weight(1f),
            )
            Box {
                IconBtn(DivanIcon.MORE, "گزینه‌های گفتگو", { menu = true })
                DropdownMenu(menu, { menu = false }, containerColor = c.overlay) {
                    for ((label, icon, go) in listOf<Triple<String, DivanIcon, () -> Unit>>(
                        Triple("صورت‌جلسه کن", DivanIcon.REPORT) { scope.launch { runCatching { env.api.talkMinutes(conv?.ref ?: return@launch) }.onFailure { (it as? ApiException)?.let { e -> toasts.error(e.messageFa) } }; session.reload() } },
                        Triple("گفتگوهای قبلی", DivanIcon.MESSAGES) { nav.go("talk-list") },
                        Triple("گفتگوی تازه", DivanIcon.ADD) { scope.launch { hf.stop(); session.startNew(conv?.persona ?: "secretary") } },
                        Triple("صدای هر نقش", DivanIcon.MIC) { sheet = TalkSheetKind.VOICES },
                        Triple("خرج صدا و سقف", DivanIcon.BUDGET) { sheet = TalkSheetKind.METER },
                        Triple("کلید صدا", DivanIcon.LOCK) { caught = ""; sheet = TalkSheetKind.KEY },
                    )) {
                        DropdownMenuItem(
                            text = { Text(label, style = Divan.type.body, color = c.textPrimary) },
                            leadingIcon = { DIcon(icon, size = 20.dp, tint = c.textSecondary) },
                            onClick = { menu = false; go() },
                        )
                    }
                }
            }
        }
        // The lights, the meter.
        Row(Modifier.fillMaxWidth().padding(horizontal = 12.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            LightsRow(engineList, inUse, session.lightsLive, onTap = { engineOpen = it; sheet = TalkSheetKind.ENGINE })
            Box(Modifier.weight(1f))
            MeterChip(live, settings.data?.voice?.warnAt ?: 0.8, { sheet = TalkSheetKind.METER })
        }
        warning?.let {
            Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 4.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                DIcon(DivanIcon.INFO, size = 14.dp, tint = c.warning)
                Text(timesFig(it), style = Divan.type.micro, color = c.warning)
            }
        }
        HorizontalDivider(color = c.lineDivider, modifier = Modifier.padding(top = 4.dp))

        // The chat.
        val list = rememberLazyListState()
        val reduced = LocalReducedMotion.current
        val total = session.turns.size + (if (session.phase != Phase.IDLE || session.liveText.isNotBlank()) 1 else 0)
        LaunchedEffect(total, session.liveText.length) {
            if (total == 0) return@LaunchedEffect
            if (reduced) list.scrollToItem(total - 1) else list.animateScrollToItem(total - 1)
        }
        Box(Modifier.weight(1f)) {
            LazyColumn(Modifier.fillMaxSize(), state = list, contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                when {
                    session.loading && session.turns.isEmpty() -> items(3) { i -> Skeleton(Modifier.fillMaxWidth(if (i % 2 == 0) 0.7f else 0.5f).height(64.dp), radius = 16.dp) }
                    session.error != null && session.turns.isEmpty() -> item { ErrorBlock(session.error, { scope.launch { session.openPersona(persona0) } }) }
                    session.turns.isEmpty() && session.phase == Phase.IDLE -> item(key = "start") {
                        val who = faces.firstOrNull { it.id == conv?.persona }
                        Column(Modifier.fillMaxWidth().padding(top = 24.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(12.dp)) {
                            who?.let { PersonaFace(it, size = 72.dp, speaking = false) }
                            Text("با ${who?.let(::personaTitle) ?: "منشی هلدینگ"} حرف بزن", style = Divan.type.h3)
                            Text("بنویس، یا دکمه‌ی میکروفون را نگه دار. تا نخواهی، هیچ کاری ساخته نمیشود.", style = Divan.type.caption, color = c.textMuted)
                            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp, Alignment.CenterHorizontally), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                for (s in STARTERS[conv?.persona].orEmpty()) {
                                    Text(s, style = Divan.type.small, color = c.textSecondary, modifier = Modifier.clip(CircleShape).border(1.dp, c.lineStrong, CircleShape).clickable { scope.launch { session.send(s) } }.padding(horizontal = 12.dp, vertical = 6.dp))
                                }
                            }
                        }
                    }
                    else -> {
                        var lastBy: String? = null
                        val multi = present.size > 1
                        items(session.turns.toList(), key = { it.idText.ifBlank { "n${it.n}" } + it.n }) { t ->
                            val show = multi && !t.owner && t.by != lastBy
                            lastBy = if (t.owner) null else t.by
                            Box(itemMotion()) {
                                TalkBubble(
                                    t, faces.firstOrNull { it.id == t.by }, session.personas, show,
                                    onReplay = if (t.audio.isEmpty()) null else ({ t.audio.sortedBy { it.seq }.forEach(session::play) }),
                                    onRun = ::runCard, onDismiss = ::dismissCard,
                                )
                            }
                        }
                    }
                }
                if (session.phase != Phase.IDLE || session.liveText.isNotBlank() || session.liveFailed != null) item(key = "live") {
                    LiveBubble(session.phase, session.liveText, session.liveFailed, faces.firstOrNull { it.id == conv?.persona }, session.liveCards.toList(), session.speaking, ::runCard, ::dismissCard)
                }
                for (n in session.notices) item(key = "notice-$n") { Text(n, style = Divan.type.caption, color = c.textMuted, modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp)) }
            }
        }

        // Mode and composer.
        Column(Modifier.fillMaxWidth().padding(horizontal = 12.dp).padding(bottom = 8.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            ModeStrip(
                conv?.mode ?: "consult",
                onMode = { m -> scope.launch { session.setMode(m) } },
                onEnd = {
                    ending = true
                    scope.launch {
                        try {
                            // «پایان جلسه»: one minutes card with the summary, the decisions and the tasks; the room goes back to consult.
                            runCatching { env.api.talkMinutes(conv?.ref ?: return@launch) }.onFailure { (it as? ApiException)?.let { e -> toasts.error(e.messageFa) } }
                            session.setMode("consult")
                            session.reload()
                        } finally { ending = false }
                    }
                },
                ending = ending,
            )
            TalkComposer(session, hf, onKey = { k -> caught = k; sheet = TalkSheetKind.KEY })
        }
    }

    if (sheet != TalkSheetKind.NONE) TalkSheet(onDismiss = { sheet = TalkSheetKind.NONE; caught = "" }) {
        when (sheet) {
            TalkSheetKind.KEY -> KeyBody({ sheet = TalkSheetKind.NONE; caught = "" }, initial = caught, provider = com.coinepro.hq.core.data.providerOf(engineList, inUse.firstOrNull()), lights = session.lightsLive)
            TalkSheetKind.METER -> MeterBody()
            TalkSheetKind.VOICES -> VoicesBody(present, session.lightsLive, onPlay = { id, s -> session.playFile(id, s) })
            TalkSheetKind.INVITE -> InviteBody(onPick = { role, company, dept ->
                sheet = TalkSheetKind.NONE
                scope.launch {
                    try {
                        val ref = session.conv?.ref ?: run { session.startNew("secretary"); session.conv?.ref } ?: return@launch
                        env.api.inviteToTalk(ref, role, company, dept)
                        session.reload()
                    } catch (e: ApiException) {
                        toasts.error(e.messageFa)
                    }
                }
            })
            TalkSheetKind.ENGINE -> engineOpen?.let { e ->
                val (st, why) = lightState(e, session.lightsLive)
                val check = com.coinepro.hq.ui.rememberAction()
                EngineReasonBody(e, st, why, onKey = { caught = ""; sheet = TalkSheetKind.KEY }, onCheck = {
                    check.run { env.api.checkVoiceEngine(e.key); env.cache.invalidate("voice"); session.engineLight(e.key, "checking", null) }
                }, checking = check.busy)
            }
            TalkSheetKind.NONE -> Unit
        }
    }
}

/** The live meter, if the stream has spoken, else the last read. */
private fun meterOf(live: VoiceMeter?, read: VoiceMeter?): VoiceMeter? = live ?: read

@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun TalkSheet(onDismiss: () -> Unit, content: @Composable () -> Unit) {
    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true), containerColor = Divan.colors.overlay) {
        Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).imePadding().padding(horizontal = 16.dp).padding(bottom = 24.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) { content() }
    }
}
