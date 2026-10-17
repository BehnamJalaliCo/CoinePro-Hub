'use client';

import Link from 'next/link';
import { type ComponentProps } from 'react';
import { Icon } from '@/components/icon';
import { Avatar } from '@/components/brand/avatar';
import { CompanyMark } from '@/components/brand/marks';
import { Bar, Pill, budgetTone } from '@/components/ui/primitives';
import type { CodeSession, Grant, SessionState, Workspace } from '@/lib/api/v13';
import { ACTOR_FA } from '@/lib/labels';
import { ago, cx, usd } from '@/lib/format';

type Tone = ComponentProps<typeof Pill>['tone'];

export const SESSION_STATE: Record<SessionState, { fa: string; tone: Tone; live?: boolean }> = {
  starting: { fa: 'در حال شروع', tone: 'lapis', live: true },
  working: { fa: 'در حال کار', tone: 'pos', live: true },
  waiting_approval: { fa: 'منتظر اجازه‌ی تو', tone: 'gold' },
  idle: { fa: 'منتظر راهنمایی', tone: 'neutral' },
  done: { fa: 'تمام شد', tone: 'silver' },
  failed: { fa: 'خطا', tone: 'neg' },
  stopped: { fa: 'متوقف', tone: 'warn' },
};
export const isOpen = (s: SessionState) => s !== 'done' && s !== 'failed' && s !== 'stopped';

export const ACTION_FA: Record<string, string> = {
  read: 'خواندن کد', edit: 'ویرایش', run: 'اجرای تست و فرمان', push_branch: 'push به شاخه‌ی جدا', open_pr: 'باز کردن PR',
};
export const APPROVAL_FA: Record<string, string> = {
  push_branch: 'push به شاخه', open_pr: 'باز کردن PR', command: 'فرمانی بیرون از فهرست مجاز',
};

export function StatePill({ state }: { state: SessionState }) {
  const s = SESSION_STATE[state];
  return <Pill tone={s.tone} live={s.live} dot={!s.live}>{s.fa}</Pill>;
}

export function companyOfWorkspace(list: Workspace[] | undefined, code: string): string {
  return list?.find((w) => w.code === code)?.company ?? code.split('-')[0] ?? 'HQ';
}

/** One session in a list: where, what, who drives it, what it has cost. */
export function SessionRow({ s, workspaces, grant }: { s: CodeSession; workspaces?: Workspace[]; grant?: Grant }) {
  const ws = workspaces?.find((w) => w.code === s.workspace);
  const cap = grant?.budget_usd ?? null;
  const pct = cap ? Math.min(100, (s.usage.usd / cap) * 100) : null;
  return (
    <Link
      href={`/workshop/${s.ref}`}
      className={cx('flex flex-col gap-2.5 rounded-[14px] px-4 py-3.5 transition-colors hover:bg-hover', s.state === 'waiting_approval' ? 'bg-gold-soft/60 ring-1 ring-[var(--hq-gold-ink)]/40' : 'bg-tile')}
    >
      <div className="flex items-start gap-3">
        <span className="mt-0.5 text-sec"><CompanyMark code={companyOfWorkspace(workspaces, s.workspace)} height={16} mono /></span>
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <span className="truncate text-[14px] font-semibold text-ink">{s.title}</span>
          <span className="flex flex-wrap items-center gap-x-2 text-[12px] text-muted">
            <span className="fig">{s.ref}</span>
            <span className="fig truncate">{ws?.repo.split('/')[1] ?? s.workspace}</span>
            {s.branch ? <span className="fig">{s.branch}</span> : null}
          </span>
        </div>
        <StatePill state={s.state} />
      </div>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[12px] text-sec">
        <span className="flex items-center gap-1.5"><Avatar kind={s.driver.kind} size={20} state={isOpen(s.state) && s.state !== 'idle' ? 'working' : 'idle'} />{ACTOR_FA(s.driver)}</span>
        <span className="flex-1" />
        {s.pr_url ? <span className="flex items-center gap-1 text-gold-ink"><Icon name="share" size={14} />PR</span> : null}
        <span className="text-muted">{ago(s.updated_at)}</span>
        <span className="fig">{usd(s.usage.usd)}{cap ? <span className="text-muted"> / {usd(cap, 0)}</span> : null}</span>
      </div>
      {pct != null && isOpen(s.state) ? <Bar pct={pct} tone={budgetTone(pct)} height={4} label={`بودجه‌ی ${s.ref}`} /> : null}
    </Link>
  );
}
