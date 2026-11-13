package com.coinepro.hq.ui.playbook

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.HorizontalDivider
import com.coinepro.hq.designsystem.Text
import com.coinepro.hq.designsystem.continuity
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.runtime.Stable
import androidx.compose.ui.platform.testTag
import com.coinepro.hq.core.data.sealSummary
import com.coinepro.hq.designsystem.DecisionBar
import com.coinepro.hq.designsystem.DecisionPage
import com.coinepro.hq.designsystem.DecisionPlace
import com.coinepro.hq.designsystem.DecisionState
import com.coinepro.hq.designsystem.IconBtn
import com.coinepro.hq.designsystem.Pill
import com.coinepro.hq.designsystem.QuietAction
import com.coinepro.hq.designsystem.facts
import com.coinepro.hq.designsystem.rememberCollapse
import com.coinepro.hq.designsystem.rememberHaptics
import com.coinepro.hq.ui.look.Fold
import com.coinepro.hq.ui.look.GroupHeader
import com.coinepro.hq.ui.look.QuietLink
import com.coinepro.hq.core.data.PB_PLATFORMS
import com.coinepro.hq.core.data.applyTargets
import com.coinepro.hq.core.data.canApplyAsIs
import com.coinepro.hq.core.data.canSeal
import com.coinepro.hq.core.data.faNum
import com.coinepro.hq.core.data.libraryGroups
import com.coinepro.hq.core.data.pbPlatformFa
import com.coinepro.hq.core.data.pbPlatformLineFa
import com.coinepro.hq.core.data.playbookPatch
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
import com.coinepro.hq.core.net.gated
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
import com.coinepro.hq.designsystem.Md
import com.coinepro.hq.designsystem.PageHeader
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
// playbook's page. ⟨1.0.1⟩ Part C (C3.4), in the look:
// - a sealed page opens with its member companies as tiles (state, last run, next run; a silver work line only while something runs;
//   a member that stands still with its one-line reason and «راه بینداز»; under each ONE grouped block of its settings), then each
//   routine with its last seven runs as dots; what the group is (goal, seats, routines, figures, connections, rules) is folded under
//   «تعریف کارگروه»;
// - a draft is lightly edited here (its title, purpose and platform; a seat, a routine or a rule taken out; a routine's brief and a
//   rule's words); «مُهر کارگروه» lives in the page's decision bar with what the seal starts in one line («۳ جایگاه | ۲ روال | ۱ اتصال»):
//   one tap, the hub decides about the passkey (it asks none for a seal of a working group). The main way to change a draft is still
//   to say it in its session, where the holder rewrites it;
// - «به شرکت دیگر بده» is a spring sheet with its decision bar (a company, a platform, a note; or «بدون تغییر»).

// ----------------------------------------------------------------- library --
@Composable
fun PlaybooksScreen() {
    val nav = LocalNav.current
    val on = served(HubFeature.PLAYBOOKS)
    val companies = rememberCompanies()
    // ⟨1.37⟩ §59.1 the library: search, the filters (platform, state, company) and a card per playbook with its figures
    var text by rememberSaveable { mutableStateOf("") }
    var platform by rememberSaveable { mutableStateOf<String?>(null) }
    var state by rememberSaveable { mutableStateOf<String?>(null) }
    var company by rememberSaveable { mutableStateOf<String?>(null) }
    val q = rememberLibrary(text.trim(), platform, state, company)
    val r = refresher(q)
    val importFile = rememberImport { pb -> nav.go("playbook/${pb.ref}") }
    val library = served(HubFeature.LIBRARY)
    Page(onRefresh = r::refresh, refreshing = r.refreshing) {
        item(key = "head") {
            PageHeader("کتابخانه‌ی کارگروه‌ها", eyebrow = "هر کارگروه آزموده، نسخه‌دار؛ با یک فرم در هر شرکتی به کار میرود") {
                if (library) IconBtn(DivanIcon.ATTACH, "درون‌آوری فایل", importFile)
            }
        }
        item(key = "search") {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                HqTextField(text, { text = it }, "جستجو در نام و هدف کارگروه‌ها", Modifier.fillMaxWidth(), maxLength = 80)
                LibraryFilters(
                    platform, { platform = it }, state, { state = it }, company, { company = it },
                    companies.filter { it.kind != "holding" && it.status != "archived" }.map { it.code to (it.nameFa ?: it.code) },
                )
            }
        }
        val list = q.data?.let { com.coinepro.hq.core.data.libraryFiltered(it, text, platform, state, company) }
        when {
            list == null && q.error != null -> item(key = "error") { ErrorBlock(q.error, { q.refresh() }) }
            list == null && !on -> item(key = "none") {
                Empty("کارگروه‌ها با به‌روزرسانی بعدی هاب میایند", icon = DivanIcon.DEPARTMENT, body = "تا آن موقع کارگروه‌های هر شرکت در «کارگروه‌ها»ی رشد است.")
            }
            list == null -> items(3, key = { "sk-$it" }) { Skeleton(Modifier.fillMaxWidth().height(120.dp), radius = 14.dp) }
            list.isEmpty() && (text.isNotBlank() || platform != null || state != null || company != null) -> item(key = "nothing") {
                Empty("کارگروهی با این پالایش نیست", icon = DivanIcon.FILTER)
            }
            list.isEmpty() -> item(key = "empty") {
                Empty("هنوز کارگروهی نیست", icon = DivanIcon.DEPARTMENT, body = "جلسه‌ای که بسته شود کارگروهش را این‌جا میگذارد؛ یا از «جزئیات» هر جلسه «کارگروه از این جلسه بساز».")
            }
            else -> items(list.size, key = { "pb-" + list[it].ref }) { i -> LibraryCard(list[i]) { nav.go("playbook/${list[i].ref}") } }
        }
    }
}

// -------------------------------------------------------------------- page --
private enum class PbSheet { NONE, APPLY, RETIRE, COPY, COMPARE, USE_VERSION }

/** A draft's light edits, kept on the phone until «ذخیره» or the seal (one `PATCH` of only what changed). */
@Stable
private class DraftEdit(val pb: Playbook) {
    var edit by mutableStateOf(pb)
    /** What goes to the hub: the edits with empty rules left out. */
    val clean: Playbook get() = edit.copy(rulesFa = edit.rulesFa.map { it.trim() }.filter { it.isNotEmpty() })
    val patch get() = playbookPatch(pb, clean)
}

@Composable
fun PlaybookScreen(ref: String, version: Int? = null) {
    val env = LocalEnv.current
    val nav = LocalNav.current
    val toasts = LocalToasts.current
    val act = activity()
    val haptics = rememberHaptics()
    val c = Divan.colors
    // ⟨1.37⟩ §59.1 a version of its own ([version]), or the playbook as the hub serves it (the newest sealed, else the newest draft)
    val q = if (version == null) rememberPlaybook(ref)
    else com.coinepro.hq.ui.rememberQuery("playbook:$ref:v$version", "playbooks", "groups", maxAgeMs = 15_000) { gated(HubFeature.PLAYBOOKS) { playbookAt(ref, version) } }
    val on = served(HubFeature.PLAYBOOKS)
    val r = refresher(q)
    val companies = rememberCompanies()
    var sheet by rememberSaveable { mutableStateOf(PbSheet.NONE) }
    var pickedVersion by rememberSaveable { mutableStateOf(0) }
    val library = served(HubFeature.LIBRARY)
    // `group.playbook` names the playbook that moved (drafted, edited in the session, sealed, given, retired).
    LaunchedEffect(env, ref) { env.stream.events.collect { e -> if (e.type == "group.playbook" && e.ref == ref) q.refresh() } }
    val pb = q.data
    val listState = rememberLazyListState()
    val collapse = rememberCollapse(listState)
    val draft = remember(pb?.ref, pb?.version, pb?.state) { pb?.takeIf { it.draft }?.let(::DraftEdit) }
    // ⟨0.19.9⟩ §45 his standing word, given with the seal: on, as he asked («به صورت خودکار از روز دوم انجام بشه»)
    var word by rememberSaveable(ref, stateSaver = StandingSaver) { mutableStateOf(MemberPublish(mode = "auto")) }
    val save = rememberAction()
    val seal = rememberAction()
    val shown = draft?.edit ?: pb

    DecisionPage(
        bar = if (pb != null && draft != null) ({
            val dirty = draft.patch != null
            // «مُهر کارگروه»: the page's one act, with what the seal starts in one line. One tap; a seal with unsaved edits saves first.
            DecisionBar(
                "مُهر کارگروه", {
                    seal.run(onError = { e -> haptics.error(); toasts.error(e.messageFa) }) {
                        var cur: Playbook = pb
                        draft.patch?.let { p -> cur = env.api.patchPlaybook(pb.ref, p) }
                        val said = word.takeIf { publishes(cur) }
                        val out = env.api.sealPlaybook(pb.ref, said) { a, t -> env.auth.stepUp(act, a, t) }
                        haptics.seal()
                        env.cache.invalidate(*PLAYBOOK_TAGS)
                        toasts.ok(sealedFa(out, said))
                        q.set(out)
                    }
                },
                context = (sealSummary(draft.clean.seats.size, draft.clean.routines.size, pb.connections.size) + (if (dirty) "مُهر اول تغییرهایت را ذخیره میکند" else "با مُهر، روال‌ها شروع میشوند")).joinToString(" · "),
                quiet = listOf(QuietAction("ذخیره", enabled = dirty && !save.busy && !seal.busy) {
                    val p = draft.patch ?: return@QuietAction
                    save.run {
                        val out = env.api.patchPlaybook(pb.ref, p)
                        env.cache.invalidate(*PLAYBOOK_TAGS)
                        toasts.ok("ذخیره شد.")
                        q.set(out)
                    }
                }),
                state = if (seal.busy) DecisionState.WORKING else DecisionState.IDLE, enabled = canSeal(draft.clean) && !save.busy, icon = DivanIcon.SEAL, place = DecisionPlace.PAGE,
            )
        }) else null,
    ) {
        Column(Modifier.fillMaxSize()) {
            // ⟨1.0.1⟩ M14: the row of the library grows into this header; M18: it folds to the title and the state.
            if (pb != null && shown != null) GroupHeader(
                { collapse.value }, "کارگروه‌های آماده", shown.titleFa.ifBlank { "کارگروه بی‌نام" }, Modifier.continuity("playbook/${pb.ref}"),
                state = { PlaybookState(pb.state) },
                facts = {
                    Text(
                        remember(pb, shown.platform, companies) {
                            facts(
                                pbPlatformLineFa(shown.platform), com.coinepro.hq.core.data.versionFa(pb.version).takeIf { pb.versions.isNotEmpty() },
                                pb.source.company?.let { "شرکت: ${companyOf(companies, it).nameFa}" },
                                pb.parent?.let { "نسخه‌ای از کارگروهی دیگر" }, pb.createdAt.takeIf { it.isNotBlank() }?.let { "ساخته شد ${jDate(it)}" },
                                pb.sealedAt?.let { "مُهر شد ${jDate(it)}" }, pb.retiredAt?.let { "بازنشسته شد ${jDate(it)}" },
                            )
                        },
                        style = Divan.type.caption, color = c.textMuted,
                    )
                },
                actions = {
                    if (pb.source.order.isNotBlank()) QuietLink("جلسه‌ای که از آن ساخته شد", { nav.go("session/${pb.source.order}") })
                    if (pb.sealed && served(HubFeature.LIBRARY)) {
                        // ⟨1.37⟩ §59.4 the page's act: one form for another company; adapting it in a session and retiring are in «کارها»
                        HqButton("در شرکت دیگر به کار ببر", { nav.go("playbook/${pb.ref}/use") }, variant = BtnVariant.SECONDARY, size = BtnSize.SM, icon = DivanIcon.SEND)
                    } else if (pb.sealed) {
                        HqButton("به شرکت دیگر بده", { sheet = PbSheet.APPLY }, variant = BtnVariant.SECONDARY, size = BtnSize.SM, icon = DivanIcon.SEND)
                        HqButton("بازنشسته کن", { sheet = PbSheet.RETIRE }, variant = BtnVariant.TEXT, size = BtnSize.SM)
                    }
                },
            )
            Box(Modifier.weight(1f)) {
                Page(onRefresh = r::refresh, refreshing = r.refreshing, state = listState) {
                    when {
                        pb == null && q.error != null -> item(key = "error") { ErrorBlock(q.error, { q.refresh() }) }
                        pb == null && !on -> item(key = "none") { Empty("کارگروه‌ها با به‌روزرسانی بعدی هاب میایند", icon = DivanIcon.DEPARTMENT) }
                        pb == null -> item(key = "sk") { Skeleton(Modifier.fillMaxWidth().height(420.dp), radius = 16.dp) }
                        else -> {
                            // What the drafter left out, said plainly (a note, not a warning).
                            pb.noteFa?.takeIf { it.isNotBlank() }?.let { note ->
                                item(key = "note") {
                                    HqCard(Modifier.fillMaxWidth(), padding = PaddingValues(12.dp)) {
                                        Text("چیزهایی که پیش‌نویس‌کننده کنار گذاشت", style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
                                        Para(note, Modifier.padding(top = 2.dp), style = Divan.type.caption, color = c.textSecondary)
                                    }
                                }
                            }
                            if (draft != null) {
                                item(key = "hint") { Hint(onSession = { nav.go("session/${pb.source.order}") }) }
                                // ⟨1.37⟩ §59.2 the flow and what it hands over, read here; changed in words in the session
                                if (pb.steps.isNotEmpty()) item(key = "flow") { FlowSection(pb) }
                                if (pb.`package`.isNotEmpty()) item(key = "package") { PackageSection(pb) }
                                if (pb.lessons.isNotEmpty()) item(key = "lessons") { LessonsFold(pb) }
                                if (pb.versions.size > 1) item(key = "versions") {
                                    VersionsSection(pb, here = pb.version, onOpen = { v -> nav.go("playbook/${pb.ref}/v/$v") }, onCompare = { sheet = PbSheet.COMPARE }) { v -> pickedVersion = v; sheet = PbSheet.USE_VERSION }
                                }
                                item(key = "draft") {
                                    DraftEditor(draft, standing = if (publishes(pb)) ({ StandingChoice(word, { word = it }, company = pb.source.company?.takeIf { !companyOf(companies, it).holding }) }) else null)
                                }
                            } else {
                                item(key = "members") {
                                    Column(Modifier.testTag("group-members"), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                                        SectionTitle("شرکت‌های عضو", note = if (pb.members.isEmpty()) "هنوز شرکتی عضو نیست" else null)
                                        MemberTiles(pb)
                                    }
                                }
                                if (pb.routines.isNotEmpty()) item(key = "routines") { RoutineRuns(pb) }
                                // ⟨1.37⟩ §59.1–§59.2 the flow step by step, the package, the lessons
                                if (pb.steps.isNotEmpty()) item(key = "flow") { FlowSection(pb) }
                                if (pb.`package`.isNotEmpty()) item(key = "package") { PackageSection(pb) }
                                if (pb.lessons.isNotEmpty()) item(key = "lessons") { LessonsFold(pb) }
                                // What the working group is: read when he wants it, folded until then.
                                item(key = "definition") {
                                    Fold("تعریف کارگروه", remember(pb) { facts(*sealSummary(pb.seats.size, pb.routines.size, pb.connections.size).toTypedArray()) }, tag = "group-definition") { Definition(pb) }
                                }
                                pb.group?.takeIf { pb.sealed }?.let { g ->
                                    item(key = "kpis") { QuietLink("شاخص‌ها و آزمایش هفته در «کارگروه‌ها»", { nav.go("groups/$g") }) }
                                }
                                item(key = "versions") {
                                    VersionsSection(pb, here = pb.version, onOpen = { v -> nav.go("playbook/${pb.ref}/v/$v") }, onCompare = { sheet = PbSheet.COMPARE }) { v -> pickedVersion = v; sheet = PbSheet.USE_VERSION }
                                }
                                if (library || pb.sealed) item(key = "acts") {
                                    PlaybookActs(pb, onCopy = { sheet = PbSheet.COPY }, onAdapt = { sheet = PbSheet.APPLY }, onRetire = { sheet = PbSheet.RETIRE })
                                }
                                if (pb.retired) item(key = "retired") {
                                    Text(
                                        plain("بازنشسته شد${pb.retiredAt?.let { " ${jDate(it)}" }.orEmpty()}؛ کارهای روتینش برای همه‌ی شرکت‌ها ایستاده است. چیزی پاک نشده."),
                                        style = Divan.type.caption, color = c.textMuted, modifier = Modifier.padding(horizontal = 4.dp),
                                    )
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    if (pb == null) return
    when (sheet) {
        PbSheet.NONE -> Unit
        PbSheet.APPLY -> com.coinepro.hq.ui.v14.HqSheet({ sheet = PbSheet.NONE }, "به شرکت دیگر بده", sub = "همین کارگروه برای شرکت دیگری، روی هر پلتفرمی.") {
            ApplyBody(pb, companies) { out, name ->
                sheet = PbSheet.NONE
                env.cache.invalidate("sessions", *PLAYBOOK_TAGS)
                val order = out.order
                if (order != null) {
                    toasts.ok("جلسه‌ی تازه برای $name باز شد.")
                    nav.go("session/$order")
                } else {
                    q.set(out.playbook)
                    toasts.ok("$name عضو کارگروه شد.")
                }
            }
        }
        PbSheet.RETIRE -> com.coinepro.hq.ui.v14.HqSheet({ sheet = PbSheet.NONE }, "این کارگروه بازنشسته شود؟", sub = "روال‌هایش برای همه‌ی شرکت‌های عضو می‌ایستد؛ چیزی پاک نمیشود.") {
            RetireBody(pb, onCancel = { sheet = PbSheet.NONE }) { out -> sheet = PbSheet.NONE; q.set(out) }
        }
        // ⟨1.37⟩ §59.1 copy for another platform, compare two versions, move a member to a version
        PbSheet.COPY -> com.coinepro.hq.ui.v14.HqSheet({ sheet = PbSheet.NONE }, "کپی برای پلتفرم دیگر", sub = "یک کارگروه تازه از روی همین روند.") {
            CopyBody(pb) { out, order ->
                sheet = PbSheet.NONE
                if (order != null) { toasts.ok("کپی ساخته شد و جلسه‌ی تطبیقش باز شد."); nav.go("session/$order") }
                else { toasts.ok("کپی ساخته شد؛ پیش‌نویسش را ببین."); nav.go("playbook/${out.ref}") }
            }
        }
        PbSheet.COMPARE -> com.coinepro.hq.ui.v14.HqSheet({ sheet = PbSheet.NONE }, "مقایسه‌ی نسخه‌ها", sub = "چه چیزی از یکی به دیگری عوض شده.") { CompareBody(pb) }
        PbSheet.USE_VERSION -> com.coinepro.hq.ui.v14.HqSheet({ sheet = PbSheet.NONE }, "استفاده از ${com.coinepro.hq.core.data.versionFa(pickedVersion)}", sub = "کدام شرکت؟") {
            UseVersionBody(pb, pickedVersion) { sheet = PbSheet.NONE; q.refresh() }
        }
    }
}

@Composable
private fun SubHead(text: String) = Text(text, style = Divan.type.micro.copy(fontWeight = FontWeight.SemiBold), color = Divan.colors.textMuted)

/** What a working group is, read whole: its goal, who, what and when, the figures it is judged by, its connections, its rules. */
@Composable
private fun Definition(pb: Playbook) {
    val c = Divan.colors
    if (pb.purposeFa.isNotBlank()) com.coinepro.hq.ui.Selectable { Para(pb.purposeFa, style = Divan.type.small, color = c.textPrimary) }
    if (pb.seats.isNotEmpty()) Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        SubHead("چه کسانی")
        for (s in pb.seats) SeatRow(s)
    }
    if (pb.routines.isNotEmpty()) Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        SubHead("چه کاری، کِی")
        var open by rememberSaveable(pb.ref) { mutableStateOf<String?>(null) }
        for (r in pb.routines) Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            RoutineLine(pb, r) {
                if (r.briefMd.isNotBlank()) IconBtn(DivanIcon.CHEVRON, if (open == r.key) "بستن" else "دستور کار", { open = if (open == r.key) null else r.key }, tint = c.textMuted)
            }
            Expand(open == r.key) {
                Box(Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(c.tile).padding(10.dp)) { com.coinepro.hq.ui.Selectable { Md(r.briefMd, color = c.textPrimary) } }
            }
        }
    }
    FiguresAndConnections(pb)
    if (pb.rulesFa.isNotEmpty()) Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        SubHead("قانون‌ها")
        for (rule in pb.rulesFa) RuleLine(rule)
    }
}

/** The figures a group is judged by and the connections each member needs (read only: they are set in the session). */
@Composable
private fun FiguresAndConnections(pb: Playbook) {
    val c = Divan.colors
    if (pb.kpis.isNotEmpty()) Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        SubHead("با چه عددی میسنجیم")
        for (k in pb.kpis) Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(plain(k.titleFa.ifBlank { k.key }), style = Divan.type.small, color = c.textPrimary, modifier = Modifier.weight(1f))
            if (k.unit.isNotBlank()) Text(plain(k.unit), style = Divan.type.micro, color = c.textMuted)
        }
    }
    if (pb.connections.isNotEmpty()) Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        SubHead("اتصال‌ها")
        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            for (k in pb.connections) Pill(com.coinepro.hq.core.data.connectionKindFa(k), Tone.NEUTRAL)
        }
    }
}

/**
 * A draft, lightly edited: its title, goal and platform, its seats and routines (each to take out; a routine's brief to change), its
 * rules, the figures and connections it carries, and his standing word for what it publishes. Its seal is the page's decision bar.
 */
@Composable
private fun DraftEditor(d: DraftEdit, standing: (@Composable () -> Unit)?) {
    val c = Divan.colors
    val pb = d.pb
    val edit = d.edit
    Column(Modifier.testTag("draft-editor"), verticalArrangement = Arrangement.spacedBy(14.dp)) {
        HqCard(Modifier.fillMaxWidth()) {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                SubHead("عنوان")
                HqTextField(edit.titleFa, { d.edit = d.edit.copy(titleFa = it) }, "نام کارگروه", Modifier.fillMaxWidth(), maxLength = 200)
                SubHead("هدف")
                HqTextField(edit.purposeFa, { d.edit = d.edit.copy(purposeFa = it) }, "هدفش در یکی دو جمله", Modifier.fillMaxWidth(), singleLine = false, minLines = 2, maxLength = 2000)
                SubHead("پلتفرم")
                ScrollRow { for (p in PB_PLATFORMS) FilterChip(pbPlatformFa(p), edit.platform == p, { d.edit = d.edit.copy(platform = p) }) }
            }
        }
        SeatsCard(edit) { seat -> d.edit = withoutSeat(d.edit, seat) }
        RoutinesCard(edit, onRemove = { k -> d.edit = d.edit.copy(routines = d.edit.routines.filter { it.key != k }) }) { k, brief ->
            d.edit = d.edit.copy(routines = d.edit.routines.map { if (it.key == k) it.copy(briefMd = brief) else it })
        }
        RulesCard(
            edit, onAdd = { d.edit = d.edit.copy(rulesFa = d.edit.rulesFa + "") }, onRemove = { i -> d.edit = d.edit.copy(rulesFa = d.edit.rulesFa.filterIndexed { j, _ -> j != i }) },
        ) { i, text -> d.edit = d.edit.copy(rulesFa = d.edit.rulesFa.mapIndexed { j, r -> if (j == i) text else r }) }
        if (pb.kpis.isNotEmpty() || pb.connections.isNotEmpty()) HqCard(Modifier.fillMaxWidth()) {
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) { FiguresAndConnections(pb) }
        }
        standing?.invoke()
        Text(
            "با مُهر تو کارگروه ساخته میشود و همین شرکت اولین عضوش؛ جایگاه‌ها به همان کسانی میرسد که در جلسه بودند و جای خالی با استخدام خودکار در سقف پاکت پر میشود.",
            style = Divan.type.micro, color = c.textMuted, modifier = Modifier.padding(horizontal = 4.dp),
        )
    }
}

/** A draft's hint: the main way to change it is to say it in its session. */
@Composable
private fun Hint(onSession: () -> Unit) {
    val c = Divan.colors
    Row(
        Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(c.tile).padding(start = 12.dp, end = 4.dp, top = 8.dp, bottom = 8.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        DIcon(DivanIcon.MESSAGES, size = 16.dp, tint = c.silverInk)
        Text(
            "راه اصلی تغییر این پیش‌نویس گفتن در خود جلسه است؛ مسئول جلسه آن را بازنویسی میکند. این‌جا فقط ویرایش سبک.",
            style = Divan.type.caption, color = c.textSecondary, modifier = Modifier.weight(1f),
        )
        HqButton("جلسه", onSession, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.NEXT)
    }
}

@Composable
private fun SeatsCard(pb: Playbook, onRemove: (String) -> Unit) {
    val c = Divan.colors
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("چه کسانی", note = if (pb.seats.isEmpty()) "جایگاهی نمانده" else "هر کدام را که نمیخواهی بردار")
        Column(Modifier.padding(top = 8.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            pb.seats.forEachIndexed { i, s ->
                if (i > 0) HorizontalDivider(color = c.lineDivider)
                SeatRow(s, onRemove = { onRemove(s.seat) })
            }
        }
    }
}

@Composable
private fun RoutinesCard(pb: Playbook, onRemove: (String) -> Unit, onBrief: (String, String) -> Unit) {
    val c = Divan.colors
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("چه کاری، کِی", note = if (pb.routines.isEmpty()) "روالی نمانده" else "شرح هر کار را میتوانی عوض کنی")
        Column(Modifier.padding(top = 8.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            pb.routines.forEachIndexed { i, r ->
                if (i > 0) HorizontalDivider(color = c.lineDivider)
                RoutineLine(pb, r) { IconBtn(DivanIcon.CLOSE, "این روال را بردار", { onRemove(r.key) }, tint = c.textMuted) }
                HqTextField(r.briefMd, { onBrief(r.key, it) }, "شرح کار هر نوبت", Modifier.fillMaxWidth(), singleLine = false, minLines = 2, maxLength = 4000)
            }
        }
    }
}

@Composable
private fun RulesCard(pb: Playbook, onAdd: () -> Unit, onRemove: (Int) -> Unit, onEdit: (Int, String) -> Unit) {
    val c = Divan.colors
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("قانون‌ها", note = "آنچه همه‌ی جایگاه‌ها رعایت میکنند") {
            HqButton("قانون تازه", onAdd, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.ADD)
        }
        Column(Modifier.padding(top = 8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            if (pb.rulesFa.isEmpty()) Text("قانونی نیست.", style = Divan.type.caption, color = c.textMuted)
            pb.rulesFa.forEachIndexed { i, rule ->
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    HqTextField(rule, { onEdit(i, it) }, "متن قانون", Modifier.weight(1f), singleLine = false, maxLength = 500)
                    IconBtn(DivanIcon.CLOSE, "این قانون را بردار", { onRemove(i) }, tint = c.textMuted)
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
        Expand(standing) { StandingChoice(word, { word = it }, company = company) }
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
        // ⟨1.0.1⟩ C0.2: the sheet's one act, stuck to its bottom, with what it does in one line.
        com.coinepro.hq.designsystem.SheetBar {
            com.coinepro.hq.designsystem.DecisionBar(
                if (asIs) "عضوش کن" else "بده", {
                    val co = company ?: return@DecisionBar
                    go.run { onApplied(env.api.applyWithWord(pb.ref, co, platform, note, asIs, key, word.takeIf { standing }), name ?: co) }
                },
                context = if (asIs) "همین کارگروه، همان‌طور که هست، عضوی تازه میگیرد." else "مسئول آن شرکت جلسه‌ای تازه باز میکند و کارگروه را تطبیق میدهد.",
                icon = if (asIs) DivanIcon.ADD else DivanIcon.SEND, enabled = company != null,
                state = if (go.busy) com.coinepro.hq.designsystem.DecisionState.WORKING else com.coinepro.hq.designsystem.DecisionState.IDLE,
            )
        }
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
        else "در ${pb.members.size} شرکت کار میکند؛ همه‌جا می‌ایستد. جلسه‌ها، کارها و خروجی‌هایش میمانند.",
        style = Divan.type.small, color = c.textSecondary,
    )
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        HqButton("بازنشسته کن", {
            go.run {
                val out = env.api.retirePlaybook(pb.ref) { a, t -> env.auth.stepUp(act, a, t) }
                env.cache.invalidate(*PLAYBOOK_TAGS)
                toasts.ok("بازنشسته شد؛ کارهای روتینش ایستاد.")
                onDone(out)
            }
        }, Modifier.weight(1f), variant = BtnVariant.DANGER, size = BtnSize.LG, icon = DivanIcon.PAUSE, loading = go.busy)
        HqButton("نه", onCancel, variant = BtnVariant.TEXT, size = BtnSize.LG)
    }
}

/** The standing word across a rotation: `mode`, `story`, the hour and «بهترین ساعت» (the account is asked by the hub when there are several). */
internal val StandingSaver = androidx.compose.runtime.saveable.Saver<MemberPublish, List<Any>>(
    save = { listOf(it.mode, it.story, it.at.orEmpty(), it.best) },
    restore = { MemberPublish(mode = it[0] as String, story = it[1] as Boolean, at = (it[2] as String).ifBlank { null }, best = it.getOrNull(3) as? Boolean ?: false) },
)

