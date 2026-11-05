import { expect, test } from '@playwright/test';
import { clean } from './support';

// ⟨1.15⟩ Contract §33 end to end over the demo holding (lib/api/mock-v33.ts): the revenue board with its forecast band, payments with
// reconcile chips, the day-by-day reconcile and the payment sources (read, add behind the passkey), the advisor's usage reports, the small
// CRM with a follow-up draft, affiliate gaps, a decision's money impact, parallel parts and the workspace in an order report, the journeys,
// and the personas with the message test.

test.use({ reducedMotion: 'reduce' });

const PAGES = ['/companies/TY/money', '/companies/TY/sales', '/companies/TY/journey', '/companies/TY/personas', '/usage', '/journeys', '/revenue/affiliate-gaps', '/revenue', '/orders/F-0096'];
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

test('the revenue board shows the figures, the forecast with its basis, cohorts and ROI', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/companies/TY/money');
    const b = page.getByLabel('تابلوی درآمد');
    await expect(b.getByText('2,050 USDT').first()).toBeVisible();
    await expect(b.getByText('6.2%')).toBeVisible();
    await expect(b.getByRole('img', { name: 'نمودار درآمد ماهانه و پیش‌بینی' })).toBeVisible();
    await expect(b.getByLabel('پایه‌ی پیش‌بینی').getByText('تخمین', { exact: true })).toBeVisible();
    await expect(b.getByLabel('پایه‌ی پیش‌بینی').getByText(/هولت/)).toBeVisible();
    await expect(b.getByRole('table', { name: 'گروه‌های ماهانه و ماندگاری' }).getByRole('row')).toHaveCount(6);
    await expect(b.getByLabel('بازده سرمایه').getByText('هنوز حساب نمیشود')).toBeVisible();
    await expect(b.getByLabel('هزینه‌ی هر خروجی').getByText('هر اجرای خط تولید')).toBeVisible();
  });
});

test('payments filter by reconcile chip; the daily reconcile lists the days', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/companies/TY/money');
    const pay = page.getByLabel('پرداخت‌ها', { exact: true });
    await expect(pay.getByRole('listitem')).toHaveCount(7);
    await expect(pay.getByText('درون‌برنامه').first()).toBeVisible();
    await pay.getByRole('button', { name: /^فقط در دفتر/ }).click();
    await expect(pay.getByRole('listitem')).toHaveCount(1);
    await expect(pay.getByLabel('پرداخت EX-1003').getByText('فقط در دفتر')).toBeVisible();
    await pay.getByRole('button', { name: /^فقط روی زنجیره/ }).click();
    await expect(pay.getByLabel('پرداخت chain-7781')).toBeVisible();
    await pay.getByRole('button', { name: 'همه' }).click();
    await expect(pay.getByRole('listitem')).toHaveCount(7);
    const rec = page.getByRole('table', { name: 'تطبیق روزانه‌ی پرداخت‌ها' });
    await expect(rec.getByRole('row')).toHaveCount(15);
    await expect(page.getByText('یک پرداخت تأییدشده روی زنجیره پیدا نشد.')).toBeVisible();
  });
});

test('payment sources: read, a failing read shows its reason, and a new one is added behind the passkey', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/companies/TY/money');
    const src = page.getByLabel('منبع‌های پرداخت');
    await expect(src.getByLabel('منبع دفتر شرکت')).toBeVisible();
    await expect(src.getByText('شبکه‌ی ترون جواب نداد؛ ساعتی دیگر دوباره امتحان میشود.')).toBeVisible();
    await src.getByRole('button', { name: 'بخوان bsc-usdt' }).click();
    await expect(page.getByText('خوانده شد.')).toBeVisible();
    await src.getByRole('button', { name: 'بخوان tron-usdt' }).click();
    await expect(page.getByText('شبکه‌ی ترون جواب نداد؛ کمی بعد دوباره بخوان.')).toBeVisible();
    await src.getByRole('button', { name: 'منبع تازه' }).click();
    const f = src.getByLabel('مشخصات منبع');
    await f.getByLabel('نام آداپتور').fill('bsc-second');
    await f.getByLabel('آدرس عمومی کیف پول').fill('demo-address-0003');
    await f.getByRole('button', { name: 'ذخیره' }).click();
    await expect(src.getByLabel('منبع زنجیره · BSC (BEP20)')).toHaveCount(2);
  }, [/502/]);
});

test('the advisor writes the usage report; the pack hides under details; a fresh report can be made', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/usage');
    const r = page.getByLabel('گزارش مصرف UR-0003');
    await expect(r.getByLabel('خلاصه‌ی مشاور').getByRole('listitem')).toHaveCount(4);
    await expect(r.getByLabel('یک پیشنهاد برای صرفه‌جویی').getByText(/هفتگی ببرید/)).toBeVisible();
    await expect(r.getByLabel('جزئیات عددها')).toHaveCount(0);
    await r.getByRole('button', { name: 'جزئیات' }).click();
    await expect(r.getByLabel('جزئیات عددها').getByText('گران‌ترین اجراها')).toBeVisible();
    await expect(r.getByLabel('جزئیات عددها').getByText(/جهش|۲ برابر/).first()).toBeVisible();
    await page.getByLabel('گزارش‌های قبلی').getByRole('button', { name: /UR-0001/ }).click();
    await expect(page.getByLabel('گزارش مصرف UR-0001')).toBeVisible();
    await page.getByRole('radio', { name: 'روزانه' }).click();
    await expect(page.getByLabel('گزارش مصرف UR-0004')).toBeVisible();
    await page.getByRole('button', { name: 'گزارش تازه بساز' }).click();
    await expect(page.getByLabel('گزارش مصرف UR-0005')).toBeVisible();
  });
});

test('the home shows yesterday in the advisor\'s three lines', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/');
    const c = page.getByLabel('مصرف دیروز');
    await expect(c.getByRole('listitem')).toHaveCount(3);
    await c.getByRole('link', { name: 'گزارش کامل' }).click();
    await expect(page).toHaveURL(/\/usage$/);
  });
});

test('sales: the pipeline, a lead with events, the follow-up draft that is only shown, a stage change and a new lead', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/companies/TY/sales');
    const pipe = page.getByLabel('مسیر فروش');
    await expect(pipe.getByLabel('مرحله‌ها').getByRole('listitem')).toHaveCount(6);
    await expect(pipe.getByText('50%')).toBeVisible();
    const leads = page.getByLabel('سرنخ‌ها', { exact: true });
    await expect(leads.getByRole('listitem')).toHaveCount(6);
    await leads.getByRole('button', { name: /^مرحله|^تماس گرفته شد/ }).first().click();
    await expect(leads.getByRole('listitem')).toHaveCount(1);
    await leads.getByRole('button', { name: /سارا م\./ }).click();
    const sheet = page.getByRole('dialog');
    await expect(sheet.getByLabel('رویدادها').getByText('از ربات تلگرام آمد.')).toBeVisible();
    await sheet.getByRole('button', { name: 'پیش‌نویس پیگیری' }).click();
    const d = sheet.getByLabel('متن پیش‌نویس');
    await expect(d.getByText(/از تیم تریدیار می‌نویسیم/)).toBeVisible();
    await expect(d.getByText(/فرستاده نمیشود/)).toBeVisible();
    await expect(sheet.getByRole('button', { name: /^ارسال/ })).toHaveCount(0);
    await sheet.getByLabel('مرحله‌ی سرنخ').selectOption('qualified');
    await expect(sheet.getByLabel('رویدادها').getByText('به «qualified» رفت.')).toBeVisible();
    await page.keyboard.press('Escape');
    await leads.getByRole('button', { name: 'همه' }).click();
    await leads.getByRole('button', { name: 'سرنخ تازه' }).click();
    const f = leads.getByLabel('سرنخ تازه', { exact: true });
    await f.getByLabel('نام', { exact: true }).fill('کاوه د.');
    await f.getByLabel('شناسه‌ی تماس (نشانه‌دار)').fill('cu_new77');
    await f.getByRole('button', { name: 'ذخیره' }).click();
    await expect(leads.getByLabel('سرنخ LD-000007')).toBeVisible();
  });
});

test('affiliate gaps list the due against the received, with the drafted message', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/revenue/affiliate-gaps');
    const g = page.getByLabel('شکاف کمیسیون');
    await expect(g.getByRole('listitem')).toHaveCount(3);
    await expect(g.getByLabel(/شکاف exchange-a\/main/).first().getByText('باز', { exact: true })).toBeVisible();
    await expect(g.getByText(/گزارش تسویه را بفرستید/)).toBeVisible();
  });
});

test('the revenue page splits money by source and carries the holding-wide board', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/revenue');
    const s = page.getByLabel('درآمد به تفکیک منبع');
    await expect(s.getByText('کمیسیون رفرال')).toBeVisible();
    await expect(s.getByText('پرداخت مشتریان')).toBeVisible();
    await expect(page.getByLabel('تابلوی درآمد').first()).toBeVisible();
    await page.getByRole('link', { name: 'پیگیری طلب و دریافت کمیسیون' }).click();
    await expect(page).toHaveURL(/affiliate-gaps$/);
  });
});

test('a decision shows its money impact: measured, or an estimate; the cartable sorts by it', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/cartable?ref=D-000035');
    await expect(page.getByLabel(/اثر پولی تخمینی: .*900 USDT/).first()).toBeVisible();
    await expect(page.getByLabel('اثر پولی').getByText(/حدس مدل است/)).toBeVisible();
    await page.getByLabel('ترتیب').selectOption('impact');
    const first = page.locator('button[aria-pressed]').first();
    await expect(first).toContainText('استوری کانال تلگرام تریدیار');
    await expect(first.getByLabel(/اثر پولی اندازه‌گیری‌شده/)).toBeVisible();
    await expect(page.getByLabel('اثر پولی', { exact: true })).toHaveCount(0);
  });
});

test('an order report shows the parts side by side, the merge, and a failed part as failed', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/orders/F-0097');
    const par = page.getByLabel('بخش‌های موازی');
    await expect(par.getByRole('listitem').filter({ has: page.getByRole('heading') })).toHaveCount(3);
    await expect(par.getByLabel('بخش ریلز آموزشی').getByRole('alert')).toContainText('کلید نداشت');
    await expect(par.getByLabel('ادغام').getByText('نوشته شد')).toBeVisible();
    await expect(par.getByLabel('بخش متن مقاله').getByRole('link', { name: 'مقاله‌ی حد ضرر' })).toBeVisible();
  });
});

test('an order done on the company\'s server shows its badge and progress', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/orders/F-0096');
    const w = page.getByLabel('محیط کاری روی سرور');
    await expect(w.getByText('روی سرور شرکت')).toBeVisible();
    await expect(w.getByText('در حال کار')).toBeVisible();
    await expect(w.getByRole('progressbar').or(w.getByLabel('پیشرفت روی سرور'))).toBeVisible();
    await expect(page.getByLabel('بخش بررسی سرعت').getByText('در حال کار')).toBeVisible();
    await expect(page.getByLabel('بخش پیشنهاد محتوا').getByText('در صف')).toBeVisible();
  });
});

test('every company is on one journey timeline, and a company has its own', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/journeys');
    const all = page.getByLabel('سفر همه‌ی شرکت‌ها');
    await expect(all.locator('section')).toHaveCount(3);
    await expect(all.getByLabel('سفر تریدیار').getByLabel('اولین پرداخت: رسیده')).toBeVisible();
    await expect(all.getByLabel('سفر پرو-چارت').getByLabel('اولین بازدیدکننده: مرحله‌ی فعلی')).toBeVisible();
    await all.getByRole('link', { name: 'کوینه‌پرو FX' }).click();
    await expect(page).toHaveURL(/\/companies\/FX\/journey$/);
    const t = page.getByLabel('مرحله‌های سفر');
    await expect(t.getByRole('listitem')).toHaveCount(8);
    await expect(t.getByLabel('اولین سرنخ: مرحله‌ی فعلی')).toBeVisible();
    await expect(page.getByLabel('قدم بعدی').getByText(/ده مشتری/)).toBeVisible();
  });
});

test('personas: edit, keep a suggestion, and test a message', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/companies/TY/personas');
    await expect(page.getByLabel('پرسونا معامله‌گر تازه‌کار')).toBeVisible();
    await page.getByRole('button', { name: 'ویرایش معامله‌گر تازه‌کار' }).click();
    const f = page.getByLabel('مشخصات پرسونا');
    await f.getByLabel('نام پرسونا').fill('معامله‌گر نوآموز');
    await f.getByRole('button', { name: 'ذخیره' }).click();
    await expect(page.getByLabel('پرسونا معامله‌گر نوآموز')).toBeVisible();
    await page.getByRole('button', { name: 'پیشنهاد از دانشنامه' }).click();
    const ideas = page.getByLabel('پیشنهادها از دانشنامه');
    await expect(ideas.getByLabel(/^پرسونا /)).toHaveCount(2);
    await ideas.getByRole('button', { name: 'نگه دار دانشجوی علاقه‌مند به بازار' }).click();
    await expect(page.getByLabel('پرسونا دانشجوی علاقه‌مند به بازار').getByText('پیشنهاد از دانشنامه')).toBeVisible();
    await ideas.getByRole('button', { name: 'نه کارمندی که کنار کار معامله میکند' }).click();
    await expect(page.getByLabel('پیشنهادها از دانشنامه')).toHaveCount(0);
    const t = page.getByLabel('آزمون پیام');
    await t.getByLabel('متن پیام').fill('اشتراک ماهانه حد ضرر را با تخفیف ویژه امتحان کن');
    await t.getByRole('button', { name: 'بسنج' }).click();
    const res = t.getByLabel('نتیجه‌ی آزمون');
    await expect(res.getByRole('listitem')).toHaveCount(3);
    await expect(res.getByLabel('نتیجه برای معامله‌گر نوآموز')).toBeVisible();
  });
});
