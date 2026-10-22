package com.coinepro.hq.ui.messages

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.Env
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.format.jTime
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.Message
import com.coinepro.hq.designsystem.Avatar
import com.coinepro.hq.designsystem.Badge
import com.coinepro.hq.designsystem.CompanyMark
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.Md
import com.coinepro.hq.designsystem.Orb
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.media.Composer
import com.coinepro.hq.ui.media.MessageMedia
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.refresher
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import okhttp3.Request
import okhttp3.Response
import okhttp3.sse.EventSource
import okhttp3.sse.EventSourceListener
import okhttp3.sse.EventSources

private fun avatarKind(k: String) = when (k) { "advisor" -> "advisor"; "overseer" -> "overseer"; "assistant" -> "assistant"; "ceo" -> "ceo"; "manager" -> "manager"; else -> "employee" }

/** The two personal counterparts beside the advisor (contract §18): their thread, their route, their words. */
private data class Counterpart(val title: String, val sub: String, val placeholder: String, val suggestions: List<String>)

private val COUNTERPARTS = mapOf(
    "overseer" to Counterpart(
        "ناظر کل", "آموزش بده، بپرس یا دستور بده؛ هر دستور دائمی با مُهر تو قطعی میشود.", "آموزش بده، بپرس یا دستور بده…",
        listOf("امروز کدام شرکت بیشتر از همه از پروتکل‌ها جا ماند؟", "یافته‌های بحرانی باز را با شاهد بگو.", "در نبودم چه چیزی را نگه داشتی و چرا؟"),
    ),
    "assistant" to Counterpart(
        "دستیار شخصی", "کارهای دم‌دستی‌ات را با اینترنت انجام میدهد؛ هر خرید، ارسال یا ثبت‌نام فقط با مُهر تو.", "بگو چه کار کنم… (ویس، عکس یا فایل هم میشود)",
        listOf("سه پیشنهاد هتل در استانبول زیر ۱۵۰ یورو پیدا کن", "خبرهای امروز بازار طلا را با منبع خلاصه کن", "یک ایمیل مؤدبانه برای عقب انداختن جلسه بنویس"),
    ),
)

/** The meeting room: one thread per counterpart (advisor, CEOs, managers). */
@Composable
fun ThreadsScreen() {
    val nav = LocalNav.current
    val c = Divan.colors
    val q = rememberQuery("threads", "threads") { threads() }
    val r = refresher(q)
    var text by rememberSaveable { mutableStateOf("") }
    var query by remember { mutableStateOf("") }
    LaunchedEffect(text) { kotlinx.coroutines.delay(300); query = text.trim() }
    val hits = if (query.length >= 2) rememberQuery("search:messages:$query", "messages", maxAgeMs = 30_000) { searchMessages(query) } else null
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item { PageHeader("پیام‌ها", eyebrow = "گفت‌وگو با مشاور، مدیرعامل‌ها و مدیرها") }
        item { com.coinepro.hq.designsystem.HqTextField(text, { text = it }, "جستجو در همه‌ی پیام‌ها", Modifier.fillMaxWidth(), maxLength = 200) }
        val list = q.data
        if (hits != null) {
            val found = hits.data?.items
            when {
                found == null && hits.error != null -> item { ErrorBlock(hits.error, { hits.refresh() }) }
                found == null -> items(3) { Skeleton(Modifier.fillMaxWidth().height(64.dp)) }
                found.isEmpty() -> item { Text("در پیام‌ها پیدا نشد.", style = Divan.type.caption, color = c.textMuted) }
                else -> items(found, key = { it.id }) { h ->
                    Column(
                        Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(c.card).clickable(role = Role.Button) {
                            val t = list?.firstOrNull { it.code == h.thread }
                            nav.go(when (t?.kind) { "advisor" -> "advisor"; "overseer" -> "oversight/chat"; "assistant" -> "assistant"; else -> "messages/${h.thread}" })
                        }.padding(14.dp),
                        verticalArrangement = Arrangement.spacedBy(4.dp),
                    ) {
                        Text(h.body.replace(Regex("[*_`#>]"), ""), style = Divan.type.small, color = c.textPrimary, maxLines = 2, overflow = TextOverflow.Ellipsis)
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            Text(com.coinepro.hq.core.format.actorFa(h.author), style = Divan.type.micro, color = c.textMuted)
                            Fig(h.ref, style = Divan.type.figureSmall, color = c.textMuted)
                            Text(com.coinepro.hq.core.format.jDate(h.createdAt), style = Divan.type.micro, color = c.textMuted)
                        }
                    }
                }
            }
            return@Page
        }
        when {
            list == null && q.error == null -> items(4) { Skeleton(Modifier.fillMaxWidth().height(64.dp)) }
            list == null -> item { ErrorBlock(q.error, { q.refresh() }) }
            list.isEmpty() -> item { Empty("هنوز گفت‌وگویی نیست", icon = DivanIcon.MESSAGES) }
            else -> item {
                Column(Modifier.clip(RoundedCornerShape(16.dp)).background(c.card)) {
                    list.sortedByDescending { it.lastMessageAt }.forEachIndexed { i, t ->
                        if (i > 0) HorizontalDivider(color = c.lineDivider)
                        Row(
                            Modifier.fillMaxWidth().clickable(role = Role.Button) { nav.go(when (t.kind) { "advisor" -> "advisor"; "overseer" -> "oversight/chat"; "assistant" -> "assistant"; else -> "messages/${t.code}" }) }.padding(14.dp),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(12.dp),
                        ) {
                            if (t.kind == "advisor") Orb(36.dp) else Avatar(avatarKind(t.kind), size = 36.dp, label = t.titleFa)
                            Column(Modifier.weight(1f)) {
                                Text(t.titleFa, style = Divan.type.small.copy(fontWeight = if (t.unread > 0) FontWeight.Bold else FontWeight.SemiBold), color = if (t.unread > 0) c.textPrimary else c.textSecondary, maxLines = 1, overflow = TextOverflow.Ellipsis)
                                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                    t.company?.let { CompanyMark(it, height = 11.dp, mono = true, ink = c.textMuted) }
                                    Text(ago(t.lastMessageAt), style = Divan.type.micro, color = c.textMuted)
                                }
                            }
                            if (t.unread > 0) Badge(t.unread)
                        }
                    }
                }
            }
        }
    }
}

private enum class LiveState { IDLE, THINKING, WRITING, FAILED }

private class LiveReply {
    var state by mutableStateOf(LiveState.IDLE)
    var text by mutableStateOf("")
    var source: EventSource? = null
}

/** Watch the agent's reply while it is written (contract §16.3): `reply.delta` chunks until `reply.done`.
 *  Without the live endpoint, polls the thread for the stored reply for up to two minutes. */
private suspend fun startLive(scope: CoroutineScope, env: Env, code: String, live: LiveReply) {
    live.source?.cancel()
    live.state = LiveState.THINKING
    live.text = ""
    if (env.demo) {
        val full = "دریافت شد. در حالت نمایشی پاسخ واقعی ساخته نمیشود؛ روی سرور، جواب واقعی با ارجاع‌ها و شاهدش میاید."
        delay(900)
        var i = 0
        while (i < full.length) { i = minOf(full.length, i + 6); live.state = LiveState.WRITING; live.text = full.take(i); delay(60) }
        delay(600)
        live.state = LiveState.IDLE
        return
    }
    var got = false
    val finish = {
        live.source?.cancel()
        env.cache.invalidate("messages", "threads")
        live.state = LiveState.IDLE
    }
    val req = Request.Builder().url(env.api.url("/threads/${java.net.URLEncoder.encode(code, "UTF-8")}/live")).header("Accept", "text/event-stream").build()
    live.source = EventSources.createFactory(env.api.streamClient).newEventSource(req, object : EventSourceListener() {
        override fun onEvent(eventSource: EventSource, id: String?, type: String?, data: String) {
            when (type) {
                "reply.delta" -> {
                    got = true
                    val t = runCatching { Api.json.parseToJsonElement(data).jsonObject["text"]?.jsonPrimitive?.contentOrNull }.getOrNull().orEmpty()
                    live.state = LiveState.WRITING
                    live.text += t
                }
                "reply.done" -> finish()
                "reply.failed" -> { eventSource.cancel(); live.state = LiveState.FAILED }
            }
        }

        override fun onFailure(eventSource: EventSource, t: Throwable?, response: Response?) {
            response?.close()
            if (got) return finish()
            live.state = LiveState.IDLE
            scope.launch { repeat(40) { delay(3_000); env.cache.invalidate("messages", "threads") } }
        }
    })
}

@Composable
private fun Bubble(m: Message, agentKind: String, onResolve: (Message) -> Unit) {
    val nav = LocalNav.current
    val c = Divan.colors
    val mine = m.author.kind == "owner"
    Row(Modifier.fillMaxWidth(), horizontalArrangement = if (mine) Arrangement.End else Arrangement.Start) {
        if (!mine) {
            Box(Modifier.padding(top = 4.dp, end = 10.dp)) { if (agentKind == "advisor") Orb(32.dp) else Avatar(agentKind, size = 32.dp) }
        }
        Column(Modifier.widthIn(max = 320.dp), horizontalAlignment = if (mine) Alignment.End else Alignment.Start, verticalArrangement = Arrangement.spacedBy(6.dp)) {
            val voice = m.kind == "voice_transcript"
            MessageMedia(m.attachments, transcriptInBody = voice)
            val shape = if (mine) RoundedCornerShape(16.dp, 6.dp, 16.dp, 16.dp) else RoundedCornerShape(6.dp, 16.dp, 16.dp, 16.dp)
            if (m.body.isNotBlank()) {
                Box(Modifier.clip(shape).background(if (mine) c.raised else c.card).padding(horizontal = 14.dp, vertical = 10.dp)) {
                    Md(m.body, color = c.textPrimary)
                }
            }
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp), itemVerticalAlignment = Alignment.CenterVertically) {
                // ⟨1.5⟩ §21.1, §21.3: the advisor's devil's-advocate replies, proactive notes and the weekly review brief carry `meta`.
                m.meta?.let { MetaTags(it) }
                if (voice) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(2.dp)) {
                    DIcon(DivanIcon.MIC, size = 12.dp, tint = c.textMuted)
                    Text("ویس", style = Divan.type.micro, color = c.textMuted)
                }
                Text(jTime(m.createdAt), style = Divan.type.micro, color = c.textMuted)
                Fig(m.ref, style = Divan.type.figureSmall, color = c.textMuted)
                for ((k, v) in m.links) {
                    val ref = (v as? JsonPrimitive)?.contentOrNull ?: continue
                    val route = when (k) {
                        "decision" -> "cartable/$ref"; "work" -> "work/$ref"; "resolution" -> "resolutions"; "errand" -> "assistant"; "teaching" -> "academy"
                        "inquiry" -> "advisor"; "finding" -> "oversight"; "session" -> "workshop/$ref"; else -> null
                    }
                    Fig(ref, Modifier.clip(CircleShape).background(c.tile).clickable(enabled = route != null) { route?.let(nav::go) }.padding(horizontal = 8.dp, vertical = 2.dp), style = Divan.type.figureSmall, color = c.goldInk)
                }
                if (m.body.isNotBlank()) Text("مصوبه", style = Divan.type.micro, color = c.textSecondary, modifier = Modifier.clip(CircleShape).clickable(onClickLabel = "این پیام را به‌عنوان مصوبه ثبت کن") { onResolve(m) }.padding(horizontal = 8.dp, vertical = 2.dp))
            }
        }
    }
}

/** The labels a message of thread A carries (§21.1, §21.3): the devil's advocate, a proactive note and its kind, the weekly review. */
@Composable
private fun MetaTags(meta: com.coinepro.hq.core.net.AdvisorMeta) {
    val c = Divan.colors
    if (meta.mode == "devil") Text("مخالف‌خوان", Modifier.clip(CircleShape).background(c.softNegative).padding(horizontal = 8.dp, vertical = 2.dp), style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = c.negative)
    meta.proactive?.let { p ->
        val k = com.coinepro.hq.ui.v18.TRIGGER[p.kind]
        Row(Modifier.clip(CircleShape).background(c.softLapis).padding(horizontal = 8.dp, vertical = 2.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            DIcon(k?.icon ?: DivanIcon.BELL, size = 12.dp, tint = c.lapis)
            Text("گزارش فعال · ${k?.fa ?: p.kind}", style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = c.lapis)
        }
    }
    meta.review?.let { r ->
        Row(Modifier.clip(CircleShape).background(c.softGold).padding(horizontal = 8.dp, vertical = 2.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            Text("مرور هفتگی", style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = c.goldInk)
            Fig(r, style = Divan.type.figureSmall, color = c.goldInk)
        }
    }
}

/** One conversation. The advisor's (thread `A`), the overseer's (`N`) and the assistant's (`P`) open with suggestions;
 *  replies stream in live. [headerAction] sits at the end of the header (the assistant's errands); [subHeader] under it (the advisor's
 *  tools, ⟨1.5⟩ §21). [mode] `"devil"` sends in the devil's-advocate mode (thread A only, §21.1), with its own [placeholder]. */
@Composable
fun ChatScreen(
    code: String,
    advisor: Boolean = false,
    agent: String? = null,
    headerAction: (@Composable () -> Unit)? = null,
    subHeader: (@Composable () -> Unit)? = null,
    mode: String? = null,
    placeholder: String? = null,
) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val scope = rememberCoroutineScope()
    val q = rememberQuery("messages:$code", "messages", maxAgeMs = 5_000) { messages(code) }
    val threads = rememberQuery("threads", "threads") { threads() }
    val thread = threads.data?.firstOrNull { it.code == code }
    val agentKind = if (advisor) "advisor" else agent ?: avatarKind(thread?.kind ?: "employee")
    val who = COUNTERPARTS[agentKind]
    val live = remember(code) { LiveReply() }
    var resolve by remember { mutableStateOf<Message?>(null) }
    val list = rememberLazyListState()
    val items = q.data?.items.orEmpty()
    val lastRef = items.lastOrNull()?.ref
    DisposableEffect(code) { onDispose { live.source?.cancel() } }
    LaunchedEffect(lastRef) {
        if (lastRef != null) {
            runCatching { env.api.markRead(code, lastRef) }
            env.cache.invalidate("threads", "inbox")
        }
    }
    LaunchedEffect(items.size, live.text.length) { if (items.isNotEmpty()) list.animateScrollToItem(list.layoutInfo.totalItemsCount.coerceAtLeast(1) - 1) }

    suspend fun send(body: String, attachments: List<String>) {
        try {
            env.api.send(code, body, attachments, mode)
            env.cache.invalidate("messages", "threads")
            scope.launch { startLive(scope, env, code, live) }
        } catch (e: com.coinepro.hq.core.net.ApiException) {
            toasts.error(e.messageFa)
            throw e
        }
    }

    Column(Modifier.fillMaxSize().imePadding()) {
        Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 10.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            if (advisor) Orb(40.dp, state = when (live.state) { LiveState.THINKING -> "thinking"; LiveState.WRITING -> "speaking"; else -> if (mode == "devil") "thinking" else "rest" })
            else Avatar(agentKind, size = 40.dp, state = if (live.state != LiveState.IDLE) "working" else "idle")
            Column(Modifier.weight(1f)) {
                Text(if (advisor) "مشاور کل" else who?.title ?: thread?.titleFa ?: code, style = Divan.type.h3)
                Text(if (advisor) "رتبه‌ی دوم؛ همه‌چیز را میخواند و از مدیرها رسمی میپرسد. به همه‌چیز ارجاع میدهد." else who?.sub ?: "هر پیام شناسه‌ی ثابت دارد و میماند.", style = Divan.type.micro, color = c.textMuted, maxLines = 2)
            }
            headerAction?.invoke()
        }
        subHeader?.invoke()
        HorizontalDivider(color = c.lineDivider)
        LazyColumn(Modifier.weight(1f), state = list, contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
            when {
                q.data == null && q.error == null -> items(3) { i -> Skeleton(Modifier.fillMaxWidth(if (i % 2 == 0) 0.75f else 0.6f).height(72.dp), radius = 16.dp) }
                q.data == null -> item { ErrorBlock(q.error, { q.refresh() }) }
                items.isEmpty() && live.state == LiveState.IDLE -> item { Empty("گفت‌وگو هنوز شروع نشده", icon = DivanIcon.MESSAGES, body = "هر پیام شناسه‌ی ثابت دارد و برای همیشه میماند؛ بعداً میتوانی به آن استناد کنی.") }
                else -> items(items, key = { it.id }) { m -> Bubble(m, agentKind) { resolve = it } }
            }
            if (live.state != LiveState.IDLE) item {
                Row {
                    Box(Modifier.padding(top = 4.dp, end = 10.dp)) {
                        if (agentKind == "advisor") Orb(32.dp, state = if (live.state == LiveState.THINKING) "thinking" else "speaking") else Avatar(agentKind, size = 32.dp, state = "working")
                    }
                    Box(Modifier.widthIn(max = 320.dp).clip(RoundedCornerShape(6.dp, 16.dp, 16.dp, 16.dp)).background(c.card).padding(horizontal = 14.dp, vertical = 10.dp)) {
                        when (live.state) {
                            LiveState.THINKING -> Text("در حال فکر…", style = Divan.type.small, color = c.textMuted)
                            LiveState.FAILED -> Text("پاسخ ساخته نشد؛ دوباره بپرس.", style = Divan.type.small, color = c.negative)
                            else -> Md(live.text, color = c.textPrimary)
                        }
                    }
                }
            }
        }
        val suggestions = if (advisor) listOf("امروز اول به کدام تصمیم برسم؟", "مصرف توکن این هفته را با هفته‌ی قبل مقایسه کن.", "کدام شرکت بیشترین ریسک را دارد و چرا؟") else who?.suggestions
        if (suggestions != null && items.isEmpty() && q.data != null) {
            FlowRow(Modifier.padding(horizontal = 16.dp), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                for (s in suggestions) {
                    Text(s, style = Divan.type.small, color = c.textSecondary, modifier = Modifier.clip(CircleShape).border(1.dp, c.lineStrong, CircleShape).clickable { scope.launch { runCatching { send(s, emptyList()) } } }.padding(horizontal = 12.dp, vertical = 6.dp))
                }
            }
        }
        Composer(placeholder ?: if (advisor) "از مشاور بپرس…" else who?.placeholder ?: "پیام…", { b, a -> send(b, a) }, Modifier.padding(12.dp), draftKey = "chat:$code")
    }
    resolve?.let { m -> com.coinepro.hq.ui.owner.RecordResolutionSheet(m.ref, m.body) { resolve = null } }
}
