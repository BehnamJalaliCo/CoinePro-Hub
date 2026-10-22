'use client';

import { useMemo, useState } from 'react';
import { Icon } from '@/components/icon';
import { SealButton } from '@/components/cartable/seal-button';
import { MdInline } from '@/components/ui/md';
import { Button } from '@/components/ui/button';
import { Dialog, Sheet } from '@/components/ui/overlay';
import { Bar, Card, Empty, FilterChip, Pill, SectionTitle, Segmented, Skeleton, Switch } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { CoMark, RefChip } from '@/components/v17/bits';
import { useCompanies } from '@/lib/api/hooks';
import { useAccounts } from '@/lib/api/v14';
import { CHECKS, faError, usePlatformLimits, useSeriesAction, useVoices, type Aspect, type MediaKind, type MediaPlacement, type Series, type SeriesIn, type SeriesTarget } from '@/lib/api/v19';
import { companyOf } from '@/lib/company';
import { ACTOR_FA } from '@/lib/labels';
import { cx, jDateTime, until } from '@/lib/format';
import { CHANNEL_FA, CHECK_FA, DAY_FA, DAY_SHORT, KIND_FA, LicenceBadge, PLACEMENT_FA, SERIES_STATUS, Schedule, buildRrule, hhmm, parseRrule, type Rule } from './bits';

const field = 'h-10 w-full rounded-[10px] border border-strong bg-card px-3 text-[14px] text-ink outline-none focus:border-gold-ink';
const DAYS = ['SA', 'SU', 'MO', 'TU', 'WE', 'TH', 'FR'];
const PLACEMENTS: Array<{ channel: 'telegram' | 'instagram'; placement: MediaPlacement }> = [
  { channel: 'instagram', placement: 'instagram_reel' }, { channel: 'instagram', placement: 'instagram_story' }, { channel: 'instagram', placement: 'instagram_post' },
  { channel: 'telegram', placement: 'telegram_post' }, { channel: 'telegram', placement: 'telegram_story' },
];
/** The platform's own rules, checked here before the server checks them again (`platform`, §22.2). */
export function placementFits(kind: MediaKind, aspect: Aspect, p: MediaPlacement): string | null {
  if (p === 'instagram_reel' && (kind !== 'reel' || aspect !== '9:16')) return 'فقط ریلز ۹:۱۶';
  if (p.endsWith('_story') && (kind !== 'story' || aspect !== '9:16')) return 'فقط استوری ۹:۱۶';
  if (p === 'instagram_post' && (!['post', 'carousel'].includes(kind) || !['4:5', '1:1'].includes(aspect))) return 'پست یا کاروسل ۴:۵ یا ۱:۱';
  return null;
}
const ASPECTS: Record<MediaKind, Aspect[]> = { reel: ['9:16'], story: ['9:16'], post: ['1:1', '4:5', '16:9'], carousel: ['4:5', '1:1'] };
/** The owner's default caps (prompt 13 §0.9 #5). */
const CAP: Record<MediaKind, number> = { reel: 2, story: 3, post: 2, carousel: 2 };
const accountKey = (channel: string, company: string) => `${channel}-${company.toLowerCase()}`;

// ------------------------------------------------------------------ one series --
export function SeriesCard({ s, focus, onEdit }: { s: Series; focus?: boolean; onEdit: (s: Series) => void }) {
  const act = useSeriesAction();
  const toast = useToast();
  const { data: companies } = useCompanies();
  const accounts = useAccounts();
  const [busy, setBusy] = useState(false);
  const [retire, setRetire] = useState(false);
  const co = companyOf(companies, s.company);
  const st = SERIES_STATUS[s.status] ?? SERIES_STATUS.draft!;
  const sealable = ['draft', 'proposed', 'paused'].includes(s.status);
  const hasKey = (acc: string) => accounts.data?.find((a) => a.key === acc)?.has_secret;
  const seal = async () => {
    setBusy(true);
    try { await act.seal.mutateAsync(s); toast({ tone: 'ok', text: <>برنامه‌ی <span className="fig">{s.ref}</span> مُهر شد؛ از این به بعد هر آیتمی که همه‌ی چک‌ها را رد کند{s.auto_publish ? ' خودکار' : ' با کارت تو'} منتشر میشود.</> }); }
    catch (e) { toast({ tone: 'error', text: faError(e) }); } finally { setBusy(false); }
  };
  const simple = async (fn: 'pause' | 'retire') => {
    try { await act[fn].mutateAsync(s.ref); setRetire(false); toast({ tone: 'info', text: fn === 'pause' ? 'متوقف شد؛ با مُهر دوباره ادامه میدهد.' : 'بازنشسته شد؛ دیگر آیتمی نمیسازد.' }); }
    catch (e) { toast({ tone: 'error', text: faError(e) }); }
  };
  return (
    <Card id={s.ref} className={cx('flex flex-col gap-4 p-4', focus && 'ring-2 ring-[var(--hq-gold-ink)]', s.status === 'proposed' && 'tahrir')}>
      <div className="flex flex-wrap items-start gap-3">
        <span className="flex size-11 flex-none items-center justify-center rounded-[12px] bg-tile text-gold-ink"><Icon name={KIND_FA[s.kind]?.icon ?? 'send'} size={22} /></span>
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <div className="flex flex-wrap items-center gap-2 text-[12px] text-muted"><CoMark code={s.company} height={11} /><span>{co.nameFa}</span><span className="fig">{s.ref}</span><span>{KIND_FA[s.kind]?.fa}</span><span>نسخه‌ی {s.version}</span></div>
          <h3 className="text-[16px] font-semibold text-ink">{s.title_fa}</h3>
          <div className="flex flex-wrap items-center gap-2"><Pill tone={st.tone} icon={st.icon}>{st.fa}</Pill>{s.auto_publish ? <Pill tone="silver" icon="send">انتشار خودکار</Pill> : <Pill tone="neutral" icon="cartable">هر آیتم کارت</Pill>}</div>
        </div>
      </div>
      {s.status_note_fa ? <p className={cx('flex items-start gap-2 rounded-[12px] p-3 text-[13px] leading-6 text-ink', s.status === 'paused' ? 'bg-warn-soft' : 'bg-tile')}><span className="text-warn"><Icon name="info" size={16} /></span>{s.status_note_fa}</p> : null}
      <dl className="grid gap-3 text-[13px] sm:grid-cols-2">
        <div className="flex flex-col gap-1"><dt className="text-[11px] text-muted">زمان‌بندی (منطقه‌ی زمانی تو)</dt><dd className="text-ink"><Schedule rrule={s.schedule} /> · سقف روزانه {s.max_per_day}</dd></div>
        <div className="flex flex-col gap-1"><dt className="text-[11px] text-muted">قالب</dt><dd className="text-ink"><span className="fig">{s.format.aspect}</span>{s.format.duration_s ? <>، <span className="fig">{s.format.duration_s}s</span></> : null}{s.format.voice ? '، با صدای هاب' : '، بی‌صدا'}{s.format.captions ? '، زیرنویس سوخته' : ''}، {s.format.music === 'none' ? 'بی‌موسیقی' : 'موسیقی کتابخانه'}</dd></div>
        <div className="flex flex-col gap-1 sm:col-span-2"><dt className="text-[11px] text-muted">جای انتشار (فقط API رسمی)</dt>
          <dd className="flex flex-wrap gap-1.5">{s.targets.map((t) => {
            const ok = hasKey(t.account);
            const manual = t.placement === 'telegram_story';
            return <span key={`${t.account}-${t.placement}`} className={cx('inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[12px]', ok === false ? 'bg-warn-soft text-warn' : 'bg-tile text-ink')}>
              {PLACEMENT_FA[t.placement]}<span className="fig text-[11px] text-muted">{t.account}</span>{ok === false ? <span className="text-[11px]">· بی‌کلید</span> : manual ? <span className="text-[11px] text-muted">· کارت با فایل</span> : null}
            </span>;
          })}</dd></div>
        <div className="flex flex-col gap-1 sm:col-span-2"><dt className="text-[11px] text-muted">موضوع‌ها</dt>
          <dd className="text-sec">{s.topics?.pool.length ? <span className="flex flex-wrap gap-1.5">{s.topics.pool.map((t) => <span key={t} className="rounded-full bg-tile px-2 py-0.5 text-[12px]">{t}</span>)}</span> : s.topics?.rule_fa ?? '—'}</dd></div>
      </dl>
      {s.status === 'sealed' && s.next_at?.length ? (
        <div className="flex flex-wrap items-center gap-2 text-[12px] text-sec"><Icon name="time" size={14} />بعدی: {s.next_at.slice(0, 3).map((at, i) => <span key={at} className={cx('rounded-full px-2 py-0.5', i === 0 ? 'bg-gold-soft text-gold-ink' : 'bg-tile')}>{jDateTime(at)}{i === 0 ? ` (${until(at)})` : ''}</span>)}
          {s.today ? <span className="text-muted">· امروز {s.today.made} ساخته، {s.today.published} منتشر</span> : null}</div>
      ) : null}
      <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-muted">
        <span>چک‌ها:</span>{CHECKS.map((k) => <span key={k} className="rounded-full bg-tile px-2 py-0.5">{CHECK_FA[k]?.fa}</span>)}
      </div>
      <div className="flex flex-wrap items-center gap-3 border-t border-div pt-3">
        {sealable ? (
          <div className="flex min-w-[240px] flex-1 items-center gap-3">
            <SealButton code={s.company} nameFa={co.nameFa} nameEn={co.nameEn} holding={co.holding} busy={busy} onSealed={seal} size={64} />
            <span className="flex min-w-0 flex-1 flex-col gap-0.5 text-[12px] leading-5 text-sec">
              <span className="font-semibold text-ink">{s.status === 'paused' ? 'مُهر دوباره برای ادامه' : 'مُهر این برنامه'}</span>
              <span>یک بار، روی همین نسخه: <span className="fig break-all">digest {s.digest.slice(0, 12)}…</span></span>
            </span>
          </div>
        ) : s.status === 'sealed' ? (
          <span className="flex min-w-[240px] flex-1 flex-col gap-1 text-[12px] text-sec">
            <span className="flex flex-wrap items-center gap-2"><span className="text-pos"><Icon name="seal" size={16} /></span>مُهر خورد{s.sealed_at ? `، ${jDateTime(s.sealed_at)}` : ''}{s.decision_ref ? <RefChip r={s.decision_ref} /> : null}</span>
            <span className="fig break-all text-[11px] text-muted">digest {s.digest.slice(0, 16)}…</span>
          </span>
        ) : <span className="flex-1" />}
        <div className="flex flex-wrap gap-2">
          {s.status !== 'retired' ? <Button size="sm" variant="secondary" icon="edit" onClick={() => onEdit(s)}>ویرایش</Button> : null}
          {s.status === 'sealed' ? <Button size="sm" variant="ghost" icon="pause" loading={act.pause.isPending} onClick={() => simple('pause')}>توقف</Button> : null}
          {s.status !== 'retired' ? <Button size="sm" variant="ghost" icon="close" onClick={() => setRetire(true)}>بازنشسته</Button> : null}
        </div>
      </div>
      {s.proposed_by ? <p className="text-[11px] text-muted">پیشنهاد {ACTOR_FA(s.proposed_by)}{s.items_total ? ` · تا امروز ${s.items_total} آیتم` : ''}</p> : null}
      <Dialog open={retire} onOpenChange={setRetire} title="بازنشسته کردن برنامه" actions={<>
        <Button variant="danger" loading={act.retire.isPending} onClick={() => simple('retire')}>بازنشسته کن</Button>
        <Button variant="secondary" onClick={() => setRetire(false)}>نه</Button>
      </>}><p>دیگر آیتم تازه‌ای نمیسازد؛ آیتم‌های ساخته‌شده و تاریخچه‌اش میمانند. برگرداندنش یعنی برنامه‌ی تازه و مُهر تازه.</p></Dialog>
    </Card>
  );
}

// ------------------------------------------------------------------ the week per channel --
/** The sealed schedule per channel: every account, its week, each slot gold when a seal covers it. */
export function ChannelWeek({ series }: { series: Series[] }) {
  const { data: companies } = useCompanies();
  const live = series.filter((s) => s.status !== 'retired');
  const channels = useMemo(() => {
    const m = new Map<string, { account: string; company: string; channel: string; slots: Array<{ day: string; time: string; s: Series; placement: MediaPlacement }> }>();
    for (const s of live) {
      const r = parseRrule(s.schedule);
      if (!r) continue;
      const days = r.freq === 'DAILY' ? DAYS : r.days;
      for (const t of s.targets) {
        const row = m.get(t.account) ?? { account: t.account, company: s.company, channel: t.channel, slots: [] };
        for (const d of days) row.slots.push({ day: d, time: hhmm(r.hour, r.minute), s, placement: t.placement });
        m.set(t.account, row);
      }
    }
    return [...m.values()].sort((a, b) => a.company.localeCompare(b.company) || a.channel.localeCompare(b.channel));
  }, [live]);
  if (!channels.length) return null;
  return (
    <Card className="flex flex-col gap-3 p-4">
      <SectionTitle title="هفته‌ی هر کانال" note="طلایی: زیر مُهر، خودکار؛ خط‌چین: بی‌مُهر یا متوقف، چیزی خودکار نمیرود" />
      <div className="flex flex-col gap-3">
        {channels.map((c) => (
          <div key={c.account} className="flex flex-col gap-2 rounded-[12px] bg-tile p-3">
            <span className="flex items-center gap-2 text-[13px] font-semibold text-ink"><CoMark code={c.company} height={11} />{CHANNEL_FA[c.channel]} {companyOf(companies, c.company).nameFa}<span className="fig text-[11px] font-normal text-muted">{c.account}</span></span>
            <div className="grid grid-cols-7 gap-1">
              {DAYS.map((d) => {
                const xs = c.slots.filter((x) => x.day === d).sort((a, b) => a.time.localeCompare(b.time));
                return (
                  <div key={d} className="flex min-h-[64px] flex-col gap-1 rounded-[8px] bg-card p-1">
                    <span className="text-center text-[11px] text-muted" title={DAY_FA[d]}>{DAY_SHORT[d]}</span>
                    {xs.map((x) => (
                      <span key={`${x.s.ref}-${x.placement}`} title={`${x.s.title_fa} · ${PLACEMENT_FA[x.placement]}`}
                        className={cx('fig rounded-[6px] px-0.5 py-0.5 text-center text-[10px] leading-4', x.s.status === 'sealed' ? 'bg-gold-soft text-gold-ink' : 'border border-dashed border-strong text-muted')}>{x.time}</span>
                    ))}
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}

// ------------------------------------------------------------------ platform limits --
export function LimitsCard() {
  const q = usePlatformLimits();
  const accounts = useAccounts();
  return (
    <Card className="flex flex-col gap-3 p-4">
      <SectionTitle title="سقف خود پلتفرم‌ها" note="جدا از سقف روزانه‌ی هر برنامه؛ پر شدنش یعنی 429 platform_limit و صبر تا ریست" />
      {q.isLoading ? <Skeleton className="h-40" /> : !q.data?.length ? <Empty icon="send" title="حسابی تعریف نشده" /> : (
        <ul className="flex flex-col gap-2">
          {q.data.map((l) => {
            const a = accounts.data?.find((x) => x.key === l.account);
            const pct = l.per_24h ? (l.used_24h / l.per_24h) * 100 : 0;
            return (
              <li key={l.account} className="flex flex-col gap-1.5 rounded-[12px] bg-tile p-3">
                <span className="flex flex-wrap items-center gap-2 text-[13px]">
                  <CoMark code={l.company} height={11} /><span className="font-semibold text-ink">{a?.title_fa ?? l.account}</span><span className="fig text-[11px] text-muted">{l.account}</span>
                  <span className="flex-1" />
                  {a ? <Pill tone={a.has_secret ? 'pos' : 'warn'} dot>{a.has_secret ? 'کلید دارد' : 'بی‌کلید'}</Pill> : null}
                </span>
                {l.per_24h ? (
                  <>
                    <Bar pct={pct} tone={pct >= 90 ? 'neg' : pct >= 70 ? 'warn' : 'silver'} label={`مصرف ۲۴ ساعت ${l.account}`} />
                    <span className="text-[11px] text-muted"><span className="fig text-sec">{l.used_24h} / {l.per_24h}</span> پست API در ۲۴ ساعت{l.resets_at ? ` · ریست ${until(l.resets_at)}` : ''}</span>
                  </>
                ) : <span className="text-[11px] text-muted"><span className="fig text-sec">{l.used_24h}</span> ارسال در ۲۴ ساعت</span>}
                {l.note_fa ? <span className="text-[11px] leading-5 text-muted"><MdInline text={l.note_fa} /></span> : null}
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}

// ------------------------------------------------------------------ the editor --
export function SeriesEditor({ s, onClose, onSaved }: { s: Series | null; onClose: () => void; onSaved: (ref: string) => void }) {
  const act = useSeriesAction();
  const toast = useToast();
  const { data: companies } = useCompanies();
  const voices = useVoices();
  const [key] = useState(() => crypto.randomUUID());
  const rule0: Rule = (s && parseRrule(s.schedule)) || { freq: 'WEEKLY', days: ['SA', 'TU'], hour: 18, minute: 30 };
  const [company, setCompany] = useState<string | null>(s?.company ?? null);
  const [title, setTitle] = useState(s?.title_fa ?? '');
  const [kind, setKind] = useState<MediaKind>(s?.kind ?? 'reel');
  const [aspect, setAspect] = useState<Aspect>(s?.format.aspect ?? '9:16');
  const [targets, setTargets] = useState<SeriesTarget[]>(s?.targets ?? []);
  const [rule, setRule] = useState<Rule>(rule0);
  const [pool, setPool] = useState((s?.topics?.pool ?? []).join('\n'));
  const [topicRule, setTopicRule] = useState(s?.topics?.rule_fa ?? '');
  const [duration, setDuration] = useState<number | null>(s?.format.duration_s ?? 15);
  const [voice, setVoice] = useState<string | null>(s ? s.format.voice?.voice_id ?? null : 'active');
  const [captions, setCaptions] = useState(s?.format.captions ?? true);
  const [cta, setCta] = useState(s?.format.overlay.cta_fa ?? '');
  const [mark, setMark] = useState(s?.format.overlay.mark ?? true);
  const [auto, setAuto] = useState(s?.auto_publish ?? false);
  const [cap, setCap] = useState(s?.max_per_day ?? CAP.reel);
  const active = voices.data?.find((v) => v.status === 'active');
  const voiceId = voice === 'active' ? active?.id ?? null : voice;
  const timed = kind === 'reel' || kind === 'story';
  const pickKind = (k: MediaKind) => { setKind(k); setAspect(ASPECTS[k][0]!); setCap(CAP[k]); setTargets((ts) => ts.filter((t) => !placementFits(k, ASPECTS[k][0]!, t.placement))); };
  const toggle = (t: SeriesTarget) => setTargets((ts) => (ts.some((x) => x.account === t.account && x.placement === t.placement) ? ts.filter((x) => !(x.account === t.account && x.placement === t.placement)) : [...ts, t]));
  const topics = { pool: pool.split('\n').map((x) => x.trim()).filter(Boolean), rule_fa: topicRule.trim() || null };
  const ok = !!company && title.trim().length >= 3 && targets.length > 0 && (topics.pool.length > 0 || !!topics.rule_fa) && (rule.freq === 'DAILY' || rule.days.length > 0);
  const sealedNow = s?.status === 'sealed' || s?.status === 'paused';

  const submit = async () => {
    if (!company) return;
    const body: SeriesIn = {
      company, title_fa: title.trim(), kind, targets, schedule: buildRrule(rule), topics,
      format: { aspect, duration_s: timed ? duration : null, voice: timed && voiceId ? { voice_id: voiceId } : null, captions: timed && captions, music: 'none', overlay: { cta_fa: cta.trim() || null, mark } },
      checks: CHECKS, auto_publish: auto, max_per_day: cap,
    };
    try {
      const out = s ? await act.update.mutateAsync({ s, body }) : await act.create.mutateAsync({ body, key });
      toast({ tone: 'ok', text: s ? (sealedNow ? 'ذخیره شد؛ مُهر قبلی دیگر این نسخه را نمیپوشاند. برای انتشار خودکار دوباره مُهر کن.' : 'ذخیره شد.') : <>برنامه‌ی <span className="fig">{out.ref}</span> ساخته شد؛ تا مُهرش نکنی هیچ آیتمی نمیسازد.</> });
      onSaved(out.ref);
    } catch (e) { toast({ tone: 'error', text: faError(e) }); }
  };

  return (
    <Sheet open onOpenChange={(v) => !v && onClose()} width={620} title={s ? <span className="flex items-center gap-2">ویرایش برنامه<span className="fig text-[13px] text-muted">{s.ref}</span></span> : 'برنامه‌ی انتشار تازه'}
      description={s ? (sealedNow ? 'این برنامه مُهر خورده؛ هر ویرایش آن را به «منتظر مُهر» برمیگرداند و تا مُهر دوباره چیزی خودکار منتشر نمیشود.' : 'تا مُهرش نکنی هیچ آیتمی نمیسازد.') : 'پیش‌نویس ساخته میشود؛ تا مُهرش نکنی هیچ آیتمی نمیسازد. مدیر رسانه هم میتواند پیشنهادش را بدهد.'}
      footer={<div className="flex gap-2"><Button variant="primary" icon={s ? 'edit' : 'add'} disabled={!ok} loading={act.create.isPending || act.update.isPending} onClick={submit}>{s ? 'ذخیره' : 'بساز'}</Button><Button variant="ghost" onClick={onClose}>انصراف</Button></div>}>
      <div className="flex flex-col gap-5 text-[13px]">
        {!s ? (
          <fieldset className="flex flex-col gap-2"><legend className="pb-2 font-semibold text-sec">کدام شرکت</legend>
            <div className="flex flex-wrap gap-1.5">{(companies ?? []).filter((c) => c.kind !== 'holding').map((c) => <FilterChip key={c.code} selected={company === c.code} onClick={() => { setCompany(c.code); setTargets([]); }}><span className="flex items-center gap-1.5"><CoMark code={c.code} height={11} />{c.name_fa}</span></FilterChip>)}</div>
          </fieldset>
        ) : null}
        <label className="flex flex-col gap-1.5 font-semibold text-sec">عنوان<input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={80} placeholder="مثلاً: سطح‌های هفته‌ی طلا" className={field} /></label>
        <div className="flex flex-col gap-2">
          <span className="font-semibold text-sec">نوع و نسبت</span>
          <div className="flex flex-wrap gap-1.5">{(Object.keys(ASPECTS) as MediaKind[]).map((k) => <FilterChip key={k} selected={kind === k} onClick={() => pickKind(k)}>{KIND_FA[k]!.fa}</FilterChip>)}</div>
          {ASPECTS[kind].length > 1 ? <div className="flex flex-wrap gap-1.5">{ASPECTS[kind].map((a) => <FilterChip key={a} selected={aspect === a} onClick={() => { setAspect(a); setTargets((ts) => ts.filter((t) => !placementFits(kind, a, t.placement))); }}><span className="fig">{a}</span></FilterChip>)}</div> : <span className="text-[11px] text-muted">نسبت <span className="fig">{aspect}</span></span>}
        </div>
        <fieldset className="flex flex-col gap-2"><legend className="pb-2 font-semibold text-sec">جای انتشار (فقط API رسمی تلگرام و اینستاگرام)</legend>
          {!company ? <span className="text-[12px] text-muted">اول شرکت را انتخاب کن.</span> : (
            <div className="flex flex-col gap-1.5">
              {PLACEMENTS.map((p) => {
                const t: SeriesTarget = { channel: p.channel, account: accountKey(p.channel, company), placement: p.placement };
                const why = placementFits(kind, aspect, p.placement);
                const on = targets.some((x) => x.account === t.account && x.placement === t.placement);
                return (
                  <button key={p.placement} type="button" disabled={!!why} aria-pressed={on} onClick={() => toggle(t)}
                    className={cx('flex items-center gap-3 rounded-[10px] px-3 py-2 text-start transition-colors disabled:opacity-50', on ? 'bg-gold-soft ring-1 ring-[var(--hq-gold-ink)]' : 'bg-tile hover:bg-hover')}>
                    <Icon name={on ? 'seal' : 'add'} size={16} />
                    <span className="flex min-w-0 flex-1 flex-col"><span className="text-ink">{PLACEMENT_FA[p.placement]}</span><span className="fig text-[11px] text-muted">{t.account}</span></span>
                    {why ? <span className="text-[11px] text-muted">{why}</span> : p.placement === 'telegram_story' ? <span className="text-[11px] text-muted">Bot API ندارد: همیشه کارت با فایل</span> : null}
                  </button>
                );
              })}
            </div>
          )}
        </fieldset>
        <fieldset className="flex flex-col gap-2"><legend className="pb-2 font-semibold text-sec">زمان‌بندی (منطقه‌ی زمانی تو)</legend>
          <Segmented label="تکرار" value={rule.freq} onChange={(v) => setRule({ ...rule, freq: v })} options={[{ value: 'DAILY', label: 'هر روز' }, { value: 'WEEKLY', label: 'روزهای هفته' }]} />
          {rule.freq === 'WEEKLY' ? <div className="flex flex-wrap gap-1.5">{DAYS.map((d) => <FilterChip key={d} selected={rule.days.includes(d)} onClick={() => setRule({ ...rule, days: rule.days.includes(d) ? rule.days.filter((x) => x !== d) : [...rule.days, d] })}>{DAY_FA[d]}</FilterChip>)}</div> : null}
          <label className="flex items-center gap-2 text-sec">ساعت
            <input type="time" dir="ltr" value={hhmm(rule.hour, rule.minute)} onChange={(e) => { const [h, m] = e.target.value.split(':').map(Number); if (Number.isFinite(h) && Number.isFinite(m)) setRule({ ...rule, hour: h!, minute: m! }); }} aria-label="ساعت انتشار" className="fig h-10 rounded-[10px] border border-strong bg-card px-3 text-ink outline-none focus:border-gold-ink" />
          </label>
          <span className="text-[11px] text-muted"><Schedule rrule={buildRrule(rule)} /> · <span dir="ltr" className="fig">{buildRrule(rule)}</span></span>
        </fieldset>
        <fieldset className="flex flex-col gap-2"><legend className="pb-2 font-semibold text-sec">موضوع‌ها</legend>
          <textarea value={pool} onChange={(e) => setPool(e.target.value)} rows={3} placeholder="هر خط یک موضوع؛ به ترتیب برداشته میشوند" aria-label="فهرست موضوع" className="w-full rounded-[10px] border border-strong bg-card p-3 text-[14px] leading-6 text-ink outline-none focus:border-gold-ink" />
          <input value={topicRule} onChange={(e) => setTopicRule(e.target.value)} maxLength={200} placeholder="یا قاعده: مثلاً یک اصطلاح از دانشنامه‌ی آموزش، به ترتیب" aria-label="قاعده‌ی موضوع" className={field} />
        </fieldset>
        <fieldset className="flex flex-col gap-3 rounded-[12px] bg-tile p-3"><legend className="px-1 text-[12px] font-semibold text-sec">قالب</legend>
          {timed ? (
            <>
              <label className="flex items-center gap-2 text-sec">مدت<input value={duration ?? ''} onChange={(e) => setDuration(Number(e.target.value.replace(/\D/g, '')) || null)} inputMode="numeric" aria-label="مدت به ثانیه" className="fig h-9 w-16 rounded-[8px] border border-strong bg-card px-2 text-center text-ink" />ثانیه</label>
              <div className="flex flex-col gap-1.5">
                <span className="text-sec">صدا</span>
                <div className="flex flex-wrap gap-1.5">
                  <FilterChip selected={voice === null} onClick={() => setVoice(null)}>بی‌صدا</FilterChip>
                  <FilterChip selected={voice === 'active'} onClick={() => setVoice('active')}>صدای فعال هاب</FilterChip>
                  {(voices.data ?? []).filter((v) => v.samples?.length).map((v) => <FilterChip key={v.id} selected={voice === v.id} onClick={() => setVoice(v.id)}>{v.name_fa}</FilterChip>)}
                </div>
                {voiceId ? (() => { const v = voices.data?.find((x) => x.id === voiceId); return v ? <span><LicenceBadge commercial={v.licence_commercial} licence={v.licence} /></span> : null; })() : null}
              </div>
              <label className="flex items-center gap-2 text-sec"><Switch label="زیرنویس فارسی سوخته" checked={captions} onChange={setCaptions} />زیرنویس فارسی سوخته</label>
            </>
          ) : null}
          <span className="flex items-center gap-2 text-[12px] text-muted"><Icon name="lock" size={14} />موسیقی: هیچ؛ کتابخانه‌ی موسیقی مجاز نداری.</span>
          <input value={cta} onChange={(e) => setCta(e.target.value)} maxLength={30} placeholder="دعوت روی تصویر (اختیاری)" aria-label="دعوت به اقدام" className={field} />
          <label className="flex items-center gap-2 text-sec"><Switch label="نشان شرکت" checked={mark} onChange={setMark} />نشان شرکت</label>
        </fieldset>
        <div className="flex flex-col gap-2">
          <label className="flex items-start gap-3 rounded-[12px] bg-tile p-3 text-sec"><Switch label="انتشار خودکار" checked={auto} onChange={setAuto} />
            <span className="flex flex-col gap-0.5"><span className="font-semibold text-ink">انتشار خودکار</span><span className="text-[12px] leading-5">فقط وقتی هر هفت چک قبول باشد، در زمان برنامه. خاموش: هر آیتم کارت توست. برنامه‌ی تازه را خاموش شروع کن.</span></span>
          </label>
          <label className="flex items-center gap-2 text-sec">سقف روزانه<input value={cap} onChange={(e) => setCap(Math.min(10, Number(e.target.value.replace(/\D/g, '')) || 1))} inputMode="numeric" aria-label="سقف روزانه" className="fig h-9 w-14 rounded-[8px] border border-strong bg-card px-2 text-center text-ink" />آیتم در روز</label>
          <span className="flex flex-wrap items-center gap-1.5 text-[11px] text-muted"><Icon name="seal" size={12} />چک‌ها همیشه هر هفت تا:{CHECKS.map((k) => <span key={k} className="rounded-full bg-tile px-2 py-0.5">{CHECK_FA[k]?.fa}</span>)}</span>
        </div>
      </div>
    </Sheet>
  );
}
