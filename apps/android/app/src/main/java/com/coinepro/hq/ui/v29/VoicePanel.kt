package com.coinepro.hq.ui.v29

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import com.coinepro.hq.designsystem.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.media.clock
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.MeterBar
import com.coinepro.hq.designsystem.Radius
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.media.Waveform

/** What the long voice shows while the owner speaks (the live [LongVoice], or fixed values for the screenshots). */
data class Listening(
    val partial: String,
    val elapsed: Double,
    /** phone · hub */
    val engine: String,
    val chunks: Int = 0,
    val sent: Int = 0,
    val fellBack: String? = null,
    val levels: List<Float> = List(32) { i -> 0.15f + ((i * 37) % 11) / 14f },
)

fun LongVoice.listening(): Listening = Listening(partial, elapsed, engine ?: "phone", chunks, sent, fellBack, levels)

/**
 * §29.5 while the owner speaks: the waveform, the time, and the text growing as it is heard (the phone's recogniser restarts at each pause
 * until «تمام»); over a minute the voice is recorded for the hub in chunks of up to 90 seconds, each sent while he keeps speaking.
 */
@Composable
fun ListeningPanel(l: Listening, onFinish: () -> Unit, onCancel: () -> Unit) {
    val c = Divan.colors
    val hub = l.engine == "hub"
    Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text(if (hub) "ضبط میشود؛ هاب به متن میکند" else "میشنوم… هر وقت تمام شد بزن «تمام»", style = Divan.type.bodyStrong, color = c.silverInk, textAlign = TextAlign.Center)
        Waveform(l.levels, Modifier.height(40.dp))
        if (l.partial.isNotBlank()) {
            val scroll = rememberScrollState()
            // The newest words stay in view as the text grows.
            LaunchedEffect(l.partial.length) { scroll.scrollTo(scroll.maxValue) }
            Text(
                plain(l.partial),
                style = Divan.type.body.copy(textAlign = TextAlign.Justify, lineHeight = Divan.type.h3.lineHeight),
                color = c.textPrimary,
                modifier = Modifier.fillMaxWidth().heightIn(max = 220.dp).clip(RoundedCornerShape(Radius.tile)).background(c.tile).verticalScroll(scroll).padding(12.dp),
            )
        }
        if (hub && l.chunks > 0) Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                DIcon(DivanIcon.SEND, size = 14.dp, tint = c.textSecondary)
                Text("${l.sent} از ${l.chunks} بخش به هاب رسید؛ هر بخش تا یک دقیقه و نیم", style = Divan.type.caption, color = c.textSecondary, modifier = Modifier.weight(1f))
            }
            MeterBar(if (l.chunks == 0) 0.0 else l.sent * 100.0 / l.chunks, tone = com.coinepro.hq.designsystem.BarTone.SILVER)
        }
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(14.dp)) {
            Fig(clock(l.elapsed), style = Divan.type.figure, color = c.textSecondary)
            Text("تمام", Modifier.clip(RoundedCornerShape(8.dp)).clickable { onFinish() }.padding(6.dp), style = Divan.type.small, color = c.silverInk)
            Text("لغو", Modifier.clip(RoundedCornerShape(8.dp)).clickable { onCancel() }.padding(6.dp), style = Divan.type.small, color = c.textMuted)
        }
        Text(
            if (hub) "صدا فقط به هاب میرود و از آن بیرون نمیرود؛ تا بیست دقیقه." else "تشخیص گفتار خود گوشی، فارسی؛ بیش از یک دقیقه که شد، صدا برای هاب ضبط میشود.",
            style = Divan.type.micro, color = c.textMuted, textAlign = TextAlign.Center,
        )
        l.fellBack?.let { why ->
            Row(
                Modifier.clip(RoundedCornerShape(10.dp)).background(c.softWarning).padding(horizontal = 10.dp, vertical = 6.dp),
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                DIcon(DivanIcon.INFO, size = 14.dp, tint = c.warning)
                Text(why, style = Divan.type.micro, color = c.textPrimary)
            }
        }
    }
}
