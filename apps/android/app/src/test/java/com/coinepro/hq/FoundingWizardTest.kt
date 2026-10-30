package com.coinepro.hq

import com.coinepro.hq.core.data.FoundingBrandStore
import com.coinepro.hq.core.data.FoundingBrief
import com.coinepro.hq.core.data.FoundingDraft
import com.coinepro.hq.core.data.FoundingPath
import com.coinepro.hq.core.data.FoundingRules
import com.coinepro.hq.core.data.FoundingStages
import com.coinepro.hq.core.net.Founding
import com.coinepro.hq.core.net.FoundingSource
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** The one way to found a company: four steps, each checked before the next, and a brief the hub keeps with the owner's name and code. */
class FoundingWizardTest {
    private val taken = setOf("HQ", "TY", "FX", "PC", "AC")
    private val ok = FoundingDraft("دایرکت هوشمند", "IG", "پاسخ خودکار و فروش در دایرکت اینستاگرام", FoundingPath.IDEA, idea = "دستیار دایرکت برای فروشگاه‌های اینستاگرامی؛ پاسخ، پیگیری سفارش و فروش.")

    @Test
    fun theCodeIsTwoToFourLatinLetters() {
        assertEquals("IG", FoundingRules.cleanCode("ig"))
        assertEquals("ABCD", FoundingRules.cleanCode("a-b c1d2e"))
        assertEquals("", FoundingRules.cleanCode("۱۲۳ابپ"))
        assertNull(FoundingRules.codeError("IG", taken))
        assertNull(FoundingRules.codeError("SMRT", taken))
        assertNotNull(FoundingRules.codeError("", taken))
        assertNotNull(FoundingRules.codeError("I", taken))
        assertNotNull(FoundingRules.codeError("ABCDE", taken))
        assertNotNull(FoundingRules.codeError("I9", taken))
        assertNotNull(FoundingRules.codeError("ig", taken))
        assertEquals("HQ کد هلدینگ است.", FoundingRules.codeError("HQ", taken))
        assertEquals("TY را شرکت یا تأسیس دیگری دارد.", FoundingRules.codeError("TY", taken))
    }

    @Test
    fun theNameIsPersianAndTheLineIsOneLine() {
        assertNull(FoundingRules.nameError("دایرکت هوشمند"))
        assertNull(FoundingRules.nameError("IG دایرکت"))
        assertNotNull(FoundingRules.nameError(""))
        assertNotNull(FoundingRules.nameError("Smart Direct"))
        assertNotNull(FoundingRules.nameError("د"))
        assertNull(FoundingRules.taglineError("پاسخ خودکار در دایرکت"))
        assertNotNull(FoundingRules.taglineError("کم"))
        assertNotNull(FoundingRules.taglineError("ا".repeat(141)))
    }

    @Test
    fun eachStepBlocksUntilItIsComplete() {
        val empty = FoundingDraft()
        assertEquals(setOf("name", "code", "tagline"), FoundingRules.errors(1, empty, taken).keys)
        assertEquals(1, FoundingRules.firstIncomplete(empty, taken))
        val who = empty.copy(nameFa = ok.nameFa, code = ok.code, tagline = ok.tagline)
        assertTrue(FoundingRules.errors(1, who, taken).isEmpty())
        assertEquals(2, FoundingRules.firstIncomplete(who, taken))
        assertEquals(setOf("path"), FoundingRules.errors(2, who, taken).keys)
        // An idea needs a sentence; a repository a real address; registering needs nothing more.
        assertNotNull(FoundingRules.pathError(who.copy(path = FoundingPath.IDEA, idea = "کوتاه")))
        assertNull(FoundingRules.pathError(ok))
        assertNotNull(FoundingRules.pathError(who.copy(path = FoundingPath.REPO, repo = "not a repo")))
        assertNull(FoundingRules.pathError(who.copy(path = FoundingPath.REPO, repo = "https://github.com/behnamjalalico/signal-bot.git")))
        assertNull(FoundingRules.pathError(who.copy(path = FoundingPath.REGISTER)))
        assertNotNull(FoundingRules.pathError(who.copy(path = FoundingPath.REGISTER, nameEn = "دایرکت")))
        // The brand is optional; a colour is one of the eight.
        assertTrue(FoundingRules.errors(3, ok, taken).isEmpty())
        assertTrue(FoundingRules.errors(3, ok.copy(colorIndex = 4, logoFileId = "f1"), taken).isEmpty())
        assertFalse(FoundingRules.errors(3, ok.copy(colorIndex = 9), taken).isEmpty())
        assertNull(FoundingRules.firstIncomplete(ok, taken))
        // The review gathers every step's errors.
        assertEquals(setOf("code"), FoundingRules.errors(4, ok.copy(code = "TY"), taken).keys)
    }

    @Test
    fun aRepositoryIsReadFromWhatWasPasted() {
        for (s in listOf("owner/name", "github.com/owner/name", "https://github.com/owner/name", "https://www.github.com/owner/name/", "https://github.com/owner/name.git", " owner/name "))
            assertEquals(s, "owner/name", FoundingRules.repo(s))
        for (s in listOf("", "owner", "https://gitlab.com/owner/name", "owner/name/tree/main", "own er/name")) assertNull(s, FoundingRules.repo(s))
    }

    @Test
    fun theBriefCarriesTheNameAndCodeAndReadsBack() {
        val brief = FoundingRules.brief(ok)
        assertTrue(brief.startsWith("نام: دایرکت هوشمند\nکد: IG\nدر یک خط: "))
        val p = FoundingBrief.parse(brief)
        assertEquals("دایرکت هوشمند", p.nameFa)
        assertEquals("IG", p.code)
        assertEquals(ok.tagline, p.tagline)
        assertEquals(ok.idea, p.body)
        // A repository's brief has no body; an old brief (free text) has no name.
        assertEquals("", FoundingBrief.parse(FoundingRules.brief(ok.copy(path = FoundingPath.REPO, repo = "a/b"))).body)
        val old = FoundingBrief.parse("دستیار مالیات و حسابداری برای معامله‌گرهای کریپتو")
        assertNull(old.nameFa)
        assertEquals("دستیار مالیات و حسابداری برای معامله‌گرهای کریپتو", old.body)
        // The founding shows the owner's name before the proposal names it.
        val f = Founding(ref = "C-0004", source = FoundingSource("idea", null, brief), state = "auditing", createdAt = "", updatedAt = "")
        assertEquals("دایرکت هوشمند", f.title)
        assertEquals("ایده‌ی تازه", f.copy(source = FoundingSource("idea", null, "free text")).title)
    }

    @Test
    fun anIdeaHasNoAuditStage() {
        assertEquals("ممیزی", FoundingStages.of("repo").first().fa)
        assertEquals("نوشتن پیشنهاد", FoundingStages.of("idea").first().fa)
        assertEquals(listOf("auditing", "proposed", "sealed", "provisioning", "ready_for_login", "active"), FoundingStages.of("idea").map { it.state })
        assertEquals("پیشنهاد در حال نوشتن است", FoundingStages.now("auditing", "idea", false).title)
        assertEquals("ممیزی فقط‌خواندنی ریپو در جریان است", FoundingStages.now("auditing", "repo", false).title)
        assertEquals("پیشنهاد در حال نوشتن است", FoundingStages.now("auditing", "repo", true).title)
        assertTrue(FoundingStages.now("proposed", "idea", false).ownersTurn)
        assertTrue(FoundingStages.now("ready_for_login", "repo", true).ownersTurn)
        assertFalse(FoundingStages.now("provisioning", "repo", true).ownersTurn)
    }

    @Test
    fun theLogoWaitsOnThePhoneUntilTheCompanyExists() {
        assertEquals("f1|4", FoundingBrandStore.encode(FoundingBrandStore.Pending("f1", 4)))
        assertEquals(FoundingBrandStore.Pending(null, 2), FoundingBrandStore.decode("|2"))
        assertEquals(FoundingBrandStore.Pending("f1", null), FoundingBrandStore.decode("f1|"))
        val store = FoundingBrandStore.memory()
        store.put("C-0004", FoundingBrandStore.Pending("f1", 3))
        assertEquals(3, store.get("C-0004")?.colorIndex)
        store.put("C-0004", FoundingBrandStore.Pending(null, null))
        assertNull(store.get("C-0004"))
    }
}
