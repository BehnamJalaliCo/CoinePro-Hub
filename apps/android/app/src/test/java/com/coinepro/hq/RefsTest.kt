package com.coinepro.hq

import com.coinepro.hq.core.data.Refs
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** One router for every ref: each prefix opens its own page, and only a work item ever reaches the work page (0.4.0 sent `MT-0077`
 *  there, and `GET /work/MT-0077` is `422 validation_failed`). */
class RefsTest {
    @Test
    fun everyPrefixOpensItsOwnPage() {
        val cases = mapOf(
            "W-000104" to "work/W-000104", "MT-0077" to "meetings/MT-0077", "D-000017" to "cartable/D-000017", "O-000030" to "outputs/O-000030",
            "AR-000092" to "archive/AR-000092", "PL-0004" to "planner", "S-0005" to "workshop/S-0005", "G-0003" to "workshop", "AP-0012" to "workshop",
            "C-0002" to "founding/C-0002", "PV-0003" to "founding/PV-0003", "FI-0212" to "oversight", "H-0004" to "oversight", "CH-0002" to "oversight",
            "SO-0001" to "oversight", "Q-0007" to "advisor", "E-0011" to "assistant", "I-0005" to "sites", "TE-0003" to "academy",
            "SC-000411" to "support/SC-000411", "FB-0009" to "feedback", "TM-0002" to "growth", "LR-0003" to "growth", "RC-0004" to "growth",
            "K-0012" to "knowledge/K-0012", "KB-0003" to "knowledge/KB-0003", "OB-0001" to "okr", "KR-0002" to "okr", "RK-0005" to "risks/RK-0005",
            "CE-0010" to "calendar", "OR-0001" to "outcomes", "M-0007" to "resolutions", "B-0002" to "cartable", "NT-0004" to "notes/NT-0004",
            "BR-0002" to "letter/BR-0002", "CR-0006" to "substitutes/CR-0006", "DM-0001" to "advisor", "WR-0001" to "advisor", "DP-0003" to "digital-ceo",
            "CL-0009" to "runs", "AK-0002" to "home", "SR-0001" to "series/SR-0001", "MI-0004" to "studio/MI-0004", "LC-0002" to "legal/LC-0002",
            "RD-0001" to "roles/RD-0001", "L-0003" to "messages/L", "LH-0002" to "archive-holds/LH-0002", "PT-0007" to "archive-in/party/PT-0007",
            "FP-0001" to "archive-in/folder/FP-0001", "RR-0002" to "archive-settings/retention/RR-0002", "RM-0003" to "archive-settings/reminders/RM-0003",
            "AU-0001" to "archive-settings/automations/AU-0001", "TY@3" to "charter", "holding@2" to "charter",
        )
        for ((ref, route) in cases) assertEquals(ref, route, Refs.route(ref))
    }

    @Test
    fun aLongerPrefixIsNeverReadAsAShorterOne() {
        assertEquals("meetings/MT-0001", Refs.route("MT-0001"))
        assertEquals("resolutions", Refs.route("M-0001"))
        assertEquals("archive/AR-000001", Refs.route("AR-000001"))
        assertEquals("founding/C-0001", Refs.route("C-0001"))
        assertEquals("oversight", Refs.route("CH-0001"))
    }

    @Test
    fun whatIsNotARefHasNoPage() {
        for (s in listOf("", "FX-CEO", "W-", "w0", "0193b1c2-0005-7d4f-8a2e-0000005a1005", "ZZ-0001", "MT 0077", "F-0001", "TY")) assertNull(s, Refs.route(s))
    }

    @Test
    fun onlyAWorkRefOrAnIdStaysOnTheWorkPage() {
        assertEquals("work/W-000104", Refs.normalize("work/W-000104"))
        assertEquals("work/0193b1c2-0005-7d4f-8a2e-0000005a1005", Refs.normalize("work/0193b1c2-0005-7d4f-8a2e-0000005a1005"))
        // The owner's 0.4.0 bug: a meeting's ref on its way to the work page goes to the meeting room.
        assertEquals("meetings/MT-0077", Refs.normalize("work/MT-0077"))
        assertEquals("cartable/D-000017", Refs.normalize("work/D-000017"))
        assertEquals("founding/C-0002", Refs.normalize("work/C-0002"))
        // A ref with no page goes nowhere rather than to a 422.
        assertNull(Refs.normalize("work/F-0001"))
        assertNull(Refs.normalize("work/"))
        // Other routes pass untouched.
        assertEquals("meetings/MT-0012", Refs.normalize("meetings/MT-0012"))
        assertEquals("companies/FX", Refs.normalize("companies/FX"))
    }

    @Test
    fun aNotificationsLinkOpensWhatItIsAbout() {
        assertEquals("cartable/D-000017", Refs.forLink("decision", "D-000017"))
        assertEquals("outputs/O-000030", Refs.forLink("deliverable", "O-000030"))
        assertEquals("work/W-000101", Refs.forLink("work", "W-000101"))
        // A "work" link that carries another kind of ref goes to that ref's page.
        assertEquals("meetings/MT-0077", Refs.forLink("work", "MT-0077"))
        assertEquals("oversight", Refs.forLink("finding", "FI-0212"))
        assertEquals("oversight", Refs.forLink("hold", "H-0004"))
        assertEquals("meetings/MT-0012", Refs.forLink("meeting", "MT-0012"))
        assertEquals("founding/C-0001", Refs.forLink("founding", "C-0001"))
        // provision_run carries the run's id when there is no founding.
        assertEquals("founding", Refs.forLink("provision_run", "4b0f1c9e-1111-4222-8333-944455556666"))
        assertEquals("founding/PV-0003", Refs.forLink("server_plan", "PV-0003"))
        assertEquals("workshop/S-0004", Refs.forLink("code_session", "S-0004"))
        assertEquals("archive/AR-000092", Refs.forLink("archive_record", "AR-000092"))
        assertEquals("support/SC-000411", Refs.forLink("support_conversation", "SC-000411"))
        assertEquals("treasury", Refs.forLink("treasury", "budget:company:TY:month"))
        assertEquals("employees/TY-GROWTH-01", Refs.forLink("employee", "TY-GROWTH-01"))
        assertEquals("advisor", Refs.forLink("message", "MSG-1"))
        assertEquals("control", Refs.forLink("backup", "BK-0091"))
        assertEquals("settings", Refs.forLink("device", "x"))
        assertEquals("messages/TY-CEO", Refs.forLink("thread", "TY-CEO"))
        assertNull(Refs.forLink(null, null))
        assertEquals("outputs/O-000001", Refs.forLink(null, "O-000001"))
    }

    @Test
    fun aPlannerRowOpensByItsKind() {
        assertEquals("work/W-1000", Refs.forPlanner("work", "W-1000"))
        assertEquals("meetings/MT-0077", Refs.forPlanner("meeting", "MT-0077"))
        assertEquals("calendar", Refs.forPlanner("calendar", "CE-0010"))
        assertNull(Refs.forPlanner("reminder", "PL-0004"))
        // An older hub without `kind`: the ref still decides.
        assertEquals("meetings/MT-0077", Refs.forPlanner("work", "MT-0077"))
    }

    @Test
    fun prefixesAndKinds() {
        assertEquals("MT", Refs.prefix("MT-0077"))
        assertTrue(Refs.isWork("W-000001"))
        assertTrue(Refs.isUuid("0193b1c2-0005-7d4f-8a2e-0000005a1005"))
        assertNull(Refs.prefix("FX-CEO"))
    }
}
