import { expect, test } from '@playwright/test';
import { clean } from './support';

// ⟨1.13⟩ Contract §31 end to end over the demo holding (lib/api/mock-v31.ts): the line's lessons, a company from a kit (preview, seal,
// what is left to connect), the newsletter, SEO and competitors, the campaign calendar with a conflict, ads (resume behind the passkey)
// and an automation from one sentence.

test.use({ reducedMotion: 'reduce' });

const PAGES = ['/company-kit', '/campaign-calendar', '/automations', '/companies/TY?tab=newsletter', '/companies/TY?tab=seo', '/companies/TY?tab=ads'];
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

test('the line page shows what it learned', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/lines/LN-0001');
    const ins = page.getByLabel('درس‌ها');
    await expect(ins.getByText('18:00')).toBeVisible();
    await expect(ins.getByText(/حدود دو برابر بازدید گرفتند/)).toBeVisible();
    await page.goto('/lines/LN-0002');
    await expect(page.getByLabel('مشخصات خط')).toBeVisible();
    await expect(page.getByLabel('درس‌ها')).toHaveCount(0);
  });
});

test('a company is made from a kit: preview, seal, and what is left to connect', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/company-kit');
    await page.getByRole('button', { name: 'الگوی شرکت رسانه‌ای' }).click();
    await page.getByLabel('کد شرکت').fill('NW');
    await page.getByLabel('نام فارسی').fill('نوآ');
    await page.getByLabel('نام انگلیسی').fill('Noa');
    await page.getByRole('button', { name: 'پیش‌نمایش' }).click();
    const prev = page.getByLabel('پیش‌نمایش', { exact: true });
    await expect(prev.getByText('ریلز آموزشی')).toBeVisible();
    await expect(prev.getByText(/کارگروه: تولید و انتشار/)).toBeVisible();
    await expect(prev.getByText(/اینستاگرام، تلگرام/)).toBeVisible();
    await expect(prev).not.toContainText('[object Object]');
    await prev.getByRole('button', { name: 'بساز و مُهر کن' }).click();
    const res = page.getByLabel('شرکت ساخته شد');
    await expect(res.getByText('شرکت «نوآ» ساخته شد')).toBeVisible();
    await expect(res.getByLabel('چه چیزی هنوز باید وصل شود').getByRole('listitem')).toHaveCount(2);
  });
});

test('the newsletter takes a campaign and schedules it', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/companies/TY?tab=newsletter');
    await expect(page.getByLabel('لیست‌ها').getByText('4,120')).toBeVisible();
    await page.getByRole('button', { name: 'کمپین تازه' }).click();
    const f = page.getByLabel('کمپین تازه', { exact: true });
    await f.getByLabel('موضوع ایمیل', { exact: true }).fill('خلاصه‌ی ماه');
    await f.getByLabel('متن ایمیل').fill('سلام، خلاصه‌ی ماه این است.');
    await f.getByRole('button', { name: 'ذخیره پیش‌نویس' }).click();
    const row = page.getByLabel('کمپین خلاصه‌ی ماه');
    await row.getByLabel(/^زمان ارسال/).fill('2026-12-01T09:00');
    await row.getByRole('button', { name: 'زمان‌بندی' }).click();
    await expect(row.getByText('زمان‌بندی شد', { exact: true })).toBeVisible();
  });
});

test('SEO keeps keywords and competitors, with a rank chart', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/companies/TY?tab=seo');
    await expect(page.getByLabel('جایگاه کلیدواژه‌ها').first()).toBeVisible();
    await page.getByLabel('عبارت').fill('ریسک مدیریت');
    await page.getByLabel('سایت', { exact: true }).first().fill('tradeyar.ir');
    await page.getByRole('button', { name: 'اضافه کن' }).click();
    await expect(page.getByLabel('کلیدواژه ریسک مدیریت')).toBeVisible();
    await page.getByRole('switch', { name: 'فعال بودن ریسک مدیریت' }).click();
    await expect(page.getByRole('switch', { name: 'فعال بودن ریسک مدیریت' })).not.toBeChecked();
    await page.getByRole('button', { name: 'حذف ریسک مدیریت' }).click();
    await expect(page.getByLabel('کلیدواژه ریسک مدیریت')).toHaveCount(0);
    const t = page.getByRole('table', { name: 'رقبا و عددهایشان' });
    await expect(t.getByText('مرجع معامله')).toBeVisible();
    await expect(t.getByText('12,240')).toBeVisible();
    await t.getByRole('button', { name: 'ویرایش مرجع معامله' }).click();
    await page.getByLabel('نام رقیب').fill('مرجع معامله‌گران');
    await page.getByRole('button', { name: 'ذخیره' }).click();
    await expect(t.getByText('مرجع معامله‌گران')).toBeVisible();
  });
});

test('the campaign calendar marks conflicts, filters by kind and adds a campaign', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/campaign-calendar');
    await expect(page.getByText('از حد مجاز کمتر است.')).toBeVisible();
    await expect(page.getByText('خبرنامه', { exact: true }).first()).toBeVisible();
    await page.getByRole('group', { name: 'نوع' }).getByRole('button', { name: 'خبرنامه' }).click();
    await expect(page.getByRole('link', { name: 'ریلز آموزشی تریدیار' })).toHaveCount(0);
    await page.getByRole('button', { name: 'کمپین تازه' }).click();
    const f = page.getByLabel('مشخصات کمپین');
    await f.getByLabel('نام کمپین').fill('جشن پایان سال');
    await f.getByRole('radio', { name: 'کوینه‌پرو FX' }).click();
    await f.getByRole('button', { name: 'ذخیره' }).click();
    await expect(page.getByLabel('کمپین جشن پایان سال')).toBeVisible();
    await page.getByRole('button', { name: 'ویرایش جشن پایان سال' }).click();
    await page.getByLabel('نام کمپین').fill('جشن زمستان');
    await page.getByRole('button', { name: 'ذخیره' }).click();
    await expect(page.getByLabel('کمپین جشن زمستان')).toBeVisible();
  });
});

test('a campaign paused by a rule is resumed behind the passkey; rules can be added', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/companies/TY?tab=ads');
    const c = page.getByLabel('کمپین جست‌وجوی سیگنال');
    await expect(c.getByText('متوقف توسط قاعده')).toBeVisible();
    await c.getByRole('button', { name: 'ادامه‌ی جست‌وجوی سیگنال' }).click();
    await expect(c.getByText('فعال', { exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'قاعده‌ی تازه' }).click();
    const f = page.getByLabel('مشخصات قاعده');
    await f.getByRole('radio', { name: 'متا ادز' }).click();
    await f.getByLabel('دامنه (account یا شناسه‌ی کمپین)').fill('M1');
    await f.getByLabel('کمترین ROAS').fill('۱٫۵');
    await f.getByRole('button', { name: 'ذخیره' }).click();
    await expect(page.getByLabel('قاعده M1')).toContainText('1.5');
    await page.getByRole('switch', { name: 'روشن بودن قاعده‌ی M1' }).click();
    await expect(page.getByRole('switch', { name: 'روشن بودن قاعده‌ی M1' })).not.toBeChecked();
  });
});

test('one sentence becomes an automation: preview, seal, then on and off', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/automations');
    await page.getByLabel('جمله‌ی اتوماسیون').fill('هر روز صبح اگر بازدید کم شد به من خبر بده و بودجه را بالا ببر');
    await page.getByRole('button', { name: 'بساز و نشانم بده' }).click();
    const prev = page.getByLabel('پیش‌نمایش اتوماسیون');
    await expect(prev.getByText(/بازدید دیروز را میسنجد/)).toBeVisible();
    await expect(prev.getByLabel('این کارها انجام نمیشود').getByRole('listitem')).toHaveCount(1);
    await prev.getByRole('button', { name: 'ثبت و مُهر' }).click();
    const row = page.getByLabel('اتوماسیون AT-0003');
    await expect(row.getByText('روشن', { exact: true })).toBeVisible();
    await row.getByRole('switch').click();
    await expect(row.getByText('خاموش', { exact: true })).toBeVisible();
    await page.getByLabel('اتوماسیون AT-0001').getByRole('button').first().click();
    const runs = page.getByLabel('اجراها');
    await expect(runs.getByText('انجام شد', { exact: true })).toBeVisible();
    await expect(runs.getByText('بازدید دیروز خوانده نشد.')).toBeVisible();
  });
});

test('a «new company» order shows the kit card; its fix scrolls there and the seal carries the order', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/s/F-0099');
    await expect(page.getByTestId('knot').getByRole('alert')).toContainText('ساخت شرکت منتظر مُهر توست');
    await page.getByTestId('knot').getByRole('button', { name: 'ساخت شرکت' }).click();
    const card = page.getByLabel('شرکت آماده', { exact: true });
    await expect(card.getByLabel('نام فارسی')).toHaveValue('آموزش');
    await card.getByLabel('نام انگلیسی').fill('Amoozesh');
    await card.getByLabel('کد شرکت').fill('TY');
    await card.getByRole('button', { name: 'پیش‌نمایش' }).click();
    await expect(card.getByRole('alert')).toBeVisible();
    await expect(card.getByRole('button', { name: 'بساز و مُهر کن' })).toBeDisabled();
    await card.getByLabel('کد شرکت').fill('AM');
    await card.getByRole('button', { name: 'پیش‌نمایش' }).click();
    await card.getByRole('button', { name: 'بساز و مُهر کن' }).click();
    await expect(card.getByText('شرکت «آموزش» ساخته شد')).toBeVisible();
  });
});
