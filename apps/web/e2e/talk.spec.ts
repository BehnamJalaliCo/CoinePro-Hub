import { expect, test, type Page } from '@playwright/test';
import { clean } from './support';

// ⟨1.14⟩ Contract §32 end to end over the demo holding (lib/api/mock-v32.ts): the faces and a streamed answer, cards that run only when the
// owner taps, a key-shaped string that never becomes a message (it opens the key sheet, is saved behind the passkey, shows the light and
// asks for the month cap), the live meter, the voices, hold-to-talk and hands-free with a scripted recogniser and Chromium's fake
// microphone, and barge-in.

test.use({
  reducedMotion: 'reduce',
  permissions: ['microphone'],
  launchOptions: { args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'] },
});

const KEY = `AIza${'x'.repeat(35)}`;
const composer = (p: Page) => p.getByRole('textbox', { name: 'پیام' });
const send = async (p: Page, t: string) => { await composer(p).fill(t); await p.getByRole('button', { name: 'بفرست', exact: true }).click(); };

/** A recogniser the test drives: `__heard(text)` is what the phone "hears" now (results grow, as in a continuous session). */
async function scriptedRecogniser(page: Page, phrases: string[] = []) {
  await page.addInitScript((ps) => {
    const w = window as unknown as Record<string, unknown>;
    const st = { cur: null as null | { onresult: ((e: unknown) => void) | null }, results: [] as Array<{ isFinal: boolean; length: number; 0: { transcript: string } }>, starts: 0 };
    w.__rec = st;
    w.__heard = (t: string) => { st.results.push({ isFinal: true, length: 1, 0: { transcript: t } }); st.cur?.onresult?.({ results: st.results }); };
    class Fake {
      lang = ''; continuous = false; interimResults = false; maxAlternatives = 1;
      onresult: ((e: unknown) => void) | null = null; onerror: ((e: unknown) => void) | null = null; onend: (() => void) | null = null;
      start() {
        const i = st.starts++;
        if (!(w.__handsfree as boolean)) {
          // Hold-to-talk: one phrase per session, then the session ends, as the other voice checks do.
          const p = (ps as string[])[i];
          if (p) setTimeout(() => { this.onresult?.({ results: [{ isFinal: true, length: 1, 0: { transcript: p } }] }); setTimeout(() => this.onend?.(), 60); }, 150);
          return;
        }
        st.cur = this; st.results = [];
      }
      stop() { setTimeout(() => this.onend?.(), 30); }
      abort() { if (st.cur === this) st.cur = null; }
    }
    w.SpeechRecognition = Fake;
    w.webkitSpeechRecognition = Fake;
  }, phrases);
}

for (const path of ['/talk']) {
  test(`renders ${path} and fits a phone @phone`, async ({ page }) => {
    await clean(page, async () => {
      await page.goto(path);
      await expect(page.locator('h1').first()).toHaveText('گفتگو');
      await expect(page.getByRole('radio', { name: 'منشی هلدینگ' })).toBeVisible();
      await page.waitForLoadState('networkidle');
      const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(over).toBeLessThanOrEqual(0);
    });
  });
}

test('the top bar has its own talk button, apart from the golden order button', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/');
    await expect(page.getByRole('button', { name: 'فرمان صوتی' }).first()).toBeVisible();
    await page.getByRole('link', { name: 'گفتگو با ستاد' }).click();
    await expect(page).toHaveURL(/\/talk$/);
  });
});

test('a typed question streams an answer, and an imperative becomes a card that runs only when tapped', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/talk');
    await expect(page.getByRole('radio', { name: 'منشی هلدینگ' })).toBeChecked();
    await send(page, 'امروز وضع چطور است؟');
    const chat = page.getByLabel('گفتگو', { exact: true });
    await expect(chat.getByText('تصمیم منتظری ندارم')).toBeVisible();
    await expect(chat.getByLabel(/^کارت/)).toHaveCount(0);
    await send(page, 'سه ریلز آموزشی برای تریدیار بساز');
    const card = chat.getByLabel(/^کارت فرمان/);
    await expect(card).toBeVisible();
    await expect(card).toHaveAttribute('data-state', 'offered');
    await card.getByRole('button', { name: 'ویرایش' }).click();
    await card.getByLabel('متن فرمان').fill('چهار ریلز آموزشی برای تریدیار بساز');
    await card.getByRole('button', { name: 'اجرا کن' }).click();
    await expect(card.getByLabel('ساخته شد')).toContainText('جلسه‌اش را باز کن');
    await expect(card).toHaveAttribute('data-state', 'done');
  });
});

test('«نه» puts a card aside; a deep question offers an «ask» card', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/talk');
    await page.getByRole('radio', { name: 'مشاور کل' }).click();
    await send(page, 'فروش ماه گذشته‌ی تریدیار را تحلیل کن');
    const card = page.getByLabel(/^کارت پرسش عمیق/);
    await expect(card).toBeVisible();
    await card.getByRole('button', { name: 'نه' }).click();
    await expect(card).toHaveAttribute('data-state', 'dismissed');
  });
});

test('a pasted key never becomes a message: it opens the sheet, is saved, shows the light, and the first key asks for the cap', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/talk');
    const lights = page.getByRole('group', { name: 'چراغ موتورهای صدا' });
    await expect(lights.locator('[data-state="missing"]')).toHaveCount(2);
    await expect(lights.locator('[data-state="ok"]')).toHaveCount(1); // the local engine is always there
    await composer(page).fill(KEY);
    await expect(page.locator('textarea[aria-label="پیام"]')).toHaveValue(''); // behind the sheet
    const dlg = page.getByRole('dialog', { name: 'کلید صدا' });
    const input = dlg.getByLabel('کلید', { exact: true });
    await expect(input).toHaveAttribute('type', 'password');
    await expect(input).toHaveAttribute('autocomplete', 'off');
    await expect(input).toHaveAttribute('spellcheck', 'false');
    await expect(page.getByLabel('گفتگو', { exact: true }).getByText(KEY)).toHaveCount(0);
    // the first key asks for the cap before it is saved
    await expect(dlg.getByRole('button', { name: 'ذخیره و بسنج' })).toBeDisabled();
    await dlg.getByLabel('سقف ماهانه به دلار').fill('20');
    await dlg.getByRole('button', { name: 'ذخیره و بسنج' }).click();
    await expect(dlg.getByText('کلید درست است؛ صدا فعال شد')).toBeVisible();
    await expect(input).toHaveCount(0); // the key is gone from the page
    await dlg.getByRole('button', { name: 'بستن', exact: true }).first().click();
    await expect(lights.locator('[data-state="ok"]')).toHaveCount(3);
    // the cap is on the meter, and the owner can edit it
    await page.getByRole('button', { name: 'شمارنده‌ی هزینه‌ی صدا' }).click();
    const panel = page.getByLabel('جزئیات هزینه');
    await expect(panel.getByLabel('ویرایش سقف ماهانه')).toHaveValue('20');
    await panel.getByLabel('ویرایش سقف ماهانه').fill('30');
    await panel.getByRole('button', { name: 'ثبت سقف' }).click();
    await expect(panel.getByLabel('ویرایش سقف ماهانه')).toHaveValue('30');
  });
});

test('a key the engine refuses shows a red light with the reason', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/talk');
    await page.getByRole('button', { name: 'کلید صدا' }).click();
    const dlg = page.getByRole('dialog', { name: 'کلید صدا' });
    await dlg.getByLabel('کلید', { exact: true }).fill(`AIzaBAD${'y'.repeat(32)}`);
    await dlg.getByLabel('سقف ماهانه به دلار').fill('10');
    await dlg.getByRole('button', { name: 'ذخیره و بسنج' }).click();
    await expect(dlg.getByText('کلید کار نکرد')).toBeVisible();
    await expect(dlg.getByText('کلید درست نیست.')).toBeVisible();
  });
});

test('the meter chip moves after a turn, and the panel carries the honest line', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/talk');
    const chip = page.getByTestId('meter-today');
    await expect(chip).toHaveText('$0.012');
    await send(page, 'سلام');
    await expect(chip).toHaveText('$0.016');
    await page.getByRole('button', { name: 'شمارنده‌ی هزینه‌ی صدا' }).click();
    const panel = page.getByLabel('جزئیات هزینه');
    await expect(panel.getByText('پیش‌بینی ماه')).toBeVisible();
    await expect(panel.getByRole('table', { name: 'به تفکیک موتور' })).toBeVisible();
    await expect(panel.getByRole('table', { name: 'به تفکیک چهره' })).toBeVisible();
    await panel.getByText('جزئیات', { exact: true }).click();
    await expect(panel.getByText(/صورتحساب گوگل \(مالیات و ارز\) ممکن است کمی فرق کند/)).toBeVisible();
    await expect(panel.getByRole('alert')).toContainText('قیمت'); // a price changes within 14 days
  });
});

test('a working session ends in one minutes card with editable tasks; «صورت‌جلسه کن» works in any mode', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/talk');
    await send(page, 'سلام');
    await expect(page.getByLabel('گفتگو', { exact: true }).getByText('تصمیم منتظری ندارم')).toBeVisible();
    await page.getByRole('radio', { name: 'جلسه‌ی کاری' }).click();
    await expect(page.getByRole('radio', { name: 'جلسه‌ی کاری' })).toBeChecked();
    await page.getByRole('button', { name: 'پایان جلسه' }).click();
    const card = page.getByLabel(/^کارت صورت‌جلسه/).first();
    await expect(card).toBeVisible();
    await card.getByRole('button', { name: 'ویرایش' }).click();
    await card.getByLabel('عنوان کار 1').fill('نوشتن خبرنامه‌ی پنجشنبه');
    await card.getByLabel('سررسید کار 2').fill('2026-11-09');
    await card.getByRole('button', { name: 'حذف' }).last().click();
    await card.getByRole('button', { name: 'اجرا کن' }).click();
    await expect(card.getByLabel('ساخته شد')).toContainText('جلسه‌اش را باز کن');
    await expect(card.getByLabel('ساخته شد')).not.toContainText('F-131'); // one task left, one order
    await page.getByRole('radio', { name: 'مشورت' }).click();
    await page.getByRole('button', { name: 'صورت‌جلسه کن' }).click();
    await expect(page.getByLabel(/^کارت صورت‌جلسه/)).toHaveCount(2);
  });
});

test('a manager is brought in from «+» (company, then role) and by words; the secretary announces it', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/talk');
    await page.getByRole('button', { name: 'مدیر یک شرکت را بیاور' }).click();
    const sheet = page.getByRole('dialog', { name: 'مدیر یک شرکت را بیاور' });
    await sheet.getByRole('button', { name: 'تریدیار' }).click();
    await sheet.getByRole('button', { name: 'مدیرعامل' }).click();
    await expect(page.getByLabel('حاضر: مدیرعامل تریدیار')).toBeVisible();
    // by words in another conversation
    await page.getByRole('radio', { name: 'دستیار شخصی' }).click();
    await send(page, 'مدیرعامل تریدیار را بیاور');
    await expect(page.getByLabel('حاضر: مدیرعامل تریدیار')).toBeVisible();
    await expect(page.getByLabel('گفتگو', { exact: true }).getByText('مدیرعامل CEO تریدیار آمد.').or(page.getByLabel('گفتگو', { exact: true }).getByText(/آمد\./))).toBeVisible();
  });
});

test('conversations are listed and searchable; a stored one opens with its turns', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/talk');
    const list = page.getByRole('complementary', { name: 'گفتگوها' });
    await expect(list.getByRole('button', { name: /^برنامه‌ی هفته‌ی تریدیار/ })).toBeVisible();
    await list.getByRole('searchbox', { name: 'جست‌وجو در گفتگوها' }).fill('هزینه');
    await expect(list.getByRole('button', { name: /مرور هزینه‌ی ماه/ })).toBeVisible();
    await expect(list.getByRole('button', { name: /^برنامه‌ی هفته‌ی تریدیار/ })).toHaveCount(0);
    await list.getByRole('searchbox').fill('');
    await list.getByRole('button', { name: /^برنامه‌ی هفته‌ی تریدیار/ }).click();
    await expect(page.getByLabel('گفتگو', { exact: true }).getByText('سه ریلز آموزشی')).toBeVisible();
  });
});

test('each persona has a voice; «بشنو» asks for a sample, and the engine without a key says why', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/talk');
    await page.getByRole('button', { name: 'صدای چهره‌ها' }).click();
    const sheet = page.getByRole('dialog', { name: 'صدای هر چهره' });
    const row = sheet.getByRole('group', { name: 'صدای ناظر کل' });
    await expect(row.getByLabel('صدای ناظر کل')).toHaveValue('Charon');
    await row.getByLabel('صدای ناظر کل').selectOption('Orus');
    await expect(row.getByLabel('صدای ناظر کل')).toHaveValue('Orus');
    await row.getByRole('button', { name: 'بشنو', exact: true }).click();
    await expect(page.getByText('این موتور الان جواب نمیدهد؛ کلید را ببین.')).toBeVisible(); // no key yet: a 502 only for a sample
  }, [/sample|voice\/sample|502/]);
});

test('hold to talk sends what the phone heard, as a turn', async ({ page }) => {
  await scriptedRecogniser(page, ['سلام منشی']);
  await clean(page, async () => {
    await page.goto('/talk');
    const mic = page.getByRole('button', { name: 'نگه‌دار و بگو' });
    const box = (await mic.boundingBox())!;
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.down();
    await expect(page.getByRole('status', { name: 'در حال شنیدن' })).toBeVisible();
    await page.waitForTimeout(700);
    await page.mouse.up();
    const chat = page.getByLabel('گفتگو', { exact: true });
    await expect(chat.locator('[data-by="owner"]').getByText('سلام منشی')).toBeVisible();
    await expect(chat.getByText('تصمیم منتظری ندارم')).toBeVisible();
  });
});

test('hands-free: a turn ends after the silence; speaking over a long answer stops it (barge-in)', async ({ page }) => {
  await page.addInitScript(() => { (window as unknown as Record<string, unknown>).__handsfree = true; });
  await scriptedRecogniser(page);
  await clean(page, async () => {
    await page.goto('/talk');
    await page.getByRole('switch', { name: /بی‌دست/ }).click();
    await page.waitForFunction(() => (window as unknown as { __rec: { cur: unknown } }).__rec.cur !== null);
    await page.evaluate(() => (window as unknown as { __heard: (t: string) => void }).__heard('سلام'));
    const chat = page.getByLabel('گفتگو', { exact: true });
    await expect(chat.locator('[data-by="owner"]').getByText('سلام', { exact: true })).toBeVisible({ timeout: 8_000 });
    await expect(chat.getByText('تصمیم منتظری ندارم')).toBeVisible();
    // a long answer starts; the owner speaks over it
    await page.evaluate(() => (window as unknown as { __heard: (t: string) => void }).__heard('یک جواب طولانی بده'));
    await expect(chat.getByRole('button', { name: 'ساکت شو' })).toBeVisible({ timeout: 8_000 });
    await page.evaluate(() => (window as unknown as { __heard: (t: string) => void }).__heard('صبر کن'));
    await expect(chat.getByText('قطع شد.')).toBeVisible({ timeout: 10_000 });
    await expect(chat.getByText('بند شماره 40 از جواب طولانی')).toHaveCount(0);
  });
});

test('«ساکت شو» ends a long answer at once', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/talk');
    await send(page, 'یک جواب طولانی بده');
    const chat = page.getByLabel('گفتگو', { exact: true });
    await chat.getByRole('button', { name: 'ساکت شو' }).click();
    await expect(chat.getByText('قطع شد.')).toBeVisible({ timeout: 10_000 });
  });
});
