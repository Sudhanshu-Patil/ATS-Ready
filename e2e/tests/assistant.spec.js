import { test, expect } from '@playwright/test'

// Needs the stack running with LLM_FAKE=true and BILLING_ENABLED=false (CI does).

function uniqueEmail() {
  return `e2e-assist-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@atsready-tests.dev`
}

async function userWithProfile(page) {
  await page.goto('/register')
  await page.getByPlaceholder('Priya Sharma').fill('Pat Assist')
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
    data: { full_name: 'Pat Assist', email: 'pat@atsready-tests.dev' },
  })
  expect(res.ok()).toBeTruthy()
}

test('questions only: answers appear, the company question pops up and survives a refresh', async ({ page }) => {
  await userWithProfile(page)
  await page.goto('/assistant')
  await page.getByLabel('Application questions').fill('Why do you want this role?\nWhat is your notice period?')
  await page.getByRole('button', { name: 'Answer my questions' }).click()

  // The fake model answers the first question; the notice period is never guessed, so it is asked back.
  await expect(page.getByLabel(/Answer to: Why do you want this role/)).toBeVisible({ timeout: 30000 })
  await expect(page.getByText(/I will not guess this/)).toBeVisible()

  // No company was given, so the popup asks, and it is still there after a refresh.
  const dialog = page.getByRole('dialog', { name: 'Which job was this for?' })
  await expect(dialog).toBeVisible({ timeout: 10000 })
  await page.reload()
  await expect(dialog).toBeVisible({ timeout: 10000 })

  await dialog.getByLabel('Company').fill('Acme')
  await dialog.getByLabel('Role').fill('Backend Engineer')
  await dialog.getByRole('button', { name: 'Save' }).click()
  await expect(dialog).toBeHidden()

  // The tracker has it, with the date it was asked.
  await page.goto('/applications')
  await expect(page.getByText('Acme · Backend Engineer')).toBeVisible()
  await expect(page.getByText(/Asked /)).toBeVisible()
})

test('a request sent while offline is delivered when the connection returns', async ({ page, context }) => {
  await userWithProfile(page)
  await page.goto('/assistant')
  await page.getByLabel('Application questions').fill('Tell me about yourself')
  await context.setOffline(true)
  await page.getByRole('button', { name: 'Answer my questions' }).click()
  await expect(page.getByText(/You are offline/).first()).toBeVisible()
  await context.setOffline(false)
  await page.evaluate(() => window.dispatchEvent(new Event('online')))
  await expect(page.getByLabel(/Answer to: Tell me about yourself/)).toBeVisible({ timeout: 30000 })
})
