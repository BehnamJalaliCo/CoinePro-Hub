import { expect, test } from '@playwright/test';
import { clean } from './support';

// The hub audit's findings on the web panel (2026-11-12), end to end over the demo holding, whose mocks now answer in the hub's own
// shapes: the tools page sums the egress days and registers a Telegram source with its channel, a meeting is made and the settings
// saved without the fields the hub refuses, a first-month hire without a score, the employee layer without an expiry, the shadow test's
// history upload and verdict, Persian digits and a decimal point in a limit, and a red line's patterns typed line by line.

test.use({ reducedMotion: 'reduce' });

test('tools: the day is summed from the egress rows; a Telegram source is registered with its channel and its own command', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/tools');
    await expect(page.getByText('1,284', { exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'ثبت منبع' }).click();
    const sheet = page.getByRole('dialog', { name: 'ثبت منبع ورودی' });
    await sheet.getByRole('button', { name: /تریدیار/ }).click();
    await sheet.getByRole('button', { name: 'تلگرام', exact: true }).click();
    await sheet.getByRole('group', { name: 'کانال تلگرام' }).getByRole('button', { name: 'تلگرام بیزینس' }).click();
    await expect(sheet.getByText('make telegram-bot-token COMPANY=TY CHANNEL=telegram_business')).toBeVisible();
    await sheet.getByRole('button', { name: 'ثبت با passkey' }).click();
    await expect(page.getByText('منبع ثبت شد؛ رمزش را در ترمینال خودت بگذار.')).toBeVisible();
  });
});

test('a meeting is made with titled items only (no postmortem by hand), and the settings save only what changed', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/meetings');
    await page.getByRole('button', { name: 'جلسه‌ی تازه' }).click();
    const sheet = page.getByRole('dialog', { name: 'جلسه‌ی تازه' });
    await expect(sheet.getByRole('button', { name: 'کالبدشکافی' })).toHaveCount(0);
    await sheet.getByRole('button', { name: /تریدیار/ }).click();
    await sheet.getByLabel('زمان شروع').fill('2026-12-01T10:00');
    await sheet.getByPlaceholder('دستور 1').fill('مرور فروش ماه');
    await sheet.getByRole('button', { name: 'بساز' }).click();
    await expect(page).toHaveURL(/\/meetings\/MT-\d+/);
    await page.goto('/meetings');
    await page.getByRole('radio', { name: 'تنظیمات' }).click();
    await page.getByLabel(/^دور /).first().selectOption('1');
    await page.getByRole('button', { name: 'ذخیره', exact: true }).click();
    await page.getByRole('button', { name: 'مُهر با passkey' }).click();
    await expect(page.getByText('تنظیمات جلسه‌ها مُهر و ذخیره شد.')).toBeVisible();
  });
});

test('a hire in its first month is in the HR round with a dash, not a crash', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/employees/TY-GROWTH-01');
    await page.getByRole('button', { name: 'کل دور' }).click();
    const sheet = page.getByRole('dialog');
    await expect(sheet.getByText('TY-CONTENT-02')).toBeVisible();
    await expect(sheet.getByText('هنوز امتیازی نیست')).toBeVisible();
  });
});

test('the employee layer of the knowledge base has no expiry and does not crash', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/knowledge');
    await page.getByRole('button', { name: 'کارمند', exact: true }).click();
    await expect(page.getByText('بی‌انقضا').first()).toBeVisible();
  });
});

test('shadow test: a CSV history goes up as text and builds the suite; an export without pairs says so; the verdict reads pass_', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/support');
    await page.getByRole('radio', { name: 'آزمون سایه' }).click();
    await expect(page.getByText('قبول نشد', { exact: true })).toBeVisible();
    const pick = page.locator('input[type=file][accept*=".csv"]').first();
    await pick.setInputFiles({ name: 'history.csv', mimeType: 'text/csv', buffer: Buffer.from('question,answer\nسلام,درود\n') });
    await expect(page.getByText(/مجموعه‌ی آزمون .* ساخته شد/)).toBeVisible();
    await pick.setInputFiles({ name: 'empty.csv', mimeType: 'text/csv', buffer: Buffer.from('question,answer\n') });
    await expect(page.getByText('در این فایل هیچ پرسش و پاسخی پیدا نشد؛ خروجی گفت‌وگوهای پشتیبانی را بده.')).toBeVisible();
  });
});

test('a limit takes Persian digits and a decimal point as typed', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/authority');
    const field = page.getByLabel(/^مقدار /).first();
    await field.fill('۱۲');
    await expect(field).toHaveValue('12');
    await field.fill('2.');
    await expect(field).toHaveValue('2.');
    await field.type('5');
    await expect(field).toHaveValue('2.5');
  });
});

test('a red line takes its patterns line by line (Enter at the end is kept)', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/charter');
    await page.getByRole('button', { name: 'نسخه‌ی تازه' }).first().click();
    const sheet = page.getByRole('dialog');
    await sheet.getByRole('button', { name: 'خط قرمز تازه' }).click();
    await sheet.getByLabel('روش سنجش').last().selectOption('rule');
    const box = sheet.getByLabel('الگوها').last();
    await box.click();
    await box.type('abc');
    await box.press('Enter');
    await box.type('def');
    await expect(box).toHaveValue('abc\ndef');
  });
});

test('a new talk after a manager starts with the secretary, not a manager without a company', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/talk');
    await page.getByRole('button', { name: 'مدیر یک شرکت را بیاور' }).click();
    const sheet = page.getByRole('dialog', { name: 'مدیر یک شرکت را بیاور' });
    await sheet.getByRole('button', { name: 'تریدیار' }).click();
    await sheet.getByRole('button', { name: 'مدیرعامل' }).click();
    await expect(page.getByLabel('حاضر: مدیرعامل تریدیار')).toBeVisible();
    await page.getByRole('button', { name: 'گفتگوی تازه' }).first().click();
    await page.getByRole('textbox', { name: 'پیام' }).fill('سلام');
    await page.getByRole('button', { name: 'بفرست', exact: true }).click();
    await expect(page.getByLabel('گفتگو', { exact: true }).locator('[data-by="owner"]').getByText('سلام', { exact: true })).toBeVisible();
  });
});
