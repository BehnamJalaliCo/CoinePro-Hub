package com.coinepro.hq.ui.servers

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsFocusedAsState
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.CircularProgressIndicator
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
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.TextRange
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.TextFieldValue
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.HubServer
import com.coinepro.hq.core.net.PairCode
import com.coinepro.hq.core.net.serverError
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.PageHeader
import com.coinepro.hq.designsystem.fig
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Page
import com.coinepro.hq.ui.activity
import com.coinepro.hq.ui.rememberAction
import com.coinepro.hq.ui.rememberCompanies
import kotlinx.coroutines.delay

/**
 * «وصل کردن سرور» (§26.1, device-authorisation pairing): on the server, its own Claude installs `hq-runner` and runs `hq-runner pair`,
 * which prints a short code; the owner types that code here and approves it with the passkey (`POST /runners/approve {user_code}`,
 * 🔏 `server.attach` on `company:<CODE>`). Then the new server, waiting until its runner takes its token and turns `online`. Nothing secret
 * is shown: no key, no token, no address to open.
 */
@Composable
fun AttachScreen(company0: String? = null, code0: String = "", error0: String? = null, out0: HubServer? = null) {
    var out by remember { mutableStateOf(out0) }
    Page {
        item(key = "header") { PageHeader("وصل کردن سرور", eyebrow = "سرور یک شرکت، زیر کنترل ستاد") }
        item(key = "body") {
            val o = out
            if (o == null) PairForm(company0, code0, error0) { out = it } else WaitStep(o)
        }
    }
}

/** One numbered step of the three: done ones gold. */
@Composable
private fun StepRow(n: Int, done: Boolean, content: @Composable () -> Unit) {
    val c = Divan.colors
    Row(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.Top) {
        Box(Modifier.padding(top = 1.dp).size(22.dp).clip(CircleShape).background(if (done) c.goldFill else c.tile), contentAlignment = Alignment.Center) {
            Text("$n", style = Divan.type.micro.copy(fontWeight = FontWeight.Bold), color = if (done) c.onGold else c.textMuted)
        }
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(6.dp)) { content() }
    }
}

@Composable
private fun PairForm(company0: String?, code0: String, error0: String?, onDone: (HubServer) -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val act = activity()
    val ctx = LocalContext.current
    val c = Divan.colors
    val companies = rememberCompanies().filter { it.kind != "holding" && it.status != "archived" }
    val action = rememberAction()
    var company by rememberSaveable { mutableStateOf(company0) }
    var code by rememberSaveable { mutableStateOf(PairCode.format(code0)) }
    var error by rememberSaveable { mutableStateOf(error0) }
    val cmd = PairCode.pairCommand(company)
    val ready = company != null && PairCode.valid(code)

    HqCard(Modifier.fillMaxWidth()) {
        Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Text("کدام شرکت", style = Divan.type.caption, color = c.textMuted)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                for (co in companies) FilterChip(co.nameFa ?: co.code, company == co.code, { company = co.code; error = null })
            }
            StepRow(1, done = true) {
                Text(isolated("روی سرور: Claude همان سرور hq-runner را طبق COMPANY_SERVER_ACCESS_SETUP.md با کاربر کاری‌اش نصب میکند."), style = Divan.type.small, color = c.textPrimary)
                HqButton("فرستادن به Claude سرور", {
                    val text = "طبق COMPANY_SERVER_ACCESS_SETUP.md از ریپوی ستاد، hq-runner را با کاربر کاری همین سرور نصب کن و بعد این را اجرا کن؛ کدی را که نشان میدهد به من بگو:\n\n$cmd"
                    ctx.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).setType("text/plain").putExtra(Intent.EXTRA_TEXT, text), "فرستادن به Claude سرور"))
                }, variant = BtnVariant.SECONDARY, size = BtnSize.SM, icon = DivanIcon.SHARE)
            }
            StepRow(2, done = true) {
                Text("همان‌جا جفت میکند و یک کد کوتاه نشان میدهد:", style = Divan.type.small, color = c.textPrimary)
                CopyBox(cmd, prefix = "$ ", wrap = true)
            }
            StepRow(3, done = ready) {
                Text("کد را اینجا بنویس و با گذرکلید تأیید کن.", style = Divan.type.small, color = c.textPrimary)
                CodeField(code, { code = it; error = null }, error != null)
                when {
                    error != null -> FieldError(error!!)
                    code.isNotEmpty() && !PairCode.valid(code) -> Text(isolated("هشت حرف و رقم لاتین، مثل ABCD-1234"), style = Divan.type.caption, color = c.textMuted)
                    company == null && code.isNotEmpty() -> Text("شرکتی را که کد برایش ساخته شده انتخاب کن.", style = Divan.type.caption, color = c.textMuted)
                }
            }
        }
    }
    HqButton(
        "تأیید با گذرکلید", {
            val co = company ?: return@HqButton
            action.run(onError = { e: ApiException ->
                val why = PairCode.refusal(e)
                if (why != null) error = why else toasts.error(serverError(e))
            }) {
                val s = env.api.approveRunner(co, code) { a, t -> env.auth.stepUp(act, a, t) }
                env.cache.invalidate("servers")
                onDone(s)
            }
        },
        Modifier.fillMaxWidth().padding(top = 14.dp), variant = BtnVariant.PRIMARY, size = BtnSize.LG, icon = DivanIcon.SEAL, enabled = ready, loading = action.busy,
    )
    Text(
        isolated("runner خودش با HTTPS به هاب وصل میشود؛ هاب به سرور وارد نمیشود، پورتی باز نمیشود و هیچ رمز یا کلیدی از اینجا رد نمیشود. هر کد ۱۵ دقیقه اعتبار دارد."),
        Modifier.padding(top = 10.dp), style = Divan.type.micro, color = c.textMuted,
    )
}

/** The code, typed as the server shows it: Latin, upper case, the dash put in after the fourth character, the cursor kept at the end. */
@Composable
private fun CodeField(code: String, onChange: (String) -> Unit, bad: Boolean) {
    val c = Divan.colors
    val src = remember { MutableInteractionSource() }
    val focused by src.collectIsFocusedAsState()
    val shape = RoundedCornerShape(12.dp)
    var tfv by remember { mutableStateOf(TextFieldValue(code, TextRange(code.length))) }
    if (tfv.text != code) tfv = TextFieldValue(code, TextRange(code.length))
    val style = Divan.type.figureM.copy(color = c.textPrimary, textAlign = TextAlign.Center, letterSpacing = 3.sp)
    Ltr {
        BasicTextField(
            value = tfv,
            onValueChange = {
                val f = PairCode.format(it.text)
                // As typed when nothing changed; formatted (a dash in, a letter up), the cursor goes to the end.
                tfv = if (f == it.text) it else TextFieldValue(f, TextRange(f.length))
                if (f != code) onChange(f)
            },
            modifier = Modifier.fillMaxWidth().semantics { contentDescription = "کد جفت‌سازی" },
            singleLine = true,
            interactionSource = src,
            textStyle = style,
            cursorBrush = SolidColor(c.goldInk),
            keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Characters, autoCorrectEnabled = false, keyboardType = KeyboardType.Ascii, imeAction = ImeAction.Done),
            decorationBox = { inner ->
                Box(
                    Modifier.fillMaxWidth().clip(shape).background(c.tile)
                        .border(if (focused || bad) 1.5.dp else 1.dp, if (bad) c.negative else if (focused) c.goldInk else c.lineStrong, shape)
                        .padding(horizontal = 12.dp, vertical = 14.dp),
                    contentAlignment = Alignment.Center,
                ) {
                    if (code.isEmpty()) Text("ABCD-1234", style = style.copy(color = c.textMuted))
                    inner()
                }
            },
        )
    }
}

@Composable
private fun FieldError(text: String) = Text(isolated(text), style = Divan.type.caption, color = Divan.colors.negative)

private const val LATIN_WORD = "[A-Za-z0-9](?:[A-Za-z0-9.:/_\\-–]*[A-Za-z0-9])?"
private val LATIN_RUN = Regex("$LATIN_WORD(?: $LATIN_WORD)*")

/** A Persian sentence with commands and file names in it ("hq-runner status", "SETUP.md"): each Latin run — several words of a command
 *  together, a sentence's full stop left out — set Latin and isolated left to right, so the bidi algorithm never reorders it. */
internal fun isolated(text: String): androidx.compose.ui.text.AnnotatedString = buildAnnotatedString {
    var last = 0
    for (m in LATIN_RUN.findAll(text)) {
        append(text.substring(last, m.range.first))
        fig("⁦${m.value}⁩")
        last = m.range.last + 1
    }
    append(text.substring(last))
}

/** A command or a code: typed and read left to right inside the right-to-left form. */
@Composable
private fun Ltr(content: @Composable () -> Unit) =
    androidx.compose.runtime.CompositionLocalProvider(androidx.compose.ui.platform.LocalLayoutDirection provides androidx.compose.ui.unit.LayoutDirection.Ltr, content = content)

/** Text the owner copies to hand on: left to right, monospace, wrapped, one tap copies it. */
@Composable
fun CopyBox(text: String, prefix: String? = null, wrap: Boolean = prefix == null) {
    val ctx = LocalContext.current
    val toasts = LocalToasts.current
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        CodeBlock(text, prefix = prefix, wrap = wrap)
        HqButton("کپی", {
            (ctx.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager).setPrimaryClip(ClipData.newPlainText("hq", text))
            toasts.ok("کپی شد.")
        }, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.DELIVERABLE)
    }
}

/** After the approval: the new server as the hub now lists it, and the wait until its runner polls and turns `online`. */
@Composable
private fun WaitStep(o: HubServer) {
    val env = LocalEnv.current
    val nav = LocalNav.current
    val c = Divan.colors
    val servers = rememberServers()
    val now: HubServer = servers.data?.firstOrNull { it.id == o.id } ?: o
    val online = now.online
    // The runner takes its token on its next poll (every few seconds); the app asks again until the server is online.
    LaunchedEffect(online) {
        while (!online) { delay(3_000); env.cache.invalidate("servers") }
    }
    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        HqCard(Modifier.fillMaxWidth(), color = c.softPositive) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                DIcon(DivanIcon.SEAL, size = 20.dp, tint = c.positive)
                Text(buildAnnotatedString { append("کد تأیید شد؛ "); fig(now.name); append(" به ستاد پیوست.") }, style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold), color = c.textPrimary)
            }
        }
        ServerCard(now, locked = rememberLocked(now.company), showCompany = true) { nav.go("servers/${now.id}") }
        HqCard(Modifier.fillMaxWidth(), color = if (online) c.softPositive else c.card) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                if (online) DIcon(DivanIcon.SEAL, size = 22.dp, tint = c.positive)
                else if (!com.coinepro.hq.designsystem.LocalReducedMotion.current) CircularProgressIndicator(Modifier.size(20.dp), color = c.goldInk, strokeWidth = 2.dp)
                else DIcon(DivanIcon.TIME, size = 20.dp, tint = c.goldInk)
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    Text(if (online) "آنلاین شد" else "منتظرم runner تماس بگیرد…", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold))
                    Text(
                        if (online) "runner کار میگیرد و اولین نقشه گرفته میشود؛ ایجنت‌ها از همین حالا میتوانند رویش کار کنند."
                        else "runner در تماس بعدی‌اش اعتبار خودش را میگیرد و سرور «آنلاین» میشود، معمولاً در چند ثانیه. لازم نیست صفحه باز بماند.",
                        style = Divan.type.caption, color = c.textSecondary,
                    )
                }
            }
            if (online) HqButton("باز کردن سرور", { nav.go("servers/${now.id}") }, Modifier.fillMaxWidth().padding(top = 12.dp), variant = BtnVariant.PRIMARY, icon = DivanIcon.SERVER)
        }
    }
}
