package com.coinepro.hq.ui.v32

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Text
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
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.conversationTitle
import com.coinepro.hq.core.data.faceOrder
import com.coinepro.hq.core.data.personaIdTitle
import com.coinepro.hq.core.data.TALK_MODE_FA
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.net.TalkConversation
import com.coinepro.hq.designsystem.Badge
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.itemMotion
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v29.plain
import com.coinepro.hq.ui.v29.served
import com.coinepro.hq.core.net.HubFeature

// Contract §32.8: every conversation is kept for good; this is the list, with a search through all of them (`GET /talk/conversations?q`).

@Composable
fun ConversationsScreen(q0: String = "") {
    val nav = LocalNav.current
    val c = Divan.colors
    var text by rememberSaveable { mutableStateOf(q0) }
    var query by remember { mutableStateOf(q0.trim()) }
    LaunchedEffect(text) { kotlinx.coroutines.delay(300); query = text.trim() }
    val list = rememberQuery("talk-conversations:$query", "talk", maxAgeMs = 15_000) { talkConversations(q = query) }
    val personas = rememberQuery("talk-personas", "talk", maxAgeMs = 60_000) { talkPersonas() }
    val r = refresher(list)
    val has = served(HubFeature.TALK)
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item { PageHeader("گفتگوهای من", eyebrow = "هر گفتگو برای همیشه میماند؛ در همه‌شان جست‌وجو کن") }
        item { HqTextField(text, { text = it }, "جست‌وجو در همه‌ی گفتگوها", Modifier.fillMaxWidth(), maxLength = 200) }
        item { HqButton("گفتگوی تازه با منشی", { nav.go("talk") }, Modifier.fillMaxWidth(), variant = BtnVariant.SILVER, size = BtnSize.MD, icon = DivanIcon.ADD) }
        val rows = list.data
        when {
            !has -> item { Empty("گفتگو با به‌روزرسانی بعدی هاب میاید", icon = DivanIcon.MESSAGES) }
            rows == null && list.error != null -> item { ErrorBlock(list.error, { list.refresh() }) }
            rows == null -> items(4) { Skeleton(Modifier.fillMaxWidth().height(64.dp), radius = 14.dp) }
            rows.isEmpty() -> item {
                if (query.isNotBlank()) Text("در گفتگوها پیدا نشد.", style = Divan.type.caption, color = c.textMuted)
                else Empty("هنوز گفتگویی نیست", icon = DivanIcon.MESSAGES, body = "دکمه‌ی گفتگو را بزن و با منشی هلدینگ حرف بزن.")
            }
            else -> item(key = "rows") {
                Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(c.card)) {
                    rows.forEachIndexed { i, cv ->
                        if (i > 0) HorizontalDivider(color = c.lineDivider)
                        ConversationRow(cv, personas.data.orEmpty()) { nav.go(cv.orderRef?.takeIf { it.isNotBlank() }?.let { "session/$it" } ?: "talk/${cv.ref}") }
                    }
                }
            }
        }
    }
}

@Composable
fun ConversationRow(cv: TalkConversation, personas: List<com.coinepro.hq.core.net.TalkPersona>, onOpen: () -> Unit) {
    val c = Divan.colors
    val who = faceOrder(personas, cv.presentIds + cv.persona).firstOrNull { it.id == cv.persona }
    Row(
        Modifier.fillMaxWidth().clickable(role = Role.Button, onClick = onOpen).padding(14.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        if (who != null) PersonaFace(who, size = 34.dp) else Box(Modifier.height(46.dp))
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(plain(conversationTitle(cv.titleFa, personaIdTitle(cv.persona, personas))), style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary, maxLines = 1, overflow = TextOverflow.Ellipsis)
            cv.summaryFa?.takeIf { it.isNotBlank() }?.let { Text(plain(it), style = Divan.type.micro, color = c.textMuted, maxLines = 2, overflow = TextOverflow.Ellipsis) }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                Text(TALK_MODE_FA[cv.mode] ?: cv.mode, style = Divan.type.micro, color = c.textMuted)
                Text(ago(cv.lastTurnAt ?: cv.startedAt), style = Divan.type.micro, color = c.textMuted)
                Fig(cv.ref, style = Divan.type.figureSmall, color = c.textMuted)
            }
        }
        if (cv.openCards > 0) Badge(cv.openCards)
    }
}
