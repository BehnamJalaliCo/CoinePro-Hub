'use client';

import { use } from 'react';
import { OrderReportView } from '@/components/v29/report';

/** ⟨1.11⟩ §29.2: one order's report, live. */
export default function OrderReportPage({ params }: { params: Promise<{ ref: string }> }) {
  const { ref } = use(params);
  return <OrderReportView refId={decodeURIComponent(ref)} />;
}
