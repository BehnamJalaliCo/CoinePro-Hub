'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense } from 'react';
import { Icon } from '@/components/icon';
import { Button } from '@/components/ui/button';
import { Card, Empty, ErrorState, PageHeader, Pill, Skeleton, Switch } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import type { IconName } from '@/generated/icons';
import { useCompanies } from '@/lib/api/hooks';
import { faError, useSourceSwitch, useSources } from '@/lib/api/v20';
import { cx } from '@/lib/format';
import { ClassTag, JStamp, useArchive } from '@/components/v20/bits';
import { PartiesTab } from '@/components/v20/parties';
import { AttrValue, PART_ORDER, RowEditor, extraParts, partUI, rowKey, rowsOf, subjectFa, type PartUI, type Row } from '@/components/v20/schema';

function Tabs({ tabs, value, onChange }: { tabs: Array<{ key: string; fa: string; icon: IconName }>; value: string; onChange: (k: string) => void }) {
  return (
    <div className="-mx-1 overflow-x-auto px-1 pb-1">
      <div role="tablist" aria-label="بخش‌های طرح بایگانی" className="flex w-max gap-1.5">
        {tabs.map((t) => (
          <button key={t.key} type="button" role="tab" aria-selected={value === t.key} onClick={() => onChange(t.key)}
            className={cx('inline-flex h-9 flex-none items-center gap-1.5 whitespace-nowrap rounded-full px-3.5 text-[13px] transition-colors', value === t.key ? 'tahrir bg-gold-soft font-semibold text-gold-ink' : 'border border-strong text-sec hover:bg-hover hover:text-ink')}>
            <Icon name={t.icon} size={15} />{t.fa}
          </button>
        ))}
      </div>
    </div>
  );
}

function PartRows({ part, ui, rows, open }: { part: string; ui: PartUI; rows: Row[]; open: (r: Row | null) => void }) {
  const m = useArchive();
  const { data: companies } = useCompanies();
  const sorted = [...rows].sort((a, b) => Number(a.status === 'retired') - Number(b.status === 'retired'));
  // The two attributes after the title say most about a row when the part has no summary of its own.
  const shown = ui.attrs.filter((a) => a.key !== 'title_fa' && !['fields', 'when', 'do', 'json'].includes(a.kind)).slice(0, 2);
  return (
    <Card className="flex min-w-0 flex-col gap-1 p-2">
      <div className="flex flex-wrap items-center gap-2 px-2 py-1.5">
        <p className="min-w-0 flex-1 text-[12px] leading-5 text-muted">{ui.note}</p>
        <Button size="sm" variant="secondary" icon="add" onClick={() => open(null)}>تازه</Button>
      </div>
      {!sorted.length ? <Empty icon={ui.icon} title="هنوز چیزی نیست" /> : (
        <ul className="flex flex-col">
          {sorted.map((r) => {
            const k = rowKey(part, ui, r);
            const retired = r.status === 'retired';
            const title = part === 'clearance' ? subjectFa(r.subject as never) : part === 'reminders' ? `${m.cls(String(r.class))?.title_fa ?? String(r.class)}: ${m.cls(String(r.class))?.fields.find((f) => f.key === r.field)?.title_fa ?? String(r.field)}` : String(r.title_fa ?? k);
            return (
              <li key={k}>
                <button type="button" onClick={() => open(r)} className={cx('flex w-full min-w-0 flex-col gap-1 rounded-[12px] px-3 py-2.5 text-start transition-colors hover:bg-hover', retired && 'opacity-60')}>
                  <span className="flex min-w-0 items-center gap-2">
                    <span className="min-w-0 flex-1 truncate text-[14px] font-semibold text-ink">{title}</span>
                    {retired ? <Pill className="h-5 text-[11px]">بازنشسته</Pill> : null}
                    {ui.usage?.(r) ? <span className="text-[11px] text-muted">{ui.usage(r)}</span> : null}
                  </span>
                  <span className="flex min-w-0 flex-wrap items-center gap-x-2.5 gap-y-1 text-[11px] text-muted">
                    <span className="fig">{k}{r.version ? ` · v${String(r.version)}` : ''}</span>
                    {ui.sub ? <span className="min-w-0">{ui.sub(r, m, companies)}</span> : shown.map((a) => <span key={a.key} className="min-w-0">{a.fa}: <AttrValue a={a} v={r[a.key]} m={m} row={r} /></span>)}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}

function SourcesTab() {
  const q = useSources();
  const sw = useSourceSwitch();
  const toast = useToast();
  const flip = async (key: string, on: boolean) => {
    try { await sw.mutateAsync({ [key]: on }); toast({ tone: 'info', text: on ? 'روشن شد؛ از این به بعد خودش بایگانی میکند.' : 'خاموش شد؛ سندهای قبلی میمانند.' }); } catch (e) { toast({ tone: 'error', text: faError(e) }); }
  };
  return (
    <Card className="flex min-w-0 flex-col gap-1 p-2">
      <p className="px-2 py-1.5 text-[12px] leading-5 text-muted">آنچه هاب خودش بایگانی میکند، هر کدام ثبت‌شده با نوع سند خودش و منبع «خودکار». فهرست منبع‌ها واژگان بسته است؛ روشن یا خاموش کردنش با توست.</p>
      {q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : q.isLoading ? <Skeleton className="h-40" /> : (
        <ul className="flex flex-col">
          {(q.data ?? []).map((s) => (
            <li key={s.key} className="flex min-w-0 items-start gap-3 rounded-[12px] px-3 py-2.5">
              <span className="flex min-w-0 flex-1 flex-col gap-1">
                <span className="text-[14px] font-semibold text-ink">{s.title_fa}</span>
                <span className="flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[11px] text-muted">
                  <span className="fig">{s.key}</span><ClassTag cls={s.class} />
                  <span>{s.filed ? `${s.filed} سند بایگانی کرده` : 'هنوز سندی نیامده'}</span>
                  {s.last_at ? <span>آخرین: <JStamp at={s.last_at} /></span> : null}
                </span>
                {s.note_fa ? <span className="text-[12px] text-sec">{s.note_fa}</span> : null}
              </span>
              <Switch label={s.title_fa} checked={s.enabled} disabled={sw.isPending} onChange={(v) => void flip(s.key, v)} />
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function SettingsInner() {
  const params = useSearchParams();
  const router = useRouter();
  const m = useArchive();
  const schema = m.schema as unknown as Record<string, unknown> | undefined;
  const parts = [...PART_ORDER, ...extraParts(schema)];
  const tabs = [
    ...parts.map((p) => ({ key: p, fa: partUI(p, rowsOf(m, p)).fa, icon: partUI(p, rowsOf(m, p)).icon })),
    { key: 'parties', fa: 'طرف‌ها', icon: 'companies' as IconName },
    { key: 'sources', fa: 'منبع‌های خودکار', icon: 'server' as IconName },
  ];
  const tab = tabs.some((t) => t.key === params.get('tab')) ? params.get('tab')! : 'classes';
  const sel = params.get('ref');
  const isNew = params.get('new') === '1';
  const go = (t: string, ref?: string | null, fresh?: boolean) => router.replace(`/archive/settings?tab=${t}${ref ? `&ref=${encodeURIComponent(ref)}` : ''}${fresh ? '&new=1' : ''}`, { scroll: false });
  const rows = rowsOf(m, tab);
  const ui = partUI(tab, rows);
  const editing = sel ? rows.find((r) => rowKey(tab, ui, r) === sel) ?? null : null;
  return (
    <>
      <PageHeader eyebrow="بایگانی · لایه‌ی باز: همه‌چیزی که بایگانی را توصیف میکند داده است" title="طرح بایگانی">
        <p className="max-w-3xl text-[13px] leading-6 text-sec">نوع سندها و فیلدهایشان، پوشه‌ها، سطح‌ها، مجوزها، نگهداری، یادآورها، طرف‌ها، پیوندها و خودکارها را خودت از همین‌جا عوض میکنی، بی‌انتشار تازه. هر ذخیره اول اثرش را نشان میدهد، بعد passkey میخواهد. هیچ چیزی حذف نمیشود؛ فقط بازنشسته. ایجنت‌ها فقط پیشنهاد میدهند (کارت «تغییر طرح بایگانی»).</p>
      </PageHeader>
      <Tabs tabs={tabs} value={tab} onChange={(t) => go(t)} />
      {m.q.error ? <ErrorState error={m.q.error} onRetry={() => m.q.refetch()} /> : m.q.isLoading ? <Skeleton className="h-64" />
        : tab === 'sources' ? <SourcesTab />
          : tab === 'parties' ? <PartiesTab sel={sel} onOpen={(ref) => go('parties', ref)} />
            : <PartRows part={tab} ui={ui} rows={rows} open={(r) => (r ? go(tab, rowKey(tab, ui, r)) : go(tab, null, true))} />}
      {m.schema && tab !== 'sources' && tab !== 'parties' && (editing || isNew) ? <RowEditor key={`${tab}:${sel ?? 'new'}:${String(editing?.version ?? '')}`} part={tab} ui={ui} row={editing} onClose={() => go(tab)} /> : null}
    </>
  );
}

/** طرح بایگانی (contract §23.10): the open layer, one tab per part, every form drawn from the schema and its closed vocabulary. */
export default function ArchiveSettingsPage() {
  return <Suspense><SettingsInner /></Suspense>;
}
