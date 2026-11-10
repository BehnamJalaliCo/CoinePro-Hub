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
  KIND_FA, STATE_FA, coverOf, kindsOf, publishOf, publishable, storyOf, usePublish, usePublishPanel,
  type PublishKind, type PublishPanel, type SessionPublish,
} from '@/lib/api/v44';
import { ApiError } from '@/lib/api/client';

type FileLite = { id: string; name: string; mime: string };

function Row({ f, p, note, story, onAsk }: { f: FileLite; p: SessionPublish | null; note: string | null; story: SessionPublish | null; onAsk: () => void }) {
  const video = f.mime.startsWith('video/');
  // the handle is Latin inside a Persian line: isolated left-to-right, so «@» stays in front of it
  const where = p
    ? [KIND_FA[p.kind], p.account ? `\u2066@${p.account}\u2069` : null, p.cover_name ? 'با کاور' : null, p.auto ? 'خودکار' : null].filter(Boolean).join(' · ')
    : null;
  return (
    <div className="flex items-center gap-3 py-2.5">
      <span className="flex-none text-sec"><Icon name={video ? 'video' : 'image'} size={20} /></span>
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span dir="ltr" className="fig truncate text-right text-[13px] text-ink">{f.name || 'فایل'}</span>
        {p === null && note ? <span className="text-[11px] text-sec">{note}</span>
          : p === null ? <span className="text-[11px] text-muted">{video ? 'ویدیو · آماده‌ی انتشار' : 'تصویر · آماده‌ی انتشار'}</span>
          : p.state === 'failed' ? <span className="text-[11px] text-neg">{[where, p.note_fa].filter(Boolean).join(' · ')}</span>
          : p.state === 'waiting_seal' ? <span className="text-[11px] text-sec">{p.note_fa ?? 'منتظر مُهر شما'}</span>
          : where ? <span className="truncate text-[11px] text-sec">{where}</span> : null}
        {story ? <span className={story.state === 'failed' ? 'text-[11px] text-neg' : 'text-[11px] text-muted'}>استوری: {STATE_FA[story.state] ?? story.state}</span> : null}
      </div>
      {p === null ? <Button variant={note ? 'secondary' : 'primary'} size="sm" icon="send" onClick={onAsk}>{note ? 'دوباره' : 'تأیید و انتشار'}</Button>
        : p.state === 'publishing' ? <Pill tone="gold" dot live>در حال انتشار</Pill>
        : p.state === 'published' ? (
          <span className="flex flex-none items-center gap-1.5">
            <Pill tone="pos" dot>منتشر شد</Pill>
            {p.url ? <a href={p.url} target="_blank" rel="noreferrer" className="inline-flex h-8 items-center rounded-[8px] px-2 text-[12px] font-semibold text-gold-ink hover:bg-gold-soft">باز کن</a> : null}
          </span>
        )
        : p.state === 'waiting_seal' ? <Pill tone="warn" dot>منتظر مُهر</Pill>
        : <Button variant="secondary" size="sm" icon="refresh" onClick={onAsk}>دوباره</Button>}
    </div>
  );
}

function Confirm({ output, f, covers, panel, onClose, onDone }: { output: string; f: FileLite; covers: ReadonlyArray<FileLite>; panel: PublishPanel; onClose: () => void; onDone: (out: SessionPublish) => void }) {
  const toast = useToast();
  const publish = usePublish(output);
  const kinds = useMemo(() => kindsOf(f.mime), [f.mime]);
  const [kind, setKind] = useState<PublishKind>(kinds[0]!);
  const [account, setAccount] = useState<string | null>(panel.accounts.length === 1 ? panel.accounts[0]! : null);
  // ⟨0.19.9⟩ §45 the caption its package carries (`caption.txt`) is already in place; he edits it or just taps
  const [caption, setCaption] = useState(panel.caption ?? '');
  // a reel goes out with its cover: the output's images (the one named `cover…`, else the one there is, chosen already)
  const [cover, setCover] = useState<string | null>(coverOf(covers)?.id ?? null);
  const [key] = useState(() => crypto.randomUUID());
  const pick = panel.accounts.length > 1 && account === null;
  const go = async () => {
    try {
      const out = await publish.mutateAsync({ file_id: f.id, kind, caption: kind === 'story' ? undefined : caption, account, cover_file_id: kind === 'reel' ? cover : null, key });
      toast({
        tone: out.state === 'waiting_setup' ? 'info' : 'ok',
        text: out.state === 'waiting_setup' ? (out.note_fa ?? 'تیم فنی هلدینگ مسیر انتشار را وصل میکند.') : out.state === 'published' ? 'منتشر شده است.' : `${KIND_FA[out.kind]} به اینستاگرام رفت؛ نتیجه همین‌جا می‌آید.`,
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
          <Button variant="primary" size="lg" icon="send" className="w-full" disabled={pick} loading={publish.isPending} onClick={go}>تأیید و انتشار</Button>
          <p className="text-[11px] text-muted">{pick ? 'اول حساب را انتخاب کنید.' : 'برداشتن پست از خود اینستاگرام انجام میشود.'}</p>
        </div>
      )}
    >
      <div className="flex flex-col gap-4">
        <div className="flex items-center gap-2">
          <span className="text-gold-ink"><Icon name={f.mime.startsWith('video/') ? 'video' : 'image'} size={18} /></span>
          <span dir="ltr" className="fig truncate text-[13px] text-ink">{f.name || 'فایل'}</span>
        </div>
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
          </div>
        ) : null}
        {kind !== 'story' ? (
          <label className="flex flex-col gap-2">
            <span className="text-[12px] font-semibold text-sec">کپشن</span>
            <textarea
              value={caption} onChange={(e) => setCaption(e.target.value.slice(0, 2200))} rows={4} dir="auto" placeholder="کپشن و هشتگ‌ها (اختیاری)"
              className="w-full rounded-[10px] border border-strong bg-tile p-3 text-[14px] leading-7 text-ink outline-none transition-colors focus:border-gold-ink"
            />
          </label>
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
