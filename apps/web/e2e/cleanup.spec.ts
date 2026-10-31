import { expect, test, type Page } from '@playwright/test';
import { clean } from './support';

// ⟨1.10⟩ Contract §28 end to end over the demo holding (NEXT_PUBLIC_HQ_MOCK=1, lib/api/mock-v21.ts and mock-v28.ts): several outputs chosen
// at once (shift for a range, «همه») and filed, marked seen or deleted for good behind the passkey and a plain confirmation; the same on
// one output's page; the company's «کاتالوگ کامل»; «دیده‌بان» and its «تأیید اصلاح»; the council's failures in plain Persian; and the
// switch for the panel's error reports.

const PAGES = ['/watch', '/companies/TY?tab=catalogue', '/work/W-000209', '/outputs?tab=all'];


for (const path of PAGES) {
  test(`renders ${path} @phone`, async ({ page }) => {
    await clean(page, async () => {
      await page.goto(path);
      await expect(page.locator('h1').first()).toBeVisible();
      await page.waitForLoadState('networkidle');
    });
  });
}

const rowBoxes = (page: Page) => page.getByRole('checkbox', { name: /^انتخاب O-\d+/ });
const bar = (page: Page) => page.getByRole('toolbar', { name: 'کار با خروجی‌های انتخاب‌شده' });

test('the search names what it searches, with no ref hint', async ({ page }) => {
  await page.goto('/outputs');
  const search = page.getByRole('textbox', { name: 'جستجو در خروجی‌ها' });
  await expect(search).toHaveAttribute('placeholder', 'جستجو در عنوان و خلاصه');
});

test('chooses a range with shift and deletes it for good after the confirmation', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/outputs?tab=all');
    const boxes = rowBoxes(page);
    await expect(boxes.first()).toBeVisible();
    const before = await boxes.count();
    const names = await Promise.all([0, 1, 2].map(async (i) => (await boxes.nth(i).getAttribute('aria-label'))!.match(/O-\d+/)![0]));
    await boxes.nth(0).click();
    await boxes.nth(2).click({ modifiers: ['Shift'] });
    await expect(boxes.nth(1)).toBeChecked();
    await expect(bar(page).getByText('۳ انتخاب‌شده')).toBeVisible();
    await bar(page).getByRole('button', { name: 'حذف برای همیشه' }).click();
    const dialog = page.getByRole('dialog');
    await expect(dialog.getByText('از دیتابیس پاک میشود و برنمیگردد؛ فقط یک خط در دفتر Audit میماند.')).toBeVisible();
    await dialog.getByRole('button', { name: 'حذف برای همیشه' }).click();
    await expect(page.getByText('۳ خروجی برای همیشه پاک شد؛ از هر کدام یک خط در دفتر Audit ماند.')).toBeVisible();
    await expect(boxes).toHaveCount(before - 3);
    for (const r of names) await expect(page.getByRole('checkbox', { name: new RegExp(`^انتخاب ${r}:`) })).toHaveCount(0);
    await expect(bar(page)).toHaveCount(0);
  });
});

test('cancelling the confirmation keeps everything', async ({ page }) => {
  await page.goto('/outputs?tab=all');
  const boxes = rowBoxes(page);
  await expect(boxes.first()).toBeVisible();
  const before = await boxes.count();
  await boxes.nth(1).click();
  await bar(page).getByRole('button', { name: 'حذف برای همیشه' }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'انصراف' }).click();
  await expect(boxes).toHaveCount(before);
  await expect(bar(page).getByText('۱ انتخاب‌شده')).toBeVisible();
});

test('chooses all, files them in the archive and marks them seen', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/outputs?tab=all');
    await expect(rowBoxes(page).first()).toBeVisible();
    await page.getByRole('checkbox', { name: 'انتخاب همه‌ی خروجی‌های فهرست' }).click();
    const n = await rowBoxes(page).count();
    await expect(bar(page).getByText(`${n.toLocaleString('fa-IR')} انتخاب‌شده`)).toBeVisible();
    await bar(page).getByRole('button', { name: 'بایگانی' }).click();
    await expect(page.getByText(/خروجی در بایگانی ثبت شد|در بایگانی ثبت شد: AR-/)).toBeVisible();
    await page.getByRole('checkbox', { name: 'انتخاب همه‌ی خروجی‌های فهرست' }).click();
    await bar(page).getByRole('button', { name: 'خوانده‌شده' }).click();
    await expect(page.getByText(/خروجی خوانده شد/)).toBeVisible();
    await page.getByRole('radio', { name: /^تازه/ }).click();
    await expect(page.getByText('چیز تازه‌ای نمانده')).toBeVisible();
  });
});

test('deletes one output from its own page', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/outputs?ref=O-000040&tab=all');
    const article = page.locator('article').first();
    await expect(article.getByRole('heading', { name: 'کاتالوگ کامل سرور تریدیار' })).toBeVisible();
    await article.getByRole('button', { name: 'حذف برای همیشه' }).click();
    const dialog = page.getByRole('dialog');
    await expect(dialog.getByText('سند بایگانی‌اش میماند؛ بایگانی سابقه‌ی رسمی توست.')).toBeVisible();
    await dialog.getByRole('button', { name: 'حذف برای همیشه' }).click();
    await expect(page.getByText('برای همیشه پاک شد؛ یک خط در دفتر Audit ماند.')).toBeVisible();
    await expect(page.getByText('یک خروجی را انتخاب کن')).toBeVisible();
    await expect(page.getByRole('checkbox', { name: /^انتخاب O-000040:/ })).toHaveCount(0);
  });
});

test('reads TradeYar\'s full catalogue, part by part, with its archive record', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/companies/TY?tab=catalogue');
    await expect(page.getByRole('heading', { name: 'محصولات و سرویس‌ها' })).toBeVisible();
    await expect(page.getByRole('link', { name: /سند بایگانی AR-000094/ })).toBeVisible();
    await expect(page.getByRole('columnheader', { name: 'پروژه‌ی compose' })).toBeVisible();
    await expect(page.getByText('تغییرها از نسخه‌ی پیش')).toBeVisible();
    await page.getByRole('group', { name: 'بخش‌های کاتالوگ' }).getByRole('button', { name: 'ریسک‌ها' }).click();
    await expect(page.getByRole('heading', { name: 'ریسک‌ها', exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'محصولات و سرویس‌ها' })).toHaveCount(0);
  });
});

test('builds CoinePro FX\'s first catalogue and shows it when the run ends', async ({ page }) => {
  await page.goto('/companies/FX?tab=catalogue');
  await expect(page.getByText('هنوز کاتالوگی ساخته نشده')).toBeVisible();
  await page.getByRole('button', { name: 'ساختن کاتالوگ' }).click();
  await expect(page.getByText('در حال خواندن سرورها')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'رابط‌ها' })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole('link', { name: /سند بایگانی AR-\d+/ })).toBeVisible();
  await expect(page.getByRole('button', { name: 'تازه کن' })).toBeEnabled();
});

test('the watch groups its findings; «تأیید اصلاح» opens the session that waits for the seal', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/watch');
    for (const g of ['امنیت', 'سلامت اپ', 'کد', 'رشد', 'پیشنهاد هلدینگ']) await expect(page.getByRole('region', { name: g })).toBeVisible();
    const first = page.getByRole('region', { name: 'امنیت' }).getByRole('article').first();
    await expect(first.getByText('بحرانی')).toBeVisible();
    await expect(first.getByText('S-0002')).toBeVisible();
    await first.getByRole('button', { name: 'تأیید اصلاح' }).click();
    await expect(page).toHaveURL(/\/workshop\/S-0002/);
  });
});

test('a fix that is only words becomes a work item for the company', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/watch');
    const card = page.getByRole('article', { name: /گواهی TLS/ });
    await card.getByRole('button', { name: 'تأیید اصلاح' }).click();
    await expect(page.getByText(/اصلاح به W-\d+ سپرده شد/)).toBeVisible();
    await expect(page).toHaveURL(/\/work\/W-\d+/);
    await expect(page.getByRole('heading', { name: /اصلاح FI-\d+: گواهی TLS/ })).toBeVisible();
  });
});

test('the watch filters by group, and growth reads as advice', async ({ page }) => {
  await page.goto('/watch');
  await page.getByRole('group', { name: 'گروه‌های دیده‌بان' }).getByRole('button', { name: /رشد/ }).click();
  await expect(page.getByRole('region', { name: 'امنیت' })).toHaveCount(0);
  const growth = page.getByRole('region', { name: 'رشد' });
  await expect(growth.getByText('پیشنهاد', { exact: true }).first()).toBeVisible();
  await expect(growth.getByText(/\+۰٫۶ واحد نرخ تبدیل/).first()).toBeVisible();
});

test('the home page shows the watch at a glance', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByText('دیده‌بان', { exact: true }).first()).toBeVisible();
  await expect(page.getByRole('link', { name: /پورت 5432 پرو-چارت روی اینترنت باز است/ })).toBeVisible();
});

test('a council where only Claude answered says so, and its failures read in Persian', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/work/W-000209');
    await expect(page.getByRole('heading', { name: 'شورا' })).toBeVisible();
    await expect(page.getByRole('note').getByText('فقط Claude پاسخ داد', { exact: true })).toBeVisible();
    await expect(page.getByText('پاسخ نداد: دستورالعمل مرورگرش روی سایت جواب نداد')).toBeVisible();
    await expect(page.getByText('پاسخ نداد: مدلش با این اشتراک پشتیبانی نمیشود')).toBeVisible();
    await expect(page.getByText('بازیکن ذخیره‌ی DeepSeek خاموش است؛ شورا بدون او برگزار شد.')).toBeVisible();
    // Never raw JSON or the provider's English on the card until «جزئیات» is opened.
    await expect(page.getByText(/recipe_failed/)).toHaveCount(0);
    await expect(page.getByText(/not supported when using Codex/)).toHaveCount(0);
    await page.getByRole('listitem', { name: /^Gemini/ }).getByRole('button', { name: 'جزئیات' }).click();
    await expect(page.getByText(/"code": "recipe_failed"/)).toBeVisible();
  });
});

test('error reports to the hub can be turned off in Settings', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/settings');
    const sw = page.getByRole('switch', { name: 'ارسال گزارش خطا به هاب' });
    await expect(sw).toHaveAttribute('aria-checked', 'true');
    await sw.click();
    await expect(page.getByText('ارسال خاموش است')).toBeVisible();
    await page.reload();
    await expect(page.getByRole('switch', { name: 'ارسال گزارش خطا به هاب' })).toHaveAttribute('aria-checked', 'false');
  });
});
