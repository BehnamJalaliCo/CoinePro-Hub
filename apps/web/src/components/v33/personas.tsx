'use client';

// ⟨1.15⟩ Contract §33.9 «پرسونا»: the company's audience as data the owner edits, up to four suggestions from its knowledge base (kept only
// when the owner keeps them), and the message test — one score per persona, its objection, and a fix.

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Bar, Card, Empty, ErrorState, Pill, SectionTitle } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { FaPara, FaText, fig } from '@/components/v29/text';
import { errText, notYet } from '@/components/v31/kit';
import { usePersonaActions, usePersonas, type PersonaDraft, type PersonaRow, type PersonaTest } from '@/lib/api/v33';
import { Area, Loading, Txt } from './bits';

const lines = (s: string) => s.split('\n').map((x) => x.trim()).filter(Boolean);
type Form = { id?: string; version?: number; name_fa: string; summary_fa: string; channel_fa: string; pains: string; objections: string; source: PersonaDraft['source'] };
const blank: Form = { name_fa: '', summary_fa: '', channel_fa: '', pains: '', objections: '', source: 'owner' };
const toForm = (p: PersonaRow | PersonaDraft): Form => ({ id: (p as PersonaRow).id, version: (p as PersonaRow).version, name_fa: p.name_fa, summary_fa: p.summary_fa, channel_fa: p.channel_fa, pains: p.pains_fa.join('\n'), objections: p.objections_fa.join('\n'), source: p.source });

function PersonaCard({ p, children }: { p: PersonaRow | PersonaDraft; children?: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-2 rounded-[14px] bg-tile p-4" aria-label={`پرسونا ${p.name_fa}`}>
      <div className="flex flex-wrap items-center gap-2"><h3 className="flex-1 text-[15px] font-semibold">{p.name_fa}</h3><Pill tone={p.source === 'owner' ? 'silver' : 'learn'}>{p.source === 'owner' ? 'نوشته‌ی تو' : 'پیشنهاد از دانشنامه'}</Pill></div>
      <FaPara text={p.summary_fa} className="text-[13px] leading-6 text-sec" />
      <div className="grid gap-3 sm:grid-cols-2">
        <div><h4 className="text-[11px] font-semibold text-muted">دردها</h4><ul className="list-disc pr-4 text-[13px] leading-6 marker:text-muted">{p.pains_fa.map((x) => <li key={x}><FaText text={x} /></li>)}</ul></div>
        <div><h4 className="text-[11px] font-semibold text-muted">اعتراض‌ها</h4><ul className="list-disc pr-4 text-[13px] leading-6 marker:text-muted">{p.objections_fa.map((x) => <li key={x}><FaText text={x} /></li>)}</ul></div>
      </div>
      <span className="text-[12px] text-sec">کانال: <FaText text={p.channel_fa} /></span>
      {children}
    </div>
  );
}

function TestCard({ code, personas }: { code: string; personas: PersonaRow[] }) {
  const act = usePersonaActions(code);
  const toast = useToast();
  const [text, setText] = useState('');
  const [res, setRes] = useState<PersonaTest | null>(null);
  const name = (id: string) => personas.find((p) => p.id === id)?.name_fa ?? id;
  return (
    <Card as="section" className="flex flex-col gap-3 p-5" aria-label="آزمون پیام">
      <SectionTitle title="آزمون پیام" note="متن را بنویس؛ هر پرسونا نمره، اعتراض و اصلاح میدهد (یک فراخوانی برای همه، با مدل متوسط)" />
      <Area label="متن پیام" value={text} set={setText} rows={4} />
      <Button variant="primary" className="self-start" loading={act.test.isPending} disabled={!text.trim() || !personas.length} onClick={() => act.test.mutate(text.trim(), { onSuccess: setRes, onError: (e) => toast({ tone: 'error', text: errText(e, 'آزمون انجام نشد.') }) })}>بسنج</Button>
      {!personas.length ? <p className="text-[12px] text-muted">اول دست‌کم یک پرسونا لازم است.</p> : null}
      {res ? (
        <ul className="hq-rise flex flex-col gap-2" aria-label="نتیجه‌ی آزمون">
          {res.results.map((r) => (
            <li key={r.persona} className="flex flex-col gap-1.5 rounded-[12px] bg-tile p-3" aria-label={`نتیجه برای ${name(r.persona)}`}>
              <div className="flex flex-wrap items-center gap-2"><span className="flex-1 text-[14px] font-semibold">{name(r.persona)}</span><span className="fig text-[15px] font-semibold">{fig(r.score)}</span><Pill tone={r.would_act ? 'pos' : 'neg'} dot>{r.would_act ? 'اقدام میکند' : 'اقدام نمیکند'}</Pill></div>
              <Bar pct={r.score} tone={r.score >= 70 ? 'pos' : r.score >= 40 ? 'warn' : 'neg'} label={`نمره ${r.score}`} />
              {r.objection_fa ? <p className="text-[13px] leading-6"><span className="text-muted">اعتراض: </span><FaText text={r.objection_fa} /></p> : null}
              {r.fix_fa ? <p className="text-[13px] leading-6"><span className="text-gold-ink">اصلاح: </span><FaText text={r.fix_fa} /></p> : null}
            </li>
          ))}
        </ul>
      ) : null}
    </Card>
  );
}

export function CompanyPersonas({ code }: { code: string }) {
  const q = usePersonas(code);
  const act = usePersonaActions(code);
  const toast = useToast();
  const [form, setForm] = useState<Form | null>(null);
  const [ideas, setIdeas] = useState<PersonaDraft[] | null>(null);
  if (q.isLoading) return <Loading h="h-64" />;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return notYet('companies', 'پرسونا بعد از به‌روزرسانی ستاد میاید', 'مخاطب‌های شرکت و آزمون پیام این‌جا میاید.');
  const list = q.data;
  const save = () => {
    if (!form) return;
    const draft: PersonaDraft = { name_fa: form.name_fa.trim(), summary_fa: form.summary_fa.trim(), channel_fa: form.channel_fa.trim(), pains_fa: lines(form.pains), objections_fa: lines(form.objections), source: 'owner' };
    const done = { onSuccess: () => { toast({ tone: 'ok', text: 'ذخیره شد.' }); setForm(null); }, onError: (e: unknown) => toast({ tone: 'error', text: errText(e, 'ذخیره نشد.') }) };
    if (form.id) act.edit.mutate({ ...draft, id: form.id, version: form.version ?? 1 }, done); else act.add.mutate({ ...draft, source: form.source }, done);
  };
  return (
    <div className="flex flex-col gap-4">
      <Card as="section" className="flex flex-col gap-3 p-5" aria-label="پرسونا‌های شرکت">
        <SectionTitle title="مخاطب‌های شرکت" note="خودت ویرایششان می‌کنی؛ پیشنهاد فقط وقتی نگه داشته شود ذخیره میشود"
          action={<span className="flex gap-2"><Button size="sm" icon="knowledge" loading={act.suggest.isPending} onClick={() => act.suggest.mutate(undefined, { onSuccess: (r) => { setIdeas(r.slice(0, 4)); if (!r.length) toast({ tone: 'ok', text: 'پیشنهاد تازه‌ای از دانشنامه نیامد.' }); }, onError: (e) => toast({ tone: 'error', text: errText(e, 'پیشنهاد نیامد.') }) })}>پیشنهاد از دانشنامه</Button><Button size="sm" variant="primary" icon="add" onClick={() => setForm(blank)}>پرسونای تازه</Button></span>} />
        {form ? (
          <div className="hq-rise flex flex-col gap-3 rounded-[12px] bg-tile p-4" aria-label="مشخصات پرسونا">
            <div className="grid gap-3 sm:grid-cols-2"><Txt label="نام پرسونا" value={form.name_fa} set={(v) => setForm({ ...form, name_fa: v })} /><Txt label="کانال" value={form.channel_fa} set={(v) => setForm({ ...form, channel_fa: v })} /></div>
            <Area label="خلاصه" value={form.summary_fa} set={(v) => setForm({ ...form, summary_fa: v })} />
            <div className="grid gap-3 sm:grid-cols-2"><Area label="دردها (هر خط یکی)" value={form.pains} set={(v) => setForm({ ...form, pains: v })} /><Area label="اعتراض‌ها (هر خط یکی)" value={form.objections} set={(v) => setForm({ ...form, objections: v })} /></div>
            <div className="flex gap-2"><Button variant="primary" loading={act.add.isPending || act.edit.isPending} disabled={!form.name_fa.trim() || !form.summary_fa.trim()} onClick={save}>ذخیره</Button><Button onClick={() => setForm(null)}>بی‌خیال</Button></div>
          </div>
        ) : null}
        {ideas?.length ? (
          <div className="hq-rise flex flex-col gap-3 rounded-[14px] border border-dashed border-strong p-3" aria-label="پیشنهادها از دانشنامه">
            <h3 className="text-[13px] font-semibold text-learn">پیشنهاد از دانشنامه</h3>
            {ideas.map((p) => (
              <PersonaCard key={p.name_fa} p={p}>
                <div className="flex gap-2">
                  <Button size="sm" variant="primary" aria-label={`نگه دار ${p.name_fa}`} loading={act.add.isPending && act.add.variables?.name_fa === p.name_fa}
                    onClick={() => act.add.mutate({ ...p, source: 'kb_suggested' }, { onSuccess: () => { setIdeas((xs) => (xs ?? []).filter((x) => x !== p)); toast({ tone: 'ok', text: 'نگه داشته شد.' }); }, onError: (e) => toast({ tone: 'error', text: errText(e, 'ذخیره نشد.') }) })}>نگه دار</Button>
                  <Button size="sm" aria-label={`نه ${p.name_fa}`} onClick={() => setIdeas((xs) => (xs ?? []).filter((x) => x !== p))}>نه</Button>
                </div>
              </PersonaCard>
            ))}
          </div>
        ) : null}
        {!list.length ? <Empty icon="companies" title="هنوز پرسونایی نیست" body="خودت بنویس یا از دانشنامه‌ی شرکت پیشنهاد بگیر." /> : (
          <div className="grid gap-3 lg:grid-cols-2">{list.map((p) => (
            <PersonaCard key={p.id} p={p}>
              <div className="flex gap-2">
                <Button size="sm" icon="edit" aria-label={`ویرایش ${p.name_fa}`} onClick={() => setForm(toForm(p))}>ویرایش</Button>
                <Button size="sm" aria-label={`حذف ${p.name_fa}`} loading={act.remove.isPending && act.remove.variables === p.id} onClick={() => act.remove.mutate(p.id, { onError: (e) => toast({ tone: 'error', text: errText(e, 'حذف نشد.') }) })}>حذف</Button>
              </div>
            </PersonaCard>
          ))}</div>
        )}
      </Card>
      <TestCard code={code} personas={list} />
    </div>
  );
}
