import { test, expect } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'

// Public pages only (no login needed). Fails on serious/critical WCAG A/AA issues.
const PAGES = ['/login', '/register', '/forgot-password', '/privacy', '/terms', '/no-such-page']

for (const scheme of ['light', 'dark']) for (const path of PAGES) {
  test(`no serious accessibility violations on ${path} (${scheme})`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme })
    await page.goto(path)
    await page.waitForLoadState('networkidle')
    const { violations } = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa'])
      .analyze()
    const bad = violations.filter(v => ['serious', 'critical'].includes(v.impact))
    expect(bad.map(v => `${v.id}: ${v.nodes.length} node(s) - ${v.help}`)).toEqual([])
  })
}

// Signed-in screens.
const APP_PAGES = ['/dashboard', '/generate', '/cover-letter', '/interview-prep', '/metabase', '/settings?section=security']

for (const scheme of ['light', 'dark']) {
  test(`no serious accessibility violations in the signed-in app (${scheme})`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme })
    await page.goto('/register')
    await page.getByPlaceholder('Priya Sharma').fill('A11y Tester')
    await page.getByPlaceholder('you@example.com').fill(`e2e-a11y-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@atsready-tests.dev`)
    await page.getByPlaceholder('Min. 8 characters').fill('e2e-test-pass-1')
    await page.getByRole('button', { name: 'Create account' }).click()
    await page.waitForURL(/\/metabase/)

    const problems = []
    for (const path of APP_PAGES) {
      await page.goto(path)
      await page.waitForLoadState('networkidle')
      await page.waitForTimeout(600)            // let route transition + skeletons settle
      const { violations } = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa']).analyze()
      for (const v of violations.filter(x => ['serious', 'critical'].includes(x.impact))) {
        problems.push(`${path}: ${v.id} (${v.nodes.length}) ${v.nodes[0].target.join(' ')}`)
      }
    }
    expect(problems).toEqual([])
  })
}
