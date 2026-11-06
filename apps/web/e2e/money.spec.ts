import { expect, test } from '@playwright/test';
import { clean } from './support';

// ⟨1.15⟩ Contract §33 end to end over the demo holding (lib/api/mock-v33.ts), whose answers are the hub's own shapes and whose checks are the
// hub's (extra keys refused, `If-Match`, `Idempotency-Key`, the `payment.source` step-up on the SHA-256 of the exact body): the revenue
// board with its forecast band, payments with their reconcile chips, the day-by-day reconcile and the payment sources (read now, add and
// change behind the passkey), the advisor's usage reports, the small CRM (a lead edited: stage, value, lost), affiliate gaps, a decision's
// money impact and the hub's sort by it, a split order and a work on the company's own server (stopped), the journeys, and the personas
// with the message test.

test.use({ reducedMotion: 'reduce' });

const PAGES = ['/companies/TY/money', '/companies/TY/sales', '/companies/TY/journey', '/companies/TY/personas', '/usage', '/journeys', '/revenue/affiliate-gaps', '/revenue', '/s/F-0096', '/s/F-0097'];
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

test('the revenue board shows the figures, the forecast with its basis, cohorts and the return', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/companies/TY/money');
    const b = page.getByLabel('تابلوی درآمد');
    await expect(b.getByText('2,050 USDT').first()).toBeVisible();
    await expect(b.getByText('6.2%')).toBeVisible();
    await expect(b.getByText('18.4 USDT')).toBeVisible();
    await expect(b.getByRole('img', { name: 'نمودار درآمد ماهانه و پیش‌بینی' })).toBeVisible();
    await expect(b.getByLabel('پایه‌ی پیش‌بینی').getByText('تخمین', { exact: true })).toBeVisible();
    await expect(b.getByLabel('پایه‌ی پیش‌بینی').getByText(/هولت/)).toBeVisible();
    await expect(b.getByRole('table', { name: 'گروه‌های ماهانه و ماندگاری' }).getByRole('row')).toHaveCount(6);
    await expect(b.getByLabel('بازده سرمایه').getByText('هنوز حساب نمیشود')).toBeVisible();
    await expect(b.getByLabel('بازده سرمایه').getByText('$576')).toBeVisible();
    await expect(b.getByLabel('هزینه‌ی هر خروجی').getByText('هر اجرای خط تولید')).toBeVisible();
    await expect(b.getByLabel('هزینه‌ی هر خروجی').getByText('$1.85')).toBeVisible();
  });
});

test('payments filter by reconcile chip; a short amount shows what arrived; the daily reconcile lists the days', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/companies/TY/money');
    const pay = page.getByLabel('پرداخت‌ها', { exact: true });
    await expect(pay.getByRole('listitem')).toHaveCount(7);
    await expect(pay.getByText('درون‌برنامه').first()).toBeVisible();
    await expect(pay.getByText(/جمع 635 USDT/)).toBeVisible();
    await expect(pay.getByLabel('پرداخت EX-1005').getByText('رسیده 35 USDT')).toBeVisible();
    await expect(pay.getByLabel('پرداخت chain-7781').getByText('مشتری نامعلوم')).toBeVisible();
    await pay.getByRole('button', { name: /^فقط در دفتر/ }).click();
    await expect(pay.getByRole('listitem')).toHaveCount(1);
    await expect(pay.getByLabel('پرداخت EX-1003').getByText('فقط در دفتر')).toBeVisible();
    await pay.getByRole('button', { name: /^فقط روی شبکه/ }).click();
    await expect(pay.getByLabel('پرداخت chain-7781')).toBeVisible();
    await pay.getByRole('button', { name: 'همه' }).click();
    await expect(pay.getByRole('listitem')).toHaveCount(7);
    const rec = page.getByRole('table', { name: 'تطبیق روزانه‌ی پرداخت‌ها' });
    await expect(rec.getByRole('row')).toHaveCount(15);
    await expect(page.getByText('یک پرداخت تأییدشده روی شبکه پیدا نشد.')).toBeVisible();
  });
});

test('payment sources: read now, a failing read shows its reason, a new address is added and the ledger turned off behind the passkey', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/companies/TY/money');
    const src = page.getByLabel('منبع‌های پرداخت');
    await expect(src.getByLabel('منبع دفتر شرکت')).toBeVisible();
    await expect(src.getByText('شبکه‌ی ترون جواب نداد؛ ساعتی دیگر دوباره امتحان میشود.')).toBeVisible();
    await src.getByRole('button', { name: /^بخوان شبکه‌ی بایننس/ }).click();
    await expect(page.getByText('خوانده شد؛ 2 واریز تازه.')).toBeVisible();
    await src.getByRole('button', { name: 'بخوان دفتر شرکت' }).click();
    await expect(page.getByText('از سرور شرکت خواسته شد؛ نتیجه کمی بعد میرسد.')).toBeVisible();
    await src.getByRole('button', { name: /^بخوان شبکه‌ی ترون/ }).click();
    await expect(page.getByText('شبکه‌ی ترون جواب نداد؛ کمی بعد دوباره بخوان.')).toBeVisible();

    await src.getByRole('button', { name: 'منبع تازه' }).click();
    const f = src.getByLabel('مشخصات منبع');
    await f.getByLabel('نشانی عمومی کیف پول').fill('demo-address-0003');
    await expect(f.getByRole('alert')).toContainText('درست نیست');
    await expect(f.getByRole('button', { name: 'ذخیره' })).toBeDisabled();
    await f.getByLabel('نشانی عمومی کیف پول').fill(`0x${'b0'.repeat(20)}`);
    await f.getByRole('button', { name: 'ذخیره' }).click();
    await expect(page.getByText('منبع ذخیره شد.')).toBeVisible();
    await expect(src.getByRole('listitem').filter({ has: page.getByText('شبکه‌ی بایننس', { exact: true }) })).toHaveCount(2);

    await src.getByRole('button', { name: 'ویرایش دفتر شرکت' }).click();
    await expect(f.getByRole('radio', { name: 'دفتر شرکت' })).toBeDisabled();
    await expect(f.getByLabel('نام سرور شرکت (اختیاری)')).toHaveValue('ty-app');
    await f.getByLabel('روشن باشد').uncheck();
    await f.getByRole('button', { name: 'ذخیره' }).click();
    await expect(src.getByLabel('منبع دفتر شرکت').getByText('خاموش')).toBeVisible();
    await expect(src.getByRole('button', { name: 'بخوان دفتر شرکت' })).toBeDisabled();
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
    const d = r.getByLabel('جزئیات عددها');
    await expect(d.getByText('گران‌ترین اجراها')).toBeVisible();
    await expect(d.getByText('کار فرمان‌ها و شرکت‌ها')).toBeVisible();
    await expect(d.getByText('تریدیار').first()).toBeVisible();
    await expect(d.getByText(/جهش|۲ برابر/).first()).toBeVisible();
    await page.getByLabel('گزارش‌های قبلی').getByRole('button', { name: /UR-0001/ }).click();
    await expect(page.getByLabel('گزارش مصرف UR-0001')).toBeVisible();
    await page.getByRole('radio', { name: 'روزانه' }).click();
    await expect(page.getByLabel('گزارش مصرف UR-0004')).toBeVisible();
    await page.getByLabel('گزارش‌های قبلی').getByRole('button', { name: /UR-0002/ }).click();
    await expect(page.getByLabel('گزارش مصرف UR-0002').getByText(/خود سامانه از روی عددها/)).toBeVisible();
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

test('sales: the pipeline, a lead with events, the draft that is only shown, a lead edited (stage, value, lost) and a new lead', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/companies/TY/sales');
    const pipe = page.getByLabel('مسیر فروش');
    await expect(pipe.getByLabel('مرحله‌ها').getByRole('listitem')).toHaveCount(6);
    await expect(pipe.getByText('50%')).toBeVisible();
    await expect(pipe.getByText('537 USDT')).toBeVisible();
    const leads = page.getByLabel('سرنخ‌ها', { exact: true });
    await expect(leads.getByRole('listitem')).toHaveCount(6);
    await leads.getByRole('button', { name: /^تماس گرفته شد/ }).click();
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
    await expect(sheet.getByLabel('رویدادها').getByText('به «جدی» رفت.')).toBeVisible();
    await sheet.getByRole('button', { name: 'تغییر ارزش' }).click();
    await sheet.getByLabel('ارزش برآوردی (USDT)').fill('120');
    await sheet.getByLabel('ارزش سرنخ').getByRole('button', { name: 'ثبت' }).click();
    await expect(sheet.getByText('120 USDT')).toBeVisible();
    await sheet.getByLabel('مرحله‌ی سرنخ').selectOption('lost');
    await sheet.getByLabel('چرا از دست رفت؟ (اختیاری)').fill('وقت نداشت.');
    await sheet.getByLabel('دلیل از دست رفتن').getByRole('button', { name: 'ثبت' }).click();
    await expect(sheet.getByText(/دلیل از دست رفتن: وقت نداشت\./)).toBeVisible();
    await page.keyboard.press('Escape');
    await leads.getByRole('button', { name: 'همه' }).click();
    await leads.getByRole('button', { name: 'سرنخ تازه' }).click();
    const f = leads.getByLabel('سرنخ تازه', { exact: true });
    await f.getByLabel('نام', { exact: true }).fill('کاوه د.');
    await f.getByLabel('شناسه (اختیاری)').fill('09 12');
    await expect(f.getByRole('alert')).toBeVisible();
    await f.getByLabel('شناسه (اختیاری)').fill('cu_new7777');
    await f.getByRole('button', { name: 'ذخیره' }).click();
    await expect(leads.getByLabel('سرنخ LD-000007')).toBeVisible();
  });
});

test('affiliate gaps list the due against the received, the settlement wait and the follow-up', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/revenue/affiliate-gaps');
    const g = page.getByLabel('شکاف کمیسیون');
    await expect(g.getByRole('listitem')).toHaveCount(3);
    const open = g.getByLabel(/شکاف exchange-a\/main/).first();
    await expect(open.getByText('باز', { exact: true })).toBeVisible();
    await expect(open.getByText(/41\.3 USDT/)).toBeVisible();
    await expect(open.getByRole('link', { name: /پیگیری مدیر مالی/ })).toBeVisible();
    await expect(g.getByText(/گزارش تسویه را بفرستید/)).toBeVisible();
    await expect(g.getByText('در مهلت تسویه')).toBeVisible();
    await expect(g.getByText(/مهلت تسویه تا/)).toBeVisible();
  });
});

test('the revenue page splits money by source per company and carries the holding-wide board', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/revenue');
    const s = page.getByLabel('درآمد به تفکیک منبع');
    await expect(s.getByText('کمیسیون رفرال')).toBeVisible();
    await expect(s.getByText('پرداخت مشتریان')).toBeVisible();
    await expect(s.getByText(/4,300 USDT/).first()).toBeVisible();
    await expect(s.getByLabel('به تفکیک شرکت').getByRole('listitem')).toHaveCount(3);
    await expect(s.getByText(/خرید درون‌برنامه/)).toBeVisible();
    await expect(page.getByLabel('تابلوی درآمد').first()).toBeVisible();
    await page.getByRole('link', { name: 'پیگیری طلب و دریافت کمیسیون' }).click();
    await expect(page).toHaveURL(/affiliate-gaps$/);
  });
});

test('a decision shows its money impact: measured, or an estimate; the hub sorts the cartable by it', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/cartable?ref=D-000035');
    await expect(page.getByLabel(/اثر پولی تخمینی: .*900 USDT/).first()).toBeVisible();
    await expect(page.getByLabel('اثر پولی', { exact: true }).getByText(/حدس است/)).toBeVisible();
    await page.getByLabel('ترتیب').selectOption('impact');
    const rows = page.locator('button[aria-pressed]').filter({ has: page.locator('[aria-label^="اثر پولی"]') });
    await expect(rows.first()).toContainText('استوری کانال تلگرام تریدیار');
    await expect(rows.first().getByLabel(/اثر پولی اندازه‌گیری‌شده/)).toBeVisible();
    await expect(rows.nth(1).getByLabel(/اثر پولی تخمینی: .*900 USDT/)).toBeVisible();
    await expect(rows.nth(2).getByLabel(/اثر پولی تخمینی: .*300 USDT/)).toBeVisible();
    await expect(rows.nth(3).getByLabel(/اثر پولی اندازه‌گیری‌شده/)).toBeVisible();
  });
});

test('an order report shows the parts side by side, the merge, and a failed part as failed', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/s/F-0097');
    const par = page.getByLabel('بخش‌های موازی');
    await expect(par.getByRole('listitem').filter({ has: page.getByRole('heading') })).toHaveCount(3);
    await expect(par.getByLabel('بخش ریلز آموزشی').getByRole('alert')).toContainText('کلید نداشت');
    await expect(par.getByLabel('بخش ریلز آموزشی').getByText('نشد', { exact: true })).toBeVisible();
    await expect(par.getByLabel('جمع‌بندی').getByText('جمع‌بندی نوشته شد', { exact: true })).toBeVisible();
    await expect(par.getByLabel('بخش متن مقاله').getByRole('link', { name: 'مقاله‌ی حد ضرر' })).toBeVisible();
    await expect(par.getByText(/2 از 3 بخش تحویل شده/)).toBeVisible();
  });
});

test('an order done on the company\'s server shows its progress, and the owner stops it', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/s/F-0096');
    const w = page.getByLabel('محیط کاری روی سرور');
    await expect(w.getByText('روی سرور شرکت', { exact: true })).toBeVisible();
    await expect(w.getByText('در حال کار')).toBeVisible();
    await expect(w.getByText(/گزارش سرعت را مینویسد/)).toBeVisible();
    await expect(page.getByLabel('بخش بررسی سرعت').getByRole('progressbar')).toBeVisible();
    await expect(page.getByLabel('بخش پیشنهاد محتوا').getByText('در حال کار')).toBeVisible();
    await expect(page.getByLabel('جمع‌بندی').getByText('بخش‌ها در حال کار')).toBeVisible();
    await w.getByRole('button', { name: 'توقف کار روی سرور' }).click();
    await w.getByRole('button', { name: 'بله، متوقف کن' }).click();
    await expect(page.getByText('کار روی سرور متوقف شد.')).toBeVisible();
    await expect(w.getByText('متوقف شد', { exact: true })).toBeVisible();
    await expect(w.getByRole('button', { name: 'توقف کار روی سرور' })).toHaveCount(0);
  });
});

test('every company is on one journey timeline, and a company has its own', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/journeys');
    const all = page.getByLabel('سفر همه‌ی شرکت‌ها');
    await expect(all.locator('section')).toHaveCount(3);
    await expect(all.getByLabel('سفر تریدیار').getByLabel('اولین پرداخت: مرحله‌ی فعلی')).toBeVisible();
    await expect(all.getByLabel('سفر تریدیار').getByLabel('اولین سرنخ: رسیده')).toBeVisible();
    await expect(all.getByLabel('سفر پرو-چارت').getByLabel('اولین بازدیدکننده: مرحله‌ی فعلی')).toBeVisible();
    await expect(page.getByLabel('خط زمان').getByRole('listitem')).toHaveCount(15);
    await all.getByRole('link', { name: 'کوینه‌پرو FX' }).click();
    await expect(page).toHaveURL(/\/companies\/FX\/journey$/);
    const t = page.getByLabel('مرحله‌های سفر');
    await expect(t.getByRole('listitem')).toHaveCount(8);
    await expect(t.getByLabel('اولین سرنخ: مرحله‌ی فعلی')).toBeVisible();
    await expect(t.getByLabel('اولین پرداخت: پیش رو')).toBeVisible();
    await expect(page.getByLabel('قدم بعدی').getByText(/رسیدن به «اولین پرداخت»/)).toBeVisible();
    await expect(page.getByLabel('قدم بعدی').getByText(/ده مشتری/)).toBeVisible();
  });
});

test('personas: edit, remove, keep a suggestion, and test a message', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/companies/TY/personas');
    await expect(page.getByLabel('مخاطب معامله‌گر تازه‌کار')).toBeVisible();
    await page.getByRole('button', { name: 'ویرایش معامله‌گر تازه‌کار' }).click();
    const f = page.getByLabel('مشخصات مخاطب');
    await f.getByLabel('نام', { exact: true }).fill('معامله‌گر نوآموز');
    await f.getByRole('button', { name: 'ذخیره' }).click();
    await expect(page.getByLabel('مخاطب معامله‌گر نوآموز')).toBeVisible();
    await page.getByRole('button', { name: 'حذف معامله‌گر باتجربه' }).click();
    await expect(page.getByLabel('مخاطب معامله‌گر باتجربه')).toHaveCount(0);
    await page.getByRole('button', { name: 'پیشنهاد از دانشنامه' }).click();
    const ideas = page.getByLabel('پیشنهادها از دانشنامه');
    await expect(ideas.getByLabel(/^مخاطب /)).toHaveCount(2);
    await expect(ideas.getByText(/پرسش‌های پرتکرار پشتیبانی/)).toBeVisible();
    await ideas.getByRole('button', { name: 'نگه دار دانشجوی علاقه‌مند به بازار' }).click();
    await expect(page.getByLabel('مخاطب دانشجوی علاقه‌مند به بازار').getByText('پیشنهاد از دانشنامه')).toBeVisible();
    await ideas.getByRole('button', { name: 'نه کارمندی که کنار کار معامله میکند' }).click();
    await expect(page.getByLabel('پیشنهادها از دانشنامه')).toHaveCount(0);
    const t = page.getByLabel('سنجش پیام');
    await t.getByLabel('متن پیام').fill('اشتراک ماهانه حد ضرر را با تخفیف ویژه امتحان کن');
    await t.getByRole('button', { name: 'بسنج' }).click();
    const res = t.getByLabel('نتیجه‌ی سنجش');
    await expect(res.getByRole('listitem')).toHaveCount(2);
    await expect(res.getByLabel('نتیجه برای معامله‌گر نوآموز')).toBeVisible();
    await expect(t.getByText('میانگین')).toBeVisible();
    await expect(t.getByText('کم‌ترین')).toBeVisible();
  });
});
