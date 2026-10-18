import { defineConfig, devices } from '@playwright/test';

// End-to-end smoke over the demo holding (NEXT_PUBLIC_HQ_MOCK=1): every page renders without errors, and the owner's
// main actions work end to end against the mock. CI runs it in the official Playwright image; locally HQ_CHROMIUM can
// point at a preinstalled Chromium.
const port = Number(process.env.HQ_E2E_PORT ?? 3100);

export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['github'], ['list']] : 'list',
  use: {
    baseURL: `http://localhost:${port}`,
    locale: 'fa-IR',
    colorScheme: 'dark',
    trace: 'retain-on-failure',
    launchOptions: process.env.HQ_CHROMIUM ? { executablePath: process.env.HQ_CHROMIUM } : {},
  },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 1000 } } },
    { name: 'phone', use: { ...devices['Pixel 7'] }, grep: /@phone/ },
  ],
  webServer: {
    command: `npx next dev --port ${port}`,
    env: { NEXT_PUBLIC_HQ_MOCK: '1', NEXT_TELEMETRY_DISABLED: '1' },
    url: `http://localhost:${port}/healthz`,
    timeout: 180_000,
    reuseExistingServer: !process.env.CI,
  },
});
