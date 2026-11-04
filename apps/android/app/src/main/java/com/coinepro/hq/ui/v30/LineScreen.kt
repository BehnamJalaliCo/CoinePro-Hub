package com.coinepro.hq.ui.v30

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.GATE_FA
import com.coinepro.hq.core.data.SCHEDULE_PRESETS
import com.coinepro.hq.core.data.capsRaised
import com.coinepro.hq.core.data.gateFa
import com.coinepro.hq.core.data.lineBody
import com.coinepro.hq.core.data.platformFa
import com.coinepro.hq.core.data.promptVariables
import com.coinepro.hq.core.data.scheduleFa
import com.coinepro.hq.core.data.setting
import com.coinepro.hq.core.data.settingFrom
import com.coinepro.hq.core.data.settingLabelFa
import com.coinepro.hq.core.data.settingText
import com.coinepro.hq.core.data.stepHasPrompt
import com.coinepro.hq.core.data.stepKindFa
import com.coinepro.hq.core.data.stepKindIcon
import com.coinepro.hq.core.data.withSetting
import com.coinepro.hq.core.data.withVariable
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.net.Asset
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.Line
import com.coinepro.hq.core.net.LineCaps
import com.coinepro.hq.core.net.StepDef
import com.coinepro.hq.core.net.StepRun
import com.coinepro.hq.core.net.StepUp
import com.coinepro.hq.core.net.TtsVoice
import com.coinepro.hq.core.net.gated
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.Chevron
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.Expand
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.HqSwitch
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.MeterBar
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.activity
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v29.CoName
import com.coinepro.hq.ui.v29.Para
import com.coinepro.hq.ui.v29.plain
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull

// Contract §30 ⟨1.12⟩: one line, edited freely. Its header (name, schedule, on or paused, draft or auto with the good runs counted, caps),
// then its steps as cards in order: the prompt with its variables, the settings (the speaker for a voice, the cover folder, when to
// publish), a test of that step alone; the whole line dry-run; its versions and a copy for another company.

/** The line [ref]. [open0] names steps that start open (the first one otherwise). */
@Composable
fun LineScreen(ref: String, open0: Set<String>? = null) {
    val q = rememberQuery("line:$ref", "lines", maxAgeMs = 20_000) { gated(HubFeature.LINES) { line(ref) } }
    val voices = rememberQuery("tts-voices", "lines", maxAgeMs = 3_600_000) { gated(HubFeature.LINES) { ttsVoices() } }
    val r = refresher(q, voices)
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        val l = q.data
        when {
            l == null && q.error != null -> item { ErrorBlock(q.error, { q.refresh() }) }
            l == null -> item { Skeleton(Modifier.fillMaxWidth().height(260.dp), radius = 16.dp) }
            else -> item(key = "line") { LineBody(l, voices.data.orEmpty(), open0) }
        }
    }
}

private fun capText(n: Number?): String = n?.toString().orEmpty()

/** The whole editor of a line. Edits are kept here until «ذخیره» makes them a new version. */
@Composable
fun LineBody(l: Line, voices: List<TtsVoice>, open0: Set<String>? = null) {
    val env = LocalEnv.current
    val nav = LocalNav.current
    val toasts = LocalToasts.current
    val act = activity()
    val c = Divan.colors
    val save = rememberAction()
    val dry = rememberAction()
    val go = rememberAction()
    val stateAct = rememberAction()
    val modeAct = rememberAction()
    var title by rememberSaveable(l.ref, l.version) { mutableStateOf(l.titleFa) }
    var schedule by rememberSaveable(l.ref, l.version) { mutableStateOf(l.schedule.orEmpty()) }
    var steps by remember(l.ref, l.version) { mutableStateOf(l.steps) }
    var caps by remember(l.ref, l.version) { mutableStateOf(l.caps) }
    var versions by rememberSaveable { mutableStateOf(false) }
    var copy by rememberSaveable { mutableStateOf(false) }
    val tests = remember(l.ref) { mutableStateMapOf<String, StepRun>() }
    val opened = remember(l.ref) { mutableStateMapOf<String, Boolean>() }
    val covers = rememberQuery("library:${l.company}:cover_folder", "library", maxAgeMs = 60_000) { gated(HubFeature.LINES) { library(l.company, "cover_folder") } }.data.orEmpty()
    val dirty = title != l.titleFa || schedule != l.schedule.orEmpty() || steps != l.steps || caps != l.caps
    val sign: StepUp = { a, t -> env.auth.stepUp(act, a, t) }

    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        // ---- header
        PageHeader(l.titleFa, eyebrow = "خط تولید، " + platformFa(l.platform))
        HqCard(Modifier.fillMaxWidth()) {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    CoName(l.company, Modifier.weight(1f), height = 13.dp, color = c.textPrimary, bold = true)
                    LinePills(l)
                }
                if (l.channel.subject.isNotBlank()) Text(plain("کانال: " + l.channel.subject), style = Divan.type.caption, color = c.textMuted)
                Text("نام خط", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
                HqTextField(title, { title = it }, "نام خط", Modifier.fillMaxWidth(), maxLength = 120)
                ScheduleEditor(schedule) { schedule = it }
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(if (l.state == "on") "خط روشن است" else if (l.state == "paused") "خط مکث کرده" else "خط هنوز روشن نشده", style = Divan.type.small, color = c.textSecondary, modifier = Modifier.weight(1f))
                    HqButton(if (l.state == "on") "مکث" else "روشن کن", {
                        stateAct.run {
                            env.api.setLineState(l.ref, if (l.state == "on") "paused" else "on")
                            env.cache.invalidate("lines")
                            toasts.ok(if (l.state == "on") "خط مکث کرد." else "خط روشن شد.")
                        }
                    }, variant = if (l.state == "on") BtnVariant.GHOST else BtnVariant.PRIMARY, size = BtnSize.SM, icon = if (l.state == "on") DivanIcon.PAUSE else DivanIcon.RESUME, loading = stateAct.busy)
                }
            }
        }
        // ---- draft or auto
        HqCard(Modifier.fillMaxWidth()) {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(if (l.mode == "auto") "منتشر میکند، بی‌مُهر" else "هر انتشار اول با مُهر تو", style = Divan.type.bodyStrong, modifier = Modifier.weight(1f))
                    Pill("${l.goodRuns} از ${l.autoAfter} اجرای خوب", if (l.goodRuns >= l.autoAfter) Tone.POS else Tone.SILVER)
                }
                MeterBar(if (l.autoAfter > 0) l.goodRuns * 100.0 / l.autoAfter else 0.0, tone = if (l.goodRuns >= l.autoAfter) com.coinepro.hq.designsystem.BarTone.POS else com.coinepro.hq.designsystem.BarTone.GOLD)
                when {
                    l.mode == "auto" -> HqButton("برگرد به مُهر تو", {
                        modeAct.run { env.api.setLineMode(l.ref, "draft"); env.cache.invalidate("lines"); toasts.ok("از این به بعد هر انتشار اول با مُهر توست.") }
                    }, variant = BtnVariant.GHOST, size = BtnSize.SM, loading = modeAct.busy)
                    (l.offerAuto || l.goodRuns >= l.autoAfter) -> {
                        Text("${l.autoAfter} اجرا را مُهر کرده‌ای و منتشر شده؛ حالا میتوانی بگذاری خودش منتشر کند.", style = Divan.type.caption, color = c.textSecondary)
                        HqButton("خودکار کن", {
                            modeAct.run {
                                env.api.setLineMode(l.ref, "auto", sign)
                                env.cache.invalidate("lines")
                                toasts.ok("خط خودکار شد؛ از اجرای بعدی بی‌مُهر منتشر میکند.")
                            }
                        }, variant = BtnVariant.PRIMARY, icon = DivanIcon.SEAL, loading = modeAct.busy)
                    }
                    else -> Text("هر اجرای مُهرشده‌ای که منتشر شود یکی حساب میشود؛ بعد از ${l.autoAfter} اجرای خوب میتوانی خودکارش کنی.", style = Divan.type.caption, color = c.textMuted)
                }
                HorizontalDivider(color = c.lineDivider)
                CapsEditor(caps) { caps = it }
            }
        }
        // ---- steps
        SectionTitle("مرحله‌ها", note = "به ترتیب اجرا؛ هر مرحله را باز کن و عوضش کن")
        steps.forEachIndexed { i, s ->
            val open = opened[s.key] ?: (open0?.contains(s.key) ?: (i == 0))
            StepCard(
                line = l, step = s, variables = promptVariables(steps, i), voices = voices, covers = covers, open = open, dirty = dirty,
                onOpen = { opened[s.key] = !open },
                onChange = { n -> steps = steps.map { if (it.key == s.key) n else it } },
                result = tests[s.key], onTested = { tests[s.key] = it },
            )
        }
        // ---- the lessons of its published runs (⟨1.13⟩ §31.1)
        com.coinepro.hq.ui.v31.LineInsights(l.ref)
        // ---- actions
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            HqButton("ذخیره‌ی نسخه‌ی تازه", {
                save.run {
                    val raised = capsRaised(l.caps, caps)
                    env.api.putLine(l.ref, lineBody(title.trim(), schedule.trim().ifBlank { null }, steps, caps), if (raised) sign else null)
                    env.cache.invalidate("lines")
                    toasts.ok("نسخه‌ی تازه ذخیره شد.")
                }
            }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, icon = DivanIcon.SEAL, enabled = dirty && title.trim().length >= 2, loading = save.busy)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                HqButton("آزمایش کامل", {
                    dry.run { val run = env.api.runLine(l.ref, dry = true); env.cache.invalidate("lines", "line-runs"); toasts.ok("آزمایش شروع شد؛ چیزی منتشر نمیشود."); nav.go("line-runs/${run.ref}") }
                }, Modifier.weight(1f), icon = DivanIcon.RESUME, enabled = !dirty, loading = dry.busy)
                HqButton("اجرا کن", {
                    go.run { val run = env.api.runLine(l.ref); env.cache.invalidate("lines", "line-runs"); toasts.ok("اجرا شروع شد."); nav.go("line-runs/${run.ref}") }
                }, Modifier.weight(1f), icon = DivanIcon.NEXT, enabled = !dirty, loading = go.busy)
            }
            if (dirty) Text("برای آزمایش و اجرا اول نسخه‌ی تازه را ذخیره کن.", style = Divan.type.caption, color = c.textMuted)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                HqButton("اجراهای این خط", { nav.go("lines/${l.ref}/runs") }, Modifier.weight(1f), variant = BtnVariant.SILVER, size = BtnSize.SM, icon = DivanIcon.TIME)
                HqButton("نسخه‌ها", { versions = true }, Modifier.weight(1f), variant = BtnVariant.SILVER, size = BtnSize.SM, icon = DivanIcon.MEMORY)
            }
            HqButton("کپی برای شرکت دیگر", { copy = true }, Modifier.fillMaxWidth(), variant = BtnVariant.GHOST, size = BtnSize.SM, icon = DivanIcon.SHARE)
        }
    }
    if (versions) com.coinepro.hq.ui.v14.HqSheet({ versions = false }, "نسخه‌های خط", sub = "هر ذخیره یک نسخه است؛ برگشتن هم نسخه‌ی تازه میسازد.") {
        VersionsBody(l) { versions = false }
    }
    if (copy) com.coinepro.hq.ui.v14.HqSheet({ copy = false }, "کپی برای شرکت دیگر", sub = "یک پیش‌نویس تازه با همین مرحله‌ها برای آن شرکت ساخته میشود.") {
        CopyBody(l) { ref -> copy = false; nav.go("lines/$ref") }
    }
}

// ------------------------------------------------------------ header bits --
/** The schedule: ready-made choices and the rule itself (free text), with what it means in words. */
@Composable
private fun ScheduleEditor(schedule: String, onChange: (String) -> Unit) {
    val c = Divan.colors
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text("برنامه‌ی اجرا", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            FilterChip("بدون برنامه", schedule.isBlank(), { onChange("") })
            for (p in SCHEDULE_PRESETS) FilterChip(scheduleFa(p), schedule == p, { onChange(p) })
        }
        HqTextField(schedule, onChange, "FREQ=DAILY;BYHOUR=9;BYMINUTE=0", Modifier.fillMaxWidth(), figure = true, maxLength = 200)
        Text(plain(scheduleFa(schedule.ifBlank { null }) + " (به وقت تهران)"), style = Divan.type.caption, color = c.textMuted)
    }
}

/** The caps: runs a day, tokens a run, Opus builds a day. A cap that rises is signed when saved. */
@Composable
private fun CapsEditor(caps: LineCaps, onChange: (LineCaps) -> Unit) {
    val c = Divan.colors
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text("سقف‌ها", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            CapField("اجرا در روز", capText(caps.runsPerDay), Modifier.weight(1f)) { onChange(caps.copy(runsPerDay = it.toIntOrNull())) }
            CapField("واحد در اجرا", capText(caps.tokensPerRun), Modifier.weight(1f)) { onChange(caps.copy(tokensPerRun = it.toLongOrNull())) }
            CapField("ساخت قوی در روز", capText(caps.opusPerDay), Modifier.weight(1f)) { onChange(caps.copy(opusPerDay = it.toIntOrNull())) }
        }
        Text("بالا بردن سقف با مُهر توست.", style = Divan.type.micro, color = c.textMuted)
    }
}

@Composable
private fun CapField(label: String, value: String, modifier: Modifier, onChange: (String) -> Unit) {
    var t by remember(value) { mutableStateOf(value) }
    Column(modifier, verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(label, style = Divan.type.micro, color = Divan.colors.textMuted, maxLines = 1)
        HqTextField(t, { v -> val d = v.filter { it.isDigit() }; t = d; onChange(d) }, "—", Modifier.fillMaxWidth(), figure = true, maxLength = 9)
    }
}

// ------------------------------------------------------------------ steps --
/** One step: its header (icon, title, gate, switch), and opened, its prompt, its settings and its test. */
@Composable
fun StepCard(
    line: Line,
    step: StepDef,
    variables: List<String>,
    voices: List<TtsVoice>,
    covers: List<Asset>,
    open: Boolean,
    dirty: Boolean,
    onOpen: () -> Unit,
    onChange: (StepDef) -> Unit,
    result: StepRun?,
    onTested: (StepRun) -> Unit,
) {
    val env = LocalEnv.current
    val c = Divan.colors
    val test = rememberAction()
    HqCard(Modifier.fillMaxWidth().alpha(if (step.enabled) 1f else 0.6f)) {
        Row(
            Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).clickable(role = Role.Button, onClickLabel = if (open) "بستن" else "باز کردن", onClick = onOpen),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            com.coinepro.hq.ui.v29.IconTile(stepKindIcon(step.kind), c.goldInk, c.softGold)
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(plain(step.titleFa.ifBlank { stepKindFa(step.kind) }), style = Divan.type.bodyStrong, maxLines = 2)
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text(stepKindFa(step.kind), style = Divan.type.micro, color = c.textMuted)
                    Pill(gateFa(step.gate), if (step.gate == "auto") Tone.SILVER else Tone.GOLD, icon = if (step.gate == "auto") null else DivanIcon.SEAL)
                    if (step.optional) Text("اختیاری", style = Divan.type.micro, color = c.textMuted)
                }
            }
            if (step.optional) HqSwitch(step.enabled, { onChange(step.copy(enabled = it)) }, "روشن بودن مرحله")
            Chevron(open, tint = c.textMuted)
        }
        Expand(open) {
            Column(Modifier.padding(top = 14.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                // the prompt and the variables it may use
                if (stepHasPrompt(step)) {
                    val prompt = step.promptFa.orEmpty()
                    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text("متن دستور", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
                        HqTextField(prompt, { onChange(step.copy(promptFa = it)) }, "دستور این مرحله را بنویس", Modifier.fillMaxWidth(), singleLine = false, minLines = 5, maxLength = 8000)
                        if (variables.isNotEmpty()) {
                            Text("متغیرها؛ برای افزودن به متن بزن", style = Divan.type.micro, color = c.textMuted)
                            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                                for (v in variables) FilterChip("{{$v}}", false, { onChange(step.copy(promptFa = withVariable(prompt, v))) }, figure = true)
                            }
                        }
                    }
                }
                // who must seal it
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("مُهر این مرحله", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        for ((g, label) in GATE_FA) FilterChip(label, step.gate == g, { onChange(step.copy(gate = g)) })
                    }
                }
                SettingsEditor(line, step, voices, covers, onChange)
                Text(plain("تا ${step.maxAttempts} بار تلاش، هر بار تا ${step.timeoutS} ثانیه مهلت"), style = Divan.type.micro, color = c.textMuted)
                // the test of this step alone
                HqButton("آزمایش همین مرحله", {
                    test.run { onTested(env.api.testLineStep(line.ref, step.key)) }
                }, Modifier.fillMaxWidth(), variant = BtnVariant.SILVER, size = BtnSize.SM, icon = DivanIcon.RESUME, enabled = !dirty, loading = test.busy)
                if (dirty) Text("برای آزمایش اول نسخه‌ی تازه را ذخیره کن.", style = Divan.type.micro, color = c.textMuted)
                result?.let { StepTestResult(it) }
            }
        }
    }
}


/** The step's settings: the special editors of a voice, a cover and a publish, then every other key as a field. */
@Composable
private fun SettingsEditor(line: Line, step: StepDef, voices: List<TtsVoice>, covers: List<Asset>, onChange: (StepDef) -> Unit) {
    val c = Divan.colors
    val special = when (step.kind) {
        "tts" -> setOf("voice")
        "cover" -> setOf("cover_folder")
        else -> emptySet()
    }
    val generic = step.settings.entries.filter { it.key !in special }
    if (step.kind !in setOf("tts", "cover", "publish") && generic.isEmpty()) return
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("تنظیم‌ها", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
        when (step.kind) {
            "tts" -> SpeakerPicker(step.setting("voice"), voices) { onChange(step.withSetting("voice", JsonPrimitive(it))) }
            "cover" -> CoverPicker(line, step.setting("cover_folder"), covers) { onChange(step.withSetting("cover_folder", JsonPrimitive(it))) }
            "publish" -> Text(plain("کجا: " + platformFa(line.platform) + (if (line.channel.subject.isNotBlank()) "، " + line.channel.subject else "")), style = Divan.type.small, color = c.textPrimary)
        }
        for ((k, v) in generic) {
            if ((v as? JsonPrimitive)?.let { !it.isString && it.booleanOrNull != null } == true) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(settingLabelFa(k), style = Divan.type.small, color = c.textSecondary, modifier = Modifier.weight(1f))
                    HqSwitch((v as JsonPrimitive).booleanOrNull == true, { onChange(step.withSetting(k, JsonPrimitive(it))) }, settingLabelFa(k))
                }
            } else {
                var t by remember(step.key, k) { mutableStateOf(settingText(v)) }
                val multi = v is kotlinx.serialization.json.JsonObject || v is kotlinx.serialization.json.JsonArray || t.length > 60
                Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text(settingLabelFa(k), style = Divan.type.micro, color = c.textMuted)
                    HqTextField(t, { t = it; onChange(step.withSetting(k, settingFrom(it, v))) }, settingLabelFa(k), Modifier.fillMaxWidth(), singleLine = !multi, minLines = if (multi) 3 else 1, maxLength = 4000, figure = (v as? JsonPrimitive)?.isString == false)
                }
            }
        }
    }
}

/** The speaker of a voice step: the speakers the speech tool offers, and a sample to listen to when there is one. */
@Composable
private fun SpeakerPicker(speaker: String, voices: List<TtsVoice>, onPick: (String) -> Unit) {
    val c = Divan.colors
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text("گوینده", style = Divan.type.micro, color = c.textMuted)
        if (voices.isEmpty()) HqTextField(speaker, onPick, "نام گوینده", Modifier.fillMaxWidth(), maxLength = 80)
        else {
            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                for (v in voices) FilterChip(v.titleFa.ifBlank { v.name }, v.name == speaker, { onPick(v.name) })
            }
            voices.firstOrNull { it.name == speaker }?.let { v ->
                Text(plain(v.titleFa.ifBlank { v.name } + (if (v.gender.isNotBlank()) "، " + genderFa(v.gender) else "")), style = Divan.type.caption, color = c.textSecondary)
                v.sampleFile?.let { com.coinepro.hq.ui.v18.AudioPlayer(it, "نمونه‌ی صدای " + v.titleFa.ifBlank { v.name }, compact = true) }
            }
        }
    }
}

private fun genderFa(g: String): String = when (g.lowercase()) { "male", "m" -> "مرد"; "female", "f" -> "زن"; else -> g }

/** The cover folder of a cover step, from the library (the company's and the holding's). */
@Composable
private fun CoverPicker(line: Line, folder: String, covers: List<Asset>, onPick: (String) -> Unit) {
    val c = Divan.colors
    val nav = LocalNav.current
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text("پوشه‌ی کاور", style = Divan.type.micro, color = c.textMuted)
        if (covers.isEmpty()) Text("در کتابخانه هنوز پوشه‌ی کاوری نیست.", style = Divan.type.caption, color = c.textMuted)
        else FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            for (a in covers) FilterChip(a.titleFa + " (" + a.files.size + " تصویر)", a.id == folder, { onPick(a.id) })
        }
        HqButton("کتابخانه‌ی این شرکت", { nav.go("library/${line.company}") }, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.NEXT)
    }
}

// ----------------------------------------------------------------- sheets --
/** Every version of the line, newest first, each with who made it and why; the old ones can be brought back. */
@Composable
fun VersionsBody(l: Line, onDone: () -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val q = rememberQuery("line-versions:${l.ref}", "lines", maxAgeMs = 10_000) { gated(HubFeature.LINES) { lineVersions(l.ref) } }
    val action = rememberAction()
    val list = q.data
    when {
        list == null && q.error != null -> ErrorBlock(q.error, { q.refresh() })
        list == null -> Skeleton(Modifier.fillMaxWidth().height(120.dp), radius = 12.dp)
        list.isEmpty() -> Text("هنوز نسخه‌ای ثبت نشده.", style = Divan.type.caption, color = c.textMuted)
        else -> Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
            list.sortedByDescending { it.version }.forEachIndexed { i, v ->
                if (i > 0) HorizontalDivider(color = c.lineDivider)
                Row(Modifier.fillMaxWidth().padding(vertical = 10.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Text(plain("نسخه‌ی ${v.version}" + (if (v.version == l.version) " (الان)" else "")), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold))
                        Text(plain(listOfNotNull(v.at?.let { ago(it) }, v.by?.takeIf { it.isNotBlank() }).joinToString("، ")), style = Divan.type.micro, color = c.textMuted)
                        if (v.noteFa.isNotBlank()) Para(v.noteFa, style = Divan.type.caption)
                    }
                    if (v.version != l.version) HqButton("برگرد به این", {
                        action.run {
                            env.api.revertLine(l.ref, v.version)
                            env.cache.invalidate("lines")
                            toasts.ok("نسخه‌ی ${v.version} برگشت؛ نسخه‌ی تازه ساخته شد.")
                            onDone()
                        }
                    }, variant = BtnVariant.SILVER, size = BtnSize.SM, loading = action.busy)
                }
            }
        }
    }
}

/** The other companies: one tap copies the line there as a draft. */
@Composable
fun CopyBody(l: Line, onCopied: (String) -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val companies = rememberCompanies().filter { it.kind != "holding" && it.code != l.company }
    val action = rememberAction()
    if (companies.isEmpty()) Text("شرکت دیگری نیست.", style = Divan.type.caption, color = c.textMuted)
    else Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
        companies.forEachIndexed { i, co ->
            if (i > 0) HorizontalDivider(color = c.lineDivider)
            Row(
                Modifier.fillMaxWidth().clickable(role = Role.Button, enabled = !action.busy) {
                    action.run {
                        val made = env.api.copyLine(l.ref, co.code)
                        env.cache.invalidate("lines")
                        toasts.ok("پیش‌نویس برای ${co.nameFa ?: co.code} ساخته شد؛ کانال و تنظیم‌هایش را عوض کن.")
                        onCopied(made.ref)
                    }
                }.padding(vertical = 12.dp),
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                CoName(co.code, Modifier.weight(1f), height = 13.dp, color = c.textPrimary, bold = true)
                DIcon(DivanIcon.NEXT, size = 16.dp, tint = c.textMuted)
            }
        }
    }
}
