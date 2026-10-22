package com.coinepro.hq.ui.support

import android.net.Uri
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
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.format.hoursUntil
import com.coinepro.hq.core.format.jDate
import com.coinepro.hq.core.format.jDateTime
import com.coinepro.hq.core.format.until
import com.coinepro.hq.core.media.describe
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.GUARD_FA
import com.coinepro.hq.core.net.KbArticle
import com.coinepro.hq.core.net.KbArticleIn
import com.coinepro.hq.core.net.KbCode
import com.coinepro.hq.core.net.KbLink
import com.coinepro.hq.core.net.QueueItem
import com.coinepro.hq.core.net.ShadowReport
import com.coinepro.hq.core.net.SupportChannel
import com.coinepro.hq.core.net.widens
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
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.Md
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.Seg
import com.coinepro.hq.designsystem.SegOption
import com.coinepro.hq.designsystem.Segmented
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.StackedBar
import com.coinepro.hq.designsystem.StatTile
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.QueryHandle
import com.coinepro.hq.ui.activity
import com.coinepro.hq.ui.companyOf
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v14.HqSheet
import com.coinepro.hq.ui.v14.Label
import com.coinepro.hq.ui.v14.LabelPill
import com.coinepro.hq.ui.v14.Tag
import com.coinepro.hq.ui.v16.AUTO_SEND
import com.coinepro.hq.ui.v16.CHANNEL_FA
import com.coinepro.hq.ui.v16.CHANNEL_STATE
import com.coinepro.hq.ui.v16.CONV_STATE
import com.coinepro.hq.ui.v16.ChipRow
import com.coinepro.hq.ui.v16.CompanyChips
import com.coinepro.hq.ui.v16.Fact
import com.coinepro.hq.ui.v16.FactRows
import com.coinepro.hq.ui.v16.HANDOFF_FA
import com.coinepro.hq.ui.v16.KB_KIND
import com.coinepro.hq.ui.v16.KB_SOURCE
import com.coinepro.hq.ui.v16.KB_STATUS
import com.coinepro.hq.ui.v16.Labelled
import com.coinepro.hq.ui.v16.Masked
import com.coinepro.hq.ui.v16.ProseTag
import com.coinepro.hq.ui.v16.QUEUE_KIND
import com.coinepro.hq.ui.v16.TerminalCommand
import com.coinepro.hq.ui.v16.go
import com.coinepro.hq.ui.v16.prose
import com.coinepro.hq.ui.v16.rate
import java.io.IOException
import java.util.Locale
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext

private val TABS = listOf(SegOption("queue", "صف آموزش"), SegOption("conversations", "گفت‌وگو"), SegOption("channels", "کانال‌ها"), SegOption("kb", "دانش"), SegOption("shadow", "آزمون سایه"))

/** پشتیبانی (contract §19.3–§19.6): a desk the owner teaches. Rules answer first, verbatim from approved knowledge; a model drafts
 *  only from approved articles; the outbound guard checks every word; what is left waits in the teaching queue. */
@Composable
fun SupportScreen(tab0: String = "queue") {
    val c = Divan.colors
    var tab by rememberSaveable { mutableStateOf(tab0) }
    val queue = rememberQuery("support:queue", "support", maxAgeMs = 30_000) { supportQueue() }
    val channels = rememberQuery("support:channels:", "support") { supportChannels() }
    val proposed = rememberQuery("support:kb:::proposed:", "support") { kb(status = "proposed") }
    val shadow = rememberQuery("support:shadow", "support") { shadowReports() }
    val r = refresher(queue, channels, proposed, shadow)
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item { PageHeader("پشتیبانی", eyebrow = "میزی که تو آموزشش میدهی؛ هیچ کلمه‌ای بی‌نگهبان به مشتری نمیرسد") }
        item {
            Text(
                "اول قاعده: پرسشی که عین یک مقاله‌ی تأییدشده است بی‌مدل جواب میگیرد. بعد ایجنت فقط از مقاله‌های تأییدشده پیش‌نویس میدهد و کد هر لینک، کد و عدد را میسنجد. پشتیبانی هرگز رمز، کلید، کد تأیید یا عبارت بازیابی نمیخواهد و هرگز وعده‌ی سود نمیدهد.",
                style = Divan.type.small, color = c.textSecondary,
            )
        }
        item {
            val qd = queue.data; val ch = channels.data; val pd = proposed.data; val sd = shadow.data
            if (qd == null || ch == null || pd == null || sd == null) Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                repeat(2) { Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) { repeat(2) { Skeleton(Modifier.weight(1f).height(104.dp), radius = 14.dp) } } }
            } else Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                val real = ch.filter { it.kind != "mystery" }
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    StatTile("منتظر تو", qd.size.toString(), Modifier.weight(1f), sub = "صف آموزش", tone = if (qd.isNotEmpty()) Tone.WARN else null, figure = false)
                    StatTile("کانال روشن", real.count { it.state == "live" }.toString(), Modifier.weight(1f), sub = "از ${real.size} کانال", figure = false)
                }
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    StatTile("مقاله‌ی منتظر تأیید", pd.size.toString(), Modifier.weight(1f), sub = "تأیید با passkey", figure = false)
                    StatTile("آزمون سایه‌ی قبول", sd.count { it.pass }.toString(), Modifier.weight(1f), sub = "از ${sd.size} شرکت آزموده", figure = false)
                }
            }
        }
        item { Segmented(TABS, tab, { tab = it }, Modifier.fillMaxWidth()) }
        item {
            when (tab) {
                "conversations" -> ConversationsTab()
                "channels" -> ChannelsTab(channels, shadow)
                "kb" -> KbTab()
                "shadow" -> ShadowTab(shadow)
                else -> QueueTab(queue)
            }
        }
    }
}

// ------------------------------------------------------------- the queue --
/** حالت آموزش (§19.3–§19.4): what waits for the owner, oldest first. */
@Composable
private fun QueueTab(q: QueryHandle<List<QueueItem>>) {
    val nav = LocalNav.current
    val c = Divan.colors
    HqCard(Modifier.fillMaxWidth(), padding = PaddingValues(14.dp)) {
        SectionTitleSmall("صف آموزش", "قدیمی‌ترین بالا؛ هر جواب یا اصلاح تو یک مقاله‌ی پیشنهادی میشود تا مشتری بعدی بی‌تو جواب بگیرد")
        val items = q.data?.sortedBy { it.since }
        when {
            items == null && q.error != null -> ErrorBlock(q.error, { q.refresh() })
            items == null -> Skeleton(Modifier.fillMaxWidth().padding(top = 12.dp).height(160.dp))
            items.isEmpty() -> Empty("صف خالی است", icon = DivanIcon.MESSAGES, body = "پشتیبانی چیزی منتظر تو ندارد.")
            else -> Column(Modifier.padding(top = 6.dp)) {
                items.forEachIndexed { i, x ->
                    if (i > 0) HorizontalDivider(color = c.lineDivider)
                    Row(
                        Modifier.fillMaxWidth().clip(RoundedCornerShape(8.dp)).clickable(role = Role.Button) { nav.go("support/${x.conversation}") }.padding(vertical = 12.dp, horizontal = 2.dp),
                        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp),
                    ) {
                        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                LabelPill(QUEUE_KIND[x.kind], x.kind)
                                CompanyMark(x.company, height = 12.dp, mono = true, ink = c.textMuted)
                                Fig(x.conversation, style = Divan.type.figureSmall, color = c.textMuted)
                                Text(ago(x.since), style = Divan.type.micro, color = c.textMuted, maxLines = 1)
                            }
                            val d = x.draft
                            if (d != null) {
                                Masked(d.body, style = Divan.type.small, maxLines = 2)
                                when {
                                    d.blockedReasons.isNotEmpty() -> Text("رد نگهبان: " + d.blockedReasons.joinToString("، ") { GUARD_FA[it] ?: it }, style = Divan.type.caption, color = c.negative)
                                    d.confidence != null -> Text(buildAnnotatedString { append("پیش‌نویس با اطمینان "); fig(String.format(Locale.US, "%.2f", d.confidence)) }, style = Divan.type.caption, color = c.textSecondary)
                                }
                            } else Text("پیش‌نویسی نیست؛ جواب تو لازم است.", style = Divan.type.small, color = c.textSecondary)
                        }
                        DIcon(DivanIcon.NEXT, size = 16.dp, tint = c.textMuted)
                    }
                }
            }
        }
    }
}

@Composable
private fun SectionTitleSmall(title: String, note: String? = null) {
    com.coinepro.hq.designsystem.SectionTitle(title, note = note, modifier = Modifier.padding(bottom = 4.dp))
}

// ------------------------------------------------------- conversations --
private val CONV_STATES = listOf("waiting_owner", "open", "answered", "closed")
private val CHANNELS = listOf("telegram_bot", "telegram_business", "chatwoot", "product_bot", "mystery")

@Composable
private fun ConversationsTab() {
    val env = LocalEnv.current
    val nav = LocalNav.current
    val c = Divan.colors
    var company by rememberSaveable { mutableStateOf<String?>(null) }
    var state by rememberSaveable { mutableStateOf<String?>(null) }
    var channel by rememberSaveable { mutableStateOf<String?>(null) }
    var text by rememberSaveable { mutableStateOf("") }
    var query by rememberSaveable { mutableStateOf("") }
    LaunchedEffect(text) { delay(300); query = text.trim() }
    val q = rememberQuery("support:conversations:${company.orEmpty()}:${state.orEmpty()}:${channel.orEmpty()}:$query", "support", maxAgeMs = 30_000) {
        conversations(company, state, channel, query)
    }
    var more by remember(q.data) { mutableStateOf(emptyList<com.coinepro.hq.core.net.Conversation>()) }
    var cursor by remember(q.data) { mutableStateOf(q.data?.nextCursor) }
    val loadMore = rememberAction()
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        HqCard(Modifier.fillMaxWidth(), padding = PaddingValues(14.dp)) {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                CompanyChips(company, { company = it })
                ChipRow {
                    FilterChip("همه", state == null, { state = null })
                    for (s in CONV_STATES) FilterChip(CONV_STATE[s]!!.fa, state == s, { state = s })
                }
                ChipRow {
                    FilterChip("همه‌ی کانال‌ها", channel == null, { channel = null })
                    for (k in CHANNELS) FilterChip(CHANNEL_FA.getValue(k), channel == k, { channel = k })
                }
                HqTextField(text, { text = it }, "جستجو در گفت‌وگوها", Modifier.fillMaxWidth(), maxLength = 120)
            }
        }
        val list = q.data?.items?.let { it + more }
        when {
            list == null && q.error != null -> ErrorBlock(q.error, { q.refresh() })
            list == null -> Skeleton(Modifier.fillMaxWidth().height(200.dp), radius = 14.dp)
            list.isEmpty() -> Empty("گفت‌وگویی نیست", icon = DivanIcon.MESSAGES)
            else -> HqCard(Modifier.fillMaxWidth(), padding = PaddingValues(horizontal = 12.dp, vertical = 4.dp)) {
                list.forEachIndexed { i, x ->
                    if (i > 0) HorizontalDivider(color = c.lineDivider)
                    Row(
                        Modifier.fillMaxWidth().clip(RoundedCornerShape(8.dp)).clickable(role = Role.Button) { nav.go("support/${x.ref}") }.padding(vertical = 12.dp, horizontal = 2.dp),
                        horizontalArrangement = Arrangement.spacedBy(10.dp),
                    ) {
                        CompanyMark(x.company, height = 14.dp, mono = true, ink = c.textSecondary, modifier = Modifier.padding(top = 4.dp))
                        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                if (x.customer.displayName != null) Text(x.customer.displayName, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), maxLines = 1)
                                else Fig(x.customer.handleMasked, style = Divan.type.figure.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                                if (x.mystery) Pill("ناشناس ناظر", Tone.LEARN)
                            }
                            FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(4.dp), itemVerticalAlignment = Alignment.CenterVertically) {
                                Fig(x.ref, style = Divan.type.figureSmall, color = c.textMuted)
                                Text(CHANNEL_FA[x.channel] ?: x.channel, style = Divan.type.micro, color = c.textMuted)
                                if (x.customer.displayName != null) Fig(x.customer.handleMasked, style = Divan.type.figureSmall, color = c.textMuted)
                                for (t in x.tags) ProseTag(t)
                                x.csat?.let { Text(buildAnnotatedString { append("رضایت "); fig("$it/5") }, style = Divan.type.micro, color = c.textMuted) }
                            }
                        }
                        Column(horizontalAlignment = Alignment.End, verticalArrangement = Arrangement.spacedBy(4.dp)) {
                            LabelPill(CONV_STATE[x.state], x.state)
                            if (x.handoff != null && x.state == "waiting_owner") HANDOFF_FA[x.handoff.reason]?.let { Pill(it.fa, it.tone) }
                            Text(ago(x.lastMessageAt), style = Divan.type.micro, color = c.textMuted)
                        }
                    }
                }
            }
        }
        cursor?.let { at ->
            HqButton("بیشتر", {
                loadMore.run {
                    val pg = env.api.conversations(company, state, channel, query, cursor = at)
                    more = more + pg.items
                    cursor = pg.nextCursor
                }
            }, variant = BtnVariant.SECONDARY, size = BtnSize.SM, loading = loadMore.busy)
        }
    }
}

// ------------------------------------------------------------ channels --
@Composable
private fun ChannelsTab(q: QueryHandle<List<SupportChannel>>, shadow: QueryHandle<List<ShadowReport>>) {
    val c = Divan.colors
    val companies = rememberCompanies()
    val cards = rememberQuery("decisions:pending", "decisions") { decisions("pending", limit = 100) }
    fun cardFor(ch: SupportChannel): String? = cards.data?.items?.firstOrNull { d ->
        d.kind == "support_go_live" && (d.payload["company"] as? kotlinx.serialization.json.JsonPrimitive)?.content == ch.company &&
            (d.payload["channel"] as? kotlinx.serialization.json.JsonPrimitive)?.content == ch.kind
    }?.ref
    val list = q.data
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("توقف همیشه امن است و passkey نمیخواهد. روشن شدن بار اول فقط با کارت شروع (go-live) بعد از قبولی آزمون سایه است؛ کانالی که قبلاً روشن بوده با passkey دوباره روشن میشود.", style = Divan.type.small, color = c.textSecondary)
        when {
            list == null && q.error != null -> ErrorBlock(q.error, { q.refresh() })
            list == null -> Skeleton(Modifier.fillMaxWidth().height(240.dp), radius = 14.dp)
            else -> for (co in list.map { it.company }.distinct()) {
                HqCard(Modifier.fillMaxWidth(), padding = PaddingValues(14.dp)) {
                    Row(Modifier.padding(bottom = 10.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        CompanyMark(co, height = 16.dp, mono = true, ink = c.textPrimary)
                        Text(companyOf(companies, co).nameFa, style = Divan.type.h3)
                    }
                    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        for (ch in list.filter { it.company == co }) ChannelCard(ch, shadow.data?.firstOrNull { it.company == co }, cardFor(ch))
                    }
                }
            }
        }
    }
}

private val SETUP = mapOf(
    "telegram_business" to "بعد از قبولی آزمون سایه: Premium تلگرام و اتصال Business\u00A0←\u00A0Chatbots به ربات هلدینگ.",
    "chatwoot" to "چت سایت تصمیم هزینه‌ی توست (سرور کوچک جدا، یا فعلاً بدون چت سایت)؛ تا آن موقع خاموش میماند.",
    "product_bot" to "از راه CR-011 (ربات خود محصول)، فقط بعد از go-live همین کانال.",
)

@Composable
private fun ChannelCard(ch: SupportChannel, report: ShadowReport?, card: String?) {
    val env = LocalEnv.current
    val nav = LocalNav.current
    val toasts = LocalToasts.current
    val act = activity()
    val c = Divan.colors
    val action = rememberAction()
    val mystery = ch.kind == "mystery"
    fun patch(autoSend: String? = null, live: Boolean = false) = action.go(toasts) {
        env.api.patchChannel(ch, autoSend, live) { a, t -> env.auth.stepUp(act, a, t) }
        env.cache.invalidate("support")
        toasts.ok(if (live) "کانال دوباره روشن شد." else "ارسال بی‌تو: ${AUTO_SEND[autoSend]?.first ?: ""}")
    }
    Column(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(if (ch.state == "paused") c.softWarning else c.tile).padding(14.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            DIcon(if (mystery) DivanIcon.OVERSEER else DivanIcon.MESSAGES, size = 18.dp, tint = c.textSecondary)
            Text(CHANNEL_FA[ch.kind] ?: ch.kind, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), modifier = Modifier.weight(1f))
            LabelPill(CHANNEL_STATE[ch.state], ch.state)
        }
        if (ch.state == "live" && ch.liveSince != null) Text("روشن از ${jDate(ch.liveSince)}", style = Divan.type.caption, color = c.textMuted)
        if (ch.state == "paused") Text(prose(ch.pausedReason ?: "متوقف است."), style = Divan.type.small, color = c.textPrimary)
        if (ch.state != "not_configured") Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("چه چیزی بی‌تو میرود", style = Divan.type.caption, color = c.textSecondary)
            Segmented(
                listOf(SegOption("off", "هیچ"), SegOption("kb_verbatim", "عین دانشنامه"), SegOption("kb_grounded", "مستند هم", if (ch.autoSend == "kb_grounded") null else DivanIcon.LOCK)),
                ch.autoSend, { v -> if (v != ch.autoSend && !action.busy) patch(autoSend = v) }, Modifier.fillMaxWidth(),
            )
            Text(
                (AUTO_SEND[ch.autoSend]?.second ?: "") + if (widens(ch, "kb_grounded", false)) " گشادتر کردن با passkey است؛ تنگ‌تر کردن نه." else "",
                style = Divan.type.micro, color = c.textMuted,
            )
        }
        when {
            mystery -> Text("فقط ناظر کل؛ کل مسیر جواب را میرود ولی هرگز به تلگرام یا Chatwoot نمیرسد و در هیچ آماری شمرده نمیشود.", style = Divan.type.caption, color = c.textSecondary)
            ch.state == "shadow" -> Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.card).padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                if (report?.pass == true) Text(buildAnnotatedString {
                    withStyle(androidx.compose.ui.text.SpanStyle(color = c.positive, fontWeight = FontWeight.SemiBold)) { append("آزمون سایه قبول شد. ") }
                    append("شروع کانال یک کارت در کارتابل است که با مُهر تو روشن میشود.")
                }, style = Divan.type.caption, color = c.textSecondary)
                else Text(buildAnnotatedString { append("اول آزمون سایه: دست‌کم "); fig("90%"); append(" درست، صفر خطای ایمنی، صفر کد یا لینک اشتباه. با قبولی، کارت شروع در کارتابل میاید.") }, style = Divan.type.caption, color = c.textSecondary)
                if (ch.kind == "telegram_business") Text(prose("تلگرام بیزینس علاوه بر این اتصال Premium تو (Business\u00A0←\u00A0Chatbots) را لازم دارد."), style = Divan.type.caption, color = c.textSecondary)
                card?.let { ref ->
                    Row(
                        Modifier.clip(RoundedCornerShape(8.dp)).clickable(role = Role.Button) { nav.go("cartable/$ref") }.padding(vertical = 4.dp, horizontal = 2.dp),
                        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp),
                    ) {
                        DIcon(DivanIcon.SEAL, size = 14.dp, tint = c.goldInk)
                        Text(buildAnnotatedString { append("کارت "); fig(ref); append(" منتظر مُهر توست") }, style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.goldInk)
                    }
                }
            }
            ch.state == "not_configured" -> Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                if (ch.kind == "telegram_bot") {
                    Text(prose("ربات را در BotFather بساز و توکنش را در ترمینال خودت بگذار:"), style = Divan.type.caption, color = c.textSecondary)
                    TerminalCommand("make telegram-bot-token COMPANY=${ch.company} CHANNEL=telegram_bot")
                } else SETUP[ch.kind]?.let { Text(prose(it), style = Divan.type.caption, color = c.textSecondary) }
            }
        }
        if (ch.state == "live" || (ch.state == "paused" && ch.liveSince != null)) Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            if (ch.state == "live") HqButton("توقف", {
                action.go(toasts) {
                    env.api.pauseChannel(ch)
                    env.cache.invalidate("support")
                    toasts.info("متوقف شد؛ از این کانال دیگر چیزی به مشتری نمیرود.")
                }
            }, variant = BtnVariant.DANGER, size = BtnSize.SM, icon = DivanIcon.PAUSE, loading = action.busy)
            else HqButton("دوباره روشن کن", { patch(live = true) }, variant = BtnVariant.PRIMARY, size = BtnSize.SM, icon = DivanIcon.SEAL, loading = action.busy)
        }
    }
}

// ------------------------------------------------------------- knowledge --
@Composable
private fun KbTab() {
    val c = Divan.colors
    var company by rememberSaveable { mutableStateOf<String?>(null) }
    var kind by rememberSaveable { mutableStateOf<String?>(null) }
    var status by rememberSaveable { mutableStateOf<String?>(null) }
    var text by rememberSaveable { mutableStateOf("") }
    var query by rememberSaveable { mutableStateOf("") }
    LaunchedEffect(text) { delay(300); query = text.trim().takeIf { it.length >= 2 }.orEmpty() }
    val q = rememberQuery("support:kb:${company.orEmpty()}:${kind.orEmpty()}:${status.orEmpty()}:$query", "support") { kb(company, kind, status, query) }
    var open by remember { mutableStateOf<String?>(null) }
    var neu by remember { mutableStateOf(false) }
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        HqCard(Modifier.fillMaxWidth(), padding = PaddingValues(14.dp)) {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("دانشنامه", style = Divan.type.h3, modifier = Modifier.weight(1f))
                    HqButton("مقاله‌ی تازه", { neu = true }, variant = BtnVariant.PRIMARY, size = BtnSize.SM, icon = DivanIcon.ADD)
                }
                CompanyChips(company, { company = it })
                ChipRow {
                    FilterChip("همه‌ی نوع‌ها", kind == null, { kind = null })
                    for ((k, fa) in KB_KIND) FilterChip(fa, kind == k, { kind = k })
                }
                ChipRow {
                    FilterChip("همه", status == null, { status = null })
                    for ((k, l) in KB_STATUS) FilterChip(l.fa, status == k, { status = k })
                }
                HqTextField(text, { text = it }, "جستجو در دانشنامه", Modifier.fillMaxWidth(), maxLength = 120)
            }
        }
        val list = q.data
        when {
            list == null && q.error != null -> ErrorBlock(q.error, { q.refresh() })
            list == null -> Skeleton(Modifier.fillMaxWidth().height(200.dp), radius = 14.dp)
            list.isEmpty() -> Empty("مقاله‌ای نیست", icon = DivanIcon.KNOWLEDGE)
            else -> for (a in list) KbRow(a) { open = "${a.ref}@${a.version}" }
        }
    }
    q.data?.firstOrNull { "${it.ref}@${it.version}" == open }?.let { a -> KbSheet(a) { open = null } }
    if (neu) KbPropose(company) { neu = false }
}

@Composable
private fun KbRow(a: KbArticle, onClick: () -> Unit) {
    val c = Divan.colors
    val soon = a.status == "approved" && (hoursUntil(a.expiresAt) ?: 9e9) < 14 * 24
    Column(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(if (a.status == "proposed") c.softGold else c.card)
            .clickable(role = Role.Button, onClick = onClick).alpha(if (a.status == "retired" || a.status == "expired") 0.7f else 1f).padding(14.dp),
        verticalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            CompanyMark(a.company, height = 11.dp, mono = true, ink = c.textMuted)
            Text(KB_KIND[a.kind] ?: a.kind, style = Divan.type.micro, color = c.textMuted)
            Fig("${a.ref}@${a.version}", style = Divan.type.figureSmall, color = c.textMuted)
            a.key?.let { Fig(it, style = Divan.type.figureSmall, color = c.textSecondary) }
            Spacer(Modifier.weight(1f))
            LabelPill(KB_STATUS[a.status], a.status)
        }
        Text(prose(a.questionFa), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
        Text(prose(a.answerMd.replace(Regex("\\*\\*|__|`"), "")), style = Divan.type.caption, color = c.textSecondary, maxLines = 2, overflow = TextOverflow.Ellipsis)
        FlowRow(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(KB_SOURCE[a.source.kind] ?: a.source.kind, style = Divan.type.micro, color = c.textMuted)
            Text("${a.uses30d} بار در ۳۰ روز", style = Divan.type.micro, color = c.textMuted)
            Text("انقضا ${until(a.expiresAt)}", style = Divan.type.micro, color = if (soon) c.warning else c.textMuted)
        }
    }
}

@Composable
private fun KbSheet(a: KbArticle, onClose: () -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val act = activity()
    val c = Divan.colors
    val action = rememberAction()
    HqSheet(onClose, KB_KIND[a.kind] ?: a.kind, ref = "${a.ref}@${a.version}") {
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(6.dp), itemVerticalAlignment = Alignment.CenterVertically) {
            LabelPill(KB_STATUS[a.status], a.status)
            CompanyMark(a.company, height = 12.dp, mono = true, ink = c.textSecondary)
            Text(KB_SOURCE[a.source.kind] ?: a.source.kind, style = Divan.type.caption, color = c.textSecondary)
            a.source.ref?.let { Fig(it, style = Divan.type.figureSmall, color = c.textMuted) }
            a.key?.let { Tag(it, figure = true) }
        }
        Text(prose(a.questionFa), style = Divan.type.h3)
        if (a.variants.isNotEmpty()) FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) { for (v in a.variants) ProseTag(v) }
        Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(14.dp)) {
            Md(a.answerMd, style = Divan.type.body, color = c.textPrimary)
        }
        if (a.variables.isNotEmpty()) Text(buildAnnotatedString {
            append("متغیرها: ")
            a.variables.forEachIndexed { i, v -> if (i > 0) append("، "); fig("{{${v.name}}}"); append(if (v.source == "policy") " (سیاست)" else " (مشتری)") }
        }, style = Divan.type.caption, color = c.textSecondary)
        if (a.links.isNotEmpty()) Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text("لینک‌های تأییدشده", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
            for (l in a.links) Column {
                Fig(l.url, style = Divan.type.figureSmall, color = c.textPrimary, maxLines = 2)
                Text(l.labelFa, style = Divan.type.micro, color = c.textMuted)
            }
        }
        if (a.codes.isNotEmpty()) FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp)) { for (k in a.codes) Tag("${k.exchange}: ${k.code}", figure = true) }
        FactRows(listOf(
            { m -> Fact("استفاده در ۳۰ روز", a.uses30d.toString(), m, figure = true) },
            { m -> Fact("تأیید", a.approvedAt?.let { jDate(it) } ?: "—", m) },
            { m -> Fact("انقضا", until(a.expiresAt), m) },
        ), perRow = 3)
        Text(buildAnnotatedString {
            append("مقاله‌ی تأییدشده همان چیزی است که بی‌تو به مشتری میرود؛ پس تأییدش با passkey و روی همین نسخه است (")
            fig("sha256 ${a.sha256.take(12)}…"); append(").")
        }, style = Divan.type.micro, color = c.textMuted)
        if (a.status == "proposed") HqButton("تأیید با passkey", {
            action.go(toasts) {
                env.api.approveKb(a) { x, t -> env.auth.stepUp(act, x, t) }
                env.cache.invalidate("support")
                toasts.ok("تأیید شد؛ از همین حالا میتواند بی‌تو به مشتری برود.")
                onClose()
            }
        }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, size = BtnSize.LG, icon = DivanIcon.SEAL, loading = action.busy)
        else if (a.status != "retired") HqButton("بازنشسته کن", {
            action.go(toasts) {
                env.api.retireKb(a.ref)
                env.cache.invalidate("support")
                toasts.info("بازنشسته شد؛ دیگر در هیچ جوابی به کار نمیرود.")
                onClose()
            }
        }, Modifier.fillMaxWidth(), variant = BtnVariant.GHOST, loading = action.busy)
    }
}

@Composable
private fun KbPropose(company0: String?, onClose: () -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val action = rememberAction()
    var company by rememberSaveable { mutableStateOf(company0) }
    var kind by rememberSaveable { mutableStateOf("faq") }
    var key by rememberSaveable { mutableStateOf("") }
    var question by rememberSaveable { mutableStateOf("") }
    var variants by rememberSaveable { mutableStateOf("") }
    var answer by rememberSaveable { mutableStateOf("") }
    var links by rememberSaveable { mutableStateOf("") }
    var codes by rememberSaveable { mutableStateOf("") }
    val linky = kind == "referral" || kind == "official_link"
    fun lines(s: String) = s.split('\n').map { it.trim() }.filter { it.isNotEmpty() }
    val parsedLinks = if (linky) lines(links).map { l -> l.split(Regex("\\s+"), limit = 2).let { KbLink(it[0], it.getOrElse(1) { "" }) } } else emptyList()
    val parsedCodes = if (kind == "referral") lines(codes).map { l -> l.split(Regex("\\s+")).let { KbCode(it[0], it.getOrElse(1) { "" }) } } else emptyList()
    val body = company?.let { co ->
        KbArticleIn(co, kind, question.trim(), answer.trim(), lines(variants), key.trim().takeIf { kind == "policy" && it.isNotEmpty() }, links = parsedLinks, codes = parsedCodes)
    }
    val valid = body != null && body.questionFa.length >= 3 && body.answerMd.length >= 5 && (kind != "policy" || key.isNotBlank()) &&
        parsedLinks.all { Regex("^https://\\S+$").matches(it.url) } && parsedCodes.all { it.code.isNotBlank() }
    HqSheet(onClose, "مقاله‌ی تازه", sub = "پیشنهاد میشود؛ تا تأیید تو با passkey، به هیچ مشتری‌ای نمیرسد.") {
        Labelled("شرکت") { CompanyChips(company, { company = it }, all = false) }
        Labelled("نوع") { ChipRow { for ((k, fa) in KB_KIND) FilterChip(fa, kind == k, { kind = k }) } }
        if (kind == "policy") Labelled("کلید سیاست") { HqTextField(key, { key = it.trim() }, "vip.min_balance", Modifier.fillMaxWidth(), maxLength = 80, figure = true) }
        Labelled("پرسش") { HqTextField(question, { question = it }, "پرسش مشتری، همان‌طور که میپرسد", Modifier.fillMaxWidth(), maxLength = 300) }
        Labelled("شکل‌های دیگر پرسش (هر خط یکی)") { HqTextField(variants, { variants = it }, "", Modifier.fillMaxWidth(), singleLine = false, minLines = 2) }
        Labelled("جواب") { HqTextField(answer, { answer = it }, "متغیرها با {{name}}", Modifier.fillMaxWidth(), singleLine = false, minLines = 5, maxLength = 4000) }
        if (linky) Labelled("لینک‌ها (هر خط: نشانی، فاصله، عنوان)") { HqTextField(links, { links = it }, "https://… عنوان", Modifier.fillMaxWidth(), singleLine = false, minLines = 3, figure = true) }
        if (kind == "referral") Labelled("کدها (هر خط: صرافی، فاصله، کد)") { HqTextField(codes, { codes = it }, "lbank CODE", Modifier.fillMaxWidth(), singleLine = false, minLines = 2, figure = true) }
        if (linky) Text(
            "کد و لینک رفرال و لینک رسمی را فقط خودت مینویسی؛ ایجنت هرگز نمیسازد. نگهبان خروجی هر لینک یا کدی را که عیناً این‌جا تأیید نشده رد میکند.",
            style = Divan.type.caption, color = c.textSecondary, modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp),
        )
        HqButton("ثبت پیشنهاد", {
            val b = body ?: return@HqButton
            action.go(toasts) {
                val a = env.api.proposeKb(b)
                env.cache.invalidate("support")
                toasts.ok("پیشنهاد ${a.ref} ثبت شد؛ برای اثر، تأییدش کن.")
                onClose()
            }
        }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, size = BtnSize.LG, icon = DivanIcon.KNOWLEDGE, enabled = valid, loading = action.busy)
    }
}

// ----------------------------------------------------------- shadow test --
private val VERDICT_FA = mapOf("wrong" to Label("نادرست", Tone.NEG), "partial" to Label("ناقص", Tone.WARN), "safety" to Label("خطای ایمنی", Tone.NEG))

@Composable
private fun ShadowTab(q: QueryHandle<List<ShadowReport>>) {
    val c = Divan.colors
    val operating = rememberCompanies().filter { it.kind != "holding" }
    val list = q.data
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text(buildAnnotatedString {
            append("قبولی یعنی دست‌کم "); fig("90%"); append(" درست، ")
            withStyle(androidx.compose.ui.text.SpanStyle(fontWeight = FontWeight.Bold)) { append("و") }
            append(" صفر خطای ایمنی، ")
            withStyle(androidx.compose.ui.text.SpanStyle(fontWeight = FontWeight.Bold)) { append("و") }
            append(" صفر کد یا لینک اشتباه. فقط بعد از قبولی کارت شروع آن شرکت ساخته میشود؛ آزمون هرگز از شرکت بیرون نمیرود.")
        }, style = Divan.type.small, color = c.textSecondary)
        when {
            list == null && q.error != null -> ErrorBlock(q.error, { q.refresh() })
            list == null -> Skeleton(Modifier.fillMaxWidth().height(240.dp), radius = 14.dp)
            else -> for (co in operating) ShadowCard(co.code, co.nameFa ?: co.code, list.firstOrNull { it.company == co.code })
        }
    }
}

@Composable
private fun ShadowCard(company: String, name: String, r: ShadowReport?) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val ctx = LocalContext.current
    val c = Divan.colors
    val upload = rememberAction()
    val run = rememberAction()
    var sending by remember { mutableStateOf(false) }
    fun send(uri: Uri) {
        sending = true
        upload.go(toasts, onError = { sending = false; false }) {
            val f = withContext(Dispatchers.IO) { ctx.contentResolver.describe(uri) }
            val ref = try {
                withContext(Dispatchers.IO) { env.api.upload(f.name, f.mime, f.size, { ctx.contentResolver.openInputStream(uri) ?: throw IOException("unreadable") }) }
            } catch (e: IOException) {
                throw ApiException(0, "upload_failed", "فایل خوانده نشد.")
            }
            val out = env.api.supportHistory(company, ref.id)
            sending = false
            env.cache.invalidate("support")
            toasts.ok("مجموعه‌ی آزمون ${out.suite ?: ""} ساخته شد" + (out.cases?.let { "، $it سؤال ماسک‌شده" } ?: "") + ". حالا اجرا کن.")
        }
    }
    val pick = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri -> if (uri != null) send(uri) }
    val correct = r?.takeIf { it.total > 0 }?.let { it.correct.toDouble() / it.total }
    HqCard(Modifier.fillMaxWidth(), padding = PaddingValues(14.dp)) {
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                CompanyMark(company, height = 16.dp, mono = true, ink = c.textPrimary)
                Text(name, style = Divan.type.h3, modifier = Modifier.weight(1f))
                when {
                    r == null -> Pill("هنوز آزمونی نیست", Tone.NEUTRAL)
                    r.pass -> Pill("قبول", Tone.POS, dot = true)
                    else -> Pill("قبول نشد", Tone.NEG, dot = true)
                }
            }
            if (r != null) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    Fig(rate(correct), style = Divan.type.figureL.copy(fontSize = 28.sp), color = if (correct != null && correct < r.threshold) c.warning else c.textPrimary)
                    Text(buildAnnotatedString { append("درست، از "); fig(r.total.toString()); append(" سؤال؛ مرز قبولی "); fig(rate(r.threshold)); append(" (خط عمودی)") }, style = Divan.type.caption, color = c.textSecondary, modifier = Modifier.weight(1f))
                }
                // The pass line sits on the bar: the correct share starts at the reading start, so it passes when it reaches the line.
                Box {
                    StackedBar(listOf(
                        Seg("c", "درست", r.correct.toDouble(), c.positive, r.correct.toString()),
                        Seg("p", "ناقص", r.partial.toDouble(), c.warning, r.partial.toString()),
                        Seg("w", "نادرست", r.wrong.toDouble(), c.negative, r.wrong.toString()),
                    ), label = "درست، ناقص و نادرست", height = 10.dp)
                    Box(Modifier.fillMaxWidth(r.threshold.toFloat().coerceIn(0f, 1f)).height(16.dp).offset(y = (-3).dp)) {
                        Box(Modifier.align(Alignment.CenterEnd).width(2.dp).fillMaxHeight().clip(RoundedCornerShape(1.dp)).background(c.textPrimary))
                    }
                }
                FactRows(listOf(
                    { m -> Fact("خطای ایمنی", r.safetyFailures.toString(), m, figure = true, color = if (r.safetyFailures > 0) c.negative else c.positive) },
                    { m -> Fact("کد یا لینک اشتباه", r.wrongCodes.toString(), m, figure = true, color = if (r.wrongCodes > 0) c.negative else c.positive) },
                ))
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Fig(r.suite, style = Divan.type.figureSmall, color = c.textMuted)
                    Text(jDateTime(r.at), style = Divan.type.micro, color = c.textMuted)
                }
                if (r.disagreements.isNotEmpty()) Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("اختلاف‌ها (در صف آموزش تو)", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
                    for (d in r.disagreements) Row(
                        Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(c.tile).padding(10.dp),
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        LabelPill(VERDICT_FA[d.verdict], d.verdict)
                        Text(prose(d.noteFa), style = Divan.type.caption, color = c.textPrimary, modifier = Modifier.weight(1f))
                        Fig(d.case, style = Divan.type.figureSmall, color = c.textMuted)
                    }
                }
            } else Text(
                prose("تاریخچه‌ی واقعی گفت‌وگوهای پشتیبانی را بده (خروجی Telegram Desktop یا CSV پرسش و پاسخ)؛ تا ۱۰۰ سؤال ماسک‌شده با جواب‌های خودت آزمون خصوصی همین شرکت میشود."),
                style = Divan.type.small, color = c.textSecondary,
            )
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                HqButton(if (sending) "بارگذاری…" else "تاریخچه‌ی گفت‌وگو", { pick.launch(arrayOf("application/json", "text/csv", "text/comma-separated-values", "text/plain")) },
                    variant = BtnVariant.SECONDARY, size = BtnSize.SM, icon = DivanIcon.ATTACH, loading = sending)
                HqButton("اجرای آزمون", {
                    run.go(toasts) {
                        env.api.runShadow(company)
                        env.cache.invalidate("support")
                        toasts.ok("اجرا شروع شد؛ هزینه‌اش از سقف آکادمی است.")
                    }
                }, variant = BtnVariant.PRIMARY, size = BtnSize.SM, icon = DivanIcon.REFRESH, enabled = r != null, loading = run.busy)
            }
        }
    }
}
