import { expect, test, type Page } from '@playwright/test';
import { clean } from './support';

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
  // ⟨1.6⟩ the media studio and the legal counsel (§22)
  '/media', '/media?item=MI-0013', '/media?item=MI-0024', '/media/series', '/media/series?ref=SR-0002', '/media/voice', '/legal', '/legal?case=LC-0001',
  '/cartable?ref=D-000085', '/cartable?ref=D-000087', '/cartable?ref=D-000081', '/companies/FX?dept=MEDIA', '/companies/FX?role=RD-0001', '/companies/HQ?dept=LEGAL',
  '/messages?thread=L',
  // ⟨1.7⟩ the archive (§23)
  '/archive', '/archive?party=PT-0002', '/archive?q=%D9%87%D8%AA%D8%B2%D9%86%D8%B1', '/archive?folder=FP-0005&level=internal', '/archive/AR-000110', '/archive/AR-000170',
  '/archive/AR-000180', '/archive/AR-000150', '/archive/holds', '/archive/holds?ref=LH-0002', '/archive/reminders', '/archive/retention', '/archive/settings',
  '/archive/settings?tab=classes&ref=invoice', '/archive/settings?tab=clearance', '/archive/settings?tab=automations&ref=AU-0002', '/archive/settings?tab=levels',
  '/archive/settings?tab=parties', '/archive/settings?tab=sources', '/cartable?ref=D-000092', '/cartable?ref=D-000093',
];


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
    await page.getByRole('button', { name: 'بستن deploy', exact: true }).first().click();
    await page.getByRole('dialog').getByRole('button', { name: 'ببند', exact: true }).click();
    await expect(page.getByRole('button', { name: 'باز کردن deploy' }).nth(1)).toBeVisible();
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

/** Holds the seal (press and hold, here with the keyboard) inside [scope]. */
async function holdSeal(page: Page, scope: ReturnType<Page['locator']>) {
  const seal = scope.getByRole('button', { name: 'برای مُهر، فشار بده و نگه دار' }).first();
  await seal.focus();
  await page.keyboard.down('Enter');
  await page.waitForTimeout(900);
  await page.keyboard.up('Enter');
}

test('seals the counsel\'s email on the exact message', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/legal?case=LC-0001');
    const box = page.getByRole('region', { name: 'ایمیل منتظر مُهر' });
    await expect(box.getByText('appeals@platform-support.example')).toBeVisible();
    await holdSeal(page, box);
    await expect(page.getByText('مُهر خورد؛ دقیقاً همین پیام یک بار فرستاده شد.')).toBeVisible();
    await expect(page.getByText('منتظر جواب').first()).toBeVisible();
  });
});

test('seals an edited publishing series again', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/media/series?ref=SR-0002');
    await holdSeal(page, page.locator('#SR-0002'));
    await expect(page.getByText(/برنامه‌ی SR-0002 مُهر شد/)).toBeVisible();
  });
});

test('publishes a Telegram channel story through its card', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/media?item=MI-0013');
    await expect(page.locator('video').first()).toBeVisible();
    await holdSeal(page, page.getByRole('dialog'));
    await expect(page.getByText('ثبت شد که استوری را خودت گذاشتی؛ بقیه از API رسمی رفت.')).toBeVisible();
  });
});

test('scores a voice blind and sees its name', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/media/voice');
    await page.getByRole('radiogroup', { name: 'نمره‌ی صدای الف' }).getByRole('radio', { name: '8 از ۱۰' }).click();
    await expect(page.getByText(/صدای الف: نمره‌ی 8/)).toBeVisible();
  });
});

test('asks a department for a role written on demand', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/companies/FX?dept=MEDIA');
    await expect(page.getByText('مأموریت: مبدأ و مقصد')).toBeVisible();
    await page.getByLabel('شرح نقش تازه').fill('یه زیرنویس‌نویس عربی برای ریلزها میخوام');
    await page.getByRole('button', { name: 'بفرست به مدیر دپارتمان' }).click();
    await expect(page.getByText(/خواسته رسید \(RD-\d+\)/)).toBeVisible();
  });
});

/** A one-page PDF with a text layer, as a scanner or an accounting export would give it. */
const pdf = (text: string) => Buffer.from(`%PDF-1.4\n1 0 obj << /Type /Page /Resources << /Font << /F1 2 0 R >> >> >> endobj\nBT /F1 11 Tf (${text}) Tj ET\n%%EOF\n`);

test('takes in files, refuses the one with a secret, makes a draft and files it', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/archive');
    await page.getByRole('button', { name: 'سند تازه' }).click();
    const sheet = page.getByRole('dialog');
    await sheet.getByRole('button', { name: 'هلدینگ کوینه‌پرو' }).click();
    await sheet.getByLabel('انتخاب فایل برای بایگانی').setInputFiles([
      { name: 'wallet-notes.txt', mimeType: 'text/plain', buffer: Buffer.from('backup seed phrase: twelve words') },
      { name: 'hetzner-R2026-11.pdf', mimeType: 'application/pdf', buffer: pdf('INVOICE Hetzner Online GmbH invoice number R0026116001 invoice date 2026-11-01 total EUR 38.10') },
    ]);
    // Named, never quoted: the refusal says which file, not what it held.
    await expect(sheet.getByRole('alert').filter({ hasText: 'رد شد: الگوی رمز' })).toBeVisible();
    await expect(sheet.getByText('twelve words')).toHaveCount(0);
    await expect(sheet.getByText('پیشنهاد قاعده‌ها')).toBeVisible();
    await expect(sheet.getByLabel('نوع سند')).toHaveValue('invoice');
    await sheet.getByRole('button', { name: 'پیش‌نویس بساز' }).click();
    await expect(page.getByText(/پیش‌نویس AR-\d+ ساخته شد/)).toBeVisible();
    await expect(page.getByText('پیش‌نویس، منتظر ثبت')).toBeVisible();
    await page.getByLabel('شماره‌ی فاکتور').fill('R0026116001');
    await page.getByLabel('مبلغ', { exact: true }).fill('38.10');
    await page.getByRole('button', { name: 'ثبت کن' }).click();
    await expect(page.getByText(/سند AR-\d+ ثبت شد/)).toBeVisible();
    await expect(page.getByText('مُهر روی manifest نسخه‌ی 1 است', { exact: false })).toBeVisible();
  }, [/POST \/archive\/intake → 422 secret_in_document/]);
});

test('seals a filed record on its manifest with the passkey', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/archive/AR-000121');
    await holdSeal(page, page.locator('#seal'));
    await expect(page.getByText(/سند AR-000121 مُهر شد/)).toBeVisible();
    await expect(page.locator('#seal').getByText(/مُهر خورد،/)).toBeVisible();
  });
});

test('declassifies a sealed record with the passkey; the seal stays and the access log shows it', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/archive/AR-000180');
    await expect(page.getByText('مُهرشده؛ اصلاح یعنی نسخه‌ی تازه')).toBeVisible();
    await page.locator('#seal').getByRole('button', { name: 'پایین به محرمانه' }).click();
    await expect(page.getByRole('dialog').getByText('AR-000180@1:confidential')).toBeVisible();
    await page.getByRole('dialog').getByRole('button', { name: 'با passkey پایین بیاور' }).click();
    await expect(page.getByText('سطح سند «محرمانه» شد.')).toBeVisible();
    await expect(page.locator('#seal').getByText(/مُهر خورد،/)).toBeVisible();
    await expect(page.locator('#access').getByText('سطح را عوض کرد')).toBeVisible();
    await expect(page.getByText('مُهرشده؛ اصلاح یعنی نسخه‌ی تازه')).toBeVisible();
  });
});

test('shows a schema change\'s impact before the passkey, then saves it', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/archive/settings?tab=classes&ref=invoice');
    const sheet = page.getByRole('dialog');
    await sheet.getByRole('button', { name: 'فیلد تازه' }).click();
    await sheet.getByLabel('فیلد 8: عنوان').fill('شناسه‌ی مالیاتی فروشنده');
    await sheet.getByLabel('فیلد 8: کلید').fill('vendor_vat_id');
    await sheet.getByLabel('فیلد 8: نوع').selectOption('id_code');
    await sheet.getByRole('switch', { name: 'فیلد 8: لازم' }).click();
    await expect(sheet.getByRole('button', { name: 'ذخیره با passkey' })).toHaveCount(0);
    await sheet.getByRole('button', { name: 'بررسی اثر' }).click();
    await expect(sheet.getByText(/6 سند از این استفاده میکند/)).toBeVisible();
    await expect(sheet.getByText(/6 سند فیلد اجباری را ندارد/)).toBeVisible();
    await sheet.getByRole('button', { name: 'ذخیره با passkey' }).click();
    await expect(page.getByText(/ذخیره شد؛ نسخه‌ی 2/)).toBeVisible();
  });
});

test('shows a refused schema change next to its input', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/archive/settings?tab=levels&ref=public');
    const sheet = page.getByRole('dialog');
    await sheet.getByLabel('رتبه').fill('10');
    await sheet.getByRole('button', { name: 'بررسی اثر' }).click();
    await expect(sheet.getByText(/رتبه‌ی تکراری/).first()).toBeVisible();
    await expect(sheet.getByRole('button', { name: 'ذخیره با passkey' })).toHaveCount(0);
  }, [/→ 422 schema_invalid/]);
});
