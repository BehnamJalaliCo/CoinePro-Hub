package com.coinepro.hq.ui.v32

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import com.coinepro.hq.designsystem.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.PayloadField
import com.coinepro.hq.core.data.applyPayloadEdits
import com.coinepro.hq.core.data.cardInfo
import com.coinepro.hq.core.data.cardStateFa
import com.coinepro.hq.core.data.madeRoute
import com.coinepro.hq.core.data.payloadFields
import com.coinepro.hq.core.data.personaIdTitle
import com.coinepro.hq.core.format.jTime
import com.coinepro.hq.core.media.FILES_ONLY_TEXT
import com.coinepro.hq.core.net.TalkCard
import com.coinepro.hq.core.net.TalkPersona
import com.coinepro.hq.core.net.TalkTurn
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Expand
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.Md
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.designsystem.rememberOrbit
import com.coinepro.hq.designsystem.timesFig
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.v29.Para
import com.coinepro.hq.ui.v29.plain
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull

// Contract §32.2: the conversation as a chat. The owner's words on the reading start side, a persona's answer opposite with its face
// (`show_md` rendered), and the cards of §32.3 under the answer that made them: every card waits for the owner's «اجرا کن».

/** The owner's turn or a persona's answer. [persona] is the speaker's data (face, title); [onReplay] plays its sentences again. */
@Composable
fun TalkBubble(
    t: TalkTurn,
    persona: TalkPersona?,
    personas: List<TalkPersona>,
    showName: Boolean,
    onReplay: (() -> Unit)?,
    onRun: suspend (TalkCard, kotlinx.serialization.json.JsonObject?) -> Unit,
    onDismiss: suspend (TalkCard) -> Unit,
    timeAtEnd: Boolean = false,
) {
    val c = Divan.colors
    val mine = t.owner
    Row(Modifier.fillMaxWidth(), horizontalArrangement = if (mine) Arrangement.Start else Arrangement.End, verticalAlignment = Alignment.Top) {
        Column(Modifier.widthIn(max = 330.dp), horizontalAlignment = if (mine) Alignment.Start else Alignment.End, verticalArrangement = Arrangement.spacedBy(6.dp)) {
            if (!mine && showName) Text(personaIdTitle(t.by, personas), style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = c.textMuted, modifier = Modifier.padding(horizontal = 4.dp))
            val shape = if (mine) RoundedCornerShape(6.dp, 16.dp, 16.dp, 16.dp) else RoundedCornerShape(16.dp, 6.dp, 16.dp, 16.dp)
            // ⟨1.18⟩ files sent with no words carry the hub's short line only; the files speak for themselves.
            val filesOnly = mine && t.files.isNotEmpty() && t.text.trim() == FILES_ONLY_TEXT
            val words = t.shown.isNotBlank() && !filesOnly
            if (words) {
                // A long press selects (the phone's handles and «کپی»); nothing above the bubble takes the press.
                com.coinepro.hq.ui.Selectable {
                    Box(Modifier.clip(shape).background(if (mine) c.raised else c.card).padding(horizontal = 14.dp, vertical = 10.dp)) {
                        // ⟨1.22⟩ §40.3 the hub writes the owner's first word of a session opened from a playbook as Markdown (the
                        // playbook whole): it reads as the owner's text formatted, its refs hidden. Every other word of his stays plain.
                        if (mine && OWNER_MD.containsMatchIn(t.text)) Md(com.coinepro.hq.core.data.withoutRefs(t.text), color = c.textPrimary)
                        else if (mine) Text(plain(t.text), style = Divan.type.body, color = c.textPrimary) else Md(t.shown, color = c.textPrimary)
                    }
                }
            }
            // ⟨1.18⟩ §36.2 the files of the turn: pictures as thumbnails (a tap opens them), films and voice in place, every other file a
            // row with its kind and size that opens (or saves) it.
            if (t.files.isNotEmpty()) com.coinepro.hq.ui.media.MessageMedia(t.files, labelled = true)
            if (t.state == "failed" || t.state == "stopped") {
                val failed = t.state == "failed"
                Text(
                    if (failed) (t.reasonFa ?: "جواب ساخته نشد؛ دوباره بگو.") else "قطع شد",
                    style = Divan.type.micro, color = if (failed) c.negative else c.textMuted, modifier = Modifier.padding(horizontal = 4.dp),
                )
            }
            for (card in t.cards) TalkCardView(card, onRun, onDismiss)
            // ⟨0.19.0⟩ [timeAtEnd] (the session): the time at the end of every bubble, the owner's too, as on every row of its chat.
            Row(Modifier.padding(horizontal = 4.dp).then(if (timeAtEnd) Modifier.align(Alignment.End) else Modifier), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                if (mine && t.source != "typed") DIcon(DivanIcon.MIC, size = 12.dp, tint = c.textMuted)
                if (t.at.isNotBlank()) Text(timesFig(jTime(t.at)), style = Divan.type.micro, color = c.textMuted)
                // The whole turn in one tap, as plain words.
                if (words) com.coinepro.hq.ui.CopyAction(turnPlain(t))
                if (!mine && onReplay != null && t.audio.isNotEmpty()) {
                    Row(
                        Modifier.clip(CircleShape).clickable(role = Role.Button, onClickLabel = "دوباره بشنو", onClick = onReplay).padding(horizontal = 6.dp, vertical = 2.dp),
                        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(3.dp),
                    ) {
                        DIcon(DivanIcon.MIC, size = 12.dp, tint = c.silverInk)
                        Text("بشنو", style = Divan.type.micro, color = c.silverInk)
                    }
                }
            }
        }
        if (!mine && persona != null) Box(Modifier.padding(start = 8.dp, top = 2.dp)) { PersonaFace(persona, size = 30.dp) }
    }
}

/** A heading at the start of a line: an owner's turn the hub wrote as Markdown (§40.3). */
private val OWNER_MD = Regex("(?m)^#{1,3}\\s")

/** What «کپی» puts on the clipboard for a turn: the owner's words as he wrote them, a persona's answer without its markdown marks. */
fun turnPlain(t: TalkTurn): String = when {
    t.owner && OWNER_MD.containsMatchIn(t.text) -> com.coinepro.hq.core.format.plainOfMd(com.coinepro.hq.core.data.withoutRefs(t.text))
    t.owner -> t.text.trim()
    else -> com.coinepro.hq.core.format.plainOfMd(t.shown)
}

/** The answer while it is written: three quiet dots first, then the text as it comes; a failure in one plain line. */
@Composable
fun LiveBubble(phase: Phase, text: String, failed: String?, persona: TalkPersona?, cards: List<TalkCard>, speaking: Boolean, onRun: suspend (TalkCard, JsonObject?) -> Unit, onDismiss: suspend (TalkCard) -> Unit) {
    val c = Divan.colors
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End, verticalAlignment = Alignment.Top) {
        Column(Modifier.widthIn(max = 330.dp), horizontalAlignment = Alignment.End, verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Box(Modifier.clip(RoundedCornerShape(16.dp, 6.dp, 16.dp, 16.dp)).background(c.card).padding(horizontal = 14.dp, vertical = 10.dp)) {
                when {
                    failed != null -> Text(failed, style = Divan.type.small, color = c.negative)
                    text.isBlank() -> Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                        ThinkingDots()
                        Text(if (phase == Phase.THINKING) "در حال فکر…" else "…", style = Divan.type.small, color = c.textMuted)
                    }
                    else -> Md(text, color = c.textPrimary)
                }
            }
            for (card in cards) TalkCardView(card, onRun, onDismiss)
        }
        if (persona != null) Box(Modifier.padding(start = 8.dp, top = 2.dp)) { PersonaFace(persona, size = 30.dp, speaking = speaking) }
    }
}

/** Three dots that take turns to brighten (still when animations are removed). */
@Composable
fun ThinkingDots(modifier: Modifier = Modifier) {
    val c = Divan.colors
    val t = rememberOrbit(true, periodMs = 1300)
    Canvas(modifier.size(width = 28.dp, height = 10.dp)) {
        val r = 3.dp.toPx()
        for (i in 0 until 3) {
            val phase = ((t.value / 360f) + i / 3f) % 1f
            val a = 0.25f + 0.75f * (1f - phase)
            drawCircle(c.goldFill.copy(alpha = a), r, Offset(r + i * (r * 2 + 3.dp.toPx()), size.height / 2))
        }
    }
}

// ------------------------------------------------------------------ cards --
/**
 * One card (§32.3): what it offers in plain words, and three choices: «اجرا کن» runs the route it stands for (with its own seal),
 * «ویرایش» opens its fields to change before running, «نه» sets it aside. A card done shows what it made, each ref opening its page.
 */
@Composable
fun TalkCardView(card: TalkCard, onRun: suspend (TalkCard, JsonObject?) -> Unit, onDismiss: suspend (TalkCard) -> Unit, modifier: Modifier = Modifier, editing0: Boolean = false) {
    // ⟨1.22⟩ §40.2 a working group drafted from the session: drawn from the playbook itself. A `playbook` card that names none, and
    // every kind this app does not know, is drawn as any card below.
    if (card.kind == "playbook") com.coinepro.hq.core.data.playbookCardOf(card.payload)?.let { pc ->
        com.coinepro.hq.ui.playbook.PlaybookCardView(card, pc, onRun, onDismiss, modifier)
        return
    }
    val c = Divan.colors
    val nav = LocalNav.current
    val run = rememberAction()
    val no = rememberAction()
    val info = cardInfo(card.kind)
    val state = cardStateFa(card.state)
    val fields = remember(card.payload) { payloadFields(card.payload) }
    var editing by rememberSaveable(card.idText) { mutableStateOf(editing0) }
    val edits = remember(card.idText) { mutableStateMapOf<List<String>, String>() }
    Column(
        modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(c.tile).padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Pill(info.fa, com.coinepro.hq.core.format.Tone.LAPIS)
            androidx.compose.foundation.layout.Spacer(Modifier.weight(1f))
            state?.let { (fa, tone) -> Pill(fa, tone, dot = true) }
        }
        if (card.titleFa.isNotBlank()) Text(plain(card.titleFa), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
        Para(card.bodyFa, style = Divan.type.caption)
        PayloadSummary(card)
        card.reasonFa?.takeIf { card.state == "failed" }?.let { Text(plain(it), style = Divan.type.caption, color = c.negative) }
        if (card.state == "done" && card.made.isNotEmpty()) FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(4.dp), itemVerticalAlignment = Alignment.CenterVertically) {
            Text("ساخته شد", style = Divan.type.micro, color = c.textMuted)
            // ⟨1.17⟩ what it made, in one word each («فرمان»، «تصمیم»); the ref is the way in, never a word on the screen.
            for (ref in card.made) {
                val route = com.coinepro.hq.core.data.madeRouteOf(ref)
                Text(com.coinepro.hq.core.data.madeFa(ref), Modifier.clip(CircleShape).background(c.raised).clickable(enabled = route != null, role = Role.Button, onClickLabel = "باز کن") { route?.let(nav::go) }.padding(horizontal = 8.dp, vertical = 2.dp), style = Divan.type.micro, color = c.silverInk)
            }
        }
        if (card.state == "offered" || card.state == "failed") {
            Expand(editing && fields.isNotEmpty()) {
                Column(Modifier.padding(top = 2.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    var lastGroup: String? = null
                    for (f in fields) {
                        if (f.group != lastGroup && f.group != null) Text(f.group, style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = c.textMuted)
                        lastGroup = f.group
                        FieldEditor(f, edits[f.path] ?: f.value) { edits[f.path] = it }
                    }
                }
            }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                HqButton(
                    if (editing) "اجرا با این تغییرها" else if (card.state == "failed") "دوباره" else info.run,
                    { run.run { onRun(card, if (edits.isEmpty()) null else applyPayloadEdits(card.payload, edits.toMap())) } },
                    variant = BtnVariant.PRIMARY, size = BtnSize.SM, icon = DivanIcon.SEAL, loading = run.busy, modifier = Modifier.weight(1f, fill = false),
                )
                if (fields.isNotEmpty()) HqButton(if (editing) "بستن" else "ویرایش", { editing = !editing }, variant = BtnVariant.SILVER, size = BtnSize.SM, icon = DivanIcon.EDIT)
                HqButton(info.dismiss, { no.run { onDismiss(card) } }, variant = BtnVariant.TEXT, size = BtnSize.SM, loading = no.busy)
            }
        }
    }
}

@Composable
private fun FieldEditor(f: PayloadField, value: String, onChange: (String) -> Unit) {
    val c = Divan.colors
    val key = f.path.last()
    val companies = com.coinepro.hq.ui.rememberCompanies().filter { it.kind != "holding" }
    Column(verticalArrangement = Arrangement.spacedBy(3.dp)) {
        Text(f.label, style = Divan.type.micro, color = c.textMuted)
        when {
            // A company or a department is picked by its name, never typed as a code.
            key == "company" && companies.isNotEmpty() -> com.coinepro.hq.designsystem.ScrollRow {
                for (co in companies) com.coinepro.hq.designsystem.FilterChip(co.nameFa ?: co.code, value == co.code, { onChange(co.code) })
            }
            key == "department" -> com.coinepro.hq.designsystem.ScrollRow {
                for ((code, fa) in com.coinepro.hq.core.format.DEPT_FA) com.coinepro.hq.designsystem.FilterChip(fa, value == code, { onChange(code) })
            }
            else -> HqTextField(value, onChange, f.label, Modifier.fillMaxWidth(), singleLine = key !in setOf("brief", "brief_fa", "body", "body_fa", "text", "text_fa", "summary", "summary_fa"), maxLength = 2000)
        }
    }
}

/** What a card carries beyond its title, when it carries it: the minutes' decisions and tasks, a plan's lines. */
@Composable
private fun PayloadSummary(card: TalkCard) {
    val c = Divan.colors
    val p = card.payload
    val companies = com.coinepro.hq.ui.rememberCompanies()
    val decisions = (p["decisions"] as? JsonArray).orEmpty().mapNotNull { textOf(it) }
    val tasks = (p["tasks"] as? JsonArray).orEmpty().mapNotNull { it as? JsonObject }
    val summary = (p["summary_fa"] ?: p["summary"])?.let { textOf(it) }
    if (summary == null && decisions.isEmpty() && tasks.isEmpty()) return
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        summary?.let { Para(it, style = Divan.type.caption, color = c.textPrimary) }
        if (decisions.isNotEmpty()) {
            Text("تصمیم‌ها", style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = c.textMuted)
            for (d in decisions) Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("•", style = Divan.type.caption, color = c.silverInk)
                Text(plain(d), style = Divan.type.caption, color = c.textPrimary, modifier = Modifier.weight(1f))
            }
        }
        if (tasks.isNotEmpty()) {
            Text("کارها", style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = c.textMuted)
            for (t in tasks) {
                val title = (t["title_fa"] ?: t["title"])?.let { textOf(it) } ?: continue
                val meta = listOfNotNull(
                    (t["company"] as? JsonPrimitive)?.contentOrNull?.let { code -> com.coinepro.hq.ui.companyOf(companies, code).nameFa },
                    (t["department"] as? JsonPrimitive)?.contentOrNull?.let { com.coinepro.hq.core.format.DEPT_FA[it] ?: it },
                    (t["due"] ?: t["due_at"] ?: t["due_date"])?.let { textOf(it) }?.let { "تا $it" },
                ).joinToString(" · ")
                Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(c.raised).padding(horizontal = 10.dp, vertical = 6.dp)) {
                    Text(plain(title), style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, maxLines = 2, overflow = TextOverflow.Ellipsis)
                    if (meta.isNotBlank()) Text(plain(meta), style = Divan.type.micro, color = c.textMuted)
                }
            }
        }
    }
}

private fun textOf(e: kotlinx.serialization.json.JsonElement): String? = when (e) {
    is JsonPrimitive -> e.contentOrNull
    is JsonObject -> listOf("text_fa", "text", "title_fa", "title").firstNotNullOfOrNull { (e[it] as? JsonPrimitive)?.contentOrNull }
    else -> null
}
