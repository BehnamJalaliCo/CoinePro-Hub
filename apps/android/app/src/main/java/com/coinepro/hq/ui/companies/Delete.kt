package com.coinepro.hq.ui.companies

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalLayoutDirection
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.CompanyDelete
import com.coinepro.hq.core.data.DeleteOutcome
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.Company
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.Radius
import com.coinepro.hq.designsystem.Space
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.activity
import kotlinx.coroutines.launch

/**
 * «حذف شرکت» (a company made by mistake): what goes and what stays, the company's code typed exactly, then the passkey. The hub keeps
 * a company that has a history (work done, outputs, revenue: `409 company_has_history`) and the sheet offers to archive it instead
 * (`status: archived`, 🔏 `company.archive`), as it does while the hub has no delete at all (a server gap: 405).
 */
@Composable
fun DeleteContent(t: CoTarget, co: Company?, onDone: () -> Unit, onCancel: () -> Unit, typed0: String = "", outcome0: DeleteOutcome? = null) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val act = activity()
    val c = Divan.colors
    val scope = rememberCoroutineScope()
    var typed by rememberSaveable { mutableStateOf(typed0) }
    var outcome by rememberSaveable { mutableStateOf(outcome0) }
    var busy by rememberSaveable { mutableStateOf(false) }

    fun delete() {
        if (busy) return
        busy = true
        scope.launch {
            try {
                env.api.deleteCompany(t.code) { a, target -> env.auth.stepUp(act, a, target) }
                outcome = DeleteOutcome.DELETED
            } catch (e: ApiException) {
                outcome = CompanyDelete.outcome(e)
                if (outcome == DeleteOutcome.FAILED) toasts.error(e.messageFa)
            } finally {
                busy = false
            }
            if (outcome == DeleteOutcome.DELETED || outcome == DeleteOutcome.GONE) {
                env.cache.invalidate("companies", "control", "brands", "founding")
                toasts.ok("${t.nameFa} حذف شد.")
                onDone()
            }
        }
    }

    fun archive() {
        if (busy) return
        busy = true
        scope.launch {
            try {
                val fresh = env.api.company(t.code)
                env.api.patchCompany(fresh, archive = true) { a, target -> env.auth.stepUp(act, a, target) }
                env.cache.invalidate("companies", "control")
                toasts.ok("${t.nameFa} بایگانی شد؛ همه‌ی سوابقش میماند.")
                onDone()
            } catch (e: ApiException) {
                toasts.error(e.messageFa)
            } finally {
                busy = false
            }
        }
    }

    Column(verticalArrangement = Arrangement.spacedBy(Space.md)) {
        when (outcome) {
            DeleteOutcome.HAS_HISTORY, DeleteOutcome.NOT_SERVED -> {
                Column(
                    Modifier.fillMaxWidth().clip(RoundedCornerShape(Radius.tile)).background(c.softWarning).padding(Space.sm),
                    verticalArrangement = Arrangement.spacedBy(Space.xs),
                ) {
                    Text(
                        if (outcome == DeleteOutcome.HAS_HISTORY) "${t.nameFa} سابقه دارد و حذف نمیشود" else "هاب هنوز حذف شرکت را ندارد",
                        style = Divan.type.bodyStrong, color = c.textPrimary,
                    )
                    Text(
                        if (outcome == DeleteOutcome.HAS_HISTORY) "کاری انجام داده، خروجی یا درآمدی دارد؛ این‌ها در دفترها میمانند. به‌جای حذف، بایگانی‌اش کن: از گزارش‌ها، ستاره‌ها و نظارت بیرون میرود، در شرکت‌ها زیر «بایگانی‌شده» میاید و همه‌ی سوابقش سر جایش میماند."
                        else "تا هاب حذف را بیاورد، بایگانی کن: از گزارش‌ها، ستاره‌ها و نظارت بیرون میرود و در شرکت‌ها زیر «بایگانی‌شده» میاید؛ هر وقت حذف آمد، از همین‌جا پاکش کن.",
                        style = Divan.type.small, color = c.textSecondary,
                    )
                }
                HqButton("بایگانی شرکت با اثر انگشت", ::archive, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, size = BtnSize.LG, icon = DivanIcon.LOCK, loading = busy)
                HqButton("انصراف", onCancel, Modifier.fillMaxWidth(), variant = BtnVariant.GHOST)
                return@Column
            }
            else -> Unit
        }
        Text("${t.nameFa} برای همیشه پاک میشود. این کار برگشت ندارد.", style = Divan.type.body, color = c.textPrimary)
        Consequences(
            listOf(
                DivanIcon.DISMISS to "شرکت، دپارتمان‌ها، جایگاه‌های خالی، نشان و تنظیماتش پاک میشوند.",
                DivanIcon.MEMORY to "فقط شرکتی پاک میشود که هنوز کاری انجام نداده، خروجی و درآمدی ندارد؛ وگرنه بایگانی پیشنهاد میشود.",
                DivanIcon.SERVER to "سرور و ریپو، اگر ساخته شده باشند، دست نمیخورند؛ پاک کردن سرور فقط با خودت در کنسول هتزنر است.",
                DivanIcon.LOCK to "تأیید آخر با اثر انگشت یا چهره است و در دفتر Audit ثبت میشود.",
            ),
            c.negative,
        )
        co?.counts?.let { n ->
            Text("الان: ${n.employeesActive} کارمند فعال، ${n.workOpen} کار باز، ${n.decisionsPending} کارت منتظر.", style = Divan.type.caption, color = c.textMuted)
        }
        Text(buildAnnotatedString { append("برای تأیید، کد شرکت را بنویس: "); fig(t.code, c.textPrimary) }, style = Divan.type.small, color = c.textSecondary)
        CompositionLocalProvider(LocalLayoutDirection provides LayoutDirection.Ltr) {
            HqTextField(typed, { typed = it.uppercase().filter { ch -> ch.isLetterOrDigit() }.take(10) }, t.code, Modifier.fillMaxWidth(), maxLength = 10, figure = true)
        }
        if (typed.isNotEmpty() && !CompanyDelete.matches(typed, t.code)) Text("کد با ${t.code} یکی نیست.", style = Divan.type.caption, color = c.negative)
        Row(horizontalArrangement = Arrangement.spacedBy(Space.xs)) {
            HqButton("حذف برای همیشه", ::delete, Modifier.weight(1f), variant = BtnVariant.DANGER, icon = DivanIcon.DISMISS, enabled = CompanyDelete.canConfirm(typed, t.code, t.holding), loading = busy)
            HqButton("انصراف", onCancel, Modifier.weight(1f), variant = BtnVariant.GHOST)
        }
    }
}

/** The control room's last card: removing a company made by mistake. */
@Composable
internal fun DeleteCard(t: CoTarget, ui: ControlUi) {
    val c = Divan.colors
    HqCard(Modifier.fillMaxWidth()) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Space.sm)) {
            Box(Modifier.size(36.dp).clip(CircleShape).background(c.softNegative), contentAlignment = Alignment.Center) { DIcon(DivanIcon.DISMISS, size = 18.dp, tint = c.negative) }
            Column(Modifier.weight(1f)) {
                Text("حذف شرکت", style = Divan.type.bodyStrong.copy(fontWeight = FontWeight.SemiBold))
                Text("اگر اشتباهی ساخته شده؛ شرکتی که سابقه دارد فقط بایگانی میشود.", style = Divan.type.caption, color = c.textMuted)
            }
            HqButton("حذف", { ui.open(ControlSheet.Delete(t)) }, size = BtnSize.SM, variant = BtnVariant.GHOST, icon = DivanIcon.DISMISS)
        }
    }
}
