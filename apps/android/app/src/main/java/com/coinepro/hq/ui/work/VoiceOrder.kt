package com.coinepro.hq.ui.work

import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
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
import androidx.compose.ui.draw.scale
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.PlayerOption
import com.coinepro.hq.core.data.applyPlayer
import com.coinepro.hq.core.data.recogniseOption
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.media.HUB_TRANSCRIBING
import com.coinepro.hq.core.media.clock
import com.coinepro.hq.core.net.Order
import com.coinepro.hq.core.net.OrderRoute
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.CompanyMark
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.RichText
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.media.VoiceProblem
import com.coinepro.hq.ui.media.VoiceResult
import com.coinepro.hq.ui.media.openAppSettings
import com.coinepro.hq.ui.media.Waveform
import com.coinepro.hq.ui.media.rememberVoiceInput
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.OrderRoute29
import com.coinepro.hq.core.net.OwnerRule
import com.coinepro.hq.core.net.orderWithPace
import com.coinepro.hq.designsystem.SegOption
import com.coinepro.hq.designsystem.Segmented
import com.coinepro.hq.ui.v29.Listening
import com.coinepro.hq.ui.v29.ListeningPanel
import com.coinepro.hq.ui.v29.OrderStatePill
import com.coinepro.hq.ui.v29.PreviewLine
import com.coinepro.hq.ui.v29.RouteEditor
import com.coinepro.hq.ui.v29.RuleCard
import com.coinepro.hq.ui.v29.listening
import com.coinepro.hq.ui.v29.rememberLongVoice
import com.coinepro.hq.ui.v29.rememberPreview
import com.coinepro.hq.ui.v29.served

private val KIND = mapOf(
    "work" to ("کار" to DivanIcon.TASK),
    "code" to ("کارگاه کد" to DivanIcon.CODE),
    "meeting" to ("جلسه" to DivanIcon.MEETING),
    "question" to ("پرسش" to DivanIcon.ADVISOR),
)

private fun routeOf(r: OrderRoute): String? = when {
    r.sessionRef != null -> "workshop/${r.sessionRef}"
    r.decisionRef != null -> "cartable/${r.decisionRef}"
    r.workRef != null -> "work/${r.workRef}"
    r.kind == "question" -> "advisor"
    else -> null
}

/** Where an order went: company, kind, who — and a way in. */
@Composable
private fun RouteChip(r: OrderRoute, onGo: (String) -> Unit) {
    val c = Divan.colors
    val employees = rememberQuery("employees:all", "employees", maxAgeMs = 60_000) { employees().items }
    val who = employees.data?.firstOrNull { it.code == r.to }?.titleFa ?: r.to
    val (fa, icon) = KIND[r.kind] ?: (r.kind to DivanIcon.TASK)
    val route = routeOf(r)
    Row(
        Modifier.clip(CircleShape).background(c.tile).then(if (route != null) Modifier.clickable(role = Role.Button) { onGo(route) } else Modifier).padding(horizontal = 10.dp, vertical = 5.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(5.dp),
    ) {
        CompanyMark(r.company, height = 12.dp, mono = true, ink = c.textSecondary)
        DIcon(icon, size = 14.dp, tint = c.textSecondary)
        Text("$fa ← $who", style = Divan.type.micro, color = c.textPrimary, maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}

/**
 * The owner speaks an order; the hub routes it (contract §17.4): rules first, then the light model, then the advisor.
 * The phone's own recogniser (fa-IR) turns the voice into words as the owner speaks; the owner reads the exact text before it goes,
 * and sees where it went. [listen] starts listening as the sheet opens (the gold button, the microphone, the quick-settings tile);
 * [typed] opens it on the text (a long press on the gold button). ⟨1.9⟩ §27: the words name who plays it («با جمنای», «شورا»): the
 * choice is shown and the owner can change it before it goes; when the phone cannot hear, the hub turns the recording into words.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun VoiceOrderSheet(onDismiss: () -> Unit, listen: Boolean = true, typed: Boolean = false) {
    ModalBottomSheet(onDismissRequest = onDismiss, sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true), containerColor = Divan.colors.overlay) {
        Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).imePadding().padding(horizontal = 16.dp).padding(bottom = 24.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            VoiceOrderBody(onDismiss, listen, typed)
        }
    }
}

/** The voice order's content. [text0] and [voice0] open it on words already heard; [hubTranscribing0] shows the hub turning a
 *  recording into words (the screenshots: the moments a test cannot speak into). ⟨1.11⟩ [rule0] opens it on «قانون تازه برای هلدینگ»,
 *  [preview0] with the secretary's route, [proposed0] on a rule just written, [listening0] on the long voice listening. */
@Composable
fun VoiceOrderBody(
    onDismiss: () -> Unit,
    listen: Boolean = true,
    typed: Boolean = false,
    text0: String = "",
    voice0: VoiceResult? = null,
    hubTranscribing0: Boolean = false,
    rule0: Boolean = false,
    preview0: OrderRoute29? = null,
    proposed0: OwnerRule? = null,
    listening0: Listening? = null,
) {
    val env = LocalEnv.current
    val nav = LocalNav.current
    val ctx = androidx.compose.ui.platform.LocalContext.current
    val c = Divan.colors
    val orders = rememberQuery("voice-orders", "orders", maxAgeMs = 10_000) { orders().items }
    val action = rememberAction()
    // ⟨1.11⟩ §29.3 the owner's rule, beside the order (when this hub has rules).
    val rulesOn = served(HubFeature.RULES)
    val sessionsOn = served(HubFeature.SESSIONS)
    var mode by rememberSaveable { mutableStateOf(if (rule0) "rule" else "order") }
    val rule = mode == "rule" && rulesOn
    var phase by rememberSaveable { mutableStateOf(if (proposed0 != null) "sent" else if (typed || text0.isNotBlank()) "review" else "ready") }
    var text by rememberSaveable { mutableStateOf(text0) }
    var voice by remember { mutableStateOf(voice0) }
    var out by remember { mutableStateOf<Order?>(null) }
    var proposed by remember { mutableStateOf(proposed0) }
    var sentWith by remember { mutableStateOf(PlayerOption.AUTO) }
    // ⟨1.9⟩ §27.1: who plays it. Read from the words until the owner picks a chip; the owner's pick stays.
    var player by rememberSaveable { mutableStateOf("auto") }
    var picked by rememberSaveable { mutableStateOf(false) }
    // ⟨2026-11-09⟩ «با من یا خودکار؟» before the order goes (every order is a session); nothing is chosen for the owner
    var pace by rememberSaveable { mutableStateOf<String?>(null) }
    var editing by remember { mutableStateOf(false) }
    val heard = remember(text) { recogniseOption(text) }
    LaunchedEffect(heard) { if (!picked) player = heard?.option?.key ?: "auto" }
    val option = PlayerOption.entries.firstOrNull { it.key == player } ?: PlayerOption.AUTO
    // ⟨1.11⟩ §29.5 the long voice: the phone's recogniser restarting at each pause, then the hub in chunks past a minute.
    val vh = rememberLongVoice(if (rule) "rule" else "order") { r -> text = if (text.isBlank()) r.text else "${text.trimEnd()} ${r.text}"; voice = r; phase = "review" }
    val v = vh.v
    val source = if (voice != null) "voice" else "text"
    // ⟨1.11⟩ §29.4 the secretary's one line, once the words are there.
    val preview = rememberPreview(text, source, on = phase == "review" && !rule && !v.active, preview0 = preview0)
    val hubBusy = hubTranscribing0 || (v.transcribing && v.engine == "hub")
    val hearing = listening0 ?: if (v.recording) v.listening() else null
    val go = { route: String -> v.cancel(); onDismiss(); nav.go(route) }
    // The record button breathes while it listens (in the layer: no recomposition; still when animations are removed).
    val pulse = com.coinepro.hq.designsystem.rememberBreath(hearing != null, periodMs = 1400)
    // Opened to speak: listening starts at once (after the microphone permission, the first time).
    LaunchedEffect(Unit) { if (listen && !typed && text0.isBlank() && listening0 == null) vh.start() }

    Text(if (rule) "قانون تازه برای هلدینگ" else if (phase == "review" && voice == null) "فرمان تازه" else "فرمان صوتی", style = Divan.type.h2)
    if (rulesOn && phase != "sent") Segmented(
        listOf(SegOption("order", "فرمان", DivanIcon.MIC), SegOption("rule", "قانون تازه برای هلدینگ", DivanIcon.SEAL)),
        mode, { m -> if (!v.active) { mode = m; out = null; proposed = null } }, Modifier.fillMaxWidth(),
    )
    Text(
        if (rule) "بگو یا بنویس چه چیزی همیشه باید رعایت شود. هاب آن را یک جمله‌ی روشن میکند، میگوید برای چه کسانی است و تو با یک ضربه مُهرش میکنی."
        else "بگو یا بنویس چه میخواهی؛ منشی هلدینگ میگوید کجا میرود و چه بیرون میاید، و تو پیش از فرستادن میبینی.",
        style = Divan.type.caption, color = c.textMuted,
    )
    when (phase) {
        "ready" -> Column(Modifier.fillMaxWidth().padding(vertical = 8.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Box(
                Modifier.size(112.dp).graphicsLayer { val k = 1f + 0.12f * pulse.value; scaleX = k; scaleY = k }.clip(CircleShape).background(c.goldFill)
                    .clickable(enabled = !v.transcribing && !hubBusy, role = Role.Button) { if (v.recording) v.finish() else vh.start() }
                    .semantics { contentDescription = if (hearing != null) "تمام؛ به متن تبدیل کن" else "شروع گفتن" },
                contentAlignment = Alignment.Center,
            ) {
                if (v.transcribing || hubBusy) CircularProgressIndicator(Modifier.size(36.dp), color = c.onGold, strokeWidth = 3.dp)
                else DIcon(if (hearing != null) DivanIcon.STOP else DivanIcon.MIC, size = 44.dp, tint = c.onGold)
            }
            when {
                hearing != null -> ListeningPanel(hearing, v::finish, v::cancel)
                hubBusy -> {
                    Text(HUB_TRANSCRIBING, style = Divan.type.bodyStrong, color = c.goldInk)
                    if (v.chunks > 0) Text("${v.sent} از ${v.chunks} بخش رسید؛ متن کامل را هاب برمیگرداند.", style = Divan.type.caption, color = c.textSecondary, textAlign = TextAlign.Center)
                    else Text("صدای ضبط‌شده روی خود هاب به متن میشود و از هاب بیرون نمیرود. متن را پیش از فرستادن میخوانی.", style = Divan.type.small, color = c.textSecondary, textAlign = TextAlign.Center)
                }
                v.transcribing -> {
                    Text("در حال تشخیص گفتار…", style = Divan.type.body, color = c.textSecondary)
                    if (v.partial.isNotBlank()) Text(v.partial, style = Divan.type.body, color = c.textPrimary, textAlign = TextAlign.Center)
                }
                v.unavailable != null -> {
                    VoiceProblem(v.unavailable.orEmpty(), v.settings, { openAppSettings(ctx) }, { v.dismiss(); phase = "review" })
                    HqButton("مینویسم", { v.dismiss(); phase = "review" }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, icon = DivanIcon.EDIT)
                }
                else -> {
                    Text("بزن و بگو، هر قدر که لازم است؛ تمام که شد دوباره بزن", style = Divan.type.bodyStrong, textAlign = TextAlign.Center)
                    Text(
                        if (rule) "مثلاً «هیچ پستی بدون منبع برای عددهایش منتشر نشود». هاب آن را دقیق میکند و میگوید برای کدام نقش‌ها و شرکت‌هاست."
                        else "مثلاً «برای تریدیار سه ریلز درباره‌ی سیگنال طلا بساز و در اینستاگرام منتشر کن». منشی شرکت، دپارتمان، خروجی و بودجه را پیشنهاد میدهد. «با جی‌پی‌تی»، «با جمنای»، «با دیپ‌سیک» یا «شورا» بازیکنش را تعیین میکند.",
                        style = Divan.type.small, color = c.textSecondary, textAlign = TextAlign.Center,
                    )
                    Text("به‌جایش مینویسم", Modifier.clickable { phase = "review" }.padding(6.dp), style = Divan.type.small, color = c.goldInk)
                }
            }
        }
        "review" -> Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text(if (voice != null) "متن آنچه گفتی؛ پیش از فرستادن بخوان و اگر لازم است اصلاح کن" else if (rule) "قانون" else "فرمان", style = Divan.type.caption, color = c.textMuted)
            HqTextField(text, { text = it }, if (rule) "چه چیزی همیشه رعایت شود؟" else "چه کاری؟", Modifier.fillMaxWidth(), singleLine = false, minLines = 5, maxLength = 10000)
            if (v.recording || v.transcribing) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                if (v.recording) Waveform(v.levels.takeLast(16), Modifier.height(20.dp)) else CircularProgressIndicator(Modifier.size(14.dp), color = c.goldInk, strokeWidth = 2.dp)
                Text(v.partial.ifBlank { if (v.recording) "میشنوم…" else if (v.engine == "hub") HUB_TRANSCRIBING else "در حال تشخیص گفتار…" }, style = Divan.type.caption, color = c.textSecondary, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
                if (v.recording) HqButton("تمام", v::finish, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.STOP)
            }
            v.fellBack?.takeIf { v.recording }?.let { FellBack(it) }
            v.unavailable?.let { why -> VoiceProblem(why, v.settings, { openAppSettings(ctx) }, v::dismiss) }
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                voice?.let { r ->
                    DIcon(DivanIcon.MIC, size = 14.dp, tint = c.textSecondary)
                    Text(if (r.engine == "hub") "متن هاب از صدای تو" else "از گفتار، با تشخیص خود گوشی", style = Divan.type.micro, color = c.textSecondary)
                    Fig(clock(r.seconds), style = Divan.type.figureSmall, color = c.textSecondary)
                }
                Box(Modifier.weight(1f))
                if (!v.active) HqButton(if (text.isBlank()) "بگو" else "ادامه بده", { vh.start() }, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.MIC)
            }
            if (rule) HqButton(
                "ثبت قانون", {
                    action.run {
                        proposed = env.api.newRule(text.trim(), source, voice?.fileId)
                        phase = "sent"
                        env.cache.invalidate("rules", "oversight")
                    }
                },
                Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, size = BtnSize.LG, icon = DivanIcon.SEAL, enabled = text.trim().length >= 3 && !v.active, loading = action.busy,
            ) else {
                PreviewLine(preview, onEdit = { editing = true })
                PlayerPicker(option, { picked = true; player = it.key }, Modifier.fillMaxWidth(), heard = heard)
                if (text.trim().length >= 3) com.coinepro.hq.ui.session.PaceAsk(pace, { pace = it })
                HqButton(
                    "بفرست", {
                        val chosen = pace ?: return@HqButton
                        action.run {
                            // §29.4: the secretary's route (the owner's edit kept; his player chip wins) is followed exactly.
                            val route = preview.route?.let { r -> if (picked) r.copy(player = option.player, mode = option.mode) else r }
                            out = env.api.orderWithPace(text.trim(), source, voice?.fileId, route, chosen)
                            // ⟨1.9⟩ §27.1: the hub reads the player from the words; the owner's own choice is set on the works it made.
                            out?.let { env.api.applyPlayer(it, option) }
                            sentWith = option
                            phase = "sent"
                            env.cache.invalidate("orders", "work", "planner", "workshop", "decisions", "inbox", "home", "sessions", "office")
                            // ⟨1.17⟩ §35.1 every order is a session: it opens at once, and its holder speaks first there.
                            if (sessionsOn) out?.let { o -> go("session/${o.ref}") }
                        }
                    },
                    Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, size = BtnSize.LG, icon = DivanIcon.SEND, enabled = text.trim().length >= 3 && !v.active && pace != null, loading = action.busy,
                )
            }
        }
        else -> if (rule || proposed != null) {
            proposed?.let { p -> RuleCard(p, onChanged = { proposed = it }) }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                HqButton("قانون بعدی", { phase = "ready"; text = ""; voice = null; proposed = null; vh.start() }, Modifier.weight(1f), icon = DivanIcon.MIC)
                HqButton("همه‌ی قانون‌ها", { go("rules") }, Modifier.weight(1f), variant = BtnVariant.GHOST, icon = DivanIcon.NEXT)
            }
        } else out?.let { o ->
            Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(c.tile).padding(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    DIcon(DivanIcon.SEAL, size = 20.dp, tint = c.goldInk, active = true)
                    Text("فرمان رسید؛ گزارشش را همین‌جا دنبال کن", style = Divan.type.bodyStrong, color = c.textPrimary)
                }
                RichText(o.summaryFa, style = Divan.type.small)
                PlayerTag(sentWith.player, sentWith.mode)
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) { for (r in o.routes) RouteChip(r, go) }
                if (served(HubFeature.ORDER_REPORT)) HqButton("جلسه‌ی فرمان", { go("session/${o.ref}") }, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.MEETING)
            }
            HqButton("فرمان بعدی", { phase = "ready"; text = ""; voice = null; out = null; picked = false; pace = null; preview.route = null; preview.edited = false; vh.start() }, Modifier.fillMaxWidth(), icon = DivanIcon.MIC)
        }
    }
    if (!rule) {
        HorizontalDivider(color = c.lineDivider)
        Text("فرمان‌های اخیر", style = Divan.type.caption, color = c.textMuted)
        val list = orders.data
        when {
            list == null -> Skeleton(Modifier.fillMaxWidth().height(72.dp), radius = 12.dp)
            list.isEmpty() -> Text("هنوز فرمانی نداده‌ای.", style = Divan.type.caption, color = c.textMuted)
            else -> for (o in list.take(5)) {
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Row(verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        DIcon(if (o.source == "voice") DivanIcon.MIC else DivanIcon.EDIT, size = 14.dp, tint = c.textMuted, modifier = Modifier.padding(top = 3.dp))
                        RichText(o.text, Modifier.weight(1f), style = Divan.type.small, color = c.textPrimary, maxLines = 2)
                        o.state?.let { OrderStatePill(it) } ?: Text(ago(o.createdAt), style = Divan.type.micro, color = c.textMuted)
                    }
                    FlowRow(Modifier.padding(start = 22.dp), horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) { for (r in o.routes) RouteChip(r, go) }
                }
            }
        }
    }
    if (editing) preview.route?.let { r -> RouteEditor(r, onDone = { preview.route = it; preview.edited = true; editing = false }, onCancel = { editing = false }) }
}

/** ⟨1.9⟩ §27.3: the phone's recogniser failed and the hub is listening instead. */
@Composable
private fun FellBack(text: String) {
    val c = Divan.colors
    Row(
        Modifier.clip(RoundedCornerShape(10.dp)).background(c.softWarning).padding(horizontal = 10.dp, vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        DIcon(DivanIcon.INFO, size = 14.dp, tint = c.warning)
        Text(text, style = Divan.type.micro, color = c.textPrimary)
    }
}
