'use client';

import { startAuthentication, startRegistration, browserSupportsWebAuthn } from '@simplewebauthn/browser';
import { api, ok, isMock, ApiError } from './api/client';

type Json = Record<string, unknown>;

/** A short, human device name for the device list ("Chrome · Android"). */
export function deviceName(): string {
  if (typeof navigator === 'undefined') return 'دستگاه';
  const ua = navigator.userAgent;
  const os = /Android/i.test(ua) ? 'Android' : /iPhone|iPad/i.test(ua) ? 'iOS' : /Mac OS X/i.test(ua) ? 'macOS' : /Windows/i.test(ua) ? 'Windows' : /Linux/i.test(ua) ? 'Linux' : 'Other';
  const br = /Edg\//.test(ua) ? 'Edge' : /Firefox\//.test(ua) ? 'Firefox' : /Chrome\//.test(ua) ? 'Chrome' : /Safari\//.test(ua) ? 'Safari' : 'Browser';
  return `${br} · ${os}`;
}

export function passkeysSupported(): boolean {
  return isMock || browserSupportsWebAuthn();
}

function ceremonyError(e: unknown): never {
  if (e instanceof ApiError) throw e;
  const name = (e as { name?: string })?.name;
  const fa =
    name === 'NotAllowedError' ? 'تأیید با اثر انگشت یا چهره لغو شد یا زمانش گذشت.'
    : name === 'InvalidStateError' ? 'این دستگاه قبلاً ثبت شده است.'
    : name === 'SecurityError' ? 'این صفحه باید روی دامنه‌ی اصلی و با HTTPS باز شود.'
    : 'تأیید هویت انجام نشد؛ دوباره تلاش کن.';
  throw new ApiError(400, { code: 'passkey_ceremony_failed', message_fa: fa, title: name ?? 'passkey' });
}

/** Sign in with a discoverable passkey (contract §2). */
export async function signIn(): Promise<void> {
  const options = await ok(api.POST('/api/v1/auth/passkey/login/options', {}));
  let credential: Json;
  try {
    credential = isMock ? {} : ((await startAuthentication({ optionsJSON: options as never })) as unknown as Json);
  } catch (e) {
    ceremonyError(e);
  }
  await ok(api.POST('/api/v1/auth/passkey/login/verify', { body: { credential: credential as never, device_name: deviceName() } }));
}

/** First enrolment (one-time link from `make owner-enroll`) or adding a device (with step-up). */
export async function enrol(opts: { enrolmentToken?: string; name: string; stepUpToken?: string }): Promise<void> {
  const options = await ok(
    api.POST('/api/v1/auth/passkey/register/options', {
      body: { enrolment_token: opts.enrolmentToken ?? null },
      headers: opts.stepUpToken ? { 'X-Step-Up': opts.stepUpToken } : undefined,
    }),
  );
  let credential: Json;
  try {
    credential = isMock ? {} : ((await startRegistration({ optionsJSON: options as never })) as unknown as Json);
  } catch (e) {
    ceremonyError(e);
  }
  await ok(api.POST('/api/v1/auth/passkey/register/verify', { body: { credential: credential as never, device_name: opts.name } }));
}

/** Step-up: a fresh passkey assertion bound to one action and target (single use, 120 s). */
export async function stepUp(action: string, target: string): Promise<string> {
  const options = await ok(api.POST('/api/v1/auth/step-up/options', { body: { action, target } }));
  let credential: Json;
  try {
    credential = isMock ? {} : ((await startAuthentication({ optionsJSON: options as never })) as unknown as Json);
  } catch (e) {
    ceremonyError(e);
  }
  const out = await ok(api.POST('/api/v1/auth/step-up/verify', { body: { credential: credential as never } }));
  return out.step_up_token;
}

/** SHA-256 hex of the exact request body, for step-ups bound to a body (assignments, budgets). */
export async function bodyTarget(body: string): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(body));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

export async function signOut(): Promise<void> {
  await ok(api.POST('/api/v1/auth/logout', {}));
}
