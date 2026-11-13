package com.coinepro.hq.ui.playbook

import android.content.Context
import android.content.Intent
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.core.content.FileProvider
import com.coinepro.hq.core.data.LIBRARY_STATES
import com.coinepro.hq.core.data.PB_PLATFORMS
import com.coinepro.hq.core.data.changeLineFa
import com.coinepro.hq.core.data.companiesLineFa
import com.coinepro.hq.core.data.exportFileName
import com.coinepro.hq.core.data.faNum
import com.coinepro.hq.core.data.pbPlatformFa
import com.coinepro.hq.core.data.pbPlatformLineFa
import com.coinepro.hq.core.data.statsLineFa
import com.coinepro.hq.core.data.stepKindFa
import com.coinepro.hq.core.data.stepKindIcon
import com.coinepro.hq.core.data.stepSeatFa
import com.coinepro.hq.core.data.stepToolFa
import com.coinepro.hq.core.data.versionFa
import com.coinepro.hq.core.data.versionStateFa
import com.coinepro.hq.core.data.versionsOf
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.jDate
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.FlowStep
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.Playbook
import com.coinepro.hq.core.net.PlaybookDiff
import com.coinepro.hq.core.net.gated
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Expand
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.ModelMark
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.ScrollRow
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.Text
import com.coinepro.hq.designsystem.continuity
import com.coinepro.hq.designsystem.facts
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.look.Fold
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v29.Para
import com.coinepro.hq.ui.v29.plain
import com.coinepro.hq.ui.v29.served
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import java.io.File
import java.util.UUID

// Contract §59.1–§59.3 ⟨1.37⟩: «کتابخانه‌ی کارگروه‌ها». Each tested working group as a pattern with versions: its card (name and goal,
// platform, version, the companies that run it, the average cost, time and success of a run), its flow step by step (who, with which
// helper or model at what effort, what it takes and leaves, its rules), the package one run hands over, the lessons it learnt, its
// versions (what changed, compare two, «استفاده از این نسخه», a new version), and what can be done with it (copy for another platform,
// export as a file, import one, adapt it in a new session, put it aside). The form «در شرکت دیگر به کار ببر» is Use.kt.

/** The library with its filters, as the hub answers it (a hub before §59.1 answers the whole list: the phone filters it too). */
@Composable
internal fun rememberLibrary(q: String, platform: String?, state: String?, company: String?) =
    rememberQuery("library59:$q:$platform:$state:$company", "playbooks", "groups", maxAgeMs = 20_000) {
        gated(HubFeature.PLAYBOOKS) { library59(state, platform, company, q) }
    }

/** One playbook as the library's card: its name and goal, platform, version and state, who runs it, and one line of its figures. */
@Composable
internal fun LibraryCard(pb: Playbook, onClick: () -> Unit) {
    val c = Divan.colors
    HqCard(Modifier.fillMaxWidth().continuity("playbook/${pb.ref}").testTag("library-card"), onClick = onClick, onClickLabel = "باز کن") {
        Row(verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Box(Modifier.size(36.dp).clip(CircleShape).background(c.tile), contentAlignment = Alignment.Center) {
                DIcon(platformIcon(pb.platform), size = 18.dp, tint = if (pb.sealed) c.silverInk else c.textMuted)
            }
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                Text(plain(pb.titleFa.ifBlank { "کارگروه بی‌نام" }), style = Divan.type.bodyStrong, color = c.textPrimary, maxLines = 2, overflow = TextOverflow.Ellipsis)
                if (pb.purposeFa.isNotBlank()) Text(plain(pb.purposeFa), style = Divan.type.caption, color = c.textSecondary, maxLines = 2, overflow = TextOverflow.Ellipsis)
            }
            PlaybookState(pb.state)
        }
        FlowRow(Modifier.padding(top = 10.dp), horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Pill(pbPlatformFa(pb.platform), Tone.NEUTRAL)
            Pill(versionFa(pb.version), Tone.NEUTRAL)
            if (pb.draftVersion != null) Pill("${versionFa(pb.draftVersion)} در راه", Tone.GOLD)
        }
        Text(
            remember(pb) { facts(companiesLineFa(pb.companiesFa, pb.members.size.coerceAtLeast(pb.stats.companies)), statsLineFa(pb.stats)) },
            style = Divan.type.micro, color = c.textMuted, maxLines = 2, overflow = TextOverflow.Ellipsis, modifier = Modifier.padding(top = 8.dp),
        )
    }
}

private fun platformIcon(p: String): DivanIcon = when (p) {
    "instagram" -> DivanIcon.VIDEO
    "youtube" -> DivanIcon.VIDEO
    "telegram" -> DivanIcon.SEND
    "site" -> DivanIcon.GLOBE
    else -> DivanIcon.DEPARTMENT
}

/** The library's filters: platform, state and company, each a row of chips (the first chip of each is «همه»). */
@Composable
internal fun LibraryFilters(
    platform: String?, onPlatform: (String?) -> Unit, state: String?, onState: (String?) -> Unit,
    company: String?, onCompany: (String?) -> Unit, companies: List<Pair<String, String>>,
) {
    Column(Modifier.testTag("library-filters"), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        ScrollRow {
            FilterChip("همه‌ی پلتفرم‌ها", platform == null, { onPlatform(null) })
            for (p in PB_PLATFORMS.filter { it != "any" }) FilterChip(pbPlatformFa(p), platform == p, { onPlatform(if (platform == p) null else p) })
        }
        ScrollRow {
            FilterChip("هر وضعی", state == null, { onState(null) })
            for ((k, fa) in LIBRARY_STATES) FilterChip(fa, state == k, { onState(if (state == k) null else k) })
        }
        if (companies.isNotEmpty()) ScrollRow {
            FilterChip("همه‌ی شرکت‌ها", company == null, { onCompany(null) })
            for ((code, name) in companies) FilterChip(name, company == code, { onCompany(if (company == code) null else code) })
        }
    }
}

// ------------------------------------------------------------------ the flow --
/** §59.2 the flow, step by step: each step's number, name and seat, its helper or model and effort; opened, its in and out and rules. */
@Composable
internal fun FlowSection(pb: Playbook) {
    val c = Divan.colors
    var open by rememberSaveable(pb.ref, pb.version) { mutableStateOf<String?>(null) }
    HqCard(Modifier.fillMaxWidth().testTag("playbook-flow")) {
        SectionTitle("روند، قدم‌به‌قدم", note = "${faNum(pb.steps.size)} قدم، به همین ترتیب")
        Column(Modifier.padding(top = 8.dp), verticalArrangement = Arrangement.spacedBy(0.dp)) {
            pb.steps.forEachIndexed { i, s ->
                if (i > 0) HorizontalDivider(color = c.lineDivider)
                StepRow(pb, i + 1, s, open == s.key) { open = if (open == s.key) null else s.key }
            }
        }
    }
}

@Composable
private fun StepRow(pb: Playbook, n: Int, s: FlowStep, open: Boolean, onToggle: () -> Unit) {
    val c = Divan.colors
    val tool = remember(s) { stepToolFa(s.helper, s.model, s.effort) }
    Column(Modifier.fillMaxWidth().clickable(role = Role.Button, onClickLabel = if (open) "ببند" else "باز کن", onClick = onToggle).padding(vertical = 10.dp)) {
        Row(verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Box(Modifier.size(26.dp).clip(CircleShape).background(c.tile), contentAlignment = Alignment.Center) {
                Text(faNum(n), style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = c.silverInk)
            }
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                Text(plain(s.titleFa.ifBlank { stepKindFa(s.kind) }), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    DIcon(stepKindIcon(s.kind), size = 13.dp, tint = c.textMuted)
                    Text(
                        remember(s, pb) { facts(stepSeatFa(pb, s).takeIf { s.seat.isNotBlank() }, tool) },
                        style = Divan.type.micro, color = c.textSecondary, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f, fill = false),
                    )
                    ToolMark(s)
                }
            }
            if (s.gate == "ask") Pill("با تأیید تو", Tone.GOLD)
            DIcon(DivanIcon.CHEVRON, size = 14.dp, tint = c.textMuted)
        }
        Expand(open) {
            Column(Modifier.padding(start = 36.dp, top = 8.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                if (s.inputFa.isNotBlank()) InOut("میگیرد", s.inputFa)
                if (s.outputFa.isNotBlank()) InOut("میدهد", s.outputFa)
                if (s.rulesFa.isNotEmpty()) {
                    Text("قاعده‌ی این قدم", style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = c.textMuted)
                    for (r in s.rulesFa) RuleLine(r)
                }
                if (s.maxAttempts > 1) Text("اگر نشد تا ${faNum(s.maxAttempts)} بار دوباره", style = Divan.type.micro, color = c.textMuted)
            }
        }
    }
}

/** The helper's or the model's logo beside a step (ChatGPT, Google, Anthropic); nothing for the hub's own code. */
@Composable
private fun ToolMark(s: FlowStep) {
    val provider = when {
        s.helper == "gpt" -> "openai"
        s.helper == "gemini" || s.helper == "aistudio" || s.model?.startsWith("gemini") == true -> "google"
        s.model?.startsWith("claude") == true || s.helper == "workshop" -> "anthropic"
        s.helper == "deepseek" -> "deepseek"
        else -> null
    } ?: return
    ModelMark(s.model, provider = provider, size = 12.dp)
}

@Composable
private fun InOut(label: String, text: String) {
    val c = Divan.colors
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(label, style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = c.textMuted, modifier = Modifier.width(44.dp))
        Para(text, Modifier.weight(1f), style = Divan.type.caption, color = c.textSecondary)
    }
}

/** §59.1 what one run hands over: each file with its name in the owner's words. */
@Composable
internal fun PackageSection(pb: Playbook) {
    val c = Divan.colors
    HqCard(Modifier.fillMaxWidth().testTag("playbook-package")) {
        SectionTitle("بسته‌ای که هر روز میسازد", note = "یک خروجی، همه با هم")
        FlowRow(Modifier.padding(top = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            for (f in pb.`package`) Row(
                Modifier.clip(RoundedCornerShape(10.dp)).background(c.tile).padding(horizontal = 10.dp, vertical = 6.dp),
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                DIcon(fileIcon(f.name), size = 14.dp, tint = c.silverInk)
                Column {
                    Text(plain(f.titleFa.ifBlank { f.name }), style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, maxLines = 1)
                    if (f.titleFa.isNotBlank() && f.name.isNotBlank()) Text(f.name, style = Divan.type.micro, color = c.textMuted, maxLines = 1)
                }
            }
        }
    }
}

private fun fileIcon(name: String): DivanIcon = when (name.substringAfterLast('.', "").lowercase()) {
    "mp4", "mov", "webm" -> DivanIcon.VIDEO
    "jpg", "jpeg", "png", "webp" -> DivanIcon.IMAGE
    "wav", "mp3", "m4a", "ogg" -> DivanIcon.MIC
    else -> DivanIcon.REPORT
}

/** §59.1 the lessons, folded: each what happened, why, what fixed it and the rule it left. */
@Composable
internal fun LessonsFold(pb: Playbook) {
    val c = Divan.colors
    Fold("درس‌ها", remember(pb.lessons.size) { facts("${faNum(pb.lessons.size)} درس", "هر کدام قاعده‌ی قدم خودش شده") }, tag = "playbook-lessons") {
        pb.lessons.forEachIndexed { i, l ->
            if (i > 0) HorizontalDivider(color = c.lineDivider)
            Column(Modifier.padding(vertical = 6.dp), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                Text(plain("${faNum(l.n.takeIf { it > 0 } ?: (i + 1))}. ${l.titleFa}"), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                if (l.causeFa.isNotBlank()) Para("علت: ${l.causeFa}", style = Divan.type.caption, color = c.textSecondary)
                if (l.fixFa.isNotBlank()) Para("رفع: ${l.fixFa}", style = Divan.type.caption, color = c.textSecondary)
                if (l.ruleFa.isNotBlank()) Row(
                    Modifier.clip(RoundedCornerShape(8.dp)).background(c.tile).padding(horizontal = 8.dp, vertical = 4.dp),
                    verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    DIcon(DivanIcon.SEAL, size = 12.dp, tint = c.silverInk)
                    Para(l.ruleFa, style = Divan.type.micro, color = c.textPrimary)
                }
            }
        }
    }
}

// --------------------------------------------------------------- the versions --
/**
 * §59.1 the versions, newest first: each with its state, date, how many companies run it and what changed; «باز کن» for another one,
 * «استفاده از این نسخه» for a sealed one a member is not on, «مقایسه», and «نسخه‌ی تازه» (a draft of the next version) on a sealed
 * playbook without one. A hub before §59.1 has only the playbook itself as its one version (no actions).
 */
@Composable
internal fun VersionsSection(pb: Playbook, here: Int, onOpen: (Int) -> Unit, onCompare: () -> Unit, onUse: (Int) -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val versions = remember(pb) { versionsOf(pb) }
    val library = served(HubFeature.LIBRARY) && pb.versions.isNotEmpty()
    val revise = rememberAction()
    HqCard(Modifier.fillMaxWidth().testTag("playbook-versions")) {
        SectionTitle("نسخه‌ها", note = if (versions.size > 1) "${faNum(versions.size)} نسخه" else null) {
            if (library && versions.size > 1) HqButton("مقایسه", onCompare, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.FILTER)
        }
        Column(Modifier.padding(top = 6.dp)) {
            versions.forEachIndexed { i, v ->
                if (i > 0) HorizontalDivider(color = c.lineDivider)
                var more by rememberSaveable(pb.ref, v.version) { mutableStateOf(false) }
                Column(Modifier.fillMaxWidth().padding(vertical = 10.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text(versionFa(v.version), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                        val (fa, tone) = versionStateFa(v.state)
                        Pill(fa, tone)
                        if (v.version == here) Pill("همین صفحه", Tone.NEUTRAL)
                        Box(Modifier.weight(1f))
                        Text(remember(v) { facts(v.at?.let { jDate(it) }, if (v.members > 0) "${faNum(v.members)} شرکت" else null) }, style = Divan.type.micro, color = c.textMuted, maxLines = 1)
                    }
                    val lines = v.changelogFa
                    if (lines.isNotEmpty()) {
                        for (l in if (more) lines else lines.take(3)) Para("• $l", style = Divan.type.caption, color = c.textSecondary)
                        if (lines.size > 3 && !more) Text(
                            "${faNum(lines.size - 3)} تغییر دیگر", style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = c.silverInk,
                            modifier = Modifier.clip(RoundedCornerShape(6.dp)).clickable(role = Role.Button) { more = true }.padding(vertical = 2.dp),
                        )
                    } else if (v.version == 1) Text("نسخه‌ی اول", style = Divan.type.micro, color = c.textMuted)
                    if (library) Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                        if (v.version != here) HqButton("باز کن", { onOpen(v.version) }, variant = BtnVariant.TEXT, size = BtnSize.SM)
                        if (v.state == "sealed" && pb.members.any { (it.version ?: pb.version) != v.version }) HqButton("استفاده از این نسخه", { onUse(v.version) }, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.REFRESH)
                    }
                }
            }
        }
        if (library && pb.sealed && pb.draftVersion == null) HqButton("نسخه‌ی تازه", {
            revise.run {
                val d = env.api.revisePlaybook(pb.ref, UUID.randomUUID().toString())
                env.cache.invalidate(*PLAYBOOK_TAGS)
                toasts.ok("${versionFa(d.version)} پیش‌نویس شد؛ نسخه‌ی مُهرشده کار خودش را میکند.")
                onOpen(d.version)
            }
        }, Modifier.fillMaxWidth().padding(top = 4.dp), variant = BtnVariant.SECONDARY, size = BtnSize.MD, icon = DivanIcon.ADD, loading = revise.busy)
        pb.draftVersion?.let { d ->
            if (d != here) Row(
                Modifier.fillMaxWidth().padding(top = 6.dp).clip(RoundedCornerShape(12.dp)).background(c.tile).clickable(role = Role.Button) { onOpen(d) }.padding(12.dp),
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                DIcon(DivanIcon.EDIT, size = 16.dp, tint = c.silverInk)
                Text("${versionFa(d)} پیش‌نویس است؛ بازش کن، بگو چه عوض شود و مُهرش کن.", style = Divan.type.caption, color = c.textSecondary, modifier = Modifier.weight(1f))
                DIcon(DivanIcon.NEXT, size = 14.dp, tint = c.textMuted)
            }
        }
    }
}

/** «مقایسه»: two versions picked, and what changed between them, line by line (the hub's code compares). */
@Composable
internal fun CompareBody(pb: Playbook) {
    val c = Divan.colors
    val versions = remember(pb) { versionsOf(pb).map { it.version }.sorted() }
    var a by rememberSaveable(pb.ref) { mutableStateOf(versions.getOrNull(versions.size - 2) ?: 1) }
    var b by rememberSaveable(pb.ref) { mutableStateOf(versions.lastOrNull() ?: 1) }
    val q = rememberQuery("playbook-compare:${pb.ref}:$a:$b", "playbooks", maxAgeMs = 60_000) { gated(HubFeature.LIBRARY) { playbookCompare(pb.ref, a, b) } }
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("از", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textMuted)
        ScrollRow { for (v in versions) FilterChip(versionFa(v), a == v, { a = v }) }
        Text("تا", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textMuted)
        ScrollRow { for (v in versions) FilterChip(versionFa(v), b == v, { b = v }) }
        val d: PlaybookDiff? = q.data
        when {
            a == b -> Text("دو نسخه‌ی متفاوت را انتخاب کن.", style = Divan.type.small, color = c.textSecondary)
            d == null && q.error != null -> Text(q.error?.messageFa.orEmpty(), style = Divan.type.small, color = c.negative)
            d == null -> Skeleton(Modifier.fillMaxWidth().height(80.dp), radius = 12.dp)
            d.changes.isEmpty() -> Text("فرقی ندارند.", style = Divan.type.small, color = c.textSecondary)
            else -> Column(Modifier.testTag("compare-lines"), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                for (ch in d.changes) Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.Top) {
                    val (sign, tint) = when (ch.kind) { "added" -> "+" to c.positive; "removed" -> "−" to c.negative; else -> "~" to c.silverInk }
                    Text(sign, style = Divan.type.small.copy(fontWeight = FontWeight.Bold), color = tint)
                    Para(changeLineFa(ch), Modifier.weight(1f), style = Divan.type.caption, color = c.textPrimary)
                }
            }
        }
    }
}

/** «استفاده از این نسخه»: which member company moves to [version]; each a tap. */
@Composable
internal fun UseVersionBody(pb: Playbook, version: Int, onDone: () -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val go = rememberAction()
    var which by remember { mutableStateOf<String?>(null) }
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text("از اجرای بعد، این شرکت ${versionFa(version)} را اجرا میکند. اجرای امروز با نسخه‌ی خودش تمام میشود.", style = Divan.type.small, color = c.textSecondary)
        for (m in pb.members) {
            val now = m.version ?: pb.version
            Row(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(start = 12.dp, end = 6.dp, top = 6.dp, bottom = 6.dp),
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Column(Modifier.weight(1f)) {
                    Text(plain(m.nameFa.ifBlank { m.company }), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                    Text("الان: ${versionFa(now)}", style = Divan.type.micro, color = c.textMuted)
                }
                if (now == version) Pill("روی همین نسخه", Tone.POS)
                else HqButton("همین نسخه", {
                    which = m.company
                    go.run {
                        env.api.useVersion(pb.ref, m.company, version)
                        env.cache.invalidate(*PLAYBOOK_TAGS, "automations")
                        toasts.ok("${m.nameFa.ifBlank { m.company }} از اجرای بعد ${versionFa(version)} را اجرا میکند.")
                        onDone()
                    }
                }, variant = BtnVariant.SECONDARY, size = BtnSize.SM, loading = go.busy && which == m.company)
            }
        }
    }
}

// --------------------------------------------------------------- what to do --
/**
 * The playbook's own acts, quiet, at the page's end: «کپی برای پلتفرم دیگر», «بیرون‌بری فایل», «تطبیق در جلسه‌ی تازه» (§40.3's
 * apply) and «کنار گذاشتن». The form «در شرکت دیگر به کار ببر» is the page's main act, in its head.
 */
@Composable
internal fun PlaybookActs(pb: Playbook, onCopy: () -> Unit, onAdapt: () -> Unit, onRetire: () -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val context = LocalContext.current
    val c = Divan.colors
    val library = served(HubFeature.LIBRARY) && pb.versioned
    val export = rememberAction()
    HqCard(Modifier.fillMaxWidth().testTag("playbook-acts"), padding = PaddingValues(vertical = 4.dp)) {
        if (library) ActRow(DivanIcon.ADD, "کپی برای پلتفرم دیگر", "یوتیوب یا تلگرام از روی همین روند", onClick = onCopy)
        if (library) ActRow(DivanIcon.DOWNLOAD, "بیرون‌بری فایل", "یک فایل، بی حساب و لینک هیچ شرکتی") {
            export.run {
                val body = env.api.exportPlaybook(pb.ref, pb.version)
                withContext(Dispatchers.IO) { shareJson(context, exportFileName(pb.titleFa, pb.version), Api.jsonPretty(body)) }
                toasts.ok("فایل کارگروه آماده‌ی فرستادن است.")
            }
        }
        if (!pb.retired) ActRow(DivanIcon.MEETING, "تطبیق در جلسه‌ی تازه", "مسئول شرکت دیگر آن را با حرف تو جور میکند", onClick = onAdapt)
        if (pb.sealed) ActRow(DivanIcon.PAUSE, "کنار گذاشتن", "در همه‌ی شرکت‌ها می‌ایستد؛ چیزی پاک نمیشود", quiet = true, onClick = onRetire)
    }
}

@Composable
private fun ActRow(icon: DivanIcon, title: String, sub: String, quiet: Boolean = false, onClick: () -> Unit) {
    val c = Divan.colors
    Row(
        Modifier.fillMaxWidth().clickable(role = Role.Button, onClick = onClick).padding(horizontal = 14.dp, vertical = 11.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        DIcon(icon, size = 18.dp, tint = if (quiet) c.textMuted else c.silverInk)
        Column(Modifier.weight(1f)) {
            Text(title, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = if (quiet) c.textSecondary else c.textPrimary)
            Text(sub, style = Divan.type.micro, color = c.textMuted, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
        DIcon(DivanIcon.NEXT, size = 14.dp, tint = c.textMuted)
    }
}

/** A JSON text as a file under cache/shared, offered to any app through the system's share sheet. */
private fun shareJson(context: Context, name: String, text: String) {
    val dir = File(context.cacheDir, "shared").apply { mkdirs() }
    val file = File(dir, name).apply { writeText(text) }
    val uri = FileProvider.getUriForFile(context, "${context.packageName}.files", file)
    val send = Intent(Intent.ACTION_SEND).setType("application/json").putExtra(Intent.EXTRA_STREAM, uri).putExtra(Intent.EXTRA_SUBJECT, name)
        .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    context.startActivity(Intent.createChooser(send, "فایل کارگروه").addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
}

/** «کپی برای پلتفرم دیگر»: the platform, a new name if he wants one, and a note (with a note a session adapts it). */
@Composable
internal fun CopyBody(pb: Playbook, onDone: (Playbook, String?) -> Unit) {
    val env = LocalEnv.current
    val c = Divan.colors
    var platform by rememberSaveable(pb.ref) { mutableStateOf(PB_PLATFORMS.firstOrNull { it != pb.platform && it != "any" } ?: "youtube") }
    var title by rememberSaveable(pb.ref) { mutableStateOf("") }
    var note by rememberSaveable(pb.ref) { mutableStateOf("") }
    val key = remember(platform, title, note) { UUID.randomUUID().toString() }
    val go = rememberAction()
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("برای کدام پلتفرم؟", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textMuted)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            for (p in PB_PLATFORMS.filter { it != "any" }) FilterChip(pbPlatformFa(p), platform == p, { platform = p })
        }
        HqTextField(title, { title = it }, "نام تازه (اختیاری)", Modifier.fillMaxWidth(), maxLength = 200)
        HqTextField(note, { note = it }, "چه چیزی برای ${pbPlatformLineFa(platform)} عوض شود؟ (اختیاری)", Modifier.fillMaxWidth(), singleLine = false, minLines = 2, maxLength = 2000)
        Text(
            if (note.isBlank()) "یک پیش‌نویس تازه با همین قدم‌ها ساخته میشود؛ بعد در صفحه‌اش یا در جلسه عوضش کن و مُهر بزن."
            else "پیش‌نویس تازه ساخته میشود و مدیر رسانه‌ی هلدینگ در یک جلسه‌ی تازه آن را با یادداشت تو جور میکند.",
            style = Divan.type.micro, color = c.textMuted,
        )
        com.coinepro.hq.designsystem.SheetBar {
            com.coinepro.hq.designsystem.DecisionBar(
                "کپی کن", {
                    go.run {
                        val body = buildJsonObject {
                            put("version", JsonPrimitive(pb.version)); put("platform", JsonPrimitive(platform))
                            title.trim().ifEmpty { null }?.let { put("title_fa", JsonPrimitive(it)) }
                            note.trim().ifEmpty { null }?.let { put("note_fa", JsonPrimitive(it)) }
                        }
                        val out = env.api.copyPlaybook(pb.ref, body, key)
                        env.cache.invalidate(*PLAYBOOK_TAGS, "sessions")
                        onDone(out.playbook, out.order)
                    }
                },
                context = "کارگروه اصلی همان‌طور که هست میماند.", icon = DivanIcon.ADD,
                state = if (go.busy) com.coinepro.hq.designsystem.DecisionState.WORKING else com.coinepro.hq.designsystem.DecisionState.IDLE,
            )
        }
    }
}

/**
 * «درون‌آوری فایل»: a playbook file picked on the phone goes up to the hub, which makes a draft of it; [onDone] gets the draft. The
 * file is read as it is: a file that is no playbook is the hub's own plain refusal.
 */
@Composable
internal fun rememberImport(onDone: (Playbook) -> Unit): () -> Unit {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val pick = rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri ->
        if (uri == null) return@rememberLauncherForActivityResult
        scope.launch {
            try {
                val bytes = withContext(Dispatchers.IO) { context.contentResolver.openInputStream(uri)?.use { it.readBytes() } } ?: return@launch
                if (bytes.size > 2_000_000) { toasts.error("این فایل برای یک کارگروه بزرگ است."); return@launch }
                val up = env.api.upload("playbook.json", "application/json", bytes.size.toLong(), { bytes.inputStream() })
                val pb = env.api.importPlaybook(up.id, UUID.randomUUID().toString())
                env.cache.invalidate(*PLAYBOOK_TAGS)
                toasts.ok(pb.noteFa?.takeIf { it.isNotBlank() }?.let { "پیش‌نویس ساخته شد؛ $it" } ?: "پیش‌نویس از فایل ساخته شد.")
                onDone(pb)
            } catch (e: ApiException) {
                toasts.error(e.messageFa)
            } catch (e: kotlin.coroutines.cancellation.CancellationException) {
                throw e
            } catch (_: Exception) {
                toasts.error("فایل خوانده نشد؛ دوباره امتحان کن.")
            }
        }
    }
    return { pick.launch("application/json") }
}

/** A JSON body as an indented text (an export file a person may read). */
internal fun Api.Companion.jsonPretty(o: JsonObject): String =
    kotlinx.serialization.json.Json { prettyPrint = true }.encodeToString(JsonObject.serializer(), o)
