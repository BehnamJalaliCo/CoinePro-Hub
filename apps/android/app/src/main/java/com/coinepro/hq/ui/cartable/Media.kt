package com.coinepro.hq.ui.cartable

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.modelLabel
import com.coinepro.hq.core.format.tokens
import com.coinepro.hq.core.net.Decision
import com.coinepro.hq.core.net.EmailDraft
import com.coinepro.hq.core.net.PublishPayload
import com.coinepro.hq.core.net.RoleNewPayload
import com.coinepro.hq.core.net.SeriesPayload
import com.coinepro.hq.core.net.payloadAs
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.v17.RefChip
import com.coinepro.hq.ui.v19.Block
import com.coinepro.hq.ui.v19.CheckGrid
import com.coinepro.hq.ui.v19.ExactEmail
import com.coinepro.hq.ui.v19.KIND_FA
import com.coinepro.hq.ui.v19.PLACEMENT_FA
import com.coinepro.hq.ui.v19.PUBLISH_ERROR
import com.coinepro.hq.ui.v19.RenderPreview
import com.coinepro.hq.ui.v19.scheduleText
import com.coinepro.hq.ui.v19.shareFile
import kotlinx.coroutines.launch

// The cards of the media studio and the legal counsel (contract §22.6, §22.7), mirroring apps/web/src/components/v19/decision.tsx:
// `media_publish` (A3, its render and how each placement goes out), `media_series` (sealed on its own page, on the series digest),
// `role_new` (a role a department's manager wrote, after the overseer and its own eval) and `email_send` (the exact message).

private val WHY = mapOf(
    "one_off" to "یک‌باره است؛ یک‌باره‌ها همیشه کارت‌اند.", "check_failed" to "یک چک رد شده؛ انتشار خودکار نیست.", "not_auto" to "برنامه‌اش انتشار خودکار ندارد.",
    "no_api" to "این جای انتشار API رسمی ندارد: فایل را بردار و خودت بگذار.", "series_not_sealed" to "برنامه‌اش مُهر نیست.",
)

@Composable
private fun Fact(label: String, value: String, modifier: Modifier = Modifier, figure: Boolean = false, onClick: (() -> Unit)? = null) {
    val c = Divan.colors
    Column(modifier.clip(RoundedCornerShape(12.dp)).background(c.tile).then(if (onClick != null) Modifier.clickable(role = Role.Button, onClick = onClick) else Modifier).padding(12.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(label, style = Divan.type.micro, color = c.textMuted)
        if (figure) Fig(value, style = Divan.type.figure.copy(fontWeight = FontWeight.SemiBold), color = if (onClick != null) c.goldInk else c.textPrimary)
        else Text(value, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
    }
}

@Composable
private fun Facts(vararg xs: @Composable (Modifier) -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        for (row in xs.toList().chunked(2)) Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            for (f in row) f(Modifier.weight(1f))
            if (row.size == 1) Box(Modifier.weight(1f))
        }
    }
}

/** The payload of a §22 card. */
@Composable
fun MediaDecisionPayload(d: Decision) {
    when (d.kind) {
        "media_publish" -> PublishBlock(d)
        "media_series" -> SeriesBlock(d)
        "role_new" -> RoleBlock(d)
        "email_send" -> EmailBlock(d)
    }
}

@Composable
private fun PublishBlock(d: Decision) {
    val env = LocalEnv.current
    val nav = LocalNav.current
    val toasts = LocalToasts.current
    val ctx = LocalContext.current
    val c = Divan.colors
    val scope = rememberCoroutineScope()
    var sharing by remember { mutableStateOf(false) }
    val p = d.payloadAs(PublishPayload.serializer()) ?: return
    val manual = p.placements.any { it.via == "manual" }
    Block("انتشار رسانه") {
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            p.render?.let { r ->
                val aspect = if (r.width != null && r.height != null) "${r.width}:${r.height}" else "9:16"
                RenderPreview(r, aspect, "رندر ${p.item}", Modifier.width(120.dp))
            }
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(4.dp), itemVerticalAlignment = Alignment.CenterVertically) {
                    if (p.item.isNotBlank()) RefChip(p.item)
                    if (p.series != null) RefChip(p.series, note = "برنامه") else Text("یک‌باره", style = Divan.type.caption, color = c.textSecondary)
                    if (p.kind.isNotBlank()) Text(KIND_FA[p.kind]?.fa ?: p.kind, style = Divan.type.caption, color = c.textSecondary)
                }
                if (p.why.isNotBlank()) Text(WHY[p.why] ?: p.why, style = Divan.type.small, color = c.textPrimary)
                for (x in p.placements) Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(c.tile).padding(10.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text(PLACEMENT_FA[x.placement] ?: x.placement, style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                    Fig(x.account, style = Divan.type.figureSmall, color = c.textMuted)
                    when {
                        x.blocked != null -> Pill("${PUBLISH_ERROR[x.blocked] ?: x.blocked}؛ این بار نه", Tone.WARN, icon = DivanIcon.URGENT)
                        x.via == "manual" -> Pill("با دست تو", Tone.GOLD, icon = DivanIcon.SHARE)
                        else -> Pill("API رسمی", Tone.SILVER, icon = DivanIcon.SEND)
                    }
                }
                if (manual && p.render != null) HqButton("فایل برای گذاشتن با دست", {
                    if (!sharing) { sharing = true; scope.launch { try { shareFile(ctx, env, p.render) } catch (_: Exception) { toasts.error("فایل باز نشد.") } finally { sharing = false } } }
                }, size = BtnSize.SM, icon = DivanIcon.DOWNLOAD, loading = sharing)
            }
        }
        if (p.checks.isNotEmpty()) CheckGrid(p.checks)
        Text(
            "با مُهر، هر جا API رسمی دارد همان لحظه منتشر میشود" + (if (manual) "؛ برای استوری کانال تلگرام، مُهر یعنی خودت گذاشتی" else "") + ". اینستاگرام با برچسب ساخته‌ی هوش مصنوعی.",
            style = Divan.type.caption, color = c.textMuted,
        )
        if (p.item.isNotBlank()) HqButton("دیدن آیتم در استودیو", { nav.go("studio/${p.item}") }, size = BtnSize.SM, icon = DivanIcon.VIDEO)
    }
}

@Composable
private fun SeriesBlock(d: Decision) {
    val nav = LocalNav.current
    val c = Divan.colors
    val p = d.payloadAs(SeriesPayload.serializer()) ?: return
    Block("برنامه‌ی انتشار") {
        Facts(
            { m -> Fact("برنامه", p.series ?: "—", m, figure = true, onClick = p.series?.let { s -> { nav.go("series/$s") } }) },
            { m -> Fact("نوع", KIND_FA[p.kind]?.fa ?: p.kind.ifBlank { "—" }, m) },
            { m -> Fact("انتشار خودکار", if (p.autoPublish) "بله، اگر هر هفت چک قبول" else "نه؛ هر آیتم کارت", m) },
            { m -> Fact("سقف روزانه", p.maxPerDay?.toString() ?: "—", m) },
        )
        if (p.schedule.isNotBlank()) Text(scheduleText(p.schedule), style = Divan.type.small, color = c.textPrimary)
        if (p.targets.isNotEmpty()) FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            for (t in p.targets) Row(Modifier.clip(CircleShape).background(c.tile).padding(horizontal = 10.dp, vertical = 4.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(PLACEMENT_FA[t.placement] ?: t.placement, style = Divan.type.caption, color = c.textPrimary)
                Fig(t.account, style = Divan.type.figureSmall, color = c.textMuted)
            }
        }
        if (p.digest.isNotBlank()) Text(buildAnnotatedString {
            append("مُهر روی همین نسخه است: "); fig("digest ${p.digest.take(16)}…")
            p.version?.let { append(" · نسخه‌ی $it") }
            append(". هر ویرایش بعدی مُهر را برمیدارد.")
        }, style = Divan.type.micro, color = c.textMuted)
    }
}

@Composable
private fun RoleBlock(d: Decision) {
    val nav = LocalNav.current
    val c = Divan.colors
    val p = d.payloadAs(RoleNewPayload.serializer()) ?: return
    Block("نقش تازه") {
        Facts(
            { m -> Fact("پیش‌نویس", p.draft ?: "—", m, figure = true, onClick = p.draft?.let { r -> { nav.go("roles/$r") } }) },
            { m -> Fact("نقش", p.role ?: "—", m, figure = true) },
            { m -> Fact("مدل و فکر", "${modelLabel(p.model)} · ${p.effort ?: "—"}", m, figure = true) },
            { m -> Fact("سقف هر اجرا", p.limits?.tokensPerRun?.takeIf { it > 0 }?.let { "${tokens(it)} tok" } ?: "—", m, figure = true) },
        )
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(6.dp), itemVerticalAlignment = Alignment.CenterVertically) {
            Pill("بازبینی ناظر: ${if (p.review == "pass") "قبول" else p.review ?: "—"}", if (p.review == "pass") Tone.POS else Tone.WARN, icon = DivanIcon.OVERSEER)
            p.evalScore?.let { Pill("آزمون خودش: ${com.coinepro.hq.ui.v17.num(it)}", Tone.GOLD, icon = DivanIcon.ACADEMY) }
            p.toolsCount?.takeIf { it > 0 }?.let { Text("$it ابزار، همه داخل سقف دپارتمان", style = Divan.type.caption, color = c.textSecondary) }
            p.sha256?.let { Fig("sha256 ${it.take(12)}…", style = Divan.type.figureSmall, color = c.textMuted) }
        }
        Text("با مُهر، نقش روی سرور فعال میشود (فقط همین شرکت و دپارتمان) و میشود رویش استخدام کرد؛ هر وقت خواستی از استوری یا صفحه‌ی شرکت بازنشسته‌اش کن.", style = Divan.type.caption, color = c.textMuted)
    }
}

@Composable
private fun EmailBlock(d: Decision) {
    val c = Divan.colors
    val p = d.payloadAs(EmailDraft.serializer())?.takeIf { it.subject.isNotBlank() } ?: return
    Block("ایمیل دقیق", action = { if (p.case.isNotBlank()) RefChip(p.case, note = "پرونده") }) {
        Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(c.tile).padding(12.dp)) { ExactEmail(p) }
    }
}
