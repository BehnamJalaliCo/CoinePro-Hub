package com.coinepro.hq.ui.playbook

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.CircleShape
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
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.data.PB_PLATFORMS
import com.coinepro.hq.core.data.applyTargets
import com.coinepro.hq.core.data.canApplyAsIs
import com.coinepro.hq.core.data.canSeal
import com.coinepro.hq.core.data.faNum
import com.coinepro.hq.core.data.libraryGroups
import com.coinepro.hq.core.data.pbPlatformFa
import com.coinepro.hq.core.data.pbPlatformLineFa
import com.coinepro.hq.core.data.playbookPatch
import com.coinepro.hq.core.data.playbookStateFa
import com.coinepro.hq.core.data.publishes
import com.coinepro.hq.core.data.withoutSeat
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.jDate
import com.coinepro.hq.core.net.Company
import com.coinepro.hq.core.net.HubFeature
import com.coinepro.hq.core.net.MemberPublish
import com.coinepro.hq.core.net.Playbook
import com.coinepro.hq.core.net.PlaybookApplied
import com.coinepro.hq.core.net.applyWithWord
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.Empty
import com.coinepro.hq.designsystem.ErrorBlock
import com.coinepro.hq.designsystem.Expand
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.HqSwitch
import com.coinepro.hq.designsystem.HqTextField
import com.coinepro.hq.designsystem.IconBtn
import com.coinepro.hq.designsystem.Md
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.ScrollRow
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.Skeleton
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.activity
import com.coinepro.hq.ui.companyOf
import com.coinepro.hq.ui.refresher
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberCompanies
import com.coinepro.hq.ui.v29.Para
import com.coinepro.hq.ui.v29.plain
import com.coinepro.hq.ui.v29.served
import java.util.UUID

// Contract §40.2–§40.3 ⟨1.22⟩: «کارگروه‌ها». A session's result as a working group the owner keeps: the library (sealed first), and each
// playbook's page. A draft is read whole and lightly edited here (its title, purpose and platform; a seat, a routine or a rule taken out;
// a routine's brief and a rule's words); the main way to change it is still to say it in its session, where the holder rewrites it.
// Sealed (🔏), it is a working group: its member companies, and «به شرکت دیگر بده» (a company, a platform, a note; or «بدون تغییر»).

// ----------------------------------------------------------------- library --
@Composable
fun PlaybooksScreen() {
    val nav = LocalNav.current
    val q = rememberPlaybooks()
    val on = served(HubFeature.PLAYBOOKS)
    val companies = rememberCompanies()
    val r = refresher(q)
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item(key = "head") { PageHeader("کارگروه‌ها", eyebrow = "نتیجه‌ی هر جلسه، ماندگار؛ مُهرش کن و به هر شرکت و پلتفرمی بده") }
        val list = q.data
        when {
            list == null && q.error != null -> item(key = "error") { ErrorBlock(q.error, { q.refresh() }) }
            list == null && !on -> item(key = "none") {
                Empty("کارگروه‌ها با به‌روزرسانی بعدی هاب میایند", icon = DivanIcon.DEPARTMENT, body = "تا آن موقع کارگروه‌های هر شرکت در «کارگروه‌ها»ی رشد است.")
            }
            list == null -> items(3, key = { "sk-$it" }) { Skeleton(Modifier.fillMaxWidth().height(72.dp), radius = 14.dp) }
            list.isEmpty() -> item(key = "empty") {
                Empty("هنوز کارگروهی نیست", icon = DivanIcon.DEPARTMENT, body = "از هر جلسه با دکمه‌ی «کارگروه از این جلسه بساز» در «جزئیات» همان جلسه.")
            }
            else -> for ((title, group) in libraryGroups(list)) {
                item(key = "t-$title") { SectionTitle(title, note = "${faNum(group.size)} کارگروه") }
                item(key = "g-$title") {
                    HqCard(Modifier.fillMaxWidth(), padding = PaddingValues(vertical = 4.dp)) {
                        group.forEachIndexed { i, pb ->
                            if (i > 0) HorizontalDivider(color = Divan.colors.lineDivider)
                            PlaybookRow(pb, pb.source.company?.let { companyOf(companies, it).nameFa }, showState = false) { nav.go("playbook/${pb.ref}") }
                        }
                    }
                }
            }
        }
    }
}

// -------------------------------------------------------------------- page --
private enum class PbSheet { NONE, APPLY, RETIRE }

@Composable
fun PlaybookScreen(ref: String) {
    val env = LocalEnv.current
    val nav = LocalNav.current
    val toasts = LocalToasts.current
    val q = rememberPlaybook(ref)
    val on = served(HubFeature.PLAYBOOKS)
    val r = refresher(q)
    var sheet by rememberSaveable { mutableStateOf(PbSheet.NONE) }
    // `group.playbook` names the playbook that moved (drafted, edited in the session, sealed, given, retired).
    LaunchedEffect(env, ref) { env.stream.events.collect { e -> if (e.type == "group.playbook" && e.ref == ref) q.refresh() } }
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        val pb = q.data
        when {
            pb == null && q.error != null -> item(key = "error") { ErrorBlock(q.error, { q.refresh() }) }
            pb == null && !on -> item(key = "none") { Empty("کارگروه‌ها با به‌روزرسانی بعدی هاب میایند", icon = DivanIcon.DEPARTMENT) }
            pb == null -> item(key = "sk") { Skeleton(Modifier.fillMaxWidth().height(420.dp), radius = 16.dp) }
            else -> item(key = "body") {
                PlaybookBody(pb, onSaved = { q.set(it) }, onApply = { sheet = PbSheet.APPLY }, onRetire = { sheet = PbSheet.RETIRE })
            }
        }
    }
    val pb = q.data ?: return
    when (sheet) {
        PbSheet.NONE -> Unit
        PbSheet.APPLY -> com.coinepro.hq.ui.v14.HqSheet({ sheet = PbSheet.NONE }, "به شرکت دیگر بده", sub = "همین کارگروه برای شرکت دیگری، روی هر پلتفرمی.") {
            ApplyBody(pb, rememberCompanies()) { out, name ->
                sheet = PbSheet.NONE
                env.cache.invalidate("sessions", *PLAYBOOK_TAGS)
                val order = out.order
                if (order != null) {
                    toasts.ok("جلسه‌ی تازه برای $name باز شد.")
                    nav.go("session/$order")
                } else {
                    q.set(out.playbook)
                    toasts.ok("به $name داده شد.")
                }
            }
        }
        PbSheet.RETIRE -> com.coinepro.hq.ui.v14.HqSheet({ sheet = PbSheet.NONE }, "بازنشسته کردن کارگروه", sub = "کارهای روتینش برای همه‌ی شرکت‌های عضو می‌ایستد؛ چیزی پاک نمیشود.") {
            RetireBody(pb, onCancel = { sheet = PbSheet.NONE }) { out -> sheet = PbSheet.NONE; q.set(out) }
        }
    }
}

/**
 * A playbook whole. A draft keeps the owner's light edits on the phone until «ذخیره» (one `PATCH` of only what changed); it is sealed
 * only when nothing is left unsaved. A sealed one shows its members and «به شرکت دیگر بده»; a retired one says what stopped.
 */
@Composable
internal fun PlaybookBody(pb: Playbook, onSaved: (Playbook) -> Unit, onApply: () -> Unit, onRetire: () -> Unit) {
    val env = LocalEnv.current
    val nav = LocalNav.current
    val toasts = LocalToasts.current
    val act = activity()
    val c = Divan.colors
    val companies = rememberCompanies()
    var edit by remember(pb.ref, pb.version, pb.state) { mutableStateOf(pb) }
    val patch = if (pb.draft) playbookPatch(pb, edit) else null
    val shown = if (pb.draft) edit else pb
    var head by rememberSaveable(pb.ref) { mutableStateOf(false) }
    var menu by remember { mutableStateOf(false) }
    val save = rememberAction()
    val seal = rememberAction()
    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        // ---- the head: what it is, its state, ⋮
        Row(verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Text("کارگروه، روی ${pbPlatformLineFa(shown.platform)}", style = Divan.type.caption, color = c.textMuted)
                Text(plain(shown.titleFa.ifBlank { "کارگروه بی‌نام" }), style = Divan.type.h1, color = c.textPrimary)
            }
            playbookStateFa(pb.state).let { (fa, tone) -> Pill(fa, tone, Modifier.padding(top = 4.dp), dot = true) }
            if (!pb.retired) Box {
                IconBtn(DivanIcon.MORE, "بیشتر", { menu = true }, tint = c.textSecondary)
                androidx.compose.material3.DropdownMenu(menu, { menu = false }, containerColor = c.overlay) {
                    androidx.compose.material3.DropdownMenuItem(
                        text = { Text("بازنشسته کن", style = Divan.type.body, color = c.negative) },
                        leadingIcon = { DIcon(DivanIcon.PAUSE, size = 20.dp, tint = c.negative) },
                        onClick = { menu = false; onRetire() },
                    )
                }
            }
        }
        // ---- where it came from, its version, its dates
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            val co = pb.source.company?.let { companyOf(companies, it).nameFa }
            Text(
                "از جلسه‌ای در ${co ?: "هلدینگ"}",
                Modifier.clip(CircleShape).clickable(role = Role.Button, onClickLabel = "جلسه‌اش") { nav.go("session/${pb.source.order}") }.padding(horizontal = 4.dp, vertical = 2.dp),
                style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.goldInk,
            )
            Text(
                plain(listOfNotNull(
                    "نسخه‌ی ${faNum(pb.version)}",
                    pb.sealedAt?.let { "مُهر ${jDate(it)}" } ?: pb.createdAt.takeIf { it.isNotBlank() }?.let { "پیش‌نویس ${jDate(it)}" },
                    pb.parent?.let { "برگرفته از کارگروهی دیگر" },
                ).joinToString(" · ")),
                style = Divan.type.micro, color = c.textMuted, modifier = Modifier.weight(1f),
            )
        }
        if (pb.draft) Hint(onSession = { nav.go("session/${pb.source.order}") })
        pb.noteFa?.takeIf { it.isNotBlank() }?.let { note ->
            HqCard(Modifier.fillMaxWidth(), color = c.softWarning, padding = PaddingValues(12.dp)) {
                Text("آنچه کنار گذاشته شد", style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = c.warning)
                Para(note, style = Divan.type.caption, color = c.textPrimary)
            }
        }
        // ---- purpose (and, for a draft, the title and the purpose to edit)
        HqCard(Modifier.fillMaxWidth()) {
            SectionTitle("هدف", icon = DivanIcon.STAR) {
                if (pb.draft) HqButton(if (head) "بستن" else "ویرایش", { head = !head }, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.EDIT)
            }
            Column(Modifier.padding(top = 8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                if (pb.draft && head) {
                    HqTextField(edit.titleFa, { edit = edit.copy(titleFa = it) }, "نام کارگروه", Modifier.fillMaxWidth(), maxLength = 200)
                    HqTextField(edit.purposeFa, { edit = edit.copy(purposeFa = it) }, "هدفش در یکی دو جمله", Modifier.fillMaxWidth(), singleLine = false, minLines = 2, maxLength = 2000)
                } else if (shown.purposeFa.isNotBlank()) com.coinepro.hq.ui.Selectable { Para(shown.purposeFa, style = Divan.type.small, color = c.textPrimary) }
                else Text("هدفی نوشته نشده.", style = Divan.type.caption, color = c.textMuted)
                if (pb.draft) {
                    Text("پلتفرم", style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = c.textMuted)
                    ScrollRow { for (p in PB_PLATFORMS) FilterChip(pbPlatformFa(p), edit.platform == p, { edit = edit.copy(platform = p) }) }
                }
            }
        }
        SeatsCard(shown, editable = pb.draft) { seat -> edit = withoutSeat(edit, seat) }
        RoutinesCard(shown, editable = pb.draft, onRemove = { k -> edit = edit.copy(routines = edit.routines.filter { it.key != k }) }) { k, brief ->
            edit = edit.copy(routines = edit.routines.map { if (it.key == k) it.copy(briefMd = brief) else it })
        }
        if (shown.kpis.isNotEmpty()) HqCard(Modifier.fillMaxWidth()) {
            SectionTitle("شاخص‌ها", note = "از اتصال‌های هر شرکت عضو، هر روز", icon = DivanIcon.CHART)
            Column(Modifier.padding(top = 6.dp)) {
                shown.kpis.forEachIndexed { i, k ->
                    if (i > 0) HorizontalDivider(color = c.lineDivider)
                    Row(Modifier.fillMaxWidth().padding(vertical = 8.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text(plain(k.titleFa.ifBlank { k.key }), style = Divan.type.small, color = c.textPrimary, modifier = Modifier.weight(1f))
                        if (k.unit.isNotBlank()) Text(plain(k.unit), style = Divan.type.micro, color = c.textMuted)
                    }
                }
            }
        }
        RulesCard(shown, editable = pb.draft, onRemove = { i -> edit = edit.copy(rulesFa = edit.rulesFa.filterIndexed { j, _ -> j != i }) }) { i, text ->
            edit = edit.copy(rulesFa = edit.rulesFa.mapIndexed { j, r -> if (j == i) text else r })
        }
        if (shown.connections.isNotEmpty()) HqCard(Modifier.fillMaxWidth()) {
            SectionTitle("اتصال‌های لازم", note = "هر شرکت عضو باید این‌ها را وصل کرده باشد", icon = DivanIcon.GLOBE)
            FlowRow(Modifier.padding(top = 8.dp), horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                for (k in shown.connections) Pill(com.coinepro.hq.core.data.connectionKindFa(k), Tone.NEUTRAL)
            }
        }
        if (!pb.draft) HqCard(Modifier.fillMaxWidth()) {
            SectionTitle("شرکت‌های عضو", note = if (pb.members.isEmpty()) null else "${faNum(pb.members.size)} شرکت این کارگروه را دارند", icon = DivanIcon.COMPANIES) {
                pb.group?.let { g -> HqButton("کارگروه در کار", { nav.go("groups/$g") }, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.NEXT) }
            }
            Column(Modifier.padding(top = 4.dp)) { MembersBlock(pb) }
        }
        // ---- what the owner does with it
        var word by rememberSaveable(pb.ref, stateSaver = StandingSaver) { mutableStateOf(MemberPublish(mode = "auto")) }
        when {
            pb.draft -> Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                if (patch != null) Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    HqButton("ذخیره‌ی تغییرها", {
                        save.run {
                            val out = env.api.patchPlaybook(pb.ref, patch)
                            env.cache.invalidate(*PLAYBOOK_TAGS)
                            toasts.ok("پیش‌نویس ذخیره شد.")
                            onSaved(out)
                        }
                    }, Modifier.weight(1f), variant = BtnVariant.PRIMARY, icon = DivanIcon.EDIT, loading = save.busy)
                    HqButton("برگردان", { edit = pb; head = false }, variant = BtnVariant.TEXT)
                }
                // ⟨0.19.9⟩ §45 his standing word, given with the seal: on, as he asked («به صورت خودکار از روز دوم انجام بشه»)
                if (publishes(pb)) StandingChoice(word, { word = it })
                HqButton("مُهر کن", {
                    seal.run {
                        val said = word.takeIf { publishes(pb) }
                        val out = env.api.sealPlaybook(pb.ref, said) { a, t -> env.auth.stepUp(act, a, t) }
                        env.cache.invalidate(*PLAYBOOK_TAGS)
                        toasts.ok(sealedFa(out, said))
                        onSaved(out)
                    }
                }, Modifier.fillMaxWidth(), variant = if (patch == null) BtnVariant.PRIMARY else BtnVariant.SECONDARY, size = BtnSize.LG, icon = DivanIcon.SEAL,
                    enabled = patch == null && canSeal(pb), loading = seal.busy)
                Text(
                    if (patch != null) "اول تغییرها را ذخیره کن، بعد مُهر بزن."
                    else "با مُهر تو کارگروه ساخته میشود و همین شرکت اولین عضوش؛ جایگاه‌ها به همان کسانی میرسد که در جلسه بودند و جای خالی با استخدام خودکار در سقف پاکت پر میشود.",
                    style = Divan.type.micro, color = c.textMuted, modifier = Modifier.padding(horizontal = 4.dp),
                )
            }
            pb.sealed -> HqButton("به شرکت دیگر بده", onApply, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, size = BtnSize.LG, icon = DivanIcon.SHARE)
            else -> Text(
                plain("بازنشسته شد${pb.retiredAt?.let { " ${jDate(it)}" }.orEmpty()}؛ کارهای روتینش برای همه‌ی شرکت‌ها ایستاده است. چیزی پاک نشده."),
                style = Divan.type.caption, color = c.textMuted, modifier = Modifier.padding(horizontal = 4.dp),
            )
        }
    }
}

/** A draft's hint: the main way to change it is to say it in its session. */
@Composable
private fun Hint(onSession: () -> Unit) {
    val c = Divan.colors
    Row(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.softLapis).padding(start = 12.dp, end = 4.dp, top = 8.dp, bottom = 8.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        DIcon(DivanIcon.MESSAGES, size = 16.dp, tint = c.lapis)
        Text(
            "راه اصلی تغییر این پیش‌نویس گفتن در خود جلسه است؛ مسئول جلسه آن را بازنویسی میکند. این‌جا فقط ویرایش سبک.",
            style = Divan.type.caption, color = c.textPrimary, modifier = Modifier.weight(1f),
        )
        HqButton("جلسه", onSession, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.NEXT)
    }
}

@Composable
private fun SeatsCard(pb: Playbook, editable: Boolean, onRemove: (String) -> Unit) {
    val c = Divan.colors
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("جایگاه‌ها", note = if (pb.seats.isEmpty()) null else "${faNum(pb.seats.size)} نفر؛ هر کدام با کارش و ابزارهایش", icon = DivanIcon.AGENT)
        Column(Modifier.padding(top = 8.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            if (pb.seats.isEmpty()) Text("هنوز جایگاهی ندارد.", style = Divan.type.caption, color = c.textMuted)
            pb.seats.forEachIndexed { i, s ->
                if (i > 0) HorizontalDivider(color = c.lineDivider)
                SeatRow(s, onRemove = if (editable) ({ onRemove(s.seat) }) else null)
            }
        }
    }
}

@Composable
private fun RoutinesCard(pb: Playbook, editable: Boolean, onRemove: (String) -> Unit, onBrief: (String, String) -> Unit) {
    val c = Divan.colors
    var open by rememberSaveable(pb.ref) { mutableStateOf<String?>(null) }
    var editing by rememberSaveable(pb.ref) { mutableStateOf<String?>(null) }
    var draft by rememberSaveable(pb.ref) { mutableStateOf("") }
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("کارهای روتین", note = "هر کدام سر وقتش یک کار کوچک برای همان جایگاه", icon = DivanIcon.TIME)
        Column(Modifier.padding(top = 8.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            if (pb.routines.isEmpty()) Text("کار روتینی ندارد.", style = Divan.type.caption, color = c.textMuted)
            pb.routines.forEachIndexed { i, r ->
                if (i > 0) HorizontalDivider(color = c.lineDivider)
                val shown = open == r.key || editing == r.key
                RoutineLine(pb, r) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        if (r.briefMd.isNotBlank() || editable) IconBtn(DivanIcon.CHEVRON, if (shown) "بستن" else "دستور کار", { open = if (open == r.key) null else r.key }, tint = c.textMuted)
                        if (editable) IconBtn(DivanIcon.CLOSE, "این کار روتین را بردار", { onRemove(r.key) }, tint = c.textMuted)
                    }
                }
                Expand(shown) {
                    Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(c.tile).padding(10.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        if (editing == r.key) {
                            HqTextField(draft, { draft = it }, "دستور کار هر بار", Modifier.fillMaxWidth(), singleLine = false, minLines = 3, maxLength = 4000)
                            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                HqButton("نگه دار", { onBrief(r.key, draft); editing = null }, size = BtnSize.SM, icon = DivanIcon.SEAL, enabled = draft.isNotBlank())
                                HqButton("بیخیال", { editing = null }, variant = BtnVariant.TEXT, size = BtnSize.SM)
                            }
                        } else {
                            if (r.briefMd.isNotBlank()) com.coinepro.hq.ui.Selectable { Md(r.briefMd, color = c.textPrimary) }
                            else Text("دستور کاری نوشته نشده.", style = Divan.type.caption, color = c.textMuted)
                            if (editable) HqButton("ویرایش دستور کار", { draft = r.briefMd; editing = r.key }, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.EDIT)
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun RulesCard(pb: Playbook, editable: Boolean, onRemove: (Int) -> Unit, onEdit: (Int, String) -> Unit) {
    val c = Divan.colors
    var editing by rememberSaveable(pb.ref) { mutableStateOf<Int?>(null) }
    var draft by rememberSaveable(pb.ref) { mutableStateOf("") }
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("قاعده‌ها", note = "آنچه همه‌ی جایگاه‌ها رعایت میکنند", icon = DivanIcon.KNOWLEDGE)
        Column(Modifier.padding(top = 8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            if (pb.rulesFa.isEmpty()) Text("قاعده‌ای ندارد.", style = Divan.type.caption, color = c.textMuted)
            pb.rulesFa.forEachIndexed { i, rule ->
                if (editing == i) Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    HqTextField(draft, { draft = it }, "متن قاعده", Modifier.fillMaxWidth(), singleLine = false, minLines = 2, maxLength = 500)
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        HqButton("نگه دار", { onEdit(i, draft.trim()); editing = null }, size = BtnSize.SM, icon = DivanIcon.SEAL, enabled = draft.isNotBlank())
                        HqButton("بیخیال", { editing = null }, variant = BtnVariant.TEXT, size = BtnSize.SM)
                    }
                } else RuleLine(rule) {
                    if (editable) Row {
                        IconBtn(DivanIcon.EDIT, "ویرایش این قاعده", { draft = rule; editing = i }, tint = c.textMuted)
                        IconBtn(DivanIcon.CLOSE, "این قاعده را بردار", { onRemove(i) }, tint = c.textMuted)
                    }
                }
            }
        }
    }
}

// ------------------------------------------------------------------- apply --
/**
 * «به شرکت دیگر بده»: the company (by its name, never a code), and either «بدون تغییر» (a sealed group: the company joins at once, no
 * session) or a platform and an optional note for the new session that adapts it there. One key per set of choices, kept across a
 * retry of the same press. [onApplied] gets the answer and the company's name.
 */
@Composable
internal fun ApplyBody(pb: Playbook, companies: List<Company>, company0: String? = null, asIs0: Boolean = false, onApplied: (PlaybookApplied, String) -> Unit) {
    val env = LocalEnv.current
    val c = Divan.colors
    val targets = applyTargets(pb, companies)
    var company by rememberSaveable(pb.ref) { mutableStateOf(company0?.takeIf { co -> targets.any { it.code == co } }) }
    var platform by rememberSaveable(pb.ref) { mutableStateOf(pb.platform) }
    var note by rememberSaveable(pb.ref) { mutableStateOf("") }
    var asIs by rememberSaveable(pb.ref) { mutableStateOf(asIs0 && canApplyAsIs(pb)) }
    // ⟨0.19.9⟩ §45 with «بدون تغییر», his standing word for that company (as the group's first member has it)
    var word by rememberSaveable(pb.ref, stateSaver = StandingSaver) {
        mutableStateOf(MemberPublish(mode = if (pb.members.any { it.publish.auto }) "auto" else "ask", story = pb.members.any { it.publish.story }))
    }
    val standing = asIs && publishes(pb) && env.api.gaps.has(HubFeature.STANDING_PUBLISH)
    val key = remember(company, platform, note, asIs, word) { UUID.randomUUID().toString() }
    val go = rememberAction()
    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        Text("به کدام شرکت؟", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textMuted)
        if (targets.isEmpty()) Text("همه‌ی شرکت‌ها همین حالا این کارگروه را دارند.", style = Divan.type.small, color = c.textSecondary)
        else FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            for (co in targets) FilterChip(co.nameFa ?: co.code, company == co.code, { company = co.code })
        }
        if (canApplyAsIs(pb)) Row(
            Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(12.dp),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                Text("بدون تغییر", style = Divan.type.bodyStrong, color = c.textPrimary)
                Text("شرکت همین حالا عضو میشود، با همین جایگاه‌ها و کارهای روتین؛ بی جلسه‌ی تازه.", style = Divan.type.micro, color = c.textMuted)
            }
            HqSwitch(asIs, { asIs = it }, "بدون تغییر")
        }
        Expand(standing) { StandingChoice(word, { word = it }) }
        Expand(!asIs) {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text("روی کدام پلتفرم؟", style = Divan.type.caption.copy(fontWeight = FontWeight.SemiBold), color = c.textMuted)
                FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    for (p in PB_PLATFORMS) FilterChip(pbPlatformFa(p), platform == p, { platform = p })
                }
                HqTextField(note, { note = it }, "یادداشت برای آن شرکت (اختیاری)", Modifier.fillMaxWidth(), singleLine = false, minLines = 2, maxLength = 2000)
                Text(
                    "برای آن شرکت یک جلسه‌ی تازه باز میشود؛ مدیرعاملش کارگروه را با حساب‌ها، لحن و پلتفرم خودش جور میکند و آخرش تو مُهر میزنی.",
                    style = Divan.type.micro, color = c.textMuted,
                )
            }
        }
        val name = targets.firstOrNull { it.code == company }?.let { it.nameFa ?: it.code }
        HqButton(
            if (asIs) "عضوش کن" else "بده و جلسه‌اش را باز کن", {
                val co = company ?: return@HqButton
                go.run { onApplied(env.api.applyWithWord(pb.ref, co, platform, note, asIs, key, word.takeIf { standing }), name ?: co) }
            },
            Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, size = BtnSize.LG, icon = if (asIs) DivanIcon.ADD else DivanIcon.SEND,
            enabled = company != null, loading = go.busy,
        )
    }
}

// ------------------------------------------------------------------ retire --
@Composable
private fun RetireBody(pb: Playbook, onCancel: () -> Unit, onDone: (Playbook) -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val act = activity()
    val c = Divan.colors
    val go = rememberAction()
    Text(
        if (pb.members.isEmpty()) "این کارگروه هنوز در هیچ شرکتی کار نمیکند؛ کنار میرود و در کتابخانه میماند."
        else "در ${faNum(pb.members.size)} شرکت کار میکند؛ همه‌جا می‌ایستد. جلسه‌ها، کارها و خروجی‌هایش میمانند.",
        style = Divan.type.small, color = c.textSecondary,
    )
    HqButton("بازنشسته کن", {
        go.run {
            val out = env.api.retirePlaybook(pb.ref) { a, t -> env.auth.stepUp(act, a, t) }
            env.cache.invalidate(*PLAYBOOK_TAGS)
            toasts.ok("بازنشسته شد؛ کارهای روتینش ایستاد.")
            onDone(out)
        }
    }, Modifier.fillMaxWidth(), variant = BtnVariant.DANGER, size = BtnSize.LG, icon = DivanIcon.PAUSE, loading = go.busy)
    HqButton("بیخیال", onCancel, Modifier.fillMaxWidth(), variant = BtnVariant.TEXT)
}

/** The standing word across a rotation: `mode`, `story`, the hour (the account is asked by the hub when there are several). */
internal val StandingSaver = androidx.compose.runtime.saveable.Saver<MemberPublish, List<Any>>(
    save = { listOf(it.mode, it.story, it.at.orEmpty()) },
    restore = { MemberPublish(mode = it[0] as String, story = it[1] as Boolean, at = (it[2] as String).ifBlank { null }) },
)

