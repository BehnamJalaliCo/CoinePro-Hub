'use client';

// ⟨1.8⟩ §26.3: a destructive command on a company server was held for the seal; with the panel open it says so at once, naming the
// server by its company (the owner's rule). Mounted once in the app shell; reads the shell's live feed.

import { useRouter } from 'next/navigation';
import { useEffect, useRef } from 'react';
import { useToast } from '@/components/ui/toast';
import { useCompanies } from '@/lib/api/hooks';
import { companyOf } from '@/lib/company';
import { useLive } from '@/lib/live';

export function ServersWatcher() {
  const router = useRouter();
  const toast = useToast();
  const { feed } = useLive();
  const { data: companies } = useCompanies();
  const seen = useRef(new Set<string>());
  useEffect(() => {
    for (const e of [...feed].reverse()) {
      if (e.type !== 'server.awaiting_seal' || seen.current.has(e.id)) continue;
      seen.current.add(e.id);
      const ref = typeof e.data.decision_ref === 'string' ? e.data.decision_ref : e.ref?.startsWith('D-') ? e.ref : null;
      const co = e.company ? companyOf(companies, e.company).nameFa : 'شرکت';
      toast({ tone: 'info', text: `کار ویرانگر روی سرور ${co} منتظر مُهر توست.`, action: { label: 'ببین', run: () => router.push(ref ? `/cartable?ref=${ref}` : '/cartable') } });
    }
  }, [feed, companies, router, toast]);
  return null;
}
