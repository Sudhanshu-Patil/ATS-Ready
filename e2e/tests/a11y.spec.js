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
