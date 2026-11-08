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

// The session page is quiet: system lines fold, outputs are one compact card, blockers are pinned above the composer (never in the talk).
// The dense demo session (F-0009): nine system steps in three places between real turns, two outputs, two blockers, a long answer.
test('the dense session: system lines fold into rows that open, outputs are one card, blockers are pinned above the composer', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/s/F-0009');
    await expect(page.getByRole('heading', { level: 1 })).toContainText('کمپین');
    const talk = page.getByTestId('talk-scroll');
    // 1. Runs of system lines between two real turns fold; a lone one stays a line.
    const groups = talk.locator('[data-sys-group]');
    await expect(groups).toHaveCount(2);
    await expect(groups.nth(0)).toHaveAttribute('data-count', '5');
    await expect(groups.nth(1)).toHaveAttribute('data-count', '3');
    await expect(groups.nth(0)).toContainText('رویداد');
    await expect(groups.nth(0)).toContainText(/\d{2}:\d{2}.\d{2}:\d{2}/);
    await expect(groups.nth(0).locator('[data-step]')).toHaveCount(0);
    await groups.nth(0).getByRole('button').click();
    const lines = groups.nth(0).locator('[data-step]');
    await expect(lines).toHaveCount(5);
    // Wrapped in full (no ellipsis), the time at the row's end, and no ref anywhere.
    const long = lines.filter({ hasText: 'کلمه‌های کلیدی' });
    await expect(long).toBeVisible();
    expect(await long.locator('span').first().evaluate((el) => getComputedStyle(el).textOverflow)).not.toBe('ellipsis');
    const box = await long.boundingBox();
    const time = await long.locator('.fig').last().boundingBox();
    expect(box && time && time.x - box.x < box.width / 3).toBeTruthy(); // RTL: the end of the row is its left side
    await groups.nth(0).getByRole('button').first().click();
    await expect(lines).toHaveCount(0);
    expect(await talk.locator('[data-step]').count()).toBeGreaterThanOrEqual(1); // the lone line
    expect((await page.locator('body').innerText()).match(/\b[A-Z]{1,3}-\d{3,}\b/)?.[0] ?? null).toBeNull();

    // 2. Two outputs arrive as one compact card with their titles and «باز کن».
    const outs = talk.locator('[data-outputs]');
    await expect(outs).toHaveCount(1);
    await expect(outs).toHaveAttribute('data-outputs', '2');
    await expect(outs).toContainText('خروجی تحویل شد');
    await expect(outs.locator('[data-output]')).toHaveCount(2);
    await expect(outs).toContainText('ریلز ۱: معرفی ابزار خط روند');
    await expect(outs.getByRole('link', { name: 'باز کن' })).toHaveCount(2);

    // 3. The blockers are not in the talk: one banner above the composer, the first with its fix; the rest fold.
    await expect(talk).not.toContainText('سری انتشار مُهر نشده');
    const banner = page.getByTestId('blockers');
    await expect(banner).toHaveAttribute('data-count', '2');
    await expect(banner.locator('[data-blocker]')).toHaveCount(1);
    await expect(banner.getByRole('button', { name: 'مُهر سری انتشار' })).toBeVisible();
    await banner.getByRole('button', { name: /گیر دیگر/ }).click();
    await expect(banner.locator('[data-blocker]')).toHaveCount(2);
    const b = await banner.boundingBox();
    const composer = await page.getByLabel('نوشتن', { exact: true }).boundingBox();
    const tb = await talk.boundingBox();
    expect(b && composer && tb && b.y >= tb.y + tb.height - 1 && b.y < composer.y).toBeTruthy();
  });
});
