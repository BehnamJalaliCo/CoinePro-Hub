'use client';

// ⟨1.10⟩ §28.3 the switch for the panel's error reports to the hub (this browser only), with what was last sent.

import { Card, Pill, SectionTitle, Switch } from '@/components/ui/primitives';
import { setUploads, useUploads } from '@/lib/error-upload';
import { ago } from '@/lib/format';

const fa = (n: number) => n.toLocaleString('fa-IR');

export function ErrorReportsCard() {
  const u = useUploads();
  const status = !u.on ? 'خاموش؛ خطاها فقط در همین مرورگر میمانند.'
    : u.served === false ? `${u.pending ? `${fa(u.pending)} مورد در نوبت؛ ` : ''}با به‌روزرسانی هاب فرستاده میشود.`
    : u.failing ? 'آخرین ارسال نرسید؛ دوباره امتحان میشود.'
    : u.lastAt ? `آخرین ارسال ${ago(u.lastAt)}، ${fa(u.lastCount)} مورد${u.pending ? `؛ ${fa(u.pending)} مورد در نوبت` : ''}.`
    : u.pending ? `${fa(u.pending)} مورد در نوبت ارسال.` : 'چیزی برای ارسال نیست.';
  return (
    <Card className="flex flex-col gap-3 p-5">
      <SectionTitle title="گزارش خطا به هاب" note="خطاها و هشدارهای خطاخوان، پوشانده‌شده، دسته‌ای میروند تا ناظر کل علتشان را در کد پیدا کند." />
      <div className="flex items-center gap-3">
        <span className="flex-1 text-[14px]">{u.on ? 'ارسال روشن است' : 'ارسال خاموش است'}</span>
        <Switch label="ارسال گزارش خطا به هاب" checked={u.on} onChange={setUploads} />
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Pill tone={!u.on ? 'neutral' : u.failing ? 'warn' : u.served === false ? 'neutral' : 'pos'} dot>{u.on ? (u.failing ? 'در انتظار' : 'فعال') : 'خاموش'}</Pill>
        <span className="text-[12px] text-sec">{status}</span>
      </div>
      <p className="text-[11px] leading-5 text-muted">هیچ بدنه‌ی درخواست، توکن، کوکی، داده‌ی passkey یا داده‌ی مشتری فرستاده نمیشود؛ شناسه‌ها، ایمیل‌ها و شماره‌ها پیش از ذخیره پوشانده شده‌اند. هر خطا یک بار میرود، و دوباره فقط اگر باز رخ داده باشد.</p>
    </Card>
  );
}
