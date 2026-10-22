package com.coinepro.hq.ui.advisor

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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.format.jDate
import com.coinepro.hq.core.format.jTime
import com.coinepro.hq.core.net.AgendaItem
import com.coinepro.hq.core.net.WeeklyReview
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqSwitch
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.RichText
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.messages.ChatScreen
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v14.HqSheet
import com.coinepro.hq.ui.v14.LabelPill
import com.coinepro.hq.ui.v17.CoMark
import com.coinepro.hq.ui.v17.Named
import com.coinepro.hq.ui.v17.RefChip
import com.coinepro.hq.ui.v17.RefTone
import com.coinepro.hq.ui.v18.AGENDA
import com.coinepro.hq.ui.v18.ITEM_STATUS
import com.coinepro.hq.ui.v18.MEMO_STATE
import com.coinepro.hq.ui.v18.PlayerName
import com.coinepro.hq.ui.v18.REC
import com.coinepro.hq.ui.v18.REVIEW_STATE
import com.coinepro.hq.ui.v18.TRIGGER
import com.coinepro.hq.ui.v18.TRIGGER_STATE
import com.coinepro.hq.ui.v18.mgmt
import java.util.Locale
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.doubleOrNull

// مشاور کل with contract §21: the decision memos with the substitutes' second and third opinions, the devil's advocate, proactive notes
// and the weekly review (§21.1, §21.3). Mirrors apps/web/src/app/(app)/advisor/page.tsx and components/v18/advisor.tsx.

private fun weekFa(week: String): String = jDate("${week}T08:00:00Z")

/** The advisor's thread with its tools: the devil's-advocate switch, the weekly review, the memos, the proactive notes and the
 *  formal inquiries; the review's banner while it is open. */
@Composable
fun AdvisorScreen() {
    var devil by rememberSaveable { mutableStateOf(false) }
    var sheet by remember { mutableStateOf<String?>(null) }
    ChatScreen(
        "A", advisor = true, mode = if (devil) "devil" else null,
        placeholder = if (devil) "بپرس چرا نه… (مشاور مخالف‌خوانی میکند)" else null,
        subHeader = {
            Column(Modifier.fillMaxWidth().padding(bottom = 10.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(horizontal = 16.dp), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                    DevilChip(devil) { devil = it }
                    ToolChip("مرور هفتگی") { sheet = "review" }
                    ToolChip("یادداشت‌های تصمیم") { sheet = "memos" }
                    ToolChip("گزارش‌های فعال") { sheet = "triggers" }
                    ToolChip("پرسش‌های رسمی") { sheet = "inquiries" }
                }
                ReviewBanner { sheet = "review" }
                if (devil) Text(
                    "حالت مخالف‌خوان: مشاور فقط برای همین پیام‌ها قوی‌ترین استدلال «چرا نه» را میاورد. پیام‌ها برچسب میگیرند.",
                    Modifier.padding(horizontal = 16.dp).fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(Divan.colors.softNegative).padding(horizontal = 12.dp, vertical = 8.dp),
                    style = Divan.type.caption, color = Divan.colors.textPrimary,
                )
            }
        },
    )
    when (sheet) {
        "review" -> HqSheet({ sheet = null }, "مرور هفتگی", sub = "دستور را کد ۳۰ دقیقه پیش از وقتش میسازد (حداکثر ۱۲ مورد)؛ کارهایی که در جلسه میکنی رکورد عادی خودشان را میسازند.") { ReviewContent() }
        "memos" -> HqSheet({ sheet = null }, "یادداشت‌های تصمیم", sub = "خودکار برای کارت‌های پرریسک، انتشار، تأسیس و طرح سرور (حداکثر ۳ در روز)؛ بقیه به درخواست تو از روی کارت.") { MemosContent { sheet = null } }
        "triggers" -> HqSheet({ sheet = null }, "گزارش‌های فعال مشاور", sub = "محرک‌ها کد هستند، بی‌مدل؛ هر کلید روزی یک بار. حداکثر ۳ پیام در روز، هرگز فوری؛ بقیه «بالای سقف» ثبت میشوند.") { TriggersContent() }
        "inquiries" -> InquiriesSheet { sheet = null }
    }
}

@Composable
private fun ToolChip(text: String, onClick: () -> Unit) {
    val c = Divan.colors
    Text(
        text, Modifier.height(32.dp).clip(CircleShape).border(1.dp, c.lineStrong, CircleShape).clickable(role = Role.Button, onClick = onClick).padding(horizontal = 12.dp, vertical = 6.dp),
        style = Divan.type.small, color = c.textSecondary, maxLines = 1,
    )
}

@Composable
private fun DevilChip(on: Boolean, onChange: (Boolean) -> Unit) {
    val c = Divan.colors
    Row(
        Modifier.height(32.dp).clip(CircleShape).background(if (on) c.softNegative else c.page).border(1.dp, if (on) c.softNegative else c.lineStrong, CircleShape).padding(start = 4.dp, end = 12.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        HqSwitch(on, onChange, "حالت مخالف‌خوان")
        Text("مخالف‌خوان", style = Divan.type.small.copy(fontWeight = if (on) FontWeight.SemiBold else FontWeight.Normal), color = if (on) c.negative else c.textSecondary)
    }
}

// ------------------------------------------------------------ the weekly review (§21.3) --
/** A slim line under the advisor's header while this week's review is open. */
@Composable
fun ReviewBanner(onOpen: () -> Unit) {
    val c = Divan.colors
    val q = rememberQuery("reviews:current", "reviews", maxAgeMs = 120_000) { currentReview() }
    val r = q.data ?: return
    if (r.state != "ready" && r.state != "in_progress") return
    val open = r.agenda.count { it.status == "open" }
    Row(
        Modifier.padding(horizontal = 16.dp).fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(c.softGold).clickable(role = Role.Button, onClick = onOpen).padding(horizontal = 12.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Box(Modifier.size(36.dp).clip(CircleShape).background(c.card), contentAlignment = Alignment.Center) { DIcon(DivanIcon.PLANNER, size = 18.dp, tint = c.goldInk) }
        Column(Modifier.weight(1f)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("مرور هفتگی", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                Fig(r.ref, style = Divan.type.figureSmall, color = c.textPrimary)
                Text("هفته‌ی ${weekFa(r.week)}", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, maxLines = 1)
            }
            Text("${r.agenda.size} مورد، $open باز؛ حدود ۱۵ دقیقه", style = Divan.type.caption, color = c.textSecondary)
        }
        val st = REVIEW_STATE[r.state]
        Pill(if (r.state == "ready") "شروع" else "ادامه", st?.tone ?: Tone.GOLD, live = st?.live == true, dot = st?.live != true)
    }
}

@Composable
private fun AgendaRow(r: WeeklyReview, it: AgendaItem, live: Boolean, onChanged: (WeeklyReview) -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val action = rememberAction()
    var note by rememberSaveable(it.n) { mutableStateOf(it.ownerNote.orEmpty()) }
    var editing by rememberSaveable(it.n) { mutableStateOf(false) }
    val k = AGENDA[it.kind] ?: Named(it.kind, DivanIcon.INFO)
    fun set(status: String) = action.mgmt(toasts) {
        onChanged(env.api.reviewItem(r, it.n, status, if (editing) note.trim() else null))
        editing = false
        env.cache.invalidate("reviews")
    }
    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(if (it.status == "open") c.tile else c.card).padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Fig("${it.n}", Modifier.width(18.dp).padding(top = 2.dp), style = Divan.type.figureSmall, color = c.textMuted)
            DIcon(k.icon, size = 16.dp, tint = c.goldInk, modifier = Modifier.padding(top = 2.dp))
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                RichText(it.titleFa, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                RichText(it.whyFa, style = Divan.type.caption, color = c.textSecondary)
                Row(Modifier.padding(top = 2.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    it.company?.let { co -> CoMark(co, height = 11.dp) }
                    if (it.ref.isNotBlank()) RefChip(it.ref, tone = RefTone.NEUTRAL)
                }
            }
            LabelPill(ITEM_STATUS[it.status], it.status)
        }
        if (!it.ownerNote.isNullOrBlank() && !editing) Text("یادداشت تو: ${it.ownerNote}", Modifier.padding(start = 26.dp), style = Divan.type.caption, color = c.textMuted)
        if (live) Column(Modifier.padding(start = 26.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            if (editing) HqTextField(note, { note = it }, "یادداشت تو برای صورت‌جلسه", Modifier.fillMaxWidth(), singleLine = false, minLines = 2, maxLength = 500)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                if (it.status != "done") HqButton("انجام شد", { set("done") }, size = BtnSize.SM, icon = DivanIcon.SEAL, loading = action.busy)
                if (it.status != "deferred") HqButton("هفته‌ی بعد", { set("deferred") }, size = BtnSize.SM, variant = BtnVariant.GHOST, icon = DivanIcon.TIME)
                if (it.status != "open") HqButton("باز کن", { set("open") }, size = BtnSize.SM, variant = BtnVariant.GHOST, icon = DivanIcon.REFRESH)
                HqButton(if (editing) "بی‌یادداشت" else "یادداشت", { editing = !editing }, size = BtnSize.SM, variant = BtnVariant.GHOST, icon = DivanIcon.EDIT)
            }
        }
    }
}

/** «مرور هفتگی با مشاور»: an agenda built by code, gone through item by item; finishing writes the minutes as a deliverable. */
@Composable
fun ReviewContent() {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val cur = rememberQuery("reviews:current", "reviews", maxAgeMs = 0) { currentReview() }
    val all = rememberQuery("reviews:list", "reviews") { weeklyReviews() }
    val action = rememberAction()
    val r = cur.data
    when {
        r == null && cur.state.loading -> Skeleton(Modifier.fillMaxWidth().height(240.dp), radius = 12.dp)
        r == null -> Empty("مرور این هفته هنوز ساخته نشده", icon = DivanIcon.PLANNER, body = "شنبه ساعت ۱۰ (تنظیمات)؛ دستورش ۳۰ دقیقه پیش‌تر ساخته میشود.")
        else -> Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            val live = r.state == "in_progress"
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(6.dp), itemVerticalAlignment = Alignment.CenterVertically) {
                Fig(r.ref, style = Divan.type.figureSmall, color = c.textMuted)
                LabelPill(REVIEW_STATE[r.state], r.state)
                Text("هفته‌ی ${weekFa(r.week)}", style = Divan.type.caption, color = c.textSecondary)
                r.startedAt?.let { Text("شروع ${jTime(it)}", style = Divan.type.caption, color = c.textSecondary) }
                r.briefMessageRef?.let { Fig(it, style = Divan.type.figureSmall, color = c.goldInk) }
                r.minutesRef?.let { RefChip(it, note = "صورت‌جلسه") }
            }
            if (r.state == "ready") {
                Text("برای علامت زدن موردها، مرور را شروع کن؛ مدت جلسه در صورت‌جلسه میماند.", style = Divan.type.caption, color = c.textMuted)
                HqButton("شروع مرور", {
                    action.mgmt(toasts) { cur.set(env.api.startReview(r.ref)); env.cache.invalidate("reviews"); toasts.ok("مرور شروع شد؛ مورد به مورد جلو برو.") }
                }, variant = BtnVariant.PRIMARY, icon = DivanIcon.RESUME, loading = action.busy)
            }
            if (live) HqButton("پایان و صورت‌جلسه", {
                action.mgmt(toasts) {
                    val out = env.api.finishReview(r.ref)
                    cur.set(out)
                    env.cache.invalidate("reviews", "deliverables")
                    toasts.ok("مرور تمام شد؛ صورت‌جلسه ${out.minutesRef ?: ""} ثبت شد.")
                }
            }, variant = BtnVariant.PRIMARY, icon = DivanIcon.SEAL, loading = action.busy)
            r.agenda.sortedBy { it.n }.forEach { AgendaRow(r, it, live) { x -> cur.set(x) } }
            val past = all.data.orEmpty().filter { it.ref != r.ref }
            if (past.isNotEmpty()) {
                Text("مرورهای قبل", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
                past.forEach { x ->
                    Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(c.tile).padding(horizontal = 12.dp, vertical = 8.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Fig(x.ref, style = Divan.type.figureSmall, color = c.textMuted)
                        Text("هفته‌ی ${weekFa(x.week)}", Modifier.weight(1f), style = Divan.type.caption, color = c.textPrimary)
                        x.durationS?.let { Text("${(it + 30) / 60} دقیقه", style = Divan.type.micro, color = c.textMuted) }
                        x.minutesRef?.let { RefChip(it) }
                        LabelPill(REVIEW_STATE[x.state], x.state)
                    }
                }
            }
        }
    }
}

// ------------------------------------------------------------------ memos (§21.1) --
@Composable
fun MemosContent(onOpen: () -> Unit = {}) {
    val nav = LocalNav.current
    val c = Divan.colors
    val q = rememberQuery("memos:list", "memos") { memos().items }
    val list = q.data
    when {
        list == null -> Skeleton(Modifier.fillMaxWidth().height(200.dp), radius = 12.dp)
        list.isEmpty() -> Empty("هنوز یادداشتی نیست", icon = DivanIcon.ADVISOR)
        else -> list.forEach { m ->
            Column(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).clickable(role = Role.Button) { onOpen(); nav.go("cartable/${m.decision}") }.padding(12.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp), itemVerticalAlignment = Alignment.CenterVertically) {
                    Fig(m.ref, style = Divan.type.figureSmall, color = c.textMuted)
                    Fig(m.decision, style = Divan.type.figureSmall, color = c.goldInk)
                    Text(if (m.mode == "devil") "مخالف‌خوان" else "استاندارد", style = Divan.type.micro, color = c.textMuted)
                    Text(if (m.trigger == "auto") "خودکار" else "درخواست تو", style = Divan.type.micro, color = c.textMuted)
                    Text(ago(m.createdAt), style = Divan.type.micro, color = c.textMuted)
                }
                if (m.summaryFa.isNotBlank()) RichText(m.summaryFa, style = Divan.type.small, color = c.textPrimary) else Text("در حال نوشتن…", style = Divan.type.small, color = c.textMuted)
                FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp), itemVerticalAlignment = Alignment.CenterVertically) {
                    if (m.state != "ready") LabelPill(MEMO_STATE[m.state], m.state) else LabelPill(REC[m.recommendation] ?: REC.getValue("ask"))
                    for (o in listOfNotNull(m.secondOpinion, m.thirdOpinion)) {
                        Row(Modifier.clip(CircleShape).background(if (o.agrees) c.softPositive else c.softWarning).padding(horizontal = 8.dp, vertical = 2.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                            PlayerName(o.player, size = 11.dp, color = if (o.agrees) c.positive else c.warning)
                            Text(if (o.agrees) "هم‌نظر" else "اختلاف", style = Divan.type.micro, color = if (o.agrees) c.positive else c.warning)
                        }
                    }
                }
            }
        }
    }
}

// ----------------------------------------------------------- proactive notes (§21.1) --
private fun factLine(f: kotlinx.serialization.json.JsonObject): String = f.entries.joinToString(" · ") { (k, v) ->
    val n = (v as? JsonPrimitive)?.takeIf { !it.isString }?.doubleOrNull
    "$k: " + if (n != null && n > 9999) String.format(Locale.US, "%,.0f", n) else (v as? JsonPrimitive)?.content ?: v.toString()
}

@Composable
fun TriggersContent() {
    val c = Divan.colors
    val q = rememberQuery("advisor:triggers", "advisor", maxAgeMs = 120_000) { advisorTriggers() }
    val list = q.data
    when {
        list == null -> Skeleton(Modifier.fillMaxWidth().height(160.dp), radius = 12.dp)
        list.isEmpty() -> Empty("امروز محرکی روشن نشده", icon = DivanIcon.BELL)
        else -> list.forEach { t ->
            val k = TRIGGER[t.kind] ?: Named(t.kind, DivanIcon.BELL)
            Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    DIcon(k.icon, size = 16.dp, tint = c.goldInk)
                    Text(k.fa, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                    t.company?.let { CoMark(it, height = 11.dp) }
                    Box(Modifier.weight(1f))
                    LabelPill(TRIGGER_STATE[t.state], t.state)
                }
                Fig(factLine(t.facts), Modifier.fillMaxWidth(), style = Divan.type.figureSmall, color = c.textMuted, maxLines = 3)
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(ago(t.firedAt), style = Divan.type.micro, color = c.textMuted)
                    t.messageRef?.let { Fig(it, style = Divan.type.figureSmall, color = c.goldInk) }
                }
            }
        }
    }
}
