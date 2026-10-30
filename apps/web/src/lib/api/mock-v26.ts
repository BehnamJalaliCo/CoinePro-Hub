// Development-only fixtures (npm run dev:mock), imported only by mock.ts. ⟨1.8⟩ Contract §26: the holding's servers, each with its
// `hq-runner`, as the hub would answer, the same world as the Android app's DemoServers.kt:
//
// - CoinePro FX's server (`fx-main`, user `forex`) online with a rich map in §26.5's shape; TradeYar's (`ty-web`) online with a map written
//   as the shell prints it; Pro-Chart's (`pc-app`) approved, its runner not yet polling.
// - FX's `fx-gpu` offline (its runner stopped polling three hours ago); TradeYar's `ty-staging` detached (revoked).
// - Activity (jobs, §26.2): FX's CTO deploying (one job running, one queued), TradeYar's SEO analyst reading the nginx config, a Claude
//   Code session on TY's server (`runtime: company_server`) working live; one destructive command (`DROP TABLE`) waiting for the seal as a
//   `server_destructive` card a few seconds after the servers wake, with its `server.awaiting_seal` on the stream.
// - The owner's terminal answers a few commands as a server would, streamed line by line as SSE; a destructive one becomes a card (202),
//   a stopped company refuses (423). Pairing, detach, the policy and the seal check the step-up header like the hub; a code ending in
//   `0000` has expired, one starting `ZZZZ` is unknown.
// - The network map (§26.6) is its own small world: FX, TradeYar and Pro-Chart on the private network a few ms from the hub, Pro-Chart's
//   runner refused on FX's SSH port, IG-Hub outside the private network; «بررسی دوباره» answers runner by runner.
//
// The world wakes the first time anything asks for `/infra/servers`, so pages that never show servers see the holding as before.

type Ctx = {
  decisions: any[];
  sessions: any[];
  employees: any[];
  control: { holding: { state: string }; companies: Array<{ company: string; state: string }> };
  sessionOut: (x: any) => any;
};
export type DemoEvent = { id: string; type: string; at: string; company: string | null; ref: string | null; data: Record<string, unknown> };

const OWNER = { kind: 'owner', code: 'owner', display_fa: 'مدیر کل' };
const SYS = { kind: 'system', code: 'HQ-SYS', display_fa: 'سیستم' };
const actor = (code: string, display_fa: string, kind = 'agent') => ({ kind, code, display_fa });
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });
const page = (items: unknown[]) => ({ items, next_cursor: null });
const problem = (status: number, code: string, fa: string) => json({ code, message_fa: fa, status, title: code, type: 'about:blank' }, status);
const isoAt = (min: number) => new Date(Date.now() + min * 60_000).toISOString();
const nowIso = () => new Date().toISOString();
const GIB = 1024 ** 3;
const RUNNER_VERSION = '0.1.0';
/** Codes `hq-runner pair` printed on servers waiting for the owner (§26.1): the company and the `--name` each was run with. */
const PAIRS: Record<string, [string, string]> = { 'FX3R-82NB': ['FX', 'fx-worker'], 'TY7K-M4QD': ['TY', 'ty-media'] };

let awake = false;
let wokeAt = 0;
let sealRaised = false;
let seq = 100;
let nextCard = 202;
let lastBeat = 0;
let beat = 0;
const servers: any[] = [];
const maps: Record<string, any> = {};
const activity: Record<string, any[]> = {};
let policy = ['db_drop', 'volume_delete', 'backup_delete', 'disk_wipe', 'access_change', 'server_delete'];
const attaching = new Map<string, number>();
const queue: DemoEvent[] = [];
let ctx: Ctx | null = null;

const server = (id: string, company: string, name: string, ip: string, user: string, host: string, state: string, seen: string | null, mapAt: string | null, via: string | null = state === 'online' ? 'private' : null, rtt: number | null = state === 'online' ? 2.6 : null) => ({
  id, company, name, origin: 'attached', private_ip: ip, user, hostname: host, runner_version: RUNNER_VERSION, state, last_seen_at: seen, map_at: mapAt, via, hub_rtt_ms: rtt, created_at: isoAt(-60 * 24 * 3),
});

/** One job of §26.2 (`kind`, `args`, `state`, its times) carrying its command's row fields too, as `…/activity` pages them. */
function call(serverId: string, code: string, fa: string, tool: string, summary: string, cmd: string | null, exit: number | null, ms: number | null, minutes: number, o: { session?: string; kind?: string; state?: string; cwd?: string } = {}) {
  const n = seq++;
  const st = o.state ?? (exit == null && ms == null ? 'running' : exit == null || exit === 0 ? 'done' : 'failed');
  return {
    id: `job-${n}`, at: isoAt(minutes), actor: actor(code, fa, code === 'owner' ? 'owner' : o.kind ?? 'agent'), tool, kind: tool.replace('server.', ''),
    args: { ...(cmd ? { cmd } : {}), ...(o.cwd ? { cwd: o.cwd } : {}) }, summary_fa: summary, state: st, created_at: isoAt(minutes),
    started_at: st === 'queued' ? null : isoAt(minutes), finished_at: ['done', 'failed', 'cancelled'].includes(st) ? isoAt(minutes) : null,
    cmd_masked: cmd, exit_code: exit, duration_ms: ms, session_ref: o.session ?? null, server: serverId,
    transcript_url: cmd ? `/api/v1/infra/servers/${serverId}/jobs/job-${n}/transcript` : null,
  };
}

function event(company: string | null, type: string, ref: string | null, data: Record<string, unknown>) {
  queue.push({ id: `demo-srv-${seq++}`, type, at: nowIso(), company, ref, data });
}

const edit = (id: string, patch: Record<string, unknown>) => { const s = servers.find((x) => x.id === id); if (s) Object.assign(s, patch); return s; };
const locked = (company: string) => !!ctx && (ctx.control.holding.state === 'engaged' || ctx.control.companies.some((k) => k.company === company && k.state === 'engaged'));

/** FX's map exactly in §26.5's binding shape (`GET …/map` → `{at, map}`). */
function fxMap(at: string) {
  const c = (name: string, image: string, st: string | null) => ({ name, image, state: st === 'exited' ? 'exited' : 'running', health: st === 'healthy' ? 'healthy' : null, project: 'coinepro-fx' });
  return {
    at,
    map: {
      os: 'Ubuntu 24.04.1 LTS', kernel: '6.8.0-47-generic', uptime_s: 1_900_800, cpu: { cores: 8, load1: 0.84 },
      memory: { total_mb: 15_872, used_mb: 11_468, swap_total_mb: 8_192, swap_used_mb: 1_126 }, disks: [{ mount: '/', total_gb: 150, used_gb: 62 }],
      containers: [
        c('coinepro-fx-api-1', 'coinepro-fx-api:a41c09e', 'healthy'), c('coinepro-fx-celery-worker-1', 'coinepro-fx-api:a41c09e', null), c('coinepro-fx-celery-beat-1', 'coinepro-fx-api:a41c09e', null),
        c('coinepro-fx-timescaledb-1', 'timescale/timescaledb:2.17.2-pg16', 'healthy'), c('coinepro-fx-redis-1', 'redis:7.4-alpine', 'healthy'), c('coinepro-fx-bot-1', 'coinepro-fx-bot:a41c09e', null),
        c('coinepro-fx-website-1', 'coinepro-fx-website:7d20f13', null), c('coinepro-fx-admin-1', 'coinepro-fx-admin:7d20f13', null), c('coinepro-fx-n8n-1', 'n8nio/n8n:1.68.0', null),
        c('coinepro-fx-backtest-1', 'coinepro-fx-api:c9b81aa', 'exited'),
      ],
      compose: [{ project: 'coinepro-fx', path: '/home/forex/CoinePro-FX', services: ['api', 'celery-worker', 'celery-beat', 'timescaledb', 'redis', 'bot', 'website', 'admin', 'n8n', 'backtest'] }],
      systemd: [
        ...[['docker.service', 'active'], ['ssh.service', 'active'], ['caddy.service', 'active'], ['hq-runner.service', 'active'], ['unattended-upgrades.service', 'active'], ['fx-healthcheck.service', 'inactive']]
          .map(([unit, state]) => ({ unit, state, timer: false, next_at: null })),
        ...([['fx-backup.timer', 95], ['certbot.timer', 210], ['apt-daily-upgrade.timer', 21 * 60]] as const).map(([unit, m]) => ({ unit, state: 'active', timer: true, next_at: isoAt(m) })),
      ],
      cron: [
        { user: 'forex', schedule: '*/5 * * * *', cmd_masked: '/home/forex/CoinePro-FX/scripts/healthcheck.sh' },
        { user: 'forex', schedule: '30 2 * * *', cmd_masked: 'cd /home/forex/CoinePro-FX && BACKUP_KEY=*** bash scripts/backup.sh' },
      ],
      ports: ([[22, '10.10.1.2', 'sshd'], [80, '0.0.0.0', 'caddy'], [443, '0.0.0.0', 'caddy'], [8000, '127.0.0.1', 'docker-proxy'], [5432, '127.0.0.1', 'docker-proxy'], [6379, '127.0.0.1', 'docker-proxy'], [5678, '127.0.0.1', 'n8n']] as const)
        .map(([port, bind, process]) => ({ port, proto: 'tcp', bind, process, public: bind === '0.0.0.0' })),
      repos: [
        { path: '/home/forex/CoinePro-FX', remote: 'git@github.com:behnamjalalico/CoineProFx.git', branch: 'claude/wizardly-edison-zyWyW', dirty: false, last_commit_at: isoAt(-4) },
        { path: '/home/forex/fx-landing', remote: 'git@github.com:behnamjalalico/fx-landing.git', branch: 'main', dirty: true, last_commit_at: isoAt(-60 * 24 * 3) },
      ],
      automations: [
        { kind: 'n8n', name: 'گزارش روزانه‌ی سیگنال‌ها به تلگرام', active: true, detail: 'cron 08:00' },
        { kind: 'n8n', name: 'هشدار افت دقت مدل', active: true, detail: 'webhook' },
        { kind: 'n8n', name: 'بک‌تست هفتگی', active: false, detail: 'cron Fri 22:00' },
        { kind: 'other', name: 'به‌روزرسانی کندل‌ها', active: true, detail: 'celery-beat · refresh_candles · every 1m' },
        { kind: 'other', name: 'پایش drift مدل‌ها', active: true, detail: 'celery-beat · drift_check · every 1h' },
      ],
      sites: [{ host: 'coineprofx.com', upstream: 'website:80' }, { host: 'api.coineprofx.com', upstream: 'api:8000' }, { host: 'admin.coineprofx.com', upstream: 'admin:80' }],
    },
  };
}

/** TradeYar's map, written the way `df -h` and `docker compose ls` print (sizes as text, `running(4)`), as a mapper may send it. */
function tyMap(at: string) {
  const remote = (repo: string) => [{ name: 'origin', url: `git@github.com:behnamjalalico/${repo}.git` }];
  return {
    taken_at: at, hostname: 'tradeyar-web', os: 'Ubuntu 24.04.1 LTS', kernel: '6.8.0-45-generic', cpus: 8, uptime_s: 4_406_400,
    disk: { mount: '/', size: '150G', used: '97G' }, memory: { total: '15Gi', available: '5.1Gi' },
    containers: [['tradeyar-app-1', 'Up 5 days'], ['tradeyar-worker-1', 'Up 5 days'], ['tradeyar-postgres-1', 'Up 41 days'], ['tradeyar-redis-1', 'Up 41 days']]
      .map(([names, status]) => ({ names, image: names!.replace(/^tradeyar-/, '').replace(/-1$/, ''), status, labels: { 'com.docker.compose.project': 'tradeyar' } })),
    compose: [{ name: 'tradeyar', config_files: '/home/tradeyar/TradeYar/docker-compose.yml', status: 'running(4)', services: 4 }],
    timers: [{ unit: 'ty-sitemap.timer', next: isoAt(50), activates: 'ty-sitemap.service' }],
    cron: ['0 3 * * * /home/tradeyar/TradeYar/scripts/backup.sh'],
    listening: ['0.0.0.0:443', '0.0.0.0:80', '10.10.1.3:22', '127.0.0.1:3000', '127.0.0.1:5432'],
    repos: [
      { path: '/home/tradeyar/TradeYar', remotes: remote('TradeYar'), branch: 'main', commit: '5be0a7d91c3e' },
      { path: '/home/tradeyar/ty-blog', remotes: remote('ty-blog'), branch: 'main', commit: 'e41f2c7a90b3', dirty: true },
    ],
    sites: [
      { server_name: 'tradeyar.com', proxy_pass: 'http://127.0.0.1:3000', https: true, via: 'nginx' },
      { server_name: 'www.tradeyar.com', proxy_pass: '301 → tradeyar.com', https: true, via: 'nginx' },
    ],
  };
}

const smallMap = (at: string) => ({ taken_at: at, os: 'Ubuntu 24.04.1 LTS', cpus: 4, disk: { total_bytes: 80 * GIB, used_bytes: 12 * GIB }, memory: { total_bytes: 8 * GIB, used_bytes: 2 * GIB } });

/** The servers, their maps and activity, the session on TY's server: made once, on first use. The card waiting for the seal follows. */
function wake() {
  if (awake || !ctx) return;
  awake = true;
  wokeAt = Date.now();
  lastBeat = Date.now();
  servers.push(
    server('srv-fx-1', 'FX', 'fx-main', '10.10.1.2', 'forex', 'coinepro-fx', 'online', isoAt(0), isoAt(-12), 'private', 3),
    server('srv-ty-1', 'TY', 'ty-web', '10.10.1.3', 'tradeyar', 'tradeyar-web', 'online', isoAt(0), isoAt(-40), 'private', 2),
    server('srv-pc-1', 'PC', 'pc-app', '10.10.1.1', 'prochart', 'pro-chart', 'pending', null, null),
    // FX's GPU box is switched off at night (its runner stopped polling); TradeYar's old staging server was detached.
    server('srv-fx-2', 'FX', 'fx-gpu', '10.10.1.12', 'forex', 'fx-gpu', 'offline', isoAt(-190), null, 'private', null),
    server('srv-ty-2', 'TY', 'ty-staging', '10.10.1.13', 'tradeyar', 'ty-staging', 'revoked', isoAt(-60 * 50), null, null, null),
  );
  maps['srv-fx-1'] = fxMap(isoAt(-12));
  maps['srv-ty-1'] = tyMap(isoAt(-40));
  const FX = '/home/forex/CoinePro-FX';
  activity['srv-fx-1'] = [
    call('srv-fx-1', 'FX-TECH-MGR', 'مدیر فنی FX', 'server.exec', 'سلامت API بعد از انتشار', 'curl -fsS http://127.0.0.1:8000/health', null, null, 0, { state: 'queued' }),
    call('srv-fx-1', 'FX-TECH-MGR', 'مدیر فنی FX', 'server.exec', 'انتشار API: ساخت و بالا آوردن کانتینر تازه', 'docker compose up -d --build api', null, null, -1, { state: 'running', cwd: FX }),
    call('srv-fx-1', 'FX-TECH-MGR', 'مدیر فنی FX', 'server.exec', 'migration پایگاه داده اجرا شد', 'docker compose exec -T api alembic upgrade head', 0, 6_420, -3, { cwd: FX }),
    call('srv-fx-1', 'FX-TECH-MGR', 'مدیر فنی FX', 'server.exec', 'آخرین کد از GitHub', 'git pull --ff-only origin claude/wizardly-edison-zyWyW', 0, 2_310, -4),
    call('srv-fx-1', 'FX-TECH-MGR', 'مدیر فنی FX', 'server.exec', 'تست‌های فاز ۱۵ پیش از انتشار سبز', 'python -m pytest tests/test_phase15*.py -q', 0, 48_900, -9),
    call('srv-fx-1', 'FX-QUANT-02', 'پایشگر سیگنال', 'server.read', 'خواندن لاگ موتور سیگنال', 'tail -n 200 logs/signals.log', 0, 140, -18),
    call('srv-fx-1', 'FX-QUANT-02', 'پایشگر سیگنال', 'server.exec', 'بک‌تست بلند؛ با کلید توقف دیروز لغو شد', 'docker compose run --rm backtest --days 365', null, 41_000, -20, { state: 'cancelled' }),
    call('srv-fx-1', 'HQ-SYS', 'سیستم', 'server.map', 'نقشه‌ی سرور گرفته شد', null, 0, 3_870, -12, { kind: 'system' }),
  ].sort((a, b) => b.at.localeCompare(a.at));
  // A Claude Code session on TradeYar's server, run by its CTO, live; and its SEO analyst reading the nginx config.
  const ref = 'S-0011';
  const TY = '/home/tradeyar/TradeYar';
  activity['srv-ty-1'] = [
    call('srv-ty-1', 'TY-TECH-MGR', 'مدیر فنی تریدیار', 'server.claude', 'Claude Code روی سرور: کش nginx صفحه‌های بازار', null, null, null, -6, { session: ref, state: 'running', cwd: TY, kind: 'manager' }),
    call('srv-ty-1', 'TY-TECH-MGR', 'مدیر فنی تریدیار', 'server.exec', 'پیکربندی nginx سالم است', 'sudo nginx -t', 0, 210, -3, { session: ref, kind: 'manager' }),
    call('srv-ty-1', 'TY-GROWTH-01', 'تحلیلگر سئوی فنی', 'server.read', 'خواندن پیکربندی nginx برای canonical و redirectها', 'cat /etc/nginx/sites-enabled/tradeyar.conf', 0, 90, -2),
    call('srv-ty-1', 'TY-GROWTH-01', 'تحلیلگر سئوی فنی', 'server.exec', 'سرعت پاسخ صفحه‌ی اصلی', "curl -s -o /dev/null -w '%{time_total}' https://tradeyar.com/", 0, 1_180, -7),
    call('srv-ty-1', 'TY-GROWTH-01', 'تحلیلگر سئوی فنی', 'server.exec', 'بررسی لینک‌های شکسته؛ یک صفحه 404 داد', 'npx linkinator https://tradeyar.com --recurse', 1, 38_400, -15, { state: 'failed' }),
  ].sort((a, b) => b.at.localeCompare(a.at));
  const tech = actor('TY-TECH-MGR', 'مدیر فنی تریدیار', 'manager');
  const curl = "for i in $(seq 10); do curl -s -o /dev/null -w '%{time_total}\\n' https://tradeyar.com/market; done";
  const ev = (n: number, min: number, type: string, a: any, summary_fa: string, data: Record<string, unknown> = {}) => ({ seq: n, at: isoAt(min), type, actor: a, summary_fa, data });
  if (!ctx.sessions.some((x) => x.ref === ref)) ctx.sessions.unshift({
    id: `s-${ref}`, ref, workspace: '', grant: '', runtime: 'company_server', server: 'srv-ty-1', company: 'TY',
    title: 'کش nginx برای صفحه‌های بازار', brief: 'صفحه‌های بازار تریدیار در ساعت شلوغی کند میشوند. کش nginx را برای مسیرهای /market فعال کن، با nginx -t بسنج، reload کن، زمان پاسخ را قبل و بعد اندازه بگیر و تغییر را در ریپو commit و push کن.',
    opened_by: OWNER, driver: tech, model: 'claude-sonnet-5-5', effort: 'high', state: 'working', branch: 'main', pr_url: null, usage: { usd: 0.62, input_tokens: 84_000, output_tokens: 6_100 },
    created_at: isoAt(-6), updated_at: isoAt(-1),
    events: [
      ev(1, -6, 'state', SYS, `Claude Code روی ty-web شروع شد؛ در ${TY}`, { state: 'working' }),
      ev(2, -6, 'message', tech, 'شروع کردم. اول زمان پاسخ فعلی /market را میگیرم و پیکربندی nginx را میخوانم.'),
      ev(3, -5, 'command', tech, 'میانگین زمان پاسخ /market در ده درخواست: ۱٫۸ ثانیه', { cmd: curl, exit_code: 0, duration_s: 19 }),
      ev(4, -4, 'file_change', tech, 'منطقه‌ی کش و قاعده‌ی /market', { path: 'deploy/nginx/tradeyar.conf', added: 14, removed: 2 }),
      ev(5, -3, 'command', tech, 'پیکربندی nginx سالم است', { cmd: 'sudo nginx -t', exit_code: 0, duration_s: 1 }),
    ],
    script: [
      { type: 'command', actor: tech, summary_fa: 'nginx بدون قطع سرویس دوباره بارگذاری شد', data: { cmd: 'sudo systemctl reload nginx', exit_code: 0, duration_s: 1 } },
      { type: 'command', actor: tech, summary_fa: 'بعد از کش: میانگین ۰٫۲۴ ثانیه (۷ برابر سریع‌تر)', data: { cmd: curl, exit_code: 0, duration_s: 4 } },
      { type: 'command', actor: tech, summary_fa: 'commit و push روی main', data: { cmd: "git commit -am 'nginx: cache /market for 60s' && git push origin main", exit_code: 0, duration_s: 3 } },
      { type: 'message', actor: tech, summary_fa: '**تمام شد.** کش ۶۰ ثانیه‌ای روی `/market` فعال است، زمان پاسخ از ۱٫۸ به ۰٫۲۴ ثانیه رسید و تغییر در `deploy/nginx/tradeyar.conf` روی main است.', data: {} },
      { type: 'state', actor: SYS, summary_fa: 'تمام شد', data: { state: 'done' } },
    ],
  });
}

/** FX's CTO wanted an old backtest table gone; the gateway held it (db_drop): the activity row, the card and the stream's event. */
function raiseSeal() {
  if (sealRaised || !ctx) return;
  sealRaised = true;
  const cmd = 'docker compose exec -T timescaledb psql -U forex -d coinepro -c "DROP TABLE signals_backtest_2025;"';
  activity['srv-fx-1']!.unshift(call('srv-fx-1', 'FX-TECH-MGR', 'مدیر فنی FX', 'server.exec', 'DROP TABLE نگه داشته شد؛ منتظر مُهر مدیر کل', cmd, null, null, 0, { state: 'awaiting_seal', kind: 'manager' }));
  addCard({
    ref: 'D-000201', company: 'FX', title: 'پاک کردن جدول بک‌تست پارسال روی fx-main',
    what: 'اجرای `DROP TABLE signals_backtest_2025;` روی دیتابیس TimescaleDB سرور fx-main.',
    why: 'جدول بک‌تست سال قبل ۱۸ گیگابایت جا گرفته و دیگر خوانده نمیشود؛ نتیجه‌هایش در گزارش O-000038 بایگانی شده است.',
    risk_note: 'برگشت‌ناپذیر است؛ آخرین پشتیبان این جدول مال دیشب ساعت ۲:۳۰ است.', proposer: actor('FX-TECH-MGR', 'مدیر فنی FX', 'manager'),
    payload: { server: { id: 'srv-fx-1', name: 'fx-main' }, server_name: 'fx-main', company: 'FX', category: 'db_drop', tool: 'server.exec', cmd, cwd: '/home/forex/CoinePro-FX', detected_by: 'pattern', pattern: 'DROP TABLE', session_ref: null, actor: actor('FX-TECH-MGR', 'مدیر فنی FX', 'manager') },
  });
  event('FX', 'server.awaiting_seal', 'srv-fx-1', { decision_ref: 'D-000201', server: 'srv-fx-1', category: 'db_drop' });
}

function addCard(c: { ref: string; company: string; title: string; what: string; why: string; risk_note?: string | null; proposer: any; payload: Record<string, unknown> }) {
  ctx!.decisions.unshift({
    id: `d-${c.ref}`, kind: 'server_destructive', action_class: 'A3', risk: 'high', reversible: false, status: 'pending', created_at: nowIso(), expires_at: isoAt(60 * 24),
    quota_estimate: { tokens: 0, usd: '0' }, risk_note: null, seal: null, decided_at: null, decided_by: null, note: null, resolution: null, thread: null, version: 1,
    effect_status: 'none', work_id: null, reason_code: null, memos: [], reminders: [], waiting_h: 0, ...c,
  });
}

/** Time moves the world: the card a few seconds after waking, a paired runner taking its token, the agents' calls one by one. */
function tick() {
  if (!awake) return;
  if (!sealRaised && Date.now() - wokeAt > 8_000) raiseSeal();
  advanceNet();
  if (Date.now() - lastBeat < 30_000) return;
  lastBeat = Date.now();
  const b = BEATS[beat++ % BEATS.length]!;
  if (locked(b.company)) return;
  activity[b.server]?.unshift(call(b.server, b.actor, b.actorFa, b.tool, b.summary, b.cmd, 0, b.ms, 0));
  edit(b.server, { last_seen_at: nowIso() });
  event(b.company, 'server.call', b.server, { server: b.server, company: b.company, actor: b.actor, actor_fa: b.actorFa, tool: b.tool, summary_fa: b.summary, cmd_masked: b.cmd, exit_code: 0, duration_ms: b.ms, state: 'done' });
}

const BEATS = [
  { company: 'FX', server: 'srv-fx-1', actor: 'FX-TECH-MGR', actorFa: 'مدیر فنی FX', tool: 'server.exec', summary: 'سلامت API بعد از انتشار: 200', cmd: 'curl -fsS http://127.0.0.1:8000/health', ms: 120 },
  { company: 'TY', server: 'srv-ty-1', actor: 'TY-GROWTH-01', actorFa: 'تحلیلگر سئوی فنی', tool: 'server.read', summary: 'خواندن sitemap تولیدشده', cmd: 'cat /var/www/tradeyar/sitemap.xml', ms: 60 },
  { company: 'FX', server: 'srv-fx-1', actor: 'FX-QUANT-02', actorFa: 'پایشگر سیگنال', tool: 'server.exec', summary: 'صف celery خالی است', cmd: 'docker compose exec -T api celery -A src inspect active', ms: 2_100 },
  { company: 'TY', server: 'srv-ty-1', actor: 'TY-TECH-MGR', actorFa: 'مدیر فنی تریدیار', tool: 'server.exec', summary: 'لاگ خطای nginx در یک ساعت گذشته خالی است', cmd: 'sudo tail -n 100 /var/log/nginx/error.log', ms: 80 },
];

/** What the stream carries since the last look (`servers` topic): the mock stream asks every couple of seconds. */
export function drainServerEvents(): DemoEvent[] {
  tick();
  return queue.splice(0);
}

// ------------------------------------------------------------------ exec --
const DESTRUCTIVE: Array<[RegExp, string]> = [
  [/drop\s+(table|database|schema)|truncate\s/i, 'db_drop'],
  [/docker\s+volume\s+rm|compose\s+down\s+.*-v\b/i, 'volume_delete'],
  [/rm\s+-[a-z]*r[a-z]*f?.*backup|restic\s+forget/i, 'backup_delete'],
  [/\b(mkfs|fdisk|parted|wipefs)\b/, 'disk_wipe'],
  [/\b(userdel|passwd|ufw|iptables)\b|sshd_config|authorized_keys/, 'access_change'],
];

/** What the demo server prints for a command: (stderr?, line) and the exit code. */
function output(cmd: string, s: any): [Array<[boolean, string]>, number] {
  const out = (...l: string[]): Array<[boolean, string]> => l.map((x) => [false, x]);
  const first = cmd.replace(/^sudo /, '').trim().split(/\s+/)[0] ?? '';
  const branch = s.name === 'fx-main' ? 'claude/wizardly-edison-zyWyW' : 'main';
  if (cmd.startsWith('docker ps')) {
    const m = maps[s.id];
    const rows: any[] = (m?.map ?? m)?.containers ?? [];
    return [[...out('CONTAINER ID   IMAGE                                STATUS                    NAMES'), ...rows.map((c, i): [boolean, string] => {
      const status = c.status ?? (c.state === 'running' ? `Up 3 minutes${c.health ? ` (${c.health})` : ''}` : 'Exited (0) 6 hours ago');
      return [false, `${(0x3fa91c2b7d00 + i * 7919).toString(16).padStart(12, '0').padEnd(14)} ${String(c.image ?? '').padEnd(36)} ${status.padEnd(25)} ${c.name ?? c.names}`];
    })], 0];
  }
  if (cmd.startsWith('df')) return [out('Filesystem      Size  Used Avail Use% Mounted on', '/dev/sda1       150G   62G   82G  43% /', 'tmpfs           7.8G     0  7.8G   0% /dev/shm', '/dev/sda15      253M  6.1M  246M   3% /boot/efi'), 0];
  if (cmd.startsWith('free')) return [out('               total        used        free      shared  buff/cache   available', 'Mem:            15Gi        11Gi       1.2Gi       214Mi       3.1Gi       4.0Gi', 'Swap:          8.0Gi       1.1Gi       6.9Gi'), 0];
  if (cmd.startsWith('uptime')) return [out(' 08:30:12 up 22 days,  3:41,  1 user,  load average: 0.84, 0.92, 0.88'), 0];
  if (cmd === 'whoami') return [out(s.user), 0];
  if (cmd === 'hostname') return [out(s.name), 0];
  if (cmd.includes('list-timers')) return [out(
    'NEXT                         LEFT        LAST                         PASSED  UNIT                     ACTIVATES',
    'Sat 2026-10-17 10:05:00 UTC  1h 35min    Fri 2026-10-16 10:05:00 UTC  22h ago fx-backup.timer          fx-backup.service',
    'Sat 2026-10-17 12:00:00 UTC  3h 30min    Sat 2026-10-17 00:00:00 UTC  8h ago  certbot.timer            certbot.service',
    'Sun 2026-10-18 06:12:00 UTC  21h         Sat 2026-10-17 06:09:41 UTC  2h ago  apt-daily-upgrade.timer  apt-daily-upgrade.service', '', '3 timers listed.'), 0];
  if (cmd.startsWith('git') && cmd.includes('status')) return [out(`On branch ${branch}`, `Your branch is up to date with 'origin/${branch}'.`, '', 'nothing to commit, working tree clean'), 0];
  if (cmd.startsWith('git') && cmd.includes('log')) return [out('a41c09e signals: calibrate LightGBM on the last 90 days', '7d20f13 api: index users.email (W-000106)', 'c9b81aa risk: weekend filter for crypto pairs'), 0];
  if (cmd.startsWith('tail')) return [out(
    `Oct 17 08:29:58 ${s.name} dockerd[812]: time="2026-10-17T08:29:58Z" level=info msg="Container api healthy"`,
    `Oct 17 08:30:01 ${s.name} CRON[44121]: (${s.user}) CMD (/home/${s.user}/scripts/healthcheck.sh)`,
    `Oct 17 08:30:02 ${s.name} systemd[1]: Started fx-healthcheck.service.`), 0];
  if (cmd.startsWith('ls')) return [out('CoinePro-FX  backups  logs  scripts'), 0];
  if (cmd.startsWith('echo ')) return [out(cmd.slice(5).trim().replace(/^["']|["']$/g, '')), 0];
  if (cmd.startsWith('docker compose logs')) return [[...out('api-1  | INFO:     Application startup complete.', 'api-1  | INFO:     10.10.1.4:51022 - "GET /health HTTP/1.1" 200 OK'), [true, 'api-1  | WARNING:  model drift above 0.12 on EURUSD (daily)']], 0];
  if (['cat', 'grep', 'systemctl', 'docker', 'git', 'curl', 'python', 'pytest', 'make', 'bash', 'sh', 'journalctl', 'nginx', 'ps', 'top', 'htop', 'du'].includes(first)) return [out(`(demo) ran on ${s.name} as ${s.user}; a real server prints its own output here.`), 0];
  return [[[true, `bash: ${first}: command not found`]], 127];
}

async function exec(req: Request, s: any): Promise<Response> {
  if (!req.headers.get('X-Step-Up')) return problem(403, 'step_up_required', 'این کار تأیید با گذرکلید لازم دارد.');
  if (locked(s.company)) return problem(423, 'company_locked', 'کلید توقف این شرکت زده شده؛ هر کاری روی سرورهایش ایستاده است.');
  if (s.state !== 'online') return problem(409, 'server_offline', 'runner این سرور الان آفلاین است.');
  const body = (await req.json().catch(() => ({}))) as { cmd?: string; sudo?: boolean };
  const cmd = (body.cmd ?? '').trim();
  const cat = DESTRUCTIVE.find(([re]) => re.test(cmd))?.[1];
  if (cat && policy.includes(cat)) {
    const ref = `D-${String(nextCard++).padStart(6, '0')}`;
    addCard({
      ref, company: s.company, title: `فرمان ویرانگر تو روی ${s.name}`, what: 'اجرای فرمانی که در ترمینال نوشتی.', why: 'دروازه آن را ویرانگر شناخت؛ قوانین سرورها میگوید منتظر مُهر بماند.', proposer: OWNER,
      payload: { server: { id: s.id, name: s.name }, server_name: s.name, company: s.company, category: cat, tool: 'server.exec', cmd, detected_by: 'pattern', actor: OWNER },
    });
    activity[s.id] = [call(s.id, 'owner', 'مدیر کل', 'server.exec', 'فرمان ویرانگر نگه داشته شد؛ منتظر مُهر', cmd, null, null, 0, { state: 'awaiting_seal' }), ...(activity[s.id] ?? [])];
    event(s.company, 'server.awaiting_seal', s.id, { decision_ref: ref, server: s.id, category: cat });
    return json({ status: 'awaiting_seal', decision_ref: ref, message_fa: `این فرمان ویرانگر است؛ کارت ${ref} در کارتابل منتظر مُهر توست.` }, 202);
  }
  const [lines, exit] = output(cmd, s);
  const ms = 180 + lines.length * 40;
  activity[s.id] = [call(s.id, 'owner', 'مدیر کل', 'server.exec', 'فرمان تو از ترمینال پنل', cmd, exit, ms, 0), ...(activity[s.id] ?? [])];
  event(s.company, 'server.call', s.id, { server: s.id, company: s.company, actor: 'owner', tool: 'server.exec', summary_fa: 'فرمان تو از ترمینال پنل', cmd_masked: cmd, exit_code: exit, duration_ms: ms, state: exit === 0 ? 'done' : 'failed' });
  const chunks = [...lines.map(([err, text]) => `event: ${err ? 'stderr' : 'stdout'}\ndata: ${JSON.stringify({ text: `${text}\n` })}\n\n`), `event: exit\ndata: ${JSON.stringify({ code: exit, exit_code: exit, duration_ms: ms })}\n\n`];
  // Streamed a few lines at a time, as a real command's output arrives.
  const enc = new TextEncoder();
  let i = 0;
  const stream = new ReadableStream<Uint8Array>({
    async pull(c) {
      if (i >= chunks.length) { c.close(); return; }
      await new Promise((r) => setTimeout(r, 60));
      c.enqueue(enc.encode(chunks[i++]!));
    },
  });
  return new Response(stream, { status: 200, headers: { 'content-type': 'text/event-stream' } });
}

// ------------------------------------------------------------------ network (§26.6) --
type NetRunner = { id: string; company: string; name: string; ip: string | null; via: 'private' | 'public'; rtt: number };
const NET: NetRunner[] = [
  { id: 'srv-fx-1', company: 'FX', name: 'fx-main', ip: '10.10.1.2', via: 'private', rtt: 3.0 },
  { id: 'srv-ty-1', company: 'TY', name: 'ty-web', ip: '10.10.1.3', via: 'private', rtt: 2.0 },
  { id: 'srv-pc-1', company: 'PC', name: 'pc-app', ip: '10.10.1.1', via: 'private', rtt: 2.4 },
  { id: 'srv-ig-1', company: 'IG', name: 'IG-Hub', ip: null, via: 'public', rtt: 41.0 },
];
const netAt = new Map<string, number>();
const roundOf = new Map<string, number>();
let netRound = 0;
let checkFrom: number | null = null;
const answered = new Set<string>();

function startCheck() {
  advanceNet();
  if (checkFrom != null) return;
  checkFrom = Date.now();
  netRound++;
  answered.clear();
}
/** The runners whose turn has come answer: a new check of their roads, stamped later than anything before it. */
function advanceNet() {
  if (checkFrom == null) return;
  const waited = Date.now() - checkFrom;
  NET.forEach((r, i) => {
    if (answered.has(r.id) || waited < 1_800 + i * 2_200) return;
    answered.add(r.id);
    const last = Math.max(0, ...netAt.values());
    netAt.set(r.id, Math.max(Date.now(), last + 1000));
    roundOf.set(r.id, netRound);
    event(r.company, 'server.state', r.id, { server: r.id, state: 'online', via: r.via, hub_rtt_ms: rtt(r) });
  });
  if (answered.size === NET.length) checkFrom = null;
}
/** A round trip that moves a little from one check to the next. */
const rtt = (r: NetRunner) => Math.round((r.rtt + [0, 0.3, -0.2, 0.5][(roundOf.get(r.id) ?? 0) % 4]! * (r.via === 'public' ? 6 : 1)) * 10) / 10;
const link = (from: string, to: string, port: number, ok: boolean, ms: number | null, error: string | null, at: string) => ({ from, to, port, ok, ms: ms == null ? null : Math.round(ms * 10) / 10, error, at });

function networkJson() {
  advanceNet();
  const first = Date.now() - 2 * 3_600_000;
  const links: any[] = [];
  for (const r of NET) {
    const at = new Date(netAt.get(r.id) ?? first).toISOString();
    links.push(link(r.id, 'hub', 443, true, rtt(r) + 0.6, null, at));
    for (const t of NET) {
      if (t.id === r.id || !t.ip) continue;
      for (const port of [22, 80, 443]) {
        // Outside the private network, the others' private addresses do not answer at all.
        if (!r.ip) links.push(link(r.id, t.id, port, false, null, 'timeout', at));
        else if (r.id === 'srv-pc-1' && t.id === 'srv-fx-1' && port === 22) links.push(link(r.id, t.id, port, false, null, 'connection refused', at));
        else links.push(link(r.id, t.id, port, true, 0.4 + ((r.id.length * 7 + t.id.length * 3 + port + (roundOf.get(r.id) ?? 0)) % 6) / 10, null, at));
      }
    }
  }
  return {
    at: nowIso(),
    nodes: [
      { id: 'hub', company: 'HQ', name: 'hub', private_ip: '10.10.1.4', via: null, state: 'online', hub_rtt_ms: null },
      ...NET.map((r) => ({ id: r.id, company: r.company, name: r.name, private_ip: r.ip, via: r.via, state: 'online', hub_rtt_ms: rtt(r) })),
    ],
    links,
  };
}

// ------------------------------------------------------------------ sessions --
function newSession(b: any) {
  const c = ctx!;
  const s = servers.find((x) => x.id === b.server);
  const ref = `S-${String(20 + c.sessions.filter((x) => x.runtime === 'company_server').length).padStart(4, '0')}`;
  const e = c.employees.find((x) => x.code === b.driver);
  const driver = e ? actor(e.code, `${e.title_fa} ${s?.company ?? ''}`.trim(), e.kind) : OWNER;
  const x: any = {
    id: `s-${ref}`, ref, workspace: '', grant: '', runtime: 'company_server', server: b.server, company: s?.company ?? b.company, title: b.title, brief: b.brief, opened_by: OWNER, driver,
    model: 'claude-sonnet-5-5', effort: 'high', state: 'starting', branch: null, pr_url: null, usage: { usd: 0, input_tokens: 0, output_tokens: 0 }, created_at: nowIso(), updated_at: nowIso(), events: [],
    script: [
      { type: 'state', actor: SYS, summary_fa: `Claude Code روی ${s?.name ?? 'سرور'} شروع شد${b.cwd ? `؛ در ${b.cwd}` : ''}`, data: { state: 'working' } },
      { type: 'message', actor: driver, summary_fa: `شروع کردم: ${b.title}. اول وضعیت ریپو و سرویس‌ها را میبینم.`, data: {} },
      { type: 'command', actor: driver, summary_fa: 'ریپو تمیز است و روی آخرین commit', data: { cmd: 'git status -sb && git log --oneline -3', exit_code: 0, duration_s: 1 } },
      { type: 'command', actor: driver, summary_fa: 'همه‌ی سرویس‌ها بالا هستند', data: { cmd: 'docker compose ps', exit_code: 0, duration_s: 2 } },
      { type: 'progress', actor: driver, summary_fa: 'جای تغییر پیدا شد؛ در حال نوشتن و تست.', data: {} },
    ],
  };
  c.sessions.unshift(x);
  activity[b.server] = [call(b.server, driver.code, driver.display_fa, 'server.claude', `Claude Code روی سرور: ${b.title}`, null, null, null, 0, { session: ref, kind: driver.kind, cwd: b.cwd }), ...(activity[b.server] ?? [])];
  return c.sessionOut(x);
}

// ------------------------------------------------------------------ HTTP --
export async function handle26(req: Request, p: string, u: URL, c: Ctx): Promise<Response | null> {
  ctx = c;
  const m = req.method;
  const stepUp = req.headers.get('X-Step-Up');
  tick();
  if (p === '/control/server-policy') {
    if (m === 'GET') return json({ seal_required: policy });
    if (m === 'PUT') {
      if (!stepUp) return problem(403, 'step_up_required', 'این کار تأیید با گذرکلید لازم دارد.');
      const b = (await req.json().catch(() => ({}))) as { seal_required?: string[] };
      policy = (b.seal_required ?? []).filter((k) => typeof k === 'string');
      return json({ seal_required: policy });
    }
  }
  if (p === '/workshop/sessions' && m === 'POST') {
    const b = (await req.clone().json().catch(() => ({}))) as any;
    if (b.runtime !== 'company_server') return null;
    const s = servers.find((x) => x.id === b.server);
    if (!s) return problem(404, 'not_found', 'این سرور پیدا نشد.');
    if (locked(s.company)) return problem(423, 'company_locked', 'کلید توقف این شرکت زده شده.');
    if (s.state !== 'online') return problem(409, 'server_offline', 'runner این سرور الان آفلاین است.');
    return json(newSession(b), 201);
  }
  // A server_destructive card: sealed with 🔏 server.destructive; sealing runs the command, a no drops it (the generic demo decides the card).
  const dm = /^\/decisions\/(D-\d+)\/(approve|reject)$/.exec(p);
  if (dm && m === 'POST') {
    const d = c.decisions.find((x) => x.ref === dm[1] && x.kind === 'server_destructive');
    if (!d) return null;
    if (dm[2] === 'approve' && !stepUp) return problem(403, 'step_up_required', 'این کار تأیید با گذرکلید لازم دارد.');
    const sid = d.payload?.server?.id as string | undefined;
    const rows = sid ? activity[sid] : undefined;
    if (rows) {
      const i = rows.findIndex((r) => r.state === 'awaiting_seal' && r.cmd_masked === d.payload.cmd);
      if (i >= 0) rows.splice(i, 1);
      if (dm[2] === 'approve') {
        const who = d.payload.actor ?? OWNER;
        rows.unshift(call(sid!, who.code, who.display_fa, 'server.exec', d.ref === 'D-000201' ? 'با مُهر مدیر کل: جدول پاک شد، ۱۸ گیگابایت آزاد شد' : 'با مُهر مدیر کل اجرا شد', d.payload.cmd, 0, 1_240, 0, { kind: who.kind }));
      }
    }
    return null;
  }
  const tr = /^\/infra\/servers\/([^/]+)\/jobs\/([^/]+)\/transcript$/.exec(p);
  if (tr) {
    const r = Object.values(activity).flat().find((x) => x.id === tr[2]);
    if (!r) return problem(404, 'not_found', 'این متن پیدا نشد.');
    const body = `$ ${r.cmd_masked ?? ''}\n${String(r.cmd_masked ?? '').includes('pytest') ? '........................................................ [ 61%]\n...................................                      [100%]\n91 passed in 48.71s\n' : `(exit ${r.exit_code ?? '—'})\n`}`;
    return new Response(body, { status: 200, headers: { 'content-type': 'text/plain; charset=utf-8' } });
  }
  // §26.6: the network map is its own small world (it does not wake the servers' pages).
  if (p === '/infra/network' && m === 'GET') return json(networkJson());
  if (p === '/infra/network/check' && m === 'POST') { startCheck(); return json({ queued: NET.length, jobs: NET.map((r) => `job-net-${r.id}`) }, 202); }
  if (p === '/runners/approve' && m === 'POST') {
    wake();
    if (!stepUp) return problem(403, 'step_up_required', 'این کار تأیید با گذرکلید لازم دارد.');
    const b = (await req.json().catch(() => ({}))) as { user_code?: string };
    const code = b.user_code ?? '';
    if (!/^[A-Z0-9]{4}-[A-Z0-9]{4}$/.test(code)) return problem(422, 'validation_failed', 'کد باید به شکل ABCD-1234 باشد.');
    if (code.endsWith('0000')) return problem(410, 'expired_token', 'این کد منقضی شده است.');
    if (code.startsWith('ZZZZ')) return problem(404, 'invalid_user_code', 'این کد پیدا نشد.');
    // The demo's step-up token names no target, so any other well-formed code is TradeYar's media server.
    const [company, base] = PAIRS[code] ?? ['TY', 'ty-media'];
    let n = 1;
    const nameOf = (i: number) => (i === 1 ? base : `${base}-${i}`);
    while (servers.some((x) => x.company === company && x.name === nameOf(n))) n++;
    const id = `srv-${company.toLowerCase()}-${servers.length + 1}`;
    const s = server(id, company, nameOf(n), `10.10.1.${20 + servers.length}`, 'deploy', `${nameOf(n)}.internal`, 'pending', null, null);
    servers.push(s);
    attaching.set(id, 0);
    return json({ server: s });
  }
  if (!p.startsWith('/infra/servers')) return null;
  wake();
  if (p === '/infra/servers' && m === 'GET') {
    // A paired runner takes its token after a few looks (its next poll) and turns online; its first map follows.
    for (const [id, n] of attaching) {
      if (n >= 2) { attaching.delete(id); edit(id, { state: 'online', via: 'private', hub_rtt_ms: 2.8, last_seen_at: nowIso(), map_at: nowIso() }); maps[id] = smallMap(nowIso()); event(servers.find((x) => x.id === id)?.company ?? null, 'server.state', id, { server: id, state: 'online' }); }
      else attaching.set(id, n + 1);
    }
    return json({ items: servers, inventory: { fetched_at: null, servers: [] } });
  }
  const x = /^\/infra\/servers\/([^/]+)(?:\/(map|activity|exec))?$/.exec(p);
  if (!x) return null;
  const s = servers.find((y) => y.id === x[1]);
  if (!s) return problem(404, 'not_found', 'این سرور پیدا نشد.');
  switch (x[2]) {
    case 'map':
      if (m === 'GET') return maps[s.id] ? json(maps[s.id]) : problem(404, 'not_found', 'هنوز نقشه‌ای گرفته نشده.');
      if (locked(s.company)) return problem(423, 'company_locked', 'کلید توقف این شرکت زده شده.');
      if (s.state !== 'online') return problem(409, 'server_offline', 'runner این سرور الان آفلاین است.');
      {
        const m0 = maps[s.id] ?? smallMap(nowIso());
        maps[s.id] = { ...m0, ...(m0.map ? { at: nowIso() } : { taken_at: nowIso() }) };
        edit(s.id, { map_at: nowIso() });
        activity[s.id] = [call(s.id, 'owner', 'مدیر کل', 'server.map', 'نقشه‌ی تازه به خواست تو', null, 0, 3_400, 0), ...(activity[s.id] ?? [])];
        return json(maps[s.id]);
      }
    case 'activity': {
      const who = u.searchParams.get('actor');
      const rows = (activity[s.id] ?? []).filter((r) => !who || r.actor?.code === who);
      return json(page(rows.slice(0, Number(u.searchParams.get('limit') ?? 50))));
    }
    case 'exec':
      return exec(req, s);
    default:
      if (m !== 'DELETE') return null;
      if (!stepUp) return problem(403, 'step_up_required', 'این کار تأیید با گذرکلید لازم دارد.');
      // The runner's token is revoked at once; the server stays listed, revoked, with its history.
      edit(s.id, { state: 'revoked', via: null, hub_rtt_ms: null });
      for (const r of activity[s.id] ?? []) if (r.state === 'queued' || r.state === 'running') r.state = 'cancelled';
      event(s.company, 'server.state', s.id, { server: s.id, state: 'revoked' });
      return json(s);
  }
}
