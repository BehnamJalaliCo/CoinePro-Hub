package com.coinepro.hq.ui.v32

import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyListState
import androidx.compose.foundation.shape.CircleShape
import com.coinepro.hq.designsystem.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.Stable
import androidx.compose.runtime.derivedStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.LocalReducedMotion
import com.coinepro.hq.designsystem.generated.DivanIcon
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch

// ⟨0.17.0⟩ A chat opens at its newest word and stays there while the owner is there. The list is drawn bottom-up (`reverseLayout`):
// item 0 is a thin tail under the newest message, so a turn that comes in lands above the tail and is in view by itself, and the
// keyboard opening keeps the last message in sight. When the owner has scrolled up nothing moves under his finger: a small round «↓»
// shows how many lines came since and takes him to the end. His own word always takes him there.

/** The key of the chat's tail (item 0 of a `reverseLayout` list); keep it first in every state of the list. */
const val CHAT_TAIL = "tail"

/** Where the owner is in a bottom-up chat, and what came while he read further up. */
@Stable
class ChatFollow internal constructor(val list: LazyListState, private val scope: CoroutineScope, private val reduced: () -> Boolean) {
    /** Lines that came while the owner was reading further up. */
    var unseen by mutableIntStateOf(0)
        internal set

    /** The end of the chat is in view: its tail is. (Exactly the tail: a line that comes then lands above it, in view; once the tail has
     *  left the screen a line that comes would land out of sight, so «↓» shows and counts it.) */
    val atEnd: Boolean by derivedStateOf { list.firstVisibleItemIndex == 0 }

    /** To the newest line. */
    fun toEnd() {
        unseen = 0
        scope.launch { if (reduced()) list.scrollToItem(0) else list.animateScrollToItem(0) }
    }
}

/**
 * Follows a bottom-up chat of [count] lines whose newest is [newestKey]: a line that came while the owner was further up is counted for
 * the «↓»; a line of his own ([newestMine]) takes him to the end; reaching the end clears the count.
 */
@Composable
fun rememberChatFollow(list: LazyListState, count: Int, newestKey: Any?, newestMine: Boolean): ChatFollow {
    val scope = rememberCoroutineScope()
    val reduced by rememberUpdatedState(LocalReducedMotion.current)
    val f = remember(list) { ChatFollow(list, scope) { reduced } }
    val seen = remember(list) { intArrayOf(-1) }
    LaunchedEffect(count, newestKey) {
        val before = seen[0]
        seen[0] = count
        if (before < 0 || count <= before) return@LaunchedEffect
        when {
            newestMine -> f.toEnd()
            f.atEnd -> f.unseen = 0
            else -> f.unseen += count - before
        }
    }
    LaunchedEffect(f) { snapshotFlow { f.atEnd }.collect { if (it) f.unseen = 0 } }
    return f
}

/** The round «↓» over the chat's foot, while the owner is further up; with the count of lines that came since, in Persian digits. */
@Composable
fun BoxScope.JumpToEnd(f: ChatFollow, modifier: Modifier = Modifier) {
    androidx.compose.animation.AnimatedVisibility(
        !f.atEnd, modifier.align(Alignment.BottomEnd).padding(12.dp),
        enter = if (LocalReducedMotion.current) androidx.compose.animation.EnterTransition.None else fadeIn(),
        exit = if (LocalReducedMotion.current) androidx.compose.animation.ExitTransition.None else fadeOut(),
    ) { JumpButton(f.unseen, f::toEnd) }
}

/** The «↓» itself, drawn from its count only (so each state can be shown). */
@Composable
fun JumpButton(unseen: Int, onClick: () -> Unit, modifier: Modifier = Modifier) {
    val c = Divan.colors
    Box(modifier.size(48.dp)) {
        Box(
            Modifier.align(Alignment.BottomCenter).size(42.dp).clip(CircleShape).background(c.raised).border(1.dp, c.lineStrong, CircleShape)
                .clickable(role = Role.Button, onClickLabel = "برو به آخرین پیام", onClick = onClick)
                .semantics { contentDescription = if (unseen > 0) "${faCount(unseen)} پیام تازه؛ برو به آخرین پیام" else "برو به آخرین پیام" },
            contentAlignment = Alignment.Center,
        ) { DIcon(DivanIcon.CHEVRON, size = 22.dp, tint = c.textPrimary) }
        if (unseen > 0) Box(
            Modifier.align(Alignment.TopCenter).clip(CircleShape).background(c.goldFill).padding(horizontal = 6.dp),
            contentAlignment = Alignment.Center,
        ) {
            Text(faCount(minOf(unseen, 99)), style = Divan.type.micro.copy(fontSize = 11.sp, lineHeight = 16.sp, fontWeight = FontWeight.Bold), color = c.onGold)
        }
    }
}
