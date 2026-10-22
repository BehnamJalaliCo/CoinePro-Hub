'use client';

import Link from 'next/link';
import { useState } from 'react';
import { CompanyMark } from '@/components/brand/marks';
import { Icon } from '@/components/icon';
import { Button, IconButton } from '@/components/ui/button';
import { Sheet } from '@/components/ui/overlay';
import { Card, Empty, ErrorState, FilterChip, PageHeader, Pill, SectionTitle, Skeleton, Switch } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { ApiError } from '@/lib/api/client';
import { useCompanies } from '@/lib/api/hooks';
import { useIncidents, usePutSites, useSites, type Site, type SiteIn } from '@/lib/api/v15';
import { ago, cx, jDateTime } from '@/lib/format';
import { useScope } from '@/lib/scope';

const field = 'h-10 w-full rounded-[10px] border border-strong bg-card px-3 text-[14px] text-ink outline-none focus:border-gold-ink';
type Last = { at?: string; status?: number | null; ms?: number | null; ok?: boolean; error?: string | null } | null;
const pct = (v: number | null) => (v == null ? '—' : `${(v * 100).toFixed(v >= 0.999 || v === 0 ? 0 : 1)}%`);

function SiteRow({ s }: { s: Site }) {
  const last = s.last as Last;
  const down = s.enabled && last?.ok === false;
  return (
    <li className={cx('flex flex-col gap-1.5 rounded-[12px] p-3', down ? 'bg-neg-soft' : 'bg-tile', !s.enabled && 'opacity-60')}>
      <div className="flex items-center gap-2">
        <span className={cx('size-2.5 flex-none rounded-full', !s.enabled ? 'bg-muted' : down ? 'bg-neg' : 'bg-pos')} aria-hidden />
        <a href={s.url} target="_blank" rel="noopener noreferrer" dir="ltr" className="fig min-w-0 flex-1 truncate text-left text-[13px] text-ink hover:underline">{s.url.replace(/^https?:\/\//, '')}</a>
        {s.canary ? <Pill tone="neutral">canary</Pill> : null}
        {!s.enabled ? <Pill tone="neutral">خاموش</Pill> : null}
      </div>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted">
        <span className="fig">{s.kind} · {s.method}</span>
        <span>۲۴ ساعت: <span className="fig text-sec">{pct(s.uptime_24h)}</span></span>
        {last ? <span className="fig">{last.status ?? '—'} · {last.ms != null ? `${last.ms}ms` : '—'}</span> : <span>هنوز چک نشده</span>}
        {last?.at ? <span>{ago(last.at)}</span> : null}
        {s.consecutive_failures ? <span className="text-neg">{s.consecutive_failures.toLocaleString('fa-IR')} شکست پشت هم</span> : null}
        {last?.error ? <span dir="ltr" className="fig text-neg">{last.error}</span> : null}
      </div>
    </li>
  );
}

/** One company's list, replaced as a whole (§16.6 PUT /ops/sites): left-out URLs are switched off, never deleted; canaries stay. */
function EditSites({ company, sites, onClose }: { company: string; sites: Site[]; onClose: () => void }) {
  const put = usePutSites();
  const toast = useToast();
  const [rows, setRows] = useState<SiteIn[]>(sites.filter((s) => !s.canary).map((s) => ({ url: s.url, kind: s.kind as SiteIn['kind'], method: s.method as SiteIn['method'], interval_s: s.interval_s, enabled: s.enabled })));
  const patch = (i: number, p: Partial<SiteIn>) => setRows(rows.map((r, j) => (j === i ? { ...r, ...p } : r)));
  const valid = rows.every((r) => /^https:\/\/[^\s/]+\.[^\s]+$/.test(r.url.trim())) && new Set(rows.map((r) => r.url.trim())).size === rows.length;
  const save = async () => {
    try {
      await put.mutateAsync({ company, sites: rows.map((r) => ({ ...r, url: r.url.trim() })) });
      toast({ tone: 'ok', text: 'فهرست سایت‌ها ذخیره شد.' });
      onClose();
    } catch (e) { toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'ذخیره نشد.' }); }
  };
  return (
    <Sheet open onOpenChange={(v) => !v && onClose()} title={<span className="flex items-center gap-2">سایت‌های <CompanyMark code={company} height={14} /></span>} width={600}
      description="نشانی‌ای که برداری خاموش میشود و تاریخچه‌اش میماند. نشانی داخلی یا خصوصی پذیرفته نمیشود."
      footer={<><Button variant="primary" icon="seal" loading={put.isPending} disabled={!valid} onClick={save}>ذخیره با passkey</Button><Button variant="ghost" onClick={onClose}>انصراف</Button></>}>
      <div className="flex flex-col gap-3">
        {rows.map((r, i) => (
          <div key={i} className="flex flex-col gap-2 rounded-[12px] bg-tile p-3">
            <div className="flex items-center gap-2">
              <input value={r.url} onChange={(e) => patch(i, { url: e.target.value })} dir="ltr" placeholder="https://…" aria-label="نشانی" className={cx(field, 'fig flex-1')} />
              <IconButton icon="close" label="برداشتن" size={36} onClick={() => setRows(rows.filter((_, j) => j !== i))} />
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {(['web', 'api', 'bot'] as const).map((k) => <FilterChip key={k} selected={r.kind === k} onClick={() => patch(i, { kind: k })}><span className="fig">{k}</span></FilterChip>)}
              <span className="w-2" />
              {(['GET', 'HEAD'] as const).map((m) => <FilterChip key={m} selected={r.method === m} onClick={() => patch(i, { method: m })}><span className="fig">{m}</span></FilterChip>)}
              <span className="flex-1" />
              <label className="flex items-center gap-2 text-[12px] text-sec">هر
                <select value={r.interval_s} onChange={(e) => patch(i, { interval_s: Number(e.target.value) })} className="h-8 rounded-[8px] border border-strong bg-card px-2 text-[12px] text-ink">
                  {[30, 60, 300, 900].map((n) => <option key={n} value={n}>{n < 60 ? `${n} ثانیه` : `${n / 60} دقیقه`}</option>)}
                </select>
              </label>
              <Switch label="روشن" checked={r.enabled} onChange={(v) => patch(i, { enabled: v })} />
            </div>
          </div>
        ))}
        {rows.length < 50 ? <Button variant="text" size="sm" icon="add" onClick={() => setRows([...rows, { url: 'https://', kind: 'web', method: 'GET', interval_s: 60, enabled: true }])}>نشانی تازه</Button> : null}
      </div>
    </Sheet>
  );
}

/** Site checks and incidents (§16.4): every product URL, its last check, 24 h uptime, and the incidents it opened. */
export default function SitesPage() {
  const { company } = useScope();
  const { data: companies } = useCompanies();
  const sites = useSites(company);
  const incidents = useIncidents({ company });
  const [edit, setEdit] = useState<string | null>(null);
  const byCompany = new Map<string, Site[]>();
  for (const s of sites.data ?? []) byCompany.set(s.company, [...(byCompany.get(s.company) ?? []), s]);
  const open = (incidents.data ?? []).filter((x) => !x.closed_at);
  const closed = (incidents.data ?? []).filter((x) => x.closed_at);
  return (
    <>
      <PageHeader eyebrow="هر دقیقه از بیرون؛ با شکست پشت هم، حادثه و بیدار شدن SRE" title="پایش سایت‌ها" />
      <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
        <div className="flex min-w-0 flex-col gap-4">
          {sites.isLoading ? <Skeleton className="h-64 rounded-[16px]" /> : sites.error ? <ErrorState error={sites.error} onRetry={() => sites.refetch()} />
            : !byCompany.size ? <Empty icon="server" title="سایتی ثبت نشده" />
            : [...byCompany].map(([co, list]) => (
              <Card key={co} className="flex flex-col gap-3 p-4">
                <SectionTitle title={<span className="flex items-center gap-2"><CompanyMark code={co} height={16} />{companies?.find((c) => c.code === co)?.name_fa}</span>}
                  action={co !== 'HQ' ? <Button variant="text" size="sm" icon="edit" onClick={() => setEdit(co)}>ویرایش</Button> : null} />
                <ul className="flex flex-col gap-2">{list.map((s) => <SiteRow key={s.id} s={s} />)}</ul>
              </Card>
            ))}
        </div>
        <Card className="flex flex-col gap-3 p-4">
          <SectionTitle title="حادثه‌ها" note="باز بالا" />
          {incidents.isLoading ? <Skeleton className="h-40" /> : !incidents.data?.length ? <p className="py-4 text-center text-[13px] text-muted">حادثه‌ای ثبت نشده.</p> : (
            <ul className="flex flex-col gap-2">
              {[...open, ...closed].map((x) => (
                <li key={x.id} className={cx('flex flex-col gap-1 rounded-[12px] p-3', x.closed_at ? 'bg-tile' : 'bg-neg-soft')}>
                  <span className="flex items-center gap-2 text-[12px]">
                    <span className="fig font-semibold text-ink">{x.ref}</span><CompanyMark code={x.company} height={11} mono />
                    <span className="flex-1" />{x.closed_at ? <Pill tone="pos" dot>بسته</Pill> : <Pill tone="neg" icon="urgent">باز</Pill>}
                  </span>
                  <span dir="ltr" className="fig truncate text-left text-[12px] text-sec">{x.url.replace(/^https?:\/\//, '')}</span>
                  <span className="flex flex-wrap items-center gap-x-3 text-[11px] text-muted">
                    <span>از {jDateTime(x.opened_at)}</span>{x.closed_at ? <span>تا {jDateTime(x.closed_at)}</span> : null}
                    <span className="fig">{x.last_status ?? '—'}</span>{x.last_error ? <span dir="ltr" className="fig">{x.last_error}</span> : null}
                    {x.work_ref ? <Link href={`/work/${x.work_ref}`} className="fig text-gold-ink hover:underline">{x.work_ref}</Link> : null}
                  </span>
                </li>
              ))}
            </ul>
          )}
          <p className="flex items-start gap-2 text-[12px] leading-5 text-muted"><Icon name="info" size={14} />فقط بیرون سایت دیده میشود. متریک داخل سرورها منتظر CR-001 است (تصمیم تو).</p>
        </Card>
      </div>
      {edit ? <EditSites company={edit} sites={byCompany.get(edit) ?? []} onClose={() => setEdit(null)} /> : null}
    </>
  );
}
