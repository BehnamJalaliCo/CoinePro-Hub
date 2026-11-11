import { expect, test, type Page } from '@playwright/test';
import { clean, openDetails } from './support';

// ⟨1.22⟩ Contract §40: a session remembers («تا اینجا») and becomes a playbook, a working group the owner can seal and give to any company or
// platform. The demo holding has a draft (from F-0007), a sealed playbook with its first member (from F-0006), and memory text on three sessions.

const REF = /\bPB-\d{3,}\b/;
async function noRefs(page: Page) {
  const text = await page.locator('body').innerText();
  expect(text.match(REF)?.[0] ?? null, `a playbook ref is printed on ${page.url()}`).toBeNull();
}

test('the details drawer shows «تا اینجا» (folded Markdown) and makes a playbook whose card lands in the chat', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/s/F-0007');
    const sheet = await openDetails(page);
    const memory = sheet.getByLabel('تا اینجا', { exact: true });
    await expect(memory).toBeVisible();
    // Folded first; opening it renders the Markdown (a list, bold text).
    await expect(memory.getByRole('listitem')).toHaveCount(0);
    await memory.getByRole('button', { name: /تا اینجا/ }).click();
    await expect(memory.getByRole('listitem').first()).toBeVisible();
    await expect(memory).toContainText('ChatGPT');
    await sheet.getByRole('button', { name: 'کارگروه از این جلسه بساز' }).click();
    await expect(page.getByText('پیش‌نویس کارگروه ساخته شد')).toBeVisible();
    // The drawer closes and the card is in the chat: title, platform, seats, routines in plain times, rules; open and seal.
    const card = page.locator('section[data-kind="playbook"]').last();
    await expect(card).toBeVisible();
    await expect(card).toContainText('کارگروه از این جلسه');
    await expect(card.getByLabel('جایگاه‌ها')).toContainText('نویسنده');
    await expect(card.getByLabel('روال‌ها')).toContainText('هر روز 09:00');
    await expect(card.getByLabel('قانون‌ها')).toContainText('هیچ چیز بدون تأیید');
    await expect(card.getByRole('link', { name: 'باز کن' })).toBeVisible();
    await noRefs(page);
  });
});

test('the card seals the draft with one tap and the pill turns «مُهر شده»', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/s/F-0007');
    await (await openDetails(page)).getByRole('button', { name: 'کارگروه از این جلسه بساز' }).click();
    const card = page.locator('section[data-kind="playbook"]').last();
    await expect(card.getByText('پیش‌نویس', { exact: true })).toBeVisible();
    await card.getByRole('button', { name: 'مُهر کن' }).click();
    await expect(card).toHaveAttribute('data-state', 'sealed');
    await expect(card.getByText('مُهر شده', { exact: true })).toBeVisible();
    await expect(card.getByRole('button', { name: 'مُهر کن' })).toHaveCount(0);
  });
});

test('a draft: edit lightly (title, a seat and a rule removed, a routine brief), save, seal; the sealed page lists its member', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/playbooks/PB-0001');
    await expect(page.getByRole('heading', { level: 1 })).toContainText('ریلز روزانه');
    await expect(page.getByText('پیش‌نویس', { exact: true }).first()).toBeVisible();
    await expect(page.getByLabel('جایگاه‌ها').getByLabel('کمک‌ها').first()).toContainText('جی‌پی‌تی');
    await expect(page.getByLabel('روال‌ها')).toContainText('هر شنبه و سه‌شنبه 18:30');
    await page.getByLabel('عنوان', { exact: true }).fill('ریلز روزانه‌ی تریدیار');
    await page.getByRole('button', { name: 'مسئول انتشار را بردار' }).click();
    // Its routines go with the seat (the review was the publisher's).
    await expect(page.locator('[data-routine="review"]')).toHaveCount(0);
    await page.getByRole('button', { name: 'قانون 2 را بردار' }).click();
    await page.getByLabel('شرح پیدا کردن موضوع روز').fill('موضوع را فقط از اخبار همان روز بردار.');
    await page.getByRole('button', { name: 'ذخیره', exact: true }).click();
    await expect(page.getByText('ذخیره شد.')).toBeVisible();
    await expect(page.getByRole('heading', { level: 1 })).toContainText('ریلز روزانه‌ی تریدیار');
    await expect(page.locator('[data-seat="publisher"]')).toHaveCount(0);
    await expect(page.getByLabel('شرح پیدا کردن موضوع روز')).toHaveValue('موضوع را فقط از اخبار همان روز بردار.');
    // ⟨0.19.9⟩ §45 an Instagram working group is sealed with the owner's standing word, on (he asked for it automatic from day two)
    const standing = page.getByTestId('standing');
    await expect(standing.getByLabel('انتشار خودکار')).toBeChecked();
    await standing.getByRole('button', { name: 'استوری هم بشود' }).click();
    // ⟨1.0.1⟩ The seal is the page's one act, in its decision bar (the look, C3.4).
    await page.getByTestId('decision-bar').getByRole('button', { name: 'مُهر کارگروه' }).click();
    await expect(page.getByText('مُهر شد؛ از نوبت بعد خودش میسازد و خودکار منتشر میکند.')).toBeVisible();
    await expect(page.getByLabel('شرکت‌های عضو')).toContainText('تریدیار');
    const mine = page.locator('[data-standing="TY"]');
    await expect(mine).toContainText('خودکار');
    await expect(mine).toContainText('@tradeyar');
    await expect(mine).toContainText('استوری هم');
    // he takes his word back with one tap, and gives it again
    // (the box follows the hub's answer, so it is clicked, not «checked»)
    await mine.getByLabel('انتشار خودکار TY').click();
    await expect(page.getByText('از این به بعد هر خروجی منتظر تأیید تو است.')).toBeVisible();
    await expect(mine).toContainText('هر بار بپرس');
    await expect(mine.getByLabel('انتشار خودکار TY')).not.toBeChecked();
    await mine.getByLabel('انتشار خودکار TY').click();
    await expect(page.getByText('از نوبت بعد خودکار منتشر میشود.')).toBeVisible();
    await expect(mine.getByLabel('انتشار خودکار TY')).toBeChecked();
    // ⟨0.20.0⟩ §46 the hour each day's package goes out at: «تنظیم», Persian digits taken as they are typed
    await mine.getByRole('button', { name: 'تنظیم' }).click();
    await mine.getByLabel('ساعت انتشار').fill('25:00');
    await expect(mine.getByText('ساعت را به شکل ۱۸:۳۰ بنویس.')).toBeVisible();
    await expect(mine.getByRole('button', { name: 'ذخیره' })).toBeDisabled();
    await mine.getByLabel('ساعت انتشار').fill('۱۸:۳۰');
    await mine.getByRole('button', { name: 'ذخیره' }).click();
    await expect(mine).toContainText('ساعت 18:30');
    await expect(mine.getByLabel('ساعت انتشار')).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'به شرکت دیگر بده' })).toBeVisible();
    await noRefs(page);
  });
});

test('a sealed playbook given to another company opens that company\'s new session, with «از کارگروه …» in its header', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/playbooks/PB-0002');
    await expect(page.getByLabel('شرکت‌های عضو')).toContainText('اف‌ایکس');
    await page.getByRole('button', { name: 'به شرکت دیگر بده' }).click();
    const dialog = page.getByRole('dialog', { name: 'به شرکت دیگر بده' });
    await expect(dialog).toBeVisible();
    await dialog.getByLabel('شرکت', { exact: true }).selectOption({ label: 'پرو-چارت' });
    await dialog.getByLabel('پلتفرم', { exact: true }).selectOption({ label: 'یوتیوب' });
    await dialog.getByLabel('یادداشت').fill('لحن پرو-چارت فنی‌تر است.');
    await dialog.getByRole('button', { name: 'بده', exact: true }).click();
    await expect(page).toHaveURL(/\/s\/F-\d+$/);
    await expect(page.locator('[data-from-playbook]')).toContainText('از کارگروه «مقاله‌ی هفتگی سئو»');
    // The owner's first turn is the playbook as Markdown, with his words about the company and the platform.
    const talk = page.getByLabel('گفتگو', { exact: true });
    await expect(talk).toContainText('پرو-چارت روی یوتیوب پیاده کن');
    await expect(talk).toContainText('لحن پرو-چارت فنی‌تر است.');
    await noRefs(page);
  });
});

test('«بدون تغییر» makes the company a member at once, no session; retiring stops the group', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/playbooks/PB-0002');
    await page.getByRole('button', { name: 'به شرکت دیگر بده' }).click();
    const dialog = page.getByRole('dialog', { name: 'به شرکت دیگر بده' });
    await dialog.getByLabel('شرکت', { exact: true }).selectOption({ label: 'تریدیار' });
    await dialog.getByLabel('بدون تغییر').check();
    await dialog.getByRole('button', { name: 'عضوش کن' }).click();
    await expect(page.getByText('تریدیار عضو کارگروه شد.')).toBeVisible();
    await expect(page).toHaveURL(/\/playbooks\/PB-0002$/);
    await expect(page.getByLabel('شرکت‌های عضو')).toContainText('تریدیار');
    await page.getByRole('button', { name: 'بازنشسته کن' }).click();
    await page.getByRole('dialog').getByRole('button', { name: 'بازنشسته کن' }).click();
    await expect(page.getByText('بازنشسته', { exact: true }).first()).toBeVisible();
    await expect(page.getByRole('button', { name: 'به شرکت دیگر بده' })).toHaveCount(0);
  });
});

test('the library groups playbooks by state with title, platform, members and the company they came from; the nav and the office lead to it', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/');
    await page.getByLabel('جلسه‌ها', { exact: true }).getByRole('link', { name: 'کارگروه‌های آماده' }).click();
    await expect(page).toHaveURL(/\/playbooks$/);
    await expect(page.getByRole('heading', { level: 1 })).toContainText('کارگروه‌های آماده');
    const drafts = page.locator('section[data-state="draft"]');
    await expect(drafts.getByRole('link', { name: /ریلز روزانه/ })).toContainText('اینستاگرام');
    await expect(drafts.getByRole('link', { name: /ریلز روزانه/ })).toContainText('از تریدیار');
    const sealed = page.locator('section[data-state="sealed"]');
    await expect(sealed.getByRole('link', { name: /مقاله‌ی هفتگی سئو/ })).toContainText('سایت');
    await expect(sealed.getByRole('link', { name: /مقاله‌ی هفتگی سئو/ })).toContainText('۱ شرکت عضو');
    await expect(page.getByRole('navigation').getByRole('link', { name: 'کارگروه‌های آماده' }).first()).toBeVisible();
    await sealed.getByRole('link', { name: /مقاله‌ی هفتگی سئو/ }).click();
    await expect(page).toHaveURL(/\/playbooks\/PB-0002$/);
    await noRefs(page);
  });
});
