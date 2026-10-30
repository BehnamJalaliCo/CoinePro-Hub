package com.coinepro.hq.ui.work

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.PlayerAvailability
import com.coinepro.hq.core.data.PlayerOption
import com.coinepro.hq.core.data.Recognised
import com.coinepro.hq.core.data.availabilityOf
import com.coinepro.hq.core.data.councilSeats
import com.coinepro.hq.core.data.optionNoteFa
import com.coinepro.hq.core.net.Substitute
import com.coinepro.hq.core.net.Work
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.ModelMark
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.rememberQuery

// Contract §27.1 ⟨1.9⟩: «با کدام مدل؟». The owner names who plays an order: the router (default), Claude, a substitute seat (GPT, Gemini,
// DeepSeek: §21.13, within its daily cap, with the same masking), or the council of models (§27.2). Each choice wears its provider's
// logo; a substitute that is signed out, limited or off is greyed with the reason (chosen anyway, the run waits up to 30 minutes for
// it and then falls back to the router, and a notification says so).

/** The substitutes as `GET /substitutes` lists them (shared with their page). */
@Composable
fun rememberSubstitutes(): List<Substitute>? = rememberQuery("substitutes", "substitutes", maxAgeMs = 60_000) { substitutes() }.data

/** An option's mark: the provider's logo; the router's model glyph; the council as the seated players' logos side by side. */
@Composable
fun PlayerLogo(option: PlayerOption, size: Dp = 16.dp, seats: List<PlayerOption> = listOf(PlayerOption.CLAUDE, PlayerOption.GPT, PlayerOption.GEMINI, PlayerOption.DEEPSEEK)) {
    when (option) {
        PlayerOption.AUTO -> DIcon(DivanIcon.MODEL, size = size, tint = Divan.colors.textSecondary)
        PlayerOption.COUNCIL -> {
            val c = Divan.colors
            val step = size * 0.62f
            Box(Modifier.width(step * (seats.size - 1) + size).height(size)) {
                seats.forEachIndexed { i, p ->
                    Box(
                        Modifier.offset(x = step * i).size(size).clip(CircleShape).background(c.card).border(1.dp, c.lineDivider, CircleShape),
                        contentAlignment = Alignment.Center,
                    ) { ModelMark(null, provider = p.provider, size = size * 0.68f) }
                }
            }
        }
        else -> ModelMark(null, provider = option.provider, size = size)
    }
}

/**
 * The compact choice of who plays: six chips, each with its logo; the substitutes' availability from `GET /substitutes`, a greyed chip
 * naming its state; under them one sentence on what the choice means and why a greyed player is greyed. [heard]: what a voice order
 * named (shown above the chips, «از گفتار: «با جمنای»»).
 */
@Composable
fun PlayerPicker(value: PlayerOption, onChange: (PlayerOption) -> Unit, modifier: Modifier = Modifier, heard: Recognised? = null, subs: List<Substitute>? = rememberSubstitutes()) {
    val c = Divan.colors
    val seats = councilSeats(subs)
    Column(modifier, verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text("با کدام مدل؟", style = Divan.type.caption, color = c.textMuted)
        heard?.let { h ->
            Row(
                Modifier.clip(RoundedCornerShape(10.dp)).background(c.softLapis).padding(horizontal = 10.dp, vertical = 6.dp),
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                DIcon(DivanIcon.MIC, size = 13.dp, tint = c.lapis)
                Text("از گفتار شنیده شد: «${h.phrase}» ← ${h.option.fa}", style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = c.lapis)
                if (h.option != value) Text("· انتخاب تو جایش نشست", style = Divan.type.micro, color = c.textSecondary)
            }
        }
        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            for (o in PlayerOption.entries) PlayerChip(o, o == value, availabilityOf(o, subs), seats) { onChange(o) }
        }
        val a = availabilityOf(value, subs)
        Text(optionNoteFa(value, a, seats.size), style = Divan.type.micro, color = if (a.waits) c.warning else c.textSecondary)
        // Every greyed player, with its reason (the chosen one is said above).
        val greyed = PlayerOption.entries.filter { it.substitute && it != value }.map { it to availabilityOf(it, subs) }.filter { !it.second.ok }
        if (greyed.isNotEmpty()) Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
            for ((o, av) in greyed) Row(verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Box(Modifier.padding(top = 2.dp).alpha(0.5f)) { PlayerLogo(o, 12.dp) }
                Text("${o.fa}: ${av.stateFa}؛ ${av.reasonFa}", style = Divan.type.micro, color = c.textMuted, maxLines = 2)
            }
        }
    }
}

@Composable
private fun PlayerChip(o: PlayerOption, selected: Boolean, a: PlayerAvailability, seats: List<PlayerOption>, onClick: () -> Unit) {
    val c = Divan.colors
    Row(
        Modifier.height(34.dp).clip(CircleShape).background(if (selected) c.softGold else androidx.compose.ui.graphics.Color.Transparent)
            .border(1.dp, if (selected) c.lineTahrir else c.lineStrong, CircleShape)
            .selectable(selected, role = Role.RadioButton, onClick = onClick)
            .semantics { contentDescription = o.fa; if (!a.ok) stateDescription = a.stateFa.orEmpty() }
            .padding(horizontal = 10.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Box(Modifier.alpha(if (a.ok) 1f else 0.45f)) { PlayerLogo(o, 16.dp, if (o == PlayerOption.COUNCIL) seats else emptyList()) }
        Text(
            o.fa, style = Divan.type.small.copy(fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Normal),
            color = when { selected -> c.goldInk; a.ok -> c.textSecondary; else -> c.textMuted },
        )
        if (!a.ok) Text(a.stateFa.orEmpty(), style = Divan.type.micro, color = c.textMuted)
    }
}

/** Who plays an order, as a small tag for its row: shown only when the owner named a player or called the council. */
@Composable
fun PlayerTag(player: String, mode: String, modifier: Modifier = Modifier, always: Boolean = false) {
    val o = PlayerOption.of(player, mode)
    if (o == PlayerOption.AUTO && !always) return
    val c = Divan.colors
    Row(
        modifier.height(22.dp).clip(CircleShape).background(if (o == PlayerOption.COUNCIL) c.softGold else c.tile).padding(horizontal = 8.dp)
            .semantics(mergeDescendants = true) { contentDescription = "بازیکن: ${o.fa}" },
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(5.dp),
    ) {
        PlayerLogo(o, 12.dp)
        Text(if (o == PlayerOption.COUNCIL) "شورا" else o.fa, style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = if (o == PlayerOption.COUNCIL) c.goldInk else c.textSecondary)
    }
}

/** On the order's tracker and its page: who plays it, in a line, with what that means; a named player that never came, said. */
@Composable
fun PlayerLine(w: Work) {
    val c = Divan.colors
    val o = PlayerOption.of(w.player, w.mode)
    if (w.playerFallback) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Box(Modifier.size(22.dp), contentAlignment = Alignment.Center) { DIcon(DivanIcon.MODEL, size = 15.dp, tint = c.warning) }
        Text("بازیکن نامبرده ۳۰ دقیقه در دسترس نبود؛ از آن پس مسیریاب خودکار بازی میکند.", style = Divan.type.caption, color = c.warning)
    } else Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Box(Modifier.height(22.dp).widthIn(min = 22.dp), contentAlignment = Alignment.Center) { PlayerLogo(o, if (o == PlayerOption.COUNCIL) 14.dp else 15.dp) }
        Text(
            when (o) {
                PlayerOption.AUTO -> "بازیکن: خودکار؛ مسیریاب مدل انتخاب میکند"
                PlayerOption.COUNCIL -> when (w.media) {
                    "image" -> "شورای مدل‌ها: هر بازیکن عکس خودش را میسازد؛ یکی را تو انتخاب میکنی"
                    "video" -> "شورای مدل‌ها: هر بازیکن ویدیوی خودش را میسازد؛ یکی را تو انتخاب میکنی"
                    else -> "شورای مدل‌ها: هر بازیکن جدا، Claude جمع‌بندی میکند"
                }
                PlayerOption.CLAUDE -> "بازیکن: Claude"
                else -> "بازیکن: ${o.fa}، در سقف روزانه‌ی جایگاهش"
            },
            style = Divan.type.caption, color = c.textSecondary,
        )
    }
}
