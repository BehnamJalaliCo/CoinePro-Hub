package com.coinepro.hq.ui.session

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import com.coinepro.hq.designsystem.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.EraseKind
import com.coinepro.hq.core.net.ErasePreview
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.eraseCountsFa
import com.coinepro.hq.core.net.gated
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.activity
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.v29.plain
import java.util.UUID

// Contract §37 ⟨1.19⟩: «پاک کردن برای همیشه». First what goes and what stays (the preview: nothing changes), then the owner's passkey on
// the ref, then the erase itself. Hiding (§35) stays for what he only wants out of sight; this one has no way back.

/** The caches an erase of [kind] leaves stale. */
fun erasedTags(kind: EraseKind): Array<String> = when (kind) {
    EraseKind.SESSION -> arrayOf("sessions", "office", "orders", "order-report", "work", "talk", "deliverables", "notifications", "decisions", "home")
    EraseKind.RECORD -> arrayOf("archive")
    EraseKind.OUTPUT -> arrayOf("deliverables", "order-report", "decisions", "work")
}

/** The preview as the owner reads it: the thing's title, what goes with it (counts in Persian digits), what stays. */
@Composable
fun ErasePreviewBlock(p: ErasePreview, kind: EraseKind, whyFa: String? = null) {
    val c = Divan.colors
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        if (p.titleFa.isNotBlank()) Text(plain(p.titleFa), style = Divan.type.bodyStrong, color = c.textPrimary)
        whyFa?.takeIf { it.isNotBlank() }?.let { Text(plain(it), style = Divan.type.small, color = c.textSecondary) }
        val goes = eraseCountsFa(p.counts)
        Column(
            Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.softNegative).padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            Text("برای همیشه پاک میشود", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.negative)
            Text(
                plain(if (goes.isBlank()) "همین ${kind.fa} و هرچه فقط به آن بسته است." else "همین ${kind.fa}، با $goes."),
                style = Divan.type.small, color = c.textPrimary,
            )
        }
        if (p.keepsFa.isNotEmpty()) Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            Text("میماند", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textMuted)
            for (k in p.keepsFa) Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.Top) {
                Box(Modifier.padding(top = 7.dp).size(6.dp).clip(CircleShape).background(c.positive))
                Text(plain(k), style = Divan.type.small, color = c.textSecondary, modifier = Modifier.weight(1f))
            }
        }
        Text("برگشتی ندارد؛ با اثر انگشت یا چهره تأیید میشود.", style = Divan.type.micro, color = c.textMuted)
    }
}

/**
 * The sheet of an erase: it reads the preview, then «پاک کن برای همیشه» asks for the passkey (🔏 [EraseKind.action] on [ref]) and erases;
 * «پاک شد» and [onErased] (the caller leaves the screen or drops the row). A hub before ⟨1.19⟩ says so, and the entries hide.
 */
@Composable
fun EraseSheet(kind: EraseKind, ref: String, onDismiss: () -> Unit, onErased: () -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val act = activity()
    val go = rememberAction()
    var preview by remember(kind, ref) { mutableStateOf<ErasePreview?>(null) }
    var failed by remember(kind, ref) { mutableStateOf<String?>(null) }
    var missing by remember(kind, ref) { mutableStateOf(false) }
    // One key per press, kept across a retry of the same press (a UUID: the hub takes nothing else).
    val key = remember(kind, ref) { UUID.randomUUID().toString() }
    LaunchedEffect(kind, ref) {
        try {
            val p = env.api.gated(HubFeature.ERASE) { erasePreview(kind, ref) }
            if (p == null) missing = true else preview = p
        } catch (e: ApiException) {
            failed = e.messageFa
        }
    }
    com.coinepro.hq.ui.v14.HqSheet(onDismiss, "پاک کردن برای همیشه", sub = ERASE_SUB) {
        EraseBody(kind, preview, missing, failed, go.busy, onDismiss) {
            go.run {
                env.api.erase(kind, ref, key) { a, t -> env.auth.stepUp(act, a, t) }
                env.cache.invalidate(*erasedTags(kind))
                toasts.ok("پاک شد.")
                onErased()
            }
        }
    }
}

const val ERASE_SUB = "پنهان کردن چیزی را پاک نمیکند؛ این یکی برای همیشه است."

/** The sheet's body as pure drawing (each state can be shown): reading, not served, refused, or the preview and the two choices. */
@Composable
fun EraseBody(kind: EraseKind, preview: ErasePreview?, missing: Boolean, failed: String?, busy: Boolean, onDismiss: () -> Unit, onErase: () -> Unit) {
    val c = Divan.colors
    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        when {
            missing -> Text("پاک کردن برای همیشه با به‌روزرسانی بعدی هاب میاید.", style = Divan.type.small, color = c.textSecondary)
            failed != null -> Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                DIcon(DivanIcon.URGENT, size = 18.dp, tint = c.negative)
                // The hub's own sentence; a hold's ref in it keeps its Latin order («LH-0003»).
                Text(com.coinepro.hq.designsystem.timesFig(failed), style = Divan.type.small, color = c.textPrimary, modifier = Modifier.weight(1f))
            }
            preview == null -> Skeleton(Modifier.fillMaxWidth().height(160.dp), radius = 12.dp)
            else -> {
                ErasePreviewBlock(preview, kind)
                HqButton("پاک کن برای همیشه", onErase, Modifier.fillMaxWidth(), variant = BtnVariant.DANGER, size = BtnSize.LG, icon = DivanIcon.SEAL, loading = busy)
            }
        }
        HqButton("نه، بماند", onDismiss, Modifier.fillMaxWidth(), variant = BtnVariant.TEXT)
    }
}
