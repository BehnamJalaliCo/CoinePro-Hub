package com.coinepro.hq.ui.support

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
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
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.format.jDateTime
import com.coinepro.hq.core.format.jTime
import com.coinepro.hq.core.net.Conversation
import com.coinepro.hq.core.net.SupportMessage
import com.coinepro.hq.core.net.faError
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.CompanyMark
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.Fig
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.HqSwitch
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.companyOf
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v14.LabelPill
import com.coinepro.hq.ui.v14.Tag
import com.coinepro.hq.ui.v16.AUTHOR_FA
import com.coinepro.hq.ui.v16.CHANNEL_FA
import com.coinepro.hq.ui.v16.CHANNEL_STATE
import com.coinepro.hq.ui.v16.CONV_STATE
import com.coinepro.hq.ui.v16.Fact
import com.coinepro.hq.ui.v16.FactRows
import com.coinepro.hq.ui.v16.GuardReasons
import com.coinepro.hq.ui.v16.HANDOFF_FA
import com.coinepro.hq.ui.v16.MSG_STATUS
import com.coinepro.hq.ui.v16.Masked
import com.coinepro.hq.ui.v16.ProseTag
import com.coinepro.hq.ui.v16.Notice
import com.coinepro.hq.ui.v16.go
import java.util.Locale
import java.util.UUID

/** What the owner is writing and the Idempotency-Key of that exact text: a retry of the same text never sends twice, an edited
 *  text is a new send. */
private data class Draft(val text: String = "", val key: String = "") {
    fun edit(t: String) = Draft(t, UUID.randomUUID().toString())
}

/** One conversation (§19.3): messages oldest first, masked; the owner's reply goes through the outbound guard like everything
 *  else, and teaching turns the right answer into a knowledge proposal for the next customer. */
@Composable
fun ConversationScreen(ref: String) {
    val env = LocalEnv.current
    val nav = LocalNav.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val companies = rememberCompanies()
    val q = rememberQuery("support:conversation:$ref", "support", maxAgeMs = 15_000) { conversation(ref) }
    val cv = q.data
    val channels = cv?.company?.let { co -> rememberQuery("support:channels:$co", "support") { supportChannels(co) } }
    val r = refresher(*listOfNotNull(q, channels).toTypedArray())
    val replyAction = rememberAction()
    val teachAction = rememberAction()
    val closeAction = rememberAction()
    var reply by remember(ref) { mutableStateOf(Draft()) }
    var reasons by remember(ref) { mutableStateOf(emptyList<String>()) }
    var replyErr by remember(ref) { mutableStateOf<String?>(null) }
    var teach by remember(ref) { mutableStateOf(Draft()) }
    var from by remember(ref) { mutableStateOf<SupportMessage?>(null) }
    var general by rememberSaveable { mutableStateOf(true) }
    var teachReasons by remember(ref) { mutableStateOf(emptyList<String>()) }

    fun send(text: String, key: String) {
        reasons = emptyList(); replyErr = null
        replyAction.go(toasts, onError = { e -> if (e.blockedReasons.isNotEmpty()) reasons = e.blockedReasons else replyErr = faError(e); true }) {
            env.api.reply(ref, text.trim(), key)
            reply = Draft()
            env.cache.invalidate("support")
            toasts.ok("از نگهبان گذشت و فرستاده شد.")
        }
    }
    fun doTeach() {
        teachReasons = emptyList()
        val key = teach.key.ifEmpty { UUID.randomUUID().toString() }
        teachAction.go(toasts, onError = { e -> if (e.blockedReasons.isNotEmpty()) { teachReasons = e.blockedReasons; true } else false }) {
            val out = env.api.teach(ref, from?.id, teach.text.trim(), general, key)
            teach = Draft(); from = null
            env.cache.invalidate("support")
            toasts.ok((if (out.message != null) "جوابت فرستاده شد و " else "جوابی فرستاده نشد (کانال روشن نیست یا گفت‌وگو منتظر نبود)؛ ") + "مقاله‌ی پیشنهادی ${out.article.ref} ساخته شد تا تأییدش کنی.")
        }
    }

    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        when {
            cv == null && q.error != null -> item { ErrorBlock(q.error, { q.refresh() }) }
            cv == null -> {
                item { Skeleton(Modifier.fillMaxWidth().height(72.dp), radius = 14.dp) }
                item { Skeleton(Modifier.fillMaxWidth().height(360.dp), radius = 16.dp) }
            }
            else -> {
                val ch = channels?.data?.firstOrNull { it.kind == cv.channel }
                val live = ch?.state == "live"
                item { Header(cv, companyOf(companies, cv.company).nameFa, closeAction.busy) {
                    closeAction.go(toasts) {
                        env.api.closeConversation(ref)
                        env.cache.invalidate("support")
                        toasts.info("بسته شد؛ قاعده‌ی رضایت (اگر فعال باشد) سراغ مشتری میرود.")
                    }
                } }
                if (cv.handoff?.reason == "security" && cv.state == "waiting_owner") item {
                    Notice(DivanIcon.URGENT, c.softNegative, c.negative) {
                        Text("گزارش امنیتی (مثل جعل هویت): مشتری جمله‌ی ایمنی را گرفته؛ رمز یا عبارتی که فرستاده ماسک شده و به هیچ مدلی نرسیده. جواب تو هم از نگهبان رد میشود.", style = Divan.type.small, color = c.textPrimary)
                    }
                }
                if (cv.mystery) item {
                    Notice(DivanIcon.OVERSEER, c.softLearning, c.learning) {
                        Text(buildAnnotatedString { append("گفت‌وگوی مشتری ناشناس ناظر ("); fig("PR-043"); append("): کل مسیر را رفته ولی هرگز به تلگرام یا Chatwoot نرسیده و در هیچ آماری نیست.") }, style = Divan.type.small, color = c.textPrimary)
                    }
                }
                item {
                    HqCard(Modifier.fillMaxWidth()) {
                        SectionTitle("پیام‌ها", note = "قدیمی‌ترین بالا؛ رمز، کارت و عبارت بازیابی پیش از ذخیره ماسک میشوند")
                        Column(Modifier.padding(top = 14.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                            for (m in cv.messages) Bubble(
                                m,
                                onSend = { send(it.body, UUID.randomUUID().toString()) },
                                onEdit = { reply = reply.edit(it.body) },
                                onTeach = { from = it; teach = teach.edit(it.body) },
                            )
                        }
                        HorizontalDivider(Modifier.padding(vertical = 16.dp), color = c.lineDivider)
                        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                            Text("جواب تو", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
                            if (!live) Text(
                                "کانال ${CHANNEL_FA[cv.channel] ?: cv.channel} ${CHANNEL_STATE[ch?.state]?.fa ?: "روشن نیست"} است؛ جواب مستقیم فرستاده نمیشود. «آموزش» هنوز مقاله‌ی پیشنهادی میسازد.",
                                style = Divan.type.caption, color = c.textSecondary, modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(c.tile).padding(10.dp),
                            )
                            val closed = cv.state == "closed"
                            HqTextField(reply.text, { reply = reply.edit(it) }, if (closed) "گفت‌وگو بسته است." else "از نگهبان خروجی رد میشود؛ لینک فقط از لینک‌های تأییدشده", Modifier.fillMaxWidth(), singleLine = false, minLines = 4, maxLength = 4000)
                            GuardReasons(reasons)
                            replyErr?.let { Text(it, style = Divan.type.caption, color = c.negative) }
                            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                                HqButton(if (reasons.isNotEmpty()) "دوباره بفرست" else "بفرست", { send(reply.text, reply.key.ifEmpty { UUID.randomUUID().toString() }) },
                                    variant = BtnVariant.PRIMARY, icon = DivanIcon.SEND, enabled = reply.text.isNotBlank() && !closed && live, loading = replyAction.busy)
                                Text("بعد از هر اصلاح، نگهبان دوباره میسنجد.", style = Divan.type.micro, color = c.textMuted, modifier = Modifier.weight(1f))
                            }
                        }
                    }
                }
                item {
                    HqCard(Modifier.fillMaxWidth()) {
                        SectionTitle("آموزش", note = "جواب درست را بنویس؛ فرستاده میشود (اگر منتظر توست) و مقاله‌ی پیشنهادی میشود")
                        Column(Modifier.padding(top = 12.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                            from?.let { m ->
                                Row(
                                    Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(c.tile).padding(horizontal = 12.dp, vertical = 6.dp),
                                    verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
                                ) {
                                    Text(buildAnnotatedString { append("اصلاح پیش‌نویس"); if (com.coinepro.hq.core.data.WorkTitles.isHuman(m.id)) { append(" "); fig(m.id) } }, style = Divan.type.caption, color = c.textSecondary, modifier = Modifier.weight(1f))
                                    DIcon(DivanIcon.CLOSE, size = 14.dp, tint = c.textMuted, label = "بی‌پیش‌نویس", modifier = Modifier.clip(RoundedCornerShape(6.dp)).clickable(role = Role.Button) { from = null })
                                }
                            }
                            HqTextField(teach.text, { teach = teach.edit(it) }, "جواب درست، همان‌طور که خودت به مشتری میگویی", Modifier.fillMaxWidth(), singleLine = false, minLines = 5, maxLength = 4000)
                            Row(
                                Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp),
                                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp),
                            ) {
                                Text("تعمیم بده: بی‌داده‌ی مشتری، با متغیرهای مشخص، تا برای مشتری بعدی هم به کار برود", style = Divan.type.caption, color = c.textPrimary, modifier = Modifier.weight(1f))
                                HqSwitch(general, { general = it }, "تعمیم")
                            }
                            GuardReasons(teachReasons)
                            HqButton("بفرست و یاد بده", { doTeach() }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, icon = DivanIcon.LEARNING, enabled = teach.text.trim().length >= 5, loading = teachAction.busy)
                        }
                    }
                }
                item {
                    HqCard(Modifier.fillMaxWidth()) {
                        SectionTitle("مشتری", note = "نام کاربری ماسک‌شده؛ بیرون از این صفحه فقط نام مستعار")
                        Column(Modifier.padding(top = 12.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                            val facts = mutableListOf<@Composable (Modifier) -> Unit>(
                                { m -> Fact("نام کاربری", cv.customer.handleMasked ?: "—", m, figure = true) },
                                { m -> Fact("زبان", cv.customer.lang, m, figure = true) },
                                { m -> Fact("باز شد", jDateTime(cv.openedAt), m) },
                                { m -> Fact("آخرین پیام", jDateTime(cv.lastMessageAt), m) },
                            )
                            cv.csat?.let { s -> facts += { m -> Fact("رضایت", "$s/5", m, figure = true) } }
                            cv.handoff?.let { h -> facts += { m -> Fact("سپرده به تو", jDateTime(h.at), m) } }
                            FactRows(facts)
                            if (cv.tags.isNotEmpty()) FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) { for (t in cv.tags) ProseTag(t) }
                            cv.rescue?.let { rc ->
                                Row(
                                    Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).clickable(role = Role.Button) { nav.go("revenue") }.padding(12.dp),
                                    verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
                                ) {
                                    DIcon(DivanIcon.REFRESH, size = 16.dp, tint = c.goldInk)
                                    Text(buildAnnotatedString { append("پرونده‌ی نجات رفرال "); fig(rc) }, style = Divan.type.small, modifier = Modifier.weight(1f))
                                    DIcon(DivanIcon.NEXT, size = 14.dp, tint = c.textMuted)
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun Header(cv: Conversation, companyName: String, closing: Boolean, onClose: () -> Unit) {
    val c = Divan.colors
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Fig(cv.ref, style = Divan.type.figureSmall, color = c.textMuted)
                CompanyMark(cv.company, height = 12.dp, mono = true, ink = c.textMuted)
                Text(companyName, style = Divan.type.micro, color = c.textMuted)
                Text(CHANNEL_FA[cv.channel] ?: cv.channel, style = Divan.type.micro, color = c.textMuted)
            }
            if (cv.customer.displayName != null) Text(cv.customer.displayName, style = Divan.type.h1)
            else Fig(cv.customer.handleMasked ?: "—", style = Divan.type.figureL, color = c.textPrimary)
        }
        FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp), itemVerticalAlignment = Alignment.CenterVertically) {
            LabelPill(CONV_STATE[cv.state], cv.state)
            if (cv.handoff != null && cv.state == "waiting_owner") HANDOFF_FA[cv.handoff.reason]?.let {
                Pill(it.fa, it.tone, icon = if (cv.handoff.reason == "security") DivanIcon.URGENT else null)
            }
            if (cv.state != "closed") HqButton("بستن گفت‌وگو", onClose, variant = BtnVariant.GHOST, size = BtnSize.SM, icon = DivanIcon.CLOSE, loading = closing)
        }
    }
}

/** One message: the customer's on the reading start, ours on the other side; status, checks, confidence and cited articles under
 *  it. A draft or a refused message waits for the owner: send it as it is, correct it, or teach with it. */
@Composable
private fun Bubble(m: SupportMessage, onSend: (SupportMessage) -> Unit, onEdit: (SupportMessage) -> Unit, onTeach: (SupportMessage) -> Unit) {
    val c = Divan.colors
    val inbound = m.direction == "in"
    val pending = !inbound && (m.status == "draft" || m.status == "blocked")
    // The corner nearest the speaker's side is the small one (top-start for the customer, top-end for us).
    val shape = if (inbound) RoundedCornerShape(6.dp, 16.dp, 16.dp, 16.dp) else RoundedCornerShape(16.dp, 6.dp, 16.dp, 16.dp)
    val ring = when (m.status) { "blocked" -> c.negative.copy(alpha = 0.55f); "draft" -> c.goldInk; else -> if (!inbound && m.author != "owner") c.lineDivider else null }
    Column(Modifier.fillMaxWidth(), horizontalAlignment = if (inbound) Alignment.Start else Alignment.End, verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Column(
            Modifier.widthIn(max = 320.dp).clip(shape)
                .background(if (inbound) c.tile else if (m.author == "owner") c.raised else c.card)
                .then(if (ring != null) Modifier.border(1.dp, ring, shape) else Modifier)
                .padding(horizontal = 14.dp, vertical = 10.dp),
        ) { Masked(m.body, style = Divan.type.body) }
        FlowRow(
            horizontalArrangement = Arrangement.spacedBy(8.dp, if (inbound) Alignment.Start else Alignment.End),
            verticalArrangement = Arrangement.spacedBy(4.dp), itemVerticalAlignment = Alignment.CenterVertically,
        ) {
            Text(AUTHOR_FA[m.author] ?: m.author, style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
            Text(jTime(m.at), style = Divan.type.micro, color = c.textMuted)
            if (!inbound) {
                LabelPill(MSG_STATUS[m.status], m.status)
                Check(m.checks.guard == "pass", "نگهبان")
                m.checks.grounded?.let { Check(it == "pass", "مستند") }
            }
            m.confidence?.let { Text(buildAnnotatedString { append("اطمینان "); fig(String.format(Locale.US, "%.2f", it)) }, style = Divan.type.micro, color = c.textMuted) }
            for (k in m.kbRefs) Tag(k, figure = true)
        }
        if (m.status == "blocked") GuardReasons(m.blockedReasons)
        if (pending) FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp, Alignment.End), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            if (m.status == "draft") HqButton("همین را بفرست", { onSend(m) }, variant = BtnVariant.SECONDARY, size = BtnSize.SM, icon = DivanIcon.SEND)
            HqButton("اصلاح و فرستادن", { onEdit(m) }, variant = BtnVariant.SECONDARY, size = BtnSize.SM, icon = DivanIcon.EDIT)
            HqButton("آموزش با این", { onTeach(m) }, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.LEARNING)
        }
    }
}

@Composable
private fun Check(ok: Boolean, label: String) {
    val c = Divan.colors
    val tint = if (ok) c.positive else c.negative
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(3.dp)) {
        DIcon(if (ok) DivanIcon.SEAL else DivanIcon.URGENT, size = 12.dp, tint = tint)
        Text(label, style = Divan.type.micro, color = tint)
    }
}
