package com.coinepro.hq

import com.coinepro.hq.core.data.PB_PLATFORMS
import com.coinepro.hq.core.data.Refs
import com.coinepro.hq.core.data.applyBody
import com.coinepro.hq.core.data.applyTargets
import com.coinepro.hq.core.data.canApplyAsIs
import com.coinepro.hq.core.data.canSeal
import com.coinepro.hq.core.data.cardInfo
import com.coinepro.hq.core.data.faNum
import com.coinepro.hq.core.data.helperOf
import com.coinepro.hq.core.data.libraryGroups
import com.coinepro.hq.core.data.madeFa
import com.coinepro.hq.core.data.memberStateFa
import com.coinepro.hq.core.data.membersFa
import com.coinepro.hq.core.data.memoryFolds
import com.coinepro.hq.core.data.withoutRefs
import com.coinepro.hq.core.data.pbPlatformFa
import com.coinepro.hq.core.data.pbPlatformLineFa
import com.coinepro.hq.core.data.playbookCardOf
import com.coinepro.hq.core.data.playbookPatch
import com.coinepro.hq.core.data.playbookStateFa
import com.coinepro.hq.core.data.playbooksOf
import com.coinepro.hq.core.data.routineTimeFa
import com.coinepro.hq.core.data.seatTitleFa
import com.coinepro.hq.core.data.withoutSeat
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.net.Api
import com.coinepro.hq.core.net.Company
import com.coinepro.hq.core.net.OrderReport
import com.coinepro.hq.core.net.Playbook
import com.coinepro.hq.core.net.PlaybookMember
import com.coinepro.hq.core.net.PlaybookRoutine
import com.coinepro.hq.core.net.PlaybookSeat
import com.coinepro.hq.core.net.PlaybookSource
import com.coinepro.hq.core.net.SessionCard
import com.coinepro.hq.core.net.TokenSource
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.boolean
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
 * ⟨1.22⟩ Contract §40, a session becomes a working group: the shapes as the hub serialises them (`Playbook` with its nulls, the "as built"
 * fields, `OrderReport.memory_md`, a session's `source`), every route with its key or its seal (`POST /orders/{ref}/playbook` with the
 * press's UUID, the library's `state`, a `PATCH` of only what changed, 🔏 `playbook.seal` and `playbook.retire` on the ref, `apply` as is
 * or with a platform and a note), and the owner's words: a routine's time, the library's order, the memory without refs, the card.
 */
@RunWith(RobolectricTestRunner::class)
class PlaybooksTest {
    private val server = MockWebServer()
    private lateinit var api: Api
    private val signed = mutableListOf<Pair<String, String>>()
    private val stepUp: suspend (String, String) -> String = { a, t -> signed += a to t; "su-token" }

    @Before
    fun setUp() {
        server.start()
        api = Api(server.url("/").toString(), object : TokenSource { override fun token() = "t"; override fun clear() = Unit })
    }

    @After
    fun tearDown() = server.close()

    private fun json(code: Int, body: String) = MockResponse.Builder().code(code).addHeader("Content-Type", "application/json").body(body).build()

    /** A playbook as pydantic writes it (every field, nulls included), from the hub's `PB.render`. */
    private fun pb(ref: String = "PB-0001", state: String = "draft", members: String = "[]", group: String? = null) = """{"ref":"$ref","title_fa":"سئوی هفتگی سایت",
        "purpose_fa":"بالا ماندن در جستجو","state":"$state","version":2,"platform":"site",
        "seats":[{"seat":"seo","role":"seo_specialist","title_fa":"کارشناس سئو","duties_fa":"بررسی رقبا","helpers":["gemini","aistudio"],"model":null},
                 {"seat":"writer","role":"content_writer","title_fa":"نویسنده","duties_fa":"","helpers":[],"model":"claude-sonnet-5-5"}],
        "routines":[{"key":"rivals","title_fa":"بررسی رقبا","seat":"seo","schedule":"FREQ=WEEKLY;BYDAY=SA;BYHOUR=9;BYMINUTE=0","brief_md":"سه رقیب","max_tokens":40000},
                    {"key":"article","title_fa":"مقاله","seat":"writer","schedule":"FREQ=WEEKLY;BYDAY=MO,TH;BYHOUR=10;BYMINUTE=30","brief_md":"","max_tokens":20000}],
        "kpis":[{"key":"rank","title_fa":"جایگاه","source":"search_console","unit":""}],"connections":["search_console"],"rules_fa":["با منبع"],
        "source":{"order":"F-0104","company":"PC","conversation":"CV-0504"},"members":$members,"parent":null,
        "created_at":"2026-11-07T08:00:00Z","sealed_at":null,"retired_at":null,"group":${group?.let { "\"$it\"" } ?: "null"},"note_fa":null}"""

    // ------------------------------------------------------------------ shapes --
    @Test
    fun theShapesReadAsTheHubWritesThem() {
        val p = Api.json.decodeFromString(Playbook.serializer(), pb(members = """[{"company":"PC","name_fa":"پرو-چارت","state":"on","order":"F-0104"}]""", group = "pb_1"))
        assertEquals(2, p.version)
        assertEquals(listOf("gemini", "aistudio"), p.seats[0].helpers)
        assertNull(p.seats[0].model)
        assertEquals(20000, p.routines[1].maxTokens)
        assertEquals("F-0104", p.source.order)
        assertEquals("pb_1", p.group)
        assertTrue(p.draft && !p.sealed && !p.retired)
        assertEquals("F-0104", p.members.single().order)
        // The shortest the hub may send (only the required fields): every list empty, the source's company and talk null.
        val bare = Api.json.decodeFromString(Playbook.serializer(), """{"ref":"PB-0009","title_fa":"t","purpose_fa":"","state":"sealed","version":1,"platform":"any","source":{"order":"F-0001","company":null,"conversation":null},"created_at":"2026-11-07T08:00:00Z"}""")
        assertTrue(bare.seats.isEmpty() && bare.members.isEmpty() && bare.rulesFa.isEmpty())
        assertNull(bare.source.company)
        // ⟨1.22⟩ the memory of a session and the playbook it came from; a hub before ⟨1.22⟩ sends neither.
        val r = Api.json.decodeFromString(OrderReport.serializer(), """{"ref":"F-0106","memory_md":"## تصمیم‌ها\n- یک","session":{"state":"open","badge":"moving","reason_fa":"","closed_at":null,"hidden":false,"source":"PB-0001"}}""")
        assertEquals("PB-0001", r.session?.source)
        assertEquals("## تصمیم‌ها\n- یک", r.memoryMd)
        assertNull(Api.json.decodeFromString(OrderReport.serializer(), """{"ref":"F-0101"}""").memoryMd)
        assertEquals("PB-0001", Api.json.decodeFromString(SessionCard.serializer(), """{"ref":"F-0106","source":"PB-0001"}""").source)
        assertNull(Api.json.decodeFromString(SessionCard.serializer(), """{"ref":"F-0101","source":null}""").source)
    }

    // ------------------------------------------------------------------ routes --
    @Test
    fun aDraftFromTheSessionCarriesThePresssOwnKey() = runTest {
        server.enqueue(json(201, pb()))
        val key = java.util.UUID.randomUUID().toString()
        val p = api.draftPlaybook("F-0104", key)
        assertEquals("PB-0001", p.ref)
        val req = server.takeRequest()
        assertEquals("POST", req.method)
        assertEquals("/api/v1/orders/F-0104/playbook", req.url.encodedPath)
        assertEquals(key, req.headers["Idempotency-Key"])
        assertNull(req.headers["X-Step-Up"])
    }

    @Test
    fun theLibraryIsABareListNarrowedByState() = runTest {
        server.enqueue(json(200, "[${pb()},${pb("PB-0002", "sealed", group = "pb_2")}]"))
        assertEquals(listOf("PB-0001", "PB-0002"), api.playbooks().map { it.ref })
        val all = server.takeRequest()
        assertEquals("/api/v1/playbooks", all.url.encodedPath)
        assertNull(all.url.queryParameter("state"))
        server.enqueue(json(200, "[]"))
        assertTrue(api.playbooks("sealed").isEmpty())
        assertEquals("sealed", server.takeRequest().url.queryParameter("state"))
        server.enqueue(json(200, pb()))
        api.playbook("PB-0001")
        assertEquals("/api/v1/playbooks/PB-0001", server.takeRequest().url.encodedPath)
    }

    @Test
    fun aLightEditSendsOnlyWhatChanged() = runTest {
        val before = Api.json.decodeFromString(Playbook.serializer(), pb())
        assertNull(playbookPatch(before, before))
        // A seat taken out takes its routines with it; a rule's words changed; the title trimmed.
        val after = withoutSeat(before, "writer").copy(titleFa = "  سئوی هفتگی  ", rulesFa = listOf("هر مقاله با منبع", " "))
        assertEquals(listOf("rivals"), after.routines.map { it.key })
        val body = playbookPatch(before, after)!!
        assertEquals(setOf("title_fa", "seats", "routines", "rules_fa"), body.keys)
        assertEquals("سئوی هفتگی", body["title_fa"]!!.jsonPrimitive.content)
        assertEquals(listOf("هر مقاله با منبع"), body["rules_fa"]!!.jsonArray.map { it.jsonPrimitive.content })
        // Seats and routines go whole, in the hub's names, every field written (a seat's model, a routine's budget stay).
        val seat = body["seats"]!!.jsonArray.single().jsonObject
        assertEquals(setOf("seat", "role", "title_fa", "duties_fa", "helpers", "model"), seat.keys)
        assertEquals(40000, body["routines"]!!.jsonArray.single().jsonObject["max_tokens"]!!.jsonPrimitive.content.toInt())
        server.enqueue(json(200, pb()))
        api.patchPlaybook("PB-0001", body)
        val req = server.takeRequest()
        assertEquals("PATCH", req.method)
        assertEquals("/api/v1/playbooks/PB-0001", req.url.encodedPath)
        assertEquals(body, Api.json.parseToJsonElement(req.body!!.utf8()).jsonObject)
        // The platform alone.
        assertEquals(setOf("platform"), playbookPatch(before, before.copy(platform = "youtube"))!!.keys)
    }

    @Test
    fun sealAndRetireAreSealedOnTheRef() = runTest {
        server.enqueue(json(200, pb(state = "sealed", group = "pb_1")))
        assertTrue(api.sealPlaybook("PB-0001", stepUp).sealed)
        val seal = server.takeRequest()
        assertEquals("/api/v1/playbooks/PB-0001/seal", seal.url.encodedPath)
        assertEquals("su-token", seal.headers["X-Step-Up"])
        server.enqueue(json(200, pb(state = "retired")))
        assertTrue(api.retirePlaybook("PB-0001", stepUp).retired)
        val retire = server.takeRequest()
        assertEquals("/api/v1/playbooks/PB-0001/retire", retire.url.encodedPath)
        assertEquals("su-token", retire.headers["X-Step-Up"])
        assertEquals(listOf("playbook.seal" to "PB-0001", "playbook.retire" to "PB-0001"), signed)
    }

    @Test
    fun applyOpensASessionOrJoinsAsIs() = runTest {
        // With a platform and a note: a new session for that company.
        server.enqueue(json(200, """{"playbook":${pb(state = "sealed", group = "pb_1")},"member":null,"order":"F-0106","conversation":"CV-0506"}"""))
        val key = java.util.UUID.randomUUID().toString()
        val out = api.applyPlaybook("PB-0001", "TY", "youtube", "  لحن رسمی  ", false, key)
        assertEquals("F-0106", out.order)
        assertEquals("CV-0506", out.conversation)
        val req = server.takeRequest()
        assertEquals("/api/v1/playbooks/PB-0001/apply", req.url.encodedPath)
        assertEquals(key, req.headers["Idempotency-Key"])
        val body = Api.json.parseToJsonElement(req.body!!.utf8()).jsonObject
        assertEquals(setOf("company", "platform", "note_fa"), body.keys)
        assertEquals("لحن رسمی", body["note_fa"]!!.jsonPrimitive.content)
        // As is: only the company and the flag (the hub ignores a platform and a note there), and the membership back.
        server.enqueue(json(200, """{"playbook":${pb(state = "sealed", group = "pb_1")},"member":{"company":"FX","name_fa":"کوینه‌پرو FX","state":"on","order":null},"order":null,"conversation":null}"""))
        val joined = api.applyPlaybook("PB-0001", "FX", "telegram", "x", true, java.util.UUID.randomUUID().toString())
        assertNull(joined.order)
        assertEquals("FX", joined.member?.company)
        val asIs = Api.json.parseToJsonElement(server.takeRequest().body!!.utf8()).jsonObject
        assertEquals(setOf("company", "as_is"), asIs.keys)
        assertTrue(asIs["as_is"]!!.jsonPrimitive.boolean)
        // No note, no platform: the company alone.
        assertEquals(setOf("company"), applyBody("PC", null, " ", false).keys)
    }

    // ------------------------------------------------------------------- words --
    @Test
    fun aRoutinesTimeInPlainPersian() {
        assertEquals("هر روز ساعت 09:00", routineTimeFa("FREQ=DAILY;BYHOUR=9;BYMINUTE=0"))
        assertEquals("هر شنبه و دوشنبه و چهارشنبه ساعت 18:30", routineTimeFa("RRULE:FREQ=WEEKLY;BYDAY=WE,SA,MO;BYHOUR=18;BYMINUTE=30"))
        assertEquals("هر ماه، روز ۱ ساعت 10:00", routineTimeFa("FREQ=MONTHLY;BYMONTHDAY=1;BYHOUR=10"))
        assertEquals("هر ۲ روز ساعت 08:00 و 20:00", routineTimeFa("FREQ=DAILY;INTERVAL=2;BYHOUR=20,8"))
        assertEquals("هر ساعت", routineTimeFa("FREQ=HOURLY"))
        assertEquals("هر هفته", routineTimeFa("FREQ=WEEKLY"))
        // A rule this does not read is never shown raw.
        assertEquals("طبق برنامه‌ی خودش", routineTimeFa("FREQ=YEARLY;BYMONTH=3"))
        assertEquals("بدون زمان", routineTimeFa(""))
    }

    @Test
    fun theLibrarySealedFirstAndTheCounts() {
        val draft = Api.json.decodeFromString(Playbook.serializer(), pb("PB-0003"))
        val sealed = draft.copy(ref = "PB-0001", state = "sealed", group = "pb_1", members = listOf(PlaybookMember("TY", "تریدیار"), PlaybookMember("FX", "کوینه‌پرو FX", "paused")))
        val retired = draft.copy(ref = "PB-0002", state = "retired")
        val groups = libraryGroups(listOf(draft, retired, sealed))
        assertEquals(listOf("مُهر شده و در کار", "پیش‌نویس", "بازنشسته"), groups.map { it.first })
        assertEquals(listOf("PB-0001"), groups[0].second.map { it.ref })
        assertTrue(libraryGroups(emptyList()).isEmpty())
        // Prose counts in Persian digits.
        assertEquals("۲ شرکت", membersFa(sealed.members.size))
        assertEquals("هنوز هیچ شرکتی", membersFa(0))
        assertEquals("۱۲", faNum(12))
        // The session's own playbooks, for its «جزئیات».
        assertEquals(listOf("PB-0003", "PB-0002", "PB-0001"), playbooksOf("F-0104", listOf(draft, retired, sealed)).map { it.ref })
        assertTrue(playbooksOf("F-0101", listOf(draft)).isEmpty())
        // The states and the platforms.
        assertEquals("مُهر شده" to Tone.POS, playbookStateFa("sealed"))
        assertEquals("پیش‌نویس" to Tone.GOLD, playbookStateFa("draft"))
        assertEquals("ایستاده" to Tone.SILVER, memberStateFa("paused"))
        assertEquals(listOf("اینستاگرام", "یوتیوب", "تلگرام", "سایت", "همه"), PB_PLATFORMS.map(::pbPlatformFa))
        assertEquals("همه‌ی پلتفرم‌ها", pbPlatformLineFa("any"))
        assertEquals("یوتیوب", pbPlatformLineFa("youtube"))
        // AI Studio carries Google's logo; an unknown helper its own name and no logo.
        assertEquals("google", helperOf("aistudio").provider)
        assertEquals("ChatGPT", helperOf("gpt").name)
        assertNull(helperOf("x").provider)
        assertEquals("کارشناس سئو", seatTitleFa(draft, "seo"))
        assertEquals("nobody", seatTitleFa(draft, "nobody"))
    }

    @Test
    fun whoItCanBeGivenToAndWhenItIsSealed() {
        val co = listOf(
            Company("1", "HQ", "holding", "هلدینگ"), Company("2", "TY", "company", "تریدیار"), Company("3", "FX", "company", "کوینه‌پرو FX"),
            Company("4", "PC", "company", "پرو-چارت"), Company("5", "OLD", "company", "قدیمی", status = "archived"),
        )
        val p = Playbook("PB-0001", titleFa = "t", state = "sealed", group = "pb_1", seats = listOf(PlaybookSeat("s", "r", "t")), members = listOf(PlaybookMember("TY", "تریدیار")))
        assertEquals(listOf("FX", "PC"), applyTargets(p, co).map { it.code })
        assertTrue(canApplyAsIs(p))
        assertFalse(canApplyAsIs(p.copy(group = null)))
        assertFalse(canApplyAsIs(p.copy(state = "draft")))
        assertTrue(canSeal(p.copy(state = "draft")))
        assertFalse(canSeal(p.copy(state = "draft", seats = emptyList())))
        assertFalse(canSeal(p.copy(state = "draft", titleFa = " ")))
    }

    @Test
    fun theCardNamesItsPlaybookAndMayCarryTheRewrite() {
        val only = playbookCardOf(Api.json.parseToJsonElement("""{"playbook":"pb-0002"}""").jsonObject)!!
        assertEquals("PB-0002", only.ref)
        assertNull(only.draft)
        val rewrite = playbookCardOf(Api.json.parseToJsonElement("""{"playbook":"PB-0002","draft":{"title_fa":"سئو","purpose_fa":"","platform":"site",
            "seats":[{"seat":"writer","role":"content_writer","title_fa":"نویسنده","duties_fa":"","helpers":["gpt","deepseek"]}],"routines":[],"kpis":[],"connections":[],"rules_fa":["با منبع"]}}""").jsonObject)!!
        assertEquals("PB-0002", rewrite.draft?.ref)
        assertEquals(listOf("gpt", "deepseek"), rewrite.draft?.seats?.single()?.helpers)
        // A payload that names no playbook: the card is drawn as any card.
        assertNull(playbookCardOf(Api.json.parseToJsonElement("""{"draft":{}}""").jsonObject))
        assertEquals("کارگروه از جلسه", cardInfo("playbook").fa)
        // A kind this app does not know still has a name and a «اجرا کن».
        assertEquals("کارت", cardInfo("survey").fa)
    }

    @Test
    fun theMemoryIsShownWithoutRefs() {
        assertEquals("- کارگروه «سئوی هفتگی» منتظر مُهر است.", withoutRefs("- کارگروه PB-0002 «سئوی هفتگی» منتظر مُهر است."))
        assertEquals("- دو پست کانال (کار) ساخته شد؛ فرمان باز است.", withoutRefs("- دو پست کانال (W-000310) ساخته شد؛ F-0101 باز است."))
        // Figures, model names and times stay as written.
        assertEquals("- ساعت 18:30، GPT-5 و 1200 کلمه", withoutRefs("- ساعت 18:30، GPT-5 و 1200 کلمه"))
        // A ref right after its own word goes, with the space before a mark; a list's indentation stays.
        assertEquals("# کارگروه: کمپین مناسبتی\n  سه ریلز", withoutRefs("# کارگروه PB-0001: کمپین مناسبتی\n  سه ریلز"))
        assertEquals("کار ساخته شد.", withoutRefs("کار W-000310 ساخته شد."))
        assertFalse(memoryFolds("## تصمیم‌ها\n- یک"))
        assertTrue(memoryFolds((1..12).joinToString("\n") { "- خط $it" }))
    }

    @Test
    fun aPlaybookRefOpensItsPage() {
        assertEquals("playbook/PB-0001", Refs.route("PB-0001"))
        assertEquals("کارگروه", madeFa("PB-0001"))
        // A planner item (PL-) is not a playbook.
        assertEquals("planner", Refs.route("PL-0004"))
        assertNotNull(PlaybookRoutine().maxTokens)
        assertEquals(PlaybookSource(), Playbook("PB-0001").source)
    }
}
