#!/usr/bin/env python3
"""Divan icon set — the single source for every icon in the web panel and the Android app.

Grammar (design/icons/README.md):
  * 24 x 24 grid, live area 2..22, stroke 1.6, round caps and joins, no fills by default.
  * Corners are cut at 45 degrees (the Divan chamfer), never rounded.
  * A human (the owner) has a round head; an agent has an octagonal head.
  * Each icon may carry a "heart": a closed shape that is filled only in the active state.
  * Icons marked mirror=True flip horizontally in RTL.

Run:  python3 design/icons/icons.py     -> writes design/icons/svg/*.svg and icons.json
"""
from __future__ import annotations

import json
from pathlib import Path


def f(v: float) -> str:
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return s if s not in ("-0", "") else "0"


def circle(cx: float, cy: float, r: float) -> str:
    return f"M{f(cx - r)} {f(cy)}a{f(r)} {f(r)} 0 1 0 {f(2 * r)} 0a{f(r)} {f(r)} 0 1 0 {f(-2 * r)} 0Z"


def chamfer(x: float, y: float, w: float, h: float, c: float) -> str:
    """A rectangle whose four corners are cut at 45 degrees by c."""
    return (
        f"M{f(x + c)} {f(y)}H{f(x + w - c)}L{f(x + w)} {f(y + c)}V{f(y + h - c)}"
        f"L{f(x + w - c)} {f(y + h)}H{f(x + c)}L{f(x)} {f(y + h - c)}V{f(y + c)}Z"
    )


def octagon(cx: float, cy: float, size: float) -> str:
    """The Divan octagon (cut = 30% of the side, as the sigils)."""
    return chamfer(cx - size / 2, cy - size / 2, size, size, size * 0.3)


def dot(x: float, y: float) -> str:
    """A dot (the Divan "nokte"): a tiny ring that the 1.6 stroke closes into a 2.5 disc."""
    return circle(x, y, 0.45)


STAR8 = (
    "M12 3.5L14.5 6H18V9.5L20.5 12L18 14.5V18H14.5L12 20.5L9.5 18H6V14.5"
    "L3.5 12L6 9.5V6H9.5Z"
)
AGENT_TORSO = "M5 20.5V17.5L8 14.5H16L19 17.5V20.5"


def agent_at(dx: float) -> tuple[str, str]:
    head = octagon(12 + dx, 6.5, 7)
    torso = f"M{f(5 + dx)} 20.5V17.5L{f(8 + dx)} 14.5H{f(16 + dx)}L{f(19 + dx)} 17.5V20.5"
    return head + torso, head


hire_s, hire_h = agent_at(-2.5)
dismiss_s, dismiss_h = agent_at(-2.5)

# id, fa, group, stroke path, heart path, mirror
ICONS: list[dict] = []


def icon(id_: str, fa: str, group: str, s: str, h: str = "", mirror: bool = False) -> None:
    ICONS.append({"id": id_, "fa": fa, "group": group, "s": s, "h": h, "mirror": mirror})


G_NAV, G_ORG, G_WORK, G_SYS, G_ACT, G_STATE = "nav", "org", "work", "system", "action", "state"

# --- navigation (bottom bar and sidebar) ---
icon("command", "فرمان", G_NAV,
     octagon(12, 12, 18) + "M12 7.5L13.4 10.6L16.5 12L13.4 13.4L12 16.5L10.6 13.4L7.5 12L10.6 10.6Z",
     "M12 7.5L13.4 10.6L16.5 12L13.4 13.4L12 16.5L10.6 13.4L7.5 12L10.6 10.6Z")
icon("cartable", "کارتابل", G_NAV,
     chamfer(3, 5, 18, 14, 2.5) + "M3 13H8L9.5 15.5H14.5L16 13H21",
     "M3 13H8L9.5 15.5H14.5L16 13H21V16.5L18.5 19H5.5L3 16.5Z")
icon("advisor", "مشاور", G_NAV, circle(12, 12, 8.5) + circle(9.6, 9.6, 2.6), circle(9.6, 9.6, 2.6))
icon("companies", "شرکت‌ها", G_NAV,
     "M4 20.5V8.5L8.5 4H15.5L20 8.5V20.5M2.5 20.5H21.5M8.5 10.5H10.5M13.5 10.5H15.5M8.5 14H10.5M13.5 14H15.5"
     "M10.5 20.5V17.5H13.5V20.5",
     "M10.5 20.5V17.5H13.5V20.5Z")
icon("messages", "پیام‌ها", G_NAV,
     "M5.5 4H18.5L21 6.5V14.5L18.5 17H11L6.5 20.5V17H5.5L3 14.5V6.5ZM7.5 9H16.5M7.5 12.5H13",
     "M11 17L6.5 20.5V17Z")

# --- people and organisation ---
icon("owner", "مالک", G_ORG, circle(12, 7, 3.6) + "M4.5 20.5a7.5 6 0 0 1 15 0", circle(12, 7, 3.6))
icon("agent", "ایجنت", G_ORG, octagon(12, 6.5, 7) + AGENT_TORSO, octagon(12, 6.5, 7))
icon("hire", "استخدام", G_ORG, hire_s + "M19.5 9.5V14.5M17 12H22", hire_h)
icon("dismiss", "برکناری", G_ORG, dismiss_s + "M17 12H22", dismiss_h)
icon("department", "دپارتمان", G_ORG,
     chamfer(9, 3, 6, 5, 1.2) + "M12 8V11.5M6 11.5H18M6 11.5V14M18 11.5V14"
     + chamfer(3, 14, 6, 5, 1.2) + chamfer(15, 14, 6, 5, 1.2),
     chamfer(9, 3, 6, 5, 1.2))
icon("meeting", "جلسه", G_ORG,
     octagon(6, 8, 4.4) + octagon(12, 5, 4.4) + octagon(18, 8, 4.4) + "M3 13.5H21M6 13.5V20M18 13.5V20",
     octagon(12, 5, 4.4))
icon("holding", "هلدینگ", G_ORG,
     circle(12, 12, 3.2) + "M12 2.5V6M12 18V21.5M2.5 12H6M18 12H21.5"
     "M5.3 5.3L7.7 7.7M16.3 16.3L18.7 18.7M18.7 5.3L16.3 7.7M7.7 16.3L5.3 18.7",
     circle(12, 12, 3.2))

# --- work ---
icon("decision", "تصمیم", G_WORK,
     "M12 20.5V13M12 13L6.5 7.5M12 13L17.5 7.5M6 11.5V7H10.5M18 11.5V7H13.5",
     "M12 11.2L13.8 13L12 14.8L10.2 13Z")
icon("seal", "مُهر", G_WORK, circle(12, 12, 8.5) + circle(12, 12, 5.2), circle(12, 12, 5.2))
icon("reject", "رد", G_WORK, chamfer(4, 4, 16, 16, 3) + "M9 9L15 15M15 9L9 15")
icon("delegate", "ارجاع", G_WORK,
     circle(5.5, 12, 2.5) + "M8 12H15M12.5 9L15.5 12L12.5 15" + chamfer(17, 8.5, 4.5, 7, 1.3),
     chamfer(17, 8.5, 4.5, 7, 1.3), mirror=True)
icon("task", "کار", G_WORK,
     chamfer(3.5, 4.5, 6, 6, 1.5) + "M5 7.6L6.3 8.9L8.3 6.7M12.5 7.5H20.5"
     + chamfer(3.5, 13.5, 6, 6, 1.5) + "M12.5 16.5H20.5",
     chamfer(3.5, 13.5, 6, 6, 1.5))
icon("report", "گزارش", G_WORK,
     "M5 3H14.5L19 7.5V21H5ZM14.5 3V7.5H19M8.5 17.5V14.5M12 17.5V11.5M15.5 17.5V13.5",
     "M14.5 3V7.5H19Z")
icon("deliverable", "خروجی", G_WORK,
     "M4 8L8 4H16L20 8V19L18 21H6L4 19ZM4 8H20" + circle(12, 14, 2.4), circle(12, 14, 2.4))
icon("planner", "پلنر", G_WORK,
     chamfer(3.5, 5, 17, 15.5, 2.5) + "M8.5 3V7M15.5 3V7M3.5 10H20.5" + chamfer(14, 13.5, 3, 3, 0.8),
     chamfer(14, 13.5, 3, 3, 0.8))
icon("rate", "امتیاز", G_WORK, STAR8, STAR8)
icon("khalvat", "خلوت", G_WORK,
     "M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z", "M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z")

# --- treasury and system ---
icon("treasury", "خزانه", G_SYS,
     "M5 7a7 2.8 0 1 0 14 0a7 2.8 0 1 0-14 0ZM5 7V12a7 2.8 0 0 0 14 0V7M5 12V17a7 2.8 0 0 0 14 0V12",
     "M5 7a7 2.8 0 1 0 14 0a7 2.8 0 1 0-14 0Z")
icon("budget", "بودجه", G_SYS, "M4 16a8 8 0 0 1 16 0M12 16L15.5 11.5M3 19.5H21" + circle(12, 16, 1.6),
     circle(12, 16, 1.6))
icon("model", "مدل", G_SYS,
     chamfer(6, 6, 12, 12, 2.5) + "M9.5 3V6M14.5 3V6M9.5 18V21M14.5 18V21M3 9.5H6M3 14.5H6M18 9.5H21M18 14.5H21"
     "M12 9.5L14.5 12L12 14.5L9.5 12Z",
     "M12 9.5L14.5 12L12 14.5L9.5 12Z")
icon("server", "سرور", G_SYS,
     chamfer(3.5, 4, 17, 7, 1.5) + chamfer(3.5, 13, 17, 7, 1.5) + "M11.5 7.5H16.5M11.5 16.5H16.5"
     + circle(7.5, 7.5, 1) + circle(7.5, 16.5, 1),
     circle(7.5, 7.5, 1) + circle(7.5, 16.5, 1))
icon("chart", "نمودار", G_SYS, "M4 4V20H20M7.5 15.5L11.5 11L14.5 13.5L18.5 8.5" + circle(18.5, 8.5, 1.4),
     circle(18.5, 8.5, 1.4))
icon("settings", "تنظیمات", G_SYS,
     octagon(12, 12, 13) + "M12 2.5V5.5M12 18.5V21.5M2.5 12H5.5M18.5 12H21.5" + circle(12, 12, 2.8),
     circle(12, 12, 2.8))
icon("lock", "قفل", G_SYS, chamfer(5, 10.5, 14, 10.5, 2) + "M8 10.5V7.5a4 4 0 0 1 8 0V10.5M12 14.5V17")
icon("time", "زمان", G_SYS, circle(12, 12, 8.5) + "M12 7.5V12L15 14")
icon("memory", "حافظه", G_SYS,
     "M4.5 12a7.5 7.5 0 1 0 2.2-5.3L4.5 8.5M4.5 4V8.5H9M12 8V12L15 14")
icon("knowledge", "دانش", G_SYS,
     "M12 6.5C10 5 7 4.5 3.5 5V18.5C7 18 10 18.5 12 20C14 18.5 17 18 20.5 18.5V5C17 4.5 14 5 12 6.5ZM12 6.5V20")

# --- actions ---
icon("add", "افزودن", G_ACT, "M12 5V19M5 12H19")
icon("edit", "ویرایش (قلم)", G_ACT,
     "M17 3.5L20.5 7L9 18.5L4 20L5.5 15ZM14.5 6L18 9.5M4 20L7.2 16.8",
     "M5.5 15L9 18.5L4 20Z")
icon("search", "جستجو", G_ACT, circle(10.5, 10.5, 6.5) + "M15.5 15.5L20.5 20.5")
icon("filter", "فیلتر", G_ACT, "M4 6.5H20M7 12H17M10 17.5H14")
icon("send", "ارسال", G_ACT, "M20.5 3.5L3.5 10.5L10.5 13.5L13.5 20.5ZM10.5 13.5L20.5 3.5",
     "M10.5 13.5L13.5 20.5L20.5 3.5Z", mirror=True)
icon("attach", "پیوست", G_ACT, "M16 8V16.5a4 4 0 0 1-8 0V6.5a2.75 2.75 0 0 1 5.5 0V15.5a1.5 1.5 0 0 1-3 0V8")
icon("mic", "میکروفون", G_ACT,
     "M9 6.5a3 3 0 0 1 6 0V11.5a3 3 0 0 1-6 0ZM5.5 11.5a6.5 6.5 0 0 0 13 0M12 18V21M9 21H15",
     "M9 6.5a3 3 0 0 1 6 0V11.5a3 3 0 0 1-6 0Z")
icon("image", "عکس", G_ACT,
     chamfer(3, 5, 18, 14, 2.5) + "M3.5 16.5L8.5 11.5L13 16L15.5 13.5L20.5 18" + circle(15.5, 9, 1.6),
     circle(15.5, 9, 1.6))
icon("video", "فیلم", G_ACT, chamfer(3, 6, 13, 12, 2) + "M16 10.5L21 7.5V16.5L16 13.5",
     "M16 10.5L21 7.5V16.5L16 13.5Z")
icon("stop", "پایان", G_ACT, chamfer(6, 6, 12, 12, 2), chamfer(6, 6, 12, 12, 2))
icon("code", "کارگاه کد", G_ACT, "M8 7L3 12L8 17M16 7L21 12L16 17M13.5 5L10.5 19")
icon("share", "اشتراک", G_ACT,
     circle(18, 5.5, 2.5) + circle(6, 12, 2.5) + circle(18, 18.5, 2.5) + "M8.2 10.8L15.8 6.7M8.2 13.2L15.8 17.3",
     circle(6, 12, 2.5))
icon("download", "دریافت", G_ACT, "M12 4V15M7.5 10.5L12 15L16.5 10.5M4.5 15.5V18L6.5 20H17.5L19.5 18V15.5")
icon("refresh", "تازه‌سازی", G_ACT, "M19.5 12a7.5 7.5 0 1 1-2.2-5.3L19.5 8.5M19.5 4V8.5H15")
icon("pause", "توقف", G_ACT, chamfer(6.5, 5, 3.5, 14, 1) + chamfer(14, 5, 3.5, 14, 1),
     chamfer(6.5, 5, 3.5, 14, 1) + chamfer(14, 5, 3.5, 14, 1))
icon("resume", "ادامه", G_ACT, "M8 5.5V18.5L18 12Z", "M8 5.5V18.5L18 12Z")
icon("close", "بستن", G_ACT, "M6 6L18 18M18 6L6 18")
icon("back", "بازگشت", G_ACT, "M19.5 12H5M10.5 6.5L5 12L10.5 17.5", mirror=True)
icon("chevron", "باز کردن", G_ACT, "M6 9L12 15L18 9")
icon("next", "بعدی", G_ACT, "M9.5 6L15.5 12L9.5 18", mirror=True)
icon("scope", "تغییر دامنه", G_ACT, "M8 9.5L12 5.5L16 9.5M8 14.5L12 18.5L16 14.5")
icon("more", "بیشتر", G_ACT, dot(12, 5.5) + dot(12, 12) + dot(12, 18.5))

# --- status and the five notification levels ---
icon("urgent", "فوری", G_STATE, octagon(12, 12, 17) + "M12 7.5V12.5" + dot(12, 16.2))
icon("level-decision", "تصمیم (سطح)", G_STATE,
     "M12 20.5V13M12 13L6.5 7.5M12 13L17.5 7.5M6 11.5V7H10.5M18 11.5V7H13.5")
icon("level-report", "گزارش (سطح)", G_STATE,
     "M5 3H14.5L19 7.5V21H5ZM14.5 3V7.5H19M8.5 12.5H15.5M8.5 16.5H13")
icon("info", "اطلاع", G_STATE, circle(12, 12, 8.5) + "M12 11V16.5" + dot(12, 7.8))
icon("learning", "یادگیری", G_STATE,
     "M12 21V12.5M12 14C12 10 9 7.5 5 7.5C5 11.5 8 14 12 14ZM12 11.5C12 8 14.5 5.5 18.5 5.5"
     "C18.5 9 16 11.5 12 11.5ZM7.5 21H16.5",
     "M12 11.5C12 8 14.5 5.5 18.5 5.5C18.5 9 16 11.5 12 11.5Z")
icon("bell", "اعلان", G_STATE, "M6 16.5V11a6 6 0 0 1 12 0V16.5L19.5 18.5H4.5ZM10 20.5a2 2 0 0 0 4 0",
     "M10 20.5a2 2 0 0 0 4 0Z")
icon("offline", "آفلاین", G_STATE,
     "M5 9.5a10 10 0 0 1 14 0M7.8 12.6a6 6 0 0 1 8.4 0M4 4L20 20" + dot(12, 16.5))
icon("sleeping", "خواب", G_STATE, "M5 5.5H10L5 11.5H10M13 12.5H19L13 19.5H19")

GROUPS = [
    (G_NAV, "ناوبری", "نوار پایین اندروید و ستون کناری وب"),
    (G_ORG, "آدم‌ها و سازمان", "سر گرد = انسان (مالک)؛ سر هشت‌ضلعی = ایجنت"),
    (G_WORK, "کار", "تصمیم، مُهر، ارجاع، خروجی و آیین‌ها"),
    (G_SYS, "خزانه و سیستم", "توکن، بودجه، مدل، سرور"),
    (G_ACT, "اقدام‌ها", "کنترل‌های عمومی"),
    (G_STATE, "وضعیت و سطح اعلان", "پنج سطح اعلان و وضعیت ایجنت"),
]


def svg(i: dict) -> str:
    heart = f'\n  <path class="heart" d="{i["h"]}" fill="none" stroke="none"/>' if i["h"] else ""
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="none"'
        ' stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">\n'
        f'  <path class="stroke" d="{i["s"]}"/>{heart}\n</svg>\n'
    )


def main() -> None:
    here = Path(__file__).resolve().parent
    out = here / "svg"
    out.mkdir(exist_ok=True)
    ids = [i["id"] for i in ICONS]
    assert len(ids) == len(set(ids)), "duplicate icon id"
    for old in out.glob("*.svg"):
        if old.stem not in ids:
            old.unlink()
    for i in ICONS:
        (out / f"{i['id']}.svg").write_text(svg(i), encoding="utf-8")
    manifest = {
        "grid": 24, "stroke": 1.6, "cap": "round", "join": "round",
        "groups": [{"id": g, "fa": fa, "note": note} for g, fa, note in GROUPS],
        "icons": ICONS,
    }
    (here / "icons.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"icons: {len(ICONS)} written to {out}")


if __name__ == "__main__":
    main()
