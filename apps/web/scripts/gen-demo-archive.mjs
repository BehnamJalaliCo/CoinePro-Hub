#!/usr/bin/env node
// Demo documents for the archive in mock mode (contract §23), written to public/demo/archive/. Development only: nothing in production
// points at these files (the fixtures module that names them is aliased away outside mock mode, and the image build drops public/demo).
//
// Every document says on its face that it is a demo and has no legal standing. Two kinds:
// - Persian pages (registration notices, the sealed charter) are laid out in HTML with IRANYekanX, rendered by headless Chromium and
//   kept as a 1-bit image inside a minimal PDF, the way a scanner's PDF looks (the hub would OCR them, §23.9). The variable font would
//   otherwise be embedded as Type 3 glyphs, several times larger than the page itself.
// - Latin documents (invoices, the affiliate agreement, the renewal notice, the licence, the counsel's emails, the shareholders'
//   agreement) are written here as PDFs with a real text layer in the standard Helvetica, so they need no embedded font at all.
// One office-lease scan is a small grey WebP (a draft waiting for the archivist).
//
// Run from apps/web: `node scripts/gen-demo-archive.mjs`. Needs the Playwright Chromium already on the machine. The whole folder stays
// well under 200 KB.

import { mkdirSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { deflateSync } from 'node:zlib';
import { chromium } from '@playwright/test';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const OUT = join(ROOT, 'public/demo/archive');
rmSync(OUT, { recursive: true, force: true });
mkdirSync(OUT, { recursive: true });
const font = (f) => `data:font/woff2;base64,${readFileSync(join(ROOT, 'public/fonts', f)).toString('base64')}`;
const FONTS = `@font-face{font-family:"YekanFa";src:url("${font('iranyekanx-fanum.woff2')}") format("woff2");font-weight:100 1000}
@font-face{font-family:"YekanLat";src:url("${font('iranyekanx-latin.woff2')}") format("woff2");font-weight:100 1000}`;

// ------------------------------------------------------------------ PDF writer --
/** A PDF from objects (strings or {dict, stream} pairs), with a correct xref table. */
function pdf(objects) {
  const parts = ['%PDF-1.4\n%\xE2\xE3\xCF\xD3\n'];
  const offsets = [];
  let size = Buffer.byteLength(parts[0], 'latin1');
  const chunks = [Buffer.from(parts[0], 'latin1')];
  objects.forEach((o, i) => {
    offsets.push(size);
    const head = Buffer.from(`${i + 1} 0 obj\n`, 'latin1');
    let body;
    if (typeof o === 'string') body = Buffer.from(`${o}\nendobj\n`, 'latin1');
    else body = Buffer.concat([Buffer.from(`${o.dict.replace('%LEN%', String(o.stream.length))}\nstream\n`, 'latin1'), o.stream, Buffer.from('\nendstream\nendobj\n', 'latin1')]);
    chunks.push(head, body);
    size += head.length + body.length;
  });
  const xref = [`xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`, ...offsets.map((o) => `${String(o).padStart(10, '0')} 00000 n \n`)].join('');
  chunks.push(Buffer.from(`${xref}trailer\n<< /Size ${objects.length + 1} /Root 1 0 R /Info ${objects.length} 0 R >>\nstartxref\n${size}\n%%EOF\n`, 'latin1'));
  return Buffer.concat(chunks);
}
const info = (title) => `<< /Title (${esc(title)}) /Producer (CoinePro HQ demo fixtures) /Creator (scripts/gen-demo-archive.mjs) >>`;
const esc = (s) => s.replace(/\\/g, '\\\\').replace(/\(/g, '\\(').replace(/\)/g, '\\)');

/** A one-page A5 PDF holding a 1-bit image (white = 1), scaled to the page. */
function imagePdf({ width, height, bits, title }) {
  const W = 420, H = 595;
  const data = deflateSync(Buffer.from(bits), { level: 9 });
  const content = Buffer.from(`q ${W} 0 0 ${H} 0 0 cm /Im0 Do Q`, 'latin1');
  return pdf([
    '<< /Type /Catalog /Pages 2 0 R >>',
    '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
    `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${W} ${H}] /Resources << /XObject << /Im0 4 0 R >> >> /Contents 5 0 R >>`,
    { dict: `<< /Type /XObject /Subtype /Image /Width ${width} /Height ${height} /ColorSpace /DeviceGray /BitsPerComponent 1 /Filter /FlateDecode /Length %LEN% >>`, stream: data },
    { dict: '<< /Length %LEN% >>', stream: content },
    info(title),
  ]);
}

/** A one-page A5 PDF with a Helvetica text layer: a header band, then lines [{text, size?, bold?, gap?, rule?}]. */
function textPdf({ title, org, lines }) {
  const W = 420, H = 595, M = 40;
  let y = H - 52;
  const ops = [
    '0.11 0.13 0.2 rg', `0 ${H - 34} ${W} 34 re f`,
    'BT 1 1 1 rg /F2 10 Tf', `${M} ${H - 22} Td (${esc(org)}) Tj ET`,
    'BT 0.85 0.75 0.45 rg /F1 7 Tf', `${W - M - 70} ${H - 22} Td (DEMO - NO LEGAL VALUE) Tj ET`,
    '0 0 0 rg',
  ];
  for (const l of lines) {
    if (l.rule) { ops.push('0.75 0.75 0.75 RG 0.6 w', `${M} ${y + 4} m ${W - M} ${y + 4} l S`); y -= 10; continue; }
    const size = l.size ?? 9;
    y -= l.gap ?? 0;
    ops.push(`BT /${l.bold ? 'F2' : 'F1'} ${size} Tf ${l.x ?? M} ${y} Td (${esc(l.text)}) Tj ET`);
    y -= size + 5;
  }
  ops.push('BT 0.45 0.45 0.45 rg /F1 6.5 Tf', `${M} 26 Td (Demo document generated for the CoinePro HQ archive mock. Not a real ${esc(title.toLowerCase())}.) Tj ET`);
  const content = Buffer.from(ops.join('\n'), 'latin1');
  return pdf([
    '<< /Type /Catalog /Pages 2 0 R >>',
    '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
    `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${W} ${H}] /Resources << /Font << /F1 4 0 R /F2 5 0 R >> >> /Contents 6 0 R >>`,
    '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>',
    '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>',
    { dict: '<< /Length %LEN% >>', stream: content },
    info(title),
  ]);
}

// ------------------------------------------------------------------ Latin documents --
const kv = (k, v) => ({ text: `${k}:  ${v}` });
const invoice = (no, date, period, amount) => textPdf({
  title: 'Invoice', org: 'Hetzner Online GmbH (demo)',
  lines: [
    { text: 'INVOICE', size: 16, bold: true, gap: 6 }, kv('Invoice number', no), kv('Invoice date', date), kv('Customer', 'CoinePro Holding (demo)'), kv('Billing period', period), { rule: true },
    { text: 'Item                                               Qty      Amount', bold: true },
    { text: 'Cloud server CPX42 (8 vCPU, 16 GB RAM)       1      EUR ' + (Number(amount) - 4.6).toFixed(2) },
    { text: 'Primary IPv4                                              1      EUR 0.60' },
    { text: 'Backups (20%)                                           1      EUR 4.00' }, { rule: true },
    { text: `Total (VAT reverse charge)                                EUR ${amount}`, bold: true }, { text: 'Paid by card on the invoice date.', gap: 6 },
  ],
});
const LATIN = {
  'hetzner-R2026-08.pdf': invoice('R0026081422', '2026-08-01', '2026-07-01 to 2026-07-31', '38.10'),
  'hetzner-R2026-09.pdf': invoice('R0026094107', '2026-09-01', '2026-08-01 to 2026-08-31', '38.10'),
  'hetzner-R2026-10.pdf': invoice('R0026105533', '2026-10-01', '2026-09-01 to 2026-09-30', '38.10'),
  'hetzner-R2018-09.pdf': invoice('R0018092201', '2018-09-01', '2018-08-01 to 2018-08-31', '11.90'),
  'hetzner-R2018-12.pdf': invoice('R0018120587', '2018-12-01', '2018-11-01 to 2018-11-30', '11.90'),
  'hetzner-R2019-02.pdf': invoice('R0019020344', '2019-02-01', '2019-01-01 to 2019-01-31', '11.90'),
  'lbank-affiliate-2026.pdf': textPdf({ title: 'Affiliate agreement', org: 'LBank Exchange - Affiliate Program (demo)', lines: [
    { text: 'AFFILIATE AGREEMENT', size: 15, bold: true, gap: 6 }, kv('Affiliate', 'CoinePro FX (demo)'), kv('Programme', 'Partner tier'), kv('Commission', '40% of trading fees of referred users'),
    kv('Start', '2026-04-01'), kv('Term', '12 months, review every 6 months'), kv('Next review', 'see the archive record'), { rule: true },
    { text: '1. Referral links are issued per channel and must not be shortened.' }, { text: '2. No profit promises; every promotion carries a risk warning.' },
    { text: '3. Commission is paid monthly in USDT to the affiliate wallet on file.' }, { text: '4. Either party may end the agreement with 30 days notice.' },
    { text: 'Signed electronically for both parties.', gap: 8 } ] }),
  'lbank-affiliate-amendment-1.pdf': textPdf({ title: 'Amendment', org: 'LBank Exchange - Affiliate Program (demo)', lines: [
    { text: 'AMENDMENT No. 1 TO THE AFFILIATE AGREEMENT', size: 12, bold: true, gap: 6 }, kv('Affiliate', 'CoinePro FX (demo)'), kv('Effective', '2026-09-01'), { rule: true },
    { text: '1. Commission rises from 40% to 45% of trading fees of referred users.' }, { text: '2. Sub-affiliate share: 5% of the sub-affiliate commission.' },
    { text: '3. Every other term of the agreement stays as signed.' }, { text: 'Signed electronically for both parties.', gap: 8 } ] }),
  'domain-coinepro-com-renewal.pdf': textPdf({ title: 'Renewal notice', org: 'Domain registrar (demo)', lines: [
    { text: 'DOMAIN RENEWAL NOTICE', size: 14, bold: true, gap: 6 }, kv('Domain', 'coinepro.com'), kv('Registrant', 'CoinePro Holding (demo)'), kv('Expires', 'in 25 days (see the archive record)'),
    kv('Auto-renew', 'OFF'), kv('Renewal price', 'USD 11.20 per year'), { rule: true },
    { text: 'If the domain is not renewed before it expires, its DNS stops answering' }, { text: 'and the name enters a 30-day redemption period.' } ] }),
  'charting-license-2026.pdf': textPdf({ title: 'Licence', org: 'Charting library vendor (demo)', lines: [
    { text: 'COMMERCIAL LICENCE', size: 14, bold: true, gap: 6 }, kv('Licensee', 'Pro-Chart (demo)'), kv('Licence number', 'CL-PC-2026-0417'), kv('Issued', '2026-03-10'), kv('Expires', '2027-03-10'),
    kv('Scope', 'Android app and web terminal, unlimited end users'), kv('Fee', 'USD 2,400 per year'), { rule: true },
    { text: 'The library may not be redistributed as a standalone product.' }, { text: 'Attribution in the app settings screen is required.' } ] }),
  'lc-0001-email-out-1.pdf': textPdf({ title: 'Email', org: 'legal@coinepro.com (sent, demo)', lines: [
    { text: 'Instagram business account cannot reply to messages - CoinePro FX', size: 10, bold: true, gap: 4 }, kv('From', 'legal@coinepro.com'), kv('To', 'appeals@platform-support.example'),
    kv('Sealed by', 'D-000083'), { rule: true }, { text: 'Hello,' }, { text: 'Since 18 October 2026 the Instagram business account of CoinePro FX cannot reply' },
    { text: 'to direct messages. We have submitted the in-app review form and would like to' }, { text: 'understand which policy the restriction refers to and what we should change.' },
    { text: 'Thank you,', gap: 6 }, { text: 'CoinePro Holding, legal desk' } ] }),
  'lc-0001-email-in-1.pdf': textPdf({ title: 'Email', org: 'appeals@platform-support.example (received, demo)', lines: [
    { text: 'Re: Instagram business account cannot reply to messages', size: 10, bold: true, gap: 4 }, kv('From', 'appeals@platform-support.example'), kv('To', 'legal@coinepro.com'),
    kv('Case', '4471-DEMO'), { rule: true }, { text: 'Thank you for contacting us. Your request has been received under case' }, { text: '4471-DEMO. We will review it within 5 business days.' },
    { text: '[masked: support agent name]', gap: 6 } ] }),
  'shareholders-agreement.pdf': textPdf({ title: 'Agreement', org: 'CoinePro Holding - board (demo)', lines: [
    { text: "SHAREHOLDERS' AGREEMENT", size: 14, bold: true, gap: 6 }, kv('Parties', 'the founder and the holding (demo)'), kv('Date', '2026-06-02'), { rule: true },
    { text: '1. Shares of a company may be transferred only with the board seal.' }, { text: '2. Pre-emption right for the holding on any new issue.' },
    { text: '3. Vesting of the operating shares over 36 months, 12-month cliff.' }, { text: '4. Drag-along and tag-along at the same price and terms.' },
    { text: '5. This agreement is filed at level SECRET in the holding archive.', gap: 6 } ] }),
};

// ------------------------------------------------------------------ Persian pages (rendered) --
const PAGE_CSS = `${FONTS}
*{box-sizing:border-box;margin:0}
body{width:630px;height:893px;background:#fff;color:#111;font-family:"YekanFa",sans-serif;padding:46px 50px;direction:rtl;font-size:16px;line-height:1.95}
h1{font-size:25px;font-weight:800;margin:6px 0 2px}
.org{font-size:14px;color:#333;border-bottom:2px solid #111;padding-bottom:8px;display:flex;justify-content:space-between}
.demo{font-family:"YekanLat";font-size:12px;font-weight:700;letter-spacing:.06em}
.kv{display:flex;gap:10px}.kv b{min-width:150px;font-weight:700}
.stamp{position:absolute;left:70px;bottom:120px;width:150px;height:150px;border:5px double #111;border-radius:50%;display:flex;align-items:center;justify-content:center;text-align:center;font-size:14px;font-weight:700;transform:rotate(-14deg);padding:16px}
.foot{position:absolute;right:50px;left:50px;bottom:40px;font-size:12.5px;border-top:1px solid #111;padding-top:8px}
ol{padding-right:22px}li{margin-bottom:4px}`;
const reg = (name, kind, no, nid, date, subject, capital) => `<div class="org"><span>اداره‌ی ثبت شرکت‌ها (نمونه)</span><span class="demo">DEMO</span></div>
<h1>آگهی تأسیس ${kind}</h1>
<div class="kv"><b>نام شرکت</b><span>${name}</span></div>
<div class="kv"><b>شماره‌ی ثبت</b><span>${no}</span></div>
<div class="kv"><b>شناسه‌ی ملی</b><span>${nid}</span></div>
<div class="kv"><b>تاریخ ثبت</b><span>${date}</span></div>
<div class="kv"><b>موضوع فعالیت</b><span>${subject}</span></div>
<div class="kv"><b>سرمایه‌ی ثبتی</b><span>${capital} ریال</span></div>
<div class="kv"><b>نشانی</b><span>تهران، نشانی نمونه</span></div>
<div class="stamp">مُهر اداره‌ی ثبت<br>نمونه</div>
<div class="foot">این سند نمونه‌ی نمایشی بایگانی هاب است و هیچ اعتبار حقوقی ندارد.</div>`;
const PERSIAN = {
  'hq-registration.pdf': reg('هلدینگ کوینه‌پرو', 'شرکت سهامی خاص', '58214', '14012345678', '1405/05/12', 'سرمایه‌گذاری و اداره‌ی شرکت‌های فناوری مالی', '1,000,000,000'),
  'ty-registration.pdf': reg('تریدیار', 'شرکت با مسئولیت محدود', '58377', '14012399120', '1405/05/26', 'آموزش و ابزار تحلیل بازار', '200,000,000'),
  'fx-registration.pdf': reg('کوینه‌پرو FX', 'شرکت با مسئولیت محدود', '58402', '14012407731', '1405/06/02', 'سیگنال و تحلیل بازارهای مالی', '200,000,000'),
  'pc-registration.pdf': reg('پرو-چارت', 'شرکت با مسئولیت محدود', '58466', '14012418856', '1405/06/09', 'نرم‌افزار نمودار و ترمینال معاملاتی', '200,000,000'),
  'hq-charter-v3.pdf': `<div class="org"><span>هلدینگ کوینه‌پرو</span><span class="demo">DEMO</span></div>
<h1>اساسنامه‌ی هلدینگ، نسخه‌ی ۳</h1>
<div class="kv"><b>وضعیت</b><span>مُهرشده با اثر انگشت مدیر کل</span></div>
<div class="kv"><b>ثبت در بایگانی</b><span>خودکار، منبع سیستمی charter_sealed</span></div>
<ol style="margin-top:14px">
<li>اول قاعده، آخر هوش مصنوعی.</li>
<li>هیچ پرداخت، امضا یا تعهدی بی‌مُهر مدیر کل انجام نمیشود.</li>
<li>داده‌ی هر شرکت جداست و هیچ شرکتی داده‌ی دیگری را نمیبیند.</li>
<li>هر سند بایگانی پس از مُهر تغییر نمیکند؛ اصلاح، نسخه‌ی تازه است.</li>
<li>هیچ رمز، کلید یا عبارت بازیابی وارد بایگانی نمیشود.</li>
</ol>
<div class="stamp">مُهر هلدینگ<br>کوینه‌پرو</div>
<div class="foot">نسخه‌ی نمایشی؛ متن کامل اساسنامه در صفحه‌ی اساسنامه‌ی هاب است.</div>`,
};
const LEASE = `<div class="org"><span>قرارداد اجاره</span><span class="demo">DEMO SCAN</span></div>
<h1>اجاره‌نامه‌ی دفتر تهران</h1>
<div class="kv"><b>موجر</b><span>مالک نمونه</span></div>
<div class="kv"><b>مستأجر</b><span>هلدینگ کوینه‌پرو</span></div>
<div class="kv"><b>مدت</b><span>از 1405/07/01 تا 1406/06/31</span></div>
<div class="kv"><b>اجاره‌ی ماهانه</b><span>180,000,000 ریال</span></div>
<div class="kv"><b>ودیعه</b><span>1,500,000,000 ریال</span></div>
<div class="stamp">امضای<br>طرفین</div>
<div class="foot">اسکن نمونه؛ منتظر طبقه‌بندی بایگان.</div>`;

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 630, height: 893 }, deviceScaleFactor: 1 });
async function render(html) {
  await page.setContent(`<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8"><style>${PAGE_CSS}</style></head><body>${html}</body></html>`);
  await page.evaluate(() => document.fonts.ready);
  return page.screenshot({ type: 'png' });
}
/** PNG → 1-bit rows (white = 1, rows padded to a byte), thresholded in the page's own canvas. */
async function oneBit(png) {
  return page.evaluate(async (b64) => {
    const img = new Image();
    img.src = `data:image/png;base64,${b64}`;
    await img.decode();
    const c = document.createElement('canvas');
    c.width = img.width; c.height = img.height;
    const g = c.getContext('2d');
    g.drawImage(img, 0, 0);
    const px = g.getImageData(0, 0, c.width, c.height).data;
    const stride = Math.ceil(c.width / 8);
    const out = new Uint8Array(stride * c.height);
    for (let y = 0; y < c.height; y++) for (let x = 0; x < c.width; x++) {
      const i = (y * c.width + x) * 4;
      const lum = 0.299 * px[i] + 0.587 * px[i + 1] + 0.114 * px[i + 2];
      if (lum > 150) out[y * stride + (x >> 3)] |= 0x80 >> (x & 7);
    }
    return { width: c.width, height: c.height, bits: Array.from(out) };
  }, png.toString('base64'));
}
/** A grey, slightly tilted scan as WebP. */
async function scan(png) {
  const url = await page.evaluate(async (b64) => {
    const img = new Image();
    img.src = `data:image/png;base64,${b64}`;
    await img.decode();
    const c = document.createElement('canvas');
    c.width = 540; c.height = 766;
    const g = c.getContext('2d');
    g.fillStyle = '#e9e6df'; g.fillRect(0, 0, c.width, c.height);
    g.translate(c.width / 2, c.height / 2); g.rotate(-0.012); g.translate(-c.width / 2, -c.height / 2);
    g.filter = 'grayscale(1) contrast(1.15) blur(0.3px)';
    g.globalAlpha = 0.92;
    g.drawImage(img, 0, 0, c.width, c.height);
    return c.toDataURL('image/webp', 0.42);
  }, png.toString('base64'));
  return Buffer.from(url.split(',')[1], 'base64');
}

for (const [name, html] of Object.entries(PERSIAN)) {
  const b = await oneBit(await render(html));
  writeFileSync(join(OUT, name), imagePdf({ ...b, title: name.replace(/\.pdf$/, '') }));
}
writeFileSync(join(OUT, 'scan-office-lease.webp'), await scan(await render(LEASE)));
await browser.close();
for (const [name, buf] of Object.entries(LATIN)) writeFileSync(join(OUT, name), buf);

let total = 0;
for (const f of readdirSync(OUT).sort()) { const s = statSync(join(OUT, f)).size; total += s; console.log(`${f.padEnd(34)} ${String(s).padStart(7)} B`); }
console.log(`${'total'.padEnd(34)} ${String(total).padStart(7)} B`);
