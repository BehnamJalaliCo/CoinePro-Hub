'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useRef, useState, useSyncExternalStore, type ReactNode } from 'react';
import { Icon } from '@/components/icon';
import { Spinner } from '@/components/ui/button';
import { Card, FilterChip } from '@/components/ui/primitives';
import { Sheet } from '@/components/ui/overlay';
import type { IconName } from '@/generated/icons';
import { useInbox } from '@/lib/api/hooks';
import { call } from '@/lib/api/v13';
import type { Inbox21 } from '@/lib/api/v21';
import { errorLog, type ErrorEntry } from '@/lib/errorlog';
import { startUploads } from '@/lib/error-upload';
import { hubHealth, backoff } from '@/lib/hub-health';
import type { StreamEvent, StreamState } from '@/lib/stream';
import { ago, cx } from '@/lib/format';
import { AlertCenter } from './push';

// The shell's additions from the Android app's 0.3.0–0.6.0: «خطاخوان» running from the first page (and what page each failure happened on),
// one calm banner while the hub restarts (and a quiet probe until it answers), the alerts, and «همه‌ی بخش‌ها» as tiled groups.

const EMPTY: ErrorEntry[] = [];

/** The hub is restarting (a deploy): one calm line instead of an error on every card; the panel reconnects on its own. */
export function HubBanner() {
  const state = useSyncExternalStore(hubHealth.subscribe, hubHealth.get, () => 'ok' as const);
  if (state !== 'restarting') return null;
  return (
    <div role="status" aria-live="polite" className="hq-rise flex items-center gap-2.5 bg-lapis-soft px-4 py-2 text-[12px] text-ink md:px-6">
      <span className="text-lapis"><Spinner size={14} /></span>
      <span className="flex-1">هاب در حال راه‌اندازی دوباره است؛ خودکار وصل میشوم.</span>
    </div>
  );
}

/** Mounted once in the shell: the log, the page it is on, the stream's ups and downs, the hub's return, and the alerts. */
export function ShellExtras({ feed, stream }: { feed: StreamEvent[]; stream: StreamState }) {
  const pathname = usePathname();
  const qc = useQueryClient();
  const prev = useRef<StreamState | null>(null);
  // ⟨1.10⟩ then its errors go to the hub in batches (§28.3), unless the owner turned that off.
  useEffect(() => { errorLog.start(); startUploads(); }, []);
  useEffect(() => { errorLog.setScreen(pathname); }, [pathname]);
  useEffect(() => {
    const was = prev.current;
    prev.current = stream;
    if (!was || was === stream) return;
    errorLog.crumb(`stream ${stream}`);
    if (stream === 'offline' && was === 'live') errorLog.note('stream', 'warning', 'dropped', 'the live stream dropped; reconnecting');
    if (stream === 'live' && was === 'offline') errorLog.note('stream', 'info', 'back', 'the live stream is back');
  }, [stream]);
  // The first answer after a restart brings everything back: every query reads again, and the log says how long the hub was away.
  useEffect(() => hubHealth.onRecovered((ms) => {
    errorLog.note('hub', 'info', `after ${Math.round(ms / 1000)} s`, `the hub answers again after ${Math.round(ms / 1000)} s`);
    void qc.invalidateQueries();
  }), [qc]);
  // While the hub is away the panel asks with a growing pause, quietly; any answer that is not a 502/503/504 ends the wait.
  const state = useSyncExternalStore(hubHealth.subscribe, hubHealth.get, () => 'ok' as const);
  useEffect(() => {
    if (state !== 'restarting') return;
    let attempt = 0;
    let timer: ReturnType<typeof setTimeout>;
    let stop = false;
    const probe = async () => {
      if (stop) return;
      // Through the panel's own client: an answer marks the hub back (lib/api/observe), a 502 joins the outage's one entry.
      try { await call('GET', '/meta'); } catch { /* still away, or answered with an error: either way observe has judged it */ }
      if (hubHealth.outage) timer = setTimeout(probe, backoff(attempt++));
    };
    timer = setTimeout(probe, backoff(attempt++));
    return () => { stop = true; clearTimeout(timer); };
  }, [state]);
  return <AlertCenter feed={feed} />;
}

// ------------------------------------------------------------------------------------------------------- tools sheet --
type Tool = { href: string; label: string; icon: IconName; hint: string; badge?: 'outputs' | 'errors' };
type Group = { key: string; title: string; note: string; tools: Tool[] };

/** Everything beyond the main bar, grouped by what the owner does with it; each place says in one line what it is for (the Android app's GROUPS). */
export const GROUPS: Group[] = [
  { key: 'work', title: 'فرمان و کار', note: 'آنچه دادی و آنچه تحویل گرفتی', tools: [
    { href: '/orders', label: 'فرمان‌های من', icon: 'command', hint: 'هر فرمانی که دادی، از ثبت تا تحویل' },
    { href: '/outputs', label: 'خروجی‌ها', icon: 'deliverable', hint: 'گزارش‌ها و کارهای تحویل‌شده؛ بخوان، امتیاز بده، بایگانی یا پاک کن', badge: 'outputs' },
    { href: '/planner', label: 'پلنر', icon: 'planner', hint: 'کارهای امروز و این هفته در یک تقویم' },
    { href: '/runs', label: 'اجرای ایجنت‌ها', icon: 'agent', hint: 'هر ایجنت الان چه میکند، قدم‌به‌قدم' },
    { href: '/notifications', label: 'اعلان‌ها', icon: 'bell', hint: 'هشدارها، گزارش‌ها و پرسش‌های یک‌ضربه‌ای' },
    { href: '/resolutions', label: 'دفتر مصوبات', icon: 'seal', hint: 'تصمیم‌های ثبت‌شده، با جست‌وجو و خروجی اکسل' },
    { href: '/workshop', label: 'کارگاه کد', icon: 'code', hint: 'جلسه‌های کدنویسی ایجنت‌ها و اجازه‌ی push' },
  ] },
  { key: 'org', title: 'سازمان', note: 'کسانی که کنار تو کار میکنند و آنچه یاد میگیرند', tools: [
    { href: '/advisor', label: 'مشاور کل', icon: 'advisor', hint: 'با او فکر کن و نظر دوم بگیر' },
    { href: '/oversight', label: 'ناظر کل', icon: 'overseer', hint: 'چه کسی کجا خطا کرد و چه نگه داشته شد' },
    { href: '/watch', label: 'دیده‌بان', icon: 'scope', hint: 'امنیت، سلامت اپ، کد، رشد و پیشنهاد هلدینگ، با اصلاح پیشنهادی' },
    { href: '/assistant', label: 'دستیار', icon: 'assistant', hint: 'کارهای بیرونی تو را در اینترنت پیگیری میکند' },
    { href: '/stars', label: 'ستاره‌ها', icon: 'star', hint: 'بهترین شرکت و کارمندهای هفته و ماه' },
    { href: '/founding', label: 'تأسیس شرکت', icon: 'found', hint: 'شرکت تازه قدم‌به‌قدم: از ایده، ریپو یا فقط با نام' },
    { href: '/skills', label: 'مهارت‌ها', icon: 'skill', hint: 'مهارت تازه به ایجنت‌ها یاد بده و فعالش کن' },
    { href: '/academy', label: 'آکادمی', icon: 'academy', hint: 'آموزش، آزمون و پیشرفت هر نقش' },
    { href: '/tools', label: 'ابزارها و اینترنت', icon: 'globe', hint: 'ایجنت‌ها به کجا وصل میشوند و چه میفرستند' },
  ] },
  { key: 'money', title: 'پول و مشتری', note: 'خرج مدل‌ها، درآمد شرکت‌ها و حرف مشتری‌ها', tools: [
    { href: '/treasury', label: 'خزانه‌ی توکن', icon: 'treasury', hint: 'مصرف مدل‌ها، بودجه‌ها و سهمیه‌ی اشتراک' },
    { href: '/revenue', label: 'درآمد', icon: 'chart', hint: 'درآمد هر شرکت و هشدار وقتی افت کند' },
    { href: '/support', label: 'پشتیبانی', icon: 'messages', hint: 'گفت‌وگوی مشتری‌ها و پاسخ‌های آماده' },
    { href: '/growth', label: 'رشد و پیام‌ها', icon: 'send', hint: 'قالب پیام، قاعده‌های ارسال و نظرسنجی' },
    { href: '/feedback', label: 'بازخورد', icon: 'rate', hint: 'حرف کاربران، پرتکرارها اول' },
  ] },
  { key: 'manage', title: 'ابزار مدیریت', note: 'یادداشت، گزارش صوتی و پیش‌بینی تصمیم‌های تو', tools: [
    { href: '/notes', label: 'یادداشت‌ها', icon: 'edit', hint: 'فکرهای سریع؛ بعداً کار یا فرمان میشوند' },
    { href: '/letter', label: 'گزارش صوتی و نامه‌ها', icon: 'mic', hint: 'گزارش صبح و نامه‌ی هفتگی مدیرعامل‌ها' },
    { href: '/substitutes', label: 'بازیکن‌های ذخیره', icon: 'agent', hint: 'ChatGPT و Gemini، وقتی سهمیه‌ی Claude تمام شود' },
    { href: '/digital-ceo', label: 'مدیر کل دیجیتال', icon: 'holding', hint: 'پیش‌بینی تصمیم تو و این‌که چقدر درست درآمد' },
  ] },
  { key: 'gov', title: 'حاکمیت', note: 'قاعده‌ها، هدف‌ها، ریسک‌ها و جلسه‌ها', tools: [
    { href: '/meetings', label: 'اتاق جلسه', icon: 'meeting', hint: 'جلسه‌های زنده، صورت‌جلسه و اتاق جنگ' },
    { href: '/charter', label: 'اساسنامه', icon: 'report', hint: 'قانون پایه‌ی هلدینگ و هر شرکت' },
    { href: '/knowledge', label: 'دانشنامه', icon: 'knowledge', hint: 'آنچه سازمان میداند، با منبع و انقضا' },
    { href: '/scorecard', label: 'کارت‌ها و امتیاز', icon: 'chart', hint: 'شاخص‌های اصلی هر شرکت در یک نگاه' },
    { href: '/okr', label: 'OKR', icon: 'planner', hint: 'هدف‌های فصل و نتیجه‌های کلیدی' },
    { href: '/outcomes', label: 'بازبینی نتیجه', icon: 'refresh', hint: 'تصمیم‌ها بعد از ۳۰، ۶۰ و ۹۰ روز چه شدند' },
    { href: '/risks', label: 'دفتر ریسک', icon: 'urgent', hint: 'ریسک‌ها روی ماتریس احتمال و اثر' },
    { href: '/calendar', label: 'تقویم تغییرات', icon: 'time', hint: 'انتشارها و تغییرها، و تداخل‌هایشان' },
    { href: '/authority', label: 'ماتریس اختیار', icon: 'lock', hint: 'چه کسی بی‌اجازه‌ی تو چه کاری میتواند' },
  ] },
  { key: 'media', title: 'رسانه و حقوقی', note: 'ویدیو و انتشار، و پرونده‌های حقوقی', tools: [
    { href: '/media', label: 'استودیوی رسانه', icon: 'video', hint: 'ویدیو و تصویر هر شرکت، از سناریو تا انتشار' },
    { href: '/media/series', label: 'برنامه‌های انتشار', icon: 'send', hint: 'چه چیزی، کجا و چه روزی منتشر شود' },
    { href: '/media/voice', label: 'صدای هاب', icon: 'mic', hint: 'صدایی که گزارش‌ها با آن خوانده میشوند' },
    { href: '/legal', label: 'مشاور حقوقی', icon: 'decision', hint: 'پرونده‌ها، مهلت‌ها و ایمیل‌های حقوقی' },
  ] },
  { key: 'archive', title: 'بایگانی', note: 'سندها، قراردادها و زمان نگهداری‌شان', tools: [
    { href: '/archive', label: 'بایگانی', icon: 'deliverable', hint: 'سندها و قراردادها، با جست‌وجو در متنشان' },
    { href: '/archive/holds', label: 'توقیف‌ها', icon: 'lock', hint: 'سندهایی که به‌خاطر پرونده نباید پاک شوند' },
    { href: '/archive/reminders', label: 'یادآورها', icon: 'time', hint: 'تمدیدها و موعدهای سندها' },
    { href: '/archive/retention', label: 'پایان نگهداری', icon: 'memory', hint: 'سندهایی که زمان امحایشان رسیده' },
    { href: '/archive/settings', label: 'طرح بایگانی', icon: 'settings', hint: 'دسته‌ها، پوشه‌ها و قاعده‌های بایگانی' },
  ] },
  { key: 'system', title: 'سیستم و ایمنی', note: 'کلیدهای توقف، سلامت و ردّ هر اقدام', tools: [
    { href: '/control', label: 'کنترل', icon: 'lock', hint: 'توقف و ادامه‌ی شرکت‌ها و انتشارها' },
    // ⟨1.8⟩ §26: the companies' servers under the holding's control, and the few things that wait for the owner's seal there.
    { href: '/servers', label: 'همه‌ی سرورها', icon: 'server', hint: 'نقشه، کارهای زنده، ترمینال و Claude روی سرور شرکت‌ها' },
    { href: '/network', label: 'شبکه‌ی هلدینگ', icon: 'globe', hint: 'راه هر سرور به هاب و به سرورهای دیگر' },
    { href: '/server-policy', label: 'قوانین سرورها', icon: 'seal', hint: 'شش کار ویرانگری که مُهر تو را میخواهند' },
    { href: '/sites', label: 'پایش سایت‌ها', icon: 'server', hint: 'سالم بودن سایت‌ها و رخدادهایشان' },
    { href: '/audit', label: 'دفتر Audit', icon: 'report', hint: 'ردّ تغییرناپذیر هر اقدام در هاب' },
    { href: '/settings', label: 'تنظیمات', icon: 'settings', hint: 'دستگاه‌ها، اعلان‌ها، استخدام و ظاهر' },
    { href: '/errors', label: 'خطاخوان', icon: 'urgent', hint: 'خطاهای پنل، برای فرستادن به توسعه‌دهنده', badge: 'errors' },
  ] },
];

/** «همه‌ی بخش‌ها» (0.4.0): every place as tiles in titled groups, each tile with its icon, name and one line on what it is for. A row of the
 *  groups' names jumps to one. The tiles arrive with a spring, one after another (still when the system removes animations). */
export function ToolsSheet({ open, onOpenChange, extra }: { open: boolean; onOpenChange: (v: boolean) => void; extra?: ReactNode }) {
  const { data: inbox } = useInbox();
  const errors = useSyncExternalStore(errorLog.subscribe, errorLog.list, () => EMPTY).filter((e) => e.level !== 'info').length;
  const i21 = inbox as Inbox21 | undefined;
  const outputs = i21?.deliverables_unseen ?? i21?.deliverables_unrated ?? 0;
  const badge = (t: Tool) => (t.badge === 'outputs' && outputs > 0 ? outputs : t.badge === 'errors' && errors > 0 ? errors : null);
  const refs = useRef<Record<string, HTMLElement | null>>({});
  let n = 0;
  return (
    <Sheet open={open} onOpenChange={onOpenChange} title="همه‌ی بخش‌ها" width={720}>
      <div className="flex flex-col gap-5">
        {extra}
        <div className="no-scrollbar -mx-1 flex gap-2 overflow-x-auto px-1">
          {GROUPS.map((g) => <FilterChip key={g.key} onClick={() => refs.current[g.key]?.scrollIntoView({ behavior: 'smooth', block: 'start' })}>{g.title}</FilterChip>)}
        </div>
        {GROUPS.map((g) => (
          <section key={g.key} ref={(el) => { refs.current[g.key] = el; }} className="flex scroll-mt-2 flex-col gap-2.5" aria-label={g.title}>
            <div className="flex flex-col px-0.5"><h3 className="text-[15px] font-semibold text-ink">{g.title}</h3><span className="text-[12px] text-muted">{g.note}</span></div>
            <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3">
              {g.tools.map((t) => {
                const b = badge(t);
                const i = n++;
                return (
                  <Link key={t.href} href={t.href} onClick={() => onOpenChange(false)} aria-label={`${t.label}: ${t.hint}`}
                    className="group flex flex-col gap-1.5 rounded-[14px] bg-card p-2.5 transition-[transform,background] duration-[120ms] hover:bg-hover active:scale-[.97]"
                    style={{ animation: `hq-tile var(--hq-dur-transition) var(--hq-ease-ceremony) ${Math.min(i, 24) * 18}ms both` }}>
                    <span className="flex items-center gap-2">
                      <span className="flex size-[30px] flex-none items-center justify-center rounded-[9px] bg-gold-soft text-gold-ink"><Icon name={t.icon} size={17} /></span>
                      <span className="min-w-0 flex-1 truncate text-[13px] font-semibold text-ink">{t.label}</span>
                      {b ? <span className="inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-gold px-1 text-[10px] font-bold text-on-gold">{b}</span> : null}
                    </span>
                    <span className="line-clamp-2 min-h-8 text-[11px] leading-4 text-muted">{t.hint}</span>
                  </Link>
                );
              })}
            </div>
          </section>
        ))}
      </div>
    </Sheet>
  );
}

/** Settings: how many errors and warnings this version has, and the way into «خطاخوان». */
export function ErrorLogCard() {
  const entries = useSyncExternalStore(errorLog.subscribe, errorLog.list, () => EMPTY);
  const serious = entries.filter((e) => e.level !== 'info');
  const [, tick] = useState(0);
  useEffect(() => { const t = setInterval(() => tick((x) => x + 1), 60_000); return () => clearInterval(t); }, []);
  return (
    <Link href="/errors" className="block rounded-[16px]">
      <Card className="flex items-center gap-3 p-4 transition-colors hover:bg-hover">
        <span className={cx('flex size-10 flex-none items-center justify-center rounded-full', serious.length ? 'bg-neg-soft text-neg' : 'bg-tile text-sec')}><Icon name="urgent" size={20} /></span>
        <span className="flex min-w-0 flex-1 flex-col">
          <span className="text-[14px] font-semibold">خطاخوان</span>
          <span className="text-[12px] text-sec">{serious.length ? `${serious.length} خطا و هشدار در این نسخه؛ آخرین ${ago(serious[0]!.lastAt ?? serious[0]!.at)}` : 'در این نسخه خطایی ثبت نشده'}</span>
        </span>
        <span className="text-muted"><Icon name="next" size={18} mirror /></span>
      </Card>
    </Link>
  );
}
