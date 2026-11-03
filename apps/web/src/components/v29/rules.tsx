'use client';

// ⟨1.11⟩ Contract §29.3 «قانون‌های من»: every rule the owner made for the holding (= the standing orders), newest first, with whom it applies
// to, how often it was applied, broken and fixed; a proposed one sealed in one tap, a sealed one edited into a new version (sealed again)
// or retired.

import { useState } from 'react';
import { Icon } from '@/components/icon';
import { Button } from '@/components/ui/button';
import { Dialog } from '@/components/ui/overlay';
import { Card, Empty, ErrorState, FilterChip, Pill, Skeleton } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { ApiError } from '@/lib/api/client';
import { useCompanies } from '@/lib/api/hooks';
import { appliesFa, useRuleActions, useRules, type Rule } from '@/lib/api/v29';
import { jDate } from '@/lib/format';
import { FaText } from './text';

const STATUS: Record<Rule['status'], { fa: string; tone: 'gold' | 'pos' | 'silver' }> = { proposed: { fa: 'منتظر مُهر', tone: 'gold' }, sealed: { fa: 'فعال', tone: 'pos' }, retired: { fa: 'بازنشسته', tone: 'silver' } };
type Tab = 'active' | 'proposed' | 'retired' | 'all';
const TABS: Array<[Tab, string]> = [['active', 'فعال'], ['proposed', 'منتظر مُهر'], ['retired', 'بازنشسته'], ['all', 'همه']];

function RuleCard({ r }: { r: Rule }) {
  const toast = useToast();
  const act = useRuleActions();
  const { data: companies } = useCompanies();
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(r.text_md);
  const [retire, setRetire] = useState(false);
  const name = (c: string) => companies?.find((x) => x.code === c)?.name_fa ?? c;
  const st = STATUS[r.status] ?? { fa: r.status, tone: 'silver' as const };
  const fail = (e: unknown, t: string) => toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : t });
  const c = r.counts;
  const applied = c?.applied ?? c?.runs ?? null;
  return (
    <Card as="article" aria-label={r.text_md} className="flex flex-col gap-3 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Pill tone={st.tone} dot>{st.fa}</Pill>
        <span className="text-[12px] text-sec">برای: {appliesFa(r.applies_to, name)}</span>
        <span className="flex-1" />
        <span className="text-[11px] text-muted">{r.source === 'voice' ? 'با صدا' : 'نوشته'}، {jDate(r.created_at)}{r.version > 1 ? <>، نسخه‌ی <span className="fig">{r.version}</span></> : null}</span>
      </div>
      {editing ? (
        <label className="flex flex-col gap-1.5">
          <span className="text-[12px] text-sec">متن تازه؛ با مُهر، نسخه‌ی تازه جای قبلی را میگیرد</span>
          <textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} maxLength={2000} aria-label="متن تازه‌ی قانون"
            className="w-full rounded-[12px] border border-strong bg-tile px-3 py-2.5 text-[14px] leading-7 text-ink outline-none focus:border-gold-ink" />
        </label>
      ) : <p className="text-justify text-[15px] font-semibold leading-7 [text-align-last:start]"><FaText text={r.text_md} /></p>}
      {r.status !== 'proposed' && c ? (
        <div className="flex flex-wrap gap-2 text-[12px]">
          <span className="rounded-full bg-tile px-2.5 py-1 text-sec">به کار رفت در <span className="fig font-semibold text-ink">{applied ?? 0}</span> اجرا</span>
          <span className="rounded-full bg-tile px-2.5 py-1 text-sec"><span className="fig font-semibold text-ink">{c.violations ?? 0}</span> تخلف</span>
          <span className="rounded-full bg-tile px-2.5 py-1 text-sec"><span className="fig font-semibold text-ink">{c.fixed ?? 0}</span> اصلاح</span>
        </div>
      ) : r.status === 'sealed' ? <span className="text-[12px] text-muted">گزارش اول اجرا ۲۴ ساعت بعد از مُهر میاید.</span> : null}
      <div className="flex flex-wrap gap-2">
        {r.status === 'proposed' ? (
          <Button variant="primary" icon="seal" loading={act.seal.isPending} onClick={() => act.seal.mutate(r.ref, { onSuccess: () => toast({ tone: 'ok', text: 'مُهر شد؛ از همین حالا در کار نقش‌ها می‌نشیند.' }), onError: (e) => fail(e, 'مُهر نشد.') })}>مُهر کن</Button>
        ) : null}
        {r.status === 'sealed' && !editing ? <Button variant="secondary" icon="edit" onClick={() => { setText(r.text_md); setEditing(true); }}>ویرایش</Button> : null}
        {editing ? (
          <>
            <Button variant="primary" icon="seal" disabled={text.trim().length < 3 || text.trim() === r.text_md} loading={act.edit.isPending}
              onClick={() => act.edit.mutate({ ref: r.ref, text: text.trim() }, { onSuccess: () => { setEditing(false); toast({ tone: 'ok', text: 'نسخه‌ی تازه مُهر شد.' }); }, onError: (e) => fail(e, 'ذخیره نشد.') })}>مُهر نسخه‌ی تازه</Button>
            <Button variant="ghost" onClick={() => setEditing(false)}>انصراف</Button>
          </>
        ) : null}
        {r.status !== 'retired' && !editing ? <Button variant="ghost" icon="dismiss" onClick={() => setRetire(true)}>بازنشسته کن</Button> : null}
      </div>
      <Dialog open={retire} onOpenChange={setRetire} title="این قانون بازنشسته شود؟"
        actions={<>
          <Button variant="danger" icon="dismiss" loading={act.retire.isPending} onClick={() => act.retire.mutate(r.ref, { onSuccess: () => { setRetire(false); toast({ tone: 'info', text: 'بازنشسته شد؛ دیگر در کار هیچ نقشی نمی‌نشیند.' }); }, onError: (e) => fail(e, 'انجام نشد.') })}>بازنشسته کن</Button>
          <Button variant="ghost" onClick={() => setRetire(false)}>انصراف</Button>
        </>}>
        از این پس در کار هیچ نقشی نمی‌نشیند و ناظر آن را نمیپاید. سابقه‌اش میماند.
      </Dialog>
    </Card>
  );
}

export function RulesList({ onNew }: { onNew: () => void }) {
  const q = useRules();
  const [tab, setTab] = useState<Tab>('active');
  const all = q.data ?? [];
  const groups: Record<Tab, Rule[]> = {
    active: all.filter((r) => r.status === 'sealed'), proposed: all.filter((r) => r.status === 'proposed'), retired: all.filter((r) => r.status === 'retired'), all,
  };
  const list = groups[tab];
  return (
    <>
      <div className="no-scrollbar -mx-1 flex gap-2 overflow-x-auto px-1">
        {TABS.map(([k, l]) => <FilterChip key={k} selected={tab === k} onClick={() => setTab(k)} count={q.data ? groups[k].length : undefined}>{l}</FilterChip>)}
      </div>
      {q.isLoading ? <div className="flex flex-col gap-3">{Array.from({ length: 3 }, (_, i) => <Skeleton key={i} className="h-36 rounded-[16px]" />)}</div>
        : q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} />
        : !list.length ? <Card><Empty icon="seal" title={tab === 'proposed' ? 'قانونی منتظر مُهر نیست' : tab === 'retired' ? 'قانون بازنشسته‌ای نیست' : 'هنوز قانونی نگذاشته‌ای'} body="«این دیگر تکرار نشود» را بگو یا بنویس؛ منشی آن را یک دستور روشن میکند و ناظر آن را هر روز میپاید." action={<Button icon="seal" onClick={onNew}>قانون تازه</Button>} /></Card>
        : <div className="grid items-start gap-3 lg:grid-cols-2">{list.map((r) => <RuleCard key={r.ref} r={r} />)}</div>}
      <p className="flex items-start gap-1.5 text-[11px] leading-5 text-muted"><Icon name="info" size={13} className="mt-0.5" />هر قانون مُهرشده در دستور کار همه‌ی نقش‌هایی که به آن‌ها مربوط است می‌نشیند. ناظر هر روز با قاعده آن را میسنجد و فقط برای نمونه مدل میخواند.</p>
    </>
  );
}
