package com.coinepro.hq.ui.org

import androidx.compose.foundation.background
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.DEPT_FA
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.actorFa
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.format.jDateTime
import com.coinepro.hq.core.format.modelLabel
import com.coinepro.hq.core.format.roleFa
import com.coinepro.hq.core.format.tokens
import com.coinepro.hq.core.net.Department
import com.coinepro.hq.core.net.MODEL_CEILINGS
import com.coinepro.hq.core.net.Mandate
import com.coinepro.hq.core.net.MandateIn
import com.coinepro.hq.core.net.RoleDraft
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.Md
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.RichText
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.SegOption
import com.coinepro.hq.designsystem.Segmented
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.activity
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.v14.LabelPill
import com.coinepro.hq.ui.v16.prose
import com.coinepro.hq.ui.v17.ActorAvatar
import com.coinepro.hq.ui.v17.RefChip
import com.coinepro.hq.ui.v19.Block
import com.coinepro.hq.ui.v19.REVIEW_CHECK_19
import com.coinepro.hq.ui.v19.ROLE_GATES
import com.coinepro.hq.ui.v19.ROLE_STATE
import com.coinepro.hq.ui.v19.media
import java.util.UUID
import kotlinx.coroutines.delay

// A department by its mandate and identity (contract §22.1) and the roles its manager writes on demand (§22.5), mirroring
// apps/web/src/components/v19/org.tsx: the company page opens a department and its drafts; a draft is its own page too (roles/{ref}).

private fun lines(s: String) = s.lines().map { it.trim() }.filter { it.isNotEmpty() }

/** A department: where it starts and must arrive, what it delivers and its limits, its ceilings, its character, the team it may start
 *  with (a suggestion, never a limit) and the roles its manager wrote; the owner asks for a new one here. */
@Composable
fun DepartmentView(company: String, code: String, onRole: (String) -> Unit) {
    val c = Divan.colors
    val deps = rememberQuery("departments:$company", "companies") { departments(company) }
    val drafts = rememberQuery("roles:drafts:$company:$code", "roles") { roleDrafts(company, code) }
    var edit by rememberSaveable { mutableStateOf(false) }
    val d = deps.data?.firstOrNull { it.code == code }
    if (d == null) return if (deps.error != null) ErrorBlock(deps.error, { deps.refresh() }) else Skeleton(Modifier.fillMaxWidth().height(380.dp), radius = 12.dp)
    if (edit) return MandateEditor(company, d) { edit = false }
    val m = d.mandate
    Column(verticalArrangement = Arrangement.spacedBy(18.dp)) {
        Text("دپارتمان با مأموریت و شخصیتش تعریف میشود، نه با فهرست نقش‌ها؛ ${d.managerTitleFa} هر نقشی که کار لازم دارد مینویسد.", style = Divan.type.caption, color = c.textMuted)
        if (m == null) Empty("هنوز مأموریتی ثبت نشده", icon = DivanIcon.DEPARTMENT, action = { HqButton("بنویس", { edit = true }, size = BtnSize.SM, icon = DivanIcon.EDIT) })
        else Block("مأموریت: مبدأ و مقصد", action = { HqButton("ویرایش", { edit = true }, size = BtnSize.SM, variant = BtnVariant.TEXT, icon = DivanIcon.EDIT) }) {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    Text("مبدأ", style = Divan.type.micro, color = c.textMuted)
                    Text(prose(m.fromFa), style = Divan.type.small, color = c.textPrimary)
                }
                Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.softGold).padding(12.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    Text("مقصد", style = Divan.type.micro, color = c.goldInk)
                    Text(prose(m.toFa), style = Divan.type.small, color = c.textPrimary)
                }
                Bullets("خروجی‌ها", m.outputsFa)
                Bullets("مرزها", m.boundariesFa)
                Text("سقف ابزار و مدل (هیچ نقشی بیشتر از این نمیگیرد)", style = Divan.type.micro, color = c.textMuted)
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Pill(modelLabel(m.modelCeiling), Tone.SILVER, figure = true)
                    for (t in m.toolCeiling) Fig(t, Modifier.clip(RoundedCornerShape(6.dp)).background(c.tile).padding(horizontal = 8.dp, vertical = 2.dp), style = Divan.type.figureSmall, color = c.textSecondary)
                }
            }
        }
        d.identityMd?.takeIf { it.isNotBlank() }?.let { id ->
            Block("شخصیت دپارتمان") {
                Md(id, Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp), color = c.textPrimary)
                Text("بعد از منشور و پیش از مهارت‌ها در دستور مدیر و هر کارمند این دپارتمان میآید؛ نسخه‌اش روی هر اجرا ثبت میشود.", style = Divan.type.micro, color = c.textMuted)
            }
        }
        Block("تیم شروع (پیشنهاد، نه محدودیت)") {
            if (d.team.isEmpty()) Text("قالب برای این دپارتمان هنوز منشور شروعی ندارد؛ مدیرش هر نقشی که کار لازم داشت مینویسد.", style = Divan.type.caption, color = c.textMuted)
            else Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                for (t in d.team) Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(c.tile).padding(horizontal = 12.dp, vertical = 8.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text(t.titleFa, style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                        Fig(t.role, style = Divan.type.figureSmall, color = c.textMuted)
                        if (t.first) Pill("اول", Tone.GOLD)
                    }
                    Text(prose(t.whyFa), style = Divan.type.micro, color = c.textMuted)
                }
            }
        }
        Block("نقش‌هایی که مدیر نوشته") {
            val xs = drafts.data
            when {
                xs == null -> Skeleton(Modifier.fillMaxWidth().height(56.dp))
                xs.isEmpty() -> Text("هنوز نقشی ننوشته.", style = Divan.type.caption, color = c.textMuted)
                else -> Column(verticalArrangement = Arrangement.spacedBy(6.dp)) { for (x in xs) DraftRow(x) { onRole(x.ref) } }
            }
            if (company != "HQ" || code != "LEGAL") AskRole(company, code, onRole)
        }
    }
}

@Composable
private fun Bullets(title: String, xs: List<String>) {
    val c = Divan.colors
    if (xs.isEmpty()) return
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(title, style = Divan.type.micro, color = c.textMuted)
        for (x in xs) Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Box(Modifier.padding(top = 8.dp).size(4.dp).clip(CircleShape).background(c.textMuted))
            Text(prose(x), Modifier.weight(1f), style = Divan.type.small, color = c.textPrimary)
        }
    }
}

/** The owner's edit of a mandate and identity: 🔏 `department.mandate`, sealed on the hash of exactly what is saved. */
@Composable
fun MandateEditor(company: String, d: Department, onDone: () -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val act = activity()
    val c = Divan.colors
    val action = rememberAction()
    val m = d.mandate
    var from by rememberSaveable { mutableStateOf(m?.fromFa.orEmpty()) }
    var to by rememberSaveable { mutableStateOf(m?.toFa.orEmpty()) }
    var outputs by rememberSaveable { mutableStateOf(m?.outputsFa.orEmpty().joinToString("\n")) }
    var bounds by rememberSaveable { mutableStateOf(m?.boundariesFa.orEmpty().joinToString("\n")) }
    var tools by rememberSaveable { mutableStateOf(m?.toolCeiling.orEmpty().joinToString("\n")) }
    var model by rememberSaveable { mutableStateOf(m?.modelCeiling ?: "claude-sonnet-5-5") }
    var identity by rememberSaveable { mutableStateOf(d.identityMd.orEmpty()) }
    val ok = from.isNotBlank() && to.isNotBlank() && lines(outputs).isNotEmpty()
    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Field("مبدأ: از چه شروع میکند") { HqTextField(from, { from = it }, "", Modifier.fillMaxWidth(), singleLine = false, minLines = 2) }
        Field("مقصد: به کجا باید برسد") { HqTextField(to, { to = it }, "", Modifier.fillMaxWidth(), singleLine = false, minLines = 2) }
        Field("خروجی‌ها (هر خط یکی)") { HqTextField(outputs, { outputs = it }, "", Modifier.fillMaxWidth(), singleLine = false, minLines = 3) }
        Field("مرزها (هر خط یکی)") { HqTextField(bounds, { bounds = it }, "", Modifier.fillMaxWidth(), singleLine = false, minLines = 3) }
        // Tool names are code: written left to right, as the web's field (dir="ltr").
        Field("سقف ابزار (هر خط یک ابزار)") {
            CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) { HqTextField(tools, { tools = it }, "", Modifier.fillMaxWidth(), singleLine = false, minLines = 4, figure = true) }
        }
        Field("سقف مدل") { Segmented(MODEL_CEILINGS.map { SegOption(it, modelLabel(it)) }, model, { model = it }, Modifier.fillMaxWidth()) }
        Field("شخصیت دپارتمان (لحن، سلیقه؛ هر عضو میخواند)") { HqTextField(identity, { identity = it }, "", Modifier.fillMaxWidth(), singleLine = false, minLines = 5) }
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            HqButton("با اثر انگشت ذخیره کن", {
                val body = MandateIn(Mandate(from.trim(), to.trim(), lines(outputs), lines(bounds), lines(tools), model), identity.trim())
                action.media(toasts) {
                    env.api.putMandate(company, d, body) { a, t -> env.auth.stepUp(act, a, t) }
                    env.cache.invalidate("companies")
                    toasts.ok("ذخیره شد؛ از اجرای بعدی، مدیر و هر کارمند این دپارتمان همین شخصیت را میخوانند.")
                    onDone()
                }
            }, variant = BtnVariant.PRIMARY, icon = DivanIcon.SEAL, enabled = ok, loading = action.busy)
            HqButton("انصراف", onDone, variant = BtnVariant.GHOST)
        }
        Text("مُهر به hash همین متن بسته است.", style = Divan.type.micro, color = c.textMuted)
    }
}

@Composable
private fun Field(label: String, content: @Composable () -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(label, style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = Divan.colors.textSecondary)
        content()
    }
}

@Composable
private fun AskRole(company: String, department: String, onAsked: (String) -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val action = rememberAction()
    var key by remember { mutableStateOf(UUID.randomUUID().toString()) }
    var brief by rememberSaveable { mutableStateOf("") }
    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text("نقش تازه بخواه", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
        HqTextField(brief, { brief = it }, "مثلاً: یه تدوینگر پادکست میخوام برای نسخه‌ی صوتی تحلیل هفتگی", Modifier.fillMaxWidth(), singleLine = false, minLines = 2, maxLength = 2000)
        HqButton("بفرست به مدیر دپارتمان", {
            action.media(toasts) {
                val d = env.api.askRole(company, department, brief.trim(), key)
                env.cache.invalidate("roles", "stories", "decisions")
                toasts.ok("خواسته رسید (${d.ref})؛ مدیر دپارتمان بیدار شد تا منشورش را بنویسد.")
                brief = ""; key = UUID.randomUUID().toString()
                onAsked(d.ref)
            }
        }, size = BtnSize.SM, icon = DivanIcon.SEND, enabled = brief.trim().length >= 6, loading = action.busy)
        Text("مدیر مینویسد؛ ناظر، آزمون و تأیید بعد از آن.", style = Divan.type.micro, color = c.textMuted)
    }
}

@Composable
fun DraftRow(d: RoleDraft, onOpen: () -> Unit) {
    val c = Divan.colors
    Row(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).clickable(role = Role.Button, onClick = onOpen).padding(12.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        DIcon(DivanIcon.DEPARTMENT, size = 18.dp, tint = c.textSecondary)
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(d.titleFa.ifBlank { "در حال نوشتن" }, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text(buildAnnotatedString {
                fig(d.ref); if (d.role.isNotBlank()) { append(" · "); fig(d.role) }; append(" · " + (DEPT_FA[d.department] ?: d.department))
            }, style = Divan.type.micro, color = c.textMuted, maxLines = 1)
        }
        LabelPill(ROLE_STATE[d.state], d.state)
    }
}

/** The company's roles written on demand, on its people tab: what each department grew beyond the template. */
@Composable
fun RolesOnDemand(company: String, onOpen: (String) -> Unit) {
    val c = Divan.colors
    val q = rememberQuery("roles:drafts:$company:", "roles") { roleDrafts(company) }
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("نقش‌های تازه", note = "مدیر هر دپارتمان مینویسد؛ ناظر، آزمون خودش و تأیید، بعد قابل استخدام")
        Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            val xs = q.data
            when {
                xs == null -> Skeleton(Modifier.fillMaxWidth().height(56.dp))
                xs.isEmpty() -> Text("هنوز نقشی بیرون از قالب نوشته نشده. روی هر دپارتمان بزن و «نقش تازه بخواه».", style = Divan.type.small, color = c.textMuted)
                else -> for (d in xs) DraftRow(d) { onOpen(d.ref) }
            }
        }
    }
}

/** The gates in order: writing, the overseer, its own eval, approval, active; a rejected or retired draft says so. */
@Composable
private fun Gates(d: RoleDraft) {
    val c = Divan.colors
    val idx = ROLE_GATES.indexOfFirst { it.first == d.state }
    val stopped = d.state == "rejected" || d.state == "retired"
    FlowRow(horizontalArrangement = Arrangement.spacedBy(4.dp), verticalArrangement = Arrangement.spacedBy(4.dp), itemVerticalAlignment = Alignment.CenterVertically) {
        ROLE_GATES.forEachIndexed { i, (_, fa) ->
            val done = !stopped && (idx > i || d.state == "active")
            val now = idx == i && d.state != "active"
            val (bg, fg) = when { now -> c.softGold to c.goldInk; done -> c.softPositive to c.positive; else -> c.tile to c.textMuted }
            Row(Modifier.clip(CircleShape).background(bg).padding(horizontal = 10.dp, vertical = 4.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                DIcon(if (done) DivanIcon.SEAL else DivanIcon.TIME, size = 12.dp, tint = fg)
                Text(fa, style = Divan.type.micro.copy(fontWeight = if (now) FontWeight.SemiBold else FontWeight.Normal), color = fg)
            }
        }
        if (stopped) ROLE_STATE[d.state]?.let { Pill(it.fa, it.tone, icon = if (d.state == "rejected") DivanIcon.REJECT else DivanIcon.PAUSE) }
    }
}

/** A role draft as its own page (from a card, a story or a ref). */
@Composable
fun RoleDraftScreen(ref: String) {
    val q = rememberQuery("roles:draft:$ref", "roles") { roleDraft(ref) }
    val r = refresher(q)
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item {
            val d = q.data
            if (d != null) Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Fig(d.ref, style = Divan.type.figureSmall, color = Divan.colors.textMuted)
                Text(d.titleFa.ifBlank { "نقش تازه" }, style = Divan.type.h1)
            }
        }
        item { HqCard(Modifier.fillMaxWidth()) { RoleDraftView(ref) } }
    }
}

/** One role written on demand: its gates, who asked and who wrote it, why a new role (and what it was compared with), the model, tools
 *  and limits inside the department's ceiling, the charter, the overseer's review, its own eval, and its approval; an active one can be
 *  retired (no passkey; employees on it keep running until moved or dismissed). */
@Composable
fun RoleDraftView(ref: String) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val action = rememberAction()
    val q = rememberQuery("roles:draft:$ref", "roles") { roleDraft(ref) }
    var confirm by remember { mutableStateOf(false) }
    val d = q.data
    val live = d?.live == true || d?.evalRun?.live == true
    LaunchedEffect(live) { while (live) { delay(5_000); q.refresh() } }
    if (d == null) return if (q.error != null) ErrorBlock(q.error, { q.refresh() }) else Skeleton(Modifier.fillMaxWidth().height(320.dp), radius = 12.dp)
    Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
        Text(buildAnnotatedString {
            append(DEPT_FA[d.department] ?: d.department); append(" "); fig(d.company)
            if (d.role.isNotBlank()) { append(" · "); fig(d.role) }
            if (d.titleEn.isNotBlank()) { append(" · "); fig(d.titleEn) }
        }, style = Divan.type.caption, color = c.textMuted)
        Gates(d)
        d.stateNoteFa?.let { note ->
            Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.softNegative).padding(12.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                DIcon(DivanIcon.URGENT, Modifier.padding(top = 2.dp), size = 16.dp, tint = c.negative)
                RichText(note, Modifier.weight(1f), style = Divan.type.small, color = c.textPrimary)
            }
        }
        FlowRow(horizontalArrangement = Arrangement.spacedBy(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp), itemVerticalAlignment = Alignment.CenterVertically) {
            d.requestedBy?.let { Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) { ActorAvatar(it, size = 18.dp); Text("خواسته‌ی ${actorFa(it)}", style = Divan.type.micro, color = c.textMuted) } }
            d.writtenBy?.let { Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) { ActorAvatar(it, size = 18.dp); Text("نوشته‌ی ${actorFa(it)}", style = Divan.type.micro, color = c.textMuted) } }
            Text(ago(d.createdAt), style = Divan.type.micro, color = c.textMuted)
        }
        d.briefMd?.let { b -> Block("خواسته") { Text(prose("«$b»"), Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp), style = Divan.type.small, color = c.textPrimary) } }
        if (d.state == "drafting") Text(
            "مدیر دپارتمان بیدار شد و منشور را مینویسد: اول میگوید کدام منشور موجود را مقایسه کرد و چرا جواب نمیداد، بعد متن، ابزارها داخل سقف دپارتمان، مدل و دست‌کم سه مورد آزمون.",
            Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp), style = Divan.type.small, color = c.textSecondary,
        )
        if (d.whyMd.isNotBlank()) Block("چرا یک نقش تازه") {
            Md(d.whyMd, color = c.textPrimary)
            if (d.compared.isNotEmpty()) FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(4.dp), itemVerticalAlignment = Alignment.CenterVertically) {
                Text("مقایسه با:", style = Divan.type.micro, color = c.textMuted)
                for (r in d.compared) Text(roleFa(r), Modifier.clip(CircleShape).background(c.tile).padding(horizontal = 8.dp, vertical = 2.dp), style = Divan.type.micro, color = c.textSecondary)
            }
            d.originality?.let { o ->
                Text(prose("چک تکراری نبودن (قاعده): ${if (o.ok) "قبول" else "رد"}" + (o.noteFa?.let { " · $it" } ?: "")), style = Divan.type.micro, color = if (o.ok) c.textMuted else c.negative)
            }
        }
        if (d.model.isNotBlank()) Block("مدل، ابزار و سقف") {
            val facts = listOf("مدل" to modelLabel(d.model), "فکر" to d.effort, "قدم هر اجرا" to d.limits.stepsPerRun.toString(), "سقف هر اجرا" to "${tokens(d.limits.tokensPerRun)} tok")
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                for (row in facts.chunked(2)) Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    for ((l, v) in row) Column(Modifier.weight(1f).clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Text(l, style = Divan.type.micro, color = c.textMuted)
                        Fig(v, style = Divan.type.figure.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                    }
                }
            }
            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                for (t in d.tools) Fig(t, Modifier.clip(RoundedCornerShape(6.dp)).background(c.tile).padding(horizontal = 8.dp, vertical = 2.dp), style = Divan.type.figureSmall, color = c.textSecondary)
            }
            Text("سقف سخت با کد: ابزارها زیرمجموعه‌ی سقف دپارتمان، هرگز قدرت نظارت، استخدام، تصمیم نقش، کلید توقف یا پیام مستقیم به تو؛ مدل حداکثر سقف دپارتمان؛ سقف‌ها حداکثر همان مدیر. A3 همیشه پیشنهاد میماند.".let(::prose), style = Divan.type.micro, color = c.textMuted)
        }
        if (d.charterMd.isNotBlank()) Block("متن منشور") {
            // The charter is English: it reads left to right, in its own scrolling box (as the web's).
            CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
                Md(
                    d.charterMd,
                    Modifier.fillMaxWidth().heightIn(max = 320.dp).clip(RoundedCornerShape(12.dp)).background(c.tile).verticalScroll(rememberScrollState()).padding(12.dp),
                    style = Divan.type.figureSmall.copy(lineHeight = Divan.type.small.lineHeight), color = c.textPrimary,
                )
            }
        }
        val rv = d.review
        if (rv != null) Block("بازبینی ناظر کل", action = {
            Pill(when (rv.verdict) { "pass" -> "قبول"; "reject" -> "رد"; else -> "اصلاح" }, when (rv.verdict) { "pass" -> Tone.POS; "reject" -> Tone.NEG; else -> Tone.WARN }, dot = true)
        }) {
            FlowRow(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalArrangement = Arrangement.spacedBy(6.dp), itemVerticalAlignment = Alignment.CenterVertically) {
                for ((k, ok) in rv.checks) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    DIcon(if (ok) DivanIcon.SEAL else DivanIcon.URGENT, size = 12.dp, tint = if (ok) c.positive else c.negative)
                    Text(REVIEW_CHECK_19[k] ?: k, style = Divan.type.caption, color = if (ok) c.positive else c.negative)
                }
            }
            Text(buildAnnotatedString { fig("sha256 ${rv.sha256.take(16)}…"); append(" · ${actorFa(rv.by)}") }, style = Divan.type.micro, color = c.textMuted)
        } else if (d.state == "in_review") Text("ناظر کل متن کامل ماسک‌شده را با sha256 میخواند؛ پنج چک: تزریق، رمز، تناقض، سیاست و سقف.".let(::prose), style = Divan.type.caption, color = c.textMuted)
        if (d.eval.cases.isNotEmpty()) {
            val run = d.evalRun
            Block("آزمون خودش", action = {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Fig(d.eval.suite, style = Divan.type.figureSmall, color = c.textMuted)
                    when {
                        run == null -> Unit
                        run.live -> Pill("در حال اجرا", Tone.LAPIS, live = true)
                        else -> Pill("${if (run.passed == true) "قبول" else "رد"}، ${run.score?.let { com.coinepro.hq.ui.v17.num(it) } ?: "—"}", if (run.passed == true) Tone.POS else Tone.NEG, dot = true)
                    }
                }
            }) {
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    for (cs in d.eval.cases) {
                        val r = run?.cases?.firstOrNull { it.id == cs.id }
                        Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(c.tile).padding(10.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                Fig(cs.id, style = Divan.type.figureSmall, color = c.textMuted)
                                Text(prose(cs.inputMd), Modifier.weight(1f), style = Divan.type.caption, color = c.textPrimary)
                                Text("وزن ${com.coinepro.hq.ui.v17.num(cs.weight)}", style = Divan.type.micro, color = c.textMuted)
                                r?.score?.let { Fig(com.coinepro.hq.ui.v17.num(it), style = Divan.type.figureSmall, color = c.textSecondary) }
                            }
                            Text(prose("معیار: ${cs.rubricMd}"), style = Divan.type.micro, color = c.textMuted)
                        }
                    }
                    Text("باید قبول شود؛ همین نمره خط پایه‌ی خود نقش میشود.", style = Divan.type.micro, color = c.textMuted)
                }
            }
        }
        if (d.state == "active" || d.approver != null) FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(4.dp), itemVerticalAlignment = Alignment.CenterVertically) {
            DIcon(DivanIcon.SEAL, size = 14.dp, tint = c.textSecondary)
            Text(com.coinepro.hq.designsystem.timesFig("تأیید ${actorFa(d.approver)}" + (d.activatedAt?.let { "، ${jDateTime(it)}" } ?: "")), style = Divan.type.caption, color = c.textSecondary)
            d.decisionRef?.let { RefChip(it) }
            d.retiredAt?.let { Text(com.coinepro.hq.designsystem.timesFig("· بازنشسته ${jDateTime(it)}"), style = Divan.type.micro, color = c.textMuted) }
        }
        if (d.state == "active") Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Text(
                "منشور روی سرور است، فقط برای همین شرکت و دپارتمان؛ " + if (d.hires > 0) "${d.hires} نفر رویش کار میکنند." else "هنوز کسی رویش استخدام نشده.",
                Modifier.weight(1f), style = Divan.type.caption, color = c.textMuted,
            )
            HqButton("بازنشسته کن", { confirm = true }, size = BtnSize.SM, variant = BtnVariant.DANGER, icon = DivanIcon.PAUSE)
        }
    }
    if (confirm) AlertDialog(
        onDismissRequest = { confirm = false },
        containerColor = c.overlay,
        title = { Text("بازنشسته کردن نقش", style = Divan.type.h3) },
        text = { Text("کسی دیگر روی این نقش استخدام نمیشود؛ کارمندهایی که دارد تا جابه‌جایی یا برکناری کار میکنند. منشورش در تاریخچه میماند و نسخه‌ی تازه، پیش‌نویس تازه است.", style = Divan.type.small, color = c.textSecondary) },
        confirmButton = {
            HqButton("بازنشسته کن", {
                action.media(toasts) {
                    q.set(env.api.retireRoleDraft(d.ref))
                    env.cache.invalidate("roles", "stories", "hiring")
                    confirm = false
                    toasts.info("بازنشسته شد؛ استخدام تازه روی آن نیست و کارمندهایش تا جابه‌جایی کار میکنند.")
                }
            }, variant = BtnVariant.DANGER, icon = DivanIcon.PAUSE, loading = action.busy)
        },
        dismissButton = { HqButton("نه", { confirm = false }, variant = BtnVariant.GHOST) },
    )
}
