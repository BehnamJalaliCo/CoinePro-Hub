package com.coinepro.hq.ui.control

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
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
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.format.jDateTime
import com.coinepro.hq.core.format.until
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.CompanyMark
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.Monogram
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Loadable
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.activity
import com.coinepro.hq.ui.companyOf
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.v14.BackupsCard

private data class Target(val scope: String, val name: String, val engaged: Boolean)

/** Kill switches (OPERATING_MODEL §1.12): engaging is instant, because speed matters; releasing needs the
 *  passkey. A switch the owner engaged is released only by the owner. */
@Composable
fun ControlScreen() {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val act = activity()
    val c = Divan.colors
    val companies = rememberCompanies()
    val q = rememberQuery("control", "control") { control() }
    val r = refresher(q)
    val action = rememberAction()
    var t by remember { mutableStateOf<Target?>(null) }
    var reason by rememberSaveable { mutableStateOf("") }

    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item { PageHeader("کنترل", eyebrow = "کلید توقف و توقف deploy") }
        item {
            Loadable(q, skeleton = { Skeleton(Modifier.fillMaxWidth().height(140.dp), radius = 16.dp) }) { s ->
                val on = s.holding.state == "engaged"
                HqCard(Modifier.fillMaxWidth(), tahrir = !on, color = if (on) c.softNegative else c.card) {
                    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                        Box(Modifier.size(52.dp).clip(CircleShape).background(c.tile), contentAlignment = Alignment.Center) { Monogram(26.dp) }
                        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                            Text("کلید توقف کل هلدینگ", style = Divan.type.h3)
                            Text(if (on) "روشن از ${ago(s.holding.changedAt)}: فقط کارهای اضطراری (P0) اجرا میشوند." else "خاموش؛ همه‌چیز عادی است.", style = Divan.type.small, color = c.textSecondary)
                            s.holding.reason?.let { Text("«$it»", style = Divan.type.caption, color = c.textMuted) }
                        }
                    }
                    HqButton(
                        if (on) "آزاد کن" else "توقف همه‌چیز",
                        { t = Target("holding", "کل هلدینگ", on) },
                        Modifier.fillMaxWidth().padding(top = 14.dp),
                        variant = if (on) BtnVariant.PRIMARY else BtnVariant.DANGER, icon = if (on) DivanIcon.RESUME else DivanIcon.PAUSE,
                    )
                }
            }
        }
        item { SectionTitle("شرکت‌ها", note = "مدیرعامل هر شرکت هم میتواند کلید شرکت خودش را بزند؛ کلیدی را که تو زده‌ای فقط خودت آزاد میکنی.") }
        val s = q.data
        if (s != null) items(s.companies, key = { it.scope }) { k ->
            val on = k.state == "engaged"
            val name = companyOf(companies, k.company).nameFa
            val freeze = s.deployFreezes.firstOrNull { it.company == k.company && (com.coinepro.hq.core.format.hoursUntil(it.until) ?: -1.0) > 0 }
            HqCard(Modifier.fillMaxWidth(), color = if (on) c.softNegative else c.card) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Box(Modifier.size(44.dp).clip(CircleShape).background(c.tile), contentAlignment = Alignment.Center) { CompanyMark(k.company, height = 18.dp, ink = c.textPrimary) }
                    Column(Modifier.weight(1f)) {
                        Text(name, style = Divan.type.bodyStrong)
                        Text(if (on) "متوقف از ${ago(k.changedAt)}" else "عادی", style = Divan.type.caption, color = c.textMuted)
                    }
                    if (on) Pill("متوقف", Tone.NEG, icon = DivanIcon.PAUSE) else Pill("فعال", Tone.POS, dot = true)
                }
                freeze?.let {
                    Row(Modifier.fillMaxWidth().padding(top = 12.dp).clip(RoundedCornerShape(12.dp)).background(c.softWarning).padding(12.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        DIcon(DivanIcon.PAUSE, size = 16.dp, tint = c.warning)
                        Text("توقف deploy تا ${jDateTime(it.until)} (${until(it.until)})، ${it.reason}", style = Divan.type.caption)
                    }
                }
                HqButton(
                    if (on) "آزاد کن (passkey)" else "توقف این شرکت",
                    { t = Target(k.scope, name, on) },
                    Modifier.fillMaxWidth().padding(top = 12.dp),
                    variant = if (on) BtnVariant.PRIMARY else BtnVariant.DANGER, size = BtnSize.SM, icon = if (on) DivanIcon.RESUME else DivanIcon.PAUSE,
                )
            }
        }
        item { BackupsCard() }
    }

    t?.let { target ->
        AlertDialog(
            onDismissRequest = { t = null },
            containerColor = c.overlay,
            title = { Text(if (target.engaged) "آزاد کردن ${target.name}" else "توقف ${target.name}", style = Divan.type.h3) },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Text(
                        if (target.engaged) "ایجنت‌ها دوباره کار میکنند. با اثر انگشت یا چهره تأیید میشود."
                        else "همه‌ی ایجنت‌های این دامنه فوراً از هر اقدام نوشتنی باز میمانند؛ فقط کارهای اضطراری (P0) ادامه پیدا میکنند.",
                        style = Divan.type.small, color = c.textSecondary,
                    )
                    HqTextField(reason, { reason = it }, "دلیل (برای دفتر Audit)", Modifier.fillMaxWidth())
                }
            },
            confirmButton = {
                HqButton(if (target.engaged) "آزاد کن" else "متوقف کن", {
                    action.run {
                        val token = if (target.engaged) env.auth.stepUp(act, "kill_switch.release", target.scope) else null
                        val out = env.api.killSwitch(target.scope, !target.engaged, reason.trim().ifBlank { if (target.engaged) "آزاد شد" else "توقف اضطراری" }, token)
                        q.set(out)
                        env.cache.invalidate("control", "companies")
                        if (target.engaged) toasts.ok("${target.name} دوباره کار میکند.") else toasts.info("${target.name} متوقف شد؛ ایجنت‌هایش هیچ اقدام نوشتنی نمیکنند.")
                        t = null
                        reason = ""
                    }
                }, variant = if (target.engaged) BtnVariant.PRIMARY else BtnVariant.DANGER, loading = action.busy)
            },
            dismissButton = { HqButton("انصراف", { t = null }, variant = BtnVariant.GHOST) },
        )
    }
}
