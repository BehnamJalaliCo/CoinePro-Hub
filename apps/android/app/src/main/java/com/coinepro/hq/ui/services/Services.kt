package com.coinepro.hq.ui.services

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.ui.draw.clip
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.HorizontalDivider
import com.coinepro.hq.designsystem.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.HubJob
import com.coinepro.hq.core.net.HubService
import com.coinepro.hq.core.net.HubServices
import com.coinepro.hq.core.net.gated
import com.coinepro.hq.core.net.hubPendingFa
import com.coinepro.hq.core.net.hubStateFa
import com.coinepro.hq.core.net.hubSwapFa
import com.coinepro.hq.core.net.hubToTurnOff
import com.coinepro.hq.core.net.mbFig
import com.coinepro.hq.designsystem.BarTone
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.HqSwitch
import com.coinepro.hq.designsystem.MeterBar
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.designsystem.timesFig
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.rememberQuery
import java.util.UUID
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeoutOrNull

// Contract §38.3 ⟨1.20⟩: «سرویس‌ها». The owner, 2026-11-06: «نمیشه که یبار توی آپ من بگم یبارم بیام به تو بگم یبار تو به سرور بگی».
// The free memory above, then each service of the hub: what it is for, on or off, its memory; a switch for each optional one. A switch
// is a job the hub's dispatcher runs within the memory budget; while it runs the row says «در حال …»; the answer comes back as a toast,
// or, when it does not fit, a sheet of what holds the memory with one tap to swap.

/** A switch the hub refused for memory: the service, the way it was turned, and the job's answer. */
data class Refused(val service: HubService, val on: Boolean, val job: HubJob)

@Composable
fun rememberHubServices() = rememberQuery("hub-services", "hub-services", maxAgeMs = 15_000) { gated(HubFeature.HUB_SERVICES) { hubServices() } }

@Composable
fun ServicesScreen() {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val scope = rememberCoroutineScope()
    val q = rememberHubServices()
    val r = refresher(q)
    val served = com.coinepro.hq.ui.v29.served(HubFeature.HUB_SERVICES)
    val pending = remember { mutableStateMapOf<String, Boolean>() }
    var refused by remember { mutableStateOf<Refused?>(null) }
    // The stream's `hub.job` wakes the job's poll at once; any other `hub.*` news reads the page again.
    val wakes = remember { MutableSharedFlow<String>(extraBufferCapacity = 16) }
    LaunchedEffect(env) {
        env.stream.events.collect { e ->
            if (e.type == "hub.job") e.ref?.let { wakes.tryEmit(it) }
            if (e.type.startsWith("hub.service")) q.refresh()
        }
    }

    suspend fun follow(first: HubJob): HubJob {
        var job = first
        for (wait in POLL_MS) {
            if (job.finished || job.ref.isBlank()) return job
            withTimeoutOrNull(wait) { wakes.first { it == job.ref } }
            job = env.api.hubJob(job.ref)
        }
        return job
    }

    fun toggle(s: HubService, on: Boolean, turnOff: List<String> = emptyList()) {
        if (s.key in pending) return
        pending[s.key] = on
        for (k in turnOff) pending[k] = false
        scope.launch {
            try {
                // One key per press: the hub takes only a UUID, and a retry of this press is this press.
                val job = follow(env.api.setHubService(s.key, on, UUID.randomUUID().toString(), turnOff))
                when (job.state) {
                    "done" -> toasts.ok(job.resultFa ?: if (on) "روشن شد." else "خاموش شد.")
                    "refused" -> refused = Refused(s, on, job)
                    "failed" -> toasts.error(job.resultFa ?: "نشد؛ کمی بعد دوباره بزن.")
                    else -> toasts.info("هاب هنوز روی آن کار میکند؛ نتیجه همین‌جا پیدا میشود.")
                }
            } catch (e: ApiException) {
                toasts.error(e.messageFa)
            } finally {
                pending.remove(s.key)
                for (k in turnOff) pending.remove(k)
                env.cache.invalidate("hub-services")
            }
        }
    }

    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item(key = "head") { PageHeader("سرویس‌ها", eyebrow = "بخش‌های هاب، روشن یا خاموش؛ هر تغییر با حافظه‌ی سرور سنجیده میشود") }
        val d = q.data
        when {
            d == null && q.error != null -> item(key = "error") { ErrorBlock(q.error, { q.refresh() }) }
            d == null && !served -> item(key = "none") {
                Empty("صفحه‌ی سرویس‌ها با به‌روزرسانی بعدی هاب میاید", icon = DivanIcon.SERVER, body = "تا آن موقع روشن و خاموش کردن بخش‌های هاب با مسئول عملیات هلدینگ است.")
            }
            d == null -> item(key = "skeleton") { Skeleton(Modifier.fillMaxWidth().height(320.dp), radius = 16.dp) }
            else -> item(key = "body") { ServicesBody(d, pending, ::toggle) }
        }
    }

    refused?.let { x ->
        com.coinepro.hq.ui.v14.HqSheet({ refused = null }, "جا نیست؛ این‌ها جا را گرفته‌اند", sub = "برای ${x.service.titleFa} حافظه‌ی سرور کم است.") {
            RefusedBody(x, q.data?.memory?.freeMb ?: 0.0, onDismiss = { refused = null }) { off ->
                // The sheet closes; the row says «در حال …» until the one job (off first, then on) answers.
                refused = null
                toggle(x.service, x.on, off)
            }
        }
    }
}

private val POLL_MS = listOf(1_500L, 2_000L, 3_000L, 4_000L, 5_000L, 8_000L, 10_000L, 15_000L, 20_000L, 30_000L, 30_000L, 30_000L)

/** The page as pure drawing: the memory, then the optional services with their switches, then the core ones read-only. */
@Composable
fun ServicesBody(d: HubServices, pending: Map<String, Boolean>, onToggle: (HubService, Boolean) -> Unit) {
    val c = Divan.colors
    val installed = d.memory != null
    Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
        MemoryCard(d)
        val (optional, core) = d.services.partition { it.optional }
        if (optional.isNotEmpty()) HqCard(Modifier.fillMaxWidth(), padding = PaddingValues(horizontal = 14.dp, vertical = 8.dp)) {
            SectionTitle("اختیاری", note = "هر کدام را لازم داری روشن کن؛ خاموش‌ها حافظه نمیگیرند", icon = DivanIcon.SETTINGS)
            optional.forEachIndexed { i, s ->
                if (i > 0) HorizontalDivider(color = c.lineDivider)
                ServiceRow(s, pending[s.key], enabled = installed) { on -> onToggle(s, on) }
            }
        }
        if (core.isNotEmpty()) HqCard(Modifier.fillMaxWidth(), padding = PaddingValues(horizontal = 14.dp, vertical = 8.dp)) {
            SectionTitle("هسته", note = "همیشه روشن؛ هاب بدون این‌ها کار نمیکند", icon = DivanIcon.LOCK)
            core.forEachIndexed { i, s ->
                if (i > 0) HorizontalDivider(color = c.lineDivider)
                ServiceRow(s, null, enabled = false) {}
            }
        }
    }
}

@Composable
private fun MemoryCard(d: HubServices) {
    val c = Divan.colors
    val m = d.memory
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("حافظه‌ی سرور", note = d.at?.takeIf { m != null && it.isNotBlank() }?.let { "به‌روز ${ago(it)}" }, icon = DivanIcon.SERVER)
        if (m == null) {
            Column(Modifier.padding(top = 8.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text("بخش سرور هنوز نصب نشده است", style = Divan.type.bodyStrong, color = c.textPrimary)
                Text("تا هاب اولین گزارش حافظه را بدهد، کلیدها خاموش میمانند.", style = Divan.type.caption, color = c.textMuted)
            }
            return@HqCard
        }
        val pct = if (m.budgetMb > 0) m.capsMb / m.budgetMb * 100 else 0.0
        Column(Modifier.padding(top = 10.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(
                buildAnnotatedString { append("آزاد "); fig(mbFig(m.freeMb), c.textPrimary, FontWeight.SemiBold); append(" از بودجه‌ی "); fig(mbFig(m.budgetMb)) },
                style = Divan.type.body, color = c.textSecondary,
            )
            MeterBar(pct, tone = when { pct >= 90 -> BarTone.NEG; pct >= 75 -> BarTone.WARN; else -> BarTone.SILVER }, height = 8.dp)
            Text(
                buildAnnotatedString { append("سرویس‌های روشن "); fig(mbFig(m.capsMb)); append(" گرفته‌اند؛ کل حافظه‌ی سرور "); fig(mbFig(m.totalMb)) },
                style = Divan.type.caption, color = c.textMuted,
            )
        }
    }
}

/** One service: its name and what it is for, its state (or «در حال …» while its switch runs), its memory, and its switch. */
@Composable
private fun ServiceRow(s: HubService, pendingOn: Boolean?, enabled: Boolean, onToggle: (Boolean) -> Unit) {
    val c = Divan.colors
    Row(Modifier.fillMaxWidth().padding(vertical = 10.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
            // A Latin name in the line («n8n»، «MCP») keeps its Latin letters and digits.
            Text(timesFig(s.titleFa.ifBlank { s.key }), style = Divan.type.bodyStrong, color = c.textPrimary)
            if (s.whatFa.isNotBlank()) Text(timesFig(s.whatFa), style = Divan.type.caption, color = c.textSecondary)
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                if (pendingOn != null) Pill(hubPendingFa(pendingOn), Tone.WARN, live = true)
                else Pill(hubStateFa(s.state), stateTone(s.state), dot = true, live = s.state == "starting")
                val used = s.memUsedMb
                Fig(if (used != null && s.state == "on") "${mbFig(used).removeSuffix(" MB")} / ${mbFig(s.memCapMb)}" else mbFig(s.memCapMb), style = Divan.type.figureSmall, color = c.textMuted)
            }
            s.noteFa?.takeIf { it.isNotBlank() }?.let { Text(it, style = Divan.type.micro, color = c.textMuted) }
        }
        if (s.canToggle) {
            val on = pendingOn ?: (s.state == "on" || s.state == "starting")
            HqSwitch(on, onToggle, s.titleFa.ifBlank { s.key }, enabled = enabled && pendingOn == null && s.state != "starting")
        } else if (!s.optional) DIcon(DivanIcon.LOCK, size = 16.dp, tint = c.textMuted)
    }
}

private fun stateTone(state: String): Tone = when (state) {
    "on" -> Tone.POS
    "starting" -> Tone.WARN
    "failed" -> Tone.NEG
    else -> Tone.SILVER
}

/** The refused sheet's body: what holds the memory (largest first) and the one tap that swaps. */
@Composable
fun RefusedBody(x: Refused, freeMb: Double, onDismiss: () -> Unit, onSwap: (List<String>) -> Unit) {
    val c = Divan.colors
    val off = hubToTurnOff(x.job.blocking, x.service.memCapMb, freeMb)
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        x.job.resultFa?.takeIf { it.isNotBlank() && it != "جا نیست؛ این‌ها جا را گرفته‌اند" }?.let { Text(it, style = Divan.type.small, color = c.textSecondary) }
        Text(
            buildAnnotatedString { append("${x.service.titleFa} "); fig(mbFig(x.service.memCapMb)); append(" لازم دارد و "); fig(mbFig(freeMb)); append(" آزاد است.") },
            style = Divan.type.small, color = c.textPrimary,
        )
        HqCard(Modifier.fillMaxWidth(), padding = PaddingValues(horizontal = 12.dp, vertical = 4.dp)) {
            x.job.blocking.sortedByDescending { it.memCapMb }.forEachIndexed { i, b ->
                if (i > 0) HorizontalDivider(color = c.lineDivider)
                Row(Modifier.fillMaxWidth().padding(vertical = 10.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text(timesFig(b.titleFa.ifBlank { b.key }), style = Divan.type.small, color = c.textPrimary, modifier = Modifier.weight(1f))
                    if (b in off) Pill("خاموش میشود", Tone.SILVER)
                    Fig(mbFig(b.memCapMb), style = Divan.type.figureSmall, color = c.textMuted)
                }
            }
        }
        // The one tap, its whole sentence on the button (it may take two lines).
        if (off.isNotEmpty() && x.on) {
            val label = hubSwapFa(off, x.service.titleFa.ifBlank { x.service.key })
            Row(
                Modifier.fillMaxWidth().heightIn(min = 48.dp).clip(RoundedCornerShape(10.dp)).background(c.goldFill)
                    .clickable(role = Role.Button, onClickLabel = label) { onSwap(off.map { it.key }) }.padding(horizontal = 16.dp, vertical = 10.dp),
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp, Alignment.CenterHorizontally),
            ) {
                DIcon(DivanIcon.RESUME, size = 18.dp, tint = c.onGold)
                Text(timesFig(label), style = Divan.type.bodyStrong, color = c.onGold, textAlign = TextAlign.Center, modifier = Modifier.weight(1f, fill = false))
            }
        }
        HqButton("فعلاً نه", onDismiss, Modifier.fillMaxWidth(), variant = BtnVariant.TEXT)
    }
}
