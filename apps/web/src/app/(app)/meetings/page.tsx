'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { FilterChip, PageHeader, Segmented } from '@/components/ui/primitives';
import { MEETING_TYPE, ScopeChips } from '@/components/v17/bits';
import { MeetingList, MeetingSettings, NewMeetingSheet } from '@/components/v17/meetings';
import type { MeetingTypeKey } from '@/lib/api/v17';
import { useScope } from '@/lib/scope';

const TYPES: MeetingTypeKey[] = ['board', 'company', 'strategy', 'war_room', 'postmortem', 'standup'];

/** اتاق جلسه (contract §20.1): meetings run by code under a budget the owner sees beforehand; resolutions only by the owner's seal. */
export default function MeetingsPage() {
  const { company: scope } = useScope();
  const [picked, setPicked] = useState<string | null | undefined>(undefined);
  const company = picked !== undefined ? picked : scope;
  const [tab, setTab] = useState<'list' | 'settings'>('list');
  const [type, setType] = useState<MeetingTypeKey | null>(null);
  const [create, setCreate] = useState(false);
  return (
    <>
      <PageHeader eyebrow="جلسه را کد اداره میکند؛ مصوبه فقط با مُهر تو" title="اتاق جلسه"
        actions={<Button variant="primary" icon="add" onClick={() => setCreate(true)}>جلسه‌ی تازه</Button>}>
        <p className="max-w-3xl text-[13px] leading-6 text-sec">حداکثر دو دور و چند سخنگوی مشخص در هر دستور، بودجه‌ی توکن جدا که پیش از شروع جلوی توست، هر ادعا با منبع و مخالف‌خوان از نظارت. مشاور کل در جلسه فقط با تو نجوا میکند و تو هر وقت بخواهی با صدا یا متن وارد میشوی.</p>
      </PageHeader>
      <div className="w-full max-w-xs"><Segmented label="بخش" value={tab} onChange={setTab} options={[{ value: 'list', label: 'جلسه‌ها' }, { value: 'settings', label: 'تنظیمات' }]} /></div>
      {tab === 'list' ? (
        <>
          <div className="flex flex-col gap-2">
            <ScopeChips value={company} onChange={setPicked} allLabel="همه‌ی جلسه‌ها" />
            <div className="flex flex-wrap gap-2"><FilterChip selected={!type} onClick={() => setType(null)}>همه‌ی نوع‌ها</FilterChip>{TYPES.map((t) => <FilterChip key={t} selected={type === t} onClick={() => setType(t)}>{MEETING_TYPE[t]!.fa}</FilterChip>)}</div>
          </div>
          <MeetingList type={type} company={company} />
        </>
      ) : <MeetingSettings />}
      {create ? <NewMeetingSheet onClose={() => setCreate(false)} /> : null}
    </>
  );
}
