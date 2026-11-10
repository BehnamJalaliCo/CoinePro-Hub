'use client';

/**
 * ⟨0.19.8⟩ §44.5 «تأیید و انتشار» under a session output's files.
 *
 * The owner, 2026-11-10: «این برو بیا و هی مهر بکن و اینو مجوز بده … آزار و اذیت میده منو». A reel the workshop made sat in his
 * session with nowhere to go. Each video or image of a session's output now has the one action under it: his tap is the seal
 * (no card, no passkey), the hub sends the file to the company's Instagram through IG-Hub and the row says where it stands.
 * A company whose publish path is not connected yet is the technical team's work, said in one calm line.
 */
import { useMemo, useState } from 'react';
import { Icon } from '@/components/icon';
import { Button } from '@/components/ui/button';
import { Sheet } from '@/components/ui/overlay';
import { FilterChip, Pill } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import {
  CAROUSEL_OTHERS, KIND_FA, STATE_FA, commentHalf, commentOf, coverOf, kindsOf, publishOf, publishable, scheduledIso, storyOf, usePublish, usePublishPanel,
  type PublishKind, type PublishPanel, type SessionPublish,
} from '@/lib/api/v44';
import { JPEG_FA, goesAsJpeg, panelBest } from '@/lib/api/v47';
import { publishNote, useCancel } from '@/components/v47/cancel';
import { FaText } from '@/components/v29/text';
import { ApiError } from '@/lib/api/client';
import { faDigits } from '@/lib/alerts';
import { jTime } from '@/lib/format';

type FileLite = { id: string; name: string; mime: string };

function Row({ f, p, note, story, onAsk }: { f: FileLite; p: SessionPublish | null; note: string | null; story: SessionPublish | null; onAsk: () => void }) {
  const video = f.mime.startsWith('video/');
  // ⟨1.0.1⟩ §51 one that is not out yet can be taken back, asked once under the row; the hub's note («در حال لغو») sits there too
  const cancel = useCancel(p);
  const hubNote = publishNote(p);
  // the handle is Latin inside a Persian line: isolated left-to-right, so «@» stays in front of it
  const where = p
    ? [
      KIND_FA[p.kind],
      // ⟨0.20.0⟩ §46 the hour it is set for (first: the line is one row), and the word viewers comment for its link
      p.state === 'scheduled' && p.scheduled_at ? `ساعت ${jTime(p.scheduled_at)}` : null,
      p.account ? `\u2066@${p.account}\u2069` : null, p.cover_name ? 'با کاور' : null, p.auto ? 'خودکار' : null,
      p.comment ? `کامنت «${p.comment}»` : null,
    ].filter(Boolean).join(' · ')
    : null;
  return (
    <div className="flex flex-col gap-1.5 py-2.5" data-file={f.name} data-publish={p?.state ?? 'none'}>
    <div className="flex items-center gap-3">
      <span className="flex-none text-sec"><Icon name={video ? 'video' : 'image'} size={20} /></span>
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span dir="ltr" className="fig truncate text-right text-[13px] text-ink">{f.name || 'فایل'}</span>
        {p === null && note ? <span className="text-[11px] text-sec">{note}</span>
          : p === null ? <span className="text-[11px] text-muted">{video ? 'ویدیو · آماده‌ی انتشار' : 'تصویر · آماده‌ی انتشار'}</span>
          : p.state === 'failed' ? <span className="text-[11px] text-neg">{[where, p.note_fa].filter(Boolean).join(' · ')}</span>
          : p.state === 'waiting_seal' ? <span className="text-[11px] text-sec">{p.note_fa ?? 'منتظر مُهر شما'}</span>
          : p.state === 'cancelled' ? <span className="truncate text-[11px] text-muted">{[where, 'لغو شد'].filter(Boolean).join(' · ')}</span>
          : where ? <span className="truncate text-[11px] text-sec">{where}</span> : null}
        {story ? <span className={story.state === 'failed' ? 'text-[11px] text-neg' : 'text-[11px] text-muted'}>استوری: {STATE_FA[story.state] ?? story.state}</span> : null}
      </div>
      {p === null ? <Button variant={note ? 'secondary' : 'primary'} size="sm" icon="send" onClick={onAsk}>{note ? 'دوباره' : 'تأیید و انتشار'}</Button>
        : p.state === 'publishing' ? <span className="flex flex-none items-center gap-1"><Pill tone="gold" dot live>در حال انتشار</Pill>{cancel.button}</span>
        : p.state === 'scheduled' ? <span className="flex flex-none items-center gap-1"><Pill tone="gold" dot>زمان‌بندی شد</Pill>{cancel.button}</span>
        : p.state === 'published' ? (
          <span className="flex flex-none items-center gap-1.5">
            <Pill tone="pos" dot>منتشر شد</Pill>
            {p.url ? <a href={p.url} target="_blank" rel="noreferrer" className="inline-flex h-8 items-center rounded-[8px] px-2 text-[12px] font-semibold text-gold-ink hover:bg-gold-soft">باز کن</a> : null}
          </span>
        )
        : p.state === 'waiting_seal' ? <Pill tone="warn" dot>منتظر مُهر</Pill>
        : <Button variant="secondary" size="sm" icon="refresh" onClick={onAsk}>دوباره</Button>}
    </div>
      {hubNote ? <span className="text-[11px] leading-5 text-muted" data-publish-note><FaText text={hubNote} /></span> : null}
      {cancel.under}
    </div>
  );
}

/** ⟨1.0.1⟩ §52 one calm line under a picture that is not a JPEG: nothing for him to do, the hub converts it. */
const JpegNote = () => <p className="text-[11px] leading-5 text-muted" data-testid="jpeg-note">{JPEG_FA}</p>;

const FIELD = 'w-full rounded-[10px] border border-strong bg-tile p-3 text-[14px] leading-7 text-ink outline-none transition-colors focus:border-gold-ink';

function Confirm({ output, f, covers, others, panel, onClose, onDone }: {
  output: string; f: FileLite; covers: ReadonlyArray<FileLite>; others: ReadonlyArray<FileLite>; panel: PublishPanel; onClose: () => void; onDone: (out: SessionPublish) => void;
}) {
  const toast = useToast();
  const publish = usePublish(output);
  // ⟨0.20.0⟩ §46 the output's other videos and images: with them this file can go out as a carousel
  const more = useMemo(() => others.slice(0, CAROUSEL_OTHERS), [others]);
  const kinds = useMemo(() => kindsOf(f.mime, more.length), [f.mime, more.length]);
  const [kind, setKind] = useState<PublishKind>(kinds[0]!);
  const [account, setAccount] = useState<string | null>(panel.accounts.length === 1 ? panel.accounts[0]! : null);
  // ⟨0.19.9⟩ §45 the caption its package carries (`caption.txt`) is already in place; he edits it or just taps
  const [caption, setCaption] = useState(panel.caption ?? '');
  // a reel goes out with its cover: the output's images (the one named `cover…`, else the one there is, chosen already)
  const [cover, setCover] = useState<string | null>(coverOf(covers)?.id ?? null);
  // ⟨0.20.0⟩ §46 the time (now, or today/tomorrow at an hour) and the comment rule of this post (its package's, already in place)
  // ⟨1.0.1⟩ §49 with the account's best hour known, it is one of the times
  const best = panelBest(panel);
  const [when, setWhen] = useState<'now' | 'later' | 'best'>('now');
  const later = when !== 'now';
  const [day, setDay] = useState<0 | 1>(0);
  const [clock, setClock] = useState('');
  const [word, setWord] = useState((panel.comment?.keywords ?? []).join('، '));
  const [reply, setReply] = useState(panel.comment?.reply ?? '');
  const [link, setLink] = useState(panel.comment?.link ?? '');
  const whenIso = when === 'later' ? scheduledIso(day, clock) : when === 'best' ? best?.at ?? null : null;
  // one key for one press: a different kind or time is another publish
  const stamp = `${kind}|${when === 'later' ? `${day}|${clock}` : when}`;
  const [keys, setKeys] = useState<Record<string, string>>({});
  const pick = panel.accounts.length > 1 && account === null;
  const noHour = later && whenIso === null;
  // ⟨1.0.1⟩ §52 a picture that goes out (this file, or the reel's cover) and is not a JPEG
  const coverFile = kind === 'reel' ? covers.find((x) => x.id === cover) ?? null : null;
  const half = kind !== 'story' && commentHalf(word, reply, link);
  const go = async () => {
    const key = keys[stamp] ?? crypto.randomUUID();
    if (!keys[stamp]) setKeys((k) => ({ ...k, [stamp]: key }));
    try {
      const out = await publish.mutateAsync({
        file_id: f.id, kind, caption: kind === 'story' ? undefined : caption, account, cover_file_id: kind === 'reel' ? cover : null, key,
        file_ids: kind === 'carousel' ? more.map((x) => x.id) : undefined, scheduled_at: whenIso, comment: commentOf(word, reply, link),
      });
      toast({
        tone: out.state === 'waiting_setup' ? 'info' : 'ok',
        text: out.state === 'waiting_setup' ? (out.note_fa ?? 'تیم فنی هلدینگ مسیر انتشار را وصل میکند.')
          : out.state === 'published' ? 'منتشر شده است.'
          : out.state === 'scheduled' ? `${KIND_FA[out.kind]} زمان‌بندی شد؛ سر ساعت خودش منتشر میشود.`
          : `${KIND_FA[out.kind]} به اینستاگرام رفت؛ نتیجه همین‌جا می‌آید.`,
      });
      onDone(out);
    } catch (e) {
      toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'این کار انجام نشد؛ دوباره امتحان کن.' });
    }
  };
  return (
    <Sheet
      open onOpenChange={(v) => { if (!v) onClose(); }} title="تأیید و انتشار" description="اینستاگرام، از راه IG-Hub · بی کارت و بی اثر انگشت"
      footer={(
        <div className="flex flex-col gap-2">
          <Button variant="primary" size="lg" icon="send" className="w-full" disabled={pick || noHour || half} loading={publish.isPending} onClick={go}>{later ? 'تأیید و زمان‌بندی' : 'تأیید و انتشار'}</Button>
          <p className="text-[11px] text-muted">
            {pick ? 'اول حساب را انتخاب کنید.'
              : noHour ? 'ساعت را به شکل ۱۸:۳۰ بنویسید.'
              : half ? 'برای کامنت، هم کلمه لازم است و هم پیام.'
              : kind === 'carousel' ? `هر ${faDigits(String(more.length + 1))} فایل این خروجی با هم، به همین ترتیب، میروند.`
              : 'برداشتن پست از خود اینستاگرام انجام میشود.'}
          </p>
        </div>
      )}
    >
      <div className="flex flex-col gap-4">
        <div className="flex items-center gap-2">
          <span className="text-gold-ink"><Icon name={f.mime.startsWith('video/') ? 'video' : 'image'} size={18} /></span>
          <span dir="ltr" className="fig truncate text-[13px] text-ink">{f.name || 'فایل'}</span>
        </div>
        {goesAsJpeg(f) ? <JpegNote /> : null}
        <div className="flex flex-col gap-2">
          <span className="text-[12px] font-semibold text-sec">حساب</span>
          {panel.accounts.length === 0 ? <p className="text-[13px] text-sec">حساب این شرکت هنوز به هاب معرفی نشده؛ با تأیید شما تیم فنی هلدینگ همین حالا وصلش میکند.</p>
            : panel.accounts.length === 1 ? <span dir="ltr" className="fig text-right text-[14px] font-semibold text-ink">@{panel.accounts[0]}</span>
            : <div className="flex flex-wrap gap-2">{panel.accounts.map((a) => <FilterChip key={a} selected={account === a} onClick={() => setAccount(a)}><bdi className="fig">@{a}</bdi></FilterChip>)}</div>}
        </div>
        <div className="flex flex-col gap-2">
          <span className="text-[12px] font-semibold text-sec">به شکل</span>
          <div className="flex flex-wrap gap-2">{kinds.map((k) => <FilterChip key={k} selected={kind === k} onClick={() => setKind(k)}>{KIND_FA[k]}</FilterChip>)}</div>
        </div>
        {kind === 'reel' && covers.length ? (
          <div className="flex flex-col gap-2">
            <span className="text-[12px] font-semibold text-sec">کاور</span>
            <div className="flex flex-wrap gap-2">
              {covers.map((x) => <FilterChip key={x.id} selected={cover === x.id} onClick={() => setCover(x.id)}><bdi className="fig">{x.name || 'تصویر'}</bdi></FilterChip>)}
              <FilterChip selected={cover === null} onClick={() => setCover(null)}>بدون کاور</FilterChip>
            </div>
            {goesAsJpeg(coverFile) ? <JpegNote /> : null}
          </div>
        ) : null}
        {kind !== 'story' ? (
          <label className="flex flex-col gap-2">
            <span className="text-[12px] font-semibold text-sec">کپشن</span>
            <textarea value={caption} onChange={(e) => setCaption(e.target.value.slice(0, 2200))} rows={4} dir="auto" placeholder="کپشن و هشتگ‌ها (اختیاری)" className={FIELD} />
          </label>
        ) : null}
        <div className="flex flex-col gap-2" data-testid="publish-time">
          <span className="text-[12px] font-semibold text-sec">زمان</span>
          <div className="flex flex-wrap gap-2">
            <FilterChip selected={when === 'now'} onClick={() => setWhen('now')}>الان</FilterChip>
            <FilterChip selected={when === 'later'} onClick={() => setWhen('later')}>ساعت مشخص</FilterChip>
            {best ? <FilterChip selected={when === 'best'} onClick={() => setWhen('best')}>بهترین ساعت ({best.hour})</FilterChip> : null}
          </div>
          {when === 'best' && best?.note_fa ? <p className="text-[11px] leading-5 text-muted"><FaText text={best.note_fa} /></p> : null}
          {when === 'later' ? (
            <div className="flex flex-wrap items-center gap-2">
              <FilterChip selected={day === 0} onClick={() => setDay(0)}>امروز</FilterChip>
              <FilterChip selected={day === 1} onClick={() => setDay(1)}>فردا</FilterChip>
              <input value={clock} onChange={(e) => setClock(e.target.value.slice(0, 5))} dir="ltr" inputMode="numeric" placeholder="18:30" aria-label="ساعت انتشار" className={`${FIELD} fig h-10 min-w-0 flex-1 py-0 text-center`} />
            </div>
          ) : null}
        </div>
        {kind !== 'story' ? (
          <div className="flex flex-col gap-2" data-testid="publish-comment">
            <span className="text-[12px] font-semibold text-sec">کامنت و لینک (اختیاری)</span>
            <input value={word} onChange={(e) => setWord(e.target.value.slice(0, 100))} dir="auto" placeholder="کلمه یا عددی که مخاطب کامنت میکند" aria-label="کلمه‌ی کامنت" className={`${FIELD} h-11 py-0`} />
            <textarea value={reply} onChange={(e) => setReply(e.target.value.slice(0, 1000))} rows={2} dir="auto" placeholder="پیام خصوصی برای او" aria-label="پیام خصوصی" className={FIELD} />
            <input value={link} onChange={(e) => setLink(e.target.value.slice(0, 1900))} dir="ltr" placeholder="https://…" aria-label="لینک" className={`${FIELD} fig h-11 py-0`} />
          </div>
        ) : null}
      </div>
    </Sheet>
  );
}

/** Nothing for an output of no session (or a hub before §44.5), else one row per video or image. */
export function PublishSection({ output, files }: { output: string; files: ReadonlyArray<FileLite> }) {
  const mine = useMemo(() => files.filter((f) => publishable(f.mime)), [files]);
  const q = usePublishPanel(output, mine.length > 0);
  const [asking, setAsking] = useState<FileLite | null>(null);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const panel = q.data;
  // ⟨0.19.9⟩ §45 a working group's daily output is no session's and is tapped here all the same (a hub of §45 says `tap`)
  if (!panel || (panel.order === null && !panel.tap) || mine.length === 0) return null;
  return (
    <section className="flex flex-col gap-1.5" data-testid="publish">
      <h3 className="text-[12px] font-semibold text-gold-ink">انتشار در اینستاگرام</h3>
      <div className="flex flex-col divide-y divide-[var(--hq-div)] rounded-[12px] bg-tile px-3">
        {mine.map((f) => <Row key={f.id} f={f} p={publishOf(panel, f.id)} story={storyOf(panel, f.id)} note={notes[f.id] ?? null} onAsk={() => setAsking(f)} />)}
      </div>
      <p className="text-[11px] text-muted">
        {panel.mode === 'auto'
          ? `کارگروه «${panel.group_fa ?? 'این خروجی'}» خروجی هر روز را خودکار منتشر میکند؛ وضعش همین‌جاست.`
          : 'با تأیید شما همین فایل منتشر میشود؛ کارت و اثر انگشت ندارد.'}
      </p>
      {asking ? (
        <Confirm
          output={output} f={asking} panel={panel} onClose={() => setAsking(null)}
          covers={asking.mime.startsWith('video/') ? mine.filter((x) => x.mime.startsWith('image/')) : []}
          others={mine.filter((x) => x.id !== asking.id)}
          onDone={(out) => {
            const id = asking.id;
            setNotes((n) => { const { [id]: _gone, ...rest } = n; return out.job === null ? { ...rest, [id]: out.note_fa ?? 'تیم فنی هلدینگ مسیر انتشار را وصل میکند.' } : rest; });
            setAsking(null);
          }}
        />
      ) : null}
    </section>
  );
}
