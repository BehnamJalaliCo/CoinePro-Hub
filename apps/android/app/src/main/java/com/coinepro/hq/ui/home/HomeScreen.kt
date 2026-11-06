package com.coinepro.hq.ui.home

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.width
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.tokens
import com.coinepro.hq.designsystem.CompanyMark
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.MeterBar
import com.coinepro.hq.designsystem.budgetTone

// ⟨1.17⟩ §35.5 the owner's home is his office (ui/office/Office.kt). What stays here is the treasury's budget line; the older home
// (greeting buttons, the morning, one card per working group, the stream's orbit) is gone with it.

@Composable
fun BudgetLine(holding: Boolean, code: String, name: String, used: Long, limit: Long?, pct: Double?) {
    val c = Divan.colors
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            if (holding) Text("کل هلدینگ", style = Divan.type.caption, color = c.textSecondary)
            else {
                CompanyMark(code, height = 13.dp, mono = true, ink = c.textSecondary)
                Text(name, style = Divan.type.caption, color = c.textSecondary)
            }
            Box(Modifier.weight(1f))
            Fig("${tokens(used)} / ${tokens(limit)}", style = Divan.type.figureSmall, color = c.textMuted)
            val p = pct ?: 0.0
            Text("${p.toInt()}٪", style = Divan.type.caption, color = when { p >= 90 -> c.negative; p >= 70 -> c.warning; else -> c.textSecondary }, modifier = Modifier.width(36.dp))
        }
        MeterBar(pct ?: 0.0, tone = budgetTone(pct))
    }
}
