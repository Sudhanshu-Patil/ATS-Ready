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
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
})
