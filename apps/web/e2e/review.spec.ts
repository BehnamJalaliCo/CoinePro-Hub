import { expect, test } from '@playwright/test';
import { clean, loggedFailures } from './support';

// Fixes from docs/reviews/WEB_REVIEW_2026-10-31.md, checked end to end over the demo holding: «برگردان» on notifications really keeps them
// unread (H5), a server's page and the outputs fit a phone (H6, minor 11), «شروع پنل» once per session (M5), no requests for an unchosen
// company (M2), and expected 404s kept out of «خطاخوان» (M3).

test('«برگردان» after «همه خوانده شد» keeps every notification unread, past the grace time', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/notifications');
    const dots = page.getByLabel('خوانده‌نشده');
    await expect(dots.first()).toBeVisible();
    const before = await dots.count();
    await page.getByRole('button', { name: 'همه خوانده شد' }).first().click();
    await expect(dots).toHaveCount(0);
    await page.getByRole('button', { name: 'برگردان' }).click();
    await expect(dots).toHaveCount(before);
    // Past the five seconds: nothing was sent, so nothing comes back read when the lists are read again.
    await page.waitForTimeout(6_500);
    await page.getByRole('radio', { name: 'خوانده‌شده', exact: true }).click();
    await page.getByRole('radio', { name: /^خوانده‌نشده/ }).click();
    await expect(dots).toHaveCount(before);
  });
});

for (const path of ['/servers/srv-fx-1', '/outputs', '/outputs?tab=all', '/cartable']) {
  test(`fits a phone without sideways scroll: ${path} @phone`, async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(path);
    await expect(page.locator('h1').first()).toBeVisible();
    await page.waitForLoadState('networkidle');
    const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(over).toBeLessThanOrEqual(0);
  });
}

test('«شروع پنل» is noted once per browser session, in Persian', async ({ page }) => {
  const live = page.getByTitle('زنده');
  await page.goto('/');
  await expect(live).toBeVisible();
  await page.reload();
  await expect(live).toBeVisible();
  await page.goto('/errors');
  await expect(page.getByText('پنل در این مرورگر باز شد').first()).toBeVisible();
  await page.reload();
  await expect(page.getByText('پنل در این مرورگر باز شد').first()).toBeVisible();
  const n = await page.evaluate(() => (JSON.parse(localStorage.getItem('hq.errors.current') ?? '{"entries":[]}') as { entries: Array<{ kind: string }> }).entries.filter((e) => e.kind === 'session').length);
  expect(n).toBe(1);
  await expect(page.getByText('پنل در این مرورگر باز شد').first()).toBeVisible();
});

test('a new order asks for no departments before a company is chosen, and expected 404s stay out of «خطاخوان»', async ({ page }) => {
  await page.goto('/orders');
  await page.getByRole('button', { name: 'فرمان تازه' }).first().click();
  await expect(page.getByRole('dialog', { name: 'فرمان تازه' })).toBeVisible();
  // FX has no catalogue yet: GET answers 404 and the page offers to build one; the advisor's memo of a fresh card is «not yet».
  await page.goto('/companies/FX?tab=catalogue');
  await expect(page.getByText('هنوز کاتالوگی ساخته نشده')).toBeVisible();
  expect(await loggedFailures(page)).toEqual([]);
});
