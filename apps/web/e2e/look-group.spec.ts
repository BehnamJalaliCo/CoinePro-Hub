import { expect, test, type Page } from '@playwright/test';
import { clean } from './support';

// ⟨1.0.1⟩ Part C, the working group (C3.4), over the demo holding. A sealed working group opens with its member companies as tiles
// (state as a shape and a word, last run, next run, a work line only while something of it runs; one that stands still says why and
// has a quiet «راه بینداز»), then each routine with its last seven runs as dots; what it is folds under «تعریف کارگروه». Each
// member's settings are one block: «انتشار خودکار» (a silver switch), «گوینده‌ی محتوا», «دفتر موضوع‌ها». A draft's «مُهر کارگروه» is in
// its decision bar with a one-line summary: one tap, no fingerprint. The growth groups (`/groups`) wear the same look. The demo
// holds PB-0003 (sealed, one member working, one standing still), PB-0001 (a draft) and asks for a run in the queue through
// `hq.e2e.group-run`.

const flag = (page: Page, key: string, value: string) => page.addInitScript(([k, v]) => window.localStorage.setItem(k!, v!), [key, value]);
const overflow = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
const golds = (page: Page) => page.locator('main .bg-gold:visible');
const member = (page: Page, code: string) => page.locator(`[data-member="${code}"]`);

test('a sealed working group opens with its members as tiles: state in a shape and a word, last run, next run', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/playbooks/PB-0003');
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('موشن‌گرافی روزانه‌ی پرو-چارت');
    await expect(page.getByTestId('group-header').locator('[data-state-word="on"]')).toHaveText('مُهر شده');
    // The members come first, before the routines and the definition.
    const members = page.getByLabel('شرکت‌های عضو');
    await expect(members.locator('[data-member]')).toHaveCount(2);
    const y = async (sel: string) => (await page.locator(sel).first().boundingBox())!.y;
    expect(await y('[data-member]')).toBeLessThan(await y('[data-testid="routine-runs"]'));
    expect(await y('[data-testid="routine-runs"]')).toBeLessThan(await y('[data-testid="group-definition"]'));
    const pc = member(page, 'PC');
    await expect(pc.locator('[data-member-state="on"]')).toHaveText('فعال');
    await expect(pc.locator('[data-member-runs]')).toContainText('آخرین نوبت');
    await expect(pc.locator('[data-member-runs]')).toContainText('انجام شد');
    await expect(pc.locator('[data-member-runs]')).toContainText(/نوبت بعد .+ 07:00/);
    await expect(pc.locator('[data-member-runs] [data-when-at] bdi')).toHaveText('07:00');
    // Nothing of it runs now: no work line.
    await expect(pc.locator('[data-member-head]')).not.toHaveAttribute('data-running', '');
    await expect(pc.locator('[data-loop="band"]')).toHaveCount(0);
    // A sealed group's page has no full gold: giving it on and retiring it are quiet.
    await expect(golds(page)).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'به شرکت دیگر بده' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'بازنشسته کن' })).toBeVisible();
    await expect(page.getByTestId('group-header')).not.toContainText('·');
  });
});

test('a member that stands still says why in one line, and «راه بینداز» starts it again', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/playbooks/PB-0003');
    const fx = member(page, 'FX');
    await expect(fx.locator('[data-member-state="paused"]')).toHaveText('ایستاده');
    const still = fx.locator('[data-member-still]');
    await expect(still).toContainText('سه نوبت پشت هم بسته‌ای تحویل نشد؛ کارگروه در این شرکت ایستاد.');
    await expect(fx.locator('[data-member-runs]')).not.toContainText('نوبت بعد');
    const start = still.getByRole('button', { name: 'راه بینداز' });
    await expect(start).not.toHaveClass(/bg-gold/);
    await start.click();
    await expect(page.getByText('کارگروه در کوینه‌پرو اف‌ایکس دوباره راه افتاد.')).toBeVisible();
    await expect(fx.locator('[data-member-state="on"]')).toHaveText('فعال');
    await expect(fx.locator('[data-member-still]')).toHaveCount(0);
    await expect(fx.locator('[data-member-runs]')).toContainText('نوبت بعد');
  });
});

test('while something of a member runs, its tile says «در کار» and carries the silver work line', async ({ page }) => {
  await flag(page, 'hq.e2e.group-run', '1');
  await clean(page, async () => {
    await page.goto('/playbooks/PB-0003');
    const pc = member(page, 'PC');
    await expect(pc.locator('[data-member-head]')).toHaveAttribute('data-running', '');
    await expect(pc.locator('[data-member-state="on"]')).toHaveText('در کار');
    await expect(pc.locator('[data-loop="band"]')).toHaveCount(1);
    await expect(member(page, 'FX').locator('[data-loop="band"]')).toHaveCount(0);
    // The run in the queue is the last of the routine's dots, a ring.
    const dots = page.getByTestId('routine-runs').getByTestId('run-dots').locator('[data-dot]');
    await expect(dots).toHaveCount(7);
    await expect(dots.last()).toHaveAttribute('data-dot', 'queued');
  });
});

test('each routine: when it runs, who does it, its last seven runs as dots (each state its own shape) and its next turn', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/playbooks/PB-0003');
    const row = page.getByTestId('routine-runs').locator('[data-routine-run="daily"]');
    await expect(row).toContainText('موشن‌گرافی روز');
    await expect(row).toContainText('هر روز 07:00');
    await expect(row).toContainText('سازنده‌ی موشن‌گرافی');
    await expect(row).toContainText(/نوبت بعد .+ 07:00/);
    const dots = row.getByTestId('run-dots');
    await expect(dots).toHaveAttribute('aria-label', 'موشن‌گرافی روز: ۷ نوبت آخر، ۴ ناموفق');
    await expect(dots.locator('[data-dot]')).toHaveCount(7);
    await expect(dots.locator('[data-dot="failed"]')).toHaveCount(4);
    await expect(dots.locator('[data-dot="done"]')).toHaveCount(3);
    // A failed run is a square, a done one a dot: the state is never a colour alone.
    await expect(dots.locator('[data-dot="failed"]').first()).toHaveClass(/rounded-\[2px\]/);
    await expect(dots.locator('[data-dot="done"]').first()).toHaveClass(/rounded-full/);
    // A routine that ran twice shows two, and the rest empty.
    await page.goto('/playbooks/PB-0002');
    const weekly = page.getByTestId('routine-runs').getByTestId('run-dots');
    await expect(weekly).toHaveAttribute('aria-label', 'نوشتن مقاله‌ی هفته: ۲ نوبت آخر، همه بی‌خطا');
    await expect(weekly.locator('[data-dot="none"]')).toHaveCount(5);
  });
});

test('what the group is folds under «تعریف کارگروه», with what it has in one line', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/playbooks/PB-0003');
    const fold = page.getByTestId('group-definition');
    await expect(fold.locator('summary')).toContainText('تعریف کارگروه');
    await expect(fold.locator('summary')).toContainText('۲ جایگاه');
    await expect(fold.locator('summary')).toContainText('۱ روال');
    await expect(fold.locator('summary')).toContainText('۱ اتصال');
    await expect(fold.getByLabel('جایگاه‌ها')).toBeHidden();
    await fold.locator('summary').click();
    await expect(fold.getByLabel('جایگاه‌ها')).toContainText('سازنده‌ی موشن‌گرافی');
    await expect(fold.getByLabel('قانون‌ها')).toBeVisible();
    // A connection is said by its Persian name.
    await expect(fold.getByLabel('اتصال‌ها')).toContainText('اینستاگرام');
    await expect(fold.getByLabel('اتصال‌ها')).not.toContainText('instagram');
  });
});

test('a member\'s settings are one block: «انتشار خودکار» a silver switch with its line, the narrator, the ledger', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/playbooks/PB-0003');
    const block = member(page, 'PC').locator('[data-member-settings]');
    await expect(block.locator('> div')).toHaveCount(3);
    const standing = block.locator('[data-standing="PC"]');
    await expect(standing.locator('[data-standing-line]')).toHaveText('خودکار، بهترین ساعت 19:00، @pro.chart');
    await expect(standing.locator('[data-standing-line] bdi').first()).toHaveText('19:00');
    const sw = standing.getByRole('switch', { name: 'انتشار خودکار PC' });
    await expect(sw).toBeChecked();
    await expect(sw).not.toHaveClass(/gold/);
    await expect(block.locator('[data-narrator="PC"] [data-narrator-line]')).toHaveText('Charon، آرام و مطمئن');
    await expect(block.locator('[data-ledger="PC"] [data-ledger-counts]')).toHaveText('۴۲ موضوع، ۴۰ نمونه');
    // The hairline between facts, never «·» beside a digit.
    await expect(block).not.toContainText('·');
    // «تنظیم» opens the hour and «بهترین ساعت، خودکار» in place, both silver; its «ذخیره» is quiet.
    await standing.getByRole('button', { name: 'تنظیم' }).click();
    await expect(standing.getByTestId('best-hour').getByRole('switch', { name: 'بهترین ساعت، خودکار' })).toBeChecked();
    await expect(standing.getByLabel('ساعت انتشار')).toHaveValue('18:30');
    await expect(standing.getByRole('button', { name: 'ذخیره' })).not.toHaveClass(/bg-gold/);
    await expect(golds(page)).toHaveCount(0);
  });
});

test('the ledger, the narrator and «به شرکت دیگر بده» are the one spring sheet, each with its act in its decision bar', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/playbooks/PB-0003');
    await page.getByRole('button', { name: 'دفتر موضوع‌های پرو-چارت' }).click();
    const ledger = page.getByTestId('ledger-sheet');
    await expect(ledger).toHaveAttribute('data-spring-sheet');
    await expect(ledger.getByTestId('decision-bar').getByRole('button', { name: 'افزودن' })).toBeDisabled();
    // The field to add is in reach under the list, however long the list is.
    await expect(ledger.getByLabel('موضوعی که قبلاً گفته‌ایم')).toBeInViewport();
    await ledger.getByLabel('موضوعی که قبلاً گفته‌ایم').fill('واگرایی در مکدی');
    await expect(ledger.locator('.bg-gold:visible')).toHaveText(['افزودن']);
    await page.keyboard.press('Escape');
    await expect(ledger).toHaveCount(0);
    await page.getByRole('button', { name: 'گوینده‌ی محتوای پرو-چارت' }).click();
    const narrator = page.getByTestId('narrator-sheet');
    await expect(narrator).toHaveAttribute('data-spring-sheet');
    await expect(narrator.getByRole('radio', { name: /Charon/ })).toHaveAttribute('aria-checked', 'true');
    await expect(narrator.getByRole('radio', { name: /Charon/ })).not.toHaveClass(/gold/);
    await expect(narrator.getByTestId('decision-bar').getByRole('button', { name: 'ثبت' })).toBeEnabled();
    await page.keyboard.press('Escape');
    await page.getByRole('button', { name: 'به شرکت دیگر بده' }).click();
    const give = page.getByTestId('apply-sheet');
    await expect(give).toHaveAttribute('data-spring-sheet');
    await expect(give.getByTestId('decision-bar').getByRole('button', { name: 'بده', exact: true })).toBeDisabled();
    await give.getByRole('switch', { name: 'بدون تغییر' }).click();
    await expect(give.getByTestId('decision-bar').getByRole('button', { name: 'عضوش کن' })).toBeDisabled();
    await expect(give.getByTestId('decision-bar').getByRole('button', { name: 'بعداً' })).toBeEnabled();
  });
});

test('a draft: «مُهر کارگروه» is in the decision bar with what it starts in one line; one tap seals it, with no fingerprint', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/playbooks/PB-0001');
    await expect(page.getByTestId('group-header').locator('[data-state-word="wait"]')).toHaveText('پیش‌نویس');
    const bar = page.getByTestId('decision-bar');
    await expect(bar.getByRole('button')).toHaveText(['مُهر کارگروه', 'ذخیره']);
    await expect(bar.locator('[data-decision-context]')).toContainText('۳ جایگاه، ۳ روال، ۱ اتصال');
    await expect(bar.locator('[data-decision-context]')).toContainText('با مُهر، روال‌ها شروع میشوند');
    await expect(bar.getByRole('button', { name: 'ذخیره' })).toBeDisabled();
    await expect(golds(page)).toHaveText(['مُهر کارگروه']);
    // A seat taken away is counted at once, and the seal will save it first.
    await page.getByRole('button', { name: 'مسئول انتشار را بردار' }).click();
    await expect(bar.locator('[data-decision-context]')).toContainText('۲ جایگاه، ۲ روال، ۱ اتصال');
    await expect(bar.locator('[data-decision-context]')).toContainText('مُهر اول تغییرهایت را ذخیره میکند');
    await expect(bar.getByRole('button', { name: 'ذخیره' })).toBeEnabled();
    await bar.getByRole('button', { name: 'مُهر کارگروه' }).click();
    // No second card, no dialog, no passkey: it is sealed and its first member is there.
    await expect(page.getByText('مُهر شد؛ از نوبت بعد خودش میسازد و خودکار منتشر میکند.')).toBeVisible();
    await expect(page.getByRole('dialog')).toHaveCount(0);
    await expect(page.getByTestId('group-header').locator('[data-state-word="on"]')).toHaveText('مُهر شده');
    await expect(member(page, 'TY')).toBeVisible();
    await expect(page.getByTestId('decision-bar')).toHaveCount(0);
  });
});

test('the library: each working group a card with its platform, its members and where it came from; a draft carries the edge', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/playbooks');
    const draft = page.locator('section[data-state="draft"] [data-playbook]');
    await expect(draft).toHaveClass(/hq-edge/);
    await expect(draft).toContainText('اینستاگرام');
    await expect(draft).toContainText('از تریدیار');
    const sealed = page.locator('section[data-state="sealed"] [data-playbook]');
    await expect(sealed).toHaveCount(2);
    await expect(sealed.first()).not.toHaveClass(/hq-edge/);
    await expect(page.locator('[data-playbook]').first()).not.toContainText('·');
    await expect(golds(page)).toHaveCount(0);
  });
});

test('the growth group wears the same look: members as tiles, routines with dots and a silver switch, the seats under «تعریف کارگروه»', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/groups');
    const cardOf = page.getByRole('link', { name: 'کارگروه تولید محتوا و انتشار' });
    await expect(cardOf).toContainText('۶ جایگاه');
    await expect(cardOf).toContainText('۵ روال');
    await expect(cardOf).toContainText('۳ شاخص');
    await expect(cardOf).not.toContainText('·');
    await expect(cardOf.locator('[data-state-word="on"]')).toHaveText('روشن');
    await cardOf.click();
    await expect(page.getByRole('heading', { level: 1, name: 'تولید محتوا و انتشار' })).toBeVisible();
    await expect(page.locator('[data-member]')).toHaveCount(3);
    await expect(member(page, 'TY').locator('[data-member-state="on"]')).toHaveText('فعال');
    await expect(member(page, 'TY').locator('[data-member-runs]')).toContainText('نوبت بعد');
    await expect(member(page, 'PC').locator('[data-member-still]')).toContainText('این شرکت در کارگروه ایستاده است');
    const routine = page.getByLabel('روال‌ها', { exact: true }).locator('[data-routine="morning_numbers"]');
    await expect(routine.getByTestId('run-dots').locator('[data-dot]')).toHaveCount(7);
    await expect(routine.getByRole('switch')).toBeChecked();
    await expect(page.getByLabel('روال‌ها', { exact: true }).locator('[data-routine="weekly_experiment"]')).toContainText('ایستاده');
    const fold = page.getByTestId('group-definition');
    await expect(fold.getByLabel('جایگاه‌ها')).toBeHidden();
    await fold.locator('summary').click();
    await expect(fold.getByLabel('جایگاه‌ها').getByText('خالی').first()).toBeVisible();
    await expect(golds(page)).toHaveCount(0);
  });
});

test('@phone the working group\'s header folds to its title on scroll, and its pages fit a phone', async ({ page }) => {
  await page.setViewportSize({ width: 400, height: 860 });
  await clean(page, async () => {
    await page.goto('/playbooks/PB-0003');
    const header = page.getByTestId('group-header');
    await expect(member(page, 'FX')).toBeVisible();
    await expect(header).not.toHaveAttribute('data-stuck', '');
    await expect(header.getByRole('button', { name: 'به شرکت دیگر بده' })).toBeVisible();
    expect(await overflow(page)).toBeLessThanOrEqual(0);
    await page.evaluate(() => window.scrollTo(0, 700));
    await expect(header).toHaveAttribute('data-stuck', '');
    await expect(header.getByRole('heading', { level: 1 })).toBeInViewport();
    await expect(header.locator('[data-state-word]')).toBeInViewport();
    await expect(header.getByRole('button', { name: 'به شرکت دیگر بده' })).toBeHidden();
    for (const path of ['/playbooks/PB-0001', '/playbooks', '/groups', '/groups/content']) {
      await page.goto(path);
      await expect(page.getByRole('heading', { level: 1 }), path).toBeVisible();
      expect(await overflow(page), path).toBeLessThanOrEqual(0);
    }
    // A draft's bar stays in reach, and the round command button never covers its actions.
    await page.goto('/playbooks/PB-0001');
    const bar = page.getByTestId('decision-bar');
    await expect(bar).toBeInViewport();
    const orb = (await page.locator('[data-command-button]').boundingBox())!;
    const box = (await bar.boundingBox())!;
    expect(orb.y + orb.height).toBeLessThanOrEqual(box.y + 1);
  });
});
