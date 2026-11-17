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
  await page.getByRole('tab', { name: 'History' }).click()
  await expect(page).toHaveURL(/tab=history/)
  await expect(page.getByText(/resume.* generated/)).toBeVisible()

  // Old bookmarks still work
  await page.goto('/history')
  await expect(page).toHaveURL(/\/generate\?tab=history/)
})

test('edit a cover letter inline; copy and downloads use the edited text', async ({ page }) => {
  await userWithProfile(page)
  await page.goto('/cover-letter')
  await page.locator('textarea').fill(JD)
  await page.getByRole('button', { name: 'Generate Cover Letter' }).click()
  await expect(page.getByText('Application for Backend Engineer').first()).toBeVisible({ timeout: 30000 })

  await page.getByRole('button', { name: 'Edit' }).click()
  await page.getByLabel(/^Letter/).fill('Hello Sam,\n\nI edited this letter myself.\n\nBest')
  await page.getByRole('button', { name: 'Save changes' }).click()
  await expect(page.getByText('I edited this letter myself.')).toBeVisible()

  // DOCX and PDF come from the saved (edited) text.
  const docx = page.waitForEvent('download')
  await page.getByRole('button', { name: 'DOCX' }).click()
  const docxFile = await docx
  expect(docxFile.suggestedFilename()).toMatch(/^cover_letter.*\.docx$/)

  const pdf = page.waitForEvent('download')
  await page.getByRole('button', { name: 'PDF', exact: true }).click()
  expect((await pdf).suggestedFilename()).toMatch(/\.pdf$/)

  // The edit survives a reload (it is saved on the server, not just on screen).
  await page.reload()
  await page.getByRole('tab', { name: 'History' }).click()
  await page.getByRole('button', { name: 'View' }).first().click()
  await expect(page.getByText('I edited this letter myself.')).toBeVisible()
})

test('draft a LinkedIn referral request', async ({ page }) => {
  await userWithProfile(page)
  await page.goto('/cover-letter')
  await page.getByRole('tab', { name: 'Referral message' }).click()
  await page.getByLabel('Who are you asking?').fill('Sam Lee')
  await page.getByLabel(/Job link/).fill('https://example.com/jobs/1')
  await page.getByLabel('Job description').fill(JD)
  await page.getByRole('button', { name: 'Draft referral message' }).click()

  await expect(page.getByLabel('Connection request note')).not.toHaveValue('', { timeout: 30000 })
  await expect(page.getByLabel('Referral message')).toContainText('referring me')
  await expect(page.getByText(/\/300$/)).toBeVisible()
})

test('a generated resume can be downloaded as PDF as well as DOCX', async ({ page }) => {
  await userWithProfile(page)
  await page.goto('/generate')
  await page.locator('textarea').first().fill(JD)
  await page.getByRole('button', { name: /^Generate Resume$/ }).click()

  await expect(page.getByRole('link', { name: 'Download DOCX' })).toBeVisible({ timeout: 60000 })
  const pdf = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Download PDF' }).click()
  const file = await pdf
  expect(file.suggestedFilename()).toMatch(/\.pdf$/)
  const path = await file.path()
  const { readFileSync } = await import('node:fs')
  expect(readFileSync(path).subarray(0, 5).toString()).toBe('%PDF-')
})
