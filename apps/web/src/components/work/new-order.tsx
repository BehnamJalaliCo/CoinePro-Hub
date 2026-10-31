'use client';

import { useRouter } from 'next/navigation';
import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Sheet } from '@/components/ui/overlay';
import { FilterChip } from '@/components/ui/primitives';
import { CompanyMark } from '@/components/brand/marks';
import { useToast } from '@/components/ui/toast';
import { ApiError } from '@/lib/api/client';
import { useCompanies, useCreateWork, useDepartments } from '@/lib/api/hooks';
import { DEFAULT_PRIORITY } from '@/lib/priority';
import { PriorityPicker } from '@/components/v21/priority';
import { PlayerPicker } from '@/components/work/player';
import { optionOf, type PlayerOption } from '@/lib/players';
import { OWNER_TZ, cx, jTime, jWeekday } from '@/lib/format';

type Prio = 'P0' | 'P1' | 'P2' | 'P3' | 'P4';

/** Tehran has kept +03:30 all year since 2022: a wall-clock time there as an instant. */
const tehranIso = (local: string) => new Date(`${local}:00+03:30`).toISOString();
/** A quick deadline: the day [days] ahead in Tehran, at 18:00 there, as the input's `YYYY-MM-DDTHH:mm`. */
function dueIn(days: number): string {
  const d = new Date(Date.now() + days * 86_400_000);
  const day = new Intl.DateTimeFormat('en-CA', { timeZone: OWNER_TZ, year: 'numeric', month: '2-digit', day: '2-digit' }).format(d);
  return `${day}T18:00`;
}

/** The owner's order (OPERATING_MODEL §1.4): to a company's CEO, or straight to a department manager; ⟨1.9⟩ with who plays it. */
export function NewOrder({ open, onOpenChange, company: initial }: { open: boolean; onOpenChange: (v: boolean) => void; company?: string | null }) {
  const { data: companies } = useCompanies();
  const [company, setCompany] = useState<string | null>(initial ?? null);
  const deps = useDepartments(company);
  const [dept, setDept] = useState<string | null>(null);
  const [title, setTitle] = useState('');
  const [brief, setBrief] = useState('');
  const [priority, setPriority] = useState<Prio>(DEFAULT_PRIORITY as Prio);
  const [due, setDue] = useState('');
  // ⟨1.9⟩ §27.1: who plays it (the router by default), or the council of models; a council can make images or a video instead of words.
  const [player, setPlayer] = useState<PlayerOption>(optionOf('auto'));
  const [media, setMedia] = useState<'image' | 'video' | null>(null);
  const create = useCreateWork();
  const router = useRouter();
  const qc = useQueryClient();
  const toast = useToast();
  const ok = company && title.trim().length >= 3;
  const field = 'rounded-[10px] border border-strong bg-tile px-3 text-[15px] text-ink outline-none focus:border-gold-ink';
  const submit = async () => {
    if (!company) return;
    try {
      const body = {
        company, department: dept, title: title.trim(), brief: brief.trim(), priority, kind: 'one_off' as const, due_at: due ? tehranIso(due) : null,
        player: player.player, mode: player.mode, media: player.key === 'council' ? media : null,
      };
      const out = await create.mutateAsync(body as Parameters<typeof create.mutateAsync>[0]);
      const o = out as { ref?: string; id?: string };
      // 0.4.0: the order is followed from here on («فرمان‌های من»).
      toast({ tone: 'ok', text: <>فرمان ثبت شد: <span className="fig">{o.ref ?? ''}</span>. {dept ? 'مدیر دپارتمان' : 'مدیرعامل'} بیدار شد.</>, action: o.id ? { label: 'پیگیری', run: () => router.push(`/work/${o.id}`) } : undefined });
      void qc.invalidateQueries({ queryKey: ['work', 'orders'] });
      onOpenChange(false);
      setTitle(''); setBrief(''); setDept(null); setPlayer(optionOf('auto')); setMedia(null); setDue('');
    } catch (e) {
      toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'ثبت نشد.' });
    }
  };
  return (
    <Sheet open={open} onOpenChange={onOpenChange} title="فرمان تازه" description="به مدیرعامل شرکت؛ اگر کار روشن است، مستقیم به مدیر همان دپارتمان." width={520}
      footer={<Button variant="primary" icon="send" className="w-full" disabled={!ok} loading={create.isPending} onClick={submit}>بفرست</Button>}>
      <div className="flex flex-col gap-5">
        <fieldset className="flex flex-col gap-2">
          <legend className="pb-2 text-[13px] text-sec">شرکت</legend>
          <div className="flex flex-wrap gap-2">
            {(companies ?? []).map((c) => (
              <FilterChip key={c.code} selected={company === c.code} onClick={() => { setCompany(c.code); setDept(null); }}>
                <span className="flex items-center gap-1.5"><CompanyMark code={c.code} height={13} mono />{c.name_fa}</span>
              </FilterChip>
            ))}
          </div>
        </fieldset>
        {company && deps.data?.length ? (
          <fieldset className="flex flex-col gap-2">
            <legend className="pb-2 text-[13px] text-sec">دپارتمان (اختیاری؛ میانبر به مدیر)</legend>
            <div className="flex flex-wrap gap-2">
              <FilterChip selected={!dept} onClick={() => setDept(null)}>مدیرعامل تصمیم بگیرد</FilterChip>
              {deps.data.map((d) => <FilterChip key={d.code} selected={dept === d.code} onClick={() => setDept(d.code)}>{d.name_fa}</FilterChip>)}
            </div>
          </fieldset>
        ) : null}
        <label className="flex flex-col gap-1.5"><span className="text-[13px] text-sec">چه کاری؟</span><input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} className={cx(field, 'h-12')} placeholder="مثلاً: علت کندی ثبت‌نام را پیدا کن و راه‌حل بده" /></label>
        <label className="flex flex-col gap-1.5"><span className="text-[13px] text-sec">توضیح و معیار تمام شدن</span><textarea value={brief} onChange={(e) => setBrief(e.target.value)} rows={4} maxLength={10000} className={cx(field, 'py-3 leading-7')} /></label>
        {/* 0.4.0: priorities in words; the chosen one's meaning in one line beneath. */}
        <fieldset className="flex flex-col gap-2">
          <legend className="pb-2 text-[13px] text-sec">اولویت</legend>
          <PriorityPicker value={priority} onChange={(c) => setPriority(c as Prio)} />
        </fieldset>
        <PlayerPicker value={player} onChange={setPlayer} />
        {player.key === 'council' ? (
          <fieldset className="flex flex-col gap-2">
            <legend className="pb-2 text-[13px] text-sec">شورا چه بسازد؟</legend>
            <div className="flex flex-wrap gap-2">
              <FilterChip selected={!media} onClick={() => setMedia(null)}>نوشته</FilterChip>
              <FilterChip selected={media === 'image'} onClick={() => setMedia('image')}>عکس</FilterChip>
              <FilterChip selected={media === 'video'} onClick={() => setMedia('video')}>ویدیو</FilterChip>
            </div>
            {media ? <span className="text-[12px] text-muted">هر بازیکنی که میتواند، نسخه‌ی خودش را میسازد؛ یکی را تو انتخاب میکنی.</span> : null}
          </fieldset>
        ) : null}
        {/* The deadline in the owner's calendar and zone: quick choices, or a day and hour read as Tehran time and said back in Jalali. */}
        <fieldset className="flex flex-col gap-2">
          <legend className="pb-2 text-[13px] text-sec">موعد (اختیاری)</legend>
          <div className="flex flex-wrap gap-2">
            <FilterChip selected={!due} onClick={() => setDue('')}>بی‌موعد</FilterChip>
            {([[0, 'امروز'], [1, 'فردا'], [3, 'سه روز دیگر'], [7, 'یک هفته']] as const).map(([d, l]) => <FilterChip key={d} selected={due === dueIn(d)} onClick={() => setDue(dueIn(d))}>{l}</FilterChip>)}
          </div>
          <label className="flex flex-wrap items-center gap-2"><span className="text-[12px] text-muted">یا روز و ساعت دیگر، به وقت تهران:</span><input type="datetime-local" aria-label="موعد به وقت تهران" value={due} onChange={(e) => setDue(e.target.value)} className={cx(field, 'fig h-10')} /></label>
          {due ? <span className="text-[12px] text-sec">موعد: {jWeekday(tehranIso(due))}، ساعت {jTime(tehranIso(due))} به وقت تهران</span> : null}
        </fieldset>
      </div>
    </Sheet>
  );
}
