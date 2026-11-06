'use client';

// Contract v1.19 §37: erasing for good. The preview changes nothing; the erase is the owner's alone and sealed behind the passkey
// (actions session.erase / archive.erase / output.erase, target = the ref), with its own Idempotency-Key (a fresh UUID, never derived).

import { useQuery } from '@tanstack/react-query';
import { call } from './v13';
import { withStepUp } from './v29';

export type EraseKind = 'session' | 'archive' | 'output';
export type ErasePreview = { ref: string; kind: string; title_fa: string; counts: Record<string, number>; keeps_fa: string[] };
export type EraseResult = { ref: string; erased: Record<string, number> };

const enc = encodeURIComponent;
export const ERASE_ACTION: Record<EraseKind, string> = { session: 'session.erase', archive: 'archive.erase', output: 'output.erase' };
export const COUNT_FA: Record<string, string> = { turns: 'گفتگو', files: 'فایل', outputs: 'خروجی', works: 'کار', notifications: 'اعلان', versions: 'نسخه' };

export const erasePreview = (kind: EraseKind, ref: string): Promise<ErasePreview> =>
  kind === 'session' ? call<ErasePreview>('GET', `/orders/${enc(ref)}/erase/preview`)
    : kind === 'archive' ? call<ErasePreview>('GET', `/archive/records/${enc(ref)}/erase/preview`)
      : call<ErasePreview>('GET', `/deliverables/${enc(ref)}/erase/preview`);

export const useErasePreview = (kind: EraseKind, ref: string, enabled: boolean) =>
  useQuery({ queryKey: ['erase', kind, ref], queryFn: () => erasePreview(kind, ref), enabled, staleTime: 0, gcTime: 0, retry: false });

/** The sealed erase: tried as it is, then once more behind the passkey when the hub asks for it. */
export const eraseNow = (kind: EraseKind, ref: string): Promise<EraseResult> =>
  withStepUp(ERASE_ACTION[kind], ref, (h) => {
    const headers = { ...h, 'Idempotency-Key': crypto.randomUUID() };
    return kind === 'session' ? call<EraseResult>('POST', `/orders/${enc(ref)}/erase`, {}, headers)
      : kind === 'archive' ? call<EraseResult>('POST', `/archive/records/${enc(ref)}/erase`, {}, headers)
        : call<EraseResult>('POST', `/deliverables/${enc(ref)}/erase`, {}, headers);
  });
