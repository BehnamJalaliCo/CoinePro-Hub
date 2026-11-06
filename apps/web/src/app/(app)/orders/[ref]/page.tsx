'use client';

import { useRouter } from 'next/navigation';
import { use, useEffect } from 'react';
import { Skeleton } from '@/components/ui/primitives';

/** ⟨1.17⟩ §35: an order's page is its session now; the old address leads there. */
export default function OrderReportPage({ params }: { params: Promise<{ ref: string }> }) {
  const { ref } = use(params);
  const router = useRouter();
  useEffect(() => { router.replace(`/s/${ref}`); }, [ref, router]);
  return <Skeleton className="h-20" />;
}
