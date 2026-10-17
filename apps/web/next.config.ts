import type { NextConfig } from 'next';

const mock = process.env.NEXT_PUBLIC_HQ_MOCK === '1';

const config: NextConfig = {
  output: 'standalone',
  poweredByHeader: false,
  reactStrictMode: true,
  productionBrowserSourceMaps: false,
  images: { unoptimized: true },
  // Development fixtures never ship: outside mock mode the module resolves to an empty stand-in.
  turbopack: mock ? {} : { resolveAlias: { '@/lib/api/mock': './src/lib/api/mock-off.ts' } },
  // Project rules live in the repository's CLAUDE.md; Next must not write its own agent files here.
  agentRules: false,
  // Android passkeys: the asset-links file lives at a dotted path, served by an ordinary route handler.
  async rewrites() {
    return [{ source: '/.well-known/assetlinks.json', destination: '/well-known/assetlinks' }];
  },
  // The API lives on the same origin under /api (Caddy). In local development
  // the panel runs in mock mode (npm run dev:mock) and never calls it.
};

export default config;
