import { expect, test } from '@playwright/test';
import { clean, openDetails } from './support';

// ⟨1.23⟩ Contract §41: the session shows its work live and never stalls. The demo holding's sessions: F-0007 is working (its lines stream with
// the mock stream), F-0005 is stuck (a nudge wakes it), F-0008 waits for the owner (and is «با من»).

// ⟨1.0.1⟩ In the look (part C, C2.2) the live work is the «الان» bar above the composer, the newest steps as thin lines at the end of
// the talk, and the whole of it one tap away; a question is the «منتظر تو» card, a knot the «گره» card (e2e/look-session.spec.ts).

test('a working session shows who works, what he does, the elapsed time and the lines as they stream in', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/s/F-0007');
    const bar = page.getByTestId('now-bar');
    await expect(bar).toHaveAttribute('data-state', 'working');
    await expect(bar.locator('[data-now-who]')).toContainText('مدیر رسانه تریدیار');
    await expect(bar.locator('[data-now-sentence]')).not.toBeEmpty();
    await expect(bar.locator('[data-now-timer]')).toHaveText(/^\d+:\d{2}$/);
    // The newest steps, at most three, at the end of the talk; the mock stream adds a line every few seconds.
    const lines = page.getByTestId('live-tail').locator('[data-line]');
    await expect(lines.first()).toBeVisible();
    await expect(lines.last().locator('[data-mark="running"]')).toBeVisible();
    const last = () => lines.last().innerText();
    const first = await last();
    await expect.poll(last, { timeout: 20_000 }).not.toBe(first);
    expect(await lines.count()).toBeLessThanOrEqual(3);
    // The whole list, and who works, one tap away.
    await bar.getByRole('button', { name: 'کار زنده را باز کن' }).click();
    const sheet = page.getByTestId('live-sheet');
    await expect.poll(() => sheet.getByLabel('همه‌ی قدم‌ها').locator('[data-line]').count()).toBeGreaterThan(3);
    await page.keyboard.press('Escape');
    // The bar sits just above the composer.
    const above = await bar.boundingBox();
    const composer = await page.getByLabel('نوشتن', { exact: true }).boundingBox();
    expect(above && composer && above.y < composer.y).toBeTruthy();
  });
});

test('a session waiting for the owner says so, in one place, to «تو»', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/s/F-0008');
    await expect(page.getByTestId('session')).toHaveAttribute('data-mood', 'waiting');
    const card = page.getByTestId('waiting-card');
    await expect(card).toContainText('کدام عنوان بهتر است');
    await expect(card).not.toContainText('شما');
    await expect(page.getByTestId('now-bar')).toHaveCount(0);
  });
});

test('a stuck session says why in plain words and «ادامه بده» wakes it', async ({ page }) => {
  // The demo's stuck session without a fix of the hub's: the knot's own way out is «ادامه بده».
  await page.addInitScript(() => window.localStorage.setItem('hq.e2e.stuck', 'plain'));
  await clean(page, async () => {
    await page.goto('/s/F-0005');
    await expect(page.getByTestId('session')).toHaveAttribute('data-mood', 'stuck');
    const knot = page.getByTestId('knot');
    await expect(knot.getByRole('alert')).toContainText('بودجه‌ی پست سوم تمام شده');
    await knot.getByRole('button', { name: 'ادامه بده' }).click();
    await expect(page.getByText('گفتم ادامه بدهد.')).toBeVisible();
    await expect(page.getByTestId('session')).toHaveAttribute('data-mood', 'working');
    await expect(page.getByTestId('now-bar')).toHaveAttribute('data-state', 'working');
    await expect(page.getByTestId('knot')).toHaveCount(0);
  });
});

// ⟨2026-11-11⟩ The owner's 12-hour stall (F-0095: Pro-Chart's daily reels, «با من», task 3 of 18): nobody worked after «… از ChatGPT
// خواسته شد و در صف است» and the hub said «آرام». The page never leaves such a session silent: after twenty minutes it is «ایستاده», with
// one calm card above the composer that says what was last done and when, and «ادامه بده».
test('a session nobody works on stands still: «ایستاده», one card with the last thing done, and «ادامه بده» wakes it; a closed one shows nothing of it', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/s/F-0095');
    await expect(page.getByTestId('session')).toHaveAttribute('data-mood', 'still');
    await expect(page.getByTestId('session').locator('header').getByTestId('mood-light')).toHaveText('ایستاده');
    await expect(page.getByTestId('now-bar')).toHaveCount(0);
    const card = page.getByTestId('still-card');
    const sentence = card.locator('[data-still-sentence]');
    await expect(sentence).toContainText('الان کسی روی این جلسه کار نمیکند؛ آخرین کار:');
    // the last words of the last thing done (never the run's end), and the day and the clock time it was done
    await expect(sentence).toContainText('از ChatGPT خواسته شد و در صف است');
    await expect(sentence).not.toContainText('گام ۲ در جریان است');
    await expect(sentence).not.toContainText('کارش را تمام کرد');
    await expect(sentence).toContainText(/ \d{2}:\d{2}\)$/);
    // the card sits right above the composer and holds the page's one gold; the send steps back
    const cardBox = (await card.boundingBox())!;
    const composer = (await page.getByLabel('نوشتن', { exact: true }).boundingBox())!;
    expect(cardBox.y + cardBox.height).toBeLessThanOrEqual(composer.y + 1);
    await expect(page.locator('main .bg-gold:visible')).toHaveText(['ادامه بده']);
    // the details keep the quiet line; «ادامه بده» is the card's
    const sheet = await openDetails(page);
    const idle = sheet.getByTestId('idle-nudge');
    await expect(idle).toContainText('آخرین کار');
    await expect(idle.getByRole('button')).toHaveCount(0);
    await page.keyboard.press('Escape');
    await card.getByRole('button', { name: 'ادامه بده' }).click();
    await expect(page.getByText('گفتم ادامه بدهد.')).toBeVisible();
    await expect(page.getByTestId('now-bar')).toHaveAttribute('data-state', 'working');
    await expect(page.getByTestId('still-card')).toHaveCount(0);
    await expect(page.getByTestId('session')).toHaveAttribute('data-mood', 'working');
    // A session ready for his OK waits for him: never «آرام», and no still card (the decision bar is its one act).
    await page.goto('/s/F-0006');
    await expect(page.getByTestId('session')).toHaveAttribute('data-mood', 'waiting');
    await expect(page.getByTestId('still-card')).toHaveCount(0);
    await page.goto('/s/F-0004');
    await expect(page.getByRole('heading', { level: 1 })).toContainText('گزارش هزینه');
    await expect(page.getByTestId('now-bar')).toHaveCount(0);
    await expect(page.getByTestId('still-card')).toHaveCount(0);
    await expect((await openDetails(page)).getByTestId('idle-nudge')).toHaveCount(0);
  });
});

test('the pace is said in the header and switched in the details; the header opens the details with the plan', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/s/F-0008');
    const facts = page.locator('[data-session-facts]');
    await expect(facts).toContainText('با من');
    await expect(facts).toContainText('کار 2 از 3');
    // A tap on the header opens the details: the same switch, the tasks.
    await page.getByRole('heading', { level: 1 }).click();
    const sheet = page.getByRole('dialog', { name: 'جزئیات جلسه' });
    await expect(sheet).toBeVisible();
    const pace = sheet.getByRole('radiogroup', { name: 'روش کار' });
    await expect(pace.getByRole('radio', { name: 'با من' })).toHaveAttribute('aria-checked', 'true');
    await pace.getByRole('radio', { name: 'خودکار' }).click();
    await expect(page.getByText('از این به بعد خودش تا آخر میرود.')).toBeVisible();
    await expect(pace.getByRole('radio', { name: 'خودکار' })).toHaveAttribute('aria-checked', 'true');
    await expect(sheet.getByLabel('کارها', { exact: true })).toHaveCount(1);
    await page.keyboard.press('Escape');
    await expect(facts).toContainText('خودکار');
    await (await openDetails(page)).getByRole('radiogroup', { name: 'روش کار' }).getByRole('radio', { name: 'با من' }).click();
    await page.keyboard.press('Escape');
    await expect(facts).toContainText('با من');
  });
});

// The session page is quiet: system lines fold, each output is its own tiles, the knots are one card above the composer (never in the talk).
// The dense demo session (F-0009): nine system steps in three places between real turns, two outputs, two blockers, a long answer.
test('the dense session: system lines fold into rows that open, each output has its tiles, the knots are one card above the composer', async ({ page }) => {
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

    // 2. The two outputs are in the talk where they arrived, each with its title and «باز کن».
    const outs = talk.locator('section[data-output]');
    await expect(outs).toHaveCount(2);
    await expect(outs.first()).toContainText('خروجی تحویل شد');
    await expect(talk).toContainText('ریلز ۱: معرفی ابزار خط روند');
    await expect(outs.getByRole('link', { name: 'باز کن' })).toHaveCount(2);

    // 3. The knots are not in the talk: one card above the composer, the first with its fix; the rest one tap away.
    await expect(talk).not.toContainText('سری انتشار مُهر نشده');
    const knot = page.getByTestId('knot');
    await expect(knot).toHaveAttribute('data-count', '2');
    await expect(knot.getByRole('alert')).toContainText('سری انتشار مُهر نشده');
    await expect(knot.getByRole('button', { name: 'مُهر سری انتشار' })).toBeVisible();
    await expect(knot.locator('[data-blocker]')).toHaveCount(0);
    await knot.getByRole('button', { name: /گره‌ی دیگر/ }).click();
    await expect(knot.locator('[data-blocker]')).toHaveCount(1);
    const b = await knot.boundingBox();
    const composer = await page.getByLabel('نوشتن', { exact: true }).boundingBox();
    const tb = await talk.boundingBox();
    expect(b && composer && tb && b.y >= tb.y + tb.height - 1 && b.y < composer.y).toBeTruthy();
  });
});
