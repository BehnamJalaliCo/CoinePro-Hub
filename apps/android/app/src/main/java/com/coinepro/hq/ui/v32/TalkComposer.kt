package com.coinepro.hq.ui.v32

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.CircularProgressIndicator
import com.coinepro.hq.designsystem.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.HANDS_FREE_FA
import com.coinepro.hq.core.data.HandsFree
import com.coinepro.hq.core.data.SOURCE_HOLD
import com.coinepro.hq.core.data.SOURCE_TYPED
import com.coinepro.hq.core.data.TALK_MODE_FA
import com.coinepro.hq.core.data.TALK_MODE_HINT_FA
import com.coinepro.hq.core.data.extractKey
import com.coinepro.hq.core.data.keyPatterns
import com.coinepro.hq.core.data.micOpen
import com.coinepro.hq.core.data.withoutKey
import com.coinepro.hq.core.media.clock
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.IconBtn
import com.coinepro.hq.designsystem.LiveDot
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.designsystem.rememberBreath
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.media.Waveform
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v29.rememberLongVoice
import kotlinx.coroutines.launch

// Contract §32.7: how the owner speaks. Typing; holding the mic (hold, speak, release); and hands-free (one tap: the app listens, a turn
// ends after a short silence, listening resumes after the answer). The 🔑 opens the secure sheet, and a key-shaped string never enters
// the composer or a turn.

/** What the held microphone is doing, for the composer to draw. */
data class HoldUi(val active: Boolean = false, val transcribing: Boolean = false, val partial: String = "", val levels: List<Float> = emptyList(), val seconds: Double = 0.0)

/** The sound-wave glyph of talk: five bars of different heights (the talk button, the hands-free switch). */
@Composable
fun WaveGlyph(size: Dp = 22.dp, tint: Color = Divan.colors.textSecondary, modifier: Modifier = Modifier) {
    Canvas(modifier.size(size)) {
        val w = this.size.width
        val h = this.size.height
        val heights = listOf(0.3f, 0.6f, 0.95f, 0.6f, 0.3f)
        val step = w / (heights.size + 0.2f)
        val stroke = (w * 0.1f).coerceAtLeast(1.5.dp.toPx())
        heights.forEachIndexed { i, k ->
            val x = step * (i + 0.6f)
            drawLine(tint, androidx.compose.ui.geometry.Offset(x, h / 2 - h * k / 2), androidx.compose.ui.geometry.Offset(x, h / 2 + h * k / 2), strokeWidth = stroke, cap = StrokeCap.Round)
        }
    }
}

/** The talk button of the app bar: apart from the gold order button, in the lapis of the conversation. */
@Composable
fun TalkButton(onClick: () -> Unit, modifier: Modifier = Modifier) {
    val c = Divan.colors
    Box(
        modifier.size(44.dp).clip(CircleShape).clickable(role = Role.Button, onClickLabel = "گفتگو با منشی و مدیرها", onClick = onClick).semantics { contentDescription = "گفتگو" },
        contentAlignment = Alignment.Center,
    ) {
        Box(Modifier.size(32.dp).clip(CircleShape).background(c.softLapis).border(1.dp, c.lapis.copy(alpha = 0.55f), CircleShape), contentAlignment = Alignment.Center) { WaveGlyph(18.dp, c.lapis) }
    }
}

/** «مشورت | جلسه‌ی کاری», and «پایان جلسه» while working. */
@Composable
fun ModeStrip(mode: String, onMode: (String) -> Unit, onEnd: () -> Unit, ending: Boolean = false, modifier: Modifier = Modifier) {
    val c = Divan.colors
    Column(modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            for (m in listOf("consult", "work")) FilterChip(TALK_MODE_FA.getValue(m), mode == m, { onMode(m) })
            androidx.compose.foundation.layout.Spacer(Modifier.weight(1f))
            if (mode == "work") HqButton("پایان جلسه", onEnd, variant = BtnVariant.SILVER, size = BtnSize.SM, icon = DivanIcon.SEAL, loading = ending)
        }
        Text(TALK_MODE_HINT_FA[mode].orEmpty(), style = Divan.type.micro, color = c.textMuted)
    }
}

/** The composer, as pure drawing: every state it can be in is given, so it can be shown in each of them. */
@Composable
fun TalkComposerView(
    text: String,
    onText: (String) -> Unit,
    hold: HoldUi,
    handsFree: HandsFree,
    hfPartial: String,
    hfLevels: List<Float>,
    sending: Boolean,
    onSend: () -> Unit,
    onKey: () -> Unit,
    onHandsFree: () -> Unit,
    onHoldStart: () -> Unit,
    onHoldEnd: () -> Unit,
    modifier: Modifier = Modifier,
    placeholder: String = COMPOSER_PLACEHOLDER,
    // ⟨1.18⟩ §36.2 files in a session: the paperclip beside the mic ([onAttach], its menu drawn by [attachMenu]), the files on their
    // way above the words ([files]); a turn may go with files and no words ([hasFiles]), once none is still uploading ([filesBusy]).
    onAttach: (() -> Unit)? = null,
    attachMenu: @Composable () -> Unit = {},
    files: (@Composable () -> Unit)? = null,
    hasFiles: Boolean = false,
    filesBusy: Boolean = false,
    // ⟨1.0.1⟩ C0.1 a page whose one full gold is elsewhere (a session with its decision bar or a knot's fix): the send is quiet.
    quietSend: Boolean = false,
    // ⟨1.0.1⟩ the owner types: where the page says so (a session), the mic is silver, held or not; it is never the page's gold.
    quietMic: Boolean = false,
    /** ⟨1.0.1⟩ asks the words' field for the keyboard («اصلاح» of a session's decision bar). */
    focus: androidx.compose.ui.focus.FocusRequester? = null,
    /** ⟨1.36⟩ §58.1 the words' field took or left the keyboard. */
    onFocus: ((Boolean) -> Unit)? = null,
) {
    val c = Divan.colors
    val ready = text.isNotBlank() || hasFiles
    val canSend = ready && !sending && !hold.active && !hold.transcribing && !filesBusy
    val hf = handsFree != HandsFree.OFF
    Column(modifier.fillMaxWidth().clip(RoundedCornerShape(18.dp)).background(c.card).border(1.dp, if (hf) c.lapis.copy(alpha = 0.6f) else c.lineStrong, RoundedCornerShape(18.dp)).padding(6.dp)) {
        files?.invoke()
        // Held: the loudness and the words so far. Hands-free: what it is doing now.
        if (hold.active || hold.transcribing) Column(Modifier.padding(horizontal = 8.dp, vertical = 4.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Row(Modifier.height(36.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                if (hold.transcribing) {
                    CircularProgressIndicator(Modifier.size(16.dp), color = c.goldInk, strokeWidth = 2.dp)
                    Text("در حال تبدیل به متن…", style = Divan.type.small, color = c.textSecondary)
                } else {
                    LiveDot(c.negative, size = 9.dp)
                    Waveform(hold.levels, Modifier.weight(1f).height(26.dp))
                    Fig(clock(hold.seconds), Modifier.width(40.dp), style = Divan.type.figureSmall, color = c.textSecondary)
                }
            }
            if (hold.partial.isNotBlank()) Text(hold.partial, style = Divan.type.small, color = c.textSecondary, maxLines = 2, overflow = TextOverflow.Ellipsis)
            else if (hold.active) Text("رها کن تا فرستاده شود.", style = Divan.type.micro, color = c.textMuted)
        } else if (hf) Column(Modifier.padding(horizontal = 8.dp, vertical = 4.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Row(Modifier.height(36.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                LiveDot(c.lapis, live = handsFree.micOpen(), size = 9.dp)
                Waveform(hfLevels, Modifier.weight(1f).height(26.dp), color = c.lapis)
            }
            Text(hfPartial.ifBlank { HANDS_FREE_FA.getValue(handsFree) }, style = Divan.type.small, color = c.textSecondary, maxLines = 2, overflow = TextOverflow.Ellipsis)
        }
        // ⟨0.17.0⟩ The words take the whole width on their own rows (up to [COMPOSER_LINES], then they scroll), never a narrow column
        // between the buttons. While the mic is held and nothing is written, the voice has the room.
        if (text.isNotEmpty() || !(hold.active || hold.transcribing)) BasicTextField(
            text, { if (it.length <= 10_000) onText(it) },
            Modifier.fillMaxWidth().heightIn(min = 40.dp).padding(horizontal = 10.dp).padding(top = 8.dp, bottom = 4.dp)
                .then(if (focus != null) Modifier.focusRequester(focus) else Modifier)
                .then(if (onFocus != null) Modifier.onFocusChanged { onFocus(it.isFocused) } else Modifier)
                .semantics { contentDescription = placeholder },
            textStyle = Divan.type.body.copy(color = c.textPrimary),
            cursorBrush = SolidColor(c.goldInk),
            maxLines = COMPOSER_LINES,
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Default),
            decorationBox = { inner -> Box { if (text.isEmpty()) Text(placeholder, style = Divan.type.small, color = c.textMuted, maxLines = 1, overflow = TextOverflow.Ellipsis); inner() } },
        )
        // The actions in one compact row under the words: the paperclip, hands-free, the key; at the end the mic, or «بفرست» once there
        // are words (with files only, both: a held turn takes the files too).
        val mic = text.isBlank() || hold.active || hold.transcribing
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(2.dp)) {
            if (onAttach != null) Box {
                IconBtn(DivanIcon.ATTACH, "پیوست فایل: عکس، فیلم، صدا، PDF، فونت، متن یا ZIP", onAttach, tint = c.textSecondary)
                attachMenu()
            }
            // Hands-free: one tap, listening until it is switched off.
            Box(
                Modifier.size(44.dp).clip(CircleShape).background(if (hf) c.softLapis else Color.Transparent)
                    .clickable(role = Role.Switch, onClickLabel = if (hf) "خاموش کردن دست‌آزاد" else "روشن کردن دست‌آزاد", onClick = onHandsFree)
                    .semantics { contentDescription = "دست‌آزاد" },
                contentAlignment = Alignment.Center,
            ) { WaveGlyph(22.dp, if (hf) c.lapis else c.textSecondary) }
            IconBtn(DivanIcon.LOCK, "کلید صدا", onKey, tint = c.textSecondary)
            androidx.compose.foundation.layout.Spacer(Modifier.weight(1f))
            if (mic) HoldMic(hold, onHoldStart, onHoldEnd, quiet = quietMic)
            if (ready) com.coinepro.hq.ui.media.RoundAction(DivanIcon.SEND, if (filesBusy) "صبر کن تا فایل‌ها برسند" else "بفرست", canSend, onSend, busy = sending, quiet = quietSend)
        }
    }
}

/** How many lines the composer grows to before its words scroll (⟨1.36⟩ §58.1: five, so the question card and the thread keep room). */
const val COMPOSER_LINES = 5

/**
 * ⟨1.36⟩ §58.1 The draft of each session's composer, kept in memory by its key while the app lives: leaving the session (the outputs, an
 * output's page, another session) and coming back finds the words where they were. A turn that went clears it.
 */
object ComposerDrafts {
    private val drafts = java.util.concurrent.ConcurrentHashMap<String, String>()
    fun get(key: String): String? = drafts[key]
    fun put(key: String, text: String) { if (text.isEmpty()) drafts.remove(key) else drafts[key] = text }
    /** Signing out, or another holding (the demo): every draft goes. */
    fun clear() = drafts.clear()
}

/** The hold-to-talk button: press, speak, release. It swells with the owner's voice while held. */
@Composable
private fun HoldMic(hold: HoldUi, onStart: () -> Unit, onEnd: () -> Unit, quiet: Boolean = false) {
    val c = Divan.colors
    val level = hold.levels.lastOrNull() ?: 0f
    val grow by animateFloatAsState(if (hold.active) 1.16f + 0.2f * level else 1f, com.coinepro.hq.designsystem.motionShort(), label = "mic")
    val breath = rememberBreath(hold.active, periodMs = 900)
    // The gesture lives across recompositions: it must call the newest handlers, not the first ones.
    val start by androidx.compose.runtime.rememberUpdatedState(onStart)
    val end by androidx.compose.runtime.rememberUpdatedState(onEnd)
    Box(
        Modifier.size(48.dp)
            .semantics { contentDescription = "نگه دار و حرف بزن"; role = Role.Button }
            .pointerInput(Unit) {
                detectTapGestures(onPress = {
                    start()
                    tryAwaitRelease()
                    end()
                })
            },
        contentAlignment = Alignment.Center,
    ) {
        Canvas(Modifier.size(48.dp)) {
            if (hold.active) drawCircle((if (quiet) c.silverInk else c.goldFill).copy(alpha = 0.14f + 0.14f * breath.value), this.size.minDimension / 2 * (0.9f + 0.1f * breath.value), style = Stroke(2.dp.toPx()))
        }
        val fill = if (quiet) (if (hold.active) c.silverInk.copy(alpha = 0.3f) else c.tile) else if (hold.active) c.goldFill else c.softGold
        Box(Modifier.size(44.dp).scale(grow).clip(CircleShape).background(fill), contentAlignment = Alignment.Center) {
            DIcon(DivanIcon.MIC, size = 22.dp, tint = if (hold.active) (if (quiet) c.textPrimary else c.onGold) else c.silverInk)
        }
    }
}

/** The composer wired to a [session]: typed, held and hands-free turns, and the key kept out of all three. ⟨1.18⟩ With [files] (a
 *  session's, §36.2) the paperclip picks through [pick], the files upload at once, and a typed or held turn takes the ones that arrived. */
@Composable
fun TalkComposer(
    session: TalkSession,
    hf: HandsFreeTalk,
    onKey: (String) -> Unit,
    modifier: Modifier = Modifier,
    files: com.coinepro.hq.ui.media.Attachments? = null,
    pick: ((String) -> Unit)? = null,
    onFilesSent: () -> Unit = {},
    /** ⟨1.0.1⟩ the words the composer opens with (an output named for «اصلاح»); [onSeeded] once they are in place. */
    seed: String? = null,
    onSeeded: () -> Unit = {},
    quietSend: Boolean = false,
    quietMic: Boolean = false,
    placeholder: String? = null,
    focus: androidx.compose.ui.focus.FocusRequester? = null,
    /** ⟨1.36⟩ §58.1 the key its draft is kept by across leaving the screen ([ComposerDrafts]); null: with the screen only. */
    draftKey: String? = null,
    /** ⟨1.36⟩ §58.1 the owner is writing (the field has the keyboard, or words): the question card folds to its first line. */
    onWriting: ((Boolean) -> Unit)? = null,
) {
    val toasts = LocalToasts.current
    val scope = rememberCoroutineScope()
    val engines = rememberQuery("voice-engines", "voice", maxAgeMs = 30_000) { voiceEngines() }
    val patterns = keyPatterns(engines.data.orEmpty())
    // The draft is saved with the screen (and by [draftKey] beyond it); a key never is (it is taken out of the text before it is stored).
    var text by rememberSaveable(session.conv?.ref) { mutableStateOf(draftKey?.let(ComposerDrafts::get).orEmpty()) }
    if (draftKey != null) androidx.compose.runtime.SideEffect { ComposerDrafts.put(draftKey, text) }
    var focused by remember { mutableStateOf(false) }
    val writing = focused || text.isNotEmpty()
    if (onWriting != null) androidx.compose.runtime.LaunchedEffect(writing) { onWriting(writing) }
    // the draft is kept per conversation, so the seed is put in again once the conversation has loaded, and only then given back
    androidx.compose.runtime.LaunchedEffect(seed, session.conv?.ref) { if (seed != null) { text = seed; if (session.conv != null) onSeeded() } }
    var sending by remember { mutableStateOf(false) }
    var menu by remember { mutableStateOf(false) }
    val mic = rememberMicPermission { toasts.info("حالا دکمه‌ی میکروفون را نگه دار و حرف بزن.") }
    var pressedAt by remember { mutableStateOf(0L) }

    fun change(next: String) {
        val k = extractKey(next, patterns)
        if (k != null) { text = withoutKey(next, k); onKey(k) } else text = next
    }

    val vh = rememberLongVoice("talk") { r ->
        val said = r.text.trim()
        val k = extractKey(said, patterns)
        // A held turn takes the files that have arrived; one still on its way waits for the next turn.
        val ready = files?.refs.orEmpty()
        if (k != null) onKey(k) else scope.launch { session.send(said, SOURCE_HOLD, ready) { files?.drop(ready); onFilesSent() } }
    }
    val v = vh.v

    fun send() {
        val body = text.trim()
        val ready = files?.refs.orEmpty()
        if ((body.isEmpty() && ready.isEmpty()) || sending || files?.uploading == true) return
        val k = extractKey(body, patterns)
        if (k != null) { text = withoutKey(body, k); onKey(k); return }
        sending = true
        scope.launch {
            val ok = try { session.send(body, SOURCE_TYPED, ready) { files?.drop(ready); onFilesSent() } } finally { sending = false }
            if (ok) text = ""
        }
    }

    TalkComposerView(
        text, ::change,
        HoldUi(v.recording, v.transcribing, v.partial, v.levels.toList(), v.elapsed),
        hf.state, hf.partial, hf.levels.toList(),
        sending, ::send,
        { onKey("") },
        { if (hf.on) hf.stop() else if (!mic.granted()) mic.ask() else { v.cancel(); hf.start() } },
        {
            if (hf.on) hf.stop()
            if (!mic.granted()) { mic.ask(); return@TalkComposerView }
            session.bargeIn()
            pressedAt = android.os.SystemClock.elapsedRealtime()
            vh.start()
        },
        {
            if (v.recording) {
                // A tap is not a held press: it only teaches how.
                if (android.os.SystemClock.elapsedRealtime() - pressedAt < 350) { v.cancel(); toasts.info("دکمه را نگه دار، حرف بزن و رها کن.") } else v.finish()
            }
        },
        modifier,
        onAttach = if (files != null && pick != null) ({ menu = true }) else null,
        attachMenu = { if (pick != null) com.coinepro.hq.ui.media.AttachMenu(menu, { menu = false }, pick, com.coinepro.hq.ui.media.SESSION_ATTACH) },
        files = files?.takeIf { it.items.isNotEmpty() }?.let { a -> { PendingFiles(a.items.toList(), onRemove = a::remove, onRetry = a::retry) } },
        hasFiles = files?.refs.orEmpty().isNotEmpty(),
        filesBusy = files?.uploading == true,
        quietSend = quietSend, quietMic = quietMic,
        placeholder = placeholder ?: COMPOSER_PLACEHOLDER, focus = focus,
        onFocus = { focused = it },
    )
}

/** What an empty composer says. */
const val COMPOSER_PLACEHOLDER = "بنویس، یا میکروفون را نگه دار…"
