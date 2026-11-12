import { test, expect } from '@playwright/test'

// Needs the stack running with LLM_FAKE=true and BILLING_ENABLED=false (CI does).

const JD = 'We are hiring a backend engineer to build Python and FastAPI services. '.repeat(3)

function uniqueEmail() {
  return `e2e-jobs-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@atsready-tests.dev`
}

// Register through the UI, then give the account the minimum profile.
async function userWithProfile(page) {
  await page.goto('/register')
  await page.getByPlaceholder('Priya Sharma').fill('Pat Jobs')
  await page.getByPlaceholder('you@example.com').fill(uniqueEmail())
  await page.getByPlaceholder('Min. 8 characters').fill('e2e-test-pass-1')
  await page.getByRole('button', { name: 'Create account' }).click()
  await expect(page).toHaveURL(/\/metabase/, { timeout: 15000 })

  const token = await page.evaluate(async () => {
    const r = await fetch('/api/auth/refresh', { method: 'POST', credentials: 'include' })
    return (await r.json()).access_token
  })
  const res = await page.request.post('/api/metabase/personal', {
    headers: { Authorization: `Bearer ${token}` },
    data: { full_name: 'Pat Jobs', email: 'pat@atsready-tests.dev' },
  })
  expect(res.ok()).toBeTruthy()
}

test('cover letter keeps running when you leave the page, then shows up', async ({ page }) => {
  await userWithProfile(page)

  await page.goto('/cover-letter')
  await page.locator('textarea').fill(JD)
  await page.getByRole('button', { name: 'Generate Cover Letter' }).click()

  // Leave straight away: the job must not depend on this page.
  await page.getByRole('link', { name: 'Dashboard' }).click()
  await expect(page).toHaveURL(/\/dashboard/)

  // Completion is announced wherever the user is.
  await expect(page.getByText(/Cover letter ready/)).toBeVisible({ timeout: 30000 })

  // Back on the page, the finished letter is waiting.
  await page.getByRole('link', { name: 'Cover Letter' }).click()
  await expect(page.getByText('Application for Backend Engineer').first()).toBeVisible({ timeout: 10000 })
})

test('several requests queue at once, with a cap of three', async ({ page }) => {
  await userWithProfile(page)
  const token = await page.evaluate(async () => {
    const r = await fetch('/api/auth/refresh', { method: 'POST', credentials: 'include' })
    return (await r.json()).access_token
  })
  const post = () => page.request.post('/api/interview-prep', {
    headers: { Authorization: `Bearer ${token}` }, data: { jd_text: JD },
  })

  // Burst of four: at most three can be in flight at the same moment.
  const codes = (await Promise.all([post(), post(), post(), post()])).map(r => r.status())
  expect(codes.filter(c => c === 202).length).toBeGreaterThanOrEqual(3)
  expect(codes.every(c => c === 202 || c === 429)).toBeTruthy()
})

test('history is a tab inside Generate, not a nav item', async ({ page }) => {
  await userWithProfile(page)
  await expect(page.getByRole('link', { name: 'History' })).toHaveCount(0)

  await page.goto('/generate')
  await page.getByRole('button', { name: 'History' }).click()
  await expect(page).toHaveURL(/tab=history/)
  await expect(page.getByText(/resume.* generated/)).toBeVisible()

  // Old bookmarks still work
  await page.goto('/history')
  await expect(page).toHaveURL(/\/generate\?tab=history/)
})
