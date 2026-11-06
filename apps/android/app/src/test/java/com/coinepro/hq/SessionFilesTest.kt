package com.coinepro.hq

import com.coinepro.hq.core.media.FileKind
import com.coinepro.hq.core.media.fileKindFa
import com.coinepro.hq.core.media.fileKindOf
import com.coinepro.hq.core.media.sessionFileKind
import com.coinepro.hq.core.media.sessionReject
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.ApiException
import com.coinepro.hq.core.net.FileRef
import com.coinepro.hq.core.net.OrderReport
import com.coinepro.hq.core.net.TalkDetail
import com.coinepro.hq.core.net.TokenSource
import com.coinepro.hq.core.net.turnFilesUnknown
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/**
 * ⟨1.18⟩ Contract §36, files in a session: what a picked file is (by its type, and by its extension where phones call fonts, ZIPs and
 * Markdown `application/octet-stream`) and the type it is sent as; why one cannot go, in plain Persian; how a file of the hub is named
 * (a kind the app does not know yet is a plain «فایل», never a crash); a turn and a report with files; and the turn's `file_ids`.
 */
@RunWith(RobolectricTestRunner::class)
class SessionFilesTest {
    private val server = MockWebServer()
    private lateinit var api: Api

    @Before
    fun setUp() {
        server.start()
        api = Api(server.url("/").toString(), object : TokenSource { override fun token() = "t"; override fun clear() = Unit })
    }

    @After
    fun tearDown() = server.close()

    private fun json(code: Int, body: String) = MockResponse.Builder().code(code).addHeader("Content-Type", "application/json").body(body).build()

    // ------------------------------------------------------------ kinds --
    @Test
    fun aFontIsKnownByItsExtensionWhateverThePhoneCallsIt() {
        assertEquals(FileKind.FONT to "font/ttf", sessionFileKind("titr.ttf", "application/octet-stream"))
        assertEquals(FileKind.FONT to "font/otf", sessionFileKind("Titr-Bold.OTF", null))
        assertEquals(FileKind.FONT to "font/woff", sessionFileKind("titr.woff", "application/font-woff"))
        assertEquals(FileKind.FONT to "font/woff2", sessionFileKind("titr.woff2", ""))
        // Its type alone is enough too, under any of the names phones give it.
        assertEquals(FileKind.FONT to "font/ttf", sessionFileKind("font", "application/x-font-ttf"))
        assertEquals(FileKind.FONT to "font/otf", sessionFileKind("font", "application/vnd.ms-opentype"))
        assertEquals(FileKind.FONT to "font/woff2", sessionFileKind("font", "font/woff2"))
    }

    @Test
    fun picturesFilmsVoiceAndPdfsGoByTheirType() {
        assertEquals(FileKind.IMAGE to "image/jpeg", sessionFileKind("IMG_1.jpg", "image/jpeg"))
        assertEquals(FileKind.IMAGE to "image/jpeg", sessionFileKind("x", "image/jpg"))
        assertEquals(FileKind.IMAGE to "image/heic", sessionFileKind("IMG_2.HEIC", "image/heic"))
        assertEquals(FileKind.VIDEO to "video/quicktime", sessionFileKind("clip.mov", "video/quicktime"))
        assertEquals(FileKind.AUDIO to "audio/mp4", sessionFileKind("voice.m4a", "audio/mp4"))
        assertEquals(FileKind.AUDIO to "audio/webm", sessionFileKind("voice.webm", "audio/webm"))
        assertEquals(FileKind.AUDIO to "audio/ogg", sessionFileKind("voice.opus", "application/octet-stream"))
        assertEquals(FileKind.PDF to "application/pdf", sessionFileKind("brief.pdf", "application/pdf"))
        // No useful type: the extension decides.
        assertEquals(FileKind.PDF to "application/pdf", sessionFileKind("brief.pdf", "application/octet-stream"))
        assertEquals(FileKind.IMAGE to "image/png", sessionFileKind("shot.png", null))
    }

    @Test
    fun textMarkdownAndZipAreDocuments() {
        assertEquals(FileKind.TEXT to "text/plain", sessionFileKind("notes.txt", "text/plain"))
        assertEquals(FileKind.TEXT to "text/markdown", sessionFileKind("brief.md", "application/octet-stream"))
        assertEquals(FileKind.TEXT to "text/markdown", sessionFileKind("brief.markdown", "text/plain"))
        assertEquals(FileKind.ZIP to "application/zip", sessionFileKind("pages.zip", "application/x-zip-compressed"))
        assertEquals(FileKind.ZIP to "application/zip", sessionFileKind("pages.zip", "application/octet-stream"))
        assertEquals("document", FileKind.TEXT.hub)
        assertEquals("document", FileKind.ZIP.hub)
        assertEquals("font", FileKind.FONT.hub)
    }

    @Test
    fun whatTheHubDoesNotTakeIsRefusedInPlainPersian() {
        assertNull(sessionFileKind("anim.gif", "image/gif"))
        assertNull(sessionFileKind("plan.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"))
        assertNull(sessionFileKind("blob.bin", "application/octet-stream"))
        val why = sessionReject("anim.gif", "image/gif", 1_000)!!
        assertTrue(why.contains("anim.gif") && why.contains("فونت") && why.contains("ZIP"))
        // Too big for its kind: the kind and the limit are named.
        val big = sessionReject("titr.ttf", "application/octet-stream", 21L * 1024 * 1024)!!
        assertTrue(big, big.contains("فونت حداکثر 20 MB"))
        assertTrue(sessionReject("pages.zip", "application/zip", 51L * 1024 * 1024)!!.contains("ZIP حداکثر 50 MB"))
        assertNull(sessionReject("pages.zip", "application/zip", 49L * 1024 * 1024))
        assertNotNull(sessionReject("empty.txt", "text/plain", 0))
        // An unknown size (a provider that does not tell) is the hub's to check while it streams.
        assertNull(sessionReject("clip.mp4", "video/mp4", -1))
    }

    // --------------------------------------------------- the hub's files --
    @Test
    fun aFileOfTheHubIsNamedByItsKindAndAFontByItsFamily() {
        val font = Api.json.decodeFromString(FileRef.serializer(), """{"id":"f1","name":"titr.ttf","mime":"font/ttf","size":186420,"kind":"font","meta":{"family":"Titr Cover"}}""")
        assertEquals(FileKind.FONT, fileKindOf(font))
        assertEquals("Titr Cover", font.family)
        assertEquals("فونت Titr Cover", fileKindFa(font))
        assertEquals(FileKind.ZIP, fileKindOf(FileRef(id = "z", name = "pages.zip", mime = "application/zip", kind = "document")))
        assertEquals("PDF", fileKindFa(FileRef(id = "p", name = "brief.pdf", mime = "application/pdf", kind = "document")))
        assertEquals("فونت", fileKindFa(FileRef(id = "f2", name = "x.ttf", mime = "font/ttf", kind = "font")))
        // A kind the app does not know yet: a plain file.
        val odd = FileRef(id = "s", name = "plan.xlsx", mime = "application/vnd.ms-excel", kind = "sheet")
        assertNull(fileKindOf(odd))
        assertEquals("فایل", fileKindFa(odd))
    }

    @Test
    fun aTurnAndAReportCarryTheirFilesAndAnOddOneNeverHidesTheConversation() {
        val d = TalkDetail.parse(
            Api.json.parseToJsonElement(
                """{"ref":"CV-0501","persona":"ceo@TY","turns_page":{"items":[
                {"id":"T-1","n":1,"by":"owner","text":"فایل","files":[
                  {"id":"f1","name":"titr.ttf","mime":"font/ttf","size":186420,"kind":"font","meta":{"family":"Titr Cover"}},
                  {"id":"f2","kind":"sheet"},
                  {"id":"f3","name":"cover.webp","mime":"image/webp","size":11962,"kind":"image","width":360,"height":640,"status":null}
                ]},
                {"id":"T-2","n":2,"by":"ceo@TY","show_md":"گرفتم."}
                ]}}""",
            ),
        )
        assertEquals(2, d.turns.size)
        assertEquals(listOf("font", "sheet", "image"), d.turns[0].files.map { it.kind })
        assertEquals("", d.turns[0].files[1].name)
        assertEquals("ready", d.turns[0].files[2].status)
        assertTrue(d.turns[1].files.isEmpty())
        val r = Api.json.decodeFromString(OrderReport.serializer(), """{"ref":"F-0101","files":[{"id":"f1","name":"titr.ttf","mime":"font/ttf","size":1,"kind":"font"}]}""")
        assertEquals(listOf("f1"), r.files.map { it.id })
        assertTrue(Api.json.decodeFromString(OrderReport.serializer(), """{"ref":"F-0102"}""").files.isEmpty())
    }

    // ----------------------------------------------------------- the call --
    @Test
    fun aTurnSendsItsFileIdsOnlyWhenThereAreSome() = runTest {
        server.enqueue(json(202, """{"turn":{"id":7,"by":"ceo@TY"},"events":null}"""))
        server.enqueue(json(202, """{"turn":{"id":8,"by":"ceo@TY"},"events":null}"""))
        api.sendTalkTurn("CV-0501", "فایل", "typed", "cid-1", fileIds = listOf("a", "b", "a") + (1..12).map { "x$it" })
        val withFiles = Api.json.parseToJsonElement(server.takeRequest().body!!.utf8()).jsonObject
        val ids = withFiles["file_ids"]!!.jsonArray.map { it.jsonPrimitive.content }
        assertEquals(10, ids.size)
        assertEquals(listOf("a", "b", "x1"), ids.take(3))
        api.sendTalkTurn("CV-0501", "سلام", "typed", "cid-2")
        val without = Api.json.parseToJsonElement(server.takeRequest().body!!.utf8()).jsonObject
        assertFalse(without.containsKey("file_ids"))
    }

    @Test
    fun aHubBeforeFilesInTalkIsToldApartFromARefusedFile() {
        val old = ApiException(422, "validation_failed", "x", fields = mapOf("file_ids" to "Extra inputs are not permitted"))
        assertTrue(old.turnFilesUnknown)
        val notYours = ApiException(422, "validation_failed", "x", fields = mapOf("file_ids" to "not yours to send: f1"))
        assertFalse(notYours.turnFilesUnknown)
        assertFalse(ApiException(409, "closed", "x").turnFilesUnknown)
    }
}
