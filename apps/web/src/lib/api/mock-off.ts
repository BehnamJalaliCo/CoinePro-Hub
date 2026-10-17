// Production stand-in for the development fixtures (next.config aliases ./mock here unless NEXT_PUBLIC_HQ_MOCK=1).
export async function handle(): Promise<Response> {
  throw new Error('mock mode is not part of this build');
}
export function register(): void {}
