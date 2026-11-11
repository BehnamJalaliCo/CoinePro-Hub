package com.coinepro.hq.ui.v32

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import com.coinepro.hq.designsystem.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.CAP_PRESETS
import com.coinepro.hq.core.data.Light
import com.coinepro.hq.core.data.METER_HONEST_FA
import com.coinepro.hq.core.data.TALK_PERIOD_FA
import com.coinepro.hq.core.data.capFraction
import com.coinepro.hq.core.data.daysToPriceChange
import com.coinepro.hq.core.data.lightFa
import com.coinepro.hq.core.data.lightFix
import com.coinepro.hq.core.data.lightOf
import com.coinepro.hq.core.data.lightState
import com.coinepro.hq.core.data.meterTone
import com.coinepro.hq.core.data.parseCap
import com.coinepro.hq.core.data.personaIdTitle
import com.coinepro.hq.core.data.priceChangeFa
import com.coinepro.hq.core.data.secondsFa
import com.coinepro.hq.core.data.usdNumber
import com.coinepro.hq.core.data.usdText
import com.coinepro.hq.core.format.HqClock
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.TalkPersona
import com.coinepro.hq.core.net.VoiceEngine
import com.coinepro.hq.core.net.VoiceMeter
import com.coinepro.hq.core.net.VoicePrice
import com.coinepro.hq.core.net.VoiceSettings
import com.coinepro.hq.designsystem.BarTone
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Expand
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.MeterBar
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.SegOption
import com.coinepro.hq.designsystem.Segmented
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.designsystem.motionEmphasised
import com.coinepro.hq.designsystem.rememberBreath
import com.coinepro.hq.designsystem.timesFig
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v29.Para
import com.coinepro.hq.ui.v29.plain
import java.time.LocalDate
import java.time.ZoneId

// Contract §32.5–32.6: the light of each voice engine and the live meter. Every number is Latin (the app's rule), the money is the
// provider's own token count times the price table, and the cap is the owner's alone.

/** Amber for an engine that reached the owner's cap (yellow is for «checking», red for a key that is missing or failing). */
val LightAmber = Color(0xFFE8873A)

@Composable
fun lightColor(l: Light): Color = when (l) {
    Light.OK -> Divan.colors.positive
    Light.CHECKING -> Divan.colors.warning
    Light.RED -> Divan.colors.negative
    Light.CAPPED -> LightAmber
}

/** The name of an engine: the hub's title, else a plain word for its key. */
fun engineTitle(key: String, engines: List<VoiceEngine>): String =
    engines.firstOrNull { it.key == key }?.titleFa?.takeIf { it.isNotBlank() } ?: when {
        key.contains("lite") -> "جمینای فلش لایت"
        key.startsWith("gemini") -> "جمینای فلش"
        key == "piper" -> "صدای ساده‌ی هاب"
        else -> "صدا"
    }

/** One dot: green, yellow (it breathes while checking), red or amber. */
@Composable
fun LightDot(state: String, size: androidx.compose.ui.unit.Dp = 10.dp, modifier: Modifier = Modifier) {
    val l = lightOf(state)
    val col = lightColor(l)
    val breath = rememberBreath(l == Light.CHECKING, periodMs = 1100, rest = 1f)
    Canvas(modifier.size(size + 6.dp)) {
        val r = size.toPx() / 2
        if (l == Light.CHECKING) drawCircle(col.copy(alpha = 0.18f + 0.25f * breath.value), r + 3.dp.toPx())
        drawCircle(col, r)
    }
}

/** One dot per engine in use. A tap says why, and what to do. */
@Composable
fun LightsRow(engines: List<VoiceEngine>, inUse: List<String>, live: Map<String, Pair<String, String?>>, onTap: (VoiceEngine) -> Unit, modifier: Modifier = Modifier) {
    Row(modifier, verticalAlignment = Alignment.CenterVertically) {
        for (k in inUse) {
            val e = engines.firstOrNull { it.key == k } ?: VoiceEngine(key = k, state = "checking")
            val (state, _) = lightState(e, live)
            Box(
                Modifier.size(32.dp).clip(CircleShape).clickable(role = Role.Button, onClickLabel = "چرا؟") { onTap(e) }
                    .semantics { contentDescription = "${engineTitle(k, engines)}: ${lightFa(state)}" },
                contentAlignment = Alignment.Center,
            ) { LightDot(state) }
        }
    }
}

/** A figure with its dollar sign, set as Latin inside the sentence. */
private fun usdSpan(b: androidx.compose.ui.text.AnnotatedString.Builder, v: Double) { b.fig(usdNumber(v)); b.append(" $") }

/**
 * The counter: «0.42 $ از 10 $ این ماه». The spent figure counts up as `voice.meter` events arrive; its colour warms at the owner's
 * warning point and turns red at the cap. Tapping opens the details.
 */
@Composable
fun MeterChip(m: VoiceMeter?, warnAt: Double, onClick: () -> Unit, modifier: Modifier = Modifier) {
    val c = Divan.colors
    val shown by animateFloatAsState((m?.voiceUsd ?: 0.0).toFloat(), motionEmphasised(), label = "meter")
    val tone = meterTone(m, warnAt)
    val ink = when (tone) { Tone.NEG -> c.negative; Tone.WARN -> c.warning; else -> c.textPrimary }
    val frac = capFraction(m)
    val text = buildAnnotatedString {
        if (m == null) append("کنتور صدا") else {
            usdSpan(this, shown.toDouble())
            if (m.capUsd != null) { append(" از "); usdSpan(this, m.capUsd) }
            append(" این ماه")
        }
    }
    Column(
        modifier.width(androidx.compose.foundation.layout.IntrinsicSize.Max).clip(RoundedCornerShape(10.dp)).background(c.tile).clickable(role = Role.Button, onClickLabel = "جزئیات خرج صدا", onClick = onClick).padding(horizontal = 10.dp, vertical = 6.dp),
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        Text(text, style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = ink, maxLines = 1)
        if (frac != null) MeterBar((frac * 100).toDouble(), Modifier.fillMaxWidth(), tone = when (tone) { Tone.NEG -> BarTone.NEG; Tone.WARN -> BarTone.WARN; else -> BarTone.SILVER }, height = 3.dp)
    }
}

// ------------------------------------------------------------ the details --
/** The meter sheet: today and this month, the projection, by voice and by persona, the cap (the owner's to edit), the prices and the honest line. */
@Composable
fun MeterBody(period0: String = "month", showPrices0: Boolean = false, editCap0: Boolean = false) {
    val c = Divan.colors
    val env = LocalEnv.current
    var period by rememberSaveable { mutableStateOf(period0) }
    val meter = rememberQuery("voice-meter:$period", "voice", maxAgeMs = 10_000) { voiceMeter(period) }
    val engines = rememberQuery("voice-engines", "voice", maxAgeMs = 30_000) { voiceEngines() }
    val personas = rememberQuery("talk-personas", "talk", maxAgeMs = 60_000) { talkPersonas() }
    val settings = rememberQuery("owner-settings", "settings") { ownerSettings() }
    val m = meter.data
    val list = engines.data.orEmpty()
    val warnAt = settings.data?.voice?.warnAt ?: 0.8
    val today = remember { LocalDate.ofInstant(HqClock.now(), ZoneId.of("Asia/Tehran")) }
    var editCap by rememberSaveable { mutableStateOf(editCap0) }
    var prices by rememberSaveable { mutableStateOf(showPrices0) }
    Text("خرج صدا", style = Divan.type.h2)
    Segmented(listOf(SegOption("today", TALK_PERIOD_FA.getValue("today")), SegOption("month", TALK_PERIOD_FA.getValue("month"))), period, { period = it }, Modifier.fillMaxWidth())
    // The big figure and the cap.
    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(c.card).padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        val tone = meterTone(m, warnAt)
        val ink = when (tone) { Tone.NEG -> c.negative; Tone.WARN -> c.warning; else -> c.textPrimary }
        Text(buildAnnotatedString { m?.let { usdSpan(this, it.voiceUsd) } ?: append("—") }, style = Divan.type.h1, color = ink)
        if (period == "month") {
            val cap = m?.capUsd
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(
                    if (cap != null) buildAnnotatedString { append("سقف این ماه: "); usdSpan(this, cap) } else buildAnnotatedString { append("سقفی نگذاشته‌ای") },
                    style = Divan.type.small, color = c.textSecondary, modifier = Modifier.weight(1f),
                )
                HqButton(if (editCap) "بستن" else if (cap == null) "سقف بگذار" else "ویرایش سقف", { editCap = !editCap }, variant = BtnVariant.SILVER, size = BtnSize.SM, icon = DivanIcon.EDIT)
            }
            capFraction(m)?.let { f -> MeterBar((f * 100).toDouble(), Modifier.fillMaxWidth(), tone = when (tone) { Tone.NEG -> BarTone.NEG; Tone.WARN -> BarTone.WARN; else -> BarTone.SILVER }) }
            Expand(editCap) { CapEditor(m?.capUsd, settings.data?.voice) { editCap = false; meter.refresh() } }
            m?.let {
                Text(buildAnnotatedString { append("با این روند تا آخر ماه حدود "); usdSpan(this, it.projectedUsd) }, style = Divan.type.small, color = c.textSecondary)
            }
        }
    }
    // A scheduled price change, said ahead (the app warns fourteen days before).
    val inUse = list.filter { it.provider != "local" }
    val note = m?.priceNoteFa?.takeIf { it.isNotBlank() } ?: inUse.firstNotNullOfOrNull { priceChangeFa(it.price) }
    val soon = inUse.any { e -> daysToPriceChange(e.price, today)?.let { it <= 14 } == true }
    if (note != null) Row(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(if (soon) c.softWarning else c.tile).padding(horizontal = 12.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        DIcon(DivanIcon.INFO, size = 16.dp, tint = if (soon) c.warning else c.textMuted)
        Text(plain(note), style = Divan.type.small, color = c.textPrimary, modifier = Modifier.weight(1f))
    }
    if (m != null) {
        if (m.byEngine.isNotEmpty()) {
            Text("به تفکیک صدا", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
            Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(c.card)) {
                m.byEngine.forEachIndexed { i, e ->
                    if (i > 0) HorizontalDivider(color = c.lineDivider)
                    Row(Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 10.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Column(Modifier.weight(1f)) {
                            Text(engineTitle(e.engine, list), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold))
                            Text(plain(secondsFa(e.seconds) + if (e.audioTokens > 0) " · ${e.audioTokens} توکن صدا" else ""), style = Divan.type.micro, color = c.textMuted)
                        }
                        Text(buildAnnotatedString { usdSpan(this, e.usd) }, style = Divan.type.small, color = c.textPrimary)
                    }
                }
            }
        }
        if (m.byPersona.isNotEmpty()) {
            Text("به تفکیک نقش", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
            Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(c.card)) {
                m.byPersona.forEachIndexed { i, p ->
                    if (i > 0) HorizontalDivider(color = c.lineDivider)
                    Row(Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 10.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Column(Modifier.weight(1f)) {
                            Text(personaIdTitle(p.persona, personas.data.orEmpty()), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold))
                            Text(plain(secondsFa(p.seconds)), style = Divan.type.micro, color = c.textMuted)
                        }
                        Text(buildAnnotatedString { usdSpan(this, p.usd) }, style = Divan.type.small, color = c.textPrimary)
                    }
                }
            }
        }
        // The brain's side: tokens of the talk turns, with the price they would have cost.
        Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(c.card).padding(14.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Column(Modifier.weight(1f)) {
                Text("توکن‌های خود گفتگو", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold))
                Text("مغز با اشتراک کار میکند و از سقف صدا کم نمیشود؛ این فقط معادل پولی آن است.", style = Divan.type.micro, color = c.textMuted)
            }
            Column(horizontalAlignment = Alignment.End) {
                Fig(String.format(java.util.Locale.US, "%,d", m.tokensTotal), style = Divan.type.figureSmall, color = c.textPrimary)
                Text(buildAnnotatedString { append("معادل "); usdSpan(this, m.talkUsdEquiv) }, style = Divan.type.micro, color = c.textMuted)
            }
        }
    } else if (meter.error != null) {
        Text("کنتور خوانده نشد؛ کمی بعد دوباره باز کن.", style = Divan.type.small, color = c.textMuted)
    }
    // The price table, which the owner can edit.
    Row(Modifier.fillMaxWidth().clickable(role = Role.Button) { prices = !prices }.padding(vertical = 4.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        Text("جزئیات و قیمت‌ها", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary, modifier = Modifier.weight(1f))
        com.coinepro.hq.designsystem.Chevron(prices, tint = c.textMuted)
    }
    Expand(prices) {
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            for (e in inUse) PriceRow(e) { env.cache.invalidate("voice"); engines.refresh(); meter.refresh() }
            Text(METER_HONEST_FA, style = Divan.type.micro, color = c.textMuted)
        }
    }
    if (!prices) Text(METER_HONEST_FA, style = Divan.type.micro, color = c.textMuted)
}

/** The owner's cap for the month: 5, 10 or 20 dollars, a number of his own, or none. Nothing else ever raises it. */
@Composable
fun CapEditor(current: Double?, settings: VoiceSettings?, onDone: () -> Unit) {
    val c = Divan.colors
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val save = rememberAction()
    var custom by rememberSaveable { mutableStateOf("") }
    var picked by rememberSaveable(current) { mutableStateOf(current) }
    val typed = parseCap(custom)
    Column(Modifier.padding(top = 4.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            for (p in CAP_PRESETS) FilterChip(usdText(p), picked == p && typed == null, { picked = p; custom = "" }, figure = true)
            FilterChip("بدون سقف", picked == null && typed == null, { picked = null; custom = "" })
        }
        HqTextField(custom, { custom = it }, "عدد دلخواه به دلار (مثلاً 15)", Modifier.fillMaxWidth(), figure = true, maxLength = 8)
        HqButton("ذخیره‌ی سقف", {
            save.run {
                val v = typed ?: picked
                val base = env.api.ownerSettings()
                val block = VoiceSettings(v, base.voice?.warnAt ?: settings?.warnAt ?: 0.8, base.voice?.chain ?: settings?.chain.orEmpty())
                env.api.saveOwnerSettings(base.version, mapOf("voice" to Api.jsonBody.encodeToJsonElement(VoiceSettings.serializer(), block)))
                env.cache.invalidate("settings", "voice")
                toasts.ok(if (v == null) "سقف برداشته شد." else "سقف این ماه ${usdText(v)} شد.")
                onDone()
            }
        }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, icon = DivanIcon.SEAL, loading = save.busy, enabled = custom.isBlank() || typed != null)
        Text("سقف را فقط تو بالا میبری. وقتی پر شود، جمله‌ی بعدی با صدای بعدیِ زنجیره گفته میشود و صدا هیچ‌وقت قطع نمیشود.", style = Divan.type.micro, color = c.textMuted)
    }
}

/** One engine's prices (per million tokens), editable by the owner. */
@Composable
private fun PriceRow(e: VoiceEngine, onSaved: () -> Unit) {
    val c = Divan.colors
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val save = rememberAction()
    var edit by rememberSaveable(e.key) { mutableStateOf(false) }
    var audio by rememberSaveable(e.key, e.price.audioOutPerM) { mutableStateOf(usdNumber(e.price.audioOutPerM)) }
    var text by rememberSaveable(e.key, e.price.textInPerM) { mutableStateOf(usdNumber(e.price.textInPerM)) }
    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(c.card).padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Column(Modifier.weight(1f)) {
                Text(e.titleFa.ifBlank { engineTitle(e.key, listOf(e)) }, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold))
                Text(
                    buildAnnotatedString { append("هر میلیون توکن صدا "); usdSpan(this, e.price.audioOutPerM); append(" · متن "); usdSpan(this, e.price.textInPerM) },
                    style = Divan.type.micro, color = c.textMuted,
                )
                priceChangeFa(e.price)?.let { Text(plain(it), style = Divan.type.micro, color = c.warning) }
            }
            HqButton(if (edit) "بستن" else "ویرایش", { edit = !edit }, variant = BtnVariant.TEXT, size = BtnSize.SM)
        }
        Expand(edit) {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                HqTextField(audio, { audio = it }, "قیمت هر میلیون توکن صدا (دلار)", Modifier.fillMaxWidth(), figure = true, maxLength = 8)
                HqTextField(text, { text = it }, "قیمت هر میلیون توکن متن (دلار)", Modifier.fillMaxWidth(), figure = true, maxLength = 8)
                HqButton("ذخیره‌ی قیمت", {
                    save.run {
                        val a = parseCap(audio); val t = parseCap(text)
                        if (a == null || t == null) { toasts.error("قیمت باید عدد باشد."); return@run }
                        env.api.putVoicePrice(e.key, e.price.copy(audioOutPerM = a, textInPerM = t))
                        toasts.ok("قیمت ذخیره شد؛ کنتور از حالا با آن حساب میکند.")
                        edit = false
                        onSaved()
                    }
                }, Modifier.fillMaxWidth(), variant = BtnVariant.SILVER, size = BtnSize.SM, loading = save.busy)
            }
        }
    }
}

// ---------------------------------------------------------- the light, why --
/** Why an engine's light is what it is, and what to do about it (tap on a dot). */
@Composable
fun EngineReasonBody(engine: VoiceEngine, state: String, reason: String?, onKey: () -> Unit, onCheck: () -> Unit, checking: Boolean = false) {
    val c = Divan.colors
    val l = lightOf(state)
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        LightDot(state, size = 14.dp)
        Column(Modifier.weight(1f)) {
            Text(engine.titleFa.ifBlank { engineTitle(engine.key, listOf(engine)) }, style = Divan.type.h3)
            Text(lightFa(state), style = Divan.type.small, color = lightColor(l))
        }
    }
    reason?.takeIf { it.isNotBlank() }?.let { Para(it, style = Divan.type.small, color = c.textPrimary) }
    lightFix(state, reason)?.let { Para(it, style = Divan.type.small, color = c.textSecondary) }
    engine.rankFa.takeIf { it.isNotBlank() }?.let { Text(plain(it), style = Divan.type.micro, color = c.textMuted) }
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        if (engine.provider != "local") HqButton(if (state == "missing") "کلید را بده" else "کلید تازه", onKey, variant = BtnVariant.PRIMARY, icon = DivanIcon.LOCK, modifier = Modifier.weight(1f, fill = false))
        HqButton("بسنج", onCheck, variant = BtnVariant.SILVER, icon = DivanIcon.REFRESH, loading = checking)
    }
    Text("سنجش بی‌هزینه است؛ فقط وضعیت کلید را میپرسد.", style = Divan.type.micro, color = c.textMuted)
}
