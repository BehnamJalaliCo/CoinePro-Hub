'use client';

import { useRef, useState, type ReactNode } from 'react';
import { Icon } from '@/components/icon';
import { useAttachments } from '@/components/media/attachments';
import { Button, Spinner } from '@/components/ui/button';
import { Pill, SectionTitle, Segmented, Skeleton } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { ApiError } from '@/lib/api/client';
import { useBrandAction, useBrandVersion, useCompanyBrand, type BrandOptions, type CompanyBrand } from '@/lib/api/brand';
import { fileUrl } from '@/lib/api/v13';
import { cx, jDate } from '@/lib/format';
import { MarkSvg } from './company-mark';
import { Seal } from './seal';

// Contract §18.14: the owner gives the company's PNG logo, the hub traces it into a two-layer mark (code, no model), the
// owner looks at it beside the original, in every size and both themes, in the seal ready and sealed, and seals it.

const REASON_FA: Record<string, string> = {
  no_background: 'لوگو را با زمینه‌ی شفاف یا یکدست بدهید',
  too_complex: 'لوگو برای نشان خیلی پیچیده است؛ جزئیات را کم کن',
};
const LOGO_TYPES = ['image/png', 'image/webp', 'image/jpeg'];
const SIZES = [48, 24, 16];
const CHECKER = 'repeating-conic-gradient(var(--hq-surface-tile) 0 25%, var(--hq-surface-card) 0 50%) 0 0 / 16px 16px';

/** One theme: the mark at 160, 48, 24 and 16 px (24 and below in one ink, as lists draw it), the wordmark, and the seal ready
 *  and sealed. `data-theme` re-scopes the tokens, so both themes show side by side whatever the app's theme is. */
function Pane({ b, theme, nameFa, nameEn }: { b: CompanyBrand; theme: 'night' | 'day'; nameFa: string; nameEn: string }) {
  if (!b.mark) return null;
  return (
    <div data-theme={theme} className="tahrir flex min-w-0 flex-1 flex-col items-center gap-4 rounded-[14px] bg-page p-4 text-ink">
      <span className="self-start text-[11px] text-muted">{theme === 'night' ? 'شب' : 'روز'}</span>
      <span className="flex flex-col items-center gap-1.5">
        <span className="flex h-[160px] max-w-full items-center justify-center"><MarkSvg mark={b.mark} height={160} colors={b} className="max-h-full max-w-full" /></span>
        <span className="fig text-[10px] text-muted">160px</span>
      </span>
      {b.wordmark ? <MarkSvg mark={b.wordmark} height={28} colors={b} className="max-w-full" /> : null}
      <span className="flex items-end gap-5">
        {SIZES.map((h) => (
          <span key={h} className="flex flex-col items-center gap-1.5">
            <MarkSvg mark={b.mark!} height={h} mono={h <= 24} colors={b} />
            <span className="fig text-[10px] text-muted">{h}px</span>
          </span>
        ))}
      </span>
      <span className="flex flex-wrap items-center justify-center gap-4">
        <Seal code={b.company} nameFa={nameFa} nameEn={nameEn} mark={b.mark} size={96} />
        <Seal code={b.company} nameFa={nameFa} nameEn={nameEn} mark={b.mark} size={96} state="sealed" />
      </span>
    </div>
  );
}

function Previews({ b, nameFa, nameEn }: { b: CompanyBrand; nameFa: string; nameEn: string }) {
  return (
    <div className="flex min-w-0 flex-col gap-3 md:flex-row">
      <Pane b={b} theme="night" nameFa={nameFa} nameEn={nameEn} />
      <Pane b={b} theme="day" nameFa={nameFa} nameEn={nameEn} />
    </div>
  );
}

/** What the owner gave, on a checkerboard so transparency shows. */
function Original({ b }: { b: CompanyBrand }) {
  const src = b.source.file_id ? fileUrl(b.source.file_id) : null;
  return (
    <figure className="flex min-w-0 flex-col gap-2">
      <span className="flex aspect-square w-full items-center justify-center overflow-hidden rounded-[14px] p-3" style={{ background: CHECKER }}>
        {/* eslint-disable-next-line @next/next/no-img-element -- the owner's own file, served by the API */}
        {src ? <img src={src} alt="لوگوی اصلی" className="max-h-full max-w-full object-contain" /> : <Icon name="image" size={28} className="text-muted" />}
      </span>
      <figcaption className="flex flex-wrap items-center gap-x-2 text-[11px] text-muted">
        <span>اصل</span>
        <span className="fig">{b.source.width}×{b.source.height}</span>
        <span>{b.source.has_alpha ? 'شفاف' : 'بدون شفافیت'}</span>
      </figcaption>
    </figure>
  );
}

function Checks({ b }: { b: CompanyBrand }) {
  const c = b.checks;
  if (!c) return null;
  return (
    <div className="flex flex-col gap-2">
      {c.warnings.length ? (
        <ul className="flex flex-col gap-1.5">
          {c.warnings.map((w) => <li key={w} className="flex items-start gap-2 rounded-[10px] bg-warn-soft px-3 py-2 text-[13px] text-ink"><Icon name="info" size={16} className="mt-0.5 text-warn" />{w}</li>)}
        </ul>
      ) : <span className="flex items-center gap-2 text-[13px] text-pos"><Icon name="seal" size={14} active />همه‌ی سنجش‌ها پذیرفته شد</span>}
      <span className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-muted">
        <span>وفاداری <span className="fig text-sec">IoU {c.iou.toFixed(2)}</span></span>
        <span>نازک‌ترین جزء در ۱۶ پیکسل <span className="fig text-sec">{c.min_feature_px_16.toFixed(1)}px</span></span>
        {c.contrast_night != null ? <span>کنتراست شب <span className="fig text-sec">{c.contrast_night.toFixed(1)}:1</span></span> : null}
        {c.contrast_day != null ? <span>کنتراست روز <span className="fig text-sec">{c.contrast_day.toFixed(1)}:1</span></span> : null}
        <span className="fig">{(c.paths_bytes / 1024).toFixed(1)} KB</span>
      </span>
      {b.palette.length ? (
        <span className="flex flex-wrap items-center gap-2">
          {b.palette.map((p) => <span key={p.hex} className="flex items-center gap-1.5 text-[11px] text-muted"><span className="size-3.5 rounded-full border border-strong" style={{ background: p.hex }} /><span className="fig">{p.hex} · {Math.round(p.share * 100)}%</span></span>)}
        </span>
      ) : null}
    </div>
  );
}

/** «نشان و مُهر»: the active brand, a new logo traced into a mark, the proposal with its checks, retrace and seal. Shared by
 *  the company page and the founding's step «مُهر شرکت» (which names itself and shows the founding's own brand state). */
export function BrandBlock({ code, nameFa, nameEn, title = 'نشان و مُهر', badge }: { code: string; nameFa: string; nameEn: string; title?: string; badge?: ReactNode }) {
  const q = useCompanyBrand(code);
  const act = useBrandAction(code);
  const toast = useToast();
  const files = useAttachments(1);
  const input = useRef<HTMLInputElement>(null);
  const [part, setPart] = useState<'mark' | 'wordmark'>('mark');
  const [colors, setColors] = useState<'auto' | '1' | '2' | '3' | '4'>('auto');
  const [detail, setDetail] = useState<'1' | '2' | '3' | '4' | '5'>('3');
  // The version this page started (an upload or a retrace), followed until it is traced.
  const [work, setWork] = useState<CompanyBrand | null>(null);
  const polled = useBrandVersion(code, work?.version ?? null);
  const err = (e: unknown) => toast({ tone: 'error', text: e instanceof ApiError ? e.messageFa : 'انجام نشد.' });

  if (q.isLoading) return <Skeleton className="h-64" />;
  const active = q.data?.active ?? null;
  // An older proposal than the active version is history, not something to seal.
  const proposed = q.data?.proposed && (!active || q.data.proposed.version > active.version) ? q.data.proposed : null;
  const mine = work ? polled.data ?? work : null;
  const shown = mine && mine.state !== 'active' && mine.state !== 'retired' ? mine : proposed;
  const options: BrandOptions = { detail: Number(detail), ...(colors === 'auto' ? {} : { colors: Number(colors) }) };
  const logo = files.items[0] ?? null;
  const busy = act.upload.isPending || act.retrace.isPending || shown?.state === 'processing';

  const make = () => {
    if (!logo?.ref) return;
    act.upload.mutateAsync({ file_id: logo.ref.id, part, options })
      .then((v) => { setWork(v); files.clear(); })
      .catch(err);
  };
  const retrace = (b: CompanyBrand) => act.retrace.mutateAsync({ version: b.version, options }).then(setWork).catch(err);
  const seal = (b: CompanyBrand) => act.activate.mutateAsync(b)
    .then(() => { setWork(null); toast({ tone: 'ok', text: `مُهر شد؛ نشان تازه‌ی ${nameFa} همه‌جا دیده میشود.` }); })
    .catch(err);
  const pick = (f: File | undefined) => {
    if (!f) return;
    if (!LOGO_TYPES.includes(f.type)) { toast({ tone: 'error', text: `«${f.name}»: لوگو باید PNG (بهتر با زمینه‌ی شفاف)، WebP یا JPEG باشد.` }); return; }
    void files.add([f]);
  };

  return (
    <div className="flex flex-col gap-5">
      <SectionTitle
        title={title}
        note={active ? `نسخه‌ی ${active.version}، مُهرشده ${jDate(active.activated_at, true)}${active.source.kind === 'seed' ? '، از فایل‌های طراحی' : ''}` : 'هنوز نشانی مُهر نشده؛ تا آن موقع شرکت با کدش دیده میشود.'}
        action={badge ?? (active ? <Pill tone="pos" icon="seal">فعال</Pill> : <Pill tone="warn" dot>بدون نشان</Pill>)}
      />
      {q.error ? <p className="text-[13px] text-neg">{q.error instanceof ApiError ? q.error.messageFa : 'نشان شرکت خوانده نشد.'}</p> : null}
      {active ? <Previews b={active} nameFa={nameFa} nameEn={nameEn} /> : null}

      {shown ? (
        <div className="flex flex-col gap-4 border-t border-div pt-4">
          <SectionTitle
            title={shown.state === 'failed' ? 'ساخت نشان انجام نشد' : 'نشان تازه'}
            note={`نسخه‌ی ${shown.version}، رنگ‌ها ${shown.options.colors ?? 'خودکار'}، جزئیات ${shown.options.detail}`}
            action={shown.state === 'processing' ? <Pill tone="lapis" live>در حال ساخت</Pill> : shown.state === 'failed' ? <Pill tone="neg" dot>ناموفق</Pill> : <Pill tone="gold" dot>منتظر مُهر تو</Pill>}
          />
          {shown.state === 'processing' ? (
            <div className="flex items-center gap-3 rounded-[12px] bg-tile p-4 text-[13px] text-sec"><Spinner size={16} />زمینه جدا میشود، رنگ‌ها شمرده میشوند و هر لایه به مسیر برداری تبدیل میشود…</div>
          ) : shown.state === 'failed' ? (
            <div className="flex items-start gap-3 rounded-[12px] bg-neg-soft p-4 text-[13px] text-ink">
              <Icon name="urgent" size={18} className="mt-0.5 text-neg" />
              <span className="flex flex-col gap-1">
                <span className="font-semibold">{REASON_FA[shown.status_reason ?? ''] ?? 'نشان از این لوگو ساخته نشد.'}</span>
                <span className="text-sec">گزینه‌ها را عوض کن و دوباره بساز، یا لوگوی دیگری بده.</span>
              </span>
            </div>
          ) : (
            <>
              <div className="grid min-w-0 gap-4 lg:grid-cols-[minmax(0,200px)_minmax(0,1fr)]">
                <Original b={shown} />
                <Previews b={shown} nameFa={nameFa} nameEn={nameEn} />
              </div>
              <Checks b={shown} />
            </>
          )}
          {shown.state !== 'processing' ? (
            <div className="flex flex-wrap items-center gap-2">
              {shown.state === 'proposed' ? <Button variant="primary" icon="seal" loading={act.activate.isPending} onClick={() => seal(shown)}>مُهر کن</Button> : null}
              <Button variant="secondary" icon="refresh" loading={act.retrace.isPending} disabled={busy} onClick={() => retrace(shown)}>دوباره بساز</Button>
              <span className="text-[12px] text-muted">با گزینه‌های پایین، از همان فایل</span>
            </div>
          ) : null}
        </div>
      ) : null}

      <div className="flex flex-col gap-4 border-t border-div pt-4">
        <SectionTitle title="لوگوی تازه" note="PNG با زمینه‌ی شفاف بهترین است؛ WebP و JPEG هم پذیرفته میشوند. حداکثر ۴۰۹۶ پیکسل." />
        <div className="grid gap-3 sm:grid-cols-3">
          <div className="flex flex-col gap-1.5"><span className="text-[12px] text-sec">بخش</span>
            <Segmented label="بخش" value={part} onChange={setPart} options={[{ value: 'mark', label: 'نشان' }, { value: 'wordmark', label: 'لوگوتایپ' }]} /></div>
          <div className="flex flex-col gap-1.5"><span className="text-[12px] text-sec">رنگ‌ها</span>
            <Segmented label="رنگ‌ها" value={colors} onChange={setColors} options={(['auto', '1', '2', '3', '4'] as const).map((v) => ({ value: v, label: v === 'auto' ? 'خودکار' : v }))} /></div>
          <div className="flex flex-col gap-1.5"><span className="text-[12px] text-sec">جزئیات</span>
            <Segmented label="جزئیات" value={detail} onChange={setDetail} options={(['1', '2', '3', '4', '5'] as const).map((v) => ({ value: v, label: v }))} /></div>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <input ref={input} type="file" accept={LOGO_TYPES.join(',')} hidden onChange={(e) => { pick(e.target.files?.[0]); e.target.value = ''; }} />
          {logo ? (
            <span className={cx('flex min-w-0 items-center gap-3 rounded-[12px] bg-tile p-2 pe-3', logo.state === 'failed' && 'tahrir')}>
              <span className="flex size-12 flex-none items-center justify-center overflow-hidden rounded-[8px]" style={{ background: CHECKER }}>
                {/* eslint-disable-next-line @next/next/no-img-element -- local object URL preview */}
                {logo.preview ? <img src={logo.preview} alt="" className="max-h-full max-w-full object-contain" /> : null}
              </span>
              <span className="flex min-w-0 flex-col">
                <span className="truncate text-[13px] text-ink">{logo.name}</span>
                <span className={cx('text-[11px]', logo.state === 'failed' ? 'text-neg' : 'text-muted')}>{logo.state === 'uploading' ? <span className="fig">{logo.pct}%</span> : logo.state === 'failed' ? logo.error : 'بارگذاری شد'}</span>
              </span>
              {logo.state === 'failed' ? <Button size="sm" variant="ghost" icon="refresh" onClick={() => files.retry(logo.key)}>دوباره</Button> : null}
              <button type="button" aria-label="برداشتن لوگو" className="text-muted hover:text-ink" onClick={() => files.remove(logo.key)}><Icon name="close" size={16} /></button>
            </span>
          ) : <Button icon="image" onClick={() => input.current?.click()}>لوگوی تازه (PNG)</Button>}
          {logo ? <Button variant="secondary" icon="edit" disabled={logo.state !== 'ready' || busy} loading={act.upload.isPending} onClick={make}>نشان را بساز</Button> : null}
        </div>
      </div>
    </div>
  );
}
