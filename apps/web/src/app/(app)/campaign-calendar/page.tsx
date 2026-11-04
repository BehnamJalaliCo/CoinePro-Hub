'use client';

import { PageHeader } from '@/components/ui/primitives';
import { CampaignCalendar } from '@/components/v31/campaigns';

/** ⟨1.13⟩ §31.5: one calendar. (`/calendar` is the change calendar of §20.) */
export default function Page() {
  return (
    <>
      <PageHeader eyebrow="خط‌ها، خبرنامه، تبلیغ و کمپین‌ها با تداخل‌هایشان" title="تقویم کمپین" />
      <CampaignCalendar />
    </>
  );
}
