'use client';

import { useMemo, useState, useSyncExternalStore } from 'react';
import { Icon } from '@/components/icon';
import { Button } from '@/components/ui/button';
import { Dialog } from '@/components/ui/overlay';
import { Card, Empty, FilterChip, PageHeader, Pill } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { inputCls } from '@/components/v21/bits';
import type { IconName } from '@/generated/icons';
import { isMock } from '@/lib/api/client';
import { APP, KEEP_VERSIONS, MAX, errorLog, local, matches, utc, type ErrorEntry, type Level } from '@/lib/errorlog';
import { cx } from '@/lib/format';

// «خطاخوان» (0.3.0, 0.4.0; the Android app's ui/settings/ErrorLog.kt): this version's log, from the session that opened it, newest first,
// each entry with its exact time (Tehran and UTC, to the millisecond), its sequence number and everything needed to trace it — the request
// id the hub wrote in its own log above all; filtered by level and searched. A new version starts empty; the last versions' logs are kept
// apart under «نسخه‌های قبلی». Copy or download as a plain-text report.

type Tone = 'neg' | 'warn' | 'neutral' | 'pos' | 'lapis';
const KINDS: Record<string, { fa: string; tone: Tone; icon: IconName }> = {
  http: { fa: 'خطای سرور', tone: 'warn', icon: 'server' },
  network: { fa: 'اتصال', tone: 'neutral', icon: 'offline' },
  unreachable: { fa: 'هاب در دسترس نبود', tone: 'warn', icon: 'server' },
  hub: { fa: 'هاب برگشت', tone: 'pos', icon: 'server' },
  stream: { fa: 'استریم زنده', tone: 'neutral', icon: 'refresh' },
  crash: { fa: 'خطای صفحه', tone: 'neg', icon: 'urgent' },
  passkey: { fa: 'اثر انگشت و passkey', tone: 'warn', icon: 'lock' },
  speech: { fa: 'تشخیص گفتار', tone: 'neutral', icon: 'mic' },
  session: { fa: 'شروع پنل', tone: 'lapis', icon: 'info' },
};
const kindOf = (e: ErrorEntry) => KINDS[e.kind] ?? { fa: e.title ?? e.kind, tone: 'neutral' as Tone, icon: 'info' as IconName };
const LEVELS: Array<[Level, string]> = [['error', 'خطا'], ['warning', 'هشدار'], ['info', 'اطلاع']];
const levelFa = (l: string) => LEVELS.find(([k]) => k === l)?.[1] ?? l;
const levelTone = (l: string): Tone => (l === 'error' ? 'neg' : l === 'warning' ? 'warn' : 'lapis');
const TONE: Record<Tone, string> = { neg: 'bg-neg-soft text-neg', warn: 'bg-warn-soft text-warn', neutral: 'bg-tile text-sec', pos: 'bg-pos-soft text-pos', lapis: 'bg-lapis-soft text-lapis' };

function Fact({ label, value, prose }: { label: string; value: string; prose?: boolean }) {
  return (
    <div className="flex gap-3">
      <span className="w-28 flex-none pt-px text-[11px] text-muted">{label}</span>
      <span className={cx('min-w-0 flex-1 whitespace-pre-wrap break-words text-[12px] text-ink', !prose && 'fig')} dir={prose ? undefined : 'ltr'} style={prose ? undefined : { textAlign: 'right' }}>{value}</span>
    </div>
  );
}

/** One entry: what it was and where, its level, number and time at a glance; everything else when opened. */
function EntryCard({ e }: { e: ErrorEntry }) {
  const [open, setOpen] = useState(false);
  const k = kindOf(e);
  const line = e.kind === 'unreachable'
    ? `${local(e.at).slice(11)} – ${local(e.lastAt ?? e.at).slice(11)} · ${Object.entries(e.tally ?? {}).sort((a, b) => b[1] - a[1]).map(([x, n]) => `${x}×${n}`).join(', ')}`
    : e.path ? `${[e.method, e.path].filter(Boolean).join(' ')}${e.status != null ? ` → ${e.status}` : ''}` : e.detail ?? e.title ?? '';
  return (
    <Card className="flex flex-col p-0">
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} className="flex items-center gap-3 rounded-[16px] p-3.5 text-start transition-colors hover:bg-hover">
        <span className={cx('flex size-8 flex-none items-center justify-center rounded-full', TONE[k.tone])}><Icon name={k.icon} size={16} /></span>
        <span className="flex min-w-0 flex-1 flex-col gap-0.5">
          <span className="flex items-center gap-1.5"><span className="truncate text-[13px] font-semibold">{k.fa}</span>{e.count > 1 ? <span className="text-[11px] text-muted">{e.kind === 'unreachable' ? `${e.count} درخواست` : `${e.count} بار`}</span> : null}</span>
          <span className="fig line-clamp-2 text-[12px] text-sec" dir="ltr" style={{ textAlign: 'right' }}>{line}</span>
        </span>
        <span className="flex flex-none flex-col items-end gap-1">
          <Pill tone={levelTone(e.level)} dot>{levelFa(e.level)}</Pill>
          <span className="fig text-[11px] text-muted">#{e.id} · {local(e.lastAt ?? e.at).slice(11, 19)}</span>
        </span>
      </button>
      {open ? (
        <div className="hq-rise flex flex-col gap-1.5 border-t border-div p-4">
          <Fact label="زمان (تهران)" value={local(e.at) + (e.lastAt && e.lastAt !== e.at ? `  →  ${local(e.lastAt)}` : '')} />
          <Fact label="زمان (UTC)" value={utc(e.at) + (e.lastAt && e.lastAt !== e.at ? `  →  ${utc(e.lastAt)}` : '')} />
          <Fact label="شماره و سطح" value={`#${e.id} · ${e.level}${e.count > 1 ? ` · ×${e.count}` : ''}`} />
          <Fact label="نسخه‌ی پنل" value={e.app} />
          {e.screen ? <Fact label="صفحه" value={e.screen} /> : null}
          {e.foreground != null || e.network ? <Fact label="زبانه و شبکه" value={[e.foreground == null ? null : e.foreground ? 'foreground' : 'background', e.network].filter(Boolean).join(' · ')} /> : null}
          {e.path ? <Fact label="درخواست" value={[e.method, e.path].filter(Boolean).join(' ')} /> : null}
          {e.status != null ? <Fact label="کد پاسخ" value={String(e.status)} /> : null}
          {e.durationMs != null ? <Fact label="مدت" value={`${e.durationMs} ms`} /> : null}
          {e.code || e.title ? <Fact label="خطا" value={[e.code, e.title].filter(Boolean).join(' — ')} /> : null}
          {e.message ? <Fact label="پیام سرور" value={e.message} prose={/[؀-ۿ]/.test(e.message)} /> : null}
          {e.tally && Object.keys(e.tally).length ? <Fact label="شکست‌ها" value={Object.entries(e.tally).sort((a, b) => b[1] - a[1]).map(([x, n]) => `${x} ×${n}`).join(', ')} /> : null}
          {e.paths?.length ? <Fact label="درخواست‌ها" value={e.paths.join('\n')} /> : null}
          {e.detail ? <Fact label="جزئیات" value={e.detail} /> : null}
          {e.requestId ? <Fact label="شناسه‌ی درخواست" value={e.requestId} /> : null}
          {e.headers && Object.keys(e.headers).length ? <Fact label="سرآیندها" value={Object.entries(e.headers).map(([h, v]) => `${h}: ${v}`).join('\n')} /> : null}
          {e.breadcrumbs?.length ? <Fact label="پیش از آن" value={e.breadcrumbs.join('\n')} /> : null}
          {e.stack ? (
            <>
              <span className="pt-1 text-[11px] text-muted">ردِ پشته</span>
              <pre dir="ltr" className="fig overflow-x-auto rounded-[10px] bg-tile p-3 text-left text-[11px] leading-5 text-sec">{e.stack}</pre>
            </>
          ) : null}
        </div>
      ) : null}
    </Card>
  );
}

const EMPTY: ErrorEntry[] = [];
export default function ErrorLogPage() {
  const toast = useToast();
  const current = useSyncExternalStore(errorLog.subscribe, errorLog.list, () => EMPTY);
  const [version, setVersion] = useState<string | null>(null);
  const [versions, setVersions] = useState(false);
  const [level, setLevel] = useState<Level | null>(null);
  const [q, setQ] = useState('');
  const [confirm, setConfirm] = useState(false);
  const archives = useMemo(() => errorLog.archives(), [current.length, version]); // eslint-disable-line react-hooks/exhaustive-deps
  const entries = version == null ? current : archives.find((a) => a.app === version)?.entries ?? [];
  const shown = entries.filter((e) => (!level || e.level === level) && matches(e, q, kindOf(e).fa));
  const report = () => errorLog.report(shown, version ?? APP);
  const copy = async () => {
    try { await navigator.clipboard.writeText(report()); toast({ tone: 'ok', text: 'گزارش کپی شد؛ برای توسعه‌دهنده بفرست.' }); } catch { toast({ tone: 'error', text: 'مرورگر اجازه‌ی کپی نداد؛ «دریافت فایل» را بزن.' }); }
  };
  const download = () => {
    const stamp = new Date().toISOString().slice(0, 16).replace(/[-:T]/g, '').replace(/^(\d{8})(\d{4})$/, '$1-$2');
    const url = URL.createObjectURL(new Blob([report()], { type: 'text/plain;charset=utf-8' }));
    const a = Object.assign(document.createElement('a'), { href: url, download: `coinepro-hq-web-errors-${stamp}.txt` });
    document.body.append(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1_000);
  };
  return (
    <>
      <PageHeader eyebrow="ردّ هر خطا، با زمان دقیق و هرچه برای پیدا کردنش لازم است؛ فقط در همین مرورگر" title="خطاخوان" actions={<>
        <Button size="sm" icon="report" disabled={!shown.length} onClick={copy}>کپی</Button>
        <Button size="sm" icon="download" disabled={!shown.length} onClick={download}>دریافت فایل</Button>
        {version == null ? <Button size="sm" variant="ghost" icon="close" disabled={!current.length} onClick={() => setConfirm(true)}>پاک کردن</Button> : null}
      </>} />
      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(260px,340px)]">
        <div className="flex min-w-0 flex-col gap-3">
          <div className="flex flex-col gap-3 md:flex-row md:items-center">
            <div className="no-scrollbar -mx-1 flex gap-2 overflow-x-auto px-1">
              <FilterChip selected={!level} onClick={() => setLevel(null)} count={entries.length}>همه</FilterChip>
              {LEVELS.map(([k, l]) => <FilterChip key={k} selected={level === k} onClick={() => setLevel(level === k ? null : k)} count={entries.filter((e) => e.level === k).length}>{l}</FilterChip>)}
            </div>
            <input value={q} onChange={(e) => setQ(e.target.value)} maxLength={80} placeholder="جست‌وجو: مسیر، کد، شناسه‌ی درخواست، صفحه…" aria-label="جست‌وجو در خطاخوان" className={cx(inputCls, 'md:max-w-sm')} />
          </div>
          {!shown.length ? (
            <Card>{entries.length ? <Empty icon="filter" title="چیزی با این فیلتر نیست" /> : <Empty icon="seal" title="خطایی ثبت نشده" body="اگر جایی خطایی دیدی، این‌جا با جزئیاتش میاید." />}</Card>
          ) : <div className="flex flex-col gap-2">{shown.map((e) => <EntryCard key={`${version ?? 'now'}-${e.id}`} e={e} />)}</div>}
        </div>
        <div className="flex flex-col gap-3 lg:sticky lg:top-20">
          {/* Which version this log belongs to, and the way to the ones before. */}
          <Card className="flex flex-col gap-3 p-4">
            <div className="flex items-center gap-3">
              <span className="text-sec"><Icon name="code" size={18} /></span>
              <span className="flex min-w-0 flex-1 flex-col">
                <span className="text-[13px] font-semibold">{version == null ? 'نسخه‌ی ' : 'نسخه‌ی قبلی '}<span className="fig">{version ?? APP}</span></span>
                <span className="text-[12px] text-muted">{version == null ? `هر نسخه‌ی تازه با خطاخوان خالی شروع میشود؛ ${entries.length} مورد از شروع این نسخه.` : `فقط خواندنی؛ ${entries.length} مورد. خطاخوان نسخه‌ی فعلی جداست.`}</span>
              </span>
            </div>
            {version != null ? <Button variant="text" size="sm" className="self-start" onClick={() => setVersion(null)}>نسخه‌ی فعلی</Button>
              : archives.length ? <Button variant="text" size="sm" className="self-start" onClick={() => setVersions(!versions)}>نسخه‌های قبلی</Button> : null}
            {versions && version == null ? (
              <div className="flex flex-col gap-1.5">
                {archives.map((a) => (
                  <button key={a.app} type="button" onClick={() => { setVersion(a.app); setVersions(false); }} className="flex items-center gap-2 rounded-[10px] bg-tile px-3 py-2.5 text-start hover:bg-hover">
                    <span className="fig flex-1 text-[12px]">{a.app}</span><span className="text-[12px] text-muted">{a.entries.length} مورد</span><Icon name="next" size={14} mirror />
                  </button>
                ))}
              </div>
            ) : null}
          </Card>
          {isMock ? (
            <Card className="flex flex-col gap-2 p-4">
              <span className="text-[13px] font-semibold">نمایشی: راه‌اندازی دوباره‌ی هاب</span>
              <span className="text-[12px] text-muted">هشت ثانیه همه‌ی درخواست‌ها ۵۰۲ میگیرند؛ نوار آرام بالای صفحه و یک مورد «هاب در دسترس نبود» را ببین.</span>
              <Button size="sm" variant="secondary" icon="refresh" className="self-start" onClick={async () => (await import('@/lib/api/mock-v21')).simulateRestart()}>نمایش</Button>
            </Card>
          ) : null}
          <p className="px-1 text-[11px] leading-5 text-muted">
            هر مورد با زمان (تهران و UTC، تا هزارم ثانیه)، شماره‌ی ترتیب، نسخه، صفحه، شبکه، مسیر درخواست (شناسه‌ها پوشیده)، مدت، کد پاسخ، پیام سرور و شناسه‌ی درخواست ثبت میشود؛
            هیچ توکن، کلید، رمز، کوکی، متن پیام یا داده‌ی مشتری ثبت نمیشود. حداکثر {MAX} مورد در هر نسخه، و خطاخوان {KEEP_VERSIONS} نسخه‌ی قبلی نگه داشته میشود.
          </p>
        </div>
      </div>
      <Dialog open={confirm} onOpenChange={setConfirm} title="خطاخوان این نسخه پاک شود؟" actions={<>
        <Button variant="danger" onClick={() => { errorLog.clear(); setConfirm(false); toast({ tone: 'info', text: 'خطاخوان پاک شد.' }); }}>پاک کن</Button>
        <Button variant="ghost" onClick={() => setConfirm(false)}>نه</Button>
      </>}>
        همه‌ی {current.length} مورد این نسخه از همین مرورگر پاک میشوند (نسخه‌های قبلی میمانند). اگر هنوز برای توسعه‌دهنده نفرستاده‌ای، اول کپی کن.
      </Dialog>
    </>
  );
}
