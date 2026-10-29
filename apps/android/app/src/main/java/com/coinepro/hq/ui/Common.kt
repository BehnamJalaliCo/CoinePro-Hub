package com.coinepro.hq.ui

import android.app.Activity
import androidx.activity.compose.LocalActivity
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Text
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.Stable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.coinepro.hq.core.Env
import com.coinepro.hq.core.data.Query
import com.coinepro.hq.core.data.QueryState
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.Company
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

val LocalEnv = staticCompositionLocalOf<Env> { error("no Env") }
val LocalToasts = staticCompositionLocalOf<Toasts> { error("no Toasts") }
val LocalNav = staticCompositionLocalOf<Nav> { error("no Nav") }

/** Navigation as the screens need it: go to a route, go back. */
interface Nav {
    fun go(route: String)
    fun back()
}

// ------------------------------------------------------------- queries --
@Stable
class QueryHandle<T>(val state: QueryState<T>, private val q: Query<T>) {
    val data: T? get() = state.data
    val error: ApiException? get() = state.error
    val loading: Boolean get() = state.loading && state.data == null
    fun refresh() = q.refresh()
    fun set(v: T) = q.set(v)
}

/** A cached query: shared across screens by [key], refreshed by [tags] (stream events, mutations) and when
 *  older than [maxAgeMs] on first show. The key must encode every parameter of [fetch]. */
@Composable
fun <T> rememberQuery(key: String, vararg tags: String, maxAgeMs: Long = 20_000, fetch: suspend Api.() -> T): QueryHandle<T> {
    val env = LocalEnv.current
    val q = remember(env, key) { env.cache.get(key, tags.toSet()) { env.api.fetch() } }
    val s by q.state.collectAsStateWithLifecycle()
    LaunchedEffect(q) { q.ensureFresh(maxAgeMs) }
    return QueryHandle(s, q)
}

/** Error with nothing cached → error block; nothing yet → skeleton; otherwise the content (stale data stays
 *  on screen while refreshing or after a failed refresh). */
@Composable
fun <T> Loadable(h: QueryHandle<T>, skeleton: @Composable () -> Unit = { Skeleton(Modifier.fillMaxWidth().height(96.dp), radius = 14.dp) }, content: @Composable (T) -> Unit) {
    val d = h.data
    when {
        d != null -> content(d)
        h.error != null -> ErrorBlock(h.error, onRetry = { h.refresh() })
        else -> skeleton()
    }
}

@Composable
fun rememberCompanies(): List<Company> = rememberQuery("companies", "companies", maxAgeMs = 60_000) { companies() }.data.orEmpty()

data class CoInfo(val code: String, val nameFa: String, val nameEn: String, val holding: Boolean, val colorIndex: Int?)

/** Name and kind of a company code from the list the API returns (companies are data, never a fixed set). */
fun companyOf(list: List<Company>, code: String?): CoInfo {
    val c = list.firstOrNull { it.code == code }
    return CoInfo(code.orEmpty(), c?.nameFa ?: code.orEmpty(), c?.nameEn ?: code.orEmpty(), c?.kind == "holding", c?.colorIndex)
}

// ------------------------------------------------------------- actions --
/** Runs one owner action: busy flag, haptic tick on success, Persian error toast on failure. */
@Stable
class ActionRunner(private val scope: CoroutineScope, private val toasts: Toasts, private val haptic: () -> Unit) {
    var busy by mutableStateOf(false)
        private set

    fun run(onError: ((ApiException) -> Unit)? = null, block: suspend () -> Unit) {
        if (busy) return
        busy = true
        scope.launch {
            try {
                block()
                haptic()
            } catch (e: ApiException) {
                onError?.invoke(e) ?: toasts.error(e.messageFa)
            } finally {
                busy = false
            }
        }
    }
}

@Composable
fun rememberAction(): ActionRunner {
    val scope = rememberCoroutineScope()
    val toasts = LocalToasts.current
    val h = LocalHapticFeedback.current
    return remember(scope, toasts) { ActionRunner(scope, toasts) { h.performHapticFeedback(androidx.compose.ui.hapticfeedback.HapticFeedbackType.Confirm) } }
}

@Composable
fun activity(): Activity = requireNotNull(LocalActivity.current) { "no Activity" }

// --------------------------------------------------------------- toasts --
enum class ToastTone { OK, INFO, ERROR }
/** One toast; [action] is a short label and what it opens (an order's page, its output). */
data class Toast(val id: Long, val tone: ToastTone, val text: String, val action: Pair<String, () -> Unit>? = null)

/** Toasts (D1 feedback): one line, tone icon + words, auto-dismissed; one with an action stays a little longer. */
@Stable
class Toasts {
    val items = mutableStateListOf<Toast>()
    private var seq = 0L
    fun ok(text: String, action: String? = null, onAction: (() -> Unit)? = null) = push(ToastTone.OK, text, action, onAction)
    fun info(text: String, action: String? = null, onAction: (() -> Unit)? = null) = push(ToastTone.INFO, text, action, onAction)
    fun error(text: String, action: String? = null, onAction: (() -> Unit)? = null) = push(ToastTone.ERROR, text, action, onAction)
    private fun push(tone: ToastTone, text: String, action: String?, onAction: (() -> Unit)?) {
        items.add(Toast(++seq, tone, text, if (action != null && onAction != null) action to onAction else null))
        // «خطاخوان»: what the owner was told goes into the breadcrumbs (an error's words help trace it).
        if (tone == ToastTone.ERROR) com.coinepro.hq.core.diag.Diag.crumb("toast error: ${text.take(48)}")
        while (items.size > 3) items.removeAt(0)
    }
    fun dismiss(id: Long) = items.removeAll { it.id == id }
}

@Composable
fun BoxScope.ToastHost(toasts: Toasts, modifier: Modifier = Modifier) {
    val c = Divan.colors
    Column(modifier.align(Alignment.BottomCenter).padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        for (t in toasts.items) {
            LaunchedEffect(t.id) { delay(if (t.action != null) 7_000 else if (t.tone == ToastTone.ERROR) 5_000 else 3_200); toasts.dismiss(t.id) }
            var shown by remember(t.id) { mutableStateOf(false) }
            LaunchedEffect(t.id) { shown = true }
            val reduced = com.coinepro.hq.designsystem.LocalReducedMotion.current
            AnimatedVisibility(
                shown,
                enter = if (reduced) androidx.compose.animation.EnterTransition.None else fadeIn(com.coinepro.hq.designsystem.Motion.emphasised()) + slideInVertically(com.coinepro.hq.designsystem.Motion.emphasised()) { it / 2 },
                exit = if (reduced) androidx.compose.animation.ExitTransition.None else fadeOut(com.coinepro.hq.designsystem.Motion.exit()) + slideOutVertically(com.coinepro.hq.designsystem.Motion.exit()) { it / 2 },
            ) {
                val (icon, tint) = when (t.tone) {
                    ToastTone.OK -> DivanIcon.SEAL to c.positive
                    ToastTone.INFO -> DivanIcon.INFO to c.lapis
                    ToastTone.ERROR -> DivanIcon.URGENT to c.negative
                }
                Row(
                    Modifier.widthIn(max = 520.dp).fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(c.raised).padding(horizontal = 14.dp, vertical = 12.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(10.dp),
                ) {
                    DIcon(icon, size = 20.dp, tint = tint)
                    Text(latinRefs(t.text), style = Divan.type.small, color = c.textPrimary, modifier = Modifier.weight(1f))
                    t.action?.let { (label, go) ->
                        com.coinepro.hq.designsystem.HqButton(label, { toasts.dismiss(t.id); go() }, variant = com.coinepro.hq.designsystem.BtnVariant.TEXT, size = com.coinepro.hq.designsystem.BtnSize.SM)
                    }
                }
            }
        }
    }
}

private val REF_IN_TEXT = Regex("\\b[A-Z]{1,3}-\\d{2,8}\\b")

/** A sentence with refs in it ("فرمان W-000210 رفت"): each ref set Latin, so it reads as the code it is. */
fun latinRefs(text: String): androidx.compose.ui.text.AnnotatedString = androidx.compose.ui.text.buildAnnotatedString {
    var last = 0
    for (m in REF_IN_TEXT.findAll(text)) {
        append(text.substring(last, m.range.first))
        fig(m.value)
        last = m.range.last + 1
    }
    append(text.substring(last))
}

// --------------------------------------------------------------- screen --
/** A scrolling page with pull-to-refresh: 16dp gutters, 16dp between sections. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun Page(onRefresh: (() -> Unit)? = null, refreshing: Boolean = false, content: LazyListScope.() -> Unit) {
    val list = rememberLazyListState()
    val body: @Composable () -> Unit = {
        LazyColumn(
            Modifier.fillMaxSize(),
            state = list,
            contentPadding = PaddingValues(start = 16.dp, end = 16.dp, top = 12.dp, bottom = 32.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
            content = content,
        )
    }
    if (onRefresh == null) Box(Modifier.fillMaxSize()) { body() }
    else PullToRefreshBox(isRefreshing = refreshing, onRefresh = onRefresh, modifier = Modifier.fillMaxSize()) { body() }
}

/** A refresh trigger for several queries at once. */
class Refresher(private val all: List<QueryHandle<*>>) {
    val refreshing: Boolean get() = all.any { it.state.refreshing }
    fun refresh() = all.forEach { it.refresh() }
}

@Composable
fun refresher(vararg q: QueryHandle<*>): Refresher = Refresher(q.toList())

/** A list item that fades in when it arrives, slides to its new place when the list reorders, and fades out when it leaves
 *  (Divan motion: medium in, short out); nothing moves when animations are removed. */
@Composable
fun androidx.compose.foundation.lazy.LazyItemScope.itemMotion(): Modifier =
    if (com.coinepro.hq.designsystem.LocalReducedMotion.current) Modifier
    else Modifier.animateItem(
        fadeInSpec = androidx.compose.animation.core.tween(com.coinepro.hq.designsystem.Motion.MEDIUM, easing = com.coinepro.hq.designsystem.Motion.Standard),
        placementSpec = androidx.compose.animation.core.tween(com.coinepro.hq.designsystem.Motion.MEDIUM, easing = com.coinepro.hq.designsystem.Motion.Standard),
        fadeOutSpec = androidx.compose.animation.core.tween(com.coinepro.hq.designsystem.Motion.SHORT, easing = com.coinepro.hq.designsystem.Motion.Exit),
    )
