package com.coinepro.hq

import com.coinepro.hq.designsystem.MdAlign
import com.coinepro.hq.designsystem.MdBlock
import com.coinepro.hq.designsystem.MdParser
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** The Markdown the hub writes, parsed into the blocks the app draws: the rule-based morning report (worker/report.py) with its
 *  table, the meeting and weekly-review minutes with nested lists, quotes, code and rules; and the table's column widths. */
class MarkdownTest {
    /** worker/report.py `render` for two companies, as the hub writes it. */
    private val morning = """
        # گزارش صبحگاهی — شنبه ۲۵ مهر ۱۴۰۵ (2026-10-17)

        > نسخه‌ی قاعده‌محور، بدون مدل: همه‌ی عددها مستقیم از دیتابیس هاب.

        ## صندوق‌ها
        - **کارتابل تصمیم:** 4 مورد در انتظار (ریسک بالا: 1، ریسک کم: 3)
        - **کارتابل خروجی:** 6 خروجی در ۲۴ ساعت گذشته؛ 5 خروجی هنوز امتیاز ندارد
        - **پیام‌ها:** 3 پیام نخوانده
        - **یادآوری کارتابل:** 4 کارت منتظر تو: 2 زیر ۲۴ ساعت، 2 بین ۱ تا ۳ روز، 0 بین ۳ تا ۷ روز، 0 بیش از ۷ روز.

        ## شرکت‌ها
        | شرکت | تصمیم در انتظار | کار باز | عقب‌افتاده | خروجی تازه | فراخوانی مدل دیروز | توکن دیروز | هزینه‌ی دیروز (USD) | کلید توقف |
        |---|---|---|---|---|---|---|---|---|
        | هلدینگ کوینه‌پرو (HQ) | 3 | 12 | 1 | 2 | 412 | 1840221 | 4.1200 | — |
        | پرو-چارت (PC) | 1 | 7 | 0 | 1 | 120 | 402331 | 0.9900 | فعال |

        ## بودجه‌ها
        - هیچ بودجه‌ای به آستانه‌ی هشدار (۷۰٪) نرسیده است.

        **کلید توقف فعال:** PC
    """.trimIndent() + "\n"

    @Test
    fun theMorningReportIsHeadingsAQuoteListsAndATable() {
        val b = MdParser.parse(morning)
        assertEquals(
            listOf("Heading", "Quote", "Heading", "ListBlock", "Heading", "Table", "Heading", "ListBlock", "Para"),
            b.map { it::class.simpleName },
        )
        assertEquals(1, (b[0] as MdBlock.Heading).level)
        assertEquals(4, (b[3] as MdBlock.ListBlock).items.size)
        val t = b[5] as MdBlock.Table
        assertEquals(9, t.columns)
        assertEquals("شرکت", t.header.first())
        assertEquals("هزینه‌ی دیروز (USD)", t.header[7])
        assertEquals(2, t.rows.size)
        assertEquals(listOf("هلدینگ کوینه‌پرو (HQ)", "3", "12", "1", "2", "412", "1840221", "4.1200", "—"), t.rows[0])
        assertTrue(t.align.all { it == MdAlign.NONE })
        // Every column but the company and the kill switch is figures (Latin, centred).
        assertEquals(listOf(false, true, true, true, true, true, true, true, false), MdParser.figureColumns(t))
        assertEquals("**کلید توقف فعال:** PC", (b[8] as MdBlock.Para).text)
    }

    @Test
    fun minutesNestTheirClaimsUnderEachStatementAndEndWithAParagraph() {
        val md = """
            # صورت‌جلسه‌ی MT-0004: بودجه‌ی فصل
            نوع board · حالت discussion · پایان: done
            ## دستور 1: بودجه (closed)
            - بیانیه · TY-CEO: افزایش ده درصدی
              - ادعا: رشد 12٪ (kpi:signups)
            - **پیش‌نویس مصوبه** (TY-CEO): بودجه 10٪ بیشتر
              - رأی‌ها: موافق 3، مخالف 1، ممتنع 0
            پیش‌نویس‌ها فقط با مُهر مدیر کل مصوبه میشوند.
        """.trimIndent()
        val b = MdParser.parse(md)
        assertEquals(listOf("Heading", "Para", "Heading", "ListBlock", "Para"), b.map { it::class.simpleName })
        val list = b[3] as MdBlock.ListBlock
        assertEquals(2, list.items.size)
        val nested = list.items[0].children.single() as MdBlock.ListBlock
        assertEquals("ادعا: رشد 12٪ (kpi:signups)", nested.items.single().text)
        assertEquals("پیش‌نویس‌ها فقط با مُهر مدیر کل مصوبه میشوند.", (b[4] as MdBlock.Para).text)
    }

    @Test
    fun orderedListsCodeRulesAndContinuations() {
        val md = "1. [kind] W-000104: کار — انجام شد\n   - یادداشت مالک: خوب\n2. دوم\n   ادامه‌ی دوم\n\n---\n\n```bash\nmake owner-enroll\n```\n"
        val b = MdParser.parse(md)
        assertEquals(listOf("ListBlock", "Rule", "Code"), b.map { it::class.simpleName })
        val l = b[0] as MdBlock.ListBlock
        assertTrue(l.ordered)
        assertEquals("دوم ادامه‌ی دوم", l.items[1].text)
        assertEquals("یادداشت مالک: خوب", ((l.items[0].children.single()) as MdBlock.ListBlock).items.single().text)
        assertEquals(MdBlock.Code("bash", "make owner-enroll"), b[2])
    }

    @Test
    fun tableCellsKeepEscapedPipesAndCodeAndPadShortRows() {
        val md = "| a | b |\n|:--|--:|\n| x \\| y | `p|q` |\n| only |\n"
        val t = MdParser.parse(md).single() as MdBlock.Table
        assertEquals(listOf(MdAlign.LEFT, MdAlign.RIGHT), t.align)
        assertEquals(listOf("x | y", "`p|q`"), t.rows[0])
        assertEquals(listOf("only", ""), t.rows[1])
    }

    @Test
    fun aPipeInProseIsNotATable() {
        val b = MdParser.parse("نسبت a|b در متن\nخط دوم")
        assertEquals(listOf(MdBlock.Para("نسبت a|b در متن خط دوم")), b)
    }

    @Test
    fun figures() {
        for (f in listOf("3", "1840221", "4.1200", "$1.84", "72%", "۷۰٪", "12.5K", "(3)", "-1.20")) assertTrue(f, MdParser.isFigure(f))
        for (t in listOf("—", "فعال", "پرو-چارت (PC)", "TY-CEO", "")) assertFalse(t, MdParser.isFigure(t))
    }

    @Test
    fun columnsFillTheCardOrKeepTheirWidthAndScroll() {
        // Narrow content fills the available width in proportion; the sum is exact.
        val fill = MdParser.columnWidths(listOf(100, 50, 50), available = 400, min = 40, max = 300, padding = 0)
        assertEquals(400, fill.sum())
        assertEquals(200, fill[0])
        // Wide content keeps its widths (capped) and the table scrolls sideways.
        val wide = MdParser.columnWidths(List(9) { 180 }, available = 1000, min = 56, max = 150, padding = 0)
        assertEquals(List(9) { 150 }, wide)
        // A cell narrower than the minimum still gets the minimum.
        assertEquals(listOf(56, 2000), MdParser.columnWidths(listOf(10, 2000), available = 300, min = 56, max = 2000, padding = 0))
    }
}
