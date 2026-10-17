'use client';

import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { Icon } from '@/components/icon';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/primitives';
import { ApiError } from '@/lib/api/client';
import { deviceName, enrol, passkeysSupported, signIn } from '@/lib/auth';

/** One-time enrolment from the link `make owner-enroll` prints (…/enroll#token=…). The token lives in the
 *  URL fragment, so it never reaches a server log; we remove it from the address bar at once. */
export default function EnrollPage() {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [name, setName] = useState('');
  const [state, setState] = useState<'idle' | 'busy' | 'done'>('idle');
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    const m = /token=([^&]+)/.exec(window.location.hash);
    if (m?.[1]) setToken(decodeURIComponent(m[1]));
    history.replaceState(null, '', window.location.pathname);
    setName(deviceName());
  }, []);

  const go = async () => {
    if (!token) return;
    setState('busy');
    setErr(null);
    try {
      await enrol({ enrolmentToken: token, name: name.trim() || deviceName() });
      await signIn();
      setState('done');
    } catch (e) {
      setErr(e instanceof ApiError ? e.messageFa : 'ثبت انجام نشد.');
      setState('idle');
    }
  };

  if (state === 'done') {
    return (
      <Card className="tahrir flex w-full flex-col items-center gap-4 p-6 text-center">
        <span className="flex size-14 items-center justify-center rounded-full bg-gold-soft text-gold-ink"><Icon name="seal" size={28} active /></span>
        <h1 className="text-h2 font-semibold">این دستگاه ثبت شد</h1>
        <p className="text-[13px] leading-6 text-sec">پیشنهاد جدی: یک دستگاه دوم (گوشی یا کامپیوتر دیگر) هم از «تنظیمات › دستگاه‌ها» ثبت کن تا اگر یکی گم شد، بیرون نمانی.</p>
        <Button variant="primary" size="lg" className="w-full" onClick={() => router.replace('/')}>ورود به ستاد</Button>
      </Card>
    );
  }

  return (
    <Card className="tahrir flex w-full flex-col gap-5 p-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-h2 font-semibold">ثبت passkey</h1>
        <p className="text-caption text-sec">این لینک یک‌بار مصرف است و ۱۵ دقیقه اعتبار دارد.</p>
      </div>
      {!token ? (
        <p role="alert" className="rounded-[12px] bg-warn-soft p-3 text-[13px] text-ink">لینک ثبت کامل نیست. دوباره <span className="fig">make owner-enroll</span> را روی سرور اجرا کن و لینک تازه را باز کن.</p>
      ) : !passkeysSupported() ? (
        <p role="alert" className="rounded-[12px] bg-warn-soft p-3 text-[13px] text-ink">این مرورگر passkey را پشتیبانی نمیکند.</p>
      ) : (
        <>
          <label className="flex flex-col gap-1.5">
            <span className="text-[13px] text-sec">نام این دستگاه</span>
            <input value={name} onChange={(e) => setName(e.target.value)} maxLength={100} className="h-12 rounded-[10px] border border-strong bg-tile px-3 text-[15px] text-ink outline-none focus:border-gold-ink" />
          </label>
          <Button variant="primary" size="lg" icon="lock" onClick={go} loading={state === 'busy'} className="w-full">ثبت با اثر انگشت یا چهره</Button>
        </>
      )}
      {err ? <p role="alert" className="flex items-start gap-2 text-[13px] text-neg"><Icon name="urgent" size={18} />{err}</p> : null}
    </Card>
  );
}
