package com.coinepro.hq

import com.coinepro.hq.core.format.ago
import com.coinepro.hq.core.format.modelLabel
import com.coinepro.hq.core.format.pct
import com.coinepro.hq.core.format.tokens
import com.coinepro.hq.core.format.until
import com.coinepro.hq.core.format.usd
import java.time.Instant
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

/** Formatting uses android.icu (Jalali calendar), so it runs on Robolectric. */
@RunWith(RobolectricTestRunner::class)
class FormatTest {
    private val now = Instant.parse("2026-10-17T12:00:00Z").toEpochMilli()

    @Test
    fun tokensAreCompactFigures() {
        assertEquals("950", tokens(950))
        assertEquals("1.5K", tokens(1_500))
        assertEquals("160K", tokens(160_400))
        assertEquals("6.2M", tokens(6_240_000))
        assertEquals("30M", tokens(30_000_000))
        assertEquals("—", tokens(null))
    }

    @Test
    fun moneyAndPercent() {
        assertEquals("$2.94", usd("2.94"))
        assertEquals("$1,234.50", usd("1234.5"))
        assertEquals("—", usd(null as String?))
        assertEquals("21٪", pct(21.4))
    }

    @Test
    fun modelNamesStayLatin() {
        assertEquals("Sonnet 5.5", modelLabel("claude-sonnet-5-5"))
        assertEquals("Opus 5.5", modelLabel("claude-opus-5-5"))
        assertEquals("gpt-x", modelLabel("gpt-x"))
    }

    @Test
    fun relativeTimes() {
        assertEquals("همین الان", ago("2026-10-17T11:59:40Z", now))
        assertEquals("5 دقیقه پیش", ago("2026-10-17T11:55:00Z", now))
        assertEquals("3 ساعت پیش", ago("2026-10-17T09:00:00+00:00", now))
        assertEquals("30 دقیقه مانده", until("2026-10-17T12:30:00Z", now))
        assertEquals("گذشته", until("2026-10-17T11:00:00Z", now))
    }
}
