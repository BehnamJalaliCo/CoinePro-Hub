import { expect, test, type Page } from '@playwright/test';
import { clean, openDetails } from './support';

// ⟨1.0.3⟩ Contract §57, the session's team, one person at a time, over the demo holding. F-0093 (Pro-Chart's reel about RSI divergence)
// is a content session: its holder, the scriptwriter at work with two lines the owner has not read, the director's and the motion
// designer's seats empty, and the company's narrator. Under the header one row «تیم این جلسه»; a filled seat opens a small sheet of
// its own side talk; an empty one is hired after one question; «گوینده» opens the company's narrator picker; the holder's chip brings
// the composer into reach. §57.6: of the three versions of the session's notes only the newest is in the talk, with «نسخه‌ی ۳».
// A hub without `/team` (every other session of the demo, and `hq.e2e.old57`) shows no row.

const flag = (page: Page, key: string, value: string) => page.addInitScript(([k, v]) => window.localStorage.setItem(k!, v!), [key, value]);
const overflow = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
const row = (page: Page) => page.getByTestId('session-team');
const seat = (page: Page, key: string) => row(page).locator(`[data-seat="${key}"]`);
const WRITER = 'PC-SCRIPT-01';
const WRITER_FA = 'نویسنده‌ی ریلز پرو-چارت';

test('the row under the header: the holder first, the scriptwriter at work with his unread dot, the empty seats dashed, the narrator', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/s/F-0093');
    await expect(row(page)).toBeVisible();
    await expect(row(page)).toContainText('تیم این جلسه');
    const seats = row(page).locator('[data-seat]');
    await expect(seats).toHaveCount(4);
    await expect(seats.nth(0)).toHaveAttribute('data-holder', '');
    await expect(seats.nth(0)).toContainText('مسئول جلسه');
    // The scriptwriter works in this order: his ring; he said two things the owner has not read: the dot.
    const writer = seat(page, WRITER);
    await expect(writer).toContainText('نویسنده');
    await expect(writer).toHaveAttribute('data-state', 'working');
    await expect(writer.locator('[data-unread]')).toHaveCount(1);
    await expect(writer).toHaveAccessibleName(/نویسنده.*در کار.*۲ حرف تازه/);
    // The media seats nobody fills yet.
    await expect(seat(page, 'role:video_director')).toHaveText('+ کارگردان');
    await expect(seat(page, 'role:video_director')).toHaveAccessibleName('کارگردان: خالی؛ استخدام');
    await expect(seat(page, 'role:motion_designer')).toHaveText('+ موشن‌گرافی');
    await expect(seat(page, 'role:video_director')).toHaveAttribute('data-state', 'empty');
    // The company's narrator.
    await expect(row(page).locator('[data-narrator-chip]')).toHaveText('گوینده: Charon');
    // The row is right under the header, above the talk.
    const head = (await page.getByTestId('session').locator('header').boundingBox())!;
    const box = (await row(page).boundingBox())!;
    expect(box.y).toBeGreaterThanOrEqual(head.y + head.height - 1);
    expect(box.y - (head.y + head.height)).toBeLessThan(24);
    expect(await overflow(page)).toBeLessThanOrEqual(0);
  });
});

test('a filled seat opens «با …»: his side talk alone, a word goes to him, his answer comes in the sheet, the main talk untouched', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/s/F-0093');
    // From the keyboard: the chip takes the focus and Enter opens it.
    await seat(page, WRITER).focus();
    await page.keyboard.press('Enter');
    const sheet = page.getByRole('dialog', { name: `با ${WRITER_FA}` });
    await expect(sheet).toBeVisible();
    const lines = sheet.locator('[data-side-line]');
    await expect(lines).toHaveCount(3);
    await expect(lines.nth(0)).toHaveAttribute('data-who', 'owner');
    await expect(lines.nth(2)).toContainText('یادداشت‌های سناریو را هم به‌روز کردم');
    // Read: the dot goes at once.
    await expect(seat(page, WRITER).locator('[data-unread]')).toHaveCount(0);
    // A word to him alone.
    const word = 'برای صحنه‌ی آخر یک مثال از نمودار طلا بیاور.';
    await sheet.getByLabel(`پیام به ${WRITER_FA}`).fill(word);
    await sheet.getByLabel(`پیام به ${WRITER_FA}`).press('Enter');
    await expect(lines).toHaveCount(4);
    await expect(lines.nth(3)).toHaveAttribute('data-who', 'owner');
    await expect(lines.nth(3)).toContainText(word);
    await expect(sheet.getByLabel(`پیام به ${WRITER_FA}`)).toHaveValue('');
    await expect(sheet.locator('[data-side-woken]')).toHaveText(`${WRITER_FA} روی حرفت کار میکند؛ جوابش همین‌جا می‌آید.`);
    // He answers a moment later: the sheet reads its talk again every four seconds while it is open.
    await expect(lines).toHaveCount(5, { timeout: 12_000 });
    await expect(lines.nth(4)).toHaveAttribute('data-who', 'seat');
    await expect(lines.nth(4)).toContainText('گرفتم؛ همین را اعمال میکنم');
    // Close: the sheet goes, and nothing of the side talk is in the main thread.
    await sheet.getByRole('button', { name: 'بستن' }).click();
    await expect(page.getByRole('dialog')).toHaveCount(0);
    await expect(page.getByLabel('گفتگو', { exact: true })).not.toContainText(word);
    await expect(seat(page, WRITER)).toHaveAttribute('data-state', 'working');
  });
});

test('the holder\'s chip brings the main composer into reach, what is typed there kept', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/s/F-0093');
    const composer = page.getByLabel('پیام', { exact: true });
    await composer.fill('یک کاور هم بساز');
    await composer.evaluate((el) => (el as HTMLElement).blur());
    await expect(composer).not.toBeFocused();
    await row(page).locator('[data-holder]').click();
    await expect(composer).toBeFocused();
    await expect(composer).toHaveValue('یک کاور هم بساز');
    await expect(page.getByRole('dialog')).toHaveCount(0);
  });
});

test('an empty seat asks once «… استخدام شود؟» and is filled at once', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/s/F-0093');
    await seat(page, 'role:video_director').click();
    const ask = page.getByRole('dialog', { name: 'کارگردان استخدام شود؟' });
    await expect(ask).toBeVisible();
    // «نه» leaves it as it was.
    await ask.getByRole('button', { name: 'نه' }).click();
    await expect(page.getByRole('dialog')).toHaveCount(0);
    await expect(seat(page, 'role:video_director')).toHaveCount(1);
    await seat(page, 'role:video_director').click();
    await page.getByRole('dialog', { name: 'کارگردان استخدام شود؟' }).getByRole('button', { name: 'استخدام کن' }).click();
    await expect(page.getByRole('dialog')).toHaveCount(0);
    await expect(page.getByText('کارگردان استخدام شد و به جلسه آمد.')).toBeVisible();
    // The seat is his now: a filled chip, and his side talk opens (empty yet).
    await expect(seat(page, 'role:video_director')).toHaveCount(0);
    const director = seat(page, 'PC-DIRECTOR-01');
    await expect(director).toHaveAttribute('data-state', 'idle');
    await expect(director).toContainText('کارگردان');
    await director.click();
    const sheet = page.getByRole('dialog', { name: 'با کارگردان ریلز پرو-چارت' });
    await expect(sheet.locator('[data-side-empty]')).toBeVisible();
  });
});

test('a hire the hub refuses says the hub\'s own words, and nothing is made', async ({ page }) => {
  await flag(page, 'hq.e2e.hire', 'refuse');
  await clean(page, async () => {
    await page.goto('/s/F-0093');
    await seat(page, 'role:motion_designer').click();
    const ask = page.getByRole('dialog', { name: 'موشن‌گرافی استخدام شود؟' });
    await ask.getByRole('button', { name: 'استخدام کن' }).click();
    await expect(ask.getByRole('alert')).toContainText('پاکت این ماه برای یک نفر دیگر جا ندارد');
    await expect(ask).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(seat(page, 'role:motion_designer')).toHaveText('+ موشن‌گرافی');
  }, [/envelope_full/]);
});

test('«گوینده» opens the company\'s narrator picker; a new voice shows on the chip', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/s/F-0093');
    await row(page).locator('[data-narrator-chip]').click();
    const picker = page.getByTestId('narrator-sheet');
    await expect(picker).toBeVisible();
    await expect(picker.getByRole('radio', { name: /Charon/ })).toHaveAttribute('aria-checked', 'true');
    await picker.getByRole('radio', { name: /Kore/ }).click();
    await picker.getByRole('button', { name: 'ثبت' }).click();
    await expect(picker).toHaveCount(0);
    await expect(row(page).locator('[data-narrator-chip]')).toHaveText('گوینده: Kore');
  });
});

test('§57.6 of a revision chain the talk shows only the newest, with «نسخه‌ی ۳»; «نتیجه‌ها» keeps them all', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/s/F-0093');
    const talk = page.getByLabel('گفتگو', { exact: true });
    await expect(talk.locator('[data-output="O-000583"]')).toBeVisible();
    await expect(talk.locator('[data-output="O-000584"]')).toBeVisible();
    await expect(talk.locator('[data-output="O-000582"]')).toHaveCount(0);
    await expect(talk.locator('[data-output="O-000581"]')).toHaveCount(0);
    const version = talk.locator('[data-output="O-000583"]').getByTestId('output-version');
    await expect(version).toHaveText('نسخه‌ی ۳');
    await expect(version).toHaveAttribute('data-version', '3');
    // An output that revises nothing says no version.
    await expect(talk.locator('[data-output="O-000584"]').getByTestId('output-version')).toHaveCount(0);
    await expect(talk.locator('[data-output="O-000583"]')).toContainText('rsi-divergence-notes-v3.pdf');
    const results = (await openDetails(page)).getByLabel('خروجی‌ها', { exact: true });
    await expect(results.getByRole('link')).toHaveCount(4);
  });
});

test('a hub without `/team`: no row, nothing said', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/s/F-0007');
    await expect(page.getByTestId('session')).toBeVisible();
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    await expect(row(page)).toHaveCount(0);
  });
});

test('a hub before §57: the content session shows no row either', async ({ page }) => {
  await flag(page, 'hq.e2e.old57', '1');
  await clean(page, async () => {
    await page.goto('/s/F-0093');
    await expect(page.getByTestId('session').locator('header')).toBeVisible();
    await expect(page.getByLabel('گفتگو', { exact: true }).locator('[data-output="O-000583"]')).toBeVisible();
    await expect(row(page)).toHaveCount(0);
  });
});

test('@phone the row fits a phone (it scrolls within itself), and the side talk is a small sheet with its composer in reach', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await clean(page, async () => {
    await page.goto('/s/F-0093');
    await expect(row(page)).toBeVisible();
    expect(await overflow(page)).toBeLessThanOrEqual(0);
    await seat(page, WRITER).click();
    const sheet = page.getByRole('dialog', { name: `با ${WRITER_FA}` });
    await expect(sheet.locator('[data-side-line]')).toHaveCount(3);
    const box = (await sheet.boundingBox())!;
    const vh = page.viewportSize()!.height;
    // Not a full-height sheet: about half the screen, with its composer inside the window.
    expect(box.height).toBeLessThan(vh * 0.8);
    const input = (await sheet.getByLabel(`پیام به ${WRITER_FA}`).boundingBox())!;
    expect(input.y + input.height).toBeLessThanOrEqual(vh);
    expect(await overflow(page)).toBeLessThanOrEqual(0);
  });
});
