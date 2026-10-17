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

private fun avatarKind(k: String) = when (k) { "advisor" -> "advisor"; "ceo" -> "ceo"; "manager" -> "manager"; else -> "employee" }

/** The meeting room: one thread per counterpart (advisor, CEOs, managers). */
@Composable
fun ThreadsScreen() {
    val nav = LocalNav.current
    val c = Divan.colors
    val q = rememberQuery("threads", "threads") { threads() }
    val r = refresher(q)
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item { PageHeader("پیام‌ها", eyebrow = "گفت‌وگو با مشاور، مدیرعامل‌ها و مدیرها") }
        val list = q.data
        when {
            list == null && q.error == null -> items(4) { Skeleton(Modifier.fillMaxWidth().height(64.dp)) }
            list == null -> item { ErrorBlock(q.error, { q.refresh() }) }
            list.isEmpty() -> item { Empty("هنوز گفت‌وگویی نیست", icon = DivanIcon.MESSAGES) }
            else -> item {
                Column(Modifier.clip(RoundedCornerShape(16.dp)).background(c.card)) {
                    list.sortedByDescending { it.lastMessageAt }.forEachIndexed { i, t ->
                        if (i > 0) HorizontalDivider(color = c.lineDivider)
                        Row(
                            Modifier.fillMaxWidth().clickable(role = Role.Button) { nav.go(if (t.kind == "advisor") "advisor" else "messages/${t.code}") }.padding(14.dp),
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(12.dp),
                        ) {
                            if (t.kind == "advisor") Orb(36.dp) else Avatar(avatarKind(t.kind), size = 36.dp)
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
        val full = "دریافت شد. در حالت نمایشی پاسخ واقعی ساخته نمیشود؛ روی سرور، مشاور با Opus 5.5 جواب میدهد و ارجاع‌هایش را میاورد."
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
private fun Bubble(m: Message, agentKind: String) {
    val nav = LocalNav.current
    val c = Divan.colors
    val mine = m.author.kind == "owner"
    Row(Modifier.fillMaxWidth(), horizontalArrangement = if (mine) Arrangement.End else Arrangement.Start) {
        if (!mine) {
            Box(Modifier.padding(top = 4.dp, end = 10.dp)) { if (agentKind == "advisor") Orb(32.dp) else Avatar(agentKind, size = 32.dp) }
        }
        Column(Modifier.widthIn(max = 320.dp), horizontalAlignment = if (mine) Alignment.End else Alignment.Start, verticalArrangement = Arrangement.spacedBy(4.dp)) {
            val shape = if (mine) RoundedCornerShape(16.dp, 6.dp, 16.dp, 16.dp) else RoundedCornerShape(6.dp, 16.dp, 16.dp, 16.dp)
            Box(Modifier.clip(shape).background(if (mine) c.raised else c.card).padding(horizontal = 14.dp, vertical = 10.dp)) {
                Md(m.body, color = c.textPrimary)
            }
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text(jTime(m.createdAt), style = Divan.type.micro, color = c.textMuted)
                Fig(m.ref, style = Divan.type.figureSmall, color = c.textMuted)
                for ((k, v) in m.links) {
                    val ref = (v as? JsonPrimitive)?.contentOrNull ?: continue
                    val route = when (k) { "decision" -> "cartable/$ref"; "work" -> "work/$ref"; else -> null }
                    Fig(ref, Modifier.clip(CircleShape).background(c.tile).clickable(enabled = route != null) { route?.let(nav::go) }.padding(horizontal = 8.dp, vertical = 2.dp), style = Divan.type.figureSmall, color = c.goldInk)
                }
            }
        }
    }
}

/** One conversation. The advisor's (thread `A`) opens with suggestions; replies stream in live. */
@Composable
fun ChatScreen(code: String, advisor: Boolean = false) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val scope = rememberCoroutineScope()
    val q = rememberQuery("messages:$code", "messages", maxAgeMs = 5_000) { messages(code) }
    val threads = rememberQuery("threads", "threads") { threads() }
    val thread = threads.data?.firstOrNull { it.code == code }
    val agentKind = if (advisor) "advisor" else avatarKind(thread?.kind ?: "employee")
    val live = remember(code) { LiveReply() }
    var text by rememberSaveable(code) { mutableStateOf("") }
    var sending by remember { mutableStateOf(false) }
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

    fun submit(body: String) {
        val b = body.trim()
        if (b.isEmpty() || sending) return
        sending = true
        scope.launch {
            try {
                env.api.send(code, b)
                text = ""
                env.cache.invalidate("messages", "threads")
                scope.launch { startLive(scope, env, code, live) }
            } catch (e: com.coinepro.hq.core.net.ApiException) {
                toasts.error(e.messageFa)
            } finally {
                sending = false
            }
        }
    }

    Column(Modifier.fillMaxSize().imePadding()) {
        Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 10.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            if (advisor) Orb(40.dp, state = when (live.state) { LiveState.THINKING -> "thinking"; LiveState.WRITING -> "speaking"; else -> "rest" })
            else Avatar(agentKind, size = 40.dp, state = if (live.state != LiveState.IDLE) "working" else "idle")
            Column(Modifier.weight(1f)) {
                Text(if (advisor) "مشاور کل" else thread?.titleFa ?: code, style = Divan.type.h3)
                Text(if (advisor) "بیرون از همه‌ی شرکت‌ها، فقط برای تو. فقط‌خواندنی؛ به همه‌چیز ارجاع میدهد." else "هر پیام شناسه‌ی ثابت دارد و میماند.", style = Divan.type.micro, color = c.textMuted, maxLines = 2)
            }
        }
        HorizontalDivider(color = c.lineDivider)
        LazyColumn(Modifier.weight(1f), state = list, contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
            when {
                q.data == null && q.error == null -> items(3) { i -> Skeleton(Modifier.fillMaxWidth(if (i % 2 == 0) 0.75f else 0.6f).height(72.dp), radius = 16.dp) }
                q.data == null -> item { ErrorBlock(q.error, { q.refresh() }) }
                items.isEmpty() && live.state == LiveState.IDLE -> item { Empty("گفت‌وگو هنوز شروع نشده", icon = DivanIcon.MESSAGES, body = "هر پیام شناسه‌ی ثابت دارد و برای همیشه میماند؛ بعداً میتوانی به آن استناد کنی.") }
                else -> items(items, key = { it.id }) { m -> Bubble(m, agentKind) }
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
        if (advisor && items.isEmpty() && q.data != null) {
            FlowRow(Modifier.padding(horizontal = 16.dp), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                for (s in listOf("امروز اول به کدام تصمیم برسم؟", "مصرف توکن این هفته را با هفته‌ی قبل مقایسه کن.", "کدام شرکت بیشترین ریسک را دارد و چرا؟")) {
                    Text(s, style = Divan.type.small, color = c.textSecondary, modifier = Modifier.clip(CircleShape).border(1.dp, c.lineStrong, CircleShape).clickable { submit(s) }.padding(horizontal = 12.dp, vertical = 6.dp))
                }
            }
        }
        Row(
            Modifier.fillMaxWidth().padding(12.dp).clip(RoundedCornerShape(16.dp)).background(c.card).border(1.dp, c.lineStrong, RoundedCornerShape(16.dp)).padding(6.dp),
            verticalAlignment = Alignment.Bottom,
            horizontalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            BasicTextField(
                text, { if (it.length <= 10_000) text = it },
                Modifier.weight(1f).heightIn(min = 44.dp).padding(horizontal = 8.dp, vertical = 10.dp).semantics { contentDescription = "پیام" },
                textStyle = Divan.type.body.copy(color = c.textPrimary),
                cursorBrush = SolidColor(c.goldInk),
                maxLines = 6,
                decorationBox = { inner ->
                    Box {
                        if (text.isEmpty()) Text(if (advisor) "از مشاور بپرس…" else "پیام…", style = Divan.type.body, color = c.textMuted)
                        inner()
                    }
                },
            )
            val can = text.isNotBlank() && !sending
            Box(
                Modifier.size(44.dp).clip(CircleShape).background(if (can) c.goldFill else c.disabledFill).clickable(enabled = can, role = Role.Button, onClickLabel = "بفرست") { submit(text) },
                contentAlignment = Alignment.Center,
            ) { DIcon(DivanIcon.SEND, size = 20.dp, tint = if (can) c.onGold else c.disabledText) }
        }
    }
}
