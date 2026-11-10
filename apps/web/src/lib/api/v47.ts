/**
 * ⟨1.0.1⟩ Contract §47 to §53, the gaps of the reels order: the ledger of what a company already said in a working group («دفتر
 * موضوع‌ها»), the company's narrator, the best hour of an account, a standing routine from one sentence, a scheduled post taken back,
 * the JPEG a picture goes out as, and how hard the workshop thought. The shapes are the hub's own (`apps/api/openapi/hq-api.v1.json`).
 *
 * A hub before §47 does not have these routes: a read that answers 404/405 is null and its piece is not shown; a write that answers so
 * hides its action from then on (`markAbsent`); a field it does not send is its default.
 */
import { useSyncExternalStore } from 'react';
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { isRealModel, modelLabel } from '@/lib/format';
import { call } from './v13';
import { qs } from './v15';
import { served } from './v33';
import type { PublishPanel, SessionPublish } from './v44';

const enc = encodeURIComponent;

// ====================================================================================== write routes an older hub lacks ==
export type Feature47 = 'cancel' | 'routine';
const absent = new Set<Feature47>();
const absentListeners = new Set<() => void>();
/** A write route answered 404/405 (the hub is older): its action is hidden from now on in this tab. */
export function markAbsent(f: Feature47) {
  if (absent.has(f)) return;
  absent.add(f);
  for (const l of absentListeners) l();
}
const onAbsent = (l: () => void) => { absentListeners.add(l); return () => { absentListeners.delete(l); }; };
export const useAbsent = (f: Feature47) => useSyncExternalStore(onAbsent, () => absent.has(f), () => false);

// ===================================================================================================== §47.4 the ledger ==
export type TopicKind = 'topic' | 'reference';
export type TopicSource = 'claim' | 'package' | 'owner';
export type TopicEntry = {
  id: string; kind: TopicKind; title_fa: string; url: string | null; at: string; by: string; source: TopicSource; work_ref: string | null; output: string | null;
};
/** One page, newest first. `topics` and `references` count the whole ledger, whatever the filter. */
export type TopicLedger = { items: TopicEntry[]; topics: number; references: number; next_cursor: string | null };
export const SOURCE_FA: Record<TopicSource, string> = { claim: 'ثبت کارمند', package: 'از بسته‌ی منتشرشده', owner: 'افزوده‌ی شما' };
/** «42 موضوع · 40 نمونه», or that nothing is written yet. */
export const ledgerCountsFa = (l: Pick<TopicLedger, 'topics' | 'references'>) =>
  (l.topics || l.references ? `${l.topics} موضوع · ${l.references} نمونه` : 'هنوز چیزی ثبت نشده');
/** A page of the ledger's sheet. */
export const LEDGER_PAGE = 30;

const ledgerPath = (group: string, company: string) => `/groups/${enc(group)}/members/${enc(company)}/topics`;
/** The counts for the member's row; null on a hub before §47. */
export const useLedgerCounts = (group: string, company: string) => useQuery({
  queryKey: ['ledger', group, company, 'counts'], staleTime: 15_000,
  queryFn: () => served(call<TopicLedger>('GET', `${ledgerPath(group, company)}?limit=1`)),
});
/** The ledger, a page at a time (`next_cursor`), filtered by kind and by the words he looks for. */
export const useLedger = (group: string, company: string, kind: TopicKind, q: string) => useInfiniteQuery({
  queryKey: ['ledger', group, company, 'list', kind, q], staleTime: 5_000, initialPageParam: null as string | null,
  queryFn: ({ pageParam }) => served(call<TopicLedger>('GET', `${ledgerPath(group, company)}${qs({ kind, q: q || null, limit: LEDGER_PAGE, cursor: pageParam })}`)),
  getNextPageParam: (last) => last?.next_cursor ?? null,
});
export function useLedgerActions(group: string, company: string) {
  const qc = useQueryClient();
  const reload = () => qc.invalidateQueries({ queryKey: ['ledger', group, company] });
  return {
    /** «این را قبلاً گفته‌ایم»: `409 topic_taken` when the ledger already says it (its `message_fa` names the line and its day). */
    add: useMutation({
      mutationFn: (v: { kind: TopicKind; title_fa?: string; url?: string }) =>
        call<TopicEntry>('POST', ledgerPath(group, company), { kind: v.kind, ...(v.title_fa ? { title_fa: v.title_fa } : {}), ...(v.url ? { url: v.url } : {}) }),
      onSuccess: reload,
    }),
    /** «آزاد کن»: the line may be said again (the hub keeps it as freed; nothing is deleted). */
    free: useMutation({ mutationFn: (id: string) => call<TopicEntry>('DELETE', `${ledgerPath(group, company)}/${enc(id)}`), onSuccess: reload }),
  };
}

// ==================================================================================================== §48 the narrator ==
export type NarratorVoice = { name: string; gender: string; trait_fa: string };
/** `set: false`: none yet (`voice` is then the default speaker). `aistudio`: whether the hub's own speaker is signed in. */
export type Narrator = {
  company: string; set?: boolean; voice?: string; style_fa?: string; by?: string | null; updated_at?: string | null; voices?: NarratorVoice[];
  aistudio?: 'signed_in' | 'signed_out' | 'unknown' | string;
};
export const GENDER_FA: Record<string, string> = { female: 'زن', male: 'مرد' };
export const NARRATOR_UNSET_FA = 'تنظیم نشده؛ هر بار مدل انتخاب میکند';
/** The only step of the owner here: his one sign-in in the hub's browser. */
export const AISTUDIO_OUT_FA = 'گوینده‌ی هاب از حسابش بیرون افتاده؛ یک بار ورود شما لازم است.';
export const STYLE_MAX = 500;
/** `GET /companies/{code}/narrator`; null on a hub before §48. */
export const useNarrator = (company: string | null | undefined) => useQuery({
  queryKey: ['narrator', company], enabled: !!company, staleTime: 15_000,
  queryFn: () => served(call<Narrator>('GET', `/companies/${enc(company!)}/narrator`)),
});
/** `PUT /companies/{code}/narrator`: his tap, no passkey. The style left out is no style. */
export function useSetNarrator(company: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { voice: string; style_fa: string }) =>
      call<Narrator>('PUT', `/companies/${enc(company)}/narrator`, { voice: v.voice, ...(v.style_fa.trim() ? { style_fa: v.style_fa.trim() } : {}) }),
    onSuccess: (out) => { qc.setQueryData(['narrator', company], out); },
  });
}

// =================================================================================================== §49 the best hour ==
/** `enough: false`: too few posts yet, and `note_fa` says how many there are. What is counted is likes and comments. */
export type BestHour = {
  account?: string | null; hour?: string | null; at?: string | null; enough?: boolean; posts?: number; days?: number; basis?: 'likes_comments'; note_fa?: string;
  read_at?: string | null;
};
/** `GET /companies/{code}/best-hour?account=`; null on a hub before §49 (the switch is then not offered). */
export const useBestHour = (company: string | null | undefined, account?: string | null, enabled = true) => useQuery({
  queryKey: ['best-hour', company, account ?? ''], enabled: !!company && enabled, staleTime: 60_000,
  queryFn: () => served(call<BestHour>('GET', `/companies/${enc(company!)}/best-hour${qs({ account: account ? account.replace(/^@/, '') : null })}`)),
});
/** The hour of an account once the hub has enough posts to say it («21:00»), else null. */
export const bestHourOf = (b: BestHour | null | undefined): string | null => (b?.enough && b.hour ? b.hour : null);
/** The publish sheet's choice: the panel's best hour when the hub sent one with its moment. */
export const panelBest = (p: Pick<PublishPanel, 'best'>): (BestHour & { hour: string; at: string }) | null =>
  (p.best && p.best.enough !== false && p.best.hour && p.best.at ? (p.best as BestHour & { hour: string; at: string }) : null);

// ================================================================================== §50 a standing routine, one sentence ==
export type SessionRoutine = {
  ref: string; company?: string | null; sentence_fa: string; when_fa: string; preview_fa: string; state: 'proposed' | 'on' | 'off';
  next_at?: string | null; last_run_at?: string | null; runs?: number; order?: string | null; note_fa?: string | null;
};
/** What §50 and §44.5 add to a session's report: its standing routines and its publishes, both newest first. */
export type OrderGaps = { routines?: SessionRoutine[]; publishes?: SessionPublish[] };
export const SENTENCE_MAX = 1000;
type WithGaps = OrderGaps & Record<string, unknown>;
const reportKey = (order: string) => ['orders', 'report', order] as const;

/** `POST /routines {sentence_fa, order}`: on at once, no card and no passkey. `422`: the sentence is no routine (`message_fa` says why). */
export function useMakeRoutine(order: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { sentence_fa: string; key: string }) => call<SessionRoutine>('POST', '/routines', { sentence_fa: v.sentence_fa, order }, { 'Idempotency-Key': v.key }),
    onSuccess: (made) => {
      // the new row is there at once; the report is read again behind it
      qc.setQueryData<WithGaps | null>(reportKey(order), (r) => (r ? { ...r, routines: [made, ...(r.routines ?? []).filter((x) => x.ref !== made.ref)] } : r));
      void qc.invalidateQueries({ queryKey: ['orders'] });
    },
  });
}
/** `POST /automations/{ref}/state`: one tap switches a routine off, and on again. */
export function useRoutineState(order: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { ref: string; state: 'on' | 'off' }) => call<{ ref: string; state: string }>('POST', `/automations/${enc(v.ref)}/state`, { state: v.state }),
    onSuccess: (_out, v) => {
      qc.setQueryData<WithGaps | null>(reportKey(order), (r) => (r ? { ...r, routines: (r.routines ?? []).map((x) => (x.ref === v.ref ? { ...x, state: v.state, ...(v.state === 'off' ? { next_at: null } : {}) } : x)) } : r));
    },
    onSettled: () => Promise.all(['orders', 'g31'].map((k) => qc.invalidateQueries({ queryKey: [k] }))),
  });
}

// ============================================================================================ §51 a scheduled post, back ==
/** Not out yet, and the hub knows its job: it can be taken back. */
export const cancellable = (p: Pick<SessionPublish, 'state' | 'job'>) => (p.state === 'scheduled' || p.state === 'publishing') && !!p.job;
const swap = (list: SessionPublish[] | undefined, out: SessionPublish) => (list?.some((x) => x.job === out.job) ? list.map((x) => (x.job === out.job ? out : x)) : list);
/**
 * `POST /publishes/{job}/cancel`: his tap, no passkey. The answer is the publication as it stands now (`cancelled`, or its state kept
 * with a note while the cancel is on its way) and takes the row's place wherever it is shown; `409 not_cancellable` when it is out.
 */
export function useCancelPublish() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (job: string) => call<SessionPublish>('POST', `/publishes/${enc(job)}/cancel`),
    onSuccess: (out) => {
      qc.setQueriesData<PublishPanel | null>({ queryKey: ['publish'] }, (p) => (p ? { ...p, publishes: swap(p.publishes, out) ?? p.publishes } : p));
      qc.setQueriesData<WithGaps | null>({ queryKey: ['orders', 'report'] }, (r) => (r?.publishes ? { ...r, publishes: swap(r.publishes, out) } : r));
      for (const k of ['publish', 'orders']) void qc.invalidateQueries({ queryKey: [k] });
    },
  });
}

// ===================================================================================================== §52 the JPEG ==
const NOT_JPEG = new Set(['image/png', 'image/webp', 'image/heic']);
/** A picture Instagram does not take as it is (PNG, WebP, HEIC): the hub sends a JPEG made from it. Never a video. */
export const goesAsJpeg = (f: { name?: string | null; mime?: string | null } | null | undefined): boolean => {
  if (!f) return false;
  const mime = (f.mime ?? '').toLowerCase();
  if (mime.startsWith('video/')) return false;
  return NOT_JPEG.has(mime) || /\.(png|webp|heic)$/i.test(f.name ?? '');
};
export const JPEG_FA = 'این تصویر هنگام انتشار خودکار به JPEG تبدیل میشود.';

// ====================================================================================================== §53 the effort ==
export const EFFORT_FA: Record<string, string> = { low: 'کم', medium: 'متوسط', high: 'زیاد', xhigh: 'خیلی زیاد', max: 'بیشترین دقت' };
/** How an output was made, from `produced_with`: the model's label and how hard it thought. Null when it names no model. */
export function madeWith(pw: unknown): { model: string; effort: string | null } | null {
  const o = (pw && typeof pw === 'object' ? pw : {}) as Record<string, unknown>;
  const model = typeof o.model === 'string' ? o.model : null;
  if (!isRealModel(model)) return null;
  return { model: modelLabel(model), effort: (typeof o.effort === 'string' && EFFORT_FA[o.effort]) || null };
}
