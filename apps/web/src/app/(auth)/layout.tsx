import { Monogram, Wordmark } from '@/components/brand/marks';

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative flex min-h-dvh items-center justify-center overflow-hidden px-4 py-10">
      {/* Shamseh rays behind the card: the holding's ceremonial motif, drawn very faint. */}
      <svg aria-hidden className="pointer-events-none absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 opacity-[.07]" width="900" height="900" viewBox="-450 -450 900 900">
        {Array.from({ length: 48 }, (_, i) => (
          <line key={i} x1="0" y1="-120" x2="0" y2={i % 2 ? -330 : -440} stroke="var(--hq-gold-fill)" strokeWidth={i % 2 ? 1 : 1.6} transform={`rotate(${i * 7.5})`} />
        ))}
        <circle r="118" fill="none" stroke="var(--hq-gold-fill)" strokeWidth="1.2" />
      </svg>
      <div className="relative flex w-full max-w-[420px] flex-col items-center gap-8">
        <div className="flex flex-col items-center gap-4">
          <Monogram size={64} />
          <div dir="ltr" className="flex items-end gap-2"><Wordmark width={150} /><span className="fig pb-0.5 text-[16px] font-semibold leading-none tracking-[.08em]">HQ</span></div>
          <span className="text-caption text-muted">ستاد کوینه‌پرو</span>
        </div>
        {children}
      </div>
    </div>
  );
}
