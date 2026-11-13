import { expect, test, type Page } from '@playwright/test';
import { clean, openDetails } from './support';

// ⟨1.0.3⟩ Contract §58 over the demo holding: room to write, a session that leaves its working group, a lighter desk.
// - §58.1 F-0093 asks a long question (`hq.e2e.ask=long`): three lines with «بیشتر», opened in place within 40% of the screen, folded
//   to its first line while the composer has the focus or his words; «خروجی آخر» opens the newest output (the third version of the
//   notes, a PDF) on the full screen over the session, and closing it brings him back to the same draft and cursor; the composer grows
//   to five lines and a session's draft is kept across leaving the screen.
// - §58.2 closing F-0007 (a session with a colleague in it) leaves its working group in the library: the toast, the end leaf and the
//   archive's card say «کارگروه این جلسه در کتابخانه ماند».
// - §58.3 a sealed working group's member says its day in one line.
// - §58.4 a published card of the desk says what was filed and what the sweep freed.
// - §58.5 the home keeps one line for the desk; the desk has a tab per channel with its counts.

const flag = (page: Page, key: string, value: string) => page.addInitScript(([k, v]) => window.localStorage.setItem(k!, v!), [key, value]);
const card = (page: Page) => page.getByTestId('waiting-card');
const composer = (page: Page) => page.getByLabel('پیام', { exact: true });
const KEPT = 'کارگروه این جلسه در کتابخانه ماند';

test('§58.1 a long question: three lines and «بیشتر», opened in place within 40% of the screen, folded to one line while he writes', async ({ page }) => {
  await flag(page, 'hq.e2e.ask', 'long');
  await clean(page, async () => {
    await page.goto('/s/F-0093');
    const q = card(page).locator('[data-question]');
    await expect(q).toContainText('نسخه‌ی سوم یادداشت‌های سناریو آماده است');
    // Three lines at most (each 28px), the rest behind «بیشتر».
    expect((await q.boundingBox())!.height).toBeLessThanOrEqual(3 * 28 + 2);
    const more = card(page).getByRole('button', { name: 'بیشتر' });
    await expect(more).toHaveAttribute('aria-expanded', 'false');
    await more.click();
    await expect(card(page)).toHaveAttribute('data-expanded', '');
    const vh = page.viewportSize()!.height;
    const open = (await q.boundingBox())!.height;
    expect(open).toBeGreaterThan(3 * 28 + 2);
    expect(open).toBeLessThanOrEqual(vh * 0.4 + 1);
    await expect(q).toContainText('آیا لحن گوینده همین‌طور آرام بماند؟');
    await card(page).getByRole('button', { name: 'کمتر' }).click();
    await expect(card(page)).not.toHaveAttribute('data-expanded', '');
    // The composer takes the focus: the card is its first line alone, and nothing of it covers what he writes.
    await composer(page).click();
    await expect(card(page)).toHaveAttribute('data-folded', '');
    expect((await card(page).boundingBox())!.height).toBeLessThan(64);
    await expect(card(page).getByRole('group', { name: 'جواب‌های آماده' })).toHaveCount(0);
    await composer(page).fill('صحنه‌ی طلا بماند');
    await composer(page).evaluate((el) => (el as HTMLElement).blur());
    // His words are there: it stays folded until he taps it, and folds again when he goes back to writing.
    await expect(card(page)).toHaveAttribute('data-folded', '');
    await card(page).locator('[data-question-line]').click();
    await expect(card(page)).not.toHaveAttribute('data-folded', '');
    await expect(card(page).getByRole('group', { name: 'جواب‌های آماده' })).toBeVisible();
    await composer(page).click();
    await expect(card(page)).toHaveAttribute('data-folded', '');
    // Nothing he wrote is under the card: the composer's box is below the card's.
    const c = (await card(page).boundingBox())!;
    const w = (await composer(page).boundingBox())!;
    expect(c.y + c.height).toBeLessThanOrEqual(w.y + 1);
    // Empty and away from the composer, the question is whole again.
    await composer(page).fill('');
    await composer(page).evaluate((el) => (el as HTMLElement).blur());
    await expect(card(page)).not.toHaveAttribute('data-folded', '');
  });
});

test('§58.1 «خروجی آخر» opens the newest output on the full screen; closing it returns to the same draft and cursor', async ({ page }) => {
  await flag(page, 'hq.e2e.ask', 'long');
  await clean(page, async () => {
    await page.goto('/s/F-0093');
    await composer(page).fill('صحنه‌ی طلا بماند');
    await composer(page).evaluate((el) => (el as HTMLTextAreaElement).setSelectionRange(5, 5));
    // folded while he writes: a tap shows it whole, with the chip of the newest output (the newest of the notes' three versions)
    await card(page).locator('[data-question-line]').click();
    const chip = card(page).locator('[data-latest-output]');
    await expect(chip).toHaveText('خروجی آخر: نسخه‌ی تازه‌ی یادداشت‌های سناریو');
    await chip.click();
    const viewer = page.getByTestId('latest-output');
    await expect(viewer).toBeVisible();
    await expect(viewer).toContainText('نسخه‌ی تازه‌ی یادداشت‌های سناریو');
    await expect(viewer).toContainText('rsi-divergence-notes-v3.pdf');
    // A PDF is not framed (framing is forbidden): its face, its name, and «باز کن» in the browser's own reader.
    await expect(viewer.locator('[data-pdf]').getByRole('link', { name: 'باز کن' })).toHaveAttribute('target', '_blank');
    const box = (await viewer.boundingBox())!;
    expect(box.width).toBeGreaterThanOrEqual(page.viewportSize()!.width - 1);
    await viewer.getByRole('button', { name: 'بستن' }).click();
    await expect(viewer).toHaveCount(0);
    await expect(composer(page)).toBeFocused();
    await expect(composer(page)).toHaveValue('صحنه‌ی طلا بماند');
    expect(await composer(page).evaluate((el) => (el as HTMLTextAreaElement).selectionStart)).toBe(5);
  });
});

test('§58.1 the composer grows to five lines then scrolls; a session\'s draft is kept across leaving the screen', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/s/F-0093');
    await composer(page).fill(Array.from({ length: 30 }, (_, i) => `خط ${i + 1}`).join('\n'));
    expect((await composer(page).boundingBox())!.height).toBeLessThanOrEqual(5 * 24 + 22 + 2);
    expect(await composer(page).evaluate((el) => el.scrollHeight > el.clientHeight)).toBe(true);
    await composer(page).fill('پیش‌نویس این جلسه');
    await page.goto('/s/F-0007');
    await expect(composer(page)).toHaveValue('');
    await page.goto('/s/F-0093');
    await expect(composer(page)).toHaveValue('پیش‌نویس این جلسه');
    // Sent, it is no draft any more.
    await composer(page).fill('');
    await page.goto('/s/F-0007');
    await page.goto('/s/F-0093');
    await expect(composer(page)).toHaveValue('');
  });
});

test('§58.2 a closed session with a colleague leaves its working group in the library: the toast, the end leaf and the archive say it', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/s/F-0007');
    await (await openDetails(page)).getByRole('button', { name: 'تأیید و بستن' }).click();
    await page.getByRole('dialog', { name: 'تأیید و بستن جلسه' }).getByRole('button', { name: 'تأیید و ببند' }).click();
    await expect(page.getByText(`جلسه بسته و بایگانی شد؛ ${KEPT}.`)).toBeVisible();
    const leaf = page.getByTestId('end-leaf');
    await expect(leaf.getByTestId('playbook-kept')).toHaveText(KEPT);
    await expect(leaf.getByTestId('playbook-kept')).toHaveAttribute('href', '/playbooks');
    // (the demo keeps its records in the page: the way to the archive is a click, not a reload)
    await page.locator('a[href="/s"]:visible').first().click();
    await expect(page).toHaveURL(/\/s$/);
    await page.getByRole('button', { name: /^بایگانی/ }).click();
    const row = page.locator('a[href="/s/F-0007"]');
    await expect(row.locator('[data-playbook-kept]')).toHaveText(KEPT);
    // A closed session that left nothing (a report of the advisor's) says nothing of it.
    await expect(page.locator('a[href="/s/F-0004"]').locator('[data-playbook-kept]')).toHaveCount(0);
  });
});

test('§58.3 a sealed working group says each member\'s day in one line, and his standing word changes it', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/playbooks/PB-0003');
    const pc = page.locator('[data-member="PC"]');
    const line = pc.locator('[data-day-flow]');
    await expect(line).toHaveText('هر روز 07:00: ساخت ← انتشار خودکار ← اینستاگرام');
    await expect(line.locator('bdi')).toHaveText('07:00');
    // A member that stands still has no day.
    await expect(page.locator('[data-member="FX"] [data-day-flow]')).toHaveCount(0);
    await pc.getByRole('switch', { name: 'انتشار خودکار PC' }).click();
    await expect(line).toHaveText('هر روز 07:00: ساخت ← تأیید تو ← اینستاگرام');
    await expect(line).toHaveAttribute('data-mode', 'ask');
  });
});

test('§58.4 a published card says it was filed and what the sweep freed; a failed one says nothing of it', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/outputs/desk');
    const out = page.locator('[data-desk="done"][data-output="O-000065"]');
    await expect(out.locator('[data-desk-swept]')).toContainText('بایگانی شد');
    await expect(out.locator('[data-desk-swept]')).toContainText('38 MB آزاد شد');
    await expect(out.locator('[data-desk-swept] [data-sep]')).toHaveCount(1);
    await expect(page.locator('[data-desk="done"][data-output="O-000066"] [data-desk-swept]')).toHaveCount(0);
  });
});

test('§58.5 the home keeps one line for the desk; the desk is its own page with a tab per channel and its counts', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/');
    const line = page.getByTestId('desk-line');
    await expect(line).toContainText('انتشار:');
    await expect(line).toContainText('۶ آماده');
    await expect(line).toContainText('۲ در صف');
    // Nothing of the desk itself in the middle of the home.
    await expect(page.locator('[data-desk]')).toHaveCount(0);
    await line.click();
    await expect(page).toHaveURL(/\/outputs\/desk$/);
    const tabs = page.getByRole('tablist', { name: 'کانال‌های انتشار' });
    await expect(tabs.getByRole('tab')).toHaveCount(1);
    const ig = tabs.getByRole('tab', { name: /اینستاگرام/ });
    await expect(ig).toHaveAttribute('aria-selected', 'true');
    await expect(ig.locator('[data-channel-counts]')).toContainText('۶ آماده');
    await expect(ig.locator('[data-channel-counts]')).toContainText('۲ در صف');
    await expect(ig.locator('[data-channel-counts]')).toContainText('منتشرشده');
    await expect(page.getByRole('tabpanel', { name: 'اینستاگرام' }).locator('[data-desk="ready"]').first()).toBeVisible();
    // The «خروجی‌ها» tab stays beside it.
    await expect(page.getByTestId('outputs-tabs').getByRole('link', { name: 'خروجی‌ها' })).toBeVisible();
  });
});

test('@phone the long question opened scrolls inside itself within 40% of the screen; the composer stays in the window', async ({ page }) => {
  await flag(page, 'hq.e2e.ask', 'long');
  await clean(page, async () => {
    await page.goto('/s/F-0093');
    await card(page).getByRole('button', { name: 'بیشتر' }).click();
    const q = card(page).locator('[data-question]');
    const vh = page.viewportSize()!.height;
    expect((await q.boundingBox())!.height).toBeLessThanOrEqual(vh * 0.4 + 1);
    await composer(page).click();
    await expect(card(page)).toHaveAttribute('data-folded', '');
    const w = (await composer(page).boundingBox())!;
    expect(w.y + w.height).toBeLessThanOrEqual(vh);
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
  });
});
