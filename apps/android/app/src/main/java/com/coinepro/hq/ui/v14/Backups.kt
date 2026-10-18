package com.coinepro.hq.ui.v14

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.format.instant
import com.coinepro.hq.core.format.until
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.rememberQuery

private val DEST_FA = mapOf("gdrive" to "Google Drive (حساب Pro تو)", "hetzner" to "Hetzner Object Storage", "local" to "خود سرور")

/** Backups at a glance (contract §18.9): hourly encrypted snapshots, continuous WAL, where they go, and the weekly
 *  restore test. Stale past two hours is a problem whatever the last run said (protocol PR-070). */
@Composable
fun BackupsCard(modifier: Modifier = Modifier) {
    val c = Divan.colors
    val q = rememberQuery("backups", "backups", maxAgeMs = 120_000) { backups() }
    val b = q.data ?: return Skeleton(modifier.fillMaxWidth().height(200.dp), radius = 16.dp)
    val last = instant(b.hourly.lastAt)
    val healthy = b.hourly.ok && last != null && com.coinepro.hq.core.format.HqClock.millis() - last.toEpochMilli() <= 2 * 3_600_000
    HqCard(modifier.fillMaxWidth()) {
        SectionTitle("پشتیبان‌گیری", note = "ساعتی و رمزنگاری‌شده، به‌علاوه‌ی WAL پیوسته برای بازگشت به هر دقیقه") {
            Pill(if (healthy) "سالم" else "مشکل", if (healthy) Tone.POS else Tone.NEG, dot = true)
        }
        if (b.encryption.isNotBlank()) Fig(b.encryption, style = Divan.type.figureSmall, color = c.textMuted)
        Column(Modifier.padding(vertical = 10.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Box3("آخرین backup ساعتی", ago(b.hourly.lastAt), "بعدی: ${until(b.hourly.nextAt)}، ${bytes(b.hourly.sizeBytes)}", Modifier.weight(1f))
                Box3("عقب‌ماندگی WAL", "${b.wal.lagS}s", "بازگشت تا هر دقیقه روی سرور", Modifier.weight(1f), figure = true)
            }
            Box3(
                "آخرین تست بازیابی", "${if (b.restoreTest.ok) "قبول" else "رد"}، ${ago(b.restoreTest.lastAt)}", b.restoreTest.notes, Modifier.fillMaxWidth(),
                valueColor = if (b.restoreTest.ok) c.positive else c.negative,
            )
        }
        b.destinations.forEachIndexed { i, d ->
            if (i > 0) HorizontalDivider(color = c.lineDivider)
            Row(Modifier.padding(vertical = 9.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                DIcon(if (d.key == "gdrive") DivanIcon.GLOBE else DivanIcon.SERVER, size = 16.dp, tint = if (d.configured) c.positive else c.textMuted)
                Text(DEST_FA[d.key] ?: d.key, style = Divan.type.small, modifier = Modifier.weight(1f))
                when {
                    d.configured -> Fig(bytes(d.usedBytes) + (d.quotaBytes?.let { " / " + bytes(it) } ?: ""), style = Divan.type.figureSmall, color = c.textSecondary)
                    d.key == "gdrive" -> Fig("make gdrive-auth", style = Divan.type.figureSmall, color = c.textMuted)
                    else -> Text("خاموش", style = Divan.type.micro, color = c.textMuted)
                }
            }
        }
        Text(
            "نگهداری: ${b.retention.hourly} ساعتی، ${b.retention.daily} روزانه، ${b.retention.monthly} ماهانه، ${b.retention.yearly} سالانه. بازیابی فقط در ترمینال خودت." +
                if (!b.openbaoSnapshot.ok) " snapshot گاوصندوق رمزها منتظر توکن تو است." else "",
            style = Divan.type.micro, color = c.textMuted, modifier = Modifier.padding(top = 6.dp),
        )
    }
}

@Composable
private fun Box3(label: String, value: String, sub: String, modifier: Modifier, figure: Boolean = false, valueColor: androidx.compose.ui.graphics.Color? = null) {
    val c = Divan.colors
    Column(modifier.clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Text(label, style = Divan.type.micro, color = c.textMuted)
        if (figure) Fig(value, style = Divan.type.figure.copy(fontWeight = FontWeight.SemiBold), color = valueColor ?: c.textPrimary)
        else Text(value, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = valueColor ?: c.textPrimary)
        Text(sub, style = Divan.type.micro, color = c.textMuted, maxLines = 2)
    }
}
