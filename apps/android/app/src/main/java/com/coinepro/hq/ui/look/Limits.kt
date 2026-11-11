package com.coinepro.hq.ui.look

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.coerceIn
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.coinepro.hq.core.data.METER_FA
import com.coinepro.hq.core.data.accountPercent
import com.coinepro.hq.core.data.accountShare
import com.coinepro.hq.core.data.allFullFa
import com.coinepro.hq.core.data.inFa
import com.coinepro.hq.core.data.inFlight
import com.coinepro.hq.core.data.limitsReadAt
import com.coinepro.hq.core.data.meterShare
import com.coinepro.hq.core.data.meterState
import com.coinepro.hq.core.data.queueOpensAt
import com.coinepro.hq.core.format.jTime
import com.coinepro.hq.core.format.tokens
import com.coinepro.hq.core.net.ClaudeAccount
import com.coinepro.hq.core.net.Limits
import com.coinepro.hq.core.net.TodayMeter
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.Ring
import com.coinepro.hq.designsystem.RingTone
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.Text
import com.coinepro.hq.designsystem.animateFill
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.designsystem.ringColor
import com.coinepro.hq.designsystem.sep
import com.coinepro.hq.ui.live.rememberLive
import com.coinepro.hq.ui.live.rememberTicker

// ⟨1.0.1⟩ Part C, the limits of the treasury (C3.6, contract §55.3; features 111 and 112). The owner's Claude accounts, each one ring:
// the share of its window that is used in the middle, its name under it and one line of where it stands; the one the hub is on has
// the turning arc only while a call is in flight. When every account is full, one amber line says until when the work waits. Then
// today's meter: what the agents spent today against their daily cap, with marks at 70, 90 and 100 percent, coloured by its state.
// Every figure says when it was read. A hub before §55 does not serve the block: nothing is shown and the older quota card stays.

// A full account is red-amber, never plain amber: beside the gold of the page it must not read as gold.
private fun accountTone(state: String): RingTone = when (state) { "full" -> RingTone.NEAR; "off" -> RingTone.MUTED; else -> RingTone.SILVER }

/** One account: its ring, its name and one line of where it stands; a full one says when it opens, on the owner's clock and as a countdown. */
@Composable
private fun Account(a: ClaudeAccount, live: Boolean, now: Long, modifier: Modifier = Modifier) {
    val c = Divan.colors
    Column(modifier.widthIn(min = 132.dp).testTag("account-${a.key}"), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Ring(
            accountShare(a), size = 84.dp, stroke = 6.dp, tone = accountTone(a.state), live = live, broken = a.state == "off",
            label = "${a.nameFa}: ${a.utilization?.let { "${Math.round(it.coerceIn(0.0, 1.0) * 100)} درصد پر" } ?: "نامعلوم"}",
        ) {
            Fig(accountPercent(a), style = Divan.type.figureM.copy(fontSize = 19.sp, lineHeight = 24.sp, fontWeight = FontWeight.Bold), color = if (a.state == "off") c.textMuted else c.textPrimary)
        }
        Text(a.nameFa, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, textAlign = TextAlign.Center)
        when (a.state) {
            "working" -> Text("الان همین کار میکند", style = Divan.type.caption, color = c.textSecondary, textAlign = TextAlign.Center)
            "ready" -> Text("آماده", style = Divan.type.caption, color = c.textSecondary, textAlign = TextAlign.Center)
            "off" -> Text("خاموش", style = Divan.type.caption, color = c.textMuted, textAlign = TextAlign.Center)
            else -> {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    DIcon(DivanIcon.TIME, size = 13.dp, tint = c.warning)
                    Text(
                        buildAnnotatedString { append("پر است"); if (a.resetsAt != null) { append("؛ "); fig(jTime(a.resetsAt)); append(" خالی میشود") } },
                        style = Divan.type.caption, color = c.warning, textAlign = TextAlign.Center,
                    )
                }
                inFa(a.resetsAt, now)?.let { Text(it, style = Divan.type.micro, color = c.textMuted, textAlign = TextAlign.Center) }
            }
        }
    }
}

private val MARKS = listOf(70, 90, 100)

/** Today's meter: the agents' spend of today against their daily cap, with marks at 70, 90 and 100 percent. Silver while calm, amber
 *  past 70, red-amber past 90, red when the cap is reached; the word and its sign say it too (never colour alone). */
@Composable
fun TodayMeterBar(t: TodayMeter, now: Long, modifier: Modifier = Modifier) {
    val c = Divan.colors
    val share = meterShare(t)
    val state = meterState(t)
    val tone = when (state) { "warm" -> RingTone.WARN; "near" -> RingTone.NEAR; "full" -> RingTone.NEG; else -> RingTone.SILVER }
    val fill = ringColor(tone)
    val ink = when (state) { "calm" -> c.textSecondary; "full" -> c.negative; else -> c.warning }
    val pct = (share * 100).coerceIn(0.0, 100.0).toFloat()
    val shown by animateFill(pct / 100f)
    Column(modifier.fillMaxWidth().testTag("today-meter"), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Text("کنتور امروز", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                DIcon(when (state) { "calm" -> DivanIcon.SEAL; "warm" -> DivanIcon.TIME; else -> DivanIcon.URGENT }, size = 13.dp, tint = ink)
                Text(METER_FA[state] ?: state, style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = ink)
            }
            Box(Modifier.weight(1f))
            Text(
                buildAnnotatedString { fig(tokens(t.spent), c.textPrimary, FontWeight.Bold); append(" از "); fig(if (t.cap > 0) tokens(t.cap) else "—") },
                style = Divan.type.small, color = c.textSecondary, maxLines = 1,
            )
        }
        BoxWithConstraints(Modifier.fillMaxWidth().padding(top = 2.dp).height(34.dp).semantics { contentDescription = "مصرف امروز از سقف روزانه: ${Math.round(pct)} درصد" }) {
            val w = maxWidth
            // The track and its fill (the fill starts at the reading side).
            Box(Modifier.fillMaxWidth().height(12.dp).clip(CircleShape).background(c.tile))
            Box(Modifier.align(Alignment.TopStart).width(w * shown).height(12.dp).clip(CircleShape).background(fill))
            for (m in MARKS) {
                val passed = pct >= m
                // From the reading side (offset follows the layout direction by itself).
                val at = w * (m / 100f) - if (m == 100) 1.5.dp else 0.dp
                // A mark: a short line through the track, and its percent under it (Latin).
                Box(Modifier.align(Alignment.TopStart).offset(x = at, y = (-3).dp).width(1.5.dp).height(18.dp).background(if (passed) fill else c.lineStrong))
                // Its percent under it: centred on the 70 mark; the 90 one stands before its mark and the 100 one ends with the track, so
                // the last two never sit on each other on a narrow phone.
                val box = 30.dp
                val x = when (m) { 70 -> at - box / 2; 90 -> at - box; else -> w - box }
                Fig(
                    "$m%", Modifier.align(Alignment.TopStart).offset(x = x.coerceIn(0.dp, w - box), y = 18.dp).width(box),
                    style = Divan.type.figureSmall.copy(fontSize = 10.sp, textAlign = when (m) { 70 -> TextAlign.Center; 90 -> TextAlign.Right; else -> TextAlign.Left }), color = if (passed) ink else c.textMuted,
                )
            }
        }
        if (t.noteFa.isNotBlank()) Text(t.noteFa, style = Divan.type.caption, color = c.textSecondary)
        if (t.resetsAt.isNotBlank()) Text(
            buildAnnotatedString { append("ساعت "); fig(jTime(t.resetsAt)); append(" از نو شروع میشود"); inFa(t.resetsAt, now)?.let { append("، $it") }; append(".") },
            style = Divan.type.micro, color = c.textMuted,
        )
    }
}

/** The limits block of the treasury. Nothing when the hub does not serve it. [flying]: whether a model call is in flight now (the
 *  working account's arc turns only then); null: read from the live store. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
fun LimitsBlock(limits: Limits?, modifier: Modifier = Modifier, flying: Boolean? = null) {
    if (limits == null) return
    val c = Divan.colors
    val now = rememberTicker(30_000)
    val live = rememberLive()
    val calling = flying ?: (inFlight(live.tokens, now) > 0)
    val accounts = limits.accounts
    val opens = if (limits.waiting) queueOpensAt(limits) else null
    val read = limitsReadAt(limits)
    HqCard(modifier.fillMaxWidth().testTag("limits")) {
        SectionTitle("اکانت‌های Claude")
        Text(
            buildAnnotatedString {
                accounts.firstOrNull()?.windowFa?.takeIf { it.isNotBlank() }?.let { append(it); sep() }
                if (read != null) { append("خوانده‌شده در "); fig(jTime(read)) } else append("هنوز خوانده نشده")
            },
            style = Divan.type.caption, color = c.textMuted, modifier = Modifier.padding(top = 2.dp),
        )
        Column(Modifier.padding(top = 14.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
            if (limits.waiting) Row(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.softWarning).padding(horizontal = 12.dp, vertical = 10.dp).testTag("limits-waiting"),
                horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.Top,
            ) {
                DIcon(DivanIcon.TIME, Modifier.padding(top = 3.dp), size = 16.dp, tint = c.warning)
                Text(
                    buildAnnotatedString { append(allFullFa(accounts.size)); append("؛ کارها "); if (opens != null) { append("تا "); fig(jTime(opens)); append(" ") }; append("در صف میمانند.") },
                    style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.warning, modifier = Modifier.weight(1f),
                )
            }
            if (accounts.isNotEmpty()) FlowRow(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceAround, verticalArrangement = Arrangement.spacedBy(18.dp)) {
                for (a in accounts) Account(a, live = a.state == "working" && calling, now = now)
            }
            HorizontalDivider(color = c.lineDivider)
            TodayMeterBar(limits.today, now)
        }
    }
}
