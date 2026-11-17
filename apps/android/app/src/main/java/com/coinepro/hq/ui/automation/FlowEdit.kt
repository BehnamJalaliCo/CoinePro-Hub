package com.coinepro.hq.ui.automation

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Slider
import androidx.compose.material3.SliderDefaults
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
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.FlowDraft
import com.coinepro.hq.core.data.J_WEEK_FA
import com.coinepro.hq.core.data.checkDraft
import com.coinepro.hq.core.data.clockOf
import com.coinepro.hq.core.data.draftChanges
import com.coinepro.hq.core.data.faNum
import com.coinepro.hq.core.data.faText
import com.coinepro.hq.core.data.flowDraftOf
import com.coinepro.hq.core.data.flowEffortFa
import com.coinepro.hq.core.data.modelShort
import com.coinepro.hq.core.data.patchBody
import com.coinepro.hq.core.data.triggerLineFa
import com.coinepro.hq.core.data.usdShort
import com.coinepro.hq.core.data.weekOfRound
import com.coinepro.hq.core.format.HqClock
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.FlowDef
import com.coinepro.hq.core.net.FlowOptions
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.DecisionBar
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.HqSwitch
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.IconBtn
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.SpringSheet
import com.coinepro.hq.designsystem.Text
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.v29.plain
import java.time.ZoneId

// ⟨1.39⟩ Contract §61.3–§61.4 and D6 «تنظیمات»: every field the owner may change, checked as the hub checks it (each wrong one said
// under itself), then «چه عوض میشود» before the save: the save is a new version, and the earlier one stays to go back to.

private const val HOUR_KEY = "hour"

@Composable
private fun Section(title: String, note: String? = null, tag: String? = null, content: @Composable () -> Unit) {
    val c = Divan.colors
    HqCard(Modifier.fillMaxWidth().then(if (tag != null) Modifier.testTag(tag) else Modifier)) {
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(title, style = Divan.type.bodyStrong, modifier = Modifier.weight(1f).semantics { heading() })
                note?.let { Text(plain(it), style = Divan.type.micro, color = c.textMuted) }
            }
            content()
        }
    }
}

/** An hour as a chip; [changed] rings it gold, [bad] red. */
@Composable
private fun HourChip(hm: String?, changed: Boolean, bad: Boolean = false, label: String? = null, onClick: () -> Unit) {
    val c = Divan.colors
    val shape = RoundedCornerShape(12.dp)
    Box(
        Modifier.height(40.dp).clip(shape).background(if (changed) c.softGold else c.tile)
            .border(if (changed || bad) 1.5.dp else 1.dp, if (bad) c.negative else if (changed) c.goldFill else c.lineHairline, shape)
            .clickable(role = Role.Button, onClickLabel = label ?: "ساعت") { onClick() }.padding(horizontal = 14.dp),
        contentAlignment = Alignment.Center,
    ) { Text(hm?.let(::faText) ?: "پربازدیدترین", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = if (bad) c.negative else if (changed) c.goldInk else c.textPrimary) }
}

@Composable
private fun ErrorLine(e: String?) {
    if (e != null) Text(plain(e), style = Divan.type.micro, color = Divan.colors.negative)
}

/** The editor. [draft] and [setDraft] are the page's (its save bar reads them); [errors] the hub's or the editor's own, by field. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun FlowEditorBody(f: FlowDef, o: FlowOptions, draft: FlowDraft, setDraft: (FlowDraft) -> Unit, errors: Map<String, String>) {
    val c = Divan.colors
    val base = remember(f.ref, f.version) { flowDraftOf(f) }
    var picking by rememberSaveable { mutableStateOf<String?>(null) }
    val stories = f.kind == "stories"
    val today = HqClock.now().atZone(ZoneId.of(com.coinepro.hq.core.format.OWNER_TZ)).toLocalDate()
    Column(Modifier.testTag("flow-editor"), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        if (!stories) Section("ساعت انتشار", note = if (draft.hours.size > 1) "به وقت تهران · دور ${faNum(draft.hours.size)} هفته" else "به وقت تهران", tag = "edit-hours") {
            val now = weekOfRound(f.schedule, today)
            for ((i, h) in draft.hours.withIndex()) Column {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.padding(vertical = 4.dp)) {
                    Column(Modifier.weight(1f)) {
                        Text(if (draft.hours.size > 1) "هفته‌ی ${faNum(i + 1)}" + if (i == now) " · این هفته" else "" else "هر روز", style = Divan.type.small)
                        if (h == null) Text("از بازدید هفته‌های قبل، هر هفته خودش", style = Divan.type.micro, color = c.textMuted)
                    }
                    if (h == null && i == draft.hours.lastIndex && draft.hours.size > 1) HqSwitch(true, { setDraft(draft.copy(hours = draft.hours.toMutableList().also { it[i] = "19:30" }, bestWeek = false)) }, label = "پربازدیدترین ساعت")
                    HourChip(h, changed = base.hours.getOrNull(i) != h, bad = errors["hours.$i"] != null) { picking = "$HOUR_KEY:$i" }
                }
                ErrorLine(errors["hours.$i"])
            }
            if (draft.hours.size > 1 && draft.hours.last() != null) Row(verticalAlignment = Alignment.CenterVertically) {
                Text("هفته‌ی آخر: پربازدیدترین ساعت", style = Divan.type.small, color = c.textSecondary, modifier = Modifier.weight(1f))
                HqSwitch(false, { setDraft(draft.copy(hours = draft.hours.dropLast(1) + listOf(null), bestWeek = true)) }, label = "پربازدیدترین ساعت")
            }
        }
        Section("روزهای هفته", note = if (draft.days.size >= 7) "هر روز" else "${faNum(draft.days.size)} روز", tag = "edit-days") {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                for ((i, d) in J_WEEK_FA.withIndex()) {
                    val on = i in draft.days
                    Box(
                        Modifier.size(40.dp).clip(CircleShape).background(if (on) c.goldFill else c.tile).border(1.dp, if (on) c.goldFill else c.lineStrong, CircleShape)
                            .clickable(role = Role.Checkbox, onClickLabel = d) { setDraft(draft.copy(days = if (on) draft.days - i else (draft.days + i).sorted())) },
                        contentAlignment = Alignment.Center,
                    ) { Text(d, style = Divan.type.small.copy(fontWeight = if (on) FontWeight.Bold else FontWeight.Normal), color = if (on) c.onGold else c.textSecondary) }
                }
            }
            ErrorLine(errors["days"])
        }
        Section("شروع ساخت", tag = "edit-trigger") {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("ساعت شروع", style = Divan.type.small, modifier = Modifier.weight(1f))
                HourChip(draft.triggerAt, changed = base.triggerAt != draft.triggerAt, bad = errors["trigger_at"] != null, label = "ساعت شروع ساخت") { picking = "trigger" }
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("همان روز انتشار بساز", style = Divan.type.small, color = c.textSecondary, modifier = Modifier.weight(1f))
                HqSwitch(draft.sameDay, { setDraft(draft.copy(sameDay = it)) }, label = "همان روز")
            }
            Text(plain(triggerLineFa(f.schedule.copy(triggerAt = draft.triggerAt, sameDay = draft.sameDay), (if (stories) draft.stories.minOrNull() else draft.hours.firstOrNull { it != null }))), style = Divan.type.micro, color = c.textSecondary,
                modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(10.dp))
            Text("هر ساعت انتشار باید دست‌کم ۹۰ دقیقه بعد از شروع ساخت باشد.", style = Divan.type.micro, color = c.textMuted)
            ErrorLine(errors["trigger_at"])
        }
        Section("مدل و تلاش", tag = "edit-model") {
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                for (m in o.models.ifEmpty { listOf(com.coinepro.hq.core.net.ModelOption(f.model, f.modelFa, o.efforts)) })
                    FilterChip(modelShort(m.id, m.nameFa), draft.model == m.id, { setDraft(draft.copy(model = m.id, effort = if (draft.effort in m.efforts || m.efforts.isEmpty()) draft.effort else m.efforts.last())) }, figure = true)
            }
            val efforts = o.models.firstOrNull { it.id == draft.model }?.efforts?.ifEmpty { null } ?: o.efforts
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                for (e in efforts) FilterChip(flowEffortFa(e), draft.effort == e, { setDraft(draft.copy(effort = e)) })
            }
            Text("فقط مدل‌هایی که هاب اجازه داده؛ تلاش بیشتر یعنی ساخت دقیق‌تر و گران‌تر.", style = Divan.type.micro, color = c.textMuted)
            ErrorLine(errors["model"] ?: errors["effort"])
        }
        Section("هشدار هزینه‌ی روز", tag = "edit-cap") {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(plain(estimateFa(draft.usdCap)), style = Divan.type.micro, color = c.textSecondary, modifier = Modifier.weight(1f))
                Text(plain(usdShort(draft.usdCap)), style = Divan.type.h2)
            }
            Slider(
                value = draft.usdCap.toFloat().coerceIn(o.usdCap.min.toFloat(), o.usdCap.max.toFloat()),
                onValueChange = { v -> setDraft(draft.copy(usdCap = Math.round(v).toDouble().coerceAtLeast(o.usdCap.min.toDouble()))) },
                valueRange = o.usdCap.min.toFloat()..o.usdCap.max.toFloat(),
                colors = SliderDefaults.colors(thumbColor = c.goldFill, activeTrackColor = c.goldFill, inactiveTrackColor = c.tile),
                modifier = Modifier.testTag("cap-slider"),
            )
            Text("از این مبلغ بگذرد فقط هشدار میدهد؛ ساخت هیچ‌وقت نمی‌ایستد (تصمیم مدیر کل).", style = Divan.type.micro, color = c.textMuted)
            ErrorLine(errors["usd_cap"])
        }
        Section("چرخه‌ی نوع روز", note = "هر روز یکی، به نوبت", tag = "edit-cycle") { CycleEditor(draft, o, setDraft) }
        if (stories) Section("استوری‌ها", note = "${faNum(draft.stories.size)} تا · حداکثر ${faNum(o.storiesMax)}", tag = "edit-stories") {
            DayLine(draft.stories, f.schedule.hours.filterNotNull().filter { false }, errors)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                for ((i, h) in draft.stories.withIndex()) HourChip(h, changed = base.stories.getOrNull(i) != h, bad = errors["stories.$i"] != null, label = "استوری ${faNum(i + 1)}") { picking = "story:$i" }
                if (draft.stories.size < o.storiesMax) HqButton("+ استوری", { picking = "story:new" }, variant = BtnVariant.GHOST, size = BtnSize.SM)
            }
            for ((k, v) in errors) if (k.startsWith("stories")) ErrorLine(v)
        }
        if (stories) Section("کلمه‌ی ریپلای استوری", tag = "edit-word") {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FilterChip("تازه هر روز", draft.storyWordMode == "fresh", { setDraft(draft.copy(storyWordMode = "fresh")) })
                FilterChip("همیشه یک کلمه", draft.storyWordMode == "fixed", { setDraft(draft.copy(storyWordMode = "fixed")) })
            }
            if (draft.storyWordMode == "fixed") Box(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp)) {
                HqTextField(draft.storyWord, { setDraft(draft.copy(storyWord = it)) }, "مثل «لینک»", Modifier.fillMaxWidth(), maxLength = 40)
            }
            Text("«همیشه یک کلمه» برای پیجی که جوابش همیشه همان لینک است.", style = Divan.type.micro, color = c.textMuted)
            ErrorLine(errors["story_word"])
        }
        Section("یادداشت اضافه برای سازنده", note = "${faNum(draft.noteFa.length)} از ${faNum(o.noteMax)}", tag = "edit-note") {
            Box(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp)) {
                HqTextField(draft.noteFa, { setDraft(draft.copy(noteFa = it)) }, "هر چه سازنده هر روز باید بداند", Modifier.fillMaxWidth(), singleLine = false, minLines = 3, maxLength = o.noteMax)
            }
            ErrorLine(errors["note_fa"])
        }
        HqCard(Modifier.fillMaxWidth()) {
            Row { Text("شروع دور", style = Divan.type.small, color = c.textSecondary, modifier = Modifier.weight(1f)); Text(plain(draft.start), style = Divan.type.small) }
            Row(Modifier.padding(top = 8.dp)) { Text("مکث", style = Divan.type.small, color = c.textSecondary, modifier = Modifier.weight(1f)); Text(f.pausedUntil?.let { "تا $it" } ?: "مکث نیست", style = Divan.type.small) }
        }
    }
    picking?.let { which ->
        val cur = when {
            which == "trigger" -> draft.triggerAt
            which.startsWith("$HOUR_KEY:") -> draft.hours.getOrNull(which.substringAfter(':').toInt())
            which == "story:new" -> null
            which.startsWith("story:") -> draft.stories.getOrNull(which.substringAfter(':').toInt())
            else -> null
        }
        HourSheet(cur, removable = which.startsWith("story:") && which != "story:new", onDismiss = { picking = null }, onRemove = {
            val i = which.substringAfter(':').toInt(); setDraft(draft.copy(stories = draft.stories.filterIndexed { j, _ -> j != i })); picking = null
        }) { hm ->
            setDraft(when {
                which == "trigger" -> draft.copy(triggerAt = hm)
                which.startsWith("$HOUR_KEY:") -> draft.copy(hours = draft.hours.toMutableList().also { it[which.substringAfter(':').toInt()] = hm })
                which == "story:new" -> draft.copy(stories = (draft.stories + hm))
                else -> draft.copy(stories = draft.stories.toMutableList().also { it[which.substringAfter(':').toInt()] = hm })
            })
            picking = null
        }
    }
}

/** The day's stories on a 24-hour line (00 on the right, as the owner reads); a wrong one red. */
@Composable
private fun DayLine(stories: List<String>, reels: List<String>, errors: Map<String, String>) {
    val c = Divan.colors
    BoxWithConstraints(Modifier.fillMaxWidth().height(56.dp).clip(RoundedCornerShape(14.dp)).background(c.tile).testTag("story-line")) {
        val w = maxWidth
        fun x(hm: String): androidx.compose.ui.unit.Dp { val m = hm.substring(0, 2).toInt() * 60 + hm.substring(3, 5).toInt(); return w * (m / 1440f) }
        for ((i, h) in stories.withIndex()) if (clockOf(h) != null) Box(Modifier.offset(x = x(h)).padding(top = 10.dp).width(3.dp).height(22.dp).clip(RoundedCornerShape(2.dp)).background(if (errors["stories.$i"] != null) c.negative else c.goldFill))
        for (h in reels) Box(Modifier.offset(x = x(h)).padding(top = 6.dp).width(3.dp).height(30.dp).background(c.lapis))
        for (hr in listOf(0, 6, 12, 18)) Text(faNum(hr).padStart(2, '۰'), style = Divan.type.micro, color = c.textMuted, modifier = Modifier.align(Alignment.BottomStart).offset(x = w * (hr / 24f)).padding(start = 2.dp, bottom = 2.dp))
    }
}

/** The cycle of the day's kinds: in their turn; up, down, out, and a new one. */
@Composable
private fun CycleEditor(d: FlowDraft, o: FlowOptions, setDraft: (FlowDraft) -> Unit) {
    val c = Divan.colors
    var adding by rememberSaveable { mutableStateOf("") }
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        if (d.cycle.isEmpty()) Text("هر روز همان نوع؛ برای چرخش، نوعی اضافه کن.", style = Divan.type.micro, color = c.textMuted)
        for ((i, k) in d.cycle.withIndex()) Row(
            Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(start = 12.dp, end = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text("${faNum(i + 1)} · $k", style = Divan.type.small, modifier = Modifier.weight(1f))
            if (i > 0) IconBtn(DivanIcon.NEXT, "یکی بالاتر", { setDraft(d.copy(cycle = d.cycle.toMutableList().also { l -> l[i] = l[i - 1].also { l[i - 1] = l[i] } })) }, flip = true)
            IconBtn(DivanIcon.CLOSE, "برداشتن «$k»", { setDraft(d.copy(cycle = d.cycle.filterIndexed { j, _ -> j != i })) })
        }
        if (d.cycle.size < o.cycleMax) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Box(Modifier.weight(1f).clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp)) {
                HqTextField(adding, { adding = it }, "نوع تازه، مثل «خبر و بازار»", Modifier.fillMaxWidth(), maxLength = 40)
            }
            HqButton("افزودن", { if (adding.isNotBlank()) { setDraft(d.copy(cycle = d.cycle + adding.trim())); adding = "" } }, variant = BtnVariant.SECONDARY, size = BtnSize.SM, enabled = adding.isNotBlank())
        }
    }
}

/** An hour picked in two taps (the hour, then its quarter) or typed. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun HourSheet(cur: String?, removable: Boolean, onDismiss: () -> Unit, onRemove: () -> Unit, onPick: (String) -> Unit) {
    val c = Divan.colors
    var h by rememberSaveable { mutableStateOf(cur?.take(2)?.toIntOrNull() ?: 12) }
    var m by rememberSaveable { mutableStateOf(cur?.drop(3)?.toIntOrNull() ?: 0) }
    var typed by rememberSaveable { mutableStateOf("") }
    val value = clockOf(typed) ?: "%02d:%02d".format(h, m)
    SpringSheet(onDismiss, "ساعت", sub = "به وقت تهران", bar = {
        DecisionBar("ساعت ${faText(value)}", { onPick(value) }, icon = DivanIcon.TIME)
    }) {
        Text("ساعت", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textMuted)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            for (i in 0..23) FilterChip(faText("%02d".format(i)), h == i && typed.isBlank(), { h = i; typed = "" })
        }
        Text("دقیقه", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textMuted)
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) { for (i in listOf(0, 15, 30, 45)) FilterChip(faText("%02d".format(i)), m == i && typed.isBlank(), { m = i; typed = "" }) }
        Box(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp)) {
            HqTextField(typed, { typed = it }, "یا بنویس، مثل 18:20", Modifier.fillMaxWidth(), maxLength = 5, figure = true)
        }
        if (removable) HqButton("این استوری برداشته شود", onRemove, variant = BtnVariant.DANGER, size = BtnSize.SM)
    }
}

// --------------------------------------------------------------------------------------------- the save and its sheet --
/** «n تغییر» and «ذخیره» at the page's foot; the sheet «چه عوض میشود» before the save; the hub's refusals back under their fields. */
@Composable
fun SaveBar(f: FlowDef, base: FlowDraft, draft: FlowDraft, o: FlowOptions, onErrors: (Map<String, String>) -> Unit, onSaved: (FlowDef) -> Unit) {
    val c = Divan.colors
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val act = rememberAction()
    var asking by rememberSaveable { mutableStateOf(false) }
    var note by rememberSaveable { mutableStateOf("") }
    val changes = remember(base, draft) { draftChanges(base, draft) { id -> o.models.firstOrNull { it.id == id }?.let { modelShort(it.id, it.nameFa) } ?: modelShort(id) } }
    if (changes.isEmpty()) return
    val own = remember(draft) { checkDraft(draft, f.kind, o) }
    Row(
        Modifier.fillMaxWidth().testTag("save-bar").background(c.card).border(1.dp, c.lineHairline).padding(horizontal = 16.dp, vertical = 12.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Column(Modifier.weight(1f)) {
            Text("${faNum(changes.size)} تغییر", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold))
            Text(plain(changes.first().let { "${it.labelFa}: ${it.beforeFa} ← ${it.afterFa}" }), style = Divan.type.micro, color = c.textMuted, maxLines = 1)
        }
        HqButton("ذخیره", {
            if (own.isNotEmpty()) { onErrors(own.associate { it.field to it.messageFa }); toasts.error("بعضی از تنظیم‌ها درست نیست؛ زیر هر کدام نوشته شد.") } else { onErrors(emptyMap()); asking = true }
        }, variant = BtnVariant.PRIMARY, size = BtnSize.LG)
    }
    if (asking) SpringSheet({ asking = false }, "چه عوض میشود", sub = "نسخه‌ی ${faNum(f.version + 1)}", bar = {
        DecisionBar("ذخیره", {
            act.run(onError = { e: ApiException ->
                asking = false
                if (e.fields.isNotEmpty()) onErrors(e.fields)
                toasts.error(if (e.status == 409) "در این فاصله تغییر دیگری ذخیره شد؛ صفحه دوباره خوانده شد." else e.messageFa)
            }) {
                val out = env.api.patchFlowDef(f.ref, f.version, patchBody(base, draft, note))
                asking = false; note = ""
                onSaved(out)
                toasts.ok("نسخه‌ی ${faNum(out.version)} ذخیره شد")
            }
        }, icon = DivanIcon.SEAL, state = if (act.busy) com.coinepro.hq.designsystem.DecisionState.WORKING else com.coinepro.hq.designsystem.DecisionState.IDLE)
    }) { DiffBody(f, changes, note) { note = it } }
}

/** «چه عوض میشود»: each change, before and after; when it holds; that nothing else is needed; a note; the version that stays. */
@Composable
internal fun DiffBody(f: FlowDef, changes: List<com.coinepro.hq.core.net.FlowChange>, note: String, onNote: (String) -> Unit) {
    val c = Divan.colors
        Column(Modifier.testTag("diff-sheet"), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            for (ch in changes) Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(c.tile).padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(ch.labelFa, style = Divan.type.micro, color = c.textMuted)
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(plain(ch.beforeFa), style = Divan.type.body.copy(textDecoration = androidx.compose.ui.text.style.TextDecoration.LineThrough), color = c.textMuted)
                    DIcon(DivanIcon.NEXT, size = 14.dp, tint = c.textMuted)
                    Text(plain(ch.afterFa), style = Divan.type.body.copy(fontWeight = FontWeight.Bold), color = c.goldInk)
                }
            }
            if (f.next != null) Text(plain("از کی: از دقیقه‌ی بعد؛ نوبت بعدی با همین تنظیم‌ها ساخته و منتشر میشود."), style = Divan.type.small)
            Text("کار دیگری لازم نیست: ساعت هاب از دقیقه‌ی بعد همین را میخواند.", style = Divan.type.small, color = c.textSecondary)
            Box(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp)) {
                HqTextField(note, onNote, "یادداشت این تغییر (اختیاری)", Modifier.fillMaxWidth(), maxLength = 200)
            }
            Text("نسخه‌ی ${faNum(f.version)} میماند؛ هر وقت خواستی با یک لمس به آن برمیگردی.", style = Divan.type.micro, color = c.textMuted)
        }
}
