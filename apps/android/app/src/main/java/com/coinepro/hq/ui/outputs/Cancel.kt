package com.coinepro.hq.ui.outputs

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.Stable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.Env
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.SessionPublish
import com.coinepro.hq.core.net.gated
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Toasts
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch

/*
 * Contract §51: a scheduled post taken back from the app. A row of a publication that is not out yet carries a quiet «لغو»; it asks once,
 * in place, and the hub's answer takes the row's place (cancelled at once, or «در حال لغو» while IG-Hub is asked). His tap, no passkey.
 * A hub before §51 has no such route: said once, then «لغو» is not offered.
 */

/** The cancel of one list of publications: which row is asking, which is on its way, and what the hub refused (shown on that row). */
@Stable
internal class PublishCancel(private val env: Env, private val toasts: Toasts, private val scope: CoroutineScope, private val onAnswer: (SessionPublish) -> Unit) {
    var asking by mutableStateOf<String?>(null)
    var busy by mutableStateOf<String?>(null)
        private set
    var refused by mutableStateOf(mapOf<String, String>())
        private set

    fun ask(job: String) { refused = refused - job; asking = job }

    fun confirm(job: String) {
        if (busy != null) return
        busy = job
        scope.launch {
            try {
                val out = env.api.gated(HubFeature.PUBLISH_CANCEL) { cancelPublish(job) }
                if (out == null) toasts.info("این نسخه‌ی هاب هنوز لغو انتشار ندارد؛ بعد از به‌روز شدن هاب می‌آید.")
                else {
                    onAnswer(out)
                    // the panel of its output and the session's report are read again behind the answer
                    env.cache.invalidate("publish", "order-report")
                    when {
                        out.state == "cancelled" -> toasts.ok("لغو شد؛ منتشر نمیشود.")
                        out.state == "published" -> toasts.info("پیش از لغو منتشر شده بود.")
                        else -> toasts.info(out.noteFa ?: "در حال لغو")
                    }
                }
            } catch (e: ApiException) {
                // the hub's own plain answer (out already, still on its way): said on the row, not an error to trace
                if (e.status == 409) { e.logged?.let { env.api.failures?.forget(it) }; refused = refused + (job to e.messageFa) }
                else toasts.error(e.messageFa)
            } finally {
                busy = null
                asking = null
            }
        }
    }
}

@Composable
internal fun rememberPublishCancel(onAnswer: (SessionPublish) -> Unit): PublishCancel {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val scope = rememberCoroutineScope()
    val latest = androidx.compose.runtime.rememberUpdatedState(onAnswer)
    return remember(env) { PublishCancel(env, toasts, scope) { latest.value(it) } }
}

/** The question, in the row's own place: «این انتشار لغو شود؟» · «لغو کن» / «نه». */
@Composable
internal fun CancelAsk(job: String, cancel: PublishCancel, modifier: Modifier = Modifier) {
    val c = Divan.colors
    Row(modifier.fillMaxWidth().testTag("cancel-ask").padding(bottom = 8.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        Text("این انتشار لغو شود؟", style = Divan.type.small, color = c.textPrimary, modifier = Modifier.weight(1f))
        HqButton("لغو کن", { cancel.confirm(job) }, variant = BtnVariant.DANGER, size = BtnSize.SM, loading = cancel.busy == job)
        HqButton("نه", { cancel.asking = null }, variant = BtnVariant.TEXT, size = BtnSize.SM, enabled = cancel.busy == null)
    }
}
