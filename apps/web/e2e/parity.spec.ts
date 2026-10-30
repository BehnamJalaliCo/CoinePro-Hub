import { expect, test, type Page } from '@playwright/test';

// The Android app's 0.3.0–0.6.0 on the web, end to end over the demo holding (NEXT_PUBLIC_HQ_MOCK=1, lib/api/mock-v21.ts): outputs seen and
// filed, the control layer and the control room, removing a company, «فرمان‌های من», priorities in words, notifications read and folded,
// the founding wizard, the ref router, «خطاخوان» and a hub restart, and «همه‌ی بخش‌ها».

const PAGES = [
  '/orders', '/notifications', '/errors', '/founding/new', '/work/W-000210', '/work/W-000204', '/companies/PC', '/companies/HQ', '/outputs?ref=O-000032',
  '/outputs?tab=seen', '/control', '/companies',
];

/** Fails the test on any page error, console error or failed API call while [run] is going on. */
async function clean(page: Page, run: () => Promise<void>) {
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(`pageerror: ${e.message}`));
  page.on('console', (m) => { if (m.type() === 'error') errors.push(`console: ${m.text()}`); });
  page.on('response', (r) => { if (r.url().includes('/api/v1/') && r.status() >= 400) errors.push(`HTTP ${r.status()} ${r.url()}`); });
  await run();
  expect(errors, errors.join('\n')).toEqual([]);
}

for (const path of PAGES) {
  test(`renders ${path} @phone`, async ({ page }) => {
    await clean(page, async () => {
      await page.goto(path);
      await expect(page.locator('h1').first()).toBeVisible();
      await page.waitForLoadState('networkidle');
    });
  });
}

test('reads the morning report with its table, marks it seen, takes it back and files it', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/outputs?ref=O-000032');
    await expect(page.locator('table').first()).toBeVisible();
    await expect(page.getByRole('columnheader', { name: 'شرکت', exact: true })).toBeVisible();
    await page.locator('article').getByRole('button', { name: 'خوانده شد', exact: true }).click();
    await expect(page.getByText('O-000032 به «خوانده‌شده» رفت')).toBeVisible();
    await page.getByRole('button', { name: 'برگردان' }).click();
    await page.getByRole('button', { name: 'بایگانی کن' }).click();
    await expect(page.getByText(/در بایگانی ثبت شد: AR-\d+/)).toBeVisible();
  });
});

test('filters outputs by category and moves a new one to «خوانده‌شده»', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/outputs');
    await page.getByRole('button', { name: 'گزارش', exact: true }).click();
    await expect(page.getByText('گزارش صبحگاهی ۱۴۰۵/۰۷/۲۵ / 2026-10-17').first()).toBeVisible();
    await page.getByRole('button', { name: 'خوانده شد', exact: true }).first().click();
    await page.getByRole('radio', { name: 'خوانده‌شده' }).click();
    await expect(page.getByText('گزارش صبحگاهی ۱۴۰۵/۰۷/۲۵ / 2026-10-17').first()).toBeVisible();
  });
});

test('stops a company at once and resumes it with the passkey', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/companies');
    const ty = page.locator('div', { has: page.getByRole('button', { name: 'باز کردن تریدیار' }) }).last();
    await ty.getByRole('button', { name: 'توقف', exact: true }).click();
    await page.getByRole('button', { name: 'فوری، بدون دلیل' }).click();
    await expect(page.getByText('تریدیار متوقف شد؛ هیچ چیز از دست نرفت.')).toBeVisible();
    await ty.getByRole('button', { name: 'ادامه با اثر انگشت' }).click();
    await page.getByRole('dialog').getByRole('button', { name: 'ادامه با اثر انگشت' }).click();
    await expect(page.getByText('تریدیار دوباره کار میکند.')).toBeVisible();
  });
});

test('closes and opens a company\'s deploys from its control room, with the switches\' history', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/companies/TY');
    await expect(page.getByRole('radio', { name: 'اتاق کنترل' })).toHaveAttribute('aria-checked', 'true');
    await expect(page.getByText('تاریخچه‌ی کلیدها')).toBeVisible();
    await expect(page.getByText('«مصرف کمپین پاییز از کنترل خارج شد.»')).toBeVisible();
    await page.getByRole('button', { name: 'ببند', exact: true }).click();
    await page.getByRole('dialog').getByRole('button', { name: 'ببند', exact: true }).click();
    await expect(page.getByText('deploy تریدیار بسته شد؛ کارهای دیگر ادامه دارند.')).toBeVisible();
    await page.getByRole('button', { name: 'باز کن', exact: true }).click();
    await page.getByRole('dialog').getByRole('button', { name: 'باز کن با اثر انگشت' }).click();
    await expect(page.getByText('deploy تریدیار باز شد.')).toBeVisible();
  });
});

test('registers a company with the wizard, then deletes it with its code; a company with a history is only archived', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/founding/new');
    await page.getByPlaceholder('مثلاً دایرکت هوشمند').fill('دایرکت هوشمند');
    await page.getByPlaceholder('IG').fill('ig');
    await page.getByPlaceholder('مثلاً پاسخ خودکار و فروش در دایرکت اینستاگرام').fill('پاسخ خودکار و فروش در دایرکت');
    await page.getByRole('button', { name: 'بعدی' }).click();
    await page.getByRole('radio', { name: /فقط ثبت کن/ }).click();
    await page.getByRole('button', { name: 'بعدی' }).click();
    await page.getByRole('button', { name: 'بعداً؛ بعدی' }).click();
    await expect(page.getByText('با تأیید تو')).toBeVisible();
    await page.getByRole('button', { name: 'ثبت کن' }).click();
    await expect(page).toHaveURL(/\/companies\/IG/);
    await page.getByRole('button', { name: 'حذف', exact: true }).click();
    await page.getByLabel('کد شرکت').fill('ig');
    await page.getByRole('button', { name: 'حذف برای همیشه' }).click();
    await expect(page.getByText('دایرکت هوشمند حذف شد.')).toBeVisible();
    await page.goto('/companies/FX');
    await page.getByRole('button', { name: 'حذف', exact: true }).click();
    await page.getByLabel('کد شرکت').fill('FX');
    await page.getByRole('button', { name: 'حذف برای همیشه' }).click();
    await expect(page.getByText('کوینه‌پرو FX سابقه دارد و حذف نمیشود')).toBeVisible();
    await expect(page.getByRole('button', { name: 'بایگانی شرکت با گذرکلید' })).toBeVisible();
  });
});

test('follows the owner\'s orders: stages, the estimate, who holds it, the live timeline', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/orders');
    await expect(page.getByText('گزارش رقبای صرافی در ۳۰ روز گذشته')).toBeVisible();
    await page.getByRole('button', { name: 'تحویل‌شده' }).click();
    await expect(page.getByText('منتظر نگاه تو: خروجی را ببین و امتیاز بده تا بسته شود.').first()).toBeVisible();
    await page.goto('/work/W-000210');
    await expect(page.getByText('پیگیری فرمان')).toBeVisible();
    await expect(page.getByText(/الان دست مدیرعامل ← مدیر رشد ← /)).toBeVisible();
    await expect(page.getByText('روند کار')).toBeVisible();
    await expect(page.getByRole('link', { name: /دیدن خروجی O-000046/ })).toBeVisible();
  });
});

test('gives an order with a priority in words', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/orders');
    await page.getByRole('button', { name: 'فرمان تازه' }).first().click();
    await page.getByRole('dialog').getByRole('button', { name: /تریدیار/ }).click();
    await page.getByRole('radio', { name: /^فوری، P1/ }).click();
    await expect(page.getByText('چیزی که کاربران محصول مستقیم میبینند؛ جلوتر از کارهای دیگر در صف.')).toBeVisible();
    await page.getByPlaceholder('مثلاً: علت کندی ثبت‌نام را پیدا کن و راه‌حل بده').fill('بررسی خطای ورود با گوگل');
    await page.getByRole('button', { name: 'بفرست' }).click();
    await expect(page.getByText(/فرمان ثبت شد: W-\d+/)).toBeVisible();
  });
});

test('folds a repeated alert, reads it and finds it among the read', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/notifications');
    await expect(page.getByText('۵ بار، آخرین', { exact: false }).or(page.getByText('5 بار، آخرین', { exact: false })).first()).toBeVisible();
    await page.getByRole('button', { name: 'همه خوانده شد' }).nth(1).click();
    await expect(page.getByText('5 اعلان خوانده شد').or(page.getByText('۵ اعلان خوانده شد'))).toBeVisible();
    await page.getByRole('radio', { name: 'خوانده‌شده' }).click();
    await expect(page.getByText(/یافته‌ی جدی ناظر کل/).first()).toBeVisible();
  });
});

test('opens a meeting\'s ref on its own page, never as a work', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/work/MT-0012');
    await expect(page).toHaveURL(/\/meetings\/MT-0012/);
  });
});

test('shows one calm line while the hub restarts and keeps one entry in «خطاخوان»', async ({ page }) => {
  await page.goto('/errors');
  await expect(page.getByRole('heading', { name: 'خطاخوان' })).toBeVisible();
  await page.getByRole('button', { name: 'نمایش', exact: true }).click();
  // Within the same page load: the demo's restart lives in the page's own fixtures.
  await page.getByRole('link', { name: 'فرمان‌های من' }).first().click();
  await expect(page.getByText('هاب در حال راه‌اندازی دوباره است؛ خودکار وصل میشوم.')).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText('هاب در حال راه‌اندازی دوباره است؛ خودکار وصل میشوم.')).toBeHidden({ timeout: 40_000 });
  await page.getByRole('button', { name: 'همه‌ی بخش‌ها' }).click();
  await page.getByRole('link', { name: /^خطاخوان:/ }).click();
  await expect(page.getByText('هاب در دسترس نبود').first()).toBeVisible();
});

test('opens every place from «همه‌ی بخش‌ها», grouped, each with its line', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/');
    await page.getByRole('button', { name: 'همه‌ی بخش‌ها' }).click();
    await expect(page.getByRole('region', { name: 'سیستم و ایمنی' })).toBeVisible();
    await page.getByRole('link', { name: /^فرمان‌های من:/ }).click();
    await expect(page).toHaveURL(/\/orders/);
  });
});
