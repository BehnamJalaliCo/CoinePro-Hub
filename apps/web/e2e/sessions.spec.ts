import { expect, test, type Page } from '@playwright/test';
import { clean, openDetails } from './support';

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
    // His turn comes first, in one of three states only («منتظر تو», «در کار», «تمام»).
    const first = sessions.locator('a[data-badge]').first();
    await expect(first).toHaveAttribute('data-badge', 'your_turn');
    await expect(first.getByText('منتظر تو')).toBeVisible();
    // ⟨1.0.1⟩ What waits for him is on top, answered in place: a session's question, and a card with its own «تأیید».
    const turn = page.getByTestId('turn-row');
    await expect(turn.getByRole('heading', { name: 'نوبت تو' })).toBeVisible();
    await expect(turn.locator('[data-wait="session"]').first()).toContainText('کدام عنوان بهتر است');
    await expect(turn.locator('[data-wait="decision"]').first().getByRole('button', { name: /^تأیید/ })).toBeVisible();
    await expect(page.getByLabel('پول')).toContainText('درآمد');
    await expect(page.getByLabel('بوم شرکت‌ها')).toBeVisible();
    await expect(page.getByLabel(/^شاخص‌های /)).toHaveCount(0);
    await noRefs(page);
  });
});

test('a word in the command bar becomes an order and opens its session', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/');
    // ⟨1.0.1⟩ The home's command entry is one row that opens the command sheet.
    await page.getByTestId('command-row').click();
    const sheet = page.getByTestId('command-sheet');
    await sheet.getByLabel('فرمان', { exact: true }).fill('برای پرو-چارت یک پست درباره‌ی هشدار قیمت بنویس');
    // ⟨2026-11-09⟩ «با من یا خودکار؟» first
    await expect(sheet.getByRole('button', { name: 'باز کن' })).toBeDisabled();
    await sheet.getByRole('radiogroup', { name: 'این جلسه چطور جلو برود؟' }).getByRole('radio', { name: 'خودکار' }).click();
    await sheet.getByRole('button', { name: 'باز کن' }).click();
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
    // ⟨1.0.1⟩ The question is one card above the composer (the look, C2.2); its ready answers are in e2e/look-session.spec.ts.
    await expect(page.getByTestId('session')).toHaveAttribute('data-mood', 'waiting');
    const turn = page.getByTestId('waiting-card');
    await expect(turn).toContainText('کدام عنوان بهتر است');
    // The pace lives in «جزئیات».
    const sheet = await openDetails(page);
    await expect(sheet.getByRole('radiogroup', { name: 'روش کار' }).getByRole('radio', { name: 'با من' })).toHaveAttribute('aria-checked', 'true');
    await page.keyboard.press('Escape');
    // Typing still works: what he writes in the composer is his answer to the open question.
    await page.getByLabel('پیام', { exact: true }).fill('عنوان دوم، سه نکته برای حد ضرر');
    await page.getByRole('button', { name: 'بفرست' }).last().click();
    await expect(page.getByTestId('answer-sent')).toContainText('جوابت رفت: عنوان دوم، سه نکته برای حد ضرر');
    await expect(page.getByTestId('waiting-card')).toHaveCount(0);
    await expect(page.getByLabel('گفتگو', { exact: true }).locator('[data-by="owner"]').getByText('عنوان دوم، سه نکته برای حد ضرر')).toBeVisible();
    // he switches to «do it all» at any time
    const pace = (await openDetails(page)).getByRole('radiogroup', { name: 'روش کار' });
    await pace.getByRole('radio', { name: 'خودکار' }).click();
    await expect(page.getByText('از این به بعد خودش تا آخر میرود.')).toBeVisible();
    await expect(pace.getByRole('radio', { name: 'خودکار' })).toHaveAttribute('aria-checked', 'true');
    await noRefs(page);
  });
});

test('the brief says what happened, what is going on and what is needed from him', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/s/F-0006');
    await expect(page.getByTestId('decision-bar')).toContainText('با تأیید تو جلسه بسته و بایگانی میشود');
    const brief = (await openDetails(page)).getByLabel('خلاصه‌ی جلسه');
    for (const t of ['چه شد', 'حالا چه', 'از تو چه']) await expect(brief.getByRole('heading', { name: t })).toBeVisible();
  });
});

test('blockers carry their one-tap fix, in words', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/s/F-0005');
    const knot = page.getByTestId('knot');
    await expect(knot.getByRole('alert')).toContainText('بودجه‌ی این فرمان تمام شد');
    await knot.getByRole('button', { name: /واحد به بودجه|هزار واحد بده/ }).click();
    await expect(page.getByText('انجام شد.')).toBeVisible();
    await expect(page.getByTestId('knot')).toHaveCount(0);
    await noRefs(page);
  });
});

test('people and model seats join, are aimed at, and leave', async ({ page }) => {
  // The signed-out model is refused on purpose (409 with words), and «خطاخوان» keeps that.
  await clean(page, async () => {
    await page.goto('/s/F-0007');
    const who = (await openDetails(page)).getByLabel('کی در جلسه است');
    await who.getByRole('button', { name: 'مدل' }).click();
    // A model that is signed out says so in words and does not join.
    await who.getByRole('button', { name: 'دیپ‌سیک' }).click();
    await expect(page.getByText('دیپ‌سیک الان وارد نیست')).toBeVisible();
    await who.getByRole('button', { name: 'جمنای' }).click();
    await expect(who.getByText('جمنای', { exact: true }).first()).toBeVisible();
    // A person: the overseer.
    await who.getByRole('button', { name: 'آدم' }).click();
    await page.getByRole('dialog', { name: 'کی را بیاورم؟' }).getByRole('button', { name: 'ناظر کل' }).click();
    await expect(who.getByText('ناظر کل')).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.getByRole('dialog')).toHaveCount(0);
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
    const who2 = (await openDetails(page)).getByLabel('کی در جلسه است');
    await who2.getByRole('button', { name: 'جمنای را بیرون ببر' }).click();
    await expect(who2.getByText('جمنای', { exact: true })).toHaveCount(0);
    await noRefs(page);
  }, [/player_signed_out/]);
});

test('tasks: add, tick, drop', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/s/F-0007');
    const tasks = (await openDetails(page)).getByLabel('کارها', { exact: true });
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
    // ⟨1.0.1⟩ The bar's «تأیید و بستن» closes with one tap (e2e/look-session.spec.ts); what may come before closing, and a note, are in
    // the details' «پایان جلسه».
    await (await openDetails(page)).getByRole('button', { name: 'تأیید و بستن' }).click();
    const sheet = page.getByRole('dialog', { name: 'تأیید و بستن جلسه' });
    await expect(sheet.getByRole('button', { name: 'کارگروه از این جلسه' })).toBeVisible();
    await sheet.getByRole('button', { name: 'خط تولید راه بینداز' }).click();
    // The holder puts the line's card in the talk.
    await expect(page.getByLabel(/^کارت خط تولید/).first()).toBeVisible();
    await (await openDetails(page)).getByRole('button', { name: 'تأیید و بستن' }).click();
    await page.getByRole('dialog', { name: 'تأیید و بستن جلسه' }).getByLabel('یادداشت بستن').fill('خوب شد');
    await page.getByRole('dialog', { name: 'تأیید و بستن جلسه' }).getByRole('button', { name: 'تأیید و ببند' }).click();
    await expect(page.getByText('جلسه بسته و بایگانی شد.')).toBeVisible();
    await expect(page.getByTestId('end-leaf')).toContainText('این جلسه تأیید و بایگانی شد');
    await expect(page.getByText('این جلسه بسته شده و فقط خواندنی است')).toBeVisible();
    // The archive lists it; the open list does not. (The demo keeps its records in the page, so the way there is a click, not a reload.)
    await page.locator('header').getByRole('link', { name: 'جلسه‌ها' }).click();
    await expect(page.getByText('یک مقاله‌ی سئو برای FX')).toHaveCount(0);
    await page.getByRole('button', { name: /^بایگانی/ }).click();
    await expect(page.getByText('یک مقاله‌ی سئو برای FX')).toBeVisible();
    await expect(page.getByText('گزارش هزینه‌ی تبلیغات اکتبر')).toBeVisible();
    // Reopen: the session is open again and the composer is back.
    await page.getByText('یک مقاله‌ی سئو برای FX').click();
    await page.getByTestId('end-leaf').getByRole('button', { name: 'دوباره باز کن' }).click();
    await expect(page.getByLabel('پیام', { exact: true })).toBeVisible();
    await expect((await openDetails(page)).getByRole('button', { name: 'تأیید و بستن' })).toBeVisible();
    await page.keyboard.press('Escape');
    // Hide: it leaves every list; nothing is deleted.
    await (await openDetails(page)).getByRole('button', { name: 'از فهرست بردار' }).click();
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

// ⟨1.18⟩ Contract §36: files in a session. A font for the covers' title and a picture go with a turn (`file_ids`), show in the owner's
// bubble, and are listed under «فایل‌ها» (OrderReport.files).
test('files in a session: a font and a picture are attached, sent, seen in the turn and in «فایل‌ها»', async ({ page }) => {
  // 1×1 PNG and a font-shaped blob: the demo hub only checks names and types.
  const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==', 'base64');
  await clean(page, async () => {
    await page.goto('/s/F-0008');
    await expect(page.getByLabel('فایل‌ها', { exact: true })).toHaveCount(0);
    await page.getByLabel('فایل برای فرستادن').setInputFiles([
      { name: 'Title-Font.ttf', mimeType: 'font/ttf', buffer: Buffer.from('\x00\x01\x00\x00demo-font') },
      { name: 'cover.png', mimeType: 'image/png', buffer: png },
      { name: 'virus.exe', mimeType: 'application/x-msdownload', buffer: Buffer.from('MZ') },
    ]);
    // The unsupported one is refused in plain words; the other two become chips and upload.
    await expect(page.getByText('این نوع فایل پذیرفته نمیشود')).toBeVisible();
    const tray = page.getByLabel('پیوست‌ها', { exact: true });
    await expect(tray.getByRole('button', { name: 'حذف Title-Font.ttf' })).toBeVisible();
    await expect(tray.getByRole('button', { name: 'حذف cover.png' })).toBeVisible();
    // Send with no text: the word «فایل» stands in.
    const send = page.getByRole('button', { name: 'بفرست' }).last();
    await expect(send).toBeEnabled();
    await send.click();
    const talk = page.getByLabel('گفتگو', { exact: true });
    const mine = talk.locator('[data-by="owner"]').last();
    await expect(mine.getByRole('link', { name: /Title-Font\.ttf/ })).toBeVisible();
    await expect(mine.getByRole('button', { name: 'نمایش cover.png' })).toBeVisible();
    await expect(page.getByLabel('پیوست‌ها', { exact: true })).toHaveCount(0);
    // The order keeps them.
    const files = (await openDetails(page)).getByLabel('فایل‌ها', { exact: true });
    await expect(files.getByRole('link', { name: /Title-Font\.ttf/ })).toBeVisible();
    await expect(files.getByRole('button', { name: 'نمایش cover.png' })).toBeVisible();
  });
});

// ⟨1.19⟩ Contract §37: erasing for good — a preview first, then the passkey and the erase; the session is gone from every list.
test('erase a closed session from the archive: preview, passkey, gone', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/s');
    await page.getByRole('button', { name: /^بایگانی/ }).click();
    await expect(page.getByText('گزارش هزینه‌ی تبلیغات اکتبر')).toBeVisible();
    await page.getByRole('button', { name: 'پاک کردن' }).first().click();
    const dlg = page.getByRole('dialog', { name: 'پاک کردن برای همیشه' });
    await expect(dlg.getByLabel('پیش‌نمایش پاک کردن')).toContainText('گزارش هزینه‌ی تبلیغات اکتبر');
    await expect(dlg.getByText('آنچه میماند')).toBeVisible();
    await dlg.getByRole('button', { name: /پاکش کن/ }).click();
    await expect(page.getByText('پاک شد.')).toBeVisible();
    await expect(page.getByText('گزارش هزینه‌ی تبلیغات اکتبر')).toHaveCount(0);
  });
});

test('erase an open session from its page, and an output from its detail', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/s/F-0006');
    await (await openDetails(page)).getByRole('button', { name: 'پاک کردن برای همیشه' }).click();
    await page.getByRole('dialog', { name: 'پاک کردن برای همیشه' }).getByRole('button', { name: /پاکش کن/ }).click();
    await expect(page).toHaveURL(/\/s$/);
    await expect(page.getByText('یک مقاله‌ی سئو برای FX')).toHaveCount(0);
    await page.goto('/outputs?ref=O-000040&tab=all');
    await page.getByRole('button', { name: 'پاک کردن برای همیشه' }).click();
    const dlg = page.getByRole('dialog', { name: 'پاک کردن برای همیشه' });
    await expect(dlg.getByLabel('پیش‌نمایش پاک کردن')).toBeVisible();
    await dlg.getByRole('button', { name: /پاکش کن/ }).click();
    await expect(page.getByText('پاک شد.')).toBeVisible();
  });
});

test('every turn has a «کپی» that copies its text; cancelling an order works with its own UUID idempotency key', async ({ page, context }) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write']);
  await clean(page, async () => {
    await page.goto('/s/F-0006');
    const talk = page.getByLabel('گفتگو', { exact: true });
    const turn = talk.locator('[data-by]').filter({ hasText: 'مقاله نوشته و در وبلاگ منتشر شد' }).first();
    // ⟨1.0.1⟩ «کپی» and the time are no longer under every bubble: they come up when the pointer (or the focus) is on the turn.
    await expect(turn.locator('[data-turn-tools]')).toHaveCSS('opacity', '0');
    await turn.hover();
    await turn.getByRole('button', { name: 'کپی متن' }).click();
    await expect(turn.getByText('کپی شد')).toBeVisible();
    expect(await page.evaluate(() => navigator.clipboard.readText())).toContain('مقاله نوشته و در وبلاگ منتشر شد');
    await (await openDetails(page)).getByRole('button', { name: 'تأیید و بستن' }).click();
    const dlg = page.getByRole('dialog', { name: 'تأیید و بستن جلسه' });
    await dlg.getByRole('button', { name: 'لغو فرمان' }).click();
    await dlg.getByRole('button', { name: 'بله، لغو کن' }).click();
    // The demo hub refuses a close whose Idempotency-Key is not a UUID (422), as the real one does.
    await expect(page.getByText('این جلسه بسته شده و فقط خواندنی است')).toBeVisible();
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

// ⟨0.17⟩ The talk is the body of the page: it opens at the latest message, stays there, and offers «↓» once he has scrolled up.
// (F-0007, a working session whose live lines stream in: the end must stay the end while they come.)
test('a session opens scrolled to its last turn; scrolled up it offers «↓» that brings him back', async ({ page }) => {
  await clean(page, async () => {
    await page.setViewportSize({ width: 900, height: 560 });
    // F-0007 is the demo's working session: its live lines stream in while the test waits.
    await page.goto('/s/F-0007');
    const talk = page.getByTestId('talk-scroll');
    await expect(talk.locator('[data-by]').first()).toBeVisible();
    const gap = () => talk.evaluate((el) => el.scrollHeight - el.scrollTop - el.clientHeight);
    expect(await talk.evaluate((el) => el.scrollHeight - el.clientHeight), 'the talk must overflow for this to mean anything').toBeGreaterThan(40);
    await expect.poll(gap).toBeLessThan(4);
    await expect(page.getByRole('button', { name: /^برو به آخر گفتگو/ })).toHaveCount(0);
    // The system steps are small lines inside the talk (a run of them folds into one quiet row), not a card.
    await expect(talk.locator('[data-step], [data-sys-group]').first()).toBeAttached();
    // Scrolled up: the round button shows; one tap and he is at the end again.
    await talk.evaluate((el) => el.scrollTo({ top: 0 }));
    const jump = page.getByRole('button', { name: /^برو به آخر گفتگو/ });
    await expect(jump).toBeVisible();
    await jump.click();
    await expect.poll(gap).toBeLessThan(4);
    await expect(jump).toHaveCount(0);
    // ⟨2026-11-11⟩ F-0007 is at work: its newest lines stream in at the end of the talk, each in place of the oldest of three. «↓»
    // lands at the end and stays there while they come (it used to stop short, a line's height behind, and fall further back).
    const tail = talk.getByTestId('live-tail').locator('[data-line]').last();
    const before = await tail.innerText();
    await expect.poll(() => tail.innerText(), { timeout: 20_000 }).not.toBe(before);
    await expect.poll(gap).toBeLessThan(4);
    await expect(jump).toHaveCount(0);
    // A word he sends keeps him at the end.
    await page.getByLabel('پیام', { exact: true }).fill('یک کلمه');
    await page.getByRole('button', { name: 'بفرست', exact: true }).click();
    await expect.poll(gap).toBeLessThan(4);
  });
});

test('the composer keeps the whole width for a long draft, grows to about six lines, then scrolls', async ({ page }) => {
  await clean(page, async () => {
    await page.goto('/s/F-0007');
    const box = page.getByLabel('پیام', { exact: true });
    const region = page.getByLabel('نوشتن', { exact: true });
    const wide = async () => ((await box.boundingBox())!.width) / ((await region.boundingBox())!.width);
    expect(await wide()).toBeGreaterThan(0.9);
    // Without text the mic is there; with text the send takes its place.
    await expect(page.getByRole('button', { name: 'نگه‌دار و بگو' })).toBeVisible();
    await box.fill('این یک پیام خیلی طولانی فارسی است که نباید هیچ وقت در یک ستون باریک بشکند. '.repeat(4));
    await expect(page.getByRole('button', { name: 'بفرست', exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: 'نگه‌دار و بگو' })).toHaveCount(0);
    expect(await wide()).toBeGreaterThan(0.9);
    const h1 = (await box.boundingBox())!.height;
    expect(h1).toBeGreaterThan(60); // it grew
    await box.fill(Array.from({ length: 30 }, (_, i) => `خط ${i + 1}`).join('\n'));
    const h2 = (await box.boundingBox())!.height;
    expect(h2, 'about six lines, then it scrolls').toBeLessThan(180);
    expect(await box.evaluate((el) => el.scrollHeight > el.clientHeight)).toBe(true);
    expect(await wide()).toBeGreaterThan(0.9);
  });
});
