'use client';

import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useState } from 'react';
import { Icon } from '@/components/icon';
import { Button } from '@/components/ui/button';
import { Md, MdInline } from '@/components/ui/md';
import { Sheet } from '@/components/ui/overlay';
import { Card, Empty, ErrorState, FilterChip, PageHeader, Pill, SectionTitle, Skeleton } from '@/components/ui/primitives';
import { AUDIO, AudioPlayer } from '@/components/v18/bits';
import { CoMark, RefChip, ScopeChips } from '@/components/v17/bits';
import { useCompanies } from '@/lib/api/hooks';
import { useBriefing, useBriefings, useLatestBriefing, useSettings18, type Briefing, type BriefingKind } from '@/lib/api/v18';
import { ago, cx, jDate, jWeekday } from '@/lib/format';

const KIND_FA: Record<BriefingKind, string> = { morning: 'گزارش صبحگاهی', ceo_letter: 'نامه‌ی هفتگی' };

function Voice({ b }: { b: Briefing }) {
  if (b.audio && b.audio_state === 'ready') return <AudioPlayer fileId={b.audio.id} label={`${KIND_FA[b.kind]} ${b.ref}`} />;
  const st = AUDIO[b.audio_state] ?? AUDIO.off!;
  return (
    <div className="flex items-center gap-2 rounded-[14px] bg-tile p-3 text-[12px] text-sec">
      <Icon name="mic" size={16} /><Pill tone={st.tone} dot live={b.audio_state === 'pending'}>{st.fa}</Pill>
      <span>{b.audio_state === 'failed' ? 'متن بی‌تغییر همین‌جاست.' : b.audio_state === 'off' ? 'صدا در تنظیمات خاموش است.' : 'چند دقیقه‌ی دیگر.'}</span>
    </div>
  );
}

function VoiceInfo({ b }: { b: Briefing }) {
  if (!b.voice) return null;
  return <p className="text-[11px] text-muted">صدا روی خود هاب ساخته شد: <span className="fig">{b.voice.engine} {b.voice.version} · {b.voice.voice}</span> · لایسنس صدا: <span className="fig">{b.voice.license}</span>. متن گفتاری را کد میسازد: هیچ رقم لاتینی نمیماند.</p>;
}

function BriefingSheet({ refId, onClose }: { refId: string; onClose: () => void }) {
  const q = useBriefing(refId);
  const b = q.data;
  return (
    <Sheet open onOpenChange={(v) => !v && onClose()} width={600} title={b ? <span className="flex items-center gap-2">{KIND_FA[b.kind]}<span className="fig text-[13px] text-muted">{b.ref}</span></span> : '…'}
      description={b ? <span className="flex items-center gap-1.5"><CoMark code={b.company} height={11} />{jDate(b.period.from)} تا {jDate(b.period.to)}</span> : undefined}>
      {q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : !b ? <Skeleton className="h-60" /> : (
        <div className="flex flex-col gap-4">
          <Voice b={b} />
          <Md text={b.text_md} className="flex flex-col gap-2 text-[14px] leading-7 text-ink" />
          <div className="flex flex-wrap items-center gap-2"><RefChip r={b.deliverable_ref} note="خروجی" />{b.kind === 'ceo_letter' ? <Link href={`/messages?thread=${b.company}-CEO`} className="text-[12px] text-gold-ink hover:underline">جواب به مدیرعامل</Link> : null}</div>
          <VoiceInfo b={b} />
        </div>
      )}
    </Sheet>
  );
}

function Morning({ onOpen }: { onOpen: (ref: string) => void }) {
  const q = useLatestBriefing('morning');
  const b = q.data;
  return (
    <Card className="flex flex-col gap-3 p-5">
      <SectionTitle title="گزارش صبحگاهی" note={b ? `${jWeekday(b.created_at)}، ${ago(b.created_at)}` : 'هر روز بعد از نسخه‌ی نوشته‌شده'} action={b ? <Button size="sm" variant="text" iconEnd="next" onClick={() => onOpen(b.ref)}>کامل</Button> : null} />
      {q.isLoading ? <Skeleton className="h-40" /> : !b ? <Empty icon="report" title="گزارش امروز هنوز نیامده" /> : (
        <>
          <Voice b={b} />
          <Md text={b.text_md} className="flex flex-col gap-1.5 text-[14px] leading-7 text-ink" />
          <VoiceInfo b={b} />
        </>
      )}
    </Card>
  );
}

function LetterCard({ company, onOpen }: { company: string; onOpen: (ref: string) => void }) {
  const q = useLatestBriefing('ceo_letter', company);
  const { data: companies } = useCompanies();
  const name = companies?.find((c) => c.code === company)?.name_fa ?? company;
  const b = q.data;
  const flagged = !!b?.text_md.includes('عدد بی‌منبع');
  return (
    <Card className="flex flex-col gap-3 p-4">
      <div className="flex items-center gap-2">
        <CoMark code={company} height={14} />
        <span className="min-w-0 flex-1 text-[14px] font-semibold text-ink">نامه‌ی مدیرعامل {name}</span>
        {flagged ? <Pill tone="neg" icon="urgent">عدد بی‌منبع</Pill> : null}
      </div>
      {q.isLoading ? <Skeleton className="h-28" /> : !b ? <p className="text-[13px] text-muted">نامه‌ی این هفته هنوز نیامده.</p> : (
        <>
          <span className="text-[11px] text-muted">هفته‌ی منتهی به {jDate(b.period.to)} · <span className="fig">{b.ref}</span></span>
          <Voice b={b} />
          <p className="line-clamp-4 text-[13px] leading-6 text-sec"><MdInline text={b.text_md.split('\n').filter((l) => !l.startsWith('>')).map((l) => l.replace(/^\s*-\s+/, '')).join(' ').replace(/[*#`]/g, '').replace(/\s+/g, ' ').trim()} /></p>
          <Button size="sm" variant="secondary" onClick={() => onOpen(b.ref)} className="self-start">خواندن کامل</Button>
        </>
      )}
    </Card>
  );
}

function LetterInner() {
  const router = useRouter();
  const params = useSearchParams();
  const open = params.get('ref');
  const setOpen = (ref: string | null) => router.replace(ref ? `/letter?ref=${ref}` : '/letter', { scroll: false });
  const { data: companies } = useCompanies();
  const settings = useSettings18();
  const [kind, setKind] = useState<BriefingKind | null>(null);
  const [company, setCompany] = useState<string | null>(null);
  const hist = useBriefings({ kind, company });
  const items = hist.data?.pages.flatMap((p) => p.items) ?? [];
  const s = settings.data;
  const operating = (companies ?? []).filter((c) => c.kind !== 'holding');
  return (
    <>
      <PageHeader eyebrow="صدا روی خود هاب ساخته میشود؛ هیچ صدایی از هاب بیرون نمیرود" title="گزارش صوتی و نامه‌ها">
        <p className="max-w-3xl text-[13px] leading-6 text-sec">
          گزارش صبحگاهی همان متن نوشته‌شده است، با صدا. هر شنبه هر مدیرعامل یک نامه‌ی حداکثر ۶۰۰ کلمه‌ای از روی بسته‌ی واقعیت‌هایی که کد میسازد مینویسد؛ عددی که در آن بسته نباشد نامه را یک بار برمیگرداند و بار دوم با برچسب «عدد بی‌منبع» منتشر میشود.
          {s?.audio_briefings ? <> صدای صبح {s.audio_briefings.morning ? 'روشن' : 'خاموش'}، صدای نامه‌ها {s.audio_briefings.ceo_letters ? 'روشن' : 'خاموش'} (<Link href="/settings" className="text-gold-ink">تنظیمات</Link>).</> : null}
        </p>
      </PageHeader>
      <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
        <Morning onOpen={setOpen} />
        <div className="grid items-start gap-3 sm:grid-cols-2 xl:grid-cols-1 2xl:grid-cols-2">{operating.map((c) => <LetterCard key={c.code} company={c.code} onOpen={setOpen} />)}</div>
      </div>
      <Card className="flex flex-col gap-3 p-4">
        <SectionTitle title="همه‌ی گزارش‌ها و نامه‌ها" />
        <div className="flex flex-wrap gap-2">
          <FilterChip selected={!kind} onClick={() => setKind(null)}>همه</FilterChip>
          <FilterChip selected={kind === 'morning'} onClick={() => setKind('morning')}>صبحگاهی</FilterChip>
          <FilterChip selected={kind === 'ceo_letter'} onClick={() => setKind('ceo_letter')}>نامه‌ها</FilterChip>
        </div>
        <ScopeChips value={company} onChange={setCompany} allLabel="همه‌ی شرکت‌ها" />
        {hist.isLoading ? <Skeleton className="h-40" /> : !items.length ? <p className="py-4 text-center text-[13px] text-muted">چیزی نیست.</p> : (
          <ul className="flex flex-col">
            {items.map((b) => {
              const st = AUDIO[b.audio_state] ?? AUDIO.off!;
              return (
                <li key={b.ref}>
                  <button type="button" onClick={() => setOpen(b.ref)} className="flex w-full items-center gap-3 border-b border-div px-1 py-2.5 text-start last:border-0 hover:bg-hover">
                    <span className={cx('flex size-8 flex-none items-center justify-center rounded-full bg-tile', b.kind === 'morning' ? 'text-gold-ink' : 'text-sec')}><Icon name={b.kind === 'morning' ? 'report' : 'messages'} size={16} /></span>
                    <span className="flex min-w-0 flex-1 flex-col">
                      <span className="flex items-center gap-1.5 text-[13px] font-semibold text-ink"><CoMark code={b.company} height={11} />{KIND_FA[b.kind]}</span>
                      <span className="text-[11px] text-muted">{jWeekday(b.created_at)} · <span className="fig">{b.ref}</span></span>
                    </span>
                    <Pill tone={st.tone} dot>{st.fa}</Pill>
                  </button>
                </li>
              );
            })}
          </ul>
        )}
        {hist.hasNextPage ? <Button variant="secondary" size="sm" loading={hist.isFetchingNextPage} onClick={() => hist.fetchNextPage()}>بیشتر</Button> : null}
      </Card>
      {open ? <BriefingSheet refId={open} onClose={() => setOpen(null)} /> : null}
    </>
  );
}

/** گزارش صوتی و نامه‌ی هفتگی (contract §21.4): the morning report with its audio, and each CEO's Saturday letter. */
export default function LetterPage() {
  return <Suspense><LetterInner /></Suspense>;
}
