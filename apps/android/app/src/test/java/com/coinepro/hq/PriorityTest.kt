package com.coinepro.hq

import com.coinepro.hq.core.format.DEFAULT_PRIORITY
import com.coinepro.hq.core.format.PRIORITIES
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.format.isUrgentPriority
import com.coinepro.hq.core.format.priority
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** Priorities as the owner reads them: a Persian name, the code, and what it means for the queue (OPERATING_MODEL, contract §16.5). */
class PriorityTest {
    @Test
    fun everyCodeHasItsNameAndMeaning() {
        assertEquals(listOf("P0", "P1", "P2", "P3", "P4"), PRIORITIES.map { it.code })
        assertEquals(listOf("اضطراری", "فوری", "مهم", "عادی", "هر وقت شد"), PRIORITIES.map { it.fa })
        assertTrue(priority("P0").line.contains("کلید توقف"))
        assertTrue(priority("P1").line.contains("کاربران"))
        assertTrue(priority("P2").line.contains("رزرو"))
        assertTrue(priority("P4").line.contains("سهمیه"))
        // Every line is one sentence the owner can read: Persian words, no bare code.
        for (p in PRIORITIES) assertFalse(p.line.contains(p.code))
    }

    @Test
    fun theDefaultIsNormalAndTheTonesKeepTheirMeaning() {
        assertEquals("P3", DEFAULT_PRIORITY)
        assertEquals("عادی", priority(DEFAULT_PRIORITY).fa)
        // Red is the emergency's alone; amber what users see; the rest stay quiet.
        assertEquals(Tone.NEG, priority("P0").tone)
        assertEquals(Tone.WARN, priority("P1").tone)
        assertEquals(1, PRIORITIES.count { it.tone == Tone.NEG })
        assertTrue(isUrgentPriority("P0") && isUrgentPriority("P1"))
        assertFalse(isUrgentPriority("P2") || isUrgentPriority("P4"))
    }

    @Test
    fun unknownOrOddCodesAreTolerated() {
        assertEquals("فوری", priority(" p1 ").fa)
        assertEquals("P9", priority("P9").fa)
        assertEquals("—", priority(null).code)
    }
}
