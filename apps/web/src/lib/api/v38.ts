'use client';

// ⟨1.20⟩ Contract §38.3 the owner's «سرویس‌ها» page: an on/off switch for each optional service of the hub and the free memory. The owner's
// word is a hub job (the hub-ops dispatcher runs it, the memory budget checked); the app polls the job and shows its words. Until the
// OpenAPI file is regenerated the shapes live here, written from §38.3.

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { call } from './v13';
import { notServed } from './v28';

const enc = encodeURIComponent;

export type ServiceState = 'on' | 'off' | 'starting' | 'failed';
export type HubService = {
  key: string; title_fa: string; what_fa: string; state: ServiceState; optional: boolean;
  mem_cap_mb: number; mem_used_mb: number | null; can_toggle: boolean; note_fa: string | null;
};
export type HubMemory = { total_mb: number; budget_mb: number; caps_mb: number; free_mb: number };
export type HubServices = { memory: HubMemory | null; services: HubService[]; at: string | null };
export type HubJobState = 'queued' | 'running' | 'done' | 'failed' | 'refused';
export type HubJob = { ref: string; state: HubJobState; result_fa: string | null; blocking: Array<{ key: string; title_fa: string; mem_cap_mb: number }> };

export const STATE_FA: Record<ServiceState, string> = { on: 'روشن', off: 'خاموش', starting: 'در حال روشن شدن', failed: 'خراب شد' };

/** `null` while the hub does not serve the route yet (it deploys after the panel). */
export const useHubServices = () => useQuery({
  queryKey: ['hub', 'services'],
  queryFn: async () => { try { return await call<HubServices>('GET', '/hub/services'); } catch (e) { if (notServed(e)) return null; throw e; } },
  refetchInterval: 30_000, staleTime: 10_000,
});

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** The owner's switch: the job is queued with its own Idempotency-Key (a fresh UUID), then polled until the dispatcher has answered. */
export function useToggleService() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (v: { key: string; on: boolean; turn_off?: string[] }): Promise<HubJob> => {
      const body = v.turn_off?.length ? { on: v.on, turn_off: v.turn_off } : { on: v.on };
      let job = await call<HubJob>('POST', `/hub/services/${enc(v.key)}`, body, { 'Idempotency-Key': crypto.randomUUID() });
      for (let i = 0; i < 90 && (job.state === 'queued' || job.state === 'running'); i++) {
        await sleep(i < 3 ? 700 : 2000);
        job = await call<HubJob>('GET', `/hub/jobs/${enc(job.ref)}`);
      }
      return job;
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ['hub'] }),
  });
}
