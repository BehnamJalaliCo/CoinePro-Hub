'use client';

// ⟨1.13⟩ Contract §31.3, §31.4 and §31.6, the company's tabs: «خبرنامه» (lists, subscribers, campaigns, a new campaign, schedule),
// «سئو و رقبا» (keywords, a rank chart per keyword, competitors and their daily figures) and «تبلیغات» (accounts, campaigns with spend and
// ROAS, rules, a paused campaign resumed behind the passkey).

import { useMemo, useState } from 'react';
import { LinesChart } from '@/components/charts/charts';
import { Button } from '@/components/ui/button';
import { Card, ErrorState, Pill, SectionTitle, Skeleton, Switch } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import {
  PLATFORM_AD_FA, useAdRules, useAds, useCompetitorDaily, useCompetitors, useCrud, useKeywords, useNewsletter, useNewsletterActions, useRanks, useResumeCampaign,
  type AdPlatform, type AdRule, type Competitor, type Keyword,
} from '@/lib/api/v31';
import { cx, jDateTime, numText, parseNum } from '@/lib/format';
import { FaText, fig } from '@/components/v29/text';
import { errText, field, notYet } from './kit';

const dayLabel = new Intl.DateTimeFormat('fa-IR-u-ca-persian-nu-latn', { day: 'numeric', month: 'short', timeZone: 'Asia/Tehran' });
const COLORS = ['var(--hq-gold-bright)', 'var(--hq-lapis, #5B8DEF)', 'var(--hq-pos, #2BAA6B)', 'var(--hq-warn, #E0A030)', 'var(--hq-neg, #E5586A)', 'var(--hq-learn, #9A74E8)'];
const Loading = () => <Skeleton className="h-48 rounded-[16px]" />;
const Txt = ({ label, value, set, ltr, w }: { label: string; value: string; set: (v: string) => void; ltr?: boolean; w?: string }) => (
  <label className={cx('flex min-w-0 flex-col gap-1.5', w)}><span className="text-[12px] text-sec">{label}</span>
    <input value={value} onChange={(e) => set(e.target.value)} dir={ltr ? 'ltr' : 'auto'} aria-label={label} className={cx(field, 'h-10', ltr && 'text-left')} /></label>
);
/** A number field that keeps the typed text (so "1." and Persian digits survive) and reports null when it is empty. */
function Num({ label, value, set }: { label: string; value: number | null; set: (v: number | null) => void }) {
  const [text, setText] = useState(value == null ? '' : String(value));
  return (
    <label className="flex min-w-0 flex-col gap-1.5"><span className="text-[12px] text-sec">{label}</span>
      <input inputMode="decimal" value={text} dir="ltr" onChange={(e) => { const t = numText(e.target.value); setText(t); set(parseNum(t)); }} aria-label={label} className={cx(field, 'h-10 text-left')} /></label>
  );
}

// ================================================================================================ newsletter ==
const NL_STATE: Record<string, string> = { draft: 'پیش‌نویس', scheduled: 'زمان‌بندی شد', running: 'در حال ارسال', finished: 'فرستاده شد', paused: 'متوقف', cancelled: 'لغو شد' };
export function CompanyNewsletter({ code }: { code: string }) {
  const q = useNewsletter(code);
  const act = useNewsletterActions(code);
  const toast = useToast();
  const [form, setForm] = useState<{ list: string; subject: string; body_md: string } | null>(null);
  const [at, setAt] = useState<Record<string, string>>({});
  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return notYet('send', 'خبرنامه بعد از به‌روزرسانی ستاد میاید', 'لیست‌ها، مشترک‌ها و کمپین‌های ایمیلی این شرکت این‌جا میاید.');
  const { lists, campaigns } = q.data;
  const open = () => setForm({ list: lists[0]?.id ?? '', subject: '', body_md: '' });
  return (
    <div className="flex flex-col gap-4">
      <Card as="section" className="flex flex-col gap-3 p-5" aria-label="لیست‌ها">
        <SectionTitle title="لیست‌ها" note="رضایت مشترک‌ها و لغو عضویت با یک کلیک را خود خبرنامه نگه میدارد" />
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{lists.map((l) => (
          <div key={l.id} className="rounded-[12px] bg-tile p-3"><div className="text-[14px] font-semibold"><FaText text={l.name} /></div>
            <div className="pt-1 text-[12px] text-sec">{l.subscribers != null ? <><span className="fig">{fig(l.subscribers)}</span> مشترک</> : 'تعداد مشترک هنوز خوانده نشده'}</div></div>
        ))}</div>
        {!lists.length ? <p className="text-[13px] text-muted">هنوز لیستی نیست.</p> : null}
      </Card>
      <Card as="section" className="flex flex-col gap-3 p-5" aria-label="کمپین‌های خبرنامه">
        <SectionTitle title="کمپین‌ها" action={<Button size="sm" variant="primary" icon="add" disabled={!lists.length} onClick={open}>کمپین تازه</Button>} />
        {form ? (
          <div className="hq-rise flex flex-col gap-3 rounded-[12px] bg-tile p-4" aria-label="کمپین تازه">
            <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="لیست">{lists.map((l) => (
              <button key={l.id} type="button" role="radio" aria-checked={form.list === l.id} onClick={() => setForm({ ...form, list: l.id })} className={cx('h-9 rounded-full px-3.5 text-[13px] font-semibold', form.list === l.id ? 'bg-gold text-on-gold' : 'bg-card text-sec')}>{l.name}</button>
            ))}</div>
            <Txt label="موضوع ایمیل" value={form.subject} set={(v) => setForm({ ...form, subject: v })} />
            <label className="flex flex-col gap-1.5"><span className="text-[12px] text-sec">متن ایمیل</span>
              <textarea value={form.body_md} onChange={(e) => setForm({ ...form, body_md: e.target.value })} rows={6} dir="auto" aria-label="متن ایمیل" className={cx(field, 'py-2.5 leading-7')} /></label>
            <div className="flex gap-2">
              <Button variant="primary" loading={act.create.isPending} disabled={!form.subject.trim() || !form.body_md.trim()} onClick={() => act.create.mutate({ list_id: form.list || null, subject: form.subject.trim(), body_md: form.body_md }, {
                onSuccess: () => { toast({ tone: 'ok', text: 'کمپین پیش‌نویس ساخته شد.' }); setForm(null); }, onError: (e) => toast({ tone: 'error', text: errText(e, 'ساخته نشد.') }),
              })}>ذخیره پیش‌نویس</Button>
              <Button onClick={() => setForm(null)}>بی‌خیال</Button>
            </div>
          </div>
        ) : null}
        {!campaigns.length ? <p className="text-[13px] text-muted">هنوز کمپینی نیست.</p> : (
          <ul className="flex flex-col">{campaigns.map((c) => (
            <li key={c.id} className="flex flex-wrap items-center gap-3 border-t border-div py-3 first:border-0" aria-label={`کمپین ${c.subject}`}>
              <span className="flex min-w-0 flex-[1_1_12rem] flex-col"><span className="text-[14px] font-semibold"><FaText text={c.subject} /></span>
                <span className="text-[11px] text-muted">{c.send_at ? jDateTime(c.send_at) : 'بدون زمان'}{c.sent != null ? <> · <span className="fig">{fig(c.sent)}</span> ارسال · <span className="fig">{fig(c.opens)}</span> باز · <span className="fig">{fig(c.clicks)}</span> کلیک</> : null}</span></span>
              <Pill tone={c.state === 'finished' ? 'pos' : c.state === 'draft' || c.state === 'cancelled' ? 'silver' : 'gold'} dot>{NL_STATE[c.state] ?? c.state}</Pill>
              {c.state === 'draft' ? (
                <span className="flex items-center gap-2">
                  <input type="datetime-local" value={at[c.id] ?? ''} onChange={(e) => setAt({ ...at, [c.id]: e.target.value })} dir="ltr" aria-label={`زمان ارسال ${c.subject}`} className={cx(field, 'h-9 w-auto text-[12px]')} />
                  <Button size="sm" icon="send" disabled={!at[c.id]} loading={act.schedule.isPending && act.schedule.variables?.id === c.id}
                    onClick={() => act.schedule.mutate({ id: c.id, at: new Date(at[c.id]!).toISOString() }, { onSuccess: () => toast({ tone: 'ok', text: 'زمان‌بندی شد.' }), onError: (e) => toast({ tone: 'error', text: errText(e, 'زمان‌بندی نشد.') }) })}>زمان‌بندی</Button>
                </span>
              ) : null}
            </li>
          ))}</ul>
        )}
      </Card>
    </div>
  );
}

// ==================================================================================================== SEO ==
export function CompanySeo({ code }: { code: string }) {
  const kw = useKeywords(code);
  const ranks = useRanks(code);
  const comps = useCompetitors(code);
  const daily = useCompetitorDaily(code);
  const kwAct = useCrud<Keyword>(code, 'keywords');
  const cAct = useCrud<Competitor>(code, 'competitors');
  const toast = useToast();
  const [k, setK] = useState({ phrase: '', site: '', target_url: '' });
  const [c, setC] = useState<{ id?: string; name_fa: string; site: string; instagram: string; youtube: string; telegram: string }>({ name_fa: '', site: '', instagram: '', youtube: '', telegram: '' });
  const [editC, setEditC] = useState(false);
  const chart = useMemo(() => {
    const rs = ranks.data ?? [];
    const days = [...new Set(rs.map((r) => r.day))].sort();
    const lines = (kw.data ?? []).map((w, i) => ({
      key: w.id, label: w.phrase, color: COLORS[i % COLORS.length]!,
      values: days.map((d) => rs.find((r) => (r.keyword === w.id || r.keyword === w.phrase) && r.day === d)?.position ?? null),
    })).filter((l) => l.values.some((v) => v != null));
    return { days, lines };
  }, [ranks.data, kw.data]);
  const latest = useMemo(() => {
    const m = new Map<string, Map<string, number>>();
    for (const d of [...(daily.data ?? [])].sort((a, b) => a.day.localeCompare(b.day))) { if (!m.has(d.competitor)) m.set(d.competitor, new Map()); m.get(d.competitor)!.set(d.key, d.value); }
    return m;
  }, [daily.data]);
  if (kw.isLoading || comps.isLoading) return <Loading />;
  if (kw.error) return <ErrorState error={kw.error} onRetry={() => kw.refetch()} />;
  if (kw.data === null) return notYet('chart', 'سئو و رقبا بعد از به‌روزرسانی ستاد میاید', 'جایگاه کلیدواژه‌ها در گوگل و عددهای روزانه‌ی رقبا این‌جا میاید.');
  const fail = (m: string) => (e: unknown) => toast({ tone: 'error', text: errText(e, m) });
  return (
    <div className="flex flex-col gap-4">
      <Card as="section" className="flex flex-col gap-3 p-5" aria-label="کلیدواژه‌ها">
        <SectionTitle title="کلیدواژه‌ها" note="جایگاه از سرچ‌کنسول؛ بررسی روزانه‌ی گوگل تقریبی است" />
        <div className="flex flex-wrap items-end gap-2">
          <Txt label="عبارت" value={k.phrase} set={(v) => setK({ ...k, phrase: v })} w="flex-[2_1_10rem]" />
          <Txt label="سایت" value={k.site} set={(v) => setK({ ...k, site: v })} ltr w="flex-[1_1_9rem]" />
          <Txt label="صفحه‌ی هدف (اختیاری)" value={k.target_url} set={(v) => setK({ ...k, target_url: v })} ltr w="flex-[1_1_9rem]" />
          <Button variant="primary" icon="add" disabled={!k.phrase.trim() || !k.site.trim()} loading={kwAct.add.isPending}
            onClick={() => kwAct.add.mutate({ phrase: k.phrase.trim(), site: k.site.trim(), target_url: k.target_url.trim() || null, state: 'on' }, { onSuccess: () => setK({ phrase: '', site: '', target_url: '' }), onError: fail('اضافه نشد.') })}>اضافه کن</Button>
        </div>
        <ul className="flex flex-col">{(kw.data ?? []).map((w) => (
          <li key={w.id} className="flex flex-wrap items-center gap-3 border-t border-div py-2.5 first:border-0" aria-label={`کلیدواژه ${w.phrase}`}>
            <span className="min-w-0 flex-[1_1_10rem] text-[14px] font-semibold"><FaText text={w.phrase} /></span>
            <span dir="ltr" className="text-[12px] text-muted">{w.site}</span>
            <Switch checked={w.state === 'on'} label={`فعال بودن ${w.phrase}`} onChange={(v) => kwAct.edit.mutate({ id: w.id, state: v ? 'on' : 'paused' }, { onError: fail('تغییر نکرد.') })} />
            <Button size="sm" aria-label={`حذف ${w.phrase}`} onClick={() => kwAct.remove.mutate(w.id, { onError: fail('حذف نشد.') })}>حذف</Button>
          </li>
        ))}</ul>
        {chart.lines.length ? (
          <div className="flex flex-col gap-1" aria-label="جایگاه کلیدواژه‌ها">
            <h3 className="text-[13px] font-semibold text-sec">جایگاه در گوگل (عدد کمتر بهتر است)</h3>
            <LinesChart label="جایگاه کلیدواژه‌ها" days={chart.days.map((d) => ({ key: d, label: dayLabel.format(new Date(`${d}T12:00:00Z`)) }))} lines={chart.lines} fmt={(v) => fig(Math.round(v))} height={220} />
          </div>
        ) : null}
      </Card>
      <Card as="section" className="flex flex-col gap-3 p-5" aria-label="رقبا">
        <SectionTitle title="رقبا" note="عددهای عمومی هر روز خوانده میشود؛ پرش بزرگ به مدیر رشد شرکت میرسد"
          action={<Button size="sm" icon="add" onClick={() => { setEditC(true); setC({ name_fa: '', site: '', instagram: '', youtube: '', telegram: '' }); }}>رقیب تازه</Button>} />
        {editC ? (
          <div className="hq-rise grid gap-2 rounded-[12px] bg-tile p-4 sm:grid-cols-2" aria-label="مشخصات رقیب">
            <Txt label="نام رقیب" value={c.name_fa} set={(v) => setC({ ...c, name_fa: v })} />
            <Txt label="سایت" value={c.site} set={(v) => setC({ ...c, site: v })} ltr />
            <Txt label="اینستاگرام" value={c.instagram} set={(v) => setC({ ...c, instagram: v })} ltr />
            <Txt label="یوتیوب" value={c.youtube} set={(v) => setC({ ...c, youtube: v })} ltr />
            <Txt label="تلگرام" value={c.telegram} set={(v) => setC({ ...c, telegram: v })} ltr />
            <div className="flex items-end gap-2">
              <Button variant="primary" disabled={!c.name_fa.trim()} loading={cAct.add.isPending || cAct.edit.isPending} onClick={() => {
                const b = { name_fa: c.name_fa.trim(), site: c.site.trim() || null, instagram: c.instagram.trim() || null, youtube: c.youtube.trim() || null, telegram: c.telegram.trim() || null, state: 'on' as const };
                const done = { onSuccess: () => setEditC(false), onError: fail('ذخیره نشد.') };
                if (c.id) cAct.edit.mutate({ ...b, id: c.id }, done); else cAct.add.mutate(b, done);
              }}>ذخیره</Button>
              <Button onClick={() => setEditC(false)}>بی‌خیال</Button>
            </div>
          </div>
        ) : null}
        {!(comps.data ?? []).length ? <p className="text-[13px] text-muted">هنوز رقیبی نیست.</p> : (
          <div className="overflow-x-auto"><table className="w-full min-w-[520px] border-collapse text-[13px]" aria-label="رقبا و عددهایشان">
            <thead><tr className="text-right text-[11px] text-muted"><th className="px-2 py-2 font-semibold">رقیب</th><th className="px-2 py-2 font-semibold">صفحه‌های تازه</th><th className="px-2 py-2 font-semibold">دنبال‌کننده</th><th className="px-2 py-2 font-semibold">مشترک</th><th className="px-2 py-2 font-semibold">پست</th><th /></tr></thead>
            <tbody>{(comps.data ?? []).map((x) => {
              const f = latest.get(x.id);
              return (
                <tr key={x.id} className="border-t border-div">
                  <td className="px-2 py-2.5 font-semibold"><FaText text={x.name_fa} /></td>
                  {['new_pages', 'followers', 'subscribers', 'posts'].map((key) => <td key={key} className="fig px-2 py-2.5">{f?.has(key) ? fig(f.get(key)) : '—'}</td>)}
                  <td className="px-2 py-2.5"><span className="flex gap-1.5">
                    <Button size="sm" aria-label={`ویرایش ${x.name_fa}`} onClick={() => { setEditC(true); setC({ id: x.id, name_fa: x.name_fa, site: x.site ?? '', instagram: x.instagram ?? '', youtube: x.youtube ?? '', telegram: x.telegram ?? '' }); }}>ویرایش</Button>
                    <Button size="sm" aria-label={`حذف ${x.name_fa}`} onClick={() => cAct.remove.mutate(x.id, { onError: fail('حذف نشد.') })}>حذف</Button></span></td>
                </tr>
              );
            })}</tbody>
          </table></div>
        )}
      </Card>
    </div>
  );
}

// ===================================================================================================== ads ==
type RuleForm = Pick<AdRule, 'platform' | 'scope' | 'daily_cap' | 'window_days' | 'min_roas' | 'min_spend_before_judging' | 'action' | 'state'> & { id?: string };
const RULE0 = (platform: AdPlatform): RuleForm => ({ platform, scope: 'account', daily_cap: null, window_days: 3, min_roas: 1, min_spend_before_judging: 0, action: 'pause', state: 'on' });
const PLATFORMS: AdPlatform[] = ['google_ads', 'meta_ads'];
export function CompanyAds({ code }: { code: string }) {
  const q = useAds(code);
  const rules = useAdRules(code);
  const act = useCrud<AdRule>(code, 'ad-rules');
  const resume = useResumeCampaign();
  const toast = useToast();
  const [r, setR] = useState<RuleForm | null>(null);
  if (q.isLoading) return <Loading />;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return notYet('budget', 'تبلیغات بعد از به‌روزرسانی ستاد میاید', 'حساب‌ها، خرج و بازده هر کمپین و قاعده‌های توقف خودکار این‌جا میاید.');
  const fail = (m: string) => (e: unknown) => toast({ tone: 'error', text: errText(e, m) });
  const { accounts, campaigns } = q.data;
  return (
    <div className="flex flex-col gap-4">
      <Card as="section" className="flex flex-col gap-3 p-5" aria-label="حساب‌های تبلیغاتی">
        <SectionTitle title="حساب‌ها" />
        <div className="flex flex-wrap gap-2">{accounts.map((a) => <Pill key={a.platform} tone={a.state === 'connected' ? 'pos' : 'warn'} dot>{PLATFORM_AD_FA[a.platform] ?? a.platform} · <FaText text={a.label_fa} /></Pill>)}
          {!accounts.length ? <p className="text-[13px] text-muted">حسابی وصل نیست؛ از «اتصال‌ها» وصل کن.</p> : null}</div>
      </Card>
      <Card as="section" className="flex flex-col gap-2 p-5" aria-label="کمپین‌های تبلیغاتی">
        <SectionTitle title="کمپین‌ها" note="خرج و بازده سی روز اخیر؛ ستاد هرگز بودجه را بالا نمیبرد" />
        {!campaigns.length ? <p className="text-[13px] text-muted">کمپینی نیست.</p> : (
          <ul className="flex flex-col">{campaigns.map((c) => (
            <li key={`${c.platform}-${c.campaign_id}`} className="flex flex-wrap items-center gap-3 border-t border-div py-3 first:border-0" aria-label={`کمپین ${c.name}`}>
              <span className="flex min-w-0 flex-[1_1_12rem] flex-col"><span className="text-[14px] font-semibold"><FaText text={c.name} /></span><span className="text-[11px] text-muted">{PLATFORM_AD_FA[c.platform] ?? c.platform}</span></span>
              <span className="text-[12px] text-sec">خرج <span className="fig">{fig(c.totals.spend)}</span></span>
              <span className="text-[12px] text-sec">ROAS <span className="fig">{c.totals.roas != null ? fig(c.totals.roas, 2) : '—'}</span></span>
              <Pill tone={c.status === 'active' ? 'pos' : c.status === 'removed' ? 'silver' : 'warn'} dot>{c.status === 'active' ? 'فعال' : c.status === 'removed' ? 'حذف‌شده' : c.paused_by === 'rule' ? 'متوقف توسط قاعده' : 'متوقف'}</Pill>
              {c.status === 'paused' ? <Button size="sm" variant="primary" icon="resume" loading={resume.isPending && resume.variables?.platform === c.platform && resume.variables?.id === c.campaign_id} aria-label={`ادامه‌ی ${c.name}`}
                onClick={() => resume.mutate({ platform: c.platform, id: c.campaign_id }, { onSuccess: () => toast({ tone: 'ok', text: 'کمپین ادامه یافت.' }), onError: fail('ادامه نیافت.') })}>ادامه</Button> : null}
            </li>
          ))}</ul>
        )}
      </Card>
      <Card as="section" className="flex flex-col gap-3 p-5" aria-label="قاعده‌های تبلیغات">
        <SectionTitle title="قاعده‌های توقف" note="قاعده‌ای که بشکند، کمپین را متوقف میکند (برگشت‌پذیر) و به مدیر رشد خبر میدهد"
          action={<Button size="sm" icon="add" onClick={() => setR(RULE0(accounts[0]?.platform ?? 'google_ads'))}>قاعده‌ی تازه</Button>} />
        {r ? (
          <div key={r.id ?? 'new'} className="hq-rise grid gap-2 rounded-[12px] bg-tile p-4 sm:grid-cols-3" aria-label="مشخصات قاعده">
            <div className="flex flex-col gap-1.5 sm:col-span-3"><span className="text-[12px] text-sec">سکو</span>
              <div className="flex gap-2" role="radiogroup" aria-label="سکوی قاعده">{PLATFORMS.map((p) => (
                <button key={p} type="button" role="radio" aria-checked={r.platform === p} disabled={!!r.id && r.platform !== p} onClick={() => setR({ ...r, platform: p })} className={cx('h-10 rounded-full px-4 text-[13px] font-semibold disabled:opacity-40', r.platform === p ? 'bg-gold text-on-gold' : 'bg-card text-sec')}>{PLATFORM_AD_FA[p]}</button>
              ))}</div></div>
            <Txt label="دامنه (account یا شناسه‌ی کمپین)" value={r.scope} set={(v) => setR({ ...r, scope: v })} ltr />
            <Num label="سقف خرج روزانه (خالی یعنی بی‌سقف)" value={r.daily_cap} set={(v) => setR({ ...r, daily_cap: v || null })} />
            <Num label="بازه (روز)" value={r.window_days} set={(v) => setR({ ...r, window_days: v ?? 0 })} />
            <Num label="کمترین ROAS" value={r.min_roas} set={(v) => setR({ ...r, min_roas: v })} />
            <Num label="حداقل خرج پیش از قضاوت" value={r.min_spend_before_judging} set={(v) => setR({ ...r, min_spend_before_judging: v ?? 0 })} />
            <div className="flex flex-col gap-1.5"><span className="text-[12px] text-sec">کار</span>
              <div className="flex gap-2" role="radiogroup" aria-label="کار قاعده">{(['pause', 'notify'] as const).map((a) => (
                <button key={a} type="button" role="radio" aria-checked={r.action === a} onClick={() => setR({ ...r, action: a })} className={cx('h-10 rounded-full px-4 text-[13px] font-semibold', r.action === a ? 'bg-gold text-on-gold' : 'bg-card text-sec')}>{a === 'pause' ? 'متوقف کن' : 'خبر بده'}</button>
              ))}</div></div>
            <div className="flex gap-2 sm:col-span-3">
              <Button variant="primary" loading={act.add.isPending || act.edit.isPending} disabled={!r.scope.trim() || (r.daily_cap == null && r.min_roas == null) || r.window_days < 1} onClick={() => {
                const done = { onSuccess: () => setR(null), onError: fail('ذخیره نشد.') };
                if (r.id) act.edit.mutate({ ...r, id: r.id }, done); else act.add.mutate(r, done);
              }}>ذخیره</Button>
              <Button onClick={() => setR(null)}>بی‌خیال</Button>
            </div>
          </div>
        ) : null}
        {(rules.data ?? []).length ? (
          <ul className="flex flex-col">{(rules.data ?? []).map((x) => (
            <li key={x.id} className="flex flex-wrap items-center gap-3 border-t border-div py-3 first:border-0" aria-label={`قاعده ${x.scope}`}>
              <span className="min-w-0 flex-[1_1_14rem] text-[13px] leading-6"><span dir="ltr">{x.scope}</span>: {x.daily_cap != null ? <>سقف روزانه <span className="fig">{fig(x.daily_cap)}</span>{x.min_roas != null ? '، ' : ' '}</> : null}{x.min_roas != null ? <>ROAS زیر <span className="fig">{fig(x.min_roas, 2)}</span> </> : null}در <span className="fig">{x.window_days}</span> روز، بعد از <span className="fig">{fig(x.min_spend_before_judging)}</span> خرج، {x.action === 'pause' ? 'متوقف کن' : 'خبر بده'}</span>
              <Switch checked={x.state === 'on'} label={`روشن بودن قاعده‌ی ${x.scope}`} onChange={(v) => act.edit.mutate({ id: x.id, state: v ? 'on' : 'off' }, { onError: fail('تغییر نکرد.') })} />
              <Button size="sm" onClick={() => setR({ id: x.id, platform: x.platform, scope: x.scope, daily_cap: x.daily_cap, window_days: x.window_days, min_roas: x.min_roas, min_spend_before_judging: x.min_spend_before_judging, action: x.action, state: x.state })}>ویرایش</Button>
              <Button size="sm" aria-label={`حذف قاعده‌ی ${x.scope}`} onClick={() => act.remove.mutate(x.id, { onError: fail('حذف نشد.') })}>حذف</Button>
            </li>
          ))}</ul>
        ) : <p className="text-[13px] text-muted">قاعده‌ای نیست.</p>}
        <p className="text-[11px] text-muted">بالا بردن سقف خرج مُهر میخواهد.</p>
      </Card>
    </div>
  );
}
