import { expect, test, type Page } from '@playwright/test';
import { clean } from './support';

// ⟨1.17⟩ Contract §34–§35: every order is a session the owner talks in; the home is his office; the canvas of the companies and their links.
// The demo holding (NEXT_PUBLIC_HQ_MOCK=1) has five sessions: his turn with a question (F-0008, step by step), a blocker with a one-tap fix
// (F-0007 the series seal, F-0005 the budget), one ready for his OK (F-0006, with a model in the room) and one closed and archived (F-0004).

const REF = /\b[A-Z]{1,3}-\d{3,}\b/;

/** What the owner can read on the page (closed folds are not text he sees), without a ref anywhere. */
async function noRefs(page: Page) {
  const text = await page.locator('body').innerText();
  expect(text.match(REF)?.[0] ?? null, `a ref is printed on ${page.url()}`).toBeNull();
}

test('the home is the office: sessions with his turn first, approvals, money, the canvas; no per-group block, no ref', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/');
    await expect(page.getByRole('heading', { level: 1 })).toContainText('مدیر کل');
    const sessions = page.getByLabel('جلسه‌ها', { exact: true });
    await expect(sessions.getByText('سه عنوان برای خبرنامه‌ی هفته‌ی تریدیار پیشنهاد بده')).toBeVisible();
    // His turn comes first.
    const first = sessions.locator('a[data-badge]').first();
    await expect(first).toHaveAttribute('data-badge', 'your_turn');
    await expect(first.getByText('نوبت تو')).toBeVisible();
    await expect(page.getByLabel('منتظر مُهر تو')).toBeVisible();
    await expect(page.getByLabel('پول')).toContainText('درآمد');
    await expect(page.getByLabel('بوم شرکت‌ها')).toBeVisible();
    await expect(page.getByLabel(/^شاخص‌های /)).toHaveCount(0);
    await noRefs(page);
  });
});

test('a word in the command bar becomes an order and opens its session', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/');
    await page.getByLabel('فرمان تازه', { exact: true }).fill('برای پرو-چارت یک پست درباره‌ی هشدار قیمت بنویس');
    await page.getByRole('button', { name: 'بفرست' }).first().click();
    await expect(page).toHaveURL(/\/s\/F-\d+$/);
    await expect(page.getByRole('heading', { level: 1 })).toContainText('هشدار قیمت');
    // The holder has greeted in the order's own talk.
    await expect(page.getByLabel('گفتگو', { exact: true }).getByText('فرمانت را گرفتم')).toBeVisible();
    await noRefs(page);
  });
});

test('his turn: the question is answered in place, the session moves on', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/s/F-0008');
    await expect(page.getByRole('heading', { level: 1 })).toContainText('خبرنامه');
    await expect(page.getByText('نوبت تو').first()).toBeVisible();
    const turn = page.getByLabel('نوبت تو', { exact: true });
    await expect(turn).toContainText('کدام عنوان بهتر است');
    const pace = page.getByRole('radiogroup', { name: 'روش کار' });
    await expect(pace.getByRole('radio', { name: 'با من' })).toHaveAttribute('aria-checked', 'true');
    await turn.getByLabel('جواب تو').fill('عنوان دوم، سه نکته برای حد ضرر');
    await turn.getByRole('button', { name: 'جواب بده' }).click();
    await expect(page.getByText('جوابت رفت.')).toBeVisible();
    await expect(page.getByLabel('نوبت تو', { exact: true })).toHaveCount(0);
    await expect(page.getByLabel('گفتگو', { exact: true }).getByText('عنوان دوم، سه نکته برای حد ضرر')).toBeVisible();
    // he switches to «do it all» at any time
    await pace.getByRole('radio', { name: 'خودکار' }).click();
    await expect(page.getByText('از این به بعد خودش تا آخر میرود.')).toBeVisible();
    await expect(pace.getByRole('radio', { name: 'خودکار' })).toHaveAttribute('aria-checked', 'true');
    await noRefs(page);
  });
});

test('the brief says what happened, what is going on and what is needed from him', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/s/F-0006');
    const brief = page.getByLabel('خلاصه‌ی جلسه');
    for (const t of ['چه شد', 'حالا چه', 'از تو چه']) await expect(brief.getByRole('heading', { name: t })).toBeVisible();
    await expect(page.getByText('آماده‌ی تأیید').first()).toBeVisible();
  });
});

test('blockers carry their one-tap fix, in words', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/s/F-0005');
    const blockers = page.getByLabel('گیرها');
    await expect(blockers.getByText('بودجه‌ی این فرمان تمام شد')).toBeVisible();
    await blockers.getByRole('button', { name: /واحد به بودجه|هزار واحد بده/ }).click();
    await expect(page.getByText('انجام شد.')).toBeVisible();
    await expect(page.getByLabel('گیرها')).toHaveCount(0);
    await noRefs(page);
  });
});

test('people and model seats join, are aimed at, and leave', async ({ page }) => {
  // The signed-out model is refused on purpose (409 with words), and «خطاخوان» keeps that.
  await clean(page, async () => {
    await page.goto('/s/F-0007');
    const who = page.getByLabel('کی در جلسه است');
    await who.getByRole('button', { name: 'مدل' }).click();
    // A model that is signed out says so in words and does not join.
    await who.getByRole('button', { name: 'دیپ‌سیک' }).click();
    await expect(page.getByText('دیپ‌سیک الان وارد نیست')).toBeVisible();
    await who.getByRole('button', { name: 'جمنای' }).click();
    await expect(who.getByText('جمنای', { exact: true }).first()).toBeVisible();
    // A person: the overseer.
    await who.getByRole('button', { name: 'آدم' }).click();
    await page.getByRole('dialog').getByRole('button', { name: 'ناظر کل' }).click();
    await expect(who.getByText('ناظر کل')).toBeVisible();
    // Aim a word at the model; it answers under its own name.
    const aim = page.getByRole('radiogroup', { name: 'به چه کسی میگویی' });
    await aim.getByRole('button', { name: 'جمنای' }).click();
    await page.getByLabel('پیام', { exact: true }).fill('نظر تو درباره‌ی ساعت انتشار چیست؟');
    await page.getByRole('button', { name: 'بفرست' }).last().click();
    await expect(page.locator('[data-by="player:gemini"]').first()).toBeVisible();
    // Everyone: each present participant says a line, then the holder sums up.
    await aim.getByRole('button', { name: 'نظر همه' }).click();
    await page.getByLabel('پیام', { exact: true }).fill('همه بگویید: هفته‌ای سه ریلز کافی است؟');
    await page.getByRole('button', { name: 'بفرست' }).last().click();
    await expect(page.locator('[data-by="overseer"]').first()).toBeVisible();
    // He sends the model away.
    await who.getByRole('button', { name: 'جمنای را بیرون ببر' }).click();
    await expect(who.getByText('جمنای', { exact: true })).toHaveCount(0);
    await noRefs(page);
  }, [/player_signed_out/]);
});

test('tasks: add, tick, drop', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/s/F-0007');
    const tasks = page.getByLabel('کارها', { exact: true });
    await expect(tasks.getByText('2 از 4 انجام شد')).toBeVisible();
    await tasks.getByLabel('کار تازه').fill('گزارش هفتگی را بفرست');
    await tasks.getByRole('button', { name: 'بیفزا' }).click();
    await expect(tasks.getByText('گزارش هفتگی را بفرست')).toBeVisible();
    await tasks.getByRole('checkbox', { name: /^گزارش هفتگی را بفرست/ }).click();
    await expect(tasks.getByText('3 از 5 انجام شد')).toBeVisible();
    await tasks.getByRole('button', { name: 'گزارش هفتگی را بفرست را کنار بگذار' }).click();
    await expect(tasks.getByText('گزارش هفتگی را بفرست')).toHaveCount(0);
  });
});

test('cards in a session: hire and delegate come from the talk, with plain links', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/s/F-0007');
    const box = page.getByLabel('پیام', { exact: true });
    await box.fill('یک مسئول انتشار استخدام کن');
    await page.getByRole('button', { name: 'بفرست' }).last().click();
    const card = page.getByLabel(/^کارت استخدام/).first();
    await expect(card).toBeVisible();
    await box.fill('متن ریلزها را به نویسنده بسپار');
    await page.getByRole('button', { name: 'بفرست' }).last().click();
    await expect(page.getByLabel(/^کارت سپردن کار/).first()).toBeVisible();
    await noRefs(page);
  });
});

test('confirm and close: the working group and the line come first, then the order is closed, archived and can be reopened or hidden', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/s/F-0006');
    await page.getByRole('button', { name: 'تأیید و بستن' }).click();
    const sheet = page.getByRole('dialog', { name: 'تأیید و بستن جلسه' });
    await expect(sheet.getByRole('button', { name: 'کارگروه راه بینداز' })).toBeVisible();
    await sheet.getByRole('button', { name: 'خط تولید راه بینداز' }).click();
    // The holder puts the line's card in the talk.
    await expect(page.getByLabel(/^کارت خط تولید/).first()).toBeVisible();
    await page.getByRole('button', { name: 'تأیید و بستن' }).click();
    await page.getByRole('dialog', { name: 'تأیید و بستن جلسه' }).getByLabel('یادداشت بستن').fill('خوب شد');
    await page.getByRole('dialog', { name: 'تأیید و بستن جلسه' }).getByRole('button', { name: 'تأیید و ببند' }).click();
    await expect(page.getByText('جلسه بسته و بایگانی شد.')).toBeVisible();
    await expect(page.getByText('بسته شد').first()).toBeVisible();
    await expect(page.getByText('این جلسه بسته شده و فقط خواندنی است')).toBeVisible();
    // The archive lists it; the open list does not. (The demo keeps its records in the page, so the way there is a click, not a reload.)
    await page.locator('header').getByRole('link', { name: 'جلسه‌ها' }).click();
    await expect(page.getByText('یک مقاله‌ی سئو برای FX')).toHaveCount(0);
    await page.getByRole('button', { name: /^بایگانی/ }).click();
    await expect(page.getByText('یک مقاله‌ی سئو برای FX')).toBeVisible();
    await expect(page.getByText('گزارش هزینه‌ی تبلیغات اکتبر')).toBeVisible();
    // Reopen: the session is open again and the composer is back.
    await page.getByText('یک مقاله‌ی سئو برای FX').click();
    await page.getByRole('button', { name: 'دوباره باز کن' }).click();
    await expect(page.getByRole('button', { name: 'تأیید و بستن' })).toBeVisible();
    await expect(page.getByLabel('پیام', { exact: true })).toBeVisible();
    // Hide: it leaves every list; nothing is deleted.
    await page.getByRole('button', { name: 'از فهرست بردار' }).click();
    await expect(page).toHaveURL(/\/s$/);
    await expect(page.getByText('یک مقاله‌ی سئو برای FX')).toHaveCount(0);
    await page.getByRole('button', { name: /^از فهرست برداشته‌شده/ }).click();
    await expect(page.getByText('یک مقاله‌ی سئو برای FX')).toBeVisible();
    await noRefs(page);
  });
});

test('the old order address leads to the session, and a talk bound to an order leads there too', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/orders/F-0007');
    await expect(page).toHaveURL(/\/s\/F-0007$/);
    await expect(page.getByRole('heading', { level: 1 })).toContainText('کلیپ');
  });
});

test('the canvas: companies on a circle, links by kind, a company panel, a new link, turning one off, dragging a company', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/');
    const canvas = page.getByTestId('canvas');
    await expect(canvas).toBeVisible();
    for (const c of ['HQ', 'TY', 'FX', 'PC']) await expect(canvas.locator(`[data-node="${c}"]`)).toBeVisible();
    // The three seeded links, each named by its kind.
    await expect(canvas.getByRole('button', { name: /ارتباط تریدیار با پرو-چارت: منتشر میکند/ })).toBeVisible();
    await expect(canvas.getByRole('button', { name: /کوینه‌پرو اف‌ایکس با تریدیار: پشتیبانی میکند، خاموش/ })).toBeVisible();

    // A company: its panel shows its sessions and links.
    await canvas.locator('[data-node="TY"]').click();
    const panel = page.getByRole('dialog', { name: 'تریدیار' });
    await expect(panel.getByText('جلسه‌های باز')).toBeVisible();
    await expect(panel.getByText('ریلزهای تریدیار را روی صفحه‌ی پرو-چارت هم منتشر میکند.')).toBeVisible();
    await page.keyboard.press('Escape');

    // Connect two companies: the form asks for the kind and the purpose.
    await page.getByRole('button', { name: 'ارتباط تازه' }).click();
    await canvas.locator('[data-node="PC"]').click();
    await canvas.locator('[data-node="FX"]').click();
    const form = page.getByRole('dialog', { name: 'ارتباط تازه' });
    await form.getByRole('radio', { name: 'میفروشد' }).or(form.getByRole('button', { name: 'میفروشد' })).first().click();
    await form.getByLabel('برای چه').fill('محصولات پرو-چارت را از طریق اف‌ایکس میفروشد.');
    await form.getByRole('button', { name: 'بساز' }).click();
    await expect(page.getByText('ارتباط ساخته شد.')).toBeVisible();
    await expect(canvas.getByRole('button', { name: /ارتباط پرو-چارت با کوینه‌پرو اف‌ایکس: میفروشد/ })).toBeVisible();

    // Turn a link off: nothing is deleted.
    await canvas.getByRole('button', { name: /ارتباط تریدیار با پرو-چارت: منتشر میکند/ }).click();
    await page.getByRole('dialog', { name: 'ارتباط دو شرکت' }).getByRole('button', { name: 'خاموشش کن' }).click();
    await expect(canvas.getByRole('button', { name: /ارتباط تریدیار با پرو-چارت: منتشر میکند، خاموش/ })).toBeVisible();

    // Drag a company to another place.
    const node = canvas.locator('[data-node="PC"]');
    const before = (await node.boundingBox())!;
    const area = (await canvas.boundingBox())!;
    await page.mouse.move(before.x + before.width / 2, before.y + before.height / 2);
    await page.mouse.down();
    await page.mouse.move(area.x + area.width * 0.2, area.y + area.height * 0.8, { steps: 10 });
    await page.mouse.up();
    await expect.poll(async () => Math.round(((await node.boundingBox())!.x - area.x) / area.width * 100)).toBeLessThan(30);
    await noRefs(page);
  });
});

test('nothing technical in the main menu: the office, sessions, cartable, companies, messages, outputs; the rest folded', async ({ page }) => {
  await page.goto('/');
  const main = page.getByRole('navigation', { name: 'ناوبری اصلی' }).first();
  for (const t of ['دفتر', 'جلسه‌ها', 'کارتابل', 'شرکت‌ها', 'پیام‌ها', 'خروجی‌ها']) await expect(main.getByRole('link', { name: t })).toBeVisible();
  await expect(main.getByRole('link', { name: 'دیده‌بان' })).toHaveCount(0);
  await expect(page.locator('nav[aria-label="فنی"]').getByRole('link', { name: 'دیده‌بان', includeHidden: true })).toBeAttached();
});

test('the sessions list: his turn first, a badge in words for each, the archive', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/s');
    const rows = page.getByRole('link').filter({ has: page.locator('[data-badge]') });
    void rows;
    const list = page.locator('a[data-badge]');
    await expect(list.first()).toHaveAttribute('data-badge', 'your_turn');
    await expect(page.locator('a[data-badge="ready"]').first()).toBeVisible();
    await noRefs(page);
  });
});

test('@phone the office and a session fit a phone', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/');
    await expect(page.getByTestId('canvas')).toBeVisible();
    const w = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(w).toBeLessThanOrEqual(1);
    await page.goto('/s/F-0008');
    await expect(page.getByLabel('گفتگو', { exact: true })).toBeVisible();
    const w2 = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(w2).toBeLessThanOrEqual(1);
  });
});
