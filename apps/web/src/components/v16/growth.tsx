'use client';

import Link from 'next/link';
import { useState } from 'react';
import { Icon } from '@/components/icon';
import { CompanyMark } from '@/components/brand/marks';
import { StackedBar } from '@/components/charts/charts';
import { Button } from '@/components/ui/button';
import { Dialog, Sheet } from '@/components/ui/overlay';
import { Card, Empty, ErrorState, FilterChip, Pill, Skeleton } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import {
  faError, useChannels, useGrowthAction, useIntakeSources, useNps, useRules, useTemplates,
  type LifecycleRule, type LifecycleRuleIn, type NpsWave, type RuleKind, type Template, type TemplatePurpose,
} from '@/lib/api/v16';
import { cx, jDate, until } from '@/lib/format';
import { useNow } from '@/lib/store';
import { CHANNEL_FA, CompanyChips, Fact, PURPOSE_FA, RULE_STATUS, TEMPLATE_STATUS, rate, triggerFa } from './bits';

const field = 'w-full rounded-[10px] border border-strong bg-card px-3 text-[14px] text-ink outline-none focus:border-gold-ink';

/** A template body with its variables marked, so the owner sees exactly what will be sent and what is filled in. */
function Body({ text, className }: { text: string; className?: string }) {
  return (
    <p className={cx('whitespace-pre-wrap break-words text-[14px] leading-7 text-ink', className)}>
      {text.split(/(\{\{\s*\w+\s*\}\})/).map((x, i) => (i % 2 ? <span key={i} className="fig mx-0.5 rounded-[6px] bg-gold-soft px-1.5 text-[12px] text-gold-ink">{x}</span> : x))}
    </p>
  );
}

// --------------------------------------------------------------- templates --
const PURPOSES: TemplatePurpose[] = ['holding_reply', 'safety', 'welcome', 'reactivation', 'rescue', 'nps', 'csat'];

function TemplateSheet({ company: initial, from, onClose }: { company: string | null; from: Template | null; onClose: () => void }) {
  const act = useGrowthAction();
  const toast = useToast();
  const [company, setCompany] = useState<string | null>(from?.company ?? initial);
  const [purpose, setPurpose] = useState<TemplatePurpose>(from?.purpose ?? 'holding_reply');
  const [body, setBody] = useState(from?.body_fa ?? '');
  const variables = [...new Set([...body.matchAll(/\{\{\s*(\w+)\s*\}\}/g)].map((m) => m[1]!))];
  const valid = !!company && body.trim().length >= 10;
  const save = () => act.proposeTemplate.mutateAsync({ company: company!, purpose, body_fa: body.trim(), variables, ...(from ? { ref: from.ref } : {}) })
    .then((t) => { toast({ tone: 'ok', text: <>قالب <span className="fig">{t.ref}@{t.version}</span> ثبت شد؛ تا مُهر تو هیچ قاعده‌ای با آن نمیفرستد.</> }); onClose(); })
    .catch((e) => toast({ tone: 'error', text: faError(e) }));
  return (
    <Sheet open onOpenChange={(o) => !o && onClose()} title={from ? <>نسخه‌ی تازه‌ی <span className="fig">{from.ref}</span></> : 'قالب تازه'} description="فقط همین متن با همین متغیرها فرستاده میشود؛ نسخه‌ی تازه قاعده‌اش را تا مُهر نگه میدارد." width={560}
      footer={<Button variant="primary" icon="send" className="w-full" disabled={!valid} loading={act.proposeTemplate.isPending} onClick={save}>ثبت برای مُهر</Button>}>
      <div className="flex flex-col gap-4 text-[13px]">
        {!from ? <div className="flex flex-col gap-1.5"><span className="font-semibold text-sec">شرکت</span><CompanyChips value={company} onChange={setCompany} all={false} /></div> : null}
        {!from ? <div className="flex flex-col gap-1.5"><span className="font-semibold text-sec">کاربرد</span><div className="flex flex-wrap gap-2">{PURPOSES.map((x) => <FilterChip key={x} selected={purpose === x} onClick={() => setPurpose(x)}>{PURPOSE_FA[x]}</FilterChip>)}</div></div> : null}
        <label className="flex flex-col gap-1.5 font-semibold text-sec">متن<textarea value={body} onChange={(e) => setBody(e.target.value)} rows={7} maxLength={1500} className={cx(field, 'py-2 leading-7')} placeholder="متغیرها با {{name}}؛ برای لغو «لغو» بفرستید" /></label>
        {variables.length ? <p className="text-[12px] text-sec">متغیرها: {variables.map((v) => <span key={v} className="fig me-2">{`{{${v}}}`}</span>)}</p> : null}
        <p className="rounded-[12px] bg-tile p-3 text-[12px] leading-6 text-sec">جمله‌ی ایمنی خودکار به هر پیام چرخه‌ی عمر اضافه میشود. لینک و کد فقط از دانشنامه‌ی تأییدشده؛ نگهبان خروجی بقیه را رد میکند.</p>
      </div>
    </Sheet>
  );
}

export function TemplatesTab({ company }: { company: string | null }) {
  const q = useTemplates(company);
  const act = useGrowthAction();
  const toast = useToast();
  const [seal, setSeal] = useState<Template | null>(null);
  const [edit, setEdit] = useState<Template | 'new' | null>(null);
  const list = [...(q.data ?? [])].sort((a, b) => Number(b.status === 'proposed') - Number(a.status === 'proposed') || a.company.localeCompare(b.company) || a.ref.localeCompare(b.ref));
  return (
    <div className="flex flex-col gap-3">
      <div className="flex justify-end"><Button variant="primary" size="sm" icon="add" onClick={() => setEdit('new')}>قالب تازه</Button></div>
      {q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : q.isLoading ? <Skeleton className="h-48" /> : !list.length ? <Empty icon="send" title="قالبی نیست" /> : (
        <div className="grid items-start gap-3 md:grid-cols-2">
          {list.map((t) => (
            <Card key={`${t.ref}@${t.version}`} className={cx('flex min-w-0 flex-col gap-2 p-4', t.status === 'proposed' && 'bg-gold-soft', t.status === 'retired' && 'opacity-60')}>
              <div className="flex items-center gap-2"><CompanyMark code={t.company} height={13} mono /><span className="min-w-0 flex-1 truncate text-[14px] font-semibold">{PURPOSE_FA[t.purpose] ?? t.purpose}</span><span className="fig text-[11px] text-muted">{t.ref}@{t.version}</span><Pill tone={TEMPLATE_STATUS[t.status]?.tone ?? 'neutral'} dot>{TEMPLATE_STATUS[t.status]?.fa ?? t.status}</Pill></div>
              <Body text={t.body_fa} className="rounded-[12px] bg-tile p-3 text-[13px]" />
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted">
                {t.sha256 ? <span className="fig">sha256 {t.sha256.slice(0, 10)}…</span> : null}
                {t.sealed_at ? <span>مُهر {jDate(t.sealed_at)}</span> : null}
                <span className="flex-1" />
                {t.status === 'proposed' ? <Button size="sm" variant="primary" icon="seal" onClick={() => setSeal(t)}>مُهر</Button> : null}
                {t.status === 'sealed' ? <Button size="sm" variant="ghost" icon="edit" onClick={() => setEdit(t)}>نسخه‌ی تازه</Button> : null}
              </div>
            </Card>
          ))}
        </div>
      )}
      {seal ? (
        <Dialog open onOpenChange={(o) => !o && setSeal(null)} title={<>مُهر قالب <span className="fig">{seal.ref}@{seal.version}</span></>} actions={<>
          <Button variant="primary" icon="seal" loading={act.sealTemplate.isPending} onClick={() => act.sealTemplate.mutateAsync(seal).then(() => { toast({ tone: 'ok', text: 'مُهر شد؛ قاعده‌هایی که با همین نسخه‌اند میتوانند بفرستند.' }); setSeal(null); }).catch((e) => toast({ tone: 'error', text: faError(e) }))}>مُهر با passkey</Button>
          <Button variant="secondary" onClick={() => setSeal(null)}>انصراف</Button>
        </>}>
          <div className="flex flex-col gap-2">
            <span>دقیقاً همین متن فرستاده میشود:</span>
            <Body text={seal.body_fa} className="max-h-60 overflow-y-auto rounded-[12px] bg-tile p-3" />
            <span className="text-[11px] text-muted">مُهر به همین متن بسته است (<span className="fig">{seal.ref}@{seal.version}:{seal.sha256.slice(0, 12)}…</span>) و برای متن هم‌شکل شرکت دیگر به کار نمیرود.</span>
          </div>
        </Dialog>
      ) : null}
      {edit ? <TemplateSheet company={company} from={edit === 'new' ? null : edit} onClose={() => setEdit(null)} /> : null}
    </div>
  );
}

// ------------------------------------------------------------------- rules --
const KINDS: RuleKind[] = ['welcome', 'reactivation', 'rescue', 'nps', 'csat'];
const EVENT_OF: Partial<Record<RuleKind, 'signup' | 'referral_failed' | 'conversation_closed'>> = { welcome: 'signup', rescue: 'referral_failed', csat: 'conversation_closed' };
const QUARTERLY = 'FREQ=MONTHLY;INTERVAL=3;BYMONTHDAY=1;BYHOUR=11';

function RuleSheet({ company: initial, onClose }: { company: string | null; onClose: () => void }) {
  const act = useGrowthAction();
  const toast = useToast();
  const [company, setCompany] = useState<string | null>(initial);
  const [kind, setKind] = useState<RuleKind>('csat');
  const tq = useTemplates(company);
  const cq = useChannels(company);
  const [template, setTemplate] = useState('');
  const [channel, setChannel] = useState('');
  const [hours, setHours] = useState('1');
  const [inactive, setInactive] = useState('30');
  const [per, setPer] = useState('30');
  const [cap, setCap] = useState('100');
  const [quiet, setQuiet] = useState<[string, string]>(['22:00', '09:00']);
  const [follow, setFollow] = useState('2');
  const templates = (tq.data ?? []).filter((t) => t.purpose === kind && t.status !== 'retired');
  const channels = (cq.data ?? []).filter((c) => c.kind !== 'mystery');
  const n = (s: string) => Math.max(0, Math.round(Number(s) || 0));
  const body: LifecycleRuleIn | null = company && template && channel ? {
    company, kind, template, channel: channel as LifecycleRuleIn['channel'],
    trigger: kind === 'nps' ? { rrule: QUARTERLY } : kind === 'reactivation' ? { inactive_days: n(inactive) } : { event: EVENT_OF[kind]!, after_hours: n(hours) },
    limits: { per_customer_days: n(per), daily_cap: n(cap), quiet_hours: quiet, max_follow_ups: kind === 'rescue' ? n(follow) : 0 },
  } : null;
  const valid = !!body && body.limits.daily_cap > 0 && body.limits.per_customer_days > 0;
  const num = (label: string, v: string, set: (s: string) => void) => <label className="flex flex-col gap-1.5 font-semibold text-sec">{label}<input value={v} onChange={(e) => set(e.target.value)} inputMode="numeric" dir="ltr" className={cx(field, 'fig h-10 text-center')} /></label>;
  return (
    <Sheet open onOpenChange={(o) => !o && onClose()} title="قاعده‌ی تازه" description="پیشنهادی ساخته میشود؛ با مُهر تو (passkey) و فقط وقتی قالبِ همان نسخه مُهرشده است فعال میشود." width={560}
      footer={<Button variant="primary" icon="add" className="w-full" disabled={!valid} loading={act.createRule.isPending} onClick={() => body && act.createRule.mutateAsync(body).then((r) => { toast({ tone: 'ok', text: <>قاعده‌ی <span className="fig">{r.ref}</span> ثبت شد؛ برای فعال شدن مُهرش کن.</> }); onClose(); }).catch((e) => toast({ tone: 'error', text: faError(e) }))}>ثبت قاعده</Button>}>
      <div className="flex flex-col gap-4 text-[13px]">
        <div className="flex flex-col gap-1.5"><span className="font-semibold text-sec">شرکت</span><CompanyChips value={company} onChange={(c) => { setCompany(c); setTemplate(''); setChannel(''); }} all={false} /></div>
        <div className="flex flex-col gap-1.5"><span className="font-semibold text-sec">نوع</span><div className="flex flex-wrap gap-2">{KINDS.map((k) => <FilterChip key={k} selected={kind === k} onClick={() => { setKind(k); setTemplate(''); }}>{PURPOSE_FA[k]}</FilterChip>)}</div></div>
        {kind === 'nps' ? <p className="rounded-[12px] bg-tile p-3 text-[12px] text-sec">فصلی، روز اول؛ نمونه‌ی تصادفی از مشتری‌هایی که در ۹۰ روز گذشته گفت‌وگو داشته‌اند.</p>
          : kind === 'reactivation' ? num('بعد از چند روز بی‌فعالیتی', inactive, setInactive) : num(`چند ساعت بعد از «${EVENT_OF[kind] === 'signup' ? 'ثبت‌نام' : EVENT_OF[kind] === 'referral_failed' ? 'رفرال ناموفق' : 'بسته شدن گفت‌وگو'}»`, hours, setHours)}
        <label className="flex flex-col gap-1.5 font-semibold text-sec">قالب
          <select value={template} onChange={(e) => setTemplate(e.target.value)} className={cx(field, 'h-10')}>
            <option value="">{company ? (templates.length ? 'انتخاب کن' : 'قالبی با این کاربرد نیست') : 'اول شرکت'}</option>
            {templates.map((t) => <option key={`${t.ref}@${t.version}`} value={`${t.ref}@${t.version}`}>{t.ref}@{t.version} · {TEMPLATE_STATUS[t.status]?.fa}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1.5 font-semibold text-sec">کانال
          <select value={channel} onChange={(e) => setChannel(e.target.value)} className={cx(field, 'h-10')}>
            <option value="">انتخاب کن</option>
            {channels.map((c) => <option key={c.kind} value={c.kind}>{CHANNEL_FA[c.kind]}</option>)}
          </select>
        </label>
        <div className="grid grid-cols-2 gap-3">
          {num('هر مشتری یک بار در (روز)', per, setPer)}
          {num('سقف روزانه', cap, setCap)}
          <label className="flex flex-col gap-1.5 font-semibold text-sec">سکوت از<input type="time" value={quiet[0]} onChange={(e) => setQuiet([e.target.value, quiet[1]])} dir="ltr" className={cx(field, 'fig h-10')} /></label>
          <label className="flex flex-col gap-1.5 font-semibold text-sec">تا<input type="time" value={quiet[1]} onChange={(e) => setQuiet([quiet[0], e.target.value])} dir="ltr" className={cx(field, 'fig h-10')} /></label>
          {kind === 'rescue' ? num('حداکثر پیگیری', follow, setFollow) : null}
        </div>
        <p className="text-[12px] leading-6 text-muted">ساعت سکوت به وقت تهران. «لغو»، «stop» یا «نمیخواهم» همه‌ی قاعده‌های این شرکت را برای آن مشتری برای همیشه قطع میکند.</p>
      </div>
    </Sheet>
  );
}

export function RulesTab({ company }: { company: string | null }) {
  const q = useRules(company);
  const templates = useTemplates(company);
  const intake = useIntakeSources();
  const act = useGrowthAction();
  const toast = useToast();
  const [neu, setNew] = useState(false);
  const err = (e: unknown) => toast({ tone: 'error', text: faError(e) });
  const tmpl = (ref: string) => { const [r, v] = ref.split('@'); return templates.data?.find((t) => t.ref === r && String(t.version) === v); };
  // welcome and reactivation wait for product events (CR-009/010): without a configured product intake they have no candidates.
  const noProduct = (r: LifecycleRule) => (r.kind === 'welcome' || r.kind === 'reactivation') && intake.data != null && !intake.data.some((s) => s.company === r.company && s.kind === 'product' && s.configured);
  const list = [...(q.data ?? [])].sort((a, b) => Number(b.status === 'proposed') - Number(a.status === 'proposed') || a.company.localeCompare(b.company) || a.ref.localeCompare(b.ref));
  return (
    <div className="flex flex-col gap-3">
      <div className="flex justify-end"><Button variant="primary" size="sm" icon="add" onClick={() => setNew(true)}>قاعده‌ی تازه</Button></div>
      {q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : q.isLoading ? <Skeleton className="h-48" /> : !list.length ? <Empty icon="time" title="قاعده‌ای نیست" /> : (
        <div className="grid items-start gap-3 md:grid-cols-2">
          {list.map((r) => {
            const t = tmpl(r.template);
            return (
              <Card key={`${r.ref}@${r.version}`} className={cx('flex min-w-0 flex-col gap-3 p-4', r.status === 'proposed' && 'bg-gold-soft')}>
                <div className="flex items-center gap-2"><CompanyMark code={r.company} height={13} mono /><span className="min-w-0 flex-1 truncate text-[14px] font-semibold">{PURPOSE_FA[r.kind] ?? r.kind}</span><span className="fig text-[11px] text-muted">{r.ref}@{r.version}</span><Pill tone={RULE_STATUS[r.status]?.tone ?? 'neutral'} dot>{RULE_STATUS[r.status]?.fa ?? r.status}</Pill></div>
                <div className="grid grid-cols-2 gap-2">
                  <Fact label="کی">{triggerFa(r.trigger)}</Fact>
                  <Fact label="کانال">{CHANNEL_FA[r.channel] ?? r.channel}</Fact>
                  <Fact label="قالب"><span className="flex flex-wrap items-center gap-1.5"><span className="fig">{r.template}</span>{t ? <span className={cx('text-[11px] font-normal', t.status === 'sealed' ? 'text-pos' : 'text-warn')}>{TEMPLATE_STATUS[t.status]?.fa}</span> : null}</span></Fact>
                  <Fact label="۳۰ روز گذشته">{r.sent_30d} فرستاده، {r.opt_outs_30d} لغو</Fact>
                </div>
                <p className="text-[12px] leading-6 text-sec">هر مشتری یک بار در {r.limits.per_customer_days} روز · سقف روزانه <span className="fig">{r.limits.daily_cap}</span> · سکوت <span className="fig">{r.limits.quiet_hours[0]}–{r.limits.quiet_hours[1]}</span>{r.limits.max_follow_ups ? <> · حداکثر {r.limits.max_follow_ups} پیگیری</> : null}</p>
                {noProduct(r) ? <p className="flex items-start gap-2 rounded-[10px] bg-tile p-2.5 text-[12px] leading-6 text-sec"><Icon name="info" size={14} className="mt-1 flex-none" /><span>تا رویداد ثبت‌نام و فعالیت از محصول نرسد (<span className="fig">CR-009/010</span>)، این قاعده هیچ کاندیدی ندارد.</span></p> : null}
                {r.status !== 'active' && t && t.status !== 'sealed' ? <p className="text-[12px] text-warn">قالب این نسخه هنوز مُهر نشده؛ اول قالب، بعد قاعده.</p> : null}
                <div className="flex flex-wrap items-center gap-2">
                  {r.decision_ref ? <Link href={`/cartable?ref=${r.decision_ref}`} className="fig text-[11px] text-gold-ink">{r.decision_ref}</Link> : null}
                  <span className="flex-1" />
                  {r.status === 'proposed' ? <Button size="sm" variant="primary" icon="seal" loading={act.sealRule.isPending && act.sealRule.variables?.ref === r.ref} onClick={() => act.sealRule.mutateAsync(r).then(() => toast({ tone: 'ok', text: 'مُهر شد و فعال است.' })).catch(err)}>مُهر و فعال</Button> : null}
                  {r.status === 'active' ? <Button size="sm" variant="danger" icon="pause" loading={act.pauseRule.isPending && act.pauseRule.variables === r.ref} onClick={() => act.pauseRule.mutateAsync(r.ref).then(() => toast({ tone: 'info', text: 'متوقف شد.' })).catch(err)}>توقف</Button> : null}
                  {r.status === 'paused' ? <Button size="sm" variant="primary" icon="resume" loading={act.resumeRule.isPending && act.resumeRule.variables?.ref === r.ref} onClick={() => act.resumeRule.mutateAsync(r).then(() => toast({ tone: 'ok', text: 'دوباره فعال شد.' })).catch(err)}>ادامه با passkey</Button> : null}
                </div>
              </Card>
            );
          })}
        </div>
      )}
      {neu ? <RuleSheet company={company} onClose={() => setNew(false)} /> : null}
    </div>
  );
}

// --------------------------------------------------------------------- NPS --
/** −100..100 on one track: the bar grows from zero towards the score. */
function NpsTrack({ score }: { score: number }) {
  const s = Math.max(-100, Math.min(100, score));
  return (
    <div className="relative h-2 rounded-full bg-tile" dir="ltr" role="img" aria-label={`امتیاز ${s}`}>
      <span className="absolute inset-y-0 rounded-full" style={{ left: `${s >= 0 ? 50 : 50 + s / 2}%`, width: `${Math.abs(s) / 2}%`, background: s >= 0 ? 'var(--hq-positive)' : 'var(--hq-negative)' }} />
      <span aria-hidden className="absolute -top-1 left-1/2 h-4 w-[2px] -translate-x-1/2 rounded-full bg-strong" />
    </div>
  );
}

function Wave({ w }: { w: NpsWave }) {
  const now = useNow();
  const open = !!now && Date.parse(w.opens_at) <= now && Date.parse(w.closes_at) > now;
  const ahead = !!now && Date.parse(w.opens_at) > now;
  return (
    <Card className="flex min-w-0 flex-col gap-3 p-4">
      <div className="flex items-center gap-2"><CompanyMark code={w.company} height={13} mono /><span className="fig min-w-0 flex-1 truncate text-[13px] font-semibold">{w.quarter}</span><span className="fig text-[11px] text-muted">{w.ref}</span><Pill tone={open ? 'lapis' : 'neutral'} live={open}>{open ? 'باز' : ahead ? 'هنوز باز نشده' : 'بسته'}</Pill></div>
      {w.score != null ? (
        <div className="flex flex-col gap-2">
          <div className="flex items-baseline gap-2"><span className={cx('fig text-[28px] font-semibold leading-8', w.score >= 0 ? 'text-ink' : 'text-neg')}>{w.score > 0 ? '+' : ''}{w.score}</span><span className="text-[12px] text-sec">امتیاز NPS، از <span className="fig">−100</span> تا <span className="fig">+100</span></span></div>
          <NpsTrack score={w.score} />
          <StackedBar label="مروج، خنثی، منتقد" height={10} segs={[
            { key: 'p', label: 'مروج (۹–۱۰)', value: w.promoters, color: 'var(--hq-positive)', fmt: String(w.promoters) },
            { key: 'n', label: 'خنثی (۷–۸)', value: w.passives, color: 'var(--hq-silver-ink)', fmt: String(w.passives) },
            { key: 'd', label: 'منتقد (۰–۶)', value: w.detractors, color: 'var(--hq-negative)', fmt: String(w.detractors) },
          ]} />
        </div>
      ) : <p className="text-[13px] text-sec">{ahead ? `موج ${jDate(w.opens_at)} باز میشود؛ نمونه از پیش انتخاب شده است.` : 'هنوز جوابی نرسیده؛ امتیاز بی‌جواب ساخته نمیشود.'}</p>}
      <div className="grid grid-cols-3 gap-2">
        <Fact label="نمونه" mono>{w.sample}</Fact>
        <Fact label="فرستاده" mono>{w.sent}</Fact>
        <Fact label="جواب" mono>{w.responses}{w.sent ? <span className="text-[11px] font-normal text-muted"> · {rate(w.responses / w.sent)}</span> : null}</Fact>
      </div>
      <div className="flex flex-wrap items-center gap-x-3 text-[11px] text-muted">
        <span>{jDate(w.opens_at)} تا {jDate(w.closes_at)}{open ? ` (${until(w.closes_at)})` : ''}</span>
        <span className="flex-1" />
        {w.comments_to_feedback ? <Link href="/feedback" className="text-gold-ink">{w.comments_to_feedback} توضیح در صندوق بازخورد</Link> : null}
      </div>
    </Card>
  );
}

export function NpsTab({ company }: { company: string | null }) {
  const q = useNps(company);
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <Skeleton className="h-48" />;
  if (!q.data.length) return <Empty icon="rate" title="موجی نیست" body="NPS یک قاعده‌ی فصلی است؛ با مُهر قاعده‌ی NPS هر شرکت شروع میشود." />;
  const list = [...q.data].sort((a, b) => b.quarter.localeCompare(a.quarter) || a.company.localeCompare(b.company));
  return (
    <div className="flex flex-col gap-3">
      <p className="max-w-3xl text-[13px] leading-6 text-sec">جواب ۰ تا ۱۰؛ امتیاز = درصد مروج منهای درصد منتقد. توضیح‌ها به صندوق بازخورد میروند.</p>
      <div className="grid items-start gap-3 md:grid-cols-2 xl:grid-cols-3">{list.map((w) => <Wave key={w.ref} w={w} />)}</div>
    </div>
  );
}
