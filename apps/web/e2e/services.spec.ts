import { expect, test } from '@playwright/test';
import { clean } from './support';

// ⟨1.20⟩ Contract §38.3 «سرویس‌ها»: a switch for each optional service, the free memory, and a refusal that offers one tap.
// The demo budget refuses «ساخت ویدیو و کاور» until the newsletter (the largest one on) is off.

test('services: memory bar, a quick switch, and a refused switch that offers «turn the newsletter off»', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/services');
    await expect(page.getByRole('heading', { level: 1 })).toContainText('سرویس‌ها');
    await expect(page.getByLabel('حافظه', { exact: true })).toContainText('آزاد');
    await expect(page.getByRole('progressbar', { name: 'حافظه‌ی گرفته‌شده از بودجه' })).toBeVisible();
    const row = (k: string) => page.locator(`li[data-service="${k}"]`);
    // Core services are listed, without a switch.
    await expect(row('api').getByRole('switch')).toHaveCount(0);

    // A small one fits: pending, then «روشن شد».
    await row('mcp').getByRole('switch').click();
    await expect(row('mcp')).toHaveAttribute('data-state', 'pending');
    await expect(page.getByText('روشن شد')).toBeVisible();
    await expect(row('mcp').getByRole('switch')).toHaveAttribute('aria-checked', 'true');

    // The big one does not: the dialog names who holds the room, with one button.
    await row('media').getByRole('switch').click();
    const dlg = page.getByRole('dialog', { name: 'جا نیست؛ این‌ها جا را گرفته‌اند' });
    await expect(dlg.getByLabel('سرویس‌هایی که جا را گرفته‌اند').getByText('خبرنامه', { exact: true })).toBeVisible();
    await dlg.getByRole('button', { name: 'خبرنامه را خاموش کن و ساخت ویدیو و کاور را روشن کن' }).click();
    await expect(row('media').getByRole('switch')).toHaveAttribute('aria-checked', 'true', { timeout: 20_000 });
    await expect(row('newsletter').getByRole('switch')).toHaveAttribute('aria-checked', 'false');
  });
});

test('the office and the technical menu lead to the services page', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/');
    await page.getByLabel('پول').getByRole('link', { name: 'سرویس‌های هاب' }).click();
    await expect(page).toHaveURL(/\/services$/);
  });
});
