'use client';

// Contract §27.1 ⟨1.9⟩ «با کدام مدل؟», as the Android app's ui/work/Player.kt: the owner names who plays an order — the router (default),
// Claude, a substitute seat (GPT, Gemini, DeepSeek: §21.13, within its daily cap, with the same masking) or the council of models (§27.2).
// Each choice wears its provider's logo; a substitute that is signed out, limited or off is greyed with the reason (chosen anyway, the run
// waits up to 30 minutes for it and then falls back to the router, and a notification says so).

import { Icon } from '@/components/icon';
import { ModelMark } from '@/components/brand/model-mark';
import { useSubstitutes } from '@/lib/api/v18';
import { PLAYER_OPTIONS, availabilityOf, councilSeats, optionNoteFa, optionOfWork, type PlayerOption, type Recognised } from '@/lib/players';
import { cx } from '@/lib/format';

/** An option's mark: the provider's logo; the router's model glyph; the council as the seated players' logos side by side. */
export function PlayerLogo({ o, size = 16, seats }: { o: PlayerOption; size?: number; seats?: PlayerOption[] }) {
  if (o.key === 'auto') return <Icon name="model" size={size} className="text-sec" />;
  if (o.key === 'council') {
    const list = seats?.length ? seats : PLAYER_OPTIONS.filter((x) => x.provider);
    return (
      <span className="inline-flex items-center" aria-hidden>
        {list.map((p, i) => (
          <span key={p.key} className="inline-flex items-center justify-center rounded-full border border-div bg-[var(--hq-surface-card)]" style={{ width: size, height: size, marginInlineStart: i ? -size * 0.38 : 0 }}>
            <ModelMark provider={p.provider} size={Math.round(size * 0.68)} />
          </span>
        ))}
      </span>
    );
  }
  return <ModelMark provider={o.provider} size={size} />;
}

/**
 * The compact choice of who plays: six chips, each with its logo; the substitutes' availability from `GET /substitutes`, a greyed chip
 * naming its state; under them one sentence on what the choice means and why a greyed player is greyed. [heard]: what a voice order named.
 */
export function PlayerPicker({ value, onChange, heard }: { value: PlayerOption; onChange: (o: PlayerOption) => void; heard?: Recognised | null }) {
  const { data: subs } = useSubstitutes();
  const seats = councilSeats(subs);
  const a = availabilityOf(value, subs);
  const greyed = PLAYER_OPTIONS.filter((o) => o.substitute && o.key !== value.key).map((o) => [o, availabilityOf(o, subs)] as const).filter(([, x]) => !x.ok);
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="pb-2 text-[13px] text-sec">با کدام مدل؟</legend>
      {heard ? (
        <span className="inline-flex flex-wrap items-center gap-1.5 self-start rounded-[10px] bg-lapis-soft px-2.5 py-1.5 text-[12px] font-semibold text-lapis">
          <Icon name="mic" size={13} />از گفتار شنیده شد: «{heard.phrase}» ← {heard.option.fa}
          {heard.option.key !== value.key ? <span className="font-normal text-sec">· انتخاب تو جایش نشست</span> : null}
        </span>
      ) : null}
      <div role="radiogroup" aria-label="با کدام مدل؟" className="flex flex-wrap gap-1.5">
        {PLAYER_OPTIONS.map((o) => {
          const on = o.key === value.key;
          const av = availabilityOf(o, subs);
          return (
            <button key={o.key} type="button" role="radio" aria-checked={on} aria-label={av.ok ? o.fa : `${o.fa}، ${av.stateFa}`} onClick={() => onChange(o)}
              className={cx('inline-flex h-[34px] items-center gap-1.5 rounded-full border px-2.5 text-[13px] transition-colors',
                on ? 'border-[var(--hq-line-tahrir)] bg-gold-soft font-semibold text-gold-ink' : 'border-strong hover:bg-hover', !on && (av.ok ? 'text-sec' : 'text-muted'))}>
              <span className={cx('inline-flex', !av.ok && 'opacity-45')}><PlayerLogo o={o} seats={o.key === 'council' ? seats : undefined} /></span>
              {o.fa}
              {!av.ok ? <span className="text-[11px] font-normal text-muted">{av.stateFa}</span> : null}
            </button>
          );
        })}
      </div>
      <p className={cx('text-[12px] leading-6', a.ok ? 'text-sec' : 'text-warn')}>{optionNoteFa(value, a, seats.length)}</p>
      {greyed.length ? (
        <ul className="flex flex-col gap-0.5">
          {greyed.map(([o, x]) => (
            <li key={o.key} className="flex items-start gap-1.5 text-[11px] leading-5 text-muted"><span className="mt-0.5 inline-flex opacity-50"><PlayerLogo o={o} size={12} /></span>{o.fa}: {x.stateFa}؛ {x.reasonFa}</li>
          ))}
        </ul>
      ) : null}
    </fieldset>
  );
}

/** Who plays an order, as a small tag: shown only when the owner named a player or called the council. */
export function PlayerTag({ player, mode, always }: { player?: string | null; mode?: string | null; always?: boolean }) {
  const o = optionOfWork(player, mode);
  if (o.key === 'auto' && !always) return null;
  const council = o.key === 'council';
  return (
    <span aria-label={`بازیکن: ${o.fa}`} className={cx('inline-flex h-[22px] flex-none items-center gap-1.5 rounded-full px-2 text-[11px] font-semibold', council ? 'bg-gold-soft text-gold-ink' : 'bg-tile text-sec')}>
      <PlayerLogo o={o} size={12} />{council ? 'شورا' : o.fa}
    </span>
  );
}

/** On an order's page: who plays it, with what that means; a named player that never came, said. */
export function PlayerLine({ player, mode, media, fallback }: { player?: string | null; mode?: string | null; media?: string | null; fallback?: boolean }) {
  const o = optionOfWork(player, mode);
  if (fallback) return <p className="flex items-center gap-2 text-[13px] text-warn"><Icon name="model" size={15} />بازیکن نامبرده ۳۰ دقیقه در دسترس نبود؛ از آن پس مسیریاب خودکار بازی میکند.</p>;
  const text = o.key === 'auto' ? 'بازیکن: خودکار؛ مسیریاب مدل انتخاب میکند'
    : o.key === 'council' ? (media === 'image' ? 'شورای مدل‌ها: هر بازیکن عکس خودش را میسازد؛ یکی را تو انتخاب میکنی' : media === 'video' ? 'شورای مدل‌ها: هر بازیکن ویدیوی خودش را میسازد؛ یکی را تو انتخاب میکنی' : 'شورای مدل‌ها: هر بازیکن جدا، Claude جمع‌بندی میکند')
    : o.key === 'claude' ? 'بازیکن: Claude' : `بازیکن: ${o.fa}، در سقف روزانه‌ی جایگاهش`;
  return <p className="flex items-center gap-2 text-[13px] text-sec"><PlayerLogo o={o} size={15} />{text}</p>;
}
