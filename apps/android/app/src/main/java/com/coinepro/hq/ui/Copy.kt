package com.coinepro.hq.ui

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.selection.SelectionContainer
import com.coinepro.hq.designsystem.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import com.coinepro.hq.designsystem.Divan

// The owner, 2026-11-06: «نمیتونم متن خروجی سشن رو کپی کنم، هرچی دستم رو روی متن نگه میدارم کپی نمیشه». Every text an agent writes for
// him, and his own words, can be selected with a long press (the phone's own handles and «کپی»), and a turn or a message is copied whole
// with one «کپی».

/** Puts [text] on the phone's clipboard; false when the phone refused. */
fun copyText(context: Context, text: String, label: String = "CoinePro HQ"): Boolean = runCatching {
    (context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager).setPrimaryClip(ClipData.newPlainText(label, text))
}.isSuccess

/** Copies a text and says so in one short line («کپی شد»). */
@Composable
fun rememberCopy(): (String) -> Unit {
    val context = LocalContext.current
    val toasts = LocalToasts.current
    return { text ->
        if (text.isNotBlank()) {
            if (copyText(context, text.trim())) toasts.ok("کپی شد.") else toasts.error("کپی نشد؛ دوباره بزن.")
        }
    }
}

/** «کپی» under a turn or a message: the whole of [text] (plain words, not markdown) to the clipboard. */
@Composable
fun CopyAction(text: String, modifier: Modifier = Modifier, color: Color = Divan.colors.silverInk) {
    val copy = rememberCopy()
    Text(
        "کپی",
        modifier.clip(CircleShape).clickable(role = Role.Button, onClickLabel = "کپی کل متن") { copy(text) }.padding(horizontal = 6.dp, vertical = 2.dp),
        style = Divan.type.micro, color = color,
    )
}

/** Text the owner may select with a long press and copy with the phone's own handles. Nothing it draws changes. */
@Composable
fun Selectable(content: @Composable () -> Unit) = SelectionContainer(content = content)
