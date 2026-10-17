// Digital Asset Links for the Android app (served at /.well-known/assetlinks.json through a rewrite).
// Credential Manager lets the app use the hub's passkeys only when this file lists the app's package and
// signing-certificate fingerprint. Defaults: the owner's signing key (created 2026-10-17; the fingerprint is
// public) for the app and its debug build. HQ_ANDROID_PACKAGES and HQ_ANDROID_CERT_SHA256 override them.

export const dynamic = 'force-dynamic';

const FINGERPRINT = /^([0-9A-F]{2}:){31}[0-9A-F]{2}$/;
const PACKAGE = /^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$/;

const OWNER_CERT = 'D6:D4:15:6F:7F:0E:AE:95:4A:F4:14:BA:A8:8B:6A:E8:C6:84:27:03:5F:62:71:B4:C5:ED:97:0F:39:2A:15:BF';
const PACKAGES = 'com.coinepro.hq,com.coinepro.hq.debug';

const list = (v: string | undefined) => (v ?? '').split(',').map((s) => s.trim()).filter(Boolean);

export function GET(): Response {
  const packages = list(process.env.HQ_ANDROID_PACKAGES || PACKAGES).filter((p) => PACKAGE.test(p));
  const certs = list(process.env.HQ_ANDROID_CERT_SHA256 || OWNER_CERT).map((c) => c.toUpperCase()).filter((c) => FINGERPRINT.test(c));
  const statements = certs.length
    ? packages.map((p) => ({
        relation: ['delegate_permission/common.handle_all_urls', 'delegate_permission/common.get_login_creds'],
        target: { namespace: 'android_app', package_name: p, sha256_cert_fingerprints: certs },
      }))
    : [];
  return Response.json(statements, { headers: { 'Cache-Control': 'public, max-age=300' } });
}
