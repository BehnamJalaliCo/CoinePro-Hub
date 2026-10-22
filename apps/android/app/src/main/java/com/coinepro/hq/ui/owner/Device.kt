package com.coinepro.hq.ui.owner

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.coinepro.hq.core.AppGraph
import com.coinepro.hq.designsystem.BtnSize
import com.coinepro.hq.designsystem.BtnVariant
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.HqButton
import com.coinepro.hq.designsystem.HqCard
import com.coinepro.hq.designsystem.HqSwitch
import com.coinepro.hq.designsystem.Monogram
import com.coinepro.hq.designsystem.SectionTitle
import com.coinepro.hq.designsystem.generated.DivanIcon
import com.coinepro.hq.ui.activity

/** The locked app (M11): nothing of the holding shows until the phone's owner is verified. */
@Composable
fun LockScreen(graph: AppGraph) {
    val c = Divan.colors
    val act = activity()
    var error by remember { mutableStateOf<String?>(null) }
    val open = { graph.lock.unlock(act) { error = it } }
    LaunchedEffect(Unit) { open() }
    Column(Modifier.fillMaxSize().padding(32.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
        Monogram(56.dp)
        Spacer(Modifier.height(20.dp))
        Text("ستاد قفل است", style = Divan.type.h2)
        Text("با اثر انگشت، چهره یا قفل گوشی باز میشود.", style = Divan.type.small, color = c.textSecondary, textAlign = TextAlign.Center)
        error?.let { Text(it, style = Divan.type.caption, color = c.negative, textAlign = TextAlign.Center, modifier = Modifier.padding(top = 8.dp)) }
        Spacer(Modifier.height(24.dp))
        HqButton("باز کردن", { open() }, Modifier.fillMaxWidth(), variant = BtnVariant.PRIMARY, size = BtnSize.LG, icon = DivanIcon.LOCK)
    }
}

/** The app lock switch (M11), shown only when the phone has a secure lock screen to verify with. */
@Composable
fun AppLockCard(graph: AppGraph) {
    val c = Divan.colors
    var on by remember { mutableStateOf(graph.prefs.appLock.value) }
    HqCard(Modifier.fillMaxWidth()) {
        SectionTitle("قفل اپ", note = "هنگام باز شدن و بعد از یک دقیقه بیرون بودن؛ محتوا در فهرست برنامه‌های اخیر پنهان است.")
        if (!graph.lock.available()) Text("روی این گوشی قفل صفحه تعریف نشده؛ قفل اپ بدون آن کار نمیکند.", style = Divan.type.caption, color = c.textMuted, modifier = Modifier.padding(top = 8.dp))
        else Row(Modifier.fillMaxWidth().padding(top = 10.dp), verticalAlignment = Alignment.CenterVertically) {
            Text(if (on) "روشن: با اثر انگشت، چهره یا قفل گوشی" else "خاموش", style = Divan.type.small, modifier = Modifier.weight(1f))
            HqSwitch(on, { on = it; graph.lock.setEnabled(it) }, "قفل اپ")
        }
    }
}
