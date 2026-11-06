import { expect, test } from '@playwright/test';
import { clean } from './support';

// ⟨1.17⟩ The owner reads plain short Persian: no ref (W-000153, F-0007, CV-0012, D-000085, O-000061), no persona key (role@CODE) and no
// «توکن» anywhere on the pages he lives in. What a fold keeps closed is not text he sees, so the check reads the visible text (innerText).

const OWNER_PAGES = [
  '/', '/s', '/s/F-0008', '/s/F-0007', '/s/F-0006', '/s/F-0005', '/s/F-0004', '/cartable', '/cartable?ref=D-000085', '/companies', '/outputs',
  '/messages', '/talk', '/orders', '/notifications', '/work/W-000104', '/groups',
];

for (const path of OWNER_PAGES) {
  test(`${path} prints no ref, no code and no token`, async ({ page }) => {
    await clean(page, async () => {
      await page.goto(path);
      await expect(page.locator('h1').first()).toBeVisible();
      await page.waitForLoadState('networkidle');
      const text = await page.locator('body').innerText();
      expect(text.match(/\b[A-Z]{1,3}-\d{3,}\b/)?.[0] ?? null, `a ref is shown on ${path}`).toBeNull();
      expect(text.match(/\b[a-z_]+@[A-Z]{2,5}\b/)?.[0] ?? null, `a persona key is shown on ${path}`).toBeNull();
      expect(text, `the word «توکن» is shown on ${path}`).not.toMatch(/توکن/);
    });
  });
}
