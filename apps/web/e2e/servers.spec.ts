import { expect, test, type Page } from '@playwright/test';

// ⟨1.8⟩ Contract §26: the companies' servers, the owner's terminal, pairing, the server rules and the holding's network map, end to end
// over the demo holding (NEXT_PUBLIC_HQ_MOCK=1, lib/api/mock-v26.ts).

const PAGES = ['/servers', '/servers/srv-fx-1', '/servers/srv-ty-1', '/servers/srv-pc-1', '/servers/srv-fx-2', '/servers/srv-fx-1/terminal', '/servers/attach', '/server-policy', '/network', '/companies/TY?tab=servers'];

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

test('lists every server by its company, with its state', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/servers');
    await expect(page.getByRole('heading', { name: 'همه‌ی سرورها' })).toBeVisible();
    // The owner's rule: a server is called by its company; the server's own name follows when the company has several.
    await expect(page.getByRole('link', { name: 'باز کردن سرور کوینه‌پرو FX · fx-main' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'باز کردن سرور پرو-چارت' })).toBeVisible();
    await expect(page.getByText('آفلاین').first()).toBeVisible();
    await expect(page.getByText('باطل‌شده').first()).toBeVisible();
  });
});

test('reads a server map, its live activity and its Claude sessions', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/servers/srv-ty-1');
    await expect(page.getByRole('heading', { name: 'کانتینرها' })).toBeVisible();
    await expect(page.getByText('/home/tradeyar/TradeYar').first()).toBeVisible();
    await page.getByRole('radio', { name: 'فعالیت' }).click();
    await expect(page.getByText('cat /etc/nginx/sites-enabled/tradeyar.conf')).toBeVisible();
    await page.getByRole('button', { name: 'متن کامل' }).first().click();
    await expect(page.getByRole('dialog').getByText(/exit/)).toBeVisible();
    await page.keyboard.press('Escape');
    await page.getByRole('radio', { name: 'جلسه‌ها' }).click();
    await page.getByText('کش nginx برای صفحه‌های بازار').click();
    await expect(page).toHaveURL(/\/workshop\/S-0011$/);
    await expect(page.getByText('Claude Code خود سرور شرکت')).toBeVisible();
  });
});

test('runs a command in the owner terminal and streams its output', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/servers/srv-fx-1/terminal');
    await page.getByRole('textbox', { name: 'فرمان', exact: true }).fill('df -h');
    await page.getByRole('button', { name: 'اجرا با اثر انگشت' }).click();
    const log = page.getByRole('log', { name: 'خروجی ترمینال' });
    await expect(log.getByText('forex@coinepro-fx$ df -h')).toBeVisible();
    await expect(log.getByText('/dev/sda1       150G   62G   82G  43% /')).toBeVisible();
    await expect(log.getByText(/^exit 0/)).toBeVisible();
  });
});

test('a destructive command in the terminal becomes a card in the cartable', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/servers/srv-fx-1/terminal');
    await page.getByRole('textbox', { name: 'فرمان', exact: true }).fill('docker volume rm coinepro_old');
    await page.getByRole('button', { name: 'اجرا با اثر انگشت' }).click();
    await expect(page.getByText('کارتش در کارتابل منتظر مُهر توست.')).toBeVisible();
    // The demo lives in the page: open the cartable from the toast (client-side), not by reloading.
    await page.getByRole('button', { name: 'کارت', exact: true }).click();
    await expect(page).toHaveURL(/\/cartable\?ref=D-\d+/);
    const card = page.getByRole('article', { name: /کار ویرانگر D-0002/ }).filter({ hasText: 'docker volume rm coinepro_old' });
    await expect(card).toBeVisible();
    await card.getByRole('button', { name: 'مُهر بزن' }).click();
    await expect(page.getByText(/مُهر خورد؛ فرمان روی سرور کوینه‌پرو FX · fx-main اجرا میشود/)).toBeVisible();
  });
});

test('delegates a task to Claude on the server, in a repository picked from its map', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/servers/srv-fx-1');
    await page.getByRole('button', { name: 'یک کار بسپار' }).click();
    const sheet = page.getByRole('dialog');
    await sheet.getByRole('radio', { name: '/home/forex/fx-landing' }).click();
    await sheet.getByPlaceholder(/عنوان؛/).fill('صفحه‌ی فرود تازه');
    await sheet.getByLabel('چه باید بشود و کی تمام است').fill('بخش قیمت‌ها را به‌روز کن و deploy کن.');
    await sheet.getByRole('button', { name: 'شروع کن' }).click();
    await expect(page).toHaveURL(/\/workshop\/S-\d+$/);
    await expect(page.getByRole('heading', { name: 'صفحه‌ی فرود تازه' })).toBeVisible();
  });
});

test('pairs a server with its short code and waits until it is online', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/servers/attach?company=FX');
    await page.getByLabel('کد جفت‌سازی').fill('fx3r82nb');
    await expect(page.getByLabel('کد جفت‌سازی')).toHaveValue('FX3R-82NB');
    await page.getByRole('button', { name: 'تأیید با گذرکلید' }).click();
    await expect(page.getByText(/کد تأیید شد؛ سرور کوینه‌پرو FX · fx-worker به ستاد پیوست/)).toBeVisible();
    await expect(page.getByText('آنلاین شد')).toBeVisible({ timeout: 20_000 });
  });
});

test('an expired pairing code says so in plain words', async ({ page }) => {
  await page.goto('/servers/attach?company=TY');
  await page.getByLabel('کد جفت‌سازی').fill('ABCD0000');
  await page.getByRole('button', { name: 'تأیید با گذرکلید' }).click();
  await expect(page.getByRole('alert').filter({ hasText: 'این کد منقضی شده' })).toBeVisible();
});

test('changes the server rules with the passkey', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/server-policy');
    await page.getByRole('switch', { name: 'حذف سرور' }).click();
    await expect(page.getByText('بدون مُهر اجرا میشود: حذف سرور')).toBeVisible();
    await page.getByRole('button', { name: 'با گذرکلید ذخیره کن' }).click();
    await expect(page.getByText('قوانین سرورها ذخیره شد.')).toBeVisible();
    await page.getByRole('switch', { name: 'حذف سرور' }).click();
    await page.getByRole('button', { name: 'با گذرکلید ذخیره کن' }).click();
    await expect(page.getByText('قوانین سرورها ذخیره شد.').first()).toBeVisible();
  });
});

test('the network map names what is broken and checks every road again', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/network');
    await expect(page.getByRole('heading', { name: 'شبکه‌ی هلدینگ' })).toBeVisible();
    await expect(page.getByText('۱ مسیر قطع است').or(page.getByText('1 مسیر قطع است'))).toBeVisible();
    await expect(page.getByText('IG-Hub از راه عمومی به هاب وصل است')).toBeVisible();
    await page.getByRole('button', { name: 'راه‌های پرو-چارت' }).click();
    const detail = page.getByLabel('راه‌های پرو-چارت').last();
    await expect(detail.getByText('از این سرور به سرورهای دیگر')).toBeVisible();
    await expect(detail.getByLabel('پورت بسته است')).toBeVisible();
    await page.getByRole('button', { name: 'بررسی دوباره' }).click();
    await expect(page.getByRole('status').getByText(/در حال بررسی/)).toBeVisible();
    await expect(page.getByText('بررسی تمام شد؛ همه‌ی سرورها جواب دادند.')).toBeVisible({ timeout: 30_000 });
  });
});

test('detaches a server from the hub', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/servers/srv-ty-1');
    await page.getByRole('button', { name: 'کارهای این سرور' }).click();
    await page.getByRole('menuitem', { name: 'جدا کردن از هاب' }).click();
    await page.getByRole('button', { name: 'با گذرکلید جدا کن' }).click();
    await expect(page).toHaveURL(/\/servers$/);
    await expect(page.getByText(/runner سرور تریدیار · ty-web باطل شد/)).toBeVisible();
  });
});
