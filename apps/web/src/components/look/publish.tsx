'use client';

// ⟨1.0.1⟩ Part C, «تأیید و انتشار» in the look (C3.3; contract §44.5, §46, §49, §51, §52). The owner's tap is the seal: no card and no
// passkey. The publish sheet is the one spring sheet: the file itself, its kind, the account, the caption, the time (now, an hour, or
// the account's best hour), the comment word, the JPEG line under a picture that is not one, and «انتشار» in its decision bar. Under an
// output's files, one row per video or picture says where its publication stands and takes it back while it is not out; the page's
// first file to publish is carried by the page's decision bar (the one full gold), the others are outlined. A company whose
// publishing path is not connected yet is the technical team's work, said in one calm line, never the owner's step.

import { useMemo, useState, type ReactNode } from 'react';
import { Button } from '@/components/ui/button';
import { FilterChip, Pill, Skeleton } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { FaText } from '@/components/v29/text';
import { publishNote, useCancel } from '@/components/v47/cancel';
import { faDigits } from '@/lib/alerts';
import { ApiError } from '@/lib/api/client';
import { useOutput } from '@/lib/api/v21';
import {
  CAROUSEL_OTHERS, KIND_FA, STATE_FA, commentHalf, commentOf, coverOf, kindsOf, publishOf, publishable, scheduledIso, storyOf, usePublish, usePublishPanel,
  type PublishKind, type PublishPanel, type SessionPublish,
} from '@/lib/api/v44';
import { JPEG_FA, goesAsJpeg, panelBest, type BestHour } from '@/lib/api/v47';
import { ROUTE_NOT_READY_FA, ROUTE_NOT_READY_SHORT_FA } from '@/lib/plain';
import { DecisionBar } from './decision-bar';
import { FileFace, type StripFile } from './files';
import { haptic } from './haptics';
import { SpringSheet } from './spring-sheet';
import { Facts, Ltr, clock } from './text';

export type PubFile = StripFile;

/** A publication that stands: on its way, set for an hour, out, or waiting on the team. A failed or cancelled one does not. */
export const stands = (p: SessionPublish | null | undefined): boolean => !!p && p.state !== 'failed' && p.state !== 'cancelled';
/** Whether the files of this output can be published by a tap at all (a session's output, or a working group's daily one). */
export const tappable = (panel: PublishPanel | null | undefined): panel is PublishPanel => !!panel && (panel.order !== null || !!panel.tap);
/** What is said of an output whose company's publishing path is not set yet (C2.3; never a step of the owner's). */
export const ROUTE_WAITS_FA = 'مسیر انتشار این شرکت را تیم فنی وصل میکند';
/** Whether the company's publishing path is set (§44.5 `ready`; a hub that does not say is taken at its word when he taps). */
export const routeOpen = (panel: PublishPanel): boolean => panel.ready !== false;
/**
 * The file the page's own «تأیید و انتشار» is about: the first video with no publication that stands, else the first such picture
 * (a picture that is only a reel's cover waits behind its reel). Nothing when the working group publishes by itself.
 */
export function leadFile<T extends { id: string; mime: string }>(panel: PublishPanel | null | undefined, files: ReadonlyArray<T>): T | null {
  if (!tappable(panel) || panel.mode === 'auto' || !routeOpen(panel)) return null;
  const free = files.filter((f) => publishable(f.mime) && !stands(publishOf(panel, f.id)));
  return free.find((f) => f.mime.startsWith('video/')) ?? (files.some((f) => f.mime.startsWith('video/')) ? null : free[0] ?? null);
}

type When = 'now' | 'later' | 'best';

/** What a caller already knows of the publication (a desk card): it opens the sheet with it in place. */
export type PublishSeed = { caption?: string | null; account?: string | null; cover?: string | null; best?: BestHour | null; when?: When };

const FIELD = 'w-full rounded-[10px] border border-strong bg-tile p-3 text-[14px] leading-7 text-ink outline-none transition-colors placeholder:text-muted focus:border-[var(--hq-silver-ink)]';
const LABEL = 'text-[12px] font-semibold text-sec';
/** One calm line under a picture that is not a JPEG: nothing for him to do, the hub converts it. */
const JpegNote = () => <p className="text-[11px] leading-5 text-muted" data-testid="jpeg-note">{JPEG_FA}</p>;

/** The publish sheet of one file. */
export function PublishSheet({ output, f, covers, others, panel, seed, onClose, onDone }: {
  output: string; f: PubFile; covers: ReadonlyArray<PubFile>; others: ReadonlyArray<PubFile>; panel: PublishPanel; seed?: PublishSeed | null;
  onClose: () => void; onDone: (out: SessionPublish) => void;
}) {
  const toast = useToast();
  const publish = usePublish(output);
  // The output's other videos and pictures: with them this file can go out as a carousel.
  const more = useMemo(() => others.slice(0, CAROUSEL_OTHERS), [others]);
  const kinds = useMemo(() => kindsOf(f.mime, more.length), [f.mime, more.length]);
  const [kind, setKind] = useState<PublishKind>(kinds[0]!);
  const [account, setAccount] = useState<string | null>(seed?.account && panel.accounts.includes(seed.account) ? seed.account : panel.accounts.length === 1 ? panel.accounts[0]! : null);
  // The caption its package carries is already in place; he edits it or just taps.
  const [caption, setCaption] = useState(seed?.caption ?? panel.caption ?? '');
  // A reel goes out with its cover: the output's pictures (the one named `cover…`, else the one there is, chosen already).
  const [cover, setCover] = useState<string | null>((seed?.cover && covers.some((x) => x.id === seed.cover) ? seed.cover : null) ?? coverOf(covers)?.id ?? null);
  const best = panelBest(panel) ?? (seed?.best ? panelBest({ best: seed.best }) : null);
  const [when, setWhen] = useState<When>(seed?.when === 'best' && best ? 'best' : 'now');
  const later = when !== 'now';
  const [day, setDay] = useState<0 | 1>(0);
  const [hour, setHour] = useState('');
  const [word, setWord] = useState((panel.comment?.keywords ?? []).join('، '));
  const [reply, setReply] = useState(panel.comment?.reply ?? '');
  const [link, setLink] = useState(panel.comment?.link ?? '');
  const [error, setError] = useState<string | null>(null);
  const whenIso = when === 'later' ? scheduledIso(day, hour) : when === 'best' ? best?.at ?? null : null;
  // One key for one press: a different kind or time is another publication.
  const stamp = `${kind}|${when === 'later' ? `${day}|${hour}` : when}`;
  const [keys, setKeys] = useState<Record<string, string>>({});
  const pick = panel.accounts.length > 1 && account === null;
  const noHour = later && whenIso === null;
  const coverFile = kind === 'reel' ? covers.find((x) => x.id === cover) ?? null : null;
  const half = kind !== 'story' && commentHalf(word, reply, link);
  const go = async () => {
    const key = keys[stamp] ?? crypto.randomUUID();
    if (!keys[stamp]) setKeys((k) => ({ ...k, [stamp]: key }));
    setError(null);
    try {
      const out = await publish.mutateAsync({
        file_id: f.id, kind, caption: kind === 'story' ? undefined : caption, account, cover_file_id: kind === 'reel' ? cover : null, key,
        file_ids: kind === 'carousel' ? more.map((x) => x.id) : undefined, scheduled_at: whenIso, comment: commentOf(word, reply, link),
      });
      haptic('seal');
      toast({
        tone: out.state === 'waiting_setup' ? 'info' : 'ok',
        text: out.state === 'waiting_setup' ? ROUTE_NOT_READY_FA
          : out.state === 'published' ? 'منتشر شده است.'
          : out.state === 'scheduled' ? `${KIND_FA[out.kind]} زمان‌بندی شد؛ سر ساعت خودش منتشر میشود.`
          : `${KIND_FA[out.kind]} به اینستاگرام رفت؛ نتیجه همین‌جا می‌آید.`,
      });
      onDone(out);
    } catch (e) {
      haptic('error');
      setError(e instanceof ApiError ? e.messageFa : 'این کار انجام نشد؛ دوباره امتحان کن.');
    }
  };
  const context = pick ? 'اول حساب را انتخاب کن.'
    : noHour ? 'ساعت را به شکل ۱۸:۳۰ بنویس.'
    : half ? 'برای کامنت، هم کلمه لازم است و هم پیام.'
    : kind === 'carousel' ? `هر ${faDigits(String(more.length + 1))} فایل این خروجی با هم، به همین ترتیب، میروند.`
    : <Facts>{KIND_FA[kind]}{account ? <Ltr tabular={false}>@{account}</Ltr> : null}{when === 'best' && best ? <>بهترین ساعت <Ltr>{best.hour}</Ltr></> : when === 'later' && whenIso ? <>{day ? 'فردا' : 'امروز'} <Ltr>{clock(whenIso)}</Ltr></> : 'همین حالا'}</Facts>;
  return (
    <SpringSheet open onOpenChange={(v) => { if (!v) onClose(); }} title="تأیید و انتشار" description="اینستاگرام؛ بی کارت و بی اثر انگشت" testid="publish-sheet" width={520}
      bar={<DecisionBar label="انتشار" error={error} context={context} state={publish.isPending ? 'working' : 'idle'}
        primary={{ label: later ? 'زمان‌بندی' : 'انتشار', onClick: () => void go(), disabled: pick || noHour || half }} />}>
      <div className="flex flex-col gap-4 pb-1">
        <div className="flex items-center gap-3" data-publish-preview>
          <span className="relative flex h-24 w-[72px] flex-none items-center justify-center overflow-hidden rounded-[12px] bg-tile shadow-[inset_0_0_0_1px_var(--hq-line-divider)]"><FileFace f={f} sign={28} /></span>
          <span className="flex min-w-0 flex-1 flex-col gap-0.5">
            <Ltr tabular={false} className="text-[13px] font-semibold text-ink [overflow-wrap:anywhere]">{f.name || 'فایل'}</Ltr>
            <span className="text-[12px] text-sec">{f.mime.startsWith('video/') ? 'ویدیو' : 'تصویر'}</span>
            {goesAsJpeg(f) ? <JpegNote /> : null}
          </span>
        </div>
        <div className="flex flex-col gap-2">
          <span className={LABEL}>به شکل</span>
          <div className="flex flex-wrap gap-2">{kinds.map((k) => <FilterChip key={k} selected={kind === k} onClick={() => setKind(k)}>{KIND_FA[k]}</FilterChip>)}</div>
        </div>
        <div className="flex flex-col gap-2">
          <span className={LABEL}>حساب</span>
          {panel.accounts.length === 0 ? <p className="text-[13px] leading-6 text-sec">{ROUTE_NOT_READY_FA}</p>
            : panel.accounts.length === 1 ? <Ltr tabular={false} className="self-start text-[14px] font-semibold text-ink">@{panel.accounts[0]}</Ltr>
            : <div className="flex flex-wrap gap-2">{panel.accounts.map((a) => <FilterChip key={a} selected={account === a} onClick={() => setAccount(a)}><bdi dir="ltr" className="latin">@{a}</bdi></FilterChip>)}</div>}
        </div>
        {kind === 'reel' && covers.length ? (
          <div className="flex flex-col gap-2">
            <span className={LABEL}>کاور</span>
            <div className="flex flex-wrap gap-2">
              {covers.map((x) => <FilterChip key={x.id} selected={cover === x.id} onClick={() => setCover(x.id)}><bdi dir="ltr" className="latin">{x.name || 'تصویر'}</bdi></FilterChip>)}
              <FilterChip selected={cover === null} onClick={() => setCover(null)}>بدون کاور</FilterChip>
            </div>
            {goesAsJpeg(coverFile) ? <JpegNote /> : null}
          </div>
        ) : null}
        {kind !== 'story' ? (
          <label className="flex flex-col gap-2">
            <span className={LABEL}>کپشن</span>
            <textarea value={caption} onChange={(e) => setCaption(e.target.value.slice(0, 2200))} rows={4} dir="auto" placeholder="کپشن و هشتگ‌ها (اختیاری)" className={FIELD} />
          </label>
        ) : null}
        <div className="flex flex-col gap-2" data-testid="publish-time">
          <span className={LABEL}>زمان</span>
          <div className="flex flex-wrap gap-2">
            <FilterChip selected={when === 'now'} onClick={() => setWhen('now')}>الان</FilterChip>
            <FilterChip selected={when === 'later'} onClick={() => setWhen('later')}>ساعت مشخص</FilterChip>
            {best ? <FilterChip selected={when === 'best'} onClick={() => setWhen('best')}><span>بهترین ساعت (<Ltr>{best.hour}</Ltr>)</span></FilterChip> : null}
          </div>
          {when === 'best' && best?.note_fa ? <p className="text-[11px] leading-5 text-muted"><FaText text={best.note_fa} /></p> : null}
          {when === 'later' ? (
            <div className="flex flex-wrap items-center gap-2">
              <FilterChip selected={day === 0} onClick={() => setDay(0)}>امروز</FilterChip>
              <FilterChip selected={day === 1} onClick={() => setDay(1)}>فردا</FilterChip>
              <input value={hour} onChange={(e) => setHour(e.target.value.slice(0, 5))} dir="ltr" inputMode="numeric" placeholder="18:30" aria-label="ساعت انتشار" className={`${FIELD} fig h-10 min-w-0 flex-1 py-0 text-center`} />
            </div>
          ) : null}
        </div>
        {kind !== 'story' ? (
          <div className="flex flex-col gap-2" data-testid="publish-comment">
            <span className={LABEL}>کامنت و لینک (اختیاری)</span>
            <input value={word} onChange={(e) => setWord(e.target.value.slice(0, 100))} dir="auto" placeholder="کلمه یا عددی که مخاطب کامنت میکند" aria-label="کلمه‌ی کامنت" className={`${FIELD} h-11 py-0`} />
            <textarea value={reply} onChange={(e) => setReply(e.target.value.slice(0, 1000))} rows={2} dir="auto" placeholder="پیام خصوصی برای او" aria-label="پیام خصوصی" className={FIELD} />
            <input value={link} onChange={(e) => setLink(e.target.value.slice(0, 1900))} dir="ltr" placeholder="https://…" aria-label="لینک" className={`${FIELD} fig h-11 py-0`} />
          </div>
        ) : null}
      </div>
    </SpringSheet>
  );
}

/**
 * The publish sheet of one file of an output, wherever it is asked from (the output's page, a tile in a session, a card of the desk):
 * the output's own files and publish panel are read (the calls the output's page uses), then the sheet opens with them.
 */
export function PublishFor({ output, fileId, seed, onClose, onDone }: { output: string; fileId: string; seed?: PublishSeed | null; onClose: () => void; onDone?: (out: SessionPublish) => void }) {
  const out = useOutput(output);
  const panel = usePublishPanel(output);
  const files = useMemo<PubFile[]>(() => (out.data?.attachments ?? []).filter((x) => publishable(x.mime)), [out.data]);
  const f = files.find((x) => x.id === fileId) ?? null;
  if (out.isLoading || panel.isLoading) {
    return (
      <SpringSheet open onOpenChange={(v) => { if (!v) onClose(); }} title="تأیید و انتشار" testid="publish-sheet">
        <div className="flex flex-col gap-3 pb-2"><Skeleton className="h-24 rounded-[12px]" /><Skeleton className="h-10 rounded-[10px]" /><Skeleton className="h-28 rounded-[10px]" /></div>
      </SpringSheet>
    );
  }
  if (!f || !tappable(panel.data)) {
    return (
      <SpringSheet open onOpenChange={(v) => { if (!v) onClose(); }} title="تأیید و انتشار" testid="publish-sheet">
        <p className="pb-3 text-[13px] leading-6 text-sec">این فایل الان آماده‌ی انتشار نیست؛ کمی بعد دوباره امتحان کن.</p>
      </SpringSheet>
    );
  }
  return (
    <PublishSheet key={f.id} output={output} f={f} panel={panel.data} seed={seed} onClose={onClose}
      covers={f.mime.startsWith('video/') ? files.filter((x) => x.mime.startsWith('image/')) : []} others={files.filter((x) => x.id !== f.id)}
      onDone={(o) => { onDone?.(o); onClose(); }} />
  );
}

// ==================================================================================== where a publication stands ==
/** The state of a publication in words with its mark; nothing here is gold. */
export function PublishState({ p }: { p: SessionPublish }) {
  return p.state === 'publishing' ? <Pill tone="silver" dot>در حال انتشار</Pill>
    : p.state === 'scheduled' ? <Pill tone="silver" icon="time">زمان‌بندی شد</Pill>
    : p.state === 'published' ? <Pill tone="pos" dot>منتشر شد</Pill>
    : p.state === 'cancelled' ? <Pill tone="neutral" dot>لغو شد</Pill>
    : p.state === 'waiting_seal' ? <Pill tone="warn" icon="time">منتظر تأیید</Pill>
    : p.state === 'waiting_setup' ? <Pill tone="neutral" dot>در حال وصل شدن</Pill>
    : <Pill tone="neg" icon="urgent">انجام نشد</Pill>;
}
const OPEN = 'inline-flex h-8 items-center rounded-[8px] px-2 text-[12px] font-semibold text-silver-ink hover:bg-[var(--hq-silver-soft)] hover:text-ink';
/** «باز کن»: the published post, outside the app. */
export const OpenLink = ({ url }: { url: string }) => <a href={url} target="_blank" rel="noreferrer" className={OPEN}>باز کن</a>;

/** The facts of a publication in one line: its kind, its hour, its account, its cover, whether the hub sent it by itself, its comment word. */
export function PublishFacts({ p }: { p: SessionPublish }) {
  return (
    <Facts>
      {KIND_FA[p.kind] ?? 'پست'}
      {p.state === 'scheduled' && p.scheduled_at ? <>ساعت <Ltr>{clock(p.scheduled_at)}</Ltr></> : null}
      {p.account ? <Ltr tabular={false}>@{p.account}</Ltr> : null}
      {p.cover_name ? 'با کاور' : null}
      {p.auto ? 'خودکار' : null}
      {p.comment ? `کامنت «${p.comment}»` : null}
    </Facts>
  );
}

function Row({ f, p, note, story, lead, cover, open, onAsk }: { f: PubFile; p: SessionPublish | null; note: string | null; story: SessionPublish | null; lead: boolean; cover: boolean; open: boolean; onAsk: () => void }) {
  const video = f.mime.startsWith('video/');
  const cancel = useCancel(p);
  const hubNote = publishNote(p);
  const free = p === null || p.state === 'failed' || p.state === 'cancelled';
  return (
    <div className="flex flex-col gap-1.5 py-2.5" data-file={f.name} data-publish={p?.state ?? 'none'}>
      <div className="flex items-center gap-3">
        <span className="relative flex h-14 w-11 flex-none items-center justify-center overflow-hidden rounded-[8px] bg-raised"><FileFace f={f} sign={20} /></span>
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <Ltr tabular={false} className="truncate text-[13px] text-ink">{f.name || 'فایل'}</Ltr>
          {p === null && note ? <span className="text-[11px] leading-5 text-sec">{note}</span>
            : p === null ? <span className="text-[11px] text-muted">{cover ? 'کاور ریلز؛ با ریلز میرود' : !open ? (video ? 'ویدیو' : 'تصویر') : video ? 'ویدیو، آماده‌ی انتشار' : 'تصویر، آماده‌ی انتشار'}</span>
            : <span className={p.state === 'failed' ? 'text-[11px] leading-5 text-neg' : 'text-[11px] leading-5 text-sec'}><PublishFacts p={p} />{p.state === 'failed' && p.note_fa ? <span className="block"><FaText text={p.note_fa} /></span> : null}</span>}
          {story ? <span className={story.state === 'failed' ? 'text-[11px] text-neg' : 'text-[11px] text-muted'}>استوری: {STATE_FA[story.state] ?? story.state}</span> : null}
        </div>
        <span className="flex flex-none flex-wrap items-center justify-end gap-1">
          {p ? <PublishState p={p} /> : null}
          {p?.state === 'published' && p.url ? <OpenLink url={p.url} /> : null}
          {cancel.button}
          {/* The page's first file to publish is in the decision bar; here it is said, not repeated. */}
          {(free && lead) || !open ? null : free ? <Button variant="secondary" size="sm" onClick={onAsk}>{p || note ? 'دوباره' : cover ? 'جدا منتشر کن' : 'تأیید و انتشار'}</Button> : null}
        </span>
      </div>
      {hubNote ? <span className="text-[11px] leading-5 text-muted" data-publish-note><FaText text={hubNote} /></span> : null}
      {cancel.under}
    </div>
  );
}

/**
 * Under an output's files: one row per video or picture with where its publication stands. [lead]: the file whose «تأیید و انتشار»
 * the page's decision bar carries. Nothing for an output that cannot be published by a tap, or on a hub before §44.5.
 */
export function PublishSection({ output, files, panel, lead, onAsk, notes }: {
  output: string; files: ReadonlyArray<PubFile>; panel: PublishPanel | null | undefined; lead: string | null; onAsk: (f: PubFile) => void; notes: Record<string, string>;
}) {
  const mine = useMemo(() => files.filter((f) => publishable(f.mime)), [files]);
  // A reel's cover goes out with its reel; on its own it is a second, quieter act.
  const cover = useMemo(() => (mine.some((f) => f.mime.startsWith('video/')) ? coverOf(mine.filter((f) => f.mime.startsWith('image/')))?.id ?? null : null), [mine]);
  if (!tappable(panel) || mine.length === 0) return null;
  const open = routeOpen(panel);
  return (
    <section className="flex flex-col gap-1.5" data-testid="publish" data-output={output} aria-label="انتشار در اینستاگرام">
      <h3 className="text-[13px] font-semibold text-ink">انتشار در اینستاگرام</h3>
      <div className="flex flex-col divide-y divide-[var(--hq-line-divider)] rounded-[12px] bg-tile px-3">
        {mine.map((f) => <Row key={f.id} f={f} p={publishOf(panel, f.id)} story={storyOf(panel, f.id)} note={notes[f.id] ?? null} lead={lead === f.id} cover={cover === f.id} open={open} onAsk={() => onAsk(f)} />)}
      </div>
      {!open ? <span className="text-[12px] leading-5 text-sec" data-route-not-ready>{ROUTE_WAITS_FA}</span> : (
        <p className="text-[11px] leading-5 text-muted">
          {panel.mode === 'auto' ? `کارگروه «${panel.group_fa ?? 'این خروجی'}» خروجی هر روز را خودکار منتشر میکند؛ وضعش همین‌جاست.` : 'با تأیید تو همین فایل منتشر میشود؛ کارت و اثر انگشت ندارد.'}
        </p>
      )}
    </section>
  );
}

/** What sits under a file's tile in a session: its quiet «تأیید و انتشار», or where its publication stands. */
export function PublishUnder({ f, panel, lead, onAsk }: { f: PubFile; panel: PublishPanel | null | undefined; lead: boolean; onAsk: () => void }): ReactNode {
  if (!tappable(panel) || !publishable(f.mime)) return null;
  const p = publishOf(panel, f.id);
  if (stands(p)) {
    return (
      <span className="flex flex-col items-start gap-0.5 text-[11px] leading-4 text-sec" data-tile-publish={p!.state}>
        <span>{p!.state === 'scheduled' && p!.scheduled_at ? <>زمان‌بندی شد، <Ltr>{clock(p!.scheduled_at)}</Ltr></> : STATE_FA[p!.state] ?? 'در راه'}</span>
        {p!.state === 'published' && p!.url ? <a href={p!.url} target="_blank" rel="noreferrer" className="font-semibold text-silver-ink hover:text-ink hover:underline">باز کن</a> : null}
      </span>
    );
  }
  if (!routeOpen(panel)) return <RouteNotReady short />;
  // What the session waits on is in its decision bar (the full gold); here it is not repeated.
  if (lead) return <span className="text-[11px] leading-4 text-muted" data-tile-publish="lead">آماده‌ی انتشار</span>;
  // A cover picture waits behind its reel.
  if (f.mime.startsWith('image/') && panel.mode === 'auto') return null;
  return <button type="button" onClick={onAsk} data-tile-publish="none" className="inline-flex h-8 items-center justify-center rounded-[8px] border border-strong px-2 text-[11px] font-semibold text-ink hover:bg-hover">{p ? 'دوباره' : 'تأیید و انتشار'}</button>;
}

/** The short line of a company whose publishing path is not connected yet. */
export const RouteNotReady = ({ short }: { short?: boolean }) => <span className="text-[12px] leading-5 text-sec" data-route-not-ready>{short ? ROUTE_NOT_READY_SHORT_FA : ROUTE_NOT_READY_FA}</span>;
