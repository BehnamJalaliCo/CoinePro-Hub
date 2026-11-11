package com.coinepro.hq.ui.session

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import com.coinepro.hq.designsystem.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.PACE_FA
import com.coinepro.hq.core.data.PACE_HINT_FA
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.SegOption
import com.coinepro.hq.designsystem.Segmented
import com.coinepro.hq.designsystem.generated.DivanIcon

/** Shown under the two choices until the owner picks one: the session is not opened before he answers. */
const val PACE_ASK_FA = "این جلسه چطور جلو برود؟"
const val PACE_PICK_FIRST_FA = "اول یکی را انتخاب کن؛ بعد جلسه باز میشود."

/**
 * ⟨2026-11-09⟩ The owner's own answer when he makes a session (the owner: «به محض اینکه سشن رو میسازم باید اول از من بپرسه با من یا
 * خودکار»): «با من» (one step, then the holder asks) or «خودکار» (to the end). Nothing is chosen until he taps one ([pace] null), and
 * the caller keeps its «باز کن» off until then; the hub takes the answer over whatever the words say (§34.1).
 */
@Composable
fun PaceAsk(pace: String?, onPace: (String) -> Unit, modifier: Modifier = Modifier) {
    val c = Divan.colors
    Column(modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(PACE_ASK_FA, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
        Segmented(
            listOf(SegOption<String?>("step", PACE_FA.getValue("step"), DivanIcon.OWNER), SegOption<String?>("auto", PACE_FA.getValue("auto"), DivanIcon.RESUME)),
            pace, { p -> if (p != null) onPace(p) }, Modifier.fillMaxWidth(),
        )
        Text(pace?.let { PACE_HINT_FA[it] } ?: PACE_PICK_FIRST_FA, style = Divan.type.micro, color = if (pace == null) c.textSecondary else c.textMuted)
    }
}
