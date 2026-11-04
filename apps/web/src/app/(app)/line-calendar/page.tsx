'use client';

import { PageHeader } from '@/components/ui/primitives';
import { LinesCalendar } from '@/components/v30/calendar';

/** ⟨1.12⟩ §30.5: what every company's lines publish, by day. (`/calendar` is the change calendar of §20.) */
export default function LineCalendarPage() {
  return (
    <>
      <PageHeader eyebrow="چه چیزی کی و کجا منتشر میشود" title="تقویم انتشار" />
      <LinesCalendar />
    </>
  );
}
