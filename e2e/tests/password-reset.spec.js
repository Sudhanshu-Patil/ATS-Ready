import { test, expect } from '@playwright/test'
import { logout } from './helpers.js'

// Needs Mailpit (the dev stack's mail catcher, UI/API on :8025). Skipped when it is not running.
const MAILPIT = process.env.MAILPIT_URL || 'http://localhost:8025'

test('forgot password -> email link -> new password -> log in', async ({ page, request }) => {
  const up = await request.get(`${MAILPIT}/api/v1/messages`).then((r) => r.ok(), () => false)
  test.skip(!up, 'Mailpit is not running')

  const email = `e2e-reset-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@atsready-tests.dev`
  const oldPassword = 'old-pass-12345'
  const newPassword = 'brand-new-pass-678'

  await page.goto('/register')
  await page.getByPlaceholder('Priya Sharma').fill('Reset Tester')
  await page.getByPlaceholder('you@example.com').fill(email)
  await page.getByPlaceholder('Min. 8 characters').fill(oldPassword)
  await page.getByRole('button', { name: 'Create account' }).click()
  await expect(page).toHaveURL(/\/metabase/, { timeout: 15000 })
  await logout(page)

  await page.goto('/forgot-password')
  await page.getByPlaceholder('you@example.com').fill(email)
  await page.getByRole('button', { name: 'Send reset link' }).click()

  // Find the reset email for this address.
  let link = null
  for (let i = 0; i < 20 && !link; i++) {
    const list = await (await request.get(`${MAILPIT}/api/v1/search?query=${encodeURIComponent('to:' + email)}`)).json()
    if (list.messages?.length) {
      const msg = await (await request.get(`${MAILPIT}/api/v1/message/${list.messages[0].ID}`)).json()
      link = (msg.Text.match(/https?:\/\/\S*reset-password\?\S+/) || [])[0]
    }
    if (!link) await page.waitForTimeout(500)
  }
  expect(link, 'reset email with a link').toBeTruthy()

  await page.goto(link.replace(/^https?:\/\/[^/]+/, ''))     // keep the path/query, use the test origin
  await page.getByPlaceholder('Min. 8 characters').fill(newPassword)
  await page.getByPlaceholder('Repeat the new password').fill(newPassword)
  await page.getByRole('button', { name: 'Reset password' }).click()
  await expect(page).toHaveURL(/\/login/, { timeout: 15000 })

  await page.getByPlaceholder('you@example.com').fill(email)
  await page.getByPlaceholder('••••••••').fill(oldPassword)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByText(/invalid email or password/i)).toBeVisible({ timeout: 10000 })

  await page.getByPlaceholder('••••••••').fill(newPassword)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page).toHaveURL(/\/dashboard/, { timeout: 15000 })
})
