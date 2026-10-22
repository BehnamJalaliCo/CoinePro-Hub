'use client';

import { useEffect, useMemo, useState } from 'react';
import { Icon } from '@/components/icon';
import { Button } from '@/components/ui/button';
import { Dialog } from '@/components/ui/overlay';
import { Card, Empty, FilterChip, Pill, Rating, SectionTitle, Skeleton } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { Figs } from '@/components/v14/bits';
import { AudioPlayer } from '@/components/v18/bits';
import { uploadFile } from '@/lib/api/v13';
import { faError, useVoiceAction, useVoiceReference, type Voice } from '@/lib/api/v19';
import { RECORDER_ERROR, clock, useRecorder } from '@/lib/recorder';
import { ago, cx, jDateTime } from '@/lib/format';
import { LicenceBadge } from './bits';

const LETTERS = ['الف', 'ب', 'ج', 'د', 'ه', 'و', 'ز', 'ح'];
const VOICE_STATUS: Record<string, { fa: string; tone: 'pos' | 'neutral' | 'gold' }> = { active: { fa: 'فعال', tone: 'pos' }, candidate: { fa: 'نامزد', tone: 'neutral' }, retired: { fa: 'کنار گذاشته', tone: 'neutral' } };
const hash = (s: string) => [...s].reduce((a, c) => (a * 33 + c.charCodeAt(0)) % 100_003, 17);
const rtfFa = (v: Voice) => (v.rtf == null ? '—' : `${v.rtf.toFixed(2)}×`);

// ------------------------------------------------------------------ the active voice and the owner's choice --
function Activate({ v, onDone }: { v: Voice; onDone?: () => void }) {
  const act = useVoiceAction();
  const toast = useToast();
  const [ask, setAsk] = useState(false);
  const go = async () => {
    try { await act.activate.mutateAsync(v); setAsk(false); toast({ tone: 'ok', text: <>«{v.name_fa}» صدای فعال هاب شد؛ گزارش‌های صوتی و برنامه‌های رسانه از همین میخوانند.</> }); onDone?.(); }
    catch (e) { toast({ tone: 'error', text: faError(e) }); }
  };
  return (
    <>
      <Button variant="primary" icon="seal" loading={act.activate.isPending} onClick={() => (v.licence_commercial ? void go() : setAsk(true))}>فعال کن</Button>
      <Dialog open={ask} onOpenChange={setAsk} title="صدای غیرتجاری" actions={<>
        <Button variant="primary" icon="seal" loading={act.activate.isPending} onClick={go}>میدانم؛ با گذرکلید فعال کن</Button>
        <Button variant="secondary" onClick={() => setAsk(false)}>نه</Button>
      </>}>
        <div className="flex flex-col gap-2">
          <p>کارت مدل «{v.name_fa}» لایسنس <span className="fig">{v.licence}</span> را غیرتجاری میداند. فعال شدنش انتخاب صریح توست، و روی هر استفاده برچسب «غیرتجاری» میخورد.</p>
          <p className="text-[12px] text-muted">مسئله‌ی حقوقی با خود توست؛ هاب فقط آنچه روی کارت مدل آمده را نشان میدهد.</p>
        </div>
      </Dialog>
    </>
  );
}

export function ActiveVoice({ voices }: { voices: Voice[] }) {
  const active = voices.find((v) => v.status === 'active');
  const choice = voices.find((v) => v.id === 'v-xtts-owner') ?? voices.find((v) => v.speaker === 'owner');
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card className="flex flex-col gap-3 p-4">
        <SectionTitle title="صدای فعال" note="گزارش صوتی صبح، نامه‌ی مدیرعامل‌ها و هر برنامه‌ی رسانه با صدا" />
        {!active ? <Empty icon="mic" title="هنوز صدایی فعال نیست" /> : (
          <div className="flex flex-col gap-2">
            <span className="text-[17px] font-semibold text-ink">{active.name_fa}</span>
            <span className="flex flex-wrap items-center gap-2 text-[12px] text-muted"><span className="fig">{active.engine}</span><LicenceBadge commercial={active.licence_commercial} licence={active.licence} /></span>
            <span className="text-[12px] text-sec">RTF <span className="fig">{rtfFa(active)}</span> · اوج حافظه <span className="fig">{active.mem_mb ?? '—'} MB</span> روی CPU هاب</span>
            {active.samples?.[0] ? <AudioPlayer fileId={active.samples[0].file.id} label={`نمونه‌ی ${active.name_fa}`} compact /> : null}
            {active.note_fa ? <p className="text-[12px] text-muted">{active.note_fa}</p> : null}
          </div>
        )}
      </Card>
      {choice && choice.status !== 'active' ? (
        <Card className="tahrir flex flex-col gap-3 p-4">
          <SectionTitle title="انتخاب تو" note="۳۰ مهر: ParsVoice-XTTS، با صدای خود تو اگر نمونه ضبط کنی" />
          <span className="text-[16px] font-semibold text-ink">{choice.name_fa}</span>
          <span className="flex flex-wrap items-center gap-2 text-[12px] text-muted"><LicenceBadge commercial={choice.licence_commercial} licence={choice.licence} /><span>RTF <span className="fig">{rtfFa(choice)}</span> · <span className="fig">{choice.mem_mb ?? '—'} MB</span></span></span>
          <p className="text-[12px] leading-5 text-sec">شنیدن کور پایین فقط تأیید نهایی است. بعد از گوش دادن، با یک مُهر فعالش کن؛ صدای غیرتجاری بی‌انتخاب صریح تو فعال نمیشود.</p>
          <div className="flex flex-wrap items-center gap-2"><Activate v={choice} />{choice.owner_score != null ? <Pill tone="gold">نمره‌ی کور تو: {choice.owner_score}</Pill> : <Pill tone="neutral" icon="mic">هنوز کور نشنیده‌ای</Pill>}</div>
        </Card>
      ) : null}
    </div>
  );
}

// ------------------------------------------------------------------ the owner's own voice --
export function ReferenceCard() {
  const ref = useVoiceReference();
  const act = useVoiceAction();
  const toast = useToast();
  const [uploading, setUploading] = useState(false);
  const rec = useRecorder({
    maxSeconds: 180,
    onFinish: (audio, seconds) => {
      if (seconds < 60) { toast({ tone: 'info', text: 'کمتر از یک دقیقه بود؛ دست‌کم یک دقیقه صدای تمیز لازم است.' }); return; }
      setUploading(true);
      const ext = audio.type.includes('mp4') ? 'm4a' : audio.type.includes('ogg') ? 'ogg' : 'webm';
      uploadFile(audio, `owner-reference.${ext}`)
        .then((f) => act.reference.mutateAsync(f.id))
        .then(() => toast({ tone: 'ok', text: 'نمونه‌ی صدایت روی هاب نشست؛ نامزدهای ساخت صدا از آن، متن‌های آزمون را دوباره میخوانند.' }))
        .catch((e: unknown) => toast({ tone: 'error', text: faError(e) }))
        .finally(() => setUploading(false));
    },
  });
  const { state, reset } = rec;
  useEffect(() => { if (state === 'denied' || state === 'unsupported' || state === 'failed') { toast({ tone: 'error', text: RECORDER_ERROR[state] }); reset(); } }, [state, reset, toast]);
  const recording = rec.state === 'recording' || rec.state === 'asking';
  const r = ref.data;
  return (
    <Card className="flex flex-col gap-3 p-4">
      <SectionTitle title="صدای خود تو" note="۱ تا ۳ دقیقه صدای تمیز؛ مثل هر فایل تو روی هاب میماند و هیچ‌جا فرستاده نمیشود" />
      {ref.isLoading ? <Skeleton className="h-16" /> : r ? (
        <div className="flex flex-wrap items-center gap-2 text-[13px] text-sec">
          <Pill tone={r.state === 'ready' ? 'pos' : r.state === 'processing' ? 'lapis' : 'neg'} dot live={r.state === 'processing'}>{r.state === 'ready' ? 'آماده' : r.state === 'processing' ? 'در حال پردازش' : 'پذیرفته نشد'}</Pill>
          {r.duration_s ? <span>نمونه‌ی <span className="fig">{clock(r.duration_s)}</span></span> : null}<span>ضبط {ago(r.created_at)}</span>
          {r.reason_fa ? <span className="text-neg">{r.reason_fa}</span> : null}
        </div>
      ) : <p className="text-[13px] text-sec">هنوز نمونه‌ای ضبط نکرده‌ای. با نمونه، ParsVoice-XTTS و Chatterbox متن‌های آزمون را با صدای خودت هم میخوانند.</p>}
      <div className="flex flex-wrap items-center gap-3 rounded-[12px] bg-tile p-3">
        {recording ? (
          <>
            <span className="flex size-3 rounded-full bg-neg" style={{ animation: 'hq-live 1.4s infinite' }} aria-hidden />
            <span className="fig text-[15px] font-semibold text-ink">{clock(rec.elapsed)}</span>
            <span className="flex h-8 min-w-0 flex-1 items-center gap-[2px]" aria-hidden>{rec.levels.map((l, i) => <span key={i} className="w-[3px] rounded-full bg-gold" style={{ height: `${Math.max(8, l * 100)}%` }} />)}</span>
            <Button variant="primary" icon="stop" onClick={rec.finish}>تمام</Button>
            <Button variant="ghost" onClick={rec.cancel}>دور بریز</Button>
          </>
        ) : (
          <>
            <span className="min-w-0 flex-1 text-[12px] leading-5 text-sec">یک جای ساکت؛ با صدای معمولی یک متن آموزشی بخوان، مثل وقتی برای کانال حرف میزنی. حداکثر <span className="fig">3:00</span>.</span>
            <Button variant="secondary" icon="mic" loading={uploading} onClick={() => void rec.start()}>{r ? 'ضبط دوباره' : 'ضبط نمونه'}</Button>
          </>
        )}
      </div>
    </Card>
  );
}

// ------------------------------------------------------------------ the blind test --
/** The owner listens without names: clips labelled الف، ب، …, in an order that says nothing; a voice's name shows once it is scored. */
export function BlindTest({ voices }: { voices: Voice[] }) {
  const act = useVoiceAction();
  const toast = useToast();
  const speaking = useMemo(() => voices.filter((v) => v.samples?.length).sort((a, b) => hash(`${a.id}·blind`) - hash(`${b.id}·blind`)), [voices]);
  const scripts = speaking[0]?.samples ?? [];
  const [script, setScript] = useState<string | null>(null);
  const [hover, setHover] = useState<Record<string, number | null>>({});
  const sc = script ?? scripts[0]?.script ?? null;
  const text = scripts.find((s) => s.script === sc);
  const scored = speaking.filter((v) => v.owner_score != null).length;
  const score = async (v: Voice, n: number, label: string) => {
    try { await act.score.mutateAsync({ id: v.id, score: n }); toast({ tone: 'ok', text: <>صدای {label}: نمره‌ی {n}. حالا اسمش را میبینی.</> }); }
    catch (e) { toast({ tone: 'error', text: faError(e) }); }
  };
  if (!speaking.length) return <Card className="p-2"><Empty icon="mic" title="هنوز نمونه‌ای اندازه‌گیری نشده" /></Card>;
  return (
    <Card className="flex flex-col gap-4 p-4">
      <SectionTitle title="شنیدن کور" note={`${scored} از ${speaking.length} صدا نمره گرفته؛ نام هر صدا بعد از نمره‌ی تو دیده میشود`} />
      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap gap-1.5">{scripts.map((s) => <FilterChip key={s.script} selected={sc === s.script} onClick={() => setScript(s.script)}>{s.title_fa}</FilterChip>)}</div>
        {text ? <p className="rounded-[12px] bg-tile p-3 text-[14px] leading-7 text-ink">«<Figs text={text.text_fa} />»</p> : null}
      </div>
      <ul className="grid gap-3 md:grid-cols-2">
        {speaking.map((v, i) => {
          const clip = v.samples?.find((s) => s.script === sc);
          const label = LETTERS[i] ?? String(i + 1);
          const shown = v.owner_score != null;
          return (
            <li key={v.id} className={cx('flex flex-col gap-2.5 rounded-[14px] p-3', shown ? 'bg-tile' : 'bg-card ring-1 ring-[var(--hq-line-strong)]')}>
              <div className="flex items-center gap-2">
                <span className="flex size-9 flex-none items-center justify-center rounded-full bg-gold-soft text-[14px] font-bold text-gold-ink">{label}</span>
                <span className="flex min-w-0 flex-1 flex-col">
                  <span className="truncate text-[13px] font-semibold text-ink">{shown ? v.name_fa : `صدای ${label}`}</span>
                  <span className="text-[11px] text-muted">{shown ? <span className="flex flex-wrap items-center gap-1.5"><LicenceBadge commercial={v.licence_commercial} licence={v.licence} />{v.speaker === 'owner' ? <span>صدای خود تو</span> : null}</span> : 'نام بعد از نمره'}</span>
                </span>
                {shown ? <Pill tone="gold">{v.owner_score}</Pill> : null}
              </div>
              {clip ? <AudioPlayer fileId={clip.file.id} label={`صدای ${label}، ${clip.title_fa}`} compact /> : <p className="text-[12px] text-muted">این متن را نخوانده.</p>}
              <div className="flex flex-col gap-1">
                <span className="text-[11px] text-muted">نمره‌ی تو</span>
                <Rating label={`نمره‌ی صدای ${label}`} value={v.owner_score ?? 0} size={26} hover={hover[v.id] ?? null} onHover={(n) => setHover((h) => ({ ...h, [v.id]: n }))} onChange={(n) => void score(v, n, label)} />
              </div>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

// ------------------------------------------------------------------ the registry --
export function VoiceRegistry({ voices }: { voices: Voice[] }) {
  return (
    <Card className="flex flex-col gap-3 p-4">
      <SectionTitle title="نامزدها و اندازه‌گیری" note="RTF و اوج حافظه روی CPU خود هاب؛ لایسنس همان‌طور که کارت هر مدل گفته" />
      <ul className="flex flex-col gap-2">
        {voices.map((v) => {
          const st = VOICE_STATUS[v.status] ?? VOICE_STATUS.candidate!;
          const scored = v.owner_score != null;
          return (
            <li key={v.id} className="flex flex-col gap-2 rounded-[12px] bg-tile p-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[14px] font-semibold text-ink">{v.name_fa}</span>
                <Pill tone={st.tone} dot>{st.fa}</Pill>
                {v.speaker === 'owner' ? <Pill tone="gold" icon="owner">صدای تو</Pill> : null}
                <span className="flex-1" />
                <LicenceBadge commercial={v.licence_commercial} licence={v.licence} />
              </div>
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px] text-sec">
                <span className="fig text-muted">{v.engine}</span>
                <span>RTF <span className="fig text-ink">{rtfFa(v)}</span></span>
                <span>حافظه <span className="fig text-ink">{v.mem_mb != null ? `${v.mem_mb} MB` : '—'}</span></span>
                <span>نمره‌ی کور <span className="text-ink">{scored ? v.owner_score : '—'}</span></span>
                {v.measured_at ? <span className="text-muted">اندازه‌گیری {jDateTime(v.measured_at)}</span> : null}
              </div>
              {v.note_fa ? <p className="flex items-start gap-1.5 text-[12px] leading-5 text-muted"><Icon name="info" size={13} />{v.note_fa}</p> : null}
              {v.status !== 'active' && v.samples?.length && scored ? <div><Activate v={v} /></div> : null}
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

