'use client';

import { useMemo, useState } from 'react';
import { Icon } from '@/components/icon';
import { Sentinel } from '@/components/brand/avatar';
import { CompanyMark } from '@/components/brand/marks';
import { Chat } from '@/components/chat/chat';
import { Composer } from '@/components/media/composer';
import { Button } from '@/components/ui/button';
import { Md, MdInline } from '@/components/ui/md';
import { Sheet } from '@/components/ui/overlay';
import { Card, Empty, ErrorState, FilterChip, Pill, SectionTitle, Segmented, Skeleton } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { AREA_FA, METHOD_FA, Score, SeverityPill, Spark, rruleFa } from '@/components/v14/bits';
import { ApiError } from '@/lib/api/client';
import { useChallenges, useFindings, useHolds, useOrders, useOversight, useOversightAction, useProtocols, type Finding, type FindingStatus, type Protocol } from '@/lib/api/v14';
import { ACTOR_FA } from '@/lib/labels';
import { ago, cx, jDateTime, until } from '@/lib/format';

type Tab = 'summary' | 'findings' | 'protocols' | 'challenges' | 'orders' | 'chat';

const STATUS_FA: Record<FindingStatus, string> = {
  open: 'باز', acknowledged: 'پذیرفته', fixing: 'در حال رفع', fixed: 'رفع شد (منتظر تأیید)', verified: 'تأیید رفع', disputed: 'مورد اختلاف', closed: 'بسته',
};
const CH_FA: Record<string, { fa: string; tone: 'neutral' | 'gold' | 'lapis' | 'pos' | 'neg' }> = {
  issued: { fa: 'صادر شد', tone: 'neutral' }, accepted: { fa: 'پذیرفته', tone: 'lapis' }, submitted: { fa: 'تحویل شد', tone: 'gold' }, scored: { fa: 'داوری شد', tone: 'pos' }, missed: { fa: 'از دست رفت', tone: 'neg' },
};

function useErr() {
  const toast = useToast();
  return (e: unknown) => toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : e instanceof Error ? e.message : 'انجام نشد.' });
}

function Summary({ go }: { go: (t: Tab) => void }) {
  const q = useOversight();
  const holds = useHolds();
  const act = useOversightAction();
  const err = useErr();
  const toast = useToast();
  if (q.isLoading) return <div className="grid gap-4 lg:grid-cols-2"><Skeleton className="h-64" /><Skeleton className="h-64" /></div>;
  if (q.error || !q.data) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const s = q.data;
  return (
    <div className="grid grid-cols-1 items-start gap-4 xl:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
      <div className="flex min-w-0 flex-col gap-4">
        {(holds.data ?? []).length ? (
          <Card className="flex flex-col gap-3 p-4 ring-1 ring-[var(--hq-gold-ink)]">
            <SectionTitle title="نگه‌داشته‌ها، منتظر تو" note="ناظر نگه داشته؛ فقط تو آزاد یا لغو میکنی" />
            {(holds.data ?? []).map((h) => (
              <div key={h.ref} className="flex flex-col gap-2 rounded-[12px] bg-gold-soft p-3">
                <div className="flex items-center gap-2">
                  <CompanyMark code={h.company} height={14} mono />
                  <span className="min-w-0 flex-1 text-[14px] font-semibold"><MdInline text={h.action.summary_fa} /></span>
                  <span className="fig text-[11px] text-muted">{h.ref}</span>
                </div>
                <p className="text-[13px] leading-6 text-sec"><MdInline text={h.reason_md} /></p>
                <div className="flex flex-wrap items-center gap-2">
                  <Button variant="primary" size="sm" icon="seal" loading={act.release.isPending} onClick={() => act.release.mutateAsync(h.ref).then(() => toast({ tone: 'ok', text: 'آزاد شد؛ اقدام ادامه پیدا میکند.' })).catch(err)}>آزاد کن</Button>
                  <Button variant="danger" size="sm" loading={act.cancel.isPending} onClick={() => act.cancel.mutateAsync(h.ref).then(() => toast({ tone: 'info', text: 'لغو شد؛ اقدام انجام نمیشود.' })).catch(err)}>لغو کن</Button>
                  <span className="text-[11px] text-muted">{ago(h.held_at)}</span>
                </div>
              </div>
            ))}
          </Card>
        ) : null}
        <Card className="flex flex-col gap-3 p-4">
          <SectionTitle title="انطباق شرکت‌ها" note="نتیجه‌ی پروتکل‌ها و یافته‌های باز؛ روند پنج روز" />
          <ul className="flex flex-col gap-1">
            {[...s.compliance].sort((a, b) => b.score - a.score).map((c) => (
              <li key={c.company} className="flex flex-col gap-2 border-b border-div py-3 last:border-0">
                <div className="flex items-center gap-3">
                  <span className="w-10 text-sec"><CompanyMark code={c.company} height={14} mono /></span>
                  <Score value={c.score} className="flex-1" />
                  <Spark values={c.trend} min={40} max={100} />
                </div>
                <div className="flex flex-wrap gap-x-3 gap-y-1 ps-[52px] text-[11px] text-muted">
                  {Object.entries(c.by_area).map(([a, v]) => <span key={a} className={cx((v ?? 100) < 65 && 'text-neg')}>{AREA_FA[a] ?? a} <span className="fig">{v}</span></span>)}
                  {c.findings_open.critical ? <span className="font-semibold text-neg">{c.findings_open.critical} یافته‌ی بحرانی</span> : null}
                </div>
              </li>
            ))}
          </ul>
        </Card>
      </div>
      <div className="flex min-w-0 flex-col gap-4">
        <Card className="flex flex-col gap-3 p-4">
          <SectionTitle title={s.watch.on ? 'در نبودت (در جریان)' : 'آخرین «در نبودت»'} note={s.watch.since ? `از ${jDateTime(s.watch.since)}` : undefined} action={s.watch.on ? <Pill tone="gold" live>نگهبان روشن</Pill> : undefined} />
          <Md text={s.watch.summary_md} className="flex flex-col gap-2 text-[13px] leading-7 text-sec" />
        </Card>
        <Card className="grid grid-cols-2 gap-3 p-4">
          <button type="button" onClick={() => go('findings')} className="flex flex-col items-start gap-1 rounded-[12px] bg-tile p-3 text-start hover:bg-hover">
            <span className="text-caption text-muted">یافته‌ی باز</span>
            <span className="text-[22px] font-semibold">{s.findings_open.critical + s.findings_open.high + s.findings_open.medium + s.findings_open.low}</span>
            <span className="text-[11px] text-neg">{s.findings_open.critical} بحرانی، {s.findings_open.high} بالا</span>
          </button>
          <button type="button" onClick={() => go('protocols')} className="flex flex-col items-start gap-1 rounded-[12px] bg-tile p-3 text-start hover:bg-hover">
            <span className="text-caption text-muted">پروتکل فعال</span>
            <span className="text-[22px] font-semibold">{s.protocols.active}</span>
            <span className="text-[11px] text-sec">{s.protocols.failed_today} با مشکل در آخرین اجرا</span>
          </button>
          <button type="button" onClick={() => go('challenges')} className="col-span-2 flex items-center gap-3 rounded-[12px] bg-tile p-3 text-start hover:bg-hover">
            <Icon name="star" size={20} className="text-gold-ink" />
            <span className="flex-1 text-[13px]">چالش‌های این هفته: {s.challenges_week.issued + (s.challenges_week.accepted ?? 0)} در جریان، {s.challenges_week.submitted} تحویل شده</span>
            <Icon name="next" size={16} mirror className="text-muted" />
          </button>
        </Card>
      </div>
    </div>
  );
}

function FindingSheet({ f, onClose }: { f: Finding | null; onClose: () => void }) {
  const act = useOversightAction();
  const err = useErr();
  const [note, setNote] = useState('');
  if (!f) return null;
  const set = (status: FindingStatus) => act.findingStatus.mutateAsync({ ref: f.ref, status, note: note.trim() }).then(onClose).catch(err);
  return (
    <Sheet open onOpenChange={(v) => !v && onClose()} title={<span className="flex items-center gap-2"><span className="fig text-[13px] text-muted">{f.ref}</span><span><MdInline text={f.title_fa} /></span></span>} width={560}
      footer={f.status === 'fixed' || f.status === 'disputed' ? (
        <div className="flex flex-wrap gap-2">
          <Button variant="primary" icon="seal" loading={act.findingStatus.isPending} onClick={() => set('verified')}>رفع را تأیید کن</Button>
          <Button variant="secondary" onClick={() => set('open')}>دوباره باز کن</Button>
          <Button variant="ghost" onClick={() => set('closed')}>ببند</Button>
        </div>
      ) : f.status !== 'closed' && f.status !== 'verified' ? <Button variant="ghost" onClick={() => set('closed')}>ببند (بی‌اثر یا تکراری)</Button> : undefined}>
      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-2">
          <SeverityPill s={f.severity} />
          <Pill tone="neutral">{STATUS_FA[f.status]}</Pill>
          <span className="flex items-center gap-1.5 text-[12px] text-sec"><CompanyMark code={f.company} height={12} mono />{ACTOR_FA(f.answerable)}</span>
          {f.protocol ? <span className="fig text-[12px] text-muted">{f.protocol}</span> : null}
          <span className="text-[12px] text-muted">موعد: {until(f.due_at)}</span>
        </div>
        <Md text={f.body_md} className="flex flex-col gap-2 text-[14px] leading-7 text-ink" />
        <div className="flex flex-col gap-1.5">
          <span className="text-[12px] font-semibold text-sec">شاهد</span>
          {f.evidence.map((e, i) => (
            <div key={i} className="flex items-center gap-2 rounded-[10px] bg-tile px-3 py-2 text-[12px]">
              <span className="text-muted">{e.kind}</span><span className="fig text-gold-ink">{e.ref}</span><span className="flex-1 text-sec">{e.note}</span>
            </div>
          ))}
        </div>
        <div className="flex flex-col gap-1.5">
          <span className="text-[12px] font-semibold text-sec">تاریخچه</span>
          <ol className="flex flex-col gap-1">
            {f.history.map((h, i) => <li key={i} className="text-[12px] text-sec">{jDateTime(h.at)} · {ACTOR_FA(h.by)} · {STATUS_FA[h.status]}{h.note ? ` — ${h.note}` : ''}</li>)}
          </ol>
        </div>
        {f.status !== 'closed' && f.status !== 'verified' ? (
          <label className="flex flex-col gap-1.5"><span className="text-[12px] text-sec">یادداشت تو (اختیاری)</span>
            <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} className="rounded-[10px] border border-strong bg-tile px-3 py-2 text-[14px] outline-none focus:border-gold-ink" />
          </label>
        ) : null}
      </div>
    </Sheet>
  );
}

function Findings() {
  const [st, setSt] = useState<string>('open');
  const q = useFindings();
  const [open, setOpen] = useState<Finding | null>(null);
  const all = q.data?.items ?? [];
  const live = (f: Finding) => !['verified', 'closed'].includes(f.status);
  const list = all.filter((f) => (st === 'open' ? live(f) : !live(f)));
  const order: Record<string, number> = { critical: 0, high: 1, medium: 2, low: 3, info: 4 };
  return (
    <Card className="flex flex-col gap-3 p-4">
      <div className="flex flex-wrap gap-2">
        <FilterChip selected={st === 'open'} onClick={() => setSt('open')} count={all.filter(live).length}>باز</FilterChip>
        <FilterChip selected={st === 'done'} onClick={() => setSt('done')} count={all.filter((f) => !live(f)).length}>بسته و تأییدشده</FilterChip>
      </div>
      {q.isLoading ? <Skeleton className="h-40" /> : q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : !list.length ? <Empty icon="overseer" title="یافته‌ای نیست" /> : (
        <ul className="flex flex-col">
          {[...list].sort((a, b) => order[a.severity]! - order[b.severity]!).map((f) => (
            <li key={f.ref} className="border-b border-div last:border-0">
              <button type="button" onClick={() => setOpen(f)} className="flex w-full items-start gap-3 rounded-[8px] px-1 py-3 text-start hover:bg-hover">
                <span className="mt-0.5"><SeverityPill s={f.severity} /></span>
                <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                  <span className="text-[14px] font-semibold text-ink"><MdInline text={f.title_fa} /></span>
                  <span className="flex flex-wrap items-center gap-x-2 text-[11px] text-muted">
                    <span className="fig">{f.ref}</span><CompanyMark code={f.company} height={11} mono /><span>{ACTOR_FA(f.answerable)}</span><span>{STATUS_FA[f.status]}</span><span>{until(f.due_at)}</span>
                  </span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
      <FindingSheet f={open} onClose={() => setOpen(null)} />
    </Card>
  );
}

function Protocols() {
  const q = useProtocols();
  const [area, setArea] = useState<string | null>(null);
  const [open, setOpen] = useState<Protocol | null>(null);
  const areas = useMemo(() => [...new Set((q.data ?? []).map((p) => p.area))], [q.data]);
  const list = (q.data ?? []).filter((p) => !area || p.area === area);
  return (
    <Card className="flex flex-col gap-3 p-4">
      <SectionTitle title="دفتر پروتکل‌ها" note="وظایف نوشته‌شده‌ی ناظر؛ نسخه‌ی تازه فقط با مُهر تو" />
      <div className="flex flex-wrap gap-2">
        <FilterChip selected={!area} onClick={() => setArea(null)} count={q.data?.length}>همه</FilterChip>
        {areas.map((a) => <FilterChip key={a} selected={area === a} onClick={() => setArea(a)} count={(q.data ?? []).filter((p) => p.area === a).length}>{AREA_FA[a] ?? a}</FilterChip>)}
      </div>
      {q.isLoading ? <Skeleton className="h-60" /> : (
        <ul className="grid gap-x-6 xl:grid-cols-2">
          {list.map((p) => (
            <li key={p.ref} className="border-b border-div">
              <button type="button" onClick={() => setOpen(p)} className="flex w-full items-center gap-3 rounded-[8px] px-1 py-2.5 text-start hover:bg-hover">
                <span className="fig w-14 text-[11px] text-muted">{p.ref}</span>
                <span className="flex min-w-0 flex-1 flex-col">
                  <span className="truncate text-[13px] text-ink">{p.title_fa}</span>
                  <span className="text-[11px] text-muted">{METHOD_FA[p.method] ?? p.method} · {rruleFa(p.schedule)}</span>
                </span>
                {p.last_run ? <Pill tone={p.last_run.result === 'pass' ? 'pos' : p.last_run.result === 'fail' ? 'neg' : 'warn'} dot>{p.last_run.result === 'pass' ? 'قبول' : p.last_run.result === 'fail' ? 'رد' : 'نیمه'}</Pill> : <Pill tone="neutral">هنوز نه</Pill>}
              </button>
            </li>
          ))}
        </ul>
      )}
      {open ? (
        <Sheet open onOpenChange={(v) => !v && setOpen(null)} title={<span className="flex items-center gap-2"><span className="fig text-[13px] text-muted">{open.ref}</span>{open.title_fa}</span>} width={560}>
          <div className="flex flex-col gap-3 text-[13px]">
            <div className="flex flex-wrap gap-2"><Pill tone="neutral">{AREA_FA[open.area]}</Pill><Pill tone="neutral">{METHOD_FA[open.method]}</Pill><SeverityPill s={open.severity} /><Pill tone="neutral">{rruleFa(open.schedule)}</Pill></div>
            <div className="flex flex-col gap-1"><span className="font-semibold text-sec">چه چیزی چک میشود</span><p dir="ltr" className="rounded-[10px] bg-tile p-3 text-left text-[12px] leading-6 text-ink">{open.check_md}</p></div>
            <div className="flex flex-col gap-1"><span className="font-semibold text-sec">شاهد</span><p dir="ltr" className="text-left text-[12px] text-sec">{open.evidence_md}</p></div>
            <p className="text-[12px] text-muted">پاسخ‌گو: {open.answerable} · نسخه‌ی <span className="fig">{open.version}</span>{open.last_run ? <> · آخرین اجرا {ago(open.last_run.at)}، {open.last_run.findings} یافته</> : null}</p>
          </div>
        </Sheet>
      ) : null}
    </Card>
  );
}

function Challenges() {
  const q = useChallenges();
  const items = q.data?.items ?? [];
  return (
    <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
      {q.isLoading ? <Skeleton className="h-40" /> : items.map((c) => (
        <Card key={c.ref} className="flex flex-col gap-2 p-4">
          <div className="flex items-center gap-2">
            <CompanyMark code={c.company} height={14} mono />
            <span className="min-w-0 flex-1 truncate text-[14px] font-semibold"><MdInline text={c.title_fa} /></span>
            <Pill tone={CH_FA[c.status]!.tone}>{CH_FA[c.status]!.fa}</Pill>
          </div>
          <p className="text-[12px] leading-6 text-sec">{c.brief_md}</p>
          <div className="flex flex-wrap gap-1">{c.criteria.map((k) => <span key={k.name_fa} className="rounded-full bg-tile px-2 py-0.5 text-[11px] text-sec">{k.name_fa} <span className="fig">{k.weight}%</span></span>)}</div>
          <div className="flex items-center gap-3 text-[11px] text-muted">
            <span className="fig">{c.ref}</span><span>داور: {ACTOR_FA(c.judge)}</span><span className="flex-1">{c.status === 'scored' ? '' : until(c.due_at)}</span>
            {c.score != null ? <Score value={c.score} className="w-32" /> : null}
          </div>
        </Card>
      ))}
    </div>
  );
}

function Orders() {
  const q = useOrders();
  const act = useOversightAction();
  const err = useErr();
  const toast = useToast();
  const [all, setAll] = useState(false);
  return (
    <div className="grid grid-cols-1 items-start gap-4 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
      <Card className="flex flex-col gap-3 p-4">
        <SectionTitle title="دستورهای دائمی تو" note="با مُهر تو قطعی میشوند؛ ناظر طبق آن‌ها داوری میکند" />
        {(q.data ?? []).map((o) => (
          <div key={o.ref} className={cx('flex flex-col gap-2 rounded-[12px] p-3', o.status === 'proposed' ? 'bg-gold-soft' : 'bg-tile', o.status === 'retired' && 'opacity-60')}>
            <div className="flex items-center gap-2 text-[11px] text-muted">
              <span className="fig">{o.ref}</span>{o.source === 'voice' ? <Icon name="mic" size={12} /> : null}
              <span>{o.applies_to === 'all' ? 'برای همه' : 'برای ناظر'}</span>
              <span className="flex-1" />
              <Pill tone={o.status === 'sealed' ? 'pos' : o.status === 'proposed' ? 'gold' : 'neutral'}>{o.status === 'sealed' ? 'مُهرشده' : o.status === 'proposed' ? 'منتظر مُهر' : 'بازنشسته'}</Pill>
            </div>
            <p className="text-[14px] leading-7 text-ink">{o.text_md}</p>
            {o.status === 'proposed' ? <div><Button variant="primary" size="sm" icon="seal" loading={act.sealOrder.isPending} onClick={() => act.sealOrder.mutateAsync(o.ref).then(() => toast({ tone: 'ok', text: 'مُهر شد؛ از همین حالا اجرا میشود.' })).catch(err)}>مُهر کن</Button></div>
              : o.status === 'sealed' ? <div><Button variant="ghost" size="sm" onClick={() => act.retireOrder.mutateAsync(o.ref).catch(err)}>بازنشسته کن</Button></div> : null}
          </div>
        ))}
      </Card>
      <Card className="flex flex-col gap-3 p-4">
        <SectionTitle title="دستور تازه" note="بگو یا بنویس؛ ناظر آن را دقیق میکند و تو مُهر میکنی" />
        <div className="flex gap-2"><FilterChip selected={!all} onClick={() => setAll(false)}>برای ناظر</FilterChip><FilterChip selected={all} onClick={() => setAll(true)}>برای همه‌ی ایجنت‌ها</FilterChip></div>
        <Composer placeholder="مثلاً: هر انتشار بدون تست بار پنج‌سناریویی را نگه دار" purpose="note" allowFiles={false} label="دستور دائمی"
          onSend={async (v) => { await act.newOrder.mutateAsync({ text_md: v.body, source: v.attachments.length ? 'voice' : 'text', file_id: v.attachments[0] ?? null, applies_to: all ? 'all' : 'overseer' }).catch((e) => { err(e); throw e; }); toast({ tone: 'ok', text: 'ثبت شد؛ برای مُهر در فهرست آمد.' }); }} />
      </Card>
    </div>
  );
}

/** ناظر کل (contract §18.1): the owner's eyes on everything. Holds, findings, protocols, challenges, standing orders and thread N. */
export default function OversightPage() {
  const [tab, setTab] = useState<Tab>('summary');
  return (
    <>
      <header className="flex flex-wrap items-center gap-4">
        <Sentinel size={56} state="working" />
        <div className="flex min-w-0 flex-[1_1_16rem] flex-col">
          <span className="text-caption text-muted">رتبه‌ی دوم، کنار مشاور کل؛ در نظارت و در نبود تو بالاتر</span>
          <h1 className="text-h1 font-semibold">ناظر کل</h1>
        </div>
        <span className="fig hidden rounded-full bg-tile px-3 py-1 text-[12px] text-sec sm:inline">Opus 5.5 · xhigh</span>
      </header>
      <div className="overflow-x-auto pb-1">
        <Segmented<Tab> label="بخش‌های ناظر" value={tab} onChange={setTab} options={[
          { value: 'summary', label: 'خلاصه' }, { value: 'findings', label: 'یافته‌ها' }, { value: 'protocols', label: 'پروتکل‌ها' },
          { value: 'challenges', label: 'چالش‌ها' }, { value: 'orders', label: 'دستورهای دائمی' }, { value: 'chat', label: 'گفت‌وگو' },
        ]} />
      </div>
      {tab === 'summary' ? <Summary go={setTab} /> : tab === 'findings' ? <Findings /> : tab === 'protocols' ? <Protocols /> : tab === 'challenges' ? <Challenges /> : tab === 'orders' ? <Orders /> : (
        <div className="mx-auto flex h-[calc(100dvh-64px-220px)] min-h-[480px] w-full max-w-[920px] flex-col">
          <Chat code="N" agentKind="overseer" placeholder="آموزش بده، بپرس یا دستور بده… (با ویس هم)" />
        </div>
      )}
    </>
  );
}
