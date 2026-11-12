import { test, expect } from '@playwright/test'

function uniqueEmail() {
  return `e2e-metabase-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@atsready-tests.dev`
}

// Fresh account per test — registering lands directly on /metabase, so no
// separate login step is needed.
async function registerFreshUser(page) {
  const email = uniqueEmail()
  await page.goto('/register')
  await page.getByPlaceholder('Priya Sharma').fill('E2E Metabase User')
  await page.getByPlaceholder('you@example.com').fill(email)
  await page.getByPlaceholder('Min. 8 characters').fill('e2e-test-pass-1')
  await page.getByRole('button', { name: 'Create account' }).click()
  await expect(page).toHaveURL(/\/metabase/, { timeout: 15000 })
}

test('add a skill, edit it, and see the change persist after reload', async ({ page }) => {
  await registerFreshUser(page)

  await page.getByRole('tab', { name: 'Skills' }).click()
  await page.getByPlaceholder('Skill name (e.g. Python)').fill('Rust')
  await page.getByPlaceholder('Category').fill('Programming Languages')
  await page.getByRole('button', { name: 'Add skill' }).click()

  // The skill chip's outer container (identified by its distinctive class,
  // not a text-based .last() guess — the edit panel renders as a *sibling*
  // of the name/badges row once opened, so scoping too deep would miss it).
  // Scoping matters here to avoid matching the identical <option>Expert</option>
  // that's always present in the "Add skill" form's proficiency <select>.
  const skillChip = page.locator('div.rounded-lg.border').filter({ hasText: 'Rust' })
  await expect(skillChip.getByText('Intermediate')).toBeVisible({ timeout: 10000 })

  // Edit: bump proficiency to Expert
  await skillChip.getByRole('button', { name: 'Edit' }).click()
  await skillChip.locator('select').selectOption('Expert')
  await skillChip.getByRole('button', { name: 'Save changes' }).click()
  // Edit panel unmounts once the save resolves — wait for that rather than
  // asserting on text that's ambiguous while the <select> is still present.
  await expect(skillChip.getByRole('button', { name: 'Cancel' })).toBeHidden({ timeout: 10000 })
  await expect(skillChip.getByText('Expert', { exact: true })).toBeVisible()

  // Reload — this is the exact regression the user reported: edits used to
  // exist only in local state and vanish (or never apply) on refresh.
  await page.reload()
  await page.getByRole('tab', { name: 'Skills' }).click()
  const skillChipAfterReload = page.locator('div.rounded-lg.border').filter({ hasText: 'Rust' })
  await expect(skillChipAfterReload.getByText('Expert', { exact: true })).toBeVisible({ timeout: 10000 })
})

test('add an experience with a description and see it tied to the UI on edit', async ({ page }) => {
  await registerFreshUser(page)

  await page.getByRole('tab', { name: 'Experience' }).click()
  await page.getByPlaceholder('Company').fill('Acme Corp')
  await page.getByPlaceholder('Role').fill('Senior Engineer')
  await page.getByPlaceholder(/start date/i).fill('Jan 2023')
  await page.getByPlaceholder('Describe your impact, responsibilities, and achievements').first().fill('Led the platform team')
  await page.getByRole('button', { name: 'Add experience' }).click()

  await expect(page.getByText('Acme Corp')).toBeVisible({ timeout: 10000 })
  await expect(page.getByText('Led the platform team')).toBeVisible()

  await page.getByTitle('Edit experience').click()
  const textareas = page.getByPlaceholder('Describe your impact, responsibilities, and achievements')
  await textareas.last().fill('Led the platform team and mentored 3 engineers')
  await page.getByRole('button', { name: 'Save changes' }).click()

  await expect(page.getByText('Led the platform team and mentored 3 engineers')).toBeVisible({ timeout: 10000 })
})
