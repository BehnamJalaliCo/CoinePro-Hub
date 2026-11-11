import { test } from '@playwright/test';
test('probe', async ({ page }) => {
  await page.setViewportSize({ width: 900, height: 560 });
  await page.goto('/s/F-0007');
  const talk = page.getByTestId('talk-scroll');
  await talk.locator('[data-by]').first().waitFor();
  await page.waitForTimeout(1500);
  await talk.evaluate((el) => {
    const w = window as unknown as { log: string[] }; w.log = [];
    const t0 = performance.now();
    const snap = (why: string) => w.log.push(`${Math.round(performance.now() - t0)} ${why} sh=${el.scrollHeight} st=${Math.round(el.scrollTop)} ch=${el.clientHeight}`);
    el.addEventListener('scroll', () => snap('scroll'));
    new ResizeObserver(() => snap('resize-inner')).observe(el.firstElementChild!);
    new ResizeObserver(() => snap('resize-frame')).observe(el);
    new MutationObserver((ms) => snap('mut ' + ms.length + ' ' + ms.map((m) => (m.target as Element).getAttribute?.('data-testid') ?? (m.target as Element).tagName).slice(0, 3).join(','))).observe(el, { childList: true, subtree: true, characterData: true });
  });
  await talk.evaluate((el) => el.scrollTo({ top: 0 }));
  await page.waitForTimeout(400);
  await page.getByRole('button', { name: /^برو به آخر گفتگو/ }).click();
  await page.waitForTimeout(6000);
  const log = await page.evaluate(() => (window as unknown as { log: string[] }).log);
  console.log(log.join('\n'));
});
