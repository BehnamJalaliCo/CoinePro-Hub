'use client';

import { useState } from 'react';
import { PageHeader, Segmented } from '@/components/ui/primitives';
import { CompanyChips } from '@/components/v16/bits';
import { NpsTab, RulesTab, TemplatesTab } from '@/components/v16/growth';
import { useCompanies } from '@/lib/api/hooks';
import { useScope } from '@/lib/scope';

type Tab = 'templates' | 'rules' | 'nps';

/** رشد و پیام‌ها (contract §19.5): rule-sent messages use a sealed template under a sealed rule with limits; sealing the rule is the
 *  owner's A3 approval in advance. Free text from an agent to a customer does not exist. */
export default function GrowthPage() {
  const { company: scope } = useScope();
  const { data: companies } = useCompanies();
  const [picked, setPicked] = useState<string | null | undefined>(undefined);
  const company = picked !== undefined ? picked : companies?.find((c) => c.code === scope)?.kind === 'holding' ? null : scope;
  const [tab, setTab] = useState<Tab>('templates');
  return (
    <>
      <PageHeader eyebrow="فقط قالب مُهرشده زیر قاعده‌ی مُهرشده؛ هیچ متن آزادی از ایجنت به مشتری نمیرسد" title="رشد و پیام‌ها">
        <p className="max-w-3xl text-[13px] leading-6 text-sec">خوش‌آمد، بازگشت، نجات رفرال، NPS و رضایت. هر پیام از نگهبان خروجی، ساعت سکوت تهران، سقف‌ها و قواعد تلگرام میگذرد؛ پیامی که تلگرام اجازه نمیدهد ثبت میشود، نه زور.</p>
      </PageHeader>
      <CompanyChips value={company} onChange={setPicked} />
      <div className="overflow-x-auto pb-1">
        <Segmented<Tab> label="بخش‌های رشد" value={tab} onChange={setTab} options={[{ value: 'templates', label: 'قالب‌ها' }, { value: 'rules', label: 'قاعده‌ها' }, { value: 'nps', label: 'NPS' }]} />
      </div>
      {tab === 'templates' ? <TemplatesTab company={company} /> : tab === 'rules' ? <RulesTab company={company} /> : <NpsTab company={company} />}
    </>
  );
}
