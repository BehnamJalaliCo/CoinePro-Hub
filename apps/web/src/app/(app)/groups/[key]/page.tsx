'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, use } from 'react';
import { GroupDetail } from '@/components/v29/groups';

function Inner({ groupKey }: { groupKey: string }) {
  const router = useRouter();
  const search = useSearchParams();
  const company = search.get('company');
  return (
    <GroupDetail groupKey={groupKey} company={company}
      onCompany={(c) => router.replace(`/groups/${encodeURIComponent(groupKey)}${c ? `?company=${encodeURIComponent(c)}` : ''}`, { scroll: false })} />
  );
}

/** ⟨1.11⟩ §29.11: one working group. */
export default function GroupPage({ params }: { params: Promise<{ key: string }> }) {
  const { key } = use(params);
  return <Suspense><Inner groupKey={decodeURIComponent(key)} /></Suspense>;
}
