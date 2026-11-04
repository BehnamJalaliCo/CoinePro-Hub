'use client';

// ⟨1.12⟩ Contract §30 (prompt 22): production lines. A template is the plan of steps, a line is a template set for one company, one
// platform and one channel; the owner edits the steps freely and the line then runs and publishes by itself. Until the OpenAPI file is
// regenerated the shapes live here, written from §30. The hub deploys §30 after the panel: a route that answers 404/405/501 is
// «not served yet» and every screen says so calmly (nothing new shows).

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { stepUp } from '@/lib/auth';
import { ApiError, isMock } from './client';
import { handled } from './observe';
import { call } from './v13';
import { notServed } from './v28';

const enc = encodeURIComponent;
type Actor = { kind: string; code: string; display_fa?: string | null };

async function served<T>(p: Promise<T>): Promise<T | null> {
  try { return await p; } catch (e) { if (notServed(e)) return null; throw e; }
}
const listOf = <T,>(x: T[] | { items?: T[] } | null | undefined): T[] => (Array.isArray(x) ? x : x?.items ?? []);

// ===================================================================================================== §30.1 data ==
export const PLATFORM_FA: Record<string, string> = {
  instagram_reel: 'ریلز اینستاگرام', instagram_post: 'پست اینستاگرام', instagram_story: 'استوری اینستاگرام', youtube_short: 'شورت یوتیوب',
  youtube_long: 'ویدیوی یوتیوب', telegram_post: 'پست تلگرام', site_article: 'مقاله‌ی سایت',
};
export const platformFa = (p: string) => PLATFORM_FA[p] ?? p;

export type StepKind = 'gpt_text' | 'dedupe' | 'tts' | 'pattern_search' | 'council_pick' | 'opus_build' | 'render' | 'cover' | 'quality' | 'publish' | 'deliver' | 'n8n' | 'seal';
type KindIcon = 'edit' | 'refresh' | 'mic' | 'search' | 'meeting' | 'model' | 'video' | 'image' | 'seal' | 'send' | 'attach' | 'task';
export const STEP_KIND: Record<StepKind, { fa: string; icon: KindIcon }> = {
  gpt_text: { fa: 'متن با هوش مصنوعی', icon: 'edit' }, dedupe: { fa: 'بررسی تکراری نبودن', icon: 'refresh' }, tts: { fa: 'تبدیل متن به صدا', icon: 'mic' },
  pattern_search: { fa: 'جست‌وجوی الگو', icon: 'search' }, council_pick: { fa: 'انتخاب شورا', icon: 'meeting' }, opus_build: { fa: 'ساخت نهایی', icon: 'model' },
  render: { fa: 'ساخت ویدیو یا تصویر', icon: 'video' }, cover: { fa: 'کاور', icon: 'image' }, quality: { fa: 'بررسی کیفیت', icon: 'seal' },
  publish: { fa: 'انتشار', icon: 'send' }, deliver: { fa: 'تحویل به مالک', icon: 'attach' }, n8n: { fa: 'روال خودکار', icon: 'task' }, seal: { fa: 'تأیید', icon: 'seal' },
};
export const stepKind = (k: string): { fa: string; icon: KindIcon } => STEP_KIND[k as StepKind] ?? { fa: k, icon: 'task' };
export type Gate = 'auto' | 'owner' | 'ceo';
export const GATE_FA: Record<Gate, string> = { auto: 'خودکار', owner: 'تأیید مالک', ceo: 'تأیید مدیرعامل' };

export type StepDef = {
  key: string; kind: StepKind | string; title_fa: string; prompt_fa: string | null; settings: Record<string, unknown>; inputs: string[];
  gate: Gate; optional: boolean; enabled: boolean; max_attempts: number; timeout_s: number;
};
export type Template = { key: string; title_fa: string; platform: string; version: number; steps: StepDef[]; defaults: Record<string, unknown>; outputs_fa: string };
export type Caps = { runs_per_day: number; tokens_per_run: number; opus_per_day: number };
export type LineState = 'draft' | 'on' | 'paused';
export type LineMode = 'draft' | 'auto';
export type RunState = 'queued' | 'running' | 'waiting' | 'done' | 'failed' | 'skipped' | 'cancelled';
export type StepRunState = 'pending' | 'running' | 'waiting' | 'done' | 'failed' | 'skipped';
export type Line = {
  ref: string; company: string; template: string; template_version: number; platform: string; channel: { kind: string; subject: string }; title_fa: string;
  schedule: string | null; state: LineState; mode: LineMode; good_runs: number; auto_after: number; caps: Caps; version: number; steps: StepDef[]; library: string[];
  created_at: string; updated_at: string;
  /** Beyond §30.1, for the company's list («next run», «last run»); when the hub does not send them the list shows a dash. */
  next_run_at?: string | null; last_run?: { ref: string; state: RunState; at: string } | null;
};
export type LineVersion = { line: string; version: number; body: Line; by: Actor; at: string; note_fa: string | null };
export type StepOutput = { text: string | null; file_id: string | null; files: string[]; data: Record<string, unknown> };
export type StepRun = { key: string; kind: StepKind | string; state: StepRunState; attempt: number; started_at: string | null; ended_at: string | null; output: StepOutput | null; via: string | null; tokens: number; usd_equiv: number; error_fa: string | null };
export type Published = { platform: string; kind: string; external_id: string | null; at: string; url: string | null };
export type LineRun = {
  ref: string; line: string; line_version: number; trigger: 'schedule' | 'owner' | 'test' | 'n8n' | 'group'; dry: boolean; state: RunState; at: string; ended_at: string | null;
  steps: StepRun[]; cost: { tokens: number; usd_equiv: number }; published: Published[]; metrics: { h24: Record<string, number> | null; d7: Record<string, number> | null }; note_fa: string | null;
};
export type AssetKind = 'cover_folder' | 'voice' | 'prompt' | 'pattern' | 'music' | 'brand';
export type Asset = { id: string; company: string | null; kind: AssetKind; title_fa: string; config: Record<string, unknown>; files: string[]; created_at: string };
export type Voice = { name: string; title_fa: string; gender: string; sample_file: string | null };
export type CalendarItem = { line: string; company: string; platform: string; at: string; state: string; run: string | null; title_fa?: string | null };
export type CalendarDay = { day: string; items: CalendarItem[] };

type Tone = 'neutral' | 'gold' | 'pos' | 'neg' | 'warn' | 'lapis' | 'silver';
export const RUN_STATE_FA: Record<RunState, { fa: string; tone: Tone; live?: boolean }> = {
  queued: { fa: 'در صف', tone: 'lapis' }, running: { fa: 'در حال اجرا', tone: 'gold', live: true }, waiting: { fa: 'منتظر تأیید', tone: 'warn' },
  done: { fa: 'انجام شد', tone: 'pos' }, failed: { fa: 'ناموفق', tone: 'neg' }, skipped: { fa: 'رد شد', tone: 'silver' }, cancelled: { fa: 'لغو شد', tone: 'silver' },
};
export const STEP_STATE_FA: Record<StepRunState, string> = { pending: 'در انتظار', running: 'در حال اجرا', waiting: 'منتظر تأیید', done: 'انجام شد', failed: 'ناموفق', skipped: 'رد شد' };
export const LINE_STATE_FA: Record<LineState, { fa: string; tone: 'neutral' | 'pos' | 'warn' | 'silver' }> = {
  draft: { fa: 'پیش‌نویس', tone: 'silver' }, on: { fa: 'روشن', tone: 'pos' }, paused: { fa: 'متوقف', tone: 'warn' },
};
export const LIVE_RUN: ReadonlySet<string> = new Set(['queued', 'running', 'waiting']);
export const KIND_FA: Record<AssetKind, string> = { cover_folder: 'پوشه‌ی کاور', voice: 'صدا', prompt: 'پرامپت', pattern: 'الگو', music: 'موسیقی', brand: 'نشان' };
/** The variables a prompt may use, as chips to insert (the line's own; a step's key is its output). */
export const BASE_VARS = ['company', 'platform', 'channel', 'title', 'date', 'topic'];

/** A sealed action is tried as it is, then once more behind the passkey when the hub answers `step_up_required`. */
async function withStepUp<T>(action: string, target: string, run: (h?: Record<string, string>) => Promise<T>): Promise<T> {
  try { return await run(); } catch (e) {
    if (!(e instanceof ApiError && e.status === 403 && e.code === 'step_up_required')) throw e;
    handled(e);
    return run({ 'X-Step-Up': await stepUp(action, target) });
  }
}

// ========================================================================================================== reads ==
export const useTemplates = () => useQuery({ queryKey: ['lines', 'templates'], staleTime: 60_000, queryFn: async () => { const r = await served(call<Template[] | { items: Template[] }>('GET', '/line-templates')); return r ? listOf(r) : null; } });
export const useCompanyLines = (code: string) =>
  useQuery({ queryKey: ['lines', 'company', code], staleTime: 15_000, queryFn: async () => { const r = await served(call<Line[] | { items: Line[] }>('GET', `/companies/${enc(code)}/lines`)); return r ? listOf(r) : null; } });
export const useLine = (ref: string) => useQuery({ queryKey: ['lines', 'one', ref], staleTime: 10_000, queryFn: () => served(call<Line>('GET', `/lines/${enc(ref)}`)) });
export const useLineVersions = (ref: string, on = true) =>
  useQuery({ queryKey: ['lines', 'versions', ref], enabled: on, staleTime: 10_000, queryFn: async () => listOf(await call<LineVersion[] | { items: LineVersion[] }>('GET', `/lines/${enc(ref)}/versions`)) });
export const useLineRuns = (ref: string) =>
  useQuery({
    queryKey: ['lines', 'runs', ref], staleTime: 10_000,
    queryFn: async () => listOf(await call<LineRun[] | { items: LineRun[] }>('GET', `/lines/${enc(ref)}/runs`)),
    refetchInterval: (q) => (q.state.data?.some((r) => LIVE_RUN.has(r.state)) ? 15_000 : false),
  });
/** The run, live: while it moves, a quiet look every 8 s (the stream's `line_run.` refreshes it sooner). */
export const useLineRun = (ref: string) =>
  useQuery({
    queryKey: ['lines', 'run', ref], staleTime: 5_000, queryFn: () => served(call<LineRun>('GET', `/line-runs/${enc(ref)}`)),
    refetchInterval: (q) => (q.state.data && LIVE_RUN.has(q.state.data.state) ? 8_000 : false),
  });
export const useVoices = (on = true) => useQuery({ queryKey: ['lines', 'voices'], enabled: on, staleTime: 3_600_000, queryFn: async () => { const r = await served(call<Voice[] | { items: Voice[] }>('GET', '/tts/voices')); return r ? listOf(r) : null; } });
export const useCalendar = (from: string, to: string, company: string | null) =>
  useQuery({
    queryKey: ['lines', 'calendar', from, to, company], staleTime: 20_000,
    queryFn: async () => (await served(call<{ days: CalendarDay[] }>('GET', `/calendar/lines?from=${enc(from)}&to=${enc(to)}${company ? `&company=${enc(company)}` : ''}`)))?.days ?? null,
  });
export const useLibrary = (company: string | null, kind: AssetKind | null, on = true) =>
  useQuery({
    queryKey: ['lines', 'library', company, kind], enabled: on, staleTime: 20_000,
    queryFn: async () => {
      const qs = [company ? `company=${enc(company)}` : '', kind ? `kind=${enc(kind)}` : ''].filter(Boolean).join('&');
      const r = await served(call<Asset[] | { items: Asset[] }>('GET', `/library${qs ? `?${qs}` : ''}`));
      return r ? listOf(r) : null;
    },
  });

// ======================================================================================================== writes ==
export type LinePatch = { title_fa?: string; schedule?: string | null; steps?: StepDef[]; caps?: Caps; library?: string[]; note_fa?: string };
const done = (qc: ReturnType<typeof useQueryClient>) => () => qc.invalidateQueries({ queryKey: ['lines'] });

export function useCreateLine(company: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (b: { template: string; platform: string; channel: { kind: string; subject: string }; title_fa: string }) => call<Line>('POST', `/companies/${enc(company)}/lines`, b),
    onSettled: done(qc),
  });
}

export function useLineActions(ref: string) {
  const qc = useQueryClient();
  const settle = done(qc);
  return {
    /** A new version. Raising a cap is sealed (`line.caps`). */
    save: useMutation({ mutationFn: (p: LinePatch) => withStepUp('line.caps', ref, (h) => call<Line>('PUT', `/lines/${enc(ref)}`, p, h)), onSettled: settle }),
    state: useMutation({ mutationFn: (state: 'on' | 'paused') => call<Line>('POST', `/lines/${enc(ref)}/state`, { state }), onSettled: settle }),
    /** «خودکار کن» is sealed (`line.auto`). */
    mode: useMutation({
      mutationFn: (mode: LineMode) => (mode === 'auto'
        ? withStepUp('line.auto', ref, (h) => call<Line>('POST', `/lines/${enc(ref)}/mode`, { mode }, h))
        : call<Line>('POST', `/lines/${enc(ref)}/mode`, { mode })),
      onSettled: settle,
    }),
    revert: useMutation({ mutationFn: (version: number) => call<Line>('POST', `/lines/${enc(ref)}/revert`, { version }), onSettled: settle }),
    copy: useMutation({ mutationFn: (company: string) => call<Line>('POST', `/lines/${enc(ref)}/copy`, { company }), onSettled: settle }),
    run: useMutation({ mutationFn: (b: { dry?: boolean; from_step?: string }) => call<LineRun>('POST', `/lines/${enc(ref)}/runs`, b), onSettled: settle }),
    test: useMutation({ mutationFn: (v: { key: string; inputs?: Record<string, string> }) => call<StepRun>('POST', `/lines/${enc(ref)}/steps/${enc(v.key)}/test`, { inputs: v.inputs ?? {} }) }),
  };
}

export function useRunActions(ref: string) {
  const qc = useQueryClient();
  const settle = done(qc);
  return {
    seal: useMutation({ mutationFn: (b: { approve: boolean; note_fa?: string }) => withStepUp('line_publish', ref, (h) => call<LineRun>('POST', `/line-runs/${enc(ref)}/seal`, b, h)), onSettled: settle }),
    rerun: useMutation({ mutationFn: (from_step: string) => call<LineRun>('POST', `/line-runs/${enc(ref)}/rerun`, { from_step }), onSettled: settle }),
    cancel: useMutation({ mutationFn: () => call<LineRun>('POST', `/line-runs/${enc(ref)}/cancel`, {}), onSettled: settle }),
  };
}

export type AssetMeta = { company: string | null; kind: AssetKind; title_fa: string; config?: Record<string, unknown> };
/** `POST /library` multipart: `meta` JSON and the files. (The demo has no multipart; it takes the names.) */
export async function uploadAsset(meta: AssetMeta, files: File[]): Promise<Asset> {
  if (isMock) return call<Asset>('POST', '/library', { meta, files: files.map((f) => f.name) });
  const fd = new FormData();
  fd.set('meta', JSON.stringify(meta));
  for (const f of files) fd.append('files', f, f.name);
  let res: Response;
  try {
    res = await fetch('/api/v1/library', { method: 'POST', body: fd, credentials: 'same-origin', headers: { 'X-HQ-Client': 'web', 'Idempotency-Key': crypto.randomUUID(), Accept: 'application/json' } });
  } catch { throw new ApiError(0, undefined); }
  if (!res.ok) {
    let p: unknown;
    try { p = await res.json(); } catch { /* not JSON */ }
    throw new ApiError(res.status, p as never);
  }
  return (await res.json()) as Asset;
}
export function useLibraryActions() {
  const qc = useQueryClient();
  const settle = done(qc);
  return {
    add: useMutation({ mutationFn: (v: { meta: AssetMeta; files: File[] }) => uploadAsset(v.meta, v.files), onSettled: settle }),
    edit: useMutation({ mutationFn: (v: { id: string; title_fa?: string; config?: Record<string, unknown> }) => call<Asset>('PUT', `/library/${enc(v.id)}`, { title_fa: v.title_fa, config: v.config }), onSettled: settle }),
    remove: useMutation({ mutationFn: (id: string) => call<void>('DELETE', `/library/${enc(id)}`), onSettled: settle }),
  };
}

/** The `{{variables}}` a prompt uses. */
export const promptVars = (t: string | null | undefined) => [...new Set([...(t ?? '').matchAll(/\{\{\s*([\w.]+)\s*\}\}/g)].map((m) => m[1]!))];
