'use client';

import Link from 'next/link';
import type { ReactNode } from 'react';
import { Icon } from '@/components/icon';
import { Pill } from '@/components/ui/primitives';
import { RefChip } from '@/components/v17/bits';
import type { Schemas } from '@/lib/api/client';
import { fileUrl } from '@/lib/api/v13';
import type { CheckResult, EmailDraft, MediaFile, MediaPlacement, SeriesTarget } from '@/lib/api/v19';
import { cx, modelLabel, tokens } from '@/lib/format';
import { Block, CheckGrid, KIND_FA, PLACEMENT_FA, PUBLISH_ERROR, RenderPreview, Schedule } from './bits';
import { ExactEmail } from './legal';

type Decision = Schemas['Decision'];
const obj = (v: unknown) => (v && typeof v === 'object' ? (v as Record<string, unknown>) : {});

function Fact({ label, children, mono }: { label: string; children: ReactNode; mono?: boolean }) {
  return (
    <div className="flex min-w-0 flex-col gap-1 rounded-[12px] bg-tile p-3">
      <span className="text-[11px] text-muted">{label}</span>
      <span className={cx('min-w-0 break-words text-[14px] font-semibold text-ink', mono && 'fig')}>{children}</span>
    </div>
  );
}

/** `media_publish` (A3), assumed payload: the item, its render, each placement and how it goes out (`api` or by the owner's hand). */
type PublishPayload = {
  item: string; series: string | null; kind: string; title_fa: string; why: 'one_off' | 'check_failed' | 'not_auto' | 'no_api' | string;
  placements: Array<{ channel: string; placement: MediaPlacement; account: string; via: 'api' | 'manual'; blocked: string | null }>;
  render: MediaFile | null; checks: CheckResult[];
};
const WHY: Record<string, string> = {
  one_off: 'یک‌باره است؛ یک‌باره‌ها همیشه کارت‌اند.', check_failed: 'یک چک رد شده؛ انتشار خودکار نیست.', not_auto: 'برنامه‌اش انتشار خودکار ندارد.',
  no_api: 'این جای انتشار API رسمی ندارد: فایل را بردار و خودت بگذار.', series_not_sealed: 'برنامه‌اش مُهر نیست.',
};
function PublishBlock({ d }: { d: Decision }) {
  const p = obj(d.payload) as Partial<PublishPayload>;
  const manual = (p.placements ?? []).some((x) => x.via === 'manual');
  return (
    <Block title="انتشار رسانه">
      <div className="grid items-start gap-3 sm:grid-cols-[160px_minmax(0,1fr)]">
        {p.render ? <RenderPreview file={p.render} aspect={p.render.width && p.render.height ? `${p.render.width}:${p.render.height}` : '9:16'} label={`رندر ${p.item ?? ''}`} className="mx-auto w-full max-w-[160px]" /> : null}
        <div className="flex min-w-0 flex-col gap-2">
          <div className="flex flex-wrap items-center gap-2 text-[12px] text-sec">
            {p.item ? <Link href={`/media?item=${p.item}`} className="fig rounded-full bg-gold-soft px-2 py-0.5 text-gold-ink hover:underline">{p.item}</Link> : null}
            {p.series ? <RefChip r={p.series} note="برنامه" /> : <span>یک‌باره</span>}
            {p.kind ? <span>{KIND_FA[p.kind]?.fa ?? p.kind}</span> : null}
          </div>
          {p.why ? <p className="text-[13px] leading-6 text-ink">{WHY[p.why] ?? p.why}</p> : null}
          <ul className="flex flex-col gap-1.5">
            {(p.placements ?? []).map((x) => (
              <li key={`${x.account}-${x.placement}`} className="flex flex-wrap items-center gap-2 rounded-[10px] bg-tile px-3 py-2 text-[12px]">
                <span className="font-semibold text-ink">{PLACEMENT_FA[x.placement] ?? x.placement}</span><span className="fig text-muted">{x.account}</span><span className="flex-1" />
                {x.blocked ? <Pill tone="warn" icon="urgent">{PUBLISH_ERROR[x.blocked] ?? x.blocked}؛ این بار نه</Pill> : x.via === 'manual' ? <Pill tone="gold" icon="share">با دست تو</Pill> : <Pill tone="silver" icon="send">API رسمی</Pill>}
              </li>
            ))}
          </ul>
          {manual && p.render ? <a href={fileUrl(p.render.id)} download={p.render.name} className="inline-flex h-9 w-fit items-center gap-2 rounded-[10px] border border-strong px-3 text-[12px] font-semibold text-ink hover:bg-hover"><Icon name="download" size={16} />فایل برای گذاشتن با دست</a> : null}
        </div>
      </div>
      {p.checks?.length ? <CheckGrid checks={p.checks} /> : null}
      <p className="text-[12px] text-muted">با مُهر، هر جا API رسمی دارد همان لحظه منتشر میشود{manual ? '؛ برای استوری کانال تلگرام، مُهر یعنی خودت گذاشتی' : ''}. اینستاگرام با برچسب ساخته‌ی هوش مصنوعی.</p>
    </Block>
  );
}

/** `media_series`: sealed on its own page, on the series digest (like a server plan). */
function SeriesBlock({ d }: { d: Decision }) {
  const p = obj(d.payload) as { series?: string; title_fa?: string; kind?: string; schedule?: string; auto_publish?: boolean; max_per_day?: number; digest?: string; version?: number; targets?: SeriesTarget[] };
  return (
    <Block title="برنامه‌ی انتشار">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Fact label="برنامه" mono>{p.series ? <Link href={`/media/series?ref=${p.series}`} className="hover:underline">{p.series}</Link> : '—'}</Fact>
        <Fact label="نوع">{p.kind ? KIND_FA[p.kind]?.fa ?? p.kind : '—'}</Fact>
        <Fact label="انتشار خودکار">{p.auto_publish ? 'بله، اگر هر هفت چک قبول' : 'نه؛ هر آیتم کارت'}</Fact>
        <Fact label="سقف روزانه">{p.max_per_day ?? '—'}</Fact>
      </div>
      {p.schedule ? <p className="text-[13px] text-ink"><Schedule rrule={p.schedule} /></p> : null}
      {p.targets?.length ? <div className="flex flex-wrap gap-1.5">{p.targets.map((t) => <span key={`${t.account}-${t.placement}`} className="rounded-full bg-tile px-2.5 py-1 text-[12px] text-ink">{PLACEMENT_FA[t.placement] ?? t.placement} <span className="fig text-[11px] text-muted">{t.account}</span></span>)}</div> : null}
      {p.digest ? <p className="text-[11px] text-muted">مُهر روی همین نسخه است: <span className="fig">digest {p.digest.slice(0, 16)}…</span>{p.version ? <> · نسخه‌ی {p.version}</> : null}. هر ویرایش بعدی مُهر را برمیدارد.</p> : null}
    </Block>
  );
}

/** `role_new` (🔏, target = ref): a role a department's manager wrote, after the overseer's review and its own eval. */
function RoleBlock({ d }: { d: Decision }) {
  const p = obj(d.payload) as { draft?: string; company?: string; department?: string; role?: string; title_fa?: string; model?: string; effort?: string; limits?: { tokens_per_run?: number }; tools_count?: number; review?: string; eval_score?: number; sha256?: string };
  return (
    <Block title="نقش تازه">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Fact label="پیش‌نویس" mono>{p.draft && p.company ? <Link href={`/companies/${p.company}?role=${p.draft}`} className="hover:underline">{p.draft}</Link> : p.draft ?? '—'}</Fact>
        <Fact label="نقش" mono>{p.role ?? '—'}</Fact>
        <Fact label="مدل و فکر" mono>{modelLabel(p.model)} · {p.effort ?? '—'}</Fact>
        <Fact label="سقف هر اجرا" mono>{p.limits?.tokens_per_run ? `${tokens(p.limits.tokens_per_run)} tok` : '—'}</Fact>
      </div>
      <div className="flex flex-wrap items-center gap-2 text-[12px] text-sec">
        <Pill tone={p.review === 'pass' ? 'pos' : 'warn'} icon="overseer">بازبینی ناظر: {p.review === 'pass' ? 'قبول' : p.review ?? '—'}</Pill>
        {p.eval_score != null ? <Pill tone="gold" icon="academy">آزمون خودش: {p.eval_score}</Pill> : null}
        {p.tools_count ? <span>{p.tools_count} ابزار، همه داخل سقف دپارتمان</span> : null}
        {p.sha256 ? <span className="fig text-muted">sha256 {p.sha256.slice(0, 12)}…</span> : null}
      </div>
      <p className="text-[12px] text-muted">با مُهر، نقش روی سرور فعال میشود (فقط همین شرکت و دپارتمان) و میشود رویش استخدام کرد؛ هر وقت خواستی از استوری یا صفحه‌ی شرکت بازنشسته‌اش کن.</p>
    </Block>
  );
}

function EmailBlock({ d }: { d: Decision }) {
  const p = obj(d.payload) as Partial<EmailDraft>;
  if (!p.subject) return null;
  return (
    <Block title={<span className="flex items-center gap-2">ایمیل دقیق{p.case ? <RefChip r={p.case} note="پرونده" /> : null}</span>}>
      <div className="flex flex-col gap-2 rounded-[14px] bg-tile p-3"><ExactEmail e={{ case: p.case ?? '', from: p.from ?? '', to: p.to ?? [], cc: p.cc ?? [], subject: p.subject, body_md: p.body_md ?? '', attachments: p.attachments ?? [], lang: p.lang ?? 'en', digest: p.digest ?? '' }} /></div>
    </Block>
  );
}

/** The payload of a §22 card; null for any other kind. */
export function MediaDecisionPayload({ d }: { d: Decision }) {
  if (d.kind === 'media_publish') return <PublishBlock d={d} />;
  if (d.kind === 'media_series') return <SeriesBlock d={d} />;
  if (d.kind === 'role_new') return <RoleBlock d={d} />;
  if (d.kind === 'email_send') return <EmailBlock d={d} />;
  return null;
}
