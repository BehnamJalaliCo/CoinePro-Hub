// Whether the hub is answering (0.4.0; the Android app's core/net/HubHealth.kt). A restart during a deploy looks like this from the browser:
// every call answers 502 (Caddy has nobody behind it), 503 or 504, or gets no answer, for a few seconds. One such failure of a read is
// retried quietly; four of them within fifteen seconds mean the hub itself is away: the panel then shows one calm banner instead of an
// error on every card, pages keep what they had (or their skeletons), the panel probes with a growing pause, and the first answer brings
// everything back.

export type HubState = 'ok' | 'restarting';
export const WINDOW_MS = 15_000;
export const THRESHOLD = 4;
/** The pause before each probe (and each quiet retry) while the hub is away. */
export const BACKOFF_MS = [2_000, 3_000, 5_000, 8_000, 13_000, 20_000];
export const backoff = (attempt: number) => BACKOFF_MS[Math.min(Math.max(attempt, 0), BACKOFF_MS.length - 1)]!;

/** A 502, 503 or 504, or no answer at all. */
export const isTransientStatus = (status: number) => status === 0 || (status >= 502 && status <= 504);

class HubHealth {
  private recent: number[] = [];
  private since = 0;
  private listeners = new Set<() => void>();
  private recovered = new Set<(awayMs: number) => void>();
  state: HubState = 'ok';

  get outage() { return this.state === 'restarting'; }
  subscribe = (l: () => void) => { this.listeners.add(l); return () => { this.listeners.delete(l); }; };
  get = () => this.state;
  /** The hub answers again; with how long it was away. */
  onRecovered(l: (awayMs: number) => void) { this.recovered.add(l); return () => { this.recovered.delete(l); }; }

  transient(now = Date.now()) {
    this.recent.push(now);
    this.recent = this.recent.filter((t) => now - t <= WINDOW_MS);
    if (this.state === 'ok' && this.recent.length >= THRESHOLD) {
      this.since = this.recent[0]!;
      this.set('restarting');
    }
  }

  /** Any other answer: the hub is there. */
  ok(now = Date.now()) {
    this.recent = [];
    if (this.state === 'restarting') {
      this.set('ok');
      for (const l of this.recovered) l(now - this.since);
    }
  }

  private set(s: HubState) {
    this.state = s;
    for (const l of this.listeners) l();
  }
}

export const hubHealth = new HubHealth();
