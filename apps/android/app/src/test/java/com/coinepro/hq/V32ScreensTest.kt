package com.coinepro.hq

import android.os.Looper
import androidx.activity.ComponentActivity
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.Modifier
import androidx.compose.ui.test.junit4.v2.createAndroidComposeRule
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.unit.dp
import androidx.test.core.app.ApplicationProvider
import com.coinepro.hq.core.AppGraph
import com.coinepro.hq.core.data.HandsFree
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.TalkCard
import com.coinepro.hq.core.net.TalkPersona
import com.coinepro.hq.core.net.TalkVoicePick
import com.coinepro.hq.core.net.VoiceEngine
import com.coinepro.hq.core.net.VoiceMeter
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.DivanTheme
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Nav
import com.coinepro.hq.ui.Toasts
import com.coinepro.hq.ui.v32.HoldUi
import com.coinepro.hq.ui.v32.Phase
import com.github.takahirom.roborazzi.RoborazziOptions
import com.github.takahirom.roborazzi.captureRoboImage
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.ParameterizedRobolectricTestRunner
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

/**
 * ⟨1.14⟩ Contract §32, night and day, with the demo holding, drawn tall (1600dp): the talk screen with the secretary (a spoken turn, an
 * order card offered and one done) and the work room with the CEO brought in (a hire card and the minutes with its tasks, open for
 * editing), the held mic and hands-free, the key's sheet (a key caught in the composer, the light waiting, the light failing with its
 * reason, the cap asked on the first key), the meter and its prices, the voices, «+», the light's reason, and the list of conversations.
 */
@RunWith(ParameterizedRobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [35], qualifiers = "w400dp-h1600dp-xxhdpi")
class V32ScreensTest(private val name: String, private val night: Boolean) {
    companion object {
        /** A key-shaped string made at run time: no key-like text is written in the source. */
        private val CAUGHT = "AI" + "za" + "x".repeat(35)

        private val FLASH = "gemini-3.8-flash-tts"
        private val LITE = "gemini-3.8-flash-lite-tts"

        private fun persona(key: String, title: String, engine: String, voice: String, role: String = "", company: String? = null) =
            TalkPersona(key = key, role = role, titleFa = title, company = company, voice = TalkVoicePick(engine, voice))

        private val PERSONAS = listOf(
            persona("secretary", "منشی هلدینگ", FLASH, "Kore"),
            persona("overseer", "ناظر کل", LITE, "Charon"),
            persona("assistant", "دستیار شخصی", "piper", "fa-male-1"),
            persona("advisor", "مشاور کل", FLASH, "Orus"),
            persona("manager", "مدیرعامل تریدیار", FLASH, "Puck", role = "ceo", company = "TY"),
        )

        private fun engine(key: String, title: String, state: String, reason: String? = null) =
            Api.json.decodeFromString(VoiceEngine.serializer(), """{"key":"$key","title_fa":"$title","provider":"${if (key == "piper") "local" else "google"}","state":"$state","reason_fa":${reason?.let { "\"$it\"" } ?: "null"}}""")

        private val CARD_MINUTES = Api.json.decodeFromString(
            TalkCard.serializer(),
            """{"id":"TC-202","kind":"minutes","title_fa":"صورت‌جلسه‌ی هفته‌ی آموزش طلا","body_fa":"خلاصه، تصمیم‌ها و دو کار؛ موعد و دپارتمان را عوض کن، بعد اجرا کن.","state":"offered","payload":{"summary_fa":"درباره‌ی هفته‌ی آموزش طلا و بودجه‌ی تبلیغ حرف زدیم.","decisions":["هفته‌ی آموزش طلا از شنبه شروع میشود","ریلزها پیش از انتشار برای مدیر کل میآید"],"tasks":[{"title_fa":"سه ریلز آموزشی طلا بسازید","company":"TY","department":"MEDIA","due":"شنبه"},{"title_fa":"گزارش بازده تبلیغ هفته را بفرستید","company":"TY","department":"GROWTH","due":"چهارشنبه"}]}}""",
        )

        private val SCREENS: Map<String, @Composable (AppGraph) -> Unit> = linkedMapOf(
            "v32-talk" to { _ -> com.coinepro.hq.ui.v32.TalkScreen(ref0 = "CV-0001") },
            "v32-talk-work" to { _ -> com.coinepro.hq.ui.v32.TalkScreen(ref0 = "CV-0002") },
            "v32-card-minutes-edit" to { _ -> Cardlike { com.coinepro.hq.ui.v32.TalkCardView(CARD_MINUTES, { _, _ -> }, { }, editing0 = true) } },
            "v32-live" to { _ ->
                Cardlike {
                    com.coinepro.hq.ui.v32.LiveBubble(Phase.THINKING, "", null, PERSONAS[0], emptyList(), false, { _, _ -> }, { })
                    com.coinepro.hq.ui.v32.LiveBubble(Phase.WRITING, "بله، **سه چیز** منتظر توست:\n\n- یک تصمیم استخدام\n- ایمیل حقوقی", null, PERSONAS[0], emptyList(), true, { _, _ -> }, { })
                    com.coinepro.hq.ui.v32.LiveBubble(Phase.IDLE, "", "الان به مغزم دسترسی ندارم؛ کمی بعد دوباره بگو.", PERSONAS[1], emptyList(), false, { _, _ -> }, { })
                }
            },
            "v32-composer" to { _ ->
                Cardlike {
                    com.coinepro.hq.ui.v32.ModeStrip("work", {}, {})
                    Composer("", HoldUi(), HandsFree.OFF)
                    Composer("هفته‌ی آموزش طلا را برای تریدیار برنامه‌ریز", HoldUi(), HandsFree.OFF)
                    Composer("", HoldUi(active = true, partial = "یک ریلز آموزشی درباره‌ی پیوت طلا", levels = LEVELS, seconds = 4.2), HandsFree.OFF)
                    Composer("", HoldUi(transcribing = true), HandsFree.OFF)
                    Composer("", HoldUi(), HandsFree.LISTENING, hf = "")
                    Composer("", HoldUi(), HandsFree.HEARING, hf = "برای تریدیار یک ریلز بساز")
                    Composer("", HoldUi(), HandsFree.ANSWERING, hf = "")
                    // ⟨0.17.0⟩ a long draft across the whole width (six lines, then it scrolls), «بفرست» in place of the mic; and «↓».
                    Composer(LONG_DRAFT, HoldUi(), HandsFree.OFF)
                    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        com.coinepro.hq.ui.v32.JumpButton(0, {})
                        com.coinepro.hq.ui.v32.JumpButton(3, {})
                    }
                }
            },
            "v32-header-states" to { _ ->
                Cardlike {
                    val engines = listOf(engine(FLASH, "جمینای فلش", "ok"), engine(LITE, "جمینای فلش لایت", "checking"), engine("piper", "صدای ساده‌ی هاب", "capped"), engine("x", "نمونه", "failing", "کلید درست نیست"))
                    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        com.coinepro.hq.ui.v32.LightsRow(engines, engines.map { it.key }, emptyMap(), {})
                    }
                    com.coinepro.hq.ui.v32.MeterChip(VoiceMeter(voiceUsd = 0.42, capUsd = 10.0), 0.8, {})
                    com.coinepro.hq.ui.v32.MeterChip(VoiceMeter(voiceUsd = 8.4, capUsd = 10.0), 0.8, {})
                    com.coinepro.hq.ui.v32.MeterChip(VoiceMeter(voiceUsd = 10.0, capUsd = 10.0), 0.8, {})
                    com.coinepro.hq.ui.v32.MeterChip(VoiceMeter(voiceUsd = 0.42, capUsd = null), 0.8, {})
                    com.coinepro.hq.ui.v32.FacesRow(PERSONAS + persona("manager", "مدیر رسانه‌ی فاکس", FLASH, "Zephyr", role = "media", company = "FX"), "overseer", true, {}, {})
                }
            },
            "v32-key-caught" to { _ -> Sheetlike { com.coinepro.hq.ui.v32.KeyBody({}, initial = CAUGHT) } },
            "v32-key-waiting" to { _ -> Sheetlike { com.coinepro.hq.ui.v32.KeyBody({}, saved0 = true, askCap0 = true, lights = mapOf(FLASH to ("checking" to null), LITE to ("checking" to null))) } },
            "v32-key-failing" to { _ -> Sheetlike { com.coinepro.hq.ui.v32.KeyBody({}, saved0 = true, lights = mapOf(FLASH to ("failing" to "این کلید به مدل صدا دسترسی ندارد"), LITE to ("ok" to null))) } },
            "v32-engine-reason" to { _ -> Sheetlike { com.coinepro.hq.ui.v32.EngineReasonBody(engine(FLASH, "جمینای فلش", "failing", "صورتحساب این پروژه فعال نیست"), "failing", "صورتحساب این پروژه فعال نیست", {}, {}) } },
            "v32-meter" to { _ -> Sheetlike { com.coinepro.hq.ui.v32.MeterBody() } },
            "v32-meter-cap" to { _ -> Sheetlike { com.coinepro.hq.ui.v32.MeterBody(editCap0 = true, showPrices0 = true) } },
            "v32-voices" to { _ -> Sheetlike { com.coinepro.hq.ui.v32.VoicesBody(listOf("secretary", "ceo@TY"), open0 = "secretary") } },
            "v32-invite-companies" to { _ -> Sheetlike { com.coinepro.hq.ui.v32.InviteBody({ _, _, _ -> }) } },
            "v32-invite-roles" to { _ -> Sheetlike { com.coinepro.hq.ui.v32.InviteBody({ _, _, _ -> }, company0 = "TY") } },
            "v32-conversations" to { _ -> com.coinepro.hq.ui.v32.ConversationsScreen() },
            "v32-conversations-search" to { _ -> com.coinepro.hq.ui.v32.ConversationsScreen(q0 = "طلا") },
        )

        private const val LONG_DRAFT = "هفته‌ی آموزش طلا را برای تریدیار برنامه‌ریزی کن: سه ریلز کوتاه درباره‌ی پیوت طلا، دو پست کانال و یک مقاله‌ی " +
            "ساده برای تازه‌کارها. ریلزها پیش از انتشار برای من بیاید و تیتر کاورها با فونت خودمان باشد. بودجه‌ی تبلیغ همان سقف ماه است؛ " +
            "اگر بیشتر لازم شد اول بپرس. گزارش بازده را آخر هفته بفرست، کوتاه و با عدد، که بدانم کدام ریلز بهتر دیده شد و چرا."

        private val LEVELS = List(32) { i -> (0.15f + 0.6f * kotlin.math.abs(kotlin.math.sin(i * 0.7f))).coerceIn(0f, 1f) }

        @JvmStatic
        @ParameterizedRobolectricTestRunner.Parameters(name = "{0}-{1}")
        fun params(): List<Array<Any>> = SCREENS.keys.flatMap { listOf(arrayOf<Any>(it, true), arrayOf<Any>(it, false)) }

        /** The composer in one of its states. */
        @Composable
        private fun Composer(text: String, hold: HoldUi, hfState: HandsFree, hf: String = "") {
            com.coinepro.hq.ui.v32.TalkComposerView(
                text, {}, hold, hfState, hf, LEVELS, false, {}, {}, {}, {}, {},
            )
        }

        @Composable
        private fun Cardlike(content: @Composable () -> Unit) {
            Column(
                Modifier.fillMaxSize().background(Divan.colors.page).verticalScroll(rememberScrollState()).padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) { content() }
        }

        @Composable
        private fun Sheetlike(content: @Composable () -> Unit) {
            Column(
                Modifier.fillMaxSize().background(Divan.colors.overlay).verticalScroll(rememberScrollState()).padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(14.dp),
            ) { content() }
        }
    }

    @get:Rule
    val compose = createAndroidComposeRule<ComponentActivity>()

    private lateinit var graph: AppGraph

    @Before
    fun setUp() {
        com.coinepro.hq.core.format.HqClock.fixed = java.time.Instant.parse("2026-10-17T08:30:00Z")
        graph = (ApplicationProvider.getApplicationContext<HqApp>()).graph
        graph.link.setForeground(false)
        graph.enterDemo()
        DemoLive.servers?.still = true
    }

    @Test
    fun screen() {
        val nav = object : Nav {
            override fun go(route: String) = Unit
            override fun back() = Unit
        }
        compose.mainClock.autoAdvance = false
        compose.setContent {
            DivanTheme(night) {
                CompositionLocalProvider(
                    LocalEnv provides graph.env.value, LocalToasts provides Toasts(), LocalNav provides nav,
                    com.coinepro.hq.designsystem.LocalReducedMotion provides true,
                ) {
                    Box(Modifier.fillMaxSize().background(Divan.colors.page)) { SCREENS.getValue(name)(graph) }
                }
            }
        }
        // Demo responses take ~150 ms each on OkHttp threads (the personas, the conversation, then the engines and the meter); let them land.
        repeat(22) {
            Thread.sleep(200)
            shadowOf(Looper.getMainLooper()).idle()
            compose.mainClock.advanceTimeBy(250)
        }
        compose.onRoot().captureRoboImage(
            "src/test/screenshots/$name-${if (night) "night" else "day"}.png",
            roborazziOptions = RoborazziOptions(
                recordOptions = RoborazziOptions.RecordOptions(resizeScale = 0.5),
                compareOptions = RoborazziOptions.CompareOptions(changeThreshold = 0.002f),
            ),
        )
    }
}
