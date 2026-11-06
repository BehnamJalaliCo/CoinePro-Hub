// ⟨1.17⟩ The owner reads plain short Persian: never a ref (W-000153, F-0007, CV-0012, D-000085), a code (TY-MEDIA-MGR, role@CODE) or a token.
// The hub's own texts are already humanized (§29.7); this is the app's second line of defence for what slips through and for the few places
// that used to print a ref. A ref is dropped with its brackets and joiners, so a sentence still reads whole.

const REF = /\b[A-Z]{1,3}-\d{3,}\b/g;
const CODE = /\b[A-Z]{2,5}(?:-[A-Z0-9]{1,12}){1,3}\b/g;
const PERSONA = /\b[a-z_]+@[A-Z]{2,5}\b/g;
const WORD: Array<[RegExp, string]> = [[/توکن‌ها/g, 'واحدها'], [/توکن/g, 'واحد']];

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
