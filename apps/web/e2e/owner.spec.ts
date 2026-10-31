import { expect, test } from '@playwright/test';
import { clean } from './support';

// The owner's three fixes of 2026-10-31, as on Android: a site's uptime as a true percentage whether the hub writes a fraction or a
// percentage; the messages page per company; and the catalogue's parts as real tables, never raw JSON.

test('site uptime reads as a percentage, from a fraction or an older hub\'s percentage', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/sites');
    await expect(page.getByText('99.8%').first()).toBeVisible();
    await expect(page.getByText('96.2%').first()).toBeVisible();
    await expect(page.getByText('100%').first()).toBeVisible();
    await expect(page.getByText(/\d{4,}(\.\d)?%/)).toHaveCount(0);
    await page.goto('/companies/TY');
    await expect(page.getByText('سلامت سایت‌ها')).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText('96.2%').first()).toBeVisible();
    await expect(page.getByText(/\d{4,}(\.\d)?%/)).toHaveCount(0);
  });
});

test('messages come per company: the holding first, each company with its CEO first, a filter, folding and a global search', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/messages');
    const sections = page.locator('section[aria-label]');
    await expect(sections.first()).toHaveAttribute('aria-label', 'هلدینگ');
    const ty = page.getByRole('region', { name: 'تریدیار' });
    // Its CEO first, though its growth manager wrote last.
    const rows = ty.getByRole('button', { name: /^ایجنت/ });
    await expect(rows.first()).toContainText('مدیرعامل تریدیار');
    await expect(rows.nth(1)).toContainText('مدیر فنی تریدیار');
    await expect(ty.getByLabel('۳ نخوانده')).toBeVisible();
    // Folding a company keeps its header and hides its rows.
    await ty.getByRole('button', { name: /تریدیار/ }).first().click();
    await expect(ty.getByText('مدیر رشد تریدیار')).toHaveCount(0);
    await ty.getByRole('button', { name: /تریدیار/ }).first().click();
    await expect(ty.getByText('مدیر رشد تریدیار')).toBeVisible();
    // The filter row shows one company alone.
    await page.getByRole('group', { name: 'گفت‌وگوهای کدام شرکت' }).getByRole('button', { name: /کوینه‌پرو FX|FX/ }).first().click();
    await expect(page.getByRole('region', { name: 'تریدیار' })).toHaveCount(0);
    await expect(page.getByText('مدیرعامل FX').first()).toBeVisible();
    // The search is global, whatever the filter shows.
    await page.getByRole('textbox', { name: 'جستجو در پیام‌ها' }).fill('ثبت‌نام');
    await expect(page.getByRole('group', { name: 'گفت‌وگوهای کدام شرکت' })).toHaveCount(0);
  });
});

test('a company page leads to its conversations', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/companies/TY');
    await page.getByRole('link', { name: /گفت‌وگوها/ }).click();
    await expect(page).toHaveURL(/\/messages\?company=TY/);
    await expect(page.getByRole('region', { name: 'تریدیار' })).toBeVisible();
    await expect(page.getByRole('region', { name: 'هلدینگ' })).toHaveCount(0);
  });
});

test('catalogue parts are tables with a sticky first column, from any section shape, never raw JSON', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/companies/TY?tab=catalogue');
    // The hub's newer shape: no key, summary_fa and notes_fa.
    await expect(page.getByRole('heading', { name: 'رابط‌ها', exact: true })).toBeVisible();
    await expect(page.getByText('وب‌هوک‌های ورودی پشت Caddy با توکن مسیر محافظت میشوند')).toBeVisible();
    // A summary that was JSON: read into its words and its table.
    const code = page.getByRole('region', { name: 'کد' });
    await expect(code.getByText(/سه مخزن روی سرور checkout شده‌اند/)).toBeVisible();
    await expect(code.getByRole('heading', { name: /پوشه‌های کاری/ })).toBeVisible();
    await expect(code.getByRole('rowheader', { name: '/srv/tradeyar/api' })).toBeVisible();
    await expect(page.getByText(/"summary_md"|```|\{"/)).toHaveCount(0);
    const firstCol = page.getByRole('rowheader').first();
    expect(await firstCol.evaluate((el) => getComputedStyle(el).position)).toBe('sticky');
  });
});
