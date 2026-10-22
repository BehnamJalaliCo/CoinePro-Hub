'use client';

import Link from 'next/link';
import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Icon } from '@/components/icon';
import { SealButton } from '@/components/cartable/seal-button';
import { Button } from '@/components/ui/button';
import { Md, MdInline } from '@/components/ui/md';
import { Dialog, Sheet } from '@/components/ui/overlay';
import { Card, Empty, ErrorState, FilterChip, Pill, Skeleton } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { AudioPlayer } from '@/components/v18/bits';
import { ActorAvatar, CoMark, RefChip } from '@/components/v17/bits';
import { useCompanies, useDecide } from '@/lib/api/hooks';
import { fileUrl } from '@/lib/api/v13';
import { faError, useMediaItem, useMediaItemAction, useSeriesList, type MediaItem, type MediaKind } from '@/lib/api/v19';
import { stepUp } from '@/lib/auth';
import { companyOf } from '@/lib/company';
import { ACTOR_FA } from '@/lib/labels';
import { ago, cx, jDateTime, tokens, usd } from '@/lib/format';
import { Block, CheckGrid, FileChip, ITEM_STATE, KIND_FA, PublishRows, QC_VERDICT, RenderPreview, STAGES, STOPPED, StageTrack, aspectOfItem } from './bits';

const SOURCE_FA: Record<string, string> = { market_data: 'داده‌ی بازار', deliverable: 'خروجی', knowledge: 'دانشنامه', url: 'صفحه' };

// ------------------------------------------------------------------ the board --
function ItemCard({ x, onOpen }: { x: MediaItem; onOpen: (ref: string) => void }) {
  const st = ITEM_STATE[x.state] ?? ITEM_STATE.scripting!;
  const k = KIND_FA[x.kind] ?? KIND_FA.post!;
  const mine = x.state === 'waiting_owner';
  return (
    <button type="button" onClick={() => onOpen(x.ref)} aria-label={`${x.title_fa} (${x.ref})`}
      className={cx('flex w-full items-center gap-3 rounded-[14px] p-2.5 text-start transition-colors hover:bg-hover', mine ? 'tahrir bg-gold-soft' : x.state === 'held' || x.state === 'failed' ? 'bg-neg-soft' : 'bg-tile')}>
      <RenderPreview file={x.render} aspect={aspectOfItem(x)} label={x.title_fa} compact className={cx('flex-none', x.kind === 'design' ? 'w-20' : 'w-12')} />
      <span className="flex min-w-0 flex-1 flex-col gap-1">
        <span className="flex items-center gap-1.5"><CoMark code={x.company} height={10} /><span className="truncate text-[13px] font-semibold text-ink">{x.title_fa}</span></span>
        <span className="flex flex-wrap items-center gap-1.5 text-[11px] text-muted">
          <span className="inline-flex items-center gap-1"><Icon name={k.icon} size={12} />{k.fa}</span>
          <span className="fig">{x.ref}</span>{x.series ? <span className="fig">{x.series}</span> : <span>یک‌باره</span>}
        </span>
        <span className="flex flex-wrap items-center gap-1.5"><Pill tone={st.tone} live={st.live} dot={!st.live} className="h-5 text-[11px]">{st.fa}</Pill><span className="text-[11px] text-muted">{ago(x.updated_at)}</span></span>
      </span>
    </button>
  );
}

/** The pipeline as lanes, one per step (§22.2): an item moves down as code moves it on. Stopped items have a lane of their own. */
export function PipelineBoard({ items, loading, onOpen }: { items: MediaItem[]; loading?: boolean; onOpen: (ref: string) => void }) {
  if (loading) return <Skeleton className="h-[520px] rounded-[16px]" />;
  if (!items.length) return <Card className="p-2"><Empty icon="video" title="آیتمی نیست" body="برنامه‌ی مُهرشده هر بار طبق زمان‌بندی‌اش یک آیتم میسازد؛ آیتم یک‌باره را خودت میسازی." /></Card>;
  const stopped = items.filter((x) => STOPPED.includes(x.state));
  return (
    <Card className="flex flex-col p-2">
      {STAGES.map((s, i) => {
        const xs = items.filter((x) => s.states.includes(x.state));
        return (
          <section key={s.key} aria-label={s.fa} className={cx('grid gap-2 p-2 md:grid-cols-[168px_minmax(0,1fr)] md:gap-4', i > 0 && 'border-t border-div')}>
            <header className="flex items-center gap-2.5 md:items-start md:pt-2">
              <span className={cx('flex size-8 flex-none items-center justify-center rounded-full', xs.length ? 'bg-gold-soft text-gold-ink' : 'bg-tile text-muted')}><Icon name={s.icon} size={16} /></span>
              <span className="flex min-w-0 flex-col"><span className="text-[13px] font-semibold text-ink">{s.fa} <span className="text-muted">{xs.length || ''}</span></span><span className="text-[11px] text-muted">{s.who}</span></span>
            </header>
            {xs.length ? (
              <div className="grid gap-2 sm:grid-cols-2 2xl:grid-cols-3">{xs.map((x) => <ItemCard key={x.ref} x={x} onOpen={onOpen} />)}</div>
            ) : <p className="hidden self-center text-[12px] text-muted md:block">الان چیزی در این مرحله نیست.</p>}
          </section>
        );
      })}
      {stopped.length ? (
        <section aria-label="متوقف" className="grid gap-2 border-t border-div p-2 md:grid-cols-[168px_minmax(0,1fr)] md:gap-4">
          <header className="flex items-center gap-2.5 md:items-start md:pt-2">
            <span className="flex size-8 flex-none items-center justify-center rounded-full bg-neg-soft text-neg"><Icon name="urgent" size={16} /></span>
            <span className="flex flex-col"><span className="text-[13px] font-semibold text-ink">متوقف <span className="text-muted">{stopped.length}</span></span><span className="text-[11px] text-muted">نگه‌داشته، شکست یا رد</span></span>
          </header>
          <div className="grid gap-2 sm:grid-cols-2 2xl:grid-cols-3">{stopped.map((x) => <ItemCard key={x.ref} x={x} onOpen={onOpen} />)}</div>
        </section>
      ) : null}
    </Card>
  );
}

/** One count per step: where the work is piling up. */
export function StageCounts({ items }: { items: MediaItem[] }) {
  return (
    <ol className="grid grid-cols-4 gap-2 md:grid-cols-8" aria-label="شمار هر مرحله">
      {STAGES.map((s) => {
        const n = items.filter((x) => s.states.includes(x.state)).length;
        const mine = s.key === 'ready' && items.some((x) => x.state === 'waiting_owner');
        return (
          <li key={s.key} className={cx('flex flex-col gap-0.5 rounded-[12px] p-2.5', mine ? 'tahrir bg-gold-soft' : 'bg-card')}>
            <span className="flex items-center gap-1 text-[11px] text-muted"><Icon name={s.icon} size={12} />{s.fa}</span>
            <span className={cx('text-[20px] font-semibold leading-7', n ? 'text-ink' : 'text-muted')}>{n}</span>
          </li>
        );
      })}
    </ol>
  );
}

// ------------------------------------------------------------------ an item --
export function ItemSheet({ refId, onClose }: { refId: string; onClose: () => void }) {
  const q = useMediaItem(refId);
  const act = useMediaItemAction();
  const decide = useDecide();
  const qc = useQueryClient();
  const toast = useToast();
  const { data: companies } = useCompanies();
  const series = useSeriesList();
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const x = q.data;
  const co = companyOf(companies, x?.company);
  const st = x ? ITEM_STATE[x.state] ?? ITEM_STATE.scripting! : null;
  const sr = series.data?.find((s) => s.ref === x?.series);
  const manual = x?.publish.some((r) => r.placement === 'telegram_story' && !r.external_id) ?? false;

  // A waiting item goes out through its card (A3): the seal approves `media_publish`, bound to the card (§22.2, §5.1).
  const seal = async () => {
    if (!x?.decision_ref) return;
    setBusy(true);
    try {
      const token = await stepUp('decision.approve', x.decision_ref);
      await decide.mutateAsync({ ref: x.decision_ref, verdict: 'approve', stepUpToken: token });
      await qc.invalidateQueries({ queryKey: ['media'] });
      toast({ tone: 'ok', text: manual ? 'ثبت شد که استوری را خودت گذاشتی؛ بقیه از API رسمی رفت.' : 'مُهر خورد و از API رسمی منتشر شد.' });
    } catch (e) { toast({ tone: 'error', text: faError(e) }); } finally { setBusy(false); }
  };
  const unpublish = async () => {
    if (!x) return;
    try { await act.unpublish.mutateAsync(x.ref); setConfirm(false); toast({ tone: 'info', text: 'پایین آمد؛ جایی که API اجازه نداد را از خود اپ پایین بیاور.' }); } catch (e) { toast({ tone: 'error', text: faError(e) }); }
  };

  return (
    <Sheet open onOpenChange={(v) => !v && onClose()} width={760}
      title={x ? <span className="flex flex-wrap items-center gap-2">{x.title_fa}<span className="fig text-[13px] text-muted">{x.ref}</span></span> : '…'}
      description={x ? <span className="flex flex-wrap items-center gap-1.5"><CoMark code={x.company} height={11} />{co.nameFa}، {KIND_FA[x.kind]?.fa}{x.series ? <>، برنامه‌ی <span className="fig">{x.series}</span>{sr ? ` «${sr.title_fa}»` : ''}</> : '، یک‌باره'}</span> : undefined}
      footer={x && (x.state === 'waiting_owner' || x.state === 'published' || x.decision_ref) ? (
        <div className="flex flex-wrap items-center gap-3">
          {x.state === 'waiting_owner' && x.decision_ref ? (
            <>
              <SealButton code={x.company} nameFa={co.nameFa} nameEn={co.nameEn} holding={co.holding} busy={busy} onSealed={seal} size={64} />
              <span className="flex min-w-[180px] flex-1 flex-col gap-1 text-[12px] leading-5 text-sec">
                <span className="font-semibold text-ink">{manual ? 'فایل را بردار، خودت در کانال بگذار، بعد مُهر کن' : 'مُهر انتشار این آیتم'}</span>
                <span>کارت <RefChip r={x.decision_ref} />؛ با اثر انگشت یا چهره. {manual ? 'استوری کانال تلگرام در Bot API نیست.' : ''}</span>
              </span>
              {x.render ? <a href={fileUrl(x.render.id)} download={x.render.name} className="inline-flex h-10 items-center gap-2 rounded-[10px] border border-strong px-4 text-[13px] font-semibold text-ink hover:bg-hover"><Icon name="download" size={18} />فایل</a> : null}
            </>
          ) : x.state === 'published' ? (
            <>
              <span className="min-w-0 flex-1 text-[12px] text-muted">پایین آوردن از همان API رسمی است، هر جا پلتفرم اجازه بدهد.</span>
              <Button variant="danger" icon="reject" onClick={() => setConfirm(true)}>پایین بیاور</Button>
            </>
          ) : x.decision_ref ? <span className="text-[12px] text-muted">کارت این آیتم: <RefChip r={x.decision_ref} /></span> : null}
        </div>
      ) : undefined}>
      {q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : !x || !st ? <Skeleton className="h-96" /> : (
        <div className="flex flex-col gap-5">
          <div className="flex flex-col gap-2">
            <StageTrack state={x.state} design={x.kind === 'design'} />
            <div className="flex flex-wrap items-center gap-2 text-[12px] text-muted">
              <Pill tone={st.tone} live={st.live} dot={!st.live}>{st.fa}</Pill>
              {x.topic_fa ? <span>موضوع: <span className="text-ink">{x.topic_fa}</span></span> : null}
              <Pill tone="neutral" icon="info">ساخته‌ی هوش مصنوعی</Pill>
              <span>به‌روز {ago(x.updated_at)}</span>
            </div>
            {x.state_note_fa ? <div className={cx('flex items-start gap-2 rounded-[12px] p-3 text-[13px] leading-6 text-ink', x.state === 'held' || x.state === 'failed' ? 'bg-neg-soft' : 'bg-warn-soft')}><span className={x.state === 'held' || x.state === 'failed' ? 'text-neg' : 'text-warn'}><Icon name="urgent" size={16} /></span><span className="min-w-0 flex-1"><MdInline text={x.state_note_fa} /></span></div> : null}
          </div>

          <div className={cx('grid items-start gap-5', x.kind === 'design' ? 'grid-cols-1' : 'md:grid-cols-[240px_minmax(0,1fr)]')}>
            <div className="flex flex-col gap-3">
              <Block title={x.kind === 'design' ? 'ماکاپ رندرشده' : 'پیش‌نمایش رندر'}>
                <RenderPreview file={x.render} aspect={aspectOfItem(x)} label={`رندر ${x.ref}`} className={x.kind === 'design' ? 'w-full' : 'mx-auto w-full max-w-[240px]'} />
                {x.render ? <span className="text-[11px] text-muted"><FileChip f={x.render} icon={x.render.mime.startsWith('video/') ? 'video' : 'image'} />{x.render.duration_s ? <> · <span className="fig">{x.render.duration_s}s</span></> : null}</span> : null}
              </Block>
              {x.voice ? <Block title="صدا (روی خود هاب)"><AudioPlayer fileId={x.voice.id} label={`صدای ${x.ref}`} compact /></Block> : null}
              {x.captions ? <Block title="زیرنویس"><FileChip f={x.captions} icon="report" /></Block> : null}
              {x.assets.length ? <Block title="فایل‌ها"><div className="flex flex-wrap gap-1.5">{x.assets.map((a) => <FileChip key={a.id} f={a} icon="image" />)}</div></Block> : null}
            </div>
            <div className="flex min-w-0 flex-col gap-5">
              {x.brief_md ? <Block title="brief"><p className="rounded-[12px] bg-tile p-3 text-[13px] leading-6 text-ink">{x.brief_md}</p></Block> : null}
              {x.script ? (
                <Block title={<span className="flex items-center gap-1.5">سناریو<span className="font-normal text-muted">· {ACTOR_FA(x.script.by)}</span></span>}>
                  <Md text={x.script.text_fa} className="flex flex-col gap-2 rounded-[12px] bg-tile p-3 text-[14px] leading-7 text-ink" />
                  {x.script.sources.length ? (
                    <ul className="flex flex-col gap-1">{x.script.sources.map((s, i) => (
                      <li key={i} className="flex flex-wrap items-center gap-1.5 text-[12px] text-sec"><Icon name="knowledge" size={13} /><span className="text-muted">{SOURCE_FA[s.kind] ?? s.kind}</span>
                        {s.ref ? <RefChip r={s.ref} tone="neutral" /> : null}{s.url ? <a href={s.url} target="_blank" rel="noreferrer noopener" dir="ltr" className="fig max-w-[220px] truncate text-gold-ink hover:underline">{s.url.replace(/^https?:\/\//, '')}</a> : null}<span>{s.note}</span></li>
                    ))}</ul>
                  ) : <p className="text-[12px] text-neg">بی‌منبع: هر عدد سناریو منبع میخواهد.</p>}
                </Block>
              ) : null}
              {x.direction ? (
                <Block title={<span className="flex items-center gap-1.5">کارگردانی<span className="font-normal text-muted">· {ACTOR_FA(x.direction.by)}</span></span>}>
                  <ol className="flex flex-col gap-1.5">
                    {x.direction.shots.map((s) => (
                      <li key={s.n} className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-0.5 rounded-[10px] bg-tile p-2.5 text-[12px]">
                        <span className="row-span-3 flex flex-col items-center gap-0.5"><span className="flex size-6 items-center justify-center rounded-full bg-card text-[11px] font-semibold text-ink">{s.n}</span>{s.duration_s ? <span className="fig text-[10px] text-muted">{s.duration_s}s</span> : null}</span>
                        <span className="text-ink">{s.visual_fa}</span>
                        {s.text_on_screen_fa ? <span className="text-sec">روی تصویر: «{s.text_on_screen_fa}»</span> : null}
                        {s.voice_fa ? <span className="text-muted">صدا: «{s.voice_fa}»</span> : null}
                      </li>
                    ))}
                  </ol>
                </Block>
              ) : null}
              {x.composition ? (
                <Block title="ترکیب‌بندی به‌صورت کد">
                  <p className="flex flex-wrap items-center gap-2 text-[12px] text-sec">
                    <span className="fig rounded-[6px] bg-tile px-2 py-0.5 text-ink">{x.composition.format === 'html' ? 'HTML · CSS · SVG' : 'Lottie JSON'}</span>
                    <span className="fig text-muted">sha256 {x.composition.sha256.slice(0, 12)}…</span>
                    <span className="flex items-center gap-1"><ActorAvatar a={x.composition.by} size={18} />{ACTOR_FA(x.composition.by)}</span>
                  </p>
                  <p className="text-[11px] leading-5 text-muted">بی‌شبکه، فقط کتابخانه‌های مجاز از داخل image، تنها قلم IRANYekanX و پالت شرکت؛ Chromium بی‌سر آن را قاب به قاب در سندباکس رندر میکند.</p>
                </Block>
              ) : null}
              {x.kind !== 'design' || x.checks.length ? (
                <Block title="چک‌ها (با کد)"><CheckGrid checks={x.checks} design={x.kind === 'design'} /></Block>
              ) : null}
              {x.qc ? (
                <Block title={<span className="flex items-center gap-2">بازبینی مدیر رسانه <Pill tone={QC_VERDICT[x.qc.verdict]?.tone} dot>{QC_VERDICT[x.qc.verdict]?.fa ?? x.qc.verdict}</Pill></span>}>
                  <Md text={x.qc.note_md} className="flex flex-col gap-1 text-[13px] leading-6 text-ink" />
                </Block>
              ) : null}
              {x.kind !== 'design' ? <Block title="برنامه‌ی انتشار"><PublishRows rows={x.publish} /></Block> : null}
              <div className="flex flex-wrap items-center gap-3 text-[11px] text-muted">
                <span>هزینه: <span className="fig text-sec">{tokens(x.cost.tokens)} tok · {usd(x.cost.usd)}</span> (از پاکت ماهانه‌ی شرکت)</span>
                <span>ساخته {jDateTime(x.created_at)}</span>
                {x.deliverable_ref ? <RefChip r={x.deliverable_ref} note="تحویل" /> : null}
              </div>
            </div>
          </div>
        </div>
      )}
      <Dialog open={confirm} onOpenChange={setConfirm} title="پایین آوردن این آیتم" actions={<>
        <Button variant="danger" icon="seal" loading={act.unpublish.isPending} onClick={unpublish}>با گذرکلید پایین بیاور</Button>
        <Button variant="secondary" onClick={() => setConfirm(false)}>نه</Button>
      </>}>
        <p>از همان API رسمی حذف میشود، هر جا پلتفرم اجازه بدهد؛ جایی که اجازه ندهد را خودت از اپ پایین میآوری. برنامه‌ی انتشار ادامه دارد.</p>
      </Dialog>
    </Sheet>
  );
}

// ------------------------------------------------------------------ a one-off --
const KINDS: Array<MediaKind | 'design'> = ['reel', 'story', 'post', 'carousel', 'design'];
export function NewItemSheet({ onClose, onMade }: { onClose: () => void; onMade: (ref: string) => void }) {
  const act = useMediaItemAction();
  const toast = useToast();
  const { data: companies } = useCompanies();
  const [key] = useState(() => crypto.randomUUID());
  const [company, setCompany] = useState<string | null>(null);
  const [kind, setKind] = useState<MediaKind | 'design'>('reel');
  const [brief, setBrief] = useState('');
  const ok = !!company && brief.trim().length >= 8;
  const submit = async () => {
    if (!company) return;
    try { const x = await act.create.mutateAsync({ body: { company, kind, brief_md: brief.trim() }, key }); toast({ tone: 'ok', text: <>آیتم <span className="fig">{x.ref}</span> ساخته شد؛ تیم رسانه‌ی همان شرکت از سناریو شروع میکند.</> }); onMade(x.ref); }
    catch (e) { toast({ tone: 'error', text: faError(e) }); }
  };
  return (
    <Sheet open onOpenChange={(v) => !v && onClose()} width={560} title="آیتم یک‌باره" description="بیرون از برنامه‌ها؛ از همان خط تولید میگذرد و آخرش همیشه کارت انتشار برای توست. طراحی رابط منتشر نمیشود و به مدیر فنی میرسد."
      footer={<div className="flex gap-2"><Button variant="primary" icon="send" disabled={!ok} loading={act.create.isPending} onClick={submit}>بساز</Button><Button variant="ghost" onClick={onClose}>انصراف</Button></div>}>
      <div className="flex flex-col gap-4 text-[13px]">
        <fieldset className="flex flex-col gap-2"><legend className="pb-2 font-semibold text-sec">کدام شرکت</legend>
          <div className="flex flex-wrap gap-1.5">{(companies ?? []).filter((c) => c.kind !== 'holding').map((c) => <FilterChip key={c.code} selected={company === c.code} onClick={() => setCompany(c.code)}><span className="flex items-center gap-1.5"><CoMark code={c.code} height={11} />{c.name_fa}</span></FilterChip>)}</div>
        </fieldset>
        <fieldset className="flex flex-col gap-2"><legend className="pb-2 font-semibold text-sec">چه چیزی</legend>
          <div className="flex flex-wrap gap-1.5">{KINDS.map((k) => <FilterChip key={k} selected={kind === k} onClick={() => setKind(k)}><span className="flex items-center gap-1.5"><Icon name={KIND_FA[k]!.icon} size={14} />{KIND_FA[k]!.fa}</span></FilterChip>)}</div>
        </fieldset>
        <label className="flex flex-col gap-1.5 font-semibold text-sec">brief
          <textarea value={brief} onChange={(e) => setBrief(e.target.value)} rows={4} maxLength={2000} placeholder={kind === 'design' ? 'مثلاً: صفحه‌ی اول تریدیار را برای کاربر تازه ساده‌تر کن' : 'مثلاً: ریلز ۱۵ ثانیه‌ای معرفی VIP رایگان تریدیار'} className="w-full rounded-[10px] border border-strong bg-card p-3 text-[14px] font-normal leading-6 text-ink outline-none focus:border-gold-ink" />
          <span className="text-[11px] font-normal text-muted">هیچ داده‌ی مشتری؛ هر عدد منبع میخواهد و محتوای ترید هشدار ریسک.</span>
        </label>
      </div>
    </Sheet>
  );
}

/** What the studio needs from the owner right now: a card to seal, a hold to decide. */
export function NeedsYou({ items, onOpen }: { items: MediaItem[]; onOpen: (ref: string) => void }) {
  const xs = items.filter((x) => x.state === 'waiting_owner' || x.state === 'held');
  if (!xs.length) return null;
  return (
    <Card className="tahrir flex flex-col gap-2 p-4">
      <div className="flex items-center gap-2"><span className="text-gold-ink"><Icon name="seal" size={18} /></span><h2 className="text-[14px] font-semibold text-ink">منتظر تو</h2></div>
      <ul className="flex flex-col gap-1.5">
        {xs.map((x) => (
          <li key={x.ref}>
            <button type="button" onClick={() => onOpen(x.ref)} className="flex w-full flex-wrap items-center gap-2 rounded-[10px] bg-tile px-3 py-2 text-start text-[13px] hover:bg-hover">
              <CoMark code={x.company} height={11} /><span className="font-semibold text-ink">{x.title_fa}</span><span className="fig text-[11px] text-muted">{x.ref}</span>
              <Pill tone={ITEM_STATE[x.state]!.tone} dot className="h-5 text-[11px]">{ITEM_STATE[x.state]!.fa}</Pill>
              <span className="min-w-0 flex-1 truncate text-[12px] text-muted">{x.state === 'held' ? 'ناظر نگه داشته؛ تصمیم با توست' : 'کارت انتشار'}</span>
              {x.decision_ref ? <Link href={`/cartable?ref=${x.decision_ref}`} onClick={(e) => e.stopPropagation()} className="fig text-[12px] text-gold-ink hover:underline">{x.decision_ref}</Link> : null}
            </button>
          </li>
        ))}
      </ul>
    </Card>
  );
}

export function KindFilter({ value, onChange }: { value: string | null; onChange: (v: string | null) => void }) {
  return (
    <div className="flex flex-wrap gap-1.5" role="group" aria-label="نوع">
      <FilterChip selected={!value} onClick={() => onChange(null)}>همه‌ی نوع‌ها</FilterChip>
      {KINDS.map((k) => <FilterChip key={k} selected={value === k} onClick={() => onChange(k)}>{KIND_FA[k]!.fa}</FilterChip>)}
    </div>
  );
}
