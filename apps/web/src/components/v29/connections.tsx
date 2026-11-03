'use client';

// ⟨1.11⟩ Contract §29.12 «اتصال‌ها»: what each company can measure and manage. Every kind in the order of work, with its state, when it
// was last read and its latest daily figures; «وصل کن» opens the one-page guide, the settings that are not secret, and the 🔏 write-only
// secret field (it never shows a secret back: only «ثبت شده» or «ثبت نشده»).

import { useState } from 'react';
import { Icon } from '@/components/icon';
import { Spark } from '@/components/v14/bits';
import { Button } from '@/components/ui/button';
import { Md } from '@/components/ui/md';
import { Sheet } from '@/components/ui/overlay';
import { Card, Empty, ErrorState, Pill, Skeleton } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { ApiError } from '@/lib/api/client';
import {
  CONNECTION_FA, CONNECTION_ICON, CONNECTION_KINDS, CONNECTION_STATE, guideText, useCompanyConnections, useConnectionActions, useConnectionGuide,
  type Connection, type ConnectionKind,
} from '@/lib/api/v29';
import { useNow } from '@/lib/store';
import { ago, cx } from '@/lib/format';
import { FaText, fig } from './text';

const field = 'h-11 w-full rounded-[10px] border border-strong bg-tile px-3 text-[14px] text-ink outline-none focus:border-gold-ink';
const KEY_FA: Record<string, string> = {
  clicks: 'کلیک', impressions: 'نمایش در گوگل', users: 'کاربر', sessions: 'بازدید', reach: 'بازدید', followers: 'دنبال‌کننده', members: 'عضو', views: 'دیده‌شدن',
  score: 'امتیاز سرعت', installs: 'نصب', subscribers: 'مشترک', interest: 'علاقه',
};
export const keyFa = (k: string) => KEY_FA[k] ?? k;
export const kindFa = (k: string) => CONNECTION_FA[k as ConnectionKind] ?? k;

/** The latest day's figures of a connection, each with its trend over the days it has. */
function Daily({ c }: { c: Connection }) {
  const keys = [...new Set(c.daily.map((d) => d.key))];
  if (!keys.length) return null;
  return (
    <div className="flex flex-wrap gap-2">
      {keys.map((k) => {
        const vs = c.daily.filter((d) => d.key === k).sort((a, b) => a.day.localeCompare(b.day));
        const last = vs.at(-1)!;
        return (
          <span key={k} className="inline-flex items-center gap-2 rounded-[10px] bg-tile px-2.5 py-1.5 text-[12px]">
            <span className="text-muted">{keyFa(k)}</span>
            <span className="fig font-semibold text-ink">{fig(last.value)}</span>
            <Spark values={vs.map((v) => v.value)} width={44} height={16} />
          </span>
        );
      })}
    </div>
  );
}

function Row({ c, onOpen }: { c: Connection; onOpen: () => void }) {
  const now = useNow();
  const st = CONNECTION_STATE[c.state] ?? { fa: c.state, tone: 'neutral' as const };
  return (
    <li className="flex flex-col gap-2 border-t border-div px-1 py-3 first:border-0">
      <div className="flex flex-wrap items-center gap-3">
        <span className="flex size-9 flex-none items-center justify-center rounded-[10px] bg-tile text-silver-ink"><Icon name={CONNECTION_ICON[c.kind] ?? 'globe'} size={18} /></span>
        <span className="flex min-w-0 flex-[1_1_12rem] flex-col">
          <span className="text-[14px] font-semibold">{kindFa(c.kind)}</span>
          <span className="truncate text-[12px] text-muted"><FaText text={c.label_fa} /></span>
        </span>
        <Pill tone={st.tone} dot>{st.fa}</Pill>
        <Button size="sm" variant={c.state === 'connected' ? 'secondary' : 'primary'} icon={c.state === 'connected' ? 'settings' : 'globe'} onClick={onOpen} aria-label={`${c.state === 'connected' ? 'تنظیم' : 'وصل کن'}: ${kindFa(c.kind)}`}>
          {c.state === 'connected' ? 'تنظیم' : 'وصل کن'}
        </Button>
      </div>
      <div className="flex flex-col gap-1.5 ps-12">
        {c.last_error_fa ? <span className="text-[12px] leading-5 text-neg"><FaText text={c.last_error_fa} /></span> : null}
        <span className="text-[11px] text-muted">{c.last_read_at ? <>آخرین خواندن: {now ? ago(c.last_read_at, now) : ''}</> : 'هنوز خوانده نشده'}</span>
        <Daily c={c} />
      </div>
    </li>
  );
}

/** A company's connections, in §29.12's order of work; a kind the hub does not list yet is shown as not connected. */
export function CompanyConnections({ code }: { code: string }) {
  const q = useCompanyConnections(code);
  const [open, setOpen] = useState<string | null>(null);
  if (q.isLoading) return <Skeleton className="h-72 rounded-[16px]" />;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (q.data === null) return <Card><Empty icon="globe" title="اتصال‌ها هنوز آماده نیست" body="بعد از به‌روزرسانی ستاد، هر اتصال با وضعیت و عددهای روزانه‌اش این‌جا میاید." /></Card>;
  const list = q.data ?? [];
  if (!list.length) return <Card><Empty icon="globe" title="اتصالی برای این شرکت نیست" body="شرکتی که صفحه یا سایت دارد، اتصال‌هایش این‌جا میاید." /></Card>;
  const ordered = [...list].sort((a, b) => CONNECTION_KINDS.indexOf(a.kind) - CONNECTION_KINDS.indexOf(b.kind));
  const on = list.filter((c) => c.state === 'connected').length;
  return (
    <Card className="flex flex-col gap-1 p-4">
      <div className="flex items-center gap-2 pb-1">
        <span className="flex-1 text-[13px] text-sec"><span className="fig">{on}</span> از <span className="fig">{list.length}</span> اتصال وصل است؛ عددها هر روز با کد خوانده میشوند، بی حدس.</span>
      </div>
      <ul className="flex flex-col">{ordered.map((c) => <Row key={c.kind} c={c} onOpen={() => setOpen(c.kind)} />)}</ul>
      {open ? <ConnectionSheet company={code} kind={open} onClose={() => setOpen(null)} /> : null}
    </Card>
  );
}

/** The one-page guide, the settings and the write-only secret of one connection. */
export function ConnectionSheet({ company, kind, onClose }: { company: string; kind: string; onClose: () => void }) {
  const toast = useToast();
  const list = useCompanyConnections(company);
  const g = useConnectionGuide(kind);
  const act = useConnectionActions(company, kind);
  const c = (list.data ?? []).find((x) => x.kind === kind) ?? null;
  const fields = g.data?.config?.length ? g.data.config : Object.keys(c?.config ?? {}).map((k) => ({ key: k, label_fa: k, placeholder: null, hint_fa: null }));
  // What the owner typed over what is stored.
  const [config, setConfig] = useState<Record<string, string>>({});
  const value = (k: string) => config[k] ?? (c?.config[k] == null ? '' : String(c.config[k]));
  const [secret, setSecret] = useState('');
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);
  const wantsSecret = g.data ? g.data.secret !== false && g.data.secret_fa !== null : true;
  const st = c ? CONNECTION_STATE[c.state] : null;
  const err = (e: unknown, fallback: string) => toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : fallback });
  return (
    <Sheet open onOpenChange={(o) => !o && onClose()} title={g.data?.title_fa ?? `وصل کردن ${kindFa(kind)}`} description={c ? <FaText text={c.label_fa} /> : undefined} width={560}>
      <div className="flex flex-col gap-5">
        {st ? <div className="flex flex-wrap items-center gap-2"><Pill tone={st.tone} dot>{st.fa}</Pill>{c?.last_error_fa ? <span className="text-[12px] text-neg"><FaText text={c.last_error_fa} /></span> : null}</div> : null}
        <section className="flex flex-col gap-2" aria-label="راهنما">
          <h3 className="text-[13px] font-semibold text-sec">راهنما</h3>
          {g.isLoading ? <Skeleton className="h-28" /> : g.data ? <div className="hq-prose rounded-[12px] bg-tile p-3 text-[14px]"><Md text={guideText(g.data)} /></div>
            : <p className="text-[13px] text-muted">راهنمای این اتصال هنوز در ستاد نیست.</p>}
        </section>
        {fields.length ? (
          <form className="flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); act.config.mutate(Object.fromEntries(fields.map((f) => [f.key, value(f.key).trim()])), { onSuccess: () => toast({ tone: 'ok', text: 'تنظیم ذخیره شد.' }), onError: (x) => err(x, 'تنظیم ذخیره نشد.') }); }}>
            <h3 className="text-[13px] font-semibold text-sec">تنظیم</h3>
            {fields.map((f) => (
              <label key={f.key} className="flex flex-col gap-1.5">
                <span className="text-[13px] text-sec">{f.label_fa}</span>
                <input dir="ltr" value={value(f.key)} onChange={(e) => setConfig({ ...config, [f.key]: e.target.value })} placeholder={f.placeholder ?? undefined} className={cx(field, 'fig text-left')} />
                {f.hint_fa ? <span className="text-[11px] text-muted"><FaText text={f.hint_fa} /></span> : null}
              </label>
            ))}
            <Button type="submit" variant="secondary" icon="seal" loading={act.config.isPending} className="self-start">ذخیره‌ی تنظیم</Button>
          </form>
        ) : null}
        {wantsSecret ? (
          <form className="flex flex-col gap-2" onSubmit={(e) => {
            e.preventDefault();
            if (!secret.trim()) return;
            act.secret.mutate(secret.trim(), {
              onSuccess: () => { setSecret(''); toast({ tone: 'ok', text: 'رمز در گاوصندوق ستاد ثبت شد؛ هیچ‌وقت دوباره نشان داده نمیشود.' }); },
              onError: (x) => err(x, 'رمز ثبت نشد.'),
            });
          }}>
            <h3 className="flex items-center gap-1.5 text-[13px] font-semibold text-sec"><Icon name="lock" size={14} />{g.data?.secret_fa ?? 'رمز'}</h3>
            <span className="text-[12px] text-muted">فقط نوشتنی: با اثر انگشت ثبت میشود و هرگز برنمیگردد. {c ? (c.secret === 'set' ? 'رمزی ثبت شده است؛ رمز تازه جایش مینشیند.' : 'هنوز رمزی ثبت نشده.') : ''}</span>
            <div className="flex flex-wrap gap-2">
              <input type="password" autoComplete="new-password" spellCheck={false} aria-label={g.data?.secret_fa ?? 'رمز'} value={secret} onChange={(e) => setSecret(e.target.value)} dir="ltr" className={cx(field, 'fig min-w-0 flex-[1_1_14rem] text-left')} />
              <Button type="submit" variant="primary" icon="lock" disabled={!secret.trim()} loading={act.secret.isPending}>ثبت رمز</Button>
            </div>
          </form>
        ) : null}
        <div className="flex flex-col gap-2 border-t border-div pt-4">
          <Button variant="secondary" icon="refresh" className="self-start" loading={act.test.isPending}
            onClick={() => act.test.mutate(undefined, {
              onSuccess: (r) => setResult({ ok: r?.ok !== false && r?.state !== 'error', text: r?.message_fa ?? (r?.ok === false ? 'وصل نشد.' : 'اتصال درست است.') }),
              onError: (x) => err(x, 'آزمایش انجام نشد.'),
            })}>آزمایش اتصال</Button>
          {result ? <span role="status" className={cx('text-[13px]', result.ok ? 'text-pos' : 'text-neg')}><FaText text={result.text} /></span> : null}
        </div>
      </div>
    </Sheet>
  );
}
