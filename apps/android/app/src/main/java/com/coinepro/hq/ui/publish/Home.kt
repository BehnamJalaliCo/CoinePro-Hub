package com.coinepro.hq.ui.publish

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.countdownFa
import com.coinepro.hq.core.data.faHour
import com.coinepro.hq.core.data.faNum
import com.coinepro.hq.core.data.heldLineFa
import com.coinepro.hq.core.data.latestOut
import com.coinepro.hq.core.data.pubKindFa
import com.coinepro.hq.core.format.HqClock
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.Text
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.v29.plain
import com.coinepro.hq.ui.v29.served

// ⟨1.39⟩ D6 «خانه»: the line «انتشار: ۲ آماده · ۱ در صف» becomes the card «انتشار امروز»: today's counts, the next one with its countdown,
// the latest five, a held one in a line; one tap opens the centre. It moves with the stream (§60.4) and with the minute.

/** One count of the card: a big figure over its word. */
@Composable
fun RowScope.Count(n: Int, word: String, tone: Color? = null) {
    val c = Divan.colors
    Column(Modifier.weight(1f).clip(RoundedCornerShape(14.dp)).background(c.tile).padding(horizontal = 10.dp, vertical = 8.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Text(faNum(n), style = Divan.type.h2.copy(fontWeight = FontWeight.Bold), color = tone ?: if (n == 0) c.textMuted else c.textPrimary, maxLines = 1)
        Text(word, style = Divan.type.micro, color = c.textSecondary, maxLines = 1)
    }
}

/** «انتشار امروز» on the home; nothing on a hub before §60 (the desk's line stays there). */
@Composable
fun PublishTodayCard(modifier: Modifier = Modifier) {
    if (!served(HubFeature.PUBLICATIONS)) return
    val q = rememberPubToday()
    val t = q.data ?: return
    val nav = LocalNav.current
    val c = Divan.colors
    OnPublication { q.refresh() }
    Every(60_000) { q.refresh() }
    val shape = RoundedCornerShape(22.dp)
    Column(
        modifier.fillMaxWidth().testTag("publish-today-card").clip(shape).background(c.card).border(1.dp, c.goldFill.copy(alpha = 0.22f), shape)
            .clickable(role = Role.Button, onClickLabel = "مرکز انتشار") { nav.go("publish") }.padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            DIcon(DivanIcon.SEND, size = 20.dp, tint = c.goldInk)
            Text("انتشار امروز", style = Divan.type.h3, modifier = Modifier.weight(1f))
            Pill("زنده", Tone.POS, dot = true, live = true)
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Count(t.counts.published, "منتشر شد")
            Count(t.counts.scheduled, "زمان‌بندی‌شده")
            Count(t.counts.held, "نگه‌داشته", tone = if (t.counts.held > 0) c.warning else null)
            Count(t.counts.failed, "خطا", tone = if (t.counts.failed > 0) c.negative else null)
        }
        t.next?.let { n ->
            Row(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)).border(1.dp, c.lineHairline, RoundedCornerShape(16.dp)).padding(horizontal = 12.dp, vertical = 10.dp),
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Column(Modifier.weight(1f)) {
                    Text("بعدی", style = Divan.type.micro, color = c.textMuted)
                    Text(plain("${faHour(n.at)} · ${n.automationFa ?: "${pubKindFa(n.kind)} ${n.titleFa}"} · @${n.account}"),
                        style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), maxLines = 1, overflow = TextOverflow.Ellipsis)
                }
                countdownFa(n.at, HqClock.millis())?.let { Pill(it, Tone.GOLD, icon = DivanIcon.TIME) }
            }
        }
        val latest = latestOut(t)
        if (latest.isNotEmpty()) Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("تازه‌ترین‌ها", style = Divan.type.micro, color = c.textMuted)
            Row(Modifier.testTag("latest-strip"), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                for (k in latest) PubCover(k.account, k.set?.let { "${faNum(it.n)} تا\n${faHour(k.at)}" } ?: "${pubKindFa(k.kind)}\n${faHour(k.at)}", k.thumbFileId, Modifier.size(width = 56.dp, height = 80.dp), radius = 12.dp)
            }
        }
        heldLineFa(t)?.let { Text(plain(it), style = Divan.type.micro, color = c.warning, maxLines = 2) }
    }
}
