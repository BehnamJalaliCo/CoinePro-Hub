import { NextResponse, type NextRequest } from 'next/server';

// Per-request nonce and a strict Content-Security-Policy for every page.
// Caddy adds HSTS, nosniff, Referrer-Policy, COOP and CORP for the whole site;
// the CSP of the web pages is ours (contract §1, prompt 5 §10).
export function proxy(request: NextRequest) {
  const nonce = Buffer.from(crypto.randomUUID()).toString('base64');
  const dev = process.env.NODE_ENV === 'development';
  const csp = [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${dev ? " 'unsafe-eval'" : ''}`,
    // Development injects <style> tags for hot reload; production ships CSS files only.
    dev ? "style-src-elem 'self' 'unsafe-inline'" : `style-src-elem 'self' 'nonce-${nonce}'`,
    // React renders `style` attributes; attributes cannot run code.
    "style-src-attr 'unsafe-inline'",
    "img-src 'self' blob: data:",
    // Owner attachments: videos and voice notes play from the API, or from a local preview before upload.
    "media-src 'self' blob: data:",
    "font-src 'self'",
    "connect-src 'self'",
    "manifest-src 'self'",
    "worker-src 'self'",
    "object-src 'none'",
    "base-uri 'none'",
    "form-action 'self'",
    "frame-ancestors 'none'",
    ...(dev ? [] : ['upgrade-insecure-requests']),
  ].join('; ');

  const headers = new Headers(request.headers);
  headers.set('x-nonce', nonce);
  headers.set('Content-Security-Policy', csp);
  const response = NextResponse.next({ request: { headers } });
  response.headers.set('Content-Security-Policy', csp);
  response.headers.set('Permissions-Policy', 'camera=(), geolocation=(), microphone=(self), payment=(), usb=()');
  response.headers.set('X-Frame-Options', 'DENY');
  return response;
}

export const config = {
  matcher: [
    {
      source: '/((?!_next/static|_next/image|fonts|favicon.ico|icon.svg|healthz).*)',
      missing: [
        { type: 'header', key: 'next-router-prefetch' },
        { type: 'header', key: 'purpose', value: 'prefetch' },
      ],
    },
  ],
};
