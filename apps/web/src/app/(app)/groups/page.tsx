'use client';

import { PageHeader } from '@/components/ui/primitives';
import { GroupsList } from '@/components/v29/groups';

/** ⟨1.11⟩ §29.11: the working groups, each a fixed team with daily routines, real KPIs and a weekly experiment. */
export default function GroupsPage() {
  return (
    <>
      <PageHeader eyebrow="تیم ثابت، روال روزانه، عدد واقعی، آزمایش هفتگی" title="کارگروه‌ها" />
      <GroupsList />
    </>
  );
}
