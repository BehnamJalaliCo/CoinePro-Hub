'use client';

// ⟨2026-11-09⟩ The owner's own answer when he makes a session (the owner: «به محض اینکه سشن رو میسازم باید اول از من بپرسه با من یا
// خودکار»): «با من» (one step, then the holder asks) or «خودکار» (to the end). Nothing is chosen until he taps one, and the caller keeps
// its send off until then; the hub takes the answer over whatever the words say (§34.1).

import { Segmented } from '@/components/ui/primitives';
import { PACE_FA, type Pace } from '@/lib/api/v34';

export const PACE_ASK_FA = 'این جلسه چطور جلو برود؟';
export const PACE_PICK_FIRST_FA = 'اول یکی را انتخاب کن؛ بعد جلسه باز میشود.';
const HINT: Record<Pace, string> = {
  step: 'مسئول یک قدم برمیدارد و بعد از تو میپرسد.',
  auto: 'مسئول برنامه میریزد و تا آخر میرود؛ فقط برای مُهر می‌ایستد.',
};

export function PaceAsk({ pace, onChange }: { pace: Pace | null; onChange: (p: Pace) => void }) {
  return (
    <div className="flex flex-col gap-1.5" data-testid="pace-ask">
      <span className="text-[13px] font-semibold text-ink">{PACE_ASK_FA}</span>
      <Segmented<Pace | ''>
        label={PACE_ASK_FA}
        value={pace ?? ''}
        onChange={(v) => { if (v) onChange(v); }}
        options={[{ value: 'step', label: PACE_FA.step }, { value: 'auto', label: PACE_FA.auto }]}
      />
      <span className={pace ? 'text-[12px] text-muted' : 'text-[12px] text-gold-ink'}>{pace ? HINT[pace] : PACE_PICK_FIRST_FA}</span>
    </div>
  );
}
