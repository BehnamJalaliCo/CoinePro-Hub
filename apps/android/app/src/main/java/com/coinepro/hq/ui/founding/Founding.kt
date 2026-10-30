package com.coinepro.hq.ui.founding

import com.coinepro.hq.ui.itemMotion
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.HorizontalDivider
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDirection
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.DEPT_FA
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.format.jTime
import com.coinepro.hq.core.format.modelLabel
import com.coinepro.hq.core.format.roleFa
import com.coinepro.hq.core.format.usd
import com.coinepro.hq.core.net.Founding
import com.coinepro.hq.core.net.HostKey
import com.coinepro.hq.core.net.ProvisionRun
import com.coinepro.hq.core.net.ServerPlan
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
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.SegOption
import com.coinepro.hq.designsystem.Segmented
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.activity
import com.coinepro.hq.ui.companies.BrandBlock
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v14.FOUNDING_STATE
import com.coinepro.hq.ui.v14.HqSheet
import com.coinepro.hq.ui.v14.LabelPill
import com.coinepro.hq.ui.v14.ScoreBar
import com.coinepro.hq.ui.v14.Tag
import com.coinepro.hq.ui.v14.figs
import com.coinepro.hq.ui.workshop.SpokenField
import java.util.Locale
import kotlinx.coroutines.delay

/** A founding's state as a pill; an idea has no audit, so its first state reads as the proposal being written. */
private fun stateLabel(f: Founding) =
    if (f.state == "auditing" && f.source.kind != "repo") com.coinepro.hq.ui.v14.Label("در حال نوشتن پیشنهاد", Tone.LAPIS, live = true) else FOUNDING_STATE[f.state]
/** ⟨1.4.6⟩ the step «مُهر شرکت» (§18.8, §18.14): open once the company exists, i.e. from the seal of `company_found` on. */
private val BRAND_OPEN = setOf("sealed", "provisioning", "ready_for_login", "active")
private val BRAND_STATE = mapOf(
    "missing" to ("هنوز نشان ندارد" to Tone.WARN), "proposed" to ("نشان آماده، منتظر مُهر تو" to Tone.GOLD), "active" to ("مُهر شد" to Tone.POS),
)
private val AUDIT_FA = mapOf("architecture" to "معماری", "quality" to "کیفیت", "security" to "امنیت", "tests" to "تست‌ها", "debt" to "بدهی فنی")
private val SOFTWARE_FA = mapOf(
    "system-upgrade" to "به‌روزرسانی و ارتقای کامل سیستم", "unattended-upgrades" to "به‌روزرسانی خودکار امنیتی", "work-user" to "کاربر کاری",
    "ssh-hardening" to "سخت‌سازی SSH (فقط کلید، بدون root)", "docker" to "Docker", "git" to "Git", "node-lts" to "Node LTS",
    "claude-code" to "Claude Code (ورود با حساب خودت)", "repo-clone" to "clone ریپوی شرکت", "private-network" to "شبکه‌ی خصوصی هتزنر",
    "hetzner-firewall" to "فایروال هتزنر", "node-exporter" to "پایش (فقط روی IP خصوصی)",
)
private val PATH = listOf(
    Triple("ممیزی (فقط از ریپو)", "جلسه‌ی فقط‌خواندنی کارگاه روی ریپو: کد، وابستگی‌ها، ریسک‌ها، هزینه. ایده ممیزی ندارد.", false),
    Triple("پیشنهاد", "نام، رسالت، تیم و نقش‌ها، KPI، بودجه‌ی توکن و نقشه‌ی راه ۹۰ روزه.", false),
    Triple("مُهر شرکت", "تو تأیید یا اصلاح میکنی؛ بدون مُهر هیچ شرکتی ساخته نمیشود.", true),
    Triple("نقشه‌ی سرور", "نوع و منطقه‌ی سرور، دیسک، فایروال هتزنر و هزینه‌ی ماهانه.", false),
    Triple("مُهر سرور", "مُهر جدا روی خلاصه‌ی دقیق نقشه؛ هزینه‌ی واقعی از اینجا شروع میشود.", true),
    Triple("ساخت", "سرور تازه، به‌روزرسانی و ارتقا، Docker، Node، Claude Code، کاربر کاری؛ فقط با کلید SSH تو.", false),
    Triple("ورود تو", "خودت وارد میشوی و Claude Code را لاگین میکنی؛ رمز هیچ‌وقت به ایجنت نمیرسد.", true),
    Triple("فعال", "مدیرعامل شروع میکند و شرکت وارد ستاره‌ها و نظارت میشود.", false),
)

/** تأسیس شرکت (contract §18.8): from a repository or an idea to a sealed company and a server ready for the owner's own login. */
@Composable
fun FoundingsScreen() {
    val nav = LocalNav.current
    val c = Divan.colors
    val env = LocalEnv.current
    val q = rememberQuery("founding:list", "founding", maxAgeMs = 15_000) { foundings() }
    val r = refresher(q)
    // §18.16: a Page, newest first; later pages are appended on «بیشتر».
    var more by remember(q.data) { mutableStateOf(emptyList<Founding>()) }
    var cursor by remember(q.data) { mutableStateOf(q.data?.nextCursor) }
    val loadMore = rememberAction()
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item {
            PageHeader("تأسیس شرکت", eyebrow = "از ایده، ریپو یا فقط با نام؛ تا شرکت فعال و سرور آماده") {
                HqButton("تأسیس تازه", { nav.go("founding/new") }, variant = BtnVariant.PRIMARY, icon = DivanIcon.ADD)
            }
        }
        item { Text("هر شرکت تازه از همین‌جا: از یک ایده، از یک ریپوی GitHub، یا فقط با نام و کد که بعداً کاملش کنی. پیشنهاد و ممیزی به کارتابلت میاید؛ شرکت فقط با مُهر تو ساخته میشود و سرور با مُهر جدا. رمز سرور هیچ‌وقت به ایجنت نمیرسد.", style = Divan.type.small, color = c.textSecondary) }
        val list = q.data?.let { it.items + more }
        when {
            list == null && q.error != null -> item { ErrorBlock(q.error, { q.refresh() }) }
            list == null -> items(2) { Skeleton(Modifier.fillMaxWidth().height(76.dp), radius = 16.dp) }
            list.isEmpty() -> item { Empty("هنوز تأسیسی نیست", icon = DivanIcon.FOUND) }
            else -> items(list.size, key = { list[it].ref }) { i -> Box(itemMotion()) {
                val f = list[i]
                val gold = f.state == "ready_for_login" || f.state == "proposed"
                Column(
                    Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(if (gold) c.softGold else c.card).clickable(role = Role.Button) { nav.go("founding/${f.ref}") }.padding(14.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        DIcon(DivanIcon.FOUND, size = 18.dp, tint = c.goldInk)
                        Text(f.title, style = Divan.type.bodyStrong, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
                        LabelPill(stateLabel(f), f.state)
                    }
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Fig(f.ref, style = Divan.type.figureSmall, color = c.textMuted)
                        if (f.source.repo != null) Fig(f.source.repo, Modifier.weight(1f), style = Divan.type.figureSmall, color = c.textMuted)
                        else Text("ایده", style = Divan.type.micro, color = c.textMuted, modifier = Modifier.weight(1f))
                        Text(ago(f.updatedAt), style = Divan.type.micro, color = c.textMuted)
                    }
                }
            }}
        }
        cursor?.let { at ->
            item {
                HqButton("بیشتر", {
                    loadMore.run {
                        val pg = env.api.foundings(at)
                        more = more + pg.items
                        cursor = pg.nextCursor
                    }
                }, variant = BtnVariant.SECONDARY, size = BtnSize.SM, loading = loadMore.busy)
            }
        }
        item { SectionTitle("مسیر تأسیس از ایده یا ریپو", note = "سه نقطه با توست؛ بقیه را ایجنت‌ها انجام میدهند و همه در دفتر Audit ثبت میشود") }
        item {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                PATH.forEachIndexed { i, (t, d, you) ->
                    Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(if (you) c.softGold else c.card).padding(12.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        Box(Modifier.size(28.dp).clip(CircleShape).background(if (you) c.goldFill else c.tile), contentAlignment = Alignment.Center) {
                            Text("${i + 1}", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = if (you) c.onGold else c.textSecondary)
                        }
                        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                Text(t, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold))
                                if (you) DIcon(DivanIcon.SEAL, size = 14.dp, tint = c.goldInk)
                            }
                            Text(d, style = Divan.type.caption, color = c.textSecondary)
                        }
                    }
                }
                Text("پیش از اولین ساخت، یک بار در ترمینال خودت: make hetzner-token و make owner-ssh-key.", style = Divan.type.caption, color = c.textMuted)
            }
        }
    }
}

/** One founding, from audit to an active company (contract §18.8). The server plan is sealed on its digest; the build
 *  runs live; the owner logs in personally before the company is activated. */
@Composable
fun FoundingScreen(ref: String) {
    // A server plan with no founding (a company's CTO wrote it, §18.16): the cartable's server_plan card lands here.
    when {
        ref == "new" -> FoundingWizard()
        ref.startsWith("PV-") -> PlanScreen(ref)
        else -> FoundingDetail(ref)
    }
}

@Composable
private fun FoundingDetail(ref: String) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val act = activity()
    val c = Divan.colors
    val q = rememberQuery("founding:$ref", "founding", maxAgeMs = 5_000) { founding(ref) }
    val f = q.data
    val plan = f?.plan?.let { p -> rememberQuery("founding:plan:$p", "founding") { f.planDetail?.takeIf { it.ref == p } ?: plan(p) } }
    val runId = plan?.data?.run
    val run = runId?.let { id -> rememberQuery("founding:run:$id", "founding", maxAgeMs = 2_000) { run(id) } }
    val action = rememberAction()
    var cancel by remember { mutableStateOf(false) }
    var noBrand by remember { mutableStateOf(false) }
    // §18.8: without an active brand the hub asks first; the owner may still go on and seal the brand later.
    fun activate(skipBrand: Boolean) = action.run(onError = { e ->
        if (e.status == 409 && e.code == "not_ready" && "brand" in e.missing) noBrand = true else toasts.error(e.messageFa)
    }) {
        env.api.activateFounding(ref, { a, t -> env.auth.stepUp(act, a, t) }, skipBrand)
        noBrand = false
        env.cache.invalidate("founding", "companies")
        toasts.ok("شرکت فعال شد؛ مدیرعامل شروع به کار کرد.")
    }
    // Live while something moves: the audit, the build (every 2 s), until the server is ready.
    val building = run?.data?.state in setOf("queued", "running")
    LaunchedEffect(f?.state, run?.data?.state) {
        while (f?.state in setOf("auditing", "sealed", "provisioning") || building) {
            delay(if (building) 2_000 else 5_000)
            run?.refresh()
            q.refresh()
        }
    }
    val r = refresher(q)
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        when {
            f == null && q.error != null -> item { ErrorBlock(q.error, { q.refresh() }) }
            f == null -> item { Skeleton(Modifier.fillMaxWidth().height(240.dp), radius = 16.dp) }
            else -> {
                // §18.16: cancel closes everything, so it is offered until a build runs; a failed build returns the founding to `sealed`.
                val cancellable = f.state == "auditing" || f.state == "proposed" || (f.state == "sealed" && !building)
                item { Header(f, if (cancellable) ({ cancel = true }) else null) }
                item { Stepper(f) }
                val login = run?.data?.login
                // The login card below says it itself when the server is ready.
                if (!(f.state == "ready_for_login" && login != null)) item { NowCard(f) }
                item { PendingBrand(f) }
                if (f.state == "ready_for_login" && login != null) item {
                    HqCard(Modifier.fillMaxWidth(), tahrir = true) {
                        SectionTitle("سرور آماده است؛ نوبت توست", note = "در ترمینال خودت وارد شو و Claude Code را با حساب خودت باز کن")
                        Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            Text("۱. وارد سرور شو", style = Divan.type.small, color = c.textSecondary)
                            CopyLine(login.ssh)
                            Text("۲. Claude Code را باز کن و با حساب خودت وارد شو", style = Divan.type.small, color = c.textSecondary)
                            for (cmd in login.then) CopyLine(cmd)
                            Text("۳. وقتی وارد شدی، شرکت را فعال کن تا مدیرعامل شروع کند.", style = Divan.type.small, color = c.textSecondary)
                            run.data?.server?.hostKeys?.takeIf { it.isNotEmpty() }?.let { HostKeys(it) }
                            HqButton("وارد شدم؛ شرکت را فعال کن", { activate(skipBrand = false) }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, size = BtnSize.LG, icon = DivanIcon.SEAL, loading = action.busy)
                        }
                    }
                }
                val co = f.company
                if (co != null && f.state in BRAND_OPEN) item {
                    HqCard(Modifier.fillMaxWidth()) {
                        BrandBlock(co, f.title, f.nameEn?.ifBlank { null } ?: co, title = "مُهر شرکت", badge = {
                            BRAND_STATE[f.brand.state]?.let { (fa, tone) -> Pill(fa, tone, dot = true) }
                        })
                    }
                }
                f.audit?.let { a ->
                    item {
                        HqCard(Modifier.fillMaxWidth()) {
                            SectionTitle("ممیزی", note = if (a.sessionRef != null) "جلسه‌ی فقط‌خواندنی کارگاه" else "امتیاز هر محور از ۱۰") {
                                // The audit is a work item (W-…) with its read-only workshop session (S-…) and its report (O-…): each opens its own page.
                                a.sessionRef?.let { com.coinepro.hq.ui.v17.RefChip(it) }
                                a.deliverable?.let { com.coinepro.hq.ui.v17.RefChip(it, tone = com.coinepro.hq.ui.v17.RefTone.NEUTRAL) }
                            }
                            Column(Modifier.padding(vertical = 10.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                for (pair in a.scores.entries.chunked(2)) Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                                    for ((k, v) in pair) Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                                        Text(AUDIT_FA[k] ?: k, style = Divan.type.micro, color = c.textMuted)
                                        ScoreBar(v, max = 10.0)
                                    }
                                    if (pair.size == 1) Box(Modifier.weight(1f))
                                }
                            }
                            Md(a.reportMd)
                        }
                    }
                }
                // While it audits (a repository) or writes the proposal (an idea), the «الان» card above says so in plain words.
                f.proposal?.let { p -> item { Proposal(f, p) } }
                plan?.let { pq ->
                    item {
                        val pl = pq.data
                        if (pl == null) Skeleton(Modifier.fillMaxWidth().height(200.dp), radius = 16.dp) else PlanCard(pl, run?.data)
                    }
                }
            }
        }
    }
    if (noBrand) AlertDialog(
        onDismissRequest = { noBrand = false },
        containerColor = c.overlay,
        title = { Text("شرکت هنوز مُهر ندارد", style = Divan.type.h3) },
        text = { Text("نشان و مُهر شرکت از لوگوی PNG آن ساخته میشود. اگر بدون مُهر فعال کنی، شرکت تا وقتی نشانش را مُهر کنی با کدش دیده میشود؛ این کار از صفحه‌ی شرکت هم شدنی است.", style = Divan.type.small, color = c.textSecondary) },
        confirmButton = { HqButton("بدون مُهر فعال کن", { activate(skipBrand = true) }, variant = BtnVariant.GHOST, loading = action.busy) },
        dismissButton = { HqButton("اول مُهر را بساز", { noBrand = false }) },
    )
    if (cancel && f != null) AlertDialog(
        onDismissRequest = { cancel = false },
        containerColor = c.overlay,
        title = { Text("این تأسیس لغو شود؟", style = Divan.type.h3) },
        text = {
            val tail = when {
                run?.data?.server != null -> "سروری که ساخته شده خاموش یا پاک نمیشود؛ پاک کردنش فقط با خودت در کنسول هتزنر است."
                f.state == "sealed" -> "طرح سرور مُهرشده به پیشنهاد برمیگردد و هیچ سروری ساخته نمیشود."
                else -> "هنوز سروری ساخته نشده و هزینه‌ای نیست."
            }
            Text("ممیزی و پیشنهاد در سوابق میماند و کارت‌های باز این تأسیس از کارتابل برداشته میشوند. $tail", style = Divan.type.small, color = c.textSecondary)
        },
        confirmButton = {
            HqButton("لغو کن", {
                action.run {
                    env.api.cancelFounding(f.ref)
                    env.cache.invalidate("founding")
                    cancel = false
                    toasts.ok("لغو شد.")
                }
            }, variant = BtnVariant.DANGER, loading = action.busy)
        },
        dismissButton = { HqButton("نه", { cancel = false }, variant = BtnVariant.GHOST) },
    )
}

@Composable
private fun Header(f: Founding, onCancel: (() -> Unit)?) {
    val c = Divan.colors
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Box(Modifier.size(48.dp).clip(CircleShape).background(c.softGold), contentAlignment = Alignment.Center) { DIcon(DivanIcon.FOUND, size = 24.dp, tint = c.goldInk) }
            Column(Modifier.weight(1f)) {
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Fig(f.ref, style = Divan.type.figureSmall, color = c.textMuted)
                    if (f.source.repo != null) Fig(f.source.repo, style = Divan.type.figureSmall, color = c.textMuted) else Text("ایده", style = Divan.type.micro, color = c.textMuted)
                }
                Text(f.title, style = Divan.type.h1)
                f.nameEn?.takeIf { it.isNotBlank() }?.let { Fig(it, style = Divan.type.figureSmall, color = c.textMuted) }
            }
        }
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            LabelPill(stateLabel(f), f.state)
            Box(Modifier.weight(1f))
            // Cancelling withdraws the cards, returns an unrun sealed plan and stops the audit (§18.16); only the owner removes servers, in Hetzner.
            if (onCancel != null) HqButton("لغو تأسیس", onCancel, variant = BtnVariant.GHOST, size = BtnSize.SM)
        }
    }
}

@Composable
private fun Stepper(f: Founding) {
    val c = Divan.colors
    val stages = com.coinepro.hq.core.data.FoundingStages.of(f.source.kind)
    val at = stages.indexOfFirst { it.state == f.state }
    Row(Modifier.horizontalScroll(rememberScrollState()), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        stages.forEachIndexed { i, st ->
            val fa = st.fa
            val (bg, fg) = when { i < at -> c.softPositive to c.positive; i == at -> c.softGold to c.goldInk; else -> c.tile to c.textMuted }
            Row(Modifier.height(28.dp).clip(CircleShape).background(bg).padding(horizontal = 10.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(5.dp)) {
                if (i < at) DIcon(DivanIcon.SEAL, size = 12.dp, tint = fg, active = true) else Text("${i + 1}", style = Divan.type.micro, color = fg)
                Text(fa, style = Divan.type.caption.copy(fontWeight = if (i == at) FontWeight.SemiBold else FontWeight.Normal), color = fg)
            }
            if (i < stages.lastIndex) Box(Modifier.width(8.dp).height(1.dp).background(c.lineDivider))
        }
    }
}

/** A server plan, its seal and its build (§18.8, §18.16): no price or an open problem, no seal. */
@Composable
private fun PlanCard(pl: ServerPlan, rn: ProvisionRun?) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val act = activity()
    val c = Divan.colors
    val action = rememberAction()
    val price = pl.monthlyEur?.let { "€" + String.format(Locale.US, "%.2f", it.toDouble()) }
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("سرور") {
            if (price != null) Fig("$price / ماه", style = Divan.type.figure.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
            else Pill("قیمت هنوز معلوم نیست", Tone.WARN, dot = true)
        }
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Fig(pl.ref, style = Divan.type.figureSmall, color = c.textMuted)
            Fig(pl.name, style = Divan.type.figureSmall, color = c.textMuted)
        }
        Row(Modifier.padding(vertical = 10.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            for ((k, v) in listOf("نوع" to pl.type, "محل" to pl.location, "سیستم" to pl.image)) {
                Column(Modifier.weight(1f).clip(RoundedCornerShape(10.dp)).background(c.tile).padding(horizontal = 10.dp, vertical = 8.dp)) {
                    Text(k, style = Divan.type.micro, color = c.textMuted)
                    Fig(v, style = Divan.type.figureSmall, color = c.textPrimary)
                }
            }
        }
        Text("فایروال هتزنر (ورودی)", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
        for (w in pl.firewall) Row(Modifier.padding(vertical = 3.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Fig(listOfNotNull(w.protocol, w.port).joinToString(" "), Modifier.width(76.dp), style = Divan.type.figureSmall, color = c.textPrimary)
            Text(w.noteFa, style = Divan.type.caption, color = c.textSecondary, modifier = Modifier.weight(1f))
            Fig(w.sources.joinToString(", "), style = Divan.type.figureSmall, color = c.textMuted)
        }
        Text("نصب کامل", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary, modifier = Modifier.padding(top = 10.dp))
        Column(Modifier.padding(vertical = 6.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            for (k in pl.software) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                DIcon(DivanIcon.SEAL, size = 12.dp, tint = c.positive)
                Text(SOFTWARE_FA[k] ?: k, style = Divan.type.caption, color = c.textPrimary)
            }
        }
        Text("کاربر کاری ${pl.workUser}" + (pl.repo?.let { " · ریپو $it" } ?: "") + " · رمز root ساخته نمیشود؛ فقط کلید عمومی تو.", style = Divan.type.micro, color = c.textMuted)
        if (pl.state == "proposed" && pl.problems.isNotEmpty()) Column(
            Modifier.fillMaxWidth().padding(top = 10.dp).clip(RoundedCornerShape(10.dp)).background(c.softWarning).padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            Text("تا این‌ها رفع نشود، طرح مُهر نمیشود", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.warning)
            for (x in pl.problems) Fig(x, style = Divan.type.figureSmall, color = c.textSecondary, maxLines = 4)
        }
        if (pl.state == "proposed") HqButton("با گذرکلید مُهر کن و بساز" + (price?.let { " ($it در ماه)" } ?: ""), {
            action.run {
                env.api.sealPlan(pl) { a, t -> env.auth.stepUp(act, a, t) }
                env.cache.invalidate("founding")
                toasts.ok("مُهر شد؛ ساخت سرور شروع شد.")
            }
        }, Modifier.fillMaxWidth().padding(top = 12.dp), variant = BtnVariant.PRIMARY, size = BtnSize.LG, icon = DivanIcon.SEAL, enabled = pl.sealable, loading = action.busy)
        rn?.let { RunBlock(it) }
    }
}

private val RUN_STATE = mapOf("queued" to ("در صف" to Tone.WARN), "running" to ("در جریان" to Tone.LAPIS), "done" to ("تمام شد" to Tone.POS), "failed" to ("خطا" to Tone.NEG))

/** The build of a sealed plan, step by step; a failed one resumes from its failed step on the same seal (§18.16). */
@Composable
private fun RunBlock(rn: ProvisionRun) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val action = rememberAction()
    HorizontalDivider(Modifier.padding(vertical = 12.dp), color = c.lineDivider)
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Text("ساخت", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
        val (fa, tone) = RUN_STATE[rn.state] ?: ("خطا" to Tone.NEG)
        Pill(fa, tone, live = rn.state == "running", dot = rn.state != "running")
    }
    Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        for (s in rn.steps) Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            val (bg, fg) = when (s.state) { "done" -> c.softPositive to c.positive; "running" -> c.softLapis to c.lapis; "failed" -> c.softNegative to c.negative; else -> c.tile to c.textMuted }
            Box(Modifier.padding(top = 2.dp).size(20.dp).clip(CircleShape).background(bg), contentAlignment = Alignment.Center) {
                when (s.state) {
                    "running" -> CircularProgressIndicator(Modifier.size(11.dp), color = fg, strokeWidth = 1.5.dp)
                    "done" -> DIcon(DivanIcon.SEAL, size = 11.dp, tint = fg, active = true)
                    "failed" -> DIcon(DivanIcon.URGENT, size = 11.dp, tint = fg)
                }
            }
            Column(Modifier.weight(1f)) {
                Text(s.titleFa, style = Divan.type.small, color = if (s.state == "pending") c.textMuted else c.textPrimary)
                if (s.logTail.isNotEmpty()) Text(s.logTail.takeLast(3).joinToString("\n"), style = Divan.type.figureSmall.copy(textDirection = TextDirection.Ltr), color = c.textMuted)
            }
            s.finishedAt?.let { Text(jTime(it), style = Divan.type.micro, color = c.textMuted) }
        }
    }
    if (rn.state == "failed") Column(
        Modifier.fillMaxWidth().padding(top = 10.dp).clip(RoundedCornerShape(10.dp)).background(c.softNegative).padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Text("ساخت در گام شکست‌خورده متوقف شد" + (rn.error?.code?.let { " ($it)" } ?: "") + ". با همان مُهر از همان گام ادامه میدهد؛ یا تأسیس را لغو کن.", style = Divan.type.caption, color = c.textSecondary)
        HqButton("از همان گام ادامه بده", {
            action.run {
                env.api.resumeRun(rn.id)
                env.cache.invalidate("founding")
                toasts.ok("ساخت از همان گام ادامه پیدا کرد.")
            }
        }, variant = BtnVariant.SECONDARY, size = BtnSize.SM, icon = DivanIcon.REFRESH, loading = action.busy)
    }
    rn.server?.let { sv -> Fig(listOfNotNull(sv.name, sv.ipv4, sv.ipv6, sv.privateIp).joinToString(" · "), Modifier.padding(top = 10.dp), style = Divan.type.figureSmall, color = c.textSecondary) }
    if (rn.state == "done") rn.server?.hostKeys?.takeIf { it.isNotEmpty() }?.let { Box(Modifier.padding(top = 8.dp)) { HostKeys(it) } }
}

/** The new server's host-key fingerprints, which the owner checks on the first login (§18.16). */
@Composable
private fun HostKeys(keys: List<HostKey>) {
    val c = Divan.colors
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text("پیش از اولین ورود، اثر انگشت کلید سرور را با همین‌ها بسنج:", style = Divan.type.caption, color = c.textSecondary)
        CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
            for (k in keys) Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(8.dp)).background(c.page).padding(horizontal = 12.dp, vertical = 6.dp)) {
                Fig(k.type, style = Divan.type.figureSmall, color = c.textMuted)
                // The whole fingerprint, wrapped: the owner compares every character.
                Fig(k.fingerprintSha256, style = Divan.type.figureSmall, color = c.textPrimary, maxLines = 3)
            }
        }
    }
}

/** A plan with no founding: its card, its build, and a way back to the cartable; a founding's plan goes on to its founding. */
@Composable
private fun PlanScreen(ref: String) {
    val nav = LocalNav.current
    val c = Divan.colors
    val q = rememberQuery("founding:plan:$ref", "founding") { plan(ref) }
    val pl = q.data
    val runId = pl?.run
    val run = runId?.let { id -> rememberQuery("founding:run:$id", "founding", maxAgeMs = 2_000) { run(id) } }
    LaunchedEffect(pl?.founding) { pl?.founding?.let { nav.go("founding/$it") } }
    val building = run?.data?.state in setOf("queued", "running")
    LaunchedEffect(run?.data?.state) {
        while (building) {
            delay(2_000)
            run?.refresh()
            q.refresh()
        }
    }
    val r = refresher(q)
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                Box(Modifier.size(48.dp).clip(CircleShape).background(c.softGold), contentAlignment = Alignment.Center) { DIcon(DivanIcon.SERVER, size = 24.dp, tint = c.goldInk) }
                Column(Modifier.weight(1f)) {
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        Text("طرح سرور", style = Divan.type.micro, color = c.textMuted)
                        pl?.company?.let { Fig(it, style = Divan.type.figureSmall, color = c.textMuted) }
                    }
                    Fig(ref, style = Divan.type.figureL, color = c.textPrimary)
                }
            }
        }
        item {
            when {
                pl == null && q.error != null -> ErrorBlock(q.error, { q.refresh() })
                pl == null -> Skeleton(Modifier.fillMaxWidth().height(200.dp), radius = 16.dp)
                else -> PlanCard(pl, run?.data)
            }
        }
    }
}

@Composable
private fun Proposal(f: Founding, p: com.coinepro.hq.core.net.FoundingProposal) {
    val nav = LocalNav.current
    val c = Divan.colors
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("پیشنهاد", note = "ساختار، هدف‌ها، تیم و نقشه‌ی راه") {
            if (f.decisionRef != null && f.state == "proposed") HqButton("مُهر در کارتابل", { nav.go("cartable/${f.decisionRef}") }, variant = BtnVariant.PRIMARY, size = BtnSize.SM, icon = DivanIcon.SEAL)
        }
        FlowRow(Modifier.padding(vertical = 10.dp), horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            for (d in p.departments) Tag(DEPT_FA[d] ?: d)
        }
        for (k in p.kpis) Row(Modifier.padding(vertical = 3.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            DIcon(DivanIcon.CHART, size = 14.dp, tint = c.textMuted)
            Text(k.nameFa, style = Divan.type.small, modifier = Modifier.weight(1f))
            Text(figs(k.target), style = Divan.type.caption, color = c.textSecondary)
        }
        HorizontalDivider(Modifier.padding(vertical = 8.dp), color = c.lineDivider)
        for (t in p.team) Row(Modifier.padding(vertical = 3.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Text(roleFa(t.role), style = Divan.type.caption, color = c.textPrimary, modifier = Modifier.weight(1f))
            Fig(modelLabel(t.model), style = Divan.type.figureSmall, color = c.textMuted)
            Fig(usd(t.monthlyUsd, 0), Modifier.width(44.dp), style = Divan.type.figureSmall, color = c.textSecondary)
        }
        Row(Modifier.padding(top = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            Text("جمع ماهانه‌ی تیم", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), modifier = Modifier.weight(1f))
            Fig(usd(p.monthlyUsd, 0), style = Divan.type.figure.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
        }
        if (p.roadmapMd.isNotBlank()) Md(p.roadmapMd, Modifier.padding(top = 10.dp))
    }
}

/** A command the owner runs in their own terminal: left to right, one tap copies it. */
@Composable
private fun CopyLine(text: String) {
    val c = Divan.colors
    val ctx = LocalContext.current
    val toasts = LocalToasts.current
    CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
        Row(
            Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(c.page).border(1.dp, c.lineDivider, RoundedCornerShape(10.dp)).padding(horizontal = 12.dp, vertical = 10.dp),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Fig("$", style = Divan.type.figureSmall, color = c.textMuted)
            Fig(text, Modifier.weight(1f), style = Divan.type.figureSmall, color = c.textPrimary)
            Text("کپی", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.goldInk, modifier = Modifier.clip(RoundedCornerShape(6.dp)).clickable(role = Role.Button) {
                (ctx.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager).setPrimaryClip(ClipData.newPlainText("command", text))
                toasts.ok("کپی شد.")
            }.padding(horizontal = 6.dp, vertical = 2.dp))
        }
    }
}

/** Where the founding is now, in plain words, whose turn it is, and the way to what it waits on. */
@Composable
private fun NowCard(f: Founding) {
    val nav = LocalNav.current
    val env = LocalEnv.current
    val c = Divan.colors
    val now = com.coinepro.hq.core.data.FoundingStages.now(f.state, f.source.kind, f.audit != null)
    HqCard(Modifier.fillMaxWidth(), color = if (now.ownersTurn) c.softGold else c.card) {
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Box(Modifier.size(36.dp).clip(CircleShape).background(if (now.ownersTurn) c.goldFill else c.tile), contentAlignment = Alignment.Center) {
                if (f.state in setOf("auditing", "provisioning")) CircularProgressIndicator(Modifier.size(16.dp), color = c.goldInk, strokeWidth = 2.dp)
                else DIcon(if (now.ownersTurn) DivanIcon.SEAL else DivanIcon.INFO, size = 18.dp, tint = if (now.ownersTurn) c.onGold else c.textSecondary)
            }
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                Text(if (now.ownersTurn) "الان، نوبت توست" else "الان", style = Divan.type.micro, color = if (now.ownersTurn) c.goldInk else c.textMuted)
                Text(now.title, style = Divan.type.bodyStrong)
                if (now.body.isNotBlank()) Text(now.body, style = Divan.type.small, color = c.textSecondary)
                if (f.company == null && env.foundingBrand.get(f.ref) != null && f.state != "cancelled")
                    Text("لوگو و رنگی که دادی روی همین گوشی نگه داشته شده تا شرکت ساخته شود.", style = Divan.type.caption, color = c.textMuted)
            }
        }
        FlowRow(Modifier.padding(top = 10.dp), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            when (f.state) {
                // The audit and the proposal are work items (W-…): they open on the work page, never a meeting or a session ref.
                "auditing" -> if (f.source.kind == "repo" && f.audit == null) f.auditWork?.let { w -> HqButton("ممیزی را ببین", { nav.go("work/$w") }, size = BtnSize.SM, icon = DivanIcon.TASK) }
                    else f.proposalWork?.let { w -> HqButton("کار پیشنهاد را ببین", { nav.go("work/$w") }, size = BtnSize.SM, icon = DivanIcon.TASK) }
                "proposed" -> f.decisionRef?.let { d -> HqButton("مُهر در کارتابل", { nav.go("cartable/$d") }, size = BtnSize.SM, variant = BtnVariant.PRIMARY, icon = DivanIcon.SEAL) }
                "active" -> f.company?.let { co -> HqButton("صفحه‌ی شرکت", { nav.go("companies/$co") }, size = BtnSize.SM, icon = DivanIcon.NEXT) }
            }
        }
    }
}

/** The logo and colour the owner gave in the wizard, used once the company exists (the hub makes it at the seal, §18.8). */
@Composable
private fun PendingBrand(f: Founding) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val co = f.company ?: return
    var pending by remember(f.ref) { mutableStateOf(env.foundingBrand.get(f.ref)) }
    val p = pending ?: return
    if (f.brand.state != "missing" || f.state == "cancelled") return
    val action = rememberAction()
    HqCard(Modifier.fillMaxWidth(), tahrir = true) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            val slot = p.colorIndex?.let { c.chart.getOrNull(it - 1) }
            Box(Modifier.size(56.dp).clip(CircleShape).background(c.tile).border(2.dp, slot ?: c.lineStrong, CircleShape), contentAlignment = Alignment.Center) {
                p.fileId?.let { coil3.compose.AsyncImage(env.media.imageModel(it), "لوگو", env.media.images, Modifier.size(56.dp).clip(CircleShape), contentScale = androidx.compose.ui.layout.ContentScale.Crop) }
                    ?: Fig(co, style = Divan.type.figure, color = slot ?: c.textSecondary)
            }
            Column(Modifier.weight(1f)) {
                Text("لوگو و رنگی که هنگام تأسیس دادی", style = Divan.type.bodyStrong)
                Text("شرکت ساخته شد؛ نشانش را از همین لوگو بساز و رنگش را بگذار. پیش از مُهر آن را در همه‌ی اندازه‌ها می‌بینی.", style = Divan.type.caption, color = c.textSecondary)
            }
        }
        Row(Modifier.padding(top = 10.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            HqButton("از همین بساز", {
                action.run {
                    p.colorIndex?.let { ci -> env.api.patchCompany(env.api.company(co), colorIndex = ci) }
                    p.fileId?.let { id -> env.api.uploadBrand(co, id, "mark", com.coinepro.hq.core.net.BrandOptions(null, 3)) }
                    env.foundingBrand.forget(f.ref)
                    pending = null
                    env.cache.invalidate("brand", "brands", "companies", "founding")
                    toasts.ok("نشان در حال ساخت است؛ همین پایین مُهرش کن.")
                }
            }, variant = BtnVariant.PRIMARY, size = BtnSize.SM, icon = DivanIcon.EDIT, loading = action.busy)
            HqButton("نه، لوگوی دیگری میدهم", { env.foundingBrand.forget(f.ref); pending = null }, variant = BtnVariant.TEXT, size = BtnSize.SM)
        }
    }
}
