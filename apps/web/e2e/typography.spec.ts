import { expect, test } from '@playwright/test';
import { clean } from './support';

// ⟨1.10.1⟩ The owner, 2026-11-01: Latin inside Persian keeps its digits and direction (model names, versions, paths, refs, URLs), agent
// prose reads as neat justified paragraphs, and notifications are chosen on both tabs and deleted for good (contract §28.5).

test('Latin runs keep Latin digits and their own direction; prose counts stay Persian', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/outputs?ref=O-000032&tab=all');
    const article = page.locator('article').first();
    const line = article.getByRole('listitem').filter({ hasText: 'مدل‌های در دسترس نیست' });
    await expect(line).toHaveText('ChatGPT: مدل‌های در دسترس نیست: GPT 5.5، GPT 5.3');
    const runs = await line.locator('bdi').allTextContents();
    expect(runs).toEqual(['ChatGPT', 'GPT 5.5', 'GPT 5.3']);
    // Each run is isolated, left to right, in the face with Latin digits.
    const style = await line.locator('bdi').nth(1).evaluate((el) => { const s = getComputedStyle(el); return { dir: s.direction, bidi: s.unicodeBidi, font: s.fontFamily }; });
    expect(style.dir).toBe('ltr');
    expect(style.bidi).toBe('isolate');
    expect(style.font.startsWith('IRANYekanX,') || style.font.startsWith('"IRANYekanX"')).toBe(true);
    // A path, a version and a ref-like token are runs; the bare count «3» is prose.
    const other = article.getByRole('listitem').filter({ hasText: 'مسیر پشتیبان' });
    const otherRuns = await other.locator('bdi, code').allTextContents();
    expect(otherRuns).toContain('/srv/backups/hq/2026-10-31/postgres-full.dump');
    expect(otherRuns).toContain('api.v1');
    expect(otherRuns).toContain('2.14.1');
    expect(otherRuns).not.toContain('3');
  });
});

test('agent prose is justified, its inline code keeps the line and may break', async ({ page }) => {
  await page.goto('/outputs?ref=O-000040&tab=all');
  const p = page.locator('.hq-prose p').first();
  await expect(p).toBeVisible();
  const s = await p.evaluate((el) => { const c = getComputedStyle(el); return { align: c.textAlign, last: c.textAlignLast }; });
  expect(s.align).toBe('justify');
  expect(['start', 'right']).toContain(s.last);
  const code = page.locator('.hq-prose code').first();
  const c = await code.evaluate((el) => { const x = getComputedStyle(el); return { ws: x.whiteSpace, wrap: x.overflowWrap }; });
  expect(c.ws).not.toBe('nowrap');
  expect(c.wrap).toBe('anywhere');
});

test('chooses unread notifications with shift, marks them read, then deletes every read one after the confirmation', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/notifications');
    const boxes = page.getByRole('checkbox', { name: /^انتخاب: / });
    await expect(boxes.first()).toBeVisible();
    await boxes.nth(0).click();
    await boxes.nth(2).click({ modifiers: ['Shift'] });
    await expect(boxes.nth(1)).toBeChecked();
    const bar = page.getByRole('toolbar', { name: 'کار با اعلان‌های انتخاب‌شده' });
    await expect(bar.getByText('۳ انتخاب‌شده')).toBeVisible();
    await bar.getByRole('button', { name: 'خوانده‌شده' }).click();
    await expect(page.getByText(/اعلان خوانده شد/)).toBeVisible();
    // The read tab: «انتخاب همه» and «حذف», only «حذف».
    await page.getByRole('radio', { name: 'خوانده‌شده', exact: true }).click();
    await page.getByRole('checkbox', { name: /انتخاب همه/ }).click();
    await expect(bar.getByRole('button', { name: 'خوانده‌شده' })).toHaveCount(0);
    await bar.getByRole('button', { name: 'حذف' }).click();
    const dialog = page.getByRole('dialog');
    await expect(dialog.getByText('از دیتابیس پاک میشود و برنمیگردد.')).toBeVisible();
    await dialog.getByRole('button', { name: 'حذف' }).click();
    await expect(page.getByText(/اعلان برای همیشه پاک شد/)).toBeVisible();
    await expect(page.getByText('هنوز اعلانی خوانده نشده')).toBeVisible();
  });
});

test('deletes one unread notification by its box', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/notifications');
    const boxes = page.getByRole('checkbox', { name: /^انتخاب: / });
    await expect(boxes.first()).toBeVisible();
    const before = await boxes.count();
    await boxes.last().click();
    await page.getByRole('toolbar', { name: 'کار با اعلان‌های انتخاب‌شده' }).getByRole('button', { name: 'حذف' }).click();
    await page.getByRole('dialog').getByRole('button', { name: 'حذف' }).click();
    await expect(page.getByText(/اعلان برای همیشه پاک شد/)).toBeVisible();
    await expect(boxes).toHaveCount(before - 1);
  });
});
