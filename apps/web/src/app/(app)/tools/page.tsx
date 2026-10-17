'use client';

import { Icon } from '@/components/icon';
import { CompanyMark } from '@/components/brand/marks';
import { Button } from '@/components/ui/button';
import { Card, PageHeader, Pill, SectionTitle, Skeleton, StatTile } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { ApiError } from '@/lib/api/client';
import { useAccounts, useCatalog, useEgress, useEgressSummary, useMcp, useMcpAction } from '@/lib/api/v14';
import { ago, cx, jTime } from '@/lib/format';
import { ROLE_FA } from '@/lib/labels';

const BLOCK_FA: Record<string, string> = { private_network: 'شبکه‌ی خصوصی (مسدود)', egress_limit: 'سقف (مسدود)', internal_data: 'داده‌ی داخلی (مسدود)' };

/** ابزارها و اینترنت (contract §18.7): agents reach the internet only through tools in the egress service; every request is logged.
 *  MCP servers come in only with the owner's seal. */
export default function ToolsPage() {
  const sum = useEgressSummary();
  const log = useEgress();
  const mcp = useMcp();
  const accounts = useAccounts();
  const catalog = useCatalog();
  const act = useMcpAction();
  const toast = useToast();
  const err = (e: unknown) => toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : e instanceof Error ? e.message : 'انجام نشد.' });
  const s = sum.data;
  return (
    <>
      <PageHeader eyebrow="تصمیم تو: اینترنت کامل برای ایجنت‌ها؛ مهم برآیند و کیفیت کار است" title="ابزارها و اینترنت">
        <p className="max-w-3xl text-[13px] leading-6 text-sec">جستجو، خواندن، مرورگر کامل و API بیرونی از درگاه خروجی؛ شبکه‌ی خصوصی و سرورهای همسایه بسته‌اند؛ تعهد بیرونی به نام هلدینگ (پرداخت، انتشار، پیام به آدم بیرونی، ساخت حساب) کارت تصمیم میشود.</p>
      </PageHeader>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {!s ? Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-[104px] rounded-[14px]" />) : (
          <>
            <StatTile label="درخواست امروز" value={<span className="fig">{s.requests.toLocaleString('en-US')}</span>} sub={<span className="fig">{(s.bytes_in / 1e6).toFixed(0)} MB</span>} />
            <StatTile label="مسدودشده" value={<span className="fig">{s.blocked}</span>} tone={s.blocked ? 'warn' : undefined} sub="شبکه‌ی خصوصی، داده‌ی داخلی، سقف" />
            <StatTile label="به مُهر تو رسید" value={<span className="fig">{s.needs_owner}</span>} sub="تعهد بیرونی ← کارت تصمیم" />
            <StatTile label="بیشترین ابزار" value={<span className="fig text-[18px]">{Object.entries(s.by_tool).sort((a, b) => b[1] - a[1])[0]?.[0]}</span>} sub={<span className="fig">{Object.entries(s.by_tool).sort((a, b) => b[1] - a[1])[0]?.[1]}</span>} />
          </>
        )}
      </div>
      <div className="grid grid-cols-1 items-start gap-4 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <Card className="flex flex-col gap-2 p-4">
          <SectionTitle title="آخرین درخواست‌ها" note="هر درخواست با ایجنت، ابزار، مقصد و نتیجه ثبت میشود" />
          {log.isLoading ? <Skeleton className="h-48" /> : (
            <ul className="flex flex-col">
              {(log.data?.items ?? []).map((e) => (
                <li key={e.id} className="flex items-center gap-3 border-b border-div py-2 text-[12px] last:border-0">
                  <span className="w-10 flex-none text-muted">{jTime(e.at)}</span>
                  {/* Phone: destination on top, who and which tool beneath; wider: one row. */}
                  <span className="flex min-w-0 flex-1 flex-col gap-0.5 sm:flex-row sm:items-center sm:gap-3">
                    <span className="fig min-w-0 truncate text-right text-ink sm:order-last sm:flex-1 sm:text-left">{e.method} {e.host}</span>
                    <span className="flex flex-none items-center gap-2 sm:gap-3"><CompanyMark code={e.company} height={12} mono /><span className="fig truncate text-sec sm:w-24">{e.actor}</span><span className="fig text-muted sm:w-24">{e.tool}</span></span>
                  </span>
                  {e.blocked_reason ? <Pill tone={e.blocked_reason.startsWith('needs_owner') ? 'gold' : 'neg'} dot>{e.blocked_reason.startsWith('needs_owner') ? 'به مُهر تو' : BLOCK_FA[e.blocked_reason] ?? e.blocked_reason}</Pill> : <span className={cx('fig', e.status < 400 ? 'text-pos' : 'text-neg')}>{e.status}</span>}
                </li>
              ))}
            </ul>
          )}
        </Card>
        <div className="flex min-w-0 flex-col gap-4">
          <Card className="flex flex-col gap-3 p-4">
            <SectionTitle title="سرورهای MCP" note="فقط با مُهر تو روشن میشوند؛ ابزار تازه‌ی هر سرور دوباره مُهر میخواهد" />
            {(mcp.data ?? []).map((m) => (
              <div key={m.key} className={cx('flex flex-col gap-2 rounded-[12px] p-3', m.status === 'pending' ? 'bg-gold-soft' : 'bg-tile')}>
                <div className="flex items-center gap-2"><Icon name="server" size={16} className="text-sec" /><span className="min-w-0 flex-1 text-[13px] font-semibold">{m.title_fa}</span>
                  <Pill tone={m.status === 'enabled' ? 'pos' : m.status === 'pending' ? 'gold' : 'neutral'} dot>{m.status === 'enabled' ? 'روشن' : m.status === 'pending' ? 'منتظر مُهر' : 'خاموش'}</Pill></div>
                <div className="flex flex-wrap gap-1">{m.tools.map((t) => <span key={t.name} className="fig rounded-full bg-card px-2 py-0.5 text-[11px] text-sec">{t.name} · {t.class}</span>)}</div>
                <div className="flex items-center gap-2 text-[11px] text-muted">
                  {m.companies === 'all' ? <span>همه‌ی شرکت‌ها</span> : <span className="flex items-center gap-2">{m.companies.map((c) => <CompanyMark key={c} code={c} height={12} mono />)}</span>}<span className="flex-1" />
                  {m.status === 'enabled' ? <Button size="sm" variant="ghost" onClick={() => act.disable.mutateAsync(m.key).catch(err)}>خاموش کن</Button>
                    : <Button size="sm" variant="primary" icon="seal" loading={act.enable.isPending} onClick={() => act.enable.mutateAsync(m.key).then(() => toast({ tone: 'ok', text: 'روشن شد.' })).catch(err)}>مُهر و روشن</Button>}
                </div>
              </div>
            ))}
          </Card>
          <Card className="flex flex-col gap-3 p-4">
            <SectionTitle title="حساب‌های سرویس" note="رمزشان را خودت روی سرور میگذاری؛ در لحظه‌ی خروج تزریق میشود و مدل نمیبیند" />
            {(accounts.data ?? []).map((a) => (
              <div key={a.key} className="flex items-center gap-3 text-[13px]">
                <Icon name="lock" size={16} className={a.has_secret ? 'text-pos' : 'text-muted'} />
                <span className="flex min-w-0 flex-1 flex-col"><span>{a.title_fa}</span><span className="fig self-start text-[11px] text-muted">{a.site}</span></span>
                <span className="text-[11px] text-muted">{a.has_secret ? (a.last_used_at ? ago(a.last_used_at) : 'آماده') : <code className="fig">make account-secret KEY={a.key}</code>}</span>
              </div>
            ))}
          </Card>
        </div>
      </div>
      <Card className="flex flex-col gap-2 p-4">
        <SectionTitle title="فهرست ابزارها" note="کلاس هر ابزار و نقش‌هایی که آن را دارند" />
        <div className="grid grid-cols-1 gap-x-6 sm:grid-cols-2">
          {(catalog.data ?? []).map((t) => (
            <div key={t.name} className="flex min-w-0 items-center gap-3 border-b border-div py-2 text-[12px]">
              <span className="fig w-32 flex-none text-ink sm:w-36">{t.name}</span><span className="fig w-14 flex-none text-gold-ink">{t.class}</span><span className="min-w-0 flex-1 truncate text-muted">{t.roles.map((r) => (r === 'all' ? 'همه' : ROLE_FA[r] ?? r)).join('، ')}</span>
            </div>
          ))}
        </div>
      </Card>
    </>
  );
}
