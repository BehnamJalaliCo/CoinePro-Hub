// Digital Asset Links for the Android app (served at /.well-known/assetlinks.json through a rewrite).
// Credential Manager lets the app use the hub's passkeys only when this file lists the app's package and
// signing-certificate fingerprint. Both come from the web service's environment, which the owner sets once the
// signing key exists (apps/android/README.md): HQ_ANDROID_PACKAGES and HQ_ANDROID_CERT_SHA256.

export const dynamic = 'force-dynamic';

const FINGERPRINT = /^([0-9A-F]{2}:){31}[0-9A-F]{2}$/;
const PACKAGE = /^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$/;

const list = (v: string | undefined) => (v ?? '').split(',').map((s) => s.trim()).filter(Boolean);

export function GET(): Response {
  const packages = list(process.env.HQ_ANDROID_PACKAGES ?? 'com.coinepro.hq').filter((p) => PACKAGE.test(p));
  const certs = list(process.env.HQ_ANDROID_CERT_SHA256).map((c) => c.toUpperCase()).filter((c) => FINGERPRINT.test(c));
  const statements = certs.length
    ? packages.map((p) => ({
        relation: ['delegate_permission/common.handle_all_urls', 'delegate_permission/common.get_login_creds'],
        target: { namespace: 'android_app', package_name: p, sha256_cert_fingerprints: certs },
      }))
    : [];
  return Response.json(statements, { headers: { 'Cache-Control': 'public, max-age=300' } });
}
