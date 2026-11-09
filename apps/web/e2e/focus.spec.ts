import { expect, test } from '@playwright/test';
import { clean, openDetails } from './support';

// ⟨1.11⟩ Contract §29 end to end over the demo holding (NEXT_PUBLIC_HQ_MOCK=1, lib/api/mock-v29.ts, fixed dates and figures; animations off):
// the owner's office (⟨1.17⟩: sessions, suggestions with «نه» and a reason, «اجرا کن» opening a session, nothing technical), the order's session and its one-tap
// fixes, the secretary's one line before an order goes, the owner's rule sealed in one tap and retired, the council v2's plan, readiness,
// the working group, the connections with the write-only secret, each employee's state, and «شرکت ← فنی».

test.use({ reducedMotion: 'reduce' });

const PAGES = ['/', '/s/F-0007', '/s/F-0006', '/rules', '/groups', '/groups/content', '/connections', '/companies/TY?tab=readiness',
  '/companies/FX?tab=connections', '/companies/PC?tab=tech', '/companies/FX?tab=people', '/work/W-000199'];

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

test('the office shows the business: suggestions, the sessions, only the critical item; no per-group block', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/');
    await expect(page.getByRole('article', { name: /^پیشنهاد مؤثر: هر روز یک ریلز آموزشی/ })).toBeVisible();
    await expect(page.getByRole('article', { name: /^پیشنهاد خوب: صفحه‌ی «آموزش فارکس/ })).toBeVisible();
    await expect(page.getByLabel('جلسه‌ها', { exact: true }).getByText('برای تریدیار کلیپ بساز و منظم منتشر کن')).toBeVisible();
    await expect(page.getByLabel('بحرانی').getByText('محصول از دسترس خارج شد')).toBeVisible();
    await expect(page.getByLabel(/^شاخص‌های /)).toHaveCount(0);
    // Nothing technical: no watch, no live orbit on the home.
    await expect(page.getByText('استریم زنده‌ی هلدینگ')).toHaveCount(0);
    await expect(page.getByText('ناظر کل', { exact: true }).locator('xpath=ancestor::main')).toHaveCount(0);
  });
});

test('«نه» asks a short reason; «اجرا کن» opens the order\'s session', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/');
    const good = page.getByRole('article', { name: /^پیشنهاد خوب/ });
    await good.getByRole('button', { name: 'نه' }).click();
    await good.getByLabel('دلیل نه').fill('الان سایت FX در حال بازطراحی است');
    await good.getByRole('button', { name: 'ثبت' }).click();
    await expect(page.getByText('دلیلت در حافظه‌ی منشی ماند؛ این پیشنهاد دیگر نمیاید.')).toBeVisible();
    await expect(page.getByRole('article', { name: /^پیشنهاد خوب: استوری نظرسنجی هفتگی/ })).toBeVisible();
    const eff = page.getByRole('article', { name: /^پیشنهاد مؤثر/ });
    await eff.getByRole('button', { name: 'اجرا کن' }).click();
    await expect(page).toHaveURL(/\/s\/F-\d+$/);
    await expect((await openDetails(page)).getByLabel('رسید و برنامه')).toBeVisible();
  });
});

test('an order report: receipt, route, steps, outputs, and each blocker fixed in one tap', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/s/F-0005');
    await expect(page.getByRole('heading', { level: 1 })).toContainText('سه پست معرفی ابزار تحلیل تکنیکال');
    const sheet = await openDetails(page);
    await expect(sheet.getByLabel('رسید و برنامه').getByText(/خروجی:/)).toBeVisible();
    await page.keyboard.press('Escape');
    const blockers = page.getByLabel('گیرها');
    await expect(blockers.getByText('بودجه‌ی این فرمان تمام شد')).toBeVisible();
    await blockers.getByRole('button', { name: '+200 هزار واحد بده' }).click();
    await expect(page.getByText('انجام شد.')).toBeVisible();
    await expect(page.getByLabel('گیرها')).toHaveCount(0);
    await expect((await openDetails(page)).getByLabel('خلاصه‌ی جلسه').getByText('واحد به بودجه اضافه شد؛ کار ادامه دارد.')).toBeVisible();

    // The clip order: the series is sealed behind the passkey, the publisher hired.
    await page.goto('/s/F-0007');
    await page.getByLabel('گیرها').getByRole('button', { name: 'مُهر سری انتشار' }).click();
    // The fix is a system step in the talk; runs of system steps fold into «n رویداد» (the owner's tidy timeline): open them, then read it.
    const talk = page.getByTestId('talk-scroll');
    await expect(async () => {
      for (const fold of await talk.locator('[data-sys-group] > button[aria-expanded="false"]').all()) await fold.click();
      await expect(talk.getByText('سری انتشار مُهر شد؛ انتشار از فردا صبح شروع میشود.')).toBeVisible({ timeout: 1000 });
    }).toPass({ timeout: 15_000 });
    await page.getByLabel('گیرها').getByRole('button', { name: 'استخدام مسئول انتشار' }).click();
    await expect(page.getByLabel('گیرها')).toHaveCount(0);
    await expect((await openDetails(page)).getByLabel('خروجی‌ها').getByRole('link')).toHaveCount(3);
    await page.keyboard.press('Escape');
    // The delivered outputs are also compact cards in the talk.
    await expect(page.getByLabel('نتیجه‌های رسیده').getByRole('link')).toHaveCount(3);
  });
});

test('a delivered order is ready for his OK with «چه شد / حالا چه / از تو چه», and its fix opens the guide', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/s/F-0006');
    const end = (await openDetails(page)).getByLabel('خلاصه‌ی جلسه');
    await expect(end.getByText('چه شد')).toBeVisible();
    await expect(end.getByText('حالا چه')).toBeVisible();
    await expect(end.getByText('از تو چه')).toBeVisible();
    await page.keyboard.press('Escape');
    await page.getByLabel('گیرها').getByRole('button', { name: 'وصل کردن جست‌وجوی گوگل' }).click();
    await expect(page.getByRole('dialog', { name: 'وصل کردن جست‌وجوی گوگل (سئو)' })).toBeVisible();
  });
});

test('the secretary says where an order goes in one line; the owner changes the output and sends it', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/');
    await page.getByRole('button', { name: 'فرمان صوتی' }).first().click();
    const sheet = page.getByRole('dialog', { name: 'فرمان صوتی' });
    await sheet.getByRole('button', { name: 'به‌جایش مینویسم' }).click();
    await sheet.getByRole('textbox').fill('برای تریدیار سه ریلز آموزشی بساز');
    const line = sheet.getByLabel('پیش‌نمایش منشی');
    await expect(line.getByTestId('secretary-line')).toContainText('تریدیار/رسانه');
    await expect(line.getByTestId('secretary-line')).toContainText('3 ریلز');
    await line.getByRole('button', { name: 'تغییر' }).click();
    await line.getByRole('button', { name: 'استوری', exact: true }).click();
    await expect(line.getByText(/خروجی:\s*3\s*استوری/)).toBeVisible();
    // ⟨2026-11-09⟩ «با من یا خودکار؟» is asked first: nothing goes until the owner answers
    await expect(sheet.getByRole('button', { name: 'بفرست' })).toBeDisabled();
    await sheet.getByRole('radiogroup', { name: 'این جلسه چطور جلو برود؟' }).getByRole('radio', { name: 'با من' }).click();
    await sheet.getByRole('button', { name: 'بفرست' }).click();
    // ⟨1.17⟩ The order is a session at once and the owner lands in it.
    await expect(page).toHaveURL(/\/s\/F-\d+$/);
    await expect((await openDetails(page)).getByLabel('رسید و برنامه').getByText(/استوری/)).toBeVisible();
  });
});

test('a new rule from the golden button is sealed in one tap; the rules page edits and retires', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/');
    await page.getByRole('button', { name: 'قانون تازه برای هلدینگ' }).click();
    const sheet = page.getByRole('dialog', { name: 'قانون تازه برای هلدینگ' });
    await sheet.getByRole('button', { name: 'به‌جایش مینویسم' }).click();
    await sheet.getByRole('textbox').fill('از این پس هیچ ریلزی بدون زیرنویس فارسی منتشر نشود');
    await sheet.getByRole('button', { name: 'بفرست به‌عنوان قانون' }).click();
    const proposed = sheet.getByLabel('قانون پیشنهادی');
    await expect(proposed.getByText('هیچ ریلزی بدون زیرنویس فارسی منتشر نشود.')).toBeVisible();
    await proposed.getByRole('button', { name: 'مُهر کن' }).click();
    await expect(proposed.getByText('قانون مُهر شد')).toBeVisible();
    // Within the page (the demo keeps its records in the page).
    await proposed.getByRole('link', { name: 'همه‌ی قانون‌ها' }).click();
    await expect(page.getByRole('article', { name: /هیچ ریلزی بدون زیرنویس فارسی/ })).toBeVisible();
    const rule = page.getByRole('article', { name: /هیچ پستی بیرون از سری مُهرشده/ });
    await expect(rule.getByText(/به کار رفت در\s*112\s*اجرا/)).toBeVisible();
    await rule.getByRole('button', { name: 'بازنشسته کن' }).click();
    await page.getByRole('dialog').getByRole('button', { name: 'بازنشسته کن' }).click();
    await expect(page.getByText('بازنشسته شد؛ دیگر در کار هیچ نقشی نمی‌نشیند.')).toBeVisible();
    await page.getByRole('button', { name: /^بازنشسته/ }).first().click();
    await expect(page.getByRole('article', { name: /هیچ پستی بیرون از سری مُهرشده/ })).toBeVisible();
  });
});

test('the council v2 leads with the captain\'s plan; «اجرا کن» makes an order from it', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/work/W-000199');
    const council = page.getByLabel('شورای مشاوران');
    await expect(council.getByText('دور ۳ از ۳: برنامه‌ی کاپیتان')).toBeVisible();
    await expect(council.getByLabel('نقش‌ها').getByText('پژوهشگر با منبع')).toBeVisible();
    await expect(council.getByLabel('بسته‌ی واقعیت').getByText('18,790')).toBeVisible();
    await council.getByRole('button', { name: 'جزئیات: پاسخ هر عضو' }).click();
    await expect(council.getByRole('link', { name: 'پاسخ کامل' })).toHaveCount(4);
    await council.getByRole('button', { name: 'اجرا کن' }).click();
    const sheet = page.getByRole('dialog', { name: 'فرمان صوتی' });
    await expect(sheet.getByRole('textbox')).toHaveValue(/هر روز یک ریلز آموزشی 30 ثانیه‌ای/);
    await expect(sheet.getByLabel('پیش‌نمایش منشی')).toBeVisible();
  });
});

test('readiness: a missing seat is hired in one tap; a broken channel opens its guide with the write-only secret', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/companies/TY?tab=readiness');
    const card = page.getByRole('region', { name: 'آمادگی' });
    await expect(card.getByText('هنوز آماده نیست')).toBeVisible();
    await card.getByRole('button', { name: 'استخدام مسئول انتشار' }).click();
    await expect(card.getByRole('listitem', { name: 'هر جایگاه کارمند فعال دارد: آماده' })).toBeVisible();

    await page.goto('/companies/FX?tab=readiness');
    await page.getByRole('region', { name: 'آمادگی' }).getByRole('button', { name: 'وصل کردن تلگرام' }).click();
    const sheet = page.getByRole('dialog', { name: 'وصل کردن تلگرام' });
    await expect(sheet.getByText('خطا دارد')).toBeVisible();
    await sheet.getByLabel('رمز ربات').fill('7429104:AAH-demo-token');
    await sheet.getByRole('button', { name: 'ثبت رمز' }).click();
    await expect(page.getByText('رمز در گاوصندوق ستاد ثبت شد؛ هیچ‌وقت دوباره نشان داده نمیشود.')).toBeVisible();
    // Write-only: the field is empty again and the secret is never shown back.
    await expect(sheet.getByLabel('رمز ربات')).toHaveValue('');
    await expect(sheet.getByText('7429104')).toHaveCount(0);
    await expect(sheet.getByText('وصل است')).toBeVisible();
  });
});

test('the working group: members paused and resumed, a routine paused, seats with their state, KPIs and the experiment', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/groups');
    await page.getByRole('link', { name: 'کارگروه تولید محتوا و انتشار' }).click();
    await expect(page.getByRole('heading', { level: 1, name: 'تولید محتوا و انتشار' })).toBeVisible();
    await page.getByRole('button', { name: 'ادامه عضویت پرو-چارت' }).click();
    await expect(page.getByText('کارگروه در پرو-چارت ادامه دارد.')).toBeVisible();
    await page.getByRole('switch', { name: 'توقف روال عددهای دیروز' }).click();
    await expect(page.getByRole('switch', { name: 'ادامه روال عددهای دیروز' })).toHaveAttribute('aria-checked', 'false');
    await expect(page.getByLabel('جایگاه‌ها').getByText('خالی').first()).toBeVisible();
    await expect(page.getByRole('img', { name: 'روند بازدید روزانه' })).toBeVisible();
    await expect(page.getByLabel('آزمایش هفته').getByText('ریلز 15 ثانیه‌ای بیشتر از ریلز 30 ثانیه‌ای تا آخر دیده میشود.')).toBeVisible();
  });
});

test('connections: every kind in order with its state; a stuck employee shows the reason and its fix', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/connections?company=TY');
    await expect(page.getByText('اینستاگرام', { exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: 'وصل کن: یوتیوب' })).toBeVisible();
    await page.goto('/companies/FX?tab=people');
    await expect(page.getByText('گیر کرده').first()).toBeVisible();
    await expect(page.getByText('تلگرام FX وصل نیست؛ ریلز آماده نمیتواند آن‌جا منتشر شود.')).toBeVisible();
  });
});
