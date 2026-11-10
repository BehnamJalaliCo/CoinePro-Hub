package com.coinepro.hq

import android.os.Looper
import androidx.activity.ComponentActivity
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.Modifier
import androidx.compose.ui.test.junit4.v2.createAndroidComposeRule
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.unit.dp
import androidx.test.core.app.ApplicationProvider
import com.coinepro.hq.core.AppGraph
import com.coinepro.hq.designsystem.Divan
import com.coinepro.hq.designsystem.DivanTheme
import com.coinepro.hq.ui.LocalEnv
import com.coinepro.hq.ui.LocalNav
import com.coinepro.hq.ui.LocalToasts
import com.coinepro.hq.ui.Nav
import com.coinepro.hq.ui.Toasts
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
 * ⟨1.16, 1.17⟩ Contract §34–§35, night and day, with the demo holding, drawn tall (1600dp): one order's session in each of its states.
 * ⟨0.17.0⟩ A compact head (the words in two lines, the badge and one line, «جزئیات») over the chat, which sits at its newest word: the
 * steps of the work as quiet lines, a result as one card, what blocks it with its fix at the foot, and a closed session's way back.
 * ⟨1.18⟩ §36 the files: the owner's turn with the covers' font, a sample cover and a brief, and the composer with files on their way
 * (going, there, failed) and a turn of files only. The phone-height views are in [SessionChatScreensTest].
 */
@RunWith(ParameterizedRobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [35], qualifiers = "w400dp-h1600dp-xxhdpi")
class SessionScreensTest(private val name: String, private val night: Boolean) {
    companion object {
        private val SCREENS: Map<String, @Composable (AppGraph) -> Unit> = linkedMapOf(
            // The owner's turn: a step order, the CEO asks; a media manager and GPT in the room; a plan of four, one of them his; the
            // files he sent with his second turn (a font, a sample cover, a brief), in the bubble and in «فایل‌ها».
            "order-session-your-turn" to { _ -> com.coinepro.hq.ui.session.OrderSessionScreen("F-0101") },
            // Ready for his OK: the advisor's report in the results, «تأیید و بستن» in gold.
            "order-session-ready" to { _ -> com.coinepro.hq.ui.session.OrderSessionScreen("F-0102") },
            // Stuck: no one to do it; the secretary holds it, the blocker with its fix and her hire card inline.
            "order-session-stuck" to { _ -> com.coinepro.hq.ui.session.OrderSessionScreen("F-0103") },
            // Closed, in the archive: read-only, «باز کردن دوباره».
            "order-session-closed" to { _ -> com.coinepro.hq.ui.session.OrderSessionScreen("F-0099") },
            // ⟨1.18⟩ the paperclip and the chips: a film going (42%), the font and the brief there, a picture that failed; then files
            // with no words (send open); then a turn of files only and the holder's answer.
            "order-session-attach" to { _ -> Attaching() },
            // ⟨1.19⟩ §37 «پاک کردن برای همیشه»: a session's preview (what goes, in Persian digits; what stays) and its two choices, then
            // an archive record's under a hold the hub named, and a hub before ⟨1.19⟩.
            "order-session-erase" to { _ -> Erasing() },
            // ⟨0.17.0⟩ «جزئیات»: the order's words whole, the brief, the people and models, the pace, the plan, the files; close, hide
            // and erase. Everything the head no longer stacks above the chat.
            "order-session-details" to { _ -> Details("F-0101") },
            // ⟨1.0.1⟩ §50 «روال‌های دائمی» of the reels session (one on with its next run, one off that says why), «روال دائمی» among its
            // actions, and the sheet with a sentence the hub would not make a routine of (its own words under the field, the text kept).
            "order-session-routines" to { _ -> Routines("F-0100") },
            // ⟨1.0.1⟩ §51 «انتشارها» of the same session: what is set to go out carries «لغو»; one taken back, one being cancelled.
            "order-session-publishes" to { _ -> Publishes("F-0100") },
            // ⟨1.0.1⟩ §53 an output of the workshop, whole: how it was made («Opus 5.5 · بیشترین دقت»), its files, and its publishes.
            "output-effort" to { _ -> com.coinepro.hq.ui.outputs.OutputScreen("O-000954") },
        )

        /** A sentence that names no time: no plain routine. */
        private const val NO_ROUTINE = "برای پرو-چارت یک لوگوی تازه بساز"

        @Composable
        private fun Routines(ref: String) {
            val env = com.coinepro.hq.ui.LocalEnv.current
            val c = com.coinepro.hq.designsystem.Divan.colors
            val o = com.coinepro.hq.ui.v29.rememberOrderReport(ref).data ?: return
            // the hub's own refusal of the sentence, as the sheet shows it
            val refused = androidx.compose.runtime.produceState<String?>(null) {
                value = try {
                    env.api.newRoutine(NO_ROUTINE, ref, java.util.UUID.randomUUID().toString())
                    "made"
                } catch (e: com.coinepro.hq.core.net.ApiException) { e.messageFa }
            }.value ?: return
            androidx.compose.foundation.layout.Column(
                Modifier.fillMaxSize().background(c.overlay).padding(16.dp),
                verticalArrangement = androidx.compose.foundation.layout.Arrangement.spacedBy(14.dp),
            ) {
                androidx.compose.material3.Text("جزئیات جلسه", style = com.coinepro.hq.designsystem.Divan.type.h2)
                com.coinepro.hq.ui.session.SessionRoutines(o.routines.orEmpty()) {}
                com.coinepro.hq.ui.session.RoutineAction {}
                androidx.compose.material3.HorizontalDivider(color = c.lineDivider)
                androidx.compose.material3.Text("روال دائمی", style = com.coinepro.hq.designsystem.Divan.type.h2)
                com.coinepro.hq.ui.session.RoutineForm(ref, sentence0 = NO_ROUTINE, refused0 = refused) {}
            }
        }

        @Composable
        private fun Publishes(ref: String) {
            val o = com.coinepro.hq.ui.v29.rememberOrderReport(ref).data ?: return
            androidx.compose.foundation.layout.Column(
                Modifier.fillMaxSize().background(com.coinepro.hq.designsystem.Divan.colors.overlay).padding(16.dp),
                verticalArrangement = androidx.compose.foundation.layout.Arrangement.spacedBy(14.dp),
            ) {
                androidx.compose.material3.Text("جزئیات جلسه", style = com.coinepro.hq.designsystem.Divan.type.h2)
                com.coinepro.hq.ui.session.SessionPublishes(o.publishes) {}
            }
        }

        @Composable
        private fun Details(ref: String) {
            val o = com.coinepro.hq.ui.v29.rememberOrderReport(ref).data ?: return
            androidx.compose.foundation.layout.Column(
                Modifier.fillMaxSize().background(com.coinepro.hq.designsystem.Divan.colors.overlay).padding(16.dp),
                verticalArrangement = androidx.compose.foundation.layout.Arrangement.spacedBy(14.dp),
            ) {
                androidx.compose.material3.Text("جزئیات جلسه", style = com.coinepro.hq.designsystem.Divan.type.h2)
                com.coinepro.hq.ui.session.SessionDetailsBody(
                    o, closed = false, sessionsOn = true, participants = com.coinepro.hq.core.data.orderParticipants(o.participants), addressee = null,
                    onPick = {}, onAddPerson = {}, onAddModel = {}, onPace = {}, onTasksChanged = {}, onClose = {}, onReopen = {}, onHide = {}, onErase = {},
                )
            }
        }

        @Composable
        private fun Erasing() {
            val c = com.coinepro.hq.designsystem.Divan.colors
            val counts = kotlinx.serialization.json.buildJsonObject {
                put("turns", kotlinx.serialization.json.JsonPrimitive(12)); put("files", kotlinx.serialization.json.JsonPrimitive(3))
                put("outputs", kotlinx.serialization.json.JsonPrimitive(1)); put("works", kotlinx.serialization.json.JsonPrimitive(4))
                put("notifications", kotlinx.serialization.json.JsonPrimitive(2))
            }
            val p = com.coinepro.hq.core.net.ErasePreview(
                "F-0101", "session", "برای تریدیار هفته‌ی آموزش طلا را راه بینداز؛ مرحله به مرحله با من جلو برو.", counts,
                listOf("خط تولید یا کارگروهی که این جلسه راه انداخت میماند؛ آن را در صفحه‌ی خودش پاک کن.", "یک خط در دفتر حسابرسی، بی متن فرمان.", "عددهای توکن و پول، که خزانه هنوز باید جمعشان را داشته باشد."),
            )
            androidx.compose.foundation.layout.Column(
                Modifier.fillMaxSize().background(c.overlay).padding(16.dp),
                verticalArrangement = androidx.compose.foundation.layout.Arrangement.spacedBy(14.dp),
            ) {
                androidx.compose.material3.Text("پاک کردن برای همیشه", style = com.coinepro.hq.designsystem.Divan.type.h3)
                androidx.compose.material3.Text(com.coinepro.hq.ui.session.ERASE_SUB, style = com.coinepro.hq.designsystem.Divan.type.caption, color = c.textMuted)
                com.coinepro.hq.ui.session.EraseBody(com.coinepro.hq.core.net.EraseKind.SESSION, p, false, null, false, {}, {})
                androidx.compose.material3.HorizontalDivider(color = c.lineDivider)
                com.coinepro.hq.ui.session.EraseBody(com.coinepro.hq.core.net.EraseKind.RECORD, null, false, "این سند زیر توقیف LH-0003 است؛ تا توقیف برداشته نشود پاک نمیشود.", false, {}, {})
                androidx.compose.material3.HorizontalDivider(color = c.lineDivider)
                com.coinepro.hq.ui.session.EraseBody(com.coinepro.hq.core.net.EraseKind.OUTPUT, null, true, null, false, {}, {})
            }
        }

        private fun pending(name: String, mime: String, size: Long, kind: String, state: String, progress: Float = 1f, error: String? = null) =
            com.coinepro.hq.ui.media.Pending(name, com.coinepro.hq.core.media.LocalFile(android.net.Uri.parse("content://demo/$name"), name, mime, size), kind, null).apply {
                this.state = state; this.progress = progress; this.error = error
                if (state == "ready") ref = com.coinepro.hq.core.net.FileRef(id = "f-$name", name = name, mime = mime, size = size, kind = kind)
            }

        @Composable
        private fun Attaching() {
            val going = listOf(
                pending("reels-gold.mp4", "video/mp4", 48_200_000, "video", "uploading", progress = 0.42f),
                pending("titr-cover.ttf", "font/ttf", 186_420, "font", "ready"),
                pending("بریف ریلزها.pdf", "application/pdf", 248_310, "pdf", "ready"),
                pending("کاور.heic", "image/heic", 3_400_000, "image", "failed", error = "بارگذاری نشد؛ اینترنت را ببین."),
            )
            val c = com.coinepro.hq.designsystem.Divan.colors
            androidx.compose.foundation.layout.Column(
                Modifier.fillMaxSize().background(c.page).padding(16.dp),
                verticalArrangement = androidx.compose.foundation.layout.Arrangement.spacedBy(16.dp),
            ) {
                Composer("تیتر کاورها با این فونت باشد", going, filesBusy = true)
                Composer("", going.subList(1, 3), filesBusy = false)
                val files = listOf(
                    com.coinepro.hq.core.net.FileRef(id = "/demo/pc-landing-redesign.webp", name = "صفحه‌ی فرود.webp", mime = "image/webp", size = 19_810, kind = "image", width = 960, height = 600),
                    com.coinepro.hq.core.net.FileRef(
                        id = "/demo/fonts/titr-cover.ttf", name = "titr-cover.ttf", mime = "font/ttf", size = 186_420, kind = "font",
                        meta = kotlinx.serialization.json.buildJsonObject { put("family", kotlinx.serialization.json.JsonPrimitive("Titr Cover")) },
                    ),
                    com.coinepro.hq.core.net.FileRef(id = "/demo/docs/pages.zip", name = "صفحه‌ها.zip", mime = "application/zip", size = 2_840_000, kind = "document"),
                    // A kind this app does not know yet: a plain file row, never dropped.
                    com.coinepro.hq.core.net.FileRef(id = "/demo/docs/plan.xlsx", name = "برنامه.xlsx", mime = "application/vnd.ms-excel", size = 41_000, kind = "sheet"),
                )
                val at = "2026-11-06T08:20:00Z"
                com.coinepro.hq.ui.v32.TalkBubble(
                    com.coinepro.hq.core.net.TalkTurn(by = "owner", text = com.coinepro.hq.core.media.FILES_ONLY_TEXT, at = at, files = files),
                    null, emptyList(), false, null, { _, _ -> }, { },
                )
                com.coinepro.hq.ui.v32.TalkBubble(
                    com.coinepro.hq.core.net.TalkTurn(by = "ceo@TY", showMd = "فونت «Titr Cover» را گرفتم؛ تیتر کاورها با همین نوشته میشود.", at = at),
                    com.coinepro.hq.core.net.TalkPersona(key = "manager", role = "ceo", company = "TY", titleFa = "مدیرعامل تریدیار"), emptyList(), true, null, { _, _ -> }, { },
                )
            }
        }

        /** The session's composer with [files] above the words, the paperclip beside the mic. */
        @Composable
        private fun Composer(text: String, files: List<com.coinepro.hq.ui.media.Pending>, filesBusy: Boolean) {
            com.coinepro.hq.ui.v32.TalkComposerView(
                text, {}, com.coinepro.hq.ui.v32.HoldUi(), com.coinepro.hq.core.data.HandsFree.OFF, "", emptyList(), false, {}, {}, {}, {}, {},
                onAttach = {}, files = { com.coinepro.hq.ui.v32.PendingFiles(files, {}, {}) },
                hasFiles = files.any { it.ref != null }, filesBusy = filesBusy,
            )
        }

        @JvmStatic
        @ParameterizedRobolectricTestRunner.Parameters(name = "{0}-{1}")
        fun params(): List<Array<Any>> = SCREENS.keys.flatMap { listOf(arrayOf<Any>(it, true), arrayOf<Any>(it, false)) }
    }

    @get:Rule
    val compose = createAndroidComposeRule<ComponentActivity>()

    private lateinit var graph: AppGraph

    @Before
    fun setUp() {
        com.coinepro.hq.core.format.HqClock.fixed = java.time.Instant.parse("2026-11-06T08:30:00Z")
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
        // The report, then the session's talk and the personas: each a demo answer of ~60–150 ms on OkHttp threads. Let them land.
        repeat(20) {
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
