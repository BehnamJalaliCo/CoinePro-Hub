import { expect, test, type Page } from '@playwright/test';

/** Every page of the panel, as the sidebar and the detail links reach them. */
const PAGES = [
  '/', '/cartable', '/outputs', '/advisor', '/oversight', '/assistant', '/companies', '/companies/FX', '/employees/FX-TECH-MGR',
  '/work/W-000104', '/messages', '/messages?thread=FX-CEO', '/workshop', '/workshop/S-0004', '/stars', '/founding', '/skills',
  '/academy', '/tools', '/treasury', '/planner', '/resolutions', '/runs', '/sites', '/control', '/audit', '/settings',
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

test('records a resolution from a message', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/messages?thread=FX-CEO');
    await page.getByRole('button', { name: 'مصوبه' }).first().click();
    await page.getByRole('button', { name: 'ثبت مصوبه' }).click();
    await expect(page.getByText(/مصوبه‌ی M-\d+ ثبت شد/)).toBeVisible();
    await page.goto('/resolutions');
    await expect(page.locator('article').first()).toBeVisible();
  });
});

test('cancels a work item with a reason', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/work/W-000104');
    await page.getByRole('button', { name: 'لغو', exact: true }).click();
    await page.getByPlaceholder('دلیل (لازم)').fill('دیگر لازم نیست');
    await page.getByRole('button', { name: 'لغو کن' }).click();
    await expect(page.getByText('لغو شد').first()).toBeVisible();
  });
});

test('freezes and lifts deploys of a company', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/control');
    await page.getByRole('button', { name: 'توقف deploy', exact: true }).first().click();
    await page.getByRole('button', { name: 'متوقف کن', exact: true }).click();
    await expect(page.getByRole('button', { name: 'برداشتن توقف deploy' }).first()).toBeVisible();
  });
});

test('searches messages from the messages page', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/messages');
    await page.getByLabel('جستجو در پیام‌ها').fill('ثبت‌نام');
    await expect(page.getByText('FX-CEO-0008')).toBeVisible();
  });
});

test('saves the notification matrix', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/settings');
    await page.getByRole('switch', { name: 'گزارش: push' }).click();
    await page.getByRole('button', { name: 'ذخیره', exact: true }).click();
    await expect(page.getByText('تنظیمات اعلان ذخیره شد.')).toBeVisible();
  });
});
