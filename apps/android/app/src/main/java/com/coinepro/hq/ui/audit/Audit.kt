package com.coinepro.hq.ui.audit

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.actorFa
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.designsystem.CompanyMark
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.Loadable
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.refresher

/** The audit ledger: append-only and hash-chained; the verification result sits on top. */
@Composable
fun AuditScreen() {
    val c = Divan.colors
    val ctx = androidx.compose.ui.platform.LocalContext.current
    val v = rememberQuery("audit:verify", "audit", maxAgeMs = 300_000) { auditVerify() }
    val q = rememberQuery("audit:list", "audit") { audit(100) }
    val r = refresher(v, q)
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item {
            PageHeader("دفتر Audit", eyebrow = "هر اقدام، با زنجیره‌ی hash") {
                val rows = q.data?.items.orEmpty()
                if (rows.isNotEmpty()) com.coinepro.hq.ui.owner.ExportButton {
                    com.coinepro.hq.ui.owner.shareCsv(ctx, "audit.csv", listOf("seq", "at", "actor", "action", "class", "target", "company", "step_up", "summary"),
                        rows.map { e -> listOf(e.seq, e.at, e.actor.code, e.action, e.actionClass, e.target.values.filterNotNull().joinToString(" "), e.company, if (e.stepUp) "yes" else "", e.summary) })
                }
            }
        }
        item {
            Loadable(v, skeleton = { Skeleton(Modifier.fillMaxWidth().height(72.dp), radius = 14.dp) }) { x ->
                HqCard(Modifier.fillMaxWidth(), color = if (x.ok) c.softPositive else c.softNegative) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        DIcon(if (x.ok) DivanIcon.SEAL else DivanIcon.URGENT, tint = if (x.ok) c.positive else c.negative)
                        Column(Modifier.weight(1f)) {
                            Text(if (x.ok) "زنجیره سالم است" else "زنجیره شکسته است", style = Divan.type.bodyStrong)
                            Text(
                                buildAnnotatedString {
                                    append("${x.checked} ردیف بررسی شد، ${ago(x.verifiedAt)}")
                                    x.firstBadSeq?.let { append("؛ اولین ردیف خراب: "); fig(it.toString()) }
                                },
                                style = Divan.type.caption, color = c.textSecondary,
                            )
                        }
                        Pill(when (x.anchor) { "ok" -> "لنگر سالم"; "mismatch" -> "لنگر ناجور"; else -> "بی‌لنگر" }, when (x.anchor) { "ok" -> Tone.POS; "mismatch" -> Tone.NEG; else -> Tone.NEUTRAL })
                    }
                }
            }
        }
        item {
            Loadable(q) { page ->
                HqCard(Modifier.fillMaxWidth(), padding = PaddingValues(horizontal = 14.dp, vertical = 6.dp)) {
                    page.items.forEachIndexed { i, e ->
                        if (i > 0) HorizontalDivider(color = c.lineDivider)
                        Column(Modifier.fillMaxWidth().padding(vertical = 10.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                Fig("#${e.seq}", style = Divan.type.figureSmall, color = c.textMuted)
                                Fig(e.action, style = Divan.type.figure, modifier = Modifier.weight(1f))
                                if (e.stepUp) DIcon(DivanIcon.LOCK, size = 14.dp, tint = c.goldInk, label = "با passkey")
                                Pill(e.actionClass, Tone.NEUTRAL, figure = true)
                            }
                            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                CompanyMark(e.company, height = 11.dp, mono = true, ink = c.textMuted)
                                Text(actorFa(e.actor), style = Divan.type.micro, color = c.textSecondary)
                                e.target["ref"]?.let { Fig(it, style = Divan.type.figureSmall, color = c.goldInk) }
                                Text(ago(e.at), style = Divan.type.micro, color = c.textMuted, modifier = Modifier.weight(1f))
                            }
                        }
                    }
                }
            }
        }
    }
}
