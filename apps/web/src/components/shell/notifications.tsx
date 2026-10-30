'use client';

import Link from 'next/link';
import { Sheet } from '@/components/ui/overlay';
import { NotificationsView } from '@/components/v21/notifications';

/** The bell (0.5.0): unread and read, the same alert raised again and again folded into one row with its count, each labelled by what it
 *  is about, opening its own page through the ref router. The whole page is «اعلان‌ها». */
export function NotificationsSheet({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange} title="اعلان‌ها" description="فوری هر جا باشی میرسد؛ بقیه این‌جا منتظر میمانند." width={460}
      footer={<Link href="/notifications" onClick={() => onOpenChange(false)} className="text-[13px] font-semibold text-gold-ink hover:underline">همه‌ی اعلان‌ها در یک صفحه</Link>}>
      {open ? <NotificationsView compact onNavigate={() => onOpenChange(false)} /> : null}
    </Sheet>
  );
}
