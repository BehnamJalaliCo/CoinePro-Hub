'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useEffect, useState } from 'react';
import { Icon } from '@/components/icon';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/primitives';
import { ApiError, isMock } from '@/lib/api/client';
import { useMeta } from '@/lib/api/hooks';
import { passkeysSupported, signIn } from '@/lib/auth';

function LoginInner() {
  const router = useRouter();
  const params = useSearchParams();
  const meta = useMeta();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [supported, setSupported] = useState(true);
  useEffect(() => setSupported(passkeysSupported()), []);

  const next = params.get('next');
  const target = next && next.startsWith('/') && !next.startsWith('//') ? next : '/';

  const go = async () => {
    setBusy(true);
    setErr(null);
    try {
      await signIn();
      router.replace(target);
    } catch (e) {
      setErr(e instanceof ApiError ? e.messageFa : 'ورود انجام نشد.');
      setBusy(false);
    }
  };

  const notConfigured = meta.data && !meta.data.login_configured && !isMock;
  return (
    <Card className="tahrir flex w-full flex-col gap-5 p-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-h2 font-semibold">ورود مدیر کل</h1>
        <p className="text-caption text-sec">بدون رمز: با اثر انگشت یا چهره روی دستگاهی که قبلاً ثبت کرده‌ای.</p>
      </div>
      {!supported ? (
        <p role="alert" className="rounded-[12px] bg-warn-soft p-3 text-[13px] text-ink">این مرورگر passkey را پشتیبانی نمیکند. از Chrome، Safari یا Edge به‌روز استفاده کن.</p>
      ) : notConfigured ? (
        <p role="alert" className="rounded-[12px] bg-warn-soft p-3 text-[13px] text-ink">ورود هنوز روی سرور روشن نیست (دامنه تنظیم نشده).</p>
      ) : null}
      <Button variant="primary" size="lg" icon="lock" onClick={go} loading={busy} disabled={!supported || !!notConfigured} className="w-full">ورود با passkey</Button>
      {err ? <p role="alert" className="flex items-start gap-2 text-[13px] text-neg"><Icon name="urgent" size={18} />{err}</p> : null}
      <details className="text-[12px] leading-5 text-muted">
        <summary className="cursor-pointer text-sec">اولین بار است یا همه‌ی دستگاه‌ها را گم کرده‌ای؟</summary>
        <p className="pt-2">روی سرور هاب، در ترمینال SSH خودت، <span className="fig text-ink">make owner-enroll</span> را اجرا کن. یک لینک یک‌بار مصرف ۱۵ دقیقه‌ای فقط در همان ترمینال نشان داده میشود؛ با آن، این دستگاه را ثبت کن.</p>
      </details>
    </Card>
  );
}

export default function LoginPage() {
  return <Suspense><LoginInner /></Suspense>;
}
