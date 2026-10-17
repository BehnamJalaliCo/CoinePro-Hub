package com.coinepro.hq.ui.auth

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.widthIn
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
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.AppGraph
import com.coinepro.hq.core.auth.Passkeys
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.Monogram
import com.coinepro.hq.designsystem.Wordmark
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.activity
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery
import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.sin

/** The shamseh behind the sign-in (D1): fine gold rays from the centre, very faint. */
@Composable
private fun Shamseh(modifier: Modifier = Modifier) {
    val c = Divan.colors
    Canvas(modifier) {
        val o = Offset(size.width / 2, size.height * 0.34f)
        val r = size.maxDimension
        for (k in 0 until 48) {
            val a = (2 * PI * k / 48).toFloat()
            drawLine(c.lineHairline, o, Offset(o.x + r * cos(a), o.y + r * sin(a)), 1f)
        }
        drawCircle(c.lineTahrir, 120.dp.toPx(), o, style = androidx.compose.ui.graphics.drawscope.Stroke(1f))
        drawCircle(c.lineHairline, 168.dp.toPx(), o, style = androidx.compose.ui.graphics.drawscope.Stroke(1f))
    }
}

@Composable
private fun AuthFrame(content: @Composable () -> Unit) {
    Box(Modifier.fillMaxSize()) {
        Shamseh(Modifier.fillMaxSize())
        Column(
            Modifier.fillMaxSize().safeDrawingPadding().padding(24.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center,
        ) {
            Monogram(84.dp)
            Spacer(Modifier.height(18.dp))
            Wordmark(150.dp)
            Spacer(Modifier.height(6.dp))
            Text("ستاد کوینه‌پرو", style = Divan.type.h3, color = Divan.colors.textSecondary)
            Spacer(Modifier.height(32.dp))
            Column(Modifier.widthIn(max = 420.dp).fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(12.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                content()
            }
        }
    }
}

/** Sign-in (contract §2): a discoverable passkey, no password anywhere. */
@Composable
fun LoginScreen(graph: AppGraph) {
    val env = LocalEnv.current
    val act = activity()
    val action = rememberAction()
    val meta = rememberQuery("meta", maxAgeMs = 60_000) { meta() }
    var link by remember { mutableStateOf(false) }
    AuthFrame {
        if (meta.data?.loginConfigured == false) {
            HqCard(Modifier.fillMaxWidth(), color = Divan.colors.softWarning) {
                Text("ورود روی سرور هنوز فعال نیست (دامنه و HTTPS). بعد از راه‌اندازی دوباره امتحان کن.", style = Divan.type.small, color = Divan.colors.textPrimary)
            }
        }
        HqButton(
            "ورود با passkey", { action.run { env.auth.signIn(act) } },
            Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, size = BtnSize.LG, icon = DivanIcon.LOCK, loading = action.busy,
        )
        Text("با اثر انگشت یا چهره‌ی همین گوشی.", style = Divan.type.caption, color = Divan.colors.textMuted, textAlign = TextAlign.Center)
        HqButton("این گوشی را با لینک ثبت‌نام اضافه کن", { link = true }, Modifier.fillMaxWidth(), variant = BtnVariant.GHOST)
        if (graph.demoAvailable) {
            HqButton("نمایش آزمایشی (بدون سرور)", { graph.enterDemo() }, Modifier.fillMaxWidth(), variant = BtnVariant.TEXT, icon = DivanIcon.KHALVAT)
        }
    }
    if (link) EnrolLinkDialog(onDismiss = { link = false })
}

/** Paste the one-time link from `make owner-enroll` when it was not opened on this phone directly. */
@Composable
private fun EnrolLinkDialog(onDismiss: () -> Unit) {
    val env = LocalEnv.current
    val act = activity()
    val toasts = LocalToasts.current
    val action = rememberAction()
    var text by rememberSaveable { mutableStateOf("") }
    val token = Regex("#token=([A-Za-z0-9_\\-.~]{16,200})").find(text)?.groupValues?.get(1) ?: text.trim().takeIf { Regex("^[A-Za-z0-9_\\-.~]{16,200}$").matches(it) }
    AlertDialog(
        onDismissRequest = onDismiss,
        containerColor = Divan.colors.overlay,
        title = { Text("ثبت این گوشی", style = Divan.type.h3) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text("لینک یک‌بار مصرفی را که `make owner-enroll` در ترمینال خودت ساخت این‌جا بگذار. لینک ۱۵ دقیقه اعتبار دارد.", style = Divan.type.small, color = Divan.colors.textSecondary)
                HqTextField(text, { text = it }, "https://hq.coinepro.com/enroll#token=…", Modifier.fillMaxWidth(), figure = true)
            }
        },
        confirmButton = {
            HqButton("ثبت با passkey", {
                action.run { env.auth.enrol(act, token); toasts.ok("این گوشی ثبت شد."); onDismiss() }
            }, variant = BtnVariant.PRIMARY, enabled = token != null, loading = action.busy)
        },
        dismissButton = { HqButton("انصراف", onDismiss, variant = BtnVariant.GHOST) },
    )
}

/** Opened from the enrolment App Link: register a passkey for this phone, then sign in. */
@Composable
fun EnrolScreen(token: String, onDone: () -> Unit) {
    val env = LocalEnv.current
    val act = activity()
    val toasts = LocalToasts.current
    val action = rememberAction()
    AuthFrame {
        HqCard(Modifier.fillMaxWidth(), tahrir = true) {
            Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                DIcon(DivanIcon.LOCK, tint = Divan.colors.goldInk)
                Text("ثبت این گوشی برای ستاد", style = Divan.type.h3)
                Text("یک passkey روی همین گوشی ساخته میشود: «${Passkeys.deviceName()}». هیچ رمزی وجود ندارد؛ از این به بعد با اثر انگشت یا چهره وارد میشوی.", style = Divan.type.small, color = Divan.colors.textSecondary)
            }
        }
        HqButton(
            "ساخت passkey و ورود", {
                action.run { env.auth.enrol(act, token); toasts.ok("گوشی ثبت شد. خوش آمدی."); onDone() }
            },
            Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, size = BtnSize.LG, icon = DivanIcon.SEAL, loading = action.busy,
        )
        HqButton("انصراف", onDone, Modifier.fillMaxWidth(), variant = BtnVariant.GHOST)
    }
}
