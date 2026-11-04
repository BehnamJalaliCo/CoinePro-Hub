'use client';

import { PageHeader } from '@/components/ui/primitives';
import { Automations } from '@/components/v31/automations';

/** ⟨1.13⟩ §31.7: an automation from one sentence. */
export default function Page() {
  return (
    <>
      <PageHeader eyebrow="یک جمله بنویس؛ اجرایش کد است، نه مدل" title="اتوماسیون از یک جمله" />
      <Automations />
    </>
  );
}
