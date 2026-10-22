import { expect, test, type Page } from '@playwright/test';

/** Every page of the panel, as the sidebar and the detail links reach them. */
const PAGES = [
  '/', '/cartable', '/outputs', '/advisor', '/oversight', '/assistant', '/companies', '/companies/FX', '/employees/FX-TECH-MGR',
  '/work/W-000104', '/messages', '/messages?thread=FX-CEO', '/workshop', '/workshop/S-0004', '/stars', '/founding', '/skills',
  '/academy', '/tools', '/treasury', '/planner', '/resolutions', '/runs', '/sites', '/control', '/audit', '/settings',
  '/revenue', '/support', '/support/SC-000411', '/growth', '/feedback',
  // ⟨1.5⟩ governance (§20)
  '/meetings', '/meetings/MT-0012', '/meetings/MT-0013', '/meetings/MT-0011', '/meetings/MT-0010', '/charter', '/knowledge', '/knowledge?ref=K-0009',
  '/scorecard', '/okr', '/outcomes', '/risks', '/calendar', '/authority',
  // ⟨1.5⟩ management tools (§21)
  '/notes', '/letter', '/letter?ref=BR-0021', '/substitutes', '/substitutes?creative=CR-0006', '/digital-ceo', '/cartable?ref=D-000017', '/cartable?ref=D-000040',
  '/companies/TY', '/employees/TY-GROWTH-01',
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

test('seals low-risk cards together with one passkey', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/cartable');
    await page.getByRole('button', { name: /مُهر گروهی/ }).click();
    const seal = page.getByRole('dialog').getByRole('button', { name: 'برای مُهر، فشار بده و نگه دار' });
    await seal.focus();
    await page.keyboard.down('Enter');
    await page.waitForTimeout(900);
    await page.keyboard.up('Enter');
    await expect(page.getByText(/کارت با یک مُهر تأیید شد/)).toBeVisible();
  });
});

test('speaks in a live meeting and moves it to the next round', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/meetings/MT-0012');
    await page.getByPlaceholder('با متن یا صدا وارد شو…').fill('ساعت کم‌بار را تأیید میکنم.');
    await page.getByPlaceholder('با متن یا صدا وارد شو…').press('Enter');
    await expect(page.getByText('حرفت در جلسه ثبت شد؛ نوبت بعد جواب میدهد.')).toBeVisible();
    await page.getByRole('button', { name: 'رفتن به دور ۲' }).click();
    await expect(page.getByText('دور ۲ شروع شد: رأی روی پیش‌نویس.')).toBeVisible();
  });
});

test('asks the hub and gets a cited answer', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/');
    await page.getByLabel('پرسش از هاب').fill('حداقل موجودی VIP کجا تعریف شده؟');
    await page.getByRole('button', { name: 'بپرس', exact: true }).click();
    await expect(page.getByText('src/bot/handlers/vip.py', { exact: false }).first()).toBeVisible();
  });
});

test('writes a quick note and promotes it to work', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/notes');
    await page.getByLabel('یادداشت تازه').fill('برای پرو-چارت یک SRE پیشنهاد بده #پرو-چارت');
    await page.getByLabel('یادداشت تازه').press('Enter');
    await expect(page.getByText(/یادداشت NT-\d+ ثبت شد/)).toBeVisible();
    await page.getByRole('button', { name: 'تبدیل', exact: true }).first().click();
    await page.getByRole('dialog').getByRole('button', { name: /پرو-چارت/ }).click();
    await page.getByRole('button', { name: 'تبدیل کن' }).click();
    await expect(page.getByText(/تبدیل شد به کار W-\d+/)).toBeVisible();
  });
});

test('asks the advisor for a devil memo on the deploy card', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/cartable?ref=D-000017');
    await expect(page.getByText('diff واقعی').first()).toBeVisible();
    await page.getByRole('button', { name: 'مخالف‌خوان', exact: true }).click();
    await expect(page.getByText('چرا نه').first()).toBeVisible();
  });
});
