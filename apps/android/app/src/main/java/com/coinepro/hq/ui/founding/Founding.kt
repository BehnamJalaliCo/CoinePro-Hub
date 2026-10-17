package com.coinepro.hq.ui.founding

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
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.format.jTime
import com.coinepro.hq.core.format.modelLabel
import com.coinepro.hq.core.format.roleFa
import com.coinepro.hq.core.format.usd
import com.coinepro.hq.core.net.Founding
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

private val STAGES = listOf("auditing" to "ممیزی", "proposed" to "پیشنهاد", "sealed" to "مُهر", "provisioning" to "ساخت سرور", "ready_for_login" to "ورود تو", "active" to "فعال")
private val AUDIT_FA = mapOf("architecture" to "معماری", "quality" to "کیفیت", "security" to "امنیت", "tests" to "تست‌ها", "debt" to "بدهی فنی")
private val SOFTWARE_FA = mapOf(
    "system-upgrade" to "به‌روزرسانی و ارتقای کامل سیستم", "unattended-upgrades" to "به‌روزرسانی خودکار امنیتی", "work-user" to "کاربر کاری",
    "ssh-hardening" to "سخت‌سازی SSH (فقط کلید، بدون root)", "docker" to "Docker", "git" to "Git", "node-lts" to "Node LTS",
    "claude-code" to "Claude Code (ورود با حساب خودت)", "repo-clone" to "clone ریپوی شرکت", "private-network" to "شبکه‌ی خصوصی هتزنر",
    "hetzner-firewall" to "فایروال هتزنر", "node-exporter" to "پایش (فقط روی IP خصوصی)",
)
private val PATH = listOf(
    Triple("ممیزی", "جلسه‌ی فقط‌خواندنی کارگاه روی ریپو: کد، وابستگی‌ها، ریسک‌ها، هزینه.", false),
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
    val q = rememberQuery("founding:list", "founding", maxAgeMs = 15_000) { foundings().items }
    val r = refresher(q)
    var start by rememberSaveable { mutableStateOf(false) }
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item {
            PageHeader("تأسیس شرکت", eyebrow = "از ریپو یا ایده تا شرکت فعال و سرور آماده") {
                HqButton("تأسیس تازه", { start = true }, variant = BtnVariant.PRIMARY, icon = DivanIcon.ADD)
            }
        }
        item { Text("ممیزی، پیشنهاد ساختار و تیم و نقشه‌ی راه، مُهر تو، و ساخت کامل سرور با API هتزنر (به‌روزرسانی، نصب و Claude Code آماده). بعد خودت وارد میشوی و ادامه میدهیم. رمز سرور هیچ‌وقت به ایجنت نمیرسد.", style = Divan.type.small, color = c.textSecondary) }
        val list = q.data
        when {
            list == null && q.error != null -> item { ErrorBlock(q.error, { q.refresh() }) }
            list == null -> items(2) { Skeleton(Modifier.fillMaxWidth().height(76.dp), radius = 16.dp) }
            list.isEmpty() -> item { Empty("هنوز تأسیسی نیست", icon = DivanIcon.FOUND) }
            else -> items(list.size, key = { list[it].ref }) { i ->
                val f = list[i]
                val gold = f.state == "ready_for_login" || f.state == "proposed"
                Column(
                    Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(if (gold) c.softGold else c.card).clickable(role = Role.Button) { nav.go("founding/${f.ref}") }.padding(14.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        DIcon(DivanIcon.FOUND, size = 18.dp, tint = c.goldInk)
                        Text(f.nameFa, style = Divan.type.bodyStrong, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
                        LabelPill(FOUNDING_STATE[f.state], f.state)
                    }
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Fig(f.ref, style = Divan.type.figureSmall, color = c.textMuted)
                        if (f.source.repo != null) Fig(f.source.repo, Modifier.weight(1f), style = Divan.type.figureSmall, color = c.textMuted)
                        else Text("ایده", style = Divan.type.micro, color = c.textMuted, modifier = Modifier.weight(1f))
                        Text(ago(f.updatedAt), style = Divan.type.micro, color = c.textMuted)
                    }
                }
            }
        }
        item { SectionTitle("مسیر تأسیس", note = "سه نقطه با توست؛ بقیه را ایجنت‌ها انجام میدهند و همه در دفتر Audit ثبت میشود") }
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
    if (start) StartSheet { start = false }
}

@Composable
private fun StartSheet(onClose: () -> Unit) {
    val env = LocalEnv.current
    val nav = LocalNav.current
    val c = Divan.colors
    val action = rememberAction()
    var kind by rememberSaveable { mutableStateOf("repo") }
    var repo by rememberSaveable { mutableStateOf("") }
    var brief by rememberSaveable { mutableStateOf("") }
    val clean = repo.trim().removePrefix("https://github.com/").removeSuffix(".git")
    val ok = if (kind == "repo") Regex("^[\\w.-]+/[\\w.-]+$").matches(clean) else brief.trim().length >= 10
    HqSheet(onClose, "تأسیس شرکت تازه", sub = "از روی یک ریپو یا یک ایده؛ ممیزی و پیشنهاد کامل به کارتابلت میاید.") {
        Segmented(listOf(SegOption("repo", "ریپوی GitHub"), SegOption("idea", "ایده")), kind, { kind = it }, Modifier.fillMaxWidth())
        if (kind == "repo") HqTextField(repo, { repo = it }, "owner/name", Modifier.fillMaxWidth(), maxLength = 200, figure = true)
        SpokenField(if (kind == "repo") "چه میخواهی از این شرکت (اختیاری)" else "ایده و هدف", brief, { brief = it }, "هدف، مشتری، درآمد، محدودیت‌ها")
        Text("ممیزی فقط‌خواندنی است. شرکت فقط با مُهر تو ساخته میشود و سرور با مُهر جدا (هزینه‌ی واقعی).", style = Divan.type.caption, color = c.textMuted)
        HqButton("شروع کن", {
            action.run {
                val f = env.api.startFounding(kind, if (kind == "repo") clean else null, brief.trim())
                env.cache.invalidate("founding")
                onClose()
                nav.go("founding/${f.ref}")
            }
        }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, size = BtnSize.LG, icon = DivanIcon.FOUND, enabled = ok, loading = action.busy)
    }
}

/** One founding, from audit to an active company (contract §18.8). The server plan is sealed on its digest; the build
 *  runs live; the owner logs in personally before the company is activated. */
@Composable
fun FoundingScreen(ref: String) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val act = activity()
    val c = Divan.colors
    val q = rememberQuery("founding:$ref", "founding", maxAgeMs = 5_000) { founding(ref) }
    val f = q.data
    val plan = f?.plan?.let { p -> rememberQuery("founding:plan:$p", "founding") { plan(p) } }
    val runId = plan?.data?.run
    val run = runId?.let { id -> rememberQuery("founding:run:$id", "founding", maxAgeMs = 2_000) { run(id) } }
    val action = rememberAction()
    var cancel by remember { mutableStateOf(false) }
    // Live while something moves: the audit, the build (every 2 s), until the server is ready.
    LaunchedEffect(f?.state, run?.data?.state) {
        while (f?.state in setOf("auditing", "sealed", "provisioning") || run?.data?.state == "running") {
            delay(if (run?.data?.state == "running") 2_000 else 5_000)
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
                item { Header(f) { cancel = true } }
                item { Stepper(f.state) }
                val login = run?.data?.login
                if (f.state == "ready_for_login" && login != null) item {
                    HqCard(Modifier.fillMaxWidth(), tahrir = true) {
                        SectionTitle("سرور آماده است؛ نوبت توست", note = "در ترمینال خودت وارد شو و Claude Code را با حساب خودت باز کن")
                        Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            Text("۱. وارد سرور شو", style = Divan.type.small, color = c.textSecondary)
                            CopyLine(login.ssh)
                            Text("۲. Claude Code را باز کن و با حساب خودت وارد شو", style = Divan.type.small, color = c.textSecondary)
                            for (cmd in login.then) CopyLine(cmd)
                            Text("۳. وقتی وارد شدی، شرکت را فعال کن تا مدیرعامل شروع کند.", style = Divan.type.small, color = c.textSecondary)
                            HqButton("وارد شدم؛ شرکت را فعال کن", {
                                action.run {
                                    env.api.activateFounding(f.ref) { a, t -> env.auth.stepUp(act, a, t) }
                                    env.cache.invalidate("founding", "companies")
                                    toasts.ok("شرکت فعال شد؛ مدیرعامل شروع به کار کرد.")
                                }
                            }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, size = BtnSize.LG, icon = DivanIcon.SEAL, loading = action.busy)
                        }
                    }
                }
                f.audit?.let { a ->
                    item {
                        HqCard(Modifier.fillMaxWidth()) {
                            SectionTitle("ممیزی", note = "جلسه‌ی فقط‌خواندنی کارگاه") { Fig(a.sessionRef, style = Divan.type.figureSmall, color = c.goldInk) }
                            Column(Modifier.padding(vertical = 10.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                for (pair in a.scores.entries.chunked(2)) Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                                    for ((k, v) in pair) Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                                        Text(AUDIT_FA[k] ?: k, style = Divan.type.micro, color = c.textMuted)
                                        ScoreBar(v)
                                    }
                                    if (pair.size == 1) Box(Modifier.weight(1f))
                                }
                            }
                            Md(a.reportMd)
                        }
                    }
                }
                if (f.audit == null && f.state == "auditing") item {
                    HqCard(Modifier.fillMaxWidth()) {
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                            CircularProgressIndicator(Modifier.size(16.dp), color = c.goldInk, strokeWidth = 2.dp)
                            Text("ممیزی در جریان است؛ نتیجه و پیشنهاد به کارتابلت میاید.", style = Divan.type.small, color = c.textSecondary)
                        }
                    }
                }
                f.proposal?.let { p -> item { Proposal(f, p) } }
                plan?.let { pq ->
                    item {
                        val pl = pq.data
                        if (pl == null) Skeleton(Modifier.fillMaxWidth().height(200.dp), radius = 16.dp)
                        else HqCard(Modifier.fillMaxWidth()) {
                            SectionTitle("سرور") {
                                Fig("€" + String.format(Locale.US, "%.2f", pl.monthlyEur) + " / ماه", style = Divan.type.figure.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
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
                                Fig("${w.protocol} ${w.port}", Modifier.width(76.dp), style = Divan.type.figureSmall, color = c.textPrimary)
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
                            if (pl.state == "proposed") HqButton("با گذرکلید مُهر کن و بساز (€${String.format(Locale.US, "%.2f", pl.monthlyEur)} در ماه)", {
                                action.run {
                                    env.api.sealPlan(pl) { a, t -> env.auth.stepUp(act, a, t) }
                                    env.cache.invalidate("founding")
                                    toasts.ok("مُهر شد؛ ساخت سرور شروع شد.")
                                }
                            }, Modifier.fillMaxWidth().padding(top = 12.dp), variant = BtnVariant.PRIMARY, size = BtnSize.LG, icon = DivanIcon.SEAL, loading = action.busy)
                            run?.data?.let { rn ->
                                HorizontalDivider(Modifier.padding(vertical = 12.dp), color = c.lineDivider)
                                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                    Text("ساخت", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
                                    when (rn.state) {
                                        "running" -> Pill("در جریان", com.coinepro.hq.core.format.Tone.LAPIS, live = true)
                                        "done" -> Pill("تمام شد", com.coinepro.hq.core.format.Tone.POS, dot = true)
                                        else -> Pill("خطا", com.coinepro.hq.core.format.Tone.NEG, dot = true)
                                    }
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
                                            if (s.logTail.isNotBlank()) Text(s.logTail, style = Divan.type.figureSmall.copy(textDirection = TextDirection.Ltr), color = c.textMuted)
                                        }
                                        s.finishedAt?.let { Text(jTime(it), style = Divan.type.micro, color = c.textMuted) }
                                    }
                                }
                                rn.server?.let { sv -> Fig(listOfNotNull(sv.name, sv.ipv4, sv.privateIp).joinToString(" · "), Modifier.padding(top = 10.dp), style = Divan.type.figureSmall, color = c.textSecondary) }
                            }
                        }
                    }
                }
            }
        }
    }
    if (cancel && f != null) AlertDialog(
        onDismissRequest = { cancel = false },
        containerColor = c.overlay,
        title = { Text("این تأسیس لغو شود؟", style = Divan.type.h3) },
        text = { Text("ممیزی و پیشنهاد در سوابق میماند. هنوز سروری ساخته نشده و هزینه‌ای نیست.", style = Divan.type.small, color = c.textSecondary) },
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
private fun Header(f: Founding, onCancel: () -> Unit) {
    val c = Divan.colors
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Box(Modifier.size(48.dp).clip(CircleShape).background(c.softGold), contentAlignment = Alignment.Center) { DIcon(DivanIcon.FOUND, size = 24.dp, tint = c.goldInk) }
            Column(Modifier.weight(1f)) {
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Fig(f.ref, style = Divan.type.figureSmall, color = c.textMuted)
                    if (f.source.repo != null) Fig(f.source.repo, style = Divan.type.figureSmall, color = c.textMuted) else Text("ایده", style = Divan.type.micro, color = c.textMuted)
                }
                Text(f.nameFa, style = Divan.type.h1)
                if (f.nameEn.isNotBlank()) Fig(f.nameEn, style = Divan.type.figureSmall, color = c.textMuted)
            }
        }
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            LabelPill(FOUNDING_STATE[f.state], f.state)
            Box(Modifier.weight(1f))
            // Before a server exists nothing is spent, so cancelling is safe; afterwards only the owner removes servers, in Hetzner.
            if (f.state == "auditing" || f.state == "proposed") HqButton("لغو تأسیس", onCancel, variant = BtnVariant.GHOST, size = BtnSize.SM)
        }
    }
}

@Composable
private fun Stepper(state: String) {
    val c = Divan.colors
    val at = STAGES.indexOfFirst { it.first == state }
    Row(Modifier.horizontalScroll(rememberScrollState()), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        STAGES.forEachIndexed { i, (_, fa) ->
            val (bg, fg) = when { i < at -> c.softPositive to c.positive; i == at -> c.softGold to c.goldInk; else -> c.tile to c.textMuted }
            Row(Modifier.height(28.dp).clip(CircleShape).background(bg).padding(horizontal = 10.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(5.dp)) {
                if (i < at) DIcon(DivanIcon.SEAL, size = 12.dp, tint = fg, active = true) else Text("${i + 1}", style = Divan.type.micro, color = fg)
                Text(fa, style = Divan.type.caption.copy(fontWeight = if (i == at) FontWeight.SemiBold else FontWeight.Normal), color = fg)
            }
            if (i < STAGES.lastIndex) Box(Modifier.width(8.dp).height(1.dp).background(c.lineDivider))
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
