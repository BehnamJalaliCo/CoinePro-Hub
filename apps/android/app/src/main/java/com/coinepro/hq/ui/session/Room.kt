package com.coinepro.hq.ui.session

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.systemBarsPadding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import com.coinepro.hq.core.data.faceOf
import com.coinepro.hq.core.data.quietLine
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.IconBtn
import com.coinepro.hq.designsystem.Md
import com.coinepro.hq.designsystem.Text
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.designsystem.timesFig
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.look.FileViewer
import com.coinepro.hq.ui.look.FilesStrip
import com.coinepro.hq.ui.media.openFile

// Contract §58.1 ⟨1.36⟩ «میگه برو خروجی رو ببین من اصلا فضایی از صفحه ندارم که خروجی رو ببینم»: the question card's chip opens the session's
// newest output over the session itself, full screen; closing it is back to the same draft (the session never left the screen).

/**
 * The newest output, full screen over the session: its film (with sound) or its picture; a document alone opens in the phone's own
 * reader; written words (the output's text, with any files under it) on a page of their own. [onClose] once it is closed.
 */
@Composable
internal fun OutputFull(o: SessionOutput, onClose: () -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val context = LocalContext.current
    val face = faceOf(o.files)
    val words = o.d?.body?.trim()?.ifBlank { null } ?: o.d?.summary?.trim()?.ifBlank { null }
    when {
        face != null -> FileViewer(face, onClose = onClose)
        words == null && o.files.isNotEmpty() -> LaunchedEffect(o.ref) {
            try { openFile(env, context, o.files.first()) } catch (_: Exception) { toasts.error("فایل باز نشد.") }
            onClose()
        }
        else -> TextFull(o.titleFa, words, o, onClose)
    }
}

/** An output's words on the full screen: its title and close at the top, the text scrolling, its files under it. */
@Composable
internal fun TextFull(title: String, words: String?, o: SessionOutput?, onClose: () -> Unit) {
    val c = Divan.colors
    Dialog(onClose, DialogProperties(usePlatformDefaultWidth = false, decorFitsSystemWindows = false)) {
        Column(Modifier.fillMaxSize().background(c.page).systemBarsPadding().testTag("output-full")) {
            Row(Modifier.fillMaxWidth().padding(start = 16.dp, end = 4.dp, top = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                Text(timesFig(quietLine(title).ifBlank { "خروجی" }), style = Divan.type.h3, color = c.textPrimary, maxLines = 2, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
                IconBtn(DivanIcon.CLOSE, "بستن", onClose, tint = c.textSecondary)
            }
            Column(Modifier.weight(1f).fillMaxWidth().verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                if (words != null) Md(words, color = c.textPrimary)
                o?.files?.takeIf { it.isNotEmpty() }?.let { FilesStrip(it) }
            }
        }
    }
}
