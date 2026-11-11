package com.coinepro.hq.ui.session

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.relocation.BringIntoViewRequester
import androidx.compose.foundation.relocation.bringIntoViewRequester
import androidx.compose.material3.HorizontalDivider
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.LivePanel
import com.coinepro.hq.core.data.lineKey
import com.coinepro.hq.core.data.livePanelOf
import com.coinepro.hq.core.data.quietLine
import com.coinepro.hq.core.net.SessionActivity
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.Text
import com.coinepro.hq.ui.live.rememberTicker
import com.coinepro.hq.ui.look.IdleNudge
import com.coinepro.hq.ui.look.LiveSheetBody
import com.coinepro.hq.ui.look.MoodLight
import com.coinepro.hq.ui.v29.plain
import kotlinx.coroutines.delay

// Contract §41 ⟨1.23⟩ «مثل خود کلود کد»: the owner sees the work happen. ⟨1.0.1⟩ Part C: on the session's page the work that is live
// is the «الان» bar over the composer and the thin lines at the end of the thread (`ui/look/Session.kt`); a tap on the bar opens
// «کار زنده», drawn here: who works on what, each with its own line and time (a workshop or direct turn with its build ring), then
// every step so far, and, when nobody works, why: the owner is asked, it is stuck (with «ادامه بده»), or it is quiet since a time.
// ⟨2026-11-11⟩ An outside call (ChatGPT drafting the text, the AI narrator) is one of those at work, with its model's mark.

/**
 * «کار زنده»: who works, every step so far, and at the end what the session waits on when nobody works. [canNudge]: the hub takes
 * «ادامه بده» (and the session is not waiting for his OK, [ready]). [companyName] names a step's company by its code.
 */
@Composable
internal fun LiveWorkSheetBody(
    a: SessionActivity, ready: Boolean, canNudge: Boolean, nudging: Boolean, onNudge: () -> Unit, companyName: (String?) -> String? = { null },
) {
    val c = Divan.colors
    val panel = livePanelOf(a)
    val now = rememberTicker(1_000, on = panel == LivePanel.WORKING)
    val end = remember { BringIntoViewRequester() }
    // The newest step is brought into view on opening and as steps arrive.
    LaunchedEffect(a.last.size, a.last.lastOrNull()?.let(::lineKey)) { delay(250); end.bringIntoView() }
    LiveSheetBody(a, now, companyName)
    Column(Modifier.fillMaxWidth().bringIntoViewRequester(end), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        when (panel) {
            LivePanel.WORKING -> Spacer(Modifier.height(1.dp))
            LivePanel.WAITING -> {
                HorizontalDivider(color = c.lineDivider)
                Row(Modifier.testTag("live-why"), verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    MoodLight("waiting", Modifier.padding(top = 2.dp))
                    Text(plain(quietLine(a.waitingFa.orEmpty())), style = Divan.type.small, color = c.textPrimary, modifier = Modifier.weight(1f))
                }
            }
            LivePanel.STUCK -> {
                HorizontalDivider(color = c.lineDivider)
                Row(Modifier.testTag("live-why"), verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    MoodLight("stuck", Modifier.padding(top = 2.dp))
                    Text(plain(quietLine(a.stuckFa.orEmpty())), style = Divan.type.small, color = c.textPrimary, modifier = Modifier.weight(1f))
                }
                if (canNudge) HqButton("ادامه بده", onNudge, variant = BtnVariant.SECONDARY, size = BtnSize.SM, loading = nudging)
            }
            LivePanel.IDLE -> if (canNudge && !ready) {
                HorizontalDivider(color = c.lineDivider)
                IdleNudge(a, nudging, onNudge)
            }
        }
    }
}
