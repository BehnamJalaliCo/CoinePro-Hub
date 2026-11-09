package com.coinepro.hq.ui.v29

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.COUNCIL_ROLE_FA
import com.coinepro.hq.core.data.connectionKindFa
import com.coinepro.hq.core.data.figureText
import com.coinepro.hq.core.format.jDate
import com.coinepro.hq.core.net.Council
import com.coinepro.hq.core.net.FactPack
import com.coinepro.hq.core.net.orderWithPace
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.Chevron
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Expand
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.Md
import com.coinepro.hq.designsystem.ModelMark
import com.coinepro.hq.designsystem.Radius
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.rememberAction

// Contract §29.8 ⟨1.11⟩: the council v2, outside advisors with a fact pack. Three rounds (proposals, critique, the captain's plan); the
// owner reads the plan in five to ten lines and «اجرا کن» makes an order of it (§29.4). Each player's role is named beside it, the fact
// pack the council started from is a tap away, and each member's whole answer stays behind «جزئیات».

/** The round the council is in, in words. */
fun councilRoundFa(k: Council): String? = when (k.round) {
    1 -> "دور اول: هر مشاور پیشنهادش را مینویسد"
    2 -> "دور دوم: هر کدام پیشنهاد بقیه را نقد میکند"
    3 -> "دور سوم: کاپیتان برنامه را مینویسد"
    else -> null
}

/** A player's role in this council (captain, researcher, numbers, devil's advocate), or null for a council before v2. */
fun councilRoleFa(k: Council, player: String): String? = k.roles[player]?.let { COUNCIL_ROLE_FA[it] ?: it }

/** The captain's plan with «اجرا کن». */
@Composable
fun CouncilPlan(k: Council) {
    val env = LocalEnv.current
    val nav = LocalNav.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val action = rememberAction()
    val plan = k.planMd ?: return
    // ⟨2026-11-09⟩ «اجرا کن» makes a session too: «با من یا خودکار؟» first, nothing chosen for the owner
    var pace by rememberSaveable(k.workRef) { mutableStateOf<String?>(null) }
    Column(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(Radius.tile)).background(c.softGold).border(1.dp, c.lineTahrir, RoundedCornerShape(Radius.tile)).padding(14.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            ModelMark("claude", provider = "anthropic", size = 18.dp)
            Column(Modifier.weight(1f)) {
                Text("برنامه‌ی شورا", style = Divan.type.bodyStrong, color = c.goldInk)
                Text("چه کسی · چه کاری · تا کی", style = Divan.type.micro, color = c.textSecondary)
            }
        }
        Md(plan, color = c.textPrimary)
        com.coinepro.hq.ui.session.PaceAsk(pace, { pace = it })
        HqButton("اجرا کن", {
            val chosen = pace ?: return@HqButton
            action.run {
                val o = env.api.orderWithPace(plan.trim(), "text", null, null, chosen)
                env.cache.invalidate("orders", "work", "home")
                toasts.ok("برنامه فرمان شد؛ گزارشش را دنبال کن.", "گزارش") { nav.go("session/${o.ref}") }
            }
        }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, icon = DivanIcon.SEND, enabled = pace != null, loading = action.busy)
    }
}

/** What the council knew before it started: the hub's figures and the connections', each with its source and day. */
@Composable
fun FactPackView(fp: FactPack) {
    val c = Divan.colors
    var open by rememberSaveable(fp.at) { mutableStateOf(false) }
    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(Radius.tile)).background(c.tile).padding(horizontal = 12.dp, vertical = 10.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(
            Modifier.fillMaxWidth().clip(RoundedCornerShape(8.dp)).clickable(role = Role.Button, onClickLabel = if (open) "بستن" else "باز کردن") { open = !open },
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text("بسته‌ی واقعیت‌ها", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, modifier = Modifier.weight(1f))
            Text("${fp.figures.size} عدد", style = Divan.type.micro, color = c.textMuted)
            Chevron(open, tint = c.textMuted)
        }
        Expand(open) {
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                fp.figures.forEachIndexed { i, f ->
                    if (i > 0) HorizontalDivider(color = c.lineDivider)
                    Row(Modifier.padding(vertical = 4.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Column(Modifier.weight(1f)) {
                            Text(plain(f.titleFa), style = Divan.type.small, color = c.textPrimary)
                            Text(plain(listOfNotNull(connectionKindFa(f.source).takeIf { f.source.isNotBlank() }, f.at?.let { jDate(it) }).joinToString(" · ")), style = Divan.type.micro, color = c.textMuted)
                        }
                        Fig(figureText(f.value), style = Divan.type.figure, color = c.textPrimary)
                    }
                }
                if (fp.notesFa.isNotBlank()) Para(fp.notesFa)
                Text("بدون هیچ رمز یا داده‌ی شخصی.", style = Divan.type.micro, color = c.textMuted)
            }
        }
    }
}

/** «جزئیات»: each member's whole answer and the synthesis, folded under the plan. */
@Composable
fun CouncilDetails(k: Council, content: @Composable () -> Unit) {
    var open by rememberSaveable(k.workRef) { mutableStateOf(false) }
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        HqButton(if (open) "بستن جزئیات" else "جزئیات: پاسخ هر مشاور", { open = !open }, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.REPORT)
        Expand(open) { Column(verticalArrangement = Arrangement.spacedBy(8.dp)) { content() } }
    }
}
