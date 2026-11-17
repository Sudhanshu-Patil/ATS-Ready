import { test, expect } from '@playwright/test'

// Credits on: run with the API started with BILLING_ENABLED=true and E2E_BILLING=1 (CI runs with billing off, so skipped).
test.skip(!process.env.E2E_BILLING, 'needs BILLING_ENABLED=true on the API')

const JD = 'We are hiring a backend engineer to build Python and FastAPI services. '.repeat(3)

test('a job without credits opens the buy dialog and nothing is created', async ({ page }) => {
  await page.goto('/register')
  await page.getByPlaceholder('Priya Sharma').fill('Pat Billing')
  await page.getByPlaceholder('you@example.com').fill(`e2e-bill-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@atsready-tests.dev`)
  await page.getByPlaceholder('Min. 8 characters').fill('e2e-test-pass-1')
  await page.getByRole('button', { name: 'Create account' }).click()
  await expect(page).toHaveURL(/\/metabase/, { timeout: 15000 })
  const token = await page.evaluate(async () => {
    const r = await fetch('/api/auth/refresh', { method: 'POST', credentials: 'include' })
    return (await r.json()).access_token
  })
  await page.request.post('/api/metabase/personal', {
    headers: { Authorization: `Bearer ${token}` }, data: { full_name: 'Pat Billing', email: 'pat@atsready-tests.dev' } })

  // Starting a job is free.
  await page.goto('/jobs')
  await page.getByRole('button', { name: 'New job' }).click()
  await page.getByLabel('Job description').fill(JD)
  await page.getByLabel('Company').fill('Acme')
  await page.getByLabel('Role').fill('Backend Engineer')
  await page.getByRole('button', { name: 'Start this job' }).click()
  await expect(page).toHaveURL(/\/jobs\/[0-9a-f-]{36}/)
  await expect(page.getByText(/Not unlocked yet/)).toBeVisible()

  // The first thing made from it needs a credit: the buy dialog opens.
  await page.locator('a[href*="/cover-letter?job="]:not([href*="tab="])').first().click()
  await page.getByRole('button', { name: 'Generate Cover Letter' }).click()
  const dialog = page.getByRole('dialog', { name: /Unlock this job with a credit/ })
  await expect(dialog).toBeVisible()
  await expect(dialog.getByText('₹10', { exact: true })).toBeVisible()
  await expect(dialog.getByText('₹99', { exact: true })).toBeVisible()
  await dialog.getByRole('button', { name: 'Not now' }).click()
  await expect(dialog).toBeHidden()

  // Billing page: balance and invite link.
  await page.goto('/settings?section=billing')
  await expect(page.getByTestId('credits-job')).toHaveText('0')
  await expect(page.getByLabel('Your invite link')).toHaveValue(/\/register\?ref=/)
})
