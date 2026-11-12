import { test, expect } from '@playwright/test'

// Chromium only (uses the DevTools protocol). Throttles to roughly "Slow 4G" / "Fast 3G"
// and checks that the app still renders and responds, instead of hanging on a blank page.
// Meant for the PRODUCTION bundle: the Vite dev server ships hundreds of unbundled modules and
// would never load at this speed. Run with SLOW_NETWORK=1 against `vite preview`.
test.skip(({ browserName }) => browserName !== 'chromium', 'CDP throttling is Chromium-only')
test.skip(!process.env.SLOW_NETWORK, 'set SLOW_NETWORK=1 and point PLAYWRIGHT_BASE_URL at a production build')

async function throttle(page, { latency, down, up }) {
  const cdp = await page.context().newCDPSession(page)
  await cdp.send('Network.enable')
  await cdp.send('Network.emulateNetworkConditions', {
    offline: false, latency, downloadThroughput: down, uploadThroughput: up,
  })
}

test('login page is usable on a slow connection', async ({ page }) => {
  await throttle(page, { latency: 400, down: (400 * 1024) / 8, up: (400 * 1024) / 8 })   // ~400 kbps, 400 ms
  const started = Date.now()
  await page.goto('/login', { waitUntil: 'commit' })
  await expect(page.getByRole('button', { name: 'Sign in' })).toBeVisible({ timeout: 45000 })
  expect(Date.now() - started).toBeLessThan(45000)
})

test('a failed network call shows an error, not an endless spinner', async ({ page }) => {
  await page.goto('/login')
  await page.route('**/api/auth/login', (route) => route.abort('internetdisconnected'))
  await page.getByPlaceholder('you@example.com').fill('someone@atsready-tests.dev')
  await page.getByPlaceholder('••••••••').fill('whatever-pass-1')
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('button', { name: 'Sign in' })).toBeEnabled({ timeout: 15000 })
  await expect(page).toHaveURL(/\/login/)
})
