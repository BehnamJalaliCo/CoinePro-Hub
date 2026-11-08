import { expect, test } from '@playwright/test';
import { clean } from './support';

// ⟨1.23⟩ Contract §41: the session shows its work live and never stalls. The demo holding's sessions: F-0007 is working (its lines stream with
// the mock stream), F-0005 is stuck (a nudge wakes it), F-0008 waits for the owner (and is «با من»).

test('a working session shows who works, the step, the elapsed time and the lines as they stream in', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/s/F-0007');
    const panel = page.getByTestId('live-work');
    await expect(panel).toHaveAttribute('data-state', 'working');
    await expect(panel).toContainText('دارد کار میکند · قدم');
    await expect(panel.locator('[data-elapsed]')).toHaveText(/^\d+:\d{2}$/);
    // Newest last, at most the last few; the mock stream adds a line every few seconds.
    const lines = panel.locator('[data-line]');
    await expect(lines.first()).toBeVisible();
    const step = async () => Number(((await panel.getByRole('status').innerText()).match(/قدم (\d+)/) ?? [])[1]);
    const s0 = await step();
    await expect.poll(step, { timeout: 20_000 }).toBeGreaterThan(s0);
    await expect(lines).toHaveCount(4);
    // The whole list on a tap, and back.
    await panel.getByRole('button', { name: /همه‌ی قدم‌ها/ }).click();
    await expect.poll(() => lines.count()).toBeGreaterThan(4);
    await panel.getByRole('button', { name: 'کمتر' }).click();
    await expect(lines).toHaveCount(4);
    // It sits just above the composer.
    const above = await panel.boundingBox();
    const composer = await page.getByLabel('نوشتن', { exact: true }).boundingBox();
    expect(above && composer && above.y < composer.y).toBeTruthy();
  });
});

test('a session waiting for the owner says so', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/s/F-0008');
    const panel = page.getByTestId('live-work');
    await expect(panel).toHaveAttribute('data-state', 'waiting');
    await expect(panel).toContainText('منتظر شما: انتخاب یکی از سه عنوان');
  });
});

test('a stuck session says why in plain words and «ادامه بده» wakes it', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/s/F-0005');
    const panel = page.getByTestId('live-work');
    await expect(panel).toHaveAttribute('data-state', 'stuck');
    await expect(panel).toContainText('گیر کرده: بودجه‌ی پست سوم تمام شده');
    await panel.getByRole('button', { name: 'ادامه بده' }).click();
    await expect(page.getByText('گفتم ادامه بدهد.')).toBeVisible();
    await expect(panel).toHaveAttribute('data-state', 'working');
    await expect(panel).toContainText('دارد کار میکند');
    await expect(panel).not.toContainText('گیر کرده');
  });
});

test('a quiet session says when it last worked, with a small «ادامه بده»; a closed one shows no panel', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/s/F-0006');
    const panel = page.getByTestId('live-work');
    await expect(panel).toHaveAttribute('data-state', 'idle');
    await expect(panel).toContainText('آرام · آخرین کار');
    await panel.getByRole('button', { name: 'ادامه بده' }).click();
    await expect(panel).toHaveAttribute('data-state', 'working');
    await page.goto('/s/F-0004');
    await expect(page.getByRole('heading', { level: 1 })).toContainText('گزارش هزینه');
    await expect(page.getByTestId('live-work')).toHaveCount(0);
    await expect(page.getByTestId('pace-chip')).toHaveCount(0);
  });
});

test('the pace is switched in the header, and the plan progress opens the plan in the drawer', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/s/F-0008');
    const chip = page.getByTestId('pace-chip');
    await expect(chip.getByRole('radio', { name: 'با من' })).toHaveAttribute('aria-checked', 'true');
    await chip.getByRole('radio', { name: 'خودکار' }).click();
    await expect(page.getByText('از این به بعد خودش تا آخر میرود.')).toBeVisible();
    await expect(chip.getByRole('radio', { name: 'خودکار' })).toHaveAttribute('aria-checked', 'true');
    // The drawer keeps the same switch, in step with the header.
    const progress = page.getByTestId('plan-progress');
    await expect(progress).toContainText('کار 1 از 3');
    await progress.click();
    const sheet = page.getByRole('dialog', { name: 'جزئیات جلسه' });
    await expect(sheet).toBeVisible();
    await expect(sheet.getByLabel('کارها', { exact: true })).toBeInViewport();
    await expect(sheet.getByRole('radiogroup', { name: 'روش کار' }).getByRole('radio', { name: 'خودکار' })).toHaveAttribute('aria-checked', 'true');
    await page.keyboard.press('Escape');
    await chip.getByRole('radio', { name: 'با من' }).click();
    await expect(chip.getByRole('radio', { name: 'با من' })).toHaveAttribute('aria-checked', 'true');
  });
});
