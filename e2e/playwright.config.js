import { defineConfig, devices } from '@playwright/test'

// Runs against the dev docker-compose stack (Vite dev server on :5173,
// proxying /api to FastAPI on :8000) — the same setup used for every manual
// verification throughout this project's development, not a separate
// CI-only environment that could drift from what actually gets tested by
// hand during development.
export default defineConfig({
  testDir: './tests',
  fullyParallel: true,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 2 : undefined,
  reporter: process.env.CI ? [['github'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:5173',
    // Pre-dismiss the cookie notice so it never covers buttons; its own test clears this.
    storageState: {
      cookies: [],
      origins: [{
        origin: new URL(process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:5173').origin,
        localStorage: [{ name: 'cookie-notice-seen', value: '1' }],
      }],
    },
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    // Full suite on desktop Chrome.
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    // Other engines and phones: public pages, auth and accessibility only (fast, no LLM flow).
    { name: 'firefox', use: { ...devices['Desktop Firefox'] }, testMatch: /(auth|a11y|account)\.spec/ },
    { name: 'webkit', use: { ...devices['Desktop Safari'] }, testMatch: /(auth|a11y|account)\.spec/ },
    { name: 'pixel-7', use: { ...devices['Pixel 7'] }, testMatch: /(auth|a11y|account)\.spec/ },
    { name: 'iphone-14', use: { ...devices['iPhone 14'] }, testMatch: /(auth|a11y|account)\.spec/ },
  ],
})
