package com.coinepro.hq

import android.content.ClipboardManager
import android.content.Context
import androidx.activity.ComponentActivity
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.test.junit4.v2.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.test.core.app.ApplicationProvider
import com.coinepro.hq.core.format.plainOfMd
import com.coinepro.hq.core.net.TalkTurn
import com.coinepro.hq.designsystem.DivanTheme
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Toasts
import com.coinepro.hq.ui.copyText
import com.coinepro.hq.ui.v32.TalkBubble
import com.coinepro.hq.ui.v32.turnPlain
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * The owner, 2026-11-06: «نمیتونم متن خروجی سشن رو کپی کنم». A turn's «کپی» puts the whole of it on the clipboard as plain words (the
 * markdown marks gone, the words of a link kept) and says «کپی شد»; the owner's own words go as he wrote them.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [35])
class CopyTextTest {
    @get:Rule
    val compose = createAndroidComposeRule<ComponentActivity>()

    private val clipboard get() = ApplicationProvider.getApplicationContext<Context>().getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager

    @Test
    fun markdownLosesItsMarksAndKeepsItsWords() {
        val md = "## برنامه‌ی هفته\n\n**سه ریلز** و *دو پست*؛ متن در `brief.md`.\n\n- ریلز اول\n* ریلز دوم\n\n> نقل قول\n\n[صفحه‌ی فرود](https://example.com/x) را ببین.\n```\ncode\n```\n~~کهنه~~"
        assertEquals(
            "برنامه‌ی هفته\n\nسه ریلز و دو پست؛ متن در brief.md.\n\n- ریلز اول\n- ریلز دوم\n\nنقل قول\n\nصفحه‌ی فرود را ببین.\ncode\nکهنه",
            plainOfMd(md),
        )
        // A star inside a figure or a word is not emphasis.
        assertEquals("2*3 = 6", plainOfMd("2*3 = 6"))
    }

    @Test
    fun aTurnIsCopiedAsPlainWords() {
        assertEquals("سلام **تو**", turnPlain(TalkTurn(by = "owner", text = " سلام **تو** ")))
        assertEquals("گزارش آماده است: درآمد ۱۲٪ بالاتر.", turnPlain(TalkTurn(by = "advisor", showMd = "گزارش آماده است: **درآمد ۱۲٪ بالاتر**.")))
        assertTrue(copyText(ApplicationProvider.getApplicationContext(), "x"))
        assertEquals("x", clipboard.primaryClip?.getItemAt(0)?.text?.toString())
    }

    @Test
    fun theBubblesCopyPutsTheWholeTurnOnTheClipboardAndSaysSo() {
        val graph = ApplicationProvider.getApplicationContext<HqApp>().graph
        graph.enterDemo()
        val toasts = Toasts()
        compose.setContent {
            DivanTheme(false) {
                CompositionLocalProvider(LocalEnv provides graph.env.value, LocalToasts provides toasts) {
                    TalkBubble(
                        TalkTurn(by = "ceo@TY", showMd = "سه ریلز آماده شد؛ **سؤال:** اول ریلزها منتشر شود یا پست‌ها؟", at = "2026-11-06T08:24:00Z"),
                        null, emptyList(), true, null, { _, _ -> }, { },
                    )
                }
            }
        }
        compose.onNodeWithText("کپی").performClick()
        compose.waitForIdle()
        assertEquals("سه ریلز آماده شد؛ سؤال: اول ریلزها منتشر شود یا پست‌ها؟", clipboard.primaryClip?.getItemAt(0)?.text?.toString())
        assertEquals(listOf("کپی شد."), toasts.items.map { it.text })
    }
}
