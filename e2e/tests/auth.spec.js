import { test, expect } from '@playwright/test'

function uniqueEmail() {
  return `e2e-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@atsready-tests.dev`
}

test('register, logout, and log back in', async ({ page }) => {
  const email = uniqueEmail()
  const password = 'e2e-test-pass-1'

  await page.goto('/register')
  await page.getByPlaceholder('Priya Sharma').fill('E2E Test User')
  await page.getByPlaceholder('you@example.com').fill(email)
  await page.getByPlaceholder('Min. 8 characters').fill(password)
  await page.getByRole('button', { name: 'Create account' }).click()

  // Register.jsx sends a fresh account straight to /metabase
  await expect(page).toHaveURL(/\/metabase/, { timeout: 15000 })
  await expect(page.getByRole('heading', { name: 'Metabase' })).toBeVisible()

  await page.getByTitle('Log out').click()
  await expect(page).toHaveURL(/\/login/, { timeout: 10000 })

  await page.getByPlaceholder('you@example.com').fill(email)
  await page.getByPlaceholder('••••••••').fill(password)
  await page.getByRole('button', { name: 'Sign in' }).click()

  await expect(page).toHaveURL(/\/dashboard/, { timeout: 15000 })
})

test('rejects an invalid login with a clear error', async ({ page }) => {
  await page.goto('/login')
  await page.getByPlaceholder('you@example.com').fill('nobody-e2e@atsready-tests.dev')
  await page.getByPlaceholder('••••••••').fill('whatever-password')
  await page.getByRole('button', { name: 'Sign in' }).click()

  await expect(page.getByText(/invalid email or password/i)).toBeVisible({ timeout: 10000 })
  await expect(page).toHaveURL(/\/login/)
})
