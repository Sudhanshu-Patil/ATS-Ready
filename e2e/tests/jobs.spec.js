import { test, expect } from '@playwright/test'

// Needs the stack running with LLM_FAKE=true and BILLING_ENABLED=false (CI does).

const JD = 'We are hiring a backend engineer to build Python and FastAPI services. '.repeat(3)

function uniqueEmail() {
  return `e2e-job-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@atsready-tests.dev`
}

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

test('paste the job once, then make a resume, cover letter and answers from it without pasting again', async ({ page }) => {
  await userWithProfile(page)

  // Start the job: the only time the posting is pasted.
  await page.goto('/jobs')
  await page.getByRole('button', { name: 'New job' }).click()
  await page.getByLabel('Job description').fill(JD)
  await page.getByLabel('Company').fill('Acme')
  await page.getByLabel('Role').fill('Backend Engineer')
  await page.getByRole('button', { name: 'Start this job' }).click()
  await expect(page).toHaveURL(/\/jobs\/[0-9a-f-]{36}/)
  await expect(page.getByRole('heading', { name: /Acme · Backend Engineer/ })).toBeVisible()

  // Resume from the saved posting: no textarea to fill.
  await page.locator('a[href*="/generate?job="]').first().click()
  await expect(page.getByLabel('Current job')).toContainText('Acme · Backend Engineer')
  await expect(page.getByPlaceholder('Paste the full job description here…')).toHaveCount(0)
  await page.getByRole('button', { name: /^generate resume$/i }).click()
  await expect(page.getByRole('link', { name: 'Download DOCX' })).toBeVisible({ timeout: 60000 })

  // Cover letter for the same job, again without pasting.
  await page.getByRole('link', { name: 'All of this job' }).click()
  await page.locator('a[href*="/cover-letter?job="]:not([href*="tab="])').first().click()
  await expect(page.getByPlaceholder('Paste the full job description here…')).toHaveCount(0)
  await page.getByRole('button', { name: 'Generate Cover Letter' }).click()
  await expect(page.getByText('Application for Backend Engineer').first()).toBeVisible({ timeout: 60000 })

  // Application answers for the same job.
  await page.getByRole('link', { name: 'All of this job' }).click()
  await page.locator('a[href*="/assistant?job="]').first().click()
  await page.getByLabel('Application questions').fill('Why do you want this role?')
  await page.getByRole('button', { name: 'Answer my questions' }).click()
  await expect(page.getByLabel(/Answer to: Why do you want this role/)).toBeVisible({ timeout: 30000 })

  // Everything is on the job's page.
  await page.getByRole('link', { name: 'All of this job' }).click()
  await expect(page.getByText('Resumes for this job')).toBeVisible()
  await expect(page.getByText('Application answers').first()).toBeVisible()
})

test('a job made from a pasted posting in a tool can be continued from there', async ({ page }) => {
  await userWithProfile(page)
  await page.goto('/cover-letter')
  await page.locator('textarea').first().fill(JD)
  await page.getByRole('button', { name: 'Generate Cover Letter' }).click()
  await expect(page.getByText('Application for Backend Engineer').first()).toBeVisible({ timeout: 60000 })
  await page.getByRole('link', { name: /Keep working on this job/ }).click()
  await expect(page).toHaveURL(/\/jobs\/[0-9a-f-]{36}/)
  await expect(page.getByText(/Cover letter/).first()).toBeVisible()
})

test('old tracker links land on the jobs list', async ({ page }) => {
  await userWithProfile(page)
  await page.goto('/applications')
  await expect(page).toHaveURL(/\/jobs$/)
  await page.goto('/settings?section=plan')
  await expect(page.getByText('Your credits')).toBeVisible()
})
