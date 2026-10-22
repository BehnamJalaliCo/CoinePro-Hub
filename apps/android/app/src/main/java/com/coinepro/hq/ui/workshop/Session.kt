package com.coinepro.hq.ui.workshop

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.Stable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.Env
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.actorFa
import com.coinepro.hq.core.format.jTime
import com.coinepro.hq.core.format.modelLabel
import com.coinepro.hq.core.format.usd
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.SessionEvent
import com.coinepro.hq.designsystem.Avatar
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.CompanyMark
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.Md
import com.coinepro.hq.designsystem.MeterBar
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.RichText
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.budgetTone
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.activity
import com.coinepro.hq.ui.media.Composer
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.intOrNull
import okhttp3.Request
import okhttp3.Response
import okhttp3.sse.EventSource
import okhttp3.sse.EventSourceListener
import okhttp3.sse.EventSources

private fun SessionEvent.str(k: String): String? = (data[k] as? JsonPrimitive)?.contentOrNull
private fun SessionEvent.int(k: String): Int? = (data[k] as? JsonPrimitive)?.intOrNull
private fun SessionEvent.num(k: String): Double? = (data[k] as? JsonPrimitive)?.doubleOrNull
private fun SessionEvent.bool(k: String): Boolean? = (data[k] as? JsonPrimitive)?.booleanOrNull

/** A session's events: the stored history, then live (SSE `/live`, resuming from the last seq). Without the live
 *  endpoint, and in the demo, it polls `?after=`. */
@Stable
class SessionFeed {
    val events = mutableStateListOf<SessionEvent>()
    var live by mutableStateOf(false)
    var error by mutableStateOf<ApiException?>(null)
    val last: Long get() = events.lastOrNull()?.seq ?: 0
}

@Composable
private fun rememberSessionFeed(env: Env, ref: String): SessionFeed {
    val feed = remember(env, ref) { SessionFeed() }
    DisposableEffect(feed) {
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
        var source: EventSource? = null
        fun add(e: SessionEvent) {
            if (e.seq <= feed.last) return
            feed.events.add(e)
            if (e.type == "state" || e.type == "approval_result" || e.type == "approval_request") env.cache.invalidate("workshop")
        }
        suspend fun poll(every: Long) {
            feed.live = true
            while (currentCoroutineContext().isActive) {
                delay(every)
                runCatching { env.api.sessionEvents(ref, feed.last).items }.getOrNull()?.forEach(::add)
            }
        }
        scope.launch {
            try {
                env.api.sessionEvents(ref).items.forEach(::add)
            } catch (e: ApiException) {
                feed.error = e
                return@launch
            }
            if (env.demo) return@launch poll(2_200)
            val req = Request.Builder().url(env.api.url("/workshop/sessions/${java.net.URLEncoder.encode(ref, "UTF-8")}/live"))
                .header("Accept", "text/event-stream").header("Last-Event-ID", feed.last.toString()).build()
            source = EventSources.createFactory(env.api.streamClient).newEventSource(req, object : EventSourceListener() {
                override fun onOpen(eventSource: EventSource, response: Response) { scope.launch { feed.live = true } }
                override fun onEvent(eventSource: EventSource, id: String?, type: String?, data: String) {
                    val e = runCatching { Api.json.decodeFromString(SessionEvent.serializer(), data) }.getOrNull() ?: return
                    scope.launch { add(e) }
                }
                override fun onFailure(eventSource: EventSource, t: Throwable?, response: Response?) {
                    response?.close()
                    scope.launch { feed.live = false; poll(4_000) }
                }
            })
        }
        onDispose { source?.cancel(); scope.cancel() }
    }
    return feed
}

@Composable
private fun ApprovalCard(e: SessionEvent, answered: SessionEvent?, busy: Boolean, onAnswer: (Boolean) -> Unit) {
    val c = Divan.colors
    val shape = RoundedCornerShape(14.dp)
    Column(
        Modifier.fillMaxWidth().clip(shape).background(if (answered == null) c.softGold else c.tile)
            .then(if (answered == null) Modifier.border(1.dp, c.goldInk, shape) else Modifier).padding(14.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            DIcon(DivanIcon.SEAL, size = 18.dp, tint = c.goldInk, active = answered == null)
            RichText(e.summaryFa, Modifier.weight(1f), style = Divan.type.bodyStrong, color = c.textPrimary)
            Fig(e.str("approval_id").orEmpty(), style = Divan.type.figureSmall, color = c.textMuted)
        }
        e.str("detail")?.let { CodeLine(it) }
        if (answered != null) {
            val allowed = answered.bool("allow") == true
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                DIcon(if (allowed) DivanIcon.SEAL else DivanIcon.REJECT, size = 14.dp, tint = if (allowed) c.positive else c.negative)
                Text((if (allowed) "اجازه دادی" else "اجازه ندادی") + " · " + jTime(answered.at), style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = if (allowed) c.positive else c.negative)
            }
        } else {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                HqButton("اجازه بده", { onAnswer(true) }, variant = BtnVariant.PRIMARY, icon = DivanIcon.SEAL, loading = busy)
                HqButton("نه", { onAnswer(false) }, enabled = !busy)
                Text("با اثر انگشت", style = Divan.type.micro, color = c.textMuted)
            }
        }
    }
}

/** A command or a git line: left to right, scrolls sideways instead of wrapping. */
@Composable
private fun CodeLine(text: String, prefix: String? = null) {
    val c = Divan.colors
    androidx.compose.runtime.CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
        Box(Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(c.page).horizontalScroll(rememberScrollState()).padding(horizontal = 12.dp, vertical = 8.dp)) {
            Fig((prefix ?: "") + text, style = Divan.type.figureSmall, color = c.textPrimary)
        }
    }
}

@Composable
private fun EventItem(e: SessionEvent, driverKind: String) {
    val c = Divan.colors
    val mine = e.actor.kind == "owner"
    when (e.type) {
        "message" -> Row(Modifier.fillMaxWidth(), horizontalArrangement = if (mine) Arrangement.End else Arrangement.Start) {
            if (!mine) Box(Modifier.padding(top = 4.dp, end = 8.dp)) { Avatar(driverKind, size = 28.dp) }
            Column(Modifier.widthIn(max = 320.dp), horizontalAlignment = if (mine) Alignment.End else Alignment.Start, verticalArrangement = Arrangement.spacedBy(4.dp)) {
                val shape = if (mine) RoundedCornerShape(14.dp, 6.dp, 14.dp, 14.dp) else RoundedCornerShape(6.dp, 14.dp, 14.dp, 14.dp)
                Box(Modifier.clip(shape).background(if (mine) c.raised else c.card).padding(horizontal = 14.dp, vertical = 10.dp)) { Md(e.summaryFa, color = c.textPrimary) }
                Text((if (mine) "تو" else actorFa(e.actor)) + " · " + jTime(e.at), style = Divan.type.micro, color = c.textMuted)
            }
        }
        "command" -> Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(10.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            CodeLine(e.str("cmd").orEmpty(), "$ ")
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                e.int("exit_code")?.let { Pill("exit $it", if (it == 0) Tone.POS else Tone.NEG, dot = true, figure = true) }
                RichText(e.summaryFa, Modifier.weight(1f), style = Divan.type.caption)
                e.num("duration_s")?.let { Fig("${it.toInt()}s", style = Divan.type.figureSmall, color = c.textMuted) }
            }
        }
        "file_change" -> Row(Modifier.fillMaxWidth().padding(horizontal = 4.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            DIcon(DivanIcon.EDIT, size = 16.dp, tint = c.textSecondary)
            Fig(e.str("path").orEmpty(), Modifier.weight(1f), style = Divan.type.figureSmall, color = c.textPrimary)
            Fig("+${e.int("added") ?: 0}", style = Divan.type.figureSmall, color = c.positive)
            Fig("−${e.int("removed") ?: 0}", style = Divan.type.figureSmall, color = c.negative)
        }
        "state" -> Row(Modifier.fillMaxWidth().padding(vertical = 2.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            HorizontalDivider(Modifier.weight(1f), color = c.lineDivider)
            RichText(e.summaryFa + " · " + jTime(e.at), style = Divan.type.micro, color = c.textMuted)
            HorizontalDivider(Modifier.weight(1f), color = c.lineDivider)
        }
        "error" -> Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.softNegative).padding(10.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            DIcon(DivanIcon.URGENT, size = 16.dp, tint = c.negative)
            RichText(e.summaryFa, style = Divan.type.small, color = c.negative)
        }
        "approval_result" -> Unit // shown on its request
        else -> Row(Modifier.fillMaxWidth().padding(horizontal = 4.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Box(Modifier.padding(top = 8.dp).size(6.dp).clip(CircleShape).background(c.silverInk))
            RichText(e.summaryFa, Modifier.weight(1f), style = Divan.type.small)
            Text(jTime(e.at), style = Divan.type.micro, color = c.textMuted)
        }
    }
}

/** One Code Workshop session, live (contract §17.3): what the driver does, the owner's approvals, steering, stop. */
@Composable
fun SessionScreen(ref: String) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val context = LocalContext.current
    val act = activity()
    val c = Divan.colors
    val q = rememberQuery("workshop:session:$ref", "workshop", maxAgeMs = 5_000) { codeSession(ref) }
    val workspaces = rememberWorkspaces()
    val grants = rememberGrants()
    val feed = rememberSessionFeed(env, ref)
    val list = rememberLazyListState()
    val answer = rememberAction()
    val stop = rememberAction()
    var answering by remember { mutableStateOf<String?>(null) }
    var confirm by remember { mutableStateOf(false) }
    LaunchedEffect(feed.events.size) { if (feed.events.isNotEmpty()) list.animateScrollToItem(list.layoutInfo.totalItemsCount.coerceAtLeast(1) - 1) }

    val s = q.data
    if (s == null) {
        Column(Modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            if (q.error != null) ErrorBlock(q.error, { q.refresh() }) else { Skeleton(Modifier.fillMaxWidth().height(120.dp), radius = 16.dp); Skeleton(Modifier.fillMaxWidth().height(300.dp), radius = 16.dp) }
        }
        return
    }
    val ws = workspaces.data?.firstOrNull { it.code == s.workspace }
    val grant = grants.data?.firstOrNull { it.ref == s.grant }
    val results = feed.events.filter { it.type == "approval_result" }.associateBy { it.str("approval_id") }

    Column(Modifier.fillMaxSize().imePadding()) {
        LazyColumn(Modifier.weight(1f), state = list, contentPadding = PaddingValues(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            item {
                HqCard {
                    Row(verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        CompanyMark(companyOf(workspaces.data, s.workspace), height = 16.dp, mono = true, ink = c.textSecondary, modifier = Modifier.padding(top = 5.dp))
                        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                            Text(s.title, style = Divan.type.h2)
                            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                Fig(s.ref, style = Divan.type.figureSmall, color = c.textMuted)
                                Fig(ws?.repo ?: s.workspace, style = Divan.type.figureSmall, color = c.textMuted)
                                s.branch?.let { Fig(it, style = Divan.type.figureSmall, color = c.textMuted) }
                            }
                        }
                    }
                    Row(Modifier.padding(top = 10.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        StatePill(s.state)
                        if (s.open) HqButton("توقف", { confirm = true }, variant = BtnVariant.DANGER, size = BtnSize.SM, icon = DivanIcon.STOP)
                        if (s.prUrl != null) HqButton("PR در GitHub", { context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(s.prUrl))) }, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.SHARE)
                    }
                    FlowRow(Modifier.padding(top = 10.dp), horizontalArrangement = Arrangement.spacedBy(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp), itemVerticalAlignment = Alignment.CenterVertically) {
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            Avatar(s.driver.kind, size = 22.dp, state = if (s.state == "working") "working" else "idle")
                            Text(actorFa(s.driver), style = Divan.type.caption, color = c.textSecondary)
                        }
                        Fig("${modelLabel(s.model)} · ${s.effort}", style = Divan.type.figureSmall, color = c.textSecondary)
                        Text(when (s.runtime) { "subscription" -> "اشتراک Claude، روی هاب"; "managed" -> "Managed Agents"; else -> "میزبانی خودمان" }, style = Divan.type.caption, color = c.textSecondary)
                        Fig(usd(s.usage.usd) + (grant?.let { " / " + usd(it.budgetUsd, 0) } ?: ""), style = Divan.type.figureSmall, color = c.textSecondary)
                    }
                    grant?.let {
                        val pct = (s.usage.usd / it.budgetUsd * 100).coerceIn(0.0, 100.0)
                        MeterBar(pct, Modifier.padding(top = 10.dp), tone = budgetTone(pct), height = 4.dp)
                    }
                    if (s.brief.isNotBlank()) {
                        HorizontalDivider(Modifier.padding(vertical = 10.dp), color = c.lineDivider)
                        RichText(s.brief, style = Divan.type.small)
                    }
                }
            }
            item {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("رویدادها", style = Divan.type.caption, color = c.textMuted, modifier = Modifier.weight(1f))
                    if (s.open) Pill(if (feed.live) "زنده" else "در حال اتصال", if (feed.live) Tone.POS else Tone.WARN, live = feed.live)
                }
            }
            when {
                feed.error != null -> item { ErrorBlock(feed.error, null) }
                feed.events.isEmpty() -> item { Skeleton(Modifier.fillMaxWidth().height(160.dp), radius = 14.dp) }
                else -> items(feed.events, key = { it.seq }) { e ->
                    if (e.type == "approval_request") {
                        val id = e.str("approval_id").orEmpty()
                        ApprovalCard(e, results[id], busy = answer.busy && answering == id) { allow ->
                            answering = id
                            answer.run {
                                val token = if (allow) env.auth.stepUp(act, "workshop.approval", "${s.ref}/$id") else null
                                env.api.answerApproval(s.ref, id, allow, token)
                                env.cache.invalidate("workshop")
                            }
                        }
                    } else EventItem(e, s.driver.kind)
                }
            }
        }
        if (s.open) {
            Composer("راهنمایی یا تغییر مسیر؛ با متن یا ویس", { b, a ->
                try { env.api.steer(s.ref, b, a) } catch (e: ApiException) { toasts.error(e.messageFa); throw e }
            }, Modifier.padding(12.dp), draftKey = "steer:$ref")
        } else {
            Text("این جلسه بسته است؛ شاخه و تاریخچه‌اش میماند.", Modifier.fillMaxWidth().padding(12.dp).clip(RoundedCornerShape(14.dp)).background(c.tile).padding(14.dp), style = Divan.type.small, color = c.textMuted)
        }
    }

    if (confirm) AlertDialog(
        onDismissRequest = { confirm = false },
        containerColor = c.overlay,
        title = { Text("جلسه متوقف شود؟", style = Divan.type.h3) },
        text = { Text("کار همین لحظه می‌ایستد. شاخه‌ی ${s.branch ?: "—"} و تاریخچه میمانند و میشود بعداً از همان‌جا ادامه داد.", style = Divan.type.small, color = c.textSecondary) },
        confirmButton = {
            HqButton("متوقف کن", {
                stop.run { q.set(env.api.stopSession(s.ref)); env.cache.invalidate("workshop"); confirm = false }
            }, variant = BtnVariant.DANGER, icon = DivanIcon.STOP, loading = stop.busy)
        },
        dismissButton = { HqButton("نه", { confirm = false }, variant = BtnVariant.GHOST) },
    )
}
