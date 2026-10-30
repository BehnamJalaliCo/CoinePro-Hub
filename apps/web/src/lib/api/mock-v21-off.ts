// Production stand-in for the 0.3.0–0.6.0 demo fixtures (./mock-v21): next.config aliases the module here outside mock mode.
export async function handle(): Promise<Response> {
  throw new Error('mock mode is not part of this build');
}
export function tick21(): never[] { return []; }
export function simulateRestart(): void {}
