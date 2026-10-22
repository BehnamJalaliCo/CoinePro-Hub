'use client';

import Link from 'next/link';
import { useState } from 'react';
import { Icon } from '@/components/icon';
import { Button } from '@/components/ui/button';
import { MdInline } from '@/components/ui/md';
import { Dialog } from '@/components/ui/overlay';
import { Card, Empty, ErrorState, FilterChip, PageHeader, Pill, SectionTitle, Segmented, Skeleton, StatTile } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { Confidence, PRINCIPLE, VERDICT3, pct01 } from '@/components/v18/bits';
import { RefChip } from '@/components/v17/bits';
import { faError, useDigitalCeo, usePredictions, usePrincipleAction, usePrinciples, useSaveSettings18, useSettings18, type DceoStats, type DceoWindow, type Principle } from '@/lib/api/v18';
import { ago, cx, jDateTime } from '@/lib/format';
import { DECISION_KIND } from '@/lib/labels';

const WINDOWS: Array<{ value: DceoWindow; label: string }> = [{ value: '30d', label: '۳۰ روز' }, { value: '90d', label: '۹۰ روز' }, { value: 'all', label: 'همه' }];

/** Reliability: each confidence bucket's hit rate against the bucket's middle (a calibrated predictor sits on the diagonal). */
function Calibration({ s }: { s: DceoStats }) {
  if (!s.calibration.length) return <p className="text-[12px] text-muted">هنوز داده‌ای نیست.</p>;
  return (
    <div className="flex flex-col gap-2">
      {s.calibration.map((c) => {
        const [lo, hi] = c.bucket.split('-').map(Number) as [number, number];
        const mid = (lo + hi) / 2;
        return (
          <div key={c.bucket} className="grid grid-cols-[4.5rem_minmax(0,1fr)_3rem] items-center gap-2 text-[11px]">
            <span className="fig text-muted" dir="ltr">{c.bucket}</span>
            <span className="relative h-3 overflow-hidden rounded-full bg-tile" dir="ltr" aria-label={`بازه‌ی ${c.bucket}: ${pct01(c.hit_rate)} درست از ${c.n}`}>
              <span className="absolute inset-y-0 left-0 rounded-full bg-[var(--hq-silver-ink)] opacity-70" style={{ width: `${c.hit_rate * 100}%` }} />
              <span className="absolute inset-y-0 w-0.5 bg-gold" style={{ left: `${mid * 100}%` }} title="انتظار" />
            </span>
            <span className="fig text-left text-sec">{pct01(c.hit_rate)} <span className="text-muted">·{c.n}</span></span>
          </div>
        );
      })}
      <p className="text-[11px] text-muted">نوار: درصد درست در هر بازه‌ی اطمینان؛ خط طلایی: آنچه پیش‌بین وعده داده بود.</p>
    </div>
  );
}

function PrincipleRow({ p }: { p: Principle }) {
  const act = usePrincipleAction();
  const toast = useToast();
  const [edit, setEdit] = useState(false);
  const [text, setText] = useState(p.text_fa);
  const st = PRINCIPLE[p.status] ?? PRINCIPLE.active!;
  const fail = (e: unknown) => toast({ tone: 'error', text: faError(e) });
  return (
    <li className={cx('flex flex-col gap-2 rounded-[12px] p-3', p.status === 'proposed' ? 'bg-gold-soft' : 'bg-tile', p.status === 'retired' && 'opacity-70')}>
      <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted">
        <span className="fig">{p.ref}</span><span>نسخه‌ی <span className="fig">{p.version}</span></span>{p.edited_by_owner ? <span>ویرایش تو</span> : null}<span>{ago(p.updated_at)}</span>
        <span className="flex-1" /><Pill tone={st.tone} dot>{st.fa}</Pill>
      </div>
      {edit ? <textarea value={text} onChange={(e) => setText(e.target.value)} rows={2} maxLength={500} aria-label={`متن ${p.ref}`} className="w-full rounded-[10px] border border-strong bg-card p-2 text-[13px] leading-6 text-ink outline-none focus:border-gold-ink" />
        : <p className={cx('text-[14px] leading-7 text-ink', p.status === 'retired' && 'line-through decoration-[var(--hq-text-muted)]')}>{p.text_fa}</p>}
      <div className="flex flex-wrap items-center gap-1.5">
        {p.sources.map((s, i) => <RefChip key={i} r={s.ref} tone="neutral" />)}
        <span className="flex-1" />
        {edit ? (
          <>
            <Button size="sm" variant="primary" disabled={!text.trim() || text.trim() === p.text_fa} loading={act.edit.isPending} onClick={() => act.edit.mutateAsync({ p, text_fa: text.trim(), status: 'active' }).then(() => setEdit(false), fail)}>نسخه‌ی تازه</Button>
            <Button size="sm" variant="ghost" onClick={() => { setEdit(false); setText(p.text_fa); }}>انصراف</Button>
          </>
        ) : (
          <>
            {p.status === 'proposed' ? <Button size="sm" variant="secondary" icon="seal" loading={act.accept.isPending} onClick={() => act.accept.mutateAsync(p.ref).catch(fail)}>بپذیر</Button> : null}
            {p.status !== 'retired' ? <Button size="sm" variant="ghost" icon="edit" onClick={() => setEdit(true)}>ویرایش</Button> : null}
            {p.status !== 'retired' ? <Button size="sm" variant="ghost" icon="close" loading={act.edit.isPending} onClick={() => act.edit.mutateAsync({ p, status: 'retired' }).catch(fail)}>کنار بگذار</Button>
              : <Button size="sm" variant="ghost" icon="refresh" onClick={() => act.edit.mutateAsync({ p, status: 'active' }).catch(fail)}>دوباره فعال</Button>}
          </>
        )}
      </div>
    </li>
  );
}

/** «مدیر کل دیجیتال» (contract §21.10): it only predicts. It never approves, rejects, messages or notifies, at any accuracy. */
export default function DigitalCeoPage() {
  const view = useDigitalCeo();
  const settings = useSettings18();
  const save = useSaveSettings18();
  const principles = usePrinciples();
  const act = usePrincipleAction();
  const toast = useToast();
  const [win, setWin] = useState<DceoWindow>('90d');
  const [correct, setCorrect] = useState<boolean | null>(null);
  const [adding, setAdding] = useState(false);
  const [text, setText] = useState('');
  const [confirmBefore, setConfirmBefore] = useState(false);
  const preds = usePredictions({ correct });
  const items = preds.data?.pages.flatMap((p) => p.items) ?? [];
  const s = view.data?.stats.find((x) => x.window === win);
  const cfg = view.data?.settings;
  const hidden = view.data?.hidden ?? 0;
  const setReveal = async (reveal: 'after' | 'before') => {
    if (!settings.data || !cfg) return;
    try { await save.mutateAsync({ version: settings.data.version, patch: { digital_ceo: { ...cfg, reveal } } }); toast({ tone: 'ok', text: reveal === 'before' ? 'از این به بعد پیش‌بینی را پیش از تصمیم میبینی؛ این‌ها در دقت تمیز شمرده نمیشوند.' : 'پیش‌بینی تا تصمیم تو پنهان میماند.' }); } catch (e) { toast({ tone: 'error', text: faError(e) }); }
  };
  const order = ['proposed', 'active', 'retired'];
  const ps = [...(principles.data ?? [])].sort((a, b) => order.indexOf(a.status) - order.indexOf(b.status) || a.ref.localeCompare(b.ref));
  return (
    <>
      <PageHeader eyebrow="فقط پیش‌بینی: هرگز تأیید، رد، پیام یا اعلان نمیسازد" title="مدیر کل دیجیتال"
        actions={cfg ? <div className="w-56"><Segmented label="زمان نمایش" value={cfg.reveal} onChange={(v) => (v === 'before' && hidden < 30 ? setConfirmBefore(true) : void setReveal(v))} options={[{ value: 'after', label: 'بعد از تصمیم' }, { value: 'before', label: 'پیش از تصمیم' }]} /></div> : null}>
        <p className="max-w-3xl text-[13px] leading-6 text-sec">
          برای هر کارتی که تو تصمیم میگیری، پیش از تصمیمت پیش‌بینی میکند و آن را مُهر میکند: روش پایه (نرخ تأیید گذشته‌ی تو بر اساس نوع، ریسک و پیشنهاددهنده، بی‌مدل) و برای کارت متوسط و پرریسک پیش‌بینی مدل
          {cfg ? <> (حداکثر <span className="fig">{cfg.max_model_per_day}</span> در روز{cfg.model_predictions ? '' : '؛ الان خاموش'})</> : null}. بعد از تصمیم تو سنجیده میشود. هر چه درباره‌ی تو ثبت میشود همین‌جا دیده میشود.
        </p>
      </PageHeader>
      {view.error ? <ErrorState error={view.error} onRetry={() => view.refetch()} /> : null}
      <div className="flex flex-wrap items-center gap-3">
        <div className="w-60"><Segmented label="بازه" value={win} onChange={setWin} options={WINDOWS} /></div>
        {cfg?.reveal === 'after' ? <span className="inline-flex items-center gap-1.5 text-[12px] text-muted"><Icon name="lock" size={14} />تا تصمیم تو پنهان؛ {hidden} پیش‌بینی پنهان تا امروز</span> : <span className="inline-flex items-center gap-1.5 text-[12px] text-warn"><Icon name="urgent" size={14} />پیش‌بینی پیش از تصمیم دیده میشود؛ در دقت تمیز نیست</span>}
      </div>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {!s ? Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-[104px] rounded-[14px]" />) : (
          <>
            <StatTile label="دقت" value={<span className="fig">{pct01(s.accuracy)}</span>} sub={<span>از {s.n} پیش‌بینی پنهان</span>} />
            <StatTile label="روش پایه" value={<span className="fig">{pct01(s.baseline_accuracy)}</span>} sub="بی‌مدل" />
            <StatTile label="مدل" value={<span className="fig">{pct01(s.model_accuracy)}</span>} sub="فقط کارت متوسط و پرریسک" />
            <StatTile label="Brier" value={<span className="fig">{s.brier ?? '—'}</span>} sub="کمتر بهتر؛ ۰ یعنی بی‌خطا" />
          </>
        )}
      </div>
      {hidden < 30 ? <p className="flex items-start gap-2 rounded-[12px] bg-warn-soft p-3 text-[12px] leading-5 text-ink"><Icon name="urgent" size={14} className="mt-0.5 text-warn" />دقت هنوز سنجیده نشده: کمتر از ۳۰ پیش‌بینی پنهان داریم و عددها با چند کارت زیاد جابه‌جا میشوند.</p> : null}
      <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
        <div className="flex min-w-0 flex-col gap-4">
          <Card className="flex flex-col gap-3 p-4">
            <SectionTitle title="کالیبراسیون" note="آیا «۷۰٪ مطمئنم» واقعاً ۷۰٪ درست است؟" />
            {s ? <Calibration s={s} /> : <Skeleton className="h-24" />}
          </Card>
          <Card className="flex flex-col gap-2 p-4">
            <SectionTitle title="به تفکیک نوع کارت" />
            {s && Object.keys(s.by_kind).length ? Object.entries(s.by_kind).sort((a, b) => b[1].n - a[1].n).map(([k, v]) => (
              <div key={k} className="flex items-center gap-2 border-b border-div py-1.5 text-[12px] last:border-0">
                <span className="text-gold-ink"><Icon name={DECISION_KIND[k]?.icon ?? 'decision'} size={15} /></span>
                <span className="min-w-0 flex-1 text-ink">{DECISION_KIND[k]?.fa ?? k}</span>
                <span className="text-muted">{v.n} کارت</span>
                <span className="fig w-12 text-left font-semibold text-ink">{pct01(v.accuracy)}</span>
              </div>
            )) : <p className="text-[12px] text-muted">هنوز داده‌ای نیست.</p>}
          </Card>
          <Card className="flex flex-col gap-3 p-4">
            <SectionTitle title="اصول" note="هر شنبه از تعامل‌های هفته و پیش‌بینی‌های غلط پیشنهاد میشود؛ تو میپذیری، ویرایش میکنی یا کنار میگذاری" action={<Button size="sm" variant="text" icon="add" onClick={() => setAdding(true)}>اصل تازه</Button>} />
            {principles.isLoading ? <Skeleton className="h-40" /> : !ps.length ? <Empty icon="learning" title="هنوز اصلی نیست" /> : <ul className="flex flex-col gap-2">{ps.map((p) => <PrincipleRow key={p.ref} p={p} />)}</ul>}
          </Card>
        </div>
        <Card className="flex flex-col gap-3 p-4">
          <SectionTitle title="پیش‌بینی‌ها" note="فقط کارت‌های تصمیم‌گرفته (یا همه، وقتی پیش از تصمیم نشان داده شود)" />
          <div className="flex flex-wrap gap-2">
            <FilterChip selected={correct == null} onClick={() => setCorrect(null)}>همه</FilterChip>
            <FilterChip selected={correct === true} onClick={() => setCorrect(true)}>درست</FilterChip>
            <FilterChip selected={correct === false} onClick={() => setCorrect(false)}>نادرست</FilterChip>
          </div>
          {preds.isLoading ? <Skeleton className="h-60" /> : !items.length ? <Empty icon="holding" title="پیش‌بینی‌ای نیست" /> : (
            <ul className="flex flex-col gap-2">
              {items.map((p) => {
                const v = VERDICT3[p.verdict] ?? VERDICT3.approve!;
                const a = p.actual ? VERDICT3[p.actual] : null;
                return (
                  <li key={p.decision} className="flex flex-col gap-1.5 rounded-[12px] bg-tile p-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <RefChip r={p.decision} />
                      {p.kind ? <span className="text-[11px] text-muted">{DECISION_KIND[p.kind]?.fa ?? p.kind}</span> : null}
                      <span className="flex-1" />
                      {p.correct == null ? <Pill tone="neutral">منتظر تصمیم</Pill> : <Pill tone={p.correct ? 'pos' : 'neg'} icon={p.correct ? 'seal' : 'reject'}>{p.correct ? 'درست' : 'نادرست'}</Pill>}
                    </div>
                    {p.title ? <span className="text-[13px] font-semibold text-ink">{p.title}</span> : null}
                    <div className="flex flex-wrap items-center gap-2 text-[12px] text-sec">
                      <span>پیش‌بینی</span><Pill tone={v.tone} dot>{v.fa}</Pill><Confidence v={p.confidence} tone="silver" />
                      {a ? <><span>تصمیم تو</span><Pill tone={a.tone} dot>{a.fa}</Pill></> : null}
                      <span className="text-muted">{p.method === 'model' ? 'مدل' : 'روش پایه'}</span>
                      {p.seen_before ? <span className="text-warn">پیش از تصمیم دیده شد</span> : null}
                    </div>
                    {p.rationale_fa ? <p className="text-[12px] leading-5 text-sec"><MdInline text={p.rationale_fa} /></p> : null}
                    <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted">
                      {p.principles.map((x) => <span key={x} className="fig">{x}</span>)}
                      <span>مُهر {jDateTime(p.made_at)}</span>
                      <span dir="ltr" className="fig" title={p.sealed_hash}>sha256 {p.sealed_hash.slice(0, 12)}…</span>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
          <p className="text-[11px] text-muted">هر پیش‌بینی پیش از تصمیم تو با sha256 همان لحظه مُهر میشود؛ پیش‌بینی‌ای که بعد از تصمیم نوشته شود دور ریخته میشود. <Link href="/cartable" className="text-gold-ink">کارتابل</Link></p>
        </Card>
      </div>
      <Dialog open={adding} onOpenChange={setAdding} title="اصل تازه" actions={<>
        <Button variant="primary" disabled={!text.trim()} loading={act.add.isPending} onClick={() => act.add.mutateAsync(text.trim()).then(() => { setAdding(false); setText(''); toast({ tone: 'ok', text: 'اصل فعال شد.' }); }, (e) => toast({ tone: 'error', text: faError(e) }))}>ثبت</Button>
        <Button variant="secondary" onClick={() => setAdding(false)}>انصراف</Button>
      </>}>
        <textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} maxLength={500} placeholder="مثلاً: انتشار در روز تعطیل را مُهر نمیکنم." aria-label="متن اصل" className="w-full rounded-[10px] border border-strong bg-tile p-3 text-[14px] text-ink outline-none focus:border-gold-ink" />
      </Dialog>
      <Dialog open={confirmBefore} onOpenChange={setConfirmBefore} title="پیش‌بینی پیش از تصمیم؟" actions={<>
        <Button variant="primary" loading={save.isPending} onClick={() => void setReveal('before').then(() => setConfirmBefore(false))}>با این حال نشان بده</Button>
        <Button variant="secondary" onClick={() => setConfirmBefore(false)}>بماند پنهان</Button>
      </>}>
        <p>دقت هنوز سنجیده نشده: فقط {hidden} پیش‌بینی پنهان داریم (دست‌کم ۳۰ لازم است). از این به بعد پیش‌بینی‌هایی که پیش از تصمیم ببینی «دیده‌شده» ثبت میشوند و در دقت تمیز نمیآیند.</p>
      </Dialog>
    </>
  );
}
