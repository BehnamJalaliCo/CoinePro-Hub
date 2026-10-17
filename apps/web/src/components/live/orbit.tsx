'use client';

import Link from 'next/link';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Seal } from '@/components/brand/seal';
import { CompanyMark } from '@/components/brand/marks';
import type { Company } from '@/lib/company';
import type { StreamEvent } from '@/lib/stream';
import { cx } from '@/lib/format';

type Pulse = { id: number; company: string; dir: 'out' | 'in' };

/** The holding orbit (D2·2 live stream): the holding seal at the centre, every company on the ring,
 *  gold particles = the owner's orders going out, silver = agents' deliveries coming back.
 *  Data-driven: any number of companies; past a ring's capacity the ring shrinks node size. */
export function Orbit({ companies, lastEvent, size = 520 }: { companies: Company[]; lastEvent?: StreamEvent | null; size?: number }) {
  const ring = useMemo(() => companies.filter((c) => c.kind !== 'holding'), [companies]);
  const holding = companies.find((c) => c.kind === 'holding');
  const [pulses, setPulses] = useState<Pulse[]>([]);
  const seq = useRef(0);

  useEffect(() => {
    if (!lastEvent?.company || lastEvent.company === holding?.code) return;
    const dir: Pulse['dir'] = /delegated|created/.test(lastEvent.type) && lastEvent.type.startsWith('work') ? 'out' : 'in';
    const id = ++seq.current;
    setPulses((p) => [...p.slice(-10), { id, company: lastEvent.company!, dir }]);
    const t = setTimeout(() => setPulses((p) => p.filter((x) => x.id !== id)), 1800);
    return () => clearTimeout(t);
  }, [lastEvent, holding?.code]);

  const c = size / 2;
  const R = size * 0.38;
  const node = Math.max(44, Math.min(76, (2 * Math.PI * R) / Math.max(ring.length, 1) / 2.2));
  const pos = (i: number) => {
    const a = -Math.PI / 2 + (2 * Math.PI * i) / Math.max(ring.length, 1);
    return { x: c + R * Math.cos(a), y: c + R * Math.sin(a) };
  };

  return (
    <div className="relative mx-auto aspect-square w-full" style={{ maxWidth: size }}>
      <svg viewBox={`0 0 ${size} ${size}`} className="absolute inset-0 size-full" aria-hidden>
        <circle cx={c} cy={c} r={R} fill="none" stroke="var(--hq-line-tahrir)" strokeWidth={1} strokeDasharray="2 6" />
        <circle cx={c} cy={c} r={R * 0.52} fill="none" stroke="var(--hq-line-divider)" strokeWidth={1} />
        {ring.map((co, i) => {
          const p = pos(i);
          return <line key={co.code} x1={c} y1={c} x2={p.x} y2={p.y} stroke="var(--hq-line-divider)" strokeWidth={1} />;
        })}
        {pulses.map((pl) => {
          const i = ring.findIndex((r) => r.code === pl.company);
          if (i < 0) return null;
          const p = pos(i);
          const [x1, y1, x2, y2] = pl.dir === 'out' ? [c, c, p.x, p.y] : [p.x, p.y, c, c];
          return (
            <circle key={pl.id} r={4} fill={pl.dir === 'out' ? 'var(--hq-gold-fill)' : 'var(--hq-silver-ink)'}>
              <animate attributeName="cx" from={x1} to={x2} dur="1.6s" fill="freeze" />
              <animate attributeName="cy" from={y1} to={y2} dur="1.6s" fill="freeze" />
              <animate attributeName="opacity" values="0;1;1;0" dur="1.6s" fill="freeze" />
            </circle>
          );
        })}
      </svg>
      <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2">
        <Seal code={holding?.code ?? 'HQ'} nameFa={holding?.name_fa ?? 'هلدینگ'} nameEn={holding?.name_en ?? 'Holding'} holding size={Math.round(size * 0.27)} />
      </div>
      {ring.map((co, i) => {
        const p = pos(i);
        const active = pulses.some((x) => x.company === co.code);
        const locked = co.kill_switch === 'engaged';
        return (
          <Link
            key={co.code}
            href={`/companies/${co.code}`}
            className="group absolute flex -translate-x-1/2 -translate-y-1/2 flex-col items-center gap-1.5"
            style={{ left: `${(p.x / size) * 100}%`, top: `${(p.y / size) * 100}%` }}
            aria-label={`${co.name_fa}: ${co.counts.work_open} کار باز، ${co.counts.decisions_pending} تصمیم منتظر`}
          >
            <span
              className={cx('relative flex items-center justify-center rounded-full border bg-tile transition-transform duration-200 group-hover:scale-105', locked ? 'border-neg' : 'border-strong')}
              style={{ width: node, height: node }}
            >
              {active ? <span className="absolute inset-[-5px] rounded-full border-2 border-ink" style={{ animation: 'hq-ring 1.6s ease-out infinite' }} /> : null}
              <span className="text-ink"><CompanyMark code={co.code} height={Math.round(node * 0.42)} /></span>
              {co.counts.decisions_pending > 0 ? (
                <span className="absolute -right-1 -top-1 inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-gold px-1 text-[11px] font-bold text-on-gold">{co.counts.decisions_pending}</span>
              ) : null}
            </span>
            <span className="whitespace-nowrap text-[12px] font-semibold text-ink">{co.name_fa}</span>
            <span className="whitespace-nowrap text-[11px] text-muted">{co.counts.work_open} کار باز</span>
          </Link>
        );
      })}
    </div>
  );
}
