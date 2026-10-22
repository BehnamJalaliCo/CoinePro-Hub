package com.coinepro.hq.ui.feedback

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.IntrinsicSize
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.format.jDate
import com.coinepro.hq.core.net.FeedbackItem
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.CompanyMark
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.LiveDot
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.designsystem.toneColors
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v14.LabelPill
import com.coinepro.hq.ui.v14.Tag
import com.coinepro.hq.ui.v16.ChipRow
import com.coinepro.hq.ui.v16.CompanyChips
import com.coinepro.hq.ui.v16.FEEDBACK_KIND
import com.coinepro.hq.ui.v16.FEEDBACK_STATE
import com.coinepro.hq.ui.v16.Masked
import com.coinepro.hq.ui.v16.go
import com.coinepro.hq.ui.v16.prose

private val WORK = Regex("^W-\\d{3,}$")

/** Where a source opens: a conversation, or the NPS waves. */
private fun sourceRoute(s: String): String? = when {
    s.startsWith("SC-") -> "support/$s"
    s.startsWith("NP-") -> "growth"
    else -> null
}

/** صندوق بازخورد (contract §19.7): from conversations and NPS comments, tagged by rules first; the most frequent first. */
@Composable
fun FeedbackScreen() {
    val env = LocalEnv.current
    val c = Divan.colors
    var company by rememberSaveable { mutableStateOf<String?>(null) }
    var kind by rememberSaveable { mutableStateOf<String?>(null) }
    var state by rememberSaveable { mutableStateOf<String?>(null) }
    val q = rememberQuery("feedback:${company.orEmpty()}:${kind.orEmpty()}:${state.orEmpty()}", "feedback") { feedback(company, kind, state) }
    val r = refresher(q)
    var more by remember(q.data) { mutableStateOf(emptyList<FeedbackItem>()) }
    var cursor by remember(q.data) { mutableStateOf(q.data?.nextCursor) }
    val loadMore = rememberAction()
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item { PageHeader("بازخورد", eyebrow = "از گفت‌وگوهای پشتیبانی و توضیح‌های NPS؛ پرتکرارترین بالا") }
        item {
            Text(
                "برچسب اول با کلیدواژه‌های هر شرکت (بی‌مدل) و بعد با مدل سبک در batch شبانه. موارد هم‌نوع و هم‌حوزه یکی میشوند؛ موردی که به آستانه‌ی شرکت برسد (پیش‌فرض ۵ بار در ۷ روز) یک کار برای مدیر محصول میشود. نقل‌قول‌ها ماسک‌شده‌اند.",
                style = Divan.type.small, color = c.textSecondary,
            )
        }
        item {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                CompanyChips(company, { company = it })
                ChipRow {
                    FilterChip("همه‌ی نوع‌ها", kind == null, { kind = null })
                    for ((k, l) in FEEDBACK_KIND) FilterChip(l.fa, kind == k, { kind = k })
                }
                ChipRow {
                    FilterChip("همه‌ی وضعیت‌ها", state == null, { state = null })
                    for ((k, l) in FEEDBACK_STATE) FilterChip(l.fa, state == k, { state = k })
                }
            }
        }
        val list = q.data?.items?.let { (it + more).sortedByDescending { x -> x.count } }
        when {
            list == null && q.error != null -> item { ErrorBlock(q.error, { q.refresh() }) }
            list == null -> items(3) { Skeleton(Modifier.fillMaxWidth().height(180.dp), radius = 16.dp) }
            list.isEmpty() -> item { Empty("بازخوردی نیست", icon = DivanIcon.RATE) }
            else -> items(list.size, key = { list[it].ref }) { i -> Item(list[i]) }
        }
        cursor?.let { at ->
            item {
                HqButton("بیشتر", {
                    loadMore.run {
                        val pg = env.api.feedback(company, kind, state, cursor = at)
                        more = more + pg.items
                        cursor = pg.nextCursor
                    }
                }, variant = BtnVariant.SECONDARY, size = BtnSize.SM, loading = loadMore.busy)
            }
        }
    }
}

@Composable
private fun Item(x: FeedbackItem) {
    val env = LocalEnv.current
    val nav = LocalNav.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val action = rememberAction()
    var work by remember(x.ref) { mutableStateOf("") }
    var menu by remember { mutableStateOf(false) }
    fun save(state: String? = null, workRef: String? = null, setWork: Boolean = false, ok: String) = action.go(toasts) {
        env.api.patchFeedback(x, state, workRef, setWork)
        work = ""
        env.cache.invalidate("feedback")
        toasts.ok(ok)
    }
    Column(
        Modifier.fillMaxWidth().alpha(if (x.state == "done" || x.state == "wont_do") 0.75f else 1f).clip(RoundedCornerShape(16.dp)).background(c.card).padding(14.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            Column(Modifier.width(56.dp).clip(RoundedCornerShape(12.dp)).background(c.tile).padding(vertical = 8.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                Fig(x.count.toString(), style = Divan.type.figureM.copy(fontSize = 20.sp), color = c.textPrimary)
                Text("بار", style = Divan.type.micro.copy(fontSize = 10.sp), color = c.textMuted)
            }
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp), itemVerticalAlignment = Alignment.CenterVertically) {
                    LabelPill(FEEDBACK_KIND[x.kind], x.kind)
                    Tag(x.area, figure = true)
                    CompanyMark(x.company, height = 12.dp, mono = true, ink = c.textSecondary)
                }
                Text(prose(x.titleFa), style = Divan.type.bodyStrong, color = c.textPrimary)
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(2.dp), itemVerticalAlignment = Alignment.CenterVertically) {
                    Fig(x.ref, style = Divan.type.figureSmall, color = c.textMuted)
                    Text("اولین بار ${jDate(x.firstSeen)}", style = Divan.type.micro, color = c.textMuted)
                    Text("آخرین بار ${ago(x.lastSeen)}", style = Divan.type.micro, color = c.textMuted)
                }
            }
        }
        if (x.quotes.isNotEmpty()) Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            for (quote in x.quotes) Row(Modifier.height(IntrinsicSize.Min), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Box(Modifier.width(2.dp).fillMaxHeight().background(c.lineStrong))
                Masked("«$quote»", style = Divan.type.small, color = c.textSecondary, modifier = Modifier.weight(1f))
            }
        }
        if (x.sources.isNotEmpty()) FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp), itemVerticalAlignment = Alignment.CenterVertically) {
            Text("منبع:", style = Divan.type.micro, color = c.textMuted)
            for (s in x.sources) {
                val route = sourceRoute(s)
                Fig(
                    s, Modifier.clip(CircleShape).background(c.tile).then(if (route != null) Modifier.clickable(role = Role.Button) { nav.go(route) } else Modifier).padding(horizontal = 8.dp, vertical = 2.dp),
                    style = Divan.type.figureSmall, color = if (route != null) c.goldInk else c.textSecondary,
                )
            }
        }
        HorizontalDivider(color = c.lineDivider)
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            // The state, as a menu: the web's select.
            Box {
                val l = FEEDBACK_STATE[x.state]
                val (bg, fg) = toneColors(l?.tone ?: com.coinepro.hq.core.format.Tone.NEUTRAL)
                Row(
                    Modifier.height(36.dp).clip(RoundedCornerShape(10.dp)).background(bg).border(1.dp, c.lineStrong, RoundedCornerShape(10.dp))
                        .clickable(role = Role.Button, enabled = !action.busy, onClickLabel = "وضعیت ${x.ref}") { menu = true }.padding(horizontal = 10.dp),
                    verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    LiveDot(fg, live = false)
                    Text(l?.fa ?: x.state, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = fg)
                    DIcon(DivanIcon.CHEVRON, size = 14.dp, tint = fg)
                }
                DropdownMenu(menu, { menu = false }, containerColor = c.overlay) {
                    for ((k, s) in FEEDBACK_STATE) DropdownMenuItem(
                        text = { Text(s.fa, style = Divan.type.body, color = if (k == x.state) c.goldInk else c.textPrimary) },
                        onClick = { menu = false; if (k != x.state) save(state = k, ok = "وضعیت به‌روز شد.") },
                    )
                }
            }
            val linked = x.workRef
            if (linked != null) {
                Fig(
                    linked, Modifier.clip(CircleShape).background(c.softGold).clickable(role = Role.Button) { nav.go("work/$linked") }.padding(horizontal = 10.dp, vertical = 4.dp),
                    style = Divan.type.figureSmall.copy(fontWeight = FontWeight.SemiBold), color = c.goldInk,
                )
                HqButton("جدا کن", { save(workRef = null, setWork = true, ok = "از کار جدا شد.") }, variant = BtnVariant.GHOST, size = BtnSize.SM)
            } else {
                HqTextField(work, { work = it.uppercase().trim() }, "W-000123", Modifier.weight(1f), maxLength = 12, figure = true)
                HqButton("وصل به کار", {
                    // Linking moves a fresh item into the backlog, as the web does.
                    save(state = if (x.state == "new" || x.state == "triaged") "in_backlog" else null, workRef = work, setWork = true, ok = "به کار وصل شد.")
                }, variant = BtnVariant.SECONDARY, size = BtnSize.SM, enabled = WORK.matches(work), loading = action.busy)
            }
        }
    }
}
