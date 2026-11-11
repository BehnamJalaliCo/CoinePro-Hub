import { expect, test, type Page } from '@playwright/test';
import { clean, openDetails } from './support';

// ⟨1.0.1⟩ Part C, the session (C2.2), over the demo holding: the header says the session in one light, one line of segments and one
// line of facts; what waits for the owner is one card above the composer, answered with one tap; while someone works the «الان» bar
// says who and what (a build of the workshop with its ring of minutes, held and taken up again from the bar; a direct session says so);
// a knot is one line with its way out; a finished session is closed, or its file published, from the decision bar; a closed one ends
// with its leaf. The demo holds one session in each state (F-0008 waiting, F-0007 working, F-0010 a workshop build, F-0011 direct,
// F-0005 stuck, F-0006 ready, F-0012 ready with a reel, F-0004 closed, ⟨2026-11-11⟩ F-0094 a draft in ChatGPT's queue, F-0095 a session
// nobody works on) and asks for the others through `hq.e2e.ring`, `hq.e2e.workers` and `hq.e2e.mood`.

const flag = (page: Page, key: string, value: string) => page.addInitScript(([k, v]) => window.localStorage.setItem(k!, v!), [key, value]);
const overflow = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
const session = (page: Page) => page.getByTestId('session');
const light = (page: Page) => session(page).locator('header').getByTestId('mood-light');
/** The full golds a screen shows (the owner's one act). */
const golds = (page: Page) => page.locator('main .bg-gold:visible');

test('the header: one light for the session, the tasks as segments, the facts on one line with hairlines', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/s/F-0008');
    await expect(session(page)).toHaveAttribute('data-mood', 'waiting');
    await expect(light(page)).toHaveText('منتظر تو');
    await expect(page.getByRole('heading', { level: 1 })).toContainText('سه عنوان برای خبرنامه‌ی هفته‌ی تریدیار');
    // Three tasks: one done, the one that waits for him, one to come.
    const segments = page.getByTestId('segment-line').locator('[data-seg]');
    await expect(segments).toHaveCount(3);
    await expect(segments.nth(0)).toHaveAttribute('data-seg', 'done');
    await expect(segments.nth(1)).toHaveAttribute('data-seg', 'waiting');
    await expect(segments.nth(2)).toHaveAttribute('data-seg', 'todo');
    await expect(page.getByTestId('segment-line')).toHaveAttribute('aria-label', /کار از 3 انجام شده؛ یک بخش منتظر تو است/);
    // The facts: the hairline between them, never «·» (which reads as a zero beside a Persian digit).
    const facts = page.locator('[data-session-facts]');
    await expect(facts).toContainText('کار 2 از 3');
    await expect(facts).toContainText('با من');
    await expect(facts).toContainText('مدیرعامل تریدیار');
    // (task, pace, holder, and once no one works, when the last step was)
    await expect(facts.locator('[data-sep]')).toHaveCount(3);
    await expect(facts.locator('[data-stall]')).toContainText('آخرین قدم');
    await expect(facts).not.toContainText('·');
  });
});

test('what waits for him is one card above the composer: the question, its ready answers, and one tap answers it', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/s/F-0008');
    const card = page.getByTestId('waiting-card');
    await expect(card).toContainText('مدیرعامل تریدیار میپرسد');
    await expect(card).toContainText('کدام عنوان بهتر است');
    await expect(card.locator('[data-waited]')).toContainText('منتظر');
    const ready = card.getByRole('group', { name: 'جواب‌های آماده' });
    await expect(ready.getByRole('button')).toHaveText(['هفته‌ای که بازار عوض شد', 'سه نکته برای حد ضرر', 'کارمزد را دست‌کم نگیر', 'خودت تصمیم بگیر و ادامه بده']);
    // A question is answered with silver answers; nothing here is a full gold but the composer's own send, once he types.
    await expect(golds(page)).toHaveCount(0);
    // The card sits right above the composer, not somewhere up the talk.
    const cardBox = (await card.boundingBox())!;
    const composer = (await page.getByLabel('نوشتن', { exact: true }).boundingBox())!;
    expect(cardBox.y + cardBox.height).toBeLessThanOrEqual(composer.y + 1);
    expect(composer.y - (cardBox.y + cardBox.height)).toBeLessThan(80);
    await ready.getByRole('button', { name: 'سه نکته برای حد ضرر' }).click();
    // The answer is said back where the question was, and it is in the talk as his own turn.
    await expect(page.getByTestId('answer-sent').getByRole('status')).toHaveText('جوابت رفت: سه نکته برای حد ضرر');
    await expect(page.getByLabel('گفتگو', { exact: true })).toContainText('سه نکته برای حد ضرر');
    // Answered: the question is gone and the session is no longer waiting for him.
    await expect(page.getByTestId('waiting-card')).toHaveCount(0);
    await expect(session(page)).not.toHaveAttribute('data-mood', 'waiting');
  });
});

test('«الان»: who works and what he does, the live work one tap away, several workers counted, a thinking one said so', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/s/F-0007');
    await expect(session(page)).toHaveAttribute('data-mood', 'working');
    await expect(light(page)).toHaveText('کار میکند');
    const bar = page.getByTestId('now-bar');
    await expect(bar).toHaveAttribute('data-state', 'working');
    await expect(bar).toHaveAttribute('data-kind', 'run');
    await expect(bar.locator('[data-now-who]')).toContainText('مدیر رسانه تریدیار');
    await expect(bar.locator('[data-now-sentence]')).not.toBeEmpty();
    // The bar sits above the composer, under the talk.
    const barBox = (await bar.boundingBox())!;
    const composer = (await page.getByLabel('نوشتن', { exact: true }).boundingBox())!;
    expect(barBox.y).toBeLessThan(composer.y);
    // One tap opens the live work: who works, and the last steps as they come.
    await bar.getByRole('button', { name: 'کار زنده را باز کن' }).click();
    const sheet = page.getByTestId('live-sheet');
    await expect(sheet).toBeVisible();
    await expect(sheet.getByRole('list', { name: 'چه کسی کار میکند' }).getByRole('listitem').first()).toContainText('مدیر رسانه تریدیار');
    await page.keyboard.press('Escape');
    await expect(sheet).toHaveCount(0);
  });
});

test('«الان»: more than one worker is counted in the bar', async ({ page }) => {
  await flag(page, 'hq.e2e.workers', '2');
  await clean(page, async () => {
    await page.goto('/s/F-0007');
    const bar = page.getByTestId('now-bar');
    await expect(bar.locator('[data-now-who]')).toContainText('و ۱ نفر دیگر');
    await expect(bar.locator('[data-workers]')).toHaveAttribute('data-workers', '2');
  });
});

test('a session whose holder has taken no step yet says «فکر میکند»', async ({ page }) => {
  await flag(page, 'hq.e2e.mood', 'thinking');
  await clean(page, async () => {
    await page.goto('/s/F-0007');
    await expect(session(page)).toHaveAttribute('data-mood', 'thinking');
    await expect(light(page)).toHaveText('فکر میکند');
  });
});

test('a build of the workshop: its minutes as a ring, «نگه دار» holds it and «ادامه بده» takes it up again', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/s/F-0010');
    const bar = page.getByTestId('now-bar');
    await expect(bar).toHaveAttribute('data-kind', 'workshop');
    const ring = page.getByTestId('build-ring');
    await expect(ring).toHaveText(/^۲[۳-۹] از ۶۰ دقیقه$/);
    await expect(ring.locator('[data-ring-minute]')).toHaveText(/^[۰-۹]+$/);
    await expect(ring).not.toHaveAttribute('data-late', '');
    await expect(bar.locator('[data-now-who]')).toContainText('کارگاه');
    await expect(bar.locator('[data-now-sentence]')).toContainText('صحنه‌ی ۳ را رندر میکند');
    // The owner's stop, from the bar; the same bar takes it up again.
    await bar.getByRole('button', { name: 'نگه دار' }).click();
    await expect(bar).toHaveAttribute('data-state', 'held');
    await expect(bar.getByRole('status')).toHaveText('کار نگه داشته شد');
    await bar.getByRole('button', { name: 'ادامه بده' }).click();
    await expect(bar).toHaveAttribute('data-state', 'working');
    await expect(page.getByTestId('build-ring')).toBeVisible();
    await expect(bar.getByRole('button', { name: 'نگه دار' })).toBeVisible();
  });
});

test('work held for twenty minutes and more: the bar\'s «ادامه بده» is the only one, no still card beside it', async ({ page }) => {
  await page.clock.install();
  await clean(page, async () => {
    await page.goto('/s/F-0010');
    const bar = page.getByTestId('now-bar');
    await bar.getByRole('button', { name: 'نگه دار' }).click();
    await expect(bar).toHaveAttribute('data-state', 'held');
    // Twenty-one minutes later, nobody has worked on it: it is his hold, not a session left standing.
    await page.clock.fastForward('21:00');
    await expect(bar).toHaveAttribute('data-state', 'held');
    await expect(page.getByTestId('still-card')).toHaveCount(0);
    await expect(session(page)).not.toHaveAttribute('data-mood', 'still');
    await expect(page.getByRole('button', { name: 'ادامه بده', exact: true })).toHaveCount(1);
    await bar.getByRole('button', { name: 'ادامه بده' }).click();
    await expect(bar).toHaveAttribute('data-state', 'working');
    await expect(page.getByRole('button', { name: 'ادامه بده', exact: true })).toHaveCount(0);
  });
});

test('a build near its sixty minutes says so in words, not in colour alone', async ({ page }) => {
  await flag(page, 'hq.e2e.ring', 'late');
  await clean(page, async () => {
    await page.goto('/s/F-0010');
    const ring = page.getByTestId('build-ring');
    await expect(ring).toHaveAttribute('data-late', '');
    await expect(ring).toHaveText(/^۵[۶-۹] از ۶۰ دقیقه$/);
    await expect(page.getByTestId('now-bar').locator('[data-now-late]')).toHaveText('نزدیک سقف زمان');
  });
});

test('a direct session: the holder does the work himself, the bar and the details say so', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/s/F-0011');
    const bar = page.getByTestId('now-bar');
    await expect(bar).toHaveAttribute('data-kind', 'direct');
    await expect(bar.locator('[data-now-who]')).toContainText('دارد روی فرمان تو کار میکند');
    await expect(page.getByTestId('build-ring')).toContainText('از ۶۰ دقیقه');
    const sheet = await openDetails(page);
    await expect(sheet.getByTestId('direct-session')).toBeVisible();
    await expect(sheet.getByTestId('direct-session')).not.toBeEmpty();
  });
});

test('an outside call at work: ChatGPT in the «الان» bar with its mark, whose it is, the whole sentence and a timer; no ring, nothing to hold', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/s/F-0094');
    await expect(session(page)).toHaveAttribute('data-mood', 'working');
    await expect(light(page)).toHaveText('کار میکند');
    const bar = page.getByTestId('now-bar');
    await expect(bar).toHaveAttribute('data-state', 'working');
    await expect(bar).toHaveAttribute('data-kind', 'call');
    await expect(bar.locator('[data-call-mark]')).toHaveAttribute('aria-label', 'ChatGPT');
    await expect(bar.locator('[data-now-who]')).toHaveText(/^ChatGPT.*پرو-چارت$/);
    await expect(bar.locator('[data-now-sentence]')).toHaveText('در صف ChatGPT: پیش‌نویس متن');
    await expect(bar.locator('[data-now-timer]')).toHaveText(/^\d+:\d{2}$/);
    await expect(page.getByTestId('build-ring')).toHaveCount(0);
    await expect(bar.getByRole('button', { name: 'نگه دار' })).toHaveCount(0);
    await expect(page.getByTestId('still-card')).toHaveCount(0);
    // one tap: who works, with the same mark
    await bar.getByRole('button', { name: 'کار زنده را باز کن' }).click();
    const sheet = page.getByTestId('live-sheet');
    await expect(sheet.locator('[data-worker="call"]')).toContainText('در صف ChatGPT: پیش‌نویس متن');
    await expect(sheet.locator('[data-worker="call"] [data-call-mark]')).toBeVisible();
  });
});

test('a session nobody works on is «ایستاده»: one calm card, a silver edge, the last thing done, and «ادامه بده» as the one gold', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/s/F-0095');
    await expect(session(page)).toHaveAttribute('data-mood', 'still');
    await expect(light(page)).toHaveText('ایستاده');
    // the header still says where the plan stands and the pace
    await expect(page.locator('[data-session-facts]')).toContainText('کار 3 از 18');
    await expect(page.locator('[data-session-facts]')).toContainText('با من');
    const card = page.getByTestId('still-card');
    await expect(card).toHaveAttribute('data-edge', 'silver');
    await expect(card.getByTestId('mood-light')).toHaveText('ایستاده');
    await expect(card.locator('[data-still-sentence]')).toContainText('الان کسی روی این جلسه کار نمیکند؛ آخرین کار: … پیش‌نویس متن');
    // the clock time of the last thing done: a Latin figure, after the day it was done
    await expect(card.locator('[data-still-sentence] bdi.fig')).toHaveText(/^\d{2}:\d{2}$/);
    await expect(golds(page)).toHaveText(['ادامه بده']);
    await expect(card).not.toContainText('شما');
    await expect(page.getByTestId('now-bar')).toHaveCount(0);
    // the holder's question of that night is a bubble of the talk with the hub's new lead, never «شما»
    await expect(page.getByLabel('گفتگو', { exact: true })).toContainText('سؤال از تو');
  });
});

test('«کار زنده» of a session nobody works on ends with «ادامه بده», as on Android', async ({ page }) => {
  await clean(page, async () => {
    // The build held: nobody works; the sheet says since when, and takes it up again.
    await page.goto('/s/F-0010');
    const bar = page.getByTestId('now-bar');
    await bar.getByRole('button', { name: 'نگه دار' }).click();
    await expect(bar).toHaveAttribute('data-state', 'held');
    await bar.getByRole('button', { name: 'کار زنده را باز کن' }).click();
    const sheet = page.getByTestId('live-sheet');
    const nudge = sheet.getByTestId('idle-nudge');
    await expect(nudge).toContainText('آخرین کار');
    await nudge.getByRole('button', { name: 'ادامه بده' }).click();
    await expect(page.getByText('گفتم ادامه بدهد.')).toBeVisible();
    await expect(sheet.getByRole('list', { name: 'چه کسی کار میکند' })).toBeVisible();
  });
});

test('a knot is one line with its way out; the others wait behind «و … گره‌ی دیگر»', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/s/F-0005');
    await expect(session(page)).toHaveAttribute('data-mood', 'stuck');
    await expect(light(page)).toHaveText('گیر کرده');
    const knot = page.getByTestId('knot');
    await expect(knot).toHaveAttribute('data-count', '1');
    await expect(knot.getByRole('alert')).toContainText('بودجه‌ی این فرمان تمام شد');
    // Its way out is the screen's one gold.
    await expect(golds(page)).toHaveText(['+200 هزار واحد بده']);
    // Two knots: the first with its fix, the other one tap away.
    await page.goto('/s/F-0007');
    const two = page.getByTestId('knot');
    await expect(two).toHaveAttribute('data-count', '2');
    await expect(two.locator('[data-blocker]')).toHaveCount(0);
    await two.getByRole('button', { name: 'و ۱ گره‌ی دیگر' }).click();
    await expect(two.locator('[data-blocker]')).toHaveCount(1);
    await expect(golds(page)).toHaveText(['مُهر سری انتشار']);
  });
});

test('a finished session: «تأیید و بستن» in the decision bar closes it with one tap, and it ends with its leaf', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/s/F-0006');
    const bar = page.getByTestId('decision-bar');
    await expect(bar.locator('[data-decision-context]')).toContainText('با تأیید تو جلسه بسته و بایگانی میشود');
    await expect(bar.getByRole('button')).toHaveText(['تأیید و بستن', 'اصلاح']);
    // The bar's primary is the only full gold (the knot's own way out steps back to silver).
    await expect(golds(page)).toHaveText(['تأیید و بستن']);
    await bar.getByRole('button', { name: 'تأیید و بستن' }).click();
    const leaf = page.getByTestId('end-leaf');
    await expect(leaf).toBeVisible();
    await expect(leaf).toContainText('این جلسه تأیید و بایگانی شد');
    await expect(page.getByTestId('decision-bar')).toHaveCount(0);
    await expect(session(page)).toHaveAttribute('data-mood', 'done');
  });
});

test('a finished session with a reel: «تأیید و انتشار» is the gold, the file is seen where it is, and the sheet has it all in place', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/s/F-0012');
    const bar = page.getByTestId('decision-bar');
    await expect(bar.getByRole('button')).toHaveText(['تأیید و انتشار', 'اصلاح', 'فقط ببند']);
    await expect(golds(page)).toHaveText(['تأیید و انتشار']);
    // The output in the talk: its files as a strip, the video first; one publish action for the package, the cover goes with its reel.
    const out = page.locator('section[data-output="O-000067"]');
    const tiles = out.locator('[data-file-tile]');
    await expect(tiles).toHaveCount(2);
    await expect(tiles.nth(0)).toHaveAttribute('data-kind', 'video');
    await expect(out.locator('[data-tile-publish="lead"]')).toHaveText('آماده‌ی انتشار');
    await expect(out.locator('[data-tile-publish="cover"]')).toHaveText('کاور ریلز');
    await expect(out.getByRole('button', { name: 'تأیید و انتشار' })).toHaveCount(0);
    // A tap on the video plays it where it is (or, where the browser cannot play it, says so and offers the file).
    await out.getByRole('button', { name: 'پخش reel-stoploss.mp4' }).click();
    await expect(out.locator('[data-inline-video], [data-video-failed]').first()).toBeVisible();
    // The bar opens the one publish sheet with the caption, the account and the cover already there.
    await bar.getByRole('button', { name: 'تأیید و انتشار' }).click();
    const sheet = page.getByTestId('publish-sheet');
    await expect(sheet.getByRole('heading', { name: 'تأیید و انتشار' })).toBeVisible();
    await expect(sheet.getByLabel('کپشن')).toHaveValue(/حد ضرر را کجا بگذاریم/);
    await expect(sheet).toContainText('@tradeyar');
    await expect(sheet.getByRole('button', { name: 'cover.png' })).toHaveAttribute('aria-pressed', 'true');
    await sheet.getByTestId('decision-bar').getByRole('button', { name: 'انتشار', exact: true }).click();
    await expect(sheet).toHaveCount(0);
    // It is on its way: the tile says where it stands and the bar now only closes the session.
    await expect(out.locator('[data-tile-publish="lead"]')).toHaveCount(0);
    await expect(page.getByTestId('decision-bar').getByRole('button').first()).toHaveText('تأیید و بستن');
  });
});

test('«اصلاح» puts the output\'s name in the composer; a closed session ends with its leaf and offers to open again', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/s/F-0012?about=O-000067');
    await expect(page.getByLabel('پیام', { exact: true })).toHaveValue(/^درباره‌ی «ریلز: حد ضرر را کجا بگذاریم»: $/);
    await page.goto('/s/F-0004');
    await expect(session(page)).toHaveAttribute('data-mood', 'done');
    const leaf = page.getByTestId('end-leaf');
    await expect(leaf).toContainText('این جلسه تأیید و بایگانی شد');
    await expect(leaf.locator('[data-leaf-figures]')).toContainText('طول کشید');
    await expect(leaf.getByRole('button', { name: 'دوباره باز کن' })).toBeVisible();
    await expect(page.getByTestId('now-bar')).toHaveCount(0);
    await expect(page.getByTestId('waiting-card')).toHaveCount(0);
    await expect(golds(page)).toHaveCount(0);
  });
});

test('the details are one sheet: the order\'s words, the plan, the people, the files and the end of the session', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/s/F-0007');
    const sheet = await openDetails(page);
    await expect(sheet.getByLabel('متن فرمان')).toContainText('کلیپ بساز');
    for (const part of ['وضعیت و روش کار', 'کی در جلسه است', 'کارها', 'رسید و برنامه', 'خروجی‌ها', 'بستن و پنهان کردن']) await expect(sheet.getByLabel(part, { exact: true }), part).toHaveCount(1);
    // Nothing in the sheet is a full gold: the session's act is on the page behind it.
    await expect(sheet.locator('.bg-gold:visible')).toHaveCount(0);
  });
});

test('@phone the session fits a phone in every state, the composer in reach', async ({ page }) => {
  await page.setViewportSize({ width: 400, height: 860 });
  await clean(page, async () => {
    for (const ref of ['F-0008', 'F-0007', 'F-0010', 'F-0005', 'F-0012', 'F-0004', 'F-0094', 'F-0095']) {
      await page.goto(`/s/${ref}`);
      await expect(session(page), ref).toBeVisible();
      await expect(page.getByLabel('نوشتن', { exact: true }), ref).toBeInViewport();
      expect(await overflow(page), ref).toBeLessThanOrEqual(0);
    }
  });
});
