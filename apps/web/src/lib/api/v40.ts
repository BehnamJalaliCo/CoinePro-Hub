'use client';

// ⟨1.22⟩ Contract §40 «یک جلسه میشود کارگروهی که به هر شرکت و پلتفرم میدهی»: the session's memory («تا اینجا»), the playbook drafted from it
// (a working group as data), its page and library, sealing, giving it to another company or platform, and retiring it. The shapes are
// written from §40 and the hub's OpenAPI (Playbook, PlaybookPatch, PlaybookApplyIn, PlaybookApplied) until the file is regenerated.
// A route answering 404/405/501 is «not served yet»: the hooks answer null and the pages say so.

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { call } from './v13';
import { notServed } from './v28';
import { withStepUp } from './v29';

const enc = encodeURIComponent;
async function served<T>(p: Promise<T>): Promise<T | null> {
  try { return await p; } catch (e) { if (notServed(e)) return null; throw e; }
}

export type PlaybookPlatform = 'instagram' | 'youtube' | 'telegram' | 'site' | 'any';
export type PlaybookState = 'draft' | 'sealed' | 'retired';
export type Helper = 'gpt' | 'gemini' | 'deepseek' | 'aistudio';
export type PlaybookSeat = { seat: string; role: string; title_fa: string; duties_fa?: string; helpers?: string[]; model?: string | null };
export type PlaybookRoutine = { key: string; title_fa: string; seat: string; schedule: string; brief_md: string; max_tokens?: number };
export type PlaybookKpi = { key: string; title_fa: string; source: string; unit?: string };
export type PlaybookMember = { company: string; name_fa: string; state: 'on' | 'paused'; order?: string | null };
export type Playbook = {
  ref: string; title_fa: string; purpose_fa: string; state: PlaybookState; version: number; platform: PlaybookPlatform;
  seats?: PlaybookSeat[]; routines?: PlaybookRoutine[]; kpis?: PlaybookKpi[]; connections?: string[]; rules_fa?: string[];
  source: { order: string; company: string | null; conversation: string | null }; members?: PlaybookMember[];
  parent?: string | null; group?: string | null; note_fa?: string | null; created_at: string; sealed_at?: string | null; retired_at?: string | null;
};
export type PlaybookPatch = Partial<Pick<Playbook, 'title_fa' | 'purpose_fa' | 'platform' | 'seats' | 'routines' | 'kpis' | 'connections' | 'rules_fa'>>;
export type PlaybookApplied = { playbook: Playbook; member?: PlaybookMember | null; order?: string | null; conversation?: string | null };
export type ApplyIn = { company: string; platform?: PlaybookPlatform | null; note_fa?: string | null; as_is?: boolean };

export const PLATFORM_FA: Record<PlaybookPlatform, string> = { instagram: 'اینستاگرام', youtube: 'یوتیوب', telegram: 'تلگرام', site: 'سایت', any: 'همه' };
export const PLATFORMS: PlaybookPlatform[] = ['instagram', 'youtube', 'telegram', 'site', 'any'];
export const HELPER_FA: Record<string, string> = { gpt: 'جی‌پی‌تی', gemini: 'جمنای', deepseek: 'دیپ‌سیک', aistudio: 'ای‌آی استودیو' };
export const PB_STATE_FA: Record<PlaybookState, { fa: string; tone: 'gold' | 'pos' | 'silver' }> = {
  draft: { fa: 'پیش‌نویس', tone: 'gold' }, sealed: { fa: 'مُهر شده', tone: 'pos' }, retired: { fa: 'بازنشسته', tone: 'silver' },
};

// ================================================================================================= reads ==
const qs = (state?: PlaybookState) => (state ? `?state=${state}` : '');
/** `GET /playbooks?state=`: the library; null on a hub before §40. */
export const usePlaybooks = (state?: PlaybookState) => useQuery({
  queryKey: ['playbooks', 'list', state ?? 'all'], staleTime: 10_000,
  queryFn: () => served(call<Playbook[] | { items: Playbook[] }>('GET', `/playbooks${qs(state)}`)).then((r) => (r ? (Array.isArray(r) ? r : r.items ?? []) : null)),
});
/** `GET /playbooks/{ref}`. */
export const usePlaybook = (ref: string | null | undefined) => useQuery({
  queryKey: ['playbooks', 'one', ref], enabled: !!ref, staleTime: 5_000,
  queryFn: () => served(call<Playbook>('GET', `/playbooks/${enc(ref!)}`)),
});

// =============================================================================================== writes ==
const reload = (qc: ReturnType<typeof useQueryClient>) => () => Promise.all(['playbooks', 'talk', 'orders', 'office', 'groups', 'g29'].map((k) => qc.invalidateQueries({ queryKey: [k] })));

/** `POST /orders/{ref}/playbook` (a UUID Idempotency-Key): the session's draft; its card lands in the chat. */
export function useDraftPlaybook(order: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => call<Playbook>('POST', `/orders/${enc(order)}/playbook`, {}, { 'Idempotency-Key': crypto.randomUUID() }),
    onSettled: reload(qc),
  });
}

export function usePlaybookActions(ref: string) {
  const qc = useQueryClient();
  const settle = reload(qc);
  return {
    patch: useMutation({ mutationFn: (b: PlaybookPatch) => call<Playbook>('PATCH', `/playbooks/${enc(ref)}`, b), onSettled: settle }),
    // 🔏 `playbook.seal` and `playbook.retire`: routine, the hub answers the step-up with its own token (no fingerprint).
    seal: useMutation({ mutationFn: () => withStepUp('playbook.seal', ref, (h) => call<Playbook>('POST', `/playbooks/${enc(ref)}/seal`, {}, h)), onSettled: settle }),
    retire: useMutation({ mutationFn: () => withStepUp('playbook.retire', ref, (h) => call<Playbook>('POST', `/playbooks/${enc(ref)}/retire`, {}, h)), onSettled: settle }),
    apply: useMutation({ mutationFn: (b: ApplyIn) => call<PlaybookApplied>('POST', `/playbooks/${enc(ref)}/apply`, b, { 'Idempotency-Key': crypto.randomUUID() }), onSettled: settle }),
  };
}
