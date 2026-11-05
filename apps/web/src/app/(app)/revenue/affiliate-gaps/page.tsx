'use client';

import Link from 'next/link';
import { PageHeader } from '@/components/ui/primitives';
import { AffiliateGaps } from '@/components/v33/sales';
import { useCompanies } from '@/lib/api/hooks';
import { useScope } from '@/lib/scope';

/** ⟨1.15⟩ §33.5: the affiliate commission due against received, per account and month. */
export default function Page() {
  const { company: scope } = useScope();
  const { data: companies } = useCompanies();
  const company = companies?.find((c) => c.code === scope)?.kind === 'holding' ? null : scope;
  return (
    <>
      <PageHeader eyebrow={<Link href="/revenue" className="hover:text-ink">درآمد ← پیگیری افیلیت</Link>} title="طلب و دریافت کمیسیون" />
      <AffiliateGaps company={company} />
    </>
  );
}
