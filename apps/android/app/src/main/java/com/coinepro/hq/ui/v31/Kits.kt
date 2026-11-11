package com.coinepro.hq.ui.v31

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.items
import com.coinepro.hq.designsystem.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.connectionKindFa
import com.coinepro.hq.core.data.platformFa
import com.coinepro.hq.core.data.validCompanyCode
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.Kit
import com.coinepro.hq.core.net.KitPreview
import com.coinepro.hq.core.net.KitResult
import com.coinepro.hq.core.net.StepUp
import com.coinepro.hq.core.net.gated
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.activity
import com.coinepro.hq.ui.itemMotion
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberQuery
import com.coinepro.hq.ui.v29.IconTile
import com.coinepro.hq.ui.v29.Para
import com.coinepro.hq.ui.v29.plain
import com.coinepro.hq.ui.v29.served

// Contract §31.2 ⟨1.13⟩ «شرکت آماده»: a company from a kit with one order. The owner picks a kit, names the company, reads what will be
// made (nothing exists yet), seals it with the passkey, and gets the list of what is left to connect.

@Composable
fun KitsScreen() {
    val q = rememberQuery("kits", "kits", maxAgeMs = 300_000) { gated(HubFeature.GROWTH) { kits() } }
    val r = refresher(q)
    val has = served(HubFeature.GROWTH)
    var picked by rememberSaveable { mutableStateOf<String?>(null) }
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item { PageHeader("شرکت آماده", eyebrow = "یک شرکت تازه با تیم، خط‌های تولید و شاخص‌هایش، با یک مُهر") }
        val list = q.data
        when {
            !has -> item { Empty("شرکت آماده با به‌روزرسانی بعدی هاب میاید", icon = DivanIcon.COMPANIES) }
            list == null && q.error != null -> item { ErrorBlock(q.error, { q.refresh() }) }
            list == null -> item { Skeleton(Modifier.fillMaxWidth().height(160.dp), radius = 16.dp) }
            list.isEmpty() -> item { Empty("هنوز بسته‌ای نیست", icon = DivanIcon.COMPANIES) }
            else -> items(list, key = { it.key }) { k -> Box(itemMotion()) { KitCard(k) { picked = k.key } } }
        }
    }
    val kit = q.data?.firstOrNull { it.key == picked }
    if (kit != null) com.coinepro.hq.ui.v14.HqSheet({ picked = null }, kit.titleFa, sub = "شرکت آماده") { KitFlowBody(kit, onClose = { picked = null }) }
}

/** A kit in the gallery: what it is for, and what comes with it. */
@Composable
fun KitCard(k: Kit, onClick: () -> Unit) {
    val c = Divan.colors
    HqCard(Modifier.fillMaxWidth(), onClick = onClick) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
            IconTile(DivanIcon.COMPANIES, c.goldInk, c.softGold)
            Column(Modifier.weight(1f)) {
                Text(plain(k.titleFa), style = Divan.type.bodyStrong)
                Text(plain("${k.lines.size} خط تولید، ${k.kpis.size} شاخص، ${k.connections.size} اتصال"), style = Divan.type.caption, color = c.textMuted)
            }
        }
        Para(k.purposeFa, Modifier.padding(top = 10.dp))
    }
}

/**
 * The flow in a sheet: the form, then the preview, then the seal, then the result. [stage0] opens it at a stage (the screenshots);
 * [autoPreview] asks for the preview at once.
 */
@Composable
fun KitFlowBody(
    kit: Kit, onClose: () -> Unit, stage0: String = "form", nameFa0: String = "", nameEn0: String = "", code0: String = "",
    autoPreview: Boolean = false, result0: KitResult? = null,
) {
    val env = LocalEnv.current
    val nav = LocalNav.current
    val toasts = LocalToasts.current
    val act = activity()
    val c = Divan.colors
    val ask = rememberAction()
    val make = rememberAction()
    var stage by rememberSaveable(kit.key) { mutableStateOf(stage0) }
    var nameFa by rememberSaveable(kit.key) { mutableStateOf(nameFa0) }
    var nameEn by rememberSaveable(kit.key) { mutableStateOf(nameEn0) }
    var code by rememberSaveable(kit.key) { mutableStateOf(code0) }
    var preview by androidx.compose.runtime.remember(kit.key) { mutableStateOf<KitPreview?>(null) }
    var result by androidx.compose.runtime.remember(kit.key) { mutableStateOf(result0) }
    val ready = nameFa.trim().length >= 2 && nameEn.trim().length >= 2 && validCompanyCode(code.trim())
    fun doPreview() = ask.run {
        preview = env.api.previewKit(kit.key, code.trim(), nameFa.trim(), nameEn.trim())
        stage = "preview"
    }
    LaunchedEffect(autoPreview) { if (autoPreview && stage == "preview" && preview == null) runCatching { preview = env.api.previewKit(kit.key, code.trim(), nameFa.trim(), nameEn.trim()) } }
    Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Para(kit.purposeFa)
        when (stage) {
            "form" -> {
                Text("نام فارسی شرکت", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
                HqTextField(nameFa, { nameFa = it }, "مثلاً نوین‌رسانه", Modifier.fillMaxWidth(), maxLength = 80)
                Text("نام انگلیسی", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
                HqTextField(nameEn, { nameEn = it }, "NovinMedia", Modifier.fillMaxWidth(), figure = true, maxLength = 80)
                Text("کد شرکت (حرف بزرگ انگلیسی، ۲ تا ۱۰ نویسه)", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
                HqTextField(code, { code = it.uppercase().filter { ch -> ch in 'A'..'Z' || ch in '0'..'9' } }, "NV", Modifier.fillMaxWidth(), figure = true, maxLength = 10)
                HqButton("ببین چه ساخته میشود", { doPreview() }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, icon = DivanIcon.NEXT, enabled = ready, loading = ask.busy)
            }
            "preview" -> {
                val p = preview
                SectionTitle("چه ساخته میشود", note = "تا مُهر نکنی چیزی ساخته نمیشود")
                if (p == null) Skeleton(Modifier.fillMaxWidth().height(140.dp), radius = 12.dp)
                else KitPreviewBody(kit, p, nameFa.trim())
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    HqButton("مُهر و بساز", {
                        make.run {
                            val sign: StepUp = { a, t -> env.auth.stepUp(act, a, t) }
                            result = env.api.createFromKit(kit.key, code.trim(), nameFa.trim(), nameEn.trim(), null, sign)
                            env.cache.invalidate("companies", "groups", "lines", "employees", "connections", "home")
                            toasts.ok("شرکت ساخته شد.")
                            stage = "done"
                        }
                    }, Modifier.weight(1f), variant = BtnVariant.PRIMARY, icon = DivanIcon.SEAL, enabled = p != null, loading = make.busy)
                    HqButton("برگرد", { stage = "form" }, variant = BtnVariant.GHOST)
                }
            }
            else -> {
                val r = result
                val co = r?.company?.code ?: code
                SectionTitle("شرکت ساخته شد", note = r?.company?.nameFa ?: nameFa, icon = DivanIcon.SEAL)
                Para("تیم، کارگروه‌ها و خط‌های تولید پیش‌نویس ساخته شد و هر انتشار اول با مُهر توست.")
                val left = r?.todoFa.orEmpty()
                if (left.isNotEmpty()) Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("هنوز باید وصل کنی", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
                    for (t in left) Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text("•", style = Divan.type.small, color = c.silverInk)
                        Para(t, Modifier.weight(1f), style = Divan.type.small, color = c.textPrimary)
                    }
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    HqButton("اتصال‌ها", { onClose(); nav.go("companies/$co/connections") }, Modifier.weight(1f), variant = BtnVariant.PRIMARY, icon = DivanIcon.NEXT)
                    HqButton("باز کردن شرکت", { onClose(); nav.go("companies/$co") }, Modifier.weight(1f), variant = BtnVariant.SILVER)
                }
            }
        }
    }
}

/** The preview: the hub's own words when it sent them, then each part (the team, groups, lines as drafts, indicators, connections). */
@Composable
fun KitPreviewBody(kit: Kit, p: KitPreview, name: String) {
    val c = Divan.colors
    val lines = p.lines.ifEmpty { kit.lines }
    val groups = p.groups.ifEmpty { kit.groups }
    val connections = p.connections.ifEmpty { kit.connections }
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        if (p.previewFa.isNotBlank()) Para(p.previewFa, style = Divan.type.small, color = c.textPrimary)
        KitPart("تیم", if (p.teamFa.isNotEmpty()) p.teamFa else listOf("تیم آماده‌ی «${kit.teamTemplate}» برای ${name.ifBlank { "شرکت" }}"))
        if (groups.isNotEmpty()) KitPart("کارگروه‌ها", groups)
        KitPart("خط‌های تولید (همه پیش‌نویس)", lines.map { it.titleFa.ifBlank { platformFa(it.platform) } + "، " + platformFa(it.platform) })
        val kpis = p.kpis.ifEmpty { kit.kpis }
        if (kpis.isNotEmpty()) KitPart("شاخص‌ها", kpis)
        if (connections.isNotEmpty()) KitPart("اتصال‌ها (بعداً وصل میکنی)", connections.map { connectionKindFa(it) })
        if (p.todoFa.isNotEmpty()) KitPart("بعد از ساخت", p.todoFa)
        Text("سرور ساخته نمیشود؛ آن کار جدا است.", style = Divan.type.micro, color = c.textMuted)
    }
}

@Composable
private fun KitPart(title: String, items: List<String>) {
    val c = Divan.colors
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(title, style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textSecondary)
        for (t in items) Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("•", style = Divan.type.small, color = c.silverInk)
            Text(plain(t), style = Divan.type.small, color = c.textPrimary, modifier = Modifier.weight(1f))
        }
    }
}
