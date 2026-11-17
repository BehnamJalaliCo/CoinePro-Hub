package com.coinepro.hq.core.data

import com.coinepro.hq.core.format.OWNER_TZ
import com.coinepro.hq.core.format.Tone
import com.coinepro.hq.core.net.PlannedItem
import com.coinepro.hq.core.net.PubCalendarDay
import com.coinepro.hq.core.net.Publication
import com.coinepro.hq.core.net.PublicationCard
import com.coinepro.hq.core.net.PublishToday
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId

// ⟨1.39⟩ Contract §60, the publish centre: what the screens say and how they lay a day, a month and a page out. Pure, so the tests read it
// without a device; the Jalali calendar is the arithmetic one (no ICU), right for this era.

private val TEHRAN: ZoneId = ZoneId.of(OWNER_TZ)

/** An instant from the hub's ISO text (with or without its offset), without the formatting module's ICU (so the tests read it). */
internal fun instant(iso: String?): Instant? = iso?.let { s ->
    runCatching { Instant.parse(s) }.getOrNull() ?: runCatching { java.time.OffsetDateTime.parse(s).toInstant() }.getOrNull()
        ?: runCatching { java.time.LocalDateTime.parse(s).atZone(java.time.ZoneOffset.UTC).toInstant() }.getOrNull()
}
private val FA_DIGITS = charArrayOf('۰', '۱', '۲', '۳', '۴', '۵', '۶', '۷', '۸', '۹')

/** "09:30" → «۰۹:۳۰» ([faNum] of Playbooks.kt for a count). */
fun faText(s: String): String = s.map { if (it in '0'..'9') FA_DIGITS[it - '0'] else it }.joinToString("")

// ------------------------------------------------------------------------------------------------------------- words --
val PUB_KIND_FA: Map<String, String> = linkedMapOf(
    "reel" to "ریلز", "story" to "استوری", "post" to "پست", "carousel" to "کاروسل", "short" to "شورت", "video" to "ویدیو",
    "tg_post" to "پست تلگرام", "article" to "مقاله", "stories" to "استوری‌ها",
)
fun pubKindFa(kind: String): String = PUB_KIND_FA[kind] ?: kind

/** The channels a row can be of; today only Instagram has rows, the rest show dim until their route exists. */
val PUB_CHANNELS: List<String> = listOf("instagram", "youtube", "telegram", "website")
fun pubChannelFa(ch: String): String = when (ch) {
    "instagram" -> "اینستاگرام"; "youtube" -> "یوتیوب"; "telegram" -> "تلگرام"; "website" -> "سایت"; "x" -> "ایکس"; "newsletter" -> "خبرنامه"
    else -> ch
}

/** A row's state in one word, and its tone. */
fun pubStateFa(state: String): String = when (state) {
    "scheduled" -> "زمان‌بندی"
    "publishing" -> "در حال انتشار"
    "published" -> "منتشر شد"
    "held" -> "نگه‌داشته"
    "failed" -> "ناموفق"
    "cancelled" -> "لغو شد"
    else -> state
}
fun pubStateTone(state: String): Tone = when (state) {
    "published" -> Tone.POS
    "publishing" -> Tone.LAPIS
    "held" -> Tone.WARN
    "failed" -> Tone.NEG
    "scheduled" -> Tone.GOLD
    else -> Tone.NEUTRAL
}
/** The line under a held row when the hub sent none. */
const val PUB_HELD_FA = "صفحه بسته است؛ به محض باز شدن پیج میرود"

/** A set's progress: «۲ از ۷». */
fun setProgressFa(done: Int, n: Int): String = "${faNum(done)} از ${faNum(n)}"

/** «۷ استوری» · «۱۲ اسلاید». */
fun setSizeFa(n: Int, slides: Boolean): String = "${faNum(n)} ${if (slides) "اسلاید" else "استوری"}"

/** The account with its @, isolated left to right. */
fun atHandle(account: String): String = if (account.isBlank()) "" else "@${account.removePrefix("@")}"

// ------------------------------------------------------------------------------------------------- time and countdown --
fun tehranDate(iso: String?): LocalDate? = instant(iso)?.atZone(TEHRAN)?.toLocalDate()
fun tehranMinutes(iso: String?): Int? = instant(iso)?.atZone(TEHRAN)?.let { it.hour * 60 + it.minute }

/** «۰۹:۳۰» in Tehran, Persian digits (the centre's hour column). */
fun faHour(iso: String?): String {
    val m = tehranMinutes(iso) ?: return "—"
    return faText("%02d:%02d".format(m / 60, m % 60))
}

/** How long until [iso]: «۲۰ دقیقه», «۱ ساعت و ۲۰ دقیقه», «۳ ساعت»; past: null. */
fun countdownFa(iso: String?, nowMs: Long): String? {
    val t = instant(iso)?.toEpochMilli() ?: return null
    val m = ((t - nowMs) / 60_000.0).let { kotlin.math.ceil(it).toLong() }
    if (m <= 0) return null
    if (m < 60) return "${faNum(m.toInt())} دقیقه"
    val h = m / 60
    val r = m % 60
    if (h >= 24) return "${faNum((h / 24).toInt())} روز"
    return if (r == 0L || h >= 6) "${faNum(h.toInt())} ساعت" else "${faNum(h.toInt())} ساعت و ${faNum(r.toInt())} دقیقه"
}

// ------------------------------------------------------------------------------------------------------- today's line --
/** One line of «امروز»: a row (or a set as one), something still to be made, or the «اکنون» mark between what went and what comes. */
sealed interface DayRow {
    val minute: Int
    data class Item(val card: PublicationCard, override val minute: Int) : DayRow
    data class Plan(val plan: PlannedItem, override val minute: Int) : DayRow
    data class Now(override val minute: Int) : DayRow
}

/** Rows and plans of [today] in their hour's order, the «اکنون» mark at [nowMs] (Tehran); a row whose day is not today stays out. */
fun dayRows(today: PublishToday, nowMs: Long, account: String? = null): List<DayRow> {
    val day = today.day.ifBlank { null }?.let { runCatching { LocalDate.parse(it) }.getOrNull() } ?: Instant.ofEpochMilli(nowMs).atZone(TEHRAN).toLocalDate()
    val keep: (String) -> Boolean = { a -> account == null || a.equals(account, ignoreCase = true) }
    val items = today.items.filter { keep(it.account) }.mapNotNull { c ->
        val d = tehranDate(c.at) ?: return@mapNotNull null
        if (d != day) null else DayRow.Item(c, tehranMinutes(c.at) ?: 0)
    }
    val plans = today.planned.filter { keep(it.account) }.map { DayRow.Plan(it, tehranMinutes(it.publishAt) ?: 0) }
    val nowMin = Instant.ofEpochMilli(nowMs).atZone(TEHRAN).let { it.hour * 60 + it.minute }
    // Ties: a row before a plan; within each, as the hub gave them.
    val sorted = (items + plans).sortedWith(compareBy<DayRow> { it.minute }.thenBy { if (it is DayRow.Item) 0 else 1 })
    val out = ArrayList<DayRow>(sorted.size + 1)
    var placed = false
    for (r in sorted) {
        if (!placed && r.minute > nowMin) { out += DayRow.Now(nowMin); placed = true }
        out += r
    }
    if (!placed) out += DayRow.Now(nowMin)
    return out
}

/** The accounts of today's line, in the order they first appear (the chips «همه‌ی پیج‌ها · @…»). */
fun dayAccounts(today: PublishToday): List<String> =
    (today.items.map { it.account } + today.planned.map { it.account }).filter { it.isNotBlank() }.distinct()

/** The home card's line under its counts: the held one, said plainly; null when nothing is held. */
fun heldLineFa(today: PublishToday): String? {
    val held = today.items.filter { it.state == "held" }
    if (held.isEmpty()) return null
    val first = held.first()
    val what = if (first.set != null || first.kind == "story") "یک استوری" else "یک ${pubKindFa(first.kind)}"
    return if (held.size == 1) "$what ${atHandle(first.account)} نگه‌داشته است؛ صفحه بسته است و به محض باز شدن میرود."
    else "${faNum(held.size)} مورد نگه‌داشته است؛ هر کدام به محض باز شدن صفحه‌اش میرود."
}

/** The latest that went out, newest first, at most [n] (the home card's strip). */
fun latestOut(today: PublishToday, n: Int = 5): List<PublicationCard> =
    today.items.filter { it.state == "published" || (it.set?.done ?: 0) > 0 }.sortedByDescending { instant(it.at) }.take(n)

// ------------------------------------------------------------------------------------------------- the Jalali month --
/** A Jalali date. Months 1–6 have 31 days, 7–11 have 30, the 12th 29 or 30. */
data class JDate(val y: Int, val m: Int, val d: Int)

private val GDM = intArrayOf(0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)

fun toJalali(g: LocalDate): JDate {
    val gy = g.year; val gm = g.monthValue; val gd = g.dayOfMonth
    val gy2 = if (gm > 2) gy + 1 else gy
    var days = 355666 + 365 * gy + (gy2 + 3) / 4 - (gy2 + 99) / 100 + (gy2 + 399) / 400 + gd + GDM[gm - 1]
    var jy = -1595 + 33 * (days / 12053)
    days %= 12053
    jy += 4 * (days / 1461)
    days %= 1461
    if (days > 365) { jy += (days - 1) / 365; days = (days - 1) % 365 }
    return if (days < 186) JDate(jy, 1 + days / 31, 1 + days % 31) else JDate(jy, 7 + (days - 186) / 30, 1 + (days - 186) % 30)
}

fun fromJalali(j: JDate): LocalDate {
    val jy1 = j.y + 1595
    var days = -355668 + 365 * jy1 + (jy1 / 33) * 8 + ((jy1 % 33) + 3) / 4 + j.d + (if (j.m < 7) (j.m - 1) * 31 else (j.m - 7) * 30 + 186)
    var gy = 400 * (days / 146097)
    days %= 146097
    if (days > 36524) {
        days -= 1
        gy += 100 * (days / 36524)
        days %= 36524
        if (days >= 365) days += 1
    }
    gy += 4 * (days / 1461)
    days %= 1461
    if (days > 365) { gy += (days - 1) / 365; days = (days - 1) % 365 }
    return LocalDate.of(gy, 1, 1).plusDays(days.toLong())
}

fun jMonthLength(y: Int, m: Int): Int = when {
    m <= 6 -> 31
    m <= 11 -> 30
    else -> (fromJalali(JDate(y + 1, 1, 1)).toEpochDay() - fromJalali(JDate(y, 12, 1)).toEpochDay()).toInt()
}

val J_MONTHS_FA = listOf("فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند")
/** Saturday first, as the owner's week runs. */
val J_WEEK_FA = listOf("ش", "ی", "د", "س", "چ", "پ", "ج")
val J_WEEKDAY_FA = listOf("شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنج‌شنبه", "جمعه")

/** Saturday = 0 … Friday = 6. */
fun satIndex(g: LocalDate): Int = (g.dayOfWeek.value + 1) % 7

fun jMonthFa(j: JDate): String = "${J_MONTHS_FA[j.m - 1]} ${faNum(j.y)}"
/** «سه‌شنبه ۲۶ آبان». */
fun jDayFa(g: LocalDate): String = toJalali(g).let { "${J_WEEKDAY_FA[satIndex(g)]} ${faNum(it.d)} ${J_MONTHS_FA[it.m - 1]}" }

/** A cell of the month: null before the 1st; else the day with its counts (past and today: published; future: planned). */
data class MonthCell(val date: LocalDate, val j: JDate, val day: PubCalendarDay?, val today: Boolean, val future: Boolean)

/** The month of [anyDay] (Jalali) in rows of seven, Saturday first; [days] the hub's counts by Gregorian day. */
fun monthGrid(anyDay: JDate, days: List<PubCalendarDay>, today: LocalDate): List<List<MonthCell?>> {
    val first = fromJalali(JDate(anyDay.y, anyDay.m, 1))
    val len = jMonthLength(anyDay.y, anyDay.m)
    val byDay = days.associateBy { it.day }
    val cells = ArrayList<MonthCell?>()
    repeat(satIndex(first)) { cells += null }
    for (i in 0 until len) {
        val g = first.plusDays(i.toLong())
        cells += MonthCell(g, JDate(anyDay.y, anyDay.m, i + 1), byDay[g.toString()], g == today, g.isAfter(today))
    }
    while (cells.size % 7 != 0) cells += null
    return cells.chunked(7)
}

/** The month's first and last Gregorian day (the calendar's `from` and `to`). */
fun monthSpan(j: JDate): Pair<LocalDate, LocalDate> {
    val first = fromJalali(JDate(j.y, j.m, 1))
    return first to first.plusDays(jMonthLength(j.y, j.m) - 1L)
}

fun nextMonth(j: JDate, by: Int): JDate {
    val k = j.y * 12 + (j.m - 1) + by
    return JDate(Math.floorDiv(k, 12), Math.floorMod(k, 12) + 1, 1)
}

/** A day's count in its cell: past and today what went out (today «۶ از ۳۰»), the future what is planned. */
fun cellCountFa(c: MonthCell): String? {
    val d = c.day ?: return null
    val out = d.published
    val all = d.published + d.scheduled + d.held + d.failed + d.planned
    return when {
        c.future -> if (all > 0) faNum(all) else null
        c.today -> if (all > 0) "${faNum(out)} از ${faNum(all)}" else null
        else -> if (out + d.failed > 0) faNum(out + d.failed) else null
    }
}

// ---------------------------------------------------------------------------------------------------- an account's page --
/** A page's grid in days, newest first: each day its Tehran date and its cards (a set as one). */
fun cardsByDay(items: List<PublicationCard>): List<Pair<LocalDate, List<PublicationCard>>> =
    items.groupBy { tehranDate(it.at) ?: LocalDate.MIN }.toSortedMap(compareByDescending { it }).map { it.key to it.value.sortedBy { c -> instant(c.at) } }

/** «امروز · سه‌شنبه ۲۶ آبان», «دیروز · …», else the day. */
fun dayHeadFa(d: LocalDate, today: LocalDate): String = when (d) {
    today -> "امروز · ${jDayFa(d)}"
    today.minusDays(1) -> "دیروز · ${jDayFa(d)}"
    today.plusDays(1) -> "فردا · ${jDayFa(d)}"
    else -> jDayFa(d)
}

/** The kinds a page's tabs offer: «همه» and each kind it has, with its count. */
fun kindTabs(byKind: Map<String, Int>): List<Pair<String?, Int>> =
    listOf<Pair<String?, Int>>(null to byKind.values.sum()) + byKind.entries.filter { it.value > 0 }.sortedByDescending { it.value }.map { it.key to it.value }

// ----------------------------------------------------------------------------------------------------------- an item --
/** Every text of a row as one block «کپی همه»: caption, comment words, the DM with its buttons, the public replies, the story word. */
fun allTexts(p: Publication): String = buildString {
    p.caption?.trim()?.ifEmpty { null }?.let { append(it).append("\n\n") }
    p.comment?.let { cm ->
        if (cm.keywords.isNotEmpty()) append("کلمه‌ی کامنت: ").append(cm.keywords.joinToString("، ")).append("\n")
        cm.reply?.trim()?.ifEmpty { null }?.let { append("دایرکت: ").append(it).append("\n") }
        cm.buttons.forEach { append("• ").append(it.title).append(": ").append(it.url).append("\n") }
        cm.link?.trim()?.ifEmpty { null }?.let { if (cm.buttons.none { b -> b.url == it }) append("لینک: ").append(it).append("\n") }
        if (cm.publicReplies.isNotEmpty()) {
            append("جواب‌های عمومی:\n")
            cm.publicReplies.forEachIndexed { i, r -> append("${i + 1}. ").append(r).append("\n") }
        }
    }
    p.storyWord?.trim()?.ifEmpty { null }?.let { append("کلمه‌ی ریپلای: ").append(it).append("\n") }
}.trim()

/** The files the owner downloads, in the order he reads them: video, cover, slides, pictures (a thumb is the app's own). */
fun downloadable(p: Publication) = p.files.filter { it.role != "thumb" }.sortedWith(compareBy({ ROLE_ORDER.indexOf(it.role).let { i -> if (i < 0) 9 else i } }, { it.n ?: 0 }))
private val ROLE_ORDER = listOf("video", "cover", "slide", "image")
fun fileRoleFa(role: String): String = when (role) { "video" -> "ویدیو"; "cover" -> "کاور"; "slide" -> "اسلاید"; "image" -> "عکس"; else -> role }

/** «۲۴٫۱ مگ», «۳۸۰ کیلو». */
fun sizeFa(bytes: Long?): String? {
    val b = bytes ?: return null
    return when {
        b >= 1_000_000 -> faText("%.1f".format(java.util.Locale.US, b / 1_000_000.0).replace('.', '٫')) + " مگ"
        b >= 1_000 -> faNum((b / 1_000).toInt()) + " کیلو"
        else -> faNum(b.toInt()) + " بایت"
    }
}

// ----------------------------------------------------------------------------------------------------------- search --
/** The hub's Persian folding, enough to mark a hit in a snippet: Arabic ی/ک, no ZWNJ or spaces, Latin digits. */
fun foldSearch(s: String): String = buildString {
    for (ch in s) when (ch) {
        'ي', 'ى' -> append('ی')
        'ك' -> append('ک')
        '‌', ' ', ' ' -> {}
        in '۰'..'۹' -> append('0' + (ch - '۰'))
        in '٠'..'٩' -> append('0' + (ch - '٠'))
        else -> append(ch.lowercaseChar())
    }
}

/** Where [query] stands in [text] once both are folded, as a range of [text]'s own characters (null: no hit). */
fun hitRange(text: String, query: String): IntRange? {
    val q = foldSearch(query)
    if (q.isEmpty()) return null
    // fold the text keeping each folded character's source index
    val idx = ArrayList<Int>(text.length)
    val sb = StringBuilder()
    text.forEachIndexed { i, ch -> val f = foldSearch(ch.toString()); for (c in f) { sb.append(c); idx += i } }
    val at = sb.indexOf(q)
    if (at < 0) return null
    return idx[at]..idx[at + q.length - 1]
}

fun matchFa(match: String?): String? = when (match) {
    "title" -> "عنوان"; "topic" -> "موضوع"; "caption" -> "کپشن"; "word" -> "کلمه"; else -> null
}
