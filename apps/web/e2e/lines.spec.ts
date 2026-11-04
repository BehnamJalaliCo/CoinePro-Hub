import { expect, test } from '@playwright/test';
import { clean } from './support';

// ⟨1.12⟩ Contract §30 end to end over the demo holding (NEXT_PUBLIC_HQ_MOCK=1, lib/api/mock-v30.ts; animations off): a line made from a
// template, a prompt edited and saved as a new version, one step tested alone, a dry run, a waiting run sealed, the calendar and the library.

test.use({ reducedMotion: 'reduce' });

const PAGES = ['/companies/TY?tab=lines', '/lines/LN-0001', '/line-runs/LR-000001', '/line-runs/LR-000002', '/campaign-calendar', '/library'];
for (const path of PAGES) {
  test(`renders ${path} and fits a phone @phone`, async ({ page }) => {
    await clean(page, async () => {
      await page.goto(path);
      await expect(page.locator('h1').first()).toBeVisible();
      await page.waitForLoadState('networkidle');
      const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(over).toBeLessThanOrEqual(0);
    });
  });
}

test('a line is made from a template and opens as a draft', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/companies/FX?tab=lines');
    await expect(page.getByRole('link', { name: /خط پست روزانه‌ی کانال FX/ })).toBeVisible();
    await page.getByRole('button', { name: 'خط تازه' }).first().click();
    const sheet = page.getByRole('dialog');
    await sheet.getByRole('button', { name: 'الگوی ریلز اینستاگرام' }).click();
    await sheet.getByLabel('نام خط').fill('ریلز هفتگی FX');
    await sheet.getByLabel('صفحه یا کانال').fill('coinepro.fx');
    await sheet.getByRole('button', { name: 'بساز' }).click();
    await expect(page.locator('h1').first()).toHaveText('ریلز هفتگی FX');
    await expect(page.getByLabel('حالت خط')).toContainText('پیش‌نویس');
    await expect(page.getByLabel('حالت خط')).toContainText('0 از 7 اجرای خوب');
    await expect(page.getByRole('button', { name: 'خودکار کن' })).toBeDisabled();
    await expect(page.getByRole('article')).toHaveCount(11);
  });
});

test('a prompt is edited and saved as a new version; one step is tested; the whole line runs dry', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/lines/LN-0001');
    await expect(page.getByLabel('حالت خط')).toContainText('3 از 7 اجرای خوب');
    const first = page.getByRole('article', { name: /^قدم 1: نوشتن سناریو/ });
    await first.getByRole('button', { name: /^نوشتن سناریو/ }).click();
    const prompt = first.getByLabel('دستور نوشتن سناریو');
    await prompt.fill('یک سناریوی کوتاه درباره‌ی ');
    await first.getByRole('button', { name: 'درج topic' }).click();
    await expect(prompt).toHaveValue('یک سناریوی کوتاه درباره‌ی {{topic}}');
    // Unsaved: the tests wait for the save.
    await expect(page.getByRole('button', { name: 'آزمایش کامل' })).toBeDisabled();
    await page.getByLabel('یادداشت نسخه').fill('سناریوی کوتاه‌تر');
    await page.getByRole('button', { name: 'ذخیره، نسخه‌ی تازه' }).click();
    await expect(page.getByText('نسخه‌ی 3 ذخیره شد.')).toBeVisible();
    await expect(page.getByRole('button', { name: /^نسخه‌ها/ })).toContainText('3');
    // The version list keeps the note; the old one can be reverted to.
    await page.getByRole('button', { name: /^نسخه‌ها/ }).click();
    const sheet = page.getByRole('dialog', { name: 'نسخه‌ها' });
    await expect(sheet.getByText('سناریوی کوتاه‌تر')).toBeVisible();
    await expect(sheet.getByRole('button', { name: 'برگرد به نسخه‌ی 2' })).toBeVisible();
    await sheet.getByRole('button', { name: 'بستن' }).first().click();

    await first.getByRole('button', { name: 'آزمایش همین مرحله' }).click();
    await expect(first.getByLabel('نتیجه‌ی آزمایش').getByText('جواب نمونه برای دستور ذخیره‌شده.')).toBeVisible();

    await page.getByRole('button', { name: 'آزمایش کامل' }).click();
    await expect(page).toHaveURL(/\/line-runs\/LR-000003$/);
    await expect(page.getByText('آزمایشی', { exact: true }).first()).toBeVisible();
    await expect(page.getByRole('list', { name: 'قدم‌های اجرا' }).getByRole('listitem')).toHaveCount(11);
  });
});

test('a step that speaks offers the voices; a cover step offers the cover folders', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/lines/LN-0001');
    await page.getByRole('article', { name: /^قدم 3: صدا/ }).getByRole('button', { name: /^صدا/ }).click();
    const voices = page.getByRole('group', { name: 'گوینده' });
    await expect(voices.getByRole('button', { name: /^شارون Charon/ })).toBeVisible();
    await voices.getByRole('button', { name: /^شارون Charon/ }).click();
    await expect(voices.getByRole('button', { name: /^شارون Charon/ })).toHaveAttribute('aria-pressed', 'true');
    await expect(voices.getByRole('button', { name: 'نمونه‌ی صدای شارون' })).toBeVisible();
    await page.getByRole('article', { name: /^قدم 9: کاور/ }).getByRole('button', { name: /^کاور/ }).click();
    await expect(page.getByRole('group', { name: 'پوشه‌ی کاور' }).getByRole('button', { name: /کاورهای تریدیار/ })).toBeVisible();
  });
});

test('a waiting run is sealed behind the passkey and counts as a good run', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/line-runs/LR-000001');
    const wait = page.getByLabel('منتظر مُهر تو');
    await expect(wait).toBeVisible();
    // Outputs are shown properly: markdown text, audio, video, image, JSON as a table.
    await expect(page.getByText('سناریوی ریلز').first()).toBeVisible();
    await expect(page.locator('audio').first()).toBeAttached();
    await expect(page.locator('video').first()).toBeAttached();
    await expect(page.getByRole('table', { name: 'داده‌ی خروجی' }).first()).toBeVisible();
    await wait.getByRole('button', { name: 'تأیید و منتشر کن' }).click();
    await expect(page.getByText('تأیید شد؛ خط ادامه میدهد.')).toBeVisible();
    await expect(page.getByLabel('منتظر مُهر تو')).toHaveCount(0);
    await expect(page.getByLabel('منتشر شده')).toBeVisible();
    await page.getByRole('link', { name: /ریلز آموزشی تریدیار/ }).click();
    await expect(page.getByLabel('حالت خط')).toContainText('4 از 7 اجرای خوب');
  });
});

test('the calendar shows every company by day; the library takes a new prompt', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/campaign-calendar');
    await expect(page.getByRole('link', { name: 'ریلز آموزشی تریدیار' }).first()).toBeVisible();
    await expect(page.getByRole('link', { name: 'پست روزانه‌ی کانال FX' }).first()).toBeVisible();
    await page.getByRole('group', { name: 'شرکت' }).getByRole('button', { name: 'تریدیار' }).click();
    await expect(page.getByRole('link', { name: 'پست روزانه‌ی کانال FX' })).toHaveCount(0);

    await page.goto('/library');
    await expect(page.getByRole('article', { name: /^پوشه‌ی کاور: کاورهای تریدیار/ })).toBeVisible();
    await page.getByRole('button', { name: 'مورد تازه' }).first().click();
    const sheet = page.getByRole('dialog', { name: 'مورد تازه' });
    await sheet.getByRole('radio', { name: 'پرامپت' }).click();
    await sheet.getByLabel('نام مورد').fill('لحن تازه');
    await sheet.getByLabel('متن مورد').fill('ساده و کوتاه بنویس.');
    await sheet.getByRole('button', { name: 'اضافه کن' }).click();
    await expect(page.getByRole('article', { name: /^پرامپت: لحن تازه/ })).toBeVisible();
    // A cover folder takes files (multipart on a real hub; the demo takes their names).
    await page.getByRole('button', { name: 'مورد تازه' }).first().click();
    const s2 = page.getByRole('dialog', { name: 'مورد تازه' });
    await s2.getByRole('radio', { name: 'پوشه‌ی کاور' }).click();
    await s2.getByLabel('نام مورد').fill('کاورهای تازه');
    await s2.getByLabel('انتخاب فایل').setInputFiles({ name: 'a.png', mimeType: 'image/png', buffer: Buffer.from('x') });
    await s2.getByRole('button', { name: 'اضافه کن' }).click();
    await expect(page.getByRole('article', { name: /^پوشه‌ی کاور: کاورهای تازه/ })).toBeVisible();
  });
});
