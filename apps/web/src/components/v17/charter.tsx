'use client';

import { useState } from 'react';
import { Icon } from '@/components/icon';
import { SealButton } from '@/components/cartable/seal-button';
import { Button } from '@/components/ui/button';
import { Md } from '@/components/ui/md';
import { Sheet } from '@/components/ui/overlay';
import { Bar, Card, Empty, Pill, Segmented, SectionTitle, Skeleton } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { useCompanies } from '@/lib/api/hooks';
import {
  charterMax, faError, useCharterAction, useCharterDiff, useCharterVersion, useCharterVersions,
  type Charter, type CharterScope, type RedLine,
} from '@/lib/api/v17';
import { companyOf } from '@/lib/company';
import { ACTOR_FA } from '@/lib/labels';
import { cx, jDate, jDateTime } from '@/lib/format';
import { CHARTER_STATUS, Diff } from './bits';

const field = 'w-full rounded-[10px] border border-strong bg-card px-3 text-[14px] text-ink outline-none focus:border-gold-ink';
export const scopeName = (scope: string, name: (c: string) => string) => (scope === 'holding' ? 'سند هلدینگ' : `الحاقیه‌ی ${name(scope)}`);

function RedLines({ lines }: { lines: RedLine[] }) {
  if (!lines.length) return <p className="text-[12px] text-muted">این نسخه خط قرمز تازه‌ای ندارد؛ خطوط قرمز سند هلدینگ برقرارند.</p>;
  return (
    <ul className="flex flex-col gap-2">
      {lines.map((r) => (
        <li key={r.key} className="flex items-start gap-2.5 rounded-[12px] bg-tile p-3">
          <span className="mt-0.5 text-neg"><Icon name="lock" size={16} /></span>
          <span className="flex min-w-0 flex-1 flex-col gap-1">
            <span className="text-[13px] font-semibold text-ink">{r.text_fa}</span>
            <span className="flex flex-wrap items-center gap-2 text-[11px] text-muted">
              <span className="fig">{r.key}</span>
              <Pill tone={r.check === 'rule' ? 'lapis' : 'neutral'} className="h-5 text-[11px]">{r.check === 'rule' ? 'قاعده: کد میسنجد' : 'نمونه‌برداری ناظر'}</Pill>
              {r.patterns?.length ? <span>{r.patterns.length} الگو</span> : null}
            </span>
          </span>
        </li>
      ))}
    </ul>
  );
}

function LengthMeter({ c }: { c: Pick<Charter, 'scope' | 'body_md'> }) {
  const max = charterMax(c.scope);
  const pct = (c.body_md.length / max) * 100;
  return (
    <div className="flex flex-col gap-1">
      <span className="flex justify-between text-[11px] text-muted"><span>طول (در هر اجرا خوانده میشود)</span><span className="fig">{c.body_md.length.toLocaleString('en-US')} / {max.toLocaleString('en-US')}</span></span>
      <Bar pct={pct} tone={pct > 100 ? 'neg' : pct > 85 ? 'warn' : 'silver'} label="طول متن" />
    </div>
  );
}

/** The proposed version: what changes against the sealed one, its red lines, and the seal bound to its body_sha256. */
function Proposed({ s, name }: { s: CharterScope; name: (c: string) => string }) {
  const p = s.proposed!;
  const diff = useCharterDiff(s.scope, p.version, s.sealed?.version ?? null);
  const act = useCharterAction();
  const toast = useToast();
  const { data: companies } = useCompanies();
  const co = companyOf(companies, s.scope === 'holding' ? companies?.find((c) => c.kind === 'holding')?.code : s.scope);
  const [view, setView] = useState<'diff' | 'text'>(s.sealed ? 'diff' : 'text');
  const seal = () => act.seal.mutateAsync(p).then(() => toast({ tone: 'ok', text: <>{scopeName(s.scope, name)}، نسخه‌ی <span className="fig">{p.version}</span> مُهر شد؛ از اجرای بعد همه‌ی ایجنت‌ها آن را میخوانند.</> })).catch((e) => toast({ tone: 'error', text: faError(e) }));
  return (
    <Card className="flex flex-col gap-4 p-4 ring-1 ring-[var(--hq-gold-ink)] md:p-5">
      <div className="flex flex-wrap items-center gap-2">
        <Pill tone="gold" dot>{CHARTER_STATUS.proposed!.fa}</Pill>
        <span className="text-[14px] font-semibold">نسخه‌ی <span className="fig">{p.version}</span></span>
        <span className="text-[12px] text-muted">{ACTOR_FA(p.created_by)}، {jDateTime(p.created_at)}</span>
      </div>
      {s.sealed ? <div className="w-full max-w-xs"><Segmented label="نما" value={view} onChange={setView} options={[{ value: 'diff', label: <>تفاوت با نسخه‌ی <span className="fig">{s.sealed.version}</span></> }, { value: 'text', label: 'متن کامل' }]} /></div> : null}
      {view === 'diff' && s.sealed ? (diff.isLoading ? <Skeleton className="h-48" /> : diff.data ? <Diff text={diff.data.diff} className="max-h-[420px] overflow-y-auto" /> : null)
        : <div className="max-h-[420px] overflow-y-auto rounded-[12px] bg-tile p-4"><Md text={p.body_md} /></div>}
      <section className="flex flex-col gap-2"><h3 className="text-[12px] font-semibold text-gold-ink">خطوط قرمز این نسخه</h3><RedLines lines={p.red_lines} /></section>
      <LengthMeter c={p} />
      <div className="flex flex-col items-center gap-2 rounded-[16px] bg-tile p-4">
        <SealButton code={co.code || s.scope} nameFa={co.nameFa} nameEn={co.nameEn} holding={s.scope === 'holding' || co.holding} busy={act.seal.isPending} onSealed={() => void seal()} size={88} />
        <p className="text-center text-[12px] leading-6 text-muted">مُهر به همین متن و همین خطوط قرمز بسته است (<span className="fig">sha256 {p.body_sha256.slice(0, 16)}…</span>)؛ سرور hash را دوباره حساب میکند.</p>
      </div>
    </Card>
  );
}

/** One version as text, or against the version before it. */
function Viewer({ scope, version, prev }: { scope: string; version: number; prev: number | null }) {
  const v = useCharterVersion(scope, version);
  const [view, setView] = useState<'text' | 'diff'>('text');
  const diff = useCharterDiff(scope, view === 'diff' ? version : null, prev);
  const c = v.data;
  if (v.isLoading || !c) return <Skeleton className="h-96" />;
  const st = CHARTER_STATUS[c.status] ?? { fa: c.status, tone: 'neutral' as const };
  return (
    <Card className="flex flex-col gap-4 p-4 md:p-5">
      <div className="flex flex-wrap items-center gap-2">
        <Pill tone={st.tone} dot>{st.fa}</Pill>
        <span className="text-[14px] font-semibold">نسخه‌ی <span className="fig">{c.version}</span></span>
        <span className="text-[12px] text-muted">{c.sealed_at ? <>مُهر {ACTOR_FA(c.sealed_by)}، {jDate(c.sealed_at, true)}</> : jDate(c.created_at, true)}</span>
        <span className="flex-1" />
        {prev != null ? <div className="w-56"><Segmented label="نما" value={view} onChange={setView} options={[{ value: 'text', label: 'متن' }, { value: 'diff', label: <>تفاوت با <span className="fig">{prev}</span></> }]} /></div> : null}
      </div>
      {view === 'diff' && prev != null ? (diff.data ? <Diff text={diff.data.diff} /> : <Skeleton className="h-48" />) : <Md text={c.body_md} />}
      <section className="flex flex-col gap-2"><h3 className="text-[12px] font-semibold text-gold-ink">خطوط قرمز</h3><RedLines lines={c.red_lines} /></section>
      <span className="fig text-[11px] text-muted">sha256 {c.body_sha256}</span>
    </Card>
  );
}

export function CharterScopeView({ s, name, onEdit }: { s: CharterScope; name: (c: string) => string; onEdit: () => void }) {
  const versions = useCharterVersions(s.scope);
  const list = versions.data ?? [];
  const [picked, setPicked] = useState<number | null>(null);
  const shown = picked ?? s.sealed?.version ?? null;
  const prev = shown != null ? list.filter((x) => x.version < shown).map((x) => x.version).sort((a, b) => b - a)[0] ?? null : null;
  return (
    <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
      <div className="flex min-w-0 flex-col gap-4">
        {s.proposed ? <Proposed key={`${s.scope}@${s.proposed.version}`} s={s} name={name} /> : null}
        {shown != null ? <Viewer key={`${s.scope}@${shown}`} scope={s.scope} version={shown} prev={prev} /> : !s.proposed ? <Card><Empty icon="report" title="هنوز نسخه‌ی مُهرشده‌ای نیست" body="تا مُهر نشده، فقط چهار خط قرمز مدل عملیاتی اجرا میشود." /></Card> : null}
      </div>
      <div className="flex min-w-0 flex-col gap-4">
        <Card className="flex flex-col gap-2 p-4">
          <SectionTitle title="نسخه‌ها" note="هر تغییر نسخه‌ی تازه است؛ هیچ نسخه‌ای پاک نمیشود" action={<Button size="sm" variant="secondary" icon="edit" onClick={onEdit}>نسخه‌ی تازه</Button>} />
          {versions.isLoading ? <Skeleton className="h-32" /> : (
            <ul className="flex flex-col gap-1">
              {list.map((c) => {
                const st = CHARTER_STATUS[c.status] ?? { fa: c.status, tone: 'neutral' as const };
                return (
                  <li key={c.version}>
                    <button type="button" onClick={() => setPicked(c.version)} aria-pressed={shown === c.version} className={cx('flex w-full items-center gap-2 rounded-[10px] px-2 py-2 text-right hover:bg-hover', shown === c.version && 'bg-hover')}>
                      <span className="fig w-7 text-[13px] font-semibold">v{c.version}</span>
                      <span className="flex min-w-0 flex-1 flex-col"><span className="text-[12px] text-sec">{ACTOR_FA(c.created_by)}</span><span className="text-[11px] text-muted">{jDate(c.sealed_at ?? c.created_at, true)}</span></span>
                      <Pill tone={st.tone} dot className="h-5 text-[11px]">{st.fa}</Pill>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </Card>
        <Card className="flex flex-col gap-2 p-4 text-[12px] leading-6 text-sec">
          <SectionTitle title="ایجنت‌ها چطور میخوانند" />
          <p>نسخه‌ی مُهرشده‌ی سند هلدینگ و الحاقیه‌ی شرکت، بعد از دستورهای مشترک و پیش از منشور نقش، در بخش cache‌شده‌ی هر اجرا میاید و هر اجرا ثبت میکند کدام نسخه را خواند (مثل <span className="fig">holding@1</span>). هیچ ابزار نوشتنی برای اساسنامه نیست.</p>
          <p>خط قرمزِ «قاعده» را کد روی خروجی‌ها، پیام‌ها و استوری‌ها میسنجد و متن مشتری را پیش از ارسال نگه میدارد؛ «نمونه‌برداری» کار ناظر است.</p>
          {s.sealed ? <LengthMeter c={s.sealed} /> : null}
        </Card>
      </div>
    </div>
  );
}

/** A new proposed version: the text and the red lines, both bound by the seal. */
export function CharterEditor({ scope, from, name, onClose }: { scope: string; from: Charter | null; name: (c: string) => string; onClose: () => void }) {
  const act = useCharterAction();
  const toast = useToast();
  const [body, setBody] = useState(from?.body_md ?? '');
  const [lines, setLines] = useState<RedLine[]>(from?.red_lines ?? []);
  const max = charterMax(scope);
  const bad = !body.trim() || body.length > max || lines.some((r) => !r.key.trim() || !r.text_fa.trim());
  const set = (i: number, p: Partial<RedLine>) => setLines((xs) => xs.map((r, j) => (j === i ? { ...r, ...p } : r)));
  const save = () => act.propose.mutateAsync({ scope, body_md: body, red_lines: lines.map((r) => ({ ...r, key: r.key.trim(), patterns: r.check === 'rule' && r.patterns?.length ? r.patterns : null })) })
    .then((c) => { toast({ tone: 'ok', text: <>نسخه‌ی <span className="fig">{c.version}</span> پیشنهاد شد؛ تا مُهر تو هیچ ایجنتی آن را نمیخواند.</> }); onClose(); })
    .catch((e) => toast({ tone: 'error', text: faError(e) }));
  return (
    <Sheet open onOpenChange={(o) => !o && onClose()} title={`${scopeName(scope, name)}، نسخه‌ی تازه`} description="نسخه‌ی پیشنهادی میماند تا خودت مُهرش کنی." width={640}
      footer={<Button variant="primary" icon="send" className="w-full" disabled={bad} loading={act.propose.isPending} onClick={() => void save()}>ثبت نسخه‌ی پیشنهادی</Button>}>
      <div className="flex flex-col gap-4 text-[13px]">
        <label className="flex flex-col gap-1.5 font-semibold text-sec">متن (Markdown)
          <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={14} className={cx(field, 'py-2 leading-7')} />
          <span className={cx('fig self-end text-[11px] font-normal', body.length > max ? 'text-neg' : 'text-muted')}>{body.length.toLocaleString('en-US')} / {max.toLocaleString('en-US')}</span>
        </label>
        <div className="flex flex-col gap-2">
          <span className="font-semibold text-sec">خطوط قرمز</span>
          {lines.map((r, i) => (
            <div key={i} className="flex flex-col gap-2 rounded-[12px] border border-div p-3">
              <div className="flex flex-wrap items-center gap-2">
                <input value={r.key} onChange={(e) => set(i, { key: e.target.value.replace(/[^a-z0-9_]/gi, '').toLowerCase() })} dir="ltr" placeholder="key" aria-label="کلید خط قرمز" className={cx(field, 'fig h-9 w-40 text-[12px]')} />
                <select value={r.check} onChange={(e) => set(i, { check: e.target.value as RedLine['check'] })} aria-label="روش سنجش" className={cx(field, 'h-9 w-auto text-[12px]')}>
                  <option value="rule">قاعده (کد)</option><option value="sample">نمونه‌برداری</option>
                </select>
                <span className="flex-1" />
                <Button size="sm" variant="ghost" icon="close" aria-label="حذف خط قرمز" onClick={() => setLines((xs) => xs.filter((_, j) => j !== i))} />
              </div>
              <input value={r.text_fa} onChange={(e) => set(i, { text_fa: e.target.value })} placeholder="متن خط قرمز" aria-label="متن خط قرمز" className={cx(field, 'h-10')} />
              {r.check === 'rule' ? (
                <textarea value={(r.patterns ?? []).join('\n')} onChange={(e) => set(i, { patterns: e.target.value.split('\n').filter((x, k, a) => x.trim() || k < a.length - 1) })} rows={2} dir="ltr" placeholder="الگوها، هر خط یکی" aria-label="الگوها" className={cx(field, 'fig py-2 text-[12px]')} />
              ) : null}
            </div>
          ))}
          <Button size="sm" variant="ghost" icon="add" className="self-start" onClick={() => setLines((xs) => [...xs, { key: '', text_fa: '', check: 'sample', patterns: null }])}>خط قرمز تازه</Button>
        </div>
      </div>
    </Sheet>
  );
}
