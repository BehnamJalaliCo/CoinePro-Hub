'use client';

// ⟨1.8⟩ §26.5 `server.map` read for the owner: the machine, its resources, what runs on it and what it serves (Android: Server.kt MapView).

import { useState, type ReactNode } from 'react';
import { Icon } from '@/components/icon';
import { Button } from '@/components/ui/button';
import { Card, Pill } from '@/components/ui/primitives';
import { portPublic, runningContainers, type ServerMap } from '@/lib/api/v26';
import { ago, cx, until } from '@/lib/format';
import { CodeBlock, UsageBar } from './bits';

function Section({ title, count, total, limit = 6, children }: { title: string; count?: number | null; total: number; limit?: number; children: (all: boolean) => ReactNode }) {
  const [all, setAll] = useState(false);
  return (
    <Card className="flex flex-col gap-2 p-4">
      <div className="flex items-center gap-2">
        <h3 className="flex-1 text-[13px] font-semibold text-gold-ink">{title}</h3>
        {count != null ? <span className="text-[12px] text-muted">{count}</span> : null}
      </div>
      <div className="flex flex-col gap-2">{children(all)}</div>
      {total > limit ? <Button variant="text" size="sm" className="self-start" onClick={() => setAll(!all)}>{all ? 'کمتر' : `همه (${total})`}</Button> : null}
    </Card>
  );
}

const Dot = ({ on }: { on: boolean | null | undefined }) => <span className={cx('size-[7px] flex-none rounded-full', on === true ? 'bg-pos' : on === false ? 'bg-neg' : 'bg-[var(--hq-text-muted)]')} />;
const Tag = ({ children, tone }: { children: ReactNode; tone?: 'warn' }) => <span className={cx('fig inline-flex items-center rounded-[6px] px-1.5 py-px text-[12px]', tone === 'warn' ? 'bg-warn-soft text-ink' : 'bg-tile text-sec')}>{children}</span>;

const uptimeFa = (s: number) => (s >= 86_400 ? `${Math.floor(s / 86_400)} روز` : s >= 3_600 ? `${Math.floor(s / 3_600)} ساعت` : `${Math.floor(s / 60)} دقیقه`);
/** A time the map wrote: an instant ("in 3 hours", "2 hours ago"), or its own words kept as written. */
const whenFa = (v: string | null, future: boolean) => (!v ? null : !v.includes('T') || Number.isNaN(Date.parse(v)) ? v : future ? until(v) : ago(v));
const take = <T,>(xs: T[], all: boolean) => (all ? xs : xs.slice(0, 6));

export function MapView({ m, refreshing, onRefresh }: { m: ServerMap; refreshing?: boolean; onRefresh?: () => void }) {
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <span className="flex-1 text-[12px] text-muted">{m.at ? `نقشه‌ی ${ago(m.at)}` : 'آخرین نقشه'}</span>
        {onRefresh ? <Button variant="text" size="sm" icon="refresh" loading={refreshing} onClick={onRefresh}>نقشه‌ی تازه</Button> : null}
      </div>
      <div className="grid items-start gap-3 lg:grid-cols-2">
        <Card className="flex flex-col gap-3 p-4">
          <h3 className="text-[13px] font-semibold text-gold-ink">سیستم</h3>
          <div className="flex flex-wrap items-center gap-x-3.5 gap-y-1.5 text-[12px]">
            {m.os ? <span className="fig text-ink">{m.os}</span> : null}
            {m.kernel ? <span className="fig text-muted">{m.kernel}</span> : null}
            {m.hostname ? <span className="fig text-muted">{m.hostname}</span> : null}
            {m.cpus != null ? <span className="text-sec"><span className="fig">{m.cpus}</span> vCPU</span> : null}
            {m.load != null ? <span className="text-sec">بار <span className="fig">{m.load.toFixed(2)}</span></span> : null}
            {m.uptimeS != null ? <span className="text-sec">روشن از {uptimeFa(m.uptimeS)} پیش</span> : null}
          </div>
          {m.disks.length || m.memory ? (
            <div className="flex flex-col gap-2.5">
              {m.disks.map((d) => <UsageBar key={d.label} u={d} label={`دیسک ${d.label}`} />)}
              {m.memory ? <UsageBar u={m.memory} label="رم" /> : null}
              {m.swap ? <UsageBar u={m.swap} label="حافظه‌ی swap" /> : null}
            </div>
          ) : null}
        </Card>
        {m.containers.length ? (
          <Section title="کانتینرها" total={m.containers.length}>{(all) => (<>
            <span className="text-[12px] text-muted">{runningContainers(m)} در حال اجرا از {m.containers.length}</span>
            {take([...m.containers].sort((a, b) => Number(b.state === 'running') - Number(a.state === 'running')), all).map((x) => (
              <div key={x.name} className="flex items-center gap-2">
                <Dot on={x.state === 'running'} />
                <div className="flex min-w-0 flex-1 flex-col">
                  <span className="fig truncate text-[12px] font-semibold text-ink">{x.name}</span>
                  {x.image ? <span className="fig truncate text-[11px] text-muted">{x.image}</span> : null}
                </div>
                {x.project ? <Tag>{x.project}</Tag> : null}
                {x.status ?? x.health ? <span className={cx('fig text-[11px]', x.health === 'unhealthy' ? 'text-neg' : 'text-muted')}>{x.status ?? x.health}</span> : null}
              </div>
            ))}
          </>)}</Section>
        ) : null}
        {m.compose.length ? (
          <Section title="پروژه‌های compose" count={m.compose.length} total={m.compose.length}>{(all) => take(m.compose, all).map((p) => {
            // §26.5 lists a project's services, not how many run: counted from the containers of the same project.
            const mine = m.containers.filter((c) => c.project === p.project);
            const running = p.running ?? (mine.length ? mine.filter((c) => c.state === 'running').length : null);
            return (
              <div key={p.project} className="flex items-center gap-2">
                <div className="flex min-w-0 flex-1 flex-col">
                  <span className="fig text-[12px] font-semibold text-ink">{p.project}</span>
                  {p.dir ? <span className="fig truncate text-[11px] text-muted">{p.dir}</span> : null}
                </div>
                {p.services != null ? <span className={cx('fig text-[12px]', running === p.services ? 'text-pos' : 'text-warn')}>{running ?? '?'}/{p.services}</span> : null}
              </div>
            );
          })}</Section>
        ) : null}
        {m.timers.length || m.units.length ? (
          <Section title="systemd" count={m.timers.length + m.units.length} total={m.timers.length}>{(all) => (<>
            {m.timers.length ? <span className="text-[12px] text-muted">تایمرها</span> : null}
            {take(m.timers, all).map((t) => (
              <div key={t.unit} className="flex items-center gap-2">
                <span className="text-sec"><Icon name="time" size={14} /></span>
                <div className="flex min-w-0 flex-1 flex-col">
                  <span className="fig text-[12px] font-semibold text-ink">{t.unit}</span>
                  {t.activates ? <span className="fig text-[11px] text-muted">→ {t.activates}</span> : null}
                </div>
                {whenFa(t.next, true) ? <span className="text-[11px] text-sec">{whenFa(t.next, true)}</span> : null}
              </div>
            ))}
            {m.units.length ? <>
              <span className="text-[12px] text-muted">سرویس‌ها</span>
              <div className="flex flex-wrap gap-1.5">
                {m.units.map((u) => <span key={u.name} className="inline-flex items-center gap-1.5 rounded-[8px] bg-tile px-2 py-0.5"><Dot on={u.state ? u.state === 'active' || u.state === 'running' : null} /><span className="fig text-[12px] text-sec">{u.name}</span></span>)}
              </div>
            </> : null}
          </>)}</Section>
        ) : null}
        {m.cron.length ? (
          <Section title="cron" count={m.cron.length} total={m.cron.length}>{(all) => take(m.cron, all).map((x, i) => (
            <div key={i} className="flex flex-col gap-1">
              <div className="flex items-center gap-2">
                <span className="fig text-[12px] font-semibold text-gold-ink">{x.schedule}</span>
                {x.user ? <span className="fig text-[11px] text-muted">{x.user}</span> : null}
              </div>
              <CodeBlock text={x.command} />
            </div>
          ))}</Section>
        ) : null}
        {m.ports.length ? (
          <Section title="پورت‌های باز" count={m.ports.length} total={0}>{() => (<>
            <div className="flex flex-wrap gap-1.5">
              {m.ports.map((p) => { const pub = portPublic(p); return <Tag key={`${p.port}/${p.proto}/${p.address}`} tone={pub ? 'warn' : undefined}>{`${p.port}/${p.proto}${p.process ? ` ${p.process}` : ''}${pub ? '' : ` · ${p.address}`}`}</Tag>; })}
            </div>
            <span className="text-[11px] text-muted">زرد: روی همه‌ی آدرس‌ها باز است؛ بقیه فقط محلی یا شبکه‌ی خصوصی.</span>
          </>)}</Section>
        ) : null}
        {m.repos.length ? (
          <Section title="ریپوها" count={m.repos.length} total={m.repos.length}>{(all) => take(m.repos, all).map((x) => (
            <div key={x.path} className="flex flex-col gap-0.5">
              <div className="flex items-center gap-2">
                <span className="text-sec"><Icon name="code" size={14} /></span>
                <span className="fig min-w-0 flex-1 truncate text-[12px] font-semibold text-ink">{x.path}</span>
                {x.dirty ? <Pill tone="warn">تغییر ثبت‌نشده</Pill> : null}
              </div>
              {x.remote ? <span className="fig truncate text-[11px] text-muted">{x.remote}</span> : null}
              {x.branch || x.head || x.lastCommitAt ? (
                <div className="flex flex-wrap items-center gap-2">
                  {x.branch || x.head ? <span className="fig text-[11px] text-sec">{[x.branch, x.head].filter(Boolean).join(' @ ')}</span> : null}
                  {whenFa(x.lastCommitAt, false) ? <span className="text-[11px] text-muted">آخرین commit {whenFa(x.lastCommitAt, false)}</span> : null}
                </div>
              ) : null}
            </div>
          ))}</Section>
        ) : null}
        {m.automations.length ? (
          <Section title="n8n و اتوماسیون‌ها" count={m.automations.length} total={m.automations.length}>{(all) => take(m.automations, all).map((a) => (
            <div key={`${a.kind}:${a.name}`} className="flex items-center gap-2">
              <Dot on={a.active} />
              <div className="flex min-w-0 flex-1 flex-col">
                <span className="truncate text-[13px] text-ink">{a.name}</span>
                {a.detail ? <span className="fig truncate text-[11px] text-muted">{a.detail}</span> : null}
              </div>
              <Tag>{a.kind}</Tag>
            </div>
          ))}</Section>
        ) : null}
        {m.sites.length ? (
          <Section title="سایت‌ها" count={m.sites.length} total={m.sites.length}>{(all) => take(m.sites, all).map((x) => (
            <div key={x.domain} className="flex items-center gap-2">
              <span className="text-sec"><Icon name="globe" size={14} /></span>
              <div className="flex min-w-0 flex-1 flex-col">
                <span className="fig text-[12px] font-semibold text-ink">{x.domain}</span>
                {x.upstream ? <span className="fig truncate text-[11px] text-muted">→ {x.upstream}{x.server ? ` · ${x.server}` : ''}</span> : null}
              </div>
              {x.tls === true ? <Pill tone="pos"><span className="fig">HTTPS</span></Pill> : x.tls === false ? <Pill tone="warn"><span className="fig">HTTP</span></Pill> : null}
            </div>
          ))}</Section>
        ) : null}
      </div>
    </div>
  );
}
