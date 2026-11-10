import { expect, test, type Page } from '@playwright/test';
import { clean } from './support';

// ⟨1.24⟩ Contract §42, design/LIVE_VIEWS.md: the 12 P0 live views over the demo holding. The demo's stream moves by itself (people change
// state, tokens tick, flows cross the hub, a server drops and comes back); these checks also drive it by hand through the demo's driver
// (`window.__hqLive.drive`), so each view is seen moving when it should. Pro-Chart is locked in the demo (its CEO stopped it).

async function drive(page: Page, ...what: string[]) {
  await page.waitForFunction(() => !!(window as unknown as { __hqLive?: unknown }).__hqLive);
  for (const w of what) await page.evaluate((x) => (window as unknown as { __hqLive: { drive: (w: string) => Promise<number> } }).__hqLive.drive(x), w);
}
const fast = { timeout: 4000, intervals: [40] };

test('GL-1: the header says the stream is live, in words', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/');
    const beacon = page.locator('[data-beacon]');
    await expect(beacon).toHaveAttribute('data-beacon', 'live');
    await expect(page.getByTitle('زنده')).toBeVisible();
  });
});

test('OF-1: the pulse of the office in one row, from the seed, glinting as it changes', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/');
    const pulse = page.getByTestId('office-pulse');
    // ⟨1.0.1⟩ Three figures in one row: who works, how many sessions are open, what waits for him; and when they were read.
    await expect(pulse.locator('[data-pulse]')).toHaveCount(3);
    for (const label of ['کار میکنند', 'جلسه‌ی باز', 'منتظر تو']) await expect(pulse.locator(`[data-pulse="${label}"]`)).toBeVisible();
    await expect(pulse.locator('[data-pulse-at]')).toContainText(/تا\s*\d{2}:\d{2}/);
    await expect(page.locator('body')).not.toContainText('سشن');
    // Seeded from the summary: no «—» once it has arrived; «کار میکنند» is n of all.
    await expect(pulse.locator('[data-pulse="کار میکنند"] [data-figure]')).toHaveAttribute('data-figure', /^\d+\/\d+$/);
    await expect(pulse.locator('[data-pulse="منتظر تو"] [data-figure]')).toHaveAttribute('data-figure', /^\d+$/);
    // People change state on the stream: a figure crossfades and its tahrir glints (silver: the agents' work).
    await drive(page, 'work', 'burst');
    await expect.poll(() => pulse.locator('[data-glint]').count(), { timeout: 15_000 }).toBeGreaterThan(0);
  });
});

test('MO-1: the token meter, four kinds against the daily budget, moving with each tick', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/treasury');
    const meter = page.getByTestId('token-meter');
    await expect(meter).toContainText('کنتور توکن · امروز');
    await expect(meter.locator('[data-mark]')).toHaveCount(3);
    await expect(meter.locator('[data-kind]')).toHaveCount(4);
    await expect(meter.getByRole('meter')).toHaveAttribute('aria-valuenow', /^\d+$/);
    const spent = meter.locator('[data-figure]').first();
    await expect(spent).toHaveAttribute('data-figure', /^\d+\.\d{2}$/);
    const before = await spent.getAttribute('data-figure');
    await drive(page, 'tokens');
    await expect.poll(() => spent.getAttribute('data-figure'), { timeout: 10_000 }).not.toBe(before);
    // On the owner's office the same meter speaks of spend (no «توکن», §34).
    await page.goto('/');
    await expect(page.getByTestId('token-meter')).toContainText('مصرف امروز');
  });
});

test('CO-1: a live card per company: people by state, servers, sessions, spend; locked hatched; a drop shows at once', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/');
    const list = page.getByTestId('live-companies');
    await expect(list.locator('[data-company-card]')).toHaveCount(3);
    await expect(list.locator('[data-company-card="PC"]')).toHaveAttribute('data-locked', 'true');
    for (const card of await list.locator('[data-company-card]').all()) expect(await card.locator('[data-dot]').count()).toBeLessThanOrEqual(12);
    const ty = list.locator('[data-company-card="TY"]');
    await expect(ty.locator('[data-servers]')).toHaveAttribute('data-servers', '1/1');
    await expect(ty.locator('[data-sessions]')).toContainText('جلسه');
    await drive(page, 'drop');
    await expect(ty.locator('[data-servers]')).toHaveAttribute('data-servers', '0/1');
    await expect(ty).toContainText('قطع');
    await drive(page, 'heal');
    await expect(ty.locator('[data-servers]')).toHaveAttribute('data-servers', '1/1');
  });
});

test('GL-2: the kill-switch band on every screen, for a company and for the holding', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/s');
    const band = page.getByTestId('kill-band');
    await expect(band).toHaveAttribute('data-scope', 'company');
    await expect(band).toContainText('پرو-چارت قفل است');
    await expect(band).toContainText('به دستور مدیرعامل');
    await drive(page, 'lock');
    await expect(band).toHaveAttribute('data-scope', 'holding');
    await expect(band).toContainText('هلدینگ قفل است');
    await expect(band).toContainText('به دستور تو');
    await drive(page, 'release');
    await expect(band).toHaveAttribute('data-scope', 'company');
  });
});

test('NO-1: an urgent alert is a banner that stays until seen; a card for the seal is a toast with a gold hairline', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/');
    await drive(page, 'urgent');
    const banner = page.getByTestId('urgent-banner');
    await expect(banner).toBeVisible();
    await expect(banner).toHaveAttribute('role', 'alert');
    await expect(banner).toContainText('دیسک سرور هاب از ۹۵٪ گذشت');
    await page.waitForTimeout(7000);
    await expect(banner).toBeVisible();
    await banner.getByRole('button', { name: 'دیدم' }).click();
    await expect(banner).toHaveCount(0);
    await drive(page, 'decision');
    const toast = page.getByTestId('decision-toast');
    await expect(toast).toContainText('تصمیم تازه');
    await expect(toast.getByRole('link', { name: 'کارتابل' })).toBeVisible();
  });
});

test('SS-1: every session row says when its last step was; a session that starts moving gets its badge and its band', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/s');
    const rows = page.locator('a[data-badge]');
    await expect(rows.first()).toBeVisible();
    await expect(page.locator('[data-stall]').first()).toContainText('آخرین قدم');
    await drive(page, 'moving');
    const row = page.locator('a[href="/s/F-0006"]');
    await expect(row).toHaveAttribute('data-badge', 'moving');
    await expect(row.locator('[data-live-badge="moving"]')).toContainText('در جریان');
    await expect(row.locator('[data-loop="band"]')).toHaveCount(1);
    await expect(row.locator('[data-stall="moving"]')).toBeVisible();
    // The header of a session has the same watch.
    await page.goto('/s/F-0007');
    await expect(page.locator('header [data-stall]')).toContainText('آخرین قدم');
  });
});

test('SE-1: the running step carries its arc and seconds; when it ends, the same line gets its tick', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/s/F-0007');
    const panel = page.getByTestId('live-work');
    await expect(panel).toHaveAttribute('data-state', 'working');
    const running = panel.locator('[data-line][data-state="running"]');
    await expect(running).toHaveCount(1);
    await expect(running.locator('[data-mark="running"] [data-line-secs]')).toHaveText(/^\d+s$/);
    const text = (await running.locator('span').nth(1).innerText()).trim();
    // The next beat ends it: the very same line (one line with these words) is now done, with its tick; one line runs again.
    const same = panel.locator('[data-line]', { hasText: text });
    await expect(same.first()).toHaveAttribute('data-state', 'done', { timeout: 15_000 });
    await expect(same).toHaveCount(1);
    await expect(same.locator('[data-mark="done"]')).toHaveCount(1);
    await expect(running).toHaveCount(1);
  });
});

test('PE-1: a person\'s state is a shape and a word, and it follows the stream', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/companies/TY?tab=people');
    const row = page.locator('tr', { has: page.locator('a[href="/employees/TY-GROWTH-01"]') });
    await expect(row.locator('[data-glyph]').first()).toBeVisible();
    await expect(row.locator('[data-person-word]')).toBeVisible();
    await drive(page, 'stuck');
    await expect(row.locator('[data-person-word]')).toHaveAttribute('data-person-word', 'stuck');
    await expect(row.locator('[data-person-word]')).toHaveText('گیر کرده');
    await expect(row.locator('[data-glyph="stuck"]').first()).toBeVisible();
  });
});

test('HM-1…3: the hub, every company and server from data; a drop breaks red with when, why and the fix; flows cross as particles', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/network');
    const map = page.getByTestId('holding-map');
    await expect(map).toHaveAttribute('data-view', 'map');
    await expect(map.getByRole('button', { name: 'هاب · ستاد' })).toBeVisible();
    await expect(map.locator('[data-company]')).toHaveCount(4);
    await expect(map.locator('[data-server]')).toHaveCount(4);
    await expect(map.locator('[data-company="PC"]')).toHaveAttribute('data-locked', 'true');
    await expect(map.locator('[data-locked-sector="PC"]')).toHaveCount(1);
    await expect(map.locator('[data-server]')).toHaveCount(4);
    // HM-3: the drop.
    await drive(page, 'drop');
    const srv = map.locator('[data-server="srv-ty-1"]');
    await expect(srv).toHaveAttribute('data-state', 'offline');
    await expect(map.locator('[data-node-edge="srv:srv-ty-1"]')).toHaveAttribute('data-runner', 'broken');
    const chip = map.locator('[data-break-chip="srv-ty-1"]');
    await expect(chip).toContainText('قطع');
    await expect(chip).toContainText('runner روی سرور ایستاده');
    await srv.click();
    const sheet = page.getByRole('dialog');
    for (const k of ['از کی', 'آخرین تماس سالم', 'چرا', 'چه چیزی معطل است', 'راه حل']) await expect(sheet.getByText(k, { exact: true })).toBeVisible();
    await expect(sheet).toContainText('hq-runner');
    await expect(sheet).not.toContainText('10.10.');
    await expect(sheet).not.toContainText('ty-web');
    await page.keyboard.press('Escape');
    await drive(page, 'heal');
    await expect(srv).toHaveAttribute('data-state', 'online');
    await expect(chip).toHaveCount(0);
    // HM-2: an order is gold from the seal; a request is silver through the hub.
    await drive(page, 'order');
    await expect.poll(() => map.locator('[data-particle="gold"]').count(), fast).toBeGreaterThan(0);
    await drive(page, 'request');
    await expect.poll(() => map.locator('[data-particle="silver"]').count(), fast).toBeGreaterThan(0);
  });
});

test('HM-2, rule 4: at most three particles on an edge; the rest fold into «×n»', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/network');
    const map = page.getByTestId('holding-map');
    await expect(map.locator('[data-company="TY"]')).toBeVisible();
    await page.waitForFunction(() => !!(window as unknown as { __hqLive?: unknown }).__hqLive);
    await page.evaluate(() => { const d = (window as unknown as { __hqLive: { drive: (w: string) => Promise<number> } }).__hqLive; for (let i = 0; i < 6; i++) void d.drive('order'); });
    const chip = map.locator('[data-chip="hub>TY"]');
    await expect(chip).toBeVisible();
    await expect(chip).toHaveText(/^×[4-9]$/);
    expect(await map.locator('[data-particle="gold"]').count()).toBeLessThanOrEqual(9);
  });
});

test('HM-8: the table shows every company and sorts', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/network?view=table');
    const map = page.getByTestId('holding-map');
    await expect(map).toHaveAttribute('data-view', 'table');
    const table = page.getByTestId('map-table');
    await expect(table.locator('[data-row]')).toHaveCount(4);
    await table.getByRole('button', { name: /شرکت/ }).click();
    await expect(table.locator('th').first()).toHaveAttribute('aria-sort', /descending|ascending/);
    await map.getByRole('radio', { name: 'نقشه' }).click();
    await expect(map).toHaveAttribute('data-view', 'map');
  });
});

test('rule 7: a hidden tab draws nothing; back on screen, a chip says how many events were applied without motion', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/network');
    const map = page.getByTestId('holding-map');
    await expect(map.locator('[data-company="TY"]')).toBeVisible();
    await page.evaluate(() => {
      Object.defineProperty(document, 'hidden', { configurable: true, get: () => true });
      Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'hidden' });
      document.dispatchEvent(new Event('visibilitychange'));
    });
    await drive(page, 'burst', 'order', 'request');
    await page.waitForTimeout(1500);
    expect(await map.locator('[data-particle]').count()).toBe(0);
    await page.evaluate(() => {
      delete (document as unknown as Record<string, unknown>).hidden;
      delete (document as unknown as Record<string, unknown>).visibilityState;
      document.dispatchEvent(new Event('visibilitychange'));
    });
    const away = page.locator('[data-away]').first();
    await expect(away).toBeVisible();
    await expect(away).toContainText('رویداد در نبودت');
    expect(Number(await away.getAttribute('data-away'))).toBeGreaterThan(20);
  });
});

test.describe('reduced motion (rule 8)', () => {
  test.use({ reducedMotion: 'reduce' });

  test('the map opens as its table; a particle becomes a tint on its edge and the «×n» chip; a loop is still with its word', async ({ page }) => {
    await clean(page, async () => {
      await page.goto('/network');
      const map = page.getByTestId('holding-map');
      await expect(map).toHaveAttribute('data-view', 'table');
      await map.getByRole('radio', { name: 'نقشه' }).click();
      await expect(map.locator('[data-company="TY"]')).toBeVisible();
      await drive(page, 'order');
      const chip = map.locator('[data-chip="hub>TY"]');
      await expect(chip).toHaveText('×1');
      await expect(map.locator('[data-node-edge="TY"]')).toHaveAttribute('data-tint', 'gold');
      expect(await map.locator('[data-particle]').count()).toBe(0);
      await page.goto('/s/F-0007');
      const running = page.getByTestId('live-work').locator('[data-line][data-state="running"]');
      await expect(running.locator('[data-mark="running"]')).toContainText('در حال انجام');
    });
  });
});

for (const path of ['/network', '/', '/companies', '/s']) {
  test(`${path} fits a phone with the live views, no sideways scroll @phone`, async ({ page }) => {
    await clean(page, async () => {
      await page.goto(path);
      await expect(page.locator('h1').first()).toBeVisible();
      await page.waitForLoadState('networkidle');
      if (path === '/network') await drive(page, 'drop');
      await page.waitForTimeout(800);
      const over = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(over).toBeLessThanOrEqual(0);
    });
  });
}
