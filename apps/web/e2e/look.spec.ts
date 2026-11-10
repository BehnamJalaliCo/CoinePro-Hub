import { expect, test, type Page } from '@playwright/test';
import { clean } from './support';

// ⟨1.0.1⟩ Part C, the look, over the demo holding: the command button of every screen and its one spring sheet (the words, the
// templates that only fill the starting text, the companies as their own marks, the pace, «باز کن»; the «کارمند ۲۴ ساعته» form), the
// home (what waits for the owner answered in place, the pulse in one row, three states of a session, one full gold), the
// notifications' three levels with their action in place, and the limits block of the treasury (the Claude accounts as rings in
// every state, today's meter, and nothing of it on a hub before §55). The demo asks for the limits' other states through
// `hq.e2e.limits`, an older hub through `hq.e2e.old55` / `hq.e2e.old47`, and a refused order through `hq.e2e.order-fail`.

const flag = (page: Page, key: string, value: string) => page.addInitScript(([k, v]) => window.localStorage.setItem(k!, v!), [key, value]);
const sheetOf = (page: Page) => page.getByTestId('command-sheet');
async function openCommand(page: Page) {
  await page.locator('[data-command-button]').click();
  const sheet = sheetOf(page);
  await expect(sheet).toBeVisible();
  return sheet;
}
const overflow = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);

// ============================================================================================== C2.1 the command ==
test('the command button is on every top-level screen, never inside a session, and leaves while its sheet is open', async ({ page }) => {
  await clean(page, async () => {
    for (const path of ['/', '/s', '/outputs', '/treasury', '/notifications']) {
      await page.goto(path);
      await expect(page.locator('[data-command-button]'), path).toBeVisible();
    }
    // The mark in a thin ring, not a filled gold.
    await expect(page.locator('[data-command-button] .bg-gold')).toHaveCount(0);
    const sheet = await openCommand(page);
    await expect(sheet.getByRole('heading', { name: 'چه میخواهی؟' })).toBeVisible();
    await expect(sheet.getByLabel('فرمان', { exact: true })).toBeFocused();
    await expect(sheet.getByLabel('فرمان', { exact: true })).toHaveAttribute('placeholder', 'بنویس چه میخواهی؛ درباره‌ی هر چیزی');
    await expect(page.locator('[data-command-button]')).toBeHidden();
    await page.keyboard.press('Escape');
    await expect(sheet).toHaveCount(0);
    await expect(page.locator('[data-command-button]')).toBeVisible();
    // Inside a session its composer is the command.
    await page.goto('/s/F-0008');
    await expect(page.getByLabel('گفتگو', { exact: true })).toBeVisible();
    await expect(page.locator('[data-command-button]')).toHaveCount(0);
  });
});

test('the sheet: a template only fills the starting text, the companies are their own marks, the pace is asked, the bar says what opens', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/outputs');
    const sheet = await openCommand(page);
    const field = sheet.getByLabel('فرمان', { exact: true });
    const open = sheet.getByRole('button', { name: 'باز کن' });
    await expect(open).toBeDisabled();
    // The templates, and the routine's entry beside them.
    const templates = sheet.getByRole('group', { name: 'الگوهای آماده' });
    await expect(templates.getByRole('button')).toHaveText(['ریلز اینستاگرام', 'موشن‌گرافی', 'کارمند ۲۴ ساعته']);
    await templates.getByRole('button', { name: 'ریلز اینستاگرام' }).click();
    await expect(field).toHaveValue('یک ریلز اینستاگرام بساز: ');
    // The companies the hub returns, each its own mark with its name under it; none picked = the holding decides.
    const marks = sheet.getByRole('group', { name: 'برای کدام شرکت؟' });
    await expect(marks.locator('[data-company]')).toHaveCount(3);
    for (const name of ['تریدیار', 'پرو-چارت']) await expect(marks.getByRole('button', { name })).toBeVisible();
    await expect(marks.locator('[data-company][aria-pressed="true"]')).toHaveCount(0);
    await marks.locator('[data-company="PC"]').click();
    await expect(marks.locator('[data-company="PC"]')).toHaveAttribute('aria-pressed', 'true');
    await expect(field).toHaveValue('برای پرو-چارت یک ریلز اینستاگرام بساز: ');
    // Several: the text names them all.
    await marks.locator('[data-company="TY"]').click();
    await expect(field).toHaveValue('برای پرو-چارت و تریدیار یک ریلز اینستاگرام بساز: ');
    await marks.locator('[data-company="TY"]').click();
    await templates.getByRole('button', { name: 'موشن‌گرافی' }).click();
    await expect(field).toHaveValue('برای پرو-چارت یک موشن‌گرافی بساز: ');
    // Once he writes past the template, picking a company no longer rewrites his words.
    await field.fill('برای پرو-چارت یک موشن‌گرافی بساز: معرفی هشدار قیمت');
    await marks.locator('[data-company="FX"]').click();
    await expect(field).toHaveValue('برای پرو-چارت یک موشن‌گرافی بساز: معرفی هشدار قیمت');
    await marks.locator('[data-company="FX"]').click();
    // The pace: nothing is chosen for him; the bar says so, then says what opens.
    const bar = sheet.getByTestId('decision-bar');
    await expect(open).toBeDisabled();
    await expect(bar).toContainText('اول «با من» یا «خودکار» را انتخاب کن');
    const pace = sheet.getByRole('radiogroup', { name: 'این جلسه چطور جلو برود؟' });
    await expect(pace.getByRole('radio')).toHaveText(['با من', 'خودکار']);
    await pace.getByRole('radio', { name: 'با من' }).click();
    await expect(open).toBeEnabled();
    await expect(bar.locator('[data-decision-context]')).toContainText('پرو-چارت');
    await expect(bar.locator('[data-decision-context]')).toContainText('با من');
    // One full gold in the sheet: «باز کن».
    await expect(sheet.locator('button.bg-gold')).toHaveCount(1);
  });
});

test('«باز کن» opens the session of the company picked by its mark, and the owner is in it', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/treasury');
    const sheet = await openCommand(page);
    // The words name no company: the mark alone says whose it is.
    await sheet.getByLabel('فرمان', { exact: true }).fill('یک پست درباره‌ی هشدار قیمت بنویس');
    await sheet.locator('[data-company="PC"]').click();
    await sheet.getByRole('radiogroup', { name: 'این جلسه چطور جلو برود؟' }).getByRole('radio', { name: 'خودکار' }).click();
    await sheet.getByRole('button', { name: 'باز کن' }).click();
    await expect(page).toHaveURL(/\/s\/F-\d+$/);
    await expect(sheet).toHaveCount(0);
    await expect(page.getByRole('heading', { level: 1 })).toContainText('هشدار قیمت');
    await expect(page.getByLabel('گفتگو', { exact: true }).getByText('فرمانت را گرفتم')).toBeVisible();
    await expect(page.locator('main')).toContainText('پرو-چارت');
  });
});

test('a refused order keeps the words and says why above the bar', async ({ page }) => {
  await flag(page, 'hq.e2e.order-fail', '1');
  await clean(page, async () => {
    await page.goto('/s');
    const sheet = await openCommand(page);
    const field = sheet.getByLabel('فرمان', { exact: true });
    await field.fill('برای تریدیار یک گزارش کوتاه از این هفته بنویس');
    await sheet.getByRole('radiogroup', { name: 'این جلسه چطور جلو برود؟' }).getByRole('radio', { name: 'با من' }).click();
    await sheet.getByRole('button', { name: 'باز کن' }).click();
    await expect(sheet.getByTestId('decision-bar').getByRole('alert')).toContainText('ستاد الان جواب نمیدهد');
    await expect(field).toHaveValue('برای تریدیار یک گزارش کوتاه از این هفته بنویس');
    await expect(page).toHaveURL(/\/s$/);
    await expect(sheet.getByRole('button', { name: 'باز کن' })).toBeEnabled();
  }, [/POST \/orders/]);
});

test('«کارمند ۲۴ ساعته»: one sentence and one company make a routine at once; a sentence that is no routine says why', async ({ page }) => {
  // The sentence without a time is refused on purpose (422), and «خطاخوان» keeps that.
  await clean(page, async () => {
    await page.goto('/');
    const sheet = await openCommand(page);
    await sheet.getByRole('button', { name: 'کارمند ۲۴ ساعته' }).click();
    await expect(sheet.getByRole('heading', { name: 'کارمند ۲۴ ساعته' })).toBeVisible();
    const field = sheet.getByLabel('جمله‌ی کارمند ۲۴ ساعته');
    await expect(field).toHaveAttribute('placeholder', 'مثلاً: هر روز ساعت ۹ رتبه‌های سئوی سایت را ببین و خلاصه بده');
    const make = sheet.getByRole('button', { name: 'بساز' });
    await expect(make).toBeDisabled();
    // «برگرد» is the order form again, and back.
    await sheet.getByRole('button', { name: 'برگرد' }).click();
    await expect(sheet.getByRole('heading', { name: 'چه میخواهی؟' })).toBeVisible();
    await sheet.getByRole('button', { name: 'کارمند ۲۴ ساعته' }).click();
    // One company only.
    const marks = sheet.getByRole('group', { name: 'برای کدام شرکت؟' });
    await marks.locator('[data-company="PC"]').click();
    await marks.locator('[data-company="TY"]').click();
    await expect(marks.locator('[data-company][aria-pressed="true"]')).toHaveCount(1);
    await expect(marks.locator('[data-company="TY"]')).toHaveAttribute('aria-pressed', 'true');
    // No time of repetition: the hub's own words above the bar, his sentence kept.
    await field.fill('رتبه‌های سئوی سایت را ببین و خلاصه بده');
    await make.click();
    await expect(sheet.getByTestId('decision-bar').getByRole('alert')).toContainText('این جمله نمیگوید هر چند وقت یک بار');
    await expect(field).toHaveValue('رتبه‌های سئوی سایت را ببین و خلاصه بده');
    await field.fill('هر روز ساعت ۹ رتبه‌های سئوی سایت را ببین و خلاصه بده');
    await make.click();
    // No card, no passkey: a quiet confirmation with when it runs and its next turn.
    const made = sheet.getByTestId('routine-made');
    await expect(made).toContainText('هر روز ساعت ۹ رتبه‌های سئوی سایت را ببین و خلاصه بده');
    await expect(made.locator('[data-when]')).toContainText('هر روز ساعت 09:00');
    await expect(made.locator('[data-next]')).toContainText('نوبت بعد:');
    await expect(page.getByRole('dialog')).toHaveCount(1);
    await sheet.getByRole('button', { name: 'باشه' }).click();
    await expect(sheet).toHaveCount(0);
  }, [/POST \/routines/]);
});

test('on a hub before the routine route the entry leaves and the order form stays', async ({ page }) => {
  await flag(page, 'hq.e2e.old47', '1');
  await clean(page, async () => {
    await page.goto('/');
    const sheet = await openCommand(page);
    await sheet.getByRole('button', { name: 'کارمند ۲۴ ساعته' }).click();
    await sheet.getByLabel('جمله‌ی کارمند ۲۴ ساعته').fill('هر روز ساعت ۹ رتبه‌های سئوی سایت را ببین');
    await sheet.getByRole('button', { name: 'بساز' }).click();
    await expect(sheet.getByRole('heading', { name: 'چه میخواهی؟' })).toBeVisible();
    await expect(sheet.getByRole('button', { name: 'کارمند ۲۴ ساعته' })).toHaveCount(0);
    await expect(sheet.getByRole('group', { name: 'الگوهای آماده' }).getByRole('button')).toHaveCount(2);
  });
});

// ================================================================================================== C3.1 the home ==
test('the home: what waits for him on top and answered in place, the pulse in one row, one full gold', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/');
    const turn = page.getByTestId('turn-row');
    const before = Number(await turn.getAttribute('data-count'));
    expect(before).toBeGreaterThan(1);
    // The same number in the row's large count and in the pulse.
    await expect(page.getByTestId('office-pulse').locator('[data-pulse="منتظر تو"] [data-figure]')).toHaveAttribute('data-figure', String(before));
    // The question in full with its ready answers and the quiet last one; one tap answers.
    const ask = turn.locator('[data-wait="session"]').first();
    await expect(ask).toContainText('مدیرعامل تریدیار میپرسد');
    await expect(ask).toContainText('منتظر');
    const answers = ask.getByRole('group', { name: 'جواب‌های آماده' });
    await expect(answers.getByRole('button')).toHaveText(['هفته‌ای که بازار عوض شد', 'سه نکته برای حد ضرر', 'کارمزد را دست‌کم نگیر', 'خودت تصمیم بگیر و ادامه بده']);
    // One filled gold on the whole page: the first decision's «تأیید»; the others are outlined.
    const decisions = turn.locator('[data-wait="decision"]');
    await expect(decisions.first().getByRole('button', { name: /^تأیید/ })).toHaveClass(/bg-gold/);
    await expect(page.locator('main button.bg-gold, main a.bg-gold')).toHaveCount(1);
    await answers.getByRole('button', { name: 'سه نکته برای حد ضرر' }).click();
    await expect(page.getByText('جوابت رفت: سه نکته برای حد ضرر')).toBeVisible();
    await expect(turn).toHaveAttribute('data-count', String(before - 1));
    // The command entry is one row.
    await expect(page.getByTestId('command-row')).toContainText('چه میخواهی؟');
    await expect(page.getByLabel('فرمان تازه', { exact: true })).toHaveCount(0);
  });
});

test('the home: a decision is approved where it is seen, with one tap; the rest of what waits opens in place', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/');
    const turn = page.getByTestId('turn-row');
    const before = Number(await turn.getAttribute('data-count'));
    const cards = turn.locator('[data-card]');
    await expect(cards).toHaveCount(3);
    await turn.getByRole('button', { name: /مورد دیگر$/ }).click();
    expect(await cards.count()).toBeGreaterThan(3);
    const first = turn.locator('[data-wait="decision"]').first();
    const title = (await first.locator('.font-semibold').first().innerText()).trim();
    await first.getByRole('button', { name: /^تأیید/ }).click();
    await expect(page.getByText('تأیید شد.')).toBeVisible();
    await expect(turn).toHaveAttribute('data-count', String(before - 1));
    await expect(turn.locator('[data-wait="decision"]').filter({ hasText: title })).toHaveCount(0);
    // No second card, no dialog on the way.
    await expect(page.getByRole('dialog')).toHaveCount(0);
  });
});

test('the home: open sessions are cards in three states only, each opening its session', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/');
    const rows = page.getByLabel('جلسه‌ها', { exact: true }).locator('a[data-state3]');
    await expect(rows.first()).toBeVisible();
    const states = await rows.evaluateAll((els) => [...new Set(els.map((e) => e.getAttribute('data-state3')))]);
    for (const s of states) expect(['waiting', 'working', 'done']).toContain(s);
    const words = await rows.locator('span[data-state3]').allInnerTexts();
    for (const w of words) expect(['منتظر تو', 'در کار', 'تمام']).toContain(w.trim());
    // No chain of stages and no percent bar on a session card.
    await expect(rows.first().getByRole('progressbar')).toHaveCount(0);
    const href = await rows.first().getAttribute('href');
    await rows.first().click();
    await expect(page).toHaveURL(new RegExp(`${href}$`));
    await expect(page.getByLabel('گفتگو', { exact: true })).toBeVisible();
  });
});

// ========================================================================================= C3.5 the notifications ==
test('notifications: three levels in one bar, what asks something of him on top, the rest by day', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/notifications');
    const bar = page.getByRole('radiogroup', { name: 'سطح اعلان' });
    await expect(bar.getByRole('radio')).toHaveText(['همه', 'فوری', 'تصمیم', 'خبر']);
    const asks = page.getByTestId('asks');
    await expect(asks.getByRole('heading', { name: 'از تو کاری میخواهد' })).toBeVisible();
    // Only urgent and decision rows, unread; each with its own action.
    await expect(asks.locator('[data-row]')).toHaveCount(3);
    for (const lv of await asks.locator('[data-level]').evaluateAll((els) => els.map((e) => e.getAttribute('data-level')))) expect(['urgent', 'decision']).toContain(lv);
    const card = asks.locator('[data-row]').filter({ hasText: 'انتشار ترمینال منتظر مُهر' });
    await expect(card.getByRole('button', { name: 'تأیید' })).toBeVisible();
    await expect(card.getByRole('button', { name: 'ببین' })).toBeVisible();
    await expect(card.locator('[data-deadline]')).toContainText('مانده');
    // By day, newest first; unread is the thin edge only (no «خوانده شد» button on the card).
    const days = page.locator('section[data-day]');
    await expect(days.first()).toHaveAttribute('aria-label', 'امروز');
    await expect(page.locator('section[data-day][aria-label="دیروز"]')).toBeVisible();
    await expect(page.locator('[data-row][data-unread]').first()).toHaveClass(/^(?!.*bg-gold)/);
    await expect(page.locator('main .bg-gold')).toHaveCount(1);
    // «خبر» is the hub's report, info and learning together; nothing of it asks.
    await bar.getByRole('radio', { name: 'خبر' }).click();
    await expect(asks).toHaveCount(0);
    expect(new Set(await page.locator('[data-row] [data-level]').evaluateAll((els) => els.map((e) => e.getAttribute('data-level'))))).toEqual(new Set(['news']));
    await expect(page.getByText('گزارش صبحگاهی آماده است')).toBeVisible();
    await expect(page.getByText('جلسه‌ی هیئت‌مدیره‌ی هلدینگ شروع شد')).toBeVisible();
    await bar.getByRole('radio', { name: 'فوری' }).click();
    await expect(page.locator('[data-row]')).toHaveCount(1);
    await expect(page.locator('[data-row]')).toContainText('پنل کاربری تریدیار کند است');
    await bar.getByRole('radio', { name: 'تصمیم' }).click();
    await expect(asks.locator('[data-row]')).toHaveCount(3);
  });
});

test('notifications: «تأیید» on a decision answers it in place, and a question is answered by its ready answer', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/notifications');
    const asks = page.getByTestId('asks');
    const card = asks.locator('[data-row]').filter({ hasText: 'انتشار ترمینال منتظر مُهر' });
    // The first decision's «تأیید» is the page's one full gold.
    await expect(card.getByRole('button', { name: 'تأیید' })).toHaveClass(/bg-gold/);
    await card.getByRole('button', { name: 'تأیید' }).click();
    await expect(page.getByText('تأیید شد.')).toBeVisible();
    await expect(page).toHaveURL(/\/notifications$/);
    await expect(asks.locator('[data-row]').filter({ hasText: 'انتشار ترمینال منتظر مُهر' })).toHaveCount(0);
    const moved = page.locator('section[data-day] [data-row]').filter({ hasText: 'انتشار ترمینال منتظر مُهر' });
    await expect(moved).toBeVisible();
    await expect(moved).not.toHaveAttribute('data-unread', '');
    // The learning question keeps its answers on its row.
    const q = page.locator('[data-row]').filter({ hasText: 'چرا انتشار قبلی را برگرداندی؟' });
    await q.getByRole('button', { name: 'ریسک' }).click();
    await expect(q.getByRole('button', { name: 'ریسک' })).toBeDisabled();
    await expect(q).not.toHaveAttribute('data-unread', '');
  });
});

test('notifications: a machine title is said in Persian with its raw text one tap away; a swipe is «خوانده شد», taken back with «برگردان»', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/notifications');
    const finding = page.locator('[data-row]').filter({ hasText: 'یافته‌ی جدی ناظر کل' }).first();
    await expect(finding).toContainText('دو سرویس پایین است');
    await expect(finding).toContainText('دیسک ۹۰٪ پر است');
    await expect(finding).not.toContainText('otel-collector');
    await expect(page.locator('[data-row]').filter({ hasText: 'بودجه‌ی تریدیار به 72٪ رسید' })).toBeVisible();
    await expect(page.locator('main')).not.toContainText('company:TY');
    // The raw words, and every time it was raised, on opening the row.
    await finding.getByRole('button', { expanded: false }).first().click();
    await expect(finding.getByRole('listitem')).toHaveCount(5);
    await finding.getByText('متن خام').click();
    await expect(finding.locator('[data-raw]')).toContainText('disk 90.4%');
    // A swipe along an unread row.
    const row = page.locator('[data-row]').filter({ hasText: 'جلسه‌ی هیئت‌مدیره‌ی هلدینگ شروع شد' });
    await expect(row).toHaveAttribute('data-unread', '');
    const box = (await row.boundingBox())!;
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 2 + 60, box.y + box.height / 2, { steps: 4 });
    await page.mouse.move(box.x + box.width / 2 + 160, box.y + box.height / 2, { steps: 6 });
    await expect(row.locator('[data-tick]').first()).toBeAttached();
    await page.mouse.up();
    await expect(page.getByRole('status').filter({ hasText: 'خوانده شد' })).toBeVisible();
    await expect(row).not.toHaveAttribute('data-unread', '');
    await page.getByRole('button', { name: 'برگردان', exact: true }).click();
    await expect(row).toHaveAttribute('data-unread', '');
  });
});

test('the notification settings speak of the same three levels', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/settings');
    for (const level of ['فوری', 'تصمیم', 'خبر']) await expect(page.getByRole('switch', { name: `${level}: push` })).toBeVisible();
    for (const old of ['گزارش', 'اطلاع', 'یادگیری']) await expect(page.getByRole('switch', { name: `${old}: push` })).toHaveCount(0);
    // A switch that is on is silver, never gold.
    await expect(page.getByRole('switch', { name: 'تصمیم: در اپ' })).toHaveClass(/^(?!.*bg-gold)/);
  });
});

// =============================================================================================== C3.6 the limits ==
test('the limits block: each Claude account one ring with its line, and today\'s meter with its three marks', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/treasury');
    const block = page.getByTestId('limits');
    await expect(block).toBeVisible();
    const main = block.locator('[data-account="main"]');
    const second = block.locator('[data-account="second"]');
    await expect(block.locator('[data-account]')).toHaveCount(2);
    await expect(main).toHaveAttribute('data-state', 'working');
    await expect(main).toContainText('اکانت اصلی');
    await expect(main.locator('[data-ring]')).toHaveAttribute('data-ring', '0.62');
    await expect(main.locator('[data-ring]')).toContainText('62%');
    await expect(main.locator('[data-account-line]')).toHaveText('الان همین کار میکند');
    await expect(second).toHaveAttribute('data-state', 'ready');
    await expect(second.locator('[data-ring]')).toContainText('8%');
    await expect(second.locator('[data-account-line]')).toHaveText('آماده');
    await expect(block.getByTestId('limits-waiting')).toHaveCount(0);
    await expect(block.locator('[data-read-at]')).toContainText(/خوانده‌شده در\s*\d{2}:\d{2}/);
    // Today's meter.
    const meter = block.getByTestId('today-meter');
    await expect(meter).toHaveAttribute('data-state', 'calm');
    await expect(meter.locator('[data-meter-figure]')).toContainText('412K');
    await expect(meter.locator('[data-meter-figure]')).toContainText('600K');
    await expect(meter.locator('[data-mark]')).toHaveCount(3);
    await expect(meter.getByRole('meter')).toHaveAttribute('aria-valuenow', '69');
    await expect(meter.locator('[data-meter-note]')).toHaveText('مصرف امروز آرام است.');
    await expect(meter.locator('[data-meter-reset]')).toContainText('از نو شروع میشود');
    // The rings take the older quota card's place; the live meter of the four kinds stays on the page.
    await expect(page.getByText('سهمیه‌ی اشتراک')).toHaveCount(0);
    await expect(page.getByTestId('token-meter')).toBeVisible();
    // The month opens with its verdict, one big number and three small ones, each saying when it was read.
    const hero = page.getByTestId('treasury-hero');
    await expect(hero.locator('[data-verdict]')).toContainText('آخر ماه');
    await expect(hero.locator('[data-small-figures] [data-amount]')).toHaveCount(3);
    await expect(hero.locator('[data-read-at]')).toContainText(/خوانده‌شده در\s*\d{2}:\d{2}/);
    // Names, never role codes.
    await expect(page.getByLabel('پرمصرف‌ها')).toContainText('مدیر فنی');
    await expect(page.getByLabel('پرمصرف‌ها')).not.toContainText(/[A-Z]{2,3}-[A-Z]+/);
  });
});

test('the limits block: every account full says until when the work waits, each with its own time and countdown', async ({ page }) => {
  await flag(page, 'hq.e2e.limits', 'both-full');
  await clean(page, async () => {
    await page.goto('/treasury');
    const block = page.getByTestId('limits');
    await expect(block.getByTestId('limits-waiting')).toContainText(/هر دو اکانت پر است؛ کارها تا\s*\d{2}:\d{2}\s*در صف میمانند/);
    for (const key of ['main', 'second']) {
      const a = block.locator(`[data-account="${key}"]`);
      await expect(a).toHaveAttribute('data-state', 'full');
      await expect(a.locator('[data-account-line]')).toContainText(/پر است؛\s*\d{2}:\d{2}\s*خالی میشود/);
      await expect(a.locator('[data-account-line]')).toContainText(/ساعت و .* دقیقه دیگر/);
      await expect(a.locator('[data-ring-live]')).toHaveCount(0);
    }
    await expect(block.locator('[data-account="main"] [data-ring]')).toContainText('100%');
    await expect(block.getByTestId('today-meter')).toHaveAttribute('data-state', 'near');
    await expect(block.getByTestId('today-meter').locator('[data-meter-word]')).toHaveText('نزدیک سقف');
  });
});

for (const [name, state, word, now] of [['warm', 'warm', 'از ۷۰٪ گذشت', '76'], ['full-day', 'full', 'سقف پر شد', '100'], ['near', 'near', 'نزدیک سقف', '93']] as const) {
  test(`today's meter and the accounts in the «${name}» state`, async ({ page }) => {
    await flag(page, 'hq.e2e.limits', name);
    await clean(page, async () => {
      await page.goto('/treasury');
      const block = page.getByTestId('limits');
      const meter = block.getByTestId('today-meter');
      await expect(meter).toHaveAttribute('data-state', state);
      await expect(meter.locator('[data-meter-word]')).toHaveText(word);
      await expect(meter.getByRole('meter')).toHaveAttribute('aria-valuenow', now);
      if (name === 'warm') {
        // One full, the other works: no queue line.
        await expect(block.locator('[data-account="main"]')).toHaveAttribute('data-state', 'full');
        await expect(block.locator('[data-account="second"] [data-account-line]')).toHaveText('الان همین کار میکند');
        await expect(block.getByTestId('limits-waiting')).toHaveCount(0);
      }
      if (name === 'near') {
        // An account that is off, and a share that is not known yet.
        await expect(block.locator('[data-account="main"] [data-account-line]')).toHaveText('خاموش');
        await expect(block.locator('[data-account="main"] [data-ring]')).toHaveAttribute('data-ring', '');
        await expect(block.locator('[data-account="second"] [data-ring]')).toContainText('—');
      }
      if (name === 'full-day') await expect(meter.locator('[data-meter-note]')).toContainText('سقف امروز پر شد');
    });
  });
}

test('on a hub before the limits route the block is not shown and the older quota card stays', async ({ page }) => {
  await flag(page, 'hq.e2e.old55', '1');
  await clean(page, async () => {
    await page.goto('/treasury');
    await expect(page.getByTestId('token-meter')).toBeVisible();
    await expect(page.getByText('سهمیه‌ی اشتراک')).toBeVisible();
    await expect(page.getByTestId('limits')).toHaveCount(0);
    await expect(page.getByTestId('treasury-hero')).toBeVisible();
  });
});

// ===================================================================================================== C0 and C1 ==
test('the shared look: a selection and a switch are silver, the separator is a hairline, a figure fits its tile', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/settings');
    await expect(page.getByRole('switch').first()).toBeVisible();
    // A selected chip or tab is never gold.
    for (const el of await page.locator('[aria-pressed="true"], [role="radio"][aria-checked="true"]').all()) await expect(el).toHaveClass(/^(?!.*(bg-gold|text-gold-ink))/);
    // The home's facts are parted by the hairline (a Persian comma for a reader), never «·» beside a digit.
    await page.goto('/');
    const row = page.getByLabel('جلسه‌ها', { exact: true }).locator('a[data-state3]').first();
    await expect(row.locator('[data-sep]').first()).toBeAttached();
    await expect(row).not.toContainText('·');
    await expect(page.getByTestId('kill-band')).not.toContainText('·');
    await expect(page.getByRole('heading', { level: 1 }).locator('xpath=ancestor::header')).not.toContainText('·');
  });
});

test('@phone the rebuilt screens and the command sheet fit a phone', async ({ page }) => {
  await page.setViewportSize({ width: 412, height: 915 });
  await clean(page, async () => {
    for (const path of ['/', '/notifications', '/treasury']) {
      await page.goto(path);
      await expect(page.locator('h1').first()).toBeVisible();
      await page.waitForLoadState('networkidle');
      expect(await overflow(page), path).toBeLessThanOrEqual(1);
    }
    // Every sign of the top bar is named.
    for (const name of ['جستجو', 'گفتگو', 'صوتی', 'اعلان', 'بیشتر']) await expect(page.locator('div.sticky.top-0').first().getByText(name, { exact: true })).toBeVisible();
    const sheet = await openCommand(page);
    await expect(sheet.locator('[data-company]').first()).toBeVisible();
    expect(await overflow(page)).toBeLessThanOrEqual(1);
    // As tall as its content, never the whole screen.
    const box = (await sheet.boundingBox())!;
    expect(box.height).toBeLessThan(page.viewportSize()!.height * 0.93);
    expect(box.y + box.height).toBeGreaterThan(page.viewportSize()!.height - 2);
  });
});
