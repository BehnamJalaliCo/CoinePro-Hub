'use client';

// Contract v1.4.6 (§18.14): the company's brand and seal, made from the owner's PNG logo. Until the OpenAPI file is regenerated,
// the types live here, written from the contract. Same conventions as v13: X-HQ-Client and Idempotency-Key on writes, Problem
// errors as ApiError.

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { stepUp } from '@/lib/auth';
import { call } from './v13';

export type BrandLayer = { role: 'ink' | 'accent'; color: string; d: string };
/** A vector mark: the same shape as `Mark` in src/generated/brand.ts, which CompanyMark already draws. */
export type BrandMark = { vb: string; layers: BrandLayer[] };
export type BrandState = 'processing' | 'proposed' | 'active' | 'failed' | 'retired';
/** colors 1..4 (left out: as many as the logo has, at most 4), detail 1..5 (default 3). */
export type BrandOptions = { colors?: number; detail: number };
export type BrandChecks = {
  paths_bytes: number; min_feature_px_16: number; iou: number; contrast_night: number | null; contrast_day: number | null; warnings: string[];
};
/** The accent per theme: `accent_night` / `accent_day` are set only where the accent fails 3:1 on that theme's page. */
export type BrandColors = { ink: string; accent: string | null; accent_night: string | null; accent_day: string | null };
export type CompanyBrand = BrandColors & {
  company: string; version: number; state: BrandState;
  source: { kind: 'upload' | 'seed'; file_id: string | null; path: string | null; sha256: string; width: number; height: number; has_alpha: boolean };
  // Null while the version is processing or after it failed.
  mark: BrandMark | null; wordmark: BrandMark | null;
  palette: Array<{ hex: string; share: number }>;
  options: BrandOptions;
  checks: BrandChecks | null;
  digest: string; status_reason: string | null; created_at: string; activated_at: string | null;
};
/** One company's active brand in GET /brands. */
export type ActiveBrand = BrandColors & { version: number; mark: BrandMark; wordmark: BrandMark | null };
export type Brands = { etag: string; companies: Record<string, ActiveBrand> };
/** GET /companies/{code}/brand: the active version and, if any, the newest proposed one. */
export type CompanyBrandView = { active: CompanyBrand | null; proposed: CompanyBrand | null };

/** Every active brand in one response; marks and seals are drawn from it. It changes only when the owner seals a brand
 *  (`brand.updated` refreshes it), and the browser revalidates it with its ETag. */
export const useBrands = () => useQuery({ queryKey: ['brands'], queryFn: () => call<Brands>('GET', '/brands'), staleTime: 3_600_000 });
export const useCompanyBrand = (code: string) => useQuery({ queryKey: ['brand', code], queryFn: () => call<CompanyBrandView>('GET', `/companies/${encodeURIComponent(code)}/brand`) });

/** One version while the media worker traces it (`/brand/versions`), polled until it is proposed or failed. */
export const useBrandVersion = (code: string, version: number | null) => useQuery({
  queryKey: ['brand', code, 'versions'],
  queryFn: async () => {
    const v = await call<CompanyBrand[] | { items: CompanyBrand[] }>('GET', `/companies/${encodeURIComponent(code)}/brand/versions`);
    return Array.isArray(v) ? v : v.items;
  },
  select: (xs) => xs.find((x) => x.version === version) ?? null,
  enabled: version != null,
  refetchInterval: (q) => (q.state.data?.find((x) => x.version === version)?.state ?? 'processing') === 'processing' ? 1_500 : false,
});

export function useBrandAction(code: string) {
  const qc = useQueryClient();
  const path = `/companies/${encodeURIComponent(code)}/brand`;
  const fresh = () => qc.invalidateQueries({ queryKey: ['brand', code] });
  return {
    // A new version that carries the other part (mark or wordmark) over from the active one.
    upload: useMutation({ mutationFn: (v: { file_id: string; part: 'mark' | 'wordmark'; options?: BrandOptions }) => call<CompanyBrand>('POST', path, v), onSuccess: fresh }),
    retrace: useMutation({ mutationFn: (v: { version: number; options: BrandOptions }) => call<CompanyBrand>('POST', `${path}/${v.version}/retrace`, { options: v.options }), onSuccess: fresh }),
    // The seal is bound to the exact version the owner saw: its digest, which the server recomputes.
    activate: useMutation({
      mutationFn: async (b: CompanyBrand) => call<CompanyBrand>('POST', `${path}/${b.version}/activate`, {}, { 'X-Step-Up': await stepUp('company.brand', b.digest) }),
      onSuccess: () => Promise.all(['brand', 'brands', 'companies', 'founding'].map((k) => qc.invalidateQueries({ queryKey: [k] }))),
    }),
  };
}
