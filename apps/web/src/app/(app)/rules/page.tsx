'use client';

import { Button } from '@/components/ui/button';
import { PageHeader } from '@/components/ui/primitives';
import { useVoiceOrder } from '@/components/work/voice-order';
import { RulesList } from '@/components/v29/rules';

/** ⟨1.11⟩ §29.3: the owner's rules for the holding. */
export default function RulesPage() {
  const voice = useVoiceOrder();
  return (
    <>
      <PageHeader eyebrow="آنچه دیگر نباید تکرار شود؛ ناظر هر روز میپاید" title="قانون‌های من"
        actions={<Button variant="primary" icon="seal" onClick={() => voice({ mode: 'rule' })}>قانون تازه</Button>} />
      <RulesList onNew={() => voice({ mode: 'rule' })} />
    </>
  );
}
