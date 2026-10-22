'use client';

import { useState } from 'react';
import { Icon } from '@/components/icon';
import { Button } from '@/components/ui/button';
import { Md } from '@/components/ui/md';
import { Sheet } from '@/components/ui/overlay';
import { Card, Empty, FilterChip, Pill, SectionTitle, Segmented, Skeleton, Switch } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { ActorAvatar, CoMark, RefChip, ScopeChips } from '@/components/v17/bits';
import { fileUrl } from '@/lib/api/v13';
import { faError, useCreative, useCreativeAction, useCreatives, useSettings18, type Creative, type CreativeIn, type CreativeState, type Placement } from '@/lib/api/v18';
import { useCompanies } from '@/lib/api/hooks';
import { ago, cx } from '@/lib/format';
import { ACTOR_FA } from '@/lib/labels';
import { CREATIVE, PLACEMENT, PlayerName } from './bits';

const ratio = (a: string) => { const [w, h] = a.split(':').map(Number) as [number, number]; return `${w} / ${h}`; };
const STATES: Array<CreativeState | null> = [null, 'review', 'generating', 'accepted', 'rejected', 'failed'];
const field = 'h-10 w-full rounded-[10px] border border-strong bg-card px-3 text-[14px] text-ink outline-none focus:border-gold-ink';

function Thumb({ c, className }: { c: Creative; className?: string }) {
  const file = c.composed ?? c.files[0] ?? null;
  return (
    <div className={cx('relative flex items-center justify-center overflow-hidden rounded-[12px] bg-page', className)} style={{ aspectRatio: ratio(c.aspect) }}>
      {file && c.kind === 'image' ? (
        // eslint-disable-next-line @next/next/no-img-element -- generated files from the hub's own store, already processed (§17.1)
        <img src={fileUrl(file.id)} alt={c.overlay?.title_fa ?? c.brief_md} className="size-full object-cover" />
      ) : (
        <span className="flex flex-col items-center gap-1.5 text-muted">
          <Icon name={c.kind === 'video' ? 'video' : 'image'} size={26} />
          <span className="text-[11px]">{CREATIVE[c.state]?.fa}</span>
        </span>
      )}
      <span className="fig absolute right-1.5 top-1.5 rounded-full bg-[rgba(11,13,20,.72)] px-1.5 py-px text-[10px] text-[#F2EEE4]">{c.aspect}</span>
    </div>
  );
}

function CreativeSheet({ refId, onClose }: { refId: string; onClose: () => void }) {
  const q = useCreative(refId);
  const act = useCreativeAction();
  const toast = useToast();
  const [note, setNote] = useState('');
  const c = q.data;
  const st = c ? CREATIVE[c.state] ?? CREATIVE.queued! : null;
  const decide = async (fn: 'accept' | 'reject') => {
    if (!c) return;
    try { await act[fn].mutateAsync({ ref: c.ref, note: note.trim() || undefined }); toast({ tone: fn === 'accept' ? 'ok' : 'info', text: fn === 'accept' ? 'پذیرفته شد. انتشار جایی، کار بیرونی است و کارت تصمیم میخواهد.' : 'رد شد؛ یادداشتت برای ایجنت مسئول رفت.' }); onClose(); } catch (e) { toast({ tone: 'error', text: faError(e) }); }
  };
  return (
    <Sheet open onOpenChange={(v) => !v && onClose()} width={620} title={c ? <span className="flex items-center gap-2">{PLACEMENT[c.placement]?.fa}<span className="fig text-[13px] text-muted">{c.ref}</span></span> : '…'}
      description="متن فارسی هرگز ساخته‌ی مدل نیست: هاب آن را با IRANYekanX و پالت برند، در حاشیه‌ی امن جای انتشار، روی نتیجه میچیند."
      footer={c?.state === 'review' ? (
        <div className="flex flex-col gap-2">
          <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="یادداشت برای ایجنت مسئول (اختیاری)" aria-label="یادداشت" className={field} />
          <div className="flex flex-wrap gap-2"><Button variant="primary" icon="seal" loading={act.accept.isPending} onClick={() => decide('accept')}>بپذیر</Button><Button variant="danger" icon="reject" loading={act.reject.isPending} onClick={() => decide('reject')}>رد</Button></div>
        </div>
      ) : undefined}>
      {!c || !st ? <Skeleton className="h-80" /> : (
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap items-center gap-2 text-[12px] text-sec">
            <Pill tone={st.tone} live={st.live} dot={!st.live}>{st.fa}</Pill>
            <CoMark code={c.company} height={12} />
            <PlayerName player={c.player} model={c.model} size={13} />
            <span className="fig text-muted">{c.path}</span>
            {c.duration_s ? <span>{c.duration_s} ثانیه</span> : null}
            <Pill tone="neutral" icon="info">ساخته‌ی هوش مصنوعی</Pill>
          </div>
          <div className={cx('grid gap-3', c.aspect === '9:16' || c.aspect === '4:5' ? 'grid-cols-2' : 'grid-cols-1')}>
            <div className="flex flex-col gap-1"><span className="text-[11px] text-muted">نسخه‌ی نهایی با متن هاب</span><Thumb c={c} /></div>
            {c.files[0] && c.composed ? (
              <div className="flex flex-col gap-1"><span className="text-[11px] text-muted">خروجی خام بازیکن (بی‌متن)</span>
                <div className="overflow-hidden rounded-[12px] bg-page" style={{ aspectRatio: ratio(c.aspect) }}>
                  {/* eslint-disable-next-line @next/next/no-img-element -- see Thumb */}
                  <img src={fileUrl(c.files[0].id)} alt="خروجی خام" className="size-full object-cover" />
                </div>
              </div>
            ) : null}
          </div>
          <section className="flex flex-col gap-1"><h3 className="text-[12px] font-semibold text-gold-ink">brief</h3><p className="text-[14px] leading-7 text-ink">{c.brief_md}</p></section>
          {c.overlay ? (
            <section className="flex flex-col gap-1"><h3 className="text-[12px] font-semibold text-gold-ink">متن روی تصویر</h3>
              <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-1 text-[13px]"><dt className="text-muted">عنوان</dt><dd className="text-ink">{c.overlay.title_fa}</dd>{c.overlay.body_fa ? <><dt className="text-muted">متن</dt><dd className="text-ink">{c.overlay.body_fa}</dd></> : null}{c.overlay.cta_fa ? <><dt className="text-muted">دعوت</dt><dd className="text-ink">{c.overlay.cta_fa}</dd></> : null}<dt className="text-muted">نشان</dt><dd className="text-ink">{c.overlay.mark ? 'با نشان شرکت' : 'بی‌نشان'}</dd></dl>
            </section>
          ) : null}
          <section className="flex flex-col gap-1"><h3 className="text-[12px] font-semibold text-gold-ink">prompt (نوشته‌ی ایجنت Claude مسئول)</h3><p dir="ltr" className="fig rounded-[10px] bg-tile p-3 text-left text-[12px] leading-5 text-sec">{c.prompt_md}</p></section>
          {c.review_md ? <section className="flex flex-col gap-1"><h3 className="text-[12px] font-semibold text-gold-ink">بازبینی</h3><Md text={c.review_md} className="flex flex-col gap-1 text-[13px] leading-6 text-ink" /></section> : null}
          <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted">
            <span className="flex items-center gap-1.5"><ActorAvatar a={c.requested_by} size={18} />{ACTOR_FA(c.requested_by)}</span><span>{ago(c.created_at)}</span>
            {c.work_ref ? <RefChip r={c.work_ref} /> : null}
            {c.source ? <span>منبع: <span className="fig">{c.source.player} · {c.source.model}</span></span> : null}
          </div>
          <p className="text-[11px] leading-5 text-muted">پذیرفتن یعنی آماده‌ی استفاده؛ انتشار در کانال یا استوری کار بیرونی است و همیشه کارت تصمیم (A3) میخواهد.</p>
        </div>
      )}
    </Sheet>
  );
}

function NewCreative({ onClose, onMade }: { onClose: () => void; onMade: (ref: string) => void }) {
  const act = useCreativeAction();
  const toast = useToast();
  const settings = useSettings18();
  const { data: companies } = useCompanies();
  const [key] = useState(() => crypto.randomUUID());
  const [company, setCompany] = useState<string | null>(null);
  const [kind, setKind] = useState<'image' | 'video'>('image');
  const [placement, setPlacement] = useState<Placement>('telegram_post');
  const [brief, setBrief] = useState('');
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [cta, setCta] = useState('');
  const [mark, setMark] = useState(true);
  const [dur, setDur] = useState(8);
  const [player, setPlayer] = useState<'gpt' | 'gemini' | null>(null);
  const def = settings.data?.substitutes?.creative_default_image ?? 'gpt';
  const who = kind === 'video' ? 'gemini' : player ?? def;
  const ok = !!company && brief.trim().length >= 8 && (kind === 'image' || (dur >= 1 && dur <= 10));
  const submit = async () => {
    if (!company) return;
    const b: CreativeIn = { company, kind, brief_md: brief.trim(), placement, ...(title.trim() ? { overlay: { title_fa: title.trim(), body_fa: body.trim() || null, cta_fa: cta.trim() || null, mark } } : {}), ...(kind === 'video' ? { duration_s: dur } : player ? { player } : {}) };
    try { const c = await act.create.mutateAsync({ body: b, key }); toast({ tone: 'ok', text: <>درخواست <span className="fig">{c.ref}</span> رفت؛ ایجنت مسئول prompt را مینویسد.</> }); onMade(c.ref); } catch (e) { toast({ tone: 'error', text: faError(e) }); }
  };
  const operating = (companies ?? []).filter((c) => c.kind !== 'holding');
  return (
    <Sheet open onOpenChange={(v) => !v && onClose()} width={560} title="عکس یا ویدیوی تبلیغ" description="ایجنت Claude مسئول همان شرکت prompt را از روی brief، جای انتشار و برند مینویسد و «بی‌متن» میخواهد؛ بازیکن ذخیره فقط میسازد."
      footer={<div className="flex gap-2"><Button variant="primary" icon="send" disabled={!ok} loading={act.create.isPending} onClick={submit}>بفرست</Button><Button variant="ghost" onClick={onClose}>انصراف</Button></div>}>
      <div className="flex flex-col gap-4 text-[13px]">
        <div className="flex flex-wrap gap-1.5">{operating.map((c) => <FilterChip key={c.code} selected={company === c.code} onClick={() => setCompany(c.code)}><span className="flex items-center gap-1.5"><CoMark code={c.code} height={11} />{c.name_fa}</span></FilterChip>)}</div>
        <Segmented label="نوع" value={kind} onChange={setKind} options={[{ value: 'image', label: 'عکس', icon: 'image' }, { value: 'video', label: 'ویدیو (Gemini، ≤ ۱۰ ثانیه)', icon: 'video' }]} />
        <div className="flex flex-col gap-1.5">
          <span className="font-semibold text-sec">جای انتشار</span>
          <div className="flex flex-wrap gap-1.5">{(Object.keys(PLACEMENT) as Placement[]).map((p) => <FilterChip key={p} selected={placement === p} onClick={() => setPlacement(p)}>{PLACEMENT[p]!.fa} <span className="fig text-[11px] opacity-70">{PLACEMENT[p]!.aspect}</span></FilterChip>)}</div>
          <span className="text-[11px] text-muted">نسبت و حاشیه‌ی امن را جای انتشار تعیین میکند.</span>
        </div>
        <label className="flex flex-col gap-1.5 font-semibold text-sec">brief<textarea value={brief} onChange={(e) => setBrief(e.target.value)} rows={3} maxLength={1000} placeholder="مثلاً: تصویر تبلیغ کانال تلگرام FX برای دوره‌ی آموزش رایگان تحلیل طلا" className="w-full rounded-[10px] border border-strong bg-card p-3 text-[14px] leading-6 text-ink outline-none focus:border-gold-ink" /><span className="text-[11px] font-normal text-muted">هیچ داده‌ی مشتری؛ ورودی ماسک میشود.</span></label>
        <fieldset className="flex flex-col gap-2 rounded-[12px] bg-tile p-3">
          <legend className="px-1 text-[12px] font-semibold text-sec">متن فارسی روی تصویر (هاب میگذارد)</legend>
          <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={60} placeholder="عنوان" aria-label="عنوان" className={field} />
          <input value={body} onChange={(e) => setBody(e.target.value)} maxLength={120} placeholder="متن کوتاه (اختیاری)" aria-label="متن" className={field} />
          <input value={cta} onChange={(e) => setCta(e.target.value)} maxLength={30} placeholder="دعوت به اقدام (اختیاری)" aria-label="دعوت به اقدام" className={field} />
          <label className="flex items-center gap-2 text-[12px] text-sec"><Switch label="نشان شرکت" checked={mark} onChange={setMark} />نشان شرکت</label>
        </fieldset>
        {kind === 'video' ? (
          <label className="flex items-center gap-2 font-semibold text-sec">مدت<input value={dur} onChange={(e) => setDur(Math.min(10, Number(e.target.value.replace(/\D/g, '') || 0)))} inputMode="numeric" aria-label="مدت به ثانیه" className="fig h-9 w-16 rounded-[8px] border border-strong bg-card px-2 text-center text-ink" />ثانیه</label>
        ) : (
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-[12px] text-sec">بازیکن:</span>
            <FilterChip selected={!player} onClick={() => setPlayer(null)}>پیش‌فرض ({def === 'gpt' ? 'ChatGPT' : 'Gemini'})</FilterChip>
            <FilterChip selected={player === 'gpt'} onClick={() => setPlayer('gpt')}><PlayerName player="gpt" size={12} /></FilterChip>
            <FilterChip selected={player === 'gemini'} onClick={() => setPlayer('gemini')}><PlayerName player="gemini" size={12} /></FilterChip>
          </div>
        )}
        <p className="flex items-center gap-1.5 text-[11px] text-muted"><Icon name="globe" size={13} />از مرورگر لاگین‌شده‌ی هاب، با اشتراک نامحدود تو: <PlayerName player={who} size={11} /></p>
      </div>
    </Sheet>
  );
}

/** The companies' ad creatives (§21.13): asked by an agent or the owner, rendered by a substitute, composed and reviewed on the hub. */
export function CreativesCard({ initial }: { initial?: string | null }) {
  const [company, setCompany] = useState<string | null>(null);
  const [state, setState] = useState<CreativeState | null>(null);
  const [open, setOpen] = useState<string | null>(initial ?? null);
  const [making, setMaking] = useState(false);
  const q = useCreatives({ company, state });
  const items = q.data?.pages.flatMap((p) => p.items) ?? [];
  return (
    <Card className="flex flex-col gap-3 p-4">
      <SectionTitle title="عکس و ویدیوی تبلیغ" note="هر کدام ساخته‌ی هوش مصنوعی است؛ انتشارش همیشه کارت تصمیم میخواهد" action={<Button size="sm" variant="primary" icon="add" onClick={() => setMaking(true)}>درخواست تازه</Button>} />
      <ScopeChips value={company} onChange={setCompany} holding={false} allLabel="همه‌ی شرکت‌ها" />
      <div className="flex flex-wrap gap-1.5">{STATES.map((s) => <FilterChip key={s ?? 'all'} selected={state === s} onClick={() => setState(s)}>{s ? CREATIVE[s]!.fa : 'همه'}</FilterChip>)}</div>
      {q.isLoading ? <Skeleton className="h-60" /> : !items.length ? <Empty icon="image" title="درخواستی نیست" /> : (
        <ul className="grid items-start gap-3 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
          {items.map((c) => {
            const st = CREATIVE[c.state] ?? CREATIVE.queued!;
            return (
              <li key={c.ref}>
                <button type="button" onClick={() => setOpen(c.ref)} className={cx('flex w-full flex-col gap-2 rounded-[14px] p-2.5 text-start hover:bg-hover', c.state === 'review' ? 'bg-gold-soft' : 'bg-tile')}>
                  <Thumb c={c} className={c.aspect === '9:16' || c.aspect === '4:5' ? 'mx-auto h-64 w-auto' : 'w-full'} />
                  <span className="flex items-center gap-2"><CoMark code={c.company} height={11} /><span className="min-w-0 flex-1 truncate text-[12px] font-semibold text-ink">{c.overlay?.title_fa ?? c.brief_md}</span></span>
                  <span className="flex flex-wrap items-center gap-1.5 text-[11px] text-muted">
                    <Pill tone={st.tone} live={st.live} dot={!st.live}>{st.fa}</Pill>
                    <span>{PLACEMENT[c.placement]?.fa}</span><PlayerName player={c.player} size={11} /><span className="fig">{c.ref}</span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
      {open ? <CreativeSheet refId={open} onClose={() => setOpen(null)} /> : null}
      {making ? <NewCreative onClose={() => setMaking(false)} onMade={(r) => { setMaking(false); setOpen(r); }} /> : null}
    </Card>
  );
}
