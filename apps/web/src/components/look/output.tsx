'use client';

// ⟨1.0.1⟩ Part C, the output and «تأیید و انتشار» (C3.3). The output's page opens with the thing itself (its video, large and playable
// in place; else its picture; else the first lines of the document), then the numbers in one row (how it was made, what it cost, who
// made it, the owner's rating), then the text; the summary is not said twice. What the owner does here is one act: the decision bar at
// the bottom carries «تأیید و انتشار» (the page's one full gold) with «اصلاح» beside it (the composer of its session, with this output
// named; an output of no session: the note to its maker). «خوانده شد» and «بایگانی» are quiet. In the list an output is a media card
// with its poster; a new one carries the thin gold edge and «بی‌امتیاز» is a silver dot.

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { Icon } from '@/components/icon';
import { CompanyMark } from '@/components/brand/marks';
import { EraseButton } from '@/components/erase/erase-button';
import { bidi } from '@/components/ui/bidi';
import { Button, IconButton } from '@/components/ui/button';
import { Md } from '@/components/ui/md';
import { Empty, ErrorState, Pill, Rating, Skeleton } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { RefChip } from '@/components/v17/bits';
import { DeleteOne, RowCheck } from '@/components/v28/outputs';
import { MadeWith, saysHow } from '@/components/v47/effort';
import { ApiError } from '@/lib/api/client';
import { useCompanies, useRate } from '@/lib/api/hooks';
import { handled } from '@/lib/api/observe';
import { fileUrl } from '@/lib/api/v13';
import { categoryOf, useLocalSeen, useOutput, useOutputActions, type Category, type Output } from '@/lib/api/v21';
import { KIND_FA, usePublishPanel, type SessionPublish } from '@/lib/api/v44';
import { panelBest } from '@/lib/api/v47';
import { cx, jDateTime, jTime, tokens, usd } from '@/lib/format';
import { leaks, plain } from '@/lib/plain';
import { STICKY_TOP, useStuck } from './collapse';
import { DecisionBar } from './decision-bar';
import { FileFace, FilesStrip, HeroMedia, VideoFailed, isImage, isVideo, type StripFile } from './files';
import { PublishFor, PublishSection, leadFile } from './publish';
import { Facts, Ltr } from './text';
import { VT_HERO, routeSettled } from './transition';

export const CATEGORY_FA: Record<Category, string> = { report: 'گزارش', work: 'کار' };

/** `usage` as the hub writes it (input, output and cache tokens, cost and equivalent cost), or the older `{tokens, usd}`. */
export function usageOf(d: Pick<Output, 'usage'>): { used: number | null; cost: string | null } {
  const u = (d.usage ?? {}) as Record<string, unknown>;
  const n = (k: string) => (typeof u[k] === 'number' ? (u[k] as number) : null);
  const s = (k: string) => (u[k] == null ? null : String(u[k]));
  const parts = ['input_tokens', 'output_tokens', 'cache_read_tokens', 'cache_write_tokens'].map(n).filter((x): x is number => x != null);
  const used = n('tokens') ?? (parts.length ? parts.reduce((a, b) => a + b, 0) : null);
  const cost = s('usd') ?? (Number(s('cost_usd') ?? 0) > 0 ? s('cost_usd') : s('equiv_cost_usd'));
  return { used: used && used > 0 ? used : null, cost };
}

/** The file an output shows of itself first: its first video, else its first picture. */
export const faceOf = <T extends StripFile>(files: ReadonlyArray<T> | null | undefined): T | null => (files ?? []).find(isVideo) ?? (files ?? []).find(isImage) ?? null;
const squash = (t: string | null | undefined) => (t ?? '').replace(/[#*_`>\-\s]+/g, ' ').trim();

// ============================================================================================== the thing itself ==
/** A video large and playable where it is: its poster until he plays it, its own controls and sound. */
function HeroVideo({ f }: { f: StripFile }) {
  const [failed, setFailed] = useState(false);
  if (failed) return <VideoFailed f={f} />;
  return (
    <video controls playsInline preload="metadata" src={fileUrl(f.id)} poster={f.variants?.poster ? fileUrl(f.variants.poster) : fileUrl(f.id, 'poster')} onError={() => setFailed(true)}
      data-output-hero="video" aria-label={f.name} className="mx-auto block max-h-[460px] max-w-full rounded-[16px] bg-black" />
  );
}

/** A figure of the numbers row. */
function Figure({ label, children, testid }: { label: string; children: ReactNode; testid?: string }) {
  return <div className="flex min-w-[6.5rem] flex-1 flex-col gap-0.5" data-testid={testid}><span className="text-[11px] text-muted">{label}</span><span className="text-[13px] font-semibold leading-6 text-ink">{children}</span></div>;
}

function RatePanel({ d, gold }: { d: Output; gold: boolean }) {
  const rate = useRate();
  const toast = useToast();
  const [score, setScore] = useState(d.rating?.score ?? 0);
  const [hover, setHover] = useState<number | null>(null);
  const [comment, setComment] = useState(d.rating?.comment ?? '');
  const dirty = score !== (d.rating?.score ?? 0) || comment !== (d.rating?.comment ?? '');
  return (
    <section className="flex flex-col gap-3 rounded-[16px] bg-tile/60 p-4" aria-label="امتیاز تو">
      <div className="flex flex-col gap-0.5">
        <h3 className="text-[15px] font-semibold">{d.rating ? 'امتیاز تو (قابل تغییر)' : 'امتیاز تو'}</h3>
        <span className="text-[12px] text-muted">در نمره و یادگیری سازنده‌اش اثر دارد؛ جدا از «خوانده شد».</span>
      </div>
      <div className="no-scrollbar overflow-x-auto"><Rating value={score} hover={hover} onHover={setHover} onChange={setScore} label="امتیاز خروجی" /></div>
      <textarea id="output-note" value={comment ?? ''} onChange={(e) => setComment(e.target.value)} rows={2} maxLength={5000} dir="auto" aria-label="نکته برای سازنده" placeholder="نکته برای سازنده (اختیاری)" className="rounded-[10px] border border-strong bg-tile p-3 text-[14px] text-ink outline-none focus:border-[var(--hq-silver-ink)]" />
      <div className="flex items-center gap-3">
        {d.rating ? <span className="flex-1 text-[12px] text-sec">{d.rating.score} از ۱۰، {jDateTime(d.rating.rated_at)}</span> : <span className="flex-1" />}
        <Button variant={gold ? 'primary' : 'secondary'} icon="rate" disabled={!score || !dirty} loading={rate.isPending} onClick={async () => {
          try { await rate.mutateAsync({ ref: d.ref, score, comment: comment || undefined }); toast({ tone: 'ok', text: `امتیاز ${score} ثبت شد.` }); }
          catch (e) { toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'ثبت نشد.' }); }
        }}>ثبت امتیاز</Button>
      </div>
    </section>
  );
}

/** One output: the thing itself, its numbers, its text, its files and their publications, and the owner's rating. */
export function OutputDetail({ refId, onSeen, onGone, back }: {
  refId: string; onSeen: (refs: string[], seen: boolean, text: string) => Promise<boolean>; onGone: () => void; back?: ReactNode;
}) {
  const router = useRouter();
  const q = useOutput(refId);
  const act = useOutputActions();
  const toast = useToast();
  const local = useLocalSeen();
  const { data: companies } = useCompanies();
  const { sentinel, stuck } = useStuck();
  const [busy, setBusy] = useState(false);
  const [whole, setWhole] = useState(false);
  const [asking, setAsking] = useState<string | null>(null);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const d = q.data;
  const files = useMemo<StripFile[]>(() => d?.attachments ?? [], [d]);
  const panel = usePublishPanel(refId, files.some((f) => isVideo(f) || isImage(f)));
  // The card that was tapped has become this page: the waiting transition may go on.
  useEffect(() => { if (d?.ref) routeSettled(); }, [d?.ref]);
  if (q.isLoading) return <div className="flex flex-col gap-3"><Skeleton className="h-16" /><Skeleton className="h-64" /></div>;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!d?.ref) return <Empty icon="deliverable" title="این خروجی پیدا نشد" />;

  const seenAt = d.seen_at ?? local[d.ref] ?? null;
  const cat = categoryOf(d);
  const { used, cost } = usageOf(d);
  const face = faceOf(files);
  const lead = leadFile(panel.data, files);
  const best = lead && panel.data ? panelBest(panel.data) : null;
  const account = panel.data?.accounts.length === 1 ? panel.data.accounts[0]! : null;
  const summaryNew = !!d.summary && !squash(d.body).includes(squash(d.summary));
  const long = !face && (d.body?.length ?? 0) > 700;
  const file = async () => {
    try {
      const out = await act.file.mutateAsync(d.ref);
      toast({ tone: 'ok', text: <>در بایگانی ثبت شد: <span className="fig">{out.record}</span>؛ پیش‌نویس است تا بایگان کاملش کند.</> });
      void q.refetch();
    } catch (e) {
      if (e instanceof ApiError && (e.status === 404 || e.status === 405)) { handled(e); toast({ tone: 'info', text: 'بایگانی خروجی با به‌روزرسانی هاب فعال میشود.' }); }
      else toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'بایگانی نشد.' });
    }
  };
  const mark = async (seen: boolean) => { setBusy(true); try { if (await onSeen([d.ref], seen, seen ? `${d.ref} به «خوانده‌شده» رفت` : `${d.ref} دوباره تازه شد`)) void q.refetch(); } finally { setBusy(false); } };
  // «اصلاح»: the composer of its session with this output named; an output of no session: the note to its maker.
  const amend = () => {
    const order = panel.data?.order ?? null;
    if (order) { router.push(`/s/${encodeURIComponent(order)}?about=${encodeURIComponent(d.ref)}`); return; }
    const note = document.getElementById('output-note');
    note?.scrollIntoView({ block: 'center' });
    note?.focus();
  };
  const done = (fileId: string, out: SessionPublish) => setNotes((n) => { const { [fileId]: _gone, ...rest } = n; return out.job === null && out.note_fa ? { ...rest, [fileId]: plain(out.note_fa) } : rest; });

  return (
    <article className="flex flex-col gap-5" data-testid="output-detail">
      <div ref={sentinel} aria-hidden className="-mb-5" />
      {/* M14: the card that was tapped grows into this header; M18: it folds to its title once the page has scrolled under it. */}
      <header data-stuck={stuck ? '' : undefined} className={cx(VT_HERO, STICKY_TOP, 'hq-m18 sticky z-10 -mx-2 flex flex-col gap-1 rounded-[12px] px-2 py-1.5', stuck && 'bg-card/95 shadow-[0_8px_20px_rgba(0,0,0,.18)] backdrop-blur-md')}>
        {back ? <div className="hq-m18-fold">{back}</div> : null}
        <div className="hq-m18-fold flex flex-wrap items-center gap-1.5 text-[12px] text-muted">
          <CompanyMark code={d.company} height={13} mono />
          <Facts>{companies?.find((c) => c.code === d.company)?.name_fa ?? d.company}{CATEGORY_FA[cat]}{`${d.producer.title_fa}، ${jDateTime(d.created_at)}`}</Facts>
        </div>
        <h2 className={cx('font-semibold text-ink', stuck ? 'truncate text-[15px] leading-7' : 'text-h2 leading-9')}>{bidi(plain(d.title))}</h2>
      </header>

      {/* The thing itself. */}
      {face ? (
        <div data-output-face={isVideo(face) ? 'video' : 'image'}>
          {isVideo(face) ? <HeroVideo f={face} /> : <HeroMedia f={face} ratio={face.width && face.height ? face.width / face.height : 4 / 5} maxHeight={440} />}
        </div>
      ) : null}

      {/* The numbers, in one row. */}
      <div className="flex flex-wrap gap-x-5 gap-y-3 rounded-[14px] bg-tile/60 px-4 py-3" data-testid="output-figures">
        {saysHow(d.produced_with) ? <div className="min-w-[6.5rem] flex-1"><MadeWith pw={d.produced_with} /></div> : null}
        {used ? <Figure label="مصرف"><Ltr>{tokens(used)}</Ltr> واحد{cost ? <span className="font-normal text-sec">، <Ltr>{usd(cost)}</Ltr></span> : null}</Figure> : null}
        <Figure label="سازنده"><Link href={`/employees/${d.producer.code}`} className="hover:underline">{d.producer.title_fa}</Link></Figure>
        <Figure label="امتیاز تو">{d.rating ? `${d.rating.score} از ۱۰` : '—'}</Figure>
      </div>

      {/* Seen and filed: quiet, never the page's gold. */}
      <div className="flex flex-wrap items-center gap-2">
        {!seenAt ? <Button variant="secondary" size="sm" icon="seal" loading={busy} onClick={() => void mark(true)}>خوانده شد</Button> : (
          <>
            <Pill tone="neutral" icon="seal">خوانده شد، {jDateTime(seenAt)}</Pill>
            <Button variant="text" size="sm" loading={busy} onClick={() => void mark(false)}>دوباره تازه کن</Button>
          </>
        )}
        {d.filed_as ? <RefChip r={d.filed_as} note="در بایگانی" /> : <Button variant="secondary" size="sm" icon="deliverable" loading={act.file.isPending} onClick={file}>بایگانی کن</Button>}
        {d.work_ref ? <Link href={`/work/${d.work_ref}`} className="inline-flex h-8 flex-none items-center gap-1.5 rounded-[8px] px-2 text-[12px] text-sec hover:bg-hover hover:text-ink"><Icon name="task" size={14} />کار مربوط</Link> : null}
      </div>

      {/* The text; the summary only where the text does not already say it. */}
      {summaryNew ? <Md text={d.summary} className="flex flex-col gap-2 text-[15px] font-semibold leading-8 text-ink" /> : null}
      {d.body ? (
        <div className="flex flex-col gap-2" data-output-text>
          <div className={cx(long && !whole && 'max-h-[13.5rem] overflow-hidden [mask-image:linear-gradient(to_bottom,#000_70%,transparent)]')}><Md text={d.body} /></div>
          {long ? <Button variant="text" size="sm" className="-ms-2 self-start" aria-expanded={whole} onClick={() => setWhole(!whole)}>{whole ? 'کمتر' : 'همه‌ی متن'}</Button> : null}
        </div>
      ) : null}

      {files.length ? (
        <section className="flex flex-col gap-2" aria-label="فایل‌ها">
          <h3 className="text-[13px] font-semibold text-ink">فایل‌ها</h3>
          <FilesStrip files={files} label="فایل‌های این خروجی" />
        </section>
      ) : null}
      {/* §44.5 where each video or picture's publication stands; the first one to publish is in the decision bar below. */}
      <PublishSection output={d.ref} files={files} panel={panel.data} lead={lead?.id ?? null} notes={notes} onAsk={(f) => setAsking(f.id)} />

      {Array.isArray(d.evidence) && d.evidence.length ? (
        <details className="text-[13px] text-sec">
          <summary className="cursor-pointer select-none text-[13px] font-semibold text-ink">شاهد ({d.evidence.length})</summary>
          <ul className="flex flex-col gap-1 pt-2">{(d.evidence as Array<Record<string, string>>).map((e, i) => <li key={i} className="flex flex-wrap items-center gap-2"><Icon name="seal" size={14} /><span className="fig">{e.kind}</span>{leaks(e.ref) ? null : <span className="fig text-muted">{e.ref}</span>}{e.note ? <span className={/[A-Za-z]/.test(e.note) ? 'fig' : undefined}>{e.note}</span> : null}</li>)}</ul>
        </details>
      ) : null}
      <RatePanel key={`${d.ref}-${d.rating?.rated_at ?? ''}`} d={d} gold={!lead} />

      {/* What removes it for ever sits last, quiet, away from what he came to do. */}
      <div className="flex flex-wrap items-center gap-2 border-t border-div pt-3" data-output-remove>
        <DeleteOne refId={d.ref} filed={!!d.filed_as} onGone={onGone} />
        <EraseButton kind="output" refId={d.ref} variant="ghost" onGone={onGone} />
      </div>

      {lead ? (
        <DecisionBar place="page" label="تأیید و انتشار"
          context={<Facts>{KIND_FA[isVideo(lead) ? 'reel' : 'post']}{account ? <Ltr tabular={false}>@{account}</Ltr> : 'اینستاگرام'}{best ? <>بهترین ساعت <Ltr>{best.hour}</Ltr></> : null}{'بی کارت و بی اثر انگشت'}</Facts>}
          primary={{ label: 'تأیید و انتشار', onClick: () => setAsking(lead.id) }} quiet={[{ label: 'اصلاح', onClick: amend }]} />
      ) : null}
      {asking ? <PublishFor output={d.ref} fileId={asking} onClose={() => setAsking(null)} onDone={(out) => done(asking, out)} /> : null}
    </article>
  );
}

// =================================================================================================== in the list ==
/** One output in the list: a media card with its poster. New: the thin gold edge and full ink; seen: quieter. «بی‌امتیاز» is a silver dot. */
export function OutputRow({ d, seen, selected, checked, companyFa, onOpen, onMark, onCheck, className }: {
  d: Output; seen: boolean; selected: boolean; checked: boolean; companyFa: string; onOpen: (from: HTMLElement) => void; onMark: () => void; onCheck: (range: boolean) => void; className?: string;
}) {
  const cat = categoryOf(d);
  const face = faceOf(d.attachments as StripFile[] | undefined);
  return (
    <div data-card data-output-row={d.ref} data-seen={seen ? '' : undefined}
      className={cx('group relative flex gap-2 rounded-[14px] p-2.5', !seen && 'hq-edge', selected ? 'bg-raised shadow-[inset_0_0_0_1px_var(--hq-silver-line)]' : checked ? 'bg-[var(--hq-silver-soft)]' : 'hover:bg-hover', className)}>
      <RowCheck on={checked} label={`انتخاب ${d.ref}: ${plain(d.title)}`} onToggle={onCheck} />
      <button type="button" onClick={(e) => onOpen(e.currentTarget.closest<HTMLElement>('[data-card]') ?? e.currentTarget)} className="flex min-w-0 flex-1 gap-3 text-start" aria-current={selected || undefined}>
        {face ? <span data-poster className="relative flex h-[76px] w-[58px] flex-none items-center justify-center overflow-hidden rounded-[10px] bg-tile shadow-[inset_0_0_0_1px_var(--hq-line-divider)]"><FileFace f={face} sign={22} /></span> : null}
        <span className="flex min-w-0 flex-1 flex-col gap-1">
          <span className="flex items-center gap-1.5 text-[11px] text-muted">
            <CompanyMark code={d.company} height={11} mono />
            <span className="min-w-0 flex-1 truncate"><Facts>{companyFa}{CATEGORY_FA[cat]}</Facts></span>
            {d.rating ? <span className="flex-none text-sec">{d.rating.score} از ۱۰</span>
              : <span className="inline-flex flex-none items-center" data-unrated><span role="img" aria-label="بی‌امتیاز" title="بی‌امتیاز" className="size-2 rounded-full bg-silver-ink" /></span>}
          </span>
          <span className={cx('line-clamp-2 text-[14px] font-semibold leading-6', seen ? 'text-sec' : 'text-ink')}>{bidi(plain(d.title))}</span>
          <span className={cx('line-clamp-2 text-[12px] leading-5', seen ? 'text-muted' : 'text-sec')}>{bidi(plain(d.summary))}</span>
          <span className="flex items-center gap-1.5 text-[11px] text-muted">
            <span className="min-w-0 truncate">{d.producer.title_fa}، {jTime(d.created_at)}</span>
            {d.filed_as ? <span className="ms-auto inline-flex flex-none items-center gap-1"><Icon name="deliverable" size={12} />در بایگانی</span> : null}
          </span>
        </span>
      </button>
      <IconButton icon={seen ? 'refresh' : 'seal'} label={seen ? 'دوباره تازه' : 'خوانده شد'} size={34} onClick={onMark} className="self-start opacity-70 group-hover:opacity-100 focus-visible:opacity-100" />
    </div>
  );
}
