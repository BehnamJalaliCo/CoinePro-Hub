'use client';

import { useState } from 'react';
import { Icon } from '@/components/icon';
import { HiringCard } from '@/components/v14/hiring';
import { Button } from '@/components/ui/button';
import { Card, PageHeader, Pill, SectionTitle, Segmented, Skeleton, Switch } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { api, ok, ApiError } from '@/lib/api/client';
import { useDevices, useMeta, useOwnerSettings, usePresence, useSetKhalvat } from '@/lib/api/hooks';
import { deviceName, enrol, signOut, stepUp } from '@/lib/auth';
import { useTheme, type ThemeChoice } from '@/lib/theme';
import { ago, cx } from '@/lib/format';
import { useQueryClient } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';

export default function SettingsPage() {
  const [theme, setTheme] = useTheme();
  const devices = useDevices();
  const meta = useMeta();
  const settings = useOwnerSettings();
  const { data: presence } = usePresence();
  const khalvat = useSetKhalvat();
  const toast = useToast();
  const qc = useQueryClient();
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const passkeys = (devices.data?.items ?? []).filter((d) => d.kind === 'passkey' && !d.revoked_at);

  const addDevice = async () => {
    setBusy('add');
    try {
      const token = await stepUp('passkey.register', 'self');
      await enrol({ name: deviceName(), stepUpToken: token });
      toast({ tone: 'ok', text: 'این دستگاه هم ثبت شد.' });
      void qc.invalidateQueries({ queryKey: ['devices'] });
    } catch (e) { toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'ثبت نشد.' }); }
    finally { setBusy(null); }
  };
  const revoke = async (id: string) => {
    setBusy(id);
    try {
      const token = await stepUp('device.revoke', id);
      await ok(api.POST('/api/v1/auth/devices/{device_id}/revoke', { params: { path: { device_id: id } }, headers: { 'X-Step-Up': token } }));
      void qc.invalidateQueries({ queryKey: ['devices'] });
      toast({ tone: 'info', text: 'باطل شد.' });
    } catch (e) { toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'انجام نشد.' }); }
    finally { setBusy(null); }
  };

  return (
    <>
      <PageHeader title="تنظیمات" />
      <div className="grid items-start gap-4 lg:grid-cols-2">
        <div className="flex flex-col gap-4">
          <Card className="flex flex-col gap-4 p-5">
            <SectionTitle title="دستگاه‌ها و passkeyها" note="بدون رمز؛ دست‌کم دو دستگاه ثبت کن تا اگر یکی گم شد بیرون نمانی." />
            {passkeys.length < 2 && devices.data ? <p className="flex items-center gap-2 rounded-[12px] bg-warn-soft p-3 text-[13px]"><Icon name="urgent" size={18} />فقط یک passkey داری؛ یک دستگاه دوم ثبت کن.</p> : null}
            {devices.isLoading ? <Skeleton className="h-28" /> : (devices.data?.items ?? []).map((d) => (
              <div key={d.id} className="flex items-center gap-3 rounded-[12px] bg-tile p-3">
                <span className="text-sec"><Icon name={d.kind === 'passkey' ? 'lock' : 'server'} size={20} /></span>
                <div className="flex min-w-0 flex-1 flex-col"><span className="fig truncate text-[14px]">{d.name}</span><span className="text-[11px] text-muted">{d.kind === 'passkey' ? 'passkey' : 'نشست'}، آخرین استفاده {ago(d.last_used_at)}</span></div>
                {d.current ? <Pill tone="gold">همین دستگاه</Pill> : d.revoked_at ? <Pill tone="neutral">باطل</Pill> : <Button variant="danger" size="sm" loading={busy === d.id} onClick={() => revoke(d.id)}>باطل کن</Button>}
              </div>
            ))}
            <div className="flex flex-wrap gap-2">
              <Button variant="secondary" icon="add" loading={busy === 'add'} onClick={addDevice}>ثبت همین دستگاه به‌عنوان passkey تازه</Button>
              <Button variant="ghost" icon="back" onClick={async () => { await signOut().catch(() => {}); qc.clear(); router.replace('/login'); }}>خروج</Button>
            </div>
          </Card>
          <HiringCard />
        </div>
        <div className="flex flex-col gap-4">
          <Card className="flex flex-col gap-4 p-5">
            <SectionTitle title="نما" />
            <Segmented<ThemeChoice> label="تم" value={theme} onChange={setTheme} options={[{ value: 'night', label: 'شب' }, { value: 'day', label: 'روز' }, { value: 'system', label: 'مثل سیستم' }]} />
          </Card>
          <Card className="flex flex-col gap-4 p-5">
            <SectionTitle title="خلوت" note="وقتی روشن است فقط 🔴 فوری میرسد؛ بقیه برای «در نبودت چه گذشت» میمانند." />
            <div className="flex items-center gap-3"><span className="flex-1 text-[14px]">{presence?.khalvat ? 'خلوت روشن است' : 'خلوت خاموش است'}</span><Switch label="خلوت" checked={!!presence?.khalvat} onChange={(v) => khalvat.mutate(v)} /></div>
          </Card>
          <Card className="flex flex-col gap-3 p-5">
            <SectionTitle title="ریتم و اعلان" note="از سرور" />
            {settings.data ? (
              <dl className="grid grid-cols-2 gap-3 text-[13px]">
                <div className="flex flex-col"><dt className="text-[11px] text-muted">گزارش صبحگاهی</dt><dd className="fig">{settings.data.morning_report_at}</dd></div>
                <div className="flex flex-col"><dt className="text-[11px] text-muted">بسته‌ی اعلان‌ها</dt><dd>هر {settings.data.digest_minutes} دقیقه</dd></div>
                <div className="flex flex-col"><dt className="text-[11px] text-muted">سهمیه‌ی توجه هر مدیرعامل</dt><dd>{settings.data.ceo_daily_attention} در روز</dd></div>
                <div className="flex flex-col"><dt className="text-[11px] text-muted">منطقه‌ی زمانی</dt><dd className="fig">{settings.data.timezone}</dd></div>
              </dl>
            ) : <Skeleton className="h-20" />}
            <div className="flex flex-wrap gap-2 pt-1">
              {meta.data ? Object.entries(meta.data.channels).map(([k, on]) => <Pill key={k} tone={on ? 'pos' : 'neutral'} dot><span className={cx(k !== 'in_app' && 'fig')}>{k === 'in_app' ? 'داخل اپ' : k === 'web_push' ? 'Web Push' : k === 'fcm' ? 'Android (FCM)' : 'Telegram'}</span></Pill>) : null}
            </div>
          </Card>
        </div>
      </div>
    </>
  );
}
