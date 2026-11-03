package com.coinepro.hq

import com.coinepro.hq.designsystem.axisOf
import org.junit.Assert.assertEquals
import org.junit.Test

/** The KPI chart's axis (owner's screenshot, 2026-11-03): a day of zeros read «2, 2, 1, 1, 0» (0.5 steps rounded); whole-number
 *  series get whole steps, so no two ticks read alike. */
class ChartAxisTest {
    private fun ticks(values: List<Double>): List<Double> = axisOf(values).let { (_, step) -> (0..4).map { it * step } }

    @Test
    fun zeros_and_small_counts_step_by_whole_numbers() {
        assertEquals(listOf(0.0, 1.0, 2.0, 3.0, 4.0), ticks(listOf(0.0, 0.0, 0.0)))
        assertEquals(listOf(0.0, 1.0, 2.0, 3.0, 4.0), ticks(listOf(1.0, 2.0)))
        assertEquals(listOf(0.0, 2.0, 4.0, 6.0, 8.0), ticks(listOf(7.0)))
        assertEquals(listOf(0.0, 5000.0, 10000.0, 15000.0, 20000.0), ticks(listOf(12190.0, 8879.0, 4006.0)))
    }

    @Test
    fun fractions_keep_quarters_of_a_nice_top() {
        val (top, step) = axisOf(listOf(1.84, 0.4))
        assertEquals(2.0, top, 1e-9)
        assertEquals(0.5, step, 1e-9)
    }
}
