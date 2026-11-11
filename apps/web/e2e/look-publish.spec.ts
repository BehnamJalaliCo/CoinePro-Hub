import { expect, test, type Page } from '@playwright/test';
import { clean } from './support';

// ⟨1.0.1⟩ Part C, the publish desk (C2.3) and the output with its «تأیید و انتشار» (C3.3), over the demo holding. The desk: three
// sections in their order (ready, in the queue, published), each card with the media itself, the company and its account, the caption
// and the account's best hour; only the first card's action is the full gold; a company whose publishing path is not set has no action
// and one quiet line; a queued one is taken back in place; an empty desk is one calm sentence; a hub before §55.2 shows none of its
// entries. The output: the thing itself first, the numbers in one row, the summary not said twice, «تأیید و انتشار» and «اصلاح» in the
// decision bar, the removals last; the list is media cards whose search folds away under the bar. The demo asks for an empty desk
// through `hq.e2e.desk=empty` and an older hub through `hq.e2e.old55`.

const flag = (page: Page, key: string, value: string) => page.addInitScript(([k, v]) => window.localStorage.setItem(k!, v!), [key, value]);
const overflow = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
const desk = (page: Page) => page.getByTestId('publish-desk');
const card = (page: Page, section: 'ready' | 'queue' | 'done', output: string) => page.locator(`[data-desk="${section}"][data-output="${output}"]`);
const golds = (page: Page) => page.locator('main .bg-gold:visible');
const detail = (page: Page) => page.getByTestId('output-detail');

// ================================================================================================ C2.3 the desk ==
test('the desk: three sections in their order; a ready card is the media, the company, the account, the caption and the best hour', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/outputs/desk');
    await expect(page.getByRole('heading', { level: 1, name: 'میز انتشار' })).toBeVisible();
    await expect(desk(page).getByRole('heading', { level: 2 })).toHaveText([/^آماده‌ی انتشار/, /^در صف/, /^منتشرشده/]);
    const first = card(page, 'ready', 'O-000067');
    await expect(first).toHaveAttribute('data-kind', 'reel');
    await expect(first.locator('[data-hero-media]')).toBeVisible();
    await expect(first.locator('[data-desk-who]')).toContainText('تریدیار');
    await expect(first.locator('[data-desk-who]')).toContainText('اینستاگرام');
    await expect(first.locator('[data-desk-who] bdi')).toHaveText('@tradeyar');
    await expect(first.getByRole('link', { name: 'ریلز: حد ضرر را کجا بگذاریم' })).toBeVisible();
    // The first two lines of the caption; a tap shows all of it.
    const caption = first.locator('[data-desk-caption]');
    await expect(caption).toHaveAttribute('aria-expanded', 'false');
    await expect(caption).toContainText('حد ضرر را کجا بگذاریم؟ سه قانون ساده.');
    await caption.click();
    await expect(caption).toHaveAttribute('aria-expanded', 'true');
    // The account's best hour, an isolated Latin figure.
    await expect(first.locator('[data-desk-best]')).toHaveText('بهترین ساعت این حساب: 21:00');
    await expect(first.locator('[data-desk-best] bdi')).toHaveAttribute('dir', 'ltr');
    // One that came from a working group says which.
    await expect(card(page, 'ready', 'O-000066')).toContainText('کارگروه «موشن‌گرافی روزانه‌ی پرو-چارت»');
  });
});

test('the desk: only the first card that can go out carries the full gold; a company whose path is not set has no action', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/outputs/desk');
    const actions = page.locator('[data-desk="ready"]').getByRole('button', { name: 'تأیید و انتشار' });
    await expect(actions.first()).toBeVisible();
    await expect(golds(page)).toHaveCount(1);
    await expect(card(page, 'ready', 'O-000067').getByRole('button', { name: 'تأیید و انتشار' })).toHaveClass(/bg-gold/);
    await expect(card(page, 'ready', 'O-000066').getByRole('button', { name: 'تأیید و انتشار' })).not.toHaveClass(/bg-gold/);
    // Its publishing path is the technical team's work: one quiet line, never a step of the owner's.
    const fx = card(page, 'ready', 'O-000064');
    await expect(fx.locator('[data-route-not-ready]')).toHaveText('مسیر انتشار این شرکت را تیم فنی وصل میکند');
    await expect(fx.getByRole('button', { name: 'تأیید و انتشار' })).toHaveCount(0);
    await expect(fx).not.toContainText('وصل نیست');
  });
});

test('the desk: «تأیید و انتشار» opens the one publish sheet with everything in place, and the card leaves the ready ones', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/outputs/desk');
    const ready = page.locator('[data-desk="ready"]');
    await expect(ready).toHaveCount(6);
    await card(page, 'ready', 'O-000067').getByRole('button', { name: 'تأیید و انتشار' }).click();
    const sheet = page.getByTestId('publish-sheet');
    await expect(sheet.getByRole('heading', { name: 'تأیید و انتشار' })).toBeVisible();
    await expect(sheet.locator('[data-publish-preview]')).toBeVisible();
    await expect(sheet.getByLabel('کپشن')).toHaveValue(/حد ضرر را کجا بگذاریم؟ سه قانون ساده\./);
    await expect(sheet).toContainText('@tradeyar');
    await expect(sheet.getByRole('button', { name: 'cover.png' })).toHaveAttribute('aria-pressed', 'true');
    // The time: now, an hour, or the account's best hour.
    const time = sheet.getByTestId('publish-time');
    await expect(time.getByRole('button', { name: 'بهترین ساعت (21:00)' })).toBeVisible();
    // The sheet's own bar carries its one gold.
    await expect(sheet.locator('.bg-gold:visible')).toHaveText(['انتشار']);
    await sheet.getByTestId('decision-bar').getByRole('button', { name: 'انتشار', exact: true }).click();
    await expect(sheet).toHaveCount(0);
    // The desk is read again: it is no longer among the ready ones, and the next card now carries the gold.
    await expect(card(page, 'ready', 'O-000067')).toHaveCount(0);
    await expect(page.locator('[data-desk]:not([data-desk="ready"])[data-output="O-000067"]')).toBeVisible();
    await expect(golds(page)).toHaveCount(1);
  });
});

test('the desk: a queued one says its hour in Latin digits and is taken back in place; what went out is linked, what failed says why', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/outputs/desk');
    const queued = card(page, 'queue', 'O-000062');
    await expect(queued).toHaveAttribute('data-state', 'scheduled');
    await expect(queued.locator('[data-desk-time]')).toHaveText(/ 18:30$/);
    await expect(queued.locator('[data-desk-time] bdi')).toHaveText('18:30');
    await expect(card(page, 'queue', 'O-000063').locator('[data-desk-time]')).toHaveText('در حال انتشار');
    // «لغو», asked once, in place.
    await queued.getByRole('button', { name: 'لغو', exact: true }).click();
    const ask = queued.getByRole('group', { name: 'لغو انتشار' });
    await expect(ask).toContainText('این انتشار لغو شود؟');
    await ask.getByRole('button', { name: 'لغو کن' }).click();
    await expect(page.getByText('لغو شد؛ منتشر نمیشود.')).toBeVisible();
    await expect(card(page, 'queue', 'O-000062')).toHaveCount(0);
    await expect(card(page, 'done', 'O-000062')).toHaveAttribute('data-state', 'cancelled');
    await expect(card(page, 'done', 'O-000062')).toContainText('لغو شد');
    // Taken back, it can go out again.
    await expect(card(page, 'ready', 'O-000062')).toBeVisible();
    // Published: the post opens outside. Failed: the hub's words and a quiet «دوباره».
    const out = card(page, 'done', 'O-000065');
    await expect(out).toHaveAttribute('data-state', 'published');
    await expect(out.getByRole('link', { name: 'باز کن' })).toHaveAttribute('target', '_blank');
    const failed = card(page, 'done', 'O-000066');
    await expect(failed.locator('[data-desk-note]')).toContainText('اینستاگرام این ویدیو را نپذیرفت');
    await expect(failed.getByRole('button', { name: 'دوباره' })).not.toHaveClass(/bg-gold/);
    await failed.getByRole('button', { name: 'دوباره' }).click();
    await expect(page.getByTestId('publish-sheet')).toBeVisible();
  });
});

test('an empty desk is one calm sentence; «تازه کن» reads it again', async ({ page }) => {
  await flag(page, 'hq.e2e.desk', 'empty');
  await clean(page, async () => {
    await page.goto('/outputs/desk');
    await expect(page.getByTestId('desk-empty')).toHaveText('چیزی آماده‌ی انتشار نیست؛ هر خروجی تأییدشدنی همین‌جا می‌آید.');
    await expect(page.locator('[data-desk]')).toHaveCount(0);
    await expect(desk(page).getByRole('heading', { level: 2 })).toHaveCount(0);
    await desk(page).getByRole('button', { name: 'تازه کن' }).click();
    await expect(page.getByTestId('desk-empty')).toBeVisible();
  });
});

test('the desk is reached from the outputs, from the home and from the navigation', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/outputs');
    const tabs = page.getByTestId('outputs-tabs');
    await expect(tabs).toContainText('میز انتشار');
    await tabs.getByRole('link', { name: /میز انتشار/ }).click();
    await expect(page).toHaveURL(/\/outputs\/desk$/);
    await expect(desk(page)).toBeVisible();
    await page.getByTestId('outputs-tabs').getByRole('link', { name: 'خروجی‌ها' }).click();
    await expect(page).toHaveURL(/\/outputs$/);
    await page.goto('/');
    const line = page.getByTestId('desk-line');
    await expect(line).toContainText('۶ خروجی آماده‌ی انتشار');
    await expect(line).toContainText('۲ در صف');
    await line.click();
    await expect(page).toHaveURL(/\/outputs\/desk$/);
    await expect(page.getByRole('navigation').getByRole('link', { name: 'میز انتشار' }).first()).toBeVisible();
    // «همه‌ی بخش‌ها» lists it beside the outputs, with its line.
    await page.getByRole('button', { name: 'همه‌ی بخش‌ها' }).click();
    const places = page.getByRole('dialog', { name: 'همه‌ی بخش‌ها' });
    await expect(places.getByRole('link', { name: /میز انتشار/ })).toHaveAttribute('href', '/outputs/desk');
  });
});

test('on a hub before the desk none of its entries is shown, and its own address says so calmly', async ({ page }) => {
  await flag(page, 'hq.e2e.old55', '1');
  await clean(page, async () => {
    await page.goto('/outputs');
    await expect(page.locator('[data-output-row]').first()).toBeVisible();
    await expect(page.getByTestId('outputs-tabs')).toHaveCount(0);
    await expect(page.getByRole('navigation').getByRole('link', { name: 'میز انتشار' })).toHaveCount(0);
    await page.goto('/');
    await expect(page.getByTestId('turn-row')).toBeVisible();
    await expect(page.getByTestId('desk-line')).toHaveCount(0);
    await page.goto('/outputs/desk');
    await expect(page.getByText('میز انتشار بعد از به‌روزرسانی ستاد می‌آید')).toBeVisible();
    await expect(page.locator('[data-desk]')).toHaveCount(0);
    await page.getByRole('button', { name: 'همه‌ی بخش‌ها' }).click();
    await expect(page.getByRole('dialog', { name: 'همه‌ی بخش‌ها' }).getByRole('link', { name: /میز انتشار/ })).toHaveCount(0);
  });
});

// ============================================================================================ C3.3 the output ==
test('the output opens with the thing itself, then the numbers in one row; the summary is not said twice', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/outputs?ref=O-000067&tab=all');
    await expect(detail(page).getByRole('heading', { level: 2 })).toHaveText('ریلز: حد ضرر را کجا بگذاریم');
    // The video, large and playable in place (where the browser cannot play it: one line and the file).
    const face = detail(page).locator('[data-output-face]');
    await expect(face).toHaveAttribute('data-output-face', 'video');
    await expect(face.locator('[data-output-hero="video"], [data-video-failed]').first()).toBeVisible();
    // The numbers: how it was made, what it cost, who made it, his rating.
    const figures = page.getByTestId('output-figures');
    await expect(figures).toContainText('ساخت');
    await expect(figures.getByTestId('made-with')).toContainText('Opus 5.5، بیشترین دقت');
    await expect(figures).toContainText('331K');
    await expect(figures).toContainText('$3.84');
    await expect(figures).toContainText('مدیر رسانه');
    await expect(figures).toContainText('امتیاز تو');
    await expect(figures).not.toContainText('·');
    // The thing comes first, the numbers after it, the text after them.
    const y = async (sel: string) => (await detail(page).locator(sel).first().boundingBox())!.y;
    expect(await y('[data-output-face]')).toBeLessThan(await y('[data-testid="output-figures"]'));
    expect(await y('[data-testid="output-figures"]')).toBeLessThan(await y('[data-output-text]'));
    await expect(detail(page).getByText(/ثانیه‌ای با کاور؛ آماده‌ی انتشار/)).toHaveCount(1);
  });
});

test('the output: «تأیید و انتشار» is the page\'s one gold in its decision bar, with «اصلاح» that opens its session with the output named', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/outputs?ref=O-000067&tab=all');
    const bar = detail(page).getByTestId('decision-bar');
    await expect(bar.getByRole('button')).toHaveText(['تأیید و انتشار', 'اصلاح']);
    await expect(bar.locator('[data-decision-context]')).toContainText('@tradeyar');
    await expect(bar.locator('[data-decision-context]')).toContainText('بهترین ساعت 21:00');
    await expect(bar.locator('[data-decision-context]')).toContainText('بی کارت و بی اثر انگشت');
    await expect(golds(page)).toHaveText(['تأیید و انتشار']);
    // Its files: the reel is the bar's; its cover goes with it and is a second, quieter act.
    const rows = page.getByTestId('publish').locator('[data-file]');
    await expect(rows).toHaveCount(2);
    await expect(rows.nth(0).getByRole('button')).toHaveCount(0);
    await expect(rows.nth(1)).toContainText('کاور ریلز؛ با ریلز میرود');
    await expect(rows.nth(1).getByRole('button', { name: 'جدا منتشر کن' })).not.toHaveClass(/bg-gold/);
    // «خوانده شد» and «بایگانی» are quiet; what removes it for ever sits last.
    await expect(detail(page).getByRole('button', { name: 'خوانده شد' })).not.toHaveClass(/bg-gold/);
    await expect(detail(page).getByRole('button', { name: 'بایگانی کن' })).not.toHaveClass(/bg-gold/);
    const removeY = (await detail(page).locator('[data-output-remove]').boundingBox())!.y;
    const rateY = (await detail(page).getByLabel('امتیاز تو', { exact: true }).boundingBox())!.y;
    expect(removeY).toBeGreaterThan(rateY);
    await bar.getByRole('button', { name: 'اصلاح' }).click();
    await expect(page).toHaveURL(/\/s\/F-0012\?about=O-000067$/);
    await expect(page.getByLabel('پیام', { exact: true })).toHaveValue('درباره‌ی «ریلز: حد ضرر را کجا بگذاریم»: ');
  });
});

test('the output: published from its bar, the row says where it stands and the bar leaves', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/outputs?ref=O-000059&tab=all');
    await expect(detail(page).locator('[data-output-face]')).toHaveAttribute('data-output-face', 'image');
    const row = page.getByTestId('publish').locator('[data-file="post-01.jpg"]');
    await expect(row).toHaveAttribute('data-publish', 'none');
    await detail(page).getByTestId('decision-bar').getByRole('button', { name: 'تأیید و انتشار' }).click();
    const sheet = page.getByTestId('publish-sheet');
    await expect(sheet).toContainText('@pro.chart');
    await sheet.getByTestId('decision-bar').getByRole('button', { name: 'انتشار', exact: true }).click();
    await expect(sheet).toHaveCount(0);
    await expect(row).not.toHaveAttribute('data-publish', 'none');
    await expect(detail(page).getByTestId('decision-bar')).toHaveCount(0);
  });
});

test('the output of a company whose path is not set: the quiet line, no publish action anywhere on the page', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/outputs?ref=O-000064&tab=all');
    await expect(page.getByTestId('publish').locator('[data-route-not-ready]')).toHaveText('مسیر انتشار این شرکت را تیم فنی وصل میکند');
    await expect(detail(page).getByTestId('decision-bar')).toHaveCount(0);
    await expect(detail(page).getByRole('button', { name: /انتشار|منتشر/ })).toHaveCount(0);
  });
});

test('a date in a title is one left-to-right run, never drawn day first', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/outputs?ref=O-000032&tab=all');
    const title = detail(page).getByRole('heading', { level: 2 });
    await expect(title).toContainText('گزارش صبحگاهی');
    const iso = title.locator('bdi', { hasText: '2026-10-17' });
    await expect(iso).toHaveAttribute('dir', 'ltr');
    await expect(iso).toHaveText('2026-10-17');
    // A document shows its first lines, and the whole of it one tap away.
    await expect(detail(page).locator('[data-output-face]')).toHaveCount(0);
    await expect(detail(page).locator('[data-output-text]')).toBeVisible();
  });
});

test('the outputs list: media cards with their posters, a new one with its edge, «بی‌امتیاز» a silver dot; a card opens its page', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/outputs?tab=all');
    const list = page.getByTestId('outputs-list');
    const media = list.locator('[data-output-row="O-000028"]');
    await expect(media.locator('[data-poster]')).toBeVisible();
    // New: the thin gold edge; seen: none.
    await expect(list.locator('[data-output-row="O-000031"]')).toHaveClass(/hq-edge/);
    await expect(list.locator('[data-output-row="O-000030"]')).not.toHaveClass(/hq-edge/);
    // Unrated is a dot with its name, not a gold chip.
    const dot = list.locator('[data-output-row="O-000031"] [data-unrated]').getByRole('img', { name: 'بی‌امتیاز' });
    await expect(dot).toBeVisible();
    await expect(dot).not.toHaveClass(/gold/);
    await expect(list.locator('.bg-gold:visible')).toHaveCount(0);
    await list.locator('[data-output-row="O-000031"]').getByRole('button').nth(0).click();
    await expect(page).toHaveURL(/ref=O-000031/);
    await expect(detail(page)).toBeVisible();
  });
});

test('@phone the list\'s search folds away under its bar, an open output takes the list\'s place, and the desk fits', async ({ page }) => {
  await page.setViewportSize({ width: 400, height: 860 });
  await clean(page, async () => {
    await page.goto('/outputs?tab=all');
    const bar = page.getByTestId('outputs-bar');
    await expect(bar).not.toHaveAttribute('data-stuck', '');
    await expect(page.getByLabel('جستجو در خروجی‌ها')).toBeVisible();
    await expect(page.locator('[data-output-row]').nth(5)).toBeVisible();
    await page.evaluate(() => window.scrollTo(0, 900));
    await expect(bar).toHaveAttribute('data-stuck', '');
    await expect(page.getByLabel('جستجو در خروجی‌ها')).toBeHidden();
    await expect(bar.getByRole('button', { name: /فیلترها/ })).toBeInViewport();
    expect(await overflow(page)).toBeLessThanOrEqual(0);
    // An open output takes the list's place; its own «خروجی‌ها» leads back.
    await page.goto('/outputs?ref=O-000067&tab=all');
    await expect(detail(page)).toBeVisible();
    await expect(page.getByTestId('outputs-list')).toBeHidden();
    await expect(detail(page).getByTestId('decision-bar')).toBeInViewport();
    expect(await overflow(page)).toBeLessThanOrEqual(0);
    // The round command button never covers the bar's actions.
    const orb = (await page.locator('[data-command-button]').boundingBox())!;
    const dbar = (await detail(page).getByTestId('decision-bar').boundingBox())!;
    expect(orb.y + orb.height).toBeLessThanOrEqual(dbar.y + 1);
    await detail(page).getByRole('button', { name: 'خروجی‌ها' }).click();
    await expect(page.getByTestId('outputs-list')).toBeVisible();
    await page.goto('/outputs/desk');
    await expect(desk(page)).toBeVisible();
    expect(await overflow(page)).toBeLessThanOrEqual(0);
  });
});
