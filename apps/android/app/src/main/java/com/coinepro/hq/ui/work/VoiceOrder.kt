package com.coinepro.hq.ui.work

import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.media.clock
import com.coinepro.hq.core.net.Order
import com.coinepro.hq.core.net.OrderRoute
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.CompanyMark
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.RichText
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.media.VoiceProblem
import com.coinepro.hq.ui.media.VoiceResult
import com.coinepro.hq.ui.media.openAppSettings
import com.coinepro.hq.ui.media.Waveform
import com.coinepro.hq.ui.media.rememberVoiceInput
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery

private val KIND = mapOf(
    "work" to ("کار" to DivanIcon.TASK),
    "code" to ("کارگاه کد" to DivanIcon.CODE),
    "meeting" to ("جلسه" to DivanIcon.MEETING),
    "question" to ("پرسش" to DivanIcon.ADVISOR),
)

private fun routeOf(r: OrderRoute): String? = when {
    r.sessionRef != null -> "workshop/${r.sessionRef}"
    r.decisionRef != null -> "cartable/${r.decisionRef}"
    r.workRef != null -> "work/${r.workRef}"
    r.kind == "question" -> "advisor"
    else -> null
}

/** Where an order went: company, kind, who — and a way in. */
@Composable
private fun RouteChip(r: OrderRoute, onGo: (String) -> Unit) {
    val c = Divan.colors
    val employees = rememberQuery("employees:all", "employees", maxAgeMs = 60_000) { employees().items }
    val who = employees.data?.firstOrNull { it.code == r.to }?.titleFa ?: r.to
    val (fa, icon) = KIND[r.kind] ?: (r.kind to DivanIcon.TASK)
    val route = routeOf(r)
    Row(
        Modifier.clip(CircleShape).background(c.tile).then(if (route != null) Modifier.clickable(role = Role.Button) { onGo(route) } else Modifier).padding(horizontal = 10.dp, vertical = 5.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(5.dp),
    ) {
        CompanyMark(r.company, height = 12.dp, mono = true, ink = c.textSecondary)
        DIcon(icon, size = 14.dp, tint = c.textSecondary)
        Text("$fa ← $who", style = Divan.type.micro, color = c.textPrimary, maxLines = 1, overflow = TextOverflow.Ellipsis)
        (r.sessionRef ?: r.decisionRef ?: r.workRef)?.let { Fig(it, style = Divan.type.figureSmall, color = c.textMuted) }
    }
}

/**
 * The owner speaks an order; the hub routes it (contract §17.4): rules first, then the light model, then the advisor.
 * The phone's own recogniser (fa-IR) turns the voice into words as the owner speaks; the owner reads the exact text before it goes,
 * and sees where it went. [listen] starts listening as the sheet opens (the gold button, the microphone, the quick-settings tile);
 * [typed] opens it on the text (a long press on the gold button).
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun VoiceOrderSheet(onDismiss: () -> Unit, listen: Boolean = true, typed: Boolean = false) {
    val env = LocalEnv.current
    val nav = LocalNav.current
    val ctx = androidx.compose.ui.platform.LocalContext.current
    val c = Divan.colors
    val orders = rememberQuery("orders", "orders", maxAgeMs = 10_000) { orders().items }
    val action = rememberAction()
    var phase by rememberSaveable { mutableStateOf(if (typed) "review" else "ready") }
    var text by rememberSaveable { mutableStateOf("") }
    var voice by remember { mutableStateOf<VoiceResult?>(null) }
    var out by remember { mutableStateOf<Order?>(null) }
    val vh = rememberVoiceInput("order") { r -> text = if (text.isBlank()) r.text else "${text.trimEnd()} ${r.text}"; voice = r; phase = "review" }
    val v = vh.v
    val go = { route: String -> v.cancel(); onDismiss(); nav.go(route) }
    // The record button breathes while it listens (in the layer: no recomposition; still when animations are removed).
    val pulse = com.coinepro.hq.designsystem.rememberBreath(v.recording, periodMs = 1400)
    // Opened to speak: listening starts at once (after the microphone permission, the first time).
    LaunchedEffect(Unit) { if (listen && !typed) vh.start() }

    ModalBottomSheet(onDismissRequest = { v.cancel(); onDismiss() }, sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true), containerColor = c.overlay) {
        Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).imePadding().padding(horizontal = 16.dp).padding(bottom = 24.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Text(if (phase == "review" && voice == null) "فرمان تازه" else "فرمان صوتی", style = Divan.type.h2)
            Text("بگو یا بنویس چه میخواهی؛ خودشان میدانند کجا و به دست چه کسی انجام شود.", style = Divan.type.caption, color = c.textMuted)
            when (phase) {
                "ready" -> Column(Modifier.fillMaxWidth().padding(vertical = 8.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(14.dp)) {
                    Box(
                        Modifier.size(112.dp).graphicsLayer { val k = 1f + 0.12f * pulse.value; scaleX = k; scaleY = k }.clip(CircleShape).background(c.goldFill)
                            .clickable(enabled = !v.transcribing, role = Role.Button) { if (v.recording) v.finish() else vh.start() }
                            .semantics { contentDescription = if (v.recording) "تمام؛ به متن تبدیل کن" else "شروع گفتن فرمان" },
                        contentAlignment = Alignment.Center,
                    ) {
                        if (v.transcribing) CircularProgressIndicator(Modifier.size(36.dp), color = c.onGold, strokeWidth = 3.dp)
                        else DIcon(if (v.recording) DivanIcon.STOP else DivanIcon.MIC, size = 44.dp, tint = c.onGold)
                    }
                    when {
                        v.recording -> {
                            Text("میشنوم…", style = Divan.type.bodyStrong, color = c.goldInk)
                            Waveform(v.levels, Modifier.height(40.dp))
                            if (v.partial.isNotBlank()) Text(v.partial, style = Divan.type.body, color = c.textPrimary, textAlign = TextAlign.Center)
                            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                                Fig(clock(v.elapsed), style = Divan.type.figure, color = c.textSecondary)
                                Text("تمام", Modifier.clickable { v.finish() }.padding(6.dp), style = Divan.type.small, color = c.goldInk)
                                Text("لغو", Modifier.clickable { v.cancel() }.padding(6.dp), style = Divan.type.small, color = c.textMuted)
                            }
                            Text(if (v.engine == "hub") "صدا برای تبدیل به هاب میرود" else "تشخیص گفتار خود گوشی، فارسی", style = Divan.type.micro, color = c.textMuted)
                        }
                        v.transcribing -> {
                            Text("در حال تشخیص گفتار…", style = Divan.type.body, color = c.textSecondary)
                            if (v.partial.isNotBlank()) Text(v.partial, style = Divan.type.body, color = c.textPrimary, textAlign = TextAlign.Center)
                        }
                        v.unavailable != null -> {
                            VoiceProblem(v.unavailable.orEmpty(), v.settings, { openAppSettings(ctx) }, { v.dismiss(); phase = "review" })
                            HqButton("مینویسم", { v.dismiss(); phase = "review" }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, icon = DivanIcon.EDIT)
                        }
                        else -> {
                            Text("بزن و بگو؛ دوباره بزن تا تمام شود", style = Divan.type.bodyStrong, textAlign = TextAlign.Center)
                            Text("مثلاً «به مدیر فنی FX بگو کندی ثبت‌نام را تا فردا ظهر اصلاح کند». کار، کارگاه کد، جلسه یا پرسش از مشاور؛ مسیرش را هاب پیدا میکند.", style = Divan.type.small, color = c.textSecondary, textAlign = TextAlign.Center)
                            Text("به‌جایش مینویسم", Modifier.clickable { phase = "review" }.padding(6.dp), style = Divan.type.small, color = c.goldInk)
                        }
                    }
                }
                "review" -> Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text(if (voice != null) "متن آنچه گفتی؛ پیش از فرستادن بخوان و اگر لازم است اصلاح کن" else "فرمان", style = Divan.type.caption, color = c.textMuted)
                    HqTextField(text, { text = it }, "چه کاری؟", Modifier.fillMaxWidth(), singleLine = false, minLines = 5, maxLength = 4000)
                    if (v.recording || v.transcribing) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        if (v.recording) Waveform(v.levels.takeLast(16), Modifier.height(20.dp)) else CircularProgressIndicator(Modifier.size(14.dp), color = c.goldInk, strokeWidth = 2.dp)
                        Text(v.partial.ifBlank { if (v.recording) "میشنوم…" else "در حال تشخیص گفتار…" }, style = Divan.type.caption, color = c.textSecondary, maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
                        if (v.recording) HqButton("تمام", v::finish, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.STOP)
                    }
                    v.unavailable?.let { why -> VoiceProblem(why, v.settings, { openAppSettings(ctx) }, v::dismiss) }
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        voice?.let { r ->
                            DIcon(DivanIcon.MIC, size = 14.dp, tint = c.textSecondary)
                            if (r.fileId != null) {
                                Text("صدای اصلی", style = Divan.type.micro, color = c.textSecondary)
                                Fig(clock(r.seconds), style = Divan.type.figureSmall, color = c.textSecondary)
                                Text("با فرمان میماند", style = Divan.type.micro, color = c.textSecondary)
                            } else Text("از گفتار، با تشخیص خود گوشی", style = Divan.type.micro, color = c.textSecondary)
                        }
                        Box(Modifier.weight(1f))
                        if (!v.active) HqButton(if (text.isBlank()) "بگو" else "ادامه بده", { vh.start() }, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.MIC)
                    }
                    HqButton(
                        "بفرست", {
                            action.run {
                                out = env.api.order(text.trim(), if (voice != null) "voice" else "text", voice?.fileId)
                                phase = "sent"
                                env.cache.invalidate("orders", "work", "planner", "workshop", "decisions", "inbox")
                            }
                        },
                        Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, size = BtnSize.LG, icon = DivanIcon.SEND, enabled = text.trim().length >= 3 && !v.active, loading = action.busy,
                    )
                }
                else -> out?.let { o ->
                    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).background(c.tile).padding(14.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            DIcon(DivanIcon.SEAL, size = 20.dp, tint = c.goldInk, active = true)
                            RichText("فرمان ${o.ref} رسید", style = Divan.type.bodyStrong, color = c.textPrimary)
                        }
                        RichText(o.summaryFa, style = Divan.type.small)
                        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) { for (r in o.routes) RouteChip(r, go) }
                    }
                    HqButton("فرمان بعدی", { phase = "ready"; text = ""; voice = null; out = null; vh.start() }, Modifier.fillMaxWidth(), icon = DivanIcon.MIC)
                }
            }
            HorizontalDivider(color = c.lineDivider)
            Text("فرمان‌های اخیر", style = Divan.type.caption, color = c.textMuted)
            val list = orders.data
            when {
                list == null -> Skeleton(Modifier.fillMaxWidth().height(72.dp), radius = 12.dp)
                list.isEmpty() -> Text("هنوز فرمانی نداده‌ای.", style = Divan.type.caption, color = c.textMuted)
                else -> for (o in list.take(5)) {
                    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Row(verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            DIcon(if (o.source == "voice") DivanIcon.MIC else DivanIcon.EDIT, size = 14.dp, tint = c.textMuted, modifier = Modifier.padding(top = 3.dp))
                            RichText(o.text, Modifier.weight(1f), style = Divan.type.small, color = c.textPrimary, maxLines = 2)
                            Text(ago(o.createdAt), style = Divan.type.micro, color = c.textMuted)
                        }
                        FlowRow(Modifier.padding(start = 22.dp), horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) { for (r in o.routes) RouteChip(r, go) }
                    }
                }
            }
        }
    }
}
