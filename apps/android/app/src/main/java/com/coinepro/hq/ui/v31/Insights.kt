package com.coinepro.hq.ui.v31

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.growthMetricFa
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.Insights
import com.coinepro.hq.core.net.gated
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v29.Para
import com.coinepro.hq.ui.v29.plain

// Contract §31.1 ⟨1.13⟩: the lessons of a line. After the 24-hour and 7-day reads, code ranks the line's published runs by its metric and
// writes what worked: the best hour, length, speaker and pattern, the best opening lines, and the lessons in plain words.

/** «درس‌ها» on the line screen: nothing at all on a hub without the route (or while it has no lessons to give). */
@Composable
fun LineInsights(ref: String) {
    val q = rememberQuery("insights:$ref", "insights", "lines", maxAgeMs = 60_000) { gated(HubFeature.GROWTH) { lineInsights(ref) } }
    val i = q.data ?: return
    InsightsCard(i)
}

@Composable
fun InsightsCard(i: Insights) {
    val c = Divan.colors
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("درس‌ها", note = "از ${i.windowRuns} اجرای منتشرشده، با معیار «${growthMetricFa(i.metric)}»", icon = DivanIcon.LEARNING)
        Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            val best = listOfNotNull(
                i.best.hour?.let { "بهترین ساعت " + String.format(java.util.Locale.US, "%02d:00", it) },
                i.best.lengthBucket?.takeIf { it.isNotBlank() }?.let { "طول: $it" },
                i.best.voice?.takeIf { it.isNotBlank() }?.let { "گوینده: $it" },
                i.best.patternSource?.takeIf { it.isNotBlank() }?.let { "الگو از $it" },
            )
            if (best.isNotEmpty()) FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                for (b in best) Text(plain(b), style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.goldInk, modifier = Modifier.clip(RoundedCornerShape(8.dp)).background(c.softGold).padding(horizontal = 10.dp, vertical = 5.dp))
            }
            if (i.lessonsFa.isEmpty()) Text("هنوز درسی نیست؛ بعد از چند اجرای منتشرشده میاید.", style = Divan.type.caption, color = c.textMuted)
            else Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                for (l in i.lessonsFa) Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.Top) {
                    DIcon(DivanIcon.LEARNING, size = 16.dp, tint = c.learning)
                    Para(l, Modifier.weight(1f), style = Divan.type.small, color = c.textPrimary)
                }
            }
            if (i.topHooks.isNotEmpty()) Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("بهترین جمله‌های شروع", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
                i.topHooks.forEachIndexed { n, h ->
                    Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(c.tile).padding(10.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text("${n + 1}", style = Divan.type.figureSmall, color = c.textMuted)
                        Para(h, Modifier.weight(1f), style = Divan.type.small, color = c.textPrimary)
                    }
                }
            }
            i.updatedAt?.let { Text("به‌روز شد ${ago(it)}", style = Divan.type.micro, color = c.textMuted) }
        }
    }
}
