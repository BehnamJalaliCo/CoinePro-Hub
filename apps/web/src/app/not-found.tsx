import Link from 'next/link';
import { Monogram } from '@/components/brand/marks';

export default function NotFound() {
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center gap-4 px-6 text-center">
      <Monogram size={48} />
      <h1 className="text-h2 font-semibold">این صفحه پیدا نشد</h1>
      <Link href="/" className="text-[14px] font-semibold text-gold-ink">برگشت به فرمان</Link>
    </div>
  );
}
