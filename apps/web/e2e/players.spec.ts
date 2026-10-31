import { expect, test } from '@playwright/test';

// ⟨1.9⟩ Contract §27.1 on the web, as the Android app's 0.9.0: «با کدام مدل؟» on a new order (substitutes' availability from
// /substitutes, the council and what it makes), and a voice order whose words name the player («با جمنای», «شورا»).

test('gives an order to the council of models for images, and its page says who plays it', async ({ page }) => {
  await page.goto('/orders');
  await page.getByRole('button', { name: 'فرمان تازه' }).first().click();
  const sheet = page.getByRole('dialog', { name: 'فرمان تازه' });
  await sheet.getByRole('button', { name: /تریدیار/ }).first().click();
  await sheet.getByRole('textbox').first().fill('بنر کمپین پاییز برای تلگرام');
  const players = sheet.getByRole('radiogroup', { name: 'با کدام مدل؟' });
  await expect(players.getByRole('radio', { name: 'خودکار' })).toHaveAttribute('aria-checked', 'true');
  await players.getByRole('radio', { name: 'شورای مدل‌ها' }).click();
  await expect(sheet.getByText(/Claude جمع‌بندی مینویسد/)).toBeVisible();
  await sheet.getByRole('button', { name: 'عکس', exact: true }).click();
  await sheet.getByRole('button', { name: 'فردا', exact: true }).click();
  await expect(sheet.getByText(/به وقت تهران$/)).toBeVisible();
  await sheet.getByRole('button', { name: 'بفرست' }).click();
  await page.getByRole('button', { name: 'پیگیری' }).click();
  await expect(page.getByText('شورای مدل‌ها: هر بازیکن عکس خودش را میسازد؛ یکی را تو انتخاب میکنی')).toBeVisible();
});

test('a written voice order that says «با جمنای» picks Gemini, and the owner can change it', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: 'فرمان صوتی' }).first().click();
  await page.getByRole('button', { name: 'به‌جایش مینویسم' }).click();
  await page.getByRole('textbox').last().fill('با جمنای یک خلاصه از بازار امروز بنویس برای تریدیار');
  const players = page.getByRole('radiogroup', { name: 'با کدام مدل؟' });
  await expect(page.getByText(/از گفتار شنیده شد: «با جمنای» ← Gemini/)).toBeVisible();
  await expect(players.getByRole('radio', { name: /^Gemini/ })).toHaveAttribute('aria-checked', 'true');
  await players.getByRole('radio', { name: 'Claude' }).click();
  await expect(page.getByText('· انتخاب تو جایش نشست')).toBeVisible();
  await page.getByRole('textbox').last().fill('شورا درباره‌ی قیمت‌گذاری بسته‌ی سالانه نظر بدهد');
  await expect(page.getByText(/از گفتار شنیده شد: «شورا» ← شورای مدل‌ها/)).toBeVisible();
});
