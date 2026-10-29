package com.coinepro.hq.core.format

import com.coinepro.hq.designsystem.generated.DivanIcon

/**
 * A work priority as the owner reads it (docs/OPERATING_MODEL.md, the model queue's priorities; contract §4 and §16.5): a Persian name
 * first, the code (`P0`…`P4`, Latin) small beside it, and one line on what it means for the queue. The tone follows the status
 * colours' meaning: red only for the emergency, amber for what users see, lapis for the owner's level, quiet for the rest.
 */
data class Priority(val code: String, val fa: String, val line: String, val tone: Tone, val icon: DivanIcon)

val PRIORITIES: List<Priority> = listOf(
    Priority("P0", "اضطراری", "حادثه و اتاق جنگ؛ حتی وقتی کلید توقف روشن است اجرا میشود. فقط برای اتفاق واقعی.", Tone.NEG, DivanIcon.URGENT),
    Priority("P1", "فوری", "چیزی که کاربران محصول مستقیم میبینند؛ جلوتر از کارهای دیگر در صف.", Tone.WARN, DivanIcon.OWNER),
    Priority("P2", "مهم", "هم‌سطح گفت‌وگوی تو با مشاور؛ همیشه یک جای خالی در صف برایش رزرو است.", Tone.LAPIS, DivanIcon.STAR),
    Priority("P3", "عادی", "کار عملیاتی و زمان‌بندی‌شده؛ پیش‌فرض بیشتر فرمان‌ها.", Tone.NEUTRAL, DivanIcon.TASK),
    Priority("P4", "هر وقت شد", "پس‌زمینه (محتوا، گزارش غیرفوری)؛ وقتی سهمیه به هشدار برسد اول همین‌ها مکث میکنند.", Tone.SILVER, DivanIcon.SLEEPING),
)

/** The default of a new order (contract §4: `priority` defaults to P3). */
const val DEFAULT_PRIORITY = "P3"

/** A code from the API, as the owner reads it; an unknown code keeps its own text with the default's meaning withheld. */
fun priority(code: String?): Priority =
    PRIORITIES.firstOrNull { it.code.equals(code?.trim(), ignoreCase = true) }
        ?: Priority(code?.trim().orEmpty().ifEmpty { "—" }, code?.trim().orEmpty().ifEmpty { "—" }, "اولویتی که اپ نمیشناسد.", Tone.NEUTRAL, DivanIcon.TASK)

/** "اضطراری (P0)", for sentences. */
fun priorityPhrase(code: String?): String = priority(code).let { if (it.fa == it.code) it.code else "${it.fa} (${it.code})" }

/** P0 and P1 come first; the rest are not urgent (the bars and dots that used `priority <= "P1"`). */
fun isUrgentPriority(code: String?): Boolean = code == "P0" || code == "P1"
