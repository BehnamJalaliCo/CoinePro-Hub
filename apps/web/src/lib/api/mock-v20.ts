// Development-only fixtures for contract v1.7 §23 (the archive of record), used by mock.ts. Never bundled in production (next.config
// aliases the fixtures module away). Scopes are data here as on the hub: the holding and every company come from the rows, nothing
// counts them. What the hub does by code is code here too, reduced to what a demo needs: clearance before anything is returned (the
// reader is the owner, who sees everything, but every list goes through the same check), SHA-256 of every file and the manifest of every
// version, the seal on that manifest, `sealed_record`, legal holds (423), the secret scan at upload, validation of every schema change
// against the closed vocabulary with its impact, retire-never-delete, retention and reminders by rule, and Persian-normalised search.
// The documents are files in public/demo/archive/ made by scripts/gen-demo-archive.mjs; their text is what the OCR or the text layer
// would give.

const now = Date.now();
const MIN = 60_000;
const DAY = 86_400_000;
const iso = (minAgo: number) => new Date(now - minAgo * MIN).toISOString();
const stamp = () => new Date().toISOString();
/** A calendar date `n` days from today (negative = past), as the archive stores dates. */
const dOff = (n: number) => new Date(now + n * DAY).toISOString().slice(0, 10);
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
const page = (items: unknown[]) => ({ items, next_cursor: null });
const problem = (status: number, code: string, message_fa: string, extra: Record<string, unknown> = {}) =>
  json({ type: 'about:blank', title: code, status, code, message_fa, ...extra }, status);
const invalid = (fields: Record<string, string>, message_fa?: string) =>
  problem(422, 'schema_invalid', message_fa ?? `با واژگان بسته نمیخواند: ${Object.values(fields)[0]}`, { fields });
const pad = (n: number, w: number) => String(n).padStart(w, '0');
const hex = (buf: ArrayBuffer) => [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, '0')).join('');
const sha256 = async (data: string | ArrayBuffer) => hex(await crypto.subtle.digest('SHA-256', typeof data === 'string' ? new TextEncoder().encode(data) : data));
const keys = new Map<string, { status: number; body: unknown }>();
const needsStepUp = (req: Request) => (req.headers.get('X-Step-Up') ? null : problem(403, 'step_up_required', 'این کار تأیید با اثر انگشت یا چهره میخواهد.'));
function versionCheck(req: Request, version: number | null): Response | null {
  const m = req.headers.get('If-Match');
  const none = req.headers.get('If-None-Match');
  if (version == null) return m && m.replace(/"/g, '') !== '0' ? problem(409, 'version_conflict', 'این کلید هنوز وجود ندارد؛ صفحه را تازه کن.') : null;
  if (none === '*') return problem(409, 'version_conflict', 'این کلید از قبل هست؛ کلید دیگری انتخاب کن.');
  if (!m) return problem(428, 'precondition_required', 'نسخه همراه درخواست نیامد.');
  if (m.replace(/"/g, '') !== String(version)) return problem(409, 'version_conflict', 'همین حالا عوض شده؛ دوباره نگاه کن.');
  return null;
}

// ------------------------------------------------------------------------ actors --
const owner = { kind: 'owner', code: 'owner', display_fa: 'مدیر کل' };
const system = { kind: 'system', code: 'system', display_fa: 'سیستم' };
const agent = (code: string, display_fa: string, kind = 'agent') => ({ kind, code, display_fa });
const archivist = agent('HQ-ARC', 'بایگان');
const counsel = agent('HQ-LGL', 'مشاور حقوقی');

// ============================================================ the closed vocabulary (§23.2, §23.7) ==
const FIELD_TYPES: Array<[string, string]> = [
  ['text', 'متن کوتاه'], ['long_text', 'متن بلند'], ['number', 'عدد'], ['money', 'مبلغ'], ['percent', 'درصد'], ['date', 'تاریخ'], ['date_range', 'بازه‌ی تاریخ'],
  ['enum', 'یک گزینه'], ['multi_enum', 'چند گزینه'], ['boolean', 'بله یا نه'], ['party', 'طرف حساب'], ['company', 'شرکت'], ['ref', 'ارجاع'],
  ['url', 'نشانی وب'], ['email', 'ایمیل'], ['phone', 'تلفن'], ['id_code', 'شناسه'], ['iban', 'شبا / IBAN'],
];
const TYPES = FIELD_TYPES.map(([k]) => k);
const REF_KINDS = ['decision', 'resolution', 'case', 'work', 'record', 'employee', 'revenue_account'];
const EVENTS = ['filed', 'sealed', 'reminder_due', 'retention_due', 'hold_set', 'version_added'];
const ACTIONS = ['notify', 'work_item', 'link', 'move_to_folder', 'raise_level', 'add_reminder'];
const OPS = ['eq', 'lt', 'gt', 'contains'];
const CURRENCIES = ['USD', 'USDT', 'EUR', 'IRR', 'AED', 'TRY', 'GBP'];
const MIMES = ['application/pdf', 'image/jpeg', 'image/png', 'image/webp', 'text/plain', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'message/rfc822'];
const KEY_RE = /^[a-z][a-z0-9_]{1,39}$/;
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
/** The same patterns as gitleaks and the outbound guard (§19.6), reduced to what the demo needs. */
const SECRET_RE = /seed|private[\s_-]?key|mnemonic|-----BEGIN [A-Z ]*PRIVATE KEY-----|عبارت بازیابی|کلید خصوصی/i;

// ============================================================ levels and clearance (§23.4) ==
// Assumed: the seeds' ranks are spaced (0, 10, 20, 30) so a new level fits between two without renumbering a used one.
const levels: any[] = [
  { key: 'public', title_fa: 'عمومی', rank: 0, color_index: 0, watermark: false, encrypt: false, step_up_to_view: false, agents_max: false },
  { key: 'internal', title_fa: 'داخلی', rank: 10, color_index: 1, watermark: false, encrypt: false, step_up_to_view: false, agents_max: false },
  { key: 'confidential', title_fa: 'محرمانه', rank: 20, color_index: 2, watermark: true, encrypt: false, step_up_to_view: false, agents_max: true },
  { key: 'secret', title_fa: 'سرّی', rank: 30, color_index: 3, watermark: true, encrypt: true, step_up_to_view: true, agents_max: false },
].map((l) => ({ ...l, version: 1, status: 'active' }));
const rankOf = (key: string | null | undefined) => levels.find((l) => l.key === key)?.rank ?? 0;
const agentsMax = () => Math.max(...levels.filter((l) => l.agents_max && l.status === 'active').map((l) => l.rank), 0);

/** Clearance rows, one subject at a time (assumed key `role:<role>`); `own` is the subject's own company. */
const clearance: any[] = [
  { subject: { kind: 'role', ref: '*' }, scope: 'own', level: 'internal', metadata_level: null, version: 1 },
  { subject: { kind: 'role', ref: 'legal_counsel' }, scope: 'all', level: 'confidential', metadata_level: null, version: 1 },
  { subject: { kind: 'role', ref: 'archivist' }, scope: 'all', level: 'confidential', metadata_level: 'secret', version: 1 },
];
/** The reader of every call in this demo: the owner, who sees everything. The check below still runs on every list, search and read. */
const READER: { kind: 'owner' } | { kind: 'role'; role: string; company: string } = { kind: 'owner' };
function maxRankFor(scope: string): number {
  if (READER.kind === 'owner') return Infinity;
  const r = READER;
  const rows = clearance.filter((c) => c.subject.kind === 'role' && (c.subject.ref === r.role || c.subject.ref === '*') && (c.scope === 'all' || c.scope === scope || (c.scope === 'own' && r.company === scope)));
  return rows.length ? Math.max(...rows.map((c) => rankOf(c.level))) : -1;
}
const canSee = (r: any) => r.state !== 'disposed_hidden' && rankOf(r.level) <= maxRankFor(r.scope);

// ============================================================ classes (§23.2) ==
const F = (key: string, title_fa: string, type: string, o: Record<string, unknown> = {}) => ({ key, title_fa, type, required: false, searchable: false, sensitive: false, help_fa: null, status: 'active', ...o });
const req = { required: true };
const srch = { searchable: true };
const classes: any[] = [
  { key: 'company_registration', title_fa: 'ثبت شرکت', icon: 'found', default_level: 'internal', retention: 'RR-0005', reminder_fields: [], required_files: 1, ocr: true,
    fields: [F('reg_no', 'شماره‌ی ثبت', 'id_code', { ...req, ...srch }), F('national_id', 'شناسه‌ی ملی', 'id_code', { ...srch, sensitive: true }), F('reg_date', 'تاریخ ثبت', 'date', req),
      F('registry', 'مرجع ثبت', 'party'), F('company', 'شرکت', 'company', req), F('subject_fa', 'موضوع فعالیت', 'long_text', srch), F('capital', 'سرمایه‌ی ثبتی', 'money', { currency: 'IRR' })] },
  { key: 'contract', title_fa: 'قرارداد', icon: 'report', default_level: 'confidential', retention: 'RR-0001', reminder_fields: ['end'], required_files: 1, ocr: true,
    fields: [F('counterparty', 'طرف قرارداد', 'party', req), F('subject', 'موضوع', 'text', { ...req, ...srch }), F('start', 'شروع', 'date', req), F('end', 'پایان', 'date'),
      F('value', 'مبلغ قرارداد', 'money', { currency: 'USD' }), F('auto_renew', 'تمدید خودکار', 'boolean'), F('notice_days', 'مهلت فسخ (روز)', 'number')] },
  { key: 'affiliate_agreement', title_fa: 'توافق افیلیت', parent: 'contract', icon: 'share', default_level: 'confidential', retention: 'RR-0001', reminder_fields: ['review_at'], required_files: 1, ocr: false,
    fields: [F('exchange', 'صرافی', 'party', req), F('commission', 'سهم کمیسیون', 'percent', req), F('start', 'شروع', 'date', req), F('end', 'پایان', 'date'), F('review_at', 'بازبینی بعدی', 'date'),
      F('referral_link', 'لینک رفرال', 'url'), F('account_id', 'شناسه‌ی حساب افیلیت', 'id_code', { sensitive: true }),
      F('tier', 'سطح همکاری', 'enum', { options: [{ key: 'standard', title_fa: 'عادی' }, { key: 'vip', title_fa: 'VIP' }, { key: 'partner', title_fa: 'شریک' }] })] },
  { key: 'license', title_fa: 'مجوز', icon: 'lock', default_level: 'internal', retention: 'RR-0003', reminder_fields: ['expires_at'], required_files: 1, ocr: false,
    fields: [F('issuer', 'صادرکننده', 'party', req), F('license_no', 'شماره‌ی مجوز', 'id_code', srch), F('issued_at', 'تاریخ صدور', 'date'), F('expires_at', 'انقضا', 'date', req),
      F('scope_fa', 'دامنه‌ی مجوز', 'long_text', srch), F('cost', 'هزینه‌ی سالانه', 'money', { currency: 'USD' })] },
  { key: 'invoice', title_fa: 'فاکتور و رسید', icon: 'budget', default_level: 'internal', retention: 'RR-0002', reminder_fields: [], required_files: 1, ocr: true,
    fields: [F('vendor', 'فروشنده', 'party', req), F('number', 'شماره‌ی فاکتور', 'text', { ...req, ...srch }), F('date', 'تاریخ فاکتور', 'date', req), F('amount', 'مبلغ', 'money', { ...req, currency: 'EUR' }),
      F('period', 'دوره', 'date_range'), F('paid', 'پرداخت‌شده', 'boolean'),
      F('category', 'دسته', 'enum', { options: [{ key: 'hosting', title_fa: 'میزبانی' }, { key: 'domain', title_fa: 'دامنه' }, { key: 'software', title_fa: 'نرم‌افزار' }, { key: 'service', title_fa: 'خدمت' }, { key: 'other', title_fa: 'دیگر' }] })] },
  { key: 'domain', title_fa: 'دامنه', icon: 'globe', default_level: 'internal', retention: 'RR-0003', reminder_fields: ['expires_at'], required_files: 0, ocr: false,
    fields: [F('domain', 'نام دامنه', 'text', { ...req, ...srch }), F('registrar', 'ثبت‌کننده', 'party', req), F('expires_at', 'انقضا', 'date', req), F('auto_renew', 'تمدید خودکار', 'boolean'), F('dns_provider', 'DNS', 'text')] },
  { key: 'legal_correspondence', title_fa: 'مکاتبه‌ی حقوقی', icon: 'send', default_level: 'confidential', retention: 'RR-0004', reminder_fields: [], required_files: 1, ocr: false,
    fields: [F('case', 'پرونده', 'ref', { ...req, ref_kinds: ['case'] }), F('direction', 'جهت', 'enum', { ...req, options: [{ key: 'out', title_fa: 'رفت' }, { key: 'in', title_fa: 'آمد' }] }),
      F('counterpart', 'طرف مقابل', 'party'), F('date', 'تاریخ', 'date', req), F('subject_en', 'موضوع ایمیل', 'text', srch), F('decision', 'کارت مُهر', 'ref', { ref_kinds: ['decision'] })] },
  { key: 'sealed_policy', title_fa: 'اساسنامه و سیاست مُهرشده', icon: 'seal', default_level: 'internal', retention: 'RR-0005', reminder_fields: [], required_files: 1, ocr: false,
    fields: [F('policy_ref', 'نسخه‌ی سند', 'text', { ...req, ...srch }), F('version', 'شماره‌ی نسخه', 'number'), F('sealed_on', 'تاریخ مُهر', 'date', req), F('decision', 'کارت', 'ref', { ref_kinds: ['decision', 'resolution'] })] },
  { key: 'brand_asset', title_fa: 'نشان و مُهر', icon: 'image', default_level: 'internal', retention: 'RR-0005', reminder_fields: [], required_files: 1, ocr: false,
    fields: [F('company', 'شرکت', 'company', req), F('version', 'نسخه', 'number'), F('sealed_on', 'تاریخ مُهر', 'date')] },
  { key: 'resolution_bundle', title_fa: 'مصوبه‌های ماه', icon: 'meeting', default_level: 'internal', retention: 'RR-0005', reminder_fields: [], required_files: 1, ocr: false,
    fields: [F('month', 'ماه', 'text', { ...req, ...srch }), F('count', 'تعداد مصوبه', 'number')] },
  { key: 'other', title_fa: 'سایر', icon: 'attach', default_level: 'internal', retention: 'RR-0006', reminder_fields: [], required_files: 0, ocr: true,
    fields: [F('description', 'شرح', 'long_text', srch)] },
].map((c) => ({ parent: null, scopes: 'all', default_folder: null, allowed_mime: ['application/pdf', 'image/jpeg', 'image/png', 'image/webp'], auto_link: [], version: 1, status: 'active', ...c }));
classes.find((c) => c.key === 'legal_correspondence')!.auto_link = [{ field: 'case', link_kind: 'about' }];
classes.find((c) => c.key === 'legal_correspondence')!.allowed_mime.push('message/rfc822');
classes.find((c) => c.key === 'other')!.allowed_mime.push('text/plain');
const classOf = (key: string | null | undefined) => classes.find((c) => c.key === key);

// ============================================================ file plan, parties, link kinds (§23.3) ==
const folders: any[] = [
  ['FP-0001', 'HQ', null, 'حقوقی و ثبتی', [], null], ['FP-0002', 'HQ', 'FP-0001', 'ثبت و اساسنامه', ['company_registration', 'sealed_policy'], null],
  ['FP-0003', 'HQ', 'FP-0001', 'قراردادها', ['contract'], 'confidential'], ['FP-0004', 'HQ', null, 'مالی', [], null], ['FP-0005', 'HQ', 'FP-0004', 'فاکتورها و رسیدها', ['invoice'], null],
  ['FP-0006', 'HQ', null, 'فنی و زیرساخت', [], null], ['FP-0007', 'HQ', 'FP-0006', 'دامنه‌ها و مجوزها', ['domain', 'license'], null], ['FP-0008', 'HQ', null, 'نشان و مصوبه‌ها', ['brand_asset', 'resolution_bundle'], null],
  ['FP-0011', 'TY', null, 'ثبتی', ['company_registration'], null], ['FP-0012', 'TY', null, 'قراردادها', ['contract', 'affiliate_agreement'], 'confidential'], ['FP-0013', 'TY', null, 'مالی', ['invoice'], null],
  ['FP-0021', 'FX', null, 'ثبتی', ['company_registration'], null], ['FP-0022', 'FX', null, 'قراردادها و افیلیت', ['contract', 'affiliate_agreement'], 'confidential'], ['FP-0023', 'FX', null, 'مکاتبات حقوقی', ['legal_correspondence'], 'confidential'],
  ['FP-0031', 'PC', null, 'ثبتی', ['company_registration'], null], ['FP-0032', 'PC', null, 'مجوزها', ['license'], null], ['FP-0033', 'PC', null, 'قراردادها', ['contract'], 'confidential'],
].map(([ref, scope, parent, title_fa, cls, lvl], i) => ({ ref, scope, parent, title_fa, classes: cls, default_level: lvl, order: i, status: 'active', version: 1 }));
const ID = (key: string, title_fa: string, type: string, o: Record<string, unknown> = {}) => F(key, title_fa, type, o);
const partyKinds: any[] = [
  { key: 'exchange', title_fa: 'صرافی', identifier_fields: [ID('website', 'وب‌سایت', 'url'), ID('account', 'شناسه‌ی حساب', 'id_code', { sensitive: true })] },
  { key: 'provider', title_fa: 'تأمین‌کننده', identifier_fields: [ID('website', 'وب‌سایت', 'url'), ID('vat_id', 'شناسه‌ی مالیاتی', 'id_code'), ID('email', 'ایمیل', 'email')] },
  { key: 'government', title_fa: 'نهاد دولتی', identifier_fields: [ID('website', 'وب‌سایت', 'url'), ID('phone', 'تلفن', 'phone')] },
  { key: 'bank', title_fa: 'بانک', identifier_fields: [ID('iban', 'شبا', 'iban', { sensitive: true }), ID('swift', 'SWIFT', 'id_code')] },
  { key: 'person', title_fa: 'شخص', identifier_fields: [ID('national_id', 'کد ملی', 'id_code', { sensitive: true }), ID('email', 'ایمیل', 'email'), ID('phone', 'تلفن', 'phone')] },
  { key: 'other', title_fa: 'دیگر', identifier_fields: [ID('note', 'یادداشت', 'text')] },
].map((k) => ({ ...k, version: 1, status: 'active' }));
const parties: any[] = [
  { ref: 'PT-0001', kind: 'exchange', name_fa: 'صرافی ال‌بنک', name_en: 'LBank', identifiers: { website: 'https://www.lbank.com', account: '88412907' }, scopes: ['FX', 'TY'] },
  { ref: 'PT-0002', kind: 'provider', name_fa: 'هتزنر', name_en: 'Hetzner Online GmbH', identifiers: { website: 'https://www.hetzner.com', vat_id: 'DE812871812' }, scopes: ['HQ'] },
  { ref: 'PT-0003', kind: 'provider', name_fa: 'ثبت‌کننده‌ی دامنه', name_en: 'Domain registrar (demo)', identifiers: { website: 'https://registrar.example' }, scopes: ['HQ'] },
  { ref: 'PT-0004', kind: 'government', name_fa: 'اداره‌ی ثبت شرکت‌ها', name_en: null, identifiers: { website: 'https://registry.example' }, scopes: ['HQ', 'TY', 'FX', 'PC'] },
  { ref: 'PT-0005', kind: 'provider', name_fa: 'اینستاگرام (Meta)', name_en: 'Instagram (Meta)', identifiers: { email: 'appeals@platform-support.example' }, scopes: ['FX'] },
  { ref: 'PT-0006', kind: 'bank', name_fa: 'بانک نمونه', name_en: 'Demo Bank', identifiers: { iban: 'IR820540102680020817909002', swift: 'DEMOIRTH' }, scopes: ['HQ'] },
  { ref: 'PT-0007', kind: 'provider', name_fa: 'فروشنده‌ی کتابخانه‌ی نمودار', name_en: 'Charting library vendor (demo)', identifiers: { website: 'https://charts.example' }, scopes: ['PC'] },
  { ref: 'PT-0008', kind: 'person', name_fa: 'بنیان‌گذار (نمونه)', name_en: null, identifiers: { national_id: '0012345678' }, scopes: ['HQ'] },
].map((p) => ({ ...p, status: 'active', version: 1 }));
const partyOf = (ref: unknown) => parties.find((p) => p.ref === ref);
const linkKinds: any[] = [
  ['supersedes', 'جایگزین میکند', 'جایگزین شده با', ['record']], ['amends', 'اصلاح میکند', 'اصلاح شده با', ['record']], ['renews', 'تمدید میکند', 'تمدید شده با', ['record']],
  ['evidence_for', 'شاهد است برای', 'شاهدش', ['decision', 'resolution', 'case', 'work', 'record']], ['attached_to', 'پیوست', 'پیوست‌ها', ['record', 'decision', 'work']],
  ['about', 'درباره‌ی', 'سندهای مرتبط', ['case', 'decision', 'resolution', 'work', 'employee', 'revenue_account', 'record']],
].map(([key, title_fa, inverse_fa, to_kinds]) => ({ key, title_fa, inverse_fa, to_kinds, version: 1, status: 'active' }));

// ============================================================ retention and reminders (§23.5, §23.6) ==
const retention: any[] = [
  { ref: 'RR-0001', title_fa: 'قرارداد و توافق: ۷ سال پس از پایان', trigger: 'field:end', keep: { years: 7 }, then: 'dispose_card' },
  { ref: 'RR-0002', title_fa: 'فاکتور: ۷ سال پس از تاریخ فاکتور', trigger: 'field:date', keep: { years: 7 }, then: 'dispose_card' },
  { ref: 'RR-0003', title_fa: 'مجوز و دامنه: ۲ سال پس از انقضا', trigger: 'field:expires_at', keep: { years: 2 }, then: 'dispose_card' },
  { ref: 'RR-0004', title_fa: 'مکاتبه‌ی حقوقی: ۱۰ سال پس از بسته شدن پرونده', trigger: 'case_closed', keep: { years: 10 }, then: 'review' },
  { ref: 'RR-0005', title_fa: 'دائمی: ثبت، اساسنامه، نشان، مصوبه', trigger: 'filed', keep: 'permanent', then: 'review' },
  { ref: 'RR-0006', title_fa: 'سایر: بازبینی پس از ۳ سال', trigger: 'filed', keep: { years: 3 }, then: 'review' },
].map((r) => ({ ...r, version: 1, status: 'active' }));
const reminderRules: any[] = [
  { ref: 'RM-0001', class: 'contract', field: 'end', lead_days: [60, 30, 7], to: 'owner', channel: 'cartable' },
  { ref: 'RM-0002', class: 'license', field: 'expires_at', lead_days: [90, 30, 7], to: 'owner', channel: 'cartable' },
  { ref: 'RM-0003', class: 'domain', field: 'expires_at', lead_days: [90, 30, 7], to: 'owner', channel: 'cartable' },
  { ref: 'RM-0004', class: 'affiliate_agreement', field: 'review_at', lead_days: [30, 7], to: { company_ceo: true }, channel: 'cartable' },
].map((r) => ({ ...r, version: 1, status: 'active' }));

// ============================================================ automations and sources (§23.7, §23.8) ==
const automations: any[] = [
  { ref: 'AU-0001', title_fa: 'مکاتبه‌ی حقوقی به پوشه‌ی مکاتبات و دست‌کم محرمانه', on: 'filed', when: { class: 'legal_correspondence' },
    do: [{ action: 'raise_level', args: { level: 'confidential' } }, { action: 'move_to_folder', args: { folder: 'FP-0023' } }], runs_30d: 2, last_run_at: iso(60 * 50) },
  { ref: 'AU-0002', title_fa: 'فاکتور بالای ۵۰۰ یورو: گزارش به مدیر کل', on: 'filed', when: { class: 'invoice', field: { key: 'amount', op: 'gt', value: 500 } },
    do: [{ action: 'notify', args: { to: 'owner', level: 'report', text_fa: 'فاکتور بزرگ بایگانی شد' } }], runs_30d: 0, last_run_at: null },
  { ref: 'AU-0003', title_fa: 'توقیف تازه: بایگان پوشش را بررسی کند', on: 'hold_set', when: {},
    do: [{ action: 'work_item', args: { role: 'archivist', title_fa: 'بررسی پوشش توقیف تازه' } }], runs_30d: 2, last_run_at: iso(300) },
].map((a) => ({ ...a, version: 1, status: 'active' }));
const sources: any[] = [
  ['charter_sealed', 'هر نسخه‌ی مُهرشده‌ی اساسنامه', 'sealed_policy', true, 1, iso(60 * 46)],
  ['resolution_month', 'PDF مصوبه‌های مُهرشده‌ی هر ماه', 'resolution_bundle', true, 0, null],
  ['brand_sealed', 'نشان و مُهر مُهرشده', 'brand_asset', true, 0, null],
  ['founding_registration', 'پیشنهاد مُهرشده‌ی تأسیس شرکت', 'company_registration', true, 0, null],
  ['legal_email', 'هر ایمیل فرستاده‌ی مشاور حقوقی و پرونده‌اش', 'legal_correspondence', true, 2, iso(60 * 50)],
  ['case_closed', 'بسته شدن پرونده‌ی حقوقی', 'legal_correspondence', true, 0, null],
  ['server_plan_sealed', 'طرح سرور مُهرشده', 'other', false, 0, null],
  ['backup_restore_test', 'نتیجه‌ی ماهانه‌ی آزمون بازگردانی پشتیبان', 'other', true, 0, null],
].map(([key, title_fa, cls, enabled, filed, last_at]) => ({ key, title_fa, class: cls, enabled, filed, last_at, note_fa: key === 'server_plan_sealed' ? 'خاموش به خواست مالک؛ طرح سرور در صفحه‌ی تأسیس میماند.' : null }));

// ============================================================ files (§23.1) ==
type StoredFile = { file_id: string; name: string; mime: string; url: string; size_bytes: number; sha256: string; pages: number | null; text_state: string; ocr_confidence: number | null; text: string; destroyed?: boolean };
const store = new Map<string, StoredFile>();
const demo = (name: string, text: string, o: Partial<StoredFile> = {}) => {
  const f: StoredFile = { file_id: `arf-${name.replace(/\.[a-z]+$/, '')}`, name, mime: name.endsWith('.webp') ? 'image/webp' : 'application/pdf', url: `/demo/archive/${name}`, size_bytes: 0, sha256: '', pages: name.endsWith('.pdf') ? 1 : null, text_state: 'text_layer', ocr_confidence: null, text, ...o };
  store.set(f.file_id, f);
  return f.file_id;
};
const ocr = (c: number) => ({ text_state: 'ocr', ocr_confidence: c });
const regText = (name: string, kind: string, no: string, nid: string, date: string, subject: string) => `اداره‌ی ثبت شرکت‌ها آگهی تأسیس ${kind} نام شرکت ${name} شماره‌ی ثبت ${no} شناسه‌ی ملی ${nid} تاریخ ثبت ${date} موضوع فعالیت ${subject}`;
const FILE = {
  hqReg: demo('hq-registration.pdf', regText('هلدینگ کوینه‌پرو', 'شرکت سهامی خاص', '58214', '14012345678', '1405/05/12', 'سرمایه‌گذاری و اداره‌ی شرکت‌های فناوری مالی'), ocr(0.91)),
  tyReg: demo('ty-registration.pdf', regText('تریدیار', 'شرکت با مسئولیت محدود', '58377', '14012399120', '1405/05/26', 'آموزش و ابزار تحلیل بازار'), ocr(0.9)),
  fxReg: demo('fx-registration.pdf', regText('کوینه‌پرو FX', 'شرکت با مسئولیت محدود', '58402', '14012407731', '1405/06/02', 'سیگنال و تحلیل بازارهای مالی'), ocr(0.89)),
  pcReg: demo('pc-registration.pdf', regText('پرو-چارت', 'شرکت با مسئولیت محدود', '58466', '14012418856', '1405/06/09', 'نرم‌افزار نمودار و ترمینال معاملاتی'), ocr(0.88)),
  charter: demo('hq-charter-v3.pdf', 'اساسنامه‌ی هلدینگ نسخه‌ی ۳ مُهرشده با اثر انگشت مدیر کل. اول قاعده، آخر هوش مصنوعی. هیچ پرداخت، امضا یا تعهدی بی‌مُهر مدیر کل انجام نمیشود. داده‌ی هر شرکت جداست. هر سند بایگانی پس از مُهر تغییر نمیکند؛ اصلاح، نسخه‌ی تازه است.'),
  lease: demo('scan-office-lease.webp', 'قرارداد اجاره اجاره‌نامه‌ی دفتر تهران موجر مالک نمونه مستأجر هلدینگ کوینه‌پرو مدت از 1405/07/01 تا 1406/06/31 اجاره‌ی ماهانه 180,000,000 ریال ودیعه 1,500,000,000 ریال', ocr(0.78)),
  lbank: demo('lbank-affiliate-2026.pdf', 'AFFILIATE AGREEMENT LBank Exchange Affiliate Program CoinePro FX Partner tier Commission 40% of trading fees of referred users Start 2026-04-01 term 12 months review every 6 months referral links risk warning commission paid monthly in USDT'),
  lbankAm: demo('lbank-affiliate-amendment-1.pdf', 'AMENDMENT No. 1 TO THE AFFILIATE AGREEMENT CoinePro FX effective 2026-09-01 commission rises from 40% to 45% sub-affiliate share 5%'),
  inv0826: demo('hetzner-R2026-08.pdf', 'INVOICE Hetzner Online GmbH invoice number R0026081422 invoice date 2026-08-01 CoinePro Holding cloud server CPX42 primary IPv4 backups total EUR 38.10'),
  inv0926: demo('hetzner-R2026-09.pdf', 'INVOICE Hetzner Online GmbH invoice number R0026094107 invoice date 2026-09-01 CoinePro Holding cloud server CPX42 primary IPv4 backups total EUR 38.10'),
  inv1026: demo('hetzner-R2026-10.pdf', 'INVOICE Hetzner Online GmbH invoice number R0026105533 invoice date 2026-10-01 CoinePro Holding cloud server CPX42 primary IPv4 backups total EUR 38.10'),
  inv0918: demo('hetzner-R2018-09.pdf', 'INVOICE Hetzner Online GmbH invoice number R0018092201 invoice date 2018-09-01 total EUR 11.90'),
  inv1218: demo('hetzner-R2018-12.pdf', 'INVOICE Hetzner Online GmbH invoice number R0018120587 invoice date 2018-12-01 total EUR 11.90'),
  inv0219: demo('hetzner-R2019-02.pdf', 'INVOICE Hetzner Online GmbH invoice number R0019020344 invoice date 2019-02-01 total EUR 11.90'),
  domain: demo('domain-coinepro-com-renewal.pdf', 'DOMAIN RENEWAL NOTICE coinepro.com registrant CoinePro Holding expires auto-renew OFF renewal price USD 11.20 per year redemption period'),
  license: demo('charting-license-2026.pdf', 'COMMERCIAL LICENCE charting library Pro-Chart licence number CL-PC-2026-0417 issued 2026-03-10 expires 2027-03-10 Android app and web terminal unlimited end users USD 2,400 per year attribution'),
  emailOut: demo('lc-0001-email-out-1.pdf', 'Instagram business account cannot reply to messages CoinePro FX legal@coinepro.com appeals@platform-support.example sealed by D-000083 in-app review form policy restriction'),
  emailIn: demo('lc-0001-email-in-1.pdf', 'Re: Instagram business account cannot reply to messages case 4471-DEMO review within 5 business days'),
  sha: demo('shareholders-agreement.pdf', "SHAREHOLDERS' AGREEMENT founder holding transfer only with board seal pre-emption right vesting 36 months cliff drag-along tag-along level SECRET"),
};
const fileOut = (f: StoredFile) => ({ file_id: f.file_id, name: f.name, mime: f.mime, size_bytes: f.size_bytes, sha256: f.sha256, pages: f.pages, text_state: f.text_state, ocr_confidence: f.ocr_confidence });
const manifestOf = (ids: string[]) => sha256(ids.map((id) => store.get(id)!).map((f) => `${f.sha256}  ${f.name}`).sort().join('\n'));

// ============================================================ records (§23.1) ==
const ver = (n: number, files: string[], at: number, o: Record<string, unknown> = {}) => ({ n, files, manifest_sha256: '', note_fa: null, created_by: owner, created_at: iso(at), sealed: false, state: 'current', ...o });
const R = (o: any) => ({
  id: `ar-${o.ref}`, folder: null, level: 'internal', state: 'filed', parties: [], links: [], metadata: {}, source: { kind: 'owner', ref: null }, created_by: owner,
  filed_at: o.state === 'draft' ? null : iso(o.at - 1), sealed_at: null, version: 1, class_version: o.class ? 1 : null, suggestion: null, created_at: iso(o.at), ...o,
});
const money = (amount: string, currency: string) => ({ amount, currency });
const records: any[] = [
  R({ ref: 'AR-000101', scope: 'HQ', class: 'company_registration', title_fa: 'آگهی تأسیس هلدینگ کوینه‌پرو', folder: 'FP-0002', state: 'sealed', at: 60 * 24 * 5, sealed_at: iso(60 * 24 * 4),
    metadata: { reg_no: '58214', national_id: '14012345678', reg_date: '2026-08-03', registry: 'PT-0004', company: 'HQ', subject_fa: 'سرمایه‌گذاری و اداره‌ی شرکت‌های فناوری مالی', capital: money('1000000000', 'IRR') },
    parties: [{ party: 'PT-0004', role_fa: 'مرجع ثبت' }], versions: [ver(1, [FILE.hqReg], 60 * 24 * 5, { sealed: true })] }),
  R({ ref: 'AR-000102', scope: 'TY', class: 'company_registration', title_fa: 'آگهی تأسیس تریدیار', folder: 'FP-0011', state: 'sealed', at: 60 * 24 * 5 - 20, sealed_at: iso(60 * 24 * 4 - 20),
    metadata: { reg_no: '58377', national_id: '14012399120', reg_date: '2026-08-17', registry: 'PT-0004', company: 'TY', subject_fa: 'آموزش و ابزار تحلیل بازار', capital: money('200000000', 'IRR') },
    parties: [{ party: 'PT-0004', role_fa: 'مرجع ثبت' }], versions: [ver(1, [FILE.tyReg], 60 * 24 * 5 - 20, { sealed: true })] }),
  R({ ref: 'AR-000103', scope: 'FX', class: 'company_registration', title_fa: 'آگهی تأسیس کوینه‌پرو FX', folder: 'FP-0021', state: 'sealed', at: 60 * 24 * 5 - 40, sealed_at: iso(60 * 24 * 4 - 40),
    metadata: { reg_no: '58402', national_id: '14012407731', reg_date: '2026-08-24', registry: 'PT-0004', company: 'FX', subject_fa: 'سیگنال و تحلیل بازارهای مالی', capital: money('200000000', 'IRR') },
    parties: [{ party: 'PT-0004', role_fa: 'مرجع ثبت' }], versions: [ver(1, [FILE.fxReg], 60 * 24 * 5 - 40, { sealed: true })] }),
  R({ ref: 'AR-000104', scope: 'PC', class: 'company_registration', title_fa: 'آگهی تأسیس پرو-چارت', folder: 'FP-0031', at: 60 * 24 * 5 - 60,
    metadata: { reg_no: '58466', national_id: '14012418856', reg_date: '2026-08-31', registry: 'PT-0004', company: 'PC', subject_fa: 'نرم‌افزار نمودار و ترمینال معاملاتی', capital: money('200000000', 'IRR') },
    parties: [{ party: 'PT-0004', role_fa: 'مرجع ثبت' }], versions: [ver(1, [FILE.pcReg], 60 * 24 * 5 - 60)] }),
  R({ ref: 'AR-000110', scope: 'FX', class: 'affiliate_agreement', class_version: 1, title_fa: 'توافق افیلیت صرافی ال‌بنک', folder: 'FP-0022', level: 'confidential', at: 60 * 24 * 4, sealed_at: null,
    metadata: { exchange: 'PT-0001', commission: 45, start: '2026-04-01', end: '2027-03-31', review_at: dOff(45), referral_link: 'https://www.lbank.com/ref/DEMO-FX', account_id: '88412907', tier: 'partner' },
    parties: [{ party: 'PT-0001', role_fa: 'صرافی' }],
    versions: [ver(1, [FILE.lbank], 60 * 24 * 4, { sealed: true, state: 'superseded' }), ver(2, [FILE.lbank, FILE.lbankAm], 60 * 24 * 2, { note_fa: 'الحاقیه‌ی ۱: کمیسیون از ۴۰٪ به ۴۵٪.' })], current_version: 2, version: 3 }),
  R({ ref: 'AR-000120', scope: 'HQ', class: 'invoice', title_fa: 'فاکتور هتزنر، مرداد ۱۴۰۵', folder: 'FP-0005', state: 'sealed', at: 60 * 24 * 3, sealed_at: iso(60 * 24 * 3 - 30),
    metadata: { vendor: 'PT-0002', number: 'R0026081422', date: '2026-08-01', amount: money('38.10', 'EUR'), period: { from: '2026-07-01', to: '2026-07-31' }, paid: true, category: 'hosting' },
    parties: [{ party: 'PT-0002', role_fa: 'فروشنده' }], versions: [ver(1, [FILE.inv0826], 60 * 24 * 3, { sealed: true })] }),
  R({ ref: 'AR-000121', scope: 'HQ', class: 'invoice', title_fa: 'فاکتور هتزنر، شهریور ۱۴۰۵', folder: 'FP-0005', at: 60 * 24 * 3 - 5,
    metadata: { vendor: 'PT-0002', number: 'R0026094107', date: '2026-09-01', amount: money('38.10', 'EUR'), period: { from: '2026-08-01', to: '2026-08-31' }, paid: true, category: 'hosting' },
    parties: [{ party: 'PT-0002', role_fa: 'فروشنده' }], versions: [ver(1, [FILE.inv0926], 60 * 24 * 3 - 5)] }),
  R({ ref: 'AR-000122', scope: 'HQ', class: 'invoice', title_fa: 'فاکتور هتزنر، مهر ۱۴۰۵', folder: 'FP-0005', at: 60 * 24 * 3 - 10,
    metadata: { vendor: 'PT-0002', number: 'R0026105533', date: '2026-10-01', amount: money('38.10', 'EUR'), period: { from: '2026-09-01', to: '2026-09-30' }, paid: true, category: 'hosting' },
    parties: [{ party: 'PT-0002', role_fa: 'فروشنده' }], versions: [ver(1, [FILE.inv1026], 60 * 24 * 3 - 10)] }),
  ...[['AR-000090', FILE.inv0918, 'R0018092201', '2018-09-01', 'شهریور ۱۳۹۷'], ['AR-000091', FILE.inv1218, 'R0018120587', '2018-12-01', 'آذر ۱۳۹۷'], ['AR-000092', FILE.inv0219, 'R0019020344', '2019-02-01', 'بهمن ۱۳۹۷']].map(([ref, file, number, date, month], i) =>
    R({ ref, scope: 'HQ', class: 'invoice', title_fa: `فاکتور قدیمی هتزنر، ${month}`, folder: 'FP-0005', at: 60 * 24 * 6 - i * 3,
      metadata: { vendor: 'PT-0002', number, date, amount: money('11.90', 'EUR'), paid: true, category: 'hosting' }, parties: [{ party: 'PT-0002', role_fa: 'فروشنده' }],
      versions: [ver(1, [file!], 60 * 24 * 6 - i * 3, { note_fa: 'از حسابداری پیش از تأسیس هلدینگ وارد شد.' })] })),
  R({ ref: 'AR-000130', scope: 'HQ', class: 'domain', title_fa: 'دامنه‌ی coinepro.com', folder: 'FP-0007', at: 60 * 24 * 3 - 30,
    metadata: { domain: 'coinepro.com', registrar: 'PT-0003', expires_at: dOff(25), auto_renew: false, dns_provider: 'Cloudflare' },
    parties: [{ party: 'PT-0003', role_fa: 'ثبت‌کننده' }], versions: [ver(1, [FILE.domain], 60 * 24 * 3 - 30)] }),
  R({ ref: 'AR-000140', scope: 'PC', class: 'license', title_fa: 'لایسنس تجاری کتابخانه‌ی نمودار', folder: 'FP-0032', state: 'sealed', at: 60 * 24 * 3 - 50, sealed_at: iso(60 * 24 * 2),
    metadata: { issuer: 'PT-0007', license_no: 'CL-PC-2026-0417', issued_at: '2026-03-10', expires_at: '2027-03-10', scope_fa: 'اپ اندروید و ترمینال وب، بدون سقف کاربر', cost: money('2400', 'USD') },
    parties: [{ party: 'PT-0007', role_fa: 'صادرکننده' }], versions: [ver(1, [FILE.license], 60 * 24 * 3 - 50, { sealed: true })] }),
  R({ ref: 'AR-000150', scope: 'FX', class: 'legal_correspondence', title_fa: 'ایمیل اول به پشتیبانی تجاری اینستاگرام', folder: 'FP-0023', level: 'confidential', at: 60 * 72 - 2, created_by: system,
    source: { kind: 'system', ref: 'legal_email' },
    metadata: { case: { kind: 'case', ref: 'LC-0001' }, direction: 'out', counterpart: 'PT-0005', date: dOff(-3), subject_en: 'Instagram business account cannot reply to messages — CoinePro FX', decision: { kind: 'decision', ref: 'D-000083' } },
    parties: [{ party: 'PT-0005', role_fa: 'گیرنده' }], links: [{ kind: 'about', to: { kind: 'case', ref: 'LC-0001' }, at: iso(60 * 72 - 2), by: system }, { kind: 'evidence_for', to: { kind: 'decision', ref: 'D-000083' }, at: iso(60 * 72 - 2), by: system }],
    versions: [ver(1, [FILE.emailOut], 60 * 72 - 2, { created_by: system })] }),
  R({ ref: 'AR-000151', scope: 'FX', class: 'legal_correspondence', title_fa: 'جواب خودکار پشتیبانی: پرونده‌ی 4471-DEMO', folder: 'FP-0023', level: 'confidential', at: 60 * 50 - 2, created_by: system,
    source: { kind: 'system', ref: 'legal_email' },
    metadata: { case: { kind: 'case', ref: 'LC-0001' }, direction: 'in', counterpart: 'PT-0005', date: dOff(-2), subject_en: 'Re: Instagram business account cannot reply to messages — CoinePro FX' },
    parties: [{ party: 'PT-0005', role_fa: 'فرستنده' }], links: [{ kind: 'about', to: { kind: 'case', ref: 'LC-0001' }, at: iso(60 * 50 - 2), by: system }],
    versions: [ver(1, [FILE.emailIn], 60 * 50 - 2, { created_by: system })] }),
  R({ ref: 'AR-000160', scope: 'HQ', class: 'sealed_policy', title_fa: 'اساسنامه‌ی هلدینگ، نسخه‌ی ۳', folder: 'FP-0002', at: 60 * 46, created_by: system, source: { kind: 'system', ref: 'charter_sealed' },
    metadata: { policy_ref: 'holding@3', version: 3, sealed_on: dOff(-2) }, versions: [ver(1, [FILE.charter], 60 * 46, { created_by: system })] }),
  R({ ref: 'AR-000170', scope: 'HQ', class: null, class_version: null, title_fa: 'اسکن: اجاره‌نامه‌ی دفتر تهران', state: 'draft', at: 60 * 7,
    suggestion: { class: 'contract', title_fa: 'اجاره‌نامه‌ی دفتر تهران', metadata: { subject: 'اجاره‌ی دفتر تهران', start: '2026-09-23', end: '2027-09-22', value: money('180000000', 'IRR') }, parties: [], by: 'rules',
      note_fa: 'از تاریخ‌ها و مبلغ‌های متن OCR پیدا شد؛ موجر در رجیستری طرف‌ها نیست و واحد مبلغ با فیلد قرارداد (USD) نمیخواند.' },
    versions: [ver(1, [FILE.lease], 60 * 7, { note_fa: 'ورود دسته‌ای مالک' })] }),
  R({ ref: 'AR-000180', scope: 'HQ', class: 'contract', title_fa: 'توافق سهامداران', folder: 'FP-0003', level: 'secret', state: 'sealed', at: 60 * 24 * 4 - 90, sealed_at: iso(60 * 24 * 4 - 100),
    metadata: { counterparty: 'PT-0008', subject: 'انتقال سهام، حق تقدم و vesting', start: '2026-06-02', auto_renew: false },
    parties: [{ party: 'PT-0008', role_fa: 'سهامدار' }], versions: [ver(1, [FILE.sha], 60 * 24 * 4 - 90, { sealed: true })] }),
].map((r) => ({ current_version: r.versions.length, ...r }));
const recordOf = (ref: string) => records.find((r) => r.ref === ref);

// ============================================================ holds (§23.5) ==
const holds: any[] = [
  { ref: 'LH-0001', title_fa: 'پرونده‌ی محدودیت اینستاگرام FX', case: 'LC-0001', reason_md: 'تا بسته شدن پرونده‌ی **LC-0001** هر مکاتبه با پشتیبانی اینستاگرام دست‌نخورده بماند.',
    scope: { classes: ['legal_correspondence'], parties: ['PT-0005'] }, state: 'active', placed_by: counsel, placed_at: iso(60 * 49), released_at: null },
  { ref: 'LH-0002', title_fa: 'ممیزی مالیاتی حساب قدیمی هتزنر', case: null, reason_md: 'تا پایان ممیزی مالیاتی سال ۱۳۹۷، فاکتور بهمن نگه داشته شود؛ بقیه‌ی فاکتورهای قدیمی بیرون از این توقیف‌اند.',
    scope: { records: ['AR-000092'] }, state: 'active', placed_by: owner, placed_at: iso(300), released_at: null },
];
const descendants = (ref: string): string[] => [ref, ...folders.filter((f) => f.parent === ref).flatMap((f) => descendants(f.ref))];
function covers(h: any, r: any): boolean {
  const s = h.scope ?? {};
  if (s.records?.includes(r.ref)) return true;
  const facets = ['folders', 'classes', 'parties'].filter((k) => s[k]?.length).length + (s.from || s.to ? 1 : 0);
  if (!facets) return false;
  if (s.folders?.length && !s.folders.flatMap(descendants).includes(r.folder)) return false;
  if (s.classes?.length && !s.classes.includes(r.class)) return false;
  if (s.parties?.length && !r.parties.some((p: any) => s.parties.includes(p.party))) return false;
  const d = docDate(r);
  if (s.from && (!d || d < s.from)) return false;
  if (s.to && (!d || d > s.to)) return false;
  return true;
}
const holdsOf = (r: any) => holds.filter((h) => h.state === 'active' && covers(h, r)).map((h) => h.ref);

// ============================================================ rules by code: dates, retention, reminders ==
function docDate(r: any): string | null {
  const c = classOf(r.class);
  for (const f of c?.fields ?? []) if (f.type === 'date' && typeof r.metadata[f.key] === 'string') return r.metadata[f.key];
  return (r.filed_at ?? r.created_at)?.slice(0, 10) ?? null;
}
const dateField = (r: any, key: string): string | null => {
  const v = r.metadata?.[key];
  if (typeof v === 'string' && DATE_RE.test(v)) return v;
  if (v && typeof v === 'object' && typeof v.to === 'string') return v.to;
  return null;
};
const addKeep = (d: string, keep: any) => { const x = new Date(`${d}T00:00:00Z`); x.setUTCFullYear(x.getUTCFullYear() + (keep.years ?? 0)); x.setUTCMonth(x.getUTCMonth() + (keep.months ?? 0)); return x.toISOString().slice(0, 10); };
const daysTo = (d: string) => Math.round((Date.parse(`${d}T00:00:00Z`) - Date.parse(`${dOff(0)}T00:00:00Z`)) / DAY);
function retentionOf(r: any) {
  const rule = retention.find((x) => x.ref === classOf(r.class)?.retention && x.status === 'active') ?? null;
  if (!rule) return { rule: null, trigger_at: null, review_at: null, disposable: false, due_at: null, then: null };
  let trigger: string | null = null;
  if (rule.trigger === 'filed') trigger = r.filed_at?.slice(0, 10) ?? null;
  else if (rule.trigger.startsWith('field:')) trigger = dateField(r, rule.trigger.slice(6));
  // case_closed and superseded wait for their event.
  const due = rule.keep === 'permanent' || !trigger ? null : addKeep(trigger, rule.keep);
  const ended = !!due && due <= dOff(0) && r.state !== 'draft' && r.state !== 'disposed';
  return { rule: rule.ref, trigger_at: trigger, review_at: rule.then === 'review' ? due : null, disposable: ended && rule.then === 'dispose_card' && !holdsOf(r).length, due_at: due, then: rule.then };
}
const remindersDone = new Set<string>();
function remindersOf(r: any) {
  if (r.state === 'draft' || r.state === 'disposed') return [];
  const out: any[] = [];
  for (const rule of reminderRules.filter((x) => x.status === 'active' && x.class === r.class)) {
    const at = dateField(r, rule.field);
    if (!at) continue;
    const left = daysTo(at);
    const leads = [...rule.lead_days].sort((a: number, b: number) => b - a);
    const reached = leads.filter((l: number) => left <= l);
    const id = `${r.ref}:${rule.field}`;
    const state = remindersDone.has(id) ? 'done' : reached.length && left >= -30 ? 'sent' : 'pending';
    out.push({ field: rule.field, at, lead_days: reached.length ? Math.min(...reached) : leads[leads.length - 1] ?? 0, state, rule: rule.ref, id, left });
  }
  for (const x of r.extra_reminders ?? []) out.push({ ...x, id: `${r.ref}:${x.field}`, left: daysTo(x.at) });
  return out;
}

// ============================================================ search (§23.9) ==
/** The deterministic Persian normaliser (hq_common.persian), reduced: Arabic letters and digits, diacritics, ZWNJ, case. */
const norm = (s: string) => s.toLowerCase()
  .replace(/[يى]/g, 'ی').replace(/ك/g, 'ک').replace(/ة/g, 'ه').replace(/[أإآ]/g, 'ا').replace(/ؤ/g, 'و')
  .replace(/[ً-ْٰـ]/g, '').replace(/[‌‏‎]/g, ' ')
  .replace(/[۰-۹]/g, (d) => String('۰۱۲۳۴۵۶۷۸۹'.indexOf(d))).replace(/[٠-٩]/g, (d) => String('٠١٢٣٤٥٦٧٨٩'.indexOf(d)))
  .replace(/\s+/g, ' ');
const searchableText = (r: any) => {
  const c = classOf(r.class);
  const fields = (c?.fields ?? []).filter((f: any) => f.searchable || ['party', 'text'].includes(f.type)).map((f: any) => {
    const v = r.metadata[f.key];
    if (f.type === 'party') return partyOf(v) ? `${partyOf(v).name_fa} ${partyOf(v).name_en ?? ''}` : '';
    return typeof v === 'string' || typeof v === 'number' ? String(v) : '';
  });
  return fields.join(' ');
};
const fileText = (r: any) => (r.versions.find((v: any) => v.n === r.current_version)?.files ?? []).map((id: string) => store.get(id)?.text ?? '').join(' ');
function scoreOf(r: any, q: string): { score: number; snippet: string } | null {
  const terms = norm(q).split(' ').filter((t) => t.length >= 2);
  if (!terms.length) return null;
  const title = norm(r.title_fa), fields = norm(searchableText(r)), text = fileText(r), nt = norm(text);
  let score = 0;
  for (const t of terms) {
    const s = (title.includes(t) ? 3 : 0) + (fields.includes(t) ? 2 : 0) + (nt.includes(t) ? 1 : 0);
    if (!s) return null;
    score += s;
  }
  // The snippet comes only from text this reader may see (the reader already passed the clearance check).
  const t0 = terms[0]!;
  const src = nt.includes(t0) ? text : fields.includes(t0) ? searchableText(r) : r.title_fa;
  const at = norm(src).indexOf(t0);
  const from = Math.max(0, at - 50);
  const snippet = `${from > 0 ? '… ' : ''}${src.slice(from, from + 150).trim()}${from + 150 < src.length ? ' …' : ''}`;
  return { score: Math.round(score * 10) / 10, snippet };
}

// ============================================================ output ==
function linksOf(r: any) {
  const own = r.links.map((l: any) => ({ ...l, title_fa: l.to.kind === 'record' ? recordOf(l.to.ref)?.title_fa ?? null : null }));
  const inverse = records.filter((x) => x !== r && canSee(x)).flatMap((x) => x.links.filter((l: any) => l.to.kind === 'record' && l.to.ref === r.ref).map((l: any) => ({ kind: l.kind, to: { kind: 'record', ref: x.ref }, at: l.at, by: l.by, sealed: l.sealed, title_fa: x.title_fa, inverse: true })));
  return [...own, ...inverse];
}
function recordOut(r: any) {
  const ret = retentionOf(r);
  const { extra_reminders: _x, tombstone, ...rest } = r;
  return {
    ...rest, holds: holdsOf(r), links: linksOf(r), doc_date: docDate(r), masked: [],
    retention: { rule: ret.rule, trigger_at: ret.trigger_at, review_at: ret.review_at, disposable: ret.disposable },
    reminders: remindersOf(r).map(({ field, at, lead_days, state }) => ({ field, at, lead_days, state })),
    versions: r.versions.map((v: any) => ({ ...v, files: v.files.map((id: string) => fileOut(store.get(id)!)) })),
    ...(tombstone ? { tombstone } : {}),
  };
}

// ============================================================ validation against the class (§23.2) ==
const isEmpty = (v: unknown) => v == null || v === '' || (Array.isArray(v) && !v.length) || (typeof v === 'object' && !Array.isArray(v) && v && 'amount' in (v as object) && !(v as any).amount);
function valueProblem(f: any, v: any, scopes: string[]): string | null {
  switch (f.type) {
    case 'text': return typeof v === 'string' && v.length <= 500 ? null : 'متن کوتاه (تا ۵۰۰ نویسه)';
    case 'long_text': return typeof v === 'string' && v.length <= 10_000 ? null : 'متن';
    case 'number': return typeof v === 'number' && Number.isFinite(v) ? null : 'عدد';
    case 'percent': return typeof v === 'number' && v >= 0 && v <= 100 ? null : 'درصد بین 0 و 100';
    case 'money': return v && typeof v.amount === 'string' && /^-?\d+(\.\d{1,8})?$/.test(v.amount) && (!f.currency || v.currency === f.currency) ? null : `مبلغ به ${f.currency ?? 'واحد'}`;
    case 'date': return typeof v === 'string' && DATE_RE.test(v) ? null : 'تاریخ';
    case 'date_range': return v && DATE_RE.test(v.from ?? '') && DATE_RE.test(v.to ?? '') && v.from <= v.to ? null : 'بازه‌ی تاریخ (از ≤ تا)';
    case 'enum': return (f.options ?? []).some((o: any) => o.key === v) ? null : 'یکی از گزینه‌ها';
    case 'multi_enum': return Array.isArray(v) && v.every((x) => (f.options ?? []).some((o: any) => o.key === x)) ? null : 'از گزینه‌ها';
    case 'boolean': return typeof v === 'boolean' ? null : 'بله یا نه';
    case 'party': return partyOf(v) ? null : 'طرفی از رجیستری';
    case 'company': return scopes.includes(v) ? null : 'شرکتی از هلدینگ';
    case 'ref': return v && (f.ref_kinds ?? []).includes(v.kind) && typeof v.ref === 'string' && v.ref.trim() ? null : `ارجاع ${(f.ref_kinds ?? []).join('/')}`;
    case 'url': return typeof v === 'string' && /^https?:\/\/\S+$/.test(v) ? null : 'نشانی http یا https';
    case 'email': return typeof v === 'string' && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v) ? null : 'ایمیل';
    case 'phone': return typeof v === 'string' && /^\+?[0-9 ()-]{6,20}$/.test(v) ? null : 'تلفن';
    case 'id_code': return typeof v === 'string' && /^[A-Za-z0-9-]{3,40}$/.test(v) ? null : 'شناسه (حرف و عدد لاتین)';
    case 'iban': return typeof v === 'string' && /^[A-Z]{2}\d{2}[A-Z0-9]{10,30}$/.test(v.replace(/\s/g, '')) ? null : 'شبا (IR و ۲۴ رقم)';
    default: return 'نوع ناشناخته';
  }
}
function metadataProblems(c: any, md: Record<string, unknown>, filing: boolean, scopes: string[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (const f of c.fields) {
    const v = md[f.key];
    if (isEmpty(v)) { if (filing && f.required && f.status === 'active') out[`metadata.${f.key}`] = `«${f.title_fa}» لازم است`; continue; }
    const why = valueProblem(f, v, scopes);
    if (why) out[`metadata.${f.key}`] = `«${f.title_fa}»: ${why}`;
  }
  for (const k of Object.keys(md)) if (!c.fields.some((f: any) => f.key === k)) out[`metadata.${k}`] = 'این فیلد در این نوع سند نیست';
  return out;
}
const cleanMeta = (md: Record<string, unknown>) => Object.fromEntries(Object.entries(md ?? {}).filter(([, v]) => !isEmpty(v)));

// ============================================================ uploads: secret scan, hashes, text ==
type Ctx = { decisions: any[]; employees: any[]; files: Map<string, any> };
let ctx: Ctx | null = null;
/** A file the owner just uploaded (§17.1): its bytes are read here for the secret scan, the hash and a text layer. */
async function intake(id: string): Promise<StoredFile | { secret: string; name: string }> {
  const known = store.get(id);
  if (known) return known;
  const meta = ctx?.files.get(id) ?? {};
  let buf = new ArrayBuffer(0);
  try { buf = await (await fetch(id)).arrayBuffer(); } catch { /* not readable: an empty demo file */ }
  const name = String(meta.name ?? 'file');
  const mime = String(meta.mime || 'application/octet-stream');
  const raw = new TextDecoder('utf-8', { fatal: false }).decode(buf.slice(0, 200_000));
  const hit = SECRET_RE.exec(`${name}\n${raw}`);
  if (hit) return { secret: hit[0], name };
  const pdf = mime === 'application/pdf';
  const textLayer = pdf ? /\/Font\b/.test(raw) : mime.startsWith('text/');
  const text = mime.startsWith('text/') ? raw.slice(0, 4000) : pdf ? (raw.match(/\(([^)]{3,})\)\s*Tj/g) ?? []).map((m) => m.replace(/^\(|\)\s*Tj$/g, '')).join(' ') : '';
  const f: StoredFile = {
    file_id: id, name, mime, url: id, size_bytes: buf.byteLength || Number(meta.size ?? 0), sha256: await sha256(buf), pages: pdf ? Math.max(1, (raw.match(/\/Type\s*\/Page\b/g) ?? []).length) : null,
    text_state: textLayer ? 'text_layer' : mime.startsWith('image/') || pdf ? 'ocr' : 'none', ocr_confidence: !textLayer && (mime.startsWith('image/') || pdf) ? 0.84 : null, text,
  };
  store.set(id, f);
  return f;
}
async function intakeAll(ids: string[]): Promise<StoredFile[] | Response> {
  const out: StoredFile[] = [];
  for (const id of ids) {
    const f = await intake(id);
    // Refused before anything is stored or logged: only the file's name and the pattern's kind come back.
    if ('secret' in f) return problem(422, 'secret_in_document', `در «${f.name}» الگوی رمز، کلید خصوصی یا عبارت بازیابی پیدا شد؛ فایل ذخیره نشد.`, { fields: { [f.name]: 'secret_pattern' } });
    out.push(f);
  }
  return out;
}
/** Rules first (§23.9): the class from words in the name and text, dates and amounts from the text, known parties from the registry. */
function suggest(fs: StoredFile[]) {
  const all = norm(fs.map((f) => `${f.name} ${f.text}`).join(' '));
  const cls = /invoice|فاکتور|رسید/.test(all) ? 'invoice' : /affiliate|افیلیت/.test(all) ? 'affiliate_agreement' : /licen[cs]e|مجوز|لایسنس/.test(all) ? 'license'
    : /domain|دامنه/.test(all) ? 'domain' : /agreement|contract|قرارداد|اجاره/.test(all) ? 'contract' : /ثبت شرکت|آگهی تاسیس/.test(all) ? 'company_registration' : null;
  const known = parties.filter((p) => all.includes(norm(p.name_fa)) || (p.name_en && all.includes(norm(p.name_en).split(' ')[0]!)));
  const date = /(\d{4}-\d{2}-\d{2})/.exec(all)?.[1];
  const metadata: Record<string, unknown> = {};
  const c = classOf(cls);
  if (c && date) { const df = c.fields.find((f: any) => f.type === 'date'); if (df) metadata[df.key] = date; }
  if (c && known[0]) { const pf = c.fields.find((f: any) => f.type === 'party'); if (pf) metadata[pf.key] = known[0].ref; }
  if (!cls && !known.length) return null;
  return { class: cls, title_fa: null, metadata, parties: known.map((p) => p.ref), by: 'rules', note_fa: cls ? 'از واژه‌های نام و متن فایل؛ فقط پیشنهاد است.' : 'نوع سند از متن پیدا نشد؛ طرف‌های شناخته از رجیستری.' };
}

// ============================================================ automations, rules only (§23.7) ==
const automationLog: Array<{ at: string; automation: string; record: string; action: string }> = [];
function runAutomations(on: string, r: any) {
  for (const a of automations.filter((x) => x.status === 'active' && x.on === on)) {
    const w = a.when ?? {};
    if (w.class && w.class !== r.class) continue;
    if (w.scope && w.scope !== r.scope) continue;
    if (w.level_min && rankOf(r.level) < rankOf(w.level_min)) continue;
    if (w.field) {
      const raw = r.metadata[w.field.key];
      const v = raw && typeof raw === 'object' && 'amount' in raw ? Number(raw.amount) : raw;
      const ok = w.field.op === 'eq' ? String(v) === String(w.field.value) : w.field.op === 'lt' ? Number(v) < Number(w.field.value) : w.field.op === 'gt' ? Number(v) > Number(w.field.value) : String(v ?? '').includes(String(w.field.value));
      if (!ok) continue;
    }
    for (const s of a.do) {
      if (s.action === 'raise_level' && rankOf(s.args.level) > rankOf(r.level)) r.level = s.args.level;
      if (s.action === 'move_to_folder' && folders.some((f) => f.ref === s.args.folder && f.scope === r.scope)) r.folder = s.args.folder;
      if (s.action === 'link' && s.args.kind && s.args.to) r.links.push({ kind: s.args.kind, to: s.args.to, at: stamp(), by: system });
      if (s.action === 'add_reminder' && s.args.field && dateField(r, String(s.args.field))) (r.extra_reminders ??= []).push({ field: s.args.field, at: dateField(r, String(s.args.field)), lead_days: (s.args.lead_days as number[])?.[0] ?? 7, state: 'pending', rule: null });
      automationLog.push({ at: stamp(), automation: a.ref, record: r.ref, action: s.action });
    }
    a.runs_30d = (a.runs_30d ?? 0) + 1;
    a.last_run_at = stamp();
  }
}

// ============================================================ schema API (§23.10) ==
const scopesNow = () => ['HQ', ...((ctx?.employees ?? []).map((e) => e.company).filter((c, i, xs) => c && xs.indexOf(c) === i && c !== 'HQ'))];
const usage = {
  classes: (k: string) => records.filter((r) => r.class === k && r.state !== 'disposed').length,
  folders: (k: string) => records.filter((r) => descendants(k).includes(r.folder)).length,
  levels: (k: string) => records.filter((r) => r.level === k).length,
  retention: (k: string) => records.filter((r) => classOf(r.class)?.retention === k).length,
  reminders: (k: string) => { const x = reminderRules.find((y) => y.ref === k); return x ? records.filter((r) => r.class === x.class && dateField(r, x.field)).length : 0; },
  party_kinds: (k: string) => records.filter((r) => r.parties.some((p: any) => partyOf(p.party)?.kind === k)).length,
  link_kinds: (k: string) => records.filter((r) => r.links.some((l: any) => l.kind === k)).length,
  automations: (k: string) => { const a = automations.find((x) => x.ref === k); return a ? records.filter((r) => (!a.when?.class || r.class === a.when.class) && (!a.when?.scope || r.scope === a.when.scope)).length : 0; },
  clearance: () => 0,
};
function schemaView() {
  return {
    classes: classes.map((c) => ({ ...c, records: usage.classes(c.key) })),
    field_types: FIELD_TYPES.map(([key, title_fa]) => ({ key, title_fa })),
    folders: folders.map((f) => ({ ...f, records: usage.folders(f.ref) })),
    levels: levels.map((l) => ({ ...l, records: usage.levels(l.key) })),
    clearance, retention: retention.map((r) => ({ ...r, records: usage.retention(r.ref) })), reminders: reminderRules,
    party_kinds: partyKinds.map((k) => ({ ...k, parties: parties.filter((p) => p.kind === k.key).length })),
    parties: parties.map(partyOut), link_kinds: linkKinds.map((k) => ({ ...k, records: usage.link_kinds(k.key) })),
    automations, sources,
    vocab: { events: EVENTS, actions: ACTIONS, ops: OPS, ref_kinds: REF_KINDS, currencies: CURRENCIES, mimes: MIMES },
  };
}
const partyOut = (p: any) => ({ ...p, records: records.filter((r) => r.parties.some((x: any) => x.party === p.ref)).length });

/** Field definitions against the closed list: every problem keyed `fields.<i>.<what>`. */
function fieldProblems(fs: any[], prefix: string, before: any[] | null): Record<string, string> {
  const out: Record<string, string> = {};
  if (!Array.isArray(fs)) return { [prefix]: 'فهرست فیلدها لازم است' };
  const seen = new Set<string>();
  fs.forEach((f, i) => {
    const at = `${prefix}.${f?.key || i}`;
    if (!KEY_RE.test(f?.key ?? '')) out[`${at}.key`] = 'کلید فیلد: حروف کوچک لاتین، عدد و _';
    else if (seen.has(f.key)) out[`${at}.key`] = `کلید «${f.key}» دو بار آمده`;
    seen.add(f?.key);
    if (!f?.title_fa?.trim()) out[`${at}.title_fa`] = 'عنوان فیلد لازم است';
    if (!TYPES.includes(f?.type)) out[`${at}.type`] = `نوع «${f?.type}» در واژگان بسته نیست`;
    if ((f?.type === 'enum' || f?.type === 'multi_enum') && !(f.options ?? []).filter((o: any) => KEY_RE.test(o?.key ?? '') && o?.title_fa?.trim()).length) out[`${at}.options`] = `«${f.title_fa || f.key}»: گزینه‌ای ندارد`;
    if (f?.type === 'enum' || f?.type === 'multi_enum') { const ks = (f.options ?? []).map((o: any) => o.key); if (new Set(ks).size !== ks.length) out[`${at}.options`] = 'کلید گزینه تکراری است'; }
    if (f?.type === 'ref' && (!(f.ref_kinds ?? []).length || f.ref_kinds.some((k: string) => !REF_KINDS.includes(k)))) out[`${at}.ref_kinds`] = `«${f.title_fa || f.key}»: نوع ارجاع از فهرست بسته لازم است`;
    if (f?.type === 'money' && !CURRENCIES.includes(f.currency)) out[`${at}.currency`] = `«${f.title_fa || f.key}»: واحد پول لازم است`;
    if (f?.status === 'retired' && f?.required) out[`${at}.required`] = 'فیلد بازنشسته اجباری نمیشود';
    const old = before?.find((x) => x.key === f?.key);
    if (old && old.type !== f?.type) out[`${at}.type`] = `نوع فیلد «${old.title_fa}» بعد از ساخت عوض نمیشود؛ فیلد تازه بساز و این را بازنشسته کن`;
  });
  for (const old of before ?? []) if (!fs.some((f) => f?.key === old.key)) out[`${prefix}.${old.key}`] = `فیلد «${old.title_fa}» حذف نمیشود؛ فقط بازنشسته`;
  return out;
}
function validatePart(part: string, key: string, b: any, cur: any): Record<string, string> {
  const out: Record<string, string> = {};
  const lv = (k: unknown) => levels.some((l) => l.key === k);
  if (part === 'classes') {
    if (!KEY_RE.test(key)) out.key = 'کلید کلاس: حروف کوچک لاتین، عدد و _';
    if (!b.title_fa?.trim()) out.title_fa = 'عنوان لازم است';
    Object.assign(out, fieldProblems(b.fields, 'fields', cur?.fields ?? null));
    if (!lv(b.default_level)) out.default_level = 'سطح پیش‌فرض نامعتبر است';
    if (b.default_folder && !folders.some((f) => f.ref === b.default_folder)) out.default_folder = 'پوشه‌ی پیش‌فرض پیدا نشد';
    if (b.retention && !retention.some((r) => r.ref === b.retention)) out.retention = 'قاعده‌ی نگهداری پیدا نشد';
    if (b.parent && (b.parent === key || !classOf(b.parent))) out.parent = 'کلاس والد نامعتبر است';
    if (!Array.isArray(b.allowed_mime) || !b.allowed_mime.length || b.allowed_mime.some((m: string) => !MIMES.includes(m))) out.allowed_mime = 'نوع فایل‌های مجاز از فهرست';
    if (!Number.isInteger(b.required_files) || b.required_files < 0 || b.required_files > 20) out.required_files = 'تعداد فایل لازم ۰ تا ۲۰';
    for (const rf of b.reminder_fields ?? []) { const f = (b.fields ?? []).find((x: any) => x.key === rf); if (!f || !['date', 'date_range'].includes(f.type) || f.status === 'retired') out.reminder_fields = `«${rf}» فیلد تاریخ فعال نیست`; }
    for (const al of b.auto_link ?? []) { const f = (b.fields ?? []).find((x: any) => x.key === al.field); if (!f || f.type !== 'ref' || !linkKinds.some((k) => k.key === al.link_kind)) out.auto_link = 'پیوند خودکار فقط از فیلد ارجاع با نوع پیوند موجود'; }
    if (b.scopes !== 'all' && (!Array.isArray(b.scopes) || !b.scopes.length || b.scopes.some((s: string) => !scopesNow().includes(s)))) out.scopes = 'دامنه: همه یا فهرستی از شرکت‌ها';
  } else if (part === 'folders') {
    if (!b.title_fa?.trim()) out.title_fa = 'عنوان لازم است';
    if (!scopesNow().includes(b.scope)) out.scope = 'دامنه‌ی پوشه نامعتبر است';
    if (b.parent) { const p = folders.find((f) => f.ref === b.parent); if (!p || p.scope !== b.scope) out.parent = 'پوشه‌ی والد باید در همین دامنه باشد'; else if (cur && descendants(cur.ref).includes(b.parent)) out.parent = 'پوشه زیرمجموعه‌ی خودش نمیشود'; }
    if ((b.classes ?? []).some((k: string) => !classOf(k))) out.classes = 'کلاس ناشناخته';
    if (b.default_level && !lv(b.default_level)) out.default_level = 'سطح نامعتبر';
  } else if (part === 'levels') {
    if (!KEY_RE.test(key)) out.key = 'کلید سطح: حروف کوچک لاتین';
    if (!b.title_fa?.trim()) out.title_fa = 'عنوان لازم است';
    if (!Number.isInteger(b.rank) || b.rank < 0 || b.rank > 1000) out.rank = 'رتبه عدد صحیح ۰ تا ۱۰۰۰';
    else if (levels.some((l) => l.key !== key && l.rank === b.rank)) out.rank = 'رتبه‌ی تکراری؛ بین دو سطح، رتبه‌ای میانشان بده';
    if (cur && cur.rank !== b.rank && usage.levels(key) > 0) out.rank = `رتبه‌ی «${cur.title_fa}» بعد از استفاده عوض نمیشود (${usage.levels(key)} سند)`;
    if (!Number.isInteger(b.color_index) || b.color_index < 0 || b.color_index > 5) out.color_index = 'رنگ ۰ تا ۵';
    if (b.agents_max && b.step_up_to_view) out.agents_max = 'سطحی که دیدنش passkey میخواهد سقف ایجنت‌ها نمیشود';
  } else if (part === 'clearance') {
    if (!/^(role|employee):[\w*-]+$/.test(key)) out.key = 'کلید: role:<نقش> یا employee:<کد>';
    if (!Array.isArray(b.grants)) out.grants = 'فهرست مجوزها لازم است';
    (b.grants ?? []).forEach((g: any, i: number) => {
      if (!['own', 'all', ...scopesNow()].includes(g.scope)) out[`grants.${i}.scope`] = 'دامنه نامعتبر';
      if (!lv(g.level)) out[`grants.${i}.level`] = 'سطح نامعتبر';
      else if (rankOf(g.level) > agentsMax()) out[`grants.${i}.level`] = `هیچ ایجنتی بالاتر از سقف ایجنت‌ها (${levels.find((l) => l.rank === agentsMax())?.title_fa}) مجوز نمیگیرد`;
    });
    if (b.metadata_level != null && !lv(b.metadata_level)) out.metadata_level = 'سطح متادیتا نامعتبر';
  } else if (part === 'retention') {
    if (!b.title_fa?.trim()) out.title_fa = 'عنوان لازم است';
    if (!(['filed', 'case_closed', 'superseded'].includes(b.trigger) || /^field:[a-z][a-z0-9_]*$/.test(b.trigger ?? ''))) out.trigger = 'آغاز: ثبت، فیلد تاریخ، بسته شدن پرونده یا جایگزینی';
    if (b.keep !== 'permanent' && (!b.keep || !((b.keep.years ?? 0) > 0 || (b.keep.months ?? 0) > 0) || (b.keep.years ?? 0) > 100 || (b.keep.months ?? 0) > 11)) out.keep = 'مدت: سال (تا ۱۰۰) و ماه (تا ۱۱)، یا دائمی';
    if (!['review', 'dispose_card'].includes(b.then)) out.then = 'پایان: بازبینی یا کارت امحا';
  } else if (part === 'reminders') {
    const c = classOf(b.class);
    if (!c) out.class = 'کلاس پیدا نشد';
    else { const f = c.fields.find((x: any) => x.key === b.field); if (!f || !['date', 'date_range'].includes(f.type) || f.status === 'retired') out.field = 'فیلد تاریخ فعالِ همین کلاس'; }
    if (!Array.isArray(b.lead_days) || !b.lead_days.length || b.lead_days.some((d: number) => !Number.isInteger(d) || d < 1 || d > 365) || new Set(b.lead_days).size !== b.lead_days.length) out.lead_days = 'روزهای پیش از موعد: عدد ۱ تا ۳۶۵، بی‌تکرار';
    if (!(b.to === 'owner' || (b.to && typeof b.to.role === 'string' && b.to.role) || b.to?.company_ceo === true)) out.to = 'گیرنده: مدیر کل، یک نقش یا مدیرعامل شرکت';
    if (!['cartable', 'digest'].includes(b.channel)) out.channel = 'کانال: کارتابل یا خلاصه';
  } else if (part === 'party_kinds') {
    if (!KEY_RE.test(key)) out.key = 'کلید: حروف کوچک لاتین';
    if (!b.title_fa?.trim()) out.title_fa = 'عنوان لازم است';
    Object.assign(out, fieldProblems(b.identifier_fields, 'identifier_fields', cur?.identifier_fields ?? null));
  } else if (part === 'link_kinds') {
    if (!KEY_RE.test(key)) out.key = 'کلید: حروف کوچک لاتین';
    if (!b.title_fa?.trim()) out.title_fa = 'عنوان لازم است';
    if (!b.inverse_fa?.trim()) out.inverse_fa = 'عنوان سوی دیگر لازم است';
    if (!Array.isArray(b.to_kinds) || !b.to_kinds.length || b.to_kinds.some((k: string) => !REF_KINDS.includes(k))) out.to_kinds = 'به چه چیزهایی: از فهرست بسته';
  } else if (part === 'automations') {
    if (!b.title_fa?.trim()) out.title_fa = 'عنوان لازم است';
    if (!EVENTS.includes(b.on)) out.on = `رویداد «${b.on}» در واژگان بسته نیست`;
    const w = b.when ?? {};
    if (w.class && !classOf(w.class)) out['when.class'] = 'کلاس ناشناخته';
    if (w.scope && !scopesNow().includes(w.scope)) out['when.scope'] = 'دامنه ناشناخته';
    if (w.level_min && !lv(w.level_min)) out['when.level_min'] = 'سطح ناشناخته';
    if (w.field && (!w.field.key || !OPS.includes(w.field.op))) out['when.field'] = 'شرط فیلد: کلید و یکی از eq، lt، gt، contains';
    if (!Array.isArray(b.do) || !b.do.length) out.do = 'دست‌کم یک اقدام';
    (b.do ?? []).forEach((s: any, i: number) => {
      const a = s?.args ?? {};
      if (!ACTIONS.includes(s?.action)) { out[`do.${i}.action`] = `اقدام «${s?.action}» در واژگان بسته نیست`; return; }
      if (s.action === 'notify' && (a.level === 'urgent' || !['info', 'report', 'decision'].includes(a.level))) out[`do.${i}.level`] = 'اعلان: اطلاع، گزارش یا تصمیم؛ هرگز فوری';
      if (s.action === 'work_item' && (!a.role || /[@\s]/.test(String(a.role)))) out[`do.${i}.role`] = 'کار فقط برای یک نقش هاب، نه یک شخص';
      if (s.action === 'link' && (!linkKinds.some((k) => k.key === a.kind) || !a.to?.ref)) out[`do.${i}.args`] = 'پیوند: نوع و مقصد';
      if (s.action === 'move_to_folder' && !folders.some((f) => f.ref === a.folder)) out[`do.${i}.folder`] = 'پوشه پیدا نشد';
      if (s.action === 'raise_level' && !lv(a.level)) out[`do.${i}.level`] = 'سطح ناشناخته';
      if (s.action === 'add_reminder' && (!a.field || !Array.isArray(a.lead_days) || !a.lead_days.length)) out[`do.${i}.args`] = 'یادآور: فیلد و روزها';
    });
  }
  return out;
}
function impactOf(part: string, key: string, b: any): { records: number; missing_required: number } {
  if (part === 'classes') {
    const rs = records.filter((r) => r.class === key && r.state !== 'disposed' && r.state !== 'draft');
    const req2 = (b.fields ?? []).filter((f: any) => f.required && f.status !== 'retired');
    return { records: rs.length, missing_required: rs.filter((r) => req2.some((f: any) => isEmpty(r.metadata[f.key]))).length };
  }
  if (part === 'clearance') {
    const grants = b.grants ?? [];
    const sees = (r: any) => grants.some((g: any) => (g.scope === 'all' || g.scope === r.scope || g.scope === 'own') && rankOf(r.level) <= rankOf(g.level));
    return { records: records.filter(sees).length, missing_required: 0 };
  }
  if (part === 'automations') return { records: records.filter((r) => (!b.when?.class || r.class === b.when.class) && (!b.when?.scope || r.scope === b.when.scope)).length, missing_required: 0 };
  if (part === 'reminders') return { records: records.filter((r) => r.class === b.class && dateField(r, b.field)).length, missing_required: 0 };
  const fn = (usage as Record<string, (k: string) => number>)[part];
  return { records: fn ? fn(key) : 0, missing_required: 0 };
}
const listOf = (part: string): any[] => ({ classes, folders, levels, retention, reminders: reminderRules, party_kinds: partyKinds, link_kinds: linkKinds, automations } as Record<string, any[]>)[part] ?? [];
const keyOf = (part: string, x: any) => (['folders', 'retention', 'reminders', 'automations'].includes(part) ? x.ref : x.key);
const PREFIX: Record<string, string> = { folders: 'FP', retention: 'RR', reminders: 'RM', automations: 'AU' };
function nextRef(part: string): string {
  const p = PREFIX[part]!;
  const n = Math.max(0, ...listOf(part).map((x) => Number(String(x.ref).slice(3)))) + 1;
  return `${p}-${pad(n, 4)}`;
}
const clearanceRows = (key: string) => { const [kind, ref] = key.split(':'); return clearance.filter((c) => c.subject.kind === kind && c.subject.ref === ref); };

// ============================================================ decision cards (§23.11) ==
const card = (d: Record<string, unknown>) => ({
  reversible: true, status: 'pending', seal: null, decided_at: null, decided_by: null, note: null, resolution: null, thread: null,
  version: 1, effect_status: 'none', work_id: null, reason_code: null, quota_estimate: { tokens: 0, usd: '0.00' }, expected: null, warnings: [], expires_at: null, ...d,
});
const INSURANCE = {
  title_fa: 'بیمه‌نامه', parent: null, scopes: 'all', icon: 'lock', default_level: 'confidential', default_folder: null,
  fields: [
    F('insurer', 'بیمه‌گر', 'party', { required: true }), F('policy_no', 'شماره‌ی بیمه‌نامه', 'id_code', { required: true, searchable: true }),
    F('coverage', 'نوع پوشش', 'enum', { required: true, options: [{ key: 'cyber', title_fa: 'سایبری' }, { key: 'liability', title_fa: 'مسئولیت' }, { key: 'property', title_fa: 'اموال' }] }),
    F('sum_insured', 'سقف تعهد', 'money', { currency: 'USD' }), F('period', 'دوره‌ی پوشش', 'date_range', { required: true }), F('expires_at', 'انقضا', 'date', { required: true }), F('premium', 'حق بیمه', 'money', { currency: 'USD' }),
  ],
  required_files: 1, allowed_mime: ['application/pdf', 'image/jpeg', 'image/png'], ocr: true, retention: 'RR-0003', reminder_fields: ['expires_at'], auto_link: [],
};
/** Exactly two new pending cards: the archivist's proposed class, and the week's disposal batch. */
export const DECISIONS_20: any[] = [
  card({ id: 'd92', ref: 'D-000092', kind: 'archive_schema', company: 'HQ', action_class: 'A2', risk: 'low', title: 'کلاس تازه‌ی بایگانی: بیمه‌نامه', proposer: archivist,
    created_at: iso(60 * 3), what: 'نوع سند تازه‌ی **بیمه‌نامه** (`insurance_policy`) با ۷ فیلد، یادآور روی انقضا و نگهداری مثل مجوزها (**RR-0003**).',
    why: 'در ورود دسته‌ای این هفته دو بیمه‌نامه‌ی سایبری آمد که هیچ نوع موجودی فیلد بیمه‌گر، سقف تعهد و دوره‌ی پوشش را ندارد؛ هر دو فعلاً پیش‌نویس‌اند. با این کلاس، بایگان آن‌ها را طبقه‌بندی میکند.',
    risk_note: 'افزودن کلاس چیزی را پاک یا عوض نمیکند؛ هیچ سند موجودی زیر آن نیست. با مُهر، دقیقاً همین بدنه اعمال میشود؛ اگر کلاس پیش از مُهر عوض شده باشد کارت باطل است.',
    payload: { part: 'classes', key: 'insurance_policy', base_version: null, body: INSURANCE, impact: { records: 0, missing_required: 0 } } }),
  card({ id: 'd93', ref: 'D-000093', kind: 'archive_disposal', company: 'HQ', action_class: 'A2', risk: 'medium', reversible: false, title: 'امحای سندهای پایان نگهداری: هفته‌ی ۴ مهر', proposer: system,
    created_at: iso(60 * 24 * 2), what: 'سه فاکتور قدیمی هتزنر به پایان **۷ سال** نگهداری پس از تاریخ فاکتور رسیده‌اند (**RR-0002**). با مُهر، فایل‌ها نابود میشوند و سنگ‌نشان (ref، کلاس، عنوان، تاریخ‌ها، hash و همین تصمیم) میماند.',
    why: 'قاعده‌ی نگهداری فاکتورها؛ دسته‌ی هفتگی کارت امحا. هیچ‌کدام مُهر نشده‌اند و پیوندی به پرونده‌ی باز ندارند.',
    risk_note: 'نابودی برگشت‌ناپذیر است. سندی که تا لحظه‌ی مُهر توقیف شده باشد رد میشود و میماند.',
    payload: { records: [
      { ref: 'AR-000090', class: 'invoice', title_fa: 'فاکتور قدیمی هتزنر، شهریور ۱۳۹۷', retention_rule: 'RR-0002', trigger_at: '2018-09-01' },
      { ref: 'AR-000091', class: 'invoice', title_fa: 'فاکتور قدیمی هتزنر، آذر ۱۳۹۷', retention_rule: 'RR-0002', trigger_at: '2018-12-01' },
      { ref: 'AR-000092', class: 'invoice', title_fa: 'فاکتور قدیمی هتزنر، بهمن ۱۳۹۷', retention_rule: 'RR-0002', trigger_at: '2019-02-01' },
    ] } }),
];

/** Called once by mock.ts after its lists exist: §23 adds the archivist (a system role of the holding), its cards and the shared file map. */
export function decorate20(c: Ctx): void {
  ctx = c;
  const base = c.employees.find((e) => e.kind === 'employee') ?? {};
  if (!c.employees.some((e) => e.code === 'HQ-ARC')) {
    c.employees.push({ ...base, id: 'e-HQ-ARC', code: 'HQ-ARC', company: 'HQ', kind: 'employee', department: null, title_fa: 'بایگان', title_en: 'Archivist', activity: 'sleeping', activity_note: null,
      hired_at: iso(60 * 24 * 2), probation_until: null, model: { connection: 'claude-max', model: 'claude-haiku-5-5', effort: 'medium' }, score: { value: null, owner_avg: null, rank_in_department: null, trend: [] } });
  }
  for (const d of DECISIONS_20) if (!c.decisions.some((x) => x.ref === d.ref)) c.decisions.push(d);
}

/** What deciding a §23 card does in the demo (mock.ts calls it after approve, reject and return). */
export function decided20(d: any): void {
  if (d.status !== 'approved') return;
  if (d.kind === 'archive_schema') applyPut(d.payload.part, d.payload.key, d.payload.body);
  if (d.kind === 'archive_disposal') {
    for (const x of d.payload.records ?? []) {
      const r = recordOf(x.ref);
      if (!r || holdsOf(r).length || r.state === 'disposed') continue; // a held record is skipped and stays
      const hashes = r.versions.flatMap((v: any) => v.files.map((id: string) => ({ name: store.get(id)!.name, sha256: store.get(id)!.sha256 })));
      for (const v of r.versions) for (const id of v.files) { const f = store.get(id); if (f) f.destroyed = true; }
      Object.assign(r, { state: 'disposed', version: r.version + 1, tombstone: { decision: d.ref, at: stamp(), hashes } });
    }
  }
}
function applyPut(part: string, key: string, b: any): any {
  if (part === 'clearance') {
    const [kind, ref] = key.split(':');
    const v = (clearanceRows(key)[0]?.version ?? 0) + 1;
    for (let i = clearance.length - 1; i >= 0; i--) if (clearance[i].subject.kind === kind && clearance[i].subject.ref === ref) clearance.splice(i, 1);
    for (const g of b.grants ?? []) clearance.push({ subject: { kind, ref }, scope: g.scope, level: g.level, metadata_level: b.metadata_level ?? null, version: v });
    return { subject: { kind, ref }, grants: b.grants, metadata_level: b.metadata_level ?? null, version: v };
  }
  const list = listOf(part);
  const realKey = key === 'new' ? nextRef(part) : key;
  const cur = list.find((x) => keyOf(part, x) === realKey);
  const id = PREFIX[part] ? { ref: realKey } : { key: realKey };
  const row = { ...(cur ?? { status: 'active' }), ...b, ...id, version: (cur?.version ?? 0) + 1 };
  if (part === 'classes') row.fields = (b.fields ?? []).map((f: any) => ({ required: false, searchable: false, sensitive: false, help_fa: null, status: 'active', ...f }));
  if (part === 'folders' && !cur) row.order = folders.length;
  if (cur) Object.assign(cur, row); else list.push(row);
  return cur ?? row;
}

// ========================================================================== routes ==
let ready: Promise<void> | null = null;
async function load() {
  await Promise.all([...store.values()].map(async (f) => {
    const buf = await (await fetch(new URL(f.url, window.location.origin))).arrayBuffer();
    f.size_bytes = buf.byteLength;
    f.sha256 = await sha256(buf);
  }));
  for (const r of records) for (const v of r.versions) v.manifest_sha256 = await manifestOf(v.files);
}
/** The §23 routes; null when the path is not one of them. */
export async function handle20(req: Request, p: string, u: URL): Promise<Response | null> {
  const m = req.method;
  const archive = p.startsWith('/archive/');
  const dec = /^\/decisions\/(D-\d+)\/approve$/.exec(p);
  if (!archive && !dec) return null;
  const q = (k: string) => u.searchParams.get(k);
  const body = async <B,>() => (await req.json().catch(() => ({}))) as B;

  // An archive_schema card is void when its class changed after it was written; a step-up is required for both kinds (§23.11).
  if (dec) {
    const d = ctx?.decisions.find((x) => x.ref === dec[1]);
    if (!d || !['archive_schema', 'archive_disposal'].includes(d.kind)) return null;
    const deny = needsStepUp(req);
    if (deny) return deny;
    if (d.kind === 'archive_schema') {
      const cur = listOf(d.payload.part).find((x) => keyOf(d.payload.part, x) === d.payload.key);
      if ((cur?.version ?? null) !== d.payload.base_version) return problem(409, 'version_conflict', 'این بخش از طرح بعد از نوشتن کارت عوض شده؛ کارت باطل است و بایگان پیشنهاد تازه مینویسد.');
      const bad = validatePart(d.payload.part, d.payload.key, d.payload.body, cur);
      if (Object.keys(bad).length) return invalid(bad);
    }
    return null;
  }
  ready ??= load();
  await ready;

  if (m === 'GET') {
    if (p === '/archive/schema') return json(schemaView());
    if (p === '/archive/sources') return json(sources);
    if (p === '/archive/records') {
      const f = { scope: q('scope'), cls: q('class'), folder: q('folder'), level: q('level'), state: q('state'), party: q('party'), q: q('q'), from: q('from'), to: q('to'), exp: q('expiring_within_days'), held: q('held') };
      let xs = records.filter(canSee).filter((r) => r.state !== 'disposed' || f.state === 'disposed');
      if (f.scope) xs = xs.filter((r) => r.scope === f.scope);
      if (f.cls) xs = xs.filter((r) => r.class === f.cls);
      if (f.folder) { const d = descendants(f.folder); xs = xs.filter((r) => d.includes(r.folder)); }
      if (f.level) xs = xs.filter((r) => r.level === f.level);
      if (f.state) xs = xs.filter((r) => r.state === f.state);
      if (f.party) xs = xs.filter((r) => r.parties.some((x: any) => x.party === f.party));
      if (f.from) xs = xs.filter((r) => (docDate(r) ?? '') >= f.from!);
      if (f.to) xs = xs.filter((r) => (docDate(r) ?? '') <= f.to!);
      if (f.exp) { const n = Number(f.exp); xs = xs.filter((r) => remindersOf(r).some((x) => x.state !== 'done' && x.left <= n && x.left >= -30)); }
      if (f.held === 'true') xs = xs.filter((r) => holdsOf(r).length);
      if (f.q?.trim()) {
        const scored = xs.map((r) => ({ r, s: scoreOf(r, f.q!) })).filter((x) => x.s);
        return json(page(scored.sort((a, b) => b.s!.score - a.s!.score).map((x) => recordOut(x.r))));
      }
      return json(page(xs.sort((a, b) => (b.filed_at ?? b.created_at).localeCompare(a.filed_at ?? a.created_at)).map(recordOut)));
    }
    if (p === '/archive/search') {
      const text = q('q') ?? '';
      let xs = records.filter(canSee).filter((r) => r.state !== 'disposed'); // clearance-filtered before ranking
      if (q('scope')) xs = xs.filter((r) => r.scope === q('scope'));
      if (q('class')) xs = xs.filter((r) => r.class === q('class'));
      if (q('level')) xs = xs.filter((r) => r.level === q('level'));
      if (q('from')) xs = xs.filter((r) => (docDate(r) ?? '') >= q('from')!);
      if (q('to')) xs = xs.filter((r) => (docDate(r) ?? '') <= q('to')!);
      const hits = xs.map((r) => ({ r, s: scoreOf(r, text) })).filter((x) => x.s).sort((a, b) => b.s!.score - a.s!.score);
      return json(page(hits.map(({ r, s }) => ({ ref: r.ref, title_fa: r.title_fa, class: r.class, snippet_fa: s!.snippet, score: s!.score }))));
    }
    const rf = /^\/archive\/records\/(AR-\d+)\/files\/([^/]+)$/.exec(p);
    if (rf) {
      const r = recordOf(rf[1]!);
      if (!r || !canSee(r)) return problem(404, 'not_found', 'این سند پیدا نشد.');
      const id = decodeURIComponent(rf[2]!);
      if (!r.versions.some((v: any) => v.files.includes(id))) return problem(404, 'not_found', 'این فایل در این سند نیست.');
      const lvl = levels.find((l) => l.key === r.level);
      if (lvl?.step_up_to_view && !req.headers.get('X-Step-Up')) return problem(403, 'step_up_required', 'دیدن سند این سطح تأیید با اثر انگشت یا چهره میخواهد.');
      const f = store.get(id)!;
      if (f.destroyed) return problem(404, 'not_found', 'این فایل با کارت امحا نابود شده؛ فقط سنگ‌نشانش مانده.');
      (r.access ??= []).unshift({ at: stamp(), actor: owner, action: 'view', file_id: id, version: r.versions.find((v: any) => v.files.includes(id))?.n ?? null, step_up: !!lvl?.step_up_to_view, watermarked: !!lvl?.watermark });
      const blob = await (await fetch(f.url.startsWith('blob:') ? f.url : new URL(f.url, window.location.origin))).blob();
      return new Response(blob, { status: 200, headers: { 'content-type': f.mime } });
    }
    const ra = /^\/archive\/records\/(AR-\d+)\/access$/.exec(p);
    if (ra) {
      const r = recordOf(ra[1]!);
      if (!r || !canSee(r)) return problem(404, 'not_found', 'این سند پیدا نشد.');
      return json(page(r.access ?? []));
    }
    const rd = /^\/archive\/records\/(AR-\d+)$/.exec(p);
    if (rd) {
      const r = recordOf(rd[1]!);
      return r && canSee(r) ? json(recordOut(r)) : problem(404, 'not_found', 'این سند پیدا نشد.');
    }
    if (p === '/archive/parties') {
      const k = q('kind'), s = q('scope'), t = norm(q('q') ?? '');
      return json(page(parties.filter((x) => (!k || x.kind === k) && (!s || x.scopes.includes(s)) && (!t || norm(`${x.name_fa} ${x.name_en ?? ''}`).includes(t))).map(partyOut)));
    }
    if (p === '/archive/holds') {
      const st = q('state'), cs = q('case');
      return json(page(holds.filter((h) => (!st || h.state === st) && (!cs || h.case === cs)).map((h) => { const rs = records.filter((r) => canSee(r) && covers(h, r)); return { ...h, records: h.state === 'active' ? rs.length : 0, record_refs: h.state === 'active' ? rs.map((r) => r.ref) : [] }; })));
    }
    if (p === '/archive/reminders') {
      const out = records.filter(canSee).flatMap((r) => remindersOf(r).filter((x) => x.state === 'sent' || (x.state === 'done' && x.left >= -30 && x.left <= 90)).map((x) => {
        const rule = reminderRules.find((y) => y.ref === x.rule);
        return { id: x.id, record: r.ref, title_fa: r.title_fa, scope: r.scope, class: r.class, field: x.field, at: x.at, lead_days: x.lead_days, days_left: x.left, state: x.state, rule: x.rule, to: rule?.to ?? 'owner', channel: rule?.channel ?? 'cartable' };
      }));
      return json(page(out.sort((a, b) => a.days_left - b.days_left)));
    }
    if (p === '/archive/retention/due') {
      const disposal = ctx?.decisions.find((d) => d.kind === 'archive_disposal' && d.status === 'pending');
      const out = records.filter(canSee).filter((r) => r.state !== 'disposed').map((r) => ({ r, x: retentionOf(r) })).filter(({ x }) => x.due_at && x.due_at <= dOff(0)).map(({ r, x }) => ({
        ref: r.ref, title_fa: r.title_fa, scope: r.scope, class: r.class, rule: x.rule, trigger_at: x.trigger_at, due_at: x.due_at, then: x.then, holds: holdsOf(r),
        decision_ref: disposal?.payload.records.some((y: any) => y.ref === r.ref) ? disposal.ref : null,
      }));
      return json(page(out));
    }
    if (p === '/archive/fixity') return json({ at: iso(60 * 5), checked: [...store.values()].filter((f) => !f.destroyed).length, failed: [], next_at: new Date(now + 19 * 60 * MIN).toISOString() });
    return problem(404, 'not_found', 'پیدا نشد.');
  }

  // ------------------------------------------------------------------ writes --
  if (p === '/archive/intake' && m === 'POST') {
    const b = await body<{ file_ids?: string[] }>();
    if (!b.file_ids?.length) return problem(422, 'validation_failed', 'فایلی نیامد.', { fields: { file_ids: 'required' } });
    const fs = await intakeAll(b.file_ids);
    if (fs instanceof Response) return fs;
    return json({ files: fs.map(fileOut), suggestion: suggest(fs) });
  }
  if (p === '/archive/records' && m === 'POST') {
    const k = req.headers.get('Idempotency-Key');
    if (!k) return problem(400, 'validation_failed', 'Idempotency-Key لازم است.');
    const hit = keys.get(k);
    if (hit) return json(hit.body, hit.status);
    const b = await body<any>();
    const c = classOf(b.class);
    const scopes = scopesNow();
    if (!scopes.includes(b.scope)) return problem(422, 'validation_failed', 'دامنه‌ی سند نامعتبر است.', { fields: { scope: 'unknown' } });
    if (!c || c.status !== 'active') return problem(422, 'validation_failed', 'نوع سند پیدا نشد یا بازنشسته است.', { fields: { class: 'unknown' } });
    if (c.scopes !== 'all' && !c.scopes.includes(b.scope)) return problem(422, 'validation_failed', 'این نوع سند در این دامنه نیست.', { fields: { class: 'scope' } });
    if (!b.title_fa?.trim()) return problem(422, 'validation_failed', 'عنوان لازم است.', { fields: { title_fa: 'required' } });
    const level = b.level ?? c.default_level;
    if (!levels.some((l) => l.key === level && l.status === 'active')) return problem(422, 'validation_failed', 'سطح نامعتبر است.', { fields: { level: 'unknown' } });
    if (b.folder && !folders.some((f) => f.ref === b.folder && f.scope === b.scope)) return problem(422, 'validation_failed', 'پوشه باید در همین دامنه باشد.', { fields: { folder: 'scope' } });
    const md = cleanMeta(b.metadata);
    const bad = metadataProblems(c, md, !!b.file, scopes);
    if (Object.keys(bad).length) return problem(422, 'validation_failed', Object.values(bad)[0]!, { fields: bad });
    const ids: string[] = b.file_ids ?? [];
    if (b.file && ids.length < c.required_files) return problem(422, 'validation_failed', `این نوع سند دست‌کم ${c.required_files} فایل میخواهد.`, { fields: { file_ids: 'required' } });
    const fs = await intakeAll(ids);
    if (fs instanceof Response) return fs;
    const wrong = fs.find((f) => !c.allowed_mime.includes(f.mime));
    if (wrong) return problem(422, 'validation_failed', `نوع فایل «${wrong.name}» برای ${c.title_fa} مجاز نیست.`, { fields: { file_ids: wrong.mime } });
    for (const pt of b.parties ?? []) if (!partyOf(pt.party)) return problem(422, 'validation_failed', 'طرف پیدا نشد.', { fields: { parties: pt.party } });
    for (const l of b.links ?? []) { const lk = linkKinds.find((x) => x.key === l.kind); if (!lk || !lk.to_kinds.includes(l.to?.kind) || !l.to?.ref) return problem(422, 'validation_failed', 'پیوند نامعتبر است.', { fields: { links: l.kind } }); }
    const n = Math.max(...records.map((r) => Number(r.ref.slice(3)))) + 1;
    const r: any = {
      id: `ar-${n}`, ref: `AR-${pad(n, 6)}`, scope: b.scope, class: c.key, class_version: c.version, title_fa: b.title_fa.trim(), folder: b.folder ?? null, level, state: b.file ? 'filed' : 'draft',
      metadata: md, parties: b.parties ?? [], links: (b.links ?? []).map((l: any) => ({ ...l, at: stamp(), by: owner })), current_version: 1,
      versions: [{ n: 1, files: fs.map((f) => f.file_id), manifest_sha256: await manifestOf(fs.map((f) => f.file_id)), note_fa: null, created_by: owner, created_at: stamp(), sealed: false, state: 'current' }],
      source: { kind: 'owner', ref: null }, created_by: owner, created_at: stamp(), filed_at: b.file ? stamp() : null, sealed_at: null, version: 1, suggestion: null,
    };
    for (const al of c.auto_link ?? []) { const v = md[al.field] as any; if (v?.ref && !r.links.some((l: any) => l.to.ref === v.ref)) r.links.push({ kind: al.link_kind, to: { kind: v.kind, ref: v.ref }, at: stamp(), by: system }); }
    records.unshift(r);
    if (b.file) runAutomations('filed', r);
    keys.set(k, { status: 201, body: recordOut(r) });
    return json(recordOut(r), 201);
  }
  if (p === '/archive/import' && m === 'POST') {
    const b = await body<{ scope?: string; file_ids?: string[]; class?: string }>();
    if (!b.scope || !scopesNow().includes(b.scope)) return problem(422, 'validation_failed', 'دامنه لازم است.', { fields: { scope: 'required' } });
    if (!b.file_ids?.length) return problem(422, 'validation_failed', 'فایلی نیامد.', { fields: { file_ids: 'required' } });
    const fs = await intakeAll(b.file_ids);
    if (fs instanceof Response) return fs;
    const out: any[] = [];
    for (const f of fs) {
      const n = Math.max(...records.map((r) => Number(r.ref.slice(3)))) + 1;
      const sg = suggest([f]);
      const r: any = { id: `ar-${n}`, ref: `AR-${pad(n, 6)}`, scope: b.scope, class: b.class ?? null, class_version: b.class ? classOf(b.class)?.version ?? null : null, title_fa: `ورود: ${f.name}`, folder: null, level: 'internal', state: 'draft',
        metadata: {}, parties: [], links: [], current_version: 1, versions: [{ n: 1, files: [f.file_id], manifest_sha256: await manifestOf([f.file_id]), note_fa: 'ورود دسته‌ای مالک', created_by: owner, created_at: stamp(), sealed: false, state: 'current' }],
        source: { kind: 'owner', ref: null }, created_by: owner, created_at: stamp(), filed_at: null, sealed_at: null, version: 1, suggestion: sg };
      records.unshift(r);
      out.push(recordOut(r));
    }
    return json(page(out), 201);
  }
  const rw = /^\/archive\/records\/(AR-\d+)(?:\/(versions|seal|links|file))?$/.exec(p);
  if (rw) {
    const r = recordOf(rw[1]!);
    if (!r || !canSee(r)) return problem(404, 'not_found', 'این سند پیدا نشد.');
    if (r.state === 'disposed') return problem(409, 'validation_failed', 'این سند امحا شده؛ فقط سنگ‌نشانش مانده.');
    const held = holdsOf(r);
    const what = rw[2];
    if (!what && m === 'PATCH') {
      const vc = versionCheck(req, r.version);
      if (vc) return vc;
      if (held.length) return problem(423, 'held', `توقیف ${held.join('، ')}: جز نسخه‌ی تازه هیچ تغییری پذیرفته نمیشود.`);
      if (r.state === 'sealed') return problem(409, 'sealed_record', 'این سند مُهر خورده؛ اصلاح یعنی نسخه‌ی تازه.');
      const b = await body<any>();
      if (b.level && rankOf(b.level) < rankOf(r.level)) {
        // Declassification: the owner's alone, with a passkey bound to ref@version:level.
        const deny = needsStepUp(req);
        if (deny) return problem(403, 'step_up_required', 'پایین آوردن سطح فقط با اثر انگشت مدیر کل است.');
      }
      if (b.level && !levels.some((l) => l.key === b.level)) return problem(422, 'validation_failed', 'سطح نامعتبر است.', { fields: { level: 'unknown' } });
      if (b.folder && !folders.some((f) => f.ref === b.folder && f.scope === r.scope)) return problem(422, 'validation_failed', 'پوشه باید در همین دامنه باشد.', { fields: { folder: 'scope' } });
      if (b.metadata) {
        const c = classOf(r.class);
        if (c) { const md = cleanMeta(b.metadata); const bad = metadataProblems(c, md, r.state !== 'draft', scopesNow()); if (Object.keys(bad).length) return problem(422, 'validation_failed', Object.values(bad)[0]!, { fields: bad }); b.metadata = md; }
      }
      for (const k of ['title_fa', 'metadata', 'folder', 'parties', 'level']) if (b[k] !== undefined) r[k] = b[k];
      r.version += 1;
      return json(recordOut(r));
    }
    if (what === 'file' && m === 'POST') {
      const vc = versionCheck(req, r.version);
      if (vc) return vc;
      if (r.state !== 'draft') return problem(409, 'validation_failed', 'فقط پیش‌نویس ثبت میشود.');
      const c = classOf(r.class);
      if (!c) return problem(422, 'validation_failed', 'نوع سند هنوز انتخاب نشده.', { fields: { class: 'required' } });
      const bad = metadataProblems(c, r.metadata, true, scopesNow());
      if (Object.keys(bad).length) return problem(422, 'validation_failed', Object.values(bad)[0]!, { fields: bad });
      Object.assign(r, { state: 'filed', filed_at: stamp(), version: r.version + 1, suggestion: null });
      runAutomations('filed', r);
      return json(recordOut(r));
    }
    if (what === 'versions' && m === 'POST') {
      // A new version is the one change a held record accepts.
      const b = await body<{ file_ids?: string[]; note_fa?: string }>();
      if (!b.file_ids?.length) return problem(422, 'validation_failed', 'فایل نسخه‌ی تازه لازم است.', { fields: { file_ids: 'required' } });
      const fs = await intakeAll(b.file_ids);
      if (fs instanceof Response) return fs;
      const c = classOf(r.class);
      const wrong = c ? fs.find((f) => !c.allowed_mime.includes(f.mime)) : null;
      if (wrong) return problem(422, 'validation_failed', `نوع فایل «${wrong.name}» برای ${c.title_fa} مجاز نیست.`, { fields: { file_ids: wrong.mime } });
      for (const v of r.versions) v.state = 'superseded';
      const n = r.versions.length + 1;
      r.versions.push({ n, files: fs.map((f) => f.file_id), manifest_sha256: await manifestOf(fs.map((f) => f.file_id)), note_fa: b.note_fa?.trim() || null, created_by: owner, created_at: stamp(), sealed: false, state: 'current' });
      Object.assign(r, { current_version: n, version: r.version + 1, ...(r.state === 'sealed' ? { state: 'filed' } : {}) });
      runAutomations('version_added', r);
      return json(recordOut(r), 201);
    }
    if (what === 'seal' && m === 'POST') {
      const deny = needsStepUp(req);
      if (deny) return deny;
      if (held.length) return problem(423, 'held', `توقیف ${held.join('، ')}: تا آزاد شدن، مُهر هم تغییر حساب میشود.`);
      if (r.state === 'sealed') return problem(409, 'sealed_record', 'همین نسخه مُهر خورده است.');
      if (r.state === 'draft') return problem(409, 'validation_failed', 'پیش‌نویس مُهر نمیشود؛ اول ثبتش کن.');
      const cur = r.versions.find((v: any) => v.n === r.current_version);
      const b = await body<{ manifest_sha256?: string }>();
      const again = await manifestOf(cur.files); // the API recomputes it
      if (again !== cur.manifest_sha256 || (b.manifest_sha256 && b.manifest_sha256 !== again)) return problem(409, 'version_conflict', 'فهرست فایل‌ها بعد از دیدن تو عوض شده؛ مُهر روی manifest تازه است. دوباره نگاه کن.');
      cur.sealed = true;
      for (const l of r.links) l.sealed = true;
      Object.assign(r, { state: 'sealed', sealed_at: stamp(), version: r.version + 1 });
      runAutomations('sealed', r);
      return json(recordOut(r));
    }
    if (what === 'links' && (m === 'POST' || m === 'DELETE')) {
      if (held.length) return problem(423, 'held', `توقیف ${held.join('، ')}: پیوندها هم تا آزاد شدن دست نمیخورند.`);
      if (m === 'POST') {
        const b = await body<{ kind?: string; to?: { kind?: string; ref?: string } }>();
        const lk = linkKinds.find((x) => x.key === b.kind && x.status === 'active');
        if (!lk) return problem(422, 'validation_failed', 'نوع پیوند پیدا نشد.', { fields: { kind: 'unknown' } });
        if (!b.to?.kind || !lk.to_kinds.includes(b.to.kind) || !b.to.ref?.trim()) return problem(422, 'validation_failed', `«${lk.title_fa}» به ${lk.to_kinds.join('، ')} وصل میشود.`, { fields: { to: 'kind' } });
        if (b.to.kind === 'record') { const t = recordOf(b.to.ref.trim()); if (!t || !canSee(t) || t.ref === r.ref) return problem(422, 'validation_failed', 'سند مقصد پیدا نشد.', { fields: { to: 'not_found' } }); }
        if (r.links.some((l: any) => l.kind === b.kind && l.to.ref === b.to!.ref!.trim())) return problem(409, 'validation_failed', 'همین پیوند هست.');
        r.links.push({ kind: lk.key, to: { kind: b.to.kind, ref: b.to.ref.trim() }, at: stamp(), by: owner, sealed: false });
      } else {
        const i = r.links.findIndex((l: any) => l.kind === q('kind') && l.to.kind === q('to_kind') && l.to.ref === q('to_ref'));
        if (i < 0) return problem(404, 'not_found', 'این پیوند نیست.');
        if (r.links[i].sealed) return problem(409, 'sealed_record', 'این پیوند با نسخه‌ی مُهرشده آمده و برداشته نمیشود.');
        r.links.splice(i, 1);
      }
      r.version += 1;
      return json(recordOut(r));
    }
  }

  // ---- §23.10 schema
  const sc = /^\/archive\/schema\/([a-z_]+)\/([^/]+?)(\/retire)?$/.exec(p);
  if (sc) {
    const [, part, rawKey, retire] = sc;
    const key = decodeURIComponent(rawKey!);
    if (!['classes', 'folders', 'levels', 'clearance', 'retention', 'reminders', 'party_kinds', 'link_kinds', 'automations'].includes(part!)) return problem(404, 'not_found', 'این بخش از طرح نیست.');
    const dry = q('dry_run') === '1';
    if (part === 'clearance') {
      const rows = clearanceRows(key);
      if (retire) return problem(422, 'schema_invalid', 'مجوز بازنشسته نمیشود؛ سطحش را عوض کن.', { fields: { clearance: 'retire' } });
      if (m !== 'PUT') return null;
      const vc = versionCheck(req, rows[0]?.version ?? null);
      if (vc) return vc;
      const b = await body<any>();
      const bad = validatePart(part, key, b, null);
      if (Object.keys(bad).length) return invalid(bad);
      const impact = impactOf(part, key, b);
      if (dry) return json({ part, key, version: (rows[0]?.version ?? 0) + 1, impact, row: null, dry_run: true });
      const deny = needsStepUp(req);
      if (deny) return deny;
      return json({ part, key, version: (rows[0]?.version ?? 0) + 1, impact, row: applyPut(part, key, b) });
    }
    const list = listOf(part!);
    const cur = key === 'new' ? null : list.find((x) => keyOf(part!, x) === key) ?? null;
    if (retire && m === 'POST') {
      if (!cur) return problem(404, 'not_found', 'پیدا نشد.');
      if (cur.status === 'retired') return problem(409, 'validation_failed', 'همین حالا بازنشسته است.');
      if (part === 'levels' && cur.rank <= rankOf('internal') && levels.filter((l) => l.status === 'active').length <= 2) return invalid({ level: 'دست‌کم دو سطح فعال لازم است' });
      const impact = impactOf(part!, key, cur);
      if (dry) return json({ part, key, version: cur.version + 1, impact, row: null, dry_run: true });
      const deny = needsStepUp(req);
      if (deny) return deny;
      Object.assign(cur, { status: 'retired', version: cur.version + 1 });
      return json({ part, key, version: cur.version, impact, row: cur });
    }
    if (m === 'PUT') {
      if (!PREFIX[part!] && key === 'new') return invalid({ key: 'کلید لازم است' });
      if (PREFIX[part!] && key !== 'new' && !cur) return problem(404, 'not_found', 'پیدا نشد.');
      const vc = versionCheck(req, cur?.version ?? null);
      if (vc) return vc;
      const b = await body<any>();
      const bad = validatePart(part!, key, b, cur);
      if (Object.keys(bad).length) return invalid(bad);
      const impact = impactOf(part!, key, b);
      if (dry) return json({ part, key, version: (cur?.version ?? 0) + 1, impact, row: null, dry_run: true });
      const deny = needsStepUp(req);
      if (deny) return deny;
      const row = applyPut(part!, key, b);
      return json({ part, key: keyOf(part!, row), version: row.version, impact, row });
    }
  }
  if (p === '/archive/sources' && m === 'PUT') {
    const b = await body<Record<string, boolean>>();
    for (const [k, v] of Object.entries(b)) { const s = sources.find((x) => x.key === k); if (!s) return problem(422, 'validation_failed', `منبع «${k}» در فهرست بسته نیست.`, { fields: { [k]: 'unknown' } }); s.enabled = !!v; }
    return json(sources);
  }

  // ---- parties
  if (p === '/archive/parties' && m === 'POST') {
    const b = await body<any>();
    const bad = partyProblems(b);
    if (bad) return bad;
    const n = Math.max(...parties.map((x) => Number(x.ref.slice(3)))) + 1;
    const x = { ref: `PT-${pad(n, 4)}`, kind: b.kind, name_fa: b.name_fa.trim(), name_en: b.name_en?.trim() || null, identifiers: cleanMeta(b.identifiers ?? {}), scopes: b.scopes ?? [], status: 'active', version: 1 };
    parties.push(x);
    return json(partyOut(x), 201);
  }
  const pp = /^\/archive\/parties\/(PT-\d+)$/.exec(p);
  if (pp && m === 'PATCH') {
    const x = partyOf(pp[1]);
    if (!x) return problem(404, 'not_found', 'این طرف پیدا نشد.');
    const vc = versionCheck(req, x.version);
    if (vc) return vc;
    const b = await body<any>();
    const merged = { ...x, ...b };
    const bad = partyProblems(merged);
    if (bad) return bad;
    Object.assign(x, { kind: merged.kind, name_fa: merged.name_fa.trim(), name_en: merged.name_en?.trim() || null, identifiers: cleanMeta(merged.identifiers ?? {}), scopes: merged.scopes ?? [], status: merged.status ?? x.status, version: x.version + 1 });
    return json(partyOut(x));
  }

  // ---- holds
  if (p === '/archive/holds' && m === 'POST') {
    const b = await body<any>();
    if (!b.title_fa?.trim()) return problem(422, 'validation_failed', 'عنوان توقیف لازم است.', { fields: { title_fa: 'required' } });
    if (!b.reason_md?.trim()) return problem(422, 'validation_failed', 'دلیل توقیف لازم است.', { fields: { reason_md: 'required' } });
    if (b.case && !/^LC-\d{4}$/.test(b.case)) return problem(422, 'validation_failed', 'پرونده باید LC-… باشد.', { fields: { case: 'format' } });
    const s = b.scope ?? {};
    if (!['records', 'folders', 'classes', 'parties'].some((k) => s[k]?.length) && !s.from && !s.to) return problem(422, 'validation_failed', 'دامنه‌ی توقیف خالی است.', { fields: { scope: 'required' } });
    const n = Math.max(0, ...holds.map((h) => Number(h.ref.slice(3)))) + 1;
    const h = { ref: `LH-${pad(n, 4)}`, title_fa: b.title_fa.trim(), case: b.case || null, reason_md: b.reason_md.trim(), scope: s, state: 'active', placed_by: owner, placed_at: stamp(), released_at: null };
    holds.unshift(h);
    for (const r of records.filter((x) => covers(h, x))) runAutomations('hold_set', r);
    const rs = records.filter((r) => canSee(r) && covers(h, r));
    return json({ ...h, records: rs.length, record_refs: rs.map((r) => r.ref) }, 201);
  }
  const hr = /^\/archive\/holds\/(LH-\d+)\/release$/.exec(p);
  if (hr && m === 'POST') {
    const h = holds.find((x) => x.ref === hr[1]);
    if (!h) return problem(404, 'not_found', 'این توقیف پیدا نشد.');
    const deny = needsStepUp(req);
    if (deny) return deny;
    if (h.state !== 'active') return problem(409, 'validation_failed', 'این توقیف همین حالا آزاد است.');
    Object.assign(h, { state: 'released', released_at: stamp() });
    return json({ ...h, records: 0, record_refs: [] });
  }

  // ---- reminders
  const rm = /^\/archive\/reminders\/([^/]+)\/done$/.exec(p);
  if (rm && m === 'POST') {
    const id = decodeURIComponent(rm[1]!);
    const r = recordOf(id.split(':')[0]!);
    if (!r || !remindersOf(r).some((x) => x.id === id)) return problem(404, 'not_found', 'این یادآور پیدا نشد.');
    remindersDone.add(id);
    return json(remindersOf(r).find((x) => x.id === id));
  }
  return null;
}

function partyProblems(b: any): Response | null {
  const k = partyKinds.find((x) => x.key === b.kind && x.status === 'active');
  if (!k) return problem(422, 'validation_failed', 'نوع طرف پیدا نشد.', { fields: { kind: 'unknown' } });
  if (!b.name_fa?.trim()) return problem(422, 'validation_failed', 'نام فارسی لازم است.', { fields: { name_fa: 'required' } });
  const md = cleanMeta(b.identifiers ?? {});
  const bad = metadataProblems({ fields: k.identifier_fields }, md, true, scopesNow());
  if (Object.keys(bad).length) return problem(422, 'validation_failed', Object.values(bad)[0]!, { fields: bad });
  if ((b.scopes ?? []).some((s: string) => !scopesNow().includes(s))) return problem(422, 'validation_failed', 'دامنه‌ی ناشناخته.', { fields: { scopes: 'unknown' } });
  return null;
}
