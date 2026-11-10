// ⟨1.17⟩ The owner reads plain short Persian: never a ref (W-000153, F-0007, CV-0012, D-000085), a code (TY-MEDIA-MGR, role@CODE) or a token.
// The hub's own texts are already humanized (§29.7); this is the app's second line of defence for what slips through and for the few places
// that used to print a ref. A ref is dropped with its brackets and joiners, so a sentence still reads whole.

const REF = /\b[A-Z]{1,3}-\d{3,}\b/g;
// An employee code: CO-DEPT-MGR, CO-DEPT-01, CO-CEO and the holding's fixed seats; never a market pair (BTC-USDT, EUR-USD), a model
// name (GPT-5.5) or an encoding (UTF-8): those are the owner's own words.
const CODE = /\b[A-Z][A-Z0-9]{1,9}-(?:[A-Z]{2,12}-(?:MGR|\d{1,3})|CEO|ADV|OVR|AST|SYS|LIB|ARC|SEC|SRE)\b/g;
const PERSONA = /\b[a-z_]+@[A-Z]{2,5}\b/g;
// «توکن» as a unit of spending (after a figure) reads «واحد»; a crypto token keeps its name.
const WORD: Array<[RegExp, string]> = [[/([0-9۰-۹][0-9۰-۹٬,.]*\s*(?:[KkMm]|هزار|میلیون)?\s*)توکن(?:‌ها)?/g, '$1واحد']];

/** [text] without refs, codes and the word «token»; the rest untouched. */
export function plain(text: string | null | undefined): string {
  if (!text) return '';
  let t = text.replace(REF, '').replace(PERSONA, '').replace(CODE, '');
  for (const [re, to] of WORD) t = t.replace(re, to);
  return t
    .replace(/[(\[«]\s*[)\]»]/g, '') // brackets that held only a ref
    .replace(/\s*[،,]\s*(?=[،,.؛:])/g, '') // a comma left against another mark
    .replace(/(^|\s)[،,:؛]\s*/g, (_m, a: string) => a) // a mark left at the start
    .replace(/\s+([،.؛:!؟])/g, '$1')
    .replace(/\s{2,}/g, ' ')
    .trim();
}

/** Whether [text] shows something the owner must not read. */
export const leaks = (text: string | null | undefined): boolean => !!text && (new RegExp(REF.source).test(text) || new RegExp(PERSONA.source).test(text));

/** The pattern the end-to-end check holds every owner page to. */
export const REF_PATTERN = /\b[A-Z]{1,3}-\d{3,}\b/;

// ⟨1.0.1⟩ Part C (C1.4), the owner's decisions: a terminal command is never the owner's step, and a publishing account is never «کلید
// ندارد» for him. A note of the hub's that carries a command is shown without that sentence; the sentence goes under «جزئیات فنی».
const COMMAND = /`[^`]+`|\bmake\s+[a-z][a-z0-9-]*/i;
/** What the owner reads where the publishing path of a company is not connected yet (the technical team's work). */
export const ROUTE_NOT_READY_FA = 'مسیر انتشار این شرکت را تیم فنی وصل میکند؛ بعد خودش منتشر میشود.';
export const ROUTE_NOT_READY_SHORT_FA = 'تیم فنی مسیر انتشار را وصل میکند';
/** [text] split into what the owner reads and the technical sentences (with their commands) that go one tap away. */
export function ownerNote(text: string | null | undefined): { fa: string; technical: string | null } {
  const t = (text ?? '').trim();
  if (!t || !COMMAND.test(t)) return { fa: t, technical: null };
  const sentences = t.split(/(?<=[.!؟])\s+/);
  const tech = sentences.filter((s) => COMMAND.test(s));
  const keep = sentences.filter((s) => !COMMAND.test(s));
  if (tech.some((s) => /کلید|حساب|اینستاگرام|account|key/i.test(s))) keep.push(ROUTE_NOT_READY_FA);
  return { fa: keep.join(' ').trim(), technical: tech.join(' ').trim() || null };
}
