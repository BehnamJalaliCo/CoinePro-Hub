import { expect, test, type Page } from '@playwright/test';
import { clean, openDetails } from './support';

// ⟨1.0.1⟩ Contract §47 to §53, the gaps of the reels order, over the demo holding: the ledger of topics under a working group's member
// («دفتر موضوع‌ها»), the company's narrator, the best hour (the standing word's switch and the publish sheet's choice), a standing routine
// from one sentence in a session, a scheduled post taken back, the JPEG line under a picture, and how an output was made. The demo has a
// sealed reels group (Pro-Chart with a full ledger, a narrator and its best hour; CoinePro FX with none of them yet) and the session
// F-0007 with two routines and its outputs' publishes in every state.

const GROUP = '/playbooks/PB-0003';
const REF = /\b[A-Z]{1,3}-\d{3,}\b/;
async function noRefs(page: Page) {
  const text = await page.locator('body').innerText();
  expect(text.match(REF)?.[0] ?? null, `a ref is printed on ${page.url()}`).toBeNull();
}
const fileRow = (page: Page, name: string) => page.getByTestId('publish').locator(`[data-file="${name}"]`);

test('the ledger: counts on the member row; open, more, search, add (refused when said already), a sample with its link, free a line', async ({ page }) => {
  // The line that is said already is refused on purpose (409 with the earlier line and its day), and «خطاخوان» keeps that.
  await clean(page, async () => {
    await page.goto(GROUP);
    await expect(page.locator('[data-ledger="PC"]')).toContainText('۴۲ موضوع، ۴۰ نمونه');
    await expect(page.locator('[data-ledger="FX"]')).toContainText('هنوز چیزی ثبت نشده');
    await page.getByRole('button', { name: 'دفتر موضوع‌های پرو-چارت' }).click();
    const sheet = page.getByRole('dialog', { name: 'دفتر موضوع‌ها' });
    const topics = sheet.getByRole('list', { name: 'موضوع‌های ثبت‌شده' }).getByRole('listitem');
    // Newest first: his own line, with where it came from and its day; a page, then «بیشتر».
    await expect(topics.first()).toContainText('هشدار قیمت در پرو-چارت');
    await expect(topics.first()).toContainText('افزوده‌ی شما');
    await expect(topics.nth(1)).toContainText('ثبت کارمند');
    await expect(sheet.getByText('از بسته‌ی منتشرشده').first()).toBeVisible();
    await expect(topics).toHaveCount(30);
    await sheet.getByRole('button', { name: 'بیشتر' }).click();
    await expect(topics).toHaveCount(42);
    await expect(sheet.getByRole('button', { name: 'بیشتر' })).toHaveCount(0);
    // Search.
    await sheet.getByLabel('جستجو در دفتر').fill('فیبوناچی');
    await expect(topics).toHaveCount(3);
    await sheet.getByLabel('جستجو در دفتر').fill('');
    await expect(topics).toHaveCount(42);
    // Said already: the hub's words under the field, his text kept.
    const field = sheet.getByLabel('موضوعی که قبلاً گفته‌ایم');
    await field.fill('حد ضرر در یک دقیقه');
    await sheet.getByRole('button', { name: 'افزودن' }).click();
    await expect(sheet.getByRole('alert')).toContainText('این پیش‌تر گفته شده: «حد ضرر: در یک دقیقه»');
    await expect(field).toHaveValue('حد ضرر در یک دقیقه');
    // A new one goes in, first.
    await field.fill('پرایس اکشن برای تازه‌کارها');
    await sheet.getByRole('button', { name: 'افزودن' }).click();
    await expect(page.getByText('موضوع در دفتر ثبت شد.')).toBeVisible();
    await expect(topics.first()).toContainText('پرایس اکشن برای تازه‌کارها');
    await expect(field).toHaveValue('');
    // Free it again, asked in place.
    await topics.first().getByRole('button', { name: 'آزاد کن' }).click();
    const ask = topics.first().getByRole('group', { name: 'آزاد کردن این خط' });
    await expect(ask).toContainText('دوباره قابل ساخت میشود');
    await ask.getByRole('button', { name: 'نه' }).click();
    await expect(ask).toHaveCount(0);
    await topics.first().getByRole('button', { name: 'آزاد کن' }).click();
    await topics.first().getByRole('group', { name: 'آزاد کردن این خط' }).getByRole('button', { name: 'آزاد کن' }).click();
    await expect(page.getByText('آزاد شد؛ دوباره میشود ساختش.')).toBeVisible();
    await expect(sheet.getByText('پرایس اکشن برای تازه‌کارها')).toHaveCount(0);
    // The samples: each with its link, which opens outside; a new one needs its link.
    await sheet.getByRole('radio', { name: /نمونه‌ها/ }).click();
    const samples = sheet.getByRole('list', { name: 'نمونه‌های ثبت‌شده' }).getByRole('listitem');
    const link = samples.first().getByRole('link');
    await expect(link).toHaveAttribute('href', /^https:\/\/www\.pinterest\.com\/pin\/\d+\/$/);
    await expect(link).toHaveAttribute('target', '_blank');
    await sheet.getByLabel('نام نمونه').fill('نمونه‌ی تازه');
    await expect(sheet.getByRole('button', { name: 'افزودن' })).toBeDisabled();
    await sheet.getByLabel('لینک نمونه').fill('https://www.pinterest.com/pin/999000111/');
    await sheet.getByRole('button', { name: 'افزودن' }).click();
    await expect(page.getByText('نمونه در دفتر ثبت شد.')).toBeVisible();
    await expect(samples.first()).toContainText('نمونه‌ی تازه');
    await page.keyboard.press('Escape');
    await expect(page.locator('[data-ledger="PC"]')).toContainText('۴۲ موضوع، ۴۱ نمونه');
    await noRefs(page);
  }, [/topic_taken/]);
});

test('the narrator: set for one company, not for another (with the sign-in line); pick a voice and a style, save', async ({ page }) => {
  await clean(page, async () => {
    await page.goto(GROUP);
    const pc = page.locator('[data-narrator="PC"]');
    await expect(pc).toContainText('گوینده‌ی محتوا');
    await expect(pc).toContainText('Charon، آرام و مطمئن');
    await expect(pc.locator('[data-aistudio]')).toHaveCount(0);
    const fx = page.locator('[data-narrator="FX"]');
    await expect(fx).toContainText('تنظیم نشده؛ هر بار مدل انتخاب میکند');
    await expect(fx).toContainText('گوینده‌ی هاب از حسابش بیرون افتاده؛ یک بار ورود شما لازم است.');
    await page.getByRole('button', { name: 'گوینده‌ی محتوای کوینه‌پرو اف‌ایکس' }).click();
    const sheet = page.getByRole('dialog', { name: 'گوینده‌ی محتوا' });
    // Nothing is chosen for him; each voice says who it is.
    await expect(sheet.getByRole('button', { name: 'ثبت' })).toBeDisabled();
    await expect(sheet.getByRole('radio', { name: /Charon/ })).toContainText('مرد، اطلاع‌رسان');
    await sheet.getByRole('radio', { name: /Kore/ }).click();
    await expect(sheet.getByRole('radio', { name: /Kore/ })).toHaveAttribute('aria-checked', 'true');
    await expect(sheet.getByRole('radio', { name: /Kore/ })).toContainText('زن، محکم');
    await sheet.getByLabel('سبک گفتن').fill('آرام و مطمئن، مثل گوینده‌ی خبر');
    await sheet.getByRole('button', { name: 'ثبت' }).click();
    await expect(page.getByText('گوینده ثبت شد')).toBeVisible();
    await expect(sheet).toHaveCount(0);
    await expect(fx).toContainText('Kore، آرام و مطمئن، مثل گوینده‌ی خبر');
    // The same row on the company's own page, beside its mark.
    await page.goto('/companies/PC?tab=brand');
    await expect(page.getByLabel('گوینده‌ی محتوا', { exact: true })).toContainText('Charon، آرام و مطمئن');
  });
});

test('the best hour: a member on it says its hour; the switch says what the hub knows, and what is used until it knows', async ({ page }) => {
  // CoinePro FX has two accounts: the first word without one is refused on purpose (422 naming them) and he picks.
  await clean(page, async () => {
    await page.goto(GROUP);
    const pc = page.locator('[data-standing="PC"]');
    await expect(pc).toContainText('خودکار، بهترین ساعت 19:00');
    await pc.getByRole('button', { name: 'تنظیم' }).click();
    const best = pc.getByTestId('best-hour');
    await expect(best.getByLabel('بهترین ساعت، خودکار')).toBeChecked();
    await expect(best).toContainText('بهترین ساعت این حساب: 19:00');
    await expect(best).toContainText('از روی لایک و کامنت');
    // The fixed hour stays in the form; off, the row is back on it.
    await expect(pc.getByLabel('ساعت انتشار')).toHaveValue('18:30');
    await best.getByLabel('بهترین ساعت، خودکار').uncheck();
    await pc.getByRole('button', { name: 'ذخیره' }).click();
    await expect(pc).toContainText('خودکار، ساعت 18:30');
    await expect(pc).not.toContainText('بهترین ساعت');
    // Too few posts yet: the hub says how many, and what is used until then.
    const fx = page.locator('[data-standing="FX"]');
    await fx.getByLabel('انتشار خودکار FX').click();
    await fx.getByRole('button', { name: '@coineprofx', exact: true }).click();
    await expect(fx).toContainText('@coineprofx');
    await fx.getByRole('button', { name: 'تنظیم' }).click();
    const thin = fx.getByTestId('best-hour');
    await expect(thin).toContainText('هنوز داده‌ی کافی نیست');
    await expect(thin).not.toContainText('تا آن وقت');
    await thin.getByLabel('بهترین ساعت، خودکار').check();
    await expect(thin).toContainText('تا آن وقت: همان لحظه‌ی آماده شدن');
    await fx.getByLabel('ساعت انتشار').fill('18:30');
    await expect(thin).toContainText('تا آن وقت: ساعت ثابت شما');
    await fx.getByRole('button', { name: 'ذخیره' }).click();
    await expect(fx).toContainText('خودکار، بهترین ساعت، تا آن وقت ساعت 18:30');
  }, [/validation_failed/]);
});

test('the publish sheet: «بهترین ساعت» is one of the times, the JPEG line sits under a picture that is not one; the row is then cancellable', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/outputs?ref=O-000061&tab=all');
    // §53 how it was made: the model's label and the effort, in Persian.
    await expect(page.getByTestId('made-with')).toContainText('ساخت');
    await expect(page.getByTestId('made-with')).toContainText('Opus 5.5، بیشترین دقت');
    // §52 a picture on its own: the line under a PNG, none under a JPEG.
    // ⟨1.0.1⟩ A reel's cover goes out with its reel; on its own it is the quieter «جدا منتشر کن» (the look, C3.3).
    await fileRow(page, 'cover-01.png').getByRole('button', { name: 'جدا منتشر کن' }).click();
    let sheet = page.getByRole('dialog', { name: 'تأیید و انتشار' });
    await expect(sheet.getByTestId('jpeg-note')).toHaveText('این تصویر هنگام انتشار خودکار به JPEG تبدیل میشود.');
    await page.keyboard.press('Escape');
    await fileRow(page, 'frame-01.jpg').getByRole('button', { name: 'تأیید و انتشار' }).click();
    sheet = page.getByRole('dialog', { name: 'تأیید و انتشار' });
    await expect(sheet.getByText('به شکل')).toBeVisible();
    await expect(sheet.getByTestId('jpeg-note')).toHaveCount(0);
    await page.keyboard.press('Escape');
    // The reel: its cover (the PNG, chosen already) gets the line; another cover, or none, does not.
    // ⟨1.0.1⟩ The reel is what the page waits on: its «تأیید و انتشار» is the decision bar's, not its row's.
    await expect(fileRow(page, 'reel-01.mp4').getByRole('button')).toHaveCount(0);
    await page.getByTestId('output-detail').getByTestId('decision-bar').getByRole('button', { name: 'تأیید و انتشار' }).click();
    sheet = page.getByRole('dialog', { name: 'تأیید و انتشار' });
    await expect(sheet.getByRole('button', { name: 'cover-01.png' })).toHaveAttribute('aria-pressed', 'true');
    await expect(sheet.getByTestId('jpeg-note')).toHaveCount(1);
    await sheet.getByRole('button', { name: 'frame-01.jpg' }).click();
    await expect(sheet.getByTestId('jpeg-note')).toHaveCount(0);
    await sheet.getByRole('button', { name: 'cover-01.png' }).click();
    await expect(sheet.getByTestId('jpeg-note')).toHaveCount(1);
    // §49 the account's best hour is a time of its own, with what it is counted from.
    const time = sheet.getByTestId('publish-time');
    await time.getByRole('button', { name: 'بهترین ساعت (21:00)' }).click();
    await expect(time).toContainText('از روی لایک و کامنت');
    await sheet.getByTestId('decision-bar').getByRole('button', { name: 'زمان‌بندی' }).click();
    await expect(page.getByText('ریلز زمان‌بندی شد؛ سر ساعت خودش منتشر میشود.')).toBeVisible();
    const row = fileRow(page, 'reel-01.mp4');
    await expect(row).toContainText('زمان‌بندی شد');
    await expect(row).toContainText('ساعت 21:00');
    await expect(row).toContainText('با کاور');
    // §51 and it can be taken back.
    await row.getByRole('button', { name: 'لغو', exact: true }).click();
    await row.getByRole('group', { name: 'لغو انتشار' }).getByRole('button', { name: 'لغو کن' }).click();
    await expect(row).toContainText('لغو شد');
    // ⟨1.0.1⟩ Taken back, the reel is what the page waits on again: its act is back in the decision bar (never twice on the page).
    await expect(row.getByRole('button')).toHaveCount(0);
    await expect(page.getByTestId('output-detail').getByTestId('decision-bar').getByRole('button', { name: 'تأیید و انتشار' })).toBeVisible();
  });
});

test('how an output was made: the effort in Persian where the model is named, the hub\'s own label where it is not', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/outputs?ref=O-000062&tab=all');
    await expect(page.getByTestId('made-with')).toContainText('Opus 5.5، خیلی زیاد');
    await page.goto('/outputs?ref=O-000063&tab=all');
    await expect(page.getByTestId('made-with')).toContainText('ساخته‌شده با');
    await expect(page.getByTestId('made-with')).toContainText('Sonnet 5.5، medium');
  });
});

test('cancel on an output\'s page: asked once in place, the row becomes «لغو شد»; one on its way says so; one still being sent is refused in words', async ({ page }) => {
  // The file still on its way cannot be cancelled yet (409 not_cancellable), on purpose.
  await clean(page, async () => {
    await page.goto('/outputs?ref=O-000062&tab=all');
    const reel = fileRow(page, 'reel-02.mp4');
    await expect(reel).toHaveAttribute('data-publish', 'scheduled');
    await expect(reel).toContainText('ساعت 18:30');
    // Cancelled before: quiet, no link, and the file can be sent again.
    const gone = fileRow(page, 'post-02.jpg');
    await expect(gone).toContainText('لغو شد');
    await expect(gone.getByRole('link')).toHaveCount(0);
    await expect(gone.getByRole('button', { name: 'لغو', exact: true })).toHaveCount(0);
    await expect(gone.getByRole('button', { name: 'دوباره' })).toBeVisible();
    // «نه» leaves it as it was.
    await reel.getByRole('button', { name: 'لغو', exact: true }).click();
    const ask = reel.getByRole('group', { name: 'لغو انتشار' });
    await expect(ask).toContainText('این انتشار لغو شود؟');
    await ask.getByRole('button', { name: 'نه' }).click();
    await expect(ask).toHaveCount(0);
    await expect(reel).toHaveAttribute('data-publish', 'scheduled');
    // «لغو کن»: the answer takes the row's place.
    await reel.getByRole('button', { name: 'لغو', exact: true }).click();
    await reel.getByRole('group', { name: 'لغو انتشار' }).getByRole('button', { name: 'لغو کن' }).click();
    await expect(page.getByText('لغو شد؛ منتشر نمیشود.')).toBeVisible();
    await expect(reel).toHaveAttribute('data-publish', 'cancelled');
    await expect(reel).toContainText('لغو شد');
    await expect(reel.getByRole('button', { name: 'لغو', exact: true })).toHaveCount(0);
    // One whose cancel is on its way keeps its state with the hub's note under it; a second tap answers the same.
    const held = fileRow(page, 'slide-02.webp');
    await expect(held.locator('[data-publish-note]')).toHaveText('در حال لغو');
    await held.getByRole('button', { name: 'لغو', exact: true }).click();
    await held.getByRole('group', { name: 'لغو انتشار' }).getByRole('button', { name: 'لغو کن' }).click();
    await expect(held).toHaveAttribute('data-publish', 'scheduled');
    await expect(held.locator('[data-publish-note]')).toHaveText('در حال لغو');
    // Still being sent: refused, in the hub's words, on the row.
    await page.goto('/outputs?ref=O-000063&tab=all');
    const busy = fileRow(page, 'reel-03.mp4');
    await expect(busy).toHaveAttribute('data-publish', 'publishing');
    await busy.getByRole('button', { name: 'لغو', exact: true }).click();
    await busy.getByRole('group', { name: 'لغو انتشار' }).getByRole('button', { name: 'لغو کن' }).click();
    await expect(busy.locator('[data-cancel-refused]')).toContainText('چند لحظه بعد دوباره لغو کنید');
    await expect(busy).toHaveAttribute('data-publish', 'publishing');
    // One that is out has its link and no «لغو».
    const out = fileRow(page, 'post-03.jpg');
    await expect(out.getByRole('link', { name: 'باز کن' })).toBeVisible();
    await expect(out.getByRole('button', { name: 'لغو', exact: true })).toHaveCount(0);
  }, [/not_cancellable/]);
});

test('a session: its publishes in the details, cancellable there; its standing routines; a routine from one sentence (refused, then made), switched off', async ({ page }) => {
  // A sentence that names no repetition is refused on purpose (422, in words under the field).
  await clean(page, async () => {
    await page.goto('/s/F-0007');
    const sheet = await openDetails(page);
    // §51 the session's own list of publishes.
    const pubs = sheet.getByLabel('انتشارها', { exact: true });
    await expect(pubs.locator('[data-publish="cancelled"]')).toContainText('لغو شد');
    await expect(pubs.locator('[data-publish="published"]').getByRole('link', { name: 'باز کن' })).toBeVisible();
    await expect(pubs.locator('[data-publish-note]')).toHaveText('در حال لغو');
    const reel = pubs.getByRole('listitem').filter({ hasText: 'reel-02.mp4' });
    await expect(reel).toContainText('زمان‌بندی شد');
    await reel.getByRole('button', { name: 'لغو', exact: true }).click();
    await expect(reel.getByRole('group', { name: 'لغو انتشار' })).toContainText('این انتشار لغو شود؟');
    await reel.getByRole('button', { name: 'لغو کن' }).click();
    await expect(reel).toHaveAttribute('data-publish', 'cancelled');
    // §50 the routines of this session: one on with its next turn, one off with the hub's note.
    const card = sheet.getByLabel('روال دائمی', { exact: true });
    const rows = card.getByRole('region', { name: 'روال‌های دائمی' }).getByRole('listitem');
    await expect(rows).toHaveCount(2);
    const on = rows.filter({ hasText: 'هر روز ساعت 09:00' });
    await expect(on).toContainText('رتبه‌های سئوی سایت');
    await expect(on).toContainText('نوبت بعد:');
    await expect(on.getByRole('switch')).toHaveAttribute('aria-checked', 'true');
    const off = rows.filter({ hasText: 'هر شنبه ساعت 10:00' });
    await expect(off.getByRole('switch')).toHaveAttribute('aria-checked', 'false');
    await expect(off).toContainText('سقف پاکت این ماه پر بود');
    // One sentence: without a time of repetition it is no routine; his words stay.
    await card.getByRole('button', { name: 'روال دائمی' }).click();
    const make = page.getByRole('dialog', { name: 'روال دائمی' });
    const field = make.getByLabel('جمله‌ی روال');
    await expect(field).toHaveAttribute('placeholder', 'مثلاً: هر روز ساعت ۹ رتبه‌های سئوی سایت را ببین و خلاصه بده');
    await field.fill('خلاصه‌ی فروش را برایم بفرست');
    await make.getByRole('button', { name: 'بساز' }).click();
    await expect(make.getByRole('alert')).toContainText('هر چند وقت یک بار');
    await expect(field).toHaveValue('خلاصه‌ی فروش را برایم بفرست');
    // With it: made, on at once, the sheet closes and the new row is first.
    await field.fill('هر روز ساعت ۸ خلاصه‌ی فروش را برایم بفرست');
    await make.getByRole('button', { name: 'بساز' }).click();
    await expect(page.getByText('روال دائمی ساخته شد و از همین حالا روشن است.')).toBeVisible();
    await expect(make).toHaveCount(0);
    await expect(rows).toHaveCount(3);
    await expect(rows.first()).toContainText('هر روز ساعت 08:00');
    await expect(rows.first()).toContainText('خلاصه‌ی فروش را برایم بفرست');
    await expect(rows.first().getByRole('switch')).toHaveAttribute('aria-checked', 'true');
    // One tap switches a routine off.
    await on.getByRole('switch').click();
    await expect(page.getByText('روال خاموش شد')).toBeVisible();
    await expect(on.getByRole('switch')).toHaveAttribute('aria-checked', 'false');
    await expect(on).not.toContainText('نوبت بعد:');
    await noRefs(page);
  }, [/validation_failed/]);
});

test('a session with no routine yet offers only the action; a closed one offers nothing', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/s/F-0008');
    let sheet = await openDetails(page);
    const card = sheet.getByLabel('روال دائمی', { exact: true });
    await expect(card.getByRole('button', { name: 'روال دائمی' })).toBeVisible();
    await expect(card.getByRole('region', { name: 'روال‌های دائمی' })).toHaveCount(0);
    await expect(sheet.getByLabel('انتشارها', { exact: true })).toHaveCount(0);
    await page.goto('/s/F-0004');
    sheet = await openDetails(page);
    await expect(sheet.getByLabel('روال دائمی', { exact: true })).toHaveCount(0);
  });
});

test('a hub before these routes: none of the new pieces is shown, the older ones stay, and «خطاخوان» keeps nothing', async ({ page }) => {
  // The demo then serves nothing of §47 to §53: every new route answers 404 and the reports carry no new field.
  await page.addInitScript(() => { try { window.localStorage.setItem('hq.e2e.old47', '1'); } catch { /* private mode */ } });
  await clean(page, async () => {
    await page.goto(GROUP);
    const pc = page.locator('[data-standing="PC"]');
    await expect(pc).toContainText('خودکار');
    await expect(page.locator('[data-ledger]')).toHaveCount(0);
    await expect(page.locator('[data-narrator]')).toHaveCount(0);
    await pc.getByRole('button', { name: 'تنظیم' }).click();
    await expect(pc.getByLabel('ساعت انتشار')).toHaveValue('18:30');
    await expect(pc.getByTestId('best-hour')).toHaveCount(0);
    await page.goto('/companies/PC?tab=brand');
    await expect(page.getByRole('heading', { level: 1 })).toContainText('پرو-چارت');
    await expect(page.getByLabel('گوینده‌ی محتوا', { exact: true })).toHaveCount(0);
    await page.goto('/s/F-0007');
    const sheet = await openDetails(page);
    await expect(sheet.getByRole('button', { name: 'کارگروه از این جلسه بساز' })).toBeVisible();
    await expect(sheet.getByLabel('روال دائمی', { exact: true })).toHaveCount(0);
    await expect(sheet.getByLabel('انتشارها', { exact: true })).toHaveCount(0);
    await page.goto('/outputs?ref=O-000061&tab=all');
    await expect(page.getByTestId('made-with')).toContainText('Sonnet 5.5، medium');
    await expect(page.getByTestId('publish')).toHaveCount(0);
  });
});

test('@phone the member rows, the ledger and the publish rows fit a phone', async ({ page }) => {
  await clean(page, async () => {
    const fits = async () => expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
    await page.goto(GROUP);
    await expect(page.locator('[data-ledger="PC"]')).toContainText('۴۲ موضوع');
    await expect(page.locator('[data-narrator="PC"]')).toContainText('Charon');
    await fits();
    await page.getByRole('button', { name: 'دفتر موضوع‌های پرو-چارت' }).click();
    const sheet = page.getByRole('dialog', { name: 'دفتر موضوع‌ها' });
    await expect(sheet.getByRole('button', { name: 'افزودن' })).toBeVisible();
    await expect(sheet.getByRole('listitem').first()).toBeVisible();
    const box = (await sheet.boundingBox())!;
    expect(box.width).toBeLessThanOrEqual(page.viewportSize()!.width + 1);
    await page.keyboard.press('Escape');
    await page.goto('/outputs?ref=O-000062&tab=all');
    const reel = fileRow(page, 'reel-02.mp4');
    await reel.getByRole('button', { name: 'لغو', exact: true }).click();
    await expect(reel.getByRole('group', { name: 'لغو انتشار' }).getByRole('button', { name: 'لغو کن' })).toBeVisible();
    await fits();
  });
});
