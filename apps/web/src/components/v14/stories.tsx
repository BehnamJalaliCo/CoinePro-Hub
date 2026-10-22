'use client';

import * as D from '@radix-ui/react-dialog';
import Link from 'next/link';
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { CompanyMark } from '@/components/brand/marks';
import { Icon } from '@/components/icon';
import { Button, IconButton } from '@/components/ui/button';
import { useToast } from '@/components/ui/toast';
import type { IconName } from '@/generated/icons';
import { ApiError } from '@/lib/api/client';
import { useCompanies } from '@/lib/api/hooks';
import { fileUrl } from '@/lib/api/v13';
import { useStories, useStoryAction, type StoryKind, type StoryRing } from '@/lib/api/v14';
import { faError, useRoleDraftAction } from '@/lib/api/v19';
import { companyColor, companyOf } from '@/lib/company';
import { ago, cx } from '@/lib/format';
import { Figs } from './bits';

const KIND: Record<StoryKind, { fa: string; icon: IconName }> = {
  hire: { fa: 'استخدام تازه', icon: 'hire' }, deliverable: { fa: 'خروجی برجسته', icon: 'deliverable' }, stars: { fa: 'ستاره‌ی هفته', icon: 'star' },
  milestone: { fa: 'هدف رسید', icon: 'chart' }, post: { fa: 'از مدیرعامل', icon: 'messages' },
  // ⟨1.6⟩ §22.5: a role written on demand became active.
  role: { fa: 'نقش تازه', icon: 'department' },
};
const SECONDS = 6;

/** Contract §18.12: the companies' stories, a row of rings at the top of «فرمان» (owner, 2026-10-17). Gold while something is unseen. */
export function StoriesBar() {
  const { data: rings } = useStories();
  const { data: companies } = useCompanies();
  const [open, setOpen] = useState<number | null>(null);
  if (!rings?.length) return null;
  return (
    <>
      <nav aria-label="استوری شرکت‌ها" className="-mx-1 flex gap-3 overflow-x-auto px-1 pb-1 [scrollbar-width:none]">
        {rings.map((r, i) => {
          const name = companyOf(companies, r.company).nameFa;
          return (
            <button key={r.company} type="button" onClick={() => setOpen(i)} aria-label={`استوری ${name}${r.unseen ? `، ${r.unseen} تازه` : ''}`}
              className="group flex w-[76px] flex-none flex-col items-center gap-1.5 rounded-[12px] py-1 outline-none focus-visible:ring-2 focus-visible:ring-[var(--hq-state-focus)]">
              <span className="rounded-full p-[2.5px] transition-transform group-active:scale-95"
                style={{ background: r.unseen ? `conic-gradient(from 200deg, var(--hq-gold-bright), var(--hq-gold-ink), ${companyColor(companies, r.company)}, var(--hq-gold-bright))` : 'var(--hq-line-strong)' }}>
                <span className="flex size-[62px] items-center justify-center rounded-full border-[3px] border-[var(--hq-surface-page)] bg-card text-ink">
                  <CompanyMark code={r.company} height={26} />
                </span>
              </span>
              <span className={cx('w-full truncate text-center text-[11px]', r.unseen ? 'font-semibold text-ink' : 'text-muted')}>{name}</span>
            </button>
          );
        })}
      </nav>
      {open !== null ? <StoryViewer rings={rings} start={open} onClose={() => setOpen(null)} /> : null}
    </>
  );
}

/** Full-screen player: one ring after another, six seconds a card, hold to pause; in RTL the left side goes forward. */
function StoryViewer({ rings: live, start, onClose }: { rings: StoryRing[]; start: number; onClose: () => void }) {
  // A snapshot, so a refetch while watching never reorders what is playing.
  const [rings] = useState(live);
  const first = (r: StoryRing | undefined) => Math.max(0, r?.items.findIndex((x) => !x.seen) ?? 0);
  const [at, setAt] = useState({ ring: start, item: first(live[start]) });
  const [elapsed, setElapsed] = useState(0);
  const [held, setHeld] = useState(false);
  const [paused, setPaused] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [welcomed, setWelcomed] = useState<Record<string, boolean>>({});
  const { data: companies } = useCompanies();
  const act = useStoryAction();
  const roleAct = useRoleDraftAction();
  const toast = useToast();
  const down = useRef(0);
  const clock = useRef(0);
  const ring = rings[at.ring]!;
  const story = ring.items[at.item]!;
  const stopped = held || paused || confirm;

  const next = useCallback(() => {
    clock.current = 0;
    setElapsed(0);
    if (at.item < rings[at.ring]!.items.length - 1) setAt({ ring: at.ring, item: at.item + 1 });
    else if (at.ring < rings.length - 1) setAt({ ring: at.ring + 1, item: first(rings[at.ring + 1]) });
    else onClose();
  }, [at, rings, onClose]);
  const prev = useCallback(() => {
    clock.current = 0;
    setElapsed(0);
    if (at.item > 0) setAt({ ring: at.ring, item: at.item - 1 });
    else if (at.ring > 0) setAt({ ring: at.ring - 1, item: 0 });
  }, [at]);

  // Seen as soon as it is on screen.
  const markSeen = act.seen.mutate;
  useEffect(() => { if (!story.seen) markSeen([story.ref]); }, [story.ref, story.seen, markSeen]);

  // The clock: a ref counts, the state only draws the bar; at six seconds the next card plays.
  const nextRef = useRef(next);
  useLayoutEffect(() => { nextRef.current = next; });
  useEffect(() => {
    if (stopped) return;
    const t = setInterval(() => {
      clock.current += 0.05;
      if (clock.current >= SECONDS) nextRef.current();
      else setElapsed(clock.current);
    }, 50);
    return () => clearInterval(t);
  }, [stopped, story.ref]);

  const keys = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowLeft') { e.preventDefault(); next(); }
    else if (e.key === 'ArrowRight') { e.preventDefault(); prev(); }
    else if (e.key === ' ') { e.preventDefault(); setPaused((v) => !v); }
  };
  const name = companyOf(companies, ring.company).nameFa;
  const color = companyColor(companies, ring.company);
  // Kinds a newer server adds are shown plainly rather than failing (§1: unknown enums are tolerated).
  const k = KIND[story.kind] ?? { fa: 'تازه', icon: 'info' as IconName };
  const isWelcomed = story.welcomed || welcomed[story.ref];

  const welcome = async () => {
    try { await act.welcome.mutateAsync(story.ref); setWelcomed((w) => ({ ...w, [story.ref]: true })); toast({ tone: 'ok', text: 'خوش‌آمدت به مدیر و مدیرعاملش رسید.' }); }
    catch (e) { toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'ثبت نشد.' }); }
  };
  const dismiss = async () => {
    if (!story.links.employee) return;
    try {
      await act.dismiss.mutateAsync(story.links.employee);
      setConfirm(false);
      toast({ tone: 'info', text: <><span className="fig">{story.links.employee}</span> برکنار شد؛ کارهای بازش به مدیرش برگشت.</> });
      next();
    } catch (e) { toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : e instanceof Error ? e.message : 'انجام نشد.' }); }
  };
  const retire = async () => {
    if (!story.links.role_draft) return;
    try {
      await roleAct.retire.mutateAsync(story.links.role_draft);
      setConfirm(false);
      toast({ tone: 'info', text: <>نقش <span className="fig">{story.links.role_draft}</span> بازنشسته شد؛ استخدام تازه روی آن نیست و کارمندهایش تا جابه‌جایی کار میکنند.</> });
      next();
    } catch (e) { toast({ tone: 'error', text: faError(e) }); }
  };
  const link = story.links.role_draft ? { href: `/companies/${ring.company}?role=${story.links.role_draft}`, fa: 'دیدن نقش' }
    : story.links.employee ? { href: `/employees/${story.links.employee}`, fa: 'دیدن کارمند' }
    : story.links.deliverable ? { href: `/outputs?ref=${story.links.deliverable}`, fa: 'دیدن خروجی' }
      : story.links.decision ? { href: `/cartable?ref=${story.links.decision}`, fa: 'در کارتابل' }
        : story.kind === 'stars' ? { href: '/stars', fa: 'ستاره‌ها' } : null;

  return (
    <D.Root open onOpenChange={(v) => { if (!v) onClose(); }}>
      <D.Portal>
        <D.Overlay className="fixed inset-0 z-50 bg-[rgba(6,8,12,.88)] backdrop-blur-sm data-[state=open]:animate-[hq-rise_200ms_both]" />
        <D.Content onKeyDown={keys} className="fixed inset-0 z-50 flex items-center justify-center gap-3 outline-none" aria-describedby={undefined}>
          <D.Title className="sr-only">استوری {name}</D.Title>
          <IconButton icon="next" label="استوری قبلی" onClick={prev} mirror className="text-white/80 hover:text-white max-sm:hidden" />
          <article className="relative flex h-[100dvh] w-[100vw] flex-col overflow-hidden bg-page sm:h-[min(92dvh,780px)] sm:w-[min(100vw,440px)] sm:rounded-[24px]"
            style={{ backgroundImage: `radial-gradient(120% 70% at 85% 0%, color-mix(in oklab, ${color} 46%, transparent) 0%, transparent 70%), linear-gradient(180deg, color-mix(in oklab, ${color} 14%, var(--hq-surface-page)) 0%, var(--hq-surface-page) 72%)` }}>
            <div className="flex gap-1 px-3 pt-3" aria-hidden>
              {ring.items.map((x, i) => (
                <span key={x.ref} className="relative h-[3px] flex-1 overflow-hidden rounded-full bg-[color-mix(in_oklab,var(--hq-text-primary)_22%,transparent)]">
                  <span className="absolute inset-y-0 start-0 rounded-full bg-[var(--hq-text-primary)]" style={{ width: `${i < at.item ? 100 : i > at.item ? 0 : Math.min(100, (elapsed / SECONDS) * 100)}%` }} />
                </span>
              ))}
            </div>
            <header className="flex items-center gap-3 px-4 pb-2 pt-3">
              <span className="flex size-9 items-center justify-center rounded-full bg-card text-ink"><CompanyMark code={ring.company} height={18} /></span>
              <span className="flex min-w-0 flex-1 flex-col">
                <span className="truncate text-[14px] font-semibold text-ink">{name}</span>
                <span className="text-[11px] text-muted">{story.author.kind === 'system' ? 'سیستم' : <>مدیرعامل، <span className="fig">{story.author.code}</span></>}، {ago(story.created_at)}</span>
              </span>
              <IconButton icon={stopped ? 'resume' : 'pause'} label={stopped ? 'ادامه' : 'مکث'} onClick={() => setPaused((v) => !v)} />
              <D.Close asChild><IconButton icon="close" label="بستن" /></D.Close>
            </header>

            {/* The card: press and hold pauses; a short tap on the left goes forward, on the right goes back. */}
            <div className="relative flex min-h-0 flex-1 cursor-pointer select-none flex-col justify-center gap-5 px-6 pb-4"
              onPointerDown={() => { down.current = Date.now(); setHeld(true); }}
              onPointerLeave={() => setHeld(false)}
              onPointerUp={(e) => {
                setHeld(false);
                if (Date.now() - down.current > 250) return;
                const r = e.currentTarget.getBoundingClientRect();
                if (e.clientX - r.left < r.width / 2) next(); else prev();
              }}>
              <span className="inline-flex w-fit items-center gap-1.5 rounded-full bg-[color-mix(in_oklab,var(--hq-surface-card)_80%,transparent)] px-3 py-1 text-[12px] font-semibold text-ink"><Icon name={k.icon} size={15} />{k.fa}</span>
              <h2 className="text-[26px] font-bold leading-[1.35] text-ink"><Figs text={story.title_fa} /></h2>
              {/* eslint-disable-next-line @next/next/no-img-element -- the company's own file, served by the API */}
              {story.media?.kind === 'image' ? <img src={fileUrl(story.media.id)} alt={story.media.name} className="max-h-[38%] w-full rounded-[16px] object-cover" draggable={false} /> : null}
              <p className="text-[16px] leading-8 text-sec"><Figs text={story.body_fa} /></p>
              {story.figures.length ? (
                <dl className="grid gap-3" style={{ gridTemplateColumns: `repeat(${story.figures.length}, minmax(0, 1fr))` }}>
                  {story.figures.map((f) => (
                    <div key={f.label_fa} className="flex flex-col gap-1 rounded-[14px] bg-[color-mix(in_oklab,var(--hq-surface-card)_78%,transparent)] p-3">
                      <dd className={cx('fig font-semibold leading-none text-ink', f.value.length > 6 ? 'text-[18px]' : 'text-[24px]')}>{f.value}</dd>
                      <dt className="text-[11px] text-muted">{f.label_fa}</dt>
                    </div>
                  ))}
                </dl>
              ) : null}
            </div>

            <footer className="flex flex-wrap items-center gap-2 border-t border-div px-4 py-3">
              {story.kind === 'hire' && story.links.employee ? (
                <>
                  <Button variant="primary" icon="rate" disabled={isWelcomed} loading={act.welcome.isPending} onClick={welcome}>{isWelcomed ? 'خوش‌آمد گفتی' : 'خوش‌آمد'}</Button>
                  <Button variant="danger" icon="dismiss" onClick={() => setConfirm(true)}>برکنار کن</Button>
                </>
              ) : story.kind === 'role' && story.links.role_draft ? (
                <Button variant="danger" icon="pause" onClick={() => setConfirm(true)}>بازنشسته کن</Button>
              ) : null}
              {link ? <Link href={link.href} onClick={onClose} className="ms-auto inline-flex h-10 items-center gap-1.5 rounded-[10px] px-3 text-[13px] font-semibold text-gold-ink hover:bg-hover">{link.fa}<Icon name="next" size={16} /></Link> : null}
            </footer>

            {confirm && story.kind === 'role' ? (
              <div role="alertdialog" aria-label="بازنشستگی نقش" className="absolute inset-x-3 bottom-3 flex flex-col gap-3 rounded-[18px] bg-raised p-4 shadow-[0_18px_48px_rgba(0,0,0,.45)]">
                <span className="text-[15px] font-semibold text-ink">نقش <span className="fig">{story.links.role_draft}</span> بازنشسته شود؟</span>
                <span className="text-[13px] leading-6 text-sec">کسی دیگر روی این نقش استخدام نمیشود؛ کارمندهایی که دارد تا جابه‌جایی یا برکناری کار میکنند. منشورش در تاریخچه میماند.</span>
                <div className="flex flex-row-reverse gap-2">
                  <Button variant="danger" icon="pause" loading={roleAct.retire.isPending} onClick={retire}>بازنشسته کن</Button>
                  <Button variant="ghost" onClick={() => setConfirm(false)}>نه</Button>
                </div>
              </div>
            ) : confirm ? (
              <div role="alertdialog" aria-label="برکناری" className="absolute inset-x-3 bottom-3 flex flex-col gap-3 rounded-[18px] bg-raised p-4 shadow-[0_18px_48px_rgba(0,0,0,.45)]">
                <span className="text-[15px] font-semibold text-ink"><span className="fig">{story.links.employee}</span> برکنار شود؟</span>
                <span className="text-[13px] leading-6 text-sec">کارهای بازش به مدیرش برمیگردد و کدش دوباره استفاده نمیشود. با گذرکلید تأیید میشود.</span>
                <div className="flex flex-row-reverse gap-2">
                  <Button variant="danger" icon="seal" loading={act.dismiss.isPending} onClick={dismiss}>با گذرکلید برکنار کن</Button>
                  <Button variant="ghost" onClick={() => setConfirm(false)}>نه</Button>
                </div>
              </div>
            ) : null}
          </article>
          <IconButton icon="next" label="استوری بعدی" onClick={next} className="text-white/80 hover:text-white max-sm:hidden" />
        </D.Content>
      </D.Portal>
    </D.Root>
  );
}

