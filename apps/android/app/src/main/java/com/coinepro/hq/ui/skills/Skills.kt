package com.coinepro.hq.ui.skills

import com.coinepro.hq.ui.itemMotion
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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
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
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.actorFa
import com.coinepro.hq.core.format.jDate
import com.coinepro.hq.core.net.Skill
import com.coinepro.hq.core.net.companiesOf
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.Md
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.activity
import com.coinepro.hq.ui.media.AttachMenu
import com.coinepro.hq.ui.media.AttachmentTray
import com.coinepro.hq.ui.media.rememberAttachments
import com.coinepro.hq.ui.media.rememberPickers
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v14.HqSheet
import com.coinepro.hq.ui.v14.LabelPill
import com.coinepro.hq.ui.v14.SKILL_STATUS
import com.coinepro.hq.ui.workshop.SpokenField

private val ROLES = listOf(
    "all" to "همه", "ceo" to "مدیرعامل‌ها", "manager" to "مدیرها", "employee" to "کارمندها", "cto" to "مدیر فنی",
    "overseer" to "ناظر", "advisor" to "مشاور", "assistant" to "دستیار",
)
private val CHECKS = mapOf("injection" to "بدون تزریق دستور", "secrets" to "بدون رمز", "conflicts" to "بی‌تناقض با منشور", "policy" to "بدون اختیار اضافه")

private fun rolesFa(rs: List<String>) = rs.joinToString("، ") { r -> ROLES.firstOrNull { it.first == r }?.second ?: r }

/** کتابخانه‌ی مهارت (contract §18.5): the owner writes how agents should work; the overseer reviews it (injection,
 *  secrets, conflicts, extra authority), the academy tests it against the golden set, and the owner activates it. */
@Composable
fun SkillsScreen() {
    val c = Divan.colors
    val q = rememberQuery("skills", "skills", maxAgeMs = 30_000) { skills() }
    val r = refresher(q)
    var filter by rememberSaveable { mutableStateOf<String?>(null) }
    var open by rememberSaveable { mutableStateOf<String?>(null) }
    var creating by rememberSaveable { mutableStateOf(false) }
    val all = q.data

    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item {
            PageHeader("مهارت‌ها", eyebrow = "روش‌هایی که ایجنت‌ها بلدند") {
                HqButton("مهارت تازه", { creating = true }, variant = BtnVariant.PRIMARY, icon = DivanIcon.ADD)
            }
        }
        item { Text("هر مهارت پیش از فعال شدن از بررسی ناظر کل (تزریق دستور، رمز، تناقض، اختیار اضافه) و آزمون طلایی آکادمی میگذرد؛ فعال شدن با مُهر توست.", style = Divan.type.small, color = c.textSecondary) }
        item {
            com.coinepro.hq.designsystem.ScrollRow {
                FilterChip("همه", filter == null, { filter = null }, count = all?.size)
                for (k in listOf("approved", "in_review", "active", "retired")) FilterChip(SKILL_STATUS.getValue(k).fa, filter == k, { filter = k }, count = all.orEmpty().count { it.status == k })
            }
        }
        val list = all.orEmpty().filter { filter == null || it.status == filter }
        when {
            all == null && q.error != null -> item { ErrorBlock(q.error, { q.refresh() }) }
            all == null -> items(3) { Skeleton(Modifier.fillMaxWidth().height(110.dp), radius = 16.dp) }
            list.isEmpty() -> item { Empty("مهارتی نیست", icon = DivanIcon.SKILL) }
            else -> items(list.size, key = { list[it].ref }) { i -> Box(itemMotion()) { SkillCard(list[i]) { open = list[i].ref } }}
        }
    }
    all?.firstOrNull { it.ref == open }?.let { SkillSheet(it) { open = null } }
    if (creating) NewSkillSheet { creating = false }
}

@Composable
private fun SkillCard(s: Skill, onClick: () -> Unit) {
    val c = Divan.colors
    val ready = s.status == "approved"
    val shape = RoundedCornerShape(16.dp)
    Column(
        Modifier.fillMaxWidth().clip(shape).background(if (ready) c.softGold else c.card).then(if (ready) Modifier.border(1.dp, c.goldInk.copy(alpha = 0.4f), shape) else Modifier)
            .clickable(role = Role.Button, onClick = onClick).padding(14.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            DIcon(DivanIcon.SKILL, size = 18.dp, tint = c.goldInk)
            Text(s.nameFa, style = Divan.type.bodyStrong, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
            LabelPill(SKILL_STATUS[s.status], s.status)
        }
        Text(s.summaryFa, style = Divan.type.small, color = c.textSecondary, maxLines = 2, overflow = TextOverflow.Ellipsis)
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Fig(s.ref, style = Divan.type.figureSmall, color = c.textMuted)
            Text(buildAnnotatedString { append("نسخه‌ی "); fig(s.version.toString()) }, style = Divan.type.micro, color = c.textMuted, modifier = Modifier.weight(1f))
            s.eval?.let { e ->
                Text(buildAnnotatedString {
                    append("آزمون "); fig(e.score?.toInt()?.toString() ?: "—", when (e.passed) { true -> c.positive; false -> c.negative; null -> c.textPrimary }); append(" · پایه "); fig(e.baseline?.toInt()?.toString() ?: "—")
                }, style = Divan.type.micro, color = c.textMuted)
            }
        }
    }
}

/** One skill: what it says, the overseer's four checks, the academy's score; activation is sealed on ref@version. */
@Composable
private fun SkillSheet(s: Skill, onClose: () -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val act = activity()
    val c = Divan.colors
    val action = rememberAction()
    HqSheet(onClose, s.nameFa, ref = s.ref) {
        FlowRow(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalArrangement = Arrangement.spacedBy(6.dp), itemVerticalAlignment = Alignment.CenterVertically) {
            LabelPill(SKILL_STATUS[s.status], s.status)
            Text(buildAnnotatedString { append("نسخه‌ی "); fig(s.version.toString()) }, style = Divan.type.caption, color = c.textSecondary)
            Text(rolesFa(s.scope.roles), style = Divan.type.caption, color = c.textSecondary)
            Text(companiesOf(s.scope.companies)?.joinToString("، ") ?: "همه‌ی شرکت‌ها", style = Divan.type.caption, color = c.textSecondary)
        }
        Md(s.bodyMd, Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(14.dp), style = Divan.type.body, color = c.textPrimary)
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Column(Modifier.weight(1f).clip(RoundedCornerShape(12.dp)).border(1.dp, c.lineDivider, RoundedCornerShape(12.dp)).padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("بررسی ناظر", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
                val rv = s.review
                if (rv == null) Text("در صف بررسی", style = Divan.type.caption, color = c.textMuted)
                else {
                    for ((k, ok) in rv.checks) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        DIcon(if (ok) DivanIcon.SEAL else DivanIcon.URGENT, size = 14.dp, tint = if (ok) c.positive else c.negative)
                        Text(CHECKS[k] ?: k, style = Divan.type.caption, color = if (ok) c.positive else c.negative)
                    }
                    Text("${actorFa(rv.by)}، ${jDate(rv.at)}", style = Divan.type.micro, color = c.textMuted)
                }
            }
            Column(Modifier.weight(1f).clip(RoundedCornerShape(12.dp)).border(1.dp, c.lineDivider, RoundedCornerShape(12.dp)).padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("آزمون آکادمی", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
                val e = s.eval
                if (e == null) Text("بعد از بررسی", style = Divan.type.caption, color = c.textMuted)
                else {
                    Fig(e.score?.toInt()?.toString() ?: "—", style = Divan.type.figureL, color = when (e.passed) { true -> c.positive; false -> c.negative; null -> c.textPrimary })
                    Text(buildAnnotatedString { append("خط پایه "); fig(e.baseline?.toInt()?.toString() ?: "—"); append(" · "); fig(e.suite); append(when (e.passed) { true -> " · قبول"; false -> " · رد"; null -> " · بدون خط پایه" }) }, style = Divan.type.micro, color = c.textMuted)
                }
            }
        }
        when (s.status) {
            "approved" -> HqButton("با گذرکلید فعال کن", {
                action.run {
                    env.api.activateSkill(s) { a, t -> env.auth.stepUp(act, a, t) }
                    env.cache.invalidate("skills", "academy")
                    toasts.ok("فعال شد؛ از اجرای بعدی نقش‌ها به کار میرود.")
                    onClose()
                }
            }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, size = BtnSize.LG, icon = DivanIcon.SEAL, loading = action.busy)
            "active" -> HqButton("بازنشسته کن", {
                action.run { env.api.retireSkill(s.ref); env.cache.invalidate("skills"); onClose() }
            }, Modifier.fillMaxWidth(), variant = BtnVariant.GHOST, loading = action.busy)
        }
    }
}

/** A new skill, written or spoken, with helper files; it goes to the overseer's review and the academy's test. */
@Composable
private fun NewSkillSheet(onClose: () -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val action = rememberAction()
    val files = rememberAttachments(5)
    val pick = rememberPickers(files)
    var menu by remember { mutableStateOf(false) }
    var name by rememberSaveable { mutableStateOf("") }
    var body by rememberSaveable { mutableStateOf("") }
    var roles by remember { mutableStateOf(listOf("all")) }
    HqSheet(onClose, "مهارت تازه", sub = "روشی که میخواهی ایجنت‌ها بلد باشند؛ بنویس، بگو یا فایل بده.") {
        HqTextField(name, { name = it }, "نام؛ مثلاً: روش پاسخ به شکایت مشتری", Modifier.fillMaxWidth(), maxLength = 120)
        SpokenField("دستورالعمل (گام‌به‌گام، قابل سنجش)", body, { body = it }, "هر گام یک خط؛ معیار درست انجام شدن را هم بنویس")
        Text("برای کدام نقش‌ها", style = Divan.type.caption, color = c.textMuted)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            for ((k, fa) in ROLES) FilterChip(fa, k in roles, {
                roles = when {
                    k == "all" -> listOf("all")
                    k in roles -> (roles - k).ifEmpty { listOf("all") }
                    else -> roles - "all" + k
                }
            })
        }
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("فایل کمکی (اختیاری)", style = Divan.type.caption, color = c.textMuted, modifier = Modifier.weight(1f))
            Box {
                HqButton("پیوست", { menu = true }, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.ATTACH)
                AttachMenu(menu, { menu = false }, pick)
            }
        }
        AttachmentTray(files)
        HqButton("برای بررسی بفرست", {
            action.run {
                env.api.newSkill(name.trim(), body.trim(), roles, null, files.ids)
                env.cache.invalidate("skills")
                toasts.ok("ثبت شد؛ ناظر بررسی میکند و آزمون آکادمی اجرا میشود.")
                onClose()
            }
        }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, size = BtnSize.LG, icon = DivanIcon.SKILL,
            enabled = name.trim().length >= 3 && body.trim().length >= 20 && !files.uploading, loading = action.busy)
    }
}
