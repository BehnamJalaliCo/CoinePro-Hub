'use client';

import { useRef, useState } from 'react';
import { Icon } from '@/components/icon';
import { AttachmentTray, PICKER_ACCEPT, useAttachments } from '@/components/media/attachments';
import { Waveform, useVoiceInput } from '@/components/media/composer';
import { Button, Spinner } from '@/components/ui/button';
import { Md } from '@/components/ui/md';
import { Sheet } from '@/components/ui/overlay';
import { Card, Empty, ErrorState, FilterChip, PageHeader, Pill, Skeleton } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { ApiError } from '@/lib/api/client';
import { useSkillAction, useSkills, type Skill } from '@/lib/api/v14';
import { clock } from '@/lib/recorder';
import { ACTOR_FA } from '@/lib/labels';
import { cx, jDate } from '@/lib/format';

const STATUS: Record<Skill['status'], { fa: string; tone: 'neutral' | 'lapis' | 'gold' | 'pos' | 'warn' }> = {
  draft: { fa: 'پیش‌نویس', tone: 'neutral' }, in_review: { fa: 'در بررسی ناظر', tone: 'lapis' }, approved: { fa: 'آماده‌ی مُهر', tone: 'gold' }, active: { fa: 'فعال', tone: 'pos' }, retired: { fa: 'بازنشسته', tone: 'warn' },
};
const ROLES: Array<[string, string]> = [['all', 'همه'], ['ceo', 'مدیرعامل‌ها'], ['manager', 'مدیرها'], ['employee', 'کارمندها'], ['cto', 'مدیر فنی'], ['overseer', 'ناظر'], ['advisor', 'مشاور'], ['assistant', 'دستیار']];
const CHECKS: Record<string, string> = { injection: 'بدون تزریق دستور', secrets: 'بدون رمز', conflicts: 'بی‌تناقض با منشور', policy: 'بدون اختیار اضافه' };

function NewSkill({ onClose }: { onClose: () => void }) {
  const act = useSkillAction();
  const toast = useToast();
  const [name, setName] = useState('');
  const [body, setBody] = useState('');
  const [roles, setRoles] = useState<string[]>(['all']);
  const files = useAttachments(5);
  const pick = useRef<HTMLInputElement>(null);
  const v = useVoiceInput({ purpose: 'note', onText: (r) => setBody((b) => (b.trim() ? `${b.trimEnd()}\n${r.text}` : r.text)) });
  const rec = v.state === 'recording' || v.state === 'asking';
  const save = () => act.create.mutateAsync({ name_fa: name.trim(), body_md: body.trim(), roles, companies: 'all', file_ids: files.ids })
    .then(() => { toast({ tone: 'ok', text: 'ثبت شد؛ ناظر بررسی میکند و آزمون آکادمی اجرا میشود.' }); onClose(); })
    .catch((e) => toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'ثبت نشد.' }));
  const field = 'w-full rounded-[10px] border border-strong bg-tile px-3 text-[15px] text-ink outline-none focus:border-gold-ink';
  return (
    <Sheet open onOpenChange={(o) => !o && onClose()} title="مهارت تازه" description="روشی که میخواهی ایجنت‌ها بلد باشند؛ بنویس، بگو یا فایل بده." width={560}
      footer={<Button variant="primary" icon="skill" className="w-full" disabled={name.trim().length < 3 || body.trim().length < 20 || files.uploading} loading={act.create.isPending} onClick={save}>برای بررسی بفرست</Button>}>
      <div className="flex flex-col gap-4">
        <label className="flex flex-col gap-1.5"><span className="text-[13px] text-sec">نام</span><input value={name} onChange={(e) => setName(e.target.value)} maxLength={120} className={cx(field, 'h-12')} placeholder="مثلاً: روش پاسخ به شکایت مشتری" /></label>
        <div className="flex flex-col gap-1.5">
          <div className="flex items-center gap-2">
            <span className="flex-1 text-[13px] text-sec">دستورالعمل (گام‌به‌گام، قابل سنجش)</span>
            {rec ? <span className="flex items-center gap-2"><Waveform levels={v.levels.slice(-16)} className="h-5 w-16" /><span className="fig text-[12px]">{clock(v.elapsed)}</span><Button size="sm" variant="primary" icon="stop" onClick={v.finish}>تمام</Button></span>
              : v.transcribing ? <span className="flex items-center gap-1.5 text-[12px] text-sec"><Spinner size={14} />در حال نوشتن…</span>
              : <Button size="sm" variant="text" icon="mic" onClick={() => void v.start()}>بگو</Button>}
          </div>
          <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={8} className={cx(field, 'py-3 leading-7')} />
        </div>
        <fieldset className="flex flex-col gap-2"><legend className="pb-2 text-[13px] text-sec">برای کدام نقش‌ها</legend>
          <div className="flex flex-wrap gap-2">{ROLES.map(([k, fa]) => <FilterChip key={k} selected={roles.includes(k)} onClick={() => setRoles((r) => (k === 'all' ? ['all'] : r.includes(k) ? r.filter((x) => x !== k) : [...r.filter((x) => x !== 'all'), k]))}>{fa}</FilterChip>)}</div>
        </fieldset>
        <div className="flex flex-col gap-2">
          <div className="flex items-center"><span className="flex-1 text-[13px] text-sec">فایل کمکی (اختیاری)</span>
            <input ref={pick} type="file" multiple accept={PICKER_ACCEPT} hidden onChange={(e) => { if (e.target.files) void files.add(e.target.files); e.target.value = ''; }} />
            <Button size="sm" variant="text" icon="attach" onClick={() => pick.current?.click()}>پیوست</Button>
          </div>
          <AttachmentTray items={files.items} onRemove={files.remove} onRetry={files.retry} />
        </div>
      </div>
    </Sheet>
  );
}

function SkillSheet({ s, onClose }: { s: Skill; onClose: () => void }) {
  const act = useSkillAction();
  const toast = useToast();
  const err = (e: unknown) => toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : e instanceof Error ? e.message : 'انجام نشد.' });
  return (
    <Sheet open onOpenChange={(o) => !o && onClose()} title={<span className="flex items-center gap-2"><span className="fig text-[13px] text-muted">{s.ref}</span>{s.name_fa}</span>} width={600}
      footer={s.status === 'approved' ? <Button variant="primary" icon="seal" className="w-full" loading={act.activate.isPending} onClick={() => act.activate.mutateAsync(s).then(() => { toast({ tone: 'ok', text: 'فعال شد؛ از اجرای بعدی نقش‌ها به کار میرود.' }); onClose(); }).catch(err)}>با گذرکلید فعال کن</Button>
        : s.status === 'active' ? <Button variant="ghost" onClick={() => act.retire.mutateAsync(s.ref).then(onClose).catch(err)}>بازنشسته کن</Button> : undefined}>
      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-2 text-[12px] text-sec">
          <Pill tone={STATUS[s.status].tone} dot>{STATUS[s.status].fa}</Pill>
          <span>نسخه‌ی <span className="fig">{s.version}</span></span>
          <span>{s.scope.roles.map((r) => ROLES.find(([k]) => k === r)?.[1] ?? r).join('، ')}</span>
          <span>{s.scope.companies === 'all' ? 'همه‌ی شرکت‌ها' : s.scope.companies.join('، ')}</span>
        </div>
        <Card className="bg-tile p-4"><Md text={s.body_md} className="flex flex-col gap-2 text-[14px] leading-7 text-ink" /></Card>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="flex flex-col gap-2 rounded-[12px] border border-div p-3">
            <span className="text-[12px] font-semibold text-sec">بررسی ناظر</span>
            {s.review ? (
              <>
                {Object.entries(s.review.checks).map(([k, ok]) => <span key={k} className={cx('flex items-center gap-1.5 text-[12px]', ok ? 'text-pos' : 'text-neg')}><Icon name={ok ? 'seal' : 'urgent'} size={14} />{CHECKS[k]}</span>)}
                <span className="text-[11px] text-muted">{ACTOR_FA(s.review.by)} · {jDate(s.review.at)}</span>
              </>
            ) : <span className="text-[12px] text-muted">در صف بررسی</span>}
          </div>
          <div className="flex flex-col gap-2 rounded-[12px] border border-div p-3">
            <span className="text-[12px] font-semibold text-sec">آزمون آکادمی</span>
            {s.eval ? (
              <>
                <span className="fig text-[22px] font-semibold">{s.eval.score}</span>
                <span className="text-[11px] text-muted">خط پایه <span className="fig">{s.eval.baseline}</span> · <span className="fig">{s.eval.suite}</span> · {s.eval.score >= s.eval.baseline - 1 ? 'قبول' : 'رد'}</span>
              </>
            ) : <span className="text-[12px] text-muted">بعد از بررسی</span>}
          </div>
        </div>
      </div>
    </Sheet>
  );
}

/** کتابخانه‌ی مهارت (contract §18.5): the owner writes how agents should work; the overseer reviews, the academy tests, the owner activates. */
export default function SkillsPage() {
  const q = useSkills();
  const [open, setOpen] = useState<string | null>(null);
  const [neu, setNew] = useState(false);
  const [st, setSt] = useState<string | null>(null);
  const items = (q.data ?? []).filter((s) => !st || s.status === st);
  const cur = q.data?.find((s) => s.ref === open);
  return (
    <>
      <PageHeader eyebrow="روش‌هایی که ایجنت‌ها بلدند" title="مهارت‌ها" actions={<Button variant="primary" icon="add" onClick={() => setNew(true)}>مهارت تازه</Button>}>
        <p className="max-w-3xl text-[13px] leading-6 text-sec">هر مهارت پیش از فعال شدن از بررسی ناظر کل (تزریق دستور، رمز، تناقض، اختیار اضافه) و آزمون طلایی آکادمی میگذرد؛ فعال شدن با مُهر توست.</p>
      </PageHeader>
      <div className="flex flex-wrap gap-2">
        <FilterChip selected={!st} onClick={() => setSt(null)} count={q.data?.length}>همه</FilterChip>
        {(['approved', 'in_review', 'active', 'retired'] as const).map((k) => <FilterChip key={k} selected={st === k} onClick={() => setSt(k)} count={(q.data ?? []).filter((s) => s.status === k).length}>{STATUS[k].fa}</FilterChip>)}
      </div>
      {q.isLoading ? <Skeleton className="h-48" /> : q.error ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : !items.length ? <Empty icon="skill" title="مهارتی نیست" /> : (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {items.map((s) => (
            <button key={s.ref} type="button" onClick={() => setOpen(s.ref)} className={cx('flex flex-col gap-2 rounded-[16px] p-4 text-start transition-colors hover:bg-hover', s.status === 'approved' ? 'bg-gold-soft' : 'bg-card')}>
              <span className="flex items-center gap-2"><Icon name="skill" size={18} className="text-gold-ink" /><span className="min-w-0 flex-1 truncate text-[14px] font-semibold">{s.name_fa}</span><Pill tone={STATUS[s.status].tone} dot>{STATUS[s.status].fa}</Pill></span>
              <span className="line-clamp-2 text-[12px] leading-6 text-sec">{s.summary_fa}</span>
              <span className="flex items-center gap-2 text-[11px] text-muted"><span className="fig">{s.ref}</span><span>نسخه‌ی <span className="fig">{s.version}</span></span><span className="flex-1" />{s.eval ? <span>آزمون <span className={cx('fig', s.eval.score >= s.eval.baseline - 1 ? 'text-pos' : 'text-neg')}>{s.eval.score}</span> · پایه <span className="fig">{s.eval.baseline}</span></span> : null}</span>
            </button>
          ))}
        </div>
      )}
      {neu ? <NewSkill onClose={() => setNew(false)} /> : null}
      {cur ? <SkillSheet s={cur} onClose={() => setOpen(null)} /> : null}
    </>
  );
}
