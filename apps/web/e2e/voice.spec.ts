import { expect, test, type Page } from '@playwright/test';
import { clean } from './support';

// ⟨1.11⟩ Contract §29.5 long voice on the web, with Chromium's fake microphone and a scripted recogniser in place of Web Speech: the text
// grows as the owner speaks and the recogniser is started again at every pause; past «one minute» (shortened here through `hq.e2e.voice`,
// mock mode only) the audio goes to the hub in pieces and the hub's whole text comes back; either way it is editable before «بفرست».

test.use({
  reducedMotion: 'reduce',
  permissions: ['microphone'],
  launchOptions: { args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'] },
});

/** A recogniser that hears one phrase per session and then ends, as Chrome does at a pause. */
async function fakeRecogniser(page: Page, phrases: string[], limits?: { minute: number; chunk: number }) {
  await page.addInitScript(([ps, lim]) => {
    if (lim) window.localStorage.setItem('hq.e2e.voice', JSON.stringify(lim));
    const w = window as unknown as Record<string, unknown>;
    const state = { starts: 0 };
    w.__voice = state;
    class FakeRecognition {
      lang = ''; continuous = false; interimResults = false; maxAlternatives = 1;
      onresult: ((e: unknown) => void) | null = null; onerror: ((e: unknown) => void) | null = null; onend: (() => void) | null = null;
      start() {
        const i = state.starts++;
        if (i >= (ps as string[]).length) return;
        setTimeout(() => {
          this.onresult?.({ results: [{ isFinal: true, length: 1, 0: { transcript: (ps as string[])[i] } }] });
          setTimeout(() => this.onend?.(), 60);
        }, 200);
      }
      stop() { setTimeout(() => this.onend?.(), 30); }
      abort() { this.onend?.(); }
    }
    w.SpeechRecognition = FakeRecognition;
    w.webkitSpeechRecognition = FakeRecognition;
  }, [phrases, limits ?? null] as const);
}

test('the recogniser writes as the owner speaks, starts again at each pause, and the whole text is editable', async ({ page }) => {
  await fakeRecogniser(page, ['برای تریدیار', 'سه ریلز آموزشی بساز', 'و منظم منتشر کن']);
  await clean(page, async () => {
    await page.goto('/');
    await page.getByRole('button', { name: 'فرمان صوتی' }).first().click();
    const sheet = page.getByRole('dialog', { name: 'فرمان صوتی' });
    await sheet.getByRole('button', { name: 'شروع ضبط فرمان' }).click();
    const live = sheet.getByRole('status', { name: 'متن تا این‌جا' });
    await expect(live).toContainText('برای تریدیار سه ریلز آموزشی بساز و منظم منتشر کن');
    expect(await page.evaluate(() => (window as unknown as { __voice: { starts: number } }).__voice.starts)).toBeGreaterThanOrEqual(3);
    await sheet.getByRole('button', { name: 'تمام؛ متن را ببینم' }).click();
    const text = sheet.getByRole('textbox', { name: 'متن کامل آنچه گفتی؛ اگر لازم است اصلاح کن' });
    await expect(text).toHaveValue('برای تریدیار سه ریلز آموزشی بساز و منظم منتشر کن');
    await text.fill('برای تریدیار سه ریلز آموزشی بساز و هر روز منتشر کن');
    await expect(sheet.getByLabel('پیش‌نمایش منشی')).toBeVisible();
  });
});

test('past the minute the audio goes to the hub in pieces and the hub\'s whole text comes back', async ({ page }) => {
  await fakeRecogniser(page, ['برای تریدیار', 'یک برنامه'], { minute: 1.5, chunk: 1 });
  await clean(page, async () => {
    await page.goto('/');
    await page.getByRole('button', { name: 'فرمان صوتی' }).first().click();
    const sheet = page.getByRole('dialog', { name: 'فرمان صوتی' });
    await sheet.getByRole('button', { name: 'شروع ضبط فرمان' }).click();
    await expect(sheet.getByText(/بیش از یک دقیقه شد؛ صدا تکه‌تکه به ستاد میرود/)).toBeVisible({ timeout: 10_000 });
    await page.waitForTimeout(2_500);
    await sheet.getByRole('button', { name: 'تمام؛ متن را ببینم' }).click();
    const text = sheet.getByRole('textbox', { name: 'متن کامل آنچه گفتی؛ اگر لازم است اصلاح کن' });
    await expect(text).toHaveValue(/^برای تریدیار یک برنامه‌ی محتوای یک‌ماهه بنویس، هر روز یک ریلز آموزشی و دو استوری/, { timeout: 15_000 });
    await expect(sheet.getByText('متن از ستاد', { exact: false })).toBeVisible();
  });
});
