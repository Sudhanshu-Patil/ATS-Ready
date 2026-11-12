import { test, expect } from '@playwright/test'

function uniqueEmail() {
  return `e2e-acct-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@atsready-tests.dev`
}
const PASSWORD = 'e2e-test-pass-1'

async function register(page, email) {
  await page.goto('/register')
  await page.getByPlaceholder('Priya Sharma').fill('Acct Tester')
  await page.getByPlaceholder('you@example.com').fill(email)
  await page.getByPlaceholder('Min. 8 characters').fill(PASSWORD)
  await page.getByRole('button', { name: 'Create account' }).click()
  await expect(page).toHaveURL(/\/metabase/, { timeout: 15000 })
}

test('unknown URLs show a real 404 page', async ({ page }) => {
  await page.goto('/definitely-not-a-page')
  await expect(page.getByRole('heading', { name: /can't find that page/i })).toBeVisible()
  await expect(page.getByRole('link', { name: /back to ats-ready/i })).toBeVisible()
})

test('privacy and terms pages are public', async ({ page }) => {
  await page.goto('/privacy')
  await expect(page.getByRole('heading', { name: 'Privacy policy' })).toBeVisible()
  await page.goto('/terms')
  await expect(page.getByRole('heading', { name: 'Terms of service' })).toBeVisible()
})

test('export my data, then delete the account for good', async ({ page }) => {
  const email = uniqueEmail()
  await register(page, email)

  await page.goto('/settings?section=security')
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Download my data' }).click()
  expect((await download).suggestedFilename()).toBe('ats-ready-data.json')

  await page.getByRole('button', { name: /delete my account/i }).click()
  await page.getByLabel(/type your email/i).fill(email)
  await page.getByLabel(/^password/i).fill(PASSWORD)
  await page.getByRole('button', { name: 'Delete everything' }).click()
  await expect(page).toHaveURL(/\/$/, { timeout: 15000 })

  // The account no longer exists.
  await page.goto('/login')
  await page.getByPlaceholder('you@example.com').fill(email)
  await page.getByPlaceholder('••••••••').fill(PASSWORD)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByText(/invalid email or password/i)).toBeVisible({ timeout: 10000 })
})

test('"sign out everywhere" ends the session', async ({ page }) => {
  await register(page, uniqueEmail())
  await page.goto('/settings?section=security')
  await page.getByRole('button', { name: 'Sign out everywhere' }).click()
  await expect(page).toHaveURL(/\/login/, { timeout: 10000 })
})

test.describe('cookie notice', () => {
  test.use({ storageState: { cookies: [], origins: [] } })

  test('is shown once, explains the cookies and can be dismissed', async ({ page }) => {
    await page.goto('/privacy')
    const notice = page.getByRole('region', { name: 'Cookie notice' })
    await expect(notice).toBeVisible()
    await expect(notice).toContainText(/only the cookies needed/i)
    await notice.getByRole('button', { name: 'Got it' }).click()
    await expect(notice).toBeHidden()
    await page.reload()
    await expect(notice).toBeHidden()
  })
})
