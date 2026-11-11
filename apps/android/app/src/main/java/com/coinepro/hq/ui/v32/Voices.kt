package com.coinepro.hq.ui.v32

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
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
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.faceOrder
import com.coinepro.hq.core.data.lightFa
import com.coinepro.hq.core.data.lightState
import com.coinepro.hq.core.data.personaTitle
import com.coinepro.hq.core.data.sampleCostFa
import com.coinepro.hq.core.net.TalkPersona
import com.coinepro.hq.core.net.VoiceEngine
import com.coinepro.hq.core.net.VoiceVoice
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Expand
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.ScrollRow
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v29.plain

// Contract §32.1 and §32.5: the voice of each persona, chosen by ear. Per persona: the engine, then the voice with «بشنو» (a short
// sample from `POST /voice/sample`, its cost said), then `PUT /talk/personas/{key}`. The charter is not editable here.

/** Every persona in the room with its engine and voice; tapping one opens its choice. [onPlay] plays a sample's file. */
@Composable
fun VoicesBody(present: List<String>, lights: Map<String, Pair<String, String?>> = emptyMap(), open0: String? = null, onPlay: (String, Double) -> Unit = { _, _ -> }) {
    val c = Divan.colors
    val personas = rememberQuery("talk-personas", "talk", maxAgeMs = 30_000) { talkPersonas() }
    val engines = rememberQuery("voice-engines", "voice", maxAgeMs = 30_000) { voiceEngines() }
    var open by rememberSaveable { mutableStateOf(open0) }
    val faces = faceOrder(personas.data.orEmpty(), present)
    Text("صدای هر نقش", style = Divan.type.h2)
    Text("هر نقش صدای خودش را دارد. با «بشنو» نمونه‌ی کوتاهی میشنوی و هزینه‌اش را همان‌جا میبینی؛ بعد انتخاب کن.", style = Divan.type.caption, color = c.textMuted)
    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(c.card)) {
        faces.forEachIndexed { i, p ->
            if (i > 0) HorizontalDivider(color = c.lineDivider)
            PersonaVoiceRow(p, engines.data.orEmpty(), lights, open == p.id, { open = if (open == p.id) null else p.id }, onPlay) { personas.refresh() }
        }
    }
}

@Composable
private fun PersonaVoiceRow(p: TalkPersona, engines: List<VoiceEngine>, lights: Map<String, Pair<String, String?>>, open: Boolean, onToggle: () -> Unit, onPlay: (String, Double) -> Unit, onSaved: () -> Unit) {
    val c = Divan.colors
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val save = rememberAction()
    val hear = rememberAction()
    var engine by rememberSaveable(p.id, p.voice.engine) { mutableStateOf(p.voice.engine.ifBlank { engines.firstOrNull()?.key.orEmpty() }) }
    val voices = rememberQuery("voice-voices:$engine", "voice", maxAgeMs = 120_000) { if (engine.isBlank()) emptyList() else voiceVoices(engine) }
    val list: List<VoiceVoice> = voices.data?.takeIf { it.isNotEmpty() } ?: engines.firstOrNull { it.key == engine }?.voices.orEmpty()
    val costs = remember { mutableStateMapOf<String, String>() }
    val saveKey = p.id
    Column {
        Row(
            Modifier.fillMaxWidth().clickable(role = Role.Button, onClickLabel = if (open) "بستن" else "انتخاب صدا", onClick = onToggle).padding(horizontal = 14.dp, vertical = 10.dp),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            PersonaFace(p, size = 34.dp)
            Column(Modifier.weight(1f)) {
                Text(personaTitle(p), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), maxLines = 1, overflow = TextOverflow.Ellipsis)
                val eTitle = engineTitle(p.voice.engine, engines)
                Text(com.coinepro.hq.designsystem.timesFig(if (p.voice.voice.isBlank()) "صدایی انتخاب نشده" else "${p.voice.voice} · $eTitle"), style = Divan.type.micro, color = c.textMuted, maxLines = 1)
            }
            com.coinepro.hq.designsystem.Chevron(open, tint = c.textMuted)
        }
        Expand(open) {
            Column(Modifier.fillMaxWidth().padding(horizontal = 14.dp).padding(bottom = 12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                ScrollRow {
                    for (e in engines) {
                        val (st, _) = lightState(e, lights)
                        FilterChip("${e.titleFa.ifBlank { engineTitle(e.key, engines) }} · ${lightFa(st)}", engine == e.key, { engine = e.key })
                    }
                }
                if (list.isEmpty()) Text("صدایی برای این موتور پیدا نشد.", style = Divan.type.caption, color = c.textMuted)
                for (v in list) {
                    val on = p.voice.engine == engine && p.voice.voice == v.name
                    Row(
                        Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(if (on) c.raised else c.tile).padding(horizontal = 12.dp, vertical = 6.dp),
                        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        Column(Modifier.weight(1f)) {
                            Text(com.coinepro.hq.designsystem.timesFig(v.name), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                            val line = listOfNotNull(v.genderFa, costs[v.name]).joinToString(" · ")
                            if (line.isNotBlank()) Text(plain(line), style = Divan.type.micro, color = c.textMuted)
                        }
                        HqButton("بشنو", {
                            hear.run {
                                val s = env.api.talkVoiceSample(engine, v.name)
                                costs[v.name] = sampleCostFa(s.usd)
                                if (s.fileId.isNotBlank()) onPlay(s.fileId, s.seconds)
                                env.cache.invalidate("voice")
                            }
                        }, variant = BtnVariant.SILVER, size = BtnSize.SM, icon = DivanIcon.MIC, loading = hear.busy)
                        HqButton(if (on) "انتخاب‌شده" else "این را بگذار", {
                            save.run {
                                env.api.setTalkPersona(saveKey, engine, v.name, null)
                                env.cache.invalidate("talk")
                                toasts.ok("صدای ${personaTitle(p)} شد ${v.name}.")
                                onSaved()
                            }
                        }, variant = if (on) BtnVariant.GHOST else BtnVariant.TEXT, size = BtnSize.SM, enabled = !on, loading = save.busy)
                    }
                }
            }
        }
    }
}
