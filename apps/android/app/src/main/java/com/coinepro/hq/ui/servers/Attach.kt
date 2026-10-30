package com.coinepro.hq.ui.servers

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.background
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.AttachIn
import com.coinepro.hq.core.net.AttachOut
import com.coinepro.hq.core.net.AttachRules
import com.coinepro.hq.core.net.HubServer
import com.coinepro.hq.core.net.serverError
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.DIcon
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.FilterChip
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.HqTextField
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

/** «وصل کردن سرور» (§26.4 `POST /infra/servers/attach`, 🔏 `server.attach` on `company:<CODE>`): who, where, as whom and its host key; then
 *  the hub's public key line to hand to that server's own Claude; then the wait until the hub reaches it. */
@Composable
fun AttachScreen(company0: String? = null, form0: AttachIn? = null, out0: AttachOut? = null, tried0: Boolean = false) {
    var out by remember { mutableStateOf(out0) }
    val servers = rememberServers()
    val reached = out?.server?.id?.let { id -> servers.data?.firstOrNull { it.id == id }?.reachable } == true
    Page {
        item(key = "header") { PageHeader("وصل کردن سرور", eyebrow = "سرور یک شرکت، زیر کنترل ستاد") }
        item(key = "steps") { Steps(if (out == null) 1 else if (reached) 3 else 2) }
        item(key = "body") {
            val o = out
            if (o == null) AttachForm(company0, form0, tried0) { out = it } else KeyStep(o)
        }
    }
}

@Composable
private fun Steps(at: Int) {
    val c = Divan.colors
    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
        listOf("نشانی و کلید میزبان", "کلید هاب روی سرور", "در دسترس").forEachIndexed { i, t ->
            val n = i + 1
            Box(Modifier.size(22.dp).clip(CircleShape).background(if (n <= at) c.goldFill else c.tile), contentAlignment = Alignment.Center) {
                Text("$n", style = Divan.type.micro.copy(fontWeight = FontWeight.Bold), color = if (n <= at) c.onGold else c.textMuted)
            }
            Text(t, style = Divan.type.micro, color = if (n == at) c.textPrimary else c.textMuted, maxLines = 1)
        }
    }
}

@Composable
private fun AttachForm(company0: String?, form0: AttachIn?, tried0: Boolean, onDone: (AttachOut) -> Unit) {
    val env = LocalEnv.current
    val toasts = LocalToasts.current
    val act = activity()
    val c = Divan.colors
    val companies = rememberCompanies().filter { it.kind != "holding" && it.status != "archived" }
    val existing = rememberServers().data.orEmpty()
    val action = rememberAction()
    var company by rememberSaveable { mutableStateOf(form0?.company ?: company0) }
    var name by rememberSaveable { mutableStateOf(form0?.name.orEmpty()) }
    var ip by rememberSaveable { mutableStateOf(form0?.privateIp.orEmpty()) }
    var user by rememberSaveable { mutableStateOf(form0?.user.orEmpty()) }
    var key by rememberSaveable { mutableStateOf(form0?.hostKeySha256.orEmpty()) }
    var tried by rememberSaveable { mutableStateOf(tried0) }
    var server by remember { mutableStateOf<Map<String, String>>(emptyMap()) }
    val form = AttachIn(company.orEmpty(), name, ip, user, key)
    val errors = AttachRules.validate(form, existing) + server
    fun err(k: String) = if (tried || (k != "company" && fieldOf(form, k).isNotBlank())) errors[k] else null

    HqCard(Modifier.fillMaxWidth()) {
        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text("کدام شرکت", style = Divan.type.caption, color = c.textMuted)
            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                for (co in companies) FilterChip(co.nameFa ?: co.code, company == co.code, { company = co.code; server = server - "company" })
            }
            err("company")?.let { FieldError(it) }
            Field("نام سرور", name, { name = it.lowercase(); server = server - "name" }, "fx-main", err("name"))
            Field("آدرس خصوصی", ip, { ip = it; server = server - "private_ip" }, "10.10.1.2", err("private_ip"))
            Field("کاربر کاری", user, { user = it; server = server - "user" }, "forex", err("user"))
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("اثر کلید میزبان", style = Divan.type.caption, color = c.textMuted)
                Text("روی خود سرور، خروجی این را بچسبان (کل خط هم قبول است):", style = Divan.type.micro, color = c.textMuted)
                CopyBox("ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub", prefix = "$ ")
                Ltr { HqTextField(key, { key = it; server = server - "host_key_sha256" }, "SHA256:…", Modifier.fillMaxWidth(), singleLine = false, minLines = 2, figure = true) }
                AttachRules.hostKey(key)?.let { Text(buildAnnotatedString { append("خوانده شد: "); fig(it) }, style = Divan.type.micro, color = c.positive) }
                err("host_key_sha256")?.let { FieldError(it) }
            }
        }
    }
    HqButton(
        "با گذرکلید وصل کن", {
            tried = true
            if (AttachRules.validate(form, existing).isEmpty()) action.run(onError = { e: ApiException ->
                if (e.fields.isNotEmpty()) server = e.fields
                toasts.error(serverError(e))
            }) {
                val o = env.api.attachServer(AttachRules.body(form)) { a, t -> env.auth.stepUp(act, a, t) }
                env.cache.invalidate("servers")
                onDone(o)
            }
        },
        Modifier.fillMaxWidth().padding(top = 14.dp), variant = BtnVariant.PRIMARY, size = BtnSize.LG, icon = DivanIcon.SEAL, loading = action.busy,
    )
    Text("هاب فقط از شبکه‌ی خصوصی و با کاربر کاری همان سرور وارد میشود؛ کلید میزبان همین حالا pin میشود و اگر روزی عوض شود هیچ فرمانی اجرا نمیشود.", Modifier.padding(top = 10.dp), style = Divan.type.micro, color = c.textMuted)
}

private fun fieldOf(f: AttachIn, k: String): String = when (k) {
    "name" -> f.name; "private_ip" -> f.privateIp; "user" -> f.user; "host_key_sha256" -> f.hostKeySha256; else -> f.company
}

@Composable
private fun Field(label: String, value: String, onChange: (String) -> Unit, example: String, error: String?) {
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Text(label, style = Divan.type.caption, color = Divan.colors.textMuted)
        Ltr { HqTextField(value, { onChange(it.trim()) }, example, Modifier.fillMaxWidth(), figure = true, maxLength = 64) }
        error?.let { FieldError(it) }
    }
}

@Composable
private fun FieldError(text: String) = Text(isolated(text), style = Divan.type.caption, color = Divan.colors.negative)

private val LATIN_RUN = Regex("[A-Za-z0-9][A-Za-z0-9.:/_\\-–]*")

/** A Persian sentence with addresses and keys in it ("10.x", "SHA256:"): each Latin run set Latin and isolated left to right, so the
 *  bidi algorithm never turns `SHA256:` into `256:SHA`. */
internal fun isolated(text: String): androidx.compose.ui.text.AnnotatedString = buildAnnotatedString {
    var last = 0
    for (m in LATIN_RUN.findAll(text)) {
        append(text.substring(last, m.range.first))
        fig("\u2066${m.value}\u2069")
        last = m.range.last + 1
    }
    append(text.substring(last))
}

/** An address, a user or a key: typed and read left to right inside the right-to-left form. */
@Composable
private fun Ltr(content: @Composable () -> Unit) =
    androidx.compose.runtime.CompositionLocalProvider(androidx.compose.ui.platform.LocalLayoutDirection provides androidx.compose.ui.unit.LayoutDirection.Ltr, content = content)

/** Text the owner copies to hand on: left to right, monospace, wrapped, one tap copies it. */
@Composable
fun CopyBox(text: String, prefix: String? = null) {
    val ctx = LocalContext.current
    val toasts = LocalToasts.current
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        CodeBlock(text, prefix = prefix, wrap = prefix == null)
        HqButton("کپی", {
            (ctx.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager).setPrimaryClip(ClipData.newPlainText("hq", text))
            toasts.ok("کپی شد.")
        }, variant = BtnVariant.TEXT, size = BtnSize.SM, icon = DivanIcon.DELIVERABLE)
    }
}

@Composable
private fun KeyStep(o: AttachOut) {
    val env = LocalEnv.current
    val nav = LocalNav.current
    val ctx = LocalContext.current
    val c = Divan.colors
    val servers = rememberServers()
    val line = AttachRules.authorizedLine(o.publicKey)
    val now: HubServer? = servers.data?.firstOrNull { it.id == o.server?.id } ?: o.server
    val reachable = now?.reachable == true
    // The hub tries to reach the server on its own; the app asks again every few seconds until it can.
    LaunchedEffect(reachable) {
        while (!reachable) { delay(3_000); env.cache.invalidate("servers") }
    }
    Column(verticalArrangement = Arrangement.spacedBy(14.dp)) {
        HqCard(Modifier.fillMaxWidth()) {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text("کلید هاب برای ${now?.name ?: "این سرور"}", style = Divan.type.bodyStrong)
                Text("این را به Claude همان سرور بده همراه فایل COMPANY_SERVER_ACCESS_SETUP.md", style = Divan.type.small, color = c.textPrimary)
                CopyBox(line)
                Text("این کلید عمومی است، نه رمز؛ کلید خصوصی‌اش فقط در OpenBao هاب میماند. Claude آن سرور آن را به authorized_keys کاربر ${now?.user ?: "کاری"} اضافه میکند و گزارش میدهد.", style = Divan.type.micro, color = c.textMuted)
                HqButton("فرستادن به Claude", {
                    val text = "این کلید هاب ستاد است؛ طبق COMPANY_SERVER_ACCESS_SETUP.md به authorized_keys کاربر ${now?.user.orEmpty()} اضافه کن:\n\n$line"
                    ctx.startActivity(Intent.createChooser(Intent(Intent.ACTION_SEND).setType("text/plain").putExtra(Intent.EXTRA_TEXT, text), "فرستادن کلید"))
                }, variant = BtnVariant.SECONDARY, size = BtnSize.SM, icon = DivanIcon.SHARE)
            }
        }
        HqCard(Modifier.fillMaxWidth(), color = if (reachable) c.softPositive else c.card) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                if (reachable) DIcon(DivanIcon.SEAL, size = 22.dp, tint = c.positive)
                else if (!com.coinepro.hq.designsystem.LocalReducedMotion.current) CircularProgressIndicator(Modifier.size(20.dp), color = c.goldInk, strokeWidth = 2.dp)
                else DIcon(DivanIcon.TIME, size = 20.dp, tint = c.goldInk)
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    Text(if (reachable) "وصل شد؛ ${now?.name} در دسترس است" else "منتظرم هاب به سرور برسد…", style = Divan.type.small.copy(fontWeight = FontWeight.SemiBold))
                    Text(if (reachable) "اولین نقشه گرفته شد؛ ایجنت‌ها از همین حالا میتوانند رویش کار کنند." else "همین که کلید روی سرور نشست، اینجا خودش «در دسترس» میشود. لازم نیست صفحه باز بماند.", style = Divan.type.caption, color = c.textSecondary)
                }
            }
            if (reachable && now != null) HqButton("باز کردن سرور", { nav.go("servers/${now.id}") }, Modifier.fillMaxWidth().padding(top = 12.dp), variant = BtnVariant.PRIMARY, icon = DivanIcon.SERVER)
        }
    }
}
