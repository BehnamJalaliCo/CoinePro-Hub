'use client';

import Link from 'next/link';
import { useState } from 'react';
import { Icon } from '@/components/icon';
import { Button } from '@/components/ui/button';
import { MdInline } from '@/components/ui/md';
import { Sheet } from '@/components/ui/overlay';
import { Empty, Pill, Skeleton } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { CoMark, RefChip } from '@/components/v17/bits';
import { faError, useAdvisorTriggers, useCurrentReview, useMemos, useReviewAction, useWeeklyReviews, type AgendaItem, type WeeklyReview } from '@/lib/api/v18';
import { ago, cx, jDate, jTime } from '@/lib/format';
import { AGENDA, ITEM_STATUS, MEMO_STATE, PlayerName, REC, REVIEW_STATE, TRIGGER, TRIGGER_STATE } from './bits';

const weekFa = (w: string) => jDate(`${w}T08:00:00Z`);

// ------------------------------------------------------------ the weekly review (§21.3) --
/** A slim line above the advisor's thread while this week's review is open. */
export function ReviewBanner({ onOpen }: { onOpen: () => void }) {
  const q = useCurrentReview();
  const r = q.data;
  if (!r || (r.state !== 'ready' && r.state !== 'in_progress')) return null;
  const open = r.agenda.filter((i) => i.status === 'open').length;
  return (
    <button type="button" onClick={onOpen} className="mt-3 flex w-full items-center gap-3 rounded-[14px] bg-gold-soft px-3 py-2.5 text-start hover:bg-[var(--hq-gold-hover-soft)]">
      <span className="flex size-9 flex-none items-center justify-center rounded-full bg-card text-gold-ink"><Icon name="planner" size={18} /></span>
      <span className="flex min-w-0 flex-1 flex-col">
        <span className="text-[13px] font-semibold text-ink">مرور هفتگی <span className="fig">{r.ref}</span>، هفته‌ی {weekFa(r.week)}</span>
        <span className="text-[12px] text-sec">{r.agenda.length} مورد، {open} باز؛ حدود ۱۵ دقیقه</span>
      </span>
      <Pill tone={REVIEW_STATE[r.state]!.tone} live={REVIEW_STATE[r.state]!.live} dot={!REVIEW_STATE[r.state]!.live}>{r.state === 'ready' ? 'شروع' : 'ادامه'}</Pill>
    </button>
  );
}

function AgendaRow({ r, it, live }: { r: WeeklyReview; it: AgendaItem; live: boolean }) {
  const act = useReviewAction();
  const toast = useToast();
  const [note, setNote] = useState(it.owner_note ?? '');
  const [editing, setEditing] = useState(false);
  const k = AGENDA[it.kind] ?? { fa: it.kind, icon: 'info' as const };
  const st = ITEM_STATUS[it.status] ?? ITEM_STATUS.open!;
  const set = async (status: AgendaItem['status']) => {
    try { await act.item.mutateAsync({ r, n: it.n, status, owner_note: editing ? note.trim() : undefined }); setEditing(false); } catch (e) { toast({ tone: 'error', text: faError(e) }); }
  };
  return (
    <li className={cx('flex flex-col gap-2 rounded-[12px] p-3', it.status === 'open' ? 'bg-tile' : 'bg-card')}>
      <div className="flex items-start gap-2">
        <span className="fig mt-0.5 w-5 flex-none text-center text-[12px] text-muted">{it.n}</span>
        <span className="mt-0.5 text-gold-ink" title={k.fa}><Icon name={k.icon} size={16} /></span>
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <span className="text-[13px] font-semibold text-ink"><MdInline text={it.title_fa} /></span>
          <span className="text-[12px] leading-5 text-sec"><MdInline text={it.why_fa} /></span>
          <span className="flex flex-wrap items-center gap-1.5 pt-0.5">{it.company ? <CoMark code={it.company} height={11} /> : null}<RefChip r={it.ref} tone="neutral" /></span>
        </div>
        <Pill tone={st.tone}>{st.fa}</Pill>
      </div>
      {it.owner_note && !editing ? <p className="ps-7 text-[12px] text-muted">یادداشت تو: {it.owner_note}</p> : null}
      {live ? (
        <div className="flex flex-col gap-2 ps-7">
          {editing ? <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} maxLength={500} placeholder="یادداشت تو برای صورت‌جلسه" aria-label={`یادداشت مورد ${it.n}`} className="w-full rounded-[10px] border border-strong bg-card p-2 text-[13px] text-ink outline-none focus:border-gold-ink" /> : null}
          <div className="flex flex-wrap gap-1.5">
            {it.status !== 'done' ? <Button size="sm" variant="secondary" icon="seal" loading={act.item.isPending} onClick={() => set('done')}>انجام شد</Button> : null}
            {it.status !== 'deferred' ? <Button size="sm" variant="ghost" icon="time" onClick={() => set('deferred')}>هفته‌ی بعد</Button> : null}
            {it.status !== 'open' ? <Button size="sm" variant="ghost" icon="refresh" onClick={() => set('open')}>باز کن</Button> : null}
            <Button size="sm" variant="ghost" icon="edit" onClick={() => setEditing((v) => !v)}>{editing ? 'بی‌یادداشت' : 'یادداشت'}</Button>
          </div>
        </div>
      ) : null}
    </li>
  );
}

/** «مرور هفتگی با مشاور»: an agenda built by code, gone through item by item; finishing writes the minutes as a deliverable. */
export function ReviewSheet({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const cur = useCurrentReview();
  const all = useWeeklyReviews();
  const act = useReviewAction();
  const toast = useToast();
  const r = cur.data;
  const live = r?.state === 'in_progress';
  const past = (all.data ?? []).filter((x) => x.ref !== r?.ref);
  const run = async (fn: 'start' | 'finish') => {
    if (!r) return;
    try { const out = await act[fn].mutateAsync(r.ref); toast({ tone: 'ok', text: fn === 'start' ? 'مرور شروع شد؛ مورد به مورد جلو برو.' : <>مرور تمام شد؛ صورت‌جلسه <span className="fig">{out.minutes_ref}</span> ثبت شد.</> }); } catch (e) { toast({ tone: 'error', text: faError(e) }); }
  };
  return (
    <Sheet open={open} onOpenChange={onOpenChange} width={600} title={r ? <span className="flex items-center gap-2">مرور هفتگی<span className="fig text-[13px] text-muted">{r.ref}</span></span> : 'مرور هفتگی'}
      description="دستور را کد ۳۰ دقیقه پیش از وقتش میسازد (حداکثر ۱۲ مورد)؛ کارهایی که در جلسه میکنی رکورد عادی خودشان را میسازند."
      footer={r && (r.state === 'ready' || live) ? <div className="flex flex-wrap gap-2">{r.state === 'ready' ? <Button variant="primary" icon="resume" loading={act.start.isPending} onClick={() => run('start')}>شروع مرور</Button> : <Button variant="primary" icon="seal" loading={act.finish.isPending} onClick={() => run('finish')}>پایان و صورت‌جلسه</Button>}</div> : undefined}>
      {cur.isLoading ? <Skeleton className="h-60" /> : !r ? <Empty icon="planner" title="مرور این هفته هنوز ساخته نشده" body="شنبه ساعت ۱۰ (تنظیمات)؛ دستورش ۳۰ دقیقه پیش‌تر ساخته میشود." /> : (
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap items-center gap-2 text-[12px] text-sec">
            <Pill tone={REVIEW_STATE[r.state]!.tone} live={REVIEW_STATE[r.state]!.live} dot={!REVIEW_STATE[r.state]!.live}>{REVIEW_STATE[r.state]!.fa}</Pill>
            <span>هفته‌ی {weekFa(r.week)}</span>
            {r.started_at ? <span>شروع {jTime(r.started_at)}</span> : null}
            {r.brief_message_ref ? <Link href="/advisor" className="fig text-gold-ink">{r.brief_message_ref}</Link> : null}
            {r.minutes_ref ? <RefChip r={r.minutes_ref} note="صورت‌جلسه" /> : null}
          </div>
          {!live && r.state === 'ready' ? <p className="text-[12px] leading-5 text-muted">برای علامت زدن موردها، مرور را شروع کن؛ مدت جلسه در صورت‌جلسه میماند.</p> : null}
          <ol className="flex flex-col gap-2">{r.agenda.map((it) => <AgendaRow key={it.n} r={r} it={it} live={live} />)}</ol>
          {past.length ? (
            <div className="flex flex-col gap-1.5">
              <span className="text-[12px] font-semibold text-sec">مرورهای قبل</span>
              {past.map((x) => (
                <div key={x.ref} className="flex flex-wrap items-center gap-2 rounded-[10px] bg-tile px-3 py-2 text-[12px]">
                  <span className="fig text-muted">{x.ref}</span><span className="text-ink">هفته‌ی {weekFa(x.week)}</span>
                  <span className="flex-1" />
                  {x.duration_s ? <span className="text-muted">{Math.round(x.duration_s / 60)} دقیقه</span> : null}
                  {x.minutes_ref ? <RefChip r={x.minutes_ref} /> : null}
                  <Pill tone={REVIEW_STATE[x.state]!.tone}>{REVIEW_STATE[x.state]!.fa}</Pill>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      )}
    </Sheet>
  );
}

// ------------------------------------------------------------------ memos (§21.1) --
export function MemosSheet({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const q = useMemos();
  const items = q.data?.pages.flatMap((p) => p.items) ?? [];
  return (
    <Sheet open={open} onOpenChange={onOpenChange} width={560} title="یادداشت‌های تصمیم" description="خودکار برای کارت‌های پرریسک، انتشار، تأسیس و طرح سرور (حداکثر ۳ در روز)؛ بقیه به درخواست تو از روی کارت.">
      {q.isLoading ? <Skeleton className="h-48" /> : !items.length ? <Empty icon="advisor" title="هنوز یادداشتی نیست" /> : (
        <ul className="flex flex-col gap-2">
          {items.map((m) => {
            const st = MEMO_STATE[m.state] ?? MEMO_STATE.ready!;
            const rec = REC[m.recommendation] ?? REC.ask!;
            return (
              <li key={m.ref}>
                <Link href={`/cartable?ref=${m.decision}`} onClick={() => onOpenChange(false)} className="flex flex-col gap-1.5 rounded-[12px] bg-tile p-3 hover:bg-hover">
                  <span className="flex flex-wrap items-center gap-2 text-[11px] text-muted">
                    <span className="fig">{m.ref}</span><span className="fig text-gold-ink">{m.decision}</span><span>{m.mode === 'devil' ? 'مخالف‌خوان' : 'استاندارد'}</span><span>{m.trigger === 'auto' ? 'خودکار' : 'درخواست تو'}</span>
                    <span className="flex-1" /><span>{ago(m.created_at)}</span>
                  </span>
                  <span className="text-[13px] leading-6 text-ink">{m.summary_fa ? <MdInline text={m.summary_fa} /> : 'در حال نوشتن…'}</span>
                  <span className="flex flex-wrap items-center gap-1.5">
                    {m.state !== 'ready' ? <Pill tone={st.tone} live={st.live} dot={!st.live}>{st.fa}</Pill> : <Pill tone={rec.tone} dot>{rec.fa}</Pill>}
                    {m.second_opinion ? <span className={cx('inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px]', m.second_opinion.agrees ? 'bg-pos-soft text-pos' : 'bg-warn-soft text-warn')}><PlayerName player={m.second_opinion.player} size={11} />{m.second_opinion.agrees ? 'هم‌نظر' : 'اختلاف'}</span> : null}
                    {m.third_opinion ? <span className={cx('inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px]', m.third_opinion.agrees ? 'bg-pos-soft text-pos' : 'bg-warn-soft text-warn')}><PlayerName player={m.third_opinion.player} size={11} />{m.third_opinion.agrees ? 'هم‌نظر' : 'اختلاف'}</span> : null}
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </Sheet>
  );
}

// ---------------------------------------------------------- proactive notes (§21.1) --
const factLine = (f: Record<string, unknown>) => Object.entries(f).map(([k, v]) => `${k}: ${typeof v === 'number' && v > 9999 ? v.toLocaleString('en-US') : String(v)}`).join(' · ');
export function TriggersSheet({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const q = useAdvisorTriggers();
  const xs = q.data ?? [];
  return (
    <Sheet open={open} onOpenChange={onOpenChange} width={520} title="گزارش‌های فعال مشاور" description="محرک‌ها کد هستند، بی‌مدل؛ هر کلید روزی یک بار. حداکثر ۳ پیام در روز، هرگز فوری؛ بقیه «بالای سقف» ثبت میشوند.">
      {q.isLoading ? <Skeleton className="h-40" /> : !xs.length ? <Empty icon="bell" title="امروز محرکی روشن نشده" /> : (
        <ul className="flex flex-col gap-2">
          {xs.map((t) => {
            const k = TRIGGER[t.kind] ?? { fa: t.kind, icon: 'bell' as const };
            const st = TRIGGER_STATE[t.state] ?? TRIGGER_STATE.sent!;
            return (
              <li key={t.id} className="flex flex-col gap-1.5 rounded-[12px] bg-tile p-3">
                <div className="flex items-center gap-2">
                  <span className="text-gold-ink"><Icon name={k.icon} size={16} /></span>
                  <span className="text-[13px] font-semibold text-ink">{k.fa}</span>
                  {t.company ? <CoMark code={t.company} height={11} /> : null}
                  <span className="flex-1" />
                  <Pill tone={st.tone}>{st.fa}</Pill>
                </div>
                <span dir="ltr" className="fig text-left text-[11px] text-muted">{factLine(t.facts)}</span>
                <span className="flex items-center gap-2 text-[11px] text-muted"><span>{ago(t.fired_at)}</span>{t.message_ref ? <span className="fig text-gold-ink">{t.message_ref}</span> : null}</span>
              </li>
            );
          })}
        </ul>
      )}
    </Sheet>
  );
}
