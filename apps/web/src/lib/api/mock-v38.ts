// ⟨1.20⟩ Demo of §38.3 «سرویس‌ها»: a memory budget that refuses «ساخت ویدیو و کاور» until the newsletter is off; a switch is a job that
// runs for a moment (the dispatcher's 10 s tick, shortened) and is polled.

const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status, headers: { 'content-type': 'application/json' } });
const problem = (status: number, code: string, message_fa: string) => json({ code, message_fa, status, title: code, type: 'about:blank' }, status);
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

type Svc = { key: string; title_fa: string; what_fa: string; state: 'on' | 'off' | 'starting' | 'failed'; optional: boolean; mem_cap_mb: number; can_toggle: boolean; note_fa: string | null };
const svc = (key: string, title_fa: string, what_fa: string, mem_cap_mb: number, on: boolean, optional = true): Svc =>
  ({ key, title_fa, what_fa, state: on ? 'on' : 'off', optional, mem_cap_mb, can_toggle: optional, note_fa: null });

const BUDGET_MB = 4000;
const services: Svc[] = [
  svc('api', 'هسته‌ی هاب', 'ثبت فرمان‌ها، کارتابل و دفتر ممیزی.', 900, true, false),
  svc('db', 'پایگاه داده', 'همه‌ی داده‌ی هلدینگ.', 600, true, false),
  svc('media', 'ساخت ویدیو و کاور', 'ریلز و کاور و تصویر برای شرکت‌ها می‌سازد.', 1200, false),
  svc('tts', 'صدای ساده‌ی هاب', 'خواندن متن با صدای سبک، بدون هزینه.', 600, false),
  svc('stt', 'تبدیل گفتار به متن', 'ویس‌ها را به متن فارسی برمیگرداند.', 600, true),
  svc('ocr', 'خواندن اسکن بایگانی', 'متن سندهای اسکن‌شده را درمیاورد.', 500, false),
  svc('newsletter', 'خبرنامه', 'خبرنامه‌ی هفتگی را مینویسد و میفرستد.', 1100, true),
  svc('automations', 'خودکارسازی (n8n)', 'قاعده‌ها و گردش‌کارهای بی‌هوش مصنوعی.', 600, true),
  svc('mcp', 'اتصال ابزارها (MCP)', 'ابزارهای بیرونی را به ایجنت‌ها میدهد.', 100, false),
  svc('tracing', 'ردیابی', 'ردّ دقیق هر فراخوانی برای عیب‌یابی.', 400, false),
];

type Job = { ref: string; key: string; on: boolean; turn_off: string[]; polls: number; state: string; result_fa: string | null; blocking: Array<{ key: string; title_fa: string; mem_cap_mb: number }> };
const jobs = new Map<string, Job>();
let seq = 0;
const used = () => services.filter((s) => s.state === 'on').reduce((n, s) => n + s.mem_cap_mb, 0);
const view = (j: Job) => ({ ref: j.ref, state: j.state, result_fa: j.result_fa, blocking: j.blocking });

export async function handle38(req: Request, p: string): Promise<Response | null> {
  const m = req.method;
  if (p === '/hub/services' && m === 'GET') {
    const caps = used();
    return json({
      memory: { total_mb: 8192, budget_mb: BUDGET_MB, caps_mb: caps, free_mb: BUDGET_MB - caps },
      services: services.map((s) => ({ ...s, mem_used_mb: s.state === 'on' ? Math.round(s.mem_cap_mb * 0.6) : null })),
      at: new Date().toISOString(),
    });
  }
  const sv = /^\/hub\/services\/([a-z_]+)$/.exec(p);
  if (sv && m === 'POST') {
    const s = services.find((x) => x.key === sv[1]);
    if (!s) return problem(404, 'not_found', 'این سرویس پیدا نشد.');
    if (!s.can_toggle) return problem(403, 'forbidden', 'این سرویس پایه است و خاموش نمیشود.');
    if (!UUID.test(req.headers.get('Idempotency-Key') ?? '')) return problem(422, 'validation_failed', 'کلید یکتا باید UUID باشد.');
    const b = (await req.clone().json().catch(() => ({}))) as { on?: boolean; turn_off?: string[] };
    if (typeof b.on !== 'boolean') return problem(422, 'validation_failed', 'روشن یا خاموش؟');
    const j: Job = { ref: `HJ-${String(++seq).padStart(4, '0')}`, key: s.key, on: b.on, turn_off: b.turn_off ?? [], polls: 0, state: 'queued', result_fa: null, blocking: [] };
    jobs.set(j.ref, j);
    return json(view(j), 202);
  }
  const jb = /^\/hub\/jobs\/([A-Z]+-\d+)$/.exec(p);
  if (jb && m === 'GET') {
    const j = jobs.get(jb[1]!);
    if (!j) return problem(404, 'not_found', 'این کار پیدا نشد.');
    if (++j.polls < 2) { j.state = 'running'; return json(view(j)); }
    if (j.state === 'running') {
      const s = services.find((x) => x.key === j.key)!;
      const freed = services.filter((x) => j.turn_off.includes(x.key) && x.state === 'on').reduce((n, x) => n + x.mem_cap_mb, 0);
      if (j.on && s.state !== 'on' && used() - freed + s.mem_cap_mb > BUDGET_MB) {
        j.state = 'refused';
        j.result_fa = 'جا نیست؛ این‌ها جا را گرفته‌اند';
        j.blocking = services.filter((x) => x.optional && x.state === 'on' && x.key !== s.key).sort((a, b) => b.mem_cap_mb - a.mem_cap_mb).map((x) => ({ key: x.key, title_fa: x.title_fa, mem_cap_mb: x.mem_cap_mb }));
      } else {
        for (const k of j.turn_off) { const x = services.find((y) => y.key === k); if (x) x.state = 'off'; }
        s.state = j.on ? 'on' : 'off';
        j.state = 'done';
        j.result_fa = j.on ? 'روشن شد' : 'خاموش شد';
      }
    }
    return json(view(j));
  }
  return null;
}
