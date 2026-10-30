'use client';

import { useRouter } from 'next/navigation';

/** A ref in agent text that opens its own page (0.5.0, the ref router). A span with the link role, not an anchor: agent text also sits
 *  inside rows that are links or buttons themselves, where a nested anchor is not valid. */
export function RefLink({ refId, href }: { refId: string; href: string }) {
  const router = useRouter();
  const go = (e: React.SyntheticEvent) => { e.preventDefault(); e.stopPropagation(); router.push(href); };
  return (
    <span role="link" tabIndex={0} title={href} onClick={go} onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') go(e); }}
      className="fig cursor-pointer whitespace-nowrap text-gold-ink underline-offset-2 hover:underline focus-visible:underline focus-visible:outline-none">
      {refId}
    </span>
  );
}
