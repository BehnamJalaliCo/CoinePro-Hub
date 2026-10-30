// The founding wizard's rules (0.5.0; the Android app's core/data/Founding.kt), each error the sentence shown under its field. Nothing reaches
// the hub before the last step; then one call, `POST /foundings` with the owner's own fields (contract §25 FoundingIn): an idea or a
// repository starts the audit and the proposal, «فقط ثبت کن» (`blank`) registers a draft company at once.

export type FoundingPath = 'idea' | 'repo' | 'blank';
export type FoundingDraft = {
  nameFa: string; code: string; tagline: string; path: FoundingPath | null; idea: string; repo: string;
  /** A slot of the companies' palette (1–8); null → the hub picks a free one. */
  colorIndex: number | null;
  /** The logo, once uploaded (`POST /files`). */
  logoFileId: string | null;
};
export const EMPTY_DRAFT: FoundingDraft = { nameFa: '', code: '', tagline: '', path: null, idea: '', repo: '', colorIndex: null, logoFileId: null };
export const STEPS = 4;

/** 2–4 Latin capitals: what the owner chooses (the hub itself takes up to 10). */
const CODE = /^[A-Z]{2,4}$/;
const PERSIAN = /[؀-ۿ]/;
const REPO = /^[A-Za-z0-9_.-]{1,100}\/[A-Za-z0-9_.-]{1,100}$/;

/** What the code field keeps of what was typed: Latin letters, upper case, four at most. */
export const cleanCode = (input: string) => input.toUpperCase().replace(/[^A-Z]/g, '').slice(0, 4);

export function nameError(name: string): string | null {
  const n = name.trim();
  if (!n) return 'نام شرکت را بنویس.';
  if (n.length < 2) return 'نام دست‌کم دو حرف است.';
  if (n.length > 60) return 'نام حداکثر ۶۰ حرف است.';
  if (!PERSIAN.test(n)) return 'نام فارسی بنویس؛ نام لاتین جدا میاید.';
  return null;
}

/** [taken]: the codes of every company and of every founding still open (the hub refuses a code twice, `409 code_taken`). */
export function codeError(code: string, taken: Set<string>): string | null {
  if (!code) return 'یک کد ۲ تا ۴ حرفی لاتین بده، مثل IG.';
  if (!CODE.test(code)) return 'کد فقط ۲ تا ۴ حرف لاتین بزرگ است (A تا Z).';
  if (code === 'HQ') return 'HQ کد هلدینگ است.';
  if (taken.has(code)) return `${code} را شرکت یا تأسیس دیگری دارد.`;
  return null;
}

export function taglineError(t: string): string | null {
  const s = t.trim();
  if (!s) return 'در یک خط بگو چه میکند.';
  if (s.length < 6) return 'کمی روشن‌تر؛ دست‌کم چند کلمه.';
  if (s.length > 140) return 'یک خط، حداکثر ۱۴۰ حرف.';
  return null;
}

/** `owner/name` from what was pasted: a GitHub URL (with or without https, `.git` or a trailing slash) or `owner/name`. */
export function repoOf(input: string): string | null {
  const s = input.trim().replace(/^https?:\/\//, '').replace(/^www\./, '').replace(/^github\.com\//, '').replace(/\/$/, '').replace(/\.git$/, '');
  return REPO.test(s) ? s : null;
}

export function pathError(d: FoundingDraft): string | null {
  if (!d.path) return 'یکی از سه راه را انتخاب کن.';
  if (d.path === 'idea' && d.idea.trim().length < 20) return 'ایده را کمی بیشتر بگو: مشتری، کار اصلی و درآمد (دست‌کم یک جمله).';
  if (d.path === 'repo' && !repoOf(d.repo)) return 'آدرس ریپو مثل github.com/owner/name یا owner/name است.';
  return null;
}

/** Field → sentence, for one step (1: who, 2: how it starts, 3: brand, optional, 4: review = all of them). */
export function stepErrors(step: number, d: FoundingDraft, taken: Set<string>): Record<string, string> {
  const out: Record<string, string> = {};
  if (step === 1 || step === 4) {
    const n = nameError(d.nameFa); if (n) out.name = n;
    const c = codeError(d.code, taken); if (c) out.code = c;
    const t = taglineError(d.tagline); if (t) out.tagline = t;
  }
  if (step === 2 || step === 4) { const p = pathError(d); if (p) out.path = p; }
  if ((step === 3 || step === 4) && d.colorIndex != null && (d.colorIndex < 1 || d.colorIndex > 8)) out.color = 'رنگ یکی از هشت رنگ است.';
  return out;
}

/** The first step [d] cannot leave yet (1-based), or null when every step is complete. */
export function firstIncomplete(d: FoundingDraft, taken: Set<string>): number | null {
  for (let s = 1; s < STEPS; s++) if (Object.keys(stepErrors(s, d, taken)).length) return s;
  return null;
}

/** The hub's `FoundingIn` (§25): the source and the owner's own name, code, line, colour and logo, kept by the proposer as given. */
export function foundingIn(d: FoundingDraft) {
  return {
    source: d.path === 'repo' ? { kind: 'repo' as const, repo: repoOf(d.repo) } : d.path === 'idea' ? { kind: 'idea' as const, brief_md: d.idea.trim() } : { kind: 'blank' as const },
    name_fa: d.nameFa.trim(), code: d.code, tagline: d.tagline.trim().replace(/\n/g, ' '), color_index: d.colorIndex, logo_file_id: d.logoFileId,
  };
}
