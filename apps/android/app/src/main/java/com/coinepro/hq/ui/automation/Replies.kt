package com.coinepro.hq.ui.automation

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.DM_BUTTONS_MAX
import com.coinepro.hq.core.data.DM_BUTTON_TITLE_MAX
import com.coinepro.hq.core.data.DM_MAX
import com.coinepro.hq.core.data.POOL_MAX
import com.coinepro.hq.core.data.commentMatchFa
import com.coinepro.hq.core.data.dmButtonsFor
import com.coinepro.hq.core.data.dmTextFor
import com.coinepro.hq.core.data.dollarsOf
import com.coinepro.hq.core.data.faNum
import com.coinepro.hq.core.data.poolFilled
import com.coinepro.hq.core.data.repeatFa
import com.coinepro.hq.core.data.replyProblemsFa
import com.coinepro.hq.core.data.repliesBody
import com.coinepro.hq.core.net.DmButton
import com.coinepro.hq.core.net.FlowAutomation
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.ReplyPolicy
import com.coinepro.hq.core.net.RepeatPolicy
import com.coinepro.hq.core.net.SiteSection
import com.coinepro.hq.core.net.gated
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.DecisionBar
import com.coinepro.hq.designsystem.DecisionPage
import com.coinepro.hq.designsystem.DecisionPlace
import com.coinepro.hq.designsystem.DecisionState
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.Expand
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.HqSwitch
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.IconBtn
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.ScrollRow
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.Text
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v29.plain

// Contract §59.6 ⟨1.37⟩: how a flow answers on Instagram. The comment under the reel is «هر کامنتی» or the word said in the video (each
// video choosing by default); a story reply and a DM answer only that word. Ten or more warm public replies that go out IN TURN (IG-Hub
// 1806b86, `rules.public_turn`: ten people who comment one after another get ten different ones, then the first again), so the list is
// shown numbered in that order and his own lines can be moved; the DM of each video (today a replay, tomorrow a tool), previewed as Instagram shows it (at most 640 letters and three buttons
// under it); and how often one person is answered (once a year by default, or again after N days). One editor for the use form and for
// each flow's own page («جواب‌ها»).

/**
 * The policy's editor. [sections] are the company's links (§59.5) a button may open; [problems] what the hub would refuse, shown under
 * the part it is about.
 */
@Composable
internal fun ReplyEditor(p: ReplyPolicy, onChange: (ReplyPolicy) -> Unit, sections: List<SiteSection>, topicFa: String? = null) {
    val c = Divan.colors
    Column(Modifier.testTag("reply-editor"), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        HqCard(Modifier.fillMaxWidth()) {
            SectionTitle("کامنت زیر ریلز")
            ScrollRow(Modifier.padding(top = 8.dp)) {
                for (m in listOf("per_video", "any", "word")) FilterChip(commentMatchFa(m), p.comment.match == m, { onChange(p.copy(comment = p.comment.copy(match = m))) })
            }
            Text(
                when (p.comment.match) {
                    "any" -> "به هر کامنتی دایرکت میرود، هر چه نوشته باشد."
                    "word" -> "فقط کامنتی که کلمه‌ی گفته‌شده در ویدیو را دارد."
                    else -> "هر ویدیو در بسته‌اش میگوید «هر کامنتی» یا فقط کلمه."
                },
                style = Divan.type.micro, color = c.textMuted, modifier = Modifier.padding(top = 6.dp),
            )
            HorizontalDivider(Modifier.padding(vertical = 10.dp), color = c.lineDivider)
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("جواب استوری", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                    Text("کسی که به استوری همان روز کلمه را بگوید", style = Divan.type.micro, color = c.textMuted)
                }
                HqSwitch(p.story, { onChange(p.copy(story = it)) }, "جواب استوری")
            }
            Row(Modifier.padding(top = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("جواب دایرکت", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                    Text("کسی که کلمه را در دایرکت بفرستد", style = Divan.type.micro, color = c.textMuted)
                }
                HqSwitch(p.dm, { onChange(p.copy(dm = it)) }, "جواب دایرکت")
            }
        }
        DmCard(p, onChange, sections, topicFa)
        PoolCard(p, onChange)
        HqCard(Modifier.fillMaxWidth()) {
            SectionTitle("تکرار برای هر نفر")
            ScrollRow(Modifier.padding(top = 8.dp)) {
                FilterChip("سالی یک بار", p.repeat.mode != "after_days", { onChange(p.copy(repeat = RepeatPolicy("once_a_year"))) })
                FilterChip("دوباره بعد از چند روز", p.repeat.mode == "after_days", { onChange(p.copy(repeat = RepeatPolicy("after_days", p.repeat.days ?: 30))) })
            }
            Expand(p.repeat.mode == "after_days") {
                HqTextField(
                    p.repeat.days?.let { faNum(it) }.orEmpty(), { t -> onChange(p.copy(repeat = p.repeat.copy(days = dollarsOf(t)?.toInt()))) },
                    "چند روز؟ مثل ۳۰", Modifier.fillMaxWidth().padding(top = 8.dp), maxLength = 3, figure = true,
                )
            }
            Text("${repeatFa(p)}؛ منطق متا و قانون اسپم همین را میخواهد. بعضی کمپین‌ها چند بار به کار میروند.", style = Divan.type.micro, color = c.textMuted, modifier = Modifier.padding(top = 6.dp))
        }
        val problems = remember(p, sections) { replyProblemsFa(p, sections.map { it.key }.toSet()) }
        if (problems.isNotEmpty()) Column(Modifier.testTag("reply-problems"), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            for (x in problems) Text(plain(x), style = Divan.type.caption, color = c.negative)
        }
    }
}

/** The DM: its text with a counter, its buttons (each with the link it opens), whether each video writes its own, and the preview. */
@Composable
private fun DmCard(p: ReplyPolicy, onChange: (ReplyPolicy) -> Unit, sections: List<SiteSection>, topicFa: String?) {
    val c = Divan.colors
    val t = p.dmTemplate
    HqCard(Modifier.fillMaxWidth().testTag("reply-dm")) {
        SectionTitle("متن دایرکت", note = "${faNum(t.textFa.length)} از ${faNum(DM_MAX)} حرف")
        HqTextField(
            t.textFa, { onChange(p.copy(dmTemplate = t.copy(textFa = it))) }, "مثلاً: این هم {topic}؛ از دکمه‌ی زیر ببین 👇",
            Modifier.fillMaxWidth().padding(top = 8.dp), singleLine = false, minLines = 3, maxLength = DM_MAX + 200,
        )
        Text("«{topic}» موضوع همان روز میشود.", style = Divan.type.micro, color = c.textMuted, modifier = Modifier.padding(top = 4.dp))
        Row(Modifier.padding(top = 10.dp), verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text("متن هر ویدیو جدا", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                Text("امروز بازپخش، فردا ابزار، پس‌فردا اندیکاتور؛ بسته‌ی هر روز متن خودش را دارد و این متن پیش‌فرض است.", style = Divan.type.micro, color = c.textMuted)
            }
            HqSwitch(p.perVideoDm, { onChange(p.copy(perVideoDm = it)) }, "متن هر ویدیو جدا")
        }
        HorizontalDivider(Modifier.padding(vertical = 10.dp), color = c.lineDivider)
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text("دکمه‌های زیر پیام", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, modifier = Modifier.weight(1f))
            if (t.buttons.size < DM_BUTTONS_MAX) HqButton("دکمه", { onChange(p.copy(dmTemplate = t.copy(buttons = t.buttons + DmButton("", null)))) }, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.ADD)
        }
        t.buttons.forEachIndexed { i, b ->
            Column(Modifier.padding(top = 8.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    HqTextField(
                        b.titleFa, { v -> onChange(p.copy(dmTemplate = t.copy(buttons = t.buttons.mapIndexed { j, x -> if (j == i) x.copy(titleFa = v) else x }))) },
                        "نام دکمه (تا ${faNum(DM_BUTTON_TITLE_MAX)} حرف)", Modifier.weight(1f), maxLength = DM_BUTTON_TITLE_MAX + 10,
                    )
                    IconBtn(DivanIcon.CLOSE, "این دکمه را بردار", { onChange(p.copy(dmTemplate = t.copy(buttons = t.buttons.filterIndexed { j, _ -> j != i }))) }, tint = c.textMuted)
                }
                ScrollRow {
                    FilterChip("سایت", b.section == null, { onChange(p.copy(dmTemplate = t.copy(buttons = t.buttons.mapIndexed { j, x -> if (j == i) x.copy(section = null) else x }))) })
                    for (s in sections) FilterChip(s.titleFa.ifBlank { s.key }, b.section == s.key, {
                        onChange(p.copy(dmTemplate = t.copy(buttons = t.buttons.mapIndexed { j, x -> if (j == i) x.copy(section = s.key) else x })))
                    })
                }
            }
        }
        if (t.buttons.isEmpty()) Text("بی دکمه، لینک سایت زیر پیام میرود.", style = Divan.type.micro, color = c.textMuted, modifier = Modifier.padding(top = 4.dp))
        HorizontalDivider(Modifier.padding(vertical = 10.dp), color = c.lineDivider)
        Text("آنچه مخاطب میبیند", style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = c.textMuted)
        IgDmPreview(dmTextFor(t.textFa.ifBlank { "این هم لینکی که خواستی 👇" }, topicFa), dmButtonsFor(t.buttons).ifEmpty { listOf("ورود به سایت") }, Modifier.padding(top = 8.dp))
    }
}

/**
 * The public replies, in the order they go out (in turn: the first commenter gets ۱, the next ۲, … and after the last the first again):
 * his own lines first, each to change, move up or down, or take out; then the ones the hub's pool adds up to ten, numbered after them.
 */
@Composable
private fun PoolCard(p: ReplyPolicy, onChange: (ReplyPolicy) -> Unit) {
    val c = Divan.colors
    var adding by remember { mutableStateOf("") }
    val filled = remember(p.publicPool) { poolFilled(p.publicPool) }
    fun move(i: Int, by: Int) {
        val j = i + by
        if (j !in p.publicPool.indices) return
        onChange(p.copy(publicPool = p.publicPool.toMutableList().also { val x = it[i]; it[i] = it[j]; it[j] = x }))
    }
    HqCard(Modifier.fillMaxWidth().testTag("reply-pool")) {
        SectionTitle("جواب‌های عمومی زیر کامنت", note = "به نوبت · ${faNum(filled.size)} جواب")
        Text(
            "ده نفری که پشت سر هم کامنت میگذارند، ده جواب متفاوت میگیرند و بعد دوباره از اول؛ به همین ترتیب.",
            style = Divan.type.micro, color = c.textMuted, modifier = Modifier.padding(top = 4.dp),
        )
        Column(Modifier.padding(top = 8.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            p.publicPool.forEachIndexed { i, line ->
                Row(Modifier.testTag("pool-line"), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    TurnNumber(i + 1)
                    HqTextField(line, { v -> onChange(p.copy(publicPool = p.publicPool.mapIndexed { j, x -> if (j == i) v else x })) }, "جواب", Modifier.weight(1f), maxLength = 300)
                    if (p.publicPool.size > 1) Column {
                        if (i > 0) IconBtn(DivanIcon.CHEVRON, "یکی بالاتر", { move(i, -1) }, Modifier.rotate(180f), tint = c.textMuted)
                        if (i < p.publicPool.lastIndex) IconBtn(DivanIcon.CHEVRON, "یکی پایین‌تر", { move(i, 1) }, tint = c.textMuted)
                    }
                    IconBtn(DivanIcon.CLOSE, "این جواب را بردار", { onChange(p.copy(publicPool = p.publicPool.filterIndexed { j, _ -> j != i })) }, tint = c.textMuted)
                }
            }
            if (p.publicPool.size < POOL_MAX) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                HqTextField(adding, { adding = it }, "جواب تازه، گرم و با ایموجی", Modifier.weight(1f), maxLength = 300)
                IconBtn(DivanIcon.ADD, "اضافه کن", { if (adding.isNotBlank()) { onChange(p.copy(publicPool = p.publicPool + adding.trim())); adding = "" } })
            }
            val more = filled.drop(p.publicPool.size)
            if (more.isNotEmpty()) {
                Text("بعد از جواب‌های تو، از مجموعه‌ی آماده‌ی هاب تا ده تا پر شود:", style = Divan.type.micro, color = c.textMuted, modifier = Modifier.padding(top = 4.dp))
                more.forEachIndexed { k, x ->
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        TurnNumber(p.publicPool.size + k + 1, faint = true)
                        Text(plain(x), style = Divan.type.caption, color = c.textMuted, modifier = Modifier.weight(1f))
                    }
                }
            }
        }
    }
}

/** The reply's turn: «۱» for the first commenter, «۲» for the next, … */
@Composable
internal fun TurnNumber(n: Int, faint: Boolean = false) {
    val c = Divan.colors
    Box(Modifier.size(22.dp).clip(CircleShape).background(c.tile), contentAlignment = Alignment.Center) {
        Text(faNum(n), style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = if (faint) c.textMuted else c.silverInk)
    }
}

/**
 * A DM as Instagram draws it: the bubble with the text (cut where Instagram cuts it, 640 letters) and the buttons under it, each a row of
 * its own. Never the brand's gold: this is someone else's screen.
 */
@Composable
internal fun IgDmPreview(text: String, buttons: List<String>, modifier: Modifier = Modifier) {
    val c = Divan.colors
    val shape = RoundedCornerShape(18.dp)
    Row(modifier.fillMaxWidth().testTag("ig-preview"), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.Bottom) {
        Box(Modifier.size(26.dp).clip(CircleShape).background(c.tile), contentAlignment = Alignment.Center) { DIcon(DivanIcon.COMPANIES, size = 14.dp, tint = c.silverInk) }
        Column(Modifier.widthIn(max = 280.dp).clip(shape).border(1.dp, c.lineDivider, shape).background(c.raised)) {
            Text(plain(text.take(DM_MAX)), style = Divan.type.small, color = c.textPrimary, modifier = Modifier.padding(horizontal = 14.dp, vertical = 10.dp))
            for (b in buttons.take(DM_BUTTONS_MAX)) {
                HorizontalDivider(color = c.lineDivider)
                Text(plain(b), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.lapis, modifier = Modifier.fillMaxWidth().padding(vertical = 10.dp, horizontal = 14.dp))
            }
        }
    }
}

// --------------------------------------------------------------- the page --
/** «جواب‌ها» of one flow: its policy edited and saved with one tap, and the hub's own preview of what a person sees. */
@Composable
fun RepliesScreen(ref: String) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val q = rememberFlow(ref)
    val links = rememberSiteLinks(q.data?.company)
    val f: FlowAutomation? = q.data
    var edit by remember(f?.ref) { mutableStateOf(f?.replies) }
    LaunchedEffect(f?.replies) { if (edit == null) edit = f?.replies }
    val save = rememberAction()
    val sections = links.data?.sections.orEmpty()
    val p = edit
    val dirty = p != null && p != f?.replies
    val problems = if (p == null) emptyList() else replyProblemsFa(p, sections.map { it.key }.toSet())
    val preview = rememberQuery("replies-preview:$ref:${f?.replies.hashCode()}", "automations", maxAgeMs = 60_000) { gated(HubFeature.AUTOMATIONS) { repliesPreview(ref) } }
    DecisionPage(bar = if (p != null) ({
        DecisionBar(
            "ذخیره", {
                save.run {
                    val out = env.api.putReplies(ref, repliesBody(p))
                    env.cache.invalidate("automations")
                    q.set(out)
                    toasts.ok("از ویدیوی بعد همین جواب‌ها میرود.")
                }
            },
            context = if (dirty) "از انتشار بعد" else "تغییری نداده‌ای", enabled = dirty && problems.isEmpty(),
            state = if (save.busy) DecisionState.WORKING else DecisionState.IDLE, icon = DivanIcon.SEAL, place = DecisionPlace.PAGE,
        )
    }) else null) {
        Page(onRefresh = { q.refresh() }, refreshing = q.state.refreshing) {
            item(key = "head") { PageHeader("جواب‌ها", eyebrow = f?.titleFa?.ifBlank { null } ?: "کامنت، استوری و دایرکت") }
            when {
                f == null && q.error != null -> item(key = "err") { ErrorBlock(q.error, { q.refresh() }) }
                f == null -> item(key = "sk") { Skeleton(Modifier.fillMaxWidth().height(320.dp), radius = 16.dp) }
                p == null -> item(key = "none") { Empty("سیاست جوابی نیست", icon = DivanIcon.MESSAGES) }
                else -> {
                    preview.data?.let { pv ->
                        item(key = "hub-preview") {
                            HqCard(Modifier.fillMaxWidth()) {
                                SectionTitle("پیش‌نمایش هاب", note = "با جواب‌های ذخیره‌شده")
                                if (pv.commentFa.isNotBlank()) Text(plain("کامنت: ${pv.commentFa}"), style = Divan.type.caption, color = c.textSecondary, modifier = Modifier.padding(top = 6.dp))
                                if (pv.storyFa.isNotBlank()) Text(plain("استوری: ${pv.storyFa}"), style = Divan.type.caption, color = c.textSecondary)
                                if (pv.dmFa.isNotBlank()) Text(plain("دایرکت: ${pv.dmFa}"), style = Divan.type.caption, color = c.textSecondary)
                                IgDmPreview(pv.dm.text, pv.dm.buttons.map { it.title }, Modifier.padding(top = 10.dp))
                                // the public replies in the order they go out: the first commenter gets ۱, the next ۲, … then ۱ again
                                if (pv.public.isNotEmpty()) Column(Modifier.padding(top = 10.dp).testTag("preview-pool"), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                                    Text("جواب زیر کامنت، به نوبت", style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = c.textMuted)
                                    pv.public.forEachIndexed { i, x ->
                                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                            TurnNumber(i + 1)
                                            Text(plain(x), style = Divan.type.caption, color = c.textSecondary, modifier = Modifier.weight(1f))
                                        }
                                    }
                                }
                            }
                        }
                    }
                    item(key = "editor") { ReplyEditor(p, { edit = it }, sections, f.next?.topicFa) }
                }
            }
        }
    }
}
