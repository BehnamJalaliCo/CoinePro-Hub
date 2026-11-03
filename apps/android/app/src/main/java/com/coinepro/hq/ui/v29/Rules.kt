package com.coinepro.hq.ui.v29

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.RULE_STATUS_FA
import com.coinepro.hq.core.data.appliesToFa
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.OwnerRule
import com.coinepro.hq.core.net.gated
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.Md
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.Radius
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.activity
import com.coinepro.hq.ui.itemMotion
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery

// Contract §29.3 ⟨1.11⟩: the owner makes a rule from the app. He says or writes it beside a voice order («قانون تازه برای هلدینگ»); the
// hub makes it one clear sentence and names whom it applies to; one tap and the passkey seal it. Sealed rules join every role they apply
// to, the overseer watches them, and the first enforcement report comes a day later. The list: edit (a new version, sealed) and retire.

@Composable
fun rememberRules() = rememberQuery("rules", "rules", "oversight", maxAgeMs = 30_000) { gated(HubFeature.RULES) { rules() } }

/** «قانون‌های من»: every rule, newest first, with how often it applied and what was found. */
@Composable
fun RulesScreen() {
    val q = rememberRules()
    val r = refresher(q)
    var editing by rememberSaveable { mutableStateOf<String?>(null) }
    val has = served(HubFeature.RULES)
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item { PageHeader("قانون‌های من", eyebrow = "آنچه همه‌ی هلدینگ باید رعایت کند") }
        item {
            Text(
                "قانون تازه را کنار دکمه‌ی طلایی فرمان بگو یا بنویس. هاب آن را یک جمله‌ی روشن میکند و با مُهر تو برای همه‌ی نقش‌هایی که به آن‌ها مربوط است اجرا میشود؛ ناظر هر روز رعایتش را میسنجد و گزارش اول فردا میرسد.",
                style = Divan.type.caption.copy(textAlign = androidx.compose.ui.text.style.TextAlign.Justify), color = Divan.colors.textMuted,
            )
        }
        val list = q.data
        when {
            !has -> item { Empty("قانون‌ها با به‌روزرسانی بعدی هاب میایند", icon = DivanIcon.SEAL, body = "تا آن موقع دستورهای دائمی در «ناظر کل» است.") }
            list == null && q.error != null -> item { ErrorBlock(q.error, { q.refresh() }) }
            list == null -> item { Skeleton(Modifier.fillMaxWidth().height(160.dp), radius = 16.dp) }
            list.isEmpty() -> item { Empty("هنوز قانونی نگذاشته‌ای", icon = DivanIcon.SEAL, body = "اولین قانون را کنار دکمه‌ی طلایی فرمان بگو.") }
            else -> items(list, key = { it.ref }) { x -> Box(itemMotion()) { RuleCard(x, onEdit = { editing = x.ref }) } }
        }
    }
    editing?.let { ref -> q.data.orEmpty().firstOrNull { it.ref == ref }?.let { RuleEditSheet(it) { editing = null } } }
}

/** One rule: its sentence, whom it applies to, its state, its counts; a proposed one is sealed with one tap. */
@Composable
fun RuleCard(x: OwnerRule, onEdit: (() -> Unit)? = null, onChanged: ((OwnerRule) -> Unit)? = null) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val c = Divan.colors
    val act = activity()
    val action = rememberAction()
    val proposed = x.status == "proposed"
    Column(
        Modifier.fillMaxWidth().alpha(if (x.status == "retired") 0.6f else 1f).clip(RoundedCornerShape(Radius.card))
            .background(if (proposed) c.softGold else c.card)
            .then(if (proposed) Modifier.border(1.dp, c.lineTahrir, RoundedCornerShape(Radius.card)) else Modifier)
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            if (x.source == "voice") DIcon(DivanIcon.MIC, size = 14.dp, tint = c.textMuted)
            Text(appliesToFa(x.appliesTo), style = Divan.type.micro, color = c.textMuted, modifier = Modifier.weight(1f))
            Pill(RULE_STATUS_FA[x.status] ?: x.status, when (x.status) { "sealed" -> Tone.POS; "proposed" -> Tone.GOLD; else -> Tone.SILVER }, dot = true)
        }
        Para(x.textMd, style = Divan.type.body, color = c.textPrimary)
        x.counts?.let { k ->
            Text(plain("روی ${k.applied} اجرا اعمال شد؛ ${k.violations} تخلف، ${k.fixed} اصلاح‌شده"), style = Divan.type.caption, color = c.textSecondary)
        } ?: x.sealedAt?.let { Text("مُهر ${ago(it)}؛ گزارش اول یک روز بعد از مُهر میرسد.", style = Divan.type.caption, color = c.textMuted) }
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            if (proposed) HqButton("مُهر کن", {
                action.run {
                    val sealed = env.api.sealRule(x.ref) { a, t -> env.auth.stepUp(act, a, t) }
                    onChanged?.invoke(sealed)
                    env.cache.invalidate("rules", "oversight")
                    toasts.ok("مُهر شد؛ از همین حالا برای همه‌ی نقش‌های مربوط اجرا میشود.")
                }
            }, variant = BtnVariant.PRIMARY, size = BtnSize.SM, icon = DivanIcon.SEAL, loading = action.busy)
            if (x.status != "retired" && onEdit != null) HqButton("ویرایش", onEdit, size = BtnSize.SM, icon = DivanIcon.EDIT)
            if (x.status == "sealed") HqButton("بازنشسته کن", {
                action.run { env.api.retireRule(x.ref); env.cache.invalidate("rules", "oversight"); toasts.ok("بازنشسته شد؛ از اجرای بعدی اعمال نمیشود.") }
            }, variant = BtnVariant.GHOST, size = BtnSize.SM)
        }
    }
}

/** A new version of a rule: the sentence edited, sealed with the passkey. */
@Composable
private fun RuleEditSheet(x: OwnerRule, onDone: () -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val act = activity()
    val action = rememberAction()
    var text by rememberSaveable(x.ref) { mutableStateOf(x.textMd) }
    com.coinepro.hq.ui.v14.HqSheet(onDone, "ویرایش قانون", sub = "نسخه‌ی تازه با مُهر تو جای قبلی را میگیرد.") {
        HqTextField(text, { text = it }, "قانون", Modifier.fillMaxWidth(), singleLine = false, minLines = 4, maxLength = 2000)
        HqButton("مُهر نسخه‌ی تازه", {
            action.run {
                env.api.putRule(x.ref, text.trim()) { a, t -> env.auth.stepUp(act, a, t) }
                env.cache.invalidate("rules", "oversight")
                toasts.ok("نسخه‌ی تازه مُهر شد.")
                onDone()
            }
        }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, icon = DivanIcon.SEAL, enabled = text.trim().length >= 3 && text.trim() != x.textMd.trim(), loading = action.busy)
    }
}
