'use client';

import { safeHref } from '@/lib/format';
import { useState } from 'react';
import { Icon } from '@/components/icon';
import { Button } from '@/components/ui/button';
import { Dialog, Sheet } from '@/components/ui/overlay';
import { Bar, Card, Pill, Skeleton, Switch } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { ApiError } from '@/lib/api/client';
import { ModelMark } from '@/components/brand/model-mark';
import { useConnections } from '@/lib/api/hooks';
import { faError, useSettings18, useSubstituteAction, useSubstituteLogin, type SeatIn, type Substitute, type SubstituteLogin } from '@/lib/api/v18';
import { ago, cx, jDateTime, tokens, until, usd } from '@/lib/format';
import { useNow } from '@/lib/store';
import { CAP, LOGIN, PLAYER, PlayerName, SEAT, SUB_STATUS, pct01, subModel } from './bits';

/** The terminal commands of §21.13 (the owner's own terminal; Claude never runs them). */
const WEB_LOGIN: Record<string, string> = { gpt: 'make chatgpt-web-login', gemini: 'make gemini-web-login', deepseek: 'make deepseek-web-login' };
const CLI_LOGIN: Record<string, string> = { gpt: 'make chatgpt-login', gemini: 'make gemini-login' };
const jDay = (t: number) => Number(new Intl.DateTimeFormat('en-US-u-ca-persian-nu-latn', { timeZone: 'Asia/Tehran', day: 'numeric' }).format(new Date(t)));

function Cmd({ text }: { text: string }) {
  const toast = useToast();
  return (
    <span className="flex items-center gap-1.5">
      <code dir="ltr" className="fig min-w-0 flex-1 truncate rounded-[8px] bg-page px-2 py-1 text-[12px] text-ink">{text}</code>
      <button type="button" aria-label="کپی دستور" onClick={() => void navigator.clipboard?.writeText(text).then(() => toast({ tone: 'info', text: 'کپی شد.' }), () => undefined)} className="flex size-7 flex-none items-center justify-center rounded-full text-sec hover:bg-hover hover:text-ink"><Icon name="share" size={14} /></button>
    </span>
  );
}

// -------------------------------------------------------------------- sign-in --
/** The CLI's own headless sign-in, from the app: a device code, or an auth code pasted back (write-only, ≤ 10 minutes). */
function LoginSheet({ s, connectionId, onClose }: { s: Substitute; connectionId: string; onClose: () => void }) {
  const act = useSubstituteAction();
  const toast = useToast();
  const [started, setStarted] = useState<SubstituteLogin | null>(null);
  const [notReady, setNotReady] = useState(false);
  const [code, setCode] = useState('');
  const poll = useSubstituteLogin(started ? connectionId : null, started?.id ?? null);
  const l = poll.data ?? started;
  const start = async () => {
    try { setStarted(await act.login.mutateAsync(connectionId)); } catch (e) { if (e instanceof ApiError && e.code === 'not_ready') setNotReady(true); else toast({ tone: 'error', text: faError(e) }); }
  };
  return (
    <Sheet open onOpenChange={(v) => !v && onClose()} width={520} title={<span className="flex items-center gap-2">ورود CLI <PlayerName player={s.player} size={16} /></span>}
      description="هاب رمز تو را هرگز نمیبیند؛ اعتبار فقط در volume خود runner میماند (بیرون از backup) و هیچ پاسخ، لاگ یا Audit آن را ندارد.">
      <div className="flex flex-col gap-4 text-[13px] leading-6">
        {!l && !notReady ? (
          <>
            <p className="text-sec">با passkey شروع کن؛ runner ورود بی‌مرورگر خود CLI را شروع میکند و نشانی ورود را میدهد. روی گوشی وارد شو.</p>
            <Button variant="primary" icon="lock" loading={act.login.isPending} onClick={start} className="self-start">شروع ورود با passkey</Button>
          </>
        ) : null}
        {notReady ? (
          <div className="flex flex-col gap-2 rounded-[12px] bg-tile p-3">
            <p className="text-ink">این نسخه‌ی CLI ورود بی‌مرورگر ندارد؛ از ترمینال خودت وارد شو:</p>
            {CLI_LOGIN[s.player] ? <Cmd text={CLI_LOGIN[s.player]!} /> : null}
          </div>
        ) : null}
        {l ? (
          l.state === 'done' ? (
            <p className="flex items-start gap-2 rounded-[12px] bg-pos-soft p-3 text-ink"><Icon name="seal" size={16} className="mt-1 text-pos" />وارد شد. جایگاه‌های CLI از همین حالا کار میکنند.</p>
          ) : l.state === 'waiting' ? (
            <div className="flex flex-col gap-3">
              <a href={safeHref(l.verification_url) ?? undefined} target="_blank" rel="noreferrer noopener" className="inline-flex items-center gap-1.5 self-start text-gold-ink hover:underline"><Icon name="globe" size={16} /><span dir="ltr" className="fig max-w-[22rem] truncate">{l.verification_url}</span></a>
              {l.method === 'device_code' && l.user_code ? (
                <div className="flex flex-col items-center gap-1 rounded-[14px] bg-tile p-4">
                  <span className="text-[12px] text-muted">این کد را آن‌جا بزن</span>
                  <span dir="ltr" className="fig text-[28px] font-semibold tracking-[.12em] text-ink">{l.user_code}</span>
                  <span className="text-[11px] text-muted">{until(l.expires_at)}؛ این صفحه خودش میفهمد.</span>
                </div>
              ) : (
                <div className="flex flex-col gap-2">
                  <label className="flex flex-col gap-1.5 font-semibold text-sec">کدی که گوگل نشان داد
                    <input type="password" autoComplete="off" value={code} onChange={(e) => setCode(e.target.value)} dir="ltr" placeholder="4/0Ab…" className="fig h-10 rounded-[10px] border border-strong bg-card px-3 text-[14px] text-ink outline-none focus:border-gold-ink" />
                    <span className="text-[11px] font-normal text-muted">فقط‌نوشتنی؛ {until(l.expires_at)}.</span>
                  </label>
                  <Button variant="primary" disabled={code.trim().length < 6} loading={act.code.isPending} className="self-start"
                    onClick={async () => { try { await act.code.mutateAsync({ connectionId, loginId: l.id, code: code.trim() }); setCode(''); void poll.refetch(); } catch (e) { toast({ tone: 'error', text: faError(e) }); } }}>بفرست</Button>
                </div>
              )}
            </div>
          ) : <p className="rounded-[12px] bg-warn-soft p-3 text-ink">{l.state === 'expired' ? 'وقتش گذشت؛ دوباره شروع کن.' : `نشد: ${l.status_reason ?? '—'}`}</p>
        ) : null}
        {CLI_LOGIN[s.player] && !notReady ? <div className="flex flex-col gap-1.5 text-[12px] text-muted"><span>یا از ترمینال خودت:</span><Cmd text={CLI_LOGIN[s.player]!} /></div> : null}
      </div>
    </Sheet>
  );
}

// ---------------------------------------------------------------------- seats --
function SeatsEditor({ s, onClose }: { s: Substitute; onClose: () => void }) {
  const act = useSubstituteAction();
  const toast = useToast();
  const [rows, setRows] = useState<SeatIn[]>(() => s.seats.map((x) => ({ seat: x.seat, via: x.via, model: x.model, enabled: x.enabled, per_day: x.per_day, ...(x.per_day_video != null ? { per_day_video: x.per_day_video } : {}) })));
  const patch = (i: number, p: Partial<SeatIn>) => setRows((rs) => rs.map((r, k) => (k === i ? { ...r, ...p } : r)));
  const save = async () => { try { await act.seats.mutateAsync({ s, seats: rows }); toast({ tone: 'ok', text: 'جایگاه‌ها ذخیره شد.' }); onClose(); } catch (e) { toast({ tone: 'error', text: faError(e) }); } };
  return (
    <Sheet open onOpenChange={(v) => !v && onClose()} width={600} title={<span className="flex items-center gap-2">جایگاه‌های <PlayerName player={s.player} size={16} /></span>}
      description="مُهر به همین فهرست بسته است. جایگاه متنی پیش‌فرض CLI است (اندازه‌پذیر و سریع)؛ «وب» یعنی چت نامحدود در مرورگر لاگین‌شده‌ی هاب."
      footer={<div className="flex gap-2"><Button variant="primary" icon="seal" loading={act.seats.isPending} onClick={save}>ذخیره با passkey</Button><Button variant="ghost" onClick={onClose}>انصراف</Button></div>}>
      <ul className="flex flex-col gap-2">
        {rows.map((r, i) => (
          <li key={r.seat} className={cx('flex flex-col gap-2 rounded-[12px] p-3', r.enabled ? 'bg-tile' : 'bg-card')}>
            <div className="flex items-center gap-2">
              <span className="flex min-w-0 flex-1 flex-col"><span className="text-[13px] font-semibold text-ink">{SEAT[r.seat]?.fa ?? r.seat}</span><span className="text-[11px] text-muted">{SEAT[r.seat]?.note}</span></span>
              <Switch label={`${SEAT[r.seat]?.fa ?? r.seat}: روشن`} checked={r.enabled} onChange={(v) => patch(i, { enabled: v })} />
            </div>
            <div className="flex flex-wrap items-center gap-2 text-[12px]">
              <div className="flex rounded-[8px] bg-card p-0.5" role="radiogroup" aria-label={`${r.seat}: مسیر`}>
                {(['cli', 'web'] as const).map((v) => <button key={v} type="button" role="radio" aria-checked={r.via === v} disabled={v === 'cli' && !s.runner} onClick={() => patch(i, { via: v })} className={cx('h-7 rounded-[6px] px-2.5 disabled:opacity-40', r.via === v ? 'bg-raised font-semibold text-ink' : 'text-sec')}>{CAP[v]}</button>)}
              </div>
              <select aria-label={`${r.seat}: مدل`} value={r.model} onChange={(e) => patch(i, { model: e.target.value })} className="fig h-8 rounded-[8px] border border-strong bg-card px-2 text-[12px] text-ink">
                {s.models.map((m) => <option key={m.id} value={m.id} disabled={!m.available}>{m.label}{m.available ? '' : ' (نیست)'}</option>)}
              </select>
              <label className="flex items-center gap-1.5 text-sec">در روز<input aria-label={`${r.seat}: سقف روزانه`} value={r.per_day} onChange={(e) => patch(i, { per_day: Number(e.target.value.replace(/\D/g, '') || 0) })} inputMode="numeric" className="fig h-8 w-14 rounded-[8px] border border-strong bg-card px-1 text-center text-ink" /></label>
              {r.per_day_video != null ? <label className="flex items-center gap-1.5 text-sec">ویدیو<input aria-label={`${r.seat}: سقف ویدیو`} value={r.per_day_video} onChange={(e) => patch(i, { per_day_video: Number(e.target.value.replace(/\D/g, '') || 0) })} inputMode="numeric" className="fig h-8 w-12 rounded-[8px] border border-strong bg-card px-1 text-center text-ink" /></label> : null}
            </div>
          </li>
        ))}
      </ul>
    </Sheet>
  );
}

// --------------------------------------------------------------------- player --
/** One substitute player: who it is, whether it can play today, what it did this Jalali month against its $20, and its seats. */
export function PlayerCard({ s }: { s: Substitute }) {
  const conns = useConnections();
  const settings = useSettings18();
  const now = useNow();
  const act = useSubstituteAction();
  const toast = useToast();
  const [seats, setSeats] = useState(false);
  const [login, setLogin] = useState(false);
  const [webOut, setWebOut] = useState(false);
  const p = PLAYER[s.player] ?? { fa: s.player, provider: s.player };
  const st = SUB_STATUS[s.status] ?? SUB_STATUS.off!;
  const conn = (conns.data ?? []).find((c) => c.key === s.connection);
  const m = s.month;
  const ratio = m.value_ratio;
  const behind = settings.data?.substitutes?.behind_ratio ?? 0.4;
  // The 15th of the Jalali month (§21.13): behind the ratio by then, the morning report suggests seats to widen.
  const late = !!now && ratio != null && ratio < behind && jDay(now) >= 15;
  const cli = LOGIN[s.login.state] ?? LOGIN.signed_out!;
  const web = LOGIN[s.web.state] ?? LOGIN.signed_out!;
  return (
    <Card className="flex flex-col gap-4 p-4">
      <div className="flex items-start gap-3">
        <span className="flex size-11 flex-none items-center justify-center rounded-[12px] bg-tile text-ink"><ModelMark provider={p.provider} size={24} /></span>
        <div className="flex min-w-0 flex-1 flex-col">
          <span className="text-[15px] font-semibold text-ink">{p.fa}</span>
          <span className="text-[12px] text-muted">{s.login.plan_fa} · <span className="fig">{s.connection}</span>{s.runner ? <> · <span className="fig">{s.runner}</span></> : ' · بی‌CLI'}</span>
        </div>
        <Pill tone={st.tone} dot>{st.fa}</Pill>
      </div>
      {s.status_reason ? <p className="rounded-[10px] bg-warn-soft px-3 py-2 text-[12px] leading-5 text-ink">{s.status_reason}{s.limited_until ? <> · {until(s.limited_until)}</> : null}</p> : null}

      <div className="flex flex-col gap-1.5">
        <div className="flex items-center gap-2 text-[12px]">
          <span className="flex-1 text-sec">این ماه</span>
          <span className="fig text-ink">{usd(m.equiv_usd)}</span>
          <span className="text-muted">{Number(m.price_usd) > 0 ? <>از <span className="fig">{usd(m.price_usd)}</span></> : 'رایگان'}</span>
          {ratio != null ? <span className={cx('fig w-11 text-left font-semibold', late ? 'text-warn' : 'text-ink')}>{pct01(ratio)}</span> : null}
        </div>
        {ratio != null ? (
          <div className="relative">
            <Bar pct={Math.min(100, ratio * 100)} tone={late ? 'warn' : 'gold'} label={`ارزش مصرف ${p.fa} در برابر اشتراک`} />
            <span aria-hidden className="absolute -top-0.5 h-2.5 w-0.5 rounded bg-[var(--hq-text-muted)]" style={{ insetInlineStart: `${behind * 100}%` }} title={`آستانه‌ی ${pct01(behind)}`} />
          </div>
        ) : null}
        <span className="flex flex-wrap gap-x-3 text-[11px] text-muted">
          <span>{m.calls} فراخوانی</span><span>{m.skipped} رد شده</span>
          <span className="fig">{tokens(m.input_tokens)} in · {tokens(m.output_tokens)} out</span>
          {m.estimated ? <span>تخمینی (CLI عدد نداد)</span> : null}
        </span>
        {late ? <p className="text-[11px] leading-5 text-warn">از نیمه‌ی ماه گذشته و ارزش مصرف زیر آستانه است؛ چند جایگاه را باز کن تا اشتراک هدر نرود. هیچ چیز خودبه‌خود باز نمیشود.</p> : null}
      </div>

      <div className="grid gap-2 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5 rounded-[12px] bg-tile p-3 text-[12px]">
          <div className="flex items-center gap-2"><span className="flex-1 font-semibold text-sec">ورود CLI</span>{s.runner ? <Pill tone={cli.tone} dot>{cli.fa}</Pill> : <span className="text-muted">CLI ندارد</span>}</div>
          {s.runner ? (
            <>
              <span className="text-[11px] text-muted">{s.login.last_ok_at ? `آخرین موفق ${ago(s.login.last_ok_at)}` : '—'}</span>
              <div className="flex flex-wrap gap-1.5">
                {s.login.state !== 'signed_in' ? <Button size="sm" variant="secondary" icon="lock" disabled={!conn} onClick={() => setLogin(true)}>ورود</Button> : null}
                {s.login.state === 'signed_in' && conn ? <Button size="sm" variant="ghost" loading={act.logout.isPending} onClick={() => act.logout.mutateAsync(conn.id).then(() => toast({ tone: 'info', text: 'ورود CLI پاک شد.' }), (e) => toast({ tone: 'error', text: faError(e) }))}>خروج با passkey</Button> : null}
              </div>
            </>
          ) : <span className="text-[11px] text-muted">همه‌ی جایگاه‌هایش از مرورگر لاگین‌شده است.</span>}
        </div>
        <div className="flex flex-col gap-1.5 rounded-[12px] bg-tile p-3 text-[12px]">
          <div className="flex items-center gap-2"><span className="flex-1 font-semibold text-sec">مرورگر هاب</span><Pill tone={web.tone} dot>{web.fa}</Pill></div>
          <span className="fig text-[11px] text-muted">{s.web.account} · {s.web.recipe_version}</span>
          {s.web.last_failure ? <span className="text-[11px] text-warn">{s.web.last_failure}</span> : <span className="text-[11px] text-muted">{s.web.last_ok_at ? `آخرین کار ${ago(s.web.last_ok_at)}` : '—'}</span>}
          {s.web.state !== 'signed_in' ? <div className="flex flex-col gap-1 pt-0.5"><span className="text-[11px] text-muted">ورود فقط از ترمینال خودت (noVNC روی <span className="fig">127.0.0.1</span> با تونل SSH):</span><Cmd text={WEB_LOGIN[s.player] ?? 'make web-login'} /></div>
            : <Button size="sm" variant="ghost" onClick={() => setWebOut(true)} className="self-start">پاک کردن پروفایل</Button>}
        </div>
      </div>

      <div className="flex flex-col gap-1.5">
        <div className="flex items-center gap-2">
          <span className="flex-1 text-[12px] font-semibold text-sec">جایگاه‌ها</span>
          <span className="text-[11px] text-muted">{(['text', 'image', 'video'] as const).map((k) => `${k === 'text' ? 'متن' : k === 'image' ? 'عکس' : 'ویدیو'}: ${CAP[s.capabilities[k]] ?? s.capabilities[k]}`).join(' · ')}</span>
          <Button size="sm" variant="text" icon="edit" onClick={() => setSeats(true)}>ویرایش</Button>
        </div>
        <ul className="flex flex-col gap-1">
          {s.seats.map((x) => {
            const usedPct = x.per_day ? (x.used_today / x.per_day) * 100 : 0;
            const skipped = !x.enabled || s.status !== 'ready' || (x.via === 'web' ? s.web.state !== 'signed_in' : s.login.state !== 'signed_in');
            return (
              <li key={x.seat} className={cx('grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1 rounded-[10px] px-2 py-1.5', skipped && 'opacity-60')}>
                <span className="flex min-w-0 items-center gap-2 text-[12px]">
                  <span className="truncate text-ink" title={SEAT[x.seat]?.note}>{SEAT[x.seat]?.fa ?? x.seat}</span>
                  <span className="fig flex-none text-[11px] text-muted">{CAP[x.via]} · {subModel(x.model)}</span>
                  {!x.enabled ? <span className="text-[11px] text-muted">خاموش</span> : skipped ? <span className="text-[11px] text-warn">رد میشود</span> : null}
                </span>
                <span className="fig text-[11px] text-sec">{x.used_today}/{x.per_day}{x.per_day_video != null ? <> · <span className="font-sans">ویدیو</span> {x.used_today_video ?? 0}/{x.per_day_video}</> : null}</span>
                <span className="col-span-2"><Bar pct={usedPct} height={4} tone={usedPct >= 100 ? 'warn' : 'silver'} label={`${SEAT[x.seat]?.fa ?? x.seat}: مصرف امروز`} /></span>
              </li>
            );
          })}
        </ul>
      </div>
      <div className="flex flex-wrap gap-1.5 text-[11px] text-muted">{s.models.map((x) => <span key={x.id} className={cx('fig rounded-full px-2 py-0.5', x.available ? 'bg-tile text-sec' : 'bg-warn-soft text-warn')}>{x.label} · {x.tier}{x.available ? '' : ' · نیست'}</span>)}</div>

      {seats ? <SeatsEditor s={s} onClose={() => setSeats(false)} /> : null}
      {login && conn ? <LoginSheet s={s} connectionId={conn.id} onClose={() => setLogin(false)} /> : null}
      <Dialog open={webOut} onOpenChange={setWebOut} title="پاک کردن پروفایل مرورگر" actions={<>
        <Button variant="danger" loading={act.webLogout.isPending} onClick={() => act.webLogout.mutateAsync(s.player).then(() => { setWebOut(false); toast({ tone: 'info', text: 'پروفایل پاک شد؛ جایگاه‌های وب تا ورود دوباره رد میشوند.' }); }, (e) => toast({ tone: 'error', text: faError(e) }))}>پاک کن، با passkey</Button>
        <Button variant="secondary" onClick={() => setWebOut(false)}>انصراف</Button>
      </>}>
        <p>پروفایل {s.web.account} و کوکی‌هایش پاک میشود. جایگاه‌هایی که از وب کار میکنند تا وقتی خودت دوباره وارد شوی رد میشوند (<span className="fig">{WEB_LOGIN[s.player]}</span>). {s.web.last_ok_at ? <>آخرین کار: {jDateTime(s.web.last_ok_at)}.</> : null}</p>
      </Dialog>
    </Card>
  );
}

export function PlayersSkeleton() {
  return <div className="grid gap-4 xl:grid-cols-3">{Array.from({ length: 3 }, (_, i) => <Skeleton key={i} className="h-96 rounded-[16px]" />)}</div>;
}
