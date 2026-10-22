'use client';

import Link from 'next/link';
import { useState, type ReactNode } from 'react';
import { Icon } from '@/components/icon';
import { Button } from '@/components/ui/button';
import { Card, SectionTitle, Segmented, Skeleton, Switch } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { WEEKDAY_FA } from '@/components/v17/bits';
import { faError, useDigitalCeo, useSaveSettings18, useSettings18, type ManagementSettings, type SettingsPatch } from '@/lib/api/v18';
import { cx } from '@/lib/format';

const KEYS = ['advisor', 'weekly_review', 'audio_briefings', 'ceo_weekly_letter', 'reminders', 'digital_ceo', 'substitutes'] as const;
const DAYS = ['sa', 'su', 'mo', 'tu', 'we', 'th', 'fr'];
const num = 'fig h-9 w-16 rounded-[8px] border border-strong bg-card px-2 text-center text-[13px] text-ink outline-none focus:border-gold-ink';

function Row({ label, note, children }: { label: string; note?: ReactNode; children: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2">
      <div className="flex min-w-0 flex-[1_1_12rem] flex-col"><span className="text-[13px] text-ink">{label}</span>{note ? <span className="text-[11px] text-muted">{note}</span> : null}</div>
      <div className="flex flex-none items-center gap-2">{children}</div>
    </div>
  );
}

/** «ابزار مدیریت» in the settings (§21.12): every switch the owner may change, saved as a partial body with the version. */
export function ManagementSettingsCard() {
  const q = useSettings18();
  const save = useSaveSettings18();
  const dceo = useDigitalCeo();
  const toast = useToast();
  const base = q.data;
  const [draft, setDraft] = useState<ManagementSettings | null>(null);
  const loaded = base && KEYS.every((k) => base[k] != null);
  const d: ManagementSettings | null = draft ?? (loaded ? (Object.fromEntries(KEYS.map((k) => [k, base[k]])) as unknown as ManagementSettings) : null);
  if (q.isLoading) return <Card className="p-5"><Skeleton className="h-40" /></Card>;
  if (!d || !base) return null;
  const set = <K extends keyof ManagementSettings>(k: K, v: Partial<ManagementSettings[K]>) => setDraft({ ...d, [k]: { ...d[k], ...v } });
  const patch: SettingsPatch = Object.fromEntries(KEYS.filter((k) => JSON.stringify(d[k]) !== JSON.stringify(base[k])).map((k) => [k, d[k]]));
  const dirty = Object.keys(patch).length > 0;
  const hidden = dceo.data?.hidden ?? 0;
  const submit = async () => { try { await save.mutateAsync({ version: base.version, patch }); setDraft(null); toast({ tone: 'ok', text: 'تنظیمات ابزار مدیریت ذخیره شد.' }); } catch (e) { toast({ tone: 'error', text: faError(e) }); } };
  return (
    <Card className="flex flex-col gap-2 p-5">
      <SectionTitle title="ابزار مدیریت" note="یادداشت خودکار، مرور هفتگی، گزارش صوتی، یادآوری، مدیر کل دیجیتال و بازیکن‌های ذخیره" />
      <div className="flex flex-col divide-y divide-div">
        <Row label="یادداشت خودکار مشاور" note="کارت پرریسک، انتشار، تأسیس و طرح سرور">
          <input aria-label="سقف روزانه‌ی یادداشت خودکار" value={d.advisor.auto_memo.max_per_day} onChange={(e) => set('advisor', { auto_memo: { ...d.advisor.auto_memo, max_per_day: Number(e.target.value.replace(/\D/g, '') || 0) } })} inputMode="numeric" className={num} />
          <span className="text-[11px] text-muted">در روز</span>
          <Switch label="یادداشت خودکار مشاور" checked={d.advisor.auto_memo.enabled} onChange={(v) => set('advisor', { auto_memo: { ...d.advisor.auto_memo, enabled: v } })} />
        </Row>
        <Row label="گزارش فعال مشاور" note="هرگز فوری؛ بالای سقف ثبت میشود و نمیرود">
          <input aria-label="سقف گزارش فعال" value={d.advisor.proactive_per_day} onChange={(e) => set('advisor', { proactive_per_day: Number(e.target.value.replace(/\D/g, '') || 0) })} inputMode="numeric" className={num} /><span className="text-[11px] text-muted">در روز</span>
        </Row>
        <Row label="مرور هفتگی با مشاور" note="دستور ۳۰ دقیقه پیش‌تر با کد ساخته میشود">
          <select aria-label="روز مرور" value={d.weekly_review.day} onChange={(e) => set('weekly_review', { day: e.target.value })} className="h-9 rounded-[8px] border border-strong bg-card px-2 text-[13px] text-ink">{DAYS.map((x) => <option key={x} value={x}>{WEEKDAY_FA[x.toUpperCase()]}</option>)}</select>
          <input aria-label="ساعت مرور" type="time" value={d.weekly_review.at} onChange={(e) => set('weekly_review', { at: e.target.value })} dir="ltr" className="fig h-9 rounded-[8px] border border-strong bg-card px-2 text-[13px] text-ink" />
          <Switch label="مرور هفتگی" checked={d.weekly_review.enabled} onChange={(v) => set('weekly_review', { enabled: v })} />
        </Row>
        <Row label="گزارش صبحگاهی صوتی" note="Piper روی خود هاب؛ هیچ صدایی بیرون نمیرود"><Switch label="گزارش صبحگاهی صوتی" checked={d.audio_briefings.morning} onChange={(v) => set('audio_briefings', { morning: v })} /></Row>
        <Row label="نامه‌ی هفتگی مدیرعامل‌ها" note={<>شنبه‌ها؛ نسخه‌ی صوتی جدا <Link href="/letter" className="text-gold-ink">نامه‌ها</Link></>}>
          <span className="text-[11px] text-muted">صدا</span><Switch label="صدای نامه‌ها" checked={d.audio_briefings.ceo_letters} onChange={(v) => set('audio_briefings', { ceo_letters: v })} />
          <span className="text-[11px] text-muted">نامه</span><Switch label="نامه‌ی هفتگی" checked={d.ceo_weekly_letter.enabled} onChange={(v) => set('ceo_weekly_letter', { enabled: v })} />
        </Row>
        <Row label="یادآوری کارتابل" note="نیمه‌ی زمان و ۶ ساعت پیش از انقضا؛ بی‌انقضا در ۲۴ و ۷۲ ساعت و ۷ روز"><Switch label="یادآوری کارتابل" checked={d.reminders.enabled} onChange={(v) => set('reminders', { enabled: v })} /></Row>
        <Row label="مدیر کل دیجیتال" note={<>فقط پیش‌بینی؛ <Link href="/digital-ceo" className="text-gold-ink">دقت و اصول</Link></>}>
          <div className="w-60"><Segmented label="زمان نمایش پیش‌بینی" value={d.digital_ceo.reveal} onChange={(v) => set('digital_ceo', { reveal: v })} options={[{ value: 'after', label: 'بعد از تصمیم' }, { value: 'before', label: 'پیش از تصمیم' }]} /></div>
          <Switch label="مدیر کل دیجیتال" checked={d.digital_ceo.enabled} onChange={(v) => set('digital_ceo', { enabled: v })} />
        </Row>
        {d.digital_ceo.reveal === 'before' && hidden < 30 ? <p className="flex items-start gap-2 rounded-[10px] bg-warn-soft p-2.5 text-[12px] leading-5 text-ink"><Icon name="urgent" size={14} className="mt-0.5 text-warn" />دقت هنوز سنجیده نشده: فقط {hidden} پیش‌بینی پنهان داریم (دست‌کم ۳۰ لازم است). پیش‌بینی‌هایی که پیش از تصمیم ببینی در دقت «تمیز» شمرده نمیشوند.</p> : null}
        <Row label="بازیکن‌های ذخیره" note="اگر روز ۱۵ ماه ارزش مصرف زیر این نسبت باشد، پیشنهاد باز کردن جایگاه میاید؛ خودبه‌خود باز نمیشود">
          <input aria-label="نسبت عقب ماندن" value={d.substitutes.behind_ratio} onChange={(e) => set('substitutes', { behind_ratio: Math.min(1, Math.max(0, Number(e.target.value) || 0)) })} inputMode="decimal" className={num} />
          <div className="w-44"><Segmented label="بازیکن پیش‌فرض عکس" value={d.substitutes.creative_default_image} onChange={(v) => set('substitutes', { creative_default_image: v })} options={[{ value: 'gpt', label: 'ChatGPT' }, { value: 'gemini', label: 'Gemini' }]} /></div>
        </Row>
      </div>
      <div className={cx('flex flex-wrap gap-2 pt-1', !dirty && 'opacity-80')}>
        <Button variant="primary" disabled={!dirty} loading={save.isPending} onClick={submit}>ذخیره‌ی ابزار مدیریت</Button>
        {dirty ? <Button variant="ghost" onClick={() => setDraft(null)}>برگرداندن</Button> : null}
      </div>
    </Card>
  );
}
