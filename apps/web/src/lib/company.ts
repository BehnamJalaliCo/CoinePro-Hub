import type { Schemas } from './api/client';

export type Company = Schemas['Company'];

/** Name and kind of a company code from the list the API returns (companies are data). */
export function companyOf(list: Company[] | undefined, code: string | null | undefined): { code: string; nameFa: string; nameEn: string; holding: boolean } {
  const c = list?.find((x) => x.code === code);
  return { code: code ?? '', nameFa: c?.name_fa ?? code ?? '', nameEn: c?.name_en ?? code ?? '', holding: c?.kind === 'holding' };
}

/** Chart colour of a company: its stored slot in the categorical palette v2; none = neutral silver. */
export function companyColor(list: Company[] | undefined, code: string): string {
  const c = list?.find((x) => x.code === code);
  return c?.color_index ? `var(--hq-chart-${c.color_index})` : 'var(--hq-silver-ink)';
}
