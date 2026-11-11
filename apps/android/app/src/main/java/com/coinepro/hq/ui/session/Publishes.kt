package com.coinepro.hq.ui.session

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.HorizontalDivider
import com.coinepro.hq.designsystem.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.cancellable
import com.coinepro.hq.core.data.cancelling
import com.coinepro.hq.core.data.faNum
import com.coinepro.hq.core.data.publishStateFa
import com.coinepro.hq.core.data.withPublish
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.jTime
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.SessionPublish
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.designsystem.timesFig
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.outputs.CancelAsk
import com.coinepro.hq.ui.outputs.KIND_FA
import com.coinepro.hq.ui.outputs.PublishCancel
import com.coinepro.hq.ui.outputs.rememberPublishCancel
import com.coinepro.hq.ui.v29.served

/*
 * Contract §44.5, §51: what went out, or is set to go out, from this session, newest first, in its «جزئیات». Each row says where its
 * publication stands; one that is not out yet carries a quiet «لغو» (asked once, in place), so a scheduled post is taken back here,
 * without looking for its output. Hidden while the session published nothing.
 */

/** A publication's state as a pill. */
@Composable
private fun StatePill(p: SessionPublish) {
    val tone = when (p.state) {
        "published" -> Tone.POS
        "failed" -> Tone.NEG
        "waiting_seal" -> Tone.WARN
        "cancelled" -> Tone.SILVER
        else -> Tone.GOLD
    }
    Pill(publishStateFa(p.state), tone, dot = true, live = p.state == "publishing" && !cancelling(p))
}

@Composable
internal fun SessionPublishes(publishes: List<SessionPublish>, onChanged: () -> Unit) {
    if (publishes.isEmpty()) return
    val c = Divan.colors
    val nav = LocalNav.current
    // the hub's answer to a cancel, shown at once (the report is read again behind it)
    var held by remember(publishes) { mutableStateOf(publishes) }
    val cancel = rememberPublishCancel { out -> held = withPublish(held, out); onChanged() }
    val canCancel = served(HubFeature.PUBLISH_CANCEL)
    HqCard(Modifier.fillMaxWidth().testTag("session-publishes")) {
        SectionTitle("انتشارها", note = "${faNum(held.size)} انتشار از این جلسه؛ تازه‌ترین بالا", icon = DivanIcon.SEND)
        Column(Modifier.padding(top = 6.dp)) {
            held.forEachIndexed { i, p ->
                if (i > 0) HorizontalDivider(color = c.lineDivider)
                PublishLine(p, cancel.takeIf { canCancel }) { p.output?.let { nav.go("outputs/$it") } }
            }
        }
    }
}

@Composable
private fun PublishLine(p: SessionPublish, cancel: PublishCancel?, onOpen: () -> Unit) {
    val c = Divan.colors
    val job = p.job
    val asking = job != null && cancel?.asking == job
    Column(Modifier.fillMaxWidth()) {
        Row(
            Modifier.fillMaxWidth().then(if (p.output != null) Modifier.clickable(role = Role.Button, onClickLabel = "خروجی‌اش", onClick = onOpen) else Modifier).padding(vertical = 10.dp),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            DIcon(if (p.kind == "reel") DivanIcon.VIDEO else DivanIcon.IMAGE, size = 18.dp, tint = c.textSecondary)
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Fig(p.fileName?.ifBlank { null } ?: "فایل", style = Divan.type.figureSmall, color = c.textPrimary)
                // the handle is Latin inside a Persian line: isolated left-to-right, so «@» stays in front of it
                val where = listOfNotNull(
                    KIND_FA[p.kind], p.scheduledAt?.takeIf { p.state == "scheduled" }?.let { "ساعت ${jTime(it)}" },
                    p.account?.let { "⁦@$it⁩" }, "خودکار".takeIf { p.auto },
                ).joinToString(" · ")
                // whole, on a second line when it has to: the hour and the account are what he looks for
                if (where.isNotEmpty()) Text(where, style = Divan.type.micro, color = c.textSecondary, maxLines = 2, overflow = TextOverflow.Ellipsis)
                // why it did not go out, or what the hub says of it meanwhile («در حال لغو», «لغو انجام نشد (…)»)
                p.noteFa?.trim()?.ifBlank { null }?.takeIf { p.state != "cancelled" && p.state != "published" }?.let {
                    Text(timesFig(it), style = Divan.type.micro, color = if (p.state == "failed") c.negative else if (cancelling(p)) c.goldInk else c.warning)
                }
                job?.let { j -> cancel?.refused?.get(j) }?.let { Text(timesFig(it), style = Divan.type.micro, color = c.warning) }
            }
            StatePill(p)
            if (job != null && cancel != null && !asking && cancellable(p)) HqButton("لغو", { cancel.ask(job) }, variant = BtnVariant.TEXT, size = BtnSize.SM, label = "لغو این انتشار")
        }
        if (asking && job != null && cancel != null) CancelAsk(job, cancel)
    }
}
