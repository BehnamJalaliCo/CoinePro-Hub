'use client';

import { PageHeader } from '@/components/ui/primitives';
import { NotificationsView } from '@/components/v21/notifications';

/** «اعلان‌ها» (0.5.0; contract §6): urgent reaches the owner wherever they are; the rest wait here, unread or read, repeats folded. */
export default function NotificationsPage() {
  return (
    <>
      <PageHeader eyebrow="فوری هر جا باشی میرسد؛ بقیه این‌جا منتظر میمانند" title="اعلان‌ها" />
      <div className="max-w-3xl"><NotificationsView /></div>
    </>
  );
}
