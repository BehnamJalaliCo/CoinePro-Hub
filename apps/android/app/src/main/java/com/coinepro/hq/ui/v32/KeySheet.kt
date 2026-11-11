package com.coinepro.hq.ui.v32

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.lightFa
import com.coinepro.hq.core.data.lightFix
import com.coinepro.hq.core.data.lightOf
import com.coinepro.hq.core.data.lightState
import com.coinepro.hq.core.data.Light
import com.coinepro.hq.core.net.StepUp
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Expand
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.activity
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v18.SecretField
import com.coinepro.hq.ui.v29.Para
import com.coinepro.hq.ui.v29.plain

// Contract §32.5: the key given inside the chat. A masked sheet (no suggestions, no autocorrect, a password keyboard); saving is sealed
// (🔏 voice.secret on the provider) and write-only; the light then turns yellow, and green or red on the stream with the reason and the
// way to mend it. The key is held only in this sheet's memory: never saved with the screen's state, never in a draft, never in a log.

/**
 * The key's sheet. [initial] is a key the composer caught (it never reached a turn). [lights] is what the stream last said about each
 * engine; [saved0] opens it after the key went (the screenshot of the waiting light).
 */
@Composable
fun KeyBody(onClose: () -> Unit, initial: String = "", provider: String = "google", lights: Map<String, Pair<String, String?>> = emptyMap(), saved0: Boolean = false, askCap0: Boolean = false) {
    val c = Divan.colors
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val act = activity()
    val save = rememberAction()
    val remove = rememberAction()
    // Not rememberSaveable: a key is never written into the saved state of the screen.
    var secret by remember { mutableStateOf(initial) }
    var saved by rememberSaveable { mutableStateOf(saved0) }
    var askCap by rememberSaveable { mutableStateOf(askCap0) }
    val engines = rememberQuery("voice-engines", "voice", maxAgeMs = 5_000) { voiceEngines() }
    val settings = rememberQuery("owner-settings", "settings") { ownerSettings() }
    val mine = engines.data.orEmpty().filter { it.provider == provider }
    val hadKey = mine.any { it.state != "missing" }
    val sign: StepUp = { a, t -> env.auth.stepUp(act, a, t) }

    Text("کلید صدا", style = Divan.type.h2)
    Para("کلید API گوگل را (از AI Studio) این‌جا بگذار. کلید مستقیم به خزانه‌ی رمزها میرود و فوراً سنجیده میشود؛ هیچ‌جا در گفتگو، لاگ یا حافظه‌ی مدل نمیماند.", style = Divan.type.small)
    if (!saved) {
        SecretField(secret, { secret = it }, "AIza…", "کلید")
        Text("کلید گوگل با AIza شروع میشود. بی‌دلیل کلید را در متن گفتگو ننویس؛ برنامه آن را نمیفرستد و به همین برگه میآورد.", style = Divan.type.micro, color = c.textMuted)
        HqButton("ذخیره با اثر انگشت", {
            save.run {
                env.api.putVoiceSecret(provider, secret.trim(), sign)
                secret = ""
                saved = true
                env.cache.invalidate("voice")
                toasts.ok("کلید رفت؛ در حال سنجش.")
                // The first key: the owner says how much a month may cost, before anything is spent.
                if (settings.data?.voice?.monthCapUsd == null) askCap = true
            }
        }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, icon = DivanIcon.SEAL, enabled = secret.trim().length >= 8, loading = save.busy)
        if (hadKey) HqButton("برداشتن کلید", {
            remove.run {
                env.api.deleteVoiceSecret(provider, sign)
                env.cache.invalidate("voice")
                toasts.ok("کلید برداشته شد؛ صدا با صدای ساده ادامه میدهد.")
            }
        }, Modifier.fillMaxWidth(), variant = BtnVariant.DANGER, size = BtnSize.SM, icon = DivanIcon.LOCK, loading = remove.busy)
    }
    // The light, waiting and then settled.
    if (saved || hadKey) Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        for (e in mine) {
            val (state, reason) = lightState(e, lights).let { (s, r) -> if (saved && lights[e.key] == null && s == "missing") "checking" to null else s to r }
            Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    LightDot(state)
                    Text(e.titleFa.ifBlank { engineTitle(e.key, mine) }, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), modifier = Modifier.weight(1f))
                    Text(lightFa(state), style = Divan.type.caption, color = lightColor(lightOf(state)))
                }
                reason?.takeIf { it.isNotBlank() }?.let { Text(plain(it), style = Divan.type.caption, color = c.textPrimary) }
                if (lightOf(state) != Light.OK && lightOf(state) != Light.CHECKING) lightFix(state, reason)?.let { Text(plain(it), style = Divan.type.caption, color = c.textSecondary) }
            }
        }
    }
    Expand(saved && askCap) {
        Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(c.card).padding(14.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                DIcon(DivanIcon.BUDGET, size = 18.dp, tint = c.goldInk)
                Text("ماهی حداکثر چقدر خرج صدا؟", style = Divan.type.bodyStrong)
            }
            Text("تا خودت سقفی نگذاری، هیچ سقفی نیست. وقتی پر شود، صدا با موتور بعدی ادامه میدهد و هیچ‌وقت قطع نمیشود.", style = Divan.type.caption, color = c.textMuted)
            CapEditor(null, settings.data?.voice) { askCap = false }
        }
    }
    if (saved) HqButton("تمام", onClose, Modifier.fillMaxWidth(), variant = BtnVariant.SILVER)
}
