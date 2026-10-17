package com.coinepro.hq.ui.advisor

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.actorFa
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.format.until
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.Md
import com.coinepro.hq.designsystem.RichText
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v14.HqSheet
import com.coinepro.hq.ui.v14.Label
import com.coinepro.hq.ui.v14.LabelPill

private val INQUIRY_STATUS = mapOf(
    "open" to Label("منتظر جواب", Tone.LAPIS), "answered" to Label("جواب داده شد", Tone.POS),
    "late" to Label("دیر شده", Tone.NEG), "withdrawn" to Label("پس گرفته شد", Tone.NEUTRAL),
)

/** The advisor's formal questions to CEOs and managers (contract §18.2), answered with evidence by a due time:
 *  a header button that opens them. */
@Composable
fun InquiriesAction() {
    var open by remember { mutableStateOf(false) }
    HqButton("پرسش‌ها", { open = true }, size = BtnSize.SM, icon = DivanIcon.SEARCH)
    if (open) InquiriesSheet { open = false }
}

@Composable
private fun InquiriesSheet(onClose: () -> Unit) {
    val c = Divan.colors
    val q = rememberQuery("inquiries:HQ-ADV", "inquiries") { inquiries(from = "HQ-ADV").items }
    HqSheet(onClose, "پرسش‌های رسمی مشاور", sub = "مشاور وقتی سوابق جواب نمیدهد، از خود مدیرها میپرسد؛ جواب با شاهد میاید.") {
        val list = q.data
        when {
            list == null -> Skeleton(Modifier.fillMaxWidth().height(160.dp), radius = 12.dp)
            list.isEmpty() -> Text("پرسشی نیست.", style = Divan.type.small, color = c.textMuted)
            else -> for (x in list) {
                Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Fig(x.ref, style = Divan.type.figureSmall, color = c.textMuted)
                        Text("به ${actorFa(x.to)}", style = Divan.type.micro, color = c.textMuted)
                        Text(if (x.status == "answered") ago(x.answeredAt) else until(x.dueAt), style = Divan.type.micro, color = c.textMuted, modifier = Modifier.weight(1f))
                        LabelPill(INQUIRY_STATUS[x.status], x.status)
                    }
                    RichText(x.questionMd, style = Divan.type.body, color = c.textPrimary)
                    x.answerMd?.let { Md(it, Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(c.card).padding(10.dp)) }
                }
            }
        }
    }
}
