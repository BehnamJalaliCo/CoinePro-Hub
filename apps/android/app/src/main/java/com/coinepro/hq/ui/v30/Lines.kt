package com.coinepro.hq.ui.v30

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.channelHintFa
import com.coinepro.hq.core.data.channelKindOf
import com.coinepro.hq.core.data.lineRunStateFa
import com.coinepro.hq.core.data.lineRunStateTone
import com.coinepro.hq.core.data.platformFa
import com.coinepro.hq.core.data.platformIcon
import com.coinepro.hq.core.data.scheduleFa
import com.coinepro.hq.core.data.stepsLineFa
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.format.jTime
import com.coinepro.hq.core.format.jWeekday
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.Line
import com.coinepro.hq.core.net.LineChannel
import com.coinepro.hq.core.net.LineTemplate
import com.coinepro.hq.core.net.gated
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v29.IconTile
import com.coinepro.hq.ui.v29.Para
import com.coinepro.hq.ui.v29.plain
import com.coinepro.hq.ui.v29.served

// Contract §30 ⟨1.12⟩: the company page's «خط تولید» tab: the company's lines, and «خط تازه» from a template.

/** The company's lines (the hub without the routes answers nothing: the tab then says so). */
@Composable
fun rememberCompanyLines(code: String) = rememberQuery("lines:$code", "lines", maxAgeMs = 30_000) { gated(HubFeature.LINES) { companyLines(code) } }

/** The company's «خط تولید» tab: every line with its platform, state, mode, next run and last run; «خط تازه» opens the template gallery. */
@Composable
fun CompanyLines(code: String) {
    val nav = LocalNav.current
    val q = rememberCompanyLines(code)
    val has = served(HubFeature.LINES)
    var gallery by rememberSaveable { mutableStateOf(false) }
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        SectionTitle("خط تولید", note = "محتوا را یک بار تنظیم میکنی؛ خط خودش میسازد و منتشر میکند") {
            if (has) HqButton("خط تازه", { gallery = true }, variant = BtnVariant.PRIMARY, size = BtnSize.SM, icon = DivanIcon.ADD)
        }
        val list = q.data
        when {
            !has -> Empty("خط تولید با به‌روزرسانی بعدی هاب میاید", icon = DivanIcon.VIDEO)
            list == null && q.error != null -> ErrorBlock(q.error, { q.refresh() })
            list == null -> Skeleton(Modifier.fillMaxWidth().height(110.dp), radius = 16.dp)
            list.isEmpty() -> Empty(
                "هنوز خطی نساخته‌ای", icon = DivanIcon.VIDEO, body = "از یک قالب شروع کن؛ هر مرحله‌اش را بعداً خودت عوض میکنی.",
                action = { HqButton("خط تازه", { gallery = true }, variant = BtnVariant.PRIMARY, icon = DivanIcon.ADD) },
            )
            else -> {
                for (l in list) LineCard(l) { nav.go("lines/${l.ref}") }
            }
        }
        if (has) HqButton("اجراهای امروز و هفته", { nav.go("campaign-calendar") }, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.PLANNER)
    }
    if (gallery) com.coinepro.hq.ui.v14.HqSheet({ gallery = false }, "خط تازه", sub = "یک قالب بردار؛ مرحله‌هایش بعداً با خودت.") {
        TemplateGallery(code) { ref -> gallery = false; nav.go("lines/$ref") }
    }
}

/** One line in the list. */
@Composable
fun LineCard(l: Line, onClick: () -> Unit) {
    val c = Divan.colors
    HqCard(Modifier.fillMaxWidth(), onClick = onClick) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            IconTile(platformIcon(l.platform), c.goldInk, c.softGold)
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text(plain(l.nameFa?.takeIf { it.isNotBlank() } ?: l.titleFa), style = Divan.type.bodyStrong, maxLines = 2)
                Text(plain(platformFa(l.platform) + (if (l.channel.subject.isNotBlank()) "، ${l.channel.subject}" else "")), style = Divan.type.caption, color = c.textMuted, maxLines = 1)
            }
        }
        LinePills(l, Modifier.padding(top = 10.dp))
        Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(plain(scheduleFa(l.schedule)), style = Divan.type.caption, color = c.textSecondary)
            l.nextAt?.let { Text(plain("اجرای بعدی: ${jWeekday(it)}، ${jTime(it)}"), style = Divan.type.caption, color = c.textSecondary) }
            l.lastRun?.takeIf { it.state.isNotBlank() }?.let { r ->
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("آخرین اجرا", style = Divan.type.caption, color = c.textMuted)
                    Pill(lineRunStateFa(r.state), lineRunStateTone(r.state), dot = true)
                    if (r.at != null) Text(ago(r.at), style = Divan.type.caption, color = c.textMuted)
                }
            }
        }
    }
}

/** The templates (what the hub seeds): the gallery reads them once and keeps them for a while. */
@Composable
fun rememberTemplates() = rememberQuery("line-templates", "lines", maxAgeMs = 300_000) { gated(HubFeature.LINES) { lineTemplates() } }

/**
 * The template gallery: each template with its platform, the steps in one summary and what it makes; one tap picks it and asks only
 * for the line's name and its channel. [onCreated] gets the new line's ref (a `draft`). [picked0] opens the form on a template.
 */
@Composable
fun TemplateGallery(code: String, picked0: LineTemplate? = null, onCreated: (String) -> Unit) {
    val q = rememberTemplates()
    var picked by rememberSaveable { mutableStateOf<String?>(picked0?.key) }
    val list = q.data
    val chosen = list?.firstOrNull { it.key == picked } ?: picked0
    when {
        chosen != null -> NewLineForm(code, chosen, onBack = { picked = null }, onCreated = onCreated)
        list == null && q.error != null -> ErrorBlock(q.error, { q.refresh() })
        list == null -> Skeleton(Modifier.fillMaxWidth().height(160.dp), radius = 16.dp)
        list.isEmpty() -> Empty("هنوز قالبی نیست", icon = DivanIcon.VIDEO)
        else -> TemplateList(list) { picked = it.key }
    }
}

/** The gallery's cards (no form): a template's title, platform, its steps and what comes out. */
@Composable
fun TemplateList(list: List<LineTemplate>, onPick: (LineTemplate) -> Unit) {
    val c = Divan.colors
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        for (t in list) HqCard(Modifier.fillMaxWidth(), color = c.card, onClick = { onPick(t) }) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                IconTile(platformIcon(t.platform), c.goldInk, c.softGold)
                Column(Modifier.weight(1f)) {
                    Text(plain(t.titleFa), style = Divan.type.bodyStrong)
                    Text(plain("${platformFa(t.platform)}، ${t.steps.size} مرحله"), style = Divan.type.caption, color = c.textMuted)
                }
            }
            StepChips(t.steps.filter { it.enabled }.map { it.kind }, Modifier.padding(top = 10.dp))
            if (t.outputsFa.isNotBlank()) Para(t.outputsFa, Modifier.padding(top = 8.dp), style = Divan.type.caption, color = c.textSecondary)
        }
    }
}

/** The last question: the line's name and its channel; then the draft is made and opened. */
@Composable
fun NewLineForm(code: String, t: LineTemplate, onBack: () -> Unit, onCreated: (String) -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val action = rememberAction()
    var title by rememberSaveable(t.key) { mutableStateOf(t.titleFa) }
    var subject by rememberSaveable(t.key) { mutableStateOf("") }
    val c = Divan.colors
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            IconTile(platformIcon(t.platform), c.goldInk, c.softGold)
            Column(Modifier.weight(1f)) {
                Text(plain(t.titleFa), style = Divan.type.bodyStrong)
                Text(plain(platformFa(t.platform)), style = Divan.type.caption, color = c.textMuted)
            }
            HqButton("قالب دیگر", onBack, variant = BtnVariant.GHOST, size = BtnSize.SM)
        }
        Text(plain(stepsLineFa(t.steps)), style = Divan.type.caption, color = c.textSecondary)
        Text("نام خط", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
        HqTextField(title, { title = it }, "مثلاً ریلز طلای تریدیار", Modifier.fillMaxWidth(), maxLength = 120)
        Text("کانال", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
        HqTextField(subject, { subject = it }, channelHintFa(t.platform), Modifier.fillMaxWidth(), maxLength = 120)
        Text("خط تازه پیش‌نویس است: هر انتشارش اول با مُهر تو میرود.", style = Divan.type.caption, color = c.textMuted)
        HqButton("بساز", {
            action.run {
                val made = env.api.newLine(code, t.key, t.platform, LineChannel(channelKindOf(t.platform), subject.trim()), title.trim())
                env.cache.invalidate("lines")
                toasts.ok("خط ساخته شد؛ مرحله‌هایش را ببین و عوض کن.")
                onCreated(made.ref)
            }
        }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, icon = DivanIcon.ADD, enabled = title.trim().length >= 2, loading = action.busy)
    }
}
