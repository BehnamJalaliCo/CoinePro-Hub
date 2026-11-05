'use client';

// ⟨1.15⟩ Contract §33.9 «مخاطب‌ها»: the company's personas as data the owner edits, up to four suggestions from its knowledge base (kept
// only when the owner keeps them), and the message test — one score per persona, its objection and a fix, with the average and the lowest
// computed by code.

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Bar, Card, Empty, ErrorState, Pill, SectionTitle, StatTile } from '@/components/ui/primitives';
import { useToast } from '@/components/ui/toast';
import { FaPara, FaText, fig } from '@/components/v29/text';
import { errText, notYet } from '@/components/v31/kit';
import { PERSONA_LIST_MAX, usePersonaActions, usePersonas, type PersonaDraft, type PersonaRow, type PersonaTest } from '@/lib/api/v33';
import { Area, Loading, Txt } from './bits';

const lines = (s: string) => s.split('\n').map((x) => x.trim()).filter(Boolean).slice(0, PERSONA_LIST_MAX);
type Form = { id?: string; name_fa: string; summary_fa: string; channel_fa: string; pains: string; objections: string };
const blank: Form = { name_fa: '', summary_fa: '', channel_fa: '', pains: '', objections: '' };
const toForm = (p: PersonaRow): Form => ({ id: p.id, name_fa: p.name_fa, summary_fa: p.summary_fa, channel_fa: p.channel_fa, pains: p.pains_fa.join('\n'), objections: p.objections_fa.join('\n') });
const draftOf = (f: Form): PersonaDraft => ({ name_fa: f.name_fa.trim(), summary_fa: f.summary_fa.trim(), channel_fa: f.channel_fa.trim(), pains_fa: lines(f.pains), objections_fa: lines(f.objections) });

function PersonaCard({ p, suggested, children }: { p: PersonaDraft; suggested: boolean; children?: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-2 rounded-[14px] bg-tile p-4" aria-label={`مخاطب ${p.name_fa}`}>
      <div className="flex flex-wrap items-center gap-2"><h3 className="flex-1 text-[15px] font-semibold">{p.name_fa}</h3><Pill tone={suggested ? 'learn' : 'silver'}>{suggested ? 'پیشنهاد از دانشنامه' : 'نوشته‌ی تو'}</Pill></div>
      <FaPara text={p.summary_fa} className="text-[13px] leading-6 text-sec" />
      <div className="grid gap-3 sm:grid-cols-2">
        <div><h4 className="text-[11px] font-semibold text-muted">دردها</h4>{p.pains_fa.length ? <ul className="list-disc pr-4 text-[13px] leading-6 marker:text-muted">{p.pains_fa.map((x) => <li key={x}><FaText text={x} /></li>)}</ul> : <p className="text-[12px] text-muted">—</p>}</div>
        <div><h4 className="text-[11px] font-semibold text-muted">اعتراض‌ها</h4>{p.objections_fa.length ? <ul className="list-disc pr-4 text-[13px] leading-6 marker:text-muted">{p.objections_fa.map((x) => <li key={x}><FaText text={x} /></li>)}</ul> : <p className="text-[12px] text-muted">—</p>}</div>
      </div>
      {p.channel_fa ? <span className="text-[12px] text-sec">کجا پیدایش میکنیم: <FaText text={p.channel_fa} /></span> : null}
      {children}
    </div>
  );
}

const tone = (n: number): 'pos' | 'warn' | 'neg' => (n >= 70 ? 'pos' : n >= 40 ? 'warn' : 'neg');

function TestCard({ code, personas }: { code: string; personas: PersonaRow[] }) {
  const act = usePersonaActions(code);
  const toast = useToast();
  const [text, setText] = useState('');
  const [res, setRes] = useState<PersonaTest | null>(null);
  return (
    <Card as="section" className="flex flex-col gap-3 p-5" aria-label="سنجش پیام">
      <SectionTitle title="سنجش پیام" note="متن را بنویس؛ هر مخاطب نمره میدهد، میگوید چرا نه، و یک اصلاح پیشنهاد میکند" />
      <Area label="متن پیام" value={text} set={setText} rows={4} />
      <Button variant="primary" className="self-start" loading={act.test.isPending} disabled={!text.trim() || text.length > 8000 || !personas.length} onClick={() => act.test.mutate(text.trim(), { onSuccess: setRes, onError: (e) => toast({ tone: 'error', text: errText(e, 'سنجش انجام نشد.') }) })}>بسنج</Button>
      {!personas.length ? <p className="text-[12px] text-muted">اول دست‌کم یک مخاطب لازم است.</p> : null}
      {res ? (
        <div className="hq-rise flex flex-col gap-3">
          <div className="grid grid-cols-2 gap-3 sm:max-w-md">
            <StatTile label="میانگین" value={<span className="fig">{fig(res.average)}</span>} tone={tone(res.average)} />
            <StatTile label="کم‌ترین" value={<span className="fig">{fig(res.lowest)}</span>} tone={tone(res.lowest)} />
          </div>
          <ul className="flex flex-col gap-2" aria-label="نتیجه‌ی سنجش">
            {res.results.map((r) => (
              <li key={r.persona} className="flex flex-col gap-1.5 rounded-[12px] bg-tile p-3" aria-label={`نتیجه برای ${r.name_fa}`}>
                <div className="flex flex-wrap items-center gap-2"><span className="flex-1 text-[14px] font-semibold">{r.name_fa}</span><span className="fig text-[15px] font-semibold">{fig(r.score)}</span><Pill tone={r.would_act ? 'pos' : 'neg'} dot>{r.would_act ? 'اقدام میکند' : 'اقدام نمیکند'}</Pill></div>
                <Bar pct={r.score} tone={tone(r.score)} label={`نمره ${r.score}`} />
                {r.objection_fa ? <p className="text-[13px] leading-6"><span className="text-muted">اعتراض: </span><FaText text={r.objection_fa} /></p> : null}
                {r.fix_fa ? <p className="text-[13px] leading-6"><span className="text-gold-ink">اصلاح: </span><FaText text={r.fix_fa} /></p> : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </Card>
  );
}

export function CompanyPersonas({ code }: { code: string }) {
  const q = usePersonas(code);
  const act = usePersonaActions(code);
  const toast = useToast();
  const [form, setForm] = useState<Form | null>(null);
  const [ideas, setIdeas] = useState<{ basis_fa: string; list: PersonaDraft[] } | null>(null);
  if (q.isLoading) return <Loading h="h-64" />;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return notYet('companies', 'مخاطب‌ها بعد از به‌روزرسانی ستاد میاید', 'مخاطب‌های شرکت و سنجش پیام این‌جا میاید.');
  const list = q.data;
  const full = list.length >= PERSONA_LIST_MAX;
  const save = () => {
    if (!form) return;
    const done = { onSuccess: () => { toast({ tone: 'ok', text: 'ذخیره شد.' }); setForm(null); }, onError: (e: unknown) => toast({ tone: 'error', text: errText(e, 'ذخیره نشد.') }) };
    if (form.id) act.edit.mutate({ id: form.id, body: draftOf(form) }, done); else act.add.mutate({ ...draftOf(form), source: 'owner' }, done);
  };
  const dropIdea = (p: PersonaDraft) => setIdeas((x) => (x ? { ...x, list: x.list.filter((y) => y !== p) } : x));
  return (
    <div className="flex flex-col gap-4">
      <Card as="section" className="flex flex-col gap-3 p-5" aria-label="مخاطب‌های شرکت">
        <SectionTitle title="مخاطب‌های شرکت" note={<>خودت ویرایششان میکنی؛ پیشنهاد فقط وقتی نگه داری ذخیره میشود. حداکثر <span className="fig">{fig(PERSONA_LIST_MAX)}</span> مخاطب.</>}
          action={<span className="flex gap-2"><Button size="sm" icon="knowledge" loading={act.suggest.isPending} onClick={() => act.suggest.mutate(undefined, { onSuccess: (r) => { setIdeas({ basis_fa: r.basis_fa, list: r.personas.slice(0, 4) }); if (!r.personas.length) toast({ tone: 'ok', text: 'پیشنهاد تازه‌ای از دانشنامه نیامد.' }); }, onError: (e) => toast({ tone: 'error', text: errText(e, 'پیشنهاد نیامد.') }) })}>پیشنهاد از دانشنامه</Button><Button size="sm" variant="primary" icon="add" disabled={full} onClick={() => setForm(blank)}>مخاطب تازه</Button></span>} />
        {form ? (
          <div className="hq-rise flex flex-col gap-3 rounded-[12px] bg-tile p-4" aria-label="مشخصات مخاطب">
            <div className="grid gap-3 sm:grid-cols-2"><Txt label="نام" value={form.name_fa} set={(v) => setForm({ ...form, name_fa: v })} /><Txt label="کجا پیدایش میکنیم" value={form.channel_fa} set={(v) => setForm({ ...form, channel_fa: v })} /></div>
            <Area label="خلاصه" value={form.summary_fa} set={(v) => setForm({ ...form, summary_fa: v })} />
            <div className="grid gap-3 sm:grid-cols-2"><Area label="دردها (هر خط یکی)" value={form.pains} set={(v) => setForm({ ...form, pains: v })} /><Area label="اعتراض‌ها (هر خط یکی)" value={form.objections} set={(v) => setForm({ ...form, objections: v })} /></div>
            <div className="flex gap-2"><Button variant="primary" loading={act.add.isPending || act.edit.isPending} disabled={!form.name_fa.trim() || !form.summary_fa.trim()} onClick={save}>ذخیره</Button><Button onClick={() => setForm(null)}>بی‌خیال</Button></div>
          </div>
        ) : null}
        {ideas?.list.length ? (
          <div className="hq-rise flex flex-col gap-3 rounded-[14px] border border-dashed border-strong p-3" aria-label="پیشنهادها از دانشنامه">
            <h3 className="text-[13px] font-semibold text-learn">پیشنهاد از دانشنامه</h3>
            {ideas.basis_fa ? <p className="text-[12px] leading-6 text-sec"><FaText text={ideas.basis_fa} /></p> : null}
            {ideas.list.map((p) => (
              <PersonaCard key={p.name_fa} p={p} suggested>
                <div className="flex gap-2">
                  <Button size="sm" variant="primary" aria-label={`نگه دار ${p.name_fa}`} disabled={full} loading={act.add.isPending && act.add.variables?.name_fa === p.name_fa}
                    onClick={() => act.add.mutate({ ...p, pains_fa: p.pains_fa.slice(0, PERSONA_LIST_MAX), objections_fa: p.objections_fa.slice(0, PERSONA_LIST_MAX), source: 'kb_suggested' }, { onSuccess: () => { dropIdea(p); toast({ tone: 'ok', text: 'نگه داشته شد.' }); }, onError: (e) => toast({ tone: 'error', text: errText(e, 'ذخیره نشد.') }) })}>نگه دار</Button>
                  <Button size="sm" aria-label={`نه ${p.name_fa}`} onClick={() => dropIdea(p)}>نه</Button>
                </div>
              </PersonaCard>
            ))}
          </div>
        ) : null}
        {!list.length ? <Empty icon="companies" title="هنوز مخاطبی نیست" body="خودت بنویس یا از دانشنامه‌ی شرکت پیشنهاد بگیر." /> : (
          <div className="grid gap-3 lg:grid-cols-2">{list.map((p) => (
            <PersonaCard key={p.id} p={p} suggested={p.source === 'kb_suggested'}>
              <div className="flex gap-2">
                <Button size="sm" icon="edit" aria-label={`ویرایش ${p.name_fa}`} onClick={() => setForm(toForm(p))}>ویرایش</Button>
                <Button size="sm" aria-label={`حذف ${p.name_fa}`} loading={act.remove.isPending && act.remove.variables === p.id} onClick={() => act.remove.mutate(p.id, { onSuccess: () => toast({ tone: 'ok', text: 'کنار گذاشته شد.' }), onError: (e) => toast({ tone: 'error', text: errText(e, 'حذف نشد.') }) })}>حذف</Button>
              </div>
            </PersonaCard>
          ))}</div>
        )}
      </Card>
      <TestCard code={code} personas={list} />
    </div>
  );
}
