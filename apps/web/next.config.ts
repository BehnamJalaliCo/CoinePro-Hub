import type { NextConfig } from 'next';

const config: NextConfig = {
  output: 'standalone',
  poweredByHeader: false,
  reactStrictMode: true,
  productionBrowserSourceMaps: false,
  images: { unoptimized: true },
  // Project rules live in the repository's CLAUDE.md; Next must not write its own agent files here.
  agentRules: false,
  // The API lives on the same origin under /api (Caddy). In local development
  // the panel runs in mock mode (npm run dev:mock) and never calls it.
};

export default config;
