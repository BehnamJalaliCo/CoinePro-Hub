package com.coinepro.hq.ui.playbook

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.bestHourLines
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.MemberPublish
import com.coinepro.hq.core.net.gated
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.HqSwitch
import com.coinepro.hq.designsystem.timesFig
import com.coinepro.hq.ui.rememberQuery

// Contract §49: the best hour, by itself. The owner's order: «بعد از یک ماه صفحه را تحلیل کند و در ساعت‌های پربازدید منتشر کند». The hub
// reads each account's posts once a day and names the hour that did best; with «بهترین ساعت، خودکار» on, each day's package goes out at
// that hour, and at his fixed hour (or at once) while the data is still thin.

/** The best hour of a company's account ([account] null: its own one). Null on a hub before §49, or before the first answer. */
@Composable
internal fun rememberBestHour(company: String, account: String?) =
    rememberQuery("best-hour:$company:${account.orEmpty()}", "best-hour", maxAgeMs = 120_000) { gated(HubFeature.BEST_HOUR) { bestHour(company, account) } }

/**
 * «بهترین ساعت، خودکار» in the standing-publish settings of one company: its switch and, under it, what the hub knows (the hour and what
 * it rests on, or what is still missing and what it does till then). Nothing on a hub that does not read the hour yet: the fixed hour
 * stands alone, as before.
 */
@Composable
internal fun BestHourChoice(company: String, value: MemberPublish, onChange: (MemberPublish) -> Unit) {
    val c = Divan.colors
    val b = rememberBestHour(company, value.account).data ?: return
    Row(Modifier.fillMaxWidth().testTag("best-hour"), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text("بهترین ساعت، خودکار", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
            bestHourLines(b, value.at).forEachIndexed { i, line ->
                // the hour is the line he looks for; what it rests on is quiet
                Text(timesFig(line), style = Divan.type.micro, color = if (i == 0 && b.enough) c.goldInk else c.textMuted)
            }
        }
        HqSwitch(value.best, { onChange(value.copy(best = it)) }, "بهترین ساعت، خودکار")
    }
}
